"""FastAPI application for Market (pustaka/18 §8).

Thin factory: creates a FastAPI app and includes all route modules.
Each route module is an APIRouter with its own prefix and tags.

Endpoint inventory:
    GET  /api/health              — health check
    GET  /api/env                 — environment config
    GET  /api/markets             — market registry list
    GET  /api/scores/{ticker}     — 6 factor scores for a ticker
    GET  /api/recommend/{ticker}  — composite recommendation with XAI
    GET  /api/advisory            — advisory report (screening → top picks)
    GET  /api/readiness/{ticker}  — instrument readiness assessment
    GET  /api/portfolio           — portfolio summary (NAV, positions, exposure)
    GET  /api/watchlist           — watchlist list
    POST /api/watchlist           — add to watchlist
    DELETE /api/watchlist/{ticker} — remove from watchlist
    GET  /api/backtest/run        — run backtest (query params)
    GET  /api/autonomous-backtest/status   — autonomous backtest runner status
    GET  /api/autonomous-backtest/runs     — list of past autonomous backtest runs
    GET  /api/autonomous-backtest/latest   — latest autonomous backtest run details
    POST /api/autonomous-backtest/trigger  — force trigger autonomous backtest (admin)
    GET  /api/automation/config   — get automation config & gate status
    POST /api/automation/config   — set automation config
    POST /api/automation/plan     — prepare execution plan from signals
    POST /api/automation/execute  — execute plan via broker
    POST /api/leverage/advise     — leverage recommendation with justification
    POST /api/pattern/detect      — detect patterns (no look-ahead, as_of date)
    POST /api/prediction/predict  — predict next-period price (no look-ahead)
    POST /api/prediction/verify   — verify past prediction, track error + root cause
    GET  /api/prediction/errors   — prediction error summary with lessons
    GET  /api/prediction/risk/{ticker} — risk adjustment from prediction errors
    GET  /api/delisting/summary   — delisting memory summary
    GET  /api/delisting/records   — list all delisting records
    GET  /api/delisting/lessons   — AI lessons from delisting events
    GET  /api/delisting/check/{ticker} — check ticker for delisting/suspension/warnings
    POST /api/delisting/record    — record a delisting or suspension event
    POST /api/delisting/block     — block an instrument from portfolio
    POST /api/delisting/filter    — filter tickers for portfolio inclusion
    GET  /api/instruments         — list instruments (filter by market/asset class)
    GET  /api/fx-risk             — FX risk assessment for multi-currency positions
    GET  /api/data/sources        — data source health listing
    GET  /api/data/watermarks     — table watermarks (staleness tracking)
    GET  /api/data/audit          — audit log (paginated)
    POST /api/data/fetch          — trigger manual data fetch
    GET  /api/data/quality/{ticker} — data quality score per ticker
    GET  /api/prices/latest         — latest intraday price snapshot
    POST /api/prices/intraday/trigger — manually trigger intraday fetch
    GET  /api/prices/compare/{ticker} — prediction vs actual price comparison
    GET  /api/notifications             — list notifications (paginated, filterable)
    GET  /api/notifications/{id}        — single notification detail
    PATCH /api/notifications/{id}/read  — mark notification as READ
    GET  /api/notifications/signals/latest — latest unread daily signal payload
    GET  /api/scheduler/status           — scheduler task status, cron jobs, pipeline phases
    GET  /docs                           — Swagger UI (interactive API docs)
    GET  /redoc                          — ReDoc API documentation
    GET  /openapi.json                   — OpenAPI 3.x schema
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from fastapi import FastAPI

from market.logging_config import setup_logging

from market.api.error_handlers import register_error_handlers
from market.api.routes_analysis import router as analysis_router
from market.api.routes_automation import router as automation_router
from market.api.routes_backtest import autonomous_router as autonomous_backtest_router
from market.api.routes_backtest import router as backtest_router
from market.api.routes_cosmos import router as cosmos_router
from market.api.routes_data import router as data_router
from market.api.routes_delisting import router as delisting_router
from market.api.routes_instruments import router as instruments_router
from market.api.routes_multi_asset import router as multi_asset_router
from market.api.routes_notifications import router as notifications_router
from market.api.routes_portfolio import router as portfolio_router
from market.api.routes_prediction import router as prediction_router
from market.api.routes_prices import router as prices_router
from market.api.routes_recompute import router as recompute_router
from market.api.routes_reports import router as reports_router
from market.api.routes_scheduler import router as scheduler_router
from market.api.routes_security import router as security_router
from market.api.routes_settings import router as settings_router
from market.api.routes_strategy import router as strategy_router
from market.api.routes_system import router as system_router

logger = logging.getLogger(__name__)

# Global scheduler instance — shared between background loop and API endpoints
_scheduler_instance = None
_scheduler_thread = None
_scheduler_stop_event = threading.Event()

SCHEDULER_POLL_INTERVAL = 300  # 5 minutes


def _get_scheduler():
    """Get or create the global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        from market.core.wiring import wire_all_events
        from market.scheduler import DailyScheduler
        from market.scheduler_tasks import register_default_tasks

        wire_all_events()
        _scheduler_instance = DailyScheduler()
        register_default_tasks(_scheduler_instance)
        logger.info("Scheduler instance created with %d tasks",
                     len(_scheduler_instance.tasks))
    return _scheduler_instance


