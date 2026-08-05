"""Tests for data quality validation engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from market.data.contracts import NormalizedOHLCV
from market.data.validation import DataQualityEngine


def _make_record(
    ts: datetime,
    o: float = 100,
    h: float = 110,
    lo: float = 90,
    c: float = 105,
    v: int = 10000,
) -> NormalizedOHLCV:
    return NormalizedOHLCV(
        ticker="TEST.JK",
        timestamp=ts,
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(lo)),
        close=Decimal(str(c)),
        volume=v,
    )


def test_valid_data_accept():
    engine = DataQualityEngine()
    base = datetime(2024, 1, 2, tzinfo=UTC)
    records = [_make_record(base + timedelta(days=i)) for i in range(30)]
    result = engine.validate(records)
    assert result.score == 100.0
    assert result.action == "accept"
    assert result.anomalies == []


def test_empty_data_pause():
    engine = DataQualityEngine()
    result = engine.validate([])
    assert result.score == 0.0
    assert result.action == "pause"


def test_plausibility_low_gt_high():
    engine = DataQualityEngine()
    base = datetime(2024, 1, 2, tzinfo=UTC)
    records = [_make_record(base, h=80, lo=90)]
    result = engine.validate(records)
    assert result.action in ("flag", "pause")
    assert any("low_gt_high" in a for a in result.anomalies)


def test_gap_detection():
    engine = DataQualityEngine()
    base = datetime(2024, 1, 2, tzinfo=UTC)
    records = [
        _make_record(base),
        _make_record(base + timedelta(days=30)),
    ]
    result = engine.validate(records)
    assert any("gap:" in a for a in result.anomalies)


def test_volume_spike():
    engine = DataQualityEngine()
    base = datetime(2024, 1, 2, tzinfo=UTC)
    records = [_make_record(base + timedelta(days=i), v=10000) for i in range(20)]
    records.append(_make_record(base + timedelta(days=20), v=200000))
    result = engine.validate(records)
    assert any("volume_spike" in a for a in result.anomalies)
