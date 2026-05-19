# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/controllers/strategy_controller.py
# v4: + MODEL feature: get_all_models, create_model,
#     replace_model_legs, fill_model
# v3: + settle_expired_legs + get_strategies_with_expired_legs
#     (per il nuovo flow di auto-settle parziale leg-by-leg)
# ============================================================

from sqlalchemy.orm import Session
from app.models.user import User
from app.services.strategy_service import StrategyService
from app.schemas.strategy import (
    StrategyCreateRequest, StrategyUpdateRequest,
    StrategyAddLegsRequest, StrategyCloseRequest, StrategySettleRequest,
    StrategySettleExpiredLegsRequest,
    StrategyUpdateLegsRequest, StrategyCloseLegRequest,
    StrategyCreateModelRequest, StrategyReplaceModelLegsRequest,
    StrategyFillModelRequest,
    StrategyCreateRequest2, StrategySaveLegsRequest, StrategyFillPendingLegRequest,
    StrategyResponse, StrategyWithTradesResponse,
)
from app.schemas.underlying_position import (
    UnderlyingPositionCreateRequest, UnderlyingPositionCloseRequest,
)


class StrategyController:
    def __init__(self, db: Session):
        self.strategy_service = StrategyService(db)

    def get_all(self, current_user: User) -> list[StrategyResponse]:
        strategies = self.strategy_service.get_all_by_user(current_user.id)
        return [StrategyResponse.model_validate(s) for s in strategies]

    # v2: tutte le strategie con trades per Portfolio
    def get_all_with_trades(self, current_user: User) -> list[StrategyWithTradesResponse]:
        strategies = self.strategy_service.get_all_by_user_with_trades(current_user.id)
        return [StrategyWithTradesResponse.model_validate(s) for s in strategies]

    def get_all_by_account(self, account_id: str, current_user: User) -> list[StrategyResponse]:
        strategies = self.strategy_service.get_all_by_account(account_id, current_user.id)
        return [StrategyResponse.model_validate(s) for s in strategies]

    def get_open_expired(self, current_user: User) -> list[StrategyWithTradesResponse]:
        strategies = self.strategy_service.get_open_expired(current_user.id)
        return [StrategyWithTradesResponse.model_validate(s) for s in strategies]

    # ★ v3: nuovo lookup per auto-settle parziale
    def get_strategies_with_expired_legs(self, current_user: User) -> list[StrategyWithTradesResponse]:
        strategies = self.strategy_service.get_strategies_with_expired_legs(current_user.id)
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

    def update_legs(self, strategy_id: str, current_user: User, data: StrategyUpdateLegsRequest) -> StrategyWithTradesResponse:
        self.strategy_service.update_legs(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def close_leg(self, strategy_id: str, current_user: User, data: StrategyCloseLegRequest) -> StrategyWithTradesResponse:
        self.strategy_service.close_leg(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def add_underlying(self, strategy_id: str, current_user: User, data: UnderlyingPositionCreateRequest) -> StrategyWithTradesResponse:
        self.strategy_service.add_underlying(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def close_underlying(self, strategy_id: str, current_user: User, data: UnderlyingPositionCloseRequest) -> StrategyWithTradesResponse:
        self.strategy_service.close_underlying(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def close(self, strategy_id: str, current_user: User, data: StrategyCloseRequest) -> StrategyResponse:
        strategy = self.strategy_service.close(strategy_id, current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    def settle(self, strategy_id: str, current_user: User, data: StrategySettleRequest) -> StrategyResponse:
        strategy = self.strategy_service.settle(strategy_id, current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    # ★ v3: settle parziale leg-by-leg.
    # Ritorna StrategyWithTradesResponse perché il frontend ha bisogno
    # dello stato aggiornato dei singoli trade (close_premium, settlement_price).
    def settle_expired_legs(
        self, strategy_id: str, current_user: User,
        data: StrategySettleExpiredLegsRequest,
    ) -> StrategyWithTradesResponse:
        self.strategy_service.settle_expired_legs(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def update(self, strategy_id: str, current_user: User, data: StrategyUpdateRequest) -> StrategyResponse:
        strategy = self.strategy_service.update(strategy_id, current_user.id, data)
        return StrategyResponse.model_validate(strategy)

    def delete(self, strategy_id: str, current_user: User) -> dict:
        self.strategy_service.delete(strategy_id, current_user.id)
        return {"message": "Strategy deleted successfully"}

    # ═══════════════════════════════════════════════════════════
    # ★ v4: MODEL feature
    # ═══════════════════════════════════════════════════════════

    def get_all_models(self, current_user: User) -> list[StrategyWithTradesResponse]:
        models = self.strategy_service.get_all_models_by_user(current_user.id)
        return [StrategyWithTradesResponse.model_validate(s) for s in models]

    def create_model(self, current_user: User, data: StrategyCreateModelRequest) -> StrategyWithTradesResponse:
        strategy = self.strategy_service.create_model(current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy.id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def replace_model_legs(
        self, strategy_id: str, current_user: User,
        data: StrategyReplaceModelLegsRequest,
    ) -> dict:
        _, assigned_ids = self.strategy_service.replace_model_legs(
            strategy_id, current_user.id, data,
        )
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return {
            "strategy": StrategyWithTradesResponse.model_validate(strategy),
            "assigned_trade_ids": assigned_ids,
        }

    def fill_model(
        self, strategy_id: str, current_user: User,
        data: StrategyFillModelRequest,
    ) -> StrategyWithTradesResponse:
        self.strategy_service.fill_model(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    # ═══════════════════════════════════════════════════════════
    # ★ v15: PENDING LEGS — vivono nella stessa Strategy con is_pending=True
    # ═══════════════════════════════════════════════════════════

    def create_with_pending(
        self, current_user: User, data: StrategyCreateRequest2,
    ) -> StrategyWithTradesResponse:
        strategy = self.strategy_service.create_with_pending(current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy.id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def save_legs(
        self, strategy_id: str, current_user: User, data: StrategySaveLegsRequest,
    ) -> StrategyWithTradesResponse:
        self.strategy_service.save_legs(strategy_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def replace_pending_legs(
        self, strategy_id: str, current_user: User, data,
    ) -> dict:
        _, assigned_ids = self.strategy_service.replace_pending_legs(
            strategy_id, current_user.id, data,
        )
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return {
            "strategy": StrategyWithTradesResponse.model_validate(strategy),
            "assigned_trade_ids": assigned_ids,
        }

    def fill_pending_leg(
        self, strategy_id: str, leg_id: str, current_user: User,
        data: StrategyFillPendingLegRequest,
    ) -> StrategyWithTradesResponse:
        self.strategy_service.fill_pending_leg(strategy_id, leg_id, current_user.id, data)
        strategy = self.strategy_service.get_by_id_with_trades(strategy_id, current_user.id)
        return StrategyWithTradesResponse.model_validate(strategy)

    def delete_pending_leg(
        self, strategy_id: str, leg_id: str, current_user: User,
    ) -> dict:
        self.strategy_service.delete_pending_leg(strategy_id, leg_id, current_user.id)
        return {"message": "Pending leg deleted"}