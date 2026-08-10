"""Tests for ticker migration and resolve_ticker functionality.

Tests cover:
- resolve_ticker: old → new ticker resolution via former_ticker
- resolve_ticker_batch: batch resolution
- migrate_ticker: full migration across tables
- check_stale_ticker_references: stale detection
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from market.data.ticker_util import resolve_ticker, resolve_ticker_batch


@pytest.fixture
def test_db() -> sqlite3.Connection:
    """Create a test database with instrument_master and ohlcv tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE instrument_master (
            ticker TEXT PRIMARY KEY,
            market_mic TEXT,
            asset_class TEXT,
            name TEXT,
            former_ticker TEXT,
            former_name TEXT,
            trading_status TEXT DEFAULT 'active',
            is_active INTEGER DEFAULT 1,
            delisting_risk_reason TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ohlcv (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestamp TEXT,
            timeframe TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
    """)
    conn.execute("""
        CREATE TABLE stock_personality (
            ticker TEXT PRIMARY KEY,
            best_pattern TEXT,
            volatility_regime TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE technical_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            date TEXT,
            indicator TEXT,
            value REAL
        )
    """)
    conn.execute("""
        CREATE TABLE recompute_watermark (
            ticker TEXT PRIMARY KEY,
            table_name TEXT,
            last_processed_date TEXT,
            last_ohlcv_date TEXT,
            rows_processed INTEGER,
            updated_at TEXT
        )
    """)

    # Insert test data
    conn.execute(
        "INSERT INTO instrument_master (ticker, market_mic, asset_class, name) VALUES (?, 'XIDX', 'equity', 'Test Bank')",
        ("BNLI.JK",),
    )
    conn.execute(
        "INSERT INTO instrument_master (ticker, market_mic, asset_class, name) VALUES (?, 'XIDX', 'equity', 'Bank Central Asia')",
        ("BBCA.JK",),
    )
    # Insert OHLCV data
    for i in range(5):
        conn.execute(
            "INSERT INTO ohlcv (ticker, timestamp, timeframe, open, high, low, close, volume) VALUES (?, ?, '1d', 100, 110, 90, 105, 1000)",
            ("BNLI.JK", f"2026-01-{i+1:02d}"),
        )
    conn.execute(
        "INSERT INTO stock_personality (ticker, best_pattern, volatility_regime) VALUES (?, 'donchian', 'low')",
        ("BNLI.JK",),
    )
    conn.execute(
        "INSERT INTO technical_indicators (ticker, date, indicator, value) VALUES (?, '2026-01-01', 'rsi', 55.0)",
        ("BNLI.JK",),
    )
    conn.commit()
    return conn


class TestResolveTicker:
    """Tests for resolve_ticker()."""

    def test_no_rename_returns_same(self, test_db):
        """Ticker without former_ticker returns itself."""
        result = resolve_ticker("BBCA.JK", conn=test_db)
        assert result == "BBCA.JK"

    def test_resolves_after_rename(self, test_db):
        """After setting former_ticker, old ticker resolves to new."""
        # Simulate rename: BNLI → BBPI
        test_db.execute(
            "UPDATE instrument_master SET ticker = 'BBPI.JK', former_ticker = 'BNLI.JK' WHERE ticker = 'BNLI.JK'"
        )
        test_db.commit()

        # Old ticker should resolve to new
        result = resolve_ticker("BNLI.JK", conn=test_db)
        assert result == "BBPI.JK"

    def test_current_ticker_returns_itself(self, test_db):
        """Current ticker (with former_ticker set) returns itself."""
        test_db.execute(
            "UPDATE instrument_master SET ticker = 'BBPI.JK', former_ticker = 'BNLI.JK' WHERE ticker = 'BNLI.JK'"
        )
        test_db.commit()

        result = resolve_ticker("BBPI.JK", conn=test_db)
        assert result == "BBPI.JK"

    def test_unknown_ticker_returns_itself(self, test_db):
        """Unknown ticker returns itself."""
        result = resolve_ticker("UNKNOWN.JK", conn=test_db)
        assert result == "UNKNOWN.JK"

    def test_none_conn_returns_input(self):
        """With conn=None, returns input unchanged."""
        result = resolve_ticker("BNLI.JK", conn=None)
        assert result == "BNLI.JK"

    def test_preserves_rename_chain(self, test_db):
        """If ticker was already renamed once, second rename preserves chain.

        Note: Only the original ticker (BNLI.JK) resolves to the current one.
        Intermediate tickers (BBPI.JK) are not stored as former_ticker —
        the chain always points to the original.
        """
        # First rename: BNLI → BBPI
        test_db.execute(
            "UPDATE instrument_master SET ticker = 'BBPI.JK', former_ticker = 'BNLI.JK', former_name = 'Bank Permata' WHERE ticker = 'BNLI.JK'"
        )
        test_db.commit()

        # Second rename: BBPI → BBPP (former_ticker stays as original BNLI)
        test_db.execute(
            "UPDATE instrument_master SET ticker = 'BBPP.JK', former_ticker = 'BNLI.JK', former_name = 'Bank Permata' WHERE ticker = 'BBPI.JK'"
        )
        test_db.commit()

        # Original old ticker resolves to latest
        assert resolve_ticker("BNLI.JK", conn=test_db) == "BBPP.JK"
        # Current returns itself
        assert resolve_ticker("BBPP.JK", conn=test_db) == "BBPP.JK"


class TestResolveTickerBatch:
    """Tests for resolve_ticker_batch()."""

    def test_batch_no_renames(self, test_db):
        """No renames → empty result."""
        result = resolve_ticker_batch(["BBCA.JK", "BNLI.JK"], conn=test_db)
        assert result == {}

    def test_batch_with_rename(self, test_db):
        """Batch resolves renamed tickers."""
        test_db.execute(
            "UPDATE instrument_master SET ticker = 'BBPI.JK', former_ticker = 'BNLI.JK' WHERE ticker = 'BNLI.JK'"
        )
        test_db.commit()

        result = resolve_ticker_batch(["BNLI.JK", "BBCA.JK"], conn=test_db)
        assert result == {"BNLI.JK": "BBPI.JK"}

    def test_batch_empty_input(self, test_db):
        """Empty input → empty result."""
        result = resolve_ticker_batch([], conn=test_db)
        assert result == {}

    def test_batch_none_conn(self):
        """None conn → empty result."""
        result = resolve_ticker_batch(["BNLI.JK"], conn=None)
        assert result == {}


class TestMigrateTicker:
    """Tests for migrate_ticker script."""

    def test_dry_run_no_changes(self, test_db):
        """Dry-run should not modify any data."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_ticker",
            str(Path(__file__).parent.parent / "scripts" / "migrate_ticker.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        stats = mod.migrate_ticker(
            test_db, "BNLI.JK", "BBPI.JK", dry_run=True
        )

        # Data should be unchanged
        row = test_db.execute("SELECT ticker FROM instrument_master WHERE ticker = 'BNLI.JK'").fetchone()
        assert row is not None  # Still exists
        row = test_db.execute("SELECT ticker FROM instrument_master WHERE ticker = 'BBPI.JK'").fetchone()
        assert row is None  # New ticker not created

    def test_migrate_updates_all_tables(self, test_db):
        """Migration should update instrument_master, ohlcv, stock_personality, technical_indicators."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_ticker",
            str(Path(__file__).parent.parent / "scripts" / "migrate_ticker.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        stats = mod.migrate_ticker(
            test_db, "BNLI.JK", "BBPI.JK",
            reason="BEI ticker change test",
        )

        # instrument_master updated
        row = test_db.execute(
            "SELECT ticker, former_ticker, former_name FROM instrument_master WHERE ticker = 'BBPI.JK'"
        ).fetchone()
        assert row is not None
        assert row[1] == "BNLI.JK"  # former_ticker set

        # Old ticker gone from instrument_master
        row = test_db.execute("SELECT ticker FROM instrument_master WHERE ticker = 'BNLI.JK'").fetchone()
        assert row is None

        # OHLCV migrated
        count = test_db.execute("SELECT COUNT(*) FROM ohlcv WHERE ticker = 'BBPI.JK'").fetchone()[0]
        assert count == 5
        count = test_db.execute("SELECT COUNT(*) FROM ohlcv WHERE ticker = 'BNLI.JK'").fetchone()[0]
        assert count == 0

        # stock_personality migrated
        row = test_db.execute("SELECT ticker FROM stock_personality WHERE ticker = 'BBPI.JK'").fetchone()
        assert row is not None
        row = test_db.execute("SELECT ticker FROM stock_personality WHERE ticker = 'BNLI.JK'").fetchone()
        assert row is None

        # technical_indicators migrated
        count = test_db.execute("SELECT COUNT(*) FROM technical_indicators WHERE ticker = 'BBPI.JK'").fetchone()[0]
        assert count == 1
        count = test_db.execute("SELECT COUNT(*) FROM technical_indicators WHERE ticker = 'BNLI.JK'").fetchone()[0]
        assert count == 0

    def test_migrate_nonexistent_ticker(self, test_db):
        """Migrating a nonexistent ticker should fail gracefully."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_ticker",
            str(Path(__file__).parent.parent / "scripts" / "migrate_ticker.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        stats = mod.migrate_ticker(test_db, "FAKE.JK", "NEW.JK")
        assert stats == {}  # No changes

    def test_migrate_to_existing_ticker_fails(self, test_db):
        """Cannot migrate to a ticker that already exists."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_ticker",
            str(Path(__file__).parent.parent / "scripts" / "migrate_ticker.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        stats = mod.migrate_ticker(test_db, "BNLI.JK", "BBCA.JK")
        assert stats == {}  # No changes

    def test_migrate_preserves_former_chain(self, test_db):
        """Second migration preserves the original former_ticker."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_ticker",
            str(Path(__file__).parent.parent / "scripts" / "migrate_ticker.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # First rename: BNLI → BBPI
        mod.migrate_ticker(test_db, "BNLI.JK", "BBPI.JK", reason="first rename")
        # Second rename: BBPI → BBPP
        mod.migrate_ticker(test_db, "BBPI.JK", "BBPP.JK", reason="second rename")

        row = test_db.execute(
            "SELECT ticker, former_ticker, former_name FROM instrument_master WHERE ticker = 'BBPP.JK'"
        ).fetchone()
        assert row is not None
        assert row[1] == "BNLI.JK"  # Chain preserved to original


def _check_stale_ticker_references(conn: sqlite3.Connection) -> list[str]:
    """Inline copy of check_stale_ticker_references for testing."""
    renamed = conn.execute(
        "SELECT ticker, former_ticker FROM instrument_master WHERE former_ticker IS NOT NULL"
    ).fetchall()

    stale: list[str] = []
    for current, former in renamed:
        if not former:
            continue
        count = conn.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE ticker = ?", (former,)
        ).fetchone()[0]
        if count > 0:
            stale.append(former)
    return stale


class TestCheckStaleTickerReferences:
    """Tests for check_stale_ticker_references logic."""

    def test_no_stale_when_no_rename(self, test_db):
        """No renames → no stale references."""
        stale = _check_stale_ticker_references(test_db)
        assert stale == []

    def test_detects_stale_after_rename(self, test_db):
        """Rename without migrating OHLCV → stale detected."""
        # Rename in instrument_master but don't migrate ohlcv
        test_db.execute(
            "UPDATE instrument_master SET ticker = 'BBPI.JK', former_ticker = 'BNLI.JK' WHERE ticker = 'BNLI.JK'"
        )
        test_db.commit()

        stale = _check_stale_ticker_references(test_db)
        assert "BNLI.JK" in stale

    def test_no_stale_after_full_migration(self, test_db):
        """Full migration (including ohlcv) → no stale."""
        import importlib.util

        # Migrate ticker fully
        spec = importlib.util.spec_from_file_location(
            "migrate_ticker",
            str(Path(__file__).parent.parent / "scripts" / "migrate_ticker.py"),
        )
        migrate_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migrate_mod)
        migrate_mod.migrate_ticker(test_db, "BNLI.JK", "BBPI.JK")

        stale = _check_stale_ticker_references(test_db)
        assert stale == []
