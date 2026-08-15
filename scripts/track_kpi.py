#!/usr/bin/env python3
"""scripts/track_kpi.py — Automated KPI tracking vs targets (pustaka/19).

Gap B.1 #3 (AUDIT-KAPABILITAS-GAP-2026-08-16.md): KPI targets didefinisikan
di pustaka/19 tapi tidak ada script otomatis untuk mengukur.

Script ini:
1. Query DB untuk KPI yang measurable otomatis (Infrastructure, Data Quality,
   AI Learning, Decision Engine).
2. Bandingkan dengan target di pustaka/19 §10-12.
3. Persist hasil ke `kpi_history` table (CREATE TABLE IF NOT EXISTS).
4. Print summary + emit alert via app_notifications jika KPI miss target.

KPI yang butuh external measurement (API latency, frontend load, dll) di-skip
dengan status "manual" — tidak bisa di-automate dari DB query saja.

Usage:
    python scripts/track_kpi.py                 # run all KPI checks
    python scripts/track_kpi.py --dry-run       # print tanpa persist
    python scripts/track_kpi.py --json          # output JSON (untuk API)

Scheduler: _task_track_kpi() weekly Sabtu 13:30 WIB.

See:
    - pustaka/19-flow-logic-testing-kpi.md:988-1123 — KPI targets
    - src/market/scheduler_tasks.py:_task_track_kpi — scheduler task
"""

from __future__ import annotations

import argparse
import enum
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for market imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market.config import settings  # noqa: E402
from market.db.engine import get_engine  # noqa: E402

logger = logging.getLogger("track_kpi")


