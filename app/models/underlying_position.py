# ============================================================
# Percorso: app/models/underlying_position.py
# v3: + commission (open) + close_commission
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, Integer, Boolean, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class UPDirection(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class UPStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class UnderlyingPosition(Base):
    __tablename__ = "underlying_positions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[UPDirection] = mapped_column(SAEnum(UPDirection), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[UPStatus] = mapped_column(SAEnum(UPStatus), default=UPStatus.OPEN, nullable=False)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ★ Commissions
    commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    close_commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="underlying_positions")

    @property
    def pnl(self) -> float | None:
        if self.close_price is None:
            return None
        mult = 1 if self.direction == UPDirection.BUY else -1
        return (self.close_price - self.entry_price) * mult * self.quantity * self.multiplier