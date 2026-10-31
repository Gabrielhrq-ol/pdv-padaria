"""
Integracao do backup_service com o resto do app.

- Le settings do banco e invoca `backup_service.create_backup`.
- Grava audit_log do resultado.
- `trigger_post_close_backup`: hook disparado por cash_service.close_session.
  Roda em thread daemon pra nao bloquear o fechamento do caixa.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, Setting, User
from app.services.backup_service import BackupResult, create_backup


# ---------- settings helpers ----------


def _get(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row is not None else default


def _get_bool(db: Session, key: str, default: bool = False) -> bool:
    v = _get(db, key, "")
    if not v:
        return default
    return v.strip().lower() == "true"


def _get_int(db: Session, key: str, default: int) -> int:
    v = _get(db, key, "")
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _destinations(db: Session) -> list[str]:
    out: list[str] = []
    for key in ("backup_dir_1", "backup_dir_2"):
        v = _get(db, key, "").strip()
        if v:
            out.append(v)
    return out


# ---------- resultado serializavel ----------


def _result_to_dict(result: BackupResult) -> dict:
    return {
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "source_bytes": result.source_bytes,
        "compressed": result.compressed,
        "ok_count": result.ok_count,
        "fail_count": result.fail_count,
        "destinations": [
            {
                "destination": r.destination,
                "status": r.status,
                "bytes": r.bytes_written,
                "file_name": r.file_name,
                "error": r.error,
            }
            for r in result.results
        ],
    }


def _audit(db: Session, user_id: Optional[int], result: BackupResult) -> None:
    details = json.dumps(_result_to_dict(result), ensure_ascii=False)[:500]
    db.add(
        AuditLog(
            user_id=user_id,
            action="backup_run",
            entity="setting",
            details=details,
        )
    )
    db.commit()


# ---------- API principal ----------


def run_backup(db: Session, user: Optional[User] = None) -> BackupResult:
    """
    Le settings, roda backup, grava audit. Retorna o BackupResult.

    Levanta ValueError se nao houver nenhum destino configurado.
    """
    destinations = _destinations(db)
    if not destinations:
        raise ValueError(
            "Nenhum destino de backup configurado. Preencha backup_dir_1 ou backup_dir_2."
        )
    keep = _get_int(db, "backup_keep", 30)
    compress = _get_bool(db, "backup_compress", True)

    source = get_settings().db_absolute_path

    result = create_backup(
        source_db_path=source,
        destinations=destinations,
        keep_last=keep,
        compress=compress,
    )
    _audit(db, user.id if user else None, result)
    return result


# ---------- hook: dispara em background ----------


def _run_in_thread(user_id: Optional[int]) -> None:
    """
    Abre sua propria sessao do banco. NAO reusa a session do request/service
    que chamou - essa pode ja ter sido fechada / commitada.

    Todo o corpo esta num try/except amplo: thread de backup nunca pode
    propagar erro - no pior caso, logs no audit_log quando houver sessao.
    """
    try:
        db = SessionLocal()
    except Exception:
        return
    try:
        destinations = _destinations(db)
        if not destinations:
            # setting faltando: grava audit indicando que foi skipped e sai.
            db.add(
                AuditLog(
                    user_id=user_id,
                    action="backup_skipped",
                    entity="setting",
                    details="sem destinos configurados",
                )
            )
            db.commit()
            return
        keep = _get_int(db, "backup_keep", 30)
        compress = _get_bool(db, "backup_compress", True)
        source = get_settings().db_absolute_path
        try:
            result = create_backup(
                source_db_path=source,
                destinations=destinations,
                keep_last=keep,
                compress=compress,
            )
            _audit(db, user_id, result)
        except Exception as exc:
            try:
                db.add(
                    AuditLog(
                        user_id=user_id,
                        action="backup_failed",
                        entity="setting",
                        details=f"{type(exc).__name__}: {exc}"[:500],
                    )
                )
                db.commit()
            except Exception:
                pass
    except Exception:
        # Qualquer erro inesperado na leitura de settings etc: silencioso.
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def trigger_post_close_backup(db: Session, user: Optional[User]) -> None:
    """
    Se setting backup_on_cash_close=true, dispara backup em thread daemon.
    NUNCA levanta - falha de backup nao pode travar o fechamento do caixa.
    """
    try:
        if not _get_bool(db, "backup_on_cash_close", True):
            return
        if not _destinations(db):
            return
        t = threading.Thread(
            target=_run_in_thread,
            args=(user.id if user else None,),
            daemon=True,
        )
        t.start()
    except Exception:
        # Defensivo: hook nunca propaga erro.
        pass
