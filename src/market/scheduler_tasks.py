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
    """Emit health check request — health pipeline handles quality checks.

    Previously this did direct DB queries (OHLCV model, not PG-compatible).
    Now delegates to HealthPipeline via event broker, which uses
    data_health.check_all() with proper PG/SQLite handling.
    """
    broker.emit("health.check.requested", {"source": "quality_check"})


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
    """Refresh feature store — compute ML features from latest OHLCV.

    Loads watchlist tickers from DB, fetches latest 200 bars of daily OHLCV,
    computes features via FeatureStore (RSI, SMA, BB width, ATR, volume ratio,
    forward returns), and caches results in-memory for downstream ML pipelines.
    """
    import pandas as pd
    from sqlalchemy import text

    from market.db.engine import get_sessionmaker
    from market.mlops.feature_store import FeatureStore

    logger.info("Feature store refresh: starting...")

    session = get_sessionmaker()()
    try:
        # Get active watchlist tickers
        rows = session.execute(text("""
            SELECT ticker FROM watchlist
            WHERE is_favorite = '1'
            ORDER BY ticker
            LIMIT 50
        """)).fetchall()
        tickers = [r[0] for r in rows]
        if not tickers:
            # Fallback: top tickers by volume from stock_prices
            rows = session.execute(text("""
                SELECT ticker FROM stock_prices
                WHERE timeframe = '1d' AND ticker LIKE '%.JK'
                GROUP BY ticker ORDER BY count(*) DESC LIMIT 20
            """)).fetchall()
            tickers = [r[0] for r in rows]

        if not tickers:
            logger.warning("Feature store: no tickers found")
            return

        fs = FeatureStore()
        fs.register_default_features()

        computed = 0
        for ticker in tickers:
            try:
                df = pd.read_sql(
                    text("""
                        SELECT timestamp, open, high, low, close, volume
                        FROM stock_prices
                        WHERE ticker = :t AND timeframe = '1d'
                        ORDER BY timestamp DESC LIMIT 200
                    """),
                    session.connection(),
                    params={"t": ticker},
                    parse_dates=["timestamp"],
                )
                if df.empty or len(df) < 50:
                    continue
                df = df.set_index("timestamp").sort_index()

                feature_set = fs.compute(df)
                cache_key = fs.cache(feature_set, key=f"{ticker}@1.0.0")
                computed += 1
            except Exception as exc:
                logger.debug("Feature store: %s failed — %s", ticker, exc)

        logger.info("Feature store refresh: %d/%d tickers computed, %d features registered",
                    computed, len(tickers), len(fs.registered_features))
    finally:
        session.close()


def _task_generate_signals() -> None:
    """Emit signal generation request — signal pipeline handles the rest.

    Runs after recompute completes. Delegates to SignalPipeline which
    wraps daily_signal_cron.py for actual signal generation.
    """
    broker.emit("signal.generate.requested", {
        "source": "scheduled",
        "dry_run": False,
    })


