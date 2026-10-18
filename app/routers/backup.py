"""
Rotas de backup (Fase 9). Admin-only.

- GET /api/admin/backup/settings
- PUT /api/admin/backup/settings
- POST /api/admin/backup/run
- GET /api/admin/backup/history
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin, require_csrf
from app.models import AuditLog, Setting, User
from app.schemas import (
    BackupDestinationOut,
    BackupHistoryEntry,
    BackupRunOut,
    BackupSettingsIn,
    BackupSettingsOut,
)
from app.services import backup_hook
from app.services.backup_service import BackupResult


router = APIRouter(prefix="/api/admin/backup", tags=["backup"])


# ---------- helpers ----------


def _get(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row is not None else default


def _upsert(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def _check_external(path: str) -> Optional[str]:
    """
    Fase 17 (B5 da auditoria): avisa se o caminho de backup esta
    no mesmo volume do PDV (SSD do caixa). Backup real deve ir pra
    pendrive, HD externo ou pasta sincronizada com nuvem.

    Nao bloqueia - admin pode insistir se tiver razao. So avisa.
    """
    from pathlib import Path
    from app.config import get_settings

    if not path:
        return None
    try:
        p = Path(path).resolve()
    except Exception:
        return None
    pdv_root = Path(get_settings().db_absolute_path).parent.parent.resolve()
    try:
        p.relative_to(pdv_root)
        return (
            f"{path!r} esta DENTRO da pasta do PDV. "
            "Backup nao protege contra queima do SSD. "
            "Aponte pra pendrive (ex: E:\\pdv-backups) ou pasta do "
            "Google Drive sincronizada."
        )
    except ValueError:
        pass
    # avisa se e C:\ e a instalacao tambem e C:\ (mesmo drive, SSD unico)
    try:
        if p.drive and pdv_root.drive and p.drive.upper() == pdv_root.drive.upper():
            # mesmo drive mas pasta diferente - menos ruim, so lembra
            return (
                f"{path!r} esta no mesmo drive do PDV ({p.drive}). "
                "Idealmente use um pendrive ou pasta Google Drive em outra midia."
            )
    except Exception:
        pass
    return None


def _current_settings(db: Session) -> BackupSettingsOut:
    def _b(key: str, default: bool) -> bool:
        v = _get(db, key, "")
        if not v:
            return default
        return v.strip().lower() == "true"

    def _i(key: str, default: int) -> int:
        v = _get(db, key, "")
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    dir1 = _get(db, "backup_dir_1", "") or None
    dir2 = _get(db, "backup_dir_2", "") or None
    warnings: list[str] = []
    for d in (dir1, dir2):
        if d:
            w = _check_external(d)
            if w:
                warnings.append(w)

    return BackupSettingsOut(
        backup_dir_1=dir1,
        backup_dir_2=dir2,
        backup_keep=_i("backup_keep", 30),
        backup_on_cash_close=_b("backup_on_cash_close", True),
        backup_compress=_b("backup_compress", True),
        warnings=warnings,
    )


def _result_to_schema(result: BackupResult) -> BackupRunOut:
    return BackupRunOut(
        started_at=result.started_at,
        finished_at=result.finished_at,
        source_bytes=result.source_bytes,
        compressed=result.compressed,
        ok_count=result.ok_count,
        fail_count=result.fail_count,
        results=[
            BackupDestinationOut(
                destination=r.destination,
                status=r.status,  # type: ignore[arg-type]
                bytes_written=r.bytes_written,
                file_name=r.file_name,
                error=r.error,
            )
            for r in result.results
        ],
    )


# ---------- settings ----------


@router.get("/settings", response_model=BackupSettingsOut)
def get_settings_endpoint(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> BackupSettingsOut:
    return _current_settings(db)


@router.put(
    "/settings",
    response_model=BackupSettingsOut,
    dependencies=[Depends(require_csrf)],
)
def update_settings(
    payload: BackupSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BackupSettingsOut:
    _upsert(db, "backup_dir_1", payload.backup_dir_1 or "")
    _upsert(db, "backup_dir_2", payload.backup_dir_2 or "")
    _upsert(db, "backup_keep", str(payload.backup_keep))
    _upsert(db, "backup_on_cash_close", "true" if payload.backup_on_cash_close else "false")
    _upsert(db, "backup_compress", "true" if payload.backup_compress else "false")
    db.add(
        AuditLog(
            user_id=user.id,
            action="backup_settings_updated",
            entity="setting",
            details=(
                f"dir1={bool(payload.backup_dir_1)} "
                f"dir2={bool(payload.backup_dir_2)} "
                f"keep={payload.backup_keep} "
                f"on_close={payload.backup_on_cash_close} "
                f"compress={payload.backup_compress}"
            ),
        )
    )
    db.commit()
    return _current_settings(db)


# ---------- run ----------


@router.post(
    "/run",
    response_model=BackupRunOut,
    dependencies=[Depends(require_csrf)],
)
def run_now(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> BackupRunOut:
    try:
        result = backup_hook.run_backup(db, user=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _result_to_schema(result)


# ---------- history ----------


@router.get("/history", response_model=list[BackupHistoryEntry])
def history(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[BackupHistoryEntry]:
    rows = db.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(
            AuditLog.action.in_(
                ["backup_run", "backup_skipped", "backup_failed"]
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()
    out = []
    for audit, user_row in rows:
        out.append(
            BackupHistoryEntry(
                created_at=audit.created_at,
                user_name=user_row.name if user_row else None,
                action=audit.action,
                details=audit.details,
            )
        )
    return out
