"""Scheduler endpoints: task status, cron jobs, pipeline health."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.db.engine import get_session
from market.db.models import SystemState

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

# Static task definitions (mirrors register_default_tasks in scheduler_tasks.py)
TASK_DEFINITIONS: list[dict[str, str]] = [
    {"task_id": "startup_catchup", "name": "Startup data staleness check & catch-up", "schedule": "daily", "time_of_day": "00:00"},
    {"task_id": "fetch_intraday", "name": "Intraday price poll (15-min interval)", "schedule": "every_15min", "time_of_day": "09:00"},
    {"task_id": "fetch_fundamental", "name": "Weekly fundamental data snapshot", "schedule": "weekly", "time_of_day": "10:00"},
    {"task_id": "weekly_hrp_recompute", "name": "Weekly HRP + Multi-Strategy portfolio recompute", "schedule": "weekly", "time_of_day": "10:00"},
    {"task_id": "strategy_assignment", "name": "Weekly strategy re-evaluation", "schedule": "weekly", "time_of_day": "11:00"},
    {"task_id": "weekly_drift_check", "name": "Weekly feature drift check (PSI)", "schedule": "weekly", "time_of_day": "11:00"},
    {"task_id": "fetch_fundamental_quarterly", "name": "Monthly quarterly fundamentals", "schedule": "monthly", "time_of_day": "12:00"},
    {"task_id": "fetch_macro_fred", "name": "Monthly FRED macro data", "schedule": "monthly", "time_of_day": "12:30"},
    {"task_id": "fetch_satellite", "name": "Weekly satellite observations", "schedule": "weekly", "time_of_day": "13:00"},
    {"task_id": "compute_astronacci_cycles", "name": "Weekly Astronacci time cycle", "schedule": "weekly", "time_of_day": "14:00"},
    {"task_id": "health_check", "name": "Pre-flight health checks", "schedule": "daily", "time_of_day": "17:00"},
    {"task_id": "fetch_eod", "name": "Fetch EOD OHLCV data (IDX)", "schedule": "EOD", "time_of_day": "17:30"},
    {"task_id": "fetch_global", "name": "Fetch global reference tickers", "schedule": "EOD", "time_of_day": "17:35"},
    {"task_id": "fetch_macro", "name": "Fetch macro economic data", "schedule": "EOD", "time_of_day": "17:40"},
    {"task_id": "fetch_macroeconomic_indicators", "name": "Daily macroeconomic indicators", "schedule": "EOD", "time_of_day": "17:42"},
    {"task_id": "quality_check", "name": "Data quality checks", "schedule": "EOD", "time_of_day": "17:45"},
    {"task_id": "recompute", "name": "Recompute indicators & scores", "schedule": "EOD", "time_of_day": "18:00"},
    {"task_id": "generate_signals", "name": "Generate trading signals", "schedule": "EOD", "time_of_day": "18:15"},
    {"task_id": "feature_store", "name": "Refresh feature store", "schedule": "EOD", "time_of_day": "18:30"},
    {"task_id": "drift_detection", "name": "Model drift detection", "schedule": "daily", "time_of_day": "18:45"},
    {"task_id": "generate_reports", "name": "Generate daily reports", "schedule": "daily", "time_of_day": "19:00"},
    {"task_id": "macro_correlation_analysis", "name": "Macro ↔ stock correlation analysis", "schedule": "daily", "time_of_day": "19:15"},
    {"task_id": "export_parquet", "name": "Export DB to parquet + WAL checkpoint", "schedule": "daily", "time_of_day": "19:30"},
    {"task_id": "scrape_news", "name": "RSS news sentiment scrape", "schedule": "daily", "time_of_day": "20:00"},
]

# Static cron job definitions (mirrors crontab -l).
# Schedule field adalah cron expression dalam WIB (Asia/Jakarta, UTC+7) —
# cron mengikuti timezone sistem. Sebelumnya ditulis sebagai UTC yang menyebabkan
# semua task berjalan 7 jam terlalu cepat (sistem = WIB, bukan UTC).
# Lihat logs/crontab_backup_20260813_153625.txt untuk versi lama.
CRON_JOBS: list[dict[str, str]] = [
    {"schedule": "30 7 * * *", "time_wib": "07:30", "script": "scrape_rss_news.py", "description": "RSS news scrape (sebelum IDX open 09:00 WIB)"},
    {"schedule": "0 17 * * 1-5", "time_wib": "17:00", "script": "run_daily_scheduler.sh", "description": "Daily scheduler — 24 tasks (setelah IDX close, Sen-Jum)"},
    {"schedule": "0 10 * * 6", "time_wib": "10:00 Sat", "script": "run_daily_scheduler.sh", "description": "Weekly scheduler trigger — weekly tasks due (>6 hari): HRP, drift, fundamental, dll."},
    {"schedule": "0 5 * * 2-6", "time_wib": "05:00", "script": "run_global_fetch.sh", "description": "Global market fetch (post US close, Sel-Sab)"},
    {"schedule": "15 16 * * 1-5", "time_wib": "16:15", "script": "daily_signal_cron.py", "description": "Daily signal generation (setelah IDX close)"},
    {"schedule": "@reboot", "time_wib": "boot", "script": "catchup_daily.sh", "description": "Catch-up semua missed tasks saat boot"},
]

# Pipeline phases (mirrors wiring.py)
PIPELINE_PHASES: list[dict[str, str]] = [
    {"phase": "1", "name": "Fetch", "trigger": "data.fetch.requested", "handler": "DataFetchPipeline", "emits": "data.fetch.stored"},
    {"phase": "2", "name": "Recompute", "trigger": "data.recompute.requested", "handler": "RecomputePipeline", "emits": "data.recompute.completed"},
    {"phase": "3", "name": "Export", "trigger": "data.export.requested", "handler": "ExportPipeline", "emits": "data.export.completed"},
    {"phase": "4", "name": "Health", "trigger": "data.export.completed / health.check.requested", "handler": "HealthPipeline", "emits": "health.check.completed"},
    {"phase": "5", "name": "Alerts", "trigger": "data.recompute.completed", "handler": "AlertPipeline", "emits": "alert.check.completed"},
    {"phase": "6", "name": "Signals", "trigger": "signal.generate.requested", "handler": "SignalPipeline", "emits": "signal.generate.completed"},
    {"phase": "7", "name": "Notifications", "trigger": "alert.check.completed / signal.generate.completed", "handler": "NotificationPipeline", "emits": "(terminal)"},
]


@router.get("/status")
async def scheduler_status(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Scheduler status — task execution state from system_state table.

    Returns task definitions merged with persisted execution state
    (last_run, last_status, last_error, run_count) from the database.
    """
    # Load persisted scheduler state
    rows = session.execute(
        select(SystemState.key, SystemState.value).where(
            SystemState.key.like("scheduler:%")
        )
    ).all()

    state_map: dict[str, dict[str, Any]] = {}
    for key, value in rows:
        task_id = key.replace("scheduler:", "", 1)
        try:
            state_map[task_id] = json.loads(value) if value else {}
        except (json.JSONDecodeError, TypeError):
            state_map[task_id] = {}

    # Merge definitions with state
    tasks: list[dict[str, Any]] = []
    for defn in TASK_DEFINITIONS:
        tid = defn["task_id"]
        st = state_map.get(tid, {})
        tasks.append({
            **defn,
            "last_run": st.get("last_run"),
            "last_status": st.get("last_status", "pending"),
            "last_error": st.get("last_error", ""),
            "run_count": st.get("run_count", 0),
        })

    # Summary counts
    succeeded = sum(1 for t in tasks if t["last_status"] == "success")
    failed = sum(1 for t in tasks if t["last_status"] == "failed")
    pending = sum(1 for t in tasks if t["last_status"] == "pending")
    never_run = sum(1 for t in tasks if t["last_run"] is None)

    return {
        "tasks": tasks,
        "cron_jobs": CRON_JOBS,
        "pipeline_phases": PIPELINE_PHASES,
        "summary": {
            "total_tasks": len(tasks),
            "succeeded": succeeded,
            "failed": failed,
            "pending": pending,
            "never_run": never_run,
        },
    }


