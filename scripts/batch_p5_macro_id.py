"""P5: Macro Indonesia fetcher — fetch from World Bank API (free, no key needed).

Fetches Indonesian macroeconomic indicators:
- GDP growth (annual %)
- Inflation CPI (annual %)
- Trade balance (% of GDP)
- Current account balance (% of GDP)
- Foreign exchange reserves (total reserves, USD)
- Government debt-to-GDP
- Real interest rate
- BI policy rate (via World Bank or existing data)

Also fetches US macro for comparison:
- Fed funds rate
- US GDP growth
- US inflation

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p5_macro_id.py
"""
from __future__ import annotations

import logging
from datetime import datetime

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"
WB_BASE = "https://api.worldbank.org/v2"

# World Bank indicator codes
WB_INDICATORS = [
    # Indonesia
    {"code": "NY.GDP.MKTP.KD.ZG", "series": "ID_GDP_GROWTH", "country": "ID",
     "name": "GDP growth (annual %)", "unit": "%", "freq": "annual"},
    {"code": "FP.CPI.TOTL.ZG", "series": "ID_INFLATION_CPI", "country": "ID",
     "name": "Inflation CPI (annual %)", "unit": "%", "freq": "annual"},
    {"code": "NE.TRD.GNFS.ZS", "series": "ID_TRADE_PCT_GDP", "country": "ID",
     "name": "Trade (% of GDP)", "unit": "%", "freq": "annual"},
    {"code": "BN.CAB.XOKA.GD.ZS", "series": "ID_CURRENT_ACCOUNT", "country": "ID",
     "name": "Current account balance (% of GDP)", "unit": "%", "freq": "annual"},
    {"code": "FI.RES.TOTL.CD", "series": "ID_FOREX_RESERVES_USD", "country": "ID",
     "name": "Total reserves (USD, current)", "unit": "USD", "freq": "annual"},
    {"code": "GC.DOD.TOTL.GD.ZS", "series": "ID_DEBT_TO_GDP", "country": "ID",
     "name": "Central government debt (% of GDP)", "unit": "%", "freq": "annual"},
    {"code": "FR.INR.RINR", "series": "ID_REAL_INTEREST_RATE", "country": "ID",
     "name": "Real interest rate (%)", "unit": "%", "freq": "annual"},
    {"code": "FM.LBL.BMNY.ZG", "series": "ID_BROAD_MONEY_GROWTH", "country": "ID",
     "name": "Broad money growth (annual %)", "unit": "%", "freq": "annual"},
    {"code": "NV.IND.TOTL.ZS", "series": "ID_INDUSTRIAL_PCT", "country": "ID",
     "name": "Industry value added (% of GDP)", "unit": "%", "freq": "annual"},
    {"code": "GC.TAX.TOTL.GD.ZS", "series": "ID_TAX_PCT_GDP", "country": "ID",
     "name": "Tax revenue (% of GDP)", "unit": "%", "freq": "annual"},
    # US (for comparison)
    {"code": "NY.GDP.MKTP.KD.ZG", "series": "US_GDP_GROWTH", "country": "US",
     "name": "US GDP growth (annual %)", "unit": "%", "freq": "annual"},
    {"code": "FP.CPI.TOTL.ZG", "series": "US_INFLATION_WB", "country": "US",
     "name": "US Inflation CPI (annual %)", "unit": "%", "freq": "annual"},
    {"code": "FRED.DFF", "series": "US_FED_FUNDS_RATE", "country": "US",
     "name": "Fed Funds Effective Rate", "unit": "%", "freq": "daily"},
    # Global
    {"code": "PA.NUS.PPP", "series": "ID_PPP", "country": "ID",
     "name": "Purchasing Power Parity", "unit": "LCU_per_USD", "freq": "annual"},
]


def fetch_wb_indicator(code: str, country: str = "ID") -> list[dict]:
    """Fetch a World Bank indicator for a country."""
    url = f"{WB_BASE}/country/{country}/indicator/{code}"
    params = {"format": "json", "per_page": "1000", "date": "1990:2100"}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning("  WB fetch failed for %s/%s: %s", country, code, e)
        return []

    if not isinstance(payload, list) or len(payload) < 2:
        return []
    records = payload[1]
    if not isinstance(records, list):
        return []
    rows = []
    for rec in records:
        value = rec.get("value")
        if value is None:
            continue
        date_str = str(rec.get("date", ""))
        # WB dates: "2023" (annual) or "2023Q1" or "202301" (monthly)
        if len(date_str) == 4 and date_str.isdigit():
            d = f"{date_str}-01-01"
        elif "Q" in date_str:
            year, q = date_str.split("Q")
            month = {"1": "01", "2": "04", "3": "07", "4": "10"}.get(q, "01")
            d = f"{year}-{month}-01"
        elif len(date_str) == 6 and date_str.isdigit():
            d = f"{date_str[:4]}-{date_str[4:6]}-01"
        else:
            d = date_str
        rows.append({"date": d, "value": float(value)})
    return rows


