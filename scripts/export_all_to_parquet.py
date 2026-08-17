"""Export ALL PostgreSQL tables to Parquet files.

Comprehensive export that reads all tables from PostgreSQL and writes them
as Parquet files (snappy compressed) to a target directory.

Large time-series tables are exported as Hive-partitioned directories
(year/month) for efficient querying. Small/reference tables are exported
as single .parquet files.

Usage:
    ENV=paper DATABASE_URL="postgresql://petrick:market_dev@localhost:5432/market" \
    python scripts/export_all_to_parquet.py --output /media/petrick/DATA1/Projects/market/parquet

    # Or with default path from settings:
    python scripts/export_all_to_parquet.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import inspect, text

from market.config import settings
from market.db.engine import get_engine

logger = logging.getLogger(__name__)

# Tables that are partitioned by month (time-series with date/timestamp column)
# Format: (table_name, partition_column)
PARTITIONED_TABLES: list[tuple[str, str]] = [
    ("stock_prices", "timestamp"),
    ("ml_labels", "date"),
    ("daily_risk_metrics", "date"),
    ("technical_indicators_wide", "date"),
    ("foreign_flow", "date"),
    ("daily_trading_stats", "date"),
    ("broker_transactions", "timestamp"),
    ("broker_flow", "date"),
    ("macro_data", "date"),
    ("astronacci_cycles", "cycle_date"),
    ("fear_greed", "date"),
    ("satellite_observations", "date"),
    ("seasonal_patterns", "date"),
    ("market_regimes", "date"),
    ("market_sessions", "session_date"),
    ("corporate_actions", "ex_date"),
    ("dividends", "ex_date"),
    ("fundamental_data", "date"),
    ("technical_indicators", "date"),
    ("pattern_analysis", "date"),
    ("valuation_cache", "date"),
    ("news_sentiment", "date"),
    ("exchange_holidays", "holiday_date"),
    ("earnings_calendar", "date"),
    ("policy_events", "created_at"),
    ("external_events", "created_at"),
    ("audit_log", "created_at"),
    ("render_log", "created_at"),
    ("broker_daily_summary", "date"),
    ("corporate_calendar", "created_at"),
    # Tables with only created_at — export as flat (too small to partition)
    ("recompute_watermark", "last_processed_date"),
    ("causal_relationships", "created_at"),
    ("stock_prediction", "prediction_updated_at"),  # may need fallback
    ("instrument_behavior_profiles", "last_updated"),
    ("cross_market_coefficients", "last_updated"),
    ("trading_style_recommendations", "created_at"),
    ("style_recommendation_reasons", "created_at"),
    ("fundamental_quarterly", "date"),  # may not exist
]

# Tables to skip (internal/bookkeeping)
SKIP_TABLES: frozenset[str] = frozenset({
    "alembic_version",
    "parquet_sync_state",
})

# Columns to drop from export (auto-generated bookkeeping)
DROP_COLS: frozenset[str] = {"id"}


def _get_all_tables(engine) -> list[str]:
    """Get all user table names from PostgreSQL."""
    insp = inspect(engine)
    return sorted(insp.get_table_names())


def _get_date_column(table: str) -> str | None:
    """Check if a table is in the partitioned list."""
    for tname, pcol in PARTITIONED_TABLES:
        if tname == table:
            return pcol
    return None


def _drop_bookkeeping_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Remove auto-generated columns."""
    return df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors="ignore")


