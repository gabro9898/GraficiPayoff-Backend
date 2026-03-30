# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/schemas/stripe.py
# ============================================================

from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    price_id: str  # "monthly" o "annual"


class CheckoutSessionResponse(BaseModel):
    url: str