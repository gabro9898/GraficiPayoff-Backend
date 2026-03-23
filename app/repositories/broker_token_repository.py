# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/repositories/broker_token_repository.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.broker_token import BrokerToken


class BrokerTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_user_and_broker(self, user_id: str, broker_id: str) -> BrokerToken | None:
        return (
            self.db.query(BrokerToken)
            .filter(BrokerToken.user_id == user_id, BrokerToken.broker_id == broker_id)
            .first()
        )

    def upsert(self, user_id: str, broker_id: str, data: dict) -> BrokerToken:
        """Crea o aggiorna il token per un user+broker."""
        token = self.find_by_user_and_broker(user_id, broker_id)
        if token:
            for key, value in data.items():
                setattr(token, key, value)
        else:
            token = BrokerToken(user_id=user_id, broker_id=broker_id, **data)
            self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def delete_by_user_and_broker(self, user_id: str, broker_id: str) -> bool:
        token = self.find_by_user_and_broker(user_id, broker_id)
        if token:
            self.db.delete(token)
            self.db.commit()
            return True
        return False