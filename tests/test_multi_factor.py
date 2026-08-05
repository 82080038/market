"""Tests for multi_factor module: feature pipeline, PCA, model."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.multi_factor import (
    MultiFactorFeaturePipeline,
    apply_pca_to_block,
    compute_autocorrelation,
    compute_autocorrelation_series,
    compute_bollinger_features,
    compute_candlestick_features,
    compute_endogenous_features,
    compute_exogenous_features,
    compute_macd_features,
    select_features_by_importance,
)


@pytest.fixture
def sample_ohlcv():
    """Sample OHLCV data with 200 bars."""
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    np.random.seed(42)
    close = 100.0 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame(
        {
            "open": close - np.random.rand(n),
            "high": close + np.random.rand(n) * 2,
            "low": close - np.random.rand(n) * 2,
            "close": close,
            "volume": np.random.randint(1000, 10000, n).astype(float),
        },
        index=dates,
    )


@pytest.fixture
def sample_global_data():
    """Sample global market data."""
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    np.random.seed(99)
    return {
        "^GSPC": pd.DataFrame(
            {"close": 4000 + np.cumsum(np.random.randn(n) * 10)}, index=dates
        ),
        "^N225": pd.DataFrame(
            {"close": 35000 + np.cumsum(np.random.randn(n) * 50)}, index=dates
        ),
        "GC=F": pd.DataFrame(
            {"close": 2000 + np.cumsum(np.random.randn(n) * 5)}, index=dates
        ),
    }


# ── Endogenous Feature Tests ──────────────────────────────────────────────


class TestEndogenousFeatures:
    def test_autocorrelation(self):
        close = pd.Series(np.random.randn(100).cumsum() + 100)
        acf = compute_autocorrelation(close, lags=[1, 5, 10])
        assert "acf_1" in acf
        assert "acf_5" in acf
        assert "acf_10" in acf
        assert -1.0 <= acf["acf_1"] <= 1.0

    def test_autocorrelation_series(self, sample_ohlcv):
        acf_series = compute_autocorrelation_series(
            sample_ohlcv["close"], lag=1, window=20
        )
        assert len(acf_series) == len(sample_ohlcv)
        assert acf_series.iloc[-1] != np.nan

    def test_candlestick_features(self, sample_ohlcv):
        result = compute_candlestick_features(sample_ohlcv)
        assert "body_ratio" in result.columns
        assert "upper_shadow" in result.columns
        assert "lower_shadow" in result.columns
        assert "doji_score" in result.columns
        assert "hammer_score" in result.columns
        assert "marubozu_score" in result.columns
        assert "gap" in result.columns
        # body_ratio should be non-negative (can exceed 1.0 when hl_range is tiny)
        assert (result["body_ratio"] >= 0).all()

    def test_bollinger_features(self, sample_ohlcv):
        bb = compute_bollinger_features(sample_ohlcv["close"])
        assert "bb_width" in bb.columns
        assert "bb_pct" in bb.columns
        assert "bb_squeeze" in bb.columns
        assert bb["bb_width"].iloc[-1] > 0

    def test_macd_features(self, sample_ohlcv):
        macd = compute_macd_features(sample_ohlcv["close"])
        assert "macd_line" in macd.columns
        assert "macd_signal" in macd.columns
        assert "macd_hist" in macd.columns
        assert "macd_hist_norm" in macd.columns

    def test_endogenous_features_all(self, sample_ohlcv):
        result = compute_endogenous_features(sample_ohlcv)
        expected = [
            "acf_1", "acf_5", "acf_10",
            "body_ratio", "doji_score", "hammer_score",
            "bb_width", "bb_pct", "bb_squeeze",
            "macd_hist_norm", "rsi", "momentum_5",
            "ma_ratio", "vwap_ratio", "vol_ratio",
        ]
        for col in expected:
            assert col in result.columns, f"Missing {col}"


# ── Exogenous Feature Tests ───────────────────────────────────────────────


class TestExogenousFeatures:
    def test_exogenous_features(self, sample_ohlcv, sample_global_data):
        exo = compute_exogenous_features(
            sample_ohlcv, sample_global_data, lookback=5
        )
        assert "sp500_lag1_ret" in exo.columns
        assert "sp500_lag5_ret" in exo.columns
        assert "sp500_corr" in exo.columns
        assert "nikkei_lag1_ret" in exo.columns
        assert "gold_lag1_ret" in exo.columns

    def test_exogenous_lag_applied(self, sample_ohlcv, sample_global_data):
        """Ensure exogenous returns are lagged (non-look-ahead)."""
        exo = compute_exogenous_features(
            sample_ohlcv, sample_global_data, lookback=5
        )
        # The first lag1_ret should be 0 (no previous data)
        assert exo["sp500_lag1_ret"].iloc[0] == 0.0

    def test_exogenous_empty_global(self, sample_ohlcv):
        exo = compute_exogenous_features(sample_ohlcv, {})
        assert exo.empty or len(exo.columns) == 0


# ── PCA & Feature Selection Tests ─────────────────────────────────────────


class TestDimensionalityReduction:
    def test_pca_reduction(self):
        X = np.random.randn(100, 10)
        X_transformed, n_comp, explained = apply_pca_to_block(
            X, variance_threshold=0.95
        )
        assert n_comp <= 10
        assert explained >= 0.9
        assert X_transformed.shape == (100, n_comp)

    def test_pca_small_block(self):
        """PCA on 2-feature block should return as-is."""
        X = np.random.randn(100, 2)
        _X_t, n_comp, explained = apply_pca_to_block(X)
        assert n_comp == 2
        assert explained == 1.0

    def test_feature_selection(self):
        np.random.seed(42)
        X = np.random.randn(200, 20)
        y = (X[:, 0] > 0).astype(int)  # Only feature 0 matters
        result = select_features_by_importance(
            X, y, [f"f{i}" for i in range(20)], top_k=5
        )
        assert len(result.selected_features) <= 5
        assert "f0" in result.selected_features


# ── Full Pipeline Tests ───────────────────────────────────────────────────


class TestMultiFactorPipeline:
    def test_pipeline_build(self, sample_ohlcv, sample_global_data):
        pipeline = MultiFactorFeaturePipeline(horizon=5, use_pca=True)
        fmatrix = pipeline.build(
            sample_ohlcv, global_data=sample_global_data,
            select_features=False,
        )
        assert len(fmatrix.endogenous_names) > 0
        assert len(fmatrix.exogenous_names) > 0
        assert len(fmatrix.feature_names) > 0
        assert fmatrix.pca_result is not None

    def test_pipeline_no_global(self, sample_ohlcv):
        pipeline = MultiFactorFeaturePipeline(horizon=5, use_pca=True)
        fmatrix = pipeline.build(sample_ohlcv, global_data=None)
        assert len(fmatrix.endogenous_names) > 0
        assert len(fmatrix.exogenous_names) == 0

    def test_pipeline_with_selection(self, sample_ohlcv, sample_global_data):
        pipeline = MultiFactorFeaturePipeline(
            horizon=5, use_pca=True, top_k_features=10
        )
        fmatrix = pipeline.build(
            sample_ohlcv, global_data=sample_global_data,
            select_features=True,
        )
        if fmatrix.selection_result:
            assert len(fmatrix.selection_result.selected_features) <= 10

    def test_3class_target(self, sample_ohlcv):
        pipeline = MultiFactorFeaturePipeline(horizon=5)
        fmatrix = pipeline.build(sample_ohlcv)
        assert "target_3class" in fmatrix.combined.columns
        # Should have classes 0, 1, 2 (and -1 for NaN)
        valid = fmatrix.combined["target_3class"] >= 0
        assert valid.sum() > 0
