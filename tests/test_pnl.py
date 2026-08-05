"""Tests for PnL Engine (FIFO)."""

from __future__ import annotations

from market.backtest.pnl import PnLEngine


def test_pnl_buy_creates_lot():
    engine = PnLEngine()
    engine.buy("BBCA.JK", 1000, 8000)
    pos = engine.get_position_pnl("BBCA.JK", 8500)
    assert pos.total_shares == 1000
    assert pos.avg_cost == 8000.0
    assert pos.unrealized_pnl == 500_000.0
    assert pos.realized_pnl == 0.0


def test_pnl_sell_fifo():
    engine = PnLEngine()
    engine.buy("BBCA.JK", 1000, 8000)
    engine.buy("BBCA.JK", 1000, 9000)
    trades = engine.sell("BBCA.JK", 1500, 9500)

    # FIFO: first 1000 from lot 1 (8000), then 500 from lot 2 (9000)
    assert len(trades) == 2
    assert trades[0].buy_price == 8000.0
    assert trades[0].shares == 1000
    assert trades[1].buy_price == 9000.0
    assert trades[1].shares == 500

    # Realized: 1000*(9500-8000) + 500*(9500-9000) = 1,500,000 + 250,000
    pos = engine.get_position_pnl("BBCA.JK", 9500)
    assert pos.realized_pnl == 1_750_000.0
    assert pos.total_shares == 500  # 2000 - 1500


def test_pnl_unrealized_after_partial_sell():
    engine = PnLEngine()
    engine.buy("TEST.JK", 1000, 100)
    engine.sell("TEST.JK", 500, 110)
    pos = engine.get_position_pnl("TEST.JK", 120)
    # Remaining 500 shares, cost 100, current 120
    assert pos.total_shares == 500
    assert pos.unrealized_pnl == 10_000.0  # 500 * (120-100)
    assert pos.realized_pnl == 5_000.0  # 500 * (110-100)


def test_pnl_portfolio_level():
    engine = PnLEngine()
    engine.buy("BBCA.JK", 1000, 8000)
    engine.buy("TLKM.JK", 500, 3000)
    engine.sell("BBCA.JK", 500, 8500)

    portfolio = engine.get_portfolio_pnl({
        "BBCA.JK": 8500,
        "TLKM.JK": 3200,
    })
    assert "BBCA.JK" in portfolio.positions
    assert "TLKM.JK" in portfolio.positions
    # BBCA realized: 500*(8500-8000) = 250,000
    # BBCA unrealized: 500*(8500-8000) = 250,000
    # TLKM unrealized: 500*(3200-3000) = 100,000
    assert portfolio.total_realized == 250_000.0
    assert portfolio.total_unrealized == 350_000.0
    assert portfolio.total_pnl == 600_000.0


def test_pnl_empty_position():
    engine = PnLEngine()
    pos = engine.get_position_pnl("EMPTY.JK", 100)
    assert pos.total_shares == 0
    assert pos.unrealized_pnl == 0.0
    assert pos.realized_pnl == 0.0


def test_pnl_multiple_sells_same_lot():
    engine = PnLEngine()
    engine.buy("TEST.JK", 1000, 100)
    engine.sell("TEST.JK", 300, 110)
    engine.sell("TEST.JK", 300, 115)
    pos = engine.get_position_pnl("TEST.JK", 120)
    assert pos.total_shares == 400
    # Realized: 300*(110-100) + 300*(115-100) = 3000 + 4500 = 7500
    assert pos.realized_pnl == 7500.0


def test_pnl_get_realized_trades():
    engine = PnLEngine()
    engine.buy("A.JK", 1000, 100)
    engine.buy("B.JK", 1000, 200)
    engine.sell("A.JK", 500, 110)
    engine.sell("B.JK", 500, 210)

    all_trades = engine.get_realized_trades()
    assert len(all_trades) == 2

    a_trades = engine.get_realized_trades("A.JK")
    assert len(a_trades) == 1
    assert a_trades[0].ticker == "A.JK"


def test_pnl_sell_more_than_held():
    engine = PnLEngine()
    engine.buy("TEST.JK", 1000, 100)
    trades = engine.sell("TEST.JK", 1500, 110)
    # Only 1000 available, so only 1000 matched
    total_matched = sum(t.shares for t in trades)
    assert total_matched == 1000
