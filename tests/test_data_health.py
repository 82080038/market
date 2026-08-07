"""Tests for data health checks (data_health module)."""

from __future__ import annotations

from pathlib import Path

from market.data.data_health import (
    HealthIssue,
    HealthReport,
    check_all,
    check_db_health,
    check_disk_space,
    wal_checkpoint,
)


def test_health_issue_severity():
    issue = HealthIssue(severity="critical", category="db", message="test")
    assert issue.severity == "critical"


def test_health_report_has_critical():
    report = HealthReport(
        issues=[HealthIssue(severity="critical", category="db", message="test")]
    )
    assert report.has_critical is True
    assert report.has_warning is False


def test_health_report_has_warning():
    report = HealthReport(
        issues=[HealthIssue(severity="warning", category="disk", message="test")]
    )
    assert report.has_critical is False
    assert report.has_warning is True


def test_health_report_summary():
    report = HealthReport(
        issues=[
            HealthIssue(severity="critical", category="a", message="x"),
            HealthIssue(severity="warning", category="b", message="y"),
            HealthIssue(severity="info", category="c", message="z"),
        ]
    )
    assert "1 critical" in report.summary()
    assert "1 warning" in report.summary()
    assert "1 info" in report.summary()


def test_check_disk_space_not_mounted(tmp_path: Path):
    """Check that missing path triggers critical issue."""
    fake_path = tmp_path / "nonexistent" / "parquet"
    issues = check_disk_space(fake_path)
    assert len(issues) == 1
    assert issues[0].severity == "critical"
    assert "not mounted" in issues[0].message


def test_check_disk_space_ok(tmp_path: Path):
    """Check that existing path with space is OK."""
    issues = check_disk_space(tmp_path)
    # Should be empty or only warnings (no critical)
    assert not any(i.severity == "critical" for i in issues)


def test_check_db_health_ok(tmp_path: Path):
    """Check that a fresh SQLite DB passes health check."""
    import sqlite3

    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE test (id INTEGER)")
    con.close()

    issues = check_db_health(db_path)
    # Fresh DB should have no critical issues
    assert not any(i.severity == "critical" for i in issues)


def test_wal_checkpoint_no_wal(tmp_path: Path):
    """WAL checkpoint on DB without WAL should succeed."""
    import sqlite3

    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE test (id INTEGER)")
    con.close()

    result = wal_checkpoint(db_path, mode="TRUNCATE")
    # Should succeed (returns True) even without WAL
    assert result is True


def test_check_all_returns_report(tmp_path: Path):
    """check_all should return a HealthReport with checked_at set."""
    import sqlite3

    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    # Create minimal tables that check_all queries
    con.execute("""
        CREATE TABLE ohlcv (
            ticker TEXT, timestamp DATETIME,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER
        )
    """)
    con.execute("CREATE TABLE source_health (source TEXT, status TEXT, total_failures INTEGER, last_error_msg TEXT)")
    con.execute("CREATE TABLE instrument_master (ticker TEXT, market_mic TEXT, asset_class TEXT, is_active INTEGER)")
    con.close()

    parquet_path = tmp_path / "parquet"
    parquet_path.mkdir()

    report = check_all(db_path=db_path, parquet_path=parquet_path)
    assert isinstance(report, HealthReport)
    assert report.checked_at != ""
    assert report.db_path == str(db_path)
