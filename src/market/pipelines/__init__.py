"""Pipeline layer: event-driven orchestrators.

Each pipeline is responsible for ONE domain and communicates
with other pipelines exclusively through the event broker.

Pipelines:
  data_fetch  — fetches external data, emits data.fetch.completed
  recompute   — recomputes indicators, emits data.recompute.completed
  export      — exports to parquet, emits data.export.completed
  health      — runs health checks, emits health.check.completed
  alerts      — checks for alert conditions after recompute
"""
