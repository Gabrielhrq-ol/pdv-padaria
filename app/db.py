"""
Engine do SQLite com PRAGMAs ligados em TODA conexao:
- foreign_keys = ON  (CLAUDE.md regra 9 / seguranca)
- journal_mode = WAL (resiste melhor a queda de energia)
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base declarativa unica do projeto."""


def _ensure_data_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _build_engine() -> Engine:
    settings = get_settings()
    _ensure_data_dir(settings.db_absolute_path)
    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
    )
    return engine


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _conn_record) -> None:  # type: ignore[no-untyped-def]
    """
    Executa em TODA conexao nova (CLAUDE.md regra 9).
    foreign_keys e preciso ligar explicitamente no SQLite.
    """
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
    finally:
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    """Dependency do FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
