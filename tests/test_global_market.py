"""Tests for Global Market Engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.analysis.global_market import GLOBAL_INDICES, GlobalMarketEngine


def _make_index_data(n: int, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic index data."""
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    if trend == "up":
        close = 100.0 * np.exp(np.linspace(0, 0.2, n))
    else:
        close = 100.0 * np.exp(-np.linspace(0, 0.2, n))
    return pd.DataFrame({"close": close}, index=dates)


def test_global_all_above():
    engine = GlobalMarketEngine()
    data = {
        ticker: _make_index_data(250, "up")
        for ticker in GLOBAL_INDICES
    }
    result = engine.analyze(data)
    assert result.score == 100.0
    assert len(result.above_ma50) == 7
    assert len(result.above_ma200) == 7


def test_global_all_below():
    engine = GlobalMarketEngine()
    data = {
        ticker: _make_index_data(250, "down")
        for ticker in GLOBAL_INDICES
    }
    result = engine.analyze(data)
    assert result.score == 0.0
    assert len(result.below_ma50) == 7
    assert len(result.below_ma200) == 7


def test_global_mixed():
    engine = GlobalMarketEngine()
    data = {}
    tickers = list(GLOBAL_INDICES.keys())
    for i, ticker in enumerate(tickers):
        trend = "up" if i < 4 else "down"
        data[ticker] = _make_index_data(250, trend)
    result = engine.analyze(data)
    assert 0 < result.score < 100
    assert len(result.above_ma50) == 4
    assert len(result.below_ma50) == 3


def test_global_empty():
    engine = GlobalMarketEngine()
    result = engine.analyze({})
    assert result.score == 0.0


def test_global_short_data():
    engine = GlobalMarketEngine()
    data = {"^GSPC": _make_index_data(30, "up")}
    result = engine.analyze(data)
    # Not enough data for MA50 or MA200
    assert result.score == 0.0
    assert len(result.above_ma50) == 0
