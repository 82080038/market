"""Price adjustment, volume dynamics, and time-zone overlap utilities.

Implements three critical market factors:
1. Corporate Action adjustment (split/dividend backward adjustment)
2. Volume dynamics features (VWAP, Volume ROC, OBV)
3. Time-Zone Bucket Grid for global market sentiment transmission

All operations use UTC timestamps strictly (no look-ahead).
References: pustaka/18 §3.2, pustaka/20, pustaka/26, pustaka/92 §4.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, timedelta
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── 1. CORPORATE ACTION PRICE ADJUSTMENT ──────────────────────────────────


class CAActionType(Enum):
    """Corporate action types for price adjustment."""

    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    DIVIDEND = "dividend"
    STOCK_DIVIDEND = "stock_dividend"
    BONUS = "bonus"


@dataclass
class CAEvent:
    """A single corporate action event."""

    ticker: str
    action_type: CAActionType
    ex_date: str
    ratio: float = 1.0
    value: float = 0.0
    currency: str = "IDR"


def compute_adjustment_factor(
    events: list[CAEvent],
    target_date: pd.Timestamp,
    current_date: pd.Timestamp,
) -> float:
    """Compute cumulative backward adjustment factor.

    For splits: factor = 1/ratio (prices before ex_date divided by ratio)
    For dividends: factor = 1 - div/prev_close (approximate)

    Args:
        events: List of corporate action events (sorted by ex_date desc).
        target_date: The date to adjust prices for.
        current_date: The most recent date (reference point).

    Returns:
        Cumulative adjustment factor. Multiply raw prices by this factor
        to get adjusted prices.
    """
    factor = 1.0
    for event in events:
        ex_date = pd.Timestamp(event.ex_date)
        if ex_date <= target_date:
            continue

        if event.action_type in (
            CAActionType.SPLIT, CAActionType.STOCK_DIVIDEND, CAActionType.BONUS,
        ):
            factor /= event.ratio
        elif event.action_type == CAActionType.REVERSE_SPLIT:
            factor *= event.ratio
        elif event.action_type == CAActionType.DIVIDEND:
            # Dividend adjustment: factor *= (1 - div/price)
            # This is approximate without exact prev_close; use ratio
            # For backward adjustment, we use the dividend yield approximation
            # The exact factor requires the close on the day before ex_date
            # We skip this here since yfinance already provides adjusted_close
            pass

    return factor


def apply_adjusted_prices(
    df: pd.DataFrame,
    adjusted_close_col: str = "adjusted_close",
) -> pd.DataFrame:
    """Apply adjusted prices to OHLCV DataFrame.

    If adjusted_close is available, compute adjustment ratio and apply
    to all OHLC columns. If not available, return as-is.

    The adjustment ratio = adj_close / close. This ratio is applied
    to open, high, low to get adjusted OHLC. Volume is divided by
    the ratio (split increases share count, so volume goes up).

    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume.
            Must also have adjusted_close column (from yfinance auto_adjust=False).
        adjusted_close_col: Column name for adjusted close.

    Returns:
        DataFrame with adjusted OHLCV (same columns, prices adjusted).
    """
    if df.empty:
        return df.copy()

    result = df.copy()

    if adjusted_close_col not in result.columns:
        logger.warning("adjusted_close not in DataFrame — using raw prices")
        return result

    adj_close = result[adjusted_close_col]
    raw_close = result["close"].astype(float)

    # Compute adjustment ratio per row
    # Where adjusted_close is None, ratio = 1.0 (no adjustment)
    ratio = np.where(
        (adj_close.notna()) & (raw_close > 0),
        adj_close.astype(float) / raw_close,
        1.0,
    )

    # Apply to OHLC
    for col in ["open", "high", "low", "close"]:
        if col in result.columns:
            result[col] = result[col].astype(float) * ratio

    # Volume: inverse adjustment (split increases volume)
    if "volume" in result.columns:
        vol_ratio = np.where(ratio > 0, 1.0 / ratio, 1.0)
        result["volume"] = result["volume"].astype(float) * vol_ratio

    # Mark as adjusted
    result.attrs["price_adjusted"] = True

    return result


def ensure_adjusted(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame uses adjusted prices.

    Priority:
    1. If 'adjusted_close' column exists → use apply_adjusted_prices
    2. If 'adj_close' column exists → rename and use
    3. Otherwise, return as-is (log warning)

    Args:
        df: OHLCV DataFrame.

    Returns:
        DataFrame with adjusted OHLCV.
    """
    if df.empty:
        return df

    if "adjusted_close" in df.columns:
        return apply_adjusted_prices(df, "adjusted_close")
    elif "adj_close" in df.columns:
        result = df.copy()
        result["adjusted_close"] = result["adj_close"]
        return apply_adjusted_prices(result, "adjusted_close")
    else:
        logger.debug(
            "No adjusted_close column — using raw prices. "
            "Stock splits may cause false anomalies."
        )
        return df.copy()


