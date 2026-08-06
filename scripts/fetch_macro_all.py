"""Fetch and populate macro economic data — both global and Indonesia.

This script addresses two priorities:
1. PRIORITAS 3: Macro Indonesia (BI Rate, CPI, GDP) from FRED CSV downloads.
2. PRIORITAS 4: Repopulate yfinance macro series (DXY, GOLD, OIL, US10Y, USD/IDR)
   with full historical data instead of just the last 5 days.

FRED series (no API key needed for CSV download):
  - INTDSBIDM193N: Indonesia Interest Rate (BI Rate equivalent)
  - IDNCPIALLMINMEI: Indonesia CPI All Items
  - NGDPRXDCID: Indonesia Real GDP (annual, domestic currency)

yfinance tickers for global macro:
  - ^TNX → US10Y yield
  - ^VIX → VIX
  - GC=F → Gold
  - CL=F → Crude Oil
  - IDR=X → USD/IDR
  - DX-Y.NYB → DXY (US Dollar Index)

Usage:
    ENV=research uv run python scripts/fetch_macro_all.py [--skip-fred] [--skip-yfinance]
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from datetime import UTC, date, datetime

import pandas as pd
import yfinance as yf
from sqlalchemy import select, text

from market.data.rate_limit import RateLimiter
from market.db.engine import get_sessionmaker
from market.db.models import MacroData

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

limiter = RateLimiter(max_calls=0.8)

# FRED series for Indonesia macro
FRED_SERIES = {
    "INTDSBIDM193N": {
        "series_name": "BI_RATE",
        "unit": "percent",
        "frequency": "monthly",
        "description": "Indonesia Interest Rate (BI Rate)",
    },
    "IDNCPIALLMINMEI": {
        "series_name": "ID_CPI",
        "unit": "index",
        "frequency": "monthly",
        "description": "Indonesia CPI All Items",
    },
    "NGDPRXDCID": {
        "series_name": "ID_GDP_REAL",
        "unit": "IDR",
        "frequency": "annual",
        "description": "Indonesia Real GDP",
    },
}

# yfinance tickers for global macro — mapped to macro_data series names
YF_MACRO_TICKERS = {
    "^TNX": {
        "series_name": "US10Y",
        "unit": "percent",
        "frequency": "daily",
    },
    "^VIX": {
        "series_name": "VIX",
        "unit": "index",
        "frequency": "daily",
    },
    "GC=F": {
        "series_name": "GOLD",
        "unit": "USD/oz",
        "frequency": "daily",
    },
    "CL=F": {
        "series_name": "CRUDE_OIL",
        "unit": "USD/barrel",
        "frequency": "daily",
    },
    "IDR=X": {
        "series_name": "USD_IDR",
        "unit": "IDR",
        "frequency": "daily",
    },
    "DX-Y.NYB": {
        "series_name": "DXY",
        "unit": "index",
        "frequency": "daily",
    },
}


def fetch_fred_series(fred_id: str) -> list[dict]:
    """Download a FRED series as CSV and return list of {date, value} dicts."""
    import urllib.request

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    logger.info("Fetching FRED series %s from %s", fred_id, url)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            csv_data = resp.read().decode("utf-8")
    except Exception as exc:
        logger.error("FRED download failed for %s: %s", fred_id, exc)
        return []

    df = pd.read_csv(io.StringIO(csv_data))
    if df.empty or len(df.columns) < 2:
        return []

    date_col = df.columns[0]
    val_col = df.columns[1]

    results = []
    for _, row in df.iterrows():
        d = row[date_col]
        v = row[val_col]
        if pd.isna(v) or v == ".":
            continue
        try:
            d_date = date.fromisoformat(str(d))
            results.append({"date": d_date, "value": float(v)})
        except (ValueError, TypeError):
            continue

    return results


def store_macro_series(session, series_name: str, data: list[dict],
                       unit: str, frequency: str, source: str) -> int:
    """Store macro data series. Returns count of new rows inserted."""
    inserted = 0
    for point in data:
        existing = session.execute(
            select(MacroData).where(
                MacroData.series_name == series_name,
                MacroData.date == point["date"],
                MacroData.source == source,
            )
        ).scalar_one_or_none()

        if existing:
            continue

        session.add(MacroData(
            series_name=series_name,
            date=point["date"],
            value=point["value"],
            unit=unit,
            source=source,
            frequency=frequency,
        ))
        inserted += 1

    return inserted


def fetch_yf_macro(ticker: str, series_name: str) -> list[dict]:
    """Fetch full historical daily data from yfinance for a macro ticker."""
    limiter.acquire()
    logger.info("Fetching yfinance macro: %s → %s", ticker, series_name)
    try:
        df = yf.download(
            ticker,
            period="max",
            auto_adjust=True,
            progress=False,
            interval="1d",
        )
    except Exception as exc:
        logger.error("yfinance download failed for %s: %s", ticker, exc)
        return []

    if df is None or df.empty:
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    results = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("Close")):
            continue
        d = ts.date() if hasattr(ts, "date") else ts
        results.append({"date": d, "value": float(row["Close"])})

    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch macro data — Indonesia (FRED) + global (yfinance)")
    parser.add_argument("--skip-fred", action="store_true", help="Skip FRED Indonesia macro")
    parser.add_argument("--skip-yfinance", action="store_true", help="Skip yfinance global macro")
    args = parser.parse_args()

    session = get_sessionmaker()()

    # ── FRED: Indonesia macro ──────────────────────────────────
    if not args.skip_fred:
        logger.info("=" * 60)
        logger.info("Fetching Indonesia macro from FRED")
        logger.info("=" * 60)

        for fred_id, meta in FRED_SERIES.items():
            data = fetch_fred_series(fred_id)
            if data:
                inserted = store_macro_series(
                    session,
                    series_name=meta["series_name"],
                    data=data,
                    unit=meta["unit"],
                    frequency=meta["frequency"],
                    source="fred",
                )
                logger.info("  %s (%s): %d points fetched, %d new rows inserted",
                            meta["series_name"], fred_id, len(data), inserted)
            else:
                logger.warning("  %s (%s): no data fetched", meta["series_name"], fred_id)

        session.commit()

    # ── yfinance: Global macro ─────────────────────────────────
    if not args.skip_yfinance:
        logger.info("=" * 60)
        logger.info("Repopulating global macro from yfinance (full history)")
        logger.info("=" * 60)

        for ticker, meta in YF_MACRO_TICKERS.items():
            data = fetch_yf_macro(ticker, meta["series_name"])
            if data:
                inserted = store_macro_series(
                    session,
                    series_name=meta["series_name"],
                    data=data,
                    unit=meta["unit"],
                    frequency=meta["frequency"],
                    source="yahoo_finance",
                )
                logger.info("  %s (%s): %d points fetched, %d new rows inserted",
                            meta["series_name"], ticker, len(data), inserted)
            else:
                logger.warning("  %s (%s): no data fetched", meta["series_name"], ticker)

        session.commit()

    # ── Summary ────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("MACRO DATA SUMMARY")
    logger.info("=" * 60)

    rows = session.execute(
        text(
            "SELECT series_name, source, COUNT(*) as cnt, "
            "MIN(date) as min_date, MAX(date) as max_date "
            "FROM macro_data GROUP BY series_name, source ORDER BY series_name"
        )
    ).fetchall()

    for r in rows:
        logger.info("  %-15s %-15s %6d rows  %s → %s", r[0], r[1], r[2], r[3], r[4])

    session.close()


if __name__ == "__main__":
    main()
