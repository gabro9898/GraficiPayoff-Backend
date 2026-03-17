# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/strategy_service.py
# Fix: passa implied_volatility quando crea Trade
# ============================================================

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.strategy import Strategy
from app.models.trade import Trade, TradeStatus, OptionType, Direction
from app.repositories.strategy_repository import StrategyRepository
from app.repositories.account_repository import AccountRepository
from app.schemas.strategy import (
    StrategyCreateRequest, StrategyUpdateRequest,
    StrategyAddLegsRequest, StrategyCloseRequest, StrategySettleRequest,
)
from app.utils.exceptions import NotFoundException, ForbiddenException


class StrategyService:
    def __init__(self, db: Session):
        self.db = db
        self.strategy_repo = StrategyRepository(db)
        self.account_repo = AccountRepository(db)

    def _verify_account_ownership(self, account_id: str, user_id: str) -> None:
        account = self.account_repo.find_by_id(account_id)
        if not account:
            raise NotFoundException("Account")
        if account.user_id != user_id:
            raise ForbiddenException()

    def get_all_by_user(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_all_by_user_id(user_id)

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
        """Ritorna strategie OPEN con tutti i trade scaduti — da settlarci."""
        return self.strategy_repo.find_open_expired_by_user(user_id)

    def _create_trade_from_leg(self, strategy_id: str, ticker: str, leg) -> Trade:
        """★ Helper: crea un Trade da un StrategyLegInput, includendo implied_volatility."""
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
            delta=leg.delta,
            gamma=leg.gamma,
            theta=leg.theta,
            vega=leg.vega,
            implied_volatility=leg.implied_volatility,  # ★ FIX
        )

    def create(self, user_id: str, data: StrategyCreateRequest) -> Strategy:
        self._verify_account_ownership(data.account_id, user_id)
        next_number = self.strategy_repo.get_next_number(user_id)

        strategy = Strategy(
            user_id=user_id,
            account_id=data.account_id,
            number=next_number,
            name=data.name,
            description=data.description,
            ticker=data.ticker,
            fill_price=data.fill_price,
            status="OPEN",
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
        strategy = self.get_by_id(strategy_id, user_id)

        for leg in data.legs:
            trade = self._create_trade_from_leg(strategy.id, strategy.ticker, leg)
            self.db.add(trade)

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
                if trade.option_type == OptionType.CALL:
                    intrinsic = max(0.0, sp - trade.strike)
                else:
                    intrinsic = max(0.0, trade.strike - sp)

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