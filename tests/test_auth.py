"""Testes de autenticacao, lockout e CSRF."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditLog, User
from app.security import utc_now


class TestLogin:
    def test_login_ok(self, client: TestClient, admin_user: User) -> None:
        resp = client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"
        assert "csrf_token" in data and len(data["csrf_token"]) > 20
        # Cookies vieram
        assert client.cookies.get("session"), "session cookie faltando"
        assert client.cookies.get("csrf_token"), "csrf_token cookie faltando"

    def test_login_case_insensitive_username(
        self, client: TestClient, admin_user: User
    ) -> None:
        resp = client.post(
            "/auth/login",
            json={"username": "ADMIN", "password": "AdminSenha123"},
        )
        assert resp.status_code == 200

    def test_senha_errada_retorna_401(
        self, client: TestClient, admin_user: User
    ) -> None:
        resp = client.post(
            "/auth/login",
            json={"username": "admin", "password": "errada"},
        )
        assert resp.status_code == 401
        assert "credenciais" in resp.json()["detail"].lower()

    def test_usuario_inexistente_retorna_401(self, client: TestClient) -> None:
        resp = client.post(
            "/auth/login",
            json={"username": "fantasma", "password": "AdminSenha123"},
        )
        assert resp.status_code == 401

    def test_rejeita_campo_extra(self, client: TestClient, admin_user: User) -> None:
        resp = client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "AdminSenha123",
                "extra": True,
            },
        )
        assert resp.status_code == 422

    def test_usuario_inativo_401(
        self, client: TestClient, SessionTesting, admin_user: User
    ) -> None:
        s = SessionTesting()
        try:
            u = s.get(User, admin_user.id)
            u.active = False
            s.commit()
        finally:
            s.close()
        resp = client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        assert resp.status_code == 401


class TestLockout:
    def test_cinco_falhas_bloqueia(
        self, client: TestClient, SessionTesting, admin_user: User
    ) -> None:
        for _ in range(5):
            r = client.post(
                "/auth/login",
                json={"username": "admin", "password": "x"},
            )
            assert r.status_code == 401
        s = SessionTesting()
        try:
            u = s.get(User, admin_user.id)
            assert u.failed_login_count == 5
            assert u.locked_until is not None
            assert u.locked_until > utc_now()
        finally:
            s.close()

    def test_login_apos_lockout_bloqueado(
        self, client: TestClient, SessionTesting, admin_user: User
    ) -> None:
        s = SessionTesting()
        try:
            u = s.get(User, admin_user.id)
            u.failed_login_count = 5
            u.locked_until = utc_now() + timedelta(minutes=15)
            s.commit()
        finally:
            s.close()
        resp = client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        assert resp.status_code == 403
        assert "bloquead" in resp.json()["detail"].lower()

    def test_sucesso_zera_contador(
        self, client: TestClient, SessionTesting, admin_user: User
    ) -> None:
        # 2 falhas
        for _ in range(2):
            client.post("/auth/login", json={"username": "admin", "password": "x"})
        # 1 sucesso
        r = client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        assert r.status_code == 200
        s = SessionTesting()
        try:
            u = s.get(User, admin_user.id)
            assert u.failed_login_count == 0
            assert u.last_login_at is not None
        finally:
            s.close()


class TestLogout:
    def test_logout_limpa_cookies(
        self, client: TestClient, admin_user: User
    ) -> None:
        login = client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        csrf = login.json()["csrf_token"]
        resp = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 204
        # Chamada subsequente ao /me deve ser 401
        me = client.get("/auth/me")
        assert me.status_code == 401

    def test_logout_sem_estar_logado_401(self, client: TestClient) -> None:
        resp = client.post("/auth/logout")
        assert resp.status_code == 401


class TestMe:
    def test_me_logado(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

    def test_me_sem_login_401(self, client: TestClient) -> None:
        assert client.get("/auth/me").status_code == 401

    def test_me_com_cookie_adulterado_401(
        self, client: TestClient, admin_user: User
    ) -> None:
        client.cookies.set("session", "lixo-nao-assinado")
        assert client.get("/auth/me").status_code == 401


class TestAuditLog:
    def test_login_ok_e_registrado(
        self, client: TestClient, SessionTesting, admin_user: User
    ) -> None:
        client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        s = SessionTesting()
        try:
            rows = s.execute(
                select(AuditLog).where(AuditLog.action == "login_ok")
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].user_id == admin_user.id
        finally:
            s.close()

    def test_login_fail_e_registrado(
        self, client: TestClient, SessionTesting, admin_user: User
    ) -> None:
        client.post("/auth/login", json={"username": "admin", "password": "x"})
        s = SessionTesting()
        try:
            rows = s.execute(
                select(AuditLog).where(AuditLog.action == "login_fail")
            ).scalars().all()
            assert len(rows) == 1
        finally:
            s.close()

    def test_login_fail_unknown_user_registrado(
        self, client: TestClient, SessionTesting
    ) -> None:
        client.post("/auth/login", json={"username": "fantasma", "password": "x"})
        s = SessionTesting()
        try:
            rows = s.execute(
                select(AuditLog).where(AuditLog.action == "login_fail_unknown_user")
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].user_id is None
        finally:
            s.close()


class TestCSRF:
    def test_post_sem_csrf_rejeitado(
        self, client: TestClient, admin_user: User
    ) -> None:
        # Login mas NAO envia header CSRF
        login = client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        assert login.status_code == 200
        resp = client.post(
            "/api/products",
            json={"name": "X", "unit": "UN", "price_cents": 100},
        )
        assert resp.status_code == 403
        assert "csrf" in resp.json()["detail"].lower()

    def test_post_com_csrf_errado_rejeitado(
        self, client: TestClient, admin_user: User
    ) -> None:
        client.post(
            "/auth/login",
            json={"username": "admin", "password": "AdminSenha123"},
        )
        resp = client.post(
            "/api/products",
            json={"name": "X", "unit": "UN", "price_cents": 100},
            headers={"X-CSRF-Token": "token-falso-que-nao-bate"},
        )
        assert resp.status_code == 403
