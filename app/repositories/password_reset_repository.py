# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/repositories/password_reset_repository.py
# ============================================================

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.password_reset import PasswordResetCode


class PasswordResetRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, code: PasswordResetCode) -> PasswordResetCode:
        self.db.add(code)
        self.db.commit()
        self.db.refresh(code)
        return code

    def find_active_by_user(self, user_id: str) -> PasswordResetCode | None:
        """Trova l'ultimo codice valido (non usato, non scaduto) di un utente."""
        return (
            self.db.query(PasswordResetCode)
            .filter(
                PasswordResetCode.user_id == user_id,
                PasswordResetCode.used_at.is_(None),
                PasswordResetCode.expires_at > datetime.now(timezone.utc),
            )
            .order_by(PasswordResetCode.created_at.desc())
            .first()
        )

    def invalidate_active_for_user(self, user_id: str) -> None:
        """Marca come usati tutti i codici attivi di un utente.
        Usato quando se ne genera uno nuovo o quando il reset è completato.
        """
        now = datetime.now(timezone.utc)
        self.db.query(PasswordResetCode).filter(
            PasswordResetCode.user_id == user_id,
            PasswordResetCode.used_at.is_(None),
        ).update({PasswordResetCode.used_at: now}, synchronize_session=False)
        self.db.commit()

    def increment_attempts(self, code: PasswordResetCode) -> None:
        code.attempts += 1
        self.db.commit()

    def mark_used(self, code: PasswordResetCode) -> None:
        code.used_at = datetime.now(timezone.utc)
        self.db.commit()
