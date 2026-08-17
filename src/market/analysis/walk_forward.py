"""Walk-Forward Optimization — honest backtesting without look-ahead bias.

Splits timeline into consecutive (train, test) folds. On each fold,
optimizes parameters on in-sample data, then evaluates on out-of-sample.
Stitches OOS returns for an honest equity curve.

Usage:
    from market.analysis.walk_forward import WalkForwardOptimizer
    wfo = WalkForwardOptimizer(train_days=252, test_days=63)
    result = wfo.run(close_series, strategy_fn, param_grid, metric="sharpe")
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardResult:
    """Result of walk-forward optimization."""
    windows: list[dict] = field(default_factory=list)
    oos_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    oos_sharpe: float = 0.0
    oos_total_return: float = 0.0
    oos_max_drawdown: float = 0.0
    best_params_per_fold: list[dict] = field(default_factory=list)
    param_stability: float = 0.0  # 0=unstable, 1=perfectly stable


class WalkForwardOptimizer:
    """Rolling walk-forward optimizer for trading strategies.

    Args:
        train_days: Number of trading days in training window (default 252 = 1 year).
        test_days: Number of trading days in test window (default 63 = 1 quarter).
        embargo_days: Days to exclude after each test fold (prevent leakage).
    """

    def __init__(
        self,
        train_days: int = 252,
        test_days: int = 63,
        embargo_days: int = 5,
    ) -> None:
        self.train_days = train_days
        self.test_days = test_days
        self.embargo_days = embargo_days

    def _sharpe(self, returns: pd.Series) -> float:
        """Annualized Sharpe ratio."""
        r = returns.dropna()
        if len(r) < 20 or r.std() == 0:
            return -np.inf
        return np.sqrt(252) * r.mean() / r.std()

    def _max_drawdown(self, returns: pd.Series) -> float:
        """Maximum drawdown from cumulative returns."""
        cum = (1 + returns).cumprod()
        running_max = cum.cummax()
        dd = (cum - running_max) / running_max
        return float(dd.min())

    def run(
        self,
        close: pd.Series,
        strategy_fn,
        param_grid: dict[str, list],
        metric: str = "sharpe",
    ) -> WalkForwardResult:
        """Run walk-forward optimization.

        Args:
            close: Price series (indexed by date).
            strategy_fn: Function(close, **params) -> returns Series.
            param_grid: Dict of parameter names to lists of values.
            metric: Optimization metric ("sharpe" or "return").

        Returns:
            WalkForwardResult with per-fold and aggregate results.
        """
        log_ret = np.log(close / close.shift(1))

        # Generate parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        grid = list(itertools.product(*param_values))

        windows = []
        oos_returns_list = []
        best_params_per_fold = []

        start = self.train_days
        n = len(close)

        while start + self.test_days <= n:
            train_slice = slice(start - self.train_days, start)
            test_slice = slice(start, min(start + self.test_days, n))

            # Optimize on training window
            best_score = -np.inf
            best_params = None

            for params in grid:
                param_dict = dict(zip(param_names, params))
                try:
                    r = strategy_fn(close.iloc[train_slice], **param_dict)
                    if metric == "sharpe":
                        score = self._sharpe(r)
                    else:
                        score = r.sum()
                    if score > best_score:
                        best_score = score
                        best_params = param_dict
                except Exception:
                    continue

            if best_params is None:
                start += self.test_days + self.embargo_days
                continue

            # Evaluate on test window (with lookback for indicators)
            lookback = max(max(v) if isinstance(v, list) else v for v in param_grid.values())
            eval_slice = slice(max(0, start - lookback), test_slice.stop)

            try:
                oos_r = strategy_fn(close.iloc[eval_slice], **best_params)
                # Only keep returns from the test period
                test_index = close.index[test_slice]
                oos_r = oos_r.reindex(test_index).fillna(0)
                oos_returns_list.append(oos_r)
            except Exception as e:
                logger.warning("OOS evaluation failed: %s", e)

            window_info = {
                "train_start": str(close.index[train_slice.start].date()),
                "train_end": str(close.index[train_slice.stop - 1].date()),
                "test_start": str(close.index[test_slice.start].date()),
                "test_end": str(close.index[test_slice.stop - 1].date()),
                "best_params": best_params,
                "in_sample_metric": best_score,
            }
            windows.append(window_info)
            best_params_per_fold.append(best_params)

            start += self.test_days + self.embargo_days

        # Aggregate OOS results
        if oos_returns_list:
            oos_returns = pd.concat(oos_returns_list)
            oos_sharpe = self._sharpe(oos_returns)
            oos_total = float((1 + oos_returns).prod() - 1)
            oos_dd = self._max_drawdown(oos_returns)
        else:
            oos_returns = pd.Series(dtype=float)
            oos_sharpe = -np.inf
            oos_total = 0.0
            oos_dd = 0.0

        # Parameter stability: fraction of folds with same params as previous
        if len(best_params_per_fold) > 1:
            stable = sum(
                1 for i in range(1, len(best_params_per_fold))
                if best_params_per_fold[i] == best_params_per_fold[i - 1]
            )
            stability = stable / (len(best_params_per_fold) - 1)
        else:
            stability = 1.0

        result = WalkForwardResult(
            windows=windows,
            oos_returns=oos_returns,
            oos_sharpe=oos_sharpe,
            oos_total_return=oos_total,
            oos_max_drawdown=oos_dd,
            best_params_per_fold=best_params_per_fold,
            param_stability=stability,
        )

        logger.info(
            "Walk-forward complete: %d folds, OOS Sharpe=%.2f, return=%.2f%%, max_dd=%.2f%%, stability=%.0f%%",
            len(windows), oos_sharpe, oos_total * 100, oos_dd * 100, stability * 100,
        )

        return result
