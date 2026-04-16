# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/models/user_preference.py
# v5: + strike_mode
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # ★ Layout
    ticker: Mapped[str] = mapped_column(String(20), default="SPX", nullable=False)
    left_width: Mapped[float] = mapped_column(Float, default=450.0, nullable=False)
    center_width: Mapped[float] = mapped_column(Float, default=280.0, nullable=False)
    chain_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sidebar_collapsed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    compare_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ★ Payoff chart settings — JSON come testo
    payoff_settings: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ★ Tema UI (dark, light, etc.)
    theme: Mapped[str] = mapped_column(String(32), default="dark", nullable=False)

    # ★ Broker preferito (ib, tastytrade, ecc.)
    broker: Mapped[str] = mapped_column(String(32), default="ib", nullable=False)

    # ★ v5: Strike mode (all-fast, all-normal, 32, 24, 16, 8, 4, 2)
    strike_mode: Mapped[str] = mapped_column(String(20), default="all-fast", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="preferences")