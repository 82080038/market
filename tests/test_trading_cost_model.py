"""Tests for TradingCostModel and cost-aware integration.

Tests cover:
1. TradingCostModel — rate calculations, IDR cost breakdowns, net profit/loss.
2. CapitalAwarePositionSizer — cost fields populated in PositionSizingResult.
3. EnhancedSignalGenerator — cost filter rejects sub-break-even signals.
4. RecommendationEngine — net R/R and cost fields in Recommendation.
"""
from __future__ import annotations

import os

import pytest

from market.risk.cost_model import (
    CostBreakdown,
    RoundTripCost,
    TradingCostModel,
)

_HAS_DB = bool(os.environ.get("DATABASE_URL"))


# ── TradingCostModel unit tests (no DB needed) ──────────────────────────────


class TestTradingCostModelRates:
    def test_default_rates(self):
        m = TradingCostModel()
        assert m.commission_rate == 0.0015
        assert m.sales_tax_rate == 0.001
        assert m.slippage_rate == 0.0005

    def test_entry_cost_rate(self):
        m = TradingCostModel()
        # commission + slippage = 0.15% + 0.05% = 0.20%
        assert m.entry_cost_rate() == pytest.approx(0.002)

    def test_exit_cost_rate(self):
        m = TradingCostModel()
        # commission + sales_tax + slippage = 0.15% + 0.10% + 0.05% = 0.30%
        assert m.exit_cost_rate() == pytest.approx(0.003)

    def test_round_trip_cost_rate(self):
        m = TradingCostModel()
        # entry + exit = 0.20% + 0.30% = 0.50%
        assert m.round_trip_cost_rate() == pytest.approx(0.005)

    def test_break_even_move_pct(self):
        m = TradingCostModel()
        # 0.50% round-trip → break-even = 0.50%
        assert m.break_even_move_pct() == pytest.approx(0.5)

    def test_custom_slippage_override(self):
        m = TradingCostModel()
        # With higher slippage (0.1%), entry = 0.25%, exit = 0.35%, total = 0.60%
        assert m.entry_cost_rate(slippage_rate=0.001) == pytest.approx(0.0025)
        assert m.exit_cost_rate(slippage_rate=0.001) == pytest.approx(0.0035)
        assert m.round_trip_cost_rate(slippage_rate=0.001) == pytest.approx(0.006)


class TestTradingCostModelIDR:
    def test_entry_cost(self):
        m = TradingCostModel()
        cb = m.entry_cost(shares=1000, price=8500)
        # trade_value = 1000 * 8500 * (1 + 0.0005) = 8,504,250
        # commission = 8,504,250 * 0.0015 = 12,756.375
        # slippage = 1000 * 8500 * 0.0005 = 4,250
        # total = 12,756.375 + 4,250 = 17,006.375
        assert cb.commission > 0
        assert cb.sales_tax == 0.0
        assert cb.slippage > 0
        assert cb.total > 0
        assert cb.total == pytest.approx(cb.commission + cb.slippage)

    def test_exit_cost_has_sales_tax(self):
        m = TradingCostModel()
        cb = m.exit_cost(shares=1000, price=8700)
        assert cb.commission > 0
        assert cb.sales_tax > 0  # sell has sales tax
        assert cb.slippage > 0
        assert cb.total == pytest.approx(cb.commission + cb.sales_tax + cb.slippage)

    def test_round_trip_cost(self):
        m = TradingCostModel()
        rt = m.round_trip_cost(shares=1000, entry_price=8500, exit_price=8700)
        assert isinstance(rt, RoundTripCost)
        assert rt.entry.total > 0
        assert rt.exit.total > 0
        assert rt.total == pytest.approx(rt.entry.total + rt.exit.total)
        # Exit should be more expensive due to sales tax
        assert rt.exit.total > rt.entry.total

    def test_zero_shares_returns_zero(self):
        m = TradingCostModel()
        cb = m.entry_cost(shares=0, price=8500)
        assert cb.total == 0.0
        cb = m.exit_cost(shares=0, price=8500)
        assert cb.total == 0.0

    def test_zero_price_returns_zero(self):
        m = TradingCostModel()
        cb = m.entry_cost(shares=1000, price=0)
        assert cb.total == 0.0

    def test_volume_adjusted_slippage(self):
        m = TradingCostModel()
        # Small order vs large ADV → slippage ≈ base
        cb_small = m.entry_cost(shares=100, price=8500, avg_daily_volume=10_000_000)
        # Large order (10% of ADV) → slippage increases
        cb_large = m.entry_cost(shares=1_000_000, price=8500, avg_daily_volume=10_000_000)
        assert cb_large.slippage > cb_small.slippage


