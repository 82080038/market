"""Data ingestion script — fill identified gaps in PostgreSQL.

Fills:
1. stock_prices (XIDX) — latest OHLCV via yfinance (delta/incremental)
2. foreign_flow — not available via free API, skip (requires IDX scraper)
3. macro_data — refresh via MacroDataFetcher (World Bank, BPS)
4. macroeconomic_indicators — refresh via yfinance (VIX, Gold, Oil, USD/IDR)
5. fear_greed — refresh via alternative.me API

Usage:
    python scripts/fill_data_gaps.py --all
    python scripts/fill_data_gaps.py --stock-prices
    python scripts/fill_data_gaps.py --macro
    python scripts/fill_data_gaps.py --fear-greed
    python scripts/fill_data_gaps.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from market.db.engine import get_engine

logger = logging.getLogger(__name__)


def get_latest_stock_price_date(ticker: str | None = None) -> date:
    """Get the latest date in stock_prices for XIDX tickers."""
    engine = get_engine()
    with engine.connect() as conn:
        if ticker:
            r = conn.execute(text(
                "SELECT max(timestamp)::date FROM stock_prices WHERE ticker = :t"
            ), {"t": ticker})
        else:
            r = conn.execute(text(
                "SELECT max(timestamp)::date FROM stock_prices WHERE exchange_mic = 'XIDX'"
            ))
        d = r.scalar()
        return d if d else date(2020, 1, 1)


def get_xidx_tickers() -> list[str]:
    """Get all XIDX tickers from stock_prices."""
    engine = get_engine()
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT DISTINCT ticker FROM stock_prices WHERE exchange_mic = 'XIDX' ORDER BY ticker"
        ))
        return [row[0] for row in r]


def fill_stock_prices(dry_run: bool = False, batch_size: int = 50) -> dict:
    """Fill missing stock_prices for XIDX tickers via yfinance (delta)."""
    latest = get_latest_stock_price_date()
    today = date.today()
    gap_days = (today - latest).days

    logger.info("stock_prices: latest=%s, today=%s, gap=%d days", latest, today, gap_days)

    if gap_days <= 1:
        logger.info("stock_prices: already up to date (gap <= 1 day)")
        return {"table": "stock_prices", "action": "skip", "reason": f"Already up to date (latest={latest})"}

    tickers = get_xidx_tickers()
    logger.info("stock_prices: %d tickers to update", len(tickers))

    if dry_run:
        return {"table": "stock_prices", "action": "dry_run", "tickers": len(tickers), "gap_days": gap_days}

    engine = get_engine()
    total_inserted = 0
    errors = 0
    start_date = latest + timedelta(days=1)
    end_date = today

    # Process in batches to avoid memory issues
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        logger.info("  Batch %d/%d: %s...%s",
                    i // batch_size + 1,
                    (len(tickers) + batch_size - 1) // batch_size,
                    batch[0], batch[-1])

        for ticker in batch:
            try:
                df = yf.download(
                    ticker,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    auto_adjust=True,
                    progress=False,
                    interval="1d",
                )
                if df is None or df.empty:
                    continue

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                rows = []
                for ts, row in df.iterrows():
                    if pd.isna(row.get("Close")):
                        continue
                    ts_utc = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
                    if ts_utc.tzinfo is None:
                        ts_utc = ts_utc.replace(tzinfo=UTC)
                    rows.append({
                        "ticker": ticker,
                        "exchange_mic": "XIDX",
                        "timestamp": ts_utc,
                        "timeframe": "1d",
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]) if not pd.isna(row.get("Volume")) else 0,
                        "source": "yfinance",
                    })

                if not rows:
                    continue

                with engine.begin() as conn:
                    # Delete existing rows for this ticker in the date range, then insert
                    conn.execute(text(
                        "DELETE FROM stock_prices WHERE ticker = :t AND timestamp >= :start AND timestamp <= :end"
                    ), {"t": ticker, "start": start_date, "end": end_date})

                    for r in rows:
                        conn.execute(text("""
                            INSERT INTO stock_prices (ticker, exchange_mic, timestamp, timeframe, open, high, low, close, volume, source)
                            VALUES (:ticker, 'XIDX', :ts, '1d', :o, :h, :l, :c, :v, 'yfinance')
                        """), {
                            "ticker": r["ticker"], "ts": r["timestamp"],
                            "o": r["open"], "h": r["high"], "l": r["low"],
                            "c": r["close"], "v": r["volume"],
                        })
                    total_inserted += len(rows)

                time.sleep(0.5)  # rate limit

            except Exception as e:
                logger.warning("  Error fetching %s: %s", ticker, str(e)[:100])
                errors += 1

    logger.info("stock_prices: inserted %d rows, %d errors", total_inserted, errors)
    return {
        "table": "stock_prices",
        "action": "filled",
        "tickers_processed": len(tickers),
        "rows_inserted": total_inserted,
        "errors": errors,
        "date_range": f"{start_date} to {end_date}",
    }


def fill_macroeconomic_indicators(dry_run: bool = False) -> dict:
    """Fill macroeconomic_indicators via yfinance (VIX, Gold, Oil, USD/IDR, Brent)."""
    engine = get_engine()

    # Check latest dates per indicator
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT indicator_code, max(recorded_at)::date FROM macroeconomic_indicators GROUP BY indicator_code"
        ))
        latest_dates = {row[0]: row[1] for row in r}

    logger.info("macroeconomic_indicators: latest dates: %s", latest_dates)

    indicators = {
        "VIX_INDEX": "^VIX",
        "GOLD_PRICE": "GC=F",
        "BRENT_CRUDE": "BZ=F",
        "USD_IDR": "IDR=X",
    }

    if dry_run:
        return {"table": "macroeconomic_indicators", "action": "dry_run", "indicators": list(indicators.keys())}

    total_inserted = 0
    for indicator_code, yf_ticker in indicators.items():
        latest = latest_dates.get(indicator_code)
        if latest:
            start_date = latest + timedelta(days=1)
        else:
            start_date = date.today() - timedelta(days=30)

        if (date.today() - start_date).days <= 0:
            logger.info("  %s: already up to date", indicator_code)
            continue

        try:
            df = yf.download(
                yf_ticker,
                start=start_date.isoformat(),
                end=date.today().isoformat(),
                auto_adjust=True,
                progress=False,
                interval="1d",
            )
            if df is None or df.empty:
                logger.info("  %s: no new data", indicator_code)
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            with engine.begin() as conn:
                for ts, row in df.iterrows():
                    if pd.isna(row.get("Close")):
                        continue
                    ts_dt = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
                    if ts_dt.tzinfo is None:
                        ts_dt = ts_dt.replace(tzinfo=UTC)

                    conn.execute(text("""
                        INSERT INTO macroeconomic_indicators (indicator_code, name, recorded_at, value, region)
                        VALUES (:code, :name, :ts, :val, 'Global')
                        ON CONFLICT DO NOTHING
                    """), {
                        "code": indicator_code,
                        "name": indicator_code.replace("_", " ").title(),
                        "ts": ts_dt,
                        "val": float(row["Close"]),
                    })
                    total_inserted += 1

            logger.info("  %s: fetched %d rows from %s to today",
                        indicator_code, len(df), start_date)
            time.sleep(0.5)

        except Exception as e:
            logger.warning("  Error fetching %s: %s", indicator_code, str(e)[:100])

    logger.info("macroeconomic_indicators: inserted %d rows", total_inserted)
    return {
        "table": "macroeconomic_indicators",
        "action": "filled",
        "rows_inserted": total_inserted,
    }


def fill_fear_greed(dry_run: bool = False) -> dict:
    """Fill fear_greed from alternative.me API."""
    import requests

    engine = get_engine()

    # Check latest date
    with engine.connect() as conn:
        r = conn.execute(text("SELECT max(date) FROM fear_greed"))
        latest = r.scalar()

    logger.info("fear_greed: latest=%s", latest)

    if dry_run:
        return {"table": "fear_greed", "action": "dry_run", "latest": str(latest)}

    # Fetch from alternative.me
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=0", timeout=30)
        if resp.status_code != 200:
            return {"table": "fear_greed", "action": "error", "error": f"HTTP {resp.status_code}"}

        data = resp.json().get("data", [])
        logger.info("fear_greed: fetched %d entries from API", len(data))

        total_inserted = 0
        with engine.begin() as conn:
            for entry in data:
                d = datetime.strptime(entry["timestamp"], "%Y-%m-%d").date()
                if latest and d <= latest:
                    continue

                value = int(entry["value"])
                label = entry.get("value_classification", "")

                conn.execute(text("""
                    INSERT INTO fear_greed (date, value, label, source)
                    VALUES (:d, :v, :l, 'alternative.me')
                    ON CONFLICT (date) DO UPDATE SET value = EXCLUDED.value, label = EXCLUDED.label
                """), {"d": d, "v": value, "l": label})
                total_inserted += 1

        logger.info("fear_greed: inserted %d new rows", total_inserted)
        return {"table": "fear_greed", "action": "filled", "rows_inserted": total_inserted}

    except Exception as e:
        logger.error("fear_greed: %s", e)
        return {"table": "fear_greed", "action": "error", "error": str(e)[:200]}


def fill_macro_data(dry_run: bool = False) -> dict:
    """Fill macro_data from World Bank API (free, no key needed)."""
    import requests

    engine = get_engine()

    # Check latest
    with engine.connect() as conn:
        r = conn.execute(text("SELECT max(date) FROM macro_data"))
        latest = r.scalar()

    logger.info("macro_data: latest=%s", latest)

    if dry_run:
        return {"table": "macro_data", "action": "dry_run", "latest": str(latest)}

    # World Bank API — Indonesia macro indicators
    indicators = {
        "ID_GDP_GROWTH": "NY.GDP.MKTP.KD.ZG",
        "ID_INFLATION_CPI": "FP.CPI.TOTL.ZG",
        "ID_REAL_INTEREST_RATE": "FR.INR.RINR",
        "ID_FOREX_RESERVES": "FI.RES.TOTL.CD",
    }

    total_inserted = 0
    for series_name, wb_code in indicators.items():
        try:
            url = f"https://api.worldbank.org/v2/country/IDN/indicator/{wb_code}?format=json&per_page=100&date=2010%3A2026"
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                logger.warning("  %s: HTTP %d", series_name, resp.status_code)
                continue

            data = resp.json()
            if len(data) < 2 or not data[1]:
                logger.info("  %s: no data", series_name)
                continue

            with engine.begin() as conn:
                for entry in data[1]:
                    d = datetime.strptime(entry["date"], "%Y").date()
                    val = entry.get("value")
                    if val is None:
                        continue

                    conn.execute(text("""
                        INSERT INTO macro_data (series_name, date, value, source, frequency, unit)
                        VALUES (:sn, :d, :v, 'world_bank', 'annual', :u)
                        ON CONFLICT (series_name, date, source) DO UPDATE SET value = EXCLUDED.value
                    """), {
                        "sn": series_name, "d": d, "v": float(val),
                        "u": "%" if "GROWTH" in series_name or "INFLATION" in series_name or "INTEREST" in series_name else "USD",
                    })
                    total_inserted += 1

            logger.info("  %s: fetched %d entries", series_name, len(data[1]))
            time.sleep(0.5)

        except Exception as e:
            logger.warning("  Error fetching %s: %s", series_name, str(e)[:100])

    logger.info("macro_data: inserted %d rows", total_inserted)
    return {"table": "macro_data", "action": "filled", "rows_inserted": total_inserted}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill data gaps in PostgreSQL")
    parser.add_argument("--all", action="store_true", help="Fill all gaps")
    parser.add_argument("--stock-prices", action="store_true", help="Fill stock_prices only")
    parser.add_argument("--macro", action="store_true", help="Fill macro data only")
    parser.add_argument("--fear-greed", action="store_true", help="Fill fear_greed only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON report")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not any([args.all, args.stock_prices, args.macro, args.fear_greed]):
        args.all = True

    results: list[dict] = []

    if args.all or args.stock_prices:
        logger.info("=" * 60)
        logger.info("FILLING stock_prices gaps...")
        logger.info("=" * 60)
        results.append(fill_stock_prices(dry_run=args.dry_run))

    if args.all or args.macro:
        logger.info("=" * 60)
        logger.info("FILLING macroeconomic_indicators gaps...")
        logger.info("=" * 60)
        results.append(fill_macroeconomic_indicators(dry_run=args.dry_run))

        logger.info("=" * 60)
        logger.info("FILLING macro_data gaps...")
        logger.info("=" * 60)
        results.append(fill_macro_data(dry_run=args.dry_run))

    if args.all or args.fear_greed:
        logger.info("=" * 60)
        logger.info("FILLING fear_greed gaps...")
        logger.info("=" * 60)
        results.append(fill_fear_greed(dry_run=args.dry_run))

    # Summary
    print(f"\n{'='*60}")
    print("DATA INGESTION SUMMARY")
    print(f"{'='*60}")
    for r in results:
        action = r.get("action", "unknown")
        table = r.get("table", "unknown")
        if action == "filled":
            rows = r.get("rows_inserted", 0)
            print(f"  {table:40s} FILLED  {rows:>8} rows")
        elif action == "skip":
            print(f"  {table:40s} SKIP    {r.get('reason', '')}")
        elif action == "dry_run":
            print(f"  {table:40s} DRY-RUN")
        elif action == "error":
            print(f"  {table:40s} ERROR   {r.get('error', '')}")
    print(f"{'='*60}")

    if args.output:
        import json
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Report saved to %s", args.output)


if __name__ == "__main__":
    main()
