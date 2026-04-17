# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/controllers/gex_controller.py
# v2: + get_all_chains()
# ============================================================

from datetime import date
from sqlalchemy.orm import Session

from app.services.gex_service import GexService
from app.schemas.gex import GexChainResponse, GexExpiriesResponse, GexAllChainsResponse


class GexController:
    def __init__(self, db: Session):
        self.gex_service = GexService(db)

    def get_chain(self, ticker: str, expiry: date) -> GexChainResponse:
        return self.gex_service.get_chain(ticker, expiry)

    def get_expiries(self, ticker: str) -> GexExpiriesResponse:
        return self.gex_service.get_expiries(ticker)

    # ★ v2
    def get_all_chains(self, ticker: str) -> GexAllChainsResponse:
        return self.gex_service.get_all_chains(ticker)