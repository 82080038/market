"""Tests for SpilloverLab (full Diebold-Yilmaz) engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.spillover_lab import (
    SpilloverLabEngine,
    SpilloverTable,
    build_spillover_table,
)


def _make_returns(n: int = 150, n_tickers: int = 4) -> pd.DataFrame:
    """Generate synthetic returns data."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    data = {}
    for i in range(n_tickers):
        data[f"ticker_{i}"] = np.random.randn(n) * 0.02
    return pd.DataFrame(data, index=dates)


class TestSpilloverTable:
    def test_get_signal_no_ticker(self):
        table = SpilloverTable(
            from_to=pd.DataFrame(),
            to_others=pd.Series(dtype=float),
            from_others=pd.Series(dtype=float),
            net=pd.Series(dtype=float),
            total=50.0,
        )
        assert table.get_signal("nonexistent") == 0

    def test_get_signal_high_spillover(self):
        net = pd.Series({"BBCA": 70.0, "BBRI": -70.0})
        table = SpilloverTable(
            from_to=pd.DataFrame(),
            to_others=pd.Series(dtype=float),
            from_others=pd.Series(dtype=float),
            net=net,
            total=50.0,
        )
        # High positive NET → contagion risk → bearish
        assert table.get_signal("BBCA", high_threshold=60) == -1
        # High negative NET → receiver → bullish
        assert table.get_signal("BBRI", high_threshold=60) == 1

    def test_get_signal_total_contagion(self):
        net = pd.Series({"BBCA": 0.0})
        table = SpilloverTable(
            from_to=pd.DataFrame(),
            to_others=pd.Series(dtype=float),
            from_others=pd.Series(dtype=float),
            net=net,
            total=70.0,  # System-wide contagion
        )
        assert table.get_signal("BBCA", high_threshold=60) == -1

    def test_get_signal_total_decoupled(self):
        net = pd.Series({"BBCA": 0.0})
        table = SpilloverTable(
            from_to=pd.DataFrame(),
            to_others=pd.Series(dtype=float),
            from_others=pd.Series(dtype=float),
            net=net,
            total=20.0,  # System-wide decoupling
        )
        assert table.get_signal("BBCA", high_threshold=60, low_threshold=30) == 1


class TestBuildSpilloverTable:
    def test_basic(self):
        returns = _make_returns(150, 4)
        table = build_spillover_table(returns, lag_order=2, horizon=10)
        if table is not None:
            assert table.from_to.shape == (4, 4)
            assert len(table.to_others) == 4
            assert len(table.from_others) == 4
            assert len(table.net) == 4
            assert 0 <= table.total <= 100

    def test_short_data(self):
        returns = _make_returns(20, 3)
        table = build_spillover_table(returns, lag_order=2, horizon=10)
        assert table is None


class TestSpilloverLabEngine:
    def test_compute(self):
        returns = _make_returns(150, 4)
        engine = SpilloverLabEngine(lag_order=2, horizon=10)
        table = engine.compute(returns)
        if table is not None:
            assert isinstance(table, SpilloverTable)

    def test_generate_signal_series(self):
        returns = _make_returns(150, 3)
        engine = SpilloverLabEngine(lag_order=2, horizon=10, window=100, retest_interval=30)
        signals = engine.generate_signal_series("ticker_0", returns)
        assert len(signals) == 150
        assert signals.isin([-1, 0, 1]).all()

    def test_insufficient_data(self):
        returns = _make_returns(50, 3)
        engine = SpilloverLabEngine(window=120)
        signals = engine.generate_signal_series("ticker_0", returns)
        assert (signals == 0).all()
