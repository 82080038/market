# Audit: Kapabilitas Aplikasi & Gap Analysis

> **Tanggal:** 16 Agustus 2026
> **Konteks:** Audit komprehensif kapabilitas aplikasi pasar modal berdasarkan database PostgreSQL 16 (83 tables + 5 views, ~6.6 GB), kode `src/market/` (163 file .py, 17 sub-packages), API layer (60+ endpoints), frontend Next.js 16 (13 halaman), dan pustaka pengetahuan (103 dokumen).
> **Scope:** Single-user personal decision-support system — bukan multi-user/enterprise.
> **Verifikasi:** Section B diverifikasi via batch audit (4 subagent paralel) terhadap kode aktual — 7 klaim dikoreksi, 15 gap baru ditemukan (total 42 gap terkatalog).

---

## A. Yang Sudah Bisa Dilakukan Aplikasi (Dengan DB Saat Ini)

### 1. Data Acquisition & Storage (✅ Fungsional)

- **OHLCV harian** ~928 tickers IDX + global via Yahoo Finance (`stock_prices`, ~2.9M rows)
- **Data fundamental** (PER, PBV, ROE, DER, market cap) di `fundamental_data`
- **Data makroekonomi** (BI Rate, Fed Rate, USD/IDR, inflasi, GDP) di `macro_data` + `macroeconomic_indicators`
- **Foreign flow** (net buy/sell asing) di `foreign_flow`
- **Broker flow** (aktivitas broker per ticker per hari) di `broker_flow`
- **Daily trading stats** (volume, value, frekuensi) di `daily_trading_stats`
- **Kalender bursa** (holidays IDX + global) di `exchange_holidays`
- **FX rates** untuk multi-currency di `fx_rates`
- **News + sentiment** di `news` + `news_sentiment`
- **Corporate actions** (splits, dividends) di `corporate_actions` + `dividends`
- **Policy events** (regulasi OJK/BI) di `policy_events`
- **External events** (geopolitical) di `external_events`
- **Satellite observations** (NDVI, weather) di `satellite_observations` + `satellite_ticker_locations`
- **Komoditas** (CL=F, CPO=F, GC=F, dll) di `stock_prices` + `commodity_to_stock_map`
- **Seasonal patterns** di `seasonal_patterns`
- **Earnings calendar** di `earnings_calendar`
- **DCC-GARCH results** di `dcc_garch_results`
- **Causal relationships** di `causal_relationships` + `causal_graphs`
- **Parquet sync** (DB → Parquet archive, incremental) di `parquet_sync_state`

### 2. Analysis Engine (✅ Fungsional — 39 modul)

- **Technical Analysis** — MA, RSI, MACD, ADX, ATR, Bollinger, Volume Profile (`technical.py`)
- **Fundamental Analysis** — PER/PBV/ROE/DER scoring (`fundamental.py`)
- **Macro Economic** — regime klasifikasi (Tightening/Easing/Growth/Slowdown) (`macro.py`)
- **Global Market** — 7 indeks global (S&P500, Nasdaq, Dow, Hang Seng, Nikkei, FTSE, DAX) (`global_market.py`)
- **Market Context** — 37K baris, konteks pasar multidimensi (`market_context.py`)
- **Multi-Factor** — factor-based analysis 35K baris (`multi_factor.py`)
- **Pattern Detector** — chart pattern detection, 32K baris (`pattern_detector.py`)
- **ML Signal** — machine learning signals, 33K baris (`ml_signal.py`)
- **Prediction** — next-period price prediction, 46K baris (`prediction.py`)
- **Profiling** — stock personality profiling, 51K baris (`profiling.py`)
- **Volume Features** — volume analysis, 27K baris (`volume_features.py`)
- **Signal Enhancer** — 25 SignalEnhancer engines, 35K baris (`signal_enhancer.py`)
- **Meta Labeling** — López de Prado triple-barrier, 31K baris (`meta_labeling.py`)
- **Alpha Signals** — 4 alpha engines (mean reversion, reversal, EWMA momentum, regime switch) (`alpha_signals.py`)
- **Sector Rotation** — analisis rotasi sektor (`sector_rotation.py`)
- **Pairs Trading** — cointegration-based pairs (`pairs_trading.py`)
- **Strategy Selector** — investor profile → strategy matching (`strategy_selector.py`)
- **Astronacci** — time cycle analysis (planetary cycles), 29K baris (`astronacci.py`)
- **Macro Correlation** — korelasi makroekonomi, 19K baris (`macro_correlation.py`)
- **Policy Event Scorer** — scoring dampak regulasi (`policy_event_scorer.py`)
- **Cross-Market Timezone** — analisis cross-market dengan timezone lag (`cross_market_timezone.py`)
- **Execution Analyzer** — analisis kualitas eksekusi, 21K baris (`execution_analyzer.py`)
- **Causal Discovery** — Granger causality (`causal_discovery.py`)
- **Spillover Lab** — Diebold-Yilmaz spillover (`spillover_lab.py`)
- **News Sentiment** — NLP sentiment analysis, 26K baris (`news_sentiment.py`)
- **Denoised News** — noise reduction news (`denoised_news.py`)
- **VTA Reasoning** — visual-technical-analytical reasoning (`vta_reasoning.py`)
- **Delisting Memory** — AI lessons dari delisting, 33K baris (`delisting_memory.py`)
- **Advisory** — screening → top picks (`advisory.py`)
- **Alerts** — alert system (`alerts.py`)
- **Decision Engine** — composite scoring + market driver narrative (`decision.py`)

