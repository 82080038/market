"""TTL cache for expensive API endpoint results.

Many analysis engines (Astronacci, PatternDetector, RecommendationEngine,
etc.) recompute from scratch on every API call. This module provides a
simple in-memory TTL cache so repeated calls within the validity window
return cached results instantly.

Usage in route handlers::

    from market.api.cache import ttl_cache

    @router.get("/expensive")
    @ttl_cache(ttl_seconds=3600, key_prefix="astronacci")
    async def expensive_endpoint(...):
        ...

For per-ticker caching, pass ``key_suffix`` in the handler::

    @ttl_cache(ttl_seconds=300)
    async def data_quality(ticker: str, ...):
        ...
    # cache key auto-includes function args
"""

from __future__ import annotations

import functools
import hashlib
import json
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

# Global cache store: {key: (timestamp, data)}
_cache_store: dict[str, tuple[float, Any]] = {}
_cache_lock = Lock()

# Cache stats
_cache_hits = 0
_cache_misses = 0


def _make_key(prefix: str, args: tuple, kwargs: dict) -> str:
    """Build a stable cache key from prefix + function arguments."""
    # Extract simple scalar args that are safe to hash
    safe_args = []
    for a in args:
        if isinstance(a, (str, int, float, bool, type(None))):
            safe_args.append(a)
        elif isinstance(a, dict):
            # Sort dict keys for stable hash
            safe_args.append(json.dumps(a, sort_keys=True, default=str))
        else:
            # Skip non-serializable objects (Session, etc) — use class name only
            safe_args.append(type(a).__name__)

    key_data = f"{prefix}:{safe_args}:{json.dumps(kwargs, sort_keys=True, default=str)}"
    return hashlib.md5(key_data.encode()).hexdigest()


def ttl_cache(ttl_seconds: int = 300, key_prefix: str = "") -> Callable:
    """Decorator: cache async endpoint result for ttl_seconds.

    Args:
        ttl_seconds: How long to keep the cached result.
        key_prefix: Optional prefix for cache key namespace.
    """
    def decorator(func: Callable) -> Callable:
        prefix = key_prefix or f"{func.__module__}.{func.__name__}"

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            global _cache_hits, _cache_misses

            # Skip caching for non-GET (mutation) calls
            # Detect by checking if 'body' or 'request' is in kwargs
            if "body" in kwargs or "request" in kwargs:
                return await func(*args, **kwargs)

            # Build cache key — skip Session/Request/Response objects
            cache_args = []
            for a in args:
                if hasattr(a, "execute") or hasattr(a, "query") or "Request" in type(a).__name__:
                    continue  # Skip SQLAlchemy Session, Request objects
                cache_args.append(a)
            cache_kwargs = {}
            for k, v in kwargs.items():
                if hasattr(v, "execute") or hasattr(v, "query") or "Request" in type(v).__name__:
                    continue
                cache_kwargs[k] = v
            key = _make_key(prefix, tuple(cache_args), cache_kwargs)

            now = time.monotonic()
            with _cache_lock:
                if key in _cache_store:
                    ts, data = _cache_store[key]
                    if now - ts < ttl_seconds:
                        _cache_hits += 1
                        return data
                    else:
                        del _cache_store[key]
                _cache_misses += 1

            # Compute fresh
            result = await func(*args, **kwargs)

            # Store
            with _cache_lock:
                _cache_store[key] = (now, result)

            return result

        # Expose cache control methods
        wrapper._cache_clear = lambda: _clear_prefix(prefix)
        return wrapper

    return decorator


def _clear_prefix(prefix: str) -> int:
    """Clear all cache entries with given prefix."""
    cleared = 0
    with _cache_lock:
        keys_to_remove = [k for k in _cache_store if k.startswith(prefix)]
        for k in keys_to_remove:
            del _cache_store[k]
            cleared += 1
    return cleared


def clear_all_cache() -> int:
    """Clear entire cache. Returns number of entries removed."""
    with _cache_lock:
        n = len(_cache_store)
        _cache_store.clear()
        return n


def cache_stats() -> dict[str, Any]:
    """Return cache statistics."""
    with _cache_lock:
        return {
            "entries": len(_cache_store),
            "hits": _cache_hits,
            "misses": _cache_misses,
            "hit_rate": round(_cache_hits / max(_cache_hits + _cache_misses, 1), 4),
        }
