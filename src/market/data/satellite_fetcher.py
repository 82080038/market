"""Satellite data fetcher — production module for the market application.

Fetches satellite data globally for any ticker/location:
  - NDVI from Sentinel-2 L2A via Microsoft Planetary Computer STAC API
  - T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN from NASA POWER API

Location resolution priority:
  1. satellite_ticker_locations table (DB-driven, per-ticker explicit mapping)
  2. SECTOR_FALLBACK_LOCATIONS (sector-based defaults for common sectors)
  3. Skip if no mapping found

This makes satellite data truly global — any ticker from any market
can be mapped to any location on Earth.

References:
  - pustaka/99-matriks-relevansi-satelit-pasar-modal.md
  - scripts/satellite_stock_correlation.py (research pipeline)
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd
import requests

from market.data.rate_limit import CircuitBreakerError, DynamicRateLimiter, retry_with_backoff

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Backward-compat aliases — the canonical implementation lives in
# market.data.rate_limit. These re-exports keep existing imports working.
_retry_with_backoff = retry_with_backoff

# Re-export for backward compatibility
CircuitBreakerError = CircuitBreakerError

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PLANETARY_COMPUTER_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"

# Only metrics proven significant (p < 0.05) in correlation analysis
SIGNIFICANT_METRICS: list[str] = [
    "NDVI",              # Sentinel-2 via Planetary Computer
    "T2M",               # NASA POWER — Temperature at 2m (°C)
    "PRECTOTCORR",       # NASA POWER — Precipitation (mm/day)
    "RH2M",              # NASA POWER — Relative humidity at 2m (%)
    "ALLSKY_SFC_SW_DWN", # NASA POWER — Surface shortwave downward irradiance (W/m²)
]

NASA_POWER_PARAMS: list[str] = ["T2M", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN"]

# Sector-based fallback locations — comprehensive global coverage.
# Used when no explicit ticker→location mapping exists in the DB.
#
# Rationale: Indonesian stock exchange (IDX) is influenced by global commodity
# prices, which in turn are influenced by satellite-observable conditions
# (weather, NDVI, cloud cover) at production regions worldwide.
# Example chain: Drought in US Corn Belt → corn price up → Indonesian food
# stocks affected. Floods in Malaysia palm oil estates → CPO price up →
# AALI.JK/LSIP.JK benefit.
#
# Each sector maps to multiple representative global locations.
SECTOR_FALLBACK_LOCATIONS: dict[str, list[dict]] = {
    # ── AGRICULTURE: Global commodity growing regions ──
    # Affects IDX: plantation stocks (AALI, LSIP, SGRO), food & beverage
    # (INDF, ICBP, MYOR, ULTJ), animal feed (CPIN, JPFA)
    "agriculture": [
        # Indonesia — palm oil (direct IDX impact)
        {"name": "Indonesia_Palm_Oil_Kalimantan", "lat": -2.5, "lon": 113.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Indonesia_Palm_Oil_Sumatera", "lat": -3.0, "lon": 104.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Indonesia_Rice_Java", "lat": -7.5, "lon": 110.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        # Malaysia — palm oil (competitor, affects CPO price)
        {"name": "Malaysia_Palm_Oil_Sabah", "lat": 5.5, "lon": 117.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Malaysia_Palm_Oil_Sarawak", "lat": 2.0, "lon": 112.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        # US — corn, soybean, wheat, cotton (global grain benchmark)
        {"name": "US_Corn_Belt_Iowa", "lat": 41.878, "lon": -93.098,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "US_Soybean_Illinois", "lat": 40.0, "lon": -89.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "US_Wheat_Kansas", "lat": 38.5, "lon": -98.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "US_Cotton_Texas", "lat": 32.0, "lon": -100.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "US_California_Central_Valley", "lat": 37.5, "lon": -121.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Brazil — soybean, sugar, coffee (major global exporter)
        {"name": "Brazil_Soybean_Mato_Grosso", "lat": -13.0, "lon": -56.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Brazil_Sugar_Cane_Sao_Paulo", "lat": -23.0, "lon": -47.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Brazil_Coffee_Minas_Gerais", "lat": -18.5, "lon": -44.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Argentina — soybean, corn (major exporter)
        {"name": "Argentina_Soybean_Buenos_Aires", "lat": -36.0, "lon": -62.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # India — wheat, rice, cotton, sugar (large producer + consumer)
        {"name": "India_Wheat_Punjab", "lat": 31.0, "lon": 75.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "India_Rice_West_Bengal", "lat": 23.5, "lon": 88.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "India_Cotton_Gujarat", "lat": 22.0, "lon": 71.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Australia — wheat, cotton, sugar (major exporter to Asia)
        {"name": "Australia_Wheat_Western_Australia", "lat": -31.0, "lon": 116.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Australia_Cotton_Queensland", "lat": -25.0, "lon": 147.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Southeast Asia — rice, sugar, coffee (ASEAN peers)
        {"name": "Thailand_Rice_Central_Plain", "lat": 15.0, "lon": 100.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Thailand_Sugar_Cane_North", "lat": 18.0, "lon": 99.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Vietnam_Rice_Mekong_Delta", "lat": 10.0, "lon": 105.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Vietnam_Coffee_Central_Highlands", "lat": 12.5, "lon": 108.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # West Africa — cocoa (global chocolate industry, affects commodity indices)
        {"name": "Cote_dIvoire_Cocoa", "lat": 7.0, "lon": -6.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Ghana_Cocoa_Ashanti", "lat": 6.5, "lon": -1.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        # China — soybean, corn, cotton (largest importer, affects global prices)
        {"name": "China_Soybean_Heilongjiang", "lat": 47.0, "lon": 127.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "China_Corn_Northeast", "lat": 44.0, "lon": 125.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "China_Cotton_Xinjiang", "lat": 40.0, "lon": 80.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Europe — wheat, barley, rapeseed (affects global grain benchmarks)
        {"name": "France_Wheat_Paris_Basin", "lat": 48.5, "lon": 2.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Germany_Wheat_Bavaria", "lat": 48.5, "lon": 11.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Ukraine_Corn_Central", "lat": 49.0, "lon": 32.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Ukraine_Wheat_South", "lat": 47.0, "lon": 33.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Russia — wheat (largest exporter, affects global wheat price)
        {"name": "Russia_Wheat_Krasnodar", "lat": 45.0, "lon": 39.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Russia_Wheat_Rostov", "lat": 47.0, "lon": 40.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
    ],

    # ── ENERGY: Global oil, gas, coal production regions ──
    # Affects IDX: coal stocks (PTBA, ADRO, ITMG, BORN, HRUM),
    # oil & gas (MEDC, ARTI, ENRG, ELSA), energy services (RIGI, ENZO)
    "energy": [
        # Indonesia — coal mines (direct IDX impact)
        {"name": "Indonesia_Coal_East_Kalimantan", "lat": -1.0, "lon": 117.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Indonesia_Coal_South_Sumatera", "lat": -4.0, "lon": 104.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # US — shale oil & gas (WTI benchmark)
        {"name": "US_Shale_Texas_Permian", "lat": 31.5, "lon": -102.5,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "US_Shale_North_Dakota_Bakken", "lat": 48.0, "lon": -103.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "US_Natural_Gas_Texas_Haynesville", "lat": 32.0, "lon": -94.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Middle East — conventional oil (Brent benchmark)
        {"name": "Saudi_Arabia_Oil_Eastern_Province", "lat": 26.0, "lon": 50.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Iraq_Oil_Basra", "lat": 30.5, "lon": 47.8,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "UAE_Oil_Abu_Dhabi", "lat": 24.0, "lon": 54.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Kuwait_Oil_Burgan", "lat": 28.5, "lon": 48.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Iran_Oil_Khuzestan", "lat": 31.0, "lon": 49.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # North Sea — Brent crude benchmark
        {"name": "North_Sea_Oil_Norway", "lat": 60.0, "lon": 3.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "UK_North_Sea_Aberdeen", "lat": 57.5, "lon": -2.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Russia — oil & gas (major exporter to Asia)
        {"name": "Russia_Oil_West_Siberia", "lat": 61.0, "lon": 73.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Russia_Gas_Yamal", "lat": 67.0, "lon": 70.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Australia — coal & LNG (major exporter to Asia, affects IDX coal)
        {"name": "Australia_Coal_Queensland_Bowen_Basin", "lat": -22.0, "lon": 148.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Australia_Coal_NSW_Hunter_Valley", "lat": -32.5, "lon": 151.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Australia_LNG_North_West_Shelf", "lat": -20.0, "lon": 116.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Africa — oil (affects global supply)
        {"name": "Nigeria_Oil_Niger_Delta", "lat": 5.5, "lon": 6.5,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Angola_Oil_Cabinda", "lat": -5.5, "lon": 12.2,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # South America — oil (pre-salt, heavy crude)
        {"name": "Brazil_Oil_Pre_Salt_Santos_Basin", "lat": -25.0, "lon": -42.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Venezuela_Oil_Orinoco_Belt", "lat": 8.0, "lon": -64.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Canada — oil sands (affects US supply → WTI)
        {"name": "Canada_Oil_Sands_Alberta", "lat": 57.0, "lon": -111.5,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        # Qatar — LNG (affects Asian gas prices)
        {"name": "Qatar_LNG_North_Field", "lat": 27.5, "lon": 51.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
    ],

    # ── MINING: Global mineral production regions ──
    # Affects IDX: nickel (INCO, ANTM), coal mining (PTBA, ADRO, ITMG),
    # gold (ANTM, MDKA), tin (TINS, MBAP), copper/gold (UNTR, INCO)
    "mining": [
        # Indonesia — nickel, copper, gold, tin (direct IDX impact)
        {"name": "Indonesia_Nickel_Sulawesi", "lat": -1.0, "lon": 121.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Indonesia_Copper_Papua_Grasberg", "lat": -4.0, "lon": 137.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Indonesia_Gold_Sumbawa", "lat": -8.5, "lon": 117.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Indonesia_Tin_Bangka_Belitung", "lat": -2.5, "lon": 106.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Indonesia_Bauxite_West_Kalimantan", "lat": 0.0, "lon": 111.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # Chile — copper (largest producer, affects LME copper price)
        {"name": "Chile_Copper_Atacama", "lat": -24.0, "lon": -69.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Chile_Copper_Escondida", "lat": -23.5, "lon": -68.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # Peru — copper, zinc, silver (2nd largest copper producer)
        {"name": "Peru_Copper_Arequipa", "lat": -16.0, "lon": -72.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Peru_Zinc_Cerro_de_Pasco", "lat": -10.5, "lon": -76.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # Australia — iron ore, gold, lithium (major exporter to China)
        {"name": "Australia_Iron_Ore_Pilbara", "lat": -21.0, "lon": 117.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Australia_Gold_Kalgoorlie", "lat": -30.8, "lon": 121.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Australia_Lithium_Greenbushes", "lat": -33.0, "lon": 116.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # China — rare earth, tungsten (dominant producer)
        {"name": "China_Rare_Earth_Inner_Mongolia", "lat": 40.0, "lon": 110.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "China_Tungsten_Jiangxi", "lat": 27.0, "lon": 115.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # South Africa — platinum, gold, manganese
        {"name": "South_Africa_Platinum_Bushveld", "lat": -25.0, "lon": 27.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "South_Africa_Gold_Witwatersrand", "lat": -26.2, "lon": 28.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "South_Africa_Manganese_Kalahari", "lat": -27.5, "lon": 23.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # DRC — cobalt, copper (largest cobalt producer, battery supply chain)
        {"name": "DRC_Cobalt_Katanga", "lat": -10.5, "lon": 25.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # Mongolia — copper, coal (major exporter to China)
        {"name": "Mongolia_Copper_Oyu_Tolgoi", "lat": 43.5, "lon": 106.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        {"name": "Mongolia_Coal_Tavan_Tolgoi", "lat": 43.5, "lon": 105.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # Brazil — iron ore (Vale, 2nd largest exporter)
        {"name": "Brazil_Iron_Ore_Carajas", "lat": -6.0, "lon": -50.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # Mexico — silver (largest producer)
        {"name": "Mexico_Silver_Zacatecas", "lat": 22.8, "lon": -102.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
        # Guinea — bauxite (largest exporter, affects aluminum)
        {"name": "Guinea_Bauxite_Boke", "lat": 10.5, "lon": -14.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR"]},
    ],

    # ── SHIPPING: Global choke points & major ports ──
    # Affects IDX: shipping/logistics (SMDR, MAYA, BULL, LION, TUGU),
    # port operators (IPOI, PORT, ENZO), coal shipping (ADRO, PTBA)
    "shipping": [
        # Indonesia — ports (direct IDX impact)
        {"name": "Indonesia_Port_Tanjung_Priok", "lat": -6.107, "lon": 106.88,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Indonesia_Port_Tanjung_Perak", "lat": -7.2, "lon": 112.7,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Indonesia_Port_Bitung", "lat": 1.45, "lon": 125.2,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        # Global choke points — affect all shipping routes
        {"name": "Strait_of_Malacca", "lat": 2.5, "lon": 101.0,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Suez_Canal_Port_Said", "lat": 31.3, "lon": 32.3,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Panama_Canal", "lat": 9.1, "lon": -79.7,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Strait_of_Hormuz", "lat": 26.6, "lon": 56.3,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Bab_el_Mandeb_Yemen", "lat": 12.6, "lon": 43.4,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Bosphorus_Istanbul", "lat": 41.1, "lon": 29.0,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        # Major global ports
        {"name": "Singapore_Port", "lat": 1.264, "lon": 103.84,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Rotterdam_Port", "lat": 51.95, "lon": 4.07,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Shanghai_Port_Yangshan", "lat": 30.6, "lon": 122.1,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Shenzhen_Port", "lat": 22.5, "lon": 114.0,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Busan_Port_South_Korea", "lat": 35.1, "lon": 129.0,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Los_Angeles_Port", "lat": 33.7, "lon": -118.3,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Hamburg_Port", "lat": 53.5, "lon": 10.0,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Mumbai_Port_India", "lat": 18.9, "lon": 72.8,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Dubai_Port_Jebel_Ali", "lat": 25.0, "lon": 55.1,
         "metrics": ["T2M", "ALLSKY_SFC_SW_DWN"]},
    ],

    # ── TEXTILES: Global cotton & textile production regions ──
    # Affects IDX: textile stocks (RALS, ERTX, UNIT, ARNA, SRIL, TRIS)
    "textiles": [
        {"name": "US_Cotton_Texas_High_Plains", "lat": 34.0, "lon": -101.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "India_Cotton_Gujarat", "lat": 22.0, "lon": 71.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "China_Cotton_Xinjiang", "lat": 40.0, "lon": 80.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Pakistan_Cotton_Sindh", "lat": 26.0, "lon": 68.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Brazil_Cotton_Mato_Grosso", "lat": -13.0, "lon": -56.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Australia_Cotton_Queensland", "lat": -25.0, "lon": 147.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Turkey_Cotton_Aegean", "lat": 38.5, "lon": 29.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
    ],

    # ── FORESTRY: Global timber & pulp production regions ──
    # Affects IDX: pulp & paper (INKP, TPIA, FASW, TKIM, DSNG)
    "forestry": [
        {"name": "Indonesia_Pulp_Riau_Sumatera", "lat": 0.5, "lon": 101.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Indonesia_Pulp_East_Kalimantan", "lat": -1.0, "lon": 116.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Brazil_Eucalyptus_Bahia", "lat": -14.0, "lon": -40.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Canada_Timber_BC_Interior", "lat": 53.0, "lon": -122.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Russia_Timber_Siberia", "lat": 60.0, "lon": 100.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Sweden_Timber_North", "lat": 65.0, "lon": 20.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Finland_Timber_North", "lat": 66.0, "lon": 26.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Chile_Plantations_Bio_Bio", "lat": -37.0, "lon": -72.5,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
    ],

    # ── AQUACULTURE & FISHING: Global fishing grounds ──
    # Affects IDX: aquaculture/fishery (CBRE, BUDI, DUHA, TSIP, ULAM)
    "aquaculture": [
        {"name": "Indonesia_Aquaculture_South_Sulawesi", "lat": -4.0, "lon": 120.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Indonesia_Fishing_Malaka_Strait", "lat": 4.0, "lon": 99.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Norway_Salmon_Fjords", "lat": 63.0, "lon": 10.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Chile_Salmon_Patagonia", "lat": -42.0, "lon": -72.5,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "China_Aquaculture_Shandong", "lat": 37.0, "lon": 122.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Vietnam_Mekong_Delta_Aquaculture", "lat": 10.0, "lon": 105.0,
         "metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"]},
        {"name": "Peru_Anchovy_Fishing_Grounds", "lat": -12.0, "lon": -78.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
        {"name": "Japan_Fishing_Tohoku", "lat": 39.0, "lon": 141.0,
         "metrics": ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]},
    ],
}

# Mapping from InstrumentMaster.sector values to SECTOR_FALLBACK_LOCATIONS keys.
# Covers both English and Indonesian sector names from various data sources.
SECTOR_NAME_MAP: dict[str, str] = {
    # Agriculture / CPO / Plantation / Food
    "agriculture": "agriculture",
    "consumer_staples": "agriculture",
    "food_beverage": "agriculture",
    "food": "agriculture",
    "plantation": "agriculture",
    "farming": "agriculture",
    "agribusiness": "agriculture",
    "crops": "agriculture",
    # Energy / Oil / Gas / Coal
    "energy": "energy",
    "oil_gas": "energy",
    "oil": "energy",
    "gas": "energy",
    "coal": "energy",
    "petroleum": "energy",
    "utilities": "energy",
    "power": "energy",
    # Mining / Metals / Minerals
    "basic_materials": "mining",
    "mining": "mining",
    "metals_mining": "mining",
    "metals": "mining",
    "materials": "mining",
    "gold": "mining",
    "precious_metals": "mining",
    "nickel": "mining",
    "copper": "mining",
    # Shipping / Logistics / Transportation
    "transportation": "shipping",
    "shipping": "shipping",
    "logistics": "shipping",
    "industrials": "shipping",
    "ports": "shipping",
    "marine": "shipping",
    # Textiles / Apparel
    "textiles": "textiles",
    "apparel": "textiles",
    "consumer_discretionary": "textiles",
    "retail": "textiles",
    # Forestry / Pulp & Paper
    "forestry": "forestry",
    "pulp_paper": "forestry",
    "paper": "forestry",
    "timber": "forestry",
    # Aquaculture / Fishery
    "aquaculture": "aquaculture",
    "fishery": "aquaculture",
    "fishing": "aquaculture",
    "seafood": "aquaculture",
}


class SatelliteFetcher:
    """Fetch and persist satellite data for market correlation analysis.

    Location resolution:
      1. Check satellite_ticker_locations table for explicit ticker mapping
      2. Fall back to SECTOR_FALLBACK_LOCATIONS based on ticker's sector
      3. Skip ticker if no mapping found

    Args:
        session: SQLAlchemy session for database persistence.
        start_date: Start date for data fetching.
        end_date: End date for data fetching.
        cloud_cover_threshold: Max cloud cover % for Sentinel-2 scenes.
    """

    def __init__(
        self,
        session: Session | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        cloud_cover_threshold: float = 30.0,
        rate_limiter: DynamicRateLimiter | None = None,
        batch_years: int = 1,
    ) -> None:
        self.session = session
        self.start_date = start_date or (datetime.now(UTC).date() - timedelta(days=730))
        self.end_date = end_date or datetime.now(UTC).date()
        self.cloud_cover_threshold = cloud_cover_threshold
        self.rate_limiter = rate_limiter or DynamicRateLimiter()
        self.batch_years = batch_years

    def resolve_locations_for_ticker(
        self,
        ticker: str,
        sector: str | None = None,
    ) -> list[dict]:
        """Resolve which geographic locations to fetch for a given ticker.

        Priority:
          1. satellite_ticker_locations table (explicit per-ticker mapping)
          2. SECTOR_FALLBACK_LOCATIONS (sector-based defaults)

        Returns:
            List of {name, lat, lon, metrics} dicts. Empty if no mapping.
        """
        locations: list[dict] = []

        # 1. Check DB for explicit ticker mapping
        if self.session is not None:
            from market.db.models import SatelliteTickerLocation

            rows = self.session.query(SatelliteTickerLocation).filter(
                SatelliteTickerLocation.ticker == ticker,
                SatelliteTickerLocation.is_active == True,  # noqa: E712
            ).all()

            for row in rows:
                locations.append({
                    "name": row.location_name,
                    "lat": float(row.lat),
                    "lon": float(row.lon),
                    "metrics": row.metrics.split(",") if row.metrics else SIGNIFICANT_METRICS,
                })

        # 2. Fallback to sector-based defaults
        if not locations and sector:
            # Normalize: lowercase, replace spaces and non-alphanumeric with underscores
            import re
            sector_lower = re.sub(r"[^a-z0-9]+", "_", sector.lower()).strip("_")
            fallback_key = SECTOR_NAME_MAP.get(sector_lower, "")
            if not fallback_key:
                # Try partial match
                for k, v in SECTOR_NAME_MAP.items():
                    if k in sector_lower or sector_lower in k:
                        fallback_key = v
                        break

            if fallback_key and fallback_key in SECTOR_FALLBACK_LOCATIONS:
                locations = [loc.copy() for loc in SECTOR_FALLBACK_LOCATIONS[fallback_key]]
                logger.info(
                    "Ticker %s: no explicit mapping, using sector '%s' fallback (%d locations)",
                    ticker, fallback_key, len(locations),
                )

        if not locations:
            logger.warning(
                "Ticker %s: no satellite location mapping found (sector=%s) — skipping",
                ticker, sector,
            )

        return locations

    def fetch_for_ticker(
        self,
        ticker: str,
        sector: str | None = None,
    ) -> int:
        """Fetch satellite data for all locations associated with a ticker.

        Args:
            ticker: Stock/commodity ticker (e.g., 'AALI.JK', 'ZC=F').
            sector: Sector name for fallback mapping (e.g., 'agriculture').

        Returns:
            Number of observations persisted.
        """
        locations = self.resolve_locations_for_ticker(ticker, sector)
        if not locations:
            return 0

        total = 0
        for loc in locations:
            total += self.fetch_location(
                location_name=loc["name"],
                lat=loc["lat"],
                lon=loc["lon"],
                metrics=loc["metrics"],
            )
        return total

    def fetch_for_tickers(
        self,
        tickers: list[tuple[str, str | None]],
    ) -> int:
        """Fetch satellite data for multiple tickers.

        Args:
            tickers: List of (ticker, sector) tuples.

        Returns:
            Total observations persisted.
        """
        total = 0
        for ticker, sector in tickers:
            total += self.fetch_for_ticker(ticker, sector)
        return total

    def fetch_all_configured(self) -> int:
        """Fetch satellite data for all tickers in satellite_ticker_locations.

        Only fetches for tickers that have explicit DB mappings.
        Does NOT use sector fallback.

        Returns:
            Total observations persisted.
        """
        if self.session is None:
            logger.warning("No DB session — cannot fetch all configured tickers")
            return 0

        from market.db.models import SatelliteTickerLocation

        rows = self.session.query(SatelliteTickerLocation).filter(
            SatelliteTickerLocation.is_active == True,  # noqa: E712
        ).all()

        # Group by location to avoid duplicate fetches
        seen_locations: set[str] = set()
        total = 0
        for row in rows:
            if row.location_name in seen_locations:
                continue
            seen_locations.add(row.location_name)
            metrics = row.metrics.split(",") if row.metrics else SIGNIFICANT_METRICS
            total += self.fetch_location(
                location_name=row.location_name,
                lat=float(row.lat),
                lon=float(row.lon),
                metrics=metrics,
            )
        if self.session is not None:
            self.session.commit()
        return total

    def fetch_all_global_locations(
        self,
        sectors: list[str] | None = None,
        skip_existing: bool = True,
    ) -> dict:
        """Autonomously fetch satellite data for ALL global fallback locations.

        Iterates over every location in SECTOR_FALLBACK_LOCATIONS (114+ locations
        across 7 sectors, 6 continents). Uses batch processing and dynamic rate
        limiter. Commits after each location to avoid losing progress on failure.

        Args:
            sectors: Optional list of sector keys to fetch (default: all).
            skip_existing: If True, skip locations that already have data in DB.

        Returns:
            Dict with summary: {total_locations, fetched, skipped, errors, observations, rate_limiter_stats}
        """
        target_sectors = sectors or list(SECTOR_FALLBACK_LOCATIONS.keys())
        all_locations: list[tuple[str, str, float, float, list[str]]] = []

        for sector_key in target_sectors:
            locs = SECTOR_FALLBACK_LOCATIONS.get(sector_key, [])
            for loc in locs:
                all_locations.append((
                    sector_key,
                    loc["name"],
                    loc["lat"],
                    loc["lon"],
                    loc["metrics"],
                ))

        total_locs = len(all_locations)
        logger.info(
            "Starting global backfill: %d locations across %d sectors, %s → %s",
            total_locs, len(target_sectors),
            self.start_date.isoformat(), self.end_date.isoformat(),
        )

        fetched = 0
        skipped = 0
        errors = 0
        total_obs = 0

        for i, (sector_key, name, lat, lon, metrics) in enumerate(all_locations):
            logger.info(
                "─── Location %d/%d: %s [%s] (%.4f, %.4f) ───",
                i + 1, total_locs, name, sector_key, lat, lon,
            )

            # Check if data already exists for this location
            if skip_existing and self.session is not None:
                from market.db.models import SatelliteObservation
                existing = self.session.query(SatelliteObservation).filter(
                    SatelliteObservation.location_name == name,
                ).count()
                if existing > 0:
                    logger.info("Skipping %s — already has %d observations", name, existing)
                    skipped += 1
                    continue

            try:
                count = self.fetch_location(name, lat, lon, metrics)
                total_obs += count
                fetched += 1

                # Commit after each location
                if self.session is not None:
                    self.session.commit()

                logger.info(
                    "✓ %s: %d observations (total so far: %d)",
                    name, count, total_obs,
                )
            except CircuitBreakerError as exc:
                errors += 1
                logger.error("✗ %s: circuit breaker tripped — %s", name, exc)
                if self.session is not None:
                    self.session.rollback()
                # Wait for network recovery, then reset circuit and continue
                logger.info("Waiting 60s for network recovery before next location...")
                time.sleep(60)
                self.rate_limiter.reset_circuit()

            except Exception as exc:
                errors += 1
                logger.error("✗ %s failed: %s", name, exc)
                if self.session is not None:
                    self.session.rollback()
                # Reset circuit if it tripped during this location
                if self.rate_limiter.circuit_tripped:
                    logger.info("Circuit breaker was tripped — resetting for next location")
                    self.rate_limiter.reset_circuit()

        rl_stats = self.rate_limiter.stats
        summary = {
            "total_locations": total_locs,
            "fetched": fetched,
            "skipped": skipped,
            "errors": errors,
            "observations": total_obs,
            "rate_limiter_stats": rl_stats,
        }
        logger.info(
            "Global backfill complete: %d fetched, %d skipped, %d errors, %d observations",
            fetched, skipped, errors, total_obs,
        )
        logger.info(
            "Rate limiter: %d requests, %d errors (%.1f%%), final delay %.1fs",
            rl_stats["total_requests"], rl_stats["total_errors"],
            rl_stats["error_rate"] * 100, rl_stats["current_delay"],
        )
        return summary

    def fetch_location(
        self,
        location_name: str,
        lat: float,
        lon: float,
        metrics: list[str],
    ) -> int:
        """Fetch satellite data for a single location and persist to DB.

        Multi-year requests are automatically batched into yearly chunks
        to avoid API timeouts and respect rate limits.

        Args:
            location_name: Human-readable location identifier.
            lat: Latitude (-90 to 90).
            lon: Longitude (-180 to 180).
            metrics: List of metric names to fetch.

        Returns:
            Number of observations persisted.
        """
        count = 0

        # NASA POWER metrics (T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN)
        nasa_metrics = [m for m in metrics if m in NASA_POWER_PARAMS]
        if nasa_metrics:
            count += self._fetch_nasa_power_batched(location_name, lat, lon, nasa_metrics)

        # Sentinel-2 NDVI
        if "NDVI" in metrics:
            count += self._fetch_sentinel2_ndvi_batched(location_name, lat, lon)

        return count

    def _generate_year_batches(self) -> list[tuple[date, date]]:
        """Split self.start_date → self.end_date into yearly batches.

        Returns:
            List of (batch_start, batch_end) date tuples.
        """
        batches: list[tuple[date, date]] = []
        current = self.start_date
        while current <= self.end_date:
            batch_end = min(
                date(current.year + self.batch_years, 1, 1) - timedelta(days=1),
                self.end_date,
            )
            if batch_end < current:
                batch_end = self.end_date
            batches.append((current, batch_end))
            current = batch_end + timedelta(days=1)
        return batches

    def _fetch_nasa_power_batched(
        self,
        location_name: str,
        lat: float,
        lon: float,
        metrics: list[str],
    ) -> int:
        """Fetch NASA POWER data in yearly batches with rate limiting."""
        batches = self._generate_year_batches()
        total = 0
        for i, (batch_start, batch_end) in enumerate(batches):
            logger.info(
                "NASA POWER batch %d/%d: %s (%.4f, %.4f) %s→%s",
                i + 1, len(batches), location_name, lat, lon,
                batch_start.strftime("%Y%m%d"), batch_end.strftime("%Y%m%d"),
            )
            total += self._fetch_nasa_power(
                location_name, lat, lon, metrics,
                override_start=batch_start, override_end=batch_end,
            )
        return total

    def _fetch_sentinel2_ndvi_batched(
        self,
        location_name: str,
        lat: float,
        lon: float,
    ) -> int:
        """Fetch Sentinel-2 NDVI in yearly batches with rate limiting.

        Sentinel-2 data available from July 2015 onwards — skip earlier batches.
        """
        sentinel2_start = date(2015, 7, 1)
        batches = [
            (s, e) for s, e in self._generate_year_batches()
            if e >= sentinel2_start
        ]
        total = 0
        for i, (batch_start, batch_end) in enumerate(batches):
            logger.info(
                "Sentinel-2 batch %d/%d: %s (%.4f, %.4f) %s→%s",
                i + 1, len(batches), location_name, lat, lon,
                batch_start.strftime("%Y-%m-%d"), batch_end.strftime("%Y-%m-%d"),
            )
            total += self._fetch_sentinel2_ndvi(
                location_name, lat, lon,
                override_start=batch_start, override_end=batch_end,
            )
        return total

    def _fetch_nasa_power(
        self,
        location_name: str,
        lat: float,
        lon: float,
        metrics: list[str],
        override_start: date | None = None,
        override_end: date | None = None,
    ) -> int:
        """Fetch weather data from NASA POWER API and persist.

        Uses rate limiter and retry with backoff for resilience.
        """
        start_d = override_start or self.start_date
        end_d = override_end or self.end_date
        start_str = start_d.strftime("%Y%m%d")
        end_str = end_d.strftime("%Y%m%d")
        params_str = ",".join(metrics)

        logger.info(
            "NASA POWER: fetching %s for %s (%.4f, %.4f) %s→%s",
            params_str, location_name, lat, lon, start_str, end_str,
        )

        def _do_request():
            self.rate_limiter.wait()
            resp = requests.get(
                NASA_POWER_URL,
                params={
                    "parameters": params_str,
                    "community": "AG",
                    "longitude": lon,
                    "latitude": lat,
                    "start": start_str,
                    "end": end_str,
                    "format": "JSON",
                },
                timeout=120,
            )
            resp.raise_for_status()
            self.rate_limiter.on_success()
            return resp.json()

        try:
            data = _retry_with_backoff(_do_request, max_retries=3, rate_limiter=self.rate_limiter)
        except Exception as exc:
            logger.error("NASA POWER fetch failed for %s: %s", location_name, exc)
            return 0

        if data is None:
            logger.error("NASA POWER returned None for %s after retries", location_name)
            return 0

        props = data.get("properties", {}).get("parameter", {})
        count = 0

        for metric in metrics:
            if metric not in props:
                continue
            for date_str, value in props[metric].items():
                if value == -999:
                    continue
                obs_date = datetime.strptime(date_str, "%Y%m%d").date()
                count += self._persist_observation(
                    location_name=location_name,
                    lat=lat,
                    lon=lon,
                    date=obs_date,
                    metric=metric,
                    value=float(value),
                    source="nasa_power",
                )

        logger.info("NASA POWER: %d observations persisted for %s", count, location_name)
        return count

    def _fetch_sentinel2_ndvi(
        self,
        location_name: str,
        lat: float,
        lon: float,
        override_start: date | None = None,
        override_end: date | None = None,
    ) -> int:
        """Fetch NDVI from Sentinel-2 via Microsoft Planetary Computer STAC API.

        Reads B04 (red) and B08 (NIR) bands, computes NDVI = (NIR-Red)/(NIR+Red).
        Uses rate limiter for STAC API calls.
        """
        try:
            import planetary_computer as pc
            import pystac_client
            import rasterio
            from rasterio.warp import transform
            from rasterio.windows import Window
            from shapely.geometry import Point, shape
        except ImportError:
            logger.warning(
                "pystac-client/planetary-computer/rasterio not installed — skipping NDVI"
            )
            return 0

        start_d = override_start or self.start_date
        end_d = override_end or self.end_date
        start_str = start_d.strftime("%Y-%m-%d")
        end_str = end_d.strftime("%Y-%m-%d")

        logger.info(
            "Sentinel-2 (Planetary Computer): searching NDVI for %s (%.4f, %.4f) %s→%s",
            location_name, lat, lon, start_str, end_str,
        )

        try:
            self.rate_limiter.wait()
            stac = pystac_client.Client.open(
                PLANETARY_COMPUTER_STAC,
                modifier=pc.sign_inplace,
            )
            search = stac.search(
                collections=["sentinel-2-l2a"],
                intersects={"type": "Point", "coordinates": [lon, lat]},
                datetime=f"{start_str}/{end_str}",
                query={"eo:cloud_cover": {"lt": self.cloud_cover_threshold}},
                max_items=200,
            )
            items = list(search.items())
            self.rate_limiter.on_success()
        except Exception as exc:
            self.rate_limiter.on_error()
            logger.error("STAC search failed for %s: %s", location_name, exc)
            return 0

        logger.info("Sentinel-2: found %d cloud-free scenes for %s", len(items), location_name)

        pt = Point(lon, lat)
        count = 0
        skipped = 0

        for item in items:
            # Check geometry containment
            geom = item.geometry
            if geom is not None:
                try:
                    item_shape = shape(geom)
                    if not item_shape.contains(pt):
                        skipped += 1
                        continue
                except Exception:
                    pass

            try:
                b04_url = item.assets["B04"].href
                b08_url = item.assets["B08"].href

                with rasterio.open(b04_url) as red_src:
                    # Transform lat/lon to raster's CRS (e.g., UTM)
                    xs, ys = transform("EPSG:4326", red_src.crs, [lon], [lat])
                    px, py = red_src.index(xs[0], ys[0])
                    if px < 0 or py < 0 or px >= red_src.height or py >= red_src.width:
                        skipped += 1
                        continue
                    win_size = 50
                    row_off = max(0, px - win_size)
                    col_off = max(0, py - win_size)
                    win_w = min(win_size * 2, red_src.width - col_off)
                    win_h = min(win_size * 2, red_src.height - row_off)
                    if win_w <= 0 or win_h <= 0:
                        skipped += 1
                        continue
                    win = Window(col_off, row_off, win_w, win_h)
                    red_data = red_src.read(1, window=win).astype("float32")

                with rasterio.open(b08_url) as nir_src:
                    nir_data = nir_src.read(1, window=Window(col_off, row_off, win_w, win_h)).astype("float32")

                import numpy as np
                ndvi_vals = (nir_data - red_data) / (nir_data + red_data + 1e-8)
                ndvi_mean = float(np.nanmean(ndvi_vals))

                if np.isnan(ndvi_mean):
                    skipped += 1
                    continue

                # Get scene date
                date_obj = item.datetime
                if date_obj is None:
                    skipped += 1
                    continue
                obs_date = pd.Timestamp(date_obj).tz_localize(None).normalize().date()

                cloud_cover = item.properties.get("eo:cloud_cover", 0)

                count += self._persist_observation(
                    location_name=location_name,
                    lat=lat,
                    lon=lon,
                    date=obs_date,
                    metric="NDVI",
                    value=ndvi_mean,
                    source="sentinel2_pc",
                    cloud_cover_pct=float(cloud_cover),
                    scene_id=item.id,
                )

            except Exception as exc:
                logger.debug("Sentinel-2 item %s failed: %s", item.id, exc)
                skipped += 1
                continue

        logger.info(
            "Sentinel-2 NDVI: %d valid scenes (%d skipped) for %s",
            count, skipped, location_name,
        )
        return count

    def _persist_observation(
        self,
        location_name: str,
        lat: float,
        lon: float,
        date: date,
        metric: str,
        value: float,
        source: str,
        cloud_cover_pct: float | None = None,
        scene_id: str | None = None,
    ) -> int:
        """Persist a single observation to the database (upsert).

        Returns 1 if persisted, 0 if skipped/updated.
        """
        if self.session is None:
            return 0

        from market.db.models import SatelliteObservation

        # Check if observation already exists
        existing = self.session.query(SatelliteObservation).filter(
            SatelliteObservation.location_name == location_name,
            SatelliteObservation.date == date,
            SatelliteObservation.metric == metric,
            SatelliteObservation.source == source,
        ).first()

        if existing is not None:
            # Update value if different
            if abs(float(existing.value) - value) > 1e-6:
                existing.value = Decimal(str(value))
                if cloud_cover_pct is not None:
                    existing.cloud_cover_pct = Decimal(str(cloud_cover_pct))
                if scene_id is not None:
                    existing.scene_id = scene_id
                self.session.flush()
            return 0

        obs = SatelliteObservation(
            location_name=location_name,
            lat=Decimal(str(lat)),
            lon=Decimal(str(lon)),
            date=date,
            metric=metric,
            value=Decimal(str(value)),
            source=source,
            cloud_cover_pct=Decimal(str(cloud_cover_pct)) if cloud_cover_pct is not None else None,
            scene_id=scene_id,
        )
        self.session.add(obs)
        self.session.flush()
        return 1

    def get_observations(
        self,
        location_name: str,
        metric: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Retrieve satellite observations from the database.

        Returns a DataFrame with columns: date, metric, value, source.
        """
        from market.db.models import SatelliteObservation

        if self.session is None:
            return pd.DataFrame()

        query = self.session.query(SatelliteObservation).filter(
            SatelliteObservation.location_name == location_name,
        )
        if metric:
            query = query.filter(SatelliteObservation.metric == metric)
        if start_date:
            query = query.filter(SatelliteObservation.date >= start_date)
        if end_date:
            query = query.filter(SatelliteObservation.date <= end_date)

        rows = query.order_by(SatelliteObservation.date).all()
        if not rows:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                "date": r.date,
                "metric": r.metric,
                "value": float(r.value),
                "source": r.source,
            }
            for r in rows
        ])


