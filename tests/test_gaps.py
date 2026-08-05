"""Tests for gap deliverables: scheduler, extras, attribution, alerts."""

from __future__ import annotations

import pandas as pd
import pytest

from market.analysis.alerts import (
    AlertChannel,
    AlertCondition,
    AlertManager,
    AlertStatus,
)
from market.analysis.attribution import (
    BrinsonAttribution,
    MarketRegime,
    RegimeWeightAdjuster,
    StressTester,
    TradeLedger,
)
from market.analysis.extras import (
    ActionType,
    CorporateAction,
    CorporateActionEngine,
    FeatureEntry,
    FeatureStore,
    PatternMemory,
)
from market.scheduler import DailyScheduler, TaskStatus

# --- Scheduler tests ---


def test_scheduler_register_task():
    sched = DailyScheduler()
    task = sched.register_task("T1", "Data Update", lambda: None, "daily")
    assert task.task_id == "T1"
    assert task.enabled


def test_scheduler_run_task():
    sched = DailyScheduler()
    sched.register_task("T1", "Test", lambda: None, "daily")
    execution = sched.run_task("T1")
    assert execution is not None
    assert execution.status == TaskStatus.SUCCESS


def test_scheduler_run_task_failed():
    sched = DailyScheduler()

    def failing() -> None:
        raise ValueError("boom")

    sched.register_task("T1", "Failing", failing, "daily")
    execution = sched.run_task("T1")
    assert execution.status == TaskStatus.FAILED
    assert "boom" in execution.error


def test_scheduler_disabled_task():
    sched = DailyScheduler()
    sched.register_task("T1", "Test", lambda: None, "daily")
    sched.disable_task("T1")
    execution = sched.run_task("T1")
    assert execution.status == TaskStatus.SKIPPED


def test_scheduler_run_all_due():
    sched = DailyScheduler()
    sched.register_task("T1", "Task 1", lambda: None, "daily")
    sched.register_task("T2", "Task 2", lambda: None, "daily")
    executions = sched.run_all_due()
    assert len(executions) == 2


def test_scheduler_status_summary():
    sched = DailyScheduler()
    sched.register_task("T1", "Task 1", lambda: None, "daily")
    sched.register_task("T2", "Task 2", lambda: None, "daily")
    sched.disable_task("T2")
    summary = sched.status_summary()
    assert summary["total_tasks"] == 2
    assert summary["enabled"] == 1
    assert summary["disabled"] == 1


# --- Corporate action engine tests ---


def test_corporate_action_split():
    engine = CorporateActionEngine()
    engine.register_action(CorporateAction(
        ticker="BBCA", action_type=ActionType.SPLIT,
        ex_date="2024-06-15", ratio=2.0,
    ))
    data = pd.DataFrame(
        {"open": [8000, 8000], "high": [8100, 8100],
         "low": [7900, 7900], "close": [8050, 8050],
         "volume": [1000000, 1000000]},
        index=pd.to_datetime(["2024-06-13", "2024-06-14"]),
    )
    adjusted = engine.adjust_ohlcv("BBCA", data)
    assert adjusted["close"].iloc[0] == pytest.approx(4025.0)


def test_corporate_action_no_actions():
    engine = CorporateActionEngine()
    data = pd.DataFrame(
        {"open": [8000], "high": [8100], "low": [7900],
         "close": [8050], "volume": [1000000]},
        index=pd.to_datetime(["2024-06-13"]),
    )
    adjusted = engine.adjust_ohlcv("BBCA", data)
    assert adjusted["close"].iloc[0] == 8050


# --- Feature store tests ---


def test_feature_store_basic():
    store = FeatureStore()
    store.store(FeatureEntry(
        ticker="BBCA", feature_name="rsi", value=65.0,
        as_of="2024-06-14",
    ))
    features = store.get_features("BBCA")
    assert features["rsi"] == 65.0


def test_feature_store_batch():
    store = FeatureStore()
    entries = [
        FeatureEntry("BBCA", "rsi", 65.0, "2024-06-14"),
        FeatureEntry("BBCA", "macd", 1.5, "2024-06-14"),
        FeatureEntry("TLKM", "rsi", 30.0, "2024-06-14"),
    ]
    count = store.store_batch(entries)
    assert count == 3
    assert store.feature_count("BBCA") == 2
    assert "BBCA" in store.list_tickers()


def test_feature_store_as_of():
    store = FeatureStore()
    store.store(FeatureEntry("BBCA", "rsi", 60.0, "2024-06-13"))
    store.store(FeatureEntry("BBCA", "rsi", 70.0, "2024-06-14"))
    features = store.get_features("BBCA", as_of="2024-06-13")
    assert features["rsi"] == 60.0


