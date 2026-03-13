from sqlalchemy.orm import Session
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdateRequest
from app.utils.exceptions import NotFoundException


class UserService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

    def get_profile(self, user_id: str) -> User:
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise NotFoundException("User")
        return user

    def update_profile(self, user_id: str, data: UserUpdateRequest) -> User:
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise NotFoundException("User")
        return self.user_repo.update(user, data.model_dump(exclude_unset=True))

    def delete_account(self, user_id: str) -> None:
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise NotFoundException("User")
        self.user_repo.delete(user)
