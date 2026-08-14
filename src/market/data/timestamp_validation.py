"""Timestamp validation utility for OHLCV data ingestion.

Ensures that timestamps inserted into the database match the expected
market close time for each exchange, preventing intraday/incomplete
data from being stored as daily bars.

Usage:
    from market.data.timestamp_validation import validate_ohlcv_timestamp
    is_valid, reason = validate_ohlcv_timestamp(ticker, timestamp, session)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Expected UTC close times per MIC — STANDARD TIME (winter, non-DST)
# During DST (summer), US/European markets close 1 hour earlier in UTC
# Source: pustaka/03-pasar-modal-global.md, verified Aug 2026
EXPECTED_CLOSE_UTC: dict[str, tuple[int, int]] = {
    "XIDX": (8, 50),    # IDX close 15:50 WIB = 08:50 UTC (no DST)
    "XNYS": (21, 0),    # NYSE close 16:00 EST = 21:00 UTC (STD) / 20:00 UTC (DST)
    "XNAS": (21, 0),    # NASDAQ same as NYSE
    "XTSE": (6, 30),    # Tokyo close 15:30 JST = 06:30 UTC (no DST)
    "XHKG": (8, 0),     # HK close 16:00 HKT = 08:00 UTC (no DST)
    "XLON": (16, 30),   # London close 16:30 GMT = 16:30 UTC (STD) / 15:30 UTC (DST)
    "XFRA": (16, 30),   # Xetra close 17:30 CET = 16:30 UTC (STD) / 15:30 UTC (DST)
    "XCEC": (18, 30),   # COMEX gold close 13:30 EST = 18:30 UTC (STD) / 17:30 UTC (DST)
    "XFXS": (22, 0),    # FX market 17:00 EST = 22:00 UTC (STD) / 21:00 UTC (DST)
    "XKLSE": (9, 0),    # Bursa Malaysia close 17:00 MYT = 09:00 UTC (no DST, UTC+8)
    "XSHG": (7, 0),     # Shanghai close 15:00 CST = 07:00 UTC (no DST)
}

# Expected UTC open times per MIC — STANDARD TIME (winter, non-DST)
# Used by is_market_open() for accurate open/close window checking
EXPECTED_OPEN_UTC: dict[str, tuple[int, int]] = {
    "XIDX": (2, 0),     # IDX open 09:00 WIB = 02:00 UTC (no DST)
    "XNYS": (14, 30),   # NYSE open 09:30 EST = 14:30 UTC (STD) / 13:30 UTC (DST)
    "XNAS": (14, 30),   # NASDAQ same as NYSE
    "XTSE": (0, 0),     # Tokyo open 09:00 JST = 00:00 UTC (no DST)
    "XHKG": (1, 30),    # HK open 09:30 HKT = 01:30 UTC (no DST)
    "XLON": (8, 0),     # London open 08:00 GMT = 08:00 UTC (STD) / 07:00 UTC (DST)
    "XFRA": (8, 0),     # Xetra open 09:00 CET = 08:00 UTC (STD) / 07:00 UTC (DST)
    "XCEC": (13, 20),   # COMEX gold open 08:20 EST = 13:20 UTC (STD) / 12:20 UTC (DST)
    "XFXS": (22, 0),    # FX market 24h (use Sunday 22:00 UTC as weekly open)
    "XKLSE": (1, 0),    # Bursa Malaysia open 09:00 MYT = 01:00 UTC (no DST, UTC+8)
    "XSHG": (1, 0),     # Shanghai open 09:00 CST = 01:00 UTC (no DST)
}

# Simple holiday check — fixed-date holidays for major markets.
# This is a lightweight check; floating holidays (Good Friday, Easter Monday,
# Lunar New Year, Eid al-Fitr, etc.) are NOT covered. For production-grade
# holiday handling, use exchange-calendars or pandas-market-calendars.
# Source: exchange websites, verified Aug 2026.
FIXED_HOLIDAYS: dict[str, set[tuple[int, int]]] = {
    "XIDX": {  # Indonesia — fixed national holidays
        (1, 1),   # New Year
        (8, 17),  # Independence Day
        (12, 25), # Christmas
        (12, 26), # Boxing Day (post-Christmas)
    },
    "XNYS": {  # NYSE — fixed holidays
        (1, 1),   # New Year
        (7, 4),   # Independence Day
        (12, 25), # Christmas
    },
    "XNAS": {  # NASDAQ — same as NYSE
        (1, 1), (7, 4), (12, 25),
    },
    "XTSE": {  # Tokyo — fixed holidays
        (1, 1),   # New Year
        (1, 2),   # Market holiday
        (1, 3),   # Market holiday
        (12, 31), # Market holiday
    },
    "XHKG": {  # HKEX — fixed holidays
        (1, 1),   # New Year
        (12, 25), # Christmas
        (12, 26), # Boxing Day
    },
    "XLON": {  # LSE — fixed holidays
        (1, 1),   # New Year
        (12, 25), # Christmas
        (12, 26), # Boxing Day
    },
    "XFRA": {  # Xetra — fixed holidays
        (1, 1),   # New Year
        (12, 24), # Christmas Eve
        (12, 25), # Christmas
        (12, 26), # Boxing Day / St. Stephen's
        (12, 31), # New Year's Eve
    },
}

# Ticker → MIC mapping for common global tickers
TICKER_MIC: dict[str, str] = {
    "^JKSE": "XIDX", "^JKLQ45": "XIDX",
    "^GSPC": "XNYS", "^DJI": "XNYS", "^IXIC": "XNAS", "^VIX": "XNYS",
    "^TNX": "XNYS", "DX-Y.NYB": "XNYS",
    "^N225": "XTSE",
    "^HSI": "XHKG",
    "^FTSE": "XLON",
    "^GDAXI": "XFRA",
    "000001.SS": "XSHG",
    "GC=F": "XCEC", "CL=F": "XCEC", "HG=F": "XCEC", "SI=F": "XCEC",
    "IDR=X": "XFXS",
    "CPO=F": "XKLSE", "FCPO=F": "XKLSE",
}


def is_us_dst(date: datetime) -> bool:
    """Check if a date falls within US DST (March-November)."""
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    year = date.year
    # Second Sunday of March to first Sunday of November
    import calendar
    march_sundays = [
        d for d in range(8, 15)
        if calendar.weekday(year, 3, d) == calendar.SUNDAY
    ]
    nov_sundays = [
        d for d in range(1, 8)
        if calendar.weekday(year, 11, d) == calendar.SUNDAY
    ]
    dst_start = datetime(year, 3, march_sundays[0], 2, 0, tzinfo=UTC)
    dst_end = datetime(year, 11, nov_sundays[0], 2, 0, tzinfo=UTC)
    return dst_start <= date < dst_end


def is_eu_dst(date: datetime) -> bool:
    """Check if a date falls within European DST (last Sunday March → last Sunday October)."""
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    year = date.year
    import calendar
    # Last Sunday of March
    march_last_sunday = max(
        d for d in range(25, 32)
        if calendar.weekday(year, 3, d) == calendar.SUNDAY
    )
    # Last Sunday of October
    oct_last_sunday = max(
        d for d in range(25, 32)
        if calendar.weekday(year, 10, d) == calendar.SUNDAY
    )
    dst_start = datetime(year, 3, march_last_sunday, 1, 0, tzinfo=UTC)
    dst_end = datetime(year, 10, oct_last_sunday, 1, 0, tzinfo=UTC)
    return dst_start <= date < dst_end


def get_expected_close_utc(mic: str, dt: datetime) -> datetime:
    """Get expected UTC market close time for a given MIC and date.

    Handles DST for US and European markets.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    base = EXPECTED_CLOSE_UTC.get(mic)
    if base is None:
        return dt  # Unknown MIC, can't validate

    hour, minute = base

    # DST adjustments: during DST, US/Europe close 1 hour earlier in UTC
    if mic in ("XNYS", "XNAS", "XCEC", "XFXS"):
        if is_us_dst(dt):
            hour -= 1  # e.g., NYSE 20:00 UTC → 20:00 during EDT, 21:00 during EST
    elif mic in ("XLON", "XFRA"):
        if is_eu_dst(dt):
            hour -= 1  # e.g., London 15:30 UTC during BST, 16:30 UTC during GMT

    return datetime(dt.year, dt.month, dt.day, hour, minute, 0, tzinfo=UTC)


