"""
Testes dos endpoints /api/admin/stock/* e da pagina /admin/stock.

Cobre autorizacao, CSRF, audit_log, filtros e pagina HTML.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Product


# ---------- helpers ----------


def _criar_produto(SessionTesting, **kwargs) -> int:
    s = SessionTesting()
    try:
        defaults = {
            "name": "Produto Teste",
            "barcode": None,
            "internal_code": None,
            "unit": "UN",
            "price_cents": 1000,
            "stock_milli": 10_000,
            "min_stock_milli": 0,
            "favorite": False,
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


# ---------- autorizacao ----------


class TestAutorizacao:
    def test_entrada_anonimo_401(self, client: TestClient) -> None:
        r = client.post(
            "/api/admin/stock/entry",
            json={"product_id": 1, "qty_milli": 1000},
        )
        assert r.status_code == 401

    def test_entrada_caixa_403(
        self, caixa_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = caixa_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1000},
        )
        assert r.status_code == 403

    def test_perda_caixa_403(self, caixa_client: TestClient, SessionTesting) -> None:
        pid = _criar_produto(SessionTesting)
        r = caixa_client.post(
            "/api/admin/stock/loss",
            json={"product_id": pid, "qty_milli": 1000, "reason": "Teste"},
        )
        assert r.status_code == 403

    def test_ajuste_caixa_403(self, caixa_client: TestClient, SessionTesting) -> None:
        pid = _criar_produto(SessionTesting)
        r = caixa_client.post(
            "/api/admin/stock/adjustment",
            json={"product_id": pid, "new_stock_milli": 5000, "reason": "Teste"},
        )
        assert r.status_code == 403

    def test_historico_caixa_pode_ler(
        self, caixa_client: TestClient, SessionTesting
    ) -> None:
        r = caixa_client.get("/api/admin/stock/movements")
        assert r.status_code == 200
        assert r.json() == []

    def test_low_stock_caixa_pode_ler(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/api/admin/stock/low")
        assert r.status_code == 200
        assert r.json() == []

    def test_pagina_admin_stock_caixa_redirecionado(
        self, caixa_client: TestClient
    ) -> None:
        r = caixa_client.get("/admin/stock", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"].endswith("/products")

    def test_pagina_admin_stock_admin_renderiza(
        self, admin_client: TestClient
    ) -> None:
        r = admin_client.get("/admin/stock")
        assert r.status_code == 200
        assert "Gestao de estoque" in r.text
        # Confere que os ids chaves estao presentes
        assert 'id="form-entrada"' in r.text
        assert 'id="form-perda"' in r.text
        assert 'id="form-ajuste"' in r.text


# ---------- CSRF ----------


class TestCSRF:
    def test_entrada_sem_csrf_falha(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        # TestClient ja tem X-CSRF-Token no header; vamos removelo
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1000},
        )
        assert r.status_code == 403

    def test_perda_sem_csrf_falha(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.post(
            "/api/admin/stock/loss",
            json={"product_id": pid, "qty_milli": 1000, "reason": "Teste"},
        )
        assert r.status_code == 403

    def test_ajuste_sem_csrf_falha(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.post(
            "/api/admin/stock/adjustment",
            json={"product_id": pid, "new_stock_milli": 5000, "reason": "Teste"},
        )
        assert r.status_code == 403


# ---------- Fluxo feliz entrada ----------


class TestEntrada:
    def test_entrada_sem_motivo_ok(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, name="Refri", stock_milli=5_000)
        r = admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 3_000},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "entrada"
        assert data["qty_milli"] == 3_000
        assert data["reason"] is None
        assert data["product_id"] == pid
        assert data["product_name"] == "Refri"

    def test_entrada_com_motivo_opcional_ok(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1_000, "reason": "nota 42"},
        )
        assert r.status_code == 200
        assert r.json()["reason"] == "nota 42"

    def test_entrada_motivo_vazio_aceito_como_none(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1_000, "reason": "   "},
        )
        assert r.status_code == 200
        assert r.json()["reason"] is None

    def test_entrada_qty_zero_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 0},
        )
        assert r.status_code == 422

    def test_entrada_produto_inativo_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, active=False)
        r = admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1_000},
        )
        assert r.status_code == 400

    def test_entrada_campo_extra_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1_000, "foo": "bar"},
        )
        assert r.status_code == 422


# ---------- Fluxo feliz perda ----------


class TestPerda:
    def test_perda_com_motivo_ok(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, stock_milli=10_000)
        r = admin_client.post(
            "/api/admin/stock/loss",
            json={"product_id": pid, "qty_milli": 2_000, "reason": "Vencimento"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "perda"
        assert data["qty_milli"] == -2_000
        assert data["reason"] == "Vencimento"

    def test_perda_sem_motivo_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = admin_client.post(
            "/api/admin/stock/loss",
            json={"product_id": pid, "qty_milli": 1_000},
        )
        # schema exige reason -> 422
        assert r.status_code == 422

    def test_perda_motivo_curto_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = admin_client.post(
            "/api/admin/stock/loss",
            json={"product_id": pid, "qty_milli": 1_000, "reason": "ab"},
        )
        assert r.status_code == 422


# ---------- Fluxo feliz ajuste ----------


class TestAjuste:
    def test_ajuste_positivo_ok(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, stock_milli=5_000)
        r = admin_client.post(
            "/api/admin/stock/adjustment",
            json={
                "product_id": pid,
                "new_stock_milli": 8_000,
                "reason": "Correcao",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["qty_milli"] == 3_000
        assert data["type"] == "ajuste"

    def test_ajuste_negativo_ok(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, stock_milli=5_000)
        r = admin_client.post(
            "/api/admin/stock/adjustment",
            json={
                "product_id": pid,
                "new_stock_milli": 3_000,
                "reason": "Divergencia",
            },
        )
        assert r.status_code == 200
        assert r.json()["qty_milli"] == -2_000

    def test_ajuste_mesmo_saldo_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, stock_milli=5_000)
        r = admin_client.post(
            "/api/admin/stock/adjustment",
            json={
                "product_id": pid,
                "new_stock_milli": 5_000,
                "reason": "Teste",
            },
        )
        assert r.status_code == 422

    def test_ajuste_produto_inativo_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, active=False, stock_milli=100)
        r = admin_client.post(
            "/api/admin/stock/adjustment",
            json={
                "product_id": pid,
                "new_stock_milli": 0,
                "reason": "Zerar descontinuado",
            },
        )
        assert r.status_code == 400

    def test_ajuste_sem_motivo_rejeita(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        r = admin_client.post(
            "/api/admin/stock/adjustment",
            json={"product_id": pid, "new_stock_milli": 5_000},
        )
        assert r.status_code == 422


# ---------- Historico ----------


class TestHistorico:
    def test_historico_filtra_por_tipo(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1_000},
        )
        admin_client.post(
            "/api/admin/stock/loss",
            json={"product_id": pid, "qty_milli": 500, "reason": "Perda teste"},
        )
        r = admin_client.get("/api/admin/stock/movements?type=entrada")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["type"] == "entrada"

    def test_historico_filtra_por_produto(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid1 = _criar_produto(SessionTesting, name="A")
        pid2 = _criar_produto(SessionTesting, name="B")
        admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid1, "qty_milli": 1_000},
        )
        admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid2, "qty_milli": 2_000},
        )
        r = admin_client.get(f"/api/admin/stock/movements?product_id={pid2}")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["product_id"] == pid2

    def test_historico_tipo_invalido_422(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/admin/stock/movements?type=xyz")
        assert r.status_code == 422


# ---------- Low stock ----------


class TestLowStock:
    def test_sem_minimo_configurado_vazio(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _criar_produto(SessionTesting, stock_milli=0, min_stock_milli=0)
        r = admin_client.get("/api/admin/stock/low")
        assert r.status_code == 200
        assert r.json() == []

    def test_abaixo_do_minimo_aparece(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _criar_produto(
            SessionTesting,
            name="Leite",
            stock_milli=500,
            min_stock_milli=2_000,
        )
        r = admin_client.get("/api/admin/stock/low")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["product_name"] == "Leite"
        assert rows[0]["stock_milli"] == 500
        assert rows[0]["min_stock_milli"] == 2_000

    def test_inativo_ignorado(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _criar_produto(
            SessionTesting,
            active=False,
            stock_milli=0,
            min_stock_milli=5_000,
        )
        r = admin_client.get("/api/admin/stock/low")
        assert r.json() == []


# ---------- Audit log ----------


class TestAuditLog:
    def test_entrada_grava_audit(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        admin_client.post(
            "/api/admin/stock/entry",
            json={"product_id": pid, "qty_milli": 1_000},
        )
        s = SessionTesting()
        try:
            from app.models import AuditLog

            audits = s.query(AuditLog).filter_by(action="stock_entry").all()
            assert len(audits) == 1
        finally:
            s.close()

    def test_perda_grava_audit(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting)
        admin_client.post(
            "/api/admin/stock/loss",
            json={"product_id": pid, "qty_milli": 500, "reason": "Perda teste"},
        )
        s = SessionTesting()
        try:
            from app.models import AuditLog

            audits = s.query(AuditLog).filter_by(action="stock_loss").all()
            assert len(audits) == 1
        finally:
            s.close()

    def test_ajuste_grava_audit(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        pid = _criar_produto(SessionTesting, stock_milli=1_000)
        admin_client.post(
            "/api/admin/stock/adjustment",
            json={
                "product_id": pid,
                "new_stock_milli": 2_000,
                "reason": "Ajuste teste",
            },
        )
        s = SessionTesting()
        try:
            from app.models import AuditLog

            audits = s.query(AuditLog).filter_by(action="stock_adjustment").all()
            assert len(audits) == 1
        finally:
            s.close()
