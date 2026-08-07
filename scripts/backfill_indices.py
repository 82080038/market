"""Backfill missing index OHLCV data from yfinance.

Backfills:
1. ^JKSE (IDX Composite) — full history (currently only 2021-07+)
2. ^LQ45 — full history (currently 0 rows)
3. 12 IDX sectoral indices (currently not in DB at all)
4. Global indices backfill: ^DJI, ^FTSE, ^GDAXI (currently only mid-2024+)
5. Fix instrument_master entries for all indices (correct market_mic, currency)

Usage:
    python scripts/backfill_indices.py [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf
from sqlalchemy import select

from market.data.contracts import NormalizedOHLCV
from market.data.rate_limit import RateLimiter
from market.data.ticker_util import from_yf_ticker, get_currency
from market.db.engine import get_sessionmaker
from market.db.models import InstrumentMaster, OHLCV

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

limiter = RateLimiter(max_calls=0.8, window_seconds=1.0)

# All indices to backfill, with metadata
# (ticker, market_mic, currency, name, asset_class)
# IDX sectoral indices use .JK suffix on Yahoo Finance (not ^ prefix)
# LQ45 is ^JKLQ45 on Yahoo Finance (not ^LQ45)
# Source: verified via Yahoo Finance quote pages
INDICES = [
    # IDX indices
    ("^JKSE", "XIDX", "IDR", "IDX Composite", "index"),
    ("^JKLQ45", "XIDX", "IDR", "IDX LQ45", "index"),
    ("IDX30.JK", "XIDX", "IDR", "IDX30", "index"),
    ("IDX80.JK", "XIDX", "IDR", "IDX80", "index"),
    ("IDXENERGY.JK", "XIDX", "IDR", "IDX SEC Energy", "index"),
    ("IDXFINANCE.JK", "XIDX", "IDR", "IDX SEC Financials", "index"),
    ("IDXHEALTH.JK", "XIDX", "IDR", "IDX SEC Healthcare", "index"),
    ("IDXINDUST.JK", "XIDX", "IDR", "IDX SEC Industrials", "index"),
    ("IDXBASIC.JK", "XIDX", "IDR", "IDX SEC Basic Materials", "index"),
    ("IDXPROPER.JK", "XIDX", "IDR", "IDX SEC Property", "index"),
    ("IDXTECHNO.JK", "XIDX", "IDR", "IDX SEC Technology", "index"),
    ("IDXTRANS.JK", "XIDX", "IDR", "IDX SEC Transportation & Logistics", "index"),
    ("IDXINFRA.JK", "XIDX", "IDR", "IDX SEC Infrastructure", "index"),
    ("IDXNONCYC.JK", "XIDX", "IDR", "IDX SEC Consumer Non-Cyclicals", "index"),
    ("IDXCYCLIC.JK", "XIDX", "IDR", "IDX SEC Consumer Cyclicals", "index"),
    # Global indices (backfill full history)
    ("^DJI", "XNYS", "USD", "Dow Jones Industrial Average", "index"),
    ("^FTSE", "XLON", "GBP", "FTSE 100", "index"),
    ("^GDAXI", "XFRA", "EUR", "DAX", "index"),
    # Also backfill these for completeness (they have data from 2021 only)
    ("^GSPC", "XNYS", "USD", "S&P 500", "index"),
    ("^IXIC", "XNAS", "USD", "NASDAQ Composite", "index"),
    ("^VIX", "XNYS", "USD", "CBOE Volatility Index", "index"),
    ("^HSI", "XHKG", "HKD", "Hang Seng Index", "index"),
    ("^N225", "XTSE", "JPY", "Nikkei 225", "index"),
    ("^TNX", "XNYS", "USD", "CBOE 10-Year Treasury Yield", "index"),
    ("000001.SS", "XSHG", "CNY", "Shanghai Composite Index", "index"),
    ("DX-Y.NYB", "XNYS", "USD", "US Dollar Index (DXY)", "index"),
]

# Old wrong tickers that need to be cleaned up from instrument_master
OBSOLETE_TICKERS = [
    "^LQ45", "^IDX30", "^IDX80", "^IDXENERGY", "^IDXFINANCE",
    "^IDXHEALTH", "^IDXINDUST", "^IDXMINE", "^IDXPROPER",
    "^IDXTECH", "^IDXTRANS", "^IDXINFRA", "^IDXCONSUMER",
]


def cleanup_obsolete_tickers(session) -> int:
    """Remove obsolete wrong ticker entries from instrument_master."""
    logger.info("=== Cleaning up %d obsolete tickers ===", len(OBSOLETE_TICKERS))
    count = 0
    for ticker in OBSOLETE_TICKERS:
        existing = session.execute(
            select(InstrumentMaster).where(InstrumentMaster.ticker == ticker)
        ).scalar_one_or_none()
        if existing:
            session.delete(existing)
            session.commit()
            logger.info("  Deleted obsolete ticker %s", ticker)
            count += 1
    logger.info("  Cleaned up %d obsolete entries", count)
    return count


def ensure_instrument_master(session) -> int:
    """Insert or update instrument_master entries for all indices.

    Returns count of entries added/updated.
    """
    logger.info("=== Ensuring instrument_master entries for %d indices ===", len(INDICES))
    count = 0
    for ticker, mic, currency, name, asset_class in INDICES:
        existing = session.execute(
            select(InstrumentMaster).where(InstrumentMaster.ticker == ticker)
        ).scalar_one_or_none()

        if existing:
            # Fix metadata if wrong
            changed = False
            if existing.market_mic != mic:
                logger.info("  Fixing %s market_mic: %s -> %s", ticker, existing.market_mic, mic)
                existing.market_mic = mic
                changed = True
            if existing.base_currency != currency:
                logger.info("  Fixing %s base_currency: %s -> %s", ticker, existing.base_currency, currency)
                existing.base_currency = currency
                changed = True
            if existing.reporting_currency != currency:
                existing.reporting_currency = currency
                changed = True
            if existing.name != name and (not existing.name or len(existing.name) < len(name)):
                existing.name = name
                changed = True
            if existing.asset_class != asset_class:
                existing.asset_class = asset_class
                changed = True
            if changed:
                session.commit()
                count += 1
        else:
            session.add(InstrumentMaster(
                ticker=ticker,
                market_mic=mic,
                asset_class=asset_class,
                name=name,
                base_currency=currency,
                reporting_currency=currency,
                is_active=True,
            ))
            session.commit()
            logger.info("  Added %s (%s) to instrument_master", ticker, name)
            count += 1

    logger.info("  instrument_master: %d entries added/updated", count)
    return count


def fetch_index_ohlcv(
    ticker: str,
    market_mic: str,
    currency: str,
    start_date: date | None = None,
) -> list[NormalizedOHLCV]:
    """Fetch full historical OHLCV for an index from yfinance.

    Args:
        ticker: yfinance ticker (e.g. ^JKSE).
        market_mic: Market MIC code.
        currency: Native currency.
        start_date: Optional start date. If None, fetches max history.

    Returns:
        List of NormalizedOHLCV records.
    """
    limiter.acquire()

    end_date = date.today() - timedelta(days=1)

    logger.info("  Fetching %s (start=%s, end=%s)...", ticker, start_date or "max", end_date)

    try:
        if start_date:
            df = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                progress=False,
                interval="1d",
            )
        else:
            df = yf.download(
                ticker,
                period="max",
                auto_adjust=True,
                progress=False,
                interval="1d",
            )
    except Exception as exc:
        logger.error("  yfinance download failed for %s: %s", ticker, exc)
        return []

    if df is None or df.empty:
        logger.warning("  No data returned for %s", ticker)
        return []

    # Flatten multi-index columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    records: list[NormalizedOHLCV] = []
    for ts, row in df.iterrows():
        try:
            ts_dt = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=UTC)

            if pd.isna(row.get("Open")) or pd.isna(row.get("Close")):
                continue

            records.append(
                NormalizedOHLCV(
                    ticker=ticker,
                    market_mic=market_mic,
                    asset_class="index",
                    timestamp=ts_dt,
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close=Decimal(str(row["Close"])),
                    volume=int(row["Volume"]) if not pd.isna(row.get("Volume")) else 0,
                    adjusted_close=(
                        Decimal(str(row["Adj Close"]))
                        if "Adj Close" in row and not pd.isna(row.get("Adj Close"))
                        else Decimal(str(row["Close"]))
                    ),
                    currency=currency,
                    source="yahoo_finance",
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("  Skipping row for %s at %s: %s", ticker, ts, exc)

    return records


def save_ohlcv_records(session, records: list[NormalizedOHLCV]) -> int:
    """Save OHLCV records with INSERT OR REPLACE semantics.

    Returns number of new records inserted (not updated).
    """
    new_count = 0
    for r in records:
        tf = "1d"
        existing = session.execute(
            select(OHLCV).where(
                OHLCV.ticker == r.ticker,
                OHLCV.timestamp == r.timestamp,
                OHLCV.timeframe == tf,
            )
        ).scalar_one_or_none()

        if existing:
            existing.open = r.open
            existing.high = r.high
            existing.low = r.low
            existing.close = r.close
            existing.volume = r.volume
            existing.adjusted_close = r.adjusted_close
            existing.source = r.source
        else:
            session.add(OHLCV(
                ticker=r.ticker,
                timestamp=r.timestamp,
                timeframe=tf,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                adjusted_close=r.adjusted_close,
                source=r.source,
            ))
            new_count += 1

    session.commit()
    return new_count


def get_existing_coverage(session, ticker: str) -> tuple[str | None, str | None, int]:
    """Get current OHLCV coverage for a ticker.

    Returns (min_timestamp, max_timestamp, row_count).
    """
    from sqlalchemy import func

    result = session.execute(
        select(
            func.min(OHLCV.timestamp),
            func.max(OHLCV.timestamp),
            func.count(),
        ).where(
            OHLCV.ticker == ticker,
            OHLCV.timeframe == "1d",
        )
    ).one()
    return result[0], result[1], result[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing index OHLCV data")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("INDEX BACKFILL SCRIPT")
    logger.info("Indices to process: %d", len(INDICES))
    logger.info("Dry run: %s", args.dry_run)
    logger.info("=" * 70)

    session = get_sessionmaker()()

    try:
        # Step 0: Clean up obsolete wrong tickers
        if not args.dry_run:
            cleanup_obsolete_tickers(session)

        # Step 1: Ensure instrument_master entries
        if not args.dry_run:
            im_count = ensure_instrument_master(session)
        else:
            logger.info("[DRY RUN] Would ensure %d instrument_master entries", len(INDICES))
            im_count = 0

        # Step 2: Fetch and save OHLCV data
        total_new = 0
        total_skipped = 0

        for ticker, mic, currency, name, _ in INDICES:
            # Check existing coverage
            min_ts, max_ts, count = get_existing_coverage(session, ticker)

            if count > 0:
                logger.info(
                    "  %s: existing coverage %s to %s (%d rows)",
                    ticker, min_ts, max_ts, count,
                )
                # Fetch full history to fill gaps (yfinance will return everything)
            else:
                logger.info("  %s: NO existing data, will fetch full history", ticker)

            if args.dry_run:
                logger.info("[DRY RUN] Would fetch %s from yfinance", ticker)
                total_skipped += 1
                continue

            # Fetch data
            records = fetch_index_ohlcv(ticker, mic, currency)

            if not records:
                logger.warning("  %s: no data fetched (may not be available on yfinance)", ticker)
                continue

            # Save
            new_count = save_ohlcv_records(session, records)
            total_new += new_count
            logger.info("  %s: %d new rows inserted (%d total fetched)", ticker, new_count, len(records))

        # Step 3: Summary
        logger.info("=" * 70)
        logger.info("BACKFILL COMPLETE")
        logger.info("  instrument_master: %d entries added/updated", im_count)
        logger.info("  OHLCV new rows: %d", total_new)
        if args.dry_run:
            logger.info("  [DRY RUN] %d indices skipped", total_skipped)
        logger.info("=" * 70)

        # Print final coverage table
        logger.info("\nFinal index coverage:")
        logger.info("%-16s %-12s %-12s %-8s %-8s", "Ticker", "Start", "End", "Rows", "Currency")
        logger.info("-" * 60)
        for ticker, mic, currency, name, _ in INDICES:
            min_ts, max_ts, count = get_existing_coverage(session, ticker)
            logger.info(
                "%-16s %-12s %-12s %-8d %-8s",
                ticker,
                str(min_ts)[:10] if min_ts else "N/A",
                str(max_ts)[:10] if max_ts else "N/A",
                count,
                currency,
            )

    finally:
        session.close()


if __name__ == "__main__":
    main()
