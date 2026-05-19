# ============================================================
# Percorso: app/api/routes/strategy_template.py
# Endpoint REST per i preset di strategia precompilati.
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.strategy_template_controller import StrategyTemplateController
from app.schemas.strategy_template import (
    StrategyTemplateCreateRequest,
    StrategyTemplateUpdateRequest,
    StrategyTemplateResponse,
)

router = APIRouter(prefix="/strategy-templates", tags=["StrategyTemplates"])


@router.get("/", response_model=list[StrategyTemplateResponse])
def get_all_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyTemplateController(db)
    return controller.get_all(current_user)


@router.get("/{template_id}", response_model=StrategyTemplateResponse)
def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyTemplateController(db)
    return controller.get_by_id(template_id, current_user)


@router.post("/", response_model=StrategyTemplateResponse, status_code=201)
def create_template(
    data: StrategyTemplateCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyTemplateController(db)
    return controller.create(current_user, data)


@router.put("/{template_id}", response_model=StrategyTemplateResponse)
def update_template(
    template_id: str,
    data: StrategyTemplateUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyTemplateController(db)
    return controller.update(template_id, current_user, data)


@router.delete("/{template_id}")
def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = StrategyTemplateController(db)
    return controller.delete(template_id, current_user)