def validate_ohlcv_timestamp(
    ticker: str,
    timestamp: datetime,
    mic: str | None = None,
    tolerance_minutes: int = 30,
) -> tuple[bool, str]:
    """Validate that an OHLCV timestamp matches the expected market close time.

    Args:
        ticker: Ticker symbol (e.g., '^GSPC', 'BBCA.JK').
        timestamp: The timestamp to validate (timezone-aware preferred).
        mic: Market MIC code. If None, inferred from ticker.
        tolerance_minutes: Allowed deviation from expected close time.

    Returns:
        Tuple of (is_valid, reason). is_valid=True if timestamp is within
        tolerance of the expected market close time.
    """
    if mic is None:
        mic = TICKER_MIC.get(ticker)
        if mic is None:
            if ticker.endswith(".JK"):
                mic = "XIDX"
            else:
                return True, f"Unknown MIC for ticker {ticker}, skipping validation"

    if mic not in EXPECTED_CLOSE_UTC:
        return True, f"Unknown MIC {mic}, skipping validation"

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)

    expected = get_expected_close_utc(mic, timestamp)
    diff = abs((timestamp - expected).total_seconds()) / 60

    if diff <= tolerance_minutes:
        return True, f"OK: {timestamp.strftime('%H:%M')} UTC ≈ expected {expected.strftime('%H:%M')} UTC ({mic})"
    return False, (
        f"MISMATCH: {ticker} timestamp {timestamp.strftime('%Y-%m-%d %H:%M')} UTC "
        f"vs expected {expected.strftime('%H:%M')} UTC for {mic} "
        f"(diff={diff:.0f}min, tolerance={tolerance_minutes}min)"
    )


