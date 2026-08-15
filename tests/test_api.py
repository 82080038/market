"""Tests for FastAPI endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from market.api.app import create_app


def test_health():
    client = TestClient(create_app())
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_env():
    client = TestClient(create_app())
    r = client.get("/api/env")
    assert r.status_code == 200
    data = r.json()
    assert "env" in data
    assert "db_path" in data


def test_markets():
    client = TestClient(create_app())
    r = client.get("/api/markets")
    assert r.status_code == 200
    markets = r.json()
    assert len(markets) > 0
    assert any(m["mic_code"] == "XIDX" for m in markets)


def test_scores_no_params():
    client = TestClient(create_app())
    r = client.get("/api/scores/BBCA.JK")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "BBCA.JK"
    assert "factors" in data


def test_scores_with_params():
    client = TestClient(create_app())
    r = client.get("/api/scores/BBCA.JK?technical=75&fundamental=80&sentiment=70")
    assert r.status_code == 200
    data = r.json()
    assert "composite_score" in data
    assert "recommendation" in data
    assert "explanation" in data


def test_recommend():
    client = TestClient(create_app())
    r = client.get("/api/recommend/BBCA.JK?technical=90&fundamental=85&sentiment=80")
    assert r.status_code == 200
    data = r.json()
    assert data["composite_score"] >= 80
    assert data["recommendation"] == "strong_buy"


def test_advisory():
    client = TestClient(create_app())
    r = client.get("/api/advisory?market_regime=growth")
    assert r.status_code == 200
    data = r.json()
    assert data["market_regime"] == "growth"
    assert data["screened"] == 0


@pytest.mark.isolated_db
def test_portfolio():
    client = TestClient(create_app())
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert "total_nav" in r.json()


@pytest.mark.isolated_db
def test_watchlist_add_get_remove():
    client = TestClient(create_app())

    # Seed instrument first (FK constraint fk_watchlist_ticker from migration 0022)
    from market.db.engine import get_sessionmaker
    from market.db.models import Exchange, Instrument
    from market.data.seed import seed_markets

    session = get_sessionmaker()()
    try:
        seed_markets(session)
        existing = session.get(Instrument, "BBCA.JK")
        if existing is None:
            session.add(Instrument(
                ticker="BBCA.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
                name="Bank Central Asia", is_active=True,
            ))
            session.commit()
    finally:
        session.close()

    # Clean up any existing entry for this ticker
    client.delete("/api/watchlist/BBCA.JK")

    # Add
    r = client.post("/api/watchlist", json={
        "ticker": "BBCA.JK",
        "is_favorite": True,
        "notes": "Test note",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "added"

    # Get — find our ticker
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    tickers = [w["ticker"] for w in r.json()]
    assert "BBCA.JK" in tickers

    # Remove
    r = client.delete("/api/watchlist/BBCA.JK")
    assert r.status_code == 200
    assert r.json()["status"] == "removed"

    # Verify removed
    r = client.get("/api/watchlist")
    tickers = [w["ticker"] for w in r.json()]
    assert "BBCA.JK" not in tickers


@pytest.mark.isolated_db
def test_watchlist_remove_not_found():
    client = TestClient(create_app())
    r = client.delete("/api/watchlist/NONEXIST")
    assert r.status_code == 404


def test_backtest_run():
    client = TestClient(create_app())
    r = client.get("/api/backtest/run?ticker=BBCA.JK&strategy=buy_hold&n_days=100")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "BBCA.JK"
    assert data["strategy"] == "buy_hold"
    assert "metrics" in data
    assert "equity_curve_sample" in data


def test_backtest_invalid_strategy():
    client = TestClient(create_app())
    r = client.get("/api/backtest/run?ticker=BBCA.JK&strategy=invalid")
    assert r.status_code == 422
