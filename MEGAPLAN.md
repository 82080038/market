# MEGAPLAN — Aplikasi Pasar Modal Single-User (Pustaka 00–93)

**Ringkasan 1 kalimat:** Membangun aplikasi pasar modal personal yang lengkap di `/home/petrick/projects/market/` dari nol, mengikuti 94 dokumen `pustaka/` dan mengadopsi pola dari `trading-system` v0.1.11 sebagai referensi, dengan fase-fase dari MVP saham Indonesia menuju multi-pasar/multi-aset dan AI self-evolution, serta environment lifecycle Research → Paper → Live yang ketat.

---

## 1. Visi & Tujuan

Membuat satu aplikasi desktop/web single-user untuk analisis, rekomendasi, simulasi (paper trading), dan — setelah melewati promotion gates — eksekusi saham IDX yang aman, transparan, dan dapat diaudit. Aplikasi pada akhirnya dapat diperluas ke multi-pasar dan multi-aset sesuai `92-multi-market-multi-asset-trading-system.md` dan `93-lifecycle-environments-real-testing-ai.md`.

## 2. Acceptance Criteria Utama

1. **Data Pipeline:** Setiap hari aplikasi mengambil data EOD Yahoo Finance/IDX, membersihkannya, mendeteksi corporate actions, dan menyimpannya ke SQLite dalam <30 menit untuk 928 saham.
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
- Seluruh topik yang dibahas di 94 dokumen `pustaka/` (00-93), dikelompokkan ke dalam 12 fase berikut.
- Tech stack: Python 3.11+ (FastAPI, uv, Alembic, SQLite WAL, pandas, PyTorch cu121), Next.js 14+ (TypeScript, Tailwind).
- Single-user deployment lokal (Linux/WSL) dan Docker.
- Migrasi data dari `/media/petrick/Parquet/trading_data/` (read-only) ke SQLite lokal.
- Bahasa Indonesia UI + tooltip untuk istilah teknis.
- GPU `cuda:1` untuk LSTM, walk-forward, Monte Carlo, NLP/IndoBERT.

### Out of Scope (kecuali diminta eksplisit)
- Multi-user, KYC, RBAC, deployment publik/enterprise.
- Otorisasi regulator untuk memberikan saran investasi ke publik.
- Eksekusi uang nyata tanpa persetujuan manual.

## 4. Constraints & Assumptions

- Single-user personal; API key di `.env` cukup.
- UTC storage, WIB display (UTC+7).
- Data EOD utama; real-time tick feed opsional/berbayar.
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
- [~] Broker adapter skeleton: `MockBroker`, `PaperBroker`, `RealBroker` (interface akan dibuat Fase 5).
- [x] `.env` templates per environment.
- [ ] GitHub Actions CI: lint + test skeleton.
- [x] ADR (Architecture Decision Record) untuk 5 keputusan besar.

**Acceptance:** `uv sync` berhasil, `ruff check .` + `mypy src/market` + `pytest` bersih (coverage 92.55%).

---

### Fase 1 — Data Platform & Migration (Minggu 2-4)

**Tujuan:** data bersih, tersistem, dapat di-query, parquet berharga dimigrasi.

**Dokumen acuan:** `22-data-engineering-pipeline.md`, `84-new-data-arrival-processing-pipeline.md`, `90-analisis-parquet-data-awal.md`, `36-gap-data-timezone-global-idx.md`, `75-corporate-actions-processing-adjustment.md`, `91-komoditas-spesifik-idx.md`, `66-market-data-distribution.md`, `53-data-governance-lineage.md`.

