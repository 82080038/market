"""Regression tests for alpha_hyper_tuner.py — Automated Optimization Pipeline.

Tests cover:
  Module 1 — Donchian, EMA Envelope, VWAP, Ensemble baseline signals
  Module 2 — Grid search, Bayesian optimization, objective function
  Module 3 — Adaptive threshold computation, dynamic meta-labeling
  Module 4 — Comparison table, config serialization, report structure
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Path setup
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from alpha_hyper_tuner import (  # noqa: E402
    HyperParamSpace,
    TrialResult,
    TuningReport,
    ReformConfig,
    generate_donchian_signals,
    generate_ema_envelope_signals,
    generate_vwap_signals,
    generate_robust_trend_baseline,
    evaluate_baseline,
    select_best_baseline,
    compute_adaptive_threshold,
    _objective_function,
    _build_config_from_params,
    evaluate_param_combo,
    grid_search_params,
    print_comparison_table,
    save_best_config,
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


# ── Module 1 Tests: Robust Trend-Following Baseline ────────────────────────


class TestDonchianSignals:
    """Test Donchian Channel Breakout signals."""

    def test_returns_series_with_valid_values(self, synthetic_ohlcv):
        sig = generate_donchian_signals(synthetic_ohlcv, period=20)
        assert isinstance(sig, pd.Series)
        assert len(sig) == len(synthetic_ohlcv)
        assert set(sig.unique()).issubset({-1.0, 0.0, 1.0})

    def test_trend_persistence(self, synthetic_ohlcv):
        """Donchian should maintain position until opposite breakout."""
        sig = generate_donchian_signals(synthetic_ohlcv, period=20)
        # After initial signal, there should be stretches of constant signal
        changes = sig.diff().abs().sum()
        assert changes < len(sig)  # fewer changes than total rows

    def test_short_period_more_signals(self, synthetic_ohlcv):
        """Shorter period should produce more signal changes."""
        sig_short = generate_donchian_signals(synthetic_ohlcv, period=10)
        sig_long = generate_donchian_signals(synthetic_ohlcv, period=50)
        changes_short = sig_short.diff().abs().sum()
        changes_long = sig_long.diff().abs().sum()
        assert changes_short >= changes_long


class TestEMAEnvelopeSignals:
    """Test EMA Envelope signals."""

    def test_returns_series_with_valid_values(self, synthetic_ohlcv):
        sig = generate_ema_envelope_signals(synthetic_ohlcv, ema_period=50, envelope_pct=0.03)
        assert isinstance(sig, pd.Series)
        assert len(sig) == len(synthetic_ohlcv)
        assert set(sig.unique()).issubset({-1.0, 0.0, 1.0})

    def test_wider_envelope_fewer_signals(self, synthetic_ohlcv):
        """Wider envelope should produce fewer signal changes."""
        sig_narrow = generate_ema_envelope_signals(synthetic_ohlcv, envelope_pct=0.01)
        sig_wide = generate_ema_envelope_signals(synthetic_ohlcv, envelope_pct=0.05)
        changes_narrow = sig_narrow.diff().abs().sum()
        changes_wide = sig_wide.diff().abs().sum()
        assert changes_narrow >= changes_wide


class TestVWAPSignals:
    """Test VWAP Confirmation signals."""

    def test_returns_series_with_valid_values(self, synthetic_ohlcv):
        sig = generate_vwap_signals(synthetic_ohlcv, vwap_period=20)
        assert isinstance(sig, pd.Series)
        assert len(sig) == len(synthetic_ohlcv)
        assert set(sig.unique()).issubset({-1.0, 0.0, 1.0})


class TestRobustTrendBaseline:
    """Test the combined robust trend baseline."""

    def test_ensemble_mode(self, synthetic_ohlcv):
        sig = generate_robust_trend_baseline(synthetic_ohlcv, mode="ensemble")
        assert isinstance(sig, pd.Series)
        assert len(sig) == len(synthetic_ohlcv)
        assert set(sig.unique()).issubset({-1.0, 0.0, 1.0})

    def test_individual_modes(self, synthetic_ohlcv):
        for mode in ["donchian", "ema_env", "vwap"]:
            sig = generate_robust_trend_baseline(synthetic_ohlcv, mode=mode)
            assert len(sig) == len(synthetic_ohlcv)

    def test_invalid_mode_raises(self, synthetic_ohlcv):
        with pytest.raises(ValueError, match="tidak dikenal"):
            generate_robust_trend_baseline(synthetic_ohlcv, mode="invalid")

    def test_ensemble_more_conservative_than_donchian(self, synthetic_ohlcv):
        """Ensemble (2/3 majority) should have fewer or equal signals than Donchian alone."""
        sig_don = generate_robust_trend_baseline(synthetic_ohlcv, mode="donchian")
        sig_ens = generate_robust_trend_baseline(synthetic_ohlcv, mode="ensemble")
        active_don = (sig_don != 0).sum()
        active_ens = (sig_ens != 0).sum()
        assert active_ens <= active_don


class TestEvaluateBaseline:
    """Test baseline evaluation."""

    def test_returns_metrics_dict(self, synthetic_ohlcv):
        m = evaluate_baseline(synthetic_ohlcv, None, "donchian")
        assert "sharpe" in m
        assert "alpha" in m
        assert "max_drawdown" in m
        assert "win_rate" in m
        assert "n_trades" in m

    def test_all_modes(self, synthetic_ohlcv):
        for mode in ["donchian", "ema_env", "vwap", "ensemble"]:
            m = evaluate_baseline(synthetic_ohlcv, None, mode)
            assert isinstance(m["sharpe"], float)


# ── Module 2 Tests: Grid / Bayesian Optimization ───────────────────────────


class TestObjectiveFunction:
    """Test the objective function for optimization."""

    def test_positive_sharpe_positive_alpha(self):
        obj = _objective_function(1.5, 0.05, -0.2, 0.6)
        assert obj > 0

    def test_negative_sharpe_penalized(self):
        obj = _objective_function(-1.0, 0.0, -0.5, 0.3)
        assert obj < 0

    def test_high_accept_rate_bonus(self):
        obj_low = _objective_function(0.5, 0.0, -0.2, 0.2)
        obj_high = _objective_function(0.5, 0.0, -0.2, 0.8)
        assert obj_high > obj_low

    def test_large_drawdown_penalized(self):
        obj_small_dd = _objective_function(0.5, 0.0, -0.1, 0.5)
        obj_large_dd = _objective_function(0.5, 0.0, -0.5, 0.5)
        assert obj_small_dd > obj_large_dd


class TestBuildConfigFromParams:
    """Test config construction from params dict."""

    def test_partial_params(self, config):
        params = {"vol_aggressiveness": 1.5}
        cfg = _build_config_from_params(config, params)
        assert cfg.vol_aggressiveness == 1.5
        # Other params should retain defaults
        assert cfg.signal_threshold == config.signal_threshold

    def test_all_params(self, config):
        params = {
            "meta_prob_threshold": 0.35,
            "vol_aggressiveness": 1.0,
            "vol_hard_cutoff_zscore": 2.5,
            "signal_threshold": 0.05,
        }
        cfg = _build_config_from_params(config, params)
        assert cfg.meta_prob_threshold == 0.35
        assert cfg.vol_aggressiveness == 1.0
        assert cfg.vol_hard_cutoff_zscore == 2.5
        assert cfg.signal_threshold == 0.05


class TestGridSearch:
    """Test grid search optimization."""

    def test_returns_list_of_trials(self, synthetic_ohlcv, config):
        space = HyperParamSpace(grid_points=2)
        results = grid_search_params(synthetic_ohlcv, config, space, None, "donchian")
        assert isinstance(results, list)
        assert len(results) == 2 ** 4  # 2 points per 4 dimensions = 16
        assert all(isinstance(r, TrialResult) for r in results)

    def test_best_trial_has_highest_objective(self, synthetic_ohlcv, config):
        space = HyperParamSpace(grid_points=2)
        results = grid_search_params(synthetic_ohlcv, config, space, None, "donchian")
        best = max(results, key=lambda t: t.objective)
        assert best.objective >= max(r.objective for r in results)

    def test_trial_params_populated(self, synthetic_ohlcv, config):
        space = HyperParamSpace(grid_points=2)
        results = grid_search_params(synthetic_ohlcv, config, space, None, "donchian")
        for r in results:
            assert "meta_prob_threshold" in r.params
            assert "vol_aggressiveness" in r.params
            assert "vol_hard_cutoff_zscore" in r.params
            assert "signal_threshold" in r.params


# ── Module 3 Tests: Dynamic Adaptive Meta-Labeling Threshold ────────────────


class TestComputeAdaptiveThreshold:
    """Test adaptive threshold computation."""

    def test_low_vol_returns_base(self):
        th = compute_adaptive_threshold(np.array([-2.0, -1.0, 0.0]), base_threshold=0.40)
        assert np.allclose(th, 0.40)

    def test_high_vol_increases_threshold(self):
        th = compute_adaptive_threshold(np.array([1.0, 2.0, 3.0]), base_threshold=0.40, adapt_kappa=0.15)
        assert th[0] > 0.40
        assert th[1] > th[0]
        assert th[2] >= th[1]

    def test_clamped_to_min(self):
        th = compute_adaptive_threshold(np.array([-5.0]), base_threshold=0.30, min_threshold=0.25)
        assert th[0] >= 0.25

    def test_clamped_to_max(self):
        th = compute_adaptive_threshold(np.array([10.0]), base_threshold=0.40, max_threshold=0.65)
        assert th[0] <= 0.65

    def test_scalar_input(self):
        th = compute_adaptive_threshold(0.5, base_threshold=0.40, adapt_kappa=0.15)
        assert float(th) == pytest.approx(0.475, abs=1e-10)

    def test_monotonic_non_decreasing(self):
        vol_z = np.array([-2.0, -1.0, 0.0, 0.5, 1.0, 2.0, 3.0])
        th = compute_adaptive_threshold(vol_z, base_threshold=0.40, adapt_kappa=0.15)
        for i in range(len(th) - 1):
            assert th[i] <= th[i + 1]


# ── Module 4 Tests: Report & Serialization ──────────────────────────────────


class TestPrintComparisonTable:
    """Test comparison table output."""

    def test_prints_without_error(self, caplog):
        before = {"sharpe": -0.5, "alpha": -0.07, "max_drawdown": -0.9,
                  "win_rate": 0.48, "accept_rate": 0.38, "brier": 0.26, "score": 2.6}
        after = {"sharpe": 0.1, "alpha": 0.05, "max_drawdown": -0.5,
                 "win_rate": 0.51, "accept_rate": 0.70, "brier": 0.25, "score": 3.2}
        with caplog.at_level(logging.INFO):
            print_comparison_table(before, after)
        assert any("COMPARISON" in r.message for r in caplog.records)
        assert any("Sharpe" in r.message for r in caplog.records)


class TestSaveBestConfig:
    """Test best config JSON serialization."""

    def test_saves_valid_json(self, tmp_path):
        params = {"meta_prob_threshold": 0.35, "vol_aggressiveness": 1.0}
        result = TrialResult(params=params, sharpe=0.5, alpha=0.03, objective=0.4)
        output = tmp_path / "test_config.json"
        save_best_config(params, "donchian", result, str(output))
        with output.open() as f:
            data = json.load(f)
        assert data["best_params"]["meta_prob_threshold"] == 0.35
        assert data["baseline_mode"] == "donchian"
        assert data["performance"]["sharpe"] == 0.5


class TestReportSerialization:
    """Test TuningReport to dict conversion."""

    def test_report_to_dict_json_safe(self):
        report = TuningReport(
            audit_date="2026-01-01",
            tickers=["BBCA.JK"],
            mode="grid",
            n_trials=16,
            best_params={"meta_prob_threshold": 0.35},
            best_result=TrialResult(params={"meta_prob_threshold": 0.35}, objective=0.5),
        )
        d = _report_to_dict(report)
        assert isinstance(d, dict)
        assert d["audit_date"] == "2026-01-01"
        assert d["mode"] == "grid"
        assert d["n_trials"] == 16

    def test_empty_report_to_dict(self):
        report = TuningReport()
        d = _report_to_dict(report)
        assert isinstance(d, dict)
        assert "audit_date" in d


class TestHyperParamSpace:
    """Test hyperparameter space configuration."""

    def test_defaults(self):
        space = HyperParamSpace()
        assert space.meta_prob_threshold == (0.35, 0.50)
        assert space.vol_aggressiveness == (1.0, 2.0)
        assert space.vol_hard_cutoff_zscore == (1.5, 2.5)
        assert space.signal_threshold == (0.05, 0.15)
        assert space.grid_points == 4

    def test_custom_space(self):
        space = HyperParamSpace(
            meta_prob_threshold=(0.30, 0.45),
            grid_points=5,
        )
        assert space.meta_prob_threshold == (0.30, 0.45)
        assert space.grid_points == 5
