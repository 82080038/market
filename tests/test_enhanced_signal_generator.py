"""Tests for EnhancedSignalGenerator (catatan.md TAHAP 5 — Prompt 5.1)."""
from __future__ import annotations

import os

import pytest

from market.advisory.trading_style_advisor import (
    ExperienceLevel,
    RiskTolerance,
    TimeAvailability,
    TradingStyleAdvisor,
    UserProfile,
)
from market.analysis.enhanced_signal_generator import (
    EnhancedSignal,
    EnhancedSignalGenerator,
)
from market.analysis.instrument_profiler import (
    InstrumentBehaviorProfiler,
    InstrumentProfile,
)

_HAS_DB = bool(os.environ.get("DATABASE_URL"))
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")


@pytest.fixture(scope="module")
def setup_profiles():
    """Ensure BBCA.JK profile + default user profile exist."""
    profiler = InstrumentBehaviorProfiler()
    prof = profiler.profile_single("BBCA.JK", lookback_days=756)
    profiler._store_profile(prof)
    advisor = TradingStyleAdvisor()
    advisor.save_profile(UserProfile(
        user_id="default",
        capital=500_000_000,
        risk_tolerance=RiskTolerance.AGGRESSIVE.value,
        time_availability=TimeAvailability.FULL_TIME.value,
        experience_level=ExperienceLevel.EXPERT.value,
        preferred_styles=["swing"],
    ))
    return advisor.get_profile("default")


@pytest.fixture
def generator(setup_profiles):
    return EnhancedSignalGenerator()


class TestEnhanceSignal:
    def test_returns_enhanced_signal(self, generator, setup_profiles):
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.05,
            entry_price=8500, user_profile=setup_profiles,
        )
        assert isinstance(sig, EnhancedSignal)
        assert sig.ticker == "BBCA.JK"
        assert sig.direction == 1
        assert sig.entry_price == 8500

    def test_profile_attached(self, generator, setup_profiles):
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.05, user_profile=setup_profiles,
        )
        assert sig.profile is not None
        assert sig.profile.ticker == "BBCA.JK"
        assert sig.intraday_suitability is not None
        assert sig.swing_suitability is not None
        assert sig.investing_suitability is not None

    def test_suitability_filter_passes(self, generator, setup_profiles):
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.05, user_profile=setup_profiles,
        )
        assert sig.passes_suitability_filter is True
        assert "suitability" in sig.filter_reason.lower()

    def test_suitability_filter_fails_with_high_min(self, setup_profiles):
        gen = EnhancedSignalGenerator(min_suitability_score=9.5)
        sig = gen.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.05, target_style="intraday",
        )
        assert sig.passes_suitability_filter is False
        assert sig.confidence == 0.0

    def test_position_sizing_caps_at_optimal(self, generator, setup_profiles):
        # Force raw_position > optimal_position_size_pct
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.5, user_profile=setup_profiles,
        )
        if sig.profile and sig.profile.optimal_position_size_pct:
            assert sig.adjusted_position_pct is not None
            assert sig.adjusted_position_pct <= sig.profile.optimal_position_size_pct
            assert "capped" in sig.sizing_reasoning.lower()

    def test_position_sizing_passthrough_when_within_optimal(self, generator, setup_profiles):
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.01, user_profile=setup_profiles,
        )
        assert sig.adjusted_position_pct == 0.01
        assert "within" in sig.sizing_reasoning.lower()

    def test_cross_market_sources_populated(self, generator, setup_profiles):
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.05, user_profile=setup_profiles,
        )
        # Should have at least 1 source (^GSPC)
        assert len(sig.cross_market_sources) >= 1
        sources = {s["source"] for s in sig.cross_market_sources}
        assert "^GSPC" in sources

    def test_confidence_in_range(self, generator, setup_profiles):
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.05, user_profile=setup_profiles,
        )
        assert 0.0 <= sig.confidence <= 10.0

    def test_recommended_style_set(self, generator, setup_profiles):
        sig = generator.enhance_signal(
            "BBCA.JK", direction=1, raw_position=0.05, user_profile=setup_profiles,
        )
        assert sig.recommended_style in {"intraday", "swing", "investing"}

    def test_no_profile_passthrough(self, generator):
        # Ticker with no profile — should passthrough
        sig = generator.enhance_signal("NONEXISTENT.X", direction=1, raw_position=0.05)
        assert sig.profile is None
        assert sig.passes_suitability_filter is True
        assert "passthrough" in sig.filter_reason.lower()


class TestEnhanceSignalsBatch:
    def test_batch_processes_all(self, generator, setup_profiles):
        raw = {
            "BBCA.JK": {"direction": 1, "raw_position": 0.05, "entry_price": 8500},
            "BBRI.JK": {"direction": -1, "raw_position": 0.08, "entry_price": 5000},
            "TLKM.JK": {"direction": 0, "raw_position": 0.0},
        }
        sigs = generator.enhance_signals(raw, user_id="default")
        assert len(sigs) == 3
        tickers = {s.ticker for s in sigs}
        assert tickers == {"BBCA.JK", "BBRI.JK", "TLKM.JK"}

    def test_batch_with_explicit_style(self, generator):
        raw = {"BBCA.JK": {"direction": 1, "raw_position": 0.05}}
        sigs = generator.enhance_signals(raw, target_style="swing")
        assert len(sigs) == 1
        assert sigs[0].recommended_style == "swing"

    def test_batch_handles_errors_gracefully(self, generator):
        raw = {
            "BBCA.JK": {"direction": 1, "raw_position": 0.05},
            "BAD.X": {"direction": "invalid", "raw_position": "bad"},  # will fail
        }
        sigs = generator.enhance_signals(raw, target_style="swing")
        # Should still return BBCA.JK signal
        assert any(s.ticker == "BBCA.JK" for s in sigs)


class TestSyntheticProfile:
    def test_suitability_filter_with_synthetic_profile(self):
        """Test filter logic with synthetic InstrumentProfile."""
        from market.analysis.instrument_profiler import InstrumentBehaviorProfiler
        profiler = InstrumentBehaviorProfiler()
        # Store a synthetic profile with low intraday suitability
        prof = InstrumentProfile(
            ticker="SYNTH.JK",
            intraday_suitability=2.0,
            swing_suitability=8.0,
            investing_suitability=9.0,
            optimal_position_size_pct=0.05,
            beta_to_ihsg=1.2,
            profile_confidence=8.0,
            data_points_used=500,
        )
        profiler._store_profile(prof)
        gen = EnhancedSignalGenerator(min_suitability_score=4.0)
        # Should fail intraday filter
        sig = gen.enhance_signal("SYNTH.JK", direction=1, raw_position=0.03, target_style="intraday")
        assert sig.passes_suitability_filter is False
        # Should pass swing filter
        sig2 = gen.enhance_signal("SYNTH.JK", direction=1, raw_position=0.03, target_style="swing")
        assert sig2.passes_suitability_filter is True