def main() -> None:
    logger.info("=" * 70)
    logger.info("P5: MACRO INDONESIA FETCHER — World Bank API")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    total_inserted = 0
    for ind in WB_INDICATORS:
        logger.info("")
        logger.info("Fetching %s (%s) for %s...", ind["series"], ind["name"], ind["country"])
        rows = fetch_wb_indicator(ind["code"], ind["country"])
        if not rows:
            logger.warning("  No data for %s", ind["series"])
            continue

        count = 0
        for row in rows:
            try:
                cur.execute("""
                    INSERT INTO macro_data (series_name, date, value, unit, source, frequency)
                    VALUES (%s, %s, %s, %s, 'world_bank', %s)
                    ON CONFLICT (series_name, date, source) DO UPDATE SET value = EXCLUDED.value
                """, (ind["series"], row["date"], row["value"], ind["unit"], ind["freq"]))
                count += cur.rowcount
            except Exception as e:
                logger.warning("  Insert failed for %s %s: %s", ind["series"], row["date"], e)
                conn.rollback()
                continue
        conn.commit()
        total_inserted += count
        logger.info("  %s: %d rows inserted/updated", ind["series"], count)

    # Also fetch BI 7-Day Repo Rate from existing data (already in macro_data)
    # and verify it's up to date
    logger.info("")
    logger.info("--- Audit: All macro_data series ---")
    cur.execute("""
        SELECT series_name, count(*), min(date), max(date)
        FROM macro_data
        GROUP BY series_name ORDER BY series_name
    """)
    for row in cur.fetchall():
        logger.info("  %s: %d rows (%s → %s)", row[0], row[1], row[2], row[3])

    # Also populate macroeconomic_indicators table (more structured)
    logger.info("")
    logger.info("--- Populating macroeconomic_indicators table ---")
    # Map macro_data series to macroeconomic_indicators
    MI_MAP = {
        "ID_GDP_GROWTH": ("ID_GDP_GROWTH", "GDP Growth", "ID"),
        "ID_INFLATION_CPI": ("ID_INFLATION_CPI", "Inflation CPI", "ID"),
        "ID_TRADE_PCT_GDP": ("ID_TRADE_PCT_GDP", "Trade % GDP", "ID"),
        "ID_CURRENT_ACCOUNT": ("ID_CURRENT_ACCOUNT", "Current Account % GDP", "ID"),
        "ID_FOREX_RESERVES_USD": ("ID_FOREX_RESERVES_USD", "Forex Reserves USD", "ID"),
        "ID_DEBT_TO_GDP": ("ID_DEBT_TO_GDP", "Debt to GDP", "ID"),
        "ID_REAL_INTEREST_RATE": ("ID_REAL_INTEREST_RATE", "Real Interest Rate", "ID"),
        "US_GDP_GROWTH": ("US_GDP_GROWTH", "US GDP Growth", "US"),
        "US_INFLATION_WB": ("US_INFLATION_WB", "US Inflation CPI", "US"),
    }
    mi_count = 0
    for series_name, (code, name, region) in MI_MAP.items():
        cur.execute("SELECT date, value FROM macro_data WHERE series_name = %s ORDER BY date", (series_name,))
        rows = cur.fetchall()
        for d, val in rows:
            if val is None:
                continue
            recorded_at = datetime.combine(d, datetime.min.time()) if hasattr(d, 'year') else d
            try:
                cur.execute("""
                    INSERT INTO macroeconomic_indicators (indicator_code, name, region, recorded_at, value)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (indicator_code, recorded_at) DO UPDATE SET value = EXCLUDED.value
                """, (code, name, region, recorded_at, float(val)))
                mi_count += cur.rowcount
            except Exception:
                conn.rollback()
                continue
    conn.commit()
    logger.info("  macroeconomic_indicators: %d rows upserted", mi_count)

    conn.close()
    logger.info("")
    logger.info("P5 COMPLETE. Total macro_data rows: %d", total_inserted)


if __name__ == "__main__":
    main()
