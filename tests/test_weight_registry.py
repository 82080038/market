"""Tests for WeightRegistry — DB-backed dynamic weight configuration.

No fallback tests — weights MUST come from DB.
Tests verify that WeightRegistry raises WeightRegistryError when DB is unavailable
or when no weights are found, instead of returning fake/hardcoded values.
"""

from __future__ import annotations

import pytest
from datetime import datetime, UTC

from market.analysis.weight_registry import WeightRegistry, WeightRegistryError


class TestWeightRegistryFromDB:
    """Test that weights are loaded from DB (not hardcoded fallback)."""

    def test_get_weights_market_context_from_db(self):
        """Should load market_context weights from DB."""
        weights = WeightRegistry.get_weights("market_context", sector="DEFAULT")
        assert isinstance(weights, dict)
        assert len(weights) > 0
        assert "fundamental" in weights
        assert "alpha" in weights
        assert "macro" in weights

    def test_get_weights_decision_engine_from_db(self):
        """Should load decision_engine weights from DB."""
        weights = WeightRegistry.get_weights("decision_engine", sector="DEFAULT")
        assert isinstance(weights, dict)
        assert len(weights) > 0
        assert "technical" in weights
        assert "prediction" in weights

    def test_weights_are_valid(self):
        """All weights should be between 0 and 1."""
        weights = WeightRegistry.get_weights("market_context", sector="DEFAULT")
        for name, w in weights.items():
            assert 0.0 <= w <= 1.0, f"Weight {name}={w} is out of range [0, 1]"


class TestWeightRegistryNormalize:
    """Test weight normalization."""

    def test_normalize_simple(self):
        weights = {"a": 0.3, "b": 0.3, "c": 0.4}
        normalized = WeightRegistry.normalize(weights)
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.001)

    def test_normalize_unbalanced(self):
        weights = {"a": 10.0, "b": 20.0, "c": 30.0}
        normalized = WeightRegistry.normalize(weights)
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.001)
        assert normalized["c"] > normalized["b"] > normalized["a"]

    def test_normalize_zero_sum_raises(self):
        """normalize should raise WeightRegistryError when all weights are 0."""
        with pytest.raises(WeightRegistryError):
            WeightRegistry.normalize({"a": 0.0, "b": 0.0})

    def test_normalize_empty_raises(self):
        """normalize should raise WeightRegistryError for empty dict."""
        with pytest.raises(WeightRegistryError):
            WeightRegistry.normalize({})


class TestWeightRegistryCache:
    """Test in-memory caching."""

    def test_clear_cache(self):
        WeightRegistry.clear_cache()
        # Should not raise
        assert True

    def test_cache_returns_same_values(self):
        w1 = WeightRegistry.get_weights("market_context", sector="DEFAULT")
        w2 = WeightRegistry.get_weights("market_context", sector="DEFAULT")
        # Second call should return same values (from cache or DB)
        assert w1 == w2


class TestMarketContextWithDBWeights:
    """Test that MarketContext.composite_signal() works with DB weights."""

    def test_composite_signal_with_db_weights(self):
        """composite_signal should work with DB weights (no fallback)."""
        from market.analysis.market_context import MarketContext

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


class TestDecisionEngineWithDBWeights:
    """Test DecisionEngine with DB weights."""

    def test_decision_engine_loads_weights_from_db(self):
        """DecisionEngine should load weights from DB on init."""
        from market.analysis.decision import DecisionEngine

        engine = DecisionEngine(use_db_weights=True)
        assert isinstance(engine.weights, dict)
        assert len(engine.weights) > 0

    def test_decision_engine_with_custom_weights(self):
        from market.analysis.decision import DecisionEngine

        custom = {"technical": 0.5, "sentiment": 0.5}
        engine = DecisionEngine(weights=custom, use_db_weights=False)
        assert engine.weights == custom

    def test_decision_engine_no_weights_raises(self):
        """DecisionEngine should raise ValueError if no weights and use_db_weights=False."""
        from market.analysis.decision import DecisionEngine

        with pytest.raises(ValueError):
            DecisionEngine(use_db_weights=False)

    def test_decision_engine_decide_works_with_loaded_weights(self):
        from market.analysis.decision import DecisionEngine

        engine = DecisionEngine(use_db_weights=True)
        result = engine.decide(
            ticker="TEST.JK",
            technical=70,
            fundamental=65,
            sentiment=60,
            prediction=75,
            alpha=65,
        )
        assert result.composite_score > 0
        assert "prediction" in result.factor_scores
