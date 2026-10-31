"""PDV e caixa so funcionam com operador aberto (cookie operator_id)."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestOperadorObrigatorio:
    def test_pdv_sem_operador_pede_abrir(self, client: TestClient) -> None:
        r = client.get("/pdv", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/operador?next=/pdv"

    def test_admin_logado_tambem_precisa_abrir_operador(
        self, admin_client: TestClient
    ) -> None:
        r = admin_client.get("/pdv", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/operador?next=/pdv"

    def test_operador_inexistente_nao_passa(self, client: TestClient) -> None:
        client.cookies.set("operator_id", "99999")
        r = client.get("/pdv", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/operador?next=/pdv"

    def test_com_operador_abre_pdv(
        self, client: TestClient, caixa_user
    ) -> None:
        r = client.post(
            "/api/pdv/select-operator", json={"operator_id": caixa_user.id}
        )
        assert r.status_code == 200
        assert client.get("/pdv").status_code == 200
        assert client.get("/caixa").status_code == 200

    def test_tela_operador_abre_sem_login(self, client: TestClient) -> None:
        r = client.get("/operador?next=/caixa")
        assert r.status_code == 200
        assert 'data-next="/caixa"' in r.text

    def test_next_externo_e_ignorado(self, client: TestClient) -> None:
        r = client.get("/operador?next=https://exemplo.com")
        assert r.status_code == 200
        assert 'data-next="/pdv"' in r.text
        assert "exemplo.com" not in r.text
