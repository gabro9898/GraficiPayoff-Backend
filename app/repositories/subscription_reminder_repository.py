# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/repositories/subscription_reminder_repository.py
# ============================================================

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.subscription_reminder_log import SubscriptionReminderLog


class SubscriptionReminderRepository:
    def __init__(self, db: Session):
        self.db = db

    def has_been_sent(self, user_id: str, expiry_at: datetime, days_before: int) -> bool:
        return (
            self.db.query(SubscriptionReminderLog)
            .filter(
                SubscriptionReminderLog.user_id == user_id,
                SubscriptionReminderLog.expiry_at == expiry_at,
                SubscriptionReminderLog.days_before == days_before,
            )
            .first()
            is not None
        )

    def record_sent(self, user_id: str, expiry_at: datetime, days_before: int) -> None:
        log = SubscriptionReminderLog(
            user_id=user_id,
            expiry_at=expiry_at,
            days_before=days_before,
        )
        self.db.add(log)
        self.db.commit()
