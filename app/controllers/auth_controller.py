from sqlalchemy.orm import Session
from app.services.auth_service import AuthService
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

    def register(self, data: UserRegisterRequest) -> UserResponse:
        user = self.auth_service.register(data)
        return UserResponse.model_validate(user)

    def login(self, data: UserLoginRequest) -> TokenResponse:
        return self.auth_service.login(data)

    def refresh_token(self, data: RefreshTokenRequest) -> TokenResponse:
        return self.auth_service.refresh_token(data.refresh_token)
