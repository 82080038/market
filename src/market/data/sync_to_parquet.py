"""Incremental sync from application SQLite DB to Parquet archive.

Hybrid strategy (pustaka/94-sync-db-to-parquet.md):

- **Partitioned time-series tables** → Hive-partitioned Parquet by
  ``year``/``month`` derived from each table's natural date column.
  Only partitions within a rolling safety window after
  ``last_synced_date`` are rewritten; older partitions are left
  untouched. This avoids rewriting 3M+ rows of ``ohlcv`` every run and
  is friendly to the flashdisk write-endurance constraint
  (AGENTS.md §7 — Windows parquet base is ``E:\\``).
- **Reference tables** (small, mutable) → full rewrite with snappy
  compression. Cheap and simple.
- **Runtime tables** (orders, positions, ...) → skipped when empty;
  full rewrite when non-empty (they are tiny).
- ``parquet_sync_state`` itself is never synced (self-reference).

Sync state is persisted in the ``parquet_sync_state`` table
(migration 0008) so subsequent runs resume incrementally.

Usage:
    ENV=research python -m market.data.sync_to_parquet [--dry-run] \\
        [--table ohlcv] [--full-rewrite] [--safety-days 7]

Cross-platform: output path comes from ``settings.parquet_archive_path``
(AGENTS.md §7). On Linux this is ``/media/petrick/Parquet/pustaka_data``,
on Windows ``E:/pustaka_data``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import inspect, select, text

from market.config import settings
from market.db.engine import get_sessionmaker
from market.db.models import ParquetSyncState

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Output root: <parquet_archive>/archive/tables/  (matches export_to_parquet.py)
EXPORT_DIR = Path(settings.parquet_archive_path) / "archive" / "tables"

# ── Table classification ─────────────────────────────────────────────────

# Time-series tables: (table_name, partition_col, optional_rename_map)
# partition_col is the SQL column used to derive year/month Hive partitions.
PARTITIONED_TABLES: list[tuple[str, str, dict[str, str] | None]] = [
    ("ohlcv", "timestamp", None),
    ("corporate_actions", "ex_date", None),
    ("dividends", "ex_date", None),
    ("market_calendar", "date", None),
    ("fx_rates", "date", None),
    ("fundamental_data", "date", {
        # DB columns → parquet-friendly names (matches export_to_parquet.py)
        "pe": "pe_ratio",
        "pb": "pb_ratio",
        "der": "debt_to_equity",
        "eps": "earnings_per_share",
        "net_income": "net_profit",
    }),
    ("macro_data", "date", None),
    ("foreign_flow", "date", None),
    ("daily_trading_stats", "date", None),
    ("technical_indicators", "date", None),
    ("broker_flow", "date", None),
    ("pattern_analysis", "date", None),
    ("valuation_cache", "date", None),
    ("ml_labels", "date", None),
    ("market_regimes", "date", None),
    ("policy_events", "tanggal", None),
    ("external_events", "tanggal", None),
    ("fear_greed", "tanggal", None),
    # audit_log uses created_at as its time axis; do NOT drop it.
    ("audit_log", "created_at", None),
]

# Reference tables: small and/or mutable — full rewrite each run.
# (table_name, optional_rename_map)
REFERENCE_TABLES: list[tuple[str, dict[str, str] | None]] = [
    ("market_registry", None),
    ("instrument_master", None),
    ("sector_master", None),
    ("scores", None),
    ("relationship_matrix", None),
    ("stock_personality", None),
    ("esg_scores", None),
    ("corporate_governance", None),
    ("source_health", None),
    ("news", None),
    ("trading_suspensions", None),
    ("data_watermark", None),
]

# Runtime tables: skipped when empty, full rewrite when non-empty.
# (table_name, optional_rename_map)
RUNTIME_TABLES: list[tuple[str, dict[str, str] | None]] = [
    ("positions", None),
    ("orders", None),
    ("equity_snapshots", None),
    ("daily_risk_metrics", None),
    ("trade_journal", None),
    ("ai_weights", None),
    ("render_log", None),
    ("watchlist", None),
    ("system_state", None),
    ("scheduler_state", None),
]

# Tables that must never be synced.
SKIP_TABLES: frozenset[str] = frozenset({"parquet_sync_state", "alembic_version"})

# Columns dropped from every exported table (auto-generated bookkeeping).
DROP_COLS: frozenset[str] = {"id", "updated_at"}
# audit_log keeps created_at (it is the event time, not bookkeeping).
# Other tables drop created_at too.
DROP_COLS_DEFAULT: frozenset[str] = DROP_COLS | {"created_at"}

# Default safety window: re-write partitions whose date is within this many
# days AFTER last_synced_date, to catch late-arriving corrections/inserts.
DEFAULT_SAFETY_DAYS = 7


# ── Helpers ──────────────────────────────────────────────────────────────


def _drop_bookkeeping_cols(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Remove auto-generated columns. audit_log keeps created_at."""
    cols = DROP_COLS_DEFAULT if table != "audit_log" else DROP_COLS
    return df.drop(columns=[c for c in cols if c in df.columns], errors="ignore")


