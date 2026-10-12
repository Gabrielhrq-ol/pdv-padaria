"""Testes de integracao do router /api/sales."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def produto_cadastrado(admin_client: TestClient) -> dict:
    r = admin_client.post(
        "/api/products",
        json={
            "name": "Refrigerante 2L",
            "barcode": "7891111111117",
            "unit": "UN",
            "price_cents": 1200,
            "stock_milli": 24000,
            "min_stock_milli": 0,
            "favorite": False,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def produto_kg(admin_client: TestClient) -> dict:
    r = admin_client.post(
        "/api/products",
        json={
            "name": "Pao frances",
            "internal_code": "101",
            "unit": "KG",
            "price_cents": 1800,
            "stock_milli": 10000,
            "min_stock_milli": 1000,
            "favorite": True,
        },
    )
    assert r.status_code == 201
    return r.json()


class TestAbrirVenda:
    def test_caixa_abre_venda(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        r = caixa_client.post("/api/sales")
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "open"
        assert data["total_cents"] == 0

    def test_anonimo_401(self, client: TestClient) -> None:
        assert client.post("/api/sales").status_code == 401

    def test_idempotente_mesmo_operador(
        self, caixa_client: TestClient
    ) -> None:
        r1 = caixa_client.post("/api/sales")
        r2 = caixa_client.post("/api/sales")
        assert r1.json()["id"] == r2.json()["id"]

    def test_get_open_vazio(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/api/sales/open")
        assert r.status_code == 200
        assert r.json() is None

    def test_get_open_depois_de_abrir(self, caixa_client: TestClient) -> None:
        caixa_client.post("/api/sales")
        r = caixa_client.get("/api/sales/open")
        assert r.json() is not None
        assert r.json()["status"] == "open"


class TestAddItem:
    def test_adiciona_por_code(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.post(
            f"/api/sales/{sale['id']}/items",
            json={"code": "7891111111117"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["product_name"] == "Refrigerante 2L"
        assert data["items"][0]["qty_milli"] == 1000
        assert data["total_cents"] == 1200

    def test_atalho_N_vezes_cod(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.post(
            f"/api/sales/{sale['id']}/items",
            json={"code": "3*7891111111117"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["items"][0]["qty_milli"] == 3000
        assert data["total_cents"] == 3600

    def test_adiciona_por_product_id_e_qty(
        self, caixa_client: TestClient, produto_kg
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.post(
            f"/api/sales/{sale['id']}/items",
            json={"product_id": produto_kg["id"], "qty_milli": 350},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_cents"] == 630  # 0.350 * 18.00

    def test_bipa_duas_vezes_mesmo_produto_agrupa(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        caixa_client.post(
            f"/api/sales/{sale['id']}/items", json={"code": "7891111111117"}
        )
        r = caixa_client.post(
            f"/api/sales/{sale['id']}/items", json={"code": "7891111111117"}
        )
        data = r.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["qty_milli"] == 2000

    def test_produto_inexistente_404(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.post(
            f"/api/sales/{sale['id']}/items", json={"code": "999999999"}
        )
        assert r.status_code == 404

    def test_preco_congelado_quando_produto_muda(
        self, admin_client: TestClient, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        caixa_client.post(
            f"/api/sales/{sale['id']}/items",
            json={"code": "7891111111117"},
        )
        # admin muda o preco
        admin_client.put(
            f"/api/products/{produto_cadastrado['id']}",
            json={"price_cents": 2000},
        )
        # consulta a venda
        r = caixa_client.get(f"/api/sales/{sale['id']}")
        assert r.json()["items"][0]["unit_price_cents"] == 1200


class TestChangeAndRemove:
    def test_altera_qty(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        add = caixa_client.post(
            f"/api/sales/{sale['id']}/items", json={"code": "7891111111117"}
        )
        item_id = add.json()["items"][0]["id"]
        r = caixa_client.patch(
            f"/api/sales/{sale['id']}/items/{item_id}",
            json={"qty_milli": 5000},
        )
        assert r.status_code == 200
        assert r.json()["items"][0]["qty_milli"] == 5000
        assert r.json()["total_cents"] == 6000

    def test_remove_item(
        self, caixa_client: TestClient, produto_cadastrado, produto_kg
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        a = caixa_client.post(
            f"/api/sales/{sale['id']}/items", json={"code": "7891111111117"}
        ).json()
        caixa_client.post(
            f"/api/sales/{sale['id']}/items", json={"code": "101"}
        )
        item_id = a["items"][0]["id"]
        r = caixa_client.delete(f"/api/sales/{sale['id']}/items/{item_id}")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    def test_404_em_item_que_nao_existe(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.patch(
            f"/api/sales/{sale['id']}/items/99999", json={"qty_milli": 100}
        )
        assert r.status_code == 404


class TestCancel:
    def test_cancela(self, caixa_client: TestClient) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.request(
            "DELETE",
            f"/api/sales/{sale['id']}",
            json={"reason": "troco errado"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"
        assert r.json()["cancel_reason"] == "troco errado"

    def test_motivo_obrigatorio(self, caixa_client: TestClient) -> None:
        sale = caixa_client.post("/api/sales").json()
        r = caixa_client.request(
            "DELETE",
            f"/api/sales/{sale['id']}",
            json={"reason": ""},
        )
        assert r.status_code == 422

    def test_cancelada_nao_pode_cancelar_de_novo(
        self, caixa_client: TestClient
    ) -> None:
        sale = caixa_client.post("/api/sales").json()
        caixa_client.request(
            "DELETE",
            f"/api/sales/{sale['id']}",
            json={"reason": "primeira"},
        )
        r = caixa_client.request(
            "DELETE",
            f"/api/sales/{sale['id']}",
            json={"reason": "segunda"},
        )
        assert r.status_code == 409


class TestIsolamentoEntreOperadores:
    def test_caixa_nao_ve_venda_de_outro(
        self,
        admin_client: TestClient,
        caixa_client: TestClient,
        produto_cadastrado,
    ) -> None:
        # admin abre venda
        admin_sale = admin_client.post("/api/sales").json()
        # caixa tenta ver
        r = caixa_client.get(f"/api/sales/{admin_sale['id']}")
        assert r.status_code == 403

    def test_admin_ve_tudo(
        self, admin_client: TestClient, caixa_client: TestClient
    ) -> None:
        caixa_sale = caixa_client.post("/api/sales").json()
        r = admin_client.get(f"/api/sales/{caixa_sale['id']}")
        assert r.status_code == 200


class TestByCode:
    def test_resolve_barcode(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        r = caixa_client.get("/api/products/by-code/7891111111117")
        assert r.status_code == 200
        data = r.json()
        assert data["product"]["name"] == "Refrigerante 2L"
        assert data["qty_multiplier"] == 1

    def test_resolve_internal_code(
        self, caixa_client: TestClient, produto_kg
    ) -> None:
        r = caixa_client.get("/api/products/by-code/101")
        assert r.status_code == 200
        assert r.json()["product"]["unit"] == "KG"

    def test_resolve_multiplicador(
        self, caixa_client: TestClient, produto_cadastrado
    ) -> None:
        r = caixa_client.get("/api/products/by-code/5*7891111111117")
        assert r.status_code == 200
        assert r.json()["qty_multiplier"] == 5

    def test_produto_nao_encontrado(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/api/products/by-code/999999")
        assert r.status_code == 404
