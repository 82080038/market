"""Price endpoints: latest intraday prices and prediction-vs-actual comparison.

Provides:
- GET /api/prices/latest — latest intraday price snapshot from DB
- POST /api/prices/intraday/trigger — manually trigger intraday fetch
- GET /api/prices/compare/{ticker} — compare prediction vs actual price
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from market.api._shared import to_jakarta
from market.core.events import broker
from market.db.engine import get_session
from market.db.models import OHLCV, StockPrice

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("/latest")
async def prices_latest(
    session: Annotated[Session, Depends(get_session)],
    ticker: str | None = None,
) -> dict[str, Any]:
    """Latest intraday price snapshot.

    Returns latest 15-min OHLCV bars from DB for all intraday tickers,
    or a specific ticker if specified.

    Query params:
        ticker: Optional ticker filter (e.g. "^JKSE", "BBCA.JK")
    """
    # Try PG stock_prices first, fallback to SQLite ohlcv
    try:
        stmt = (
            select(StockPrice)
            .where(StockPrice.timeframe == "15m")
            .order_by(desc(StockPrice.timestamp))
            .limit(50)
        )
        if ticker:
            stmt = (
                select(StockPrice)
                .where(StockPrice.timeframe == "15m", StockPrice.ticker == ticker)
                .order_by(desc(StockPrice.timestamp))
                .limit(20)
            )
        rows = session.execute(stmt).scalars().all()
        if not rows:
            raise Exception("No PG stock_prices data")
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        stmt = (
            select(OHLCV)
            .where(OHLCV.timeframe == "15m")
            .order_by(desc(OHLCV.timestamp))
            .limit(50)
        )
        if ticker:
            stmt = (
                select(OHLCV)
                .where(OHLCV.timeframe == "15m", OHLCV.ticker == ticker)
                .order_by(desc(OHLCV.timestamp))
                .limit(20)
            )
        rows = session.execute(stmt).scalars().all()

    if not rows:
        return {
            "prices": {},
            "count": 0,
            "message": "No intraday data yet. Run fetch_intraday first.",
        }

    prices: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.ticker in prices:
            continue
        prices[r.ticker] = {
            "price": float(r.close),
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "volume": r.volume,
            "timestamp": to_jakarta(r.timestamp),
            "timeframe": r.timeframe,
            "source": r.source,
        }

    return {
        "prices": prices,
        "count": len(prices),
    }


@router.get("/ihsg")
async def ihsg_summary(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Latest IHSG (^JKSE) summary — lightweight endpoint for dashboard."""
    from sqlalchemy import text as sql_text

    sql = sql_text("""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv
        WHERE ticker = '^JKSE' AND timeframe = '1d'
          AND timestamp IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 2
    """)
    rows = session.execute(sql).fetchall()
    if not rows:
        return {"price": None, "change": None, "pct_change": None, "as_of": None}
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    close = float(latest[4])
    prev_close = float(prev[4]) if prev else None
    change = close - prev_close if prev_close else None
    pct = round((change / prev_close * 100), 2) if prev_close and prev_close > 0 else None
    return {
        "price": close,
        "open": float(latest[1]),
        "high": float(latest[2]),
        "low": float(latest[3]),
        "volume": int(latest[5]) if latest[5] else 0,
        "change": round(change, 2) if change is not None else None,
        "pct_change": pct,
        "as_of": to_jakarta(latest[0]),
    }


@router.get("/movers")
async def prices_movers(
    session: Annotated[Session, Depends(get_session)],
    limit: int = 10,
) -> dict[str, Any]:
    """Top movers (gainers/losers) based on latest daily pct change.

    Compares the latest 1d close vs the previous trading day close
    for all IDX tickers.

    Query params:
        limit: Number of gainers/losers to return (default 10).
    """
    from sqlalchemy import text

    # Use raw SQL for efficient LAG window function
    sql = text("""
        WITH ranked AS (
            SELECT ticker, close, timestamp,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) AS rn
            FROM ohlcv
            WHERE timeframe = '1d'
              AND ticker LIKE '%.JK'
              AND timestamp IS NOT NULL
        ),
        latest AS (
            SELECT ticker, close, timestamp FROM ranked WHERE rn = 1
        ),
        prev AS (
            SELECT ticker, close AS prev_close FROM ranked WHERE rn = 2
        )
        SELECT l.ticker, l.close, l.timestamp, p.prev_close,
               ((l.close - p.prev_close) / NULLIF(p.prev_close, 0) * 100) AS pct_change
        FROM latest l
        JOIN prev p ON l.ticker = p.ticker
        WHERE p.prev_close > 0
        ORDER BY pct_change DESC
    """)

    rows = session.execute(sql).fetchall()

    if not rows:
        return {"gainers": [], "losers": [], "as_of": None, "count": 0}

    movers = [
        {
            "ticker": r[0],
            "close": float(r[1]),
            "prev_close": float(r[3]),
            "pct_change": round(float(r[4]), 2),
        }
        for r in rows
        if r[4] is not None
    ]

    gainers = movers[:limit]
    losers = list(reversed(movers))[:limit]
    as_of = to_jakarta(rows[0][2]) if rows[0][2] else None

    return {
        "gainers": gainers,
        "losers": losers,
        "as_of": as_of,
        "count": len(movers),
    }


