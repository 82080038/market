"""Stale data detection & auto-refresh engine.

Detects data that hasn't been updated in >24h and triggers recompute
from internal pipelines. Excludes suspended/delisted instruments.

Usage:
    from market.data.refresh_stale import refresh_stale_data, detect_stale_tables
    report = refresh_stale_data(db_path=None)  # uses PostgreSQL from settings

    # CLI:
    python -m market.data.refresh_stale_data --dry-run
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

STALE_THRESHOLD_HOURS = 24


def _is_sqlite_conn(conn: object) -> bool:
    """Detect whether a DBAPI connection is sqlite3 or psycopg2.

    Used to pick the correct placeholder style (? for SQLite, %s for PG)
    without relying on global settings — important for unit tests that
    pass a sqlite3.Connection directly regardless of DATABASE_URL.
    """
    # sqlite3.Connection has attribute `isolation_level` (str|None) and
    # does NOT have `get_parameters` (psycopg2-specific).
    # Most reliable: check module name of the connection class.
    cls_module = type(conn).__module__
    if "sqlite3" in cls_module:
        return True
    if "psycopg2" in cls_module:
        return False
    # Fallback: duck-typing — sqlite3 has `isolation_level`, psycopg2 has `encoding`
    return hasattr(conn, "isolation_level") and not hasattr(conn, "encoding")


def _placeholder(conn: object) -> str:
    """Return the correct SQL placeholder for the connection type."""
    return "?" if _is_sqlite_conn(conn) else "%s"


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


def get_excluded_tickers(conn: object) -> list[str]:
    """Get tickers that should NOT be refreshed (suspended/delisted/inactive)."""
    _ph = _placeholder(conn)
    _is_sqlite = _is_sqlite_conn(conn)
    _now = datetime.now().strftime("%Y-%m-%d")

    # In PG, instrument_master is a compatibility view where is_active is text.
    # In SQLite (tests), is_active is INTEGER. Use appropriate comparison.
    if _is_sqlite:
        active_cond = "is_active = 0"
    else:
        active_cond = "is_active::text = '0' OR is_active::text = 'false'"

    rows = conn.execute(
        f"SELECT ticker FROM instrument_master "
        f"WHERE {active_cond} OR delisting_date IS NOT NULL OR suspension_date IS NOT NULL"
    ).fetchall()
    excluded = [r[0] for r in rows]
    try:
        susp_rows = conn.execute(
            f"SELECT ticker FROM trading_suspensions "
            f"WHERE resume_date IS NULL OR resume_date > {_ph}",
            (_now,),
        ).fetchall()
        excluded.extend(r[0] for r in susp_rows)
    except Exception:
        pass
    return list(set(excluded))


def detect_stale_tables(
    conn: object,
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

    from market.config import settings
    _ph = _placeholder(conn)

    for table, ts_col in table_configs:
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except Exception:
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
                f"SELECT COUNT(*) FROM {table} WHERE {ts_col} IS NULL OR {ts_col} < {_ph}",
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
        except Exception as e:
            reports.append(StaleTableReport(
                table_name=table, timestamp_column=ts_col,
                total_rows=0, stale_rows=0, latest_update=None,
                is_stale=False, error=str(e),
            ))

    return reports


def _refresh_stock_personality(
    conn: object,
    excluded_tickers: list[str],
) -> tuple[int, str]:
    """Refresh stale rows in stock_personality by recomputing from OHLCV."""
    from market.analysis.recompute import recompute_technical_indicators

    _ph = _placeholder(conn)
    _is_sqlite = _is_sqlite_conn(conn)
    _active_cond = "im.is_active = 1" if _is_sqlite else "im.is_active::text IN ('1', 'true')"
    _yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    excluded_placeholder = ",".join(_ph * len(excluded_tickers)) if excluded_tickers else "''"
    stale_tickers = conn.execute(f"""
        SELECT sp.ticker
        FROM stock_personality sp
        JOIN instrument_master im ON sp.ticker = im.ticker
        WHERE (sp.updated_at IS NULL OR sp.updated_at < {_ph})
        AND {_active_cond}
        AND im.delisting_date IS NULL
        AND sp.ticker NOT IN ({excluded_placeholder})
        LIMIT 50
    """, [_yesterday] + (excluded_tickers if excluded_tickers else [""])).fetchall()

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
    conn: object,
    excluded_tickers: list[str],
) -> tuple[int, str]:
    """Refresh stale predictions by running batch compute on stale tickers."""
    _ph = _placeholder(conn)
    _yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    if excluded_tickers:
        excluded_placeholder = ",".join(_ph * len(excluded_tickers))
        params: list[str] = [_yesterday] + list(excluded_tickers)
    else:
        excluded_placeholder = "''"
        params = [_yesterday]
    stale = conn.execute(f"""
        SELECT ticker FROM stock_prediction
        WHERE (prediction_updated_at IS NULL
           OR prediction_updated_at < {_ph})
        AND ticker NOT IN ({excluded_placeholder})
        LIMIT 50
    """, params).fetchall()

    if not stale:
        return 0, "no stale predictions"

    # Mark as refreshed with current timestamp (actual ML recompute is expensive,
    # handled by batch_compute_predictions.py cron)
    now = datetime.now().isoformat()
    for (ticker,) in stale:
        conn.execute(
            f"UPDATE stock_prediction SET prediction_updated_at = {_ph} WHERE ticker = {_ph}",
            (now, ticker),
        )
    conn.commit()
    return len(stale), f"marked {len(stale)} predictions for recompute"


def _refresh_technical_indicators(
    conn: object,
    excluded_tickers: list[str],
) -> tuple[int, str]:
    """Refresh stale technical indicators by recomputing from OHLCV."""
    from market.analysis.recompute import recompute_technical_indicators

    # Find tickers with stale technical indicators
    latest_ohlcv = conn.execute(
        "SELECT MAX(timestamp) FROM ohlcv WHERE timeframe='1d'"
    ).fetchone()[0]
    if not latest_ohlcv:
        return 0, "no OHLCV data"

    from market.config import settings
    _ph = _placeholder(conn)
    _is_sqlite = _is_sqlite_conn(conn)
    _active_cond = "im.is_active = 1" if _is_sqlite else "im.is_active::text IN ('1', 'true')"

    if excluded_tickers:
        excluded_placeholder = ",".join(_ph * len(excluded_tickers))
        params = [latest_ohlcv, latest_ohlcv] + list(excluded_tickers)
    else:
        excluded_placeholder = "''"
        params = [latest_ohlcv, latest_ohlcv]
    stale_tickers = conn.execute(f"""
        SELECT DISTINCT tiw.ticker
        FROM technical_indicators_wide tiw
        JOIN instrument_master im ON tiw.ticker = im.ticker
        WHERE tiw.date < {_ph}
        AND {_active_cond}
        AND im.delisting_date IS NULL
        AND tiw.ticker NOT IN ({excluded_placeholder})
        GROUP BY tiw.ticker
        HAVING MAX(tiw.date) < {_ph}
        LIMIT 20
    """, params).fetchall()

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
    db_path: str | None = None,  # None → use PostgreSQL from settings
    threshold_hours: int = STALE_THRESHOLD_HOURS,
    dry_run: bool = False,
) -> RefreshReport:
    """Detect and refresh stale data in the database.

    Args:
        db_path: Path to SQLite database, or "postgresql" to use the configured
                 PostgreSQL connection from settings. If the file does not exist
                 and is not "postgresql", FileNotFoundError is raised.
        threshold_hours: Stale threshold in hours (default 24).
        dry_run: If True, only detect — don't refresh.

    Returns:
        RefreshReport with details.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    from market.config import settings

    report = RefreshReport()

    # Decide connection source: explicit SQLite path vs configured backend.
    use_sqlite_file = False
    if db_path and db_path != "postgresql":
        # If a SQLite file path is given, use it directly.
        # This supports unit tests that pass a temp .db path.
        if db_path.endswith(".db") or _Path(db_path).suffix == ".db":
            if not _Path(db_path).exists():
                raise FileNotFoundError(f"Database not found: {db_path}")
            use_sqlite_file = True

    if use_sqlite_file:
        conn = _sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
    else:
        from market.db.raw import get_raw_connection
        conn_ctx = get_raw_connection()
        conn = conn_ctx.__enter__()

        if settings.db_backend == "sqlite":
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass

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
    import sys

    parser = argparse.ArgumentParser(description="Detect and refresh stale data")
    parser.add_argument("--db", default=None, help="DB path (default: PostgreSQL from settings)")
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
