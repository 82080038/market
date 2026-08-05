"""Tests for multi-asset API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from market.api.app import create_app


def test_api_instruments_all():
    client = TestClient(create_app())
    r = client.get("/api/instruments")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 5


def test_api_instruments_by_market():
    client = TestClient(create_app())
    r = client.get("/api/instruments?market_mic=XIDX")
    assert r.status_code == 200
    data = r.json()
    assert all(d["market_mic"] == "XIDX" for d in data)


def test_api_instruments_by_asset_class():
    client = TestClient(create_app())
    r = client.get("/api/instruments?asset_class=equity")
    assert r.status_code == 200
    data = r.json()
    assert all(d["asset_class"] == "equity" for d in data)


def test_api_instruments_by_market_and_class():
    client = TestClient(create_app())
    r = client.get("/api/instruments?market_mic=XNAS&asset_class=equity")
    assert r.status_code == 200
    data = r.json()
    assert all(d["market_mic"] == "XNAS" for d in data)
    assert all(d["asset_class"] == "equity" for d in data)


def test_api_fx_risk():
    client = TestClient(create_app())
    r = client.get("/api/fx-risk?positions=IDR:50000000,USD:1000,SGD:500")
    assert r.status_code == 200
    data = r.json()
    assert data["base_currency"] == "IDR"
    assert data["total_exposure"] > 0
    assert len(data["exposures"]) == 3
