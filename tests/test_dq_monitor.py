"""Tests for data quality monitor (Gap #10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from market.data.dq_monitor import (
    DataQualityMonitor,
    DataQualityResult,
    DQ_ERROR_THRESHOLD,
    DQ_WARNING_THRESHOLD,
)


def _make_ohlcv(days: int = 60, start_price: float = 100.0, zero_vol_days: int = 0) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    dates = pd.bdate_range(end=datetime.now(UTC), periods=days)
    prices = start_price + np.random.randn(days).cumsum() * 0.5
    volumes = np.random.randint(100000, 1000000, days).astype(float)
    if zero_vol_days > 0:
        # Put zero-vol at the END so they fall within the recent window
        volumes[-zero_vol_days:] = 0
    return pd.DataFrame(
        {"close": prices, "volume": volumes},
        index=dates,
    )


def test_dq_monitor_good_data():
    """DQ monitor returns high score for clean data."""
    np.random.seed(42)
    df = _make_ohlcv(60)
    monitor = DataQualityMonitor()
    result = monitor.assess_ticker("BBCA.JK", df)

    assert result.ticker == "BBCA.JK"
    assert result.dq_score > 0.7
    assert result.severity == "ok"
    assert result.to_alert() is None


def test_dq_monitor_stale_data():
    """DQ monitor detects stale data."""
    dates = pd.bdate_range(end=datetime.now(UTC) - timedelta(days=30), periods=60)
    df = pd.DataFrame(
        {"close": np.linspace(100, 110, 60), "volume": np.full(60, 500000.0)},
        index=dates,
    )
    monitor = DataQualityMonitor()
    result = monitor.assess_ticker("STALE.JK", df)

    assert result.staleness_days >= 30
    assert result.freshness < 0.5
    assert "Stale data" in " ".join(result.issues)


def test_dq_monitor_zero_volume():
    """DQ monitor detects high zero-volume ratio."""
    df = _make_ohlcv(60, zero_vol_days=25)
    monitor = DataQualityMonitor()
    result = monitor.assess_ticker("ZEROVOL.JK", df)

    assert result.zero_volume_count == 25
    assert result.volume_quality < 0.5
    assert any("zero-volume" in issue for issue in result.issues)


def test_dq_monitor_extreme_price_changes():
    """DQ monitor detects extreme price changes."""
    dates = pd.bdate_range(end=datetime.now(UTC), periods=60)
    prices = np.full(60, 100.0)
    prices[30] = 130  # +30% spike
    prices[31] = 90   # -30% drop
    df = pd.DataFrame(
        {"close": prices, "volume": np.full(60, 500000.0)},
        index=dates,
    )
    monitor = DataQualityMonitor()
    result = monitor.assess_ticker("EXTREME.JK", df)

    assert result.extreme_change_count >= 2
    assert result.outlier_free < 1.0
    assert any("extreme" in issue for issue in result.issues)


def test_dq_monitor_empty_data():
    """DQ monitor handles empty DataFrame gracefully."""
    monitor = DataQualityMonitor()
    result = monitor.assess_ticker("EMPTY.JK", pd.DataFrame())

    assert result.dq_score == 0.0
    assert result.row_count == 0
    assert "No data available" in result.issues


def test_dq_monitor_completeness():
    """DQ monitor calculates completeness correctly."""
    # Only 20 days out of ~42 expected (60 lookback * 5/7)
    dates = pd.bdate_range(end=datetime.now(UTC), periods=20)
    df = pd.DataFrame(
        {"close": np.linspace(100, 110, 20), "volume": np.full(20, 500000.0)},
        index=dates,
    )
    monitor = DataQualityMonitor(lookback_days=60)
    result = monitor.assess_ticker("PARTIAL.JK", df)

    assert result.completeness < 0.6
    assert result.missing_days > 0


def test_dq_monitor_severity_thresholds():
    """Severity is correctly determined by DQ score."""
    result_ok = DataQualityResult(ticker="OK", dq_score=0.9)
    assert result_ok.severity == "ok"

    result_warn = DataQualityResult(ticker="WARN", dq_score=0.6)
    assert result_warn.severity == "warning"

    result_err = DataQualityResult(ticker="ERR", dq_score=0.3)
    assert result_err.severity == "error"


def test_dq_monitor_to_alert():
    """to_alert() returns None for good data, dict for bad data."""
    result_good = DataQualityResult(ticker="GOOD", dq_score=0.9)
    assert result_good.to_alert() is None

    result_bad = DataQualityResult(
        ticker="BAD", dq_score=0.4, issues=["Stale data: 20 days old"],
    )
    alert = result_bad.to_alert()
    assert alert is not None
    assert alert["type"] == "data_quality_drop"
    assert alert["severity"] == "error"
    assert alert["ticker"] == "BAD"
    assert alert["dq_score"] == 0.4


def test_dq_monitor_batch():
    """assess_batch processes multiple tickers."""
    np.random.seed(42)
    data = {
        "GOOD.JK": _make_ohlcv(60),
        "BAD.JK": _make_ohlcv(60, zero_vol_days=30),
    }
    monitor = DataQualityMonitor()
    results = monitor.assess_batch(data)

    assert len(results) == 2
    # Sorted by DQ score ascending — BAD should be first
    assert results[0].dq_score <= results[1].dq_score


def test_dq_monitor_generate_alerts():
    """generate_alerts returns only tickers with DQ issues."""
    np.random.seed(42)
    data = {
        "GOOD.JK": _make_ohlcv(60),
        "BAD.JK": _make_ohlcv(60, zero_vol_days=40),
    }
    monitor = DataQualityMonitor()
    alerts = monitor.generate_alerts(data)

    # BAD.JK should generate an alert (zero-volume issue)
    tickers = [a["ticker"] for a in alerts]
    assert "BAD.JK" in tickers
    for alert in alerts:
        assert alert["type"] == "data_quality_drop"
        # Alert fires when dq_score < threshold OR there are issues
        assert alert["dq_score"] < DQ_WARNING_THRESHOLD or alert.get("issues")


def test_dq_monitor_composite_score_weights():
    """Composite score is weighted sum of components."""
    result = DataQualityResult(
        ticker="TEST",
        dq_score=0.0,
        completeness=1.0,
        gap_free=1.0,
        outlier_free=1.0,
        volume_quality=1.0,
        freshness=1.0,
    )
    # Manually compute
    from market.data.dq_monitor import DQ_WEIGHTS
    expected = sum(DQ_WEIGHTS.values())
    assert abs(expected - 1.0) < 0.01  # weights should sum to ~1.0
