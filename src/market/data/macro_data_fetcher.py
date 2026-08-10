"""Macro data fetcher with dynamic rate-limiting.

Pulls macroeconomic and commodity data from multiple FREE sources:
- BPS (Badan Pusat Statistik) — GDP, CPI, trade balance, industrial production
- World Bank Open Data API — GDP, trade, inflation
- NOAA Climate — El Nino/La Nina ONI index
- yfinance — commodity futures (CPO proxy, coal, nickel, copper, gold, oil)

All HTTP sources share a :class:`DynamicRateLimiter` that adapts request
intervals per-domain based on observed response times, 429 errors, and
success rates.

References:
    pustaka/22-data-engineering-pipeline.md §12-13 (adaptive rate limiter,
    macro data adapters)
    pustaka/89-faktor-pasar-modal-analisis-implementasi.md (macro factors,
    CPI/GDP/trade/commodity relevance for IDX)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import pandas as pd
import requests

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 30  # seconds
_DEFAULT_RETRIES = 3
_DEFAULT_INTERVAL = 0.5  # seconds
_MIN_INTERVAL = 0.1
_MAX_INTERVAL = 60.0
_BACKOFF_FACTOR = 2.0
_SPEEDUP_FACTOR = 0.9

_BPS_BASE = "https://webapi.bps.go.id/v1"
_WORLD_BANK_BASE = "https://api.worldbank.org/v2"
_NOAA_ONI_URL = "https://psl.noaa.gov/data/correlation/oni.data"

# Commodity futures tickers (yfinance). CPO has no direct US-listed futures
# contract on Yahoo, so we use Bursa Malaysia FCPOc1 proxy via ^KLSE palm
# exposure as a fallback. Newcastle coal is not on Yahoo; we keep the ticker
# slot but it may return empty — logged as a warning.
COMMODITY_TICKERS: dict[str, str] = {
    "cpo_proxy": "^KLSE",  # palm proxy (no direct FCPO on Yahoo)
    "newcastle_coal": "COAL=F",  # best-effort coal proxy
    "nickel": "NI=F",
    "copper": "HG=F",
    "tin": "TIN=F",  # may be unavailable; handled gracefully
    "gold": "GC=F",
    "oil": "CL=F",
}


# ---------------------------------------------------------------------------
# Dynamic Rate Limiter
# ---------------------------------------------------------------------------


class DynamicRateLimiter:
    """Adaptive per-domain rate limiter.

    Tracks response times, 429 errors, and adjusts the request interval
    per-domain. On a 429 or error, interval is multiplied by
    :data:`_BACKOFF_FACTOR` (max :data:`_MAX_INTERVAL`). On success,
    interval is multiplied by :data:`_SPEEDUP_FACTOR` (min
    :data:`_MIN_INTERVAL`).

    Args:
        default_interval: Initial interval between requests (seconds).
        min_interval: Minimum allowed interval.
        max_interval: Maximum allowed interval (backoff cap).
        backoff_factor: Multiplier applied on 429/error.
        speedup_factor: Multiplier applied on success.
        sleep_func: Injectable sleep function (for testing).
        monotonic_func: Injectable monotonic clock (for testing).
    """

    def __init__(
        self,
        default_interval: float = _DEFAULT_INTERVAL,
        min_interval: float = _MIN_INTERVAL,
        max_interval: float = _MAX_INTERVAL,
        backoff_factor: float = _BACKOFF_FACTOR,
        speedup_factor: float = _SPEEDUP_FACTOR,
        sleep_func: Callable[[float], None] | None = None,
        monotonic_func: Callable[[], float] | None = None,
    ) -> None:
        self._default = default_interval
        self._min = min_interval
        self._max = max_interval
        self._backoff = backoff_factor
        self._speedup = speedup_factor
        self._sleep = sleep_func or time.sleep
        self._clock = monotonic_func or time.monotonic
        self._lock = threading.Lock()
        self._intervals: dict[str, float] = {}
        self._last_request: dict[str, float] = {}
        self._consecutive_errors: dict[str, int] = {}

    def _interval_for(self, domain: str) -> float:
        return self._intervals.get(domain, self._default)

    def wait(self, domain: str) -> float:
        """Block until the rate limit allows the next request for *domain*.

        Returns the actual wait time in seconds.
        """
        with self._lock:
            interval = self._interval_for(domain)
            last = self._last_request.get(domain)
            now = self._clock()
            wait_time = 0.0
            if last is not None:
                elapsed = now - last
                if elapsed < interval:
                    wait_time = interval - elapsed
            # record the projected request time
            self._last_request[domain] = now + wait_time
        if wait_time > 0:
            self._sleep(wait_time)
        return wait_time

    def record_success(self, domain: str, response_time: float = 0.0) -> None:
        """Record a successful request; gradually speed up the interval."""
        with self._lock:
            self._consecutive_errors[domain] = 0
            current = self._interval_for(domain)
            new_interval = max(self._min, current * self._speedup)
            self._intervals[domain] = new_interval
        logger.debug(
            "RateLimiter success domain=%s response_time=%.3fs interval %.3f→%.3f",
            domain, response_time, current, new_interval,
        )

    def record_error(self, domain: str, status_code: int | None = None) -> None:
        """Record a failed request; apply exponential backoff.

        A 429 status triggers a stronger backoff (interval *= backoff_factor).
        Other errors also back off but are tracked separately.
        """
        with self._lock:
            errors = self._consecutive_errors.get(domain, 0) + 1
            self._consecutive_errors[domain] = errors
            current = self._interval_for(domain)
            new_interval = min(self._max, current * self._backoff)
            self._intervals[domain] = new_interval
        logger.warning(
            "RateLimiter error domain=%s status=%s errors=%d interval %.3f→%.3f",
            domain, status_code, errors, current, new_interval,
        )

    def get_interval(self, domain: str) -> float:
        """Return the current interval for a domain (for inspection/testing)."""
        with self._lock:
            return self._interval_for(domain)

    def get_consecutive_errors(self, domain: str) -> int:
        """Return consecutive error count for a domain."""
        with self._lock:
            return self._consecutive_errors.get(domain, 0)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Result of a single source fetch operation."""

    source: str
    success: bool
    data: pd.DataFrame
    row_count: int = 0
    error: str | None = None
    elapsed_seconds: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _domain_from_url(url: str) -> str:
    """Extract a short domain key from a URL for rate-limit tracking."""
    try:
        from urllib.parse import urlparse

        host = urlparse(url).hostname or "unknown"
        # use the last two labels as the domain key (e.g. bps.go.id)
        parts = host.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return host
    except Exception:
        return "unknown"


