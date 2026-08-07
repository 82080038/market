"""Tests for feature_drift_remediation.py and signal_matrix_alignment.py.

Tests cover:
- PSI computation and drift classification
- Exponential decay weighting
- Regime-aware weighting boost
- Quant-Safe Imputation (forward fill with limit, no bfill)
- Signal alignment and merge
- Data leakage audit
- Target computation post-alignment
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ── Imports from scripts ───────────────────────────────────────────────────

from scripts.feature_drift_remediation import (
    population_stability_index,
    classify_drift,
    compute_exponential_weights,
    apply_regime_aware_weighting,
    get_remediation_actions,
    audit_feature_drift,
    compute_features_from_ohlcv,
    FeatureDriftResult,
)
from scripts.signal_matrix_alignment import (
    quant_safe_imputation,
    align_signals,
    compute_targets_post_alignment,
    audit_data_leakage,
    ML_BLEND_WEIGHT,
    MF_BLEND_WEIGHT,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate synthetic OHLCV data for 300 trading days."""
    np.random.seed(42)
    n = 300
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = 10000 + np.cumsum(np.random.randn(n) * 50)
    close = np.maximum(close, 1000)
    high = close * (1 + np.abs(np.random.randn(n)) * 0.01)
    low = close * (1 - np.abs(np.random.randn(n)) * 0.01)
    volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)

    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=pd.DatetimeIndex(dates),
    )


@pytest.fixture
def sample_features(sample_ohlcv) -> pd.DataFrame:
    """Compute features from sample OHLCV."""
    return compute_features_from_ohlcv(sample_ohlcv)


@pytest.fixture
def sample_regimes() -> pd.DataFrame:
    """Generate synthetic regime labels."""
    dates = pd.bdate_range("2024-01-01", periods=300)
    regimes = ["bull"] * 100 + ["sideways"] * 100 + ["bear"] * 100
    return pd.DataFrame(
        {"regime": regimes},
        index=pd.DatetimeIndex(dates),
    )


# ── Tests: PSI Computation ────────────────────────────────────────────────


class TestPSI:
    def test_psi_identical_distributions(self):
        """PSI of identical distributions should be near zero."""
        data = np.random.randn(500)
        psi = population_stability_index(data, data)
        assert psi < 0.01, f"PSI should be ~0 for identical dist, got {psi}"

    def test_psi_shifted_distributions(self):
        """PSI of shifted distributions should be high."""
        ref = np.random.randn(500)
        cur = np.random.randn(500) + 3  # Large shift
        psi = population_stability_index(ref, cur)
        assert psi > 0.25, f"PSI should be >0.25 for shifted dist, got {psi}"

    def test_psi_moderate_shift(self):
        """PSI of moderately shifted distributions should be in moderate range."""
        ref = np.random.randn(500)
        cur = np.random.randn(500) + 0.5  # Moderate shift
        psi = population_stability_index(ref, cur)
        assert 0.05 < psi < 0.5, f"PSI should be moderate, got {psi}"

    def test_classify_drift_stable(self):
        assert classify_drift(0.05) == "stable"

    def test_classify_drift_moderate(self):
        assert classify_drift(0.15) == "moderate"

    def test_classify_drift_drifted(self):
        assert classify_drift(0.30) == "drifted"


# ── Tests: Exponential Weighting ──────────────────────────────────────────


class TestExponentialWeights:
    def test_weights_sum_to_one(self):
        """Normalized weights must sum to 1."""
        dates = pd.bdate_range("2024-01-01", periods=100)
        weights = compute_exponential_weights(dates, lambda_decay=0.02)
        assert abs(weights.sum() - 1.0) < 1e-10, f"Sum={weights.sum()}"

    def test_recent_higher_weight(self):
        """Most recent date should have highest weight."""
        dates = pd.bdate_range("2024-01-01", periods=100)
        weights = compute_exponential_weights(dates, lambda_decay=0.02)
        assert weights[-1] == weights.max(), "Last date should have max weight"

    def test_empty_dates(self):
        """Empty dates should return empty array."""
        weights = compute_exponential_weights(pd.DatetimeIndex([]), 0.02)
        assert len(weights) == 0

    def test_higher_lambda_decays_faster(self):
        """Higher lambda should decay faster (lower weight for old data)."""
        dates = pd.bdate_range("2024-01-01", periods=100)
        w_low = compute_exponential_weights(dates, lambda_decay=0.01)
        w_high = compute_exponential_weights(dates, lambda_decay=0.10)
        # Weight of first observation should be much smaller with high lambda
        assert w_high[0] < w_low[0], "High lambda should give less weight to old data"


# ── Tests: Regime-Aware Weighting ─────────────────────────────────────────


