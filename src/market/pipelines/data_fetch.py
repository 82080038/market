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
             data.fetch_commodity.requested, data.fetch_macro.requested,
             data.fetch_fx.requested, data.fetch.intraday.requested
Emits:      data.fetch.stored (eod/global/commodity/macro/fx — no auto-recompute)
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

# ── Layer 1: Global Market Indices (sentiment drivers) ────────────────────
# These represent overall market sentiment that influences IDX.
# Each ticker maps to its exchange MIC for correct market-hours gating.
# Source: pustaka/03-pasar-modal-global.md, verified Aug 2026.
GLOBAL_INDICES: list[tuple[str, str, str]] = [
    # (ticker, MIC, currency)
    # US markets
    ("^GSPC", "XNYS", "USD"),   # S&P 500
    ("^IXIC", "XNAS", "USD"),   # NASDAQ Composite
    ("^DJI",  "XNYS", "USD"),   # Dow Jones Industrial Average
    ("^VIX",  "XNYS", "USD"),   # CBOE Volatility Index (fear gauge)
    ("^TNX",  "XNYS", "USD"),   # US 10-Year Treasury Yield
    # Asian markets
    ("^N225", "XTSE", "JPY"),   # Nikkei 225 (Tokyo)
    ("^HSI",  "XHKG", "HKD"),   # Hang Seng Index (Hong Kong)
    ("^JKSE", "XIDX", "IDR"),   # Jakarta Composite Index (IHSG)
    ("000001.SS", "XSHG", "CNY"),  # Shanghai Composite
    ("^KS11", "XKRX", "KRW"),   # KOSPI (Korea)
    ("^STI",  "XSES", "SGD"),   # Straits Times Index (Singapore)
    ("^SET.BK", "XBKK", "THB"), # SET Index (Thailand)
    ("^NSEI", "XNSE", "INR"),   # NIFTY 50 (India)
    ("^TWII", "XTAI", "TWD"),   # Taiwan Weighted Index
    # European markets
    ("^FTSE",  "XLON", "GBP"),   # FTSE 100 (London)
    ("^GDAXI", "XFRA", "EUR"),   # DAX 40 (Frankfurt)
    ("^STOXX50E", "XPAR", "EUR"), # Euro Stoxx 50 (Euronext Paris)
    ("FTSEMIB.MI", "XMTA", "EUR"), # FTSE MIB (Borsa Italiana)
    ("^IBEX", "XMAD", "EUR"),   # IBEX 35 (BME Madrid)
    # Americas / EM
    ("^BVSP", "BVMF", "BRL"),   # Ibovespa (Brasil B3)
    ("^GSPTSE", "XTSX", "CAD"), # S&P/TSX Composite (Canada)
    # Middle East / Africa
    ("^TASI.SR", "XSAU", "SAR"), # Tadawul All Share (Saudi)
    ("JSE.JO", "XJSE", "ZAR"),   # JSE All Share (South Africa)
    # FX / Dollar Index
    ("DX-Y.NYB", "XNYS", "USD"),  # US Dollar Index
    ("IDR=X",    "XFXS", "USD"),  # USD/IDR exchange rate
]

# ── Layer 2: Commodities (sector drivers for IDX) ──────────────────────────
# These affect specific IDX sectors:
#   - Gold/Silver → Precious Metals mining (ANTM, MDKA)
#   - Copper → Basic Materials / Mining (INCO, TINS)
#   - Crude Oil → Energy / Oil & Gas (ADRO, PTBA, MEDC)
#   - Palm Oil → Plantation / Agriculture (LSNG, BWPT, AALI)
# Source: pustaka/91-komoditas-spesifik-idx.md, verified Aug 2026.
COMMODITY_TICKERS: list[tuple[str, str, str]] = [
    # (ticker, MIC, currency)
    ("GC=F", "XCEC", "USD"),   # COMEX Gold futures
    ("CL=F", "XCEC", "USD"),   # NYMEX WTI Crude Oil futures
    ("HG=F", "XCEC", "USD"),   # COMEX Copper futures
    ("SI=F", "XCEC", "USD"),   # COMEX Silver futures
    ("CPO=F", "XKLSE", "MYR"), # Bursa Malaysia Palm Oil futures
    ("^KLSE", "XKLSE", "MYR"), # KLSE index (palm oil sector proxy)
]

