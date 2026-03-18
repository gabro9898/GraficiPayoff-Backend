# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/models/strategy.py
# Aggiunto: realized_pnl
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    settlement_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="OPEN", nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="strategies")
    account: Mapped["Account"] = relationship("Account", back_populates="strategies")
    trades: Mapped[list["Trade"]] = relationship(
        "Trade", back_populates="strategy", cascade="all, delete-orphan"
    )
    underlying_positions: Mapped[list["UnderlyingPosition"]] = relationship(
        "UnderlyingPosition", back_populates="strategy", cascade="all, delete-orphan"
    )