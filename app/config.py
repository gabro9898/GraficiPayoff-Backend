# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/config.py
# v6: + GEX / Polygon settings
# ============================================================

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/options_tracker"

    # JWT
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # App
    APP_NAME: str = "Option Tracker"
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173,app://."

    # TastyTrade OAuth2
    TASTYTRADE_CLIENT_ID: str = ""
    TASTYTRADE_CLIENT_SECRET: str = ""
    TASTYTRADE_REDIRECT_URI: str = "http://localhost:8000/api/v1/tastytrade/callback"
    TASTYTRADE_SANDBOX: bool = True

    # Encryption key per token storage
    TOKEN_ENCRYPTION_KEY: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PRICE_MONTHLY: str = ""
    STRIPE_PRICE_ANNUAL: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:5173"

    # ★ GEX / Polygon
    POLYGON_API_KEY: str = ""
    # 5/min = piano free. Imposta 0 per disattivare il rate limit (piano Starter/Developer).
    POLYGON_RATE_LIMIT_PER_MINUTE: int = 5
    # Lista ticker (comma-separated) aggiornati dallo scheduler giornaliero.
    # Per ora solo SPX; domani aggiungerai SPY, QQQ, ecc.
    GEX_TICKERS: str = "SPX"
    # Flag per disattivare completamente lo scheduler (utile in locale)
    GEX_ENABLED: bool = True

    # ★ Brevo (email transazionali)
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = "noreply@mailoptiontracker.optiontraders.it"
    BREVO_SENDER_NAME: str = "Option Tracker"
    BREVO_REPLY_TO: str = "gabriele.murru@optiontraders.it"

    # ★ Subscription scheduler
    # URL a cui mandiamo gli utenti per rinnovare l'abbonamento.
    SUBSCRIPTION_RENEWAL_URL: str = "https://optiontracker.optiontraders.it/dashboard"
    # Flag per disattivare lo scheduler (utile in locale o in test)
    SUBSCRIPTION_SCHEDULER_ENABLED: bool = True

    # ★ Email verification
    # Base URL del landing — usata per costruire il link di verifica email.
    # Il link finale sarà: {LANDING_URL}/verify-email?token=...
    LANDING_URL: str = "https://optiontracker.optiontraders.it"

    # ★ Assistente IA — relay verso i fornitori di modelli
    #   (rotte in app/api/routes/ai.py, inoltro in app/services/ai_relay.py)
    #
    # Interruttore generale: a False le rotte /ai/chat e /ai/count-tokens
    # rispondono 503 con un messaggio esplicito. /ai/health continua a
    # rispondere, così il frontend distingue "relay spento" da "relay assente".
    AI_RELAY_ENABLED: bool = True
    # Chiave Fernet usata per cifrare A RIPOSO le chiavi dei fornitori.
    # DEFAULT VUOTO DI PROPOSITO: non è un segreto vero e non deve esserlo.
    # Finché resta vuoto, /ai/credential fallisce con 503 e un messaggio che
    # dice cosa manca — mai una cifratura con chiave effimera, che sparirebbe
    # al riavvio lasciando in tabella ciphertext indecifrabili.
    # Generare con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    AI_ENCRYPTION_KEY: str = ""
    # Tetto per utente sulle chiamate al relay (sintassi slowapi/limits).
    AI_RELAY_RATE_LIMIT: str = "30/minute"
    # Silenzio massimo tollerato dal fornitore fra due pezzi dello stream.
    # Il frontend si arrende a 90 s (AI_STREAM_IDLE_TIMEOUT_MS): qui sta più
    # largo, così a chiudere è il client e non il relay.
    AI_RELAY_READ_TIMEOUT_SECONDS: float = 120.0

    @property
    def tastytrade_base_url(self) -> str:
        if self.TASTYTRADE_SANDBOX:
            return "https://api.cert.tastyworks.com"
        return "https://api.tastyworks.com"

    @property
    def tastytrade_auth_url(self) -> str:
        if self.TASTYTRADE_SANDBOX:
            return "https://my.cert.tastyworks.com"
        return "https://my.tastytrade.com"

    @property
    def gex_tickers_list(self) -> list[str]:
        """Lista dei ticker da aggiornare, parsata da GEX_TICKERS."""
        return [t.strip().upper() for t in self.GEX_TICKERS.split(",") if t.strip()]

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()