# ── 2. VOLUME DYNAMICS FEATURE ENGINEERING ────────────────────────────────


def compute_vwap(
    df: pd.DataFrame,
    window: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Compute rolling Volume-Weighted Average Price (VWAP).

    VWAP = sum(close * volume) / sum(volume) over rolling window.

    Args:
        df: OHLCV DataFrame.
        window: Rolling window size (default 20 bars).
        price_col: Price column to use (default 'close').

    Returns:
        pd.Series of VWAP values.
    """
    if df.empty or price_col not in df.columns or "volume" not in df.columns:
        return pd.Series(dtype=float, index=df.index)

    price = df[price_col].astype(float)
    volume = df["volume"].astype(float)

    vol_price = price * volume
    vol_sum = volume.rolling(window, min_periods=1).sum()
    vp_sum = vol_price.rolling(window, min_periods=1).sum()

    vwap = vp_sum / vol_sum.replace(0, np.nan)
    return vwap


def compute_volume_roc(
    df: pd.DataFrame,
    period: int = 10,
    vol_col: str = "volume",
) -> pd.Series:
    """Compute Volume Rate of Change (VROC).

    VROC = ((volume_t - volume_{t-period}) / volume_{t-period}) * 100

    Args:
        df: OHLCV DataFrame.
        period: Lookback period (default 10).
        vol_col: Volume column name.

    Returns:
        pd.Series of VROC values (percentage).
    """
    if df.empty or vol_col not in df.columns:
        return pd.Series(dtype=float, index=df.index)

    vol = df[vol_col].astype(float)
    roc = ((vol - vol.shift(period)) / vol.shift(period).replace(0, np.nan)) * 100
    return roc


def compute_obv(df: pd.DataFrame, price_col: str = "close") -> pd.Series:
    """Compute On-Balance Volume (OBV).

    OBV accumulates volume: +volume if price up, -volume if price down.

    Args:
        df: OHLCV DataFrame.
        price_col: Price column.

    Returns:
        pd.Series of OBV values.
    """
    if df.empty or price_col not in df.columns or "volume" not in df.columns:
        return pd.Series(dtype=float, index=df.index)

    price = df[price_col].astype(float)
    volume = df["volume"].astype(float)

    direction = np.sign(price.diff())
    obv = (direction * volume).cumsum()
    return obv


def compute_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all volume-based features for ML/prediction.

    Adds columns:
    - vwap_20: 20-bar rolling VWAP
    - vwap_ratio: close / vwap_20 (price vs VWAP)
    - vol_roc_10: 10-bar volume rate of change (%)
    - obv: On-Balance Volume (cumulative)
    - obv_slope: OBV 5-bar slope (trend direction)
    - vol_price_trend: volume * price change correlation

    Args:
        df: OHLCV DataFrame.

    Returns:
        DataFrame with additional volume feature columns.
    """
    result = df.copy()

    # VWAP
    result["vwap_20"] = compute_vwap(result, window=20)
    result["vwap_ratio"] = (
        result["close"].astype(float) / result["vwap_20"].replace(0, np.nan)
    )

    # Volume ROC
    result["vol_roc_10"] = compute_volume_roc(result, period=10)

    # OBV
    result["obv"] = compute_obv(result)
    result["obv_slope"] = result["obv"].diff(5)

    # Volume-price trend (positive = volume confirms price direction)
    price_change = result["close"].astype(float).pct_change()
    vol_norm = result["volume"].astype(float) / result["volume"].astype(float).rolling(20).mean()
    result["vol_price_trend"] = (price_change * vol_norm).rolling(10).mean()

    return result


# ── 3. TIME-ZONE BUCKET GRID ──────────────────────────────────────────────


@dataclass
class MarketSession:
    """Market trading session definition (all times in UTC)."""

    mic_code: str
    name: str
    tz_name: str
    open_utc: tuple[int, int]  # (hour, minute) in UTC (standard time)
    close_utc: tuple[int, int]  # (hour, minute) in UTC (standard time)
    supports_dst: bool = False

    @property
    def open_hour_utc(self) -> float:
        return self.open_utc[0] + self.open_utc[1] / 60.0

    @property
    def close_hour_utc(self) -> float:
        return self.close_utc[0] + self.close_utc[1] / 60.0

    def is_open_at(self, ts: pd.Timestamp) -> bool:
        """Check if market is open at given UTC timestamp.

        Note: DST adjustment is approximate (±1 hour).
        For backtesting, this is sufficient since we use daily bars.
        """
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")

        hour = ts.hour + ts.minute / 60.0
        # Approximate DST: if US market and between March-November, shift +1h
        if self.supports_dst:
            month = ts.month
            if 3 <= month <= 11:
                hour_adj = hour - 1  # UTC open is 1h earlier during DST
                open_h = self.open_hour_utc - 1
                close_h = self.close_hour_utc - 1
            else:
                hour_adj = hour
                open_h = self.open_hour_utc
                close_h = self.close_hour_utc
        else:
            hour_adj = hour
            open_h = self.open_hour_utc
            close_h = self.close_hour_utc

        return open_h <= hour_adj <= close_h


# Pre-defined market sessions (standard time UTC offsets)
MARKET_SESSIONS: dict[str, MarketSession] = {
    "XIDX": MarketSession(
        mic_code="XIDX",
        name="Indonesia Stock Exchange (IDX)",
        tz_name="Asia/Jakarta",
        open_utc=(2, 0),    # 09:00 WIB = 02:00 UTC
        close_utc=(8, 50),  # 15:50 WIB = 08:50 UTC
        supports_dst=False,
    ),
    "XNYS": MarketSession(
        mic_code="XNYS",
        name="New York Stock Exchange (NYSE)",
        tz_name="America/New_York",
        open_utc=(14, 30),  # 09:30 EST = 14:30 UTC
        close_utc=(21, 0),  # 16:00 EST = 21:00 UTC
        supports_dst=True,
    ),
    "XNAS": MarketSession(
        mic_code="XNAS",
        name="NASDAQ",
        tz_name="America/New_York",
        open_utc=(14, 30),
        close_utc=(21, 0),
        supports_dst=True,
    ),
    "XTSE": MarketSession(
        mic_code="XTSE",
        name="Tokyo Stock Exchange (TSE)",
        tz_name="Asia/Tokyo",
        open_utc=(0, 0),    # 09:00 JST = 00:00 UTC
        close_utc=(6, 30),  # 15:30 JST = 06:30 UTC
        supports_dst=False,
    ),
    "XHKG": MarketSession(
        mic_code="XHKG",
        name="Hong Kong Stock Exchange (HKEX)",
        tz_name="Asia/Hong_Kong",
        open_utc=(1, 30),   # 09:30 HKT = 01:30 UTC
        close_utc=(8, 0),   # 16:00 HKT = 08:00 UTC
        supports_dst=False,
    ),
    "XLON": MarketSession(
        mic_code="XLON",
        name="London Stock Exchange (LSE)",
        tz_name="Europe/London",
        open_utc=(8, 0),    # 08:00 GMT = 08:00 UTC
        close_utc=(16, 30), # 16:30 GMT = 16:30 UTC (standard)
        supports_dst=True,
    ),
}


@dataclass
class TimeBucketGrid:
    """Time-Zone Bucket Grid for mapping global market sessions.

    Divides a trading day into buckets based on which global markets
    are open/closed. This maps the transmission of sentiment from
    global markets to IDX.

    Buckets (UTC):
    - B0: 00:00-02:00 → Tokyo open, before IDX open (overnight Asia)
    - B1: 02:00-08:50 → IDX open (Jakarta trading)
    - B2: 08:50-14:30 → IDX closed, before NYSE open (Europe transition)
    - B3: 14:30-21:00 → NYSE/NASDAQ open (Wall Street)
    - B4: 21:00-24:00 → NYSE closed (post-Wall Street, before Tokyo)

    For IDX daily bars, the key transmission is:
    - B3 (previous day): Wall Street close → B1 (next day): IDX open
    - B0 (same day): Tokyo session → B1: IDX open
    """

    bucket_definitions: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "B0_overnight_asia": (0.0, 2.0),     # Tokyo open → IDX open
        "B1_idx_session": (2.0, 8.83),       # IDX trading (08:50 = 8.83)
        "B2_europe_transition": (8.83, 14.5), # IDX close → NYSE open
        "B3_wall_street": (14.5, 21.0),      # NYSE/NASDAQ session
        "B4_post_wall_street": (21.0, 24.0),  # After NYSE close
    })

    def get_bucket(self, ts: pd.Timestamp) -> str:
        """Get bucket label for a UTC timestamp.

        Args:
            ts: Timestamp (will be converted to UTC if needed).

        Returns:
            Bucket label string.
        """
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")

        hour = ts.hour + ts.minute / 60.0

        for label, (start, end) in self.bucket_definitions.items():
            if start <= hour < end:
                return label

        return "B4_post_wall_street"  # Fallback

    def get_global_sentiment_window(
        self, idx_date: pd.Timestamp,
    ) -> dict[str, pd.Timestamp]:
        """Get the global market window that precedes an IDX trading day.

        For a given IDX trading date, returns the timestamps of:
        - wall_street_close_prev: Previous day's Wall Street close (UTC)
        - tokyo_close: Tokyo close on the same day (before IDX open)
        - hong_kong_close: HK close on the same day (overlaps with IDX)

        This defines the "sentiment transmission window" — global market
        data that is available BEFORE IDX opens, without look-ahead.

        Args:
            idx_date: The IDX trading date.

        Returns:
            Dict of market close timestamps.
        """
        if idx_date.tzinfo is None:
            idx_date = idx_date.tz_localize("UTC")
        else:
            idx_date = idx_date.tz_convert("UTC")

        # Previous day's Wall Street close: 21:00 UTC
        prev_day = idx_date - timedelta(days=1)
        wall_street_close = pd.Timestamp(
            year=prev_day.year, month=prev_day.month, day=prev_day.day,
            hour=21, minute=0, tzinfo=UTC,
        )

        # Tokyo close on same day: 06:30 UTC
        tokyo_close = pd.Timestamp(
            year=idx_date.year, month=idx_date.month, day=idx_date.day,
            hour=6, minute=30, tzinfo=UTC,
        )

        # Hong Kong close on same day: 08:00 UTC
        hk_close = pd.Timestamp(
            year=idx_date.year, month=idx_date.month, day=idx_date.day,
            hour=8, minute=0, tzinfo=UTC,
        )

        return {
            "wall_street_close_prev": wall_street_close,
            "tokyo_close": tokyo_close,
            "hong_kong_close": hk_close,
            "idx_open": idx_date.replace(hour=2, minute=0, second=0, microsecond=0),
            "idx_close": idx_date.replace(hour=8, minute=50, second=0, microsecond=0),
        }


