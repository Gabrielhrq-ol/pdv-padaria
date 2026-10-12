"""
Importacao em massa de produtos a partir de um arquivo CSV.

Formato (cabecalho obrigatorio):
    name,barcode,internal_code,category,unit,price,stock,min_stock,favorite

Uso:
    python scripts/import_products.py produtos.csv
    python scripts/import_products.py produtos.csv --dry-run
    python scripts/import_products.py produtos.csv --strict

Ver docs/IMPORTACAO-CSV.md para detalhes de formato e exemplos.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import SessionLocal  # noqa: E402
from app.services.csv_import import import_csv_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="Caminho do arquivo CSV")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida e simula sem gravar nada no banco.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Aborta no primeiro erro ou produto duplicado.",
    )
    args = parser.parse_args()

    path = Path(args.csv_path).resolve()
    print(f"Arquivo: {path}")
    print(f"Modo: {'DRY-RUN' if args.dry_run else 'IMPORT'}"
          f"{' + STRICT' if args.strict else ''}")
    print("-" * 60)

    session = SessionLocal()
    try:
        parse_result, import_result = import_csv_file(
            session, path, dry_run=args.dry_run, strict=args.strict
        )
    except FileNotFoundError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()

    # Reporta erros detalhados
    if import_result.errors:
        print("Erros encontrados:")
        for err in import_result.errors:
            print(f"  linha {err.line_number}: {err.message}")
        print()

    print(import_result.summary())

    if import_result.errors and args.strict:
        return 1
    if import_result.errors and not import_result.inserted:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
