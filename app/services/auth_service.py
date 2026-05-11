import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.email_verification import EmailVerificationToken
from app.models.password_reset import PasswordResetCode
from app.models.user import User
from app.repositories.email_verification_repository import EmailVerificationRepository
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserRegisterRequest, UserLoginRequest, TokenResponse
from app.utils.exceptions import (
    EmailAlreadyExistsException,
    EmailNotVerifiedException,
    InvalidCredentialsException,
    InvalidResetCodeException,
    InvalidTokenException,
    InvalidVerificationTokenException,
    VerificationRateLimitException,
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

# Configurazione del flusso email-verification
VERIFICATION_TOKEN_BYTES = 32          # secrets.token_urlsafe(32) → ~43 char URL-safe
VERIFICATION_TOKEN_EXPIRY_HOURS = 24
VERIFICATION_RESEND_COOLDOWN_SECONDS = 60


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


@dataclass
class VerificationTokenIssued:
    """Risultato dell'emissione di un token di verifica email.
    Il token in chiaro va inserito nel link inviato all'utente; sul DB
    salviamo solo l'hash.
    """
    user: User
    token: str
    expires_in_hours: int = VERIFICATION_TOKEN_EXPIRY_HOURS


class AuthService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)
        self.reset_repo = PasswordResetRepository(db)
        self.verification_repo = EmailVerificationRepository(db)

    # --- Registration / login / refresh ---

    def register(self, data: UserRegisterRequest) -> tuple[User, VerificationTokenIssued]:
        """Crea un nuovo utente con email_verified=False e genera contestualmente
        il primo token di verifica. Ritorna (user, token_in_clear): la route
        si occupa di mandare l'email col link.
        """
        existing = self.user_repo.find_by_email(data.email)
        if existing:
            raise EmailAlreadyExistsException()

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            marketing_consent=data.marketing_consent,
            email_verified=False,
        )
        user = self.user_repo.create(user)
        issued = self._issue_verification_token(user)
        return user, issued

    def login(self, data: UserLoginRequest) -> TokenResponse:
        user = self.user_repo.find_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise InvalidCredentialsException()

        # Blocca il login se l'utente non ha ancora verificato l'email.
        # Status 403 con detail dedicato così il frontend può mostrare
        # il bottone "reinvia email di verifica".
        if not user.email_verified:
            raise EmailNotVerifiedException()

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

    # --- Email verification ---

    def _issue_verification_token(self, user: User) -> VerificationTokenIssued:
        """Genera un nuovo token di verifica, invalidando i precedenti.
        Ritorna sempre il token IN CHIARO (sul DB c'è solo l'hash).
        Helper privato usato sia da register che da resend.
        """
        self.verification_repo.invalidate_active_for_user(user.id)
        token = secrets.token_urlsafe(VERIFICATION_TOKEN_BYTES)
        record = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_password(token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=VERIFICATION_TOKEN_EXPIRY_HOURS),
        )
        self.verification_repo.create(record)
        return VerificationTokenIssued(user=user, token=token)

    def verify_email(self, token: str) -> User:
        """Verifica un token email. Solleva InvalidVerificationTokenException
        se il token è scaduto, già usato, o non corrisponde a nessun utente.
        Se valido, marca user.email_verified=True e brucia il token.
        """
        # Il token è random URL-safe — dobbiamo confrontare per hash contro
        # TUTTI i token attivi. Per scalare, l'ideale sarebbe usare un id
        # prefissato nel token; per ora il volume è basso, scanniamo gli attivi.
        from sqlalchemy import and_
        candidates = (
            self.verification_repo.db.query(EmailVerificationToken)
            .filter(
                and_(
                    EmailVerificationToken.used_at.is_(None),
                    EmailVerificationToken.expires_at > datetime.now(timezone.utc),
                )
            )
            .all()
        )

        matching: EmailVerificationToken | None = None
        for cand in candidates:
            if verify_password(token, cand.token_hash):
                matching = cand
                break

        if matching is None:
            raise InvalidVerificationTokenException()

        user = self.user_repo.find_by_id(matching.user_id)
        if user is None:
            raise InvalidVerificationTokenException()

        # Idempotente: se già verificato, ritorna comunque ok senza errori.
        if not user.email_verified:
            self.user_repo.update(user, {"email_verified": True})
        self.verification_repo.mark_used(matching)
        return user

    def resend_verification_email(self, email: str) -> VerificationTokenIssued | None:
        """Genera un nuovo token di verifica per email. Ritorna None se
        l'utente non esiste o è già verificato (la route risponde 200 in
        entrambi i casi per non rivelare la lista email registrate).
        Solleva VerificationRateLimitException se l'ultima richiesta è
        più recente di VERIFICATION_RESEND_COOLDOWN_SECONDS.
        """
        user = self.user_repo.find_by_email(email)
        if user is None or user.email_verified:
            return None

        # Rate limit basato sul created_at dell'ultimo token (qualsiasi stato).
        latest = self.verification_repo.find_latest_by_user(user.id)
        if latest is not None:
            created_at = latest.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - created_at).total_seconds()
            if elapsed < VERIFICATION_RESEND_COOLDOWN_SECONDS:
                raise VerificationRateLimitException(
                    retry_after_seconds=int(VERIFICATION_RESEND_COOLDOWN_SECONDS - elapsed)
                )

        return self._issue_verification_token(user)