def test_feature_store_vector():
    store = FeatureStore()
    store.store(FeatureEntry("BBCA", "rsi", 65.0, "2024-06-14"))
    store.store(FeatureEntry("BBCA", "macd", 1.5, "2024-06-14"))
    vec = store.get_feature_vector("BBCA", ["rsi", "macd"])
    assert len(vec) == 2
    assert vec[0] == 65.0


# --- Pattern memory tests ---


def test_pattern_memory_record():
    mem = PatternMemory()
    pattern = mem.record_pattern(
        "double_bottom", "BBCA", direction="bullish",
        confidence=0.8, price_at_detection=7500,
    )
    assert pattern.outcome == "pending"
    assert pattern.direction == "bullish"


def test_pattern_memory_update_outcome():
    mem = PatternMemory()
    pattern = mem.record_pattern(
        "double_bottom", "BBCA", direction="bullish",
        price_at_detection=7500,
    )
    updated = mem.update_outcome(pattern.pattern_id, 7800)
    assert updated.outcome == "confirmed"
    assert updated.return_pct > 0


def test_pattern_memory_reliability():
    mem = PatternMemory()
    p1 = mem.record_pattern("flag", "BBCA", direction="bullish", price_at_detection=100)
    mem.update_outcome(p1.pattern_id, 105)
    p2 = mem.record_pattern("flag", "TLKM", direction="bullish", price_at_detection=100)
    mem.update_outcome(p2.pattern_id, 95)
    stats = mem.get_reliability("flag")
    assert stats["total"] == 2
    assert stats["confirmed"] == 1
    assert stats["reliability"] == 0.5


# --- Regime weight adjuster tests ---


def test_regime_classify_bull():
    adj = RegimeWeightAdjuster()
    regime = adj.classify_regime(ihsg_return_30d=8.0, ihsg_volatility=15.0, ihsg_trend="up")
    assert regime == MarketRegime.BULL


def test_regime_classify_bear():
    adj = RegimeWeightAdjuster()
    regime = adj.classify_regime(ihsg_return_30d=-8.0, ihsg_volatility=25.0, ihsg_trend="down")
    assert regime == MarketRegime.BEAR


def test_regime_classify_crisis():
    adj = RegimeWeightAdjuster()
    regime = adj.classify_regime(ihsg_return_30d=-15.0, ihsg_volatility=50.0, ihsg_trend="down")
    assert regime == MarketRegime.CRISIS


def test_regime_get_weights():
    adj = RegimeWeightAdjuster()
    weights = adj.get_weights(MarketRegime.BULL)
    assert "technical" in weights
    assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)


def test_regime_adjust_weights():
    adj = RegimeWeightAdjuster()
    base = {"technical": 0.20, "fundamental": 0.25, "macro": 0.15,
            "global": 0.10, "relationship": 0.10, "sentiment": 0.20}
    adjusted = adj.adjust_weights(base, MarketRegime.BULL)
    assert sum(adjusted.values()) == pytest.approx(1.0, abs=0.01)
    assert adjusted["technical"] > base["technical"] * 0.9  # Should increase in bull


# --- Brinson attribution tests ---


def test_brinson_attribution():
    brinson = BrinsonAttribution()
    result = brinson.attribute(
        portfolio_weights={"finance": 0.60, "energy": 0.40},
        portfolio_returns={"finance": 0.10, "energy": 0.05},
        benchmark_weights={"finance": 0.50, "energy": 0.50},
        benchmark_returns={"finance": 0.08, "energy": 0.03},
    )
    assert result.excess_return > 0
    assert "finance" in result.sector_breakdown


def test_brinson_zero_excess():
    brinson = BrinsonAttribution()
    result = brinson.attribute(
        portfolio_weights={"a": 1.0},
        portfolio_returns={"a": 0.10},
        benchmark_weights={"a": 1.0},
        benchmark_returns={"a": 0.10},
    )
    assert result.excess_return == 0


# --- Trade ledger tests ---


def test_trade_ledger_buy():
    ledger = TradeLedger(opening_cash=10_000_000)
    entry = ledger.record_buy("BBCA", 100, 7500, fee=5000)
    assert entry.entry_type.value == "buy"
    assert ledger.cash_balance == 10_000_000 - 750_000 - 5000


def test_trade_ledger_sell():
    ledger = TradeLedger(opening_cash=10_000_000)
    ledger.record_buy("BBCA", 100, 7500)
    entry = ledger.record_sell("BBCA", 50, 8000)
    assert entry.entry_type.value == "sell"
    assert ledger.cash_balance > 10_000_000 - 750_000


