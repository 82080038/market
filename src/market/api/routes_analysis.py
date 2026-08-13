"""Analysis endpoints: scores, recommend, advisory, readiness."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from market.api._engines import engines
from market.api._shared import _dataclass_to_dict, to_jakarta
from market.db.engine import get_session

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/stock/{ticker}")
async def stock_summary(
    ticker: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Stock detail summary — latest OHLCV, factor scores from DB, prediction.

    Combines data from multiple sources for the stock detail page.
    """
    from sqlalchemy import text as sql_text

    # Latest OHLCV
    sql = sql_text("""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv
        WHERE ticker = :ticker AND timeframe = '1d'
          AND timestamp IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 30
    """)
    rows = session.execute(sql, {"ticker": ticker}).fetchall()
    if not rows:
        raise HTTPException(404, f"No data for {ticker}")

    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    close = float(latest[4])
    prev_close = float(prev[4]) if prev else None
    pct_change = round((close - prev_close) / prev_close * 100, 2) if prev_close and prev_close > 0 else None

    ohlcv = [
        {
            "date": to_jakarta(r[0])[:10] if r[0] else "",
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": int(r[5]) if r[5] else 0,
        }
        for r in reversed(rows)
    ]

    # Factor scores from scores table (one row per engine)
    scores_sql = sql_text("""
        SELECT engine, score, breakdown, as_of
        FROM scores
        WHERE ticker = :ticker
        ORDER BY as_of DESC
    """)
    score_rows = session.execute(scores_sql, {"ticker": ticker}).fetchall()

    factors: dict[str, Any] = {
        "technical": 0, "fundamental": 0, "macro": 0,
        "global": 0, "relationship": 0, "sentiment": 0,
        "composite": 0,
    }
    import json as _json
    for row in score_rows:
        engine_name = row[0]
        score_val = float(row[1] or 0)
        breakdown = row[2]
        if engine_name == "composite":
            factors["composite"] = score_val
        elif engine_name in factors:
            factors[engine_name] = score_val
        elif breakdown:
            try:
                bd = _json.loads(breakdown) if isinstance(breakdown, str) else breakdown
                if isinstance(bd, dict):
                    for k in factors:
                        if k in bd:
                            factors[k] = float(bd[k] or 0)
            except Exception:
                pass

    # Prediction from stock_prediction table
    pred_sql = sql_text("""
        SELECT predicted_direction, predicted_price, predicted_return_pct,
               prediction_confidence, composite_signal, prediction_updated_at
        FROM stock_prediction
        WHERE ticker = :ticker
        ORDER BY prediction_updated_at DESC
        LIMIT 1
    """)
    pred_row = session.execute(pred_sql, {"ticker": ticker}).fetchone()
    prediction = None
    if pred_row:
        prediction = {
            "direction": pred_row[0],
            "predicted_price": float(pred_row[1]) if pred_row[1] else None,
            "return_pct": float(pred_row[2]) if pred_row[2] else None,
            "confidence": float(pred_row[3]) if pred_row[3] else None,
            "composite_signal": float(pred_row[4]) if pred_row[4] else None,
            "as_of": to_jakarta(pred_row[5]),
        }

    return {
        "ticker": ticker,
        "latest": {
            "close": close,
            "open": float(latest[1]),
            "high": float(latest[2]),
            "low": float(latest[3]),
            "volume": int(latest[5]) if latest[5] else 0,
            "pct_change": pct_change,
            "as_of": to_jakarta(latest[0]),
        },
        "ohlcv": ohlcv,
        "factors": factors,
        "prediction": prediction,
    }


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
