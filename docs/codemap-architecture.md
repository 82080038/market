# Codemap: Pustaka Pasar Modal - Event-Driven Quantitative Trading System

**Codemap ID:** `Pustaka_Pasar_Modal_-_Event-Driven_Quantitative_Trading_System_20260815_015721`
**Dibuat:** 2026-08-15
**Deskripsi:** Codemap untuk aplikasi trading quantitative berbasis event-driven architecture dengan 38 engine modular, pipeline terpisah (fetch→recompute→export→health→alert), dan ablation framework. Alur dimulai dari scheduler [1a] yang memicu data fetch [1c], event broker [2b] mengirim event ke recompute pipeline [2d], decision engine [3c] mengkombinasikan 6 faktor scores [3d], API endpoint [4b] melayani request frontend [4d], dan ablation framework [5c] mengevaluasi performa engine [5e].

---

## Trace 1: Daily Data Acquisition Flow - Scheduler ke Data Fetch Pipeline

Scheduler system memicu event-driven data fetch pipeline untuk mengambil OHLCV dari Yahoo Finance setiap hari.

```
Daily Data Acquisition Flow (Trace 1)
│
├── Scheduler System
│   └── _task_fetch_eod() <-- 1a
│       └── broker.emit("data.fetch.requested")
│
├── Event Broker (Core Wiring)
│   └── Event routing setup <-- 1b
│       └── broker.on() registers listener
│
├── Data Fetch Pipeline
│   └── on_fetch_requested() handler <-- 1c
│       ├── DataAcquisitionEngine created
│       ├── TickerScreener.screen() <-- 1d
│       │   └── Filter delisted/suspended <-- screener.py:67
│       └── For each valid ticker: <-- data_fetch.py:160
│           └── engine.fetch_and_store() <-- data_fetch.py:165
│
├── Data Acquisition Engine
│   └── yf.download() call <-- 1e
│       └── Yahoo Finance with retry <-- data_fetch.py:64
│
├── Data Repository
│   └── session.commit() <-- 1f
│       └── Save OHLCV to database
│
└── Pipeline Completion
    └── broker.emit("data.fetch.stored") <-- 1g
        └── Lightweight event (no auto-recompute)
```

### Lokasi (Trace 1)

| ID | Judul | Deskripsi | Path |
|----|-------|-----------|------|
| 1a | Scheduler Task Emit Event | Scheduler task mengirim event `data.fetch.requested` ke event broker (thin emitter, tidak langsung fetch) | `src/market/scheduler_tasks.py:40` |
| 1b | Event Listener Registration | Event broker mendaftarkan listener `DataFetchPipeline.on_fetch_requested` untuk event `data.fetch.requested` | `src/market/core/wiring.py:23` |
| 1c | Data Acquisition Engine Instantiation | Pipeline handler membuat instance `DataAcquisitionEngine` untuk fetch data eksternal | `src/market/pipelines/data_fetch.py:140` |
| 1d | Ticker Screening | `TickerScreener` memfilter ticker yang delisted/suspended/blocked sebelum fetch | `src/market/pipelines/data_fetch.py:144` |
| 1e | Yahoo Finance Data Download | Fetch OHLCV dari Yahoo Finance dengan retry exponential backoff untuk handle rate limit 429 | `src/market/data/acquisition.py:89` |
| 1f | Database Commit | `DataRepository` menyimpan OHLCV ke database (PostgreSQL/SQLite) dengan INSERT OR REPLACE | `src/market/data/storage.py:156` |
| 1g | Emit Completion Event | Pipeline emit event `data.fetch.stored` (lightweight, tidak auto-trigger recompute untuk avoid redundant cycles) | `src/market/pipelines/data_fetch.py:178` |

---

## Trace 2: Recompute Pipeline Flow - Event Broker ke Derived Tables

Event-driven recompute pipeline menghitung ulang indicators, scores, dan derived tables setelah semua fetch selesai.