**Deliverables & Markers:**
- [ ] `market_registry` table (MIC, timezone, trading hours, DST, settlement, lot, tick, currency).
- [ ] Extended `instrument_master` dengan `asset_class`, `market_mic`, `base_currency`, `lot_size`, `tick_size`, `underlying_ticker`.
- [ ] Data acquisition engine: Yahoo Finance adapter, IDX scraper, parquet archive fallback.
- [ ] Data quality validation: 8 checks + tier gold/silver/bronze/reject.
- [ ] `market_calendar` table + timezone/DST engine.
- [ ] `fx_rates` table + FX engine (USDIDR, HKDIDR, JPYIDR, dll.).
- [ ] Corporate action detection & backward adjustment.
- [ ] Migration 9 dataset parquet ke SQLite.
- [ ] Daily scheduler skeleton.

**Acceptance:** `market_paper.db` terisi OHLCV ≥2.9M rows, commodity, sentiment, shareholders; `fetch --universe idx` sukses tanpa FAIL major.

---

### Fase 2 — Core Analysis Engines: IDX (Minggu 5-7)

**Tujuan:** setiap faktor pasar modal dapat dihitung dan di-skor untuk saham Indonesia.

**Dokumen acuan:** `05-analisis-teknikal.md`, `06-analisis-fundamental.md`, `07-manajemen-risiko.md`, `18-modul-engine-data-wajib.md`, `21-portfolio-optimization-construction.md`, `23-machine-learning-trading.md`, `24-market-microstructure-likuiditas.md`, `30-sentiment-analysis-alternative-data.md`, `35-multi-asset-cross-market-analysis.md`, `39-screening-aiml-pattern-memory.md`, `58-feature-store-engineering-pipeline.md`, `31-risk-management-lanjutan.md`.

**Deliverables & Markers:**
- [ ] Technical analysis engine (RSI, MACD, MA, ADX, ATR, BB, volume profile).
- [ ] Fundamental analysis engine (PER, PBV, ROE, DER, EPS growth, DCF stub).
- [ ] Macro/global engine (US10Y, USD/IDR, oil, gold, S&P 500, etc.).
- [ ] Relationship/correlation engine (lead-lag, spillover, clustering).
- [ ] Sentiment engine (IndoBERT, foreign flow, broker flow, news, social media).
- [ ] Corporate action engine integrated into technical signals.
- [ ] Feature store with 42+ features per ticker, tagged `market_mic` + `asset_class`.
- [ ] Pattern memory / reliability tracker.

**Acceptance:** `/api/scores/{ticker}` returns 6 factor scores; unit tests per engine ≥70% coverage.

---

### Fase 3 — Decision, XAI & Advisory (Minggu 8-9)

**Tujuan:** aplikasi dapat memberikan saran yang dapat dijelaskan.

**Dokumen acuan:** `12-panduan-membangun-aplikasi-pasar-modal.md`, `18-modul-engine-data-wajib.md`, `46-prediksi-pola-portfolio-pipeline.md`, `83-advisory-system-screening-to-recommendation.md`, `85-backtest-to-live-gap-prevention.md`, `69-knowledge-base-persistent-memory.md`.

**Deliverables & Markers:**
- [ ] Decision engine with default weights (technical 20%, fundamental 25%, macro/global/sentiment/relationship).
- [ ] Regime-based weight adjustment.
- [ ] XAI narrative generator (Bahasa Indonesia, top 3 factors, warning flags).
- [ ] Advisory pipeline: screening → stock personality → strategy rec → position sizing → entry/exit → expected return → XAI evidence.
- [ ] `/api/recommend/{ticker}` endpoint.
- [ ] `/api/advisory/{ticker}` endpoint.
- [ ] Knowledge-base lookup integration.

**Acceptance:** Recommendation includes action, conviction, position size, SL/TP, expected hold period, risk flags, XAI narrative.

---

### Fase 4 — Backtest, Paper Trading & Risk (Minggu 10-12)

**Tujuan:** validasi strategi tanpa risiko finansial.

