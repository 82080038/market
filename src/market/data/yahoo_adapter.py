"""Yahoo Finance data adapter (pustaka/18 §2.1, pustaka/92 §4.1).

Fetches OHLCV, corporate actions (dividends, splits), and basic info
from Yahoo Finance via the `yfinance` library.
"""

from __future__ import annotations

import logging
from datetime import UTC, date
from decimal import Decimal

import pandas as pd
import yfinance as yf

from market.config import settings
from market.data.contracts import CorporateActionRecord, NormalizedOHLCV
from market.data.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


class YahooFinanceAdapter:
    """Yahoo Finance data adapter with rate limiting.

    Args:
        rate_limit: Max calls per second.
    """

    def __init__(self, rate_limit: float | None = None) -> None:
        self._limiter = RateLimiter(
            max_calls=rate_limit or settings.yfinance_rate_limit_per_second,
        )

    def fetch_ohlcv(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        period: str = "max",
        market_mic: str = "XIDX",
        currency: str = "IDR",
    ) -> list[NormalizedOHLCV]:
        """Fetch OHLCV data for a single ticker.

        Args:
            ticker: Yahoo Finance ticker (e.g. ``BBCA.JK``).
            start: Start date (inclusive). If None, uses ``period``.
            end: End date (exclusive).
            period: yfinance period string (e.g. ``max``, ``1y``, ``3mo``).
            market_mic: Market MIC code for the record.
            currency: Native currency of the instrument.

        Returns:
            List of NormalizedOHLCV records.
        """
        self._limiter.acquire()
        logger.info(
            "Fetching OHLCV for %s (period=%s, start=%s, end=%s)",
            ticker, period, start, end,
        )

        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                period=period if not start else None,
                auto_adjust=False,
                progress=False,
                interval="1d",
            )
        except Exception as exc:
            logger.error("yfinance download failed for %s: %s", ticker, exc)
            return []

        if df is None or df.empty:
            logger.warning("No data returned for %s", ticker)
            return []

        records: list[NormalizedOHLCV] = []
        for ts, row in df.iterrows():
            try:
                ts_dt = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=UTC)

                records.append(
                    NormalizedOHLCV(
                        ticker=ticker,
                        market_mic=market_mic,
                        timestamp=ts_dt,
                        open=Decimal(str(row["Open"])),
                        high=Decimal(str(row["High"])),
                        low=Decimal(str(row["Low"])),
                        close=Decimal(str(row["Close"])),
                        volume=int(row["Volume"]),
                        adjusted_close=(
                            Decimal(str(row["Adj Close"]))
                            if "Adj Close" in row else None
                        ),
                        currency=currency,
                        source="yahoo_finance",
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping row for %s at %s: %s", ticker, ts, exc)

        return records

    def fetch_dividends(self, ticker: str) -> list[CorporateActionRecord]:
        """Fetch dividend history for a ticker."""
        self._limiter.acquire()
        try:
            ticker_obj = yf.Ticker(ticker)
            divs = ticker_obj.dividends
        except Exception as exc:
            logger.error("yfinance dividends failed for %s: %s", ticker, exc)
            return []

        if divs is None or divs.empty:
            return []

        records: list[CorporateActionRecord] = []
        for ts, amount in divs.items():
            ex_date = ts.date() if isinstance(ts, pd.Timestamp) else ts
            records.append(
                CorporateActionRecord(
                    ticker=ticker,
                    action_type="dividend",
                    ex_date=ex_date,
                    value=float(amount),
                    currency="IDR" if ticker.endswith(".JK") else "USD",
                    source="yahoo_finance",
                )
            )
        return records

    def fetch_splits(self, ticker: str) -> list[CorporateActionRecord]:
        """Fetch stock split history for a ticker."""
        self._limiter.acquire()
        try:
            ticker_obj = yf.Ticker(ticker)
            splits = ticker_obj.splits
        except Exception as exc:
            logger.error("yfinance splits failed for %s: %s", ticker, exc)
            return []

        if splits is None or splits.empty:
            return []

        records: list[CorporateActionRecord] = []
        for ts, ratio in splits.items():
            ex_date = ts.date() if isinstance(ts, pd.Timestamp) else ts
            records.append(
                CorporateActionRecord(
                    ticker=ticker,
                    action_type="stock_split",
                    ex_date=ex_date,
                    value=float(ratio),
                    description=f"Split ratio {ratio}:1",
                    source="yahoo_finance",
                )
            )
        return records

    def fetch_info(self, ticker: str) -> dict[str, object]:
        """Fetch basic instrument info (name, sector, market_cap, etc.)."""
        self._limiter.acquire()
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
        except Exception as exc:
            logger.error("yfinance info failed for %s: %s", ticker, exc)
            return {}

        return dict(info) if info else {}