@router.post("/run")
async def scheduler_run() -> dict[str, Any]:
    """Trigger due tasks manually.

    Light tasks run inline and return results immediately.
    Heavy tasks (fetch, recompute, export) are dispatched in background
    threads — check scheduler status later for results.
    """
    import threading
    from datetime import UTC, datetime

    from market.api.app import _get_scheduler, _HEAVY_TASKS

    sched = _get_scheduler()
    if sched._persist:
        sched.load_state()

    now = datetime.now(UTC)
    due_tasks = [
        t for t in sched.tasks
        if t.enabled and sched._is_due(t, now)
    ]

    results = []
    heavy_dispatched = []

    for task in due_tasks:
        if task.task_id in _HEAVY_TASKS:
            heavy_dispatched.append(task.task_id)

            def _run_heavy(t=task):
                try:
                    sched.run_task(t.task_id)
                except Exception:
                    pass

            threading.Thread(
                target=_run_heavy, daemon=True,
                name=f"api-task-{task.task_id}",
            ).start()
        else:
            ex = sched.run_task(task.task_id)
            if ex:
                results.append({
                    "task_id": ex.task_id,
                    "status": ex.status.value,
                    "duration_seconds": round(ex.duration_seconds, 2),
                    "error": ex.error,
                })

    return {
        "executed": len(results) + len(heavy_dispatched),
        "results": results,
        "heavy_dispatched": heavy_dispatched,
    }