### 3. Backtesting (✅ Fungsional)

- **Backtest engine** — next-bar-open execution, survivorship-free (`backtest/engine.py`)
- **Autonomous backtest** — automated runner (`backtest/autonomous.py`)
- **Paper trading** — simulator (`backtest/paper_trading.py`)
- **PnL analysis** — profit/loss tracking (`backtest/pnl.py`)
- **Strategies** — built-in strategies (`backtest/strategies.py`)

### 4. Risk Management (✅ Fungsional)

- **Risk Engine** — VaR, CVaR, Kelly criterion, position sizing (`risk/engine.py`)
- **Leverage** — leverage recommendation + justification (`risk/leverage.py`)
- **Daily risk metrics** di `daily_risk_metrics` table

### 5. Portfolio Management (✅ Fungsional)

- **Portfolio engine** — positions, NAV, PnL (`execution/portfolio.py`)
- **OMS** — order management system (`execution/oms.py`)
- **Automation** — auto trading engine dengan circuit breaker (`execution/automation.py`)
- **Broker adapter** — mock + paper execution (`execution/brokers.py`)
- **Tax calculator** — PPh22, PPh23, fee (`execution/validation.py`)
- **Positions, Orders, Equity Snapshots, Trade Journal** — semua ada DB table

### 6. AI/ML & MLOps (✅ Fungsional)

- **ML labels** — triple-barrier labeling di `ml_labels`
- **Market regime** — HMM-based regime detection di `market_regimes`
- **Model performance history** di `model_performance_history`
- **AI weights** — LR weight optimization di `ai_weights`
- **Strategy assignment** — best strategy per ticker di `strategy_assignment`
- **MLOps** — drift detection, cross-validation, feature store, model registry, promotion, training (`mlops/`)
- **Engine Ablation** — 42 engine terdaftar, scorecard KEEP/MARGINAL/REMOVE (`ablation/`)

### 7. Autonomous Agent (✅ Fungsional)

- **Agent** — autonomous trading agent (`autonomous/agent.py`)
- **Approval** — human-in-the-loop approval (`autonomous/approval.py`)
- **Hot swap** — strategy hot-swap (`autonomous/hot_swap.py`)
- **Memory** — agent memory (`autonomous/memory.py`)
- **Pipeline** — orchestration (`autonomous/pipeline.py`)
- **Sandbox** — safe execution sandbox (`autonomous/sandbox.py`)

### 8. Scheduler & Automation (✅ Fungsional)

- **Daily scheduler** — cron-based task runner (`scheduler.py`, 15K baris)
- **Scheduler tasks** — 20+ tasks (fetch EOD, global, macro, fundamental, intraday, news, recompute, signals, etc.) (`scheduler_tasks.py`, 51K baris)
- **Persistent state** — `scheduler_state` table for catch-up
- **Recompute pipeline** — incremental recompute with watermark (`recompute_watermark`)

### 9. API Layer (✅ Fungsional — 60+ endpoints)

- Analysis (scores, recommendation, advisory, pattern detect)
- Backtest (run, autonomous runner)
- Automation (config, plan, execute)
- Portfolio (summary, watchlist)
- Prediction (predict, verify, errors, risk adjustment)
- Delisting (summary, records, lessons, check, filter)
- Instruments (list, filter)
- Data (sources, watermarks, audit, fetch, quality)
- Prices (latest, intraday trigger, compare)
- Notifications (list, read, signals)
- Scheduler (status)
- Cosmos (astronacci + satellite data)
- Recompute (40K baris routes — comprehensive recompute API)
- FX risk assessment

### 10. Frontend (✅ 13 halaman — Next.js 16)

- **Dashboard** — portfolio summary, IHSG, top movers (`page.tsx`)
- **Cosmos** — astronacci cycles + satellite data visualization (`cosmos/page.tsx`, 1560 baris)
- **Backtest** — backtest configuration & results
- **Screener** — stock screening
- **Portfolio** — positions & PnL
- **Stock Detail** — per-ticker view
- **Signals** — trading signals
- **Automation** — auto trading config
- **Scheduler** — task status
- **Data** — data inspection
- **Reports** — report generation
- **Scan** — market scanning
- **Settings** — configuration