# Heavy tasks that fetch external data — run in background thread
# so they don't block the scheduler loop or other tasks
_HEAVY_TASKS = frozenset({
    "fetch_eod", "fetch_global", "fetch_macro", "fetch_macroeconomic_indicators",
    "fetch_fundamental", "fetch_fundamental_quarterly", "fetch_macro_fred",
    "fetch_satellite", "fetch_intraday", "scrape_news",
    "weekly_hrp_recompute", "weekly_drift_check",
    "strategy_assignment", "compute_astronacci_cycles",
    "macro_correlation_analysis", "export_parquet",
    "backup_postgresql", "track_kpi",
    "recompute", "generate_signals", "startup_catchup",
})


def _scheduler_loop() -> None:
    """Background loop that runs all due tasks periodically.

    Heavy/long tasks (data fetch, export) are dispatched in separate
    threads so they don't block the loop. Light tasks run inline.
    """
    logger.info("Scheduler background loop started (poll every %ds)",
                SCHEDULER_POLL_INTERVAL)
    while not _scheduler_stop_event.is_set():
        try:
            sched = _get_scheduler()
            # Load state to know what's due
            if sched._persist:
                sched.load_state()

            now = datetime.now(UTC)
            due_tasks = [
                t for t in sched.tasks
                if t.enabled and sched._is_due(t, now)
            ]

            if due_tasks:
                logger.info("Scheduler: %d due tasks", len(due_tasks))

            for task in due_tasks:
                if task.task_id in _HEAVY_TASKS:
                    # Run heavy task in separate thread
                    def _run_heavy(t=task):
                        try:
                            ex = sched.run_task(t.task_id)
                            if ex:
                                logger.info("  [bg] %s: %s (%.1fs)",
                                            ex.task_id, ex.status.value,
                                            ex.duration_seconds)
                        except Exception as e:
                            logger.error("  [bg] %s failed: %s", t.task_id, e)
                    threading.Thread(
                        target=_run_heavy, daemon=True,
                        name=f"task-{task.task_id}",
                    ).start()
                else:
                    # Run light task inline
                    ex = sched.run_task(task.task_id)
                    if ex:
                        logger.info("  %s: %s (%.1fs)",
                                    ex.task_id, ex.status.value,
                                    ex.duration_seconds)
        except Exception as e:
            logger.error("Scheduler loop error: %s", e)

        _scheduler_stop_event.wait(SCHEDULER_POLL_INTERVAL)

    logger.info("Scheduler background loop stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Set up structured logging (Gap #28)
    setup_logging()

    app = FastAPI(
        title="Market API",
        description="Single-user capital market decision-support API.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.include_router(system_router)
    app.include_router(analysis_router)
    app.include_router(portfolio_router)
    app.include_router(backtest_router)
    app.include_router(autonomous_backtest_router)
    app.include_router(automation_router)
    app.include_router(prediction_router)
    app.include_router(delisting_router)
    app.include_router(instruments_router)
    app.include_router(data_router)
    app.include_router(prices_router)
    app.include_router(recompute_router)
    app.include_router(scheduler_router)
    app.include_router(notifications_router)
    app.include_router(cosmos_router)
    app.include_router(multi_asset_router)
    app.include_router(strategy_router)
    app.include_router(reports_router)
    app.include_router(security_router)
    app.include_router(settings_router)

    # Register global error handlers (Gap #29)
    register_error_handlers(app)

    @app.on_event("startup")
    def _start_scheduler() -> None:
        global _scheduler_thread
        _scheduler_stop_event.clear()
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop, daemon=True, name="scheduler-loop",
        )
        _scheduler_thread.start()

    @app.on_event("shutdown")
    def _stop_scheduler() -> None:
        _scheduler_stop_event.set()
        if _scheduler_thread is not None:
            _scheduler_thread.join(timeout=10)

    return app


# Module-level app instance
app = create_app()
