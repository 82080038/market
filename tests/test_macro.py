"""Tests for Macro Economic Engine."""

from __future__ import annotations

from market.analysis.macro import MacroEconomicEngine


def test_macro_full_data():
    engine = MacroEconomicEngine()
    result = engine.analyze(
        us10y_yield=4.0,
        us10y_prev=4.5,
        gold_price=2000,
        gold_prev=1950,
        oil_price=75,
        oil_prev=70,
        usd_idr=15800,
        usd_idr_prev=16000,
    )
    assert 0 <= result.score <= 100
    assert result.regime in ("tightening", "easing", "growth", "slowdown", "neutral")
    assert "us10y" in result.breakdown
    assert "gold" in result.breakdown
    assert "oil" in result.breakdown
    assert "usd_idr" in result.breakdown


def test_macro_easing_regime():
    engine = MacroEconomicEngine()
    result = engine.analyze(
        us10y_yield=3.5,
        us10y_prev=4.0,
        oil_price=75,
        oil_prev=70,
        usd_idr=15800,
        usd_idr_prev=16000,
    )
    assert result.regime == "easing"


def test_macro_tightening_regime():
    engine = MacroEconomicEngine()
    result = engine.analyze(
        us10y_yield=4.5,
        us10y_prev=4.0,
    )
    assert result.regime == "tightening"


def test_macro_growth_regime():
    engine = MacroEconomicEngine()
    result = engine.analyze(
        us10y_yield=4.0,
        us10y_prev=4.0,
        oil_price=80,
        oil_prev=70,
        usd_idr=15500,
        usd_idr_prev=16000,
    )
    assert result.regime == "growth"


def test_macro_slowdown_regime():
    engine = MacroEconomicEngine()
    result = engine.analyze(
        us10y_yield=4.0,
        us10y_prev=4.0,
        oil_price=60,
        oil_prev=70,
        usd_idr=16500,
        usd_idr_prev=16000,
    )
    assert result.regime == "slowdown"


def test_macro_neutral_regime():
    engine = MacroEconomicEngine()
    result = engine.analyze(
        us10y_yield=4.0,
        us10y_prev=4.0,
        oil_price=75,
        oil_prev=75,
        usd_idr=16000,
        usd_idr_prev=16000,
    )
    assert result.regime == "neutral"


def test_macro_us10y_score():
    engine = MacroEconomicEngine()
    result = engine.analyze(us10y_yield=4.0)
    assert result.breakdown["us10y"] == 15.0  # 25 - 4*2.5 = 15


def test_macro_oil_in_range():
    engine = MacroEconomicEngine()
    result = engine.analyze(oil_price=75)
    assert result.breakdown["oil"] == 25.0


def test_macro_oil_out_of_range():
    engine = MacroEconomicEngine()
    result = engine.analyze(oil_price=50)
    assert result.breakdown["oil"] == 15.0


def test_macro_gold_small_change():
    engine = MacroEconomicEngine()
    result = engine.analyze(gold_price=2050, gold_prev=2000)
    assert result.breakdown["gold"] == 25.0  # 2.5% < 5%


def test_macro_gold_large_change():
    engine = MacroEconomicEngine()
    result = engine.analyze(gold_price=2300, gold_prev=2000)
    assert result.breakdown["gold"] == 0.0  # 15% >= 10%


def test_macro_missing_data():
    engine = MacroEconomicEngine()
    result = engine.analyze()
    assert result.score == 50.0  # 4 * 12.5
    assert result.regime == "neutral"