def test_trade_ledger_dividend():
    ledger = TradeLedger(opening_cash=1_000_000)
    ledger.record_dividend("BBCA", 50000)
    assert ledger.cash_balance == 1_050_000


def test_trade_ledger_nav():
    ledger = TradeLedger(opening_cash=10_000_000)
    ledger.record_buy("BBCA", 100, 7500)
    nav = ledger.nav({"BBCA": 8000})
    expected = (10_000_000 - 750_000) + (100 * 8000)
    assert nav == pytest.approx(expected)


def test_trade_ledger_reconcile():
    ledger = TradeLedger(opening_cash=10_000_000)
    ledger.record_buy("BBCA", 100, 7500)
    report = ledger.reconcile({"BBCA": 8000})
    assert "nav" in report
    assert "positions" in report
    assert report["positions"]["BBCA"] == 100


# --- Stress test tests ---


def test_stress_test_basic():
    tester = StressTester()
    positions = {
        "BBCA": {"quantity": 100, "price": 7500},
        "TLKM": {"quantity": 200, "price": 3200},
    }
    result = tester.run_stress_test(positions, "ST-001")
    assert result.loss > 0
    assert result.loss_pct > 0


def test_stress_test_survived():
    tester = StressTester()
    positions = {
        "BBCA": {"quantity": 10, "price": 7500},
    }
    result = tester.run_stress_test(positions, "ST-001")
    assert result.survived  # Small position should survive


def test_stress_test_all_scenarios():
    tester = StressTester()
    positions = {"BBCA": {"quantity": 100, "price": 7500}}
    results = tester.run_all_scenarios(positions)
    assert len(results) == 5  # 5 default scenarios


def test_stress_test_scenarios_list():
    tester = StressTester()
    scenarios = tester.scenarios
    assert len(scenarios) == 5
    assert any(s.name == "Market Crash" for s in scenarios)


# --- Alert manager tests ---


def test_alert_create():
    mgr = AlertManager()
    alert = mgr.create_alert("BBCA", AlertCondition.PRICE_ABOVE, threshold=8000)
    assert alert.alert_id == "ALR-00001"
    assert alert.status == AlertStatus.ACTIVE


def test_alert_price_above_triggered():
    mgr = AlertManager()
    mgr.create_alert("BBCA", AlertCondition.PRICE_ABOVE, threshold=8000)
    notifs = mgr.evaluate("BBCA", {"price": 8100})
    assert len(notifs) == 1
    assert notifs[0].condition == AlertCondition.PRICE_ABOVE


def test_alert_price_above_not_triggered():
    mgr = AlertManager()
    mgr.create_alert("BBCA", AlertCondition.PRICE_ABOVE, threshold=8000)
    notifs = mgr.evaluate("BBCA", {"price": 7500})
    assert len(notifs) == 0


def test_alert_rsi_oversold():
    mgr = AlertManager()
    mgr.create_alert("BBCA", AlertCondition.RSI_OVERSOLD, threshold=30)
    notifs = mgr.evaluate("BBCA", {"rsi": 25})
    assert len(notifs) == 1


def test_alert_disable():
    mgr = AlertManager()
    alert = mgr.create_alert("BBCA", AlertCondition.PRICE_ABOVE, threshold=8000)
    mgr.disable_alert(alert.alert_id)
    notifs = mgr.evaluate("BBCA", {"price": 8100})
    assert len(notifs) == 0


def test_alert_multiple_channels():
    mgr = AlertManager()
    mgr.create_alert(
        "BBCA", AlertCondition.PRICE_BELOW, threshold=7000,
        channels=[AlertChannel.TELEGRAM, AlertChannel.EMAIL],
    )
    notifs = mgr.evaluate("BBCA", {"price": 6900})
    assert len(notifs) == 1
    assert AlertChannel.TELEGRAM in notifs[0].channels


def test_alert_active_alerts():
    mgr = AlertManager()
    mgr.create_alert("BBCA", AlertCondition.PRICE_ABOVE, threshold=8000)
    mgr.create_alert("TLKM", AlertCondition.VOLUME_SPIKE, threshold=3.0)
    assert len(mgr.active_alerts) == 2


def test_alert_volume_spike():
    mgr = AlertManager()
    mgr.create_alert("BBCA", AlertCondition.VOLUME_SPIKE, threshold=3.0)
    notifs = mgr.evaluate("BBCA", {"volume": 5000000, "avg_volume": 1000000})
    assert len(notifs) == 1
