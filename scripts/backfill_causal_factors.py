"""Backfill missing causal factor data for AI/ML pattern recognition.

Adds global market tickers that complete the causal chain identified by
Granger causality testing. These factors allow AI/ML models to recognize
cross-market patterns:

1. Regional Asia indices: KOSPI, STI, KLSE, ASX, Sensex
2. Additional currency pairs: CNY/IDR, SGD/IDR
3. Energy complements: Brent Oil, Natural Gas
4. Rate factors: US 2Y Treasury, Fed Funds Rate
5. Re-fetch stale: MTF=F (coal), XIIT (Indonesia ETF)
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PG_URL = "postgresql://petrick:market_dev@localhost:5432/market"

# Tickers to add/re-fetch with their exchange MIC and expected UTC close time
# Format: (ticker, mic, close_hour_utc, close_minute_utc, name, asset_class)
NEW_TICKERS = [
    # Regional Asia indices
    ("^KS11", "XKRX", 6, 0, "KOSPI 200 Index", "INDEX_COMPOSITE"),
    ("^STI", "XSES", 9, 0, "Straits Times Index", "INDEX_COMPOSITE"),
    ("^KLSE", "XKLS", 9, 0, "FTSE Bursa Malaysia KLCI", "INDEX_COMPOSITE"),
    ("^AXJO", "XASX", 7, 0, "S&P/ASX 200 Index", "INDEX_COMPOSITE"),
    ("^BSESN", "XBOM", 8, 30, "BSE Sensex", "INDEX_COMPOSITE"),
    # Additional currency pairs
    ("CNYIDR=X", "XFXS", 21, 0, "CNY/IDR Exchange Rate", "fx"),
    ("SGDIDR=X", "XFXS", 21, 0, "SGD/IDR Exchange Rate", "fx"),
    # Energy complements
    ("BZ=F", "XCEC", 17, 30, "Brent Crude Oil Futures", "COMMODITY_FUTURES"),
    ("NG=F", "XCEC", 17, 30, "Natural Gas Futures", "COMMODITY_FUTURES"),
    # Rate factors
    ("^IRX", "XNYS", 20, 0, "US Treasury 13-Week Bill", "VOLATILITY_RATE"),
    # Stale re-fetch
    ("MTF=F", "XNYS", 20, 0, "Coal Futures (API2/ICE)", "COMMODITY_FUTURES"),
    ("XIIT", "XNYS", 20, 0, "iShares MSCI Indonesia ETF", "etf"),
]


def upsert_ohlcv(conn, ticker, mic, ts_utc, o, h, l, c, v):
    """Update if exists, insert if not."""
    result = conn.execute(text("""
        UPDATE stock_prices SET open=:o, high=:h, low=:l, close=:c, volume=:v
        WHERE ticker=:t AND timestamp=:ts AND timeframe='1d'
    """), {"o": o, "h": h, "l": l, "c": c, "v": v, "t": ticker, "ts": ts_utc})
    if result.rowcount == 0:
        conn.execute(text("""
            INSERT INTO stock_prices (ticker, exchange_mic, timestamp, timeframe, open, high, low, close, volume, source)
            VALUES (:t, :m, :ts, '1d', :o, :h, :l, :c, :v, 'yfinance')
        """), {"t": ticker, "m": mic, "ts": ts_utc, "o": o, "h": h, "l": l, "c": c, "v": v})


def ensure_instrument(conn, ticker, name, asset_class, mic):
    """Insert instrument if not exists."""
    conn.execute(text("""
        INSERT INTO instruments (ticker, exchange_mic, name, asset_class, is_active, created_at)
        VALUES (:t, :m, :n, :a, true, NOW())
        ON CONFLICT (ticker) DO UPDATE SET is_active = true, name = :n
    """), {"t": ticker, "m": mic, "n": name, "a": asset_class})


def main():
    engine = create_engine(PG_URL, echo=False, future=True, pool_pre_ping=True)
    lookback_years = 5
    start_date = date.today() - timedelta(days=lookback_years * 365)

    total_inserted = 0
    total_updated = 0

    with engine.begin() as conn:
        for ticker, mic, close_h, close_m, name, asset_class in NEW_TICKERS:
            logger.info("Fetching %s (%s) — %s ...", ticker, mic, name)

            # Ensure instrument exists
            ensure_instrument(conn, ticker, name, asset_class, mic)

            try:
                df = yf.download(
                    ticker, start=start_date.isoformat(),
                    end=(date.today() + timedelta(days=1)).isoformat(),
                    auto_adjust=True, progress=False, interval="1d",
                )
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if df is None or df.empty:
                    logger.warning("  No data for %s — may be delisted or unavailable", ticker)
                    continue

                count = 0
                for ts, row in df.iterrows():
                    if pd.isna(row.get("Close")):
                        continue
                    ts_dt = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
                    if ts_dt.tzinfo is None:
                        ts_dt = ts_dt.replace(tzinfo=UTC)
                    # Set correct close time in UTC
                    close_ts = datetime(
                        ts_dt.year, ts_dt.month, ts_dt.day,
                        close_h, close_m, 0, tzinfo=UTC,
                    )
                    o = float(row["Open"])
                    h = float(row["High"])
                    l = float(row["Low"])
                    c = float(row["Close"])
                    v = int(row["Volume"]) if not pd.isna(row.get("Volume")) else 0

                    # Check if row exists
                    existing = conn.execute(text(
                        "SELECT 1 FROM stock_prices WHERE ticker=:t AND timestamp=:ts AND timeframe='1d'"
                    ), {"t": ticker, "ts": close_ts}).fetchone()

                    upsert_ohlcv(conn, ticker, mic, close_ts, o, h, l, c, v)
                    if existing:
                        total_updated += 1
                    else:
                        total_inserted += 1
                    count += 1

                logger.info("  %s: %d rows processed (date range: %s to %s)",
                            ticker, count, df.index[0].date(), df.index[-1].date())

            except Exception as e:
                logger.error("  Failed %s: %s", ticker, e)

    engine.dispose()
    logger.info("\n" + "=" * 70)
    logger.info("BACKFILL COMPLETE")
    logger.info("  Total rows inserted: %d", total_inserted)
    logger.info("  Total rows updated: %d", total_updated)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
