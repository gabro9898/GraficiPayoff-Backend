from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, user_id: str) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def find_by_email(self, email: str) -> User | None:
        # Confronto case-insensitive: gli schemas in entrata normalizzano già
        # l'email in lowercase, ma gli utenti storici hanno l'email salvata
        # con il case di registrazione (es. "ANTONIOGIAMMARIA@gmail.com").
        # Senza func.lower qui, quegli utenti non riuscirebbero più a loggare
        # finché non si esegue lo script SQL di normalizzazione storica.
        return (
            self.db.query(User)
            .filter(func.lower(User.email) == (email or "").lower())
            .first()
        )

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User, data: dict) -> User:
        for key, value in data.items():
            if value is not None:
                setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.commit()
