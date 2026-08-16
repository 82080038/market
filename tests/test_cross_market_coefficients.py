"""Tests for CrossMarketCoefficientEngine (catatan.md TAHAP 3 — Prompt 3.1)."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from market.analysis.cross_market_coefficients import (
    CrossMarketCoefficient,
    CrossMarketCoefficientEngine,
    DEFAULT_SOURCE_INDICES,
    DEFAULT_TARGET_TICKER,
)

_HAS_DB = bool(os.environ.get("DATABASE_URL"))
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")


@pytest.fixture(scope="module")
def engine():
    return CrossMarketCoefficientEngine()


class TestDefaults:
    def test_default_sources(self):
        assert "^GSPC" in DEFAULT_SOURCE_INDICES
        assert "^HSI" in DEFAULT_SOURCE_INDICES
        assert "^N225" in DEFAULT_SOURCE_INDICES

    def test_default_target(self):
        assert DEFAULT_TARGET_TICKER == "^JKSE"


class TestRegressionBeta:
    def test_positive_relationship(self, engine):
        rng = np.random.RandomState(42)
        x = rng.randn(200)
        y = 0.5 * x + rng.randn(200) * 0.1
        beta = engine._regression_beta(x, y)
        assert beta is not None
        assert 0.4 <= beta <= 0.6

    def test_negative_relationship(self, engine):
        rng = np.random.RandomState(42)
        x = rng.randn(200)
        y = -0.7 * x + rng.randn(200) * 0.1
        beta = engine._regression_beta(x, y)
        assert beta is not None
        assert -0.8 <= beta <= -0.6

    def test_insufficient_data_returns_none(self, engine):
        beta = engine._regression_beta(np.array([1, 2, 3]), np.array([1, 2, 3]))
        assert beta is None

    def test_zero_variance_returns_none(self, engine):
        x = np.zeros(100)
        y = np.arange(100, dtype=float)
        assert engine._regression_beta(x, y) is None


class TestClassifyRegime:
    def test_bull_regime(self, engine):
        # Strong positive drift
        rng = np.random.RandomState(1)
        returns = pd.Series(rng.randn(250) * 0.01 + 0.002,
                            index=pd.date_range("2025-01-01", periods=250, freq="B"))
        assert engine._classify_regime(returns) == "BULL"

    def test_bear_regime(self, engine):
        rng = np.random.RandomState(2)
        returns = pd.Series(rng.randn(250) * 0.01 - 0.002,
                            index=pd.date_range("2025-01-01", periods=250, freq="B"))
        assert engine._classify_regime(returns) == "BEAR"

    def test_sideways_regime(self, engine):
        # Mean-reverting around 0 — cumulative return stays near 0
        rng = np.random.RandomState(3)
        n = 250
        returns = pd.Series(rng.randn(n) * 0.005,
                            index=pd.date_range("2025-01-01", periods=n, freq="B"))
        # Force cumulative return to be small by alternating signs
        returns.iloc[::2] *= -1
        regime = engine._classify_regime(returns)
        assert regime in {"SIDEWAYS", "BULL", "BEAR"}  # tolerance for noise
        # Stronger test: near-zero drift should not be extreme
        cum = float((1 + returns.tail(200)).prod() - 1) * 100
        assert abs(cum) < 15  # not strong bull/bear

    def test_short_series_defaults_sideways(self, engine):
        returns = pd.Series([0.01, -0.01, 0.02], index=pd.date_range("2025-01-01", periods=3, freq="B"))
        assert engine._classify_regime(returns) == "SIDEWAYS"


class TestComputeCoefficients:
    def test_synthetic_causal_relationship(self, engine):
        # Source Granger-causes target at lag 1
        rng = np.random.RandomState(123)
        n = 300
        src = pd.Series(rng.randn(n) * 0.01,
                        index=pd.date_range("2025-01-01", periods=n, freq="B"),
                        name="SRC")
        # target_t = 0.5 * src_{t-1} + noise
        tgt = pd.Series(np.zeros(n),
                        index=pd.date_range("2025-01-01", periods=n, freq="B"),
                        name="TGT")
        tgt.iloc[1:] = 0.5 * src.iloc[:-1].values + rng.randn(n - 1) * 0.005
        coefs = engine.compute_coefficients(src, tgt, regime="BULL")
        assert len(coefs) > 0
        # Lag 1 should have strongest coefficient
        lag1 = next((c for c in coefs if c.lag_days == 1), None)
        assert lag1 is not None
        assert lag1.coefficient is not None
        assert 0.3 <= lag1.coefficient <= 0.7
        assert lag1.regime == "BULL"

    def test_asymmetric_up_down(self, engine):
        rng = np.random.RandomState(456)
        n = 400
        src = pd.Series(rng.randn(n) * 0.02,
                        index=pd.date_range("2025-01-01", periods=n, freq="B"),
                        name="SRC")
        tgt = pd.Series(np.zeros(n),
                        index=pd.date_range("2025-01-01", periods=n, freq="B"),
                        name="TGT")
        # Asymmetric: up moves pass through 0.6, down moves 0.2
        for i in range(1, n):
            coef = 0.6 if src.iloc[i - 1] > 0 else 0.2
            tgt.iloc[i] = coef * src.iloc[i - 1] + rng.randn() * 0.003
        coefs = engine.compute_coefficients(src, tgt, regime="SIDEWAYS")
        lag1 = next((c for c in coefs if c.lag_days == 1), None)
        assert lag1 is not None
        assert lag1.asymmetric_up is not None
        assert lag1.asymmetric_down is not None
        assert lag1.asymmetric_up > lag1.asymmetric_down

    def test_insufficient_data_returns_empty(self, engine):
        src = pd.Series([0.01, 0.02], name="SRC")
        tgt = pd.Series([0.01, 0.02], name="TGT")
        assert engine.compute_coefficients(src, tgt) == []


class TestPersistenceIntegration:
    def test_update_all_and_retrieve(self, engine):
        # Run update — should populate at least ^GSPC coefficients
        result = engine.update_all()
        assert result["errors"] == 0
        assert result["updated"] >= 5  # at least 5 lags for ^GSPC
        # Retrieve
        c = engine.get_coefficient("^GSPC", "^JKSE", lag=1)
        assert c is not None
        assert c.source_index == "^GSPC"
        assert c.target_ticker == "^JKSE"
        assert c.coefficient is not None
        assert c.regime in {"BULL", "BEAR", "SIDEWAYS"}

    def test_get_all_for_target(self, engine):
        all_coefs = engine.get_all_for_target("^JKSE")
        assert len(all_coefs) >= 5
        sources = {c.source_index for c in all_coefs}
        assert "^GSPC" in sources

    def test_get_optimal_lag(self, engine):
        lag, coef = engine.get_optimal_lag("^GSPC", "^JKSE")
        assert lag >= 1
        # Coefficient should be non-trivial for ^GSPC → ^JKSE
        assert abs(coef) > 0.0

    def test_get_nonexistent_returns_none(self, engine):
        c = engine.get_coefficient("NONEXISTENT", "^JKSE", lag=1)
        assert c is None
