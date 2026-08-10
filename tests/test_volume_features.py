"""Tests for volume_features: VWAP, Volume Profile, OFI, OBV divergence, VW momentum, foreign flow.

All tests use synthetic OHLCV data and verify the non-look-ahead property,
edge-case handling, and numerical correctness of each component.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.volume_features import (
    DivergenceResult,
    ForeignFlowResult,
    OFIResult,
    RetailAbsorptionResult,
    VolumeProfile,
    VWAPResult,
    calculate_retail_absorption,
    compute_foreign_flow_signal,
    compute_ofi_proxy,
    compute_volume_profile,
    compute_vw_momentum,
    compute_vwap,
    detect_obv_divergence,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def ohlcv_20bars() -> pd.DataFrame:
    """20-bar synthetic OHLCV with a deterministic uptrend and varied volume."""
    rng = np.random.default_rng(seed=42)
    n = 20
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    base = 100.0 + np.arange(n) * 0.5
    high = base + rng.uniform(0.1, 1.0, size=n)
    low = base - rng.uniform(0.1, 1.0, size=n)
    close = base + rng.uniform(-0.5, 0.5, size=n)
    volume = rng.integers(1000, 5000, size=n).astype(float)
    return pd.DataFrame(
        {"high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture()
def ohlcv_60bars() -> pd.DataFrame:
    """60-bar synthetic OHLCV used for volume profile / momentum tests."""
    rng = np.random.default_rng(seed=7)
    n = 60
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100.0 + rng.normal(0, 1.0, size=n).cumsum() * 0.1
    high = close + rng.uniform(0.1, 1.0, size=n)
    low = close - rng.uniform(0.1, 1.0, size=n)
    volume = rng.integers(1000, 5000, size=n).astype(float)
    return pd.DataFrame(
        {"high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


# ── 1. VWAP Calculation ─────────────────────────────────────────────────────


class TestVWAP:
    """Tests for compute_vwap."""

    def test_vwap_equals_volume_weighted_typical_price(self, ohlcv_20bars):
        """Rolling VWAP must equal the volume-weighted average of typical prices over the window."""
        window = 5
        df = ohlcv_20bars
        result = compute_vwap(
            df["high"], df["low"], df["close"], df["volume"], window=window
        )

        assert isinstance(result, VWAPResult)
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vp = typical * df["volume"]
        expected_vwap = (
            vp.rolling(window, min_periods=1).sum()
            / df["volume"].rolling(window, min_periods=1).sum().replace(0, np.nan)
        )

        pd.testing.assert_series_equal(result.vwap, expected_vwap)
        pd.testing.assert_series_equal(result.typical_price, typical)

    def test_vwap_window5_length_and_index(self, ohlcv_20bars):
        """VWAP series preserves index and length of input."""
        df = ohlcv_20bars
        result = compute_vwap(df["high"], df["low"], df["close"], df["volume"], window=5)
        assert len(result.vwap) == len(df)
        assert result.vwap.index.equals(df.index)

    def test_vwap_first_bar_equals_typical_price(self, ohlcv_20bars):
        """With min_periods=1, the first VWAP bar equals the first typical price."""
        df = ohlcv_20bars
        result = compute_vwap(df["high"], df["low"], df["close"], df["volume"], window=5)
        typical_0 = (df["high"].iloc[0] + df["low"].iloc[0] + df["close"].iloc[0]) / 3.0
        assert result.vwap.iloc[0] == pytest.approx(typical_0)


# ── 2. VWAP Deviation ───────────────────────────────────────────────────────


class TestVWAPDeviation:
    """Tests for the VWAP deviation signal (shifted by 1 to avoid look-ahead)."""

    def test_positive_deviation_when_close_above_prior_vwap(self):
        """When close[T] > vwap[T-1], deviation at T must be positive."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        # Constant price so vwap is stable, then jump close up.
        high = pd.Series([100.0] * n, index=dates)
        low = pd.Series([99.0] * n, index=dates)
        close = pd.Series([100.0] * n, index=dates)
        volume = pd.Series([1000.0] * n, index=dates)
        # Make the last close well above the stable vwap.
        close.iloc[-1] = 110.0

        result = compute_vwap(high, low, close, volume, window=5)
        vwap_prior = result.vwap.iloc[-2]
        assert close.iloc[-1] > vwap_prior
        assert result.deviation.iloc[-1] > 0

    def test_negative_deviation_when_close_below_prior_vwap(self):
        """When close[T] < vwap[T-1], deviation at T must be negative."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([100.0] * n, index=dates)
        low = pd.Series([99.0] * n, index=dates)
        close = pd.Series([100.0] * n, index=dates)
        volume = pd.Series([1000.0] * n, index=dates)
        close.iloc[-1] = 90.0

        result = compute_vwap(high, low, close, volume, window=5)
        vwap_prior = result.vwap.iloc[-2]
        assert close.iloc[-1] < vwap_prior
        assert result.deviation.iloc[-1] < 0

    def test_deviation_boundary_zero_when_close_equals_vwap(self):
        """When close[T] == vwap[T-1], deviation is ~0."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([100.0] * n, index=dates)
        low = pd.Series([98.0] * n, index=dates)
        close = pd.Series([99.0] * n, index=dates)  # typical = 99
        volume = pd.Series([1000.0] * n, index=dates)

        result = compute_vwap(high, low, close, volume, window=5)
        # vwap is stable at 99; close at last bar = 99 → deviation 0.
        assert result.deviation.iloc[-1] == pytest.approx(0.0, abs=1e-9)

    def test_deviation_first_bar_is_zero(self, ohlcv_20bars):
        """First deviation bar is zero (vwap shifted → NaN → filled with 0)."""
        df = ohlcv_20bars
        result = compute_vwap(df["high"], df["low"], df["close"], df["volume"], window=5)
        assert result.deviation.iloc[0] == 0.0


