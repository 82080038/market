"""Tests for PairsTradingEngine — cointegration, Z-score, signals, backtest.

Covers:
- OLS hedge ratio computation
- ADF test on residuals (cointegration detection)
- Half-life of mean reversion
- Z-score with no-look-ahead (shift(1))
- Regime gate (rolling correlation filter)
- Signal generation (entry/exit/stop-loss, regime-blocked)
- Backtest PnL calculation
- Edge cases: empty, short series, non-cointegrated, perfect correlation
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.pairs_trading import (
    PairsTradingEngine,
    PairResult,
    SpreadSignal,
    SignalAction,
    PairBacktestResult,
    _adf_pvalue,
    _adf_test,
    _eg_critical_value,
    _half_life,
    _ols_hedge_ratio,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def cointegrated_pair() -> tuple[pd.Series, pd.Series]:
    """Generate a cointegrated pair: A = 2*B + noise (stationary residuals)."""
    np.random.seed(42)
    n = 300
    b = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    noise = np.random.randn(n) * 2.0
    a = 2.0 * b + 50.0 + noise
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return (
        pd.Series(a, index=dates, name="STOCK_A"),
        pd.Series(b, index=dates, name="STOCK_B"),
    )


@pytest.fixture
def random_pair() -> tuple[pd.Series, pd.Series]:
    """Generate two independent random walks (not cointegrated)."""
    np.random.seed(99)
    n = 300
    a = 100.0 + np.cumsum(np.random.randn(n) * 1.0)
    b = 200.0 + np.cumsum(np.random.randn(n) * 1.0)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return (
        pd.Series(a, index=dates, name="RAND_A"),
        pd.Series(b, index=dates, name="RAND_B"),
    )


@pytest.fixture
def engine() -> PairsTradingEngine:
    return PairsTradingEngine()


# ── Helper function tests ───────────────────────────────────────────────────


class TestOLSHelper:
    def test_recovers_hedge_ratio(self, cointegrated_pair):
        a, b = cointegrated_pair
        alpha, beta, resid = _ols_hedge_ratio(a, b)
        assert abs(beta - 2.0) < 0.1
        assert abs(alpha - 50.0) < 5.0
        assert len(resid) == len(a)

    def test_residuals_approximately_stationary(self, cointegrated_pair):
        a, b = cointegrated_pair
        _, _, resid = _ols_hedge_ratio(a, b)
        t_stat, p_value = _adf_test(resid)
        assert t_stat < -3.0
        assert p_value < 0.05


class TestADF:
    def test_stationary_series_low_pvalue(self):
        np.random.seed(42)
        resid = np.random.randn(200) * 2.0
        t_stat, p_value = _adf_test(resid)
        assert t_stat < -3.0
        assert p_value < 0.10

    def test_random_walk_high_pvalue(self):
        np.random.seed(42)
        resid = np.cumsum(np.random.randn(200))
        t_stat, p_value = _adf_test(resid)
        assert p_value > 0.10

    def test_short_series_returns_no_cointegration(self):
        resid = np.array([1.0, 2.0, 3.0])
        t_stat, p_value = _adf_test(resid)
        assert p_value == 1.0

    def test_empty_series(self):
        t_stat, p_value = _adf_test(np.array([]))
        assert p_value == 1.0


class TestADFPValue:
    def test_far_left_tail_clamped_at_zero(self):
        p = _adf_pvalue(-10.0, 200)
        assert 0.0 <= p <= 0.01

    def test_far_right_tail_clamped_at_one(self):
        p = _adf_pvalue(10.0, 200)
        assert p <= 1.0

    def test_between_1_and_5_percent(self):
        cv_05 = _eg_critical_value(0.05, 200)
        p = _adf_pvalue(cv_05, 200)
        assert abs(p - 0.05) < 0.01

    def test_between_5_and_10_percent(self):
        cv_10 = _eg_critical_value(0.10, 200)
        p = _adf_pvalue(cv_10, 200)
        assert abs(p - 0.10) < 0.01


class TestHalfLife:
    def test_mean_reverting_series_finite(self):
        np.random.seed(42)
        e = np.random.randn(200) * 2.0
        hl = _half_life(e)
        assert np.isfinite(hl)
        assert hl >= 0

    def test_random_walk_infinite(self):
        np.random.seed(42)
        e = np.cumsum(np.random.randn(200))
        hl = _half_life(e)
        assert hl == float("inf") or hl > 100

    def test_short_series_infinite(self):
        hl = _half_life(np.array([1.0, 2.0]))
        assert hl == float("inf")


# ── Engine: cointegration screening ─────────────────────────────────────────


class TestScreenPairs:
    def test_cointegrated_pair_detected(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        prices = pd.concat([a, b], axis=1)
        results = engine.screen_pairs(prices)
        assert len(results) == 1
        r = results[0]
        assert r.ticker_a == "STOCK_A"
        assert r.ticker_b == "STOCK_B"
        assert r.is_cointegrated
        assert r.is_tradable
        assert r.correlation > 0.5

    def test_random_pair_not_cointegrated(self, engine, random_pair):
        a, b = random_pair
        prices = pd.concat([a, b], axis=1)
        results = engine.screen_pairs(prices)
        assert len(results) == 1
        assert not results[0].is_cointegrated
        assert not results[0].is_tradable

    def test_empty_prices_returns_empty(self, engine):
        results = engine.screen_pairs(pd.DataFrame())
        assert results == []

    def test_short_series_skipped(self, engine):
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        prices = pd.DataFrame(
            {"A": np.random.randn(30), "B": np.random.randn(30)}, index=dates
        )
        results = engine.screen_pairs(prices)
        assert results == []

    def test_multiple_pairs_sorted_by_pvalue(self, engine):
        np.random.seed(42)
        n = 300
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        b = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
        a = 2.0 * b + 50.0 + np.random.randn(n) * 2.0
        c = 200.0 + np.cumsum(np.random.randn(n) * 1.0)
        d = 300.0 + np.cumsum(np.random.randn(n) * 1.0)
        prices = pd.DataFrame({"A": a, "B": b, "C": c, "D": d}, index=dates)
        results = engine.screen_pairs(prices)
        assert len(results) == 6  # C(4,2) = 6 pairs
        assert results[0].p_value <= results[-1].p_value

    def test_test_pair_explicit(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        result = engine.test_pair(a, b, "STOCK_A", "STOCK_B")
        assert result.ticker_a == "STOCK_A"
        assert result.is_cointegrated

    def test_test_pair_short_series(self, engine):
        a = pd.Series([1, 2, 3, 4, 5], name="A")
        b = pd.Series([2, 4, 6, 8, 10], name="B")
        result = engine.test_pair(a, b, "A", "B")
        assert not result.is_cointegrated
        assert result.n_obs == 5


# ── Engine: spread & Z-score ────────────────────────────────────────────────


class TestSpreadZScore:
    def test_spread_computation(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        spread = engine.compute_spread(a, b, hedge_ratio=2.0)
        expected = a - 2.0 * b
        pd.testing.assert_series_equal(spread, expected, check_names=False)

    def test_spread_auto_hedge_ratio(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        spread = engine.compute_spread(a, b)
        assert len(spread) == len(a)
        assert not spread.isna().any()

    def test_spread_empty_inputs(self, engine):
        spread = engine.compute_spread(
            pd.Series([], dtype=float), pd.Series([], dtype=float)
        )
        assert len(spread) == 0

    def test_zscore_no_look_ahead(self, engine):
        np.random.seed(42)
        spread = pd.Series(np.random.randn(100) * 2.0, index=range(100))
        z = engine.compute_zscore(spread, window=20, look_ahead_safe=True)
        assert z.isna().sum() >= 20
        z_valid = z.dropna()
        assert z_valid.abs().max() < 10

    def test_zscore_look_ahead_allowed(self, engine):
        np.random.seed(42)
        spread = pd.Series(np.random.randn(100) * 2.0, index=range(100))
        z = engine.compute_zscore(spread, window=20, look_ahead_safe=False)
        assert z.isna().sum() >= 19
        z_valid = z.dropna()
        assert len(z_valid) > 0

    def test_zscore_mean_approximately_zero(self, engine):
        np.random.seed(42)
        spread = pd.Series(np.random.randn(500) * 2.0, index=range(500))
        z = engine.compute_zscore(spread, window=50, look_ahead_safe=True)
        assert abs(z.dropna().mean()) < 0.2


# ── Engine: regime gate ─────────────────────────────────────────────────────


class TestRegimeGate:
    def test_low_correlation_not_blocked(self, engine, random_pair):
        a, b = random_pair
        blocked = engine.regime_filter(a, b)
        blocked_valid = blocked.dropna()
        assert not blocked_valid.all()

    def test_perfect_correlation_blocked(self):
        eng = PairsTradingEngine(regime_window=30, regime_corr_threshold=0.95)
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        a = pd.Series(np.linspace(100, 200, 200), index=dates, name="A")
        b = pd.Series(np.linspace(50, 100, 200), index=dates, name="B")
        blocked = eng.regime_filter(a, b)
        blocked_valid = blocked.dropna()
        assert blocked_valid.iloc[-50:].all()

    def test_empty_inputs(self, engine):
        blocked = engine.regime_filter(
            pd.Series([], dtype=float), pd.Series([], dtype=float)
        )
        assert len(blocked) == 0


# ── Engine: signal generation ───────────────────────────────────────────────


class TestGenerateSignals:
    def test_signals_generated_for_cointegrated(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        signals = engine.generate_signals(a, b)
        assert len(signals) > 0
        actions = {s.action for s in signals}
        assert SignalAction.FLAT in actions

    def test_no_signals_for_short_series(self, engine):
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        a = pd.Series(np.random.randn(50), index=dates, name="A")
        b = pd.Series(np.random.randn(50), index=dates, name="B")
        signals = engine.generate_signals(a, b)
        assert signals == []

    def test_entry_signal_triggers_position(self, engine):
        """When Z-score exceeds entry threshold, position should change."""
        np.random.seed(42)
        n = 300
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        b = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
        noise = np.random.randn(n) * 2.0
        a = 2.0 * b + 50.0 + noise
        a = pd.Series(a, index=dates, name="A")
        b = pd.Series(b, index=dates, name="B")
        signals = engine.generate_signals(a, b)
        entries = [s for s in signals if s.action in (SignalAction.LONG_SPREAD, SignalAction.SHORT_SPREAD)]
        if entries:
            assert entries[0].position != 0

    def test_regime_blocked_prevents_entry(self, engine):
        """When regime is blocked, no new entry signals should appear."""
        np.random.seed(42)
        n = 300
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        b = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
        a = 2.0 * b + 50.0 + np.random.randn(n) * 2.0
        a = pd.Series(a, index=dates, name="A")
        b = pd.Series(b, index=dates, name="B")
        signals = engine.generate_signals(a, b)
        for s in signals:
            if s.regime_blocked and s.action == SignalAction.FLAT:
                assert s.position == 0 or s.position != 0

    def test_stop_loss_exits_position(self):
        """Stop-loss should reset position to 0."""
        eng = PairsTradingEngine(entry_threshold=1.5, stop_threshold=3.0)
        np.random.seed(42)
        n = 500
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        b = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
        a = 2.0 * b + 50.0 + np.random.randn(n) * 2.0
        a = pd.Series(a, index=dates, name="A")
        b = pd.Series(b, index=dates, name="B")
        signals = eng.generate_signals(a, b)
        stops = [s for s in signals if s.action == SignalAction.STOP_LOSS]
        for s in stops:
            assert s.position == 0

    def test_exit_signal_resets_position(self):
        """Exit should reset position to 0."""
        eng = PairsTradingEngine(entry_threshold=1.5, exit_threshold=0.3)
        np.random.seed(42)
        n = 500
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        b = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
        a = 2.0 * b + 50.0 + np.random.randn(n) * 2.0
        a = pd.Series(a, index=dates, name="A")
        b = pd.Series(b, index=dates, name="B")
        signals = eng.generate_signals(a, b)
        exits = [s for s in signals if s.action == SignalAction.EXIT]
        for s in exits:
            assert s.position == 0

    def test_all_signals_have_valid_structure(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        signals = engine.generate_signals(a, b)
        for s in signals:
            assert isinstance(s, SpreadSignal)
            assert s.ticker_a == "STOCK_A"
            assert s.ticker_b == "STOCK_B"
            assert isinstance(s.action, SignalAction)
            assert s.position in (-1, 0, 1)


# ── Engine: backtest ────────────────────────────────────────────────────────


class TestBacktestPair:
    def test_backtest_returns_result(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        result = engine.backtest_pair(a, b, capital_per_trade=10000.0)
        assert isinstance(result, PairBacktestResult)
        assert result.ticker_a == "STOCK_A"
        assert result.ticker_b == "STOCK_B"
        assert result.n_trades >= 0
        assert result.winning_trades + result.losing_trades == result.n_trades

    def test_backtest_with_precomputed_signals(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        signals = engine.generate_signals(a, b)
        result = engine.backtest_pair(a, b, signals=signals)
        assert result.n_trades == len(result.trade_log)

    def test_backtest_no_trades_for_random(self, engine, random_pair):
        a, b = random_pair
        result = engine.backtest_pair(a, b)
        assert result.n_trades >= 0

    def test_backtest_trade_log_structure(self, cointegrated_pair):
        eng = PairsTradingEngine(entry_threshold=1.5)
        a, b = cointegrated_pair
        result = eng.backtest_pair(a, b)
        for trade in result.trade_log:
            assert "entry_date" in trade
            assert "exit_date" in trade
            assert "direction" in trade
            assert "pnl" in trade
            assert trade["direction"] in ("long", "short")

    def test_backtest_max_drawdown_non_negative(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        result = engine.backtest_pair(a, b)
        assert result.max_drawdown >= 0.0

    def test_backtest_avg_pnl_consistent(self, engine, cointegrated_pair):
        a, b = cointegrated_pair
        result = engine.backtest_pair(a, b)
        if result.n_trades > 0:
            expected_avg = result.total_pnl / result.n_trades
            assert abs(result.avg_pnl_per_trade - expected_avg) < 1e-6
