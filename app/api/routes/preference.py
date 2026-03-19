# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/api/routes/preference.py
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.preference_controller import PreferenceController
from app.schemas.user_preference import PreferenceUpdateRequest, PreferenceResponse

router = APIRouter(prefix="/preferences", tags=["Preferences"])


@router.get("/", response_model=PreferenceResponse)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = PreferenceController(db)
    return controller.get(current_user)


@router.put("/", response_model=PreferenceResponse)
def update_preferences(
    data: PreferenceUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = PreferenceController(db)
    return controller.update(current_user, data)