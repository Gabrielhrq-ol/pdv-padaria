"""
Testes dos endpoints /api/cash/* e /api/admin/settings/cash-required
e a pagina /caixa.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestPaginaCaixa:
    def test_anonimo_redireciona_login(self, client: TestClient) -> None:
        r = client.get("/caixa", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]

    def test_caixa_pode_abrir(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/caixa")
        assert r.status_code == 200
        assert "Caixa" in r.text

    def test_admin_pode_abrir(self, admin_client: TestClient) -> None:
        r = admin_client.get("/caixa")
        assert r.status_code == 200


class TestCurrent:
    def test_404_quando_sem_sessao(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/cash/current")
        assert r.status_code == 404

    def test_summary_404_quando_sem_sessao(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/cash/current/summary")
        assert r.status_code == 404


class TestAbrir:
    def test_abrir_fluxo_feliz(self, admin_client: TestClient) -> None:
        r = admin_client.post(
            "/api/cash/open", json={"opening_cash_cents": 10000}
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "open"
        assert data["opening_cash_cents"] == 10000

    def test_abrir_caixa_tambem_pode(self, caixa_client: TestClient) -> None:
        r = caixa_client.post(
            "/api/cash/open", json={"opening_cash_cents": 5000}
        )
        assert r.status_code == 200

    def test_abrir_anonimo_401(self, client: TestClient) -> None:
        r = client.post("/api/cash/open", json={"opening_cash_cents": 1000})
        assert r.status_code == 401

    def test_abrir_sem_csrf_falha(self, admin_client: TestClient) -> None:
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.post(
            "/api/cash/open", json={"opening_cash_cents": 1000}
        )
        assert r.status_code == 403

    def test_abrir_duplicado_409(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 100})
        r = admin_client.post(
            "/api/cash/open", json={"opening_cash_cents": 200}
        )
        assert r.status_code == 409

    def test_abrir_valor_negativo_422(self, admin_client: TestClient) -> None:
        r = admin_client.post(
            "/api/cash/open", json={"opening_cash_cents": -1}
        )
        assert r.status_code == 422

    def test_abrir_campo_extra_rejeitado(self, admin_client: TestClient) -> None:
        r = admin_client.post(
            "/api/cash/open",
            json={"opening_cash_cents": 100, "foo": "bar"},
        )
        assert r.status_code == 422


class TestMovimentos:
    def test_sangria_sem_motivo_422(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 10000})
        r = admin_client.post(
            "/api/cash/sangria", json={"amount_cents": 1000}
        )
        assert r.status_code == 422

    def test_sangria_fluxo_feliz(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 10000})
        r = admin_client.post(
            "/api/cash/sangria",
            json={"amount_cents": 2500, "reason": "fornecedor da farinha"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "sangria"
        assert data["amount_cents"] == 2500

    def test_suprimento_sem_motivo_ok(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 100})
        r = admin_client.post(
            "/api/cash/suprimento", json={"amount_cents": 500}
        )
        assert r.status_code == 200
        assert r.json()["reason"] is None

    def test_suprimento_com_motivo(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 100})
        r = admin_client.post(
            "/api/cash/suprimento",
            json={"amount_cents": 500, "reason": "reforco de troco"},
        )
        assert r.status_code == 200
        assert r.json()["reason"] == "reforco de troco"

    def test_sem_caixa_aberto_409(self, admin_client: TestClient) -> None:
        r = admin_client.post(
            "/api/cash/sangria",
            json={"amount_cents": 100, "reason": "teste123"},
        )
        assert r.status_code == 409

    def test_sangria_sem_csrf(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 100})
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.post(
            "/api/cash/sangria",
            json={"amount_cents": 100, "reason": "teste123"},
        )
        assert r.status_code == 403


class TestSummary:
    def test_summary_zera(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 10000})
        r = admin_client.get("/api/cash/current/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["expected_cash_cents"] == 10000
        assert data["sales_cash_cents"] == 0
        assert data["sales_count"] == 0
        assert data["movements"] == []
        assert data["payments_by_method"] == []

    def test_summary_apos_movimentos(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 10000})
        admin_client.post(
            "/api/cash/suprimento",
            json={"amount_cents": 5000},
        )
        admin_client.post(
            "/api/cash/sangria",
            json={"amount_cents": 2000, "reason": "fornecedor"},
        )
        r = admin_client.get("/api/cash/current/summary")
        data = r.json()
        assert data["expected_cash_cents"] == 10000 + 5000 - 2000
        assert len(data["movements"]) == 2


class TestFechar:
    def test_fechar_sem_diferenca(self, admin_client: TestClient) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 10000})
        r = admin_client.post(
            "/api/cash/close", json={"declared_cash_cents": 10000}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "closed"

    def test_fechar_com_diferenca_sem_motivo_422(
        self, admin_client: TestClient
    ) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 10000})
        r = admin_client.post(
            "/api/cash/close", json={"declared_cash_cents": 9500}
        )
        assert r.status_code == 422

    def test_fechar_com_diferenca_e_motivo(
        self, admin_client: TestClient
    ) -> None:
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 10000})
        r = admin_client.post(
            "/api/cash/close",
            json={
                "declared_cash_cents": 10050,
                "difference_reason": "cliente trocou nota",
            },
        )
        assert r.status_code == 200
        assert r.json()["closing_difference_cents"] == 50


class TestToggleCashRequired:
    def test_toggle_requer_admin(self, caixa_client: TestClient) -> None:
        r = caixa_client.put(
            "/api/admin/settings/cash-required", json={"enabled": True}
        )
        assert r.status_code == 403

    def test_admin_pode_toggle(self, admin_client: TestClient) -> None:
        r = admin_client.put(
            "/api/admin/settings/cash-required", json={"enabled": True}
        )
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_get_cash_required(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/admin/settings/cash-required")
        assert r.status_code == 200
        assert r.json()["enabled"] is False  # default
