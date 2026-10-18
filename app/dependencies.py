"""
Dependencies de autenticacao e autorizacao do FastAPI.

- `get_current_user`: lê cookie `session`, retorna User (ou lanca 401).
- `require_admin`: exige role=admin.
- `require_authenticated`: exige qualquer usuario autenticado.
- `require_csrf`: valida double-submit CSRF em rotas mutantes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    compare_csrf_tokens,
    utc_now,
    verify_session_token,
)


# Duracao da sessao em segundos (padrao 8h). Pode virar setting no banco.
SESSION_MAX_AGE_SECONDS = 8 * 3600


def _unauth(detail: str = "Nao autenticado.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    if not session:
        raise _unauth()
    uid = verify_session_token(session, max_age_seconds=SESSION_MAX_AGE_SECONDS)
    if uid is None:
        raise _unauth("Sessao invalida ou expirada.")
    user = db.get(User, uid)
    if user is None or not user.active:
        raise _unauth("Usuario inativo ou removido.")
    # Se locked_until estiver no futuro, nega acesso mesmo com cookie valido.
    if user.locked_until is not None and user.locked_until > utc_now():
        raise HTTPException(status_code=403, detail="Conta temporariamente bloqueada.")
    return user


def require_authenticated(user: User = Depends(get_current_user)) -> User:
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Permissao de admin obrigatoria.")
    return user


def require_csrf(
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
    csrf_token: Optional[str] = Cookie(default=None, alias=CSRF_COOKIE),
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
) -> None:
    """
    Double-submit cookie: o header `X-CSRF-Token` deve bater com o cookie
    `csrf_token`. Metodos seguros (GET/HEAD/OPTIONS) nao precisam.

    Quando NAO ha sessao, deixa a dependency de autenticacao retornar 401.
    Caso contrario, cliente anonimo veria 403 (CSRF) em vez do 401 esperado.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not session:
        return  # Autenticacao vai retornar 401 em sequencia.
    if not compare_csrf_tokens(x_csrf_token, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF invalido.")


def get_optional_user(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Retorna o user autenticado ou None. Nao lanca."""
    if not session:
        return None
    uid = verify_session_token(session, max_age_seconds=SESSION_MAX_AGE_SECONDS)
    if uid is None:
        return None
    user = db.get(User, uid)
    if user is None or not user.active:
        return None
    if user.locked_until is not None and user.locked_until > utc_now():
        return None
    return user


def require_user_or_operator(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
    operator_id: Optional[str] = Cookie(default=None, alias="operator_id"),
    db: Session = Depends(get_db),
) -> User:
    """
    Fase 18: aceita OU session cookie (admin logado) OU operator_id cookie
    (operador do PDV sem login). Serve rotas do PDV que precisam saber
    quem fez a acao, mas o PDV abre sem senha.
    """
    # Tenta session primeiro
    if session:
        uid = verify_session_token(session, max_age_seconds=SESSION_MAX_AGE_SECONDS)
        if uid is not None:
            user = db.get(User, uid)
            if user is not None and user.active:
                if user.locked_until is None or user.locked_until <= utc_now():
                    return user
    # Fallback: operator_id do PDV
    if operator_id:
        try:
            uid = int(operator_id)
            user = db.get(User, uid)
            if user is not None and user.active:
                return user
        except (TypeError, ValueError):
            pass
    raise _unauth("Nenhum operador ou sessao ativa.")
