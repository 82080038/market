"""Consolidate and drop 6+2 redundant tables.

Data already migrated to main tables:
  emiten       → instrument_master (0 missing)
  instrumen    → instrument_master (asset_class already present)
  sektor       → sector_master (10 sectors)
  bursa_efek   → market_registry (11 MICs, 1:1 mapping)
  indeks_pasar → instrument_master (0 missing, 57 index tickers)
  fx_rates     → ohlcv IDR=X (1318 rows; 60 extra dates to migrate)
  regulator    → only referenced by bursa_efek (drop together)
  transaksi_investor → 0 rows, FK to instrumen (drop, no IDX API)

Also recreates broker_bursa without FK to bursa_efek (keeps data).

Usage:
  DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market uv run python scripts/consolidate_redundant_tables.py
  DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market uv run python scripts/consolidate_redundant_tables.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DROP_TABLES = [
    "transaksi_investor",
    "instrumen",
    "emiten",
    "indeks_pasar",
    "broker_bursa",
    "bursa_efek",
    "sektor",
    "regulator",
    "fx_rates",
]


def get_db_path() -> str:
    from market.config import settings as _settings
    return os.environ.get("DB_PATH") or _settings.db_path


def migrate_fx_rates(conn: sqlite3.Connection) -> int:
    """Migrate fx_rates dates not yet in ohlcv (IDR=X)."""
    fx_rows = conn.execute(
        "SELECT date, rate, source FROM fx_rates "
        "WHERE date NOT IN (SELECT DISTINCT date(timestamp) FROM ohlcv WHERE ticker='IDR=X') "
        "ORDER BY date"
    ).fetchall()

    count = 0
    for date_str, rate, source in fx_rows:
        conn.execute(
            "INSERT OR REPLACE INTO ohlcv "
            "(ticker, timestamp, timeframe, open, high, low, close, volume, adjusted_close, data_quality_score, source) "
            "VALUES (?, ?, '1d', ?, ?, ?, ?, 0, ?, 100, ?)",
            ("IDR=X", date_str, rate, rate, rate, rate, rate, source or "yahoo_finance"),
        )
        count += 1
    conn.commit()
    logger.info("fx_rates → ohlcv: migrated %d missing dates", count)
    return count


def backup_broker_bursa(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """Save broker_bursa data before dropping."""
    rows = conn.execute("SELECT id_broker, id_bursa FROM broker_bursa").fetchall()
    logger.info("broker_bursa: backed up %d rows", len(rows))
    return rows


def drop_redundant_tables(conn: sqlite3.Connection) -> int:
    """Drop redundant tables with FK enforcement off."""
    conn.execute("PRAGMA foreign_keys = OFF")
    count = 0
    for table in DROP_TABLES:
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            count += 1
            logger.info("  Dropped table: %s", table)
        except Exception as e:
            logger.warning("  Failed to drop %s: %s", table, e)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    return count


def recreate_broker_bursa(conn: sqlite3.Connection, data: list[tuple[int, int]]) -> int:
    """Recreate broker_bursa without FK to bursa_efek."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS broker_bursa ("
        "id_broker INTEGER NOT NULL, "
        "id_bursa INTEGER NOT NULL, "
        "PRIMARY KEY (id_broker, id_bursa)"
        ")"
    )
    for id_broker, id_bursa in data:
        conn.execute(
            "INSERT OR REPLACE INTO broker_bursa (id_broker, id_bursa) VALUES (?, ?)",
            (id_broker, id_bursa),
        )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    logger.info("broker_bursa: recreated with %d rows (no FK)", len(data))
    return len(data)


def verify(conn: sqlite3.Connection) -> None:
    """Verify tables are gone and kept tables intact."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("VERIFICATION")
    logger.info("=" * 60)

    for table in DROP_TABLES:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        status = "STILL EXISTS" if exists else "DROPPED"
        logger.info("  %-25s %s", table, status)

    kept = ["broker", "broker_bursa", "instrument_master", "sector_master", "market_registry", "ohlcv"]
    for table in kept:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            logger.info("  %-25s %d rows  [KEPT]", table, cnt)
        except Exception:
            logger.info("  %-25s ERROR  [KEPT]", table)

    idr_x = conn.execute(
        "SELECT COUNT(*) FROM ohlcv WHERE ticker='IDR=X'"
    ).fetchone()[0]
    logger.info("  ohlcv IDR=X:              %d rows", idr_x)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate and drop redundant tables")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done, no changes")
    args = parser.parse_args()

    db_path = get_db_path()
    logger.info("Database: %s", db_path)

    conn = sqlite3.connect(db_path)
    try:
        logger.info("")
        logger.info("Step 1: Migrate fx_rates → ohlcv (missing dates)")
        if not args.dry_run:
            migrated = migrate_fx_rates(conn)
        else:
            fx_count = conn.execute(
                "SELECT COUNT(*) FROM fx_rates "
                "WHERE date NOT IN (SELECT DISTINCT date(timestamp) FROM ohlcv WHERE ticker='IDR=X')"
            ).fetchone()[0]
            logger.info("  [DRY RUN] Would migrate %d dates", fx_count)

        logger.info("")
        logger.info("Step 2: Backup broker_bursa")
        bb_data = backup_broker_bursa(conn)

        logger.info("")
        logger.info("Step 3: Drop %d redundant tables", len(DROP_TABLES))
        if not args.dry_run:
            dropped = drop_redundant_tables(conn)
            logger.info("  Dropped %d tables", dropped)
        else:
            for t in DROP_TABLES:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                logger.info("  [DRY RUN] Would drop %s (%d rows)", t, cnt)

        logger.info("")
        logger.info("Step 4: Recreate broker_bursa (no FK)")
        if not args.dry_run:
            recreate_broker_bursa(conn, bb_data)

        if not args.dry_run:
            verify(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
