"""Daily scheduler for automated data updates, model training, and drift detection.

Runs scheduled tasks at defined times (EOD after IDX close).
Supports task registration, cron-like scheduling, and execution logging.
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
    """

    def __init__(self, tz_offset_hours: int = 7) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._executions: list[TaskExecution] = []
        self._tz_offset = tz_offset_hours

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

        self._executions.append(execution)
        return execution

    def run_all_due(self) -> list[TaskExecution]:
        """Run all tasks that are due.

        Checks each task's schedule and last run time to determine
        if it should run now.

        Returns:
            List of TaskExecution records for tasks that ran.
        """
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
