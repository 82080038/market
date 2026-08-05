"""Tests for Relationship Engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.analysis.relationship import MarketRelationshipEngine


def _make_returns(n: int = 100, seed: int = 42) -> pd.Series:
    np.random.seed(seed)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.Series(np.random.normal(0.001, 0.02, n), index=dates)


def test_relationship_basic():
    engine = MarketRelationshipEngine()
    target = _make_returns(100, seed=42)
    refs = {
        "^GSPC": _make_returns(100, seed=10),
        "^JKSE": _make_returns(100, seed=20),
    }
    result = engine.analyze("BBCA.JK", target, refs, window=60)
    assert 0 <= result.score <= 100
    assert len(result.relationships) == 2
    assert result.window == 60


def test_relationship_empty_refs():
    engine = MarketRelationshipEngine()
    target = _make_returns(100)
    result = engine.analyze("TEST.JK", target, {})
    assert result.score == 0.0
    assert result.relationships == []


def test_relationship_empty_target():
    engine = MarketRelationshipEngine()
    result = engine.analyze(
        "EMPTY.JK", pd.Series(dtype=float), {"^GSPC": _make_returns(100)},
    )
    assert result.score == 0.0


def test_relationship_high_correlation():
    engine = MarketRelationshipEngine()
    target = _make_returns(100, seed=42)
    # Same seed → perfect correlation
    refs = {"^JKSE": _make_returns(100, seed=42)}
    result = engine.analyze("CORR.JK", target, refs, window=60)
    assert result.score > 50.0  # High correlation


def test_relationship_lag_detection():
    engine = MarketRelationshipEngine()
    n = 100
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    np.random.seed(42)
    base = np.random.normal(0.001, 0.02, n)
    target = pd.Series(base, index=dates)
    # Reference is target shifted by 2 days
    ref = pd.Series(np.roll(base, 2), index=dates)
    refs = {"^GSPC": ref}
    result = engine.analyze("LAG.JK", target, refs, window=60, max_lag=5)
    # Should detect some relationship
    assert len(result.relationships) == 1
    assert isinstance(result.relationships[0]["lag"], int)
