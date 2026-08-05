"""Ticker screener — filters instruments before data fetch.

This module is the single gatekeeper that decides which tickers
should be fetched from external sources. It applies multiple filters:

1. **InstrumentMaster**: only `is_active=True` and `asset_class="equity"`
2. **Delisting date**: excludes tickers with `delisting_date` set
3. **TradingSuspension**: excludes currently suspended tickers (no `resume_date`)
4. **DelistingMemory**: excludes tickers blocked/delisted by AI memory
5. **Liquidity**: optionally excludes tickers below a liquidity score threshold

DataFetchPipeline calls this screener instead of querying InstrumentMaster
directly. This ensures fetch only spends time on tickers that are
tradeable and relevant.

Usage:
    from market.data.screener import TickerScreener
    screener = TickerScreener()
    tickers = screener.screen(session)
    # → ["BBCA.JK", "BBRI.JK", ...]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from market.db.models import InstrumentMaster, StockPersonality, TradingSuspension

logger = logging.getLogger(__name__)


class _DelistingMemoryLike(Protocol):
    """Protocol for DelistingMemory-like objects used by screener."""

    def is_blocked(self, ticker: str) -> bool: ...
    def is_suspended(self, ticker: str) -> bool: ...


@dataclass
class ScreeningResult:
    """Result of ticker screening with breakdown of exclusions."""

    passed: list[str] = field(default_factory=list)
    excluded_delisted: list[str] = field(default_factory=list)
    excluded_suspended: list[str] = field(default_factory=list)
    excluded_blocked: list[str] = field(default_factory=list)
    excluded_low_liquidity: list[str] = field(default_factory=list)

    @property
    def total_excluded(self) -> int:
        return (
            len(self.excluded_delisted)
            + len(self.excluded_suspended)
            + len(self.excluded_blocked)
            + len(self.excluded_low_liquidity)
        )

    def summary(self) -> dict[str, int]:
        return {
            "passed": len(self.passed),
            "excluded_delisted": len(self.excluded_delisted),
            "excluded_suspended": len(self.excluded_suspended),
            "excluded_blocked": len(self.excluded_blocked),
            "excluded_low_liquidity": len(self.excluded_low_liquidity),
            "total_excluded": self.total_excluded,
        }


class TickerScreener:
    """Screens tickers for fetch eligibility.

    Applies layered filters to InstrumentMaster to produce a clean
    list of tickers that should be fetched from external sources.
    """

    def __init__(
        self,
        min_liquidity_score: float | None = None,
        delisting_memory: _DelistingMemoryLike | None = None,
    ) -> None:
        """Initialize screener.

        Args:
            min_liquidity_score: If set, exclude tickers with
                StockPersonality.liquidity_score below this value.
                None disables liquidity filtering.
            delisting_memory: Optional DelistingMemory instance.
                If provided, tickers blocked/delisted in AI memory
                are excluded.
        """
        self._min_liquidity_score = min_liquidity_score
        self._delisting_memory = delisting_memory

    def screen(
        self,
        session: Session,
        asset_class: str = "equity",
    ) -> ScreeningResult:
        """Screen tickers and return filtered result with breakdown.

        Args:
            session: SQLAlchemy session.
            asset_class: Asset class to filter (default: equity).

        Returns:
            ScreeningResult with passed tickers and exclusion breakdown.
        """
        result = ScreeningResult()

        # Layer 1: Active instruments from InstrumentMaster
        active_tickers = session.execute(
            select(InstrumentMaster.ticker).where(
                InstrumentMaster.is_active == True,  # noqa: E712
                InstrumentMaster.asset_class == asset_class,
            )
        ).scalars().all()

        if not active_tickers:
            logger.info("Screener: 0 active %s tickers in InstrumentMaster", asset_class)
            return result

        # Layer 2: Exclude tickers with delisting_date set
        delisted = set(
            session.execute(
                select(InstrumentMaster.ticker).where(
                    InstrumentMaster.is_active == True,  # noqa: E712
                    InstrumentMaster.asset_class == asset_class,
                    InstrumentMaster.delisting_date.is_not(None),
                )
            ).scalars().all()
        )

        # Layer 3: Exclude currently suspended tickers (no resume_date)
        suspended_rows = session.execute(
            select(TradingSuspension.ticker, TradingSuspension.resume_date).where(
                TradingSuspension.ticker.in_(active_tickers),
            )
        ).all()
        suspended = {
            row[0] for row in suspended_rows if row[1] is None
        }

        # Layer 4: Exclude tickers blocked by DelistingMemory
        blocked: set[str] = set()
        if self._delisting_memory is not None:
            for ticker in active_tickers:
                if (
                    self._delisting_memory.is_blocked(ticker)
                    or self._delisting_memory.is_suspended(ticker)
                ):
                    blocked.add(ticker)

        # Layer 5: Optional liquidity filter
        low_liquidity: set[str] = set()
        if self._min_liquidity_score is not None:
            personality_rows = session.execute(
                select(
                    StockPersonality.ticker,
                    StockPersonality.liquidity_score,
                ).where(
                    StockPersonality.ticker.in_(active_tickers),
                )
            ).all()
            for row in personality_rows:
                ticker, liq = row[0], row[1]
                if liq is not None and float(liq) < self._min_liquidity_score:
                    low_liquidity.add(ticker)

        # Apply all filters
        for ticker in active_tickers:
            if ticker in delisted:
                result.excluded_delisted.append(ticker)
            elif ticker in suspended:
                result.excluded_suspended.append(ticker)
            elif ticker in blocked:
                result.excluded_blocked.append(ticker)
            elif ticker in low_liquidity:
                result.excluded_low_liquidity.append(ticker)
            else:
                result.passed.append(ticker)

        logger.info(
            "Screener: %d passed, %d excluded (delisted=%d, suspended=%d, blocked=%d, low_liq=%d)",
            len(result.passed),
            result.total_excluded,
            len(result.excluded_delisted),
            len(result.excluded_suspended),
            len(result.excluded_blocked),
            len(result.excluded_low_liquidity),
        )

        return result

    def screen_tickers(
        self,
        session: Session,
        asset_class: str = "equity",
    ) -> list[str]:
        """Convenience method: return only the list of passed tickers.

        Args:
            session: SQLAlchemy session.
            asset_class: Asset class to filter (default: equity).

        Returns:
            List of ticker strings that passed all filters.
        """
        return self.screen(session, asset_class=asset_class).passed