def _apply_rename(df: pd.DataFrame, rename_map: dict[str, str] | None) -> pd.DataFrame:
    if rename_map:
        return df.rename(columns=rename_map)
    return df


def _table_row_count(session: Session, table: str) -> int:
    return int(session.execute(text(f"SELECT COUNT(*) FROM [{table}]")).scalar() or 0)


def _max_partition_value(session: Session, table: str, col: str) -> date | None:
    """Return MAX(partition_col) as a python date, or None if table empty."""
    row = session.execute(text(f"SELECT MAX([{col}]) FROM [{table}]")).scalar()
    if row is None:
        return None
    if isinstance(row, datetime):
        return row.date()
    if isinstance(row, date):
        return row
    # pandas/SQLite may return a string
    return pd.Timestamp(row).date()


def _get_sync_state(session: Session, table: str) -> ParquetSyncState | None:
    try:
        return session.execute(
            select(ParquetSyncState).where(ParquetSyncState.table_name == table)
        ).scalar_one_or_none()
    except Exception as exc:
        # parquet_sync_state table may not exist yet (migration 0008 not run).
        # Log once and treat as no prior state.
        logger.debug("parquet_sync_state unavailable (%s) — treating as initial sync", exc)
        return None


def _upsert_sync_state(
    session: Session,
    table: str,
    sync_mode: str,
    partition_col: str | None,
    last_synced_date: date | None,
    row_count: int,
    partitions_written: int,
) -> None:
    try:
        state = _get_sync_state(session, table)
    except Exception:
        return
    now = datetime.now(timezone.utc)
    try:
        if state is None:
            state = ParquetSyncState(
                table_name=table,
                sync_mode=sync_mode,
                partition_col=partition_col,
                last_synced_date=last_synced_date,
                last_synced_at=now,
                last_row_count=row_count,
                total_partitions_written=partitions_written,
            )
            session.add(state)
        else:
            state.sync_mode = sync_mode
            state.partition_col = partition_col
            state.last_synced_date = last_synced_date
            state.last_synced_at = now
            state.last_row_count = row_count
            if state.total_partitions_written is None:
                state.total_partitions_written = partitions_written
            else:
                state.total_partitions_written += partitions_written
    except Exception as exc:
        logger.warning("Could not persist sync state for %s: %s", table, exc)


# ── Partitioned sync ─────────────────────────────────────────────────────


def _partition_root(table: str) -> Path:
    return EXPORT_DIR / table


def _partition_path(table: str, year: int, month: int) -> Path:
    return _partition_root(table) / f"year={year}" / f"month={month:02d}"


def _existing_partitions(table: str) -> set[tuple[int, int]]:
    """List (year, month) pairs already present on disk for a table."""
    root = _partition_root(table)
    out: set[tuple[int, int]] = set()
    if not root.exists():
        return out
    for year_dir in root.iterdir():
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        try:
            year = int(year_dir.name.removeprefix("year="))
        except ValueError:
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not month_dir.name.startswith("month="):
                continue
            try:
                month = int(month_dir.name.removeprefix("month="))
            except ValueError:
                continue
            out.add((year, month))
    return out


def _write_partition(
    df: pd.DataFrame,
    table: str,
    year: int,
    month: int,
) -> int:
    """Write a single month partition. Returns rows written."""
    out_dir = _partition_path(table, year, month)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    table_obj = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table_obj, out_path, compression="snappy")
    return len(df)


