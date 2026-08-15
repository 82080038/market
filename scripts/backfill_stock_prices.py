"""Backfill stock_prices from yfinance using DynamicRateLimiter.

Fetches daily OHLCV for all active IDX tickers (and global indices)
from the last available date to today, using adaptive rate limiting
to avoid IP bans.

Usage:
    python scripts/backfill_stock_prices.py [--dry-run] [--batch-size 50]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, date, timedelta

import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text

from market.config import settings
from market.data.rate_limit import CircuitBreakerError, DynamicRateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DELETE_SQL = "DELETE FROM stock_prices WHERE ticker = :ticker AND timestamp = :ts AND timeframe = '1d'"

INSERT_SQL = """
    INSERT INTO stock_prices (ticker, exchange_mic, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source)
    VALUES (:ticker, :mic, :ts, '1d', :open, :high, :low, :close, :volume, :adj_close, 'yahoo_finance')
"""


def get_active_tickers(engine) -> list[tuple[str, str]]:
    """Return (ticker, exchange_mic) for all active instruments."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT ticker, exchange_mic FROM instruments WHERE is_active = true ORDER BY ticker"
        )).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_last_date(engine, ticker: str) -> date | None:
    """Get the last available date for a ticker in stock_prices."""
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT MAX(timestamp) FROM stock_prices WHERE ticker = :t AND timeframe = '1d'"
        ), {"t": ticker}).fetchone()
    if row and row[0]:
        return row[0].date() if hasattr(row[0], 'date') else row[0]
    return None


def backfill_ticker(
    ticker: str,
    mic: str,
    start_date: date,
    end_date: date,
    engine,
    limiter: DynamicRateLimiter,
    dry_run: bool = False,
) -> int:
    """Fetch and insert OHLCV for a single ticker. Returns rows inserted."""
    limiter.wait()
    try:
        df = yf.download(
            ticker,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
            interval="1d",
        )
    except Exception as exc:
        limiter.on_error(None)
        logger.error("yfinance failed for %s: %s", ticker, exc)
        return 0

    if df is None or df.empty:
        limiter.on_success()
        logger.debug("No data for %s (%s to %s)", ticker, start_date, end_date)
        return 0

    limiter.on_success()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    rows = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("Open")) or pd.isna(row.get("Close")):
            continue
        ts_dt = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=UTC)
        rows.append({
            "ticker": ticker,
            "mic": mic,
            "ts": ts_dt,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]) if not pd.isna(row.get("Volume")) else 0,
            "adj_close": float(row["Close"]),
        })

    if not rows or dry_run:
        return len(rows)

    with engine.begin() as conn:
        for r in rows:
            conn.execute(text(DELETE_SQL), {"ticker": r["ticker"], "ts": r["ts"]})
        conn.execute(text(INSERT_SQL), rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill stock_prices from yfinance")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't insert")
    parser.add_argument("--batch-size", type=int, default=50, help="Commit batch size")
    parser.add_argument("--start-date", type=str, default=None, help="Override start date (YYYY-MM-DD)")
    args = parser.parse_args()

    engine = create_engine(settings.resolved_database_url)
    tickers = get_active_tickers(engine)
    logger.info("Found %d active tickers to backfill", len(tickers))

    end_date = date.today() - timedelta(days=1)
    default_start = date(2025, 7, 1)
    override_start = date.fromisoformat(args.start_date) if args.start_date else None

    limiter = DynamicRateLimiter(
        initial_delay=0.5,
        min_delay=0.1,
        max_delay=30.0,
        backoff_factor=1.5,
        recovery_factor=0.9,
        success_streak_threshold=5,
    )

    total_inserted = 0
    total_skipped = 0
    total_errors = 0
    start_time = time.time()

    for i, (ticker, mic) in enumerate(tickers, 1):
        last_date = get_last_date(engine, ticker)
        if override_start:
            fetch_start = override_start
        elif last_date:
            fetch_start = last_date + timedelta(days=1)
        else:
            fetch_start = default_start

        if fetch_start >= end_date:
            total_skipped += 1
            continue

        try:
            n = backfill_ticker(
                ticker, mic, fetch_start, end_date, engine, limiter, args.dry_run
            )
            total_inserted += n
            if n > 0:
                logger.info(
                    "[%d/%d] %s: %d rows (%s → %s) | delay=%.2fs",
                    i, len(tickers), ticker, n, fetch_start, end_date, limiter.delay,
                )
            elif i % 50 == 0:
                logger.info(
                    "[%d/%d] Progress checkpoint | delay=%.2fs | stats=%s",
                    i, len(tickers), limiter.delay, limiter.stats,
                )
        except CircuitBreakerError:
            logger.error("Circuit breaker tripped at ticker %d/%d (%s). Stopping.", i, len(tickers), ticker)
            logger.info("Waiting 60s before circuit reset...")
            time.sleep(60)
            limiter.reset_circuit()
            logger.info("Circuit reset. Continuing...")
            total_errors += 1
            continue
        except Exception as exc:
            logger.error("Unexpected error for %s: %s", ticker, exc)
            total_errors += 1
            continue

    elapsed = time.time() - start_time
    logger.info(
        "Backfill complete: %d rows inserted, %d tickers skipped, %d errors, %.1fs elapsed",
        total_inserted, total_skipped, total_errors, elapsed,
    )
    logger.info("Rate limiter final stats: %s", limiter.stats)
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
