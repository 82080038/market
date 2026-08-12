"""Migrate missing tables from SQLite to PostgreSQL.

Migrates 18 tables that exist in SQLite but not (or empty) in PostgreSQL,
in priority order. Uses psycopg2.extras.execute_values for bulk inserts.

Usage:
    python scripts/migrate_sqlite_to_pg_tables.py --all
    python scripts/migrate_sqlite_to_pg_tables.py --p1          # critical for S2
    python scripts/migrate_sqlite_to_pg_tables.py --p2          # recompute pipeline
    python scripts/migrate_sqlite_to_pg_tables.py --p3          # supporting
    python scripts/migrate_sqlite_to_pg_tables.py --table ml_labels
    python scripts/migrate_sqlite_to_pg_tables.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import sqlite3

from market.config import settings

logger = logging.getLogger(__name__)

SQLITE_PATH = "data/market_research.db"

# ─── DDL for PG tables ──────────────────────────────────────────────────────

DDL_STATEMENTS: dict[str, str] = {
    "ml_labels": """
        CREATE TABLE IF NOT EXISTS ml_labels (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            date DATE NOT NULL,
            horizon INTEGER NOT NULL,
            direction VARCHAR(10) NOT NULL,
            barrier_hit VARCHAR(20),
            return_pct NUMERIC(10,4),
            vol_adjusted_return NUMERIC(10,4),
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(ticker, date, horizon)
        );
        CREATE INDEX IF NOT EXISTS ix_mllabel_ticker_date ON ml_labels(ticker, date);
        CREATE INDEX IF NOT EXISTS ix_ml_labels_ticker ON ml_labels(ticker);
        CREATE INDEX IF NOT EXISTS ix_ml_labels_date ON ml_labels(date);
    """,
    "relationship_matrix": """
        CREATE TABLE IF NOT EXISTS relationship_matrix (
            id BIGSERIAL PRIMARY KEY,
            asset_a VARCHAR(30) NOT NULL,
            asset_b VARCHAR(30) NOT NULL,
            "window" INTEGER NOT NULL,
            correlation NUMERIC(10,6),
            lag INTEGER,
            as_of TIMESTAMPTZ,
            UNIQUE(asset_a, asset_b, "window")
        );
        CREATE INDEX IF NOT EXISTS ix_rel_a ON relationship_matrix(asset_a);
        CREATE INDEX IF NOT EXISTS ix_rel_b ON relationship_matrix(asset_b);
    """,
    "scores": """
        CREATE TABLE IF NOT EXISTS scores (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            engine VARCHAR(50) NOT NULL,
            score NUMERIC(5,2) NOT NULL,
            breakdown TEXT,
            as_of TIMESTAMPTZ,
            created_at TIMESTAMPTZ,
            UNIQUE(ticker, engine, as_of)
        );
        CREATE INDEX IF NOT EXISTS ix_score_ticker ON scores(ticker);
    """,
    "policy_events": """
        CREATE TABLE IF NOT EXISTS policy_events (
            id BIGSERIAL PRIMARY KEY,
            tanggal DATE NOT NULL,
            kategori VARCHAR(50),
            judul VARCHAR(500),
            instansi VARCHAR(200),
            dampak VARCHAR(30),
            sektor VARCHAR(200),
            deskripsi TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_policy_events_tanggal ON policy_events(tanggal);
    """,
    "external_events": """
        CREATE TABLE IF NOT EXISTS external_events (
            id BIGSERIAL PRIMARY KEY,
            tanggal DATE NOT NULL,
            kategori VARCHAR(50),
            judul VARCHAR(500),
            lokasi VARCHAR(200),
            dampak_market VARCHAR(30),
            sektor VARCHAR(200),
            deskripsi TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_external_events_tanggal ON external_events(tanggal);
    """,
    "recompute_watermark": """
        CREATE TABLE IF NOT EXISTS recompute_watermark (
            ticker VARCHAR(20) NOT NULL,
            table_name VARCHAR(50) NOT NULL,
            last_processed_date DATE,
            last_ohlcv_date DATE,
            rows_processed INTEGER,
            updated_at TIMESTAMPTZ,
            PRIMARY KEY(ticker, table_name)
        );
        CREATE INDEX IF NOT EXISTS ix_recompute_watermark_table ON recompute_watermark(table_name);
    """,
    "technical_indicators_wide": """
        CREATE TABLE IF NOT EXISTS technical_indicators_wide (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            date DATE NOT NULL,
            timeframe VARCHAR(10) DEFAULT '1d',
            ma20 NUMERIC(20,6),
            ma50 NUMERIC(20,6),
            rsi NUMERIC(20,6),
            macd NUMERIC(20,6),
            macd_signal NUMERIC(20,6),
            adx NUMERIC(20,6),
            atr14 NUMERIC(20,6),
            bb_upper NUMERIC(20,6),
            bb_lower NUMERIC(20,6),
            volume_sma20 NUMERIC(20,6),
            ema50 NUMERIC(20,6),
            ema_env_upper NUMERIC(20,6),
            ema_env_lower NUMERIC(20,6),
            donchian_upper NUMERIC(20,6),
            donchian_lower NUMERIC(20,6),
            donchian_mid NUMERIC(20,6),
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(ticker, date, timeframe)
        );
        CREATE INDEX IF NOT EXISTS ix_tiw_ticker_date ON technical_indicators_wide(ticker, date);
        CREATE INDEX IF NOT EXISTS ix_tiw_date ON technical_indicators_wide(date);
        CREATE INDEX IF NOT EXISTS ix_tiw_ticker ON technical_indicators_wide(ticker);
    """,
    "stock_prediction": """
        CREATE TABLE IF NOT EXISTS stock_prediction (
            ticker VARCHAR(30) PRIMARY KEY,
            predicted_direction VARCHAR(10),
            predicted_price NUMERIC(15,2),
            predicted_return_pct NUMERIC(8,4),
            prediction_confidence NUMERIC(5,3),
            ml_signal NUMERIC(6,4),
            multifactor_signal NUMERIC(6,4),
            composite_signal NUMERIC(6,4),
            factors_summary TEXT,
            prediction_updated_at TIMESTAMPTZ
        );
    """,
    "render_log": """
        CREATE TABLE IF NOT EXISTS render_log (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            table_name VARCHAR(50) NOT NULL,
            last_rendered TIMESTAMPTZ DEFAULT now(),
            rows_rendered INTEGER,
            status VARCHAR(20),
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """,
    "corporate_governance": """
        CREATE TABLE IF NOT EXISTS corporate_governance (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            year INTEGER NOT NULL,
            board_commissioners NUMERIC(10,2),
            independent_commissioners NUMERIC(10,2),
            board_directors NUMERIC(10,2),
            audit_committee_meetings NUMERIC(10,2),
            gcg_score VARCHAR(50),
            acgs_score VARCHAR(50),
            has_whistleblowing BOOLEAN,
            has_risk_committee BOOLEAN,
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """,
    "esg_scores": """
        CREATE TABLE IF NOT EXISTS esg_scores (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            year INTEGER NOT NULL,
            rating_agency VARCHAR(50) NOT NULL,
            rating TEXT,
            score NUMERIC(10,4),
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """,
    "trading_suspensions": """
        CREATE TABLE IF NOT EXISTS trading_suspensions (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            suspend_date DATE,
            resume_date DATE,
            reason TEXT,
            suspension_type VARCHAR(50),
            source VARCHAR(50) DEFAULT 'manual',
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """,
    "pattern_analysis": """
        CREATE TABLE IF NOT EXISTS pattern_analysis (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            date DATE NOT NULL,
            pattern_type VARCHAR(50) NOT NULL,
            confidence NUMERIC(5,2),
            direction VARCHAR(20),
            details TEXT,
            source VARCHAR(50) DEFAULT 'technical_compute',
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """,
    "valuation_cache": """
        CREATE TABLE IF NOT EXISTS valuation_cache (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            date DATE NOT NULL,
            method VARCHAR(30) NOT NULL,
            intrinsic_value NUMERIC(20,2),
            market_price NUMERIC(20,2),
            upside_pct NUMERIC(10,2),
            assumptions TEXT,
            source VARCHAR(50) DEFAULT 'computed',
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """,
    "broker_flow": """
        CREATE TABLE IF NOT EXISTS broker_flow (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            date DATE NOT NULL,
            broker VARCHAR(20) NOT NULL,
            buy_volume NUMERIC(20,2),
            buy_value NUMERIC(20,2),
            sell_volume NUMERIC(20,2),
            sell_value NUMERIC(20,2),
            net_volume NUMERIC(20,2),
            net_value NUMERIC(20,2),
            source VARCHAR(50) DEFAULT 'idx_scraper',
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """,
    "market_calendar": """
        CREATE TABLE IF NOT EXISTS market_calendar (
            id BIGSERIAL PRIMARY KEY,
            date DATE NOT NULL,
            exchange VARCHAR(10) NOT NULL DEFAULT 'XIDX',
            is_trading_day BOOLEAN DEFAULT true,
            holiday_name VARCHAR(200),
            half_day BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ
        );
    """,
    "daily_risk_metrics": """
        CREATE TABLE IF NOT EXISTS daily_risk_metrics (
            id BIGSERIAL PRIMARY KEY,
            date DATE NOT NULL,
            var_95 NUMERIC(10,4),
            var_99 NUMERIC(10,4),
            cvar_95 NUMERIC(10,4),
            cvar_99 NUMERIC(10,4),
            max_drawdown NUMERIC(10,4),
            annualized_volatility NUMERIC(10,4),
            portfolio_value NUMERIC(20,2),
            created_at TIMESTAMPTZ DEFAULT now(),
            ticker VARCHAR(30)
        );
        CREATE INDEX IF NOT EXISTS ix_daily_risk_metrics_ticker_date ON daily_risk_metrics(ticker, date);
        CREATE INDEX IF NOT EXISTS ix_daily_risk_metrics_date ON daily_risk_metrics(date);
    """,
    "daily_trading_stats": """
        CREATE TABLE IF NOT EXISTS daily_trading_stats (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            date DATE NOT NULL,
            previous_close NUMERIC(20,4),
            first_trade NUMERIC(20,4),
            "change" NUMERIC(20,4),
            value NUMERIC(20,2),
            frequency INTEGER,
            index_individual NUMERIC(20,4),
            offer NUMERIC(20,4),
            offer_volume NUMERIC(20,2),
            bid NUMERIC(20,4),
            bid_volume NUMERIC(20,2),
            listed_shares NUMERIC(20,2),
            tradeable_shares NUMERIC(20,2),
            weight_for_index NUMERIC(20,4),
            non_regular_volume NUMERIC(20,2),
            non_regular_value NUMERIC(20,2),
            non_regular_frequency INTEGER,
            source VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ,
            UNIQUE(ticker, date, source)
        );
        CREATE INDEX IF NOT EXISTS ix_daily_trading_stats_ticker ON daily_trading_stats(ticker);
        CREATE INDEX IF NOT EXISTS ix_daily_trading_stats_date ON daily_trading_stats(date);
        CREATE INDEX IF NOT EXISTS ix_dts_ticker_date ON daily_trading_stats(ticker, date);
    """,
}

# ─── Column lists for INSERT ────────────────────────────────────────────────

INSERT_COLUMNS: dict[str, list[str]] = {
    "ml_labels": ["ticker", "date", "horizon", "direction", "barrier_hit", "return_pct", "vol_adjusted_return", "created_at"],
    "relationship_matrix": ['asset_a', 'asset_b', '"window"', 'correlation', 'lag', 'as_of'],
    "scores": ["ticker", "engine", "score", "breakdown", "as_of", "created_at"],
    "policy_events": ["tanggal", "kategori", "judul", "instansi", "dampak", "sektor", "deskripsi", "created_at"],
    "external_events": ["tanggal", "kategori", "judul", "lokasi", "dampak_market", "sektor", "deskripsi", "created_at"],
    "recompute_watermark": ["ticker", "table_name", "last_processed_date", "last_ohlcv_date", "rows_processed", "updated_at"],
    "technical_indicators_wide": [
        "ticker", "date", "timeframe", "ma20", "ma50", "rsi", "macd", "macd_signal",
        "adx", "atr14", "bb_upper", "bb_lower", "volume_sma20",
        "ema50", "ema_env_upper", "ema_env_lower", "donchian_upper", "donchian_lower",
        "donchian_mid", "created_at",
    ],
    "stock_prediction": [
        "ticker", "predicted_direction", "predicted_price", "predicted_return_pct",
        "prediction_confidence", "ml_signal", "multifactor_signal", "composite_signal",
        "factors_summary", "prediction_updated_at",
    ],
    "render_log": ["ticker", "table_name", "last_rendered", "rows_rendered", "status", "created_at"],
    "corporate_governance": [
        "ticker", "year", "board_commissioners", "independent_commissioners",
        "board_directors", "audit_committee_meetings", "gcg_score", "acgs_score",
        "has_whistleblowing", "has_risk_committee", "created_at",
    ],
    "esg_scores": ["ticker", "year", "rating_agency", "rating", "score", "created_at"],
    "trading_suspensions": ["ticker", "suspend_date", "resume_date", "reason", "suspension_type", "source", "created_at"],
    "pattern_analysis": ["ticker", "date", "pattern_type", "confidence", "direction", "details", "source", "created_at"],
    "valuation_cache": ["ticker", "date", "method", "intrinsic_value", "market_price", "upside_pct", "assumptions", "source", "created_at"],
    "broker_flow": ["ticker", "date", "broker", "buy_volume", "buy_value", "sell_volume", "sell_value", "net_volume", "net_value", "source", "created_at"],
    "market_calendar": ["date", "exchange", "is_trading_day", "holiday_name", "half_day", "created_at"],
    "daily_risk_metrics": ["date", "var_95", "var_99", "cvar_95", "cvar_99", "max_drawdown", "annualized_volatility", "portfolio_value", "created_at", "ticker"],
    "daily_trading_stats": ["ticker", "date", "previous_close", "first_trade", "\"change\"", "value", "frequency", "index_individual", "offer", "offer_volume", "bid", "bid_volume", "listed_shares", "tradeable_shares", "weight_for_index", "non_regular_volume", "non_regular_value", "non_regular_frequency", "source", "created_at"],
}

# Tables with unique constraint → use ON CONFLICT
ON_CONFLICT: dict[str, str] = {
    "ml_labels": "ON CONFLICT (ticker, date, horizon) DO UPDATE SET direction=EXCLUDED.direction, barrier_hit=EXCLUDED.barrier_hit, return_pct=EXCLUDED.return_pct, vol_adjusted_return=EXCLUDED.vol_adjusted_return",
    "relationship_matrix": 'ON CONFLICT (asset_a, asset_b, "window") DO UPDATE SET correlation=EXCLUDED.correlation, lag=EXCLUDED.lag, as_of=EXCLUDED.as_of',
    "scores": "ON CONFLICT (ticker, engine, as_of) DO UPDATE SET score=EXCLUDED.score, breakdown=EXCLUDED.breakdown",
    "recompute_watermark": "ON CONFLICT (ticker, table_name) DO UPDATE SET last_processed_date=EXCLUDED.last_processed_date, last_ohlcv_date=EXCLUDED.last_ohlcv_date, rows_processed=EXCLUDED.rows_processed, updated_at=EXCLUDED.updated_at",
    "technical_indicators_wide": "ON CONFLICT (ticker, date, timeframe) DO UPDATE SET ma20=EXCLUDED.ma20, ma50=EXCLUDED.ma50, rsi=EXCLUDED.rsi, macd=EXCLUDED.macd, macd_signal=EXCLUDED.macd_signal, adx=EXCLUDED.adx, atr14=EXCLUDED.atr14, bb_upper=EXCLUDED.bb_upper, bb_lower=EXCLUDED.bb_lower, volume_sma20=EXCLUDED.volume_sma20, ema50=EXCLUDED.ema50, ema_env_upper=EXCLUDED.ema_env_upper, ema_env_lower=EXCLUDED.ema_env_lower, donchian_upper=EXCLUDED.donchian_upper, donchian_lower=EXCLUDED.donchian_lower, donchian_mid=EXCLUDED.donchian_mid",
    "stock_prediction": "ON CONFLICT (ticker) DO UPDATE SET predicted_direction=EXCLUDED.predicted_direction, predicted_price=EXCLUDED.predicted_price, predicted_return_pct=EXCLUDED.predicted_return_pct, prediction_confidence=EXCLUDED.prediction_confidence, ml_signal=EXCLUDED.ml_signal, multifactor_signal=EXCLUDED.multifactor_signal, composite_signal=EXCLUDED.composite_signal, factors_summary=EXCLUDED.factors_summary, prediction_updated_at=EXCLUDED.prediction_updated_at",
    "daily_trading_stats": 'ON CONFLICT (ticker, date, source) DO UPDATE SET previous_close=EXCLUDED.previous_close, first_trade=EXCLUDED.first_trade, "change"=EXCLUDED."change", value=EXCLUDED.value, frequency=EXCLUDED.frequency, index_individual=EXCLUDED.index_individual, offer=EXCLUDED.offer, offer_volume=EXCLUDED.offer_volume, bid=EXCLUDED.bid, bid_volume=EXCLUDED.bid_volume, listed_shares=EXCLUDED.listed_shares, tradeable_shares=EXCLUDED.tradeable_shares, weight_for_index=EXCLUDED.weight_for_index, non_regular_volume=EXCLUDED.non_regular_volume, non_regular_value=EXCLUDED.non_regular_value, non_regular_frequency=EXCLUDED.non_regular_frequency, created_at=EXCLUDED.created_at',
}

# Priority groups
P1_TABLES = ["ml_labels", "relationship_matrix", "scores", "policy_events", "external_events", "recompute_watermark"]
P2_TABLES = ["technical_indicators_wide", "stock_prediction", "render_log"]
P3_TABLES = ["corporate_governance", "esg_scores", "trading_suspensions", "pattern_analysis", "valuation_cache", "broker_flow", "market_calendar"]

# Batch sizes (smaller for tables with many columns)
BATCH_SIZES: dict[str, int] = {
    "ml_labels": 50000,
    "daily_risk_metrics": 50000,
    "technical_indicators_wide": 10000,
    "daily_trading_stats": 10000,
    "broker_flow": 5000,
    "market_calendar": 5000,
    "relationship_matrix": 5000,
    "scores": 5000,
}
DEFAULT_BATCH_SIZE = 2000


def migrate_table(table_name: str, sqlite_conn: sqlite3.Connection, pg_conn, dry_run: bool = False) -> dict:
    """Migrate a single table from SQLite to PostgreSQL."""
    cols = INSERT_COLUMNS[table_name]
    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    conflict = ON_CONFLICT.get(table_name, "")
    batch_size = BATCH_SIZES.get(table_name, DEFAULT_BATCH_SIZE)

    # Count source rows
    total_rows = sqlite_conn.execute(f'SELECT count(*) FROM "{table_name}"').fetchone()[0]
    if total_rows == 0:
        logger.info("  %s: 0 rows in SQLite — skipping", table_name)
        return {"table": table_name, "action": "skip", "rows": 0}

    logger.info("  %s: %d rows to migrate (batch=%d)", table_name, total_rows, batch_size)

    if dry_run:
        return {"table": table_name, "action": "dry_run", "rows": total_rows}

    # Create DDL
    pg_cur = pg_conn.cursor()
    pg_cur.execute(DDL_STATEMENTS[table_name])
    pg_conn.commit()
    pg_cur.close()

    # Read and insert in batches
    inserted = 0
    errors = 0
    offset = 0
    start_time = time.monotonic()

    select_sql = f'SELECT {col_list} FROM "{table_name}" LIMIT {batch_size} OFFSET ?'

    while offset < total_rows:
        rows = sqlite_conn.execute(select_sql, (offset,)).fetchall()
        if not rows:
            break

        # Convert rows: handle None and type conversions
        clean_rows = []
        for row in rows:
            clean = []
            for val in row:
                clean.append(val)
            clean_rows.append(tuple(clean))

        # Special handling: convert int 0/1 to bool for market_calendar
        if table_name == "market_calendar":
            clean_rows = [
                tuple(bool(v) if isinstance(v, int) and i in (2, 4) else v
                      for i, v in enumerate(row))
                for row in clean_rows
            ]
        elif table_name == "corporate_governance":
            # has_whistleblowing=idx 8, has_risk_committee=idx 9
            clean_rows = [
                tuple(bool(v) if isinstance(v, int) and i in (8, 9) else v
                      for i, v in enumerate(row))
                for row in clean_rows
            ]

        try:
            pg_cur = pg_conn.cursor()
            insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES %s {conflict}".strip()
            psycopg2.extras.execute_values(pg_cur, insert_sql, clean_rows, template=f"({placeholders})")
            pg_conn.commit()
            pg_cur.close()
            inserted += len(clean_rows)
        except Exception as e:
            pg_conn.rollback()
            logger.warning("  %s: batch at offset %d failed: %s", table_name, offset, str(e)[:150])
            errors += len(clean_rows)
            # Try smaller batches
            sub_batch = max(1, len(clean_rows) // 10)
            for i in range(0, len(clean_rows), sub_batch):
                sub = clean_rows[i:i + sub_batch]
                try:
                    pg_cur = pg_conn.cursor()
                    psycopg2.extras.execute_values(pg_cur, insert_sql, sub, template=f"({placeholders})")
                    pg_conn.commit()
                    pg_cur.close()
                    inserted += len(sub)
                except Exception as e2:
                    pg_conn.rollback()
                    errors += len(sub)
                    logger.warning("  %s: sub-batch failed: %s", table_name, str(e2)[:100])

        offset += batch_size

        if offset % (batch_size * 10) == 0 or offset >= total_rows:
            elapsed = time.monotonic() - start_time
            pct = min(100, offset / total_rows * 100)
            rate = inserted / max(elapsed, 0.1)
            logger.info("  %s: %d/%d (%.0f%%) — %d inserted, %d errors, %.0f rows/s",
                        table_name, min(offset, total_rows), total_rows, pct, inserted, errors, rate)

    elapsed = time.monotonic() - start_time
    logger.info("  %s: DONE — %d inserted, %d errors in %.1fs", table_name, inserted, errors, elapsed)
    return {
        "table": table_name,
        "action": "migrated",
        "rows_source": total_rows,
        "rows_inserted": inserted,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite tables to PostgreSQL")
    parser.add_argument("--all", action="store_true", help="Migrate all tables")
    parser.add_argument("--p1", action="store_true", help="Priority 1: critical for S2 prediction")
    parser.add_argument("--p2", action="store_true", help="Priority 2: recompute pipeline")
    parser.add_argument("--p3", action="store_true", help="Priority 3: supporting tables")
    parser.add_argument("--table", action="append", type=str, help="Migrate specific table (can repeat)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not any([args.all, args.p1, args.p2, args.p3, args.table]):
        args.all = True

    tables: list[str] = []
    if args.all:
        tables = P1_TABLES + P2_TABLES + P3_TABLES
    if args.p1:
        tables = P1_TABLES
    if args.p2:
        tables = P2_TABLES
    if args.p3:
        tables = P3_TABLES
    if args.table:
        tables = args.table

    sqlite_path = SQLITE_PATH
    if not Path(sqlite_path).exists():
        logger.error("SQLite database not found: %s", sqlite_path)
        return

    logger.info("SQLite source: %s", sqlite_path)
    logger.info("PG target: %s", settings.resolved_database_url)
    logger.info("Tables to migrate: %s", tables)
    logger.info("=" * 60)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    # Convert SQLAlchemy URL to psycopg2 DSN
    db_url = settings.resolved_database_url
    if "+psycopg2" in db_url:
        db_url = db_url.replace("+psycopg2", "")
    # Handle Unix socket format: postgresql:///market?host=/var/run/postgresql
    pg_conn = psycopg2.connect(db_url)

    results: list[dict] = []
    for table in tables:
        logger.info("-" * 40)
        result = migrate_table(table, sqlite_conn, pg_conn, dry_run=args.dry_run)
        results.append(result)

    sqlite_conn.close()
    pg_conn.close()

    # Summary
    print(f"\n{'='*60}")
    print("MIGRATION SUMMARY")
    print(f"{'='*60}")
    for r in results:
        action = r.get("action", "unknown")
        table = r.get("table", "unknown")
        if action == "migrated":
            print(f"  {table:40s} MIGRATED  {r['rows_inserted']:>10,} rows  ({r['elapsed_seconds']}s)")
        elif action == "dry_run":
            print(f"  {table:40s} DRY-RUN   {r['rows']:>10,} rows")
        elif action == "skip":
            print(f"  {table:40s} SKIP      0 rows")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
