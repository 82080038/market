"""Data acquisition engine (pustaka/18 §2.1, pustaka/92 §4.1).

Orchestrates fetching, validation, and storage of market data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from market.data.validation import DataQualityEngine
from market.data.yahoo_adapter import YahooFinanceAdapter

if TYPE_CHECKING:
    from datetime import date

    from market.data.storage import DataRepository

logger = logging.getLogger(__name__)


class DataAcquisitionEngine:
    """Orchestrates data acquisition from source → validation → storage.

    Args:
        adapter: Data source adapter (defaults to YahooFinanceAdapter).
        validator: Data quality validator.
        repository: Data storage repository.
    """

    def __init__(
        self,
        adapter: YahooFinanceAdapter | None = None,
        validator: DataQualityEngine | None = None,
        repository: DataRepository | None = None,
    ) -> None:
        self._adapter = adapter or YahooFinanceAdapter()
        self._validator = validator or DataQualityEngine()
        self._repository = repository

    def set_repository(self, repository: DataRepository) -> None:
        """Set the data repository (useful for dependency injection)."""
        self._repository = repository

    def fetch_and_store(
        self,
        ticker: str,
        start: date | None = None,
        end: date | None = None,
        period: str = "max",
        market_mic: str = "XIDX",
        currency: str = "IDR",
    ) -> dict[str, object]:
        """Fetch, validate, and store OHLCV for a single ticker.

        Returns:
            Summary dict with counts and quality score.
        """
        if self._repository is None:
            raise RuntimeError("Repository not set. Call set_repository() first.")

        # 1. Fetch
        records = self._adapter.fetch_ohlcv(
            ticker=ticker,
            start=start,
            end=end,
            period=period,
            market_mic=market_mic,
            currency=currency,
        )

        if not records:
            self._repository.update_source_health(
                source="yahoo_finance",
                status="error",
                error_msg=f"No data for {ticker}",
            )
            return {
                "ticker": ticker,
                "fetched": 0,
                "stored": 0,
                "quality_score": 0.0,
                "action": "pause",
            }

        # 2. Validate
        quality = self._validator.validate(records)
        for r in records:
            r.data_quality_score = quality.score

        # 3. Store (only if not paused)
        stored = 0
        if quality.action != "pause":
            stored = self._repository.save_ohlcv(records)
            self._repository.update_watermark(
                ticker=ticker,
                table_name="ohlcv",
                row_count=stored,
            )
            self._repository.update_source_health(source="yahoo_finance", status="ok")
            self._repository.audit(
                event_type="data.fetch_ohlcv",
                payload={
                    "ticker": ticker,
                    "records": stored,
                    "quality_score": quality.score,
                    "action": quality.action,
                },
            )
        else:
            self._repository.update_source_health(
                source="yahoo_finance",
                status="error",
                error_msg=f"Quality pause for {ticker}: {quality.anomalies}",
            )

        return {
            "ticker": ticker,
            "fetched": len(records),
            "stored": stored,
            "quality_score": quality.score,
            "action": quality.action,
            "anomalies": quality.anomalies,
        }
