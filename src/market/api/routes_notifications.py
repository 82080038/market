"""Notification endpoints — daily trading signals & overnight strategy mining.

Provides read access to ``app_notifications`` table where ``daily_signal_cron.py``
and ``overnight_strategy_mining.py`` insert signal payloads.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.db.engine import get_session
from market.db.models import AppNotification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = Query(None, description="Filter by status: UNREAD or READ"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Daftar notifikasi sinyal harian (paginated).

    Query ``app_notifications`` diurutkan dari terbaru.
    ``body_json`` di-parse menjadi object untuk konsumsi frontend.
    """
    stmt = select(AppNotification).order_by(AppNotification.timestamp.desc())
    if status:
        stmt = stmt.where(AppNotification.status == status.upper())
    stmt = stmt.limit(limit).offset(offset)
    rows = session.execute(stmt).scalars().all()

    results: list[dict[str, Any]] = []
    for r in rows:
        entry: dict[str, Any] = {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "title": r.title,
            "status": r.status,
        }
        try:
            entry["body"] = json.loads(r.body_json) if r.body_json else None
        except (json.JSONDecodeError, TypeError):
            entry["body"] = None
            entry["body_raw"] = r.body_json
        results.append(entry)

    return {
        "total": len(results),
        "limit": limit,
        "offset": offset,
        "notifications": results,
    }


@router.get("/{notification_id}")
async def get_notification(
    notification_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Detail notifikasi tunggal dengan body_json ter-parse."""
    row = session.execute(
        select(AppNotification).where(AppNotification.id == notification_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    result: dict[str, Any] = {
        "id": row.id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "title": row.title,
        "status": row.status,
    }
    try:
        result["body"] = json.loads(row.body_json) if row.body_json else None
    except (json.JSONDecodeError, TypeError):
        result["body"] = None
        result["body_raw"] = row.body_json
    return result


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    """Tandai notifikasi sebagai READ."""
    row = session.execute(
        select(AppNotification).where(AppNotification.id == notification_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.status = "READ"
    session.commit()
    return {"status": "read", "id": str(notification_id)}


@router.get("/signals/latest")
async def latest_signals(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Sinyal harian terbaru — notifikasi UNREAD terbaru dengan body ter-parse.

    Shortcut untuk frontend: ambil sinyal terbaru tanpa pagination.
    Mencari notifikasi dengan title 'Daily Signal' yang belum dibaca.
    """
    row = session.execute(
        select(AppNotification)
        .where(AppNotification.status == "UNREAD")
        .where(AppNotification.title.like("Daily Signal%"))
        .order_by(AppNotification.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        return {
            "found": False,
            "message": "Belum ada sinyal harian. Jalankan daily_signal_cron.py untuk generate.",
            "notification": None,
        }

    try:
        body = json.loads(row.body_json) if row.body_json else None
    except (json.JSONDecodeError, TypeError):
        body = None

    return {
        "found": True,
        "notification": {
            "id": row.id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "title": row.title,
            "status": row.status,
            "body": body,
        },
    }
