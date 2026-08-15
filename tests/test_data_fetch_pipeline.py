"""Integration tests for DataFetchPipeline — E2E via event broker with mocked yfinance.

Tests the full event flow: emit event → DataFetchPipeline handler → DB insert.
Uses in-memory SQLite DB by patching get_sessionmaker to return our test session.
Mocks yfinance.download to avoid real API calls.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from market.core.events import Event, EventBroker
from market.data.seed import seed_markets
from market.db.models import Base, Instrument, MacroData, OHLCV


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def test_engine():
    """Create in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def test_session_factory(test_engine):
    """Create a sessionmaker bound to the in-memory engine."""
    return sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture()
def patched_sessionmaker(test_session_factory):
    """Patch get_sessionmaker to return our in-memory SQLite sessionmaker.

    DataFetchPipeline imports get_sessionmaker inside method bodies
    (deferred import), so patching market.db.engine.get_sessionmaker
    is sufficient — the import will resolve to our patched version.

    Also patches settings.db_backend to 'sqlite' so DataRepository
    uses OHLCV model (not StockPrice) for in-memory SQLite tests.
    """
    test_sm = test_session_factory

    def fake_get_sessionmaker():
        return test_sm

    with patch("market.db.engine.get_sessionmaker", side_effect=fake_get_sessionmaker):
        with patch("market.data.storage._is_postgres", return_value=False):
            # Patch db_backend property on Settings class so data_fetch.py
            # also sees 'sqlite' and uses OHLCV model for queries
            from market.config import Settings
            with patch.object(Settings, "db_backend", new_callable=lambda: property(lambda self: "sqlite")):
                yield test_sm


def _mock_yf_df(ticker: str, rows: int = 3) -> pd.DataFrame:
    """Create a mock yfinance download DataFrame."""
    base = datetime(2024, 1, 2, tzinfo=UTC)
    dates = [base + timedelta(days=i) for i in range(rows)]
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(rows)],
            "High": [110.0 + i for i in range(rows)],
            "Low": [90.0 + i for i in range(rows)],
            "Close": [105.0 + i for i in range(rows)],
            "Adj Close": [105.0 + i for i in range(rows)],
            "Volume": [10000 * (i + 1) for i in range(rows)],
        },
        index=pd.DatetimeIndex(dates, name="Date"),
    )


def _seed_test_instruments(session: Session) -> None:
    """Seed minimal instruments for EOD fetch test."""
    seed_markets(session)
    instruments = [
        Instrument(
            ticker="BBCA.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
            name="Bank Central Asia", is_active=True,
        ),
        Instrument(
            ticker="BBRI.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
            name="Bank Rakyat Indonesia", is_active=True,
        ),
    ]
    for inst in instruments:
        session.add(inst)
    session.commit()