```
Recompute Pipeline Flow (Event-Driven)
│
├── Scheduler System
│   └── _task_recompute() <-- scheduler_tasks.py:100
│       └── broker.emit("data.recompute.requested") <-- 2a
│
├── Event Broker (Core Wiring)
│   └── broker.on() listener registration <-- 2b
│       └── route to RecomputePipeline handler
│
├── Recompute Pipeline Handler
│   └── on_recompute_requested(event) <-- recompute.py:35
│       ├── run_all_recompute() call <-- 2c
│       │   ├── _recompute_technical_indicators() <-- 2d
│       │   │   └── compute RSI, MACD, MA, ADX, ATR, BB
│       │   ├── _recompute_scores() <-- 2e
│       │   │   └── compute 6 factor scores
│       │   ├── _recompute_relationship_matrix() <-- recompute.py:567
│       │   ├── _recompute_fear_greed() <-- recompute.py:678
│       │   ├── _recompute_stock_personality() <-- recompute.py:789
│       │   ├── _recompute_ml_labels() <-- recompute.py:890
│       │   └── _recompute_market_regimes() <-- recompute.py:945
│       └── broker.emit("data.recompute.completed") <-- 2f
│
└── Downstream Listeners
    └── AlertPipeline.on_recompute_completed() <-- wiring.py:31
        └── evaluate alert conditions <-- alerts.py:89
```

### Lokasi (Trace 2)

| ID | Judul | Deskripsi | Path |
|----|-------|-----------|------|
| 2a | Scheduler Trigger Recompute | Scheduler emit event recompute SETELAH semua fetch (eod, global, macro) selesai untuk avoid 3-4x redundant recompute | `src/market/scheduler_tasks.py:111` |
| 2b | Recompute Event Listener | Event broker route event ke `RecomputePipeline` handler | `src/market/core/wiring.py:25` |
| 2c | Run All Recompute | Pipeline memanggil `run_all_recompute` untuk update `technical_indicators`, `scores`, `relationship_matrix`, `fear_greed`, `stock_personality`, `ml_labels`, `market_regimes` | `src/market/pipelines/recompute.py:56` |
| 2d | Recompute Technical Indicators | Compute RSI, MACD, MA, ADX, ATR, Bollinger Bands untuk semua ticker dari OHLCV | `src/market/analysis/recompute.py:234` |
| 2e | Recompute Factor Scores | Compute 6 factor scores (technical, fundamental, macro, global, relationship, sentiment) untuk decision engine | `src/market/analysis/recompute.py:456` |
| 2f | Emit Recompute Completion | Pipeline emit event completion yang dipick up oleh `AlertPipeline` untuk evaluasi alert conditions | `src/market/pipelines/recompute.py:68` |

---

## Trace 3: Decision Engine Flow - Multi-Factor Score Combination

Decision engine mengkombinasikan 6 factor scores dengan weights, regime adjustment, dan XAI explanation untuk generate recommendation.

```
Decision Engine Flow - Multi-Factor Combination
├── API/Client Layer
│   └── engine.decide(ticker, scores...) <-- 3a
│       └── Validate & collect factor_scores <-- decision.py:125
│           dict
├── Weight Management
│   ├── Renormalize weights for available <-- 3b
│   │   factors (handle missing data)
│   └── total_weight = sum(weights) <-- decision.py:151
├── Composite Score Calculation
│   ├── Loop through factor_scores <-- 3c
│   │   ├── w = weight / total_weight <-- decision.py:160
│   │   ├── contrib = score * w <-- decision.py:161
│   │   └── composite += contrib <-- 3d
│   └── Clamp composite to [0, 100] <-- decision.py:165
├── Recommendation Mapping
│   └── Map score to label via thresholds <-- 3e
│       (strong_buy/buy/hold/reduce/sell)
├── XAI & Context Generation
│   ├── _generate_explanation() <-- decision.py:175
│   │   └── Top 3 factors + warnings <-- decision.py:210
│   └── generate_market_driver_narrative() <-- 3f
│       (causal, seasonal, commodity, etc)
└── Return DecisionResult <-- 3g
    (score, recommendation, explanation,
     market_driver_context)
```

### Lokasi (Trace 3)

| ID | Judul | Deskripsi | Path |
|----|-------|-----------|------|
| 3a | Decision Engine Entry Point | `DecisionEngine.decide()` menerima 6 factor scores (technical, fundamental, macro, global, relationship, sentiment) | `src/market/analysis/decision.py:98` |
| 3b | Weight Renormalization | Renormalize weights untuk available factors (weight redistribution jika ada engine tanpa data) | `src/market/analysis/decision.py:151` |
| 3c | Composite Score Calculation | Loop untuk compute weighted composite score dan contribution breakdown per factor | `src/market/analysis/decision.py:159` |
| 3d | Accumulate Weighted Scores | Akumulasi `score * weight` untuk setiap factor menjadi composite score (0-100) | `src/market/analysis/decision.py:162` |
| 3e | Recommendation Mapping | Map composite score ke recommendation label (strong_buy: 80-100, buy: 65-80, hold: 45-65, reduce: 30-45, sell: 0-30) | `src/market/analysis/decision.py:169` |
| 3f | Market Driver Narrative | Generate narrative Bahasa Indonesia dari 5 sumber: `causal_relationships`, `seasonal_patterns`, `commodity_to_stock_map`, `dcc_garch_results`, `satellite_observations` | `src/market/analysis/decision.py:183` |
| 3g | Return Decision Result | Return `DecisionResult` dengan composite score, recommendation, weights, factor_scores, contribution, explanation, market_driver_context | `src/market/analysis/decision.py:187` |

