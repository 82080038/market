"""API routes for instrument behavior profiles.

Provides endpoints for instrument profiling data:
- GET /api/instrument-profiles — list all profiles
- GET /api/instrument-profiles/{ticker} — single ticker profile
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from market.db.engine import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instrument-profiles", tags=["instrument-profiles"])


@router.get("")
def list_profiles(limit: int = 100):
    """List all instrument behavior profiles."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT ticker, regime, volatility_quartile, trend_strength, "
                "mean_reversion_strength, autocorr_lag1, autocorr_lag5, "
                "win_rate_dow_mon, win_rate_dow_fri, avg_spread_pct, "
                "earnings_drift_days, earnings_avg_move, "
                "updated_at "
                "FROM instrument_behavior_profiles "
                "ORDER BY updated_at DESC LIMIT :n"
            ),
            {"n": limit},
        ).all()
        if not rows:
            raise HTTPException(404, "No profiles found")
        return [
            {
                "ticker": r[0], "regime": r[1], "volatility_quartile": r[2],
                "trend_strength": float(r[3]) if r[3] else None,
                "mean_reversion_strength": float(r[4]) if r[4] else None,
                "autocorr_lag1": float(r[5]) if r[5] else None,
                "autocorr_lag5": float(r[6]) if r[6] else None,
                "win_rate_dow_mon": float(r[7]) if r[7] else None,
                "win_rate_dow_fri": float(r[8]) if r[8] else None,
                "avg_spread_pct": float(r[9]) if r[9] else None,
                "earnings_drift_days": r[10], "earnings_avg_move": float(r[11]) if r[11] else None,
                "updated_at": str(r[12]) if r[12] else None,
            }
            for r in rows
        ]


@router.get("/{ticker}")
def get_profile(ticker: str):
    """Get behavior profile for a single ticker."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT ticker, regime, volatility_quartile, trend_strength, "
                "mean_reversion_strength, autocorr_lag1, autocorr_lag5, "
                "win_rate_dow_mon, win_rate_dow_fri, avg_spread_pct, "
                "earnings_drift_days, earnings_avg_move, updated_at "
                "FROM instrument_behavior_profiles WHERE ticker = :t"
            ),
            {"t": ticker},
        ).first()
        if not row:
            raise HTTPException(404, f"No profile for {ticker}")
        return {
            "ticker": row[0], "regime": row[1], "volatility_quartile": row[2],
            "trend_strength": float(row[3]) if row[3] else None,
            "mean_reversion_strength": float(row[4]) if row[4] else None,
            "autocorr_lag1": float(row[5]) if row[5] else None,
            "autocorr_lag5": float(row[6]) if row[6] else None,
            "win_rate_dow_mon": float(row[7]) if row[7] else None,
            "win_rate_dow_fri": float(row[8]) if row[8] else None,
            "avg_spread_pct": float(row[9]) if row[9] else None,
            "earnings_drift_days": row[10], "earnings_avg_move": float(row[11]) if row[11] else None,
            "updated_at": str(row[12]) if row[12] else None,
        }
