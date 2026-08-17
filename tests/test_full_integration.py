"""Tests for full prediction ↔ decision integration.

Tests that:
1. MarketContext has all 20+ fields populated
2. composite_signal() includes all 20 signals
3. DecisionEngine has 13 factors
4. decide_with_db() auto-fetches scores
5. prediction_score_from_prediction() converts correctly
6. fetch_scores_from_db() returns available scores
"""

from __future__ import annotations

import pytest
from datetime import date
from dataclasses import dataclass

from market.analysis.market_context import MarketContext, MarketContextProvider
from market.analysis.decision import DecisionEngine, DEFAULT_WEIGHTS


class TestMarketContextFields:
    """Test that MarketContext has all new fields."""

    def test_alpha_fields_exist(self):
        ctx = MarketContext()
        assert hasattr(ctx, "alpha_mean_reversion")
        assert hasattr(ctx, "alpha_reversal")
        assert hasattr(ctx, "alpha_ewma_momentum")
        assert hasattr(ctx, "alpha_regime_switch")

    def test_policy_event_fields_exist(self):
        ctx = MarketContext()
        assert hasattr(ctx, "policy_event_signal")
        assert hasattr(ctx, "policy_event_count")

    def test_sector_rotation_field_exists(self):
        ctx = MarketContext()
        assert hasattr(ctx, "sector_rotation_signal")

    def test_pairs_trading_field_exists(self):
        ctx = MarketContext()
        assert hasattr(ctx, "pairs_trading_zscore")

    def test_meta_label_field_exists(self):
        ctx = MarketContext()
        assert hasattr(ctx, "meta_label_probability")

    def test_volume_fields_exist(self):
        ctx = MarketContext()
        assert hasattr(ctx, "volume_ofi")
        assert hasattr(ctx, "volume_vwap_deviation")
        assert hasattr(ctx, "volume_obv_divergence")

    def test_seasonal_fields_exist(self):
        ctx = MarketContext()
        assert hasattr(ctx, "seasonal_score")
        assert hasattr(ctx, "seasonal_pattern_name")

    def test_earnings_fields_exist(self):
        ctx = MarketContext()
        assert hasattr(ctx, "earnings_days_to_report")
        assert hasattr(ctx, "earnings_expected_surprise")

    def test_profile_fields_exist(self):
        ctx = MarketContext()
        assert hasattr(ctx, "profile_volatility_regime")
        assert hasattr(ctx, "profile_liquidity_score")
        assert hasattr(ctx, "profile_overnight_gap_pct")

    def test_dcc_garch_field_exists(self):
        ctx = MarketContext()
        assert hasattr(ctx, "dcc_garch_corr_global")

    def test_granger_fields_exist(self):
        ctx = MarketContext()
        assert hasattr(ctx, "granger_cause_count")
        assert hasattr(ctx, "granger_top_cause")

    def test_is_available_checks_new_fields(self):
        ctx = MarketContext()
        ctx.alpha_mean_reversion = 0.5
        assert ctx.is_available is True

    def test_is_available_false_when_all_none(self):
        ctx = MarketContext()
        assert ctx.is_available is False


class TestMarketContextSignals:
    """Test signal computation methods."""

    def test_alpha_composite_signal_with_values(self):
        ctx = MarketContext()
        ctx.alpha_mean_reversion = 0.5
        ctx.alpha_reversal = -0.3
        ctx.alpha_ewma_momentum = 0.8
        ctx.alpha_regime_switch = 0.1
        signal = ctx.alpha_composite_signal()
        assert -1.0 <= signal <= 1.0
        assert signal == pytest.approx(0.275, abs=0.01)

    def test_alpha_composite_signal_no_values(self):
        ctx = MarketContext()
        assert ctx.alpha_composite_signal() == 0.0

    def test_policy_event_signal_value(self):
        ctx = MarketContext()
        ctx.policy_event_signal = 0.8
        ctx.policy_event_count = 3
        signal = ctx.policy_event_signal_value()
        assert 0 < signal <= 1.0

    def test_sector_rotation_signal_value(self):
        ctx = MarketContext()
        ctx.sector_rotation_signal = 0.6
        assert ctx.sector_rotation_signal_value() == 0.6

    def test_pairs_trading_signal_value(self):
        ctx = MarketContext()
        ctx.pairs_trading_zscore = 2.5
        signal = ctx.pairs_trading_signal_value()
        assert signal < 0  # High Z-score → short signal

    def test_volume_signal_with_ofi(self):
        ctx = MarketContext()
        ctx.volume_ofi = 0.3
        signal = ctx.volume_signal()
        assert signal > 0

    def test_seasonal_signal(self):
        ctx = MarketContext()
        ctx.seasonal_score = 0.7
        assert ctx.seasonal_signal() == 0.7

    def test_earnings_signal_pre_earnings(self):
        ctx = MarketContext()
        ctx.earnings_days_to_report = 3
        assert ctx.earnings_signal() == -0.15  # Pre-earnings uncertainty

    def test_earnings_signal_post_earnings(self):
        ctx = MarketContext()
        ctx.earnings_days_to_report = 0
        ctx.earnings_expected_surprise = 5.0
        signal = ctx.earnings_signal()
        assert signal > 0  # Positive surprise → bullish drift

    def test_causal_signal_neutral(self):
        ctx = MarketContext()
        ctx.granger_cause_count = 5
        assert ctx.causal_signal() == 0.0  # Neutral without direction data

    def test_meta_label_signal(self):
        ctx = MarketContext()
        ctx.meta_label_probability = 0.8
        signal = ctx.meta_label_signal()
        assert signal == pytest.approx(0.6, abs=0.01)

    def test_composite_signal_includes_all_signals(self):
        """Verify composite_signal doesn't error with all fields set."""
        ctx = MarketContext()
        ctx.pe_ratio = 15.0
        ctx.roe = 0.15
        ctx.dividend_yield = 5.0
        ctx.der = 1.0
        ctx.vix = 18.0
        ctx.us_10y_yield = 3.5
        ctx.fear_greed_index = 60
        ctx.foreign_net_flow_5d = 5e9
        ctx.corr_us = 0.4
        ctx.corr_ihsg = 0.6
        ctx.ml_signal = 0.3
        ctx.news_sentiment = 0.2
        ctx.news_count = 5
        ctx.commodity_signal = 0.1
        ctx.global_sentiment = 0.2
        ctx.esg_score = 70
        ctx.governance_score = 75
        ctx.has_whistleblowing = True
        ctx.has_risk_committee = True
        ctx.astronacci_signal = 0.1
        ctx.is_pre_holiday = True
        ctx.pre_holiday_expected_return = 0.3
        ctx.alpha_mean_reversion = 0.4
        ctx.alpha_reversal = 0.2
        ctx.policy_event_signal = 0.5
        ctx.policy_event_count = 2
        ctx.sector_rotation_signal = 0.3
        ctx.volume_ofi = 0.2
        ctx.seasonal_score = 0.4
        ctx.earnings_days_to_report = 10
        ctx.granger_cause_count = 3
        ctx.meta_label_probability = 0.7
        ctx.sector = "Financial Services"

        signal = ctx.composite_signal()
        assert -1.0 <= signal <= 1.0