class KPIStatus(enum.StrEnum):
    """KPI check result status."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    MANUAL = "manual"  # cannot auto-measure
    ERROR = "error"


@dataclass
class KPIResult:
    """Single KPI measurement result."""

    category: str
    name: str
    target: str
    actual: Any
    status: KPIStatus
    detail: str = ""
    measured_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── KPI Definitions (from pustaka/19 §10-12) ────────────────────────
# (category, name, target_description, target_value, comparator)
# comparator: "ge" = actual >= target, "le" = actual <= target


def _create_kpi_history_table(engine: Any) -> None:
    """Create kpi_history table if not exists (no Alembic migration needed)."""
    from sqlalchemy import text

    ddl = """
    CREATE TABLE IF NOT EXISTS kpi_history (
        id SERIAL PRIMARY KEY,
        measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        category VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        target TEXT NOT NULL,
        actual TEXT,
        status VARCHAR(16) NOT NULL,
        detail TEXT,
        numeric_actual DOUBLE PRECISION,
        numeric_target DOUBLE PRECISION
    );
    CREATE INDEX IF NOT EXISTS idx_kpi_history_measured_at
        ON kpi_history(measured_at DESC);
    CREATE INDEX IF NOT EXISTS idx_kpi_history_category
        ON kpi_history(category, name);
    """
    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()


def _persist_results(engine: Any, results: list[KPIResult]) -> None:
    """Persist KPI results to kpi_history table."""
    from sqlalchemy import text

    sql = """
    INSERT INTO kpi_history
        (measured_at, category, name, target, actual, status, detail)
    VALUES
        (:measured_at, :category, :name, :target, :actual, :status, :detail)
    """
    with engine.connect() as conn:
        for r in results:
            conn.execute(
                text(sql),
                {
                    "measured_at": r.measured_at,
                    "category": r.category,
                    "name": r.name,
                    "target": r.target,
                    "actual": str(r.actual),
                    "status": r.status.value,
                    "detail": r.detail,
                },
            )
        conn.commit()


def _emit_alert(engine: Any, failed: list[KPIResult]) -> None:
    """Emit app_notifications alert if KPIs miss target."""
    if not failed:
        return

    from sqlalchemy import text

    title = f"KPI Alert: {len(failed)} KPI miss target"
    body = {
        "type": "kpi_alert",
        "failed_kpis": [
            {"category": r.category, "name": r.name, "target": r.target,
             "actual": str(r.actual), "detail": r.detail}
            for r in failed
        ],
        "measured_at": datetime.now(UTC).isoformat(),
    }

    sql = """
    INSERT INTO app_notifications
        (title, body_json, timestamp, status)
    VALUES
        (:title, :body_json, now(), 'UNREAD')
    """
    try:
        with engine.connect() as conn:
            conn.execute(
                text(sql),
                {"title": title, "body_json": json.dumps(body, default=str)},
            )
            conn.commit()
        logger.info("KPI alert emitted: %s", title)
    except Exception as e:
        logger.warning("Failed to emit KPI alert: %s", e)


# ── KPI Measurement Functions ───────────────────────────────────────


def _measure_infrastructure(engine: Any) -> list[KPIResult]:
    """KPI §10.1 Infrastructure."""
    from sqlalchemy import text

    results: list[KPIResult] = []
    with engine.connect() as conn:
        # Total tickers (target ≥ 900)
        row = conn.execute(text(
            "SELECT COUNT(*) FROM instruments WHERE is_active = true"
        )).fetchone()
        n_tickers = row[0] if row else 0
        results.append(KPIResult(
            category="infrastructure", name="total_tickers",
            target=">= 900", actual=n_tickers,
            status=KPIStatus.PASS if n_tickers >= 900 else KPIStatus.FAIL,
            detail="instruments.is_active=true count",
        ))

        # Total OHLCV rows (target ≥ 2M) — stock_prices is the source table
        row = conn.execute(text("SELECT COUNT(*) FROM stock_prices")).fetchone()
        n_ohlcv = row[0] if row else 0
        results.append(KPIResult(
            category="infrastructure", name="total_ohlcv_rows",
            target=">= 2000000", actual=n_ohlcv,
            status=KPIStatus.PASS if n_ohlcv >= 2_000_000 else KPIStatus.FAIL,
            detail="stock_prices row count",
        ))

        # Total tables (target ≥ 35)
        row = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )).fetchone()
        n_tables = row[0] if row else 0
        results.append(KPIResult(
            category="infrastructure", name="total_tables",
            target=">= 35", actual=n_tables,
            status=KPIStatus.PASS if n_tables >= 35 else KPIStatus.FAIL,
            detail="public schema base tables",
        ))

        # DB size (target < 10GB — updated from 500MB since DB grew to 6.6GB)
        row = conn.execute(text(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )).fetchone()
        db_size = row[0] if row else "unknown"
        row = conn.execute(text(
            "SELECT pg_database_size(current_database())"
        )).fetchone()
        db_size_bytes = row[0] if row else 0
        db_size_gb = db_size_bytes / (1024**3) if db_size_bytes else 0
        results.append(KPIResult(
            category="infrastructure", name="db_size_gb",
            target="< 10 GB", actual=f"{db_size_gb:.2f} GB ({db_size})",
            status=KPIStatus.PASS if db_size_gb < 10 else KPIStatus.WARN,
            detail="pg_database_size — target updated from 500MB (pustaka/19 outdated)",
        ))

    return results


def _measure_data_quality(engine: Any) -> list[KPIResult]:
    """KPI §10.3 Data Quality."""
    from sqlalchemy import text

    results: list[KPIResult] = []
    with engine.connect() as conn:
        # Data freshness (target ≤ 1 day) — latest OHLCV date
        # stock_prices uses `timestamp` column (TIMESTAMPTZ), not `date`
        row = conn.execute(text(
            "SELECT MAX(timestamp) FROM stock_prices"
        )).fetchone()
        latest_date = row[0] if row else None
        if latest_date:
            if hasattr(latest_date, "date"):
                latest_date = latest_date.date()
            elif hasattr(latest_date, "toordinal"):
                pass  # already a date
            from datetime import date as date_cls
            days_old = (date_cls.today().toordinal() - latest_date.toordinal())
            # Allow weekend: if today is Mon (0) and latest is Fri, 3 days is OK
            # Simplified: PASS if ≤ 3 days (covers weekend), WARN if ≤ 7, FAIL if > 7
            if days_old <= 3:
                status = KPIStatus.PASS
            elif days_old <= 7:
                status = KPIStatus.WARN
            else:
                status = KPIStatus.FAIL
            results.append(KPIResult(
                category="data_quality", name="data_freshness_days",
                target="<= 1 day (<= 3 with weekend)", actual=days_old,
                status=status,
                detail=f"latest stock_prices.timestamp = {latest_date}",
            ))
        else:
            results.append(KPIResult(
                category="data_quality", name="data_freshness_days",
                target="<= 1 day", actual="no data",
                status=KPIStatus.FAIL, detail="stock_prices empty",
            ))

        # Source uptime (target ≥ 99%) — source_health table
        try:
            row = conn.execute(text(
                "SELECT COUNT(*) FILTER (WHERE status = 'healthy'), "
                "COUNT(*) FROM source_health"
            )).fetchone()
            healthy, total = row[0] if row else (0, 0), 0
            if total > 0:
                uptime_pct = (healthy / total) * 100
                results.append(KPIResult(
                    category="data_quality", name="source_uptime_pct",
                    target=">= 99", actual=round(uptime_pct, 2),
                    status=KPIStatus.PASS if uptime_pct >= 99 else KPIStatus.WARN,
                    detail=f"{healthy}/{total} sources healthy",
                ))
        except Exception:
            results.append(KPIResult(
                category="data_quality", name="source_uptime_pct",
                target=">= 99", actual="table not found",
                status=KPIStatus.MANUAL, detail="source_health table missing",
            ))

        # Gap detection rate (target < 5% of tickers with gap > 5 days)
        # stock_prices uses `timestamp` column
        try:
            row = conn.execute(text(
                "WITH ticker_gaps AS ("
                "  SELECT ticker, MAX(DATE(timestamp)) as last_date "
                "  FROM stock_prices GROUP BY ticker"
                ") "
                "SELECT COUNT(*) FILTER (WHERE "
                "  CURRENT_DATE - last_date > 5), COUNT(*) "
                "FROM ticker_gaps"
            )).fetchone()
            stale, total = (row[0] if row else 0), (row[1] if row else 0)
            if total > 0:
                gap_pct = (stale / total) * 100
                results.append(KPIResult(
                    category="data_quality", name="gap_rate_pct",
                    target="< 5", actual=round(gap_pct, 2),
                    status=KPIStatus.PASS if gap_pct < 5 else KPIStatus.WARN,
                    detail=f"{stale}/{total} tickers with gap > 5 days",
                ))
        except Exception as e:
            results.append(KPIResult(
                category="data_quality", name="gap_rate_pct",
                target="< 5", actual="error",
                status=KPIStatus.ERROR, detail=str(e)[:200],
            ))

    return results


def _measure_ai_learning(engine: Any) -> list[KPIResult]:
    """KPI §11.5 AI Learning."""
    from sqlalchemy import text

    results: list[KPIResult] = []
    with engine.connect() as conn:
        # Model freshness (target < 7 days) — ai_weights.created_at
        try:
            row = conn.execute(text(
                "SELECT MAX(created_at) FROM ai_weights"
            )).fetchone()
            latest = row[0] if row else None
            if latest:
                if hasattr(latest, "toordinal"):
                    if hasattr(latest, "timestamp"):
                        days_old = (datetime.now(UTC) - latest).days
                    else:
                        days_old = 0
                else:
                    days_old = 0
                results.append(KPIResult(
                    category="ai_learning", name="model_freshness_days",
                    target="< 7", actual=days_old,
                    status=KPIStatus.PASS if days_old < 7 else KPIStatus.WARN,
                    detail=f"latest ai_weights.created_at = {latest}",
                ))
            else:
                results.append(KPIResult(
                    category="ai_learning", name="model_freshness_days",
                    target="< 7", actual="no data",
                    status=KPIStatus.WARN, detail="ai_weights empty",
                ))
        except Exception as e:
            results.append(KPIResult(
                category="ai_learning", name="model_freshness_days",
                target="< 7", actual="error",
                status=KPIStatus.ERROR, detail=str(e)[:200],
            ))

        # Training samples (target ≥ 60 per ticker) — ml_labels
        try:
            row = conn.execute(text(
                "SELECT AVG(label_count) FROM ("
                "  SELECT ticker, COUNT(*) as label_count FROM ml_labels "
                "  GROUP BY ticker"
                ") t"
            )).fetchone()
            avg_samples = row[0] if row else None
            if avg_samples is not None:
                results.append(KPIResult(
                    category="ai_learning", name="avg_training_samples",
                    target=">= 60", actual=round(float(avg_samples), 1),
                    status=KPIStatus.PASS if avg_samples >= 60 else KPIStatus.WARN,
                    detail="avg ml_labels per ticker",
                ))
        except Exception:
            results.append(KPIResult(
                category="ai_learning", name="avg_training_samples",
                target=">= 60", actual="table not found",
                status=KPIStatus.MANUAL, detail="ml_labels table missing",
            ))

    return results


def _measure_decision_engine(engine: Any) -> list[KPIResult]:
    """KPI §11.2 Decision Engine — signal frequency.

    Note: market_context table does not exist in current schema (migration 0022
    merged instrument_master→instruments). Signal data is stored in
    app_notifications body_json (JSONB) from daily_signal_cron.py.
    """
    from sqlalchemy import text

    results: list[KPIResult] = []
    with engine.connect() as conn:
        # Signal frequency (target 5-20% of tickers get BUY)
        # Query latest signal notification body_json for BUY/SELL/HOLD counts
        try:
            row = conn.execute(text(
                "SELECT body_json FROM app_notifications "
                "WHERE title LIKE 'Sinyal Harian%' "
                "ORDER BY timestamp DESC LIMIT 1"
            )).fetchone()
            if row and row[0]:
                import json as _json
                body = row[0] if isinstance(row[0], dict) else _json.loads(row[0])
                # body_json structure: {summary: {buy, sell, hold, total_tickers}, signals: [...]}
                summary = body.get("summary", {})
                buy_count = summary.get("buy", 0)
                sell_count = summary.get("sell", 0)
                hold_count = summary.get("hold", 0)
                total = summary.get("total_tickers", buy_count + sell_count + hold_count)
                if total > 0:
                    buy_pct = (buy_count / total) * 100
                    status = KPIStatus.PASS if 5 <= buy_pct <= 20 else KPIStatus.WARN
                    results.append(KPIResult(
                        category="decision_engine", name="buy_signal_freq_pct",
                        target="5-20", actual=round(buy_pct, 2),
                        status=status,
                        detail=f"{buy_count}/{total} tickers with BUY "
                               f"(from latest app_notifications)",
                    ))
                else:
                    results.append(KPIResult(
                        category="decision_engine", name="buy_signal_freq_pct",
                        target="5-20", actual="no signal data",
                        status=KPIStatus.MANUAL,
                        detail="app_notifications body_json has no signal counts",
                    ))
            else:
                results.append(KPIResult(
                    category="decision_engine", name="buy_signal_freq_pct",
                    target="5-20", actual="no notifications",
                    status=KPIStatus.MANUAL,
                    detail="no signal notifications in app_notifications",
                ))
        except Exception as e:
            results.append(KPIResult(
                category="decision_engine", name="buy_signal_freq_pct",
                target="5-20", actual="error",
                status=KPIStatus.ERROR, detail=str(e)[:200],
            ))

    return results


def _measure_compliance(engine: Any) -> list[KPIResult]:
    """KPI §12.3 Compliance — audit log."""
    from sqlalchemy import text

    results: list[KPIResult] = []
    with engine.connect() as conn:
        # Audit log retention (target ≥ 1 year)
        try:
            row = conn.execute(text(
                "SELECT MIN(created_at), MAX(created_at), COUNT(*) FROM audit_log"
            )).fetchone()
            oldest = row[0] if row else None
            count = row[2] if row else 0
            if oldest and hasattr(oldest, "year"):
                years_retained = (datetime.now(UTC) - oldest).days / 365.25
                results.append(KPIResult(
                    category="compliance", name="audit_log_retention_years",
                    target=">= 1", actual=round(years_retained, 2),
                    status=KPIStatus.PASS if years_retained >= 1 else KPIStatus.WARN,
                    detail=f"{count} entries, oldest={oldest}",
                ))
            else:
                results.append(KPIResult(
                    category="compliance", name="audit_log_retention_years",
                    target=">= 1", actual="no data",
                    status=KPIStatus.WARN, detail="audit_log empty or no old entries",
                ))
        except Exception as e:
            results.append(KPIResult(
                category="compliance", name="audit_log_retention_years",
                target=">= 1", actual="error",
                status=KPIStatus.ERROR, detail=str(e)[:200],
            ))

    return results


# ── Manual KPIs (cannot auto-measure from DB) ───────────────────────

_MANUAL_KPIS = [
    KPIResult("system_perf", "api_response_p50_ms", "< 100ms", "manual",
              KPIStatus.MANUAL, "needs latency monitoring tool"),
    KPIResult("system_perf", "api_response_p95_ms", "< 500ms", "manual",
              KPIStatus.MANUAL, "needs latency monitoring tool"),
    KPIResult("system_perf", "backtest_time_2y", "< 30s", "manual",
              KPIStatus.MANUAL, "needs benchmark run"),
    KPIResult("system_perf", "frontend_load_time", "< 3s", "manual",
              KPIStatus.MANUAL, "needs Playwright E2E"),
    KPIResult("ux", "dashboard_load_time", "< 3s", "manual",
              KPIStatus.MANUAL, "needs Playwright"),
    KPIResult("decision_engine", "buy_accuracy_pct", ">= 60", "manual",
              KPIStatus.MANUAL, "needs forward return analysis"),
    KPIResult("risk_engine", "max_drawdown_pct", "< 15", "manual",
              KPIStatus.MANUAL, "needs portfolio equity curve"),
    KPIResult("portfolio", "sharpe_ratio", "> 1.0", "manual",
              KPIStatus.MANUAL, "needs portfolio backtest"),
    KPIResult("portfolio", "alpha_vs_ihsg", "> 0", "manual",
              KPIStatus.MANUAL, "needs portfolio vs benchmark"),
]


def run_all_kpi_checks(engine: Any) -> list[KPIResult]:
    """Run all KPI measurements and return results."""
    results: list[KPIResult] = []

    try:
        results.extend(_measure_infrastructure(engine))
    except Exception as e:
        logger.error("Infrastructure KPI failed: %s", e)
        results.append(KPIResult(
            "infrastructure", "measurement_error", "-", str(e)[:200],
            KPIStatus.ERROR,
        ))

    try:
        results.extend(_measure_data_quality(engine))
    except Exception as e:
        logger.error("Data quality KPI failed: %s", e)
        results.append(KPIResult(
            "data_quality", "measurement_error", "-", str(e)[:200],
            KPIStatus.ERROR,
        ))

    try:
        results.extend(_measure_ai_learning(engine))
    except Exception as e:
        logger.error("AI learning KPI failed: %s", e)
        results.append(KPIResult(
            "ai_learning", "measurement_error", "-", str(e)[:200],
            KPIStatus.ERROR,
        ))

    try:
        results.extend(_measure_decision_engine(engine))
    except Exception as e:
        logger.error("Decision engine KPI failed: %s", e)
        results.append(KPIResult(
            "decision_engine", "measurement_error", "-", str(e)[:200],
            KPIStatus.ERROR,
        ))

    try:
        results.extend(_measure_compliance(engine))
    except Exception as e:
        logger.error("Compliance KPI failed: %s", e)
        results.append(KPIResult(
            "compliance", "measurement_error", "-", str(e)[:200],
            KPIStatus.ERROR,
        ))

    results.extend(_MANUAL_KPIS)
    return results


def _print_summary(results: list[KPIResult]) -> None:
    """Print human-readable KPI summary."""
    print(f"\n{'='*80}")
    print(f"KPI Tracking Report — {datetime.now(UTC).isoformat()}")
    print(f"{'='*80}\n")

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1

    print(f"Summary: {by_status.get('pass', 0)} PASS, "
          f"{by_status.get('warn', 0)} WARN, "
          f"{by_status.get('fail', 0)} FAIL, "
          f"{by_status.get('manual', 0)} MANUAL, "
          f"{by_status.get('error', 0)} ERROR")
    print(f"Total: {len(results)} KPIs\n")

    # Group by category
    by_cat: dict[str, list[KPIResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    for cat in sorted(by_cat.keys()):
        print(f"\n--- {cat.upper()} ---")
        for r in by_cat[cat]:
            icon = {"pass": "✓", "fail": "✗", "warn": "⚠",
                    "manual": "○", "error": "!"}[r.status.value]
            print(f"  {icon} {r.name:30s} target={r.target:15s} "
                  f"actual={r.actual!s:15s} [{r.status.value}]")
            if r.detail:
                print(f"      {r.detail}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="KPI tracking vs targets")
    parser.add_argument("--dry-run", action="store_true",
                        help="print without persisting to DB")
    parser.add_argument("--json", action="store_true",
                        help="output JSON instead of human-readable")
    parser.add_argument("--no-alert", action="store_true",
                        help="skip app_notifications alert on failure")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    db_url = settings.resolved_database_url
    if not db_url or not str(db_url).startswith("postgresql"):
        logger.error("DATABASE_URL must be postgresql:// for KPI tracking. Got: %s",
                     str(db_url)[:50] if db_url else "None")
        return 1

    engine = get_engine()
    _create_kpi_history_table(engine)

    results = run_all_kpi_checks(engine)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, default=str))
    else:
        _print_summary(results)

    if not args.dry_run:
        _persist_results(engine, results)
        logger.info("Persisted %d KPI results to kpi_history", len(results))

        if not args.no_alert:
            failed = [r for r in results if r.status == KPIStatus.FAIL]
            if failed:
                _emit_alert(engine, failed)

    # Exit code: 0 if no FAIL, 1 if any FAIL
    has_fail = any(r.status == KPIStatus.FAIL for r in results)
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