**Dokumen acuan:** `19-flow-logic-testing-kpi.md`, `20-syarat-robot-auto-trading.md`, `29-backtesting-strategy-validation.md`, `74-trading-financial-management-capital-operations.md`, `77-performance-attribution-benchmark-comparison.md`, `85-backtest-to-live-gap-prevention.md`, `07-manajemen-risiko.md`, `31-risk-management-lanjutan.md`.

**Deliverables & Markers:**
- [ ] Event-driven backtest engine (next-bar-open, realistic cost, slippage).
- [ ] Strategies: Buy & Hold, MA Crossover, Conviction.
- [ ] Walk-forward analysis, Monte Carlo simulation, Deflated Sharpe Ratio.
- [ ] Paper trading engine with lot validation, fees, tax, dividends.
- [ ] PnL engine (realized/unrealized, FIFO cost basis).
- [ ] Risk engine: VaR/CVaR, Kelly, position sizing, drawdown circuit breaker.
- [ ] Backtest quality gate runner (PBO, DSR, WFA).

**Acceptance:** Backtest returns equity curve, Sharpe, Sortino, max DD, win rate; paper trading updates virtual portfolio correctly.

---

### Fase 5 — Execution, OMS & Portfolio (Minggu 13-15)

**Tujuan:** sistem dapat mengelola order dan portofolio.

**Dokumen acuan:** `16-strategi-mencari-keuntungan.md`, `26-post-trade-settlement-rekonsiliasi.md`, `40-oms-ems-architecture.md`, `47-operational-contract-runbook.md`, `48-disaster-recovery-business-continuity.md`, `49-incident-management-post-mortem.md`, `52-transaction-cost-analysis-execution-quality.md`, `55-capacity-planning-load-stress-testing.md`, `74-trading-financial-management-capital-operations.md`, `76-idx-trading-rules-market-mechanics.md`.

**Deliverables & Markers:**
- [ ] OMS state machine (new → pending → partial → filled/cancelled/rejected).
- [ ] Order validation: lot, tick size, price limits, session, buying power.
- [ ] Broker adapter: mock, paper, Sinarmas/BNI stubs.
- [ ] Portfolio engine: positions, exposures, drift, rebalancing.
- [ ] Performance attribution vs IHSG (Brinson, factor attribution).
- [ ] Trade ledger (double-entry), NAV, reconciliation.
- [ ] DR/BCP & incident response runbooks.
- [ ] Capacity/stress test skeleton.

**Acceptance:** User can create paper order, see lifecycle status, and view real-time PnL.

---

### Fase 6 — Frontend & UI/UX (Minggu 16-18)

**Tujuan:** aplikasi usable oleh pemilik.

**Dokumen acuan:** `17-aplikasi-retail-pribadi.md`, `32-ui-ux-design-trading-app.md`, `43-mobile-app-architecture.md`, `56-notification-strategy-alert-fatigue.md`, `57-user-onboarding-journey-design.md`, `61-accessibility-a11y-trading-app.md`, `78-reporting-export-system.md`, `79-education-content-management.md`, `80-watchlist-alert-system.md`, `81-gamification-engagement-design.md`.

**Deliverables & Markers:**
- [ ] Next.js project scaffold (App Router, Tailwind, shadcn/ui, Recharts/Lightweight Charts).
- [ ] Dashboard page: portfolio summary, watchlist, market status, top movers.
- [ ] Stock detail page: chart, indicators, scores, recommendation, fundamentals.
- [ ] Portfolio page: positions, PnL, allocation, history.
- [ ] Backtest page: config, results, equity curve.
- [ ] Analysis/Screener page.
- [ ] Settings page: risk params, notifications, API key.
- [ ] Reports page: tax, dividend, trade log, statements.
- [ ] Watchlist & 15 alert types with Telegram/email/in-app routing.
- [ ] Education content CMS & gamification engine (XP, badges, streaks).
- [ ] Mobile responsive + accessibility.

**Acceptance:** All 7+ main pages accessible and data-driven; alerts can be triggered.

---

### Fase 7 — Multi-Market & Multi-Asset Extension (Minggu 19-21)