---

## Trace 4: API Request Flow - Frontend ke Decision Engine via FastAPI

FastAPI endpoint melayani request frontend untuk recommendation dengan memanggil decision engine dan risk engine.

```
FastAPI Application
└── GET /api/recommend/{ticker} endpoint <-- 4a
    └── recommend_ticker() handler <-- routes_analysis.py:68
        ├── Database Session <-- routes_analysis.py:87
        │   └── _get_latest_scores(session, ticker) <-- 4b
        │       └── Query scores table (6 factors) <-- _engines.py:45
        ├── Decision Engine
        │   ├── DecisionEngine(weights, db_url) <-- 4c
        │   └── engine.decide(ticker, **scores) <-- 4d
        │       ├── Renormalize weights <-- decision.py:151
        │       ├── Compute composite score <-- decision.py:162
        │       ├── Map to recommendation <-- decision.py:169
        │       └── Generate XAI explanation <-- decision.py:175
        ├── Risk Engine
        │   └── risk_engine.analyze(ticker) <-- 4e
        │       ├── Calculate position_size <-- engine.py:89
        │       ├── Calculate stop_loss/take_profit <-- engine.py:95
        │       └── Generate risk_flags <-- engine.py:112
        └── JSON Response <-- 4f
            ├── composite_score
            ├── recommendation
            ├── factor_scores
            ├── risk_metrics
            └── market_driver_context
```

### Lokasi (Trace 4)

| ID | Judul | Deskripsi | Path |
|----|-------|-----------|------|
| 4a | API Endpoint Definition | FastAPI route untuk `GET /api/recommend/{ticker}` yang return composite recommendation dengan XAI | `src/market/api/routes_analysis.py:67` |
| 4b | Fetch Latest Scores | Query database untuk ambil latest 6 factor scores (technical, fundamental, macro, global, relationship, sentiment) | `src/market/api/routes_analysis.py:89` |
| 4c | Instantiate Decision Engine | Create `DecisionEngine` instance dengan default weights dan database URL untuk market driver narrative | `src/market/api/routes_analysis.py:102` |
| 4d | Call Decision Engine | Panggil `DecisionEngine.decide()` dengan ticker dan unpacked scores untuk generate recommendation | `src/market/api/routes_analysis.py:103` |
| 4e | Risk Analysis | `RiskEngine.analyze()` compute position_size, stop_loss, take_profit, risk_flags (LIQUIDITY_LOW, HIGH_VOLATILITY) | `src/market/api/routes_analysis.py:108` |
| 4f | Return JSON Response | Return JSON response dengan recommendation, scores, risk metrics, XAI explanation, dan market driver context ke frontend | `src/market/api/routes_analysis.py:125` |

---

## Trace 5: Ablation Framework Flow - Engine Evaluation & Scorecard

Ablation framework mengisolasi dan mengevaluasi performa setiap engine (38 engines) dengan isolated backtest dan statistical significance test.

```
Ablation Framework - Engine Evaluation Flow
├── run_ablation.py script entry <-- run_ablation.py:89
│   ├── create_default_registry() <-- 5a
│   │   └── Returns 38 engines (24 enabled)
│   └── for entry in enabled_entries() <-- 5b
│       └── run_isolated_backtest() <-- run_ablation.py:78
│           ├── _run_backtest(baseline) <-- 5c
│           │   └── BacktestEngine.run() <-- isolated_backtest.py:127
│           │       └── Returns equity_curve
│           ├── _run_backtest(with_engine) <-- 5d
│           │   └── BacktestEngine.run() <-- isolated_backtest.py:138
│           │       └── Returns equity_curve
│           └── compute_scorecard() <-- isolated_backtest.py:145
│               ├── stats.ttest_rel() <-- 5e
│               │   └── Paired t-test + Bonferroni
│               ├── assign verdict <-- 5f
│               │   └── KEEP/MARGINAL/REMOVE
│               └── save_to_db() <-- 5g
│                   └── ablation_scorecards table
```

### Lokasi (Trace 5)

