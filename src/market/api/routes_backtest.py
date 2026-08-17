"""Backtest endpoints: simple backtest + autonomous backtest runner."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from market.api._engines import engines
from market.api._shared import _dataclass_to_dict, _generate_mock_instruments
from market.api.cache import ttl_cache
from market.backtest.autonomous import BacktestTrigger

router = APIRouter(prefix="/api", tags=["backtest"])


@router.get("/backtest/run")
@ttl_cache(ttl_seconds=600, key_prefix="backtest_run")
async def run_backtest(
    ticker: str = Query(...),
    strategy: str = Query("buy_hold", pattern="^(buy_hold|ma_crossover|conviction)$"),
    n_days: int = Query(100, ge=30, le=1000),
) -> dict[str, Any]:
    """Run a simple backtest with synthetic data.

    In production, this would load real OHLCV from the database.
    """
    import numpy as np
    import pandas as pd

    from market.backtest.engine import BacktestEngine
    from market.backtest.strategies import (
        BuyHoldStrategy,
        ConvictionStrategy,
        MACrossoverStrategy,
    )

    np.random.seed(42)
    dates = pd.date_range("2024-01-02", periods=n_days, freq="B")
    close = 100.0 * np.cumprod(1 + np.random.normal(0.001, 0.015, n_days))
    data = pd.DataFrame(
        {
            "open": close * 1.001,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n_days, 1_000_000.0),
        },
        index=dates,
    )

    strategies = {
        "buy_hold": BuyHoldStrategy(),
        "ma_crossover": MACrossoverStrategy(fast=20, slow=50),
        "conviction": ConvictionStrategy(),
    }
    strat = strategies[strategy]
    engine = BacktestEngine(initial_capital=100_000_000)
    result = engine.run(strat, data, ticker)

    return {
        "ticker": ticker,
        "strategy": strategy,
        "n_days": n_days,
        "metrics": result.metrics,
        "n_trades": len(result.trades),
        "equity_curve_sample": [
            {"date": str(d), "equity": round(v, 2)}
            for d, v in result.equity_curve.iloc[::max(1, n_days // 20)].items()
        ],
    }


# --- Autonomous backtest ---

autonomous_router = APIRouter(prefix="/api/autonomous-backtest", tags=["backtest"])


@autonomous_router.get("/status")
async def autonomous_backtest_status() -> dict[str, Any]:
    """Get autonomous backtest runner status."""
    return dict(engines.autonomous_backtest_runner.status_summary())


@autonomous_router.get("/runs")
async def autonomous_backtest_runs() -> dict[str, Any]:
    """List all autonomous backtest runs."""
    runs = engines.autonomous_backtest_runner.runs
    return {
        "total": len(runs),
        "runs": [
            {
                "run_id": r.run_id,
                "trigger": r.trigger.value,
                "status": r.status.value,
                "triggered_at": r.triggered_at,
                "completed_at": r.completed_at,
                "total_instruments": r.total_instruments,
                "successful": r.successful,
                "failed": r.failed,
                "skipped": r.skipped,
                "avg_sharpe": r.avg_sharpe,
                "best_sharpe": r.best_sharpe,
                "best_strategy": r.best_strategy,
                "worst_strategy": r.worst_strategy,
                "instruments_tested": r.instruments_tested,
                "agent_actions": r.agent_actions_proposed,
                "summary": r.summary,
                "duration_seconds": r.duration_seconds,
            }
            for r in runs
        ],
    }


@autonomous_router.get("/latest")
async def autonomous_backtest_latest() -> dict[str, Any]:
    """Get latest autonomous backtest run with full details."""
    latest = engines.autonomous_backtest_runner.latest
    if latest is None:
        return {"status": "idle", "message": "No autonomous backtest runs yet."}

    instrument_results = []
    for r in latest.instrument_results:
        ir: dict[str, Any] = {
            "ticker": r.ticker,
            "strategy": r.strategy.value,
            "status": r.status.value,
            "metrics": r.metrics,
            "trade_count": r.trade_count,
            "error": r.error,
        }
        if r.walk_forward:
            ir["walk_forward"] = {
                "oos_sharpe": r.walk_forward.oos_sharpe,
                "oos_return_pct": r.walk_forward.oos_return_pct,
                "consistency_pct": r.walk_forward.consistency_pct,
            }
        if r.monte_carlo:
            ir["monte_carlo"] = {
                "percentiles": r.monte_carlo.percentiles,
                "prob_loss_pct": r.monte_carlo.prob_loss_pct,
                "max_drawdown_pct": r.monte_carlo.max_drawdown_pct,
            }
        instrument_results.append(ir)

    return {
        "run_id": latest.run_id,
        "trigger": latest.trigger.value,
        "status": latest.status.value,
        "triggered_at": latest.triggered_at,
        "completed_at": latest.completed_at,
        "total_instruments": latest.total_instruments,
        "total_strategies": latest.total_strategies,
        "successful": latest.successful,
        "failed": latest.failed,
        "skipped": latest.skipped,
        "best_sharpe": latest.best_sharpe,
        "worst_sharpe": latest.worst_sharpe,
        "avg_sharpe": latest.avg_sharpe,
        "best_strategy": latest.best_strategy,
        "worst_strategy": latest.worst_strategy,
        "instruments_tested": latest.instruments_tested,
        "agent_actions_proposed": latest.agent_actions_proposed,
        "summary": latest.summary,
        "duration_seconds": latest.duration_seconds,
        "instrument_results": instrument_results,
    }


@autonomous_router.post("/trigger")
async def autonomous_backtest_trigger(body: dict[str, Any]) -> dict[str, Any]:
    """Force trigger an autonomous backtest run (admin only).

    Request body (all optional):
        trigger: str — trigger type (default: manual_force)
        instruments: dict[ticker, {open, high, low, close, volume, ...}] —
            if not provided, uses mock data
    """
    import pandas as pd

    trigger_str = body.get("trigger", "manual_force")
    try:
        trigger = BacktestTrigger(trigger_str)
    except ValueError:
        trigger = BacktestTrigger.MANUAL_FORCE

    instruments_raw = body.get("instruments")
    if instruments_raw and isinstance(instruments_raw, dict):
        instruments = {}
        for ticker, ohlcv in instruments_raw.items():
            if isinstance(ohlcv, dict):
                instruments[ticker] = pd.DataFrame(ohlcv)
                if "date" in instruments[ticker].columns:
                    instruments[ticker] = instruments[ticker].set_index("date")
            else:
                instruments[ticker] = ohlcv
    else:
        instruments = _generate_mock_instruments()

    run = engines.autonomous_backtest_runner.run(instruments, trigger=trigger)
    return dict(_dataclass_to_dict(run))
