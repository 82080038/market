"""Backfill technical_indicators table with historical data.

Computes RSI, MACD, MA20, MA50, ADX, ATR14, BB_UPPER, BB_LOWER, VOLUME_SMA20
for every date in OHLCV history (not just the latest snapshot).

Usage:
    ENV=research uv run python scripts/backfill_technical_indicators.py [--batch-size 500] [--tickers AAA,BBB]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from market.db.engine import get_sessionmaker
from market.db.models import OHLCV, TechnicalIndicator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

INDICATOR_MAP = {
    "ma20": "MA20",
    "ma50": "MA50",
    "rsi": "RSI",
    "macd": "MACD",
    "macd_signal": "MACD_SIGNAL",
    "adx": "ADX",
    "atr": "ATR14",
    "bb_upper": "BB_UPPER",
    "bb_lower": "BB_LOWER",
    "vol_ratio": "VOLUME_SMA20",
}


def compute_indicators_series(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators as time series.

    Args:
        df: DataFrame with columns open, high, low, close, volume.
            Index must be DatetimeIndex.

    Returns:
        DataFrame with indicator columns, same index as input.
        NaN for periods where indicator is not yet available.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    result = pd.DataFrame(index=df.index)

    # Moving Averages
    result["ma20"] = close.rolling(20).mean()
    result["ma50"] = close.rolling(50).mean()

    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    result["rsi"] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    result["macd"] = macd_line
    result["macd_signal"] = signal_line

    # ATR (14)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    result["atr"] = tr.ewm(alpha=1 / 14, min_periods=14).mean()

    # Bollinger Bands (20, 2)
    bb_ma = close.rolling(20).mean()
    bb_sd = close.rolling(20).std()
    result["bb_upper"] = bb_ma + 2 * bb_sd
    result["bb_lower"] = bb_ma - 2 * bb_sd

    # ADX (14)
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0

    atr_adx = tr.ewm(alpha=1 / 14, min_periods=14).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / 14, min_periods=14).mean() / atr_adx)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / 14, min_periods=14).mean() / atr_adx)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
    result["adx"] = dx.ewm(alpha=1 / 14, min_periods=14).mean()

    # Volume SMA20 ratio
    vol_sma20 = volume.rolling(20).mean()
    result["vol_ratio"] = volume / vol_sma20.replace(0, np.nan)

    return result


def load_ohlcv_df(session, ticker: str) -> pd.DataFrame:
    """Load OHLCV data for a ticker into a pandas DataFrame."""
    rows = session.execute(
        select(OHLCV)
        .where(OHLCV.ticker == ticker, OHLCV.timeframe == "1d")
        .order_by(OHLCV.timestamp)
    ).scalars().all()
    if not rows:
        return pd.DataFrame()
    data = [
        {
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": int(r.volume),
        }
        for r in rows
    ]
    idx = pd.DatetimeIndex([r.timestamp for r in rows])
    return pd.DataFrame(data, index=idx)


def get_existing_dates(session, ticker: str) -> set:
    """Get set of dates already in technical_indicators for this ticker."""
    rows = session.execute(
        text(
            "SELECT DISTINCT date FROM technical_indicators "
            "WHERE ticker = :ticker AND source = 'computed'"
        ),
        {"ticker": ticker},
    ).fetchall()
    return {r[0] for r in rows}


def backfill_ticker(session, ticker: str, batch_size: int = 500) -> tuple[int, int]:
    """Backfill technical indicators for a single ticker.

    Returns:
        (inserted, skipped)
    """
    df = load_ohlcv_df(session, ticker)
    if df.empty or len(df) < 50:
        return 0, 0

    indicators_df = compute_indicators_series(df)

    # Drop rows where all indicators are NaN (warmup period)
    indicators_df = indicators_df.dropna(how="all")
    if indicators_df.empty:
        return 0, 0

    existing_dates = get_existing_dates(session, ticker)

    inserted = 0
    skipped = 0
    batch = []

    for ts, row in indicators_df.iterrows():
        date_val = ts.date() if hasattr(ts, "date") else ts

        if date_val in existing_dates:
            skipped += 1
            continue

        for key, label in INDICATOR_MAP.items():
            val = row.get(key)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                batch.append({
                    "ticker": ticker,
                    "date": str(date_val),
                    "indicator": label,
                    "value": float(val),
                    "timeframe": "1d",
                    "source": "computed",
                })

        if len(batch) >= batch_size:
            session.execute(
                text("""INSERT OR IGNORE INTO technical_indicators
                    (ticker, date, indicator, value, timeframe, source, created_at)
                    VALUES (:ticker, :date, :indicator, :value, :timeframe, :source, datetime('now'))"""),
                batch,
            )
            session.commit()
            inserted += len(batch)
            batch = []

    if batch:
        session.execute(
            text("""INSERT OR IGNORE INTO technical_indicators
                (ticker, date, indicator, value, timeframe, source, created_at)
                VALUES (:ticker, :date, :indicator, :value, :timeframe, :source, datetime('now'))"""),
            batch,
        )
        session.commit()
        inserted += len(batch)

    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Backfill technical indicators")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch insert size")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers (default: all)")
    parser.add_argument("--clear", action="store_true", help="Clear existing data first")
    args = parser.parse_args()

    session = get_sessionmaker()()

    if args.clear:
        logger.info("Clearing technical_indicators table...")
        session.execute(text("DELETE FROM technical_indicators"))
        session.commit()
        logger.info("Cleared.")

    # Get tickers
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        rows = session.execute(
            text(
                "SELECT DISTINCT ticker FROM ohlcv "
                "WHERE ticker LIKE '%.JK' AND timeframe='1d' "
                "ORDER BY ticker"
            )
        ).fetchall()
        tickers = [r[0] for r in rows]

    total = len(tickers)
    logger.info("Backfilling technical_indicators for %d tickers", total)

    total_inserted = 0
    total_skipped = 0
    total_empty = 0

    for i, ticker in enumerate(tickers):
        inserted, skipped = backfill_ticker(session, ticker, args.batch_size)
        total_inserted += inserted
        total_skipped += skipped

        if inserted == 0 and skipped == 0:
            total_empty += 1

        if (i + 1) % 10 == 0 or (i + 1) == total:
            logger.info(
                "[%d/%d] %s: +%d inserted, %d skipped | Running: inserted=%d, skipped=%d, empty=%d",
                i + 1, total, ticker, inserted, skipped,
                total_inserted, total_skipped, total_empty,
            )

    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("  Total tickers: %d", total)
    logger.info("  Total inserted: %d", total_inserted)
    logger.info("  Total skipped (already exists): %d", total_skipped)
    logger.info("  Empty/insufficient data: %d", total_empty)

    # Verify
    count = session.execute(
        text("SELECT COUNT(*) FROM technical_indicators")
    ).scalar()
    dates = session.execute(
        text("SELECT COUNT(DISTINCT date) FROM technical_indicators")
    ).scalar()
    tickers_count = session.execute(
        text("SELECT COUNT(DISTINCT ticker) FROM technical_indicators")
    ).scalar()
    logger.info("  technical_indicators table: %d rows, %d dates, %d tickers", count, dates, tickers_count)

    session.close()


if __name__ == "__main__":
    main()
