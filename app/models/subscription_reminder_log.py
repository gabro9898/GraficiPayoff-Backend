# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/models/subscription_reminder_log.py
#
# Tiene traccia dei promemoria di scadenza già spediti, così non li
# duplichiamo. Una riga per ogni (utente, scadenza, giorni-prima).
# La chiave logica è (user_id, expiry_at, days_before): se la scadenza
# cambia (rinnovo), le vecchie righe non matchano la nuova data e i
# promemoria ripartono freschi per il nuovo ciclo.
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubscriptionReminderLog(Base):
    __tablename__ = "subscription_reminder_log"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "expiry_at", "days_before",
            name="uq_subscription_reminder_log_user_expiry_days",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Data di scadenza dell'abbonamento al momento dell'invio. Identifica il
    # "ciclo" di abbonamento per cui il promemoria è stato spedito.
    expiry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Giorni di anticipo del promemoria: 7, 3, 2, 1.
    days_before: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
