"""Tests for market registry seed data."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from market.data.seed import DEFAULT_MARKETS, seed_markets
from market.db.models import Base, MarketRegistry


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_seed_markets_inserts_all(db_session):
    count = seed_markets(db_session)
    assert count == len(DEFAULT_MARKETS)

    idx = db_session.get(MarketRegistry, "XIDX")
    assert idx is not None
    assert idx.currency == "IDR"
    assert idx.lot_size == 100

    nys = db_session.get(MarketRegistry, "XNYS")
    assert nys is not None
    assert nys.currency == "USD"
    assert nys.supports_dst is True


def test_seed_markets_idempotent(db_session):
    first = seed_markets(db_session)
    second = seed_markets(db_session)
    assert first == len(DEFAULT_MARKETS)
    assert second == 0
