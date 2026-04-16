# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/schemas/user_preference.py
# v5: + strike_mode
# ============================================================

from datetime import datetime
from pydantic import BaseModel, Field


class PreferenceUpdateRequest(BaseModel):
    ticker: str | None = Field(None, min_length=1, max_length=20)
    left_width: float | None = Field(None, gt=0)
    center_width: float | None = Field(None, gt=0)
    chain_count: int | None = Field(None, ge=1, le=2)
    sidebar_collapsed: bool | None = None
    compare_mode: bool | None = None
    payoff_settings: str | None = None  # JSON string
    theme: str | None = Field(None, min_length=1, max_length=32)
    broker: str | None = Field(None, min_length=1, max_length=32)
    strike_mode: str | None = Field(None, min_length=1, max_length=20)  # ★ v5


class PreferenceResponse(BaseModel):
    id: str
    user_id: str
    ticker: str
    left_width: float
    center_width: float
    chain_count: int
    sidebar_collapsed: bool
    compare_mode: bool
    payoff_settings: str | None
    theme: str
    broker: str
    strike_mode: str  # ★ v5
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}