"""Update tracking markers for all recompute functions and data tables.

Populates:
1. recompute_dependencies: next_run_at, previous_run_at, last_data_changed_at,
   recommendation, recommendation_reason
2. recompute_watermark: per-ticker watermark for all recompute output tables
3. data_watermark: per-ticker per-table freshness with previous_updated,
   next_check_at, change_detected

Run this after recompute cycles or data fetches to keep tracking current.
The smart skip logic in RecomputeEstimator reads these markers to decide
whether to skip or run a function.

Usage:
    uv run python scripts/update_tracking.py [--populate-watermarks]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from market.db.engine import get_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Recompute schedule intervals (hours between runs)
RECOMPUTE_INTERVALS: dict[str, float] = {
    "recompute_technical_indicators": 24.0,
    "recompute_scores": 24.0,
    "recompute_relationship_matrix": 48.0,
    "recompute_fear_greed": 6.0,
    "recompute_stock_personality": 168.0,  # weekly
    "recompute_ml_labels": 24.0,
    "recompute_market_regimes": 24.0,
    "recompute_weights": 168.0,  # weekly
    "recompute_holiday_effects": 720.0,  # monthly
    "recompute_instrument_profiles": 168.0,  # weekly
    "recompute_cross_market_coefficients": 168.0,
    "recompute_dcc_garch": 720.0,  # monthly
    "recompute_seasonal_patterns": 720.0,
    "recompute_macro_correlation": 168.0,
    "recompute_causal_relationships": 168.0,
    "recompute_satellite_correlation": 720.0,
    "recompute_astronacci_cycles": 24.0,
    "recompute_cross_market": 48.0,
}

# Output table per recompute function
RECOMPUTE_OUTPUT_TABLES: dict[str, str] = {
    "recompute_technical_indicators": "technical_indicators",
    "recompute_scores": "scores",
    "recompute_relationship_matrix": "relationship_matrix",
    "recompute_fear_greed": "fear_greed",
    "recompute_stock_personality": "stock_personality",
    "recompute_ml_labels": "ml_labels",
    "recompute_market_regimes": "market_regimes",
    "recompute_weights": "signal_weights",
    "recompute_holiday_effects": "holiday_effects",
    "recompute_instrument_profiles": "instrument_behavior_profiles",
    "recompute_cross_market_coefficients": "cross_market_coefficients",
    "recompute_dcc_garch": "dcc_garch_results",
    "recompute_seasonal_patterns": "seasonal_patterns",
    "recompute_macro_correlation": "causal_relationships",
    "recompute_causal_relationships": "causal_relationships",
    "recompute_satellite_correlation": "satellite_correlation_results",
    "recompute_astronacci_cycles": "astronacci_cycles",
}

# Data source tables to track freshness
DATA_TABLES_TO_TRACK: list[tuple[str, str]] = [
    # (table_name, timestamp_column)
    ("ohlcv", "timestamp"),
    ("stock_prices_default", "timestamp"),
    ("fundamental_data", "date"),
    ("macro_data", "date"),
    ("foreign_flow", "date"),
    ("fear_greed", "date"),
    ("news", "published_at"),
    ("news_sentiment", "published_at"),
    ("policy_events", "event_date"),
    ("external_events", "tanggal"),
    ("exchange_holidays", "holiday_date"),
    ("earnings_calendar", "report_date"),
    ("satellite_observations", "observed_at"),
    ("broker_flow", "date"),
    ("broker_transactions", "date"),
    ("corporate_actions", "ex_date"),
    ("dividends", "ex_date"),
    ("esg_scores", "updated_at"),
    ("corporate_governance", "updated_at"),
    ("market_sessions", "session_start"),
    ("market_regimes", "date"),
    ("ml_labels", "date"),
    ("scores", "as_of"),
    ("relationship_matrix", "as_of"),
    ("technical_indicators", "date"),
    ("technical_indicators_wide", "date"),
    ("stock_personality", "updated_at"),
    ("signal_weights", "updated_at"),
    ("holiday_effects", "created_at"),
    ("astronacci_cycles", "created_at"),
    ("seasonal_patterns", "created_at"),
    ("cross_market_coefficients", "created_at"),
    ("causal_relationships", "created_at"),
    ("dcc_garch_results", "created_at"),
    ("instrument_behavior_profiles", "updated_at"),
    ("daily_risk_metrics", "date"),
    ("daily_trading_stats", "date"),
    ("valuation_cache", "as_of"),
    ("pattern_analysis", "created_at"),
    ("market_influence_kb", "created_at"),
]


def _get_max_timestamp(session: Session, table: str, ts_col: str) -> datetime | None:
    """Get MAX(timestamp_col) from a table safely."""
    try:
        result = session.execute(text(f"SELECT MAX({ts_col}) FROM {table}")).scalar()
        if result is None:
            result = session.execute(
                text(f"SELECT MAX(created_at) FROM {table}")
            ).scalar()
        return result
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        return None


def _get_row_count(session: Session, table: str) -> int:
    """Get row count from a table safely."""
    try:
        return session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        return 0


def update_recompute_dependencies(session: Session) -> dict:
    """Update next_run_at, previous_run_at, last_data_changed_at, recommendation."""
    now = datetime.now(UTC)
    updated = 0
    errors = 0

    rows = session.execute(
        text(
            "SELECT id, function_name, data_source, last_run_at, run_count "
            "FROM recompute_dependencies"
        )
    ).all()

    for row in rows:
        dep_id, fn_name, data_source, last_run_at, run_count = row

        # Get previous run (second-to-last)
        previous_run_at = None
        if last_run_at is not None:
            try:
                prev = session.execute(
                    text(
                        "SELECT MAX(started_at) FROM recompute_run_stats "
                        "WHERE function_name = :fn AND started_at < :last "
                        "AND status = 'completed'"
                    ),
                    {"fn": fn_name, "last": last_run_at},
                ).scalar()
                previous_run_at = prev
            except Exception:
                session.rollback()

        # Get last data change time for the source table
        last_data_changed_at = _get_max_timestamp(session, data_source, "timestamp")
        if last_data_changed_at is None:
            last_data_changed_at = _get_max_timestamp(session, data_source, "date")
        if last_data_changed_at is None:
            last_data_changed_at = _get_max_timestamp(session, data_source, "updated_at")
        if last_data_changed_at is None:
            last_data_changed_at = _get_max_timestamp(session, data_source, "created_at")

        # Calculate next_run_at based on interval
        interval_h = RECOMPUTE_INTERVALS.get(fn_name, 24.0)
        if last_run_at is not None:
            if isinstance(last_run_at, str):
                last_run_at = datetime.fromisoformat(last_run_at)
            next_run_at = last_run_at + timedelta(hours=interval_h)
        else:
            next_run_at = now  # never run → should run now

        # Generate recommendation
        recommendation, reason = _generate_recommendation(
            fn_name, last_run_at, last_data_changed_at, next_run_at, now, run_count or 0
        )

        try:
            session.execute(
                text(
                    "UPDATE recompute_dependencies SET "
                    "next_run_at = :next_run, "
                    "previous_run_at = :prev_run, "
                    "last_data_changed_at = :data_changed, "
                    "recommendation = :rec, "
                    "recommendation_reason = :reason "
                    "WHERE id = :id"
                ),
                {
                    "next_run": next_run_at,
                    "prev_run": previous_run_at,
                    "data_changed": last_data_changed_at,
                    "rec": recommendation,
                    "reason": reason,
                    "id": dep_id,
                },
            )
            updated += 1
            session.commit()
        except Exception as e:
            logger.error("Failed to update dep %s: %s", dep_id, e)
            session.rollback()
            errors += 1
            continue

    session.commit()
    return {"updated": updated, "errors": errors}


def _generate_recommendation(
    fn_name: str,
    last_run_at: datetime | None,
    last_data_changed_at: datetime | None,
    next_run_at: datetime,
    now: datetime,
    run_count: int,
) -> tuple[str, str]:
    """Generate recommendation and reason for a recompute function."""

    if run_count == 0 or last_run_at is None:
        return "RUN_NOW", "Never been run — initial execution needed"

    if isinstance(last_run_at, str):
        last_run_at = datetime.fromisoformat(last_run_at)
    if isinstance(last_run_at, date) and not isinstance(last_run_at, datetime):
        last_run_at = datetime.combine(last_run_at, datetime.min.time(), tzinfo=UTC)
    if isinstance(last_run_at, datetime) and last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=UTC)

    hours_since_run = (now - last_run_at).total_seconds() / 3600

    # Check if data changed after last run
    if last_data_changed_at is not None:
        if isinstance(last_data_changed_at, str):
            last_data_changed_at = datetime.fromisoformat(last_data_changed_at)
        if isinstance(last_data_changed_at, date) and not isinstance(last_data_changed_at, datetime):
            last_data_changed_at = datetime.combine(last_data_changed_at, datetime.min.time(), tzinfo=UTC)
        if last_data_changed_at.tzinfo is None:
            last_data_changed_at = last_data_changed_at.replace(tzinfo=UTC)

        if last_data_changed_at > last_run_at:
            return "RUN_NOW", f"Input data changed at {last_data_changed_at.isoformat()} after last run at {last_run_at.isoformat()}"

    # Check if next_run_at has passed
    if isinstance(next_run_at, str):
        next_run_at = datetime.fromisoformat(next_run_at)
    if next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=UTC)

    if now >= next_run_at:
        return "RUN_NOW", f"Scheduled next_run_at {next_run_at.isoformat()} has passed"

    hours_until_next = (next_run_at - now).total_seconds() / 3600
    if hours_until_next < 2:
        return "RUN_SOON", f"Next run in {hours_until_next:.1f}h (at {next_run_at.isoformat()})"

    return "SKIP", f"Data fresh — next run at {next_run_at.isoformat()} ({hours_until_next:.1f}h remaining)"


def update_data_watermarks(session: Session) -> dict:
    """Update data_watermark for all tracked tables."""
    now = datetime.now(UTC)
    updated = 0
    errors = 0

    for table_name, ts_col in DATA_TABLES_TO_TRACK:
        try:
            max_ts = _get_max_timestamp(session, table_name, ts_col)
            row_count = _get_row_count(session, table_name)

            if row_count == 0:
                continue

            # Get existing watermark for comparison
            existing = session.execute(
                text(
                    "SELECT last_updated, row_count FROM data_watermark "
                    "WHERE table_name = :tbl AND ticker = '__table__'"
                ),
                {"tbl": table_name},
            ).first()

            previous_updated = None
            change_detected = False

            if existing:
                old_ts, old_count = existing
                if old_ts:
                    if isinstance(old_ts, str):
                        old_ts = datetime.fromisoformat(old_ts)
                    previous_updated = old_ts
                    if max_ts and old_ts and max_ts != old_ts:
                        change_detected = True
                    elif row_count != old_count:
                        change_detected = True

            # Next check: 6 hours for high-frequency tables, 24h for others
            if table_name in ("ohlcv", "stock_prices_default", "fear_greed", "market_sessions"):
                next_check = now + timedelta(hours=6)
            elif table_name in ("ml_labels", "scores", "technical_indicators"):
                next_check = now + timedelta(hours=12)
            else:
                next_check = now + timedelta(hours=24)

            # Upsert
            session.execute(
                text(
                    "INSERT INTO data_watermark "
                    "(ticker, table_name, last_updated, row_count, source, "
                    " previous_updated, next_check_at, change_detected) "
                    "VALUES ('__table__', :tbl, :max_ts, :count, 'update_tracking', "
                    " :prev_ts, :next_check, :changed) "
                    "ON CONFLICT (ticker, table_name) DO UPDATE SET "
                    "previous_updated = EXCLUDED.previous_updated, "
                    "last_updated = EXCLUDED.last_updated, "
                    "row_count = EXCLUDED.row_count, "
                    "next_check_at = EXCLUDED.next_check_at, "
                    "change_detected = EXCLUDED.change_detected"
                ),
                {
                    "tbl": table_name,
                    "max_ts": max_ts,
                    "count": row_count,
                    "prev_ts": previous_updated,
                    "next_check": next_check,
                    "changed": change_detected,
                },
            )
            updated += 1
            session.commit()
        except Exception as e:
            logger.debug("data_watermark skip %s: %s", table_name, e)
            try:
                session.rollback()
            except Exception:
                pass
            errors += 1

    session.commit()
    return {"updated": updated, "errors": errors}


def populate_recompute_watermarks(session: Session) -> dict:
    """Populate recompute_watermark for all recompute output tables.

    For each output table, finds the max date per ticker and stores it
    as the watermark so incremental recompute can skip already-processed data.
    """
    populated = 0
    errors = 0

    for fn_name, output_table in RECOMPUTE_OUTPUT_TABLES.items():
        try:
            # Determine the date/timestamp column
            date_col = "date"
            if output_table in ("scores", "relationship_matrix", "valuation_cache"):
                date_col = "as_of"
            elif output_table in ("stock_personality", "signal_weights",
                                  "instrument_behavior_profiles", "esg_scores"):
                date_col = "updated_at"
            elif output_table in ("holiday_effects", "astronacci_cycles",
                                  "seasonal_patterns", "cross_market_coefficients",
                                  "causal_relationships", "dcc_garch_results"):
                date_col = "created_at"
            elif output_table == "satellite_correlation_results":
                date_col = "created_at"

            # Check if table has ticker column
            has_ticker = session.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :tbl AND column_name = 'ticker' LIMIT 1"
                ),
                {"tbl": output_table},
            ).first()

            if not has_ticker:
                continue

            # Get max date per ticker
            rows = session.execute(
                text(
                    f"SELECT ticker, MAX({date_col}) as max_date, count(*) as cnt "
                    f"FROM {output_table} GROUP BY ticker"
                )
            ).all()

            for ticker, max_date, cnt in rows:
                if max_date is None:
                    continue

                session.execute(
                    text(
                        "INSERT INTO recompute_watermark "
                        "(ticker, table_name, last_processed_date, last_ohlcv_date, "
                        " rows_processed, updated_at) "
                        "VALUES (:ticker, :tbl, :max_date, :max_date, :cnt, :now) "
                        "ON CONFLICT (ticker, table_name) DO UPDATE SET "
                        "last_processed_date = EXCLUDED.last_processed_date, "
                        "last_ohlcv_date = EXCLUDED.last_ohlcv_date, "
                        "rows_processed = EXCLUDED.rows_processed, "
                        "updated_at = EXCLUDED.updated_at"
                    ),
                    {
                        "ticker": ticker,
                        "tbl": output_table,
                        "max_date": max_date,
                        "cnt": cnt,
                        "now": datetime.now(UTC),
                    },
                )
                populated += 1
                session.commit()

        except Exception as e:
            logger.debug("watermark skip %s/%s: %s", fn_name, output_table, e)
            try:
                session.rollback()
            except Exception:
                pass
            errors += 1

    session.commit()
    return {"populated": populated, "errors": errors}


def print_status_report(session: Session) -> None:
    """Print a status report of all tracking markers."""
    print("\n" + "=" * 100)
    print("RECOMPUTE DEPENDENCIES — TRACKING STATUS")
    print("=" * 100)
    print(f"{'Function':<40} {'Last Run':<22} {'Prev Run':<22} {'Next Run':<22} {'Data Changed':<22} {'Recommendation'}")
    print("-" * 180)

    rows = session.execute(
        text(
            "SELECT function_name, last_run_at, previous_run_at, next_run_at, "
            "last_data_changed_at, recommendation, recommendation_reason "
            "FROM recompute_dependencies ORDER BY function_name"
        )
    ).all()

    for fn, last_run, prev_run, next_run, data_changed, rec, reason in rows:
        last_str = last_run.strftime("%Y-%m-%d %H:%M") if last_run else "NEVER"
        prev_str = prev_run.strftime("%Y-%m-%d %H:%M") if prev_run else "—"
        next_str = next_run.strftime("%Y-%m-%d %H:%M") if next_run else "—"
        changed_str = data_changed.strftime("%Y-%m-%d %H:%M") if data_changed else "—"
        rec_str = rec or "—"
        print(f"{fn:<40} {last_str:<22} {prev_str:<22} {next_str:<22} {changed_str:<22} {rec_str}")

    print(f"\nTotal functions: {len(rows)}")

    # Summary
    run_now = sum(1 for r in rows if r[5] == "RUN_NOW")
    run_soon = sum(1 for r in rows if r[5] == "RUN_SOON")
    skip = sum(1 for r in rows if r[5] == "SKIP")
    never = sum(1 for r in rows if r[1] is None)
    print(f"  RUN_NOW: {run_now}  |  RUN_SOON: {run_soon}  |  SKIP: {skip}  |  NEVER RUN: {never}")

    # Data watermark summary
    print("\n" + "=" * 100)
    print("DATA WATERMARK — TABLE FRESHNESS")
    print("=" * 100)
    print(f"{'Table':<40} {'Last Updated':<22} {'Prev Updated':<22} {'Rows':>10} {'Changed':>8} {'Next Check'}")
    print("-" * 130)

    dw_rows = session.execute(
        text(
            "SELECT table_name, last_updated, previous_updated, row_count, "
            "change_detected, next_check_at "
            "FROM data_watermark WHERE ticker = '__table__' ORDER BY table_name"
        )
    ).all()

    for tbl, last_upd, prev_upd, count, changed, next_check in dw_rows:
        last_str = last_upd.strftime("%Y-%m-%d %H:%M") if last_upd else "—"
        prev_str = prev_upd.strftime("%Y-%m-%d %H:%M") if prev_upd else "—"
        changed_str = "YES" if changed else "no"
        next_str = next_check.strftime("%Y-%m-%d %H:%M") if next_check else "—"
        print(f"{tbl:<40} {last_str:<22} {prev_str:<22} {count:>10} {changed_str:>8} {next_str}")

    print(f"\nTotal tables tracked: {len(dw_rows)}")

    # Recompute watermark summary
    print("\n" + "=" * 100)
    print("RECOMPUTE WATERMARK — PER-TICKER PROGRESS")
    print("=" * 100)

    wm_rows = session.execute(
        text(
            "SELECT table_name, count(*) as tickers, "
            "min(last_processed_date) as oldest, max(last_processed_date) as newest, "
            "max(updated_at) as last_update "
            "FROM recompute_watermark GROUP BY table_name ORDER BY table_name"
        )
    ).all()

    print(f"{'Table':<40} {'Tickers':>8} {'Oldest Date':<14} {'Newest Date':<14} {'Last Update'}")
    print("-" * 100)
    for tbl, tickers, oldest, newest, last_upd in wm_rows:
        oldest_str = str(oldest) if oldest else "—"
        newest_str = str(newest) if newest else "—"
        last_str = last_upd.strftime("%Y-%m-%d %H:%M") if last_upd else "—"
        print(f"{tbl:<40} {tickers:>8} {oldest_str:<14} {newest_str:<14} {last_str}")

    print(f"\nTotal watermark entries: {sum(r[1] for r in wm_rows)} across {len(wm_rows)} tables")


def main():
    parser = argparse.ArgumentParser(description="Update tracking markers")
    parser.add_argument(
        "--populate-watermarks", action="store_true",
        help="Also populate recompute_watermark for all output tables",
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Only print status report without updating",
    )
    args = parser.parse_args()

    session = get_sessionmaker()()

    try:
        if not args.report_only:
            print("Updating recompute_dependencies tracking...")
            result = update_recompute_dependencies(session)
            print(f"  Updated: {result['updated']}, Errors: {result['errors']}")

            print("\nUpdating data_watermark freshness...")
            result = update_data_watermarks(session)
            print(f"  Updated: {result['updated']}, Errors: {result['errors']}")

            if args.populate_watermarks:
                print("\nPopulating recompute_watermark per-ticker...")
                result = populate_recompute_watermarks(session)
                print(f"  Populated: {result['populated']}, Errors: {result['errors']}")

        print_status_report(session)

    finally:
        session.close()


if __name__ == "__main__":
    main()