def sync_partitioned_table(
    session: Session,
    table: str,
    partition_col: str,
    rename_map: dict[str, str] | None,
    safety_days: int = DEFAULT_SAFETY_DAYS,
    dry_run: bool = False,
) -> dict[str, int]:
    """Sync one time-series table as Hive year/month partitions.

    Returns a stats dict: {rows, partitions_written, partitions_skipped,
    bytes_written}.
    """
    total = _table_row_count(session, table)
    if total == 0:
        logger.info("  %-25s empty, skipping", table)
        if not dry_run:
            _upsert_sync_state(session, table, "partitioned", partition_col, None, 0, 0)
        return {"rows": 0, "partitions_written": 0, "partitions_skipped": 0,
                "bytes_written": 0}

    state = _get_sync_state(session, table)
    last_synced = state.last_synced_date if state else None
    existing = _existing_partitions(table)

    # Determine the set of (year, month) partitions to write.
    # - If no prior state: write ALL partitions present in DB (initial sync).
    # - If prior state: write partitions with date >= last_synced - safety_days
    #   (catches late corrections), PLUS any DB partition missing on disk
    #   (catch-up for partitions that were never written).
    all_db_pairs_query = (
        f"SELECT DISTINCT "
        f"CAST(strftime('%Y', [{partition_col}]) AS INTEGER) AS y, "
        f"CAST(strftime('%m', [{partition_col}]) AS INTEGER) AS m "
        f"FROM [{table}] ORDER BY y, m"
    )
    all_db_pairs: set[tuple[int, int]] = set()
    for r in session.execute(text(all_db_pairs_query)).all():
        if r.y and r.m:
            all_db_pairs.add((int(r.y), int(r.m)))

    if last_synced is None:
        # Initial sync: write everything in DB.
        targets = sorted(all_db_pairs)
    else:
        cutoff_date = last_synced - timedelta(days=safety_days)
        where_clause = (
            f"WHERE date([{partition_col}]) >= date('{cutoff_date.isoformat()}')"
        )
        recent_query = (
            f"SELECT DISTINCT "
            f"CAST(strftime('%Y', [{partition_col}]) AS INTEGER) AS y, "
            f"CAST(strftime('%m', [{partition_col}]) AS INTEGER) AS m "
            f"FROM [{table}] {where_clause} ORDER BY y, m"
        )
        recent_pairs: set[tuple[int, int]] = set()
        for r in session.execute(text(recent_query)).all():
            if r.y and r.m:
                recent_pairs.add((int(r.y), int(r.m)))
        # Catch-up: DB partitions not yet on disk (regardless of date).
        missing_on_disk = all_db_pairs - existing
        targets = sorted(recent_pairs | missing_on_disk)

    if not targets:
        logger.info("  %-25s no new partitions (last_synced=%s)", table, last_synced)
        return {"rows": 0, "partitions_written": 0, "partitions_skipped": 0,
                "bytes_written": 0}

    rows_written = 0
    partitions_written = 0
    bytes_written = 0
    max_date_seen = last_synced

    for year, month in targets:
        # Read this month's rows from DB.
        month_query = (
            f"SELECT * FROM [{table}] "
            f"WHERE strftime('%Y', [{partition_col}]) = '{year:04d}' "
            f"AND strftime('%m', [{partition_col}]) = '{month:02d}'"
        )
        df = pd.read_sql_query(month_query, session.bind)
        if df.empty:
            continue
        df = _drop_bookkeeping_cols(df, table)
        df = _apply_rename(df, rename_map)

        if dry_run:
            logger.info("  [DRY RUN] %-25s y=%d m=%d : %d rows",
                        table, year, month, len(df))
            rows_written += len(df)
            partitions_written += 1
            continue

        n = _write_partition(df, table, year, month)
        out_path = _partition_path(table, year, month) / "data.parquet"
        size = out_path.stat().st_size if out_path.exists() else 0
        rows_written += n
        partitions_written += 1
        bytes_written += size
        logger.info("  %-25s y=%d m=%d : %d rows, %d KB",
                    table, year, month, n, size // 1024)

        # Track max partition date seen.
        col_values = pd.to_datetime(df[partition_col], errors="coerce") if partition_col in df.columns else pd.Series([], dtype="datetime64[ns]")
        if not col_values.empty:
            local_max = col_values.max().date()
            if max_date_seen is None or local_max > max_date_seen:
                max_date_seen = local_max

    if not dry_run:
        _upsert_sync_state(
            session, table, "partitioned", partition_col,
            max_date_seen, rows_written, partitions_written,
        )

    return {
        "rows": rows_written,
        "partitions_written": partitions_written,
        "partitions_skipped": 0,
        "bytes_written": bytes_written,
    }


# ── Full-rewrite sync (reference + non-empty runtime) ────────────────────


def sync_full_rewrite(
    session: Session,
    table: str,
    rename_map: dict[str, str] | None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Full-rewrite sync for a reference or non-empty runtime table."""
    count = _table_row_count(session, table)
    if count == 0:
        logger.info("  %-25s empty, skipping", table)
        if not dry_run:
            _upsert_sync_state(session, table, "full_rewrite", None, None, 0, 0)
        return {"rows": 0, "bytes_written": 0}

    df = pd.read_sql_table(table, session.bind)
    df = _drop_bookkeeping_cols(df, table)
    df = _apply_rename(df, rename_map)

    out_path = EXPORT_DIR / f"{table}.parquet"
    if dry_run:
        logger.info("  [DRY RUN] %-25s : %d rows, %d cols",
                    table, len(df), len(df.columns))
        return {"rows": len(df), "bytes_written": 0}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)
    size = out_path.stat().st_size
    logger.info("  %-25s : %d rows, %d KB", table, len(df), size // 1024)

    _upsert_sync_state(session, table, "full_rewrite", None, None, len(df), 1)
    return {"rows": len(df), "bytes_written": size}


# ── Orchestration ────────────────────────────────────────────────────────


def sync_all(
    safety_days: int = DEFAULT_SAFETY_DAYS,
    only_table: str | None = None,
    force_full_rewrite: bool = False,
    dry_run: bool = False,
) -> dict[str, dict[str, int]]:
    """Run the hybrid sync. Returns per-table stats."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Sync target: %s", EXPORT_DIR)
    logger.info("Safety window: %d days", safety_days)
    if only_table:
        logger.info("Filtering to table: %s", only_table)
    if force_full_rewrite:
        logger.info("Force full-rewrite mode requested for partitioned tables")

    sessionmaker = get_sessionmaker()
    session = sessionmaker()
    results: dict[str, dict[str, int]] = {}

    try:
        # Partitioned tables
        for table, pcol, rename in PARTITIONED_TABLES:
            if only_table and table != only_table:
                continue
            if force_full_rewrite:
                # Treat as full rewrite (single flat file), ignoring partitions.
                results[table] = sync_full_rewrite(session, table, rename, dry_run)
            else:
                results[table] = sync_partitioned_table(
                    session, table, pcol, rename,
                    safety_days=safety_days, dry_run=dry_run,
                )
            if not dry_run:
                try:
                    session.commit()
                except Exception as exc:
                    logger.warning("commit state for %s failed (%s) — parquet already written", table, exc)
                    session.rollback()

        # Reference tables
        for table, rename in REFERENCE_TABLES:
            if only_table and table != only_table:
                continue
            results[table] = sync_full_rewrite(session, table, rename, dry_run)
            if not dry_run:
                try:
                    session.commit()
                except Exception as exc:
                    logger.warning("commit state for %s failed (%s) — parquet already written", table, exc)
                    session.rollback()

        # Runtime tables (skip if empty)
        for table, rename in RUNTIME_TABLES:
            if only_table and table != only_table:
                continue
            results[table] = sync_full_rewrite(session, table, rename, dry_run)
            if not dry_run:
                try:
                    session.commit()
                except Exception as exc:
                    logger.warning("commit state for %s failed (%s) — parquet already written", table, exc)
                    session.rollback()

        # Sanity: warn about any user table we did not classify.
        inspector = inspect(session.bind)
        all_tables = set(inspector.get_table_names()) - SKIP_TABLES
        classified = (
            {t for t, _, _ in PARTITIONED_TABLES}
            | {t for t, _ in REFERENCE_TABLES}
            | {t for t, _ in RUNTIME_TABLES}
        )
        unclassified = sorted(all_tables - classified)
        if unclassified:
            logger.warning("Unclassified tables (NOT synced): %s", unclassified)

    finally:
        session.close()

    return results


def print_summary(results: dict[str, dict[str, int]]) -> None:
    print(f"\n{'=' * 70}")
    print("SYNC SUMMARY")
    print(f"{'=' * 70}")
    total_rows = 0
    total_bytes = 0
    total_parts = 0
    for table, stats in results.items():
        rows = stats.get("rows", 0)
        parts = stats.get("partitions_written", 0)
        size = stats.get("bytes_written", 0)
        total_rows += rows
        total_parts += parts
        total_bytes += size
        if parts:
            print(f"  {table:<28} {rows:>10,} rows  {parts:>4} parts  "
                  f"{size // 1024:>10,} KB")
        else:
            print(f"  {table:<28} {rows:>10,} rows  "
                  f"{'-':>4}       {size // 1024:>10,} KB")
    print(f"\n  Total: {total_rows:,} rows, {total_parts} partitions, "
          f"{total_bytes // 1024:,} KB written")
    print(f"  Output: {EXPORT_DIR}")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="Incremental DB → Parquet sync")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--table", default=None,
                        help="Sync only this table (default: all)")
    parser.add_argument("--full-rewrite", action="store_true",
                        help="Force full-rewrite even for partitioned tables")
    parser.add_argument("--safety-days", type=int, default=DEFAULT_SAFETY_DAYS,
                        help=f"Re-write window after last_synced_date "
                             f"(default {DEFAULT_SAFETY_DAYS})")
    args = parser.parse_args()

    res = sync_all(
        safety_days=args.safety_days,
        only_table=args.table,
        force_full_rewrite=args.full_rewrite,
        dry_run=args.dry_run,
    )
    print_summary(res)
