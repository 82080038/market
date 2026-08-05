"""Delisting memory & AI reminder endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from market.analysis.delisting_memory import (
    DelistingReason,
    WarningPattern,
    WarningPatternType,
)
from market.api._engines import engines
from market.api._shared import _dataclass_to_dict

router = APIRouter(prefix="/api", tags=["delisting"])


@router.get("/delisting/summary")
async def delisting_summary() -> dict[str, Any]:
    """Get delisting memory summary."""
    return dict(engines.delisting_memory.summary())


@router.get("/delisting/records")
async def delisting_records() -> dict[str, Any]:
    """List all delisting records."""
    return {
        "records": [
            {
                "record_id": r.record_id,
                "ticker": r.ticker,
                "exchange": r.exchange,
                "status": r.status.value,
                "reason": r.reason.value,
                "event_date": r.event_date,
                "last_price": r.last_price,
                "price_decline_pct": r.price_decline_pct,
                "lesson": r.lesson,
                "risk_score": r.risk_score,
                "sector": r.sector,
                "warning_patterns": [
                    {"type": w.pattern_type.value, "description": w.description,
                     "severity": w.severity}
                    for w in r.warning_patterns
                ],
            }
            for r in engines.delisting_memory.records
        ]
    }


@router.get("/delisting/lessons")
async def delisting_lessons(limit: int = 20) -> dict[str, Any]:
    """Get AI lessons from delisting events."""
    return {"lessons": engines.delisting_memory.get_lessons(limit=limit)}


@router.get("/delisting/check/{ticker}")
async def delisting_check(ticker: str) -> dict[str, Any]:
    """Check a ticker for delisting/suspension/warning patterns."""
    record = engines.delisting_memory.get_record(ticker)
    is_blocked = engines.delisting_memory.is_blocked(ticker)
    is_suspended = engines.delisting_memory.is_suspended(ticker)

    return {
        "ticker": ticker,
        "is_blocked": is_blocked,
        "is_suspended": is_suspended,
        "record": dict(_dataclass_to_dict(record)) if record else None,
    }


@router.post("/delisting/record")
async def delisting_record(body: dict[str, Any]) -> dict[str, Any]:
    """Record a delisting or suspension event.

    Request body:
        ticker: str
        exchange: str
        reason: str (delisting reason enum value)
        event_date: str
        last_price: float (optional)
        price_decline_pct: float (optional)
        sector: str (optional)
        status: str — "delisted" or "suspended" (default: delisted)
        warning_patterns: list of {pattern_type, description, severity} (optional)
    """
    ticker = body.get("ticker", "")
    exchange = body.get("exchange", "IDX")
    reason_str = body.get("reason", "unknown")
    event_date = body.get("event_date", "")
    status_str = body.get("status", "delisted")

    if not ticker or not event_date:
        raise HTTPException(400, "Missing ticker or event_date")

    try:
        reason = DelistingReason(reason_str)
    except ValueError:
        reason = DelistingReason.UNKNOWN

    raw_patterns = body.get("warning_patterns", [])
    warning_patterns: list[WarningPattern] = []
    for wp in raw_patterns:
        try:
            ptype = WarningPatternType(wp.get("pattern_type", ""))
        except ValueError:
            continue
        warning_patterns.append(WarningPattern(
            pattern_type=ptype,
            description=wp.get("description", ""),
            severity=float(wp.get("severity", 0.5)),
            detected_date=event_date,
        ))

    if status_str == "suspended":
        record = engines.delisting_memory.record_suspension(
            ticker=ticker,
            exchange=exchange,
            reason=reason,
            event_date=event_date,
            warning_patterns=warning_patterns,
            sector=body.get("sector", ""),
        )
    else:
        record = engines.delisting_memory.record_delisting(
            ticker=ticker,
            exchange=exchange,
            reason=reason,
            event_date=event_date,
            last_price=float(body.get("last_price", 0)),
            price_decline_pct=float(body.get("price_decline_pct", 0)),
            warning_patterns=warning_patterns,
            sector=body.get("sector", ""),
            market_cap_at_delisting=float(body.get("market_cap_at_delisting", 0)),
            days_suspended_before_delisting=int(body.get("days_suspended_before_delisting", 0)),
        )

    return dict(_dataclass_to_dict(record))


@router.post("/delisting/block")
async def delisting_block(body: dict[str, Any]) -> dict[str, Any]:
    """Block an instrument from portfolio inclusion.

    Request body:
        ticker: str
        reason: str
        risk_score: float (optional, default 0.8)
        similar_delisted: list[str] (optional)
    """
    ticker = body.get("ticker", "")
    reason = body.get("reason", "AI risk block")
    risk_score = float(body.get("risk_score", 0.8))
    similar = body.get("similar_delisted", [])

    if not ticker:
        raise HTTPException(400, "Missing ticker")

    record = engines.delisting_memory.block_instrument(
        ticker=ticker,
        reason=reason,
        risk_score=risk_score,
        similar_delisted=similar,
    )
    return dict(_dataclass_to_dict(record))


@router.post("/delisting/filter")
async def delisting_filter(body: dict[str, Any]) -> dict[str, Any]:
    """Filter tickers for portfolio inclusion.

    Request body:
        tickers: list[str] — candidate tickers
    """
    tickers = body.get("tickers", [])
    if not tickers:
        raise HTTPException(400, "Missing tickers list")

    return dict(engines.delisting_memory.get_portfolio_risk_filter(tickers))
