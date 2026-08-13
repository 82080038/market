"""Cross-Market Timezone & DST Engine (pustaka/36, pustaka/92 §4).

Provides DST-aware cutoff verification and anti look-ahead bias feature
alignment for global market data ingestion.

Key components:
1. ``verify_dst_cutoff`` — Checks whether Wall Street (NYSE/NASDAQ) has
   fully closed, accounting for Daylight Saving Time shifts:
   - Summer (DST, March→November): US close = 03:00 WIB (20:00 UTC)
   - Winter (Standard, November→March): US close = 04:00 WIB (21:00 UTC)
2. ``get_us_market_close_utc`` — Returns the Wall Street close time in UTC
   for a given date, correctly handling DST transitions.
3. ``is_us_market_closed`` — Boolean check: has Wall Street fully closed?
4. ``DST_AWARE_GLOBAL_TICKERS`` — Tickers whose data must wait for US close.
5. ``get_aligned_global_features`` — Supplies global features at 16:15 WIB
   with anti look-ahead bias: T-0 for Asian markets (close before IDX),
   T-1 for US markets and commodities (close after IDX).

Time-Zone Bucket Grid (UTC):
    B0: 00:00-02:00 → Tokyo open, before IDX open (overnight Asia)
    B1: 02:00-08:50 → IDX open (Jakarta trading)
    B2: 08:50-14:30 → IDX closed, before NYSE open (Europe transition)
    B3: 14:30-21:00 → NYSE/NASDAQ session
    B4: 21:00-24:00 → NYSE closed (post-Wall Street, before Tokyo)

At 16:15 WIB (09:15 UTC) — prediction time:
    - Tokyo (^N225): closed at 06:30 UTC → T-0 data available
    - Hong Kong (^HSI): closed at 08:00 UTC → T-0 data available
    - US (^GSPC, ^VIX, ^TNX): opens 13:30/14:30 UTC → must use T-1
    - Commodities (GC=F, CL=F, HG=F, MTF=F, CPO=F): US-centric settle → T-1

References:
    pustaka/36-gap-data-timezone-global-idx.md
    pustaka/92-multi-market-multi-asset-trading-system.md §4
    MEGAPLAN.md Fase 7 — DST Shift-Aware Logic
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

# Tickers whose data depends on Wall Street close completion
DST_AWARE_GLOBAL_TICKERS: list[str] = [
    "^GSPC",   # S&P 500
    "^IXIC",   # NASDAQ Composite
    "^DJI",    # Dow Jones
    "^VIX",    # CBOE Volatility Index
    "^TNX",    # 10-Year Treasury Yield
    "GC=F",    # Gold futures (COMEX)
    "CL=F",    # Crude Oil futures (NYMEX)
    "HG=F",    # Copper futures (COMEX)
]

# US/Eastern timezone via zoneinfo (auto DST aware)
_ET = ZoneInfo("America/New_York")
_WIB = ZoneInfo("Asia/Jakarta")

# ── Market close times in UTC (standard time) ──────────────────────────────
# Markets that close BEFORE IDX close (08:50 UTC) → T-0 data available
# at 16:15 WIB (09:15 UTC) prediction time.
ASIAN_T0_TICKERS: set[str] = {
    "^N225",  # Tokyo close: 06:30 UTC (before IDX close 08:50 UTC)
    "^HSI",   # Hong Kong close: 08:00 UTC (before IDX close 08:50 UTC)
}

# Markets that close AFTER IDX → must use T-1 (previous day close)
# US equities, US futures, European indices, and commodity futures.
US_T1_TICKERS: set[str] = {
    "^GSPC",  # US close: 20:00/21:00 UTC (after IDX)
    "^IXIC",  # US close: 20:00/21:00 UTC
    "^DJI",   # US close: 20:00/21:00 UTC
    "^VIX",   # US close: 20:00/21:00 UTC
    "^TNX",   # US close: 20:00/21:00 UTC
    "^FTSE",  # LSE close: 15:30/16:30 UTC (after IDX close)
    "GC=F",   # COMEX settle: ~20:00/21:00 UTC
    "CL=F",   # NYMEX settle: ~20:00/21:00 UTC
    "HG=F",   # COMEX settle: ~20:00/21:00 UTC
    "MTF=F",  # ICE coal settle: US-centric hours
    "CPO=F",  # Bursa Malaysia close: 10:00 UTC (after 09:15 UTC prediction)
    "FCPO=F", # FCPO (Bursa Malaysia, same as CPO=F — yfinance uses CPO=F)
}

# All global tickers with their lag requirement (0 = same day, 1 = previous day)
GLOBAL_TICKER_LAGS: dict[str, int] = {
    # Asian — T-0 (close before IDX)
    "^N225": 0,
    "^HSI": 0,
    # US — T-1 (close after IDX)
    "^GSPC": 1,
    "^IXIC": 1,
    "^DJI": 1,
    "^VIX": 1,
    "^TNX": 1,
    # European — T-1 (close after IDX)
    "^FTSE": 1,
    # Commodities — T-1 (US-centric settle or close after prediction time)
    "GC=F": 1,
    "CL=F": 1,
    "HG=F": 1,
    "MTF=F": 1,
    "CPO=F": 1,
    "FCPO=F": 1,
}


@dataclass(frozen=True)
class MarketTimezoneInfo:
    """Market timezone and session info for a global ticker."""

    ticker: str
    exchange: str
    tz_name: str
    close_utc_hour: float  # UTC hour of close (standard time)
    supports_dst: bool
    lag_days: int  # 0 = T-0 (close before IDX), 1 = T-1 (close after IDX)


# Pre-defined market timezone metadata
MARKET_TIMEZONES: dict[str, MarketTimezoneInfo] = {
    "^N225": MarketTimezoneInfo("^N225", "TSE", "Asia/Tokyo", 6.5, False, 0),
    "^HSI": MarketTimezoneInfo("^HSI", "HKEX", "Asia/Hong_Kong", 8.0, False, 0),
    "^GSPC": MarketTimezoneInfo("^GSPC", "NYSE", "America/New_York", 21.0, True, 1),
    "^IXIC": MarketTimezoneInfo("^IXIC", "NASDAQ", "America/New_York", 21.0, True, 1),
    "^DJI": MarketTimezoneInfo("^DJI", "NYSE", "America/New_York", 21.0, True, 1),
    "^VIX": MarketTimezoneInfo("^VIX", "CBOE", "America/New_York", 21.0, True, 1),
    "^TNX": MarketTimezoneInfo("^TNX", "CBOE", "America/New_York", 21.0, True, 1),
    "^FTSE": MarketTimezoneInfo("^FTSE", "LSE", "Europe/London", 16.5, True, 1),
    "GC=F": MarketTimezoneInfo("GC=F", "COMEX", "America/New_York", 21.0, True, 1),
    "CL=F": MarketTimezoneInfo("CL=F", "NYMEX", "America/New_York", 21.0, True, 1),
    "HG=F": MarketTimezoneInfo("HG=F", "COMEX", "America/New_York", 21.0, True, 1),
    "MTF=F": MarketTimezoneInfo("MTF=F", "ICE", "America/New_York", 21.0, True, 1),
    "CPO=F": MarketTimezoneInfo("CPO=F", "Bursa Malaysia", "Asia/Kuala_Lumpur", 10.0, False, 1),
    "FCPO=F": MarketTimezoneInfo("FCPO=F", "Bursa Malaysia", "Asia/Kuala_Lumpur", 10.0, False, 1),
}


@dataclass(frozen=True)
class DSTCutoffResult:
    """Result of DST cutoff verification."""

    current_time_utc: datetime
    us_close_utc: datetime
    is_dst: bool
    us_market_closed: bool
    wait_seconds: int  # seconds until US market closes (0 if already closed)
    dst_label: str  # "EDT" (summer) or "EST" (winter)

    def __str__(self) -> str:
        status = "CLOSED" if self.us_market_closed else "OPEN"
        return (
            f"DSTCutoff(us_close={self.us_close_utc.isoformat()}, "
            f"dst={self.dst_label}, us_market={status}, "
            f"wait={self.wait_seconds}s)"
        )


def get_us_market_close_utc(date: datetime | pd.Timestamp | None = None) -> datetime:
    """Return Wall Street close time in UTC for a given date.

    US market closes at 16:00 Eastern Time.
    - During EDT (Daylight Saving, ~March→November): 16:00 EDT = 20:00 UTC
    - During EST (Standard, ~November→March): 16:00 EST = 21:00 UTC

    Uses ``zoneinfo`` for accurate DST transition detection (second Sunday
    of March 02:00 → first Sunday of November 02:00).

    Args:
        date: The date to check (defaults to current UTC time).

    Returns:
        UTC datetime of Wall Street close for that date.
    """
    if date is None:
        date = datetime.now(UTC)
    elif isinstance(date, pd.Timestamp):
        date = date.to_pydatetime()
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)

    # Convert to Eastern Time to determine the close hour
    et_naive = date.astimezone(_ET).replace(hour=16, minute=0, second=0, microsecond=0)
    # Convert back to UTC
    return et_naive.astimezone(UTC)


def is_us_dst(date: datetime | pd.Timestamp | None = None) -> bool:
    """Check if a given date falls within US Daylight Saving Time.

    Args:
        date: Date to check (defaults to now).

    Returns:
        True if date is during DST (EDT), False if EST.
    """
    if date is None:
        date = datetime.now(UTC)
    elif isinstance(date, pd.Timestamp):
        date = date.to_pydatetime()
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)

    et = date.astimezone(_ET)
    # zoneinfo handles DST automatically — check if offset is -4 (EDT) vs -5 (EST)
    dst_offset = et.utcoffset()
    standard_offset = timedelta(hours=-5)
    return dst_offset != standard_offset


def is_us_market_closed(now: datetime | None = None) -> bool:
    """Check if Wall Street has fully closed for the current session.

    Args:
        now: Current UTC time (defaults to ``datetime.now(UTC)``).

    Returns:
        True if current time is past Wall Street close.
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    us_close = get_us_market_close_utc(now)
    return now >= us_close


