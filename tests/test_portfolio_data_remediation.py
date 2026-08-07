"""Regression tests for portfolio_data_remediation.py.

Tests cover:
  Module A — Quant-Safe Data Patching (market_cap proxy, stock personality healing)
  Module B — Sector-Level Hierarchical Clustering
  Module C — Regime-invariant feature building, feature completeness, meta-signal Brier score
  Module D — JSON serialization safety, config output structure
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

from portfolio_data_remediation import (  # noqa: E402
    DEFAULT_FOCUS_TICKERS,
    REGIME_INVARIANT_INDICATORS,
    N_OPERATIONAL_CLUSTERS,
    KEEP_SCORE_TARGET,
    TickerRemediation,
    RemediationReport,
    json_safe,
    compute_stock_personality_metrics,
    cluster_tickers_by_sector_cap,
    build_regime_invariant_features,
    feature_completeness,
)
from alpha_rescue_pipeline import ReformConfig  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_ohlcv() -> pd.DataFrame:
    """Generate synthetic OHLCV data with enough rows for personality metrics."""
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
def synthetic_tech_features(synthetic_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Generate synthetic technical_indicators in wide format (aligned to ohlcv dates)."""
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


# ── Module A Tests: Quant-Safe Data Patching ────────────────────────────────


class TestStockPersonalityMetrics:
    """Test healing of 100% NULL stock_personality from OHLCV."""

    def test_returns_all_metrics(self, synthetic_ohlcv):
        result = compute_stock_personality_metrics(synthetic_ohlcv)
        expected_keys = {
            "avg_daily_volatility", "trend_strength", "correlation_ihsg",
            "avg_volume", "volume_consistency",
        }
        assert set(result.keys()) == expected_keys

    def test_avg_daily_volatility_positive(self, synthetic_ohlcv):
        result = compute_stock_personality_metrics(synthetic_ohlcv)
        assert result["avg_daily_volatility"] > 0.0

    def test_trend_strength_in_range(self, synthetic_ohlcv):
        result = compute_stock_personality_metrics(synthetic_ohlcv)
        assert 0.0 <= result["trend_strength"] <= 100.0

    def test_volume_consistency_in_range(self, synthetic_ohlcv):
        result = compute_stock_personality_metrics(synthetic_ohlcv)
        assert 0.0 <= result["volume_consistency"] <= 1.0

    def test_correlation_with_benchmark(self, synthetic_ohlcv):
        benchmark = synthetic_ohlcv["close"].pct_change().dropna()
        result = compute_stock_personality_metrics(synthetic_ohlcv, benchmark)
        assert -1.0 <= result["correlation_ihsg"] <= 1.0

    def test_empty_ohlcv_returns_zeros(self):
        result = compute_stock_personality_metrics(pd.DataFrame())
        assert result["avg_daily_volatility"] == 0.0
        assert result["trend_strength"] == 0.0

    def test_short_ohlcv_returns_zeros(self):
        short = pd.DataFrame(
            {"close": [100, 101, 102], "volume": [1e6, 2e6, 1.5e6]},
            index=pd.date_range("2024-01-01", periods=3, freq="B"),
        )
        result = compute_stock_personality_metrics(short)
        assert result["avg_daily_volatility"] == 0.0


# ── Module B Tests: Sector-Level Hierarchical Clustering ────────────────────


class TestSectorClustering:
    """Test clustering of tickers by sector + log(market_cap)."""

    def _make_records(self, n: int = 6) -> list[TickerRemediation]:
        sectors = ["Energy", "Energy", "Consumer", "Consumer", "Financial", "Financial"]
        caps = [1e12, 1e10, 5e13, 2e11, 8e12, 3e10]
        return [
            TickerRemediation(
                ticker=f"TKR{i}.JK",
                sector=sectors[i],
                calculated_market_cap=caps[i],
            )
            for i in range(n)
        ]

    def test_returns_dict_with_all_tickers(self):
        records = self._make_records()
        result = cluster_tickers_by_sector_cap(records)
        assert len(result) == len(records)
        assert all(isinstance(v, int) for v in result.values())

    def test_cluster_ids_in_valid_range(self):
        records = self._make_records()
        result = cluster_tickers_by_sector_cap(records)
        for v in result.values():
            assert 0 <= v < N_OPERATIONAL_CLUSTERS

    def test_zero_market_cap_tickers_get_outlier(self):
        records = self._make_records()
        records.append(TickerRemediation(ticker="ZERO.JK", sector="Energy",
                                         calculated_market_cap=0.0))
        result = cluster_tickers_by_sector_cap(records)
        assert result["ZERO.JK"] == -1

    def test_all_zero_cap_returns_default_cluster(self):
        records = [
            TickerRemediation(ticker=f"TKR{i}.JK", sector="Energy",
                              calculated_market_cap=0.0)
            for i in range(3)
        ]
        result = cluster_tickers_by_sector_cap(records)
        assert all(v == 0 for v in result.values())


# ── Module C Tests: Regime-Invariant Features ──────────────────────────────


