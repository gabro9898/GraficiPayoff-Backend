# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/controllers/preference_controller.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.user import User
from app.services.preference_service import PreferenceService
from app.schemas.user_preference import PreferenceUpdateRequest, PreferenceResponse


class PreferenceController:
    def __init__(self, db: Session):
        self.preference_service = PreferenceService(db)

    def get(self, current_user: User) -> PreferenceResponse:
        pref = self.preference_service.get_or_create(current_user.id)
        return PreferenceResponse.model_validate(pref)

    def update(self, current_user: User, data: PreferenceUpdateRequest) -> PreferenceResponse:
        pref = self.preference_service.update(current_user.id, data)
        return PreferenceResponse.model_validate(pref)