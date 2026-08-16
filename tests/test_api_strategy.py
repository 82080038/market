"""Tests for strategy selector API routes (Gap #13)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from market.api.app import create_app


def test_strategy_classes():
    """GET /api/strategy/classes returns available strategy classes."""
    client = TestClient(create_app())
    r = client.get("/api/strategy/classes")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert "trend_following" in data
    assert "mean_reversion" in data
    assert "donchian" in data["trend_following"]


def test_strategy_assignment_not_found():
    """GET /api/strategy/assignment/{ticker} returns 404 for unknown ticker."""
    client = TestClient(create_app())
    r = client.get("/api/strategy/assignment/NONEXIST.JK")
    assert r.status_code == 404
    data = r.json()
    assert data["error"] is True
    assert "404" in str(data["status_code"])


def test_strategy_assignments_list():
    """GET /api/strategy/assignments returns a list."""
    client = TestClient(create_app())
    r = client.get("/api/strategy/assignments")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_strategy_assignments_filter_by_class():
    """GET /api/strategy/assignments?strategy_class=trend_following filters results."""
    client = TestClient(create_app())
    r = client.get("/api/strategy/assignments?strategy_class=trend_following")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for item in data:
        assert item["strategy_class"] == "trend_following"
