"""
Rotas administrativas. So admin acessa.

Fase 5 preparatoria: configuracao da impressora.
Fases futuras podem adicionar: management de usuarios, auditoria, etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin, require_csrf
from app.models import AuditLog, Setting, User
from app.schemas import (
    PrinterSettingsOut,
    PrinterSettingsUpdate,
    PrinterTestResult,
)
from app.services.printer import (
    PrintJob,
    PrinterUnavailableError,
    get_printer,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


PRINTER_KEYS = (
    "printer_backend",
    "printer_name",
    "printer_codepage",
    "printer_auto_cut",
)


def _get_setting_value(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row is not None else default


def _upsert_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def _audit(
    db: Session,
    *,
    user_id: int,
    action: str,
    details: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity="setting",
            entity_id=None,
            details=details,
            ip=ip,
        )
    )


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _printer_settings_from_db(db: Session) -> PrinterSettingsOut:
    backend = (
        _get_setting_value(db, "printer_backend", "dummy").strip().lower() or "dummy"
    )
    name = _get_setting_value(db, "printer_name", "")
    codepage = _get_setting_value(db, "printer_codepage", "").strip().upper()
    auto_cut = (
        _get_setting_value(db, "printer_auto_cut", "false").strip().lower() == "true"
    )
    # label do backend ativo
    try:
        label = get_printer(db).label()
    except PrinterUnavailableError as exc:
        label = f"ERRO: {exc}"

    # Pydantic valida; se setting tiver valor estranho ja no banco, caiu no default.
    if backend not in {"dummy", "win32raw"}:
        backend = "dummy"
    if codepage not in {"", "CP437", "CP850", "CP858", "CP860"}:
        codepage = ""
    return PrinterSettingsOut(
        printer_backend=backend,  # type: ignore[arg-type]
        printer_name=name,
        printer_codepage=codepage,  # type: ignore[arg-type]
        printer_auto_cut=auto_cut,
        active_label=label,
    )


@router.get("/printer-settings", response_model=PrinterSettingsOut)
def get_printer_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> PrinterSettingsOut:
    return _printer_settings_from_db(db)


@router.put(
    "/printer-settings",
    response_model=PrinterSettingsOut,
    dependencies=[Depends(require_csrf)],
)
def update_printer_settings(
    payload: PrinterSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> PrinterSettingsOut:
    # Validacoes extra
    if payload.printer_backend == "win32raw" and not payload.printer_name:
        raise HTTPException(
            status_code=422,
            detail="printer_name e obrigatorio quando backend=win32raw.",
        )

    _upsert_setting(db, "printer_backend", payload.printer_backend)
    _upsert_setting(db, "printer_name", payload.printer_name)
    _upsert_setting(db, "printer_codepage", payload.printer_codepage)
    _upsert_setting(
        db, "printer_auto_cut", "true" if payload.printer_auto_cut else "false"
    )
    _audit(
        db,
        user_id=user.id,
        action="printer_settings_updated",
        details=f"backend={payload.printer_backend} name={payload.printer_name[:40]}",
        ip=_ip(request),
    )
    db.commit()
    return _printer_settings_from_db(db)


@router.post(
    "/printer-test",
    response_model=PrinterTestResult,
    dependencies=[Depends(require_csrf)],
)
def printer_test(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> PrinterTestResult:
    """
    Monta um cupom de TESTE curto e envia pelo backend ATUAL (salvo em
    settings). Nao envolve nenhuma venda. Nao desconta estoque.
    """
    try:
        printer = get_printer(db)
    except PrinterUnavailableError as exc:
        return PrinterTestResult(
            backend="(erro)",
            printed=False,
            print_error=str(exc),
            lines=[],
        )

    # Cabecalho simples que respeita 32 colunas (POS-58).
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    lines = [
        "PDV PADARIA".center(32),
        "TESTE DE IMPRESSORA".center(32),
        "-" * 32,
        f"Operador: {user.name[:18]}",
        f"Hora: {now}",
        "-" * 32,
        "1234567890123456789012345678901234"[:32],  # regua 1..32
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"[:32],
        "Acentos: pao, cafe, acao, coracao",
        "Acentos: " + "pão, café, ação, coração",
        "-" * 32,
        f"Backend: {printer.label()}"[:32],
        "",
        "",
        "",
    ]

    printed = False
    print_error: Optional[str] = None
    try:
        printer.print_job(PrintJob(lines=lines))
        printed = True
    except PrinterUnavailableError as exc:
        print_error = str(exc)
    except Exception as exc:  # pragma: no cover - defensivo
        print_error = f"{type(exc).__name__}: {exc}"

    _audit(
        db,
        user_id=user.id,
        action="printer_test",
        details=f"backend={printer.label()[:40]} printed={printed}",
        ip=_ip(request),
    )
    db.commit()

    return PrinterTestResult(
        backend=printer.label(),
        printed=printed,
        print_error=print_error,
        lines=lines,
    )
