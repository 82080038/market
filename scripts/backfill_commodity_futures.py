"""Backfill global commodity futures OHLCV data from yfinance.

Backfills daily OHLCV for commodity futures critical to IDX sector prediction:
- CL=F  — Crude Oil (NYMEX) — drives IDX Energy sector
- GC=F  — Gold (COMEX) — drives IDX Basic Materials (precious metals)
- HG=F  — Copper (COMEX) — drives IDX Basic Materials (industrial metals)
- MTF=F — Coal (ICE/API2) — drives IDX Energy (coal miners: ITMG, PTBA, HRUM)
- CPO=F — Crude Palm Oil (Bursa Malaysia) — drives IDX Plantation (AALI, LSIP, SIMP)
- NI=F  — Nickel (LME proxy) — drives IDX Basic Materials (nickel: ANTM, INCO)

Data range: January 2023 → August 2026 (or latest available).
All data stored in ``ohlcv`` table with ``timeframe='1d'`` and ``source='yfinance'``.

Usage:
    DB_PATH=data/market_research.db python scripts/backfill_commodity_futures.py
    DB_PATH=data/market_research.db python scripts/backfill_commodity_futures.py --dry-run
    DB_PATH=data/market_research.db python scripts/backfill_commodity_futures.py --start 2023-01-01
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

COMMODITY_FUTURES: list[dict[str, str]] = [
    {"ticker": "CL=F",  "name": "Crude Oil WTI Futures",       "currency": "USD", "sector": "energy"},
    {"ticker": "GC=F",  "name": "Gold Futures",                 "currency": "USD", "sector": "materials"},
    {"ticker": "HG=F",  "name": "Copper Futures",               "currency": "USD", "sector": "materials"},
    {"ticker": "MTF=F", "name": "Coal Futures (API2/ICE)",      "currency": "USD", "sector": "energy"},
    {"ticker": "CPO=F", "name": "Crude Palm Oil Futures (Bursa)", "currency": "MYR", "sector": "plantation"},
    {"ticker": "FCPO=F", "name": "FCPO Crude Palm Oil (Bursa, alt ticker)", "currency": "MYR", "sector": "plantation"},
    {"ticker": "NI=F",  "name": "Nickel Futures (LME proxy)",   "currency": "USD", "sector": "materials"},
]

DEFAULT_START = "2023-01-01"


def fetch_commodity_ohlcv(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Fetch daily OHLCV from yfinance for a commodity futures ticker.

    Args:
        ticker: yfinance ticker (e.g., 'CL=F').
        start: Start date (YYYY-MM-DD).
        end: End date (defaults to today).

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    if end is None:
        end = datetime.now(UTC).strftime("%Y-%m-%d")

    logger.info("Fetching %s from %s to %s ...", ticker, start, end)
    try:
        df = yf.download(ticker, start=start, end=end, interval="1d", progress=False)
    except Exception as e:
        logger.error("yfinance download failed for %s: %s", ticker, e)
        return pd.DataFrame()

    if df is None or df.empty:
        logger.warning("No data returned for %s — ticker may be unavailable on yfinance", ticker)
        return pd.DataFrame()

    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    df = df.rename(columns={
        "Date": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    # Keep only needed columns
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = df[[c for c in cols if c in df.columns]]

    # Ensure timestamp is string
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")

    return df


def upsert_ohlcv(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame) -> int:
    """Insert or replace OHLCV rows for a commodity ticker.

    Args:
        conn: SQLite connection.
        ticker: Ticker symbol.
        df: DataFrame with OHLCV data.

    Returns:
        Number of rows upserted.
    """
    if df.empty:
        return 0

    count = 0
    for _, row in df.iterrows():
        conn.execute("""
            INSERT OR REPLACE INTO ohlcv
                (ticker, timestamp, timeframe, open, high, low, close, volume, source)
            VALUES (?, ?, '1d', ?, ?, ?, ?, ?, 'yfinance')
        """, (
            ticker,
            row["timestamp"],
            float(row.get("open", 0)),
            float(row.get("high", 0)),
            float(row.get("low", 0)),
            float(row.get("close", 0)),
            int(row.get("volume", 0)) if pd.notna(row.get("volume", 0)) else 0,
        ))
        count += 1

    conn.commit()
    return count


def ensure_instrument_master(conn: sqlite3.Connection, info: dict[str, str]) -> None:
    """Ensure commodity ticker exists in instrument_master."""
    ticker = info["ticker"]
    row = conn.execute(
        "SELECT ticker FROM instrument_master WHERE ticker = ?", (ticker,)
    ).fetchone()
    if row:
        conn.execute("""
            UPDATE instrument_master SET name = ?, asset_class = 'commodity',
                   base_currency = ?, is_active = 1
            WHERE ticker = ?
        """, (info["name"], info["currency"], ticker))
    else:
        conn.execute("""
            INSERT INTO instrument_master
                (ticker, name, asset_class, base_currency, is_active, market_mic)
            VALUES (?, ?, 'commodity', ?, 1, 'OFF')
        """, (ticker, info["name"], info["currency"]))
    conn.commit()


def audit_commodity_data(conn: sqlite3.Connection) -> dict[str, dict]:
    """Audit existing commodity data in ohlcv table.

    Returns:
        Dict of {ticker: {rows, min_date, max_date, missing}}.
    """
    audit: dict[str, dict] = {}
    for info in COMMODITY_FUTURES:
        ticker = info["ticker"]
        row = conn.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) "
            "FROM ohlcv WHERE ticker = ? AND timeframe = '1d'",
            (ticker,),
        ).fetchone()
        count = row[0] or 0
        min_date = str(row[1])[:10] if row[1] else None
        max_date = str(row[2])[:10] if row[2] else None
        missing = count == 0
        audit[ticker] = {
            "name": info["name"],
            "rows": count,
            "min_date": min_date,
            "max_date": max_date,
            "missing": missing,
        }
        status = "MISSING" if missing else f"{count} rows ({min_date} → {max_date})"
        logger.info("  %s (%s): %s", ticker, info["name"], status)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill global commodity futures OHLCV from yfinance",
    )
    parser.add_argument("--db", type=str, default=None,
                        help="Path to DB (default: env DB_PATH or data/market_research.db)")
    parser.add_argument("--start", type=str, default=DEFAULT_START,
                        help=f"Start date (default: {DEFAULT_START})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Audit only, do not fetch or insert data")
    parser.add_argument("--only", type=str, default=None,
                        help="Comma-separated tickers to backfill (default: all)")
    args = parser.parse_args()

    db_path = args.db or os.environ.get("DB_PATH", "data/market_research.db")
    logger.info("Commodity Futures Backfill — DB: %s", db_path)
    logger.info("Date range: %s → today", args.start)

    conn = sqlite3.connect(db_path)

    # Audit existing data
    logger.info("")
    logger.info("=== AUDIT: Current commodity data ===")
    audit = audit_commodity_data(conn)

    if args.dry_run:
        logger.info("")
        logger.info("DRY RUN — No data fetched or inserted.")
        conn.close()
        return

    # Determine which tickers to fetch
    if args.only:
        tickers_to_fetch = [t.strip() for t in args.only.split(",")]
    else:
        tickers_to_fetch = [info["ticker"] for info in COMMODITY_FUTURES]

    end_date = datetime.now(UTC).strftime("%Y-%m-%d")
    total_inserted = 0

    for info in COMMODITY_FUTURES:
        ticker = info["ticker"]
        if ticker not in tickers_to_fetch:
            continue

        logger.info("")
        logger.info("=== Backfilling %s (%s) ===", ticker, info["name"])

        # Ensure instrument_master entry
        try:
            ensure_instrument_master(conn, info)
        except Exception as e:
            logger.warning("Failed to update instrument_master for %s: %s", ticker, e)

        # Fetch from yfinance
        df = fetch_commodity_ohlcv(ticker, args.start, end_date)
        if df.empty:
            logger.warning("  No data for %s — skipping (may be unavailable on yfinance)", ticker)
            continue

        # Upsert to DB
        n = upsert_ohlcv(conn, ticker, df)
        total_inserted += n
        logger.info("  Inserted/updated %d rows for %s", n, ticker)

    # Post-audit
    logger.info("")
    logger.info("=== POST-AUDIT: Commodity data after backfill ===")
    audit_commodity_data(conn)

    logger.info("")
    logger.info("Total rows inserted/updated: %d", total_inserted)
    conn.close()


if __name__ == "__main__":
    main()
