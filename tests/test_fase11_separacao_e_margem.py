"""
Testes da Fase 11:
- Snapshot de unit_cost_cents em sale_items
- Margem no dashboard e endpoint /api/reports/margins
- Redirect por papel apos login (admin -> /admin, caixa -> /pdv)
- Pagina /admin so pra admin
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models import Payment, Product, Sale, SaleItem, User, utc_now


# ---------- helpers ----------


def _criar_produto(SessionTesting, **kwargs) -> int:
    s = SessionTesting()
    try:
        defaults = {
            "name": "Pao",
            "internal_code": "100",
            "unit": "UN",
            "price_cents": 1000,
            "cost_cents": 400,  # custo real
            "stock_milli": 100_000,
            "min_stock_milli": 0,
            "active": True,
        }
        defaults.update(kwargs)
        p = Product(**defaults)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id
    finally:
        s.close()


def _criar_venda_com_item(SessionTesting, user_id, product_id, qty_milli, price):
    s = SessionTesting()
    try:
        p = s.get(Product, product_id)
        nxt = s.query(Sale).count() + 1
        sale = Sale(
            number=nxt,
            user_id=user_id,
            status="completed",
            subtotal_cents=price,
            total_cents=price,
            finalized_at=utc_now(),
        )
        s.add(sale)
        s.flush()
        line_total = price * qty_milli // 1000
        s.add(
            SaleItem(
                sale_id=sale.id,
                product_id=p.id,
                product_name=p.name,
                unit=p.unit,
                unit_price_cents=price,
                unit_cost_cents=p.cost_cents,  # snapshot
                qty_milli=qty_milli,
                line_total_cents=line_total,
            )
        )
        s.add(
            Payment(
                sale_id=sale.id, method="dinheiro",
                amount_cents=price, change_cents=0,
            )
        )
        s.commit()
        return sale.id
    finally:
        s.close()


# ---------- redirect por papel ----------


class TestRedirectPorPapel:
    def test_admin_root_vai_pra_admin(self, admin_client: TestClient) -> None:
        r = admin_client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/admin"

    def test_caixa_root_vai_pra_pdv(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/pdv"

    def test_anonimo_root_vai_pra_login(self, client: TestClient) -> None:
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]

    def test_login_admin_logado_redireciona_pra_admin(
        self, admin_client: TestClient
    ) -> None:
        r = admin_client.get("/login", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/admin"

    def test_login_caixa_logado_redireciona_pra_pdv(
        self, caixa_client: TestClient
    ) -> None:
        r = caixa_client.get("/login", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/pdv"


# ---------- pagina /admin ----------


class TestPaginaAdmin:
    def test_admin_acessa(self, admin_client: TestClient) -> None:
        r = admin_client.get("/admin")
        assert r.status_code == 200
        assert "Painel do dono" in r.text
        assert "Margem bruta" in r.text

    def test_caixa_redireciona(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/admin", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/pdv"

    def test_anonimo_redireciona_login(self, client: TestClient) -> None:
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]


# ---------- snapshot de cost no sale_item ----------


class TestCostSnapshot:
    def test_sale_item_copia_cost(
        self, SessionTesting, admin_user
    ) -> None:
        pid = _criar_produto(SessionTesting, cost_cents=500)
        _criar_venda_com_item(
            SessionTesting, admin_user.id, pid, qty_milli=1000, price=1000
        )
        s = SessionTesting()
        try:
            item = s.query(SaleItem).first()
            assert item.unit_cost_cents == 500
        finally:
            s.close()

    def test_sale_item_cost_pode_ser_null(
        self, SessionTesting, admin_user
    ) -> None:
        pid = _criar_produto(SessionTesting, cost_cents=None)
        _criar_venda_com_item(
            SessionTesting, admin_user.id, pid, qty_milli=1000, price=1000
        )
        s = SessionTesting()
        try:
            item = s.query(SaleItem).first()
            assert item.unit_cost_cents is None
        finally:
            s.close()


# ---------- dashboard com margem ----------


class TestDashboardComMargem:
    def test_dashboard_sem_vendas(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/dashboard")
        data = r.json()
        assert data["today_margin_cents"] == 0
        assert data["today_margin_pct"] == 0.0
        assert data["today_margin_covered_items"] == 0

    def test_dashboard_calcula_margem(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        # Venda de 1 UN a R$ 10,00 (preco=1000, custo=400) => margem 600, 60%
        pid = _criar_produto(SessionTesting, cost_cents=400)
        _criar_venda_com_item(
            SessionTesting, admin_user.id, pid, qty_milli=1000, price=1000
        )
        r = admin_client.get("/api/reports/dashboard")
        data = r.json()
        assert data["today_margin_cents"] == 600
        assert data["today_margin_pct"] == 60.0
        assert data["today_margin_covered_items"] == 1
        assert data["today_margin_total_items"] == 1

    def test_dashboard_ignora_itens_sem_custo(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        # Um com custo, um sem custo
        pid1 = _criar_produto(SessionTesting, name="A", internal_code="A1", cost_cents=400)
        pid2 = _criar_produto(SessionTesting, name="B", internal_code="B1", cost_cents=None)
        _criar_venda_com_item(SessionTesting, admin_user.id, pid1, 1000, 1000)
        _criar_venda_com_item(SessionTesting, admin_user.id, pid2, 1000, 2000)
        r = admin_client.get("/api/reports/dashboard")
        data = r.json()
        # So o item com custo entra: margem = 1000 - 400 = 600; pct = 60
        assert data["today_margin_cents"] == 600
        assert data["today_margin_pct"] == 60.0
        assert data["today_margin_covered_items"] == 1
        assert data["today_margin_total_items"] == 2


# ---------- endpoint /margins ----------


class TestEndpointMargins:
    def test_caixa_nao_acessa(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/api/reports/margins")
        assert r.status_code == 403

    def test_vazio(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/margins")
        assert r.status_code == 200
        data = r.json()
        assert data["rows"] == []
        assert data["total_margin_cents"] == 0
        assert data["covered_items"] == 0

    def test_agrupa_por_produto(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        pid = _criar_produto(SessionTesting, cost_cents=400)
        _criar_venda_com_item(SessionTesting, admin_user.id, pid, 1000, 1000)
        _criar_venda_com_item(SessionTesting, admin_user.id, pid, 1000, 1000)
        r = admin_client.get("/api/reports/margins")
        data = r.json()
        assert len(data["rows"]) == 1
        row = data["rows"][0]
        # 2 vendas de 1 UN a R$10 (preco), custo 400:
        # revenue = 2000, cost = 800, margem = 1200
        assert row["revenue_cents"] == 2000
        assert row["cost_cents"] == 800
        assert row["margin_cents"] == 1200
        assert row["margin_pct"] == 60.0

    def test_conta_uncovered(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        pid = _criar_produto(SessionTesting, cost_cents=None)
        _criar_venda_com_item(SessionTesting, admin_user.id, pid, 1000, 500)
        r = admin_client.get("/api/reports/margins")
        data = r.json()
        assert data["rows"] == []
        assert data["uncovered_items"] == 1

    def test_order_by_invalido_422(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/margins?order_by=xyz")
        assert r.status_code == 422

    def test_csv_tem_bom_e_total(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        pid = _criar_produto(SessionTesting, cost_cents=400)
        _criar_venda_com_item(SessionTesting, admin_user.id, pid, 1000, 1000)
        r = admin_client.get("/api/reports/margins/csv")
        assert r.status_code == 200
        assert r.content.startswith(b"\xef\xbb\xbf")
        text = r.content.decode("utf-8-sig")
        assert "Produto" in text
        assert "Margem" in text
        assert "TOTAL" in text
