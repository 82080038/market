"""Built-in scheduler task definitions (pustaka/18 §6).

Provides default task registration for the DailyScheduler so that
`market scheduler list` shows real tasks and `market scheduler run`
executes them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.scheduler import DailyScheduler

logger = logging.getLogger(__name__)


def _task_fetch_eod() -> None:
    """Fetch end-of-day OHLCV data for tracked tickers."""
    from market.data.storage import DataRepository
    from market.db.engine import get_sessionmaker

    session = get_sessionmaker()()
    try:
        repo = DataRepository(session)
        tickers = repo.list_tickers()
        logger.info("EOD fetch: %d tickers tracked", len(tickers))
    finally:
        session.close()


def _task_quality_check() -> None:
    """Run data quality checks on stored OHLCV data."""
    from market.data.storage import DataRepository
    from market.db.engine import get_sessionmaker

    session = get_sessionmaker()()
    try:
        repo = DataRepository(session)
        tickers = repo.list_tickers()
        for ticker in tickers:
            bars = repo.load_ohlcv(ticker)
            if len(bars) < 30:
                logger.warning("Quality: %s has only %d bars", ticker, len(bars))
        logger.info("Quality check complete: %d tickers", len(tickers))
    finally:
        session.close()


def _task_feature_store() -> None:
    """Refresh feature store with latest computed indicators."""
    logger.info("Feature store refresh: stub — connect to FeatureStore when ready")


def _task_drift_detection() -> None:
    """Check model drift by comparing recent predictions vs actuals."""
    logger.info("Drift detection: stub — connect to PredictionEngine when ready")


def _task_generate_reports() -> None:
    """Generate daily advisory and portfolio reports."""
    logger.info("Report generation: stub — connect to AdvisoryEngine when ready")


def _task_export_parquet() -> None:
    """Export DB to parquet archive for portable backup.

    Runs after all EOD tasks to ensure parquet snapshot reflects
    the latest DB state. See pustaka/90 for sync rules.
    """
    from market.data.export_to_parquet import export_all

    logger.info("Parquet export: starting")
    results = export_all()
    total = sum(results.values())
    logger.info("Parquet export: %d rows across %d tables", total, len(results))


def register_default_tasks(scheduler: DailyScheduler) -> None:
    """Register all built-in tasks on the given scheduler.

    Args:
        scheduler: DailyScheduler instance to register tasks onto.
    """
    scheduler.register_task(
        task_id="fetch_eod",
        name="Fetch EOD OHLCV data",
        func=_task_fetch_eod,
        schedule="EOD",
        time_of_day="17:30",
    )
    scheduler.register_task(
        task_id="quality_check",
        name="Data quality checks",
        func=_task_quality_check,
        schedule="EOD",
        time_of_day="17:45",
    )
    scheduler.register_task(
        task_id="feature_store",
        name="Refresh feature store",
        func=_task_feature_store,
        schedule="EOD",
        time_of_day="18:00",
    )
    scheduler.register_task(
        task_id="drift_detection",
        name="Model drift detection",
        func=_task_drift_detection,
        schedule="daily",
        time_of_day="18:30",
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
        name="Export DB to parquet backup",
        func=_task_export_parquet,
        schedule="daily",
        time_of_day="19:30",
    )
