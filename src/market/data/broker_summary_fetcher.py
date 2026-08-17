"""Broker summary fetcher — fetches broker trading activity from idx.co.id.

Uses IDXOfficialAdapter.fetch_broker_summary_for_date() which calls the
GetBrokerSummary endpoint. Stores per-broker buy/sell data to
broker_transactions table.

Usage:
    from market.data.broker_summary_fetcher import BrokerSummaryFetcher
    fetcher = BrokerSummaryFetcher()
    count = fetcher.fetch_and_store(days_back=7)
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


class BrokerSummaryFetcher:
    """Fetch broker summary data from idx.co.id and persist to database."""

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
        days_back: int = 7,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, int]:
        """Fetch broker summary data for a date range and store to DB.

        Args:
            days_back: Number of days to look back from today.
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
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            # Check existing data for this date
            existing = session.execute(
                text("SELECT COUNT(*) FROM broker_daily_summary WHERE date = :d"),
                {"d": current},
            ).scalar()

            if existing and existing > 50:
                logger.debug("broker_daily_summary for %s already has %d rows, skipping", current, existing)
                dates_skipped += 1
                current += timedelta(days=1)
                continue

            try:
                records = adapter.fetch_broker_summary_for_date(current)
                if not records:
                    dates_skipped += 1
                    current += timedelta(days=1)
                    continue

                for rec in records:
                    session.execute(
                        text("""
                            INSERT INTO broker_daily_summary
                                (broker_code, broker_name, date, volume, value,
                                 frequency, source, created_at)
                            VALUES
                                (:broker_code, :broker_name, :date, :volume, :value,
                                 :frequency, :source, :now)
                            ON CONFLICT (broker_code, date) DO NOTHING
                        """),
                        {
                            "broker_code": rec["broker_code"],
                            "broker_name": rec["broker_name"],
                            "date": current,
                            "volume": int(rec["volume"]),
                            "value": rec["value"],
                            "frequency": rec["frequency"],
                            "source": "idx_co_id",
                            "now": datetime.now(UTC),
                        },
                    )

                session.commit()
                rows_stored += len(records)
                dates_fetched += 1
                logger.info("broker_summary %s: %d rows stored", current, len(records))

            except Exception as e:
                logger.error("broker_summary fetch failed for %s: %s", current, e)
                session.rollback()
                errors += 1

            current += timedelta(days=1)

        self._close_session()

        logger.info(
            "broker_summary fetch complete: %d dates, %d skipped, %d rows, %d errors",
            dates_fetched, dates_skipped, rows_stored, errors,
        )

        return {
            "dates_fetched": dates_fetched,
            "dates_skipped": dates_skipped,
            "rows_stored": rows_stored,
            "errors": errors,
        }
