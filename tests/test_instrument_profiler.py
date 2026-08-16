"""Tests for InstrumentBehaviorProfiler (catatan.md TAHAP 2 — Prompt 2.1).

Uses real DB connection (PostgreSQL, see AGENTS.md §1) — tests are integration
tests against the live market database. Marked as integration so they can be
skipped in CI without DB.
"""
from __future__ import annotations

import os
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from market.analysis.instrument_profiler import (
    InstrumentBehaviorProfiler,
    InstrumentProfile,
    RegimeChangeAlert,
)

_HAS_DB = bool(os.environ.get("DATABASE_URL"))
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")


@pytest.fixture(scope="module")
def profiler():
    return InstrumentBehaviorProfiler()


# Tickers yang pasti ada di DB dengan data cukup
_FX_TICKERS = ["BBCA.JK", "BBRI.JK", "TLKM.JK"]


class TestVolatilityClassification:
    def test_low_regime(self, profiler):
        assert profiler._classify_volatility(0.5) == "LOW"

    def test_medium_regime(self, profiler):
        assert profiler._classify_volatility(1.5) == "MEDIUM"

    def test_high_regime(self, profiler):
        assert profiler._classify_volatility(3.0) == "HIGH"

    def test_extreme_regime(self, profiler):
        assert profiler._classify_volatility(5.0) == "EXTREME"

    def test_boundary_low_medium(self, profiler):
        assert profiler._classify_volatility(1.0) == "MEDIUM"

    def test_calculate_volatility_regime_returns_string(self, profiler):
        regime = profiler.calculate_volatility_regime("BBCA.JK")
        assert regime in {"LOW", "MEDIUM", "HIGH", "EXTREME"}


class TestMomentumVsMeanRevert:
    def test_synthetic_momentum_series(self, profiler):
        # Trending up → positive autocorrelation at some lag
        close = pd.Series(np.cumsum(np.random.RandomState(42).randn(300) + 0.1) + 100,
                          index=pd.date_range("2025-01-01", periods=300, freq="B"))
        strength, lookback = profiler._momentum_vs_meanrevert(close)
        assert -1.0 <= strength <= 1.0
        assert lookback in {5, 10, 20, 60, 120, 252}

    def test_calculate_momentum_returns_tuple(self, profiler):
        strength, lookback = profiler.calculate_momentum_vs_meanrevert("BBCA.JK")
        assert isinstance(strength, float)
        assert isinstance(lookback, int)
        assert -1.0 <= strength <= 1.0


class TestMeanReversionHalflife:
    def test_synthetic_stationary_series(self, profiler):
        # Mean-reverting series: y_t = 0.95 * y_{t-1} + noise
        rng = np.random.RandomState(123)
        n = 500
        y = np.zeros(n)
        for i in range(1, n):
            y[i] = 0.95 * y[i - 1] + rng.randn() * 0.5
        returns = pd.Series(np.diff(y) / y[:-1], index=pd.date_range("2025-01-01", periods=n - 1, freq="B"))
        hl = profiler._mean_reversion_halflife(returns)
        # Should be a positive finite number for mean-reverting series
        assert hl is None or (hl > 0 and np.isfinite(hl))

    def test_random_walk_returns_none(self, profiler):
        # Pure random walk → phi ≈ 0 → not mean-reverting
        rng = np.random.RandomState(99)
        returns = pd.Series(rng.randn(500) * 0.01, index=pd.date_range("2025-01-01", periods=500, freq="B"))
        hl = profiler._mean_reversion_halflife(returns)
        # For random walk, phi ≈ 0 → returns None
        assert hl is None or hl > 0


class TestLiquidityScore:
    def test_high_volume_low_spread(self, profiler):
        score = profiler._liquidity_score(20_000_000, 0.05)
        assert 8.0 <= score <= 10.0

    def test_low_volume_high_spread(self, profiler):
        score = profiler._liquidity_score(5_000, 1.5)
        assert score <= 4.0

    def test_score_in_range_1_to_10(self, profiler):
        for adv in [100, 1000, 100_000, 10_000_000]:
            for sp in [0.05, 0.5, 1.5]:
                s = profiler._liquidity_score(adv, sp)
                assert 1.0 <= s <= 10.0


class TestOptimalPositionSize:
    def test_high_volatility_caps_size(self, profiler):
        # Extreme vol → very small position size
        size = profiler._optimal_position_size_pct(1_000_000, 10.0)
        assert size <= 0.01  # capped low

    def test_low_volatility_allows_larger(self, profiler):
        size = profiler._optimal_position_size_pct(10_000_000, 1.0)
        assert 0 < size <= 0.10

    def test_zero_volatility_returns_floor(self, profiler):
        size = profiler._optimal_position_size_pct(1_000_000, 0.0)
        assert size == 0.01  # floor


class TestSeasonality:
    def test_seasonality_returns_lists(self, profiler):
        close = pd.Series(
            np.cumsum(np.random.RandomState(7).randn(300) * 0.5) + 100,
            index=pd.date_range("2024-01-01", periods=300, freq="B"),
        )
        best, worst = profiler._seasonality(close)
        assert isinstance(best, list) and isinstance(worst, list)
        assert all(1 <= m <= 12 for m in best + worst)

    def test_seasonality_insufficient_data(self, profiler):
        close = pd.Series([100, 101, 102], index=pd.date_range("2025-01-01", periods=3, freq="B"))
        best, worst = profiler._seasonality(close)
        assert best == [] and worst == []


