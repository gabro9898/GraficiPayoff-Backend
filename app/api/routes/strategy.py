# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/api/routes/strategy.py
# Aggiunto: PATCH /{id}/legs (update legs), POST /{id}/close-leg
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.strategy_controller import StrategyController
from app.schemas.strategy import (
    StrategyCreateRequest, StrategyUpdateRequest,
    StrategyAddLegsRequest, StrategyCloseRequest, StrategySettleRequest,
    StrategyUpdateLegsRequest, StrategyCloseLegRequest,
    StrategyResponse, StrategyWithTradesResponse,
)

router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.get("/", response_model=list[StrategyResponse])
def get_all_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_all(current_user)


@router.get("/open-expired", response_model=list[StrategyWithTradesResponse])
def get_open_expired_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_open_expired(current_user)


@router.get("/account/{account_id}", response_model=list[StrategyResponse])
def get_strategies_by_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_all_by_account(account_id, current_user)


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_by_id(strategy_id, current_user)


@router.get("/{strategy_id}/details", response_model=StrategyWithTradesResponse)
def get_strategy_with_trades(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_with_trades(strategy_id, current_user)


@router.post("/", response_model=StrategyWithTradesResponse, status_code=201)
def create_strategy(
    data: StrategyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.create(current_user, data)


@router.post("/{strategy_id}/legs", response_model=StrategyWithTradesResponse)
def add_legs_to_strategy(
    strategy_id: str,
    data: StrategyAddLegsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.add_legs(strategy_id, current_user, data)


# ★ Feature 1: aggiornare legs esistenti (attivare legs spente, aggiornare premium)
@router.patch("/{strategy_id}/legs", response_model=StrategyWithTradesResponse)
def update_legs_in_strategy(
    strategy_id: str,
    data: StrategyUpdateLegsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.update_legs(strategy_id, current_user, data)


# ★ Feature 2: chiudere una singola leg (adjustment con realized PnL)
@router.post("/{strategy_id}/close-leg", response_model=StrategyWithTradesResponse)
def close_leg_in_strategy(
    strategy_id: str,
    data: StrategyCloseLegRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.close_leg(strategy_id, current_user, data)


@router.post("/{strategy_id}/close", response_model=StrategyResponse)
def close_strategy(
    strategy_id: str,
    data: StrategyCloseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.close(strategy_id, current_user, data)


@router.post("/{strategy_id}/settle", response_model=StrategyResponse)
def settle_strategy(
    strategy_id: str,
    data: StrategySettleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.settle(strategy_id, current_user, data)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(
    strategy_id: str,
    data: StrategyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.update(strategy_id, current_user, data)


@router.delete("/{strategy_id}")
def delete_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.delete(strategy_id, current_user)