# ── Layer 3: Macro Rates (stored to macro_data table, not stock_prices) ────
# These are macro indicators that go to macro_data table as time series.
# Commodities (GC=F, CL=F) are NOT here — they go to stock_prices via
# the commodity fetch layer above. This eliminates the previous duplication
# where commodities were stored in BOTH stock_prices AND macro_data.
# Source: pustaka/18 §3.3, restructured Aug 2026.
MACRO_YF_TICKERS: dict[str, str] = {
    "US10Y": "^TNX",       # US 10-Year Treasury Yield (also in indices for stock_prices)
    "VIX": "^VIX",         # CBOE Volatility Index (also in indices for stock_prices)
    "USD_IDR": "IDR=X",    # USD/IDR exchange rate (also in indices for stock_prices)
    "DXY": "DX-Y.NYB",     # US Dollar Index (also in indices for stock_prices)
}

# Backward compat — kept for any code still referencing GLOBAL_TICKERS
GLOBAL_TICKERS = [t[0] for t in GLOBAL_INDICES + COMMODITY_TICKERS]

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

        Queries FetchRegistry for idx_equity instruments with STALE/FAILED/
        NEVER_FETCHED status. Uses TickerScreener to filter out
        delisted/suspended/blocked tickers. Handles partial failures.
        Emits data.fetch.stored with summary (does NOT auto-trigger recompute).
        """
        from market.config import settings
        from market.core.events import broker
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.fetch_registry import FetchRegistry
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
            registry = FetchRegistry(session)

            # Query DB for pending idx_equity fetches
            pending = registry.get_pending_fetches("idx_equity")
            pending_tickers = {item.ticker for item in pending}

            screener = TickerScreener()
            screening = screener.screen(session)
            tickers = screening.passed

            logger.info(
                "EOD fetch: %d tickers passed screening, %d pending in DB (excluded: %d)",
                len(tickers), len(pending), screening.total_excluded,
            )

            success, failed, skipped = 0, 0, 0
            for ticker in tickers:
                yf_ticker = to_yf_ticker(ticker, "XIDX", session)

                # Skip if not pending (OK status, recently fetched)
                if yf_ticker not in pending_tickers:
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
                    registry.mark_fetched(yf_ticker, rows=result.get("stored", 0))
                else:
                    failed += 1
                    registry.mark_failed(yf_ticker, "no data returned")

            session.commit()
            logger.info("EOD fetch: %d success, %d failed, %d skipped",
                        success, failed, skipped)

            broker.emit("data.fetch.stored", {
                "source": "eod",
                "tickers_success": success,
                "tickers_failed": failed,
                "tickers_skipped": skipped,
                "screening": screening.summary(),
            })
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def on_fetch_global_requested(self, event: Event) -> None:
        """Handle data.fetch_global.requested — fetch global market indices.

        Queries FetchRegistry for global_index + volatility instruments
        with STALE/FAILED/NEVER_FETCHED status. Falls back to hardcoded
        GLOBAL_INDICES list if DB has no entries.
        """
        from market.core.events import broker
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.fetch_registry import FetchRegistry
        from market.data.storage import DataRepository
        from market.db.engine import get_sessionmaker

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)
            registry = FetchRegistry(session)

            # Query DB for pending global_index + volatility fetches
            pending = (
                registry.get_pending_fetches("global_index")
                + registry.get_pending_fetches("volatility")
            )

            if pending:
                tickers_data = [
                    (item.ticker, item.exchange_mic, item.currency)
                    for item in pending
                ]
                logger.info("Global indices fetch: %d pending from DB", len(tickers_data))
            else:
                tickers_data = list(GLOBAL_INDICES)
                logger.info("Global indices fetch: %d fallback tickers", len(tickers_data))

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
                    registry.mark_fetched(ticker, rows=result.get("stored", 0))
                else:
                    failed += 1
                    registry.mark_failed(ticker, "no data returned")

            session.commit()
            logger.info("Global indices fetch: %d success, %d failed", success, failed)
            broker.emit("data.fetch.stored", {
                "source": "global",
                "tickers_success": success,
                "tickers_failed": failed,
            })
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def on_fetch_commodity_requested(self, event: Event) -> None:
        """Handle data.fetch_commodity.requested — fetch commodity futures.

        Queries FetchRegistry for commodity instruments with STALE/FAILED/
        NEVER_FETCHED status. Falls back to hardcoded COMMODITY_TICKERS
        if DB has no entries.

        Commodities affect specific IDX sectors:
          - Gold/Silver → Precious Metals (ANTM, MDKA)
          - Copper → Basic Materials (INCO, TINS)
          - Crude Oil → Energy (ADRO, PTBA, MEDC)
          - Palm Oil → Plantation (LSNG, BWPT, AALI)
        """
        from market.core.events import broker
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.fetch_registry import FetchRegistry
        from market.data.storage import DataRepository
        from market.db.engine import get_sessionmaker

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)
            registry = FetchRegistry(session)

            # Query DB for pending commodity fetches
            pending = registry.get_pending_fetches("commodity")

            if pending:
                tickers_data = [
                    (item.ticker, item.exchange_mic, item.currency)
                    for item in pending
                ]
                logger.info("Commodity fetch: %d pending from DB", len(tickers_data))
            else:
                tickers_data = list(COMMODITY_TICKERS)
                logger.info("Commodity fetch: %d fallback tickers", len(tickers_data))

            success, failed = 0, 0
            for ticker, market_mic, currency in tickers_data:
                result = _retry(
                    lambda t=ticker, m=market_mic, c=currency: engine.fetch_and_store(
                        ticker=t, period="5d", market_mic=m, currency=c,
                    ),
                    label=f"fetch commodity {ticker}",
                    max_retries=2,
                )
                if result and result.get("stored", 0) > 0:
                    success += 1
                    registry.mark_fetched(ticker, rows=result.get("stored", 0))
                else:
                    failed += 1
                    registry.mark_failed(ticker, "no data returned")

            session.commit()
            logger.info("Commodity fetch: %d success, %d failed", success, failed)
            broker.emit("data.fetch.stored", {
                "source": "commodity",
                "tickers_success": success,
                "tickers_failed": failed,
            })
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def on_fetch_macro_requested(self, event: Event) -> None:
        """Handle data.fetch_macro.requested — fetch macro rates to macro_data.

        Fetches Layer 3 data: macro rate series (US10Y, VIX, USD/IDR, DXY)
        from yfinance and stores them to the macro_data table. These are
        macro indicators tracked as time series separate from OHLCV.

        Note: Commodities (GOLD, CRUDE_OIL) were previously fetched here
        but are now fetched via on_fetch_commodity_requested to stock_prices.
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

    def on_fetch_fx_requested(self, event: Event) -> None:
        """Handle data.fetch_fx.requested — fetch FX exchange rates.

        Queries FetchRegistry for fx instruments with STALE/FAILED/
        NEVER_FETCHED status. Fetches each pair via yfinance and stores
        to stock_prices. For pairs not available on yfinance (e.g.
        PHPIDR, INRIDR, BRLIDR, CNYIDR, SARIDR), computes cross-rates
        from USD/IDR and USD/CCY pairs.

        FX pairs are fetched with period='5d' since FX markets are
        24h on weekdays (no market open/close gating needed beyond
        weekend check).

        Emits data.fetch.stored with summary (does NOT auto-trigger
        recompute). Downstream: cross_market_coefficients and
        market_influence_kb are updated by separate scheduled tasks.
        """
        import pandas as pd
        from sqlalchemy import text

        from market.core.events import broker
        from market.data.acquisition import DataAcquisitionEngine
        from market.data.fetch_registry import FetchRegistry
        from market.data.storage import DataRepository
        from market.db.engine import get_sessionmaker

        # FX pairs that must be computed (not available on yfinance)
        COMPUTED_CROSS_RATES: dict[str, str] = {
            "PHPIDR=X": "USDPHP=X",
            "INRIDR=X": "USDINR=X",
            "BRLIDR=X": "USDBRL=X",
            "CNYIDR=X": "USDCNY=X",
            "SARIDR=X": "USDSAR=X",
        }

        session = get_sessionmaker()()
        try:
            repo = DataRepository(session)
            engine = DataAcquisitionEngine()
            engine.set_repository(repo)
            registry = FetchRegistry(session)

            pending = registry.get_pending_fetches("fx")
            logger.info("FX fetch: %d pending from DB", len(pending))

            success, failed, computed = 0, 0, 0
            computed_tickers = set(COMPUTED_CROSS_RATES.keys())

            for item in pending:
                ticker = item.ticker

                # Skip computed cross-rates — handle after yfinance fetches
                if ticker in computed_tickers:
                    continue

                result = _retry(
                    lambda t=ticker: engine.fetch_and_store(
                        ticker=t, period="5d", market_mic="XFXS",
                        currency=item.currency or "USD",
                    ),
                    label=f"fetch fx {ticker}",
                    max_retries=2,
                )
                if result and result.get("stored", 0) > 0:
                    success += 1
                    registry.mark_fetched(ticker, rows=result.get("stored", 0))
                else:
                    failed += 1
                    registry.mark_failed(ticker, "no data returned")

            # Compute cross-rates: CCYIDR = USDIDR / USDCCY
            # Only recompute if USDIDR (IDR=X) or USDCCY was fetched today
            today = date.today()
            for target_ticker, usd_ccy_ticker in COMPUTED_CROSS_RATES.items():
                try:
                    df_idr = pd.read_sql(text("""
                        SELECT timestamp::date as date, close FROM stock_prices
                        WHERE ticker='IDR=X' AND timeframe='1d'
                        ORDER BY timestamp DESC LIMIT 5
                    """), session.connection())
                    df_ccy = pd.read_sql(text(f"""
                        SELECT timestamp::date as date, close FROM stock_prices
                        WHERE ticker='{usd_ccy_ticker}' AND timeframe='1d'
                        ORDER BY timestamp DESC LIMIT 5
                    """), session.connection())

                    if df_idr.empty or df_ccy.empty:
                        continue

                    df_idr = df_idr.drop_duplicates(subset="date").set_index("date")
                    df_ccy = df_ccy.drop_duplicates(subset="date").set_index("date")
                    aligned = df_idr.join(df_ccy, lsuffix="_idr", rsuffix="_ccy").dropna()
                    if aligned.empty:
                        continue

                    cross_rate = aligned["close_idr"] / aligned["close_ccy"]
                    latest_date = cross_rate.index[-1]
                    latest_val = float(cross_rate.iloc[-1])

                    # Check if we already have this date
                    existing = session.execute(text("""
                        SELECT 1 FROM stock_prices
                        WHERE ticker=:t AND timestamp::date=:d AND timeframe='1d'
                        LIMIT 1
                    """), {"t": target_ticker, "d": latest_date}).first()

                    if existing is None:
                        from datetime import datetime as dt_cls, timezone as tz_cls
                        ts = dt_cls(latest_date.year, latest_date.month, latest_date.day,
                                    0, 0, 0, tzinfo=tz_cls.utc)
                        session.execute(text("""
                            INSERT INTO stock_prices (ticker, exchange_mic, timestamp, timeframe,
                                open, high, low, close, volume, source)
                            VALUES (:t, 'XFXS', :ts, '1d', :v, :v, :v, :v, 0, 'computed_cross_rate')
                        """), {"t": target_ticker, "ts": ts, "v": latest_val})
                        session.commit()
                        computed += 1
                        registry.mark_fetched(target_ticker, rows=1)
                except Exception as e:
                    logger.warning("Cross-rate compute %s failed: %s", target_ticker, e)

            logger.info("FX fetch: %d success, %d failed, %d cross-rates computed",
                        success, failed, computed)
            broker.emit("data.fetch.stored", {
                "source": "fx",
                "tickers_success": success,
                "tickers_failed": failed,
                "cross_rates_computed": computed,
            })
        except Exception:
            session.rollback()
            raise
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
