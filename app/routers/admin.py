"""
Rotas administrativas. So admin acessa.

Fase 5 preparatoria: configuracao da impressora.
Fases futuras podem adicionar: management de usuarios, auditoria, etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin, require_authenticated, require_csrf
from app.models import AuditLog, Setting, User
from app.schemas import (
    LowStockOut,
    PrinterSettingsOut,
    PrinterSettingsUpdate,
    PrinterTestResult,
    StockAdjustmentIn,
    StockEntryIn,
    StockLossIn,
    StockMovementOut,
    StockMovementType,
)
from app.services import stock_service
from app.services.printer import (
    PrintJob,
    PrinterUnavailableError,
    get_printer,
)
from app.services.stock_service import StockError

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

    # Cabecalho simples em 48 colunas (CLAUDE.md regra de teste).
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    W = 48
    lines = [
        "PDV PADARIA".center(W),
        "TESTE DE IMPRESSORA".center(W),
        "-" * W,
        f"Operador: {user.name[:W - 10]}",
        f"Hora: {now}",
        "-" * W,
        ("1234567890" * 5)[:W],  # regua
        ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuv")[:W],
        "Acentos: pao, cafe, acao, coracao",
        "Acentos: pão, café, ação, coração",
        "-" * W,
        f"Backend: {printer.label()}"[:W],
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


# ---------- Stock (Fase 6) ----------


def _movement_to_out(row: stock_service.MovementRow) -> StockMovementOut:
    return StockMovementOut(
        id=row.id,
        product_id=row.product_id,
        product_name=row.product_name,
        product_unit=row.product_unit,  # type: ignore[arg-type]
        type=row.type,  # type: ignore[arg-type]
        qty_milli=row.qty_milli,
        reason=row.reason,
        sale_id=row.sale_id,
        user_id=row.user_id,
        user_name=row.user_name,
        created_at=row.created_at,
    )


@router.post(
    "/stock/entry",
    response_model=StockMovementOut,
    dependencies=[Depends(require_csrf)],
)
def stock_entry(
    payload: StockEntryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> StockMovementOut:
    try:
        stock_service.register_entry(
            db,
            user=user,
            product_id=payload.product_id,
            qty_milli=payload.qty_milli,
            reason=payload.reason,
        )
    except StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    rows = stock_service.list_movements(
        db, product_id=payload.product_id, type_="entrada", limit=1
    )
    return _movement_to_out(rows[0])


@router.post(
    "/stock/loss",
    response_model=StockMovementOut,
    dependencies=[Depends(require_csrf)],
)
def stock_loss(
    payload: StockLossIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> StockMovementOut:
    try:
        stock_service.register_loss(
            db,
            user=user,
            product_id=payload.product_id,
            qty_milli=payload.qty_milli,
            reason=payload.reason,
        )
    except StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    rows = stock_service.list_movements(
        db, product_id=payload.product_id, type_="perda", limit=1
    )
    return _movement_to_out(rows[0])


@router.post(
    "/stock/adjustment",
    response_model=StockMovementOut,
    dependencies=[Depends(require_csrf)],
)
def stock_adjustment(
    payload: StockAdjustmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> StockMovementOut:
    try:
        stock_service.register_adjustment(
            db,
            user=user,
            product_id=payload.product_id,
            new_stock_milli=payload.new_stock_milli,
            reason=payload.reason,
        )
    except StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    rows = stock_service.list_movements(
        db, product_id=payload.product_id, type_="ajuste", limit=1
    )
    return _movement_to_out(rows[0])


@router.get("/stock/movements", response_model=list[StockMovementOut])
def stock_movements(
    product_id: Optional[int] = Query(default=None, ge=1),
    type: Optional[StockMovementType] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_authenticated),
) -> list[StockMovementOut]:
    """
    Historico de movimentacoes. Admin e caixa podem consultar.
    """
    rows = stock_service.list_movements(
        db,
        product_id=product_id,
        type_=type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [_movement_to_out(r) for r in rows]


@router.get("/stock/low", response_model=list[LowStockOut])
def stock_low(
    db: Session = Depends(get_db),
    _: User = Depends(require_authenticated),
) -> list[LowStockOut]:
    """
    Produtos ativos abaixo do minimo configurado. Admin e caixa podem ver
    (caixa precisa saber o que acabou).
    """
    rows = stock_service.list_low_stock(db)
    return [
        LowStockOut(
            product_id=r.product_id,
            product_name=r.product_name,
            unit=r.unit,  # type: ignore[arg-type]
            stock_milli=r.stock_milli,
            min_stock_milli=r.min_stock_milli,
        )
        for r in rows
    ]