def _http_get(
    url: str,
    limiter: DynamicRateLimiter,
    params: dict[str, str] | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    retries: int = _DEFAULT_RETRIES,
) -> requests.Response | None:
    """Perform an HTTP GET with rate-limiting and retries.

    Returns the Response on success (2xx), or None on failure after retries.
    """
    domain = _domain_from_url(url)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        limiter.wait(domain)
        try:
            resp = requests.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            limiter.record_error(domain, status_code=None)
            logger.warning(
                "HTTP GET %s attempt %d/%d failed: %s", url, attempt, retries, exc,
            )
            continue

        if resp.status_code == 429:
            limiter.record_error(domain, status_code=429)
            logger.warning(
                "HTTP 429 for %s attempt %d/%d — backing off", url, attempt, retries,
            )
            continue
        if resp.status_code >= 400:
            limiter.record_error(domain, status_code=resp.status_code)
            logger.warning(
                "HTTP %d for %s attempt %d/%d", resp.status_code, url, attempt, retries,
            )
            continue

        limiter.record_success(domain, response_time=resp.elapsed.total_seconds())
        return resp

    if last_exc is not None:
        logger.error("HTTP GET %s exhausted retries: %s", url, last_exc)
    return None


# ---------------------------------------------------------------------------
# BPS Fetcher
# ---------------------------------------------------------------------------


