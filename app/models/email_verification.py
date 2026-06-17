# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/models/email_verification.py
#
# Tabella che ospita i token di verifica email per la registrazione.
# Il token viene inviato in chiaro all'utente via link nell'email, ma sul DB
# salviamo solo l'hash (stesso meccanismo delle password e dei reset OTP).
#
# Pattern copiato da password_reset.py.
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # ★ Audit 2026-05-23: index=True su token_hash per O(1) lookup.
    # Prima verify_email scannava tutti i token attivi e faceva bcrypt-verify
    # uno per uno — O(N) e vettore di DoS CPU. Ora si usa SHA-256 e si
    # cerca direttamente sul hash indicizzato.
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None
