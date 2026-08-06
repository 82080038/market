"""Backfill quarterly fundamental history from yfinance.

yfinance Ticker.quarterly_financials / quarterly_balance_sheet / quarterly_cashflow
provide ~8 quarters of historical data. This script fetches that for all active
IDX tickers and stores each quarter as a row in fundamental_data with
fiscal_year and quarter populated.

Usage:
    ENV=research uv run python scripts/backfill_fundamental_quarterly.py [--tickers AAA,BBB] [--limit N]
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

limiter = RateLimiter(max_calls=0.8)


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def _quarter_from_date(d: date) -> str:
    month = d.month
    if month <= 3:
        return "Q1"
    elif month <= 6:
        return "Q2"
    elif month <= 9:
        return "Q3"
    return "Q4"


def fetch_quarterly_for_ticker(ticker: str) -> list[dict]:
    """Fetch quarterly fundamental data from yfinance for a single ticker.

    Returns a list of dicts, one per quarter, with keys matching
    FundamentalData columns.
    """
    limiter.acquire()
    try:
        t = yf.Ticker(ticker)
        q_inc = t.quarterly_income_stmt
        q_bs = t.quarterly_balance_sheet
        q_cf = t.quarterly_cashflow
        info = t.info
    except Exception as exc:
        logger.error("yfinance quarterly failed for %s: %s", ticker, exc)
        return []

    results: list[dict] = []
    all_dates: set[str] = set()

    if q_inc is not None and not q_inc.empty:
        all_dates.update(str(c.date()) for c in q_inc.columns)
    if q_bs is not None and not q_bs.empty:
        all_dates.update(str(c.date()) for c in q_bs.columns)
    if q_cf is not None and not q_cf.empty:
        all_dates.update(str(c.date()) for c in q_cf.columns)

    if not all_dates:
        return []

    market_cap = _safe_float(info.get("marketCap")) if info else None

    for qdate_str in sorted(all_dates, reverse=True):
        qdate = date.fromisoformat(qdate_str)
        row: dict = {"date": qdate}

        if q_inc is not None and not q_inc.empty and qdate_str in [str(c.date()) for c in q_inc.columns]:
            col = qdate_str
            row["revenue"] = _safe_float(q_inc.loc["Total Revenue", col]) if "Total Revenue" in q_inc.index else None
            row["net_income"] = _safe_float(q_inc.loc["Net Income", col]) if "Net Income" in q_inc.index else None
            row["eps"] = _safe_float(q_inc.loc["Diluted EPS", col]) if "Diluted EPS" in q_inc.index else None

        if q_bs is not None and not q_bs.empty and qdate_str in [str(c.date()) for c in q_bs.columns]:
            col = qdate_str
            row["total_assets"] = _safe_float(q_bs.loc["Total Assets", col]) if "Total Assets" in q_bs.index else None
            row["total_liabilities"] = _safe_float(q_bs.loc["Total Liab", col]) if "Total Liab" in q_bs.index else None
            row["book_value_per_share"] = _safe_float(q_bs.loc["Book Value", col]) if "Book Value" in q_bs.index else None

        if q_cf is not None and not q_cf.empty and qdate_str in [str(c.date()) for c in q_cf.columns]:
            col = qdate_str
            row["cash_flow"] = _safe_float(q_cf.loc["Total Cash From Operating Activities", col]) if "Total Cash From Operating Activities" in q_cf.index else None

        row["market_cap"] = market_cap
        row["fiscal_year"] = qdate.year
        row["quarter"] = _quarter_from_date(qdate)

        results.append(row)

    return results


def store_quarterly(session, ticker: str, quarters: list[dict]) -> int:
    """Store quarterly fundamental data. Returns count of new rows inserted."""
    inserted = 0
    for q in quarters:
        existing = session.execute(
            select(FundamentalData).where(
                FundamentalData.ticker == ticker,
                FundamentalData.date == q["date"],
                FundamentalData.source == "yahoo_quarterly",
            )
        ).scalar_one_or_none()

        if existing:
            continue

        session.add(FundamentalData(
            ticker=ticker,
            date=q["date"],
            pe=None,
            pb=None,
            roe=None,
            der=None,
            dividend_yield=None,
            eps=Decimal(str(q["eps"])) if q.get("eps") else None,
            book_value_per_share=Decimal(str(q["book_value_per_share"])) if q.get("book_value_per_share") else None,
            revenue=Decimal(str(q["revenue"])) if q.get("revenue") else None,
            net_income=Decimal(str(q["net_income"])) if q.get("net_income") else None,
            total_assets=Decimal(str(q["total_assets"])) if q.get("total_assets") else None,
            total_liabilities=Decimal(str(q["total_liabilities"])) if q.get("total_liabilities") else None,
            cash_flow=Decimal(str(q["cash_flow"])) if q.get("cash_flow") else None,
            market_cap=Decimal(str(q["market_cap"])) if q.get("market_cap") else None,
            fiscal_year=q.get("fiscal_year"),
            quarter=q.get("quarter"),
            source="yahoo_quarterly",
        ))
        inserted += 1

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Backfill quarterly fundamental history from yfinance")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tickers")
    args = parser.parse_args()

    session = get_sessionmaker()()

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
        tickers = [r[0] if r[0].endswith(".JK") else f"{r[0]}.JK" for r in rows]

    if args.limit:
        tickers = tickers[:args.limit]

    total = len(tickers)
    logger.info("Backfilling quarterly fundamentals for %d tickers", total)

    inserted = 0
    skipped = 0
    failed = 0

    for i, ticker in enumerate(tickers):
        quarters = fetch_quarterly_for_ticker(ticker)

        if not quarters:
            failed += 1
            if (i + 1) % 50 == 0:
                logger.info("[%d/%d] %s: no quarterly data | ins=%d fail=%d",
                            i + 1, total, ticker, inserted, failed)
            continue

        new_rows = store_quarterly(session, ticker, quarters)
        inserted += new_rows
        skipped += len(quarters) - new_rows

        if (i + 1) % 50 == 0:
            logger.info("[%d/%d] %s: +%d quarters | Running: ins=%d skip=%d fail=%d",
                        i + 1, total, ticker, new_rows, inserted, skipped, failed)

        if (i + 1) % 20 == 0:
            session.commit()

    session.commit()

    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("  Total tickers: %d", total)
    logger.info("  Quarters inserted: %d", inserted)
    logger.info("  Quarters skipped (existing): %d", skipped)
    logger.info("  Tickers failed: %d", failed)

    count = session.execute(
        text("SELECT COUNT(*) FROM fundamental_data WHERE source = 'yahoo_quarterly'")
    ).scalar()
    dates = session.execute(
        text("SELECT COUNT(DISTINCT date) FROM fundamental_data WHERE source = 'yahoo_quarterly'")
    ).scalar()
    logger.info("  quarterly fundamental_data: %d rows, %d distinct dates", count, dates)

    session.close()


if __name__ == "__main__":
    main()
