#!/usr/bin/env python3
"""Migrate SQLite market_research.db → PostgreSQL domino effect schema.

Transfers real data from existing SQLite tables to PostgreSQL schema defined
in docs/domino_effect_schema.sql.

Mappings:
  SQLite market_registry   → PG exchanges
  SQLite instrument_master  → PG instruments
  SQLite broker             → PG brokers
  SQLite ohlcv              → PG stock_prices (partitioned)
  SQLite policy_events      → PG events (category mapping)
  SQLite external_events    → PG events (category mapping)
  SQLite dividends          → PG corporate_actions (DIVIDEND type)
  SQLite broker_flow        → PG broker_transactions (aggregated → per-day)
  Generated from trading_hours → PG market_sessions

Usage:
  # Generate SQL file (no PostgreSQL connection needed):
  DB_PATH=data/market_research.db uv run python scripts/migrate_sqlite_to_pg.py --output migration.sql

  # Direct connection (requires psycopg2 or psycopg3):
  DB_PATH=data/market_research.db uv run python scripts/migrate_sqlite_to_pg.py \
      --pg-url "postgresql://user:pass@localhost:5432/market"

  # Dry run (count rows, show plan, no data transfer):
  DB_PATH=data/market_research.db uv run python scripts/migrate_sqlite_to_pg.py --dry-run

  # Limit OHLCV to recent years (faster testing):
  DB_PATH=data/market_research.db uv run python scripts/migrate_sqlite_to_pg.py --ohlcv-from 2024-01-01
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Category mappings ─────────────────────────────────────────────────────────

_POLICY_CATEGORY_MAP = {
    "Moneter": "MONETARY",
    "Fiskal": "FISCAL",
    "Regulasi OJK": "REGULATORY",
    "Regulasi BEI": "REGULATORY",
    "Politik": "ELECTION",
}

_EXT_CATEGORY_MAP = {
    "Konflik Geopolitik": "GEOPOLITICAL",
    "Perang": "GEOPOLITICAL",
    "Bencana Alam": "NATURAL_DISASTER",
    "Pandemi": "PANDEMIC",
    "Perubahan Iklim": "REGULATORY",
    "ESG": "REGULATORY",
}

_IMPACT_MAP = {
    "Positif": ("BULLISH", "MEDIUM"),
    "Negatif": ("BEARISH", "HIGH"),
    "Netral": ("NEUTRAL", "LOW"),
    "Tinggi": ("BEARISH", "HIGH"),
    "Sedang": ("BEARISH", "MEDIUM"),
    "Rendah": ("BEARISH", "LOW"),
}

_REGION_MAP = {
    "Indonesia": "ID",
    "Global": "GLOBAL",
    "Timur Tengah": "GLOBAL",
    "Asia": "ASIA",
    "AS": "US",
    "Eropa": "EU",
}


def get_db_path() -> str:
    return os.environ.get("DB_PATH", "data/market_research.db")


def parse_sqlite_timestamp(val: str | None) -> str | None:
    """Convert SQLite datetime string to ISO 8601 UTC for PostgreSQL TIMESTAMPTZ.

    Handles:
    - "2025-07-16 02:00:00.000000" → "2025-07-16T02:00:00+00:00"
    - "2025-07-16 02:00:00+00:00" → preserved as-is
    - "2025-07-16" → "2025-07-16T00:00:00+00:00"
    - "2025-07-16T02:00:00+07:00" → preserved (PostgreSQL will convert to UTC)
    """
    if val is None:
        return None
    val = str(val)
    # Already has timezone offset (e.g., +00:00, +07:00, -04:00, Z)
    if any(c in val for c in ["+", "-"]) and ":" in val.split(" ")[-1]:
        # Check if the last part looks like a timezone offset
        parts = val.replace("T", " ").split(" ")
        if len(parts) >= 2 and ("+" in parts[-1] or parts[-1].startswith("-")):
            return val
    # SQLite formats: "2025-07-16 02:00:00.000000" or "2025-07-16"
    if " " in val:
        return val.split(".")[0].replace(" ", "T") + "+00:00"
    return val + "T00:00:00+00:00"


def parse_sqlite_date(val: str | None) -> str | None:
    """Convert SQLite date string to ISO date."""
    if val is None:
        return None
    return str(val)[:10]


def parse_sectors(sektor: str | None) -> list[str] | None:
    """Parse semicolon-separated sectors into array."""
    if not sektor:
        return None
    return [s.strip() for s in sektor.split(";") if s.strip()]


def parse_trading_hours(trading_hours: str, tz_name: str) -> list[tuple[str, str]]:
    """Parse trading_hours string into (open_local, close_local) pairs.

    Returns list of (open_time, close_time) in local HH:MM format.
    Handles formats like "09:00-12:00,13:30-15:50" and "24/7".
    """
    if not trading_hours:
        return []

    if trading_hours.strip() == "24/7":
        return [("00:00", "23:59")]

    sessions = []
    parts = trading_hours.split(",")
    for part in parts:
        part = part.strip()
        match = re.match(r"(\d{2}:\d{2})-(\d{2}:\d{2})", part)
        if match:
            sessions.append((match.group(1), match.group(2)))
    return sessions


def local_to_utc(local_time: str, date_str: str, tz_name: str) -> str:
    """Convert local HH:MM on date to UTC ISO timestamp.

    Uses zoneinfo (Python 3.9+) for timezone conversion.
    """
    from zoneinfo import ZoneInfo

    h, m = local_time.split(":")
    local_dt = datetime(
        int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
        int(h), int(m), 0,
        tzinfo=ZoneInfo(tz_name),
    )
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


# ── SQL generation helpers ────────────────────────────────────────────────────

def sql_escape(val: str | None) -> str:
    """Escape string for SQL single-quoted literal."""
    if val is None:
        return "NULL"
    return "'" + val.replace("'", "''") + "'"


def sql_val(val) -> str:
    """Format any value for SQL."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return sql_escape(val)
    return sql_escape(str(val))


