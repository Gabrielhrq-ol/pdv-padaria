"""Fixtures compartilhadas dos testes do PDV."""

from __future__ import annotations

import os

# SECRET_KEY precisa estar definida antes de importar app.config.
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-chars-xx")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DB_PATH", ":memory:")

from collections.abc import Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db as db_module  # noqa: E402, F401
from app.db import Base, get_db  # noqa: E402
import app.models  # noqa: E402, F401
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture
def engine_memory():
    """Engine SQLite in-memory limpa por teste."""
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
def SessionTesting(engine_memory):
    return sessionmaker(
        bind=engine_memory, autoflush=False, autocommit=False, future=True
    )


@pytest.fixture
def session(SessionTesting) -> Generator:
    s = SessionTesting()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def admin_user(SessionTesting) -> User:
    s = SessionTesting()
    try:
        u = User(
            name="Admin de Teste",
            username="admin",
            password_hash=hash_password("AdminSenha123"),
            role="admin",
            active=True,
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        return u
    finally:
        s.close()


@pytest.fixture
def caixa_user(SessionTesting) -> User:
    s = SessionTesting()
    try:
        u = User(
            name="Caixa de Teste",
            username="caixa",
            password_hash=hash_password("CaixaSenha123"),
            role="caixa",
            active=True,
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        return u
    finally:
        s.close()


def _make_client(SessionTesting) -> TestClient:
    """Cria um TestClient novo compartilhando o mesmo DB."""

    def _override_get_db() -> Generator:
        s = SessionTesting()
        try:
            yield s
        finally:
            s.close()

    from app.main import app

    # dependency_overrides e dict compartilhado - override uma vez basta.
    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app, base_url="http://127.0.0.1")


@pytest.fixture
def client(SessionTesting) -> Generator[TestClient, None, None]:
    """TestClient anonimo (sem login)."""
    from app.main import app

    with _make_client(SessionTesting) as c:
        yield c
    app.dependency_overrides.clear()


def _login(c: TestClient, username: str, password: str) -> str:
    """Faz login e devolve o csrf_token. Lanca em falha."""
    resp = c.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


@pytest.fixture
def admin_client(SessionTesting, admin_user: User) -> Generator[TestClient, None, None]:
    """
    TestClient autenticado como admin, independente do client anonimo
    e do caixa_client. Cada um tem seus proprios cookies.
    """
    from app.main import app

    with _make_client(SessionTesting) as c:
        csrf = _login(c, "admin", "AdminSenha123")
        c.headers["X-CSRF-Token"] = csrf
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def caixa_client(SessionTesting, caixa_user: User) -> Generator[TestClient, None, None]:
    """TestClient autenticado como caixa."""
    from app.main import app

    with _make_client(SessionTesting) as c:
        csrf = _login(c, "caixa", "CaixaSenha123")
        c.headers["X-CSRF-Token"] = csrf
        yield c
    app.dependency_overrides.clear()
