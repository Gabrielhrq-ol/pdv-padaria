"""
Servico de relatorios (Fase 8).

Funcoes puras (recebem Session, retornam dataclass). O router empacota
em schemas e em CSV. Admin-only (checado no router).

Padrao de filtros de data:
- date_from e date_to sao datetime UTC naive (como o resto do sistema).
- date_from inclusivo; date_to inclusivo. Default sem filtro quando None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CashSession,
    Payment,
    Product,
    Sale,
    SaleItem,
    User,
    utc_now,
)


# ---------- helpers ----------


def _apply_date_filter(stmt, column, date_from, date_to):
    if date_from is not None:
        stmt = stmt.where(column >= date_from)
    if date_to is not None:
        stmt = stmt.where(column <= date_to)
    return stmt


def _today_window() -> tuple[datetime, datetime]:
    now = utc_now()
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start, end


# ---------- dashboard ----------


@dataclass
class DashboardTotals:
    today_sales_count: int
    today_revenue_cents: int
    today_avg_ticket_cents: int
    today_margin_cents: int
    today_margin_pct: float  # 0..100; 0 se revenue_coberto == 0
    today_margin_covered_items: int  # itens com cost_cents nao-nulo
    today_margin_total_items: int  # itens vendidos no dia
    open_cash_session_id: Optional[int]
    low_stock_count: int


def _today_margin(db: Session, start: datetime, end: datetime) -> tuple[int, int, int, int]:
    """
    Retorna (margin_cents, revenue_coberto_cents, covered_items, total_items)
    dos sale_items do dia. Ignora linhas com unit_cost_cents NULL.
    - margin = sum(line_total_cents - unit_cost_cents * qty_milli / 1000)
      aproximando com arredondamento igual ao de line_total_cents.
    """
    # total_items (todas as linhas do dia)
    total_items = int(
        db.execute(
            select(func.count(SaleItem.id))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.status == "completed",
                Sale.finalized_at >= start,
                Sale.finalized_at <= end,
            )
        ).scalar_one() or 0
    )
    # itens com custo cadastrado
    covered_items = int(
        db.execute(
            select(func.count(SaleItem.id))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.status == "completed",
                Sale.finalized_at >= start,
                Sale.finalized_at <= end,
                SaleItem.unit_cost_cents.is_not(None),
            )
        ).scalar_one() or 0
    )
    if covered_items == 0:
        return 0, 0, 0, total_items

    # soma revenue e cost_raw (unit_cost * qty_milli). Divide por 1000 no
    # Python com arredondamento banker's half-up, pra evitar perda de precisao
    # por dividir linha a linha no SQL (0.5+0.5=1 em float, 0+0=0 em int).
    row = db.execute(
        select(
            func.coalesce(func.sum(SaleItem.line_total_cents), 0),
            func.coalesce(
                func.sum(SaleItem.unit_cost_cents * SaleItem.qty_milli), 0
            ),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.status == "completed",
            Sale.finalized_at >= start,
            Sale.finalized_at <= end,
            SaleItem.unit_cost_cents.is_not(None),
        )
    ).one()
    revenue_coberto = int(row[0] or 0)
    cost_raw = int(row[1] or 0)  # unit_cost * qty_milli, antes de dividir por 1000
    cost_total = (cost_raw + 500) // 1000
    return revenue_coberto - cost_total, revenue_coberto, covered_items, total_items


def dashboard(db: Session) -> DashboardTotals:
    """Totais do dia + estado de caixa + alertas + margem bruta."""
    start, end = _today_window()
    row = db.execute(
        select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_cents), 0),
        ).where(
            Sale.status == "completed",
            Sale.finalized_at >= start,
            Sale.finalized_at <= end,
        )
    ).one()
    count = int(row[0] or 0)
    revenue = int(row[1] or 0)
    avg = revenue // count if count > 0 else 0

    margin, revenue_coberto, covered, total_items = _today_margin(db, start, end)
    margin_pct = (margin / revenue_coberto * 100.0) if revenue_coberto > 0 else 0.0

    open_cash = db.execute(
        select(CashSession.id).where(CashSession.status == "open")
    ).scalar_one_or_none()

    low = db.execute(
        select(func.count(Product.id)).where(
            Product.active.is_(True),
            Product.min_stock_milli > 0,
            Product.stock_milli <= Product.min_stock_milli,
        )
    ).scalar_one()

    return DashboardTotals(
        today_sales_count=count,
        today_revenue_cents=revenue,
        today_avg_ticket_cents=avg,
        today_margin_cents=margin,
        today_margin_pct=round(margin_pct, 2),
        today_margin_covered_items=covered,
        today_margin_total_items=total_items,
        open_cash_session_id=open_cash,
        low_stock_count=int(low or 0),
    )


# ---------- 1. vendas por periodo (dia a dia) ----------


@dataclass
class SalesPeriodDay:
    day: str  # YYYY-MM-DD
    sales_count: int
    revenue_cents: int
    avg_ticket_cents: int


@dataclass
class SalesPeriodResult:
    days: list[SalesPeriodDay]
    total_count: int
    total_revenue_cents: int
    total_avg_ticket_cents: int


def sales_by_period(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    include_cancelled: bool = False,
) -> SalesPeriodResult:
    """Faturamento agrupado por dia (date(finalized_at))."""
    # SQLite func date() retorna YYYY-MM-DD
    day_expr = func.date(Sale.finalized_at)
    stmt = (
        select(
            day_expr.label("day"),
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_cents), 0),
        )
        .where(Sale.finalized_at.is_not(None))
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if not include_cancelled:
        stmt = stmt.where(Sale.status == "completed")
    stmt = _apply_date_filter(stmt, Sale.finalized_at, date_from, date_to)

    days = []
    total_count = 0
    total_revenue = 0
    for row in db.execute(stmt).all():
        count = int(row[1] or 0)
        revenue = int(row[2] or 0)
        avg = revenue // count if count > 0 else 0
        days.append(
            SalesPeriodDay(
                day=str(row[0]),
                sales_count=count,
                revenue_cents=revenue,
                avg_ticket_cents=avg,
            )
        )
        total_count += count
        total_revenue += revenue
    total_avg = total_revenue // total_count if total_count > 0 else 0
    return SalesPeriodResult(
        days=days,
        total_count=total_count,
        total_revenue_cents=total_revenue,
        total_avg_ticket_cents=total_avg,
    )


# ---------- 2. caixas fechados ----------


@dataclass
class ClosedCashRow:
    id: int
    opened_by_name: Optional[str]
    opened_at: datetime
    closed_by_name: Optional[str]
    closed_at: Optional[datetime]
    opening_cash_cents: int
    expected_cash_cents: Optional[int]
    declared_cash_cents: Optional[int]
    difference_cents: Optional[int]
    difference_reason: Optional[str]


def closed_cash_sessions(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 100,
) -> list[ClosedCashRow]:
    """Historico de sessoes fechadas. Admin usa pra conferir diferencas."""
    opener = User.__table__.alias("opener")
    closer = User.__table__.alias("closer")
    stmt = (
        select(
            CashSession.id,
            opener.c.name,
            CashSession.opened_at,
            closer.c.name,
            CashSession.closed_at,
            CashSession.opening_cash_cents,
            CashSession.closing_cash_expected_cents,
            CashSession.closing_cash_declared_cents,
            CashSession.closing_difference_cents,
            CashSession.difference_reason,
        )
        .join(opener, opener.c.id == CashSession.opened_by)
        .outerjoin(closer, closer.c.id == CashSession.closed_by)
        .where(CashSession.status == "closed")
        .order_by(CashSession.closed_at.desc())
        .limit(limit)
    )
    stmt = _apply_date_filter(stmt, CashSession.closed_at, date_from, date_to)
    rows = []
    for r in db.execute(stmt).all():
        rows.append(
            ClosedCashRow(
                id=int(r[0]),
                opened_by_name=r[1],
                opened_at=r[2],
                closed_by_name=r[3],
                closed_at=r[4],
                opening_cash_cents=int(r[5]),
                expected_cash_cents=int(r[6]) if r[6] is not None else None,
                declared_cash_cents=int(r[7]) if r[7] is not None else None,
                difference_cents=int(r[8]) if r[8] is not None else None,
                difference_reason=r[9],
            )
        )
    return rows


# ---------- 3. vendas por operador ----------


@dataclass
class OperatorStats:
    user_id: int
    user_name: str
    sales_count: int
    revenue_cents: int
    discount_total_cents: int
    cancelled_count: int


def sales_by_operator(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[OperatorStats]:
    completed = (
        select(
            Sale.user_id,
            func.count(Sale.id).label("count"),
            func.coalesce(func.sum(Sale.total_cents), 0).label("revenue"),
            func.coalesce(func.sum(Sale.discount_cents), 0).label("discount"),
        )
        .where(Sale.status == "completed")
    )
    completed = _apply_date_filter(completed, Sale.finalized_at, date_from, date_to)
    completed = completed.group_by(Sale.user_id).subquery()

    cancelled = (
        select(
            Sale.user_id,
            func.count(Sale.id).label("count"),
        )
        .where(Sale.status == "cancelled")
    )
    cancelled = _apply_date_filter(cancelled, Sale.cancelled_at, date_from, date_to)
    cancelled = cancelled.group_by(Sale.user_id).subquery()

    stmt = (
        select(
            User.id,
            User.name,
            func.coalesce(completed.c.count, 0),
            func.coalesce(completed.c.revenue, 0),
            func.coalesce(completed.c.discount, 0),
            func.coalesce(cancelled.c.count, 0),
        )
        .outerjoin(completed, completed.c.user_id == User.id)
        .outerjoin(cancelled, cancelled.c.user_id == User.id)
        .where(
            (completed.c.count.is_not(None)) | (cancelled.c.count.is_not(None))
        )
        .order_by(User.name)
    )
    out = []
    for r in db.execute(stmt).all():
        out.append(
            OperatorStats(
                user_id=int(r[0]),
                user_name=r[1],
                sales_count=int(r[2] or 0),
                revenue_cents=int(r[3] or 0),
                discount_total_cents=int(r[4] or 0),
                cancelled_count=int(r[5] or 0),
            )
        )
    return out


# ---------- 4. vendas por forma de pagamento ----------


@dataclass
class MethodStats:
    method: str
    sales_count: int
    total_cents: int


def sales_by_method(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[MethodStats]:
    stmt = (
        select(
            Payment.method,
            func.count(func.distinct(Sale.id)),
            func.coalesce(func.sum(Payment.amount_cents - Payment.change_cents), 0),
        )
        .join(Sale, Sale.id == Payment.sale_id)
        .where(Sale.status == "completed")
        .group_by(Payment.method)
        .order_by(Payment.method)
    )
    stmt = _apply_date_filter(stmt, Sale.finalized_at, date_from, date_to)
    out = []
    for r in db.execute(stmt).all():
        out.append(
            MethodStats(
                method=r[0],
                sales_count=int(r[1] or 0),
                total_cents=int(r[2] or 0),
            )
        )
    return out


# ---------- 5. top produtos ----------


@dataclass
class TopProductRow:
    product_id: int
    product_name: str
    unit: str
    qty_milli: int
    revenue_cents: int


def top_products(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    order_by: str = "revenue",  # "revenue" | "qty"
    limit: int = 20,
) -> list[TopProductRow]:
    if limit <= 0 or limit > 500:
        limit = 20
    if order_by not in ("revenue", "qty"):
        order_by = "revenue"

    stmt = (
        select(
            SaleItem.product_id,
            SaleItem.product_name,
            SaleItem.unit,
            func.coalesce(func.sum(SaleItem.qty_milli), 0).label("qty"),
            func.coalesce(func.sum(SaleItem.line_total_cents), 0).label("revenue"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(Sale.status == "completed")
        .group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.unit)
    )
    stmt = _apply_date_filter(stmt, Sale.finalized_at, date_from, date_to)
    if order_by == "revenue":
        stmt = stmt.order_by(func.coalesce(func.sum(SaleItem.line_total_cents), 0).desc())
    else:
        stmt = stmt.order_by(func.coalesce(func.sum(SaleItem.qty_milli), 0).desc())
    stmt = stmt.limit(limit)

    out = []
    for r in db.execute(stmt).all():
        out.append(
            TopProductRow(
                product_id=int(r[0]),
                product_name=r[1],
                unit=r[2],
                qty_milli=int(r[3] or 0),
                revenue_cents=int(r[4] or 0),
            )
        )
    return out


# ---------- 6. descontos e cancelamentos ----------


@dataclass
class DiscountRow:
    sale_id: int
    sale_number: int
    kind: str  # "desconto" | "cancelamento"
    user_name: Optional[str]
    occurred_at: Optional[datetime]
    total_cents: int
    discount_cents: int
    reason: Optional[str]


def discounts_and_cancellations(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 500,
) -> list[DiscountRow]:
    """Vendas com desconto (status completed e discount_cents > 0) OR canceladas."""
    stmt_disc = (
        select(
            Sale.id,
            Sale.number,
            User.name,
            Sale.finalized_at,
            Sale.total_cents,
            Sale.discount_cents,
            Sale.discount_reason,
        )
        .join(User, User.id == Sale.user_id)
        .where(Sale.status == "completed", Sale.discount_cents > 0)
    )
    stmt_disc = _apply_date_filter(stmt_disc, Sale.finalized_at, date_from, date_to)

    stmt_canc = (
        select(
            Sale.id,
            Sale.number,
            User.name,
            Sale.cancelled_at,
            Sale.total_cents,
            Sale.discount_cents,
            Sale.cancel_reason,
        )
        .join(User, User.id == Sale.user_id)
        .where(Sale.status == "cancelled")
    )
    stmt_canc = _apply_date_filter(stmt_canc, Sale.cancelled_at, date_from, date_to)

    rows: list[DiscountRow] = []
    for r in db.execute(stmt_disc).all():
        rows.append(
            DiscountRow(
                sale_id=int(r[0]),
                sale_number=int(r[1]),
                kind="desconto",
                user_name=r[2],
                occurred_at=r[3],
                total_cents=int(r[4] or 0),
                discount_cents=int(r[5] or 0),
                reason=r[6],
            )
        )
    for r in db.execute(stmt_canc).all():
        rows.append(
            DiscountRow(
                sale_id=int(r[0]),
                sale_number=int(r[1]),
                kind="cancelamento",
                user_name=r[2],
                occurred_at=r[3],
                total_cents=int(r[4] or 0),
                discount_cents=int(r[5] or 0),
                reason=r[6],
            )
        )
    # ordena por data decrescente; None vai pro fim
    rows.sort(
        key=lambda x: x.occurred_at.timestamp() if x.occurred_at else 0,
        reverse=True,
    )
    return rows[:limit]


# ---------- 7. margem por produto (Fase 11) ----------


@dataclass
class MarginProductRow:
    product_id: int
    product_name: str
    unit: str
    qty_milli: int
    revenue_cents: int
    cost_cents: int
    margin_cents: int
    margin_pct: float  # (margin / revenue) * 100


@dataclass
class MarginSummary:
    rows: list[MarginProductRow]
    total_revenue_cents: int
    total_cost_cents: int
    total_margin_cents: int
    total_margin_pct: float
    covered_items: int
    uncovered_items: int  # linhas sem unit_cost_cents


def margin_by_product(
    db: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    order_by: str = "margin",  # "margin" | "pct" | "revenue"
    limit: int = 100,
) -> MarginSummary:
    """
    Agrupa por produto considerando SOMENTE linhas com unit_cost_cents.
    Produtos sem custo cadastrado aparecem no contador uncovered_items
    mas nao entram nos totais nem na lista.
    """
    if limit <= 0 or limit > 1000:
        limit = 100
    if order_by not in ("margin", "pct", "revenue"):
        order_by = "margin"

    # linhas sem custo
    stmt_unc = (
        select(func.count(SaleItem.id))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.status == "completed",
            SaleItem.unit_cost_cents.is_(None),
        )
    )
    stmt_unc = _apply_date_filter(stmt_unc, Sale.finalized_at, date_from, date_to)
    uncovered = int(db.execute(stmt_unc).scalar_one() or 0)

    # agregacao por produto, so com custo. cost_raw e somado antes de dividir
    # por 1000 (arredondamento consistente, feito no Python).
    stmt = (
        select(
            SaleItem.product_id,
            SaleItem.product_name,
            SaleItem.unit,
            func.coalesce(func.sum(SaleItem.qty_milli), 0).label("qty"),
            func.coalesce(func.sum(SaleItem.line_total_cents), 0).label("revenue"),
            func.coalesce(
                func.sum(SaleItem.unit_cost_cents * SaleItem.qty_milli), 0
            ).label("cost_raw"),
            func.count(SaleItem.id).label("items"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.status == "completed",
            SaleItem.unit_cost_cents.is_not(None),
        )
        .group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.unit)
    )
    stmt = _apply_date_filter(stmt, Sale.finalized_at, date_from, date_to)

    rows_raw = db.execute(stmt).all()
    rows: list[MarginProductRow] = []
    total_rev = 0
    total_cost = 0
    covered = 0
    for r in rows_raw:
        rev = int(r.revenue or 0)
        cost = (int(r.cost_raw or 0) + 500) // 1000
        margin = rev - cost
        pct = (margin / rev * 100.0) if rev > 0 else 0.0
        rows.append(
            MarginProductRow(
                product_id=int(r.product_id),
                product_name=r.product_name,
                unit=r.unit,
                qty_milli=int(r.qty or 0),
                revenue_cents=rev,
                cost_cents=cost,
                margin_cents=margin,
                margin_pct=round(pct, 2),
            )
        )
        total_rev += rev
        total_cost += cost
        covered += int(r.items or 0)

    if order_by == "pct":
        rows.sort(key=lambda x: x.margin_pct, reverse=True)
    elif order_by == "revenue":
        rows.sort(key=lambda x: x.revenue_cents, reverse=True)
    else:
        rows.sort(key=lambda x: x.margin_cents, reverse=True)
    rows = rows[:limit]

    total_margin = total_rev - total_cost
    total_pct = (total_margin / total_rev * 100.0) if total_rev > 0 else 0.0

    return MarginSummary(
        rows=rows,
        total_revenue_cents=total_rev,
        total_cost_cents=total_cost,
        total_margin_cents=total_margin,
        total_margin_pct=round(total_pct, 2),
        covered_items=covered,
        uncovered_items=uncovered,
    )
