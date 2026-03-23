# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/schemas/broker.py
# Schemas per broker OAuth e status
# ============================================================

from datetime import datetime
from pydantic import BaseModel


class BrokerAuthUrlResponse(BaseModel):
    """URL OAuth da aprire nel browser/Electron."""
    auth_url: str
    state: str  # CSRF protection


class BrokerStatusResponse(BaseModel):
    """Status connessione di un broker per l'utente corrente."""
    broker_id: str
    connected: bool
    expires_at: datetime | None = None


class BrokerDisconnectResponse(BaseModel):
    broker_id: str
    disconnected: bool


class TastyTradeAccountInfo(BaseModel):
    """Info account TastyTrade."""
    account_number: str
    account_type: str | None = None
    nickname: str | None = None
    is_margin: bool = False