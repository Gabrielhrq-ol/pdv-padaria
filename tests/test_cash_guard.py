"""
Testes do guard de caixa:
- Setting cash_session_required=true bloqueia venda sem caixa aberto
  (via sales_service.create_open_sale).
- /pdv redireciona para /caixa quando setting on e sem sessao.
- Setting off: venda funciona normalmente (comportamento pre-Fase 7).
- Carimba cash_session_id na venda quando ha sessao aberta.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models import Setting, User
from app.security import hash_password
from app.services import cash_service
from app.services.sales_service import SalesError, create_open_sale


def _habilitar_cash(session) -> None:
    session.add(Setting(key="cash_session_required", value="true"))
    session.commit()


@pytest.fixture
def user_db(session) -> User:
    u = User(
        name="C",
        username="caixaguard",
        password_hash=hash_password("Senha1234"),
        role="caixa",
        active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


# ---------- service level ----------


class TestServiceGuard:
    def test_sem_setting_venda_livre(self, session, user_db):
        """Comportamento legado: sem setting, venda sem caixa funciona."""
        sale = create_open_sale(session, user_db)
        assert sale.status == "open"
        assert sale.cash_session_id is None

    def test_setting_on_sem_caixa_bloqueia(self, session, user_db):
        _habilitar_cash(session)
        with pytest.raises(SalesError) as exc:
            create_open_sale(session, user_db)
        assert exc.value.status_code == 409
        assert "caixa" in exc.value.message.lower()

    def test_setting_on_com_caixa_carimba_id(self, session, user_db):
        _habilitar_cash(session)
        s = cash_service.open_session(
            session, user=user_db, opening_cash_cents=1000
        )
        sale = create_open_sale(session, user_db)
        assert sale.cash_session_id == s.id

    def test_setting_off_mas_caixa_aberto_ainda_carimba(self, session, user_db):
        """Se tem caixa aberto, mesmo com setting off, carimba na venda."""
        s = cash_service.open_session(
            session, user=user_db, opening_cash_cents=1000
        )
        sale = create_open_sale(session, user_db)
        assert sale.cash_session_id == s.id


# ---------- HTTP level: /pdv guard ----------


def _habilitar_cash_via_client(admin_client: TestClient) -> None:
    r = admin_client.put(
        "/api/admin/settings/cash-required", json={"enabled": True}
    )
    assert r.status_code == 200, r.text


def _abrir_operador(client: TestClient) -> None:
    uid = client.get("/auth/me").json()["id"]
    r = client.post("/api/pdv/select-operator", json={"operator_id": uid})
    assert r.status_code == 200, r.text


class TestPdvGuard:
    def test_pdv_sem_setting_funciona(self, admin_client: TestClient) -> None:
        _abrir_operador(admin_client)
        r = admin_client.get("/pdv")
        assert r.status_code == 200

    def test_pdv_com_setting_sem_caixa_redireciona(
        self, admin_client: TestClient
    ) -> None:
        _abrir_operador(admin_client)
        _habilitar_cash_via_client(admin_client)
        r = admin_client.get("/pdv", follow_redirects=False)
        assert r.status_code == 302
        assert "/caixa" in r.headers["location"]

    def test_pdv_com_setting_e_caixa_aberto_funciona(
        self, admin_client: TestClient
    ) -> None:
        _abrir_operador(admin_client)
        _habilitar_cash_via_client(admin_client)
        r = admin_client.post(
            "/api/cash/open", json={"opening_cash_cents": 10000}
        )
        assert r.status_code == 200, r.text
        r = admin_client.get("/pdv")
        assert r.status_code == 200

    def test_pdv_apos_fechar_caixa_volta_a_redirecionar(
        self, admin_client: TestClient
    ) -> None:
        _abrir_operador(admin_client)
        _habilitar_cash_via_client(admin_client)
        admin_client.post("/api/cash/open", json={"opening_cash_cents": 100})
        admin_client.post(
            "/api/cash/close", json={"declared_cash_cents": 100}
        )
        r = admin_client.get("/pdv", follow_redirects=False)
        assert r.status_code == 302
