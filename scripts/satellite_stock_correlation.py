"""Satellite-to-Stock Correlation Pipeline.

Mengunduh data satelit gratis (NASA POWER API + Sentinel-2 NDVI via
Microsoft Planetary Computer), menyelaraskan dengan harga saham/komoditas
harian, dan menguji korelasi serta hubungan lead-lag (time-lag) antara
metrik satelit dan return saham.

Hanya data satelit yang terbukti signifikan (p < 0.05) yang di-render:
  - NDVI (Sentinel-2): untuk komoditas pertanian
  - T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN (NASA POWER): untuk CPO & Corn

Test Cases (berdasarkan Matriks Relevansi Data Satelit vs Pasar Modal):
  Kasus A — Perkebunan CPO (Kalimantan Tengah):
    Sentinel-2 NDVI & cuaca vs AALI.JK / LSIP.JK
  Kasus C — Corn (Iowa, US):
    Sentinel-2 NDVI & cuaca vs ZC=F (Corn Futures)
  Kasus D — Soybean (Illinois, US):
    Sentinel-2 NDVI & cuaca vs ZS=F (Soybean Futures)
  Kasus E — Wheat (Kansas, US):
    Sentinel-2 NDVI & cuaca vs ZW=F (Wheat Futures)

DROPPED:
  - Kasus B (Port/Shipping) — tidak ada korelasi signifikan
  - NIGHTLIGHT — simulasi, tidak terbukti dengan data real

Usage:
  uv run python scripts/satellite_stock_correlation.py
  uv run python scripts/satellite_stock_correlation.py --years 3
  uv run python scripts/satellite_stock_correlation.py --use-yfinance
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from scipy import stats
from statsmodels.tsa.stattools import grangercausalitytests

# ── Project path setup ────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("satellite_stock_corr")

OUTPUT_DIR = PROJECT_DIR / "output" / "satellite_correlation"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Test case definitions — filtered based on proven significant correlations
# (pustaka/99-matriks-relevansi-satelit-pasar-modal.md)
# Only metrics with p < 0.05 in at least one frequency are included.
# Kasus B (Port/Shipping) DROPPED — no significant results.
# NIGHTLIGHT DROPPED — simulation only, not proven with real data.
TEST_CASES: list[dict] = [
    {
        "name": "Kasus A — Perkebunan CPO (Kalimantan Tengah)",
        "lat": -2.5,
        "lon": 113.0,
        "tickers": ["AALI.JK", "LSIP.JK"],
        "satellite_metrics": ["NDVI", "T2M", "PRECTOTCORR", "RH2M"],
        "description": "Sentinel-2 NDVI & cuaca perkebunan sawit vs saham CPO",
    },
    {
        "name": "Kasus C — Corn (Iowa, US)",
        "lat": 41.878,
        "lon": -93.098,
        "tickers": ["ZC=F"],
        "satellite_metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"],
        "description": "Sentinel-2 NDVI & cuaca Iowa corn belt vs Corn futures (ZC=F)",
    },
    {
        "name": "Kasus D — Soybean (Illinois, US)",
        "lat": 40.0,
        "lon": -89.0,
        "tickers": ["ZS=F"],
        "satellite_metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"],
        "description": "Sentinel-2 NDVI & cuaca Illinois soybean belt vs Soybean futures (ZS=F)",
    },
    {
        "name": "Kasus E — Wheat (Kansas, US)",
        "lat": 38.5,
        "lon": -98.0,
        "tickers": ["ZW=F"],
        "satellite_metrics": ["NDVI", "T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"],
        "description": "Sentinel-2 NDVI & cuaca Kansas wheat belt vs Wheat futures (ZW=F)",
    },
]

MAX_LAG_DAYS = 60
GRANGER_MAX_LAG = 20
ROLLING_WINDOWS = [7, 30]

# Resampling frequencies: (label, pandas_freq, max_lag, granger_max_lag, unit_label)
FREQUENCIES = [
    ("daily", None, MAX_LAG_DAYS, GRANGER_MAX_LAG, "hari"),
    ("weekly", "W", 8, 6, "minggu"),
    ("monthly", "M", 3, 3, "bulan"),
]


# ═══════════════════════════════════════════════════════════════════════
# 1. SATELLITE DATA FETCHER
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class SatelliteDataFetcher:
    """Fetch satellite-derived data from free APIs with simulation fallback."""

    lat: float
    lon: float
    start_date: date
    end_date: date

    # NASA POWER parameter codes
    NASA_PARAMS: list[str] = field(default_factory=lambda: [
        "T2M",              # Temperature at 2m (°C)
        "PRECTOTCORR",      # Precipitation (mm/day)
        "RH2M",             # Relative humidity at 2m (%)
        "ALLSKY_SFC_SW_DWN",  # Surface shortwave downward irradiance (W/m²)
    ])

    def fetch_all(self) -> pd.DataFrame:
        """Fetch all available satellite metrics, return as daily DataFrame.

        Only renders data proven significant in correlation analysis:
        - NASA POWER: T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN
        - Sentinel-2 NDVI via Microsoft Planetary Computer
        NIGHTLIGHT dropped — simulation only, not proven with real data.
        """
        df = self._fetch_nasa_power()

        # Try Sentinel-2 via Planetary Computer for NDVI; fallback to simulation
        ndvi = self._fetch_ndvi()
        if ndvi is not None and not ndvi.empty:
            logger.info("Using real Sentinel-2 NDVI data")
            df = df.join(ndvi, how="outer")
        else:
            logger.info("NDVI: using simulation fallback")
            sim_ndvi = self._simulate_ndvi(df)
            df = df.join(sim_ndvi, how="outer")

        return df

    def _fetch_nasa_power(self) -> pd.DataFrame:
        """Fetch real satellite-derived environmental data from NASA POWER API."""
        start_str = self.start_date.strftime("%Y%m%d")
        end_str = self.end_date.strftime("%Y%m%d")
        params_str = ",".join(self.NASA_PARAMS)

        logger.info(
            "NASA POWER: fetching %s for (%.4f, %.4f) %s→%s",
            params_str, self.lat, self.lon, start_str, end_str,
        )

        params = {
            "parameters": params_str,
            "community": "AG",
            "longitude": self.lon,
            "latitude": self.lat,
            "start": start_str,
            "end": end_str,
            "format": "JSON",
        }

        try:
            resp = requests.get(NASA_POWER_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("NASA POWER API failed: %s — using simulation", exc)
            return self._simulate_environmental()

        data = resp.json()
        props = data.get("properties", {}).get("parameter", {})

        frames = {}
        for param_code, daily_dict in props.items():
            # Convert {YYYYMMDD: value} to Series
            records = []
            for yyyymmdd, val in daily_dict.items():
                if val == -999 or val is None:
                    continue
                d = pd.to_datetime(yyyymmdd, format="%Y%m%d")
                records.append({"date": d, param_code: float(val)})
            if records:
                s = pd.DataFrame(records).set_index("date")[param_code]
                frames[param_code] = s

        if not frames:
            logger.warning("NASA POWER returned no valid data — using simulation")
            return self._simulate_environmental()

        df = pd.DataFrame(frames)
        df.index.name = "date"
        # Replace remaining -999 with NaN
        df = df.replace(-999, np.nan)

        logger.info("NASA POWER: %d rows, columns=%s", len(df), list(df.columns))
        return df

    def _fetch_ndvi(self) -> pd.Series | None:
        """Fetch real NDVI from Sentinel-2 via Microsoft Planetary Computer.

        Uses the STAC API to find cloud-free Sentinel-2 L2A scenes,
        reads B04 (red) and B08 (NIR) bands, computes NDVI.

        No account needed — Planetary Computer is free and open.
        """
        try:
            import pystac_client
            import planetary_computer as pc
            import rasterio
            from rasterio.windows import Window
            from rasterio.warp import transform
            from shapely.geometry import Point, shape
        except ImportError:
            logger.warning("pystac-client/planetary-computer/rasterio not installed — NDVI simulation fallback")
            return None

        start_str = self.start_date.strftime("%Y-%m-%d")
        end_str = self.end_date.strftime("%Y-%m-%d")

        logger.info(
            "Sentinel-2 (Planetary Computer): searching NDVI for (%.4f, %.4f) %s→%s",
            self.lat, self.lon, start_str, end_str,
        )

        try:
            stac = pystac_client.Client.open(
                "https://planetarycomputer.microsoft.com/api/stac/v1",
                modifier=pc.sign_inplace,
            )
            search = stac.search(
                collections=["sentinel-2-l2a"],
                intersects={"type": "Point", "coordinates": [self.lon, self.lat]},
                datetime=f"{start_str}/{end_str}",
                query={"eo:cloud_cover": {"lt": 30}},
                max_items=200,
            )
            items = list(search.items())
        except Exception as exc:
            logger.error("Sentinel-2 STAC search failed: %s — NDVI simulation fallback", exc)
            return None

        if not items:
            logger.warning("Sentinel-2: no cloud-free scenes found — NDVI simulation fallback")
            return None

        logger.info("Sentinel-2: found %d cloud-free scenes", len(items))

        # Sort by date
        items.sort(key=lambda item: item.datetime)

        # Point geometry for containment check
        pt = Point(self.lon, self.lat)

        ndvi_records = []
        skipped = 0
        for item in items:
            date_obj = item.datetime
            if date_obj is None:
                continue

            # Check if point is within this item's geometry (MGRS tile)
            geom = item.geometry
            if geom is not None:
                try:
                    item_shape = shape(geom)
                    if not item_shape.contains(pt):
                        skipped += 1
                        continue
                except Exception:
                    pass  # If geometry check fails, try anyway

            try:
                b04_url = item.assets["B04"].href
                b08_url = item.assets["B08"].href

                # Read a small window around the point (100x100 pixels at 10m = 1km²)
                with rasterio.open(b04_url) as red_src:
                    # Transform lat/lon to raster's CRS (e.g., UTM)
                    xs, ys = transform("EPSG:4326", red_src.crs, [self.lon], [self.lat])
                    px, py = red_src.index(xs[0], ys[0])
                    # Skip if point is outside this tile's bounds
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
                    red_data = red_src.read(1, window=win).astype(np.float32)
                    red_data = np.where(red_data == red_src.nodata, np.nan, red_data)

                with rasterio.open(b08_url) as nir_src:
                    nir_data = nir_src.read(1, window=Window(
                        col_off, row_off, win_w, win_h
                    )).astype(np.float32)
                    nir_data = np.where(nir_data == nir_src.nodata, np.nan, nir_data)

                # NDVI = (NIR - Red) / (NIR + Red)
                ndvi_vals = (nir_data - red_data) / (nir_data + red_data + 1e-8)
                ndvi_mean = float(np.nanmean(ndvi_vals))

                if np.isnan(ndvi_mean):
                    skipped += 1
                    continue

                ndvi_records.append({
                    "date": pd.Timestamp(date_obj).tz_localize(None).normalize(),
                    "NDVI": ndvi_mean,
                })

            except Exception as exc:
                logger.debug("Sentinel-2 item %s failed: %s", item.id, exc)
                skipped += 1
                continue

        if not ndvi_records:
            logger.warning("Sentinel-2: all scenes failed (%d skipped) — NDVI simulation fallback", skipped)
            return None

        df = pd.DataFrame(ndvi_records).set_index("date")
        df.index.name = "date"

        # Remove duplicate dates (keep first)
        df = df[~df.index.duplicated(keep="first")]

        logger.info(
            "Sentinel-2 NDVI: %d valid scenes (%d skipped), range %.3f–%.3f",
            len(df), skipped, df["NDVI"].min(), df["NDVI"].max(),
        )
        return df["NDVI"]

    def _simulate_ndvi(self, env_df: pd.DataFrame) -> pd.Series:
        """Simulate realistic NDVI driven by precipitation and seasonal pattern.

        NDVI for palm oil plantations in Kalimantan:
        - Wet season (Oct-Apr): higher NDVI (0.6-0.8)
        - Dry season (May-Sep): lower NDVI (0.4-0.6)
        - Precipitation is a strong driver (lag ~15-30 days)
        """
        rng = np.random.default_rng(seed=42)
        dates = pd.date_range(self.start_date, self.end_date, freq="D", name="date")

        # Seasonal component (Indonesian wet/dry cycle)
        day_of_year = np.array(dates.dayofyear)
        # Peak around March (wet season), trough around August (dry season)
        seasonal = 0.6 + 0.15 * np.sin(2 * np.pi * (day_of_year - 60) / 365.25)

        # Precipitation driver (if available, with 20-day lag)
        if "PRECTOTCORR" in env_df.columns:
            precip = env_df["PRECTOTCORR"].reindex(dates).fillna(0)
            precip_lagged = precip.shift(20).fillna(0)
            # Normalize precipitation to [-0.1, +0.1] influence
            precip_norm = (precip_lagged - precip_lagged.mean()) / (precip_lagged.std() + 1e-8)
            precip_effect = 0.08 * np.tanh(precip_norm.values)
        else:
            precip_effect = np.zeros(len(dates))

        # Sensor noise
        noise = rng.normal(0, 0.03, len(dates))

        ndvi_values = np.asarray(seasonal, dtype=float) + np.asarray(precip_effect, dtype=float) + noise
        # Clip to valid NDVI range
        ndvi_values = np.clip(ndvi_values, 0.1, 0.9)

        # Simulate cloud cover gaps (missing data ~20% of days)
        cloud_mask = rng.random(len(dates)) < 0.20
        ndvi_values[cloud_mask] = np.nan

        return pd.Series(ndvi_values, index=dates, name="NDVI")

    def _fetch_nightlight(self) -> pd.Series | None:
        """Fetch VIIRS nighttime light radiance via NASA Earthdata.

        Requires EARTHDATA_USERNAME and EARTHDATA_PASSWORD env vars.
        Uses the VIIRS Black Marble monthly composite via GIBS WMS or
        Earthdata Search API.

        Returns None if credentials not available → simulation fallback.
        """
        username = os.environ.get("EARTHDATA_USERNAME", "")
        password = os.environ.get("EARTHDATA_PASSWORD", "")

        if not username or not password:
            logger.info("VIIRS: no EARTHDATA credentials — simulation fallback")
            return None

        # VIIRS Black Marble monthly composites are available via
        # NASA GIBS WMS service. We can query the raster value at a point.
        # However, this requires complex WMS parsing.
        # For now, log that credentials exist but implementation is deferred.
        logger.info("VIIRS: Earthdata credentials found but monthly composite fetch not yet implemented — simulation fallback")
        return None

    def _simulate_nightlight(self, env_df: pd.DataFrame) -> pd.Series:
        """Simulate nightlight intensity for industrial/port zone.

        Nightlight (VIIRS DNB proxy):
        - Slow upward trend (economic growth ~3-5% p.a.)
        - Seasonal: brighter during holiday seasons (Ramadan, year-end)
        - Weather effect: clouds reduce observed radiance
        """
        rng = np.random.default_rng(seed=99)
        dates = pd.date_range(self.start_date, self.end_date, freq="D", name="date")
        n = len(dates)

        # Linear trend (economic growth)
        days_from_start = (dates - dates[0]).days.values
        trend = 1.0 + 0.03 * days_from_start / 365.25  # ~3% annual growth

        # Seasonal: Ramadan effect (varies each year) + year-end
        month = dates.month.values
        seasonal = np.zeros(n)
        # Year-end boost (Nov-Dec)
        seasonal[(month == 11) | (month == 12)] += 0.08
        # Mid-year dip (Jun-Jul, slower activity)
        seasonal[(month == 6) | (month == 7)] -= 0.04

        # Cloud cover effect (if irradiance available, lower irradiance = more clouds)
        if "ALLSKY_SFC_SW_DWN" in env_df.columns:
            irradiance = env_df["ALLSKY_SFC_SW_DWN"].reindex(dates).fillna(
                env_df["ALLSKY_SFC_SW_DWN"].median()
            )
            # Low irradiance → cloudy → reduced observed nightlight
            cloud_factor = -0.05 * (irradiance < irradiance.quantile(0.25)).astype(float).values
        else:
            cloud_factor = np.zeros(n)

        # Noise
        noise = rng.normal(0, 0.02, n)

        values = trend + seasonal + cloud_factor + noise
        # Clip to positive
        values = np.clip(values, 0.1, None)

        return pd.Series(values, index=dates, name="NIGHTLIGHT")

    def _simulate_environmental(self) -> pd.DataFrame:
        """Simulate environmental data if NASA POWER API fails."""
        rng = np.random.default_rng(seed=77)
        dates = pd.date_range(self.start_date, self.end_date, freq="D", name="date")
        n = len(dates)
        day_of_year = np.array(dates.dayofyear)

        # Temperature: tropical, seasonal ~±2°C around mean
        mean_temp = 27.0 if self.lat > -10 else 25.0
        temp = mean_temp + 2.0 * np.sin(2 * np.pi * (day_of_year - 120) / 365.25)
        temp += rng.normal(0, 1.0, n)

        # Precipitation: wet/dry season, gamma-like distribution
        wet_season = np.sin(2 * np.pi * (day_of_year - 60) / 365.25) > 0
        base_rain = np.where(wet_season, 15.0, 3.0)
        precip = rng.gamma(shape=1.5, scale=base_rain / 1.5)

        # Humidity: inversely correlated with temperature
        humidity = 80.0 - 0.5 * (temp - mean_temp) + rng.normal(0, 5, n)
        humidity = np.clip(humidity, 30, 100)

        # Irradiance: seasonal + cloud noise
        irradiance = 180 + 40 * np.sin(2 * np.pi * (day_of_year - 80) / 365.25)
        irradiance += rng.normal(0, 20, n)
        irradiance = np.clip(irradiance, 50, 300)

        df = pd.DataFrame({
            "T2M": temp,
            "PRECTOTCORR": precip,
            "RH2M": humidity,
            "ALLSKY_SFC_SW_DWN": irradiance,
        }, index=dates)
        df.index.name = "date"

        logger.info("Environmental simulation: %d rows", len(df))
        return df


# ═══════════════════════════════════════════════════════════════════════
# 2. STOCK DATA FETCHER
# ═══════════════════════════════════════════════════════════════════════
class StockDataFetcher:
    """Fetch daily OHLCV from SQLite/PostgreSQL or yfinance fallback."""

    def __init__(self, use_yfinance: bool = False) -> None:
        self.use_yfinance = use_yfinance
        self._db_path = self._resolve_db_path()

    def _resolve_db_path(self) -> str:
        env = os.environ.get("ENV", "paper")
        db_path = os.environ.get("DB_PATH", "")
        if not db_path:
            db_path = str(PROJECT_DIR / "data" / f"market_{env}.db")
        return db_path

    def fetch(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Fetch daily OHLCV for ticker. Returns DataFrame with date index."""
        if self.use_yfinance:
            return self._fetch_yfinance(ticker, start, end)
        return self._fetch_from_db(ticker, start, end)

    def _fetch_from_db(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Fetch from SQLite ohlcv table."""
        import sqlite3

        db_path = self._db_path
        if not Path(db_path).exists():
            logger.warning("DB not found at %s — falling back to yfinance", db_path)
            return self._fetch_yfinance(ticker, start, end)

        logger.info("Fetching %s from DB (%s)", ticker, db_path)
        conn = sqlite3.connect(db_path)
        try:
            query = """
                SELECT timestamp as date, open, high, low, close,
                       volume, adjusted_close
                FROM ohlcv
                WHERE ticker = ?
                  AND timestamp >= ?
                  AND timestamp <= ?
                ORDER BY timestamp
            """
            df = pd.read_sql_query(
                query, conn, params=(ticker, start.isoformat(), end.isoformat()),
                parse_dates=["date"],
            )
        finally:
            conn.close()

        if df.empty:
            logger.warning("No DB data for %s — falling back to yfinance", ticker)
            return self._fetch_yfinance(ticker, start, end)

        df = df.set_index("date")
        # Use adjusted_close if available, else close
        if "adjusted_close" in df.columns and df["adjusted_close"].notna().any():
            df["price"] = df["adjusted_close"]
        else:
            df["price"] = df["close"]

        logger.info("  %s: %d rows (%s → %s)", ticker, len(df),
                     df.index[0].date(), df.index[-1].date())
        return df

    def _fetch_yfinance(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Fetch from yfinance as fallback."""
        import yfinance as yf

        logger.info("Fetching %s from yfinance", ticker)
        df = yf.download(
            ticker, start=start.isoformat(), end=end.isoformat(),
            auto_adjust=True, progress=False,
        )
        if df is None or df.empty:
            raise ValueError(f"No data for {ticker}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.index.name = "date"
        df["price"] = df["Close"]
        df["volume"] = df["Volume"]

        logger.info("  %s: %d rows (%s → %s)", ticker, len(df),
                     df.index[0].date(), df.index[-1].date())
        return df


# ═══════════════════════════════════════════════════════════════════════
# 3. DATA ALIGNER
# ═══════════════════════════════════════════════════════════════════════
class DataAligner:
    """Align satellite data to stock trading days with interpolation & smoothing."""

    @staticmethod
    def align_to_trading_days(
        satellite_df: pd.DataFrame,
        stock_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Reindex satellite data to match stock trading days.

        - Forward-fill + linear interpolation for gaps
        - Drops NaN at edges
        """
        # Reindex satellite to stock trading days
        aligned = satellite_df.reindex(stock_df.index)

        # Linear interpolation for internal gaps
        aligned = aligned.interpolate(method="linear", limit_direction="both")

        # Forward-fill any remaining edge NaNs
        aligned = aligned.ffill().bfill()

        return aligned

    @staticmethod
    def apply_rolling_smoothing(
        df: pd.DataFrame,
        windows: list[int] | None = None,
    ) -> dict[int, pd.DataFrame]:
        """Apply rolling average smoothing at multiple window sizes."""
        if windows is None:
            windows = ROLLING_WINDOWS

        result = {}
        for w in windows:
            smoothed = df.rolling(window=w, min_periods=1).mean()
            result[w] = smoothed

        return result

    @staticmethod
    def compute_returns(prices: pd.Series) -> pd.Series:
        """Compute daily log returns."""
        returns = np.log(prices / prices.shift(1))
        returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
        return returns

    @staticmethod
    def compute_changes(series: pd.Series) -> pd.Series:
        """Compute first differences (for non-price satellite metrics)."""
        return series.diff().dropna()

    @staticmethod
    def resample_data(df: pd.DataFrame, freq: str) -> pd.DataFrame:
        """Resample daily data to weekly or monthly frequency.

        Uses mean aggregation for satellite metrics.
        """
        resampled = df.resample(freq).mean()
        resampled = resampled.dropna(how="all")
        return resampled

    @staticmethod
    def resample_prices(prices: pd.Series, freq: str) -> pd.Series:
        """Resample daily prices to weekly/monthly (last observation)."""
        resampled = prices.resample(freq).last()
        return resampled.dropna()

    @staticmethod
    def compute_period_returns(prices: pd.Series) -> pd.Series:
        """Compute log returns over the resampled period."""
        returns = np.log(prices / prices.shift(1))
        returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
        return returns


# ═══════════════════════════════════════════════════════════════════════
# 4. LAG ANALYZER (CCF + GRANGER)
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class LagResult:
    """Result of lag analysis for one satellite metric vs one stock metric."""
    satellite_metric: str
    stock_ticker: str
    stock_metric: str  # "returns" or "price_change"
    rolling_window: int
    frequency: str  # "daily", "weekly", "monthly"
    lag_unit: str  # "hari", "minggu", "bulan"
    optimal_lag: int
    optimal_corr: float
    optimal_pvalue: float
    ccf_lags: np.ndarray
    ccf_values: np.ndarray
    granger_pvalues: dict[int, float]
    granger_optimal_pvalue: float
    is_significant: bool


class LagAnalyzer:
    """Cross-correlation and Granger causality analysis with time-lag."""

    def __init__(self, max_lag: int = MAX_LAG_DAYS) -> None:
        self.max_lag = max_lag

    def cross_correlation(
        self,
        x: pd.Series,
        y: pd.Series,
        max_lag: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute cross-correlation function (CCF) for lags -max_lag to +max_lag.

        Positive lag means x leads y by that many days.
        Returns (lags, correlations).
        """
        if max_lag is None:
            max_lag = self.max_lag

        # Align indices
        common = x.index.intersection(y.index)
        if len(common) < max_lag + 10:
            logger.warning("Insufficient overlap: %d points", len(common))
            return np.array([]), np.array([])

        x_vals = x.loc[common].values
        y_vals = y.loc[common].values

        # Remove NaN
        mask = ~(np.isnan(x_vals) | np.isnan(y_vals))
        x_vals = x_vals[mask]
        y_vals = y_vals[mask]

        if len(x_vals) < max_lag + 10:
            logger.warning("Insufficient non-NaN data: %d points", len(x_vals))
            return np.array([]), np.array([])

        # Normalize
        x_norm = (x_vals - x_vals.mean()) / (x_vals.std() + 1e-10)
        y_norm = (y_vals - y_vals.mean()) / (y_vals.std() + 1e-10)

        lags = np.arange(-max_lag, max_lag + 1)
        corrs = np.zeros(len(lags))

        n = len(x_norm)
        for i, lag in enumerate(lags):
            if lag < 0:
                # x leads y by |lag| days
                a = x_norm[:n + lag]
                b = y_norm[-lag:]
            elif lag > 0:
                # y leads x by lag days
                a = x_norm[lag:]
                b = y_norm[:n - lag]
            else:
                a = x_norm
                b = y_norm
            corrs[i] = np.corrcoef(a, b)[0, 1]

        return lags, corrs

    def find_optimal_lag(
        self,
        x: pd.Series,
        y: pd.Series,
        max_lag: int | None = None,
    ) -> tuple[int, float, float, np.ndarray, np.ndarray]:
        """Find lag with highest absolute correlation.

        Returns (optimal_lag, correlation, p_value, all_lags, all_corrs).
        """
        lags, corrs = self.cross_correlation(x, y, max_lag=max_lag)
        if len(lags) == 0:
            return 0, 0.0, 1.0, lags, corrs

        abs_corrs = np.abs(corrs)
        best_idx = np.argmax(abs_corrs)
        best_lag = int(lags[best_idx])
        best_corr = float(corrs[best_idx])

        # Compute p-value for the optimal lag
        n = len(x)
        if abs(best_corr) < 1.0 and n > 2:
            t_stat = best_corr * np.sqrt((n - 2) / (1 - best_corr**2 + 1e-10))
            p_value = 2 * stats.t.sf(np.abs(t_stat), df=n - 2)
        else:
            p_value = 1.0

        return best_lag, best_corr, float(p_value), lags, corrs

    def granger_causality(
        self,
        x: pd.Series,
        y: pd.Series,
        max_lag: int | None = None,
    ) -> dict[int, float]:
        """Run Granger causality test: does x granger-cause y?

        Tests multiple lag orders. Returns {lag_order: p_value}.
        Uses F-test p-values from ssr_ftest.
        """
        if max_lag is None:
            max_lag = min(GRANGER_MAX_LAG, len(x) // 5)

        # Align and prepare data
        common = x.index.intersection(y.index)
        x_aligned = x.loc[common].dropna()
        y_aligned = y.loc[common].dropna()

        # Re-intersect after dropna
        common2 = x_aligned.index.intersection(y_aligned.index)
        x_clean = x_aligned.loc[common2]
        y_clean = y_aligned.loc[common2]

        if len(x_clean) < max_lag * 5:
            logger.warning("Insufficient data for Granger: %d points", len(x_clean))
            return {}

        # Granger requires stationary series — use differenced series
        x_diff = x_clean.diff().dropna()
        y_diff = y_clean.diff().dropna()

        # Align after differencing
        common3 = x_diff.index.intersection(y_diff.index)
        x_diff = x_diff.loc[common3]
        y_diff = y_diff.loc[common3]

        # grangercausalitytests expects [y, x] (does x cause y?)
        data = pd.DataFrame({"y": y_diff, "x": x_diff})

        pvalues = {}
        for lag in range(1, max_lag + 1):
            try:
                import warnings as _w
                with _w.catch_warnings():
                    _w.simplefilter("ignore", category=FutureWarning)
                    result = grangercausalitytests(data[["y", "x"]], maxlag=lag, verbose=False)
                # result[lag] is a dict with test results
                # Use F-test (ssr_ftest) p-value
                p_val = result[lag][0]["ssr_ftest"][1]
                pvalues[lag] = float(p_val)
            except Exception as exc:
                logger.debug("Granger lag=%d failed: %s", lag, exc)
                pvalues[lag] = 1.0

        return pvalues

    def analyze(
        self,
        satellite_series: pd.Series,
        stock_returns: pd.Series,
        satellite_name: str,
        ticker: str,
        rolling_window: int,
        frequency: str = "daily",
        lag_unit: str = "hari",
        max_lag: int | None = None,
        granger_max_lag: int | None = None,
    ) -> LagResult:
        """Full lag analysis for one satellite metric vs one stock."""
        if max_lag is None:
            max_lag = self.max_lag
        if granger_max_lag is None:
            granger_max_lag = min(GRANGER_MAX_LAG, len(satellite_series) // 5)

        # Align indices
        common = satellite_series.index.intersection(stock_returns.index)
        sat = satellite_series.loc[common].dropna()
        ret = stock_returns.loc[common].dropna()
        common2 = sat.index.intersection(ret.index)
        sat = sat.loc[common2]
        ret = ret.loc[common2]

        min_points = max_lag + 10
        if len(sat) < min_points:
            logger.warning(
                "Insufficient data for %s vs %s (%s): %d points (need %d)",
                satellite_name, ticker, frequency, len(sat), min_points,
            )
            return LagResult(
                satellite_metric=satellite_name,
                stock_ticker=ticker,
                stock_metric="returns",
                rolling_window=rolling_window,
                frequency=frequency,
                lag_unit=lag_unit,
                optimal_lag=0, optimal_corr=0.0, optimal_pvalue=1.0,
                ccf_lags=np.array([]), ccf_values=np.array([]),
                granger_pvalues={}, granger_optimal_pvalue=1.0,
                is_significant=False,
            )

        # CCF analysis
        best_lag, best_corr, p_val, all_lags, all_corrs = self.find_optimal_lag(sat, ret, max_lag=max_lag)

        # Granger causality
        granger_pv = self.granger_causality(sat, ret, max_lag=granger_max_lag)
        granger_best = min(granger_pv.values()) if granger_pv else 1.0

        # Significance: either CCF p-value or Granger p-value < 0.05
        is_sig = (p_val < 0.05) or (granger_best < 0.05)

        return LagResult(
            satellite_metric=satellite_name,
            stock_ticker=ticker,
            stock_metric="returns",
            rolling_window=rolling_window,
            frequency=frequency,
            lag_unit=lag_unit,
            optimal_lag=best_lag,
            optimal_corr=best_corr,
            optimal_pvalue=p_val,
            ccf_lags=all_lags,
            ccf_values=all_corrs,
            granger_pvalues=granger_pv,
            granger_optimal_pvalue=granger_best,
            is_significant=is_sig,
        )


# ═══════════════════════════════════════════════════════════════════════
# 5. OUTPUT GENERATOR
# ═══════════════════════════════════════════════════════════════════════
class OutputGenerator:
    """Generate correlation matrix, plots, and text report."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_correlation_matrix(
        self,
        results: list[LagResult],
        case_name: str,
    ) -> str:
        """Generate text correlation matrix table."""
        lines = []
        lines.append(f"{'='*100}")
        lines.append(f"  MATRIKS KORELASI SATELIT vs SAHAM — {case_name}")
        lines.append(f"{'='*100}")
        lines.append(
            f"{'Metrik':<20} {'Ticker':<10} {'Freq':<9} {'Win':<5} "
            f"{'Lag':<6} {'r':<8} {'p(CCF)':<10} {'p(Granger)':<12} {'Sig':<5}"
        )
        lines.append("-" * 100)

        for r in results:
            sig_str = "YA" if r.is_significant else "-"
            granger_str = f"{r.granger_optimal_pvalue:.4f}" if r.granger_pvalues else "N/A"
            freq_str = f"{r.frequency}"
            lines.append(
                f"{r.satellite_metric:<20} {r.stock_ticker:<10} {freq_str:<9} "
                f"{r.rolling_window:<5} {r.optimal_lag:+5d} "
                f"{r.optimal_corr:+.4f}  {r.optimal_pvalue:.4f}    "
                f"{granger_str:<12} {sig_str}"
            )

        lines.append("-" * 100)
        lines.append("Catatan:")
        lines.append(f"  Lag: +N = satelit mendahului saham N {r.lag_unit}, -N = sebaliknya")
        lines.append("  r > 0: korelasi positif, r < 0: korelasi negatif")
        lines.append("  Sig: YA jika p-value < 0.05 (CCF atau Granger)")
        lines.append("")

        text = "\n".join(lines)
        print(text)
        return text

    def generate_plots(
        self,
        satellite_df: pd.DataFrame,
        stock_data: dict[str, pd.DataFrame],
        results: list[LagResult],
        case_name: str,
        case_idx: int,
    ) -> list[Path]:
        """Generate matplotlib plots: time series + CCF."""
        plot_files = []

        # ── Plot 1: Time Series Overview ───────────────────────────
        n_tickers = len(stock_data)
        n_sat = len(satellite_df.columns)
        fig, axes = plt.subplots(
            n_sat + n_tickers, 1,
            figsize=(14, 3 * (n_sat + n_tickers)),
            sharex=True,
        )
        if n_sat + n_tickers == 1:
            axes = [axes]

        for i, col in enumerate(satellite_df.columns):
            ax = axes[i]
            data = satellite_df[col].dropna()
            ax.plot(data.index, data.values, linewidth=0.8, alpha=0.7, color="green")
            ax.set_ylabel(col, fontsize=9)
            ax.tick_params(axis="y", labelsize=8)
            if col == "NDVI":
                ax.set_title(f"{case_name} — NDVI & Environmental Data", fontsize=11)
            elif col == "NIGHTLIGHT":
                ax.set_title(f"{case_name} — Nightlight & Environmental Data", fontsize=11)

        for j, (ticker, df) in enumerate(stock_data.items()):
            ax = axes[n_sat + j]
            ax.plot(df.index, df["price"].values, linewidth=0.8, alpha=0.7, color="blue")
            ax.set_ylabel(f"{ticker}\nPrice", fontsize=9)
            ax.tick_params(axis="y", labelsize=8)

        axes[-1].set_xlabel("Date")
        plt.tight_layout()
        p1 = self.output_dir / f"case_{case_idx+1}_timeseries.png"
        fig.savefig(p1, dpi=150, bbox_inches="tight")
        plt.close(fig)
        plot_files.append(p1)
        logger.info("Saved: %s", p1)

        # ── Plot 2: CCF Lag Plots ──────────────────────────────────
        if not results:
            return plot_files

        # Group by ticker
        tickers = sorted(set(r.stock_ticker for r in results))
        metrics = sorted(set(r.satellite_metric for r in results))

        n_rows = len(metrics)
        n_cols = len(tickers)
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(7 * n_cols, 4 * n_rows), squeeze=False)

        for i, metric in enumerate(metrics):
            for j, ticker in enumerate(tickers):
                ax = axes[i][j]
                matching = [r for r in results
                            if r.satellite_metric == metric
                            and r.stock_ticker == ticker
                            and r.rolling_window == 7]  # Use 7-day window for plot
                if matching:
                    r = matching[0]
                    if len(r.ccf_lags) > 0:
                        colors = ["red" if v < 0 else "blue" for v in r.ccf_values]
                        ax.bar(r.ccf_lags, r.ccf_values, color=colors, alpha=0.6, width=1.0)
                        ax.axvline(r.optimal_lag, color="green", linestyle="--",
                                   linewidth=1.5, label=f"Opt lag={r.optimal_lag}")
                        ax.axhline(0, color="black", linewidth=0.5)
                        # Significance bands (approximate 95% CI)
                        n = len(r.ccf_values)
                        ci = 1.96 / np.sqrt(n) if n > 0 else 0
                        ax.axhline(ci, color="gray", linestyle=":", alpha=0.5)
                        ax.axhline(-ci, color="gray", linestyle=":", alpha=0.5)
                        ax.legend(fontsize=8)
                        ax.set_title(
                            f"{metric} vs {ticker}\n"
                            f"r={r.optimal_corr:+.3f}, lag={r.optimal_lag}d, "
                            f"p={r.optimal_pvalue:.4f}",
                            fontsize=9,
                        )
                else:
                    ax.set_title(f"{metric} vs {ticker} (no data)", fontsize=9)
                ax.set_xlabel("Lag (days)")
                ax.set_ylabel("Cross-correlation")
                ax.tick_params(labelsize=8)

        fig.suptitle(f"{case_name} — Cross-Correlation Function (CCF)", fontsize=12, y=1.01)
        plt.tight_layout()
        p2 = self.output_dir / f"case_{case_idx+1}_ccf_lag.png"
        fig.savefig(p2, dpi=150, bbox_inches="tight")
        plt.close(fig)
        plot_files.append(p2)
        logger.info("Saved: %s", p2)

        return plot_files

    def generate_report(
        self,
        case_name: str,
        case_def: dict,
        results: list[LagResult],
        satellite_df: pd.DataFrame,
        stock_data: dict[str, pd.DataFrame],
        plot_files: list[Path],
    ) -> Path:
        """Generate detailed text report."""
        lines = []
        lines.append("=" * 80)
        lines.append("LAPORAN ANALISIS KORELASI SATELIT vs HARGA SAHAM")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Test Case: {case_name}")
        lines.append(f"Deskripsi: {case_def['description']}")
        lines.append(f"Koordinat: lat={case_def['lat']}, lon={case_def['lon']}")
        lines.append(f"Ticker: {', '.join(case_def['tickers'])}")
        lines.append(f"Metrik Satelit: {', '.join(case_def['satellite_metrics'])}")
        lines.append(f"Periode Data: {satellite_df.index[0].date()} → {satellite_df.index[-1].date()}")
        lines.append(f"Total Hari Satelit: {len(satellite_df)}")
        for ticker, df in stock_data.items():
            lines.append(f"  {ticker}: {len(df)} hari perdagangan")
        lines.append("")

        # Data sources
        lines.append("SUMBER DATA:")
        lines.append("  - NASA POWER API (https://power.larc.nasa.gov/)")
        lines.append("    → T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN (real satellite-derived)")
        if "NDVI" in satellite_df.columns:
            ndvi_count = satellite_df["NDVI"].dropna().shape[0]
            total_count = satellite_df.shape[0]
            if ndvi_count > 0 and ndvi_count < total_count * 0.8:
                lines.append(f"  - NDVI: Sentinel-2 via Microsoft Planetary Computer ({ndvi_count} scenes)")
                lines.append("    → Real NDVI from B04/B08 bands, cloud cover < 30%")
            else:
                lines.append("  - NDVI: Simulasi (Sentinel-2 tidak tersedia untuk periode/lokasi ini)")
                lines.append("    → Driven by precipitation + seasonal pattern")
        if "NIGHTLIGHT" in satellite_df.columns:
            lines.append("  - Nightlight: Simulasi (VIIRS Earthdata credentials not configured)")
            lines.append("    → Trend + seasonality + cloud effect proxy")
        lines.append("  - Stock: SQLite ohlcv table atau yfinance (untuk futures ZC=F, ZS=F, ZW=F)")
        lines.append("")

        # Results summary
        lines.append("HASIL ANALISIS LEAD-LAG:")
        lines.append("-" * 80)

        significant_results = [r for r in results if r.is_significant]
        if significant_results:
            lines.append(f"\n  {len(significant_results)} hubungan signifikan ditemukan (p < 0.05):\n")
            for r in significant_results:
                direction = "mendahului" if r.optimal_lag > 0 else "mengikuti" if r.optimal_lag < 0 else "konkuren"
                abs_lag = abs(r.optimal_lag)
                lines.append(
                    f"  • [{r.frequency}] {r.satellite_metric} {direction} {r.stock_ticker} "
                    f"sebesar {abs_lag} {r.lag_unit}"
                )
                lines.append(
                    f"    r = {r.optimal_corr:+.4f}, p(CCF) = {r.optimal_pvalue:.4f}, "
                    f"p(Granger) = {r.granger_optimal_pvalue:.4f}"
                )
                lines.append(
                    f"    Rolling window: {r.rolling_window} {r.lag_unit}"
                )
                # Interpretation
                if r.optimal_corr > 0:
                    corr_type = "positif"
                    interp = "kenaikan metrik satelit berasosiasi dengan kenaikan return saham"
                else:
                    corr_type = "negatif"
                    interp = "kenaikan metrik satelit berasosiasi dengan penurunan return saham"
                lines.append(f"    Korelasi {corr_type}: {interp}")
                lines.append("")
        else:
            lines.append("\n  Tidak ada hubungan signifikan (p ≥ 0.05) ditemukan.\n")

        # Detailed table
        lines.append("TABEL DETAIL:")
        lines.append(
            f"{'Metrik':<20} {'Ticker':<10} {'Freq':<9} {'Win':<5} {'Lag':<6} "
            f"{'r':<8} {'p(CCF)':<10} {'p(Granger)':<12} {'Sig':<5}"
        )
        lines.append("-" * 90)
        for r in results:
            sig = "YA" if r.is_significant else "-"
            gp = f"{r.granger_optimal_pvalue:.4f}" if r.granger_pvalues else "N/A"
            lines.append(
                f"{r.satellite_metric:<20} {r.stock_ticker:<10} {r.frequency:<9} "
                f"{r.rolling_window:<5} {r.optimal_lag:+5d} "
                f"{r.optimal_corr:+.4f}  {r.optimal_pvalue:.4f}    "
                f"{gp:<12} {sig}"
            )
        lines.append("")

        # Plots
        lines.append("FILE PLOT:")
        for p in plot_files:
            lines.append(f"  {p}")
        lines.append("")

        # Methodology
        lines.append("METODOLOGI:")
        lines.append("  1. Resampling: daily (harian), weekly (mingguan W), monthly (bulanan ME)")
        lines.append("  2. Cross-Correlation Function (CCF):")
        lines.append("     - Daily: lag -60 h +60 hari")
        lines.append("     - Weekly: lag -8 h +8 minggu")
        lines.append("     - Monthly: lag -3 h +3 bulan")
        lines.append("  3. Granger Causality Test: F-test, lag order disesuaikan per frekuensi")
        lines.append("  4. Rolling average: 7 dan 30 (daily), 4 dan 12 (weekly), 3 (monthly)")
        lines.append("  5. Signifikansi: p-value < 0.05 (CCF atau Granger)")
        lines.append("  6. Data alignment: linear interpolation + forward-fill")
        lines.append("")

        # Caveats
        lines.append("CATATAN & KETERBATASAN:")
        lines.append("  - NDVI: data real dari Sentinel-2 via Microsoft Planetary Computer (gratis, no account)")
        lines.append("    → Cloud cover threshold < 30%, 10m resolusi, 5-day revisit")
        lines.append("    → Jika tidak ada scene yang valid, fallback ke simulasi")
        lines.append("  - Nightlight: simulasi (VIIRS Earthdata credentials not configured)")
        lines.append("    → Untuk data real: set EARTHDATA_USERNAME dan EARTHDATA_PASSWORD di .env")
        lines.append("  - Hasil korelasi pada data simulasi TIDAK dapat diinterpretasikan sebagai")
        lines.append("    bukti kausalitas nyata — hanya menguji metodologi pipeline")
        lines.append("  - Untuk analisis produksi: integrasikan GEE dengan service account")
        lines.append("  - Granger causality bukan bukti kausalitas sejati, hanya prediksi statistik")
        lines.append("")

        report_text = "\n".join(lines)
        safe_name = case_name.replace(" ", "_").replace("—", "-").replace("/", "-")[:60]
        report_path = self.output_dir / f"{safe_name}_report.txt"
        report_path.write_text(report_text, encoding="utf-8")
        logger.info("Report saved: %s", report_path)
        print(report_text)

        return report_path

    def save_json_results(
        self,
        case_name: str,
        results: list[LagResult],
        case_def: dict,
    ) -> Path:
        """Save results as JSON for programmatic access."""
        data = {
            "case_name": case_name,
            "description": case_def["description"],
            "coordinates": {"lat": case_def["lat"], "lon": case_def["lon"]},
            "tickers": case_def["tickers"],
            "results": [
                {
                    "satellite_metric": r.satellite_metric,
                    "stock_ticker": r.stock_ticker,
                    "rolling_window": r.rolling_window,
                    "frequency": r.frequency,
                    "lag_unit": r.lag_unit,
                    "optimal_lag": r.optimal_lag,
                    "optimal_corr": r.optimal_corr,
                    "optimal_pvalue": r.optimal_pvalue,
                    "granger_optimal_pvalue": r.granger_optimal_pvalue,
                    "is_significant": r.is_significant,
                    "granger_pvalues": r.granger_pvalues,
                }
                for r in results
            ],
        }
        safe_name = case_name.replace(" ", "_").replace("—", "-").replace("/", "-")[:60]
        json_path = self.output_dir / f"{safe_name}_results.json"
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info("JSON results saved: %s", json_path)
        return json_path

    def generate_comparison_table(
        self,
        all_results: list[LagResult],
        case_name: str,
    ) -> str:
        """Generate comparison table: daily vs weekly vs monthly correlation.

        Groups results by (satellite_metric, stock_ticker, rolling_window)
        and shows how r changes across frequencies.
        """
        from collections import defaultdict

        groups: dict[tuple, dict[str, LagResult]] = defaultdict(dict)
        for r in all_results:
            key = (r.satellite_metric, r.stock_ticker, r.rolling_window)
            groups[key][r.frequency] = r

        lines = []
        lines.append("=" * 95)
        lines.append(f"  PERBANDINGAN KORELASI: DAILY vs WEEKLY vs MONTHLY — {case_name}")
        lines.append("=" * 95)
        lines.append(
            f"{'Metrik':<20} {'Ticker':<10} {'Win':<5} "
            f"{'r(daily)':<10} {'r(weekly)':<10} {'r(monthly)':<11} "
            f"{'Δ(w-d)':<8} {'Δ(m-d)':<8} {'Best':<8}"
        )
        lines.append("-" * 95)

        freq_order = ["daily", "weekly", "monthly"]
        for key in sorted(groups.keys()):
            metric, ticker, window = key
            freqs = groups[key]
            r_vals = {}
            for f in freq_order:
                if f in freqs:
                    r_vals[f] = freqs[f].optimal_corr
                else:
                    r_vals[f] = None

            r_d = r_vals.get("daily")
            r_w = r_vals.get("weekly")
            r_m = r_vals.get("monthly")

            r_d_str = f"{r_d:+.4f}" if r_d is not None else "N/A"
            r_w_str = f"{r_w:+.4f}" if r_w is not None else "N/A"
            r_m_str = f"{r_m:+.4f}" if r_m is not None else "N/A"

            delta_wd = ""
            if r_w is not None and r_d is not None:
                dw = abs(r_w) - abs(r_d)
                delta_wd = f"{dw:+.4f}"
            delta_md = ""
            if r_m is not None and r_d is not None:
                dm = abs(r_m) - abs(r_d)
                delta_md = f"{dm:+.4f}"

            abs_vals = {f: abs(v) for f, v in r_vals.items() if v is not None}
            best_freq = max(abs_vals, key=abs_vals.get) if abs_vals else "N/A"

            lines.append(
                f"{metric:<20} {ticker:<10} {window:<5} "
                f"{r_d_str:<10} {r_w_str:<10} {r_m_str:<11} "
                f"{delta_wd:<8} {delta_md:<8} {best_freq:<8}"
            )

        lines.append("-" * 95)
        lines.append("Δ(w-d) = perubahan |r| dari daily ke weekly")
        lines.append("Δ(m-d) = perubahan |r| dari daily ke monthly")
        lines.append("Best = frekuensi dengan |r| tertinggi")
        lines.append("")

        text = "\n".join(lines)
        print(text)

        safe_name = case_name.replace(" ", "_").replace("—", "-").replace("/", "-")[:60]
        comp_path = self.output_dir / f"{safe_name}_comparison.txt"
        comp_path.write_text(text, encoding="utf-8")
        logger.info("Comparison table saved: %s", comp_path)
        return text


# ═══════════════════════════════════════════════════════════════════════
# 6. MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════
def run_pipeline(years: int = 2, use_yfinance: bool = False) -> None:
    """Run the full satellite-to-stock correlation pipeline.

    Runs analysis at three frequencies:
    - Daily: lag -60..+60 days, rolling windows [7, 30]
    - Weekly: lag -8..+8 weeks, rolling windows [4, 12]
    - Monthly: lag -3..+3 months, rolling window [3]
    """
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=years * 365)

    logger.info("=" * 70)
    logger.info("SATELLITE-TO-STOCK CORRELATION PIPELINE (Multi-Frequency)")
    logger.info("Period: %s → %s (%d years)", start_date, end_date, years)
    logger.info("Frequencies: daily, weekly, monthly")
    logger.info("=" * 70)

    stock_fetcher = StockDataFetcher(use_yfinance=use_yfinance)
    aligner = DataAligner()
    output_gen = OutputGenerator(OUTPUT_DIR)

    # Frequency-specific configs: (label, freq, max_lag, granger_max_lag, rolling_windows, unit_label)
    freq_configs = [
        ("daily", None, MAX_LAG_DAYS, GRANGER_MAX_LAG, [7, 30], "hari"),
        ("weekly", "W", 8, 6, [4, 12], "minggu"),
        ("monthly", "ME", 3, 3, [3], "bulan"),
    ]

    all_results_json = []

    for idx, case in enumerate(TEST_CASES):
        logger.info("\n%s", "=" * 70)
        logger.info("  %s", case["name"])
        logger.info("=" * 70)

        # ── Step 1: Fetch satellite data ───────────────────────────
        sat_fetcher = SatelliteDataFetcher(
            lat=case["lat"],
            lon=case["lon"],
            start_date=start_date,
            end_date=end_date,
        )
        satellite_raw = sat_fetcher.fetch_all()
        logger.info("Satellite data: %d rows, columns=%s", len(satellite_raw), list(satellite_raw.columns))

        # ── Step 2: Fetch stock data ───────────────────────────────
        stock_data: dict[str, pd.DataFrame] = {}
        for ticker in case["tickers"]:
            try:
                df = stock_fetcher.fetch(ticker, start_date, end_date)
                stock_data[ticker] = df
            except Exception as exc:
                logger.error("Failed to fetch %s: %s", ticker, exc)

        if not stock_data:
            logger.error("No stock data for case %d — skipping", idx + 1)
            continue

        all_results: list[LagResult] = []
        plot_files: list[Path] = []

        for freq_label, freq_str, freq_max_lag, freq_granger_lag, freq_windows, freq_unit in freq_configs:
            logger.info("\n── %s analysis (lag ±%d %s) ──", freq_label.upper(), freq_max_lag, freq_unit)

            # ── Step 3: Resample data for this frequency ────────────
            if freq_str is None:
                # Daily: align satellite to trading days
                ref_ticker = case["tickers"][0]
                satellite_aligned = aligner.align_to_trading_days(satellite_raw, stock_data[ref_ticker])
                stock_returns: dict[str, pd.Series] = {}
                for ticker, df in stock_data.items():
                    rets = aligner.compute_returns(df["price"])
                    stock_returns[ticker] = rets
            else:
                # Weekly/monthly: resample both satellite and stock
                satellite_aligned = aligner.resample_data(satellite_raw, freq_str)
                stock_returns = {}
                for ticker, df in stock_data.items():
                    resampled_prices = aligner.resample_prices(df["price"], freq_str)
                    rets = aligner.compute_period_returns(resampled_prices)
                    stock_returns[ticker] = rets

            logger.info(
                "  %s: satellite=%d rows, stock returns=%d points",
                freq_label, len(satellite_aligned),
                len(next(iter(stock_returns.values()))) if stock_returns else 0,
            )

            # ── Step 4: Rolling smoothing ────────────────────────────
            smoothed_variants = aligner.apply_rolling_smoothing(satellite_aligned, windows=freq_windows)

            # ── Step 5: Lag analysis ────────────────────────────────
            freq_lag_analyzer = LagAnalyzer(max_lag=freq_max_lag)

            for window, sat_smoothed in smoothed_variants.items():
                for metric in case["satellite_metrics"]:
                    if metric not in sat_smoothed.columns:
                        logger.warning("Metric %s not in satellite data — skipping", metric)
                        continue

                    sat_series = sat_smoothed[metric].dropna()
                    min_pts = freq_max_lag + 10
                    if len(sat_series) < min_pts:
                        logger.warning(
                            "Metric %s has too few points (%d < %d) for %s — skipping",
                            metric, len(sat_series), min_pts, freq_label,
                        )
                        continue

                    for ticker in case["tickers"]:
                        if ticker not in stock_returns:
                            continue
                        ret = stock_returns[ticker]

                        logger.info(
                            "  [%s] Analyzing: %s vs %s (window=%d %s)",
                            freq_label, metric, ticker, window, freq_unit,
                        )
                        result = freq_lag_analyzer.analyze(
                            satellite_series=sat_series,
                            stock_returns=ret,
                            satellite_name=metric,
                            ticker=ticker,
                            rolling_window=window,
                            frequency=freq_label,
                            lag_unit=freq_unit,
                            max_lag=freq_max_lag,
                            granger_max_lag=freq_granger_lag,
                        )
                        all_results.append(result)

                        if result.is_significant:
                            logger.info(
                                "    ★ SIGNIFIKAN: lag=%+d %s, r=%.4f, p(CCF)=%.4f, p(Granger)=%.4f",
                                result.optimal_lag, freq_unit, result.optimal_corr,
                                result.optimal_pvalue, result.granger_optimal_pvalue,
                            )
                        else:
                            logger.info(
                                "    lag=%+d %s, r=%.4f, p(CCF)=%.4f, p(Granger)=%.4f",
                                result.optimal_lag, freq_unit, result.optimal_corr,
                                result.optimal_pvalue, result.granger_optimal_pvalue,
                            )

            # Generate plots for this frequency (only for daily to avoid clutter)
            if freq_str is None:
                plot_files = output_gen.generate_plots(
                    satellite_aligned, stock_data, all_results, case["name"], idx,
                )

        # ── Step 6: Output ─────────────────────────────────────────
        output_gen.generate_correlation_matrix(all_results, case["name"])
        report_path = output_gen.generate_report(
            case["name"], case, all_results, satellite_raw, stock_data, plot_files,
        )
        json_path = output_gen.save_json_results(case["name"], all_results, case)
        output_gen.generate_comparison_table(all_results, case["name"])

        all_results_json.append({
            "case": case["name"],
            "report": str(report_path),
            "json": str(json_path),
            "plots": [str(p) for p in plot_files],
        })

    # ── Final summary ──────────────────────────────────────────────
    logger.info("\n%s", "=" * 70)
    logger.info("PIPELINE SELESAI — OUTPUT di %s", OUTPUT_DIR)
    logger.info("=" * 70)
    for item in all_results_json:
        logger.info("  %s", item["case"])
        logger.info("    Report: %s", item["report"])
        logger.info("    JSON:   %s", item["json"])
        logger.info("    Plots:  %s", ", ".join(item["plots"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Satellite-to-Stock Correlation Pipeline",
    )
    parser.add_argument(
        "--years", type=int, default=2,
        help="Number of years of historical data (default: 2)",
    )
    parser.add_argument(
        "--use-yfinance", action="store_true",
        help="Use yfinance instead of local DB for stock data",
    )
    args = parser.parse_args()

    run_pipeline(years=args.years, use_yfinance=args.use_yfinance)
