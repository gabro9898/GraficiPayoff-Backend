# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/main.py
# v6: + GEX router + GEX scheduler avviato allo startup
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
from app.api.routes.stripe import router as stripe_router
from app.api.routes.gex import router as gex_router  # ★ GEX
from app.api.routes.contact import router as contact_router  # ★ Chat contatto

# ★ Import dei modelli per registrarli sul Base.metadata
# (se non vengono importati da qualche parte, create_all non li vede)
from app.models import gex_data  # noqa: F401
from app.models import password_reset  # noqa: F401
from app.models import subscription_reminder_log  # noqa: F401

from app.services import gex_scheduler as gex_scheduler_module  # ★ GEX scheduler
from app.services.gex_scheduler import GexScheduler
from app.services.subscription_scheduler import SubscriptionScheduler  # ★ Subscription scheduler

settings = get_settings()


def seed_app_settings():
    from app.models.app_setting import AppSetting
    db = SessionLocal()
    try:
        existing = db.query(AppSetting).filter(AppSetting.key == "latest_version").first()
        if not existing:
            db.add(AppSetting(key="latest_version", value="1.0.1"))

        existing_url = db.query(AppSetting).filter(AppSetting.key == "download_url").first()
        if not existing_url:
            db.add(AppSetting(key="download_url", value="https://optionspayofftracker.com/download"))

        existing_landing = db.query(AppSetting).filter(AppSetting.key == "landing_url").first()
        if not existing_landing:
            db.add(AppSetting(key="landing_url", value="https://optionspayofftracker.com/pricing"))

        db.commit()
    except Exception as e:
        print(f"[Seed] Error seeding app_settings: {e}")
        db.rollback()
    finally:
        db.close()


def ensure_schema_columns():
    """Migrazioni leggere: aggiunge colonne nuove a tabelle esistenti che
    Base.metadata.create_all() non sa gestire (create_all crea solo tabelle
    nuove, non altera quelle che già esistono).
    Idempotente grazie a `ADD COLUMN IF NOT EXISTS`.
    """
    from sqlalchemy import text
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_processed_expiry TIMESTAMP WITH TIME ZONE",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                print(f"[Schema] Errore eseguendo '{stmt}': {e}")


def backfill_subscription_tracking_once():
    """Al primo avvio dopo l'introduzione del subscription_scheduler, allinea
    last_processed_expiry = subscription_expiry per tutti gli utenti già
    presenti, così il primo giro dello scheduler non trigghera l'email
    "pagamento ricevuto" per pagamenti vecchi.
    Gated da una flag in app_settings: gira una sola volta nella vita del DB.
    """
    from app.models.app_setting import AppSetting
    from app.models.user import User
    db = SessionLocal()
    try:
        flag = db.query(AppSetting).filter(
            AppSetting.key == "subscription_tracking_initialized"
        ).first()
        if flag is not None:
            return  # Già fatto

        updated = (
            db.query(User)
            .filter(
                User.subscription_expiry.is_not(None),
                User.last_processed_expiry.is_(None),
            )
            .update(
                {User.last_processed_expiry: User.subscription_expiry},
                synchronize_session=False,
            )
        )
        db.add(AppSetting(key="subscription_tracking_initialized", value="true"))
        db.commit()
        print(f"[Subscription] Backfill iniziale: allineati {updated} utenti")
    except Exception as e:
        print(f"[Subscription] Errore backfill iniziale: {e}")
        db.rollback()
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Backend API for Options Payoff Tracker",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(account_router, prefix="/api/v1")
    app.include_router(strategy_router, prefix="/api/v1")
    app.include_router(trade_router, prefix="/api/v1")
    app.include_router(preference_router, prefix="/api/v1")
    app.include_router(tastytrade_router, prefix="/api/v1")
    app.include_router(app_info_router, prefix="/api/v1")
    app.include_router(stripe_router, prefix="/api/v1")
    app.include_router(gex_router, prefix="/api/v1")  # ★ GEX
    app.include_router(contact_router, prefix="/api/v1")  # ★ Chat contatto

    # ★ Subscription scheduler: tenuto in chiusura nel scope di create_app
    # così l'handler di shutdown lo trova.
    subscription_scheduler_holder: dict = {"instance": None}

    @app.on_event("startup")
    def on_startup():
        # Crea tutte le tabelle (inclusa la nuova gex_data)
        Base.metadata.create_all(bind=engine)
        # ★ Aggiunge colonne nuove a tabelle pre-esistenti (create_all non lo fa)
        ensure_schema_columns()
        seed_app_settings()

        # ★ Allinea last_processed_expiry per gli utenti pre-esistenti, una volta
        backfill_subscription_tracking_once()

        # ★ Avvia lo scheduler GEX (idempotente: se già avviato, start() no-op)
        scheduler = GexScheduler(
            tickers=settings.gex_tickers_list,
            polygon_api_key=settings.POLYGON_API_KEY,
            rate_limit_per_minute=settings.POLYGON_RATE_LIMIT_PER_MINUTE,
            enabled=settings.GEX_ENABLED,
        )
        scheduler.start()
        gex_scheduler_module.gex_scheduler = scheduler

        # ★ Avvia lo scheduler abbonamenti (cambi scadenza + promemoria)
        sub_scheduler = SubscriptionScheduler(
            enabled=settings.SUBSCRIPTION_SCHEDULER_ENABLED,
        )
        sub_scheduler.start()
        subscription_scheduler_holder["instance"] = sub_scheduler

    @app.on_event("shutdown")
    def on_shutdown():
        # ★ Ferma gli scheduler in modo pulito
        if gex_scheduler_module.gex_scheduler is not None:
            gex_scheduler_module.gex_scheduler.shutdown()
        if subscription_scheduler_holder["instance"] is not None:
            subscription_scheduler_holder["instance"].shutdown()

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "healthy", "app": settings.APP_NAME}

    return app


app = create_app()