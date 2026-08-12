"""Regression tests for recompute_internal functions.

Tests the core data-loading and batch-processing helpers with an
in-memory SQLite database to ensure correctness after P1/P2/P3 changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from market.db.models import OHLCV, Base, Score


@pytest.fixture()
def session() -> Session:
    """In-memory SQLite session with minimal schema."""
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(engine, tables=[OHLCV.__table__, Score.__table__])
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    sess = SessionLocal()
    yield sess
    sess.close()
    engine.dispose()


def _insert_ohlcv(
    session: Session,
    ticker: str,
    days: int = 60,
    start_price: float = 8000.0,
) -> None:
    """Insert minimal OHLCV rows for a ticker."""
    base_date = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(days):
        p = start_price + i * 10
        session.add(OHLCV(
            ticker=ticker,
            timestamp=base_date + timedelta(days=i),
            timeframe="1d",
            open=p,
            high=p + 50,
            low=p - 50,
            close=p + 25,
            volume=100_000 + i * 100,
        ))
    session.commit()


# ── _load_ohlcv_df ──────────────────────────────────────────────────────────


def test_load_ohlcv_df_empty(session: Session) -> None:
    from market.data.recompute_internal import _load_ohlcv_df

    df = _load_ohlcv_df(session, "NONEXIST.JK")
    assert df.empty


def test_load_ohlcv_df_basic(session: Session) -> None:
    from market.data.recompute_internal import _load_ohlcv_df

    _insert_ohlcv(session, "BBCA.JK", days=60)
    df = _load_ohlcv_df(session, "BBCA.JK")

    assert not df.empty
    assert len(df) == 60
    assert "open" in df.columns
    assert "high" in df.columns
    assert "low" in df.columns
    assert "close" in df.columns
    assert "volume" in df.columns
    assert df["close"].dtype == float
    assert df["volume"].dtype == int
    assert df.index.is_monotonic_increasing


# ── _load_all_ohlcv_dfs ─────────────────────────────────────────────────────


def test_load_all_ohlcv_dfs_empty(session: Session) -> None:
    from market.data.recompute_internal import _load_all_ohlcv_dfs

    result = _load_all_ohlcv_dfs(session, [])
    assert result == {}


def test_load_all_ohlcv_dfs_batch(session: Session) -> None:
    from market.data.recompute_internal import _load_all_ohlcv_dfs

    _insert_ohlcv(session, "BBCA.JK", days=60, start_price=8000)
    _insert_ohlcv(session, "BBRI.JK", days=60, start_price=4000)
    _insert_ohlcv(session, "TLKM.JK", days=60, start_price=3000)

    result = _load_all_ohlcv_dfs(session, ["BBCA.JK", "BBRI.JK", "TLKM.JK"])

    assert len(result) == 3
    assert "BBCA.JK" in result
    assert "BBRI.JK" in result
    assert "TLKM.JK" in result

    for ticker, df in result.items():
        assert len(df) == 60
        assert df["close"].dtype == float
        assert df.index.is_monotonic_increasing


def test_load_all_ohlcv_dfs_missing_ticker(session: Session) -> None:
    from market.data.recompute_internal import _load_all_ohlcv_dfs

    _insert_ohlcv(session, "BBCA.JK", days=60)
    result = _load_all_ohlcv_dfs(session, ["BBCA.JK", "MISSING.JK"])

    assert "BBCA.JK" in result
    assert "MISSING.JK" not in result


# ── _load_ohlcv_df_since ────────────────────────────────────────────────────


def test_load_ohlcv_df_since(session: Session) -> None:
    from market.data.recompute_internal import _load_ohlcv_df_since

    _insert_ohlcv(session, "BBCA.JK", days=100)
    cutoff = datetime(2024, 1, 1, tzinfo=UTC).date() + timedelta(days=50)
    df = _load_ohlcv_df_since(session, "BBCA.JK", cutoff, buffer_days=0)

    assert not df.empty
    assert len(df) == 50  # days 50-99


def test_load_ohlcv_df_since_with_buffer(session: Session) -> None:
    from market.data.recompute_internal import _load_ohlcv_df_since

    _insert_ohlcv(session, "BBCA.JK", days=100)
    cutoff = datetime(2024, 1, 1, tzinfo=UTC).date() + timedelta(days=50)
    df = _load_ohlcv_df_since(session, "BBCA.JK", cutoff, buffer_days=10)

    assert not df.empty
    # cutoff - 10 days buffer = day 40, so days 40-99 = 60 rows
    assert len(df) == 60


# ── DailyLossTracker ────────────────────────────────────────────────────────


def test_daily_loss_tracker_not_halted_initially():
    from market.risk.engine import DailyLossTracker

    tracker = DailyLossTracker(trading_capital=100_000_000, daily_loss_limit_pct=2.0)
    assert not tracker.is_halted
    assert tracker.loss_limit_amount == 2_000_000


def test_daily_loss_tracker_halt_on_limit():
    from market.risk.engine import DailyLossTracker

    tracker = DailyLossTracker(trading_capital=100_000_000, daily_loss_limit_pct=2.0)
    allowed = tracker.update(-2_500_000)
    assert not allowed
    assert tracker.is_halted


def test_daily_loss_tracker_auto_reset_on_new_day():
    from market.risk.engine import DailyLossTracker

    tracker = DailyLossTracker(trading_capital=100_000_000, daily_loss_limit_pct=2.0)
    tracker.update(-3_000_000, date_str="2026-01-15")
    assert tracker.is_halted

    tracker.update(0, date_str="2026-01-16")
    assert not tracker.is_halted


def test_daily_loss_tracker_stays_halted_after_recovery():
    from market.risk.engine import DailyLossTracker

    tracker = DailyLossTracker(trading_capital=100_000_000, daily_loss_limit_pct=2.0)
    tracker.update(-3_000_000, date_str="2026-01-15")
    assert tracker.is_halted

    tracker.update(1_000_000, date_str="2026-01-15")
    assert tracker.is_halted  # still halted same day


def test_daily_loss_tracker_reset_day():
    from market.risk.engine import DailyLossTracker

    tracker = DailyLossTracker(trading_capital=100_000_000, daily_loss_limit_pct=2.0)
    tracker.update(-3_000_000, date_str="2026-01-15")
    assert tracker.is_halted

    tracker.reset_day()
    assert not tracker.is_halted
