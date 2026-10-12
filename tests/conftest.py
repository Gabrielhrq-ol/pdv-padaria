"""Fixtures compartilhadas dos testes do PDV."""

from __future__ import annotations

import os

# Precisa estar definida antes de importar app.config.
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-chars-xx")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DB_PATH", ":memory:")

from collections.abc import Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db as db_module  # noqa: E402
from app.db import Base, get_db  # noqa: E402
import app.models  # noqa: E402, F401


@pytest.fixture
def engine_memory():
    """Engine SQLite in-memory limpa por teste."""
    # StaticPool mantem uma unica conexao - necessario em in-memory,
    # senao cada sessao abre um DB novo e nao enxerga as tabelas.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        c = dbapi_conn.cursor()
        try:
            c.execute("PRAGMA foreign_keys = ON")
        finally:
            c.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine_memory) -> Generator:
    SessionTesting = sessionmaker(
        bind=engine_memory, autoflush=False, autocommit=False, future=True
    )
    s = SessionTesting()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(engine_memory) -> Generator[TestClient, None, None]:
    """TestClient com DB in-memory substituindo o engine global."""
    SessionTesting = sessionmaker(
        bind=engine_memory, autoflush=False, autocommit=False, future=True
    )

    def _override_get_db() -> Generator:
        s = SessionTesting()
        try:
            yield s
        finally:
            s.close()

    # Importa a app depois dos env vars.
    from app.main import app

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c
    app.dependency_overrides.clear()
