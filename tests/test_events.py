"""Tests for the event broker (core/events module)."""

from __future__ import annotations

from market.core.events import EventBroker, Event


def test_event_creation():
    """Event should auto-populate timestamp and source."""
    event = Event(name="test.event", payload={"key": "value"})
    assert event.name == "test.event"
    assert event.payload == {"key": "value"}
    assert event.timestamp != ""


def test_subscribe_and_emit():
    """Handler should be called when event is emitted."""
    broker = EventBroker()
    received = []

    def handler(event: Event) -> None:
        received.append(event)

    broker.subscribe("test.event", handler)
    broker.emit("test.event", {"data": 123})

    assert len(received) == 1
    assert received[0].payload == {"data": 123}


def test_multiple_handlers():
    """All handlers should be called in order."""
    broker = EventBroker()
    order = []

    broker.subscribe("evt", lambda e: order.append("first"))
    broker.subscribe("evt", lambda e: order.append("second"))
    broker.emit("evt", {})

    assert order == ["first", "second"]


def test_handler_error_does_not_block_others():
    """If one handler fails, others should still run."""
    broker = EventBroker()
    results = []

    def failing_handler(e: Event) -> None:
        raise ValueError("boom")

    def good_handler(e: Event) -> None:
        results.append("called")

    broker.subscribe("evt", failing_handler)
    broker.subscribe("evt", good_handler)
    broker.emit("evt", {})

    assert results == ["called"]


def test_unsubscribe():
    """Unsubscribed handler should not be called."""
    broker = EventBroker()
    received = []

    def handler(event: Event) -> None:
        received.append(event)

    broker.subscribe("evt", handler)
    broker.unsubscribe("evt", handler)
    broker.emit("evt", {})

    assert len(received) == 0


def test_no_handlers_silent():
    """Emitting event with no handlers should not error."""
    broker = EventBroker()
    event = broker.emit("nobody.listens", {"x": 1})
    assert event.name == "nobody.listens"


def test_event_history():
    """Broker should track event history."""
    broker = EventBroker()
    broker.emit("evt1", {"a": 1})
    broker.emit("evt2", {"b": 2})
    assert len(broker.history) == 2
    assert broker.history[0].name == "evt1"
    assert broker.history[1].name == "evt2"


def test_handler_count():
    """handler_count should return correct count."""
    broker = EventBroker()
    broker.subscribe("evt", lambda e: None)
    broker.subscribe("evt", lambda e: None)
    assert broker.handler_count("evt") == 2
    assert broker.handler_count("other") == 0


def test_registered_events():
    """registered_events should list events with handlers."""
    broker = EventBroker()
    broker.subscribe("a.b.c", lambda e: None)
    broker.subscribe("x.y.z", lambda e: None)
    events = broker.registered_events()
    assert "a.b.c" in events
    assert "x.y.z" in events


def test_event_is_immutable():
    """Event should be frozen (immutable)."""
    event = Event(name="test", payload={"x": 1})
    try:
        event.name = "other"  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass  # Expected — frozen dataclass


def test_event_chain():
    """One handler emitting another event should work (chain)."""
    broker = EventBroker()
    chain = []

    def handler_a(e: Event) -> None:
        chain.append("a")
        broker.emit("b", {})

    def handler_b(e: Event) -> None:
        chain.append("b")

    broker.subscribe("a", handler_a)
    broker.subscribe("b", handler_b)
    broker.emit("a", {})

    assert chain == ["a", "b"]
