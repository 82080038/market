"""Tests for walk-forward, Monte Carlo, and Deflated Sharpe Ratio."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.backtest.analysis import (
    deflated_sharpe_ratio,
    monte_carlo,
    walk_forward,
)
from market.backtest.strategies import BuyHoldStrategy


def _make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    close = 100.0 * np.cumprod(1 + np.random.normal(0.001, 0.015, n))
    return pd.DataFrame(
        {
            "open": close * 1.001,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=dates,
    )


def test_walk_forward_basic():
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(300)
    result = walk_forward(
        strategy, data, train_size=100, test_size=50, step=50,
    )
    assert len(result.window_results) > 0
    assert isinstance(result.oos_sharpe, float)
    assert isinstance(result.oos_return_pct, float)
    assert 0 <= result.consistency_pct <= 100


def test_walk_forward_insufficient_data():
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(50)
    result = walk_forward(
        strategy, data, train_size=100, test_size=50, step=50,
    )
    assert len(result.window_results) == 0


def test_monte_carlo_basic():
    returns = [0.02, -0.01, 0.03, -0.02, 0.01, 0.04, -0.01, 0.02]
    result = monte_carlo(returns, initial_capital=100_000_000, n_simulations=100)
    assert "p5" in result.percentiles
    assert "p95" in result.percentiles
    assert result.mean_final_equity > 0
    assert result.std_final_equity > 0
    assert 0 <= result.prob_loss_pct <= 100


def test_monte_carlo_empty_returns():
    result = monte_carlo([])
    assert result.mean_final_equity == 0.0


def test_monte_carlo_all_positive():
    returns = [0.01, 0.02, 0.03, 0.01]
    result = monte_carlo(returns, initial_capital=100_000_000, n_simulations=100)
    assert result.prob_loss_pct == 0.0
    assert result.mean_final_equity > 100_000_000


def test_monte_carlo_all_negative():
    returns = [-0.01, -0.02, -0.03, -0.01]
    result = monte_carlo(returns, initial_capital=100_000_000, n_simulations=100)
    assert result.prob_loss_pct == 100.0
    assert result.mean_final_equity < 100_000_000


def test_deflated_sharpe_ratio_basic():
    dsr = deflated_sharpe_ratio(
        sharpe=2.0, n_trials=10, sample_size=252,
    )
    assert isinstance(dsr, float)


def test_deflated_sharpe_ratio_higher_is_better():
    dsr_low = deflated_sharpe_ratio(sharpe=0.5, n_trials=100, sample_size=252)
    dsr_high = deflated_sharpe_ratio(sharpe=3.0, n_trials=100, sample_size=252)
    assert dsr_high > dsr_low


def test_deflated_sharpe_ratio_more_trials_penalized():
    dsr_few = deflated_sharpe_ratio(sharpe=1.5, n_trials=5, sample_size=252)
    dsr_many = deflated_sharpe_ratio(sharpe=1.5, n_trials=500, sample_size=252)
    assert dsr_few > dsr_many  # More trials → lower DSR


def test_deflated_sharpe_ratio_edge_cases():
    assert deflated_sharpe_ratio(sharpe=1.0, n_trials=0, sample_size=252) == 0.0
    assert deflated_sharpe_ratio(sharpe=1.0, n_trials=10, sample_size=1) == 0.0
