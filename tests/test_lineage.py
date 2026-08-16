"""Tests for data lineage & provenance tracking (Gap #35)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from market.data.lineage import DataLineage, LineageTracker, LINEAGE_VERSION


def test_data_lineage_defaults():
    """DataLineage has sensible defaults."""
    lineage = DataLineage(source="yahoo_finance", ticker="BBCA.JK")
    assert lineage.source == "yahoo_finance"
    assert lineage.ticker == "BBCA.JK"
    assert lineage.row_count == 0
    assert lineage.quality_score == 0.0
    assert lineage.lineage_version == LINEAGE_VERSION
    assert lineage.fetched_at  # auto-generated


def test_data_lineage_to_dict():
    """DataLineage serializes to dict."""
    lineage = DataLineage(
        source="FRED",
        ticker="GDP",
        row_count=100,
        quality_score=0.95,
        parameters={"start": "2020-01-01"},
    )
    d = lineage.to_dict()
    assert d["source"] == "FRED"
    assert d["ticker"] == "GDP"
    assert d["row_count"] == 100
    assert d["quality_score"] == 0.95
    assert d["parameters"] == {"start": "2020-01-01"}


def test_data_lineage_checksum():
    """Checksum is computed from first and last records."""
    @dataclass
    class Record:
        date: str
        close: float

    records = [
        Record("2024-01-01", 100.0),
        Record("2024-01-02", 101.0),
        Record("2024-01-03", 102.0),
    ]
    lineage = DataLineage(source="yahoo_finance", ticker="BBCA.JK")
    checksum = lineage.compute_checksum(records)
    assert len(checksum) == 32  # MD5 hex
    assert lineage.checksum == checksum


def test_data_lineage_checksum_empty():
    """Checksum of empty records is empty string."""
    lineage = DataLineage(source="yahoo_finance", ticker="BBCA.JK")
    assert lineage.compute_checksum([]) == ""


def test_lineage_tracker_record():
    """LineageTracker.record creates and stores a lineage entry."""
    tracker = LineageTracker()
    lineage = tracker.record(
        source="yahoo_finance",
        ticker="BBCA.JK",
        row_count=1000,
        stored_count=995,
        quality_score=0.95,
        parameters={"period": "max"},
        storage_table="stock_prices",
    )
    assert len(tracker.records) == 1
    assert tracker.records[0].ticker == "BBCA.JK"
    assert tracker.records[0].row_count == 1000


def test_lineage_tracker_persist_to_repository():
    """LineageTracker persists to repository.audit()."""
    repo = MagicMock()
    tracker = LineageTracker(repository=repo, fetcher_version="2.0.0")
    tracker.record(
        source="yahoo_finance",
        ticker="TLKM.JK",
        row_count=500,
        quality_score=0.9,
    )
    repo.audit.assert_called_once()
    call_args = repo.audit.call_args
    assert call_args.kwargs["event_type"] == "data.lineage"
    payload = call_args.kwargs["payload"]
    assert payload["source"] == "yahoo_finance"
    assert payload["ticker"] == "TLKM.JK"
    assert payload["fetcher_version"] == "2.0.0"


def test_lineage_tracker_no_repository():
    """LineageTracker without repository doesn't crash."""
    tracker = LineageTracker()
    tracker.record(source="FRED", ticker="GDP", row_count=50)
    assert len(tracker.records) == 1


def test_lineage_tracker_get_by_ticker():
    """get_lineage filters by ticker."""
    tracker = LineageTracker()
    tracker.record(source="yahoo_finance", ticker="BBCA.JK", row_count=100)
    tracker.record(source="yahoo_finance", ticker="TLKM.JK", row_count=200)
    tracker.record(source="yahoo_finance", ticker="BBCA.JK", row_count=150)

    bbca = tracker.get_lineage("BBCA.JK")
    assert len(bbca) == 2
    assert all(r.ticker == "BBCA.JK" for r in bbca)

    all_records = tracker.get_lineage()
    assert len(all_records) == 3


def test_lineage_tracker_clear():
    """clear() removes in-memory records."""
    tracker = LineageTracker()
    tracker.record(source="yahoo_finance", ticker="BBCA.JK")
    assert len(tracker.records) == 1
    tracker.clear()
    assert len(tracker.records) == 0


def test_lineage_tracker_set_repository():
    """set_repository updates the repository for persistence."""
    tracker = LineageTracker()
    tracker.record(source="yahoo_finance", ticker="BBCA.JK")  # no persist

    repo = MagicMock()
    tracker.set_repository(repo)
    tracker.record(source="yahoo_finance", ticker="TLKM.JK")  # persists
    repo.audit.assert_called_once()


def test_lineage_tracker_error_handling():
    """LineageTracker handles repository errors gracefully."""
    repo = MagicMock()
    repo.audit.side_effect = RuntimeError("DB error")
    tracker = LineageTracker(repository=repo)
    # Should not raise
    tracker.record(source="yahoo_finance", ticker="BBCA.JK")
    assert len(tracker.records) == 1  # still in memory


def test_lineage_with_records_checksum():
    """LineageTracker computes checksum when records are provided."""
    tracker = LineageTracker()
    records = [{"date": "2024-01-01", "close": 100}, {"date": "2024-01-02", "close": 101}]
    lineage = tracker.record(
        source="yahoo_finance",
        ticker="BBCA.JK",
        row_count=2,
        records=records,
    )
    assert len(lineage.checksum) == 32
