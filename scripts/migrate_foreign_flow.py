"""Migrate foreign_flow from SQLite to PostgreSQL (non-blocking, batched).

Reads 1.25M rows from SQLite in batches of 5000 and upserts to PostgreSQL.
Uses COPY for fast bulk insert with ON CONFLICT handling.

Usage:
    uv run python scripts/migrate_foreign_flow.py &
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SQLITE_PATH = "/home/petrick/projects/market/data/market_research.db"
PG_DSN = "postgresql://petrick:market_dev@localhost:5432/market"
BATCH_SIZE = 5000


def migrate():
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(PG_DSN)
    pg_conn.autocommit = False

    # Get total count
    total = sqlite_conn.execute("SELECT COUNT(*) FROM foreign_flow").fetchone()[0]
    logger.info("Migrating %d foreign_flow rows SQLite → PostgreSQL", total)

    # Read in batches using OFFSET (simple, non-blocking for SQLite)
    offset = 0
    inserted = 0
    skipped = 0
    errors = 0
    start_time = time.monotonic()

    # Check what's already in PG
    pg_cur = pg_conn.cursor()
    pg_cur.execute("SELECT COUNT(*) FROM foreign_flow")
    existing = pg_cur.fetchone()[0]
    if existing > 0:
        logger.info("PostgreSQL already has %d rows — will upsert (skip existing)", existing)

    # Use server-side cursor for SQLite to avoid loading all into memory
    sqlite_cur = sqlite_conn.execute("""
        SELECT ticker, date, foreign_buy, foreign_sell, foreign_net,
               domestic_buy, domestic_sell, domestic_net, source, created_at
        FROM foreign_flow
        ORDER BY ticker, date
    """)

    batch = []
    while True:
        rows = sqlite_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break

        for row in rows:
            batch.append((
                row["ticker"],
                row["date"],
                float(row["foreign_buy"]) if row["foreign_buy"] is not None else None,
                float(row["foreign_sell"]) if row["foreign_sell"] is not None else None,
                float(row["foreign_net"]) if row["foreign_net"] is not None else None,
                None,  # foreign_volume_buy (not in SQLite)
                None,  # foreign_volume_sell
                float(row["domestic_buy"]) if row["domestic_buy"] is not None else None,
                float(row["domestic_sell"]) if row["domestic_sell"] is not None else None,
                float(row["domestic_net"]) if row["domestic_net"] is not None else None,
                None,  # domestic_volume_buy
                None,  # domestic_volume_sell
                row["source"] or "parquet_archive",
                row["created_at"] or datetime.now(timezone.utc).isoformat(),
            ))

        if len(batch) >= BATCH_SIZE:
            try:
                execute_values(
                    pg_cur,
                    """
                    INSERT INTO foreign_flow (
                        ticker, date, foreign_buy, foreign_sell, foreign_net,
                        foreign_volume_buy, foreign_volume_sell,
                        domestic_buy, domestic_sell, domestic_net,
                        domestic_volume_buy, domestic_volume_sell,
                        source, created_at
                    ) VALUES %s
                    ON CONFLICT (ticker, date, source) DO UPDATE SET
                        foreign_buy = EXCLUDED.foreign_buy,
                        foreign_sell = EXCLUDED.foreign_sell,
                        foreign_net = EXCLUDED.foreign_net,
                        domestic_buy = EXCLUDED.domestic_buy,
                        domestic_sell = EXCLUDED.domestic_sell,
                        domestic_net = EXCLUDED.domestic_net
                    """,
                    batch,
                    page_size=BATCH_SIZE,
                )
                pg_conn.commit()
                inserted += len(batch)
                offset += len(batch)
                if inserted % 50000 == 0:
                    elapsed = time.monotonic() - start_time
                    rate = inserted / elapsed
                    pct = 100 * inserted / total
                    logger.info("Progress: %d/%d (%.1f%%) — %.0f rows/s", inserted, total, pct, rate)
                batch = []
            except Exception as e:
                pg_conn.rollback()
                errors += len(batch)
                logger.warning("Batch error at offset %d: %s — skipping", offset, e)
                batch = []

    # Final batch
    if batch:
        try:
            execute_values(
                pg_cur,
                """
                INSERT INTO foreign_flow (
                    ticker, date, foreign_buy, foreign_sell, foreign_net,
                    foreign_volume_buy, foreign_volume_sell,
                    domestic_buy, domestic_sell, domestic_net,
                    domestic_volume_buy, domestic_volume_sell,
                    source, created_at
                ) VALUES %s
                ON CONFLICT (ticker, date, source) DO UPDATE SET
                    foreign_buy = EXCLUDED.foreign_buy,
                    foreign_sell = EXCLUDED.foreign_sell,
                    foreign_net = EXCLUDED.foreign_net,
                    domestic_buy = EXCLUDED.domestic_buy,
                    domestic_sell = EXCLUDED.domestic_sell,
                    domestic_net = EXCLUDED.domestic_net
                """,
                batch,
                page_size=BATCH_SIZE,
            )
            pg_conn.commit()
            inserted += len(batch)
        except Exception as e:
            pg_conn.rollback()
            errors += len(batch)
            logger.warning("Final batch error: %s", e)

    elapsed = time.monotonic() - start_time
    logger.info("MIGRATION COMPLETE: %d inserted, %d errors, %.1fs", inserted, errors, elapsed)

    # Verify
    pg_cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker), MIN(date), MAX(date) FROM foreign_flow")
    result = pg_cur.fetchone()
    logger.info("PostgreSQL foreign_flow: %d rows, %d tickers, %s to %s", *result)

    pg_cur.close()
    pg_conn.close()
    sqlite_conn.close()


if __name__ == "__main__":
    migrate()
