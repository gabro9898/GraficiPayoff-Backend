# ============================================================
# Percorso: app/models/strategy_template.py
# Preset precompilati di strategie. L'utente definisce parametri
# astratti (delta target, DTE target, offset, linked) e poi
# "applica" il preset: il frontend risolve gli strike via BS +
# snapshot IB e popola lo StrategyBuilder.
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class StrategyTemplate(Base):
    __tablename__ = "strategy_templates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    legs: Mapped[list["StrategyTemplateLeg"]] = relationship(
        "StrategyTemplateLeg",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="StrategyTemplateLeg.leg_index",
    )


class StrategyTemplateLeg(Base):
    __tablename__ = "strategy_template_legs"
    __table_args__ = (
        UniqueConstraint("template_id", "leg_index", name="uq_template_leg_idx"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategy_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    leg_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Tipo e direzione opzione ---
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # 'CALL' | 'PUT'
    direction: Mapped[str] = mapped_column(String(4), nullable=False)    # 'BUY'  | 'SELL'
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- Scadenza target ---
    # expiry_days = giorni desiderati a scadenza (es. 45)
    # expiry_match = 'EXACT' (deve essere quel DTE) o 'NEAREST' (più vicino disponibile)
    expiry_days: Mapped[int] = mapped_column(Integer, nullable=False)
    expiry_match: Mapped[str] = mapped_column(String(8), nullable=False, default="NEAREST")

    # --- Modalità di scelta strike ---
    # strike_mode: 'DELTA' | 'OFFSET' | 'LINKED' | 'PREMIUM'
    strike_mode: Mapped[str] = mapped_column(String(8), nullable=False)

    # Mode DELTA: target_delta in [0, 1] (es. 0.30 = "delta 30")
    # delta_match: 'EXACT' o 'NEAREST'
    target_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_match: Mapped[str | None] = mapped_column(String(8), nullable=True, default="NEAREST")

    # Mode OFFSET: target_offset = punti rispetto allo SPOT corrente
    # (es. +100 = strike 100pt sopra spot, -50 = 50pt sotto)
    target_offset: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Mode LINKED: linked_leg_index = riferimento a leg_index precedente
    # (es. calendar: la leg 1 usa lo stesso strike risolto della leg 0)
    linked_leg_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # linked_offset = punti da aggiungere allo strike della leg linkata
    # (es. +20 = 20pt sopra, -10 = 10pt sotto; 0 = stesso strike).
    # Lo strike risultante viene poi arrotondato a quello disponibile più vicino.
    linked_offset: Mapped[float | None] = mapped_column(Float, nullable=True, default=0)

    # Mode PREMIUM: target_premium = valore (mid) target dell'opzione.
    # - Standalone: cerca lo strike il cui mid è più vicino a target_premium
    #   (es. 5.0 = "l'opzione che costa ~5$").
    # - Linked (linked_leg_index valorizzato): cerca lo strike il cui mid è
    #   più vicino a (mid_della_leg_linkata + target_premium). In questo caso
    #   target_premium è un OFFSET di premio (es. -2.0 = "2$ più economica
    #   della leg #N", +3.0 = "3$ più costosa").
    target_premium: Mapped[float | None] = mapped_column(Float, nullable=True)

    template: Mapped["StrategyTemplate"] = relationship("StrategyTemplate", back_populates="legs")
