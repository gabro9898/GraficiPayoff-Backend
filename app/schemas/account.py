# ============================================================
# Percorso: app/schemas/account.py
# v3: separate open/close commission for options and stocks
# ============================================================

from datetime import datetime
from pydantic import BaseModel, Field


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    commission_option_per_contract: float = Field(default=0.0, ge=0)
    commission_option_close_per_contract: float = Field(default=0.0, ge=0)
    commission_stock_type: str = Field(default="per_order", pattern="^(per_order|per_share)$")
    commission_stock_value: float = Field(default=0.0, ge=0)
    commission_stock_close_value: float = Field(default=0.0, ge=0)


class AccountUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    commission_option_per_contract: float | None = Field(None, ge=0)
    commission_option_close_per_contract: float | None = Field(None, ge=0)
    commission_stock_type: str | None = Field(None, pattern="^(per_order|per_share)$")
    commission_stock_value: float | None = None
    commission_stock_close_value: float | None = None


class AccountResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    commission_option_per_contract: float
    commission_option_close_per_contract: float
    commission_stock_type: str
    commission_stock_value: float
    commission_stock_close_value: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountWithStrategiesResponse(AccountResponse):
    strategies: list["StrategyResponse"] = []


from app.schemas.strategy import StrategyResponse  # noqa: E402

AccountWithStrategiesResponse.model_rebuild()