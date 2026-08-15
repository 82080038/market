#!/usr/bin/env python3
"""Migrate ticker code across all DB tables when BEI changes a ticker symbol.

BEI plans to allow ticker code changes starting January 2028 (revisi Peraturan I-A).
This script handles:
  1. Update instrument_master: set new ticker, former_ticker, former_name
  2. Migrate all data tables (ohlcv, stock_personality, foreign_flow, etc.)
  3. Verify data integrity after migration

Usage:
    # Dry-run (show what would change, no writes)
    python scripts/migrate_ticker.py --old BNLI.JK --new BBPI.JK --dry-run

    # Actual migration
    python scripts/migrate_ticker.py --old BNLI.JK --new BBPI.JK

    # With reason and effective date
    python scripts/migrate_ticker.py --old BNLI.JK --new BBPI.JK \
        --reason "BEI ticker change Jan 2028" --effective-date 2028-01-02
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Tables with a 'ticker' column that need migration.
# Key = table name, value = whether ticker is part of PRIMARY KEY.
# For PK tables, we use INSERT OR REPLACE + DELETE instead of UPDATE.
TICKER_TABLES: dict[str, bool] = {
    "instrument_master": True,        # PK: ticker
    "stock_personality": True,        # PK: ticker
    "recompute_watermark": True,      # PK: ticker
    "ohlcv": False,                   # FK-like, id is PK
    "technical_indicators": False,    # id is PK
    "ml_labels": False,               # id is PK
    "foreign_flow": False,            # id is PK
    "daily_trading_stats": False,     # id is PK
    "daily_risk_metrics": False,      # id is PK
    "fundamental_data": False,        # id is PK
    "corporate_actions": False,       # id is PK
    "dividends": False,               # id is PK
    "broker_flow": False,             # id is PK
    "pattern_analysis": False,        # id is PK
    "scores": False,                  # id is PK
    "valuation_cache": False,         # id is PK
    "ai_weights": False,              # id is PK
    "trading_suspensions": False,     # id is PK
    "corporate_governance": False,    # id is PK
    "esg_scores": False,             # id is PK
    "data_watermark": False,         # id is PK
    "watchlist": False,              # id is PK
    "orders": False,                 # id is PK
    "positions": False,              # id is PK
    "trade_journal": False,          # id is PK
    "render_log": False,             # id is PK
}


def get_ticker_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Get column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cursor.fetchall()]


def count_ticker_rows(conn: sqlite3.Connection, table: str, ticker: str) -> int:
    """Count rows for a given ticker in a table. Returns 0 if table doesn't exist."""
    try:
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ticker = ?", (ticker,)
        )
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def migrate_ticker(
    conn: sqlite3.Connection,
    old_ticker: str,
    new_ticker: str,
    reason: str = "",
    effective_date: str = "",
    dry_run: bool = False,
) -> dict[str, int]:
    """Migrate a ticker code across all DB tables.

    Args:
        conn: sqlite3.Connection to the database.
        old_ticker: Current ticker (e.g. ``BNLI.JK``).
        new_ticker: New ticker code (e.g. ``BBPI.JK``).
        reason: Reason for the change (stored in delisting_risk_reason).
        effective_date: Effective date of the change (YYYY-MM-DD).
        dry_run: If True, only report what would change.

    Returns:
        Dict mapping table name → number of rows affected.
    """
    stats: dict[str, int] = {}

    # Verify old ticker exists
    row = conn.execute(
        "SELECT ticker, name, former_ticker, former_name FROM instrument_master WHERE ticker = ?",
        (old_ticker,),
    ).fetchone()
    if not row:
        logger.error("Old ticker %s not found in instrument_master", old_ticker)
        return stats

    old_name = row[1]
    old_former_ticker = row[2]
    old_former_name = row[3]

    # Check if new ticker already exists
    existing_new = conn.execute(
        "SELECT ticker FROM instrument_master WHERE ticker = ?", (new_ticker,)
    ).fetchone()
    if existing_new:
        logger.error(
            "New ticker %s already exists in instrument_master — cannot merge", new_ticker
        )
        return stats

    logger.info("=" * 70)
    logger.info("MIGRATION: %s → %s", old_ticker, new_ticker)
    logger.info("  Reason: %s", reason or "BEI ticker change")
    logger.info("  Effective: %s", effective_date or "N/A")
    logger.info("  Mode: %s", "DRY-RUN" if dry_run else "LIVE")
    logger.info("=" * 70)

    # Pre-migration counts
    logger.info("\nPre-migration row counts:")
    for table in TICKER_TABLES:
        count = count_ticker_rows(conn, table, old_ticker)
        if count > 0:
            logger.info("  %-30s %d rows", table, count)
        stats[table] = 0

    if dry_run:
        logger.info("\n[DRY-RUN] No changes applied.")
        return stats

    # ── Step 1: Update instrument_master ──────────────────────────────
    logger.info("\nStep 1: Update instrument_master")

    # Set former_ticker to the old ticker (preserve chain if already has one)
    chain_ticker = old_former_ticker or old_ticker
    chain_name = old_former_name or old_name

    conn.execute(
        """UPDATE instrument_master
           SET ticker = ?,
               former_ticker = ?,
               former_name = ?,
               delisting_risk_reason = ?,
               updated_at = datetime('now')
           WHERE ticker = ?""",
        (
            new_ticker,
            chain_ticker,
            chain_name,
            f"Ticker changed from {old_ticker} to {new_ticker}: {reason}",
            old_ticker,
        ),
    )
    stats["instrument_master"] = 1
    logger.info("  instrument_master: %s → %s (former_ticker=%s)", old_ticker, new_ticker, chain_ticker)

    # ── Step 2: Migrate data tables ───────────────────────────────────
    logger.info("\nStep 2: Migrate data tables")

    for table, is_pk in TICKER_TABLES.items():
        if table == "instrument_master":
            continue  # Already done

        count = count_ticker_rows(conn, table, old_ticker)
        if count == 0:
            continue

        if is_pk:
            # For PK tables (ticker is primary key), use INSERT OR REPLACE + DELETE
            cols = get_ticker_columns(conn, table)
            col_list = ", ".join(cols)
            select_expr = ", ".join(
                f"'{new_ticker}'" if c == "ticker" else c for c in cols
            )
            conn.execute(
                f"""INSERT OR REPLACE INTO {table} ({col_list})
                    SELECT {select_expr} FROM {table} WHERE ticker = ?""",
                (old_ticker,),
            )
            conn.execute(f"DELETE FROM {table} WHERE ticker = ?", (old_ticker,))
        else:
            # Simple UPDATE for non-PK tables
            conn.execute(
                f"UPDATE {table} SET ticker = ? WHERE ticker = ?",
                (new_ticker, old_ticker),
            )

        stats[table] = count
        logger.info("  %-30s %d rows migrated", table, count)

    conn.commit()

    # ── Step 3: Verify ────────────────────────────────────────────────
    logger.info("\nStep 3: Verification")
    old_remaining = 0
    for table in TICKER_TABLES:
        count = count_ticker_rows(conn, table, old_ticker)
        if count > 0:
            logger.warning("  %s: %d rows still have old ticker %s", table, count, old_ticker)
            old_remaining += count

    new_count = count_ticker_rows(conn, "instrument_master", new_ticker)
    if new_count == 1:
        logger.info("  instrument_master: %s exists ✓", new_ticker)
    else:
        logger.error("  instrument_master: %s not found after migration!", new_ticker)

    if old_remaining == 0:
        logger.info("  No stale %s references remaining ✓", old_ticker)
    else:
        logger.warning("  %d stale %s references remain", old_remaining, old_ticker)

    logger.info("\nMigration complete: %s → %s", old_ticker, new_ticker)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate ticker code across all DB tables"
    )
    parser.add_argument(
        "--old", required=True, help="Old ticker (e.g. BNLI.JK)"
    )
    parser.add_argument(
        "--new", required=True, help="New ticker (e.g. BBPI.JK)"
    )
    parser.add_argument(
        "--reason", default="BEI ticker change",
        help="Reason for the change"
    )
    parser.add_argument(
        "--effective-date", default="",
        help="Effective date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without applying"
    )
    parser.add_argument(
        "--db-path", default=None,
        help="Database path (default: env DB_PATH atau settings.db_path)"
    )
    args = parser.parse_args()

    from market.config import settings as _settings
    db_path = Path(args.db_path or os.environ.get("DB_PATH") or _settings.db_path)
    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        migrate_ticker(
            conn,
            old_ticker=args.old,
            new_ticker=args.new,
            reason=args.reason,
            effective_date=args.effective_date,
            dry_run=args.dry_run,
        )
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
