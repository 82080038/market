"""Daily scheduler for automated data updates, model training, and drift detection.

Runs scheduled tasks at defined times (EOD after IDX close).
Supports task registration, cron-like scheduling, and execution logging.

State is persisted to the scheduler_state table so missed tasks are caught up
when the application restarts.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of a scheduled task execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ScheduledTask:
    """A scheduled task definition."""

    task_id: str
    name: str
    func: Callable[[], Any]
    schedule: str  # "daily", "weekly", "monthly", "hourly", "EOD"
    time_of_day: str = "17:30"  # HH:MM in WIB
    enabled: bool = True
    last_run: str | None = None
    last_status: TaskStatus = TaskStatus.PENDING
    last_error: str = ""
    run_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    # New fields for DB-driven state tracking
    next_run_at: str | None = None
    is_stale: bool = False
    data_dependencies: list[str] = field(default_factory=list)
    data_ready: bool = False
    last_result: dict[str, Any] | None = None
    is_catchup: bool = False
    last_duration_seconds: float = 0.0


@dataclass
class TaskExecution:
    """Record of a single task execution."""

    task_id: str
    started_at: str
    finished_at: str = ""
    status: TaskStatus = TaskStatus.RUNNING
    error: str = ""
    duration_seconds: float = 0.0
    is_catchup: bool = False
    result_summary: dict[str, Any] | None = None


class DailyScheduler:
    """Daily task scheduler for the trading application.

    Schedules tasks like data updates, model retraining,
    drift detection, and report generation.

    State is persisted to the scheduler_state table so that missed
    tasks are caught up when the application restarts.
    """

    def __init__(self, tz_offset_hours: int = 7, persist: bool = True) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._executions: list[TaskExecution] = []
        self._tz_offset = tz_offset_hours
        self._persist = persist
        self._session_factory = None

    def _get_session(self):
        """Lazily get a DB session for state persistence."""
        if self._session_factory is None:
            from market.db.engine import get_sessionmaker
            self._session_factory = get_sessionmaker()
        return self._session_factory()

    def register_task(
        self,
        task_id: str,
        name: str,
        func: Callable[[], Any],
        schedule: str = "daily",
        time_of_day: str = "17:30",
        data_dependencies: list[str] | None = None,
    ) -> ScheduledTask:
        """Register a scheduled task.

        Args:
            task_id: Unique task identifier.
            name: Human-readable task name.
            func: Callable to execute.
            schedule: Schedule type ("daily", "weekly", "monthly", "hourly", "EOD").
            time_of_day: Time to run (HH:MM in WIB).
            data_dependencies: List of data layers/tables this task needs
                (e.g., ["stock_prices:idx_equity", "macro_data"]). Used by
                get_upcoming_tasks() so modules can pre-load data before render.

        Returns:
            The registered ScheduledTask.
        """
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            func=func,
            schedule=schedule,
            time_of_day=time_of_day,
            data_dependencies=data_dependencies or [],
        )
        self._tasks[task_id] = task
        return task

    def unregister_task(self, task_id: str) -> bool:
        """Remove a task from the scheduler.

        Args:
            task_id: Task to remove.

        Returns:
            True if removed, False if not found.
        """
        return self._tasks.pop(task_id, None) is not None

    def enable_task(self, task_id: str) -> bool:
        """Enable a disabled task.

        Args:
            task_id: Task to enable.

        Returns:
            True if enabled, False if not found.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.enabled = True
        return True

    def disable_task(self, task_id: str) -> bool:
        """Disable a task.

        Args:
            task_id: Task to disable.

        Returns:
            True if disabled, False if not found.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.enabled = False
        return True

    def load_state(self) -> int:
        """Load task state from scheduler_state table.

        Restores last_run, last_status, run_count, next_run_at, is_stale,
        data_dependencies, data_ready, last_result, is_catchup, and
        last_duration_seconds for each registered task from the database.
        Tasks not in the DB are left as PENDING.

        Returns:
            Number of tasks with restored state.
        """
        session = self._get_session()
        try:
            from sqlalchemy import select as _select

            from market.db.models import SchedulerState

            rows = session.execute(
                _select(SchedulerState).where(
                    SchedulerState.task_id.in_(list(self._tasks.keys()))
                )
            ).scalars().all()
            restored = 0
            for row in rows:
                task = self._tasks.get(row.task_id)
                if task is None:
                    continue
                if row.last_run:
                    task.last_run = row.last_run.isoformat() if hasattr(row.last_run, 'isoformat') else str(row.last_run)
                if row.last_status:
                    try:
                        task.last_status = TaskStatus(row.last_status)
                    except ValueError:
                        pass
                if row.last_error:
                    task.last_error = row.last_error
                if row.run_count:
                    task.run_count = row.run_count
                if row.next_run_at:
                    task.next_run_at = row.next_run_at.isoformat() if hasattr(row.next_run_at, 'isoformat') else str(row.next_run_at)
                task.is_stale = row.is_stale or False
                if row.data_dependencies:
                    task.data_dependencies = row.data_dependencies if isinstance(row.data_dependencies, list) else []
                task.data_ready = row.data_ready or False
                if row.last_result:
                    task.last_result = row.last_result
                task.is_catchup = row.is_catchup or False
                if row.last_duration_seconds is not None:
                    task.last_duration_seconds = row.last_duration_seconds
                restored += 1
            logger.info("Loaded scheduler state: %d tasks restored", restored)
            return restored
        except Exception as e:
            logger.warning("Failed to load scheduler state: %s", e)
            return 0
        finally:
            session.close()

    def save_state(self, task: ScheduledTask) -> None:
        """Save a single task's state to scheduler_state table.

        Persists all fields: last_run, last_status, last_error, run_count,
        next_run_at, is_stale, data_dependencies, data_ready, last_result,
        is_catchup, last_duration_seconds.
        """
        from sqlalchemy import select as _select

        from market.db.models import SchedulerState

        session = self._get_session()
        try:
            existing = session.execute(
                _select(SchedulerState).where(SchedulerState.task_id == task.task_id)
            ).scalar_one_or_none()

            # Compute next_run_at based on schedule
            next_run = self._compute_next_run(task)

            if existing:
                existing.last_run = task.last_run
                existing.last_status = task.last_status.value
                existing.last_error = task.last_error
                existing.run_count = task.run_count
                existing.next_run_at = next_run
                existing.is_stale = False  # Just ran, not stale
                existing.data_dependencies = task.data_dependencies if task.data_dependencies else None
                existing.data_ready = task.data_ready
                existing.last_result = task.last_result
                existing.is_catchup = task.is_catchup
                existing.last_duration_seconds = task.last_duration_seconds
            else:
                session.add(SchedulerState(
                    task_id=task.task_id,
                    last_run=task.last_run,
                    last_status=task.last_status.value,
                    last_error=task.last_error,
                    run_count=task.run_count,
                    next_run_at=next_run,
                    is_stale=False,
                    data_dependencies=task.data_dependencies if task.data_dependencies else None,
                    data_ready=task.data_ready,
                    last_result=task.last_result,
                    is_catchup=task.is_catchup,
                    last_duration_seconds=task.last_duration_seconds,
                ))
            session.commit()
        except Exception as e:
            logger.warning("Failed to save scheduler state for %s: %s", task.task_id, e)
            session.rollback()
        finally:
            session.close()

    def run_task(self, task_id: str) -> TaskExecution | None:
        """Execute a single task immediately.

        Args:
            task_id: Task to execute.

        Returns:
            TaskExecution record, or None if task not found.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None

        if not task.enabled:
            execution = TaskExecution(
                task_id=task_id,
                started_at=datetime.now(UTC).isoformat(),
                status=TaskStatus.SKIPPED,
                finished_at=datetime.now(UTC).isoformat(),
            )
            self._executions.append(execution)
            return execution

        start = datetime.now(UTC)
        execution = TaskExecution(
            task_id=task_id,
            started_at=start.isoformat(),
            is_catchup=task.is_stale,
        )

        try:
            task.last_status = TaskStatus.RUNNING
            task.func()
            task.last_status = TaskStatus.SUCCESS
            task.last_error = ""
            execution.status = TaskStatus.SUCCESS
        except Exception as e:
            task.last_status = TaskStatus.FAILED
            task.last_error = str(e)
            execution.status = TaskStatus.FAILED
            execution.error = str(e)
            logger.error(f"Task {task_id} failed: {e}")

        end = datetime.now(UTC)
        execution.finished_at = end.isoformat()
        execution.duration_seconds = (end - start).total_seconds()

        task.last_run = end.isoformat()
        task.run_count += 1
        task.is_catchup = task.is_stale
        task.last_duration_seconds = execution.duration_seconds
        task.is_stale = False  # Reset stale after run

        # Persist state to DB
        if self._persist:
            self.save_state(task)

        self._executions.append(execution)
        return execution

    def run_all_due(self) -> list[TaskExecution]:
        """Run all tasks that are due.

        Checks each task's schedule and last run time to determine
        if it should run now. Loads persisted state first so that
        catch-up works correctly after restart.

        Returns:
            List of TaskExecution records for tasks that ran.
        """
        # Load persisted state before checking due tasks
        if self._persist:
            self.load_state()

        executions: list[TaskExecution] = []
        now = datetime.now(UTC)

        for task in self._tasks.values():
            if not task.enabled:
                continue

            if self._is_due(task, now):
                execution = self.run_task(task.task_id)
                if execution is not None:
                    executions.append(execution)

        return executions

    def _is_due(self, task: ScheduledTask, now: datetime) -> bool:
        """Check if a task is due to run.

        A task is due if it has never run, or if enough time has
        passed since its last run (catch-up for missed executions).

        For daily/EOD/weekly/monthly tasks, time_of_day is enforced as a
        wall-clock trigger in WIB (Asia/Jakarta, UTC+7). The task will not
        run before its scheduled time_of_day on the current calendar day,
        even if enough time has elapsed since last_run. This prevents
        tasks from running at unexpected hours when the machine boots
        mid-day after being off.

        For every_15min/hourly tasks, only the elapsed-time check applies
        (no wall-clock gating) since these are interval-based.

        Args:
            task: Task to check.
            now: Current UTC time.

        Returns:
            True if task should run now.
        """
        if task.last_run is None:
            return True

        last = datetime.fromisoformat(task.last_run)

        if task.schedule == "every_15min":
            return (now - last) >= timedelta(minutes=15)
        elif task.schedule == "hourly":
            return (now - last) >= timedelta(hours=1)

        # For daily/EOD/weekly/monthly: check both elapsed time AND wall-clock
        elapsed_ok = self._check_elapsed(task, now, last)
        if not elapsed_ok:
            return False

        # Wall-clock check: is current WIB time >= scheduled time_of_day?
        return self._is_past_scheduled_time(task, now)

    def _check_elapsed(
        self, task: ScheduledTask, now: datetime, last: datetime,
    ) -> bool:
        """Check if enough time has elapsed since last run."""
        if task.schedule in ("daily", "EOD"):
            return (now - last) >= timedelta(hours=20)
        elif task.schedule == "weekly":
            return (now - last) >= timedelta(days=6)
        elif task.schedule == "monthly":
            return (now - last) >= timedelta(days=28)
        else:
            return (now - last) >= timedelta(hours=24)

    def _is_past_scheduled_time(
        self, task: ScheduledTask, now: datetime,
    ) -> bool:
        """Check if current WIB time is at or past the task's time_of_day.

        Uses zoneinfo for accurate timezone conversion (handles UTC offset
        correctly). time_of_day is in HH:MM format, interpreted as WIB
        (Asia/Jakarta, UTC+7 — no DST in Indonesia).

        For the startup_catchup task (time_of_day="00:00"), this always
        returns True so catch-up runs immediately on boot.
        """
        from zoneinfo import ZoneInfo

        try:
            wib = ZoneInfo("Asia/Jakarta")
            now_wib = now.astimezone(wib)
        except Exception:
            # Fallback: UTC+7 manual offset
            now_wib = now + timedelta(hours=7)

        try:
            hour, minute = map(int, task.time_of_day.split(":"))
        except (ValueError, AttributeError):
            return True  # Can't parse time, allow run

        scheduled_min = hour * 60 + minute
        current_min = now_wib.hour * 60 + now_wib.minute

        return current_min >= scheduled_min

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    @property
    def tasks(self) -> list[ScheduledTask]:
        """All registered tasks."""
        return list(self._tasks.values())

    @property
    def executions(self) -> list[TaskExecution]:
        """All execution records."""
        return list(self._executions)

    def status_summary(self) -> dict[str, Any]:
        """Get scheduler status summary.

        Returns:
            Dict with task counts and last run info.
        """
        total = len(self._tasks)
        enabled = sum(1 for t in self._tasks.values() if t.enabled)
        succeeded = sum(
            1 for t in self._tasks.values()
            if t.last_status == TaskStatus.SUCCESS
        )
        failed = sum(
            1 for t in self._tasks.values()
            if t.last_status == TaskStatus.FAILED
        )

        return {
            "total_tasks": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "succeeded": succeeded,
            "failed": failed,
            "pending": sum(
                1 for t in self._tasks.values()
                if t.last_status == TaskStatus.PENDING
            ),
            "stale": sum(1 for t in self._tasks.values() if t.is_stale),
            "total_executions": len(self._executions),
        }

    def _compute_next_run(self, task: ScheduledTask) -> datetime | None:
        """Compute the next scheduled run time for a task.

        Based on schedule type and time_of_day, returns the next
        datetime (UTC) when this task should run.

        For every_15min/hourly: next_run = last_run + interval
        For daily/EOD: next_run = tomorrow at time_of_day WIB
        For weekly: next_run = next Saturday at time_of_day WIB
        For monthly: next_run = next month on the same day at time_of_day WIB
        """
        from zoneinfo import ZoneInfo

        try:
            wib = ZoneInfo("Asia/Jakarta")
        except Exception:
            wib = None

        now = datetime.now(UTC)
        now_wib = now.astimezone(wib) if wib else now + timedelta(hours=7)

        try:
            hour, minute = map(int, task.time_of_day.split(":"))
        except (ValueError, AttributeError):
            return None

        if task.schedule == "every_15min":
            return now + timedelta(minutes=15)
        elif task.schedule == "hourly":
            return now + timedelta(hours=1)
        elif task.schedule in ("daily", "EOD"):
            # Next run is tomorrow at scheduled time WIB
            tomorrow = now_wib.date() + timedelta(days=1)
            next_wib = datetime(tomorrow.year, tomorrow.month, tomorrow.day,
                                hour, minute, tzinfo=wib or UTC)
            return next_wib.astimezone(UTC)
        elif task.schedule == "weekly":
            # Next Saturday at scheduled time
            days_until_sat = (5 - now_wib.weekday()) % 7
            if days_until_sat == 0 and now_wib.hour * 60 + now_wib.minute >= hour * 60 + minute:
                days_until_sat = 7
            next_sat = now_wib.date() + timedelta(days=days_until_sat)
            next_wib = datetime(next_sat.year, next_sat.month, next_sat.day,
                                hour, minute, tzinfo=wib or UTC)
            return next_wib.astimezone(UTC)
        elif task.schedule == "monthly":
            # Next month, same day
            if now_wib.month == 12:
                next_month = datetime(now_wib.year + 1, 1, now_wib.day,
                                      hour, minute, tzinfo=wib or UTC)
            else:
                next_month = datetime(now_wib.year, now_wib.month + 1, now_wib.day,
                                      hour, minute, tzinfo=wib or UTC)
            return next_month.astimezone(UTC)
        return None

    def check_stale_tasks(self) -> list[str]:
        """Check all tasks for staleness and update DB.

        A task is stale if its last_run is older than its expected interval
        (e.g., daily tasks stale if >26h since last run, weekly if >7 days).

        Updates is_stale flag in scheduler_state table and in-memory.
        Returns list of task_ids that are now stale.
        """
        if not self._persist:
            return []

        now = datetime.now(UTC)
        stale_tasks: list[str] = []

        for task in self._tasks.values():
            if task.task_id in ("startup_catchup", "fetch_intraday"):
                continue  # These have their own catch-up logic

            if task.last_run is None:
                task.is_stale = True
                stale_tasks.append(task.task_id)
                continue

            try:
                last = datetime.fromisoformat(task.last_run)
            except (ValueError, TypeError):
                continue

            if task.schedule in ("daily", "EOD"):
                threshold = timedelta(hours=26)
            elif task.schedule == "weekly":
                threshold = timedelta(days=7)
            elif task.schedule == "monthly":
                threshold = timedelta(days=31)
            elif task.schedule == "every_15min":
                threshold = timedelta(minutes=30)
            elif task.schedule == "hourly":
                threshold = timedelta(hours=2)
            else:
                threshold = timedelta(hours=26)

            if (now - last) > threshold:
                task.is_stale = True
                stale_tasks.append(task.task_id)

        # Persist stale flags to DB
        if stale_tasks:
            session = self._get_session()
            try:
                from sqlalchemy import text
                for tid in stale_tasks:
                    session.execute(
                        text("UPDATE scheduler_state SET is_stale = true WHERE task_id = :tid"),
                        {"tid": tid},
                    )
                session.commit()
                logger.info("Marked %d tasks as stale: %s", len(stale_tasks), stale_tasks)
            except Exception as e:
                logger.warning("Failed to persist stale flags: %s", e)
                session.rollback()
            finally:
                session.close()

        return stale_tasks

    def get_upcoming_tasks(self, within_hours: int = 24) -> list[dict[str, Any]]:
        """Get tasks scheduled to run within the next N hours.

        Reads next_run_at from scheduler_state (or computes it if missing)
        and returns tasks that are due soon. This allows modules to
        pre-load required data before the scheduled time.

        Args:
            within_hours: Look-ahead window in hours.

        Returns:
            List of dicts with task_id, name, next_run_at, data_dependencies.
        """
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=within_hours)
        upcoming: list[dict[str, Any]] = []

        for task in self._tasks.values():
            if not task.enabled:
                continue

            # Use next_run_at from loaded state, or compute it
            next_run_str = task.next_run_at
            if next_run_str:
                try:
                    next_run = datetime.fromisoformat(next_run_str)
                except (ValueError, TypeError):
                    next_run = self._compute_next_run(task)
            else:
                next_run = self._compute_next_run(task)

            if next_run and now <= next_run <= cutoff:
                upcoming.append({
                    "task_id": task.task_id,
                    "name": task.name,
                    "next_run_at": next_run.isoformat(),
                    "schedule": task.schedule,
                    "time_of_day": task.time_of_day,
                    "data_dependencies": task.data_dependencies,
                    "data_ready": task.data_ready,
                    "is_stale": task.is_stale,
                })

        upcoming.sort(key=lambda x: x["next_run_at"])
        return upcoming
