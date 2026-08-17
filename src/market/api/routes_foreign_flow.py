"""API routes for foreign flow data.

Provides endpoints for foreign investor flow analysis:
- GET /api/foreign-flow/summary — aggregate flow by date
- GET /api/foreign-flow/{ticker} — per-ticker flow history
- GET /api/foreign-flow/top — top net buy/sell for latest date
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import text

from market.db.engine import get_engine

router = APIRouter(prefix="/api/foreign-flow", tags=["foreign-flow"])


@router.get("/summary")
async def foreign_flow_summary(days: int = Query(30, ge=1, le=365)):
    """Get aggregate foreign flow summary by date."""
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT date,
                   COUNT(*) as n_stocks,
                   SUM(foreign_buy)::float as fb,
                   SUM(foreign_sell)::float as fs,
                   SUM(foreign_net)::float as fn,
                   SUM(CASE WHEN foreign_net > 0 THEN 1 ELSE 0 END) as net_buy_count,
                   SUM(CASE WHEN foreign_net < 0 THEN 1 ELSE 0 END) as net_sell_count
            FROM foreign_flow
            WHERE date >= :cutoff
            GROUP BY date ORDER BY date DESC
        """), {"cutoff": cutoff}).all()

    return {
        "dates": [str(r[0]) for r in rows],
        "foreign_buy": [r[2] or 0 for r in rows],
        "foreign_sell": [r[3] or 0 for r in rows],
        "foreign_net": [r[4] or 0 for r in rows],
        "net_buy_count": [r[5] or 0 for r in rows],
        "net_sell_count": [r[6] or 0 for r in rows],
    }


@router.get("/{ticker}")
async def foreign_flow_ticker(ticker: str, days: int = Query(60, ge=1, le=365)):
    """Get foreign flow history for a specific ticker."""
    if not ticker.endswith(".JK"):
        ticker = f"{ticker}.JK"
    cutoff = date.today() - timedelta(days=days)
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT date, foreign_buy, foreign_sell, foreign_net,
                   domestic_buy, domestic_sell, domestic_net
            FROM foreign_flow
            WHERE ticker = :ticker AND date >= :cutoff
            ORDER BY date DESC
        """), {"ticker": ticker, "cutoff": cutoff}).all()

    return {
        "ticker": ticker,
        "history": [
            {
                "date": str(r[0]),
                "foreign_buy": float(r[1] or 0),
                "foreign_sell": float(r[2] or 0),
                "foreign_net": float(r[3] or 0),
                "domestic_buy": float(r[4] or 0),
                "domestic_sell": float(r[5] or 0),
                "domestic_net": float(r[6] or 0),
            }
            for r in rows
        ],
    }


@router.get("/top/{direction}")
async def foreign_flow_top(direction: str, limit: int = Query(20, ge=1, le=100)):
    """Get top foreign net buy/sell for latest date."""
    if direction not in ("buy", "sell"):
        return {"error": "direction must be 'buy' or 'sell'"}

    with get_engine().connect() as conn:
        latest = conn.execute(text("SELECT MAX(date) FROM foreign_flow")).scalar()
        if not latest:
            return {"error": "No data"}

        if direction == "buy":
            rows = conn.execute(text("""
                SELECT ticker, foreign_buy, foreign_sell, foreign_net
                FROM foreign_flow WHERE date = :d AND foreign_net > 0
                ORDER BY foreign_net DESC LIMIT :limit
            """), {"d": latest, "limit": limit}).all()
        else:
            rows = conn.execute(text("""
                SELECT ticker, foreign_buy, foreign_sell, foreign_net
                FROM foreign_flow WHERE date = :d AND foreign_net < 0
                ORDER BY foreign_net ASC LIMIT :limit
            """), {"d": latest, "limit": limit}).all()

    return {
        "date": str(latest),
        "direction": direction,
        "stocks": [
            {
                "ticker": r[0],
                "foreign_buy": float(r[1] or 0),
                "foreign_sell": float(r[2] or 0),
                "foreign_net": float(r[3] or 0),
            }
            for r in rows
        ],
    }
