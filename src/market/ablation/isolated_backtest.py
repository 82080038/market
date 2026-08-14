"""Isolated Backtester — run one engine in isolation, measure its contribution.

For each engine:
1. Run baseline (all engines disabled) → baseline metrics
2. Run with ONLY that engine enabled → isolated metrics
3. Compute delta = isolated - baseline
4. Statistical significance test (paired t-test on daily returns)

The "engine" here is abstracted as a signal provider that generates
directional signals (-1, 0, +1) for each trading day. The caller provides
a signal_fn that produces signals for a given OHLCV DataFrame.

This design allows testing any engine without needing the full
SignalEnhancer/MarketContext pipeline running.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats

from market.backtest.engine import BacktestEngine, BacktestResult
from market.backtest.strategies import Signal, Strategy

logger = logging.getLogger(__name__)

# Round-trip transaction cost (commission 0.15% + sales tax 0.1% + slippage 0.05%)
ROUND_TRIP_COST = 0.003


@dataclass
class IsolationResult:
    """Result of testing a single engine in isolation."""

    engine_name: str
    baseline_metrics: dict[str, float]
    isolated_metrics: dict[str, float]
    delta_metrics: dict[str, float] = field(default_factory=dict)
    p_value: float = 1.0
    t_statistic: float = 0.0
    is_significant: bool = False
    n_observations: int = 0
    baseline_returns: pd.Series | None = None
    isolated_returns: pd.Series | None = None
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def delta_sharpe(self) -> float:
        return self.delta_metrics.get("sharpe_ratio", 0.0)

    @property
    def delta_alpha(self) -> float:
        return self.delta_metrics.get("alpha", 0.0)

    @property
    def delta_win_rate(self) -> float:
        return self.delta_metrics.get("win_rate_pct", 0.0)


class SignalInjectionStrategy(Strategy):
    """Strategy that uses pre-computed signals from an external source.

    This allows us to test any engine's signals through the standard
    BacktestEngine without needing the full pipeline.
    """

    def __init__(self, signals: pd.Series) -> None:
        self._signals = signals

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        result = pd.Series(Signal.HOLD, index=data.index)
        for idx in data.index:
            if idx in self._signals.index:
                val = self._signals.loc[idx]
                if val > 0:
                    result.loc[idx] = Signal.BUY
                elif val < 0:
                    result.loc[idx] = Signal.SELL
        return result


def simulate_returns(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    cost_per_trade: float = ROUND_TRIP_COST,
) -> pd.Series:
    """Simulate daily returns from a signal series (vectorized).

    Position held during day t equals ``signal[t-1]`` (the signal decided at
    the end of day t-1 using information up to t-1). This avoids look-ahead:
    the return earned during day t (close[t-1] → close[t]) is applied to the
    position decided the prior evening.

    Transaction costs are modelled as turnover-proportional:
        turnover[t] = |position[t] - position[t-1]|
        cost[t]     = turnover[t] * (cost_per_trade / 2)

    ``cost_per_trade`` is a *round-trip* cost (buy + sell). A one-way trade
    (enter from cash or exit to cash) has turnover 1 and is charged half the
    round-trip cost. A flip (+1 → -1) has turnover 2 and is charged the full
    round-trip cost. A complete enter-then-exit cycle therefore accrues
    exactly ``cost_per_trade`` (not 2× as in the previous per-change model).

    The cost is borne by the return of the first day the new position is
    held (no off-by-one): the trade decided at end of t-1 affects day t.

    Args:
        ohlcv: DataFrame with 'close' column, DatetimeIndex.
        signals: Series of signals (-1, 0, +1) aligned to ohlcv index.
        cost_per_trade: Round-trip cost (buy + sell) per unit turnover of 2.

    Returns:
        Daily returns series (after cost).
    """
    close = ohlcv["close"].astype(float)
    returns = close.pct_change()

    signals = signals.reindex(returns.index).fillna(0)
    # Position for day t = signal decided at end of t-1 (no look-ahead)
    position = signals.shift(1).fillna(0)
    # Turnover = how many units were traded at the end of the previous day
    turnover = position.diff().abs().fillna(0)
    # One-way cost = half round-trip; flips (turnover 2) pay full round-trip
    cost = turnover * (cost_per_trade / 2.0)

    strategy_returns = position * returns - cost
    return strategy_returns.dropna()


def compute_metrics(returns: pd.Series, benchmark: pd.Series | None = None) -> dict[str, float]:
    """Compute performance metrics from a returns series.

    Args:
        returns: Daily returns series.
        benchmark: Optional benchmark returns for alpha/beta calculation.

    Returns:
        Dict with sharpe, sortino, max_drawdown, win_rate, alpha, beta.
    """
    if returns.empty or len(returns) < 2:
        return {
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "total_return_pct": 0.0,
            "annual_return_pct": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "n_days": 0,
        }

    cumulative = (1 + returns).cumprod()
    total_return = (cumulative.iloc[-1] - 1) * 100
    n_days = len(returns)
    annual_return = ((cumulative.iloc[-1]) ** (252 / n_days) - 1) * 100

    sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0

    downside = returns[returns < 0]
    sortino = (
        float(returns.mean() / downside.std() * np.sqrt(252))
        if len(downside) > 0 and downside.std() > 0
        else 0.0
    )

    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_dd = float(drawdown.min() * 100)

    win_rate = float((returns > 0).sum() / len(returns) * 100)

    alpha = 0.0
    beta = 0.0
    if benchmark is not None and not benchmark.empty:
        aligned = pd.DataFrame({"strategy": returns, "benchmark": benchmark}).dropna()
        if len(aligned) > 30 and aligned["benchmark"].std() > 0:
            beta = float(
                aligned.cov().iloc[0, 1] / aligned["benchmark"].var()
            )
            alpha = float(aligned["strategy"].mean() - beta * aligned["benchmark"].mean())
            alpha *= 252  # annualize

    return {
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate_pct": round(win_rate, 2),
        "total_return_pct": round(total_return, 2),
        "annual_return_pct": round(annual_return, 2),
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        "n_days": n_days,
    }


class IsolatedBacktester:
    """Run isolated backtest for a single engine.

    Workflow:
    1. Generate baseline signals (no engine) → baseline returns
    2. Generate engine signals → engine returns
    3. Compute delta metrics + statistical significance
    """

    def __init__(
        self,
        initial_capital: float = 100_000_000,
        cost_per_trade: float = ROUND_TRIP_COST,
    ) -> None:
        self.initial_capital = initial_capital
        self.cost_per_trade = cost_per_trade

    def run(
        self,
        engine_name: str,
        ohlcv: pd.DataFrame,
        baseline_signals: pd.Series,
        engine_signals: pd.Series,
        benchmark_returns: pd.Series | None = None,
    ) -> IsolationResult:
        """Run isolated backtest for one engine.

        Args:
            engine_name: Name of the engine being tested.
            ohlcv: OHLCV DataFrame with 'close' column.
            baseline_signals: Signals with engine disabled (-1, 0, +1).
            engine_signals: Signals with ONLY this engine enabled.
            benchmark_returns: Optional benchmark (IHSG) daily returns.

        Returns:
            IsolationResult with metrics and significance test.
        """
        t0 = datetime.now(timezone.utc)

        try:
            baseline_ret = simulate_returns(ohlcv, baseline_signals, self.cost_per_trade)
            engine_ret = simulate_returns(ohlcv, engine_signals, self.cost_per_trade)

            baseline_metrics = compute_metrics(baseline_ret, benchmark_returns)
            engine_metrics = compute_metrics(engine_ret, benchmark_returns)

            delta = {}
            for key in engine_metrics:
                if key == "n_days":
                    continue
                delta[key] = round(engine_metrics[key] - baseline_metrics[key], 4)

            # Paired t-test on daily returns
            aligned = pd.DataFrame({
                "engine": engine_ret,
                "baseline": baseline_ret,
            }).dropna()

            p_value = 1.0
            t_stat = 0.0
            significant = False

            if len(aligned) > 30:
                t_stat, p_value = stats.ttest_rel(aligned["engine"], aligned["baseline"])
                t_stat = float(t_stat)
                p_value = float(p_value)
                # Handle nan (identical series → t-test returns nan)
                if not np.isfinite(p_value):
                    p_value = 1.0
                if not np.isfinite(t_stat):
                    t_stat = 0.0
                significant = p_value < 0.05

            return IsolationResult(
                engine_name=engine_name,
                baseline_metrics=baseline_metrics,
                isolated_metrics=engine_metrics,
                delta_metrics=delta,
                p_value=round(p_value, 6),
                t_statistic=round(t_stat, 4),
                is_significant=significant,
                n_observations=len(aligned),
                baseline_returns=baseline_ret,
                isolated_returns=engine_ret,
                duration_seconds=(datetime.now(timezone.utc) - t0).total_seconds(),
            )

        except Exception as e:
            logger.error("Isolated backtest failed for %s: %s", engine_name, e)
            return IsolationResult(
                engine_name=engine_name,
                baseline_metrics={},
                isolated_metrics={},
                error=str(e),
                duration_seconds=(datetime.now(timezone.utc) - t0).total_seconds(),
            )

    def run_full_backtest(
        self,
        engine_name: str,
        ohlcv: pd.DataFrame,
        engine_signals: pd.Series,
    ) -> BacktestResult:
        """Run full event-driven backtest with BacktestEngine.

        This is more realistic than vectorized simulate_returns because it
        models next-bar-open execution, lot sizes, and separate commission/tax.

        Args:
            engine_name: Name for logging.
            ohlcv: OHLCV DataFrame.
            engine_signals: Signal series (-1, 0, +1).

        Returns:
            BacktestResult with equity curve, trades, and metrics.
        """
        strategy = SignalInjectionStrategy(engine_signals)
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            max_position_pct=0.25,
        )
        return engine.run(strategy=strategy, data=ohlcv, ticker=engine_name)
