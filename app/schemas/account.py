# ============================================================
# NUOVO FILE
# Percorso: app/schemas/account.py
# ============================================================

from datetime import datetime
from pydantic import BaseModel, Field


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class AccountUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None


class AccountResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountWithStrategiesResponse(AccountResponse):
    strategies: list["StrategyResponse"] = []


from app.schemas.strategy import StrategyResponse  # noqa: E402

AccountWithStrategiesResponse.model_rebuild()