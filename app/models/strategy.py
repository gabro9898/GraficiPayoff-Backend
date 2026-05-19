# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/models/strategy.py
# v4: + status="MODEL" (strategie disegnate ma non ancora fillate)
#     + parent_strategy_id (model annidato dentro una strategia OPEN)
# v3: + earliest_expiry
# ============================================================

import uuid
from datetime import datetime, timezone, date
from sqlalchemy import String, DateTime, Text, Float, Integer, Date, ForeignKey
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
    # ★ v4: valori ammessi → "OPEN", "CLOSED", "MODEL"
    status: Mapped[str] = mapped_column(String(10), default="OPEN", nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    contract_multiplier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # ★ Scadenza più vicina tra i trades aperti
    earliest_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    underlying_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ★ v4: per i model annidati dentro una strategia OPEN già fillata.
    # NULL = model "free-standing" o strategia normale OPEN/CLOSED.
    parent_strategy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
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

    # ★ v15: `pending_count` viene iniettato dal repository via setattr() dopo
    # la query (non è una colonna del DB, non è una @property — è un instance
    # attribute popolato in memoria). Pydantic con from_attributes=True legge
    # comunque `getattr(obj, 'pending_count', 0)` → funziona.