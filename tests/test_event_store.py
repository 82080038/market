"""Tests for OMS event sourcing (Gap #6)."""

from __future__ import annotations

import json

import pytest

from market.execution.event_store import (
    EventStore,
    EventType,
    OrderAggregate,
    OrderStatus,
    OrderEvent,
    replay_all_orders,
    replay_order,
)


@pytest.fixture
def store() -> EventStore:
    return EventStore()


@pytest.fixture
def order(store: EventStore) -> OrderAggregate:
    agg = OrderAggregate("ORD-001")
    agg.create(
        store, ticker="BBCA.JK", side="buy",
        order_type="LIMIT", quantity=100, price=90000,
    )
    return agg


def test_event_type_enum():
    """EventType has all expected values."""
    assert EventType.ORDER_CREATED.value == "OrderCreated"
    assert EventType.ORDER_FILLED.value == "OrderFilled"
    assert EventType.ORDER_CANCELLED.value == "OrderCancelled"
    assert EventType.ORDER_REJECTED.value == "OrderRejected"


def test_event_store_append(store: EventStore):
    """EventStore.append stores events."""
    event = OrderEvent(
        event_id="evt_001", order_id="ORD-1",
        event_type=EventType.ORDER_CREATED,
        timestamp="2026-01-01T00:00:00+00:00",
        sequence=1, payload={"ticker": "X"},
    )
    store.append(event)
    assert store.count() == 1
    assert store.order_count() == 1


def test_event_store_get_events(store: EventStore):
    """get_events returns events for an order."""
    e1 = OrderEvent(
        event_id="e1", order_id="ORD-1",
        event_type=EventType.ORDER_CREATED,
        timestamp="2026-01-01", sequence=1,
    )
    e2 = OrderEvent(
        event_id="e2", order_id="ORD-1",
        event_type=EventType.ORDER_SUBMITTED,
        timestamp="2026-01-01", sequence=2,
    )
    e3 = OrderEvent(
        event_id="e3", order_id="ORD-2",
        event_type=EventType.ORDER_CREATED,
        timestamp="2026-01-01", sequence=1,
    )
    store.append(e1)
    store.append(e2)
    store.append(e3)

    ord1_events = store.get_events("ORD-1")
    assert len(ord1_events) == 2
    assert all(e.order_id == "ORD-1" for e in ord1_events)


def test_event_store_get_events_since(store: EventStore):
    """get_events_since returns events after a sequence number."""
    for i in range(1, 4):
        store.append(OrderEvent(
            event_id=f"e{i}", order_id="ORD-1",
            event_type=EventType.ORDER_CREATED,
            timestamp="2026-01-01", sequence=i,
        ))
    since = store.get_events_since("ORD-1", 1)
    assert len(since) == 2
    assert all(e.sequence > 1 for e in since)


def test_next_sequence(store: EventStore):
    """next_sequence returns correct next number."""
    assert store.next_sequence("ORD-1") == 1
    store.append(OrderEvent(
        event_id="e1", order_id="ORD-1",
        event_type=EventType.ORDER_CREATED,
        timestamp="2026-01-01", sequence=1,
    ))
    assert store.next_sequence("ORD-1") == 2


def test_order_create(store: EventStore):
    """OrderAggregate.create emits OrderCreated event."""
    agg = OrderAggregate("ORD-001")
    event = agg.create(
        store, ticker="BBCA.JK", side="buy",
        order_type="LIMIT", quantity=100, price=90000,
    )
    assert event.event_type == EventType.ORDER_CREATED
    assert agg.state.ticker == "BBCA.JK"
    assert agg.state.side == "buy"
    assert agg.state.quantity == 100
    assert agg.state.price == 90000
    assert agg.state.status == OrderStatus.DRAFT
    assert agg.state.version == 1


def test_order_submit(store: EventStore, order: OrderAggregate):
    """submit transitions to SUBMITTED."""
    order.submit(store)
    assert order.state.status == OrderStatus.SUBMITTED
    assert order.state.version == 2


def test_order_pending(store: EventStore, order: OrderAggregate):
    """mark_pending transitions to PENDING."""
    order.submit(store)
    order.mark_pending(store)
    assert order.state.status == OrderStatus.PENDING


def test_order_partial_fill(store: EventStore, order: OrderAggregate):
    """partial_fill accumulates filled quantity."""
    order.submit(store)
    order.mark_pending(store)
    order.partial_fill(store, fill_quantity=50, fill_price=90000, commission=675)
    assert order.state.status == OrderStatus.PARTIALLY_FILLED
    assert order.state.filled_quantity == 50
    assert order.state.commission == 675