class BPSFetcher:
    """Fetch macro data from BPS (Badan Pusat Statistik) API.

    Requires the ``BPS_API_KEY`` environment variable. If missing, all
    fetch methods log a warning and return an empty DataFrame.

    Args:
        limiter: Shared dynamic rate limiter.
        api_key: BPS API key token. If None, reads from ``BPS_API_KEY`` env var.
        base_url: BPS API base URL.
    """

    def __init__(
        self,
        limiter: DynamicRateLimiter,
        api_key: str | None = None,
        base_url: str = _BPS_BASE,
    ) -> None:
        self._limiter = limiter
        self._api_key = api_key or os.environ.get("BPS_API_KEY")
        self._base_url = base_url.rstrip("/")

    def _available(self) -> bool:
        if not self._api_key:
            logger.warning("BPS_API_KEY not set — skipping BPS fetches")
            return False
        return True

    def _fetch_indicator(self, var_id: str, indicator: str, unit: str) -> pd.DataFrame:
        """Fetch a single BPS indicator series and normalize to a DataFrame."""
        if not self._available():
            return _empty_macro_frame()

        url = f"{self._base_url}/domains/0000/indicators/{var_id}"
        params = {"key": self._api_key or "", "format": "json", "lang": "eng"}
        resp = _http_get(url, self._limiter, params=params)
        if resp is None:
            return _empty_macro_frame()
        try:
            payload = resp.json()
        except ValueError as exc:
            logger.warning("BPS %s: invalid JSON: %s", indicator, exc)
            return _empty_macro_frame()

        rows = _extract_bps_data(payload, indicator, unit)
        if not rows:
            logger.warning("BPS %s: no data rows in response", indicator)
            return _empty_macro_frame()
        return pd.DataFrame(rows, columns=["date", "indicator", "value", "unit", "source"])

    def fetch_gdp(self) -> pd.DataFrame:
        """Fetch Indonesian GDP growth from BPS."""
        return self._fetch_indicator(var_id="1700", indicator="gdp_growth", unit="%")

    def fetch_cpi(self) -> pd.DataFrame:
        """Fetch Indonesian CPI (inflation) from BPS."""
        return self._fetch_indicator(var_id="1320", indicator="cpi_yoy", unit="%")

    def fetch_trade_balance(self) -> pd.DataFrame:
        """Fetch Indonesian trade balance from BPS."""
        return self._fetch_indicator(
            var_id="1130", indicator="trade_balance", unit="million_usd",
        )

    def fetch_industrial_production(self) -> pd.DataFrame:
        """Fetch Indonesian industrial production index from BPS."""
        return self._fetch_indicator(
            var_id="1400", indicator="industrial_production", unit="index",
        )


