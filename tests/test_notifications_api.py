"""Tests for notification API routes."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from market.api.app import create_app


@pytest.mark.isolated_db
def test_list_notifications_empty():
    client = TestClient(create_app())
    r = client.get("/api/notifications")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["notifications"] == []


@pytest.mark.isolated_db
def test_list_notifications_with_data():
    client = TestClient(create_app())

    # Insert a notification directly via DB session
    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    sm = get_sessionmaker()
    session = sm()
    try:
        notif = AppNotification(
            title="Daily Signal 2026-08-10",
            body_json=json.dumps({
                "signal_date": "2026-08-10",
                "keep_score": 3.5,
                "keep_verdict": "KEEP",
                "promoted_to_keep": True,
                "portfolio_capital": 100_000_000,
                "summary": {"buy": 5, "sell": 3, "hold": 10, "errors": 2, "total_tickers": 20},
                "signals": [
                    {
                        "ticker": "BBCA.JK",
                        "action": "BUY",
                        "signal": 0.75,
                        "close_price": 8000,
                        "portfolio_weight": 0.15,
                        "position_sizing": {"shares": 100, "lots": 1, "allocation_idr": 800000},
                    },
                ],
            }),
            status="UNREAD",
        )
        session.add(notif)
        session.commit()
        notif_id = notif.id
    finally:
        session.close()

    r = client.get("/api/notifications")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    entry = data["notifications"][0]
    assert entry["id"] == notif_id
    assert entry["title"] == "Daily Signal 2026-08-10"
    assert entry["status"] == "UNREAD"
    assert entry["body"] is not None
    assert entry["body"]["signal_date"] == "2026-08-10"
    assert entry["body"]["signals"][0]["ticker"] == "BBCA.JK"


@pytest.mark.isolated_db
def test_list_notifications_filter_by_status():
    client = TestClient(create_app())

    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    sm = get_sessionmaker()
    session = sm()
    try:
        session.add(AppNotification(title="Unread", body_json="{}", status="UNREAD"))
        session.add(AppNotification(title="Read", body_json="{}", status="READ"))
        session.commit()
    finally:
        session.close()

    r = client.get("/api/notifications?status=UNREAD")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["notifications"][0]["title"] == "Unread"

    r = client.get("/api/notifications?status=READ")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["notifications"][0]["title"] == "Read"


@pytest.mark.isolated_db
def test_get_notification_by_id():
    client = TestClient(create_app())

    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    sm = get_sessionmaker()
    session = sm()
    try:
        notif = AppNotification(
            title="Test Notif",
            body_json=json.dumps({"key": "value"}),
            status="UNREAD",
        )
        session.add(notif)
        session.commit()
        notif_id = notif.id
    finally:
        session.close()

    r = client.get(f"/api/notifications/{notif_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == notif_id
    assert data["title"] == "Test Notif"
    assert data["body"]["key"] == "value"


@pytest.mark.isolated_db
def test_get_notification_not_found():
    client = TestClient(create_app())
    r = client.get("/api/notifications/9999")
    assert r.status_code == 404


@pytest.mark.isolated_db
def test_mark_as_read():
    client = TestClient(create_app())

    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    sm = get_sessionmaker()
    session = sm()
    try:
        notif = AppNotification(title="To Read", body_json="{}", status="UNREAD")
        session.add(notif)
        session.commit()
        notif_id = notif.id
    finally:
        session.close()

    r = client.patch(f"/api/notifications/{notif_id}/read")
    assert r.status_code == 200
    assert r.json()["status"] == "read"

    # Verify it's now READ
    r = client.get(f"/api/notifications/{notif_id}")
    assert r.json()["status"] == "READ"


@pytest.mark.isolated_db
def test_mark_as_read_not_found():
    client = TestClient(create_app())
    r = client.patch("/api/notifications/9999/read")
    assert r.status_code == 404


@pytest.mark.isolated_db
def test_latest_signals_empty():
    client = TestClient(create_app())
    r = client.get("/api/notifications/signals/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["found"] is False
    assert data["notification"] is None


@pytest.mark.isolated_db
def test_latest_signals_found():
    client = TestClient(create_app())

    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    sm = get_sessionmaker()
    session = sm()
    try:
        notif = AppNotification(
            title="Daily Signal 2026-08-10",
            body_json=json.dumps({
                "signal_date": "2026-08-10",
                "keep_score": 3.5,
                "signals": [{"ticker": "UNTR.JK", "action": "BUY"}],
            }),
            status="UNREAD",
        )
        session.add(notif)
        session.commit()
    finally:
        session.close()

    r = client.get("/api/notifications/signals/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["found"] is True
    assert data["notification"]["title"] == "Daily Signal 2026-08-10"
    assert data["notification"]["body"]["signal_date"] == "2026-08-10"


@pytest.mark.isolated_db
def test_latest_signals_skips_read():
    client = TestClient(create_app())

    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    sm = get_sessionmaker()
    session = sm()
    try:
        session.add(AppNotification(
            title="Daily Signal Old",
            body_json=json.dumps({"signal_date": "2026-08-09"}),
            status="READ",
        ))
        session.commit()
    finally:
        session.close()

    r = client.get("/api/notifications/signals/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["found"] is False


@pytest.mark.isolated_db
def test_notifications_pagination():
    client = TestClient(create_app())

    from market.db.engine import get_sessionmaker
    from market.db.models import AppNotification

    sm = get_sessionmaker()
    session = sm()
    try:
        for i in range(5):
            session.add(AppNotification(
                title=f"Test {i}",
                body_json=json.dumps({"index": i}),
                status="UNREAD",
            ))
        session.commit()
    finally:
        session.close()

    r = client.get("/api/notifications?limit=2&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["notifications"]) == 2

    r = client.get("/api/notifications?limit=2&offset=2")
    data = r.json()
    assert len(data["notifications"]) == 2
