"""Backfill 4 kolom NULL di technical_indicators_wide.

Kolom yang di-backfill:
  - ema50
  - ema_env_upper
  - ema_env_lower
  - donchian_upper
  - donchian_lower
  - donchian_mid

Strategi:
  1. Untuk setiap ticker di technical_indicators_wide WHERE ema50 IS NULL
  2. Load OHLCV dari tabel OHLCV (timestamp, open, high, low, close, volume)
  3. Compute EMA50, EMA Envelope (±3%), Donchian Channel (20) untuk semua tanggal
  4. Batch UPDATE ke technical_indicators_wide

Usage:
  DB_PATH=data/market_research.db uv run python scripts/backfill_ti_wide_null_cols.py
  DB_PATH=data/market_research.db uv run python scripts/backfill_ti_wide_null_cols.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_db_path() -> str:
    import os
    db_path = os.environ.get("DB_PATH", "data/market_research.db")
    return db_path


def get_null_tickers(engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT ticker FROM technical_indicators_wide "
            "WHERE ema50 IS NULL ORDER BY ticker"
        )).fetchall()
    return [r[0] for r in rows]


def load_ohlcv(engine, ticker: str) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT timestamp, high, low, close, volume "
            "FROM ohlcv WHERE ticker = :tk ORDER BY timestamp"
        ), {"tk": ticker}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute EMA50, EMA Envelope, Donchian Channel for all dates."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # EMA50
    ema50 = close.ewm(span=50, adjust=False).mean()

    # EMA Envelope (±3%)
    ema_env_upper = ema50 * 1.03
    ema_env_lower = ema50 * 0.97

    # Donchian Channel (20)
    dc_period = 20
    dc_upper = high.rolling(dc_period).max()
    dc_lower = low.rolling(dc_period).min()
    dc_mid = (dc_upper + dc_lower) / 2

    result = pd.DataFrame({
        "date": df["date"],
        "ema50": ema50,
        "ema_env_upper": ema_env_upper,
        "ema_env_lower": ema_env_lower,
        "donchian_upper": dc_upper,
        "donchian_lower": dc_lower,
        "donchian_mid": dc_mid,
    })
    # Drop rows where any indicator is NaN (warmup period)
    result = result.dropna(subset=["ema50", "donchian_upper"])
    return result


def batch_update_wide(engine, ticker: str, indicators: pd.DataFrame) -> int:
    """Batch UPDATE technical_indicators_wide for one ticker."""
    if indicators.empty:
        return 0

    updated = 0
    with engine.begin() as conn:
        for _, row in indicators.iterrows():
            result = conn.execute(text(
                "UPDATE technical_indicators_wide SET "
                "  ema50 = :ema50, "
                "  ema_env_upper = :emu, "
                "  ema_env_lower = :eml, "
                "  donchian_upper = :du, "
                "  donchian_lower = :dl, "
                "  donchian_mid = :dm "
                "WHERE ticker = :tk AND date = :dt AND timeframe = '1d'"
            ), {
                "ema50": float(row["ema50"]),
                "emu": float(row["ema_env_upper"]),
                "eml": float(row["ema_env_lower"]),
                "du": float(row["donchian_upper"]),
                "dl": float(row["donchian_lower"]),
                "dm": float(row["donchian_mid"]),
                "tk": ticker,
                "dt": row["date"],
            })
            updated += result.rowcount
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill NULL columns in technical_indicators_wide")
    parser.add_argument("--dry-run", action="store_true", help="Only show stats, no updates")
    parser.add_argument("--ticker", type=str, default=None, help="Process single ticker only")
    args = parser.parse_args()

    db_path = get_db_path()
    logger.info("Database: %s", db_path)
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    # Stats
    with engine.connect() as conn:
        total_rows = conn.execute(text(
            "SELECT COUNT(*) FROM technical_indicators_wide"
        )).scalar()
        null_ema50 = conn.execute(text(
            "SELECT COUNT(*) FROM technical_indicators_wide WHERE ema50 IS NULL"
        )).scalar()
        null_donchian = conn.execute(text(
            "SELECT COUNT(*) FROM technical_indicators_wide WHERE donchian_upper IS NULL"
        )).scalar()

    logger.info("Wide table rows: %d", total_rows)
    logger.info("NULL ema50: %d (%.1f%%)", null_ema50, 100 * null_ema50 / max(1, total_rows))
    logger.info("NULL donchian_upper: %d (%.1f%%)", null_donchian, 100 * null_donchian / max(1, total_rows))

    if args.dry_run:
        logger.info("Dry run — no updates performed")
        return

    # Get tickers to process
    if args.ticker:
        tickers = [args.ticker]
    else:
        tickers = get_null_tickers(engine)

    logger.info("Tickers to process: %d", len(tickers))
    if not tickers:
        logger.info("No tickers need backfill — all columns populated")
        return

    total_updated = 0
    start_time = time.time()

    for i, ticker in enumerate(tickers, 1):
        df = load_ohlcv(engine, ticker)
        if df.empty or len(df) < 50:
            logger.debug("  %s: skip (insufficient data: %d rows)", ticker, len(df))
            continue

        indicators = compute_indicators(df)
        updated = batch_update_wide(engine, ticker, indicators)
        total_updated += updated

        if i % 50 == 0 or i == len(tickers):
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(tickers) - i) / rate if rate > 0 else 0
            logger.info(
                "  Progress: %d/%d tickers (%.1f%%) | updated: %d rows | ETA: %.0fs",
                i, len(tickers), 100 * i / len(tickers), total_updated, eta,
            )

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("Done! Updated %d rows across %d tickers in %.1fs", total_updated, len(tickers), elapsed)

    # Verify
    with engine.connect() as conn:
        null_ema50_after = conn.execute(text(
            "SELECT COUNT(*) FROM technical_indicators_wide WHERE ema50 IS NULL"
        )).scalar()
    logger.info("NULL ema50 after backfill: %d", null_ema50_after)


if __name__ == "__main__":
    main()
