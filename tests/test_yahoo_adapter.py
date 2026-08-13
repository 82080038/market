"""Tests for YahooFinanceAdapter — mocked yfinance calls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from market.data.contracts import NormalizedOHLCV
from market.data.yahoo_adapter import YahooFinanceAdapter


def _make_ohlcv_df(ticker: str = "BBCA.JK", rows: int = 5) -> pd.DataFrame:
    """Create a mock yfinance download DataFrame."""
    base = datetime(2024, 1, 2, tzinfo=UTC)
    dates = [base + timedelta(days=i) for i in range(rows)]
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(rows)],
            "High": [110.0 + i for i in range(rows)],
            "Low": [90.0 + i for i in range(rows)],
            "Close": [105.0 + i for i in range(rows)],
            "Adj Close": [105.0 + i for i in range(rows)],
            "Volume": [10000 * (i + 1) for i in range(rows)],
        },
        index=pd.DatetimeIndex(dates, name="Date"),
    )


@pytest.fixture()
def adapter():
    """Create adapter with fast rate limit."""
    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        return YahooFinanceAdapter()


# ── fetch_ohlcv ─────────────────────────────────────────────────────────


@patch("market.data.yahoo_adapter.yf.download")
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_success(mock_open, mock_download, adapter):
    mock_download.return_value = _make_ohlcv_df("BBCA.JK", rows=3)
    records = adapter.fetch_ohlcv("BBCA.JK", period="5d", market_mic="XIDX", currency="IDR")

    assert len(records) == 3
    assert all(isinstance(r, NormalizedOHLCV) for r in records)
    assert records[0].ticker == "BBCA.JK"
    assert records[0].market_mic == "XIDX"
    assert records[0].currency == "IDR"
    assert records[0].source == "yahoo_finance"
    assert records[0].open == Decimal("100")
    assert records[0].close == Decimal("105")


@patch("market.data.yahoo_adapter.yf.download")
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_empty_df(mock_open, mock_download, adapter):
    mock_download.return_value = pd.DataFrame()
    records = adapter.fetch_ohlcv("EMPTY.JK", period="5d")
    assert records == []


@patch("market.data.yahoo_adapter.yf.download")
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_none_df(mock_open, mock_download, adapter):
    mock_download.return_value = None
    records = adapter.fetch_ohlcv("NONE.JK", period="5d")
    assert records == []


@patch("market.data.yahoo_adapter.yf.download", side_effect=Exception("Network error"))
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_network_error(mock_open, mock_download, adapter):
    records = adapter.fetch_ohlcv("FAIL.JK", period="5d")
    assert records == []


@patch("market.data.timestamp_validation.is_market_open", return_value=True)
def test_fetch_ohlcv_market_open_skips(mock_open, adapter):
    records = adapter.fetch_ohlcv("BBCA.JK", period="5d", interval="1d")
    assert records == []


@patch("market.data.yahoo_adapter.yf.download")
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_multiindex_columns(mock_open, mock_download, adapter):
    df = _make_ohlcv_df("BBCA.JK", rows=2)
    df.columns = pd.MultiIndex.from_tuples(
        [(c, "BBCA.JK") for c in df.columns], names=["Field", "Ticker"]
    )
    mock_download.return_value = df

    records = adapter.fetch_ohlcv("BBCA.JK", period="5d")
    assert len(records) == 2
    assert records[0].open == Decimal("100")


@patch("market.data.yahoo_adapter.yf.download")
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_skips_nan_rows(mock_open, mock_download, adapter):
    df = _make_ohlcv_df("BBCA.JK", rows=3)
    df.loc[df.index[1], "Open"] = float("nan")
    mock_download.return_value = df

    records = adapter.fetch_ohlcv("BBCA.JK", period="5d")
    assert len(records) == 2  # row 1 skipped


@patch("market.data.yahoo_adapter.yf.download")
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_volume_nan_defaults_zero(mock_open, mock_download, adapter):
    df = _make_ohlcv_df("BBCA.JK", rows=1)
    df.loc[df.index[0], "Volume"] = float("nan")
    mock_download.return_value = df

    records = adapter.fetch_ohlcv("BBCA.JK", period="5d")
    assert len(records) == 1
    assert records[0].volume == 0


@patch("market.data.yahoo_adapter.yf.download")
@patch("market.data.timestamp_validation.is_market_open", return_value=False)
def test_fetch_ohlcv_timestamp_timezone(mock_open, mock_download, adapter):
    df = _make_ohlcv_df("BBCA.JK", rows=1)
    mock_download.return_value = df

    records = adapter.fetch_ohlcv("BBCA.JK", period="5d")
    assert records[0].timestamp.tzinfo is not None


# ── fetch_dividends ─────────────────────────────────────────────────────


@patch("market.data.yahoo_adapter.yf.Ticker")
def test_fetch_dividends_success(mock_ticker_cls):
    div_series = pd.Series(
        [500.0, 300.0],
        index=pd.DatetimeIndex(
            [datetime(2024, 6, 1), datetime(2024, 12, 1)], name="Date"
        ),
    )
    mock_ticker = MagicMock()
    mock_ticker.dividends = div_series
    mock_ticker_cls.return_value = mock_ticker

    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        adapter = YahooFinanceAdapter()

    records = adapter.fetch_dividends("BBCA.JK")
    assert len(records) == 2
    assert records[0].action_type == "dividend"
    assert records[0].value == 500.0
    assert records[0].ticker == "BBCA.JK"


@patch("market.data.yahoo_adapter.yf.Ticker")
def test_fetch_dividends_empty(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.dividends = pd.Series([], dtype=float)
    mock_ticker_cls.return_value = mock_ticker

    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        adapter = YahooFinanceAdapter()

    records = adapter.fetch_dividends("NODIV.JK")
    assert records == []


@patch("market.data.yahoo_adapter.yf.Ticker", side_effect=Exception("API error"))
def test_fetch_dividends_error(mock_ticker_cls):
    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        adapter = YahooFinanceAdapter()

    records = adapter.fetch_dividends("FAIL.JK")
    assert records == []


# ── fetch_splits ────────────────────────────────────────────────────────


@patch("market.data.yahoo_adapter.yf.Ticker")
def test_fetch_splits_success(mock_ticker_cls):
    split_series = pd.Series(
        [2.0],
        index=pd.DatetimeIndex([datetime(2024, 3, 1)], name="Date"),
    )
    mock_ticker = MagicMock()
    mock_ticker.splits = split_series
    mock_ticker_cls.return_value = mock_ticker

    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        adapter = YahooFinanceAdapter()

    records = adapter.fetch_splits("SPLIT.JK")
    assert len(records) == 1
    assert records[0].action_type == "stock_split"
    assert records[0].value == 2.0


@patch("market.data.yahoo_adapter.yf.Ticker")
def test_fetch_splits_empty(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.splits = pd.Series([], dtype=float)
    mock_ticker_cls.return_value = mock_ticker

    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        adapter = YahooFinanceAdapter()

    records = adapter.fetch_splits("NOSPLIT.JK")
    assert records == []


# ── fetch_info ──────────────────────────────────────────────────────────


@patch("market.data.yahoo_adapter.yf.Ticker")
def test_fetch_info_success(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "BBCA", "sector": "Financial Services"}
    mock_ticker_cls.return_value = mock_ticker

    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        adapter = YahooFinanceAdapter()

    info = adapter.fetch_info("BBCA.JK")
    assert info["shortName"] == "BBCA"
    assert info["sector"] == "Financial Services"


@patch("market.data.yahoo_adapter.yf.Ticker", side_effect=Exception("API error"))
def test_fetch_info_error(mock_ticker_cls):
    with patch("market.data.yahoo_adapter.settings") as mock_settings:
        mock_settings.yfinance_rate_limit_per_second = 100.0
        adapter = YahooFinanceAdapter()

    info = adapter.fetch_info("FAIL.JK")
    assert info == {}
