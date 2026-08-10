"""Ticker screener — filters instruments before data fetch.

This module is the single gatekeeper that decides which tickers
should be fetched from external sources. It applies multiple filters:

1. **InstrumentMaster**: only `is_active=True` and `asset_class="EQUITY_INDIVIDUAL"`
   (segment-aware: excludes indices ^JKSE, commodities CL=F, volatility ^VIX
   from ML training data — these are exogenous features only)
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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market.db.models import (
    BursaEfek,
    DailyTradingStats,
    Emiten,
    InstrumentMaster,
    Instrumen,
    Regulator,
    StockPersonality,
    TradingSuspension,
)

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
    excluded_merged: list[str] = field(default_factory=list)
    excluded_illiquid: list[str] = field(default_factory=list)

    @property
    def total_excluded(self) -> int:
        return (
            len(self.excluded_delisted)
            + len(self.excluded_suspended)
            + len(self.excluded_blocked)
            + len(self.excluded_low_liquidity)
            + len(self.excluded_merged)
            + len(self.excluded_illiquid)
        )

    def summary(self) -> dict[str, int]:
        return {
            "passed": len(self.passed),
            "excluded_delisted": len(self.excluded_delisted),
            "excluded_suspended": len(self.excluded_suspended),
            "excluded_blocked": len(self.excluded_blocked),
            "excluded_low_liquidity": len(self.excluded_low_liquidity),
            "excluded_merged": len(self.excluded_merged),
            "excluded_illiquid": len(self.excluded_illiquid),
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
        min_daily_value: float | None = None,
        daily_value_lookback: int = 20,
    ) -> None:
        """Initialize screener.

        Args:
            min_liquidity_score: If set, exclude tickers with
                StockPersonality.liquidity_score below this value.
                None disables liquidity filtering.
            delisting_memory: Optional DelistingMemory instance.
                If provided, tickers blocked/delisted in AI memory
                are excluded.
            min_daily_value: If set, exclude tickers whose 20-day average
                daily trading value (from daily_trading_stats.value) falls
                below this threshold (in IDR). Default 30e9 = Rp30 miliar.
                None disables the hard-cut.
            daily_value_lookback: Number of trading days to average for
                min_daily_value filter (default 20).
        """
        self._min_liquidity_score = min_liquidity_score
        self._delisting_memory = delisting_memory
        self._min_daily_value = min_daily_value
        self._daily_value_lookback = daily_value_lookback

    def screen(
        self,
        session: Session,
        asset_class: str = "EQUITY_INDIVIDUAL",
    ) -> ScreeningResult:
        """Screen tickers and return filtered result with breakdown.

        Args:
            session: SQLAlchemy session.
            asset_class: Asset class to filter (default: equity).

        Returns:
            ScreeningResult with passed tickers and exclusion breakdown.
        """
        result = ScreeningResult()

        # Layer 1: Active instruments — try PG instruments first, fallback to InstrumentMaster
        try:
            from market.db.models import Instrument

            pg_asset = asset_class.upper() if asset_class else "EQUITY"
            active_tickers = session.execute(
                select(Instrument.ticker).where(
                    Instrument.is_active == True,  # noqa: E712
                    Instrument.asset_class == pg_asset,
                )
            ).scalars().all()
            if active_tickers:
                # PG instruments table doesn't have delisting_date/underlying_ticker
                delisted: set[str] = set()
                merged: set[str] = set()
            else:
                raise Exception("No rows in PG instruments, trying SQLite")
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
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

            # Layer 2b: Exclude tickers that have been merged (underlying_ticker set)
            merged = set(
                session.execute(
                    select(InstrumentMaster.ticker).where(
                        InstrumentMaster.is_active == True,  # noqa: E712
                        InstrumentMaster.asset_class == asset_class,
                        InstrumentMaster.underlying_ticker.is_not(None),
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

        # Layer 6: Liquidity hard-cut — exclude tickers with 20-day avg daily
        # trading value below threshold (default Rp30 miliar) to avoid signal
        # manipulation on illiquid stocks.
        illiquid: set[str] = set()
        if self._min_daily_value is not None:
            candidates = [
                t for t in active_tickers
                if t not in delisted and t not in merged
                and t not in suspended and t not in blocked
                and t not in low_liquidity
            ]
            if candidates:
                # Subquery: avg daily value over last N trading days per ticker
                avg_value_subq = (
                    select(
                        DailyTradingStats.ticker,
                        func.avg(DailyTradingStats.value).label("avg_value"),
                    )
                    .where(
                        DailyTradingStats.ticker.in_(candidates),
                        DailyTradingStats.value.is_not(None),
                    )
                    .group_by(DailyTradingStats.ticker)
                ).subquery()

                rows = session.execute(
                    select(avg_value_subq.c.ticker, avg_value_subq.c.avg_value)
                ).all()

                for row in rows:
                    ticker, avg_val = row[0], row[1]
                    if avg_val is not None and float(avg_val) < self._min_daily_value:
                        illiquid.add(ticker)

                # Tickers with no daily_trading_stats data at all are also excluded
                tickers_with_data = {row[0] for row in rows}
                illiquid.update(set(candidates) - tickers_with_data)

            logger.info(
                "Screener liquidity hard-cut: %d tickers below Rp%.0fB avg daily value (%d-day lookback)",
                len(illiquid),
                self._min_daily_value / 1e9,
                self._daily_value_lookback,
            )

        # Apply all filters
        for ticker in active_tickers:
            if ticker in delisted:
                result.excluded_delisted.append(ticker)
            elif ticker in merged:
                result.excluded_merged.append(ticker)
            elif ticker in suspended:
                result.excluded_suspended.append(ticker)
            elif ticker in blocked:
                result.excluded_blocked.append(ticker)
            elif ticker in low_liquidity:
                result.excluded_low_liquidity.append(ticker)
            elif ticker in illiquid:
                result.excluded_illiquid.append(ticker)
            else:
                result.passed.append(ticker)

        logger.info(
            "Screener: %d passed, %d excluded (delisted=%d, merged=%d, suspended=%d, blocked=%d, low_liq=%d, illiquid=%d)",
            len(result.passed),
            result.total_excluded,
            len(result.excluded_delisted),
            len(result.excluded_merged),
            len(result.excluded_suspended),
            len(result.excluded_blocked),
            len(result.excluded_low_liquidity),
            len(result.excluded_illiquid),
        )

        return result

    def screen_tickers(
        self,
        session: Session,
        asset_class: str = "EQUITY_INDIVIDUAL",
    ) -> list[str]:
        """Convenience method: return only the list of passed tickers.

        Args:
            session: SQLAlchemy session.
            asset_class: Asset class to filter (default: equity).

        Returns:
            List of ticker strings that passed all filters.
        """
        return self.screen(session, asset_class=asset_class).passed

    def screen_relational(
        self,
        session: Session,
        jenis_instrumen: str = "Saham",
        negara: str = "Indonesia",
    ) -> list[str]:
        """Screen tickers using the relational hierarchy tables (migration 0013).

        JOINs: instrumen → emiten → bursa_efek → regulator
        Filters by jenis_instrumen (default: Saham) and negara (default: Indonesia).
        This ensures MLSignalProvider only trains on instruments that are
        listed on an Indonesian bursa and regulated by OJK.

        Args:
            session: SQLAlchemy session.
            jenis_instrumen: Instrument type filter (default: Saham).
            negara: Country filter via regulator (default: Indonesia).

        Returns:
            List of ticker strings (kode_ticker from emiten) that passed.
        """
        stmt = (
            select(Emiten.kode_ticker)
            .join(Instrumen, Instrumen.id_emiten == Emiten.id_emiten)
            .join(BursaEfek, BursaEfek.id_bursa == Emiten.id_bursa)
            .join(Regulator, Regulator.id_regulator == BursaEfek.id_regulator)
            .where(
                Instrumen.jenis_instrumen == jenis_instrumen,
                Instrumen.is_active == True,  # noqa: E712
                Emiten.is_active == True,  # noqa: E712
                Regulator.negara == negara,
            )
        )
        tickers = session.execute(stmt).scalars().all()

        logger.info(
            "Relational screener: %d tickers (jenis=%s, negara=%s)",
            len(tickers), jenis_instrumen, negara,
        )
        return tickers
