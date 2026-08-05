"""Data fetch pipeline — fetches external market data.

SRP: This pipeline ONLY fetches data from external sources and stores it.
It does NOT recompute indicators, export, or check health.
After fetching, it emits "data.fetch.completed" and the recompute pipeline
picks it up automatically.

Listens to: data.fetch.requested, data.fetch_global.requested, data.fetch_macro.requested
Emits:      data.fetch.completed
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 2
RETRY_DELAY_SEC = 5

# Global reference tickers (pustaka/18 §3.4)
GLOBAL_TICKERS = [
    "^GSPC", "^IXIC", "^DJI", "^HSI", "^N225", "^FTSE", "^GDAXI",
    "^TNX", "^VIX", "GC=F", "CL=F", "SI=F", "^JKSE",
]

# Macro series (pustaka/18 §3.3)
MACRO_SERIES = ["DGS10", "VIXCLS", "CPIAUCSL", "FEDFUNDS", "UNRATE"]


def _retry(func, label: str, max_retries: int = MAX_RETRIES) -> object:
    """Retry a function with backoff. Returns result or None."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries:
                delay = RETRY_DELAY_SEC * (attempt + 1)
                logger.warning("%s attempt %d/%d failed: %s — retry in %ds",
                              label, attempt + 1, max_retries + 1, e, delay)
                time.sleep(delay)
            else:
                logger.error("%s failed after %d attempts: %s", label, max_retries + 1, e)
                return None


class DataFetchPipeline:
    """Fetches external data and emits completion events.

    This pipeline is the ONLY module that talks to external data sources
    (Yahoo Finance, IDX scraper). Other modules never fetch directly.
    """

    def on_fetch_requested(self, event: Event) -> None:
        """Handle data.fetch.requested — fetch IDX equity OHLCV.

        Handles partial failures: failed tickers are logged but don't
        abort the batch. Emits data.fetch.completed with summary.
        """
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.storage import DataRepository
        from market.db.engine import get_sessionmaker
        from market.db.models import InstrumentMaster, OHLCV
        from sqlalchemy import select, func
        from market.core.events import broker

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)

            tickers = session.execute(
                select(InstrumentMaster.ticker).where(
                    InstrumentMaster.is_active == True,  # noqa: E712
                    InstrumentMaster.asset_class == "equity",
                )
            ).scalars().all()

            logger.info("EOD fetch: %d active equity tickers", len(tickers))

            success, failed, skipped = 0, 0, 0
            for ticker in tickers:
                latest = session.execute(
                    select(func.max(OHLCV.timestamp)).where(OHLCV.ticker == ticker)
                ).scalar()
                if latest and (datetime.now(UTC) - latest).days <= 1:
                    skipped += 1
                    continue

                result = _retry(
                    lambda t=ticker: engine.fetch_and_store(
                        ticker=t, period="5d", market_mic="XIDX", currency="IDR",
                    ),
                    label=f"fetch {ticker}",
                    max_retries=1,
                )
                if result and result.get("stored", 0) > 0:
                    success += 1
                else:
                    failed += 1

            logger.info("EOD fetch: %d success, %d failed, %d skipped",
                        success, failed, skipped)

            # Emit completion event — recompute pipeline will pick this up
            broker.emit("data.fetch.completed", {
                "source": "eod",
                "tickers_success": success,
                "tickers_failed": failed,
                "tickers_skipped": skipped,
            })
        finally:
            session.close()

    def on_fetch_global_requested(self, event: Event) -> None:
        """Handle data.fetch_global.requested — fetch global reference tickers."""
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.storage import DataRepository
        from market.db.engine import get_sessionmaker
        from market.core.events import broker

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)

            logger.info("Global fetch: %d reference tickers", len(GLOBAL_TICKERS))

            success, failed = 0, 0
            for ticker in GLOBAL_TICKERS:
                market_mic = "XIDX" if ticker in ("^JKSE",) else "XNYS"
                currency = "IDR" if ticker == "^JKSE" else "USD"

                result = _retry(
                    lambda t=ticker: engine.fetch_and_store(
                        ticker=t, period="5d", market_mic=market_mic, currency=currency,
                    ),
                    label=f"fetch {ticker}",
                    max_retries=2,
                )
                if result and result.get("stored", 0) > 0:
                    success += 1
                else:
                    failed += 1

            logger.info("Global fetch: %d success, %d failed", success, failed)
            broker.emit("data.fetch.completed", {
                "source": "global",
                "tickers_success": success,
                "tickers_failed": failed,
            })
        finally:
            session.close()

    def on_fetch_macro_requested(self, event: Event) -> None:
        """Handle data.fetch_macro.requested — fetch macro economic data."""
        from market.data.yahoo_adapter import YahooFinanceAdapter
        from market.db.engine import get_sessionmaker
        from market.db.models import MacroData
        from sqlalchemy import select, desc
        from market.core.events import broker

        session = get_sessionmaker()()
        try:
            adapter = YahooFinanceAdapter()
            today = date.today()
            success = 0

            for series in MACRO_SERIES:
                latest = session.execute(
                    select(MacroData.date)
                    .where(MacroData.series_name == series)
                    .order_by(desc(MacroData.date))
                    .limit(1)
                ).scalar_one_or_none()

                if latest and (today - latest).days <= 3:
                    continue

                result = _retry(
                    lambda s=series: adapter.fetch_ohlcv(
                        ticker=f"^{series}" if not series.startswith("^") else series,
                        period="1mo", market_mic="XNYS", currency="USD",
                    ),
                    label=f"macro {series}",
                    max_retries=1,
                )

                if result:
                    for record in result:
                        session.add(MacroData(
                            series_name=series,
                            date=record.timestamp.date(),
                            value=float(record.close),
                            source="yahoo_finance",
                        ))
                    session.commit()
                    success += 1

            logger.info("Macro fetch: %d/%d series updated", success, len(MACRO_SERIES))
            broker.emit("data.fetch.completed", {
                "source": "macro",
                "series_updated": success,
            })
        except Exception as e:
            logger.error("Macro fetch failed: %s", e)
            session.rollback()
        finally:
            session.close()
