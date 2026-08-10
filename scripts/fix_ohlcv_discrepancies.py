"""Fix OHLCV data discrepancies in PostgreSQL.

Two operations:
1. Delete intraday rows with wrong timestamps (Aug 5, 2026 batch)
2. Re-fetch Aug 7 data for ^FTSE, ^GDAXI, ^VIX from yfinance

Usage:
    python scripts/fix_ohlcv_discrepancies.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PG_URL = "postgresql://petrick:market_dev@localhost:5432/market"

# Tickers with wrong intraday rows on Aug 5, 2026
INTRADAY_TICKERS = [
    "^VIX", "^GSPC", "^N225", "^HSI", "^JKSE",
    "^FTSE", "^GDAXI", "GC=F", "CL=F",
]

# Tickers with wrong close prices on Aug 7, 2026
REFETCH_TICKERS = ["^FTSE", "^GDAXI", "^VIX"]


def get_engine():
    from market.config import settings
    url = settings.resolved_database_url if settings.db_backend == "postgresql" else PG_URL
    return create_engine(url, echo=False, future=True, pool_pre_ping=True)


def delete_intraday_rows(engine, dry_run: bool) -> int:
    """Delete intraday OHLCV rows with timestamps not matching market close times."""
    from market.data.timestamp_validation import TICKER_MIC, validate_ohlcv_timestamp

    total_deleted = 0
    for ticker in INTRADAY_TICKERS:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT timestamp, close, volume
                    FROM stock_prices
                    WHERE ticker = :ticker
                      AND timeframe = '1d'
                      AND timestamp >= '2026-08-05'
                      AND timestamp < '2026-08-06'
                    ORDER BY timestamp
                """),
                {"ticker": ticker},
            ).fetchall()

            if not rows:
                continue

            for ts, close, vol in rows:
                is_valid, reason = validate_ohlcv_timestamp(ticker, ts)
                if not is_valid:
                    logger.info("  DELETE %s @ %s (close=%s) — %s", ticker, ts, close, reason)
                    if not dry_run:
                        conn.execute(
                            text("""
                                DELETE FROM stock_prices
                                WHERE ticker = :ticker
                                  AND timestamp = :ts
                                  AND timeframe = '1d'
                            """),
                            {"ticker": ticker, "ts": ts},
                        )
                        conn.commit()
                    total_deleted += 1

    return total_deleted


def refetch_aug7_data(engine, dry_run: bool) -> int:
    """Re-fetch Aug 7, 2026 OHLCV data from yfinance for tickers with wrong prices."""
    total_updated = 0
    end_date = date.today() - timedelta(days=1)

    for ticker in REFETCH_TICKERS:
        logger.info("  Re-fetching %s from yfinance (Aug 7, 2026)...", ticker)
        try:
            df = yf.download(
                ticker,
                start="2026-08-06",
                end="2026-08-09",
                auto_adjust=True,
                progress=False,
                interval="1d",
            )
        except Exception as e:
            logger.error("  yfinance failed for %s: %s", ticker, e)
            continue

        if df is None or df.empty:
            logger.warning("  No data returned for %s", ticker)
            continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        for ts, row in df.iterrows():
            ts_dt = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=UTC)

            # Only update Aug 7 data
            if ts_dt.day != 7 or ts_dt.month != 8 or ts_dt.year != 2026:
                continue

            if pd.isna(row.get("Close")):
                continue

            o = float(row["Open"])
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
            v = int(row["Volume"]) if not pd.isna(row.get("Volume")) else 0

            logger.info("  UPDATE %s @ %s → close=%.2f", ticker, ts_dt, c)

            if not dry_run:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE stock_prices
                            SET open = :o, high = :h, low = :l, close = :c, volume = :v
                            WHERE ticker = :ticker
                              AND timestamp = :ts
                              AND timeframe = '1d'
                        """),
                        {
                            "ticker": ticker, "ts": ts_dt,
                            "o": o, "h": h, "l": l, "c": c, "v": v,
                        },
                    )
            total_updated += 1

    return total_updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix OHLCV data discrepancies")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("OHLCV DATA FIX SCRIPT")
    logger.info("Dry run: %s", args.dry_run)
    logger.info("=" * 70)

    engine = get_engine()

    # Step 1: Delete intraday rows with wrong timestamps
    logger.info("\n--- Step 1: Delete intraday rows (Aug 5, 2026) ---")
    deleted = delete_intraday_rows(engine, args.dry_run)
    logger.info("  Total rows %s: %d", "to delete" if args.dry_run else "deleted", deleted)

    # Step 2: Re-fetch Aug 7 data for tickers with wrong prices
    logger.info("\n--- Step 2: Re-fetch Aug 7 data from yfinance ---")
    updated = refetch_aug7_data(engine, args.dry_run)
    logger.info("  Total rows %s: %d", "to update" if args.dry_run else "updated", updated)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("FIX COMPLETE")
    logger.info("  Rows deleted: %d", deleted)
    logger.info("  Rows updated: %d", updated)
    if args.dry_run:
        logger.info("  [DRY RUN] No actual changes made")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
