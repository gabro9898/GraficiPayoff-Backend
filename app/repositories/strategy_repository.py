# ============================================================
# FILE AGGIORNATO — sostituisce il file esistente
# Percorso: app/repositories/strategy_repository.py
# ============================================================

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.models.strategy import Strategy


class StrategyRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, strategy_id: str) -> Strategy | None:
        return self.db.query(Strategy).filter(Strategy.id == strategy_id).first()

    def find_by_id_with_trades(self, strategy_id: str) -> Strategy | None:
        return (
            self.db.query(Strategy)
            .options(joinedload(Strategy.trades))
            .filter(Strategy.id == strategy_id)
            .first()
        )

    def find_all_by_user_id(self, user_id: str) -> list[Strategy]:
        return (
            self.db.query(Strategy)
            .filter(Strategy.user_id == user_id)
            .order_by(Strategy.created_at.desc())
            .all()
        )

    def find_all_by_account_id(self, account_id: str) -> list[Strategy]:
        return (
            self.db.query(Strategy)
            .filter(Strategy.account_id == account_id)
            .order_by(Strategy.number.asc())
            .all()
        )

    def get_next_number(self, user_id: str) -> int:
        """Prossimo numero progressivo per utente (001, 002, ...)."""
        result = (
            self.db.query(func.max(Strategy.number))
            .filter(Strategy.user_id == user_id)
            .scalar()
        )
        return (result or 0) + 1

    def create(self, strategy: Strategy) -> Strategy:
        self.db.add(strategy)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def update(self, strategy: Strategy, data: dict) -> Strategy:
        for key, value in data.items():
            if value is not None:
                setattr(strategy, key, value)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def delete(self, strategy: Strategy) -> None:
        self.db.delete(strategy)
        self.db.commit()