# ── 3. Volume Profile ───────────────────────────────────────────────────────


class TestVolumeProfile:
    """Tests for compute_volume_profile (POC, VAH, VAL)."""

    def test_poc_near_concentrated_price_level(self):
        """POC should be near the price level where most volume concentrates."""
        n = 60
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        # 50 bars at price 100 with huge volume, 10 bars at other prices with tiny volume.
        close = pd.Series(
            [100.0] * 50 + [95.0, 105.0, 90.0, 110.0, 85.0, 115.0, 92.0, 108.0, 88.0, 112.0],
            index=dates,
        )
        volume = pd.Series(
            [10000.0] * 50 + [100.0] * 10,
            index=dates,
        )

        series = compute_volume_profile(close, volume, bins=10, window=60)
        assert isinstance(series, pd.Series)
        # Series is shifted by 1; first element is NaN.
        assert pd.isna(series.iloc[0])

        # Take the last bar (profile computed from data up to T-1, which includes the
        # concentrated volume at 100).
        profile = series.iloc[-1]
        assert isinstance(profile, VolumeProfile)
        # POC must be near 100 (within one bin width).
        price_range = close.max() - close.min()  # 115 - 85 = 30
        bin_width = price_range / 10
        assert abs(profile.poc - 100.0) <= bin_width

    def test_volume_profile_returns_volume_profile_objects(self):
        """Non-NaN entries must be VolumeProfile instances."""
        n = 30
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        rng = np.random.default_rng(seed=1)
        close = pd.Series(100.0 + rng.normal(0, 1, n).cumsum() * 0.1, index=dates)
        volume = pd.Series(rng.integers(500, 2000, n).astype(float), index=dates)

        series = compute_volume_profile(close, volume, bins=10, window=20)
        # Skip the first (NaN due to shift); the rest should be VolumeProfile.
        non_nan = series.dropna()
        assert len(non_nan) > 0
        assert all(isinstance(v, VolumeProfile) for v in non_nan)

    def test_volume_profile_single_price_no_crash(self):
        """When all prices are identical, POC=VAH=VAL=that price (no crash)."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = pd.Series([100.0] * n, index=dates)
        volume = pd.Series([1000.0] * n, index=dates)

        series = compute_volume_profile(close, volume, bins=10, window=10)
        profile = series.dropna().iloc[-1]
        assert profile.poc == pytest.approx(100.0)
        assert profile.vah == pytest.approx(100.0)
        assert profile.val == pytest.approx(100.0)


# ── 4. Value Area ───────────────────────────────────────────────────────────


class TestValueArea:
    """Tests that VAH/VAL contain ~70% of volume."""

    def test_value_area_contains_70_percent_volume(self):
        """Sum of volume between VAL and VAH must be >= 70% of total volume."""
        n = 60
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        rng = np.random.default_rng(seed=99)
        # Spread volume across price levels so value area is non-trivial.
        close = pd.Series(
            np.concatenate([
                np.full(15, 90.0),
                np.full(15, 95.0),
                np.full(15, 100.0),
                np.full(15, 105.0),
            ]) + rng.normal(0, 0.2, n),
            index=dates,
        )
        volume = pd.Series(rng.integers(500, 3000, n).astype(float), index=dates)

        series = compute_volume_profile(close, volume, bins=10, window=60)
        profile = series.dropna().iloc[-1]
        assert isinstance(profile, VolumeProfile)

        total_vol = profile.volume_by_level.sum()
        assert total_vol > 0
        # The value area indices span [val_idx, vah_idx]; volume in that range >= 70%.
        val_idx = int(np.argmin(np.abs(profile.price_levels - profile.val)))
        vah_idx = int(np.argmin(np.abs(profile.price_levels - profile.vah)))
        lo, hi = min(val_idx, vah_idx), max(val_idx, vah_idx)
        va_vol = profile.volume_by_level[lo : hi + 1].sum()
        assert va_vol >= 0.7 * total_vol - 1e-6

    def test_vah_above_val(self):
        """VAH must be >= VAL."""
        n = 60
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        rng = np.random.default_rng(seed=3)
        close = pd.Series(100.0 + rng.normal(0, 2, n).cumsum() * 0.2, index=dates)
        volume = pd.Series(rng.integers(500, 3000, n).astype(float), index=dates)

        series = compute_volume_profile(close, volume, bins=10, window=60)
        profile = series.dropna().iloc[-1]
        assert profile.vah >= profile.val


# ── 5. OFI Proxy ────────────────────────────────────────────────────────────


class TestOFIProxy:
    """Tests for compute_ofi_proxy (buy/sell pressure estimate)."""

    def test_bullish_close_near_high(self):
        """Close near high → buy_volume > sell_volume and OFI > 0."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([110.0] * n, index=dates)
        low = pd.Series([90.0] * n, index=dates)
        close = pd.Series([109.0] * n, index=dates)  # near high
        volume = pd.Series([1000.0] * n, index=dates)

        result = compute_ofi_proxy(close, volume, high, low)
        assert isinstance(result, OFIResult)
        assert (result.buy_volume > result.sell_volume).all()
        assert (result.ofi > 0).all()

    def test_bearish_close_near_low(self):
        """Close near low → sell_volume > buy_volume and OFI < 0."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([110.0] * n, index=dates)
        low = pd.Series([90.0] * n, index=dates)
        close = pd.Series([91.0] * n, index=dates)  # near low
        volume = pd.Series([1000.0] * n, index=dates)

        result = compute_ofi_proxy(close, volume, high, low)
        assert (result.sell_volume > result.buy_volume).all()
        assert (result.ofi < 0).all()

    def test_ofi_range_bounded(self):
        """OFI must be in [-1, 1]."""
        n = 20
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        rng = np.random.default_rng(seed=5)
        high = pd.Series(100.0 + rng.uniform(0, 5, n), index=dates)
        low = pd.Series(100.0 - rng.uniform(0, 5, n), index=dates)
        close = pd.Series(100.0 + rng.uniform(-5, 5, n), index=dates)
        volume = pd.Series(rng.integers(100, 1000, n).astype(float), index=dates)

        result = compute_ofi_proxy(close, volume, high, low)
        assert result.ofi.between(-1.0, 1.0).all()

    def test_ofi_rolling_shifted_first_bar_zero(self):
        """ofi_5 and ofi_10 are shifted by 1 → first bar is 0."""
        n = 15
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([110.0] * n, index=dates)
        low = pd.Series([90.0] * n, index=dates)
        close = pd.Series([109.0] * n, index=dates)
        volume = pd.Series([1000.0] * n, index=dates)

        result = compute_ofi_proxy(close, volume, high, low)
        assert result.ofi_5.iloc[0] == 0.0
        assert result.ofi_10.iloc[0] == 0.0


# ── 6. OBV Divergence Detection ─────────────────────────────────────────────


class TestOBVDivergence:
    """Tests for detect_obv_divergence."""

    def test_bullish_divergence(self):
        """Price lower low + OBV higher low → bullish divergence."""
        window = 20
        # First half: low at 100 (index 1). Second half: lower low at 90 (index 11).
        close = pd.Series(
            [105, 100, 108, 102, 106, 101, 107, 103, 109, 104,
             95, 90, 98, 92, 96, 91, 97, 93, 99, 94],
            dtype=float,
        )
        # OBV increasing so obv at second-half low > obv at first-half low.
        obv = pd.Series(np.arange(1, 21, dtype=float))
        result = detect_obv_divergence(close, obv, window=window)
        assert isinstance(result, DivergenceResult)
        assert result.divergence_type == "bullish"
        assert 0.0 < result.strength <= 1.0
        assert result.price_low == pytest.approx(90.0)

    def test_bearish_divergence(self):
        """Price higher high + OBV lower high → bearish divergence."""
        window = 20
        close = pd.Series(
            [90, 95, 92, 97, 94, 99, 96, 100, 98, 103,
             105, 108, 106, 111, 109, 113, 110, 115, 112, 109],
            dtype=float,
        )
        # OBV decreasing so obv at second-half high < obv at first-half high.
        obv = pd.Series(np.arange(20, 0, -1, dtype=float))
        result = detect_obv_divergence(close, obv, window=window)
        assert result.divergence_type == "bearish"
        assert 0.0 < result.strength <= 1.0
        assert result.price_high == pytest.approx(115.0)

    def test_no_divergence_when_aligned(self):
        """Price and OBV both making higher highs → no divergence."""
        window = 20
        close = pd.Series(np.arange(100, 120, dtype=float))
        obv = pd.Series(np.arange(1, 21, dtype=float))  # both rising
        result = detect_obv_divergence(close, obv, window=window)
        assert result.divergence_type == "none"
        assert result.strength == 0.0

    def test_insufficient_data_returns_none(self):
        """Fewer bars than window → no divergence."""
        close = pd.Series([100.0, 101.0, 102.0])
        obv = pd.Series([1.0, 2.0, 3.0])
        result = detect_obv_divergence(close, obv, window=20)
        assert result.divergence_type == "none"
        assert result.strength == 0.0


# ── 7. Volume-Weighted Momentum ─────────────────────────────────────────────


class TestVWMomentum:
    """Tests for compute_vw_momentum."""

    def test_positive_momentum_on_upward_high_volume(self):
        """Strong upward move on high volume → positive VW momentum."""
        n = 30
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = pd.Series(100.0 + np.arange(n) * 0.5, index=dates)  # steady uptrend
        volume = pd.Series([2000.0] * n, index=dates)

        momentum = compute_vw_momentum(close, volume, period=10)
        assert isinstance(momentum, pd.Series)
        assert momentum.iloc[-1] > 0

    def test_negative_momentum_on_downward_high_volume(self):
        """Strong downward move on high volume → negative VW momentum."""
        n = 30
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = pd.Series(100.0 - np.arange(n) * 0.5, index=dates)  # steady downtrend
        volume = pd.Series([2000.0] * n, index=dates)

        momentum = compute_vw_momentum(close, volume, period=10)
        assert momentum.iloc[-1] < 0

    def test_momentum_high_volume_amplifies(self):
        """Higher volume on a move should produce larger |momentum| than low volume."""
        n = 30
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = pd.Series(100.0 + np.arange(n) * 0.5, index=dates)
        # Low volume first 20 bars, then high volume.
        vol_low = pd.Series([100.0] * 20 + [5000.0] * 10, index=dates)
        vol_const = pd.Series([1000.0] * n, index=dates)

        mom_low = compute_vw_momentum(close, vol_low, period=10)
        mom_const = compute_vw_momentum(close, vol_const, period=10)
        # The high-volume tail should amplify momentum magnitude.
        assert abs(mom_low.iloc[-1]) > abs(mom_const.iloc[-1])


# ── 8. Foreign Flow Signal ──────────────────────────────────────────────────


class TestForeignFlowSignal:
    """Tests for compute_foreign_flow_signal."""

    def test_bullish_on_5day_net_buy(self):
        """5-day positive cumulative net flow → bullish signal."""
        flow = pd.Series([10.0] * 5, index=pd.date_range("2024-01-01", periods=5))
        result = compute_foreign_flow_signal(flow, window=5)
        assert isinstance(result, ForeignFlowResult)
        assert result.cumulative_5d > 0
        assert result.signal == "bullish"

    def test_neutral_on_5day_net_sell(self):
        """5-day negative cumulative net flow (non-extreme) → neutral signal.

        The API defines only 'bullish', 'contrarian_buy', and 'neutral' — there is
        no explicit 'bearish' signal, so a plain net sell yields 'neutral'.
        """
        flow = pd.Series([-10.0] * 5, index=pd.date_range("2024-01-01", periods=5))
        result = compute_foreign_flow_signal(flow, window=5)
        assert result.cumulative_5d < 0
        assert result.signal == "neutral"

    def test_contrarian_buy_on_extreme_outflow(self):
        """Extreme outflow (z-score < -2) → contrarian_buy signal."""
        rng = np.random.default_rng(seed=123)
        # 60 bars of moderate flow with variation, then a huge negative outflow.
        base = rng.normal(50.0, 10.0, size=60)
        flow = pd.Series(
            np.concatenate([base, [-1000.0]]),
            index=pd.date_range("2024-01-01", periods=61, freq="D"),
        )
        result = compute_foreign_flow_signal(flow, window=5)
        assert result.z_score < -2.0
        assert result.signal == "contrarian_buy"

    def test_empty_series_returns_neutral(self):
        """Empty foreign flow series → neutral signal with zero values."""
        flow = pd.Series([], dtype=float)
        result = compute_foreign_flow_signal(flow, window=5)
        assert result.signal == "neutral"
        assert result.cumulative_5d == 0.0
        assert result.z_score == 0.0


# ── 9. No-Look-Ahead ────────────────────────────────────────────────────────


class TestNoLookAhead:
    """Verify features at time T use only data <= T (or <= T-1 via shift)."""

    def test_vwap_deviation_uses_prior_vwap(self):
        """deviation[T] = (close[T] - vwap[T-1]) / vwap[T-1], not vwap[T]."""
        n = 15
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series(100.0 + np.arange(n) * 0.1, index=dates)
        low = pd.Series(99.0 + np.arange(n) * 0.1, index=dates)
        close = pd.Series(99.5 + np.arange(n) * 0.1, index=dates)
        volume = pd.Series([1000.0] * n, index=dates)

        result = compute_vwap(high, low, close, volume, window=5)
        for t in range(1, n):
            vwap_prior = result.vwap.iloc[t - 1]
            if np.isfinite(vwap_prior) and vwap_prior != 0:
                expected = (close.iloc[t] - vwap_prior) / vwap_prior
                assert result.deviation.iloc[t] == pytest.approx(expected, rel=1e-9)

    def test_modifying_future_bar_does_not_change_past_features(self, ohlcv_60bars):
        """Changing bar k must not affect features at indices < k."""
        df = ohlcv_60bars
        result1 = compute_vwap(df["high"], df["low"], df["close"], df["volume"], window=5)

        # Modify bar at index 30 and recompute.
        df2 = df.copy()
        df2.iloc[30] = [999.0, 998.0, 998.5, 99999.0]
        result2 = compute_vwap(df2["high"], df2["low"], df2["close"], df2["volume"], window=5)

        # Bars before index 30 must be identical (no look-ahead).
        pd.testing.assert_series_equal(
            result1.vwap.iloc[:30], result2.vwap.iloc[:30]
        )
        pd.testing.assert_series_equal(
            result1.deviation.iloc[:30], result2.deviation.iloc[:30]
        )

    def test_volume_profile_shifted_by_one(self):
        """Volume profile at T uses data up to T-1 (series is shifted by 1)."""
        n = 30
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        rng = np.random.default_rng(seed=11)
        close = pd.Series(100.0 + rng.normal(0, 1, n).cumsum() * 0.1, index=dates)
        volume = pd.Series(rng.integers(500, 2000, n).astype(float), index=dates)

        series = compute_volume_profile(close, volume, bins=10, window=20)
        # First bar is NaN due to shift(1).
        assert pd.isna(series.iloc[0])

    def test_ofi_rolling_shifted(self):
        """ofi_5 at T uses OFI up to T-1 (shifted by 1)."""
        n = 20
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([110.0] * n, index=dates)
        low = pd.Series([90.0] * n, index=dates)
        close = pd.Series([109.0] * n, index=dates)
        volume = pd.Series([1000.0] * n, index=dates)

        result = compute_ofi_proxy(close, volume, high, low)
        # ofi_5 shifted → first bar 0.
        assert result.ofi_5.iloc[0] == 0.0
        # ofi_5 at T = mean(ofi[T-5:T]) (the 5 bars before T, due to shift).
        ofi_raw = result.ofi
        for t in range(1, n):
            start = max(0, t - 5)
            expected = ofi_raw.iloc[start:t].mean()
            assert result.ofi_5.iloc[t] == pytest.approx(expected, rel=1e-9)

    def test_vw_momentum_vol_avg_shifted(self):
        """VW momentum vol_avg is shifted by 1 so current bar's volume doesn't enter the average."""
        n = 25
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = pd.Series(100.0 + np.arange(n) * 0.2, index=dates)
        volume = pd.Series([1000.0] * n, index=dates)

        momentum = compute_vw_momentum(close, volume, period=10)
        # Modifying bar k must not change momentum at indices < k.
        vol2 = volume.copy()
        vol2.iloc[15] = 999999.0
        momentum2 = compute_vw_momentum(close, vol2, period=10)
        pd.testing.assert_series_equal(momentum.iloc[:15], momentum2.iloc[:15])


# ── 10. Edge Cases ──────────────────────────────────────────────────────────


class TestEdgeCases:
    """Empty / single-value / all-zero-volume must not raise or divide by zero."""

    def test_empty_series_vwap(self):
        """Empty inputs → empty outputs, no exception."""
        empty = pd.Series([], dtype=float)
        result = compute_vwap(empty, empty, empty, empty, window=5)
        assert len(result.vwap) == 0
        assert len(result.deviation) == 0
        assert len(result.typical_price) == 0

    def test_single_value_vwap(self):
        """Single bar → no crash, deviation filled to 0."""
        dates = pd.date_range("2024-01-01", periods=1)
        high = pd.Series([110.0], index=dates)
        low = pd.Series([90.0], index=dates)
        close = pd.Series([100.0], index=dates)
        volume = pd.Series([1000.0], index=dates)

        result = compute_vwap(high, low, close, volume, window=5)
        assert len(result.vwap) == 1
        assert np.isfinite(result.vwap.iloc[0])
        assert result.deviation.iloc[0] == 0.0  # shifted vwap is NaN → filled 0

    def test_all_zero_volume_vwap(self):
        """All-zero volume → no division-by-zero; vwap NaN, deviation 0."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([110.0] * n, index=dates)
        low = pd.Series([90.0] * n, index=dates)
        close = pd.Series([100.0] * n, index=dates)
        volume = pd.Series([0.0] * n, index=dates)

        result = compute_vwap(high, low, close, volume, window=5)
        # vwap should be NaN (0 volume replaced with NaN), no inf/exception.
        assert not np.any(np.isinf(result.vwap.replace(np.nan, 0.0)))
        assert (result.deviation == 0.0).all()

    def test_all_zero_volume_ofi(self):
        """All-zero volume → OFI 0, no division-by-zero."""
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        high = pd.Series([110.0] * n, index=dates)
        low = pd.Series([90.0] * n, index=dates)
        close = pd.Series([100.0] * n, index=dates)
        volume = pd.Series([0.0] * n, index=dates)

        result = compute_ofi_proxy(close, volume, high, low)
        assert (result.ofi == 0.0).all()
        assert (result.buy_volume == 0.0).all()
        assert (result.sell_volume == 0.0).all()

    def test_all_zero_volume_vw_momentum(self):
        """All-zero volume → momentum 0, no NaN/inf."""
        n = 15
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = pd.Series(100.0 + np.arange(n) * 0.1, index=dates)
        volume = pd.Series([0.0] * n, index=dates)

        momentum = compute_vw_momentum(close, volume, period=10)
        assert not np.any(np.isinf(momentum))
        assert not np.any(np.isnan(momentum))

    def test_empty_volume_profile(self):
        """Empty close/volume → empty series, no exception."""
        empty = pd.Series([], dtype=float)
        series = compute_volume_profile(empty, empty, bins=10, window=60)
        assert len(series) == 0

    def test_empty_vw_momentum(self):
        """Empty inputs → empty momentum series."""
        empty = pd.Series([], dtype=float)
        momentum = compute_vw_momentum(empty, empty, period=10)
        assert len(momentum) == 0

    def test_empty_obv_divergence(self):
        """Empty inputs → no divergence."""
        empty = pd.Series([], dtype=float)
        result = detect_obv_divergence(empty, empty, window=20)
        assert result.divergence_type == "none"
        assert result.strength == 0.0


