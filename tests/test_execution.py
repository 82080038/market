"""Tests for order validation and broker adapters."""

from __future__ import annotations

from market.execution.brokers import MockBroker, PaperBroker, RealBroker
from market.execution.oms import Order, OrderSide, OrderType
from market.execution.validation import (
    OrderValidator,
    get_tick_size,
    validate_price_tick,
)

# --- Validation tests ---


def test_tick_size_low_price():
    assert get_tick_size(150) == 1.0


def test_tick_size_mid_price():
    assert get_tick_size(300) == 2.5


def test_tick_size_high_price():
    assert get_tick_size(6000) == 25.0


def test_validate_price_tick_valid():
    assert validate_price_tick(8500, 25.0)


def test_validate_price_tick_invalid():
    assert not validate_price_tick(8501, 25.0)


def test_validator_valid_buy():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="buy",
        shares=1000,
        price=8500,
        buying_power=100_000_000,
    )
    assert result.is_valid
    assert len(result.errors) == 0


def test_validator_invalid_lot_size():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="buy",
        shares=150,
        price=8500,
    )
    assert not result.is_valid
    assert any("INVALID_LOT" in e for e in result.errors)


def test_validator_insufficient_funds():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="buy",
        shares=1000,
        price=8500,
        buying_power=1_000_000,
    )
    assert not result.is_valid
    assert any("INSUFFICIENT_FUNDS" in e for e in result.errors)


def test_validator_price_limit_exceeded():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="buy",
        shares=1000,
        price=11000,
        reference_price=8500,
    )
    assert not result.is_valid
    assert any("PRICE_LIMIT" in e for e in result.errors)


def test_validator_price_limit_below():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="sell",
        shares=1000,
        price=6000,
        reference_price=8500,
        current_shares=1000,
    )
    assert not result.is_valid
    assert any("PRICE_LIMIT" in e for e in result.errors)


def test_validator_insufficient_shares():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="sell",
        shares=1000,
        price=8500,
        current_shares=500,
    )
    assert not result.is_valid
    assert any("INSUFFICIENT_SHARES" in e for e in result.errors)


def test_validator_sell_closing_position_odd_lot():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="sell",
        shares=350,
        price=8500,
        current_shares=350,
    )
    assert result.is_valid  # Odd-lot sell allowed if closing position


def test_validator_tick_warning():
    v = OrderValidator()
    result = v.validate(
        ticker="BBCA.JK",
        side="buy",
        shares=1000,
        price=8501,  # Not a valid tick for 25 IDR tick size
    )
    assert result.is_valid  # Tick is a warning, not error
    assert any("TICK_SIZE" in w for w in result.warnings)


# --- Broker adapter tests ---


def test_mock_broker_buy():
    broker = MockBroker()
    order = Order(
        id="TEST-001",
        ticker="BBCA.JK",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        shares=1000,
        price=8500,
    )
    fill = broker.submit(order)
    assert fill is not None
    assert fill.shares == 1000
    assert fill.price == 8500
    assert fill.commission == 0.0


def test_mock_broker_no_price():
    broker = MockBroker()
    order = Order(
        id="TEST-002",
        ticker="BBCA.JK",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        shares=1000,
        price=None,
    )
    fill = broker.submit(order)
    assert fill is None


def test_paper_broker_buy():
    broker = PaperBroker()
    order = Order(
        id="TEST-003",
        ticker="BBCA.JK",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        shares=1000,
        price=8500,
    )
    fill = broker.submit(order)
    assert fill is not None
    assert fill.shares == 1000
    assert fill.price > 8500  # Slippage increases buy price
    assert fill.commission > 0
    assert fill.sales_tax == 0  # No tax on buy


def test_paper_broker_sell():
    broker = PaperBroker()
    order = Order(
        id="TEST-004",
        ticker="BBCA.JK",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        shares=1000,
        price=8500,
    )
    fill = broker.submit(order)
    assert fill is not None
    assert fill.price < 8500  # Slippage decreases sell price
    assert fill.commission > 0
    assert fill.sales_tax > 0  # Tax on sell


def test_real_broker_not_connected():
    broker = RealBroker("sinarmas")
    order = Order(
        id="TEST-005",
        ticker="BBCA.JK",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        shares=1000,
        price=8500,
    )
    fill = broker.submit(order)
    assert fill is None  # Not connected


def test_real_broker_connect_stub():
    broker = RealBroker("sinarmas")
    result = broker.connect("key", "secret")
    assert result is False  # Stub always returns False
