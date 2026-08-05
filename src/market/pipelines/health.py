"""Health pipeline — runs health checks after data cycle completes.

SRP: This pipeline ONLY checks system health. It does NOT fix issues.
It listens for "data.export.completed" and emits "health.check.completed".

Listens to: data.export.completed, health.check.requested
Emits:      health.check.completed
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from market.config import settings

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)


class HealthPipeline:
    """Runs health checks and reports issues.

    Checks: stale data, disk space, DB integrity, source health.
    Does NOT fix issues — only reports them.
    """

    def on_export_done(self, event: Event) -> None:
        """Handle data.export.completed — run health checks."""
        self._run_checks(trigger="post_export")

    def on_check_requested(self, event: Event) -> None:
        """Handle health.check.requested — manual health check."""
        self._run_checks(trigger="manual")

    def _run_checks(self, trigger: str) -> None:
        """Run all health checks and emit results."""
        from market.core.events import broker
        from market.data.data_health import check_all

        report = check_all(
            db_path=Path(settings.resolved_db_path),
            parquet_path=Path(settings.parquet_archive_path),
        )

        for issue in report.issues:
            if issue.severity == "critical":
                logger.error("HEALTH [critical] %s: %s — %s",
                            issue.category, issue.message, issue.detail)
            elif issue.severity == "warning":
                logger.warning("HEALTH [warning] %s: %s — %s",
                              issue.category, issue.message, issue.detail)
            else:
                logger.info("HEALTH [info] %s: %s", issue.category, issue.message)

        logger.info("Health check complete (%s): %s", trigger, report.summary())

        broker.emit("health.check.completed", {
            "trigger": trigger,
            "summary": report.summary(),
            "has_critical": report.has_critical,
            "has_warning": report.has_warning,
            "issue_count": len(report.issues),
        })
