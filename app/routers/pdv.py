"""
Rotas publicas do PDV (Fase 18). Nao exigem login.

Modelo: o PDV abre direto sem senha. Operador se identifica num
dropdown no topo da tela. O backend persiste a escolha num cookie
`operator_id` nao-assinado (so o id). Vendas criadas pelo PDV usam
esse id como autor.

CUIDADO: cookie nao-assinado implica que QUALQUER acesso fisico ao
PC pode fingir ser qualquer operador. Decisao do dono (CLAUDE.md):
PDV sem senha. Auditoria continua gravando o operador escolhido.

Operacoes sensiveis (/products CRUD, /admin/*, /api/admin/*)
continuam exigindo login real.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User


OPERATOR_COOKIE = "operator_id"
OPERATOR_COOKIE_MAX_AGE = 12 * 3600  # 12h (um turno)


router = APIRouter(prefix="/api/pdv", tags=["pdv-public"])


class OperatorOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: int
    name: str
    username: str
    role: str


class OperatorSelectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_id: int = Field(..., ge=1)


class OperatorCurrentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator: Optional[OperatorOut] = None


def get_pdv_operator(
    operator_id: Optional[str] = Cookie(default=None, alias=OPERATOR_COOKIE),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Resolve o operador do PDV pelo cookie. Retorna None se nao houver
    cookie ou id invalido. Nao lanca - PDV precisa decidir o que fazer.
    """
    if not operator_id:
        return None
    try:
        uid = int(operator_id)
    except (TypeError, ValueError):
        return None
    user = db.get(User, uid)
    if user is None or not user.active:
        return None
    return user


def require_pdv_operator(
    user: Optional[User] = Depends(get_pdv_operator),
) -> User:
    """Mesma coisa mas obriga - erro 401 se vazio."""
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Nenhum operador selecionado no PDV.",
        )
    return user


# ---------- endpoints ----------


@router.get("/operators", response_model=list[OperatorOut])
def list_operators(db: Session = Depends(get_db)) -> list[OperatorOut]:
    """Lista operadores ativos para o dropdown do PDV. Publico."""
    rows = db.execute(
        select(User).where(User.active.is_(True)).order_by(User.name)
    ).scalars().all()
    return [
        OperatorOut(id=u.id, name=u.name, username=u.username, role=u.role)
        for u in rows
    ]


@router.post("/select-operator", response_model=OperatorCurrentOut)
def select_operator(
    payload: OperatorSelectIn,
    response: Response,
    db: Session = Depends(get_db),
) -> OperatorCurrentOut:
    """
    Seta o cookie operator_id. Nao exige senha - CLAUDE.md define
    PDV como "sem senha". Operador escolhe quem e no dropdown.
    """
    user = db.get(User, payload.operator_id)
    if user is None or not user.active:
        raise HTTPException(status_code=404, detail="Operador nao encontrado ou inativo.")
    response.set_cookie(
        OPERATOR_COOKIE,
        str(user.id),
        max_age=OPERATOR_COOKIE_MAX_AGE,
        httponly=False,  # UI precisa ler pra mostrar o nome; nao e segredo
        samesite="strict",
        secure=False,  # local http
    )
    return OperatorCurrentOut(
        operator=OperatorOut(
            id=user.id, name=user.name, username=user.username, role=user.role
        )
    )


@router.get("/current-operator", response_model=OperatorCurrentOut)
def current_operator(
    user: Optional[User] = Depends(get_pdv_operator),
) -> OperatorCurrentOut:
    if user is None:
        return OperatorCurrentOut(operator=None)
    return OperatorCurrentOut(
        operator=OperatorOut(
            id=user.id, name=user.name, username=user.username, role=user.role
        )
    )
