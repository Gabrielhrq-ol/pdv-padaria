"""Testes unitarios de finalize_sale, reverse_sale e calculate_change."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Payment, Product, Setting, StockMovement, User
from app.security import hash_password
from app.services.sales_service import (
    SalesError,
    add_item,
    calculate_change,
    create_open_sale,
    finalize_sale,
    reverse_sale,
    get_last_completed,
)


@pytest.fixture
def user_db(session):
    u = User(
        name="Op", username="op1",
        password_hash=hash_password("Senha1234"),
        role="caixa", active=True,
    )
    session.add(u); session.commit()
    return u


@pytest.fixture
def produto_un(session):
    p = Product(
        name="Refri", barcode="7891", unit="UN",
        price_cents=1200, stock_milli=24000, min_stock_milli=0,
        favorite=False, active=True,
    )
    session.add(p); session.commit()
    return p


@pytest.fixture
def produto_kg(session):
    p = Product(
        name="Pao", internal_code="101", unit="KG",
        price_cents=1800, stock_milli=10000, min_stock_milli=0,
        favorite=False, active=True,
    )
    session.add(p); session.commit()
    return p


@pytest.fixture
def payment_methods_setting(session):
    s = Setting(
        key="payment_methods",
        value='["dinheiro","debito","credito","pix","outros"]',
    )
    session.add(s); session.commit()


# ---------- calculate_change ----------


class TestCalculateChange:
    def test_dinheiro_exato(self) -> None:
        r = calculate_change([("dinheiro", 1200)], 1200)
        assert r.change_cents == 0
        assert r.change_payment_index == -1

    def test_dinheiro_com_troco(self) -> None:
        r = calculate_change([("dinheiro", 2000)], 1200)
        assert r.change_cents == 800
        assert r.change_payment_index == 0

    def test_misto_cartao_mais_dinheiro(self) -> None:
        r = calculate_change(
            [("debito", 500), ("dinheiro", 1000)],
            1200,
        )
        # Pago 1500, total 1200, excesso 300 (do dinheiro)
        assert r.change_cents == 300
        assert r.change_payment_index == 1  # ultimo dinheiro

    def test_cartao_nao_pode_exceder(self) -> None:
        with pytest.raises(SalesError) as exc:
            calculate_change([("credito", 1500)], 1200)
        assert exc.value.status_code == 400
        assert "excede" in exc.value.message.lower()

    def test_valor_insuficiente(self) -> None:
        with pytest.raises(SalesError) as exc:
            calculate_change([("dinheiro", 500)], 1200)
        assert exc.value.status_code == 400
        assert "insuficiente" in exc.value.message.lower()

    def test_multiplos_dinheiros_ultimo_leva_troco(self) -> None:
        r = calculate_change(
            [("dinheiro", 500), ("dinheiro", 1000)],
            1200,
        )
        assert r.change_cents == 300
        assert r.change_payment_index == 1

    def test_vazio(self) -> None:
        with pytest.raises(SalesError):
            calculate_change([], 100)


# ---------- finalize_sale ----------


class TestFinalize:
    def test_finaliza_simples(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()

        finalize_sale(session, sale, user_db, [("dinheiro", 1200)])
        session.commit()

        assert sale.status == "completed"
        assert sale.finalized_at is not None
        assert sale.total_cents == 1200
        assert len(sale.payments) == 1
        assert sale.payments[0].change_cents == 0

    def test_estoque_abaixa_e_movement_criado(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        estoque_inicial = produto_un.stock_milli  # 24000
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 3000)  # 3 un
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 3600)])
        session.commit()

        session.refresh(produto_un)
        assert produto_un.stock_milli == estoque_inicial - 3000

        movs = session.execute(
            select(StockMovement).where(StockMovement.product_id == produto_un.id)
        ).scalars().all()
        assert len(movs) == 1
        assert movs[0].type == "venda"
        assert movs[0].qty_milli == -3000
        assert movs[0].sale_id == sale.id

    def test_troco_distribuido_no_ultimo_dinheiro(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 2000)])
        session.commit()

        p = sale.payments[0]
        assert p.change_cents == 800

    def test_misto_com_troco_so_no_dinheiro(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        finalize_sale(
            session, sale, user_db,
            [("debito", 500), ("dinheiro", 1000)],
        )
        session.commit()
        assert len(sale.payments) == 2
        assert sale.payments[0].method == "debito"
        assert sale.payments[0].change_cents == 0
        assert sale.payments[1].method == "dinheiro"
        assert sale.payments[1].change_cents == 300

    def test_bloqueia_dupla_finalizacao(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 1200)])
        session.commit()
        with pytest.raises(SalesError) as exc:
            finalize_sale(session, sale, user_db, [("dinheiro", 1200)])
        assert exc.value.status_code == 409

    def test_sem_itens_bloqueado(
        self, session, user_db, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        session.commit()
        with pytest.raises(SalesError) as exc:
            finalize_sale(session, sale, user_db, [("dinheiro", 100)])
        assert exc.value.status_code == 400

    def test_metodo_nao_permitido(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        with pytest.raises(SalesError) as exc:
            finalize_sale(session, sale, user_db, [("cheque", 1200)])
        assert "permitida" in exc.value.message.lower()

    def test_desconto_sem_motivo_bloqueado(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        with pytest.raises(SalesError) as exc:
            finalize_sale(
                session, sale, user_db,
                [("dinheiro", 1000)],
                discount_cents=200,
                discount_reason="",
            )
        assert "motivo" in exc.value.message.lower()

    def test_desconto_maior_que_subtotal_bloqueado(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        with pytest.raises(SalesError):
            finalize_sale(
                session, sale, user_db,
                [("dinheiro", 100)],
                discount_cents=5000,
                discount_reason="x",
            )

    def test_desconto_aplica_no_total(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        finalize_sale(
            session, sale, user_db,
            [("dinheiro", 1000)],
            discount_cents=200,
            discount_reason="cliente frequente",
        )
        session.commit()
        assert sale.total_cents == 1000  # 1200 - 200
        assert sale.discount_cents == 200
        assert sale.discount_reason == "cliente frequente"

    def test_permite_estoque_negativo(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        """Decisao 9 do cliente: NUNCA bloquear por estoque."""
        produto_un.stock_milli = 500
        session.commit()
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)  # vende mais do que tem
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 1200)])
        session.commit()
        session.refresh(produto_un)
        assert produto_un.stock_milli == -500  # negativo permitido


class TestEstoqueBateComMovements:
    """Invariante critico: product.stock_milli = soma(movements.qty_milli) + inicial."""

    def test_tres_vendas_consecutivas(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        inicial = produto_un.stock_milli
        for _ in range(3):
            sale = create_open_sale(session, user_db)
            add_item(session, sale, produto_un, 1000)
            session.commit()
            finalize_sale(session, sale, user_db, [("dinheiro", 1200)])
            session.commit()

        session.refresh(produto_un)
        movs = session.execute(
            select(StockMovement).where(StockMovement.product_id == produto_un.id)
        ).scalars().all()
        soma = sum(m.qty_milli for m in movs)
        assert produto_un.stock_milli == inicial + soma
        assert len(movs) == 3

    def test_linhas_repetidas_baixam_e_estornam_estoque(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        inicial = produto_un.stock_milli
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        add_item(session, sale, produto_un, 1000)
        add_item(session, sale, produto_un, 3000)
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 6000)])
        session.commit()
        session.refresh(produto_un)
        assert produto_un.stock_milli == inicial - 5000

        reverse_sale(session, sale, user_db, "cliente desistiu")
        session.commit()
        session.refresh(produto_un)
        assert produto_un.stock_milli == inicial
        movs = session.execute(
            select(StockMovement).where(StockMovement.product_id == produto_un.id)
        ).scalars().all()
        assert sum(m.qty_milli for m in movs) == 0


# ---------- reverse_sale ----------


class TestReverse:
    def test_estorna_estoque(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        inicial = produto_un.stock_milli
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 2000)
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 2400)])
        session.commit()
        session.refresh(produto_un)
        assert produto_un.stock_milli == inicial - 2000

        reverse_sale(session, sale, user_db, "cliente desistiu")
        session.commit()

        assert sale.status == "cancelled"
        assert sale.cancel_reason == "cliente desistiu"
        assert sale.cancelled_by == user_db.id
        session.refresh(produto_un)
        assert produto_un.stock_milli == inicial  # voltou

    def test_cria_movement_de_estorno(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 1200)])
        session.commit()
        reverse_sale(session, sale, user_db, "motivo")
        session.commit()

        movs = session.execute(
            select(StockMovement)
            .where(StockMovement.sale_id == sale.id)
            .order_by(StockMovement.id)
        ).scalars().all()
        assert len(movs) == 2
        assert movs[0].type == "venda"
        assert movs[0].qty_milli == -1000
        assert movs[1].type == "estorno"
        assert movs[1].qty_milli == 1000

    def test_nao_estorna_venda_open(
        self, session, user_db
    ) -> None:
        sale = create_open_sale(session, user_db)
        session.commit()
        with pytest.raises(SalesError) as exc:
            reverse_sale(session, sale, user_db, "x")
        assert exc.value.status_code == 409

    def test_motivo_obrigatorio(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        finalize_sale(session, sale, user_db, [("dinheiro", 1200)])
        session.commit()
        with pytest.raises(SalesError):
            reverse_sale(session, sale, user_db, "   ")


# ---------- last_completed ----------


class TestLastCompleted:
    def test_vazio_se_nao_tem_vendas(self, session, user_db) -> None:
        assert get_last_completed(session, user_db.id) is None

    def test_retorna_ultima_completed(
        self, session, user_db, produto_un, payment_methods_setting
    ) -> None:
        s1 = create_open_sale(session, user_db)
        add_item(session, s1, produto_un, 1000)
        session.commit()
        finalize_sale(session, s1, user_db, [("dinheiro", 1200)])
        session.commit()

        last = get_last_completed(session, user_db.id)
        assert last.id == s1.id
