"""Tests for HolidayEffectAnalyzer — holiday effect analysis + features."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from market.analysis.holiday_effect import (
    HolidayEffectAnalyzer,
    HolidayEffectResult,
    SpilloverResult,
    INDEX_TICKERS,
)


@pytest.fixture
def mock_engine():
    """Mock SQLAlchemy engine for DB-free testing."""
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = MagicMock()
    return engine


@pytest.fixture
def sample_holidays():
    """Sample holiday data for testing."""
    return [
        (date(2026, 1, 1), "New Year's Day"),
        (date(2026, 2, 17), "Lunar New Year"),
        (date(2026, 3, 19), "Day of Silence"),
        (date(2026, 8, 17), "Independence Day"),
        (date(2026, 12, 25), "Christmas Day"),
    ]


@pytest.fixture
def sample_price_data():
    """Sample daily price data for testing (100 days)."""
    dates = pd.bdate_range(date(2026, 1, 1), date(2026, 5, 31))
    n = len(dates)
    closes = np.cumprod(1 + np.random.RandomState(42).normal(0.001, 0.02, n))
    adj_closes = closes * 1.0  # no adjustment
    volumes = np.random.RandomState(42).randint(1000000, 5000000, n)
    df = pd.DataFrame({
        "date": dates.date,
        "close": closes,
        "adjusted_close": adj_closes,
        "volume": volumes,
    })
    return df


class TestHolidayEffectAnalyzerInit:
    """Test analyzer initialization."""

    def test_default_lookback(self):
        with patch("market.analysis.holiday_effect.get_engine"):
            analyzer = HolidayEffectAnalyzer()
            assert analyzer.lookback_years == 10

    def test_custom_lookback(self):
        with patch("market.analysis.holiday_effect.get_engine"):
            analyzer = HolidayEffectAnalyzer(lookback_years=5)
            assert analyzer.lookback_years == 5


class TestComputeReturns:
    """Test _compute_returns method."""

    def test_empty_df(self, mock_engine):
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()
            df = pd.DataFrame(columns=["date", "close", "adjusted_close", "volume"])
            returns = analyzer._compute_returns(df)
            assert returns.empty

    def test_single_row(self, mock_engine):
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()
            df = pd.DataFrame({
                "date": [date(2026, 1, 1)],
                "close": [100.0],
                "adjusted_close": [100.0],
                "volume": [1000],
            })
            returns = analyzer._compute_returns(df)
            assert returns.empty

    def test_normal_returns(self, mock_engine):
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()
            df = pd.DataFrame({
                "date": [date(2026, 1, 1), date(2026, 1, 2)],
                "close": [100.0, 101.0],
                "adjusted_close": [100.0, 101.0],
                "volume": [1000, 2000],
            })
            returns = analyzer._compute_returns(df)
            assert len(returns) == 1
            assert abs(returns.iloc[0] - 1.0) < 0.01  # 1% return


class TestIndexTickers:
    """Test INDEX_TICKERS mapping."""

    def test_idx_present(self):
        assert "XIDX" in INDEX_TICKERS
        assert INDEX_TICKERS["XIDX"] == "^JKSE"

    def test_nyse_present(self):
        assert "XNYS" in INDEX_TICKERS
        assert INDEX_TICKERS["XNYS"] == "^GSPC"

    def test_all_21_exchanges(self):
        assert len(INDEX_TICKERS) >= 21


class TestHolidayEffectResult:
    """Test HolidayEffectResult dataclass."""

    def test_creation(self):
        result = HolidayEffectResult(
            mic_code="XIDX",
            holiday_name="Christmas Day",
            pre_holiday_avg_return=0.3,
            post_holiday_avg_return=-0.1,
            pre_holiday_win_rate=65.0,
            post_holiday_win_rate=40.0,
            n_occurrences=10,
            pre_holiday_std=0.5,
            post_holiday_std=0.8,
            is_significant=True,
        )
        assert result.mic_code == "XIDX"
        assert result.holiday_name == "Christmas Day"
        assert result.pre_holiday_avg_return == 0.3
        assert result.is_significant is True


class TestSpilloverResult:
    """Test SpilloverResult dataclass."""

    def test_creation(self):
        result = SpilloverResult(
            source_mic="XNYS",
            source_holiday_name="Thanksgiving",
            idx_next_day_avg_return=0.2,
            idx_next_day_win_rate=55.0,
            n_occurrences=8,
            is_significant=False,
        )
        assert result.source_mic == "XNYS"
        assert result.idx_next_day_avg_return == 0.2
        assert result.is_significant is False


class TestGetHolidayFeatures:
    """Test get_holiday_features method."""

    def test_normal_day_no_holiday(self, mock_engine):
        """Test features on a normal day with no nearby holidays."""
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()

            # Mock all DB queries to return empty
            conn = mock_engine.connect.return_value.__enter__.return_value
            conn.execute.return_value.first.return_value = None
            conn.execute.return_value.fetchall.return_value = []

            features = analyzer.get_holiday_features("XIDX", date(2026, 7, 15))

            assert features["is_holiday_today"] is False
            assert features["is_pre_holiday"] is False
            assert features["is_post_holiday"] is False
            assert features["pre_holiday_expected_return"] == 0.0

    def test_holiday_today(self, mock_engine):
        """Test features when today is a holiday."""
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()

            conn = mock_engine.connect.return_value.__enter__.return_value

            # Mock: today is holiday
            def execute_side_effect(query, params=None):
                mock_result = MagicMock()
                if "holiday_date = :d" in str(query) and params and params.get("d") == date(2026, 8, 17):
                    mock_result.first.return_value = ("Independence Day",)
                else:
                    mock_result.first.return_value = None
                return mock_result

            conn.execute.side_effect = execute_side_effect

            features = analyzer.get_holiday_features("XIDX", date(2026, 8, 17))

            assert features["is_holiday_today"] is True
            assert "Independence" in features["next_holiday_name"]


class TestAnalyzeHolidayEffect:
    """Test analyze_holiday_effect method with mocked data."""

    def test_no_holidays(self, mock_engine):
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()

            conn = mock_engine.connect.return_value.__enter__.return_value
            conn.execute.return_value.fetchall.return_value = []

            results = analyzer.analyze_holiday_effect("XIDX", "^JKSE")
            assert results == []

    def test_insufficient_price_data(self, mock_engine):
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()

            conn = mock_engine.connect.return_value.__enter__.return_value

            # Mock: very little price data
            price_result = MagicMock()
            price_result.fetchall.return_value = [
                (date(2026, 1, 1), 100.0, 100.0, 1000),
                (date(2026, 1, 2), 101.0, 101.0, 2000),
            ]

            # Mock: some holidays
            holiday_result = MagicMock()
            holiday_result.fetchall.return_value = [
                (date(2026, 1, 1), "New Year"),
            ]

            def execute_side_effect(query, params=None):
                if "stock_prices" in str(query):
                    return price_result
                elif "exchange_holidays" in str(query):
                    return holiday_result
                return MagicMock()

            conn.execute.side_effect = execute_side_effect

            results = analyzer.analyze_holiday_effect("XIDX", "^JKSE")
            # With only 2 rows of price data, should return empty
            assert results == []


class TestSpilloverAnalysis:
    """Test analyze_spillover_to_idx method."""

    def test_no_idx_data(self, mock_engine):
        with patch("market.analysis.holiday_effect.get_engine", return_value=mock_engine):
            analyzer = HolidayEffectAnalyzer()

            conn = mock_engine.connect.return_value.__enter__.return_value
            conn.execute.return_value.fetchall.return_value = []

            results = analyzer.analyze_spillover_to_idx(["XNYS"])
            assert results == []


class TestHolidaySignalIntegration:
    """Test holiday_signal in MarketContext."""

    def test_holiday_signal_no_data(self):
        from market.analysis.market_context import MarketContext

        ctx = MarketContext()
        signal = ctx.holiday_signal()
        assert signal == 0.0

    def test_holiday_signal_pre_holiday(self):
        from market.analysis.market_context import MarketContext

        ctx = MarketContext(
            is_pre_holiday=True,
            pre_holiday_expected_return=0.3,
        )
        signal = ctx.holiday_signal()
        assert signal > 0  # positive pre-holiday effect

    def test_holiday_signal_post_holiday_negative(self):
        from market.analysis.market_context import MarketContext

        ctx = MarketContext(
            is_post_holiday=True,
            post_holiday_expected_return=-0.2,
        )
        signal = ctx.holiday_signal()
        assert signal < 0  # negative post-holiday effect

    def test_holiday_signal_clamped(self):
        from market.analysis.market_context import MarketContext

        ctx = MarketContext(
            is_pre_holiday=True,
            pre_holiday_expected_return=10.0,  # extreme value
        )
        signal = ctx.holiday_signal()
        assert -1.0 <= signal <= 1.0

    def test_holiday_signal_in_composite(self):
        """Test that holiday_signal is included in composite_signal."""
        from market.analysis.market_context import MarketContext

        ctx = MarketContext(
            is_pre_holiday=True,
            pre_holiday_expected_return=0.5,
            sector="Basic Materials",
        )
        composite = ctx.composite_signal()
        # Should be a valid float
        assert isinstance(composite, float)
        assert -1.0 <= composite <= 1.0