# ── EOD Fetch (on_fetch_requested) ──────────────────────────────────────


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_eod_fetch_inserts_ohlcv(mock_download, mock_open, patched_sessionmaker):
    """Emit data.fetch.requested → DataFetchPipeline → OHLCV rows in DB."""
    from market.pipelines.data_fetch import DataFetchPipeline

    # Seed instruments
    session = patched_sessionmaker()
    try:
        _seed_test_instruments(session)
    finally:
        session.close()

    mock_download.side_effect = lambda ticker, **kw: _mock_yf_df(ticker, rows=3)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.requested", pipeline.on_fetch_requested)

    test_broker.emit("data.fetch.requested", {})

    session = patched_sessionmaker()
    try:
        bbca_rows = session.execute(
            select(OHLCV).where(OHLCV.ticker == "BBCA.JK")
        ).scalars().all()
        assert len(bbca_rows) == 3
        assert bbca_rows[0].open == Decimal("100")
        assert bbca_rows[0].close == Decimal("105")

        bbri_rows = session.execute(
            select(OHLCV).where(OHLCV.ticker == "BBRI.JK")
        ).scalars().all()
        assert len(bbri_rows) == 3
    finally:
        session.close()


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_eod_fetch_skips_recent(mock_download, mock_open, patched_sessionmaker):
    """Tickers with data ≤1 day old should be skipped."""
    from market.pipelines.data_fetch import DataFetchPipeline

    session = patched_sessionmaker()
    try:
        _seed_test_instruments(session)

        now = datetime.now(UTC)
        session.add(OHLCV(
            ticker="BBCA.JK", timestamp=now, timeframe="1d",
            open=Decimal("8000"), high=Decimal("8100"), low=Decimal("7900"),
            close=Decimal("8050"), volume=1000000, source="yahoo_finance",
        ))
        session.commit()
    finally:
        session.close()

    mock_download.side_effect = lambda ticker, **kw: _mock_yf_df(ticker, rows=2)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.requested", pipeline.on_fetch_requested)

    test_broker.emit("data.fetch.requested", {})

    session = patched_sessionmaker()
    try:
        bbca_rows = session.execute(
            select(OHLCV).where(OHLCV.ticker == "BBCA.JK")
        ).scalars().all()
        assert len(bbca_rows) == 1  # not fetched again
    finally:
        session.close()


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_eod_fetch_partial_failure(mock_download, mock_open, patched_sessionmaker):
    """If one ticker fails, others should still succeed."""
    from market.pipelines.data_fetch import DataFetchPipeline

    session = patched_sessionmaker()
    try:
        _seed_test_instruments(session)
    finally:
        session.close()

    def download_side_effect(ticker, **kwargs):
        if ticker == "BBCA.JK":
            return _mock_yf_df(ticker, rows=2)
        raise Exception("Network timeout")

    mock_download.side_effect = download_side_effect

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.requested", pipeline.on_fetch_requested)

    test_broker.emit("data.fetch.requested", {})

    session = patched_sessionmaker()
    try:
        bbca_rows = session.execute(
            select(OHLCV).where(OHLCV.ticker == "BBCA.JK")
        ).scalars().all()
        assert len(bbca_rows) == 2  # BBCA succeeded
    finally:
        session.close()


# ── Global Fetch (on_fetch_global_requested) ────────────────────────────


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_global_fetch_with_db_instruments(mock_download, mock_open, patched_sessionmaker):
    """Global fetch reads non-XIDX instruments from DB."""
    from market.pipelines.data_fetch import DataFetchPipeline

    session = patched_sessionmaker()
    try:
        seed_markets(session)
        session.add(Instrument(
            ticker="^GSPC", exchange_mic="XNYS", asset_class="INDEX_COMPOSITE",
            name="S&P 500", is_active=True,
        ))
        session.commit()
    finally:
        session.close()

    mock_download.side_effect = lambda ticker, **kw: _mock_yf_df(ticker, rows=2)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch_global.requested", pipeline.on_fetch_global_requested)

    test_broker.emit("data.fetch_global.requested", {})

    session = patched_sessionmaker()
    try:
        rows = session.execute(
            select(OHLCV).where(OHLCV.ticker == "^GSPC")
        ).scalars().all()
        assert len(rows) == 2
    finally:
        session.close()


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_global_fetch_fallback_tickers(mock_download, mock_open, patched_sessionmaker):
    """Global fetch falls back to hardcoded GLOBAL_TICKERS when DB has no non-XIDX."""
    from market.pipelines.data_fetch import DataFetchPipeline, GLOBAL_TICKERS

    mock_download.side_effect = lambda ticker, **kw: _mock_yf_df(ticker, rows=1)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch_global.requested", pipeline.on_fetch_global_requested)

    test_broker.emit("data.fetch_global.requested", {})

    session = patched_sessionmaker()
    try:
        all_tickers = session.execute(
            select(OHLCV.ticker).distinct()
        ).scalars().all()
        assert len(all_tickers) > 0
        # Should have fetched some of the GLOBAL_TICKERS
        assert any(t in GLOBAL_TICKERS for t in all_tickers)
    finally:
        session.close()


