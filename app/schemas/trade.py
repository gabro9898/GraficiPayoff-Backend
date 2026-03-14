# ============================================================
# FILE AGGIORNATO — sostituisce il file esistente
# Percorso: app/schemas/trade.py
# ============================================================

from datetime import datetime, date
from pydantic import BaseModel, Field
from app.models.trade import OptionType, Direction, TradeStatus


# --- Request schemas ---

class TradeCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
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
    underlying_price: float | None = Field(None, gt=0)
    implied_volatility: float | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=500)


class TradeUpdateRequest(BaseModel):
    ticker: str | None = Field(None, min_length=1, max_length=20)
    option_type: OptionType | None = None
    direction: Direction | None = None
    strike: float | None = Field(None, gt=0)
    premium: float | None = Field(None, ge=0)
    quantity: int | None = Field(None, gt=0)
    expiry: date | None = None
    enabled: bool | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    underlying_price: float | None = Field(None, gt=0)
    implied_volatility: float | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=500)


class TradeCloseRequest(BaseModel):
    close_premium: float = Field(ge=0)


# --- Response schemas ---

class TradeResponse(BaseModel):
    id: str
    strategy_id: str
    ticker: str
    option_type: OptionType
    direction: Direction
    strike: float
    premium: float
    quantity: int
    expiry: date
    enabled: bool
    frozen: bool
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    underlying_price: float | None
    implied_volatility: float | None
    status: TradeStatus
    open_date: datetime
    close_date: datetime | None
    close_premium: float | None
    pnl: float | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}