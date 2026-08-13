"""Data fetch pipeline — fetches external market data.

SRP: This pipeline ONLY fetches data from external sources and stores it.
It does NOT recompute indicators, export, or check health.
After fetching, it emits "data.fetch.stored" — a lightweight event that
does NOT auto-trigger recompute. Recompute is triggered separately by
the scheduler (data.recompute.requested) after ALL fetch phases complete.

This decoupling prevents redundant recompute+export cycles: previously
each fetch (eod, global, macro) triggered a full recompute+export chain,
resulting in 4x recompute and 5x export per night. Now fetch only stores;
recompute and export run once after all fetches are done.

Listens to: data.fetch.requested, data.fetch_global.requested,
             data.fetch_macro.requested, data.fetch.intraday.requested
Emits:      data.fetch.stored (eod/global/macro — no auto-recompute)
            data.fetch.intraday.completed (intraday — price snapshot only)
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

# Retry config — exponential backoff for transient errors (yfinance 429,
# network timeouts). yfinance raises YFRateLimitError on HTTP 429 "Too Many
# Requests" (see yfinance/data.py _get_crumb_basic). Yahoo has no documented
# rate limit, but empirical evidence shows ~1 req/sec is safe; bursts get 429.
# Backoff: 5s, 10s, 20s — enough for Yahoo's sliding window to reset.
MAX_RETRIES = 2
RETRY_DELAY_SEC = 5
RATE_LIMIT_EXTRA_DELAY_SEC = 15  # extra delay when YFRateLimitError detected

# Global reference tickers (pustaka/18 §3.4)
# Used as fallback when DB has no non-XIDX instruments registered
GLOBAL_TICKERS = [
    "^GSPC", "^IXIC", "^DJI", "^HSI", "^N225", "^FTSE", "^GDAXI",
    "^TNX", "^VIX", "GC=F", "CL=F", "SI=F", "^JKSE",
]

# Macro series via yfinance (pustaka/18 §3.3)
# Maps macro_data series_name → yfinance ticker
MACRO_YF_TICKERS: dict[str, str] = {
    "US10Y": "^TNX",
    "VIX": "^VIX",
    "GOLD": "GC=F",
    "CRUDE_OIL": "CL=F",
    "USD_IDR": "IDR=X",
    "DXY": "DX-Y.NYB",
}

# FRED series (fetched via CSV download, not yfinance)
MACRO_FRED_SERIES: list[str] = ["DGS10", "VIXCLS", "CPIAUCSL", "FEDFUNDS", "UNRATE"]


def _retry(func: Callable[[], Any], label: str, max_retries: int = MAX_RETRIES) -> Any:
    """Retry a function with exponential backoff. Returns result or None.

    Handles yfinance YFRateLimitError (HTTP 429) with longer backoff:
    base_delay * 2^attempt + extra delay for rate limit specifically.
    This follows the pattern recommended by yfinance maintainers
    (PR #2627) and TradingAgents project (yf_retry wrapper).

    See:
        - https://github.com/ranaroussi/yfinance/pull/2627
        - https://github.com/ranaroussi/yfinance/issues/2422
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            # Detect yfinance rate limit error (HTTP 429)
            is_rate_limit = (
                "RateLimit" in type(e).__name__
                or "429" in str(e)
                or "Too Many Requests" in str(e)
            )
            if attempt < max_retries:
                if is_rate_limit:
                    # Longer backoff for rate limit: 2^attempt * base + extra
                    delay = (RETRY_DELAY_SEC * (2 ** attempt)) + RATE_LIMIT_EXTRA_DELAY_SEC
                    logger.warning(
                        "%s attempt %d/%d rate-limited (429) — retry in %ds",
                        label, attempt + 1, max_retries + 1, delay,
                    )
                else:
                    # Standard exponential backoff for transient network errors
                    delay = RETRY_DELAY_SEC * (attempt + 1)
                    logger.warning(
                        "%s attempt %d/%d failed: %s — retry in %ds",
                        label, attempt + 1, max_retries + 1, e, delay,
                    )
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
        Emits data.fetch.stored with summary (does NOT auto-trigger recompute).
        """
        from sqlalchemy import func, select

        from market.config import settings
        from market.core.events import broker
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.screener import TickerScreener
        from market.data.storage import DataRepository
        from market.data.ticker_util import to_yf_ticker
        from market.db.engine import get_sessionmaker
        from market.db.models import OHLCV, StockPrice

        is_pg = settings.db_backend == "postgresql"
        price_model = StockPrice if is_pg else OHLCV

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)

            screener = TickerScreener()
            screening = screener.screen(session)
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
                    select(func.max(price_model.timestamp)).where(price_model.ticker == yf_ticker)
                ).scalar()
                if latest and (datetime.now(UTC) - latest).days <= 1:
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

            # Emit stored event — does NOT auto-trigger recompute.
            # Recompute is triggered by scheduler after all fetch phases done.
            broker.emit("data.fetch.stored", {
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
        from market.db.models import Instrument, InstrumentMaster
        from sqlalchemy import select

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)

            # Read non-XIDX active instruments from DB
            # Try PG instruments table first
            try:
                db_rows = session.execute(
                    select(
                        Instrument.ticker,
                        Instrument.exchange_mic,
                        Instrument.currency,
                    ).where(
                        Instrument.exchange_mic != "XIDX",
                        Instrument.is_active == True,  # noqa: E712
                    )
                ).all()
            except Exception:
                session.rollback()
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
            # Emit stored event — does NOT auto-trigger recompute.
            broker.emit("data.fetch.stored", {
                "source": "global",
                "tickers_success": success,
                "tickers_failed": failed,
            })
        finally:
            session.close()

    def on_fetch_macro_requested(self, event: Event) -> None:
        """Handle data.fetch_macro.requested — fetch macro economic data.

        Fetches global macro series (US10Y, VIX, GOLD, OIL, USD/IDR, DXY)
        from yfinance using the correct ticker symbols.
        """
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

            for series_name, yf_ticker in MACRO_YF_TICKERS.items():
                latest = session.execute(
                    select(MacroData.date)
                    .where(MacroData.series_name == series_name)
                    .order_by(desc(MacroData.date))
                    .limit(1)
                ).scalar_one_or_none()

                if latest and (today - latest).days <= 3:
                    continue

                result = _retry(
                    lambda t=yf_ticker: adapter.fetch_ohlcv(
                        ticker=t,
                        period="1mo",
                        market_mic="XNYS",
                        currency="USD",
                    ),
                    label=f"macro {series_name} ({yf_ticker})",
                    max_retries=1,
                )

                if result:
                    for record in result:
                        session.add(MacroData(
                            series_name=series_name,
                            date=record.timestamp.date(),
                            value=float(record.close),
                            source="yahoo_finance",
                            frequency="daily",
                        ))
                    session.commit()
                    success += 1

            logger.info("Macro fetch: %d/%d series updated", success, len(MACRO_YF_TICKERS))
            # Emit stored event — does NOT auto-trigger recompute.
            broker.emit("data.fetch.stored", {
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
        commodities). Stores to stock_prices (PG) or ohlcv (SQLite) with timeframe='15m'.
        Does NOT trigger full recompute — only updates latest prices.

        Emits data.fetch.intraday.completed with price snapshot for FE.
        """
        from sqlalchemy import select

        from market.config import settings
        from market.core.events import broker
        from market.data.yahoo_adapter import YahooFinanceAdapter
        from market.db.engine import get_sessionmaker
        from market.db.models import OHLCV, StockPrice

        tickers = event.payload.get("tickers", [])
        if not tickers:
            logger.warning("Intraday fetch: no tickers in event payload")
            return

        is_pg = settings.db_backend == "postgresql"
        model = StockPrice if is_pg else OHLCV

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
                        select(model).where(
                            model.ticker == ticker,
                            model.timestamp == latest.timestamp,
                            model.timeframe == "15m",
                        )
                    ).scalar_one_or_none()

                    if existing is None:
                        if is_pg:
                            session.add(StockPrice(
                                ticker=ticker,
                                exchange_mic=market_mic,
                                timestamp=latest.timestamp,
                                timeframe="15m",
                                open=latest.open,
                                high=latest.high,
                                low=latest.low,
                                close=latest.close,
                                volume=int(latest.volume) if latest.volume else 0,
                                adjusted_close=latest.adjusted_close,
                                source="yahoo_finance_intraday",
                            ))
                        else:
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
