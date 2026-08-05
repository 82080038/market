"""Tests for Trading Automation Orchestrator (pustaka/32, 40, 67, 76, 83, 93)."""

from __future__ import annotations

from market.execution.automation import (
    AutoExecutor,
    AutomationConfig,
    AutomationGate,
    AutomationOrchestrator,
    ExecutionMode,
    ExecutionPlan,
    GateCheckStatus,
    MarketScope,
    PlanBuilder,
    PlanStatus,
    SignalSource,
)
from market.execution.brokers import MockBroker, PaperBroker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signals() -> list[dict]:
    return [
        {"ticker": "BBCA.JK", "side": "buy", "source": "screening_ai",
         "confidence": 78, "price": 8500, "recommendation": "strong_buy"},
        {"ticker": "ADRO.JK", "side": "buy", "source": "model_prediction",
         "confidence": 72, "price": 2750, "recommendation": "buy"},
        {"ticker": "TLKM.JK", "side": "buy", "source": "advisory_recommendation",
         "confidence": 68, "price": 3200, "recommendation": "buy"},
        {"ticker": "WEAK.JK", "side": "buy", "source": "screening_ai",
         "confidence": 40, "price": 1000, "recommendation": "hold"},
        {"ticker": "SELL.JK", "side": "sell", "source": "pattern_signal",
         "confidence": 75, "price": 5000, "recommendation": "sell"},
    ]


def _make_full_config(**overrides) -> AutomationConfig:
    defaults = {
        "enabled_sources": {
            SignalSource.SCREENING_AI,
            SignalSource.MODEL_PREDICTION,
            SignalSource.ADVISORY_RECOMMENDATION,
        },
        "market_scope": {MarketScope.IDX},
        "execution_mode": ExecutionMode.SEMI_AUTO,
        "min_confidence": 65.0,
        "max_orders_per_session": 5,
        "max_value_per_session": 50_000_000,
        "auto_sell": False,
        "auto_rebalance": False,
        "confirmed_paper_30d": True,
        "confirmed_risk_understood": True,
        "confirmed_risk_limits": True,
    }
    defaults.update(overrides)
    return AutomationConfig(**defaults)


# ---------------------------------------------------------------------------
# AutomationConfig tests
# ---------------------------------------------------------------------------


class TestAutomationConfig:
    def test_default_manual(self):
        config = AutomationConfig()
        assert config.execution_mode == ExecutionMode.MANUAL
        assert not config.is_any_enabled()

    def test_is_any_enabled(self):
        config = AutomationConfig(
            enabled_sources={SignalSource.SCREENING_AI},
            execution_mode=ExecutionMode.SEMI_AUTO,
        )
        assert config.is_any_enabled()

    def test_is_live_ready(self):
        config = AutomationConfig(
            confirmed_paper_30d=True,
            confirmed_risk_understood=True,
            confirmed_risk_limits=True,
        )
        assert config.is_live_ready()

    def test_not_live_ready(self):
        config = AutomationConfig(
            confirmed_paper_30d=True,
            confirmed_risk_understood=False,
            confirmed_risk_limits=True,
        )
        assert not config.is_live_ready()


# ---------------------------------------------------------------------------
# AutomationGate tests
# ---------------------------------------------------------------------------


