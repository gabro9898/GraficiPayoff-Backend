# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/api/routes/app_info.py
# Endpoint per version check e info app
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.app_setting import AppSetting

router = APIRouter(prefix="/app", tags=["App Info"])


@router.get("/version")
def get_latest_version(db: Session = Depends(get_db)):
    """Ritorna la versione più recente dell'app + link. Non richiede autenticazione."""
    version_row = db.query(AppSetting).filter(AppSetting.key == "latest_version").first()
    download_url_row = db.query(AppSetting).filter(AppSetting.key == "download_url").first()
    landing_url_row = db.query(AppSetting).filter(AppSetting.key == "landing_url").first()

    return {
        "latest_version": version_row.value if version_row else "1.0.0",
        "download_url": download_url_row.value if download_url_row else "",
        "landing_url": landing_url_row.value if landing_url_row else "",
    }