"""Regression tests for portfolio_final_execution.py.

Tests cover:
  Module 1 — Config loading & parameter override (build_config_from_ticker_params, build_baseline_candidate)
  Module 2 — Signal generation, daily inverse-variance weighting, weighted portfolio returns
  Module 3 — OOS ticker evaluation (date filtering, metrics computation)
  Module 4 — Final verdict computation, JSON serialization, report structure
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Path setup
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from portfolio_final_execution import (  # noqa: E402
    TickerExecution,
    FinalVerdictReport,
    load_ticker_config,
    build_config_from_ticker_params,
    build_baseline_candidate,
    generate_ticker_signals,
    generate_baseline_ticker_signals,
    compute_daily_inverse_variance_weights,
    compute_weighted_portfolio_returns,
    evaluate_oos_ticker,
    compute_final_verdict,
    save_verdict_json,
)
from alpha_rescue_pipeline import ReformConfig  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_ohlcv() -> pd.DataFrame:
    """Generate synthetic OHLCV with enough rows for walk-forward."""
    np.random.seed(42)
    n = 800
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
def synthetic_tech_features(synthetic_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Generate synthetic technical_indicators in wide format."""
    np.random.seed(123)
    idx = synthetic_ohlcv.index.normalize()
    n = len(idx)
    return pd.DataFrame(
        {
            "RSI": np.random.uniform(20, 80, n),
            "MACD": np.random.randn(n) * 0.5,
            "ATR14": np.random.uniform(1, 5, n),
            "BB_LOWER": synthetic_ohlcv["close"].values * 0.95,
            "VOLUME_SMA20": np.random.uniform(1e6, 5e6, n),
        },
        index=idx,
    )


@pytest.fixture
def config() -> ReformConfig:
    return ReformConfig()


@pytest.fixture
def ticker_config_file(tmp_path: Path) -> Path:
    """Create a minimal best_ticker_quant_config.json for testing."""
    config_data = {
        "generated_at": "2026-01-01T00:00:00",
        "n_tickers": 3,
        "tickers": {
            "KPIG.JK": {
                "sector": "Basic Materials",
                "cluster_id": 0,
                "cluster_label": "cluster_0",
                "adapt_kappa": 0.08,
                "gk_volatility": 0.035,
                "baseline_mode": "donchian",
                "baseline_params": {"donchian_period": 15},
                "best_params": {
                    "meta_prob_threshold": 0.35,
                    "vol_aggressiveness": 1.5,
                    "vol_hard_cutoff_zscore": 2.0,
                    "signal_threshold": 0.08,
                },
                "performance": {"sharpe": 0.5, "alpha": 0.02},
            },
            "ICBP.JK": {
                "sector": "Consumer Defensive",
                "cluster_id": 2,
                "cluster_label": "cluster_2",
                "adapt_kappa": 0.25,
                "gk_volatility": 0.012,
                "baseline_mode": "ema_env",
                "baseline_params": {"ema_period": 50, "envelope_pct": 0.03},
                "best_params": {
                    "meta_prob_threshold": 0.45,
                    "vol_aggressiveness": 1.0,
                    "vol_hard_cutoff_zscore": 2.5,
                    "signal_threshold": 0.10,
                },
                "performance": {"sharpe": 1.2, "alpha": 0.05},
            },
            "MEDC.JK": {
                "sector": "Energy",
                "cluster_id": 1,
                "cluster_label": "cluster_1",
                "adapt_kappa": 0.10,
                "gk_volatility": 0.028,
                "baseline_mode": "donchian",
                "baseline_params": {"donchian_period": 20},
                "best_params": {
                    "meta_prob_threshold": 0.38,
                    "vol_aggressiveness": 1.8,
                    "vol_hard_cutoff_zscore": 1.8,
                    "signal_threshold": 0.06,
                },
                "performance": {"sharpe": 0.3, "alpha": 0.01},
            },
        },
    }
    path = tmp_path / "best_ticker_quant_config.json"
    path.write_text(json.dumps(config_data, indent=2))
    return path


# ── Module 1 Tests: Config Loading ─────────────────────────────────────────


