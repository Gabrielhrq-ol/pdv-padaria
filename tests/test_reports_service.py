"""Testes unitarios do reports_service."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import (
    CashSession,
    Payment,
    Product,
    Sale,
    SaleItem,
    User,
    utc_now,
)
from app.security import hash_password
from app.services.reports_service import (
    closed_cash_sessions,
    dashboard,
    discounts_and_cancellations,
    sales_by_method,
    sales_by_operator,
    sales_by_period,
    top_products,
)


# ---------- fixtures ----------


@pytest.fixture
def user_a(session) -> User:
    u = User(
        name="Alice",
        username="alice",
        password_hash=hash_password("Senha1234"),
        role="caixa",
        active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture
def user_b(session) -> User:
    u = User(
        name="Bruno",
        username="bruno",
        password_hash=hash_password("Senha1234"),
        role="caixa",
        active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture
def produto(session) -> Product:
    p = Product(
        name="Pao",
        internal_code="100",
        unit="UN",
        price_cents=100,
        stock_milli=1_000_000,
        min_stock_milli=0,
        active=True,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.fixture
def produto_bolo(session) -> Product:
    p = Product(
        name="Bolo",
        internal_code="200",
        unit="KG",
        price_cents=3000,
        stock_milli=100_000,
        min_stock_milli=0,
        active=True,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _criar_venda_completed(
    session,
    user,
    produtos_qtd,
    *,
    finalized_at=None,
    method="dinheiro",
    cash_amount=None,
    change=0,
    discount_cents=0,
    discount_reason=None,
):
    """Helper: cria venda com itens + pagamento."""
    finalized = finalized_at or utc_now()
    total = 0
    for prod, qty, price in produtos_qtd:
        total += price * qty // 1000
    sub = total
    total_final = max(sub - discount_cents, 0)
    nxt = (
        session.query(Sale).count() + 1
    )  # simplificacao: pega id sequencial baseado em count
    sale = Sale(
        number=nxt,
        user_id=user.id,
        status="completed",
        subtotal_cents=sub,
        discount_cents=discount_cents,
        total_cents=total_final,
        finalized_at=finalized,
        discount_reason=discount_reason,
    )
    session.add(sale)
    session.flush()
    for prod, qty, price in produtos_qtd:
        line = price * qty // 1000
        session.add(
            SaleItem(
                sale_id=sale.id,
                product_id=prod.id,
                product_name=prod.name,
                unit=prod.unit,
                unit_price_cents=price,
                qty_milli=qty,
                line_total_cents=line,
            )
        )
    pay_amount = cash_amount if cash_amount is not None else total_final
    session.add(
        Payment(
            sale_id=sale.id,
            method=method,
            amount_cents=pay_amount,
            change_cents=change,
        )
    )
    session.commit()
    return sale


def _criar_venda_cancelled(session, user, cancelled_at=None, reason="desistiu"):
    nxt = session.query(Sale).count() + 1
    s = Sale(
        number=nxt,
        user_id=user.id,
        status="cancelled",
        subtotal_cents=100,
        total_cents=100,
        cancel_reason=reason,
        cancelled_by=user.id,
        cancelled_at=cancelled_at or utc_now(),
    )
    session.add(s)
    session.commit()
    return s


# ---------- dashboard ----------


class TestDashboard:
    def test_dashboard_vazio(self, session):
        d = dashboard(session)
        assert d.today_sales_count == 0
        assert d.today_revenue_cents == 0
        assert d.today_avg_ticket_cents == 0
        assert d.open_cash_session_id is None
        assert d.low_stock_count == 0

    def test_dashboard_conta_vendas_do_dia(self, session, user_a, produto):
        _criar_venda_completed(session, user_a, [(produto, 1000, 500)])
        _criar_venda_completed(session, user_a, [(produto, 1000, 300)])
        d = dashboard(session)
        assert d.today_sales_count == 2
        assert d.today_revenue_cents == 800
        assert d.today_avg_ticket_cents == 400

    def test_dashboard_ignora_vendas_antigas(self, session, user_a, produto):
        # venda de 2 dias atras
        _criar_venda_completed(
            session,
            user_a,
            [(produto, 1000, 500)],
            finalized_at=utc_now() - timedelta(days=2),
        )
        d = dashboard(session)
        assert d.today_sales_count == 0

    def test_dashboard_detecta_caixa_aberto(self, session, user_a):
        cs = CashSession(status="open", opened_by=user_a.id, opening_cash_cents=100)
        session.add(cs)
        session.commit()
        d = dashboard(session)
        assert d.open_cash_session_id == cs.id

    def test_dashboard_conta_low_stock(self, session, produto):
        produto.min_stock_milli = 100000
        produto.stock_milli = 50000  # abaixo do min
        session.commit()
        d = dashboard(session)
        assert d.low_stock_count == 1


# ---------- 1. vendas por periodo ----------


class TestSalesByPeriod:
    def test_vazio(self, session):
        r = sales_by_period(session)
        assert r.days == []
        assert r.total_count == 0
        assert r.total_revenue_cents == 0

    def test_agrupa_por_dia(self, session, user_a, produto):
        hoje = utc_now()
        _criar_venda_completed(session, user_a, [(produto, 1000, 200)], finalized_at=hoje)
        _criar_venda_completed(session, user_a, [(produto, 1000, 300)], finalized_at=hoje)
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 500)],
            finalized_at=hoje - timedelta(days=1),
        )
        r = sales_by_period(session)
        assert len(r.days) == 2
        assert r.total_count == 3
        assert r.total_revenue_cents == 1000

    def test_filtro_data(self, session, user_a, produto):
        hoje = utc_now()
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 500)],
            finalized_at=hoje - timedelta(days=5),
        )
        _criar_venda_completed(session, user_a, [(produto, 1000, 200)], finalized_at=hoje)
        r = sales_by_period(session, date_from=hoje - timedelta(hours=1))
        assert r.total_count == 1
        assert r.total_revenue_cents == 200

    def test_exclui_canceladas_por_padrao(self, session, user_a, produto):
        _criar_venda_completed(session, user_a, [(produto, 1000, 100)])
        _criar_venda_cancelled(session, user_a)
        r = sales_by_period(session)
        assert r.total_count == 1

    def test_inclui_canceladas_se_pedido(self, session, user_a, produto):
        _criar_venda_completed(session, user_a, [(produto, 1000, 100)])
        c = _criar_venda_cancelled(session, user_a)
        # cancelled nao tem finalized_at; stmt filtra por "finalized_at IS NOT NULL"
        # entao mesmo include_cancelled=True nao traz canceladas sem finalized.
        # Mas se setarmos finalized_at manualmente, aparece.
        c.finalized_at = utc_now()
        session.commit()
        r = sales_by_period(session, include_cancelled=True)
        assert r.total_count == 2


# ---------- 2. caixas fechados ----------


class TestClosedCash:
    def test_vazio(self, session):
        assert closed_cash_sessions(session) == []

    def test_lista_fechados(self, session, user_a):
        s1 = CashSession(
            status="closed",
            opened_by=user_a.id,
            opening_cash_cents=1000,
            closed_by=user_a.id,
            closed_at=utc_now(),
            closing_cash_declared_cents=1000,
            closing_cash_expected_cents=1000,
            closing_difference_cents=0,
        )
        s2 = CashSession(
            status="open", opened_by=user_a.id, opening_cash_cents=500
        )
        session.add_all([s1, s2])
        session.commit()
        rows = closed_cash_sessions(session)
        assert len(rows) == 1
        assert rows[0].id == s1.id
        assert rows[0].opened_by_name == "Alice"

    def test_filtro_data(self, session, user_a):
        s1 = CashSession(
            status="closed", opened_by=user_a.id, opening_cash_cents=100,
            closed_at=utc_now() - timedelta(days=10),
        )
        s2 = CashSession(
            status="closed", opened_by=user_a.id, opening_cash_cents=100,
            closed_at=utc_now(),
        )
        session.add_all([s1, s2])
        session.commit()
        rows = closed_cash_sessions(session, date_from=utc_now() - timedelta(days=1))
        assert len(rows) == 1
        assert rows[0].id == s2.id


# ---------- 3. vendas por operador ----------


class TestByOperator:
    def test_vazio(self, session):
        assert sales_by_operator(session) == []

    def test_agrupa_corretamente(self, session, user_a, user_b, produto):
        _criar_venda_completed(session, user_a, [(produto, 1000, 100)])
        _criar_venda_completed(session, user_a, [(produto, 1000, 200)])
        _criar_venda_completed(session, user_b, [(produto, 1000, 300)])
        rows = sales_by_operator(session)
        by_name = {r.user_name: r for r in rows}
        assert by_name["Alice"].sales_count == 2
        assert by_name["Alice"].revenue_cents == 300
        assert by_name["Bruno"].sales_count == 1
        assert by_name["Bruno"].revenue_cents == 300

    def test_inclui_canceladas(self, session, user_a, produto):
        _criar_venda_completed(session, user_a, [(produto, 1000, 100)])
        _criar_venda_cancelled(session, user_a)
        rows = sales_by_operator(session)
        assert len(rows) == 1
        assert rows[0].sales_count == 1
        assert rows[0].cancelled_count == 1

    def test_desconto_total(self, session, user_a, produto):
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 1000)],
            discount_cents=100,
            discount_reason="cliente fiel",
        )
        rows = sales_by_operator(session)
        assert rows[0].discount_total_cents == 100


# ---------- 4. vendas por forma ----------


class TestByMethod:
    def test_vazio(self, session):
        assert sales_by_method(session) == []

    def test_agrupa_por_method(self, session, user_a, produto):
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 100)], method="dinheiro"
        )
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 200)], method="dinheiro"
        )
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 300)], method="pix"
        )
        rows = sales_by_method(session)
        by = {r.method: r for r in rows}
        assert by["dinheiro"].sales_count == 2
        assert by["dinheiro"].total_cents == 300
        assert by["pix"].sales_count == 1


# ---------- 5. top produtos ----------


class TestTopProducts:
    def test_vazio(self, session):
        assert top_products(session) == []

    def test_order_by_revenue(self, session, user_a, produto, produto_bolo):
        _criar_venda_completed(
            session, user_a, [(produto, 10_000, 100)]  # 10 UN x 1,00 = 10,00
        )
        _criar_venda_completed(
            session, user_a, [(produto_bolo, 2_000, 3000)]  # 2 KG x 30,00 = 60,00
        )
        rows = top_products(session, order_by="revenue")
        assert rows[0].product_name == "Bolo"
        assert rows[0].revenue_cents == 6000

    def test_order_by_qty(self, session, user_a, produto, produto_bolo):
        _criar_venda_completed(
            session, user_a, [(produto, 10_000, 100)]
        )
        _criar_venda_completed(
            session, user_a, [(produto_bolo, 2_000, 3000)]
        )
        rows = top_products(session, order_by="qty")
        assert rows[0].product_name == "Pao"
        assert rows[0].qty_milli == 10_000


# ---------- 6. descontos e cancelamentos ----------


class TestDiscountsCancellations:
    def test_vazio(self, session):
        assert discounts_and_cancellations(session) == []

    def test_lista_descontos(self, session, user_a, produto):
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 1000)],
            discount_cents=100,
            discount_reason="promocao",
        )
        rows = discounts_and_cancellations(session)
        assert len(rows) == 1
        assert rows[0].kind == "desconto"
        assert rows[0].discount_cents == 100
        assert rows[0].reason == "promocao"

    def test_lista_cancelamentos(self, session, user_a):
        _criar_venda_cancelled(session, user_a, reason="desistencia do cliente")
        rows = discounts_and_cancellations(session)
        assert len(rows) == 1
        assert rows[0].kind == "cancelamento"
        assert rows[0].reason == "desistencia do cliente"

    def test_ignora_vendas_sem_desconto(self, session, user_a, produto):
        _criar_venda_completed(session, user_a, [(produto, 1000, 500)])
        rows = discounts_and_cancellations(session)
        assert rows == []

    def test_combina_desconto_e_cancelamento(self, session, user_a, produto):
        _criar_venda_completed(
            session, user_a, [(produto, 1000, 1000)],
            discount_cents=50,
            discount_reason="x",
        )
        _criar_venda_cancelled(session, user_a)
        rows = discounts_and_cancellations(session)
        assert len(rows) == 2
        kinds = {r.kind for r in rows}
        assert kinds == {"desconto", "cancelamento"}