### 11. Security & Compliance (✅ Fungsional)

- API key auth, CORS, rate limiting
- Audit log (`audit_log`)
- PDP compliance (`security/pdp.py`)
- Sharia screening (`security/sharia.py`)
- Surveillance (`security/surveillance.py`)
- Credentials management (`security/credentials.py`)

### 12. Social/Advanced Features (✅ Kode ada)

- Robo advisor, copy trading, competitive analysis, monetization, onboarding, reporting (`social/`)
- Multi-asset: cross-market, fundamental scorer, FX risk (`multi_asset/`)

---

## B. Gap yang Masih Ada

> **Catatan verifikasi:** Setiap gap di bawah telah diverifikasi terhadap kode aktual via batch audit (4 subagent paralel, 16 Agustus 2026). Beberapa klaim audit awal dikoreksi berdasarkan evidence file konkret — ditandai dengan **[KOREKSI]**.

### B.1 Gap KRITIS (High Impact untuk Personal Use)

| # | Gap | Status | Evidence | Detail & Rekomendasi |
|---|-----|--------|----------|----------------------|
| 1 | **Deflated Sharpe Ratio (DSR)** | ✅ FIXED **[KOREKSI]** | `src/market/backtest/analysis.py:168-211` — function `deflated_sharpe_ratio()` ADA; `backtest/engine.py:173-237` — `_compute_metrics()` sekarang MEMANGGIL DSR (param `n_trials`); `tests/test_backtest_analysis.py:83-103` + 3 test baru di `test_backtest.py` | Function DSR lengkap & teruji, **sekarang terintegrasi** ke backtest pipeline via param `n_trials` di `BacktestEngine.run()`. Metric `deflated_sharpe_ratio` selalu ada di result (0.0 jika n_trials=1). **Status: CLOSED 16 Agustus 2026.** |
| 2 | **Model Drift Detection Alert** | ✅ SUDAH ADA **[KOREKSI]** | `src/market/mlops/drift.py:1-260` — `DriftDetector` (PSI, metric drift, feature drift); `scheduler_tasks.py:200-300` — `_task_drift_detection()`; `scheduler_tasks.py:1252-1257` — terjadwal harian 18:45 WIB; `scheduler_tasks.py:271-293` — **automated alert** via `app_notifications` (severity, drifted metrics, PSI scores) | **Klaim audit awal SALAH.** Automated alert SUDAH diimplementasi via tabel `app_notifications`. Task harian generate notifikasi saat model performance degradasi. File 260 baris (bukan 8K). **Tidak perlu fix.** Opsional: tambah channel Telegram/email jika ingin notifikasi push. |
| 3 | **KPI Automated Tracking** | ✅ FIXED | `scripts/track_kpi.py` (BARU) — 19 KPI measurements (8 auto + 9 manual + 2 warn); `kpi_history` table (CREATE TABLE IF NOT EXISTS); `scheduler_tasks.py:_task_track_kpi()` weekly Sabtu 13:30 WIB; emit `app_notifications` alert jika FAIL | **Status: CLOSED 16 Agustus 2026.** Script query DB untuk Infrastructure, Data Quality, AI Learning, Decision Engine, Compliance KPI. Tested: 8 PASS, 2 WARN, 0 FAIL, 9 MANUAL. |
| 4 | **Automated Backup** | ✅ FIXED | `scripts/backup_postgresql.sh` (BARU) — pg_dump + kompresi + retention policy; `scheduler_tasks.py:_task_backup_postgresql()` harian 19:35 WIB; handle `postgresql://` (TCP) + `postgresql+psycopg2:///db?host=socket` (Unix socket); `.env.example` — BACKUP_DIR, BACKUP_RETENTION_DAYS, BACKUP_FORMAT | **Status: CLOSED 16 Agustus 2026.** Tested: 648MB dump file berhasil dibuat. OS-aware BACKUP_DIR default (Linux: /media/petrick/Parquet/..., Windows: E:/projects/market/...). |

### B.2 Gap MEDIUM (Penting tapi tidak blocking)