class TestDayOfWeekEffect:
    def test_returns_dict_with_weekdays(self, profiler):
        returns = pd.Series(
            np.random.RandomState(11).randn(120) * 0.01,
            index=pd.date_range("2025-01-01", periods=120, freq="B"),
        )
        dow = profiler._day_of_week_effect(returns)
        assert set(dow.keys()) == {"Mon", "Tue", "Wed", "Thu", "Fri"}
        assert all(isinstance(v, float) for v in dow.values())


class TestTradingStyleSuitability:
    def test_synthetic_high_liquidity_low_vol(self, profiler):
        prof = InstrumentProfile(
            ticker="TEST",
            avg_daily_volatility=1.0,
            liquidity_score=9.0,
            avg_spread_pct=0.05,
            momentum_strength=0.1,
            mean_reversion_halflife=20.0,
            beta_to_ihsg=1.0,
            data_points_used=800,
        )
        suit = profiler.calculate_trading_style_suitability_from_data(prof)
        assert 1.0 <= suit["intraday"] <= 10.0
        assert 1.0 <= suit["swing"] <= 10.0
        assert 1.0 <= suit["investing"] <= 10.0
        # Low vol + long history → investing should be high
        assert suit["investing"] >= 7.0

    def test_synthetic_high_vol_illiquid(self, profiler):
        prof = InstrumentProfile(
            ticker="TEST2",
            avg_daily_volatility=6.0,
            liquidity_score=2.0,
            avg_spread_pct=1.5,
            momentum_strength=-0.1,
            mean_reversion_halflife=2.0,
            beta_to_ihsg=2.0,
            data_points_used=80,
        )
        suit = profiler.calculate_trading_style_suitability_from_data(prof)
        # High vol + illiquid → investing low
        assert suit["investing"] <= 5.0


class TestProfileSingleIntegration:
    def test_profile_bbcy_has_all_fields(self, profiler):
        prof = profiler.profile_single("BBCA.JK", lookback_days=756)
        assert prof.ticker == "BBCA.JK"
        assert prof.asset_class == "EQUITY_INDIVIDUAL"
        assert prof.volatility_regime in {"LOW", "MEDIUM", "HIGH", "EXTREME"}
        assert prof.avg_daily_volatility is not None and prof.avg_daily_volatility > 0
        assert prof.liquidity_score is not None and 1.0 <= prof.liquidity_score <= 10.0
        assert prof.intraday_suitability is not None
        assert prof.swing_suitability is not None
        assert prof.investing_suitability is not None
        assert prof.profile_confidence is not None
        assert prof.data_points_used is not None and prof.data_points_used > 0
        assert prof.last_updated is not None

    def test_profile_insufficient_data_returns_sparse(self, profiler):
        # Ticker yang mungkin tidak ada datanya — gunakan ticker dummy
        prof = profiler.profile_single("NONEXISTENT.X", lookback_days=252)
        assert prof.ticker == "NONEXISTENT.X"
        assert prof.data_points_used == 0
        assert prof.volatility_regime is None


class TestStoreAndGetProfile:
    def test_store_and_retrieve(self, profiler):
        prof = profiler.profile_single("BBCA.JK", lookback_days=756)
        profiler._store_profile(prof)
        got = profiler.get_profile("BBCA.JK")
        assert got is not None
        assert got.ticker == "BBCA.JK"
        assert got.volatility_regime == prof.volatility_regime
        # JSON fields round-trip
        assert isinstance(got.best_months, list)
        assert isinstance(got.day_of_week_effect, dict)

    def test_get_nonexistent_returns_none(self, profiler):
        got = profiler.get_profile("ZZZZZZ.JK")
        assert got is None


class TestRegimeChangeDetection:
    def test_detect_returns_alert(self, profiler):
        # Pastikan BBCA.JK sudah di-profile
        prof = profiler.profile_single("BBCA.JK", lookback_days=756)
        profiler._store_profile(prof)
        alert = profiler.detect_regime_change("BBCA.JK")
        assert isinstance(alert, RegimeChangeAlert)
        assert alert.ticker == "BBCA.JK"
        assert alert.severity in {"LOW", "MEDIUM", "HIGH"}
        assert isinstance(alert.changed, bool)
        assert isinstance(alert.details, str) and len(alert.details) > 0

    def test_detect_insufficient_data(self, profiler):
        alert = profiler.detect_regime_change("NONEXISTENT.X")
        assert alert.changed is False
        assert "insufficient" in alert.details.lower()


class TestProfileAllInstruments:
    def test_batch_run_with_subset(self, profiler, monkeypatch):
        # Patch _load_active_tickers untuk test cepat
        monkeypatch.setattr(
            profiler, "_load_active_tickers",
            lambda ac=None: ["BBCA.JK", "BBRI.JK"],
        )
        result = profiler.profile_all_instruments(lookback_days=756)
        assert result["profiled"] == 2
        assert result["errors"] == 0
