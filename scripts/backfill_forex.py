"""Backfill major forex pairs into ohlcv table via yfinance.

Fetches daily OHLCV for major currency pairs and stores them in the
database with the same schema as equity data. Idempotent — uses
INSERT OR REPLACE (SQLite) / ON CONFLICT DO UPDATE (PostgreSQL).

Pairs to backfill:
  - Major USD pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCNY, USDCHF, USDSGD
  - Cross rates: EURJPY, GBPJPY, EURGBP, AUDJPY
  - IDR pairs (fill gaps): CNYIDR, SGDIDR (already have some)

Usage:
    python scripts/backfill_forex.py [--dry-run] [--ticker EURUSD=X]

References: AGENTS.md §2 (yfinance data source), pustaka/90.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text

from market.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# All forex pairs to backfill (yfinance ticker format)
FOREX_TICKERS: list[str] = [
    # Major USD pairs
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X",
    "USDCAD=X", "USDCNY=X", "USDCHF=X", "USDSGD=X",
    "USDMXN=X", "USDBRL=X", "USDINR=X", "USDKRW=X",
    "USDZAR=X", "USDTRY=X", "USDRUB=X", "USDTHB=X",
    "USDPHP=X", "USDMYR=X", "USDVND=X",
    # Cross rates
    "EURJPY=X", "GBPJPY=X", "EURGBP=X", "AUDJPY=X",
    "EURSGD=X", "EURCHF=X", "GBPCHF=X",
    # IDR pairs (fill gaps / extend history)
    "CNYIDR=X", "SGDIDR=X", "JPYIDR=X", "EURIDR=X",
    "GBPIDR=X", "AUDIDR=X", "KRWIDR=X", "CNYIDR=X",
    # US Dollar Index (already have, but refresh)
    "DX-Y.NYB",
]

# Instrument master entries for forex
FOREX_INSTRUMENTS: list[dict] = [
    {"ticker": "EURUSD=X", "name": "EUR/USD Exchange Rate", "base": "EUR", "reporting": "USD"},
    {"ticker": "GBPUSD=X", "name": "GBP/USD Exchange Rate", "base": "GBP", "reporting": "USD"},
    {"ticker": "USDJPY=X", "name": "USD/JPY Exchange Rate", "base": "USD", "reporting": "JPY"},
    {"ticker": "AUDUSD=X", "name": "AUD/USD Exchange Rate", "base": "AUD", "reporting": "USD"},
    {"ticker": "USDCAD=X", "name": "USD/CAD Exchange Rate", "base": "USD", "reporting": "CAD"},
    {"ticker": "USDCNY=X", "name": "USD/CNY Exchange Rate", "base": "USD", "reporting": "CNY"},
    {"ticker": "USDCHF=X", "name": "USD/CHF Exchange Rate", "base": "USD", "reporting": "CHF"},
    {"ticker": "USDSGD=X", "name": "USD/SGD Exchange Rate", "base": "USD", "reporting": "SGD"},
    {"ticker": "USDMXN=X", "name": "USD/MXN Exchange Rate", "base": "USD", "reporting": "MXN"},
    {"ticker": "USDBRL=X", "name": "USD/BRL Exchange Rate", "base": "USD", "reporting": "BRL"},
    {"ticker": "USDINR=X", "name": "USD/INR Exchange Rate", "base": "USD", "reporting": "INR"},
    {"ticker": "USDKRW=X", "name": "USD/KRW Exchange Rate", "base": "USD", "reporting": "KRW"},
    {"ticker": "USDZAR=X", "name": "USD/ZAR Exchange Rate", "base": "USD", "reporting": "ZAR"},
    {"ticker": "USDTRY=X", "name": "USD/TRY Exchange Rate", "base": "USD", "reporting": "TRY"},
    {"ticker": "USDRUB=X", "name": "USD/RUB Exchange Rate", "base": "USD", "reporting": "RUB"},
    {"ticker": "USDTHB=X", "name": "USD/THB Exchange Rate", "base": "USD", "reporting": "THB"},
    {"ticker": "USDPHP=X", "name": "USD/PHP Exchange Rate", "base": "USD", "reporting": "PHP"},
    {"ticker": "USDMYR=X", "name": "USD/MYR Exchange Rate", "base": "USD", "reporting": "MYR"},
    {"ticker": "USDVND=X", "name": "USD/VND Exchange Rate", "base": "USD", "reporting": "VND"},
    {"ticker": "EURJPY=X", "name": "EUR/JPY Exchange Rate", "base": "EUR", "reporting": "JPY"},
    {"ticker": "GBPJPY=X", "name": "GBP/JPY Exchange Rate", "base": "GBP", "reporting": "JPY"},
    {"ticker": "EURGBP=X", "name": "EUR/GBP Exchange Rate", "base": "EUR", "reporting": "GBP"},
    {"ticker": "AUDJPY=X", "name": "AUD/JPY Exchange Rate", "base": "AUD", "reporting": "JPY"},
    {"ticker": "EURSGD=X", "name": "EUR/SGD Exchange Rate", "base": "EUR", "reporting": "SGD"},
    {"ticker": "EURCHF=X", "name": "EUR/CHF Exchange Rate", "base": "EUR", "reporting": "CHF"},
    {"ticker": "GBPCHF=X", "name": "GBP/CHF Exchange Rate", "base": "GBP", "reporting": "CHF"},
    {"ticker": "GBPIDR=X", "name": "GBP/IDR Exchange Rate", "base": "GBP", "reporting": "IDR"},
    {"ticker": "AUDIDR=X", "name": "AUD/IDR Exchange Rate", "base": "AUD", "reporting": "IDR"},
    {"ticker": "KRWIDR=X", "name": "KRW/IDR Exchange Rate", "base": "KRW", "reporting": "IDR"},
]


def get_engine():
    """Get SQLAlchemy engine from settings."""
    db_url = settings.database_url
    if db_url.startswith("postgresql"):
        return create_engine(db_url)
    else:
        db_path = settings.db_path
        return create_engine(f"sqlite:///{db_path}")


def is_postgres(engine) -> bool:
    return engine.dialect.name == "postgresql"


def fetch_forex(ticker: str, period: str = "max") -> pd.DataFrame | None:
    """Fetch daily forex data from yfinance."""
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if df is None or df.empty:
            logger.warning("No data for %s", ticker)
            return None
        # Flatten multi-level columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "timestamp",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "adjusted_close",
            "Volume": "volume",
        })
        # Ensure timestamp is naive datetime (strip tz for DB compat)
        if df["timestamp"].dt.tz is not None:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
        # Fill adjusted_close if missing
        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = df["close"]
        df["volume"] = df.get("volume", 0).fillna(0).astype(int)
        return df
    except Exception as e:
        logger.error("Failed to fetch %s: %s", ticker, e)
        return None


def upsert_ohlcv(engine, ticker: str, df: pd.DataFrame) -> int:
    """Insert OHLCV rows (delete existing for same ticker first). Returns rows written."""
    rows_written = 0

    with engine.begin() as conn:
        # Delete existing rows for this ticker (full replace)
        conn.execute(text("DELETE FROM ohlcv WHERE ticker = :ticker"), {"ticker": ticker})

        # Batch insert
        params = []
        for _, row in df.iterrows():
            ts = row["timestamp"]
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()
            params.append({
                "ticker": ticker, "ts": ts,
                "o": float(row["open"]), "h": float(row["high"]),
                "l": float(row["low"]), "c": float(row["close"]),
                "ac": float(row["adjusted_close"]),
                "v": int(row["volume"]),
                "src": "yfinance", "tf": "1d",
            })

        conn.execute(text("""
            INSERT INTO ohlcv (ticker, exchange_mic, timestamp, timeframe, open, high, low, close, adjusted_close, volume, source)
            VALUES (:ticker, 'XFXS', :ts, :tf, :o, :h, :l, :c, :ac, :v, :src)
        """), params)
        rows_written = len(params)

    return rows_written


def upsert_instrument_master(engine, instruments: list[dict]) -> int:
    """Insert or update forex instruments in instrument_master."""
    count = 0

    with engine.begin() as conn:
        for inst in instruments:
            # Delete existing then insert (avoid ON CONFLICT issues)
            conn.execute(text("DELETE FROM instrument_master WHERE ticker = :ticker"), {"ticker": inst["ticker"]})
            conn.execute(text("""
                INSERT INTO instrument_master (ticker, market_mic, asset_class, name, base_currency, reporting_currency, is_active)
                VALUES (:ticker, 'XFXS', 'fx', :name, :base, :reporting, true)
            """), inst)
            count += 1

    return count


def main():
    parser = argparse.ArgumentParser(description="Backfill forex pairs into ohlcv")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, don't write to DB")
    parser.add_argument("--ticker", type=str, default=None, help="Single ticker to backfill")
    parser.add_argument("--period", type=str, default="max", help="yfinance period (default: max)")
    args = parser.parse_args()

    tickers = [args.ticker] if args.ticker else FOREX_TICKERS
    # Deduplicate
    seen = set()
    tickers = [t for t in tickers if not (t in seen or seen.add(t))]

    logger.info("Backfilling %d forex tickers (period=%s, dry_run=%s)", len(tickers), args.period, args.dry_run)

    if not args.dry_run:
        engine = get_engine()
        pg = is_postgres(engine)
        logger.info("Database: %s", "PostgreSQL" if pg else "SQLite")

        # Register instruments
        inst_count = upsert_instrument_master(engine, FOREX_INSTRUMENTS)
        logger.info("Instrument master: %d forex instruments upserted", inst_count)
    else:
        engine = None

    total_rows = 0
    success = 0
    failed = 0

    for i, ticker in enumerate(tickers, 1):
        logger.info("[%d/%d] Fetching %s ...", i, len(tickers), ticker)
        df = fetch_forex(ticker, period=args.period)
        if df is None or df.empty:
            logger.warning("  No data for %s", ticker)
            failed += 1
            continue

        logger.info("  Fetched %d rows: %s → %s",
                     len(df), df["timestamp"].iloc[0].date(), df["timestamp"].iloc[-1].date())

        if not args.dry_run:
            written = upsert_ohlcv(engine, ticker, df)
            logger.info("  Written %d rows to ohlcv", written)
            total_rows += written

        success += 1

    logger.info("")
    logger.info("=== BACKFILL COMPLETE ===")
    logger.info("Success: %d / %d tickers", success, len(tickers))
    logger.info("Failed: %d", failed)
    logger.info("Total rows written: %d", total_rows)


if __name__ == "__main__":
    main()
