"""Recompute pipeline — recomputes internal tables from fresh OHLCV.

SRP: This pipeline ONLY recomputes derived data (indicators, scores, etc).
It does NOT fetch data or export. It listens for "data.fetch.completed"
and emits "data.recompute.completed" when done.

Listens to: data.fetch.completed
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

    This pipeline is triggered automatically when new data is fetched.
    It does NOT know where the data came from — it just recomputes.
    """

    def on_data_fetched(self, event: Event) -> None:
        """Handle data.fetch.completed — recompute all internal tables.

        Runs: technical_indicators, scores, relationship_matrix,
        fear_greed, stock_personality.
        """
        from market.data.recompute_internal import (
            recompute_fear_greed,
            recompute_relationship_matrix,
            recompute_scores,
            recompute_stock_personality,
            recompute_technical_indicators,
        )
        from market.db.engine import get_sessionmaker
        from market.core.events import broker

        source = event.payload.get("source", "unknown")
        logger.info("Recompute triggered by %s fetch", source)

        session = get_sessionmaker()()
        try:
            results = {}
            for name, func in [
                ("technical_indicators", recompute_technical_indicators),
                ("scores", recompute_scores),
                ("relationship_matrix", recompute_relationship_matrix),
                ("fear_greed", recompute_fear_greed),
                ("stock_personality", recompute_stock_personality),
            ]:
                try:
                    count = func(session)
                    results[name] = count
                    logger.info("  %s: %d rows", name, count)
                except Exception as e:
                    logger.error("  %s: FAILED — %s", name, e)
                    results[name] = -1

            success_count = sum(1 for v in results.values() if v >= 0)
            logger.info("Recompute complete: %d/%d tables updated",
                        success_count, len(results))

            # Emit completion — export pipeline will pick this up
            broker.emit("data.recompute.completed", {
                "tables": results,
                "success_count": success_count,
                "triggered_by": source,
            })
        finally:
            session.close()
