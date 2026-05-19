# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/controllers/one_import_controller.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.user import User
from app.services.one_import_service import OneImportService
from app.schemas.one_import import OneImportRequest, OneImportResponse


class OneImportController:
    def __init__(self, db: Session):
        self.service = OneImportService(db)

    def import_one(self, current_user: User, data: OneImportRequest) -> OneImportResponse:
        return self.service.import_trades(current_user.id, data)