def _task_drift_detection() -> None:
    """Check model drift — compare recent predictions vs baseline.

    Loads stock_prediction table (latest predictions) and compares against
    a historical baseline using DriftDetector (PSI on predicted returns +
    metric drift on confidence). If drift is detected, persists a warning
    notification to app_notifications.
    """
    import json

    import numpy as np
    from sqlalchemy import text

    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification
    from market.mlops.drift import DriftDetector

    logger.info("Drift detection: starting...")

    session = get_sessionmaker()()
    try:
        # Load recent predictions (last 30 days)
        recent = session.execute(text("""
            SELECT ticker, predicted_return_pct, prediction_confidence,
                   predicted_direction, prediction_updated_at
            FROM stock_prediction
            WHERE prediction_updated_at >= now() - interval '30 days'
            ORDER BY prediction_updated_at DESC
        """)).fetchall()

        if len(recent) < 20:
            logger.info("Drift detection: insufficient recent predictions (%d), skipping", len(recent))
            return

        # Load baseline predictions (30-90 days ago)
        baseline = session.execute(text("""
            SELECT ticker, predicted_return_pct, prediction_confidence,
                   predicted_direction, prediction_updated_at
            FROM stock_prediction
            WHERE prediction_updated_at >= now() - interval '90 days'
              AND prediction_updated_at < now() - interval '30 days'
            ORDER BY prediction_updated_at DESC
        """)).fetchall()

        if len(baseline) < 20:
            logger.info("Drift detection: insufficient baseline predictions (%d), skipping", len(baseline))
            return

        # Prepare arrays
        recent_returns = np.array([float(r[1] or 0) for r in recent])
        baseline_returns = np.array([float(r[1] or 0) for r in baseline])
        recent_conf = np.array([float(r[2] or 0) for r in recent])
        baseline_conf = np.array([float(r[2] or 0) for r in baseline])

        detector = DriftDetector(metric_threshold=0.20, psi_threshold=0.25)
        detector.set_baseline_predictions(baseline_returns)
        detector.set_baseline_metrics({
            "mean_confidence": float(np.mean(baseline_conf)),
            "std_confidence": float(np.std(baseline_conf)),
            "mean_return": float(np.mean(baseline_returns)),
        })

        report = detector.assess(
            current_predictions=recent_returns,
            current_metrics={
                "mean_confidence": float(np.mean(recent_conf)),
                "std_confidence": float(np.std(recent_conf)),
                "mean_return": float(np.mean(recent_returns)),
            },
        )

        if report.is_drifted:
            drifted_names = [r.metric_name for r in report.drifted_metrics]
            logger.warning("Drift detected: %s", drifted_names)

            # Persist warning notification
            session2 = get_sessionmaker()()
            try:
                session2.add(AppNotification(
                    title="[WARNING] model_drift",
                    body_json=json.dumps({
                        "type": "model_drift",
                        "severity": "warning",
                        "drifted_metrics": drifted_names,
                        "psi_scores": report.psi_scores,
                        "n_recent": len(recent),
                        "n_baseline": len(baseline),
                        "message": f"Model drift detected in {len(drifted_names)} metrics: {drifted_names}",
                    }, default=str),
                    status="UNREAD",
                ))
                session2.commit()
            finally:
                session2.close()
        else:
            logger.info("Drift detection: no significant drift (PSI=%s)",
                        {k: round(v, 4) for k, v in report.psi_scores.items()} or "N/A")
    except Exception as exc:
        logger.error("Drift detection failed: %s", exc)
    finally:
        session.close()