def _export_partitioned(engine, table: str, pcol: str, output_dir: Path) -> dict:
    """Export a time-series table as Hive-partitioned parquet files."""
    stats = {"rows": 0, "partitions": 0, "bytes": 0}

    # Check if table has data
    with engine.connect() as conn:
        count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
        if count == 0:
            logger.info("  %-35s empty, skipping", table)
            return stats

        # Check if partition column exists
        cols = [c["name"] for c in inspect(engine).get_columns(table)]
        if pcol not in cols:
            logger.warning("  %-35s column '%s' not found, falling back to flat export", table, pcol)
            return _export_flat(engine, table, output_dir)

        # Get distinct year/month pairs — cast to timestamp first for text columns
        pairs_query = (
            f'SELECT DISTINCT '
            f"EXTRACT(YEAR FROM \"{pcol}\"::timestamp)::INT AS y, "
            f"EXTRACT(MONTH FROM \"{pcol}\"::timestamp)::INT AS m "
            f'FROM "{table}" WHERE "{pcol}" IS NOT NULL ORDER BY y, m'
        )
        pairs = conn.execute(text(pairs_query)).all()

    table_dir = output_dir / table
    table_dir.mkdir(parents=True, exist_ok=True)

    for row in pairs:
        year, month = int(row.y), int(row.m)
        if year is None or month is None:
            continue

        month_query = (
            f'SELECT * FROM "{table}" '
            f"WHERE EXTRACT(YEAR FROM \"{pcol}\"::timestamp) = {year} "
            f"AND EXTRACT(MONTH FROM \"{pcol}\"::timestamp) = {month}"
        )
        df = pd.read_sql_query(month_query, engine)
        if df.empty:
            continue

        df = _drop_bookkeeping_cols(df)

        part_dir = table_dir / f"year={year}" / f"month={month:02d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        out_path = part_dir / "data.parquet"

        table_obj = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_table(table_obj, out_path, compression="snappy")

        size = out_path.stat().st_size
        stats["rows"] += len(df)
        stats["partitions"] += 1
        stats["bytes"] += size
        logger.info("  %-35s y=%d m=%02d : %d rows, %d KB", table, year, month, len(df), size // 1024)

    return stats


def _export_flat(engine, table: str, output_dir: Path) -> dict:
    """Export a table as a single flat parquet file."""
    stats = {"rows": 0, "partitions": 0, "bytes": 0}

    with engine.connect() as conn:
        count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
        if count == 0:
            logger.info("  %-35s empty, skipping", table)
            return stats

    df = pd.read_sql_table(table, engine)
    df = _drop_bookkeeping_cols(df)

    out_path = output_dir / f"{table}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)

    size = out_path.stat().st_size
    stats["rows"] = len(df)
    stats["bytes"] = size
    logger.info("  %-35s : %d rows, %d KB", table, len(df), size // 1024)

    return stats


def export_all(output_dir: Path, dry_run: bool = False) -> dict[str, dict]:
    """Export all PostgreSQL tables to parquet.

    Args:
        output_dir: Target directory for parquet files.
        dry_run: If True, only report what would be exported.

    Returns:
        Dict of table_name -> stats dict.
    """
    engine = get_engine()
    all_tables = _get_all_tables(engine)

    # Filter out skipped tables and partition child tables (they're included in parent)
    tables_to_export = [
        t for t in all_tables
        if t not in SKIP_TABLES
        and not t.startswith("stock_prices_20")  # partition children
    ]

    logger.info("Export target: %s", output_dir)
    logger.info("Tables to export: %d", len(tables_to_export))

    if dry_run:
        for table in tables_to_export:
            pcol = _get_date_column(table)
            mode = "partitioned" if pcol else "flat"
            logger.info("  [DRY RUN] %-35s (%s)", table, mode)
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for table in tables_to_export:
        pcol = _get_date_column(table)
        if pcol:
            results[table] = _export_partitioned(engine, table, pcol, output_dir)
        else:
            results[table] = _export_flat(engine, table, output_dir)

    return results


def print_summary(results: dict[str, dict]) -> None:
    """Print export summary."""
    print(f"\n{'=' * 70}")
    print("PARQUET EXPORT SUMMARY")
    print(f"{'=' * 70}")
    total_rows = 0
    total_bytes = 0
    total_parts = 0
    for table, stats in sorted(results.items()):
        rows = stats.get("rows", 0)
        parts = stats.get("partitions", 0)
        size = stats.get("bytes", 0)
        total_rows += rows
        total_parts += parts
        total_bytes += size
        if parts:
            print(f"  {table:<37} {rows:>10,} rows  {parts:>4} parts  "
                  f"{size // 1024:>10,} KB")
        else:
            print(f"  {table:<37} {rows:>10,} rows  "
                  f"{'-':>4}       {size // 1024:>10,} KB")
    print(f"\n  Total: {total_rows:,} rows, {total_parts} partitions, "
          f"{total_bytes // (1024*1024):,} MB written")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export all PostgreSQL tables to Parquet")
    parser.add_argument("--output", default=None,
                        help="Output directory (default: <parquet_archive>/archive/tables)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path(settings.parquet_archive_path) / "archive" / "tables"

    results = export_all(output_dir, dry_run=args.dry_run)
    if results:
        print_summary(results)


if __name__ == "__main__":
    main()
