"""Pytest configuration: ensure tests use an isolated test database."""

from __future__ import annotations

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "isolated_db: isolate DB to tmp_path")


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Redirect the application DB to a temp file for this test.

    This prevents tests from polluting the real research/paper/live databases.
    """
    test_db = tmp_path / "test_market.db"

    monkeypatch.setenv("ENV", "research")
    monkeypatch.setenv("DB_PATH", str(test_db))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BROKER_ADAPTER", "mock")

    from market import config as config_module
    from market.config import Settings

    new_settings = Settings()
    monkeypatch.setattr(config_module, "settings", new_settings)

    from market.db import engine as engine_module
    monkeypatch.setattr(engine_module, "settings", new_settings)

    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{test_db}",
    )
    command.upgrade(alembic_cfg, "head")

    yield

    import gc
    gc.collect()


@pytest.fixture(autouse=True)
def _auto_isolated_db(request, tmp_path, monkeypatch):
    """Auto-isolate env vars for all tests; full DB isolation for marked tests."""
    # Always override ENV to research to avoid .env file (ENV=paper) interference
    monkeypatch.setenv("ENV", "research")
    monkeypatch.setenv("BROKER_ADAPTER", "mock")

    from market import config as config_module
    from market.config import Settings

    new_settings = Settings()
    monkeypatch.setattr(config_module, "settings", new_settings)

    from market.db import engine as engine_module
    monkeypatch.setattr(engine_module, "settings", new_settings)

    if "isolated_db" in request.keywords:
        test_db = tmp_path / "test_market.db"
        monkeypatch.setenv("DB_PATH", str(test_db))
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        # Re-create settings with the isolated DB path
        new_settings = Settings()
        monkeypatch.setattr(config_module, "settings", new_settings)
        monkeypatch.setattr(engine_module, "settings", new_settings)

        from alembic import command
        from alembic.config import Config as AlembicConfig

        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_cfg.set_main_option(
            "sqlalchemy.url",
            f"sqlite:///{test_db}",
        )
        command.upgrade(alembic_cfg, "head")

    yield

    import gc
    gc.collect()

