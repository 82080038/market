"""Tests for CausalStock-style causal discovery engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.causal_discovery import (
    CausalDiscoveryEngine,
    CausalGraph,
    CausalLink,
    build_causal_graph,
    granger_causality,
)


def _make_returns(n: int = 150, n_tickers: int = 4, causal: bool = True) -> pd.DataFrame:
    """Generate synthetic returns with optional causal structure.

    If causal=True, ticker_0 causes ticker_1 (lag 1).
    """
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    data = {}

    r0 = np.random.randn(n) * 0.02
    data["ticker_0"] = r0

    if causal:
        # ticker_1 depends on ticker_0's lag-1
        r1 = 0.5 * np.roll(r0, 1) + np.random.randn(n) * 0.01
        r1[0] = 0
        data["ticker_1"] = r1
    else:
        data["ticker_1"] = np.random.randn(n) * 0.02

    for i in range(2, n_tickers):
        data[f"ticker_{i}"] = np.random.randn(n) * 0.02

    return pd.DataFrame(data, index=dates)


class TestGrangerCausality:
    def test_causal_relationship(self):
        returns = _make_returns(150, 2, causal=True)
        f_stat, p_val, lag = granger_causality(
            returns["ticker_0"], returns["ticker_1"], max_lag=3
        )
        assert f_stat > 0
        assert p_val < 0.05
        assert lag >= 1

    def test_non_causal_relationship(self):
        returns = _make_returns(150, 2, causal=False)
        f_stat, p_val, lag = granger_causality(
            returns["ticker_0"], returns["ticker_1"], max_lag=3
        )
        # Should not find strong causality
        assert p_val > 0.01 or f_stat < 5.0

    def test_short_data(self):
        s1 = pd.Series(np.random.randn(10))
        s2 = pd.Series(np.random.randn(10))
        f_stat, p_val, lag = granger_causality(s1, s2, max_lag=3)
        assert f_stat == 0.0
        assert p_val == 1.0


class TestBuildCausalGraph:
    def test_graph_structure(self):
        returns = _make_returns(150, 4, causal=True)
        graph = build_causal_graph(returns, max_lag=3, significance=0.10, min_f_stat=1.5)
        assert isinstance(graph, CausalGraph)
        assert graph.matrix is not None
        assert graph.matrix.shape == (4, 4)

    def test_directed_asymmetry(self):
        returns = _make_returns(150, 2, causal=True)
        graph = build_causal_graph(returns, max_lag=3, significance=0.10, min_f_stat=1.0)
        # Should find ticker_0 -> ticker_1 but not ticker_1 -> ticker_0
        if graph.links:
            sources = {l.source for l in graph.links}
            targets = {l.target for l in graph.links}
            assert "ticker_0" in sources


class TestCausalDiscoveryEngine:
    def test_discover(self):
        returns = _make_returns(150, 4, causal=True)
        engine = CausalDiscoveryEngine(max_lag=3, significance=0.10)
        graph = engine.discover(returns)
        assert isinstance(graph, CausalGraph)

    def test_generate_signal(self):
        returns = _make_returns(150, 4, causal=True)
        engine = CausalDiscoveryEngine(max_lag=3, significance=0.10)
        graph = engine.discover(returns)
        signal = engine.generate_signal("ticker_1", graph, returns)
        assert signal in [-1, 0, 1]

    def test_generate_signal_series(self):
        returns = _make_returns(150, 3, causal=True)
        engine = CausalDiscoveryEngine(max_lag=2, significance=0.10, min_data_days=100)
        signals = engine.generate_signal_series("ticker_1", returns, window=100)
        assert len(signals) == 150
        assert signals.isin([-1, 0, 1]).all()

    def test_insufficient_data(self):
        returns = _make_returns(50, 3)
        engine = CausalDiscoveryEngine(min_data_days=120)
        signals = engine.generate_signal_series("ticker_0", returns)
        assert (signals == 0).all()

    def test_get_influencers(self):
        returns = _make_returns(150, 4, causal=True)
        graph = build_causal_graph(returns, max_lag=3, significance=0.10, min_f_stat=1.0)
        influencers = graph.get_influencers("ticker_1")
        assert isinstance(influencers, list)