def sql_array(arr: list[str] | None) -> str:
    """Format Python list as PostgreSQL ARRAY literal."""
    if arr is None or len(arr) == 0:
        return "NULL"
    return "ARRAY[" + ",".join(sql_escape(x) for x in arr) + "]::TEXT[]"


def sql_jsonb(d: dict) -> str:
    """Format dict as PostgreSQL JSONB literal."""
    import json
    return sql_escape(json.dumps(d)) + "::JSONB"


# ── Migration functions ───────────────────────────────────────────────────────

def migrate_exchanges(conn: sqlite3.Connection, out: StringIO) -> int:
    """market_registry → exchanges"""
    # First, insert a catch-all exchange for unknown/delisted instruments
    out.write(
        "INSERT INTO exchanges (mic_code, name, country_code, timezone, "
        "currency, lot_size, tick_size, is_active) VALUES (\n"
        "  'OFF', 'Off-Exchange/Delisted', 'XXX', 'UTC', "
        "'USD', 1, 0.01, FALSE\n"
        ") ON CONFLICT (mic_code) DO NOTHING;\n"
    )

    rows = conn.execute(
        "SELECT mic_code, country_code, timezone, currency, lot_size, "
        "tick_size_rule, trading_status FROM market_registry"
    ).fetchall()

    count = 0
    for mic, country, tz, currency, lot, tick_rule, status in rows:
        tick_size = 0.01
        if tick_rule and "fraction" in tick_rule.lower():
            tick_size = 0.1
        is_active = status == "active" if status else True
        out.write(
            f"INSERT INTO exchanges (mic_code, name, country_code, timezone, "
            f"currency, lot_size, tick_size, is_active) VALUES (\n"
            f"  {sql_val(mic)}, {sql_val(mic + ' Exchange')}, {sql_val(country)}, "
            f"{sql_val(tz)}, {sql_val(currency)}, {sql_val(lot or 100)}, "
            f"{sql_val(tick_size)}, {sql_val(is_active)}\n"
            f") ON CONFLICT (mic_code) DO NOTHING;\n"
        )
        count += 1

    logger.info("exchanges: %d rows", count)
    return count


