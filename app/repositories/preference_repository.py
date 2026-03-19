# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/repositories/preference_repository.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.user_preference import UserPreference


class PreferenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_user_id(self, user_id: str) -> UserPreference | None:
        return (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == user_id)
            .first()
        )

    def create(self, preference: UserPreference) -> UserPreference:
        self.db.add(preference)
        self.db.commit()
        self.db.refresh(preference)
        return preference

    def update(self, preference: UserPreference, data: dict) -> UserPreference:
        for key, value in data.items():
            if value is not None:
                setattr(preference, key, value)
        self.db.commit()
        self.db.refresh(preference)
        return preference