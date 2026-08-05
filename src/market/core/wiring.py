"""Event wiring — connects producers to consumers at startup.

This is the ONLY place where modules know about each other.
Each module registers its handlers here, and the broker routes events.
This replaces direct imports between modules.

Flow (event-driven, no direct coupling):
    scheduler emits → data pipeline fetches → analysis pipeline recomputes
    → export pipeline backs up → health pipeline checks

    data.fetch.requested     →  DataFetchPipeline.handle_fetch()
    data.fetch.completed     →  RecomputePipeline.handle_recompute()
    data.recompute.completed →  ExportPipeline.handle_export()
    data.export.completed    →  HealthPipeline.handle_health_check()

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

    # ── Data layer: fetch pipeline ──────────────────────────────
    # Listens to: data.fetch.requested
    # Emits:      data.fetch.completed
    from market.pipelines.data_fetch import DataFetchPipeline

    fetch_pipeline = DataFetchPipeline()
    broker.subscribe("data.fetch.requested", fetch_pipeline.on_fetch_requested)
    broker.subscribe("data.fetch_global.requested", fetch_pipeline.on_fetch_global_requested)
    broker.subscribe("data.fetch_macro.requested", fetch_pipeline.on_fetch_macro_requested)
    broker.subscribe("data.fetch.intraday.requested", fetch_pipeline.on_intraday_requested)

    # ── Data layer: recompute pipeline ──────────────────────────
    # Listens to: data.fetch.completed
    # Emits:      data.recompute.completed
    from market.pipelines.recompute import RecomputePipeline

    recompute_pipeline = RecomputePipeline()
    broker.subscribe("data.fetch.completed", recompute_pipeline.on_data_fetched)

    # ── Infrastructure: export pipeline ─────────────────────────
    # Listens to: data.recompute.completed
    # Emits:      data.export.completed
    from market.pipelines.export import ExportPipeline

    export_pipeline = ExportPipeline()
    broker.subscribe("data.recompute.completed", export_pipeline.on_recompute_done)
    broker.subscribe("data.export.requested", export_pipeline.on_export_requested)

    # ── Infrastructure: health pipeline ─────────────────────────
    # Listens to: data.export.completed
    # Emits:      health.check.completed
    from market.pipelines.health import HealthPipeline

    health_pipeline = HealthPipeline()
    broker.subscribe("data.export.completed", health_pipeline.on_export_done)
    broker.subscribe("health.check.requested", health_pipeline.on_check_requested)

    # ── Analysis layer: alert pipeline ──────────────────────────
    # Listens to: data.recompute.completed
    # Emits:      (nothing — terminal node)
    from market.pipelines.alerts import AlertPipeline

    alert_pipeline = AlertPipeline()
    broker.subscribe("data.recompute.completed", alert_pipeline.on_recompute_done)

    registered = broker.registered_events()
    logger.info("Event wiring complete: %d event types registered", len(registered))
    for evt in registered:
        logger.debug("  %s → %d handlers", evt, broker.handler_count(evt))
