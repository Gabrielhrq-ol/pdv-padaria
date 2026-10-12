"""Testes do CRUD de produtos."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _novo_produto(**overrides) -> dict:
    base = {
        "name": "Pao frances",
        "unit": "KG",
        "price_cents": 1800,
        "stock_milli": 5000,
        "min_stock_milli": 1000,
        "favorite": True,
    }
    base.update(overrides)
    return base


class TestListarProdutos:
    def test_lista_vazia(self, client: TestClient) -> None:
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCriarProduto:
    def test_cria_e_retorna_201(self, client: TestClient) -> None:
        resp = client.post("/api/products", json=_novo_produto())
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["id"] >= 1
        assert data["name"] == "Pao frances"
        assert data["unit"] == "KG"
        assert data["active"] is True

    def test_barcode_duplicado_409(self, client: TestClient) -> None:
        p = _novo_produto(name="Refri", unit="UN", barcode="7891111111111")
        r1 = client.post("/api/products", json=p)
        assert r1.status_code == 201
        r2 = client.post(
            "/api/products",
            json=_novo_produto(name="Outro", unit="UN", barcode="7891111111111"),
        )
        assert r2.status_code == 409
        assert "codigo de barras" in r2.json()["detail"].lower()

    def test_internal_code_duplicado_409(self, client: TestClient) -> None:
        client.post(
            "/api/products",
            json=_novo_produto(name="Pao A", internal_code="101"),
        )
        resp = client.post(
            "/api/products",
            json=_novo_produto(name="Pao B", internal_code="101"),
        )
        assert resp.status_code == 409

    def test_rejeita_campo_extra(self, client: TestClient) -> None:
        resp = client.post(
            "/api/products",
            json=_novo_produto(delete_me=True),
        )
        assert resp.status_code == 422

    def test_rejeita_preco_negativo(self, client: TestClient) -> None:
        resp = client.post("/api/products", json=_novo_produto(price_cents=-1))
        assert resp.status_code == 422

    def test_rejeita_estoque_negativo(self, client: TestClient) -> None:
        resp = client.post("/api/products", json=_novo_produto(stock_milli=-100))
        assert resp.status_code == 422

    def test_rejeita_unidade_invalida(self, client: TestClient) -> None:
        resp = client.post("/api/products", json=_novo_produto(unit="ML"))
        assert resp.status_code == 422

    def test_rejeita_barcode_nao_numerico(self, client: TestClient) -> None:
        resp = client.post(
            "/api/products",
            json=_novo_produto(barcode="ABC1234"),
        )
        assert resp.status_code == 422

    def test_rejeita_internal_code_com_espaco(self, client: TestClient) -> None:
        resp = client.post(
            "/api/products",
            json=_novo_produto(internal_code="pao frances"),
        )
        assert resp.status_code == 422

    def test_rejeita_preco_acima_do_teto(self, client: TestClient) -> None:
        resp = client.post(
            "/api/products",
            json=_novo_produto(price_cents=100_000_001),
        )
        assert resp.status_code == 422

    def test_rejeita_nome_vazio(self, client: TestClient) -> None:
        resp = client.post("/api/products", json=_novo_produto(name=""))
        assert resp.status_code == 422


class TestEditarProduto:
    def test_edita_preco(self, client: TestClient) -> None:
        r = client.post("/api/products", json=_novo_produto())
        pid = r.json()["id"]
        resp = client.put(f"/api/products/{pid}", json={"price_cents": 2000})
        assert resp.status_code == 200
        assert resp.json()["price_cents"] == 2000

    def test_edita_so_o_que_veio(self, client: TestClient) -> None:
        """exclude_unset: campos nao enviados nao mudam."""
        r = client.post(
            "/api/products",
            json=_novo_produto(name="Original", favorite=True),
        )
        pid = r.json()["id"]
        resp = client.put(f"/api/products/{pid}", json={"name": "Renomeado"})
        data = resp.json()
        assert data["name"] == "Renomeado"
        assert data["favorite"] is True

    def test_404_se_nao_existe(self, client: TestClient) -> None:
        resp = client.put("/api/products/99999", json={"name": "X"})
        assert resp.status_code == 404

    def test_rejeita_campo_extra_no_update(self, client: TestClient) -> None:
        r = client.post("/api/products", json=_novo_produto())
        pid = r.json()["id"]
        resp = client.put(f"/api/products/{pid}", json={"foo": "bar"})
        assert resp.status_code == 422


class TestDesativarProduto:
    def test_desativa_mas_nao_apaga(self, client: TestClient) -> None:
        r = client.post("/api/products", json=_novo_produto())
        pid = r.json()["id"]
        resp = client.patch(f"/api/products/{pid}/active", json={"active": False})
        assert resp.status_code == 200
        assert resp.json()["active"] is False
        # Ainda existe
        get = client.get(f"/api/products/{pid}")
        assert get.status_code == 200
        assert get.json()["active"] is False

    def test_lista_padrao_nao_mostra_inativos(self, client: TestClient) -> None:
        r = client.post("/api/products", json=_novo_produto())
        pid = r.json()["id"]
        client.patch(f"/api/products/{pid}/active", json={"active": False})
        lst = client.get("/api/products").json()
        assert all(p["id"] != pid for p in lst)

    def test_include_inactive_mostra(self, client: TestClient) -> None:
        r = client.post("/api/products", json=_novo_produto())
        pid = r.json()["id"]
        client.patch(f"/api/products/{pid}/active", json={"active": False})
        lst = client.get("/api/products?include_inactive=true").json()
        assert any(p["id"] == pid for p in lst)

    def test_reativa(self, client: TestClient) -> None:
        r = client.post("/api/products", json=_novo_produto())
        pid = r.json()["id"]
        client.patch(f"/api/products/{pid}/active", json={"active": False})
        resp = client.patch(f"/api/products/{pid}/active", json={"active": True})
        assert resp.json()["active"] is True


class TestBuscar:
    def _popula(self, client: TestClient) -> None:
        client.post(
            "/api/products",
            json=_novo_produto(
                name="Pao frances", internal_code="101", unit="KG",
            ),
        )
        client.post(
            "/api/products",
            json=_novo_produto(
                name="Refrigerante 2L",
                barcode="7891000000001",
                unit="UN",
            ),
        )
        client.post(
            "/api/products",
            json=_novo_produto(
                name="Cafe expresso",
                internal_code="202",
                unit="UN",
            ),
        )

    def test_busca_por_nome(self, client: TestClient) -> None:
        self._popula(client)
        resp = client.get("/api/products/search?q=pao")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "Pao frances" in names
        assert "Refrigerante 2L" not in names

    def test_busca_por_barcode(self, client: TestClient) -> None:
        self._popula(client)
        resp = client.get("/api/products/search?q=7891000000001")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Refrigerante 2L"

    def test_busca_por_internal_code(self, client: TestClient) -> None:
        self._popula(client)
        resp = client.get("/api/products/search?q=202")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Cafe expresso"

    def test_busca_vazia_retorna_422(self, client: TestClient) -> None:
        resp = client.get("/api/products/search?q=")
        assert resp.status_code == 422

    def test_busca_sem_resultado(self, client: TestClient) -> None:
        self._popula(client)
        resp = client.get("/api/products/search?q=xyz_nao_existe")
        assert resp.json() == []


class TestSegurancaHeaders:
    """Confirma que os headers de seguranca sao injetados."""

    def test_csp_presente(self, client: TestClient) -> None:
        resp = client.get("/health")
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "'unsafe-inline'" not in csp
        assert "'unsafe-eval'" not in csp

    def test_x_frame_options(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_x_content_type_options(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_referrer_policy(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.headers.get("referrer-policy") == "no-referrer"

    def test_health_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestTrustedHost:
    def test_rejeita_host_externo(self, client: TestClient) -> None:
        resp = client.get("/health", headers={"host": "evil.com"})
        assert resp.status_code == 400
