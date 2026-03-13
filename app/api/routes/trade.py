from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.trade_controller import TradeController
from app.schemas.trade import (
    TradeCreateRequest,
    TradeUpdateRequest,
    TradeCloseRequest,
    TradeResponse,
)

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.get("/strategy/{strategy_id}", response_model=list[TradeResponse])
def get_trades_by_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = TradeController(db)
    return controller.get_all_by_strategy(strategy_id, current_user)


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(
    trade_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = TradeController(db)
    return controller.get_by_id(trade_id, current_user)


@router.post("/strategy/{strategy_id}", response_model=TradeResponse, status_code=201)
def create_trade(
    strategy_id: str,
    data: TradeCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = TradeController(db)
    return controller.create(strategy_id, current_user, data)


@router.patch("/{trade_id}", response_model=TradeResponse)
def update_trade(
    trade_id: str,
    data: TradeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = TradeController(db)
    return controller.update(trade_id, current_user, data)


@router.post("/{trade_id}/close", response_model=TradeResponse)
def close_trade(
    trade_id: str,
    data: TradeCloseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = TradeController(db)
    return controller.close(trade_id, current_user, data)


@router.delete("/{trade_id}")
def delete_trade(
    trade_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = TradeController(db)
    return controller.delete(trade_id, current_user)
