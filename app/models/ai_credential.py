# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/models/ai_credential.py
# Chiave del fornitore IA (Anthropic, OpenAI, ...) registrata dall'utente,
# CIFRATA A RIPOSO con Fernet. Un record per utente e per fornitore.
#
# REGOLE DI QUESTA TABELLA:
#  - `api_key_enc` contiene SOLO il ciphertext: la chiave in chiaro non viene
#    mai scritta, mai restituita da una rotta, mai messa in un log.
#  - `key_hint` sono le ULTIME 4 cifre, e servono unicamente a far riconoscere
#    all'utente quale chiave ha registrato. Non e un segreto e non basta a
#    ricostruire nulla.
#  - Nessuna `relationship` verso `User`: la aggiungerebbe una modifica a
#    app/models/user.py, file che questo lavoro non possiede. La FK con
#    ON DELETE CASCADE basta a non lasciare credenziali orfane.
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiCredential(Base):
    __tablename__ = "ai_credentials"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Identificativo del catalogo condiviso col frontend: "anthropic", "openai",
    # "deepseek", "perplexity", "openrouter", "groq".
    provider_id: Mapped[str] = mapped_column(String(32), nullable=False)

    # Chiave del fornitore cifrata (Fernet). Mai in chiaro.
    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False)

    # Ultime 4 cifre, in chiaro, solo per riconoscimento visivo.
    key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Una sola chiave per utente e per fornitore: registrarne un'altra sostituisce.
    __table_args__ = (
        UniqueConstraint("user_id", "provider_id", name="uq_user_ai_provider"),
    )
