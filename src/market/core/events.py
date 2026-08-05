"""Event broker — pub/sub middleware for decoupling modules.

This is the single communication channel between all modules.
No module imports another module directly. Instead:
  - Producers emit events:  broker.emit("data.fetched", {"ticker": ...})
  - Consumers subscribe:    broker.subscribe("data.fetched", handler)
  - The broker routes events without either side knowing about the other.

Event naming convention:  "<domain>.<action>.<result>"
  Examples:
    "data.fetch.requested"   — someone wants data fetched
    "data.fetch.completed"   — data has been fetched and stored
    "data.recompute.requested" — someone wants indicators recomputed
    "data.recompute.completed" — indicators have been recomputed
    "data.export.requested"  — someone wants parquet export
    "data.export.completed"  — parquet export done
    "health.check.requested" — someone wants health checks
    "health.check.completed" — health checks done (with report)

Usage:
    from market.core.events import broker

    # Subscribe (anywhere, at startup)
    broker.subscribe("data.fetch.completed", my_handler)

    # Emit (anywhere, when something happens)
    broker.emit("data.fetch.completed", {"ticker": "BBCA.JK", "rows": 100})

Design principles:
  - Synchronous delivery (simple, deterministic for single-user app)
  - Handlers run in subscription order
  - Handler errors are caught and logged, do not block other handlers
  - No circular dependencies possible (broker is the only hub)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[["Event"], Any]


@dataclass(frozen=True)
class Event:
    """An immutable event passed through the broker.

    Attributes:
        name: Event name following "<domain>.<action>.<result>" convention.
        payload: Arbitrary data dict — consumers define what they expect.
        timestamp: When the event was emitted (UTC).
        source: Name of the module that emitted the event (for debugging).
    """

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(UTC).isoformat())
        if not self.source:
            # Auto-detect caller module from stack (best-effort)
            import sys
            frame = sys._getframe(2)  # skip __post_init__ and emit
            mod = frame.f_globals.get("__name__", "unknown")
            object.__setattr__(self, "source", mod)


class EventBroker:
    """Synchronous pub/sub event broker.

    Central hub for all inter-module communication.
    Modules subscribe to events they care about and emit events
    when they complete work. No module needs to know about any other.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 1000

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event.

        Multiple handlers can subscribe to the same event.
        Handlers run in subscription order.

        Args:
            event_name: Event to listen for (e.g. "data.fetch.completed").
            handler: Callable that receives an Event.
        """
        self._handlers[event_name].append(handler)
        logger.debug("Subscribed %s to '%s'", handler.__qualname__, event_name)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """Remove a handler subscription."""
        if event_name in self._handlers:
            self._handlers[event_name] = [
                h for h in self._handlers[event_name] if h is not handler
            ]

    def emit(self, event_name: str, payload: dict[str, Any] | None = None) -> Event:
        """Emit an event to all subscribers.

        Handlers are called synchronously in subscription order.
        If a handler raises, it's logged but does not block other handlers.

        Args:
            event_name: Event to emit (e.g. "data.fetch.completed").
            payload: Data to pass to handlers.

        Returns:
            The Event that was emitted.
        """
        event = Event(name=event_name, payload=payload or {})
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._handlers.get(event_name, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    "Event handler %s failed for '%s': %s",
                    handler.__qualname__, event_name, e,
                    exc_info=True,
                )

        logger.debug("Event '%s' delivered to %d handlers", event_name, len(handlers))
        return event

    @property
    def history(self) -> list[Event]:
        """Recent event history (for debugging/audit)."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

    def handler_count(self, event_name: str) -> int:
        """Number of handlers subscribed to an event."""
        return len(self._handlers.get(event_name, []))

    def registered_events(self) -> list[str]:
        """All event names that have at least one handler."""
        return sorted(
            name for name, handlers in self._handlers.items() if handlers
        )


# Singleton broker — the single communication hub for the entire app
broker = EventBroker()
