"""Data lineage & provenance tracking (Gap #35).

Records the origin, transformation, and storage path of every data point
fetched into the system. This enables:
- Audit trail: "where did this data come from?"
- Debugging: "which fetcher version produced this anomaly?"
- Reproducibility: "what parameters were used?"
- Freshness tracking: "when was this last fetched?"

Lineage records are persisted to the ``audit_log`` table via the
repository's ``audit()`` method, with ``event_type="data.lineage"``.

Usage:
    from market.data.lineage import LineageTracker
    tracker = LineageTracker(repository)
    tracker.record(
        source="yahoo_finance",
        ticker="BBCA.JK",
        row_count=1000,
        quality_score=0.95,
        parameters={"period": "max", "market_mic": "XIDX"},
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market.data.storage import DataRepository

logger = logging.getLogger(__name__)

# Version of the lineage tracking system itself
LINEAGE_VERSION = "1.0.0"


@dataclass
class DataLineage:
    """A single data lineage record — provenance for one fetch operation."""
    source: str                          # yahoo_finance, FRED, NASA_POWER, etc.
    ticker: str                          # what was fetched
    fetched_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    fetcher_version: str = ""            # version of the fetcher code
    parameters: dict[str, Any] = field(default_factory=dict)  # fetch params
    row_count: int = 0                   # rows fetched
    stored_count: int = 0                # rows actually stored
    quality_score: float = 0.0           # data quality score (0-1)
    storage_table: str = ""              # where stored (stock_prices, macro_data, etc.)
    checksum: str = ""                   # MD5 of first/last row for integrity
    action: str = "store"                # store, pause, skip
    error: str | None = None             # error message if failed
    lineage_version: str = LINEAGE_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return asdict(self)

    def compute_checksum(self, records: list[Any]) -> str:
        """Compute a checksum from the first and last record for integrity.

        Args:
            records: List of data records (objects with attributes or dicts).

        Returns:
            MD5 hex string.
        """
        if not records:
            return ""
        first = records[0]
        last = records[-1]

        def _serialize(r: Any) -> str:
            if isinstance(r, dict):
                return json.dumps(r, sort_keys=True, default=str)
            return str(r.__dict__) if hasattr(r, "__dict__") else str(r)

        combined = _serialize(first) + _serialize(last)
        self.checksum = hashlib.md5(combined.encode()).hexdigest()  # noqa: S324
        return self.checksum


class LineageTracker:
    """Tracks data lineage records and persists them.

    Args:
        repository: DataRepository with an ``audit()`` method for persistence.
        fetcher_version: Version string of the current fetcher code.
    """

    def __init__(
        self,
        repository: DataRepository | None = None,
        fetcher_version: str = "",
    ) -> None:
        self._repository = repository
        self._fetcher_version = fetcher_version
        self._records: list[DataLineage] = []

    def set_repository(self, repository: DataRepository) -> None:
        """Set or update the repository for persistence."""
        self._repository = repository

    def record(
        self,
        source: str,
        ticker: str,
        row_count: int = 0,
        stored_count: int = 0,
        quality_score: float = 0.0,
        parameters: dict[str, Any] | None = None,
        storage_table: str = "",
        action: str = "store",
        error: str | None = None,
        records: list[Any] | None = None,
    ) -> DataLineage:
        """Record a lineage entry and persist it.

        Args:
            source: Data source name (yahoo_finance, FRED, etc.).
            ticker: Ticker that was fetched.
            row_count: Number of rows fetched.
            stored_count: Number of rows actually stored.
            quality_score: Data quality score (0-1).
            parameters: Fetch parameters dict.
            storage_table: Table where data was stored.
            action: Action taken (store, pause, skip).
            error: Error message if fetch failed.
            records: Optional records list for checksum computation.

        Returns:
            The created DataLineage record.
        """
        lineage = DataLineage(
            source=source,
            ticker=ticker,
            fetcher_version=self._fetcher_version,
            parameters=parameters or {},
            row_count=row_count,
            stored_count=stored_count,
            quality_score=quality_score,
            storage_table=storage_table,
            action=action,
            error=error,
        )

        if records:
            lineage.compute_checksum(records)

        self._records.append(lineage)
        self._persist(lineage)
        return lineage

    def _persist(self, lineage: DataLineage) -> None:
        """Persist lineage to the audit log via repository."""
        if self._repository is None:
            logger.debug("Lineage not persisted (no repository): %s", lineage.ticker)
            return

        try:
            self._repository.audit(
                event_type="data.lineage",
                payload=lineage.to_dict(),
            )
        except Exception as exc:
            logger.error("Failed to persist lineage for %s: %s", lineage.ticker, exc)

    @property
    def records(self) -> list[DataLineage]:
        """All lineage records in memory."""
        return list(self._records)

    def get_lineage(self, ticker: str | None = None) -> list[DataLineage]:
        """Get lineage records, optionally filtered by ticker."""
        if ticker:
            return [r for r in self._records if r.ticker == ticker]
        return list(self._records)

    def clear(self) -> None:
        """Clear in-memory records (does not affect persisted records)."""
        self._records.clear()
