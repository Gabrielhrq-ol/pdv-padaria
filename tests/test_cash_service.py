"""Testes unitarios do cash_service (sem HTTP)."""

from __future__ import annotations

import pytest

from app.models import (
    AuditLog,
    CashMovement,
    CashSession,
    Payment,
    Product,
    Sale,
    SaleItem,
    Setting,
    User,
)
from app.security import hash_password
from app.services.cash_service import (
    CashError,
    build_summary,
    calculate_expected_cash,
    close_session,
    get_open_session,
    is_cash_required,
    open_session,
    register_sangria,
    register_suprimento,
    require_open_session,
    set_cash_required,
)


# ---------- fixtures ----------


@pytest.fixture
def admin_db(session):
    u = User(
        name="Admin",
        username="adm",
        password_hash=hash_password("Senha1234"),
        role="admin",
        active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture
def caixa_db(session):
    u = User(
        name="Caixa",
        username="caixa1",
        password_hash=hash_password("Senha1234"),
        role="caixa",
        active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


# ---------- setting ----------


class TestSetting:
    def test_cash_required_default_false_quando_nao_existe(self, session):
        assert is_cash_required(session) is False

    def test_set_cash_required_true(self, session, admin_db):
        assert set_cash_required(session, admin_db, True) is True
        assert is_cash_required(session) is True

    def test_set_cash_required_toggle(self, session, admin_db):
        set_cash_required(session, admin_db, True)
        set_cash_required(session, admin_db, False)
        assert is_cash_required(session) is False

    def test_toggle_grava_audit(self, session, admin_db):
        set_cash_required(session, admin_db, True)
        audits = session.query(AuditLog).filter_by(action="cash_required_toggled").all()
        assert len(audits) == 1


# ---------- abertura ----------


class TestAbertura:
    def test_abre_sessao_simples(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=5000)
        assert s.status == "open"
        assert s.opening_cash_cents == 5000
        assert s.opened_by == admin_db.id

    def test_abre_com_notes(self, session, admin_db):
        s = open_session(
            session, user=admin_db, opening_cash_cents=10000, notes="Turno manha"
        )
        assert s.notes == "Turno manha"

    def test_notes_vazio_fica_none(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=0, notes="  ")
        assert s.notes is None

    def test_abertura_duplicada_falha(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=100)
        with pytest.raises(CashError) as exc:
            open_session(session, user=admin_db, opening_cash_cents=200)
        assert exc.value.status_code == 409

    def test_abertura_valor_negativo_falha(self, session, admin_db):
        with pytest.raises(CashError):
            open_session(session, user=admin_db, opening_cash_cents=-100)

    def test_abertura_grava_audit(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=100)
        audits = session.query(AuditLog).filter_by(action="cash_opened").all()
        assert len(audits) == 1


# ---------- get_open / require_open ----------


class TestGetOpen:
    def test_get_open_none_quando_vazio(self, session):
        assert get_open_session(session) is None

    def test_get_open_retorna_aberta(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=100)
        assert get_open_session(session).id == s.id

    def test_require_open_sem_sessao_falha(self, session):
        with pytest.raises(CashError) as exc:
            require_open_session(session)
        assert exc.value.status_code == 409


# ---------- sangria ----------


class TestSangria:
    def test_sangria_ok(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        mv = register_sangria(
            session,
            user=admin_db,
            amount_cents=2000,
            reason="pagamento fornecedor",
        )
        assert mv.type == "sangria"
        assert mv.amount_cents == 2000
        assert mv.reason == "pagamento fornecedor"

    def test_sangria_sem_motivo_falha(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        with pytest.raises(CashError):
            register_sangria(session, user=admin_db, amount_cents=1000, reason="")

    def test_sangria_motivo_curto_falha(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        with pytest.raises(CashError):
            register_sangria(session, user=admin_db, amount_cents=1000, reason="ab")

    def test_sangria_valor_zero_falha(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        with pytest.raises(CashError):
            register_sangria(
                session, user=admin_db, amount_cents=0, reason="teste"
            )

    def test_sangria_sem_caixa_aberto_falha(self, session, admin_db):
        with pytest.raises(CashError) as exc:
            register_sangria(
                session, user=admin_db, amount_cents=1000, reason="teste"
            )
        assert exc.value.status_code == 409

    def test_sangria_grava_audit(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        register_sangria(
            session, user=admin_db, amount_cents=500, reason="teste sangria"
        )
        audits = session.query(AuditLog).filter_by(action="cash_sangria").all()
        assert len(audits) == 1


# ---------- suprimento ----------


class TestSuprimento:
    def test_suprimento_com_motivo(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=0)
        mv = register_suprimento(
            session, user=admin_db, amount_cents=5000, reason="reforco de troco"
        )
        assert mv.type == "suprimento"
        assert mv.amount_cents == 5000
        assert mv.reason == "reforco de troco"

    def test_suprimento_sem_motivo_ok(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=0)
        mv = register_suprimento(session, user=admin_db, amount_cents=5000)
        assert mv.reason is None

    def test_suprimento_motivo_vazio_fica_none(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=0)
        mv = register_suprimento(
            session, user=admin_db, amount_cents=100, reason="   "
        )
        assert mv.reason is None

    def test_suprimento_valor_zero_falha(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=0)
        with pytest.raises(CashError):
            register_suprimento(session, user=admin_db, amount_cents=0)


# ---------- calculate expected ----------


def _finalize_sale_with_cash(
    session, user, product, price_cents, qty_milli, cash_amount, change=0
):
    """Helper: cria venda completa com um pagamento em dinheiro."""
    sale = Sale(
        number=1,
        user_id=user.id,
        cash_session_id=get_open_session(session).id,
        status="completed",
        subtotal_cents=price_cents,
        total_cents=price_cents,
    )
    session.add(sale)
    session.flush()
    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        product_name=product.name,
        unit=product.unit,
        unit_price_cents=price_cents,
        qty_milli=qty_milli,
        line_total_cents=price_cents,
    )
    session.add(item)
    pay = Payment(
        sale_id=sale.id,
        method="dinheiro",
        amount_cents=cash_amount,
        change_cents=change,
    )
    session.add(pay)
    session.commit()
    return sale


@pytest.fixture
def produto(session):
    p = Product(
        name="Pao",
        internal_code="100",
        unit="UN",
        price_cents=100,
        stock_milli=100_000,
        min_stock_milli=0,
        favorite=False,
        active=True,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


class TestExpectedCash:
    def test_expected_so_opening(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=10000)
        assert calculate_expected_cash(session, s) == 10000

    def test_expected_opening_mais_suprimento(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=10000)
        register_suprimento(session, user=admin_db, amount_cents=5000)
        assert calculate_expected_cash(session, s) == 15000

    def test_expected_menos_sangria(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=10000)
        register_sangria(
            session, user=admin_db, amount_cents=3000, reason="fornecedor"
        )
        assert calculate_expected_cash(session, s) == 7000

    def test_expected_com_venda_dinheiro(self, session, admin_db, produto):
        s = open_session(session, user=admin_db, opening_cash_cents=5000)
        # venda de 100 pagando 100 em dinheiro
        _finalize_sale_with_cash(
            session, admin_db, produto, 100, 1000, cash_amount=100, change=0
        )
        assert calculate_expected_cash(session, s) == 5100

    def test_expected_com_troco(self, session, admin_db, produto):
        s = open_session(session, user=admin_db, opening_cash_cents=0)
        # venda de 100, cliente deu 500 em dinheiro, troco de 400
        _finalize_sale_with_cash(
            session, admin_db, produto, 100, 1000, cash_amount=500, change=400
        )
        # dinheiro liquido entrou = 500 - 400 = 100
        assert calculate_expected_cash(session, s) == 100

    def test_expected_combinacao(self, session, admin_db, produto):
        s = open_session(session, user=admin_db, opening_cash_cents=10000)
        register_suprimento(session, user=admin_db, amount_cents=5000)
        register_sangria(
            session, user=admin_db, amount_cents=2000, reason="fornecedor"
        )
        _finalize_sale_with_cash(
            session, admin_db, produto, 300, 1000, cash_amount=500, change=200
        )
        # 10000 + 5000 - 2000 + (500 - 200) = 13300
        assert calculate_expected_cash(session, s) == 13300


class TestSummary:
    def test_summary_sem_movimentos(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=5000)
        summary = build_summary(session, s)
        assert summary.movements == []
        assert summary.payments_by_method == []
        assert summary.sales_count == 0
        assert summary.sales_cash_cents == 0
        assert summary.expected_cash_cents == 5000

    def test_summary_com_vendas(self, session, admin_db, produto):
        s = open_session(session, user=admin_db, opening_cash_cents=1000)
        _finalize_sale_with_cash(
            session, admin_db, produto, 200, 1000, cash_amount=200, change=0
        )
        summary = build_summary(session, s)
        assert summary.sales_count == 1
        assert summary.sales_cash_cents == 200
        assert len(summary.payments_by_method) == 1
        assert summary.payments_by_method[0].method == "dinheiro"
        assert summary.payments_by_method[0].total_cents == 200


# ---------- fechamento ----------


class TestFechamento:
    def test_fechar_sem_diferenca(self, session, admin_db):
        s = open_session(session, user=admin_db, opening_cash_cents=10000)
        closed = close_session(
            session, user=admin_db, declared_cash_cents=10000
        )
        assert closed.status == "closed"
        assert closed.closing_cash_declared_cents == 10000
        assert closed.closing_cash_expected_cents == 10000
        assert closed.closing_difference_cents == 0
        assert closed.difference_reason is None
        assert closed.closed_by == admin_db.id

    def test_fechar_com_sobra_requer_motivo(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        with pytest.raises(CashError):
            close_session(session, user=admin_db, declared_cash_cents=10100)

    def test_fechar_com_falta_requer_motivo(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        with pytest.raises(CashError):
            close_session(session, user=admin_db, declared_cash_cents=9500)

    def test_fechar_com_diferenca_e_motivo(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        closed = close_session(
            session,
            user=admin_db,
            declared_cash_cents=9950,
            difference_reason="faltou 50 centavos de troco",
        )
        assert closed.closing_difference_cents == -50
        assert closed.difference_reason == "faltou 50 centavos de troco"

    def test_fechar_sem_sessao_falha(self, session, admin_db):
        with pytest.raises(CashError) as exc:
            close_session(session, user=admin_db, declared_cash_cents=0)
        assert exc.value.status_code == 409

    def test_fechar_com_venda_aberta_falha(self, session, admin_db, produto):
        s = open_session(session, user=admin_db, opening_cash_cents=10000)
        # cria venda aberta
        venda = Sale(
            number=1,
            user_id=admin_db.id,
            cash_session_id=s.id,
            status="open",
            subtotal_cents=0,
            total_cents=0,
        )
        session.add(venda)
        session.commit()
        with pytest.raises(CashError) as exc:
            close_session(session, user=admin_db, declared_cash_cents=10000)
        assert exc.value.status_code == 409

    def test_fechar_declarado_negativo_falha(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=100)
        with pytest.raises(CashError):
            close_session(session, user=admin_db, declared_cash_cents=-1)

    def test_fechar_grava_audit(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=10000)
        close_session(session, user=admin_db, declared_cash_cents=10000)
        audits = session.query(AuditLog).filter_by(action="cash_closed").all()
        assert len(audits) == 1

    def test_apos_fechar_pode_abrir_outra(self, session, admin_db):
        open_session(session, user=admin_db, opening_cash_cents=100)
        close_session(session, user=admin_db, declared_cash_cents=100)
        s2 = open_session(session, user=admin_db, opening_cash_cents=200)
        assert s2.status == "open"
        assert s2.opening_cash_cents == 200
