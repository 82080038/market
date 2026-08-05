"""Autonomous backtest runner (pustaka/29, pustaka/67, pustaka/86).

Runs backtests automatically across:
- All instruments (IDX, global, multi-asset)
- All strategies (buy_hold, ma_crossover, conviction)
- Walk-forward validation + Monte Carlo risk
- Triggered by: data changes, market events, user activity, scheduled EOD

No user intervention required. Results feed into SelfEvolutionAgent
for autonomous decisions (retrain, adjust params, promote/demote strategy).

The runner is the bridge between backtest infrastructure and the
AI self-evolution & autonomous layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from market.backtest.analysis import (
    MonteCarloResult,
    WalkForwardResult,
    monte_carlo,
    walk_forward,
)
from market.backtest.engine import BacktestEngine, BacktestResult
from market.backtest.strategies import (
    BuyHoldStrategy,
    ConvictionStrategy,
    MACrossoverStrategy,
    Strategy,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BacktestTrigger(Enum):
    """What triggered the autonomous backtest run."""

    SCHEDULED_EOD = "scheduled_eod"        # Scheduled end-of-day
    DATA_CHANGE = "data_change"            # New OHLCV data arrived
    MARKET_EVENT = "market_event"          # Global market regime shift
    USER_ACTIVITY = "user_activity"        # User changed config/portfolio
    DRIFT_DETECTED = "drift_detected"      # Model drift detected
    MANUAL_FORCE = "manual_force"          # Force re-run (admin)


class StrategyType(Enum):
    """Available strategies for autonomous backtesting."""

    BUY_HOLD = "buy_hold"
    MA_CROSSOVER = "ma_crossover"
    CONVICTION = "conviction"


class BacktestStatus(Enum):
    """Status of an autonomous backtest run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InstrumentBacktestResult:
    """Backtest result for a single instrument + strategy."""

    ticker: str
    strategy: StrategyType
    metrics: dict[str, float] = field(default_factory=dict)
    walk_forward: WalkForwardResult | None = None
    monte_carlo: MonteCarloResult | None = None
    trade_count: int = 0
    status: BacktestStatus = BacktestStatus.COMPLETED
    error: str = ""