def verify_dst_cutoff(
    now: datetime | None = None,
    tickers: list[str] | None = None,
) -> DSTCutoffResult:
    """Verify that Wall Street has fully closed before locking global data.

    During DST (summer, March→November):
        US close = 03:00 WIB (20:00 UTC)
    During EST (winter, November→March):
        US close = 04:00 WIB (21:00 UTC)

    This function ensures the daily signal pipeline waits for full Wall
    Street settlement before using ^GSPC, ^VIX, and other US-dependent
    data for LightGBM feature computation.

    Args:
        now: Current UTC time (defaults to ``datetime.now(UTC)``).
        tickers: List of tickers that depend on US close (for logging).

    Returns:
        DSTCutoffResult with close time, DST status, and wait duration.
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    us_close = get_us_market_close_utc(now)
    dst = is_us_dst(now)
    closed = now >= us_close

    if closed:
        wait = 0
    else:
        wait = int((us_close - now).total_seconds())

    dst_label = "EDT" if dst else "EST"

    if not closed and tickers:
        logger.info(
            "DST cutoff: Wall Street still OPEN (closes at %s UTC / %s WIB). "
            "Waiting %ds for: %s",
            us_close.strftime("%H:%M"),
            us_close.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M"),
            wait,
            ", ".join(tickers),
        )

    return DSTCutoffResult(
        current_time_utc=now,
        us_close_utc=us_close,
        is_dst=dst,
        us_market_closed=closed,
        wait_seconds=wait,
        dst_label=dst_label,
    )


def get_us_close_wib(date: datetime | pd.Timestamp | None = None) -> str:
    """Return Wall Street close time in WIB (UTC+7) for display.

    Args:
        date: Date to check.

    Returns:
        String like "03:00 WIB" (DST) or "04:00 WIB" (EST).
    """
    us_close = get_us_market_close_utc(date)
    wib = us_close.astimezone(ZoneInfo("Asia/Jakarta"))
    return wib.strftime("%H:%M WIB")


def get_ticker_lag(ticker: str) -> int:
    """Return the required lag (in days) for a global ticker.

    - Asian markets (^N225, ^HSI): lag=0 (T-0, close before IDX)
    - US markets & commodities: lag=1 (T-1, close after IDX)

    Args:
        ticker: Global ticker symbol.

    Returns:
        0 for T-0 (Asian), 1 for T-1 (US/European/commodities).
    """
    return GLOBAL_TICKER_LAGS.get(ticker, 1)  # default to T-1 (safe)


def get_aligned_global_features(
    as_of_wib: datetime | pd.Timestamp | None = None,
    global_data: dict[str, pd.DataFrame] | None = None,
    lookback: int = 5,
) -> dict[str, float]:
    """Supply global features aligned to 16:15 WIB prediction time.

    At 16:15 WIB (09:15 UTC):
    - Asian markets (^N225, ^HSI) already closed → T-0 same-day close
    - US markets (^GSPC, ^VIX, ^TNX) not yet opened → T-1 previous close
    - Commodities (GC=F, CL=F, HG=F, MTF=F, CPO=F) → T-1 previous settle

    This function computes lag-1 and lag-5 returns for each global asset,
    applying the correct lag (0 or 1) per ticker to prevent look-ahead bias.

    Args:
        as_of_wib: Prediction timestamp in WIB (defaults to now).
        global_data: Dict of {ticker: DataFrame} with 'close' column and
            DatetimeIndex. If None, returns empty dict.
        lookback: Momentum lookback period (default 5 days).

    Returns:
        Dict of {feature_name: value} ready for MultiFactorModel/MLSignalProvider.
        Feature names follow pattern: ``{asset_name}_lag1_ret``, ``{asset_name}_lag5_ret``.
    """
    if global_data is None:
        return {}

    if as_of_wib is None:
        as_of_wib = datetime.now(_WIB)
    elif isinstance(as_of_wib, pd.Timestamp):
        as_of_wib = as_of_wib.to_pydatetime()
    if as_of_wib.tzinfo is None:
        as_of_wib = as_of_wib.replace(tzinfo=_WIB)
    else:
        as_of_wib = as_of_wib.astimezone(_WIB)

    as_of_utc = as_of_wib.astimezone(UTC)
    as_of_date = as_of_utc.date()

    # Import GLOBAL_ASSETS for name mapping
    from market.analysis.multi_factor import GLOBAL_ASSETS

    features: dict[str, float] = {}

    for ticker, name in GLOBAL_ASSETS.items():
        if ticker not in global_data:
            continue

        gdf = global_data[ticker]
        if gdf is None or gdf.empty:
            continue

        gclose = gdf["close"].astype(float)
        lag = get_ticker_lag(ticker)

        # Filter to data available at prediction time (anti look-ahead)
        # For T-0 tickers: data up to as_of_date is valid (already closed)
        # For T-1 tickers: only data up to as_of_date - 1 is valid
        cutoff_date = as_of_date - timedelta(days=lag)

        if isinstance(gdf.index, pd.DatetimeIndex):
            if gdf.index.tzinfo is not None:
                mask = gdf.index.tz_convert("UTC").date <= cutoff_date
            else:
                mask = gdf.index.date <= cutoff_date
            gclose_valid = gclose[mask]
        else:
            gclose_valid = gclose

        if len(gclose_valid) < 2:
            features[f"{name}_lag1_ret"] = 0.0
            features[f"{name}_lag5_ret"] = 0.0
            continue

        current = gclose_valid.iloc[-1]

        # lag1 return: daily return (with correct T-0/T-1 alignment)
        if len(gclose_valid) >= 2:
            prev = gclose_valid.iloc[-2]
            lag1_ret = (current - prev) / prev if prev > 0 else 0.0
        else:
            lag1_ret = 0.0

        # lag5 return: 5-day momentum
        if len(gclose_valid) >= lookback + 1:
            past = gclose_valid.iloc[-(lookback + 1)]
            lag5_ret = (current - past) / past if past > 0 else 0.0
        else:
            lag5_ret = 0.0

        features[f"{name}_lag1_ret"] = float(lag1_ret)
        features[f"{name}_lag5_ret"] = float(lag5_ret)

    return features
