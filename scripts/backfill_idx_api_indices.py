"""Backfill IDX index daily close prices from idx.co.id API.

Uses cloudscraper to bypass Cloudflare, then fetches monthly batches
from the IDX DigitalStatistic API. Data covers 2021-01 onwards (when
IDX sectoral indices were launched).

Only inserts rows for tickers that don't already have OHLCV data.
Does NOT overwrite existing yfinance data (^JKSE, ^JKLQ45, etc.).

Usage:
    DB_PATH=data/market_research.db python scripts/backfill_idx_api_indices.py
    DB_PATH=data/market_research.db python scripts/backfill_idx_api_indices.py --start-year 2024
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import cloudscraper
from sqlalchemy import select, text

from market.config import settings
from market.db.engine import get_sessionmaker
from market.db.models import InstrumentMaster, OHLCV

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Map IDX API index names to DB tickers
# Only include indices we want to backfill (skip those already have yfinance data)
INDEX_NAME_MAP: dict[str, str] = {
    # Sectoral indices (no yfinance data)
    "IDX Sector Energy": "IDXENERGY.JK",
    "IDX Sector Basic Materials": "IDXBASIC.JK",
    "IDX Sector Industrials": "IDXINDUST.JK",
    "IDX Sector Consumer Non-Cyclicals": "IDXNONCYC.JK",
    "IDX Sector Consumer Cyclicals": "IDXCYCLIC.JK",
    "IDX Sector Healthcare": "IDXHEALTH.JK",
    "IDX Sector Financials": "IDXFINANCE.JK",
    "IDX Sector Properties & Real Estate": "IDXPROPER.JK",
    "IDX Sector Technology": "IDXTECHNO.JK",
    "IDX Sector Infrastructures": "IDXINFRA.JK",
    "IDX Sector Transportation & Logistic": "IDXTRANS.JK",
    # Other indices with no yfinance data
    "Indeks IDX30": "IDX30.JK",
    "Indeks IDX80": "IDX80.JK",
    "Jakarta Islamic Index": "IDXJII.JK",
    "KOMPAS100": "KOMPAS100.JK",
    "BISNIS-27": "BISNIS27.JK",
    "PEFINDO25 Index": "PEFINDO25.JK",
    "SRI-KEHATI Index": "SRIKEHATI.JK",
    "ESG Sector Leaders IDX KEHATI": "ESGQKEHATI.JK",
    "ESG Quality 45 IDX KEHATI": "ESGSKEHATI.JK",
    "Indeks Saham Syariah Indonesia": "ISSI.JK",
    "Indeks infobank15": "INFOBANK15.JK",
    "IDX-PEFINDO Prime Bank": "PRIMBANK10.JK",
    "SMinfra18": "SMINFRA18.JK",
    "Indeks MNC36": "MNC36.JK",
    "Indeks Investor33": "INVESTOR33.JK",
    "Pefindo I-Grade": "IGRADE.JK",
    "IDX SMC Composite": "IDXSMCCOM.JK",
    "IDX SMC Liquid": "IDXSMCLIQ.JK",
    "IDX High Dividend 20": "IDXHIDIV20.JK",
    "IDX BUMN20": "IDXBUMN20.JK",
    "Jakarta Islamic Index 70": "JII70.JK",
    "IDX Value30": "IDXV30.JK",
    "IDX Growth30": "IDXG30.JK",
    "IDX Quality30": "IDXQ30.JK",
    "IDX ESG Leaders": "IDXESGL.JK",
    "IDX LQ45 Low Carbon Leaders": "IDXLQ45LCL.JK",
    "IDX-MES BUMN 17": "IDXMESBUMN.JK",
    "IDX Sharia Growth": "IDXSHAGROW.JK",
    "Main Board Index": "MBX.JK",
    "Development Board Index": "DBX.JK",
    "Acceleration Board Index": "ABX.JK",
    "IDX Cyclical Economy 30": "IDXCYCLIC30.JK",
    "IDX-Infovesta Multi-Factor 28": "IDXVESTA28.JK",
}

# Indices already covered by yfinance — skip these
SKIP_TICKERS: set[str] = {"^JKSE", "^JKLQ45"}

IDX_API_URL = (
    "https://www.idx.co.id/primary/DigitalStatistic/GetApiData"
    "?urlName=LINK_DAILY_IDX_INDICES&query={query}&isPrint=False&cumulative=false"
)


def create_scraper():
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "desktop": True},
        delay=10,
    )


def init_session(scraper) -> bool:
    """Initialize session by visiting main page and validating."""
    try:
        r = scraper.get("https://www.idx.co.id/id", timeout=30)
        if r.status_code != 200:
            log.error("Failed to get session: HTTP %d", r.status_code)
            return False
        time.sleep(1)
        # Validate with GetIndexList
        r = scraper.get(
            "https://www.idx.co.id/primary/home/GetIndexList",
            headers={
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.idx.co.id/id",
            },
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            log.info("Session valid, %d indices available", len(data) if isinstance(data, list) else 0)
            return True
        log.error("Session validation failed: HTTP %d", r.status_code)
        return False
    except Exception as e:
        log.error("Session init error: %s", e)
        return False


def fetch_month(scraper, year: int, month: int) -> dict[str, list[dict]]:
    """Fetch one month of index data. Returns {index_name: [{date, close}, ...]}."""
    query_obj = {"year": year, "month": month, "quarter": 0, "type": "monthly"}
    query_b64 = base64.b64encode(json.dumps(query_obj).encode()).decode()
    url = IDX_API_URL.format(query=query_b64)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.idx.co.id/id",
    }
    try:
        r = scraper.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            log.warning("Fetch %d-%02d: HTTP %d", year, month, r.status_code)
            return {}
        data = r.json()
        result = {}
        for item in data.get("data", []):
            name = item.get("Name", "")
            months = item.get("months", [])
            if name and months:
                result[name] = [
                    {"date": m["date"], "close": m["close"]["value"]}
                    for m in months
                    if m.get("close") and m["close"].get("value") is not None
                ]
        return result
    except Exception as e:
        log.error("Fetch %d-%02d error: %s", year, month, e)
        return {}


def ensure_instrument_master(session, ticker: str, name: str) -> None:
    """Ensure instrument_master has the index entry."""
    existing = session.get(InstrumentMaster, ticker)
    if existing:
        if not existing.name:
            existing.name = name
            session.commit()
        return
    session.add(InstrumentMaster(
        ticker=ticker,
        market_mic="XIDX",
        asset_class="index",
        name=name,
        base_currency="IDR",
        reporting_currency="IDR",
        is_active=True,
    ))
    session.commit()
    log.info("Added instrument_master: %s (%s)", ticker, name)


def insert_ohlcv(session, ticker: str, records: list[dict]) -> int:
    """Insert OHLCV records (close price only, open=high=low=close, volume=0).
    
    Only inserts if no existing row for that date.
    Returns number of rows inserted.
    """
    inserted = 0
    for rec in records:
        d = rec["date"]
        close = rec["close"]
        # Check if row already exists
        existing = session.execute(
            select(OHLCV).where(
                OHLCV.ticker == ticker,
                OHLCV.timeframe == "1d",
                text("date(ohlcv.timestamp) = :d"),
            ),
            {"d": d},
        ).scalar_one_or_none()

        if existing:
            continue

        ts = datetime.strptime(d, "%Y-%m-%d")
        session.add(OHLCV(
            ticker=ticker,
            timestamp=ts,
            timeframe="1d",
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0,
            source="idx_api",
        ))
        inserted += 1

    if inserted:
        session.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill IDX index data from idx.co.id API")
    parser.add_argument("--start-year", type=int, default=2021, help="Start year (default: 2021)")
    parser.add_argument("--end-year", type=int, default=2026, help="End year (default: 2026)")
    parser.add_argument("--end-month", type=int, default=8, help="End month (default: 8)")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests (seconds)")
    args = parser.parse_args()

    log.info("Database: %s", settings.resolved_db_path)
    log.info("Date range: %d-01 to %d-%02d", args.start_year, args.end_year, args.end_month)

    scraper = create_scraper()
    if not init_session(scraper):
        log.error("Failed to initialize IDX API session. Aborting.")
        sys.exit(1)

    Session = get_sessionmaker()
    session = Session()

    total_inserted = 0
    total_months = 0
    total_errors = 0

    # Track which tickers we've seen
    seen_tickers: set[str] = set()

    try:
        year = args.start_year
        month = 1
        while (year < args.end_year) or (year == args.end_year and month <= args.end_month):
            total_months += 1
            log.info("[%d/%d] Fetching %d-%02d...", total_months,
                     (args.end_year - args.start_year) * 12 + args.end_month,
                     year, month)

            month_data = fetch_month(scraper, year, month)

            if not month_data:
                log.warning("  No data for %d-%02d", year, month)
                total_errors += 1
            else:
                month_inserted = 0
                for idx_name, records in month_data.items():
                    ticker = INDEX_NAME_MAP.get(idx_name)
                    if not ticker:
                        continue  # Skip indices not in our map (e.g. Composite Index, LQ45)

                    if ticker in SKIP_TICKERS:
                        continue  # Don't touch yfinance-covered indices

                    if ticker not in seen_tickers:
                        seen_tickers.add(ticker)
                        ensure_instrument_master(session, ticker, idx_name)

                    inserted = insert_ohlcv(session, ticker, records)
                    month_inserted += inserted

                total_inserted += month_inserted
                log.info("  %d indices, %d rows inserted", len(month_data), month_inserted)

            time.sleep(args.delay)

            # Next month
            month += 1
            if month > 12:
                month = 1
                year += 1

        log.info("=" * 60)
        log.info("Backfill complete!")
        log.info("  Months fetched: %d", total_months)
        log.info("  Total rows inserted: %d", total_inserted)
        log.info("  Indices covered: %d", len(seen_tickers))
        log.info("  Errors: %d", total_errors)

        # Print coverage summary
        log.info("\nCoverage by ticker:")
        for ticker in sorted(seen_tickers):
            count = session.execute(
                select(text("COUNT(*)")).where(
                    text("ticker = :t AND timeframe = '1d' AND source = 'idx_api'")
                ),
                {"t": ticker},
            ).scalar()
            dmin = session.execute(
                select(text("MIN(timestamp)")).where(
                    text("ticker = :t AND timeframe = '1d' AND source = 'idx_api'")
                ),
                {"t": ticker},
            ).scalar()
            dmax = session.execute(
                select(text("MAX(timestamp)")).where(
                    text("ticker = :t AND timeframe = '1d' AND source = 'idx_api'")
                ),
                {"t": ticker},
            ).scalar()
            log.info("  %s: %d rows, %s to %s", ticker, count,
                     str(dmin)[:10] if dmin else "N/A",
                     str(dmax)[:10] if dmax else "N/A")

    finally:
        session.close()


if __name__ == "__main__":
    main()
