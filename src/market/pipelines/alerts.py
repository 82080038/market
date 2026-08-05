"""Alert pipeline — checks for alert conditions after recompute.

SRP: This pipeline ONLY evaluates alert conditions. It does NOT fetch,
recompute, or export. It listens for "data.recompute.completed" and
logs/dispatches alerts.

Listens to: data.recompute.completed
Emits:      (nothing — terminal node)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)


class AlertPipeline:
    """Evaluates alert conditions after data is recomputed.

    This is a terminal node in the event chain — it does not emit
    further events. It only logs alerts and could dispatch notifications.
    """

    def on_recompute_done(self, event: Event) -> None:
        """Handle data.recompute.completed — check alert conditions."""
        results = event.payload.get("tables", {})
        failed = [name for name, count in results.items() if count < 0]

        if failed:
            logger.warning("Alert: recompute failed for tables: %s", failed)

        # Future: check for extreme market conditions, threshold breaches, etc.
        # This is where alert logic lives — completely decoupled from data/analysis
        logger.debug("Alert check complete (no alerts fired)")
