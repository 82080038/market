#!/usr/bin/env python3
"""Backfill broker_transactions in PostgreSQL from SQLite data.

Strategy:
  broker_flow has only __MARKET__ aggregate data (per broker per day, no ticker).
  We render per-ticker transactions by:
  1. For each trading day with OHLCV data, take top N most active tickers by volume
  2. Distribute volume across brokers using deterministic weighted random
  3. Split into BUY/SELL based on daily price movement (up day → more BUY)

  This produces realistic per-ticker broker transaction data for the domino
  timeline analysis, derived from real OHLCV volume and real broker names.

Usage:
  DB_PATH=data/market_research.db uv run python scripts/backfill_broker_transactions.py \
      --pg-url "postgresql://petrick:market_dev@localhost:5432/market" \
      --start-date 2024-01-01 --top-tickers 50
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sqlite3
import subprocess
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_db_path() -> str:
    return os.environ.get("DB_PATH", "data/market_research.db")


def sql_escape(val: str | None) -> str:
    if val is None:
        return "NULL"
    return "'" + val.replace("'", "''") + "'"


def sql_val(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    return sql_escape(str(val))


def backfill(
    sqlite_conn: sqlite3.Connection,
    pg_url: str,
    start_date: str,
    end_date: str | None,
    top_tickers: int,
    batch_days: int = 30,
) -> int:
    """Generate broker_transactions from OHLCV volume + broker list."""

    # Load brokers from SQLite
    brokers = sqlite_conn.execute(
        "SELECT id_broker, nama_broker FROM broker ORDER BY id_broker"
    ).fetchall()
    broker_ids = [b[0] for b in brokers]
    broker_codes = {b[0]: f"BR{b[0]:04d}" for b in brokers}
    logger.info("Loaded %d brokers", len(brokers))

    if not broker_ids:
        logger.error("No brokers found in SQLite")
        return 0

    # Broker weight distribution (top brokers get more volume)
    # Deterministic seeded random for reproducibility
    rng = random.Random(42)
    broker_weights = [rng.uniform(0.5, 1.0) for _ in broker_ids]
    total_weight = sum(broker_weights)
    broker_weights = [w / total_weight for w in broker_weights]

    end = date.fromisoformat(end_date) if end_date else date.today()
    start = date.fromisoformat(start_date)

    # Get all trading dates from OHLCV in range
    dates = sqlite_conn.execute(
        "SELECT DISTINCT date(timestamp) as d FROM ohlcv "
        "WHERE timeframe='1d' AND date(timestamp) >= ? AND date(timestamp) <= ? "
        "ORDER BY d",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    trading_dates = [d[0] for d in dates]
    logger.info("Trading dates: %d (%s to %s)", len(trading_dates), trading_dates[0] if trading_dates else "?", trading_dates[-1] if trading_dates else "?")

    total_count = 0
    batch_num = 0

    for i in range(0, len(trading_dates), batch_days):
        batch_dates = trading_dates[i:i + batch_days]
        batch_num += 1

        out = StringIO()

        for dt in batch_dates:
            # Get top tickers by volume for this date
            rows = sqlite_conn.execute(
                "SELECT ticker, close, volume, open FROM ohlcv "
                "WHERE timeframe='1d' AND date(timestamp) = ? AND volume > 0 "
                "ORDER BY volume DESC LIMIT ?",
                (dt, top_tickers),
            ).fetchall()

            if not rows:
                continue

            for ticker, close, volume, open_price in rows:
                if not ticker or ticker.startswith("^") or ticker == "IDR=X":
                    continue

                exchange_mic = "XIDX" if ticker.endswith(".JK") else "XNYS"

                # Determine buy/sell ratio from price movement
                if open_price and close and open_price > 0:
                    daily_return = (close - open_price) / open_price
                else:
                    daily_return = 0

                # Up day: 60-70% buy volume, down day: 40-50%
                buy_ratio = 0.55 + 0.15 * max(-1, min(1, daily_return * 10))
                buy_volume = int(volume * buy_ratio)
                sell_volume = volume - buy_volume

                # Distribute across top 5-8 brokers
                n_brokers = rng.randint(5, min(8, len(broker_ids)))
                selected_indices = rng.sample(range(len(broker_ids)), n_brokers)
                selected_weights = [broker_weights[idx] for idx in selected_indices]
                sw_sum = sum(selected_weights)
                selected_weights = [w / sw_sum for w in selected_weights]

                ts = f"{dt}T08:00:00+00:00"  # approximate mid-session UTC

                # Generate BUY transactions
                remaining_buy = buy_volume
                for j, idx in enumerate(selected_indices):
                    broker_id = broker_ids[idx]
                    broker_code = broker_codes[broker_id]
                    is_foreign = broker_id <= 5  # top 5 brokers are foreign

                    if j == n_brokers - 1:
                        vol = remaining_buy
                    else:
                        vol = int(buy_volume * selected_weights[j])
                        remaining_buy -= vol

                    if vol <= 0:
                        continue

                    # Estimate price as close ± small random spread
                    price = float(close) * rng.uniform(0.999, 1.001)
                    if price <= 0:
                        continue

                    out.write(
                        f"INSERT INTO broker_transactions "
                        f"(ticker, exchange_mic, timestamp, side, order_type, "
                        f"quantity, price, status, is_foreign) VALUES (\n"
                        f"  {sql_val(ticker)}, {sql_val(exchange_mic)}, {sql_val(ts)}, "
                        f"'BUY', 'MARKET', {sql_val(vol)}, {sql_val(round(price, 6))}, "
                        f"'FILLED', {sql_val(is_foreign)}\n);\n"
                    )
                    total_count += 1

                # Generate SELL transactions
                remaining_sell = sell_volume
                for j, idx in enumerate(selected_indices):
                    broker_id = broker_ids[idx]
                    is_foreign = broker_id <= 5

                    if j == n_brokers - 1:
                        vol = remaining_sell
                    else:
                        vol = int(sell_volume * selected_weights[j])
                        remaining_sell -= vol

                    if vol <= 0:
                        continue

                    price = float(close) * rng.uniform(0.999, 1.001)
                    if price <= 0:
                        continue

                    out.write(
                        f"INSERT INTO broker_transactions "
                        f"(ticker, exchange_mic, timestamp, side, order_type, "
                        f"quantity, price, status, is_foreign) VALUES (\n"
                        f"  {sql_val(ticker)}, {sql_val(exchange_mic)}, {sql_val(ts)}, "
                        f"'SELL', 'MARKET', {sql_val(vol)}, {sql_val(round(price, 6))}, "
                        f"'FILLED', {sql_val(is_foreign)}\n);\n"
                    )
                    total_count += 1

        # Execute batch via psql
        sql_content = out.getvalue()
        if sql_content.strip():
            tmp_path = tempfile.mktemp(suffix=".sql")
            Path(tmp_path).write_text(sql_content)
            result = subprocess.run(
                ["psql", pg_url, "-f", tmp_path, "-v", "ON_ERROR_STOP=1", "-q"],
                capture_output=True, text=True,
            )
            Path(tmp_path).unlink(missing_ok=True)

            if result.returncode != 0:
                logger.warning("Batch %d: psql error: %s", batch_num, result.stderr[:500])
            else:
                logger.info("Batch %d: dates %s..%s, %d transactions",
                           batch_num, batch_dates[0], batch_dates[-1],
                           sql_content.count("INSERT INTO"))

        if total_count % 10000 == 0 and total_count > 0:
            logger.info("Total transactions generated: %d", total_count)

    logger.info("Backfill complete: %d total broker_transactions", total_count)
    return total_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill broker_transactions in PostgreSQL")
    parser.add_argument("--pg-url", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--start-date", default="2024-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=None, help="End date (default: today)")
    parser.add_argument("--top-tickers", type=int, default=50, help="Top N tickers per day by volume")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no insert")
    args = parser.parse_args()

    db_path = get_db_path()
    logger.info("SQLite source: %s", db_path)
    logger.info("PG target: %s", args.pg_url)

    sqlite_conn = sqlite3.connect(db_path)

    if args.dry_run:
        # Count trading days and estimate
        end = args.end_date or date.today().isoformat()
        cnt = sqlite_conn.execute(
            "SELECT COUNT(DISTINCT date(timestamp)) FROM ohlcv "
            "WHERE timeframe='1d' AND date(timestamp) >= ? AND date(timestamp) <= ?",
            (args.start_date, end),
        ).fetchone()[0]
        est = cnt * args.top_tickers * 14  # ~14 transactions per ticker (7 buy + 7 sell)
        logger.info("DRY RUN: ~%d trading days × %d tickers × ~14 txns = ~%d transactions", cnt, args.top_tickers, est)
        sqlite_conn.close()
        return

    backfill(
        sqlite_conn, args.pg_url,
        start_date=args.start_date,
        end_date=args.end_date,
        top_tickers=args.top_tickers,
    )
    sqlite_conn.close()


if __name__ == "__main__":
    main()
