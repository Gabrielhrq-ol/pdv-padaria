"""
Testes do endpoint GET /api/products/favorites (Fase 14).
Admin e caixa podem consultar. Lista so ativos+favoritos ordenados por nome.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Product


def _criar(SessionTesting, **kwargs) -> int:
    s = SessionTesting()
    try:
        defaults = {
            "name": "Pao",
            "internal_code": "100",
            "unit": "UN",
            "price_cents": 100,
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


class TestFavoritesEndpoint:
    def test_anonimo_401(self, client: TestClient) -> None:
        assert client.get("/api/products/favorites").status_code == 401

    def test_caixa_pode_ler(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/api/products/favorites")
        assert r.status_code == 200
        assert r.json() == []

    def test_admin_pode_ler(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/products/favorites")
        assert r.status_code == 200

    def test_lista_apenas_favoritos_ativos(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _criar(SessionTesting, name="A Pao", internal_code="a1", favorite=True)
        _criar(SessionTesting, name="B Nao fav", internal_code="b1", favorite=False)
        _criar(SessionTesting, name="C Inativo", internal_code="c1",
               favorite=True, active=False)
        r = admin_client.get("/api/products/favorites")
        data = r.json()
        names = [p["name"] for p in data]
        assert names == ["A Pao"]  # so o ativo+favorito

    def test_ordenado_por_nome(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _criar(SessionTesting, name="Zebra", internal_code="z1", favorite=True)
        _criar(SessionTesting, name="Alice", internal_code="a1", favorite=True)
        _criar(SessionTesting, name="Marcos", internal_code="m1", favorite=True)
        r = admin_client.get("/api/products/favorites")
        names = [p["name"] for p in r.json()]
        assert names == ["Alice", "Marcos", "Zebra"]

    def test_respeita_limit(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        for i in range(15):
            _criar(SessionTesting, name=f"P{i:02d}", internal_code=f"c{i}",
                   favorite=True)
        r = admin_client.get("/api/products/favorites?limit=5")
        assert len(r.json()) == 5

    def test_limit_invalido_422(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/products/favorites?limit=0")
        assert r.status_code == 422

    def test_default_limit_12(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        for i in range(20):
            _criar(SessionTesting, name=f"P{i:02d}", internal_code=f"c{i}",
                   favorite=True)
        r = admin_client.get("/api/products/favorites")
        assert len(r.json()) == 12
