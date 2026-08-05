"""Tests for data storage repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from market.data.contracts import NormalizedOHLCV
from market.data.storage import DataRepository
from market.db.models import Base


@pytest.fixture()
def repo():
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield DataRepository(session)
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_save_and_load_ohlcv(repo):
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    records = [
        NormalizedOHLCV(
            ticker="BBCA.JK",
            timestamp=ts,
            open=Decimal("8500"),
            high=Decimal("8600"),
            low=Decimal("8400"),
            close=Decimal("8550"),
            volume=1000000,
        ),
        NormalizedOHLCV(
            ticker="BBCA.JK",
            timestamp=ts + timedelta(days=1),
            open=Decimal("8550"),
            high=Decimal("8700"),
            low=Decimal("8500"),
            close=Decimal("8650"),
            volume=800000,
        ),
    ]
    count = repo.save_ohlcv(records)
    assert count == 2

    loaded = repo.load_ohlcv("BBCA.JK")
    assert len(loaded) == 2
    assert loaded[0].close == Decimal("8550")


def test_save_ohlcv_replace_existing(repo):
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    record = NormalizedOHLCV(
        ticker="TLKM.JK",
        timestamp=ts,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=500000,
    )
    repo.save_ohlcv([record])

    record.close = Decimal("106")
    repo.save_ohlcv([record])

    loaded = repo.load_ohlcv("TLKM.JK")
    assert len(loaded) == 1
    assert loaded[0].close == Decimal("106")


def test_list_tickers(repo):
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    repo.save_ohlcv([
        NormalizedOHLCV(
            ticker="A.JK",
            timestamp=ts,
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=100,
        ),
        NormalizedOHLCV(
            ticker="B.JK",
            timestamp=ts,
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=100,
        ),
    ])
    tickers = repo.list_tickers()
    assert set(tickers) == {"A.JK", "B.JK"}


def test_save_score(repo):
    repo.save_score("BBCA.JK", "technical", 75.5, {"trend": 25, "rsi": 20})
    repo.save_score("BBCA.JK", "fundamental", 80.0)
    # Just verify no exception
    assert True


def test_source_health_upsert(repo):
    repo.update_source_health("yahoo_finance", status="ok")
    repo.update_source_health("yahoo_finance", status="error", error_msg="timeout")
    repo.update_source_health("yahoo_finance", status="ok")
    # Just verify no exception
    assert True


def test_audit_log(repo):
    repo.audit("test.event", {"key": "value"}, actor="test")
    # Just verify no exception
    assert True
