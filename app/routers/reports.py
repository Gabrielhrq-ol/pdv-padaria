"""
Relatorios (Fase 8). Admin-only. Export JSON e CSV.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin
from app.models import User
from app.schemas import (
    ClosedCashRowOut,
    DashboardOut,
    DiscountRowOut,
    MethodStatsOut,
    OperatorStatsOut,
    SalesPeriodDayOut,
    SalesPeriodOut,
    TopProductRowOut,
)
from app.services import reports_service


router = APIRouter(prefix="/api/reports", tags=["reports"])


# ---------- helpers CSV ----------


def _csv_response(filename: str, header: list[str], rows: list[list]) -> StreamingResponse:
    """Streaming CSV com BOM UTF-8 pra Excel abrir acentos."""

    def iter_csv():
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        yield "﻿" + buf.getvalue()  # BOM UTF-8 pro Excel
        buf.seek(0)
        buf.truncate(0)
        for row in rows:
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        iter_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def _brl(cents: int) -> str:
    neg = cents < 0
    abs_c = -cents if neg else cents
    reais, resto = divmod(abs_c, 100)
    return ("-" if neg else "") + f"{reais},{resto:02d}"


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def _fmt_qty(qty_milli: int, unit: str) -> str:
    neg = qty_milli < 0
    abs_q = -qty_milli if neg else qty_milli
    inteiro, resto = divmod(abs_q, 1000)
    if unit == "UN" and resto == 0:
        return ("-" if neg else "") + str(inteiro)
    return ("-" if neg else "") + f"{inteiro},{resto:03d}"


# ---------- dashboard ----------


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DashboardOut:
    d = reports_service.dashboard(db)
    return DashboardOut(
        today_sales_count=d.today_sales_count,
        today_revenue_cents=d.today_revenue_cents,
        today_avg_ticket_cents=d.today_avg_ticket_cents,
        open_cash_session_id=d.open_cash_session_id,
        low_stock_count=d.low_stock_count,
    )


# ---------- 1. vendas por periodo ----------


@router.get("/sales-period", response_model=SalesPeriodOut)
def sales_period(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    include_cancelled: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> SalesPeriodOut:
    r = reports_service.sales_by_period(
        db, date_from=date_from, date_to=date_to, include_cancelled=include_cancelled
    )
    return SalesPeriodOut(
        days=[
            SalesPeriodDayOut(
                day=d.day,
                sales_count=d.sales_count,
                revenue_cents=d.revenue_cents,
                avg_ticket_cents=d.avg_ticket_cents,
            )
            for d in r.days
        ],
        total_count=r.total_count,
        total_revenue_cents=r.total_revenue_cents,
        total_avg_ticket_cents=r.total_avg_ticket_cents,
    )


@router.get("/sales-period/csv")
def sales_period_csv(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    include_cancelled: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StreamingResponse:
    r = reports_service.sales_by_period(
        db, date_from=date_from, date_to=date_to, include_cancelled=include_cancelled
    )
    rows = [
        [d.day, d.sales_count, _brl(d.revenue_cents), _brl(d.avg_ticket_cents)]
        for d in r.days
    ]
    rows.append(
        ["TOTAL", r.total_count, _brl(r.total_revenue_cents), _brl(r.total_avg_ticket_cents)]
    )
    return _csv_response(
        "vendas-por-periodo.csv",
        ["Dia", "Qtd vendas", "Faturamento (R$)", "Ticket medio (R$)"],
        rows,
    )


# ---------- 2. caixas fechados ----------


@router.get("/cash-sessions", response_model=list[ClosedCashRowOut])
def cash_sessions(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ClosedCashRowOut]:
    rows = reports_service.closed_cash_sessions(
        db, date_from=date_from, date_to=date_to, limit=limit
    )
    return [
        ClosedCashRowOut(
            id=r.id,
            opened_by_name=r.opened_by_name,
            opened_at=r.opened_at,
            closed_by_name=r.closed_by_name,
            closed_at=r.closed_at,
            opening_cash_cents=r.opening_cash_cents,
            expected_cash_cents=r.expected_cash_cents,
            declared_cash_cents=r.declared_cash_cents,
            difference_cents=r.difference_cents,
            difference_reason=r.difference_reason,
        )
        for r in rows
    ]


@router.get("/cash-sessions/csv")
def cash_sessions_csv(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StreamingResponse:
    rows = reports_service.closed_cash_sessions(
        db, date_from=date_from, date_to=date_to, limit=limit
    )
    data = [
        [
            r.id,
            _fmt_dt(r.opened_at),
            r.opened_by_name or "",
            _fmt_dt(r.closed_at),
            r.closed_by_name or "",
            _brl(r.opening_cash_cents),
            _brl(r.expected_cash_cents or 0),
            _brl(r.declared_cash_cents or 0),
            _brl(r.difference_cents or 0),
            r.difference_reason or "",
        ]
        for r in rows
    ]
    return _csv_response(
        "caixas-fechados.csv",
        [
            "ID",
            "Aberto em",
            "Aberto por",
            "Fechado em",
            "Fechado por",
            "Fundo inicial",
            "Esperado",
            "Declarado",
            "Diferenca",
            "Motivo",
        ],
        data,
    )


# ---------- 3. vendas por operador ----------


@router.get("/sales-by-operator", response_model=list[OperatorStatsOut])
def sales_operator(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[OperatorStatsOut]:
    rows = reports_service.sales_by_operator(db, date_from=date_from, date_to=date_to)
    return [
        OperatorStatsOut(
            user_id=r.user_id,
            user_name=r.user_name,
            sales_count=r.sales_count,
            revenue_cents=r.revenue_cents,
            discount_total_cents=r.discount_total_cents,
            cancelled_count=r.cancelled_count,
        )
        for r in rows
    ]


@router.get("/sales-by-operator/csv")
def sales_operator_csv(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StreamingResponse:
    rows = reports_service.sales_by_operator(db, date_from=date_from, date_to=date_to)
    data = [
        [
            r.user_name,
            r.sales_count,
            _brl(r.revenue_cents),
            _brl(r.discount_total_cents),
            r.cancelled_count,
        ]
        for r in rows
    ]
    return _csv_response(
        "vendas-por-operador.csv",
        ["Operador", "Qtd vendas", "Faturamento", "Descontos", "Canceladas"],
        data,
    )


# ---------- 4. vendas por forma de pagamento ----------


@router.get("/sales-by-method", response_model=list[MethodStatsOut])
def sales_method(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[MethodStatsOut]:
    rows = reports_service.sales_by_method(db, date_from=date_from, date_to=date_to)
    return [
        MethodStatsOut(method=r.method, sales_count=r.sales_count, total_cents=r.total_cents)
        for r in rows
    ]


@router.get("/sales-by-method/csv")
def sales_method_csv(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StreamingResponse:
    rows = reports_service.sales_by_method(db, date_from=date_from, date_to=date_to)
    data = [[r.method, r.sales_count, _brl(r.total_cents)] for r in rows]
    return _csv_response(
        "vendas-por-forma.csv",
        ["Forma", "Qtd vendas", "Total liquido"],
        data,
    )


# ---------- 5. top produtos ----------


@router.get("/top-products", response_model=list[TopProductRowOut])
def top_products(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    order_by: str = Query(default="revenue", pattern="^(revenue|qty)$"),
    limit: int = Query(default=20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[TopProductRowOut]:
    rows = reports_service.top_products(
        db, date_from=date_from, date_to=date_to, order_by=order_by, limit=limit
    )
    return [
        TopProductRowOut(
            product_id=r.product_id,
            product_name=r.product_name,
            unit=r.unit,  # type: ignore[arg-type]
            qty_milli=r.qty_milli,
            revenue_cents=r.revenue_cents,
        )
        for r in rows
    ]


@router.get("/top-products/csv")
def top_products_csv(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    order_by: str = Query(default="revenue", pattern="^(revenue|qty)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StreamingResponse:
    rows = reports_service.top_products(
        db, date_from=date_from, date_to=date_to, order_by=order_by, limit=limit
    )
    data = [
        [r.product_name, r.unit, _fmt_qty(r.qty_milli, r.unit), _brl(r.revenue_cents)]
        for r in rows
    ]
    return _csv_response(
        "top-produtos.csv",
        ["Produto", "Un.", "Qtd vendida", "Faturamento"],
        data,
    )


# ---------- 6. descontos e cancelamentos ----------


@router.get("/discounts-cancellations", response_model=list[DiscountRowOut])
def discounts_cancellations(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DiscountRowOut]:
    rows = reports_service.discounts_and_cancellations(
        db, date_from=date_from, date_to=date_to, limit=limit
    )
    return [
        DiscountRowOut(
            sale_id=r.sale_id,
            sale_number=r.sale_number,
            kind=r.kind,  # type: ignore[arg-type]
            user_name=r.user_name,
            occurred_at=r.occurred_at,
            total_cents=r.total_cents,
            discount_cents=r.discount_cents,
            reason=r.reason,
        )
        for r in rows
    ]


@router.get("/discounts-cancellations/csv")
def discounts_cancellations_csv(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StreamingResponse:
    rows = reports_service.discounts_and_cancellations(
        db, date_from=date_from, date_to=date_to, limit=limit
    )
    data = [
        [
            r.sale_number,
            r.kind,
            _fmt_dt(r.occurred_at),
            r.user_name or "",
            _brl(r.total_cents),
            _brl(r.discount_cents),
            r.reason or "",
        ]
        for r in rows
    ]
    return _csv_response(
        "descontos-cancelamentos.csv",
        ["Venda #", "Tipo", "Data", "Operador", "Total", "Desconto", "Motivo"],
        data,
    )