def migrate_instruments(conn: sqlite3.Connection, out: StringIO) -> int:
    """instrument_master → instruments"""
    rows = conn.execute(
        "SELECT ticker, market_mic, name, asset_class, sector, base_currency, "
        "is_active, listing_date FROM instrument_master"
    ).fetchall()

    count = 0
    for ticker, mic, name, asset_class, sector, currency, is_active, listed in rows:
        listed_ts = parse_sqlite_date(listed)
        out.write(
            f"INSERT INTO instruments (ticker, exchange_mic, name, asset_class, "
            f"sector, currency, is_active, listed_at) VALUES (\n"
            f"  {sql_val(ticker)}, {sql_val(mic)}, {sql_val(name)}, "
            f"{sql_val(asset_class)}, {sql_val(sector)}, {sql_val(currency)}, "
            f"{sql_val(bool(is_active))}, {sql_val(listed_ts)}\n"
            f") ON CONFLICT (ticker) DO NOTHING;\n"
        )
        count += 1

    logger.info("instruments: %d rows", count)
    return count


def migrate_brokers(conn: sqlite3.Connection, out: StringIO) -> int:
    """broker → brokers"""
    rows = conn.execute("SELECT id_broker, nama_broker FROM broker").fetchall()

    count = 0
    for broker_id, name in rows:
        code = f"BR{broker_id:04d}"
        out.write(
            f"INSERT INTO brokers (code, name, is_active) VALUES (\n"
            f"  {sql_val(code)}, {sql_val(name)}, TRUE\n"
            f") ON CONFLICT (code) DO NOTHING;\n"
        )
        count += 1

    logger.info("brokers: %d rows", count)
    return count


def migrate_events(conn: sqlite3.Connection, out: StringIO) -> int:
    """policy_events + external_events → events"""
    count = 0

    # policy_events
    rows = conn.execute(
        "SELECT tanggal, kategori, judul, instansi, dampak, sektor, deskripsi "
        "FROM policy_events ORDER BY tanggal"
    ).fetchall()

    for tanggal, kategori, judul, instansi, dampak, sektor, deskripsi in rows:
        category = _POLICY_CATEGORY_MAP.get(kategori or "", "REGULATORY")
        direction, impact = _IMPACT_MAP.get(dampak or "", ("NEUTRAL", "MEDIUM"))
        sectors = parse_sectors(sektor)
        occurred = parse_sqlite_date(tanggal)
        if occurred:
            occurred = occurred + "T00:00:00+00:00"

        out.write(
            f"INSERT INTO events (occurred_at, source, category, title, description, "
            f"region, impact_level, impact_direction, affected_sectors) VALUES (\n"
            f"  {sql_val(occurred)}, {sql_val(instansi)}, {sql_val(category)}, "
            f"{sql_val(judul)}, {sql_val(deskripsi)}, 'ID', "
            f"{sql_val(impact)}, {sql_val(direction)}, {sql_array(sectors)}\n"
            f");\n"
        )
        count += 1

    # external_events
    rows = conn.execute(
        "SELECT tanggal, kategori, judul, lokasi, dampak_market, sektor, deskripsi "
        "FROM external_events ORDER BY tanggal"
    ).fetchall()

    for tanggal, kategori, judul, lokasi, dampak_market, sektor, deskripsi in rows:
        category = _EXT_CATEGORY_MAP.get(kategori or "", "GEOPOLITICAL")
        direction, impact = _IMPACT_MAP.get(dampak_market or "", ("NEUTRAL", "MEDIUM"))
        sectors = parse_sectors(sektor)
        region = _REGION_MAP.get(lokasi or "", "GLOBAL")
        occurred = parse_sqlite_date(tanggal)
        if occurred:
            occurred = occurred + "T00:00:00+00:00"

        out.write(
            f"INSERT INTO events (occurred_at, source, category, title, description, "
            f"region, impact_level, impact_direction, affected_sectors) VALUES (\n"
            f"  {sql_val(occurred)}, 'external_events', {sql_val(category)}, "
            f"{sql_val(judul)}, {sql_val(deskripsi)}, {sql_val(region)}, "
            f"{sql_val(impact)}, {sql_val(direction)}, {sql_array(sectors)}\n"
            f");\n"
        )
        count += 1

    logger.info("events: %d rows (policy + external)", count)
    return count


