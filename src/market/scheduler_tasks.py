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


def _task_quality_check() -> None:
    """Run data quality checks directly (lightweight, no event needed)."""
    from market.db.engine import get_sessionmaker
    from market.db.models import OHLCV
    from sqlalchemy import select, func

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

    Note: normally recompute is auto-triggered by data.fetch.completed,
    but this task allows manual recompute without fetching.
    """
    broker.emit("data.fetch.completed", {"source": "manual_recompute"})


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


def register_default_tasks(scheduler: DailyScheduler) -> None:
    """Register all built-in tasks on the given scheduler.

    Tasks are thin emitters — they emit events and pipelines do the work.
    The scheduler only controls WHEN things happen, not HOW.

    Task schedule (WIB):
        17:00  health_check      — pre-flight checks
        17:30  fetch_eod         — fetch IDX equity OHLCV
        17:35  fetch_global      — fetch global indices/commodities/bonds
        17:40  fetch_macro       — fetch macro economic data
        17:45  quality_check     — validate fetched data
        18:00  recompute         — recompute indicators/scores
        18:30  feature_store     — refresh feature store
        18:45  drift_detection   — check model drift
        19:00  generate_reports  — daily reports
        19:30  export_parquet    — backup DB to parquet + WAL checkpoint

    Event chain (automatic, after fetch):
        fetch_eod emits → data.fetch.requested
        → DataFetchPipeline fetches → emits data.fetch.completed
        → RecomputePipeline recomputes → emits data.recompute.completed
        → ExportPipeline exports → emits data.export.completed
        → HealthPipeline checks → emits health.check.completed
        → AlertPipeline evaluates alerts (terminal)
    """
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
        name="Recompute indicators & scores",
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
        name="Export DB to parquet + WAL checkpoint",
        func=_task_export_parquet,
        schedule="daily",
        time_of_day="19:30",
    )
