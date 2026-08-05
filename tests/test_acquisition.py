"""Tests for data acquisition engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from market.data.acquisition import DataAcquisitionEngine
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


def _mock_records(ticker: str = "TEST.JK", count: int = 5):
    base = datetime(2024, 1, 2, tzinfo=UTC)
    return [
        NormalizedOHLCV(
            ticker=ticker,
            timestamp=base + timedelta(days=i),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=10000,
        )
        for i in range(count)
    ]


def test_fetch_and_store_success(repo):
    engine = DataAcquisitionEngine()
    engine.set_repository(repo)

    mock_adapter = MagicMock()
    mock_adapter.fetch_ohlcv.return_value = _mock_records()

    engine._adapter = mock_adapter

    result = engine.fetch_and_store("TEST.JK")
    assert result["fetched"] == 5
    assert result["stored"] == 5
    assert result["action"] == "accept"
    assert result["quality_score"] == 100.0


def test_fetch_and_store_no_data(repo):
    engine = DataAcquisitionEngine()
    engine.set_repository(repo)

    mock_adapter = MagicMock()
    mock_adapter.fetch_ohlcv.return_value = []
    engine._adapter = mock_adapter

    result = engine.fetch_and_store("EMPTY.JK")
    assert result["fetched"] == 0
    assert result["stored"] == 0
    assert result["action"] == "pause"


def test_fetch_and_store_quality_pause(repo):
    engine = DataAcquisitionEngine()
    engine.set_repository(repo)

    mock_adapter = MagicMock()
    mock_adapter.fetch_ohlcv.return_value = [
        NormalizedOHLCV(
            ticker="BAD.JK",
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            open=Decimal("0"),
            high=Decimal("0"),
            low=Decimal("0"),
            close=Decimal("0"),
            volume=0,
        ),
    ]
    engine._adapter = mock_adapter

    result = engine.fetch_and_store("BAD.JK")
    assert result["action"] in ("flag", "pause")
    assert result["stored"] == 0 or result["stored"] == 1


def test_fetch_and_store_no_repository():
    engine = DataAcquisitionEngine()
    with pytest.raises(RuntimeError, match="Repository not set"):
        engine.fetch_and_store("TEST.JK")