# ── Macro Fetch (on_fetch_macro_requested) ──────────────────────────────


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_macro_fetch_inserts_macro_data(mock_download, mock_open, patched_sessionmaker):
    """Macro fetch inserts into macro_data table."""
    from market.pipelines.data_fetch import DataFetchPipeline

    mock_download.side_effect = lambda ticker, **kw: _mock_yf_df(ticker, rows=5)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch_macro.requested", pipeline.on_fetch_macro_requested)

    test_broker.emit("data.fetch_macro.requested", {})

    session = patched_sessionmaker()
    try:
        series_names = session.execute(
            select(MacroData.series_name).distinct()
        ).scalars().all()
        assert len(series_names) > 0
        assert "US10Y" in series_names
        assert "VIX" in series_names
    finally:
        session.close()


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_macro_fetch_skips_recent(mock_download, mock_open, patched_sessionmaker):
    """Macro fetch skips series with data ≤3 days old."""
    from market.pipelines.data_fetch import DataFetchPipeline
    from datetime import date

    session = patched_sessionmaker()
    try:
        session.add(MacroData(
            series_name="US10Y", date=date.today(),
            value=4.25, source="yahoo_finance", frequency="daily",
        ))
        session.commit()
    finally:
        session.close()

    mock_download.side_effect = lambda ticker, **kw: _mock_yf_df(ticker, rows=3)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch_macro.requested", pipeline.on_fetch_macro_requested)

    test_broker.emit("data.fetch_macro.requested", {})

    session = patched_sessionmaker()
    try:
        us10y_rows = session.execute(
            select(MacroData).where(MacroData.series_name == "US10Y")
        ).scalars().all()
        assert len(us10y_rows) == 1  # only our pre-inserted row
    finally:
        session.close()


# ── Intraday Fetch (on_intraday_requested) ──────────────────────────────


@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_intraday_fetch_inserts_15m(mock_download, patched_sessionmaker):
    """Intraday fetch stores 15-minute interval data."""
    from market.pipelines.data_fetch import DataFetchPipeline

    base = datetime(2024, 1, 2, 9, 0, tzinfo=UTC)
    dates = [base + timedelta(minutes=15 * i) for i in range(3)]
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Adj Close": [100.5, 101.5, 102.5],
            "Volume": [5000, 6000, 7000],
        },
        index=pd.DatetimeIndex(dates, name="Datetime"),
    )
    mock_download.return_value = df

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.intraday.requested", pipeline.on_intraday_requested)

    test_broker.emit("data.fetch.intraday.requested", {
        "tickers": ["BBCA.JK"],
    })

    session = patched_sessionmaker()
    try:
        rows = session.execute(
            select(OHLCV).where(
                OHLCV.ticker == "BBCA.JK",
                OHLCV.timeframe == "15m",
            )
        ).scalars().all()
        assert len(rows) == 1  # only latest record stored
        assert rows[0].close == Decimal("102.5")  # last record
    finally:
        session.close()


def test_e2e_intraday_fetch_no_tickers(patched_sessionmaker):
    """Intraday fetch with empty tickers list should not error."""
    from market.pipelines.data_fetch import DataFetchPipeline

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.intraday.requested", pipeline.on_intraday_requested)

    test_broker.emit("data.fetch.intraday.requested", {"tickers": []})


# ── Event chain verification ────────────────────────────────────────────


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_fetch_emits_stored_event(mock_download, mock_open, patched_sessionmaker):
    """DataFetchPipeline should emit data.fetch.stored after EOD fetch."""
    from market.pipelines.data_fetch import DataFetchPipeline

    session = patched_sessionmaker()
    try:
        _seed_test_instruments(session)
    finally:
        session.close()

    mock_download.side_effect = lambda ticker, **kw: _mock_yf_df(ticker, rows=2)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.requested", pipeline.on_fetch_requested)

    received_events: list[Event] = []
    test_broker.subscribe("data.fetch.stored", lambda e: received_events.append(e))

    with patch("market.core.events.broker", test_broker):
        test_broker.emit("data.fetch.requested", {})

    assert len(received_events) == 1
    assert received_events[0].name == "data.fetch.stored"
    assert received_events[0].payload["source"] == "eod"
    assert received_events[0].payload["tickers_success"] > 0


