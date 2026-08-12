"""Data health checks for real-world failure scenarios.

Detects and reports:
- Stale data (tickers not updated >N days)
- Flashdisk not mounted (parquet export target)
- Disk space low
- DB integrity issues
- WAL size too large
- Source health degradation

Usage:
    from market.data.data_health import check_all
    report = check_all()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Thresholds
STALE_DAYS_WARNING = 3
STALE_DAYS_CRITICAL = 7
DISK_FREE_MIN_GB = 1.0
WAL_MAX_MB = 100


@dataclass
class HealthIssue:
    """A single health issue found during checks."""

    severity: str  # "info", "warning", "critical"
    category: str  # "stale_data", "disk", "db", "source"
    message: str
    detail: str = ""


@dataclass
class HealthReport:
    """Result of health checks."""

    checked_at: str = ""
    issues: list[HealthIssue] = field(default_factory=list)
    db_path: str = ""
    parquet_path: str = ""

    @property
    def has_critical(self) -> bool:
        return any(i.severity == "critical" for i in self.issues)

    @property
    def has_warning(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)

    def summary(self) -> str:
        crit = sum(1 for i in self.issues if i.severity == "critical")
        warn = sum(1 for i in self.issues if i.severity == "warning")
        info = sum(1 for i in self.issues if i.severity == "info")
        return f"{crit} critical, {warn} warning, {info} info"


def check_stale_data(con: object) -> list[HealthIssue]:
    """Check for tickers with stale OHLCV data."""
    from market.config import settings
    _ph = "%s" if settings.db_backend == "postgresql" else "?"

    issues: list[HealthIssue] = []
    now = datetime.now(UTC)
    _now_str = now.strftime("%Y-%m-%d")

    if settings.db_backend == "postgresql":
        _stale_sql = f"""
            SELECT o.ticker, MAX(o.timestamp::date)::text last_date,
                   EXTRACT(EPOCH FROM (NOW() - MAX(o.timestamp)))/86400 days_old
            FROM ohlcv o
            JOIN instrument_master im ON (
                im.ticker = REPLACE(o.ticker, '.JK', '')
                AND im.market_mic = 'XIDX'
                AND im.is_active::text IN ('1', 'true', 't')
                AND im.asset_class = 'equity'
            )
            WHERE o.ticker LIKE '%%.JK'
            GROUP BY o.ticker
            HAVING EXTRACT(EPOCH FROM (NOW() - MAX(o.timestamp)))/86400 > {_ph}
            ORDER BY days_old DESC
        """
    else:
        _stale_sql = f"""
            SELECT o.ticker, MAX(date(o.timestamp)) last_date,
                   julianday('now') - julianday(MAX(date(o.timestamp))) days_old
            FROM ohlcv o
            JOIN instrument_master im ON (
                im.ticker = REPLACE(o.ticker, '.JK', '')
                AND im.market_mic = 'XIDX'
                AND im.is_active = 1
                AND im.asset_class = 'equity'
            )
            WHERE o.ticker LIKE '%.JK'
            GROUP BY o.ticker
            HAVING days_old > {_ph}
            ORDER BY days_old DESC
        """

    stale = con.execute(_stale_sql, (STALE_DAYS_CRITICAL,)).fetchall()

    if stale:
        # Separate delisted (very old) from temporarily stale
        delisted = [s for s in stale if s[2] > 365]
        temporarily_stale = [s for s in stale if s[2] <= 365]

        if temporarily_stale:
            issues.append(HealthIssue(
                severity="warning",
                category="stale_data",
                message=f"{len(temporarily_stale)} tickers not updated >{STALE_DAYS_CRITICAL} days",
                detail=f"Most stale: {temporarily_stale[0][0]} ({temporarily_stale[0][2]:.0f} days)",
            ))

        if delisted:
            issues.append(HealthIssue(
                severity="info",
                category="stale_data",
                message=f"{len(delisted)} tickers appear delisted (>{365} days stale)",
                detail=f"Oldest: {delisted[0][0]} ({delisted[0][2]:.0f} days)",
            ))

    # Global reference tickers stale
    global_refs = ["^GSPC", "^IXIC", "^DJI", "^HSI", "^N225", "^FTSE", "^GDAXI",
                   "^TNX", "^VIX", "GC=F", "CL=F", "^JKSE"]
    if settings.db_backend == "postgresql":
        _global_sql = f"""
            SELECT ticker, MAX(timestamp::date)::text last_date,
                   EXTRACT(EPOCH FROM (NOW() - MAX(timestamp)))/86400 days_old
            FROM ohlcv
            WHERE ticker IN ({','.join(f"'{t}'" for t in global_refs)})
            GROUP BY ticker
            HAVING EXTRACT(EPOCH FROM (NOW() - MAX(timestamp)))/86400 > {_ph}
        """
    else:
        _global_sql = f"""
            SELECT ticker, MAX(date(timestamp)) last_date,
                   julianday('now') - julianday(MAX(date(timestamp))) days_old
            FROM ohlcv
            WHERE ticker IN ({','.join(f"'{t}'" for t in global_refs)})
            GROUP BY ticker
            HAVING days_old > ?
        """
    stale_global = con.execute(
        _global_sql, (STALE_DAYS_WARNING,),
    ).fetchall()

    if stale_global:
        issues.append(HealthIssue(
            severity="critical",
            category="stale_data",
            message=f"{len(stale_global)} global reference tickers stale >{STALE_DAYS_WARNING} days",
            detail=", ".join(f"{s[0]}({s[2]:.0f}d)" for s in stale_global[:5]),
        ))

    return issues


def check_disk_space(parquet_path: Path) -> list[HealthIssue]:
    """Check flashdisk mount and disk space."""
    issues: list[HealthIssue] = []

    if not parquet_path.exists():
        issues.append(HealthIssue(
            severity="critical",
            category="disk",
            message=f"Parquet target not mounted: {parquet_path}",
            detail="Flashdisk may be unplugged. Export will fail.",
        ))
        return issues

    stat = os.statvfs(parquet_path)
    free_gb = (stat.f_bavail * stat.f_frsize) / 1024**3

    if free_gb < DISK_FREE_MIN_GB:
        issues.append(HealthIssue(
            severity="critical",
            category="disk",
            message=f"Disk space low: {free_gb:.2f} GB free (min {DISK_FREE_MIN_GB} GB)",
            detail=f"Path: {parquet_path}",
        ))
    elif free_gb < DISK_FREE_MIN_GB * 2:
        issues.append(HealthIssue(
            severity="warning",
            category="disk",
            message=f"Disk space getting low: {free_gb:.2f} GB free",
        ))

    return issues


def check_pg_health(issues: list[HealthIssue]) -> list[HealthIssue]:
    """PostgreSQL-specific health checks."""
    from market.db.raw import get_raw_connection

    try:
        with get_raw_connection() as con:
            # Connection test
            ver = con.execute("SELECT version()").fetchone()[0]
            issues.append(HealthIssue(
                severity="info",
                category="db",
                message=f"PostgreSQL connected: {ver.split(',')[0]}",
            ))

            # Database size
            db_size = con.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            ).fetchone()[0]
            issues.append(HealthIssue(
                severity="info",
                category="db",
                message=f"Database size: {db_size}",
            ))

            # Long-running transactions (>5 min)
            long_txns = con.execute("""
                SELECT count(*) FROM pg_stat_activity
                WHERE state = 'idle in transaction'
                  AND xact_start < NOW() - INTERVAL '5 minutes'
            """).fetchone()[0]
            if long_txns > 0:
                issues.append(HealthIssue(
                    severity="warning",
                    category="db",
                    message=f"{long_txns} long-running idle transactions (>5 min)",
                    detail="May cause bloat. Consider terminating stale sessions.",
                ))

            # Table bloat (approximate via pg_stat_user_tables)
            bloated = con.execute("""
                SELECT relname, n_live_tup, n_dead_tup,
                       CASE WHEN n_live_tup > 0
                            THEN round(n_dead_tup::numeric / n_live_tup * 100, 1)
                            ELSE 0 END as dead_pct
                FROM pg_stat_user_tables
                WHERE n_live_tup > 1000 AND n_dead_tup > 100
                ORDER BY dead_pct DESC LIMIT 5
            """).fetchall()
            for r in bloated:
                if r[3] and r[3] > 10:
                    issues.append(HealthIssue(
                        severity="warning",
                        category="db",
                        message=f"Table {r[0]} has {r[3]}% dead tuples ({r[2]} dead / {r[1]} live)",
                        detail="Consider VACUUM ANALYZE to reclaim space.",
                    ))

            # Check critical tables exist and have data
            critical_tables = [
                "stock_prices", "instruments", "technical_indicators",
                "scores", "fear_greed", "stock_personality",
            ]
            for tbl in critical_tables:
                try:
                    cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
                    if cnt == 0:
                        issues.append(HealthIssue(
                            severity="critical",
                            category="db",
                            message=f"Critical table '{tbl}' is empty",
                        ))
                except Exception:
                    issues.append(HealthIssue(
                        severity="critical",
                        category="db",
                        message=f"Critical table '{tbl}' missing or inaccessible",
                    ))

    except Exception as e:
        issues.append(HealthIssue(
            severity="critical",
            category="db",
            message=f"PostgreSQL connection failed: {e}",
        ))

    return issues


def check_db_health(db_path: Path) -> list[HealthIssue]:
    """Check DB integrity, WAL size, and foreign keys.

    For PostgreSQL, checks connection status, bloat, and long-running transactions.
    For SQLite, checks WAL size, integrity, and foreign keys.
    """
    from market.config import settings
    issues: list[HealthIssue] = []

    if settings.db_backend == "postgresql":
        return check_pg_health(issues)

    import sqlite3

    # WAL size
    wal_path = Path(str(db_path) + "-wal")
    if wal_path.exists():
        wal_mb = wal_path.stat().st_size / 1024 / 1024
        if wal_mb > WAL_MAX_MB:
            issues.append(HealthIssue(
                severity="warning",
                category="db",
                message=f"WAL file large: {wal_mb:.1f} MB (max {WAL_MAX_MB} MB)",
                detail="Run WAL checkpoint to compact.",
            ))

    # Integrity check (quick mode)
    con = sqlite3.connect(str(db_path))
    try:
        integrity = con.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            issues.append(HealthIssue(
                severity="critical",
                category="db",
                message=f"DB integrity check failed: {integrity}",
            ))

        fk_violations = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            issues.append(HealthIssue(
                severity="warning",
                category="db",
                message=f"{len(fk_violations)} FK violations",
                detail=f"Tables: {set(r[0] for r in fk_violations)}",
            ))

        # Check busy_timeout
        busy = con.execute("PRAGMA busy_timeout").fetchone()[0]
        if busy < 5000:
            issues.append(HealthIssue(
                severity="info",
                category="db",
                message=f"busy_timeout={busy}ms (recommend >=5000)",
            ))
    finally:
        con.close()

    return issues


def check_source_health(con: object) -> list[HealthIssue]:
    """Check data source health status."""
    issues: list[HealthIssue] = []

    rows = con.execute(
        "SELECT source, status, total_failures, last_error_msg FROM source_health"
    ).fetchall()

    for r in rows:
        if r[1] == "error":
            issues.append(HealthIssue(
                severity="critical",
                category="source",
                message=f"Source {r[0]} in error state",
                detail=f"Failures: {r[2]}, Error: {r[3]}",
            ))
        elif r[2] and r[2] > 10:
            issues.append(HealthIssue(
                severity="warning",
                category="source",
                message=f"Source {r[0]} has {r[2]} failures",
            ))

    return issues


def check_all(db_path: Path | str, parquet_path: Path | str) -> HealthReport:
    """Run all health checks and return a report.

    Args:
        db_path: Path to database (SQLite or PostgreSQL config path).
        parquet_path: Path to parquet archive directory.

    Returns:
        HealthReport with all issues found.
    """
    from market.config import settings

    db_path = Path(db_path)
    parquet_path = Path(parquet_path)
    report = HealthReport(
        checked_at=datetime.now(UTC).isoformat(),
        db_path=str(db_path),
        parquet_path=str(parquet_path),
    )

    # DB checks (SQLite-only PRAGMA checks, no-op for PostgreSQL)
    report.issues.extend(check_db_health(db_path))

    # Open DB for data checks via unified connection helper
    from market.db.raw import get_raw_connection
    with get_raw_connection() as con:
        report.issues.extend(check_stale_data(con))
        report.issues.extend(check_source_health(con))

    # Disk checks
    report.issues.extend(check_disk_space(parquet_path))

    logger.info("Health check: %s — %s", report.summary(), report.checked_at)
    return report


def wal_checkpoint(db_path: Path | str, mode: str = "TRUNCATE") -> bool:
    """Run WAL checkpoint to compact the database (SQLite-only).

    No-op for PostgreSQL — PG manages its own WAL.

    Args:
        db_path: Path to SQLite database.
        mode: Checkpoint mode (PASSIVE, FULL, RESTART, TRUNCATE).

    Returns:
        True if checkpoint succeeded (always True for PostgreSQL).
    """
    from market.config import settings

    if settings.db_backend == "postgresql":
        logger.info("WAL checkpoint: skipped (PostgreSQL manages WAL internally)")
        return True

    import sqlite3

    con = sqlite3.connect(str(db_path))
    try:
        result = con.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        logger.info("WAL checkpoint %s: busy=%d, log=%d, checkpointed=%d",
                     mode, result[0], result[1], result[2])
        return result[0] == 0  # 0 = success
    except Exception as e:
        logger.error("WAL checkpoint failed: %s", e)
        return False
    finally:
        con.close()
