"""Shared utilities and Pydantic models for API routes."""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from pydantic import BaseModel

_JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


def to_jakarta(dt: Any) -> str | None:
    """Convert UTC datetime to Asia/Jakarta (WIB, UTC+7) ISO string.

    This is the presentation-layer conversion — backend logic stays in UTC,
    only API responses convert to local time for the frontend.

    Handles edge cases where DB returns string or Decimal instead of datetime.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return str(dt)
    if not isinstance(dt, datetime):
        return str(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_JAKARTA_TZ).isoformat()


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclass to dict for JSON serialization."""
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in obj.__dataclass_fields__:
            val = getattr(obj, f)
            result[f] = _dataclass_to_dict(val)
        return result
    if isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return to_jakarta(obj)
    return obj


class WatchlistItem(BaseModel):
    ticker: str
    is_favorite: bool = False
    notes: str | None = None


class ScoreInput(BaseModel):
    technical: float | None = None
    fundamental: float | None = None
    macro: float | None = None
    global_market: float | None = None
    relationship: float | None = None
    sentiment: float | None = None


def _generate_mock_instruments() -> dict[str, Any]:
    """Generate mock OHLCV data for testing autonomous backtest."""
    import pandas as pd

    np_rng = np.random.RandomState(42)
    dates = pd.bdate_range("2023-01-01", periods=300)
    instruments: dict[str, pd.DataFrame] = {}

    for ticker in ["BBCA.JK", "BBRI.JK", "TLKM.JK"]:
        close = 8000 + np_rng.randn(300).cumsum() * 50
        instruments[ticker] = pd.DataFrame({
            "open": close + np_rng.randn(300) * 10,
            "high": close + abs(np_rng.randn(300) * 20),
            "low": close - abs(np_rng.randn(300) * 20),
            "close": close,
            "volume": np_rng.randint(100000, 1000000, 300).astype(float),
        }, index=dates)

    return instruments
