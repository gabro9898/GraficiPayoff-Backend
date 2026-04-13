from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.trade import Trade, TradeStatus, Direction
from app.repositories.trade_repository import TradeRepository
from app.repositories.strategy_repository import StrategyRepository
from app.schemas.trade import TradeCreateRequest, TradeUpdateRequest, TradeCloseRequest
from app.utils.exceptions import NotFoundException, ForbiddenException


class TradeService:
    def __init__(self, db: Session):
        self.trade_repo = TradeRepository(db)
        self.strategy_repo = StrategyRepository(db)

    def _verify_strategy_ownership(self, strategy_id: str, user_id: str) -> None:
        strategy = self.strategy_repo.find_by_id(strategy_id)
        if not strategy:
            raise NotFoundException("Strategy")
        if strategy.user_id != user_id:
            raise ForbiddenException()

    def _verify_trade_ownership(self, trade_id: str, user_id: str) -> Trade:
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundException("Trade")
        self._verify_strategy_ownership(trade.strategy_id, user_id)
        return trade

    def get_all_by_strategy(self, strategy_id: str, user_id: str) -> list[Trade]:
        self._verify_strategy_ownership(strategy_id, user_id)
        return self.trade_repo.find_all_by_strategy_id(strategy_id)

    def get_by_id(self, trade_id: str, user_id: str) -> Trade:
        return self._verify_trade_ownership(trade_id, user_id)

    def create(self, strategy_id: str, user_id: str, data: TradeCreateRequest) -> Trade:
        self._verify_strategy_ownership(strategy_id, user_id)
        trade = Trade(
            strategy_id=strategy_id,
            **data.model_dump(),
        )
        return self.trade_repo.create(trade)

    def update(self, trade_id: str, user_id: str, data: TradeUpdateRequest) -> Trade:
        trade = self._verify_trade_ownership(trade_id, user_id)
        was_open = trade.status == TradeStatus.OPEN
        old_close_premium = trade.close_premium
        trade = self.trade_repo.update(trade, data.model_dump(exclude_unset=True))
        if (trade.close_premium is not None and was_open and trade.status == TradeStatus.CLOSED) or (trade.close_premium != old_close_premium and trade.close_premium is not None):
            self._recalculate_strategy_pnl(trade.strategy_id)
        return trade

    def _recalculate_strategy_pnl(self, strategy_id: str) -> None:
        strategy = self.strategy_repo.find_by_id_with_trades(strategy_id)
        if not strategy:
            return
        total_pnl = 0.0
        for t in strategy.trades:
            if t.status == TradeStatus.CLOSED and t.close_premium is not None:
                multiplier = 1 if t.direction == Direction.BUY else -1
                total_pnl += (t.close_premium - t.premium) * multiplier * t.quantity * 100
        for p in strategy.underlying_positions:
            if p.status == 'CLOSED' and p.close_price is not None:
                mult = 1 if p.direction == 'BUY' else -1
                total_pnl += (p.close_price - p.entry_price) * mult * p.quantity * p.multiplier
        strategy.realized_pnl = total_pnl
        self.trade_repo.db.commit()

    def close(self, trade_id: str, user_id: str, data: TradeCloseRequest) -> Trade:
        trade = self._verify_trade_ownership(trade_id, user_id)
        update_data = {
            "status": TradeStatus.CLOSED,
            "close_premium": data.close_premium,
            "close_date": datetime.now(timezone.utc),
        }
        return self.trade_repo.update(trade, update_data)

    def delete(self, trade_id: str, user_id: str) -> None:
        trade = self._verify_trade_ownership(trade_id, user_id)
        self.trade_repo.delete(trade)