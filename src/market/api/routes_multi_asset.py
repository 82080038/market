"""Multi-asset cross-market API routes (Gap #23).

Exposes the CrossMarketEngine results stored in ``relationship_matrix``
and provides on-demand analysis endpoints:

    GET  /api/multi-asset/correlations  — cross-market correlation list
    GET  /api/multi-asset/lead-lag      — lead-lag relationships (window=0)
    GET  /api/multi-asset/spillover     — volatility spillover (window=-1)
    GET  /api/multi-asset/heatmap       — correlation heatmap matrix
    POST /api/multi-asset/analyze       — on-demand analysis from returns data
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.db.engine import get_session
from market.db.models import RelationshipMatrix

router = APIRouter(prefix="/api/multi-asset", tags=["multi-asset"])


@router.get("/correlations")
async def correlations(
    session: Annotated[Session, Depends(get_session)],
    asset: str | None = Query(None, description="Filter by asset_a or asset_b"),
    min_corr: float = Query(0.0, description="Minimum absolute correlation"),
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """List cross-market correlations from relationship_matrix.

    Returns entries where window > 0 (rolling correlation windows).
    Use ``asset`` to filter for a specific ticker.
    """
    stmt = select(RelationshipMatrix).where(RelationshipMatrix.window > 0)
    if asset:
        stmt = stmt.where(
            (RelationshipMatrix.asset_a == asset)
            | (RelationshipMatrix.asset_b == asset),
        )
    stmt = stmt.order_by(RelationshipMatrix.correlation.desc()).limit(limit)

    rows = session.execute(stmt).scalars().all()
    results: list[dict[str, Any]] = []
    for r in rows:
        corr = float(r.correlation) if r.correlation is not None else 0.0
        if abs(corr) >= min_corr:
            results.append({
                "asset_a": r.asset_a,
                "asset_b": r.asset_b,
                "window": r.window,
                "correlation": corr,
                "lag": r.lag,
                "as_of": r.as_of.isoformat() if r.as_of else None,
            })
    return results


@router.get("/lead-lag")
async def lead_lag(
    session: Annotated[Session, Depends(get_session)],
    asset: str | None = Query(None),
    limit: int = Query(50, le=200),
) -> list[dict[str, Any]]:
    """List cross-market lead-lag relationships (window=0).

    These are computed by ``recompute_cross_market`` and stored with
    ``window=0`` as the cross-market marker. ``lag`` stores the optimal
    lead-lag in days.
    """
    stmt = select(RelationshipMatrix).where(RelationshipMatrix.window == 0)
    if asset:
        stmt = stmt.where(
            (RelationshipMatrix.asset_a == asset)
            | (RelationshipMatrix.asset_b == asset),
        )
    stmt = stmt.order_by(RelationshipMatrix.correlation.desc()).limit(limit)

    rows = session.execute(stmt).scalars().all()
    return [
        {
            "leader": r.asset_a,
            "follower": r.asset_b,
            "optimal_lag_days": r.lag,
            "correlation_at_lag": float(r.correlation) if r.correlation is not None else 0.0,
            "as_of": r.as_of.isoformat() if r.as_of else None,
        }
        for r in rows
    ]


@router.get("/spillover")
async def spillover(
    session: Annotated[Session, Depends(get_session)],
    asset: str | None = Query(None),
    limit: int = Query(50, le=200),
) -> list[dict[str, Any]]:
    """List volatility spillover results (window=-1).

    These are computed by ``recompute_cross_market`` and stored with
    ``window=-1``. ``correlation`` stores the spillover percentage
    (as a fraction, e.g. 0.35 = 35%).
    """
    stmt = select(RelationshipMatrix).where(RelationshipMatrix.window == -1)
    if asset:
        stmt = stmt.where(
            (RelationshipMatrix.asset_a == asset)
            | (RelationshipMatrix.asset_b == asset),
        )
    stmt = stmt.order_by(RelationshipMatrix.correlation.desc()).limit(limit)

    rows = session.execute(stmt).scalars().all()
    return [
        {
            "source": r.asset_a,
            "target": r.asset_b,
            "spillover_pct": float(r.correlation) * 100 if r.correlation is not None else 0.0,
            "as_of": r.as_of.isoformat() if r.as_of else None,
        }
        for r in rows
    ]


@router.get("/heatmap")
async def heatmap(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, dict[str, float]]:
    """Generate a correlation heatmap from stored relationship_matrix data.

    Returns a nested dict: {asset_a: {asset_b: correlation}}.
    Uses the latest correlation for each pair (highest window).
    """
    stmt = (
        select(
            RelationshipMatrix.asset_a,
            RelationshipMatrix.asset_b,
            RelationshipMatrix.correlation,
        )
        .where(RelationshipMatrix.window > 0)
        .order_by(RelationshipMatrix.window.desc())
    )
    rows = session.execute(stmt).all()

    seen: set[tuple[str, str]] = set()
    heatmap_data: dict[str, dict[str, float]] = {}

    for asset_a, asset_b, corr in rows:
        key = (asset_a, asset_b)
        if key in seen:
            continue
        seen.add(key)
        corr_val = float(corr) if corr is not None else 0.0

        if asset_a not in heatmap_data:
            heatmap_data[asset_a] = {}
        if asset_b not in heatmap_data:
            heatmap_data[asset_b] = {}
        heatmap_data[asset_a][asset_b] = corr_val
        heatmap_data[asset_b][asset_a] = corr_val
        heatmap_data[asset_a][asset_a] = 1.0
        heatmap_data[asset_b][asset_b] = 1.0

    return heatmap_data


class AnalyzeRequest(BaseModel):
    """Request body for on-demand cross-market analysis."""
    returns: dict[str, list[float]]
    volatilities: dict[str, list[float]] | None = None
    max_lag: int = 10
    min_samples: int = 30


@router.post("/analyze")
async def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    """Run on-demand cross-market analysis from provided returns data.

    Accepts returns (and optionally volatilities) as dicts mapping
    market name to a list of return values. Returns correlations,
    lead-lag, spillover, and heatmap data.
    """
    import pandas as pd

    from market.multi_asset.cross_market import CrossMarketEngine

    engine = CrossMarketEngine(min_samples=req.min_samples)

    returns = {k: pd.Series(v) for k, v in req.returns.items()}
    volatilities = None
    if req.volatilities:
        volatilities = {k: pd.Series(v) for k, v in req.volatilities.items()}

    report = engine.analyze(returns, volatilities, max_lag=req.max_lag)

    return {
        "correlations": [
            {
                "market_a": c.market_a,
                "market_b": c.market_b,
                "correlation": c.correlation,
                "p_value": c.p_value,
                "sample_size": c.sample_size,
            }
            for c in report.correlations
        ],
        "lead_lag": [
            {
                "leader": ll.leader,
                "follower": ll.follower,
                "optimal_lag": ll.optimal_lag,
                "correlation_at_lag": ll.correlation_at_lag,
                "significance": ll.significance,
            }
            for ll in report.lead_lag
        ],
        "spillovers": [
            {
                "source": s.source,
                "target": s.target,
                "spillover_pct": s.spillover_pct,
                "direction": s.direction,
            }
            for s in report.spillovers
        ],
        "heatmap": report.heatmap_data,
    }
