"""Tests for policy_event_scorer (pustaka/89, pustaka/10)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from market.analysis.policy_event_scorer import (
    DEFAULT_IMPACTS,
    EventDirection,
    EventImpact,
    EventScope,
    EventType,
    compute_event_signal,
    event_decay,
    get_upcoming_events,
    pre_event_confidence_reduction,
)

AS_OF = datetime(2024, 6, 10)


def _make(
    event_type: EventType,
    days_offset: int,
    ticker: str | None = None,
    description: str = "",
) -> EventImpact:
    """Helper: build an EventImpact using DEFAULT_IMPACTS defaults."""
    direction, scope, base_impact = DEFAULT_IMPACTS[event_type]
    return EventImpact(
        event_type=event_type,
        direction=direction,
        scope=scope,
        base_impact=base_impact,
        event_date=AS_OF - timedelta(days=days_offset),
        ticker=ticker,
        description=description,
    )


# --- event_decay -----------------------------------------------------------

def test_event_decay_day_zero():
    assert event_decay(0) == pytest.approx(1.0)


def test_event_decay_day_ten():
    assert event_decay(10) == pytest.approx(0.5)


def test_event_decay_day_thirty():
    assert event_decay(30) == pytest.approx(0.125)


def test_event_decay_negative_days():
    assert event_decay(-1) == 0.0


# --- compute_event_signal: bullish / bearish -------------------------------

def test_bullish_bi_rate_cut():
    events = [_make(EventType.BI_RATE_CUT, days_offset=1, description="BI cut 25bps")]
    sig = compute_event_signal("BBCA.JK", events, AS_OF)
    assert sig.score > 5
    assert sig.direction == "bullish"
    assert sig.market_wide_score > 0
    assert sig.confidence > 0


def test_bearish_bi_rate_hike():
    events = [_make(EventType.BI_RATE_HIKE, days_offset=1, description="BI hike 50bps")]
    sig = compute_event_signal("BBCA.JK", events, AS_OF)
    assert sig.score < -5
    assert sig.direction == "bearish"
    assert sig.market_wide_score < 0


# --- ticker-specific isolation ---------------------------------------------

def test_ticker_specific_buyback_affects_only_target():
    buyback = EventImpact(
        event_type=EventType.BUYBACK,
        direction=EventDirection.BULLISH,
        scope=EventScope.TICKER_SPECIFIC,
        base_impact=50.0,
        event_date=AS_OF - timedelta(days=1),
        ticker="BBCA.JK",
        description="BBCA buyback",
    )
    sig_bbca = compute_event_signal("BBCA.JK", [buyback], AS_OF)
    sig_bbri = compute_event_signal("BBRI.JK", [buyback], AS_OF)
    assert sig_bbca.score > 5
    assert sig_bbca.direction == "bullish"
    assert sig_bbca.ticker_specific_score > 0
    # BBRI is unaffected by BBCA's buyback.
    assert sig_bbri.ticker_specific_score == 0
    assert sig_bbri.score == 0
    assert sig_bbri.direction == "neutral"


# --- no look-ahead ---------------------------------------------------------

def test_no_look_ahead_future_events_ignored():
    future = EventImpact(
        event_type=EventType.BI_RATE_CUT,
        direction=EventDirection.BULLISH,
        scope=EventScope.MARKET_WIDE,
        base_impact=30.0,
        event_date=AS_OF + timedelta(days=5),
        description="Future BI cut",
    )
    sig = compute_event_signal("BBCA.JK", [future], AS_OF)
    assert sig.score == 0
    assert sig.direction == "neutral"
    assert sig.active_events == []


# --- decay ordering --------------------------------------------------------

def test_old_event_less_impact_than_recent():
    recent = _make(EventType.BI_RATE_CUT, days_offset=1)
    old = _make(EventType.BI_RATE_CUT, days_offset=30)
    sig_recent = compute_event_signal("BBCA.JK", [recent], AS_OF)
    sig_old = compute_event_signal("BBCA.JK", [old], AS_OF)
    assert sig_recent.score > sig_old.score
    assert sig_old.score > 0  # still positive, just smaller


# --- get_upcoming_events ---------------------------------------------------

def test_get_upcoming_events_within_lookahead():
    events = [
        _make(EventType.BI_RATE_CUT, days_offset=1),  # past, excluded
        EventImpact(
            event_type=EventType.FED_RATE_CUT,
            direction=EventDirection.BULLISH,
            scope=EventScope.MARKET_WIDE,
            base_impact=20.0,
            event_date=AS_OF + timedelta(days=3),
            description="Fed cut in 3d",
        ),
        EventImpact(
            event_type=EventType.ELECTION,
            direction=EventDirection.BEARISH,
            scope=EventScope.MARKET_WIDE,
            base_impact=-20.0,
            event_date=AS_OF + timedelta(days=20),  # outside 14d window
            description="Election in 20d",
        ),
    ]
    upcoming = get_upcoming_events(events, AS_OF, lookahead_days=14)
    assert len(upcoming) == 1
    assert upcoming[0].event_type is EventType.FED_RATE_CUT
    assert upcoming[0].days_until == 3


def test_get_upcoming_events_sorted_by_days_until():
    events = [
        EventImpact(
            event_type=EventType.ELECTION,
            direction=EventDirection.BEARISH,
            scope=EventScope.MARKET_WIDE,
            base_impact=-20.0,
            event_date=AS_OF + timedelta(days=10),
            description="Election",
        ),
        EventImpact(
            event_type=EventType.BI_RATE_CUT,
            direction=EventDirection.BULLISH,
            scope=EventScope.MARKET_WIDE,
            base_impact=30.0,
            event_date=AS_OF + timedelta(days=2),
            description="BI cut",
        ),
    ]
    upcoming = get_upcoming_events(events, AS_OF, lookahead_days=14)
    assert [e.days_until for e in upcoming] == [2, 10]


# --- pre_event_confidence_reduction ---------------------------------------

def test_pre_event_confidence_reduction_imminent():
    upcoming = get_upcoming_events(
        [EventImpact(
            event_type=EventType.BI_RATE_CUT,
            direction=EventDirection.BULLISH,
            scope=EventScope.MARKET_WIDE,
            base_impact=30.0,
            event_date=AS_OF + timedelta(days=2),
            description="BI cut in 2d",
        )],
        AS_OF,
        lookahead_days=14,
    )
    mult = pre_event_confidence_reduction(upcoming)
    # (7 - 2) * 0.02 = 0.10 reduction -> 0.90
    assert mult == pytest.approx(0.90)


def test_pre_event_confidence_reduction_far_event_no_effect():
    upcoming = get_upcoming_events(
        [EventImpact(
            event_type=EventType.ELECTION,
            direction=EventDirection.BEARISH,
            scope=EventScope.MARKET_WIDE,
            base_impact=-20.0,
            event_date=AS_OF + timedelta(days=14),
            description="Election in 14d",
        )],
        AS_OF,
        lookahead_days=14,
    )
    mult = pre_event_confidence_reduction(upcoming)
    assert mult == pytest.approx(1.0)


def test_pre_event_confidence_reduction_clamped_at_0_8():
    # Many imminent events should clamp to 0.8.
    upcoming = [
        type("U", (), {
            "event_type": EventType.BI_RATE_CUT,
            "event_date": AS_OF + timedelta(days=0),
            "days_until": 0,
            "description": "today",
        })(),
        type("U", (), {
            "event_type": EventType.FED_RATE_CUT,
            "event_date": AS_OF + timedelta(days=1),
            "days_until": 1,
            "description": "tomorrow",
        })(),
    ]
    mult = pre_event_confidence_reduction(upcoming)
    assert mult == pytest.approx(0.8)


# --- empty events ----------------------------------------------------------

def test_empty_events_neutral():
    sig = compute_event_signal("BBCA.JK", [], AS_OF)
    assert sig.score == 0
    assert sig.direction == "neutral"
    assert sig.confidence == 0
    assert sig.active_events == []


# --- mixed events ----------------------------------------------------------

def test_mixed_market_wide_and_ticker_specific():
    events = [
        _make(EventType.BI_RATE_CUT, days_offset=2, description="BI cut"),
        EventImpact(
            event_type=EventType.BUYBACK,
            direction=EventDirection.BULLISH,
            scope=EventScope.TICKER_SPECIFIC,
            base_impact=50.0,
            event_date=AS_OF - timedelta(days=1),
            ticker="BBCA.JK",
            description="BBCA buyback",
        ),
        EventImpact(
            event_type=EventType.RIGHTS_ISSUE,
            direction=EventDirection.BEARISH,
            scope=EventScope.TICKER_SPECIFIC,
            base_impact=-45.0,
            event_date=AS_OF - timedelta(days=1),
            ticker="BBRI.JK",
            description="BBRI rights issue",
        ),
    ]
    sig = compute_event_signal("BBCA.JK", events, AS_OF)
    # Both market-wide cut (0.3 weight) and BBCA buyback (1.0 weight) are bullish.
    assert sig.score > 5
    assert sig.direction == "bullish"
    assert sig.market_wide_score > 0
    assert sig.ticker_specific_score > 0
    # BBRI rights issue must not leak into BBCA's score.
    bbri_contributions = [
        e for e in sig.active_events if e.get("ticker") == "BBRI.JK"
    ]
    assert bbri_contributions == []
