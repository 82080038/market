"""Tests for scheduler task registration (scheduler_tasks module)."""

from __future__ import annotations

from market.scheduler import DailyScheduler
from market.scheduler_tasks import register_default_tasks


def test_register_default_tasks_count():
    sched = DailyScheduler(persist=False)
    register_default_tasks(sched)
    assert len(sched.tasks) == 26


def test_register_default_tasks_ids():
    sched = DailyScheduler(persist=False)
    register_default_tasks(sched)
    ids = {t.task_id for t in sched.tasks}
    assert ids == {
        "startup_catchup", "fetch_intraday", "health_check",
        "fetch_eod", "fetch_global", "fetch_macro",
        "quality_check", "recompute", "generate_signals", "feature_store",
        "drift_detection", "generate_reports", "export_parquet",
        "fetch_fundamental", "scrape_news", "strategy_assignment",
        "fetch_fundamental_quarterly", "fetch_macro_fred",
        # Added 2026-08-11: macro/satellite/astronacci pipeline wiring
        "fetch_macroeconomic_indicators", "fetch_satellite",
        "macro_correlation_analysis", "compute_astronacci_cycles",
        # Added 2026-08-13: weekly scripts integrated to scheduler for catch-up
        "weekly_hrp_recompute", "weekly_drift_check",
        # Added 2026-08-16: automated backup + KPI tracking (gap #3, #4)
        "backup_postgresql", "track_kpi",
    }


def test_register_default_tasks_all_enabled():
    sched = DailyScheduler(persist=False)
    register_default_tasks(sched)
    assert all(t.enabled for t in sched.tasks)


def test_register_default_tasks_run_success():
    sched = DailyScheduler(persist=False)
    register_default_tasks(sched)
    execution = sched.run_task("feature_store")
    assert execution is not None
    assert execution.status.value == "success"


def test_register_default_tasks_idempotent():
    sched = DailyScheduler(persist=False)
    register_default_tasks(sched)
    register_default_tasks(sched)
    # Re-registering overwrites, so count stays the same
    assert len(sched.tasks) == 26


def test_register_default_tasks_order():
    """Tasks should be registered in chronological order."""
    sched = DailyScheduler(persist=False)
    register_default_tasks(sched)
    times = [t.time_of_day for t in sched.tasks]
    assert times == sorted(times)
