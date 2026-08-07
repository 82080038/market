"""Tests for parquet migration with mocked data."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from market.data.migrate_parquet import (
    _d,
    _f,
    _s,
    migrate_corporate_actions,
    migrate_dividends,
    migrate_fundamental_data,
    migrate_macro_data,
    migrate_market_calendar,
    migrate_ohlcv,
    migrate_stock_personality,
    run_all_migrations,
)


def test_f_returns_default_for_nan():
    row = pd.Series({"val": float("nan")})
    assert _f(row, "val", 0.0) == 0.0


def test_f_returns_value_for_valid():
    row = pd.Series({"val": 42.5})
    assert _f(row, "val") == 42.5


def test_f_returns_default_zero():
    row = pd.Series({"val": float("nan")})
    assert _f(row, "val", 0.0) == 0.0


def test_s_returns_default_for_nan():
    row = pd.Series({"val": float("nan")})
    assert _s(row, "val", "") == ""


def test_s_returns_value_for_valid():
    row = pd.Series({"val": "hello"})
    assert _s(row, "val") == "hello"


def test_d_returns_date_for_valid():
    row = pd.Series({"val": "2024-01-15"})
    result = _d(row, "val")
    assert result == date(2024, 1, 15)


def test_d_returns_none_for_nan():
    row = pd.Series({"val": float("nan")})
    assert _d(row, "val") is None


def test_migrate_ohlcv_file_not_found(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_ohlcv(session)
    assert count == 0


def test_migrate_ohlcv_dry_run(tmp_path):
    df = pd.DataFrame({
        "ticker": ["BBCA"],
        "timestamp": ["2024-01-01"],
        "open": [8000.0],
        "high": [8100.0],
        "low": [7900.0],
        "close": [8050.0],
        "volume": [1000000],
    })
    parquet_path = tmp_path / "ohlcv.parquet"
    df.to_parquet(parquet_path)
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_ohlcv(session, dry_run=True)
    assert count == 1


def test_migrate_corporate_actions_file_not_found(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_corporate_actions(session)
    assert count == 0


def test_migrate_dividends_file_not_found(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_dividends(session)
    assert count == 0


def test_migrate_macro_data_file_not_found(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_macro_data(session)
    assert count == 0


def test_migrate_market_calendar_file_not_found(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_market_calendar(session)
    assert count == 0


def test_migrate_fundamental_data_file_not_found(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_fundamental_data(session)
    assert count == 0


def test_migrate_stock_personality_file_not_found(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        count = migrate_stock_personality(session)
    assert count == 0


def test_run_all_migrations_all_missing(tmp_path):
    session = MagicMock()
    with patch("market.data.migrate_parquet.ARCHIVE_TABLES", tmp_path):
        results = run_all_migrations(session, dry_run=True)
    assert all(v == 0 for v in results.values())
    assert len(results) == 19
