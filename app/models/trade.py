# ============================================================
# FILE AGGIORNATO — sostituisce il file esistente
# Percorso: app/models/trade.py
# ============================================================

import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, Float, Integer, Boolean, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class OptionType(str, enum.Enum):
    CALL = "CALL"
    PUT = "PUT"


class Direction(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # --- Basic option data ---
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    option_type: Mapped[OptionType] = mapped_column(SAEnum(OptionType), nullable=False)
    direction: Mapped[Direction] = mapped_column(SAEnum(Direction), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    premium: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)

    # --- Greeks (at time of trade entry) ---
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    gamma: Mapped[float | None] = mapped_column(Float, nullable=True)
    theta: Mapped[float | None] = mapped_column(Float, nullable=True)
    vega: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Market data (at time of trade entry) ---
    underlying_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    implied_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Leg state ---
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Trade metadata ---
    status: Mapped[TradeStatus] = mapped_column(
        SAEnum(TradeStatus), default=TradeStatus.OPEN, nullable=False
    )
    open_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="trades")

    @property
    def pnl(self) -> float | None:
        if self.close_premium is None:
            return None
        multiplier = 1 if self.direction == Direction.BUY else -1
        return (self.close_premium - self.premium) * multiplier * self.quantity * 100