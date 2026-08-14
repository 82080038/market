"""P1: Commodity-specific IDX — fetch nickel/tin, update coal, populate macro_data series.

Actions:
1. Fetch NI=F (nickel), TIN=F (tin) from yfinance → stock_prices
2. Update MTF=F (coal) to latest (last data was 2025-12-27)
3. Update CPO=F, HG=F to latest
4. Populate macro_data series: CPO, NEWCASTLE_COAL, NICKEL, COPPER, TIN (from stock_prices close)
5. Ensure instrument_master entries for all commodity tickers
6. Create commodity_to_stock mapping table + populate with IDX commodity-dependent stocks

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p1_commodity.py
"""
from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import psycopg2
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"

# Commodity tickers to fetch/update
COMMODITIES = [
    {"ticker": "NI=F",  "name": "Nickel Futures (LME proxy)",   "currency": "USD", "sector": "Basic Materials", "subsector": "nickel"},
    {"ticker": "TIN=F", "name": "Tin Futures (LME proxy)",      "currency": "USD", "sector": "Basic Materials", "subsector": "tin"},
    {"ticker": "MTF=F", "name": "Coal Futures (API2/ICE)",      "currency": "USD", "sector": "Energy",          "subsector": "coal"},
    {"ticker": "CPO=F", "name": "Crude Palm Oil Futures (Bursa)","currency": "MYR", "sector": "Consumer Non-Cyclicals", "subsector": "plantation"},
    {"ticker": "HG=F",  "name": "Copper Futures (COMEX)",       "currency": "USD", "sector": "Basic Materials", "subsector": "copper"},
    {"ticker": "CL=F",  "name": "Crude Oil WTI Futures",        "currency": "USD", "sector": "Energy",          "subsector": "oil"},
    {"ticker": "GC=F",  "name": "Gold Futures (COMEX)",         "currency": "USD", "sector": "Basic Materials", "subsector": "gold"},
]

# macro_data series_name mapping from ticker
MACRO_SERIES_MAP = {
    "CPO=F": "CPO",
    "MTF=F": "NEWCASTLE_COAL",
    "NI=F": "NICKEL",
    "HG=F": "COPPER",
    "TIN=F": "TIN",
    "CL=F": "CRUDE_OIL",
    "GC=F": "GOLD",
}

# Commodity → IDX stock mapping (pustaka/91-komoditas-spesifik-idx.md)
COMMODITY_STOCK_MAP = [
    # CPO / Palm Oil
    {"commodity": "CPO", "ticker": "AALI.JK", "sector": "Consumer Non-Cyclicals", "sensitivity": 0.85},
    {"commodity": "CPO", "ticker": "LSIP.JK", "sector": "Consumer Non-Cyclicals", "sensitivity": 0.80},
    {"commodity": "CPO", "ticker": "SIMP.JK", "sector": "Consumer Non-Cyclicals", "sensitivity": 0.75},
    {"commodity": "CPO", "ticker": "DSNG.JK", "sector": "Consumer Non-Cyclicals", "sensitivity": 0.70},
    {"commodity": "CPO", "ticker": "ANJT.JK", "sector": "Consumer Non-Cyclicals", "sensitivity": 0.75},
    {"commodity": "CPO", "ticker": "SGRO.JK", "sector": "Consumer Non-Cyclicals", "sensitivity": 0.65},
    {"commodity": "CPO", "ticker": "BWPT.JK", "sector": "Consumer Non-Cyclicals", "sensitivity": 0.60},
    # Coal
    {"commodity": "NEWCASTLE_COAL", "ticker": "PTBA.JK", "sector": "Energy", "sensitivity": 0.90},
    {"commodity": "NEWCASTLE_COAL", "ticker": "ITMG.JK", "sector": "Energy", "sensitivity": 0.85},
    {"commodity": "NEWCASTLE_COAL", "ticker": "ADRO.JK", "sector": "Energy", "sensitivity": 0.80},
    {"commodity": "NEWCASTLE_COAL", "ticker": "HRUM.JK", "sector": "Energy", "sensitivity": 0.80},
    {"commodity": "NEWCASTLE_COAL", "ticker": "BYAN.JK", "sector": "Energy", "sensitivity": 0.75},
    {"commodity": "NEWCASTLE_COAL", "ticker": "BSSR.JK", "sector": "Energy", "sensitivity": 0.70},
    {"commodity": "NEWCASTLE_COAL", "ticker": "GEMS.JK", "sector": "Energy", "sensitivity": 0.65},
    # Nickel
    {"commodity": "NICKEL", "ticker": "INCO.JK", "sector": "Basic Materials", "sensitivity": 0.95},
    {"commodity": "NICKEL", "ticker": "ANTM.JK", "sector": "Basic Materials", "sensitivity": 0.70},
    {"commodity": "NICKEL", "ticker": "MDKA.JK", "sector": "Basic Materials", "sensitivity": 0.65},
    # Copper
    {"commodity": "COPPER", "ticker": "ANTM.JK", "sector": "Basic Materials", "sensitivity": 0.50},
    {"commodity": "COPPER", "ticker": "MDKA.JK", "sector": "Basic Materials", "sensitivity": 0.55},
    {"commodity": "COPPER", "ticker": "INCO.JK", "sector": "Basic Materials", "sensitivity": 0.40},
    # Gold
    {"commodity": "GOLD", "ticker": "ANTM.JK", "sector": "Basic Materials", "sensitivity": 0.60},
    {"commodity": "GOLD", "ticker": "MDKA.JK", "sector": "Basic Materials", "sensitivity": 0.50},
    # Tin
    {"commodity": "TIN", "ticker": "TINS.JK", "sector": "Basic Materials", "sensitivity": 0.90},
    {"commodity": "TIN", "ticker": "MBAP.JK", "sector": "Basic Materials", "sensitivity": 0.75},
    # Crude Oil
    {"commodity": "CRUDE_OIL", "ticker": "MEDC.JK", "sector": "Energy", "sensitivity": 0.70},
    {"commodity": "CRUDE_OIL", "ticker": "ARTI.JK", "sector": "Energy", "sensitivity": 0.65},
    {"commodity": "CRUDE_OIL", "ticker": "ENRG.JK", "sector": "Energy", "sensitivity": 0.60},
    {"commodity": "CRUDE_OIL", "ticker": "ELSA.JK", "sector": "Energy", "sensitivity": 0.55},
]


