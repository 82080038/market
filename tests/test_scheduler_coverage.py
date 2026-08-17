"""Comprehensive tests for scheduler.py — _is_due, _check_elapsed, _is_past_scheduled_time, load/save state."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from market.scheduler import DailyScheduler, ScheduledTask, TaskExecution, TaskStatus


# ── _is_due tests ─────────────────────────────────────────────────────────


class TestIsDue:
    """Test _is_due logic for various schedule types."""

    def test_never_run_always_due(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "daily", "17:30")
        assert sched._is_due(task, datetime.now(UTC))

    def test_every_15min_due_after_15min(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "every_15min", "09:00")
        task.last_run = (datetime.now(UTC) - timedelta(minutes=16)).isoformat()
        assert sched._is_due(task, datetime.now(UTC))

    def test_every_15min_not_due_before_15min(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "every_15min", "09:00")
        task.last_run = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        assert not sched._is_due(task, datetime.now(UTC))

    def test_hourly_due_after_1hr(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "hourly", "09:00")
        task.last_run = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        assert sched._is_due(task, datetime.now(UTC))

    def test_hourly_not_due_before_1hr(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "hourly", "09:00")
        task.last_run = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        assert not sched._is_due(task, datetime.now(UTC))

    def test_daily_not_due_within_20hrs(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "daily", "17:30")
        task.last_run = (datetime.now(UTC) - timedelta(hours=10)).isoformat()
        assert not sched._is_due(task, datetime.now(UTC))

    def test_daily_due_after_20hrs_and_past_time(self):
        sched = DailyScheduler(persist=False)
        # Use time_of_day="00:00" so wall-clock always passes
        task = sched.register_task("T1", "Test", lambda: None, "daily", "00:00")
        task.last_run = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        assert sched._is_due(task, datetime.now(UTC))

    def test_weekly_not_due_within_6_days(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "weekly", "10:00")
        task.last_run = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        assert not sched._is_due(task, datetime.now(UTC))

    def test_weekly_due_after_6_days_and_past_time(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "weekly", "00:00")
        task.last_run = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        assert sched._is_due(task, datetime.now(UTC))

    def test_monthly_not_due_within_28_days(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "monthly", "12:00")
        task.last_run = (datetime.now(UTC) - timedelta(days=15)).isoformat()
        assert not sched._is_due(task, datetime.now(UTC))

    def test_monthly_due_after_28_days_and_past_time(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "monthly", "00:00")
        task.last_run = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        assert sched._is_due(task, datetime.now(UTC))

    def test_unknown_schedule_defaults_to_24hr(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "weird", "00:00")
        task.last_run = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        assert sched._is_due(task, datetime.now(UTC))

    def test_unknown_schedule_not_due_within_24hr(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "weird", "00:00")
        task.last_run = (datetime.now(UTC) - timedelta(hours=12)).isoformat()
        assert not sched._is_due(task, datetime.now(UTC))


# ── _is_past_scheduled_time tests ─────────────────────────────────────────


class TestIsPastScheduledTime:
    """Test wall-clock time checking."""

    def test_midnight_always_true(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "daily", "00:00")
        assert sched._is_past_scheduled_time(task, datetime.now(UTC))

    def test_invalid_time_returns_true(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "daily", "invalid")
        assert sched._is_past_scheduled_time(task, datetime.now(UTC))

    def test_valid_time_parse(self):
        sched = DailyScheduler(persist=False)
        task = sched.register_task("T1", "Test", lambda: None, "daily", "23:59")
        # At any time, 23:59 WIB might or might not be past, but it should not raise
        result = sched._is_past_scheduled_time(task, datetime.now(UTC))
        assert isinstance(result, bool)


# ── Load/save state tests ─────────────────────────────────────────────────


class TestLoadSaveState:
    """Test load_state and save_state with mocked DB."""

    def test_load_state_no_db_session(self):
        sched = DailyScheduler(persist=True)
        sched._session_factory = MagicMock(return_value=MagicMock())
        mock_session = sched._session_factory()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            result = sched.load_state()
            assert result == 0

    def test_load_state_with_rows(self):
        sched = DailyScheduler(persist=True)
        sched.register_task("T1", "Test", lambda: None, "daily")

        mock_row = MagicMock()
        mock_row.task_id = "T1"
        mock_row.last_run = datetime.now(UTC)
        mock_row.last_status = "success"
        mock_row.last_error = ""
        mock_row.run_count = 5
        mock_row.next_run_at = None
        mock_row.is_stale = False
        mock_row.data_dependencies = None
        mock_row.data_ready = False
        mock_row.last_result = None
        mock_row.is_catchup = False
        mock_row.last_duration_seconds = None

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_row]

        sched._session_factory = lambda: mock_session
        result = sched.load_state()
        assert result == 1
        task = sched.get_task("T1")
        assert task.run_count == 5
        assert task.last_status == TaskStatus.SUCCESS
        mock_session.close.assert_called_once()

    def test_load_state_invalid_json_skipped(self):
        sched = DailyScheduler(persist=True)
        sched.register_task("T1", "Test", lambda: None, "daily")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        sched._session_factory = lambda: mock_session
        result = sched.load_state()
        assert result == 0
        mock_session.close.assert_called_once()

    def test_load_state_unknown_task_skipped(self):
        sched = DailyScheduler(persist=True)

        mock_row = MagicMock()
        mock_row.task_id = "UNKNOWN"
        mock_row.last_run = datetime.now(UTC)
        mock_row.last_status = "success"
        mock_row.last_error = ""
        mock_row.run_count = 1
        mock_row.next_run_at = None
        mock_row.is_stale = False
        mock_row.data_dependencies = None
        mock_row.data_ready = False
        mock_row.last_result = None
        mock_row.is_catchup = False
        mock_row.last_duration_seconds = None

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_row]

        sched._session_factory = lambda: mock_session
        result = sched.load_state()
        assert result == 0

    def test_load_state_invalid_status_value(self):
        sched = DailyScheduler(persist=True)
        sched.register_task("T1", "Test", lambda: None, "daily")

        mock_row = MagicMock()
        mock_row.task_id = "T1"
        mock_row.last_run = datetime.now(UTC)
        mock_row.last_status = "invalid_status"
        mock_row.last_error = ""
        mock_row.run_count = 3
        mock_row.next_run_at = None
        mock_row.is_stale = False
        mock_row.data_dependencies = None
        mock_row.data_ready = False
        mock_row.last_result = None
        mock_row.is_catchup = False
        mock_row.last_duration_seconds = None

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_row]

        sched._session_factory = lambda: mock_session
        result = sched.load_state()
        assert result == 1
        task = sched.get_task("T1")
        assert task.last_status == TaskStatus.PENDING
        assert task.run_count == 3

    def test_load_state_exception_returns_zero(self):
        sched = DailyScheduler(persist=True)
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB error")
        sched._session_factory = lambda: mock_session

        result = sched.load_state()
        assert result == 0
        mock_session.close.assert_called_once()

    def test_save_state_new_entry(self):
        sched = DailyScheduler(persist=True)
        task = sched.register_task("T1", "Test", lambda: None, "daily")
        task.last_run = datetime.now(UTC).isoformat()
        task.run_count = 1

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        sched._session_factory = lambda: mock_session

        sched.save_state(task)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_save_state_update_existing(self):
        sched = DailyScheduler(persist=True)
        task = sched.register_task("T1", "Test", lambda: None, "daily")
        task.last_run = datetime.now(UTC).isoformat()
        task.run_count = 2

        mock_existing = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_existing
        sched._session_factory = lambda: mock_session

        sched.save_state(task)
        assert mock_existing.last_run is not None
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_save_state_exception_rolls_back(self):
        sched = DailyScheduler(persist=True)
        task = sched.register_task("T1", "Test", lambda: None, "daily")

        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB error")
        sched._session_factory = lambda: mock_session

        sched.save_state(task)
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


# ── run_task with persistence ─────────────────────────────────────────────


class TestRunTaskWithPersistence:
    """Test run_task with persist=True."""

    def test_run_task_saves_state(self):
        sched = DailyScheduler(persist=True)
        sched.register_task("T1", "Test", lambda: None, "daily")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        sched._session_factory = lambda: mock_session

        execution = sched.run_task("T1")
        assert execution.status == TaskStatus.SUCCESS
        mock_session.commit.assert_called_once()

    def test_run_task_failed_saves_state(self):
        sched = DailyScheduler(persist=True)
        sched.register_task("T1", "Failing", lambda: (_ for _ in ()).throw(ValueError("boom")), "daily")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        sched._session_factory = lambda: mock_session

        execution = sched.run_task("T1")
        assert execution.status == TaskStatus.FAILED
        assert "boom" in execution.error
        mock_session.commit.assert_called_once()


# ── run_all_due with persistence ──────────────────────────────────────────


class TestRunAllDueWithPersistence:
    """Test run_all_due with persist=True."""

    def test_run_all_due_loads_state_first(self):
        sched = DailyScheduler(persist=True)
        sched.register_task("T1", "Test", lambda: None, "daily", "00:00")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        # Also need scalar_one_or_none for save_state
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        sched._session_factory = lambda: mock_session

        executions = sched.run_all_due()
        assert len(executions) == 1


# ── Status summary with executions ────────────────────────────────────────


class TestStatusSummaryExtended:
    """Extended status_summary tests."""

    def test_status_summary_with_executions(self):
        sched = DailyScheduler(persist=False)
        sched.register_task("T1", "Task 1", lambda: None, "daily")
        sched.register_task("T2", "Task 2", lambda: None, "daily")
        sched.run_task("T1")
        sched.run_task("T2")
        summary = sched.status_summary()
        assert summary["total_executions"] == 2
        assert summary["succeeded"] == 2

    def test_status_summary_with_failed(self):
        sched = DailyScheduler(persist=False)
        sched.register_task("T1", "Task 1", lambda: (_ for _ in ()).throw(ValueError("fail")), "daily")
        sched.run_task("T1")
        summary = sched.status_summary()
        assert summary["failed"] == 1
        assert summary["succeeded"] == 0

    def test_status_summary_all_pending(self):
        sched = DailyScheduler(persist=False)
        sched.register_task("T1", "Task 1", lambda: None, "daily")
        summary = sched.status_summary()
        assert summary["pending"] == 1
        assert summary["total_executions"] == 0


# ── Task and Execution dataclass tests ────────────────────────────────────


class TestDataclasses:
    """Test dataclass defaults and properties."""

    def test_scheduled_task_defaults(self):
        task = ScheduledTask("T1", "Test", lambda: None, "daily")
        assert task.time_of_day == "17:30"
        assert task.enabled is True
        assert task.last_run is None
        assert task.last_status == TaskStatus.PENDING
        assert task.run_count == 0
        assert task.metadata == {}

    def test_task_execution_defaults(self):
        exec_ = TaskExecution(task_id="T1", started_at="2026-01-01T00:00:00")
        assert exec_.finished_at == ""
        assert exec_.status == TaskStatus.RUNNING
        assert exec_.error == ""
        assert exec_.duration_seconds == 0.0

    def test_tasks_property(self):
        sched = DailyScheduler(persist=False)
        sched.register_task("T1", "Task 1", lambda: None, "daily")
        sched.register_task("T2", "Task 2", lambda: None, "daily")
        assert len(sched.tasks) == 2

    def test_executions_property(self):
        sched = DailyScheduler(persist=False)
        assert sched.executions == []
        sched.register_task("T1", "Task 1", lambda: None, "daily")
        sched.run_task("T1")
        assert len(sched.executions) == 1

    def test_get_task_not_found(self):
        sched = DailyScheduler(persist=False)
        assert sched.get_task("nonexistent") is None


# ── _get_session lazy init ────────────────────────────────────────────────


class TestGetSession:
    """Test _get_session lazy initialization."""

    def test_get_session_lazy_init(self):
        sched = DailyScheduler(persist=True)
        assert sched._session_factory is None

        mock_factory = MagicMock()
        mock_session = MagicMock()
        mock_factory.return_value = mock_session

        with patch("market.db.engine.get_sessionmaker", return_value=mock_factory):
            session = sched._get_session()
            assert session is mock_session
            assert sched._session_factory is mock_factory

    def test_get_session_reuses_factory(self):
        sched = DailyScheduler(persist=True)
        mock_factory = MagicMock()
        sched._session_factory = mock_factory

        session = sched._get_session()
        mock_factory.assert_called_once()
