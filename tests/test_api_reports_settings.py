"""Tests for reports and settings API routes (Gap #25)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from market.api.app import create_app


def test_reports_trade_log():
    """GET /api/reports/trade-log returns list."""
    client = TestClient(create_app())
    r = client.get("/api/reports/trade-log")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_reports_dividends():
    """GET /api/reports/dividends returns list."""
    client = TestClient(create_app())
    r = client.get("/api/reports/dividends")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_reports_tax():
    """GET /api/reports/tax/{year} returns tax summary."""
    client = TestClient(create_app())
    r = client.get("/api/reports/tax/2026")
    assert r.status_code == 200
    data = r.json()
    assert data["year"] == 2026
    assert "total_sell_value" in data
    assert "expected_pph_final_0_1_pct" in data
    assert "sell_count" in data


def test_reports_statement():
    """GET /api/reports/statement?month=YYYY-MM returns statement."""
    client = TestClient(create_app())
    r = client.get("/api/reports/statement?month=2026-08")
    assert r.status_code == 200
    data = r.json()
    assert data["month"] == "2026-08"
    assert "positions" in data
    assert "position_count" in data


def test_settings_get():
    """GET /api/settings returns settings dict."""
    client = TestClient(create_app())
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert "risk_per_trade_pct" in data
    assert "telegram_alert_enabled" in data


def test_settings_put():
    """PUT /api/settings saves settings."""
    client = TestClient(create_app())
    r = client.put("/api/settings", json={
        "risk_per_trade_pct": 2.0,
        "atr_multiplier_sl": 2.0,
        "risk_reward_ratio": 3.0,
        "max_volatility_pct": 40.0,
        "telegram_alert_enabled": False,
        "email_alert_enabled": True,
        "in_app_alert_enabled": True,
        "circuit_breaker_alert_enabled": True,
        "display_timezone": "Asia/Jakarta",
        "default_chart_period": "60d",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"

    # Verify it was saved
    r2 = client.get("/api/settings")
    assert r2.status_code == 200
    saved = r2.json()
    assert saved["risk_per_trade_pct"] == 2.0
    assert saved["email_alert_enabled"] is True
