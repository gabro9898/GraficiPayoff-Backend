# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/api/routes/strategy.py
# v4: + MODEL feature: GET /models, POST /model,
#     PUT /{id}/model-legs (auto-save), POST /{id}/fill
# v3: + GET /with-expired-legs (lookup auto-settle parziale)
#     + POST /{id}/settle-expired-legs (settle leg-by-leg con mappa expiry→price)
# ============================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.strategy_controller import StrategyController
from app.schemas.strategy import (
    StrategyCreateRequest, StrategyUpdateRequest,
    StrategyAddLegsRequest, StrategyCloseRequest, StrategySettleRequest,
    StrategySettleExpiredLegsRequest,
    StrategyUpdateLegsRequest, StrategyCloseLegRequest,
    StrategyCreateModelRequest, StrategyReplaceModelLegsRequest,
    StrategyReplacePendingLegsRequest,
    StrategyFillModelRequest,
    StrategyCreateRequest2, StrategySaveLegsRequest, StrategyFillPendingLegRequest,
    StrategyResponse, StrategyWithTradesResponse, StrategyReplaceLegsResponse,
)
from app.schemas.underlying_position import (
    UnderlyingPositionCreateRequest, UnderlyingPositionCloseRequest,
)

router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.get("/", response_model=list[StrategyResponse])
def get_all_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_all(current_user)


# v2: ritorna TUTTE le strategie CON trades per la Portfolio page
@router.get("/portfolio", response_model=list[StrategyWithTradesResponse])
def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_all_with_trades(current_user)


@router.get("/open-expired", response_model=list[StrategyWithTradesResponse])
def get_open_expired_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_open_expired(current_user)


# ★ v3: nuovo endpoint per il flow di auto-settle parziale.
# Ritorna strategie OPEN con almeno UN trade OPEN già scaduto.
# Superset di /open-expired (che invece richiede TUTTE le legs scadute).
@router.get("/with-expired-legs", response_model=list[StrategyWithTradesResponse])
def get_strategies_with_expired_legs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_strategies_with_expired_legs(current_user)


# ★ v4: MODEL — lista delle strategie MODEL dell'utente.
# Il backend fa cleanup on-the-fly: i MODEL con tutte le leg scadute
# vengono cancellati prima di restituire la lista.
@router.get("/models", response_model=list[StrategyWithTradesResponse])
def get_all_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.get_all_models(current_user)


# ★ v4: MODEL — crea una nuova strategia MODEL (leg senza prezzi).
@router.post("/model", response_model=StrategyWithTradesResponse, status_code=201)
def create_model(
    data: StrategyCreateModelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.create_model(current_user, data)


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


# Feature 1: aggiornare legs esistenti
@router.patch("/{strategy_id}/legs", response_model=StrategyWithTradesResponse)
def update_legs_in_strategy(
    strategy_id: str,
    data: StrategyUpdateLegsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.update_legs(strategy_id, current_user, data)


# Feature 2: chiudere una singola leg
@router.post("/{strategy_id}/close-leg", response_model=StrategyWithTradesResponse)
def close_leg_in_strategy(
    strategy_id: str,
    data: StrategyCloseLegRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.close_leg(strategy_id, current_user, data)


# ★ v4: MODEL — auto-save: replace totale delle leg di un MODEL.
# Usato dal FE a ogni modifica dell'utente (con debounce).
# Funziona SOLO se strategy.status == "MODEL".
@router.put("/{strategy_id}/model-legs", response_model=StrategyReplaceLegsResponse)
def replace_model_legs(
    strategy_id: str,
    data: StrategyReplaceModelLegsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.replace_model_legs(strategy_id, current_user, data)


# ★ Auto-save delle pending leg di una strategia OPEN. Equivalente di
# replace_model_legs ma per le pending — replace totale evita duplicati quando
# l'utente modifica una pending già salvata (es. shift bulk di strike).
@router.put("/{strategy_id}/pending-legs", response_model=StrategyReplaceLegsResponse)
def replace_pending_legs(
    strategy_id: str,
    data: StrategyReplacePendingLegsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.replace_pending_legs(strategy_id, current_user, data)


# ★ v4: MODEL — fill: converte un MODEL in strategia OPEN salvando prezzi/greche.
# Body identico a StrategyCreateRequest (fill_price + legs con premium/delta/...).
@router.post("/{strategy_id}/fill", response_model=StrategyWithTradesResponse)
def fill_model(
    strategy_id: str,
    data: StrategyFillModelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.fill_model(strategy_id, current_user, data)


# ═══════════════════════════════════════════════════════════════
# ★ v15: PENDING LEGS — vivono nella stessa Strategy con is_pending=True
# ═══════════════════════════════════════════════════════════════

# Crea una nuova strategy OPEN con leg active (frozen=True) + leg pending
# (is_pending=True), tutte nella stessa Strategy.
@router.post("/with-pending", response_model=StrategyWithTradesResponse)
def create_strategy_with_pending(
    data: StrategyCreateRequest2,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.create_with_pending(current_user, data)


# Aggiunge leg a una strategy OPEN: active diventano frozen Trade, pending
# diventano is_pending Trade (tutto nella stessa Strategy).
@router.post("/{strategy_id}/legs-mixed", response_model=StrategyWithTradesResponse)
def save_legs(
    strategy_id: str,
    data: StrategySaveLegsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.save_legs(strategy_id, current_user, data)


# Fill incrementale di una pending leg: in-place setta is_pending=False,
# frozen=True, premium=<fill> (la leg resta nella stessa Strategy).
@router.post("/{strategy_id}/pending-legs/{leg_id}/fill", response_model=StrategyWithTradesResponse)
def fill_pending_leg(
    strategy_id: str,
    leg_id: str,
    data: StrategyFillPendingLegRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.fill_pending_leg(strategy_id, leg_id, current_user, data)


# Rimuove una pending leg dalla Strategy.
@router.delete("/{strategy_id}/pending-legs/{leg_id}")
def delete_pending_leg(
    strategy_id: str,
    leg_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.delete_pending_leg(strategy_id, leg_id, current_user)


# Underlying positions
@router.post("/{strategy_id}/underlying", response_model=StrategyWithTradesResponse)
def add_underlying_to_strategy(
    strategy_id: str,
    data: UnderlyingPositionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.add_underlying(strategy_id, current_user, data)


@router.post("/{strategy_id}/close-underlying", response_model=StrategyWithTradesResponse)
def close_underlying_in_strategy(
    strategy_id: str,
    data: UnderlyingPositionCloseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.close_underlying(strategy_id, current_user, data)


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


# ★ v3: settle parziale leg-by-leg.
# Body: { "settlements": { "2026-04-15": 5642.50, "2026-05-15": 5701.20 } }
# Chiude solo le legs OPEN con expiry < today() per cui è presente un prezzo.
@router.post("/{strategy_id}/settle-expired-legs", response_model=StrategyWithTradesResponse)
def settle_expired_legs(
    strategy_id: str,
    data: StrategySettleExpiredLegsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyController(db)
    return controller.settle_expired_legs(strategy_id, current_user, data)


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