def migrate_corporate_actions(conn: sqlite3.Connection, out: StringIO) -> int:
    """dividends → corporate_actions (DIVIDEND type)"""
    rows = conn.execute(
        "SELECT ticker, ex_date, record_date, payment_date, amount, currency, "
        "frequency, source FROM dividends ORDER BY ex_date"
    ).fetchall()

    count = 0
    for ticker, ex_date, record_date, payment_date, amount, currency, frequency, source in rows:
        announced = parse_sqlite_date(ex_date)
        if announced:
            announced = announced + "T00:00:00+00:00"
        details = {}
        if amount is not None:
            details["amount_per_share"] = float(amount)
        if currency:
            details["currency"] = currency
        if frequency:
            details["frequency"] = frequency

        out.write(
            f"INSERT INTO corporate_actions (ticker, action_type, ex_date, "
            f"record_date, payment_date, announced_at, details_json, impact_direction) VALUES (\n"
            f"  {sql_val(ticker)}, 'DIVIDEND', {sql_val(parse_sqlite_date(ex_date))}, "
            f"{sql_val(parse_sqlite_date(record_date))}, "
            f"{sql_val(parse_sqlite_date(payment_date))}, {sql_val(announced)}, "
            f"{sql_jsonb(details)}, 'BULLISH'\n"
            f");\n"
        )
        count += 1

    logger.info("corporate_actions: %d rows (dividends)", count)
    return count


def migrate_broker_transactions(conn: sqlite3.Connection, out: StringIO) -> int:
    """broker_flow → broker_transactions (aggregated daily per broker per ticker)"""
    rows = conn.execute(
        "SELECT ticker, date, broker, buy_volume, buy_value, sell_volume, "
        "sell_value, net_volume, net_value, source FROM broker_flow "
        "WHERE ticker != '__MARKET__' ORDER BY date"
    ).fetchall()

    count = 0
    for ticker, dt, broker_code, buy_vol, buy_val, sell_vol, sell_val, net_vol, net_val, source in rows:
        ts = parse_sqlite_date(dt)
        if ts:
            ts = ts + "T00:00:00+00:00"

        # Determine exchange from ticker suffix
        exchange_mic = "XIDX" if ticker.endswith(".JK") else "XNYS"

        # Emit BUY transaction if buy_volume > 0
        if buy_vol and float(buy_vol) > 0:
            avg_price = float(buy_val) / float(buy_vol) if float(buy_vol) > 0 else 0
            out.write(
                f"INSERT INTO broker_transactions (ticker, exchange_mic, timestamp, "
                f"side, order_type, quantity, price, status, is_foreign) VALUES (\n"
                f"  {sql_val(ticker)}, {sql_val(exchange_mic)}, {sql_val(ts)}, "
                f"'BUY', 'MARKET', {sql_val(int(float(buy_vol)))}, "
                f"{sql_val(round(avg_price, 6))}, 'FILLED', FALSE\n"
                f");\n"
            )
            count += 1

        # Emit SELL transaction if sell_volume > 0
        if sell_vol and float(sell_vol) > 0:
            avg_price = float(sell_val) / float(sell_vol) if float(sell_vol) > 0 else 0
            out.write(
                f"INSERT INTO broker_transactions (ticker, exchange_mic, timestamp, "
                f"side, order_type, quantity, price, status, is_foreign) VALUES (\n"
                f"  {sql_val(ticker)}, {sql_val(exchange_mic)}, {sql_val(ts)}, "
                f"'SELL', 'MARKET', {sql_val(int(float(sell_vol)))}, "
                f"{sql_val(round(avg_price, 6))}, 'FILLED', FALSE\n"
                f");\n"
            )
            count += 1

    logger.info("broker_transactions: %d rows (from broker_flow)", count)
    return count


