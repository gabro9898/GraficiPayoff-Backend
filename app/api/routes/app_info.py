# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/api/routes/app_info.py
# v2: + endpoint /downloads con GitHub Releases
# ============================================================

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/app", tags=["App Info"])

GITHUB_REPO = "gabro9898/options-tracker-releases"


@router.get("/version")
def get_latest_version(db: Session = Depends(get_db)):
    version_row = db.query(AppSetting).filter(AppSetting.key == "latest_version").first()
    download_url_row = db.query(AppSetting).filter(AppSetting.key == "download_url").first()
    landing_url_row = db.query(AppSetting).filter(AppSetting.key == "landing_url").first()

    return {
        "latest_version": version_row.value if version_row else "1.0.0",
        "download_url": download_url_row.value if download_url_row else "",
        "landing_url": landing_url_row.value if landing_url_row else "",
    }


@router.get("/downloads")
async def get_downloads(current_user: User = Depends(get_current_user)):
    """Ritorna i link di download dall'ultima release GitHub. Richiede autenticazione."""

    if not current_user.is_subscription_active:
        raise HTTPException(status_code=403, detail="Abbonamento non attivo")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )

        if res.status_code != 200:
            raise HTTPException(status_code=502, detail="Impossibile recuperare le release")

        release = res.json()
        version = release.get("tag_name", "")
        assets = release.get("assets", [])

        downloads = {
            "version": version,
            "windows": None,
            "mac": None,
        }

        for asset in assets:
            name = asset.get("name", "").lower()
            url = asset.get("browser_download_url", "")
            size_mb = round(asset.get("size", 0) / (1024 * 1024), 1)

            if name.endswith(".exe"):
                downloads["windows"] = {
                    "name": asset.get("name"),
                    "url": url,
                    "size": f"{size_mb} MB",
                }
            elif name.endswith(".dmg"):
                downloads["mac"] = {
                    "name": asset.get("name"),
                    "url": url,
                    "size": f"{size_mb} MB",
                }

        return downloads

    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Errore di connessione a GitHub")