"""Data contracts (Pydantic v2) for normalized data (pustaka/18 §2.4).

These models define the wire format between acquisition → validation → storage.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class NormalizedOHLCV(BaseModel):
    """Normalized OHLCV record (pustaka/92 §4.1)."""

    ticker: str
    market_mic: str = "XIDX"
    asset_class: str = "equity"
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    adjusted_close: Decimal | None = None
    currency: str = "IDR"
    source: str = "yahoo_finance"
    data_quality_score: float | None = None


class DataQualityResult(BaseModel):
    """Result of data quality validation (pustaka/18 §2.2)."""

    ticker: str
    score: float = Field(ge=0, le=100)
    action: str = Field(pattern=r"^(accept|flag|pause)$")
    anomalies: list[str] = Field(default_factory=list)
    checked_at: datetime | None = None


class SourceHealthUpdate(BaseModel):
    """Source health update payload."""

    source: str
    status: str = "ok"
    error_msg: str | None = None
    rows_fetched: int = 0


class CorporateActionRecord(BaseModel):
    """Normalized corporate action record."""

    ticker: str
    action_type: str
    announce_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    payment_date: date | None = None
    value: float | None = None
    currency: str = "IDR"
    description: str | None = None
    source: str = "yahoo_finance"


class FXRateRecord(BaseModel):
    """FX rate record (pustaka/92 §4.3)."""

    base_currency: str
    quote_currency: str = "IDR"
    date: date
    rate: Decimal
    source: str = "yahoo_finance"
