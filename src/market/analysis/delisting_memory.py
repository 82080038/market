"""Delisting & suspension memory for AI/ML risk reminders (pustaka/67, pustaka/69).

Tracks instruments that were delisted, suspended, or blocked from trading,
along with the root causes and warning patterns that preceded the event.

This memory serves as an AI/ML reminder system:
- When evaluating new instruments for portfolio inclusion, the system checks
  if current patterns match historical delisting warning patterns.
- Instruments exhibiting similar pre-delisting behavior are flagged with
  elevated risk, reducing or preventing portfolio inclusion.
- Lessons from delisting events feed into the Self-Evolution Agent's
  persistent memory for autonomous decision-making.

Delisting reasons (IDX/BEI context):
- Financial distress / bankruptcy
- Failure to meet listing requirements (minimum equity, revenue)
- Regulatory violation (OJK/BEI sanctions)
- Merger/acquisition (voluntary delisting)
- Going-private transaction
- Extended suspension (>6 months → automatic delisting)
- Public float below minimum
- Negative equity for consecutive years

Warning patterns tracked:
- Sustained price decline (>50% over 6 months)
- Volume collapse (>80% drop vs historical average)
- Consecutive negative earnings
- Negative equity
- Regulatory inquiry/sanction flags
- Failed corporate governance audits
- Going concern audit opinion
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class DelistingReason(Enum):
    """Reasons for delisting or trading suspension."""

    FINANCIAL_DISTRESS = "financial_distress"
    BANKRUPTCY = "bankruptcy"
    LISTING_REQUIREMENT_FAILURE = "listing_requirement_failure"
    REGULATORY_VIOLATION = "regulatory_violation"
    MERGER_ACQUISITION = "merger_acquisition"
    GOING_PRIVATE = "going_private"
    EXTENDED_SUSPENSION = "extended_suspension"
    INSUFFICIENT_FLOAT = "insufficient_float"
    NEGATIVE_EQUITY = "negative_equity"
    GOING_CONCERN = "going_concern"
    VOLUNTARY_DELISTING = "voluntary_delisting"
    UNKNOWN = "unknown"


class InstrumentStatus(Enum):
    """Current status of an instrument."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    BLOCKED = "blocked"  # Blocked by AI risk system


class WarningPatternType(Enum):
    """Types of warning patterns that precede delisting."""

    SUSTAINED_PRICE_DECLINE = "sustained_price_decline"
    VOLUME_COLLAPSE = "volume_collapse"
    CONSECUTIVE_NEGATIVE_EARNINGS = "consecutive_negative_earnings"
    NEGATIVE_EQUITY = "negative_equity"
    REGULATORY_FLAG = "regulatory_flag"
    GOING_CONCERN_OPINION = "going_concern_opinion"
    GOVERNANCE_FAILURE = "governance_failure"
    LIQUIDITY_DRAIN = "liquidity_drain"
    PRICE_BELOW_PAR = "price_below_par"
    MARKET_CAP_COLLAPSE = "market_cap_collapse"


