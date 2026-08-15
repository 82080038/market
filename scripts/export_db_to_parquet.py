"""Export all database tables to fresh Parquet files in E:\\pustaka_data\\archive\\tables\\.

Reads from the application SQLite database (source of truth) and writes
clean Parquet files, replacing the old parquet data that was deleted.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from market.config import settings as _settings
DB_PATH = _settings.db_path
EXPORT_BASE = Path("E:/pustaka_data/archive/tables")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get all user tables
    c.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%' "
        "ORDER BY name"
    )
    tables = [r[0] for r in c.fetchall()]
    logger.info("Found %d tables to export", len(tables))

    # Create export directory
    EXPORT_BASE.mkdir(parents=True, exist_ok=True)
    logger.info("Export directory: %s", EXPORT_BASE)

    results: dict[str, int] = {}
    for table in tables:
        try:
            df = pd.read_sql_query(f"SELECT * FROM [{table}]", conn)

            # Write to parquet
            out_path = EXPORT_BASE / f"{table}.parquet"
            df.to_parquet(out_path, index=False, engine="pyarrow")

            results[table] = len(df)
            logger.info("  %-35s %d rows -> %s", table, len(df), out_path.name)
        except Exception as exc:
            logger.error("  %-35s FAILED: %s", table, exc)
            results[table] = -1

    conn.close()

    # Summary
    print(f"\n{'=' * 60}")
    print("EXPORT SUMMARY")
    print(f"{'=' * 60}")
    total_rows = 0
    for table, count in results.items():
        status = f"{count:,} rows" if count >= 0 else "FAILED"
        print(f"  {table:<35} {status}")
        if count > 0:
            total_rows += count

    success = sum(1 for v in results.values() if v >= 0)
    failed = sum(1 for v in results.values() if v < 0)
    print(f"\n  Total: {success} OK, {failed} FAILED, {total_rows:,} rows exported")
    print(f"  Output: {EXPORT_BASE}")


if __name__ == "__main__":
    main()
