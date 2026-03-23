# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/config.py
# v4: fix tastytrade_auth_url per OAuth login page
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
    APP_NAME: str = "Options Payoff Tracker"
    DEBUG: bool = True

    # ★ TastyTrade OAuth2
    TASTYTRADE_CLIENT_ID: str = ""
    TASTYTRADE_CLIENT_SECRET: str = ""
    TASTYTRADE_REDIRECT_URI: str = "http://localhost:8000/api/v1/tastytrade/callback"
    TASTYTRADE_SANDBOX: bool = True  # True = sandbox, False = production

    # ★ Encryption key per token storage (Fernet, 32 bytes base64)
    TOKEN_ENCRYPTION_KEY: str = ""

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

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()