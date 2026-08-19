#!/usr/bin/env python3
"""Dry-run test for all signal engines — verify each produces non-FLAT signals.

Tests a sample of tickers and dates to:
1. Verify all 16 engines produce directional signals (non-FLAT)
2. Measure computation time per ticker-day
3. Identify engines that need fixing
4. Estimate full backfill duration

Usage:
    python scripts/engine_dry_run_test.py --tickers BBCA.JK,BBRI.JK,TPIA.JK --days 30
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime, timedelta

warnings.filterwarnings("ignore", message=".*not converging.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

import pandas as pd
import psycopg2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.backfill_signal_attribution import compute_engine_signals


def get_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return "postgresql://petrick:market_dev@localhost:5432/market"


def get_trading_dates(conn, start_date, end_date):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT timestamp::date FROM stock_prices
            WHERE ticker = '^JKSE' AND timeframe = '1d'
            AND timestamp::date BETWEEN %s AND %s
            ORDER BY timestamp::date
        """, (start_date, end_date))
        return [r[0] for r in cur.fetchall()]


def load_prices(conn, ticker, as_of_date):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM stock_prices
            WHERE ticker = %s AND timeframe = '1d'
            AND timestamp <= %s
            ORDER BY timestamp DESC LIMIT 300
        """, (ticker, as_of_date))
        rows = cur.fetchall()
        if not rows or len(rows) < 30:
            return None
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df


def main():
    parser = argparse.ArgumentParser(description="Dry-run test for signal engines")
    parser.add_argument("--tickers", type=str, default="BBCA.JK,BBRI.JK,TPIA.JK,DEWA.JK,DSSA.JK",
                        help="Comma-separated tickers to test")
    parser.add_argument("--days", type=int, default=30, help="Number of trading days to test")
    args = parser.parse_args()

    tickers = args.tickers.split(",")
    db_url = get_db_url()
    print(f"Connecting to: {db_url.split('@')[1] if '@' in db_url else db_url}")
    conn = psycopg2.connect(db_url)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=args.days + 30)
    trading_dates = get_trading_dates(conn, start_date, end_date)
    trading_dates = trading_dates[-args.days:]
    print(f"Testing {len(tickers)} tickers × {len(trading_dates)} dates = {len(tickers) * len(trading_dates)} ticker-days")
    print(f"Date range: {trading_dates[0]} to {trading_dates[-1]}")
    print()

    # Stats per engine
    engine_stats = defaultdict(lambda: {
        "total": 0, "up": 0, "down": 0, "flat": 0,
        "errors": 0, "signal_values": [], "times": []
    })

    total_ticker_days = 0
    successful_ticker_days = 0
    t0 = time.time()

    for i, dt in enumerate(trading_dates):
        for ticker in tickers:
            df = load_prices(conn, ticker, dt)
            if df is None or len(df) < 30:
                continue

            total_ticker_days += 1
            t1 = time.time()
            try:
                signals = compute_engine_signals(df, ticker, dt, conn=conn)
                elapsed = time.time() - t1

                if signals:
                    successful_ticker_days += 1

                for s in signals:
                    name = s["engine_name"]
                    engine_stats[name]["total"] += 1
                    engine_stats[name]["times"].append(elapsed / max(len(signals), 1))
                    engine_stats[name]["signal_values"].append(s["signal_value"])
                    dir = s["signal_direction"]
                    if dir == "UP":
                        engine_stats[name]["up"] += 1
                    elif dir == "DOWN":
                        engine_stats[name]["down"] += 1
                    else:
                        engine_stats[name]["flat"] += 1

            except Exception as e:
                elapsed = time.time() - t1
                print(f"  ERROR {ticker} {dt}: {e}")
            finally:
                conn.rollback()

        if (i + 1) % 5 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(trading_dates)}] {dt} | {successful_ticker_days} successful | {elapsed:.1f}s")

    total_elapsed = time.time() - t0
    print(f"\n{'='*80}")
    print(f"DRY-RUN RESULTS: {successful_ticker_days}/{total_ticker_days} ticker-days successful in {total_elapsed:.1f}s")
    print(f"{'='*80}")
    print(f"\n{'Engine':<25s} {'Total':>6s} {'UP':>6s} {'DOWN':>6s} {'FLAT':>6s} {'%FLAT':>7s} {'AvgSig':>8s} {'AvgTime':>8s}")
    print("-" * 85)

    for name in sorted(engine_stats.keys()):
        s = engine_stats[name]
        pct_flat = 100.0 * s["flat"] / max(s["total"], 1)
        avg_sig = sum(s["signal_values"]) / max(len(s["signal_values"]), 1)
        avg_time = sum(s["times"]) / max(len(s["times"]), 1)
        flag = ""
        if pct_flat > 90:
            flag = " ⚠️ ALL FLAT"
        elif pct_flat > 70:
            flag = " ⚠️ MOSTLY FLAT"
        print(f"{name:<25s} {s['total']:>6d} {s['up']:>6d} {s['down']:>6d} {s['flat']:>6d} {pct_flat:>6.1f}% {avg_sig:>+8.4f} {avg_time:>7.4f}s{flag}")

    # Estimate full backfill time
    avg_per_td = total_elapsed / max(successful_ticker_days, 1)
    print(f"\n{'='*80}")
    print(f"ESTIMATION FOR FULL BACKFILL:")
    print(f"  Avg time per ticker-day: {avg_per_td:.3f}s")
    print(f"  20 tickers × 250 days = 5000 ticker-days → est. {avg_per_td * 5000 / 60:.1f} min")
    print(f"  50 tickers × 250 days = 12500 ticker-days → est. {avg_per_td * 12500 / 60:.1f} min")
    print(f"  100 tickers × 250 days = 25000 ticker-days → est. {avg_per_td * 25000 / 3600:.1f} hours")

    # Identify engines needing attention
    print(f"\n{'='*80}")
    print("ENGINES NEEDING ATTENTION:")
    for name in sorted(engine_stats.keys()):
        s = engine_stats[name]
        pct_flat = 100.0 * s["flat"] / max(s["total"], 1)
        if pct_flat > 70:
            print(f"  ⚠️  {name}: {pct_flat:.1f}% FLAT — needs wiring or parameter tuning")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
