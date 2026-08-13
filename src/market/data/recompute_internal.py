"""Data loaders for recompute pipeline (S1 — Data Layer).

This module provides batch OHLCV loading utilities, watermark helpers,
and ticker discovery. It belongs to the data layer (S1) and must NOT
import from analysis, risk, execution, or higher layers.

Recompute functions that use analysis engines have been moved to
``market.analysis.recompute`` (S2). This module re-exports them for
backward compatibility via ``__getattr__``.

Usage (data loaders only):
    from market.data.recompute_internal import _load_ohlcv_df, _load_all_ohlcv_dfs

Usage (recompute functions — backward compat):
    from market.data.recompute_internal import run_all_recompute  # re-exported
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import select, text

from market.db.models import RecomputeWatermark

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ProgressCb = "callable[[str, int, int, str], None] | None"


def _load_ohlcv_df(session: Session, ticker: str) -> pd.DataFrame:
    """Load OHLCV data for a ticker into a pandas DataFrame.

    Uses pd.read_sql for direct DataFrame conversion — avoids ORM object
    instantiation overhead (2-5x faster than scalar->dict conversion).
    """
    sql = text(
        "SELECT timestamp, open, high, low, close, volume "
        "FROM ohlcv WHERE ticker = :ticker AND timeframe = '1d' ORDER BY timestamp"
    )
    df = pd.read_sql(
        sql,
        session.bind,
        params={"ticker": ticker},
        index_col="timestamp",
        parse_dates=["timestamp"],
    )
    if df.empty:
        return df
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(int)
    return df


def _load_all_ohlcv_dfs(
    session: Session, tickers: list[str],
) -> dict[str, pd.DataFrame]:
    """Batch-load OHLCV for all tickers in a single query.

    Eliminates N+1 query pattern: 963 individual queries → 1 query.
    Returns a dict mapping ticker → DataFrame (same format as _load_ohlcv_df).

    Args:
        session: SQLAlchemy session.
        tickers: List of ticker symbols to load.

    Returns:
        Dict {ticker: DataFrame} with DatetimeIndex and OHLCV columns.
    """
    if not tickers:
        return {}

    # SQLite has a 999 parameter limit; chunk if needed
    CHUNK_SIZE = 900
    all_dfs: dict[str, pd.DataFrame] = {}

    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i : i + CHUNK_SIZE]
        placeholders = ",".join(f":t{j}" for j in range(len(chunk)))
        params = {f"t{j}": t for j, t in enumerate(chunk)}
        sql = text(
            f"SELECT ticker, timestamp, open, high, low, close, volume "
            f"FROM ohlcv WHERE ticker IN ({placeholders}) AND timeframe = '1d' "
            f"ORDER BY ticker, timestamp"
        )
        df = pd.read_sql(
            sql,
            session.bind,
            params=params,
            parse_dates=["timestamp"],
        )
        if df.empty:
            continue
        for ticker, group in df.groupby("ticker"):
            gdf = group.drop(columns=["ticker"]).set_index("timestamp")
            gdf["open"] = gdf["open"].astype(float)
            gdf["high"] = gdf["high"].astype(float)
            gdf["low"] = gdf["low"].astype(float)
            gdf["close"] = gdf["close"].astype(float)
            gdf["volume"] = gdf["volume"].astype(int)
            all_dfs[ticker] = gdf

    return all_dfs


def _load_ohlcv_df_since(
    session: Session, ticker: str, since_date: date, buffer_days: int = 0,
) -> pd.DataFrame:
    """Load OHLCV data from (since_date - buffer_days) to latest.

    Bounded load for incremental recompute — only loads the data needed
    instead of the full history. The buffer_days parameter adds extra
    lookback for indicators that need historical context (e.g. MA200
    needs 200 days before the first new date to compute correctly).
    """
    cutoff = since_date - timedelta(days=buffer_days)
    sql = text(
        "SELECT timestamp, open, high, low, close, volume "
        "FROM ohlcv WHERE ticker = :ticker AND timeframe = '1d' "
        "AND timestamp >= :cutoff ORDER BY timestamp"
    )
    df = pd.read_sql(
        sql,
        session.bind,
        params={"ticker": ticker, "cutoff": cutoff},
        index_col="timestamp",
        parse_dates=["timestamp"],
    )
    if df.empty:
        return df
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(int)
    return df


def _get_watermark(session: Session, ticker: str, table_name: str) -> date | None:
    """Get last-processed date from recompute_watermark."""
    row = session.execute(
        select(RecomputeWatermark.last_processed_date).where(
            RecomputeWatermark.ticker == ticker,
            RecomputeWatermark.table_name == table_name,
        )
    ).scalar_one_or_none()
    return row


def _set_watermark(
    session: Session, ticker: str, table_name: str,
    last_date: date, rows: int = 0,
) -> None:
    """Upsert watermark for a ticker/table."""
    existing = session.execute(
        select(RecomputeWatermark).where(
            RecomputeWatermark.ticker == ticker,
            RecomputeWatermark.table_name == table_name,
        )
    ).scalar_one_or_none()
    if existing:
        existing.last_processed_date = last_date
        existing.last_ohlcv_date = last_date
        existing.rows_processed = rows
        existing.updated_at = datetime.now(UTC)
    else:
        session.add(RecomputeWatermark(
            ticker=ticker,
            table_name=table_name,
            last_processed_date=last_date,
            last_ohlcv_date=last_date,
            rows_processed=rows,
            updated_at=datetime.now(UTC),
        ))
    session.commit()


def _load_all_idx_tickers(session: Session) -> list[str]:
    """Get all IDX equity tickers from instruments table."""
    from market.data.ticker_util import to_yf_ticker

    # Try PG instruments table first
    try:
        from market.db.models import Instrument

        rows = session.execute(
            select(Instrument.ticker, Instrument.exchange_mic).where(
                Instrument.exchange_mic == "XIDX",
                Instrument.asset_class.in_(["EQUITY", "EQUITY_INDIVIDUAL", "equity"]),
            )
        ).all()
        if rows:
            return [to_yf_ticker(r[0], r[1], session) for r in rows]
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass

    # Fallback: SQLite instrument_master
    from market.db.models import InstrumentMaster

    rows = session.execute(
        select(InstrumentMaster.ticker, InstrumentMaster.market_mic).where(
            InstrumentMaster.market_mic == "XIDX",
            InstrumentMaster.asset_class == "equity",
        )
    ).all()
    return [to_yf_ticker(r[0], r[1], session) for r in rows]

