from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.security import decode_token
from app.utils.exceptions import InvalidTokenException

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: extracts and validates the current user from JWT token."""
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise InvalidTokenException()

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidTokenException()

    user_repo = UserRepository(db)
    user = user_repo.find_by_id(user_id)
    if not user:
        raise InvalidTokenException()

    return user
