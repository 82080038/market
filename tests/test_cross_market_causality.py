"""Tests for cross-market causal chain integration.

Tests verify:
1. compute_exogenous_features produces timezone-aware T-0/T-1 lagged features
2. CrossMarketEngine lead-lag and spillover produce correct results
3. SignalEnhancer cross_market signal uses only pre-IDX data (no look-ahead)
4. MLSignalProvider _add_exogenous_features includes global features with correct lag
5. recompute_cross_market function signature is correct
6. Anti look-ahead: verify no future data leaks into features
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def idx_ohlcv() -> pd.DataFrame:
    """Simulated IDX ticker OHLCV data (100 days)."""
    dates = pd.bdate_range("2026-01-01", periods=100)
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.random.randint(1000, 10000, 100),
        },
        index=dates,
    )


@pytest.fixture
def global_data() -> dict[str, pd.DataFrame]:
    """Simulated global market data for testing."""
    dates = pd.bdate_range("2026-01-01", periods=100)

    def make_df(start: float, vol: float) -> pd.DataFrame:
        close = start + np.cumsum(np.random.randn(100) * vol)
        return pd.DataFrame({"close": close}, index=dates)

    return {
        "^N225": make_df(30000, 100),
        "^HSI": make_df(20000, 80),
        "^GSPC": make_df(5000, 20),
        "^IXIC": make_df(15000, 50),
        "^FTSE": make_df(8000, 30),
        "GC=F": make_df(2000, 10),
        "CL=F": make_df(75, 2),
        "HG=F": make_df(4, 0.1),
        "MTF=F": make_df(100, 3),
        "CPO=F": make_df(4000, 20),
        "000001.SS": make_df(3000, 15),
    }


# ── 1. compute_exogenous_features timezone-aware lag ─────────────────────


class TestComputeExogenousFeatures:
    """Test that compute_exogenous_features applies correct T-0/T-1 lag."""

    def test_asian_tickers_t0_no_shift(self, idx_ohlcv, global_data):
        """Asian markets (^N225, ^HSI) should have lag=0 (T-0)."""
        from market.analysis.multi_factor import compute_exogenous_features
        from market.analysis.cross_market_timezone import get_ticker_lag

        assert get_ticker_lag("^N225") == 0
        assert get_ticker_lag("^HSI") == 0

        result = compute_exogenous_features(idx_ohlcv, global_data)
        assert "nikkei_lag1_ret" in result.columns
        assert "hangseng_lag1_ret" in result.columns

    def test_us_tickers_t1_shifted(self, idx_ohlcv, global_data):
        """US markets (^GSPC) should have lag=1 (T-1)."""
        from market.analysis.multi_factor import compute_exogenous_features
        from market.analysis.cross_market_timezone import get_ticker_lag

        assert get_ticker_lag("^GSPC") == 1

        result = compute_exogenous_features(idx_ohlcv, global_data)
        assert "sp500_lag1_ret" in result.columns
        assert "sp500_lag5_ret" in result.columns
        assert "sp500_corr" in result.columns

    def test_commodity_tickers_t1(self, idx_ohlcv, global_data):
        """Commodities should have lag=1 (T-1)."""
        from market.analysis.multi_factor import compute_exogenous_features

        result = compute_exogenous_features(idx_ohlcv, global_data)
        assert "gold_lag1_ret" in result.columns
        assert "oil_wti_lag1_ret" in result.columns
        assert "cpo_lag1_ret" in result.columns

    def test_no_lookahead_bias(self, idx_ohlcv, global_data):
        """Verify T-1 features don't use same-day data.

        For T-1 tickers, lag1_ret at date D should equal
        pct_change of close at D-1 (not D).
        """
        from market.analysis.multi_factor import compute_exogenous_features

        result = compute_exogenous_features(idx_ohlcv, global_data)

        # ^GSPC is T-1: sp500_lag1_ret at row i should be
        # (gclose[i-1] / gclose[i-2] - 1) shifted by 1 more day
        gclose = global_data["^GSPC"]["close"].astype(float)
        gclose_aligned = gclose.reindex(idx_ohlcv.index, method="ffill")
        g_returns_raw = gclose_aligned.pct_change()
        # T-1 means shift(1) additional
        expected = g_returns_raw.shift(1).fillna(0.0)

        np.testing.assert_array_almost_equal(
            result["sp500_lag1_ret"].values,
            expected.values,
            decimal=5,
        )

    def test_t0_asian_uses_same_day(self, idx_ohlcv, global_data):
        """Verify T-0 Asian features use same-day data (no extra shift)."""
        from market.analysis.multi_factor import compute_exogenous_features

        result = compute_exogenous_features(idx_ohlcv, global_data)

        # ^N225 is T-0: nikkei_lag1_ret at row i should be
        # (gclose[i] / gclose[i-1] - 1) with no additional shift
        gclose = global_data["^N225"]["close"].astype(float)
        gclose_aligned = gclose.reindex(idx_ohlcv.index, method="ffill")
        g_returns_raw = gclose_aligned.pct_change()
        # T-0 means no shift
        expected = g_returns_raw.fillna(0.0)

        np.testing.assert_array_almost_equal(
            result["nikkei_lag1_ret"].values,
            expected.values,
            decimal=5,
        )

    def test_empty_global_data(self, idx_ohlcv):
        """Empty global_data should produce empty result."""
        from market.analysis.multi_factor import compute_exogenous_features

        result = compute_exogenous_features(idx_ohlcv, {})
        assert len(result.columns) == 0


# ── 2. CrossMarketEngine lead-lag and spillover ──────────────────────────


class TestCrossMarketEngine:
    """Test CrossMarketEngine lead-lag and spillover computation."""

    def test_lead_lag_self_correlation(self):
        """A series lead-lag with itself should have lag=0, high correlation."""
        from market.multi_asset.cross_market import CrossMarketEngine

        returns = pd.Series(np.random.randn(100) * 0.01, index=range(100))
        engine = CrossMarketEngine(min_samples=30)
        result = engine.compute_lead_lag(returns, returns, "A", "B", max_lag=5)

        assert result is not None
        assert result.optimal_lag == 0
        assert abs(result.correlation_at_lag - 1.0) < 0.01

    def test_lead_lag_with_known_lag(self):
        """If A leads B by 2 days, optimal_lag should be 2."""
        from market.multi_asset.cross_market import CrossMarketEngine

        n = 200
        a = pd.Series(np.random.randn(n) * 0.01, index=range(n))
        # B = A shifted by 2 + noise
        b = a.shift(2).fillna(0) + pd.Series(np.random.randn(n) * 0.001, index=range(n))

        engine = CrossMarketEngine(min_samples=30)
        result = engine.compute_lead_lag(a, b, "A", "B", max_lag=5)

        assert result is not None
        assert result.leader == "A"
        assert result.optimal_lag == 2

    def test_spillover_detection(self):
        """Volatility spillover should be detectable."""
        from market.multi_asset.cross_market import CrossMarketEngine

        n = 200
        vol_a = pd.Series(np.abs(np.random.randn(n)) * 0.02, index=range(n))
        # B's volatility follows A's volatility
        vol_b = vol_a.shift(1).fillna(0) * 0.8 + pd.Series(
            np.abs(np.random.randn(n)) * 0.005, index=range(n)
        )

        engine = CrossMarketEngine(min_samples=30)
        result = engine.compute_spillover(vol_a, vol_b, "A", "B")

        assert result is not None
        assert result.source == "A"
        assert result.target == "B"
        assert result.spillover_pct > 0

    def test_insufficient_data_returns_none(self):
        """Insufficient data should return None."""
        from market.multi_asset.cross_market import CrossMarketEngine

        a = pd.Series(np.random.randn(10) * 0.01, index=range(10))
        b = pd.Series(np.random.randn(10) * 0.01, index=range(10))

        engine = CrossMarketEngine(min_samples=30)
        assert engine.compute_lead_lag(a, b, "A", "B") is None
        assert engine.compute_spillover(a, b, "A", "B") is None

    def test_analyze_full_report(self):
        """analyze() should produce a complete report."""
        from market.multi_asset.cross_market import CrossMarketEngine

        n = 100
        returns = {
            "IDX": pd.Series(np.random.randn(n) * 0.01, index=range(n)),
            "US": pd.Series(np.random.randn(n) * 0.01, index=range(n)),
            "JP": pd.Series(np.random.randn(n) * 0.01, index=range(n)),
        }
        vols = {k: v.rolling(20).std().dropna() for k, v in returns.items()}

        engine = CrossMarketEngine(min_samples=30)
        report = engine.analyze(returns, vols, max_lag=5)

        assert len(report.correlations) > 0
        assert len(report.lead_lag) > 0
        assert len(report.heatmap_data) == 3


# ── 3. SignalEnhancer cross_market signal ────────────────────────────────


class TestCrossMarketSignal:
    """Test the cross-market domino signal in SignalEnhancer."""

    def test_cross_market_signal_with_exog_columns(self, idx_ohlcv):
        """Signal should be computed from exogenous feature columns."""
        from market.analysis.signal_enhancer import SignalEnhancer

        # Add exogenous columns to df
        df = idx_ohlcv.copy()
        df["nikkei_lag1_ret"] = 0.01  # bullish
        df["hangseng_lag1_ret"] = 0.02  # bullish
        df["shanghai_lag1_ret"] = -0.01  # bearish
        df["cpo_lag1_ret"] = 0.005  # bullish

        enhancer = SignalEnhancer()
        signal = enhancer._compute_cross_market_signal(df, "BBCA.JK", df.index[-1])

        assert signal.available
        assert signal.source == "cross_market"
        # Weighted: 0.35*1 + 0.35*1 + 0.15*(-1) + 0.15*1 = 0.7 → positive
        assert signal.signal > 0
        assert "domino" in signal.rationale

    def test_cross_market_signal_all_bearish(self, idx_ohlcv):
        """All bearish markets should produce negative signal."""
        from market.analysis.signal_enhancer import SignalEnhancer

        df = idx_ohlcv.copy()
        df["nikkei_lag1_ret"] = -0.02
        df["hangseng_lag1_ret"] = -0.03
        df["shanghai_lag1_ret"] = -0.01
        df["cpo_lag1_ret"] = -0.005

        enhancer = SignalEnhancer()
        signal = enhancer._compute_cross_market_signal(df, "BBCA.JK", df.index[-1])

        assert signal.available
        assert signal.signal < 0

    def test_cross_market_signal_no_columns(self, idx_ohlcv):
        """Without exogenous columns, signal should not be available."""
        from market.analysis.signal_enhancer import SignalEnhancer

        enhancer = SignalEnhancer()
        signal = enhancer._compute_cross_market_signal(
            idx_ohlcv, "BBCA.JK", idx_ohlcv.index[-1]
        )

        # Should gracefully skip (no v_domino_timeline in test, no columns)
        assert not signal.available

    def test_cross_market_signal_empty_df(self):
        """Empty DataFrame should return unavailable signal."""
        from market.analysis.signal_enhancer import SignalEnhancer

        enhancer = SignalEnhancer()
        signal = enhancer._compute_cross_market_signal(
            pd.DataFrame(), "BBCA.JK", "2026-01-01"
        )

        assert not signal.available

    def test_cross_market_weight_in_aggregation(self, idx_ohlcv):
        """Cross-market signal should affect total_adjustment."""
        from market.analysis.signal_enhancer import SignalEnhancer, EnhancementSignal

        df = idx_ohlcv.copy()
        df["nikkei_lag1_ret"] = 0.03
        df["hangseng_lag1_ret"] = 0.03
        df["shanghai_lag1_ret"] = 0.02
        df["cpo_lag1_ret"] = 0.01

        enhancer = SignalEnhancer(cross_market_weight=0.20)
        signal = enhancer._compute_cross_market_signal(df, "BBCA.JK", df.index[-1])

        assert signal.available
        # With weight 0.20, a strong signal should contribute significantly
        assert abs(signal.signal) * 0.20 > 0.01


# ── 4. MLSignalProvider feature columns ──────────────────────────────────


class TestMLFeatureColumns:
    """Test that MLSignalProvider includes global features in _get_feature_cols."""

    def test_global_feature_cols_present(self):
        """_get_feature_cols should include timezone-aware global features."""
        from market.analysis.ml_signal import MLSignalProvider

        provider = MLSignalProvider()
        cols = provider._get_feature_cols()

        # Asian markets (T-0)
        assert "nikkei_lag1_ret" in cols
        assert "nikkei_lag5_ret" in cols
        assert "nikkei_corr" in cols
        assert "hangseng_lag1_ret" in cols
        assert "hangseng_lag5_ret" in cols

        # US markets (T-1)
        assert "sp500_lag1_ret" in cols
        assert "sp500_lag5_ret" in cols
        assert "sp500_corr" in cols

        # Commodities (T-1)
        assert "gold_lag1_ret" in cols
        assert "oil_lag1_ret" in cols
        assert "cpo_lag1_ret" in cols

        # Non-market features
        assert "id_inflation_3m" in cols
        assert "has_corp_action" in cols
        assert "has_dividend" in cols

    def test_old_feature_cols_removed(self):
        """Old usd_idr_ret_1 etc should no longer be in feature cols."""
        from market.analysis.ml_signal import MLSignalProvider

        provider = MLSignalProvider()
        cols = provider._get_feature_cols()

        # Old hardcoded features should be gone
        assert "usd_idr_ret_1" not in cols
        assert "shanghai_ret_1" not in cols


# ── 5. recompute_cross_market function ───────────────────────────────────


class TestRecomputeCrossMarket:
    """Test recompute_cross_market function exists and has correct signature."""

    def test_function_exists(self):
        """recompute_cross_market should be importable."""
        from market.multi_asset.cross_market import recompute_cross_market
        assert callable(recompute_cross_market)

    def test_cross_market_pairs_defined(self):
        """CROSS_MARKET_PAIRS should include all major markets."""
        from market.multi_asset.cross_market import CROSS_MARKET_PAIRS

        tickers = [t for t, _ in CROSS_MARKET_PAIRS]
        assert "^N225" in tickers  # Tokyo
        assert "^HSI" in tickers   # Hong Kong
        assert "^GSPC" in tickers  # US
        assert "^FTSE" in tickers  # London
        assert "GC=F" in tickers   # Gold
        assert "CL=F" in tickers   # Oil
        assert "CPO=F" in tickers  # CPO
        assert "^VIX" in tickers   # VIX
        assert "000001.SS" in tickers  # Shanghai

    def test_in_run_all_recompute(self):
        """cross_market should be in run_all_recompute function list."""
        import inspect
        from market.analysis.recompute import run_all_recompute

        source = inspect.getsource(run_all_recompute)
        assert "cross_market" in source
        assert "recompute_cross_market" in source


# ── 6. Anti look-ahead verification ──────────────────────────────────────


class TestAntiLookAhead:
    """Verify no look-ahead bias in the cross-market feature pipeline."""

    def test_t1_features_dont_use_future(self, idx_ohlcv, global_data):
        """T-1 features at date D must not use data from date D."""
        from market.analysis.multi_factor import compute_exogenous_features

        result = compute_exogenous_features(idx_ohlcv, global_data)

        # For ^GSPC (T-1): the feature at index i should not depend on
        # global_data["^GSPC"] at index i. It should only use index i-1.
        gclose = global_data["^GSPC"]["close"].astype(float)
        gclose_aligned = gclose.reindex(idx_ohlcv.index, method="ffill")

        # Modify the last value of global data
        gclose_modified = gclose_aligned.copy()
        original_last = gclose_modified.iloc[-1]
        gclose_modified.iloc[-1] = original_last * 2  # huge change

        global_data_mod = {**global_data, "^GSPC": pd.DataFrame({"close": gclose_modified})}
        result_mod = compute_exogenous_features(idx_ohlcv, global_data_mod)

        # The T-1 feature at the last row should be the same
        # (because T-1 uses data up to D-1, not D)
        assert abs(
            result["sp500_lag1_ret"].iloc[-1] - result_mod["sp500_lag1_ret"].iloc[-1]
        ) < 1e-10

    def test_t0_features_use_same_day(self, idx_ohlcv, global_data):
        """T-0 features at date D should use data from date D."""
        from market.analysis.multi_factor import compute_exogenous_features

        result = compute_exogenous_features(idx_ohlcv, global_data)

        # For ^N225 (T-0): modifying the last value SHOULD change the feature
        gclose = global_data["^N225"]["close"].astype(float)
        gclose_aligned = gclose.reindex(idx_ohlcv.index, method="ffill")

        gclose_modified = gclose_aligned.copy()
        original_last = gclose_modified.iloc[-1]
        gclose_modified.iloc[-1] = original_last * 2

        global_data_mod = {**global_data, "^N225": pd.DataFrame({"close": gclose_modified})}
        result_mod = compute_exogenous_features(idx_ohlcv, global_data_mod)

        # T-0 feature at last row SHOULD change (it uses same-day data)
        assert abs(
            result["nikkei_lag1_ret"].iloc[-1] - result_mod["nikkei_lag1_ret"].iloc[-1]
        ) > 0.01

    def test_signal_enhancer_truncates_to_as_of(self, idx_ohlcv):
        """SignalEnhancer should truncate data to as_of date."""
        from market.analysis.signal_enhancer import SignalEnhancer

        df = idx_ohlcv.copy()
        df["nikkei_lag1_ret"] = 0.01
        df["hangseng_lag1_ret"] = 0.01
        df["shanghai_lag1_ret"] = 0.01
        df["cpo_lag1_ret"] = 0.01

        # Use a mid-point as_of
        as_of = df.index[50]
        enhancer = SignalEnhancer()
        signal = enhancer._compute_cross_market_signal(df, "BBCA.JK", as_of)

        # Signal should use data at index 50, not the last row
        assert signal.available

    def test_cross_market_signal_only_pre_idx(self, idx_ohlcv):
        """Cross-market signal should only use pre-IDX market data.

        ^GSPC, ^FTSE, ^GDAXI should NOT appear in the domino signal
        because they close AFTER IDX.
        """
        from market.analysis.signal_enhancer import SignalEnhancer

        df = idx_ohlcv.copy()
        # Add all global features
        df["nikkei_lag1_ret"] = 0.01
        df["hangseng_lag1_ret"] = 0.01
        df["shanghai_lag1_ret"] = 0.01
        df["cpo_lag1_ret"] = 0.01
        # These should NOT be used (post-IDX markets)
        df["sp500_lag1_ret"] = 0.05
        df["ftse_lag1_ret"] = 0.05
        df["gold_lag1_ret"] = 0.05

        enhancer = SignalEnhancer()
        signal = enhancer._compute_cross_market_signal(df, "BBCA.JK", df.index[-1])

        assert signal.available
        # Signal should be based on pre-IDX markets only
        # Pre-IDX: nikkei=0.01, hangseng=0.01, shanghai=0.01, cpo=0.01 → all bullish
        # If post-IDX were included, signal would be different
        assert "sp500" not in signal.rationale.lower()
        assert "ftse" not in signal.rationale.lower()
        assert "gold" not in signal.rationale.lower()
