import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.password_reset import PasswordResetCode
from app.models.user import User
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserRegisterRequest, UserLoginRequest, TokenResponse
from app.utils.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidResetCodeException,
    InvalidTokenException,
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


# Configurazione del flusso password-reset
RESET_CODE_LENGTH = 6
RESET_CODE_EXPIRY_MINUTES = 30
RESET_CODE_MAX_ATTEMPTS = 5


@dataclass
class PasswordResetIssued:
    """Risultato di una richiesta di forgot-password.
    Se user_found è False, nessun codice è stato generato e nessuna email
    deve partire (l'utente non esiste). La route comunque restituisce 200
    al chiamante per non rivelare quali email sono registrate.
    """
    user_found: bool
    user: User | None = None
    code: str | None = None
    expires_in_minutes: int = RESET_CODE_EXPIRY_MINUTES


class AuthService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)
        self.reset_repo = PasswordResetRepository(db)

    # --- Registration / login / refresh ---

    def register(self, data: UserRegisterRequest) -> User:
        existing = self.user_repo.find_by_email(data.email)
        if existing:
            raise EmailAlreadyExistsException()

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
        )
        return self.user_repo.create(user)

    def login(self, data: UserLoginRequest) -> TokenResponse:
        user = self.user_repo.find_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise InvalidCredentialsException()

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    def refresh_token(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise InvalidTokenException()

        user_id = payload.get("sub")
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise InvalidTokenException()

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    # --- Password reset ---

    def issue_password_reset_code(self, email: str) -> PasswordResetIssued:
        """Genera un codice OTP per il reset password e lo salva su DB.
        Se l'email non esiste, ritorna user_found=False senza sollevare
        eccezioni — la privacy impone che la risposta HTTP sia identica
        in entrambi i casi.
        Tutti i codici precedenti dell'utente vengono invalidati.
        """
        user = self.user_repo.find_by_email(email)
        if not user:
            return PasswordResetIssued(user_found=False)

        # Invalida eventuali codici precedenti ancora attivi
        self.reset_repo.invalidate_active_for_user(user.id)

        # Genera codice numerico a N cifre, sempre con leading zeros
        code = f"{secrets.randbelow(10 ** RESET_CODE_LENGTH):0{RESET_CODE_LENGTH}d}"

        reset = PasswordResetCode(
            user_id=user.id,
            code_hash=hash_password(code),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=RESET_CODE_EXPIRY_MINUTES),
        )
        self.reset_repo.create(reset)

        return PasswordResetIssued(
            user_found=True,
            user=user,
            code=code,
            expires_in_minutes=RESET_CODE_EXPIRY_MINUTES,
        )

    def reset_password(self, email: str, code: str, new_password: str) -> None:
        """Verifica il codice e applica la nuova password.
        Solleva InvalidResetCodeException se:
        - email sconosciuta
        - nessun codice attivo
        - codice scaduto / già usato / sbagliato
        - troppi tentativi sullo stesso codice
        """
        user = self.user_repo.find_by_email(email)
        if not user:
            raise InvalidResetCodeException()

        active = self.reset_repo.find_active_by_user(user.id)
        if not active:
            raise InvalidResetCodeException()

        if active.attempts >= RESET_CODE_MAX_ATTEMPTS:
            # Brucia il codice: deve richiederne uno nuovo
            self.reset_repo.mark_used(active)
            raise InvalidResetCodeException()

        if not verify_password(code, active.code_hash):
            self.reset_repo.increment_attempts(active)
            raise InvalidResetCodeException()

        # Codice valido: aggiorna password e brucia il codice
        self.user_repo.update(user, {"hashed_password": hash_password(new_password)})
        self.reset_repo.mark_used(active)