@dataclass
class WarningPattern:
    """A warning pattern observed before a delisting event."""

    pattern_type: WarningPatternType
    description: str
    severity: float  # 0-1, how severe this warning is
    detected_date: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DelistingRecord:
    """Record of a delisted or blocked instrument."""

    record_id: str
    ticker: str
    exchange: str  # IDX, NYSE, etc.
    status: InstrumentStatus
    reason: DelistingReason
    event_date: str  # When delisting/suspension occurred
    last_price: float = 0.0
    price_decline_pct: float = 0.0  # Total decline before delisting
    warning_patterns: list[WarningPattern] = field(default_factory=list)
    lesson: str = ""  # AI lesson learned from this event
    risk_score: float = 0.0  # 0-1, how risky similar patterns are
    sector: str = ""
    market_cap_at_delisting: float = 0.0
    days_suspended_before_delisting: int = 0
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIReminder:
    """An AI/ML reminder generated for a current instrument."""

    reminder_id: str
    ticker: str
    reminder_type: str  # "delisting_risk", "pattern_match", "sector_warning"
    severity: str  # "info", "warn", "critical"
    message: str
    matched_patterns: list[str] = field(default_factory=list)
    similar_delisted: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    recommendation: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DelistingMemory:
    """Memory of delisted/blocked instruments and their warning patterns.

    Provides AI/ML reminders to avoid similar instruments in portfolio decisions.
    Integrates with the Self-Evolution Agent's persistent memory.
    """

    _counter = 0

    def __init__(self) -> None:
        self._records: dict[str, DelistingRecord] = {}  # ticker → record
        self._reminders: list[AIReminder] = []

    @property
    def records(self) -> list[DelistingRecord]:
        """All delisting records."""
        return list(self._records.values())

    @property
    def reminders(self) -> list[AIReminder]:
        """All AI reminders."""
        return list(self._reminders)

    def record_delisting(
        self,
        ticker: str,
        exchange: str,
        reason: DelistingReason,
        event_date: str,
        last_price: float = 0.0,
        price_decline_pct: float = 0.0,
        warning_patterns: list[WarningPattern] | None = None,
        lesson: str = "",
        sector: str = "",
        market_cap_at_delisting: float = 0.0,
        days_suspended_before_delisting: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> DelistingRecord:
        """Record a delisting or suspension event.

        Args:
            ticker: Instrument ticker.
            exchange: Exchange (IDX, NYSE, etc.).
            reason: Reason for delisting.
            event_date: Date of the event.
            last_price: Last traded price before delisting.
            price_decline_pct: Total price decline percentage before delisting.
            warning_patterns: Warning patterns observed before the event.
            lesson: AI lesson learned from this event.
            sector: Sector classification.
            market_cap_at_delisting: Market cap at time of delisting.
            days_suspended_before_delisting: Days under suspension before delisting.
            metadata: Additional metadata.

        Returns:
            The created DelistingRecord.
        """
        DelistingMemory._counter += 1
        record_id = f"DLM-{DelistingMemory._counter:05d}"

        # Auto-generate lesson if not provided
        if not lesson:
            lesson = self._generate_lesson(ticker, reason, warning_patterns or [])

        # Calculate risk score from warning patterns
        risk_score = self._calculate_risk_score(
            reason, warning_patterns or [], price_decline_pct,
        )

        record = DelistingRecord(
            record_id=record_id,
            ticker=ticker,
            exchange=exchange,
            status=InstrumentStatus.DELISTED,
            reason=reason,
            event_date=event_date,
            last_price=last_price,
            price_decline_pct=price_decline_pct,
            warning_patterns=warning_patterns or [],
            lesson=lesson,
            risk_score=risk_score,
            sector=sector,
            market_cap_at_delisting=market_cap_at_delisting,
            days_suspended_before_delisting=days_suspended_before_delisting,
            metadata=metadata or {},
        )

        self._records[ticker] = record
        return record

    def record_suspension(
        self,
        ticker: str,
        exchange: str,
        reason: DelistingReason,
        event_date: str,
        warning_patterns: list[WarningPattern] | None = None,
        lesson: str = "",
        sector: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DelistingRecord:
        """Record a trading suspension (not yet delisted)."""
        DelistingMemory._counter += 1
        record_id = f"SUS-{DelistingMemory._counter:05d}"

        if not lesson:
            lesson = self._generate_lesson(ticker, reason, warning_patterns or [])

        risk_score = self._calculate_risk_score(reason, warning_patterns or [], 0.0)

        record = DelistingRecord(
            record_id=record_id,
            ticker=ticker,
            exchange=exchange,
            status=InstrumentStatus.SUSPENDED,
            reason=reason,
            event_date=event_date,
            warning_patterns=warning_patterns or [],
            lesson=lesson,
            risk_score=risk_score,
            sector=sector,
            metadata=metadata or {},
        )

        self._records[ticker] = record
        return record

    def block_instrument(
        self,
        ticker: str,
        reason: str,
        risk_score: float = 0.8,
        similar_delisted: list[str] | None = None,
    ) -> DelistingRecord:
        """Block an instrument from portfolio inclusion by AI risk system."""
        DelistingMemory._counter += 1
        record_id = f"BLK-{DelistingMemory._counter:05d}"

        record = DelistingRecord(
            record_id=record_id,
            ticker=ticker,
            exchange="AI",
            status=InstrumentStatus.BLOCKED,
            reason=DelistingReason.UNKNOWN,
            event_date=datetime.now(UTC).isoformat(),
            lesson=f"Instrument blocked by AI: {reason}",
            risk_score=risk_score,
            metadata={"block_reason": reason, "similar_delisted": similar_delisted or []},
        )

        self._records[ticker] = record
        return record

    def get_record(self, ticker: str) -> DelistingRecord | None:
        """Get delisting record for a ticker."""
        return self._records.get(ticker)

    def is_blocked(self, ticker: str) -> bool:
        """Check if an instrument is blocked or delisted."""
        record = self._records.get(ticker)
        if record is None:
            return False
        return record.status in (InstrumentStatus.DELISTED, InstrumentStatus.BLOCKED)

    def is_suspended(self, ticker: str) -> bool:
        """Check if an instrument is suspended."""
        record = self._records.get(ticker)
        if record is None:
            return False
        return record.status == InstrumentStatus.SUSPENDED

    def check_warning_patterns(
        self,
        ticker: str,
        data: pd.DataFrame,
        as_of: str | pd.Timestamp | None = None,
    ) -> list[WarningPattern]:
        """Check current data for warning patterns similar to historical delisting events.

        Args:
            ticker: Instrument ticker.
            data: OHLCV data.
            as_of: Check up to this date (no look-ahead).

        Returns:
            List of detected warning patterns.
        """
        if as_of:
            cutoff = pd.Timestamp(as_of)
            data = data[data.index <= cutoff]

        if len(data) < 60:
            return []

        close = data["close"].astype(float)
        volume = data["volume"].astype(float)
        warnings: list[WarningPattern] = []

        # 1. Sustained price decline (>50% over 6 months ~126 bars)
        if len(close) >= 126:
            price_6m_ago = float(close.iloc[-126])
            current_price = float(close.iloc[-1])
            if price_6m_ago > 0:
                decline_pct = (price_6m_ago - current_price) / price_6m_ago * 100
                if decline_pct > 50:
                    warnings.append(WarningPattern(
                        pattern_type=WarningPatternType.SUSTAINED_PRICE_DECLINE,
                        description=(
                            f"Price declined {decline_pct:.1f}% over 6 months "
                            f"(from {price_6m_ago:.2f} to {current_price:.2f})"
                        ),
                        severity=min(1.0, decline_pct / 100),
                        detected_date=str(data.index[-1]),
                        details={"decline_pct": round(decline_pct, 2), "period_bars": 126},
                    ))

        # 2. Volume collapse (>80% drop vs 60-day average)
        if len(volume) >= 120:
            recent_vol = float(volume.iloc[-30:].mean())
            historical_vol = float(volume.iloc[-120:-30].mean())
            if historical_vol > 0:
                vol_drop = (1 - recent_vol / historical_vol) * 100
                if vol_drop > 80:
                    warnings.append(WarningPattern(
                        pattern_type=WarningPatternType.VOLUME_COLLAPSE,
                        description=(
                            f"Volume collapsed {vol_drop:.1f}% vs historical average "
                            f"(recent: {recent_vol:.0f}, historical: {historical_vol:.0f})"
                        ),
                        severity=min(1.0, vol_drop / 100),
                        detected_date=str(data.index[-1]),
                        details={"vol_drop_pct": round(vol_drop, 2)},
                    ))

        # 3. Liquidity drain (very low absolute volume)
        avg_vol = float(volume.iloc[-20:].mean())
        if avg_vol < 10000:  # Less than 10k shares/day
            warnings.append(WarningPattern(
                pattern_type=WarningPatternType.LIQUIDITY_DRAIN,
                description=(
                    f"Extremely low liquidity: avg volume {avg_vol:.0f} shares/day "
                    f"(last 20 days)"
                ),
                severity=0.7,
                detected_date=str(data.index[-1]),
                details={"avg_volume_20d": round(avg_vol, 0)},
            ))

        # 4. Price below par / penny stock
        current_price = float(close.iloc[-1])
        if current_price < 50:  # IDX minimum price threshold
            warnings.append(WarningPattern(
                pattern_type=WarningPatternType.PRICE_BELOW_PAR,
                description=(
                    f"Price below minimum threshold: {current_price:.2f} "
                    f"(IDX minimum is typically 50 IDR)"
                ),
                severity=0.6,
                detected_date=str(data.index[-1]),
                details={"current_price": current_price},
            ))

        # 5. Market cap collapse (if we can estimate)
        # Using price * volume as proxy
        if len(close) >= 126:
            current_mc_proxy = float(close.iloc[-1]) * float(volume.iloc[-20:].mean())
            past_mc_proxy = (
                float(close.iloc[-126]) * float(volume.iloc[-146:-126].mean())
                if len(volume) >= 146 else 0
            )
            if past_mc_proxy > 0 and current_mc_proxy > 0:
                mc_drop = (1 - current_mc_proxy / past_mc_proxy) * 100
                if mc_drop > 70:
                    warnings.append(WarningPattern(
                        pattern_type=WarningPatternType.MARKET_CAP_COLLAPSE,
                        description=(
                            f"Market cap proxy collapsed {mc_drop:.1f}% "
                            f"(price x volume based estimate)"
                        ),
                        severity=min(1.0, mc_drop / 100),
                        detected_date=str(data.index[-1]),
                        details={"mc_drop_pct": round(mc_drop, 2)},
                    ))

        return warnings

    def generate_reminders(
        self,
        ticker: str,
        data: pd.DataFrame,
        as_of: str | pd.Timestamp | None = None,
    ) -> list[AIReminder]:
        """Generate AI/ML reminders for a current instrument.

        Checks for:
        - Current warning patterns that match historical delisting patterns
        - Similar sector/behavior to delisted instruments
        - Direct status checks (suspended/blocked)

        Args:
            ticker: Instrument ticker.
            data: OHLCV data.
            as_of: Check up to this date.

        Returns:
            List of AIReminder objects.
        """
        reminders: list[AIReminder] = []

        # Check if already blocked/delisted/suspended
        record = self._records.get(ticker)
        if record:
            if record.status == InstrumentStatus.DELISTED:
                reminders.append(AIReminder(
                    reminder_id=f"REM-{DelistingMemory._counter:05d}",
                    ticker=ticker,
                    reminder_type="delisted",
                    severity="critical",
                    message=(
                        f"{ticker} is DELISTED ({record.reason.value}). "
                        f"Do NOT include in portfolio. Lesson: {record.lesson}"
                    ),
                    risk_score=1.0,
                    recommendation="Exclude from portfolio immediately.",
                ))
                return reminders

            if record.status == InstrumentStatus.SUSPENDED:
                reminders.append(AIReminder(
                    reminder_id=f"REM-{DelistingMemory._counter:05d}",
                    ticker=ticker,
                    reminder_type="suspended",
                    severity="critical",
                    message=(
                        f"{ticker} is SUSPENDED ({record.reason.value}). "
                        f"Trading halted. Lesson: {record.lesson}"
                    ),
                    risk_score=0.9,
                    recommendation="Exclude from portfolio until suspension lifted.",
                ))
                return reminders

            if record.status == InstrumentStatus.BLOCKED:
                reminders.append(AIReminder(
                    reminder_id=f"REM-{DelistingMemory._counter:05d}",
                    ticker=ticker,
                    reminder_type="blocked",
                    severity="critical",
                    message=f"{ticker} is BLOCKED by AI risk system: {record.lesson}",
                    risk_score=record.risk_score,
                    recommendation="Exclude from portfolio. Review block reason.",
                ))
                return reminders

        # Check for warning patterns in current data
        current_warnings = self.check_warning_patterns(ticker, data, as_of)

        if current_warnings:
            # Find similar delisted instruments by matching warning patterns
            current_warning_types = {w.pattern_type for w in current_warnings}
            similar_delisted: list[str] = []
            for delisted_ticker, delisted_record in self._records.items():
                if delisted_record.status != InstrumentStatus.DELISTED:
                    continue
                delisted_warning_types = {
                    w.pattern_type for w in delisted_record.warning_patterns
                }
                overlap = current_warning_types & delisted_warning_types
                if overlap:
                    similar_delisted.append(delisted_ticker)

            # Calculate aggregate risk score
            max_severity = max(w.severity for w in current_warnings)
            risk_score = min(1.0, max_severity + (0.1 if similar_delisted else 0.0))

            severity = "critical" if risk_score >= 0.7 else "warn" if risk_score >= 0.4 else "info"

            # Build message
            warning_descs = [f"{w.pattern_type.value}: {w.description}" for w in current_warnings]
            message = (
                f"{ticker} shows {len(current_warnings)} warning pattern(s):\n"
                + "\n".join(f"  • {d}" for d in warning_descs)
            )
            if similar_delisted:
                message += (
                    f"\n\nSimilar patterns found in delisted instruments: "
                    f"{', '.join(similar_delisted[:5])}"
                )

            # Build recommendation
            if risk_score >= 0.7:
                recommendation = (
                    "DO NOT include in portfolio. High risk of delisting/suspension. "
                    "If already held, consider immediate exit."
                )
            elif risk_score >= 0.4:
                recommendation = (
                    "Caution: elevated risk. Reduce position size. "
                    "Set tight stop-loss. Monitor closely for further deterioration."
                )
            else:
                recommendation = (
                    "Monitor: minor warning signs detected. "
                    "Include in watchlist with risk flags."
                )

            DelistingMemory._counter += 1
            reminders.append(AIReminder(
                reminder_id=f"REM-{DelistingMemory._counter:05d}",
                ticker=ticker,
                reminder_type="pattern_match",
                severity=severity,
                message=message,
                matched_patterns=[w.pattern_type.value for w in current_warnings],
                similar_delisted=similar_delisted[:10],
                risk_score=round(risk_score, 3),
                recommendation=recommendation,
            ))

        # Check sector-based warnings
        if record is None and current_warnings:
            # Find delisted instruments in same sector (if we can infer)
            # This is a simplified check — in production, use sector metadata
            for delisted_ticker, delisted_record in self._records.items():
                if delisted_record.status == InstrumentStatus.DELISTED and delisted_record.sector:
                    # Check if similar warning patterns
                    delisted_patterns = {w.pattern_type for w in delisted_record.warning_patterns}
                    if current_warning_types & delisted_patterns:
                        DelistingMemory._counter += 1
                        reminders.append(AIReminder(
                            reminder_id=f"REM-{DelistingMemory._counter:05d}",
                            ticker=ticker,
                            reminder_type="sector_warning",
                            severity="warn",
                            message=(
                                f"Sector warning: {ticker} shows patterns similar to "
                                f"delisted {delisted_ticker} (sector: {delisted_record.sector}). "
                                f"Lesson from {delisted_ticker}: {delisted_record.lesson}"
                            ),
                            matched_patterns=[
                                p.value for p in (current_warning_types & delisted_patterns)
                            ],
                            similar_delisted=[delisted_ticker],
                            risk_score=delisted_record.risk_score * 0.7,
                            recommendation=(
                                f"Review {ticker} carefully. Historical lesson from "
                                f"{delisted_ticker}: {delisted_record.lesson}"
                            ),
                        ))
                        break  # One sector warning is enough

        self._reminders.extend(reminders)
        return reminders

    def get_portfolio_risk_filter(
        self,
        tickers: list[str],
    ) -> dict[str, Any]:
        """Filter a list of tickers for portfolio inclusion.

        Args:
            tickers: Candidate tickers for portfolio.

        Returns:
            Dict with approved, blocked, and warning lists.
        """
        approved: list[str] = []
        blocked: list[str] = []
        warnings: dict[str, str] = {}

        for ticker in tickers:
            record = self._records.get(ticker)
            if record and record.status in (
                InstrumentStatus.DELISTED,
                InstrumentStatus.BLOCKED,
            ):
                blocked.append(ticker)
                warnings[ticker] = (
                    f"{record.status.value}: {record.lesson}"
                )
            elif record and record.status == InstrumentStatus.SUSPENDED:
                blocked.append(ticker)
                warnings[ticker] = f"suspended: {record.lesson}"
            else:
                approved.append(ticker)

        return {
            "approved": approved,
            "blocked": blocked,
            "warnings": warnings,
            "total": len(tickers),
            "approved_count": len(approved),
            "blocked_count": len(blocked),
        }

    def get_lessons(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get all lessons from delisting events for AI self-evolution.

        Args:
            limit: Maximum number of lessons.

        Returns:
            List of lesson dicts with ticker, reason, lesson, risk_score.
        """
        lessons: list[dict[str, Any]] = []
        for record in self._records.values():
            lessons.append({
                "ticker": record.ticker,
                "reason": record.reason.value,
                "status": record.status.value,
                "lesson": record.lesson,
                "risk_score": record.risk_score,
                "warning_patterns": [w.pattern_type.value for w in record.warning_patterns],
                "event_date": record.event_date,
                "sector": record.sector,
            })
        lessons.sort(key=lambda x: x["risk_score"], reverse=True)
        return lessons[:limit]

    def sync_to_persistent_memory(self, persistent_memory: Any) -> int:
        """Sync delisting lessons into the autonomous layer's PersistentMemory.

        This makes delisting lessons available to the Self-Evolution Agent
        for autonomous decision-making and policy evolution.

        Args:
            persistent_memory: PersistentMemory instance from market.autonomous.memory.

        Returns:
            Number of lessons synced.
        """
        # Import here to avoid circular dependency
        from market.autonomous.memory import MemoryType

        count = 0
        for record in self._records.values():
            # Check if already synced (search by tag)
            existing = persistent_memory.search(
                memory_type=MemoryType.SEMANTIC,
                tags=["delisting_lesson", record.ticker],
                limit=1,
            )
            if existing:
                continue

            persistent_memory.store(
                memory_type=MemoryType.SEMANTIC,
                content=(
                    f"Delisting lesson for {record.ticker} ({record.exchange}): "
                    f"reason={record.reason.value}, status={record.status.value}, "
                    f"risk_score={record.risk_score}. "
                    f"Lesson: {record.lesson}"
                ),
                metadata={
                    "ticker": record.ticker,
                    "reason": record.reason.value,
                    "status": record.status.value,
                    "risk_score": record.risk_score,
                    "event_date": record.event_date,
                    "sector": record.sector,
                    "warning_patterns": [w.pattern_type.value for w in record.warning_patterns],
                },
                tags=["delisting_lesson", record.ticker, record.reason.value],
                relevance_score=record.risk_score,
            )
            count += 1

        return count

    def summary(self) -> dict[str, Any]:
        """Get delisting memory summary."""
        by_status: dict[str, int] = {}
        by_reason: dict[str, int] = {}
        for record in self._records.values():
            by_status[record.status.value] = by_status.get(record.status.value, 0) + 1
            by_reason[record.reason.value] = by_reason.get(record.reason.value, 0) + 1

        return {
            "total_records": len(self._records),
            "by_status": by_status,
            "by_reason": by_reason,
            "total_reminders": len(self._reminders),
            "critical_reminders": sum(
                1 for r in self._reminders if r.severity == "critical"
            ),
        }

    def _generate_lesson(
        self,
        ticker: str,
        reason: DelistingReason,
        warning_patterns: list[WarningPattern],
    ) -> str:
        """Auto-generate an AI lesson from a delisting event."""
        pattern_names = [w.pattern_type.value for w in warning_patterns]

        lessons = {
            DelistingReason.FINANCIAL_DISTRESS: (
                f"{ticker} delisted due to financial distress. "
                f"Warning patterns: {pattern_names}. "
                f"Lesson: Monitor for sustained price decline >50% and volume collapse. "
                f"Instruments showing these patterns should be excluded from portfolio."
            ),
            DelistingReason.BANKRUPTCY: (
                f"{ticker} delisted due to bankruptcy. "
                f"Lesson: Negative equity and going concern opinions are critical signals. "
                f"Always check financial health before inclusion."
            ),
            DelistingReason.LISTING_REQUIREMENT_FAILURE: (
                f"{ticker} delisted for failing listing requirements. "
                f"Lesson: Track minimum equity, revenue, and float requirements. "
                f"Instruments near minimum thresholds carry elevated risk."
            ),
            DelistingReason.REGULATORY_VIOLATION: (
                f"{ticker} delisted due to regulatory violation. "
                f"Lesson: Monitor OJK/BEI sanction announcements. "
                f"Regulatory flags should immediately block portfolio inclusion."
            ),
            DelistingReason.EXTENDED_SUSPENSION: (
                f"{ticker} delisted after extended suspension ({warning_patterns}). "
                f"Lesson: Suspensions >6 months often lead to delisting. "
                f"Exit positions at first sign of extended suspension."
            ),
            DelistingReason.NEGATIVE_EQUITY: (
                f"{ticker} delisted due to negative equity. "
                f"Lesson: Check equity ratio quarterly. "
                f"Negative equity for 2+ consecutive periods = critical risk."
            ),
            DelistingReason.GOING_CONCERN: (
                f"{ticker} delisted after going concern audit opinion. "
                f"Lesson: Going concern opinions are strong sell signals. "
                f"Never include instruments with going concern flags in portfolio."
            ),
            DelistingReason.INSUFFICIENT_FLOAT: (
                f"{ticker} delisted due to insufficient public float. "
                f"Lesson: Monitor free float percentage. "
                f"Low float instruments have liquidity risk and manipulation potential."
            ),
        }

        return lessons.get(
            reason,
            f"{ticker} delisted ({reason.value}). Warning patterns: {pattern_names}. "
            f"Lesson: Avoid instruments with similar patterns in the future.",
        )

    def _calculate_risk_score(
        self,
        reason: DelistingReason,
        warning_patterns: list[WarningPattern],
        price_decline_pct: float,
    ) -> float:
        """Calculate risk score from delisting reason and warning patterns."""
        base_scores = {
            DelistingReason.BANKRUPTCY: 1.0,
            DelistingReason.FINANCIAL_DISTRESS: 0.9,
            DelistingReason.GOING_CONCERN: 0.9,
            DelistingReason.NEGATIVE_EQUITY: 0.85,
            DelistingReason.REGULATORY_VIOLATION: 0.85,
            DelistingReason.EXTENDED_SUSPENSION: 0.8,
            DelistingReason.LISTING_REQUIREMENT_FAILURE: 0.7,
            DelistingReason.INSUFFICIENT_FLOAT: 0.6,
            DelistingReason.MERGER_ACQUISITION: 0.3,  # Not a risk signal
            DelistingReason.GOING_PRIVATE: 0.3,
            DelistingReason.VOLUNTARY_DELISTING: 0.2,
            DelistingReason.UNKNOWN: 0.5,
        }

        score = base_scores.get(reason, 0.5)

        # Adjust for warning pattern severity
        if warning_patterns:
            avg_severity = float(np.mean([w.severity for w in warning_patterns]))
            score = min(1.0, (score + avg_severity) / 2)

        # Adjust for price decline
        if price_decline_pct > 80:
            score = min(1.0, score + 0.1)

        return round(score, 3)
