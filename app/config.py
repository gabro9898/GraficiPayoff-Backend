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
    # NB: qui c'era un campo DEBUG mai letto da nessuno — una manopola finta.
    # Rimosso: il backend non ha una configurazione del logging da governare
    # (nessun basicConfig, nessun log_level), quindi non c'era niente a cui
    # collegarlo. La riga DEBUG=true eventualmente rimasta nei .env viene
    # ignorata senza errori grazie a extra="ignore" (vedi class Config).
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
        # ★ Chiavi in .env che qui non hanno un campo: si ignorano.
        #
        # NON è un dettaglio di gusto. Il default di pydantic-settings è
        # extra="forbid", e con quello UNA SOLA riga di troppo nel .env fa
        # fallire la costruzione di Settings — cioè impedisce all'app di
        # partire, con un ValidationError che nomina il campo ma non spiega
        # che basta cancellare la riga.
        #
        # È successo davvero rimuovendo il relay IA (luglio 2026): tolto il
        # campo AI_ENCRYPTION_KEY da questa classe, il .env che lo conteneva
        # ancora ha bloccato l'avvio. I file .env vivono più a lungo del
        # codice che li legge e nessuno li ripulisce in fretta: tollerare le
        # chiavi orfane è l'unico comportamento che regge un'eliminazione.
        #
        # Il prezzo: un refuso in .env (es. POLIGON_API_KEY) non dà più
        # errore, viene semplicemente ignorato e il campo resta al default.
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()