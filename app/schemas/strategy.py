# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/schemas/strategy.py
# ============================================================

from datetime import datetime, date
from pydantic import BaseModel, Field
from app.models.trade import OptionType, Direction


# --- Leg sub-schema ---

class StrategyLegInput(BaseModel):
    """Singola leg quando si salva una strategia."""
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


# --- Request schemas ---

class StrategyCreateRequest(BaseModel):
    """Salva una nuova strategia con tutte le legs."""
    account_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    ticker: str = Field(min_length=1, max_length=20)
    fill_price: float | None = None
    legs: list[StrategyLegInput] = Field(min_length=1)


class StrategyAddLegsRequest(BaseModel):
    """Aggiunge nuove legs (correzioni) a una strategia esistente."""
    fill_price: float | None = None
    legs: list[StrategyLegInput] = Field(min_length=1)


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    fill_price: float | None = None


# --- Response schemas ---

class StrategyResponse(BaseModel):
    id: str
    user_id: str
    account_id: str
    number: int
    name: str
    description: str | None
    ticker: str
    fill_price: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategyWithTradesResponse(StrategyResponse):
    trades: list["TradeResponse"] = []


from app.schemas.trade import TradeResponse  # noqa: E402

StrategyWithTradesResponse.model_rebuild()