| # | Gap | Status | Evidence | Detail & Rekomendasi |
|---|-----|--------|----------|----------------------|
| 5 | **Broker API Integration** | ⚠️ Stub **[KOREKSI]** | `src/market/execution/brokers.py:157-202` — `RealBroker` class stub dengan warning, **bukan `NotImplementedError`** (grep = 0 matches); `brokers.py:172` — `broker_name="sinarmas"` default; `brokers.py:161` — comment "(Sinarmas, BNI, etc.)" | **Klaim audit awal SALAH** — bukan exception, tapi stub return False/None dengan warning. BNI hanya disebut di comment. **Blocker eksternal:** Sinarmas/BNI belum buka API publik. Paper/Mock broker fungsional untuk simulasi. |
| 6 | **OMS Event Sourcing** | ❌ Tidak ada | `src/market/execution/oms.py:36-63` — `OrderStatus` enum + `VALID_TRANSITIONS` (state machine basic: NEW→PENDING→PARTIAL→FILLED); grep "event_sourcing\|OrderEvent\|aggregate" = 0 matches; `oms.py:66-96` — `Order` mutable object, bukan aggregate root | State machine basic ADA, tapi **bukan event sourcing** (no event store, no replay, no aggregate root). Untuk personal use, state machine saat ini cukup. Event sourcing relevan jika butuh audit trail/replay lengkap. |
| 7 | **Smart Order Router (SOR)** | ❌ Tidak ada | grep "smart_order_router\|SOR\|order_router\|route_order" di `src/market/` = 0 matches relevant; tidak ada file `*router*.py` di `execution/` | Tidak ada SOR untuk multi-broker routing. Order langsung ke broker adapter. **Relevan hanya jika multiple live broker** — saat ini paper/mock only, tidak prioritas. |
| 8 | **Real-time Price Feed** | ❌ Tidak ada **[KOREKSI]** | `src/market/api/routes_recompute.py:53` — `@router.websocket("/ws/recompute")` untuk streaming progress recompute; grep "ws/live\|price.*stream" di `src/market/api/` = 0 matches; `app.py` tidak ada price streaming endpoint | **Klaim audit awal tidak akurat** — tidak ada `/ws/live` endpoint sama sekali. WebSocket hanya untuk recompute progress. Data EOD only via yfinance. **Blocker eksternal:** real-time IDX feed berbayar. Intraday polling 15-menit cukup untuk Day Trading monitoring. |
| 9 | **Stale Data Detection (7-state)** | ❌ Tidak ada | `src/market/data/data_health.py:67-132` — `check_stale_data()` hanya cek tanggal > N hari (STALE_DAYS_WARNING=3, STALE_DAYS_CRITICAL=7); `pustaka/66-market-data-distribution.md:721-781` — definisi 7-state: LIVE/DEGRADED/STALE/FALLBACK/RECOVERING/DEAD/MARKET_CLOSED; grep "MarketDataState\|DEGRADED\|FALLBACK\|RECOVERING" di data_health.py = 0 matches | Staleness check berbasis tanggal ADA, tapi **bukan 7-state freshness tracker** seperti di pustaka. 7-state relevan jika ada real-time WebSocket feed dengan quote age tracking. Untuk EOD-only, check saat ini adequate. |
| 10 | **Data Quality Alert Automation** | ❌ Tidak ada | `alembic/versions/0001_initial_schema.py:82` — `data_quality_score` di legacy ohlcv (SQLite); `db/models.py:90-119` — OHLCV view over `stock_prices`, **tidak punya** `data_quality_score`; `data/cleanup_data.py:217-218` — UPDATE ohlcv SET data_quality_score=0.3 untuk volume=0; `pipelines/alerts.py:1-311` — AlertPipeline cek 5 kondisi (recompute fail, Fear&Greed, VIX, position breach, price movement) **tanpa DQ score check**; grep "data_quality" di scheduler_tasks.py = 0 matches | `data_quality_score` ada di legacy SQLite ohlcv tapi **tidak di `stock_prices`** (PostgreSQL partitioned). AlertPipeline tidak monitor DQ drop. **Fix:** tambah `data_quality_score` ke `stock_prices` (migration) + check di AlertPipeline + scheduler task. |
| 11 | **Performance Regression Test** | ❌ Tidak ada | `tests/` — tidak ada `test_performance.py`/`test_benchmark.py`/`test_regression.py`; `pyproject.toml:42-52` — dev deps tidak termasuk `pytest-benchmark` | Tidak ada baseline performance test atau benchmark suite. **Fix:** tambah `pytest-benchmark` ke dev deps + buat `tests/test_performance.py` untuk critical path (recompute, backtest engine, signal generation). |
| 12 | **Portfolio Rebalancer Integration** | ⚠️ Sebagian | `src/market/execution/portfolio.py:37-225` — `PortfolioEngine.needs_rebalance()` (line 159) + `compute_rebalance_orders()` (line 179); `execution/automation.py:114` — config `auto_rebalance: bool = False`; grep "PortfolioEngine\|compute_rebalance" di automation.py = 0 matches; `automation.py:891-1145` — `execute_plan()` tidak panggil rebalance | Backend rebalancer fungsional, tapi **tidak terintegrasi** ke automation/execution path. Flag `auto_rebalance` ada di config tapi tidak diimplementasi. **Fix:** integrasi `compute_rebalance_orders()` ke `PlanBuilder`/`AutoExecutor` saat `auto_rebalance=True`. |
| 13 | **Strategy Selector Integration** | ⚠️ Sebagian | `src/market/analysis/strategy_selector.py:210-249` — `StrategySelector.select()`; `scheduler_tasks.py:738-784` — `_task_strategy_assignment()` weekly → persist ke `strategy_assignment` table; grep "strategy_selector" di `src/market/api/` = 0 matches; frontend tidak ada komponen strategy_selector | Backend fungsional + scheduled weekly, tapi **tidak ada API endpoint** untuk query hasil & **tidak ada UI**. **Fix:** tambah `GET /api/strategy/assignment/{ticker}` + section di Stock Detail page frontend. |