def _task_generate_reports() -> None:
    """Generate daily advisory report — run AdvisoryEngine screening.

    Loads factor scores from the scores table, builds a universe dict,
    runs the AdvisoryEngine.generate_report() method with readiness gate,
    and persists the report summary to app_notifications.
    """
    import json

    from sqlalchemy import text

    from market.analysis.advisory import AdvisoryEngine
    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    logger.info("Report generation: starting...")

    session = get_sessionmaker()()
    try:
        # Load latest factor scores per ticker
        rows = session.execute(text("""
            SELECT DISTINCT ON (s.ticker, s.engine)
                s.ticker, s.engine, s.score, s.breakdown, s.as_of
            FROM scores s
            WHERE s.as_of >= now() - interval '7 days'
            ORDER BY s.ticker, s.engine, s.as_of DESC
        """)).fetchall()

        if not rows:
            logger.warning("Report generation: no recent scores found")
            return

        # Build universe dict: ticker → {engine_name: score}
        universe: dict[str, dict[str, float | None]] = {}
        for r in rows:
            ticker, engine, score, breakdown, as_of = r
            if ticker not in universe:
                universe[ticker] = {}
            try:
                universe[ticker][engine] = float(score) if score is not None else None
            except (TypeError, ValueError):
                universe[ticker][engine] = None

        # Map engine names to factor categories
        factor_map = {
            "technical": "technical",
            "fundamental": "fundamental",
            "sentiment": "sentiment",
            "macro": "macro",
            "global": "global",
            "relationship": "relationship",
        }

        # Normalize universe for AdvisoryEngine
        # Missing factor scores default to 0.0 so filters don't auto-reject
        normalized: dict[str, dict[str, float | None]] = {}
        for ticker, scores in universe.items():
            normalized[ticker] = {}
            for key, val in scores.items():
                mapped = factor_map.get(key, key)
                normalized[ticker][mapped] = val
            # Fill missing factors with 0.0
            for factor in ("technical", "fundamental", "sentiment", "macro", "global", "relationship"):
                if factor not in normalized[ticker] or normalized[ticker][factor] is None:
                    normalized[ticker][factor] = 0.0

        # Determine market regime from latest fear_greed
        regime = "Neutral"
        try:
            fg_row = session.execute(text("""
                SELECT value FROM fear_greed
                ORDER BY date DESC LIMIT 1
            """)).fetchone()
            if fg_row:
                fg_val = float(fg_row[0])
                if fg_val < 25:
                    regime = "Extreme Fear"
                elif fg_val < 45:
                    regime = "Fear"
                elif fg_val < 55:
                    regime = "Neutral"
                elif fg_val < 75:
                    regime = "Greed"
                else:
                    regime = "Extreme Greed"
        except Exception:
            pass

        # Generate report
        engine = AdvisoryEngine()
        report = engine.generate_report(
            market_regime=regime,
            universe=normalized,
            min_composite=50.0,
            top_n=10,
        )

        logger.info("Report generation: %s", report.summary)

        # Persist report notification
        session2 = get_sessionmaker()()
        try:
            top_picks_data = [
                {
                    "ticker": d.ticker,
                    "recommendation": d.recommendation,
                    "composite_score": round(d.composite_score, 2),
                }
                for d in report.top_picks[:10]
            ]
            session2.add(AppNotification(
                title=f"[INFO] advisory_report_{report.date}",
                body_json=json.dumps({
                    "type": "advisory_report",
                    "date": report.date,
                    "market_regime": report.market_regime,
                    "screened": report.screened,
                    "passed": report.passed,
                    "top_picks": top_picks_data,
                    "summary": report.summary,
                }, default=str),
                status="UNREAD",
            ))
            session2.commit()
            logger.info("Report generation: advisory report persisted to app_notifications")
        finally:
            session2.close()
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
    finally:
        session.close()


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

    from market.config import settings
    from market.db.engine import get_sessionmaker

    is_pg = settings.db_backend == "postgresql"
    if is_pg:
        from market.db.models import StockPrice as model
    else:
        from market.db.models import OHLCV as model

    session = get_sessionmaker()()
    try:
        latest = session.execute(
            select(func.max(model.timestamp)).where(model.timeframe == "1d")
        ).scalar()

        if latest is None:
            logger.warning("Startup catch-up: no OHLCV data found — triggering full fetch")
            stale = True
        else:
            # Check if latest daily OHLCV is older than 1 day.
            # DB stores TIMESTAMPTZ; compare with timezone-aware UTC.
            from datetime import UTC, datetime
            now = datetime.now(UTC)
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
    from datetime import UTC, datetime
    from decimal import Decimal

    import yfinance as yf
    from sqlalchemy import select

    from market.data.rate_limit import RateLimiter
    from market.data.ticker_util import to_yf_ticker
    from market.db.engine import get_sessionmaker
    from market.db.models import FundamentalData, Instrument, InstrumentMaster

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
        "totalDebt": "total_debt",
        "marketCap": "market_cap",
    }

    try:
        # Try PG instruments table first
        try:
            rows = session.execute(
                select(Instrument.ticker).where(
                    Instrument.exchange_mic == "XIDX",
                    Instrument.asset_class == "EQUITY",
                    Instrument.is_active == True,
                ).order_by(Instrument.ticker)
            ).fetchall()
        except Exception:
            session.rollback()
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
                total_debt=Decimal(str(data["total_debt"])) if "total_debt" in data else None,
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


