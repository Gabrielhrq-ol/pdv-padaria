"""
CLI de backup. Pensado pra ser agendado via Task Scheduler do Windows.

Uso:
    python scripts/do_backup.py            # usa settings do banco
    python scripts/do_backup.py --quiet    # so imprime erros

Codigo de saida:
    0 = todos os destinos deram ok
    1 = nenhum destino configurado
    2 = ao menos um destino falhou (ok_count > 0 ainda)
    3 = tudo falhou
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import SessionLocal  # noqa: E402
from app.services.backup_hook import run_backup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup do banco do PDV.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Nao imprime se tudo deu certo.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        try:
            result = run_backup(db, user=None)
        except ValueError as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 1
    finally:
        db.close()

    if not args.quiet or result.fail_count > 0:
        print(
            f"Backup: {result.ok_count}/{len(result.results)} destinos OK, "
            f"fonte={result.source_bytes} bytes, "
            f"gzip={result.compressed}"
        )
        for r in result.results:
            if r.status == "ok":
                print(f"  OK  {r.destination}  {r.file_name}  ({r.bytes_written} bytes)")
            else:
                print(f"  FAIL {r.destination}  {r.error}")

    if result.ok_count == 0:
        return 3
    if result.fail_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
