"""
Rotas de gestao de usuarios (Fase 13). Admin only + CSRF em mutantes.

- GET  /api/admin/users
- POST /api/admin/users
- PUT  /api/admin/users/{id}
- POST /api/admin/users/{id}/change-password
- POST /api/admin/users/{id}/toggle-active
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin, require_csrf
from app.models import User
from app.schemas import (
    UserChangePasswordIn,
    UserCreateIn,
    UserManageOut,
    UserToggleActiveIn,
    UserUpdateIn,
)
from app.services import user_service
from app.services.user_service import UserError


router = APIRouter(prefix="/api/admin/users", tags=["users"])


def _to_out(u: User) -> UserManageOut:
    return UserManageOut(
        id=u.id,
        name=u.name,
        username=u.username,
        role=u.role,  # type: ignore[arg-type]
        active=u.active,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
    )


@router.get("", response_model=list[UserManageOut])
def list_users_endpoint(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserManageOut]:
    return [_to_out(u) for u in user_service.list_users(db)]


@router.post(
    "",
    response_model=UserManageOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_user_endpoint(
    payload: UserCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserManageOut:
    try:
        u = user_service.create_user(
            db,
            actor=actor,
            name=payload.name,
            username=payload.username,
            password=payload.password,
            role=payload.role,
        )
    except UserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _to_out(u)


@router.put(
    "/{user_id}",
    response_model=UserManageOut,
    dependencies=[Depends(require_csrf)],
)
def update_user_endpoint(
    user_id: int,
    payload: UserUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserManageOut:
    try:
        u = user_service.update_user(
            db,
            actor=actor,
            target_id=user_id,
            name=payload.name,
            role=payload.role,
        )
    except UserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _to_out(u)


@router.post(
    "/{user_id}/change-password",
    response_model=UserManageOut,
    dependencies=[Depends(require_csrf)],
)
def change_password_endpoint(
    user_id: int,
    payload: UserChangePasswordIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserManageOut:
    try:
        u = user_service.change_password(
            db,
            actor=actor,
            target_id=user_id,
            new_password=payload.new_password,
        )
    except UserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _to_out(u)


@router.post(
    "/{user_id}/toggle-active",
    response_model=UserManageOut,
    dependencies=[Depends(require_csrf)],
)
def toggle_active_endpoint(
    user_id: int,
    payload: UserToggleActiveIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserManageOut:
    try:
        u = user_service.toggle_active(
            db,
            actor=actor,
            target_id=user_id,
            active=payload.active,
        )
    except UserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _to_out(u)
