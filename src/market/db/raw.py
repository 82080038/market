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


@contextmanager
def get_raw_connection() -> Generator[object, None, None]:
    """Yield a raw DBAPI connection (sqlite3 or psycopg2).

    Usage:
        with get_raw_connection() as conn:
            rows = conn.execute("SELECT ...").fetchall()

    Note: For SQLite, returns sqlite3.Connection.
    For PostgreSQL, returns psycopg2 connection.
    """
    if settings.db_backend == "postgresql":
        import psycopg2
        conn = psycopg2.connect(settings.database_url)
        try:
            yield conn
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
