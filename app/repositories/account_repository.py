# ============================================================
# NUOVO FILE
# Percorso: app/repositories/account_repository.py
# ============================================================

from sqlalchemy.orm import Session, joinedload
from app.models.account import Account


class AccountRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, account_id: str) -> Account | None:
        return self.db.query(Account).filter(Account.id == account_id).first()

    def find_by_id_with_strategies(self, account_id: str) -> Account | None:
        return (
            self.db.query(Account)
            .options(joinedload(Account.strategies))
            .filter(Account.id == account_id)
            .first()
        )

    def find_all_by_user_id(self, user_id: str) -> list[Account]:
        return (
            self.db.query(Account)
            .filter(Account.user_id == user_id)
            .order_by(Account.created_at.asc())
            .all()
        )

    def create(self, account: Account) -> Account:
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def update(self, account: Account, data: dict) -> Account:
        for key, value in data.items():
            if value is not None:
                setattr(account, key, value)
        self.db.commit()
        self.db.refresh(account)
        return account

    def delete(self, account: Account) -> None:
        self.db.delete(account)
        self.db.commit()