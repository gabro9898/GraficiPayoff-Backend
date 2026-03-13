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
