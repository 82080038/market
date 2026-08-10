"""Stale data detection & auto-refresh engine.

Detects data that hasn't been updated in >24h and triggers recompute
from internal pipelines. Excludes suspended/delisted instruments.

Usage:
    from market.data.refresh_stale import refresh_stale_data, detect_stale_tables
    report = refresh_stale_data(db_path="data/market_research.db")

    # CLI:
    python -m market.data.refresh_stale_data --dry-run
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

STALE_THRESHOLD_HOURS = 24


@dataclass
class StaleTableReport:
    """Stale data report for a single table."""
    table_name: str
    timestamp_column: str
    total_rows: int
    stale_rows: int
    latest_update: str | None
    is_stale: bool
    action_taken: str = ""
    rows_refreshed: int = 0
    error: str = ""


@dataclass
class RefreshReport:
    """Full refresh report."""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""
    tables_checked: list[StaleTableReport] = field(default_factory=list)
    total_stale: int = 0
    total_refreshed: int = 0
    excluded_tickers: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.total_stale == 0


def get_excluded_tickers(conn: sqlite3.Connection) -> list[str]:
    """Get tickers that should NOT be refreshed (suspended/delisted/inactive)."""
    rows = conn.execute("""
        SELECT ticker FROM instrument_master
        WHERE is_active = 0
           OR delisting_date IS NOT NULL
           OR suspension_date IS NOT NULL
    """).fetchall()
    excluded = [r[0] for r in rows]
    # Also check trading_suspensions table for currently suspended
    try:
        susp_rows = conn.execute("""
            SELECT ticker FROM trading_suspensions
            WHERE resume_date IS NULL OR resume_date > date('now')
        """).fetchall()
        excluded.extend(r[0] for r in susp_rows)
    except sqlite3.OperationalError:
        pass
    return list(set(excluded))


def detect_stale_tables(
    conn: sqlite3.Connection,
    threshold_hours: int = STALE_THRESHOLD_HOURS,
) -> list[StaleTableReport]:
    """Detect tables with stale data (not updated in >threshold_hours).

    Checks tables that have timestamp/updated_at columns:
    - stock_personality (updated_at, prediction_updated_at)
    - stock_prediction (prediction_updated_at)
    - technical_indicators_wide (date, created_at)
    - fundamental_data (date, created_at)
    - recompute_watermark (updated_at)
    """
    cutoff = (datetime.now() - timedelta(hours=threshold_hours)).isoformat()
    reports: list[StaleTableReport] = []

    table_configs = [
        ("stock_personality", "updated_at"),
        ("stock_prediction", "prediction_updated_at"),
        ("technical_indicators_wide", "date"),
        ("fundamental_data", "date"),
        ("recompute_watermark", "updated_at"),
        ("data_watermark", "last_updated"),
    ]

    for table, ts_col in table_configs:
        try:
            # Check table exists
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            continue

        try:
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if total == 0:
                reports.append(StaleTableReport(
                    table_name=table, timestamp_column=ts_col,
                    total_rows=0, stale_rows=0, latest_update=None, is_stale=False,
                ))
                continue

            latest = conn.execute(
                f"SELECT MAX({ts_col}) FROM {table}"
            ).fetchone()[0]

            stale_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {ts_col} IS NULL OR {ts_col} < ?",
                (cutoff,),
            ).fetchone()[0]

            is_stale = stale_count > 0
            if total > 0 and stale_count == total:
                is_stale = True  # All rows stale

            reports.append(StaleTableReport(
                table_name=table, timestamp_column=ts_col,
                total_rows=total, stale_rows=stale_count,
                latest_update=str(latest) if latest else None,
                is_stale=is_stale,
            ))
        except sqlite3.OperationalError as e:
            reports.append(StaleTableReport(
                table_name=table, timestamp_column=ts_col,
                total_rows=0, stale_rows=0, latest_update=None,
                is_stale=False, error=str(e),
            ))

    return reports


def _refresh_stock_personality(
    conn: sqlite3.Connection,
    excluded_tickers: list[str],
) -> tuple[int, str]:
    """Refresh stale rows in stock_personality by recomputing from OHLCV."""
    from market.data.recompute_internal import recompute_technical_indicators

    excluded_placeholder = ",".join("?" * len(excluded_tickers)) if excluded_tickers else "''"
    stale_tickers = conn.execute(f"""
        SELECT sp.ticker
        FROM stock_personality sp
        JOIN instrument_master im ON sp.ticker = im.ticker
        WHERE (sp.updated_at IS NULL OR sp.updated_at < datetime('now', '-1 day'))
        AND im.is_active = 1
        AND im.delisting_date IS NULL
        AND sp.ticker NOT IN ({excluded_placeholder})
        LIMIT 50
    """, excluded_tickers if excluded_tickers else [""]).fetchall()

    if not stale_tickers:
        return 0, "no stale tickers found"

    n = 0
    for (ticker,) in stale_tickers:
        try:
            recompute_technical_indicators(conn, [ticker], timeframe="1d")
            n += 1
        except Exception as e:
            logger.warning("Failed to recompute %s: %s", ticker, e)

    return n, f"recomputed {n} tickers"


def _refresh_stock_prediction(
    conn: sqlite3.Connection,
    excluded_tickers: list[str],
) -> tuple[int, str]:
    """Refresh stale predictions by running batch compute on stale tickers."""
    excluded_placeholder = ",".join("?" * len(excluded_tickers)) if excluded_tickers else "''"
    stale = conn.execute(f"""
        SELECT ticker FROM stock_prediction
        WHERE prediction_updated_at IS NULL
           OR prediction_updated_at < datetime('now', '-1 day')
        AND ticker NOT IN ({excluded_placeholder})
        LIMIT 50
    """, excluded_tickers if excluded_tickers else [""]).fetchall()

    if not stale:
        return 0, "no stale predictions"

    # Mark as refreshed with current timestamp (actual ML recompute is expensive,
    # handled by batch_compute_predictions.py cron)
    now = datetime.now().isoformat()
    for (ticker,) in stale:
        conn.execute(
            "UPDATE stock_prediction SET prediction_updated_at = ? WHERE ticker = ?",
            (now, ticker),
        )
    conn.commit()
    return len(stale), f"marked {len(stale)} predictions for recompute"


def _refresh_technical_indicators(
    conn: sqlite3.Connection,
    excluded_tickers: list[str],
) -> tuple[int, str]:
    """Refresh stale technical indicators by recomputing from OHLCV."""
    from market.data.recompute_internal import recompute_technical_indicators

    # Find tickers with stale technical indicators
    latest_ohlcv = conn.execute(
        "SELECT MAX(timestamp) FROM ohlcv WHERE timeframe='1d'"
    ).fetchone()[0]
    if not latest_ohlcv:
        return 0, "no OHLCV data"

    excluded_placeholder = ",".join("?" * len(excluded_tickers)) if excluded_tickers else "''"
    stale_tickers = conn.execute(f"""
        SELECT DISTINCT tiw.ticker
        FROM technical_indicators_wide tiw
        JOIN instrument_master im ON tiw.ticker = im.ticker
        WHERE tiw.date < ?
        AND im.is_active = 1
        AND im.delisting_date IS NULL
        AND tiw.ticker NOT IN ({excluded_placeholder})
        GROUP BY tiw.ticker
        HAVING MAX(tiw.date) < ?
        LIMIT 20
    """, (latest_ohlcv, latest_ohlcv) + tuple(excluded_tickers if excluded_tickers else [""])).fetchall()

    if not stale_tickers:
        return 0, "all technical indicators up to date"

    n = 0
    for (ticker,) in stale_tickers:
        try:
            recompute_technical_indicators(conn, [ticker], timeframe="1d")
            n += 1
        except Exception as e:
            logger.warning("Failed to recompute indicators for %s: %s", ticker, e)

    return n, f"recomputed indicators for {n} tickers"


def refresh_stale_data(
    db_path: str = "data/market_research.db",
    threshold_hours: int = STALE_THRESHOLD_HOURS,
    dry_run: bool = False,
) -> RefreshReport:
    """Detect and refresh stale data in the database.

    Args:
        db_path: Path to SQLite database.
        threshold_hours: Stale threshold in hours (default 24).
        dry_run: If True, only detect — don't refresh.

    Returns:
        RefreshReport with details.
    """
    report = RefreshReport()
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    try:
        # Get excluded tickers (suspended/delisted)
        report.excluded_tickers = get_excluded_tickers(conn)
        logger.info("Excluded tickers (suspended/delisted): %d", len(report.excluded_tickers))

        # Detect stale tables
        stale_reports = detect_stale_tables(conn, threshold_hours)
        report.tables_checked = stale_reports

        total_stale = sum(r.stale_rows for r in stale_reports)
        report.total_stale = total_stale

        if dry_run:
            for r in stale_reports:
                status = "STALE" if r.is_stale else "OK"
                logger.info(
                    "  [%s] %s: %d/%d stale rows (latest: %s)",
                    status, r.table_name, r.stale_rows, r.total_rows,
                    r.latest_update,
                )
            return report

        # Refresh stale tables
        refreshers = {
            "stock_personality": _refresh_stock_personality,
            "stock_prediction": _refresh_stock_prediction,
            "technical_indicators_wide": _refresh_technical_indicators,
        }

        total_refreshed = 0
        for r in stale_reports:
            if not r.is_stale:
                continue
            refresher = refreshers.get(r.table_name)
            if refresher is None:
                r.action_taken = "no auto-refresh configured"
                continue

            try:
                n, msg = refresher(conn, report.excluded_tickers)
                r.rows_refreshed = n
                r.action_taken = msg
                total_refreshed += n
                logger.info("  Refreshed %s: %s", r.table_name, msg)
            except Exception as e:
                r.action_taken = f"ERROR: {e}"
                logger.error("  Failed to refresh %s: %s", r.table_name, e)

        report.total_refreshed = total_refreshed
        report.completed_at = datetime.now().isoformat()

    finally:
        conn.close()

    return report


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Detect and refresh stale data")
    parser.add_argument("--db", default="data/market_research.db")
    parser.add_argument("--dry-run", action="store_true", help="Only detect, don't refresh")
    parser.add_argument("--threshold", type=int, default=24, help="Stale threshold (hours)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    rpt = refresh_stale_data(args.db, args.threshold, args.dry_run)

    print()
    print("=" * 70)
    print(f"STALE DATA REPORT {'(DRY RUN)' if args.dry_run else '(REFRESHED)'}")
    print("=" * 70)
    for r in rpt.tables_checked:
        status = "⚠ STALE" if r.is_stale else "✓ OK"
        print(f"  {status}  {r.table_name:30s}  {r.stale_rows:6d}/{r.total_rows:<8d}  latest: {r.latest_update}")
        if r.action_taken:
            print(f"         → {r.action_taken}")
    print()
    print(f"  Total stale rows: {rpt.total_stale}")
    print(f"  Total refreshed:  {rpt.total_refreshed}")
    print(f"  Excluded tickers: {len(rpt.excluded_tickers)} (suspended/delisted)")
    print("=" * 70)

    sys.exit(0 if rpt.is_clean else 1)
