"""Backfill avg_volume di stock_personality dari OHLCV.

Kolom avg_volume saat ini 100% NULL. Script ini menghitung
AVG(volume) per ticker dari tabel ohlcv dan UPDATE stock_personality.

Usage:
  DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market uv run python scripts/backfill_avg_volume.py
  DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market uv run python scripts/backfill_avg_volume.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os

from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_db_path() -> str:
    from market.config import settings as _settings
    return os.environ.get("DB_PATH") or _settings.db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill avg_volume in stock_personality from OHLCV")
    parser.add_argument("--dry-run", action="store_true", help="Only show stats, no updates")
    args = parser.parse_args()

    db_path = get_db_path()
    logger.info("Database: %s", db_path)
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    with engine.connect() as conn:
        total_sp = conn.execute(text("SELECT COUNT(*) FROM stock_personality")).scalar()
        null_avg_vol = conn.execute(text(
            "SELECT COUNT(*) FROM stock_personality WHERE avg_volume IS NULL"
        )).scalar()

    logger.info("stock_personality rows: %d", total_sp)
    logger.info("NULL avg_volume: %d (%.1f%%)", null_avg_vol, 100 * null_avg_vol / max(1, total_sp))

    if args.dry_run:
        logger.info("Dry run — no updates performed")
        return

    if null_avg_vol == 0:
        logger.info("All avg_volume already populated — nothing to do")
        return

    # Compute AVG(volume) per ticker from ohlcv and update stock_personality
    logger.info("Computing AVG(volume) per ticker from ohlcv...")
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE stock_personality "
            "SET avg_volume = ("
            "  SELECT AVG(volume) FROM ohlcv WHERE ohlcv.ticker = stock_personality.ticker"
            ") "
            "WHERE avg_volume IS NULL "
            "AND EXISTS ("
            "  SELECT 1 FROM ohlcv WHERE ohlcv.ticker = stock_personality.ticker"
            ")"
        ))
        updated = result.rowcount

    logger.info("Updated %d rows in stock_personality", updated)

    # Verify
    with engine.connect() as conn:
        null_after = conn.execute(text(
            "SELECT COUNT(*) FROM stock_personality WHERE avg_volume IS NULL"
        )).scalar()
    logger.info("NULL avg_volume after backfill: %d", null_after)

    # Show sample
    with engine.connect() as conn:
        sample = conn.execute(text(
            "SELECT ticker, avg_volume FROM stock_personality "
            "WHERE avg_volume IS NOT NULL LIMIT 5"
        )).fetchall()
    for ticker, avg_vol in sample:
        logger.info("  %s: avg_volume = %.2f", ticker, float(avg_vol))


if __name__ == "__main__":
    main()
