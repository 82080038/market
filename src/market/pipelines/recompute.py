"""Recompute pipeline — recomputes internal tables from fresh OHLCV.

SRP: This pipeline ONLY recomputes derived data (indicators, scores, etc).
It does NOT fetch data or export. It listens for "data.recompute.requested"
(emitted by the scheduler after ALL fetch phases complete) and emits
"data.recompute.completed" when done.

Previously this listened to "data.fetch.completed" which fired after EACH
fetch phase (eod, global, macro), causing 3-4x redundant recompute per
night. Now recompute runs ONCE after all fetches are done.

Listens to: data.recompute.requested
Emits:      data.recompute.completed
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)


class RecomputePipeline:
    """Recomputes indicators, scores, and derived data after fetch.

    This pipeline is triggered by the scheduler after all fetch phases
    (eod, global, macro) have completed. It does NOT know where the data
    came from — it just recomputes.
    """

    def on_recompute_requested(self, event: Event) -> None:
        """Handle data.recompute.requested — recompute all internal tables.

        Runs: technical_indicators, scores, relationship_matrix,
        fear_greed, stock_personality, ml_labels, market_regimes.

        If event payload contains incremental=True, time-series tables
        (fear_greed, ml_labels, market_regimes) only append new dates.
        Snapshot tables always do full recompute (they store latest only).
        """
        from market.analysis.recompute import run_all_recompute
        from market.db.engine import get_sessionmaker
        from market.core.events import broker

        source = event.payload.get("source", "unknown")
        incremental = event.payload.get("incremental", False)
        mode_label = "incremental" if incremental else "full"
        logger.info("Recompute triggered by %s (mode=%s)", source, mode_label)

        session = get_sessionmaker()()
        try:
            results = run_all_recompute(
                session, dry_run=False, incremental=incremental,
            )

            success_count = sum(1 for v in results.values() if v >= 0)
            logger.info("Recompute complete (%s): %d/%d tables updated",
                        mode_label, success_count, len(results))

            # Emit completion — alert pipeline picks this up for alert evaluation.
            # Export is NOT auto-triggered here; it runs on its own schedule
            # (data.export.requested from scheduler) to avoid redundant writes
            # to the flashdisk archive.
            broker.emit("data.recompute.completed", {
                "tables": results,
                "success_count": success_count,
                "triggered_by": source,
                "incremental": incremental,
            })
        finally:
            session.close()
