"""Tests for Google Trends integration (Gap #27)."""

from __future__ import annotations

import pytest

from market.analysis.google_trends import (
    GoogleTrendsCollector,
    TrendsComparison,
    TrendsResult,
    trends_to_sentiment_signal,
)


@pytest.fixture
def collector() -> GoogleTrendsCollector:
    """Collector without pytrends installed (graceful degradation)."""
    return GoogleTrendsCollector()


def test_collector_not_available(collector: GoogleTrendsCollector):
    """Collector without pytrends is not available."""
    assert collector.available is False


def test_get_interest_empty_without_pytrends(collector: GoogleTrendsCollector):
    """get_interest_over_time returns empty result without pytrends."""
    result = collector.get_interest_over_time("saham BCA")
    assert result.is_empty
    assert result.keyword == "saham BCA"
    assert len(result.data) == 0


def test_compare_keywords_empty_without_pytrends(collector: GoogleTrendsCollector):
    """compare_keywords returns empty results without pytrends."""
    result = collector.compare_keywords(["saham", "investasi"])
    assert len(result.keywords) == 2
    assert all(r.is_empty for r in result.results.values())


def test_get_related_queries_empty_without_pytrends(collector: GoogleTrendsCollector):
    """get_related_queries returns empty without pytrends."""
    result = collector.get_related_queries("saham")
    assert result == {"top": [], "rising": []}


def test_trends_result_dataclass():
    """TrendsResult can be constructed with defaults."""
    result = TrendsResult(keyword="test", timeframe="today 3-m")
    assert result.keyword == "test"
    assert result.is_empty
    assert result.average_interest == 0.0
    assert result.peak_interest == 0
    assert result.trend_direction == "flat"


def test_trends_result_with_data():
    """TrendsResult with data is not empty."""
    result = TrendsResult(
        keyword="test", timeframe="today 3-m",
        data=[{"date": "2026-01-01", "value": 50}, {"date": "2026-01-02", "value": 75}],
        average_interest=62.5,
        peak_interest=75,
        peak_date="2026-01-02",
        trend_direction="up",
    )
    assert not result.is_empty
    assert len(result.data) == 2
    assert result.peak_interest == 75


def test_trends_comparison_dataclass():
    """TrendsComparison can be constructed."""
    comp = TrendsComparison(
        keywords=["a", "b"],
        timeframe="today 3-m",
        results={
            "a": TrendsResult(keyword="a", timeframe="today 3-m", average_interest=50),
            "b": TrendsResult(keyword="b", timeframe="today 3-m", average_interest=80),
        },
        winner="b",
    )
    assert comp.winner == "b"
    assert len(comp.keywords) == 2


def test_trends_to_sentiment_signal_up():
    """trends_to_sentiment_signal returns positive for 'up' trend."""
    result = TrendsResult(
        keyword="test", timeframe="today 3-m",
        data=[{"date": "x", "value": 50}],
        trend_direction="up",
    )
    assert trends_to_sentiment_signal(result) > 0


def test_trends_to_sentiment_signal_down():
    """trends_to_sentiment_signal returns negative for 'down' trend."""
    result = TrendsResult(
        keyword="test", timeframe="today 3-m",
        data=[{"date": "x", "value": 50}],
        trend_direction="down",
    )
    assert trends_to_sentiment_signal(result) < 0


def test_trends_to_sentiment_signal_flat():
    """trends_to_sentiment_signal returns 0 for 'flat' trend."""
    result = TrendsResult(
        keyword="test", timeframe="today 3-m",
        data=[{"date": "x", "value": 50}],
        trend_direction="flat",
    )
    assert trends_to_sentiment_signal(result) == 0.0


def test_trends_to_sentiment_signal_empty():
    """trends_to_sentiment_signal returns 0 for empty result."""
    result = TrendsResult(keyword="test", timeframe="today 3-m")
    assert trends_to_sentiment_signal(result) == 0.0


def test_collector_geo_default():
    """Default geo is Indonesia."""
    collector = GoogleTrendsCollector()
    assert collector.geo == "ID"


def test_collector_custom_geo():
    """Custom geo can be set."""
    collector = GoogleTrendsCollector(geo="US")
    assert collector.geo == "US"
