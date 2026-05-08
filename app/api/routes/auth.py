from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.controllers.auth_controller import AuthController
from app.schemas.user import (
    ForgotPasswordRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.email_service import send_transactional_email
from app.services.email_templates import password_reset_email, welcome_email

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    data: UserRegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    controller = AuthController(db)
    user = controller.register(data)

    subject, html, text = welcome_email(user.first_name)
    background_tasks.add_task(
        send_transactional_email,
        to_email=user.email,
        to_name=f"{user.first_name} {user.last_name}",
        subject=subject,
        html_content=html,
        text_content=text,
    )

    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLoginRequest, db: Session = Depends(get_db)):
    controller = AuthController(db)
    return controller.login(data)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshTokenRequest, db: Session = Depends(get_db)):
    controller = AuthController(db)
    return controller.refresh_token(data)


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
