#!/usr/bin/env python3
"""Recompute stale tables: pattern_analysis, valuation_cache, market_sessions.

These tables are not covered by run_all_recompute() but still need periodic refresh.

Usage:
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5432/market \
    .venv/bin/python3 scripts/recompute_stale_tables.py [--tickers AAA,BBB]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from market.db.engine import get_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_db_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://petrick:market_dev@localhost:5432/market")


def load_ohlcv_df(session, ticker: str) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT timestamp, open, high, low, close, volume
        FROM stock_prices
        WHERE ticker = :t AND timeframe = '1d'
        ORDER BY timestamp
    """), {"t": ticker}).all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([{"open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows],
                      index=pd.DatetimeIndex([r[0] for r in rows]))
    return df


def recompute_pattern_analysis(session, tickers: list[str]) -> int:
    """Recompute pattern_analysis for given tickers using PatternDetector."""
    from market.analysis.pattern_detector import PatternDetector

    detector = PatternDetector(min_lookback=60)
    today = date.today()
    count = 0

    # Delete existing rows for these tickers
    if tickers:
        placeholders = ",".join([f":t{i}" for i in range(len(tickers))])
        params = {f"t{i}": t for i, t in enumerate(tickers)}
        session.execute(text(f"DELETE FROM pattern_analysis WHERE ticker IN ({placeholders})"), params)
        session.commit()

    batch = []
    for ticker in tickers:
        df = load_ohlcv_df(session, ticker)
        if df.empty or len(df) < 60:
            continue
        detections = detector.detect(ticker, df, as_of=None)
        for d in detections:
            batch.append({
                "ticker": ticker,
                "date": today,
                "pattern_type": d.pattern_type,
                "confidence": float(d.confidence),
                "direction": d.direction,
                "details": json.dumps({"key_levels": d.key_levels, "description": d.description}),
                "source": "recompute_stale",
                "created_at": datetime.now(UTC),
            })
            count += 1
        if len(batch) >= 100:
            session.execute(text("""
                INSERT INTO pattern_analysis (ticker, date, pattern_type, confidence, direction, details, source, created_at)
                VALUES (:ticker, :date, :pattern_type, :confidence, :direction, :details, :source, :created_at)
                ON CONFLICT (ticker, date, pattern_type) DO UPDATE SET
                    confidence=EXCLUDED.confidence, direction=EXCLUDED.direction,
                    details=EXCLUDED.details, source=EXCLUDED.source
            """), batch)
            session.commit()
            batch.clear()
            logger.info("  pattern_analysis: %d rows so far (%s)", count, ticker)

    if batch:
        session.execute(text("""
            INSERT INTO pattern_analysis (ticker, date, pattern_type, confidence, direction, details, source, created_at)
            VALUES (:ticker, :date, :pattern_type, :confidence, :direction, :details, :source, :created_at)
            ON CONFLICT (ticker, date, pattern_type) DO UPDATE SET
                confidence=EXCLUDED.confidence, direction=EXCLUDED.direction,
                details=EXCLUDED.details, source=EXCLUDED.source
        """), batch)
        session.commit()

    logger.info("pattern_analysis: %d rows for %d tickers", count, len(tickers))
    return count


def recompute_valuation_cache(session, tickers: list[str]) -> int:
    """Recompute valuation_cache from fundamental_data + latest close prices."""
    count = 0
    today = date.today()
    batch = []

    for ticker in tickers:
        # Get latest fundamental data
        row = session.execute(text("""
            SELECT pe, pb, roe, der, dividend_yield, earnings_growth, revenue_growth
            FROM fundamental_data
            WHERE ticker = :t
            ORDER BY date DESC LIMIT 1
        """), {"t": ticker}).fetchone()

        if not row:
            continue

        pe, pb, roe, der, div_yield, eps_g, rev_g = row
        pe = float(pe) if pe is not None else None
        pb = float(pb) if pb is not None else None

        # Get latest close price
        price_row = session.execute(text("""
            SELECT close FROM stock_prices
            WHERE ticker = :t AND timeframe = '1d'
            ORDER BY timestamp DESC LIMIT 1
        """), {"t": ticker}).fetchone()

        if not price_row:
            continue

        market_price = float(price_row[0])

        # Simple relative valuation: intrinsic_value based on PE and earnings
        eps = market_price / pe if pe and pe > 0 else None
        intrinsic_value = None
        method = "relative_pe"
        assumptions = {}

        if eps and eps > 0:
            # Fair PE = 15 (market average), intrinsic = fair_pe * eps
            fair_pe = 15.0
            intrinsic_value = fair_pe * eps
            assumptions = {"fair_pe": fair_pe, "eps": eps, "actual_pe": pe}
        elif pb and pb > 0:
            # Fallback: P/B based
            bps = market_price / pb
            fair_pb = 1.5
            intrinsic_value = fair_pb * bps
            method = "relative_pb"
            assumptions = {"fair_pb": fair_pb, "bps": bps, "actual_pb": pb}

        if intrinsic_value is None:
            continue

        upside_pct = ((intrinsic_value - market_price) / market_price) * 100 if market_price > 0 else 0

        batch.append({
            "ticker": ticker,
            "date": today,
            "method": method,
            "intrinsic_value": round(intrinsic_value, 2),
            "market_price": round(market_price, 2),
            "upside_pct": round(upside_pct, 2),
            "assumptions": json.dumps(assumptions),
            "source": "recompute_stale",
            "created_at": datetime.now(UTC),
        })
        count += 1

        if len(batch) >= 100:
            session.execute(text("""
                INSERT INTO valuation_cache (ticker, date, method, intrinsic_value, market_price, upside_pct, assumptions, source, created_at)
                VALUES (:ticker, :date, :method, :intrinsic_value, :market_price, :upside_pct, :assumptions, :source, :created_at)
                ON CONFLICT DO NOTHING
            """), batch)
            session.commit()
            batch.clear()
            logger.info("  valuation_cache: %d rows so far", count)

    if batch:
        session.execute(text("""
            INSERT INTO valuation_cache (ticker, date, method, intrinsic_value, market_price, upside_pct, assumptions, source, created_at)
            VALUES (:ticker, :date, :method, :intrinsic_value, :market_price, :upside_pct, :assumptions, :source, :created_at)
            ON CONFLICT DO NOTHING
        """), batch)
        session.commit()

    logger.info("valuation_cache: %d rows for %d tickers", count, len(tickers))
    return count


def generate_market_sessions(session, start_date: str = "2026-08-01") -> int:
    """Generate market_sessions from market_registry trading_hours."""
    # Hardcoded trading hours per MIC (DB trading_hours column is empty)
    MIC_HOURS = {
        "XIDX": ("09:00", "16:00", "Asia/Jakarta", "IDX"),
        "XNYS": ("09:30", "16:00", "America/New_York", "NYSE"),
        "XNAS": ("09:30", "16:00", "America/New_York", "NASDAQ"),
        "XHKG": ("09:30", "16:00", "Asia/Hong_Kong", "HKEX"),
        "XTSE": ("09:00", "15:00", "Asia/Tokyo", "TSE"),
        "XSGX": ("09:00", "17:00", "Asia/Singapore", "SGX"),
        "XLON": ("08:00", "16:30", "Europe/London", "LSE"),
        "XFRA": ("09:00", "17:30", "Europe/Berlin", "Frankfurt"),
        "XCEC": ("09:30", "16:00", "America/New_York", "CME/Comex"),
        "XSHG": ("09:30", "15:00", "Asia/Shanghai", "SSE"),
        "XKLS": ("09:00", "17:00", "Asia/Kuala_Lumpur", "Bursa Malaysia"),
        "XKRX": ("09:00", "15:30", "Asia/Seoul", "KRX"),
        "XSES": ("09:00", "17:00", "Asia/Singapore", "SGX"),
        "XASX": ("10:00", "16:00", "Australia/Sydney", "ASX"),
        "XBOM": ("09:15", "15:30", "Asia/Kolkata", "BSE"),
    }

    # Get active exchanges
    exchanges = session.execute(text("""
        SELECT mic_code, timezone
        FROM market_registry
        WHERE trading_status = 'active'
    """)).all()

    if not exchanges:
        logger.warning("No active exchanges found in market_registry")
        return 0

    start = date.fromisoformat(start_date)
    today = date.today()
    count = 0
    batch = []

    # Delete existing sessions in the date range
    try:
        session.execute(text("DELETE FROM market_sessions WHERE session_date >= :s"), {"s": start})
        session.commit()
    except Exception:
        session.rollback()
        logger.warning("Could not delete old market_sessions (continuing with ON CONFLICT)")

    for mic, tz_name in exchanges:
        if mic not in MIC_HOURS:
            continue

        open_str, close_str, tz, exch_name = MIC_HOURS[mic]

        current = start
        while current <= today:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            open_dt = datetime.fromisoformat(f"{current.isoformat()}T{open_str}:00+07:00")
            close_dt = datetime.fromisoformat(f"{current.isoformat()}T{close_str}:00+07:00")

            batch.append({
                "exchange_mic": mic,
                "session_date": current,
                "open_at": open_dt,
                "close_at": close_dt,
                "session_type": "REGULAR",
                "is_closed": False,
                "note": f"{exch_name} regular session",
                "created_at": datetime.now(UTC),
            })
            count += 1

            if len(batch) >= 500:
                session.execute(text("""
                    INSERT INTO market_sessions (exchange_mic, session_date, open_at, close_at, session_type, is_closed, note, created_at)
                    VALUES (:exchange_mic, :session_date, :open_at, :close_at, :session_type, :is_closed, :note, :created_at)
                    ON CONFLICT DO NOTHING
                """), batch)
                session.commit()
                batch.clear()

            current += timedelta(days=1)

    if batch:
        session.execute(text("""
            INSERT INTO market_sessions (exchange_mic, session_date, open_at, close_at, session_type, is_closed, note, created_at)
            VALUES (:exchange_mic, :session_date, :open_at, :close_at, :session_type, :is_closed, :note, :created_at)
            ON CONFLICT DO NOTHING
        """), batch)
        session.commit()

    logger.info("market_sessions: %d rows (%s to %s, %d exchanges)", count, start, today, len(exchanges))
    return count


def main():
    parser = argparse.ArgumentParser(description="Recompute stale tables")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers (default: all .JK)")
    parser.add_argument("--skip-pattern", action="store_true")
    parser.add_argument("--skip-valuation", action="store_true")
    parser.add_argument("--skip-sessions", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("DATABASE_URL", "postgresql://petrick:market_dev@localhost:5432/market")

    session = get_sessionmaker()()

    # Get tickers
    if args.tickers:
        tickers = args.tickers.split(",")
    else:
        rows = session.execute(text("""
            SELECT DISTINCT ticker FROM stock_prices
            WHERE ticker LIKE '%.JK' AND timeframe = '1d'
            ORDER BY ticker
        """)).all()
        tickers = [r[0] for r in rows]

    logger.info("Processing %d tickers", len(tickers))

    try:
        if not args.skip_pattern:
            logger.info("=== Recomputing pattern_analysis ===")
            recompute_pattern_analysis(session, tickers)

        if not args.skip_valuation:
            logger.info("=== Recomputing valuation_cache ===")
            recompute_valuation_cache(session, tickers)

        if not args.skip_sessions:
            logger.info("=== Generating market_sessions ===")
            generate_market_sessions(session)

        logger.info("All done.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
