"""Earnings calendar fetcher — fetches corporate events from idx.co.id.

Uses IDXOfficialAdapter.fetch_company_calendar() which calls the
GetCompanyCalendar endpoint. Stores RUPS, dividend, split events to
earnings_calendar table.

Usage:
    from market.data.earnings_calendar_fetcher import EarningsCalendarFetcher
    fetcher = EarningsCalendarFetcher()
    count = fetcher.fetch_and_store(months_ahead=3)
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


class EarningsCalendarFetcher:
    """Fetch earnings/corporate event calendar from idx.co.id and persist to DB."""

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

    def fetch_and_store(self, months_ahead: int = 3) -> dict[str, int]:
        """Fetch corporate event calendar for upcoming months and store to DB.

        Args:
            months_ahead: Number of months to fetch ahead (default 3).

        Returns:
            Dict with keys: months_fetched, events_stored, errors.
        """
        session = self._get_session()
        adapter = self._adapter

        months_fetched = 0
        events_stored = 0
        errors = 0

        today = datetime.now(UTC).date()

        for month_offset in range(months_ahead):
            target_date = today.replace(day=1) + timedelta(days=month_offset * 30)
            # Adjust to first day of month
            if target_date.day > 1:
                target_date = target_date.replace(day=1)

            try:
                records = adapter.fetch_company_calendar(target_date, date_range="m")
                if not records:
                    logger.debug("No calendar events for %s", target_date.strftime("%Y-%m"))
                    months_fetched += 1
                    continue

                for rec in records:
                    # Parse event date
                    try:
                        event_date_str = rec.get("event_date", "")
                        if event_date_str:
                            event_date = datetime.strptime(event_date_str[:10], "%Y-%m-%d").date()
                        else:
                            continue
                    except Exception:
                        continue

                    # Parse tgl_rups if available
                    tgl_rups = None
                    tgl_rups_str = rec.get("tgl_rups", "")
                    if tgl_rups_str and tgl_rups_str[:4] != "1911":
                        try:
                            tgl_rups = datetime.strptime(tgl_rups_str[:19], "%Y-%m-%dT%H:%M:%S")
                        except Exception:
                            pass

                    session.execute(
                        text("""
                            INSERT INTO corporate_calendar
                                (ticker, event_date, event_type, description,
                                 agenda, location, step, tgl_rups, tgl_pe,
                                 source, created_at)
                            VALUES
                                (:ticker, :event_date, :event_type, :description,
                                 :agenda, :location, :step, :tgl_rups, :tgl_pe,
                                 :source, :now)
                            ON CONFLICT (ticker, event_date, event_type) DO NOTHING
                        """),
                        {
                            "ticker": rec["ticker"],
                            "event_date": event_date,
                            "event_type": rec.get("event_type", ""),
                            "description": rec.get("description", ""),
                            "agenda": rec.get("agenda", ""),
                            "location": rec.get("location", ""),
                            "step": rec.get("step", ""),
                            "tgl_rups": tgl_rups,
                            "tgl_pe": None,
                            "source": "idx_co_id",
                            "now": datetime.now(UTC),
                        },
                    )
                    events_stored += 1

                session.commit()
                months_fetched += 1
                logger.info("earnings_calendar %s: %d events stored",
                           target_date.strftime("%Y-%m"), len(records))

            except Exception as e:
                logger.error("earnings_calendar fetch failed for %s: %s",
                            target_date.strftime("%Y-%m"), e)
                session.rollback()
                errors += 1

        self._close_session()

        logger.info(
            "earnings_calendar fetch complete: %d months, %d events, %d errors",
            months_fetched, events_stored, errors,
        )

        return {
            "months_fetched": months_fetched,
            "events_stored": events_stored,
            "errors": errors,
        }