def save_correlation_results(
    session: Session,
    results: list[dict],
) -> int:
    """Save correlation analysis results to the database.

    Args:
        session: SQLAlchemy session.
        results: List of result dicts with keys matching SatelliteCorrelationResult.

    Returns:
        Number of results persisted.
    """
    from market.db.models import SatelliteCorrelationResult

    count = 0
    for r in results:
        # Check for existing record (upsert)
        existing = session.query(SatelliteCorrelationResult).filter(
            SatelliteCorrelationResult.location_name == r["location_name"],
            SatelliteCorrelationResult.satellite_metric == r["satellite_metric"],
            SatelliteCorrelationResult.stock_ticker == r["stock_ticker"],
            SatelliteCorrelationResult.frequency == r["frequency"],
            SatelliteCorrelationResult.rolling_window == r["rolling_window"],
        ).first()

        if existing is not None:
            # Update
            existing.optimal_lag = r["optimal_lag"]
            existing.optimal_corr = Decimal(str(r["optimal_corr"]))
            existing.optimal_pvalue = Decimal(str(r["optimal_pvalue"]))
            if r.get("granger_optimal_pvalue") is not None:
                existing.granger_optimal_pvalue = Decimal(str(r["granger_optimal_pvalue"]))
            existing.is_significant = r.get("is_significant", False)
            session.flush()
            continue

        result = SatelliteCorrelationResult(
            location_name=r["location_name"],
            satellite_metric=r["satellite_metric"],
            stock_ticker=r["stock_ticker"],
            frequency=r["frequency"],
            rolling_window=r["rolling_window"],
            optimal_lag=r["optimal_lag"],
            optimal_corr=Decimal(str(r["optimal_corr"])),
            optimal_pvalue=Decimal(str(r["optimal_pvalue"])),
            granger_optimal_pvalue=Decimal(str(r["granger_optimal_pvalue"])) if r.get("granger_optimal_pvalue") is not None else None,
            is_significant=r.get("is_significant", False),
            lag_unit=r.get("lag_unit", "hari"),
        )
        session.add(result)
        count += 1

    session.flush()
    return count