def _is_fixed_holiday(mic: str, dt: datetime) -> bool:
    """Check if a date is a fixed-date holiday for the given market.

    Only covers fixed-date holidays (New Year, Christmas, etc.).
    Floating holidays (Easter, Lunar New Year, Eid, etc.) are NOT
    covered — for production use, install exchange-calendars.
    """
    holidays = FIXED_HOLIDAYS.get(mic)
    if not holidays:
        return False
    return (dt.month, dt.day) in holidays


def get_expected_open_utc(mic: str, dt: datetime) -> datetime:
    """Get expected UTC market open time for a given MIC and date.

    Handles DST for US and European markets.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    base = EXPECTED_OPEN_UTC.get(mic)
    if base is None:
        return dt  # Unknown MIC

    hour, minute = base

    if mic in ("XNYS", "XNAS", "XCEC", "XFXS"):
        if is_us_dst(dt):
            hour -= 1
    elif mic in ("XLON", "XFRA"):
        if is_eu_dst(dt):
            hour -= 1

    return datetime(dt.year, dt.month, dt.day, hour, minute, 0, tzinfo=UTC)


def is_market_open(mic: str, now: datetime | None = None) -> bool:
    """Check if a market is currently open (for ingestion gating).

    Uses actual open/close times per MIC with DST adjustment and
    fixed-date holiday checking. For FX markets (XFXS), returns True
    on weekdays (24h trading).

    Args:
        mic: Market MIC code.
        now: Current time (defaults to now UTC).

    Returns:
        True if the market is currently in its trading session.
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    if mic not in EXPECTED_CLOSE_UTC:
        return False  # Unknown market, assume closed

    # Weekend check
    if now.weekday() >= 5:
        return False

    # Fixed holiday check
    if _is_fixed_holiday(mic, now):
        return False

    # FX market: 24h on weekdays
    if mic == "XFXS":
        return True

    expected_open = get_expected_open_utc(mic, now)
    expected_close = get_expected_close_utc(mic, now)

    return expected_open <= now < expected_close
