"""Event wiring — connects producers to consumers at startup.

This is the ONLY place where modules know about each other.
Each module registers its handlers here, and the broker routes events.
This replaces direct imports between modules.

Flow (decoupled — fetch does NOT auto-trigger recompute/export):

    PHASE 1 — FETCH (scheduler triggers each independently):
        data.fetch.requested          →  DataFetchPipeline → data.fetch.stored
        data.fetch_global.requested   →  DataFetchPipeline → data.fetch.stored
        data.fetch_macro.requested    →  DataFetchPipeline → data.fetch.stored
        data.fetch.intraday.requested →  DataFetchPipeline → data.fetch.intraday.completed

    PHASE 2 — RECOMPUTE (scheduler triggers after all fetches done):
        data.recompute.requested      →  RecomputePipeline → data.recompute.completed

    PHASE 3 — EXPORT (scheduler triggers after recompute done):
        data.export.requested         →  ExportPipeline → data.export.completed

    PHASE 4 — HEALTH (after export):
        data.export.completed         →  HealthPipeline → health.check.completed
        health.check.requested        →  HealthPipeline

    ALERTS (after recompute):
        data.recompute.completed      →  AlertPipeline (terminal)

Key change: fetch phases emit "data.fetch.stored" (not "data.fetch.completed")
which does NOT auto-trigger recompute. This prevents 3-4x redundant recompute
and 5x redundant export per night. Recompute and export run ONCE each,
triggered by the scheduler after all fetches complete.

Usage (at application startup):
    from market.core.wiring import wire_all_events
    wire_all_events()
"""

from __future__ import annotations

import logging

from market.core.events import broker

logger = logging.getLogger(__name__)


def wire_all_events() -> None:
    """Register all event handlers with the broker.

    Call this once at application startup (CLI, API, scheduler).
    After this, modules communicate purely through events.
    """
    logger.info("Wiring event handlers...")

    # ── PHASE 1: Data fetch pipeline ────────────────────────────
    # Listens to: data.fetch.requested, data.fetch_global.requested,
    #             data.fetch_macro.requested, data.fetch.intraday.requested
    # Emits:      data.fetch.stored (eod/global/macro — no auto-recompute)
    #             data.fetch.intraday.completed (intraday — price snapshot)
    from market.pipelines.data_fetch import DataFetchPipeline

    fetch_pipeline = DataFetchPipeline()
    broker.subscribe("data.fetch.requested", fetch_pipeline.on_fetch_requested)
    broker.subscribe("data.fetch_global.requested", fetch_pipeline.on_fetch_global_requested)
    broker.subscribe("data.fetch_macro.requested", fetch_pipeline.on_fetch_macro_requested)
    broker.subscribe("data.fetch.intraday.requested", fetch_pipeline.on_intraday_requested)

    # ── PHASE 2: Recompute pipeline ─────────────────────────────
    # Listens to: data.recompute.requested (from scheduler, after all fetches)
    # Emits:      data.recompute.completed
    from market.pipelines.recompute import RecomputePipeline

    recompute_pipeline = RecomputePipeline()
    broker.subscribe("data.recompute.requested", recompute_pipeline.on_recompute_requested)

    # ── PHASE 3: Export pipeline ────────────────────────────────
    # Listens to: data.export.requested (from scheduler, after recompute)
    # Emits:      data.export.completed
    from market.pipelines.export import ExportPipeline

    export_pipeline = ExportPipeline()
    broker.subscribe("data.export.requested", export_pipeline.on_export_requested)

    # ── PHASE 4: Health pipeline ────────────────────────────────
    # Listens to: data.export.completed, health.check.requested
    # Emits:      health.check.completed
    from market.pipelines.health import HealthPipeline

    health_pipeline = HealthPipeline()
    broker.subscribe("data.export.completed", health_pipeline.on_export_done)
    broker.subscribe("health.check.requested", health_pipeline.on_check_requested)

    # ── Alerts: alert pipeline (after recompute) ────────────────
    # Listens to: data.recompute.completed
    # Emits:      (nothing — terminal node)
    from market.pipelines.alerts import AlertPipeline

    alert_pipeline = AlertPipeline()
    broker.subscribe("data.recompute.completed", alert_pipeline.on_recompute_done)

    registered = broker.registered_events()
    logger.info("Event wiring complete: %d event types registered", len(registered))
    for evt in registered:
        logger.debug("  %s → %d handlers", evt, broker.handler_count(evt))
