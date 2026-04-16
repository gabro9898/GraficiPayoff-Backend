# ============================================================
# Percorso: app/schemas/underlying_position.py
# v3: + commission + close_commission
# ============================================================

from datetime import datetime
from pydantic import BaseModel, Field


class UnderlyingPositionCreateRequest(BaseModel):
    direction: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    multiplier: float = Field(gt=0, default=1.0)
    commission: float = Field(default=0.0, ge=0)


class UnderlyingPositionCloseRequest(BaseModel):
    position_id: str
    close_price: float = Field(gt=0)
    close_commission: float = Field(default=0.0, ge=0)  # ★ v3


class UnderlyingPositionResponse(BaseModel):
    id: str
    strategy_id: str
    ticker: str
    direction: str
    quantity: int
    entry_price: float
    multiplier: float
    status: str
    close_price: float | None
    close_date: datetime | None
    commission: float
    close_commission: float
    pnl: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}