"""Tests for CapitalAwarePositionSizer (catatan.md TAHAP 6 — Prompt 6.1)."""
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
from market.analysis.instrument_profiler import (
    InstrumentBehaviorProfiler,
    InstrumentProfile,
)
from market.risk.capital_aware_sizer import (
    CapitalAwarePositionSizer,
    PositionSizingResult,
)

_HAS_DB = bool(os.environ.get("DATABASE_URL"))
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")


@pytest.fixture(scope="module")
def setup_data():
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
        max_loss_per_trade_pct=2.0,
        max_portfolio_drawdown_pct=15.0,
        preferred_styles=["swing"],
    ))
    return None


@pytest.fixture
def sizer(setup_data):
    return CapitalAwarePositionSizer()


class TestSizePosition:
    def test_buy_signal_returns_result(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            win_rate=0.55, win_loss_ratio=1.5,
            target_style="swing", user_id="default",
        )
        assert isinstance(r, PositionSizingResult)
        assert r.ticker == "BBCA.JK"
        assert r.direction == 1
        assert r.approved is True
        assert r.shares > 0
        assert r.lots > 0
        assert r.value_idr > 0
        assert r.shares % 100 == 0  # whole lots

    def test_hold_signal_rejected(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=0, entry_price=8500, target_style="swing",
        )
        assert r.approved is False
        assert "HOLD" in r.rejection_reason

    def test_no_user_profile_rejected(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            user_id="nonexistent_user",
        )
        assert r.approved is False
        assert "profile" in r.rejection_reason.lower()

    def test_kelly_capped_at_quarter(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            win_rate=0.80, win_loss_ratio=3.0,  # very high → large Kelly
            target_style="swing", user_id="default",
        )
        # Kelly raw should be high but capped at 25% × raw
        assert r.kelly_fraction_raw > r.kelly_fraction_capped
        # Capped should be ≤ max_position_pct (20%)
        assert r.kelly_fraction_capped <= 0.20

    def test_liquidity_cap_applied(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            target_style="swing", user_id="default",
        )
        # liquidity_cap_pct should come from instrument profile
        assert r.liquidity_cap_pct is not None
        assert 0 < r.liquidity_cap_pct <= 0.10

    def test_stop_loss_set(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            target_style="swing", user_id="default",
        )
        assert r.stop_loss_price is not None
        assert r.stop_loss_price < 8500  # below entry for BUY

    def test_reasoning_in_indonesian(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            target_style="swing", user_id="default",
        )
        assert len(r.reasoning_steps) >= 5
        # Should contain Indonesian keywords
        assert any("Modal" in s for s in r.reasoning_steps)
        assert any("Rp" in s for s in r.reasoning_steps)
        assert any("Kelly" in s for s in r.reasoning_steps)

    def test_position_pct_within_portfolio_cap(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            win_rate=0.90, win_loss_ratio=5.0,  # aggressive
            target_style="swing", user_id="default",
        )
        assert r.position_pct_of_portfolio <= 20.0  # max_position_pct

    def test_portfolio_override(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            target_style="swing", user_id="default",
            portfolio_override=10_000_000,  # 10jt only
        )
        # With only 10jt, position should be small
        assert r.value_idr <= 10_000_000
        assert r.available_capital == 10_000_000


class TestSizeMultiple:
    def test_multiple_signals_sized(self, sizer):
        sigs = [
            {"ticker": "BBCA.JK", "direction": 1, "entry_price": 8500,
             "win_rate": 0.55, "win_loss_ratio": 1.5, "target_style": "swing",
             "raw_position": 0.05},
            {"ticker": "BBRI.JK", "direction": 1, "entry_price": 5000,
             "win_rate": 0.58, "win_loss_ratio": 1.4, "target_style": "swing",
             "raw_position": 0.04},
        ]
        results = sizer.size_multiple(sigs, user_id="default")
        assert len(results) == 2
        assert all(r.ticker in {"BBCA.JK", "BBRI.JK"} for r in results)

    def test_capital_depleted_per_style(self, sizer):
        # Many swing signals — capital should deplete
        sigs = [
            {"ticker": "BBCA.JK", "direction": 1, "entry_price": 8500,
             "win_rate": 0.55, "win_loss_ratio": 1.5, "target_style": "swing",
             "raw_position": 0.5},
        ] * 20  # 20 signals
        results = sizer.size_multiple(sigs, user_id="default")
        approved = [r for r in results if r.approved]
        rejected = [r for r in results if not r.approved]
        # Some should be rejected when capital runs out
        assert len(rejected) > 0 or sum(r.value_idr for r in approved) <= 200_000_000

    def test_hold_in_multiple(self, sizer):
        sigs = [
            {"ticker": "BBCA.JK", "direction": 0, "entry_price": 8500,
             "target_style": "swing"},
        ]
        results = sizer.size_multiple(sigs, user_id="default")
        assert results[0].approved is False


class TestKellyMath:
    def test_even_odds_negative_kelly(self, sizer):
        # win_rate=0.4, ratio=1.0 → negative Kelly → 0 position
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            win_rate=0.40, win_loss_ratio=1.0,
            target_style="swing", user_id="default",
        )
        # Kelly raw should be 0 or negative → floored to 0
        assert r.kelly_fraction_raw == 0.0

    def test_favorable_kelly_positive(self, sizer):
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            win_rate=0.60, win_loss_ratio=2.0,
            target_style="swing", user_id="default",
        )
        # f* = (0.6*2 - 0.4) / 2 = 0.4
        assert r.kelly_fraction_raw == pytest.approx(0.4, abs=0.01)
        # Capped at 25% → 0.1
        assert r.kelly_fraction_capped == pytest.approx(0.1, abs=0.01)
