"""
Troca de credenciais de dev antes da entrega (Fase 10).

Executa 2 coisas em sequencia:
1. Cria o admin real do dono (interativo, usa getpass)
2. Desativa os usuarios de teste listados (nao apaga - regra 5 do
   CLAUDE.md: produto/usuario nunca e apagado, so active=False)

Uso:
    python scripts/trocar_admin.py

Depois lista os usuarios ativos pra confirmar.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import AuditLog, User  # noqa: E402


# Usuarios criados em dev/teste que devem ser desativados antes de entregar.
# Se voce criou outros users de teste, adicione aqui.
DEV_USERNAMES_PADRAO = ["gabriel", "admin", "teste", "dev"]


def _print_users(db) -> None:
    rows = db.execute(select(User).order_by(User.id)).scalars().all()
    print()
    print(f"{'ID':<4} {'Username':<20} {'Nome':<30} {'Role':<8} {'Ativo':<6}")
    print("-" * 70)
    for u in rows:
        print(
            f"{u.id:<4} {u.username:<20} {u.name[:30]:<30} "
            f"{u.role:<8} {'sim' if u.active else 'nao':<6}"
        )
    print()


def main() -> int:
    print("=" * 70)
    print(" PDV Padaria - Troca de credenciais pre-entrega")
    print("=" * 70)
    print()
    print("Este script:")
    print("  1. Mostra os usuarios atuais")
    print("  2. Chama scripts/create_admin.py pra criar o admin do dono")
    print("  3. Desativa usuarios de dev conhecidos (nao apaga - regra 5)")
    print()

    db = SessionLocal()
    try:
        print("USUARIOS ANTES:")
        _print_users(db)

        resp = input(
            "Prosseguir? Isso vai pedir dados do admin real e depois "
            "desativar os de dev. [s/N] "
        ).strip().lower()
        if resp != "s":
            print("Cancelado.")
            return 1
    finally:
        db.close()

    # Passo 2: delega pro create_admin.py existente
    print()
    print(">>> Criando o admin real do dono...")
    import subprocess

    r = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "create_admin.py")],
        cwd=str(PROJECT_ROOT),
    )
    if r.returncode != 0:
        print()
        print("create_admin.py retornou erro. Abortando a desativacao.")
        return 2

    # Passo 3: desativa os de dev
    print()
    print(">>> Desativando usuarios de dev...")
    print()

    db = SessionLocal()
    desativados: list[str] = []
    try:
        for username in DEV_USERNAMES_PADRAO:
            user = db.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
            if user is None:
                continue
            if not user.active:
                print(f"  - {username}: ja estava inativo, pulando")
                continue
            user.active = False
            db.add(
                AuditLog(
                    user_id=user.id,
                    action="user_deactivated_pre_delivery",
                    entity="user",
                    entity_id=user.id,
                    details=f"desativado pelo script trocar_admin",
                )
            )
            desativados.append(username)
            print(f"  - {username}: DESATIVADO")

        db.commit()

        print()
        print("USUARIOS DEPOIS:")
        _print_users(db)

        if not desativados:
            print(
                "Nenhum usuario de dev conhecido foi encontrado ativo. "
                "Se voce usa outros nomes, desative manualmente via SQL."
            )
        else:
            print(f"Desativados: {', '.join(desativados)}")
            print()
            print("CHECK: Rode 'SELECT username, active FROM users' e confirme")
            print("que SO o admin do dono fica ativo.")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
