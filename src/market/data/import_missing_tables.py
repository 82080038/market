"""Import 15 missing tables + re-import 4 altered tables from parquet global.

Reads from project global's parquet archive (read-only) at
/media/petrick/Parquet/trading_data/ and imports into market_paper.db.

Tables imported:
  - 15 new tables: news, broker_flow, policy_events, external_events,
    pattern_analysis, trading_suspensions, render_log, valuation_cache,
    positions, orders, equity_snapshots, daily_risk_metrics, trade_journal,
    ai_weights, system_state
  - 4 altered tables (re-import with new columns): instrument_master,
    corporate_actions, fundamental_data, stock_personality

Usage:
    ENV=paper python -m market.data.import_missing_tables
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from market.db.engine import get_sessionmaker

logger = logging.getLogger(__name__)

GLOBAL_ARCHIVE = Path("/media/petrick/Parquet/trading_data/archive/tables")
GLOBAL_SQLITE_BACKUP = Path("/media/petrick/Parquet/trading_data/raw/sqlite_backup")
GLOBAL_SUSP = Path("/media/petrick/Parquet/trading_data/archive/trading_suspensions")


def _find_parquet(name: str) -> Path | None:
    """Find parquet file in archive/tables or sqlite_backup."""
    for base in [GLOBAL_ARCHIVE, GLOBAL_SQLITE_BACKUP]:
        p = base / f"{name}.parquet"
        if p.exists():
            return p
    # Special case: trading_suspensions
    if name == "trading_suspensions":
        files = list(GLOBAL_SUSP.glob("trading_suspensions_*.parquet"))
        if files:
            return files[0]
    return None


def _to_sql_safe(df: pd.DataFrame, table: str, session: Any) -> int:
    """Insert DataFrame into table, handling column mapping."""
    # Drop columns that don't exist in DB schema or are auto-generated
    drop_cols = {"id", "created_at", "updated_at"}
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

    # Rename parquet columns to DB column names where they differ
    rename_maps = {
        "fundamental_data": {
            "pe_ratio": "pe", "pb_ratio": "pb", "earnings_per_share": "eps",
            "debt_to_equity": "der", "net_profit": "net_income",
        },
        "instrument_master": {
            "exchange": "market_mic",
        },
        "stock_personality": {
            "kode": "ticker",
        },
    }
    if table in rename_maps:
        df = df.rename(columns=rename_maps[table])

    # Filter to only columns that exist in DB schema
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(session.bind)
    db_cols = set(c["name"] for c in inspector.get_columns(table))
    df = df[[c for c in df.columns if c in db_cols]]

    # Convert date columns
    for col in df.columns:
        if col in ("date", "tanggal", "ex_date", "record_date", "payment_date",
                    "announce_date", "suspend_date", "resume_date", "entry_date",
                    "exit_date", "profile_date", "listing_date", "delisting_date"):
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        elif col in ("opened_at", "closed_at", "last_rendered"):
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Insert via pandas to_sql with append
    df.to_sql(table, session.bind, if_exists="append", index=False, method="multi")
    return len(df)


def import_table(table: str, session: Any) -> int:
    """Import a single table from parquet."""
    path = _find_parquet(table)
    if path is None:
        logger.warning("  %s: parquet not found, skipping", table)
        return 0

    df = pd.read_parquet(path)
    if df.empty:
        logger.warning("  %s: empty parquet, skipping", table)
        return 0

    # Clear existing data (for re-import of altered tables)
    session.execute(text(f"DELETE FROM {table}"))
    session.commit()

    # Deduplicate on unique constraints per table
    dedup_keys = {
        "pattern_analysis": ["ticker", "date", "pattern_type"],
        "news": ["news_id"],
        "broker_flow": ["ticker", "date", "broker", "source"],
        "render_log": ["ticker", "table_name"],
        "valuation_cache": ["ticker", "date", "method", "source"],
        "system_state": ["key"],
        "instrument_master": ["ticker"],
        "corporate_actions": ["ticker", "action_type", "ex_date"],
        "fundamental_data": ["ticker", "date", "source"],
        "stock_personality": ["kode"],
    }
    if table in dedup_keys:
        keys = dedup_keys[table]
        before = len(df)
        df = df.drop_duplicates(subset=keys, keep="last")
        if before != len(df):
            logger.info("  %s: deduped %d -> %d rows", table, before, len(df))

    count = _to_sql_safe(df, table, session)
    session.commit()
    logger.info("  %s: %d rows imported from %s", table, count, path.name)
    return count


def import_all() -> dict[str, int]:
    """Import all missing + altered tables."""
    sessionmaker = get_sessionmaker()
    session = sessionmaker()
    results: dict[str, int] = {}

    # Disable FK checks during bulk import (re-enable after)
    session.execute(text("PRAGMA foreign_keys=OFF"))

    # 15 new tables
    new_tables = [
        "news", "broker_flow", "policy_events", "external_events",
        "pattern_analysis", "trading_suspensions", "render_log",
        "valuation_cache", "positions", "orders", "equity_snapshots",
        "daily_risk_metrics", "trade_journal", "ai_weights", "system_state",
    ]

    # 4 altered tables (re-import with new columns)
    altered_tables = [
        "instrument_master", "corporate_actions",
        "fundamental_data", "stock_personality",
    ]

    try:
        logger.info("=== Importing 15 new tables ===")
        for t in new_tables:
            results[t] = import_table(t, session)

        logger.info("=== Re-importing 4 altered tables ===")
        for t in altered_tables:
            results[t] = import_table(t, session)
    finally:
        session.execute(text("PRAGMA foreign_keys=ON"))
        session.close()

    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    results = import_all()

    logger.info("=" * 60)
    logger.info("Import summary:")
    total = 0
    for table, count in results.items():
        logger.info("  %s: %s", table, f"{count:,}")
        total += count
    logger.info("  TOTAL: %s", f"{total:,}")
