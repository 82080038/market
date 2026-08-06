"""Fetch fundamental data from yfinance and store to database.

yfinance Ticker.info provides snapshot fundamental data (P/E, P/B, ROE, DER,
dividend yield, EPS, market cap, etc). This pipeline fetches that data for
all active IDX tickers and stores it as a dated snapshot in fundamental_data.

Since yfinance only provides current snapshot (no historical), running this
weekly builds up historical fundamental data gradually over time.

Usage:
    ENV=research uv run python scripts/fetch_fundamental.py [--tickers AAA,BBB]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import yfinance as yf
from sqlalchemy import select, text

from market.data.rate_limit import RateLimiter
from market.db.engine import get_sessionmaker
from market.db.models import FundamentalData

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

limiter = RateLimiter(max_calls=1.0)


# yfinance info keys → FundamentalData columns
INFO_MAP = {
    "trailingPE": "pe",
    "priceToBook": "pb",
    "returnOnEquity": "roe",
    "debtToEquity": "der",
    "dividendYield": "dividend_yield",
    "trailingEps": "eps",
    "bookValue": "book_value_per_share",
    "totalRevenue": "revenue",
    "netIncomeToCommon": "net_income",
    "totalAssets": "total_assets",
    "totalDebt": "total_liabilities",
    "totalCash": "cash_flow",
    "marketCap": "market_cap",
}


def fetch_fundamental_for_ticker(ticker: str) -> dict | None:
    """Fetch fundamental data from yfinance for a single ticker."""
    limiter.acquire()
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
    except Exception as exc:
        logger.error("yfinance info failed for %s: %s", ticker, exc)
        return None

    if not info:
        return None

    result = {}
    for yf_key, db_col in INFO_MAP.items():
        val = info.get(yf_key)
        if val is not None:
            result[db_col] = float(val)

    return result if result else None


def store_fundamental(session, ticker: str, data: dict, fetch_date: date) -> bool:
    """Store fundamental data snapshot. Returns True if inserted."""
    # Check if already exists for this date
    existing = session.execute(
        select(FundamentalData).where(
            FundamentalData.ticker == ticker,
            FundamentalData.date == fetch_date,
            FundamentalData.source == "yahoo_finance",
        )
    ).scalar_one_or_none()

    if existing:
        return False

    session.add(FundamentalData(
        ticker=ticker,
        date=fetch_date,
        pe=Decimal(str(data["pe"])) if "pe" in data else None,
        pb=Decimal(str(data["pb"])) if "pb" in data else None,
        roe=Decimal(str(data["roe"])) if "roe" in data else None,
        der=Decimal(str(data["der"])) if "der" in data else None,
        dividend_yield=Decimal(str(data["dividend_yield"])) if "dividend_yield" in data else None,
        eps=Decimal(str(data["eps"])) if "eps" in data else None,
        book_value_per_share=Decimal(str(data["book_value_per_share"])) if "book_value_per_share" in data else None,
        revenue=Decimal(str(data["revenue"])) if "revenue" in data else None,
        net_income=Decimal(str(data["net_income"])) if "net_income" in data else None,
        total_assets=Decimal(str(data["total_assets"])) if "total_assets" in data else None,
        total_liabilities=Decimal(str(data["total_liabilities"])) if "total_liabilities" in data else None,
        cash_flow=Decimal(str(data["cash_flow"])) if "cash_flow" in data else None,
        market_cap=Decimal(str(data["market_cap"])) if "market_cap" in data else None,
        source="yahoo_finance",
    ))
    return True


def main():
    parser = argparse.ArgumentParser(description="Fetch fundamental data from yfinance")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    args = parser.parse_args()

    session = get_sessionmaker()()
    fetch_date = datetime.now(UTC).date()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        rows = session.execute(
            text(
                "SELECT ticker FROM instrument_master "
                "WHERE market_mic = 'XIDX' AND asset_class = 'equity' AND is_active = 1 "
                "ORDER BY ticker"
            )
        ).fetchall()
        tickers = [f"{r[0]}.JK" for r in rows]

    total = len(tickers)
    logger.info("Fetching fundamental data for %d tickers (date=%s)", total, fetch_date)

    inserted = 0
    skipped = 0
    failed = 0
    empty = 0

    for i, ticker in enumerate(tickers):
        data = fetch_fundamental_for_ticker(ticker)

        if data is None:
            failed += 1
            if (i + 1) % 50 == 0:
                logger.info("[%d/%d] %s: failed", i + 1, total, ticker)
            continue

        if not data:
            empty += 1
            if (i + 1) % 50 == 0:
                logger.info("[%d/%d] %s: empty info", i + 1, total, ticker)
            continue

        was_inserted = store_fundamental(session, ticker, data, fetch_date)
        if was_inserted:
            inserted += 1
            if (i + 1) % 50 == 0:
                logger.info("[%d/%d] %s: +1 inserted | Running: ins=%d, skip=%d, fail=%d, empty=%d",
                            i + 1, total, ticker, inserted, skipped, failed, empty)
        else:
            skipped += 1

        if (i + 1) % 100 == 0:
            session.commit()

    session.commit()

    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("  Total tickers: %d", total)
    logger.info("  Inserted: %d", inserted)
    logger.info("  Skipped (already exists): %d", skipped)
    logger.info("  Failed: %d", failed)
    logger.info("  Empty: %d", empty)

    count = session.execute(text("SELECT COUNT(*) FROM fundamental_data")).scalar()
    dates = session.execute(text("SELECT COUNT(DISTINCT date) FROM fundamental_data")).scalar()
    logger.info("  fundamental_data table: %d rows, %d dates", count, dates)

    session.close()


if __name__ == "__main__":
    main()