### B.3 Gap LOW (Tidak relevan untuk personal use)

| # | Gap | Status | Relevan? |
|---|-----|--------|----------|
| 14 | MFA/TOTP | ❌ | ❌ Tidak (single-user, localhost) |
| 15 | HTTPS/TLS | ⚠️ Dev HTTP | ❌ Tidak (localhost) |
| 16 | Redis Cache | ❌ | ❌ Tidak (single-user) |
| 17 | DR Automation | ❌ | ⚠️ Opsional |
| 18 | FIX Protocol | ❌ | ❌ Tidak |
| 19 | Mobile App | ❌ | ❌ Tidak |
| 20 | Onboarding/Kuesioner | ❌ | ❌ Tidak (personal) |
| 21 | Multi-user/RBAC | ❌ | ❌ Tidak |

### B.4 Gap BARU — Dead Code & Integrasi (Tambahan dari audit kode terkini)

| # | Gap | Status | Evidence | Detail & Rekomendasi |
|---|-----|--------|----------|----------------------|
| 22 | **Social/Copy Trading** | ⚠️ Dead code | `src/market/social/copy_trading.py` (7,783 baris), `social/robo_advisor.py` (11,925 baris); grep "copy_trading\|robo_advisor" di `src/market/api/` = 0 matches; grep di `scheduler_tasks.py` = 0 matches; `app.py` tidak ada router registration | Kode lengkap ADA tapi **dead code** — tidak dipanggil dari API/scheduler manapun. **Fix:** buat `routes_social.py` + register di `app.py`, ATAU hapus jika tidak relevan untuk single-user. |
| 23 | **Multi-Asset Cross-Market** | ⚠️ Sebagian **[KOREKSI]** | `src/market/multi_asset/cross_market.py` (12,836 baris); grep "cross_market" di `src/market/api/` = 0 matches; **`src/market/analysis/recompute.py:1133`** — `from market.multi_asset.cross_market import recompute_cross_market` (TERINTEGRASI ke recompute pipeline) | **Klaim audit awal SALAH** — cross_market SUDAH terintegrasi ke recompute pipeline. Tapi benar **tidak ada API route** yang expose hasil ke frontend. **Fix:** tambah endpoint di `routes_instruments.py` atau buat `routes_multi_asset.py` untuk cross-market correlation matrix, lead-lag, spillover heatmap. |
| 24 | **Security Modules** | ⚠️ Dead code | `src/market/security/sharia.py` (7,516 baris), `security/surveillance.py` (10,998 baris), `security/fractional.py` (6,539 baris); grep "sharia\|surveillance\|fractional" di `src/market/api/` = 0 matches; grep "from market.security" di `src/market/` = 0 matches | Ketiga module **dead code** — tidak di-import dari manapun. **Fix:** Sharia screening → integrasi ke screener jika user butuh; surveillance (market abuse) → tidak relevan single-user; fractional → relevan jika broker dukung. Pertimbangkan hapus jika tidak akan diintegrasikan. |
| 25 | **Frontend ↔ API Coverage** | ⚠️ Sebagian | 13 halaman ada; 11 halaman konsumsi API dengan baik; **`reports/page.tsx`** — UI placeholder "Generate" button tanpa API call; **`settings/page.tsx`** — UI form tanpa fetch/POST ke backend; API tidak dikonsumsi: `/api/recompute/*` (40K baris routes), `/api/scores/{ticker}`, `/api/recommend/{ticker}`, `/api/readiness/{ticker}` | 2 halaman (reports, settings) **tidak terhubung backend**. Recompute API tidak diakses dari frontend Next.js. **Fix:** tambah API endpoints untuk reports (tax, dividend, trade log) + settings (save/load config) + connect frontend. |
| 26 | **Social Sentiment (Reddit/X)** | ❌ Tidak ada **[KOREKSI]** | grep "reddit\|twitter\|social_sentiment\|SocialMedia" di `src/market/` = 0 matches; `analysis/sentiment.py:50` — weight `social_media: 0.15` tapi hanya parameter tanpa implementasi; `analysis/news_sentiment.py` (26K baris) — lexicon-based NEWS sentiment, BUKAN social media | **Klaim audit awal SALAH** — tidak ada class SocialSentiment sama sekali. Hanya placeholder weight di SentimentEngine. **Fix:** implementasi module baru dengan `praw` (Reddit) + `tweepy` (X) jika dibutuhkan, ATAU hapus placeholder `social_media` weight. |
| 27 | **Google Trends** | ❌ Tidak ada **[KOREKSI]** | grep "google_trends" di `src/market/` = 5 hasil, semua di `sentiment.py` (parameter weight); grep "pytrends" = 0 matches; tidak ada file `google_trends.py`/`trends.py`; `pustaka/30-sentiment-analysis-alternative-data.md:472-504` — contoh `pytrends.request.TrendReq` hanya di dokumentasi | **Klaim audit awal SALAH** — tidak ada class GoogleTrendsCollector. Hanya placeholder parameter. **Fix:** implementasi `src/market/analysis/google_trends.py` dengan pytrends (sesuai contoh pustaka/30) + integrate ke scheduler & SentimentEngine, ATAU hapus placeholder. |

