"""Tests for security modules API integration (Gap #24)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from market.api.app import create_app


def test_sharia_screen_compliant():
    """POST /api/security/sharia/screen returns compliant result."""
    client = TestClient(create_app())
    r = client.post("/api/security/sharia/screen", json={
        "ticker": "TEST.JK",
        "tags": ["technology"],
        "debt_to_assets": 0.2,
        "interest_income_to_revenue": 0.05,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "TEST.JK"
    assert data["is_compliant"] is True
    assert data["stage"] == "passed"


def test_sharia_screen_haram_business():
    """POST /api/security/sharia/screen detects haram business."""
    client = TestClient(create_app())
    r = client.post("/api/security/sharia/screen", json={
        "ticker": "TEST.JK",
        "tags": ["alcohol"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["is_compliant"] is False
    assert data["business_activity_pass"] is False


def test_sharia_screen_high_debt():
    """POST /api/security/sharia/screen detects high debt ratio."""
    client = TestClient(create_app())
    r = client.post("/api/security/sharia/screen", json={
        "ticker": "TEST.JK",
        "debt_to_assets": 0.6,  # > 0.45 threshold
    })
    assert r.status_code == 200
    data = r.json()
    assert data["is_compliant"] is False
    assert data["financial_ratio_pass"] is False


def test_sharia_screen_batch():
    """POST /api/security/sharia/screen-batch screens multiple stocks."""
    client = TestClient(create_app())
    r = client.post("/api/security/sharia/screen-batch", json={
        "stocks": [
            {"ticker": "A.JK", "tags": ["tech"], "debt_to_assets": 0.2},
            {"ticker": "B.JK", "tags": ["gambling"]},
        ]
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["is_compliant"] is True
    assert data[1]["is_compliant"] is False


def test_sharia_compliant_list():
    """GET /api/security/sharia/compliant returns criteria and haram list."""
    client = TestClient(create_app())
    r = client.get("/api/security/sharia/compliant")
    assert r.status_code == 200
    data = r.json()
    assert "criteria" in data
    assert "haram_activities" in data
    assert "alcohol" in data["haram_activities"]


def test_surveillance_record_trade():
    """POST /api/security/surveillance/trade records a trade."""
    client = TestClient(create_app())
    r = client.post("/api/security/surveillance/trade", json={
        "trade_id": "T001",
        "ticker": "BBCA.JK",
        "side": "buy",
        "quantity": 100,
        "price": 90000,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_surveillance_record_order():
    """POST /api/security/surveillance/order records an order."""
    client = TestClient(create_app())
    r = client.post("/api/security/surveillance/order", json={
        "order_id": "O001",
        "ticker": "BBCA.JK",
        "side": "buy",
        "quantity": 100,
        "price": 90000,
        "status": "new",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_surveillance_alerts():
    """GET /api/security/surveillance/alerts returns alerts list."""
    client = TestClient(create_app())
    r = client.get("/api/security/surveillance/alerts")
    assert r.status_code == 200
    data = r.json()
    assert "alert_count" in data
    assert "alerts" in data


def test_fractional_buy():
    """POST /api/security/fractional/buy buys fractional shares."""
    client = TestClient(create_app())
    r = client.post("/api/security/fractional/buy", json={
        "ticker": "BBCA.JK",
        "amount": 100_000,
        "price": 90000,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["quantity"] > 0


def test_fractional_buy_below_minimum():
    """POST /api/security/fractional/buy rejects below minimum."""
    client = TestClient(create_app())
    r = client.post("/api/security/fractional/buy", json={
        "ticker": "BBCA.JK",
        "amount": 100,  # Below minimum
        "price": 90000,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "error"


def test_fractional_position_not_found():
    """GET /api/security/fractional/position/{ticker} returns not_found for unknown."""
    client = TestClient(create_app())
    r = client.get("/api/security/fractional/position/UNKNOWN.JK")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "not_found"


def test_fractional_create_plan():
    """POST /api/security/fractional/plan creates a micro-investment plan."""
    client = TestClient(create_app())
    r = client.post("/api/security/fractional/plan", json={
        "ticker": "BBCA.JK",
        "amount_per_period": 500_000,
        "frequency": "monthly",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["plan_id"] != ""
    assert data["frequency"] == "monthly"