def _task_scrape_news() -> None:
    """Scrape RSS news feeds and compute sentiment (daily).

    Runs the RSS scraper as a subprocess to avoid importing requests/psycopg2
    in the main process. Stores results in news_sentiment table.
    """
    import subprocess
    import sys

    logger.info("News sentiment scrape: starting...")

    try:
        result = subprocess.run(
            [sys.executable, "scripts/scrape_rss_news.py", "--days", "7"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("News sentiment scrape: completed successfully")
        else:
            logger.warning("News sentiment scrape: exited with code %d", result.returncode)
            if result.stderr:
                logger.debug("stderr: %s", result.stderr[:500])
    except subprocess.TimeoutExpired:
        logger.warning("News sentiment scrape: timed out after 300s")
    except Exception as e:
        logger.error("News sentiment scrape: failed — %s", e)


def _task_strategy_assignment() -> None:
    """Re-evaluate strategy assignments for all active tickers (weekly).

    Uses StrategySelector to pick the best strategy class per ticker
    based on personality profile and in-sample backtesting. Persists
    results to strategy_assignment table.
    """
    import pandas as pd
    from sqlalchemy import select, text

    from market.analysis.profiling import InstrumentProfiler
    from market.analysis.strategy_selector import StrategySelector
    from market.db.engine import get_sessionmaker
    from market.db.models import InstrumentMaster

    session = get_sessionmaker()()
    try:
        rows = session.execute(
            select(InstrumentMaster.ticker).where(
                InstrumentMaster.asset_class == "equity",
                InstrumentMaster.trading_status == "active",
            ).order_by(InstrumentMaster.ticker)
        ).fetchall()
        tickers = [r[0] for r in rows]
        logger.info("Strategy assignment: %d tickers to evaluate", len(tickers))

        profiler = InstrumentProfiler()
        selector = StrategySelector()

        # Load IHSG for beta calculation
        ihsg_df = pd.read_sql(
            "SELECT timestamp, close FROM ohlcv WHERE ticker='^JKSE' "
            "AND timeframe='1d' ORDER BY timestamp",
            session.connection(),
            parse_dates=["timestamp"],
        )
        if not ihsg_df.empty:
            ihsg_df = ihsg_df.set_index("timestamp")

        assigned = 0
        for ticker in tickers:
            try:
                df = pd.read_sql(
                    text("SELECT timestamp, open, high, low, close, volume "
                         "FROM ohlcv WHERE ticker=:t AND timeframe='1d' "
                         "ORDER BY timestamp"),
                    session.connection(),
                    params={"t": ticker},
                    parse_dates=["timestamp"],
                )
                if df.empty or len(df) < 100:
                    continue
                df = df.set_index("timestamp")

                profile = profiler.profile(ticker, df, ihsg_df)
                result = selector.select(ticker, df["close"].astype(float), profile)
                selector.persist_assignment(result, get_sessionmaker)
                assigned += 1
            except Exception as e:
                logger.debug("Strategy assignment failed for %s: %s", ticker, e)

        session.commit()
        logger.info("Strategy assignment complete: %d/%d tickers assigned", assigned, len(tickers))
    finally:
        session.close()


def _task_fetch_fundamental_quarterly() -> None:
    """Fetch quarterly fundamental history from yfinance (monthly).

    yfinance provides ~8 quarters of historical data. Running monthly
    ensures we capture new quarters as they're reported. Fetches ALL
    active IDX tickers (100+) including banking-specific metrics
    (NPL, CAR, LDR, NIM).
    """
    import subprocess
    import sys

    logger.info("Quarterly fundamental fetch: starting...")

    try:
        result = subprocess.run(
            [sys.executable, "scripts/backfill_fundamental_quarterly.py"],
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.returncode == 0:
            logger.info("Quarterly fundamental fetch: completed successfully")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-5:]:
                    logger.info("  %s", line)
        else:
            logger.warning("Quarterly fundamental fetch: exited with code %d", result.returncode)
            if result.stderr:
                logger.debug("stderr: %s", result.stderr[:500])
    except subprocess.TimeoutExpired:
        logger.warning("Quarterly fundamental fetch: timed out after 3600s")
    except Exception as e:
        logger.error("Quarterly fundamental fetch: failed — %s", e)


def _task_fetch_macro_fred() -> None:
    """Fetch Indonesia macro data from FRED (monthly).

    FRED provides:
    - INTDSBIDM193N: Indonesia Interest Rate (BI Rate) — monthly
    - IDNCPIALLMINMEI: Indonesia CPI All Items — monthly
    - NGDPRXDCID: Indonesia Real GDP — annual

    Also fetches global macro from yfinance (US10Y, VIX, Gold, Oil,
    USD/IDR, DXY) with full historical backfill instead of just
    the last 5 days.

    Runs the fetch_macro_all.py script as a subprocess.
    """
    import subprocess
    import sys

    logger.info("FRED macro fetch: starting...")

    try:
        result = subprocess.run(
            [sys.executable, "scripts/fetch_macro_all.py"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("FRED macro fetch: completed successfully")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-5:]:
                    logger.info("  %s", line)
        else:
            logger.warning("FRED macro fetch: exited with code %d", result.returncode)
            if result.stderr:
                logger.debug("stderr: %s", result.stderr[:500])
    except subprocess.TimeoutExpired:
        logger.warning("FRED macro fetch: timed out after 600s")
    except Exception as e:
        logger.error("FRED macro fetch: failed — %s", e)


def _task_fetch_macroeconomic_indicators() -> None:
    """Fetch macroeconomic indicators → macroeconomic_indicators table (PostgreSQL).

    Pulls daily global macro from yfinance (USD/IDR, VIX, Gold, Brent) and
    monthly rates/inflation from FRED (Fed Rate, US/ID CPI) into the
    TIMESTAMPTZ-anchored macroeconomic_indicators table for correlation
    analysis. Uses DynamicRateLimiter to avoid HTTP 429 IP bans.

    Runs the fetch_macroeconomic_indicators.py script as a subprocess.
    """
    import subprocess
    import sys

    logger.info("Macroeconomic indicators fetch: starting...")

    try:
        result = subprocess.run(
            [sys.executable, "scripts/fetch_macroeconomic_indicators.py", "--years", "2"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("Macroeconomic indicators fetch: completed successfully")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-5:]:
                    logger.info("  %s", line)
        else:
            logger.warning(
                "Macroeconomic indicators fetch: exited with code %d",
                result.returncode)
            if result.stderr:
                logger.debug("stderr: %s", result.stderr[:500])
    except subprocess.TimeoutExpired:
        logger.warning("Macroeconomic indicators fetch: timed out after 600s")
    except Exception as e:
        logger.error("Macroeconomic indicators fetch: failed — %s", e)


def _task_fetch_satellite() -> None:
    """Fetch satellite observations → satellite_observations table.

    Fetches NASA POWER (T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN) and
    Sentinel-2 NDVI for all DB-configured ticker-location mappings.
    Uses DynamicRateLimiter for adaptive backoff on API errors.

    Runs the fetch_satellite_data.py script as a subprocess.
    """
    import subprocess
    import sys

    logger.info("Satellite data fetch: starting...")

    try:
        result = subprocess.run(
            [sys.executable, "scripts/fetch_satellite_data.py"],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode == 0:
            logger.info("Satellite data fetch: completed successfully")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-5:]:
                    logger.info("  %s", line)
        else:
            logger.warning(
                "Satellite data fetch: exited with code %d", result.returncode)
            if result.stderr:
                logger.debug("stderr: %s", result.stderr[:500])
    except subprocess.TimeoutExpired:
        logger.warning("Satellite data fetch: timed out after 1800s")
    except Exception as e:
        logger.error("Satellite data fetch: failed — %s", e)


def _task_macro_correlation_analysis() -> None:
    """Run macro ↔ stock correlation analysis and persist results.

    Computes lagged Pearson correlation, event study, and Granger causality
    between key macro indicators (VIX, USD/IDR, Gold, Brent) and major IDX
    tickers (BBCA.JK, BBRI.JK, ANTM.JK, etc.) using the macro_correlation
    module. Results are logged for the daily report pipeline.
    """

    from market.analysis.macro_correlation import full_analysis
    from market.db.engine import get_sessionmaker

    logger.info("Macro correlation analysis: starting...")

    session = get_sessionmaker()()
    try:
        # Get top IDX tickers by volume from stock_prices
        from sqlalchemy import text
        tickers = session.execute(text("""
            SELECT ticker, count(*) AS n
            FROM stock_prices
            WHERE timeframe = '1d' AND ticker LIKE '%.JK'
            GROUP BY ticker ORDER BY n DESC LIMIT 5
        """)).scalars().all()
        if not tickers:
            tickers = ["BBCA.JK", "BBRI.JK", "ANTM.JK", "TLKM.JK", "ASII.JK"]
    finally:
        session.close()

    indicators = ["VIX_INDEX", "USD_IDR", "GOLD_PRICE", "BRENT_CRUDE"]
    significant_findings = []

    for indicator in indicators:
        for ticker in tickers:
            try:
                report = full_analysis(
                    indicator, ticker,
                    shock_threshold_pct=10.0, forward_window_days=2, max_lag=3)
                es = report.get("event_study", {})
                gc = report.get("granger_causality")
                if gc and gc.get("is_significant"):
                    significant_findings.append({
                        "indicator": indicator, "ticker": ticker,
                        "granger_p": gc["p_value"],
                        "n_events": es.get("n_events", 0),
                        "mean_return": es.get("mean_forward_return_pct"),
                    })
            except Exception as exc:
                logger.debug("  %s vs %s: %s", indicator, ticker, exc)

    logger.info("Macro correlation analysis: %d significant findings",
                len(significant_findings))
    for f in significant_findings:
        logger.info(
            "  %s → %s: Granger p=%.4f, n_events=%d, mean_ret=%.2f%%",
            f["indicator"], f["ticker"], f["granger_p"],
            f["n_events"], f["mean_return"])


def _task_compute_astronacci_cycles() -> None:
    """Compute Astronacci time cycles and persist to astronacci_cycles table.

    Generates upcoming time-cycle events (Mercury retrograde, Moon phases,
    Fibonacci time windows) for the next 90 days and stores them in the
    astronacci_cycles table for integration with v_domino_timeline.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from market.analysis.astronacci import AstronacciEngine
    from market.db.engine import get_sessionmaker

    logger.info("Astronacci cycles computation: starting...")

    engine = AstronacciEngine()
    now = datetime.now(UTC)
    end = now + timedelta(days=90)

    try:
        cycles = engine.compute_cycles(start=now, end=end)
    except Exception as exc:
        logger.warning("Astronacci cycle computation failed: %s", exc)
        return

    session = get_sessionmaker()()
    inserted = 0
    try:
        for cycle in cycles:
            result = session.execute(text("""
                INSERT INTO astronacci_cycles
                    (cycle_type, title, start_at, end_at, potential_impact,
                     target_asset_class, expected_reversal, description)
                VALUES (:ctype, :title, :start, :end, :impact, :asset, :rev, :desc)
                ON CONFLICT DO NOTHING
                RETURNING id
            """), {
                "ctype": getattr(cycle, "cycle_type", "UNKNOWN"),
                "title": getattr(cycle, "title", "Astronacci Cycle"),
                "start": getattr(cycle, "start_at", now),
                "end": getattr(cycle, "end_at", now + timedelta(days=7)),
                "impact": getattr(cycle, "potential_impact", "MEDIUM"),
                "asset": getattr(cycle, "target_asset_class", "ALL"),
                "rev": getattr(cycle, "expected_reversal", "NEUTRAL"),
                "desc": getattr(cycle, "description", None),
            })
            if result.scalar_one_or_none() is not None:
                inserted += 1
        session.commit()
        logger.info("Astronacci cycles: %d new cycles inserted (of %d computed)",
                    inserted, len(cycles))
    except Exception as exc:
        session.rollback()
        logger.error("Astronacci cycles persistence failed: %s", exc)
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
        Sat 11:00 strategy_assignment — weekly strategy re-evaluation per ticker
        Sat 12:00 fetch_fundamental_quarterly — monthly quarterly fundamentals (100+ tickers)
        Sat 12:30 fetch_macro_fred    — monthly FRED macro (BI Rate, CPI, GDP + global backfill)
        20:00  scrape_news       — RSS news sentiment scrape (daily)

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
        task_id="strategy_assignment",
        name="Weekly strategy assignment re-evaluation",
        func=_task_strategy_assignment,
        schedule="weekly",
        time_of_day="11:00",
    )
    scheduler.register_task(
        task_id="fetch_fundamental_quarterly",
        name="Monthly quarterly fundamental history (yfinance, 100+ tickers)",
        func=_task_fetch_fundamental_quarterly,
        schedule="monthly",
        time_of_day="12:00",
    )
    scheduler.register_task(
        task_id="fetch_macro_fred",
        name="Monthly FRED macro data (BI Rate, CPI, GDP + global macro backfill)",
        func=_task_fetch_macro_fred,
        schedule="monthly",
        time_of_day="12:30",
    )
    scheduler.register_task(
        task_id="fetch_satellite",
        name="Weekly satellite observations (NASA POWER + Sentinel-2 NDVI)",
        func=_task_fetch_satellite,
        schedule="weekly",
        time_of_day="13:00",
    )
    scheduler.register_task(
        task_id="compute_astronacci_cycles",
        name="Weekly Astronacci time cycle computation (next 90 days)",
        func=_task_compute_astronacci_cycles,
        schedule="weekly",
        time_of_day="14:00",
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
        task_id="fetch_macroeconomic_indicators",
        name="Daily macroeconomic indicators (USD/IDR, VIX, Gold, Brent → PG)",
        func=_task_fetch_macroeconomic_indicators,
        schedule="EOD",
        time_of_day="17:42",
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
        task_id="generate_signals",
        name="Generate trading signals for watchlist (after recompute)",
        func=_task_generate_signals,
        schedule="EOD",
        time_of_day="18:15",
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
        task_id="macro_correlation_analysis",
        name="Daily macro ↔ stock correlation & Granger causality analysis",
        func=_task_macro_correlation_analysis,
        schedule="daily",
        time_of_day="19:15",
    )
    scheduler.register_task(
        task_id="export_parquet",
        name="Export DB to parquet + WAL checkpoint (after recompute)",
        func=_task_export_parquet,
        schedule="daily",
        time_of_day="19:30",
    )
    scheduler.register_task(
        task_id="scrape_news",
        name="RSS news sentiment scrape (daily)",
        func=_task_scrape_news,
        schedule="daily",
        time_of_day="20:00",
    )
