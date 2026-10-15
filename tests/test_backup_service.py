"""Testes do backup_service (puro, sem HTTP)."""

from __future__ import annotations

import gzip
import sqlite3
import time
from pathlib import Path

import pytest

from app.services.backup_service import (
    BackupResult,
    create_backup,
    list_backup_files,
)


def _make_db(path: Path) -> None:
    """Cria um SQLite minimo pra testar."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('a'), ('b'), ('c')")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    p = tmp_path / "pdv.db"
    _make_db(p)
    return p


class TestCreateBackup:
    def test_backup_compressed_grava_gz(self, source_db, tmp_path):
        dest = tmp_path / "dest1"
        r = create_backup(source_db, [dest], compress=True)
        assert r.ok_count == 1
        assert r.fail_count == 0
        files = list(dest.glob("pdv-backup-*.db.gz"))
        assert len(files) == 1

    def test_backup_sem_compressao_grava_db(self, source_db, tmp_path):
        dest = tmp_path / "dest1"
        r = create_backup(source_db, [dest], compress=False)
        files = list(dest.glob("pdv-backup-*.db"))
        assert len(files) == 1

    def test_backup_dois_destinos(self, source_db, tmp_path):
        d1 = tmp_path / "pendrive"
        d2 = tmp_path / "gdrive"
        r = create_backup(source_db, [d1, d2])
        assert r.ok_count == 2
        assert len(list(d1.glob("*.db.gz"))) == 1
        assert len(list(d2.glob("*.db.gz"))) == 1

    def test_falha_em_um_destino_nao_quebra_outro(self, source_db, tmp_path):
        bom = tmp_path / "ok"
        # Simula destino invalido: arquivo onde deveria ser pasta
        ruim = tmp_path / "x.txt"
        ruim.write_text("sou arquivo, nao pasta")

        r = create_backup(source_db, [bom, ruim])
        assert r.ok_count == 1
        assert r.fail_count == 1
        bom_ok = next((x for x in r.results if x.status == "ok"), None)
        ruim_fail = next((x for x in r.results if x.status == "fail"), None)
        assert bom_ok is not None
        assert ruim_fail is not None
        assert ruim_fail.error is not None

    def test_backup_db_inexistente_levanta(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            create_backup(tmp_path / "nao-existe.db", [tmp_path / "dest"])

    def test_integridade_do_backup_comprimido(self, source_db, tmp_path):
        dest = tmp_path / "dest"
        create_backup(source_db, [dest], compress=True)
        gz_file = next(dest.glob("*.db.gz"))

        # Descomprime e abre pra verificar integridade
        tmp_db = tmp_path / "restaurado.db"
        with gzip.open(gz_file, "rb") as fi, open(tmp_db, "wb") as fo:
            fo.write(fi.read())
        conn = sqlite3.connect(str(tmp_db))
        try:
            rows = conn.execute("SELECT v FROM t ORDER BY id").fetchall()
            assert [r[0] for r in rows] == ["a", "b", "c"]
            # SQLite integrity check
            check = conn.execute("PRAGMA integrity_check").fetchone()
            assert check[0] == "ok"
        finally:
            conn.close()

    def test_api_nativa_nao_bloqueia_db_aberto(self, source_db, tmp_path):
        """
        Mantem uma conexao aberta no source enquanto roda o backup.
        A API nativa de SQLite deve permitir essa coexistencia.
        """
        active = sqlite3.connect(str(source_db))
        try:
            dest = tmp_path / "dest"
            r = create_backup(source_db, [dest])
            assert r.ok_count == 1
        finally:
            active.close()


class TestRotation:
    def test_mantem_keep_last(self, source_db, tmp_path):
        dest = tmp_path / "dest"
        # Faz 5 backups, mantendo os 3 mais recentes
        for _ in range(5):
            create_backup(source_db, [dest], keep_last=3)
            time.sleep(1.1)  # garante mtime diferente
        files = sorted(dest.glob("pdv-backup-*.db.gz"))
        assert len(files) == 3

    def test_keep_last_zero_mantem_tudo(self, source_db, tmp_path):
        dest = tmp_path / "dest"
        for _ in range(3):
            create_backup(source_db, [dest], keep_last=0)
            time.sleep(1.1)
        files = list(dest.glob("pdv-backup-*.db.gz"))
        assert len(files) == 3


class TestListBackupFiles:
    def test_lista_vazio_quando_pasta_nao_existe(self, tmp_path):
        assert list_backup_files(tmp_path / "nao-existe") == []

    def test_lista_recentes_primeiro(self, source_db, tmp_path):
        dest = tmp_path / "dest"
        create_backup(source_db, [dest])
        time.sleep(1.1)
        create_backup(source_db, [dest])
        rows = list_backup_files(dest)
        assert len(rows) == 2
        # mais recente primeiro
        assert rows[0]["modified_at"] >= rows[1]["modified_at"]
