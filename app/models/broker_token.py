# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/models/broker_token.py
# Storage crittografato dei token OAuth per broker esterni.
# Un record per user per broker_id.
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class BrokerToken(Base):
    __tablename__ = "broker_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    broker_id: Mapped[str] = mapped_column(
        String(32), nullable=False  # "tastytrade", "ib", ecc.
    )

    # Token crittografati (Fernet)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scadenza access token (UTC)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Metadata extra (JSON, es. account_id TastyTrade)
    metadata_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Unico token per user+broker
    __table_args__ = (
        UniqueConstraint("user_id", "broker_id", name="uq_user_broker"),
    )

    user: Mapped["User"] = relationship("User", back_populates="broker_tokens")