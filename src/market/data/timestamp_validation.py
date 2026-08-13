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


def is_market_open(mic: str, now: datetime | None = None) -> bool:
    """Check if a market is currently open (for ingestion gating).

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

    expected_close = get_expected_close_utc(mic, now)
    # Market is open if we're before the close time on the same day
    # and it's a weekday (simplified — doesn't check holidays)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False

    # Open time: typically close_time - 6.5 hours for stock exchanges
    # For simplicity, check if we're within 8 hours before close
    open_window = expected_close - now
    return timedelta(0) < open_window <= timedelta(hours=8)
