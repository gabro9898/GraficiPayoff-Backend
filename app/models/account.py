# ============================================================
# Percorso: app/models/account.py
# v3: separate open/close commission for options and stocks
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ★ Options commissions
    commission_option_per_contract: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    commission_option_close_per_contract: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # ★ Stock commissions
    commission_stock_type: Mapped[str] = mapped_column(String(20), default="per_order", nullable=False)
    commission_stock_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    commission_stock_close_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="accounts")
    strategies: Mapped[list["Strategy"]] = relationship(
        "Strategy", back_populates="account", cascade="all, delete-orphan"
    )