"""Tests for feature store freshness monitoring (Gap #36)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from market.mlops.feature_store import (
    FeatureDefinition,
    FeatureSet,
    FeatureStore,
    FreshnessStatus,
)


def _make_ohlcv(n: int = 100) -> pd.DataFrame:
    """Make sample OHLCV data."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    close = 100 + rng.standard_normal(n).cumsum()
    return pd.DataFrame({
        "open": close + rng.standard_normal(n) * 0.5,
        "high": close + rng.uniform(0.1, 1.5, n),
        "low": close - rng.uniform(0.1, 1.5, n),
        "close": close,
        "volume": rng.integers(100_000, 1_000_000, n),
    }, index=dates)


def test_freshness_status_enum():
    """FreshnessStatus has expected values."""
    assert FreshnessStatus.FRESH.value == "FRESH"
    assert FreshnessStatus.STALE.value == "STALE"
    assert FreshnessStatus.EXPIRED.value == "EXPIRED"
    assert FreshnessStatus.MISSING.value == "MISSING"
    assert FreshnessStatus.ERROR.value == "ERROR"


def test_check_freshness_missing():
    """check_freshness returns MISSING for non-existent key."""
    store = FeatureStore()
    report = store.check_freshness("nonexistent")
    assert report.status == FreshnessStatus.MISSING
    assert "not in cache" in report.message


def test_check_freshness_fresh():
    """check_freshness returns FRESH for newly cached feature set."""
    store = FeatureStore(max_fresh_age_hours=24)
    data = _make_ohlcv()
    fs = store.compute(data)
    key = store.cache(fs)
    report = store.check_freshness(key)
    assert report.status == FreshnessStatus.FRESH
    assert report.age_hours is not None
    assert report.age_hours < 1


def test_check_freshness_stale():
    """check_freshness returns STALE for old feature set."""
    store = FeatureStore(max_fresh_age_hours=24)
    data = _make_ohlcv()

    # Create a feature set with old computed_at
    old_time = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    fs = FeatureSet(
        name="test",
        version="1.0.0",
        features=pd.DataFrame({"a": [1, 2]}),
        computed_at=old_time,
    )
    key = store.cache(fs, "stale_key")
    report = store.check_freshness(key)
    assert report.status == FreshnessStatus.STALE
    assert report.age_hours is not None
    assert report.age_hours >= 30


def test_check_freshness_expired():
    """check_freshness returns EXPIRED for very old feature set."""
    store = FeatureStore(max_fresh_age_hours=24)
    old_time = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
    fs = FeatureSet(
        name="test",
        version="1.0.0",
        features=pd.DataFrame({"a": [1, 2]}),
        computed_at=old_time,
    )
    key = store.cache(fs, "expired_key")
    report = store.check_freshness(key)
    assert report.status == FreshnessStatus.EXPIRED


def test_check_freshness_error():
    """check_freshness returns ERROR for feature set with errors."""
    store = FeatureStore()
    fs = FeatureSet(
        name="test",
        version="1.0.0",
        features=pd.DataFrame({"a": [1, 2]}),
        has_errors=True,
    )
    key = store.cache(fs, "error_key")
    report = store.check_freshness(key)
    assert report.status == FreshnessStatus.ERROR


def test_check_all_freshness():
    """check_all_freshness returns reports for all cached keys."""
    store = FeatureStore(max_fresh_age_hours=24)

    # Fresh
    fs1 = FeatureSet(
        name="fresh", version="1.0.0",
        features=pd.DataFrame({"a": [1]}),
        computed_at=datetime.now(UTC).isoformat(),
    )
    store.cache(fs1, "fresh_key")

    # Stale
    old_time = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    fs2 = FeatureSet(
        name="stale", version="1.0.0",
        features=pd.DataFrame({"a": [1]}),
        computed_at=old_time,
    )
    store.cache(fs2, "stale_key")

    reports = store.check_all_freshness()
    assert len(reports) == 2
    statuses = {r.status for r in reports}
    assert FreshnessStatus.FRESH in statuses
    assert FreshnessStatus.STALE in statuses


def test_get_stale_keys():
    """get_stale_keys returns only stale/expired keys."""
    store = FeatureStore(max_fresh_age_hours=24)

    fs_fresh = FeatureSet(
        name="fresh", version="1.0.0",
        features=pd.DataFrame({"a": [1]}),
        computed_at=datetime.now(UTC).isoformat(),
    )
    store.cache(fs_fresh, "fresh_key")

    old_time = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    fs_stale = FeatureSet(
        name="stale", version="1.0.0",
        features=pd.DataFrame({"a": [1]}),
        computed_at=old_time,
    )
    store.cache(fs_stale, "stale_key")

    stale_keys = store.get_stale_keys()
    assert "stale_key" in stale_keys
    assert "fresh_key" not in stale_keys


def test_evict_stale():
    """evict_stale removes stale entries and returns count."""
    store = FeatureStore(max_fresh_age_hours=24)

    fs_fresh = FeatureSet(
        name="fresh", version="1.0.0",
        features=pd.DataFrame({"a": [1]}),
        computed_at=datetime.now(UTC).isoformat(),
    )
    store.cache(fs_fresh, "fresh_key")

    old_time = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
    fs_expired = FeatureSet(
        name="expired", version="1.0.0",
        features=pd.DataFrame({"a": [1]}),
        computed_at=old_time,
    )
    store.cache(fs_expired, "expired_key")

    evicted = store.evict_stale()
    assert evicted == 1
    assert "expired_key" not in store._cache
    assert "fresh_key" in store._cache


def test_compute_tracks_source_data_last_date():
    """compute() sets source_data_last_date on FeatureSet."""
    store = FeatureStore()
    data = _make_ohlcv(50)
    fs = store.compute(data)
    assert fs.source_data_last_date is not None
    assert "2026" in fs.source_data_last_date


def test_check_freshness_includes_source_age():
    """check_freshness report includes source data age."""
    store = FeatureStore(max_fresh_age_hours=24)
    old_source = (datetime.now(UTC) - timedelta(days=5)).date().isoformat()
    fs = FeatureSet(
        name="test", version="1.0.0",
        features=pd.DataFrame({"a": [1]}),
        computed_at=datetime.now(UTC).isoformat(),
        source_data_last_date=old_source,
    )
    key = store.cache(fs, "test_key")
    report = store.check_freshness(key)
    assert report.source_data_last_date == old_source
    assert report.source_age_hours is not None
    assert report.source_age_hours >= 5 * 24


def test_age_hours_helper():
    """_age_hours correctly computes age from ISO timestamp."""
    recent = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    age = FeatureStore._age_hours(recent)
    assert age is not None
    assert 1.9 <= age <= 2.1


def test_age_hours_invalid():
    """_age_hours returns None for invalid timestamp."""
    assert FeatureStore._age_hours(None) is None
    assert FeatureStore._age_hours("invalid") is None
    assert FeatureStore._age_hours("") is None
