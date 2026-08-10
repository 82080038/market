"""Backfill fundamental data from yfinance for IDX tickers.

Fetches PE, PB, ROE, DER, EPS, revenue, net income, market cap, beta,
profit margins, and other fundamental metrics for all active IDX tickers.
Stores in PostgreSQL fundamental_data table.

Usage:
    uv run python scripts/backfill_fundamentals.py [--tickers BBCA.JK,BBRI.JK]
    uv run python scripts/backfill_fundamentals.py [--limit 50]
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, date, datetime
from decimal import Decimal

import yfinance as yf
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PG_URL = "postgresql://petrick:market_dev@localhost:5432/market"

# Fields to extract from yfinance .info
INFO_FIELDS = {
    "trailingPE": "pe",
    "priceToBook": "pb",
    "returnOnEquity": "roe",
    "debtToEquity": "der",
    "dividendYield": "dividend_yield",
    "trailingEps": "eps",
    "marketCap": "market_cap",
    "sharesOutstanding": "shares_outstanding",
    "floatShares": "free_float",
    "beta": "beta",
    "profitMargins": "profit_margin",
    "operatingMargins": "operating_margin",
    "currentRatio": "current_ratio",
    "quickRatio": "quick_ratio",
    "bookValue": "book_value_per_share",
    "returnOnAssets": "return_on_assets",
    "revenueGrowth": "revenue_growth",
    "earningsGrowth": "earnings_growth",
    "sector": "sector",
    "industry": "industry",
    # Banking-specific metrics (yfinance exposes these for financials sector)
    # NPL ratio is not directly available from yfinance; computed from
    # nonPerformingLoans / totalLoans if both are present
    "nonPerformingLoans": "_npl_raw",
    "totalLoans": "_total_loans_raw",
    "capitalAdequacyRatio": "car",
    "loanToDepositRatio": "loan_to_deposit",
    "netInterestMargin": "nim",
}

# Fields from .financials (annual)
FINANCIAL_FIELDS = {
    "Total Revenue": "revenue",
    "Net Income": "net_income",
    "Total Assets": "total_assets",
    "Total Debt": "total_debt",
}


def safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def fetch_fundamental(ticker: str) -> dict | None:
    """Fetch fundamental data from yfinance for a single ticker."""
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info
        if not info or len(info) < 5:
            return None

        result = {"ticker": ticker, "date": date.today()}

        for yf_key, db_key in INFO_FIELDS.items():
            val = info.get(yf_key)
            if isinstance(val, (int, float)):
                result[db_key] = safe_float(val)
            elif isinstance(val, str):
                result[db_key] = val if db_key in ("sector", "industry") else None

        # Try to get annual financials
        try:
            financials = yf_ticker.financials
            if financials is not None and not financials.empty:
                latest_col = financials.columns[0]
                for fin_key, db_key in FINANCIAL_FIELDS.items():
                    if fin_key in financials.index:
                        result[db_key] = safe_float(financials.loc[fin_key, latest_col])
        except Exception:
            pass

        # Calculate ROE if not provided
        if result.get("roe") is None and result.get("net_income") and result.get("total_assets"):
            if result["total_assets"] > 0:
                result["roe"] = result["net_income"] / result["total_assets"] * 100

        # Calculate NPL ratio if raw values are available
        npl_raw = result.pop("_npl_raw", None)
        total_loans_raw = result.pop("_total_loans_raw", None)
        if npl_raw is not None and total_loans_raw and total_loans_raw > 0:
            result["npl_ratio"] = (npl_raw / total_loans_raw) * 100

        return result

    except Exception as e:
        logger.warning("  Failed %s: %s", ticker, e)
        return None


def upsert_fundamental(conn, data: dict):
    """Insert or update fundamental data."""
    cols = []
    vals = []
    for k, v in data.items():
        if v is not None:
            cols.append(k)
            if isinstance(v, str):
                vals.append(f"'{v.replace(chr(39), chr(39)*2)}'")
            elif isinstance(v, (int, float)):
                vals.append(str(v))
            elif isinstance(v, date):
                vals.append(f"'{v.isoformat()}'")
            else:
                vals.append(f"'{str(v)}'")

    if not cols:
        return

    # Skip if only ticker/date present (no actual fundamental data)
    data_cols = [c for c in cols if c not in ("ticker", "date", "source")]
    if not data_cols:
        return

    col_list = ", ".join(cols)
    val_list = ", ".join(vals)

    # Use ON CONFLICT for upsert
    conn.execute(text(f"""
        INSERT INTO fundamental_data ({col_list})
        VALUES ({val_list})
        ON CONFLICT (ticker, date, source) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in data_cols)}
    """))


def main():
    parser = argparse.ArgumentParser(description="Backfill fundamental data from yfinance")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers (default: all active IDX)")
    parser.add_argument("--limit", type=int, help="Limit number of tickers")
    args = parser.parse_args()

    engine = create_engine(PG_URL, echo=False, future=True, pool_pre_ping=True)

    with engine.connect() as conn:
        if args.tickers:
            tickers = [t.strip() for t in args.tickers.split(",")]
        else:
            rows = conn.execute(text(
                "SELECT ticker FROM instruments WHERE is_active = true AND ticker LIKE '%.JK' ORDER BY ticker"
            )).fetchall()
            tickers = [r[0] for r in rows]

        if args.limit:
            tickers = tickers[:args.limit]

        logger.info("Backfilling fundamentals for %d tickers...", len(tickers))

        success = 0
        failed = 0
        no_data = 0

        for i, ticker in enumerate(tickers):
            if (i + 1) % 50 == 0:
                logger.info("  Progress: %d/%d (success=%d, no_data=%d, failed=%d)",
                            i + 1, len(tickers), success, no_data, failed)

            data = fetch_fundamental(ticker)
            if data is None:
                no_data += 1
                continue

            with engine.begin() as txn:
                upsert_fundamental(txn, data)
            success += 1

            # Rate limit: 1 request per second
            time.sleep(0.5)

        logger.info("\n" + "=" * 70)
        logger.info("FUNDAMENTAL BACKFILL COMPLETE")
        logger.info("  Total tickers: %d", len(tickers))
        logger.info("  Success: %d", success)
        logger.info("  No data: %d", no_data)
        logger.info("  Failed: %d", failed)
        logger.info("=" * 70)

    engine.dispose()


if __name__ == "__main__":
    main()
