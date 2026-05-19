# ============================================================
# Percorso: app/services/strategy_template_service.py
# Business logic per i preset di strategia precompilati.
# ============================================================

from sqlalchemy.orm import Session
from app.models.strategy_template import StrategyTemplate, StrategyTemplateLeg
from app.repositories.strategy_template_repository import StrategyTemplateRepository
from app.schemas.strategy_template import (
    StrategyTemplateCreateRequest,
    StrategyTemplateUpdateRequest,
    StrategyTemplateLegInput,
)
from app.utils.exceptions import NotFoundException, ForbiddenException


class StrategyTemplateService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = StrategyTemplateRepository(db)

    def _verify_owner(self, template: StrategyTemplate, user_id: str) -> None:
        if template.user_id != user_id:
            raise ForbiddenException()

    @staticmethod
    def _make_leg(template_id: str, leg: StrategyTemplateLegInput) -> StrategyTemplateLeg:
        return StrategyTemplateLeg(
            template_id=template_id,
            leg_index=leg.leg_index,
            option_type=leg.option_type,
            direction=leg.direction,
            quantity=leg.quantity,
            expiry_days=leg.expiry_days,
            expiry_match=leg.expiry_match,
            strike_mode=leg.strike_mode,
            target_delta=leg.target_delta,
            delta_match=leg.delta_match,
            target_offset=leg.target_offset,
            linked_leg_index=leg.linked_leg_index,
            linked_offset=leg.linked_offset,
            target_premium=leg.target_premium,
        )

    def get_all(self, user_id: str) -> list[StrategyTemplate]:
        return self.repo.find_all_by_user(user_id)

    def get_by_id(self, template_id: str, user_id: str) -> StrategyTemplate:
        template = self.repo.find_by_id(template_id)
        if not template:
            raise NotFoundException("StrategyTemplate")
        self._verify_owner(template, user_id)
        return template

    def create(self, user_id: str, data: StrategyTemplateCreateRequest) -> StrategyTemplate:
        template = StrategyTemplate(
            user_id=user_id,
            name=data.name,
            description=data.description,
        )
        self.db.add(template)
        self.db.flush()
        for leg in data.legs:
            self.db.add(self._make_leg(template.id, leg))
        self.db.commit()
        self.db.refresh(template)
        return template

    def update(
        self,
        template_id: str,
        user_id: str,
        data: StrategyTemplateUpdateRequest,
    ) -> StrategyTemplate:
        template = self.get_by_id(template_id, user_id)
        if data.name is not None:
            template.name = data.name
        if data.description is not None:
            template.description = data.description
        if data.legs is not None:
            # Replace totale delle leg
            for leg in list(template.legs):
                self.db.delete(leg)
            self.db.flush()
            for leg in data.legs:
                self.db.add(self._make_leg(template.id, leg))
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete(self, template_id: str, user_id: str) -> None:
        template = self.get_by_id(template_id, user_id)
        self.repo.delete(template)
