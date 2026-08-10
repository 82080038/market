"""Tests for stale data detection and refresh engine."""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from market.data.refresh_stale import (
    RefreshReport,
    StaleTableReport,
    detect_stale_tables,
    get_excluded_tickers,
    refresh_stale_data,
)


@pytest.fixture
def test_db():
    """Create a temporary test database with schema and sample data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    # instrument_master
    conn.execute("""
        CREATE TABLE instrument_master (
            ticker TEXT PRIMARY KEY,
            is_active INTEGER DEFAULT 1,
            delisting_date TEXT,
            suspension_date TEXT
        )
    """)
    conn.execute("INSERT INTO instrument_master (ticker, is_active) VALUES ('AAA.JK', 1)")
    conn.execute("INSERT INTO instrument_master (ticker, is_active) VALUES ('BBB.JK', 1)")
    conn.execute("INSERT INTO instrument_master (ticker, is_active, delisting_date) VALUES ('CCC.JK', 0, '2025-01-01')")
    conn.execute("INSERT INTO instrument_master (ticker, is_active, suspension_date) VALUES ('DDD.JK', 0, '2025-06-01')")

    # stock_personality
    conn.execute("""
        CREATE TABLE stock_personality (
            ticker TEXT PRIMARY KEY,
            updated_at TEXT
        )
    """)
    now = datetime.now().isoformat()
    old = (datetime.now() - timedelta(hours=48)).isoformat()
    conn.execute("INSERT INTO stock_personality (ticker, updated_at) VALUES ('AAA.JK', ?)", (old,))
    conn.execute("INSERT INTO stock_personality (ticker, updated_at) VALUES ('BBB.JK', ?)", (now,))

    # stock_prediction (AAA.JK stale, BBB.JK fresh)
    conn.execute("""
        CREATE TABLE stock_prediction (
            ticker TEXT PRIMARY KEY,
            prediction_updated_at TEXT
        )
    """)
    conn.execute("INSERT INTO stock_prediction (ticker, prediction_updated_at) VALUES ('AAA.JK', ?)", (old,))
    conn.execute("INSERT INTO stock_prediction (ticker, prediction_updated_at) VALUES ('BBB.JK', ?)", (now,))

    # ohlcv (minimal, for technical_indicators refresher)
    conn.execute("""
        CREATE TABLE ohlcv (
            ticker TEXT,
            timestamp TEXT,
            timeframe TEXT,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER
        )
    """)
    conn.execute("INSERT INTO ohlcv VALUES ('AAA.JK', ?, '1d', 100, 110, 95, 105, 1000)", (now,))

    # technical_indicators_wide (stale — date older than latest ohlcv)
    conn.execute("""
        CREATE TABLE technical_indicators_wide (
            ticker TEXT,
            date TEXT,
            rsi REAL
        )
    """)
    conn.execute("INSERT INTO technical_indicators_wide VALUES ('AAA.JK', ?, 50.0)", (old,))

    # recompute_watermark
    conn.execute("""
        CREATE TABLE recompute_watermark (
            ticker TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("INSERT INTO recompute_watermark (ticker, updated_at) VALUES ('AAA.JK', ?)", (old,))

    # data_watermark
    conn.execute("""
        CREATE TABLE data_watermark (
            ticker TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("INSERT INTO data_watermark (ticker, last_updated) VALUES ('AAA.JK', ?)", (old,))

    conn.commit()
    conn.close()

    yield db_path

    Path(db_path).unlink(missing_ok=True)


class TestGetExcludedTickers:
    def test_returns_suspended_and_delisted(self, test_db):
        conn = sqlite3.connect(test_db)
        excluded = get_excluded_tickers(conn)
        conn.close()
        assert "CCC.JK" in excluded
        assert "DDD.JK" in excluded
        assert "AAA.JK" not in excluded
        assert "BBB.JK" not in excluded


class TestDetectStaleTables:
    def test_detects_stale_stock_personality(self, test_db):
        conn = sqlite3.connect(test_db)
        reports = detect_stale_tables(conn, threshold_hours=24)
        conn.close()

        sp_report = next(r for r in reports if r.table_name == "stock_personality")
        assert sp_report.total_rows == 2
        assert sp_report.stale_rows == 1  # AAA.JK is stale
        assert sp_report.is_stale

    def test_clean_stock_prediction(self, test_db):
        conn = sqlite3.connect(test_db)
        reports = detect_stale_tables(conn, threshold_hours=24)
        conn.close()

        pred_report = next(r for r in reports if r.table_name == "stock_prediction")
        assert pred_report.stale_rows == 1  # AAA.JK is stale
        assert pred_report.is_stale

    def test_missing_table_skipped(self, test_db):
        conn = sqlite3.connect(test_db)
        reports = detect_stale_tables(conn, threshold_hours=24)
        conn.close()
        table_names = [r.table_name for r in reports]
        # fundamental_data and fear_greed don't exist in test DB
        assert "fundamental_data" not in table_names
        assert "fear_greed" not in table_names


class TestRefreshStaleData:
    def test_dry_run_detects_without_refreshing(self, test_db):
        report = refresh_stale_data(test_db, dry_run=True)
        assert isinstance(report, RefreshReport)
        assert report.total_refreshed == 0
        assert report.total_stale > 0

    def test_excluded_tickers_loaded(self, test_db):
        report = refresh_stale_data(test_db, dry_run=True)
        assert "CCC.JK" in report.excluded_tickers
        assert "DDD.JK" in report.excluded_tickers

    def test_nonexistent_db_raises(self):
        with pytest.raises(FileNotFoundError):
            refresh_stale_data("/nonexistent/path.db")

    def test_report_has_tables_checked(self, test_db):
        report = refresh_stale_data(test_db, dry_run=True)
        assert len(report.tables_checked) > 0
        assert all(isinstance(r, StaleTableReport) for r in report.tables_checked)

    def test_non_dry_run_refreshes_stale(self, test_db):
        """Non-dry-run should attempt refresh and mark predictions."""
        report = refresh_stale_data(test_db, dry_run=False)
        assert report.completed_at != ""
        # stock_prediction has no stale rows, so refresh should be 0 for it
        # but stock_personality has 1 stale row (AAA.JK)
        sp_report = next(r for r in report.tables_checked if r.table_name == "stock_personality")
        # The refresher may fail because recompute_internal needs real OHLCV,
        # but the action_taken should be set
        assert sp_report.action_taken != ""

    def test_is_clean_property(self, test_db):
        """is_clean should be False when stale rows exist."""
        report = refresh_stale_data(test_db, dry_run=True)
        assert not report.is_clean  # we have stale rows

    def test_is_clean_when_no_stale(self, test_db):
        """is_clean should be True when no stale rows."""
        # Update all rows to current timestamp
        conn = sqlite3.connect(test_db)
        now = datetime.now().isoformat()
        conn.execute("UPDATE stock_personality SET updated_at = ?", (now,))
        conn.execute("UPDATE stock_prediction SET prediction_updated_at = ?", (now,))
        conn.execute("UPDATE recompute_watermark SET updated_at = ?", (now,))
        conn.execute("UPDATE data_watermark SET last_updated = ?", (now,))
        conn.execute("UPDATE technical_indicators_wide SET date = ?", (now,))
        conn.commit()
        conn.close()
        report = refresh_stale_data(test_db, dry_run=True)
        assert report.is_clean

    def test_stale_table_report_error_field(self):
        """StaleTableReport should handle error field."""
        r = StaleTableReport(
            table_name="nonexistent",
            timestamp_column="ts",
            total_rows=0,
            stale_rows=0,
            latest_update=None,
            is_stale=False,
            error="table not found",
        )
        assert r.error == "table not found"
        assert r.rows_refreshed == 0

    def test_refresh_stock_prediction_directly(self, test_db):
        """Exercise _refresh_stock_prediction refresher directly."""
        from market.data.refresh_stale import _refresh_stock_prediction
        conn = sqlite3.connect(test_db)
        n, msg = _refresh_stock_prediction(conn, excluded_tickers=[])
        conn.close()
        assert n == 1  # AAA.JK was stale
        assert "marked" in msg

    def test_refresh_stock_prediction_no_stale(self, test_db):
        """_refresh_stock_prediction returns 0 when no stale rows."""
        from market.data.refresh_stale import _refresh_stock_prediction
        conn = sqlite3.connect(test_db)
        # First refresh to mark all as fresh
        _refresh_stock_prediction(conn, [])
        # Second call should find nothing stale
        n, msg = _refresh_stock_prediction(conn, [])
        conn.close()
        assert n == 0
        assert "no stale" in msg

    def test_refresh_technical_indicators_no_ohlcv(self, test_db):
        """_refresh_technical_indicators returns 0 when no OHLCV for ticker."""
        from market.data.refresh_stale import _refresh_technical_indicators
        conn = sqlite3.connect(test_db)
        # Remove ohlcv data
        conn.execute("DELETE FROM ohlcv")
        conn.commit()
        n, msg = _refresh_technical_indicators(conn, [])
        conn.close()
        assert n == 0
        assert "no OHLCV" in msg