@router.post("/intraday/trigger")
async def intraday_trigger(
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Manually trigger intraday fetch.

    Optionally specify tickers in request body:
        {"tickers": ["^JKSE", "^GSPC", "BBCA.JK"]}

    If no tickers specified, uses default intraday ticker list.
    """
    from market.scheduler_tasks import INTRADAY_TICKER_MIC

    tickers = (body or {}).get("tickers", list(INTRADAY_TICKER_MIC.keys()))

    event = broker.emit("data.fetch.intraday.requested", {
        "source": "manual",
        "tickers": tickers,
    })

    return {
        "status": "triggered",
        "event_id": id(event),
        "tickers": tickers,
        "message": "Intraday fetch triggered. Check /api/prices/latest after a few seconds.",
    }


@router.get("/compare/{ticker}")
async def prices_compare(
    ticker: str,
    session: Annotated[Session, Depends(get_session)],
    lookback_bars: int = 20,
) -> dict[str, Any]:
    """Compare prediction vs actual price for a ticker.

    Fetches recent OHLCV data, runs prediction engine, and compares
    the predicted direction/price with actual price movement.

    Path params:
        ticker: Ticker to compare (e.g. "BBCA.JK")

    Query params:
        lookback_bars: Number of recent bars to use for prediction (default 20)
    """
    import pandas as pd

    from market.analysis.prediction import PredictionMethod
    from market.api._engines import engines

    # Try PG stock_prices first, fallback to SQLite ohlcv
    try:
        rows = session.execute(
            select(StockPrice)
            .where(StockPrice.ticker == ticker, StockPrice.timeframe == "1d")
            .order_by(StockPrice.timestamp)
            .limit(300)
        ).scalars().all()
        if len(rows) < 50:
            raise Exception("Insufficient PG data")
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        rows = session.execute(
            select(OHLCV)
            .where(OHLCV.ticker == ticker, OHLCV.timeframe == "1d")
            .order_by(OHLCV.timestamp)
            .limit(300)
        ).scalars().all()

    if len(rows) < 50:
        raise HTTPException(
            404,
            f"Insufficient data for {ticker}: {len(rows)} bars (need ≥50)",
        )

    df = pd.DataFrame(
        [
            {
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": r.volume,
            }
            for r in rows
        ],
        index=pd.DatetimeIndex([r.timestamp for r in rows]),
    )

    as_of = str(df.index[-lookback_bars])
    actual_close = float(df.iloc[-1]["close"])
    predicted_close_at_as_of = float(df.iloc[-lookback_bars]["close"])

    try:
        pred = engines.prediction_engine.predict(
            ticker=ticker,
            data=df,
            method=PredictionMethod.ENSEMBLE,
            as_of=as_of,
        )
    except Exception as exc:
        raise HTTPException(500, f"Prediction failed: {exc}") from exc

    actual_direction = "up" if actual_close > predicted_close_at_as_of else "down"
    predicted_direction = pred.predicted_direction
    direction_correct = actual_direction == predicted_direction

    actual_pct_change = round(
        (actual_close - predicted_close_at_as_of) / predicted_close_at_as_of * 100, 2,
    )

    predicted_price = pred.predicted_price
    price_error_pct = None
    if predicted_price is not None and predicted_price > 0:
        price_error_pct = round(
            abs(actual_close - predicted_price) / predicted_price * 100, 2,
        )

    return {
        "ticker": ticker,
        "as_of": as_of,
        "prediction": {
            "direction": predicted_direction,
            "predicted_price": predicted_price,
            "confidence": pred.confidence,
            "method": pred.method.value,
            "rationale": pred.rationale,
        },
        "actual": {
            "direction": actual_direction,
            "actual_price": actual_close,
            "actual_pct_change": actual_pct_change,
        },
        "comparison": {
            "direction_correct": direction_correct,
            "price_error_pct": price_error_pct,
        },
    }