def test_order_full_fill(store: EventStore, order: OrderAggregate):
    """fill transitions to FILLED."""
    order.submit(store)
    order.mark_pending(store)
    order.fill(store, fill_quantity=100, fill_price=90000, commission=1350, sales_tax=9000)
    assert order.state.status == OrderStatus.FILLED
    assert order.state.filled_quantity == 100
    assert order.state.commission == 1350
    assert order.state.sales_tax == 9000
    assert order.is_terminal


def test_order_cancel(store: EventStore, order: OrderAggregate):
    """cancel transitions to CANCELLED."""
    order.submit(store)
    order.cancel(store)
    assert order.state.status == OrderStatus.CANCELLED
    assert order.is_terminal


def test_order_reject(store: EventStore, order: OrderAggregate):
    """reject transitions to REJECTED with reason."""
    order.submit(store)
    order.reject(store, reason="Insufficient funds")
    assert order.state.status == OrderStatus.REJECTED
    assert order.state.rejection_reason == "Insufficient funds"
    assert order.is_terminal


def test_order_modify(store: EventStore, order: OrderAggregate):
    """modify updates price and quantity."""
    order.modify(store, price=91000, quantity=200)
    assert order.state.price == 91000
    assert order.state.quantity == 200


def test_replay_order(store: EventStore, order: OrderAggregate):
    """replay_order reconstructs state from events."""
    order.submit(store)
    order.mark_pending(store)
    order.fill(store, fill_quantity=100, fill_price=90000, commission=1350)

    # Replay from event store
    replayed = replay_order("ORD-001", store)
    assert replayed.state.ticker == "BBCA.JK"
    assert replayed.state.status == OrderStatus.FILLED
    assert replayed.state.filled_quantity == 100
    assert replayed.state.commission == 1350
    assert replayed.state.version == 4


def test_replay_all_orders(store: EventStore):
    """replay_all_orders reconstructs all orders."""
    agg1 = OrderAggregate("ORD-1")
    agg1.create(store, ticker="A", side="buy", order_type="LIMIT", quantity=100)
    agg1.fill(store, fill_quantity=100, fill_price=100)

    agg2 = OrderAggregate("ORD-2")
    agg2.create(store, ticker="B", side="sell", order_type="MARKET", quantity=200)
    agg2.cancel(store)

    orders = replay_all_orders(store)
    assert len(orders) == 2
    assert orders["ORD-1"].state.status == OrderStatus.FILLED
    assert orders["ORD-2"].state.status == OrderStatus.CANCELLED


def test_event_to_dict_roundtrip():
    """OrderEvent serializes and deserializes correctly."""
    event = OrderEvent(
        event_id="e1", order_id="ORD-1",
        event_type=EventType.ORDER_FILLED,
        timestamp="2026-01-01T00:00:00+00:00",
        sequence=3,
        payload={"fill_quantity": 100, "fill_price": 90000},
    )
    d = event.to_dict()
    restored = OrderEvent.from_dict(d)
    assert restored.event_id == event.event_id
    assert restored.event_type == event.event_type
    assert restored.payload == event.payload


def test_event_store_json_roundtrip(store: EventStore, order: OrderAggregate):
    """EventStore serializes to JSON and back."""
    order.submit(store)
    order.fill(store, fill_quantity=100, fill_price=90000)

    json_str = store.to_json()
    restored = EventStore.from_json(json_str)
    assert restored.count() == store.count()

    # Verify replay works on restored store
    replayed = replay_order("ORD-001", restored)
    assert replayed.state.status == OrderStatus.FILLED


def test_multiple_partial_fills_accumulate(store: EventStore, order: OrderAggregate):
    """Multiple partial fills accumulate correctly."""
    order.submit(store)
    order.mark_pending(store)
    order.partial_fill(store, fill_quantity=30, fill_price=90000, commission=270)
    order.partial_fill(store, fill_quantity=30, fill_price=90500, commission=271.5)
    order.partial_fill(store, fill_quantity=40, fill_price=91000, commission=364)

    assert order.state.filled_quantity == 100
    assert order.state.commission == pytest.approx(905.5)
    assert order.state.status == OrderStatus.PARTIALLY_FILLED


def test_event_store_count(store: EventStore):
    """count and order_count track correctly."""
    assert store.count() == 0
    assert store.order_count() == 0

    agg = OrderAggregate("ORD-1")
    agg.create(store, ticker="X", side="buy", order_type="LIMIT", quantity=100)
    agg.submit(store)

    assert store.count() == 2
    assert store.order_count() == 1