class TestConfigLoading:
    """Test loading and parsing of best_ticker_quant_config.json."""

    def test_load_ticker_config(self, ticker_config_file):
        configs = load_ticker_config(str(ticker_config_file))
        assert len(configs) == 3
        assert "KPIG.JK" in configs
        assert configs["KPIG.JK"]["adapt_kappa"] == 0.08

    def test_load_ticker_config_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_ticker_config(str(tmp_path / "nonexistent.json"))

    def test_build_config_from_ticker_params(self, config, ticker_config_file):
        configs = load_ticker_config(str(ticker_config_file))
        cfg = build_config_from_ticker_params(config, configs["KPIG.JK"])
        assert cfg.meta_prob_threshold == 0.35
        assert cfg.signal_threshold == 0.08

    def test_build_config_no_params_returns_base(self, config):
        cfg = build_config_from_ticker_params(config, {})
        assert cfg.meta_prob_threshold == config.meta_prob_threshold

    def test_build_baseline_candidate(self, ticker_config_file):
        configs = load_ticker_config(str(ticker_config_file))
        candidate = build_baseline_candidate(configs["KPIG.JK"])
        assert candidate["mode"] == "donchian"
        assert candidate["donchian_period"] == 15

    def test_build_baseline_candidate_ema_env(self, ticker_config_file):
        configs = load_ticker_config(str(ticker_config_file))
        candidate = build_baseline_candidate(configs["ICBP.JK"])
        assert candidate["mode"] == "ema_env"
        assert candidate["ema_period"] == 50

    def test_adapt_kappa_high_vol_smaller(self, ticker_config_file):
        """High-volatility stocks should have smaller κ than defensive."""
        configs = load_ticker_config(str(ticker_config_file))
        kpig_kappa = configs["KPIG.JK"]["adapt_kappa"]
        icbp_kappa = configs["ICBP.JK"]["adapt_kappa"]
        assert kpig_kappa < icbp_kappa


# ── Module 2 Tests: Signal Generation & Weighting ──────────────────────────


class TestSignalGeneration:
    """Test signal generation and baseline comparison."""

    def test_generate_ticker_signals_returns_series(self, synthetic_ohlcv,
                                                     synthetic_tech_features, config):
        baseline_candidate = {"mode": "donchian", "donchian_period": 20}
        positions, returns, diag = generate_ticker_signals(
            synthetic_ohlcv, config, baseline_candidate,
            synthetic_tech_features, adapt_kappa=0.15,
        )
        assert isinstance(positions, pd.Series)
        assert isinstance(returns, pd.Series)
        assert "accept_rate" in diag
        assert "brier" in diag

    def test_generate_baseline_returns(self, synthetic_ohlcv):
        returns = generate_baseline_ticker_signals(synthetic_ohlcv)
        assert isinstance(returns, pd.Series)
        assert len(returns) > 0

    def test_generate_ticker_signals_empty_ohlcv(self, config):
        empty = pd.DataFrame()
        positions, returns, diag = generate_ticker_signals(
            empty, config, {"mode": "donchian"}, pd.DataFrame(), 0.15,
        )
        assert len(positions) == 0
        assert len(returns) == 0


