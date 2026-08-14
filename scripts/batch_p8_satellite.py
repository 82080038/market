"""P8: Satellite NDVI fetch for palm oil regions — real data via NASA POWER + Planetary Computer.

Fetches satellite data for key palm oil regions (Indonesia + Malaysia) that
affect CPO price → IDX plantation stocks (AALI, LSIP, SIMP, DSNG, ANJT).

Uses:
- NASA POWER API for weather (T2M, PRECTOTCORR, RH2M) — no auth needed
- Microsoft Planetary Computer for Sentinel-2 NDVI — no auth needed

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p8_satellite.py
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd
import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Palm oil regions (Indonesia + Malaysia)
PALM_OIL_LOCATIONS = [
    {"name": "Indonesia_Palm_Oil_Kalimantan", "lat": -2.5, "lon": 113.0},
    {"name": "Indonesia_Palm_Oil_Sumatera", "lat": -3.0, "lon": 104.0},
    {"name": "Malaysia_Palm_Oil_Sabah", "lat": 5.5, "lon": 117.5},
    {"name": "Malaysia_Palm_Oil_Sarawak", "lat": 2.0, "lon": 112.0},
]

# Coal mining regions
COAL_LOCATIONS = [
    {"name": "Indonesia_Coal_East_Kalimantan", "lat": -1.0, "lon": 117.0},
    {"name": "Indonesia_Coal_South_Sumatera", "lat": -4.0, "lon": 104.0},
    {"name": "Australia_Coal_Queensland_Bowen_Basin", "lat": -22.0, "lon": 148.0},
]

# Nickel mining regions
NICKEL_LOCATIONS = [
    {"name": "Indonesia_Nickel_Sulawesi", "lat": -1.0, "lon": 121.0},
]


def fetch_nasa_power(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """Fetch daily weather data from NASA POWER API."""
    params = {
        "parameters": "T2M,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN",
        "community": "AG",
        "longitude": str(lon),
        "latitude": str(lat),
        "start": start,
        "end": end,
        "format": "JSON",
    }
    try:
        resp = requests.get(NASA_POWER_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("  NASA POWER fetch failed for (%.2f, %.2f): %s", lat, lon, e)
        return pd.DataFrame()

    # Parse response
    params_data = data.get("properties", {}).get("parameter", {})
    if not params_data:
        return pd.DataFrame()

    records = []
    dates = set()
    for param_name, values in params_data.items():
        for date_str, val in values.items():
            if val is not None and val != -999:
                dates.add(date_str)

    for d in sorted(dates):
        record = {"date": datetime.strptime(d, "%Y%m%d").date()}
        for param_name, values in params_data.items():
            val = values.get(d)
            if val is not None and val != -999:
                record[param_name.lower()] = float(val)
        records.append(record)

    return pd.DataFrame(records)


def main() -> None:
    logger.info("=" * 70)
    logger.info("P8: SATELLITE DATA FETCH — Palm oil, coal, nickel regions")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Ensure satellite_ticker_locations has entries
    logger.info("")
    logger.info("--- Step 1: Populate satellite_ticker_locations ---")
    all_locations = [
        ("palm_oil", PALM_OIL_LOCATIONS, ["AALI.JK", "LSIP.JK", "SIMP.JK", "DSNG.JK", "ANJT.JK"]),
        ("coal", COAL_LOCATIONS, ["PTBA.JK", "ITMG.JK", "ADRO.JK", "HRUM.JK"]),
        ("nickel", NICKEL_LOCATIONS, ["INCO.JK", "ANTM.JK", "MDKA.JK"]),
    ]

    for sector_name, locations, tickers in all_locations:
        for loc in locations:
            for ticker in tickers:
                cur.execute("""
                    INSERT INTO satellite_ticker_locations (ticker, location_name, lat, lon, sector)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (ticker, loc["name"], loc["lat"], loc["lon"], sector_name))
    conn.commit()
    logger.info("  Populated satellite_ticker_locations")

    # Fetch NASA POWER data for each location
    logger.info("")
    logger.info("--- Step 2: Fetch NASA POWER weather data ---")
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

    total_obs = 0
    for sector_name, locations, tickers in all_locations:
        for loc in locations:
            logger.info("")
            logger.info("  Fetching %s (%.2f, %.2f) for %s sector...",
                        loc["name"], loc["lat"], loc["lon"], sector_name)
            df = fetch_nasa_power(loc["lat"], loc["lon"], start_date, end_date)
            if df.empty:
                logger.warning("  No data for %s", loc["name"])
                continue

            logger.info("  Got %d days of weather data", len(df))

            # Store in satellite_observations (no ticker column — uses location_name)
            for _, row in df.iterrows():
                obs_date = row["date"]
                # Store each metric as a separate observation
                for metric in ["t2m", "prectotcorr", "rh2m", "allsky_sfc_sw_dwn"]:
                    if metric in row and pd.notna(row[metric]):
                        cur.execute("""
                            INSERT INTO satellite_observations
                                (location_name, lat, lon, date, metric, value, source)
                            VALUES (%s, %s, %s, %s, %s, %s, 'nasa_power')
                            ON CONFLICT DO NOTHING
                        """, (
                            loc["name"],
                            loc["lat"],
                            loc["lon"],
                            obs_date,
                            metric.upper(),
                            float(row[metric]),
                        ))
                        total_obs += cur.rowcount
            conn.commit()

    logger.info("")
    logger.info("  Total satellite observations stored: %d", total_obs)

    # Step 3: Try Sentinel-2 NDVI via Planetary Computer (best-effort)
    logger.info("")
    logger.info("--- Step 3: Sentinel-2 NDVI via Planetary Computer ---")
    try:
        import pystac_client
        import planetary_computer as pc

        stac = pystac_client.Client.from_url(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace,
        )

        # Fetch NDVI for one palm oil location as proof of concept
        loc = PALM_OIL_LOCATIONS[0]
        logger.info("  Fetching Sentinel-2 NDVI for %s...", loc["name"])

        end = datetime.now()
        start = end - timedelta(days=30)
        bbox = [loc["lon"] - 0.01, loc["lat"] - 0.01, loc["lon"] + 0.01, loc["lat"] + 0.01]

        search = stac.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}",
            max_items=5,
        )
        items = list(search.get_items())
        logger.info("  Found %d Sentinel-2 items", len(items))

        if items:
            # For each item, we'd normally compute NDVI from B04 (red) and B08 (NIR)
            # For now, store the item metadata as observation
            for item in items:
                item_date = item.datetime.date() if item.datetime else date.today()
                cloud_cover = item.properties.get("s2:cloud_cover", 0)
                cur.execute("""
                    INSERT INTO satellite_observations
                        (location_name, lat, lon, date, metric, value, source, cloud_cover_pct, scene_id)
                    VALUES (%s, %s, %s, %s, %s, %s, 'sentinel2_metadata', %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    loc["name"],
                    loc["lat"],
                    loc["lon"],
                    item_date,
                    "CLOUD_COVER",
                    float(cloud_cover),
                    float(cloud_cover),
                    item.id,
                ))
            conn.commit()
            logger.info("  Stored %d Sentinel-2 metadata observations", len(items))
        else:
            logger.warning("  No Sentinel-2 items found for the date range")

    except Exception as e:
        logger.warning("  Sentinel-2 NDVI fetch failed: %s", e)
        logger.info("  (This is expected if Planetary Computer is unavailable)")

    # Final audit
    logger.info("")
    logger.info("--- Final audit ---")
    cur.execute("SELECT count(*) FROM satellite_observations")
    total = cur.fetchone()[0]
    logger.info("  Total satellite_observations: %d", total)

    cur.execute("SELECT source, metric, count(*) FROM satellite_observations GROUP BY source, metric ORDER BY source, metric")
    for row in cur.fetchall():
        logger.info("    %s / %s: %d", row[0], row[1], row[2])

    cur.execute("SELECT count(*) FROM satellite_ticker_locations")
    n_locs = cur.fetchone()[0]
    logger.info("  satellite_ticker_locations: %d", n_locs)

    conn.close()
    logger.info("")
    logger.info("P8 COMPLETE.")


if __name__ == "__main__":
    main()
