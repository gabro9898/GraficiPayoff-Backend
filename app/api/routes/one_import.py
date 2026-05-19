# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/api/routes/one_import.py
#
# Endpoint dedicato all'import di "ONE Detail Report" (Option Net Explorer).
# Isolato dai router /strategies e /trades per non rompere i flussi normali.
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.one_import_controller import OneImportController
from app.schemas.one_import import OneImportRequest, OneImportResponse


router = APIRouter(prefix="/import", tags=["Import"])


@router.post("/one", response_model=OneImportResponse)
def import_one_detail_report(
    data: OneImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import di un batch di trade da ONE Detail Report.

    Riceve una lista di trade ONE (header + transazioni) e produce strategie
    con leg correttamente popolate. Gestisce:
     - close_premium SIGNED (convention contabile di ONE)
     - commission pro-rata sugli split close
     - created_at della strategy allineato alla data di apertura più vecchia
     - fallback close a premio 0 per leg orfane
     - auto-close a 0 per Open scaduti se richiesto

    Ritorna risultati per-trade (success/failure + warnings + PnL delta).
    """
    controller = OneImportController(db)
    return controller.import_one(current_user, data)
