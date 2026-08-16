"""Tests for Almgren-Chriss market impact model (Gap #40)."""

from __future__ import annotations

import numpy as np
import pytest

from market.execution.market_impact import (
    AlmgrenChrissModel,
    ExecutionTrajectory,
    ImpactEstimate,
    ImpactParams,
)


@pytest.fixture
def model() -> AlmgrenChrissModel:
    return AlmgrenChrissModel()


def test_impact_params_defaults():
    """ImpactParams has sensible defaults."""
    p = ImpactParams()
    assert p.eta > 0
    assert p.gamma > 0
    assert p.sigma > 0
    assert p.lam > 0


def test_compute_trajectory_basic(model: AlmgrenChrissModel):
    """compute_trajectory returns a valid trajectory."""
    traj = model.compute_trajectory(
        total_shares=10000, horizon=5, initial_price=100.0,
    )
    assert isinstance(traj, ExecutionTrajectory)
    assert traj.total_shares == 10000
    assert traj.execution_time == 5.0
    assert len(traj.time_points) == 6  # N+1 points
    assert len(traj.shares_remaining) == 6
    assert len(traj.execution_rate) == 5  # N rates


def test_compute_trajectory_starts_at_total(model: AlmgrenChrissModel):
    """Trajectory starts at total shares."""
    traj = model.compute_trajectory(total_shares=10000, horizon=5)
    assert traj.shares_remaining[0] == 10000


def test_compute_trajectory_ends_at_zero(model: AlmgrenChrissModel):
    """Trajectory ends at zero shares."""
    traj = model.compute_trajectory(total_shares=10000, horizon=5)
    assert abs(traj.shares_remaining[-1]) < 0.01  # Should be ~0


def test_compute_trajectory_monotonic_decreasing(model: AlmgrenChrissModel):
    """Shares remaining is monotonically decreasing."""
    traj = model.compute_trajectory(total_shares=10000, horizon=10)
    for i in range(len(traj.shares_remaining) - 1):
        assert traj.shares_remaining[i] >= traj.shares_remaining[i + 1]


def test_compute_trajectory_execution_rate_positive(model: AlmgrenChrissModel):
    """Execution rates are non-negative."""
    traj = model.compute_trajectory(total_shares=10000, horizon=5)
    assert all(r >= 0 for r in traj.execution_rate)


def test_compute_trajectory_total_executed(model: AlmgrenChrissModel):
    """Sum of execution rates * tau equals total shares."""
    traj = model.compute_trajectory(total_shares=10000, horizon=5)
    total_executed = sum(traj.execution_rate)  # tau=1
    assert abs(total_executed - 10000) < 1.0  # Allow small numerical error


def test_estimate_impact_basic(model: AlmgrenChrissModel):
    """estimate_impact returns valid estimate."""
    est = model.estimate_impact(
        total_shares=10000, avg_price=100.0, horizon_days=5,
    )
    assert isinstance(est, ImpactEstimate)
    assert est.total_shares == 10000
    assert est.avg_price == 100.0
    assert est.execution_horizon_days == 5
    assert est.temporary_impact_bps >= 0
    assert est.permanent_impact_bps >= 0
    assert est.total_impact_bps == est.temporary_impact_bps + est.permanent_impact_bps
    assert est.expected_cost > 0
    assert est.optimal_strategy in ("twap", "vwap", "almgren_chriss")


def test_estimate_impact_zero_shares(model: AlmgrenChrissModel):
    """estimate_impact with zero shares returns zeros."""
    est = model.estimate_impact(
        total_shares=0, avg_price=100.0, horizon_days=5,
    )
    assert est.temporary_impact_bps == 0
    assert est.permanent_impact_bps == 0
    assert est.expected_cost == 0


def test_estimate_impact_large_order(model: AlmgrenChrissModel):
    """Large order has higher impact than small order."""
    small = model.estimate_impact(
        total_shares=100, avg_price=100.0, horizon_days=5,
    )
    large = model.estimate_impact(
        total_shares=100000, avg_price=100.0, horizon_days=5,
    )
    assert large.total_impact_bps > small.total_impact_bps


def test_estimate_impact_with_adv(model: AlmgrenChrissModel):
    """estimate_impact with ADV selects appropriate strategy."""
    # Large order relative to ADV
    est = model.estimate_impact(
        total_shares=100000, avg_price=100.0, horizon_days=5,
        adv=500000,  # 20% participation
    )
    assert est.optimal_strategy == "almgren_chriss"

    # Small order relative to ADV
    est_small = model.estimate_impact(
        total_shares=1000, avg_price=100.0, horizon_days=5,
        adv=1000000,  # 0.1% participation
    )
    assert est_small.optimal_strategy == "vwap"


def test_efficient_frontier(model: AlmgrenChrissModel):
    """efficient_frontier returns multiple points."""
    frontier = model.efficient_frontier(
        total_shares=10000, avg_price=100.0, horizon_days=5, n_points=10,
    )
    assert len(frontier) == 10
    assert all("lambda" in p for p in frontier)
    assert all("expected_cost" in p for p in frontier)
    assert all("risk" in p for p in frontier)


def test_efficient_frontier_restores_lambda(model: AlmgrenChrissModel):
    """efficient_frontier restores original lambda after computation."""
    original = model.params.lam
    model.efficient_frontier(10000, 100.0, n_points=5)
    assert model.params.lam == original


def test_participation_rate():
    """participation_rate computes correctly."""
    assert AlmgrenChrissModel.participation_rate(1000, 10000) == 0.1
    assert AlmgrenChrissModel.participation_rate(0, 10000) == 0.0
    assert AlmgrenChrissModel.participation_rate(1000, 0) == 0.0


def test_kyle_lambda():
    """kyle_lambda computes correctly."""
    assert AlmgrenChrissModel.kyle_lambda(1.0, 1000) == 0.001
    assert AlmgrenChrissModel.kyle_lambda(0, 1000) == 0.0
    assert AlmgrenChrissModel.kyle_lambda(1.0, 0) == 0.0


def test_trajectory_with_longer_horizon(model: AlmgrenChrissModel):
    """Longer horizon reduces temporary impact."""
    short = model.estimate_impact(10000, 100.0, horizon_days=1)
    long = model.estimate_impact(10000, 100.0, horizon_days=20)
    # Longer horizon should have lower temporary impact (slower execution)
    assert long.temporary_impact_bps <= short.temporary_impact_bps


def test_higher_risk_aversion_faster_execution():
    """Higher risk aversion leads to faster execution."""
    conservative = AlmgrenChrissModel(ImpactParams(lam=1e-8))
    aggressive = AlmgrenChrissModel(ImpactParams(lam=1e-2))

    traj_c = conservative.compute_trajectory(10000, horizon=5)
    traj_a = aggressive.compute_trajectory(10000, horizon=5)

    # Aggressive (higher lambda) should execute more in early periods
    assert traj_a.execution_rate[0] >= traj_c.execution_rate[0]


def test_zero_kappa_linear_trajectory():
    """When kappa=0 (eta very large), trajectory is linear (TWAP)."""
    # Very high eta makes kappa ~ 0
    model = AlmgrenChrissModel(ImpactParams(eta=1e10, lam=1e-6))
    traj = model.compute_trajectory(10000, horizon=5)
    # Linear trajectory: each step should be ~2000
    rates = traj.execution_rate
    # All rates should be approximately equal (TWAP)
    assert max(rates) - min(rates) < 100  # Small variance
