from sqlalchemy.orm import Session
from app.models.user import User
from app.services.trade_service import TradeService
from app.schemas.trade import (
    TradeCreateRequest,
    TradeUpdateRequest,
    TradeCloseRequest,
    TradeResponse,
)


class TradeController:
    def __init__(self, db: Session):
        self.trade_service = TradeService(db)

    def get_all_by_strategy(
        self, strategy_id: str, current_user: User
    ) -> list[TradeResponse]:
        trades = self.trade_service.get_all_by_strategy(strategy_id, current_user.id)
        return [TradeResponse.model_validate(t) for t in trades]

    def get_by_id(self, trade_id: str, current_user: User) -> TradeResponse:
        trade = self.trade_service.get_by_id(trade_id, current_user.id)
        return TradeResponse.model_validate(trade)

    def create(
        self, strategy_id: str, current_user: User, data: TradeCreateRequest
    ) -> TradeResponse:
        trade = self.trade_service.create(strategy_id, current_user.id, data)
        return TradeResponse.model_validate(trade)

    def update(
        self, trade_id: str, current_user: User, data: TradeUpdateRequest
    ) -> TradeResponse:
        trade = self.trade_service.update(trade_id, current_user.id, data)
        return TradeResponse.model_validate(trade)

    def close(
        self, trade_id: str, current_user: User, data: TradeCloseRequest
    ) -> TradeResponse:
        trade = self.trade_service.close(trade_id, current_user.id, data)
        return TradeResponse.model_validate(trade)

    def delete(self, trade_id: str, current_user: User) -> dict:
        self.trade_service.delete(trade_id, current_user.id)
        return {"message": "Trade deleted successfully"}