@patch("market.data.timestamp_validation.is_market_open", return_value=False)
@patch("market.data.yahoo_adapter.yf.download")
def test_e2e_intraday_emits_completed_event(mock_download, mock_open, patched_sessionmaker):
    """Intraday fetch should emit data.fetch.intraday.completed."""
    from market.pipelines.data_fetch import DataFetchPipeline

    mock_download.return_value = _mock_yf_df("BBCA.JK", rows=1)

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.intraday.requested", pipeline.on_intraday_requested)

    received: list[Event] = []
    test_broker.subscribe("data.fetch.intraday.completed", lambda e: received.append(e))

    with patch("market.core.events.broker", test_broker):
        test_broker.emit("data.fetch.intraday.requested", {"tickers": ["BBCA.JK"]})

    assert len(received) == 1
    assert received[0].name == "data.fetch.intraday.completed"
    assert "BBCA.JK" in received[0].payload["prices"]


# ── Retry helper ────────────────────────────────────────────────────────


def test_retry_success_first_try():
    """_retry returns result on first attempt."""
    from market.pipelines.data_fetch import _retry

    result = _retry(lambda: 42, "test")
    assert result == 42


def test_retry_returns_none_after_max():
    """_retry returns None after max retries exhausted."""
    from market.pipelines.data_fetch import _retry

    call_count = [0]

    def always_fail():
        call_count[0] += 1
        raise Exception("fail")

    result = _retry(always_fail, "test", max_retries=1)
    assert result is None
    assert call_count[0] == 2  # initial + 1 retry


def test_retry_succeeds_on_second_attempt():
    """_retry succeeds on retry."""
    from market.pipelines.data_fetch import _retry

    attempts = [0]

    def fail_then_succeed():
        attempts[0] += 1
        if attempts[0] == 1:
            raise Exception("transient")
        return "ok"

    result = _retry(fail_then_succeed, "test", max_retries=2)
    assert result == "ok"
    assert attempts[0] == 2


# ── PG path verification ────────────────────────────────────────────────


def test_data_repository_pg_uses_stock_price(test_session_factory):
    """DataRepository.save_ohlcv should use StockPrice model when db_backend='postgresql'."""
    from market.data.storage import DataRepository
    from market.db.models import StockPrice
    from market.data.contracts import NormalizedOHLCV

    patcher_pg = patch("market.data.storage._is_postgres", return_value=True)
    patcher_pg.start()

    session = test_session_factory()
    try:
        repo = DataRepository(session)
        assert repo._is_pg is True

        record = NormalizedOHLCV(
            ticker="TEST.JK", timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            open=Decimal("100"), high=Decimal("110"), low=Decimal("90"),
            close=Decimal("105"), volume=1000, adjusted_close=Decimal("105"),
            source="test", market_mic="XIDX", currency="IDR",
        )
        count = repo.save_ohlcv([record])
        assert count == 1

        rows = session.execute(
            select(StockPrice).where(StockPrice.ticker == "TEST.JK")
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].exchange_mic == "XIDX"
        assert rows[0].close == Decimal("105")
    finally:
        session.close()
        patcher_pg.stop()


def test_data_repository_sqlite_uses_ohlcv(test_session_factory):
    """DataRepository.save_ohlcv should use OHLCV model when db_backend='sqlite'."""
    from market.data.storage import DataRepository
    from market.db.models import OHLCV
    from market.data.contracts import NormalizedOHLCV

    patcher_sqlite = patch("market.data.storage._is_postgres", return_value=False)
    patcher_sqlite.start()

    session = test_session_factory()
    try:
        repo = DataRepository(session)
        assert repo._is_pg is False

        record = NormalizedOHLCV(
            ticker="TEST2.JK", timestamp=datetime(2024, 1, 3, tzinfo=UTC),
            open=Decimal("200"), high=Decimal("210"), low=Decimal("190"),
            close=Decimal("205"), volume=2000, adjusted_close=Decimal("205"),
            source="test", market_mic="XIDX", currency="IDR",
        )
        count = repo.save_ohlcv([record])
        assert count == 1

        rows = session.execute(
            select(OHLCV).where(OHLCV.ticker == "TEST2.JK")
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].close == Decimal("205")
    finally:
        session.close()
        patcher_sqlite.stop()
