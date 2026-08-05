# Gap Analysis: Teori vs Praktek

> **Dokumen 88** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Tujuan:** Dokumen ini adalah audit komparatif antara apa yang **dijelaskan di pustaka** (teori/desain) vs apa yang **benar-benar diimplementasikan** di `trading-system` v0.1.11 (praktek/kode). Setiap gap dianalisis: apa yang ada di teori, apa yang ada di kode, penyebab gap, dan rencana penutupan.
>
> **Konteks:** Pustaka berisi 89 dokumen (~68K baris) pengetahuan pasar modal. Trading-system v0.1.11 adalah implementasi nyata dengan 27 modul analysis, 95 API endpoints, 51 test files, 928 equity tickers, ~2.9M OHLCV rows. Namun tidak semua teori di pustaka terimplementasi penuh — dokumen ini memetakan gap secara jujur dan objektif.
>
> **Scope:** Proyek ini adalah **sistem personal untuk pemiliknya sendiri** — tidak untuk didistribusikan. Prioritas gap disesuaikan: fitur multi-user, compliance distribusi, app store deployment, dan enterprise security adalah **tidak relevan**. Fokus pada decision support yang akurat dan usable untuk satu orang.

---

## Daftar Isi

1. [Metodologi Audit](#1-metodologi-audit)
2. [Gap Summary Matrix](#2-gap-summary-matrix)
3. [Gap Detail: Frontend](#3-gap-detail-frontend)
4. [Gap Detail: Execution & OMS](#4-gap-detail-execution--oms)
5. [Gap Detail: Market Data & Real-Time](#5-gap-detail-market-data--real-time)
6. [Gap Detail: Infrastructure & DevOps](#6-gap-detail-infrastructure--devops)
7. [Gap Detail: Security & Compliance](#7-gap-detail-security--compliance)
8. [Gap Detail: AI/ML & Backtesting](#8-gap-detail-aiml--backtesting)
9. [Gap Detail: Portfolio & User Features](#9-gap-detail-portfolio--user-features)
10. [Gap Detail: Testing & Quality](#10-gap-detail-testing--quality)
11. [Rencana Penutupan Gap](#11-rencana-penutupan-gap)
12. [Prioritas dan Timeline](#12-prioritas-dan-timeline)

---

## 1. Metodologi Audit

### 1.1 Sumber Teori
- 88 dokumen pustaka (00-87), ~67K baris
- Dokumen kunci: 12 (panduan membangun), 17 (aplikasi retail), 32 (UI/UX), 40 (OMS/EMS), 28 (API design), 33 (cybersecurity), 34 (performance), 48 (DR/BC), 55 (capacity), 20 (robot trading), 19 (flow/KPI)

### 1.2 Sumber Praktek
- `src/trading_system/` — 27 modul analysis, 6 sentiment, 7 execution, 6 portfolio, 5 XAI, 2 testing, 2 corporate, 1 monitoring, 1 decision, 1 risk
- `frontend/app/` — 1 page (Data Inspection Dashboard), 3 components
- `tests/unit/` — 51 test files, 700+ tests
- `scripts/bench/` — 4 benchmark scripts

### 1.3 Klasifikasi Gap

| Status | Simbol | Arti |
|--------|--------|------|
| **Tercapai** | ✅ | Teori terimplementasi penuh di kode |
| **Sebagian** | ⚠️ | Teori terimplementasi sebagian, ada stub/placeholder |
| **Gap** | ❌ | Teori ada, implementasi tidak ada |
| **Teori saja** | 📖 | Teori ada, implementasi belum dimulai |
| **Praktek saja** | 🔧 | Implementasi ada, teori belum didokumentasikan |

---

## 2. Gap Summary Matrix

| Area | Teori (Pustaka) | Praktek (Kode) | Status | Gap Severity |
|------|-----------------|----------------|--------|-------------|
| **Frontend — Dashboard** | 7 halaman (Dashboard, Stock Detail, Portfolio, Orders, Backtest, Analysis, Settings) | 1 halaman (Data Inspection only) | ❌ | **Critical** |
| **Frontend — Mobile** | React Native/Flutter, offline, biometric, push notif | Tidak ada | 📖 | N/A (personal) |
| **OMS/EMS** | Order state machine, event sourcing, SOR, fill processor, kill switch, reconciliation, saga, concurrency | Automated executor + paper execution + broker adapter (mock only) | ⚠️ | **Critical** |
| **Broker Integration** | Mock + Sinarmas + BNI Sekuritas | Mock only; Sinarmas & BNI = `NotImplementedError` | ⚠️ | **Critical** |
| **FIX Protocol** | FIX 4.4 spec, session management, message types | Tidak ada implementasi FIX | 📖 | Medium |
| **Market Data Real-Time** | Ticker plant, WebSocket gateway, tick coalescer, delta encoder, stale data 7-state | WebSocket `/ws/live` (engine status only, bukan price feed) | ⚠️ | High |
| **Redis/Caching** | Multi-tier cache (local → Redis → CDN) | Tidak ada Redis; SQLite only | 📖 | Medium |
| **Disaster Recovery** | RTO/RPO, failover, backup strategy, DR drill | Tidak ada DR automation; manual backup only | 📖 | Low (personal) |
| **Load/Stress Testing** | Concurrent API test, pipeline capacity, stress multi-failure | 4 benchmark scripts (rate limit, speed test) | ⚠️ | Medium |
| **Cybersecurity — MFA** | MFA mandatory, TOTP, biometric | API key only (single-user) | ⚠️ | N/A (personal) |
| **Cybersecurity — Encryption** | Encrypt at rest, Fernet, TLS | API key auth; no field-level encryption | ⚠️ | Low (personal) |
| **Deflated Sharpe Ratio** | DSR formula, effective trials, checklist | Tidak ada di `backtest/metrics.py` | ❌ | High |
| **Concurrency Patterns** | TOCTOU, saga, materialized view, claim-before-dispatch | Tidak ada (single-user, async) | 📖 | N/A (personal) |
| **Social Media Sentiment** | Reddit + X/Twitter scraping | Class exists, lexicon-based, no API integration | ⚠️ | Low (personal) |
| **Google Trends Sentiment** | pytrends API integration | Class exists, hardcoded keywords, no API call | ⚠️ | Low (personal) |
| **Portfolio Rebalancer** | Target weights, drift detection, auto-rebalance | Class exists, functional, but not integrated with execution | ⚠️ | Low (personal) |
| **Strategy Selector** | Investor profile → strategy matching | Class exists, dataclass-based, not integrated with UI | ⚠️ | Low (personal) |
| **KPI Tracking** | 30+ KPI targets across infrastructure, performance, data, engine, business | KPI targets defined in doc, no automated measurement | ❌ | High |
| **Telegram Notifier** | Notification via Telegram | `utils/` module exists | ✅ | — |
| **Corporate Actions** | Splits, dividends, suspension, delisting | `corporate/actions.py` functional | ✅ | — |
| **XAI** | Narrative + top factors + context providers | 5 XAI modules, fully functional | ✅ | — |
| **Backtest Engine** | Next-bar execution, survivorship-free, Monte Carlo, walk-forward | Fully implemented | ✅ | — |
| **Decision Engine** | Multi-factor weighted scoring with regime filter | Fully implemented | ✅ | — |
| **Risk Engine** | VaR, CVaR, Kelly, position sizing, circuit breaker | Fully implemented | ✅ | — |
| **Data Acquisition** | Yahoo Finance + IDX scraping + foreign/broker flow | Fully implemented | ✅ | — |

---

## 3. Gap Detail: Frontend

### 3.1 Teori (Pustaka Doc 32, 17, 43)

Pustaka mendesain 7 halaman frontend:
| Halaman | Konten |
|---------|--------|
| **Dashboard** | Portfolio summary, watchlist, market status, top movers |
| **Stock Detail** | Chart, indicators, scores, recommendation, fundamental |
| **Portfolio** | Open positions, PnL, allocation, history |
| **Orders** | Active orders, order history, trade log |
| **Backtest** | Strategy testing, configuration, equity curve |
| **Analysis** | Screeners, factor analysis, heatmap |
| **Settings** | Risk params, API key, notifications |

Plus: mobile app (React Native/Flutter), offline support, biometric auth, push notification.

### 3.2 Praktek (Kode Aktual)

- **1 halaman saja:** `frontend/app/page.tsx` (854 baris) — Data Inspection Dashboard
- **Sidebar:** Hanya link "Data Inspection" (`TerminalLayout.tsx`)
- **Tidak ada:** Dashboard, Stock Detail, Portfolio, Orders, Backtest, Analysis, Settings
- **Tidak ada:** Mobile app, offline support, biometric, push notification
- **API layer:** `frontend/app/lib/api.ts` (72 baris) — `safeApiFetch()` dengan `X-API-Key`

### 3.3 Analisis Gap

**Penyebab:** Frontend di-strip ke Data Inspection only karena fokus pengembangan ke backend/data. Semua halaman lain (dashboard, backtest, engines, portfolio, simulation, audit, replay) pernah ada tapi dihapus.

**Dampak:** Aplikasi tidak usable untuk end-user. Backend punya 95 API endpoints tapi frontend hanya konsumsi ~10 endpoint. Fitur unggulan (XAI, backtest, recommendation, screener) tidak accessible via UI.

**Rencana:** Lihat §11.1 — Roadmap Frontend Recovery

---

## 4. Gap Detail: Execution & OMS

### 4.1 Teori (Pustaka Doc 40, 20, 28)

Pustaka mendesain OMS lengkap:
- Order state machine (new → pending → partial fill → filled / cancelled / rejected)
- Event sourcing (append-only event log)
- Smart Order Routing (multi-broker)
- Fill processor (partial fill handling, idempotency)
- Kill switch & emergency controls
- Reconciliation engine
- Saga pattern dengan compensation
- Concurrency patterns (TOCTOU, claim-before-dispatch, materialized view)
- FIX 4.4 protocol support
- Broker adapter untuk Sinarmas + BNI Sekuritas

### 4.2 Praktek (Kode Aktual)

| Komponen | Status Kode | Detail |
|----------|-------------|--------|
| `execution/automated.py` | ✅ Fungsional | Auto trading engine, 471 baris, circuit breaker, daily loss limit |
| `execution/paper_execution.py` | ✅ Fungsional | Paper trading simulator, 253 baris |
| `execution/real_execution.py` | ✅ Fungsional | Real execution wrapper, 335 baris, fallback ke paper |
| `execution/broker_adapter.py` | ⚠️ Stub | Mock adapter fungsional; Sinarmas = `NotImplementedError` (8 method); BNI = `NotImplementedError` (8 method) |
| `execution/interface.py` | ✅ Fungsional | Abstract base class, 87 baris |
| `execution/tax.py` | ✅ Fungsional | Tax calculator, 199 baris |
| OMS (OrderStateMachine) | ❌ Tidak ada | Tidak ada class OMS |
| Event sourcing | ❌ Tidak ada | Tidak ada order_events table |
| Smart Order Router | ❌ Tidak ada | Tidak ada SOR class |
| Kill switch | ❌ Tidak ada | Circuit breaker ada, tapi bukan OMS kill switch |
| Reconciliation | ❌ Tidak ada | Tidak ada reconciliation engine |
| FIX protocol | ❌ Tidak ada | Tidak ada FIX implementation |
| Saga pattern | ❌ Tidak ada | Tidak ada saga orchestrator |
| Concurrency patterns | ❌ Tidak ada | Single-user, tidak butuh concurrent order |

### 4.3 Analisis Gap

**Penyebab:** Aplikasi adalah **decision support system**, bukan full trading platform. Eksekusi nyata butuh broker API access yang tidak tersedia (Sinarmas/BNI belum buka API publik). OMS kompleks tidak prioritas untuk single-user decision support.

**Dampak:** Aplikasi tidak bisa mengeksekusi order nyata. User dapat rekomendasi tapi harus eksekusi manual di broker. Paper trading berfungsi untuk simulasi.

**Rencana:** Lihat §11.2 — Roadmap OMS/Execution

---

## 5. Gap Detail: Market Data & Real-Time

### 5.1 Teori (Pustaka Doc 66, 22, 28)

Pustaka mendesain:
- Ticker plant (ingest, validate, cache)
- WebSocket gateway (pub/sub, subscribe/unsubscribe)
- Tick coalescer (batch updates)
- Delta encoder (reduce bandwidth 67%)
- Multi-tier cache (local → Redis → CDN)
- Stale data detection (7-state model)
- Sequence number monitoring
- Heartbeat detection per symbol

### 5.2 Praktek (Kode Aktual)

| Komponen | Status | Detail |
|----------|--------|--------|
| Data acquisition | ✅ | Yahoo Finance + IDX scraping, batch scraper |
| WebSocket `/ws/live` | ⚠️ | Engine status only, bukan real-time price feed |
| Tick validation | ✅ | Plausibility check di data acquisition |
| Ticker plant | ❌ | Tidak ada real-time ticker plant |
| Tick coalescer | ❌ | Tidak ada |
| Delta encoder | ❌ | Tidak ada |
| Redis cache | ❌ | Tidak ada Redis |
| Stale data detection | ❌ | Tidak ada 7-state model |
| Sequence number monitoring | ❌ | Tidak ada |
| Heartbeat detection | ❌ | Tidak ada |

### 5.3 Analisis Gap

**Penyebab:** Data saat ini end-of-day (EOD) dari Yahoo Finance, bukan real-time tick feed. IDX tidak menyediakan real-time data feed gratis. Untuk decision support EOD, real-time pipeline tidak diperlukan.

**Dampak:** Aplikasi tidak bisa menampilkan real-time price movement. Decision engine beroperasi pada data harian, bukan intraday.

**Rencana:** Lihat §11.3 — Roadmap Market Data

---

## 6. Gap Detail: Infrastructure & DevOps

### 6.1 Teori (Pustaka Doc 27, 34, 48, 55)

| Topik | Teori |
|-------|-------|
| **Deployment (Doc 27)** | Docker, CI/CD, blue-green deploy, health check |
| **Performance (Doc 34)** | Redis cache, async I/O, query optimization, CDN |
| **Disaster Recovery (Doc 48)** | RTO 4h, RPO 1h, failover, backup strategy, DR drill |
| **Capacity (Doc 55)** | Load test, stress test, scale 928 → 2000 tickers |

### 6.2 Praktek (Kode Aktual)

| Komponen | Status | Detail |
|----------|--------|--------|
| Docker | ✅ | `Dockerfile` + `docker-compose.yml` |
| CI/CD | ✅ | `.github/workflows/ci.yml` |
| API server | ✅ | Uvicorn/FastAPI, port 8000 |
| Frontend server | ✅ | Next.js dev, port 3000 |
| Redis | ❌ | Tidak ada |
| CDN | ❌ | Tidak ada |
| Async I/O | ⚠️ | FastAPI async, tapi sebagian besar engine synchronous |
| DR automation | ❌ | Tidak ada; manual backup saja |
| Failover | ❌ | Single instance, no HA |
| Load test | ⚠️ | 4 benchmark scripts (rate limit, speed test), bukan comprehensive load test |
| Stress test | ❌ | Tidak ada multi-failure stress test |
| Monitoring | ⚠️ | `monitoring/engine.py` — health check sederhana, bukan comprehensive observability |

### 6.3 Analisis Gap

**Penyebab:** Single-user, single-instance, EOD system. Redis/CDN/HA tidak diperlukan untuk 1 user. DR manual acceptable untuk personal system.

**Dampak:** Sistem tidak scale untuk multi-user. Tidak ada automated recovery. Performance bottleneck saat compute-scores untuk 928 tickers.

**Rencana:** Lihat §11.4 — Roadmap Infrastructure

---

## 7. Gap Detail: Security & Compliance

### 7.1 Teori (Pustaka Doc 33, 10)

| Topik | Teori |
|-------|-------|
| **Auth** | MFA mandatory (TOTP/biometric), OAuth, session management |
| **Encryption** | TLS in transit, Fernet at rest, field-level encryption untuk credentials |
| **Audit trail** | Immutable audit log, every state change logged |
| **OWASP** | A02 (crypto failures), A03 (injection), A07 (auth failures) |
| **Regulasi 2026** | UU P2SK, POJK 3/5, free float 15%, demutualisasi, JATS MME |

### 7.2 Praktek (Kode Aktual)

| Komponen | Status | Detail |
|----------|--------|--------|
| API key auth | ✅ | `X-API-Key` header, `secrets.compare_digest` |
| CORS | ✅ | Configurable origins |
| Rate limiting | ✅ | Middleware-level |
| Audit log | ✅ | `audit_log` table, 3,125 entries |
| MFA | ❌ | Tidak ada (single-user, API key only) |
| TLS | ⚠️ | Dev mode HTTP; production perlu HTTPS reverse proxy |
| Field-level encryption | ❌ | Tidak ada Fernet encryption untuk credentials |
| Penetration test | ❌ | Tidak ada |
| Compliance 2026 | ❌ | Belum ada update untuk UU P2SK, POJK 3/5, JATS MME |

### 7.3 Analisis Gap

**Penyebab:** Single-user personal system. MFA/TLS/pen-test adalah enterprise requirements. API key auth cukup untuk akses lokal.

**Dampak:** Sistem tidak production-ready untuk multi-user atau internet-facing deployment.

**Rencana:** Lihat §11.5 — Roadmap Security

---

## 8. Gap Detail: AI/ML & Backtesting

### 8.1 Teori (Pustaka Doc 29, 39, 85, 86, 51)

| Topik | Teori |
|-------|-------|
| **Backtest** | Next-bar execution, survivorship-free, Monte Carlo, walk-forward |
| **DSR** | Deflated Sharpe Ratio, effective trials, multiple testing bias |
| **AI Learning** | LR weight optimization, LSTM deep learning, ensemble, purged TSS |
| **Walk-forward** | Rolling window, purge gap, parameter stability |
| **Alpha research** | Alpha composer, validation lab, factor engine |
| **MLOps** | Model degradation, drift detection, model registry |

### 8.2 Praktek (Kode Aktual)

| Komponen | Status | Detail |
|----------|--------|--------|
| Backtest engine | ✅ | Next-bar-open, survivorship-free |
| Monte Carlo | ✅ | GPU-accelerated, block bootstrap |
| Walk-forward | ✅ | `ai_learning/walk_forward.py` |
| AI Learning (LR) | ✅ | `ai_learning/engine.py` — linear regression weight optimization |
| Deep Learning (LSTM) | ✅ | `ai_learning/deep_learning.py` — PyTorch, GPU cuda:1 |
| Ensemble | ✅ | `ai_learning/ensemble.py` |
| Purged TSS | ✅ | `ai_learning/purged_tss.py` |
| Model registry | ✅ | `ai_learning/model_registry.py` |
| Prediction test | ✅ | `testing/prediction_test.py` |
| Alpha composer | ✅ | `analysis/alpha_composer.py` |
| Alpha validation | ✅ | `analysis/alpha_validation.py` |
| Factor engine | ✅ | `analysis/factor_engine.py` |
| **Deflated Sharpe Ratio** | ❌ | Tidak ada di `backtest/metrics.py` |
| **Model drift detection** | ⚠️ | Model registry ada, tapi automated drift alert belum |
| **Live degradation alert** | ❌ | Tidak ada (doc 85 gap #5) |

### 8.3 Analisis Gap

**Penyebab:** DSR adalah konsep advanced yang baru ditambahkan ke pustaka (doc 29 §16). Model drift dan live degradation alert adalah fitur monitoring yang belum prioritas.

**Dampak:** Backtest results mungkin misleading jika banyak konfigurasi diuji tanpa DSR correction. Tidak ada alert otomatis saat model performance degradasi di live.

**Rencana:** Lihat §11.6 — Roadmap AI/ML

---

## 9. Gap Detail: Portfolio & User Features

### 9.1 Teori (Pustaka Doc 17, 74, 18)

| Topik | Teori |
|-------|-------|
| **Onboarding** | Profil risiko, kuesioner, strategi selection |
| **Portfolio** | Open positions, PnL, allocation, rebalancing, profit tracker |
| **Screener** | Multi-factor screen, gorengan filter, liquidity filter |
| **Notification** | Telegram, push notification, email alert |
| **Tax calculator** | PPh22, PPh23, fee calculation, annual tax report |
| **Education** | Inline glossary, contextual tips, behavioral warning |

### 9.2 Praktek (Kode Aktual)

| Komponen | Status | Detail |
|----------|--------|--------|
| Portfolio engine | ✅ | `portfolio/engine.py` |
| Portfolio performance | ✅ | `portfolio/performance.py` |
| Portfolio rebalancer | ⚠️ | `portfolio/rebalancer.py` — fungsional tapi tidak terhubung ke execution |
| Profit tracker | ✅ | `portfolio/profit_tracker.py` |
| Strategy selector | ⚠️ | `portfolio/strategy_selector.py` — dataclass, tidak terhubung ke UI |
| Screener | ✅ | `analysis/screener.py` + `analysis/factor_screener.py` |
| Gorengan detector | ✅ | `analysis/gorengan_detector.py` |
| Liquidity filter | ✅ | `analysis/liquidity_filter.py` |
| Telegram notifier | ✅ | `utils/` module |
| Tax calculator | ✅ | `execution/tax.py` |
| Onboarding | ❌ | Tidak ada profil risiko kuesioner |
| Education/inline tips | ❌ | Tidak ada di frontend |
| Behavioral warning UI | ❌ | Tidak ada di frontend |
| Push notification | ❌ | Tidak ada |
| Email alert | ❌ | Tidak ada |

### 9.3 Analisis Gap

**Penyebab:** Backend portfolio/screener/tax berfungsi, tapi frontend tidak ada. Fitur user-facing (onboarding, education, behavioral warning) tidak diimplementasi.

**Dampak:** Backend punya kemampuan tapi user tidak bisa akses. Rebalancer dan strategy selector tidak terintegrasi dengan execution path.

**Rencana:** Lihat §11.7 — Roadmap Portfolio & User Features

---

## 10. Gap Detail: Testing & Quality

### 10.1 Teori (Pustaka Doc 19)

| Topik | Teori |
|-------|-------|
| **Unit tests** | ≥ 500 tests, ≥ 50% coverage |
| **E2E tests** | Playwright, comprehensive flow test |
| **KPI tracking** | 30+ KPI dengan target dan measurement |
| **CI/CD** | Automated test, lint, type check |
| **Test determinism** | Fixture autouse, tidak terpengaruh env |

### 10.2 Praktek (Kode Aktual)

| Komponen | Status | Detail |
|----------|--------|--------|
| Unit tests | ✅ | 51 files, 700+ tests, 50% coverage minimum |
| ruff linter | ✅ | `pyproject.toml` configured |
| mypy type check | ✅ | `pyproject.toml` configured |
| CI/CD | ✅ | GitHub Actions |
| Playwright E2E | ⚠️ | `tests/e2e/` ada 6 files, tapi frontend terbatas |
| **KPI automated tracking** | ❌ | KPI targets defined di doc 19, tapi tidak ada automated measurement |
| **Performance regression test** | ❌ | Tidak ada baseline performance test |
| **Data quality monitoring** | ⚠️ | `data_quality_score` di DB, tapi tidak ada automated alert |

### 10.3 Analisis Gap

**Penyebab:** KPI tracking adalah fitur monitoring yang belum dibangun. Performance regression tidak prioritas untuk single-user.

**Dampak:** Tidak ada cara otomatis untuk mengetahui apakah sistem memenuhi KPI target. Degradasi performance tidak terdeteksi sampai user complain.

**Rencana:** Lihat §11.8 — Roadmap Testing & Quality

---

## 11. Rencana Penutupan Gap

### 11.1 Roadmap Frontend Recovery

**Prioritas: CRITICAL** — Tanpa frontend, aplikasi tidak usable.

| Phase | Halaman | Estimasi | Dependencies |
|-------|---------|----------|-------------|
| **F1** | Dashboard (portfolio summary, watchlist, market status) | 2 minggu | API sudah ada |
| **F2** | Stock Detail (chart, indicators, scores, recommendation, XAI) | 3 minggu | API sudah ada |
| **F3** | Backtest (config, results, equity curve) | 2 minggu | API sudah ada |
| **F4** | Screener & Analysis (factor screen, heatmap) | 2 minggu | API sudah ada |
| **F5** | Portfolio (positions, PnL, allocation) | 2 minggu | API sudah ada |
| **F6** | Settings (risk params, API key, notifications) | 1 minggu | API sudah ada |
| **F7** | Orders (jika OMS dibangun) | 2 minggu | OMS (§11.2) |

**Catatan:** Semua API endpoints sudah ada (95 endpoints). Frontend hanya perlu konsumsi API yang existing.

### 11.2 Roadmap OMS/Execution

**Prioritas: MEDIUM (personal)** — Untuk personal use, paper trading + manual eksekusi di broker app sudah cukup. OMS hanya jika ingin full automation.

| Phase | Komponen | Estimasi | Dependencies |
|-------|----------|----------|-------------|
| **O1** | Order state machine + event sourcing | 3 minggu | DB schema |
| **O2** | Smart Order Router (multi-broker) | 2 minggu | O1 |
| **O3** | Fill processor (partial fill, idempotency) | 2 minggu | O1 |
| **O4** | Kill switch + reconciliation | 2 minggu | O1 |
| **O5** | Broker API integration (Sinarmas/BNI) | 4 minggu | Broker API access |
| **O6** | FIX protocol (opsional) | 4 minggu | O5 |

**Blocker:** Broker API access. Sinarmas dan BNI Sekuritas belum menyediakan API publik. **Untuk personal use:** paper trading + manual eksekusi via broker app (e.g., BNI SmartPlus, Sinarmas Online) sudah cukup. OMS hanya diperlukan jika ingin full automation tanpa intervensi manual.

### 11.3 Roadmap Market Data

**Prioritas: MEDIUM** — EOD data cukup untuk decision support. Real-time hanya jika ada demand.

| Phase | Komponen | Estimasi | Dependencies |
|-------|----------|----------|-------------|
| **M1** | Stale data detection (7-state model) | 1 minggu | Ticker plant |
| **M2** | WebSocket price feed (bukan engine status) | 2 minggu | Real-time data source |
| **M3** | Redis cache untuk latest prices | 1 minggu | Redis setup |
| **M4** | Tick coalescer + delta encoder | 2 minggu | M2 |

**Blocker:** Real-time IDX data feed. Yahoo Finance hanya EOD. IDX DataFeed berbayar.

### 11.4 Roadmap Infrastructure

**Prioritas: LOW (personal)** — Single-user lokal tidak butuh Redis, CDN, HA, atau DR automation. Automated backup adalah satu-satunya yang worth doing.

| Phase | Komponen | Estimasi | Dependencies | Relevan? |
|-------|----------|----------|-------------|----------|
| **I1** | Automated backup (SQLite + Parquet) | 1 minggu | — | ✅ Ya |
| **I2** | DR runbook + automated recovery | 2 minggu | I1 | ⚠️ Opsional |
| **I3** | Redis setup untuk caching | 1 minggu | — | ❌ Tidak (personal) |
| **I4** | Comprehensive load test | 2 minggu | — | ❌ Tidak (personal) |
| **I5** | Stress test multi-failure | 2 minggu | I4 | ❌ Tidak (personal) |
| **I6** | Observability (latency histogram, queue depth) | 2 minggu | — | ❌ Tidak (personal) |

### 11.5 Roadmap Security

**Prioritas: LOW (personal, local)** — Sistem berjalan di localhost untuk satu user. API key auth sudah cukup. MFA, HTTPS, dan pen-test tidak relevan untuk personal local system.

| Phase | Komponen | Estimasi | Dependencies | Relevan? |
|-------|----------|----------|-------------|----------|
| **S1** | HTTPS reverse proxy (nginx/Caddy) | 1 minggu | — | ❌ Tidak (localhost) |
| **S2** | Field-level encryption (credentials) | 1 minggu | — | ⚠️ Opsional |
| **S3** | MFA (TOTP) | 2 minggu | — | ❌ Tidak (personal) |
| **S4** | Compliance 2026 update (UU P2SK, POJK 3/5) | 2 minggu | — | ❌ Tidak (personal) |
| **S5** | Penetration test | 1 minggu | S1-S3 | ❌ Tidak (personal) |

### 11.6 Roadmap AI/ML

**Prioritas: HIGH** — DSR adalah missing piece yang penting untuk validasi strategy.

| Phase | Komponen | Estimasi | Dependencies |
|-------|----------|----------|-------------|
| **A1** | Deflated Sharpe Ratio di `backtest/metrics.py` | 1 minggu | — |
| **A2** | Effective number of trials (eigenvalue) | 1 minggu | A1 |
| **A3** | Model drift detection | 2 minggu | Model registry (sudah ada) |
| **A4** | Live degradation alert | 1 minggu | A3 |
| **A5** | Automated KPI tracking | 2 minggu | — |

### 11.7 Roadmap Portfolio & User Features

**Prioritas: LOW (personal)** — Backend portfolio/screener/tax berfungsi. Frontend adalah bottleneck. Onboarding dan behavioral warning tidak relevan untuk personal use (user sudah paham sistemnya sendiri).

| Phase | Komponen | Estimasi | Dependencies | Relevan? |
|-------|----------|----------|-------------|----------|
| **P1** | Integrate rebalancer dengan execution | 2 minggu | OMS (§11.2) | ⚠️ Jika OMS dibangun |
| **P2** | Integrate strategy selector dengan UI | 1 minggu | Frontend (§11.1) | ⚠️ Opsional |
| **P3** | Onboarding (profil risiko kuesioner) | 2 minggu | Frontend | ❌ Tidak (personal) |
| **P4** | Behavioral warning UI | 2 minggu | Frontend | ❌ Tidak (personal) |
| **P5** | Inline education/glossary | 2 minggu | Frontend | ❌ Tidak (personal) |

### 11.8 Roadmap Testing & Quality

**Prioritas: MEDIUM**

| Phase | Komponen | Estimasi | Dependencies |
|-------|----------|----------|-------------|
| **T1** | KPI automated measurement script | 2 minggu | — |
| **T2** | Performance regression baseline | 1 minggu | — |
| **T3** | Data quality alert automation | 1 minggu | — |
| **T4** | E2E test expansion (sesuai frontend recovery) | Ongoing | Frontend |

---

## 12. Prioritas dan Timeline

### 12.1 Quick Wins (1-2 minggu, high impact untuk personal use)

| Item | Estimasi | Impact |
|------|----------|--------|
| **A1: Deflated Sharpe Ratio** | 1 minggu | Mencegah false discovery di backtest |
| **A5: Automated KPI tracking** | 2 minggu | Visibility ke sistem health |
| **I1: Automated backup** | 1 minggu | Data safety |

### 12.2 Critical Path (1-3 bulan)

| Item | Estimasi | Impact |
|------|----------|--------|
| **F1-F4: Frontend recovery** | 9 minggu | Aplikasi usable untuk personal decision support |
| **A3-A4: Model drift + live alert** | 3 minggu | AI reliability |

### 12.3 Long-term (3-12 bulan, opsional untuk personal use)

| Item | Estimasi | Impact | Relevan? |
|------|----------|--------|----------|
| **O1-O4: OMS core** | 9 minggu | Full order management | ⚠️ Jika ingin automation |
| **O5: Broker API integration** | 4 minggu | Real execution | ⚠️ Blocker: broker API |
| **M1-M4: Real-time market data** | 6 minggu | Intraday capability | ⚠️ Blocker: data feed |
| **F5-F7: Remaining frontend** | 5 minggu | Complete UI | ✅ Ya |
| **I2-I6: Infrastructure** | 8 minggu | Scale + reliability | ❌ Tidak (personal) |

### 12.4 Priority Matrix (Personal Use)

```
     HIGH IMPACT
         │
  F1-F4  │  A1, A5
         │  I1
         │
─────────┼─────────  LOW EFFORT
         │
  O1-O4  │  T1-T3
  M1-M4  │  A3-A4
         │
     LOW IMPACT

Legenda:
  F1-F4  = Frontend recovery (Dashboard, Stock Detail, Backtest, Screener)
  A1-A5  = AI/ML (DSR, KPI tracking, drift detection)
  I1     = Automated backup
  T1-T3  = Testing (KPI measurement, performance baseline, data quality alert)
  O1-O4  = OMS (opsional untuk personal)
  M1-M4  = Market data real-time (opsional untuk personal)
  
  Dihapus dari prioritas personal:
  S1-S5  = Security (MFA, HTTPS, pen-test) — N/A untuk localhost
  P3-P5  = Onboarding, behavioral warning, education — N/A untuk personal
  I2-I6  = DR, Redis, load test, observability — N/A untuk single-user
```

---

## Referensi

### Internal (Pustaka)
- `00-README.md` — Overview pustaka
- `12-panduan-membangun-aplikasi-pasar-modal.md` — Panduan sintesis
- `17-aplikasi-retail-pribadi.md` — Fitur retail
- `19-flow-logic-testing-kpi.md` — KPI targets
- `20-syarat-robot-auto-trading.md` — 12 pilar robot trading
- `28-api-design-integration-patterns.md` — API design
- `32-ui-ux-design-trading-app.md` — UI/UX design
- `40-oms-ems-architecture.md` — OMS/EMS design
- `43-mobile-app-architecture.md` — Mobile architecture
- `48-disaster-recovery-business-continuity.md` — DR plan
- `55-capacity-planning-load-stress-testing.md` — Capacity planning
- `85-backtest-to-live-gap-prevention.md` — Backtest gaps
- `86-gigantic-ai-autonomous-trading-system.md` — AI vision

### Internal (Codebase)
- `src/trading_system/` — 27 modul analysis, 95 API endpoints
- `frontend/app/` — 1 page (Data Inspection)
- `tests/unit/` — 51 test files, 700+ tests
- `pyproject.toml` — ruff, mypy, pytest config

---

> **Catatan:** Dokumen ini adalah audit jujur dan objektif. Pustaka berisi teori yang komprehensif (89 dokumen, ~68K baris), tetapi implementasi nyata (trading-system v0.1.11) adalah **sistem personal EOD untuk satu user** — bukan full trading platform untuk distribusi. Banyak teori di pustaka (mobile app, MFA, compliance distribusi, multi-user scaling, DR automation) memang **tidak perlu diimplementasikan** untuk personal use. Gap yang **relevan** untuk ditutup: (1) Frontend recovery — agar sistem usable untuk diri sendiri, (2) DSR — agar backtest tidak menipu, (3) KPI tracking — agar tahu sistem health, (4) Automated backup — agar data aman. Backend/data engine sudah matang; frontend adalah next phase yang paling berdampak.
