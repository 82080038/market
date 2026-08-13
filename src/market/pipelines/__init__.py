"""Pipeline layer: event-driven orchestrators.

Each pipeline is responsible for ONE domain and communicates
with other pipelines exclusively through the event broker.

Pipelines (decoupled — fetch does NOT auto-trigger recompute/export):
  data_fetch      — fetches external data, emits data.fetch.stored
  recompute       — recomputes indicators, emits data.recompute.completed
  export          — exports to parquet, emits data.export.completed
  health          — runs health checks, emits health.check.completed
  alerts          — checks alert conditions after recompute, emits alert.check.completed
  signal          — generates trading signals, emits signal.generate.completed
  notification    — persists alerts/signals to app_notifications (terminal)
"""
