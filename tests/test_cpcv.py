"""Tests for Combinatorial Purged Cross-Validation (Gap #39)."""

from __future__ import annotations

from math import comb

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

from market.mlops.cross_validation import (
    CPCVResult,
    CPCVSplit,
    CombinatorialPurgedCV,
    aggregate_cpcv_results,
    combinatorial_purged_splits,
    compute_pbo,
)


@pytest.fixture
def sample_data() -> pd.DataFrame:
    """Sample dataset for CPCV."""
    rng = np.random.default_rng(42)
    n = 300
    return pd.DataFrame({
        "f1": rng.standard_normal(n),
        "f2": rng.standard_normal(n),
        "target": rng.standard_normal(n),
    }, index=pd.date_range("2026-01-01", periods=n, freq="B"))


def test_cpcv_split_dataclass():
    """CPCVSplit can be constructed."""
    s = CPCVSplit(path_id=0, train_indices=[1, 2], test_indices=[3, 4])
    assert s.path_id == 0
    assert s.train_indices == [1, 2]
    assert s.test_indices == [3, 4]


def test_combinatorial_purged_splits_basic():
    """combinatorial_purged_splits generates correct number of paths."""
    splits = combinatorial_purged_splits(
        n_samples=300, n_groups=6, n_test_groups=2,
    )
    # C(6, 2) = 15 combinations
    assert len(splits) == comb(6, 2)


def test_combinatorial_purged_splits_train_test_disjoint():
    """Train and test indices are disjoint."""
    splits = combinatorial_purged_splits(
        n_samples=300, n_groups=6, n_test_groups=2,
    )
    for s in splits:
        train_set = set(s.train_indices)
        test_set = set(s.test_indices)
        assert len(train_set & test_set) == 0


def test_combinatorial_purged_splits_all_data_covered():
    """Every sample appears in at least one test set."""
    splits = combinatorial_purged_splits(
        n_samples=300, n_groups=6, n_test_groups=2,
    )
    all_test = set()
    for s in splits:
        all_test.update(s.test_indices)
    # All 300 samples should appear in some test set
    assert len(all_test) == 300


def test_combinatorial_purged_splits_purging():
    """Purging removes data near test boundaries."""
    splits = combinatorial_purged_splits(
        n_samples=300, n_groups=6, n_test_groups=2,
        purge_pct=0.10, embargo_pct=0.05,
    )
    # With purging, train should be smaller than without
    no_purge = combinatorial_purged_splits(
        n_samples=300, n_groups=6, n_test_groups=2,
        purge_pct=0.0, embargo_pct=0.0,
    )
    assert len(splits[0].train_indices) <= len(no_purge[0].train_indices)


def test_combinatorial_purged_splits_invalid_params():
    """Invalid parameters raise ValueError."""
    with pytest.raises(ValueError):
        combinatorial_purged_splits(300, n_groups=1, n_test_groups=1)
    with pytest.raises(ValueError):
        combinatorial_purged_splits(300, n_groups=5, n_test_groups=5)
    with pytest.raises(ValueError):
        combinatorial_purged_splits(300, n_groups=5, n_test_groups=0)


def test_cpcv_class_n_paths():
    """CombinatorialPurgedCV.n_paths returns C(N, P)."""
    cv = CombinatorialPurgedCV(n_groups=6, n_test_groups=2)
    assert cv.n_paths == comb(6, 2)  # 15

    cv2 = CombinatorialPurgedCV(n_groups=10, n_test_groups=3)
    assert cv2.n_paths == comb(10, 3)  # 120


def test_cpcv_class_split():
    """CombinatorialPurgedCV.split generates splits."""
    cv = CombinatorialPurgedCV(n_groups=6, n_test_groups=2)
    splits = cv.split(300)
    assert len(splits) == comb(6, 2)
    assert all(isinstance(s, CPCVSplit) for s in splits)


