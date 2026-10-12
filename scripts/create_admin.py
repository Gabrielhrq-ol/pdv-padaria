"""
Cria o primeiro usuario admin do sistema (ou um usuario adicional).

Uso interativo:
    python scripts/create_admin.py

Uso nao-interativo (nao recomendado em producao - senha fica no historico):
    python scripts/create_admin.py --name "Dono" --username dono --role admin

Regras de senha:
    - 8+ caracteres, pelo menos 1 letra e 1 numero.
    - A senha e lida com getpass (nao ecoa) e nunca e logada.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import AuditLog, User  # noqa: E402
from app.security import hash_password, validate_password_strength  # noqa: E402


USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
VALID_ROLES = ("admin", "caixa")


def _prompt_name() -> str:
    while True:
        name = input("Nome completo: ").strip()
        if 2 <= len(name) <= 120:
            return name
        print("  Nome precisa ter entre 2 e 120 caracteres.")


def _prompt_username() -> str:
    while True:
        username = input("Username (letras, numeros, . _ -): ").strip()
        if 3 <= len(username) <= 50 and USERNAME_RE.match(username):
            return username
        print("  Username invalido. 3-50 chars, so letras/numeros/._-")


def _prompt_role(default: str = "admin") -> str:
    while True:
        resp = input(f"Papel (admin/caixa) [{default}]: ").strip().lower() or default
        if resp in VALID_ROLES:
            return resp
        print("  Papel deve ser 'admin' ou 'caixa'.")


def _prompt_password() -> str:
    while True:
        p1 = getpass.getpass("Senha (nao sera exibida): ")
        err = validate_password_strength(p1)
        if err:
            print(f"  {err}")
            continue
        p2 = getpass.getpass("Confirme a senha: ")
        if p1 != p2:
            print("  As senhas nao coincidem.")
            continue
        return p1


def create_user(
    name: str,
    username: str,
    role: str,
    password: str,
) -> int:
    if role not in VALID_ROLES:
        raise ValueError(f"role invalida: {role}")
    err = validate_password_strength(password)
    if err:
        raise ValueError(err)
    session = SessionLocal()
    try:
        existing = session.execute(
            select(User).where(func.lower(User.username) == username.lower())
        ).scalar_one_or_none()
        if existing is not None:
            raise RuntimeError(f"Usuario '{username}' ja existe (id={existing.id}).")
        user = User(
            name=name,
            username=username,
            password_hash=hash_password(password),
            role=role,
            active=True,
        )
        session.add(user)
        session.flush()
        session.add(
            AuditLog(
                user_id=user.id,
                action="user_created",
                entity="user",
                entity_id=user.id,
                details=f"role={role}",
            )
        )
        session.commit()
        return user.id
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", help="Nome completo")
    parser.add_argument("--username", help="Username (letras/numeros/._-)")
    parser.add_argument(
        "--role", choices=VALID_ROLES, help="Papel (admin|caixa)"
    )
    args = parser.parse_args()

    print("=" * 48)
    print("Criacao de usuario - PDV Padaria")
    print("=" * 48)

    name = args.name or _prompt_name()
    username = args.username or _prompt_username()
    role = args.role or _prompt_role()
    # Senha SEMPRE via prompt - nunca aceita por CLI.
    password = _prompt_password()

    try:
        uid = create_user(name=name, username=username, role=role, password=password)
    except RuntimeError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    print(f"\nUsuario criado com sucesso. id={uid} username={username} role={role}")
    print("Senha gravada como hash argon2id. Nunca sera exibida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
