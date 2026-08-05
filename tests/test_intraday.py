"""Tests for intraday price polling and prediction-vs-actual comparison."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from market.api.app import create_app
from market.core.events import broker
from market.db.engine import get_sessionmaker
from market.db.models import OHLCV


def _seed_intraday_ohlcv(session) -> None:
    """Seed 15-min OHLCV bars for testing."""
    base_time = datetime(2026, 8, 6, 9, 0, tzinfo=UTC)
    bars = [
        ("^JKSE", base_time, 7900, 7950, 7880, 7920, 100000),
        ("^GSPC", base_time, 5500, 5510, 5490, 5505, 200000),
        ("GC=F", base_time, 2400, 2410, 2395, 2405, 50000),
    ]
    for ticker, ts, o, h, lo, c, v in bars:
        session.add(OHLCV(
            ticker=ticker,
            timestamp=ts,
            timeframe="15m",
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(lo)),
            close=Decimal(str(c)),
            volume=v,
            source="yahoo_finance_intraday",
        ))
    session.commit()


def _seed_daily_ohlcv(session, ticker: str = "BBCA.JK", n: int = 60) -> None:
    """Seed n daily OHLCV bars for prediction comparison."""
    base = datetime(2026, 6, 1, tzinfo=UTC)
    for i in range(n):
        ts = base + __import__("datetime").timedelta(days=i)
        close = 8000 + i * 50
        session.add(OHLCV(
            ticker=ticker,
            timestamp=ts,
            timeframe="1d",
            open=Decimal(str(close - 20)),
            high=Decimal(str(close + 30)),
            low=Decimal(str(close - 40)),
            close=Decimal(str(close)),
            volume=500000,
            source="yahoo_finance",
        ))
    session.commit()


# ── Scheduler tests ──────────────────────────────────────────────────────


def test_intraday_task_registered():
    """Intraday fetch task is registered in default tasks."""
    from market.scheduler import DailyScheduler
    from market.scheduler_tasks import register_default_tasks

    scheduler = DailyScheduler(persist=False)
    register_default_tasks(scheduler)

    task = scheduler.get_task("fetch_intraday")
    assert task is not None
    assert task.schedule == "every_15min"
    assert task.enabled


def test_intraday_task_emits_event():
    """_task_fetch_intraday emits data.fetch.intraday.requested."""
    from market.scheduler_tasks import _task_fetch_intraday

    received: list[dict] = []

    def handler(event):
        received.append(event.payload)

    broker.subscribe("data.fetch.intraday.requested", handler)
    try:
        _task_fetch_intraday()
    finally:
        broker.unsubscribe("data.fetch.intraday.requested", handler)

    assert len(received) == 1
    assert received[0]["source"] == "intraday"
    assert "^JKSE" in received[0]["tickers"]


def test_every_15min_schedule_due():
    """every_15min schedule is due after 15 minutes."""
    from datetime import timedelta

    from market.scheduler import DailyScheduler, ScheduledTask, TaskStatus

    scheduler = DailyScheduler(persist=False)

    task = ScheduledTask(
        task_id="test",
        name="test",
        func=lambda: None,
        schedule="every_15min",
    )
    task.last_run = (datetime.now(UTC) - timedelta(minutes=16)).isoformat()
    task.last_status = TaskStatus.SUCCESS

    assert scheduler._is_due(task, datetime.now(UTC))

    task.last_run = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    assert not scheduler._is_due(task, datetime.now(UTC))


# ── API endpoint tests ───────────────────────────────────────────────────


@pytest.mark.isolated_db
def test_prices_latest_empty():
    """GET /api/prices/latest returns empty when no intraday data."""
    client = TestClient(create_app())
    r = client.get("/api/prices/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert "prices" in data


@pytest.mark.isolated_db
def test_prices_latest_with_data():
    """GET /api/prices/latest returns seeded intraday prices."""
    session = get_sessionmaker()()
    try:
        _seed_intraday_ohlcv(session)
    finally:
        session.close()

    client = TestClient(create_app())
    r = client.get("/api/prices/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert "^JKSE" in data["prices"]
    assert data["prices"]["^JKSE"]["price"] == 7920.0
    assert data["prices"]["^JKSE"]["timeframe"] == "15m"


@pytest.mark.isolated_db
def test_prices_latest_filter_by_ticker():
    """GET /api/prices/latest?ticker=^GSPC returns only that ticker."""
    session = get_sessionmaker()()
    try:
        _seed_intraday_ohlcv(session)
    finally:
        session.close()

    client = TestClient(create_app())
    r = client.get("/api/prices/latest", params={"ticker": "^GSPC"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert "^GSPC" in data["prices"]
    assert "^JKSE" not in data["prices"]


@pytest.mark.isolated_db
def test_prices_intraday_trigger():
    """POST /api/prices/intraday/trigger emits fetch event.

    Unsubscribes the real handler to avoid network calls during test.
    """
    # Find and remove the real handler to prevent yfinance network calls
    handlers = broker._handlers.get("data.fetch.intraday.requested", [])
    real_handlers = list(handlers)
    handlers.clear()

    try:
        received: list[dict] = []

        def capture(event):
            received.append(event.payload)

        broker.subscribe("data.fetch.intraday.requested", capture)

        client = TestClient(create_app())
        r = client.post("/api/prices/intraday/trigger")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "triggered"
        assert "^JKSE" in data["tickers"]
        assert len(received) == 1
        assert received[0]["source"] == "manual"
    finally:
        # Restore real handlers
        handlers.extend(real_handlers)


@pytest.mark.isolated_db
def test_prices_intraday_trigger_custom_tickers():
    """POST /api/prices/intraday/trigger with custom tickers.

    Unsubscribes the real handler to avoid network calls during test.
    """
    handlers = broker._handlers.get("data.fetch.intraday.requested", [])
    real_handlers = list(handlers)
    handlers.clear()

    try:
        client = TestClient(create_app())
        r = client.post("/api/prices/intraday/trigger", json={
            "tickers": ["BBCA.JK", "TLKM.JK"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["tickers"] == ["BBCA.JK", "TLKM.JK"]
    finally:
        handlers.extend(real_handlers)


@pytest.mark.isolated_db
def test_prices_compare_insufficient_data():
    """GET /api/prices/compare/{ticker} returns 404 for insufficient data."""
    client = TestClient(create_app())
    r = client.get("/api/prices/compare/UNKNOWN.JK")
    assert r.status_code == 404


@pytest.mark.isolated_db
def test_prices_compare_with_data():
    """GET /api/prices/compare/{ticker} returns prediction vs actual."""
    session = get_sessionmaker()()
    try:
        _seed_daily_ohlcv(session, "BBCA.JK", n=60)
    finally:
        session.close()

    client = TestClient(create_app())
    r = client.get("/api/prices/compare/BBCA.JK", params={"lookback_bars": 20})
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "BBCA.JK"
    assert "prediction" in data
    assert "actual" in data
    assert "comparison" in data
    assert data["prediction"]["direction"] in ("up", "down", "flat")
    assert data["actual"]["direction"] in ("up", "down")
    assert isinstance(data["comparison"]["direction_correct"], bool)


# ── YahooFinanceAdapter interval test ────────────────────────────────────


def test_yahoo_adapter_accepts_interval_param():
    """YahooFinanceAdapter.fetch_ohlcv accepts interval parameter."""
    import inspect

    from market.data.yahoo_adapter import YahooFinanceAdapter

    sig = inspect.signature(YahooFinanceAdapter.fetch_ohlcv)
    assert "interval" in sig.parameters
    assert sig.parameters["interval"].default == "1d"
