#!/usr/bin/env python3
"""Backfill astronacci_cycles table with computed Astronacci cycles.

Computes all Astronacci cycle events (Moon Phases, Planetary Retrogrades,
Planetary Ingresses, Fibonacci Price Retracement levels) for the full date
range covered by the stock_prices table, and inserts them into PostgreSQL.

Usage:
    python scripts/backfill_astronacci.py [--dry-run] [--fibonacci]
    python scripts/backfill_astronacci.py --start 2020-01-01 --end 2026-12-31

Environment:
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5432/market
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import psycopg2
import psycopg2.extras

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.market.analysis.astronacci import AstronacciEngine, AstronacciCycle


def get_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        url = "postgresql://petrick:market_dev@localhost:5432/market"
    return url


def get_date_range(conn) -> tuple[datetime, datetime]:
    """Get min/max timestamp from stock_prices."""
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM stock_prices")
        row = cur.fetchone()
        if row and row[0] and row[1]:
            return row[0], row[1]
    # Fallback
    return datetime(2000, 1, 1, tzinfo=timezone.utc), datetime(2026, 12, 31, tzinfo=timezone.utc)


def get_index_prices(conn, ticker: str = "^JKSE") -> pd.DataFrame:
    """Get daily price data for Fibonacci time window computation."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT timestamp, close FROM stock_prices "
            "WHERE ticker = %s AND timeframe = '1d' "
            "ORDER BY timestamp",
            (ticker,),
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["timestamp", "close"])
    return pd.DataFrame(rows, columns=["timestamp", "close"])


def clear_existing(conn) -> int:
    """Clear existing astronacci_cycles data. Returns deleted count."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM astronacci_cycles")
        count = cur.fetchone()[0]
        if count > 0:
            cur.execute("TRUNCATE astronacci_cycles RESTART IDENTITY")
            conn.commit()
            print(f"  Cleared {count} existing rows")
    return count


def insert_cycles(conn, cycles: list[AstronacciCycle]) -> int:
    """Insert AstronacciCycle events into PostgreSQL."""
    if not cycles:
        return 0

    rows = []
    for c in cycles:
        rows.append((
            c.cycle_type,
            c.title,
            c.start_at,
            c.end_at,
            c.potential_impact,
            c.target_asset_class,
            c.expected_reversal,
            c.description,
        ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO astronacci_cycles
                (cycle_type, title, start_at, end_at,
                 potential_impact, target_asset_class, expected_reversal, description)
            VALUES %s
            ON CONFLICT DO NOTHING
            """,
            rows,
            page_size=500,
        )
    conn.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Backfill astronacci_cycles table")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't insert")
    parser.add_argument("--fibonacci", action="store_true", help="Include Fibonacci price retracement levels")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--fib-ticker", type=str, default="^JKSE", help="Ticker for Fibonacci swing detection")
    args = parser.parse_args()

    db_url = get_db_url()
    print(f"Connecting to: {db_url.split('@')[1] if '@' in db_url else db_url}")

    conn = psycopg2.connect(db_url)

    # Determine date range
    if args.start and args.end:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        start_dt, end_dt = get_date_range(conn)

    print(f"Date range: {start_dt} to {end_dt}")
    print(f"Duration: {(end_dt - start_dt).days} days ({(end_dt - start_dt).days / 365.25:.1f} years)")

    # Get price data for Fibonacci if requested
    prices = None
    if args.fibonacci:
        print(f"Loading price data for Fibonacci computation (ticker={args.fib_ticker})...")
        prices = get_index_prices(conn, args.fib_ticker)
        print(f"  Loaded {len(prices)} price rows")

    # Clear existing
    if not args.dry_run:
        clear_existing(conn)

    # Compute cycles
    print("Computing Astronacci cycles...")
    t0 = time.time()

    engine = AstronacciEngine(include_fibonacci=args.fibonacci)
    cycles = engine.compute(start_dt, end_dt, prices=prices)

    elapsed = time.time() - t0
    print(f"  Computed {len(cycles)} cycles in {elapsed:.1f}s")

    # Summary by type
    by_type: dict[str, int] = {}
    for c in cycles:
        by_type[c.cycle_type] = by_type.get(c.cycle_type, 0) + 1

    print("\nBreakdown by cycle type:")
    for ct, count in sorted(by_type.items()):
        print(f"  {ct:30s} {count:6d}")

    # Insert
    if args.dry_run:
        print(f"\n[DRY RUN] Would insert {len(cycles)} rows")
    else:
        inserted = insert_cycles(conn, cycles)
        print(f"\nInserted {inserted} rows into astronacci_cycles")

        # Verify
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM astronacci_cycles")
            total = cur.fetchone()[0]
            cur.execute("SELECT MIN(start_at), MAX(start_at) FROM astronacci_cycles")
            min_dt, max_dt = cur.fetchone()
            print(f"Table now has {total} rows")
            print(f"Date range: {min_dt} to {max_dt}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
