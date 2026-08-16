"""Tests for global error handlers (Gap #29)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from market.api.error_handlers import register_error_handlers
from market.data.rate_limit import CircuitBreakerError


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with error handlers for testing."""
    app = FastAPI()

    @app.get("/raise-http-404")
    async def _raise_404() -> None:
        raise HTTPException(status_code=404, detail="Not found test")

    @app.get("/raise-http-500")
    async def _raise_500() -> None:
        raise HTTPException(status_code=500, detail="Server error test")

    @app.get("/raise-circuit")
    async def _raise_circuit() -> None:
        raise CircuitBreakerError("Circuit tripped — 10 consecutive errors")

    @app.get("/raise-generic")
    async def _raise_generic() -> None:
        raise RuntimeError("Unexpected boom")

    @app.get("/validation/{item_id}")
    async def _validation(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    register_error_handlers(app)
    return app


def _client() -> TestClient:
    """TestClient that lets exception handlers process errors (not re-raise)."""
    return TestClient(_make_app(), raise_server_exceptions=False)


def test_http_exception_404():
    """HTTPException 404 returns standardized envelope."""
    client = _client()
    r = client.get("/raise-http-404")
    assert r.status_code == 404
    data = r.json()
    assert data["error"] is True
    assert data["status_code"] == 404
    assert data["error_type"] == "http_exception"
    assert "Not found test" in data["detail"]
    assert data["path"] == "/raise-http-404"
    assert "timestamp" in data


def test_http_exception_500():
    """HTTPException 500 returns standardized envelope."""
    client = _client()
    r = client.get("/raise-http-500")
    assert r.status_code == 500
    data = r.json()
    assert data["error"] is True
    assert data["status_code"] == 500
    assert data["error_type"] == "http_exception"


def test_circuit_breaker_returns_503():
    """CircuitBreakerError returns 503 with Retry-After header."""
    client = _client()
    r = client.get("/raise-circuit")
    assert r.status_code == 503
    data = r.json()
    assert data["error"] is True
    assert data["error_type"] == "circuit_breaker"
    assert "Circuit tripped" in data["detail"]
    assert r.headers.get("Retry-After") == "60"


def test_generic_exception_returns_500():
    """Unhandled exceptions return 500 without leaking traceback."""
    client = _client()
    r = client.get("/raise-generic")
    assert r.status_code == 500
    data = r.json()
    assert data["error"] is True
    assert data["error_type"] == "internal_server_error"
    # Detail should NOT contain the actual exception message (security)
    assert "Unexpected boom" not in data["detail"]
    assert "check server logs" in data["detail"].lower()


def test_validation_error_returns_422():
    """RequestValidationError returns 422 with field-level detail."""
    client = _client()
    r = client.get("/validation/not-a-number")
    assert r.status_code == 422
    data = r.json()
    assert data["error"] is True
    assert data["status_code"] == 422
    assert data["error_type"] == "validation_error"
    # detail should be a list of validation errors
    assert isinstance(data["detail"], list)
    assert len(data["detail"]) > 0


def test_error_envelope_consistency():
    """All error responses have consistent envelope structure."""
    client = _client()
    for path in ["/raise-http-404", "/raise-http-500", "/raise-circuit", "/raise-generic"]:
        r = client.get(path)
        data = r.json()
        assert "error" in data
        assert "status_code" in data
        assert "error_type" in data
        assert "detail" in data
        assert "path" in data
        assert "timestamp" in data
        assert data["error"] is True
        assert data["status_code"] == r.status_code
        assert data["path"] == path
