# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/controllers/strategy_controller.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.user import User
from app.services.strategy_service import StrategyService
from app.schemas.strategy import (
    StrategyCreateRequest, StrategyUpdateRequest,
    StrategyAddLegsRequest, StrategyCloseRequest, StrategySettleRequest,
    StrategyResponse, StrategyWithTradesResponse,
)


class StrategyController:
    def __init__(self, db: Session):
        self.strategy_service = StrategyService(db)

    def get_all(self, current_user: User) -> list[StrategyResponse]:
        strategies = self.strategy_service.get_all_by_user(current_user.id)
        return [StrategyResponse.model_validate(s) for s in strategies]

    def get_all_by_account(self, account_id: str, current_user: User) -> list[StrategyResponse]:
        strategies = self.strategy_service.get_all_by_account(account_id, current_user.id)
        return [StrategyResponse.model_validate(s) for s in strategies]

    def get_open_expired(self, current_user: User) -> list[StrategyWithTradesResponse]:
        strategies = self.strategy_service.get_open_expired(current_user.id)
        return [StrategyWithTradesResponse.model_validate(s) for s in strategies]

    def get_by_id(self, strategy_id: str, current_user: User) -> StrategyResponse:
        strategy = self.strategy_service.get_by_id(strategy_id, current_user.id)
        return StrategyResponse.model_validate(strategy)

    def get_with_trades(self, strategy_id: str, current_user: User) -> StrategyWithTradesResponse:
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def create(self, current_user: User, data: StrategyCreateRequest) -> StrategyWithTradesResponse:
        strategy = self.strategy_service.create(current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy.id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def add_legs(self, strategy_id: str, current_user: User, data: StrategyAddLegsRequest) -> StrategyWithTradesResponse:
        self.strategy_service.add_legs(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def close(self, strategy_id: str, current_user: User, data: StrategyCloseRequest) -> StrategyResponse:
        strategy = self.strategy_service.close(strategy_id, current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    def settle(self, strategy_id: str, current_user: User, data: StrategySettleRequest) -> StrategyResponse:
        strategy = self.strategy_service.settle(strategy_id, current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    def update(self, strategy_id: str, current_user: User, data: StrategyUpdateRequest) -> StrategyResponse:
        strategy = self.strategy_service.update(strategy_id, current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    def delete(self, strategy_id: str, current_user: User) -> dict:
        self.strategy_service.delete(strategy_id, current_user.id)
        return {"message": "Strategy deleted successfully"}