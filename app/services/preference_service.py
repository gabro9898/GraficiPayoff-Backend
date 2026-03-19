# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/services/preference_service.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.user_preference import UserPreference
from app.repositories.preference_repository import PreferenceRepository
from app.schemas.user_preference import PreferenceUpdateRequest


class PreferenceService:
    def __init__(self, db: Session):
        self.preference_repo = PreferenceRepository(db)

    def get_or_create(self, user_id: str) -> UserPreference:
        """Ritorna le preferenze dell'utente, creandole con valori default se non esistono."""
        pref = self.preference_repo.find_by_user_id(user_id)
        if not pref:
            pref = UserPreference(user_id=user_id)
            pref = self.preference_repo.create(pref)
        return pref

    def update(self, user_id: str, data: PreferenceUpdateRequest) -> UserPreference:
        """Aggiorna le preferenze dell'utente (crea se non esistono)."""
        pref = self.get_or_create(user_id)
        update_data = data.model_dump(exclude_unset=True)
        if update_data:
            pref = self.preference_repo.update(pref, update_data)
        return pref