# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/schemas/one_import.py
#
# Schemas dedicati per l'import di "ONE Detail Report" (Option Net Explorer).
# Isolati dagli schemas condivisi (strategy.py, trade.py) per non rompere
# le validazioni dei flussi normali (close manuale, broker, ecc.).
#
# Differenze chiave rispetto agli schemas standard:
#  - close_premium accetta valori SIGNED (ONE usa il segno come convention
#    contabile sulle chiusure: "Buy @ -0.467" = accreditato 0.467)
#  - open_date passata per leg
#  - opened_at per la strategy (override di created_at)
# ============================================================

from datetime import datetime, date
from pydantic import BaseModel, Field
from app.models.trade import OptionType, Direction


class OneTransactionIn(BaseModel):
    """Una singola transazione di ONE (apertura o chiusura)."""
    date: datetime
    transaction: str  # "Buy" | "Sell"
    qty: int = Field(gt=0)
    option_type: OptionType
    strike: float = Field(gt=0)
    expiry: date
    # ★ SIGNED: per le chiusure ONE può usare valori negativi come convention
    # contabile (es. "Buy @ -0.467" → accreditato 0.467 per contratto).
    price: float
    commission: float = Field(default=0.0, ge=0)


class OneTradeIn(BaseModel):
    """Un trade ONE completo (header + transazioni)."""
    trade_id: str  # ONE TradeId originale (per logging/troubleshooting)
    trade_name: str
    underlying: str
    status: str  # "Open" | "Closed"
    expiration: date
    open_date: datetime
    close_date: datetime | None = None
    expected_pnl: float | None = None      # ONE PnL — usato per validazione
    expected_comms: float | None = None    # ONE comms — usato per validazione
    transactions: list[OneTransactionIn] = Field(min_length=1)


class OneImportRequest(BaseModel):
    """Payload completo per l'import: una lista di trade + opzioni."""
    account_id: str
    contract_multiplier: int = Field(default=100, ge=1)
    # Cosa fare con trade Open ma con expiry già passata
    expired_open_action: str = Field(default="leave-open")  # "leave-open" | "close-auto"
    trades: list[OneTradeIn] = Field(min_length=1)


# ─── Response ───

class OneImportResultItem(BaseModel):
    """Risultato dell'import di un singolo trade."""
    trade_id: str         # ONE TradeId originale
    trade_name: str
    success: bool
    strategy_id: str | None = None
    realized_pnl: float | None = None
    expected_pnl: float | None = None
    pnl_delta: float | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class OneImportResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: list[OneImportResultItem]
