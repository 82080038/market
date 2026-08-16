"""Global error handlers for FastAPI app (Gap #29).

Provides centralized exception handling with structured JSON error responses:
- ``HTTPException``: passthrough with standardized format
- ``RequestValidationError``: 422 with field-level detail
- ``CircuitBreakerError``: 503 Service Unavailable
- Generic ``Exception``: 500 with traceback logged but not leaked to client

All error responses follow the envelope:
    {
        "error": true,
        "status_code": int,
        "error_type": str,
        "detail": str,
        "path": str | null,
        "timestamp": str (ISO 8601 UTC),
    }
"""

from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from market.data.rate_limit import CircuitBreakerError

logger = logging.getLogger(__name__)


def _error_envelope(
    status_code: int,
    error_type: str,
    detail: Any,
    path: str | None = None,
) -> dict[str, Any]:
    """Build a standardized error response envelope."""
    return {
        "error": True,
        "status_code": status_code,
        "error_type": error_type,
        "detail": detail,
        "path": path,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on a FastAPI app.

    Args:
        app: FastAPI application instance.
    """

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle FastAPI HTTPException with standardized envelope."""
        logger.warning(
            "HTTPException %d on %s: %s",
            exc.status_code,
            request.url.path,
            exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(
                status_code=exc.status_code,
                error_type="http_exception",
                detail=str(exc.detail),
                path=request.url.path,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError,
    ) -> JSONResponse:
        """Handle 422 validation errors with field-level detail."""
        logger.warning(
            "Validation error on %s: %s",
            request.url.path,
            exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content=_error_envelope(
                status_code=422,
                error_type="validation_error",
                detail=exc.errors(),
                path=request.url.path,
            ),
        )

    @app.exception_handler(CircuitBreakerError)
    async def _circuit_breaker_handler(
        request: Request, exc: CircuitBreakerError,
    ) -> JSONResponse:
        """Handle circuit breaker trips (503 Service Unavailable)."""
        logger.error(
            "Circuit breaker tripped on %s: %s",
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=503,
            content=_error_envelope(
                status_code=503,
                error_type="circuit_breaker",
                detail=str(exc),
                path=request.url.path,
            ),
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(Exception)
    async def _generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unhandled exceptions — log full traceback, return 500."""
        tb = traceback.format_exc()
        logger.error(
            "Unhandled exception on %s: %s\n%s",
            request.url.path,
            exc,
            tb,
        )
        return JSONResponse(
            status_code=500,
            content=_error_envelope(
                status_code=500,
                error_type="internal_server_error",
                detail="An unexpected error occurred. Check server logs for details.",
                path=request.url.path,
            ),
        )