def _extract_bps_data(
    payload: dict[str, object], indicator: str, unit: str,
) -> list[dict[str, object]]:
    """Extract normalized rows from a BPS JSON payload.

    BPS responses typically nest data under ``datacontent`` keyed by period
    strings (e.g. ``"2023"`` or ``"2023Q1"`` or ``"202301"``).
    """
    data = payload.get("datacontent") or payload.get("data")
    if not isinstance(data, dict):
        # Some responses use a list of records
        if isinstance(data, list):
            rows: list[dict[str, object]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                date_str = str(item.get("date") or item.get("period") or item.get("tahun", ""))
                value = item.get("value") or item.get("nilai")
                if date_str and value is not None:
                    rows.append(
                        {
                            "date": _normalize_bps_date(str(date_str)),
                            "indicator": indicator,
                            "value": _safe_float(value),
                            "unit": unit,
                            "source": "bps",
                        }
                    )
            return rows
        return []

    rows = []
    for period, value in data.items():
        if value is None:
            continue
        rows.append(
            {
                "date": _normalize_bps_date(str(period)),
                "indicator": indicator,
                "value": _safe_float(value),
                "unit": unit,
                "source": "bps",
            }
        )
    return rows


def _normalize_bps_date(period: str) -> str:
    """Normalize a BPS period string to a YYYY-MM-DD date string."""
    period = period.strip()
    # Annual: "2023"
    if len(period) == 4 and period.isdigit():
        return f"{period}-01-01"
    # Quarterly: "2023Q1"
    if "Q" in period:
        year, q = period.split("Q")
        month = {"1": "01", "2": "04", "3": "07", "4": "10"}.get(q, "01")
        return f"{year}-{month}-01"
    # Monthly: "202301" or "2023-01"
    if len(period) == 6 and period.isdigit():
        return f"{period[:4]}-{period[4:6]}-01"
    if len(period) >= 7 and period[4] == "-":
        return f"{period}-01"
    return period


def _safe_float(value: object) -> float | None:
    """Convert a value to float, returning None on failure."""
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result


def _empty_macro_frame() -> pd.DataFrame:
    """Return an empty DataFrame with the standard macro schema."""
    return pd.DataFrame(columns=["date", "indicator", "value", "unit", "source"])


# ---------------------------------------------------------------------------
# World Bank Fetcher
# ---------------------------------------------------------------------------


class WorldBankFetcher:
    """Fetch macro data from the World Bank Open Data API (no key required).

    Args:
        limiter: Shared dynamic rate limiter.
        base_url: World Bank API base URL.
    """

    def __init__(
        self,
        limiter: DynamicRateLimiter,
        base_url: str = _WORLD_BANK_BASE,
    ) -> None:
        self._limiter = limiter
        self._base_url = base_url.rstrip("/")

    def _fetch_indicator(
        self, indicator_code: str, indicator_name: str, country: str = "ID",
    ) -> pd.DataFrame:
        """Fetch a World Bank indicator and normalize to a DataFrame."""
        url = f"{self._base_url}/country/{country}/indicator/{indicator_code}"
        params = {"format": "json", "per_page": "1000", "date": "1990:2100"}
        resp = _http_get(url, self._limiter, params=params)
        if resp is None:
            return _empty_macro_frame()
        try:
            payload = resp.json()
        except ValueError as exc:
            logger.warning("World Bank %s: invalid JSON: %s", indicator_name, exc)
            return _empty_macro_frame()

        if not isinstance(payload, list) or len(payload) < 2:
            logger.warning("World Bank %s: unexpected payload shape", indicator_name)
            return _empty_macro_frame()

        records = payload[1]
        if not isinstance(records, list):
            return _empty_macro_frame()

        rows = []
        for rec in records:
            value = rec.get("value")
            if value is None:
                continue
            date_str = str(rec.get("date", ""))
            rows.append(
                {
                    "date": _normalize_wb_date(date_str),
                    "indicator": indicator_name,
                    "value": _safe_float(value),
                    "unit": rec.get("unit") or "",
                    "source": "world_bank",
                }
            )
        if not rows:
            return _empty_macro_frame()
        return pd.DataFrame(rows, columns=["date", "indicator", "value", "unit", "source"])

    def fetch_gdp(self, country: str = "ID") -> pd.DataFrame:
        """Fetch GDP (current US$) for a country."""
        return self._fetch_indicator("NY.GDP.MKTP.CD", "gdp_usd", country=country)

    def fetch_trade(self, country: str = "ID") -> pd.DataFrame:
        """Fetch trade (% of GDP) for a country."""
        return self._fetch_indicator("NE.TRD.GNFS.ZS", "trade_pct_gdp", country=country)

    def fetch_inflation(self, country: str = "ID") -> pd.DataFrame:
        """Fetch inflation (CPI %) for a country."""
        return self._fetch_indicator("FP.CPI.TOTL.ZG", "inflation_cpi", country=country)


def _normalize_wb_date(date_str: str) -> str:
    """Normalize a World Bank date string to YYYY-MM-DD."""
    date_str = date_str.strip()
    if len(date_str) == 4 and date_str.isdigit():
        return f"{date_str}-01-01"
    return date_str


# ---------------------------------------------------------------------------
# NOAA Climate Fetcher
# ---------------------------------------------------------------------------


class NOAAFetcher:
    """Fetch El Nino/La Nina ONI index from NOAA PSL.

    The ONI data file is a fixed-width text format with 3-month seasons
    arranged in rows by year and columns by season.

    Args:
        limiter: Shared dynamic rate limiter.
        url: NOAA ONI data URL.
    """

    # Column order in the ONI text file (3-month seasons)
    _SEASONS: ClassVar[list[str]] = [
        "DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ",
        "JJA", "JAS", "ASO", "SON", "OND", "NDJ",
    ]

    def __init__(
        self,
        limiter: DynamicRateLimiter,
        url: str = _NOAA_ONI_URL,
    ) -> None:
        self._limiter = limiter
        self._url = url

    def fetch_oni(self) -> pd.DataFrame:
        """Fetch and parse the ONI index into a DataFrame.

        Returns:
            DataFrame with columns: date, oni_value, enso_phase.
        """
        resp = _http_get(limiter=self._limiter, url=self._url)
        if resp is None:
            return pd.DataFrame(columns=["date", "oni_value", "enso_phase"])
        return self._parse_oni_text(resp.text)

    def _parse_oni_text(self, text: str) -> pd.DataFrame:
        """Parse the raw ONI text file into a DataFrame."""
        rows: list[dict[str, object]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            # Each data line: year + 12 season values
            if len(parts) != 13:
                continue
            if not parts[0].isdigit():
                continue
            year = int(parts[0])
            for i, season in enumerate(self._SEASONS):
                raw = parts[i + 1]
                if raw == "-99.99" or raw == "-99.9":
                    continue
                val = _safe_float(raw)
                if val is None:
                    continue
                month = _season_to_month(season)
                date_str = f"{year}-{month:02d}-01"
                rows.append(
                    {
                        "date": date_str,
                        "oni_value": val,
                        "enso_phase": _enso_phase(val),
                    }
                )
        if not rows:
            return pd.DataFrame(columns=["date", "oni_value", "enso_phase"])
        return pd.DataFrame(rows, columns=["date", "oni_value", "enso_phase"])


def _season_to_month(season: str) -> int:
    """Map a 3-month season label to its middle month (1-12)."""
    # Use the middle month of the season
    mapping = {
        "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
        "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
    }
    return mapping.get(season, 1)


def _enso_phase(oni: float) -> str:
    """Classify an ONI value into an ENSO phase."""
    if oni >= 0.5:
        return "el_nino"
    if oni <= -0.5:
        return "la_nina"
    return "neutral"


# ---------------------------------------------------------------------------
# Commodity Fetcher (yfinance)
# ---------------------------------------------------------------------------


class CommodityFetcher:
    """Fetch commodity futures prices via yfinance.

    Args:
        limiter: Shared dynamic rate limiter (used for the yfinance domain).
        tickers: Mapping of commodity name to yfinance ticker.
    """

    def __init__(
        self,
        limiter: DynamicRateLimiter,
        tickers: dict[str, str] | None = None,
    ) -> None:
        self._limiter = limiter
        self._tickers = tickers or dict(COMMODITY_TICKERS)

    def fetch_commodity(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        """Fetch a single commodity futures series via yfinance.

        Args:
            ticker: yfinance ticker symbol (e.g. ``GC=F``).
            period: yfinance period string (e.g. ``5y``, ``max``).

        Returns:
            DataFrame with columns: date, indicator, value, unit, source.
        """
        domain = "finance.yahoo.com"
        self._limiter.wait(domain)
        try:
            import yfinance as yf

            df = yf.download(
                ticker, period=period, auto_adjust=True, progress=False,
            )
        except Exception as exc:
            self._limiter.record_error(domain, status_code=None)
            logger.error("yfinance download failed for %s: %s", ticker, exc)
            return _empty_macro_frame()

        if df is None or df.empty:
            self._limiter.record_error(domain, status_code=None)
            logger.warning("No commodity data returned for %s", ticker)
            return _empty_macro_frame()

        self._limiter.record_success(domain)

        # Flatten multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        rows = []
        name = _commodity_name_for_ticker(ticker)
        for ts, row in df.iterrows():
            close = row.get("Close")
            if pd.isna(close):
                continue
            date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
            rows.append(
                {
                    "date": date_str,
                    "indicator": name,
                    "value": float(close),
                    "unit": "usd",
                    "source": "yfinance",
                }
            )
        if not rows:
            return _empty_macro_frame()
        return pd.DataFrame(rows, columns=["date", "indicator", "value", "unit", "source"])

    def fetch_all(self, period: str = "5y") -> dict[str, pd.DataFrame]:
        """Fetch all configured commodity tickers.

        Returns:
            Mapping of commodity name to DataFrame.
        """
        results: dict[str, pd.DataFrame] = {}
        for name, ticker in self._tickers.items():
            logger.info("Fetching commodity %s (%s)", name, ticker)
            results[name] = self.fetch_commodity(ticker, period=period)
        return results


def _commodity_name_for_ticker(ticker: str) -> str:
    """Return a human-readable commodity name for a ticker."""
    for name, sym in COMMODITY_TICKERS.items():
        if sym == ticker:
            return name
    return ticker


# ---------------------------------------------------------------------------
# Unified Macro Data Fetcher
# ---------------------------------------------------------------------------


class MacroDataFetcher:
    """Unified fetcher that orchestrates all macro data sources.

    Combines BPS, World Bank, NOAA, and commodity fetchers with a shared
    :class:`DynamicRateLimiter`. Handles partial failures gracefully —
    one source being down does not break the others.

    Args:
        rate_limiter: Optional shared dynamic rate limiter.
        bps_key: Optional BPS API key (else from env ``BPS_API_KEY``).
    """

    def __init__(
        self,
        rate_limiter: DynamicRateLimiter | None = None,
        bps_key: str | None = None,
    ) -> None:
        self._limiter = rate_limiter or DynamicRateLimiter()
        self._bps = BPSFetcher(self._limiter, api_key=bps_key)
        self._world_bank = WorldBankFetcher(self._limiter)
        self._noaa = NOAAFetcher(self._limiter)
        self._commodity = CommodityFetcher(self._limiter)

    def fetch_source(self, source_name: str) -> FetchResult:
        """Fetch from a single named source.

        Args:
            source_name: One of ``bps``, ``world_bank``, ``noaa``, ``commodity``.

        Returns:
            FetchResult with the combined DataFrame for that source.
        """
        source_name = source_name.lower()
        start = time.monotonic()
        try:
            if source_name == "bps":
                frames = [
                    self._bps.fetch_gdp(),
                    self._bps.fetch_cpi(),
                    self._bps.fetch_trade_balance(),
                    self._bps.fetch_industrial_production(),
                ]
                df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
            elif source_name == "world_bank":
                frames = [
                    self._world_bank.fetch_gdp(),
                    self._world_bank.fetch_trade(),
                    self._world_bank.fetch_inflation(),
                ]
                df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
            elif source_name == "noaa":
                df = self._noaa.fetch_oni()
            elif source_name == "commodity":
                all_commodities = self._commodity.fetch_all()
                df = pd.concat(
                    [f for f in all_commodities.values() if not f.empty],
                    ignore_index=True,
                )
            else:
                return FetchResult(
                    source=source_name,
                    success=False,
                    data=_empty_macro_frame(),
                    error=f"Unknown source: {source_name}",
                    elapsed_seconds=time.monotonic() - start,
                )
        except Exception as exc:
            logger.error("Source %s failed: %s", source_name, exc)
            return FetchResult(
                source=source_name,
                success=False,
                data=_empty_macro_frame(),
                error=str(exc),
                elapsed_seconds=time.monotonic() - start,
            )

        elapsed = time.monotonic() - start
        logger.info(
            "Source %s: %d rows in %.2fs", source_name, len(df), elapsed,
        )
        return FetchResult(
            source=source_name,
            success=True,
            data=df,
            row_count=len(df),
            elapsed_seconds=elapsed,
        )

    def fetch_all(self) -> dict[str, FetchResult]:
        """Fetch from all sources, handling partial failures.

        Returns:
            Mapping of source name to FetchResult. Failed sources have
            ``success=False`` and an error message.
        """
        sources = ["bps", "world_bank", "noaa", "commodity"]
        results: dict[str, FetchResult] = {}
        for src in sources:
            logger.info("=== Fetching macro source: %s ===", src)
            result = self.fetch_source(src)
            results[src] = result
            if not result.success:
                logger.warning("Source %s failed: %s", src, result.error)
        return results

    def fetch_all_combined(self) -> pd.DataFrame:
        """Fetch from all sources and return a single combined DataFrame.

        Macro sources (bps, world_bank, noaa) share the standard schema
        (date, indicator, value, unit, source). Commodity data is also
        normalized to that schema.
        """
        results = self.fetch_all()
        frames: list[pd.DataFrame] = []
        for result in results.values():
            if result.success and not result.data.empty:
                frames.append(result.data)
        if not frames:
            return _empty_macro_frame()
        return pd.concat(frames, ignore_index=True)
