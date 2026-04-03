# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/api/routes/tastytrade.py
# v4: fix callback — code/state opzionali, gestione errore pulita
# ============================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.services.tastytrade_service import TastyTradeService
from app.config import get_settings
from app.schemas.broker import (
    BrokerAuthUrlResponse,
    BrokerStatusResponse,
    BrokerDisconnectResponse,
)

router = APIRouter(prefix="/tastytrade", tags=["TastyTrade"])


# ═══════════════ Sandbox check ═══════════════

@router.get("/is-sandbox")
def is_sandbox():
    """Il frontend usa questo per sapere se mostrare il modal refresh token o la popup OAuth."""
    return {"sandbox": get_settings().TASTYTRADE_SANDBOX}


# ═══════════════ OAuth2 Flow (produzione) ═══════════════

@router.get("/auth-url", response_model=BrokerAuthUrlResponse)
def get_auth_url(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Genera l'URL per l'autorizzazione OAuth2 TastyTrade (produzione)."""
    service = TastyTradeService(db)
    return service.get_auth_url(current_user.id)


@router.get("/callback")
async def oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    """Callback OAuth2 (produzione). TastyTrade rimanda qui dopo login."""

    # ★ Se code o state mancano, o TastyTrade ha mandato un errore
    if error or not code or not state:
        err_msg = error or "Autorizzazione negata o parametri mancanti"
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head><title>Errore autorizzazione</title></head>
        <body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0a0a0f;color:#e4e4ee;">
            <div style="text-align:center;">
                <h2 style="color:#ff4757;">✗ Autorizzazione fallita</h2>
                <p style="color:#8888a0;">{err_msg[:200]}</p>
                <p style="color:#55556a;font-size:0.85rem;">Chiudi questa finestra e riprova.</p>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{ type: 'tastytrade-auth-error', error: '{err_msg[:100]}' }}, '*');
                        setTimeout(() => window.close(), 3000);
                    }}
                </script>
            </div>
        </body>
        </html>
        """, status_code=200)

    service = TastyTradeService(db)
    try:
        result = await service.handle_callback(code, state)
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>Autorizzazione completata</title></head>
        <body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0a0a0f;color:#e4e4ee;">
            <div style="text-align:center;">
                <h2 style="color:#00d4aa;">✓ TastyTrade connesso!</h2>
                <p style="color:#8888a0;">Puoi chiudere questa finestra e tornare all'app.</p>
                <script>
                    if (window.opener) {
                        window.opener.postMessage({ type: 'tastytrade-auth-success' }, '*');
                        setTimeout(() => window.close(), 1500);
                    }
                </script>
            </div>
        </body>
        </html>
        """, status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head><title>Errore autorizzazione</title></head>
        <body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0a0a0f;color:#e4e4ee;">
            <div style="text-align:center;">
                <h2 style="color:#ff4757;">✗ Autorizzazione fallita</h2>
                <p style="color:#8888a0;">Errore: {str(e)[:200]}</p>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{ type: 'tastytrade-auth-error', error: '{str(e)[:100]}' }}, '*');
                        setTimeout(() => window.close(), 3000);
                    }}
                </script>
            </div>
        </body>
        </html>
        """, status_code=200)


# ═══════════════ Sandbox: refresh token manuale ═══════════════

class ConnectRequest(BaseModel):
    refresh_token: str


@router.post("/connect")
async def connect_with_refresh_token(
    data: ConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connetti TastyTrade con refresh token manuale (sandbox).
    L'utente lo genera dal portale developer.tastyworks.com → Create Grant.
    """
    service = TastyTradeService(db)
    return await service.save_refresh_token(current_user.id, data.refresh_token)


# ═══════════════ Status & Disconnect ═══════════════

@router.get("/status", response_model=BrokerStatusResponse)
def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    return service.get_status(current_user.id)


@router.post("/disconnect", response_model=BrokerDisconnectResponse)
def disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    result = service.disconnect(current_user.id)
    return {"broker_id": "tastytrade", "disconnected": result}


# ═══════════════ API Proxy ═══════════════

@router.get("/accounts")
async def get_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    return await service.get_accounts(current_user.id)


@router.get("/streamer-token")
async def get_streamer_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    return await service.get_streamer_token(current_user.id)


@router.get("/option-chains/{symbol}")
async def get_option_chains(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    return await service.get_option_chains(current_user.id, symbol.upper())


@router.get("/symbols/search/{query}")
async def search_symbols(
    query: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    return await service.search_symbols(current_user.id, query)


@router.post("/accounts/{account_number}/orders")
async def place_order(
    account_number: str,
    order: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    return await service.place_order(current_user.id, account_number, order)


@router.get("/accounts/{account_number}/positions")
async def get_positions(
    account_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = TastyTradeService(db)
    return await service.get_positions(current_user.id, account_number)