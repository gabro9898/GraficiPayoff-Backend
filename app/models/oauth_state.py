# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/models/oauth_state.py
# State CSRF OAuth2 persistito su Postgres: sopravvive a restart
# e funziona con N worker uvicorn/gunicorn su Render.
# ============================================================

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class OAuthState(Base):
    __tablename__ = "oauth_states"

    # state random a 32 byte (secrets.token_urlsafe → ~43 char) — PK diretta
    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Quale broker ha iniziato il flow (oggi solo "tastytrade", domani potrebbero esserci altri)
    broker_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
