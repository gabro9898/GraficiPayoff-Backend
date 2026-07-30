# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/repositories/ai_credential.py
# Accesso alla tabella `ai_credentials`. Stessa forma degli altri repository
# del progetto (vedi broker_token_repository.py): costruttore con la Session,
# metodi che fanno commit e ritornano l'entita.
#
# NOTA sul nome del file: gli altri repository si chiamano `*_repository.py`.
# Questo file conserva il nome assegnato dal compito (`ai_credential.py`)
# perche il perimetro dei file da scrivere era vincolante; la classe invece
# segue la convenzione del progetto (`AiCredentialRepository`).
#
# QUI DENTRO NON SI DECIFRA NULLA: il repository muove ciphertext. La
# cifratura vive in app/services/ai_relay.py, dove sta anche la chiave.
# ============================================================

from sqlalchemy.orm import Session

from app.models.ai_credential import AiCredential


class AiCredentialRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_user_and_provider(self, user_id: str, provider_id: str) -> AiCredential | None:
        return (
            self.db.query(AiCredential)
            .filter(
                AiCredential.user_id == user_id,
                AiCredential.provider_id == provider_id,
            )
            .first()
        )

    def list_by_user(self, user_id: str) -> list[AiCredential]:
        return (
            self.db.query(AiCredential)
            .filter(AiCredential.user_id == user_id)
            .order_by(AiCredential.provider_id)
            .all()
        )

    def upsert(
        self,
        user_id: str,
        provider_id: str,
        api_key_enc: str,
        key_hint: str | None,
    ) -> AiCredential:
        """Registra o sostituisce la chiave cifrata per un utente+fornitore."""
        credential = self.find_by_user_and_provider(user_id, provider_id)
        if credential:
            credential.api_key_enc = api_key_enc
            credential.key_hint = key_hint
        else:
            credential = AiCredential(
                user_id=user_id,
                provider_id=provider_id,
                api_key_enc=api_key_enc,
                key_hint=key_hint,
            )
            self.db.add(credential)
        self.db.commit()
        self.db.refresh(credential)
        return credential

    def delete_by_user_and_provider(self, user_id: str, provider_id: str) -> bool:
        """Revoca la chiave. Ritorna False se non ce n'era una da revocare."""
        credential = self.find_by_user_and_provider(user_id, provider_id)
        if credential:
            self.db.delete(credential)
            self.db.commit()
            return True
        return False
