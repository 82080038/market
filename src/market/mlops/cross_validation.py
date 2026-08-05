"""Walk-forward & purged k-fold cross-validation (pustaka/23 §4, pustaka/51 §4).

Implements:
- Walk-forward validation with expanding/rolling window
- Purged k-fold CV (removes data near train/test boundary to prevent leakage)
- Embargo period support
- Combinatorial purged cross-validation (CPCV) stub
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