class TestRegimeAwareWeighting:
    def test_sample_weight_column_exists(self, sample_features):
        """Output should have 'sample_weight' column."""
        result = apply_regime_aware_weighting(sample_features, lambda_decay=0.02)
        assert "sample_weight" in result.columns

    def test_weights_sum_to_one(self, sample_features):
        """Sample weights should sum to 1."""
        result = apply_regime_aware_weighting(sample_features, lambda_decay=0.02)
        assert abs(result["sample_weight"].sum() - 1.0) < 1e-10

    def test_regime_boost_increases_weight(self, sample_features, sample_regimes):
        """Regime boost should increase weight for same-regime rows."""
        result_no_boost = apply_regime_aware_weighting(
            sample_features, lambda_decay=0.02, regimes=sample_regimes,
            regime_boost=1.0,  # No boost
        )
        result_boost = apply_regime_aware_weighting(
            sample_features, lambda_decay=0.02, regimes=sample_regimes,
            regime_boost=2.0,  # Double boost
        )
        # Weights should differ
        assert not result_no_boost["sample_weight"].equals(
            result_boost["sample_weight"]
        )

    def test_no_regimes_still_works(self, sample_features):
        """Should work even without regime data."""
        result = apply_regime_aware_weighting(
            sample_features, lambda_decay=0.02, regimes=None,
        )
        assert "sample_weight" in result.columns
        assert abs(result["sample_weight"].sum() - 1.0) < 1e-10


# ── Tests: Drift Audit ────────────────────────────────────────────────────


class TestDriftAudit:
    def test_audit_returns_results(self, sample_features):
        """Audit should return results for each feature column."""
        results = audit_feature_drift(
            sample_features,
            ref_end_date="2024-08-01",
            cur_start_date="2024-08-02",
        )
        assert len(results) > 0
        assert all(isinstance(r, FeatureDriftResult) for r in results)

    def test_audit_with_regimes(self, sample_features, sample_regimes):
        """Audit should include regime info when provided."""
        results = audit_feature_drift(
            sample_features,
            ref_end_date="2024-08-01",
            cur_start_date="2024-08-02",
            regimes=sample_regimes,
        )
        assert all(r.regime_ref != "unknown" for r in results)
        assert all(r.regime_cur != "unknown" for r in results)


# ── Tests: Remediation Actions ────────────────────────────────────────────


class TestRemediationActions:
    def test_drifted_momentum_feature_gets_transform(self):
        """RSI drift should suggest rank transform."""
        results = [
            FeatureDriftResult(
                feature="rsi", psi=0.35, ks_statistic=0.3, ks_pvalue=0.01,
                status="drifted", ref_mean=55, cur_mean=45, ref_std=15, cur_std=10,
                regime_ref="bull", regime_cur="sideways",
            ),
        ]
        actions = get_remediation_actions(results)
        assert "rsi" in actions["retrain_with_weights"]
        assert any("rank_transform" in a for a in actions["consider_transform"])

    def test_drifted_volatility_feature_gets_percentile(self):
        """ATR drift should suggest percentile transform."""
        results = [
            FeatureDriftResult(
                feature="atr_pct", psi=0.40, ks_statistic=0.3, ks_pvalue=0.01,
                status="drifted", ref_mean=1.5, cur_mean=3.0, ref_std=0.5, cur_std=1.0,
                regime_ref="bull", regime_cur="crisis",
            ),
        ]
        actions = get_remediation_actions(results)
        assert any("percentile_rank" in a for a in actions["consider_transform"])

    def test_moderate_feature_goes_to_monitor(self):
        results = [
            FeatureDriftResult(
                feature="ma_ratio", psi=0.15, ks_statistic=0.1, ks_pvalue=0.1,
                status="moderate", ref_mean=1.0, cur_mean=1.05, ref_std=0.05, cur_std=0.06,
                regime_ref="bull", regime_cur="bull",
            ),
        ]
        actions = get_remediation_actions(results)
        assert "ma_ratio" in actions["monitor"]


# ── Tests: Quant-Safe Imputation ──────────────────────────────────────────


