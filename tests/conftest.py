"""Pytest configuration: ensure tests use an isolated PostgreSQL test database.

Test DB strategy (per user decision 2026-08-15):
- Production uses PostgreSQL (`market` database).
- Tests use a dedicated `market_test` database in the same PG instance.
- `market_test` schema is cloned from `market` via `pg_dump --schema-only`
  once per pytest session (or reused if already populated).
- Each `isolated_db` test truncates all tables (CASCADE) for isolation.

This ensures tests run against the exact same schema as production, including
compatibility views (market_registry, instrument_master), partitioned tables,
FK constraints, and all PG-specific DDL.

Note: alembic migrations 0001-0006 contain SQLite-isms (e.g. BOOLEAN DEFAULT 0)
that fail on PostgreSQL. The production `market` database was created via
`docs/domino_effect_schema.sql` (raw DDL), not alembic. Therefore we clone
the schema via pg_dump rather than running alembic upgrade head.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from urllib.parse import urlparse, parse_qs

import pytest
from sqlalchemy import create_engine, text

# Load .env so DATABASE_URL is available (python-dotenv is a project dependency)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Constants ──────────────────────────────────────────────────────────────

def _test_db_url() -> str:
    """Build the test database URL from the production DATABASE_URL or default."""
    prod_url = os.environ.get("DATABASE_URL", "")
    if prod_url:
        # Split URL and query string to preserve socket host params
        base, _, query = prod_url.partition("?")
        if "/market" in base:
            test_base = base.rsplit("/market", 1)[0] + "/market_test"
        else:
            test_base = base + "_test"
        return test_base + (f"?{query}" if query else "")
    return "postgresql://petrick:market_dev@localhost:5432/market_test"


def _prod_db_url() -> str:
    """Build the production database URL for schema source."""
    return os.environ.get("DATABASE_URL", "postgresql://petrick:market_dev@localhost:5432/market")


TEST_DB_URL = _test_db_url()
PROD_DB_URL = _prod_db_url()


def _parse_pg_url(url: str) -> dict:
    """Parse a PostgreSQL URL into connection params.

    Handles both TCP URLs (postgresql://user:pass@host:port/db) and
    socket URLs (postgresql+psycopg2:///db?host=/var/run/postgresql).
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    # Socket connections put host in query string (e.g. ?host=/var/run/postgresql)
    socket_host = query_params.get("host", [None])[0]
    return {
        "host": parsed.hostname or socket_host or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "petrick",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/").split("/")[-1] if parsed.path else "market",
    }


# ── Session-scoped: ensure test DB exists and has schema ───────────────────

@pytest.fixture(scope="session", autouse=True)
def _ensure_test_db():
    """Ensure market_test database exists and has the production schema.

    Runs once per pytest session:
    1. Create market_test database if missing.
    2. Check if schema is already populated (has 'exchanges' table).
    3. If empty, dump schema from market (production) via pg_dump and load it.
    4. Reuse across sessions for speed (truncated per-test, not dropped).
    """
    test_params = _parse_pg_url(TEST_DB_URL)
    prod_params = _parse_pg_url(PROD_DB_URL)

    # Step 1: Create test database if missing
    # Build admin URL — handle socket connections (host is a path like /var/run/postgresql)
    if test_params["host"].startswith("/"):
        admin_url = f"postgresql+psycopg2:///postgres?host={test_params['host']}"
    else:
        admin_url = (
            f"postgresql://{test_params['user']}:{test_params['password']}"
            f"@{test_params['host']}:{test_params['port']}/postgres"
        )
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :db"),
                {"db": test_params["dbname"]},
            ).fetchone()
            if result is None:
                conn.execute(
                    text(f'CREATE DATABASE "{test_params["dbname"]}" OWNER "{test_params["user"]}"')
                )
                print(f"[conftest] Created test database: {test_params['dbname']}")
    finally:
        admin_engine.dispose()

    # Step 2: Check if schema is already populated
    test_engine = create_engine(TEST_DB_URL)
    schema_populated = False
    try:
        with test_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'exchanges'"
            )).fetchone()
            schema_populated = result is not None
    except Exception:
        pass
    finally:
        test_engine.dispose()

    # Step 3: If empty, clone schema from production via pg_dump
    if not schema_populated:
        print(f"[conftest] Cloning schema from {prod_params['dbname']} to {test_params['dbname']}...")
        # Cross-platform: use PATH lookup, fallback to Windows default location
        pg_dump = shutil.which("pg_dump") or r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
        psql = shutil.which("psql") or r"C:\Program Files\PostgreSQL\16\bin\psql.exe"

        env = os.environ.copy()
        env["PGPASSWORD"] = prod_params["password"]

        # Dump schema-only (no data) from production
        dump_cmd = [
            pg_dump,
            "-h", prod_params["host"],
            "-p", str(prod_params["port"]),
            "-U", prod_params["user"],
            "-d", prod_params["dbname"],
            "--schema-only",
            "--no-owner",
            "--no-privileges",
        ]
        dump_result = subprocess.run(
            dump_cmd, capture_output=True, text=True, env=env, check=True
        )
        schema_sql = dump_result.stdout

        # Load schema into test database
        env["PGPASSWORD"] = test_params["password"]
        load_cmd = [
            psql,
            "-h", test_params["host"],
            "-p", str(test_params["port"]),
            "-U", test_params["user"],
            "-d", test_params["dbname"],
            "-v", "ON_ERROR_STOP=1",
        ]
        load_result = subprocess.run(
            load_cmd, input=schema_sql, capture_output=True, text=True, env=env, check=True
        )
        print(f"[conftest] Schema cloned successfully ({len(schema_sql)} bytes)")

    yield

    # Clean up engine connections at session end
    from market.db.engine import dispose_engine
    dispose_engine()


