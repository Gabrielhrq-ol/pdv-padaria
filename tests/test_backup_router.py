"""Testes dos endpoints de /api/admin/backup e pagina /admin/backup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fake_db_file(tmp_path, monkeypatch):
    """
    Cria um arquivo SQLite real pra o backup_service copiar.
    Nos testes normais o DB e :memory: e o backup_service nao conseguiria
    gerar snapshot. Patcheia a config pra apontar pra esse arquivo.
    """
    db_path = tmp_path / "pdv.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
    finally:
        conn.close()

    from app.services import backup_hook

    class _FakeSettings:
        db_absolute_path = db_path

    monkeypatch.setattr(backup_hook, "get_settings", lambda: _FakeSettings())
    return db_path


class TestAutorizacao:
    def test_anonimo_401_settings(self, client: TestClient) -> None:
        assert client.get("/api/admin/backup/settings").status_code == 401

    def test_caixa_403_settings(self, caixa_client: TestClient) -> None:
        assert caixa_client.get("/api/admin/backup/settings").status_code == 403

    def test_caixa_403_run(self, caixa_client: TestClient) -> None:
        assert caixa_client.post("/api/admin/backup/run").status_code == 403

    def test_caixa_403_history(self, caixa_client: TestClient) -> None:
        assert caixa_client.get("/api/admin/backup/history").status_code == 403


class TestSettings:
    def test_defaults(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/admin/backup/settings")
        assert r.status_code == 200
        d = r.json()
        assert d["backup_dir_1"] is None
        assert d["backup_dir_2"] is None
        assert d["backup_keep"] == 30
        assert d["backup_on_cash_close"] is True
        assert d["backup_compress"] is True

    def test_salva(self, admin_client: TestClient, tmp_path: Path) -> None:
        dest = str(tmp_path / "pendrive")
        r = admin_client.put(
            "/api/admin/backup/settings",
            json={
                "backup_dir_1": dest,
                "backup_keep": 10,
                "backup_on_cash_close": False,
                "backup_compress": False,
            },
        )
        assert r.status_code == 200
        d = r.json()
        assert d["backup_dir_1"] == dest
        assert d["backup_dir_2"] is None
        assert d["backup_keep"] == 10
        assert d["backup_on_cash_close"] is False
        assert d["backup_compress"] is False

    def test_sem_csrf_falha(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.put(
            "/api/admin/backup/settings",
            json={"backup_dir_1": str(tmp_path)},
        )
        assert r.status_code == 403


class TestRun:
    def test_run_sem_destinos_falha_400(self, admin_client: TestClient) -> None:
        r = admin_client.post("/api/admin/backup/run")
        assert r.status_code == 400
        assert "destino" in r.json()["detail"].lower()

    def test_run_com_destino_valido(
        self, admin_client: TestClient, tmp_path: Path, fake_db_file
    ) -> None:
        dest = str(tmp_path / "d1")
        admin_client.put(
            "/api/admin/backup/settings",
            json={"backup_dir_1": dest},
        )
        r = admin_client.post("/api/admin/backup/run")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok_count"] == 1
        assert data["fail_count"] == 0
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "ok"
        # arquivo foi criado
        files = list(Path(dest).glob("pdv-backup-*.db.gz"))
        assert len(files) == 1

    def test_run_sem_csrf(self, admin_client: TestClient, tmp_path: Path) -> None:
        admin_client.put(
            "/api/admin/backup/settings",
            json={"backup_dir_1": str(tmp_path)},
        )
        del admin_client.headers["X-CSRF-Token"]
        r = admin_client.post("/api/admin/backup/run")
        assert r.status_code == 403


class TestHistory:
    def test_history_vazio(self, admin_client: TestClient) -> None:
        r = admin_client.get("/api/admin/backup/history")
        assert r.status_code == 200
        assert r.json() == []

    def test_history_apos_run(
        self, admin_client: TestClient, tmp_path: Path, fake_db_file
    ) -> None:
        admin_client.put(
            "/api/admin/backup/settings",
            json={"backup_dir_1": str(tmp_path / "d1")},
        )
        admin_client.post("/api/admin/backup/run")
        r = admin_client.get("/api/admin/backup/history")
        rows = r.json()
        actions = [row["action"] for row in rows]
        assert "backup_run" in actions


class TestPagina:
    def test_admin_abre(self, admin_client: TestClient) -> None:
        r = admin_client.get("/admin/backup")
        assert r.status_code == 200
        assert "Backup" in r.text
        assert 'id="form-settings"' in r.text

    def test_caixa_redireciona(self, caixa_client: TestClient) -> None:
        r = caixa_client.get("/admin/backup", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"].endswith("/products")
