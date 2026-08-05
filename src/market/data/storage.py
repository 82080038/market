"""Data storage repository (pustaka/18 §2.3).

Provides save/load operations for OHLCV, scores, corporate actions,
source health, and audit log via SQLAlchemy.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from market.db.models import (
    OHLCV,
    AuditLog,
    DataWatermark,
    Score,
    SourceHealth,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from market.data.contracts import NormalizedOHLCV

logger = logging.getLogger(__name__)


class DataRepository:
    """Repository for persisting market data to SQLite."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_ohlcv(self, records: Sequence[NormalizedOHLCV]) -> int:
        """Save OHLCV records with INSERT OR REPLACE semantics.

        Returns:
            Number of records saved.
        """
        count = 0
        for r in records:
            existing = self._session.execute(
                select(OHLCV).where(
                    OHLCV.ticker == r.ticker,
                    OHLCV.timestamp == r.timestamp,
                    OHLCV.timeframe == "1d",
                )
            ).scalar_one_or_none()

            if existing:
                existing.open = r.open
                existing.high = r.high
                existing.low = r.low
                existing.close = r.close
                existing.volume = r.volume
                existing.adjusted_close = r.adjusted_close
                existing.data_quality_score = r.data_quality_score
                existing.source = r.source
            else:
                self._session.add(
                    OHLCV(
                        ticker=r.ticker,
                        timestamp=r.timestamp,
                        timeframe="1d",
                        open=r.open,
                        high=r.high,
                        low=r.low,
                        close=r.close,
                        volume=r.volume,
                        adjusted_close=r.adjusted_close,
                        data_quality_score=r.data_quality_score,
                        source=r.source,
                    )
                )
            count += 1

        self._session.commit()
        return count

    def load_ohlcv(
        self,
        ticker: str,
        start: datetime | None = None,
        end: datetime | None = None,
        timeframe: str = "1d",
    ) -> list[OHLCV]:
        """Load OHLCV records for a ticker."""
        stmt = select(OHLCV).where(
            OHLCV.ticker == ticker,
            OHLCV.timeframe == timeframe,
        )
        if start:
            stmt = stmt.where(OHLCV.timestamp >= start)
        if end:
            stmt = stmt.where(OHLCV.timestamp < end)
        stmt = stmt.order_by(OHLCV.timestamp)
        return list(self._session.execute(stmt).scalars().all())

    def list_tickers(self) -> list[str]:
        """List unique tickers in the OHLCV table."""
        stmt = select(OHLCV.ticker).distinct()
        return list(self._session.execute(stmt).scalars().all())

    def save_score(
        self,
        ticker: str,
        engine: str,
        score: float,
        breakdown: dict[str, object] | None = None,
    ) -> None:
        """Save an engine score for a ticker."""
        breakdown_str = json.dumps(breakdown) if breakdown else None
        self._session.add(
            Score(
                ticker=ticker,
                engine=engine,
                score=score,
                breakdown=breakdown_str,
                as_of=datetime.now(UTC),
            )
        )
        self._session.commit()

    def update_source_health(
        self,
        source: str,
        status: str = "ok",
        error_msg: str | None = None,
    ) -> None:
        """Upsert source health record."""
        existing = self._session.get(SourceHealth, source)
        now = datetime.now(UTC)
        if existing:
            existing.status = status
            existing.updated_at = now
            if status == "ok":
                existing.last_success = now
                existing.total_fetches += 1
            else:
                existing.last_error = now
                existing.last_error_msg = error_msg
                existing.total_failures += 1
        else:
            self._session.add(
                SourceHealth(
                    source=source,
                    status=status,
                    last_success=now if status == "ok" else None,
                    last_error=now if status != "ok" else None,
                    last_error_msg=error_msg,
                    total_fetches=1 if status == "ok" else 0,
                    total_failures=1 if status != "ok" else 0,
                )
            )
        self._session.commit()

    def audit(
        self,
        event_type: str,
        payload: dict[str, object] | None = None,
        actor: str = "system",
    ) -> None:
        """Write an audit log entry (append-only)."""
        self._session.add(
            AuditLog(
                event_type=event_type,
                event_payload=json.dumps(payload) if payload else None,
                actor=actor,
            )
        )
        self._session.commit()

    def update_watermark(
        self,
        ticker: str,
        table_name: str,
        row_count: int | None = None,
        source: str = "yahoo_finance",
    ) -> None:
        """Update data watermark for staleness tracking."""
        existing = self._session.execute(
            select(DataWatermark).where(
                DataWatermark.ticker == ticker,
                DataWatermark.table_name == table_name,
            )
        ).scalar_one_or_none()

        now = datetime.now(UTC)
        if existing:
            existing.last_updated = now
            existing.row_count = row_count
            existing.source = source
        else:
            self._session.add(
                DataWatermark(
                    ticker=ticker,
                    table_name=table_name,
                    last_updated=now,
                    row_count=row_count,
                    source=source,
                )
            )
        self._session.commit()
