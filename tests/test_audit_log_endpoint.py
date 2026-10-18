"""Testes do endpoint GET /api/admin/audit-log (Fase 16). Admin only."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import AuditLog, User, utc_now


def _add_audit(SessionTesting, **kwargs):
    s = SessionTesting()
    try:
        defaults = {
            "user_id": None,
            "action": "test_event",
            "entity": None,
            "entity_id": None,
            "details": None,
            "ip": None,
        }
        defaults.update(kwargs)
        a = AuditLog(**defaults)
        s.add(a)
        s.commit()
        s.refresh(a)
        return a.id
    finally:
        s.close()


class TestAutorizacao:
    def test_anonimo_401(self, client: TestClient) -> None:
        assert client.get("/api/admin/audit-log").status_code == 401

    def test_caixa_403(self, caixa_client: TestClient) -> None:
        assert caixa_client.get("/api/admin/audit-log").status_code == 403

    def test_caixa_403_actions(self, caixa_client: TestClient) -> None:
        assert caixa_client.get("/api/admin/audit-log/actions").status_code == 403

    def test_admin_200(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/admin/audit-log")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestFiltros:
    def test_admin_client_registra_login(self, admin_client: TestClient) -> None:
        # Antes mesmo de adicionar audits custom, o fixture ja fez login
        # - o audit login_ok deve estar la.
        r = admin_client.get("/api/admin/audit-log")
        rows = r.json()
        assert len(rows) >= 1
        assert any(row["action"] == "login_ok" for row in rows)

    def test_filtra_por_action(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _add_audit(SessionTesting, action="login_ok")
        _add_audit(SessionTesting, action="login_fail")
        _add_audit(SessionTesting, action="login_ok")
        r = admin_client.get("/api/admin/audit-log?action=login_fail")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["action"] == "login_fail"

    def test_filtra_por_entity(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _add_audit(SessionTesting, action="x", entity="product", entity_id=1)
        _add_audit(SessionTesting, action="y", entity="user", entity_id=1)
        _add_audit(SessionTesting, action="z", entity="sale", entity_id=1)
        r = admin_client.get("/api/admin/audit-log?entity=user")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["entity"] == "user"

    def test_filtra_por_user(
        self, admin_client: TestClient, SessionTesting, admin_user, caixa_user
    ) -> None:
        _add_audit(SessionTesting, action="a1", user_id=admin_user.id)
        _add_audit(SessionTesting, action="a2", user_id=caixa_user.id)
        r = admin_client.get(f"/api/admin/audit-log?user_id={caixa_user.id}")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["user_id"] == caixa_user.id
        assert rows[0]["user_name"] == caixa_user.name

    def test_ordem_decrescente(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        import time
        _add_audit(SessionTesting, action="x_first")
        time.sleep(0.01)
        _add_audit(SessionTesting, action="x_second")
        time.sleep(0.01)
        _add_audit(SessionTesting, action="x_third")
        # pega tudo e filtra os nossos no cliente (ignora o login_ok do fixture)
        r = admin_client.get("/api/admin/audit-log?limit=500")
        all_actions = [row["action"] for row in r.json()]
        xs = [a for a in all_actions if a.startswith("x_")]
        assert xs == ["x_third", "x_second", "x_first"]

    def test_paginacao(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        for i in range(5):
            _add_audit(SessionTesting, action=f"evt{i}")
        r = admin_client.get("/api/admin/audit-log?limit=2&offset=0")
        page1 = r.json()
        r = admin_client.get("/api/admin/audit-log?limit=2&offset=2")
        page2 = r.json()
        assert len(page1) == 2 and len(page2) == 2
        ids1 = {row["id"] for row in page1}
        ids2 = {row["id"] for row in page2}
        assert ids1.isdisjoint(ids2)

    def test_limit_invalido_422(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/admin/audit-log?limit=9999")
        assert r.status_code == 422

    def test_user_desconhecido_user_name_none(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        # user_id=99999 nao existe
        _add_audit(SessionTesting, action="orphan", user_id=None)
        r = admin_client.get("/api/admin/audit-log?action=orphan")
        rows = r.json()
        assert rows[0]["user_name"] is None


class TestActions:
    def test_actions_tem_pelo_menos_login(self, admin_client: TestClient) -> None:
        # admin_client fixture ja fez login_ok
        r = admin_client.get("/api/admin/audit-log/actions")
        assert r.status_code == 200
        assert "login_ok" in r.json()

    def test_actions_distinct(
        self, admin_client: TestClient, SessionTesting
    ) -> None:
        _add_audit(SessionTesting, action="cash_opened")
        _add_audit(SessionTesting, action="cash_opened")
        _add_audit(SessionTesting, action="cash_closed")
        r = admin_client.get("/api/admin/audit-log/actions")
        actions = r.json()
        # distinct + ordenado alfabeticamente. login_ok veio do fixture.
        assert "cash_opened" in actions
        assert "cash_closed" in actions
        assert "login_ok" in actions
        # ordenado
        assert actions == sorted(actions)
        # distinct (cada acao aparece uma vez)
        assert len(actions) == len(set(actions))


class TestPagina:
    def test_admin_abre(self, admin_client: TestClient) -> None:
        r = admin_client.get("/admin/auditoria")
        assert r.status_code == 200
        assert "Auditoria do sistema" in r.text

    def test_caixa_redireciona(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/admin/auditoria", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/pdv"
