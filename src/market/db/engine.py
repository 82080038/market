"""SQLAlchemy database engine and session management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from market.config import settings

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import Engine


def _make_engine(db_path: str) -> Engine:
    """Create a SQLite WAL engine with pragmas for performance."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(
        url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def get_engine() -> Engine:
    """Return the SQLAlchemy engine for the active environment."""
    return _make_engine(str(settings.resolved_db_path))


def get_sessionmaker() -> sessionmaker[Session]:
    """Return a sessionmaker bound to the active engine."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a session and close it after use."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
