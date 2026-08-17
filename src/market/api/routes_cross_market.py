"""API routes for cross-market coefficients.

Provides endpoints for Granger causality and asymmetric correlation data:
- GET /api/cross-market — list all coefficients
- GET /api/cross-market/{source_ticker} — coefficients for a source ticker
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from market.db.engine import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cross-market", tags=["cross-market"])


@router.get("")
def list_coefficients(
    limit: int = Query(100, ge=1, le=1000),
    min_pvalue: float = Query(0.05, ge=0.0, le=1.0),
):
    """List cross-market Granger causality coefficients."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT source_ticker, target_ticker, lag, p_value, f_statistic, "
                "corr_up, corr_down, regime, updated_at "
                "FROM cross_market_coefficients "
                "WHERE p_value <= :p "
                "ORDER BY p_value ASC LIMIT :n"
            ),
            {"p": min_pvalue, "n": limit},
        ).all()
        if not rows:
            raise HTTPException(404, "No coefficients found")
        return [
            {
                "source_ticker": r[0], "target_ticker": r[1], "lag": r[2],
                "p_value": float(r[3]) if r[3] else None,
                "f_statistic": float(r[4]) if r[4] else None,
                "corr_up": float(r[5]) if r[5] else None,
                "corr_down": float(r[6]) if r[6] else None,
                "regime": r[7], "updated_at": str(r[8]) if r[8] else None,
            }
            for r in rows
        ]


@router.get("/{source_ticker}")
def get_coefficients(source_ticker: str):
    """Get cross-market coefficients originating from a source ticker."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT source_ticker, target_ticker, lag, p_value, f_statistic, "
                "corr_up, corr_down, regime, updated_at "
                "FROM cross_market_coefficients "
                "WHERE source_ticker = :t "
                "ORDER BY p_value ASC"
            ),
            {"t": source_ticker},
        ).all()
        if not rows:
            raise HTTPException(404, f"No coefficients for {source_ticker}")
        return [
            {
                "source_ticker": r[0], "target_ticker": r[1], "lag": r[2],
                "p_value": float(r[3]) if r[3] else None,
                "f_statistic": float(r[4]) if r[4] else None,
                "corr_up": float(r[5]) if r[5] else None,
                "corr_down": float(r[6]) if r[6] else None,
                "regime": r[7], "updated_at": str(r[8]) if r[8] else None,
            }
            for r in rows
        ]
