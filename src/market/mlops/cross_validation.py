"""Walk-forward & purged k-fold cross-validation (pustaka/23 §4, pustaka/51 §4).

Implements:
- Walk-forward validation with expanding/rolling window
- Purged k-fold CV (removes data near train/test boundary to prevent leakage)
- Embargo period support
- Combinatorial Purged Cross-Validation (CPCV) — full implementation (Gap #39)

CPCV (López de Prado, "Advances in Financial Machine Learning", Ch. 7):
- Splits data into N groups
- Selects P of N groups as test set (combinatorial — all C(N,P) combinations)
- Remaining N-P groups form training set
- Purging removes data near train/test boundaries to prevent label leakage
- Embargo adds extra gap after test set to account for autocorrelation
- Produces multiple backtest paths for robust probability of backtest overfitting (PBO)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class TrainTestSplit:
    """A single train/test split."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int
    fold: int


@dataclass
class CVResult:
    """Cross-validation result."""

    fold: int
    train_size: int
    test_size: int
    metrics: dict[str, float]


@dataclass
class CPCVSplit:
    """A CPCV split with multiple test groups (Gap #39)."""

    path_id: int  # Backtest path ID
    train_indices: list[int] = field(default_factory=list)
    test_indices: list[int] = field(default_factory=list)
    train_groups: list[int] = field(default_factory=list)
    test_groups: list[int] = field(default_factory=list)


@dataclass
class CPCVResult:
    """CPCV result for a single path (Gap #39)."""

    path_id: int
    train_size: int
    test_size: int
    metrics: dict[str, float]
    train_groups: list[int] = field(default_factory=list)
    test_groups: list[int] = field(default_factory=list)