class TestDailyInverseVarianceWeights:
    """Test daily adaptive inverse-variance weighting."""

    def test_weights_sum_to_one(self):
        """Weights should sum to 1.0 per day."""
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        returns_dict = {
            "A": pd.Series(np.random.randn(100) * 0.01, index=dates),
            "B": pd.Series(np.random.randn(100) * 0.03, index=dates),
            "C": pd.Series(np.random.randn(100) * 0.005, index=dates),
        }
        weights = compute_daily_inverse_variance_weights(
            returns_dict,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
            max_weight=0.50,
        )
        assert len(weights) == 3
        # Check sum ≈ 1 for each date (after lookback)
        df_w = pd.DataFrame(weights)
        row_sums = df_w.sum(axis=1).dropna()
        assert np.allclose(row_sums.values, 1.0, atol=1e-10)

    def test_volatile_ticker_gets_smaller_weight(self):
        """Volatile ticker should get smaller weight than stable ticker."""
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        np.random.seed(42)
        returns_dict = {
            "STABLE": pd.Series(np.random.randn(200) * 0.005, index=dates),
            "VOLATILE": pd.Series(np.random.randn(200) * 0.05, index=dates),
        }
        weights = compute_daily_inverse_variance_weights(
            returns_dict,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
            max_weight=0.90,
        )
        avg_stable = weights["STABLE"].mean()
        avg_volatile = weights["VOLATILE"].mean()
        assert avg_stable > avg_volatile

    def test_empty_returns_empty(self):
        weights = compute_daily_inverse_variance_weights(
            {}, pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"),
        )
        assert weights == {}

    def test_oos_filtering(self):
        """Weights should only cover OOS period."""
        dates = pd.date_range("2023-01-01", periods=300, freq="B")
        returns_dict = {
            "A": pd.Series(np.random.randn(300) * 0.01, index=dates),
        }
        weights = compute_daily_inverse_variance_weights(
            returns_dict,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-06-30"),
        )
        w = weights["A"].dropna()
        assert w.index.min() >= pd.Timestamp("2024-01-01")
        assert w.index.max() <= pd.Timestamp("2024-06-30")

    def test_zero_variance_ticker_filtered_out(self):
        """Regression: ticker with all-zero returns (AcceptRate=0%) must NOT
        collapse portfolio weighting. This was the BVIC.JK bug that caused
        weight=1.0 on a zero-signal ticker."""
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        np.random.seed(42)
        returns_dict = {
            "GOOD_A": pd.Series(np.random.randn(200) * 0.01, index=dates),
            "GOOD_B": pd.Series(np.random.randn(200) * 0.02, index=dates),
            "ZERO_SIGNAL": pd.Series(0.0, index=dates),
        }
        weights = compute_daily_inverse_variance_weights(
            returns_dict,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
        )
        assert "ZERO_SIGNAL" not in weights or weights["ZERO_SIGNAL"].mean() == 0.0
        good_a_mean = weights["GOOD_A"].dropna().mean()
        good_b_mean = weights["GOOD_B"].dropna().mean()
        assert good_a_mean > 0.0
        assert good_b_mean > 0.0

    def test_all_zero_returns_falls_back_to_equal_weight(self):
        """If all tickers have zero returns, fallback to equal weighting."""
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        returns_dict = {
            "A": pd.Series(0.0, index=dates),
            "B": pd.Series(0.0, index=dates),
        }
        weights = compute_daily_inverse_variance_weights(
            returns_dict,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
        )
        assert len(weights) == 2
        for ticker in weights:
            w = weights[ticker].dropna()
            if len(w) > 0:
                assert abs(w.iloc[0] - 0.5) < 1e-10

    def test_max_weight_cap_enforced(self):
        """No single ticker should exceed max_weight when enough tickers exist."""
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        np.random.seed(42)
        returns_dict = {
            f"T{i}": pd.Series(np.random.randn(200) * (0.001 * (i + 1)), index=dates)
            for i in range(6)
        }
        weights = compute_daily_inverse_variance_weights(
            returns_dict,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
            max_weight=0.20,
        )
        df_w = pd.DataFrame(weights)
        max_w = df_w.max().max()
        assert max_w <= 0.20 + 1e-6


class TestWeightedPortfolioReturns:
    """Test weighted portfolio return computation."""

    def test_basic_weighted_returns(self):
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        returns_dict = {
            "A": pd.Series(np.random.randn(50) * 0.01, index=dates),
            "B": pd.Series(np.random.randn(50) * 0.02, index=dates),
        }
        weights_dict = {
            "A": pd.Series(0.6, index=dates),
            "B": pd.Series(0.4, index=dates),
        }
        portfolio = compute_weighted_portfolio_returns(returns_dict, weights_dict)
        assert len(portfolio) == 50
        # Check first day: 0.6 * ret_A + 0.4 * ret_B
        expected = 0.6 * returns_dict["A"].iloc[0] + 0.4 * returns_dict["B"].iloc[0]
        assert abs(portfolio.iloc[0] - expected) < 1e-10

    def test_empty_inputs(self):
        result = compute_weighted_portfolio_returns({}, {})
        assert len(result) == 0


# ── Module 3 Tests: OOS Evaluation ─────────────────────────────────────────


class TestOOSEvaluation:
    """Test out-of-sample ticker evaluation."""

    def test_evaluate_oos_ticker_returns_execution(self, synthetic_ohlcv,
                                                    synthetic_tech_features, config):
        baseline_candidate = {"mode": "donchian", "donchian_period": 20}
        exec_result, oos_rets, oos_base = evaluate_oos_ticker(
            synthetic_ohlcv, None, config, baseline_candidate,
            synthetic_tech_features, 0.15,
            pd.Timestamp("2024-01-01"), pd.Timestamp("2026-08-31"),
        )
        assert isinstance(exec_result, TickerExecution)
        assert isinstance(oos_rets, pd.Series)
        assert isinstance(oos_base, pd.Series)
        # OOS returns should be within date range
        if len(oos_rets) > 0:
            assert oos_rets.index.min() >= pd.Timestamp("2024-01-01")

    def test_oos_returns_filtered(self, synthetic_ohlcv, synthetic_tech_features, config):
        """OOS returns should only contain dates within the OOS window."""
        baseline_candidate = {"mode": "donchian", "donchian_period": 20}
        _, oos_rets, _ = evaluate_oos_ticker(
            synthetic_ohlcv, None, config, baseline_candidate,
            synthetic_tech_features, 0.15,
            pd.Timestamp("2025-01-01"), pd.Timestamp("2025-06-30"),
        )
        if len(oos_rets) > 0:
            assert oos_rets.index.min() >= pd.Timestamp("2025-01-01")
            assert oos_rets.index.max() <= pd.Timestamp("2025-06-30")


