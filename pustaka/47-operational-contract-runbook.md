# Operational Contract & Runbook: Aturan Eksekusi Setiap Task Aplikasi

> **Dokumen 47** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Definisi operasional lengkap untuk setiap task/modul di aplikasi — apa yang dikerjakan, kapan, siapa yang bertanggung jawab, bagaimana caranya, di mana, kenapa, dan kemana hasilnya. Serta aturan-aturan operasional dari best practice software engineering (runbook, idempotency, retry, escalation).
>
> **Konteks:** Dokumen 18 punya spesifikasi modul (tujuan, input, output, file). Dokumen 19 punya flow dan logic. Dokumen 36 punya jadwal WIB. Dokumen 46 punya jadwal pipeline. Tapi tidak ada satu dokumen yang systematically menjawab 5W1H + Output untuk **setiap task**. Dokumen ini mengisi gap tersebut.

---

## Daftar Isi

1. [Konsep: 5W1H + Output Framework](#1-konsep-5w1h--output-framework)
2. [Task Operations Matrix](#2-task-operations-matrix)
3. [RACI Matrix: Siapa Bertanggung Jawab](#3-raci-matrix-siapa-bertanggung-jawab)
4. [Runbook per Task Category](#4-runbook-per-task-category)
   - [4.1 Data Layer (T-001 to T-009)](#41-runbook-data-layer-t-001-to-t-009)
   - [4.2 Analysis Layer (T-010 to T-019)](#42-runbook-analysis-layer-t-010-to-t-019)
   - [4.3 Prediction & AI Layer (T-020 to T-027)](#43-runbook-prediction--ai-layer-t-020-to-t-027)
   - [4.4 Self-Correction (T-023)](#44-runbook-self-correction-t-023)
   - [4.5 Decision & Risk Layer (T-030 to T-034)](#45-runbook-decision--risk-layer-t-030-to-t-034)
   - [4.6 Execution & Monitoring (T-040 to T-046)](#46-runbook-execution--monitoring-t-040-to-t-046)
   - [4.7 Frontend & User Interaction (T-050 to T-053)](#47-runbook-frontend--user-interaction-t-050-to-t-053)
   - [4.8 Operations Activity Ownership Matrix](#48-operations-activity-ownership-matrix)
5. [Aturan Operasional (Best Practices)](#5-aturan-operasional-best-practices)
6. [Master Schedule (Unified)](#6-master-schedule-unified)
7. [Failure Handling & Escalation](#7-failure-handling--escalation)
8. [Idempotency & Retry Rules](#8-idempotency--retry-rules)
9. [Observability & Audit Trail](#9-observability--audit-trail)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Konsep: 5W1H + Output Framework

### 1.1 Kenapa Dokumen Ini Diperlukan

Setiap task di aplikasi harus punya **operational contract** — kontrak yang mendefinisikan dengan jelas:

| Dimensi | Pertanyaan | Contoh Jawaban |
|---------|-----------|----------------|
| **WHAT** | Apa yang harus dikerjakan? | "Fetch OHLCV data untuk 928 tickers dari Yahoo Finance" |
| **WHEN** | Kapan harus dikerjakan? | "16:30 WIB setiap hari bursa" |
| **WHO** | Bagian mana yang mengerjakan dan bertanggung jawab? | "Data Acquisition Engine (`data/acquisition.py`)" |
| **HOW** | Bagaimana cara mengerjakannya? | "yfinance API, rate limit 1 req/sec, retry 3x, normalize ke skema standar" |
| **WHERE** | Di mana harusnya dikerjakan? | "Backend Python, lokal (localhost), CPU-bound" |
| **WHY** | Kenapa dikerjakan? | "Data OHLCV adalah input untuk semua analysis engine" |
| **OUTPUT** | Kemana hasilnya disimpan atau diberikan? | "SQLite `ohlcv` table + event `data.raw.ohlcv` ke Event Bus" |

### 1.2 Prinsip Kontrak

Setiap task **wajib** punya semua 7 dimensi terdefinisi. Jika salah satu dimensi tidak terjawab, task tidak boleh diimplementasikan.

```
TASK CONTRACT TEMPLATE
═══════════════════════════════════════════════════════════════
Task ID     : T-001
Task Name   : EOD Data Fetch
WHAT        : Fetch OHLCV EOD untuk 928 active equity tickers
WHEN        : 16:30 WIB, setiap hari bursa (Senin-Jumat, skip holiday)
WHO         : Data Acquisition Engine → `data/acquisition.py`
HOW         : yfinance.batch_fetch(), rate limit 1 req/sec, retry 3x
              exponential backoff, normalize_ohlcv() → INSERT OR REPLACE
WHERE       : Backend Python, localhost, CPU-bound, I/O heavy
WHY         : Data OHLCV adalah single source of truth untuk semua
              analysis engine. Tanpa data terbaru, semua score stale.
OUTPUT      : SQLite `ohlcv` table (INSERT OR REPLACE)
              → Event `data.raw.ohlcv` published
              → `source_health` table updated
              → Audit log: `audit_log` table
CONSUMER    : Technical Analysis, Fundamental Analysis, Pattern Detection,
              LSTM Prediction, Backtest Engine
SLA         : < 60 detik untuk 928 tickers
FAILURE     : Retry 3x → fallback Google Finance → skip + alert
DEPENDENCY  : Yahoo Finance API availability, network connection
═══════════════════════════════════════════════════════════════
```

### 1.3 Sumber Aturan (Best Practices)

Dokumen ini mengadopsi konsep dari:

| Sumber | Konsep yang Diadopsi |
|--------|----------------------|
| **AWS Well-Architected Framework** (Operational Excellence) | Runbook per task, ownership matrix, error handling, escalation |
| **SRE Runbook Framework** | Imperative instructions, expected outcomes, troubleshooting, rollback |
| **Operations Activity Ownership Matrix** | Owner, responsibilities, validation method, feedback mechanism |
| **RACI Matrix** | Responsible, Accountable, Consulted, Informed per task |
| **Idempotency Principle** | Setiap task harus aman dijalankan ulang tanpa side effect |
| **SLA/SLO/SLI** | Service Level Agreement per task: latency, availability, error rate |

---

## 2. Task Operations Matrix

### 2.1 Data Layer Tasks

| ID | Task | WHAT | WHEN | WHO | HOW | WHERE | WHY | OUTPUT | CONSUMER |
|----|------|------|------|-----|-----|-------|-----|--------|----------|
| T-001 | EOD Data Fetch | Fetch OHLCV 928 tickers | 16:30 WIB daily | `data/acquisition.py` | yfinance API, rate limit 1/s, retry 3x | Backend, CPU+I/O | Single source of truth untuk semua analysis | `ohlcv` table + event `data.raw.*` | All analysis engines |
| T-002 | Foreign Flow Scrape | Scrape net buy/sell asing | 17:00 WIB daily | `data/acquisition.py` (IDXScraper) | cloudscraper, idx.co.id, rate 0.3s/req | Backend, I/O | Sinyal aliran dana asing per saham | `foreign_flow` table | Sentiment Engine, Decision Engine |
| T-003 | Broker Flow Scrape | Scrape aktivitas broker | 17:00 WIB daily | `data/acquisition.py` (IDXScraper) | cloudscraper, idx.co.id | Backend, I/O | Deteksi konsentrasi broker per saham | `broker_flow` table | Sentiment Engine |
| T-004 | Data Validation | Validasi completeness, plausibility | 16:35 WIB daily (after T-001) | `data/validation.py` | Check missing, gap, price ≤ 0, low > high | Backend, CPU | Pastikan data bersih sebelum dipakai | `data_quality_score` (0-100) + event `data.clean.*` | All downstream engines |
| T-005 | Macro Data Fetch | Fetch BI rate, inflasi, GDP | 08:00 WIB weekly (Senin) | `data/acquisition.py` | BPS/BI/FRED API | Backend, I/O | Konteks makro ekonomi untuk decision | `macro_data` table | Macro Analysis Engine |
| T-006 | Global Market Fetch | Fetch S&P500, NASDAQ, VIX, oil, gold | 06:00 WIB daily | `data/acquisition.py` | yfinance (global tickers) | Backend, I/O | Konteks pasar global → IDX | `ohlcv` table (global tickers) | Global Market Engine |
| T-007 | Corporate Actions | Fetch splits, dividends | 09:00 WIB weekly (Senin) | `corporate/actions.py` | yfinance actions API | Backend, I/O | Adjust historical prices | `corporate_actions` + `dividends` tables | Technical Analysis, Backtest |
| T-008 | DB Backup | Backup SQLite + Parquet sync | 01:00 WIB daily | `scripts/backup.py` | sqlite3 .backup + rsync to Parquet | Backend, I/O | Disaster recovery | `backups/` dir + Parquet archive | Recovery procedure |
| T-009 | Data Quality Report | Generate quality report | 18:00 WIB daily | `data/validation.py` | Aggregate quality scores | Backend, CPU | Monitoring data health | `audit_log` + UI dashboard | Monitoring Engine, User |

### 2.2 Analysis Layer Tasks

| ID | Task | WHAT | WHEN | WHO | HOW | WHERE | WHY | OUTPUT | CONSUMER |
|----|------|------|------|-----|-----|-------|-----|--------|----------|
| T-010 | Technical Analysis | Compute RSI, MACD, ADX, BB, pattern | 18:00 WIB daily (after T-001) | `analysis/technical.py` | pandas vectorization, 20+ indicators | Backend, CPU | Sinyal teknikal per saham | `technical_indicators` table + `scores` (technical) | Decision Engine, Pattern Memory |
| T-011 | Fundamental Analysis | Score ROE, P/E, P/B, DER, growth | 18:00 WIB daily | `analysis/fundamental.py` | yfinance fundamentals, scoring 0-100 | Backend, CPU | Valuasi saham | `scores` (fundamental) | Decision Engine |
| T-012 | Macro Analysis | Score BI rate, inflasi, GDP trend | 18:05 WIB daily | `analysis/macro.py` | Compare macro indicators to regime | Backend, CPU | Konteks makro | `scores` (macro) | Decision Engine |
| T-013 | Global Market Analysis | Score S&P500, VIX, oil, gold | 18:05 WIB daily | `analysis/global_market.py` | Correlation global → IDX | Backend, CPU | Konteks global | `scores` (global) | Decision Engine |
| T-014 | Relationship Analysis | Correlation matrix, lead-lag | 18:10 WIB daily | `analysis/relationship.py` | Pearson correlation, Granger causality | Backend, CPU | Diversifikasi & intermarket | `relationship_matrix` table + `scores` (relationship) | Decision Engine, Portfolio |
| T-015 | Sentiment Analysis | NLP (IndoBERT), foreign flow, Fear&Greed | 18:10 WIB daily | `sentiment/engine.py` | IndoBERT inference, 6-source weighting | Backend, GPU (cuda:1) untuk IndoBERT | Sentimen pasar | `scores` (sentiment) | Decision Engine |
| T-016 | Regime Detection | HMM regime: easing/tightening/growth | 18:15 WIB daily | `analysis/enhanced_regime.py` | HMM fitting on macro + IDX data | Backend, CPU | Konteks regime untuk weight adjustment | `ai_weights` table (regime tag) | AI Learning, Decision Engine |
| T-017 | Pattern Detection | Detect chart & candlestick patterns | 18:15 WIB daily | `analysis/technical.py` | Pattern recognition algorithms | Backend, CPU | Sinyal pola chart | `pattern_analysis` table | Pattern Reliability, Prediction Engine |
| T-018 | Factor Screening | Multi-factor composite ranking | 18:20 WIB daily | `analysis/factor_screener.py` | Value, momentum, quality, volatility factors | Backend, CPU | Ranking saham multi-faktor | In-memory + API response | Screener UI, Portfolio Pipeline |
| T-019 | Score Computation (Pipeline) | Run full 6-factor pipeline | 18:00 WIB daily | `analysis/pipeline.py` | Orchestrate T-010 to T-016 | Backend, CPU | Composite score per saham | `scores` table (all 6 factors) | Decision Engine, XAI |

### 2.3 Prediction & AI Layer Tasks

| ID | Task | WHAT | WHEN | WHO | HOW | WHERE | WHY | OUTPUT | CONSUMER |
|----|------|------|------|-----|-----|-------|-----|--------|----------|
| T-020 | LSTM Prediction | Price prediction per ticker | 18:00 WIB daily | `ai_learning/deep_learning.py` | PyTorch LSTM, GPU cuda:1, batch ≤64 | Backend, GPU (cuda:1) | Prediksi arah harga N hari ke depan | In-memory → `prediction_log` table | Prediction Engine |
| T-021 | Pattern Reliability Lookup | Win-rate per pola per saham | 18:15 WIB daily | `analysis/pattern_reliability.py` | Query `pattern_analysis` aggregate | Backend, CPU | Validasi pola dengan historis | `pattern_reliability` data | Prediction Engine, Decision Engine |
| T-022 | Prediction Engine (Fusion) | Fuse LSTM + pattern + factor + sentiment | 18:20 WIB daily | `analysis/prediction_engine.py` (NEW) | Weighted fusion, regime-specific weights | Backend, CPU | Final prediction per saham | `prediction_log` table | Portfolio Pipeline, XAI |
| T-023 | Self-Correction Loop | Evaluate pending predictions | 16:30 WIB daily | `ai_learning/error_analysis.py` (NEW) | Compare prediction vs actual, root cause | Backend, CPU | Belajar dari kesalahan | `error_analysis` table + Pattern Journal | AI Learning, Pattern Journal |
| T-024 | AI Weight Optimization | Optimize factor weights per regime | 20:00 WIB weekly (Sabtu) | `ai_learning/engine.py` | Ridge regression on historical scores | Backend, CPU | Dynamic weight adjustment | `ai_weights` table | Decision Engine |
| T-025 | LSTM Retrain | Retrain per-ticker LSTM models | 20:00 WIB weekly (Sabtu) | `ai_learning/per_ticker_lstm.py` (NEW) | PyTorch training, GPU cuda:1, 4-8 jam | Backend, GPU (cuda:1) | Update model dengan data terbaru | `models/lstm/{ticker}_lstm.pt` | LSTM Prediction (T-020) |
| T-026 | Pattern Discovery | Find new patterns via clustering | 20:00 WIB weekly (Sabtu) | `analysis/pattern_discovery.py` (NEW) | K-means on 20-day windows, outcome check | Backend, CPU+GPU | Temukan pola baru | `discovered_patterns` table | Pattern Journal, Prediction Engine |
| T-027 | Walk-Forward Validation | Out-of-sample validation | 20:00 WIB weekly (Sabtu) | `ai_learning/walk_forward.py` | Rolling window train/test, purged TSS | Backend, CPU | Validasi model tidak overfit | Model registry metrics | Model Registry |

### 2.4 Decision & Risk Layer Tasks

| ID | Task | WHAT | WHEN | WHO | HOW | WHERE | WHY | OUTPUT | CONSUMER |
|----|------|------|------|-----|-----|-------|-----|--------|----------|
| T-030 | Decision Engine | 6-factor weighted scoring → recommendation | 18:25 WIB daily | `decision/engine.py` | Weighted sum + regime filter + conviction | Backend, CPU | Rekomendasi BUY/HOLD/WATCHLIST/AVOID | `scores` (composite) + recommendation | XAI, Execution, User |
| T-031 | Risk Assessment | VaR, position sizing, SL/TP | 18:30 WIB daily | `risk/engine.py` | Historical VaR, Kelly criterion, ATR-based SL | Backend, CPU | Manajemen risiko per trade | Risk metrics in recommendation | Execution Engine, Portfolio |
| T-032 | XAI Narrative | Generate explanation in Bahasa Indonesia | 18:30 WIB daily | `xai/engine.py` | Template-based narrative + top factors | Backend, CPU | Explainable AI untuk user | Narrative text in API response | Frontend UI, User |
| T-033 | Portfolio Optimization | HRP / Markowitz optimization | 18:30 WIB daily | `portfolio/candidate_pipeline.py` (NEW) | Filter → risk → correlation → optimize | Backend, CPU | Alokasi portofolio optimal | `portfolio_candidates` table | User, Execution Engine |
| T-034 | Portfolio Rebalancing | Check drift, suggest rebalance | 16:30 WIB daily | `portfolio/rebalancer.py` | Compare current vs target weights | Backend, CPU | Maintain target allocation | Rebalance suggestions | User |

### 2.5 Execution & Monitoring Tasks

| ID | Task | WHAT | WHEN | WHO | HOW | WHERE | WHY | OUTPUT | CONSUMER |
|----|------|------|------|-----|-----|-------|-----|--------|----------|
| T-040 | Paper Trading | Simulate execution | 09:00-15:50 WIB (market hours) | `paper_trading/simulator.py` | Mock broker, track fills, PnL | Backend, CPU | Test strategi tanpa risiko | `paper_trades` table | User, AI Learning |
| T-041 | Auto Trading | Execute real orders | 09:00-15:50 WIB (if enabled) | `execution/automated.py` | Broker API, signal-driven | Backend, network | Eksekusi otomatis | `orders` table + broker API | User, Audit Log |
| T-042 | Position Monitor | Check SL/TP, trailing stop | Every 60s during market | `execution/automated.py` | Poll price, compare to SL/TP | Backend, CPU | Protect capital | Position update + alert | User, Execution |
| T-043 | Market Status Check | Check IDX open/close, auto-reject | Every 5min during market | `data/storage.py` | Query market_calendar + IDX API | Backend, CPU | Avoid trading on closed/halted market | Market status flag | Execution Engine |
| T-044 | System Health Monitor | Check all engines, DB, API | Every 5min, 24/7 | `monitoring/engine.py` | Health check all components | Backend, CPU | Detect system issues early | `audit_log` + alert | User, Telegram |
| T-045 | Telegram Notification | Send alerts to user | Event-driven | `utils/telegram_notifier.py` | Telegram Bot API | Backend, network | Real-time alert ke user | Telegram message | User |
| T-046 | Audit Log | Record all significant events | Event-driven (real-time) | `data/storage.py` | Append-only log | Backend, I/O | Traceability & debugging | `audit_log` table | User, Debugging |

### 2.6 Frontend & User Interaction Tasks

| ID | Task | WHAT | WHEN | WHO | HOW | WHERE | WHY | OUTPUT | CONSUMER |
|----|------|------|------|-----|-----|-------|-----|--------|----------|
| T-050 | Dashboard Render | Render data inspection dashboard | On user visit | `frontend/app/page.tsx` | Next.js SSR, API fetch | Frontend (browser) | User melihat data | HTML page | User |
| T-051 | API Request | Handle REST API request | On user action | `api/app.py` (FastAPI) | Async endpoint, X-API-Key header | Backend, network | User interaction | JSON response | Frontend |
| T-052 | WebSocket Stream | Real-time data push | On connect, 24/7 | `api/app.py` (WebSocket) | FastAPI WebSocket, JSON stream | Backend, network | Real-time updates | WebSocket frames | Frontend |
| T-053 | Pre-Market Scan | Quick prediction for watchlist | 08:30 WIB daily | `analysis/prediction_engine.py` | Run prediction for ~20-50 tickers | Backend, GPU (LSTM) | Pre-market signals | `prediction_log` + alert | User, Frontend |

---

## 3. RACI Matrix: Siapa Bertanggung Jawab

### 3.1 Konsep RACI

| Role | Arti |
|------|------|
| **R** (Responsible) | Yang mengerjakan task |
| **A** (Accountable) | Yang bertanggung jawab atas hasil (hanya 1) |
| **C** (Consulted) | Yang dikonsultasikan sebelum/during task |
| **I** (Informed) | Yang diberi tahu setelah task selesai |

### 3.2 RACI per Task (All 53 Tasks)

| Task | Data Engine | Analysis Engine | AI Learning | Decision Engine | Risk Engine | Portfolio Engine | Execution Engine | Monitoring | XAI | Frontend | User |
|------|------------|----------------|-------------|----------------|-------------|-----------------|-----------------|------------|-----|----------|------|
| T-001 EOD Fetch | **R/A** | I | — | — | — | — | — | I | — | — | — |
| T-002 Foreign Flow | **R/A** | I | — | — | — | — | — | I | — | — | — |
| T-003 Broker Flow | **R/A** | I | — | — | — | — | — | I | — | — | — |
| T-004 Validation | **R/A** | C | — | — | — | — | — | I | — | — | — |
| T-005 Macro Fetch | **R/A** | I | — | — | — | — | — | I | — | — | — |
| T-006 Global Fetch | **R/A** | I | — | — | — | — | — | I | — | — | — |
| T-007 Corp Actions | **R/A** | C | — | — | — | — | — | I | — | — | — |
| T-008 DB Backup | **R/A** | — | — | — | — | — | — | I | — | — | — |
| T-009 Quality Report | **R/A** | I | — | — | — | — | — | C | — | — | I |
| T-010 Technical | I | **R/A** | — | C | — | — | — | I | — | — | — |
| T-011 Fundamental | I | **R/A** | — | C | — | — | — | I | — | — | — |
| T-012 Macro Analysis | I | **R/A** | — | C | — | — | — | I | — | — | — |
| T-013 Global Market | I | **R/A** | — | C | — | — | — | I | — | — | — |
| T-014 Relationship | I | **R/A** | — | C | — | C | — | I | — | — | — |
| T-015 Sentiment | I | **R/A** | C | C | — | — | — | I | — | — | — |
| T-016 Regime | I | **R/A** | C | C | — | — | — | I | — | — | — |
| T-017 Pattern Detect | I | **R/A** | C | — | — | — | — | I | — | — | — |
| T-018 Factor Screen | I | **R/A** | — | C | — | C | — | I | — | — | — |
| T-019 Pipeline | I | **R/A** | C | C | — | — | — | I | — | — | — |
| T-020 LSTM | I | C | **R/A** | — | — | — | — | I | — | — | — |
| T-021 Pattern Rel. | I | C | **R/A** | C | — | — | — | I | — | — | — |
| T-022 Prediction | I | C | **R/A** | C | — | C | — | I | C | — | — |
| T-023 Self-Correct | I | C | **R/A** | C | — | — | — | I | — | — | — |
| T-024 Weight Opt | I | C | **R/A** | C | — | — | — | I | — | — | — |
| T-025 LSTM Retrain | I | — | **R/A** | — | — | — | — | I | — | — | — |
| T-026 Pattern Disc. | I | C | **R/A** | — | — | — | — | I | — | — | — |
| T-027 Walk-Forward | I | — | **R/A** | — | — | — | — | I | — | — | — |
| T-030 Decision | I | C | C | **R/A** | C | — | — | I | C | — | — |
| T-031 Risk | I | — | — | C | **R/A** | C | C | I | — | — | — |
| T-032 XAI Narrative | I | C | C | C | — | — | — | I | **R/A** | — | I |
| T-033 Portfolio | I | C | C | C | C | **R/A** | — | I | — | — | I |
| T-034 Rebalancing | I | — | — | — | C | **R/A** | — | I | — | — | I |
| T-040 Paper Trade | I | — | C | C | C | — | **R/A** | I | — | — | I |
| T-041 Auto Trade | I | — | C | C | C | C | **R/A** | I | — | — | **A** |
| T-042 Position Mon. | I | — | — | — | C | — | **R/A** | I | — | — | I |
| T-043 Market Status | **R/A** | — | — | — | — | — | C | I | — | — | — |
| T-044 Health Mon. | I | I | I | I | I | I | I | **R/A** | I | I | I |
| T-045 Telegram | I | — | — | — | — | — | — | C | — | — | **R/A** |
| T-046 Audit Log | **R/A** | I | I | I | I | I | I | C | I | — | I |
| T-050 Dashboard | I | — | — | I | — | I | — | I | I | **R/A** | I |
| T-051 API Request | I | C | C | C | C | C | C | I | C | **R/A** | I |
| T-052 WebSocket | I | — | — | I | — | I | C | I | — | **R/A** | I |
| T-053 Pre-Market | I | C | **R/A** | C | — | C | — | I | C | — | I |

### 3.3 Accountability Rules

- **Satu Accountable per task** — tidak boleh dua modul accountable untuk task yang sama
- **Accountable ≠ Responsible** — modul yang mengerjakan (R) bisa berbeda dengan yang accountable (A)
- **User adalah I (Informed) untuk sebagian besar task** — user tidak perlu tahu detail teknis
- **User adalah A untuk T-041 (Auto Trade)** — user yang bertanggung jawab atas keputusan auto-trading, bukan sistem
- **Monitoring adalah I untuk semua task** — monitoring tahu semua yang terjadi, tapi tidak mengerjakan

---

## 4. Runbook per Task Category

### 4.1 Runbook: Data Layer (T-001 to T-009)

```yaml
Task ID: T-001
Task Name: EOD Data Fetch
Owner: data/acquisition.py
SLA: < 60 detik untuk 928 tickers

WHAT:
  Fetch OHLCV end-of-day data untuk 928 active equity tickers dari Yahoo Finance.

WHEN:
  - Schedule: 16:30 WIB setiap hari bursa (Senin-Jumat)
  - Skip: IDX holidays (cek market_calendar), weekend
  - Retry window: 16:30-17:00 WIB (30 menit)

WHO:
  - Responsible: DataAcquisition.fetch_batch()
  - Accountable: Data Acquisition Engine
  - Consulted: Data Validation Engine (T-004)
  - Informed: Monitoring Engine, Audit Log

HOW:
  1. Load list_active_equity_tickers() → 928 tickers
  2. For each ticker (rate limited 1 req/sec):
     a. Call yfinance.download(ticker, period="1d")
     b. Normalize: normalize_ohlcv(raw_df, ticker)
     c. Validate: check completeness, plausibility
     d. Store: storage.save_ohlcv(df) → INSERT OR REPLACE
  3. Update source_health: yahoo_finance → "ok" or "error"
  4. Publish event: data.raw.ohlcv
  5. Audit log: "EOD fetch completed: 928 tickers, 925 success, 3 fail"

WHERE:
  - Backend Python, localhost
  - CPU + I/O bound (network ke Yahoo Finance)
  - No GPU needed

WHY:
  - OHLCV adalah single source of truth untuk semua analysis
  - Tanpa data terbaru, semua score dan prediction menjadi stale
  - Data lag > 1 hari → semua downstream engine tidak valid

OUTPUT:
  - Primary: SQLite `ohlcv` table (INSERT OR REPLACE)
  - Secondary: `source_health` table (status update)
  - Event: data.raw.ohlcv published to Event Bus
  - Audit: `audit_log` table (append-only)
  - Consumer: T-010 to T-019 (all analysis engines)

FAILURE HANDLING:
  - Yahoo API timeout: retry 3x, exponential backoff (1s, 2s, 4s)
  - Yahoo API down: fallback ke Google Finance scraper
  - Still failing: skip ticker, log warning, continue next ticker
  - > 10% tickers fail: alert via Telegram, mark pipeline as "degraded"
  - Complete failure: skip T-010 to T-019, alert user

IDEMPOTENCY:
  - INSERT OR REPLACE → aman dijalankan ulang
  - Same data fetched twice → no duplicate, no side effect

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM ohlcv WHERE date = today
  - Expected: ~928 rows for today's date
  - Alert if: < 900 rows (> 3% missing)
```

```yaml
Task ID: T-002
Task Name: Foreign Flow Scrape
Owner: data/acquisition.py (IDXScraper)
SLA: < 10 menit untuk 928 tickers

WHAT:
  Scrape data net buy/sell asing per saham dari idx.co.id.

WHEN:
  - Schedule: 17:00 WIB daily (after T-001, post IDX data publish)
  - Skip: IDX holidays, weekends

WHO:
  - Responsible: IDXScraper.fetch_foreign_flow()
  - Accountable: Data Acquisition Engine
  - Informed: Sentiment Engine, Decision Engine, Monitoring

HOW:
  1. Navigate to idx.co.id foreign flow page
  2. For each ticker: scrape net buy/sell value
  3. Rate limit: 0.3s per request
  4. Normalize: map to (ticker, date, net_buy, net_sell, net_value)
  5. Store: storage.save_foreign_flow(df) → INSERT OR REPLACE

WHERE:
  - Backend Python, localhost
  - I/O bound (web scraping)

WHY:
  - Aliran dana asing adalah sinyal sentiment kuat di IDX
  - Foreign sell → tekanan jual; foreign buy → dukungan harga
  - Tanpa data ini, Sentiment Engine kehilangan komponen penting

OUTPUT:
  - Primary: `foreign_flow` table (INSERT OR REPLACE)
  - Audit: `audit_log` table
  - Consumer: T-015 (Sentiment), T-022 (Prediction), T-030 (Decision)

FAILURE HANDLING:
  - idx.co.id blocked: retry 5x linear backoff (5s, 10s, 15s, 20s, 25s)
  - Cloudflare challenge: use cloudscraper library
  - Still failing: skip, log warning, use last known foreign flow
  - > 20% tickers fail: alert, mark sentiment score as "stale"

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date) → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM foreign_flow WHERE date = today
  - Expected: ~928 rows
  - Alert if: < 700 rows
```

```yaml
Task ID: T-003
Task Name: Broker Flow Scrape
Owner: data/acquisition.py (IDXScraper)
SLA: < 10 menit

WHAT:
  Scrape data aktivitas broker (broker summary) per saham dari idx.co.id.

WHEN:
  - Schedule: 17:00 WIB daily (parallel with T-002)
  - Skip: IDX holidays, weekends

WHO:
  - Responsible: IDXScraper.fetch_broker_summary()
  - Accountable: Data Acquisition Engine
  - Informed: Sentiment Engine, Monitoring

HOW:
  1. Navigate to idx.co.id broker summary page
  2. For each ticker: scrape top broker buy/sell
  3. Rate limit: 0.3s per request
  4. Normalize: map to (ticker, date, broker, buy_value, sell_value)
  5. Store: storage.save_broker_flow(df) → INSERT OR REPLACE

WHERE:
  - Backend Python, localhost
  - I/O bound (web scraping)

WHY:
  - Konsentrasi broker menunjukkan institusional activity
  - Broker accumulation → sinyal kuat; distribution → sinyal lemah

OUTPUT:
  - Primary: `broker_flow` table
  - Audit: `audit_log` table
  - Consumer: T-015 (Sentiment)

FAILURE HANDLING:
  - Same as T-002

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, broker) → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM broker_flow WHERE date = today
  - Expected: > 100 rows (not all tickers have broker data daily)
```

```yaml
Task ID: T-004
Task Name: Data Validation
Owner: data/validation.py
SLA: < 30 detik

WHAT:
  Validasi completeness, plausibility, dan gap detection untuk data yang baru di-fetch.

WHEN:
  - Schedule: 16:35 WIB daily (after T-001 completes)
  - Dependency: T-001 must complete

WHO:
  - Responsible: DataValidation.validate_batch()
  - Accountable: Data Acquisition Engine
  - Consulted: Analysis Engine (downstream consumer)
  - Informed: Monitoring

HOW:
  1. For each ticker fetched in T-001:
     a. Completeness: check missing OHLCV columns
     b. Plausibility: price ≤ 0, low > high, close outside range
     c. Gap detection: gap > 5 trading days
     d. Volume spike: volume > 10x median
  2. Compute quality score 0-100
  3. Score ≥ 90: accept; 70-89: flag; < 70: pause (reject)
  4. Publish event: data.clean.* for accepted data

WHERE:
  - Backend Python, localhost
  - CPU bound (computation only)

WHY:
  - Data kotor → semua downstream analysis tidak valid
  - Validasi mencegah garbage-in-garbage-out

OUTPUT:
  - Primary: data_quality_score per ticker (0-100)
  - Event: data.clean.* published
  - Audit: `audit_log` table
  - Consumer: All downstream engines (T-010 to T-019)

FAILURE HANDLING:
  - Validation crash: log error, default to "flag" status
  - All data paused: alert user, skip pipeline

IDEMPOTENCY:
  - Recompute score on same data → same result, no side effect

VALIDATION:
  - Post-check: SELECT AVG(quality_score) FROM ohlcv WHERE date = today
  - Expected: > 85 average
  - Alert if: < 70 average
```

```yaml
Task ID: T-005
Task Name: Macro Data Fetch
Owner: data/acquisition.py
SLA: < 2 menit

WHAT:
  Fetch data makro ekonomi: BI rate, inflasi, GDP, USD/IDR dari BPS, BI, FRED.

WHEN:
  - Schedule: 08:00 WIB weekly (Senin)
  - Skip: public holidays

WHO:
  - Responsible: DataAcquisition.fetch_macro()
  - Accountable: Data Acquisition Engine
  - Informed: Macro Analysis Engine, Monitoring

HOW:
  1. Fetch BI rate from BI website/API
  2. Fetch inflasi (CPI) from BPS
  3. Fetch GDP growth from BPS
  4. Fetch USD/IDR from Yahoo Finance
  5. Normalize: map to (indicator, date, value, source)
  6. Store: storage.save_macro_data(df) → INSERT OR REPLACE

WHERE:
  - Backend Python, localhost
  - I/O bound (multiple APIs)

WHY:
  - Data makro adalah konteks untuk regime detection dan decision engine
  - Tanpa data makro, regime detection tidak akurat

OUTPUT:
  - Primary: `macro_data` table
  - Audit: `audit_log` table
  - Consumer: T-012 (Macro Analysis), T-016 (Regime Detection)

FAILURE HANDLING:
  - BPS/BI API down: use last known value, log warning
  - Partial failure: save what's available, flag missing indicators

IDEMPOTENCY:
  - INSERT OR REPLACE on (indicator, date) → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM macro_data WHERE date = this_week
  - Expected: ≥ 4 indicators
```

```yaml
Task ID: T-006
Task Name: Global Market Fetch
Owner: data/acquisition.py
SLA: < 30 detik

WHAT:
  Fetch OHLCV untuk global market tickers: S&P 500, NASDAQ, VIX, crude oil, gold, DXY.

WHEN:
  - Schedule: 06:00 WIB daily
  - Note: US market closed at 05:00 WIB (previous day close)

WHO:
  - Responsible: DataAcquisition.fetch_global()
  - Accountable: Data Acquisition Engine
  - Informed: Global Market Engine, Monitoring

HOW:
  1. Fetch via yfinance for: ^GSPC, ^IXIC, ^VIX, CL=F, GC=F, DX-Y.NYB
  2. Normalize: normalize_ohlcv() to standard schema
  3. Store: storage.save_ohlcv(df) → INSERT OR REPLACE

WHERE:
  - Backend Python, localhost
  - I/O bound (network to Yahoo Finance)

WHY:
  - Pasar global memengaruhi IDX (overnight sentiment)
  - VIX tinggi → risk-off → IDX cenderung turun

OUTPUT:
  - Primary: `ohlcv` table (global tickers, asset_class != 'equity')
  - Audit: `audit_log` table
  - Consumer: T-013 (Global Market Analysis)

FAILURE HANDLING:
  - Yahoo API timeout: retry 3x exponential backoff
  - US holiday: no new data, log info, skip

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date) → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM ohlcv WHERE ticker IN ('^GSPC','^VIX') AND date = today
  - Expected: 2+ rows
```

```yaml
Task ID: T-007
Task Name: Corporate Actions Fetch
Owner: corporate/actions.py
SLA: < 5 menit

WHAT:
  Fetch corporate actions (stock splits, dividends) untuk semua active equity tickers.

WHEN:
  - Schedule: 09:00 WIB weekly (Senin)
  - Skip: public holidays

WHO:
  - Responsible: CorporateActions.fetch_all()
  - Accountable: Data Acquisition Engine
  - Consulted: Analysis Engine (price adjustment)
  - Informed: Monitoring

HOW:
  1. For each ticker: yfinance.Ticker(ticker).actions
  2. Extract splits and dividends
  3. Normalize: map to (ticker, date, action_type, value)
  4. Store: storage.save_corporate_action() / save_dividend()
  5. If split detected: trigger adjusted close recalculation

WHERE:
  - Backend Python, localhost
  - I/O bound (yfinance API)

WHY:
  - Stock split → harga adjust, perlu recalculate historical prices
  - Dividend → total return calculation
  - Tanpa adjust, backtest dan technical analysis tidak akurat

OUTPUT:
  - Primary: `corporate_actions` table + `dividends` table
  - Secondary: trigger adjusted close update
  - Audit: `audit_log` table
  - Consumer: T-010 (Technical), Backtest Engine

FAILURE HANDLING:
  - yfinance actions API fail: retry 3x, skip ticker on failure
  - Split detection: log, alert user for manual verification

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, action_type) → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM corporate_actions WHERE date = this_week
  - Expected: variable (0-50 actions per week)
```

```yaml
Task ID: T-008
Task Name: Database Backup
Owner: scripts/backup.py
SLA: < 10 menit

WHAT:
  Backup SQLite database + sync Parquet archive.

WHEN:
  - Schedule: 01:00 WIB daily
  - Always runs (including holidays and weekends)

WHO:
  - Responsible: backup_script.run()
  - Accountable: Data Acquisition Engine
  - Informed: Monitoring

HOW:
  1. sqlite3 .backup command → backups/trading_system_YYYYMMDD.db
  2. Verify backup: open backup, SELECT COUNT(*) per table
  3. rsync Parquet archive to DATA_ARCHIVE_DIR
  4. Clean old backups: keep last 30 days
  5. Audit log: "Backup completed: size=X MB, tables=41"

WHERE:
  - Backend Python, localhost
  - I/O bound (disk write)

WHY:
  - Disaster recovery: jika DB corrupt, restore dari backup
  - Parquet sync: redundant storage untuk data archival

OUTPUT:
  - Primary: `backups/trading_system_YYYYMMDD.db`
  - Secondary: Parquet archive updated
  - Audit: `audit_log` table
  - Consumer: Recovery procedure (if needed)

FAILURE HANDLING:
  - Backup fail: retry 3x, alert via Telegram (SEV-0)
  - Disk full: alert, skip backup, clean old backups
  - Parquet sync fail: log warning, DB backup still valid

IDEMPOTENCY:
  - .backup overwrites if same filename → use date-suffixed filename
  - Re-run same date → new backup file, no data loss

VALIDATION:
  - Post-check: open backup file, SELECT COUNT(*) FROM ohlcv
  - Expected: same count as production DB
  - Alert if: backup file missing or corrupt
```

```yaml
Task ID: T-009
Task Name: Data Quality Report
Owner: data/validation.py
SLA: < 30 detik

WHAT:
  Generate aggregated data quality report untuk semua tickers.

WHEN:
  - Schedule: 18:00 WIB daily (after T-004 validation)
  - Dependency: T-004 must complete

WHO:
  - Responsible: DataValidation.generate_report()
  - Accountable: Data Acquisition Engine
  - Consulted: Monitoring Engine
  - Informed: User (via dashboard)

HOW:
  1. Aggregate quality scores from T-004
  2. Compute: avg score, min score, tickers below threshold
  3. Identify: missing data patterns, recurring issues
  4. Store summary in audit_log
  5. Expose via API: /api/data-quality

WHERE:
  - Backend Python, localhost
  - CPU bound (aggregation)

WHY:
  - Monitoring data health secara sistematis
  - User perlu tahu jika data quality menurun

OUTPUT:
  - Primary: `audit_log` entry (quality report)
  - Secondary: API endpoint /api/data-quality
  - Consumer: Monitoring Engine, User (dashboard)

FAILURE HANDLING:
  - Report generation fail: log error, skip (non-critical)

IDEMPOTENCY:
  - Re-generating report for same date → overwrites, no side effect

VALIDATION:
  - Post-check: audit_log entry exists for today
  - Expected: 1 entry with quality summary
```

### 4.2 Runbook: Analysis Layer (T-010 to T-019)

```yaml
Task ID: T-019
Task Name: Score Computation Pipeline
Owner: analysis/pipeline.py
SLA: < 5 menit untuk 928 tickers

WHAT:
  Run full 6-factor analysis pipeline: Technical → Fundamental → Macro →
  Global → Relationship → Sentiment → Composite score.

WHEN:
  - Schedule: 18:00 WIB daily (after T-001 EOD fetch + T-002 foreign flow)
  - Dependency: T-001 must complete successfully
  - Skip: if T-001 failed (> 10% tickers missing)

WHO:
  - Responsible: AnalysisPipeline.run()
  - Accountable: Analysis Layer
  - Consulted: AI Learning (regime weights), Pattern Reliability
  - Informed: Decision Engine, Monitoring, Audit Log

HOW:
  1. Get regime from enhanced_regime.get_current_regime()
  2. Get regime-specific weights from ai_learning.get_regime_weights()
  3. For each ticker (928):
     a. Technical: compute RSI, MACD, ADX, BB, pattern → score 0-100
     b. Fundamental: score ROE, P/E, P/B, DER, growth → score 0-100
     c. Macro: score BI rate, inflasi, GDP → score 0-100
     d. Global: score S&P500, VIX, oil, gold → score 0-100
     e. Relationship: correlation, lead-lag → score 0-100
     f. Sentiment: NLP, foreign flow, Fear&Greed → score 0-100
     g. Composite: weighted sum (regime-specific weights) → conviction
  4. Save all scores to `scores` table
  5. Publish event: analysis.scores.computed

WHERE:
  - Backend Python, localhost
  - CPU bound (pandas vectorization)
  - GPU optional (cuda:1) untuk sentiment NLP (IndoBERT)

WHY:
  - Composite score adalah input untuk Decision Engine
  - Tanpa score, Decision Engine tidak bisa generate recommendation
  - Score stale > 1 hari → recommendation tidak valid

OUTPUT:
  - Primary: `scores` table (6 factor scores + composite per ticker per date)
  - Secondary: `technical_indicators` table (raw indicator values)
  - Event: analysis.scores.computed
  - Audit: `audit_log` table
  - Consumer: T-030 (Decision Engine), T-022 (Prediction Engine)

FAILURE HANDLING:
  - Single ticker error: skip, log, continue next ticker
  - Whole pipeline crash: partial scores saved, resume from last ticker
  - Regime detection fail: use default weights, log warning

IDEMPOTENCY:
  - Scores saved with INSERT OR REPLACE per (ticker, date, engine)
  - Re-running for same date → overwrites, no duplicate
```

```yaml
Task ID: T-010
Task Name: Technical Analysis
Owner: analysis/technical.py
SLA: < 2 menit untuk 928 tickers

WHAT:
  Compute 20+ technical indicators (RSI, MACD, ADX, ATR, Bollinger, OBV, Ichimoku, etc.)
  dan detect chart/candlestick patterns per ticker.

WHEN:
  - Schedule: 18:00 WIB daily (sub-task of T-019 pipeline)
  - Dependency: T-001 (EOD data)

WHO:
  - Responsible: TechnicalAnalysis.compute_all()
  - Accountable: Analysis Engine
  - Consulted: Decision Engine, Pattern Reliability
  - Informed: Monitoring

HOW:
  1. For each ticker (928):
     a. Load OHLCV (last 252 days minimum)
     b. Compute: MA20, MA50, ADX14, RSI14, MACD(12,26,9), ATR14, BB(20,2), OBV, Ichimoku, Williams %R, Stoch RSI
     c. Classify trend: Uptrend / Downtrend / Sideways
     d. Detect patterns: double bottom/top, head & shoulders, bullish/bearish engulfing, etc.
     e. Score 0-100 based on indicator composite
     f. Save: technical_indicators table + scores (technical)
  2. Publish event: analysis.technical.score

WHERE:
  - Backend Python, localhost
  - CPU bound (pandas vectorization)

WHY:
  - Sinyal teknikal adalah komponen utama decision engine (20% weight)
  - Pattern detection feeds Pattern Reliability engine

OUTPUT:
  - Primary: `technical_indicators` table (raw values), `scores` table (technical score 0-100)
  - Secondary: `pattern_analysis` table (detected patterns)
  - Consumer: T-019 (Pipeline), T-021 (Pattern Reliability), T-030 (Decision)

FAILURE HANDLING:
  - Single ticker error: skip, log, continue
  - Insufficient data (< 252 days): skip ticker, log

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, indicator) → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM technical_indicators WHERE date = today
  - Expected: ~928 rows
```

```yaml
Task ID: T-011
Task Name: Fundamental Analysis
Owner: analysis/fundamental.py
SLA: < 3 menit

WHAT:
  Score fundamental metrics: ROE, P/E, P/B, DER, EPS growth, EBITDA margin per ticker.

WHEN:
  - Schedule: 18:00 WIB daily (sub-task of T-019)
  - Dependency: T-001 (EOD data for market cap), fundamental_data table

WHO:
  - Responsible: FundamentalAnalysis.score()
  - Accountable: Analysis Engine
  - Consulted: Decision Engine
  - Informed: Monitoring

HOW:
  1. For each ticker: load fundamental_data (latest quarterly)
  2. Compute: ROE, P/E, P/B, DER, EPS growth, EBITDA margin, dividend yield
  3. Score 0-100: weighted composite (ROE 25%, P/E 20%, P/B 15%, DER 15%, growth 25%)
  4. Save: scores (fundamental)

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Fundamental score adalah 25% dari decision weight (terbesar)
  - Tanpa fundamental, decision engine hanya teknikal → tidak seimbang

OUTPUT:
  - Primary: `scores` table (fundamental, 0-100)
  - Consumer: T-019 (Pipeline), T-030 (Decision)

FAILURE HANDLING:
  - Missing fundamental data: use last known, log warning
  - yfinance fundamentals fail: use cached/stored data

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, engine='fundamental')

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM scores WHERE engine='fundamental' AND date=today
  - Expected: ~928 rows
```

```yaml
Task ID: T-012
Task Name: Macro Analysis
Owner: analysis/macro.py
SLA: < 30 detik

WHAT:
  Score kondisi makro ekonomi: BI rate, inflasi, GDP growth, USD/IDR.

WHEN:
  - Schedule: 18:05 WIB daily (sub-task of T-019)
  - Dependency: T-005 (macro data)

WHO:
  - Responsible: MacroAnalysis.score()
  - Accountable: Analysis Engine
  - Consulted: Decision Engine, Regime Detection
  - Informed: Monitoring

HOW:
  1. Load latest macro_data
  2. Score each indicator: BI rate (low=good), inflasi (low=good), GDP (high=good), USD/IDR (stable=good)
  3. Composite score 0-100
  4. Save: scores (macro)

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Macro adalah 15% dari decision weight
  - Macro menentukan regime (easing/tightening)

OUTPUT:
  - Primary: `scores` table (macro, 0-100)
  - Consumer: T-016 (Regime), T-019 (Pipeline), T-030 (Decision)

FAILURE HANDLING:
  - Missing macro data: use last known values

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, engine='macro')
  - Note: macro score is same for all tickers (market-wide)

VALIDATION:
  - Post-check: SELECT DISTINCT score FROM scores WHERE engine='macro' AND date=today
  - Expected: 1 unique score (same for all tickers)
```

```yaml
Task ID: T-013
Task Name: Global Market Analysis
Owner: analysis/global_market.py
SLA: < 30 detik

WHAT:
  Score pengaruh pasar global terhadap IDX: S&P 500, NASDAQ, VIX, crude oil, gold, DXY.

WHEN:
  - Schedule: 18:05 WIB daily (sub-task of T-019)
  - Dependency: T-006 (global market data)

WHO:
  - Responsible: GlobalMarketAnalysis.score()
  - Accountable: Analysis Engine
  - Consulted: Decision Engine
  - Informed: Monitoring

HOW:
  1. Load global tickers OHLCV
  2. Compute: S&P500 return (1d, 5d), VIX level, oil/gold trend, DXY direction
  3. Score 0-100: high when global bullish, low when risk-off
  4. Save: scores (global)

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Global market adalah 15% dari decision weight
  - VIX > 30 → risk-off → IDX cenderung turun

OUTPUT:
  - Primary: `scores` table (global, 0-100)
  - Consumer: T-019 (Pipeline), T-030 (Decision)

FAILURE HANDLING:
  - Missing global data: use last known, log warning

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, engine='global')
  - Note: global score is same for all tickers (market-wide)

VALIDATION:
  - Post-check: SELECT DISTINCT score FROM scores WHERE engine='global' AND date=today
  - Expected: 1 unique score
```

```yaml
Task ID: T-014
Task Name: Relationship Analysis
Owner: analysis/relationship.py
SLA: < 5 menit

WHAT:
  Compute correlation matrix, lead-lag relationships, dan intermarket analysis
  antar saham IDX dan global.

WHEN:
  - Schedule: 18:10 WIB daily (sub-task of T-019)
  - Dependency: T-001 (EOD data)

WHO:
  - Responsible: RelationshipEngine.compute()
  - Accountable: Analysis Engine
  - Consulted: Decision Engine, Portfolio Engine
  - Informed: Monitoring

HOW:
  1. Load OHLCV for all tickers (252-day window)
  2. Compute Pearson correlation matrix (928 x 928)
  3. Compute Granger causality for top pairs
  4. Compute lead-lag: which ticker leads which
  5. Score 0-100: based on diversification potential
  6. Save: relationship_matrix table + scores (relationship)

WHERE:
  - Backend Python, localhost
  - CPU bound (matrix computation)

WHY:
  - Relationship adalah 10% dari decision weight
  - Correlation matrix essential untuk portfolio diversification

OUTPUT:
  - Primary: `relationship_matrix` table (pairwise correlations)
  - Secondary: `scores` table (relationship, 0-100)
  - Consumer: T-019 (Pipeline), T-030 (Decision), T-033 (Portfolio)

FAILURE HANDLING:
  - Correlation computation OOM: reduce window to 126 days
  - Single pair error: skip, continue

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker_a, ticker_b, window)

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM relationship_matrix WHERE date=today
  - Expected: > 1000 pairs
```

```yaml
Task ID: T-015
Task Name: Sentiment Analysis
Owner: sentiment/engine.py
SLA: < 5 menit

WHAT:
  Compute sentiment score dari 6 sources: news NLP (IndoBERT), foreign flow,
  broker flow, social media (Reddit/X), Google Trends, Fear & Greed index.

WHEN:
  - Schedule: 18:10 WIB daily (sub-task of T-019)
  - Dependency: T-002 (foreign flow), T-003 (broker flow)

WHO:
  - Responsible: SentimentEngine.compute()
  - Accountable: Analysis Engine
  - Consulted: AI Learning (IndoBERT model), Decision Engine
  - Informed: Monitoring

HOW:
  1. News NLP: IndoBERT inference on latest news articles (GPU cuda:1)
  2. Foreign flow: net buy/sell asing → sentiment signal
  3. Broker flow: broker accumulation/distribution → sentiment signal
  4. Social media: Reddit/X scraping → NLP sentiment
  5. Google Trends: query volume for ticker keywords
  6. Fear & Greed: compute from multiple market signals
  7. Weighted composite: 6-source weighting → score 0-100
  8. Save: scores (sentiment)

WHERE:
  - Backend Python, localhost
  - GPU (cuda:1) for IndoBERT inference
  - I/O bound for social media scraping

WHY:
  - Sentiment adalah 15% dari decision weight
  - Foreign flow adalah sinyal kuat di IDX (asing dominan)

OUTPUT:
  - Primary: `scores` table (sentiment, 0-100)
  - Secondary: `fear_greed` table
  - Consumer: T-019 (Pipeline), T-022 (Prediction), T-030 (Decision)

FAILURE HANDLING:
  - IndoBERT CUDA error: fallback to CPU or lexicon-based NLP
  - Social media API down: skip source, use 5 remaining sources
  - News empty: neutral sentiment (50), log warning

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, engine='sentiment')

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM scores WHERE engine='sentiment' AND date=today
  - Expected: ~928 rows
```

```yaml
Task ID: T-016
Task Name: Regime Detection
Owner: analysis/enhanced_regime.py
SLA: < 30 detik

WHAT:
  Detect market regime menggunakan HMM: easing, tightening, growth, slowdown, risk_off.

WHEN:
  - Schedule: 18:15 WIB daily (sub-task of T-019)
  - Dependency: T-005 (macro), T-001 (IDX index data)

WHO:
  - Responsible: EnhancedRegime.detect()
  - Accountable: Analysis Engine
  - Consulted: AI Learning (regime weights), Decision Engine
  - Informed: Monitoring

HOW:
  1. Load macro indicators + IHSG returns
  2. Fit HMM on 252-day window
  3. Predict current regime state
  4. Map: state → regime label (easing/tightening/growth/slowdown/risk_off)
  5. Save: ai_weights table (regime tag for weight lookup)

WHERE:
  - Backend Python, localhost
  - CPU bound (HMM fitting)

WHY:
  - Regime menentukan weight set untuk decision engine
  - Regime growth → technical weight tinggi; regime tightening → fundamental weight tinggi

OUTPUT:
  - Primary: `ai_weights` table (current regime tag)
  - Consumer: T-019 (Pipeline weights), T-024 (Weight Opt), T-030 (Decision)

FAILURE HANDLING:
  - HMM fitting fail: use last known regime, log warning
  - Insufficient data: default to "growth" regime

IDEMPOTENCY:
  - INSERT OR REPLACE on (regime, date)

VALIDATION:
  - Post-check: SELECT regime FROM ai_weights WHERE date=today
  - Expected: 1 row with valid regime label
```

```yaml
Task ID: T-017
Task Name: Pattern Detection
Owner: analysis/technical.py
SLA: < 2 menit (runs within T-010)

WHAT:
  Detect chart patterns (double bottom/top, head & shoulders, triangles, flags)
  dan candlestick patterns (engulfing, doji, hammer, shooting star) per ticker.

WHEN:
  - Schedule: 18:15 WIB daily (sub-task of T-010/T-019)
  - Dependency: T-001 (EOD data)

WHO:
  - Responsible: TechnicalAnalysis.detect_patterns()
  - Accountable: Analysis Engine
  - Consulted: AI Learning (pattern reliability), Prediction Engine
  - Informed: Monitoring

HOW:
  1. For each ticker: load last 60 days OHLCV
  2. Detect chart patterns: scan for double bottom/top, H&S, triangles, flags, wedges
  3. Detect candlestick patterns: scan last 5 candles for engulfing, doji, hammer, etc.
  4. For each detected pattern:
     a. Record: ticker, pattern_name, detected_date, entry_price
     b. Store: pattern_analysis table
  5. Publish event: analysis.pattern.detected

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Pattern detection feeds Pattern Reliability engine (win-rate calculation)
  - Patterns are input to Prediction Engine fusion

OUTPUT:
  - Primary: `pattern_analysis` table (detected patterns with context)
  - Consumer: T-021 (Pattern Reliability), T-022 (Prediction), Pattern Journal

FAILURE HANDLING:
  - Single ticker pattern detection error: skip, continue
  - No patterns detected: normal (not all tickers have patterns daily)

IDEMPOTENCY:
  - INSERT pattern_analysis with unique (ticker, pattern_name, detected_date)
  - Re-run same date → new detections (patterns may differ with updated data)

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM pattern_analysis WHERE detected_date=today
  - Expected: 0-100 rows (variable)
```

```yaml
Task ID: T-018
Task Name: Factor Screening
Owner: analysis/factor_screener.py
SLA: < 1 menit

WHAT:
  Multi-factor composite ranking: value, momentum, quality, volatility, beta, size factors.

WHEN:
  - Schedule: 18:20 WIB daily (after T-019 pipeline)
  - Dependency: T-010, T-011 (technical + fundamental scores)

WHO:
  - Responsible: FactorScreener.screen()
  - Accountable: Analysis Engine
  - Consulted: Decision Engine, Portfolio Engine
  - Informed: Monitoring

HOW:
  1. Load all factor scores from T-010, T-011
  2. Compute factor composites: value (P/B, P/E), momentum (6m return), quality (ROE, margin), volatility (20d), beta, size
  3. Rank tickers per factor (percentile rank)
  4. Composite ranking: weighted average across factors
  5. Return top 50 tickers per factor and composite

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Factor screening untuk user discovery dan portfolio candidate pre-filter
  - Multi-factor approach lebih robust dari single-factor

OUTPUT:
  - Primary: In-memory result (API response)
  - Secondary: Exposed via /api/screen, /api/factors
  - Consumer: User (screener UI), T-033 (Portfolio Pipeline)

FAILURE HANDLING:
  - Missing factor data: skip factor, use available factors
  - All factors missing: return empty, log error

IDEMPOTENCY:
  - In-memory only, no DB write → inherently idempotent

VALIDATION:
  - Post-check: API /api/screen returns non-empty result
  - Expected: 50+ tickers in composite ranking
```

### 4.3 Runbook: Prediction & AI Layer (T-020 to T-027)

```yaml
Task ID: T-020
Task Name: LSTM Prediction
Owner: ai_learning/deep_learning.py
SLA: < 20 menit untuk 928 tickers (GPU batch inference)

WHAT:
  Run per-ticker LSTM model inference untuk predict harga N hari ke depan.
  Setiap ticker punya model sendiri (personalized).

WHEN:
  - Schedule: 18:00 WIB daily (parallel with T-019 score pipeline)
  - Dependency: T-001 (latest OHLCV data)

WHO:
  - Responsible: PerTickerLSTM.predict() / DeepLearning.predict()
  - Accountable: AI Learning Layer
  - Informed: Prediction Engine (T-022), Monitoring

HOW:
  1. For each ticker (928):
     a. Load model: models/lstm/{ticker}_lstm.pt
     b. Load features: last 60 days OHLCV → engineer 20+ features
     c. Inference: model.forward(features) on GPU cuda:1
     d. Output: expected_return (float), confidence_raw (float), horizon_days (int)
     e. Batch: batch_size ≤ 64 (4GB VRAM constraint)
  2. Store results in-memory (consumed by T-022)

WHERE:
  - Backend Python, localhost
  - GPU (cuda:1) — primary
  - CPU fallback if CUDA unavailable

WHY:
  - LSTM menangkap pola non-linear yang tidak tertangkap indicator tradisional
  - Per-ticker model → personalized untuk karakteristik unik setiap saham

OUTPUT:
  - Primary: In-memory dict {ticker: {expected_return, confidence_raw, horizon_days}}
  - Secondary: Stored to prediction_log by T-022 (fusion)
  - Consumer: T-022 (Prediction Engine Fusion)

FAILURE HANDLING:
  - Model file missing: fallback to factor-only prediction (skip LSTM component)
  - CUDA OOM: reduce batch_size to 32, retry
  - CUDA unavailable: fallback to CPU (slow, ~60 min for 928 tickers)
  - Single ticker inference error: skip, log, continue

IDEMPOTENCY:
  - Inference is read-only (no DB write) → inherently idempotent
  - T-022 stores results with unique prediction ID

VALIDATION:
  - Post-check: count predictions in-memory
  - Expected: ~928 predictions (or fewer if some tickers skipped)
  - Alert if: < 800 predictions (> 14% skip rate)
```

```yaml
Task ID: T-021
Task Name: Pattern Reliability Lookup
Owner: analysis/pattern_reliability.py
SLA: < 30 detik

WHAT:
  Lookup win-rate historis untuk setiap pattern yang terdeteksi (T-017) per ticker.

WHEN:
  - Schedule: 18:15 WIB daily (after T-017 pattern detection)
  - Dependency: T-017 (pattern detection), pattern_analysis table (historical)

WHO:
  - Responsible: PatternReliabilityEngine.score_pattern()
  - Accountable: AI Learning Layer
  - Consulted: Prediction Engine, Decision Engine
  - Informed: Monitoring

HOW:
  1. For each pattern detected in T-017:
     a. Query: SELECT * FROM pattern_analysis WHERE ticker=X AND pattern_name=Y
     b. Compute: win_rate = success_count / total_occurrences
     c. Compute: avg_return, reliability_rating (excellent/good/average/poor)
  2. Return dict {pattern_name: {win_rate, total, success, fail, avg_return, rating}}
  3. Feed to T-022 (Prediction Engine) for fusion

WHERE:
  - Backend Python, localhost
  - CPU bound (SQL query + aggregation)

WHY:
  - Win-rate historis menentukan seberapa reliable suatu pola untuk saham tertentu
  - Double bottom di BBCA mungkin 72% win-rate, tapi di ASII hanya 35%

OUTPUT:
  - Primary: In-memory dict (consumed by T-022)
  - Secondary: Pattern Journal entries (via T-023 evaluation)
  - Consumer: T-022 (Prediction Engine), T-030 (Decision)

FAILURE HANDLING:
  - No historical data for pattern: default win_rate = 0.50, log
  - Query timeout: use cached results, log warning

IDEMPOTENCY:
  - Read-only (no DB write) → inherently idempotent

VALIDATION:
  - Post-check: all detected patterns have reliability score
  - Expected: 100% coverage for detected patterns
```

```yaml
Task ID: T-022
Task Name: Prediction Engine (Fusion)
Owner: analysis/prediction_engine.py (NEW)
SLA: < 30 menit untuk 928 tickers

WHAT:
  Fuse LSTM prediction + pattern reliability + factor scores + regime +
  foreign flow + sentiment → final prediction per saham.

WHEN:
  - Schedule: 18:20 WIB daily (after T-019 score computation)
  - Dependency: T-019 (scores), T-020 (LSTM), T-017 (pattern detection)
  - Skip: if T-019 failed

WHO:
  - Responsible: PredictionEngine.predict()
  - Accountable: AI Learning Layer
  - Consulted: Analysis Layer (factor scores), Pattern Reliability
  - Informed: Portfolio Pipeline, XAI, Monitoring

HOW:
  1. For each ticker (928):
     a. Load LSTM prediction from T-020
     b. Load pattern reliabilities from T-021
     c. Load factor scores from T-019
     d. Get regime from T-016
     e. Get foreign flow signal from T-002
     f. Get sentiment score from T-015
     g. Get regime-specific weights from AI Learning
     h. Fuse: weighted average → direction + confidence + expected return
     i. Build reasoning: top 5 factors
     j. Store prediction to `prediction_log` table
  2. Publish event: prediction.completed

WHERE:
  - Backend Python, localhost
  - CPU bound (fusion computation)
  - GPU already used in T-020 (LSTM inference)

WHY:
  - Single source of truth untuk prediksi per saham
  - Tanpa fusion, sinyal dari masing-masing engine tidak terintegrasi
  - Portfolio Pipeline butuh prediction + confidence untuk filter

OUTPUT:
  - Primary: `prediction_log` table (928 predictions)
  - Event: prediction.completed
  - Audit: `audit_log` table
  - Consumer: T-033 (Portfolio Pipeline), T-032 (XAI), User

FAILURE HANDLING:
  - LSTM model missing for ticker: fallback to factor-only prediction
  - Pattern reliability missing: use default 0.50 win-rate
  - CUDA error: fallback to CPU for LSTM inference
  - Single ticker error: skip, log, continue

IDEMPOTENCY:
  - prediction_log uses unique ID per prediction
  - Re-running for same date → new predictions (new IDs), old ones remain
  - Status PENDING → SUCCESS/FAIL updated by T-023
```

### 4.4 Runbook: Self-Correction (T-023)

```yaml
Task ID: T-023
Task Name: Self-Correction Loop
Owner: ai_learning/error_analysis.py (NEW)
SLA: < 5 menit untuk ~100 pending predictions

WHAT:
  Evaluate all predictions whose horizon has passed. Compare predicted
  direction vs actual. If wrong, run root cause analysis and apply corrections.

WHEN:
  - Schedule: 16:30 WIB daily (post-close, before new predictions)
  - Dependency: T-001 (EOD data for actual prices)
  - Frequency: daily

WHO:
  - Responsible: ErrorAnalysisEngine.evaluate_all_pending()
  - Accountable: AI Learning Layer
  - Consulted: Pattern Reliability, Regime Engine
  - Informed: Pattern Journal, AI Learning (weights), Monitoring

HOW:
  1. Query: SELECT * FROM prediction_log WHERE status = 'PENDING'
    AND target_date <= today
  2. For each pending prediction:
     a. Load actual OHLCV from prediction_date to target_date
     b. Compute actual_return, actual_direction
     c. If predicted == actual: status = SUCCESS → reinforce patterns
     d. If predicted != actual: status = FAIL → analyze_error()
       - Classify error type (8 types, see doc 46 §4.3)
       - Root cause: which factor wrong, which pattern failed, regime change?
       - Corrections: reduce_weight, reduce_pattern_confidence, etc.
       - Generate lesson text
       - Save to `error_analysis` table
       - Apply corrections to AI Learning weights
       - Record to Pattern Journal
  3. Summary: "Evaluated 100 predictions: 72 success, 28 fail. 15 corrections applied."

WHERE:
  - Backend Python, localhost
  - CPU bound (no GPU needed)

WHY:
  - Sistem belajar dari kesalahan → meningkatkan akurasi dari waktu ke waktu
  - Tanpa self-correction, sistem mengulang kesalahan yang sama
  - Pattern Journal menjadi database pengetahuan "what NOT to do"

OUTPUT:
  - Primary: `prediction_log` table (status updated)
  - Secondary: `error_analysis` table (root cause + corrections)
  - Tertiary: `pattern_journal` table (lesson learned entries)
  - AI Learning: weights adjusted in `ai_weights` table
  - Audit: `audit_log` table
  - Consumer: AI Learning (T-024), Pattern Journal, User (lessons display)

FAILURE HANDLING:
  - No OHLCV data for evaluation date: mark as EXPIRED, skip
  - Correction fails (weight already at minimum): log, skip
  - Batch fails: partial evaluations saved, resume next day

IDEMPOTENCY:
  - Each prediction evaluated once (status changes PENDING → SUCCESS/FAIL)
  - Re-running for same prediction → no-op (status already updated)
  - Corrections are additive (weight adjustments accumulate)
```

```yaml
Task ID: T-024
Task Name: AI Weight Optimization
Owner: ai_learning/engine.py
SLA: < 30 menit (weekly)

WHAT:
  Optimize factor weights per regime menggunakan Ridge regression on historical
  scores vs forward returns.

WHEN:
  - Schedule: 20:00 WIB weekly (Sabtu malam)
  - Dependency: T-023 (self-correction feedback from week)

WHO:
  - Responsible: AILearningEngine.optimize_weights()
  - Accountable: AI Learning Layer
  - Consulted: Decision Engine (weight consumer)
  - Informed: Monitoring

HOW:
  1. Load historical scores (last 252 days) per regime
  2. Load forward returns (5d, 10d, 20d) per ticker
  3. For each regime:
     a. Fit Ridge regression: scores → forward returns
     b. Extract coefficients → normalize to weights (sum=1.0)
     c. Clip weights to [0.05, 0.50] (prevent extreme weights)
  4. Save: ai_weights table (regime, factor, weight)
  5. Validate: out-of-sample R² > 0 (model adds value)

WHERE:
  - Backend Python, localhost
  - CPU bound (regression fitting)

WHY:
  - Dynamic weight adjustment berdasarkan regime → adaptif
  - Regime growth: technical weight tinggi; regime tightening: fundamental weight tinggi
  - Tanpa optimization, weights static → tidak adaptif terhadap perubahan market

OUTPUT:
  - Primary: `ai_weights` table (per regime, per factor, per date)
  - Consumer: T-019 (Pipeline), T-030 (Decision Engine)

FAILURE HANDLING:
  - Regression fail: keep last known weights, log warning
  - OOS R² < 0: revert to default weights, log warning
  - Insufficient data: skip optimization this week

IDEMPOTENCY:
  - INSERT OR REPLACE on (regime, factor, date) → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM ai_weights WHERE date=today
  - Expected: 30 rows (5 regimes × 6 factors)
  - Alert if: weights don't sum to 1.0 per regime
```

```yaml
Task ID: T-025
Task Name: LSTM Retrain
Owner: ai_learning/per_ticker_lstm.py (NEW)
SLA: < 8 jam (weekly, 928 models)

WHAT:
  Retrain per-ticker LSTM models dengan data terbaru (termasuk failure cases
  dari T-023 self-correction).

WHEN:
  - Schedule: 20:00 WIB weekly (Sabtu malam)
  - Dependency: T-001 (latest OHLCV), T-023 (failure cases)

WHO:
  - Responsible: PerTickerLSTM.train()
  - Accountable: AI Learning Layer
  - Informed: Monitoring

HOW:
  1. For each ticker (928):
     a. Load OHLCV (full history, min 252 days)
     b. Engineer features: 20+ technical indicators
     c. Create sequences: lookback=60, horizon=20
     d. Train: PyTorch LSTM, GPU cuda:1, batch_size ≤ 64, hidden_dim ≤ 256
     e. Validate: walk-forward OOS metrics
     f. Save model: models/lstm/{ticker}_lstm.pt
     g. Update model registry: version, metrics, date
  2. Log: "Retrained 928 models, avg OOS R² = 0.12"

WHERE:
  - Backend Python, localhost
  - GPU (cuda:1) — primary, 4-8 hours
  - VRAM constraint: 4GB → batch_size ≤ 64, hidden_dim ≤ 256

WHY:
  - Model drift: LSTM perlu update dengan data terbaru
  - Failure cases dari T-023 → model belajar dari kesalahan
  - Tanpa retrain, model menjadi stale → prediksi tidak akurat

OUTPUT:
  - Primary: `models/lstm/{ticker}_lstm.pt` (928 model files)
  - Secondary: model_registry table (version, metrics)
  - Consumer: T-020 (LSTM Prediction, next week)

FAILURE HANDLING:
  - CUDA OOM: reduce batch_size to 32, retry
  - CUDA unavailable: skip retrain this week, log SEV-1
  - Single ticker training fail: skip, keep old model, log
  - > 10% models fail: alert, investigate systemic issue

IDEMPOTENCY:
  - Overwrite model file → safe to re-run (new model replaces old)
  - Model registry: INSERT OR REPLACE on (ticker, version)

VALIDATION:
  - Post-check: count .pt files in models/lstm/
  - Expected: 928 files
  - Alert if: < 900 files (> 3% missing)
```

```yaml
Task ID: T-026
Task Name: Pattern Discovery
Owner: analysis/pattern_discovery.py (NEW)
SLA: < 1 jam (weekly)

WHAT:
  Discover new, undocumented patterns via clustering on 20-day price windows.
  Extract all windows, cluster similar shapes, check outcome consistency.

WHEN:
  - Schedule: 20:00 WIB weekly (Sabtu malam, parallel with T-025)
  - Dependency: T-001 (OHLCV history)

WHO:
  - Responsible: PatternDiscovery.discover()
  - Accountable: AI Learning Layer
  - Consulted: Pattern Journal, Prediction Engine
  - Informed: Monitoring

HOW:
  1. For each ticker:
     a. Extract all 20-day windows from OHLCV
     b. Normalize: z-score normalization per window
     c. Cluster: K-means (n_clusters=20) on normalized windows
     d. For each cluster:
        - Compute forward returns (20d) for all members
        - If ≥ 5 occurrences AND |avg_return| > 2%: significant pattern
        - Record: pattern_name, occurrences, avg_return, win_rate, characteristics
  2. Save: discovered_patterns table
  3. Flag for validation: patterns with win_rate > 65% → candidate for naming

WHERE:
  - Backend Python, localhost
  - CPU + GPU (K-means can use GPU for distance computation)

WHY:
  - Pola baru mungkin belum dikenal oleh pattern detection tradisional
  - ML-driven discovery menemukan pola yang human eye miss
  - Setiap saham mungkin punya pola unik yang tidak generic

OUTPUT:
  - Primary: `discovered_patterns` table (new patterns per ticker)
  - Consumer: Pattern Journal, T-022 (Prediction Engine if validated)

FAILURE HANDLING:
  - Clustering fail: skip ticker, continue
  - No significant patterns found: normal (not all tickers have new patterns)

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, cluster_id, date)
  - Re-run → may find different clusters (K-means random init), acceptable

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM discovered_patterns WHERE date=this_week
  - Expected: 0-200 rows (variable)
```

```yaml
Task ID: T-027
Task Name: Walk-Forward Validation
Owner: ai_learning/walk_forward.py
SLA: < 1 jam (weekly)

WHAT:
  Out-of-sample validation untuk semua LSTM models menggunakan rolling window
  train/test dengan purged time-series split.

WHEN:
  - Schedule: 20:00 WIB weekly (Sabtu malam, after T-025 retrain)
  - Dependency: T-025 (retrained models)

WHO:
  - Responsible: WalkForward.validate()
  - Accountable: AI Learning Layer
  - Informed: Monitoring, Model Registry

HOW:
  1. For each ticker:
     a. Split data: rolling windows (train 180d, test 60d, purge 5d)
     b. For each window:
        - Train LSTM on train period
        - Predict on test period
        - Compute OOS metrics: R², RMSE, directional accuracy
     c. Aggregate: avg OOS R², avg directional accuracy
  2. Compare: this week's model vs last week's model
  3. Save metrics to model_registry

WHERE:
  - Backend Python, localhost
  - GPU (cuda:1) for LSTM training in validation
  - CPU for metrics computation

WHY:
  - Validasi model tidak overfit
  - Deteksi model degradation (OOS R² declining)
  - Purged TSS mencegah data leakage

OUTPUT:
  - Primary: model_registry table (OOS metrics per model per version)
  - Consumer: T-025 (retrain decision), T-022 (prediction confidence)

FAILURE HANDLING:
  - Validation crash: skip, use last week's metrics
  - OOS R² < 0: flag model as "degraded", alert

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, version, metric_name)

VALIDATION:
  - Post-check: SELECT AVG(oos_r2) FROM model_registry WHERE date=this_week
  - Expected: > 0 (model adds value)
  - Alert if: avg OOS R² < -0.05 (model worse than naive)
```

### 4.5 Runbook: Decision & Risk Layer (T-030 to T-034)

```yaml
Task ID: T-030
Task Name: Decision Engine
Owner: decision/engine.py
SLA: < 30 detik untuk 928 tickers

WHAT:
  6-factor weighted scoring → recommendation: BUY / HOLD / WATCHLIST / AVOID
  dengan conviction level dan entry/exit levels.

WHEN:
  - Schedule: 18:25 WIB daily (after T-019 pipeline + T-022 prediction)
  - Dependency: T-019 (scores), T-022 (predictions), T-016 (regime weights)

WHO:
  - Responsible: DecisionEngine.recommend()
  - Accountable: Decision Engine
  - Consulted: AI Learning (weights), Risk Engine, XAI
  - Informed: Monitoring, User (via API)

HOW:
  1. Load regime-specific weights from ai_weights (T-024/T-016)
  2. For each ticker:
     a. Load 6 factor scores from T-019
     b. Load prediction from T-022 (direction, confidence)
     c. Compute weighted composite: sum(score_i * weight_i)
     d. Apply regime filter: if regime=risk_off, raise conviction threshold
     e. Map composite → action:
        - composite > 70 + prediction UP → BUY
        - composite 55-70 → WATCHLIST
        - composite 40-55 → HOLD
        - composite < 40 + prediction DOWN → AVOID
     f. Compute conviction: 0-100 (based on composite + prediction confidence)
     g. Compute entry range, stop loss (ATR-based), take profit
  3. Save: scores (composite) + recommendation in API response
  4. Publish event: decision.recommendation.created

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Decision engine adalah output utama untuk user
  - Tanpa decision engine, user hanya punya raw scores → tidak actionable

OUTPUT:
  - Primary: `scores` table (composite score + action + conviction)
  - Secondary: API response /api/recommend/{ticker}
  - Consumer: T-031 (Risk), T-032 (XAI), User, T-033 (Portfolio)

FAILURE HANDLING:
  - Missing factor score: use 50 (neutral), log warning
  - Missing prediction: use factor-only, log
  - Single ticker error: skip, continue

IDEMPOTENCY:
  - INSERT OR REPLACE on (ticker, date, engine='composite')

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM scores WHERE engine='composite' AND date=today
  - Expected: ~928 rows
```

```yaml
Task ID: T-031
Task Name: Risk Assessment
Owner: risk/engine.py
SLA: < 1 menit

WHAT:
  Compute VaR (95%, 99%), CVaR, position sizing (Kelly), stop-loss/take-profit
  (ATR-based), drawdown analysis per ticker.

WHEN:
  - Schedule: 18:30 WIB daily (after T-030 decision)
  - Dependency: T-030 (recommendation), T-001 (OHLCV for VaR computation)

WHO:
  - Responsible: RiskEngine.analyze()
  - Accountable: Risk Engine
  - Consulted: Decision Engine, Portfolio Engine, Execution Engine
  - Informed: Monitoring

HOW:
  1. For each ticker with action BUY or WATCHLIST:
     a. Compute VaR 95%: historical simulation (252-day window)
     b. Compute CVaR 95%: average of tail losses
     c. Compute max drawdown (252-day)
     d. Position sizing: Kelly criterion → fraction = (p*b - q) / b
     e. Stop-loss: entry_price - 2 * ATR14
     f. Take-profit: entry_price + 3 * ATR14
     g. Risk flags: high_volatility, high_drawdown, low_liquidity
  2. Attach risk metrics to recommendation

WHERE:
  - Backend Python, localhost
  - CPU bound (historical simulation)

WHY:
  - Risk assessment mencegah oversized positions
  - VaR > 8% → skip ticker (too risky)
  - Tanpa risk check, user bisa overexpose ke saham berisiko

OUTPUT:
  - Primary: Risk metrics attached to recommendation (API response)
  - Consumer: T-033 (Portfolio), T-040/T-041 (Execution), User

FAILURE HANDLING:
  - Insufficient data for VaR: use parametric VaR (assumes normal distribution)
  - Kelly negative: position_size = 0 (don't trade)

IDEMPOTENCY:
  - Read-only computation → inherently idempotent
  - Results attached to T-030 recommendation (stored together)

VALIDATION:
  - Post-check: all BUY recommendations have VaR + position size
  - Expected: 100% coverage for BUY/WATCHLIST
```

```yaml
Task ID: T-032
Task Name: XAI Narrative
Owner: xai/engine.py
SLA: < 30 detik

WHAT:
  Generate narrative explanation dalam Bahasa Indonesia untuk setiap
  recommendation: top 5 factors, pattern reasoning, risk notes.

WHEN:
  - Schedule: 18:30 WIB daily (after T-030 decision)
  - Dependency: T-030 (recommendation), T-022 (prediction reasoning)

WHO:
  - Responsible: XAIEngine.explain()
  - Accountable: XAI Engine
  - Consulted: Decision Engine, Prediction Engine
  - Informed: User (via API)

HOW:
  1. For each ticker with recommendation:
     a. Load: composite score, factor breakdown, prediction, patterns
     b. Identify top 5 contributing factors (highest score * weight)
     c. Generate narrative (template-based, Bahasa Indonesia):
        "BBCA.JK direkomendasikan WATCHLIST dengan conviction 55.
         Faktor utama: Fundamental (80, weight 25%), Technical (56, weight 20%).
         Pola terdeteksi: double_bottom (win-rate 72%).
         Prediksi: UP +5.2% dalam 20 hari, confidence 72%.
         Risiko: VaR 95% = 4.2%, max drawdown 252d = -12%.
         Entry: 7850-7950, SL: 7600, TP: 8500."
     d. Attach narrative to API response

WHERE:
  - Backend Python, localhost
  - CPU bound (template rendering)

WHY:
  - Explainable AI: user perlu tahu KENAPA direkomendasikan
  - Tanpa narrative, user tidak trust recommendation
  - Bahasa Indonesia untuk retail investor Indonesia

OUTPUT:
  - Primary: Narrative text in API response /api/explain/{ticker}
  - Consumer: User (frontend), T-051 (API)

FAILURE HANDLING:
  - Template rendering fail: return generic narrative, log error
  - Missing data: use "data tidak tersedia" in narrative

IDEMPOTENCY:
  - Read-only (no DB write) → inherently idempotent

VALIDATION:
  - Post-check: API /api/explain/BBCA.JK returns non-empty narrative
  - Expected: 200+ characters, contains "conviction", "faktor", "risiko"
```

```yaml
Task ID: T-033
Task Name: Portfolio Optimization
Owner: portfolio/candidate_pipeline.py (NEW)
SLA: < 2 menit

WHAT:
  Convert predictions → portfolio allocation: filter by confidence, risk check,
  correlation filter, HRP/Markowitz optimization → final weights per saham.

WHEN:
  - Schedule: 18:30 WIB daily (after T-022 prediction + T-031 risk)
  - Dependency: T-022 (predictions), T-031 (risk metrics), T-014 (correlation)

WHO:
  - Responsible: PortfolioCandidatePipeline.run()
  - Accountable: Portfolio Engine
  - Consulted: Risk Engine, Decision Engine, AI Learning
  - Informed: User, Monitoring

HOW:
  1. Load all predictions from T-022
  2. Filter: confidence > 60, direction UP, expected_return > 2%
  3. Risk check: VaR < 8%, max_drawdown < 25%, avg_volume > 100K
  4. Correlation filter: remove highly correlated (> 0.7) candidates
  5. Optimize: HRP (Hierarchical Risk Parity) on covariance matrix
  6. Cap: max single weight = 20%
  7. Save: portfolio_candidates table

WHERE:
  - Backend Python, localhost
  - CPU bound (optimization)

WHY:
  - Output akhir pipeline: dari 928 saham → ~10-15 kandidat portofolio
  - Tanpa optimization, user tidak tahu berapa alokasi per saham
  - HRP robust terhadap estimation error (tidak perlu matrix inversion)

OUTPUT:
  - Primary: `portfolio_candidates` table (ticker, weight, prediction_id, entry, SL, TP)
  - Consumer: User (portfolio UI), T-041 (Execution if auto-trade)

FAILURE HANDLING:
  - No candidates pass filter: return empty, log info
  - Optimization fail (singular matrix): use equal weight, log warning
  - All candidates correlated: reduce correlation threshold, retry

IDEMPOTENCY:
  - New allocation = new ID per date → safe to re-run (old allocation remains)

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM portfolio_candidates WHERE allocation_date=today
  - Expected: 5-20 candidates
  - Alert if: 0 candidates (pipeline produced nothing)
```

```yaml
Task ID: T-034
Task Name: Portfolio Rebalancing
Owner: portfolio/rebalancer.py
SLA: < 30 detik

WHAT:
  Check drift antara current portfolio weights vs target weights.
  Suggest rebalance trades jika drift > threshold.

WHEN:
  - Schedule: 16:30 WIB daily (post-close)
  - Dependency: T-001 (current prices for portfolio valuation)

WHO:
  - Responsible: Rebalancer.check_drift()
  - Accountable: Portfolio Engine
  - Consulted: Risk Engine
  - Informed: User

HOW:
  1. Load current portfolio positions
  2. Load target weights from latest T-033 allocation
  3. Compute current weights: position_value / total_portfolio_value
  4. Compute drift: |current_weight - target_weight| per ticker
  5. If max drift > 5%: suggest rebalance trades
  6. Output: list of rebalance suggestions (buy/sell to align to target)

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Portfolio drift → risk profile berubah
  - Tanpa rebalancing, winner stocks dominate → concentration risk

OUTPUT:
  - Primary: Rebalance suggestions (in-memory / API response)
  - Consumer: User (portfolio UI)

FAILURE HANDLING:
  - No portfolio positions: skip, log info
  - No target weights: skip, log warning

IDEMPOTENCY:
  - Read-only computation → inherently idempotent

VALIDATION:
  - Post-check: if portfolio exists, rebalance suggestions generated
  - Expected: 0-10 suggestions depending on drift
```

### 4.6 Runbook: Execution & Monitoring (T-040 to T-046)

```yaml
Task ID: T-040
Task Name: Paper Trading
Owner: paper_trading/simulator.py
SLA: Real-time (event-driven, < 1 detik per trade)

WHAT:
  Simulate order execution dengan mock broker: track fills, PnL, equity curve.
  Tidak ada uang real.

WHEN:
  - Schedule: 09:00-15:50 WIB (market hours, if enabled)
  - Trigger: Decision engine recommendation or user manual order

WHO:
  - Responsible: PaperTradingSimulator.execute()
  - Accountable: Execution Engine
  - Consulted: Decision Engine, Risk Engine, AI Learning
  - Informed: User, Monitoring

HOW:
  1. Receive signal from T-030 (or user manual order)
  2. Mock fill: use current price ± slippage (0.1%)
  3. Round to IDX lot size (100 shares)
  4. Deduct fees: broker (0.15%) + levy (0.025%)
  5. Update: position, cash, equity
  6. Save: paper_trades table
  7. Publish event: paper_trade.executed

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Test strategi tanpa risiko uang real
  - Validasi recommendation quality sebelum live trading
  - AI Learning: paper trade results → feedback untuk weight optimization

OUTPUT:
  - Primary: `paper_trades` table (ticker, action, price, shares, fees, pnl)
  - Secondary: equity curve (in-memory / API)
  - Consumer: User, T-024 (AI Learning feedback)

FAILURE HANDLING:
  - Price data unavailable: skip fill, log warning
  - Insufficient cash: reject order, log

IDEMPOTENCY:
  - Each trade has unique ID → safe to re-run (new trade = new ID)
  - Re-submitting same order → new trade (not deduplicated)

VALIDATION:
  - Post-check: paper_trades table has entries for today (if signals generated)
  - Expected: 0-10 trades per day
```

```yaml
Task ID: T-041
Task Name: Auto Trading
Owner: execution/automated.py
SLA: Real-time (< 5 detik from signal to order)

WHAT:
  Execute real orders via broker API (Sinarmas/BNI) berdasarkan decision engine
  signals. Hanya jika auto_trade_enabled = true.

WHEN:
  - Schedule: 09:00-15:50 WIB (market hours, if enabled)
  - Trigger: Decision engine BUY/SELL signal
  - Prerequisite: auto_trade_enabled = true (user opt-in)

WHO:
  - Responsible: AutomatedTrader.run_loop()
  - Accountable: **User** (user is Accountable for auto-trading decisions)
  - Consulted: Decision Engine, Risk Engine, Portfolio Engine
  - Informed: Monitoring, Audit Log

HOW:
  1. run_loop(tickers, interval=15s):
     a. For each ticker: get recommendation from T-030
     b. If BUY and no position:
        - Risk check: VaR, position sizing from T-031
        - Check: daily_loss < DAILY_LOSS_LIMIT
        - Check: market is open (T-043)
        - Check: ticker not in auto-reject
        - Submit order: broker API (buy, shares, price)
        - Save: orders table
        - Telegram notification
     c. If SELL and has position:
        - Submit order: broker API (sell, shares, price)
        - Close position, realize PnL
        - Save: orders table
        - Telegram notification
     d. monitor_positions(): check SL/TP every 60s
  2. Circuit breaker: if daily_loss > limit → halt trading

WHERE:
  - Backend Python, localhost
  - Network bound (broker API)

WHY:
  - Eksekusi otomatis berdasarkan sistem → disiplin, no emotion
  - User opt-in: user bertanggung jawab (Accountable)
  - Circuit breaker mencegah catastrophic loss

OUTPUT:
  - Primary: `orders` table (real orders)
  - Secondary: broker API confirmation
  - Tertiary: Telegram notification
  - Consumer: User, Audit Log, AI Learning (for feedback)

FAILURE HANDLING:
  - Broker API down: halt trading, alert SEV-1
  - Order rejected: log reason, alert user
  - Daily loss limit hit: halt trading, persist halt state, alert
  - Market closed: skip, log info

IDEMPOTENCY:
  - Each order has unique ID → safe to re-run
  - BUT: duplicate order submission must be prevented (idempotency key to broker API)

VALIDATION:
  - Post-check: orders table has entries for today (if signals + auto-trade enabled)
  - Alert if: unexpected order or position mismatch
```

```yaml
Task ID: T-042
Task Name: Position Monitor
Owner: execution/automated.py
SLA: < 5 detik per check

WHAT:
  Monitor open positions: check stop-loss, take-profit, trailing stop,
  daily loss limit.

WHEN:
  - Schedule: Every 60 seconds during market hours (09:00-15:50 WIB)
  - Dependency: Price feed (Yahoo Finance or broker API)

WHO:
  - Responsible: AutomatedTrader.monitor_positions()
  - Accountable: Execution Engine
  - Consulted: Risk Engine
  - Informed: User (via alert), Monitoring

HOW:
  1. For each open position:
     a. Get current price
     b. If price ≤ stop_loss: trigger SELL (stop-loss hit)
     c. If price ≥ take_profit: trigger SELL (take-profit hit)
     d. If price > highest_since_entry: update trailing stop
     e. Compute unrealized PnL
  2. Check daily loss: if daily_loss > DAILY_LOSS_LIMIT → halt trading
  3. Alert user via Telegram if SL/TP hit

WHERE:
  - Backend Python, localhost
  - CPU + network bound (price polling)

WHY:
  - Protect capital: stop-loss mencegah large losses
  - Trailing stop lock in profits
  - Daily loss limit mencegah catastrophic day

OUTPUT:
  - Primary: Position updates (in-memory)
  - Secondary: Orders (if SL/TP triggered)
  - Tertiary: Telegram alert
  - Consumer: User, Audit Log

FAILURE HANDLING:
  - Price feed unavailable: use last known price, log warning
  - Position data corrupt: halt, alert SEV-0

IDEMPOTENCY:
  - Read-only check → inherently idempotent
  - SL/TP trigger: one-time (position closed)

VALIDATION:
  - Post-check: all open positions have current price + PnL
  - Expected: 100% coverage
```

```yaml
Task ID: T-043
Task Name: Market Status Check
Owner: data/storage.py
SLA: < 1 detik

WHAT:
  Check apakah IDX sedang open, apakah ticker dalam auto-reject, apakah hari libur.

WHEN:
  - Schedule: Every 5 minutes during market hours
  - Also: on-demand (called by T-041 before each order)

WHO:
  - Responsible: Storage.is_idx_open() / is_auto_reject()
  - Accountable: Data Acquisition Engine
  - Consulted: Execution Engine
  - Informed: Monitoring

HOW:
  1. Query market_calendar: is today a trading day?
  2. Check current time: 09:00-11:30 (Sesi 1) or 14:00-15:50 (Sesi 2)?
  3. If trading day + market hours: return open=True
  4. Check auto-reject: query IDX API or cached data

WHERE:
  - Backend Python, localhost
  - CPU bound (DB query)

WHY:
  - Mencegah order saat market closed
  - Mencegah order pada ticker yang auto-reject (tidak bisa trading)

OUTPUT:
  - Primary: Boolean (market_open, ticker_tradeable)
  - Consumer: T-041 (Auto Trade), T-042 (Position Monitor)

FAILURE HANDLING:
  - market_calendar query fail: default to closed (safe), log error

IDEMPOTENCY:
  - Read-only → inherently idempotent

VALIDATION:
  - Post-check: correct status returned during market hours
  - Expected: open=True during 09:00-15:50 WIB on trading days
```

```yaml
Task ID: T-044
Task Name: System Health Monitor
Owner: monitoring/engine.py
SLA: < 10 detik per check

WHAT:
  Health check semua komponen sistem: DB, API, GPU, scheduler, data freshness,
  engine status.

WHEN:
  - Schedule: Every 5 minutes, 24/7 (including holidays)

WHO:
  - Responsible: MonitoringEngine.check_all()
  - Accountable: Monitoring Engine
  - Informed: User (via dashboard), Telegram (if alert)

HOW:
  1. Check DB: SELECT COUNT(*) FROM ohlcv (is DB responsive?)
  2. Check API: GET /api/health (is API responsive?)
  3. Check GPU: nvidia-smi (is CUDA available?)
  4. Check data freshness: latest date in ohlcv = today?
  5. Check engine status: last run timestamp per engine
  6. Compute health score 0-100
  7. If score < 70: alert via Telegram

WHERE:
  - Backend Python, localhost
  - CPU bound

WHY:
  - Detect system issues sebelum user terdampak
  - Data stale > 1 hari → semua analysis tidak valid

OUTPUT:
  - Primary: `audit_log` entries (health check results)
  - Secondary: API /api/monitor
  - Tertiary: Telegram alert (if unhealthy)
  - Consumer: User (dashboard), Debugging

FAILURE HANDLING:
  - Monitor itself crash: restart via systemd, alert
  - DB unresponsive: alert SEV-0

IDEMPOTENCY:
  - Read-only checks → inherently idempotent
  - Audit log: append-only (new entries each check)

VALIDATION:
  - Post-check: audit_log has health check entry every 5 minutes
  - Expected: ~288 entries per day (24h / 5min)
```

```yaml
Task ID: T-045
Task Name: Telegram Notification
Owner: utils/telegram_notifier.py
SLA: < 5 detik (send message)

WHAT:
  Send alert/notification ke user via Telegram Bot API.

WHEN:
  - Trigger: Event-driven (SEV-0, SEV-1, SL/TP hit, pipeline complete, trade executed)

WHO:
  - Responsible: TelegramNotifier.send()
  - Accountable: **User** (user owns the Telegram bot)
  - Consulted: Monitoring Engine (trigger source)
  - Informed: User

HOW:
  1. Receive alert payload (severity, message, timestamp)
  2. Format: "[SEV-1] Yahoo API down. Pipeline skipped today. 2026-08-05 16:35 WIB"
  3. Send: Telegram Bot API → user chat
  4. Log: audit_log (notification sent)

WHERE:
  - Backend Python, localhost
  - Network bound (Telegram API)

WHY:
  - Real-time alert ke user untuk events penting
  - User tidak perlu cek dashboard 24/7

OUTPUT:
  - Primary: Telegram message to user
  - Secondary: audit_log entry
  - Consumer: User

FAILURE HANDLING:
  - Telegram API down: retry 3x, log error, skip (non-critical)
  - Bot token invalid: log SEV-1, skip notifications

IDEMPOTENCY:
  - Each notification is independent → safe to retry
  - Duplicate notifications: acceptable (better over-alert than under-alert)

VALIDATION:
  - Post-check: audit_log has notification entry when alert triggered
  - Expected: 1 entry per alert event
```

```yaml
Task ID: T-046
Task Name: Audit Log
Owner: data/storage.py
SLA: < 100ms per entry (append)

WHAT:
  Record all significant events ke audit_log table (append-only).
  Setiap task start, complete, error wajib log.

WHEN:
  - Trigger: Event-driven (real-time, called by all other tasks)

WHO:
  - Responsible: Storage.audit()
  - Accountable: Data Acquisition Engine
  - Informed: All engines, User (via audit API)

HOW:
  1. Receive: (event_type, payload, actor, timestamp)
  2. INSERT INTO audit_log (id, event_type, payload_json, actor, created_at)
  3. Commit immediately (WAL mode)

WHERE:
  - Backend Python, localhost
  - I/O bound (disk write)

WHY:
  - Traceability: setiap event tercatat, dapat ditelusuri
  - Debugging: jika ada issue, audit log adalah sumber kebenaran
  - Compliance: audit trail untuk transparency

OUTPUT:
  - Primary: `audit_log` table (append-only, never delete/update)
  - Consumer: User (audit UI), Debugging, Monitoring

FAILURE HANDLING:
  - DB write fail: retry 3x, log to stderr, skip (non-critical but concerning)
  - DB full: alert SEV-0

IDEMPOTENCY:
  - Each entry has unique ID → safe to re-run
  - Append-only: never update or delete

VALIDATION:
  - Post-check: audit_log grows monotonically
  - Expected: 100+ entries per day (all task events)
```

### 4.7 Runbook: Frontend & User Interaction (T-050 to T-053)

```yaml
Task ID: T-050
Task Name: Dashboard Render
Owner: frontend/app/page.tsx
SLA: < 2 detik (page load)

WHAT:
  Render data inspection dashboard di browser user.

WHEN:
  - Trigger: On user visit (browser request)
  - Always available (24/7)

WHO:
  - Responsible: Next.js SSR / page.tsx
  - Accountable: Frontend
  - Informed: User

HOW:
  1. User navigates to /
  2. Next.js SSR: fetch data from API (safeApiFetch with X-API-Key)
  3. Render: data tables, charts, summary cards
  4. Client-side: interactive filters, ticker search

WHERE:
  - Frontend (browser), Next.js
  - Network bound (API calls to backend)

WHY:
  - User interface untuk melihat data dan analysis results
  - Tanpa UI, user tidak bisa interact dengan sistem

OUTPUT:
  - Primary: HTML page rendered in browser
  - Consumer: User

FAILURE HANDLING:
  - API timeout: show error message, retry button
  - API down: show "Backend unavailable" message

IDEMPOTENCY:
  - Read-only (no DB write) → inherently idempotent
  - Each page load is independent

VALIDATION:
  - Post-check: page loads with HTTP 200
  - Expected: < 2 second load time
```

```yaml
Task ID: T-051
Task Name: API Request Handling
Owner: api/app.py (FastAPI)
SLA: < 500ms per request (target), < 2s (max)

WHAT:
  Handle REST API request: authenticate (X-API-Key), process, return JSON response.

WHEN:
  - Trigger: On user action (frontend) or CLI request
  - Always available (24/7, while API server running)

WHO:
  - Responsible: FastAPI endpoint handler
  - Accountable: Frontend (API layer)
  - Consulted: All engines (via endpoint handlers)
  - Informed: Monitoring

HOW:
  1. Receive HTTP request
  2. Authenticate: check X-API-Key header
  3. Route to endpoint handler
  4. Process: call appropriate engine/method
  5. Return: JSON response
  6. Log: request method, path, status, duration

WHERE:
  - Backend Python, localhost:8000
  - CPU + I/O bound

WHY:
  - API adalah interface antara frontend dan backend
  - Tanpa API, frontend tidak bisa akses data

OUTPUT:
  - Primary: JSON response
  - Secondary: access log
  - Consumer: Frontend, CLI, User

FAILURE HANDLING:
  - Auth fail: 401 Unauthorized
  - Not found: 404
  - Server error: 500 + log traceback
  - Timeout: 504 Gateway Timeout

IDEMPOTENCY:
  - GET requests: inherently idempotent
  - POST requests: depends on endpoint (compute scores = idempotent via INSERT OR REPLACE)

VALIDATION:
  - Post-check: API responds with 200 for /api/health
  - Expected: < 500ms average response time
```

```yaml
Task ID: T-052
Task Name: WebSocket Stream
Owner: api/app.py (WebSocket)
SLA: < 100ms (message push)

WHAT:
  Real-time data push ke frontend via WebSocket connection.

WHEN:
  - Trigger: On client connect
  - Duration: While client connected (24/7)

WHO:
  - Responsible: FastAPI WebSocket handler
  - Accountable: Frontend (API layer)
  - Informed: Monitoring

HOW:
  1. Client connects to ws://localhost:8000/ws
  2. Server accepts connection
  3. Push events: engine status updates, health checks, trade notifications
  4. Client receives and updates UI in real-time

WHERE:
  - Backend Python, localhost:8000
  - Network bound (persistent connection)

WHY:
  - Real-time updates tanpa polling
  - User melihat engine status dan alerts instantly

OUTPUT:
  - Primary: WebSocket frames (JSON)
  - Consumer: Frontend (dashboard)

FAILURE HANDLING:
  - Connection drop: client auto-reconnect
  - Server restart: all clients reconnect

IDEMPOTENCY:
  - Each message is independent → safe to re-send

VALIDATION:
  - Post-check: WebSocket connection established
  - Expected: messages received within 100ms of event
```

```yaml
Task ID: T-053
Task Name: Pre-Market Scan
Owner: analysis/prediction_engine.py
SLA: < 5 menit (watchlist only)

WHAT:
  Quick prediction untuk tickers di watchlist (~20-50 tickers) sebelum market open.

WHEN:
  - Schedule: 08:30 WIB daily (pre-market)
  - Skip: IDX holidays, weekends

WHO:
  - Responsible: PredictionEngine.predict() for watchlist tickers
  - Accountable: AI Learning Layer
  - Consulted: Decision Engine, XAI
  - Informed: User (via alert), Monitoring

HOW:
  1. Load watchlist tickers from watchlist table
  2. For each ticker (~20-50):
     a. Run T-010 (technical), T-017 (pattern), T-020 (LSTM), T-022 (fusion)
     b. Generate prediction: direction, confidence, expected return
  3. Filter: confidence > 60, direction UP
  4. Alert user via Telegram: "Pre-market scan: 3 watchlist stocks with high confidence"
  5. Save: prediction_log table

WHERE:
  - Backend Python, localhost
  - GPU (cuda:1) for LSTM inference (small batch)

WHY:
  - User perlu tahu sinyal sebelum market open
  - Watchlist = saham yang user interested in
  - Pre-market scan → user bisa prepare orders

OUTPUT:
  - Primary: `prediction_log` table (watchlist predictions)
  - Secondary: Telegram alert
  - Consumer: User, Frontend

FAILURE HANDLING:
  - Watchlist empty: skip, log info
  - LSTM error: fallback to factor-only prediction

IDEMPOTENCY:
  - New predictions = new IDs → safe to re-run

VALIDATION:
  - Post-check: SELECT COUNT(*) FROM prediction_log WHERE prediction_date=today AND ticker IN (watchlist)
  - Expected: ~20-50 rows
```

### 4.8 Operations Activity Ownership Matrix

> **Sumber:** AWS Well-Architected Framework — Operations Activity Ownership Matrix
> Setiap task punya Owner, Responsibilities, Validation Method, dan Feedback Mechanism.

| Task ID | Task | Owner (Accountable) | Responsibilities | Validation Method | Feedback Mechanism |
|---------|------|---------------------|------------------|-------------------|-------------------|
| T-001 | EOD Data Fetch | Data Acquisition Engine | Fetch, normalize, validate, store OHLCV | SELECT COUNT(*) FROM ohlcv WHERE date=today | Daily quality report (T-009) |
| T-002 | Foreign Flow Scrape | Data Acquisition Engine | Scrape idx.co.id, normalize, store | SELECT COUNT(*) FROM foreign_flow WHERE date=today | Sentiment engine accuracy |
| T-003 | Broker Flow Scrape | Data Acquisition Engine | Scrape broker summary, normalize, store | SELECT COUNT(*) FROM broker_flow WHERE date=today | Sentiment engine accuracy |
| T-004 | Data Validation | Data Acquisition Engine | Validate completeness, plausibility, gap | AVG(quality_score) per day | Quality report → user dashboard |
| T-005 | Macro Data Fetch | Data Acquisition Engine | Fetch BI rate, inflasi, GDP, USD/IDR | COUNT(*) FROM macro_data WHERE date=this_week | Regime detection stability |
| T-006 | Global Market Fetch | Data Acquisition Engine | Fetch S&P500, VIX, oil, gold | COUNT(*) FROM ohlcv WHERE ticker=global | Global market analysis accuracy |
| T-007 | Corporate Actions | Data Acquisition Engine | Fetch splits, dividends, adjust prices | COUNT(*) FROM corporate_actions this week | Backtest accuracy with adjustments |
| T-008 | DB Backup | Data Acquisition Engine | Backup SQLite, sync Parquet, clean old | Backup file exists + integrity check | Recovery drill (quarterly) |
| T-009 | Quality Report | Data Acquisition Engine | Aggregate quality scores, expose API | audit_log entry exists | User feedback via dashboard |
| T-010 | Technical Analysis | Analysis Engine | Compute 20+ indicators, detect patterns | COUNT(*) FROM technical_indicators WHERE date=today | Decision engine accuracy |
| T-011 | Fundamental Analysis | Analysis Engine | Score ROE, P/E, P/B, DER, growth | COUNT(*) FROM scores WHERE engine=fundamental | Decision engine accuracy |
| T-012 | Macro Analysis | Analysis Engine | Score BI rate, inflasi, GDP | DISTINCT score FROM scores WHERE engine=macro | Regime detection accuracy |
| T-013 | Global Market Analysis | Analysis Engine | Score S&P500, VIX, oil, gold | DISTINCT score FROM scores WHERE engine=global | Decision engine accuracy |
| T-014 | Relationship Analysis | Analysis Engine | Correlation matrix, lead-lag | COUNT(*) FROM relationship_matrix WHERE date=today | Portfolio diversification quality |
| T-015 | Sentiment Analysis | Analysis Engine | NLP, foreign flow, broker, social, F&G | COUNT(*) FROM scores WHERE engine=sentiment | Prediction accuracy correlation |
| T-016 | Regime Detection | Analysis Engine | HMM regime detection | regime label exists in ai_weights | Weight optimization convergence |
| T-017 | Pattern Detection | Analysis Engine | Detect chart + candlestick patterns | COUNT(*) FROM pattern_analysis WHERE detected_date=today | Pattern reliability win-rate |
| T-018 | Factor Screening | Analysis Engine | Multi-factor composite ranking | API /api/screen returns non-empty | User adoption of screener |
| T-019 | Score Pipeline | Analysis Engine | Orchestrate T-010 to T-016 | COUNT(*) FROM scores WHERE date=today (all 6 engines) | Decision engine accuracy |
| T-020 | LSTM Prediction | AI Learning Layer | Per-ticker LSTM inference (GPU) | Count predictions in-memory | Prediction accuracy (T-023) |
| T-021 | Pattern Reliability | AI Learning Layer | Win-rate lookup per pattern per ticker | 100% coverage for detected patterns | Pattern Journal feedback |
| T-022 | Prediction Engine | AI Learning Layer | Fuse LSTM + pattern + factor + sentiment | COUNT(*) FROM prediction_log WHERE date=today | T-023 self-correction results |
| T-023 | Self-Correction | AI Learning Layer | Evaluate predictions, root cause, correct | COUNT(*) FROM error_analysis WHERE date=today | Prediction accuracy trend over time |
| T-024 | Weight Optimization | AI Learning Layer | Ridge regression per regime | Weights sum to 1.0 per regime | OOS R² trend |
| T-025 | LSTM Retrain | AI Learning Layer | Retrain 928 models (GPU, 4-8h) | COUNT(.pt files) = 928 | OOS R² per model |
| T-026 | Pattern Discovery | AI Learning Layer | K-means clustering, find new patterns | COUNT(*) FROM discovered_patterns | Pattern Journal validation |
| T-027 | Walk-Forward | AI Learning Layer | OOS validation, purged TSS | AVG(oos_r2) > 0 in model_registry | Model degradation alerts |
| T-030 | Decision Engine | Decision Engine | 6-factor weighted scoring → recommendation | COUNT(*) FROM scores WHERE engine=composite | User trade outcome feedback |
| T-031 | Risk Assessment | Risk Engine | VaR, position sizing, SL/TP | 100% BUY recs have VaR | Drawdown analysis feedback |
| T-032 | XAI Narrative | XAI Engine | Bahasa Indonesia narrative | API /api/explain returns 200+ chars | User comprehension feedback |
| T-033 | Portfolio Optimization | Portfolio Engine | HRP/Markowitz optimization | COUNT(*) FROM portfolio_candidates | Portfolio performance vs benchmark |
| T-034 | Rebalancing | Portfolio Engine | Check drift, suggest rebalance | Rebalance suggestions generated if drift > 5% | Portfolio drift over time |
| T-040 | Paper Trading | Execution Engine | Mock broker, track fills, PnL | COUNT(*) FROM paper_trades | Paper trade PnL vs real |
| T-041 | Auto Trading | **User** (Accountable) | Real orders via broker API | COUNT(*) FROM orders | User PnL feedback |
| T-042 | Position Monitor | Execution Engine | Check SL/TP, trailing stop | All positions have current price | SL/TP hit rate analysis |
| T-043 | Market Status | Data Acquisition Engine | Check IDX open/close, auto-reject | Correct status during market hours | Order rejection rate |
| T-044 | Health Monitor | Monitoring Engine | Health check all components | audit_log entries every 5 min | System uptime metrics |
| T-045 | Telegram | **User** (Accountable) | Send alerts via Telegram Bot | audit_log notification entries | User response time to alerts |
| T-046 | Audit Log | Data Acquisition Engine | Append-only event log | audit_log grows monotonically | Audit trail completeness |
| T-050 | Dashboard | Frontend | Render data inspection UI | HTTP 200, < 2s load | User session duration |
| T-051 | API Request | Frontend | Handle REST API request | < 500ms avg response | API error rate |
| T-052 | WebSocket | Frontend | Real-time data push | Messages received < 100ms | Client connection stability |
| T-053 | Pre-Market Scan | AI Learning Layer | Quick prediction for watchlist | COUNT(*) FROM prediction_log (watchlist) | User pre-market alert usefulness |

---

## 5. Aturan Operasional (Best Practices)

### 5.1 Aturan Runbook (dari AWS Well-Architected + SRE)

| Aturan | Deskripsi | Implementasi |
|--------|-----------|--------------|
| **Setiap task punya runbook** | Tidak ada task tanpa dokumentasi operasional | Task Operations Matrix (§2) + Runbook (§4) |
| **Runbook di version control** | Runbook disimpan di repo, bukan wiki terpisah | `pustaka/47-operational-contract-runbook.md` |
| **Runbook di-update setelah insiden** | Setiap failure → review runbook → update | Post-incident review wajib update runbook |
| **Runbook executable by anyone** | Engineer baru bisa ikuti runbook tanpa training | Imperative instructions, exact commands |
| **Expected outcome per step** | Setiap step punya expected output | "Expected: ~928 rows for today's date" |
| **Rollback procedure** | Setiap task punya cara undo | INSERT OR REPLACE → re-run with old data |
| **Escalation path** | Kapan escalate, ke siapa | §7 Failure Handling & Escalation |

### 5.2 Aturan Idempotency

Setiap task **wajib idempotent** — aman dijalankan ulang tanpa side effect:

| Pattern | Implementasi | Contoh |
|---------|--------------|--------|
| **INSERT OR REPLACE** | Upsert berdasarkan primary key | `save_ohlcv()` → same (ticker, date) → replace |
| **Unique ID per run** | Setiap run punya UUID, tidak overwrite run lain | `prediction_log.id = uuid4()` |
| **Status state machine** | Status hanya bergerak forward: PENDING → SUCCESS/FAIL | T-023 tidak re-evaluate sudah SUCCESS/FAIL |
| **Append-only audit** | Audit log tidak pernah dihapus/edit | `audit_log` table |
| **Checkpoint resume** | Jika crash mid-task, resume dari checkpoint | `pipeline_state` table: last_processed_ticker |

### 5.3 Aturan Retry & Backoff

| Skenario | Retry Strategy | Max Retry | Backoff |
|----------|---------------|-----------|---------|
| **Yahoo API timeout** | Exponential backoff | 3 | 1s, 2s, 4s |
| **IDX scraper blocked** | Linear backoff | 5 | 5s, 10s, 15s, 20s, 25s |
| **DB lock (SQLite WAL)** | Random jitter backoff | 3 | 0.1s, 0.3s, 0.5s |
| **CUDA OOM** | Reduce batch size + retry | 2 | Immediate (batch/2) |
| **Network timeout** | Exponential backoff | 3 | 2s, 4s, 8s |
| **Broker API reject** | No retry (log + alert) | 0 | — |

### 5.4 Aturan Dependency

| Aturan | Deskripsi |
|--------|-----------|
| **Explicit dependency** | Setiap task mendeklarasikan dependency di runbook |
| **Fail-fast** | Jika dependency gagal, task tidak jalan (skip + log) |
| **No circular dependency** | T-001 → T-019 → T-022 → T-033. Tidak boleh balik. |
| **Parallel if independent** | T-010 to T-016 bisa parallel (masing-masing engine independen) |
| **Sequential if dependent** | T-019 (pipeline) → T-022 (prediction) → T-033 (portfolio) |

### 5.5 Aturan SLA/SLO

| Task | SLA (max latency) | SLO (target) | Error Budget |
|------|-------------------|-------------|--------------|
| T-001 EOD Fetch | 60 detik | 45 detik | 15 detik |
| T-019 Score Pipeline | 5 menit | 3 menit | 2 menit |
| T-022 Prediction | 30 menit | 20 menit | 10 menit |
| T-023 Self-Correction | 5 menit | 3 menit | 2 menit |
| T-030 Decision | 30 detik | 15 detik | 15 detik |
| T-033 Portfolio | 2 menit | 1 menit | 1 menit |
| T-044 Health Monitor | 10 detik | 5 detik | 5 detik |
| API Response (any) | 2 detik | 500ms | 1.5 detik |

### 5.6 Aturan Observability

Setiap task wajib menghasilkan:

| Output | Format | Tujuan |
|--------|--------|--------|
| **Start log** | `[timestamp] T-001 START: EOD fetch for 928 tickers` | Audit trail |
| **Progress log** | `[timestamp] T-001 PROGRESS: 500/928 tickers fetched` | Monitoring |
| **Complete log** | `[timestamp] T-001 DONE: 925 success, 3 fail, 45s` | Audit + metrics |
| **Error log** | `[timestamp] T-001 ERROR: BBCA.JK timeout, retry 1/3` | Debugging |
| **Metric** | `task_duration_seconds{task="T-001"} 45.2` | Performance tracking |
| **Audit entry** | `audit_log` table: event_type, payload, actor, timestamp | Traceability |

---

## 6. Master Schedule (Unified)

### 6.1 Jadwal Lengkap (Semua Task, WIB)

```
00:00  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
      T-008 DB Backup (01:00)

05:00  ░░░░░░ US Close Check (05:00) ░░░░░░░░░░░░░░░░░░░░░░

06:00  T-006 Global Market Fetch (06:00) ░░░░░░░░░░░░░░░░░░░
      T-053 Gap Prediction (06:00)

08:00  T-005 Macro Data Fetch (08:00, weekly) ░░░░░░░░░░░░░

08:30  T-053 Pre-Market Scan (08:30) ░░░░░░░░░░░░░░░░░░░░░░

09:00  ▓▓▓▓▓ IDX MARKET OPEN ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
      T-040 Paper Trading (09:00-15:50)
      T-041 Auto Trading (09:00-15:50, if enabled)
      T-042 Position Monitor (every 60s)
      T-043 Market Status (every 5min)
      T-044 Health Monitor (every 5min, 24/7)

15:50  ▓▓▓▓▓ IDX MARKET CLOSE ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓

16:30  T-001 EOD Data Fetch (16:30) ░░░░░░░░░░░░░░░░░░░░░░
      T-023 Self-Correction Loop (16:30, parallel)
      T-034 Portfolio Rebalancing (16:30)

17:00  T-002 Foreign Flow Scrape (17:00) ░░░░░░░░░░░░░░░░░
      T-003 Broker Flow Scrape (17:00)

18:00  T-019 Score Pipeline (18:00) ░░░░░░░░░░░░░░░░░░░░░░
      T-010 to T-016 (sub-tasks of pipeline)
      T-017 Pattern Detection (18:15)
      T-020 LSTM Prediction (18:00, GPU cuda:1)
      T-021 Pattern Reliability (18:15)

18:20  T-022 Prediction Engine Fusion (18:20) ░░░░░░░░░░░░

18:25  T-030 Decision Engine (18:25) ░░░░░░░░░░░░░░░░░░░░░

18:30  T-031 Risk Assessment (18:30) ░░░░░░░░░░░░░░░░░░░░░
      T-032 XAI Narrative (18:30)
      T-033 Portfolio Pipeline (18:30)

20:00  T-024 AI Weight Opt (20:00, weekly Sabtu) ░░░░░░░░░░
      T-025 LSTM Retrain (20:00, weekly Sabtu, GPU 4-8 jam)
      T-026 Pattern Discovery (20:00, weekly Sabtu)
      T-027 Walk-Forward (20:00, weekly Sabtu)

22:30  US Market Monitor (22:30) ░░░░░░░░░░░░░░░░░░░░░░░░░

24:00  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

### 6.2 Dependency Graph

```
T-008 DB Backup (01:00) ─── independent
T-006 Global Fetch (06:00) ─── independent
T-005 Macro Fetch (08:00, weekly) ─── independent
T-053 Pre-Market Scan (08:30) ─── depends on: T-019 (yesterday's scores)

T-001 EOD Fetch (16:30) ─── independent (trigger: market close)
  ├── T-004 Validation (16:35) ─── depends on: T-001
  ├── T-023 Self-Correction (16:30) ─── depends on: T-001 (actual prices)
  ├── T-034 Rebalancing (16:30) ─── depends on: T-001 (current prices)
  │
  ├── T-002 Foreign Flow (17:00) ─── independent (IDX scraper)
  ├── T-003 Broker Flow (17:00) ─── independent (IDX scraper)
  │
  ├── T-019 Score Pipeline (18:00) ─── depends on: T-001, T-002
  │   ├── T-010 Technical (18:00)
  │   ├── T-011 Fundamental (18:00)
  │   ├── T-012 Macro (18:05)
  │   ├── T-013 Global (18:05)
  │   ├── T-014 Relationship (18:10)
  │   ├── T-015 Sentiment (18:10, GPU for NLP)
  │   ├── T-016 Regime (18:15)
  │   ├── T-017 Pattern Detection (18:15)
  │   └── T-021 Pattern Reliability (18:15)
  │
  ├── T-020 LSTM Prediction (18:00, GPU) ─── depends on: T-001
  │
  ├── T-022 Prediction Fusion (18:20) ─── depends on: T-019, T-020, T-017, T-021
  │
  ├── T-030 Decision (18:25) ─── depends on: T-019, T-022
  │   ├── T-031 Risk (18:30) ─── depends on: T-030
  │   ├── T-032 XAI (18:30) ─── depends on: T-030
  │   └── T-033 Portfolio (18:30) ─── depends on: T-022, T-031
  │
  └── T-009 Quality Report (18:00) ─── depends on: T-004

T-024 Weight Opt (20:00, Sat) ─── depends on: T-023 (corrections)
T-025 LSTM Retrain (20:00, Sat, GPU) ─── depends on: T-001 (latest data)
T-026 Pattern Discovery (20:00, Sat) ─── depends on: T-001
T-027 Walk-Forward (20:00, Sat) ─── depends on: T-025

T-044 Health Monitor (24/7, every 5min) ─── independent
T-042 Position Monitor (market hours, 60s) ─── depends on: price feed
T-043 Market Status (market hours, 5min) ─── independent
```

---

## 7. Failure Handling & Escalation

### 7.1 Escalation Matrix

| Severity | Skenario | Action | Escalate To |
|----------|----------|--------|-------------|
| **SEV-0 (Critical)** | DB corruption, complete pipeline failure | Halt all tasks, alert immediately | User (Telegram) |
| **SEV-1 (High)** | > 10% tickers fail fetch, LSTM model missing | Skip affected task, alert | User (Telegram) + audit log |
| **SEV-2 (Medium)** | Single ticker error, pattern detection fail | Skip ticker, log warning, continue | Audit log only |
| **SEV-3 (Low)** | Minor data quality flag, slow response | Log, continue, no alert | Audit log only |

### 7.2 Failure Recovery Procedures

```yaml
SEV-0: DB Corruption
  SYMPTOM: SQLite error, data inconsistency, corrupt WAL file
  IMMEDIATE:
    1. Stop all pipeline tasks
    2. Alert user via Telegram: "CRITICAL: DB corruption detected"
    3. Do NOT attempt write operations
  RECOVERY:
    1. Restore from latest backup (T-008, 01:00 WIB)
    2. Re-run T-001 to T-019 for today
    3. Verify data integrity: SELECT COUNT(*) per table
  POST-INCIDENT:
    1. Update runbook with root cause
    2. Add prevention check to T-004

SEV-1: Yahoo API Down
  SYMPTOM: > 10% tickers fail fetch in T-001
  IMMEDIATE:
    1. Retry with exponential backoff (3x)
    2. Fallback to Google Finance scraper
    3. If still failing: skip T-010 to T-019
    4. Alert user: "Yahoo API down, pipeline skipped today"
  RECOVERY:
    1. Wait for Yahoo API recovery (check every 30 min)
    2. Re-run T-001 when API available
    3. Continue pipeline normally

SEV-1: CUDA Error
  SYMPTOM: torch.cuda error, OOM, device not found
  IMMEDIATE:
    1. Fallback to CPU for LSTM inference
    2. Log warning: "CUDA unavailable, using CPU (slow)"
    3. Continue pipeline (slower but functional)
  RECOVERY:
    1. Check nvidia-smi
    2. If OOM: reduce batch_size, retry
    3. If device not found: check driver, reboot if needed

SEV-2: Single Ticker Error
  SYMPTOM: Exception for one ticker in any engine
  IMMEDIATE:
    1. Catch exception, log error with ticker + traceback
    2. Skip ticker, continue to next
    3. Record in audit log
  RECOVERY:
    1. Review error in next cycle
    2. If persistent: investigate data quality for that ticker
```

---

## 8. Idempotency & Retry Rules

### 8.1 Idempotency Checklist per Task

| Task | Idempotent? | Mechanism |
|------|-------------|-----------|
| T-001 EOD Fetch | ✅ | INSERT OR REPLACE on (ticker, date) |
| T-002 Foreign Flow | ✅ | INSERT OR REPLACE on (ticker, date) |
| T-004 Validation | ✅ | Recompute score, replace |
| T-010 Technical | ✅ | INSERT OR REPLACE on (ticker, date, engine) |
| T-019 Pipeline | ✅ | INSERT OR REPLACE scores |
| T-020 LSTM | ✅ | New prediction = new ID, old remains |
| T-022 Prediction | ✅ | New prediction = new ID |
| T-023 Self-Correction | ✅ | Status state machine: PENDING → SUCCESS/FAIL (one-way) |
| T-024 Weight Opt | ✅ | INSERT OR REPLACE on (regime, factor) |
| T-025 LSTM Retrain | ✅ | Overwrite model file |
| T-033 Portfolio | ✅ | New allocation = new ID per date |

### 8.2 Retry Rules

```python
# utils/retry.py — shared retry decorator

import time
from functools import wraps

def retry(max_attempts=3, backoff="exponential", base_delay=1.0):
    """
    Retry decorator with configurable backoff.
    
    Args:
        max_attempts: Max retry attempts (default 3)
        backoff: "exponential" or "linear" or "jitter"
        base_delay: Base delay in seconds (default 1.0)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    if backoff == "exponential":
                        delay = base_delay * (2 ** (attempt - 1))
                    elif backoff == "linear":
                        delay = base_delay * attempt
                    elif backoff == "jitter":
                        delay = base_delay * (0.5 + random.random())
                    time.sleep(delay)
        return wrapper
    return decorator

# Usage:
@retry(max_attempts=3, backoff="exponential", base_delay=1.0)
def fetch_yahoo(ticker):
    return yfinance.download(ticker)
```

---

## 9. Observability & Audit Trail

### 9.1 Audit Log Format

Setiap task wajib menulis ke `audit_log`:

```python
# Every task must log:
storage.audit(
    event_type="task_start",
    payload={"task_id": "T-001", "tickers": 928, "started_at": now},
    actor="system/scheduler",
)

storage.audit(
    event_type="task_complete",
    payload={"task_id": "T-001", "success": 925, "fail": 3, "duration_s": 45.2},
    actor="data/acquisition.py",
)

# On failure:
storage.audit(
    event_type="task_error",
    payload={"task_id": "T-001", "error": "Yahoo API timeout", "ticker": "BBCA.JK"},
    actor="data/acquisition.py",
)
```

### 9.2 Monitoring Dashboard

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Task duration | `audit_log` (task_complete) | > SLA (see §5.5) |
| Task success rate | `audit_log` (task_complete vs task_error) | < 95% |
| Pipeline completion | `audit_log` (all tasks for today) | < 100% by 19:00 WIB |
| DB size | `sqlite3 PRAGMA page_count` | > 500 MB |
| GPU utilization | `nvidia-smi` | > 95% for > 1 hour |
| API latency | FastAPI middleware | > 2 seconds |
| Prediction accuracy | `prediction_log` (SUCCESS vs FAIL) | < 60% win-rate |

### 9.3 Health Check Endpoint

```python
@app.get("/api/health/operational")
async def operational_health():
    """Operational health: all tasks status."""
    return {
        "last_pipeline_run": get_last_audit("task_complete", "T-019"),
        "predictions_today": count_predictions_today(),
        "pending_evaluations": count_pending_predictions(),
        "failed_tasks_today": count_audit("task_error", today),
        "gpu_status": check_gpu_health(),
        "db_size_mb": get_db_size(),
        "last_backup": get_last_audit("task_complete", "T-008"),
    }
```

---

## 10. Checklist Implementasi

### Task Operations Matrix
- [ ] Setiap task (T-001 to T-053) punya 7 dimensi terdefinisi (What/When/Who/How/Where/Why/Output)
- [ ] Setiap task punya SLA dan SLO
- [ ] Setiap task punya consumer yang jelas
- [ ] Setiap task punya dependency yang explicit

### RACI
- [ ] Setiap task punya tepat 1 Accountable
- [ ] User adalah Informed untuk operational tasks, Accountable untuk trading decisions
- [ ] Monitoring adalah Informed untuk semua tasks

### Runbook
- [ ] Runbook untuk Data Layer (T-001 to T-009)
- [ ] Runbook untuk Analysis Layer (T-010 to T-019)
- [ ] Runbook untuk Prediction & AI Layer (T-020 to T-027)
- [ ] Runbook untuk Decision & Risk Layer (T-030 to T-034)
- [ ] Runbook untuk Execution & Monitoring (T-040 to T-046)
- [ ] Setiap runbook punya: steps, expected outcome, failure handling, rollback

### Aturan Operasional
- [ ] Semua task idempotent
- [ ] Retry decorator implemented di semua I/O tasks
- [ ] Checkpoint/resume mechanism untuk long-running tasks
- [ ] Audit log untuk setiap task (start, progress, complete, error)
- [ ] Monitoring dashboard menampilkan task status real-time

### Schedule
- [ ] `scripts/daily_pipeline_runner.py` mengimplementasikan master schedule (§6)
- [ ] Cron/systemd timer untuk setiap schedule entry
- [ ] IDX holiday check (skip pipeline)
- [ ] Weekend handling (Sabtu: retrain only, Minggu: rest)

### Failure Handling
- [ ] SEV-0: DB corruption recovery procedure tested
- [ ] SEV-1: Yahoo API down fallback tested
- [ ] SEV-1: CUDA error fallback to CPU tested
- [ ] SEV-2: Single ticker error handling tested
- [ ] Telegram alert untuk SEV-0 dan SEV-1

---

## Referensi

1. AWS Well-Architected Framework — Operational Excellence Pillar — Runbook best practices
2. SRE Runbook Framework — Imperative instructions, expected outcomes, escalation
3. Operations Activity Ownership Matrix — Owner, responsibilities, validation, feedback
4. `pustaka/18-modul-engine-data-wajib.md` — Modul spesifikasi (tujuan, input, output, file)
5. `pustaka/19-flow-logic-testing-kpi.md` — Data flow, process flow, business logic, KPI, SLA
6. `pustaka/36-gap-data-timezone-global-idx.md` §9 — Schedule WIB, timezone awareness
7. `pustaka/46-prediksi-pola-portfolio-pipeline.md` §11 — Pipeline operational schedule
8. `pustaka/34-performance-engineering-optimization.md` §13 — GPU/CUDA acceleration
9. `src/trading_system/data/storage.py` — Audit logging, data storage
10. `src/trading_system/monitoring/engine.py` — System health monitor
11. `scripts/daily_runner.py` — Existing daily pipeline runner

---

> **Catatan:** Dokumen ini adalah **operational contract** untuk setiap task di aplikasi. Setiap task harus punya jawaban untuk 7 pertanyaan: What, When, Who, How, Where, Why, Output. Tanpa kontrak yang lengkap, task tidak boleh diimplementasikan. Kontrak ini bersifat living document — di-update setiap kali ada task baru, insiden, atau perubahan arsitektur. Sumber aturan: AWS Well-Architected (Operational Excellence), SRE Runbook Framework, Operations Activity Ownership Matrix, RACI, idempotency principle, SLA/SLO/SLI.
