"""Export cleaned data from market_paper.db to parquet archive.

Creates a portable parquet backup of all database tables at the configured
parquet archive path (OS-aware default: Linux /media/petrick/Parquet/pustaka_data/,
Windows E:/pustaka_data/).

This is the inverse of migrate_parquet.py: it writes the application's own
cleaned data to parquet so the data can be carried to another machine and
used to bootstrap a fresh database via migrate_parquet.py.

Usage:
    ENV=paper python -m market.data.export_to_parquet [--dry-run]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import text

from market.config import settings
from market.db.engine import get_sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Export target: <parquet_root>/archive/tables/
EXPORT_DIR = Path(settings.parquet_archive_path) / "archive" / "tables"

# Tables to export with their column selection / transformation
# Format: (table_name, output_filename, optional_column_rename_map)
TABLES_TO_EXPORT: list[tuple[str, str, dict[str, str] | None]] = [
    ("ohlcv", "ohlcv.parquet", None),
    ("instrument_master", "instrument_master.parquet", None),
    ("market_registry", "market_registry.parquet", None),
    ("market_calendar", "market_calendar.parquet", None),
    ("sector_master", "sector_master.parquet", None),
    ("corporate_actions", "corporate_actions.parquet", None),
    ("dividends", "dividends.parquet", None),
    ("fundamental_data", "fundamental_data.parquet", {
        # DB columns → parquet-friendly names (matches global schema)
        "pe": "pe_ratio",
        "pb": "pb_ratio",
        "der": "debt_to_equity",
        "eps": "earnings_per_share",
        "net_income": "net_profit",
    }),
    ("macro_data", "macro_data.parquet", None),
    ("foreign_flow", "foreign_flow.parquet", None),
    ("fx_rates", "fx_rates.parquet", None),
    ("technical_indicators", "technical_indicators.parquet", None),
    ("scores", "scores.parquet", None),
    ("relationship_matrix", "relationship_matrix.parquet", None),
    ("stock_personality", "stock_personality.parquet", None),
    ("fear_greed", "fear_greed.parquet", None),
    ("esg_scores", "esg_scores.parquet", None),
    ("corporate_governance", "corporate_governance.parquet", None),
    ("source_health", "source_health.parquet", None),
    ("data_watermark", "data_watermark.parquet", None),
    # Tables added in migration 0003
    ("news", "news.parquet", None),
    ("broker_flow", "broker_flow.parquet", None),
    ("policy_events", "policy_events.parquet", None),
    ("external_events", "external_events.parquet", None),
    ("pattern_analysis", "pattern_analysis.parquet", None),
    ("trading_suspensions", "trading_suspensions.parquet", None),
    ("render_log", "render_log.parquet", None),
    ("valuation_cache", "valuation_cache.parquet", None),
    ("positions", "positions.parquet", None),
    ("orders", "orders.parquet", None),
    ("equity_snapshots", "equity_snapshots.parquet", None),
    ("daily_risk_metrics", "daily_risk_metrics.parquet", None),
    ("trade_journal", "trade_journal.parquet", None),
    ("ai_weights", "ai_weights.parquet", None),
    ("system_state", "system_state.parquet", None),
]


def export_table(
    session: Session,
    table_name: str,
    filename: str,
    rename_map: dict[str, str] | None = None,
    dry_run: bool = False,
) -> int:
    """Export a single table to parquet. Returns row count."""
    # Read all rows via pandas for efficient parquet writing
    df = pd.read_sql_table(table_name, session.bind)

    if df.empty:
        logger.warning("Table %s is empty, skipping", table_name)
        return 0

    # Drop auto-generated columns that shouldn't be in archive
    drop_cols = {"id", "created_at", "updated_at"}
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

    # Rename columns if needed
    if rename_map:
        df = df.rename(columns=rename_map)

    if dry_run:
        logger.info("[DRY RUN] %s → %s: %d rows, %d cols",
                    table_name, filename, len(df), len(df.columns))
        return len(df)

    out_path = EXPORT_DIR / filename
    # Use snappy compression for smaller files (pyarrow engine)
    df.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)
    size_kb = out_path.stat().st_size // 1024
    logger.info("Exported %s → %s: %d rows, %d KB", table_name, filename,
                len(df), size_kb)
    return len(df)


def export_all(dry_run: bool = False) -> dict[str, int]:
    """Export all tables to parquet. Returns {table_name: row_count}."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    sessionmaker = get_sessionmaker()
    session = sessionmaker()
    results: dict[str, int] = {}

    try:
        for table_name, filename, rename_map in TABLES_TO_EXPORT:
            count = export_table(
                session, table_name, filename, rename_map, dry_run=dry_run
            )
            results[table_name] = count
    finally:
        session.close()

    return results


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="Export DB to parquet archive")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    args = parser.parse_args()

    logger.info("Export target: %s", EXPORT_DIR)
    results = export_all(dry_run=args.dry_run)

    logger.info("=" * 60)
    logger.info("Export summary:")
    total = 0
    for table, count in results.items():
        logger.info("  %s: %s", table, f"{count:,}")
        total += count
    logger.info("  TOTAL: %s", f"{total:,}")