# ── Function-scoped: truncate tables for test isolation ────────────────────

def _truncate_all_tables(engine) -> None:
    """Truncate all tables in the test database (CASCADE).

    Provides per-test isolation without dropping/recreating the database.
    Excludes alembic_version table (migration state).
    """
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename != 'alembic_version' "
            "ORDER BY tablename"
        ))
        tables = [row[0] for row in result]

    if not tables:
        return

    table_list = ", ".join(f'"{t}"' for t in tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def isolated_db(monkeypatch):
    """Isolate DB to the market_test PostgreSQL database.

    - Sets DATABASE_URL to market_test
    - Truncates all tables before the test for clean state
    - Restores env after test
    """
    monkeypatch.setenv("ENV", "research")
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("BROKER_ADAPTER", "mock")

    from market import config as config_module
    from market.config import Settings

    new_settings = Settings()
    monkeypatch.setattr(config_module, "settings", new_settings)

    from market.db import engine as engine_module
    monkeypatch.setattr(engine_module, "settings", new_settings)

    from market.db.engine import dispose_engine
    dispose_engine()

    # Truncate all tables for clean test state
    test_engine = create_engine(TEST_DB_URL)
    _truncate_all_tables(test_engine)
    test_engine.dispose()

    yield

    dispose_engine()
    import gc
    gc.collect()


@pytest.fixture(autouse=True)
def _auto_isolated_db(request, monkeypatch):
    """Auto-isolate env vars for all tests; full DB isolation for marked tests.

    For non-isolated tests: only override ENV/BROKER_ADAPTER (no DB change).
    For isolated_db tests: redirect to market_test + truncate tables.
    """
    # Always override ENV to research to avoid .env file (ENV=paper) interference
    monkeypatch.setenv("ENV", "research")
    monkeypatch.setenv("BROKER_ADAPTER", "mock")

    from market import config as config_module
    from market.config import Settings

    new_settings = Settings()
    monkeypatch.setattr(config_module, "settings", new_settings)

    from market.db import engine as engine_module
    monkeypatch.setattr(engine_module, "settings", new_settings)

    # Reset cached engine so it picks up new settings
    from market.db.engine import dispose_engine
    dispose_engine()

    if "isolated_db" in request.keywords:
        monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)

        # Re-create settings with the test DB URL
        new_settings = Settings()
        monkeypatch.setattr(config_module, "settings", new_settings)
        monkeypatch.setattr(engine_module, "settings", new_settings)

        dispose_engine()

        # Truncate all tables for clean test state
        test_engine = create_engine(TEST_DB_URL)
        _truncate_all_tables(test_engine)
        test_engine.dispose()

    yield

    # Teardown: truncate again for isolated_db tests to prevent data leakage
    if "isolated_db" in request.keywords:
        test_engine = create_engine(TEST_DB_URL)
        _truncate_all_tables(test_engine)
        test_engine.dispose()

    dispose_engine()
    import gc
    gc.collect()
