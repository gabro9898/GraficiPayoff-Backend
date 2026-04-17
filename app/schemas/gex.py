# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/schemas/gex.py
# v2: + ExpiryChainData + GexAllChainsResponse (multi-expiry endpoint)
# ============================================================

from datetime import datetime, date
from pydantic import BaseModel, Field


class StrikeGexData(BaseModel):
    """Dati OI+IV per un singolo strike."""
    strike: float
    oi_call: int
    oi_put: int
    iv_call: float | None = None
    iv_put: float | None = None


class GexChainResponse(BaseModel):
    """Response dell'endpoint /gex/chain/{ticker}/{expiry}."""
    ticker: str
    expiry: date
    fetched_at: datetime | None = None
    is_previous_session: bool = False
    is_loading: bool = False
    strikes: list[StrikeGexData] = Field(default_factory=list)


class GexExpiriesResponse(BaseModel):
    """Response dell'endpoint /gex/expiries/{ticker}."""
    ticker: str
    fetched_at: datetime | None = None
    is_previous_session: bool = False
    is_loading: bool = False
    expiries: list[date] = Field(default_factory=list)


# ═══════════════ ★ v2: multi-expiry ═══════════════

class ExpiryChainData(BaseModel):
    """
    Chain di una singola scadenza, arricchita con dte_days precomputato
    (utile al frontend per filtering 0DTE/monthly senza ricalcoli).
    """
    expiry: date
    dte_days: float            # Days to expiry (float, può essere 0.5 per 0DTE pomeridiano)
    is_monthly: bool           # True se è 3° venerdì del mese (standard monthly)
    strikes: list[StrikeGexData] = Field(default_factory=list)


class GexAllChainsResponse(BaseModel):
    """
    Response dell'endpoint /gex/chain-all/{ticker}.
    Ritorna tutte le scadenze future in un unico payload.
    Il frontend può aggregare localmente per All/0DTE/Monthly.
    """
    ticker: str
    fetched_at: datetime | None = None
    is_previous_session: bool = False
    is_loading: bool = False
    expiries: list[ExpiryChainData] = Field(default_factory=list)