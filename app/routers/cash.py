"""
Rotas da sessao de caixa (Fase 7).

Admin e caixa podem operar o caixa (quem logar opera o aberto).
Toggle do setting cash_session_required e admin-only.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import (
    require_admin,
    require_authenticated,
    require_csrf,
    require_user_or_operator,
)
from app.models import AuditLog, CashMovement, CashSession, User
from app.schemas import (
    CashCloseIn,
    CashCloseOut,
    CashMovementOut,
    CashOpenIn,
    CashPaymentTotal,
    CashReportPrintOut,
    CashRequiredToggle,
    CashSangriaIn,
    CashSessionOut,
    CashSessionSummaryOut,
    CashSuprimentoIn,
)
from app.services import cash_service
from app.services.cash_service import CashError
from app.services.printer import PrintJob, get_printer


logger = logging.getLogger("cash")

router = APIRouter(prefix="/api/cash", tags=["cash"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


def _handle_cash_error(fn):
    """Pequeno wrapper: converte CashError em HTTPException."""
    pass


def _session_to_out(db: Session, s: CashSession) -> CashSessionOut:
    opener = db.get(User, s.opened_by)
    closer = db.get(User, s.closed_by) if s.closed_by else None
    return CashSessionOut(
        id=s.id,
        status=s.status,  # type: ignore[arg-type]
        opened_by=s.opened_by,
        opened_by_name=opener.name if opener else None,
        opened_at=s.opened_at,
        opening_cash_cents=s.opening_cash_cents,
        closed_by=s.closed_by,
        closed_by_name=closer.name if closer else None,
        closed_at=s.closed_at,
        closing_cash_declared_cents=s.closing_cash_declared_cents,
        closing_cash_expected_cents=s.closing_cash_expected_cents,
        closing_difference_cents=s.closing_difference_cents,
        difference_reason=s.difference_reason,
        notes=s.notes,
    )


def _movement_to_out(db: Session, m: CashMovement) -> CashMovementOut:
    user = db.get(User, m.user_id)
    return CashMovementOut(
        id=m.id,
        cash_session_id=m.cash_session_id,
        type=m.type,  # type: ignore[arg-type]
        amount_cents=m.amount_cents,
        reason=m.reason,
        user_id=m.user_id,
        user_name=user.name if user else None,
        created_at=m.created_at,
    )


# ---------- current / summary ----------


@router.get("/current", response_model=CashSessionOut)
def current(
    db: Session = Depends(get_db),
    _: User = Depends(require_user_or_operator),
) -> CashSessionOut:
    s = cash_service.get_open_session(db)
    if s is None:
        raise HTTPException(status_code=404, detail="Nenhum caixa aberto.")
    return _session_to_out(db, s)


@router.get("/current/summary", response_model=CashSessionSummaryOut)
def current_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_user_or_operator),
) -> CashSessionSummaryOut:
    s = cash_service.get_open_session(db)
    if s is None:
        raise HTTPException(status_code=404, detail="Nenhum caixa aberto.")
    summary = cash_service.build_summary(db, s)
    return CashSessionSummaryOut(
        session=_session_to_out(db, summary.session),
        movements=[_movement_to_out(db, m) for m in summary.movements],
        payments_by_method=[
            CashPaymentTotal(
                method=p.method, total_cents=p.total_cents, count=p.count
            )
            for p in summary.payments_by_method
        ],
        sales_cash_cents=summary.sales_cash_cents,
        sales_count=summary.sales_count,
        expected_cash_cents=summary.expected_cash_cents,
    )


# ---------- abrir ----------


@router.post(
    "/open",
    response_model=CashSessionOut,
    dependencies=[Depends(require_csrf)],
)
def open_cash(
    payload: CashOpenIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_or_operator),
) -> CashSessionOut:
    try:
        s = cash_service.open_session(
            db,
            user=user,
            opening_cash_cents=payload.opening_cash_cents,
            notes=payload.notes,
        )
    except CashError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _session_to_out(db, s)


# ---------- sangria ----------


@router.post(
    "/sangria",
    response_model=CashMovementOut,
    dependencies=[Depends(require_csrf)],
)
def sangria(
    payload: CashSangriaIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_or_operator),
) -> CashMovementOut:
    try:
        mv = cash_service.register_sangria(
            db, user=user, amount_cents=payload.amount_cents, reason=payload.reason
        )
    except CashError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _movement_to_out(db, mv)


# ---------- suprimento ----------


@router.post(
    "/suprimento",
    response_model=CashMovementOut,
    dependencies=[Depends(require_csrf)],
)
def suprimento(
    payload: CashSuprimentoIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_or_operator),
) -> CashMovementOut:
    try:
        mv = cash_service.register_suprimento(
            db, user=user, amount_cents=payload.amount_cents, reason=payload.reason
        )
    except CashError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _movement_to_out(db, mv)


# ---------- fechar ----------


def _imprimir_relatorio(
    db: Session, lines: list[str]
) -> tuple[bool, Optional[str]]:
    """Regra 6: impressora nunca desfaz operacao; so devolve o resultado."""
    try:
        get_printer(db).print_job(PrintJob(lines=lines))
        return True, None
    except Exception as exc:
        return False, str(exc)


@router.post(
    "/close",
    response_model=CashCloseOut,
    dependencies=[Depends(require_csrf)],
)
def close_cash(
    payload: CashCloseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_or_operator),
) -> CashCloseOut:
    try:
        s = cash_service.close_session(
            db,
            user=user,
            declared_cash_cents=payload.declared_cash_cents,
        )
    except CashError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    # Caixa ja esta fechado e gravado: relatorio nao pode reverter nada.
    lines: list[str] = []
    printed = False
    print_error: Optional[str] = None
    try:
        lines = cash_service.close_report_lines(db, s)
        printed, print_error = _imprimir_relatorio(db, lines)
    except Exception as exc:
        logger.exception("Falha ao montar relatorio de fechamento")
        print_error = str(exc)

    return CashCloseOut(
        **_session_to_out(db, s).model_dump(),
        report_lines=lines,
        printed=printed,
        print_error=print_error,
    )


@router.post(
    "/{session_id}/report/print",
    response_model=CashReportPrintOut,
    dependencies=[Depends(require_csrf)],
)
def print_close_report(
    session_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_or_operator),
) -> CashReportPrintOut:
    s = db.get(CashSession, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Caixa nao encontrado.")
    if s.status != "closed":
        raise HTTPException(status_code=409, detail="Este caixa ainda esta aberto.")
    printed, print_error = _imprimir_relatorio(
        db, cash_service.close_report_lines(db, s)
    )
    return CashReportPrintOut(printed=printed, print_error=print_error)


# ---------- admin: toggle setting ----------


@admin_router.put(
    "/settings/cash-required",
    response_model=CashRequiredToggle,
    dependencies=[Depends(require_csrf)],
)
def toggle_cash_required(
    payload: CashRequiredToggle,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> CashRequiredToggle:
    enabled = cash_service.set_cash_required(db, user, payload.enabled)
    return CashRequiredToggle(enabled=enabled)


@admin_router.get(
    "/settings/cash-required",
    response_model=CashRequiredToggle,
)
def get_cash_required(
    db: Session = Depends(get_db),
    _: User = Depends(require_user_or_operator),
) -> CashRequiredToggle:
    return CashRequiredToggle(enabled=cash_service.is_cash_required(db))
