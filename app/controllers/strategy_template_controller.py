# ============================================================
# Percorso: app/controllers/strategy_template_controller.py
# ============================================================

from sqlalchemy.orm import Session
from app.models.user import User
from app.services.strategy_template_service import StrategyTemplateService
from app.schemas.strategy_template import (
    StrategyTemplateCreateRequest,
    StrategyTemplateUpdateRequest,
    StrategyTemplateResponse,
)


class StrategyTemplateController:
    def __init__(self, db: Session):
        self.service = StrategyTemplateService(db)

    def get_all(self, current_user: User) -> list[StrategyTemplateResponse]:
        templates = self.service.get_all(current_user.id)
        return [StrategyTemplateResponse.model_validate(t) for t in templates]

    def get_by_id(self, template_id: str, current_user: User) -> StrategyTemplateResponse:
        template = self.service.get_by_id(template_id, current_user.id)
        return StrategyTemplateResponse.model_validate(template)

    def create(
        self, current_user: User, data: StrategyTemplateCreateRequest
    ) -> StrategyTemplateResponse:
        template = self.service.create(current_user.id, data)
        return StrategyTemplateResponse.model_validate(template)

    def update(
        self,
        template_id: str,
        current_user: User,
        data: StrategyTemplateUpdateRequest,
    ) -> StrategyTemplateResponse:
        template = self.service.update(template_id, current_user.id, data)
        return StrategyTemplateResponse.model_validate(template)

    def delete(self, template_id: str, current_user: User) -> dict:
        self.service.delete(template_id, current_user.id)
        return {"message": "Strategy template deleted successfully"}
