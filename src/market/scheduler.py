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

from sqlalchemy import text

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
    schedule: str  # "daily", "weekly", "hourly", "EOD"
    time_of_day: str = "17:30"  # HH:MM in WIB
    enabled: bool = True
    last_run: str | None = None
    last_status: TaskStatus = TaskStatus.PENDING
    last_error: str = ""
    run_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskExecution:
    """Record of a single task execution."""

    task_id: str
    started_at: str
    finished_at: str = ""
    status: TaskStatus = TaskStatus.RUNNING
    error: str = ""
    duration_seconds: float = 0.0


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
    ) -> ScheduledTask:
        """Register a scheduled task.

        Args:
            task_id: Unique task identifier.
            name: Human-readable task name.
            func: Callable to execute.
            schedule: Schedule type ("daily", "weekly", "hourly", "EOD").
            time_of_day: Time to run (HH:MM in WIB).

        Returns:
            The registered ScheduledTask.
        """
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            func=func,
            schedule=schedule,
            time_of_day=time_of_day,
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

        Restores last_run, last_status, and run_count for each registered
        task from the database. Tasks not in the DB are left as PENDING.

        Returns:
            Number of tasks with restored state.
        """
        session = self._get_session()
        try:
            rows = session.execute(
                text("SELECT task_id, last_run, last_status, last_error, run_count FROM scheduler_state")
            ).fetchall()
            restored = 0
            for row in rows:
                task = self._tasks.get(row[0])
                if task is None:
                    continue
                if row[1] is not None:
                    task.last_run = str(row[1])
                if row[2]:
                    try:
                        task.last_status = TaskStatus(row[2])
                    except ValueError:
                        pass
                if row[3]:
                    task.last_error = row[3]
                if row[4]:
                    task.run_count = row[4]
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

        Uses UPSERT (INSERT OR REPLACE) to update or insert the row.
        """
        session = self._get_session()
        try:
            session.execute(
                text(
                    "INSERT OR REPLACE INTO scheduler_state "
                    "(task_id, last_run, last_status, last_error, run_count, updated_at) "
                    "VALUES (:tid, :lr, :ls, :le, :rc, datetime('now'))"
                ),
                {
                    "tid": task.task_id,
                    "lr": task.last_run,
                    "ls": task.last_status.value,
                    "le": task.last_error or None,
                    "rc": task.run_count,
                },
            )
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
        )

        try:
            task.last_status = TaskStatus.RUNNING
            task.func()
            task.last_status = TaskStatus.SUCCESS
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

        Args:
            task: Task to check.
            now: Current UTC time.

        Returns:
            True if task should run now.
        """
        if task.last_run is None:
            return True

        last = datetime.fromisoformat(task.last_run)

        if task.schedule == "hourly":
            return (now - last) >= timedelta(hours=1)
        elif task.schedule in ("daily", "EOD"):
            return (now - last) >= timedelta(hours=20)
        elif task.schedule == "weekly":
            return (now - last) >= timedelta(days=6)
        else:
            return (now - last) >= timedelta(hours=24)

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
            "total_executions": len(self._executions),
        }
