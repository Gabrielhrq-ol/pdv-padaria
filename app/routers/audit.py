"""
Visualizacao do audit_log pela UI (Fase 16). Admin only.

Audit log cresce muito (toda acao sensivel grava). Esta rota expoe
leitura filtrada pra admin investigar incidentes (quem fez sangria,
quem alterou preco, quem resetou senha etc).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin
from app.models import AuditLog, User
from app.schemas import AuditLogRowOut


router = APIRouter(prefix="/api/admin/audit-log", tags=["audit"])


@router.get("", response_model=list[AuditLogRowOut])
def list_audit(
    action: Optional[str] = Query(default=None, max_length=60),
    user_id: Optional[int] = Query(default=None, ge=1),
    entity: Optional[str] = Query(default=None, max_length=40),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AuditLogRowOut]:
    """
    Lista audit log. Join com User pra pegar o nome do autor.
    Ordem: created_at DESC (mais recente primeiro).
    """
    stmt = (
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if entity is not None:
        stmt = stmt.where(AuditLog.entity == entity)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    stmt = stmt.limit(limit).offset(offset)

    out: list[AuditLogRowOut] = []
    for a, u in db.execute(stmt).all():
        out.append(
            AuditLogRowOut(
                id=a.id,
                created_at=a.created_at,
                user_id=a.user_id,
                user_name=u.name if u else None,
                action=a.action,
                entity=a.entity,
                entity_id=a.entity_id,
                details=a.details,
                ip=a.ip,
            )
        )
    return out


@router.get("/actions", response_model=list[str])
def list_distinct_actions(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[str]:
    """Lista distinct de acoes pro combobox de filtro."""
    rows = db.execute(
        select(distinct(AuditLog.action)).order_by(AuditLog.action)
    ).all()
    return [r[0] for r in rows if r[0]]