### B.5 Gap BARU — Ditemukan via Batch Audit (verifikasi 16 Agustus 2026)

| # | Gap | Status | Evidence | Prioritas |
|---|-----|--------|----------|-----------|
| 28 | **Structured Logging & Log Aggregation** | ❌ Tidak ada | `api/app.py:81` — hanya `logging.getLogger(__name__)`; grep "structlog\|loguru" = 0 matches; tidak ada JSON logging atau log aggregation (ELK/Loki) | LOW |
| 29 | **Global Error Handler API** | ❌ Tidak ada | `api/app.py:175-214` — FastAPI app tanpa `@app.exception_handler()`; `data/rate_limit.py:24-30` — CircuitBreakerError hanya untuk rate limiter, bukan global | MEDIUM |
| 30 | **Database Migration Testing** | ❌ Tidak ada | `tests/conftest.py:14-17` — note: "alembic 0001-0006 contain SQLite-isms that fail on PostgreSQL... we clone schema via pg_dump rather than running alembic upgrade head"; `tests/test_cli.py:18-29` — test CLI command, bukan migration logic | MEDIUM |
| 31 | **OpenAPI/Swagger UI** | ✅ FIXED | `api/app.py:177-181` — FastAPI app sekarang punya `docs_url="/docs"`, `redoc_url="/redoc"`, `openapi_url="/openapi.json"` | ✅ CLOSED 16 Agustus 2026 |
| 32 | **Frontend Unit Testing** | ❌ Tidak ada | `frontend/package.json:5-10` — scripts: dev, build, start, lint, type-check (tidak ada test); `frontend/playwright.config.ts` — hanya E2E; tidak ada jest/vitest | LOW |
| 33 | **CI/CD Frontend Build** | ⚠️ Sebagian | `.github/workflows/ci.yml:1-32` — hanya ruff + mypy + pytest (Python); tidak ada `npm run build` atau deploy step | LOW |
| 34 | **Pre-commit Hooks** | ✅ FIXED | `.pre-commit-config.yaml` (BARU) — ruff (lint+format), mypy, pre-commit-hooks (whitespace, YAML, large files, private key), conventional-pre-commit (commit-msg) | ✅ CLOSED 16 Agustus 2026. Run `pre-commit install` untuk aktifkan. |
| 35 | **Data Lineage & Provenance** | ❌ Tidak ada | grep "lineage\|provenance" di `src/market/` = 0 matches; `data/acquisition.py:73-76` — hanya `update_source_health`, tidak ada lineage tracking | LOW |
| 36 | **Feature Store Freshness Monitoring** | ❌ Tidak ada | `mlops/feature_store.py:1-100` — feature store ADA dengan versioning + caching; grep "freshness" di `mlops/` = 0 matches | LOW |
| 37 | **Model Registry Persistence** | ⚠️ Sebagian | `mlops/registry.py:1-100` — model registry ADA dengan versioning + aliases (@experiment, @candidate, @champion); `registry.py:59-62` — `self._models: dict[str, ModelVersion] = {}` **in-memory only**, hilang setelah restart | MEDIUM |
| 38 | **Explainability (XAI)** | ❌ Tidak ada | grep "shap\|lime" di `src/market/` = 0 matches (kecuali `shapely` di satellite_fetcher); `multi_factor.py:432,478,513-537` — hanya PCA explained_variance + sklearn `feature_importances_`; `decision.py:4` — mention "XAI" tapi hanya narasi | LOW |
| 39 | **Combinatorial Purged CV (CPCV)** | ⚠️ Sebagian | `mlops/cross_validation.py:1-50` — walk-forward + purged k-fold ADA; line 7: "Combinatorial purged cross-validation (CPCV) stub" — belum diimplementasi lengkap | LOW |
| 40 | **Market Impact Model** | ⚠️ Sebagian | `execution/brokers.py:89-136` — PaperBroker dengan volume-adjusted slippage (base 0.05%, scaling non-linear jika order > 1% ADV); `execution_analyzer.py:1-558` — slippage analysis ADA; tidak ada Almgren-Chriss model untuk large orders | LOW |
| 41 | **Annual Tax Report Generator** | ❌ Tidak ada | `execution_analyzer.py:333-389` — PPh Final 0.1% calculation ADA; `brokers.py:140-150` — sales tax ADA; grep "annual_report" = 0 matches — tidak ada generator laporan pajak tahunan | MEDIUM |
| 42 | **Notification Channel (Telegram/Email)** | ⚠️ Sebagian | `analysis/alerts.py:38-44` — `AlertChannel` enum: TELEGRAM, EMAIL, IN_APP, WEBHOOK; `autonomous/approval.py:70-75,273-275` — Telegram bot token/chat_id params, line 274: "In production: send via Telegram Bot API" (stub); IN_APP sudah berfungsi via DB table | LOW |

