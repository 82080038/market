"""Tests for VTA-style verbal reasoning engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.vta_reasoning import (
    ReasoningTrace,
    VTAReasoningEngine,
    annotate_ohlcv,
    generate_reasoning,
)


def _make_ohlcv(n: int = 30, trend: float = 0.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5 + trend)
    return pd.DataFrame({
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    }, index=dates)


class TestAnnotateOHLCV:
    def test_basic_annotations(self):
        ohlcv = _make_ohlcv(30)
        ann = annotate_ohlcv(ohlcv, lookback=20)
        assert "current_price" in ann
        assert "ma_5" in ann
        assert "ma_20" in ann
        assert "rsi" in ann
        assert "momentum_5d" in ann
        assert "bb_width" in ann
        assert "vol_ratio" in ann
        assert "atr_ratio" in ann
        assert "macd" in ann

    def test_short_data(self):
        ohlcv = _make_ohlcv(5)
        ann = annotate_ohlcv(ohlcv, lookback=20)
        assert ann["current_price"] > 0
        assert ann["rsi"] >= 0
        assert ann["rsi"] <= 100

    def test_empty_data(self):
        ohlcv = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        ann = annotate_ohlcv(ohlcv, lookback=20)
        assert ann["current_price"] == 0


class TestGenerateReasoning:
    def test_bullish_signal(self):
        annotations = {
            "ma_crossover": 5.0,
            "rsi": 55.0,
            "momentum_5d": 0.05,
            "bb_pct": 0.5,
            "vol_ratio": 1.8,
            "atr_ratio": 0.9,
            "macd_histogram": 0.5,
        }
        trace = generate_reasoning(annotations)
        assert trace.signal == 1
        assert trace.confidence > 0
        assert "naik" in trace.explanation

    def test_bearish_signal(self):
        annotations = {
            "ma_crossover": -5.0,
            "rsi": 75.0,
            "momentum_5d": -0.05,
            "bb_pct": 1.5,
            "vol_ratio": 1.8,
            "atr_ratio": 0.9,
            "macd_histogram": -0.5,
        }
        trace = generate_reasoning(annotations)
        assert trace.signal == -1
        assert "turun" in trace.explanation

    def test_neutral_signal(self):
        annotations = {
            "ma_crossover": 0.0,
            "rsi": 50.0,
            "momentum_5d": 0.0,
            "bb_pct": 0.0,
            "vol_ratio": 1.0,
            "atr_ratio": 1.0,
            "macd_histogram": 0.0,
        }
        trace = generate_reasoning(annotations)
        assert trace.signal == 0
        assert "datar" in trace.explanation

    def test_high_volatility_reduces_confidence(self):
        annotations_low_vol = {
            "ma_crossover": 5.0, "rsi": 55, "momentum_5d": 0.05,
            "bb_pct": 0.5, "vol_ratio": 1.0, "atr_ratio": 0.5,
            "macd_histogram": 0.5,
        }
        annotations_high_vol = {
            "ma_crossover": 5.0, "rsi": 55, "momentum_5d": 0.05,
            "bb_pct": 0.5, "vol_ratio": 1.0, "atr_ratio": 2.0,
            "macd_histogram": 0.5,
        }
        trace_low = generate_reasoning(annotations_low_vol)
        trace_high = generate_reasoning(annotations_high_vol)
        assert trace_high.confidence < trace_low.confidence


class TestVTAReasoningEngine:
    def test_analyze(self):
        ohlcv = _make_ohlcv(30, trend=0.5)
        engine = VTAReasoningEngine(lookback=20)
        trace = engine.analyze(ohlcv)
        assert isinstance(trace, ReasoningTrace)
        assert trace.signal in [-1, 0, 1]
        assert len(trace.explanation) > 0

    def test_insufficient_data(self):
        ohlcv = _make_ohlcv(3)
        engine = VTAReasoningEngine(lookback=20)
        trace = engine.analyze(ohlcv)
        assert trace.signal == 0
        assert "tidak cukup" in trace.explanation

    def test_generate_signal_series(self):
        ohlcv = _make_ohlcv(50, trend=0.3)
        engine = VTAReasoningEngine(lookback=20)
        signals = engine.generate_signal_series(ohlcv)
        assert len(signals) == 50
        assert signals.iloc[:20].sum() == 0  # No signal before lookback
        assert signals.isin([-1, 0, 1]).all()

    def test_explanation_contains_indicators(self):
        ohlcv = _make_ohlcv(30, trend=0.5)
        engine = VTAReasoningEngine(lookback=20)
        trace = engine.analyze(ohlcv)
        # Explanation or reasoning should mention at least one indicator
        text = trace.explanation + " " + trace.reasoning
        assert any(kw in text for kw in ["MA", "RSI", "momentum", "MACD", "BB", "Volume", "No clear"])