# ── Retail Absorption (Smart Money Score) Tests ──────────────────────────────


class TestRetailAbsorption:
    """Tests for calculate_retail_absorption — Smart Money / Bandarmology."""

    @pytest.fixture()
    def accumulation_broker_flow(self) -> pd.DataFrame:
        """5 days of broker flow where retail (YP, CC, XL, PD) are net selling heavily."""
        rows = []
        for day in range(5):
            date = f"2024-01-{day+1:02d}"
            # Retail brokers selling heavily (>60% of total volume)
            for broker in ("YP", "CC", "XL", "PD"):
                rows.append({
                    "ticker": "TEST.JK",
                    "date": pd.Timestamp(date),
                    "broker": broker,
                    "buy_volume": 100,
                    "sell_volume": 10000,
                    "net_volume": -9900,
                    "buy_value": 1000.0,
                    "sell_value": 100000.0,
                    "net_value": -99000.0,
                })
            # Institutional brokers buying (small volume)
            for broker in ("AD", "AG"):
                rows.append({
                    "ticker": "TEST.JK",
                    "date": pd.Timestamp(date),
                    "broker": broker,
                    "buy_volume": 3000,
                    "sell_volume": 200,
                    "net_volume": 2800,
                    "buy_value": 30000.0,
                    "sell_value": 2000.0,
                    "net_value": 28000.0,
                })
        return pd.DataFrame(rows)

    @pytest.fixture()
    def accumulation_ohlcv(self) -> pd.DataFrame:
        """5 days of OHLCV where price holds steady (above VWAP)."""
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        return pd.DataFrame(
            {
                "high": [101.0, 101.5, 102.0, 101.8, 102.2],
                "low": [99.0, 99.5, 100.0, 100.2, 100.5],
                "close": [100.0, 100.5, 101.0, 101.0, 101.5],
                "volume": [100000, 110000, 120000, 105000, 115000],
            },
            index=dates,
        )

    def test_accumulation_detected(self, accumulation_broker_flow, accumulation_ohlcv):
        """Retail net selling + price holding → positive smart_money_score."""
        result = calculate_retail_absorption(
            broker_flow_df=accumulation_broker_flow,
            ohlcv_df=accumulation_ohlcv,
            ticker="TEST.JK",
            lookback=5,
        )
        assert isinstance(result, RetailAbsorptionResult)
        assert result.smart_money_score > 0
        assert result.label == "accumulation"
        assert result.retail_net_volume < 0  # Retail net selling

    def test_accumulation_streak(self, accumulation_broker_flow, accumulation_ohlcv):
        """5 consecutive days of accumulation → streak = 5."""
        result = calculate_retail_absorption(
            broker_flow_df=accumulation_broker_flow,
            ohlcv_df=accumulation_ohlcv,
            ticker="TEST.JK",
            lookback=5,
        )
        assert result.accumulation_streak == 5

    def test_daily_scores_length(self, accumulation_broker_flow, accumulation_ohlcv):
        """daily_scores should have exactly `lookback` entries."""
        result = calculate_retail_absorption(
            broker_flow_df=accumulation_broker_flow,
            ohlcv_df=accumulation_ohlcv,
            ticker="TEST.JK",
            lookback=5,
        )
        assert len(result.daily_scores) == 5

    def test_empty_broker_flow(self, accumulation_ohlcv):
        """Empty broker_flow → neutral result with zero score."""
        empty_bf = pd.DataFrame(columns=["ticker", "date", "broker", "buy_volume", "sell_volume", "net_volume"])
        result = calculate_retail_absorption(
            broker_flow_df=empty_bf,
            ohlcv_df=accumulation_ohlcv,
            ticker="TEST.JK",
            lookback=5,
        )
        assert result.smart_money_score == 0.0
        assert result.label == "neutral"
        assert result.accumulation_streak == 0

    def test_empty_ohlcv(self, accumulation_broker_flow):
        """Empty OHLCV → neutral result."""
        empty_ohlcv = pd.DataFrame(columns=["high", "low", "close", "volume"])
        result = calculate_retail_absorption(
            broker_flow_df=accumulation_broker_flow,
            ohlcv_df=empty_ohlcv,
            ticker="TEST.JK",
            lookback=5,
        )
        assert result.smart_money_score == 0.0
        assert result.label == "neutral"

    def test_distribution_label(self):
        """Retail selling + price dropping → distribution or neutral (not accumulation)."""
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        # Price dropping
        ohlcv = pd.DataFrame(
            {
                "high": [100.0, 99.0, 98.0, 97.0, 96.0],
                "low": [98.0, 97.0, 96.0, 95.0, 94.0],
                "close": [99.0, 98.0, 97.0, 96.0, 95.0],
                "volume": [100000] * 5,
            },
            index=dates,
        )
        bf_rows = []
        for day in range(5):
            date = f"2024-01-{day+1:02d}"
            for broker in ("YP", "CC"):
                bf_rows.append({
                    "ticker": "TEST.JK", "date": pd.Timestamp(date), "broker": broker,
                    "buy_volume": 100, "sell_volume": 5000, "net_volume": -4900,
                    "buy_value": 1000.0, "sell_value": 50000.0, "net_value": -49000.0,
                })
            for broker in ("AD",):
                bf_rows.append({
                    "ticker": "TEST.JK", "date": pd.Timestamp(date), "broker": broker,
                    "buy_volume": 200, "sell_volume": 8000, "net_volume": -7800,
                    "buy_value": 2000.0, "sell_value": 80000.0, "net_value": -78000.0,
                })
        bf = pd.DataFrame(bf_rows)
        result = calculate_retail_absorption(
            broker_flow_df=bf, ohlcv_df=ohlcv, ticker="TEST.JK", lookback=5,
        )
        assert result.label != "accumulation"

    def test_ticker_filtering(self, accumulation_broker_flow, accumulation_ohlcv):
        """Broker flow for other tickers should be filtered out."""
        # Add some rows for a different ticker
        bf = pd.concat([
            accumulation_broker_flow,
            pd.DataFrame([{
                "ticker": "OTHER.JK", "date": pd.Timestamp("2024-01-01"),
                "broker": "YP", "buy_volume": 1, "sell_volume": 1,
                "net_volume": 0, "buy_value": 1.0, "sell_value": 1.0, "net_value": 0.0,
            }]),
        ])
        result = calculate_retail_absorption(
            broker_flow_df=bf, ohlcv_df=accumulation_ohlcv, ticker="TEST.JK", lookback=5,
        )
        assert result.smart_money_score > 0  # Should still detect accumulation for TEST.JK

    def test_retail_sell_ratio_range(self, accumulation_broker_flow, accumulation_ohlcv):
        """retail_sell_ratio should be in [0, 1]."""
        result = calculate_retail_absorption(
            broker_flow_df=accumulation_broker_flow,
            ohlcv_df=accumulation_ohlcv,
            ticker="TEST.JK",
            lookback=5,
        )
        assert 0.0 <= result.retail_sell_ratio <= 1.0
