"""Seven-state stale data detection (Gap #9).

States:
    LIVE           — Data is fresh and up-to-date
    DEGRADED       — Data is slightly stale but usable
    STALE          — Data is stale, needs refresh
    FALLBACK       — Using fallback/cached data because primary source failed
    RECOVERING     — Source was down, now attempting to recover
    DEAD           — Source is unreachable, no data available
    MARKET_CLOSED  — Market is closed (weekend/holiday), staleness expected

This module provides a state machine that transitions between these states
based on data age, source health, and market hours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from enum import Enum


class FreshnessState(str, Enum):
    """Seven-state data freshness model (Gap #9)."""

    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FALLBACK = "FALLBACK"
    RECOVERING = "RECOVERING"
    DEAD = "DEAD"
    MARKET_CLOSED = "MARKET_CLOSED"


# Thresholds (in hours)
LIVE_MAX_AGE_HOURS = 24           # < 24h = LIVE
DEGRADED_MAX_AGE_HOURS = 72       # 24-72h = DEGRADED
STALE_MAX_AGE_HOURS = 168         # 72-168h (7 days) = STALE
DEAD_THRESHOLD_HOURS = 720        # > 30 days = DEAD

# IDX market hours (WIB = UTC+7)
IDX_MARKET_OPEN = time(9, 0)   # 09:00 WIB
IDX_MARKET_CLOSE = time(15, 0)  # 15:00 WIB
WIB_OFFSET = timedelta(hours=7)


@dataclass
class FreshnessAssessment:
    """Result of a freshness assessment for a data source."""

    source: str
    ticker: str
    state: FreshnessState
    last_update: datetime | None
    age_hours: float | None
    market_closed: bool
    using_fallback: bool
    recovering: bool
    message: str
    assessed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_actionable(self) -> bool:
        """True if state requires action (STALE, DEAD, RECOVERING)."""
        return self.state in (
            FreshnessState.STALE,
            FreshnessState.DEAD,
            FreshnessState.RECOVERING,
        )

    @property
    def is_usable(self) -> bool:
        """True if data can be used for analysis (LIVE, DEGRADED, MARKET_CLOSED)."""
        return self.state in (
            FreshnessState.LIVE,
            FreshnessState.DEGRADED,
            FreshnessState.MARKET_CLOSED,
        )


class FreshnessStateMachine:
    """Seven-state freshness state machine (Gap #9).

    Transitions:
        LIVE → DEGRADED (age > 24h)
        DEGRADED → STALE (age > 72h)
        STALE → DEAD (age > 30 days)
        Any → FALLBACK (source failed, using cache)
        Any → RECOVERING (source was down, attempting recovery)
        Any → MARKET_CLOSED (market is closed)
        FALLBACK → LIVE (source recovered, data fresh)
        RECOVERING → LIVE (recovery successful)
        RECOVERING → DEAD (recovery failed)
    """

    def __init__(
        self,
        live_max_age_hours: float = LIVE_MAX_AGE_HOURS,
        degraded_max_age_hours: float = DEGRADED_MAX_AGE_HOURS,
        stale_max_age_hours: float = STALE_MAX_AGE_HOURS,
        dead_threshold_hours: float = DEAD_THRESHOLD_HOURS,
    ) -> None:
        self.live_max_age = live_max_age_hours
        self.degraded_max_age = degraded_max_age_hours
        self.stale_max_age = stale_max_age_hours
        self.dead_threshold = dead_threshold_hours

    def assess(
        self,
        source: str,
        ticker: str,
        last_update: datetime | None,
        source_available: bool = True,
        using_fallback: bool = False,
        recovering: bool = False,
        market_closed: bool | None = None,
        now: datetime | None = None,
    ) -> FreshnessAssessment:
        """Assess freshness state for a data source.

        Args:
            source: Data source name (e.g. "yfinance", "idx_feed").
            ticker: Stock ticker.
            last_update: Last successful data update timestamp (UTC).
            source_available: Whether the primary source is reachable.
            using_fallback: Whether fallback/cached data is being used.
            recovering: Whether recovery is in progress.
            market_closed: Whether market is closed. Auto-detected if None.
            now: Current timestamp (defaults to UTC now).

        Returns:
            FreshnessAssessment with computed state.
        """
        now = now or datetime.now(UTC)
        if last_update and last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=UTC)

        # Auto-detect market closed if not specified
        if market_closed is None:
            market_closed = self._is_market_closed(now)

        # Compute age
        age_hours: float | None = None
        if last_update is not None:
            age_hours = (now - last_update).total_seconds() / 3600

        # Determine state based on priority
        # 1. DEAD — source unavailable AND no recent data
        if not source_available and (age_hours is None or age_hours > self.dead_threshold):
            return FreshnessAssessment(
                source=source, ticker=ticker,
                state=FreshnessState.DEAD,
                last_update=last_update, age_hours=age_hours,
                market_closed=market_closed,
                using_fallback=False, recovering=False,
                message=f"Source '{source}' unreachable, no data for {age_hours or '∞':.0f}h.",
            )

        # 2. RECOVERING — recovery in progress
        if recovering:
            return FreshnessAssessment(
                source=source, ticker=ticker,
                state=FreshnessState.RECOVERING,
                last_update=last_update, age_hours=age_hours,
                market_closed=market_closed,
                using_fallback=False, recovering=True,
                message=f"Recovering from source '{source}' failure.",
            )

        # 3. FALLBACK — using cached/fallback data
        if using_fallback:
            return FreshnessAssessment(
                source=source, ticker=ticker,
                state=FreshnessState.FALLBACK,
                last_update=last_update, age_hours=age_hours,
                market_closed=market_closed,
                using_fallback=True, recovering=False,
                message=f"Using fallback data (age: {age_hours or '∞':.0f}h).",
            )

        # 4. No data at all
        if last_update is None:
            return FreshnessAssessment(
                source=source, ticker=ticker,
                state=FreshnessState.DEAD,
                last_update=None, age_hours=None,
                market_closed=market_closed,
                using_fallback=False, recovering=False,
                message="No data available — never updated.",
            )

        # 5. Market closed — staleness expected
        if market_closed and age_hours is not None and age_hours < 72:
            return FreshnessAssessment(
                source=source, ticker=ticker,
                state=FreshnessState.MARKET_CLOSED,
                last_update=last_update, age_hours=age_hours,
                market_closed=True, using_fallback=False, recovering=False,
                message=f"Market closed. Last update {age_hours:.1f}h ago.",
            )

        # 6. Age-based states
        if age_hours < self.live_max_age:
            state = FreshnessState.LIVE
            msg = f"Data is live ({age_hours:.1f}h old)."
        elif age_hours < self.degraded_max_age:
            state = FreshnessState.DEGRADED
            msg = f"Data degraded ({age_hours:.1f}h old)."
        elif age_hours < self.stale_max_age:
            state = FreshnessState.STALE
            msg = f"Data is stale ({age_hours:.1f}h old). Refresh needed."
        elif age_hours < self.dead_threshold:
            state = FreshnessState.STALE
            msg = f"Data very stale ({age_hours:.1f}h old). Urgent refresh needed."
        else:
            state = FreshnessState.DEAD
            msg = f"Data is dead ({age_hours:.1f}h old). Source may be abandoned."

        return FreshnessAssessment(
            source=source, ticker=ticker,
            state=state,
            last_update=last_update, age_hours=age_hours,
            market_closed=market_closed,
            using_fallback=False, recovering=False,
            message=msg,
        )

    @staticmethod
    def _is_market_closed(now: datetime) -> bool:
        """Check if IDX market is currently closed.

        IDX trading hours: Mon-Fri 09:00-15:00 WIB (UTC+7).
        Weekend (Sat-Sun) = closed.
        """
        wib_time = now + WIB_OFFSET
        # Weekend check (Python weekday: Monday=0, Sunday=6)
        if wib_time.weekday() >= 5:  # Saturday or Sunday
            return True
        # After hours check
        current_time = wib_time.time()
        if current_time < IDX_MARKET_OPEN or current_time >= IDX_MARKET_CLOSE:
            return True
        return False

    def assess_batch(
        self,
        items: list[dict],
        now: datetime | None = None,
    ) -> list[FreshnessAssessment]:
        """Assess freshness for multiple data sources.

        Args:
            items: List of dicts with keys: source, ticker, last_update,
                source_available, using_fallback, recovering, market_closed.
            now: Current timestamp.

        Returns:
            List of FreshnessAssessment.
        """
        return [
            self.assess(
                source=item.get("source", "unknown"),
                ticker=item.get("ticker", ""),
                last_update=item.get("last_update"),
                source_available=item.get("source_available", True),
                using_fallback=item.get("using_fallback", False),
                recovering=item.get("recovering", False),
                market_closed=item.get("market_closed"),
                now=now,
            )
            for item in items
        ]

    def get_state_summary(
        self, assessments: list[FreshnessAssessment],
    ) -> dict[str, int]:
        """Get count of each state from a list of assessments.

        Returns:
            Dict mapping state name to count.
        """
        summary: dict[str, int] = {s.value: 0 for s in FreshnessState}
        for a in assessments:
            summary[a.state.value] = summary.get(a.state.value, 0) + 1
        return summary
