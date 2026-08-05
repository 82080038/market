"""Tests for Advisory Engine."""

from __future__ import annotations

from market.analysis.advisory import AdvisoryEngine


def _make_universe() -> dict[str, dict[str, float | None]]:
    return {
        "BBCA.JK": {
            "technical": 75.0, "fundamental": 80.0,
            "macro": 60.0, "global": 65.0,
            "relationship": 55.0, "sentiment": 70.0,
        },
        "TLKM.JK": {
            "technical": 50.0, "fundamental": 60.0,
            "macro": 55.0, "global": 50.0,
            "relationship": 45.0, "sentiment": 50.0,
        },
        "FAIL.JK": {
            "technical": 10.0, "fundamental": 20.0,
            "macro": 30.0, "global": 25.0,
            "relationship": 15.0, "sentiment": 10.0,
        },
    }


def test_advisory_screen_all_pass():
    engine = AdvisoryEngine()
    results = engine.screen(_make_universe(), min_composite=0.0)
    assert len(results) == 3
    assert all(r.passed for r in results)


def test_advisory_screen_with_filters():
    engine = AdvisoryEngine()
    results = engine.screen(
        _make_universe(),
        min_technical=40.0,
        min_fundamental=40.0,
        min_sentiment=40.0,
        min_composite=50.0,
    )
    passed = [r for r in results if r.passed]
    assert len(passed) == 2  # BBCA and TLKM pass, FAIL.JK doesn't
    assert "FAIL.JK" not in [r.ticker for r in passed]


def test_advisory_screen_strict():
    engine = AdvisoryEngine()
    results = engine.screen(
        _make_universe(),
        min_technical=70.0,
        min_fundamental=70.0,
        min_sentiment=60.0,
        min_composite=65.0,
    )
    passed = [r for r in results if r.passed]
    assert len(passed) == 1
    assert passed[0].ticker == "BBCA.JK"


def test_advisory_generate_report():
    engine = AdvisoryEngine()
    report = engine.generate_report(
        market_regime="growth",
        universe=_make_universe(),
        min_technical=40.0,
        min_fundamental=40.0,
        min_sentiment=40.0,
        min_composite=50.0,
        top_n=5,
    )
    assert report.market_regime == "growth"
    assert report.screened == 3
    assert report.passed == 2
    assert len(report.top_picks) <= 5
    assert report.top_picks[0].composite_score >= report.top_picks[-1].composite_score
    assert "growth" in report.summary


def test_advisory_empty_universe():
    engine = AdvisoryEngine()
    report = engine.generate_report("neutral", {})
    assert report.screened == 0
    assert report.passed == 0
    assert report.top_picks == []


def test_advisory_top_picks_sorted():
    engine = AdvisoryEngine()
    report = engine.generate_report(
        "neutral", _make_universe(), min_composite=0.0, top_n=3,
    )
    scores = [d.composite_score for d in report.top_picks]
    assert scores == sorted(scores, reverse=True)
