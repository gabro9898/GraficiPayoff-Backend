# ============================================================
# NUOVO FILE
# Percorso: app/controllers/account_controller.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.user import User
from app.services.account_service import AccountService
from app.schemas.account import (
    AccountCreateRequest,
    AccountUpdateRequest,
    AccountResponse,
    AccountWithStrategiesResponse,
)


class AccountController:
    def __init__(self, db: Session):
        self.account_service = AccountService(db)

    def get_all(self, current_user: User) -> list[AccountResponse]:
        accounts = self.account_service.get_all_by_user(current_user.id)
        return [AccountResponse.model_validate(a) for a in accounts]

    def get_by_id(self, account_id: str, current_user: User) -> AccountResponse:
        account = self.account_service.get_by_id(account_id, current_user.id)
        return AccountResponse.model_validate(account)

    def get_with_strategies(self, account_id: str, current_user: User) -> AccountWithStrategiesResponse:
        account = self.account_service.get_by_id_with_strategies(account_id, current_user.id)
        return AccountWithStrategiesResponse.model_validate(account)

    def create(self, current_user: User, data: AccountCreateRequest) -> AccountResponse:
        account = self.account_service.create(current_user.id, data)
        return AccountResponse.model_validate(account)

    def update(self, account_id: str, current_user: User, data: AccountUpdateRequest) -> AccountResponse:
        account = self.account_service.update(account_id, current_user.id, data)
        return AccountResponse.model_validate(account)

    def delete(self, account_id: str, current_user: User) -> dict:
        self.account_service.delete(account_id, current_user.id)
        return {"message": "Account deleted successfully"}