"""Tests for Fundamental Analysis Engine."""

from __future__ import annotations

from market.analysis.fundamental import FundamentalAnalysisEngine


def test_fundamental_full_data():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(
        "BBCA.JK",
        pe=15.0,
        pb=3.0,
        roe=20.0,
        der=0.5,
        eps_growth=10.0,
        revenue_growth=8.0,
    )
    assert 0 <= result.score <= 100
    assert result.status == "ok"
    assert "pe" in result.breakdown
    assert "pb" in result.breakdown
    assert "roe" in result.breakdown
    assert "der" in result.breakdown
    assert "growth" in result.breakdown


def test_fundamental_low_pe_high_score():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze("CHEAP.JK", pe=5.0, pb=0.5, roe=25.0, der=0.1)
    assert result.breakdown["pe"] == 24.0  # 25 - 5/5 = 24
    assert result.breakdown["pb"] == 23.75  # 25 - 0.5/0.4 = 23.75
    assert result.breakdown["roe"] == 25.0
    assert result.breakdown["der"] == 22.5  # 25 - 0.1*25 = 22.5


def test_fundamental_high_pe_low_score():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze("EXPENSIVE.JK", pe=200, pb=10, roe=2, der=3)
    assert result.breakdown["pe"] == 0.0  # 25 - 200/5 = -15 -> 0
    assert result.breakdown["pb"] == 0.0  # 25 - 10/0.4 = 0 -> 0
    assert result.breakdown["roe"] == 2.0
    assert result.breakdown["der"] == 0.0  # 25 - 3*25 = -50 -> 0


def test_fundamental_missing_data_warning():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze("PARTIAL.JK", pe=10, pb=1.5)
    assert result.status == "warning"
    assert result.breakdown["roe"] == 12.5
    assert result.breakdown["der"] == 12.5
    assert result.breakdown["growth"] == 12.5


def test_fundamental_no_data():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze("NODATA.JK")
    assert result.status == "no_data"
    assert result.score == 62.5  # 5 * 12.5


def test_fundamental_growth_positive():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(
        "GROW.JK", pe=10, pb=1, roe=15, der=0.5,
        eps_growth=20, revenue_growth=15,
    )
    growth_score = result.breakdown["growth"]
    assert growth_score == 25.0  # 12.5 + 17.5 = 30 -> capped at 25


def test_fundamental_growth_negative():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(
        "DECLINE.JK", pe=10, pb=1, roe=15, der=0.5,
        eps_growth=-15, revenue_growth=-10,
    )
    growth_score = result.breakdown["growth"]
    assert growth_score == 0.0  # 12.5 + (-12.5) = 0
