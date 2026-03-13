from datetime import datetime
from pydantic import BaseModel, Field


# --- Request schemas ---

class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None


# --- Response schemas ---

class StrategyResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategyWithTradesResponse(StrategyResponse):
    trades: list["TradeResponse"] = []


# Avoid circular import - will be resolved at runtime
from app.schemas.trade import TradeResponse  # noqa: E402

StrategyWithTradesResponse.model_rebuild()
