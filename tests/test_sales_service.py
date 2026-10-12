"""Testes unitarios do sales_service (sem HTTP)."""

from __future__ import annotations

import pytest

from app.models import Product, User
from app.security import hash_password
from app.services.sales_service import (
    SalesError,
    add_item,
    cancel_sale,
    change_item_qty,
    create_open_sale,
    get_open_sale,
    remove_item,
    resolve_code,
)


@pytest.fixture
def user_db(session):
    u = User(
        name="X",
        username="caixa1",
        password_hash=hash_password("Senha1234"),
        role="caixa",
        active=True,
    )
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def produto_un(session):
    p = Product(
        name="Refrigerante",
        barcode="7891111111117",
        unit="UN",
        price_cents=1200,
        stock_milli=24000,
        min_stock_milli=0,
        favorite=False,
        active=True,
    )
    session.add(p)
    session.commit()
    return p


@pytest.fixture
def produto_kg(session):
    p = Product(
        name="Pao frances",
        internal_code="101",
        unit="KG",
        price_cents=1800,
        stock_milli=10000,
        min_stock_milli=1000,
        favorite=True,
        active=True,
    )
    session.add(p)
    session.commit()
    return p


class TestResolveCode:
    def test_barcode(self, session, produto_un) -> None:
        r = resolve_code(session, "7891111111117")
        assert r.product.id == produto_un.id
        assert r.qty_multiplier == 1

    def test_internal_code(self, session, produto_kg) -> None:
        r = resolve_code(session, "101")
        assert r.product.id == produto_kg.id
        assert r.qty_multiplier == 1

    def test_multiplicador(self, session, produto_un) -> None:
        r = resolve_code(session, "3*7891111111117")
        assert r.qty_multiplier == 3

    def test_multiplicador_com_espaco(self, session, produto_un) -> None:
        r = resolve_code(session, "3 * 7891111111117")
        assert r.qty_multiplier == 3

    def test_codigo_inexistente(self, session) -> None:
        with pytest.raises(SalesError) as exc:
            resolve_code(session, "999999")
        assert exc.value.status_code == 404

    def test_codigo_vazio(self, session) -> None:
        with pytest.raises(SalesError) as exc:
            resolve_code(session, "")
        assert exc.value.status_code == 422

    def test_multiplicador_zero(self, session, produto_un) -> None:
        with pytest.raises(SalesError):
            resolve_code(session, "0*7891111111117")

    def test_multiplicador_muito_grande(self, session, produto_un) -> None:
        with pytest.raises(SalesError):
            resolve_code(session, "99999*7891111111117")

    def test_produto_inativo(self, session, produto_un) -> None:
        produto_un.active = False
        session.commit()
        with pytest.raises(SalesError) as exc:
            resolve_code(session, "7891111111117")
        assert exc.value.status_code == 400


class TestCreateSale:
    def test_cria_venda(self, session, user_db) -> None:
        s = create_open_sale(session, user_db)
        session.commit()
        assert s.id is not None
        assert s.status == "open"
        assert s.number >= 1
        assert s.user_id == user_db.id
        assert s.total_cents == 0

    def test_idempotente(self, session, user_db) -> None:
        s1 = create_open_sale(session, user_db)
        session.commit()
        s2 = create_open_sale(session, user_db)
        session.commit()
        assert s1.id == s2.id

    def test_get_open(self, session, user_db) -> None:
        assert get_open_sale(session, user_db.id) is None
        s = create_open_sale(session, user_db)
        session.commit()
        assert get_open_sale(session, user_db.id).id == s.id