def fetch_yf_ohlcv(ticker: str, start: str = "2020-01-01") -> pd.DataFrame:
    """Fetch daily OHLCV from yfinance."""
    end = datetime.now(UTC).strftime("%Y-%m-%d")
    logger.info("  Fetching %s from %s to %s ...", ticker, start, end)
    try:
        df = yf.download(ticker, start=start, end=end, interval="1d", progress=False)
    except Exception as e:
        logger.error("  yfinance download failed for %s: %s", ticker, e)
        return pd.DataFrame()
    if df is None or df.empty:
        logger.warning("  No data returned for %s", ticker)
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df = df.rename(columns={
        "Date": "timestamp", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def upsert_stock_prices(conn, ticker: str, df: pd.DataFrame, exchange_mic: str = "OFF") -> int:
    """Upsert OHLCV rows into stock_prices (PostgreSQL)."""
    if df.empty:
        return 0
    cur = conn.cursor()
    count = 0
    for _, row in df.iterrows():
        ts = row["timestamp"]
        if hasattr(ts, "to_pydatetime"):
            ts_dt = ts.to_pydatetime()
        else:
            ts_dt = ts
        cur.execute("""
            INSERT INTO stock_prices (ticker, exchange_mic, timestamp, timeframe, open, high, low, close, volume, source, adjusted_close)
            VALUES (%s, %s, %s, '1d', %s, %s, %s, %s, %s, 'yfinance', %s)
            ON CONFLICT DO NOTHING
        """, (
            ticker, exchange_mic, ts_dt,
            float(row.get("open", 0)) if pd.notna(row.get("open")) else None,
            float(row.get("high", 0)) if pd.notna(row.get("high")) else None,
            float(row.get("low", 0)) if pd.notna(row.get("low")) else None,
            float(row.get("close", 0)) if pd.notna(row.get("close")) else None,
            int(row.get("volume", 0)) if pd.notna(row.get("volume")) else 0,
            float(row.get("close", 0)) if pd.notna(row.get("close")) else None,
        ))
        count += cur.rowcount
    conn.commit()
    return count


def ensure_instrument_master(conn, info: dict) -> None:
    """Ensure commodity ticker exists in instrument_master."""
    ticker = info["ticker"]
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM instrument_master WHERE ticker = %s", (ticker,))
    exists = cur.fetchone()
    if exists:
        cur.execute("""
            UPDATE instrument_master SET name = %s, asset_class = 'COMMODITY_FUTURES',
                   base_currency = %s, sector = %s, subsector = %s, is_active = '1'
            WHERE ticker = %s
        """, (info["name"], info["currency"], info["sector"], info.get("subsector"), ticker))
    else:
        cur.execute("""
            INSERT INTO instrument_master (ticker, name, asset_class, base_currency, sector, subsector, is_active, market_mic)
            VALUES (%s, %s, 'COMMODITY_FUTURES', %s, %s, %s, '1', 'OFF')
        """, (ticker, info["name"], info["currency"], info["sector"], info.get("subsector")))
    conn.commit()


def populate_macro_data_from_prices(conn, ticker: str, series_name: str) -> int:
    """Populate macro_data series from stock_prices close prices."""
    cur = conn.cursor()
    cur.execute("""
        SELECT timestamp::date, close FROM stock_prices
        WHERE ticker = %s AND timeframe = '1d'
        ORDER BY timestamp
    """, (ticker,))
    rows = cur.fetchall()
    if not rows:
        logger.warning("  No price data for %s → macro_data.%s", ticker, series_name)
        return 0
    count = 0
    for d, close in rows:
        if close is None:
            continue
        cur.execute("""
            INSERT INTO macro_data (series_name, date, value, unit, source, frequency)
            VALUES (%s, %s, %s, 'price', 'yfinance', 'daily')
            ON CONFLICT (series_name, date, source) DO UPDATE SET value = EXCLUDED.value
        """, (series_name, d, float(close)))
        count += cur.rowcount
    conn.commit()
    logger.info("  macro_data.%s: %d rows populated", series_name, count)
    return count


def create_commodity_stock_map(conn) -> int:
    """Create commodity_to_stock_map table and populate it."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS commodity_to_stock_map (
            id SERIAL PRIMARY KEY,
            commodity_series VARCHAR(50) NOT NULL,
            ticker VARCHAR(30) NOT NULL,
            sector VARCHAR(100),
            sensitivity FLOAT DEFAULT 0.5,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (commodity_series, ticker)
        )
    """)
    # Clear existing
    cur.execute("DELETE FROM commodity_to_stock_map")
    for entry in COMMODITY_STOCK_MAP:
        cur.execute("""
            INSERT INTO commodity_to_stock_map (commodity_series, ticker, sector, sensitivity)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (commodity_series, ticker) DO UPDATE SET sensitivity = EXCLUDED.sensitivity
        """, (entry["commodity"], entry["ticker"], entry["sector"], entry["sensitivity"]))
    conn.commit()
    return len(COMMODITY_STOCK_MAP)


def main() -> None:
    logger.info("=" * 70)
    logger.info("P1: COMMODITY-SPECIFIC IDX — Batch Execution")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)

    # Step 1: Fetch & upsert commodity OHLCV
    logger.info("")
    logger.info("--- Step 1: Fetch commodity OHLCV from yfinance ---")
    total_rows = 0
    for info in COMMODITIES:
        ticker = info["ticker"]
        logger.info("")
        logger.info("Processing %s (%s)", ticker, info["name"])
        ensure_instrument_master(conn, info)
        df = fetch_yf_ohlcv(ticker, start="2020-01-01")
        if not df.empty:
            n = upsert_stock_prices(conn, ticker, df)
            total_rows += n
            logger.info("  Upserted %d rows into stock_prices", n)
        else:
            logger.warning("  No data for %s — may be unavailable on yfinance", ticker)

    logger.info("")
    logger.info("Total commodity OHLCV rows upserted: %d", total_rows)

    # Step 2: Populate macro_data series from stock_prices
    logger.info("")
    logger.info("--- Step 2: Populate macro_data series from close prices ---")
    for ticker, series_name in MACRO_SERIES_MAP.items():
        populate_macro_data_from_prices(conn, ticker, series_name)

    # Step 3: Create commodity-to-stock mapping
    logger.info("")
    logger.info("--- Step 3: Create commodity_to_stock_map table ---")
    n_mapped = create_commodity_stock_map(conn)
    logger.info("  commodity_to_stock_map: %d mappings", n_mapped)

    # Step 4: Audit
    logger.info("")
    logger.info("--- Step 4: Post-audit ---")
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, count(*), min(timestamp)::date, max(timestamp)::date
        FROM stock_prices
        WHERE ticker IN ('CL=F','GC=F','HG=F','MTF=F','CPO=F','NI=F','TIN=F')
        GROUP BY ticker ORDER BY ticker
    """)
    logger.info("Commodity OHLCV in stock_prices:")
    for row in cur.fetchall():
        logger.info("  %s: %d rows (%s → %s)", row[0], row[1], row[2], row[3])

    cur.execute("""
        SELECT series_name, count(*), min(date), max(date)
        FROM macro_data
        WHERE series_name IN ('CPO','NEWCASTLE_COAL','NICKEL','COPPER','TIN','CRUDE_OIL','GOLD')
        GROUP BY series_name ORDER BY series_name
    """)
    logger.info("")
    logger.info("Commodity series in macro_data:")
    for row in cur.fetchall():
        logger.info("  %s: %d rows (%s → %s)", row[0], row[1], row[2], row[3])

    cur.execute("SELECT count(*) FROM commodity_to_stock_map")
    n = cur.fetchone()[0]
    logger.info("")
    logger.info("commodity_to_stock_map: %d rows", n)

    conn.close()
    logger.info("")
    logger.info("P1 COMPLETE.")


if __name__ == "__main__":
    main()
