"""Tests for RecommendationEngine (catatan.md TAHAP 7 — Prompt 7.1)."""
from __future__ import annotations

import json
import os

import pytest

from market.advisory.trading_style_advisor import (
    ExperienceLevel,
    RiskTolerance,
    TimeAvailability,
    TradingStyleAdvisor,
    UserProfile,
)
from market.analysis.instrument_profiler import InstrumentBehaviorProfiler
from market.analysis.recommendation_engine import (
    Recommendation,
    RecommendationEngine,
    RecommendationReport,
)

_HAS_DB = bool(os.environ.get("DATABASE_URL"))
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")


@pytest.fixture(scope="module")
def setup_data():
    """Ensure profiles exist for test tickers + default user."""
    profiler = InstrumentBehaviorProfiler()
    for t in ["BBCA.JK", "BBRI.JK", "TLKM.JK"]:
        try:
            prof = profiler.profile_single(t, lookback_days=756)
            profiler._store_profile(prof)
        except Exception:
            pass
    advisor = TradingStyleAdvisor()
    advisor.save_profile(UserProfile(
        user_id="default",
        capital=500_000_000,
        risk_tolerance=RiskTolerance.AGGRESSIVE.value,
        time_availability=TimeAvailability.FULL_TIME.value,
        experience_level=ExperienceLevel.EXPERT.value,
        max_loss_per_trade_pct=2.0,
        preferred_styles=["swing"],
    ))
    return None


@pytest.fixture
def engine(setup_data):
    return RecommendationEngine()


@pytest.fixture
def sample_raw_signals():
    return {
        "BBCA.JK": {"direction": 1, "raw_position": 0.05, "entry_price": 8500,
                    "win_rate": 0.55, "win_loss_ratio": 1.5},
        "BBRI.JK": {"direction": 1, "raw_position": 0.04, "entry_price": 5000,
                    "win_rate": 0.58, "win_loss_ratio": 1.4},
        "TLKM.JK": {"direction": -1, "raw_position": 0.03, "entry_price": 2800,
                    "win_rate": 0.52, "win_loss_ratio": 1.8},
        "ASII.JK": {"direction": 0, "raw_position": 0.0, "entry_price": 5200},
    }


class TestGenerateReport:
    def test_returns_report(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        assert isinstance(report, RecommendationReport)
        assert report.user_id == "default"
        assert len(report.recommendations) == 4
        assert report.generated_at != ""

    def test_recommendations_have_required_fields(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        for r in report.recommendations:
            assert isinstance(r, Recommendation)
            assert r.ticker in sample_raw_signals
            assert r.direction in {"BUY", "SELL", "HOLD"}
            assert r.trading_style in {"intraday", "swing", "investing"}
            assert 0.0 <= r.confidence <= 10.0
            assert len(r.reasoning) > 20
            assert r.generated_at != ""

    def test_buy_signals_have_entry_target_stop(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        buy = [r for r in report.recommendations if r.direction == "BUY"]
        assert len(buy) >= 2
        for r in buy:
            if r.approved:
                assert r.entry_price is not None and r.entry_price > 0
                assert r.target_price is not None and r.target_price > r.entry_price
                assert r.stop_loss_price is not None and r.stop_loss_price < r.entry_price

    def test_sell_signals_have_target_below_entry(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        sell = [r for r in report.recommendations if r.direction == "SELL"]
        assert len(sell) >= 1
        for r in sell:
            if r.approved:
                assert r.target_price is not None and r.target_price < r.entry_price
                assert r.stop_loss_price is not None and r.stop_loss_price > r.entry_price

    def test_hold_signal_rejected(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        hold = [r for r in report.recommendations if r.direction == "HOLD"]
        assert len(hold) == 1
        assert hold[0].approved is False
        assert "HOLD" in hold[0].rejection_reason

    def test_position_sizing_in_lots(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        for r in report.recommendations:
            if r.approved:
                assert r.shares > 0
                assert r.lots > 0
                assert r.shares % 100 == 0  # whole lots
                assert r.shares == r.lots * 100
                assert r.value_idr > 0

    def test_reward_risk_ratio_positive(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        for r in report.recommendations:
            if r.approved and r.direction != "HOLD":
                assert r.reward_risk_ratio > 0
                # Target 2× vol, stop 1× vol → R/R should be ~2.0
                assert 1.5 <= r.reward_risk_ratio <= 2.5


class TestPortfolioAggregates:
    def test_portfolio_summary_populated(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        assert "total_recommendations" in report.portfolio_summary
        assert report.portfolio_summary["total_recommendations"] == 4
        assert report.portfolio_summary["buy_signals"] >= 2
        assert report.portfolio_summary["sell_signals"] >= 1
        assert report.portfolio_summary["hold_signals"] == 1

    def test_totals_non_negative(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        assert report.total_allocated_idr >= 0
        assert report.total_risk_idr >= 0
        assert report.total_potential_profit_idr >= 0
        assert report.total_potential_loss_idr >= 0

    def test_average_confidence_in_range(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        if report.recommendations:
            assert 0.0 <= report.average_confidence <= 10.0

    def test_style_breakdown(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        assert len(report.style_breakdown) > 0
        assert sum(report.style_breakdown.values()) == 4


class TestOutputFormats:
    def test_to_dict_serializable(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "recommendations" in d
        assert len(d["recommendations"]) == 4
        # Should be JSON serializable
        json.dumps(d, default=str)

    def test_to_json_returns_string(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        s = report.to_json()
        assert isinstance(s, str)
        parsed = json.loads(s)
        assert parsed["user_id"] == "default"

    def test_to_text_summary_indonesian(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        text = report.to_text_summary()
        assert isinstance(text, str)
        assert "LAPORAN REKOMENDASI" in text
        assert "Rp" in text
        assert "BUY" in text or "SELL" in text
        # Per-ticker section
        assert "BBCA.JK" in text
        assert "Position:" in text
        assert "Confidence:" in text


class TestReasoning:
    def test_reasoning_contains_profile_info(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        bbca = next(r for r in report.recommendations if r.ticker == "BBCA.JK")
        assert "Volatility regime" in bbca.reasoning or "volatility" in bbca.reasoning.lower()
        assert "liquidity" in bbca.reasoning.lower()

    def test_reasoning_contains_cross_market(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        bbca = next(r for r in report.recommendations if r.ticker == "BBCA.JK")
        assert "Cross-market" in bbca.reasoning or "GSPC" in bbca.reasoning

    def test_reasoning_contains_kelly(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        for r in report.recommendations:
            if r.approved and r.direction != "HOLD":
                assert "Kelly" in r.reasoning
                break

    def test_supporting_data_has_cross_market_sources(self, engine, sample_raw_signals):
        report = engine.generate_report(sample_raw_signals, user_id="default")
        bbca = next(r for r in report.recommendations if r.ticker == "BBCA.JK")
        assert "cross_market_sources" in bbca.supporting_data
        assert len(bbca.supporting_data["cross_market_sources"]) >= 1


class TestForcedStyle:
    def test_force_swing_style(self, engine, sample_raw_signals):
        report = engine.generate_report(
            sample_raw_signals, user_id="default", target_style="swing",
        )
        for r in report.recommendations:
            assert r.trading_style == "swing"

    def test_force_investing_style(self, engine, sample_raw_signals):
        report = engine.generate_report(
            sample_raw_signals, user_id="default", target_style="investing",
        )
        for r in report.recommendations:
            assert r.trading_style == "investing"
