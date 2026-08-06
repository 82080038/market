"""Export pipeline — syncs DB to parquet backup (incremental hybrid).

SRP: This pipeline ONLY syncs data to parquet and manages WAL checkpoint.
It does NOT fetch or recompute. It listens for "data.export.requested"
(emitted by the scheduler after recompute completes) and emits
"data.export.completed" when done.

Previously this auto-synced after every recompute (which itself fired after
every fetch), causing 5x redundant writes to the flashdisk per night. Now
export runs ONCE per night on its own schedule, after recompute is done.

Uses ``sync_to_parquet.sync_all()`` (hybrid incremental: Hive-partitioned
for time-series, full-rewrite for reference, skip empty runtime) instead
of the legacy ``export_to_parquet.export_all()`` (full rewrite every run).
See pustaka/95-sync-db-to-parquet.md for the full design.

Listens to: data.export.requested
Emits:      data.export.completed
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from market.config import settings

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)


class ExportPipeline:
    """Syncs DB to parquet archive on schedule.

    Pre-flight checks flashdisk mount and disk space.
    Post-sync runs WAL checkpoint to keep DB compact.
    """

    def on_export_requested(self, event: Event) -> None:
        """Handle data.export.requested — sync to parquet.

        Triggered by the scheduler (scheduled or startup catch-up).
        Also can be triggered manually via the same event.
        """
        trigger = event.payload.get("source", "manual")
        self._run_export(trigger=trigger)

    def _run_export(self, trigger: str) -> None:
        """Run the actual sync with pre-flight checks and WAL checkpoint."""
        from market.core.events import broker
        from market.data.data_health import check_disk_space, wal_checkpoint

        parquet_path = Path(settings.parquet_archive_path)

        # Pre-flight: flashdisk mounted + disk space
        disk_issues = check_disk_space(parquet_path)
        critical = [i for i in disk_issues if i.severity == "critical"]
        if critical:
            for issue in critical:
                logger.error("Sync aborted: %s", issue.message)
            broker.emit("data.export.completed", {
                "success": False,
                "reason": "disk_critical",
                "issues": [i.message for i in critical],
            })
            return

        for issue in disk_issues:
            logger.warning("%s", issue.message)

        # Sync (incremental hybrid — pustaka/95)
        from market.data.sync_to_parquet import sync_all

        logger.info("Parquet sync: starting (trigger=%s)", trigger)
        results = sync_all()
        total = sum(stats.get("rows", 0) for stats in results.values())
        parts = sum(stats.get("partitions_written", 0) for stats in results.values())
        logger.info("Parquet sync: %d rows, %d partitions across %d tables",
                    total, parts, len(results))

        # WAL checkpoint
        db_path = Path(settings.resolved_db_path)
        wal_checkpoint(db_path, mode="TRUNCATE")
        logger.info("WAL checkpoint complete")

        # Emit completion — health pipeline will pick this up
        broker.emit("data.export.completed", {
            "success": True,
            "tables": len(results),
            "total_rows": total,
            "partitions": parts,
            "trigger": trigger,
        })
