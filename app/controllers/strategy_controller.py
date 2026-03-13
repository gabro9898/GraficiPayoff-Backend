from sqlalchemy.orm import Session
from app.models.user import User
from app.services.strategy_service import StrategyService
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyUpdateRequest,
    StrategyResponse,
    StrategyWithTradesResponse,
)


class StrategyController:
    def __init__(self, db: Session):
        self.strategy_service = StrategyService(db)

    def get_all(self, current_user: User) -> list[StrategyResponse]:
        strategies = self.strategy_service.get_all_by_user(current_user.id)
        return [StrategyResponse.model_validate(s) for s in strategies]

    def get_by_id(self, strategy_id: str, current_user: User) -> StrategyResponse:
        strategy = self.strategy_service.get_by_id(strategy_id, current_user.id)
        return StrategyResponse.model_validate(strategy)

    def get_with_trades(self, strategy_id: str, current_user: User) -> StrategyWithTradesResponse:
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def create(self, current_user: User, data: StrategyCreateRequest) -> StrategyResponse:
        strategy = self.strategy_service.create(current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    def update(
        self, strategy_id: str, current_user: User, data: StrategyUpdateRequest
    ) -> StrategyResponse:
        strategy = self.strategy_service.update(strategy_id, current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    def delete(self, strategy_id: str, current_user: User) -> dict:
        self.strategy_service.delete(strategy_id, current_user.id)
        return {"message": "Strategy deleted successfully"}
