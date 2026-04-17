# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/api/routes/gex.py
# v2: + GET /gex/chain-all/{ticker} (multi-expiry)
# ============================================================

from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.gex_controller import GexController
from app.schemas.gex import GexChainResponse, GexExpiriesResponse, GexAllChainsResponse

router = APIRouter(prefix="/gex", tags=["GEX"])


def _require_active_subscription(user: User) -> None:
    if not user.is_subscription_active:
        raise HTTPException(status_code=403, detail="Abbonamento non attivo")


@router.get("/expiries/{ticker}", response_model=GexExpiriesResponse)
def get_expiries(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_active_subscription(current_user)
    controller = GexController(db)
    return controller.get_expiries(ticker)


@router.get("/chain/{ticker}/{expiry}", response_model=GexChainResponse)
def get_chain(
    ticker: str,
    expiry: date,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_active_subscription(current_user)
    controller = GexController(db)
    return controller.get_chain(ticker, expiry)


# ★ v2: endpoint multi-expiry
@router.get("/chain-all/{ticker}", response_model=GexAllChainsResponse)
def get_all_chains(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ritorna TUTTE le scadenze future con i rispettivi strikes in un unico payload.
    Usato dal frontend per calcolare esposizioni aggregate (All / 0DTE / Monthly).

    Payload:
      {
        "ticker": "SPX",
        "fetched_at": "...",
        "is_previous_session": false,
        "is_loading": false,
        "expiries": [
          { "expiry": "2026-04-16", "dte_days": 0.5, "is_monthly": false, "strikes": [...] },
          { "expiry": "2026-04-17", "dte_days": 1.5, "is_monthly": false, "strikes": [...] },
          ...
        ]
      }
    """
    _require_active_subscription(current_user)
    controller = GexController(db)
    return controller.get_all_chains(ticker)