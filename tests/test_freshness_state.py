"""Tests for seven-state stale data detection (Gap #9)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market.data.freshness_state import (
    FreshnessAssessment,
    FreshnessState,
    FreshnessStateMachine,
)


@pytest.fixture
def fsm() -> FreshnessStateMachine:
    return FreshnessStateMachine()


@pytest.fixture
def now() -> datetime:
    # Use a Wednesday during IDX market hours (10:00 WIB = 03:00 UTC)
    return datetime(2026, 8, 19, 3, 0, 0, tzinfo=UTC)  # Wed 10:00 WIB


def test_seven_states_defined():
    """All seven states are defined."""
    states = {s.value for s in FreshnessState}
    assert states == {
        "LIVE", "DEGRADED", "STALE", "FALLBACK",
        "RECOVERING", "DEAD", "MARKET_CLOSED",
    }


def test_live_state(fsm, now):
    """Data < 24h old is LIVE."""
    last = now - timedelta(hours=12)
    result = fsm.assess("yfinance", "BBCA.JK", last, now=now)
    assert result.state == FreshnessState.LIVE
    assert result.age_hours is not None
    assert result.age_hours < 24
    assert result.is_usable
    assert not result.is_actionable


def test_degraded_state(fsm, now):
    """Data 24-72h old is DEGRADED."""
    last = now - timedelta(hours=48)
    result = fsm.assess("yfinance", "BBCA.JK", last, now=now)
    assert result.state == FreshnessState.DEGRADED
    assert result.is_usable


def test_stale_state(fsm, now):
    """Data 72-168h old is STALE."""
    last = now - timedelta(hours=100)
    result = fsm.assess("yfinance", "BBCA.JK", last, now=now)
    assert result.state == FreshnessState.STALE
    assert result.is_actionable
    assert not result.is_usable


def test_dead_state_no_data(fsm, now):
    """No last_update means DEAD."""
    result = fsm.assess("yfinance", "BBCA.JK", None, now=now)
    assert result.state == FreshnessState.DEAD
    assert result.is_actionable


def test_dead_state_very_old(fsm, now):
    """Data > 30 days old with unavailable source is DEAD."""
    last = now - timedelta(days=45)
    result = fsm.assess("yfinance", "BBCA.JK", last, source_available=False, now=now)
    assert result.state == FreshnessState.DEAD


def test_fallback_state(fsm, now):
    """Using fallback data returns FALLBACK."""
    last = now - timedelta(hours=48)
    result = fsm.assess("yfinance", "BBCA.JK", last, using_fallback=True, now=now)
    assert result.state == FreshnessState.FALLBACK
    assert result.using_fallback


def test_recovering_state(fsm, now):
    """Recovery in progress returns RECOVERING."""
    last = now - timedelta(hours=48)
    result = fsm.assess("yfinance", "BBCA.JK", last, recovering=True, now=now)
    assert result.state == FreshnessState.RECOVERING
    assert result.recovering
    assert result.is_actionable


def test_market_closed_state(fsm):
    """Market closed with recent data returns MARKET_CLOSED."""
    # Saturday in UTC (Saturday in WIB too)
    sat = datetime(2026, 8, 22, 5, 0, 0, tzinfo=UTC)  # Sat 12:00 WIB
    last = sat - timedelta(hours=12)
    result = fsm.assess("yfinance", "BBCA.JK", last, now=sat)
    assert result.state == FreshnessState.MARKET_CLOSED
    assert result.market_closed
    assert result.is_usable


def test_market_closed_explicit(fsm, now):
    """Explicit market_closed=True with recent data returns MARKET_CLOSED."""
    last = now - timedelta(hours=12)
    result = fsm.assess("yfinance", "BBCA.JK", last, market_closed=True, now=now)
    assert result.state == FreshnessState.MARKET_CLOSED


def test_market_closed_overrides_stale(fsm, now):
    """Market closed with moderately stale data still returns MARKET_CLOSED."""
    last = now - timedelta(hours=48)
    result = fsm.assess("yfinance", "BBCA.JK", last, market_closed=True, now=now)
    # 48h with market_closed=True should be MARKET_CLOSED (within 72h window)
    assert result.state == FreshnessState.MARKET_CLOSED


def test_market_closed_does_not_override_very_stale(fsm, now):
    """Very stale data (>72h) with market_closed=True returns STALE."""
    last = now - timedelta(hours=100)
    result = fsm.assess("yfinance", "BBCA.JK", last, market_closed=True, now=now)
    assert result.state == FreshnessState.STALE


def test_source_unavailable_with_recent_data(fsm, now):
    """Source unavailable but recent data is not DEAD (could be FALLBACK)."""
    last = now - timedelta(hours=12)
    result = fsm.assess("yfinance", "BBCA.JK", last, source_available=False, now=now)
    # Recent data exists, source just temporarily down — should not be DEAD
    assert result.state != FreshnessState.DEAD


def test_assess_batch(fsm, now):
    """assess_batch processes multiple items."""
    items = [
        {"source": "yfinance", "ticker": "A.JK", "last_update": now - timedelta(hours=12)},
        {"source": "yfinance", "ticker": "B.JK", "last_update": now - timedelta(hours=100)},
        {"source": "yfinance", "ticker": "C.JK", "last_update": None},
    ]
    results = fsm.assess_batch(items, now=now)
    assert len(results) == 3
    assert results[0].state == FreshnessState.LIVE
    assert results[1].state == FreshnessState.STALE
    assert results[2].state == FreshnessState.DEAD


def test_state_summary(fsm, now):
    """get_state_summary counts each state."""
    items = [
        {"source": "s", "ticker": "A", "last_update": now - timedelta(hours=12)},
        {"source": "s", "ticker": "B", "last_update": now - timedelta(hours=12)},
        {"source": "s", "ticker": "C", "last_update": now - timedelta(hours=100)},
    ]
    results = fsm.assess_batch(items, now=now)
    summary = fsm.get_state_summary(results)
    assert summary["LIVE"] == 2
    assert summary["STALE"] == 1


def test_is_market_closed_weekend(fsm):
    """Saturday is market closed."""
    sat = datetime(2026, 8, 22, 5, 0, 0, tzinfo=UTC)  # Sat 12:00 WIB
    assert fsm._is_market_closed(sat) is True


def test_is_market_closed_sunday(fsm):
    """Sunday is market closed."""
    sun = datetime(2026, 8, 23, 5, 0, 0, tzinfo=UTC)  # Sun 12:00 WIB
    assert fsm._is_market_closed(sun) is True


def test_is_market_closed_after_hours(fsm):
    """After 15:00 WIB is market closed."""
    # 09:00 UTC = 16:00 WIB (after close)
    after = datetime(2026, 8, 19, 9, 0, 0, tzinfo=UTC)  # Wed 16:00 WIB
    assert fsm._is_market_closed(after) is True


def test_is_market_closed_before_open(fsm):
    """Before 09:00 WIB is market closed."""
    # 01:00 UTC = 08:00 WIB (before open)
    before = datetime(2026, 8, 19, 1, 0, 0, tzinfo=UTC)  # Wed 08:00 WIB
    assert fsm._is_market_closed(before) is True


def test_is_market_open_during_hours(fsm):
    """During market hours is not closed."""
    # 03:00 UTC = 10:00 WIB (during trading)
    during = datetime(2026, 8, 19, 3, 0, 0, tzinfo=UTC)  # Wed 10:00 WIB
    assert fsm._is_market_closed(during) is False


def test_naive_datetime_treated_as_utc(fsm, now):
    """Naive datetime is treated as UTC."""
    last_naive = datetime(2026, 8, 19, 0, 0, 0)  # No tzinfo
    result = fsm.assess("yfinance", "BBCA.JK", last_naive, now=now)
    # Should not crash and should produce a valid state
    assert result.state in FreshnessState


def test_assessment_properties():
    """FreshnessAssessment properties work correctly."""
    a = FreshnessAssessment(
        source="test", ticker="X",
        state=FreshnessState.LIVE,
        last_update=None, age_hours=10,
        market_closed=False, using_fallback=False, recovering=False,
        message="test",
    )
    assert a.is_usable
    assert not a.is_actionable

    b = FreshnessAssessment(
        source="test", ticker="X",
        state=FreshnessState.STALE,
        last_update=None, age_hours=100,
        market_closed=False, using_fallback=False, recovering=False,
        message="test",
    )
    assert b.is_actionable
    assert not b.is_usable
