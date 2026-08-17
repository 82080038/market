"""API routes for risk metrics — Monte Carlo VaR & CVaR.

Provides endpoints for portfolio risk analysis:
- GET /api/risk/var — compute VaR for watchlist tickers
- GET /api/risk/var/{ticker} — per-ticker VaR
"""
from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from market.db.engine import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/risk", tags=["risk"])


def _load_returns(tickers: list[str], lookback_days: int = 252) -> pd.DataFrame:
    """Load daily returns for given tickers."""
    from sqlalchemy import text

    frames = {}
    with get_engine().connect() as conn:
        for tk in tickers:
            rows = conn.execute(
                text(
                    "SELECT timestamp, close FROM stock_prices "
                    "WHERE ticker = :t AND timeframe = '1d' "
                    "ORDER BY timestamp DESC LIMIT :n"
                ),
                {"t": tk, "n": lookback_days},
            ).all()
            if len(rows) < 30:
                continue
            s = pd.Series(
                [float(r[1]) for r in reversed(rows)],
                index=pd.to_datetime([r[0] for r in reversed(rows)]),
            )
            frames[tk] = s.pct_change().dropna()
    if not frames:
        return pd.DataFrame()
    df = pd.DataFrame(frames).dropna()
    return df


@router.get("/var")
def get_portfolio_var(
    tickers: str = Query("", description="Comma-separated tickers (default: top 10 by volume)"),
    lookback_days: int = Query(252, ge=30, le=1000),
    confidence: float = Query(0.95, ge=0.90, le=0.999),
    method: str = Query("historical", pattern="^(historical|parametric|monte_carlo)$"),
    n_simulations: int = Query(10000, ge=100, le=100000),
):
    """Compute portfolio VaR and CVaR."""
    from market.risk.monte_carlo_var import MonteCarloVaR

    if tickers:
        tk_list = [t.strip() for t in tickers.split(",") if t.strip()]
    else:
        from sqlalchemy import text
        with get_engine().connect() as conn:
            tk_list = conn.execute(
                text(
                    "SELECT ticker FROM stock_prices "
                    "WHERE timeframe = '1d' AND ticker LIKE '%.JK' "
                    "GROUP BY ticker ORDER BY SUM(volume) DESC LIMIT 10"
                )
            ).scalars().all()

    if not tk_list:
        raise HTTPException(404, "No tickers found")

    returns = _load_returns(tk_list, lookback_days)
    if returns.empty:
        raise HTTPException(404, "No return data available")

    engine = MonteCarloVaR(n_simulations=n_simulations, use_gpu=True)
    result = engine.compute(
        returns=returns,
        confidence_levels=[confidence],
        method=method,
    )

    return {
        "tickers": list(returns.columns),
        "method": method,
        "confidence": confidence,
        "var": {f"{c:.0%}": v for c, v in zip(result.confidence_levels, result.var_values)},
        "cvar": {f"{c:.0%}": v for c, v in zip(result.confidence_levels, result.cvar_values)},
        "n_simulations": n_simulations,
        "lookback_days": lookback_days,
    }


@router.get("/var/{ticker}")
def get_ticker_var(
    ticker: str,
    lookback_days: int = Query(252, ge=30, le=1000),
    confidence: float = Query(0.95, ge=0.90, le=0.999),
    method: str = Query("historical", pattern="^(historical|parametric|monte_carlo)$"),
):
    """Compute VaR for a single ticker."""
    from market.risk.monte_carlo_var import MonteCarloVaR

    returns = _load_returns([ticker], lookback_days)
    if returns.empty:
        raise HTTPException(404, f"No data for {ticker}")

    engine = MonteCarloVaR(n_simulations=10000, use_gpu=True)
    result = engine.compute(
        returns=returns,
        confidence_levels=[confidence],
        method=method,
    )

    return {
        "ticker": ticker,
        "method": method,
        "confidence": confidence,
        "var": {f"{c:.0%}": v for c, v in zip(result.confidence_levels, result.var_values)},
        "cvar": {f"{c:.0%}": v for c, v in zip(result.confidence_levels, result.cvar_values)},
        "lookback_days": lookback_days,
    }
