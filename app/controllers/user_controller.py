from sqlalchemy.orm import Session
from app.models.user import User
from app.services.user_service import UserService
from app.schemas.user import UserUpdateRequest, UserResponse


class UserController:
    def __init__(self, db: Session):
        self.user_service = UserService(db)

    def get_profile(self, current_user: User) -> UserResponse:
        user = self.user_service.get_profile(current_user.id)
        return UserResponse.model_validate(user)

    def update_profile(self, current_user: User, data: UserUpdateRequest) -> UserResponse:
        user = self.user_service.update_profile(current_user.id, data)
        return UserResponse.model_validate(user)

    def delete_account(self, current_user: User) -> dict:
        self.user_service.delete_account(current_user.id)
        return {"message": "Account deleted successfully"}
