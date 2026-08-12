"""Tests for isolated backtester."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.ablation.isolated_backtest import (
    IsolatedBacktester,
    IsolationResult,
    compute_metrics,
    simulate_returns,
)


def _make_synthetic_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Create synthetic OHLCV data with a trend."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    returns = rng.normal(0.001, 0.02, n)
    close = 10000 * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(1_000_000, 10_000_000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def _make_signals(ohlcv: pd.DataFrame, bias: float = 0.0) -> pd.Series:
    """Create signal series with optional directional bias."""
    rng = np.random.default_rng(123)
    raw = rng.random(len(ohlcv))
    signal = pd.Series(0, index=ohlcv.index)
    signal[raw > 0.5 + bias] = 1
    signal[raw < 0.3 + bias] = -1
    return signal


class TestSimulateReturns:
    def test_basic_returns(self):
        ohlcv = _make_synthetic_ohlcv(100)
        signals = _make_signals(ohlcv)
        returns = simulate_returns(ohlcv, signals)
        assert not returns.empty
        assert len(returns) > 0

    def test_empty_signals(self):
        ohlcv = _make_synthetic_ohlcv(100)
        signals = pd.Series(0, index=ohlcv.index)
        returns = simulate_returns(ohlcv, signals)
        # All-zero signals → returns should be 0 (minus cost on changes, but no changes)
        assert (returns == 0).all()

    def test_cost_applied_on_signal_change(self):
        ohlcv = _make_synthetic_ohlcv(100)
        signals = pd.Series(0, index=ohlcv.index)
        signals.iloc[50] = 1  # One signal change
        returns = simulate_returns(ohlcv, signals, cost_per_trade=0.01)
        # The day of signal change should have cost deducted
        change_idx = ohlcv.index[50]
        assert change_idx in returns.index
        assert returns.loc[change_idx] < 0  # cost applied at signal change


class TestComputeMetrics:
    def test_basic_metrics(self):
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))
        metrics = compute_metrics(returns)
        assert "sharpe_ratio" in metrics
        assert "sortino_ratio" in metrics
        assert "max_drawdown_pct" in metrics
        assert "win_rate_pct" in metrics
        assert "total_return_pct" in metrics
        assert "alpha" in metrics
        assert "beta" in metrics
        assert metrics["n_days"] == 252

    def test_empty_returns(self):
        returns = pd.Series(dtype=float)
        metrics = compute_metrics(returns)
        assert metrics["sharpe_ratio"] == 0.0
        assert metrics["n_days"] == 0

    def test_with_benchmark(self):
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 252))
        benchmark = pd.Series(rng.normal(0.0005, 0.015, 252))
        metrics = compute_metrics(returns, benchmark)
        assert metrics["alpha"] != 0.0
        assert metrics["beta"] != 0.0

    def test_win_rate_range(self):
        returns = pd.Series(np.random.normal(0, 0.02, 100))
        metrics = compute_metrics(returns)
        assert 0 <= metrics["win_rate_pct"] <= 100


class TestIsolatedBacktester:
    def test_run_basic(self):
        ohlcv = _make_synthetic_ohlcv(300)
        baseline = _make_signals(ohlcv, bias=0.0)
        engine = _make_signals(ohlcv, bias=0.1)

        backtester = IsolatedBacktester()
        result = backtester.run(
            engine_name="test_engine",
            ohlcv=ohlcv,
            baseline_signals=baseline,
            engine_signals=engine,
        )

        assert isinstance(result, IsolationResult)
        assert result.engine_name == "test_engine"
        assert result.error is None
        assert "sharpe_ratio" in result.baseline_metrics
        assert "sharpe_ratio" in result.isolated_metrics
        assert "sharpe_ratio" in result.delta_metrics
        assert result.n_observations > 0

    def test_run_identical_signals(self):
        """When engine signals = baseline signals, delta should be ~0."""
        ohlcv = _make_synthetic_ohlcv(300)
        signals = _make_signals(ohlcv)

        backtester = IsolatedBacktester()
        result = backtester.run(
            engine_name="identical",
            ohlcv=ohlcv,
            baseline_signals=signals,
            engine_signals=signals,
        )

        assert result.delta_sharpe == pytest.approx(0.0, abs=1e-6)
        assert result.p_value == pytest.approx(1.0, abs=0.01)

    def test_run_with_error(self):
        """Should handle errors gracefully."""
        ohlcv = pd.DataFrame()  # empty
        backtester = IsolatedBacktester()
        result = backtester.run(
            engine_name="error_test",
            ohlcv=ohlcv,
            baseline_signals=pd.Series(dtype=float),
            engine_signals=pd.Series(dtype=float),
        )
        # Empty data should not crash, just return empty metrics
        assert result.engine_name == "error_test"

    def test_run_with_benchmark(self):
        ohlcv = _make_synthetic_ohlcv(300)
        baseline = _make_signals(ohlcv)
        engine = _make_signals(ohlcv, bias=0.1)
        benchmark = ohlcv["close"].pct_change().dropna()

        backtester = IsolatedBacktester()
        result = backtester.run(
            engine_name="with_benchmark",
            ohlcv=ohlcv,
            baseline_signals=baseline,
            engine_signals=engine,
            benchmark_returns=benchmark,
        )

        assert result.isolated_metrics.get("alpha", 0) != 0 or result.isolated_metrics.get("beta", 0) != 0
