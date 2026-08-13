"""Signal pipeline — generates trading signals after recompute.

SRP: This pipeline ONLY generates trading signals for watchlist tickers.
It listens for "signal.generate.requested" (emitted by scheduler after
recompute completes) and runs the signal generation logic.

The heavy lifting (config loading, EOD data ingestion, signal computation,
position sizing) is delegated to the existing ``daily_signal_cron`` module
to avoid duplication. This pipeline wraps it in an event-driven interface.

Listens to: signal.generate.requested
Emits:      signal.generate.completed (with signal summary)
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)


class SignalPipeline:
    """Generates trading signals for watchlist tickers.

    Wraps the existing ``scripts/daily_signal_cron.py`` in an event-driven
    interface. The script handles:
    - Reading optimal config from best_ticker_quant_config.json
    - Loading latest EOD data from DB
    - Running generate_ticker_signals() per ticker
    - Computing position sizing (Inverse-Variance weighting)
    - Injecting results to app_notifications table

    This pipeline runs it as a subprocess for isolation (the script has
    its own logging, error handling, and config management).
    """

    def on_signal_requested(self, event: Event) -> None:
        """Handle signal.generate.requested — run signal generation.

        Event payload (optional):
            dry_run: bool — if True, run without DB insert (default: False)
            tickers: list[str] — override watchlist tickers (default: from config)
        """
        from market.core.events import broker

        dry_run = event.payload.get("dry_run", False)
        source = event.payload.get("source", "scheduled")

        logger.info("Signal generation: starting (source=%s, dry_run=%s)", source, dry_run)

        cmd = [sys.executable, "scripts/daily_signal_cron.py"]
        if dry_run:
            cmd.append("--dry-run")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode == 0:
                logger.info("Signal generation: completed successfully")
                if result.stdout:
                    for line in result.stdout.strip().split("\n")[-5:]:
                        logger.info("  %s", line)
                broker.emit("signal.generate.completed", {
                    "success": True,
                    "source": source,
                    "dry_run": dry_run,
                })
            else:
                logger.warning("Signal generation: exited with code %d", result.returncode)
                if result.stderr:
                    logger.debug("stderr: %s", result.stderr[:500])
                broker.emit("signal.generate.completed", {
                    "success": False,
                    "source": source,
                    "error": f"Exit code {result.returncode}",
                })
        except subprocess.TimeoutExpired:
            logger.warning("Signal generation: timed out after 600s")
            broker.emit("signal.generate.completed", {
                "success": False,
                "source": source,
                "error": "Timeout after 600s",
            })
        except Exception as exc:
            logger.error("Signal generation: failed — %s", exc)
            broker.emit("signal.generate.completed", {
                "success": False,
                "source": source,
                "error": str(exc),
            })
