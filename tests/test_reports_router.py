"""Testes dos endpoints /api/reports/*. Admin-only."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Payment, Product, Sale, SaleItem, utc_now


# ---------- helpers ----------


def _seed_venda(SessionTesting, user_id, total=500, method="dinheiro", change=0):
    s = SessionTesting()
    try:
        p = Product(
            name="X",
            internal_code=f"P{total}",
            unit="UN",
            price_cents=total,
            stock_milli=1_000_000,
            min_stock_milli=0,
            active=True,
        )
        s.add(p)
        s.flush()
        nxt = s.query(Sale).count() + 1
        sale = Sale(
            number=nxt,
            user_id=user_id,
            status="completed",
            subtotal_cents=total,
            total_cents=total,
            finalized_at=utc_now(),
        )
        s.add(sale)
        s.flush()
        s.add(
            SaleItem(
                sale_id=sale.id,
                product_id=p.id,
                product_name=p.name,
                unit=p.unit,
                unit_price_cents=total,
                qty_milli=1000,
                line_total_cents=total,
            )
        )
        s.add(
            Payment(
                sale_id=sale.id,
                method=method,
                amount_cents=total + change,
                change_cents=change,
            )
        )
        s.commit()
        return sale.id
    finally:
        s.close()


# ---------- autorizacao ----------


class TestAutorizacao:
    def test_anonimo_401(self, client: TestClient) -> None:
        r = client.get("/api/reports/dashboard")
        assert r.status_code == 401

    def test_caixa_403(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/api/reports/dashboard")
        assert r.status_code == 403

    def test_admin_200(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/dashboard")
        assert r.status_code == 200


class TestAutorizacaoCadaRota:
    @classmethod
    def rotas(cls):
        return [
            "/api/reports/dashboard",
            "/api/reports/sales-period",
            "/api/reports/cash-sessions",
            "/api/reports/sales-by-operator",
            "/api/reports/sales-by-method",
            "/api/reports/top-products",
            "/api/reports/discounts-cancellations",
            "/api/reports/sales-period/csv",
            "/api/reports/cash-sessions/csv",
            "/api/reports/sales-by-operator/csv",
            "/api/reports/sales-by-method/csv",
            "/api/reports/top-products/csv",
            "/api/reports/discounts-cancellations/csv",
        ]

    def test_caixa_bloqueado_em_todas(self, caixa_client: TestClient) -> None:
        for rota in TestAutorizacaoCadaRota.rotas():
            r = caixa_client.get(rota)
            assert r.status_code == 403, f"{rota} deveria ser 403, veio {r.status_code}"


# ---------- dashboard ----------


class TestDashboardEndpoint:
    def test_dashboard_zera(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert data["today_sales_count"] == 0
        assert data["today_revenue_cents"] == 0
        assert data["open_cash_session_id"] is None

    def test_dashboard_apos_vendas(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _seed_venda(SessionTesting, admin_user.id, total=200)
        _seed_venda(SessionTesting, admin_user.id, total=300)
        r = admin_client.get("/api/reports/dashboard")
        data = r.json()
        assert data["today_sales_count"] == 2
        assert data["today_revenue_cents"] == 500
        assert data["today_avg_ticket_cents"] == 250


# ---------- relatorios json ----------


class TestRelatorios:
    def test_sales_period_vazio(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/sales-period")
        assert r.status_code == 200
        data = r.json()
        assert data["days"] == []
        assert data["total_count"] == 0

    def test_sales_period_popula(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _seed_venda(SessionTesting, admin_user.id, total=400)
        r = admin_client.get("/api/reports/sales-period")
        data = r.json()
        assert data["total_count"] == 1
        assert data["total_revenue_cents"] == 400

    def test_sales_by_operator(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _seed_venda(SessionTesting, admin_user.id, total=100)
        r = admin_client.get("/api/reports/sales-by-operator")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["user_name"] == "Admin de Teste"

    def test_sales_by_method(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _seed_venda(SessionTesting, admin_user.id, total=100, method="dinheiro")
        _seed_venda(SessionTesting, admin_user.id, total=200, method="pix")
        r = admin_client.get("/api/reports/sales-by-method")
        rows = r.json()
        methods = {row["method"] for row in rows}
        assert methods == {"dinheiro", "pix"}

    def test_top_products_order_by_invalido_422(
        self, admin_client: TestClient
    ) -> None:
        r = admin_client.get("/api/reports/top-products?order_by=invalido")
        assert r.status_code == 422

    def test_top_products_ok(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _seed_venda(SessionTesting, admin_user.id, total=100)
        r = admin_client.get("/api/reports/top-products?order_by=revenue&limit=10")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1

    def test_cash_sessions_vazio(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/cash-sessions")
        assert r.status_code == 200
        assert r.json() == []

    def test_discounts_cancellations_vazio(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/discounts-cancellations")
        assert r.status_code == 200
        assert r.json() == []


# ---------- CSV ----------


class TestCSV:
    def test_csv_content_type(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/sales-period/csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        assert "vendas-por-periodo.csv" in r.headers["content-disposition"]

    def test_csv_tem_bom_utf8(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/sales-period/csv")
        # BOM UTF-8 em bytes
        assert r.content.startswith(b"\xef\xbb\xbf")

    def test_csv_sales_period_popula(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _seed_venda(SessionTesting, admin_user.id, total=250)
        r = admin_client.get("/api/reports/sales-period/csv")
        text = r.content.decode("utf-8-sig")
        assert "Dia" in text
        assert "TOTAL" in text
        assert "2,50" in text  # 250 centavos = R$ 2,50

    def test_csv_separator_ponto_virgula(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/sales-period/csv")
        text = r.content.decode("utf-8-sig")
        # Header tem ;
        first_line = text.split("\n")[0]
        assert ";" in first_line

    def test_csv_cash_sessions_header(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/reports/cash-sessions/csv")
        text = r.content.decode("utf-8-sig")
        assert "Fundo inicial" in text
        assert "Diferenca" in text

    def test_csv_top_products(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _seed_venda(SessionTesting, admin_user.id, total=100)
        r = admin_client.get("/api/reports/top-products/csv")
        text = r.content.decode("utf-8-sig")
        assert "Produto" in text
        assert "Faturamento" in text


# ---------- pagina HTML ----------


class TestPaginaAdminReports:
    def test_caixa_redireciona(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/admin/reports", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"].endswith("/products")

    def test_admin_renderiza(self, admin_client: TestClient) -> None:
        r = admin_client.get("/admin/reports")
        assert r.status_code == 200
        assert "Relatorios" in r.text
        assert "panel-period" in r.text
