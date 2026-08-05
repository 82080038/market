"""Tests for paper trading engine."""

from __future__ import annotations

from market.backtest.paper_trading import PaperTradingEngine


def test_paper_buy_basic():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    order = engine.buy("BBCA.JK", 1000, 8500)
    assert order.status == "filled"
    assert order.commission > 0
    assert "BBCA.JK" in engine.positions
    assert engine.positions["BBCA.JK"].shares == 1000


def test_paper_buy_insufficient_funds():
    engine = PaperTradingEngine(initial_capital=1_000_000)
    order = engine.buy("BBCA.JK", 1000, 8500)
    assert order.status == "rejected"
    assert order.rejection_reason == "INSUFFICIENT_FUNDS"


def test_paper_buy_invalid_lot():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    order = engine.buy("BBCA.JK", 150, 8500)  # Not multiple of 100
    assert order.status == "rejected"
    assert order.rejection_reason == "INVALID_LOT_SIZE"


def test_paper_sell_basic():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    engine.buy("BBCA.JK", 1000, 8500)
    order = engine.sell("BBCA.JK", 500, 9000)
    assert order.status == "filled"
    assert order.sales_tax > 0
    assert engine.positions["BBCA.JK"].shares == 500


def test_paper_sell_insufficient_shares():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    order = engine.sell("BBCA.JK", 100, 8500)
    assert order.status == "rejected"
    assert order.rejection_reason == "INSUFFICIENT_SHARES"


def test_paper_sell_all():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    engine.buy("BBCA.JK", 1000, 8500)
    order = engine.sell("BBCA.JK", 1000, 9000)
    assert order.status == "filled"
    assert engine.positions["BBCA.JK"].shares == 0
    assert engine.positions["BBCA.JK"].realized_pnl > 0


def test_paper_portfolio_value():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    engine.buy("BBCA.JK", 1000, 8500)
    value = engine.get_portfolio_value({"BBCA.JK": 9000})
    # cash = 100M - 1000*8500 - commission = ~91,472,500
    # position = 1000 * 9000 = 9,000,000
    assert value > 99_000_000  # Should be close to initial


def test_paper_unrealized_pnl():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    engine.buy("BBCA.JK", 1000, 8500)
    pnl = engine.get_unrealized_pnl({"BBCA.JK": 9000})
    # 1000 * (9000 - 8500) = 500,000
    assert pnl == 500_000.0


def test_paper_avg_cost_multiple_buys():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    engine.buy("BBCA.JK", 1000, 8000)
    engine.buy("BBCA.JK", 1000, 9000)
    pos = engine.positions["BBCA.JK"]
    assert pos.shares == 2000
    # avg_cost ≈ (8000 + 9000) / 2 = 8500 (ignoring commission)
    assert 8400 < pos.avg_cost < 8600


def test_paper_realized_pnl_on_sell():
    engine = PaperTradingEngine(initial_capital=100_000_000)
    engine.buy("BBCA.JK", 1000, 8500)
    engine.sell("BBCA.JK", 1000, 9000)
    pos = engine.positions["BBCA.JK"]
    # Realized PnL should be positive (sold above cost)
    assert pos.realized_pnl > 0
