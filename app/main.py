# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/main.py
# v4: + app_info router + seed latest_version on startup
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import engine, Base, SessionLocal
from app.api.routes import auth_router, user_router, strategy_router, trade_router
from app.api.routes.account import router as account_router
from app.api.routes.preference import router as preference_router
from app.api.routes.tastytrade import router as tastytrade_router
from app.api.routes.app_info import router as app_info_router

settings = get_settings()


def seed_app_settings():
    """Crea i settings di default se non esistono."""
    from app.models.app_setting import AppSetting
    db = SessionLocal()
    try:
        # latest_version
        existing = db.query(AppSetting).filter(AppSetting.key == "latest_version").first()
        if not existing:
            db.add(AppSetting(key="latest_version", value="1.0.1"))

        # download_url (landing page per scaricare aggiornamento)
        existing_url = db.query(AppSetting).filter(AppSetting.key == "download_url").first()
        if not existing_url:
            db.add(AppSetting(key="download_url", value="https://optionspayofftracker.com/download"))

        # landing_url (pagina per acquisto/rinnovo abbonamento)
        existing_landing = db.query(AppSetting).filter(AppSetting.key == "landing_url").first()
        if not existing_landing:
            db.add(AppSetting(key="landing_url", value="https://optionspayofftracker.com/pricing"))

        db.commit()
    except Exception as e:
        print(f"[Seed] Error seeding app_settings: {e}")
        db.rollback()
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Backend API for Options Payoff Tracker - manage users, strategies, and option trades.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS - allow Electron frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(account_router, prefix="/api/v1")
    app.include_router(strategy_router, prefix="/api/v1")
    app.include_router(trade_router, prefix="/api/v1")
    app.include_router(preference_router, prefix="/api/v1")
    app.include_router(tastytrade_router, prefix="/api/v1")
    app.include_router(app_info_router, prefix="/api/v1")  # ★ App info + version

    @app.on_event("startup")
    def on_startup():
        # Create tables (use Alembic migrations in production)
        Base.metadata.create_all(bind=engine)
        # ★ Seed default app settings
        seed_app_settings()

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "healthy", "app": settings.APP_NAME}

    return app


app = create_app()