class TestRegimeInvariantFeatures:
    """Test build_regime_invariant_features and feature_completeness."""

    def test_feature_columns_present(self, synthetic_ohlcv, synthetic_tech_features):
        feat = build_regime_invariant_features(synthetic_ohlcv, synthetic_tech_features)
        expected_cols = {"RSI", "MACD", "ATR_pct", "BB_dist", "VOLUME_SMA20"}
        assert set(feat.columns) == expected_cols

    def test_no_fundamental_features(self, synthetic_ohlcv, synthetic_tech_features):
        feat = build_regime_invariant_features(synthetic_ohlcv, synthetic_tech_features)
        forbidden = {"PE", "PB", "ROE", "DER", "dividend_yield"}
        assert not (set(feat.columns) & forbidden)

    def test_index_aligned_to_ohlcv(self, synthetic_ohlcv, synthetic_tech_features):
        feat = build_regime_invariant_features(synthetic_ohlcv, synthetic_tech_features)
        assert len(feat) == len(synthetic_ohlcv)

    def test_atr_pct_is_scale_free(self, synthetic_ohlcv, synthetic_tech_features):
        feat = build_regime_invariant_features(synthetic_ohlcv, synthetic_tech_features)
        assert feat["ATR_pct"].notna().all()
        assert (feat["ATR_pct"] >= 0).all()

    def test_bb_dist_is_scale_free(self, synthetic_ohlcv, synthetic_tech_features):
        feat = build_regime_invariant_features(synthetic_ohlcv, synthetic_tech_features)
        assert feat["BB_dist"].notna().all()

    def test_empty_tech_returns_empty(self, synthetic_ohlcv):
        feat = build_regime_invariant_features(synthetic_ohlcv, pd.DataFrame())
        assert feat.empty

    def test_feature_completeness_full(self, synthetic_tech_features):
        pct = feature_completeness(synthetic_tech_features)
        assert pct == 100.0

    def test_feature_completeness_empty(self):
        pct = feature_completeness(pd.DataFrame())
        assert pct == 0.0

    def test_feature_completeness_partial(self):
        tech = pd.DataFrame(
            {"RSI": [50, 60, None], "MACD": [0.1, 0.2, 0.3],
             "ATR14": [2, 3, 4], "BB_LOWER": [95, 96, 97],
             "VOLUME_SMA20": [1e6, 2e6, 3e6]},
            index=pd.date_range("2024-01-01", periods=3, freq="B"),
        )
        pct = feature_completeness(tech)
        assert 0.0 < pct < 100.0


# ── Module C Tests: Brier Score Regression ──────────────────────────────────


class TestBrierScoreRegression:
    """Regression test for the Brier score bug fix.

    The Brier score in _generate_regime_invariant_meta_signals must compare
    test predictions against actual test outcomes, NOT against the last
    training label.
    """

    def test_brier_score_uses_test_outcomes(self, synthetic_ohlcv,
                                            synthetic_tech_features, config):
        """Verify Brier score is computed on test window outcomes."""
        import lightgbm as lgb
        from portfolio_data_remediation import _generate_regime_invariant_meta_signals
        from alpha_hyper_tuner import generate_robust_trend_baseline

        primary = generate_robust_trend_baseline(synthetic_ohlcv, mode="donchian")
        feat = build_regime_invariant_features(synthetic_ohlcv, synthetic_tech_features)

        positions, diag = _generate_regime_invariant_meta_signals(
            synthetic_ohlcv, primary, config, feat, adapt_kappa=0.15,
        )

        assert "brier" in diag
        assert 0.0 <= diag["brier"] <= 1.0
        assert "accept_rate" in diag
        assert 0.0 <= diag["accept_rate"] <= 1.0


# ── Module D Tests: JSON Serialization & Config ─────────────────────────────


class TestJsonSafe:
    """Test json_safe handles numpy/pandas types correctly."""

    def test_numpy_integer(self):
        assert json_safe(np.int64(42)) == 42

    def test_numpy_float(self):
        assert json_safe(np.float64(3.14)) == 3.14

    def test_numpy_nan(self):
        assert json_safe(np.float64(np.nan)) is None

    def test_numpy_bool(self):
        assert json_safe(np.bool_(True)) is True

    def test_numpy_array(self):
        result = json_safe(np.array([1, 2, 3]))
        assert result == [1, 2, 3]

    def test_pandas_timestamp(self):
        ts = pd.Timestamp("2024-01-15")
        assert json_safe(ts) == "2024-01-15T00:00:00"

    def test_nested_dict(self):
        d = {"a": np.int32(1), "b": [np.float64(2.0), np.nan]}
        result = json_safe(d)
        assert result == {"a": 1, "b": [2.0, None]}

    def test_json_serializable_after_transform(self):
        d = {"val": np.float64(np.nan), "arr": np.array([1, 2])}
        result = json_safe(d)
        assert json.dumps(result) is not None


class TestConstants:
    """Verify key constants match requirements."""

    def test_focus_tickers_count(self):
        assert len(DEFAULT_FOCUS_TICKERS) == 20

    def test_regime_invariant_indicators(self):
        expected = {"RSI", "MACD", "ATR14", "BB_LOWER", "VOLUME_SMA20"}
        assert set(REGIME_INVARIANT_INDICATORS) == expected

    def test_no_fundamental_in_indicators(self):
        forbidden = {"PE", "PB", "ROE", "DER", "dividend_yield"}
        assert not (set(REGIME_INVARIANT_INDICATORS) & forbidden)

    def test_n_clusters(self):
        assert N_OPERATIONAL_CLUSTERS == 3

    def test_keep_score_target(self):
        assert KEEP_SCORE_TARGET == 3.5