**Tujuan:** aplikasi siap untuk aset dan pasar lain sebagai input/faktor, dengan jalur trading bertahap.

**Dokumen acuan:** `03-pasar-modal-global.md`, `04-instrumen-pasar-modal.md`, `35-multi-asset-cross-market-analysis.md`, `36-gap-data-timezone-global-idx.md`, `92-multi-market-multi-asset-trading-system.md`.

**Deliverables & Markers:**
- [ ] Multi-market registry (US, HK, SG, JP, etc.).
- [ ] Multi-asset instrument master (equity, ETF, bond, commodity, forex, crypto, derivative stubs).
- [ ] FX & currency risk engine.
- [ ] Cross-market relationship engine (correlation, lead-lag, spillover).
- [ ] Per-asset-class fundamental scorer.
- [ ] Per-asset-class decision weights.
- [ ] Multi-market OMS validation rules.
- [ ] UI market selector + multi-currency PnL display.

**Acceptance:** `/api/instruments?market_mic=XNAS&asset_class=equity` works; cross-market correlation heatmap displayed.

---

### Fase 8 — Advanced AI/ML & MLOps (Minggu 22-24)

**Tujuan:** model dapat belajar, di-versioning, dan dipromosikan dengan aman.

**Dokumen acuan:** `23-machine-learning-trading.md`, `30-sentiment-analysis-alternative-data.md`, `39-screening-aiml-pattern-memory.md`, `51-mlops-model-risk-management.md`, `58-feature-store-engineering-pipeline.md`, `67-llm-agent-layer-self-evolution.md`, `71-eval-gated-promotion-ab-testing.md`.

**Deliverables & Markers:**
- [ ] LSTM/ensemble training pipeline (GPU `cuda:1`).
- [ ] Model registry with aliases (`@experiment`, `@candidate`, `@champion`).
- [ ] Feature store automation.
- [ ] Walk-forward & purged k-fold cross-validation.
- [ ] Model drift detection.
- [ ] Champion/challenger promotion workflow.
- [ ] A/B testing framework for strategies.
- [ ] Eval-gated promotion pipeline.

**Acceptance:** Model can be trained, registered, promoted, and inference uses champion alias.

---

### Fase 9 — AI Self-Evolution & Autonomous Layer (Minggu 25-27)

**Tujuan:** sistem dapat memperbaiki dirinya sendiri dengan pengawasan manusia.

**Dokumen acuan:** `67-llm-agent-layer-self-evolution.md`, `68-sandbox-execution-self-generated-code.md`, `69-knowledge-base-persistent-memory.md`, `70-hot-swap-runtime-update.md`, `71-eval-gated-promotion-ab-testing.md`, `72-human-in-the-loop-oversight.md`, `73-self-evolving-ai-roadmap-recommendation.md`, `86-gigantic-ai-autonomous-trading-system.md`.

**Deliverables & Markers:**
- [ ] Self-evolution agent loop (observe → analyze → reflect → decide → validate → execute → monitor → learn → evolve).
- [ ] Sandbox for AI-generated code (resource limits, AST scan, timeout).
- [ ] Human-in-the-loop approval bot (Telegram).
- [ ] Hot-swap runtime module update with rollback.
- [ ] Persistent knowledge/memory layer.
- [ ] Autonomous improvement pipeline integrated with eval-gate.

**Acceptance:** Agent can propose a small patch, run tests, and create a PR-like patch after eval-gate; human approval required for merge/live.

---

### Fase 10 — Security, Compliance & Operations (Minggu 28-29)

**Tujuan:** sistem siap produksi lokal dari sisi keamanan, kepatuhan, dan operasional.

