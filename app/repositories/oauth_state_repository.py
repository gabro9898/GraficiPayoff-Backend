# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/repositories/oauth_state_repository.py
# CRUD per oauth_states + cleanup TTL (10 minuti)
# ============================================================

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.oauth_state import OAuthState

# TTL: dopo 10 minuti uno state non riscattato viene considerato scaduto.
STATE_TTL_MINUTES = 10


class OAuthStateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, state: str, user_id: str, broker_id: str) -> OAuthState:
        row = OAuthState(state=state, user_id=user_id, broker_id=broker_id)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def pop(self, state: str, broker_id: str) -> OAuthState | None:
        """Recupera lo state e lo cancella in transazione (one-shot).
        Ritorna None se non esiste, è scaduto, o appartiene a un altro broker."""
        row = (
            self.db.query(OAuthState)
            .filter(OAuthState.state == state, OAuthState.broker_id == broker_id)
            .first()
        )
        if row is None:
            return None
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=STATE_TTL_MINUTES)
        # created_at salvato in UTC con tz-aware; confronto safe
        if row.created_at < cutoff:
            self.db.delete(row)
            self.db.commit()
            return None
        # State valido — lo cancello subito così non può essere riusato (replay protection)
        self.db.delete(row)
        self.db.commit()
        return row

    def cleanup_expired(self) -> int:
        """Pulisce state scaduti. Chiamata periodicamente (es. ogni get_auth_url)."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=STATE_TTL_MINUTES)
        deleted = (
            self.db.query(OAuthState)
            .filter(OAuthState.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted
