# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/strategy_service.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.repositories.strategy_repository import StrategyRepository
from app.repositories.account_repository import AccountRepository
from app.schemas.strategy import StrategyCreateRequest, StrategyUpdateRequest, StrategyAddLegsRequest
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
        return self.strategy_repo.find_all_by_account_id(account_id)

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

    def create(self, user_id: str, data: StrategyCreateRequest) -> Strategy:
        """
        Salva una nuova strategia con tutte le legs in una transazione.
        """
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
        )
        self.db.add(strategy)
        self.db.flush()

        for leg in data.legs:
            trade = Trade(
                strategy_id=strategy.id,
                ticker=data.ticker,
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
            )
            self.db.add(trade)

        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def add_legs(self, strategy_id: str, user_id: str, data: StrategyAddLegsRequest) -> Strategy:
        """
        Aggiunge nuove legs (correzioni/aggiustamenti) a una strategia esistente.
        Ogni correzione viene salvata come frozen=True con il proprio fill_price.
        """
        strategy = self.get_by_id(strategy_id, user_id)

        for leg in data.legs:
            trade = Trade(
                strategy_id=strategy.id,
                ticker=strategy.ticker,
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
            )
            self.db.add(trade)

        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def update(self, strategy_id: str, user_id: str, data: StrategyUpdateRequest) -> Strategy:
        strategy = self.get_by_id(strategy_id, user_id)
        return self.strategy_repo.update(strategy, data.model_dump(exclude_unset=True))

    def delete(self, strategy_id: str, user_id: str) -> None:
        strategy = self.get_by_id(strategy_id, user_id)
        self.strategy_repo.delete(strategy)