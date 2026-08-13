"""Database completeness audit for PostgreSQL (S1 — Data Layer).

Audits row counts, date ranges, null rates, and missing tables/columns
against ORM expectations. Outputs a structured report.

Usage:
    python -m market.data.db_completeness_audit
    python -m market.data.db_completeness_audit --format json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import inspect as sa_inspect, text

from market.db.engine import get_engine
from market.db.models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class TableAudit:
    table_name: str
    exists_in_db: bool
    row_count: int | None = None
    min_date: str | None = None
    max_date: str | None = None
    date_column: str | None = None
    null_rates: dict[str, float] = field(default_factory=dict)
    missing_orm_columns: list[str] = field(default_factory=list)
    extra_pg_columns: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class CompletenessReport:
    generated_at: str
    database_url: str
    total_orm_tables: int
    total_db_tables: int
    missing_in_db: list[str]
    missing_in_orm: list[str]
    empty_tables: list[str]
    table_audits: list[TableAudit]
    summary: dict[str, int]


def _get_db_tables(engine: Engine) -> set[str]:
    insp = sa_inspect(engine)
    return set(insp.get_table_names())


def _get_orm_tables() -> set[str]:
    return set(Base.metadata.tables.keys())


def _get_row_count(conn, table: str) -> int | None:
    try:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
    except Exception:
        conn.rollback()
        return None


def _get_date_range(conn, table: str, date_col: str) -> tuple[str | None, str | None]:
    try:
        r = conn.execute(text(
            f"SELECT min({date_col})::text, max({date_col})::text FROM {table}"
        ))
        row = r.first()
        return (str(row[0]) if row[0] else None, str(row[1]) if row[1] else None)
    except Exception:
        conn.rollback()
        return (None, None)


def _get_null_rates(conn, table: str, columns: list[str]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for col in columns:
        try:
            r = conn.execute(text(
                f"SELECT count(*) FILTER (WHERE {col} IS NULL)::float / "
                f"NULLIF(count(*), 0) FROM {table}"
            ))
            val = r.scalar()
            if val is not None and val > 0:
                rates[col] = round(float(val) * 100, 2)
        except Exception:
            conn.rollback()
    return rates


def _get_column_diff(conn, table: str) -> tuple[list[str], list[str]]:
    """Return (orm_only_columns, pg_only_columns)."""
    try:
        r = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t AND table_schema = 'public' ORDER BY ordinal_position"
        ), {"t": table})
        pg_cols = {row[0] for row in r}
    except Exception:
        conn.rollback()
        pg_cols = set()

    orm_table = Base.metadata.tables.get(table)
    if orm_table is None:
        return ([], sorted(pg_cols))
    orm_cols = {c.name for c in orm_table.columns}
    return (sorted(orm_cols - pg_cols), sorted(pg_cols - orm_cols))


# Tables with date columns for range checking
_DATE_COLUMN_MAP = {
    "stock_prices": "timestamp",
    "fundamental_data": "date",
    "macro_data": "date",
    "macroeconomic_indicators": "recorded_at",
    "foreign_flow": "date",
    "fear_greed": "date",
    "corporate_actions": "ex_date",
    "news_sentiment": "date",
    "market_sessions": "timestamp",
    "events": "tanggal",
    "broker_transactions": "tanggal",
}

# Tables with important nullable columns to check
_NULL_CHECK_MAP = {
    "stock_prices": ["open", "high", "low", "close", "volume", "vwap"],
    "fundamental_data": ["pe", "pb", "roe", "der", "dividend_yield", "eps", "revenue", "net_income", "market_cap", "beta"],
    "foreign_flow": ["foreign_net", "foreign_buy", "foreign_sell"],
}


def run_completeness_audit(engine: Engine | None = None) -> CompletenessReport:
    """Run full database completeness audit."""
    if engine is None:
        engine = get_engine()

    db_tables = _get_db_tables(engine)
    orm_tables = _get_orm_tables()

    missing_in_db = sorted(orm_tables - db_tables)
    missing_in_orm = sorted(db_tables - orm_tables)

    table_audits: list[TableAudit] = []
    empty_tables: list[str] = []

    with engine.connect() as conn:
        for table_name in sorted(orm_tables | db_tables):
            ta = TableAudit(table_name=table_name, exists_in_db=table_name in db_tables)

            if not ta.exists_in_db:
                ta.issues.append("Table missing in database (ORM defines it)")
                table_audits.append(ta)
                continue

            ta.row_count = _get_row_count(conn, table_name)
            if ta.row_count == 0:
                empty_tables.append(table_name)
                ta.issues.append("Table is empty (0 rows)")

            date_col = _DATE_COLUMN_MAP.get(table_name)
            if date_col:
                ta.date_column = date_col
                ta.min_date, ta.max_date = _get_date_range(conn, table_name, date_col)

            null_cols = _NULL_CHECK_MAP.get(table_name)
            if null_cols:
                ta.null_rates = _get_null_rates(conn, table_name, null_cols)
                for col, rate in ta.null_rates.items():
                    if rate > 50:
                        ta.issues.append(f"High null rate: {col} = {rate}%")

            orm_only, pg_only = _get_column_diff(conn, table_name)
            ta.missing_orm_columns = orm_only
            ta.extra_pg_columns = pg_only
            if orm_only:
                ta.issues.append(f"ORM columns missing in PG: {orm_only}")
            if pg_only:
                ta.issues.append(f"PG columns not in ORM: {pg_only}")

            table_audits.append(ta)

    # Mask password in URL
    db_url = str(engine.url)
    if "@" in db_url:
        scheme, rest = db_url.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.rsplit("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                db_url = f"{scheme}://{user}:***@{host_part}"

    summary = {
        "total_orm_tables": len(orm_tables),
        "total_db_tables": len(db_tables),
        "missing_in_db": len(missing_in_db),
        "missing_in_orm": len(missing_in_orm),
        "empty_tables": len(empty_tables),
        "tables_with_issues": sum(1 for t in table_audits if t.issues),
    }

    return CompletenessReport(
        generated_at=datetime.now(UTC).isoformat(),
        database_url=db_url,
        total_orm_tables=len(orm_tables),
        total_db_tables=len(db_tables),
        missing_in_db=missing_in_db,
        missing_in_orm=missing_in_orm,
        empty_tables=empty_tables,
        table_audits=table_audits,
        summary=summary,
    )


def report_to_markdown(report: CompletenessReport) -> str:
    lines = [
        "# Database Completeness Audit Report",
        "",
        f"**Generated:** {report.generated_at}",
        f"**Database:** {report.database_url}",
        "",
        "## Summary",
        "",
        f"- ORM tables: {report.total_orm_tables}",
        f"- DB tables: {report.total_db_tables}",
        f"- Missing in DB: {report.summary['missing_in_db']}",
        f"- Missing in ORM: {report.summary['missing_in_orm']}",
        f"- Empty tables: {report.summary['empty_tables']}",
        f"- Tables with issues: {report.summary['tables_with_issues']}",
        "",
        "## Missing Tables (ORM → DB)",
        "",
    ]
    if report.missing_in_db:
        for t in report.missing_in_db:
            lines.append(f"- `{t}`")
    else:
        lines.append("None — all ORM tables exist in DB.")

    lines.extend(["", "## Extra Tables (DB → ORM)", ""])
    if report.missing_in_orm:
        for t in report.missing_in_orm:
            lines.append(f"- `{t}`")
    else:
        lines.append("None")

    lines.extend(["", "## Empty Tables", ""])
    if report.empty_tables:
        for t in report.empty_tables:
            lines.append(f"- `{t}`")
    else:
        lines.append("None")

    lines.extend(["", "## Table Details", "",
                  "| Table | Rows | Date Range | Issues |",
                  "|-------|------|------------|--------|"])
    for ta in report.table_audits:
        if not ta.exists_in_db:
            lines.append(f"| `{ta.table_name}` | — | — | MISSING |")
            continue
        dr = f"{ta.min_date} → {ta.max_date}" if ta.min_date else "—"
        issues = "; ".join(ta.issues) if ta.issues else "OK"
        rc = f"{ta.row_count:,}" if ta.row_count is not None else "—"
        lines.append(f"| `{ta.table_name}` | {rc} | {dr} | {issues} |")

    lines.extend(["", "## High Null Rates (>50%)", ""])
    for ta in report.table_audits:
        for col, rate in ta.null_rates.items():
            if rate > 50:
                lines.append(f"- `{ta.table_name}.{col}`: {rate}%")

    return "\n".join(lines)


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Database completeness audit")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("Running database completeness audit...")

    report = run_completeness_audit()

    if args.format == "json":
        output = json.dumps(
            {
                "generated_at": report.generated_at,
                "database_url": report.database_url,
                "summary": report.summary,
                "missing_in_db": report.missing_in_db,
                "missing_in_orm": report.missing_in_orm,
                "empty_tables": report.empty_tables,
                "table_audits": [
                    {
                        "table_name": ta.table_name,
                        "exists_in_db": ta.exists_in_db,
                        "row_count": ta.row_count,
                        "min_date": ta.min_date,
                        "max_date": ta.max_date,
                        "null_rates": ta.null_rates,
                        "missing_orm_columns": ta.missing_orm_columns,
                        "extra_pg_columns": ta.extra_pg_columns,
                        "issues": ta.issues,
                    }
                    for ta in report.table_audits
                ],
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    else:
        output = report_to_markdown(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        logger.info("Report written to %s", args.output)
    else:
        print(output)


if __name__ == "__main__":
    _main()
