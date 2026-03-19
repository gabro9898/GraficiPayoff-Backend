# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/models/user.py
# Aggiunto: preferences relationship
# ============================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    subscription_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    accounts: Mapped[list["Account"]] = relationship(
        "Account", back_populates="user", cascade="all, delete-orphan"
    )
    strategies: Mapped[list["Strategy"]] = relationship(
        "Strategy", back_populates="user", cascade="all, delete-orphan"
    )
    # ★ Preferences (one-to-one)
    preferences: Mapped["UserPreference"] = relationship(
        "UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def is_subscription_active(self) -> bool:
        if self.subscription_expiry is None:
            return False
        return self.subscription_expiry > datetime.now(timezone.utc)