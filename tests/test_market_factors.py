"""Tests for market_factors module: price adjustment, volume dynamics, time-zone grid."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.market_factors import (
    MARKET_SESSIONS,
    TimeBucketGrid,
    apply_adjusted_prices,
    compute_global_sentiment_signal,
    compute_obv,
    compute_volume_features,
    compute_volume_roc,
    compute_vwap,
    ensure_adjusted,
    get_market_overlap_status,
)

# ── 1. Price Adjustment Tests ──────────────────────────────────────────────


class TestPriceAdjustment:
    """Tests for corporate action price adjustment."""

    def test_adjusted_close_ratio_applied(self):
        """Test that adjusted_close ratio is applied to OHLC."""
        df = pd.DataFrame(
            {
                "open": [100.0, 200.0, 300.0],
                "high": [110.0, 210.0, 310.0],
                "low": [90.0, 190.0, 290.0],
                "close": [100.0, 200.0, 300.0],
                "adjusted_close": [50.0, 100.0, 300.0],
                "volume": [1000, 2000, 3000],
            },
            index=pd.date_range("2024-01-01", periods=3),
        )
        result = apply_adjusted_prices(df)
        # Row 0: ratio = 50/100 = 0.5
        assert result["close"].iloc[0] == pytest.approx(50.0)
        assert result["open"].iloc[0] == pytest.approx(50.0)
        # Row 1: ratio = 100/200 = 0.5
        assert result["close"].iloc[1] == pytest.approx(100.0)
        # Row 2: ratio = 300/300 = 1.0
        assert result["close"].iloc[2] == pytest.approx(300.0)
        # Volume: inverse ratio
        assert result["volume"].iloc[0] == pytest.approx(2000.0)

    def test_no_adjusted_close_returns_copy(self):
        """Test that missing adjusted_close returns original data."""
        df = pd.DataFrame(
            {"open": [100.0], "high": [110.0], "low": [90.0],
             "close": [100.0], "volume": [1000]},
            index=pd.date_range("2024-01-01", periods=1),
        )
        result = ensure_adjusted(df)
        assert result["close"].iloc[0] == 100.0

    def test_none_adjusted_close_uses_ratio_1(self):
        """Test that None adjusted_close uses ratio 1.0."""
        df = pd.DataFrame(
            {
                "open": [100.0, 200.0],
                "high": [110.0, 210.0],
                "low": [90.0, 190.0],
                "close": [100.0, 200.0],
                "adjusted_close": [None, 200.0],
                "volume": [1000, 2000],
            },
            index=pd.date_range("2024-01-01", periods=2),
        )
        result = apply_adjusted_prices(df)
        # Row 0: adjusted_close is None → ratio = 1.0
        assert result["close"].iloc[0] == pytest.approx(100.0)
        # Row 1: ratio = 200/200 = 1.0
        assert result["close"].iloc[1] == pytest.approx(200.0)

    def test_empty_dataframe(self):
        """Test that empty DataFrame returns empty."""
        df = pd.DataFrame()
        result = ensure_adjusted(df)
        assert result.empty


# ── 2. Volume Dynamics Tests ───────────────────────────────────────────────


class TestVolumeDynamics:
    """Tests for volume-based feature computation."""

    @pytest.fixture
    def sample_ohlcv(self):
        """Sample OHLCV data for testing."""
        n = 50
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        np.random.seed(42)
        close = 100.0 + np.cumsum(np.random.randn(n) * 2)
        volume = np.random.randint(1000, 10000, n).astype(float)
        return pd.DataFrame(
            {
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )

    def test_vwap(self, sample_ohlcv):
        """Test VWAP computation."""
        vwap = compute_vwap(sample_ohlcv, window=20)
        assert len(vwap) == len(sample_ohlcv)
        assert vwap.iloc[-1] > 0
        # VWAP should be within price range
        close = sample_ohlcv["close"]
        assert vwap.iloc[-1] >= close.min()
        assert vwap.iloc[-1] <= close.max()

    def test_volume_roc(self, sample_ohlcv):
        """Test Volume ROC computation."""
        roc = compute_volume_roc(sample_ohlcv, period=10)
        assert len(roc) == len(sample_ohlcv)
        # First 10 values should be NaN
        assert pd.isna(roc.iloc[0])
        # Later values should be finite
        assert np.isfinite(roc.iloc[-1])

    def test_obv(self, sample_ohlcv):
        """Test OBV computation."""
        obv = compute_obv(sample_ohlcv)
        assert len(obv) == len(sample_ohlcv)
        # OBV is cumulative, should be non-decreasing in magnitude
        assert obv.iloc[-1] != 0

    def test_compute_volume_features(self, sample_ohlcv):
        """Test all volume features at once."""
        result = compute_volume_features(sample_ohlcv)
        assert "vwap_20" in result.columns
        assert "vwap_ratio" in result.columns
        assert "vol_roc_10" in result.columns
        assert "obv" in result.columns
        assert "obv_slope" in result.columns
        assert "vol_price_trend" in result.columns

    def test_empty_volume_features(self):
        """Test volume features on empty DataFrame."""
        df = pd.DataFrame()
        vwap = compute_vwap(df)
        assert vwap.empty
        roc = compute_volume_roc(df)
        assert roc.empty


# ── 3. Time-Zone Bucket Grid Tests ─────────────────────────────────────────


class TestTimeZoneBucketGrid:
    """Tests for time-zone bucket grid."""

    def test_bucket_assignment(self):
        """Test correct bucket assignment for different UTC hours."""
        grid = TimeBucketGrid()
        assert grid.get_bucket(pd.Timestamp("2025-06-16 01:00")) == "B0_overnight_asia"
        assert grid.get_bucket(pd.Timestamp("2025-06-16 03:00")) == "B1_idx_session"
        assert grid.get_bucket(pd.Timestamp("2025-06-16 10:00")) == "B2_europe_transition"
        assert grid.get_bucket(pd.Timestamp("2025-06-16 16:00")) == "B3_wall_street"
        assert grid.get_bucket(pd.Timestamp("2025-06-16 22:00")) == "B4_post_wall_street"

    def test_market_sessions(self):
        """Test market session definitions."""
        assert MARKET_SESSIONS["XIDX"].open_hour_utc == 2.0
        assert MARKET_SESSIONS["XNYS"].open_hour_utc == 14.5
        assert MARKET_SESSIONS["XTSE"].open_hour_utc == 0.0

    def test_market_open_check(self):
        """Test is_open_at for different markets."""
        # IDX open at 03:00 UTC (09:00 WIB)
        ts = pd.Timestamp("2025-06-16 03:00")
        assert MARKET_SESSIONS["XIDX"].is_open_at(ts)
        # NYSE closed at 03:00 UTC
        assert not MARKET_SESSIONS["XNYS"].is_open_at(ts)
        # NYSE open at 16:00 UTC (during DST: 10:00 EDT)
        ts2 = pd.Timestamp("2025-06-16 16:00")
        assert MARKET_SESSIONS["XNYS"].is_open_at(ts2)

    def test_global_sentiment_window(self):
        """Test sentiment window computation."""
        grid = TimeBucketGrid()
        idx_date = pd.Timestamp("2025-06-16")
        window = grid.get_global_sentiment_window(idx_date)
        assert "wall_street_close_prev" in window
        assert "tokyo_close" in window
        assert "hong_kong_close" in window
        assert "idx_open" in window
        assert "idx_close" in window
        # Wall Street close should be previous day at 21:00 UTC
        assert window["wall_street_close_prev"].day == 15
        assert window["wall_street_close_prev"].hour == 21

    def test_global_sentiment_signal(self):
        """Test global sentiment signal computation."""
        dates = pd.date_range("2025-01-01", periods=100, freq="B")
        global_data = {
            "^GSPC": pd.DataFrame(
                {"close": np.linspace(4000, 4200, 100)}, index=dates
            ),
            "^N225": pd.DataFrame(
                {"close": np.linspace(35000, 36000, 100)}, index=dates
            ),
            "^HSI": pd.DataFrame(
                {"close": np.linspace(18000, 17500, 100)}, index=dates
            ),
        }
        signals = compute_global_sentiment_signal(
            global_data, pd.Timestamp("2025-06-16"), lookback=5,
        )
        assert "combined_global" in signals
        assert -1.0 <= signals["combined_global"] <= 1.0

    def test_market_overlap_status(self):
        """Test market overlap status at a given timestamp."""
        ts = pd.Timestamp("2025-06-16 03:00")
        status = get_market_overlap_status(ts)
        assert "XIDX" in status
        assert status["XIDX"] is True
        assert status["XNYS"] is False

    def test_empty_global_data(self):
        """Test global sentiment with no data."""
        signals = compute_global_sentiment_signal({}, pd.Timestamp("2025-06-16"))
        assert "combined_global" not in signals
