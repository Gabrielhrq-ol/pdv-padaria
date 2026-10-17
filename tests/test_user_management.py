"""
Testes de gestao de usuarios (Fase 13).

Cobre: service puro + rotas HTTP + regra "admin nao se desativa".
Admin/caixa das fixtures do conftest vem de outra Session, por isso
usamos _rebind() antes de passar como actor.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models import AuditLog, User
from app.security import verify_password
from app.services.user_service import (
    UserError,
    change_password,
    create_user,
    list_users,
    toggle_active,
    update_user,
)


def _rebind(session, user: User) -> User:
    """Re-busca user pela id na session do teste (fixture vem de outra)."""
    rebound = session.get(User, user.id)
    if rebound is None:
        raise RuntimeError(f"user {user.id} nao esta no DB da session")
    return rebound


# ---------- service puro ----------


class TestServiceCreate:
    def test_cria_caixa_simples(self, session, admin_user) -> None:
        u = create_user(
            session, actor=_rebind(session, admin_user),
            name="Jose Silva", username="jose.silva",
            password="SenhaForte1", role="caixa",
        )
        assert u.id is not None
        assert u.name == "Jose Silva"
        assert u.role == "caixa"
        assert u.active is True
        assert u.password_hash != "SenhaForte1"
        assert verify_password("SenhaForte1", u.password_hash)

    def test_cria_admin(self, session, admin_user) -> None:
        u = create_user(
            session, actor=_rebind(session, admin_user),
            name="Novo Dono", username="dono2",
            password="SenhaForte1", role="admin",
        )
        assert u.role == "admin"

    def test_username_duplicado_falha(self, session, admin_user) -> None:
        actor = _rebind(session, admin_user)
        create_user(session, actor=actor, name="XX", username="repetido",
                    password="SenhaForte1", role="caixa")
        with pytest.raises(UserError) as exc:
            create_user(session, actor=actor, name="YY", username="repetido",
                        password="SenhaForte1", role="caixa")
        assert exc.value.status_code == 409

    def test_senha_fraca_falha(self, session, admin_user) -> None:
        with pytest.raises(UserError) as exc:
            create_user(session, actor=_rebind(session, admin_user),
                        name="XX", username="x1",
                        password="curta", role="caixa")
        assert exc.value.status_code == 422

    def test_role_invalido_falha(self, session, admin_user) -> None:
        with pytest.raises(UserError):
            create_user(session, actor=_rebind(session, admin_user),
                        name="XX", username="x1",
                        password="SenhaForte1", role="superuser")

    def test_username_com_espaco_falha(self, session, admin_user) -> None:
        with pytest.raises(UserError):
            create_user(session, actor=_rebind(session, admin_user),
                        name="XX", username="x com espaco",
                        password="SenhaForte1", role="caixa")

    def test_audit_log_registrado(self, session, admin_user) -> None:
        create_user(session, actor=_rebind(session, admin_user),
                    name="XX", username="x1x",
                    password="SenhaForte1", role="caixa")
        audits = session.query(AuditLog).filter_by(action="user_created").all()
        assert len(audits) == 1
        # nunca grava a senha
        assert "SenhaForte1" not in (audits[0].details or "")


class TestServiceUpdate:
    def test_atualiza_nome(self, session, admin_user, caixa_user) -> None:
        u = update_user(session, actor=_rebind(session, admin_user),
                        target_id=caixa_user.id, name="Nome Novo")
        assert u.name == "Nome Novo"

    def test_atualiza_role(self, session, admin_user, caixa_user) -> None:
        u = update_user(session, actor=_rebind(session, admin_user),
                        target_id=caixa_user.id, role="admin")
        assert u.role == "admin"

    def test_admin_nao_troca_proprio_role(self, session, admin_user) -> None:
        actor = _rebind(session, admin_user)
        with pytest.raises(UserError) as exc:
            update_user(session, actor=actor, target_id=actor.id, role="caixa")
        assert exc.value.status_code == 400

    def test_sem_changes_noop(self, session, admin_user, caixa_user) -> None:
        update_user(session, actor=_rebind(session, admin_user),
                    target_id=caixa_user.id,
                    name=caixa_user.name, role=caixa_user.role)
        audits = session.query(AuditLog).filter_by(action="user_updated").all()
        assert len(audits) == 0

    def test_user_inexistente(self, session, admin_user) -> None:
        with pytest.raises(UserError) as exc:
            update_user(session, actor=_rebind(session, admin_user),
                        target_id=99999, name="X")
        assert exc.value.status_code == 404


class TestServiceChangePassword:
    def test_troca_senha_funciona(self, session, admin_user, caixa_user) -> None:
        change_password(session, actor=_rebind(session, admin_user),
                        target_id=caixa_user.id, new_password="NovaSenha1")
        reloaded = session.get(User, caixa_user.id)
        assert verify_password("NovaSenha1", reloaded.password_hash)

    def test_senha_fraca_falha(self, session, admin_user, caixa_user) -> None:
        with pytest.raises(UserError):
            change_password(session, actor=_rebind(session, admin_user),
                            target_id=caixa_user.id, new_password="short")

    def test_reseta_lockout(self, session, admin_user, caixa_user) -> None:
        from datetime import datetime, timedelta, timezone
        actor = _rebind(session, admin_user)
        target = _rebind(session, caixa_user)
        target.failed_login_count = 5
        target.locked_until = (datetime.now(timezone.utc).replace(tzinfo=None)
                                + timedelta(minutes=15))
        session.commit()
        change_password(session, actor=actor, target_id=target.id,
                        new_password="NovaSenha1")
        reloaded = session.get(User, target.id)
        assert reloaded.failed_login_count == 0
        assert reloaded.locked_until is None

    def test_audit_sem_senha(self, session, admin_user, caixa_user) -> None:
        change_password(session, actor=_rebind(session, admin_user),
                        target_id=caixa_user.id, new_password="NovaSenha1")
        audits = session.query(AuditLog).filter_by(
            action="user_password_changed"
        ).all()
        assert len(audits) == 1
        assert "NovaSenha1" not in (audits[0].details or "")


class TestServiceToggleActive:
    def test_desativa_caixa(self, session, admin_user, caixa_user) -> None:
        toggle_active(session, actor=_rebind(session, admin_user),
                      target_id=caixa_user.id, active=False)
        reloaded = session.get(User, caixa_user.id)
        assert reloaded.active is False

    def test_reativa(self, session, admin_user, caixa_user) -> None:
        actor = _rebind(session, admin_user)
        target = _rebind(session, caixa_user)
        target.active = False
        session.commit()
        toggle_active(session, actor=actor, target_id=target.id, active=True)
        reloaded = session.get(User, target.id)
        assert reloaded.active is True

    def test_admin_nao_se_desativa(self, session, admin_user) -> None:
        actor = _rebind(session, admin_user)
        with pytest.raises(UserError) as exc:
            toggle_active(session, actor=actor, target_id=actor.id, active=False)
        assert exc.value.status_code == 400
        assert "trancar" in exc.value.message.lower()

    def test_admin_pode_se_ativar(self, session, admin_user) -> None:
        actor = _rebind(session, admin_user)
        # noop ja que esta ativo, nao deve falhar
        toggle_active(session, actor=actor, target_id=actor.id, active=True)

    def test_idempotente(self, session, admin_user, caixa_user) -> None:
        toggle_active(session, actor=_rebind(session, admin_user),
                      target_id=caixa_user.id, active=True)
        audits = session.query(AuditLog).filter(
            AuditLog.action.in_(["user_activated", "user_deactivated"])
        ).all()
        # ja estava ativo, nao gerou audit
        assert len(audits) == 0


class TestServiceList:
    def test_lista_vazia(self, session) -> None:
        assert list_users(session) == []

    def test_lista_ordena_ativos_primeiro(self, session, admin_user) -> None:
        actor = _rebind(session, admin_user)
        create_user(session, actor=actor, name="Z Zebra", username="zze",
                    password="SenhaForte1", role="caixa")
        u2 = create_user(session, actor=actor, name="A Alice", username="ale",
                         password="SenhaForte1", role="caixa")
        # desativa a Alice
        toggle_active(session, actor=actor, target_id=u2.id, active=False)
        users = list_users(session)
        # admin + z + alice (inativa no fim)
        assert users[-1].name == "A Alice"


# ---------- rotas HTTP ----------


class TestRouterAutorizacao:
    def test_anonimo_401(self, client: TestClient) -> None:
        assert client.get("/api/admin/users").status_code == 401

    def test_caixa_403_list(self, caixa_client: TestClient) -> None:
        assert caixa_client.get("/api/admin/users").status_code == 403

    def test_caixa_403_create(self, caixa_client: TestClient) -> None:
        r = caixa_client.post("/api/admin/users", json={
            "name": "XX", "username": "x1",
            "password": "SenhaForte1", "role": "caixa",
        })
        assert r.status_code == 403

    def test_pagina_admin_usuarios_caixa_redireciona(
        self, caixa_client: TestClient
    ) -> None:
        r = caixa_client.get("/admin/usuarios", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/pdv"

    def test_pagina_admin_usuarios_admin_abre(
        self, admin_client: TestClient
    ) -> None:
        r = admin_client.get("/admin/usuarios")
        assert r.status_code == 200
        assert "Gestao de usuarios" in r.text


class TestRouterCreate:
    def test_cria_usuario(self, admin_client: TestClient) -> None:
        r = admin_client.post("/api/admin/users", json={
            "name": "Operador Novo",
            "username": "op1",
            "password": "SenhaForte1",
            "role": "caixa",
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["username"] == "op1"
        assert data["active"] is True
        assert "password" not in data
        assert "password_hash" not in data

    def test_sem_csrf_falha(self, admin_client: TestClient) -> None:
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.post("/api/admin/users", json={
            "name": "XX", "username": "x1",
            "password": "SenhaForte1", "role": "caixa",
        })
        assert r.status_code == 403

    def test_payload_invalido_422(self, admin_client: TestClient) -> None:
        r = admin_client.post("/api/admin/users", json={"name": "XX"})
        assert r.status_code == 422

    def test_extra_field_rejeitado(self, admin_client: TestClient) -> None:
        r = admin_client.post("/api/admin/users", json={
            "name": "XX", "username": "x1", "password": "SenhaForte1",
            "role": "caixa", "is_super": True,
        })
        assert r.status_code == 422


class TestRouterToggle:
    def test_admin_nao_se_desativa_via_http(
        self, admin_client: TestClient, admin_user
    ) -> None:
        r = admin_client.post(
            f"/api/admin/users/{admin_user.id}/toggle-active",
            json={"active": False},
        )
        assert r.status_code == 400
        assert "trancar" in r.json()["detail"].lower()

    def test_desativa_caixa_via_http(
        self, admin_client: TestClient, caixa_user
    ) -> None:
        r = admin_client.post(
            f"/api/admin/users/{caixa_user.id}/toggle-active",
            json={"active": False},
        )
        assert r.status_code == 200
        assert r.json()["active"] is False


class TestRouterChangePassword:
    def test_troca_senha_via_http(
        self, admin_client: TestClient, caixa_user
    ) -> None:
        r = admin_client.post(
            f"/api/admin/users/{caixa_user.id}/change-password",
            json={"new_password": "NovaSenha1"},
        )
        assert r.status_code == 200

    def test_senha_fraca_via_http_422(
        self, admin_client: TestClient, caixa_user
    ) -> None:
        r = admin_client.post(
            f"/api/admin/users/{caixa_user.id}/change-password",
            json={"new_password": "fraca"},
        )
        assert r.status_code == 422