| ID | Judul | Deskripsi | Path |
|----|-------|-----------|------|
| 5a | Load Engine Registry | Load registry dengan 38 engine (24 enabled + 14 disabled): 22 SignalEnhancer + 12 MarketContext + 4 PredictionCore | `scripts/engine_ablation/run_ablation.py:45` |
| 5b | Loop Through Enabled Engines | Iterate semua enabled engines untuk isolated backtest vs baseline | `scripts/engine_ablation/run_ablation.py:67` |
| 5c | Run Baseline Backtest | Run backtest dengan baseline signal (tanpa engine yang sedang ditest) untuk comparison | `src/market/ablation/isolated_backtest.py:123` |
| 5d | Run Engine Backtest | Run backtest dengan engine signal (include engine yang sedang ditest) untuk measure delta alpha | `src/market/ablation/isolated_backtest.py:134` |
| 5e | Paired T-Test | Paired t-test untuk statistical significance dengan Bonferroni correction (alpha = 0.05 / num_engines) | `src/market/ablation/scorecard.py:89` |
| 5f | Verdict Assignment | Assign verdict KEEP/MARGINAL/REMOVE berdasarkan delta alpha, p-value, dan Bonferroni-corrected significance threshold | `src/market/ablation/scorecard.py:112` |
| 5g | Save to Database | Persist ablation results ke `ablation_runs` dan `ablation_scorecards` tables untuk historical tracking dan recommendations | `src/market/ablation/ablation_report.py:234` |

---

## Trace 6: Event Broker Architecture - Decoupled Pipeline Communication

Event broker system menghubungkan scheduler, pipelines, dan engines secara loosely coupled dengan pub/sub pattern.

```
Event Broker Architecture (Pub/Sub Pattern)
├── EventBroker Class <-- events.py:15
│   ├── emit(event_type, payload) <-- 6a
│   │   └── for handler in listeners[event_type] <-- 6b
│   │       └── handler(Event(type, payload)) <-- events.py:57
│   └── on(event_type, handler) <-- events.py:60
│       └── _listeners[event_type].append(handler) <-- events.py:62
├── Central Wiring Setup
│   └── wire_all_events() <-- 6c
│       ├── broker.on("data.fetch.requested", ...) <-- wiring.py:23
│       ├── broker.on("data.recompute.requested",
│       │   ...) <-- wiring.py:25
│       └── broker.on("data.recompute.completed", 
│           alert_pipeline.on_recompute_completed) <-- 6d
└── Pipeline Handlers (Subscribers)
    └── AlertPipeline <-- alerts.py:25
        └── on_recompute_completed(event) <-- 6e
            ├── check 15 alert types <-- alerts.py:89
            │   └── (price_target, volume_spike, etc)
            └── broker.emit("alert.check.completed",
                {...}) <-- 6f
```

### Lokasi (Trace 6)

| ID | Judul | Deskripsi | Path |
|----|-------|-----------|------|
| 6a | Event Broker Emit | `EventBroker.emit()` publish event dengan type dan payload ke semua registered listeners | `src/market/core/events.py:45` |
| 6b | Dispatch to Listeners | Loop semua listeners yang subscribe ke event_type dan call handler dengan `Event` object | `src/market/core/events.py:56` |
| 6c | Wire All Event Listeners | Central wiring function yang register semua pipeline listeners ke event broker (data_fetch, recompute, export, health, alerts) | `src/market/core/wiring.py:18` |
| 6d | Alert Pipeline Wiring | `AlertPipeline` listen ke `data.recompute.completed` untuk evaluate alert conditions setelah scores updated | `src/market/core/wiring.py:31` |
| 6e | Alert Pipeline Handler | Handler yang triggered ketika recompute selesai untuk check 15 alert types (price_target, volume_spike, ma_crossover, rsi_oversold, etc) | `src/market/pipelines/alerts.py:67` |
| 6f | Alert Completion Event | `AlertPipeline` emit completion event dengan count triggered alerts (terminal node, tidak auto-trigger notification) | `src/market/pipelines/alerts.py:156` |

---

## Catatan

- Codemap ini adalah snapshot arsitektur per 2026-08-15. Line numbers dapat bergeser setelah perubahan kode.
- Trace 5 (Ablation Framework) sudah diperbaiki logikanya pada sesi yang sama — lihat `.devin/SESSION_MEMORY.md` "Checkpoint Sesi 2026-08-15 — Perbaikan Logika Ablation Framework" untuk detail 9 bug fix.
- Untuk navigasi pustaka pengetahuan, lihat `pustaka/00-README.md`.
