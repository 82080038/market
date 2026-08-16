"""Strategy selector API routes (Gap #13).

Exposes strategy assignment results from ``strategy_assignment`` table:

    GET /api/strategy/assignment/{ticker}  — get strategy for a ticker
    GET /api/strategy/assignments         — list all strategy assignments
    GET /api/strategy/classes             — list available strategy classes
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.db.engine import get_session
from market.db.models import StrategyAssignment

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/assignment/{ticker}")
async def get_assignment(
    ticker: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get strategy assignment for a specific ticker.

    Returns the best strategy, strategy class, rationale, and in-sample
    performance metrics from the ``strategy_assignment`` table.
    """
    row = session.execute(
        select(StrategyAssignment).where(StrategyAssignment.ticker == ticker)
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(404, f"No strategy assignment found for {ticker}")

    return {
        "ticker": row.ticker,
        "best_strategy": row.best_strategy,
        "strategy_class": row.strategy_class,
        "strategy_rationale": row.strategy_rationale,
        "in_sample_sharpe": float(row.in_sample_sharpe) if row.in_sample_sharpe is not None else None,
        "in_sample_max_dd": float(row.in_sample_max_dd) if row.in_sample_max_dd is not None else None,
        "in_sample_winrate": float(row.in_sample_winrate) if row.in_sample_winrate is not None else None,
        "oos_sharpe": float(row.oos_sharpe) if row.oos_sharpe is not None else None,
        "oos_max_dd": float(row.oos_max_dd) if row.oos_max_dd is not None else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/assignments")
async def list_assignments(
    session: Annotated[Session, Depends(get_session)],
    strategy_class: str | None = Query(None, description="Filter by strategy class"),
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """List all strategy assignments, optionally filtered by strategy class."""
    stmt = select(StrategyAssignment)
    if strategy_class:
        stmt = stmt.where(StrategyAssignment.strategy_class == strategy_class)
    stmt = stmt.limit(limit)

    rows = session.execute(stmt).scalars().all()
    return [
        {
            "ticker": r.ticker,
            "best_strategy": r.best_strategy,
            "strategy_class": r.strategy_class,
            "in_sample_sharpe": float(r.in_sample_sharpe) if r.in_sample_sharpe is not None else None,
            "in_sample_winrate": float(r.in_sample_winrate) if r.in_sample_winrate is not None else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.get("/classes")
async def list_classes() -> dict[str, list[str]]:
    """List available strategy classes and their member strategies."""
    from market.analysis.strategy_selector import STRATEGY_CLASSES

    return {cls: strategies for cls, strategies in STRATEGY_CLASSES.items()}
