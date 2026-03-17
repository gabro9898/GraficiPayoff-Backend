# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/schemas/strategy.py
# Aggiunto: realized_pnl, StrategyCloseLegRequest, StrategyUpdateLegsRequest
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
    legs: list[StrategyLegInput] = Field(min_length=1)


class StrategyAddLegsRequest(BaseModel):
    fill_price: float | None = None
    legs: list[StrategyLegInput] = Field(min_length=1)


class StrategyCloseRequest(BaseModel):
    close_premium: float


class StrategySettleRequest(BaseModel):
    settlement_price: float = Field(gt=0)


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    fill_price: float | None = None


# ★ Feature 1: aggiornare legs esistenti (es. attivare legs spente)
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


# ★ Feature 2: chiudere una singola leg (adjustment)
class StrategyCloseLegRequest(BaseModel):
    trade_id: str
    close_premium: float = Field(ge=0)


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategyWithTradesResponse(StrategyResponse):
    trades: list["TradeResponse"] = []


from app.schemas.trade import TradeResponse  # noqa: E402

StrategyWithTradesResponse.model_rebuild()