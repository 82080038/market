"""Tests for multi-asset cross-market API routes (Gap #23)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from market.api.app import create_app


def test_multi_asset_analyze_basic():
    """POST /api/multi-asset/analyze runs on-demand cross-market analysis."""
    client = TestClient(create_app())
    # Generate synthetic returns for 3 markets
    import numpy as np
    np.random.seed(42)
    n = 100
    returns = {
        "MarketA": (np.random.randn(n) * 0.01).tolist(),
        "MarketB": (np.random.randn(n) * 0.015).tolist(),
        "MarketC": (np.random.randn(n) * 0.02).tolist(),
    }
    r = client.post("/api/multi-asset/analyze", json={
        "returns": returns,
        "max_lag": 5,
        "min_samples": 30,
    })
    assert r.status_code == 200
    data = r.json()
    assert "correlations" in data
    assert "lead_lag" in data
    assert "spillovers" in data
    assert "heatmap" in data
    # 3 markets → 3 pairs
    assert len(data["correlations"]) == 3
    # Heatmap should have all 3 markets
    assert len(data["heatmap"]) == 3
    for market in ("MarketA", "MarketB", "MarketC"):
        assert market in data["heatmap"]
        assert data["heatmap"][market][market] == 1.0


def test_multi_asset_analyze_with_volatilities():
    """POST /api/multi-asset/analyze with volatilities produces spillover results."""
    client = TestClient(create_app())
    import numpy as np
    np.random.seed(42)
    n = 100
    returns = {
        "MarketA": (np.random.randn(n) * 0.01).tolist(),
        "MarketB": (np.random.randn(n) * 0.015).tolist(),
    }
    volatilities = {
        "MarketA": (np.abs(np.random.randn(n)) * 0.01).tolist(),
        "MarketB": (np.abs(np.random.randn(n)) * 0.015).tolist(),
    }
    r = client.post("/api/multi-asset/analyze", json={
        "returns": returns,
        "volatilities": volatilities,
    })
    assert r.status_code == 200
    data = r.json()
    assert "spillovers" in data


def test_multi_asset_analyze_insufficient_data():
    """POST /api/multi-asset/analyze with too few samples returns empty results."""
    client = TestClient(create_app())
    r = client.post("/api/multi-asset/analyze", json={
        "returns": {"A": [0.01, 0.02], "B": [0.01, 0.02]},
        "min_samples": 30,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["correlations"] == []
    assert data["lead_lag"] == []


def test_multi_asset_correlations_endpoint():
    """GET /api/multi-asset/correlations returns list (may be empty)."""
    client = TestClient(create_app())
    r = client.get("/api/multi-asset/correlations")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_multi_asset_lead_lag_endpoint():
    """GET /api/multi-asset/lead-lag returns list."""
    client = TestClient(create_app())
    r = client.get("/api/multi-asset/lead-lag")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_multi_asset_spillover_endpoint():
    """GET /api/multi-asset/spillover returns list."""
    client = TestClient(create_app())
    r = client.get("/api/multi-asset/spillover")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_multi_asset_heatmap_endpoint():
    """GET /api/multi-asset/heatmap returns dict."""
    client = TestClient(create_app())
    r = client.get("/api/multi-asset/heatmap")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_multi_asset_correlations_with_asset_filter():
    """GET /api/multi-asset/correlations with asset filter returns filtered list."""
    client = TestClient(create_app())
    r = client.get("/api/multi-asset/correlations?asset=^GSPC&min_corr=0.0")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # All results should involve ^GSPC
    for item in data:
        assert item["asset_a"] == "^GSPC" or item["asset_b"] == "^GSPC"