class TestAutomationGate:
    def test_manual_mode_passes(self):
        gate = AutomationGate(env="research")
        config = AutomationConfig(execution_mode=ExecutionMode.MANUAL)
        result = gate.check_config(config)
        assert result.passed
        assert result.blocking_count == 0

    def test_full_auto_research_fails(self):
        gate = AutomationGate(env="research")
        config = AutomationConfig(
            execution_mode=ExecutionMode.FULL_AUTO,
            enabled_sources={SignalSource.SCREENING_AI},
            confirmed_paper_30d=True,
            confirmed_risk_understood=True,
            confirmed_risk_limits=True,
        )
        result = gate.check_config(config)
        assert not result.passed
        assert result.blocking_count > 0
        assert any(r.rule_id == "R1_ENV" for r in result.rules if r.status == GateCheckStatus.FAIL)

    def test_semi_auto_paper_passes(self):
        gate = AutomationGate(env="paper")
        config = _make_full_config()
        result = gate.check_config(config)
        assert result.passed
        assert result.blocking_count == 0

    def test_live_without_approval_fails(self):
        gate = AutomationGate(env="live", live_approved=False)
        config = _make_full_config(execution_mode=ExecutionMode.FULL_AUTO)
        result = gate.check_config(config)
        assert not result.passed
        assert any(
            r.rule_id == "R2_LIVE_APPROVAL"
            for r in result.rules if r.status == GateCheckStatus.FAIL
        )

    def test_live_with_approval_passes(self):
        gate = AutomationGate(env="live", live_approved=True, paper_trading_days=45)
        config = _make_full_config(execution_mode=ExecutionMode.FULL_AUTO)
        result = gate.check_config(config)
        assert result.passed

    def test_missing_confirmations_fails(self):
        gate = AutomationGate(env="paper")
        config = _make_full_config(confirmed_paper_30d=False)
        result = gate.check_config(config)
        assert not result.passed
        assert any(
            r.rule_id == "R3_CONFIRMATIONS"
            for r in result.rules if r.status == GateCheckStatus.FAIL
        )

    def test_circuit_breaker_blocks(self):
        gate = AutomationGate(env="paper", circuit_breaker_triggered=True)
        config = _make_full_config()
        result = gate.check_config(config)
        assert not result.passed
        assert any(
            r.rule_id == "R5_CIRCUIT_BREAKER"
            for r in result.rules if r.status == GateCheckStatus.FAIL
        )

    def test_market_closed_warning_for_full_auto(self):
        gate = AutomationGate(env="paper", market_open=False)
        config = _make_full_config(execution_mode=ExecutionMode.FULL_AUTO)
        result = gate.check_config(config)
        assert any(
            r.rule_id == "R6_MARKET_OPEN"
            for r in result.rules if r.status == GateCheckStatus.FAIL
        )

    def test_model_degraded_warning(self):
        gate = AutomationGate(env="paper", model_degraded=True)
        config = _make_full_config(enabled_sources={SignalSource.MODEL_PREDICTION})
        result = gate.check_config(config)
        assert result.warning_count > 0
        assert any(
            r.rule_id == "R7_MODEL_PERF"
            for r in result.rules if r.status == GateCheckStatus.WARNING
        )

    def test_global_scope_live_warning(self):
        gate = AutomationGate(env="live", live_approved=True, paper_trading_days=45)
        config = _make_full_config(
            market_scope={MarketScope.IDX, MarketScope.GLOBAL},
            execution_mode=ExecutionMode.FULL_AUTO,
        )
        result = gate.check_config(config)
        assert any(
            r.rule_id == "R8_GLOBAL_SCOPE"
            for r in result.rules if r.status == GateCheckStatus.WARNING
        )

    def test_low_confidence_warning(self):
        gate = AutomationGate(env="paper")
        config = _make_full_config(min_confidence=30)
        result = gate.check_config(config)
        assert any(
            r.rule_id == "R9_CONFIDENCE"
            for r in result.rules if r.status == GateCheckStatus.WARNING
        )

    def test_auto_sell_without_confirmation_fails(self):
        gate = AutomationGate(env="paper")
        config = _make_full_config(auto_sell=True, confirmed_risk_understood=False)
        result = gate.check_config(config)
        assert any(
            r.rule_id == "R10_AUTO_SELL"
            for r in result.rules if r.status == GateCheckStatus.FAIL
        )

    def test_check_can_enable_source(self):
        gate = AutomationGate(env="paper")
        config = _make_full_config()
        can, reason = gate.check_can_enable(config, SignalSource.SCREENING_AI)
        assert can
        assert reason == "OK"

    def test_check_can_enable_model_degraded(self):
        gate = AutomationGate(env="paper", model_degraded=True)
        config = _make_full_config()
        can, reason = gate.check_can_enable(config, SignalSource.MODEL_PREDICTION)
        assert not can
        assert "degraded" in reason.lower()

    def test_check_can_enable_circuit_breaker(self):
        gate = AutomationGate(env="paper", circuit_breaker_triggered=True)
        config = _make_full_config()
        can, reason = gate.check_can_enable(config, SignalSource.SCREENING_AI)
        assert not can
        assert "circuit breaker" in reason.lower()

    def test_check_can_enable_no_confirmation(self):
        gate = AutomationGate(env="paper")
        config = _make_full_config(confirmed_paper_30d=False)
        can, reason = gate.check_can_enable(config, SignalSource.SCREENING_AI)
        assert not can
        assert "paper trading" in reason.lower()

    def test_paper_trading_30d_requirement(self):
        gate = AutomationGate(env="live", live_approved=True, paper_trading_days=20)
        config = _make_full_config(execution_mode=ExecutionMode.FULL_AUTO)
        result = gate.check_config(config)
        assert not result.passed
        assert any(
            r.rule_id == "R4_PAPER_30D"
            for r in result.rules if r.status == GateCheckStatus.FAIL
        )


