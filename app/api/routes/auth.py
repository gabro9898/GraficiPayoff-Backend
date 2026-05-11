from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from app.config import get_settings
from app.database import get_db
from app.controllers.auth_controller import AuthController
from app.schemas.user import (
    ForgotPasswordRequest,
    RefreshTokenRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.auth_service import VERIFICATION_TOKEN_EXPIRY_HOURS
from app.services.email_service import send_transactional_email
from app.services.email_templates import (
    password_reset_email,
    verification_email,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _build_verification_url(token: str) -> str:
    """Costruisce il link di verifica che punta al landing.
    Esempio: https://optiontracker.optiontraders.it/verify-email?token=...
    """
    settings = get_settings()
    base = settings.LANDING_URL.rstrip("/")
    query = urlencode({"token": token})
    return f"{base}/verify-email?{query}"


def _send_verification_email_bg(
    background_tasks: BackgroundTasks,
    *,
    to_email: str,
    first_name: str,
    last_name: str,
    token: str,
) -> None:
    """Helper: schedula l'invio dell'email di verifica. Usato sia da register
    che da resend-verification così la pipeline è identica.
    """
    subject, html, text = verification_email(
        first_name=first_name,
        verification_url=_build_verification_url(token),
        expires_in_hours=VERIFICATION_TOKEN_EXPIRY_HOURS,
    )
    background_tasks.add_task(
        send_transactional_email,
        to_email=to_email,
        to_name=f"{first_name} {last_name}",
        subject=subject,
        html_content=html,
        text_content=text,
    )


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(
    data: UserRegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Crea un nuovo utente con email_verified=False e invia l'email di verifica.
    NON ritorna token di accesso: l'utente deve cliccare il link nell'email per
    poter loggare.
    """
    controller = AuthController(db)
    user, issued = controller.register(data)

    _send_verification_email_bg(
        background_tasks,
        to_email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        token=issued.token,
    )

    return RegisterResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
    )


@router.post("/login", response_model=TokenResponse)
def login(data: UserLoginRequest, db: Session = Depends(get_db)):
    """Login. Solleva 403 EmailNotVerifiedException se l'utente non ha
    ancora confermato l'email — il frontend deve mostrare il pulsante
    "reinvia email di verifica".
    """
    controller = AuthController(db)
    return controller.login(data)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshTokenRequest, db: Session = Depends(get_db)):
    controller = AuthController(db)
    return controller.refresh_token(data)


@router.post("/verify-email", status_code=200)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Conferma l'indirizzo email tramite il token ricevuto via email.
    Solleva 400 InvalidVerificationTokenException se il token è scaduto,
    già usato, o non valido. Idempotente: se l'utente è già verificato,
    risponde comunque 200.
    """
    controller = AuthController(db)
    user = controller.verify_email(data.token)
    return {
        "message": "Email verified successfully.",
        "email": user.email,
        "email_verified": user.email_verified,
    }


@router.post("/resend-verification", status_code=200)
def resend_verification(
    data: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Reinvia l'email di verifica. Rate-limited a 1 invio ogni 60 secondi
    per utente (solleva 429 con Retry-After).
    Risponde 200 anche se l'email non esiste o è già verificata, per non
    rivelare la lista email registrate.
    """
    controller = AuthController(db)
    issued = controller.resend_verification_email(data.email)

    if issued is not None:
        _send_verification_email_bg(
            background_tasks,
            to_email=issued.user.email,
            first_name=issued.user.first_name,
            last_name=issued.user.last_name,
            token=issued.token,
        )

    return {"message": "If the email is registered and not yet verified, a new verification link has been sent."}


@router.post("/forgot-password", status_code=200)
def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Invia un codice OTP via email per reimpostare la password.
    Risponde sempre 200, anche se l'email non è registrata, per non rivelare
    la lista degli utenti.
    """
    controller = AuthController(db)
    issued = controller.issue_password_reset_code(data.email)

    if issued.user_found:
        subject, html, text = password_reset_email(
            first_name=issued.user.first_name,
            code=issued.code,
            expires_in_minutes=issued.expires_in_minutes,
        )
        background_tasks.add_task(
            send_transactional_email,
            to_email=issued.user.email,
            to_name=f"{issued.user.first_name} {issued.user.last_name}",
            subject=subject,
            html_content=html,
            text_content=text,
        )

    return {"message": "If the email is registered, a reset code has been sent."}


@router.post("/reset-password", status_code=200)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Verifica il codice OTP e imposta la nuova password."""
    controller = AuthController(db)
    controller.reset_password(data.email, data.code, data.new_password)
    return {"message": "Password updated successfully."}