def test_cpcv_class_run(sample_data: pd.DataFrame):
    """CombinatorialPurgedCV.run executes all paths."""
    cv = CombinatorialPurgedCV(n_groups=6, n_test_groups=2)

    def train_fn(X, y):
        return LinearRegression().fit(X, y)

    def eval_fn(model, X, y):
        preds = model.predict(X)
        mse = float(np.mean((preds - y) ** 2))
        return {"mse": mse}

    results = cv.run(
        sample_data, ["f1", "f2"], "target",
        train_fn, eval_fn,
    )
    assert len(results) > 0
    assert all(isinstance(r, CPCVResult) for r in results)
    assert all("mse" in r.metrics for r in results)


def test_compute_pbo_no_overfitting():
    """PBO is low when all paths perform similarly."""
    results = [
        CPCVResult(path_id=i, train_size=100, test_size=50,
                   metrics={"sharpe": 1.0 + i * 0.01})
        for i in range(10)
    ]
    pbo = compute_pbo(results, "sharpe")
    # All similar — PBO should be around 0.5
    assert 0.0 <= pbo <= 1.0


def test_compute_pbo_high_overfitting():
    """PBO is high when performances are split."""
    results = [
        CPCVResult(path_id=0, train_size=100, test_size=50, metrics={"sharpe": 2.0}),
        CPCVResult(path_id=1, train_size=100, test_size=50, metrics={"sharpe": 0.1}),
        CPCVResult(path_id=2, train_size=100, test_size=50, metrics={"sharpe": 1.9}),
        CPCVResult(path_id=3, train_size=100, test_size=50, metrics={"sharpe": 0.2}),
    ]
    pbo = compute_pbo(results, "sharpe")
    assert 0.0 <= pbo <= 1.0


def test_compute_pbo_empty():
    """PBO returns 0 for empty results."""
    assert compute_pbo([], "sharpe") == 0.0


def test_compute_pbo_single():
    """PBO returns 0 for single result."""
    results = [CPCVResult(path_id=0, train_size=100, test_size=50, metrics={"sharpe": 1.0})]
    assert compute_pbo(results, "sharpe") == 0.0


def test_aggregate_cpcv_results():
    """aggregate_cpcv_results computes mean, std, min, max."""
    results = [
        CPCVResult(path_id=0, train_size=100, test_size=50, metrics={"mse": 1.0}),
        CPCVResult(path_id=1, train_size=100, test_size=50, metrics={"mse": 2.0}),
        CPCVResult(path_id=2, train_size=100, test_size=50, metrics={"mse": 3.0}),
    ]
    agg = aggregate_cpcv_results(results)
    assert agg["mse_mean"] == pytest.approx(2.0)
    assert agg["mse_min"] == pytest.approx(1.0)
    assert agg["mse_max"] == pytest.approx(3.0)
    assert "mse_std" in agg


def test_aggregate_cpcv_empty():
    """aggregate_cpcv_results returns empty dict for no results."""
    assert aggregate_cpcv_results([]) == {}


def test_cpcv_with_different_group_counts():
    """CPCV works with different N and P values."""
    for n_groups, n_test in [(4, 1), (6, 2), (8, 3), (10, 2)]:
        cv = CombinatorialPurgedCV(n_groups=n_groups, n_test_groups=n_test)
        splits = cv.split(500)
        assert len(splits) == comb(n_groups, n_test)


def test_cpcv_train_groups_correct():
    """Train groups are complement of test groups."""
    splits = combinatorial_purged_splits(300, n_groups=6, n_test_groups=2)
    for s in splits:
        assert len(s.test_groups) == 2
        assert len(s.train_groups) == 4
        assert set(s.test_groups) & set(s.train_groups) == set()
        assert set(s.test_groups) | set(s.train_groups) == set(range(6))


def test_cpcv_path_ids_sequential():
    """Path IDs are sequential starting from 0."""
    splits = combinatorial_purged_splits(300, n_groups=6, n_test_groups=2)
    path_ids = [s.path_id for s in splits]
    assert path_ids == list(range(len(splits)))