---

## C. Ringkasan Prioritas (Update post-verifikasi)

### C.1 Koreksi Status Gap (audit awal vs verifikasi kode)

| Gap | Klaim Awal | Status Aktual | Catatan |
|-----|-----------|---------------|---------|
| 1 DSR | ❌ Tidak ada | ⚠️ Sebagian | Function ada & teruji, tapi tidak terintegrasi ke engine |
| 2 Drift Alert | ⚠️ Sebagian | ✅ Sudah ada | Automated alert via `app_notifications` sudah berfungsi |
| 5 Broker API | ⚠️ Stub (NotImplementedError) | ⚠️ Stub (warning) | Bukan exception, tapi stub return False/None |
| 8 Real-time | ⚠️ Sebagian (/ws/live) | ❌ Tidak ada | Tidak ada /ws/live; hanya /ws/recompute |
| 23 Multi-Asset | ⚠️ Tidak terintegrasi | ⚠️ Sebagian | Sudah terintegrasi ke recompute pipeline |
| 26 Social Sentiment | ⚠️ Stub | ❌ Tidak ada | Tidak ada class, hanya placeholder weight |
| 27 Google Trends | ⚠️ Stub | ❌ Tidak ada | Tidak ada class, hanya placeholder parameter |

### C.2 Quick wins (1-2 minggu, LOW effort + HIGH impact) — ✅ DIIMPLEMENTASI 16 Agustus 2026

1. ✅ **Integrasi DSR** ke `backtest/engine.py:_compute_metrics()` — function sudah ada, tinggal panggil. Param `n_trials` di `BacktestEngine.run()`, metric `deflated_sharpe_ratio` di result.
2. ✅ **Automated backup PostgreSQL** — `scripts/backup_postgresql.sh` (pg_dump + retention) + scheduler task `_task_backup_postgresql()` harian 19:35 WIB.
3. ✅ **KPI tracking script** — `scripts/track_kpi.py` (19 KPI measurements) + `kpi_history` table + scheduler task `_task_track_kpi()` weekly Sabtu 13:30 WIB.
4. ✅ **Pre-commit hooks** — `.pre-commit-config.yaml` (ruff + mypy + pre-commit-hooks + conventional commits).
5. ✅ **OpenAPI/Swagger UI** — `docs_url="/docs"`, `redoc_url="/redoc"`, `openapi_url="/openapi.json"` di FastAPI app.

### C.3 Medium term (1-3 bulan)

6. **Data quality alert automation** — tambah `data_quality_score` ke `stock_prices` + check di AlertPipeline
7. **Integrasi dead code modules** ke API routes (social, multi-asset expose, security/sharia ke screener)
8. **Frontend reports & settings** — connect ke backend API
9. **Strategy selector API + UI** — `GET /api/strategy/assignment/{ticker}` + section di Stock Detail
10. **Portfolio rebalancer integration** — wire `compute_rebalance_orders()` ke AutoExecutor
11. **Global error handler API** — `@app.exception_handler()` + circuit breaker DB
12. **Model registry persistence** — persist ke DB/file (saat ini in-memory)
13. **Annual tax report generator** — untuk compliance pajak tahunan
14. **DB migration testing** — test alembic migration logic (saat ini via pg_dump clone)

### C.4 Blocker eksternal (tidak bisa di-fix dengan kode)

15. **Broker API** — Sinarmas/BNI belum buka API publik → paper/mock only
16. **Real-time IDX data feed** — berbayar → EOD + intraday polling 15-menit cukup

### C.5 Priority Matrix (Personal Use, post-verifikasi)

```
     HIGH IMPACT
         │
  DSR     │  KPI Tracking
  Integr. │  Automated Backup
           │  Pre-commit Hooks
           │  Swagger UI
───────────┼──────────  LOW EFFORT
           │
  DQ Alert │  Module Integration
  Rebalance│  Strategy Selector UI
  Registry │  Reports/Settings FE
  Persist. │  Global Error Handler
           │  Tax Report
           │  Migration Testing
     LOW IMPACT

Sudah closed (tidak perlu action):
  ✅ Drift Alert (automated via app_notifications)

Dihapus dari prioritas personal:
  MFA, HTTPS, Redis, DR, FIX, Mobile, Onboarding, Multi-user,
  Structured Logging, Frontend Unit Test, CI/CD Frontend,
  Data Lineage, Feature Freshness, XAI, CPCV, Market Impact,
  Notification Channel (Telegram/Email), SOR, OMS Event Sourcing,
  7-state Stale Detection, Social Sentiment, Google Trends
```

