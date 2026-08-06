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
import sqlite3
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


def check_stale_data(con: sqlite3.Connection) -> list[HealthIssue]:
    """Check for tickers with stale OHLCV data."""
    issues: list[HealthIssue] = []
    now = datetime.now(UTC)

    # Active IDX equity tickers stale >7 days
    stale = con.execute(
        """
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
        HAVING days_old > ?
        ORDER BY days_old DESC
        """,
        (STALE_DAYS_CRITICAL,),
    ).fetchall()

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
    stale_global = con.execute(
        """
        SELECT ticker, MAX(date(timestamp)) last_date,
               julianday('now') - julianday(MAX(date(timestamp))) days_old
        FROM ohlcv
        WHERE ticker IN ({})
        GROUP BY ticker
        HAVING days_old > ?
        """.format(",".join(f"'{t}'" for t in global_refs)),
        (STALE_DAYS_WARNING,),
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


def check_db_health(db_path: Path) -> list[HealthIssue]:
    """Check DB integrity, WAL size, and foreign keys."""
    issues: list[HealthIssue] = []

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


def check_source_health(con: sqlite3.Connection) -> list[HealthIssue]:
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
        db_path: Path to SQLite database.
        parquet_path: Path to parquet archive directory.

    Returns:
        HealthReport with all issues found.
    """
    db_path = Path(db_path)
    parquet_path = Path(parquet_path)
    report = HealthReport(
        checked_at=datetime.now(UTC).isoformat(),
        db_path=str(db_path),
        parquet_path=str(parquet_path),
    )

    # DB checks (don't need a persistent connection)
    report.issues.extend(check_db_health(db_path))

    # Open DB for data checks
    con = sqlite3.connect(str(db_path))
    try:
        report.issues.extend(check_stale_data(con))
        report.issues.extend(check_source_health(con))
    finally:
        con.close()

    # Disk checks
    report.issues.extend(check_disk_space(parquet_path))

    logger.info("Health check: %s — %s", report.summary(), report.checked_at)
    return report


def wal_checkpoint(db_path: Path | str, mode: str = "TRUNCATE") -> bool:
    """Run WAL checkpoint to compact the database.

    Args:
        db_path: Path to SQLite database.
        mode: Checkpoint mode (PASSIVE, FULL, RESTART, TRUNCATE).

    Returns:
        True if checkpoint succeeded.
    """
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
