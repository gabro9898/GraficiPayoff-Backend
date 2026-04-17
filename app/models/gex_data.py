# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/models/gex_data.py
# Tabella che contiene i dati OI+IV per calcolo GEX.
# Una riga per ogni (ticker, expiry, strike).
# Ricaricata interamente ogni giorno dallo scheduler.
# ============================================================

import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, Float, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class GexData(Base):
    __tablename__ = "gex_data"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ★ Identificativi
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)

    # ★ Open Interest
    oi_call: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    oi_put: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ★ Implied Volatility (può essere null se Polygon non la ritorna per quel contratto)
    iv_call: Mapped[float | None] = mapped_column(Float, nullable=True)
    iv_put: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ★ Timestamp del fetch da Polygon — usato per flag is_previous_session
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # ★ Una sola riga per combinazione ticker+expiry+strike
    __table_args__ = (
        UniqueConstraint("ticker", "expiry", "strike", name="uq_gex_ticker_expiry_strike"),
        Index("ix_gex_ticker_expiry", "ticker", "expiry"),
    )