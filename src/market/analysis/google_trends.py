"""Google Trends integration for market sentiment (Gap #27).

Uses pytrends to fetch Google Trends data for stock-related search terms.
Provides search interest time series that can be used as a sentiment proxy
or alternative data source for trading signals.

Graceful degradation:
- If pytrends not installed, returns empty results with warning.
- If Google Trends rate-limits, retries with backoff.
- Never crashes the application due to Trends API failure.

Note: Google Trends data is daily/weekly granularity, suitable for
swing trading (not intraday/day trading).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TrendsResult:
    """Google Trends search interest result."""

    keyword: str
    timeframe: str  # e.g. "today 3-m", "today 12-m"
    data: list[dict[str, Any]] = field(default_factory=list)  # [{date, value}]
    average_interest: float = 0.0
    peak_interest: int = 0
    peak_date: str = ""
    trend_direction: str = "flat"  # "up", "down", "flat"
    fetched_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_empty(self) -> bool:
        return len(self.data) == 0


@dataclass
class TrendsComparison:
    """Comparison of search interest across multiple keywords."""

    keywords: list[str]
    timeframe: str
    results: dict[str, TrendsResult] = field(default_factory=dict)
    winner: str = ""  # Keyword with highest average interest
    fetched_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class GoogleTrendsCollector:
    """Collects Google Trends data using pytrends (Gap #27).

    Gracefully degrades if pytrends is not installed or Google Trends
    is rate-limiting.
    """

    def __init__(
        self,
        geo: str = "ID",  # Indonesia
        hl: str = "id-ID",  # Bahasa Indonesia
        retry_count: int = 3,
        retry_delay: float = 5.0,
    ) -> None:
        self.geo = geo
        self.hl = hl
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self._pytrends = None
        self._init_pytrends()

    def _init_pytrends(self) -> None:
        """Initialize pytrends client."""
        try:
            from pytrends.request import TrendReq  # type: ignore[import-untyped]
            self._pytrends = TrendReq(hl=self.hl, tz=420)  # tz=420 = UTC+7 WIB
            logger.info("pytrends client initialized.")
        except ImportError:
            logger.warning("pytrends not installed — Google Trends disabled.")
        except Exception as exc:
            logger.warning("Failed to initialize pytrends: %s", exc)

    @property
    def available(self) -> bool:
        return self._pytrends is not None

    def get_interest_over_time(
        self,
        keyword: str,
        timeframe: str = "today 3-m",
    ) -> TrendsResult:
        """Get search interest over time for a keyword.

        Args:
            keyword: Search term (e.g. "saham BCA", "BBCA stock").
            timeframe: Time window. Options:
                "now 1-H", "now 4-H", "now 1-d", "now 7-d",
                "today 1-m", "today 3-m", "today 12-m", "today 5-y".

        Returns:
            TrendsResult with time series data.
        """
        if not self.available:
            logger.debug("pytrends not available — returning empty result.")
            return TrendsResult(keyword=keyword, timeframe=timeframe)

        for attempt in range(self.retry_count):
            try:
                self._pytrends.build_payload(
                    [keyword], cat=0, timeframe=timeframe, geo=self.geo,
                )
                df = self._pytrends.interest_over_time()

                if df.empty:
                    return TrendsResult(keyword=keyword, timeframe=timeframe)

                data = []
                values = []
                for idx, row in df.iterrows():
                    value = int(row[keyword]) if keyword in row else 0
                    date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                    data.append({"date": date_str, "value": value})
                    values.append(value)

                avg = sum(values) / len(values) if values else 0
                peak = max(values) if values else 0
                peak_idx = values.index(peak) if values else 0
                peak_date = data[peak_idx]["date"] if data else ""

                # Determine trend direction (compare first half vs second half)
                if len(values) >= 4:
                    mid = len(values) // 2
                    first_half_avg = sum(values[:mid]) / mid if mid > 0 else 0
                    second_half_avg = sum(values[mid:]) / (len(values) - mid) if (len(values) - mid) > 0 else 0
                    if second_half_avg > first_half_avg * 1.1:
                        direction = "up"
                    elif second_half_avg < first_half_avg * 0.9:
                        direction = "down"
                    else:
                        direction = "flat"
                else:
                    direction = "flat"

                return TrendsResult(
                    keyword=keyword,
                    timeframe=timeframe,
                    data=data,
                    average_interest=round(avg, 2),
                    peak_interest=peak,
                    peak_date=peak_date,
                    trend_direction=direction,
                )

            except Exception as exc:
                logger.warning(
                    "pytrends attempt %d/%d failed: %s",
                    attempt + 1, self.retry_count, exc,
                )
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)

        return TrendsResult(keyword=keyword, timeframe=timeframe)

    def compare_keywords(
        self,
        keywords: list[str],
        timeframe: str = "today 3-m",
    ) -> TrendsComparison:
        """Compare search interest across multiple keywords.

        Args:
            keywords: List of search terms to compare.
            timeframe: Time window.

        Returns:
            TrendsComparison with results for each keyword.
        """
        results: dict[str, TrendsResult] = {}
        for kw in keywords:
            results[kw] = self.get_interest_over_time(kw, timeframe)

        # Determine winner (highest average interest)
        winner = ""
        max_avg = -1
        for kw, result in results.items():
            if result.average_interest > max_avg:
                max_avg = result.average_interest
                winner = kw

        return TrendsComparison(
            keywords=keywords,
            timeframe=timeframe,
            results=results,
            winner=winner,
        )

    def get_related_queries(
        self,
        keyword: str,
        timeframe: str = "today 3-m",
    ) -> dict[str, list[dict[str, Any]]]:
        """Get related queries for a keyword.

        Args:
            keyword: Search term.
            timeframe: Time window.

        Returns:
            Dict with "top" and "rising" related queries.
        """
        if not self.available:
            return {"top": [], "rising": []}

        try:
            self._pytrends.build_payload(
                [keyword], cat=0, timeframe=timeframe, geo=self.geo,
            )
            related = self._pytrends.related_queries()

            top = []
            rising = []
            if keyword in related:
                if related[keyword].get("top") is not None:
                    top = related[keyword]["top"].to_dict("records")
                if related[keyword].get("rising") is not None:
                    rising = related[keyword]["rising"].to_dict("records")

            return {"top": top, "rising": rising}
        except Exception as exc:
            logger.warning("Failed to get related queries: %s", exc)
            return {"top": [], "rising": []}


def trends_to_sentiment_signal(result: TrendsResult) -> float:
    """Convert TrendsResult to a sentiment signal (-1.0 to 1.0).

    Rising search interest = positive sentiment (more attention).
    Falling search interest = negative sentiment (less attention).
    Flat = neutral.

    Args:
        result: TrendsResult from get_interest_over_time.

    Returns:
        Sentiment score from -1.0 to 1.0.
    """
    if result.is_empty:
        return 0.0

    if result.trend_direction == "up":
        return 0.5
    elif result.trend_direction == "down":
        return -0.5
    else:
        return 0.0
