"""Policy & Corporate Event Impact Scorer for IDX (pustaka/89, pustaka/10).

Scores the impact of policy and corporate events on Indonesian stock market
tickers. Supports market-wide events (BI/Fed rate decisions, geopolitical,
pandemic, election) and ticker-specific events (buyback, rights issue, stock
split, dividend, merger, earnings).

Design guarantees:
    - **No look-ahead bias**: only events with ``event_date <= as_of_date``
      contribute to ``compute_event_signal``. Future events are surfaced via
      ``get_upcoming_events`` and used to *reduce* confidence (uncertainty),
      never to inflate the score.
    - **CPU-only**: pure Python math, no GPU/network required.
    - Exponential decay: recent events weigh more than stale ones.

References:
    - pustaka/89-faktor-pasar-modal-analisis-implementasi.md
    - pustaka/10-regulasi-pasar-modal.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class EventType(Enum):
    """Policy or corporate event type."""

    BI_RATE_CUT = "bi_rate_cut"
    BI_RATE_HIKE = "bi_rate_hike"
    FED_RATE_CUT = "fed_rate_cut"
    FED_RATE_HIKE = "fed_rate_hike"
    BUYBACK = "buyback"
    RIGHTS_ISSUE = "rights_issue"
    STOCK_SPLIT = "stock_split"
    DIVIDEND = "dividend"
    MERGER = "merger"
    AUTO_REJECT_CHANGE = "auto_reject_change"
    GEOPOLITICAL = "geopolitical"
    TRADE_WAR = "trade_war"
    PANDEMIC = "pandemic"
    ELECTION = "election"
    EARNINGS_BEAT = "earnings_beat"
    EARNINGS_MISS = "earnings_miss"
    OTHER = "other"


class EventDirection(Enum):
    """Directional bias of an event."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class EventScope(Enum):
    """Scope of an event's impact."""

    MARKET_WIDE = "market_wide"
    TICKER_SPECIFIC = "ticker_specific"


# Default (direction, scope, base_impact) per event type.
# base_impact in [-100, +100]; positive = bullish, negative = bearish.
DEFAULT_IMPACTS: dict[EventType, tuple[EventDirection, EventScope, float]] = {
    EventType.BI_RATE_CUT: (EventDirection.BULLISH, EventScope.MARKET_WIDE, 30.0),
    EventType.BI_RATE_HIKE: (EventDirection.BEARISH, EventScope.MARKET_WIDE, -40.0),
    EventType.FED_RATE_CUT: (EventDirection.BULLISH, EventScope.MARKET_WIDE, 20.0),
    EventType.FED_RATE_HIKE: (EventDirection.BEARISH, EventScope.MARKET_WIDE, -25.0),
    EventType.BUYBACK: (EventDirection.BULLISH, EventScope.TICKER_SPECIFIC, 50.0),
    EventType.RIGHTS_ISSUE: (EventDirection.BEARISH, EventScope.TICKER_SPECIFIC, -45.0),
    EventType.STOCK_SPLIT: (EventDirection.BULLISH, EventScope.TICKER_SPECIFIC, 15.0),
    EventType.DIVIDEND: (EventDirection.BULLISH, EventScope.TICKER_SPECIFIC, 10.0),
    EventType.MERGER: (EventDirection.NEUTRAL, EventScope.TICKER_SPECIFIC, 20.0),
    EventType.AUTO_REJECT_CHANGE: (EventDirection.NEUTRAL, EventScope.MARKET_WIDE, 0.0),
    EventType.GEOPOLITICAL: (EventDirection.BEARISH, EventScope.MARKET_WIDE, -40.0),
    EventType.TRADE_WAR: (EventDirection.BEARISH, EventScope.MARKET_WIDE, -35.0),
    EventType.PANDEMIC: (EventDirection.BEARISH, EventScope.MARKET_WIDE, -50.0),
    EventType.ELECTION: (EventDirection.BEARISH, EventScope.MARKET_WIDE, -20.0),
    EventType.EARNINGS_BEAT: (EventDirection.BULLISH, EventScope.TICKER_SPECIFIC, 25.0),
    EventType.EARNINGS_MISS: (EventDirection.BEARISH, EventScope.TICKER_SPECIFIC, -30.0),
    EventType.OTHER: (EventDirection.NEUTRAL, EventScope.MARKET_WIDE, 0.0),
}


@dataclass
class EventImpact:
    """A single policy or corporate event with its impact parameters.

    Attributes:
        event_type: Category of the event (see :class:`EventType`).
        direction: Bullish/bearish/neutral bias.
        scope: Whether the event affects the whole market or one ticker.
        base_impact: Raw impact magnitude in [-100, +100] before decay.
        event_date: When the event occurred (or was announced).
        ticker: Affected ticker for TICKER_SPECIFIC events; ``None`` for
            MARKET_WIDE events.
        description: Human-readable description of the event.
    """

    event_type: EventType
    direction: EventDirection
    scope: EventScope
    base_impact: float
    event_date: datetime
    ticker: str | None = None
    description: str = ""


def event_decay(days_since: float, half_life: float = 10.0) -> float:
    """Exponential decay factor for an event ``days_since`` days old.

    Returns 1.0 at day 0, 0.5 at ``half_life`` days, 0.125 at 3*half_life days.

    Args:
        days_since: Elapsed days since the event date (>= 0).
        half_life: Days for the impact to halve. Default 10.

    Returns:
        Decay multiplier in (0.0, 1.0].
    """
    if days_since < 0:
        return 0.0
    return 0.5 ** (days_since / half_life)


