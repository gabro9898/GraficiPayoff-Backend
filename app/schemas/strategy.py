# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/schemas/strategy.py
# v10: + StrategySettleExpiredLegsRequest (settle parziale leg-by-leg
#      con mappa expiry → settlement_price del sottostante)
# ============================================================

from datetime import datetime, date
from pydantic import BaseModel, Field
from app.models.trade import OptionType, Direction


class StrategyLegInput(BaseModel):
    option_type: OptionType
    direction: Direction
    strike: float = Field(gt=0)
    premium: float = Field(ge=0)
    quantity: int = Field(gt=0)
    expiry: date
    enabled: bool = True
    trading_class: str | None = None
    commission: float = Field(default=0.0, ge=0)
    open_date: datetime | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    implied_volatility: float | None = None


class StrategyCreateRequest(BaseModel):
    account_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    ticker: str = Field(min_length=1, max_length=20)
    fill_price: float | None = None
    contract_multiplier: int = Field(default=1, ge=1)
    underlying_expiry: date | None = None
    legs: list[StrategyLegInput] = Field(default_factory=list)


class StrategyAddLegsRequest(BaseModel):
    fill_price: float | None = None
    legs: list[StrategyLegInput] = Field(min_length=1)


class StrategyCloseRequest(BaseModel):
    close_premium: float
    underlying_close_price: float | None = None


class StrategySettleRequest(BaseModel):
    """Settle 'vecchio stile': un solo settlement_price applicato a TUTTE le legs OPEN."""
    settlement_price: float = Field(gt=0)


# ★ v10: settle parziale per scadenza
class StrategySettleExpiredLegsRequest(BaseModel):
    """
    Settle parziale leg-by-leg.
    `settlements` è una mappa { expiry_iso : settlement_price_underlying }
    dove le chiavi sono date in formato ISO 'YYYY-MM-DD'.

    Il backend:
    - chiude solo le legs OPEN con expiry < today() per cui esiste
      una entry nella mappa
    - calcola intrinsic per ogni leg con il prezzo della SUA expiry
    - salva trade.settlement_price per-trade
    - lascia la strategia OPEN se restano legs non scadute
    - chiude la strategia se non rimane nessuna leg/underlying OPEN
    """
    settlements: dict[str, float] = Field(min_length=1)


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    fill_price: float | None = None
    # ★ v9: nuovi campi modificabili dall'EditStrategyModal
    account_id: str | None = None
    contract_multiplier: int | None = Field(None, ge=1)


class StrategyUpdateLegRequest(BaseModel):
    trade_id: str
    enabled: bool | None = None
    premium: float | None = Field(None, ge=0)
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None


class StrategyUpdateLegsRequest(BaseModel):
    fill_price: float | None = None
    legs: list[StrategyUpdateLegRequest] = Field(min_length=1)


class StrategyCloseLegRequest(BaseModel):
    trade_id: str
    close_premium: float = Field(ge=0)
    close_commission: float = Field(default=0.0, ge=0)
    quantity_to_close: int | None = Field(default=None, gt=0)


# --- Responses ---

class StrategyResponse(BaseModel):
    id: str
    user_id: str
    account_id: str
    number: int
    name: str
    description: str | None
    ticker: str
    fill_price: float | None
    settlement_price: float | None
    status: str
    realized_pnl: float
    contract_multiplier: int
    earliest_expiry: date | None
    underlying_expiry: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategyWithTradesResponse(StrategyResponse):
    trades: list["TradeResponse"] = []
    underlying_positions: list["UnderlyingPositionResponse"] = []


from app.schemas.trade import TradeResponse  # noqa: E402
from app.schemas.underlying_position import UnderlyingPositionResponse  # noqa: E402

StrategyWithTradesResponse.model_rebuild()