"""Tests for Decision Engine."""

from __future__ import annotations

from market.analysis.decision import DecisionEngine


def test_decision_all_factors():
    engine = DecisionEngine()
    result = engine.decide(
        "BBCA.JK",
        technical=75.0,
        fundamental=80.0,
        macro=60.0,
        global_market=65.0,
        relationship=55.0,
        sentiment=70.0,
    )
    assert 0 <= result.composite_score <= 100
    assert result.recommendation in (
        "strong_buy", "buy", "hold", "reduce", "sell",
    )
    assert len(result.factor_scores) == 6
    assert len(result.contribution) == 6
    assert len(result.explanation) > 0


def test_decision_strong_buy():
    engine = DecisionEngine()
    result = engine.decide(
        "STRONG.JK",
        technical=90.0,
        fundamental=85.0,
        macro=80.0,
        global_market=85.0,
        relationship=80.0,
        sentiment=90.0,
    )
    assert result.recommendation == "strong_buy"
    assert result.composite_score >= 80.0


def test_decision_sell():
    engine = DecisionEngine()
    result = engine.decide(
        "WEAK.JK",
        technical=10.0,
        fundamental=15.0,
        macro=20.0,
        global_market=10.0,
        relationship=15.0,
        sentiment=10.0,
    )
    assert result.recommendation == "sell"
    assert result.composite_score < 30.0


def test_decision_partial_factors():
    engine = DecisionEngine()
    result = engine.decide(
        "PARTIAL.JK",
        technical=70.0,
        fundamental=60.0,
    )
    assert len(result.factor_scores) == 2
    # Weights should be renormalized
    assert result.composite_score > 0


def test_decision_no_factors():
    engine = DecisionEngine()
    result = engine.decide("NODATA.JK")
    assert result.composite_score == 0.0
    assert result.recommendation == "no_data"


def test_decision_custom_weights():
    custom = {
        "technical": 0.50,
        "fundamental": 0.50,
        "macro": 0.0,
        "global": 0.0,
        "relationship": 0.0,
        "sentiment": 0.0,
    }
    engine = DecisionEngine(weights=custom)
    result = engine.decide(
        "CUSTOM.JK",
        technical=80.0,
        fundamental=60.0,
    )
    assert result.composite_score == 70.0  # (80+60)/2


def test_decision_explanation_content():
    engine = DecisionEngine()
    result = engine.decide(
        "EXPLAIN.JK",
        technical=75.0,
        fundamental=30.0,
        sentiment=60.0,
    )
    assert any("Composite score" in e for e in result.explanation)
    assert any("fundamental" in e.lower() for e in result.explanation)


def test_decision_hold_range():
    engine = DecisionEngine()
    result = engine.decide(
        "HOLD.JK",
        technical=50.0,
        fundamental=50.0,
        macro=50.0,
        global_market=50.0,
        relationship=50.0,
        sentiment=50.0,
    )
    assert result.recommendation == "hold"
    assert 45.0 <= result.composite_score < 65.0
