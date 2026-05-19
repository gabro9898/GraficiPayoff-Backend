# ============================================================
# Percorso: app/repositories/strategy_template_repository.py
# ============================================================

from sqlalchemy.orm import Session, joinedload
from app.models.strategy_template import StrategyTemplate


class StrategyTemplateRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, template_id: str) -> StrategyTemplate | None:
        return (
            self.db.query(StrategyTemplate)
            .options(joinedload(StrategyTemplate.legs))
            .filter(StrategyTemplate.id == template_id)
            .first()
        )

    def find_all_by_user(self, user_id: str) -> list[StrategyTemplate]:
        return (
            self.db.query(StrategyTemplate)
            .options(joinedload(StrategyTemplate.legs))
            .filter(StrategyTemplate.user_id == user_id)
            .order_by(StrategyTemplate.created_at.desc())
            .all()
        )

    def delete(self, template: StrategyTemplate) -> None:
        self.db.delete(template)
        self.db.commit()