@dataclass
class EventSignal:
    """Composite event-driven signal for a single ticker.

    Attributes:
        score: Weighted composite impact score (can be negative).
        direction: ``"bullish"`` if score > 5, ``"bearish"`` if < -5, else
            ``"neutral"``.
        confidence: Confidence in [0.0, 1.0], derived from ``abs(score)/100``.
        active_events: List of contributing events (dicts with metadata).
        market_wide_score: Sum of market-wide contributions.
        ticker_specific_score: Sum of ticker-specific contributions.
    """

    score: float
    direction: str
    confidence: float
    active_events: list[dict] = field(default_factory=list)
    market_wide_score: float = 0.0
    ticker_specific_score: float = 0.0


@dataclass
class UpcomingEvent:
    """A future event within the lookahead window.

    Attributes:
        event_type: Category of the event.
        event_date: Scheduled/expected date of the event.
        days_until: Days from ``as_of_date`` until ``event_date``.
        description: Human-readable description.
    """

    event_type: EventType
    event_date: datetime
    days_until: int
    description: str = ""


def compute_event_signal(
    ticker: str,
    events: list[EventImpact],
    as_of_date: datetime,
    half_life: float = 10.0,
) -> EventSignal:
    """Compute a composite event-driven signal for ``ticker`` as of ``as_of_date``.

    No look-ahead: only events with ``event_date <= as_of_date`` contribute.
    Market-wide events are weighted 0.3 per ticker (distributed effect);
    ticker-specific events are weighted 1.0 and only count when
    ``event.ticker == ticker``.

    Args:
        ticker: Target ticker (e.g. ``"BBCA.JK"``).
        events: List of :class:`EventImpact` instances (may include future
            events, which are filtered out).
        as_of_date: Evaluation cutoff date.
        half_life: Decay half-life in days (default 10).

    Returns:
        :class:`EventSignal` with composite score, direction, and confidence.
    """
    market_wide_score = 0.0
    ticker_specific_score = 0.0
    active_events: list[dict] = []

    for event in events:
        # No look-ahead: skip events that haven't happened yet.
        if event.event_date > as_of_date:
            continue

        days_since = (as_of_date - event.event_date).total_seconds() / 86400.0
        decay = event_decay(days_since, half_life=half_life)
        if decay <= 0.0:
            continue

        if event.scope is EventScope.MARKET_WIDE:
            weight = 0.3
            contribution = event.base_impact * decay * weight
            market_wide_score += contribution
            active_events.append({
                "event_type": event.event_type.value,
                "direction": event.direction.value,
                "scope": event.scope.value,
                "days_since": round(days_since, 2),
                "decay": round(decay, 4),
                "weight": weight,
                "contribution": round(contribution, 4),
                "description": event.description,
            })
        elif event.scope is EventScope.TICKER_SPECIFIC:
            # Only affects the target ticker.
            if event.ticker is None or event.ticker != ticker:
                continue
            weight = 1.0
            contribution = event.base_impact * decay * weight
            ticker_specific_score += contribution
            active_events.append({
                "event_type": event.event_type.value,
                "direction": event.direction.value,
                "scope": event.scope.value,
                "ticker": event.ticker,
                "days_since": round(days_since, 2),
                "decay": round(decay, 4),
                "weight": weight,
                "contribution": round(contribution, 4),
                "description": event.description,
            })

    score = market_wide_score + ticker_specific_score

    if score > 5:
        direction = "bullish"
    elif score < -5:
        direction = "bearish"
    else:
        direction = "neutral"

    confidence = min(1.0, abs(score) / 100.0)

    return EventSignal(
        score=round(score, 4),
        direction=direction,
        confidence=round(confidence, 4),
        active_events=active_events,
        market_wide_score=round(market_wide_score, 4),
        ticker_specific_score=round(ticker_specific_score, 4),
    )


def get_upcoming_events(
    events: list[EventImpact],
    as_of_date: datetime,
    lookahead_days: int = 14,
) -> list[UpcomingEvent]:
    """Return events scheduled within ``(as_of_date, as_of_date + lookahead_days]``.

    Args:
        events: List of :class:`EventImpact` instances.
        as_of_date: Evaluation cutoff date.
        lookahead_days: How many days forward to scan (default 14).

    Returns:
        List of :class:`UpcomingEvent` sorted by ``days_until`` ascending.
    """
    horizon = as_of_date + timedelta(days=lookahead_days)
    upcoming: list[UpcomingEvent] = []
    for event in events:
        if as_of_date < event.event_date <= horizon:
            days_until = (event.event_date - as_of_date).days
            upcoming.append(UpcomingEvent(
                event_type=event.event_type,
                event_date=event.event_date,
                days_until=days_until,
                description=event.description,
            ))
    upcoming.sort(key=lambda e: e.days_until)
    return upcoming


def pre_event_confidence_reduction(
    upcoming_events: list[UpcomingEvent],
    reduction_per_day: float = 0.02,
) -> float:
    """Compute a confidence multiplier accounting for imminent upcoming events.

    For each upcoming event within 7 days, confidence is reduced by
    ``(7 - days_until) * reduction_per_day``. The aggregate multiplier is
    clamped to ``[0.8, 1.0]``.

    Args:
        upcoming_events: Output of :func:`get_upcoming_events`.
        reduction_per_day: Confidence reduction per day of proximity
            (default 0.02).

    Returns:
        Float multiplier in [0.8, 1.0].
    """
    total_reduction = 0.0
    for event in upcoming_events:
        if 0 <= event.days_until <= 7:
            total_reduction += (7 - event.days_until) * reduction_per_day
    multiplier = 1.0 - total_reduction
    return max(0.8, min(1.0, multiplier))