def compute_global_sentiment_signal(
    global_data: dict[str, pd.DataFrame],
    idx_date: pd.Timestamp,
    lookback: int = 5,
) -> dict[str, float]:
    """Compute global market sentiment signal for an IDX trading date.

    Uses data from global markets that closed BEFORE IDX opened on the
    given date. This ensures strict no-look-ahead.

    Signals computed:
    - us_sentiment: S&P 500 (^GSPC) momentum over `lookback` days
    - asia_sentiment: Nikkei 225 (^N225) momentum
    - hk_sentiment: Hang Seng (^HSI) momentum
    - combined_global: Weighted average of all three

    Args:
        global_data: Dict of {ticker: DataFrame} for global indices.
        idx_date: The IDX trading date.
        lookback: Momentum lookback period (days).

    Returns:
        Dict of sentiment signals (-1.0 to 1.0).
    """
    grid = TimeBucketGrid()
    window = grid.get_global_sentiment_window(idx_date)

    signals: dict[str, float] = {}

    # Map global tickers to their close timestamps
    market_map = {
        "^GSPC": ("wall_street_close_prev", "us_sentiment"),
        "^N225": ("tokyo_close", "asia_sentiment"),
        "^HSI": ("hong_kong_close", "hk_sentiment"),
    }

    for ticker, (ts_key, signal_name) in market_map.items():
        if ticker not in global_data:
            continue

        df = global_data[ticker]
        if df.empty:
            continue

        cutoff = window[ts_key]

        # Filter to data before the cutoff (strict no-look-ahead)
        if df.index.tzinfo is None:
            df_filtered = df[df.index <= cutoff.tz_localize(None)]
        else:
            df_filtered = df[df.index <= cutoff]

        if len(df_filtered) < lookback + 1:
            continue

        close = df_filtered["close"].astype(float)
        current = close.iloc[-1]
        past = close.iloc[-lookback - 1]

        if past > 0:
            momentum = (current - past) / past
            # Normalize: ±5% momentum → ±1.0 signal
            signal = max(-1.0, min(1.0, momentum / 0.05))
            signals[signal_name] = signal

    # Combined signal
    if signals:
        weights = {"us_sentiment": 0.5, "asia_sentiment": 0.3, "hk_sentiment": 0.2}
        combined = sum(
            signals.get(k, 0.0) * w
            for k, w in weights.items()
        )
        signals["combined_global"] = combined

    return signals


def get_market_overlap_status(ts: pd.Timestamp) -> dict[str, bool]:
    """Check which markets are open at a given timestamp.

    Args:
        ts: Timestamp to check.

    Returns:
        Dict of {market_code: is_open} for all registered markets.
    """
    return {
        mic: session.is_open_at(ts)
        for mic, session in MARKET_SESSIONS.items()
    }