class TestAddItem:
    def test_adiciona_un(self, session, user_db, produto_un) -> None:
        sale = create_open_sale(session, user_db)
        item = add_item(session, sale, produto_un, 1000)
        session.commit()
        assert item.product_name == "Refrigerante"
        assert item.unit_price_cents == 1200
        assert item.line_total_cents == 1200
        assert sale.total_cents == 1200

    def test_adiciona_kg(self, session, user_db, produto_kg) -> None:
        sale = create_open_sale(session, user_db)
        item = add_item(session, sale, produto_kg, 350)  # 0,350 kg
        session.commit()
        assert item.line_total_cents == 630  # 0,350 x 18,00
        assert sale.total_cents == 630

    def test_agrupamento_mesmo_produto(self, session, user_db, produto_un) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        add_item(session, sale, produto_un, 1000)
        session.commit()
        assert len(sale.items) == 1
        assert sale.items[0].qty_milli == 2000
        assert sale.total_cents == 2400

    def test_preco_copiado_nao_muda_depois(
        self, session, user_db, produto_un
    ) -> None:
        """CLAUDE.md regra 4: preco e congelado no momento da venda."""
        sale = create_open_sale(session, user_db)
        item = add_item(session, sale, produto_un, 1000)
        session.commit()

        # Agora o produto fica mais caro
        produto_un.price_cents = 1500
        session.commit()

        # O item mantem o preco antigo
        session.refresh(item)
        assert item.unit_price_cents == 1200
        assert item.line_total_cents == 1200

    def test_rejeita_qty_zero(self, session, user_db, produto_un) -> None:
        sale = create_open_sale(session, user_db)
        with pytest.raises(SalesError):
            add_item(session, sale, produto_un, 0)

    def test_rejeita_qty_negativa(self, session, user_db, produto_un) -> None:
        sale = create_open_sale(session, user_db)
        with pytest.raises(SalesError):
            add_item(session, sale, produto_un, -1)

    def test_rejeita_produto_inativo(
        self, session, user_db, produto_un
    ) -> None:
        produto_un.active = False
        session.commit()
        sale = create_open_sale(session, user_db)
        with pytest.raises(SalesError):
            add_item(session, sale, produto_un, 1000)

    def test_nao_adiciona_em_venda_cancelada(
        self, session, user_db, produto_un
    ) -> None:
        sale = create_open_sale(session, user_db)
        sale.status = "cancelled"
        session.commit()
        with pytest.raises(SalesError):
            add_item(session, sale, produto_un, 1000)


class TestChangeAndRemove:
    def test_change_qty_recalcula_total(
        self, session, user_db, produto_un
    ) -> None:
        sale = create_open_sale(session, user_db)
        item = add_item(session, sale, produto_un, 1000)
        change_item_qty(session, sale, item, 3000)
        session.commit()
        assert item.qty_milli == 3000
        assert item.line_total_cents == 3600
        assert sale.total_cents == 3600

    def test_remove_item(self, session, user_db, produto_un, produto_kg) -> None:
        sale = create_open_sale(session, user_db)
        a = add_item(session, sale, produto_un, 1000)
        b = add_item(session, sale, produto_kg, 350)
        session.commit()
        assert sale.total_cents == 1830
        remove_item(session, sale, a)
        session.commit()
        assert sale.total_cents == 630
        assert len(sale.items) == 1
        assert sale.items[0].id == b.id


class TestCancel:
    def test_cancela(self, session, user_db, produto_un) -> None:
        sale = create_open_sale(session, user_db)
        add_item(session, sale, produto_un, 1000)
        cancel_sale(session, sale, user_db, "troco errado")
        session.commit()
        assert sale.status == "cancelled"
        assert sale.cancel_reason == "troco errado"
        assert sale.cancelled_by == user_db.id

    def test_rejeita_motivo_vazio(self, session, user_db) -> None:
        sale = create_open_sale(session, user_db)
        with pytest.raises(SalesError):
            cancel_sale(session, sale, user_db, "   ")

    def test_nao_cancela_duas_vezes(self, session, user_db) -> None:
        sale = create_open_sale(session, user_db)
        cancel_sale(session, sale, user_db, "motivo")
        session.commit()
        with pytest.raises(SalesError):
            cancel_sale(session, sale, user_db, "outro")
