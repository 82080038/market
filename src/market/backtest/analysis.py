"""Walk-forward analysis, Monte Carlo, and Deflated Sharpe Ratio.

(pustaka/29, pustaka/85)

- Walk-forward: split data into train/test windows, run strategy
  on each, aggregate out-of-sample performance.
- Monte Carlo: resample trade returns with replacement to estimate
  distribution of final equity.
- Deflated Sharpe Ratio: adjust Sharpe for multiple testing bias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from market.backtest.engine import BacktestEngine, BacktestResult

if TYPE_CHECKING:
    import pandas as pd

    from market.backtest.strategies import Strategy


@dataclass
class WalkForwardResult:
    """Walk-forward analysis result."""

    window_results: list[BacktestResult] = field(default_factory=list)
    oos_sharpe: float = 0.0
    oos_return_pct: float = 0.0
    consistency_pct: float = 0.0  # % of windows with positive return


def walk_forward(
    strategy: Strategy,
    data: pd.DataFrame,
    train_size: int = 252,
    test_size: int = 63,
    step: int = 63,
) -> WalkForwardResult:
    """Run walk-forward analysis.

    Args:
        strategy: Strategy to test.
        data: Full OHLCV DataFrame.
        train_size: Training window size (days).
        test_size: Out-of-sample test window size (days).
        step: Step size between windows (days).

    Returns:
        WalkForwardResult with per-window results and aggregated metrics.
    """
    if len(data) < train_size + test_size:
        return WalkForwardResult()

    engine = BacktestEngine()
    results: list[BacktestResult] = []
    sharpes: list[float] = []
    returns: list[float] = []

    start = 0
    while start + train_size + test_size <= len(data):
        test_data = data.iloc[start + train_size : start + train_size + test_size]
        result = engine.run(strategy, test_data)
        results.append(result)

        if result.metrics:
            sharpes.append(result.metrics.get("sharpe_ratio", 0.0))
            returns.append(result.metrics.get("total_return_pct", 0.0))

        start += step

    oos_sharpe = float(np.mean(sharpes)) if sharpes else 0.0
    oos_return = float(np.mean(returns)) if returns else 0.0
    positive = sum(1 for r in returns if r > 0)
    consistency = (positive / len(returns) * 100) if returns else 0.0

    return WalkForwardResult(
        window_results=results,
        oos_sharpe=round(oos_sharpe, 3),
        oos_return_pct=round(oos_return, 2),
        consistency_pct=round(consistency, 2),
    )


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation result."""

    percentiles: dict[str, float] = field(default_factory=dict)
    mean_final_equity: float = 0.0
    std_final_equity: float = 0.0
    prob_loss_pct: float = 0.0
    max_drawdown_pct: float = 0.0


def monte_carlo(
    trade_returns: list[float],
    initial_capital: float = 100_000_000,
    n_simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    """Run Monte Carlo simulation by resampling trade returns.

    Args:
        trade_returns: List of per-trade returns (decimal, e.g. 0.02 = 2%).
        initial_capital: Starting capital.
        n_simulations: Number of simulations.
        seed: Random seed for reproducibility.

    Returns:
        MonteCarloResult with percentile distribution and risk metrics.
    """
    if not trade_returns:
        return MonteCarloResult()

    rng = np.random.RandomState(seed)
    n_trades = len(trade_returns)
    returns_array = np.array(trade_returns)

    final_equities: list[float] = []
    max_drawdowns: list[float] = []

    for _ in range(n_simulations):
        sampled = rng.choice(returns_array, size=n_trades, replace=True)
        equity = initial_capital
        peak = equity
        max_dd = 0.0

        for r in sampled:
            equity *= (1 + r)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        final_equities.append(equity)
        max_drawdowns.append(max_dd)

    final_array = np.array(final_equities)
    dd_array = np.array(max_drawdowns)

    percentiles = {
        "p5": round(float(np.percentile(final_array, 5)), 2),
        "p25": round(float(np.percentile(final_array, 25)), 2),
        "p50": round(float(np.percentile(final_array, 50)), 2),
        "p75": round(float(np.percentile(final_array, 75)), 2),
        "p95": round(float(np.percentile(final_array, 95)), 2),
    }

    prob_loss = float(
        np.sum(final_array < initial_capital) / n_simulations * 100,
    )

    return MonteCarloResult(
        percentiles=percentiles,
        mean_final_equity=round(float(np.mean(final_array)), 2),
        std_final_equity=round(float(np.std(final_array)), 2),
        prob_loss_pct=round(prob_loss, 2),
        max_drawdown_pct=round(float(np.mean(dd_array)), 2),
    )


def deflated_sharpe_ratio(
    sharpe: float,
    n_trials: int,
    sample_size: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Compute Deflated Sharpe Ratio (Bailey & López de Prado 2014).

    Adjusts Sharpe for multiple testing and non-normality.

    Args:
        sharpe: Observed Sharpe ratio.
        n_trials: Number of strategies tested.
        sample_size: Number of observations.
        skewness: Return distribution skewness.
        kurtosis: Return distribution kurtosis (3 = normal).

    Returns:
        Deflated Sharpe Ratio (probability-adjusted).
    """
    if sample_size < 2 or n_trials < 1:
        return 0.0

    # Expected maximum Sharpe under null (multiple testing)
    euler_mascheroni = 0.5772156649
    expected_max_sharpe = (
        np.sqrt(2 * np.log(n_trials))
        * (1 - euler_mascheroni / np.sqrt(2 * np.log(n_trials)))
    )

    # Variance of Sharpe estimator (non-normal adjustment)
    var_sharpe = (
        (1 - skewness * sharpe + (kurtosis - 1) / 4 * sharpe**2)
        / (sample_size - 1)
    )

    if var_sharpe <= 0:
        return 0.0

    # Deflated Sharpe
    dsr = (sharpe - expected_max_sharpe) / np.sqrt(var_sharpe)

    return round(float(dsr), 4)
