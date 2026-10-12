"""
Rotas de autenticacao: login, logout, /me.

Flux de login:
    - username case-insensitive
    - verifica argon2
    - 5 falhas em 15 min -> locked_until = now + 15min
    - audit_log: login_ok, login_fail, account_locked, logout
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dependencies import (
    SESSION_MAX_AGE_SECONDS,
    get_current_user,
    get_optional_user,
)
from app.models import AuditLog, User
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_session_token,
    generate_csrf_token,
    utc_now,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("auth")


# Politica de bloqueio - pode virar setting no banco.
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _client_ip(request: Request) -> Optional[str]:
    """IP do cliente. 127.0.0.1 na quase totalidade dos casos."""
    if request.client is None:
        return None
    return request.client.host


def _audit(
    db: Session,
    *,
    action: str,
    user_id: Optional[int],
    ip: Optional[str],
    details: Optional[str] = None,
    entity: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
            ip=ip,
        )
    )


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    settings = get_settings()
    secure = not settings.is_development  # Secure em producao
    # Session cookie: HttpOnly + SameSite=Strict
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    # CSRF cookie: NAO-HttpOnly (JS precisa ler); mesmo max_age
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    response.delete_cookie(key=CSRF_COOKIE, path="/")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    ip = _client_ip(request)
    # Busca case-insensitive
    user = db.execute(
        select(User).where(func.lower(User.username) == payload.username.lower())
    ).scalar_one_or_none()

    now = utc_now()

    if user is None:
        _audit(
            db,
            action="login_fail_unknown_user",
            user_id=None,
            ip=ip,
            details=f"username={payload.username[:50]}",
        )
        db.commit()
        # Mensagem generica (nao vaza se o username existe).
        raise HTTPException(status_code=401, detail="Credenciais invalidas.")

    if not user.active:
        _audit(db, action="login_fail_inactive", user_id=user.id, ip=ip)
        db.commit()
        raise HTTPException(status_code=401, detail="Credenciais invalidas.")

    # Lockout em vigor?
    if user.locked_until is not None and user.locked_until > now:
        _audit(db, action="login_blocked_locked", user_id=user.id, ip=ip)
        db.commit()
        raise HTTPException(
            status_code=403, detail="Conta temporariamente bloqueada. Tente mais tarde."
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            _audit(
                db,
                action="account_locked",
                user_id=user.id,
                ip=ip,
                details=f"attempts={user.failed_login_count}",
            )
        else:
            _audit(
                db,
                action="login_fail",
                user_id=user.id,
                ip=ip,
                details=f"attempts={user.failed_login_count}",
            )
        db.commit()
        raise HTTPException(status_code=401, detail="Credenciais invalidas.")

    # Login OK
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    session_token = create_session_token(user.id)
    csrf_token = generate_csrf_token()
    _set_auth_cookies(response, session_token, csrf_token)

    _audit(db, action="login_ok", user_id=user.id, ip=ip)
    db.commit()
    db.refresh(user)

    return LoginResponse(
        user=UserOut.model_validate(user),
        csrf_token=csrf_token,
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    _audit(db, action="logout", user_id=user.id, ip=_client_ip(request))
    db.commit()
    _clear_auth_cookies(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
