"""Tests for Portfolio Engine."""

from __future__ import annotations

from market.execution.portfolio import PortfolioEngine


def test_portfolio_nav_empty():
    engine = PortfolioEngine(initial_capital=100_000_000)
    nav = engine.get_nav({})
    assert nav == 100_000_000


def test_portfolio_nav_with_positions():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.add_position("BBCA.JK", 1000, 8000, sector="finance")
    engine.add_position("TLKM.JK", 500, 3000, sector="telecom")
    nav = engine.get_nav({"BBCA.JK": 8500, "TLKM.JK": 3200})
    # 100M - (1000*8000 + 500*3000) + cash... wait, add_position doesn't deduct cash
    # NAV = cash + positions = 100M + 1000*8500 + 500*3200 = 100M + 8.5M + 1.6M = 110.1M
    assert nav == 110_100_000


def test_portfolio_summary():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.add_position("BBCA.JK", 1000, 8000, sector="finance")
    engine.add_position("TLKM.JK", 500, 3000, sector="telecom")
    summary = engine.get_summary({"BBCA.JK": 8500, "TLKM.JK": 3200})
    assert summary.total_nav == 110_100_000
    assert summary.n_positions == 2
    assert "BBCA.JK" in summary.positions
    assert "finance" in summary.sector_exposure
    assert "telecom" in summary.sector_exposure
    assert summary.largest_position_pct > 0


def test_portfolio_drift():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.set_target_weights({"BBCA.JK": 0.05, "TLKM.JK": 0.03})
    engine.add_position("BBCA.JK", 1000, 8000, sector="finance")
    summary = engine.get_summary({"BBCA.JK": 8500})
    # BBCA weight = 8500*1000 / (100M + 8500*1000) = 8.5M / 108.5M ≈ 7.83%
    # Target = 5%, drift ≈ +2.83%
    assert "BBCA.JK" in summary.drift_from_target
    assert summary.drift_from_target["BBCA.JK"] > 2.0


def test_portfolio_needs_rebalance():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.set_target_weights({"BBCA.JK": 0.05})
    engine.add_position("BBCA.JK", 1000, 8000, sector="finance")
    # Weight is ~7.8%, target 5%, drift > 2% but threshold is 5%
    assert not engine.needs_rebalance({"BBCA.JK": 8500}, threshold_pct=5.0)
    # With lower threshold
    assert engine.needs_rebalance({"BBCA.JK": 8500}, threshold_pct=1.0)


def test_portfolio_rebalance_orders():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.set_target_weights({"BBCA.JK": 0.10})
    # No position yet, need to buy 10% of NAV
    orders = engine.compute_rebalance_orders({"BBCA.JK": 8500})
    # Target value = 10M, shares = 10M / 8500 ≈ 1176, rounded to 1100
    assert len(orders) == 1
    assert orders[0]["side"] == "buy"
    assert orders[0]["shares"] > 0


def test_portfolio_rebalance_sell():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.set_target_weights({"BBCA.JK": 0.01})  # Very small target
    engine.add_position("BBCA.JK", 1000, 8000, sector="finance")
    orders = engine.compute_rebalance_orders({"BBCA.JK": 8500})
    # Current weight >> target, should sell
    sell_orders = [o for o in orders if o["side"] == "sell"]
    assert len(sell_orders) > 0


def test_portfolio_no_rebalance_needed():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.set_target_weights({"BBCA.JK": 0.0})
    # No position, target 0%, no orders
    orders = engine.compute_rebalance_orders({"BBCA.JK": 8500})
    assert len(orders) == 0


def test_portfolio_market_exposure():
    engine = PortfolioEngine(initial_capital=100_000_000)
    engine.add_position("BBCA.JK", 1000, 8000, sector="finance", market_mic="XIDX")
    engine.add_position("AAPL", 100, 150, sector="tech", market_mic="XNAS")
    summary = engine.get_summary({"BBCA.JK": 8500, "AAPL": 160})
    assert "XIDX" in summary.market_exposure
    assert "XNAS" in summary.market_exposure
