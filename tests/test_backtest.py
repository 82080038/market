"""Tests for backtest engine and strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.backtest.engine import BacktestEngine
from market.backtest.strategies import (
    BuyHoldStrategy,
    ConvictionStrategy,
    MACrossoverStrategy,
    Signal,
)


def _make_ohlcv(n: int = 100, trend: str = "up") -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    if trend == "up":
        close = 100.0 * np.exp(np.linspace(0, 0.15, n))
    elif trend == "down":
        close = 100.0 * np.exp(-np.linspace(0, 0.15, n))
    else:
        np.random.seed(42)
        close = 100.0 * np.cumprod(1 + np.random.normal(0, 0.01, n))
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


def test_buy_hold_strategy():
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(100, "up")
    signals = strategy.generate_signals(data)
    assert signals.iloc[0] == Signal.BUY
    assert signals.iloc[-1] == Signal.SELL


def test_ma_crossover_signals():
    strategy = MACrossoverStrategy(fast=5, slow=10)
    # Use sideways data to generate crossovers
    data = _make_ohlcv(50, "sideways")
    signals = strategy.generate_signals(data)
    assert len(signals) == 50
    # Should have at least one signal (buy or sell) in sideways market
    assert any(s != Signal.HOLD for s in signals)


def test_ma_crossover_insufficient_data():
    strategy = MACrossoverStrategy(fast=20, slow=50)
    data = _make_ohlcv(30)
    signals = strategy.generate_signals(data)
    assert all(s == Signal.HOLD for s in signals)


def test_conviction_strategy():
    strategy = ConvictionStrategy(buy_threshold=65, sell_threshold=35)
    data = _make_ohlcv(50, "up")
    data["score"] = np.linspace(80, 20, 50)  # Declining conviction
    signals = strategy.generate_signals(data)
    assert signals.iloc[0] == Signal.BUY
    assert signals.iloc[-1] == Signal.SELL


def test_conviction_no_score_column():
    strategy = ConvictionStrategy()
    data = _make_ohlcv(50)
    signals = strategy.generate_signals(data)
    assert all(s == Signal.HOLD for s in signals)


def test_backtest_buy_hold_uptrend():
    engine = BacktestEngine(initial_capital=100_000_000)
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(100, "up")
    result = engine.run(strategy, data, "TEST.JK")
    assert len(result.equity_curve) == 100
    assert result.metrics["total_return_pct"] > 0
    assert result.metrics["final_equity"] > 100_000_000
    assert len(result.trades) >= 1


def test_backtest_buy_hold_downtrend():
    engine = BacktestEngine(initial_capital=100_000_000)
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(100, "down")
    result = engine.run(strategy, data, "TEST.JK")
    assert result.metrics["total_return_pct"] < 0
    assert result.metrics["final_equity"] < 100_000_000


def test_backtest_empty_data():
    engine = BacktestEngine()
    strategy = BuyHoldStrategy()
    result = engine.run(strategy, pd.DataFrame(), "EMPTY.JK")
    assert result.metrics == {}
    assert len(result.trades) == 0


def test_backtest_metrics_computed():
    engine = BacktestEngine(initial_capital=100_000_000)
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(100, "up")
    result = engine.run(strategy, data, "TEST.JK")
    assert "sharpe_ratio" in result.metrics
    assert "sortino_ratio" in result.metrics
    assert "max_drawdown_pct" in result.metrics
    assert "annual_return_pct" in result.metrics
    # DSR key always present (gap #1: DSR integration)
    assert "deflated_sharpe_ratio" in result.metrics


def test_backtest_dsr_default_no_adjustment():
    """With n_trials=1 (default), DSR should be 0 (no multiple-testing)."""
    engine = BacktestEngine(initial_capital=100_000_000)
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(100, "up")
    result = engine.run(strategy, data, "TEST.JK")
    # Default n_trials=1 → DSR not computed (stays 0.0)
    assert result.metrics["deflated_sharpe_ratio"] == 0.0


def test_backtest_dsr_with_multiple_trials():
    """With n_trials>1, DSR should be computed (may be negative if Sharpe low)."""
    engine = BacktestEngine(initial_capital=100_000_000)
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(100, "up")
    result = engine.run(strategy, data, "TEST.JK", n_trials=10)
    # DSR is computed — value depends on Sharpe, but key must exist
    assert "deflated_sharpe_ratio" in result.metrics
    assert isinstance(result.metrics["deflated_sharpe_ratio"], float)


def test_backtest_ma_crossover():
    engine = BacktestEngine(initial_capital=100_000_000)
    strategy = MACrossoverStrategy(fast=5, slow=10)
    data = _make_ohlcv(100, "sideways")
    result = engine.run(strategy, data, "MA.JK")
    assert len(result.equity_curve) == 100
    # Should have some trades in sideways market
    assert len(result.trades) > 0


def test_backtest_costs_applied():
    engine = BacktestEngine(
        initial_capital=100_000_000,
        commission_rate=0.0015,
        sales_tax_rate=0.001,
    )
    strategy = BuyHoldStrategy()
    data = _make_ohlcv(50, "up")
    result = engine.run(strategy, data, "COST.JK")
    # Buy trade should have cost (commission)
    buy_trades = [t for t in result.trades if t.side == "buy"]
    assert len(buy_trades) > 0
    assert buy_trades[0].cost > 0
    # Sell trade should have cost (commission + sales tax)
    sell_trades = [t for t in result.trades if t.side == "sell"]
    if sell_trades:
        assert sell_trades[0].cost > 0