---

## D. Kesimpulan

Backend dan database sudah sangat matang — **83 tables + 5 views**, **60+ API endpoints**, **39 analysis modul**, **13 frontend pages**, **autonomous agent**, **MLOps**, **engine ablation framework**. Hasil verifikasi batch menemukan:

1. **2 gap yang sebenarnya SUDAH closed:** Drift Alert (gap 2) sudah ada automated alert via `app_notifications`; Multi-Asset Cross-Market (gap 23) sudah terintegrasi ke recompute pipeline.
2. **3 gap yang statusnya dikoreksi lebih akurat:** DSR (function ada tapi tidak terintegrasi), Broker API (stub warning bukan NotImplementedError), Real-time (tidak ada /ws/live sama sekali).
3. **2 gap yang sebenarnya TIDAK ADA implementasi sama sekali:** Social Sentiment (gap 26) dan Google Trends (gap 27) — hanya placeholder parameter, bukan stub class.
4. **15 gap BARU ditemukan** (nomor 28-42): 4 MEDIUM (global error handler, migration testing, model registry persistence, tax report) + 11 LOW.

### Quick Wins Diimplementasi (16 Agustus 2026)

5 dari 5 quick wins prioritas telah diimplementasi dan diverifikasi:
- ✅ **Gap 1 DSR** — terintegrasi ke `BacktestEngine._compute_metrics()` dengan param `n_trials`
- ✅ **Gap 3 KPI Tracking** — `scripts/track_kpi.py` + `kpi_history` table + scheduler task weekly
- ✅ **Gap 4 Automated Backup** — `scripts/backup_postgresql.sh` + scheduler task harian 19:35 WIB
- ✅ **Gap 31 Swagger UI** — `/docs`, `/redoc`, `/openapi.json` diaktifkan di FastAPI app
- ✅ **Gap 34 Pre-commit Hooks** — `.pre-commit-config.yaml` dengan ruff + mypy + conventional commits

**Gap utama yang masih perlu ditutup (medium term):**
- **Integrasi dead code modules** ke API routes (social, security, multi-asset expose)
- **Data quality alert** (score tidak di-monitor AlertPipeline)
- **Frontend reports & settings** (2 halaman placeholder tanpa backend)
- **Strategy selector API + UI** — `GET /api/strategy/assignment/{ticker}` + section di Stock Detail
- **Portfolio rebalancer integration** — wire `compute_rebalance_orders()` ke AutoExecutor
- **Global error handler API** — `@app.exception_handler()` + circuit breaker DB
- **Model registry persistence** — persist ke DB/file (saat ini in-memory)
- **Annual tax report generator** — untuk compliance pajak tahunan
- **DB migration testing** — test alembic migration logic (saat ini via pg_dump clone)

Backend/data engine sudah matang; penutupan gap medium term akan meningkatkan reliability dan visibility sistem secara signifikan. Quick wins (DSR, backup, KPI, pre-commit, Swagger) sudah selesai dengan effort rendah dalam 1 sesi.

---

> **Referensi:**
> - `pustaka/88-gap-teori-vs-praktek.md` — Gap analysis sebelumnya (v0.1.11)
> - `pustaka/18-modul-engine-data-wajib.md` — Referensi definitif modul/engine
> - `pustaka/19-flow-logic-testing-kpi.md` — KPI targets definition (line 988-1123)
> - `pustaka/30-sentiment-analysis-alternative-data.md` — Contoh implementasi pytrends (line 472-504)
> - `pustaka/66-market-data-distribution.md` — 7-state data freshness model (line 721-781)
> - `pustaka/00-README.md` — Index pustaka
> - `src/market/db/models.py` — 50+ ORM models (1388 baris)
> - `src/market/api/app.py` — 60+ API endpoints
> - `src/market/backtest/analysis.py:168-211` — DSR function (belum terintegrasi ke engine)
> - `src/market/mlops/drift.py:1-260` — DriftDetector + automated alert (sudah berfungsi)
> - `src/market/scheduler_tasks.py:271-293,1252-1257` — Drift detection task + alert via app_notifications
> - `src/market/analysis/recompute.py:1133` — cross_market sudah terintegrasi ke recompute pipeline
> - `frontend/src/app/` — 13 halaman Next.js
>
> **Metodologi verifikasi:** Batch audit via 4 subagent paralel (16 Agustus 2026) — verifikasi setiap gap terhadap kode aktual dengan grep + readfile. 7 klaim audit awal dikoreksi, 15 gap baru ditemukan.
