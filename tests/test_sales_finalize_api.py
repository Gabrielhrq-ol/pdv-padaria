"""Testes de integracao dos endpoints POST /finalize, /reverse, /reprint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Payment, Product, Setting, StockMovement


@pytest.fixture
def payment_methods_setting(SessionTesting):
    s = SessionTesting()
    try:
        s.add(Setting(
            key="payment_methods",
            value='["dinheiro","debito","credito","pix","outros"]',
        ))
        s.commit()
    finally:
        s.close()


@pytest.fixture
def produto(admin_client: TestClient) -> dict:
    r = admin_client.post("/api/products", json={
        "name": "Refri 2L",
        "barcode": "7891111",
        "unit": "UN",
        "price_cents": 1200,
        "stock_milli": 24000,
        "min_stock_milli": 0,
        "favorite": False,
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def sale_com_item(caixa_client: TestClient, produto) -> int:
    sale = caixa_client.post("/api/sales").json()
    caixa_client.post(
        f"/api/sales/{sale['id']}/items",
        json={"code": "7891111"},
    )
    return sale["id"]


class TestFinalizeEndpoint:
    def test_finaliza_com_dinheiro_exato(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sale"]["status"] == "completed"
        assert data["printed"] is False

    def test_finaliza_com_troco(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 2000}],
                "print_receipt": False,
            },
        )
        data = r.json()
        assert data["sale"]["payments"][0]["change_cents"] == 800

    def test_finaliza_imprime_via_dummy(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": True,
            },
        )
        data = r.json()
        assert data["printed"] is True
        assert len(data["receipt_lines"]) > 0
        joined = "\n".join(data["receipt_lines"])
        assert "CUPOM NAO FISCAL - SEM VALOR FISCAL" in joined

    def test_cartao_excedendo_bloqueia(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "credito", "amount_cents": 1500}],
                "print_receipt": False,
            },
        )
        assert r.status_code == 400
        assert "excede" in r.json()["detail"].lower()

    def test_valor_insuficiente(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 100}],
                "print_receipt": False,
            },
        )
        assert r.status_code == 400

    def test_metodo_invalido(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "cheque", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        assert r.status_code == 400

    def test_dupla_finalizacao_rejeitada(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        assert r.status_code == 409

    def test_sem_csrf_bloqueado(
        self, client: TestClient, admin_user, produto, payment_methods_setting
    ) -> None:
        # login manual sem injetar header csrf
        client.post("/auth/login", json={
            "username": "admin",
            "password": "AdminSenha123",
        })
        # cria venda
        s = client.request(
            "POST",
            "/api/sales",
            headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
        ).json()
        # finaliza SEM header csrf
        r = client.post(
            f"/api/sales/{s['id']}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        assert r.status_code == 403


class TestReverseEndpoint:
    def test_reverte_e_estoca_volta(
        self,
        caixa_client: TestClient,
        sale_com_item,
        produto,
        payment_methods_setting,
        SessionTesting,
    ) -> None:
        caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/reverse",
            json={"reason": "cliente desistiu"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"
        # Estoque voltou
        s = SessionTesting()
        try:
            p = s.get(Product, produto["id"])
            assert p.stock_milli == 24000  # inicial
        finally:
            s.close()

    def test_motivo_obrigatorio_422(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/reverse",
            json={"reason": ""},
        )
        assert r.status_code == 422

    def test_so_reverte_completed(
        self, caixa_client: TestClient, produto, payment_methods_setting
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.post(
            f"/api/sales/{sale['id']}/reverse",
            json={"reason": "x"},
        )
        assert r.status_code == 409


class TestReprintEndpoint:
    def test_reprint_marca_2a_via(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        r = caixa_client.post(
            f"/api/sales/{sale_com_item}/reprint",
        )
        assert r.status_code == 200
        data = r.json()
        joined = "\n".join(data["receipt_lines"])
        assert "2a VIA" in joined
        assert data["printed"] is True

    def test_reprint_so_de_completed(
        self, caixa_client: TestClient, produto
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.post(f"/api/sales/{sale['id']}/reprint")
        assert r.status_code == 400

    def test_last_completed(
        self, caixa_client: TestClient, sale_com_item, payment_methods_setting
    ) -> None:
        caixa_client.post(
            f"/api/sales/{sale_com_item}/finalize",
            json={
                "payments": [{"method": "dinheiro", "amount_cents": 1200}],
                "print_receipt": False,
            },
        )
        r = caixa_client.get("/api/sales/last-completed")
        assert r.status_code == 200
        assert r.json()["id"] == sale_com_item

    def test_last_completed_vazio(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/api/sales/last-completed")
        assert r.status_code == 200
        assert r.json() is None