# ── Module 4 Tests: Final Verdict ──────────────────────────────────────────


class TestFinalVerdict:
    """Test final verdict computation and JSON output."""

    def test_compute_final_verdict_returns_tuple(self):
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        np.random.seed(42)
        portfolio = pd.Series(np.random.randn(200) * 0.01 + 0.0005, index=dates)
        baseline = pd.Series(np.random.randn(200) * 0.01, index=dates)
        benchmark = pd.Series(np.random.randn(200) * 0.008, index=dates)

        verdict, port_metrics, base_metrics = compute_final_verdict(
            portfolio, baseline, benchmark,
            pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"),
        )
        assert hasattr(verdict, "verdict")
        assert "sharpe" in port_metrics
        assert "alpha" in port_metrics
        assert "sharpe" in base_metrics

    def test_compute_final_verdict_no_benchmark(self):
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        np.random.seed(42)
        portfolio = pd.Series(np.random.randn(200) * 0.01, index=dates)
        baseline = pd.Series(np.random.randn(200) * 0.01, index=dates)

        verdict, port_metrics, _ = compute_final_verdict(
            portfolio, baseline, None,
            pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"),
        )
        assert verdict.verdict in ("KEEP", "MARGINAL", "REMOVE")

    def test_save_verdict_json(self, tmp_path):
        report = FinalVerdictReport(
            execution_date="2026-01-01T00:00:00",
            config_path="best_ticker_quant_config.json",
            db_path="data/market_research.db",
            oos_start="2024-01-01",
            oos_end="2026-08-31",
            n_tickers=20,
            n_tickers_executed=18,
            portfolio_sharpe=1.35,
            portfolio_sortino=1.8,
            portfolio_alpha=0.045,
            portfolio_max_drawdown=-0.22,
            portfolio_win_rate=0.54,
            portfolio_total_return=0.15,
            portfolio_calmar=0.68,
            portfolio_information_ratio=0.9,
            portfolio_score=3.65,
            portfolio_verdict="KEEP",
            promoted_to_keep=True,
            p_value_paired_ttest=0.03,
            p_value_diebold_mariano=0.04,
            p_value_whites_rc=0.02,
            portfolio_weights={"KPIG.JK": 0.05, "ICBP.JK": 0.15},
            baseline_portfolio_sharpe=0.3,
            baseline_portfolio_alpha=-0.01,
            baseline_portfolio_max_drawdown=-0.35,
            delta_sharpe=1.05,
            delta_alpha=0.055,
            ticker_results=[{"ticker": "KPIG.JK", "oos_sharpe": 0.5}],
        )
        output = tmp_path / "final_portfolio_verdict.json"
        save_verdict_json(report, str(output))
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["score_card"]["score"] == 3.65
        assert data["score_card"]["promoted_to_keep"] is True
        assert data["portfolio_metrics"]["sharpe"] == 1.35
        assert data["n_tickers_executed"] == 18

    def test_save_verdict_json_handles_nan(self, tmp_path):
        """JSON output should handle NaN values gracefully."""
        report = FinalVerdictReport(
            portfolio_sharpe=float("nan"),
            portfolio_alpha=float("nan"),
        )
        output = tmp_path / "verdict_nan.json"
        save_verdict_json(report, str(output))
        data = json.loads(output.read_text())
        assert data["portfolio_metrics"]["sharpe"] is None
        assert data["portfolio_metrics"]["alpha"] is None


# ── Integration Tests: TickerExecution Dataclass ───────────────────────────


class TestTickerExecution:
    """Test TickerExecution dataclass behavior."""

    def test_default_values(self):
        te = TickerExecution()
        assert te.ticker == ""
        assert te.adapt_kappa == 0.15
        assert te.cluster_id == -1
        assert te.oos_returns is None

    def test_portfolio_weight_default(self):
        te = TickerExecution()
        assert te.portfolio_weight == 0.0
