"""Analysis endpoints: scores, recommend, advisory, readiness."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from market.api._engines import engines
from market.api._shared import _dataclass_to_dict

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/scores/{ticker}")
async def get_scores(
    ticker: str,
    technical: float | None = Query(None),
    fundamental: float | None = Query(None),
    macro: float | None = Query(None),
    global_market: float | None = Query(None),
    relationship: float | None = Query(None),
    sentiment: float | None = Query(None),
) -> dict[str, Any]:
    """Get 6 factor scores for a ticker.

    If query params are provided, use them directly.
    Otherwise returns a placeholder structure.
    """
    if all(
        v is None
        for v in [technical, fundamental, macro, global_market, relationship, sentiment]
    ):
        return {
            "ticker": ticker,
            "message": "Provide factor scores as query params.",
            "factors": [
                "technical", "fundamental", "macro",
                "global", "relationship", "sentiment",
            ],
        }

    result = engines.decision_engine.decide(
        ticker=ticker,
        technical=technical,
        fundamental=fundamental,
        macro=macro,
        global_market=global_market,
        relationship=relationship,
        sentiment=sentiment,
    )
    return dict(_dataclass_to_dict(result))


@router.get("/recommend/{ticker}")
async def recommend(
    ticker: str,
    technical: float | None = Query(None),
    fundamental: float | None = Query(None),
    macro: float | None = Query(None),
    global_market: float | None = Query(None),
    relationship: float | None = Query(None),
    sentiment: float | None = Query(None),
) -> dict[str, Any]:
    """Get composite recommendation with XAI breakdown."""
    result = engines.decision_engine.decide(
        ticker=ticker,
        technical=technical,
        fundamental=fundamental,
        macro=macro,
        global_market=global_market,
        relationship=relationship,
        sentiment=sentiment,
    )
    return dict(_dataclass_to_dict(result))


@router.get("/advisory")
async def advisory(
    market_regime: str = Query("neutral"),
    min_composite: float = Query(50.0),
) -> dict[str, Any]:
    """Get advisory report with top picks.

    Pass universe as query param ticker=score pairs.
    Example: ?ticker=BBCA&tech=75&fund=80&sent=70&ticker=TLKM&tech=50&fund=60&sent=50
    """
    report = engines.advisory_engine.generate_report(
        market_regime=market_regime,
        universe={},
        min_composite=min_composite,
    )
    return dict(_dataclass_to_dict(report))


@router.get("/readiness/{ticker}")
async def readiness(
    ticker: str,
    sector: str | None = Query(None),
    market_cap: float | None = Query(None),
    asset_class: str = Query("equity"),
    bars: int = Query(0, ge=0, le=10000),
) -> dict[str, Any]:
    """Get instrument readiness assessment.

    Evaluates whether the application has sufficient knowledge about
    an instrument before making screening/selection decisions.

    Query params:
        sector: Sector classification (e.g., 'energy', 'financials').
        market_cap: Market capitalization in IDR.
        asset_class: Asset class string (equity, etf, bond, etc.).
        bars: Number of OHLCV bars available (if no real data loaded).
    """
    import numpy as np
    import pandas as pd

    if bars > 0:
        dates = pd.date_range("2024-01-02", periods=bars, freq="B")
        rng = np.random.RandomState(42)
        returns = rng.normal(0.001, 0.01, bars)
        close = 100.0 * np.cumprod(1 + returns)
        high = close * (1 + np.abs(rng.normal(0, 0.005, bars)))
        low = close * (1 - np.abs(rng.normal(0, 0.005, bars)))
        op = close * (1 + rng.normal(0, 0.003, bars))
        volume = rng.randint(100_000, 1_000_000, bars).astype(float)
        df = pd.DataFrame(
            {"open": op, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )
    else:
        df = pd.DataFrame()

    report = engines.readiness_gate.evaluate(
        ticker, df, sector=sector, market_cap=market_cap, asset_class=asset_class,
    )
    return dict(_dataclass_to_dict(report))
