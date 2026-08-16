"""Tests for TradingStyleAdvisor (catatan.md TAHAP 4 — Prompt 4.1)."""
from __future__ import annotations

import os

import pytest

from market.advisory.trading_style_advisor import (
    AllocationBreakdown,
    ExperienceLevel,
    RiskTolerance,
    StyleRecommendation,
    TimeAvailability,
    TradingStyleAdvisor,
    UserProfile,
)

_HAS_DB = bool(os.environ.get("DATABASE_URL"))
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")


@pytest.fixture
def advisor():
    return TradingStyleAdvisor()


@pytest.fixture
def aggressive_profile():
    return UserProfile(
        user_id="test_agg",
        capital=500_000_000,
        risk_tolerance=RiskTolerance.AGGRESSIVE.value,
        time_availability=TimeAvailability.FULL_TIME.value,
        experience_level=ExperienceLevel.EXPERT.value,
        max_loss_per_trade_pct=2.0,
        max_portfolio_drawdown_pct=15.0,
        preferred_styles=["swing"],
        preferred_sectors=["Financials"],
    )


@pytest.fixture
def beginner_profile():
    return UserProfile(
        user_id="test_beg",
        capital=50_000_000,
        risk_tolerance=RiskTolerance.CONSERVATIVE.value,
        time_availability=TimeAvailability.EVENINGS.value,
        experience_level=ExperienceLevel.BEGINNER.value,
    )


class TestSaveAndGetProfile:
    def test_save_and_retrieve(self, advisor, aggressive_profile):
        advisor.save_profile(aggressive_profile)
        got = advisor.get_profile("test_agg")
        assert got is not None
        assert got.user_id == "test_agg"
        assert got.capital == 500_000_000
        assert got.risk_tolerance == "AGGRESSIVE"
        assert got.experience_level == "EXPERT"
        assert "swing" in got.preferred_styles

    def test_get_nonexistent_returns_none(self, advisor):
        got = advisor.get_profile("nonexistent_user_xyz")
        assert got is None


class TestCalculateAllocation:
    def test_aggressive_full_time_expert_favors_intraday(self, advisor, aggressive_profile):
        alloc = advisor.calculate_allocation(aggressive_profile)
        assert alloc.intraday_pct + alloc.swing_pct + alloc.investing_pct == pytest.approx(100, abs=0.1)
        # Aggressive + full_time + expert → intraday should be high
        assert alloc.intraday_pct >= 30
        # Investing should be lowest for aggressive expert
        assert alloc.investing_pct <= alloc.intraday_pct

    def test_beginner_conservative_evenings_favors_investing(self, advisor, beginner_profile):
        alloc = advisor.calculate_allocation(beginner_profile)
        assert alloc.intraday_pct + alloc.swing_pct + alloc.investing_pct == pytest.approx(100, abs=0.1)
        # Beginner + conservative + evenings → investing should dominate
        assert alloc.investing_pct > alloc.intraday_pct
        assert alloc.investing_pct > alloc.swing_pct
        assert alloc.investing_pct >= 40

    def test_capital_split_correctly(self, advisor, aggressive_profile):
        alloc = advisor.calculate_allocation(aggressive_profile)
        total = alloc.intraday_capital + alloc.swing_capital + alloc.investing_capital
        assert total == pytest.approx(aggressive_profile.capital, rel=0.01)

    def test_minimum_5_pct_floor(self, advisor):
        # Extreme profile that would otherwise give 0% to a style
        prof = UserProfile(
            user_id="test_extreme",
            capital=10_000_000,
            risk_tolerance=RiskTolerance.AGGRESSIVE.value,
            time_availability=TimeAvailability.FULL_TIME.value,
            experience_level=ExperienceLevel.EXPERT.value,
        )
        alloc = advisor.calculate_allocation(prof)
        # All styles should be at least 5%
        assert alloc.intraday_pct >= 5
        assert alloc.swing_pct >= 5
        assert alloc.investing_pct >= 5

    def test_preferred_styles_boost(self, advisor):
        prof_no_pref = UserProfile(
            user_id="test_nopref",
            capital=200_000_000,
            risk_tolerance=RiskTolerance.MODERATE.value,
            time_availability=TimeAvailability.PART_TIME.value,
            experience_level=ExperienceLevel.INTERMEDIATE.value,
        )
        prof_pref = UserProfile(
            user_id="test_pref",
            capital=200_000_000,
            risk_tolerance=RiskTolerance.MODERATE.value,
            time_availability=TimeAvailability.PART_TIME.value,
            experience_level=ExperienceLevel.INTERMEDIATE.value,
            preferred_styles=["investing"],
        )
        a1 = advisor.calculate_allocation(prof_no_pref)
        a2 = advisor.calculate_allocation(prof_pref)
        # Preferred investing should boost its allocation
        assert a2.investing_pct > a1.investing_pct


class TestRecommendStyle:
    def test_recommend_returns_full_object(self, advisor, aggressive_profile):
        advisor.save_profile(aggressive_profile)
        rec = advisor.recommend_style("test_agg")
        assert isinstance(rec, StyleRecommendation)
        assert rec.user_id == "test_agg"
        assert isinstance(rec.allocations, AllocationBreakdown)
        assert 1.0 <= rec.confidence <= 10.0
        assert rec.primary_style in {"intraday", "swing", "investing"}
        assert len(rec.reasons) >= 4
        assert "Berdasarkan profil" in rec.reasoning_summary

    def test_reasons_contain_all_types(self, advisor, aggressive_profile):
        advisor.save_profile(aggressive_profile)
        rec = advisor.recommend_style("test_agg")
        types = {r["reason_type"] for r in rec.reasons}
        assert "capital_match" in types
        assert "risk_match" in types
        assert "time_match" in types
        assert "experience_match" in types

    def test_reasoning_is_indonesian(self, advisor, aggressive_profile):
        advisor.save_profile(aggressive_profile)
        rec = advisor.recommend_style("test_agg")
        # Should contain Indonesian keywords
        assert "Rp" in rec.reasoning_summary or "modal" in rec.reasoning_summary.lower()
        for r in rec.reasons:
            assert len(r["reason_text"]) > 10

    def test_recommend_without_profile_raises(self, advisor):
        with pytest.raises(ValueError, match="No profile"):
            advisor.recommend_style("definitely_nonexistent_user")


class TestConfidence:
    def test_expert_high_confidence(self, advisor, aggressive_profile):
        advisor.save_profile(aggressive_profile)
        rec = advisor.recommend_style("test_agg")
        # Expert + aggressive + full_time + explicit preference → high confidence
        assert rec.confidence >= 7.0

    def test_beginner_aggressive_penalized(self, advisor):
        # Beginner + aggressive is risky combination → lower confidence
        prof = UserProfile(
            user_id="test_beg_agg",
            capital=100_000_000,
            risk_tolerance=RiskTolerance.AGGRESSIVE.value,
            time_availability=TimeAvailability.FULL_TIME.value,
            experience_level=ExperienceLevel.BEGINNER.value,
        )
        advisor.save_profile(prof)
        rec = advisor.recommend_style("test_beg_agg")
        assert rec.confidence <= 7.0  # penalized


class TestGenerateReasoning:
    def test_generate_reasoning_returns_string(self, advisor, aggressive_profile):
        advisor.save_profile(aggressive_profile)
        rec = advisor.recommend_style("test_agg")
        text = advisor.generate_reasoning(rec)
        assert isinstance(text, str)
        assert len(text) > 50
