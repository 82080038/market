"""Event wiring — connects producers to consumers at startup.

This is the ONLY place where modules know about each other.
Each module registers its handlers here, and the broker routes events.
This replaces direct imports between modules.

Flow (decoupled — fetch does NOT auto-trigger recompute/export):

    PHASE 1 — FETCH (scheduler triggers each independently):
        data.fetch.requested           →  DataFetchPipeline → data.fetch.stored (IDX equities)
        data.fetch_global.requested    →  DataFetchPipeline → data.fetch.stored (global indices)
        data.fetch_commodity.requested →  DataFetchPipeline → data.fetch.stored (commodity futures)
        data.fetch_macro.requested     →  DataFetchPipeline → data.fetch.stored (macro rates → macro_data)
        data.fetch.intraday.requested  →  DataFetchPipeline → data.fetch.intraday.completed

    PHASE 2 — RECOMPUTE (scheduler triggers after all fetches done):
        data.recompute.requested      →  RecomputePipeline → data.recompute.completed

    PHASE 3 — EXPORT (scheduler triggers after recompute done):
        data.export.requested         →  ExportPipeline → data.export.completed

    PHASE 4 — HEALTH (after export):
        data.export.completed         →  HealthPipeline → health.check.completed
        health.check.requested        →  HealthPipeline

    PHASE 5 — ALERTS (after recompute):
        data.recompute.completed      →  AlertPipeline → alert.check.completed

    PHASE 6 — SIGNALS (scheduler triggers after recompute):
        signal.generate.requested     →  SignalPipeline → signal.generate.completed

    PHASE 7 — NOTIFICATIONS (terminal, after alerts and signals):
        alert.check.completed         →  NotificationPipeline (terminal)
        signal.generate.completed     →  NotificationPipeline (terminal)

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
    # Layer 1: IDX equities (emiten/saham)
    # Layer 2: Global indices (sentiment drivers)
    # Layer 3: Commodity futures (sector drivers)
    # Layer 4: Macro rates (→ macro_data table)
    # Layer 5: FX exchange rates (61 pairs: USD, IDR crosses, EUR crosses)
    # Layer 6: Intraday polling (15-min price snapshot)
    from market.pipelines.data_fetch import DataFetchPipeline

    fetch_pipeline = DataFetchPipeline()
    broker.subscribe("data.fetch.requested", fetch_pipeline.on_fetch_requested)
    broker.subscribe("data.fetch_global.requested", fetch_pipeline.on_fetch_global_requested)
    broker.subscribe("data.fetch_commodity.requested", fetch_pipeline.on_fetch_commodity_requested)
    broker.subscribe("data.fetch_macro.requested", fetch_pipeline.on_fetch_macro_requested)
    broker.subscribe("data.fetch_fx.requested", fetch_pipeline.on_fetch_fx_requested)
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

    # ── PHASE 5: Alert pipeline (after recompute) ───────────────
    # Listens to: data.recompute.completed
    # Emits:      alert.check.completed
    from market.pipelines.alerts import AlertPipeline

    alert_pipeline = AlertPipeline()
    broker.subscribe("data.recompute.completed", alert_pipeline.on_recompute_done)

    # ── PHASE 6: Signal pipeline (scheduler triggers after recompute) ──
    # Listens to: signal.generate.requested
    # Emits:      signal.generate.completed
    from market.pipelines.signal import SignalPipeline

    signal_pipeline = SignalPipeline()
    broker.subscribe("signal.generate.requested", signal_pipeline.on_signal_requested)

    # ── PHASE 7: Notification pipeline (terminal, after alerts/signals) ──
    # Listens to: alert.check.completed, signal.generate.completed
    # Emits:      (nothing — terminal node)
    from market.pipelines.notification import NotificationPipeline

    notification_pipeline = NotificationPipeline()
    broker.subscribe("alert.check.completed", notification_pipeline.on_alert_completed)
    broker.subscribe("signal.generate.completed", notification_pipeline.on_signal_completed)

    registered = broker.registered_events()
    logger.info("Event wiring complete: %d event types registered", len(registered))
    for evt in registered:
        logger.debug("  %s → %d handlers", evt, broker.handler_count(evt))
