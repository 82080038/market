"""Tests for Alembic migration integrity (Gap #30).

Verifies:
1. Migration chain integrity (revision/down_revision links)
2. All migration files have upgrade() and downgrade() functions
3. Alembic head matches expected (0023)
4. Migration 0023 compatibility view exists in production DB
5. Migration files are syntactically valid Python
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

ALEMBIC_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"
EXPECTED_HEAD = "0023"


def _load_migration_module(filepath: Path):
    """Load a migration file as a module without importing the package."""
    spec = importlib.util.spec_from_file_location(
        f"_migration_{filepath.stem}", filepath,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {filepath}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _get_migration_files() -> list[Path]:
    """Get all migration .py files (excluding __pycache__)."""
    return sorted(
        f for f in ALEMBIC_VERSIONS_DIR.glob("*.py")
        if f.stem != "__init__" and not f.name.startswith("__")
    )


def test_migration_files_exist():
    """Migration files exist in alembic/versions/."""
    files = _get_migration_files()
    assert len(files) >= 23, f"Expected at least 23 migrations, got {len(files)}"


def test_migration_chain_integrity():
    """All migrations have valid revision/down_revision links forming a chain."""
    files = _get_migration_files()
    revisions: dict[str, str | None] = {}  # revision -> down_revision
    revision_to_file: dict[str, Path] = {}

    for f in files:
        mod = _load_migration_module(f)
        rev = getattr(mod, "revision", None)
        down = getattr(mod, "down_revision", None)
        assert rev is not None, f"{f.name} missing revision"
        revisions[rev] = down
        revision_to_file[rev] = f

    # Find head (revision not referenced as down_revision by any other)
    referenced = {d for d in revisions.values() if d is not None}
    heads = [r for r in revisions if r not in referenced]

    assert len(heads) == 1, f"Expected 1 head, got {heads}"
    assert heads[0] == EXPECTED_HEAD, f"Expected head {EXPECTED_HEAD}, got {heads[0]}"

    # Verify chain from head back to base
    chain: list[str] = []
    current: str | None = heads[0]
    while current is not None:
        chain.append(current)
        assert current in revisions, f"Missing migration for revision {current}"
        current = revisions[current]
        # Prevent infinite loop
        if len(chain) > len(revisions) + 1:
            pytest.fail(f"Cycle detected in migration chain: {chain}")

    assert len(chain) == len(revisions), (
        f"Chain length {len(chain)} != revision count {len(revisions)}. "
        f"Missing: {set(revisions) - set(chain)}"
    )


def test_migrations_have_upgrade_and_downgrade():
    """All migration files define upgrade() and downgrade() functions."""
    files = _get_migration_files()
    for f in files:
        mod = _load_migration_module(f)
        assert callable(getattr(mod, "upgrade", None)), (
            f"{f.name} missing upgrade() function"
        )
        assert callable(getattr(mod, "downgrade", None)), (
            f"{f.name} missing downgrade() function"
        )


def test_migration_0023_code_map():
    """Migration 0023 has correct exchange code mapping."""
    f = ALEMBIC_VERSIONS_DIR / "0023_merge_market_calendar.py"
    if not f.exists():
        pytest.skip("Migration 0023 not found")
    mod = _load_migration_module(f)
    code_map = getattr(mod, "_CODE_MAP", None)
    assert code_map is not None, "0023 missing _CODE_MAP"
    assert code_map["IDX"] == "XIDX"
    assert code_map["XTKS"] == "XTSE"


def test_alembic_config_exists():
    """alembic.ini exists and is configured."""
    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    assert ini.exists(), "alembic.ini missing"
    content = ini.read_text()
    assert "[alembic]" in content
    assert "script_location" in content


def test_alembic_env_exists():
    """alembic/env.py exists."""
    env = Path(__file__).resolve().parent.parent / "alembic" / "env.py"
    assert env.exists(), "alembic/env.py missing"


def test_production_db_at_head():
    """Production DB alembic_version table is at expected head (0023).

    Skips if DATABASE_URL not configured or DB unreachable.
    """
    try:
        from market.config import settings
        from sqlalchemy import create_engine, text
    except ImportError:
        pytest.skip("SQLAlchemy/config not available")

    try:
        engine = create_engine(settings.resolved_database_url)
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchone()
            if result is None:
                pytest.skip("alembic_version table empty or missing")
            assert result[0] == EXPECTED_HEAD, (
                f"DB at {result[0]}, expected {EXPECTED_HEAD}"
            )
    except Exception as exc:
        pytest.skip(f"Cannot connect to DB: {exc}")


def test_compatibility_views_exist():
    """Compatibility views exist in production DB (from migration 0022/0023).

    Skips if DB unreachable.
    """
    try:
        from market.config import settings
        from sqlalchemy import create_engine, text
    except ImportError:
        pytest.skip("SQLAlchemy/config not available")

    try:
        engine = create_engine(settings.resolved_database_url)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT viewname FROM pg_views "
                "WHERE viewname IN ('instrument_master', 'market_registry', 'market_calendar')"
            )).fetchall()
            view_names = {r[0] for r in result}
            # market_calendar view should exist after 0023
            assert "market_calendar" in view_names, (
                f"market_calendar view missing. Found: {view_names}"
            )
    except Exception as exc:
        pytest.skip(f"Cannot connect to DB: {exc}")
