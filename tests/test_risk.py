"""Tests for Risk Engine and Circuit Breaker."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.risk.engine import CircuitBreaker, RiskEngine


def _make_returns(n: int = 100, seed: int = 42) -> pd.Series:
    rng = np.random.RandomState(seed)
    return pd.Series(rng.normal(0.001, 0.02, n))


def test_risk_basic_assess():
    engine = RiskEngine()
    result = engine.assess(
        ticker="BBCA.JK",
        last_price=8750.0,
        atr=125.5,
        capital=100_000_000,
    )
    assert result.ticker == "BBCA.JK"
    assert result.stop_loss < result.last_price
    assert result.take_profit > result.last_price
    assert result.position_size > 0
    assert result.slippage == 0.0005
    assert result.risk_flags == []


def test_risk_stop_loss_atr_based():
    engine = RiskEngine(atr_multiplier_sl=1.5)
    result = engine.assess(
        ticker="TEST.JK",
        last_price=100.0,
        atr=10.0,
        capital=1_000_000,
    )
    # stop = 100 - 1.5 * 10 = 85
    assert result.stop_loss == 85.0
    # tp = 100 + 2 * (100 - 85) = 130
    assert result.take_profit == 130.0


def test_risk_liquidity_flag():
    engine = RiskEngine()
    result = engine.assess(
        ticker="ILLIQ.JK",
        last_price=100.0,
        atr=5.0,
        capital=1_000_000,
        avg_daily_volume=1000,  # Very low volume
        target_value=500_000,  # Large order relative to ADV
    )
    assert "LIQUIDITY_LOW" in result.risk_flags


def test_risk_volatility_flag():
    engine = RiskEngine()
    # High volatility returns
    returns = pd.Series(np.random.normal(0, 0.05, 100))
    result = engine.assess(
        ticker="VOL.JK",
        last_price=100.0,
        atr=10.0,
        capital=1_000_000,
        returns=returns,
    )
    assert "HIGH_VOLATILITY" in result.risk_flags


def test_risk_var_cvar():
    engine = RiskEngine()
    returns = _make_returns(100)
    result = engine.assess(
        ticker="VAR.JK",
        last_price=100.0,
        atr=5.0,
        capital=1_000_000,
        returns=returns,
    )
    assert result.var_95 is not None
    assert result.cvar_95 is not None
    assert result.cvar_95 <= result.var_95  # CVaR <= VaR (more negative)


def test_risk_kelly_criterion():
    engine = RiskEngine()
    result = engine.assess(
        ticker="KELLY.JK",
        last_price=100.0,
        atr=5.0,
        capital=1_000_000,
        win_rate=0.55,
        avg_win=0.03,
        avg_loss=0.02,
    )
    assert result.kelly_fraction is not None
    assert result.kelly_fraction > 0  # Positive edge


def test_risk_kelly_negative_edge():
    engine = RiskEngine()
    result = engine.assess(
        ticker="BAD.JK",
        last_price=100.0,
        atr=5.0,
        capital=1_000_000,
        win_rate=0.30,
        avg_win=0.02,
        avg_loss=0.03,
    )
    assert result.kelly_fraction == 0.0  # No bet on negative edge


def test_circuit_breaker_normal():
    cb = CircuitBreaker(threshold_pct=10.0)
    state = cb.update(100_000_000)
    assert not state.is_triggered
    assert state.current_drawdown_pct == 0.0


def test_circuit_breaker_triggered():
    cb = CircuitBreaker(threshold_pct=10.0)
    cb.update(100_000_000)
    state = cb.update(89_000_000)  # 11% drawdown
    assert state.is_triggered
    assert state.current_drawdown_pct >= 10.0


def test_circuit_breaker_not_triggered_below_threshold():
    cb = CircuitBreaker(threshold_pct=10.0)
    cb.update(100_000_000)
    state = cb.update(95_000_000)  # 5% drawdown
    assert not state.is_triggered


def test_circuit_breaker_reset():
    cb = CircuitBreaker(threshold_pct=10.0)
    cb.update(100_000_000)
    cb.update(89_000_000)
    assert cb._triggered
    cb.reset()
    assert not cb._triggered
    assert cb._peak_equity == 0.0


def test_circuit_breaker_new_peak():
    cb = CircuitBreaker(threshold_pct=10.0)
    cb.update(100_000_000)
    cb.update(110_000_000)  # New peak
    state = cb.update(105_000_000)  # ~4.5% DD from new peak
    assert not state.is_triggered
    assert state.peak_equity == 110_000_000