@dataclass
class AutonomousBacktestRun:
    """A complete autonomous backtest run across all instruments."""

    run_id: str
    triggered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    trigger: BacktestTrigger = BacktestTrigger.SCHEDULED_EOD
    status: BacktestStatus = BacktestStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    instrument_results: list[InstrumentBacktestResult] = field(default_factory=list)
    summary: str = ""
    total_instruments: int = 0
    total_strategies: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    best_sharpe: float = 0.0
    worst_sharpe: float = 0.0
    avg_sharpe: float = 0.0
    best_strategy: str = ""
    worst_strategy: str = ""
    instruments_tested: list[str] = field(default_factory=list)
    agent_actions_proposed: list[dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Autonomous Backtest Runner
# ---------------------------------------------------------------------------


class AutonomousBacktestRunner:
    """Runs backtests autonomously across all instruments and strategies.

    No user intervention needed. Triggers:
    - SCHEDULED_EOD: After IDX close (17:30 WIB)
    - DATA_CHANGE: When new OHLCV data arrives
    - MARKET_EVENT: Global market regime shift detected
    - USER_ACTIVITY: User changed config/portfolio (re-validate strategies)
    - DRIFT_DETECTED: Model drift → re-backtest affected instruments

    Results feed into SelfEvolutionAgent for autonomous decisions.
    """

    _run_counter = 0

    def __init__(
        self,
        engine: BacktestEngine | None = None,
        strategies: list[StrategyType] | None = None,
        walk_forward_train: int = 252,
        walk_forward_test: int = 63,
        monte_carlo_sims: int = 500,
    ) -> None:
        self.engine = engine or BacktestEngine()
        self.strategies = strategies or [
            StrategyType.BUY_HOLD,
            StrategyType.MA_CROSSOVER,
            StrategyType.CONVICTION,
        ]
        self.wf_train = walk_forward_train
        self.wf_test = walk_forward_test
        self.mc_sims = monte_carlo_sims
        self._runs: list[AutonomousBacktestRun] = []
        self._latest: AutonomousBacktestRun | None = None

    @property
    def runs(self) -> list[AutonomousBacktestRun]:
        """All backtest runs."""
        return self._runs

    @property
    def latest(self) -> AutonomousBacktestRun | None:
        """Latest backtest run."""
        return self._latest

    def _make_strategy(self, strategy_type: StrategyType) -> Strategy:
        """Create strategy instance from type."""
        if strategy_type == StrategyType.BUY_HOLD:
            return BuyHoldStrategy()
        elif strategy_type == StrategyType.MA_CROSSOVER:
            return MACrossoverStrategy()
        elif strategy_type == StrategyType.CONVICTION:
            return ConvictionStrategy()
        else:
            return BuyHoldStrategy()

    def run(
        self,
        instruments: dict[str, pd.DataFrame],
        trigger: BacktestTrigger = BacktestTrigger.SCHEDULED_EOD,
        agent: Any | None = None,
    ) -> AutonomousBacktestRun:
        """Run autonomous backtest across all instruments and strategies.

        Args:
            instruments: Dict of ticker → OHLCV DataFrame.
            trigger: What triggered this run.
            agent: Optional SelfEvolutionAgent to feed results into.

        Returns:
            AutonomousBacktestRun with all results.
        """
        AutonomousBacktestRunner._run_counter += 1
        run = AutonomousBacktestRun(
            run_id=f"ABT-{AutonomousBacktestRunner._run_counter:05d}",
            trigger=trigger,
            status=BacktestStatus.RUNNING,
            started_at=datetime.now(UTC).isoformat(),
            total_instruments=len(instruments),
            total_strategies=len(self.strategies),
        )

        start_time = datetime.now(UTC)

        all_sharpes: list[float] = []
        strategy_sharpes: dict[str, list[float]] = {}

        for ticker, data in instruments.items():
            if data is None or data.empty:
                run.instrument_results.append(InstrumentBacktestResult(
                    ticker=ticker,
                    strategy=StrategyType.BUY_HOLD,
                    status=BacktestStatus.SKIPPED,
                    error="No data",
                ))
                run.skipped += 1
                continue

            run.instruments_tested.append(ticker)

            for strat_type in self.strategies:
                result = self._backtest_instrument(ticker, data, strat_type)
                run.instrument_results.append(result)

                if result.status == BacktestStatus.COMPLETED:
                    run.successful += 1
                    sharpe = result.metrics.get("sharpe_ratio", 0.0)
                    all_sharpes.append(sharpe)
                    strategy_sharpes.setdefault(strat_type.value, []).append(sharpe)
                elif result.status == BacktestStatus.FAILED:
                    run.failed += 1
                else:
                    run.skipped += 1

        # Aggregate
        if all_sharpes:
            run.best_sharpe = round(max(all_sharpes), 3)
            run.worst_sharpe = round(min(all_sharpes), 3)
            run.avg_sharpe = round(float(np.mean(all_sharpes)), 3)

        if strategy_sharpes:
            best_strat = max(
                strategy_sharpes.keys(),
                key=lambda s: float(np.mean(strategy_sharpes[s])),
            )
            worst_strat = min(
                strategy_sharpes.keys(),
                key=lambda s: float(np.mean(strategy_sharpes[s])),
            )
            run.best_strategy = best_strat
            run.worst_strategy = worst_strat

        # Feed into agent if provided
        if agent is not None:
            run.agent_actions_proposed = self._feed_agent(run, agent)

        run.status = BacktestStatus.COMPLETED
        run.completed_at = datetime.now(UTC).isoformat()
        run.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()
        run.summary = self._build_summary(run)

        self._runs.append(run)
        self._latest = run
        return run

    def _backtest_instrument(
        self,
        ticker: str,
        data: pd.DataFrame,
        strategy_type: StrategyType,
    ) -> InstrumentBacktestResult:
        """Run backtest + walk-forward + Monte Carlo for one instrument."""
        try:
            strategy = self._make_strategy(strategy_type)

            # Main backtest
            bt_result = self.engine.run(strategy, data, ticker)

            # Walk-forward
            wf_result: WalkForwardResult | None = None
            if len(data) >= self.wf_train + self.wf_test:
                wf_result = walk_forward(
                    strategy, data,
                    train_size=self.wf_train,
                    test_size=self.wf_test,
                )

            # Monte Carlo (from trade returns)
            mc_result: MonteCarloResult | None = None
            trade_returns = self._extract_trade_returns(bt_result)
            if trade_returns:
                mc_result = monte_carlo(
                    trade_returns,
                    n_simulations=self.mc_sims,
                )

            return InstrumentBacktestResult(
                ticker=ticker,
                strategy=strategy_type,
                metrics=bt_result.metrics,
                walk_forward=wf_result,
                monte_carlo=mc_result,
                trade_count=len(bt_result.trades),
                status=BacktestStatus.COMPLETED,
            )

        except Exception as e:
            return InstrumentBacktestResult(
                ticker=ticker,
                strategy=strategy_type,
                status=BacktestStatus.FAILED,
                error=str(e),
            )

    def _extract_trade_returns(self, result: BacktestResult) -> list[float]:
        """Extract per-trade returns from backtest result."""
        if not result.trades:
            return []

        # Pair buy/sell trades to compute returns
        returns: list[float] = []
        buys: list[Any] = []

        for trade in result.trades:
            if trade.side == "buy":
                buys.append(trade)
            elif trade.side == "sell" and buys:
                buy = buys.pop(0)
                if buy.price > 0:
                    ret = (trade.price - buy.price) / buy.price
                    returns.append(ret)

        return returns

    def _feed_agent(self, run: AutonomousBacktestRun, agent: Any) -> list[dict[str, Any]]:
        """Feed backtest results into SelfEvolutionAgent for autonomous decisions.

        The agent observes backtest metrics and may propose actions:
        - RETRAIN_MODEL if strategy performance degraded
        - ADJUST_PARAMS if parameters need tuning
        - ESCALATE_HUMAN if critical issue found
        """
        actions: list[dict[str, Any]] = []

        # Collect metrics for agent observation
        metrics: dict[str, float] = {
            "avg_sharpe": run.avg_sharpe,
            "best_sharpe": run.best_sharpe,
            "worst_sharpe": run.worst_sharpe,
            "total_instruments": float(run.total_instruments),
            "successful": float(run.successful),
            "failed": float(run.failed),
        }

        # Collect per-strategy performance
        strategy_perf: dict[str, list[float]] = {}
        for result in run.instrument_results:
            if result.status == BacktestStatus.COMPLETED:
                key = f"{result.strategy.value}_sharpe"
                strategy_perf.setdefault(key, []).append(
                    result.metrics.get("sharpe_ratio", 0.0),
                )

        # Average per strategy
        model_performance: dict[str, float] = {}
        for key, values in strategy_perf.items():
            model_performance[key] = float(np.mean(values))

        # Detect drift-like signals from walk-forward consistency
        drift_signals: dict[str, float] = {}
        for result in run.instrument_results:
            if result.walk_forward and result.walk_forward.consistency_pct < 50:
                drift_signals[result.ticker] = 0.3  # PSI-like signal

        # Run agent cycle
        try:
            cycle = agent.run_full_cycle(
                metrics=metrics,
                drift_signals=drift_signals if drift_signals else None,
                model_performance=model_performance,
                errors=[
                    r.error for r in run.instrument_results
                    if r.status == BacktestStatus.FAILED
                ],
            )

            if cycle.decision:
                actions.append({
                    "cycle_id": cycle.cycle_id,
                    "action": cycle.decision.action_type.value,
                    "description": cycle.decision.description,
                    "confidence": cycle.decision.confidence,
                    "requires_human": cycle.decision.requires_human_approval,
                    "status": cycle.status.value,
                })
        except Exception:
            pass  # Agent errors don't fail the backtest

        return actions

    def _build_summary(self, run: AutonomousBacktestRun) -> str:
        """Build human-readable summary."""
        parts = [
            f"Run {run.run_id} ({run.trigger.value}):",
            f"{run.successful}/{run.total_instruments * run.total_strategies} backtests successful",
            f"avg Sharpe={run.avg_sharpe:.3f}",
            f"best={run.best_strategy} worst={run.worst_strategy}",
        ]
        if run.agent_actions_proposed:
            actions = [a["action"] for a in run.agent_actions_proposed]
            parts.append(f"agent actions: {', '.join(actions)}")
        return " | ".join(parts)

    def trigger_data_change(
        self,
        instruments: dict[str, pd.DataFrame],
        changed_tickers: list[str] | None = None,
        agent: Any | None = None,
    ) -> AutonomousBacktestRun:
        """Trigger backtest on data change.

        Only re-tests instruments whose data changed (if specified).
        """
        if changed_tickers:
            subset = {
                t: instruments[t] for t in changed_tickers if t in instruments
            }
        else:
            subset = instruments

        return self.run(subset, trigger=BacktestTrigger.DATA_CHANGE, agent=agent)

    def trigger_market_event(
        self,
        instruments: dict[str, pd.DataFrame],
        event_description: str = "",
        agent: Any | None = None,
    ) -> AutonomousBacktestRun:
        """Trigger backtest on global market event."""
        return self.run(instruments, trigger=BacktestTrigger.MARKET_EVENT, agent=agent)

    def trigger_user_activity(
        self,
        instruments: dict[str, pd.DataFrame],
        activity: str = "",
        agent: Any | None = None,
    ) -> AutonomousBacktestRun:
        """Trigger backtest on user activity (config change, portfolio update)."""
        return self.run(instruments, trigger=BacktestTrigger.USER_ACTIVITY, agent=agent)

    def status_summary(self) -> dict[str, Any]:
        """Get runner status summary."""
        total_runs = len(self._runs)
        if total_runs == 0:
            return {
                "total_runs": 0,
                "latest_run": None,
                "status": "idle",
            }

        latest = self._latest
        return {
            "total_runs": total_runs,
            "latest_run": latest.run_id if latest else None,
            "latest_trigger": latest.trigger.value if latest else None,
            "latest_status": latest.status.value if latest else None,
            "latest_avg_sharpe": latest.avg_sharpe if latest else 0.0,
            "latest_best_strategy": latest.best_strategy if latest else "",
            "latest_instruments": len(latest.instruments_tested) if latest else 0,
            "latest_agent_actions": len(latest.agent_actions_proposed) if latest else 0,
            "latest_duration_s": latest.duration_seconds if latest else 0.0,
            "latest_summary": latest.summary if latest else "",
        }


# ---------------------------------------------------------------------------
# Scheduler integration
# ---------------------------------------------------------------------------


def register_autonomous_backtest_tasks(
    scheduler: Any,
    runner: AutonomousBacktestRunner,
    instruments_provider: Any,
    agent: Any | None = None,
) -> list[str]:
    """Register autonomous backtest tasks into the DailyScheduler.

    Args:
        scheduler: DailyScheduler instance.
        runner: AutonomousBacktestRunner instance.
        instruments_provider: Callable that returns dict[ticker, DataFrame].
        agent: Optional SelfEvolutionAgent.

    Returns:
        List of registered task IDs.
    """
    task_ids: list[str] = []

    # Task 1: EOD backtest (after IDX close)
    def eod_backtest() -> None:
        instruments = (
            instruments_provider() if callable(instruments_provider) else instruments_provider
        )
        runner.run(instruments, trigger=BacktestTrigger.SCHEDULED_EOD, agent=agent)

    scheduler.register_task(
        task_id="autonomous_backtest_eod",
        name="Autonomous Backtest EOD",
        func=eod_backtest,
        schedule="EOD",
        time_of_day="17:30",
    )
    task_ids.append("autonomous_backtest_eod")

    # Task 2: Data change backtest (hourly check)
    def data_change_backtest() -> None:
        instruments = (
            instruments_provider() if callable(instruments_provider) else instruments_provider
        )
        runner.trigger_data_change(instruments, agent=agent)

    scheduler.register_task(
        task_id="autonomous_backtest_data",
        name="Autonomous Backtest on Data Change",
        func=data_change_backtest,
        schedule="hourly",
        time_of_day="09:00",
    )
    task_ids.append("autonomous_backtest_data")

    return task_ids