class TestQuantSafeImputation:
    def test_forward_fill_within_limit(self):
        """NaN within ffill_limit should be filled."""
        dates = pd.bdate_range("2024-01-01", periods=10)
        df = pd.DataFrame(
            {"ml_signal": [0.5, np.nan, np.nan, 0.3, 0.4, np.nan, 0.6, 0.7, 0.8, 0.9]},
            index=dates,
        )
        result = quant_safe_imputation(df, ["ml_signal"], ffill_limit=3)
        # NaN at index 1,2 should be filled with 0.5
        assert result["ml_signal"].iloc[1] == 0.5
        assert result["ml_signal"].iloc[2] == 0.5
        # Imputed flag should be set
        assert result["ml_signal_imputed"].iloc[1] == 1
        assert result["ml_signal_imputed"].iloc[2] == 1

    def test_forward_fill_exceeds_limit(self):
        """NaN beyond ffill_limit should remain as 0 (HOLD) with no_signal flag."""
        dates = pd.bdate_range("2024-01-01", periods=10)
        df = pd.DataFrame(
            {"ml_signal": [0.5, np.nan, np.nan, np.nan, np.nan, 0.3, 0.4, 0.5, 0.6, 0.7]},
            index=dates,
        )
        result = quant_safe_imputation(df, ["ml_signal"], ffill_limit=2)
        # NaN at index 1,2 should be filled (within limit)
        assert result["ml_signal"].iloc[1] == 0.5
        assert result["ml_signal"].iloc[2] == 0.5
        # NaN at index 3,4 should be 0 (no signal) with no_signal flag
        assert result["ml_signal"].iloc[3] == 0.0
        assert result["ml_signal_no_signal"].iloc[3] == 1
        assert result["ml_signal"].iloc[4] == 0.0
        assert result["ml_signal_no_signal"].iloc[4] == 1

    def test_no_backward_fill(self):
        """Leading NaN should NOT be filled from future data (no bfill)."""
        dates = pd.bdate_range("2024-01-01", periods=5)
        df = pd.DataFrame(
            {"ml_signal": [np.nan, np.nan, 0.5, 0.6, 0.7]},
            index=dates,
        )
        result = quant_safe_imputation(df, ["ml_signal"], ffill_limit=3)
        # Leading NaN should be 0 (no signal), NOT 0.5 (bfill)
        assert result["ml_signal"].iloc[0] == 0.0
        assert result["ml_signal_no_signal"].iloc[0] == 1
        assert result["ml_signal"].iloc[1] == 0.0
        assert result["ml_signal_no_signal"].iloc[1] == 1

    def test_imputed_flag_not_set_for_valid_data(self):
        """Imputed flag should be 0 for originally valid data."""
        dates = pd.bdate_range("2024-01-01", periods=5)
        df = pd.DataFrame(
            {"ml_signal": [0.5, 0.6, 0.7, 0.8, 0.9]},
            index=dates,
        )
        result = quant_safe_imputation(df, ["ml_signal"], ffill_limit=3)
        assert result["ml_signal_imputed"].sum() == 0
        assert result["ml_signal_no_signal"].sum() == 0


# ── Tests: Signal Alignment ───────────────────────────────────────────────


class TestSignalAlignment:
    def test_align_both_signals_present(self):
        """When both models have signal on same date, alignment_quality='both'."""
        dates = pd.bdate_range("2024-01-01", periods=10)
        ml = pd.DataFrame(
            {"ml_signal": [0.5] * 10, "ml_confidence": [0.8] * 10, "ml_n_train": [300] * 10},
            index=dates,
        )
        mf = pd.DataFrame(
            {"mf_signal": [0.3] * 10, "mf_action": ["BUY"] * 10, "mf_action_code": [2] * 10,
             "mf_prob_buy": [0.6] * 10, "mf_prob_sell": [0.2] * 10, "mf_prob_hold": [0.2] * 10,
             "mf_confidence": [0.7] * 10, "mf_n_train": [300] * 10},
            index=dates,
        )
        result = align_signals(ml, mf, "TEST.JK", ffill_limit=3)
        assert "blended_signal" in result.columns
        assert "ticker" in result.columns
        assert (result["alignment_quality"] == "both").all()
        # Blended = 0.40 * 0.5 + 0.60 * 0.3 = 0.38
        assert abs(result["blended_signal"].iloc[0] - (0.40 * 0.5 + 0.60 * 0.3)) < 1e-10

    def test_align_ml_only(self):
        """When only MLSignal has signal, alignment_quality='ml_only'."""
        dates = pd.bdate_range("2024-01-01", periods=10)
        ml_dates = dates
        mf_dates = dates[5:]  # MultiFactor starts later
        ml = pd.DataFrame(
            {"ml_signal": [0.5] * 10, "ml_confidence": [0.8] * 10, "ml_n_train": [300] * 10},
            index=ml_dates,
        )
        mf = pd.DataFrame(
            {"mf_signal": [0.3] * 5, "mf_action": ["BUY"] * 5, "mf_action_code": [2] * 5,
             "mf_prob_buy": [0.6] * 5, "mf_prob_sell": [0.2] * 5, "mf_prob_hold": [0.2] * 5,
             "mf_confidence": [0.7] * 5, "mf_n_train": [300] * 5},
            index=mf_dates,
        )
        result = align_signals(ml, mf, "TEST.JK", ffill_limit=2)
        # First 5 rows: ML only (mf will be ffilled within limit, then no_signal)
        assert "ml_only" in result["alignment_quality"].values or "both" in result["alignment_quality"].values

    def test_align_blended_signal_range(self):
        """Blended signal should be within [-1, 1]."""
        dates = pd.bdate_range("2024-01-01", periods=10)
        ml = pd.DataFrame(
            {"ml_signal": [-0.8] * 10, "ml_confidence": [0.8] * 10, "ml_n_train": [300] * 10},
            index=dates,
        )
        mf = pd.DataFrame(
            {"mf_signal": [0.9] * 10, "mf_action": ["BUY"] * 10, "mf_action_code": [2] * 10,
             "mf_prob_buy": [0.8] * 10, "mf_prob_sell": [0.1] * 10, "mf_prob_hold": [0.1] * 10,
             "mf_confidence": [0.7] * 10, "mf_n_train": [300] * 10},
            index=dates,
        )
        result = align_signals(ml, mf, "TEST.JK", ffill_limit=3)
        assert result["blended_signal"].min() >= -1.01
        assert result["blended_signal"].max() <= 1.01


