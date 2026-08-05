"""Parquet database seeder — portable schema-validated data import.

Allows contributors to seed their local database from Parquet files.
Copy Parquet files into data/parquet_seeds/ and run this script.

Usage:
    uv run python scripts/seed_from_parquet.py                # Seed all
    uv run python scripts/seed_from_parquet.py --table ohlcv  # Seed specific table
    uv run python scripts/seed_from_parquet.py --export       # Export DB to Parquet
    uv run python scripts/seed_from_parquet.py --validate     # Validate only

Schema validation ensures external Parquet files are compatible
with the Gigantic AI database schema before importing.

References: pustaka/18 §13, pustaka/90.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from market.db.engine import get_sessionmaker
from market.db.models import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Seed directory: external Parquet data source
# Contributors copy Parquet files here (or point --seed-dir to their path)
# Default: /media/petrick/Parquet/pustaka_data/archive/tables/
SEED_DIR = Path("/media/petrick/Parquet/pustaka_data/archive/tables")

# Export directory: for exporting existing DB to Parquet
EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "parquet_export"

# Tables that can be seeded (exclude alembic_version, system_state)
SEEDABLE_TABLES = [
    "ohlcv",
    "instrument_master",
    "fundamental_data",
    "corporate_actions",
    "dividends",
    "foreign_flow",
    "macro_data",
    "market_registry",
    "market_calendar",
    "news",
    "scores",
    "technical_indicators",
    "relationship_matrix",
    "fear_greed",
    "pattern_analysis",
    "stock_personality",
    "sector_master",
    "watchlist",
    "broker_flow",
    "fx_rates",
    "external_events",
    "policy_events",
    "esg_scores",
    "corporate_governance",
    "valuation_cache",
    "trading_suspensions",
    "data_watermark",
    "source_health",
]

# Required columns per table (subset for validation)
REQUIRED_COLUMNS: dict[str, list[str]] = {
    "ohlcv": ["ticker", "timestamp", "timeframe", "open", "high", "low", "close", "volume"],
    "instrument_master": ["ticker", "market_mic", "asset_class", "name"],
    "fundamental_data": ["ticker", "date", "pe", "pb", "roe"],
    "corporate_actions": ["ticker", "action_type", "ex_date"],
    "dividends": ["ticker", "ex_date", "amount"],
    "foreign_flow": ["ticker", "date", "foreign_buy", "foreign_sell"],
    "macro_data": ["series_name", "date", "value"],
    "market_registry": ["mic_code", "country_code", "timezone", "trading_hours"],
    "news": ["headline", "published_at"],
    "scores": ["ticker", "engine", "score", "as_of"],
    "technical_indicators": ["ticker", "date", "indicator", "value"],
    "fear_greed": ["tanggal", "nilai"],
}

# Column name mapping: Parquet column → DB column
# Handles schema differences between external Parquet and DB
COLUMN_MAPPING: dict[str, dict[str, str]] = {
    "fundamental_data": {
        "pe_ratio": "pe",
        "pb_ratio": "pb",
        "debt_to_equity": "der",
        "earnings_per_share": "eps",
        "net_profit": "net_income",
    },
}


def get_table_columns(session: Session, table_name: str) -> list[str]:
    """Get column names for a table from the database schema."""
    insp = inspect(session.bind)
    columns = insp.get_columns(table_name)
    return [c["name"] for c in columns]


def validate_parquet_schema(
    parquet_path: Path, table_name: str, db_columns: list[str],
) -> tuple[bool, list[str]]:
    """Validate Parquet file schema against database table.

    Checks:
    1. Required columns exist in Parquet file
    2. All Parquet columns exist in DB schema (extra columns will be skipped)

    Args:
        parquet_path: Path to Parquet file.
        table_name: Target database table name.
        db_columns: List of DB column names.

    Returns:
        Tuple of (is_valid, error_messages).
    """
    errors: list[str] = []

    if not parquet_path.exists():
        errors.append(f"File not found: {parquet_path}")
        return False, errors

    try:
        schema = pq.read_schema(parquet_path)
    except Exception as e:
        errors.append(f"Cannot read Parquet schema: {e}")
        return False, errors

    # Apply column mapping for this table
    mapping = COLUMN_MAPPING.get(table_name, {})
    parquet_cols = set()
    for name in schema.names:
        parquet_cols.add(mapping.get(name, name))

    # Check required columns
    required = REQUIRED_COLUMNS.get(table_name, [])
    for col in required:
        if col not in parquet_cols:
            errors.append(
                f"Missing required column '{col}' for table '{table_name}'"
            )

    # Check for columns in Parquet that don't exist in DB
    extra_cols = parquet_cols - set(db_columns)
    if extra_cols:
        logger.warning(
            "Table %s: Parquet has extra columns (will be skipped): %s",
            table_name, ", ".join(sorted(extra_cols)),
        )

    return len(errors) == 0, errors


def seed_table(
    session: Session,
    table_name: str,
    parquet_path: Path,
    batch_size: int = 5000,
) -> int:
    """Seed a database table from a Parquet file.

    Uses INSERT OR REPLACE for upsert behavior (SQLite).
    Only inserts columns that exist in both Parquet and DB schema.

    Args:
        session: SQLAlchemy session.
        table_name: Target table name.
        parquet_path: Path to Parquet file.
        batch_size: Rows per batch insert.

    Returns:
        Number of rows inserted.
    """
    db_columns = get_table_columns(session, table_name)
    is_valid, errors = validate_parquet_schema(parquet_path, table_name, db_columns)

    if not is_valid:
        for e in errors:
            logger.error(e)
        return 0

    # Read Parquet table
    table = pq.read_table(parquet_path)

    # Apply column mapping
    mapping = COLUMN_MAPPING.get(table_name, {})
    if mapping:
        renamed = {k: v for k, v in mapping.items() if k in table.schema.names}
        if renamed:
            table = table.rename_columns([
                renamed.get(c, c) for c in table.schema.names
            ])
            logger.info("  Renamed columns: %s", renamed)

    parquet_cols = [c for c in table.schema.names if c in db_columns]

    if not parquet_cols:
        logger.error("No matching columns between Parquet and DB for %s", table_name)
        return 0

    # Convert to rows
    df = table.to_pandas()
    total_rows = len(df)
    inserted = 0

    logger.info(
        "Seeding %s from %s (%d rows, %d columns)",
        table_name, parquet_path.name, total_rows, len(parquet_cols),
    )

    # Get DB table object
    db_table = Base.metadata.tables.get(table_name)
    if db_table is None:
        logger.error("Table %s not found in Base.metadata", table_name)
        return 0

    # Clear existing data
    session.execute(text(f"DELETE FROM {table_name}"))
    session.commit()

    # Insert in batches
    for i in range(0, total_rows, batch_size):
        batch = df.iloc[i:i + batch_size]
        records = []
        for _, row in batch.iterrows():
            record = {}
            for col in parquet_cols:
                val = row[col]
                # Convert NaN to None
                if hasattr(val, "item"):
                    val = val.item()
                if val != val:  # NaN check
                    val = None
                record[col] = val
            records.append(record)

        if records:
            session.bulk_insert_mappings(db_table, records)
            session.commit()
            inserted += len(records)

            if inserted % (batch_size * 10) == 0:
                logger.info(
                    "  %s: %d/%d rows inserted",
                    table_name, inserted, total_rows,
                )

    logger.info("  %s: %d rows inserted (done)", table_name, inserted)
    return inserted


def export_table_to_parquet(
    session: Session, table_name: str, output_dir: Path,
) -> int:
    """Export a database table to Parquet format.

    Args:
        session: SQLAlchemy session.
        table_name: Source table name.
        output_dir: Directory to write Parquet file.

    Returns:
        Number of rows exported.
    """
    import pandas as pd

    result = session.execute(text(f"SELECT * FROM {table_name}"))
    rows = result.fetchall()

    if not rows:
        logger.info("  %s: 0 rows (skipped)", table_name)
        return 0

    columns = list(result.keys())
    df = pd.DataFrame(rows, columns=columns)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{table_name}.parquet"
    df.to_parquet(output_path, index=False)

    logger.info("  %s: %d rows → %s", table_name, len(df), output_path.name)
    return len(df)


def main() -> int:
    """Main entry point for Parquet seeder."""
    parser = argparse.ArgumentParser(
        description="Seed database from Parquet files or export to Parquet.",
    )
    parser.add_argument(
        "--table", type=str, default=None,
        help="Specific table to seed (default: all in parquet_seeds/)",
    )
    parser.add_argument(
        "--export", action="store_true",
        help="Export database tables to Parquet files",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Validate Parquet files without importing",
    )
    parser.add_argument(
        "--seed-dir", type=Path, default=SEED_DIR,
        help=f"Directory containing Parquet seed files (default: {SEED_DIR})",
    )
    parser.add_argument(
        "--export-dir", type=Path, default=EXPORT_DIR,
        help=f"Directory for Parquet export output (default: {EXPORT_DIR})",
    )
    args = parser.parse_args()

    session = get_sessionmaker()()

    try:
        if args.export:
            # Export mode
            logger.info("=" * 60)
            logger.info("EXPORT DATABASE TO PARQUET")
            logger.info("Output: %s", args.export_dir)
            logger.info("=" * 60)

            tables = args.table if args.table else SEEDABLE_TABLES
            if isinstance(tables, str):
                tables = [tables]

            total = 0
            for t in tables:
                count = export_table_to_parquet(session, t, args.export_dir)
                total += count

            logger.info("=" * 60)
            logger.info("Export complete: %d total rows", total)
            return 0

        # Seed mode
        logger.info("=" * 60)
        logger.info("SEED DATABASE FROM PARQUET")
        logger.info("Seed directory: %s", args.seed_dir)
        logger.info("=" * 60)

        if not args.seed_dir.exists():
            logger.error(
                "Seed directory not found: %s", args.seed_dir
            )
            logger.info(
                "\nTo use the seeder:\n"
                "1. Create the directory: mkdir -p data/parquet_seeds\n"
                "2. Copy Parquet files there (named <table_name>.parquet)\n"
                "3. Run: uv run python scripts/seed_from_parquet.py\n"
            )
            return 1

        # Find Parquet files
        if args.table:
            parquet_files = list(args.seed_dir.glob(f"{args.table}.parquet"))
        else:
            parquet_files = sorted(args.seed_dir.glob("*.parquet"))

        if not parquet_files:
            logger.error("No Parquet files found in %s", args.seed_dir)
            return 1

        logger.info("Found %d Parquet files", len(parquet_files))

        total_inserted = 0
        for pq_file in parquet_files:
            table_name = pq_file.stem  # filename without .parquet

            if table_name not in SEEDABLE_TABLES:
                logger.warning("Skipping %s: not a seedable table", table_name)
                continue

            if args.validate:
                # Validate only
                db_cols = get_table_columns(session, table_name)
                is_valid, errors = validate_parquet_schema(
                    pq_file, table_name, db_cols,
                )
                if is_valid:
                    logger.info("  ✓ %s: schema valid", table_name)
                else:
                    logger.error("  ✗ %s: schema invalid", table_name)
                    for e in errors:
                        logger.error("    %s", e)
                continue

            count = seed_table(session, table_name, pq_file)
            total_inserted += count

        logger.info("=" * 60)
        if args.validate:
            logger.info("Validation complete")
        else:
            logger.info("Seeding complete: %d total rows inserted", total_inserted)
        logger.info("=" * 60)

        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
