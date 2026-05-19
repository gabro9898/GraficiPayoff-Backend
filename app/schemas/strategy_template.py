# ============================================================
# Percorso: app/schemas/strategy_template.py
# Pydantic schemas per i preset di strategia precompilati.
# ============================================================

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator


OptionType = Literal["CALL", "PUT"]
Direction = Literal["BUY", "SELL"]
ExpiryMatch = Literal["EXACT", "NEAREST"]
StrikeMode = Literal["DELTA", "OFFSET", "LINKED", "PREMIUM"]
DeltaMatch = Literal["EXACT", "NEAREST"]


class StrategyTemplateLegInput(BaseModel):
    leg_index: int = Field(ge=0)
    option_type: OptionType
    direction: Direction
    quantity: int = Field(ge=1, default=1)
    expiry_days: int = Field(ge=0)
    expiry_match: ExpiryMatch = "NEAREST"
    strike_mode: StrikeMode
    target_delta: float | None = Field(default=None, ge=0.0, le=1.0)
    delta_match: DeltaMatch | None = "NEAREST"
    target_offset: float | None = None
    linked_leg_index: int | None = Field(default=None, ge=0)
    linked_offset: float | None = 0
    # PREMIUM mode: valore assoluto del mid target (standalone) oppure offset
    # di premio rispetto alla leg linkata (se linked_leg_index è valorizzato).
    target_premium: float | None = None

    @model_validator(mode="after")
    def _check_mode_fields(self) -> "StrategyTemplateLegInput":
        if self.strike_mode == "DELTA":
            if self.target_delta is None:
                raise ValueError("target_delta richiesto quando strike_mode='DELTA'")
        elif self.strike_mode == "OFFSET":
            if self.target_offset is None:
                raise ValueError("target_offset richiesto quando strike_mode='OFFSET'")
        elif self.strike_mode == "LINKED":
            if self.linked_leg_index is None:
                raise ValueError("linked_leg_index richiesto quando strike_mode='LINKED'")
            if self.linked_leg_index >= self.leg_index:
                raise ValueError(
                    "linked_leg_index deve riferirsi a una leg precedente "
                    f"(leg_index={self.leg_index}, linked_leg_index={self.linked_leg_index})"
                )
        elif self.strike_mode == "PREMIUM":
            if self.target_premium is None:
                raise ValueError("target_premium richiesto quando strike_mode='PREMIUM'")
            # Se è anche linked, target_premium è interpretato come offset di
            # premio (può essere negativo); altrimenti è un valore assoluto > 0.
            if self.linked_leg_index is None and self.target_premium <= 0:
                raise ValueError(
                    "target_premium standalone deve essere > 0 "
                    f"(ricevuto {self.target_premium})"
                )
            if self.linked_leg_index is not None and self.linked_leg_index >= self.leg_index:
                raise ValueError(
                    "linked_leg_index deve riferirsi a una leg precedente "
                    f"(leg_index={self.leg_index}, linked_leg_index={self.linked_leg_index})"
                )
        return self


class StrategyTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    legs: list[StrategyTemplateLegInput] = Field(min_length=1)


class StrategyTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    # Se passato, sostituisce TUTTE le leg (replace totale). Se None, le leg
    # restano invariate. Comodo per editor che inviano sempre l'intera lista.
    legs: list[StrategyTemplateLegInput] | None = None


# --- Responses ---

class StrategyTemplateLegResponse(BaseModel):
    id: str
    leg_index: int
    option_type: str
    direction: str
    quantity: int
    expiry_days: int
    expiry_match: str
    strike_mode: str
    target_delta: float | None
    delta_match: str | None
    target_offset: float | None
    linked_leg_index: int | None
    linked_offset: float | None
    target_premium: float | None

    model_config = {"from_attributes": True}


class StrategyTemplateResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    legs: list[StrategyTemplateLegResponse] = []

    model_config = {"from_attributes": True}