class TestNetProfitLoss:
    def test_net_profit_buy(self):
        m = TradingCostModel()
        # BUY 1000 @ 8500, exit @ 8700
        # gross profit = (8700 - 8500) * 1000 = 200,000
        # round-trip cost > 0
        net = m.net_profit(1000, 8500, 8700, direction=1)
        assert net > 0
        assert net < 200_000  # less than gross due to costs

    def test_net_loss_buy(self):
        m = TradingCostModel()
        # BUY 1000 @ 8500, stop @ 8300
        # gross loss = (8500 - 8300) * 1000 = 200,000
        # net loss = gross loss + round-trip cost
        net = m.net_loss(1000, 8500, 8300, direction=1)
        assert net > 200_000  # more than gross due to costs

    def test_net_profit_sell(self):
        m = TradingCostModel()
        # SELL 1000 @ 8500, exit @ 8300
        # gross profit = (8500 - 8300) * 1000 = 200,000
        net = m.net_profit(1000, 8500, 8300, direction=-1)
        assert net > 0
        assert net < 200_000

    def test_net_reward_risk_ratio(self):
        m = TradingCostModel()
        # BUY: target=2x vol, stop=1x vol → gross R/R = 2.0
        # net R/R should be < 2.0 due to costs
        rr = m.net_reward_risk_ratio(
            1000, entry_price=8500, target_price=8700,
            stop_price=8400, direction=1,
        )
        assert rr > 0
        assert rr < 2.0  # costs reduce R/R

    def test_net_rr_zero_loss(self):
        m = TradingCostModel()
        rr = m.net_reward_risk_ratio(
            1000, entry_price=8500, target_price=8500,
            stop_price=8500, direction=1,
        )
        # No price move → net_profit is negative (costs only), net_loss positive
        assert rr <= 0.0

    def test_is_cost_effective(self):
        m = TradingCostModel()
        # break-even = 0.5%
        assert m.is_cost_effective(1.0) is True
        assert m.is_cost_effective(0.3) is False
        assert m.is_cost_effective(0.5) is False  # equal, not exceeding


# ── CapitalAwarePositionSizer cost integration (DB needed) ──────────────────


@pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")
class TestSizerCostIntegration:
    def test_cost_fields_populated(self):
        from market.advisory.trading_style_advisor import (
            ExperienceLevel,
            RiskTolerance,
            TimeAvailability,
            TradingStyleAdvisor,
            UserProfile,
        )
        from market.analysis.instrument_profiler import (
            InstrumentBehaviorProfiler,
        )
        from market.risk.capital_aware_sizer import CapitalAwarePositionSizer

        profiler = InstrumentBehaviorProfiler()
        try:
            prof = profiler.profile_single("BBCA.JK", lookback_days=756)
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

        sizer = CapitalAwarePositionSizer()
        r = sizer.size_position(
            "BBCA.JK", direction=1, entry_price=8500,
            win_rate=0.55, win_loss_ratio=1.5,
            target_style="swing", user_id="default",
        )
        if r.shares > 0:
            assert r.estimated_entry_cost_idr > 0
            assert r.estimated_round_trip_cost_idr > 0
            assert r.round_trip_cost_rate > 0
            # Round-trip cost rate should be ~0.5%
            assert 0.003 < r.round_trip_cost_rate < 0.008
            # Cost should appear in reasoning
            assert "biaya" in r.reasoning.lower() or "cost" in r.reasoning.lower()


# ── EnhancedSignalGenerator cost filter (DB needed) ─────────────────────────


@pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")
class TestEnhancedSignalCostFilter:
    def test_cost_filter_fields_exist(self):
        from market.analysis.enhanced_signal_generator import EnhancedSignal

        sig = EnhancedSignal(ticker="TEST", direction=1, raw_position=0.05)
        assert hasattr(sig, "cost_filter_passed")
        assert hasattr(sig, "cost_filter_reason")
        assert sig.cost_filter_passed is True  # default

    def test_cost_filter_rejects_low_volatility(self):
        """A stock with very low volatility (< 0.17% daily for swing)
        should fail the cost filter since 3-day expected move < 0.5% break-even."""
        from market.analysis.enhanced_signal_generator import (
            EnhancedSignal,
            EnhancedSignalGenerator,
        )
        from market.analysis.instrument_profiler import InstrumentProfile
        from market.risk.cost_model import TradingCostModel

        gen = EnhancedSignalGenerator()
        # Create a signal with very low volatility profile
        sig = EnhancedSignal(
            ticker="LOWVOL.JK", direction=1, raw_position=0.05,
            entry_price=10000,
        )
        sig.profile = InstrumentProfile(
            ticker="LOWVOL.JK",
            avg_daily_volatility=0.10,  # 0.10% daily → swing 3x = 0.30% < 0.5%
        )
        sig.recommended_style = "swing"
        sig.passes_suitability_filter = True

        result = gen._apply_cost_filter(sig)
        assert result.cost_filter_passed is False
        assert "break-even" in result.cost_filter_reason

    def test_cost_filter_passes_high_volatility(self):
        """A stock with normal volatility (> 0.17% daily for swing)
        should pass the cost filter."""
        from market.analysis.enhanced_signal_generator import (
            EnhancedSignal,
            EnhancedSignalGenerator,
        )
        from market.analysis.instrument_profiler import InstrumentProfile

        gen = EnhancedSignalGenerator()
        sig = EnhancedSignal(
            ticker="BBCA.JK", direction=1, raw_position=0.05,
            entry_price=8500,
        )
        sig.profile = InstrumentProfile(
            ticker="BBCA.JK",
            avg_daily_volatility=1.73,  # 1.73% daily → swing 3x = 5.19% > 0.5%
        )
        sig.recommended_style = "swing"
        sig.passes_suitability_filter = True

        result = gen._apply_cost_filter(sig)
        assert result.cost_filter_passed is True

    def test_cost_filter_skipped_for_hold(self):
        from market.analysis.enhanced_signal_generator import (
            EnhancedSignal,
            EnhancedSignalGenerator,
        )
        from market.analysis.instrument_profiler import InstrumentProfile

        gen = EnhancedSignalGenerator()
        sig = EnhancedSignal(
            ticker="TEST.JK", direction=0, raw_position=0.0,
        )
        sig.profile = InstrumentProfile(
            ticker="TEST.JK",
            avg_daily_volatility=0.10,
        )
        sig.recommended_style = "swing"

        result = gen._apply_cost_filter(sig)
        assert result.cost_filter_passed is True
        assert "HOLD" in result.cost_filter_reason


# ── RecommendationEngine cost integration (DB needed) ───────────────────────


@pytest.mark.skipif(not _HAS_DB, reason="no DATABASE_URL — integration test")
class TestRecommendationCostIntegration:
    def test_net_fields_in_recommendation(self):
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
        )

        profiler = InstrumentBehaviorProfiler()
        for t in ["BBCA.JK", "BBRI.JK"]:
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

        engine = RecommendationEngine()
        report = engine.generate_report(
            raw_signals={
                "BBCA.JK": {"direction": 1, "raw_position": 0.05, "entry_price": 8500,
                            "win_rate": 0.55, "win_loss_ratio": 1.5},
            },
            user_id="default",
        )
        assert len(report.recommendations) > 0
        rec = report.recommendations[0]
        assert hasattr(rec, "estimated_cost_idr")
        assert hasattr(rec, "net_potential_profit_idr")
        assert hasattr(rec, "net_potential_loss_idr")
        assert hasattr(rec, "net_reward_risk_ratio")
        # Net R/R should be <= gross R/R due to costs
        if rec.reward_risk_ratio > 0 and rec.net_reward_risk_ratio > 0:
            assert rec.net_reward_risk_ratio <= rec.reward_risk_ratio
        # Portfolio summary should have cost aggregates
        assert "total_estimated_cost_idr" in report.portfolio_summary
        assert "total_net_profit_idr" in report.portfolio_summary
        assert "total_net_loss_idr" in report.portfolio_summary
