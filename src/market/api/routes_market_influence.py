"""API routes for market influence knowledge base.

Provides endpoints for the market_influence_kb table:
- GET /api/market-influence — list all influence mappings
- GET /api/market-influence/{influence_type} — filter by type
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from market.db.engine import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-influence", tags=["market-influence"])


@router.get("")
def list_influences(
    limit: int = Query(100, ge=1, le=1000),
    influence_type: str | None = Query(None, description="Filter by influence type"),
):
    """List market influence KB entries."""
    with get_engine().connect() as conn:
        if influence_type:
            rows = conn.execute(
                text(
                    "SELECT id, source_ticker, target_ticker, influence_type, "
                    "strength, direction, description, created_at "
                    "FROM market_influence_kb "
                    "WHERE influence_type = :t "
                    "ORDER BY strength DESC LIMIT :n"
                ),
                {"t": influence_type, "n": limit},
            ).all()
        else:
            rows = conn.execute(
                text(
                    "SELECT id, source_ticker, target_ticker, influence_type, "
                    "strength, direction, description, created_at "
                    "FROM market_influence_kb "
                    "ORDER BY strength DESC LIMIT :n"
                ),
                {"n": limit},
            ).all()
        if not rows:
            raise HTTPException(404, "No influence entries found")
        return [
            {
                "id": r[0], "source_ticker": r[1], "target_ticker": r[2],
                "influence_type": r[3], "strength": float(r[4]) if r[4] else None,
                "direction": r[5], "description": r[6],
                "created_at": str(r[7]) if r[7] else None,
            }
            for r in rows
        ]


@router.get("/types")
def list_influence_types():
    """List all unique influence types in the KB."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT influence_type, COUNT(*) as cnt "
                "FROM market_influence_kb "
                "GROUP BY influence_type ORDER BY cnt DESC"
            )
        ).all()
        if not rows:
            raise HTTPException(404, "No influence types found")
        return [
            {"influence_type": r[0], "count": r[1]}
            for r in rows
        ]