def generate_market_sessions(conn: sqlite3.Connection, out: StringIO,
                              start_date: str = "2024-01-01",
                              end_date: str | None = None) -> int:
    """Generate market_sessions from market_registry.trading_hours.

    Creates one row per exchange per trading day from start_date to end_date.
    Skips weekends (Sat/Sun) for non-24/7 markets.
    """
    from datetime import timedelta

    if end_date is None:
        end_date = date.today().isoformat()

    exchanges = conn.execute(
        "SELECT mic_code, timezone, trading_hours FROM market_registry "
        "WHERE trading_status = 'active'"
    ).fetchall()

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    count = 0
    for mic, tz_name, trading_hours in exchanges:
        sessions = parse_trading_hours(trading_hours, tz_name)
        if not sessions:
            continue

        is_24_7 = trading_hours and trading_hours.strip() == "24/7"

        current = start
        while current <= end:
            # Skip weekends for non-24/7 markets
            if not is_24_7 and current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.isoformat()

            # Use first session as open, last session end as close
            try:
                open_utc = local_to_utc(sessions[0][0], date_str, tz_name)
                close_utc = local_to_utc(sessions[-1][1], date_str, tz_name)
            except Exception:
                current += timedelta(days=1)
                continue

            # For multi-session days (e.g. IDX with lunch break),
            # open = first session open, close = last session close
            session_type = "REGULAR"
            if is_24_7:
                session_type = "SPECIAL"

            out.write(
                f"INSERT INTO market_sessions (exchange_mic, session_date, "
                f"open_at, close_at, session_type, is_closed) VALUES (\n"
                f"  {sql_val(mic)}, {sql_val(date_str)}, "
                f"{sql_val(open_utc)}, {sql_val(close_utc)}, "
                f"{sql_val(session_type)}, FALSE\n"
                f") ON CONFLICT (exchange_mic, session_date) DO NOTHING;\n"
            )
            count += 1
            current += timedelta(days=1)

    logger.info("market_sessions: %d rows (generated %s to %s)", count, start_date, end_date)
    return count


