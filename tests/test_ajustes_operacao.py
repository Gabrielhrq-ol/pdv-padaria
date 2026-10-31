"""Correcoes da primeira instalacao: operador x painel, dia local, backup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.security import SESSION_COOKIE
from app.services import backup_hook
from app.services.reports_service import _today_window


class TestOperadorDiferenteDoPainel:
    def test_encerra_painel_e_venda_sai_no_operador(
        self, admin_client: TestClient, caixa_user
    ) -> None:
        admin_client.post(
            "/api/pdv/select-operator", json={"operator_id": caixa_user.id}
        )
        r = admin_client.get("/pdv", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/pdv"
        assert SESSION_COOKIE not in admin_client.cookies

        assert admin_client.get("/pdv", follow_redirects=False).status_code == 200
        venda = admin_client.post("/api/sales").json()
        assert venda["user_id"] == caixa_user.id

    def test_mesmo_usuario_mantem_painel(self, admin_client: TestClient) -> None:
        uid = admin_client.get("/auth/me").json()["id"]
        admin_client.post("/api/pdv/select-operator", json={"operator_id": uid})
        assert admin_client.get("/pdv", follow_redirects=False).status_code == 200
        assert SESSION_COOKIE in admin_client.cookies


class TestDiaLocal:
    def test_janela_de_hoje_comeca_a_meia_noite_local(self) -> None:
        inicio, fim = _today_window()
        local = inicio.replace(tzinfo=timezone.utc).astimezone()
        assert (local.hour, local.minute, local.second) == (0, 0, 0)
        assert local.date() == datetime.now().date()
        assert fim - inicio == timedelta(days=1) - timedelta(microseconds=1)


class TestBackupAoFechar:
    def test_sem_setting_salvo_dispara_backup(self, session) -> None:
        with (
            patch.object(backup_hook, "_destinations", return_value=["X:\\b"]),
            patch.object(backup_hook.threading, "Thread") as thread,
        ):
            backup_hook.trigger_post_close_backup(session, None)
        thread.return_value.start.assert_called_once()
