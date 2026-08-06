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
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 2
RETRY_DELAY_SEC = 5

# Global reference tickers (pustaka/18 §3.4)
# Used as fallback when DB has no non-XIDX instruments registered
GLOBAL_TICKERS = [
    "^GSPC", "^IXIC", "^DJI", "^HSI", "^N225", "^FTSE", "^GDAXI",
    "^TNX", "^VIX", "GC=F", "CL=F", "SI=F", "^JKSE",
]

# Macro series (pustaka/18 §3.3)
MACRO_SERIES = ["DGS10", "VIXCLS", "CPIAUCSL", "FEDFUNDS", "UNRATE"]


def _retry(func: Callable[[], Any], label: str, max_retries: int = MAX_RETRIES) -> Any:
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
    return None  # unreachable, but satisfies mypy


class DataFetchPipeline:
    """Fetches external data and emits completion events.

    This pipeline is the ONLY module that talks to external data sources
    (Yahoo Finance, IDX scraper). Other modules never fetch directly.
    """

    def on_fetch_requested(self, event: Event) -> None:
        """Handle data.fetch.requested — fetch IDX equity OHLCV.

        Uses TickerScreener to filter out delisted/suspended/blocked
        tickers before fetching. Handles partial failures: failed
        tickers are logged but don't abort the batch.
        Emits data.fetch.completed with summary.
        """
        from sqlalchemy import func, select

        from market.core.events import broker
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.screener import TickerScreener
        from market.data.storage import DataRepository
        from market.db.engine import get_sessionmaker
        from market.db.models import OHLCV

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)

            screener = TickerScreener()
            screening = screener.screen(session, asset_class="equity")
            tickers = screening.passed

            logger.info(
                "EOD fetch: %d tickers passed screening (excluded: %d)",
                len(tickers), screening.total_excluded,
            )

            success, failed, skipped = 0, 0, 0
            for ticker in tickers:
                # Use ticker_util to apply correct suffix per market_mic
                yf_ticker = to_yf_ticker(ticker, "XIDX", session)

                latest = session.execute(
                    select(func.max(OHLCV.timestamp)).where(OHLCV.ticker == yf_ticker)
                ).scalar()
                if latest and (datetime.now(UTC).replace(tzinfo=None) - latest).days <= 1:
                    skipped += 1
                    continue

                result = _retry(
                    lambda t=yf_ticker: engine.fetch_and_store(
                        ticker=t, period="5d", market_mic="XIDX", currency="IDR",
                    ),
                    label=f"fetch {yf_ticker}",
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
                "screening": screening.summary(),
            })
        finally:
            session.close()

    def on_fetch_global_requested(self, event: Event) -> None:
        """Handle data.fetch_global.requested — fetch global reference tickers.

        Reads non-XIDX instruments from instrument_master (commodities,
        indices, FX, ETFs). Falls back to hardcoded GLOBAL_TICKERS if
        DB has no non-XIDX entries.
        """
        from market.core.events import broker
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.storage import DataRepository
        from market.data.ticker_util import get_currency
        from market.db.engine import get_sessionmaker
        from market.db.models import InstrumentMaster
        from sqlalchemy import select

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)

            # Read non-XIDX active instruments from DB
            db_rows = session.execute(
                select(
                    InstrumentMaster.ticker,
                    InstrumentMaster.market_mic,
                    InstrumentMaster.base_currency,
                ).where(
                    InstrumentMaster.market_mic != "XIDX",
                    InstrumentMaster.is_active == True,  # noqa: E712
                )
            ).all()

            if db_rows:
                tickers_data = [
                    (row[0], row[1], row[2] or get_currency(row[0], row[1]))
                    for row in db_rows
                ]
                logger.info("Global fetch: %d tickers from DB", len(tickers_data))
            else:
                # Fallback to hardcoded list
                tickers_data = [
                    (t, "XIDX" if t == "^JKSE" else "XNYS",
                     "IDR" if t == "^JKSE" else "USD")
                    for t in GLOBAL_TICKERS
                ]
                logger.info("Global fetch: %d fallback tickers", len(tickers_data))

            success, failed = 0, 0
            for ticker, market_mic, currency in tickers_data:
                result = _retry(
                    lambda t=ticker, m=market_mic, c=currency: engine.fetch_and_store(
                        ticker=t, period="5d", market_mic=m, currency=c,
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
        from sqlalchemy import desc, select

        from market.core.events import broker
        from market.data.yahoo_adapter import YahooFinanceAdapter
        from market.db.engine import get_sessionmaker
        from market.db.models import MacroData

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
                        ticker=f"^{s}" if not s.startswith("^") else s,
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

    def on_intraday_requested(self, event: Event) -> None:
        """Handle data.fetch.intraday.requested — poll yfinance for latest prices.

        Fetches latest 15-min interval data for key tickers (indices,
        commodities). Stores to OHLCV with timeframe='15m'.
        Does NOT trigger full recompute — only updates latest prices.

        Emits data.fetch.intraday.completed with price snapshot for FE.
        """
        from sqlalchemy import select

        from market.core.events import broker
        from market.data.yahoo_adapter import YahooFinanceAdapter
        from market.db.engine import get_sessionmaker
        from market.db.models import OHLCV

        tickers = event.payload.get("tickers", [])
        if not tickers:
            logger.warning("Intraday fetch: no tickers in event payload")
            return

        session = get_sessionmaker()()
        try:
            adapter = YahooFinanceAdapter()
            prices: dict[str, Any] = {}
            success, failed = 0, 0

            for ticker in tickers:
                result = _retry(
                    lambda t=ticker: adapter.fetch_ohlcv(
                        ticker=t, period="1d", interval="15m",
                    ),
                    label=f"intraday {ticker}",
                    max_retries=1,
                )

                if result and len(result) > 0:
                    latest = result[-1]
                    market_mic = "XIDX" if ticker in ("^JKSE",) else "XNYS"
                    currency = "IDR" if ticker == "^JKSE" else "USD"

                    existing = session.execute(
                        select(OHLCV).where(
                            OHLCV.ticker == ticker,
                            OHLCV.timestamp == latest.timestamp,
                            OHLCV.timeframe == "15m",
                        )
                    ).scalar_one_or_none()

                    if existing is None:
                        session.add(OHLCV(
                            ticker=ticker,
                            timestamp=latest.timestamp,
                            timeframe="15m",
                            open=latest.open,
                            high=latest.high,
                            low=latest.low,
                            close=latest.close,
                            volume=int(latest.volume) if latest.volume else 0,
                            source="yahoo_finance_intraday",
                        ))

                    prices[ticker] = {
                        "price": float(latest.close),
                        "change": float(latest.close - latest.open),
                        "change_pct": round(
                            float((latest.close - latest.open) / latest.open * 100)
                            if latest.open else 0.0, 2,
                        ),
                        "volume": int(latest.volume) if latest.volume else 0,
                        "timestamp": latest.timestamp.isoformat(),
                        "currency": currency,
                        "market_mic": market_mic,
                    }
                    success += 1
                else:
                    failed += 1

            session.commit()
            logger.info(
                "Intraday fetch: %d success, %d failed (of %d tickers)",
                success, failed, len(tickers),
            )

            broker.emit("data.fetch.intraday.completed", {
                "source": "intraday",
                "prices": prices,
                "success": success,
                "failed": failed,
            })
        except Exception as e:
            logger.error("Intraday fetch failed: %s", e)
            session.rollback()
        finally:
            session.close()