# ---------------------------------------------------------------------------
# PlanBuilder tests
# ---------------------------------------------------------------------------


class TestPlanBuilder:
    def test_build_plan(self):
        config = _make_full_config()
        builder = PlanBuilder(
            min_confidence=config.min_confidence,
            max_orders=config.max_orders_per_session,
            max_value=config.max_value_per_session,
        )
        plan = builder.build(_make_signals(), config)
        assert plan.status == PlanStatus.VALIDATED
        assert plan.passed_count > 0
        assert len(plan.orders) > 0

    def test_filter_low_confidence(self):
        config = _make_full_config(min_confidence=65.0)
        builder = PlanBuilder(min_confidence=65.0)
        plan = builder.build(_make_signals(), config)
        weak_orders = [o for o in plan.orders if o.ticker == "WEAK.JK"]
        assert len(weak_orders) == 0
        assert any("WEAK.JK" in r for r in plan.rejection_reasons)

    def test_filter_source_not_enabled(self):
        config = _make_full_config(
            enabled_sources={SignalSource.SCREENING_AI},
        )
        builder = PlanBuilder()
        plan = builder.build(_make_signals(), config)
        sources_in_plan = {o.source for o in plan.orders}
        assert SignalSource.SCREENING_AI in sources_in_plan
        assert SignalSource.MODEL_PREDICTION not in sources_in_plan

    def test_filter_sell_without_auto_sell(self):
        config = _make_full_config(auto_sell=False)
        builder = PlanBuilder()
        plan = builder.build(_make_signals(), config)
        sell_orders = [o for o in plan.orders if o.side == "sell"]
        assert len(sell_orders) == 0

    def test_max_orders_limit(self):
        config = _make_full_config(max_orders_per_session=1)
        builder = PlanBuilder(max_orders=1)
        plan = builder.build(_make_signals(), config)
        assert len(plan.orders) <= 1

    def test_max_value_limit(self):
        config = _make_full_config(max_value_per_session=5_000_000)
        builder = PlanBuilder(max_value=5_000_000)
        plan = builder.build(_make_signals(), config)
        assert plan.total_value <= 5_000_000

    def test_lot_size_rounding(self):
        config = _make_full_config()
        builder = PlanBuilder()
        plan = builder.build(_make_signals(), config)
        for order in plan.orders:
            assert order.shares % 100 == 0
            assert order.shares > 0

    def test_empty_signals(self):
        config = _make_full_config()
        builder = PlanBuilder()
        plan = builder.build([], config)
        assert plan.status == PlanStatus.REJECTED
        assert len(plan.orders) == 0

    def test_rejection_reasons_populated(self):
        config = _make_full_config(min_confidence=80)
        builder = PlanBuilder(min_confidence=80)
        plan = builder.build(_make_signals(), config)
        assert plan.rejected_count > 0
        assert len(plan.rejection_reasons) > 0

    def test_stop_loss_take_profit(self):
        config = _make_full_config()
        builder = PlanBuilder()
        plan = builder.build(_make_signals(), config)
        for order in plan.orders:
            assert order.stop_loss > 0
            assert order.take_profit > 0
            assert order.take_profit > order.price
            assert order.stop_loss < order.price


# ---------------------------------------------------------------------------
# AutoExecutor tests
# ---------------------------------------------------------------------------


