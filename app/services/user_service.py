"""
Gestao de usuarios pela UI (Fase 13).

Expoe operacoes CRUD-sem-D (produto/usuario nunca e apagado - regra 5):
- create: cria usuario novo (admin ou caixa)
- update: altera nome, role (nao mexe em senha)
- change_password: troca senha com validacao de strength
- toggle_active: ativa/desativa (BLOQUEIA se for o proprio admin)
- list: lista todos ordenados por nome

Regras:
- Username unico (constraint do banco)
- Senha nunca aparece em response/log
- Admin NAO consegue desativar a si mesmo (evita trancar fora)
- Admin NAO consegue trocar o proprio papel (idem)
- Audit log em TODAS as mutacoes
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.security import hash_password, validate_password_strength


USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
VALID_ROLES = ("admin", "caixa")


class UserError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _audit(db: Session, actor: User, action: str, target_id: int, details: str) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            action=action,
            entity="user",
            entity_id=target_id,
            details=details[:500],
        )
    )


def _validate_name(name: str) -> str:
    if not isinstance(name, str):
        raise UserError("Nome invalido.", 422)
    s = name.strip()
    if len(s) < 2:
        raise UserError("Nome muito curto (minimo 2 caracteres).", 422)
    if len(s) > 120:
        raise UserError("Nome muito longo (maximo 120 caracteres).", 422)
    return s


def _validate_username(username: str) -> str:
    if not isinstance(username, str):
        raise UserError("Username invalido.", 422)
    s = username.strip()
    if len(s) < 3 or len(s) > 50:
        raise UserError("Username deve ter entre 3 e 50 caracteres.", 422)
    if not USERNAME_RE.match(s):
        raise UserError("Username so aceita letras, numeros, ponto, hifen e underscore.", 422)
    return s


def _validate_role(role: str) -> str:
    if role not in VALID_ROLES:
        raise UserError(f"Papel invalido. Use um de: {', '.join(VALID_ROLES)}.", 422)
    return role


def _validate_password(password: str) -> None:
    err = validate_password_strength(password)
    if err:
        raise UserError(err, 422)


# ---------- API ----------


def list_users(db: Session) -> list[User]:
    return list(
        db.execute(select(User).order_by(User.active.desc(), User.name)).scalars()
    )


def create_user(
    db: Session,
    *,
    actor: User,
    name: str,
    username: str,
    password: str,
    role: str,
) -> User:
    name_ok = _validate_name(name)
    username_ok = _validate_username(username)
    role_ok = _validate_role(role)
    _validate_password(password)

    user = User(
        name=name_ok,
        username=username_ok,
        password_hash=hash_password(password),
        role=role_ok,
        active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise UserError(f"Username ja existe: {username_ok}", 409)

    _audit(
        db,
        actor,
        action="user_created",
        target_id=user.id,
        details=f"name={name_ok[:40]} username={username_ok} role={role_ok}",
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    *,
    actor: User,
    target_id: int,
    name: Optional[str] = None,
    role: Optional[str] = None,
) -> User:
    user = db.get(User, target_id)
    if user is None:
        raise UserError("Usuario nao encontrado.", 404)

    changes = []

    if name is not None:
        new_name = _validate_name(name)
        if new_name != user.name:
            user.name = new_name
            changes.append(f"name={new_name[:40]}")

    if role is not None:
        new_role = _validate_role(role)
        if new_role != user.role:
            if user.id == actor.id:
                raise UserError(
                    "Admin nao pode trocar o proprio papel (risco de trancar fora).",
                    400,
                )
            user.role = new_role
            changes.append(f"role={new_role}")

    if not changes:
        return user

    _audit(
        db,
        actor,
        action="user_updated",
        target_id=user.id,
        details=" ".join(changes),
    )
    db.commit()
    db.refresh(user)
    return user


def change_password(
    db: Session,
    *,
    actor: User,
    target_id: int,
    new_password: str,
) -> User:
    user = db.get(User, target_id)
    if user is None:
        raise UserError("Usuario nao encontrado.", 404)
    _validate_password(new_password)
    user.password_hash = hash_password(new_password)
    # Reseta tentativas de login erradas quando a senha e trocada
    user.failed_login_count = 0
    user.locked_until = None
    _audit(
        db,
        actor,
        action="user_password_changed",
        target_id=user.id,
        details=f"username={user.username}",
    )
    db.commit()
    db.refresh(user)
    return user


def toggle_active(
    db: Session,
    *,
    actor: User,
    target_id: int,
    active: bool,
) -> User:
    user = db.get(User, target_id)
    if user is None:
        raise UserError("Usuario nao encontrado.", 404)

    if user.id == actor.id and not active:
        raise UserError(
            "Admin nao pode desativar a si mesmo (risco de trancar fora).",
            400,
        )

    if user.active == bool(active):
        return user  # idempotente

    user.active = bool(active)
    _audit(
        db,
        actor,
        action="user_activated" if active else "user_deactivated",
        target_id=user.id,
        details=f"username={user.username}",
    )
    db.commit()
    db.refresh(user)
    return user
