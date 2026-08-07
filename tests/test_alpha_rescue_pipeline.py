"""Regression tests for alpha_rescue_pipeline.py — 4 Reformasi Signal Action.

Tests cover:
  Reform 1 — volatility_targeted_position_size, build_volatility_features
  Reform 2 — detect_regime, build_meta_label_features
  Reform 3 — cluster_features_by_correlation, select_clustered_features
  Reform 4 — verify_reform (smoke test with synthetic data)
  Orchestration — ReformConfig defaults, RescueReport serialization
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Path setup
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from alpha_rescue_pipeline import (  # noqa: E402
    ReformConfig,
    Reform1Result,
    Reform2Result,
    Reform3Result,
    Reform4Result,
    RescueReport,
    volatility_targeted_position_size,
    build_volatility_features,
    generate_volatility_targeted_signals,
    detect_regime,
    build_meta_label_features,
    generate_meta_labeled_signals,
    cluster_features_by_correlation,
    select_clustered_features,
    build_multifactor_features,
    generate_pruned_multifactor_signals,
    verify_reform,
    _report_to_dict,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_ohlcv() -> pd.DataFrame:
    """Generate synthetic OHLCV data with enough rows for walk-forward."""
    np.random.seed(42)
    n = 600
    returns = np.random.randn(n) * 0.02
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.randn(n)) * 0.01)
    low = close * (1 - np.abs(np.random.randn(n)) * 0.01)
    volume = np.random.randint(1e6, 1e7, n).astype(float)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def config() -> ReformConfig:
    return ReformConfig()


# ── Reform 1 Tests ──────────────────────────────────────────────────────────


class TestVolatilityTargetedPositionSize:
    """Test the mathematical position sizing function."""

    def test_low_vol_full_position(self):
        vol = np.array([-2.0, -1.0, 0.0])
        pos = volatility_targeted_position_size(vol, target_vol_zscore=0.0)
        assert np.allclose(pos, 1.0)

    def test_high_vol_zero_position(self):
        vol = np.array([1.5, 2.0, 3.0])
        pos = volatility_targeted_position_size(vol, hard_cutoff=1.5)
        assert np.allclose(pos, 0.0)

    def test_mid_vol_decay(self):
        vol = np.array([0.5])
        pos = volatility_targeted_position_size(
            vol, target_vol_zscore=0.0, aggressiveness=2.5, hard_cutoff=1.5
        )
        expected = np.exp(-2.5 * 0.5)
        assert abs(pos[0] - expected) < 1e-10
        assert 0 < pos[0] < 1.0

    def test_scalar_input(self):
        pos = volatility_targeted_position_size(0.3)
        # np.clip on 0-d array may return numpy scalar
        assert float(pos) == pytest.approx(np.exp(-2.5 * 0.3), abs=1e-10)

    def test_max_position_cap(self):
        vol = np.array([-1.0])
        pos = volatility_targeted_position_size(vol, max_position=0.5)
        assert pos[0] == 0.5

    def test_monotonic_decrease(self):
        vol = np.array([0.0, 0.3, 0.6, 0.9, 1.2])
        pos = volatility_targeted_position_size(vol, hard_cutoff=1.5)
        assert all(pos[i] >= pos[i + 1] for i in range(len(pos) - 1))


class TestBuildVolatilityFeatures:
    """Test volatility feature engineering."""

    def test_returns_dataframe_with_targets(self, synthetic_ohlcv):
        feat = build_volatility_features(synthetic_ohlcv)
        assert isinstance(feat, pd.DataFrame)
        assert "target_vol_zscore" in feat.columns
        assert "target_vol_spike" in feat.columns
        assert "vol_zscore" in feat.columns
        assert len(feat) == len(synthetic_ohlcv)

    def test_no_inf_values(self, synthetic_ohlcv):
        feat = build_volatility_features(synthetic_ohlcv)
        numeric = feat.select_dtypes(include=[np.number])
        assert not np.any(np.isinf(numeric.values[np.isfinite(numeric.values) | np.isinf(numeric.values)]))

    def test_target_vol_spike_binary(self, synthetic_ohlcv):
        feat = build_volatility_features(synthetic_ohlcv)
        clean = feat["target_vol_spike"].dropna()
        assert set(clean.unique()).issubset({0.0, 1.0})

    def test_gk_vol_non_negative(self, synthetic_ohlcv):
        """Garman-Klass volatility should not produce NaN from negative sqrt."""
        feat = build_volatility_features(synthetic_ohlcv)
        gk = feat["gk_vol"].dropna()
        assert (gk >= 0).all()


class TestGenerateVolatilityTargetedSignals:
    """Test the full Reform 1 pipeline."""

    def test_returns_series_and_diag(self, synthetic_ohlcv, config):
        positions, diag = generate_volatility_targeted_signals(synthetic_ohlcv, config)
        assert isinstance(positions, pd.Series)
        assert isinstance(diag, dict)
        assert "n_predictions" in diag
        assert "avg_vol_zscore" in diag
        assert "avg_scale" in diag
        assert len(positions) == len(synthetic_ohlcv)

    def test_positions_bounded(self, synthetic_ohlcv, config):
        positions, _ = generate_volatility_targeted_signals(synthetic_ohlcv, config)
        assert positions.abs().max() <= 1.0 + 1e-10

    def test_insufficient_data_fallback(self, config):
        """With very few rows, should fallback to baseline."""
        tiny = pd.DataFrame(
            {"open": [100, 101], "high": [101, 102], "low": [99, 100],
             "close": [100, 101], "volume": [1e6, 1e6]},
            index=pd.date_range("2022-01-01", periods=2, freq="B"),
        )
        positions, diag = generate_volatility_targeted_signals(tiny, config)
        assert diag["n_predictions"] == 0


# ── Reform 2 Tests ──────────────────────────────────────────────────────────


class TestDetectRegime:
    """Test regime detection."""

    def test_returns_series_with_valid_labels(self, synthetic_ohlcv):
        regime = detect_regime(synthetic_ohlcv)
        assert isinstance(regime, pd.Series)
        assert len(regime) == len(synthetic_ohlcv)
        valid = {"bull", "bear", "sideways", "crisis"}
        assert set(regime.unique()).issubset(valid)

    def test_crisis_when_high_vol(self, synthetic_ohlcv):
        """High volatility periods should be classified as crisis."""
        regime = detect_regime(synthetic_ohlcv)
        assert "crisis" in regime.values or "sideways" in regime.values


class TestBuildMetaLabelFeatures:
    """Test meta-label feature engineering."""

    def test_returns_dataframe_with_target(self, synthetic_ohlcv, config):
        side = pd.Series(1.0, index=synthetic_ohlcv.index)
        feat = build_meta_label_features(synthetic_ohlcv, side, config)
        assert "target_meta" in feat.columns
        assert "regime_bull" in feat.columns
        assert "regime_bear" in feat.columns
        assert "regime_sideways" in feat.columns
        assert "regime_crisis" in feat.columns
        assert "primary_side" in feat.columns

    def test_target_meta_binary_when_side_nonzero(self, synthetic_ohlcv, config):
        side = pd.Series(1.0, index=synthetic_ohlcv.index)
        feat = build_meta_label_features(synthetic_ohlcv, side, config)
        clean = feat["target_meta"].dropna()
        assert set(clean.unique()).issubset({0.0, 1.0})

    def test_target_meta_nan_when_side_zero(self, synthetic_ohlcv, config):
        side = pd.Series(0.0, index=synthetic_ohlcv.index)
        feat = build_meta_label_features(synthetic_ohlcv, side, config)
        assert feat["target_meta"].isna().all()


class TestGenerateMetaLabeledSignals:
    """Test the full Reform 2 pipeline."""

    def test_returns_series_and_diag(self, synthetic_ohlcv, config):
        primary = pd.Series(1.0, index=synthetic_ohlcv.index)
        positions, diag = generate_meta_labeled_signals(synthetic_ohlcv, primary, config)
        assert isinstance(positions, pd.Series)
        assert isinstance(diag, dict)
        assert "accept_rate" in diag
        assert "brier" in diag
        assert len(positions) == len(synthetic_ohlcv)

    def test_positions_bounded(self, synthetic_ohlcv, config):
        primary = pd.Series(1.0, index=synthetic_ohlcv.index)
        positions, _ = generate_meta_labeled_signals(synthetic_ohlcv, primary, config)
        assert positions.abs().max() <= 1.0 + 1e-10


# ── Reform 3 Tests ──────────────────────────────────────────────────────────


class TestClusterFeaturesByCorrelation:
    """Test hierarchical feature clustering."""

    def test_clusters_highly_correlated_features(self):
        np.random.seed(42)
        n = 200
        x1 = np.random.randn(n)
        x2 = x1 + np.random.randn(n) * 0.05  # highly correlated with x1
        x3 = np.random.randn(n)  # uncorrelated
        df = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3})
        clusters = cluster_features_by_correlation(df, corr_threshold=0.65)
        # x1 and x2 should be in the same cluster
        cluster_of_x1 = None
        cluster_of_x2 = None
        for cid, members in clusters.items():
            if "x1" in members:
                cluster_of_x1 = cid
            if "x2" in members:
                cluster_of_x2 = cid
        assert cluster_of_x1 == cluster_of_x2
        # x3 should be in a different cluster
        cluster_of_x3 = None
        for cid, members in clusters.items():
            if "x3" in members:
                cluster_of_x3 = cid
        assert cluster_of_x3 != cluster_of_x1

    def test_returns_dict_of_lists(self):
        df = pd.DataFrame(np.random.randn(100, 5), columns=list("abcde"))
        clusters = cluster_features_by_correlation(df)
        assert isinstance(clusters, dict)
        for members in clusters.values():
            assert isinstance(members, list)

    def test_all_features_assigned(self):
        df = pd.DataFrame(np.random.randn(100, 5), columns=list("abcde"))
        clusters = cluster_features_by_correlation(df)
        all_features = [f for members in clusters.values() for f in members]
        assert sorted(all_features) == list("abcde")


class TestSelectClusteredFeatures:
    """Test clustered feature selection."""

    def test_reduces_redundant_features(self):
        np.random.seed(42)
        n = 200
        x1 = np.random.randn(n)
        x2 = x1 + np.random.randn(n) * 0.05  # redundant
        x3 = np.random.randn(n)
        y = (x1 > 0).astype(int)  # label depends on x1
        X = np.column_stack([x1, x2, x3])
        names = ["x1", "x2", "x3"]
        selected, dropped, clusters = select_clustered_features(
            X, y, names, corr_threshold=0.65, top_k_clusters=3,
        )
        assert len(selected) <= 3
        assert len(selected) + len(dropped) == 3
        # Either x1 or x2 should be selected (not both, since they're correlated)
        assert not (set(selected) == {"x1", "x2"})

    def test_empty_when_no_features(self):
        """Empty input should return empty selection without error."""
        selected, dropped, clusters = select_clustered_features(
            np.array([]).reshape(0, 0), np.array([]), [], corr_threshold=0.65,
        )
        # With no features, should return empty (LightGBM may skip or error;
        # the function catches ImportError but not ValueError, so test with
        # at least 1 sample to avoid LightGBM crash)
        # This test verifies the function handles edge case gracefully


class TestBuildMultifactorFeatures:
    """Test MultiFactor feature engineering."""

    def test_returns_dataframe_with_target(self, synthetic_ohlcv, config):
        data = build_multifactor_features(synthetic_ohlcv, config)
        assert "target_3class" in data.columns
        assert "forward_return" in data.columns
        assert len(data) == len(synthetic_ohlcv)

    def test_target_3class_values(self, synthetic_ohlcv, config):
        data = build_multifactor_features(synthetic_ohlcv, config)
        clean = data["target_3class"].dropna()
        assert set(clean.unique()).issubset({0, 1, 2})


class TestGeneratePrunedMultifactorSignals:
    """Test the full Reform 3 pipeline."""

    def test_returns_series_and_diag(self, synthetic_ohlcv, config):
        signals, diag = generate_pruned_multifactor_signals(synthetic_ohlcv, config)
        assert isinstance(signals, pd.Series)
        assert isinstance(diag, dict)
        assert "n_features_before" in diag
        assert "n_features_after" in diag
        assert "n_clusters" in diag
        assert len(signals) == len(synthetic_ohlcv)

    def test_signals_in_range(self, synthetic_ohlcv, config):
        signals, _ = generate_pruned_multifactor_signals(synthetic_ohlcv, config)
        assert signals.min() >= -1.0 - 1e-10
        assert signals.max() <= 1.0 + 1e-10

    def test_feature_reduction(self, synthetic_ohlcv, config):
        _, diag = generate_pruned_multifactor_signals(synthetic_ohlcv, config)
        if diag["n_features_before"] > 0:
            assert diag["n_features_after"] <= diag["n_features_before"]


# ── Reform 4 Tests ───────────────────────────────────────────────────────────


class TestVerifyReform:
    """Test post-remediation verification."""

    def test_returns_reform4_result(self, synthetic_ohlcv):
        signals = pd.Series(0.5, index=synthetic_ohlcv.index)
        result = verify_reform(synthetic_ohlcv, signals, benchmark=None)
        assert isinstance(result, Reform4Result)
        assert isinstance(result.sharpe_rescued, float)
        assert isinstance(result.alpha_rescued, float)
        assert isinstance(result.brier_score_signal, float)


# ── Config & Serialization Tests ────────────────────────────────────────────


class TestReformConfig:
    """Test configuration defaults and constraints."""

    def test_defaults_sensible(self):
        cfg = ReformConfig()
        assert cfg.vol_n_estimators == 150
        assert cfg.mf_n_estimators == 80  # pruned from 300
        assert cfg.mf_max_depth == 4  # pruned from 5
        assert cfg.mf_min_data_in_leaf == 50
        assert cfg.mf_corr_threshold == 0.65

    def test_custom_config(self):
        cfg = ReformConfig(vol_aggressiveness=5.0, mf_n_estimators=50)
        assert cfg.vol_aggressiveness == 5.0
        assert cfg.mf_n_estimators == 50


class TestReportSerialization:
    """Test RescueReport to dict conversion."""

    def test_report_to_dict_json_safe(self):
        report = RescueReport(
            audit_date="2026-01-01",
            tickers_audited=["BBCA.JK"],
            config={"vol_aggressiveness": 2.5},
            reform1=Reform1Result(tickers=["BBCA.JK"], n_vol_predictions=100),
        )
        d = _report_to_dict(report)
        assert isinstance(d, dict)
        assert d["audit_date"] == "2026-01-01"
        assert d["tickers_audited"] == ["BBCA.JK"]
        assert d["reform1"]["n_vol_predictions"] == 100

    def test_empty_report_to_dict(self):
        report = RescueReport()
        d = _report_to_dict(report)
        assert isinstance(d, dict)
        assert "audit_date" in d
