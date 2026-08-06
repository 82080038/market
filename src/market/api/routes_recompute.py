"""WebSocket endpoint for recompute progress streaming + dashboard HTML.

Provides real-time BE→FE visibility for recompute_internal pipeline.

5W1H:
  WHO:   Single-user trading application (personal)
  WHAT:  Recompute 7 internal analysis tables from OHLCV raw data
  WHEN:  On-demand (after data cleanup or schema change)
  WHERE: Backend (Python/SQLAlchemy) → WebSocket → Frontend (HTML/Alpine.js)
  WHY:   Replace stale migrated parquet data with freshly computed values
  HOW:   Each engine reads OHLCV from SQLite, computes indicators/scores/labels,
         writes results back to SQLite. Progress streamed via WebSocket.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from market.db.engine import get_sessionmaker
from market.data.recompute_internal import run_all_recompute

router = APIRouter(tags=["recompute"])


@router.get("/recompute", response_class=HTMLResponse)
async def recompute_dashboard() -> str:
    """Serve the recompute progress dashboard (Alpine.js, no build step)."""
    return _DASHBOARD_HTML


@router.get("/api/recompute/stats")
async def recompute_stats() -> JSONResponse:
    """Get current DB table row counts for before/after comparison."""
    conn = sqlite3.connect("data/market_research.db")
    c = conn.cursor()
    c.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%' "
        "ORDER BY name"
    )
    tables = [r[0] for r in c.fetchall()]
    stats: dict[str, int] = {}
    for t in tables:
        c.execute(f"SELECT COUNT(*) FROM [{t}]")
        stats[t] = c.fetchone()[0]
    conn.close()
    return JSONResponse({"tables": stats, "timestamp": datetime.now(UTC).isoformat()})


@router.websocket("/ws/recompute")
async def ws_recompute(websocket: WebSocket) -> None:
    """WebSocket endpoint that runs recompute_internal and streams progress.

    Query params:
        mode: "incremental" (default) or "full"
    """
    await websocket.accept()

    # Read mode from query params
    mode = websocket.query_params.get("mode", "incremental")
    incremental = mode == "incremental"

    await websocket.send_json({
        "type": "status",
        "status": "starting",
        "mode": mode,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    async def progress_cb(step: str, current: int, total: int, message: str) -> None:
        msg = {
            "type": "progress",
            "step": step,
            "current": current,
            "total": total,
            "message": message,
            "mode": mode,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            await websocket.send_json(msg)
        except Exception:
            pass

    loop = asyncio.get_event_loop()

    def _run_recompute() -> dict[str, int]:
        session = get_sessionmaker()()
        try:
            def sync_progress_cb(step: str, current: int, total: int, message: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    progress_cb(step, current, total, message), loop
                )

            return run_all_recompute(
                session, dry_run=False,
                progress_cb=sync_progress_cb,
                incremental=incremental,
            )
        finally:
            session.close()

    try:
        await websocket.send_json({
            "type": "status",
            "status": "running",
            "mode": mode,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        results = await loop.run_in_executor(None, _run_recompute)

        await websocket.send_json({
            "type": "complete",
            "results": results,
            "timestamp": datetime.now(UTC).isoformat(),
        })
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({
            "type": "error",
            "message": str(exc),
            "timestamp": datetime.now(UTC).isoformat(),
        })
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Dashboard HTML ─────────────────────────────────────────────────────────

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Recompute Pipeline — Market Trading App</title>
<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #0f172a; --card: #1e293b; --border: #334155;
  --text: #e2e8f0; --muted: #94a3b8; --dim: #64748b;
  --green: #22c55e; --red: #ef4444; --yellow: #eab923; --blue: #3b82f6;
  --purple: #a78bfa; --cyan: #22d3ee; --orange: #f97316;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text);
  font-family: 'Segoe UI', system-ui, sans-serif; padding: 0;
  max-width: 1400px; margin: 0 auto;
}
h1 { font-size: 1.3rem; margin-bottom: 0.15rem; }
h2 { font-size: 1rem; margin: 1rem 0 0.5rem; }
h2.collapsible { cursor: pointer; user-select: none; display: flex; align-items: center; gap: 0.3rem; }
h2.collapsible:hover { color: var(--blue); }
h2.collapsible .chevron { font-size: 0.7rem; transition: transform 0.2s ease; }
h2.collapsible.collapsed .chevron { transform: rotate(-90deg); }
.subtitle { color: var(--muted); font-size: 0.75rem; margin-bottom: 0.5rem; }

/* Sticky header */
.sticky-header {
  position: sticky; top: 0; z-index: 100;
  background: var(--bg); border-bottom: 1px solid var(--border);
  padding: 0.75rem 1.5rem; margin: -0.75rem -1.5rem 0;
}
.sticky-header h1 { margin: 0; }
.sticky-header .subtitle { margin: 0; }

/* Content wrapper */
.content { padding: 0 1.5rem 1.5rem; }

/* Collapsible section */
.collapse-body { overflow: hidden; transition: max-height 0.3s ease, opacity 0.2s ease, margin 0.2s ease; }
.collapse-body.collapsed { max-height: 0; opacity: 0; margin: 0; pointer-events: none; }
.collapse-body.expanded { max-height: 9999px; opacity: 1; }

/* KPI cards */
.kpi-row {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 0.5rem; margin-bottom: 0.75rem;
}
.kpi {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 0.5rem; padding: 0.5rem 0.75rem; position: relative; overflow: hidden;
}
.kpi .label { font-size: 0.6rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.kpi .value { font-size: 1.2rem; font-weight: 700; margin-top: 0.1rem; }
.kpi .sub { font-size: 0.6rem; color: var(--dim); margin-top: 0.05rem; }
.kpi .icon { position: absolute; top: 0.35rem; right: 0.5rem; font-size: 1rem; opacity: 0.25; }
.kpi.green .value { color: var(--green); }
.kpi.blue .value { color: var(--blue); }
.kpi.yellow .value { color: var(--yellow); }
.kpi.cyan .value { color: var(--cyan); }
.kpi.red .value { color: var(--red); }
.kpi.purple .value { color: var(--purple); }

/* Charts */
.charts-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem;
}
@media (max-width: 900px) { .charts-row { grid-template-columns: 1fr; } }
.chart-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 0.5rem; padding: 0.75rem;
}
.chart-card h3 { font-size: 0.75rem; color: var(--muted); margin-bottom: 0.4rem; }
.chart-container { position: relative; height: 140px; }

/* 5W1H */
.w5h {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 0.5rem; padding: 0.75rem; margin-bottom: 0.75rem;
}
.w5h-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.5rem;
}
.w5h-item { font-size: 0.7rem; }
.w5h-item .label { color: var(--cyan); font-weight: 600; text-transform: uppercase; font-size: 0.6rem; }
.w5h-item .value { color: var(--text); margin-top: 0.1rem; }

/* DB stats */
.db-stats {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.4rem; margin-bottom: 0.75rem;
}
.db-stat {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 0.4rem; padding: 0.4rem 0.6rem; font-size: 0.7rem;
  transition: border-color 0.3s ease;
}
.db-stat:hover { border-color: var(--blue); }
.db-stat .name { color: var(--muted); }
.db-stat .count { font-size: 0.9rem; font-weight: 600; }
.db-stat .delta { font-size: 0.65rem; }
.db-stat .delta.pos { color: var(--green); }
.db-stat .delta.neg { color: var(--red); }
.db-stat.changed { border-color: var(--green); }

/* Controls */
.controls {
  display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; flex-wrap: wrap;
}
button {
  background: var(--blue); color: white; border: none;
  padding: 0.4rem 1.2rem; border-radius: 0.4rem; cursor: pointer;
  font-size: 0.8rem; font-weight: 600; transition: background 0.2s ease;
}
button:hover { background: #2563eb; }
button:disabled { background: var(--border); cursor: not-allowed; }
button.secondary { background: var(--border); }
button.secondary:hover { background: var(--dim); }

.status-badge {
  display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px;
  font-size: 0.75rem; font-weight: 600;
}
.status-badge.idle { background: var(--border); color: var(--muted); }
.status-badge.running { background: rgba(59,130,246,0.2); color: var(--blue); }
.status-badge.done { background: rgba(34,197,94,0.2); color: var(--green); }
.status-badge.error { background: rgba(239,68,68,0.2); color: var(--red); }
.timer { font-family: 'Cascadia Code', monospace; font-size: 0.8rem; color: var(--muted); }
.timer .elapsed { color: var(--yellow); font-weight: 600; }
.timer .eta { color: var(--cyan); }

/* Step cards */
.grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 0.75rem; margin-bottom: 0.75rem;
}
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 0.5rem; padding: 0.75rem; transition: border-color 0.3s ease, box-shadow 0.3s ease;
  scroll-margin-top: 200px;
}
.card.active {
  border-color: var(--blue); box-shadow: 0 0 0 2px rgba(59,130,246,0.4), 0 4px 20px rgba(59,130,246,0.15);
  animation: cardFocus 0.4s ease;
}
@keyframes cardFocus {
  0% { transform: scale(1); }
  50% { transform: scale(1.02); }
  100% { transform: scale(1); }
}
.card-title {
  font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem;
  display: flex; align-items: center; gap: 0.5rem;
}
.card-title .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--dim); }
.card-title .dot.running { background: var(--blue); animation: pulse 1s infinite; }
.card-title .dot.done { background: var(--green); }
.card-title .dot.failed { background: var(--red); }
.card-title .num {
  font-size: 0.65rem; color: var(--dim); background: var(--bg);
  padding: 0.1rem 0.4rem; border-radius: 0.25rem;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
.card-desc { font-size: 0.7rem; color: var(--muted); margin-bottom: 0.5rem; line-height: 1.4; }
.card-desc .field { display: flex; gap: 0.3rem; margin-bottom: 0.15rem; }
.card-desc .field .k { color: var(--purple); min-width: 45px; font-weight: 600; }
.card-desc .field .v { color: var(--text); }
.progress-bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; margin: 0.5rem 0; }
.progress-fill { height: 100%; background: var(--blue); transition: width 0.3s ease; }
.progress-fill.done { background: var(--green); }
.progress-fill.failed { background: var(--red); }
.progress-text { font-size: 0.7rem; color: var(--muted); display: flex; justify-content: space-between; }
.progress-text .pct { font-weight: 600; color: var(--text); }

/* Sparkline */
.sparkline { height: 24px; margin: 0.25rem 0; }

/* Log */
.log {
  background: #0d1117; border: 1px solid var(--border);
  border-radius: 0.4rem; padding: 0.5rem;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 0.65rem; max-height: 150px; overflow-y: auto; line-height: 1.4;
}
.log .entry { padding: 0.1rem 0; }
.log .entry .ts { color: var(--dim); }
.log .entry .step { color: var(--blue); font-weight: 600; }
.log .entry .msg { color: var(--text); }
.log .entry.error .msg { color: var(--red); }
.log .entry.complete .msg { color: var(--green); }

/* Summary */
.summary table { width: 100%; border-collapse: collapse; }
.summary th, .summary td {
  padding: 0.5rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.75rem;
}
.summary th { color: var(--muted); font-weight: 600; }
.summary td .ok { color: var(--green); }
.summary td .fail { color: var(--red); }

/* Warning */
.warn {
  background: rgba(234,185,35,0.1); border: 1px solid rgba(234,185,35,0.3);
  border-radius: 0.4rem; padding: 0.5rem 0.75rem; margin-bottom: 0.5rem;
  font-size: 0.7rem; color: var(--yellow);
}

/* Pipeline flow diagram */
.flow {
  display: flex; align-items: center; gap: 0; margin-bottom: 0.75rem;
  overflow-x: auto; padding: 0.25rem 0;
}
.flow-step {
  flex: 1; min-width: 90px; text-align: center; position: relative;
  font-size: 0.6rem; padding: 0.35rem; border-radius: 0.4rem;
  background: var(--card); border: 1px solid var(--border);
  transition: all 0.3s ease;
}
.flow-step.active { border-color: var(--blue); background: rgba(59,130,246,0.1); }
.flow-step.done { border-color: var(--green); background: rgba(34,197,94,0.1); }
.flow-step.failed { border-color: var(--red); background: rgba(239,68,68,0.1); }
.flow-step .name { font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.flow-step .pct { font-size: 0.6rem; color: var(--muted); margin-top: 0.15rem; }
.flow-arrow { color: var(--dim); font-size: 0.8rem; padding: 0 0.25rem; flex-shrink: 0; }
.flow-arrow.active { color: var(--blue); }
.flow-arrow.done { color: var(--green); }

/* Collapsible */
.collapsible-content { overflow: hidden; transition: max-height 0.3s ease; }

/* Mode selector */
.mode-selector { display: inline-flex; gap: 0; margin-left: 0.5rem; border: 1px solid var(--border); border-radius: 0.4rem; overflow: hidden; }
.mode-btn { font-size: 0.7rem; padding: 0.35rem 0.75rem; border: none; background: var(--card); color: var(--muted); cursor: pointer; transition: all 0.2s; }
.mode-btn:hover { color: var(--text); }
.mode-btn.active { font-weight: 600; }
.mode-btn.incremental.active { background: rgba(34,197,94,0.2); color: var(--green); }
.mode-btn.full.active { background: rgba(239,68,68,0.2); color: var(--red); }
button.incremental { border-left: 3px solid var(--green); }
button.full { border-left: 3px solid var(--red); }
</style>
</head>
<body x-data="dashboard()" x-init="init()">

<!-- STICKY HEADER: always visible -->
<div class="sticky-header">
  <h1>Recompute Pipeline Dashboard</h1>
  <p class="subtitle">
    Recompute 7 tabel analisis internal dari OHLCV mentah di SQLite (6.1 GB).
    <span class="status-badge" :class="status" x-text="status.toUpperCase()"></span>
    <span class="timer" x-show="status === 'running'">
      &middot; <span class="elapsed" x-text="elapsedStr"></span>
      &middot; <span class="eta" x-text="etaStr"></span>
    </span>
  </p>
  <div class="controls">
    <button @click="start()" :disabled="status === 'running'"
      x-text="status === 'running' ? 'Running...' : 'Start Recompute'"
      :class="mode"></button>
    <button @click="loadStats()" :disabled="status === 'running'" class="secondary">Refresh Stats</button>
    <button @click="togglePause()" x-show="status === 'running'" class="secondary"
      x-text="paused ? 'Resume Log' : 'Pause Log'"></button>
    <span class="mode-selector">
      <button @click="setMode('incremental')" :disabled="status === 'running'"
        :class="mode === 'incremental' ? 'active' : ''" class="mode-btn incremental">Incremental</button>
      <button @click="setMode('full')" :disabled="status === 'running'"
        :class="mode === 'full' ? 'active' : ''" class="mode-btn full">Full</button>
    </span>
  </div>
  <!-- KPI Cards inline in header -->
  <div class="kpi-row">
    <div class="kpi blue"><div class="label">Total Rows</div><div class="value" x-text="formatNum(totalRows)"></div><div class="sub" x-text="totalRows > 0 ? completedSteps + '/7 done' : 'idle'"></div><div class="icon">&#128202;</div></div>
    <div class="kpi cyan"><div class="label">Throughput</div><div class="value" x-text="throughputStr"></div><div class="sub">rows/sec</div><div class="icon">&#9889;</div></div>
    <div class="kpi yellow"><div class="label">Elapsed</div><div class="value" x-text="elapsedStr"></div><div class="sub" x-text="status === 'running' ? 'running' : ''"></div><div class="icon">&#9201;</div></div>
    <div class="kpi purple"><div class="label">ETA</div><div class="value" x-text="etaStr"></div><div class="sub" x-text="eta > 0 ? 'remaining' : ''"></div><div class="icon">&#128338;</div></div>
    <div class="kpi green"><div class="label">Success</div><div class="value" x-text="successCount + '/7'"></div><div class="sub" x-show="successCount > 0">completed</div><div class="icon">&#9989;</div></div>
    <div class="kpi red"><div class="label">Errors</div><div class="value" x-text="errorCount"></div><div class="sub" x-show="errorCount > 0">failed</div><div class="icon">&#10060;</div></div>
  </div>
  <!-- Charts inline in header -->
  <div class="charts-row">
    <div class="chart-card"><h3>Throughput (rows/sec)</h3><div class="chart-container"><canvas x-ref="throughputChart"></canvas></div></div>
    <div class="chart-card"><h3>Rows per Step</h3><div class="chart-container"><canvas x-ref="stepChart"></canvas></div></div>
  </div>
  <!-- Pipeline flow inline in header -->
  <div class="flow">
    <template x-for="(step, idx) in steps" :key="step.name">
      <div style="display:flex;align-items:center;flex:1;min-width:0">
        <div class="flow-step" :class="step.state">
          <div class="name" x-text="step.title"></div>
          <div class="pct" x-text="step.total > 0 ? Math.round(step.current/step.total*100) + '%' : (step.state === 'done' ? '100%' : '0%')"></div>
        </div>
        <span class="flow-arrow" :class="step.state === 'done' ? 'done' : (idx < currentStepIdx ? 'done' : '')" x-show="idx < steps.length - 1">&rarr;</span>
      </div>
    </template>
  </div>
</div>

<!-- SCROLLABLE CONTENT -->
<div class="content">

<!-- Warning -->
<div class="warn" x-show="status === 'idle' && mode === 'full'">
  &#9888; <b>Full mode:</b> Pipeline akan MENGHAPUS dan menghitung ulang 7 tabel: technical_indicators, scores,
  relationship_matrix, fear_greed, stock_personality, ml_labels, market_regimes.
  Data lama akan hilang dan diganti dengan hasil komputasi baru. ~56 menit untuk ml_labels.
</div>
<div class="warn" style="border-color: rgba(34,197,94,0.3); background: rgba(34,197,94,0.1); color: var(--green);" x-show="status === 'idle' && mode === 'incremental'">
  &#9989; <b>Incremental mode:</b> Hanya append tanggal baru untuk fear_greed, ml_labels, market_regimes.
  Snapshot tables (technical_indicators, scores, relationship_matrix, stock_personality) tetap full recompute (cepat).
  Estimasi &lt; 2 menit untuk data harian baru.
</div>

<!-- 5W1H (collapsible, collapsed by default) -->
<h2 class="collapsible" :class="sections.w5h ? '' : 'collapsed'" @click="toggleSection('w5h')">
  <span class="chevron">&#9660;</span> 5W1H &mdash; Apa yang dilakukan pipeline ini?
</h2>
<div class="collapse-body" :class="sections.w5h ? 'expanded' : 'collapsed'">
  <div class="w5h">
    <div class="w5h-grid">
      <div class="w5h-item"><div class="label">Who</div><div class="value">Single-user trading app (personal)</div></div>
      <div class="w5h-item"><div class="label">What</div><div class="value">Recompute 7 tabel analisis dari OHLCV mentah di SQLite (3M+ rows)</div></div>
      <div class="w5h-item"><div class="label">When</div><div class="value">On-demand: setelah data cleanup atau schema change</div></div>
      <div class="w5h-item"><div class="label">Where</div><div class="value">Backend Python &rarr; WebSocket &rarr; Dashboard HTML</div></div>
      <div class="w5h-item"><div class="label">Why</div><div class="value">Replace data parquet lama dengan hasil komputasi fresh dari app sendiri</div></div>
      <div class="w5h-item"><div class="label">How</div><div class="value">Setiap engine baca OHLCV, hitung indikator/score/label, tulis kembali ke SQLite</div></div>
    </div>
  </div>
</div>

<!-- DB Stats (collapsible) -->
<h2 class="collapsible" :class="sections.dbStats ? '' : 'collapsed'" @click="toggleSection('dbStats')">
  <span class="chevron">&#9660;</span> Database Table Stats
  <span style="font-size:0.7rem;color:var(--muted)" x-text="statsTs ? '&middot; ' + formatTime(statsTs) : ''"></span>
</h2>
<div class="collapse-body" :class="sections.dbStats ? 'expanded' : 'collapsed'">
  <div class="db-stats">
    <template x-for="(count, name) in dbStats" :key="name">
      <div class="db-stat" :class="afterStats && afterStats[name] !== undefined && afterStats[name] !== count ? 'changed' : ''">
        <div class="name" x-text="name"></div>
        <div class="count" x-text="formatNum(count)"></div>
        <div class="delta" x-show="afterStats && afterStats[name] !== undefined"
          :class="(afterStats[name] - count) > 0 ? 'pos' : 'neg'"
          x-text="afterStats && afterStats[name] !== undefined ? ((afterStats[name] - count) > 0 ? '+' : '') + formatNum(afterStats[name] - count) : ''">
        </div>
      </div>
    </template>
  </div>
</div>

<!-- Step cards (always expanded — this is the focus area) -->
<h2 class="collapsible" :class="sections.steps ? '' : 'collapsed'" @click="toggleSection('steps')">
  <span class="chevron">&#9660;</span> Pipeline Steps Detail (7 stages)
</h2>
<div class="collapse-body" :class="sections.steps ? 'expanded' : 'collapsed'">
  <div class="grid">
    <template x-for="(step, idx) in steps" :key="step.name">
      <div class="card" :class="step.state === 'running' ? 'active' : ''" :id="'step-' + step.name">
        <div class="card-title">
          <span class="dot" :class="step.state"></span>
          <span x-text="step.title"></span>
          <span class="num" x-text="'Step ' + (idx + 1) + '/7'"></span>
        </div>
        <div class="card-desc">
          <div class="field"><span class="k">What</span><span class="v" x-text="step.what"></span></div>
          <div class="field"><span class="k">Why</span><span class="v" x-text="step.why"></span></div>
          <div class="field"><span class="k">How</span><span class="v" x-text="step.how"></span></div>
          <div class="field"><span class="k">Output</span><span class="v" x-text="step.output"></span></div>
          <div class="field"><span class="k">Est</span><span class="v" x-text="step.est"></span></div>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :class="step.state"
            :style="`width: ${step.total > 0 ? Math.min(100, step.current / step.total * 100) : 0}%`">
          </div>
        </div>
        <div class="progress-text">
          <span>
            <span class="pct" x-text="step.total > 0 ? Math.round(step.current / step.total * 100) + '%' : '&mdash;'"></span>
            &middot; <span x-text="step.current + ' / ' + step.total"></span>
          </span>
          <span x-text="step.message"></span>
        </div>
      </div>
    </template>
  </div>
</div>

<!-- Live Log (collapsible) -->
<h2 class="collapsible" :class="sections.log ? '' : 'collapsed'" @click="toggleSection('log')">
  <span class="chevron">&#9660;</span> Live Log
  <span style="font-size:0.7rem;color:var(--muted)" x-show="logs.length > 0" x-text="'&middot; ' + logs.length + ' entries'"></span>
</h2>
<div class="collapse-body" :class="sections.log ? 'expanded' : 'collapsed'">
  <div class="card" style="margin-bottom:0.75rem">
    <div class="log" x-ref="log">
      <template x-for="(entry, idx) in logs" :key="idx">
        <div class="entry" :class="entry.type">
          <span class="ts" x-text="formatTime(entry.timestamp)"></span>
          <span class="step" x-text="entry.step ? '[' + entry.step + ']' : ''"></span>
          <span class="msg" x-text="entry.message"></span>
        </div>
      </template>
    </div>
  </div>
</div>

<!-- Summary + DB Comparison Chart (auto-show when done) -->
<div class="charts-row" x-show="results !== null" style="margin-top:0.75rem">
  <div class="chart-card">
    <h3>DB Row Count: Before vs After Recompute</h3>
    <div class="chart-container"><canvas x-ref="compareChart"></canvas></div>
  </div>
  <div class="card summary">
    <h2 style="margin-top:0">Final Summary</h2>
    <table>
      <thead><tr><th>Step</th><th>Rows</th><th>Status</th><th>Est</th></tr></thead>
      <tbody>
        <template x-for="(count, name) in (results || {})" :key="name">
          <tr>
            <td x-text="name"></td>
            <td x-text="count >= 0 ? formatNum(count) : 'FAILED'"></td>
            <td><span :class="count >= 0 ? 'ok' : 'fail'" x-text="count >= 0 ? 'OK' : 'ERROR'"></span></td>
            <td x-text="stepInfo[name]?.est || ''"></td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</div>

</div><!-- /content -->

<script>
const STEP_INFO = {
  technical_indicators: {
    title: "Technical Indicators",
    what: "MA20, MA50, RSI, MACD, ADX, ATR, Bollinger Bands, Volume SMA",
    why: "Indikator teknikal untuk scoring & sinyal trading",
    how: "TechnicalAnalysisEngine.analyze() per ticker dari OHLCV",
    output: "technical_indicators (10 indikator x ~986 tickers)",
    est: "~9,800 rows",
  },
  scores: {
    title: "Six-Factor Scores",
    what: "Technical, Fundamental, Macro, Global, Relationship, Sentiment (0-100)",
    why: "Composite scoring untuk screening & rekomendasi saham",
    how: "6 analysis engines -> DecisionEngine per ticker",
    output: "scores (6 engine x ~986 tickers)",
    est: "~5,900 rows",
  },
  relationship_matrix: {
    title: "Relationship Matrix",
    what: "Korelasi & lag saham vs 13 aset referensi (5 window: 30/60/90/180/360)",
    why: "Mengukur pengaruh pasar global & makro terhadap saham IDX",
    how: "MarketRelationshipEngine per ticker x per window",
    output: "relationship_matrix (986 x 13 x 5 = ~64K pairs)",
    est: "~64,000 rows",
  },
  fear_greed: {
    title: "Fear & Greed Index",
    what: "Sentimen pasar harian (0=Extreme Fear -> 100=Extreme Greed)",
    why: "Gauge sentimen untuk timing entry/exit",
    how: "Composite momentum + volatility + volume dari IHSG",
    output: "fear_greed (~1,178 hari)",
    est: "~1,178 rows",
  },
  stock_personality: {
    title: "Stock Personality",
    what: "Volatility regime, trend bias, beta vs IHSG, liquidity, personality label",
    why: "Klasifikasi karakter saham untuk strategi selection",
    how: "InstrumentProfiler.profile() per ticker",
    output: "stock_personality (~986 tickers)",
    est: "~986 rows",
  },
  ml_labels: {
    title: "ML Triple-Barrier Labels",
    what: "Label supervised: up/down/static dengan barrier TP/SL/time",
    why: "Training data untuk model ML prediksi arah harga",
    how: "Triple-barrier (2x ATR14, horizon 1/5/10/21 hari) per ticker",
    output: "ml_labels (~986 tickers x ~1000 hari x 4 horizon)",
    est: "~2-4 juta rows (paling berat)",
  },
  market_regimes: {
    title: "Market Regime Labels",
    what: "Regime pasar harian: bull / bear / sideways / crisis",
    why: "Konteks makro untuk adaptive strategy & position sizing",
    how: "Heuristic: MA50/MA200 IHSG + volatility + VIX + F&G + foreign flow",
    output: "market_regimes (~998 hari)",
    est: "~998 rows",
  },
};

// Chart instances kept outside Alpine reactivity
let throughputChart = null;
let stepChart = null;
let compareChart = null;

const CHART_COLORS = ['#3b82f6','#22c55e','#a78bfa','#22d3ee','#eab923','#f97316','#ef4444'];

function dashboard() {
  return {
    status: 'idle',
    mode: 'incremental',
    steps: Object.entries(STEP_INFO).map(([name, info]) => ({
      name, ...info, current: 0, total: 0, message: '', state: ''
    })),
    stepInfo: STEP_INFO,
    logs: [],
    results: null,
    ws: null,
    dbStats: {},
    afterStats: null,
    statsTs: null,
    startTime: null,
    elapsed: 0,
    eta: 0,
    paused: false,
    get modeLabel() {
      return this.mode === 'incremental' ? 'Incremental (append new dates)' : 'Full (DELETE + recompute all)';
    },
    _timer: null,
    _throughputHistory: [],
    _lastProgressTs: null,
    _lastProgressTotal: 0,
    _lastActiveStep: null,
    sections: { w5h: false, dbStats: false, steps: true, log: true },

    // Computed
    get totalRows() {
      return this.steps.reduce((sum, s) => sum + (s.state === 'done' ? s.current : 0), 0);
    },
    get throughputStr() {
      if (this._throughputHistory.length < 2) return '0';
      const recent = this._throughputHistory.slice(-5);
      const avg = recent.reduce((a, b) => a + b.v, 0) / recent.length;
      return avg > 0 ? formatNum(Math.round(avg)) : '0';
    },
    get elapsedStr() {
      const m = Math.floor(this.elapsed / 60), s = this.elapsed % 60;
      return `${m}m ${s}s`;
    },
    get etaStr() {
      if (this.eta <= 0) return '--';
      const m = Math.floor(this.eta / 60), s = this.eta % 60;
      return `${m}m ${s}s`;
    },
    get successCount() { return this.steps.filter(s => s.state === 'done').length; },
    get errorCount() { return this.steps.filter(s => s.state === 'failed').length; },
    get completedSteps() { return this.steps.filter(s => s.state === 'done' || s.state === 'failed').length; },
    get currentStepIdx() { return this.steps.findIndex(s => s.state === 'running'); },

    // Init
    async init() {
      await this.loadStats();
      this.$nextTick(() => this.initCharts());
    },

    initCharts() {
      const tCtx = this.$refs.throughputChart;
      if (tCtx) {
        throughputChart = new Chart(tCtx, {
          type: 'line',
          data: { labels: [], datasets: [{
            label: 'rows/sec', data: [], borderColor: '#22d3ee',
            backgroundColor: 'rgba(34,211,238,0.1)', fill: true, tension: 0.3,
            pointRadius: 0, borderWidth: 2,
          }]},
          options: {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 300 },
            scales: {
              x: { display: false },
              y: { ticks: { color: '#64748b', font: { size: 9 } }, grid: { color: '#1e293b' } },
            },
            plugins: { legend: { display: false } },
          },
        });
      }
      const sCtx = this.$refs.stepChart;
      if (sCtx) {
        stepChart = new Chart(sCtx, {
          type: 'bar',
          data: { labels: this.steps.map(s => s.title), datasets: [{
            label: 'rows', data: this.steps.map(() => 0),
            backgroundColor: CHART_COLORS, borderRadius: 4,
          }]},
          options: {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 400 },
            scales: {
              x: { ticks: { color: '#64748b', font: { size: 8 }, maxRotation: 45, minRotation: 45 }, grid: { display: false } },
              y: { ticks: { color: '#64748b', font: { size: 9 }, callback: v => v >= 1000 ? (v/1000)+'k' : v }, grid: { color: '#1e293b' } },
            },
            plugins: { legend: { display: false } },
          },
        });
      }
    },

    initCompareChart() {
      const cCtx = this.$refs.compareChart;
      if (!cCtx || !this.afterStats) return;
      const targetTables = ['technical_indicators','scores','relationship_matrix','fear_greed','stock_personality','ml_labels','market_regimes'];
      const labels = targetTables;
      const before = targetTables.map(t => this.dbStats[t] || 0);
      const after = targetTables.map(t => this.afterStats[t] || 0);
      if (compareChart) compareChart.destroy();
      compareChart = new Chart(cCtx, {
        type: 'bar',
        data: { labels, datasets: [
          { label: 'Before', data: before, backgroundColor: '#64748b', borderRadius: 4 },
          { label: 'After', data: after, backgroundColor: '#22c55e', borderRadius: 4 },
        ]},
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: { duration: 500 },
          scales: {
            x: { ticks: { color: '#64748b', font: { size: 8 }, maxRotation: 45, minRotation: 45 }, grid: { display: false } },
            y: { type: 'logarithmic', ticks: { color: '#64748b', font: { size: 9 } }, grid: { color: '#1e293b' } },
          },
          plugins: { legend: { labels: { color: '#94a3b8', font: { size: 10 } } } },
        },
      });
    },

    // Stats
    async loadStats() {
      try {
        const r = await fetch('/api/recompute/stats');
        const d = await r.json();
        this.dbStats = d.tables;
        this.statsTs = d.timestamp;
      } catch (e) { console.error('Failed to load stats:', e); }
    },
    async loadAfterStats() {
      try {
        const r = await fetch('/api/recompute/stats');
        const d = await r.json();
        this.afterStats = d.tables;
        this.$nextTick(() => this.initCompareChart());
      } catch (e) {}
    },

    // Pause
    togglePause() { this.paused = !this.paused; },

    // Mode selector
    setMode(m) { if (this.status !== 'running') this.mode = m; },

    // Collapsible sections
    toggleSection(name) { this.sections[name] = !this.sections[name]; },

    // Auto-scroll active step card to center of viewport
    scrollToActiveStep(stepName) {
      if (stepName === this._lastActiveStep) return;
      this._lastActiveStep = stepName;
      this.$nextTick(() => {
        const el = document.getElementById('step-' + stepName);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    },

    // Start
    start() {
      this.status = 'running';
      this.results = null;
      this.afterStats = null;
      this.logs = [];
      this.elapsed = 0;
      this.eta = 0;
      this.paused = false;
      this._throughputHistory = [];
      this._lastProgressTs = null;
      this._lastProgressTotal = 0;
      this.startTime = Date.now();
      this.steps.forEach(s => { s.current = 0; s.total = 0; s.message = ''; s.state = ''; });
      // Reset charts
      if (throughputChart) {
        throughputChart.data.labels.length = 0;
        throughputChart.data.datasets[0].data.length = 0;
        throughputChart.update();
      }
      if (stepChart) {
        stepChart.data.datasets[0].data = this.steps.map(() => 0);
        stepChart.update();
      }
      this._timer = setInterval(() => {
        this.elapsed = Math.floor((Date.now() - this.startTime) / 1000);
        // Sample throughput
        const totalNow = this.steps.reduce((a, s) => a + s.current, 0);
        const now = Date.now();
        if (this._lastProgressTs && totalNow > this._lastProgressTotal) {
          const dt = (now - this._lastProgressTs) / 1000;
          const dr = totalNow - this._lastProgressTotal;
          if (dt > 0) {
            const rps = dr / dt;
            this._throughputHistory.push({ t: now, v: rps });
            if (this._throughputHistory.length > 60) this._throughputHistory.shift();
            if (throughputChart) {
              throughputChart.data.labels.push('');
              throughputChart.data.datasets[0].data.push(Math.round(rps));
              if (throughputChart.data.labels.length > 60) {
                throughputChart.data.labels.shift();
                throughputChart.data.datasets[0].data.shift();
              }
              throughputChart.update('none');
            }
          }
        }
        this._lastProgressTs = now;
        this._lastProgressTotal = totalNow;
      }, 1000);
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.ws = new WebSocket(`${proto}//${location.host}/ws/recompute?mode=${this.mode}`);
      this.ws.onmessage = (e) => { this.handleMessage(JSON.parse(e.data)); };
      this.ws.onerror = () => {
        this.status = 'error';
        this.addLog('', 'WebSocket error - koneksi terputus', 'error');
        clearInterval(this._timer);
      };
      this.ws.onclose = () => {
        if (this.status === 'running') this.status = 'idle';
        clearInterval(this._timer);
      };
    },

    handleMessage(msg) {
      if (msg.type === 'status') {
        if (msg.mode) this.mode = msg.mode;
        this.addLog('', `Pipeline status: ${msg.status} (mode: ${msg.mode || this.mode})`, '');
      } else if (msg.type === 'progress') {
        const step = this.steps.find(s => s.name === msg.step);
        if (step) {
          step.current = msg.current;
          step.total = msg.total;
          step.message = msg.message;
          if (msg.current > 0 && msg.current < msg.total) {
            if (step.state !== 'running') {
              step.state = 'running';
              this.scrollToActiveStep(msg.step);
            } else {
              step.state = 'running';
            }
          }
          else if (msg.current >= msg.total && msg.total > 0) step.state = 'done';
          else if (msg.current < 0) step.state = 'failed';
          // ETA
          if (step.state === 'running' && step.total > 0 && step.current > 0 && this.elapsed > 0) {
            const rate = step.current / this.elapsed;
            if (rate > 0) this.eta = Math.floor((step.total - step.current) / rate);
          }
          // Update step bar chart
          if (stepChart) {
            const idx = this.steps.findIndex(s => s.name === msg.step);
            if (idx >= 0) {
              stepChart.data.datasets[0].data[idx] = step.current;
              stepChart.update('none');
            }
          }
        }
        this.addLog(msg.step, `${msg.current}/${msg.total} - ${msg.message}`, '');
      } else if (msg.type === 'complete') {
        this.results = msg.results;
        this.status = 'done';
        clearInterval(this._timer);
        this.addLog('', 'Pipeline complete! Semua step selesai.', 'complete');
        this.steps.forEach(s => {
          if (s.state === 'running' || s.state === '') {
            const r = msg.results[s.name];
            s.state = r >= 0 ? 'done' : 'failed';
          }
        });
        // Final step chart update
        if (stepChart) {
          this.steps.forEach((s, i) => {
            const r = msg.results[s.name];
            stepChart.data.datasets[0].data[i] = r >= 0 ? r : 0;
          });
          stepChart.update();
        }
        this.loadAfterStats();
      } else if (msg.type === 'error') {
        this.status = 'error';
        clearInterval(this._timer);
        this.addLog('', `Pipeline error: ${msg.message}`, 'error');
      }
      if (!this.paused) {
        this.$nextTick(() => {
          if (this.$refs.log) this.$refs.log.scrollTop = this.$refs.log.scrollHeight;
        });
      }
    },

    addLog(step, message, type) {
      this.logs.push({ step, message, type, timestamp: new Date().toISOString() });
    },
    formatTime(ts) { return new Date(ts).toLocaleTimeString('id-ID', { hour12: false }); },
    formatNum(n) { return n != null ? n.toLocaleString('id-ID') : '-'; },
  };
}
</script>
</body>
</html>
"""