class TestAutoExecutor:
    def test_execute_with_mock_broker(self):
        config = _make_full_config()
        builder = PlanBuilder()
        plan = builder.build(_make_signals(), config)
        assert plan.orders

        executor = AutoExecutor(MockBroker())
        result = executor.execute_plan(plan)
        assert result.filled_count > 0
        assert result.rejected_count == 0
        assert result.total_value > 0

    def test_execute_with_paper_broker(self):
        config = _make_full_config()
        builder = PlanBuilder()
        plan = builder.build(_make_signals(), config)

        executor = AutoExecutor(PaperBroker())
        result = executor.execute_plan(plan)
        assert result.filled_count > 0
        assert result.total_commission > 0

    def test_empty_plan(self):
        executor = AutoExecutor(MockBroker())
        plan = ExecutionPlan(
            plan_id="EMPTY",
            created_at="2024-01-01T00:00:00Z",
            status=PlanStatus.REJECTED,
        )
        result = executor.execute_plan(plan)
        assert result.filled_count == 0
        assert result.rejected_count == 0

    def test_plan_status_updated(self):
        config = _make_full_config()
        builder = PlanBuilder()
        plan = builder.build(_make_signals(), config)

        executor = AutoExecutor(MockBroker())
        executor.execute_plan(plan)
        assert plan.status in (PlanStatus.COMPLETED, PlanStatus.PARTIAL)


# ---------------------------------------------------------------------------
# AutomationOrchestrator tests
# ---------------------------------------------------------------------------


class TestAutomationOrchestrator:
    def test_configure_manual(self):
        orch = AutomationOrchestrator(gate=AutomationGate(env="research"))
        config = AutomationConfig(execution_mode=ExecutionMode.MANUAL)
        result = orch.configure(config)
        assert result.passed
        assert orch.config is not None

    def test_configure_full_auto_research(self):
        orch = AutomationOrchestrator(gate=AutomationGate(env="research"))
        config = _make_full_config(execution_mode=ExecutionMode.FULL_AUTO)
        result = orch.configure(config)
        assert not result.passed
        assert orch.config is None

    def test_prepare_plan_no_config(self):
        orch = AutomationOrchestrator(gate=AutomationGate(env="research"))
        plan = orch.prepare_plan(_make_signals())
        assert plan.status == PlanStatus.REJECTED

    def test_prepare_plan_with_config(self):
        gate = AutomationGate(env="paper")
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config()
        orch.configure(config)
        plan = orch.prepare_plan(_make_signals())
        assert plan.status == PlanStatus.VALIDATED
        assert len(plan.orders) > 0

    def test_execute_manual_mode(self):
        gate = AutomationGate(env="paper")
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config(execution_mode=ExecutionMode.MANUAL)
        orch.configure(config)
        result = orch.execute(_make_signals())
        assert "manual" in result.summary.lower()

    def test_execute_semi_auto(self):
        gate = AutomationGate(env="paper")
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config(execution_mode=ExecutionMode.SEMI_AUTO)
        orch.configure(config)
        result = orch.execute(_make_signals())
        assert result.filled_count > 0

    def test_execute_gate_fail(self):
        gate = AutomationGate(env="paper", circuit_breaker_triggered=True)
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config()
        orch.configure(config)
        result = orch.execute(_make_signals())
        assert "gate" in result.summary.lower()

    def test_execute_no_signals(self):
        gate = AutomationGate(env="paper")
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config()
        orch.configure(config)
        result = orch.execute([])
        assert "tidak ada order" in result.summary.lower() or "empty" in result.summary.lower()

    def test_last_plan_tracked(self):
        gate = AutomationGate(env="paper")
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config()
        orch.configure(config)
        orch.prepare_plan(_make_signals())
        assert orch.last_plan is not None
        assert orch.last_plan.passed_count > 0

    def test_last_execution_tracked(self):
        gate = AutomationGate(env="paper")
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config(execution_mode=ExecutionMode.SEMI_AUTO)
        orch.configure(config)
        orch.execute(_make_signals())
        assert orch.last_execution is not None
        assert orch.last_execution.filled_count > 0

    def test_full_auto_paper_env(self):
        gate = AutomationGate(env="paper")
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config(execution_mode=ExecutionMode.FULL_AUTO)
        result = orch.configure(config)
        assert result.passed
        exec_result = orch.execute(_make_signals())
        assert exec_result.filled_count > 0

    def test_full_auto_market_closed(self):
        gate = AutomationGate(env="paper", market_open=False)
        orch = AutomationOrchestrator(gate=gate)
        config = _make_full_config(execution_mode=ExecutionMode.FULL_AUTO)
        result = orch.configure(config)
        assert result.passed
        exec_result = orch.execute(_make_signals())
        assert exec_result.filled_count > 0
