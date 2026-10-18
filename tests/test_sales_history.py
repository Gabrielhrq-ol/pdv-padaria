"""
Testes do endpoint GET /api/sales (Fase 15) e da pagina /admin/vendas.
Reprint e reverse ja tem cobertura em test_sales_finalize_api.py; aqui
focamos no NOVO endpoint de listagem com filtros + pagina HTML.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import Payment, Product, Sale, SaleItem, User, utc_now


def _criar_venda(SessionTesting, user_id, *, status="completed",
                 total=500, when=None, number=None):
    s = SessionTesting()
    try:
        n = number or (s.query(Sale).count() + 1)
        when = when or utc_now()
        sale = Sale(
            number=n,
            user_id=user_id,
            status=status,
            subtotal_cents=total,
            total_cents=total,
            finalized_at=when if status == "completed" else None,
            cancelled_at=when if status == "cancelled" else None,
            cancel_reason="teste" if status == "cancelled" else None,
            created_at=when,
        )
        s.add(sale)
        s.commit()
        s.refresh(sale)
        return sale.id
    finally:
        s.close()


class TestAutorizacao:
    def test_anonimo_401(self, client: TestClient) -> None:
        assert client.get("/api/sales").status_code == 401

    def test_caixa_403(self, caixa_client: TestClient) -> None:
        # listagem agregada e admin only
        assert caixa_client.get("/api/sales").status_code == 403

    def test_admin_200(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/sales")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestFiltros:
    def test_vazio_sem_vendas(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/sales")
        assert r.json() == []

    def test_filtro_por_numero(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _criar_venda(SessionTesting, admin_user.id, number=10)
        _criar_venda(SessionTesting, admin_user.id, number=11)
        _criar_venda(SessionTesting, admin_user.id, number=12)
        r = admin_client.get("/api/sales?number=11")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["number"] == 11

    def test_filtro_por_status(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _criar_venda(SessionTesting, admin_user.id, status="completed", number=20)
        _criar_venda(SessionTesting, admin_user.id, status="cancelled", number=21)
        r = admin_client.get("/api/sales?status=cancelled")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["status"] == "cancelled"

    def test_filtro_por_user(
        self, admin_client: TestClient, SessionTesting, admin_user, caixa_user
    ) -> None:
        _criar_venda(SessionTesting, admin_user.id, number=30)
        _criar_venda(SessionTesting, caixa_user.id, number=31)
        r = admin_client.get(f"/api/sales?user_id={caixa_user.id}")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["user_id"] == caixa_user.id

    def test_filtro_data(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        ontem = utc_now() - timedelta(days=1)
        hoje = utc_now()
        _criar_venda(SessionTesting, admin_user.id, number=40, when=ontem)
        _criar_venda(SessionTesting, admin_user.id, number=41, when=hoje)
        inicio_hoje = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        r = admin_client.get(f"/api/sales?date_from={inicio_hoje.isoformat()}")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["number"] == 41

    def test_ordem_decrescente_por_numero(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        _criar_venda(SessionTesting, admin_user.id, number=100)
        _criar_venda(SessionTesting, admin_user.id, number=200)
        _criar_venda(SessionTesting, admin_user.id, number=150)
        r = admin_client.get("/api/sales")
        numbers = [row["number"] for row in r.json()]
        assert numbers == [200, 150, 100]

    def test_paginacao(
        self, admin_client: TestClient, SessionTesting, admin_user
    ) -> None:
        for i in range(5):
            _criar_venda(SessionTesting, admin_user.id, number=1000 + i)
        r = admin_client.get("/api/sales?limit=2&offset=0")
        page1 = r.json()
        r = admin_client.get("/api/sales?limit=2&offset=2")
        page2 = r.json()
        assert len(page1) == 2 and len(page2) == 2
        # sem sobreposicao
        n1 = {s["number"] for s in page1}
        n2 = {s["number"] for s in page2}
        assert n1.isdisjoint(n2)

    def test_limit_acima_do_max_422(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/sales?limit=9999")
        assert r.status_code == 422

    def test_status_invalido_422(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/sales?status=xyz")
        assert r.status_code == 422


class TestPagina:
    def test_admin_abre(self, admin_client: TestClient) -> None:
        r = admin_client.get("/admin/vendas")
        assert r.status_code == 200
        assert "Historico de vendas" in r.text

    def test_caixa_redireciona(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/admin/vendas", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/pdv"

    def test_anonimo_redireciona_login(self, client: TestClient) -> None:
        r = client.get("/admin/vendas", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]
