"""System endpoints: health, env, markets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from market.config import settings
from market.data.seed import DEFAULT_MARKETS
from market.api.cache import cache_stats, clear_all_cache

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}


@router.get("/env")
async def env() -> dict[str, Any]:
    return {
        "env": settings.env,
        "db_path": str(settings.resolved_db_path),
        "reporting_currency": settings.reporting_currency,
        "device": settings.device,
        "broker_adapter": settings.broker_adapter,
        "live_approved": settings.live_approved,
    }


@router.get("/markets")
async def markets() -> list[dict[str, Any]]:
    return list(DEFAULT_MARKETS)


@router.get("/cache/stats")
async def get_cache_stats() -> dict[str, Any]:
    """Cache statistics — hit rate, entries, misses."""
    return cache_stats()


@router.post("/cache/clear")
async def clear_cache() -> dict[str, Any]:
    """Clear all cached API results."""
    n = clear_all_cache()
    return {"cleared": n}