class TestDecisionEngineNewFactors:
    """Test DecisionEngine with new factors."""

    def test_default_weights_has_13_factors(self):
        assert "technical" in DEFAULT_WEIGHTS
        assert "fundamental" in DEFAULT_WEIGHTS
        assert "macro" in DEFAULT_WEIGHTS
        assert "global" in DEFAULT_WEIGHTS
        assert "relationship" in DEFAULT_WEIGHTS
        assert "sentiment" in DEFAULT_WEIGHTS
        assert "holiday" in DEFAULT_WEIGHTS
        assert "prediction" in DEFAULT_WEIGHTS
        assert "alpha" in DEFAULT_WEIGHTS
        assert "policy_event" in DEFAULT_WEIGHTS
        assert "sector_rotation" in DEFAULT_WEIGHTS
        assert "seasonal" in DEFAULT_WEIGHTS
        assert "earnings" in DEFAULT_WEIGHTS

    def test_weights_sum_approximately_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.05  # Allow small deviation

    def test_decide_with_prediction_factor(self):
        engine = DecisionEngine()
        result = engine.decide(
            ticker="BBCA.JK",
            technical=70,
            fundamental=65,
            sentiment=60,
            prediction=75,
        )
        assert result.ticker == "BBCA.JK"
        assert "prediction" in result.factor_scores
        assert result.composite_score > 0

    def test_decide_with_all_new_factors(self):
        engine = DecisionEngine()
        result = engine.decide(
            ticker="BBCA.JK",
            technical=70,
            fundamental=65,
            macro=55,
            global_market=60,
            relationship=50,
            sentiment=60,
            holiday=55,
            prediction=75,
            alpha=65,
            policy_event=52,
            sector_rotation=58,
            seasonal=54,
            earnings=50,
        )
        assert len(result.factor_scores) == 13
        assert result.composite_score > 0
        assert result.recommendation in ["strong_buy", "buy", "hold", "reduce", "sell"]

    def test_prediction_score_from_prediction_up(self):
        @dataclass
        class MockPrediction:
            predicted_direction: str = "up"
            confidence: float = 0.8
            predicted_return_pct: float = 3.5

        score = DecisionEngine.prediction_score_from_prediction(MockPrediction())
        assert score is not None
        assert score > 50  # Bullish prediction → above neutral

    def test_prediction_score_from_prediction_down(self):
        @dataclass
        class MockPrediction:
            predicted_direction: str = "down"
            confidence: float = 0.7
            predicted_return_pct: float = -2.5

        score = DecisionEngine.prediction_score_from_prediction(MockPrediction())
        assert score is not None
        assert score < 50  # Bearish prediction → below neutral

    def test_prediction_score_from_prediction_flat(self):
        @dataclass
        class MockPrediction:
            predicted_direction: str = "flat"
            confidence: float = 0.5
            predicted_return_pct: float = 0.0

        score = DecisionEngine.prediction_score_from_prediction(MockPrediction())
        assert score == 50.0  # Neutral

    def test_decide_with_db_returns_result(self):
        """Test that decide_with_db returns a valid DecisionResult."""
        engine = DecisionEngine(db_url=None)  # No DB → graceful degradation
        result = engine.decide_with_db("TEST.JK")
        assert result.ticker == "TEST.JK"
        # Without DB, should return no_data or minimal result
        assert result.recommendation in ["no_data", "hold"]

    def test_fetch_scores_from_db_no_connection(self):
        """Test that fetch_scores_from_db handles no DB gracefully."""
        engine = DecisionEngine(db_url=None)
        scores = engine.fetch_scores_from_db("TEST.JK")
        assert isinstance(scores, dict)
        # Without DB, should return empty or only computable scores
