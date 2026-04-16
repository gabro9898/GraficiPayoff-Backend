# ============================================================
# Percorso: app/services/account_service.py
# v2: + commission fields on create
# ============================================================

from sqlalchemy.orm import Session
from app.models.account import Account
from app.repositories.account_repository import AccountRepository
from app.schemas.account import AccountCreateRequest, AccountUpdateRequest
from app.utils.exceptions import NotFoundException, ForbiddenException


class AccountService:
    def __init__(self, db: Session):
        self.account_repo = AccountRepository(db)

    def get_all_by_user(self, user_id: str) -> list[Account]:
        return self.account_repo.find_all_by_user_id(user_id)

    def get_by_id(self, account_id: str, user_id: str) -> Account:
        account = self.account_repo.find_by_id(account_id)
        if not account:
            raise NotFoundException("Account")
        if account.user_id != user_id:
            raise ForbiddenException()
        return account

    def get_by_id_with_strategies(self, account_id: str, user_id: str) -> Account:
        account = self.account_repo.find_by_id_with_strategies(account_id)
        if not account:
            raise NotFoundException("Account")
        if account.user_id != user_id:
            raise ForbiddenException()
        return account

    def create(self, user_id: str, data: AccountCreateRequest) -> Account:
        account = Account(
            user_id=user_id,
            name=data.name,
            description=data.description,
            commission_option_per_contract=data.commission_option_per_contract,
            commission_option_close_per_contract=data.commission_option_close_per_contract,
            commission_stock_type=data.commission_stock_type,
            commission_stock_value=data.commission_stock_value,
            commission_stock_close_value=data.commission_stock_close_value,
        )
        return self.account_repo.create(account)

    def update(self, account_id: str, user_id: str, data: AccountUpdateRequest) -> Account:
        account = self.get_by_id(account_id, user_id)
        return self.account_repo.update(account, data.model_dump(exclude_unset=True))

    def delete(self, account_id: str, user_id: str) -> None:
        account = self.get_by_id(account_id, user_id)
        self.account_repo.delete(account)