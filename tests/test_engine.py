"""Tests for database engine and session management."""

from __future__ import annotations

from sqlalchemy.orm import Session

from market.db.engine import _make_sqlite_engine, get_session
from market.db.models import Base, MarketRegistry


def test_make_engine_creates_tables():
    engine = _make_sqlite_engine(":memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        market = MarketRegistry(
            mic_code="XIDX",
            country_code="IDN",
            timezone="Asia/Jakarta",
            trading_hours="09:00-15:50",
            settlement_cycle=2,
            currency="IDR",
        )
        session.add(market)
        session.commit()
        found = session.get(MarketRegistry, "XIDX")
        assert found is not None
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_get_session_yields_and_closes():
    engine = _make_sqlite_engine(":memory:")
    Base.metadata.create_all(engine)

    # Override get_session to use our in-memory engine
    import market.db.engine as eng_mod

    original_sm = eng_mod.get_sessionmaker
    eng_mod.get_sessionmaker = lambda: type(
        "SM",
        (),
        {"__call__": lambda self: Session(engine)},
    )()
    try:
        gen = get_session()
        session = next(gen)
        assert isinstance(session, Session)
        gen.close()
    finally:
        eng_mod.get_sessionmaker = original_sm
    Base.metadata.drop_all(engine)
    engine.dispose()