def seed_ticker_locations(session: Session) -> int:
    """Seed initial ticker→location mappings for proven significant tickers.

    Returns:
        Number of mappings inserted.
    """
    from market.db.models import SatelliteTickerLocation

    seed_data = [
        # CPO — Indonesian palm oil companies
        ("AALI.JK", "CPO_Kalimantan_Tengah", -2.5, 113.0, "agriculture",
         "NDVI,T2M,PRECTOTCORR,RH2M", "Astra Agro Lestari — perkebunan sawit Kalimantan"),
        ("AALI.JK", "CPO_Sumatera_Selatan", -3.0, 104.0, "agriculture",
         "NDVI,T2M,PRECTOTCORR,RH2M", "Astra Agro Lestari — perkebunan sawit Sumatera"),
        ("LSIP.JK", "CPO_Sumatera_Selatan", -3.0, 104.0, "agriculture",
         "NDVI,T2M,PRECTOTCORR,RH2M", "London Sumatra — perkebunan sawit Sumatera"),
        ("LSIP.JK", "CPO_Kalimantan_Tengah", -2.5, 113.0, "agriculture",
         "NDVI,T2M,PRECTOTCORR,RH2M", "London Sumatra — perkebunan sawit Kalimantan"),

        # US Corn futures
        ("ZC=F", "US_Corn_Belt_Iowa", 41.878, -93.098, "agriculture",
         "NDVI,T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN", "Iowa corn belt — primary US corn production"),

        # US Soybean futures
        ("ZS=F", "US_Soybean_Illinois", 40.0, -89.0, "agriculture",
         "NDVI,T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN", "Illinois soybean belt — primary US soybean production"),

        # US Wheat futures
        ("ZW=F", "US_Wheat_Kansas", 38.5, -98.0, "agriculture",
         "NDVI,T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN", "Kansas wheat belt — primary US wheat production"),
    ]

    count = 0
    for ticker, loc_name, lat, lon, sector, metrics, desc in seed_data:
        existing = session.query(SatelliteTickerLocation).filter(
            SatelliteTickerLocation.ticker == ticker,
            SatelliteTickerLocation.location_name == loc_name,
        ).first()

        if existing is not None:
            continue

        loc = SatelliteTickerLocation(
            ticker=ticker,
            location_name=loc_name,
            lat=Decimal(str(lat)),
            lon=Decimal(str(lon)),
            sector=sector,
            metrics=metrics,
            description=desc,
            is_active=True,
        )
        session.add(loc)
        count += 1

    session.flush()
    return count
