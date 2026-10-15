"""
Backup do banco SQLite (Fase 9).

Decisoes:
- Usa sqlite3.Connection.backup() (API nativa) para gerar uma copia
  CONSISTENTE do banco mesmo com conexoes ativas. NAO copia o .db direto
  do disco - isso pode corromper se vier escrita no meio.
- Compressao gzip opcional (padrao true) reduz 5-10x o tamanho.
- Multiplos destinos: um pendrive, uma pasta Google Drive sincronizada.
  Falha em um destino nao aborta o outro.
- Rotacao por mtime: mantem os `keep_last` mais recentes em cada destino.
- Nome padrao: `pdv-backup-YYYYMMDD-HHMMSS.db[.gz]`.

Chamadores:
- UI admin: botao "Fazer backup agora"
- cash_service.close_session (hook, se setting on)
- scripts/do_backup.py (CLI para Task Scheduler)
"""

from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------- resultado ----------


@dataclass
class DestinationResult:
    destination: str
    status: str  # "ok" | "fail"
    bytes_written: int = 0
    file_name: Optional[str] = None
    error: Optional[str] = None


@dataclass
class BackupResult:
    started_at: datetime
    finished_at: datetime
    source_bytes: int
    compressed: bool
    results: list[DestinationResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def all_ok(self) -> bool:
        return self.fail_count == 0 and self.ok_count > 0


# ---------- core ----------


def _snapshot_sqlite(source_db_path: Path, target_file: Path) -> int:
    """
    Cria uma copia consistente do SQLite usando a API nativa de backup.
    Retorna o tamanho em bytes do snapshot.
    """
    if not source_db_path.exists():
        raise FileNotFoundError(f"DB nao encontrado: {source_db_path}")

    src = sqlite3.connect(str(source_db_path))
    try:
        dst = sqlite3.connect(str(target_file))
        try:
            # pages=0 implica copia tudo de uma vez; sem sleep.
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return target_file.stat().st_size


def _compress(src_file: Path, dst_file: Path) -> int:
    """gzip streaming. Retorna o tamanho comprimido."""
    with open(src_file, "rb") as f_in:
        with gzip.open(dst_file, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
    return dst_file.stat().st_size


def _rotate(destination: Path, pattern: str, keep_last: int) -> list[Path]:
    """Mantem os `keep_last` mais recentes por mtime. Retorna os apagados."""
    if keep_last <= 0:
        return []
    files = sorted(
        destination.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    old = files[keep_last:]
    deleted: list[Path] = []
    for f in old:
        try:
            f.unlink()
            deleted.append(f)
        except OSError:
            # nao bloqueia o backup se nao conseguir apagar
            pass
    return deleted


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_name(compress: bool) -> str:
    suffix = ".db.gz" if compress else ".db"
    return f"pdv-backup-{_timestamp()}{suffix}"


# ---------- API ----------


def create_backup(
    source_db_path: Path | str,
    destinations: list[Path | str],
    *,
    keep_last: int = 30,
    compress: bool = True,
    file_name: Optional[str] = None,
) -> BackupResult:
    """
    Executa o backup para TODOS os destinos listados.

    source_db_path: caminho do banco (ex: data/pdv.db).
    destinations: lista de paths de pasta destino. Cada pasta e criada se
      nao existir. Falha em uma nao aborta as outras.
    keep_last: quantos backups manter em cada pasta (por mtime do arquivo
      que casa com pdv-backup-*.db[.gz]).
    compress: se True, grava .db.gz; se False, .db puro.
    file_name: nome do arquivo final. Se None, usa `pdv-backup-ts.db[.gz]`.
    """
    src = Path(source_db_path)
    started = datetime.now()
    name = file_name or _default_name(compress)
    pattern = "pdv-backup-*.db.gz" if compress else "pdv-backup-*.db"

    # 1) snapshot em arquivo temporario via API nativa
    with tempfile.TemporaryDirectory(prefix="pdv-bak-") as tmpdir:
        tmp_root = Path(tmpdir)
        raw_snap = tmp_root / "snap.db"
        source_bytes = _snapshot_sqlite(src, raw_snap)

        if compress:
            payload = tmp_root / name
            _compress(raw_snap, payload)
        else:
            payload = raw_snap
            # renomeia dentro do tmpdir, pra nome final
            final_tmp = tmp_root / name
            raw_snap.rename(final_tmp)
            payload = final_tmp

        payload_bytes = payload.stat().st_size

        # 2) copia pros destinos
        results: list[DestinationResult] = []
        for dest in destinations:
            dest_path = Path(dest)
            try:
                dest_path.mkdir(parents=True, exist_ok=True)
                target = dest_path / name
                shutil.copy2(payload, target)
                _rotate(dest_path, pattern, keep_last)
                results.append(
                    DestinationResult(
                        destination=str(dest_path),
                        status="ok",
                        bytes_written=payload_bytes,
                        file_name=name,
                    )
                )
            except Exception as exc:
                results.append(
                    DestinationResult(
                        destination=str(dest_path),
                        status="fail",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

    return BackupResult(
        started_at=started,
        finished_at=datetime.now(),
        source_bytes=source_bytes,
        compressed=compress,
        results=results,
    )


# ---------- settings helpers ----------


BACKUP_SETTING_KEYS = {
    "backup_dir_1",
    "backup_dir_2",
    "backup_keep",
    "backup_on_cash_close",
    "backup_compress",
}


def list_backup_files(destination: Path | str, compressed: bool = True) -> list[dict]:
    """Lista arquivos de backup em um destino. Usado pelo historico."""
    d = Path(destination)
    if not d.exists():
        return []
    pattern = "pdv-backup-*.db.gz" if compressed else "pdv-backup-*.db"
    out = []
    for f in sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
        st = f.stat()
        out.append(
            {
                "name": f.name,
                "size": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime),
            }
        )
    return out