**Dokumen acuan:** `10-regulasi-pasar-modal.md`, `33-cybersecurity-trading-system.md`, `41-uu-pdp-compliance-fintech.md`, `42-customer-support-dispute-resolution.md`, `47-operational-contract-runbook.md`, `48-disaster-recovery-business-continuity.md`, `49-incident-management-post-mortem.md`, `50-change-release-management-trading.md`, `54-trade-surveillance-market-abuse.md`, `62-api-versioning-deprecation-policy.md`, `63-investasi-syariah-des-screening.md`, `64-fractional-shares-micro-investing.md`, `82-vendor-third-party-integration-management.md`, `87-regulatory-developments-2026.md`.

**Deliverables & Markers:**
- [ ] Credential encryption at rest (Fernet).
- [ ] API versioning policy (`/api/v1/...`).
- [ ] Sharia-compliant DES screening.
- [ ] Fractional shares / micro-investing stubs.
- [ ] Vendor health check & SLA monitoring.
- [ ] Trade surveillance / market-abuse detection stubs.
- [ ] Incident response & DR runbooks tested.
- [ ] Customer support & dispute resolution workflow.
- [ ] UU PDP compliance checklist implemented.

**Acceptance:** Security review passes; no secrets in repo; runbooks executed at least once.

---

### Fase 11 — Social, Robo-Advisor, Monetization & Polish (Minggu 30-32)

**Tujuan:** fitur engagement lengkap, reporting lengkap, dan final polish.

**Dokumen acuan:** `44-social-copy-trading.md`, `45-robo-advisor-goal-based-investing.md`, `57-user-onboarding-journey-design.md`, `59-competitive-analysis-feature-benchmarking.md`, `60-monetization-business-model.md`, `78-reporting-export-system.md`, `79-education-content-management.md`, `81-gamification-engagement-design.md`.

**Deliverables & Markers:**
- [ ] Social/copy trading stubs (paper only, no real leaderboard for real trading).
- [ ] Robo-advisor / goal-based investing module.
- [ ] Onboarding journey (beginner → intermediate → advanced).
- [ ] Competitive analysis feature benchmarking.
- [ ] Monetization model document.
- [ ] Reporting engine: PDF/CSV/Excel exports.
- [ ] Final stress test & performance optimization.
- [ ] Complete documentation & user manual.

**Acceptance:** All major features accessible; load test ≥100 concurrent API calls; documentation complete.

---

## 6. Prompting-Cycle Autonomous Execution

### 6.1 Cara Menggunakan MEGAPLAN.md

AI (Devin/Cascade) memperlakukan MEGAPLAN.md sebagai **source of truth** proyek. Setiap sesi dimulai dengan:

1. Baca `@/home/petrick/projects/market/MEGAPLAN.md`.
2. Baca `@/home/petrick/projects/market/AGENTS.md`.
3. Baca `@/home/petrick/projects/market/.devin/SESSION_MEMORY.md`.
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
- Simpan ringkasan ke `@/home/petrick/projects/market/.devin/SESSION_MEMORY.md` dan memory system.
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

- [ ] Menjalankan migrasi skema DB `market_live.db`.
- [ ] Mengaktifkan broker adapter real / live trading.
- [ ] Menghapus file/data penting (termasuk DB lama).
- [ ] Menginstal dependency sistem atau mengubah konfigurasi OS.
- [ ] Deploy ke cloud/VPS/public endpoint.
- [ ] Memodifikasi konfigurasi keamanan (firewall, secrets, TLS).
- [ ] Mengganti model champion di Live environment.

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

## 9. Next Steps Segera

1. Review dan setujui MEGAPLAN.md.
2. (Setelah disetujui) salin ke root project: `/home/petrick/projects/market/MEGAPLAN.md`.
3. (Setelah disetujui) buat skill Devin: `.devin/skills/megaplan-executor/SKILL.md`.
4. Jalankan Fase 0: bootstrap repo, tooling, environment selector.
5. Update `.devin/SESSION_MEMORY.md` dengan status "Fase 0 sedang dikerjakan".
6. Mulai Fase 1: migrasi data parquet.
