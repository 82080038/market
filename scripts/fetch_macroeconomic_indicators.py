"""Fetch macroeconomic indicators and populate ``macroeconomic_indicators`` table.

This script implements the "WHY" dimension (Dimensi 1) of the domino-effect
causal framework by ingesting time-series readings of macro indicators that
drive stock price movements:

yfinance (daily, free, no API key):
  - IDR=X       → USD_IDR       (Nilai tukar USD/IDR)
  - ^VIX        → VIX_INDEX     (CBOE Volatility Index / Indeks Ketakutan)
  - GC=F        → GOLD_PRICE    (Harga emas dunia, COMEX)
  - BZ=F        → BRENT_CRUDE   (Harga minyak mentah Brent, ICE)

FRED (St. Louis Fed, free CSV download, no API key) — optional:
  - FEDFUNDS    → FED_RATE      (US Federal Funds Rate, monthly)
  - INTDSBIDM193N → BI_RATE     (Indonesia Interest Rate / BI Rate, monthly)
  - CPIAUCSL    → US_INFLATION  (US CPI All Items, monthly)
  - IDNCPIALLMINMEI → ID_INFLATION (Indonesia CPI All Items, monthly)

All ``recorded_at`` values are stored as TIMESTAMPTZ in UTC per AGENTS.md §2.
yfinance daily bars carry a timezone-aware index (America/New_York for US
exchanges); we normalize to UTC before insert. FRED series are date-only
(monthly); we anchor them at 00:00:00 UTC.

Idempotent: uses PostgreSQL ``ON CONFLICT (indicator_code, recorded_at)
DO NOTHING`` so re-runs only insert new rows.

Usage:
    ENV=research uv run python scripts/fetch_macroeconomic_indicators.py
    ENV=research uv run python scripts/fetch_macroeconomic_indicators.py --years 2
    ENV=research uv run python scripts/fetch_macroeconomic_indicators.py --skip-fred
    ENV=research uv run python scripts/fetch_macroeconomic_indicators.py --skip-yfinance
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from market.data.rate_limit import DynamicRateLimiter
from market.db.engine import get_sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Dynamic rate limiter — adaptive backoff on HTTP 429 to avoid IP bans
# from yfinance/FRED. Starts at 0.8s, backs off up to 30s on errors.
limiter = DynamicRateLimiter(initial_delay=0.8, min_delay=0.3, max_delay=30.0)

# ── yfinance macro ticker registry ────────────────────────────────────────────
YF_INDICATORS = {
    "IDR=X": {
        "indicator_code": "USD_IDR",
        "name": "USD/IDR Exchange Rate",
        "region": "GLOBAL",
    },
    "^VIX": {
        "indicator_code": "VIX_INDEX",
        "name": "CBOE Volatility Index (Fear Index)",
        "region": "US",
    },
    "GC=F": {
        "indicator_code": "GOLD_PRICE",
        "name": "Gold Futures (COMEX)",
        "region": "GLOBAL",
    },
    "BZ=F": {
        "indicator_code": "BRENT_CRUDE",
        "name": "Brent Crude Oil Futures (ICE)",
        "region": "GLOBAL",
    },
}

# ── FRED series registry (optional, no API key — CSV download) ────────────────
FRED_INDICATORS = {
    "FEDFUNDS": {
        "indicator_code": "FED_RATE",
        "name": "US Federal Funds Effective Rate",
        "region": "US",
    },
    "INTDSBIDM193N": {
        "indicator_code": "BI_RATE",
        "name": "Bank Indonesia 7-Day Reverse Repo Rate",
        "region": "ID",
    },
    "CPIAUCSL": {
        "indicator_code": "US_INFLATION",
        "name": "US CPI All Urban Consumers (Inflation proxy)",
        "region": "US",
    },
    "IDNCPIALLMINMEI": {
        "indicator_code": "ID_INFLATION",
        "name": "Indonesia CPI All Items (Inflation proxy)",
        "region": "ID",
    },
}


def fetch_yf_indicator(ticker: str, years: int) -> list[dict]:
    """Fetch daily historical close from yfinance, normalized to UTC.

    Returns list of dicts: {recorded_at: datetime(UTC), value: float}.
    """
    limiter.wait()
    start = (datetime.now(UTC) - timedelta(days=365 * years)).date()
    logger.info("Fetching yfinance %s (start=%s)", ticker, start)
    try:
        df = yf.download(
            ticker,
            start=start.isoformat(),
            auto_adjust=True,
            progress=False,
            interval="1d",
        )
    except Exception as exc:
        logger.error("yfinance download failed for %s: %s", ticker, exc)
        return []

    if df is None or df.empty:
        logger.warning("  %s: no data returned", ticker)
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    results: list[dict] = []
    for ts, row in df.iterrows():
        close = row.get("Close")
        if pd.isna(close):
            continue
        # yfinance DatetimeIndex is tz-aware (e.g. America/New_York for US).
        # Convert to UTC for universal TIMESTAMPTZ storage.
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            ts_utc = ts.astimezone(UTC)
        else:
            ts_utc = pd.Timestamp(ts).tz_localize("UTC").to_pydatetime()
        results.append({
            "recorded_at": ts_utc.to_pydatetime() if hasattr(ts_utc, "to_pydatetime") else ts_utc,
            "value": float(close),
        })
    return results


def fetch_fred_series(fred_id: str) -> list[dict]:
    """Download a FRED series as CSV; return list of {recorded_at, value}.

    FRED dates are monthly/annual (date-only). We anchor at 00:00:00 UTC.
    """
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    logger.info("Fetching FRED series %s", fred_id)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            csv_data = resp.read().decode("utf-8")
    except Exception as exc:
        logger.error("FRED download failed for %s: %s", fred_id, exc)
        return []

    df = pd.read_csv(io.StringIO(csv_data))
    if df.empty or len(df.columns) < 2:
        return []

    date_col, val_col = df.columns[0], df.columns[1]
    results: list[dict] = []
    for _, row in df.iterrows():
        d, v = row[date_col], row[val_col]
        if pd.isna(v) or v == ".":
            continue
        try:
            d_date = date.fromisoformat(str(d))
            ts_utc = datetime(d_date.year, d_date.month, d_date.day, tzinfo=UTC)
            results.append({"recorded_at": ts_utc, "value": float(v)})
        except (ValueError, TypeError):
            continue
    return results


def upsert_indicator(session, indicator_code: str, name: str,
                     region: str, data: list[dict]) -> int:
    """Idempotent upsert into macroeconomic_indicators. Returns inserted count."""
    if not data:
        return 0

    inserted = 0
    for point in data:
        result = session.execute(text("""
            INSERT INTO macroeconomic_indicators
                (indicator_code, name, region, recorded_at, value)
            VALUES (:code, :name, :region, :ts, :val)
            ON CONFLICT (indicator_code, recorded_at) DO NOTHING
            RETURNING id
        """), {
            "code": indicator_code,
            "name": name,
            "region": region,
            "ts": point["recorded_at"],
            "val": point["value"],
        })
        if result.scalar_one_or_none() is not None:
            inserted += 1

    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch macroeconomic indicators → macroeconomic_indicators table")
    parser.add_argument("--years", type=int, default=2,
                        help="Years of history to fetch from yfinance (default: 2)")
    parser.add_argument("--skip-yfinance", action="store_true",
                        help="Skip yfinance indicators (USD/IDR, VIX, Gold, Brent)")
    parser.add_argument("--skip-fred", action="store_true",
                        help="Skip FRED indicators (Fed Rate, BI Rate, inflation)")
    args = parser.parse_args()

    session = get_sessionmaker()()
    total_inserted = 0

    # ── yfinance: daily global macro ────────────────────────────────
    if not args.skip_yfinance:
        logger.info("=" * 60)
        logger.info("Fetching yfinance macro indicators (%d years)", args.years)
        logger.info("=" * 60)
        for ticker, meta in YF_INDICATORS.items():
            data = fetch_yf_indicator(ticker, args.years)
            if data:
                inserted = upsert_indicator(
                    session, meta["indicator_code"], meta["name"],
                    meta["region"], data)
                logger.info("  %s (%s): %d fetched, %d new rows",
                            meta["indicator_code"], ticker, len(data), inserted)
                total_inserted += inserted
            else:
                logger.warning("  %s (%s): no data", meta["indicator_code"], ticker)
        session.commit()

    # ── FRED: monthly rates & inflation ─────────────────────────────
    if not args.skip_fred:
        logger.info("=" * 60)
        logger.info("Fetching FRED macro indicators (full history)")
        logger.info("=" * 60)
        for fred_id, meta in FRED_INDICATORS.items():
            data = fetch_fred_series(fred_id)
            if data:
                inserted = upsert_indicator(
                    session, meta["indicator_code"], meta["name"],
                    meta["region"], data)
                logger.info("  %s (%s): %d fetched, %d new rows",
                            meta["indicator_code"], fred_id, len(data), inserted)
                total_inserted += inserted
            else:
                logger.warning("  %s (%s): no data", meta["indicator_code"], fred_id)
        session.commit()

    # ── Summary ─────────────────────────────────────────────────────
    summary = session.execute(text("""
        SELECT indicator_code, region, count(*) AS rows,
               min(recorded_at) AS first_at, max(recorded_at) AS last_at
        FROM macroeconomic_indicators
        GROUP BY indicator_code, region
        ORDER BY indicator_code
    """)).fetchall()
    logger.info("=" * 60)
    logger.info("Ingestion complete. %d new rows inserted this run.", total_inserted)
    logger.info("Table contents:")
    for row in summary:
        logger.info("  %-16s %-7s %6d rows  %s → %s",
                    row[0], row[1], row[2],
                    row[3].strftime("%Y-%m-%d") if row[3] else "-",
                    row[4].strftime("%Y-%m-%d") if row[4] else "-")
    logger.info("=" * 60)

    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
