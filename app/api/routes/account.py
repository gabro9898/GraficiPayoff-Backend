# ============================================================
# NUOVO FILE
# Percorso: app/api/routes/account.py
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.controllers.account_controller import AccountController
from app.schemas.account import (
    AccountCreateRequest,
    AccountUpdateRequest,
    AccountResponse,
    AccountWithStrategiesResponse,
)

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/", response_model=list[AccountResponse])
def get_all_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = AccountController(db)
    return controller.get_all(current_user)


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = AccountController(db)
    return controller.get_by_id(account_id, current_user)


@router.get("/{account_id}/details", response_model=AccountWithStrategiesResponse)
def get_account_with_strategies(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = AccountController(db)
    return controller.get_with_strategies(account_id, current_user)


@router.post("/", response_model=AccountResponse, status_code=201)
def create_account(
    data: AccountCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = AccountController(db)
    return controller.create(current_user, data)


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: str,
    data: AccountUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = AccountController(db)
    return controller.update(account_id, current_user, data)


@router.delete("/{account_id}")
def delete_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    controller = AccountController(db)
    return controller.delete(account_id, current_user)