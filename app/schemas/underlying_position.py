# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/schemas/underlying_position.py
# ============================================================

from datetime import datetime
from pydantic import BaseModel, Field


class UnderlyingPositionCreateRequest(BaseModel):
    direction: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    multiplier: float = Field(gt=0, default=1.0)


class UnderlyingPositionCloseRequest(BaseModel):
    position_id: str
    close_price: float = Field(gt=0)


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
    pnl: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}