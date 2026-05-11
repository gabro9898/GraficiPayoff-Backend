# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/repositories/email_verification_repository.py
#
# Pattern copiato da password_reset_repository.py.
# ============================================================

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.email_verification import EmailVerificationToken


class EmailVerificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, token: EmailVerificationToken) -> EmailVerificationToken:
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def find_active_by_user(self, user_id: str) -> EmailVerificationToken | None:
        """Ultimo token attivo (non usato, non scaduto) di un utente."""
        return (
            self.db.query(EmailVerificationToken)
            .filter(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at > datetime.now(timezone.utc),
            )
            .order_by(EmailVerificationToken.created_at.desc())
            .first()
        )

    def find_latest_by_user(self, user_id: str) -> EmailVerificationToken | None:
        """Ultimo token (anche scaduto/usato) — usato per il rate limit del resend."""
        return (
            self.db.query(EmailVerificationToken)
            .filter(EmailVerificationToken.user_id == user_id)
            .order_by(EmailVerificationToken.created_at.desc())
            .first()
        )

    def invalidate_active_for_user(self, user_id: str) -> None:
        """Marca come usati tutti i token attivi di un utente.
        Usato quando se ne genera uno nuovo o quando la verifica è completata.
        """
        now = datetime.now(timezone.utc)
        self.db.query(EmailVerificationToken).filter(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.used_at.is_(None),
        ).update({EmailVerificationToken.used_at: now}, synchronize_session=False)
        self.db.commit()

    def mark_used(self, token: EmailVerificationToken) -> None:
        token.used_at = datetime.now(timezone.utc)
        self.db.commit()
