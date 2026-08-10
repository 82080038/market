"""Data visibility endpoints: sources, watermarks, audit, fetch, quality."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.api._shared import to_jakarta
from market.db.engine import get_session
from market.db.models import (
    OHLCV,
    AuditLog,
    DataWatermark,
    SourceHealth,
)

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/sources")
async def data_sources(
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    """Daftar sumber data dengan status kesehatan.

    Menampilkan semua sumber data eksternal yang terdaftar di database,
    beserta status kesehatan, jumlah fetch, dan error terakhir.
    """
    rows = session.execute(
        select(SourceHealth).order_by(SourceHealth.source)
    ).scalars().all()
    return [
        {
            "source": r.source,
            "status": r.status,
            "last_success": to_jakarta(r.last_success),
            "last_error": to_jakarta(r.last_error),
            "last_error_msg": r.last_error_msg,
            "total_fetches": r.total_fetches,
            "total_failures": r.total_failures,
            "updated_at": to_jakarta(r.updated_at),
        }
        for r in rows
    ]


@router.get("/watermarks")
async def data_watermarks(
    table_name: str | None = Query(None, description="Filter by table name"),
    session: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> list[dict[str, Any]]:
    """Watermark semua tabel — kapan terakhir diupdate dan jumlah rows.

    Menampilkan timestamp update terakhir per tabel per ticker,
    untuk melacak kestalan (staleness) data.
    """
    stmt = select(DataWatermark).order_by(
        DataWatermark.table_name, DataWatermark.ticker,
    )
    if table_name:
        stmt = stmt.where(DataWatermark.table_name == table_name)
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "ticker": r.ticker,
            "table_name": r.table_name,
            "last_updated": to_jakarta(r.last_updated),
            "row_count": r.row_count,
            "source": r.source,
        }
        for r in rows
    ]


@router.get("/audit")
async def data_audit(
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Audit log aktivitas data (paginated).

    Menampilkan event log seperti data.fetch_ohlcv, decision.score,
    execution.order, dll. Berguna untuk tracing dan debugging.
    """
    from sqlalchemy import func as sqlfunc

    count_stmt = select(sqlfunc.count(AuditLog.id))
    if event_type:
        count_stmt = count_stmt.where(AuditLog.event_type == event_type)
    total = session.execute(count_stmt).scalar() or 0

    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
    stmt = stmt.limit(limit).offset(offset)
    rows = session.execute(stmt).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [
            {
                "id": r.id,
                "event_type": r.event_type,
                "event_payload": r.event_payload,
                "actor": r.actor,
                "created_at": to_jakarta(r.created_at),
            }
            for r in rows
        ],
    }


@router.post("/fetch")
async def data_fetch(
    body: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Trigger fetch manual untuk ticker tertentu dari Yahoo Finance.

    Request body:
        ticker: str — Yahoo Finance ticker (e.g. "BBCA.JK")
        period: str — yfinance period (default "3mo")
    """
    from market.data.acquisition import DataAcquisitionEngine
    from market.data.storage import DataRepository

    ticker = body.get("ticker")
    if not ticker:
        raise HTTPException(400, "Missing 'ticker' in request body")

    period = body.get("period", "3mo")

    repo = DataRepository(session)
    engine = DataAcquisitionEngine(repository=repo)

    try:
        result = engine.fetch_and_store(ticker=ticker, period=period)
        return dict(result)
    except Exception as exc:
        raise HTTPException(500, f"Fetch failed: {exc}") from exc


@router.get("/quality/{ticker}")
async def data_quality(
    ticker: str,
    session: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Skor kualitas data per ticker.

    Memeriksa kelengkapan data OHLCV, jumlah bar, gap, dan
    memberikan skor kualitas 0-100.
    """
    from market.data.validation import DataQualityEngine

    rows = session.execute(
        select(OHLCV).where(OHLCV.ticker == ticker).order_by(OHLCV.timestamp)
    ).scalars().all()

    if not rows:
        return {
            "ticker": ticker,
            "bars": 0,
            "score": 0.0,
            "action": "pause",
            "anomalies": ["No data available"],
        }

    from market.data.contracts import NormalizedOHLCV

    records = [
        NormalizedOHLCV(
            ticker=r.ticker,
            timestamp=r.timestamp,
            open=Decimal(str(r.open)),
            high=Decimal(str(r.high)),
            low=Decimal(str(r.low)),
            close=Decimal(str(r.close)),
            volume=r.volume,
        )
        for r in rows
    ]

    validator = DataQualityEngine()
    result = validator.validate(records)

    return {
        "ticker": ticker,
        "bars": len(rows),
        "score": result.score,
        "action": result.action,
        "anomalies": result.anomalies,
    }
