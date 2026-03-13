from sqlalchemy.orm import Session
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserRegisterRequest, UserLoginRequest, TokenResponse
from app.utils.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.utils.exceptions import (
    InvalidCredentialsException,
    InvalidTokenException,
    EmailAlreadyExistsException,
)


class AuthService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

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
