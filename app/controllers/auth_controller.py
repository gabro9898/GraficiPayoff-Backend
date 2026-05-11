from sqlalchemy.orm import Session
from app.services.auth_service import (
    AuthService,
    PasswordResetIssued,
    VerificationTokenIssued,
)
from app.models.user import User
from app.schemas.user import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
    RefreshTokenRequest,
)


class AuthController:
    def __init__(self, db: Session):
        self.auth_service = AuthService(db)

    def register(self, data: UserRegisterRequest) -> tuple[User, VerificationTokenIssued]:
        """Ritorna (user, verification) — la route si occupa di mandare l'email."""
        return self.auth_service.register(data)

    def login(self, data: UserLoginRequest) -> TokenResponse:
        return self.auth_service.login(data)

    def refresh_token(self, data: RefreshTokenRequest) -> TokenResponse:
        return self.auth_service.refresh_token(data.refresh_token)

    def issue_password_reset_code(self, email: str) -> PasswordResetIssued:
        return self.auth_service.issue_password_reset_code(email)

    def reset_password(self, email: str, code: str, new_password: str) -> None:
        self.auth_service.reset_password(email, code, new_password)

    def verify_email(self, token: str) -> User:
        return self.auth_service.verify_email(token)

    def resend_verification_email(self, email: str) -> VerificationTokenIssued | None:
        return self.auth_service.resend_verification_email(email)
