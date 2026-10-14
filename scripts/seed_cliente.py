"""
Popula a tabela `settings` com os dados REAIS do cliente, lidos de
`data/cliente.json`.

`data/cliente.json` esta no .gitignore (toda a pasta `data/` esta).
Apenas `data/cliente.example.json` e versionado, com placeholders.

Fluxo recomendado:
    1. Copie: `copy data\\cliente.example.json data\\cliente.json`
    2. Edite data\\cliente.json com os dados reais.
    3. Rode: `python scripts/seed_cliente.py`
    4. Confira: `git status`  (data/cliente.json NAO deve aparecer).

Uso:
    python scripts/seed_cliente.py
    python scripts/seed_cliente.py --file caminho/para/arquivo.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import SessionLocal  # noqa: E402
from app.models import Setting  # noqa: E402


# Chaves aceitas em cliente.json. Outras chaves sao ignoradas (com aviso).
ALLOWED_KEYS: set[str] = {
    "store_name",
    "store_cnpj",
    "store_address",
    "store_phone",
    "receipt_header_extra",
    "receipt_footer",
    "receipt_columns",
    "receipt_show_barcode",
    "receipt_disclaimer",
    "printer_name",
    "printer_codepage",
    "printer_auto_cut",
    "allow_negative_stock",
    "default_print_after_sale",
    "payment_methods",
}


def _coerce_to_str(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"valor nao serializavel: {value!r}")


def seed_cliente(json_path: Path) -> None:
    if not json_path.exists():
        print(f"ERRO: nao encontrei {json_path}", file=sys.stderr)
        print(
            "Copie data/cliente.example.json para data/cliente.json e preencha.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("ERRO: o arquivo precisa conter um objeto JSON.")

    session = SessionLocal()
    applied = 0
    ignored: list[str] = []
    try:
        for key, value in data.items():
            if key.startswith("_"):
                continue  # comentarios
            if key not in ALLOWED_KEYS:
                ignored.append(key)
                continue
            value_str = _coerce_to_str(value)
            existing = session.get(Setting, key)
            if existing is None:
                session.add(Setting(key=key, value=value_str))
            else:
                existing.value = value_str
            applied += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"Settings aplicadas: {applied}.")
    if ignored:
        print(f"Chaves ignoradas (nao conhecidas): {', '.join(ignored)}")
    print("\nIMPORTANTE: confira `git status` -- data/cliente.json NAO deve aparecer.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        default=str(PROJECT_ROOT / "data" / "cliente.json"),
        help="Caminho do JSON com os dados do cliente.",
    )
    args = parser.parse_args()
    seed_cliente(Path(args.file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
