"""Export pipeline — exports DB to parquet backup.

SRP: This pipeline ONLY exports data to parquet and manages WAL checkpoint.
It does NOT fetch or recompute. It listens for "data.recompute.completed"
and emits "data.export.completed" when done.

Listens to: data.recompute.completed, data.export.requested
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
    """Exports DB to parquet archive after data is recomputed.

    Pre-flight checks flashdisk mount and disk space.
    Post-export runs WAL checkpoint to keep DB compact.
    """

    def on_recompute_done(self, event: Event) -> None:
        """Handle data.recompute.completed — auto-export to parquet."""
        self._run_export(trigger="recompute")

    def on_export_requested(self, event: Event) -> None:
        """Handle data.export.requested — manual export trigger."""
        self._run_export(trigger="manual")

    def _run_export(self, trigger: str) -> None:
        """Run the actual export with pre-flight checks and WAL checkpoint."""
        from market.core.events import broker
        from market.data.data_health import check_disk_space, wal_checkpoint

        parquet_path = Path(settings.parquet_archive_path)

        # Pre-flight: flashdisk mounted + disk space
        disk_issues = check_disk_space(parquet_path)
        critical = [i for i in disk_issues if i.severity == "critical"]
        if critical:
            for issue in critical:
                logger.error("Export aborted: %s", issue.message)
            broker.emit("data.export.completed", {
                "success": False,
                "reason": "disk_critical",
                "issues": [i.message for i in critical],
            })
            return

        for issue in disk_issues:
            logger.warning("%s", issue.message)

        # Export
        from market.data.export_to_parquet import export_all

        logger.info("Parquet export: starting (trigger=%s)", trigger)
        results = export_all()
        total = sum(results.values())
        logger.info("Parquet export: %d rows across %d tables", total, len(results))

        # WAL checkpoint
        db_path = Path(settings.resolved_db_path)
        wal_checkpoint(db_path, mode="TRUNCATE")
        logger.info("WAL checkpoint complete")

        # Emit completion — health pipeline will pick this up
        broker.emit("data.export.completed", {
            "success": True,
            "tables": len(results),
            "total_rows": total,
            "trigger": trigger,
        })
