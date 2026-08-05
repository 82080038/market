"""Tests for OMS state machine."""

from __future__ import annotations

import pytest

from market.execution.oms import (
    OMS,
    OrderSide,
    OrderStatus,
    OrderType,
)


def test_oms_create_order():
    oms = OMS()
    order = oms.create_order(
        ticker="BBCA.JK",
        side=OrderSide.BUY,
        shares=1000,
        order_type=OrderType.LIMIT,
        price=8500,
    )
    assert order.id == "ORD-000001"
    assert order.status == OrderStatus.NEW
    assert order.ticker == "BBCA.JK"
    assert order.side == OrderSide.BUY
    assert order.shares == 1000
    assert order.price == 8500
    assert order.remaining_shares == 1000


def test_oms_valid_transition_new_to_pending():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    updated = oms.transition(order.id, OrderStatus.PENDING)
    assert updated.status == OrderStatus.PENDING


def test_oms_invalid_transition_new_to_filled():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    with pytest.raises(ValueError, match="Invalid transition"):
        oms.transition(order.id, OrderStatus.FILLED)


def test_oms_add_fill_partial():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    oms.transition(order.id, OrderStatus.PENDING)
    oms.add_fill(order.id, 500, 8490)
    updated = oms.get_order(order.id)
    assert updated.status == OrderStatus.PARTIAL
    assert updated.filled_shares == 500
    assert updated.avg_fill_price == 8490.0
    assert updated.remaining_shares == 500


def test_oms_add_fill_complete():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    oms.transition(order.id, OrderStatus.PENDING)
    oms.add_fill(order.id, 1000, 8500)
    updated = oms.get_order(order.id)
    assert updated.status == OrderStatus.FILLED
    assert updated.filled_shares == 1000


def test_oms_multiple_fills_avg_price():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    oms.transition(order.id, OrderStatus.PENDING)
    oms.add_fill(order.id, 300, 8490)
    oms.add_fill(order.id, 700, 8510)
    updated = oms.get_order(order.id)
    assert updated.status == OrderStatus.FILLED
    # avg = (300*8490 + 700*8510) / 1000 = 8504
    assert abs(updated.avg_fill_price - 8504.0) < 0.01


def test_oms_cancel_order():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    oms.transition(order.id, OrderStatus.PENDING)
    oms.cancel(order.id)
    assert oms.get_order(order.id).status == OrderStatus.CANCELLED


def test_oms_cancel_filled_rejected():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    oms.transition(order.id, OrderStatus.PENDING)
    oms.add_fill(order.id, 1000, 8500)
    with pytest.raises(ValueError, match="Invalid transition"):
        oms.cancel(order.id)


def test_oms_get_open_orders():
    oms = OMS()
    o1 = oms.create_order("A.JK", OrderSide.BUY, 100, OrderType.MARKET)
    o2 = oms.create_order("B.JK", OrderSide.SELL, 100, OrderType.MARKET)
    oms.transition(o1.id, OrderStatus.PENDING)
    oms.transition(o2.id, OrderStatus.PENDING)
    oms.add_fill(o2.id, 100, 100)
    open_orders = oms.get_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0].id == o1.id


def test_oms_order_not_found():
    oms = OMS()
    with pytest.raises(ValueError, match="not found"):
        oms.transition("NONEXISTENT", OrderStatus.PENDING)


def test_oms_reject_order():
    oms = OMS()
    order = oms.create_order("BBCA.JK", OrderSide.BUY, 1000, OrderType.LIMIT, 8500)
    oms.transition(order.id, OrderStatus.REJECTED, rejection_reason="INVALID_PRICE")
    updated = oms.get_order(order.id)
    assert updated.status == OrderStatus.REJECTED
    assert updated.rejection_reason == "INVALID_PRICE"
