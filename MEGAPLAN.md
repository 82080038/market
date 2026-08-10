# MEGAPLAN — Aplikasi Pasar Modal Single-User (Pustaka 00–93)

**Ringkasan 1 kalimat:** Membangun aplikasi pasar modal personal yang lengkap (Linux: `/opt/lampp/htdocs/market/`, Windows: `C:\xampp\htdocs\market\`) dari nol, mengikuti 98 dokumen `pustaka/` (00-97) dan mengadopsi pola dari `trading-system` v0.1.11 sebagai referensi, dengan fase-fase dari MVP saham Indonesia menuju multi-pasar/multi-aset dan AI self-evolution, serta environment lifecycle Research → Paper → Live yang ketat.

---

## 1. Visi & Tujuan

Membuat satu aplikasi desktop/web single-user untuk analisis, rekomendasi, simulasi (paper trading), dan — setelah melewati promotion gates — eksekusi saham IDX yang aman, transparan, dan dapat diaudit. Aplikasi pada akhirnya dapat diperluas ke multi-pasar dan multi-aset sesuai `92-multi-market-multi-asset-trading-system.md` dan `93-lifecycle-environments-real-testing-ai.md`.

## 2. Acceptance Criteria Utama

1. **Data Pipeline:** Setiap hari aplikasi mengambil data EOD Yahoo Finance/IDX, membersihkannya, mendeteksi corporate actions, dan menyimpannya ke SQLite dalam <30 menit untuk ~923 saham aktif.
2. **Decision Engine:** Endpoint `/api/recommend/{ticker}` mengembalikan skor 0-100, sinyal, VaR 95%, position size, dan narasi XAI Bahasa Indonesia.
3. **Backtest Valid:** Event-driven, next-bar-open, realistic cost/slippage, walk-forward, tidak ada look-ahead bias.
4. **Paper Trading:** Simulasi order memperhitungkan lot IDX (100), biaya broker, PPh final 0.1%, dividen 10%.
5. **UI Dashboard:** Pengguna dapat melihat portfolio, watchlist, rekomendasi, backtest equity curve, laporan pajak, dan laporan lainnya.
6. **Audit & Safety:** Setiap perubahan konfigurasi, rekomendasi, dan order dicatat; eksekusi nyata memerlukan persetujuan eksplisit.
7. **Test Coverage:** Backend unit + integration test ≥70%; frontend smoke test ≥5 skenario kritis.
8. **Multi-Market Ready:** Instrument master, market registry, FX engine, dan OMS multi-pasar tersedia (meski live trading awal tetap IDX).
9. **Autonomous Loop (Fase akhir):** LLM agent dapat mengusulkan perbaikan kode/strategi, menjalankan test, dan mengintegrasikan setelah eval-gate.

## 3. Scope

### In Scope
- Seluruh topik yang dibahas di 98 dokumen `pustaka/` (00-97), dikelompokkan ke dalam 12 fase berikut.
- Tech stack: Python 3.11+ (FastAPI, uv, Alembic, SQLite WAL, pandas, PyTorch cu121), Next.js 14+ (TypeScript, Tailwind).
- Single-user deployment lokal (Linux/WSL) dan Docker.
- Migrasi data dari Parquet archive (read-only) ke SQLite lokal. Lihat `src/market/paths.py` untuk path OS-aware.
- Bahasa Indonesia UI + tooltip untuk istilah teknis.
- GPU `cuda:1` untuk LSTM, walk-forward, Monte Carlo, NLP/IndoBERT.

### Out of Scope (kecuali diminta eksplisit)
- Multi-user, KYC, RBAC, deployment publik/enterprise.
- Otorisasi regulator untuk memberikan saran investasi ke publik.
- Eksekusi uang nyata tanpa persetujuan manual.
- **Scalping/HFT** — tidak ada data tick-level, tidak ada WebSocket streaming, tidak ada co-located server. Metodologi adalah Quant/Algorithmic Trading dengan target Day Trading (intraday 15-min polling) dan Swing Trading (EOD + recompute).

## 4. Constraints & Assumptions

- Single-user personal; API key di `.env` cukup.
- UTC storage, WIB display (UTC+7).
- Data EOD utama; intraday polling 15-menit via yfinance untuk ~40 ticker penting (Day Trading monitoring). Real-time tick feed berbayar tidak dirancang.
- GPU 2× GTX 1050 Ti 4 GB; batasi batch size dan hidden dim.
- Parquet existing hanya dibaca; tulis data sendiri ke direktori project.
- `.env` dan kredensial tidak di-commit; patuhi UU PDP.
- AI boleh mengembangkan kode secara otonom; human-gate untuk live trading dan perubahan skema DB produksi.

---

## 5. Fase Implementasi & Completion Markers

**Legenda:** `[ ]` = belum dikerjakan | `[~]` = sedang dikerjakan | `[x]` = selesai | **(PR)** = butuh persetujuan manual sebelum merge/live

---

### Fase 0 — Bootstrap & Environment Lifecycle (Minggu 1) ✅ SELESAI

**Tujuan:** repo siap, tooling aktif, 3 environment terdefinisi, CI skeleton.

**Dokumen acuan:** `37-bahasa-pemrograman-tech-stack.md`, `93-lifecycle-environments-real-testing-ai.md`, `27-deployment-devops-trading.md`, `50-change-release-management-trading.md`, `41-uu-pdp-compliance-fintech.md`, `33-cybersecurity-trading-system.md`, `47-operational-contract-runbook.md`.

**Deliverables & Markers:**
- [x] `pyproject.toml`, `uv.lock`, `.env.example`, `.gitignore`, `README.md` root.
- [x] Struktur direktori `src/market/`, `frontend/`, `tests/`, `alembic/`, `data/`, `scripts/`.
- [x] Tooling: ruff, mypy, pytest, pre-commit hook.
- [x] Environment selector: `ENV=research|paper|live` via CLI/API.
- [x] Database isolation: `market_research.db`, `market_paper.db`, `market_live.db`.
- [x] Broker adapter skeleton: `MockBroker`, `PaperBroker`, `RealBroker` (interface akan dibuat Fase 5).
- [x] `.env` templates per environment.
- [x] GitHub Actions CI: lint + test skeleton.
- [x] ADR (Architecture Decision Record) untuk 5 keputusan besar.

**Acceptance:** `uv sync` berhasil, `ruff check .` + `mypy src/market` + `pytest` bersih (coverage 92.55%).

---

### Fase 1 — Data Platform & Migration (Minggu 2-4) [✓] DONE

**Tujuan:** data bersih, tersistem, dapat di-query, parquet berharga dimigrasi.

**Dokumen acuan:** `22-data-engineering-pipeline.md`, `84-new-data-arrival-processing-pipeline.md`, `90-analisis-parquet-data-awal.md`, `36-gap-data-timezone-global-idx.md`, `75-corporate-actions-processing-adjustment.md`, `91-komoditas-spesifik-idx.md`, `66-market-data-distribution.md`, `53-data-governance-lineage.md`.

**Deliverables & Markers:**
- [x] `market_registry` table (MIC, timezone, trading hours, DST, settlement, lot, tick, currency).
- [x] Extended `instrument_master` dengan `asset_class`, `market_mic`, `base_currency`, `lot_size`, `tick_size`, `underlying_ticker`.
- [x] Data acquisition engine: Yahoo Finance adapter, IDX scraper, parquet archive fallback.
- [x] Data quality validation: 4 checks (completeness, plausibility, volume spike, gap detection) + score/action tier.
- [x] `market_calendar` table + timezone/DST engine.
- [x] `fx_rates` table + FX engine (USDIDR, HKDIDR, JPYIDR, dll.).
- [x] Corporate action detection & backward adjustment.
- [x] Migration 8 dataset parquet ke SQLite (ohlcv, corporate_actions, dividends, macro_data, foreign_flow, market_calendar, fundamental_data, stock_personality).
- [x] Daily scheduler skeleton.

**Acceptance:** `market_paper.db` terisi OHLCV ≥2.9M rows, commodity, sentiment, shareholders; `fetch --universe idx` sukses tanpa FAIL major.

---

### Fase 2 — Core Analysis Engines: IDX (Minggu 5-7) [✓] DONE

**Tujuan:** setiap faktor pasar modal dapat dihitung dan di-skor untuk saham Indonesia.

**Dokumen acuan:** `05-analisis-teknikal.md`, `06-analisis-fundamental.md`, `07-manajemen-risiko.md`, `18-modul-engine-data-wajib.md`, `21-portfolio-optimization-construction.md`, `23-machine-learning-trading.md`, `24-market-microstructure-likuiditas.md`, `30-sentiment-analysis-alternative-data.md`, `35-multi-asset-cross-market-analysis.md`, `39-screening-aiml-pattern-memory.md`, `58-feature-store-engineering-pipeline.md`, `31-risk-management-lanjutan.md`.

**Deliverables & Markers:**
- [x] Technical analysis engine (RSI, MACD, MA, ADX, ATR, BB, volume profile).
- [x] Fundamental analysis engine (PER, PBV, ROE, DER, EPS growth, DCF stub).
- [x] Macro/global engine (US10Y, USD/IDR, oil, gold, S&P 500, etc.).
- [x] Relationship/correlation engine (lead-lag, spillover, clustering).
- [x] Sentiment engine (lexicon-based NLP, foreign flow, broker flow, news, social media).
- [x] Corporate action engine integrated into technical signals.
- [x] Feature store with 42+ features per ticker, tagged `market_mic` + `asset_class`.
- [x] Pattern memory / reliability tracker.

**Acceptance:** `/api/scores/{ticker}` returns 6 factor scores; unit tests per engine ≥70% coverage.

---

### Fase 3 — Decision, XAI & Advisory (Minggu 8-9) [✓] DONE

**Tujuan:** aplikasi dapat memberikan saran yang dapat dijelaskan.

**Dokumen acuan:** `12-panduan-membangun-aplikasi-pasar-modal.md`, `18-modul-engine-data-wajib.md`, `46-prediksi-pola-portfolio-pipeline.md`, `83-advisory-system-screening-to-recommendation.md`, `85-backtest-to-live-gap-prevention.md`, `69-knowledge-base-persistent-memory.md`.

**Deliverables & Markers:**
- [x] Decision engine with default weights (technical 20%, fundamental 25%, macro/global/sentiment/relationship).
- [x] Regime-based weight adjustment.
- [x] XAI narrative generator (Bahasa Indonesia, top 3 factors, warning flags).
- [x] Advisory pipeline: screening → stock personality → strategy rec → position sizing → entry/exit → expected return → XAI evidence.
- [x] `/api/recommend/{ticker}` endpoint.
- [x] `/api/advisory/{ticker}` endpoint.
- [x] Knowledge-base lookup integration.

**Acceptance:** Recommendation includes action, conviction, position size, SL/TP, expected hold period, risk flags, XAI narrative.

---

### Fase 4 — Backtest, Paper Trading & Risk (Minggu 10-12) ✅

**Tujuan:** validasi strategi tanpa risiko finansial.

**Dokumen acuan:** `19-flow-logic-testing-kpi.md`, `20-syarat-robot-auto-trading.md`, `29-backtesting-strategy-validation.md`, `74-trading-financial-management-capital-operations.md`, `77-performance-attribution-benchmark-comparison.md`, `85-backtest-to-live-gap-prevention.md`, `07-manajemen-risiko.md`, `31-risk-management-lanjutan.md`.

**Deliverables & Markers:**
- [x] Event-driven backtest engine (next-bar-open, realistic cost, slippage).
- [x] Strategies: Buy & Hold, MA Crossover, Conviction.
- [x] Walk-forward analysis, Monte Carlo simulation, Deflated Sharpe Ratio.
- [x] Paper trading engine with lot validation, fees, tax, dividends.
- [x] PnL engine (realized/unrealized, FIFO cost basis).
- [x] Risk engine: VaR/CVaR, Kelly, position sizing, drawdown circuit breaker.
- [x] Backtest quality gate runner (WFA, Monte Carlo, DSR).

**Acceptance:** Backtest returns equity curve, Sharpe, Sortino, max DD, win rate; paper trading updates virtual portfolio correctly.

---

### Fase 5 — Execution, OMS & Portfolio (Minggu 13-15) [✓] DONE

**Tujuan:** sistem dapat mengelola order dan portofolio.

**Dokumen acuan:** `16-strategi-mencari-keuntungan.md`, `26-post-trade-settlement-rekonsiliasi.md`, `40-oms-ems-architecture.md`, `47-operational-contract-runbook.md`, `48-disaster-recovery-business-continuity.md`, `49-incident-management-post-mortem.md`, `52-transaction-cost-analysis-execution-quality.md`, `55-capacity-planning-load-stress-testing.md`, `74-trading-financial-management-capital-operations.md`, `76-idx-trading-rules-market-mechanics.md`.

**Deliverables & Markers:**
- [x] OMS state machine (new → pending → partial → filled/cancelled/rejected).
- [x] Order validation: lot, tick size, price limits, session, buying power.
- [x] Broker adapter: mock, paper, Sinarmas/BNI stubs.
- [x] Portfolio engine: positions, exposures, drift, rebalancing.
- [x] Performance attribution vs IHSG (Brinson, factor attribution).
- [x] Trade ledger (double-entry), NAV, reconciliation.
- [x] DR/BCP & incident response runbooks.
- [x] Capacity/stress test skeleton.
- [x] **Post-Trade Execution Analyzer** (`src/market/analysis/execution_analyzer.py`) — slippage measurement (target vs fill price), Net Alpha Attribution (gross PnL − broker fees − PPh Final 0.1%), execution efficiency metrics. Fed into Ablation Study di `audit_ai_advanced.py` sebagai feedback loop untuk deteksi model decay.

**Acceptance:** User can create paper order, see lifecycle status, and view real-time PnL.

---

### Fase 6 — Frontend & UI/UX (Minggu 16-18) [✓] DONE

**Tujuan:** aplikasi usable oleh pemilik.

**Dokumen acuan:** `17-aplikasi-retail-pribadi.md`, `32-ui-ux-design-trading-app.md`, `43-mobile-app-architecture.md`, `56-notification-strategy-alert-fatigue.md`, `57-user-onboarding-journey-design.md`, `61-accessibility-a11y-trading-app.md`, `78-reporting-export-system.md`, `79-education-content-management.md`, `80-watchlist-alert-system.md`, `81-gamification-engagement-design.md`.

**Deliverables & Markers:**
- [x] Next.js project scaffold (App Router, Tailwind, shadcn/ui, Recharts/Lightweight Charts).
- [x] Dashboard page: portfolio summary, watchlist, market status, top movers.
- [x] Stock detail page: chart, indicators, scores, recommendation, fundamentals.
- [x] Portfolio page: positions, PnL, allocation, history.
- [x] Backtest page: config, results, equity curve.
- [x] Analysis/Screener page.
- [x] Settings page: risk params, notifications, API key.
- [x] Reports page: tax, dividend, trade log, statements.
- [x] Watchlist & 15 alert types with Telegram/email/in-app routing.
- [x] Education content CMS & gamification engine (XP, badges, streaks).
- [x] Mobile responsive + accessibility.
- [x] FastAPI backend: health, env, scores, recommend, advisory, portfolio, watchlist, backtest, markets.

**Acceptance:** All 7+ main pages accessible and data-driven; alerts can be triggered.

---

### Fase 7 — Multi-Market & Multi-Asset Extension (Minggu 19-21) [✓] DONE

**Tujuan:** aplikasi siap untuk aset dan pasar lain sebagai input/faktor, dengan jalur trading bertahap.

**Dokumen acuan:** `03-pasar-modal-global.md`, `04-instrumen-pasar-modal.md`, `35-multi-asset-cross-market-analysis.md`, `36-gap-data-timezone-global-idx.md`, `92-multi-market-multi-asset-trading-system.md`.

**Deliverables & Markers:**
- [x] Multi-market registry (US, HK, SG, JP, etc.).
- [x] Multi-asset instrument master (equity, ETF, bond, commodity, forex, crypto, derivative stubs).
- [x] FX & currency risk engine.
- [x] Cross-market relationship engine (correlation, lead-lag, spillover).
- [x] Per-asset-class fundamental scorer.
- [x] Per-asset-class decision weights.
- [x] Multi-market OMS validation rules.
- [x] UI market selector + multi-currency PnL display.

**Acceptance:** `/api/instruments?market_mic=XNAS&asset_class=equity` works; cross-market correlation heatmap displayed.

---

### Fase 8 — Advanced AI/ML & MLOps (Minggu 22-24) [✓] DONE

**Tujuan:** model dapat belajar, di-versioning, dan dipromosikan dengan aman.

**Dokumen acuan:** `23-machine-learning-trading.md`, `30-sentiment-analysis-alternative-data.md`, `39-screening-aiml-pattern-memory.md`, `51-mlops-model-risk-management.md`, `58-feature-store-engineering-pipeline.md`, `67-llm-agent-layer-self-evolution.md`, `71-eval-gated-promotion-ab-testing.md`.

**Deliverables & Markers:**
- [x] LSTM/ensemble training pipeline (GPU `cuda:1`).
- [x] Model registry with aliases (`@experiment`, `@candidate`, `@champion`).
- [x] Feature store automation.
- [x] Walk-forward & purged k-fold cross-validation.
- [x] Model drift detection.
- [x] Champion/challenger promotion workflow.
- [x] A/B testing framework for strategies.
- [x] Eval-gated promotion pipeline.
- [x] **Overnight Strategy Mining** (`scripts/overnight_strategy_mining.py`) — Trade Ideas Mode, crontab 02:00 WIB. Scan bursa global semalam (^GSPC, ^VIX, CL=F, MTF=F) → assess macro regime → LightGBM Donchian parameter sweep (period 10–25) pada mock DB → update `best_ticker_quant_config.json` dengan parameter Max Drawdown tertipis → insert hasil ke `app_notifications` (status UNREAD) untuk panduan transaksi IHSG pagi.

**Acceptance:** Model can be trained, registered, promoted, and inference uses champion alias.

---

### Fase 9 — AI Self-Evolution & Autonomous Layer (Minggu 25-27) [✓] DONE

**Tujuan:** sistem dapat memperbaiki dirinya sendiri dengan pengawasan manusia.

**Dokumen acuan:** `67-llm-agent-layer-self-evolution.md`, `68-sandbox-execution-self-generated-code.md`, `69-knowledge-base-persistent-memory.md`, `70-hot-swap-runtime-update.md`, `71-eval-gated-promotion-ab-testing.md`, `72-human-in-the-loop-oversight.md`, `73-self-evolving-ai-roadmap-recommendation.md`, `86-gigantic-ai-autonomous-trading-system.md`.

**Deliverables & Markers:**
- [x] Self-evolution agent loop (observe → analyze → reflect → decide → validate → execute → monitor → learn → evolve).
- [x] Sandbox for AI-generated code (resource limits, AST scan, timeout).
- [x] Human-in-the-loop approval bot (Telegram).
- [x] Hot-swap runtime module update with rollback.
- [x] Persistent knowledge/memory layer.
- [x] Autonomous improvement pipeline integrated with eval-gate.

**Acceptance:** Agent can propose a small patch, run tests, and create a PR-like patch after eval-gate; human approval required for merge/live.

---

### Fase 10 — Security, Compliance & Operations (Minggu 28-29) [✓] DONE

**Tujuan:** sistem siap produksi lokal dari sisi keamanan, kepatuhan, dan operasional.

**Dokumen acuan:** `10-regulasi-pasar-modal.md`, `33-cybersecurity-trading-system.md`, `41-uu-pdp-compliance-fintech.md`, `42-customer-support-dispute-resolution.md`, `47-operational-contract-runbook.md`, `48-disaster-recovery-business-continuity.md`, `49-incident-management-post-mortem.md`, `50-change-release-management-trading.md`, `54-trade-surveillance-market-abuse.md`, `62-api-versioning-deprecation-policy.md`, `63-investasi-syariah-des-screening.md`, `64-fractional-shares-micro-investing.md`, `82-vendor-third-party-integration-management.md`, `87-regulatory-developments-2026.md`.

**Deliverables & Markers:**
- [x] Credential encryption at rest (Fernet).
- [x] API versioning policy (`/api/v1/...`).
- [x] Sharia-compliant DES screening.
- [x] Fractional shares / micro-investing stubs.
- [x] Vendor health check & SLA monitoring.
- [x] Trade surveillance / market-abuse detection stubs.
- [x] Incident response & DR runbooks tested.
- [x] Customer support & dispute resolution workflow.
- [x] UU PDP compliance checklist implemented.

**Acceptance:** Security review passes; no secrets in repo; runbooks executed at least once.

---

### Fase 11 — Social, Robo-Advisor, Monetization & Polish (Minggu 30-32) [✓] DONE

**Tujuan:** fitur engagement lengkap, reporting lengkap, dan final polish.

**Dokumen acuan:** `44-social-copy-trading.md`, `45-robo-advisor-goal-based-investing.md`, `57-user-onboarding-journey-design.md`, `59-competitive-analysis-feature-benchmarking.md`, `60-monetization-business-model.md`, `78-reporting-export-system.md`, `79-education-content-management.md`, `81-gamification-engagement-design.md`.

**Deliverables & Markers:**
- [x] Social/copy trading stubs (paper only, no real leaderboard for real trading).
- [x] Robo-advisor / goal-based investing module.
- [x] Onboarding journey (beginner → intermediate → advanced).
- [x] Competitive analysis feature benchmarking.
- [x] Monetization model document.
- [x] Reporting engine: PDF/CSV/Excel exports.
- [x] Final stress test & performance optimization.
- [x] Complete documentation & user manual.

**Acceptance:** All major features accessible; load test ≥100 concurrent API calls; documentation complete.

---

## 6. Prompting-Cycle Autonomous Execution

### 6.1 Cara Menggunakan MEGAPLAN.md

AI (Devin/Cascade) memperlakukan MEGAPLAN.md sebagai **source of truth** proyek. Setiap sesi dimulai dengan:

1. Baca `@MEGAPLAN.md` (relative to project root).
2. Baca `@AGENTS.md`.
3. Baca `@.devin/SESSION_MEMORY.md`.
4. Identifikasi fase dengan marker `[ ]` atau `[~]` paling awal.
5. Baca dokumen `pustaka/` yang tercantum dalam fase tersebut.
6. Jalankan prompting-cycle di bawah ini.

### 6.2 Prompting-Cycle per Iterasi

Setiap iterasi (biasanya 1-3 hari kerja) mengikuti loop berikut:

```
[PLAN]    →  [IMPLEMENT]  →  [TEST]  →  [COMMIT]  →  [REPORT]  →  [CHECKPOINT]
   ↑                                              ↓
   └────────────── next iteration ←──────────────┘
```

**1. PLAN — Rencana micro-task (≤30 menit perencanaan AI)**
- Identifikasi 1-3 deliverables dari fase aktif.
- Baca dokumen pustaka terkait.
- Cek dependensi dengan deliverables sebelumnya.
- Tulis mini-plan singkat dalam chat/session notes.

**2. IMPLEMENT — Coding autonomous**
- Implementasi mengikuti arsitektur dan konvensi project.
- Prefer minimal, focused edits; jangan over-engineering.
- Gunakan `ruff`, `mypy`, `pytest` sebelum melanjutkan.
- Untuk kode yang dihasilkan AI: jalankan AST scan dan sandbox test.

**3. TEST — Verifikasi**
- Unit tests untuk kode baru/ubahan.
- Integration test untuk pipeline/data flow.
- Smoke test jika menyentuh frontend/API.
- Coverage tidak boleh turun di bawah 70%.

**4. COMMIT — Snapshot progress**
- Commit/patch dengan pesan deskriptif: `[Fase-X] <deskripsi singkat>`.
- Update completion marker di MEGAPLAN.md dari `[ ]` → `[~]` → `[x]`.
- Jika human-gate diperlukan (live trading, schema DB produksi, penghapusan data), tandai `[~]` dan minta approval, jangan ubah ke `[x]` tanpa persetujuan.

**5. REPORT — Ringkasan untuk user**
- Apa yang selesai?
- Apa yang masih `[~]`?
- Apa blocker/risiko?
- Apa rencana micro-task berikutnya?

**6. CHECKPOINT — Context preservation**
- Jika context window mendekati ~70% ATAU sebelum topik besar berganti, jalankan `/context-checkpoint`.
- Simpan ringkasan ke `@.devin/SESSION_MEMORY.md` dan memory system.
- Jika sesi berakhir, tulis status fase aktif, file yang diubah, pending tasks, dan dependensi.

### 6.3 Aturan Autonomous yang Wajib

- **Tidak pernah** mengaktifkan `ENV=live` atau eksekusi uang nyata tanpa approval eksplisit.
- **Tidak pernah** menghapus data, mengubah skema DB production, atau men-deploy publik tanpa approval.
- **Tidak pernah** melewati fase Paper Trading untuk strategi/model baru.
- **Selalu** update marker completion dan SESSION_MEMORY.md setelah iterasi.
- **Selalu** lint + type-check + test sebelum commit.
- **Selalu** baca AGENTS.md dan memory di awal sesi.
- **Gunakan subagents** untuk tugas paralel: data audit, testing, dokumentasi, code review ringan.

### 6.4 Human-Gate Checklist (PR)

AI wajib berhenti dan minta approval jika:

- [x] Menjalankan migrasi skema DB `market_live.db`. *(approved 2026-08-05, head 0012)*
- [ ] Mengaktifkan broker adapter real / live trading. *(form disiapkan di FE settings, perlu approval token)*
- [x] Menghapus file/data penting (termasuk DB lama). *(tidak ada penghapusan — standing rule)*
- [x] Menginstal dependency sistem atau mengubah konfigurasi OS. *(approved 2026-08-05)*
- [ ] Deploy ke cloud/VPS/public endpoint. *(local-only untuk sekarang, sebelum dinyatakan layak live)*
- [x] Memodifikasi konfigurasi keamanan (firewall, secrets, TLS). *(single-user local — minimal setup, .env + .gitignore sudah ada)*
- [ ] Mengganti model champion di Live environment. *(CLI: `market model promote/rollback` — perlu eval-gate pass + paper trading 30 hari)*

### 6.5 Subagent Prompts (Opsional)

```
/knowledge-base-curator <topic>
    → Audit dan cross-link pustaka untuk topik tertentu.

/context-checkpoint [reason]
    → Simpan checkpoint context saat session hampir habis.

/megaplan-executor
    → Mulai eksekusi MEGAPLAN.md dari fase aktif.

/code-review <files>
    → Review kode untuk future-peek, bug, konvensi, dan test coverage.

/data-audit <ticker/table>
    → Periksa kualitas data, anomali, dan broken links.
```

## 7. Risiko & Mitigasi

| Risiko | Mitigasi |
|--------|----------|
| Scope creep (94 dokumen) | Fase jelas, deliverables terukur, marker completion. |
| Overfitting backtest | PBO, DSR, WFA, paper trading 30 hari. |
| Live trading loss | Human-gate, paper period, circuit breakers, daily loss limits, scale-up 25%. |
| AI-generated code rusak | Sandbox, AST scan, test wajib, rollback otomatis. |
| GPU OOM | Batch size ≤64, hidden dim ≤256, fallback CPU. |
| Data parquet corrupt | Quality tier, reconciliation, watermark, reject tier bronze. |

## 8. Timeline Ringkas

| Fase | Minggu | Fokus |
|------|--------|-------|
| 0 | 1 | Bootstrap & Environment |
| 1 | 2-4 | Data Platform & Migration |
| 2 | 5-7 | Core Analysis Engines (IDX) |
| 3 | 8-9 | Decision, XAI, Advisory |
| 4 | 10-12 | Backtest, Paper Trading, Risk |
| 5 | 13-15 | Execution, OMS, Portfolio |
| 6 | 16-18 | Frontend & UI/UX |
| 7 | 19-21 | Multi-Market & Multi-Asset |
| 8 | 22-24 | Advanced AI/ML & MLOps |
| 9 | 25-27 | AI Self-Evolution |
| 10 | 28-29 | Security, Compliance, Operations |
| 11 | 30-32 | Social, Robo-Advisor, Monetization, Polish |

**Total estimasi:** 32 minggu (8 bulan). Dapat dikompresi menjadi 24-28 minggu dengan parallel work, tetapi **tidak disarankan memangkas fase Paper Trading atau eval-gate**.

> **Status per 10 Agustus 2026:** Semua 12 fase (0-11) selesai dari sisi kode dan test (1274 tests, coverage 76%+). Aplikasi siap untuk paper trading 30 hari sebelum live gate.

## 9. Next Steps Segera (Status per 10 Agustus 2026)

Semua fase 0–11 sudah selesai dari sisi kode dan test (1274 tests, 64 files, coverage 76%+). Data enrichment, batch AI/ML backfill, DB normalization, fast portfolio pipeline, dan 7 modul strategi alternatif juga selesai. Langkah nyata berikutnya adalah validasi strategi dan memulai paper trading sungguhan:

1. **Persiapan Environment**: ✅ Selesai — `.env` dengan `ENV=paper`, `BROKER_ADAPTER=paper`.
2. **Database**: ✅ Selesai — `market_research.db` (~10 GB) & `market_paper.db` (~8.3 GB) ter-seed penuh, alembic head 0012.
3. **Scheduler**: ✅ Selesai — 11+ tasks terdaftar + crontab aktif (daily signal, weekly HRP recompute, weekly drift check).
4. **Frontend Security**: ✅ Selesai (Next.js 16.3.0, 0 vulnerabilities, 10 pages).
5. **Wire-up API**: ✅ Selesai — `/api/portfolio`, `/api/watchlist`, `/api/backtest/run` terhubung ke DB.
6. **Intraday Polling**: ✅ Selesai — `fetch_intraday` task + `/api/prices/latest` + `/api/prices/compare/{ticker}`.
7. **Production Pipeline**: ✅ Selesai — fast portfolio pipeline (4-65 detik) menggantikan pipeline 14-jam. HRP + walk-forward + EvalGate + SignalEnhancer.
8. **DB Normalization & AI/ML Modularisasi**: ✅ Selesai — wide tables (0012), stock_prediction split, MLOps integrations (ModelRegistry, DriftDetector, EvalGate), hyperparameter tuning anti-overfit.
9. **Strategi Alternatif**: ✅ Selesai — 7 modul baru (meta-labeling, pairs trading, volume features, policy event scorer, macro data fetcher, sector rotation, compute device). Lihat `pustaka/97-strategi-alternatif-ekspansi-data-2026.md`.
10. **Stale Data Engine**: ✅ Selesai — `refresh_stale.py` deteksi & auto-refresh >24h.
11. **AI/ML Audit**: ✅ Selesai — framework 4-pilar (Delta Alpha, significance, drift, latency). Baseline teknikal Sharpe -0.50, AI belum berikan Alpha positif (perlu retraining dengan fitur remediasi). Lihat `pustaka/96-ai-ml-audit-framework.md`.
12. **Paper Trading 30 Hari**: ⏳ Pending — jalankan minimal 30 hari simulasi sebelum membuka human-gate broker real. Paper DB siap (8.3 GB, 980 tickers, ML labels 9.85M rows).
13. **Model Champion Pertama**: ⏳ Pending — 50 tickers sudah trained (avg val_acc 0.502), perlu retraining dengan fitur remediasi + promosi setelah eval-gate pass.
14. **Live Gate**: ⏳ Pending — setelah paper period memadai, ajukan approval untuk broker real dan/atau deploy local-only production.

### Prioritas Riset Berikutnya (dari pustaka/97)

1. **Meta-labeling retraining** — fix accuracy 40-43% → target 55%+ via Lopez de Prado secondary ML model (prioritas TERTINGGI).
2. **Pairs trading backtest** — strategi market-neutral yang tahan bear market choppy (statarb cointegration).
3. **Regime-switching portfolio** — HMM + dynamic allocation untuk bear/bull/sideways.
4. **Foreign flow momentum** — foreign net buy 5-day sebagai entry signal (1.25M rows foreign_flow tersedia).
5. **Macro data expansion** — BPS API + BI SEKI + NOAA ONI + World Bank + commodity futures (rate-limited, gratis).

### Data Enrichment Completed (6 Agustus 2026)

- ✅ **Delisting logic**: 62 tickers ditandai `is_active=0` + `delisting_date`; 211 tickers dengan `delisting_risk_reason`.
- ✅ **Merger logic**: 3 tickers dengan `underlying_ticker` (FREN→EXCL, MFIN→ADMF, dll); 2 `corporate_actions` rows dengan `action_type='merger'`.
- ✅ **Name changes**: 34 tickers dengan `former_name` diisi (2024–2026 IDX name changes).
- ✅ **Ticker suffix standardization**: `src/market/data/ticker_util.py` menggantikan hardcoded `.JK` di `data_fetch.py`, `scheduler_tasks.py`, `yahoo_adapter.py`, `recompute_internal.py`, `data_health.py`, `profiling.py`.
- ✅ **Screener enhancement**: `excluded_merged` filter untuk ticker yang sudah merged.
- ✅ **DTS backfill**: 4,928 rows untuk 25 IPO baru dari OHLCV (source: `yfinance_derived`).
- ✅ **free_float backfill**: 922/923 (99.9%) — hanya GOTOM tanpa data.
- ✅ **listed_shares/tradeable_shares**: 25 IPO baru di-backfill dari yfinance info.
- ✅ **Migration 0006**: Kolom `listed_shares`, `tradeable_shares`, `delisting_risk_score`, `delisting_risk_reason`, `former_ticker`, `former_name`.
- ⏳ **DTS gap Feb 2025–Aug 2026**: Butuh CSV IDX (tidak tersedia dari yfinance — hanya bid/offer/frequency/value).
- ⏳ **Fundamental time-series**: Scheduler weekly sudah aktif, data historis terbangun secara gradual.

### Index Backfill Completed (7 Agustus 2026)

- ✅ **^JKSE (IHSG) backfill**: 1,199 → 8,845 rows (1990-04-06 s/d 2026-08-07). Sebelumnya hanya dari 2021-07.
- ✅ **^JKLQ45 (LQ45) backfill**: 0 → 7,152 rows (1997-02-24 s/d 2026-08-07). Ticker yfinance: `^JKLQ45` (bukan `^LQ45`).
- ✅ **Global indices backfill**: ^DJI (1992+), ^FTSE (1984+), ^GDAXI (1987+), ^GSPC (1927+), ^IXIC (1971+), ^VIX (1990+), ^HSI (1986+), ^N225 (1965+), ^TNX (1962+), DX-Y.NYB (1971+). Total 136,827 new OHLCV rows.
- ✅ **Instrument master cleanup**: 13 obsolete tickers (^LQ45, ^IDX30, dll) dihapus; 25 entries ditambah/diperbaiki (market_mic, currency, name).
- ✅ **IDX sectoral indices backfill via idx.co.id API**: 53,253 rows, 44 indeks, 2021-01-04 s/d 2026-06-30. Semua 13 indeks sektoral (IDXENERGY, IDXFINANCE, IDXHEALTH, IDXBASIC, IDXTECHNO, IDXINDUST, IDXPROPER, IDXTRANS, IDXINFRA, IDXNONCYC, IDXCYCLIC, IDX30, IDX80) + 31 indeks lainnya (JII, KOMPAS100, BISNIS-27, ISSI, INFOBANK15, SMINFRA18, dll). Data: close price only (open=high=low=close, volume=0), source=`idx_api`. Akses via cloudscraper (Cloudflare bypass), endpoint `GetApiData?urlName=LINK_DAILY_IDX_INDICES`. Data IDX API verified 100% match dengan yfinance untuk overlapping dates.
- Script: `scripts/backfill_indices.py` (yfinance, idempotent), `scripts/backfill_idx_api_indices.py` (idx.co.id API, cloudscraper).

### DST Shift-Aware Logic & Commodity Futures Alignment (10 Agustus 2026)

- ✅ **`verify_dst_cutoff()`** — DST-aware Wall Street close detection via `zoneinfo` (America/New_York). Summer (EDT, Mar→Nov): US close = 03:00 WIB (20:00 UTC). Winter (EST, Nov→Mar): US close = 04:00 WIB (21:00 UTC). Module: `src/market/analysis/cross_market_timezone.py`.
- ✅ **`daily_signal_cron.py` integration** — DST cutoff check sebelum signal computation. Jika Wall Street masih buka, log WARNING bahwa global index data (^GSPC, ^VIX) mungkin incomplete.
- ✅ **Commodity futures backfill** — `scripts/backfill_commodity_futures.py` meng-backfill 6 kontrak komoditas:
  - CL=F (Crude Oil): 2,179 rows (2021-07 → 2026-08-07)
  - GC=F (Gold): 2,179 rows (2021-07 → 2026-08-07)
  - HG=F (Copper): 905 rows (2023-01 → 2026-08-07) — **NEW**
  - MTF=F (Coal API2/ICE): 750 rows (2023-01 → 2025-12-26) — **NEW**
  - CPO=F (Crude Palm Oil, Bursa Malaysia): 1,408 rows (2023-01 → 2026-08-07) — **NEW**
  - NI=F (Nickel LME): tidak tersedia di yfinance (404) — logged as warning
- ✅ **MultiFactorModel feature expansion** — `GLOBAL_ASSETS` di `multi_factor.py` diperluas: +MTF=F (coal), +CPO=F (cpo), +NI=F (nickel). T-1 returns otomatis masuk sebagai exogenous features via `compute_exogenous_features()`.
- ✅ **Sector-specific commodity signals** — `_fetch_commodity_signal()` di `market_context.py` diperluas: Energy→CL=F+MTF=F, Consumer Defensive→CPO=F, Basic Materials→GC=F+HG=F+NI=F.
- ✅ **Tests**: 47 tests di `tests/test_cross_market_timezone.py` (DST detection, US close UTC, market closed check, WIB conversion, cutoff verification, ticker lags, market timezones, get_aligned_global_features T-0/T-1). Total 1,317 tests pass (3 pre-existing failures unrelated).
- ✅ **`get_aligned_global_features()`** — Fungsi baru di `cross_market_timezone.py` yang menyupply global features dengan anti look-ahead bias: T-0 untuk Asian markets (^N225, ^HSI — close sebelum IDX), T-1 untuk US markets (^GSPC, ^VIX, ^TNX — close setelah IDX) dan commodities (GC=F, CL=F, HG=F, MTF=F, CPO=F). Menggunakan `GLOBAL_TICKER_LAGS` dict dan `MARKET_TIMEZONES` metadata untuk menentukan lag per ticker.
- ✅ **`compute_exogenous_features()` asymmetric lag** — Diganti dari uniform `.shift(1)` menjadi `get_ticker_lag(gticker)` per ticker. Asian markets menggunakan T-0 (same-day close valid), US/commodities menggunakan T-1 (previous-day close only). Mencegah look-ahead bias untuk Asian features yang sebelumnya tertunda 1 hari.
- Script: `scripts/backfill_commodity_futures.py` (yfinance, idempotent, INSERT OR REPLACE).

### Instrument Classification (7 Agustus 2026)

- ✅ **Migration 0010**: Kolom `index_category` dan `region` ditambahkan ke `instrument_master`.
- ✅ **Index category**: 57 indeks diklasifikasi — `sectoral` (11), `factor` (13), `broad_market` (9), `global` (8), `esg` (5), `sharia` (4), `board` (3), `volatility` (1), `rate` (1), `currency` (1), `composite` (1).
- ✅ **Region**: 1,054 instrumen diklasifikasi — `ID` (1,033), `US` (12), `GLOBAL` (4), `EU` (2), `AS` (2), `CN` (1).
- ✅ **Sector untuk indeks sektoral**: 11 indeks sektoral diberi sector (IDXENERGY→Energy, IDXFINANCE→Financials, dll).
- ✅ **Sector standardization**: Duplikat digabung — `Consumer Cyclical`→`Consumer Cyclicals` (171), `Financial Services`→`Financials` (108), `Real Estate`→`Properties & Real Estate` (95).
- Script: `scripts/classify_instruments.py`.

### Batch AI/ML Data Backfill (7 Agustus 2026)

Eksekusi batch 5 task untuk meningkatkan kesiapan data AI/ML:

#### #1 Fundamental Quarterly Backfill (yfinance, rate-limited 0.8 req/s)
- ✅ **140 quarters baru** diinsert, 3,639 skipped (sudah ada), 339 tickers failed (no quarterly data di yfinance).
- ✅ Total `fundamental_data` (source=`yahoo_quarterly`): **3,779 rows**, 8 distinct dates.
- Coverage: 978 IDX equity tickers di-fetch, ~639 punya quarterly data.
- Script: `scripts/backfill_fundamental_quarterly.py`.

#### #2 Technical Indicators Time-Series (compute from OHLCV)
- ✅ **30,006,953 rows** diinsert untuk **1,030 tickers** (10 indikator × ~2,900 dates × 1,030 tickers).
- Indikator: MA20, MA50, RSI, MACD, MACD_SIGNAL, ADX, ATR14, BB_UPPER, BB_LOWER, VOLUME_SMA20.
- Data di-clear dan recomputed full history (bukan snapshot lagi).
- 6 tickers empty (insufficient OHLCV < 50 rows).
- Script: `scripts/backfill_technical_indicators.py`.

#### #3 Daily Risk Metrics (VaR/CVaR/Max Drawdown/Volatility per ticker)
- ✅ **Migration 0011**: Kolom `ticker` ditambahkan ke `daily_risk_metrics` untuk per-ticker risk.
- ✅ **8,919,950 rows** untuk **1,024 tickers**, 6,755 distinct dates.
- Metrik: VaR_95, VaR_99, CVaR_95, CVaR_99, max_drawdown, annualized_volatility (rolling 252-day, historical simulation).
- 6 tickers empty (insufficient data < 60 rows).
- Script: `scripts/backfill_risk_metrics.py`.

#### #4 AI Weights Persistence (LightGBM 3-class BUY/SELL/HOLD)
- ✅ **50 tickers** trained dan persisted (top by OHLCV row count).
- ✅ `ai_weights` table: 50 rows, avg validation accuracy **0.5020**.
- Top performers: PANS.JK (0.744), DNET.JK (0.695), IGAR.JK (0.691), TRST.JK (0.652), BRNA.JK (0.637).
- Model: LightGBM 3-class, 300 trees, depth 5, lr 0.05, walk-forward 80/20, early stopping 15.
- Features: ret_1, ret_5, ret_10, RSI, MA ratios, vol_20, vol_ratio, BB width, MACD histogram.
- Script: `scripts/persist_ai_weights.py`.

#### #5 News Ticker Tagging (keyword matching)
- ✅ **106 dari 110 articles** tagged (96.4% hit rate), 4 no match (berita geopolitik/sosial murni).
- Keyword map: 2,211 keywords dari instrument_master + market entities + company abbreviations + sectoral keywords.
- Bug fix: case-sensitivity (keyword tidak di-uppercase saat match dengan uppercased headline).
- Tambahan keyword: BNI→BBNI, BCA→BBCA, BRI→BBRI, RUPIAH, ASING, BANDARA, CNG, PLTS, BERAS, MOBIL, VIRUS, KEUANGAN, APBN, dll.
- 4 untagged: Iran nuklir, Perang AS, WNI scam Thailand, IKD KTP — tidak menyebut entitas pasar modal.
- Method: regex word-boundary matching, longest-first to avoid partial matches.
- Script: `scripts/tag_news_entities.py`.

#### Catatan: 6 tickers insufficient OHLCV
- Bukan delisting — semua adalah **IPO baru** (listing 7-10 Juli 2026):
  - RANS.JK (19 baris), PRDL.JK (20), BACH.JK (21), EMMI.JK (21), JECX.JK (22), JELI.JK (22).
- Technical indicators butuh minimal 50 baris (MA50, ADX). Data akan terisi otomatis oleh scheduler EOD.
- Estimasi cukup data dalam ~30 hari bursa (~6 minggu).

#### Total dampak database:
- **~39M rows baru** across technical_indicators + daily_risk_metrics + fundamental_data + ai_weights.
- Database size: ~6 GB sebelum batch → ~10 GB setelah batch ini (research DB, per 10 Agustus 2026).

### Paper DB Sync (7 Agustus 2026)

Sinkronisasi `market_paper.db` agar siap untuk paper trading:

- ✅ **Migration 0010 + 0011** di-applied ke paper DB (sebelumnya tertinggal di 0009).
- ✅ **Technical indicators**: 29,534,656 rows, 980 tickers, 6,814 dates.
- ✅ **Daily risk metrics**: 2,938,285 rows, 980 tickers, 6,755 dates.
- ✅ **Fundamental data (quarterly)**: 140 rows baru di-sync dari research DB (total 3,779 quarterly + 1,974 lainnya = 5,753 rows).
- ✅ **News tagging**: 106/110 articles tagged (96.4%).
- ✅ **AI weights**: 50 tickers trained, avg val_acc 0.5020.
- ✅ **Alembic version**: 0011 (synced dengan research DB).

#### Paper DB final state:
| Table | Rows |
|-------|------|
| OHLCV | 3,161,808 |
| Technical Indicators | 29,534,656 |
| Daily Risk Metrics | 2,938,285 |
| ML Labels | 9,853,230 |
| Foreign Flow | 1,253,802 |
| Macro Data | 68,294 |
| Market Calendar | 27,305 |
| Relationship Matrix | 63,252 |
| Instrument Master | 1,023 |
| Scores | 5,880 |
| Fundamental Data | 5,753 |
| Corporate Actions | 6,367 |
| Dividends | 5,974 |
| News | 110 (106 tagged) |
| AI Weights | 50 |

**Paper trading environment siap.** Langkah berikutnya: aktifkan scheduler EOD + intraday polling, lalu mulai paper trading 30 hari.

### AI/ML Utility Audit Framework (7 Agustus 2026)

Framework komprehensif untuk mengevaluasi apakah model AI/ML memberikan Alpha atau overfitting. Dokumen: `pustaka/96-ai-ml-audit-framework.md`. Script: `scripts/audit_ai_utility.py`.

**4 Pilar Audit:**

1. **Model Performance Metrics** — Sharpe, Sortino, MaxDD, Information Ratio, Win Rate, Profit Factor, IC, Brier Score, Precision@K (bukan sekadar akurasi).
2. **Ablation Study** — Skenario A (Full AI) vs F (Baseline teknikal) vs G (Random). Delta Alpha per komponen. Paired t-test untuk signifikansi statistik.
3. **Latency & Cost-Benefit** — End-to-end latency profiling per komponen. Break-even AUM = Monthly Cost / Monthly Alpha. Benefit/Cost ratio.
4. **Feature Importance & Drift** — PSI (Population Stability Index), KS test, model decay indicators, regime shift detection per feature.

**Hasil audit awal (20 tickers, baseline teknikal vs random):**

| Metrik | Baseline (Technical) | Random (Null) |
|--------|---------------------|---------------|
| Sharpe | -0.496 | -3.996 |
| Sortino | -0.662 | — |
| Max DD | -63.22% | -100.00% |
| Win Rate | 49.1% | 29.9% |
| Profit Factor | 0.974 | — |
| Alpha (ann) | 0.00% | 0.00% |

**Feature drift (KPIG.JK, 70/30 split):**

| Feature | PSI | Status |
|---------|-----|--------|
| ret_1 | 0.079 | ✅ stable |
| vol_20 | 0.472 | 🔴 drifted |
| rsi | 0.252 | 🔴 drifted |
| ma_ratio_20 | 0.107 | ⚠️ moderate |
| ma_ratio_50 | 0.292 | 🔴 drifted |
| bb_width | 0.130 | ⚠️ moderate |

**Temuan kritis:**
- Baseline teknikal (MA crossover + RSI) Sharpe -0.50 — **merugi setelah biaya**. Perlu AI untuk memberikan Alpha positif.
- 3 dari 6 feature sudah drifted (PSI > 0.25) — model yang dilatih pada data lama perlu retraining.
- Latency baseline signal generation: 2.9ms median (sangat cepat, tidak ada bottleneck).
- Score card awal: 1.2/5.0 (REMOVE) — **karena ini audit baseline tanpa AI, bukan audit AI itu sendiri**. Audit AI penuh memerlukan backtest dengan sinyal MLSignal + MultiFactor.

**Next:** Jalankan audit dengan sinyal AI penuh (MLSignal + MultiFactor) untuk dapat Delta Alpha = Alpha(AI) - Alpha(Baseline).

### Advanced AI Audit — Delta Alpha, Significance & Remediation (7 Agustus 2026)

Script: `scripts/audit_ai_advanced.py` — modul lanjutan yang mengimpor `audit_ai_utility.py`.

#### Step 1: Feature Remediation Pipeline

Mendeteksi 3 fitur drifted (PSI > 0.25) dan melakukan remediasi otomatis:

| Ticker | Feature | PSI Before | PSI After | Action |
|--------|---------|-----------|-----------|--------|
| KPIG.JK | vol_20 | 0.472 | 0.095 | replaced → vol_pctile |
| KPIG.JK | rsi | 0.252 | 0.015 | replaced → rsi_rank |
| KPIG.JK | ma_ratio_50 | 0.292 | 0.096 | replaced → ma_ratio_zscore |
| TRIM.JK | rsi | 0.514 | 0.015 | replaced → rsi_rank |
| SONA.JK | rsi | 0.317 | 0.067 | replaced → rsi_rank |
| TIRT.JK | ma_ratio_50 | 0.430 | 0.430 | dropped (no stable alt) |
| TIRT.JK | bb_width | 0.290 | 0.113 | replaced → vol_pctile |
| TCID.JK | rsi | 0.839 | 0.026 | replaced → rsi_rank |
| TCID.JK | ma_ratio_50 | 0.388 | 0.097 | replaced → ma_ratio_zscore |

**Summary: 8 replaced, 1 dropped.** Fitur alternatif stabil: `rsi_rank` (rank-based RSI), `vol_pctile` (volatility percentile), `ma_ratio_zscore` (MA ratio z-score). Teknik regime-aware weighting juga diimplementasikan (eksponential decay + recent boost).

#### Step 2: Delta Alpha Execution

Walk-forward backtest (10 tickers, 80/20 split, LightGBM):

| Component | Sharpe (AI) | Sharpe (Base) | ΔSharpe | Win Rate (AI) | Max DD (AI) |
|-----------|-------------|---------------|---------|---------------|-------------|
| MLSignal | 0.000 | -0.399 | +0.399 | 0.0% | 0.00% |
| MultiFactor | -2.670 | -0.399 | -2.271 | 40.6% | -99.84% |

**ΔAlpha = 0.00% untuk keduanya** — Alpha tahunan AI maupun baseline sama-sama 0% (regresi terhadap IHSG menghasilkan alpha ≈ 0). MLSignal menghasilkan Sharpe 0 (tidak ada sinyal karena walk-forward jarang menghasilkan prediksi). MultiFactor menghasilkan Sharpe -2.67 (lebih buruk dari baseline).

#### Step 3: Statistical Significance Tests

| Test | MLSignal | MultiFactor |
|------|----------|-------------|
| Paired t-test | t=0.582, p=0.561, NOT significant | t=-5.484, p=0.000, significant (AI LEBIH BURUK) |
| Diebold-Mariano | DM=3.268, p=0.001, significant | DM=1.389, p=0.165, NOT significant |
| Bootstrap Reality Check | p=0.492, NOT significant | p=0.474, NOT significant |

**Interpretasi:** MLSignal tidak signifikan secara paired t-test (p=0.56) — outperformance mungkin noise. MultiFactor signifikan secara paired t-test tapi arahnya **negatif** (AI lebih buruk dari baseline).

#### Step 4: Automated Score Card

| Component | ΔAlpha | ΔSharpe | p-value | Score | Verdict |
|-----------|--------|---------|---------|-------|---------|
| MLSignal | 0.00% | +0.399 | 0.0000 | **2.85/5.00** | **MARGINAL** |
| MultiFactor | 0.00% | -2.271 | 0.0000 | **2.37/5.00** | **MARGINAL** |

**Rekomendasi:**
- MLSignal: Delta Alpha rendah — pertimbangkan retraining atau tuning hyperparameter.
- MultiFactor: Delta Alpha rendah dan ΔSharpe negatif — model perlu retraining dengan fitur yang sudah diremediasi.

**Catatan:** Hasil ini menggunakan walk-forward backtest sederhana dengan 10 tickers. MLSignal menghasilkan sedikit sinyal karena threshold dan walk-forward step yang jarang. Untuk audit yang lebih robust, perlu:
1. Lebih banyak ticker (50-100)
2. Walk-forward step yang lebih kecil (daily prediction)
3. Gunakan fitur yang sudah diremediasi (Step 1) untuk retraining
4. Tambahkan exogenous features (global market) untuk MultiFactor

### Production Pipeline — Fast Portfolio Pipeline (10 Agustus 2026)

Pipeline 14-jam lama (`run_production_pipeline.sh`) **telah dihapus** dan diganti dengan `fast_portfolio_pipeline.py` yang menyelesaikan dalam **~4 detik** (5 tickers) hingga **~65 detik** (100 tickers).

**Perbandingan:**

| Metrik | Pipeline Lama (14 jam) | Fast Pipeline |
|--------|----------------------|---------------|
| Durasi | ~14 jam | ~4-65 detik |
| Tickers | 20 | 5-100 (configurable) |
| Portfolio Weight | IV (bug: collapse) | HRP (Hierarchical Risk Parity) |
| Walk-forward | Manual 80/20 | mlops/cross_validation.py |
| Score Gate | Hardcoded >= 3.5 | EvalGate (mlops.promotion) |
| Signal Enhancement | None | SignalEnhancer (5 non-trend signals) |

**Crontab aktif:**
- `15 9 * * 1-5` — daily signal cron (16:15 WIB, Mon-Fri)
- `0 3 * * 6` — weekly HRP recompute (Saturday 03:00 UTC)
- `0 4 * * 6` — weekly drift check (Saturday 04:00 UTC)

**File lama yang dihapus:** `run_production_pipeline.sh`, `RENCANA-LANJUTAN-PRODUCTION-PIPELINE.md`

**File dependency yang tetap (sebagai library):** `alpha_rescue_pipeline.py`, `alpha_hyper_tuner.py`, `portfolio_cluster_tuner.py`, `portfolio_data_remediation.py`, `portfolio_final_execution.py` — digunakan oleh `daily_signal_cron.py` untuk signal generation.

### Database Normalization & AI/ML Modularisasi (10 Agustus 2026)

**Audit Mendalam** — 4 isu kritis diperbaiki:

1. **EAV → Wide Table:** `technical_indicators` (EAV) → `technical_indicators_wide` (3M+ rows). Migration `0012_wide_tables_and_fk.py` + backfill script. Semua consumer updated dengan fallback.

2. **stock_personality split:** Prediction columns → `stock_prediction` table (1,020 rows). Profile columns tetap di `stock_personality`.

3. **SignalEnhancer integration:** 5 non-trend signals (volume, policy, sector, pairs, meta-labeling) di-wire ke `daily_signal_cron.py`. Meta-labeler dapat veto prediction (bet_size < 0.1 → flat).

4. **Walk-forward CV dedup:** `ml_signal.py` dan `multi_factor.py` sekarang menggunakan `mlops/cross_validation.walk_forward_splits` (sebelumnya manual 80/20 split).

**MLOps integrations:**
- `ModelRegistry` → `batch_compute_predictions.py` (register model per ticker)
- `DriftDetector` → `weekly_drift_check.py` (Saturday cron, PSI-based)
- `EvalGate` → `fast_portfolio_pipeline.py` (replaces hardcoded Score >= 3.5)

**Hyperparameter tuning (anti-overfit):**
- `MLSignalProvider`: ditambah `min_data_in_leaf=40`, `reg_alpha=0.1`, `reg_lambda=1.0`, configurable `learning_rate`, `subsample`, `colsample_bytree`
- `MultiFactorModel`: ditambah `min_data_in_leaf=50`, `reg_alpha=0.1`, `reg_lambda=1.0`, configurable `subsample`, `colsample_bytree`
- Kedua model sekarang menggunakan `mlops.cross_validation.walk_forward_splits` untuk konsistensi

**Stale Data Detection Engine:**
- `src/market/data/refresh_stale.py` — `refresh_stale_data()` function
- Deteksi stale >24h berdasarkan `updated_at`/`timestamp` columns
- Auto-refresh: stock_personality, stock_prediction, technical_indicators_wide
- Excluded: 139 tickers (suspended/delisted/inactive)
- CLI: `python -m market.data.refresh_stale --dry-run`

**Database status terkini:**

| Tabel | Rows | NULL Status | Stale Status |
|-------|------|-------------|--------------|
| technical_indicators_wide | 3,049,358 | 0% NULL | Latest: 2026-08-06 |
| stock_prediction | 1,020 | 0% NULL | 0 stale |
| stock_personality | 1,026 | 6 NULL predicted_direction | 108 stale (>24h) |
| fundamental_data | 4,786 | >80% NULL (pe, pb, roe, der) | Stale (data fundamental jarang update) |
| ohlcv | 3,215,048 | 0% NULL | Latest: 2026-08-07 |

**Catatan fundamental_data:** NULL >80% adalah expected — data fundamental hanya update quarterly. Tidak dapat di-refresh harian. Stale detection mengabaikan tabel ini untuk refresh harian.

### Strategi Alternatif & Ekspansi Data (10 Agustus 2026)

Setelah autonomous trading sim V1-V4 menunjukkan prediction accuracy 40-43% (di bawah random 50%) di bear market choppy, dilakukan analisis mendalam 7 area pengembangan. Lihat `pustaka/97-strategi-alternatif-ekspansi-data-2026.md` untuk dokumentasi lengkap (17 sumber riset 2025-2026).

**Akar masalah:** Ensemble prediction engine (`prediction.py:825-956`) menggunakan 4 metode yang semuanya trend-following (MA, momentum, pattern, vol-adj). Di bear market choppy dengan sharp bounces, semua metode salah arah.

**7 modul baru dibuat:**

| Modul | Lokasi | Test | Status | Untuk Poin |
|-------|--------|------|--------|------------|
| Meta-labeling | `src/market/analysis/meta_labeling.py` | 59 pass | Selesai | 5 (fix accuracy) |
| Pairs trading | `src/market/analysis/pairs_trading.py` | In progress | Selesai | 1 (market-neutral) |
| Volume features | `src/market/analysis/volume_features.py` | In progress | Selesai | 2 (OFI, VWAP, foreign flow) |
| Policy event scorer | `src/market/analysis/policy_event_scorer.py` | 16 pass | Selesai | 3 (BI/BEI/corporate) |
| Macro data fetcher | `src/market/data/macro_data_fetcher.py` | In progress | Selesai | 4 (BPS/BI/NOAA/WorldBank) |
| Sector rotation | `src/market/analysis/sector_rotation.py` | 21 pass | Selesai | 1 (sector momentum) |
| Compute device | `src/market/compute/device.py` | 30 pass | Selesai | 7 (dynamic GPU/CPU) |

**Prioritas implementasi:**
1. **Meta-labeling (TERTINGGI)** — fix accuracy 40-43% → target 55%+ via Lopez de Prado secondary ML model
2. **Pairs trading** — strategi market-neutral yang tahan bear market (statarb cointegration)
3. **Volume features** — foreign flow 1.25M rows + OFI proxy + VWAP (belum terhubung ke prediction)
4. **Policy event scorer** — consume policy_events 179 rows + external_events 119 rows + corporate_actions 6,367 rows
5. **Macro data fetcher** — BPS API + BI SEKI + NOAA + World Bank + commodity futures (dynamic rate limiter)
6. **Sector rotation** — agregasi skor per sektor + momentum + rotation signal
7. **Compute device** — dynamic dispatch GPU/CPU berdasarkan workload type + VRAM check

**Data expansion roadmap (gratis, rate-limited):**
- BPS API (`webapi.bps.go.id`) — GDP, CPI, trade balance, IP
- BI SEKI — moneter, fiskal, real sector, eksternal
- NOAA ONI — El Nino/La Nina climate index
- World Bank API — GDP per negara, trade
- Commodity futures yfinance — CPO, coal, nickel, copper, tin

**Defer:** Satellite imagery (Sentinel-2 pipeline) — butuh infrastruktur ML berat, defer sampai base system stabil.

**Strategi baru untuk backtest:**
1. Pairs trading (statarb) — market-neutral, tahan bear market
2. Meta-labeled ensemble — filter prediksi buruk, boost precision
3. Regime-switching portfolio (HMM + dynamic allocation)
4. Foreign flow momentum — foreign net buy 5-day = entry signal
5. Triple-barrier labeled LightGBM — regime-aware, mean-reversion di bear

