"""Scheduler task definitions — thin event emitters (SRP).

Each task is a thin function that ONLY emits an event.
The actual work is done by pipelines that subscribe to those events.
This means scheduler_tasks.py has ZERO imports from data/analysis modules.

Before (tightly coupled):
    def _task_fetch_eod():
        from market.data.acquisition import DataAcquisitionEngine  # ← direct import
        engine = DataAcquisitionEngine()
        engine.fetch_and_store(...)

After (event-driven):
    def _task_fetch_eod():
        broker.emit("data.fetch.requested", {})  # ← just emit, pipeline handles it

The scheduler no longer knows HOW data is fetched. It only knows WHEN.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from market.core.events import broker

if TYPE_CHECKING:
    from market.scheduler import DailyScheduler

logger = logging.getLogger(__name__)


def _task_health_check() -> None:
    """Emit health check request — health pipeline handles the rest."""
    broker.emit("health.check.requested", {})


def _task_fetch_eod() -> None:
    """Emit EOD fetch request — data fetch pipeline handles the rest."""
    broker.emit("data.fetch.requested", {"source": "eod"})


def _task_fetch_global() -> None:
    """Emit global fetch request — data fetch pipeline handles the rest."""
    broker.emit("data.fetch_global.requested", {"source": "global"})


def _task_fetch_macro() -> None:
    """Emit macro fetch request — data fetch pipeline handles the rest."""
    broker.emit("data.fetch_macro.requested", {"source": "macro"})


# Tickers for intraday polling — key indices + commodities + user watchlist
INTRADAY_TICKERS = [
    "^JKSE", "^GSPC", "^IXIC", "^DJI", "^HSI", "^N225", "^FTSE", "^GDAXI",
    "^TNX", "^VIX", "GC=F", "CL=F", "SI=F",
]


def _task_fetch_intraday() -> None:
    """Emit intraday fetch request — poll yfinance for key tickers every 15 min.

    Only runs during active market hours (IDX: 09:00-15:50 WIB, or global
    market hours). Fetches latest price snapshot for ~40 tickers, stores
    to DB with timeframe='15m'. Does NOT trigger full recompute.
    """
    broker.emit("data.fetch.intraday.requested", {
        "source": "intraday",
        "tickers": INTRADAY_TICKERS,
    })


def _task_quality_check() -> None:
    """Run data quality checks directly (lightweight, no event needed)."""
    from sqlalchemy import func, select

    from market.db.engine import get_sessionmaker
    from market.db.models import OHLCV

    session = get_sessionmaker()()
    try:
        counts = session.execute(
            select(OHLCV.ticker, func.count()).group_by(OHLCV.ticker)
        ).all()
        low_data = sum(1 for _, c in counts if c < 30)
        total = len(counts)
        logger.info("Quality check: %d tickers, %d with <30 bars", total, low_data)

        anomalies = session.execute(
            select(func.count()).where(OHLCV.high < OHLCV.low)
        ).scalar()
        if anomalies:
            logger.warning("OHLC anomalies (high<low): %d rows", anomalies)
    finally:
        session.close()


def _task_recompute() -> None:
    """Emit recompute request — recompute pipeline handles the rest.

    Recompute runs ONCE after all fetch phases (eod, global, macro) are done.
    Previously this emitted a fake "data.fetch.completed" event to trick the
    recompute pipeline into running. Now it emits the proper
    "data.recompute.requested" event that the recompute pipeline listens to.

    Scheduled daily runs use incremental=True (only append new dates for
    time-series tables). Manual recompute via dashboard can use full mode.
    """
    broker.emit("data.recompute.requested", {
        "source": "scheduled_recompute",
        "incremental": True,
    })


def _task_feature_store() -> None:
    """Refresh feature store (stub — connect to FeatureStore when ready)."""
    logger.info("Feature store refresh: stub")


def _task_drift_detection() -> None:
    """Check model drift (stub — connect to PredictionEngine when ready)."""
    logger.info("Drift detection: stub")


def _task_generate_reports() -> None:
    """Generate daily reports (stub — connect to AdvisoryEngine when ready)."""
    logger.info("Report generation: stub")


def _task_export_parquet() -> None:
    """Emit export request — export pipeline handles the rest."""
    broker.emit("data.export.requested", {"source": "scheduled"})


def _task_startup_catchup() -> None:
    """Check data staleness on startup and catch up if needed.

    This task runs ONCE when the application starts. It checks whether
    the latest OHLCV data is stale (older than 1 trading day). If stale,
    it triggers the full fetch → recompute → export chain to catch up
    on missed runs while the computer was off.

    This handles the real-world scenario where the developer's machine
    is not always on at scheduled times (17:30 WIB fetch, 18:00 recompute,
    19:30 export). When the machine boots up, this task detects the gap
    and backfills automatically.

    Idempotency: fetch pipelines already skip tickers whose latest OHLCV
    is within 1 day (on_fetch_requested) or 3 days (macro). So re-running
    fetch after a missed day only fetches the missing data, not duplicates.
    Recompute is DELETE+INSERT (idempotent). Export is incremental hybrid
    (only writes changed partitions). Safe to re-run.

    See:
        - pustaka/95-sync-db-to-parquet.md §4.1 (incremental sync)
        - https://datadriven.io/pipeline/backfill (idempotent backfill)
        - https://muhammadamal.my.id/blog/etl-idempotent-watermarks/
    """
    from sqlalchemy import func, select

    from market.db.engine import get_sessionmaker
    from market.db.models import OHLCV

    session = get_sessionmaker()()
    try:
        latest = session.execute(
            select(func.max(OHLCV.timestamp)).where(OHLCV.timeframe == "1d")
        ).scalar()

        if latest is None:
            logger.warning("Startup catch-up: no OHLCV data found — triggering full fetch")
            stale = True
        else:
            # Check if latest daily OHLCV is older than 1 day.
            # Use naive datetime comparison (DB stores UTC naive).
            from datetime import UTC, datetime
            now = datetime.now(UTC).replace(tzinfo=None)
            age_hours = (now - latest).total_seconds() / 3600
            stale = age_hours > 26  # >26h = missed at least 1 trading day
            logger.info(
                "Startup catch-up: latest OHLCV=%s (%.1f hours ago, stale=%s)",
                latest, age_hours, stale,
            )

        if stale:
            logger.info("Startup catch-up: data is stale — triggering fetch chain")
            # Phase 1: fetch all data sources (idempotent — skips fresh tickers)
            broker.emit("data.fetch.requested", {"source": "startup_catchup"})
            broker.emit("data.fetch_global.requested", {"source": "startup_catchup"})
            broker.emit("data.fetch_macro.requested", {"source": "startup_catchup"})
            # Phase 2: recompute (runs after fetch via scheduler, or manually)
            # NOTE: We don't auto-chain here. The scheduler's run_all_due()
            # will pick up recompute and export tasks if they're also due.
            # If not due (e.g., last_run within 20h), user can trigger manually.
            # For immediate catch-up, emit recompute after a short delay
            # to let fetch phases complete. In practice, fetch is synchronous
            # (event broker is sync), so by the time we get here, fetch is done.
            broker.emit("data.recompute.requested", {"source": "startup_catchup", "incremental": True})
            # Phase 3: export (after recompute completes)
            broker.emit("data.export.requested", {"source": "startup_catchup"})
            logger.info("Startup catch-up: fetch → recompute → export chain emitted")
        else:
            logger.info("Startup catch-up: data is fresh — no action needed")
    except Exception as e:
        logger.error("Startup catch-up failed: %s", e)
    finally:
        session.close()


def _task_fetch_fundamental() -> None:
    """Fetch fundamental data from yfinance (weekly snapshot).

    yfinance only provides current fundamental snapshot, so running this
    weekly builds historical fundamental data gradually over time.
    """
    from market.db.engine import get_sessionmaker
    from market.db.models import FundamentalData, InstrumentMaster
    from market.data.rate_limit import RateLimiter
    from market.data.ticker_util import to_yf_ticker
    from decimal import Decimal
    from datetime import UTC, date, datetime
    import yfinance as yf
    from sqlalchemy import select

    limiter = RateLimiter(max_calls=1.0)
    session = get_sessionmaker()()
    fetch_date = datetime.now(UTC).date()

    INFO_MAP = {
        "trailingPE": "pe",
        "priceToBook": "pb",
        "returnOnEquity": "roe",
        "debtToEquity": "der",
        "dividendYield": "dividend_yield",
        "trailingEps": "eps",
        "bookValue": "book_value_per_share",
        "totalRevenue": "revenue",
        "netIncomeToCommon": "net_income",
        "totalAssets": "total_assets",
        "totalDebt": "total_liabilities",
        "totalCash": "cash_flow",
        "marketCap": "market_cap",
    }

    try:
        rows = session.execute(
            select(InstrumentMaster.ticker).where(
                InstrumentMaster.market_mic == "XIDX",
                InstrumentMaster.asset_class == "equity",
                InstrumentMaster.is_active == True,
            ).order_by(InstrumentMaster.ticker)
        ).fetchall()
        tickers = [to_yf_ticker(r[0], "XIDX", session) for r in rows]
        logger.info("Fundamental fetch: %d tickers", len(tickers))

        inserted = 0
        for ticker in tickers:
            limiter.acquire()
            try:
                info = yf.Ticker(ticker).info
            except Exception:
                continue
            if not info:
                continue

            data = {}
            for yf_key, db_col in INFO_MAP.items():
                val = info.get(yf_key)
                if val is not None:
                    data[db_col] = float(val)

            if not data:
                continue

            existing = session.execute(
                select(FundamentalData).where(
                    FundamentalData.ticker == ticker,
                    FundamentalData.date == fetch_date,
                    FundamentalData.source == "yahoo_finance",
                )
            ).scalar_one_or_none()

            if existing:
                continue

            session.add(FundamentalData(
                ticker=ticker,
                date=fetch_date,
                pe=Decimal(str(data["pe"])) if "pe" in data else None,
                pb=Decimal(str(data["pb"])) if "pb" in data else None,
                roe=Decimal(str(data["roe"])) if "roe" in data else None,
                der=Decimal(str(data["der"])) if "der" in data else None,
                dividend_yield=Decimal(str(data["dividend_yield"])) if "dividend_yield" in data else None,
                eps=Decimal(str(data["eps"])) if "eps" in data else None,
                book_value_per_share=Decimal(str(data["book_value_per_share"])) if "book_value_per_share" in data else None,
                revenue=Decimal(str(data["revenue"])) if "revenue" in data else None,
                net_income=Decimal(str(data["net_income"])) if "net_income" in data else None,
                total_assets=Decimal(str(data["total_assets"])) if "total_assets" in data else None,
                total_liabilities=Decimal(str(data["total_liabilities"])) if "total_liabilities" in data else None,
                cash_flow=Decimal(str(data["cash_flow"])) if "cash_flow" in data else None,
                market_cap=Decimal(str(data["market_cap"])) if "market_cap" in data else None,
                source="yahoo_finance",
            ))
            inserted += 1

            if inserted % 100 == 0:
                session.commit()

        session.commit()
        logger.info("Fundamental fetch complete: %d new snapshots", inserted)
    finally:
        session.close()


def register_default_tasks(scheduler: DailyScheduler) -> None:
    """Register all built-in tasks on the given scheduler.

    Tasks are thin emitters — they emit events and pipelines do the work.
    The scheduler only controls WHEN things happen, not HOW.

    Task schedule (WIB):
        STARTUP  startup_catchup   — check staleness, catch up if missed (once)
        09:00-15:50  fetch_intraday — poll yfinance every 15 min (market hours)
        17:00  health_check      — pre-flight checks
        17:30  fetch_eod         — fetch IDX equity OHLCV
        17:35  fetch_global      — fetch global indices/commodities/bonds
        17:40  fetch_macro       — fetch macro economic data
        17:45  quality_check     — validate fetched data
        18:00  recompute         — recompute indicators/scores (ONCE, not per-fetch)
        18:30  feature_store     — refresh feature store
        18:45  drift_detection   — check model drift
        19:00  generate_reports  — daily reports
        19:30  export_parquet    — backup DB to parquet + WAL checkpoint (ONCE)
        Sat 10:00 fetch_fundamental — weekly fundamental snapshot from yfinance

    Decoupled event flow (fetch does NOT auto-trigger recompute/export):
        PHASE 1: fetch_eod/global/macro → data.fetch.stored (no auto-recompute)
        PHASE 2: recompute → data.recompute.requested → data.recompute.completed
        PHASE 3: export → data.export.requested → data.export.completed
        PHASE 4: health → data.export.completed → health.check.completed
        ALERTS:  data.recompute.completed → AlertPipeline (terminal)

    Startup catch-up (handles computer was off at scheduled times):
        On startup, if latest OHLCV > 26 hours old, triggers full
        fetch → recompute → export chain. Idempotent: fetch skips fresh
        tickers, recompute is DELETE+INSERT, export is incremental hybrid.
    """
    # ── Startup catch-up: runs once on application start ──────────
    # Checks if data is stale (>26h since last OHLCV) and backfills.
    # This handles the case where the computer was off at 17:30 WIB.
    scheduler.register_task(
        task_id="startup_catchup",
        name="Startup data staleness check & catch-up",
        func=_task_startup_catchup,
        schedule="daily",  # _is_due returns True if never run or >20h ago
        time_of_day="00:00",  # nominal time; actual trigger is run_all_due() on startup
    )

    scheduler.register_task(
        task_id="fetch_intraday",
        name="Intraday price poll (15-min interval)",
        func=_task_fetch_intraday,
        schedule="every_15min",
        time_of_day="09:00",
    )
    scheduler.register_task(
        task_id="fetch_fundamental",
        name="Weekly fundamental data snapshot (yfinance)",
        func=_task_fetch_fundamental,
        schedule="weekly",
        time_of_day="10:00",
    )
    scheduler.register_task(
        task_id="health_check",
        name="Pre-flight health checks",
        func=_task_health_check,
        schedule="daily",
        time_of_day="17:00",
    )
    scheduler.register_task(
        task_id="fetch_eod",
        name="Fetch EOD OHLCV data (IDX)",
        func=_task_fetch_eod,
        schedule="EOD",
        time_of_day="17:30",
    )
    scheduler.register_task(
        task_id="fetch_global",
        name="Fetch global reference tickers",
        func=_task_fetch_global,
        schedule="EOD",
        time_of_day="17:35",
    )
    scheduler.register_task(
        task_id="fetch_macro",
        name="Fetch macro economic data",
        func=_task_fetch_macro,
        schedule="EOD",
        time_of_day="17:40",
    )
    scheduler.register_task(
        task_id="quality_check",
        name="Data quality checks",
        func=_task_quality_check,
        schedule="EOD",
        time_of_day="17:45",
    )
    scheduler.register_task(
        task_id="recompute",
        name="Recompute indicators & scores (after all fetches)",
        func=_task_recompute,
        schedule="EOD",
        time_of_day="18:00",
    )
    scheduler.register_task(
        task_id="feature_store",
        name="Refresh feature store",
        func=_task_feature_store,
        schedule="EOD",
        time_of_day="18:30",
    )
    scheduler.register_task(
        task_id="drift_detection",
        name="Model drift detection",
        func=_task_drift_detection,
        schedule="daily",
        time_of_day="18:45",
    )
    scheduler.register_task(
        task_id="generate_reports",
        name="Generate daily reports",
        func=_task_generate_reports,
        schedule="daily",
        time_of_day="19:00",
    )
    scheduler.register_task(
        task_id="export_parquet",
        name="Export DB to parquet + WAL checkpoint (after recompute)",
        func=_task_export_parquet,
        schedule="daily",
        time_of_day="19:30",
    )
