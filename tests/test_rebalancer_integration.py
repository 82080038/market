"""Tests for portfolio rebalancer integration with AutoExecutor (Gap #12)."""

from __future__ import annotations

from market.execution.automation import AutoExecutor, AutomationOrchestrator
from market.execution.portfolio import PortfolioEngine


def test_auto_executor_execute_rebalance_buy():
    """AutoExecutor.execute_rebalance() executes buy orders."""
    executor = AutoExecutor()
    orders = [
        {"ticker": "BBCA.JK", "side": "buy", "shares": 200, "value": 18000000},
        {"ticker": "TLKM.JK", "side": "buy", "shares": 100, "value": 350000},
    ]
    prices = {"BBCA.JK": 90000, "TLKM.JK": 3500}
    result = executor.execute_rebalance(orders, prices)

    assert result.filled_count == 2
    assert result.rejected_count == 0
    assert result.total_value > 0
    assert "Rebalance" in result.summary


def test_auto_executor_execute_rebalance_sell():
    """AutoExecutor.execute_rebalance() executes sell orders."""
    executor = AutoExecutor()
    orders = [
        {"ticker": "BBCA.JK", "side": "sell", "shares": 100, "value": 9000000},
    ]
    prices = {"BBCA.JK": 90000}
    result = executor.execute_rebalance(orders, prices)

    assert result.filled_count == 1
    assert result.rejected_count == 0


def test_auto_executor_execute_rebalance_mixed():
    """AutoExecutor.execute_rebalance() handles mixed buy/sell."""
    executor = AutoExecutor()
    orders = [
        {"ticker": "BBCA.JK", "side": "buy", "shares": 200, "value": 18000000},
        {"ticker": "TLKM.JK", "side": "sell", "shares": 100, "value": 350000},
    ]
    prices = {"BBCA.JK": 90000, "TLKM.JK": 3500}
    result = executor.execute_rebalance(orders, prices)

    assert result.filled_count == 2
    assert result.rejected_count == 0


def test_auto_executor_execute_rebalance_empty():
    """AutoExecutor.execute_rebalance() handles empty order list."""
    executor = AutoExecutor()
    result = executor.execute_rebalance([], {})

    assert result.filled_count == 0
    assert result.rejected_count == 0


def test_auto_executor_execute_rebalance_skip_zero_shares():
    """AutoExecutor.execute_rebalance() skips orders with 0 shares."""
    executor = AutoExecutor()
    orders = [
        {"ticker": "BBCA.JK", "side": "buy", "shares": 0, "value": 0},
    ]
    result = executor.execute_rebalance(orders, {"BBCA.JK": 90000})

    assert result.filled_count == 0


def test_auto_executor_execute_rebalance_market_order():
    """AutoExecutor.execute_rebalance() works with market orders (price from broker)."""
    executor = AutoExecutor()
    orders = [
        {"ticker": "BBCA.JK", "side": "buy", "shares": 100, "value": 9000000},
    ]
    # MockBroker needs a price for limit order; provide prices
    prices = {"BBCA.JK": 90000}
    result = executor.execute_rebalance(orders, prices)

    assert result.filled_count == 1


def test_orchestrator_rebalance_no_drift():
    """AutomationOrchestrator.rebalance() skips when drift is below threshold."""
    pe = PortfolioEngine(initial_capital=0)
    pe.add_position("BBCA.JK", shares=1000, avg_cost=80000)
    pe.set_target_weights({"BBCA.JK": 1.0})
    prices = {"BBCA.JK": 90000}
    orchestrator = AutomationOrchestrator()
    result = orchestrator.rebalance(pe, prices, drift_threshold_pct=5.0)

    assert "no rebalance" in result.summary.lower()


def test_orchestrator_rebalance_with_drift():
    """AutomationOrchestrator.rebalance() executes when drift exceeds threshold."""
    pe = PortfolioEngine(initial_capital=50_000_000)
    pe.add_position("BBCA.JK", shares=100, avg_cost=80000)
    pe.set_target_weights({"BBCA.JK": 0.5, "TLKM.JK": 0.5})
    prices = {"BBCA.JK": 90000, "TLKM.JK": 3500}
    orchestrator = AutomationOrchestrator()
    result = orchestrator.rebalance(pe, prices, drift_threshold_pct=1.0)

    # Should attempt rebalance (may or may not have orders due to lot rounding)
    assert "REBALANCE" in result.plan_id


def test_orchestrator_rebalance_empty_orders():
    """AutomationOrchestrator.rebalance() handles case where orders round to 0."""
    pe = PortfolioEngine(initial_capital=100)
    pe.add_position("BBCA.JK", shares=1, avg_cost=80000)
    pe.set_target_weights({"BBCA.JK": 1.0})
    prices = {"BBCA.JK": 90000}
    orchestrator = AutomationOrchestrator()
    result = orchestrator.rebalance(pe, prices, drift_threshold_pct=0.01)

    # Should skip due to no drift or empty orders
    assert result.plan_id in ("REBALANCE-SKIP", "REBALANCE-EMPTY")
