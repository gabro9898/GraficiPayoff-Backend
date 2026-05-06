# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/api/routes/gex.py
# v3: + POST /gex/refresh/{ticker} (trigger manuale del refresh)
# ============================================================

from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.gex_controller import GexController
from app.schemas.gex import GexChainResponse, GexExpiriesResponse, GexAllChainsResponse
from app.services import gex_scheduler as gex_scheduler_module

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


# ★ v3: trigger manuale del refresh GEX — route di emergenza, SENZA AUTH
# Endpoint pubblico volutamente: serve a forzare il refresh al volo senza
# dover prendere un token. Se il backend è esposto pubblicamente, valuta
# l'aggiunta di un secret in header (es. X-Refresh-Secret).
@router.post("/refresh/{ticker}", status_code=202)
async def trigger_manual_refresh(ticker: str):
    """
    Forza un refresh manuale del GEX per il ticker indicato.
    Background: loop di retry ogni 60s fino al successo o al cutoff orario.
    Risposta immediata (202 Accepted).

    Stati possibili:
      - "started"          → loop avviato adesso
      - "already_running"  → un loop era già in corso per questo ticker
      - "unknown_ticker"   → ticker non configurato in GEX_TICKERS
      - "disabled"         → scheduler disattivato o POLYGON_API_KEY mancante
    """
    scheduler = gex_scheduler_module.gex_scheduler
    if scheduler is None:
        raise HTTPException(status_code=503, detail="GEX scheduler non inizializzato")

    result = scheduler.trigger_manual_refresh(ticker)

    if result["status"] == "unknown_ticker":
        raise HTTPException(
            status_code=404,
            detail=f"Ticker '{ticker}' non configurato. Disponibili: "
                   f"{result.get('available_tickers', [])}",
        )
    if result["status"] == "disabled":
        raise HTTPException(status_code=503, detail=result.get("message", "GEX disabilitato"))

    return result