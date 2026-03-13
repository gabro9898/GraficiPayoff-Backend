from sqlalchemy.orm import Session
from app.models.trade import Trade, TradeStatus


class TradeRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, trade_id: str) -> Trade | None:
        return self.db.query(Trade).filter(Trade.id == trade_id).first()

    def find_all_by_strategy_id(self, strategy_id: str) -> list[Trade]:
        return (
            self.db.query(Trade)
            .filter(Trade.strategy_id == strategy_id)
            .order_by(Trade.open_date.desc())
            .all()
        )

    def find_all_by_user_strategies(self, strategy_ids: list[str]) -> list[Trade]:
        return (
            self.db.query(Trade)
            .filter(Trade.strategy_id.in_(strategy_ids))
            .order_by(Trade.open_date.desc())
            .all()
        )

    def find_open_by_strategy_id(self, strategy_id: str) -> list[Trade]:
        return (
            self.db.query(Trade)
            .filter(Trade.strategy_id == strategy_id, Trade.status == TradeStatus.OPEN)
            .order_by(Trade.open_date.desc())
            .all()
        )

    def create(self, trade: Trade) -> Trade:
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        return trade

    def update(self, trade: Trade, data: dict) -> Trade:
        for key, value in data.items():
            if value is not None:
                setattr(trade, key, value)
        self.db.commit()
        self.db.refresh(trade)
        return trade

    def delete(self, trade: Trade) -> None:
        self.db.delete(trade)
        self.db.commit()
