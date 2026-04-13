# ============================================================
# Percorso: app/services/strategy_service.py
# v5: + trading_class on trade creation
# ============================================================

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.strategy import Strategy
from app.models.trade import Trade, TradeStatus, OptionType, Direction
from app.models.underlying_position import UnderlyingPosition, UPDirection, UPStatus
from app.repositories.strategy_repository import StrategyRepository
from app.repositories.account_repository import AccountRepository
from app.repositories.trade_repository import TradeRepository
from app.schemas.strategy import (
    StrategyCreateRequest, StrategyUpdateRequest,
    StrategyAddLegsRequest, StrategyCloseRequest, StrategySettleRequest,
    StrategyUpdateLegsRequest, StrategyCloseLegRequest,
)
from app.schemas.underlying_position import (
    UnderlyingPositionCreateRequest, UnderlyingPositionCloseRequest,
)
from app.utils.exceptions import NotFoundException, ForbiddenException


class StrategyService:
    def __init__(self, db: Session):
        self.db = db
        self.strategy_repo = StrategyRepository(db)
        self.account_repo = AccountRepository(db)
        self.trade_repo = TradeRepository(db)

    def _verify_account_ownership(self, account_id: str, user_id: str) -> None:
        account = self.account_repo.find_by_id(account_id)
        if not account:
            raise NotFoundException("Account")
        if account.user_id != user_id:
            raise ForbiddenException()

    def _recompute_earliest_expiry(self, strategy: Strategy) -> None:
        open_expiries = [
            t.expiry for t in strategy.trades
            if t.status != TradeStatus.CLOSED and t.expiry is not None
        ]
        strategy.earliest_expiry = min(open_expiries) if open_expiries else None

    def get_all_by_user(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_all_by_user_id(user_id)

    def get_all_by_user_with_trades(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_all_by_user_with_trades(user_id)

    def get_all_by_account(self, account_id: str, user_id: str) -> list[Strategy]:
        self._verify_account_ownership(account_id, user_id)
        return self.strategy_repo.find_all_by_account_id(
            account_id, status="OPEN", exclude_expired=True
        )

    def get_by_id(self, strategy_id: str, user_id: str) -> Strategy:
        strategy = self.strategy_repo.find_by_id(strategy_id)
        if not strategy:
            raise NotFoundException("Strategy")
        if strategy.user_id != user_id:
            raise ForbiddenException()
        return strategy

    def get_by_id_with_trades(self, strategy_id: str, user_id: str) -> Strategy:
        strategy = self.strategy_repo.find_by_id_with_trades(strategy_id)
        if not strategy:
            raise NotFoundException("Strategy")
        if strategy.user_id != user_id:
            raise ForbiddenException()
        return strategy

    def get_open_expired(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_open_expired_by_user(user_id)

    # ★ v5: include trading_class
    def _create_trade_from_leg(self, strategy_id: str, ticker: str, leg) -> Trade:
        return Trade(
            strategy_id=strategy_id,
            ticker=ticker,
            option_type=leg.option_type,
            direction=leg.direction,
            strike=leg.strike,
            premium=leg.premium,
            quantity=leg.quantity,
            expiry=leg.expiry,
            enabled=leg.enabled,
            frozen=True,
            trading_class=getattr(leg, 'trading_class', None),
            delta=leg.delta,
            gamma=leg.gamma,
            theta=leg.theta,
            vega=leg.vega,
            implied_volatility=leg.implied_volatility,
        )

    def create(self, user_id: str, data: StrategyCreateRequest) -> Strategy:
        self._verify_account_ownership(data.account_id, user_id)
        next_number = self.strategy_repo.get_next_number(user_id)
        earliest = None
        if data.legs:
            earliest = min(leg.expiry for leg in data.legs)
        strategy = Strategy(
            user_id=user_id, account_id=data.account_id, number=next_number,
            name=data.name, description=data.description, ticker=data.ticker,
            fill_price=data.fill_price, contract_multiplier=data.contract_multiplier,
            earliest_expiry=earliest, status="OPEN", realized_pnl=0.0,
        )
        self.db.add(strategy)
        self.db.flush()
        for leg in data.legs:
            trade = self._create_trade_from_leg(strategy.id, data.ticker, leg)
            self.db.add(trade)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def add_legs(self, strategy_id: str, user_id: str, data: StrategyAddLegsRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        for leg in data.legs:
            trade = self._create_trade_from_leg(strategy.id, strategy.ticker, leg)
            self.db.add(trade)
        self.db.flush()
        new_earliest = min(leg.expiry for leg in data.legs)
        if strategy.earliest_expiry is None or new_earliest < strategy.earliest_expiry:
            strategy.earliest_expiry = new_earliest
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def update_legs(self, strategy_id: str, user_id: str, data: StrategyUpdateLegsRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        trade_map = {t.id: t for t in strategy.trades}
        for leg_update in data.legs:
            trade = trade_map.get(leg_update.trade_id)
            if not trade:
                raise NotFoundException(f"Trade {leg_update.trade_id}")
            if leg_update.enabled is not None: trade.enabled = leg_update.enabled
            if leg_update.premium is not None: trade.premium = leg_update.premium
            if leg_update.implied_volatility is not None: trade.implied_volatility = leg_update.implied_volatility
            if leg_update.delta is not None: trade.delta = leg_update.delta
            if leg_update.gamma is not None: trade.gamma = leg_update.gamma
            if leg_update.theta is not None: trade.theta = leg_update.theta
            if leg_update.vega is not None: trade.vega = leg_update.vega
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def close_leg(self, strategy_id: str, user_id: str, data: StrategyCloseLegRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)
        trade = None
        for t in strategy.trades:
            if t.id == data.trade_id: trade = t; break
        if not trade: raise NotFoundException(f"Trade {data.trade_id}")
        if trade.status == TradeStatus.CLOSED: raise ForbiddenException()
        multiplier = 1 if trade.direction == Direction.BUY else -1
        leg_pnl = (data.close_premium - trade.premium) * multiplier * trade.quantity * 100
        trade.status = TradeStatus.CLOSED
        trade.close_premium = data.close_premium
        trade.close_date = now
        strategy.realized_pnl = (strategy.realized_pnl or 0.0) + leg_pnl
        self._recompute_earliest_expiry(strategy)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def add_underlying(self, strategy_id: str, user_id: str, data: UnderlyingPositionCreateRequest) -> Strategy:
        strategy = self.get_by_id(strategy_id, user_id)
        position = UnderlyingPosition(
            strategy_id=strategy.id, ticker=strategy.ticker,
            direction=data.direction, quantity=data.quantity,
            entry_price=data.entry_price, multiplier=data.multiplier, status=UPStatus.OPEN,
        )
        self.db.add(position)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def close_underlying(self, strategy_id: str, user_id: str, data: UnderlyingPositionCloseRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)
        position = None
        for p in strategy.underlying_positions:
            if p.id == data.position_id: position = p; break
        if not position: raise NotFoundException(f"UnderlyingPosition {data.position_id}")
        if position.status == UPStatus.CLOSED: raise ForbiddenException()
        mult = 1 if position.direction == UPDirection.BUY else -1
        pos_pnl = (data.close_price - position.entry_price) * mult * position.quantity * position.multiplier
        position.status = UPStatus.CLOSED
        position.close_price = data.close_price
        position.close_date = now
        strategy.realized_pnl = (strategy.realized_pnl or 0.0) + pos_pnl
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def close(self, strategy_id: str, user_id: str, data: StrategyCloseRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)
        strategy.status = "CLOSED"
        for trade in strategy.trades:
            if trade.status == TradeStatus.OPEN:
                trade.status = TradeStatus.CLOSED
                trade.close_premium = data.close_premium
                trade.close_date = now
        for pos in strategy.underlying_positions:
            if pos.status == UPStatus.OPEN:
                close_price = data.underlying_close_price if data.underlying_close_price is not None else 0.0
                mult = 1 if pos.direction == UPDirection.BUY else -1
                pos_pnl = (close_price - pos.entry_price) * mult * pos.quantity * pos.multiplier
                pos.status = UPStatus.CLOSED
                pos.close_price = close_price
                pos.close_date = now
                strategy.realized_pnl = (strategy.realized_pnl or 0.0) + pos_pnl
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def settle(self, strategy_id: str, user_id: str, data: StrategySettleRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)
        sp = data.settlement_price
        strategy.status = "CLOSED"
        strategy.settlement_price = sp
        for trade in strategy.trades:
            if trade.status == TradeStatus.OPEN:
                if trade.option_type == OptionType.CALL: intrinsic = max(0.0, sp - trade.strike)
                else: intrinsic = max(0.0, trade.strike - sp)
                trade.close_premium = intrinsic
                trade.close_date = now
                trade.status = TradeStatus.CLOSED
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def update(self, strategy_id: str, user_id: str, data: StrategyUpdateRequest) -> Strategy:
        strategy = self.get_by_id(strategy_id, user_id)
        return self.strategy_repo.update(strategy, data.model_dump(exclude_unset=True))

    def delete(self, strategy_id: str, user_id: str) -> None:
        strategy = self.get_by_id(strategy_id, user_id)
        self.strategy_repo.delete(strategy)