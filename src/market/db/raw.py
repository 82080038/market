"""Database connection helper supporting both SQLite and PostgreSQL.

Provides a unified interface for raw SQL queries (used by scripts and
analysis modules that bypass SQLAlchemy ORM). Backend is determined by
settings.db_backend.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from market.config import settings

if TYPE_CHECKING:
    from collections.abc import Generator


class _PgConnWrapper:
    """Wrapper around psycopg2 connection that adds sqlite3-like .execute().

    sqlite3.Connection has a direct .execute() method that returns a cursor.
    psycopg2 connections do not — they require an explicit cursor() call.
    This wrapper bridges the gap so callers can use ``conn.execute(sql, params)``
    uniformly regardless of backend.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        if params is not None:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._conn.row_factory = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._conn.__exit__(*args)


@contextmanager
def get_raw_connection() -> Generator[object, None, None]:
    """Yield a raw DBAPI connection (sqlite3 or psycopg2).

    Usage:
        with get_raw_connection() as conn:
            rows = conn.execute("SELECT ...").fetchall()

    Note: For SQLite, returns sqlite3.Connection.
    For PostgreSQL, returns _PgConnWrapper (sqlite3-compatible interface).
    """
    if settings.db_backend == "postgresql":
        import psycopg2
        dsn = settings.database_url
        if dsn.startswith("postgresql+psycopg2://"):
            dsn = dsn.replace("postgresql+psycopg2://", "postgresql://", 1)
        conn = psycopg2.connect(dsn)
        try:
            yield _PgConnWrapper(conn)
        finally:
            conn.close()
    else:
        import sqlite3
        db_path = str(settings.resolved_db_path)
        conn = sqlite3.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()


def execute_query(sql: str, params: tuple | None = None) -> list[tuple]:
    """Execute a query and return all rows.

    Handles parameter style differences:
    - SQLite: ? placeholders
    - PostgreSQL: %s placeholders

    Automatically converts ? to %s for PostgreSQL.
    """
    if settings.db_backend == "postgresql":
        pg_sql = sql.replace("?", "%s")
        with get_raw_connection() as conn:
            cur = conn.cursor()
            cur.execute(pg_sql, params or ())
            rows = cur.fetchall()
            cur.close()
            return rows
    else:
        with get_raw_connection() as conn:
            cur = conn.execute(sql, params or ())
            rows = cur.fetchall()
            cur.close()
            return rows