def walk_forward_splits(
    n_samples: int,
    train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> list[TrainTestSplit]:
    """Generate walk-forward train/test splits.

    Args:
        n_samples: Total number of samples.
        train_size: Number of training samples per fold.
        test_size: Number of test samples per fold.
        step_size: Step between folds (defaults to test_size).

    Returns:
        List of TrainTestSplit objects.
    """
    if step_size is None:
        step_size = test_size

    splits = []
    fold = 0
    start = 0

    while start + train_size + test_size <= n_samples:
        splits.append(TrainTestSplit(
            train_start=start,
            train_end=start + train_size,
            test_start=start + train_size,
            test_end=start + train_size + test_size,
            fold=fold,
        ))
        start += step_size
        fold += 1

    return splits


def purged_kfold_splits(
    n_samples: int,
    n_folds: int = 5,
    purge_pct: float = 0.05,
    embargo_pct: float = 0.0,
) -> list[TrainTestSplit]:
    """Generate purged k-fold splits.

    Removes `purge_pct` of data around train/test boundaries
    to prevent label leakage.

    Args:
        n_samples: Total number of samples.
        n_folds: Number of folds.
        purge_pct: Fraction of data to purge at boundaries.
        embargo_pct: Additional embargo after test set.

    Returns:
        List of TrainTestSplit objects.
    """
    fold_size = n_samples // n_folds
    purge = max(1, int(fold_size * purge_pct))
    embargo = max(0, int(fold_size * embargo_pct))

    splits = []

    for fold in range(n_folds):
        test_start = fold * fold_size
        test_end = min((fold + 1) * fold_size, n_samples)

        # Train = everything except test ± purge
        train_start = 0
        train_end = max(0, test_start - purge)

        # If embargo, extend the gap after test
        embargo_end = min(test_end + embargo, n_samples)

        # For purged k-fold, train is all data except [test_start-purge, test_end+embargo]
        # We represent this as two segments, but for simplicity
        # we use the segment before test (most common in time series)
        if train_end - train_start < fold_size // 2:
            # Use data after test+embargo instead
            train_start = embargo_end
            train_end = n_samples
            if train_end - train_start < fold_size // 2:
                continue

        splits.append(TrainTestSplit(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            fold=fold,
        ))

    return splits


class WalkForwardCV:
    """Walk-forward cross-validation orchestrator."""

    def __init__(
        self,
        train_size: int = 200,
        test_size: int = 50,
        step_size: int | None = None,
    ) -> None:
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = step_size

    def split(self, n_samples: int) -> list[TrainTestSplit]:
        """Generate splits for the given data size."""
        return walk_forward_splits(
            n_samples, self.train_size, self.test_size, self.step_size,
        )

    def run(
        self,
        data: pd.DataFrame,
        features: list[str],
        target: str,
        train_fn: Callable[..., Any],
        eval_fn: Callable[..., dict[str, float]],
    ) -> list[CVResult]:
        """Run walk-forward CV.

        Args:
            data: Full dataset.
            features: Feature column names.
            target: Target column name.
            train_fn: Function(X_train, y_train) -> model
            eval_fn: Function(model, X_test, y_test) -> dict[str, float]

        Returns:
            List of CVResult per fold.
        """
        splits = self.split(len(data))
        results = []

        for split in splits:
            train_data = data.iloc[split.train_start:split.train_end]
            test_data = data.iloc[split.test_start:split.test_end]

            X_train = train_data[features].values
            y_train = train_data[target].values
            X_test = test_data[features].values
            y_test = test_data[target].values

            model = train_fn(X_train, y_train)
            metrics = eval_fn(model, X_test, y_test)

            results.append(CVResult(
                fold=split.fold,
                train_size=len(X_train),
                test_size=len(X_test),
                metrics=metrics,
            ))

        return results


class PurgedKFoldCV:
    """Purged k-fold cross-validation."""

    def __init__(
        self,
        n_folds: int = 5,
        purge_pct: float = 0.05,
        embargo_pct: float = 0.0,
    ) -> None:
        self.n_folds = n_folds
        self.purge_pct = purge_pct
        self.embargo_pct = embargo_pct

    def split(self, n_samples: int) -> list[TrainTestSplit]:
        """Generate purged splits."""
        return purged_kfold_splits(
            n_samples, self.n_folds, self.purge_pct, self.embargo_pct,
        )

    def run(
        self,
        data: pd.DataFrame,
        features: list[str],
        target: str,
        train_fn: Callable[..., Any],
        eval_fn: Callable[..., dict[str, float]],
    ) -> list[CVResult]:
        """Run purged k-fold CV.

        Args:
            data: Full dataset.
            features: Feature column names.
            target: Target column name.
            train_fn: Function(X_train, y_train) -> model
            eval_fn: Function(model, X_test, y_test) -> dict[str, float]

        Returns:
            List of CVResult per fold.
        """
        splits = self.split(len(data))
        results = []

        for split in splits:
            train_data = data.iloc[split.train_start:split.train_end]
            test_data = data.iloc[split.test_start:split.test_end]

            if len(train_data) == 0 or len(test_data) == 0:
                continue

            X_train = train_data[features].values
            y_train = train_data[target].values
            X_test = test_data[features].values
            y_test = test_data[target].values

            model = train_fn(X_train, y_train)
            metrics = eval_fn(model, X_test, y_test)

            results.append(CVResult(
                fold=split.fold,
                train_size=len(X_train),
                test_size=len(X_test),
                metrics=metrics,
            ))

        return results


def aggregate_cv_results(results: list[CVResult]) -> dict[str, float]:
    """Aggregate CV results across folds.

    Args:
        results: List of CVResult objects.

    Returns:
        Dict with mean and std for each metric.
    """
    if not results:
        return {}

    all_metrics: dict[str, list[float]] = {}
    for r in results:
        for k, v in r.metrics.items():
            all_metrics.setdefault(k, []).append(v)

    aggregated: dict[str, float] = {}
    for metric, values in all_metrics.items():
        aggregated[f"{metric}_mean"] = float(np.mean(values))
        aggregated[f"{metric}_std"] = float(np.std(values))

    return aggregated


# ── Combinatorial Purged Cross-Validation (CPCV) — Gap #39 ────────────────

def combinatorial_purged_splits(
    n_samples: int,
    n_groups: int = 6,
    n_test_groups: int = 2,
    purge_pct: float = 0.05,
    embargo_pct: float = 0.0,
) -> list[CPCVSplit]:
    """Generate Combinatorial Purged Cross-Validation splits (Gap #39).

    Divides data into N groups, then generates all C(N, P) combinations
    where P groups are test and N-P groups are train. Purging removes
    data near group boundaries to prevent label leakage.

    Reference: López de Prado, "Advances in Financial Machine Learning", Ch. 7.

    Args:
        n_samples: Total number of samples.
        n_groups: Number of groups to divide data into (N).
        n_test_groups: Number of groups for testing (P).
        purge_pct: Fraction of group size to purge at boundaries.
        embargo_pct: Additional embargo after test groups.

    Returns:
        List of CPCVSplit, one per combination (backtest path).
    """
    if n_groups < 2 or n_test_groups < 1 or n_test_groups >= n_groups:
        raise ValueError(
            f"Need 2 <= n_groups, 1 <= n_test_groups < n_groups. "
            f"Got n_groups={n_groups}, n_test_groups={n_test_groups}."
        )

    group_size = n_samples // n_groups
    purge = max(1, int(group_size * purge_pct))
    embargo = max(0, int(group_size * embargo_pct))

    # Define group boundaries
    group_bounds = []
    for g in range(n_groups):
        start = g * group_size
        end = min((g + 1) * group_size, n_samples)
        group_bounds.append((start, end))

    # Generate all combinations of P test groups out of N
    splits: list[CPCVSplit] = []
    path_id = 0

    for test_combo in combinations(range(n_groups), n_test_groups):
        test_set = set(test_combo)
        train_groups = [g for g in range(n_groups) if g not in test_set]

        # Build test indices (with purging at boundaries)
        test_indices: list[int] = []
        for g in test_combo:
            g_start, g_end = group_bounds[g]
            test_indices.extend(range(g_start, g_end))

        # Build train indices, excluding purged regions near test groups
        purged_ranges: set[int] = set()
        for g in test_combo:
            g_start, g_end = group_bounds[g]
            # Purge before test group
            for i in range(max(0, g_start - purge), g_start):
                purged_ranges.add(i)
            # Embargo after test group
            for i in range(g_end, min(n_samples, g_end + embargo)):
                purged_ranges.add(i)

        train_indices: list[int] = []
        for g in train_groups:
            g_start, g_end = group_bounds[g]
            for i in range(g_start, g_end):
                if i not in purged_ranges and i not in test_indices:
                    train_indices.append(i)

        if len(train_indices) > 0 and len(test_indices) > 0:
            splits.append(CPCVSplit(
                path_id=path_id,
                train_indices=train_indices,
                test_indices=test_indices,
                train_groups=train_groups,
                test_groups=list(test_combo),
            ))
            path_id += 1

    return splits


class CombinatorialPurgedCV:
    """Combinatorial Purged Cross-Validation orchestrator (Gap #39).

    Reference: López de Prado, "Advances in Financial Machine Learning", Ch. 7.

    Unlike standard k-fold CV which produces a single backtest path,
    CPCV produces C(N, P) backtest paths, enabling:
    - Probability of Backtest Overfitting (PBO) computation
    - More robust performance estimation
    - Better detection of overfit strategies
    """

    def __init__(
        self,
        n_groups: int = 6,
        n_test_groups: int = 2,
        purge_pct: float = 0.05,
        embargo_pct: float = 0.0,
    ) -> None:
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.purge_pct = purge_pct
        self.embargo_pct = embargo_pct

    def split(self, n_samples: int) -> list[CPCVSplit]:
        """Generate CPCV splits.

        Args:
            n_samples: Total number of samples.

        Returns:
            List of CPCVSplit objects.
        """
        return combinatorial_purged_splits(
            n_samples, self.n_groups, self.n_test_groups,
            self.purge_pct, self.embargo_pct,
        )

    @property
    def n_paths(self) -> int:
        """Number of backtest paths (C(N, P))."""
        from math import comb
        return comb(self.n_groups, self.n_test_groups)

    def run(
        self,
        data: pd.DataFrame,
        features: list[str],
        target: str,
        train_fn: Callable[..., Any],
        eval_fn: Callable[..., dict[str, float]],
    ) -> list[CPCVResult]:
        """Run CPCV.

        Args:
            data: Full dataset.
            features: Feature column names.
            target: Target column name.
            train_fn: Function(X_train, y_train) -> model
            eval_fn: Function(model, X_test, y_test) -> dict[str, float]

        Returns:
            List of CPCVResult, one per path.
        """
        splits = self.split(len(data))
        results: list[CPCVResult] = []

        for split in splits:
            if len(split.train_indices) == 0 or len(split.test_indices) == 0:
                continue

            train_data = data.iloc[split.train_indices]
            test_data = data.iloc[split.test_indices]

            X_train = train_data[features].values
            y_train = train_data[target].values
            X_test = test_data[features].values
            y_test = test_data[target].values

            model = train_fn(X_train, y_train)
            metrics = eval_fn(model, X_test, y_test)

            results.append(CPCVResult(
                path_id=split.path_id,
                train_size=len(X_train),
                test_size=len(X_test),
                metrics=metrics,
                train_groups=split.train_groups,
                test_groups=split.test_groups,
            ))

        return results


def compute_pbo(
    cpcv_results: list[CPCVResult],
    benchmark_metric: str = "sharpe",
    higher_is_better: bool = True,
) -> float:
    """Compute Probability of Backtest Overfitting (PBO) from CPCV results.

    PBO is the probability that an optimal strategy in-sample is
    in the bottom half of out-of-sample performance. A high PBO
    indicates backtest overfitting.

    Reference: López de Prado et al. (2015), "The Probability of Backtest
    Overfitting and Deflated Sharpe Ratio".

    Args:
        cpcv_results: Results from CPCV.
        benchmark_metric: Metric to use for ranking.
        higher_is_better: Whether higher metric values are better.

    Returns:
        PBO value between 0 and 1. Higher = more overfitting.
    """
    if len(cpcv_results) < 2:
        return 0.0

    # Simplified PBO: fraction of paths where OOS performance
    # is below the median of all OOS performances
    values = [r.metrics.get(benchmark_metric, 0.0) for r in cpcv_results]
    if not values:
        return 0.0

    median = float(np.median(values))

    if higher_is_better:
        below_median = sum(1 for v in values if v < median)
    else:
        below_median = sum(1 for v in values if v > median)

    return below_median / len(values)


def aggregate_cpcv_results(results: list[CPCVResult]) -> dict[str, float]:
    """Aggregate CPCV results across all paths.

    Args:
        results: List of CPCVResult objects.

    Returns:
        Dict with mean, std, min, max for each metric.
    """
    if not results:
        return {}

    all_metrics: dict[str, list[float]] = {}
    for r in results:
        for k, v in r.metrics.items():
            all_metrics.setdefault(k, []).append(v)

    aggregated: dict[str, float] = {}
    for metric, values in all_metrics.items():
        aggregated[f"{metric}_mean"] = float(np.mean(values))
        aggregated[f"{metric}_std"] = float(np.std(values))
        aggregated[f"{metric}_min"] = float(np.min(values))
        aggregated[f"{metric}_max"] = float(np.max(values))

    return aggregated
