"""Pattern detection & prediction endpoints (no look-ahead bias)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from market.analysis.prediction import PredictionMethod
from market.api._engines import engines
from market.api._shared import _dataclass_to_dict

router = APIRouter(prefix="/api", tags=["prediction"])


@router.post("/pattern/detect")
async def pattern_detect(body: dict[str, Any]) -> dict[str, Any]:
    """Detect chart patterns with no look-ahead bias.

    Request body:
        ticker: str — instrument ticker
        ohlcv: dict with keys open, high, low, close, volume (lists)
        as_of: str (optional) — detection date cutoff (ISO format)
    """
    import pandas as pd

    ticker = body.get("ticker", "UNKNOWN")
    ohlcv_raw = body.get("ohlcv", {})
    as_of = body.get("as_of")

    if not ohlcv_raw:
        raise HTTPException(400, "Missing ohlcv data")

    df = pd.DataFrame(ohlcv_raw)
    if "date" in df.columns:
        df = df.set_index("date")
    elif "index" in df.columns:
        df = df.set_index("index")

    detections = engines.pattern_detector.detect(ticker, df, as_of)

    return {
        "ticker": ticker,
        "as_of": as_of or str(df.index[-1]),
        "patterns": [
            {
                "pattern_type": d.pattern_type,
                "direction": d.direction,
                "confidence": d.confidence,
                "price_at_detection": d.price_at_detection,
                "key_levels": d.key_levels,
                "description": d.description,
                "indicators_snapshot": d.indicators_snapshot,
            }
            for d in detections
        ],
        "log": [
            {
                "timestamp": e.timestamp,
                "level": e.level,
                "ticker": e.ticker,
                "message": e.message,
                "data": e.data,
            }
            for e in engines.pattern_detector.log
        ],
    }


@router.post("/prediction/predict")
async def prediction_predict(body: dict[str, Any]) -> dict[str, Any]:
    """Predict next-period price with no look-ahead bias.

    Request body:
        ticker: str
        ohlcv: dict with keys open, high, low, close, volume (lists)
        as_of: str (optional) — prediction date cutoff
        method: str (optional) — ma_based, momentum, pattern_based,
                volatility_adjusted, ensemble (default)
    """
    import pandas as pd

    ticker = body.get("ticker", "UNKNOWN")
    ohlcv_raw = body.get("ohlcv", {})
    as_of = body.get("as_of")
    method_str = body.get("method", "ensemble")

    if not ohlcv_raw:
        raise HTTPException(400, "Missing ohlcv data")

    try:
        method = PredictionMethod(method_str)
    except ValueError:
        method = PredictionMethod.ENSEMBLE

    df = pd.DataFrame(ohlcv_raw)
    if "date" in df.columns:
        df = df.set_index("date")
    elif "index" in df.columns:
        df = df.set_index("index")

    pred = engines.prediction_engine.predict(ticker, df, as_of, method)

    return {
        "prediction": {
            "ticker": pred.ticker,
            "as_of": pred.as_of,
            "method": pred.method.value,
            "predicted_price": pred.predicted_price,
            "predicted_direction": pred.predicted_direction,
            "predicted_return_pct": pred.predicted_return_pct,
            "confidence": pred.confidence,
            "horizon_days": pred.horizon_days,
            "indicators_used": pred.indicators_used,
            "pattern_signals": pred.pattern_signals,
            "rationale": pred.rationale,
        },
        "log": [
            {
                "timestamp": e.timestamp,
                "level": e.level,
                "ticker": e.ticker,
                "message": e.message,
                "data": e.data,
            }
            for e in engines.prediction_engine.log
        ],
    }


@router.post("/prediction/verify")
async def prediction_verify(body: dict[str, Any]) -> dict[str, Any]:
    """Verify a past prediction against actual outcome.

    Request body:
        ticker: str
        ohlcv: dict with full OHLCV data (including future data)
        as_of: str — the date the prediction was made
    """
    import pandas as pd

    ticker = body.get("ticker", "UNKNOWN")
    ohlcv_raw = body.get("ohlcv", {})
    as_of = body.get("as_of")

    if not ohlcv_raw:
        raise HTTPException(400, "Missing ohlcv data")
    if not as_of:
        raise HTTPException(400, "Missing as_of date")

    df = pd.DataFrame(ohlcv_raw)
    if "date" in df.columns:
        df = df.set_index("date")
    elif "index" in df.columns:
        df = df.set_index("index")

    error = engines.prediction_engine.verify(ticker, df, as_of)

    return {
        "ticker": ticker,
        "as_of": as_of,
        "error": dict(_dataclass_to_dict(error)) if error else None,
        "log": [
            {
                "timestamp": e.timestamp,
                "level": e.level,
                "ticker": e.ticker,
                "message": e.message,
                "data": e.data,
            }
            for e in engines.prediction_engine.log
        ],
    }


@router.get("/prediction/errors")
async def prediction_errors(ticker: str | None = None) -> dict[str, Any]:
    """Get prediction error summary with lessons and risk factors."""
    return dict(engines.prediction_engine.get_error_summary(ticker))


@router.get("/prediction/risk/{ticker}")
async def prediction_risk(ticker: str) -> dict[str, Any]:
    """Get risk adjustment factor from prediction errors for a ticker."""
    adjustment = engines.prediction_engine.get_risk_adjustment(ticker)
    summary = engines.prediction_engine.get_error_summary(ticker)
    return {
        "ticker": ticker,
        "risk_adjustment": adjustment,
        "error_summary": summary,
    }