def migrate_stock_prices(conn: sqlite3.Connection, out: StringIO,
                          ohlcv_from: str | None = None,
                          batch_size: int = 50000) -> int:
    """ohlcv → stock_prices (batched COPY-style INSERTs).

    For 3.2M rows, this generates batch INSERT statements.
    For production use, consider pg_dump or psycopg2 COPY.
    """
    where_clause = "WHERE timeframe = '1d'"
    if ohlcv_from:
        where_clause += f" AND timestamp >= '{ohlcv_from}'"

    total = conn.execute(f"SELECT COUNT(*) FROM ohlcv {where_clause}").fetchone()[0]
    logger.info("stock_prices: starting migration of %d rows (ohlcv_from=%s)", total, ohlcv_from)

    count = 0
    offset = 0

    while offset < total:
        rows = conn.execute(
            f"SELECT ticker, timestamp, timeframe, open, high, low, close, "
            f"volume, adjusted_close, source "
            f"FROM ohlcv {where_clause} "
            f"ORDER BY timestamp, ticker LIMIT {batch_size} OFFSET {offset}"
        ).fetchall()

        if not rows:
            break

        out.write("INSERT INTO stock_prices (ticker, exchange_mic, timestamp, timeframe, open, high, low, close, volume, source) VALUES\n")
        values = []
        for ticker, ts, timeframe, o, h, l, c, vol, adj_close, source in rows:
            utc_ts = parse_sqlite_timestamp(str(ts))
            exchange_mic = "XIDX" if ticker.endswith(".JK") else (
                "XNYS" if ticker.startswith("^") or ticker in ("AAPL", "MSFT", "GOOG") else "XNYS"
            )
            # Map known global tickers to their exchanges
            if ticker.endswith(".HK"):
                exchange_mic = "XHKG"
            elif ticker.endswith(".T"):
                exchange_mic = "XTSE"
            elif ticker.endswith(".L"):
                exchange_mic = "XLON"
            elif ticker.endswith(".DE"):
                exchange_mic = "XFRA"
            elif ticker.endswith(".SS"):
                exchange_mic = "XSHG"
            elif ticker.endswith(".SI"):
                exchange_mic = "XSGX"
            elif ticker == "IDR=X":
                exchange_mic = "XFXS"
            elif ticker in ("GC=F", "CL=F", "HG=F", "SI=F", "NG=F"):
                exchange_mic = "XCEC"

            values.append(
                f"  ({sql_val(ticker)}, {sql_val(exchange_mic)}, {sql_val(utc_ts)}, "
                f"{sql_val(timeframe)}, {sql_val(o)}, {sql_val(h)}, {sql_val(l)}, "
                f"{sql_val(c)}, {sql_val(vol)}, {sql_val(source)})"
            )

        out.write(",\n".join(values))
        out.write("\nON CONFLICT DO NOTHING;\n\n")
        count += len(rows)
        offset += batch_size

        if count % 100000 == 0:
            logger.info("stock_prices: %d / %d rows", count, total)

    logger.info("stock_prices: %d rows total", count)
    return count


# ── DDL: create tables (from schema file, filtered) ──────────────────────────

