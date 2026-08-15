"""Tests for database models and engine."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from market.db.models import (
    OHLCV,
    Base,
    Exchange,
    FXRate,
    Instrument,
    SourceHealth,
)


@pytest.fixture()
def db_session():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_exchange(db_session):
    market = Exchange(
        mic_code="XIDX",
        name="Indonesia Stock Exchange",
        country_code="IDN",
        timezone="Asia/Jakarta",
        trading_hours="09:00-15:50",
        settlement_cycle=2,
        currency="IDR",
        data_suffix=".JK",
    )
    db_session.add(market)
    db_session.commit()

    found = db_session.get(Exchange, "XIDX")
    assert found is not None
    assert found.currency == "IDR"


def test_create_instrument(db_session):
    db_session.add(
        Exchange(
            mic_code="XIDX",
            name="Indonesia Stock Exchange",
            country_code="IDN",
            timezone="Asia/Jakarta",
            trading_hours="09:00-15:50",
            settlement_cycle=2,
            currency="IDR",
        )
    )
    db_session.commit()

    inst = Instrument(
        ticker="BBCA.JK",
        exchange_mic="XIDX",
        asset_class="EQUITY",
        name="Bank Central Asia",
        currency="IDR",
        is_active=True,
        sector="Financials",
    )
    db_session.add(inst)
    db_session.commit()

    found = db_session.get(Instrument, "BBCA.JK")
    assert found is not None
    assert found.name == "Bank Central Asia"


def test_create_ohlcv(db_session):
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    record = OHLCV(
        ticker="BBCA.JK",
        timestamp=ts,
        timeframe="1d",
        open=Decimal("8500"),
        high=Decimal("8600"),
        low=Decimal("8400"),
        close=Decimal("8550"),
        volume=1000000,
        adjusted_close=Decimal("8550"),
        source="yahoo_finance",
    )
    db_session.add(record)
    db_session.commit()

    found = db_session.query(OHLCV).filter_by(ticker="BBCA.JK").one()
    assert found.close == Decimal("8550")
    assert found.volume == 1000000


def test_create_fx_rate(db_session):
    fx = FXRate(
        base_currency="USD",
        quote_currency="IDR",
        date=date(2024, 1, 2),
        rate=Decimal("15800.50"),
    )
    db_session.add(fx)
    db_session.commit()

    found = db_session.query(FXRate).one()
    assert found.rate == Decimal("15800.50")


def test_source_health_upsert(db_session):
    sh = SourceHealth(source="yahoo_finance", status="ok", total_fetches=1)
    db_session.add(sh)
    db_session.commit()

    found = db_session.get(SourceHealth, "yahoo_finance")
    assert found is not None
    assert found.total_fetches == 1