# ── Tests: Target Computation ─────────────────────────────────────────────


class TestTargetComputation:
    def test_target_3class_values(self, sample_ohlcv):
        """Target should be 0 (SELL), 1 (HOLD), or 2 (BUY)."""
        dates = sample_ohlcv.index[:50]
        aligned = pd.DataFrame(
            {"ml_signal": [0.5] * 50, "mf_signal": [0.3] * 50,
             "blended_signal": [0.38] * 50, "ticker": ["TEST.JK"] * 50,
             "alignment_quality": ["both"] * 50,
             "ml_signal_imputed": [0] * 50, "mf_signal_imputed": [0] * 50,
             "ml_signal_no_signal": [0] * 50, "mf_signal_no_signal": [0] * 50},
            index=dates,
        )
        result = compute_targets_post_alignment(aligned, sample_ohlcv, horizon=5)
        assert "next_return" in result.columns
        assert "target_3class" in result.columns
        valid_targets = result["target_3class"][result["target_3class"] >= 0].unique()
        assert all(t in [0, 1, 2] for t in valid_targets)

    def test_tail_rows_have_nan_target(self, sample_ohlcv):
        """Last `horizon` rows of OHLCV should have NaN next_return → target=-1."""
        # Use the last 50 rows of ohlcv so forward return is truly missing at the end
        dates = sample_ohlcv.index[-50:]
        aligned = pd.DataFrame(
            {"ml_signal": [0.5] * 50, "mf_signal": [0.3] * 50,
             "blended_signal": [0.38] * 50, "ticker": ["TEST.JK"] * 50,
             "alignment_quality": ["both"] * 50,
             "ml_signal_imputed": [0] * 50, "mf_signal_imputed": [0] * 50,
             "ml_signal_no_signal": [0] * 50, "mf_signal_no_signal": [0] * 50},
            index=dates,
        )
        result = compute_targets_post_alignment(aligned, sample_ohlcv, horizon=5)
        # Last 5 rows should have target=-1 (unknown)
        assert (result["target_3class"].iloc[-5:] == -1).all()


# ── Tests: Data Leakage Audit ─────────────────────────────────────────────


class TestDataLeakageAudit:
    def test_clean_data_passes_audit(self):
        """Clean aligned data should pass leakage audit."""
        dates = pd.bdate_range("2024-01-01", periods=50)
        df = pd.DataFrame(
            {"ml_signal": [0.5] * 50, "mf_signal": [0.3] * 50,
             "blended_signal": [0.38] * 50,
             "next_return": [0.01] * 45 + [np.nan] * 5,
             "target_3class": [2] * 45 + [-1] * 5},
            index=dates,
        )
        audit = audit_data_leakage(df)
        assert audit["passed"], f"Should pass: {audit}"

    def test_suspicious_column_fails_audit(self):
        """Data with forward-looking columns should fail audit."""
        dates = pd.bdate_range("2024-01-01", periods=50)
        df = pd.DataFrame(
            {"ml_signal": [0.5] * 50, "forward_pe_ratio": [15.0] * 50,
             "blended_signal": [0.38] * 50},
            index=dates,
        )
        audit = audit_data_leakage(df)
        assert not audit["leakage_checks"]["no_suspicious_columns"]["passed"]

    def test_signal_out_of_range_fails_audit(self):
        """Signal outside [-1, 1] should fail audit."""
        dates = pd.bdate_range("2024-01-01", periods=50)
        df = pd.DataFrame(
            {"ml_signal": [2.0] * 50, "blended_signal": [0.38] * 50},
            index=dates,
        )
        audit = audit_data_leakage(df)
        assert not audit["leakage_checks"]["ml_signal_range"]["passed"]