def write_ddl(out: StringIO) -> None:
    """Write DDL statements from domino_effect_schema.sql (sections 0-9)."""
    schema_path = Path(__file__).parent.parent / "docs" / "domino_effect_schema.sql"
    if schema_path.exists():
        sql_text = schema_path.read_text()
        # Cut everything after section 9 (the helper function)
        # Remove section 10+ (sample data) — already removed from file
        out.write("-- ═══ DDL from domino_effect_schema.sql ═══\n\n")
        out.write(sql_text)
        out.write("\n\n-- ═══ DATA MIGRATION ═══\n\n")
    else:
        logger.warning("Schema file not found: %s", schema_path)
        out.write("-- WARNING: domino_effect_schema.sql not found, DDL skipped\n\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL domino schema")
    parser.add_argument("--output", "-o", type=str, help="Output SQL file path")
    parser.add_argument("--pg-url", type=str, help="PostgreSQL connection URL (requires psycopg2/psycopg3)")
    parser.add_argument("--dry-run", action="store_true", help="Count rows only, no SQL output")
    parser.add_argument("--ohlcv-from", type=str, default=None, help="OHLCV start date (YYYY-MM-DD), default: all")
    parser.add_argument("--sessions-from", type=str, default="2024-01-01", help="Market sessions start date")
    parser.add_argument("--sessions-to", type=str, default=None, help="Market sessions end date (default: today)")
    parser.add_argument("--skip-ohlcv", action="store_true", help="Skip OHLCV migration (3.2M rows)")
    parser.add_argument("--no-drop", action="store_true", help="Don't drop schema first (incremental)")
    args = parser.parse_args()

    db_path = get_db_path()
    logger.info("SQLite source: %s", db_path)

    conn = sqlite3.connect(db_path)

    if args.pg_url and not args.no_drop:
        # Drop and recreate schema for clean migration
        import subprocess
        logger.info("Dropping public schema for clean migration...")
        subprocess.run(
            ["psql", args.pg_url, "-c", "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"],
            capture_output=True, text=True, check=True,
        )

    if args.dry_run:
        # Just count and report
        tables = {
            "exchanges (market_registry)": "SELECT COUNT(*) FROM market_registry",
            "instruments (instrument_master)": "SELECT COUNT(*) FROM instrument_master",
            "brokers (broker)": "SELECT COUNT(*) FROM broker",
            "events (policy_events)": "SELECT COUNT(*) FROM policy_events",
            "events (external_events)": "SELECT COUNT(*) FROM external_events",
            "corporate_actions (dividends)": "SELECT COUNT(*) FROM dividends",
            "broker_transactions (broker_flow)": "SELECT COUNT(*) FROM broker_flow WHERE ticker != '__MARKET__'",
        }
        for label, query in tables.items():
            cnt = conn.execute(query).fetchone()[0]
            logger.info("  %-45s %d rows", label, cnt)

        ohlcv_where = "WHERE timeframe = '1d'"
        if args.ohlcv_from:
            ohlcv_where += f" AND timestamp >= '{args.ohlcv_from}'"
        ohlcv_cnt = conn.execute(f"SELECT COUNT(*) FROM ohlcv {ohlcv_where}").fetchone()[0]
        logger.info("  %-45s %d rows", f"stock_prices (ohlcv) {ohlcv_where}", ohlcv_cnt)

        # Estimate market_sessions
        from datetime import timedelta
        start = date.fromisoformat(args.sessions_from)
        end = date.fromisoformat(args.sessions_to or date.today().isoformat())
        days = (end - start).days
        active_exchanges = conn.execute(
            "SELECT COUNT(*) FROM market_registry WHERE trading_status = 'active' AND trading_hours != '24/7'"
        ).fetchone()[0]
        est_sessions = int(days * 5/7 * active_exchanges)
        logger.info("  %-45s ~%d rows (estimated)", "market_sessions (generated)", est_sessions)

        logger.info("")
        logger.info("DRY RUN complete. Use --output or --pg-url to execute migration.")
        conn.close()
        return

    # Generate SQL
    out = StringIO()

    # 1. DDL (create tables)
    write_ddl(out)

    # 2. Data migration
    logger.info("Migrating data...")
    migrate_exchanges(conn, out)
    migrate_instruments(conn, out)
    migrate_brokers(conn, out)
    migrate_events(conn, out)
    migrate_corporate_actions(conn, out)
    generate_market_sessions(conn, out, start_date=args.sessions_from, end_date=args.sessions_to)

    if not args.skip_ohlcv:
        migrate_stock_prices(conn, out, ohlcv_from=args.ohlcv_from)
    else:
        logger.info("stock_prices: SKIPPED (--skip-ohlcv)")

    migrate_broker_transactions(conn, out)

    # 3. Create view (already in DDL, but ensure it's after data)
    out.write("\n-- ═══ MIGRATION COMPLETE ═══\n")

    sql_content = out.getvalue()
    conn.close()

    if args.output:
        Path(args.output).write_text(sql_content)
        size_mb = len(sql_content) / 1024 / 1024
        logger.info("SQL written to %s (%.1f MB)", args.output, size_mb)
    elif args.pg_url:
        # Direct connection: write to temp file then use psql -f
        # (psycopg2 can't handle multi-statement with $$ functions reliably)
        import subprocess
        import tempfile

        tmp_path = tempfile.mktemp(suffix=".sql")
        Path(tmp_path).write_text(sql_content)
        logger.info("SQL written to temp file (%.1f MB), executing via psql...", len(sql_content) / 1024 / 1024)

        # Parse pg_url for psql command
        cmd = ["psql", args.pg_url, "-f", tmp_path, "-v", "ON_ERROR_STOP=1"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode != 0:
            logger.error("psql failed (exit %d):", result.returncode)
            logger.error("STDERR: %s", result.stderr[-2000:])
            logger.error("STDOUT: %s", result.stdout[-2000:])
            raise RuntimeError("psql execution failed")
        else:
            # Show summary from stdout
            for line in result.stdout.strip().split("\n")[-10:]:
                logger.info("  psql: %s", line)
            logger.info("Migration complete!")
    else:
        # Print to stdout
        print(sql_content)


if __name__ == "__main__":
    main()
