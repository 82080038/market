"""Tests for Autonomous Backtest Runner (pustaka/29, pustaka/67, pustaka/86)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.autonomous.agent import SelfEvolutionAgent
from market.backtest.autonomous import (
    AutonomousBacktestRunner,
    BacktestStatus,
    BacktestTrigger,
    StrategyType,
    register_autonomous_backtest_tasks,
)
from market.scheduler import DailyScheduler


def _make_ohlcv(n: int = 400, seed: int = 42) -> pd.DataFrame:
    """Generate mock OHLCV data."""
    rng = np.random.RandomState(seed)
    close = 8000 + rng.randn(n).cumsum() * 50
    dates = pd.bdate_range("2023-01-01", periods=n)
    return pd.DataFrame({
        "open": close + rng.randn(n) * 10,
        "high": close + abs(rng.randn(n) * 20),
        "low": close - abs(rng.randn(n) * 20),
        "close": close,
        "volume": rng.randint(100000, 1000000, n).astype(float),
    }, index=dates)


def _make_instruments() -> dict[str, pd.DataFrame]:
    """Generate mock instruments dict."""
    return {
        "BBCA.JK": _make_ohlcv(400, 42),
        "BBRI.JK": _make_ohlcv(400, 123),
        "TLKM.JK": _make_ohlcv(400, 999),
    }


# ---------------------------------------------------------------------------
# AutonomousBacktestRunner tests
# ---------------------------------------------------------------------------


class TestAutonomousBacktestRunner:
    def test_run_basic(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        assert run.status == BacktestStatus.COMPLETED
        assert run.total_instruments == 3
        assert run.total_strategies == 3  # buy_hold, ma_crossover, conviction
        assert len(run.instrument_results) == 9  # 3 instruments x 3 strategies
        assert run.successful > 0
        assert run.run_id.startswith("ABT-")

    def test_run_with_agent(self):
        runner = AutonomousBacktestRunner()
        agent = SelfEvolutionAgent()
        instruments = _make_instruments()
        run = runner.run(instruments, agent=agent)

        assert run.status == BacktestStatus.COMPLETED
        assert len(run.agent_actions_proposed) > 0
        action = run.agent_actions_proposed[0]
        assert "action" in action
        assert "cycle_id" in action
        assert "confidence" in action

    def test_multiple_runs_increment_id(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run1 = runner.run(instruments)
        run2 = runner.run(instruments)

        assert run1.run_id != run2.run_id
        assert len(runner.runs) == 2

    def test_latest_property(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run1 = runner.run(instruments)
        assert runner.latest is run1

        run2 = runner.run(instruments)
        assert runner.latest is run2

    def test_empty_instruments(self):
        runner = AutonomousBacktestRunner()
        run = runner.run({})

        assert run.status == BacktestStatus.COMPLETED
        assert run.total_instruments == 0
        assert len(run.instrument_results) == 0
        assert run.avg_sharpe == 0.0

    def test_empty_dataframe_skipped(self):
        runner = AutonomousBacktestRunner()
        run = runner.run({"EMPTY.JK": pd.DataFrame()})

        assert run.skipped > 0
        skipped = [r for r in run.instrument_results if r.status == BacktestStatus.SKIPPED]
        assert len(skipped) > 0

    def test_trigger_types(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()

        for trigger in BacktestTrigger:
            run = runner.run(instruments, trigger=trigger)
            assert run.trigger == trigger

    def test_trigger_data_change(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.trigger_data_change(instruments, changed_tickers=["BBCA.JK"])

        assert run.trigger == BacktestTrigger.DATA_CHANGE
        assert run.total_instruments == 1

    def test_trigger_data_change_all(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.trigger_data_change(instruments)

        assert run.trigger == BacktestTrigger.DATA_CHANGE
        assert run.total_instruments == 3

    def test_trigger_market_event(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.trigger_market_event(instruments)

        assert run.trigger == BacktestTrigger.MARKET_EVENT

    def test_trigger_user_activity(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.trigger_user_activity(instruments)

        assert run.trigger == BacktestTrigger.USER_ACTIVITY

    def test_metrics_aggregation(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        if run.successful > 0:
            assert run.best_sharpe >= run.avg_sharpe
            assert run.avg_sharpe >= run.worst_sharpe

    def test_best_worst_strategy(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        if run.successful > 0:
            assert run.best_strategy != ""
            assert run.worst_strategy != ""

    def test_summary_populated(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        assert "Run" in run.summary
        assert "Sharpe" in run.summary

    def test_status_summary_idle(self):
        runner = AutonomousBacktestRunner()
        summary = runner.status_summary()

        assert summary["total_runs"] == 0
        assert summary["status"] == "idle"

    def test_status_summary_after_run(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        runner.run(instruments)
        summary = runner.status_summary()

        assert summary["total_runs"] == 1
        assert summary["latest_run"] is not None
        assert summary["latest_status"] == "completed"

    def test_walk_forward_included(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        wf_results = [
            r for r in run.instrument_results
            if r.walk_forward is not None
        ]
        # With 300 bars, walk-forward should work for most
        assert len(wf_results) > 0

    def test_monte_carlo_included(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        mc_results = [
            r for r in run.instrument_results
            if r.monte_carlo is not None
        ]
        # Buy & hold should generate at least 1 trade pair
        assert len(mc_results) > 0

    def test_custom_strategies(self):
        runner = AutonomousBacktestRunner(
            strategies=[StrategyType.BUY_HOLD],
        )
        instruments = _make_instruments()
        run = runner.run(instruments)

        assert run.total_strategies == 1
        assert len(run.instrument_results) == 3

    def test_duration_recorded(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        assert run.duration_seconds > 0.0

    def test_instruments_tested_list(self):
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()
        run = runner.run(instruments)

        assert "BBCA.JK" in run.instruments_tested
        assert "BBRI.JK" in run.instruments_tested
        assert "TLKM.JK" in run.instruments_tested

    def test_agent_action_on_drift(self):
        """Agent should propose retrain when walk-forward consistency is low."""
        runner = AutonomousBacktestRunner()
        agent = SelfEvolutionAgent()
        instruments = _make_instruments()
        run = runner.run(instruments, agent=agent)

        # Agent should have been called and proposed something
        assert len(run.agent_actions_proposed) > 0


# ---------------------------------------------------------------------------
# Scheduler integration tests
# ---------------------------------------------------------------------------


class TestSchedulerIntegration:
    def test_register_tasks(self):
        scheduler = DailyScheduler()
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()

        task_ids = register_autonomous_backtest_tasks(
            scheduler, runner, instruments,
        )

        assert len(task_ids) == 2
        assert "autonomous_backtest_eod" in task_ids
        assert "autonomous_backtest_data" in task_ids

        eod_task = scheduler.get_task("autonomous_backtest_eod")
        assert eod_task is not None
        assert eod_task.schedule == "EOD"

        data_task = scheduler.get_task("autonomous_backtest_data")
        assert data_task is not None
        assert data_task.schedule == "hourly"

    def test_run_eod_task(self):
        scheduler = DailyScheduler()
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()

        register_autonomous_backtest_tasks(scheduler, runner, instruments)

        execution = scheduler.run_task("autonomous_backtest_eod")
        assert execution is not None
        assert execution.status.value == "success"
        assert runner.latest is not None
        assert runner.latest.trigger == BacktestTrigger.SCHEDULED_EOD

    def test_run_data_change_task(self):
        scheduler = DailyScheduler()
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()

        register_autonomous_backtest_tasks(scheduler, runner, instruments)

        execution = scheduler.run_task("autonomous_backtest_data")
        assert execution is not None
        assert execution.status.value == "success"
        assert runner.latest is not None
        assert runner.latest.trigger == BacktestTrigger.DATA_CHANGE

    def test_instruments_provider_callable(self):
        scheduler = DailyScheduler()
        runner = AutonomousBacktestRunner()
        instruments = _make_instruments()

        call_count = [0]

        def provider():
            call_count[0] += 1
            return instruments

        register_autonomous_backtest_tasks(scheduler, runner, provider)
        scheduler.run_task("autonomous_backtest_eod")

        assert call_count[0] == 1
        assert runner.latest is not None


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestAutonomousBacktestAPI:
    def test_status_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/autonomous-backtest/status")
        assert response.status_code == 200
        data = response.json()
        assert "total_runs" in data

    def test_runs_endpoint_empty(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/autonomous-backtest/runs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_latest_endpoint_idle(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/autonomous-backtest/latest")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "idle"

    def test_trigger_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.post(
            "/api/autonomous-backtest/trigger",
            json={"trigger": "manual_force"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data

    def test_status_after_trigger(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        client.post("/api/autonomous-backtest/trigger", json={})
        response = client.get("/api/autonomous-backtest/status")
        data = response.json()
        assert data["total_runs"] >= 1

    def test_latest_after_trigger(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        client.post("/api/autonomous-backtest/trigger", json={})
        response = client.get("/api/autonomous-backtest/latest")
        data = response.json()
        assert data.get("run_id") is not None
        assert "instrument_results" in data
