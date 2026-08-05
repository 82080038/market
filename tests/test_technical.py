"""Tests for Technical Analysis Engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.analysis.technical import TechnicalAnalysisEngine


def _make_ohlcv(n: int = 100, start_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data with an uptrend."""
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.01, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
    op = close * (1 + np.random.normal(0, 0.003, n))
    volume = np.random.randint(100000, 500000, n).astype(float)
    return pd.DataFrame(
        {"open": op, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def test_technical_uptrend():
    engine = TechnicalAnalysisEngine()
    df = _make_ohlcv(100, start_price=100.0)
    result = engine.analyze("TEST.JK", df)
    assert 0 <= result.score <= 100
    assert result.trend in ("uptrend", "downtrend", "sideways")
    assert "trend" in result.breakdown
    assert "rsi" in result.breakdown
    assert "macd" in result.breakdown
    assert "volatility" in result.breakdown
    assert "volume" in result.breakdown
    assert "ma20" in result.indicators
    assert "ma50" in result.indicators
    assert "rsi" in result.indicators
    assert "atr" in result.indicators
    assert "adx" in result.indicators
    assert "poc" in result.indicators


def test_technical_insufficient_data():
    engine = TechnicalAnalysisEngine()
    df = _make_ohlcv(30)
    result = engine.analyze("SHORT.JK", df)
    assert result.score == 0.0
    assert result.trend == "insufficient_data"


def test_technical_empty_data():
    engine = TechnicalAnalysisEngine()
    result = engine.analyze("EMPTY.JK", pd.DataFrame())
    assert result.score == 0.0
    assert result.trend == "insufficient_data"


def test_technical_downtrend():
    engine = TechnicalAnalysisEngine()
    dates = pd.date_range("2024-01-02", periods=100, freq="B")
    close = 100.0 * np.exp(-np.linspace(0, 0.3, 100))
    df = pd.DataFrame(
        {
            "open": close * 1.01,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": np.full(100, 200000.0),
        },
        index=dates,
    )
    result = engine.analyze("DOWN.JK", df)
    assert result.trend in ("downtrend", "sideways")
    assert result.breakdown["trend"] <= 12.0


def test_technical_rsi_range():
    engine = TechnicalAnalysisEngine()
    df = _make_ohlcv(100)
    result = engine.analyze("RSI.JK", df)
    rsi = result.indicators["rsi"]
    assert 0 <= rsi <= 100


def test_technical_volume_profile():
    engine = TechnicalAnalysisEngine()
    df = _make_ohlcv(100)
    result = engine.analyze("VP.JK", df)
    poc = result.indicators["poc"]
    vah = result.indicators["vah"]
    val = result.indicators["val"]
    assert val <= poc <= vah
