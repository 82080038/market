"""Foreign flow fetcher — fetches foreign investor flow data from idx.co.id.

Uses IDXOfficialAdapter.fetch_foreign_flow_for_date() which calls the
GetStockSummary endpoint. This endpoint returns ForeignBuy/ForeignSell
per stock per day, which we persist to the foreign_flow table.

Integration:
    - Triggered by scheduler or on-demand
    - Uses FetchRegistry to determine which dates need fetching
    - Stores to foreign_flow table with ON CONFLICT DO UPDATE
    - Registered in engine_registry as a fetcher

Usage:
    from market.data.foreign_flow_fetcher import ForeignFlowFetcher
    fetcher = ForeignFlowFetcher()
    count = fetcher.fetch_and_store(days_back=14)
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from market.data.idx_adapter import IDXOfficialAdapter
from market.db.engine import get_sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ForeignFlowFetcher:
    """Fetch foreign flow data from idx.co.id and persist to database.

    Args:
        adapter: IDXOfficialAdapter instance (created if None).
        session: SQLAlchemy session (created if None).
    """

    def __init__(
        self,
        adapter: IDXOfficialAdapter | None = None,
        session: Session | None = None,
    ) -> None:
        self._adapter = adapter or IDXOfficialAdapter()
        self._session = session
        self._owns_session = session is None

    def _get_session(self) -> Session:
        if self._session is None:
            self._session = get_sessionmaker()()
            self._owns_session = True
        return self._session

    def _close_session(self) -> None:
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    def fetch_and_store(
        self,
        days_back: int = 14,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, int]:
        """Fetch foreign flow data for a date range and store to DB.

        Args:
            days_back: Number of days to look back from today (default 14).
            start_date: Explicit start date (overrides days_back).
            end_date: Explicit end date (default: today).

        Returns:
            Dict with keys: dates_fetched, dates_skipped, rows_stored, errors.
        """
        today = end_date or datetime.now(UTC).date()
        start = start_date or (today - timedelta(days=days_back))

        session = self._get_session()
        adapter = self._adapter

        dates_fetched = 0
        dates_skipped = 0
        rows_stored = 0
        errors = 0

        current = start
        while current <= today:
            # Skip weekends (IDX trading days only)
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            # Check if we already have data for this date
            existing = session.execute(
                text("SELECT COUNT(*) FROM foreign_flow WHERE date = :d"),
                {"d": current},
            ).scalar()

            if existing and existing > 0:
                logger.debug("foreign_flow for %s already has %d rows, skipping", current, existing)
                dates_skipped += 1
                current += timedelta(days=1)
                continue

            # Fetch from idx.co.id
            try:
                records = adapter.fetch_foreign_flow_for_date(current)
                if not records:
                    logger.warning("No foreign flow data returned for %s (possibly holiday)", current)
                    dates_skipped += 1
                    current += timedelta(days=1)
                    continue

                # Bulk insert with ON CONFLICT DO UPDATE
                for rec in records:
                    session.execute(
                        text("""
                            INSERT INTO foreign_flow
                                (ticker, date, foreign_buy, foreign_sell, foreign_net,
                                 domestic_buy, domestic_sell, domestic_net, source, created_at)
                            VALUES
                                (:ticker, :date, :fb, :fs, :fn,
                                 :db, :ds, :dn, :source, :now)
                            ON CONFLICT (ticker, date, source) DO UPDATE SET
                                foreign_buy = EXCLUDED.foreign_buy,
                                foreign_sell = EXCLUDED.foreign_sell,
                                foreign_net = EXCLUDED.foreign_net,
                                domestic_buy = EXCLUDED.domestic_buy,
                                domestic_sell = EXCLUDED.domestic_sell,
                                domestic_net = EXCLUDED.domestic_net,
                                source = EXCLUDED.source
                        """),
                        {
                            "ticker": rec["ticker"],
                            "date": rec["date"],
                            "fb": rec["foreign_buy"],
                            "fs": rec["foreign_sell"],
                            "fn": rec["foreign_net"],
                            "db": rec["domestic_buy"],
                            "ds": rec["domestic_sell"],
                            "dn": rec["domestic_net"],
                            "source": rec["source"],
                            "now": datetime.now(UTC),
                        },
                    )

                session.commit()
                rows_stored += len(records)
                dates_fetched += 1
                logger.info("foreign_flow %s: %d rows stored", current, len(records))

            except Exception as e:
                logger.error("foreign_flow fetch failed for %s: %s", current, e)
                session.rollback()
                errors += 1

            current += timedelta(days=1)

        logger.info(
            "foreign_flow fetch complete: %d dates fetched, %d skipped, %d rows, %d errors",
            dates_fetched, dates_skipped, rows_stored, errors,
        )

        self._close_session()

        return {
            "dates_fetched": dates_fetched,
            "dates_skipped": dates_skipped,
            "rows_stored": rows_stored,
            "errors": errors,
        }

    def get_latest_date(self) -> date | None:
        """Get the latest date in foreign_flow table."""
        session = self._get_session()
        try:
            result = session.execute(
                text("SELECT MAX(date) FROM foreign_flow")
            ).scalar()
            return result
        finally:
            self._close_session()
