# Pustaka: Knowledge Base Pasar Modal

> **Koleksi lengkap pengetahuan tentang pasar modal (global dan Indonesia) sebagai fondasi untuk membangun aplikasi pasar modal.**

---

## Tentang Pustaka Ini

Direktori `pustaka/` berisi dokumen Markdown komprehensif yang mencakup seluruh aspek pasar modal — dari konsep dasar hingga implementasi aplikasi, infrastruktur produksi, dan analisis multi-aset. Pengetahuan ini dikumpulkan dari riset internet mendalam, sumber otoritatif (OJK, BEI, SEC, Investopedia, CFA Institute, López de Prado, Diebold-Yilmaz, dll.), dan pengalaman nyata membangun sistem trading (`trading-system` v0.1.11).

---

## Keputusan Desain Aplikasi

Berikut adalah keputusan desain tetap yang berlaku untuk seluruh dokumen di pustaka ini:

### 1. Frontend Berbahasa Indonesia

- **Semua UI labels, menu, button, dan teks** ditampilkan dalam **Bahasa Indonesia**.
- Istilah pasar modal yang tidak dapat diterjemahkan (misal: *ticker*, *OHLCV*, *RSI*, *MACD*, *Sharpe ratio*, *VaR*, *P/E*, *EBITDA*) tetap ditampilkan dalam bahasa aslinya, **tetapi wajib memiliki tooltip** yang menjelaskan arti dan konteksnya dalam Bahasa Indonesia.
- Singkatan umum pasar modal (misal: *IDX*, *BEI*, *OJK*, *KSEI*, *KPEI*, *IPO*, *SPO*, *REITs*, *ETF*) juga wajib memiliki tooltip.
- Tooltip harus: (a) muncul on-hover (desktop) atau on-tap (mobile), (b) berisi penjelasan singkat 1-2 kalimat, (c) mudah diakses tanpa mengganggu flow pengguna.
- Lihat `32-ui-ux-design-trading-app.md` bagian [13. Bahasa Indonesia & Tooltip System](32-ui-ux-design-trading-app.md#13-bahasa-indonesia--tooltip-system).

### 2. Timezone GMT+7 (WIB) sebagai Acuan Lokal

- Aplikasi dijalankan di komputer yang berada di wilayah **GMT+7 (WIB / Indonesia Barat)**.
- **Storage:** Semua timestamp disimpan dalam **UTC** di database untuk konsistensi cross-market.
- **Display:** Semua waktu ditampilkan ke user dalam **WIB (UTC+7)**.
- **Operasi terjadwal** (render, backtesting, PnL testing, manajemen risiko, portfolio rebalancing, AI/ML auto-adjust, strategy testing, dll.) harus memperhitungkan:
  - Jam perdagangan IDX (09:00-15:50 WIB, Jumat 09:00-11:30 & 14:00-15:50 WIB).
  - Overlap dengan bursa Asia (HK, SG, TH, JP, CN) yang beroperasi pada jam yang berdekatan.
  - **Overnight gap** dari bursa US/Europe yang tutup setelah IDX dan buka sebelum IDX hari berikutnya.
  - DST (Daylight Saving Time) untuk US/Europe — offset UTC berubah Mar-Nov (US) dan Mar-Oct (EU).
- **Schedule semua operasi** mengacu pada waktu WIB lokal. Lihat `36-gap-data-timezone-global-idx.md` bagian [9. GMT+7 Local Timezone Awareness](36-gap-data-timezone-global-idx.md#9-gmt7-local-timezone-awareness).

### 3. Aplikasi Single-User (Tidak Multi-User)

- Aplikasi ini **hanya digunakan oleh satu orang** (pemilik/developer). Tidak ada multi-user, tidak ada user registration, tidak ada KYC, tidak ada role-based access control.
- **Security minimal:** API key cukup hardcoded di `.env` untuk development, tidak perlu JWT/OAuth/RBAC. Tidak perlu rate limiting per-user, CORS restrictive, atau audit trail untuk multi-user.
- **Yang TETAP diperlukan:**
  - Audit trail untuk trading decisions (untuk traceability dan debugging, bukan untuk compliance multi-user).
  - Backup database dan Parquet archive.
  - `.env` tetap di `.gitignore` (best practice, bukan security concern).
  - Broker API key tetap aman (jangan hardcode di repo).
- Lihat `33-cybersecurity-trading-system.md` bagian [13. Catatan: Single-User Application](33-cybersecurity-trading-system.md#13-catatan-single-user-application).

### 4. GPU/CUDA Acceleration Wajib Diperiksa

- **Setiap proses development, testing, dan production** harus selalu memeriksa apakah GPU CUDA dapat membantu mempercepat operasi.
- Hardware: 2x NVIDIA GeForce GTX 1050 Ti (4 GB VRAM each, Pascal GP107, compute capability 6.1).
- GPU 0 digunakan oleh display (Xorg/GNOME) — **prefer `cuda:1`** untuk compute.
- PyTorch 2.5.1+cu121 terinstall dan berfungsi di project `global`.
- Batasan: `batch_size <= 64`, `hidden_dim <= 256`, FP32 primary (no Tensor Cores).
- Operasi yang wajib periksa GPU: LSTM training, walk-forward, Monte Carlo backtest, VaR simulation, NLP/sentiment (IndoBERT), ensemble training.
- Operasi yang TIDAK perlu GPU: data fetching, database I/O, API handling, single ticker computation, frontend rendering.
- Lihat `34-performance-engineering-optimization.md` bagian [13. GPU/CUDA Acceleration](34-performance-engineering-optimization.md#13-gpucuda-acceleration).

---

## Daftar Dokumen

| # | File | Topik | Deskripsi |
|---|------|-------|-----------|
| 00 | `00-README.md` | **Index** | Dokumen ini — navigasi dan ringkasan |
| 01 | `01-fundamental-pasar-modal.md` | **Dasar Pasar Modal** | Definisi, fungsi, klasifikasi, peserta, mekanisme, konsep investasi |
| 02 | `02-pasar-modal-indonesia.md` | **Pasar Modal Indonesia** | Sejarah BEI, struktur kelembagaan, regulasi OJK, sistem perdagangan, indeks, konvensi IDX |
| 03 | `03-pasar-modal-global.md` | **Pasar Modal Global** | Bursa-bursa utama dunia, struktur, perbandingan developed vs emerging, tren global |
| 04 | `04-instrumen-pasar-modal.md` | **Instrumen** | Saham, obligasi, reksa dana, ETF, derivatif, sukuk, warrant, REITs |
| 05 | `05-analisis-teknikal.md` | **Analisis Teknikal** | Indikator (RSI, MACD, Bollinger, ATR, Ichimoku), pola chart, candlestick, implementasi kode |
| 06 | `06-analisis-fundamental.md` | **Analisis Fundamental** | Laporan keuangan, rasio (ROE, P/E, ROIC), valuasi (DCF, relative), kualitas earnings |
| 07 | `07-manajemen-risiko.md` | **Manajemen Risiko** | Position sizing, Kelly criterion, VaR/CVaR, drawdown, portfolio optimization |
| 08 | `08-trading-algoritmik.md` | **Trading Algoritmik** | Market microstructure, LOB, strategi, execution algorithms, backtesting, ML |
| 09 | `09-behavioral-finance.md` | **Behavioral Finance** | Bias kognitif & emosional, prospect theory, market anomalies, sentimen pasar |
| 10 | `10-regulasi-pasar-modal.md` | **Regulasi** | Regulasi Indonesia (UU, POJK, BEI) dan global (SEC, MiFID, GDPR), compliance |
| 11 | `11-knowledge-transfer-aplikasi.md` | **Knowledge Transfer** | Pola arsitektur, best practices, bug lessons dari proyek `trading-system` nyata |
| 12 | `12-panduan-membangun-aplikasi-pasar-modal.md` | **Panduan Aplikasi** | Sintesis: cara membangun aplikasi pasar modal menggunakan seluruh pengetahuan di atas |
| 13 | `13-hal-yang-perlu-diperhatikan.md` | **Hal yang Perlu Diperhatikan** | Risiko, kesalahan umum, checklist praktis, hal krusial sebelum investasi |
| 14 | `14-kendala-pasar-modal.md` | **Kendala Pasar Modal** | Tantangan struktural, likuiditas, transparansi, tata kelola, reformasi 2026 |
| 15 | `15-pelaku-pasar-modal.md` | **Pelaku Pasar Modal** | Emiten, investor, broker, underwriter, MI, lembaga & profesi penunjang, regulator |
| 16 | `16-strategi-mencari-keuntungan.md` | **Strategi Mencari Keuntungan** | Cara mencari keuntungan, persiapan, strategi investasi & trading, kendala, roadmap praktis |
| 17 | `17-aplikasi-retail-pribadi.md` | **Aplikasi Retail/Pribadi** | Analisis lengkap fitur aplikasi retail/pribadi untuk investor individu di pasar modal |
| 18 | `18-modul-engine-data-wajib.md` | **Modul, Engine, dan Data Wajib** | Daftar definitif semua modul, engine, data, database schema, event bus, dan checklist implementasi |
| 19 | `19-flow-logic-testing-kpi.md` | **Flow, Logic, Testing, Aturan & KPI** | Data flow end-to-end, business logic, state machine, aturan aplikasi, testing strategy, KPI sistem/engine/bisnis, SLA, security rules |
| 20 | `20-syarat-robot-auto-trading.md` | **Syarat Robot/Auto Trading** | Analisis mendalam 12 pilar syarat robot trading: arsitektur, data, decision, risk, eksekusi, broker, monitoring, security, infrastruktur, compliance, testing, failsafe |
| 21 | `21-portfolio-optimization-construction.md` | **Portfolio Optimization** | Markowitz MPT, efficient frontier, Black-Litterman, HRP, risk parity, rebalancing, covariance estimation, IDX constraints |
| 22 | `22-data-engineering-pipeline.md` | **Data Engineering Pipeline** | Data sources, ingestion, ETL, storage architecture, real-time feeds, data quality framework, Parquet, lineage |
| 23 | `23-machine-learning-trading.md` | **Machine Learning Trading** | Feature engineering, model selection, walk-forward optimization, regime detection (HMM), labeling, purged CV, ensemble |
| 24 | `24-market-microstructure-likuiditas.md` | **Market Microstructure & Likuiditas** | Order book, bid-ask spread, price discovery, slippage modeling, market impact, IDX tick size/auto-reject |
| 25 | `25-pajak-akuntansi-trading.md` | **Pajak & Akuntansi Trading** | PPh final 0,1%, pajak dividen 10%, PP 9/2021, SPT reporting, cost basis tracking (FIFO/avg), NAV calculation |
| 26 | `26-post-trade-settlement-rekonsiliasi.md` | **Post-Trade & Settlement** | Trade lifecycle, KPEI/KSEI clearing, T+2 settlement, reconciliation, corporate action processing, NAV, performance attribution |
| 27 | `27-deployment-devops-trading.md` | **Deployment & DevOps** | Docker, CI/CD pipeline, environment management, monitoring, alerting (Telegram), blue-green deployment, backup, disaster recovery |
| 28 | `28-api-design-integration-patterns.md` | **API Design & Integration** | REST API design, WebSocket real-time, FIX protocol, broker API adapter pattern, event-driven architecture, auth, rate limiting |
| 29 | `29-backtesting-strategy-validation.md` | **Backtesting & Validation** | Vectorized vs event-driven, look-ahead/survivorship bias, walk-forward analysis, Monte Carlo, Deflated Sharpe Ratio, transaction cost modeling |
| 30 | `30-sentiment-analysis-alternative-data.md` | **Sentiment & Alternative Data** | NLP Bahasa Indonesia (IndoBERT), RSS news, Reddit/X, foreign flow sentiment, Google Trends, broker concentration, Fear & Greed index |
| 31 | `31-risk-management-lanjutan.md` | **Risk Management Lanjutan** | VaR/CVaR (historical, parametric, Monte Carlo), stress testing, Kelly criterion, correlation-based sizing, drawdown circuit breaker, risk parity |
| 32 | `32-ui-ux-design-trading-app.md` | **UI/UX Design Trading App** | Dashboard layout, data visualization, real-time WebSocket UI, mobile-first, order entry flow, design system, accessibility, IDX-specific UI |
| 33 | `33-cybersecurity-trading-system.md` | **Cybersecurity Trading System** | API security, JWT/RBAC, encryption, audit trail, OWASP financial, key management, secure broker integration, UU PDP compliance, incident response |
| 34 | `34-performance-engineering-optimization.md` | **Performance Engineering** | SQLite optimization, index strategy, caching (LRU/Redis), async I/O, memory management, batch processing, frontend performance, profiling |
| 35 | `35-multi-asset-cross-market-analysis.md` | **Multi-Asset & Cross-Market** | Intermarket analysis, correlation dynamics, lead-lag (Granger), spillover (Diebold-Yilmaz), cross-asset signals, global→IDX, commodity linkage, FX-equity, sector rotation |
| 36 | `36-gap-data-timezone-global-idx.md` | **Gap Data & Timezone** | Zona waktu bursa global, jam perdagangan IDX, overlap IDX-global, delay data per provider (Yahoo 10min, broker real-time), overnight gap risk, strategi mitigasi gap |
| 37 | `37-bahasa-pemrograman-tech-stack.md` | **Bahasa Pemrograman & Tech Stack** | Riset bahasa pemrograman terbaik untuk aplikasi pasar modal: Frontend (Next.js/SvelteKit, TypeScript), Middleware (Go, gRPC, Kafka, Redis), Backend (Python FastAPI, Go, Rust), benchmark performance, rekomendasi stack untuk IDX, adopsi dari proyek existing |
| 38 | `38-manajemen-aplikasi-ritel.md` | **Manajemen Aplikasi Ritel** | Modul manajemen admin: User & KYC, Konten & Edukasi, Data & Sumber Data, Broker & Eksekusi, Keuangan & Billing, Kepatuhan & Audit, Risiko Sistem, Operasional, Notifikasi, Keamanan & Akses, Analytics, API, Backup & DR, Admin Dashboard blueprint, implementasi IDX |
| 39 | `39-screening-aiml-pattern-memory.md` | **Screening, AI/ML & Pattern Memory** | Screener saham (teknikal, fundamental, multi-faktor, sentimen, gorengan detector), AI/ML untuk pola saham (LSTM, weight optimization, walk-forward), 6 faktor yang mempengaruhi harga, pattern memory (win-rate historis per pola per saham), feedback loop, integrasi ketiga komponen, status implementasi codebase |
| 40 | `40-oms-ems-architecture.md` | **OMS/EMS Architecture** | Order Management System & Execution Management System — order state machine, event sourcing, smart order routing, partial fill handling, idempotency, kill switch, reconciliation, IDX-specific considerations |
| 41 | `41-uu-pdp-compliance-fintech.md` | **UU PDP Compliance untuk Fintech** | Implementasi UU No. 27/2022 (Personal Data Protection) — data subject rights, DPO, breach notification, data localization, consent management, overlap dengan POJK 11 & POJK 22 |
| 42 | `42-customer-support-dispute-resolution.md` | **Customer Support & Dispute Resolution** | Ticketing system, escalation workflow (4-tier), SLA management, AI chatbot dengan guardrails, LAPS-SJK integration, knowledge base, OJK reporting, audit trail |
| 43 | `43-mobile-app-architecture.md` | **Mobile App Architecture** | Flutter vs React Native vs Native, offline support & sync, biometric auth, push notification (FCM), security mobile (certificate pinning, root detection), app store deployment, performance optimization |
| 44 | `44-social-copy-trading.md` | **Social & Copy Trading** | Copy trading engine, creator verification & ranking, risk firewall (AI audit), leaderboard & discovery, social features (follow, comment, portfolio share), regulatory considerations (OJK), monetization (performance fee) |
| 45 | `45-robo-advisor-goal-based-investing.md` | **Robo-Advisor & Goal-Based Investing** | Goal-based planning (rumah, pensiun, haji), risk profiling questionnaire, automated portfolio allocation (IDX-specific), micro-savings (round-up), automated rebalancing, DCA automation, AI narrative advice |
| 46 | `46-prediksi-pola-portfolio-pipeline.md` | **Prediksi, Pola & Portfolio Pipeline** | Prediction Engine (fusion LSTM + pattern + factor + regime + sentiment), per-stock testing & pattern discovery, Error Analysis Engine (self-correction: root cause → mark → adjust), Pattern Journal (dokumentasi pola per saham), Portfolio Candidate Pipeline (prediksi → filter → risk → optimization → alokasi) |
| 47 | `47-operational-contract-runbook.md` | **Operational Contract & Runbook** | 5W1H+Output framework untuk setiap task (What/When/Who/How/Where/Why/Output), Task Operations Matrix (53 tasks), RACI matrix, runbook per task category, aturan operasional (idempotency, retry, backoff, SLA/SLO), master schedule unified, failure handling & escalation, observability & audit trail |
| 48 | `48-disaster-recovery-business-continuity.md` | **Disaster Recovery & BCP** | RTO/RPO per komponen, failure scenarios & recovery procedures (DB corrupt, GPU fail, API down, data source down, disk full, multi-failure), backup strategy (3-2-1 rule), failover matrix, DR drill schedule quarterly |
| 49 | `49-incident-management-post-mortem.md` | **Incident Management & Post-Mortem** | Incident lifecycle (detect→respond→mitigate→resolve→post-mortem→improve), severity matrix, on-call rotation, blameless post-mortem template, action item tracking, incident metrics (MTTD/MTTA/MTTM/MTTR) |
| 50 | `50-change-release-management-trading.md` | **Change & Release Management** | Change classification (A-E), blue-green deploy, canary release untuk trading logic, feature flags untuk trading, rollback strategy per komponen, change approval process, pre-deployment checklist, post-deployment verification |
| 51 | `51-mlops-model-risk-management.md` | **MLOps & Model Risk Management** | MLOps lifecycle, model registry & versioning, drift detection (data drift PSI, concept drift), model monitoring (health score), champion/challenger pattern, model retirement policy, model risk governance, feature store integration |
| 52 | `52-transaction-cost-analysis-execution-quality.md` | **TCA & Execution Quality** | Implementation shortfall, VWAP/TWAP/arrival benchmark, market impact model (square root), slippage analysis per ticker, best execution policy & score, TCA report template, IDX-specific costs (auto-reject, lot size, tick size) |
| 53 | `53-data-governance-lineage.md` | **Data Governance & Lineage** | Data catalog (39 tables), data lineage graph (source→ingestion→storage→processing→output), data quality SLA (completeness/accuracy/timeliness/validity/uniqueness), data retention policy (forever→7yr→5yr→2yr→1yr), data stewardship, PII handling |
| 54 | `54-trade-surveillance-market-abuse.md` | **Trade Surveillance & Market Abuse** | Wash trade detection, spoofing, layering, front-running, marking the close, excessive trading, surveillance dashboard, compliance log untuk OJK, alert & investigation process |
| 55 | `55-capacity-planning-load-stress-testing.md` | **Capacity Planning & Stress Testing** | Current capacity baseline, capacity limits per komponen (GPU VRAM, CPU O(n²), SQLite, network), scale-up triggers, load test scenarios, stress test (multi-failure), capacity forecast, upgrade roadmap (GPU/RAM/PostgreSQL) |
| 56 | `56-notification-strategy-alert-fatigue.md` | **Notification Strategy & Alert Fatigue** | Severity-based routing, alert deduplication, quiet hours & suppression, alert aggregation (daily/weekly summary), escalation policy, alert quality metrics (precision/recall/MTTA/fatigue index) |
| 57 | `57-user-onboarding-journey-design.md` | **User Onboarding & Journey** | First-run experience, risk profile assessment (konservatif→speculator), educational onboarding, paper trading as mandatory step, progressive disclosure UI, onboarding funnel metrics |
| 58 | `58-feature-store-engineering-pipeline.md` | **Feature Store & Engineering Pipeline** | Centralized feature definitions (42 features), feature computation pipeline, feature serving (online cache vs offline), feature freshness monitoring, feature versioning, feature reuse matrix across 8 consumers |
| 59 | `59-competitive-analysis-feature-benchmarking.md` | **Competitive Analysis & Benchmarking** | Competitor landscape (Stockbit/Bibit/Ajaib/IPOT/Mirae), feature parity matrix, strengths & weaknesses, unique selling proposition (AI prediction, XAI, self-correction), gap analysis, pricing comparison |
| 60 | `60-monetization-business-model.md` | **Monetization & Business Model** | Business model options (SaaS/subscription/broker share/data API/white-label), freemium tier design (Free/Pro/Elite), revenue projections (Year 1-3), cost structure, break-even analysis |
| 61 | `61-accessibility-a11y-trading-app.md` | **Accessibility (a11y)** | WCAG 2.1 AA compliance, screen reader support untuk chart data, keyboard navigation & shortcuts, color-blind friendly charts, ARIA live regions untuk price updates, implementation checklist |
| 62 | `62-api-versioning-deprecation-policy.md` | **API Versioning & Deprecation** | URL-based versioning, backward compatibility rules, deprecation timeline (announce→warn→sunset→retire→remove), migration guide template, version header strategy, changelog format |
| 63 | `63-investasi-syariah-des-screening.md` | **Investasi Syariah: DES Screening** | Implementasi modul investasi syariah — screening DES, kriteria DSN-MUI, integrasi decision engine, sukuk, Sharia virtual trading, Sharia education portal, compliance OJK |
| 64 | `64-fractional-shares-micro-investing.md` | **Fractional Shares & Micro-Investing** | Broker pooling model untuk fractional shares di IDX, sub-lot accounting, corporate action handling (split, dividend, rights), reconciliation, alternatif reksadana fractional |
| 65 | `65-event-driven-event-sourcing.md` | **Event-Driven Architecture & Event Sourcing** | EDA untuk trading system — Kafka topic design, CQRS pattern, event store, replay capability (backtest, audit, recovery), backpressure handling, multi-exchange normalization |
| 66 | `66-market-data-distribution.md` | **Market Data Distribution** | Ticker plant architecture, WebSocket vs SSE, connection pooling & sharding, delta encoding (67% bandwidth saving), coalescing & throttling, price tick validation, CDN/edge caching |
| 67 | `67-llm-agent-layer-self-evolution.md` | **LLM Agent Layer untuk Self-Evolution** | Arsitektur 5-agent (Monitor, Analyzer, Builder, Validator, Integrator) untuk self-building, self-repairing, self-updating — LLM code generation, TDD cycle, event bus integration, database schema |
| 68 | `68-sandbox-execution-self-generated-code.md` | **Sandbox Execution** | Isolasi aman untuk eksekusi kode dari LLM — process/container/E2B levels, resource limits, code scanning (AST + regex), mock strategy, security measures, rollback |
| 69 | `69-knowledge-base-persistent-memory.md` | **Knowledge Base: Persistent Memory** | Function registry, lesson store, pattern memory integration, search & retrieval (keyword, similarity, tag), reuse tracking, anti-pattern detection |
| 70 | `70-hot-swap-runtime-update.md` | **Hot-Swap: Runtime Module Update** | `importlib.reload()` mechanism, state preservation, dependency-aware reload order, rollback manager, safety guards (locked modules, market hours check) |
| 71 | `71-eval-gated-promotion-ab-testing.md` | **Eval-Gated Promotion & A/B Testing** | 7-layer evaluation pipeline, A/B testing untuk trading, statistical significance (bootstrap, paired t-test, Cohen's d), falsification criteria, champion/challenger pattern |
| 72 | `72-human-in-the-loop-oversight.md` | **Human-in-the-Loop Oversight** | Approval gate architecture, risk classification (low/medium/high/critical), escalation policy, Telegram approval bot, kill switch, audit & compliance, LLM cost tracking |
| 73 | `73-self-evolving-ai-roadmap-recommendation.md` | **Self-Evolving AI Roadmap & Rekomendasi** | 5 level self-evolution (L1-L5), current state assessment, roadmap bertahap (2-24 bulan), safety boundaries, cost estimation, risk register, rekomendasi implementasi |
| 74 | `74-trading-financial-management-capital-operations.md` | **Trading Financial Management & Capital Operations** | Kalkulasi modal per transaksi (price + fees + tax), cek buying power (cash balance vs capital needed), flow screening→decision→eksekusi, cash flow manager (deposit/withdraw/buy/sell/dividend), capital allocator (conviction/equal-weight/HRP), PnL engine (realized/unrealized/FIFO), trade ledger (double-entry), NAV calculation, reconciliation (broker vs internal), capital efficiency metrics, financial config & parameter management |
| 75 | `75-corporate-actions-processing-adjustment.md` | **Corporate Actions Processing & Adjustment** | Stock split, reverse split, stock dividend, cash dividend, bonus share, rights issue — price adjustment (backward), position adjustment (qty/price), cost basis adjustment, ex-date/cum-date/record date/payment date logic, dividend processor (PPh 10%), automated daily processing pipeline, ex-date notification |
| 76 | `76-idx-trading-rules-market-mechanics.md` | **IDX Trading Rules & Market Mechanics** | Sesi perdagangan (pre-opening/S1/S2/pre-closing), fraksi harga/tick size, lot size 100, auto-reject (ARA/ARB 15-25%), circuit breaker IHSG (5%/10%/15%), trading halt, short selling (Designated Securities), margin trading (initial 50%/maintenance 30%), order validation |
| 77 | `77-performance-attribution-benchmark-comparison.md` | **Performance Attribution & Benchmark Comparison** | Risk-adjusted metrics (Sharpe, Sortino, Calmar, Information Ratio, max drawdown), benchmark comparison vs IHSG (alpha, beta, R²), Brinson attribution (allocation/selection/interaction effect), factor attribution (6-factor regression), return decomposition (capital gain + dividend - costs - tax) |
| 78 | `78-reporting-export-system.md` | **Reporting & Export System** | Report types (portfolio summary, monthly/annual statement, tax report/SPT, performance report, trade log, dividend statement), export formats (PDF/CSV/Excel/JSON), Jinja2 template engine, scheduled report generation, regulatory reporting (OJK/DJP), API endpoints |
| 79 | `79-education-content-management.md` | **Education & Content Management** | Learning path (3 level: Pemula/Menengah/Advanced, 15 modul), content types (article/video/tutorial/quiz/simulation), glossary (200+ entries), contextual help & tooltip, quiz & assessment (passing score gating), content management system (draft→review→publish), API endpoints |
| 80 | `80-watchlist-alert-system.md` | **Watchlist & Alert System** | Multiple watchlist per user, 15 alert types (price/volume/score/conviction/technical/foreign flow/drawdown/corporate action), alert lifecycle (active→triggered→expired), notification routing (push/Telegram/email/in-app), snooze & recurring, alert history log, anti-spam dedup |
| 81 | `81-gamification-engagement-design.md` | **Gamification & Engagement Design** | XP & level system (8 level), 15 badge/achievement, streak system (learning/discipline/review/paper trading), challenge & quest, leaderboard (education/discipline/paper only — NO real trading leaderboard), anti-overtrading guardrails (daily XP cap, loss streak pause), opt-out |
| 82 | `82-vendor-third-party-integration-management.md` | **Vendor & Third-Party Integration Management** | Vendor landscape (data/broker/infrastructure/notification), vendor config & health check, broker API failover, SLA monitoring, per-vendor circuit breaker, fallback strategy (Yahoo→archive, broker→mock, Telegram→email), vendor evaluation framework (6 criteria), API endpoints |
| 83 | `83-advisory-system-screening-to-recommendation.md` | **Advisory System: Screening ke Saran Eksekusi** | Pipeline advisory lengkap — data testing & validation, screening (3 template + factor screener + equity filter), stock personality classification, strategy recommendation (swing/position/momentum/value/dividend), saran jumlah (position sizing + fees), saran entry (timing + technical signals), saran exit (SL/TP/trailing/conviction exit), persentase untung (expected value + win probability), alasan empiris (6-factor scores + XAI narrative + backtest evidence + VaR), eksekusi otomatis (condition check + auto-execute + post-execution monitoring), `/api/advisory/{ticker}` endpoint |
| 84 | `84-new-data-arrival-processing-pipeline.md` | **New Data Arrival Processing Pipeline** | Pipeline 7 tahap setiap data baru masuk — Stage 1: ingestion (Yahoo/archive/IDX, rate limit, raw Parquet), Stage 2: pemeriksaan data lengkap (8 quality checks: completeness, plausibility, volume anomaly, gap detection, cross-source, reconciliation, OHLCV internal, TIP quality → score 0-100, tier gold/silver/bronze/reject), Stage 3: testing & validasi (normalization, corporate action detection, adjusted close, save to SQLite + watermark + Parquet sync), Stage 4: screening (3 template + factor screener + equity filter), Stage 5: penemuan pola (30+ indicators, chart & candlestick pattern detection, pattern reliability scoring, stock personality classification), Stage 6: penandaan & labeling ke DB (6-factor scores, AI labels triple-barrier, pattern tagging, personality tagging, data quality tag, watermark, audit trail), Stage 7: post-processing (decision engine, recommendation, XAI, risk metrics, alerts, auto-execution), daily runner implementation, real-time pipeline roadmap |
| 85 | `85-backtest-to-live-gap-prevention.md` | **Backtest-to-Live Gap Prevention** | Mengatasi fenomena “backtest selalu untung, live trading rugi” — 7 root causes (look-ahead bias, survivorship bias, overfitting, unrealistic costs, market impact, regime change, behavioral gap), 8 mekanisme yang sudah diimplementasi (next-bar-open execution, survivorship-free backtest, walk-forward validation, realistic cost model + slippage, regime filter, automated execution, circuit breaker + daily loss limit, paper trading), 6 gap yang masih kurang (WFA belum mandatory, paper-vs-backtest comparison, conservative slippage, faster regime detection, live degradation alert, mandatory paper period), backtest-to-live transition protocol (6 step: backtest → WFA → paper 30 hari → live small → scale up → full size), stop conditions, continuous validation loop, re-validation triggers |
| 86 | `86-gigantic-ai-autonomous-trading-system.md` | **Gigantic AI: Sistem Trading Otonom yang Berkembang Sendiri** | Arsitektur "Gigantic AI" yang bekerja mandiri tanpa campur tangan user — self-awareness layer (8 state: market/portfolio/performance/model/data/strategy/self/risk), self-reflection (5 pertanyaan: Am I profitable? Am I degrading? Is my model stale? Am I within risk limits? Are my self-improvements working?), autonomous decision loop 9-step (observe → analyze → reflect → decide → validate → execute → monitor → learn → evolve), runtime code generation dengan 7-layer validation + accountability (setiap keputusan + kode punya alasan empiris), profitability guarantee 5-layer (strategy validation → pre-execution risk → post-execution monitoring → self-correction → circuit breaker), 7-layer architecture stack (Layer 0 infrastructure → Layer 1 data → Layer 2 AI/ML → Layer 3 analysis → Layer 4 decision → Layer 5 self-awareness → Layer 6 self-evolution), 5 autonomy levels (A0 manual → A4 fully autonomous), path to full autonomy 24 bulan, perbedaan gigantic AI vs AGI (operational self-awareness bukan philosophical consciousness) |
| 87 | `87-regulatory-developments-2026.md` | **Regulatory Developments 2026** | Perkembangan regulasi pasar modal 2026 — POJK No. 3/2026 (PEKU 1/2/3, permodalan minimum perusahaan efek), POJK No. 5/2026 (MIKU 1/2, dana kelolaan minimum MI), 8 rencana aksi reformasi OJK (free float 15%, UBO transparansi, demutualisasi BEI, enforcement, tata kelola emiten), reformasi BEI PPK/FCA (hapus 3 kriteria teknis, auto-reject berjenjang 4 kelompok harga, Non-Cancellation Period), implikasi untuk aplikasi trading, update konfigurasi, testing |
| 88 | `88-gap-teori-vs-praktek.md` | **Gap Analysis: Teori vs Praktek** | Audit komparatif antara 88 dokumen pustaka (teori) vs `trading-system` v0.1.11 (kode aktual) — 25+ gap teridentifikasi across frontend, OMS, broker integration, market data real-time, infrastructure, security, AI/ML, testing; rencana penutupan gap dengan 8 roadmap dan prioritas timeline |
| 89 | `89-faktor-pasar-modal-analisis-implementasi.md` | **Faktor Pasar Modal: Analisis & Implementasi** | Audit komprehensif 22 faktor yang mempengaruhi pasar modal IDX — 13 faktor tercakup terimplementasi, 5 sebagian, 9 belum dibahas; cara menggunakan data per faktor, implementasi di trading-system, gap prioritas, rekomendasi update pustaka |
| 90 | `90-analisis-parquet-data-awal.md` | **Analisis Parquet: Data Awal Database** | Analisis struktur direktori `/media/petrick/Parquet/trading_data` (raw + archive), 28 tabel archive siap pakai, 53 raw subdirs data legacy, 77 tabel sqlite_backup, 9 data berharga belum di-migrate, masalah schema (kolom Bahasa Indonesia, duplikasi, stale data, UUID), 8 schema SQL baru, rekomendasi quick wins migrasi |
| 91 | `91-komoditas-spesifik-idx.md` | **Komoditas Spesifik IDX** | Hubungan harga komoditas dan saham emiten di IDX — 10 komoditas (CPO, batubara, nikel, tembaga, emas, perak, timah, aluminium, gas, crude oil), mapping ke emiten, mekanisme transmisi, time lag, faktor driver, cara analisis dan scoring, roadmap implementasi 6-8 hari |
| 92 | `92-multi-market-multi-asset-trading-system.md` | **Multi-Market & Multi-Asset Trading System** | Ekstensi aplikasi single-user dari saham Indonesia ke multi-pasar (US, HK, SG, JP, dll.) dan multi-aset (saham, ETF, obligasi, komoditas, forex, kripto, derivatif) — instrument master, market registry, timezone/DST, multi-currency, AI/ML cross-market, decision engine multi-aset, advisory engine, OMS multi-pasar, risk & compliance per yurisdiksi, roadmap implementasi |
| 93 | `93-lifecycle-environments-real-testing-ai.md` | **Lifecycle Environment: Real, Testing & AI/ML Development** | Analisis konsep 3 environment (Research/Development, Paper/Staging, Live/Production) untuk aplikasi trading — arsitektur environment, promotion gates (backtest → paper → live), isolasi data/kode/model, CI/CD & model registry alias, 7 live auto-pause metrics, rollback rules, governance & approval workflow, penerapan pada project ini |
| 94 | `94-aiml-knowledge-architecture-analysis.md` | **AI/ML Knowledge Architecture Analysis** | Audit data aktual database untuk 5 pilar AI/ML (Asset Mapping, Correlation, Price Drivers, Anomaly Detection, Data Structuring), 7 prioritas tindakan implementasi (triple-barrier labels, fundamental quarterly, macro Indonesia, global macro repopulate, multi-window relationship, global calendar, regime labels), kode dan script yang dibuat |
| 95 | `95-sync-db-to-parquet.md` | **Sync DB → Parquet (Hybrid Incremental)** | Desain dan implementasi sinkronisasi incremental dari SQLite ke Parquet archive — hybrid strategy (19 tabel time-series partitioned Hive year/month + 12 reference full-rewrite + 10 runtime skip), tabel `parquet_sync_state` (migration 0008), safety window 7 hari, kompatibilitas dengan `migrate_parquet.py`, CLI `scripts/sync_db_to_parquet.py` |
| 96 | `96-ai-ml-audit-framework.md` | **AI/ML Audit Framework** | Framework komprehensif untuk mengevaluasi apakah model AI/ML memberikan Alpha atau overfitting — 4 pilar audit (Model Performance Metrics, Ablation Study, Latency & Cost-Benefit, Feature Importance & Drift), score card 5 kriteria, statistical significance tests (paired t-test, Diebold-Mariano, White's RC), automated remediation pipeline, hasil audit awal baseline teknikal vs random |
| 97 | `97-strategi-alternatif-ekspansi-data-2026.md` | **Strategi Alternatif & Ekspansi Data 2026** | Analisis mendalam 7 area pengembangan strategi dan data untuk mengatasi prediction accuracy 40-43% — pairs trading (statarb cointegration, Sharpe 1.67 LSTM vs 0.69 traditional IDX), volume features (OFI proxy, VWAP, foreign flow signal), policy event scorer (BI/BEI/corporate actions), data satelit proxy gratis (BPS/BI/NOAA/WorldBank), meta-labeling (Lopez de Prado, fix accuracy), GitHub repos (vectorbt, mlfinlab, StatArb-Research), dynamic GPU/CPU dispatch, 7 modul baru dibuat |
| 98 | `98-migrasi-sqlite-ke-postgresql.md` | **Migrasi SQLite → PostgreSQL** | DDL schema PostgreSQL (partitioning by month, TIMESTAMPTZ, JSONB, GIN/GiST indexes), view v_domino_timeline, multi-DB support (config.py database_url, db/engine.py, db/raw.py), migrasi 3.2M rows OHLCV + 345K broker_transactions, scripts migrate_sqlite_to_pg.py + backfill_broker_transactions.py |
| 99 | `99-matriks-relevansi-satelit-pasar-modal.md` | **Matriks Relevansi: Data Satelit vs Pasar Modal** | Daftar 9 sumber data satelit gratis (NASA POWER, Sentinel-2, VIIRS, Sentinel-1 SAR, AIS, Umbra, MODIS, Landsat, Forest Data Partnership), matriks relevansi 16 pasangan data-satelit vs ticker/komoditas, 6 studi pendukung (Nature, IMF, arxiv, ESA), prioritas implementasi pipeline, cross-reference ke pipeline `scripts/satellite_stock_correlation.py` |
| 100 | `100-astronacci-time-cycle-integration.md` | **Astronacci: Financial Astrology & Time Cycle** | Integrasi metodologi Astronacci (Astrology + Fibonacci) sebagai indikator "WHEN" — tabel `astronacci_cycles` (14,073 rows, 1927–2026), 3 elemen astrologi (Moon Phase, Retrograde, Ingress) + Fibonacci Time Windows, module `src/market/analysis/astronacci.py` (PyEphem), integrasi ke SignalEnhancer (signal ke-8, weight 6%) dan MarketContext (weight 3%), backfill script, 32 tests |

---

## Cara Membaca

### Untuk Pemula

1. Mulai dari `01-fundamental-pasar-modal.md` → pahami konsep dasar
2. Lanjut `02-pasar-modal-indonesia.md` → konteks Indonesia
3. Baca `04-instrumen-pasar-modal.md` → kenali instrumen
4. Pelajari `05-analisis-teknikal.md` dan `06-analisis-fundamental.md` → metode analisis
5. Pahami `07-manajemen-risiko.md` → penting untuk survival
6. Baca `13-hal-yang-perlu-diperhatikan.md` → hindari kesalahan fatal
7. Pahami `14-kendala-pasar-modal.md` → kenali tantangan pasar
8. Pelajari `15-pelaku-pasar-modal.md` → kenali siapa saja yang terlibat
9. Baca `16-strategi-mencari-keuntungan.md` → pelajari cara mencari profit
10. Pelajari `17-aplikasi-retail-pribadi.md` → pahami fitur aplikasi retail untuk investor individu
11. Rujuk `18-modul-engine-data-wajib.md` → daftar lengkap modul, engine, dan data sistem
12. Pelajari `19-flow-logic-testing-kpi.md` → pahami flow, aturan, testing, dan KPI sistem
13. Baca `20-syarat-robot-auto-trading.md` → pahami syarat mendalam untuk robot/auto trading
14. Pelajari `25-pajak-akuntansi-trading.md` → pahami pajak trading saham di Indonesia
15. Baca `32-ui-ux-design-trading-app.md` → pahami desain antarmuka aplikasi trading

### Untuk Developer

1. Baca semua dokumen 01-18 untuk konteks domain
2. Fokus pada `11-knowledge-transfer-aplikasi.md` → pelajaran dari proyek nyata
3. Ikuti `12-panduan-membangun-aplikasi-pasar-modal.md` → blueprint implementasi
4. Pelajari `17-aplikasi-retail-pribadi.md` → fitur khusus aplikasi retail/pribadi
5. Rujuk `18-modul-engine-data-wajib.md` → spesifikasi teknis modul, engine, data, dan checklist
6. Pelajari `19-flow-logic-testing-kpi.md` → flow, logic, testing, aturan, KPI, SLA, security
7. Wajib baca `20-syarat-robot-auto-trading.md` → 12 pilar syarat robot trading, checklist implementasi, pitfall
8. Pelajari `21-portfolio-optimization-construction.md` → MPT, Black-Litterman, HRP, rebalancing
9. Pelajari `22-data-engineering-pipeline.md` → arsitektur data pipeline, ETL, quality framework
10. Pelajari `23-machine-learning-trading.md` → ML pipeline, walk-forward, regime detection, ensemble
11. Pelajari `24-market-microstructure-likuiditas.md` → order book, spread, slippage, IDX specifics
12. Pelajari `25-pajak-akuntansi-trading.md` → PPh final, cost basis, SPT reporting
13. Pelajari `26-post-trade-settlement-rekonsiliasi.md` → trade lifecycle, settlement, reconciliation
14. Pelajari `27-deployment-devops-trading.md` → Docker, CI/CD, monitoring, disaster recovery
15. Pelajari `28-api-design-integration-patterns.md` → REST, WebSocket, FIX, broker integration
16. Pelajari `29-backtesting-strategy-validation.md` → backtest, walk-forward, Monte Carlo, Deflated Sharpe
17. Pelajari `30-sentiment-analysis-alternative-data.md` → NLP Indonesia, foreign flow, Fear & Greed
18. Pelajari `31-risk-management-lanjutan.md` → VaR/CVaR, stress test, Kelly, drawdown management
19. Pelajari `32-ui-ux-design-trading-app.md` → dashboard, visualization, mobile-first, design system
20. Pelajari `33-cybersecurity-trading-system.md` → API security, encryption, audit, OWASP, UU PDP
21. Pelajari `34-performance-engineering-optimization.md` → DB optimization, caching, async, profiling
22. Pelajari `35-multi-asset-cross-market-analysis.md` → intermarket, lead-lag, spillover, sector rotation
23. Pelajari `36-gap-data-timezone-global-idx.md` → zona waktu, delay data, overnight gap risk
24. Pelajari `37-bahasa-pemrograman-tech-stack.md` → bahasa pemrograman terbaik, tech stack, benchmark
25. Pelajari `38-manajemen-aplikasi-ritel.md` → modul manajemen admin, operasional, kepatuhan
26. Pelajari `39-screening-aiml-pattern-memory.md` → screener, AI/ML pola saham, pattern memory
27. Pelajari `40-oms-ems-architecture.md` → OMS/EMS, order state machine, event sourcing, smart order routing, kill switch
28. Pelajari `41-uu-pdp-compliance-fintech.md` → UU PDP, data subject rights, DPO, breach notification, data localization
29. Pelajari `42-customer-support-dispute-resolution.md` → ticketing, escalation, SLA, AI chatbot guardrails, LAPS-SJK
30. Pelajari `43-mobile-app-architecture.md` → Flutter, offline support, biometric auth, push notification, security mobile
31. Pelajari `44-social-copy-trading.md` → copy trading engine, creator ranking, risk firewall, leaderboard, OJK compliance
32. Pelajari `45-robo-advisor-goal-based-investing.md` → goal-based planning, risk profiling, DCA, round-up, auto-rebalancing
33. Pelajari `46-prediksi-pola-portfolio-pipeline.md` → prediksi masa depan, self-correction, pattern journal, portfolio candidate pipeline
34. Pelajari `47-operational-contract-runbook.md` → operational contract per task (5W1H+Output), RACI, runbook, master schedule, failure handling
35. Pelajari `48-disaster-recovery-business-continuity.md` → DR plan, RTO/RPO, recovery procedures, DR drill
36. Pelajari `49-incident-management-post-mortem.md` → incident lifecycle, blameless post-mortem, action items
37. Pelajari `50-change-release-management-trading.md` → change classification, canary release, feature flags, rollback
38. Pelajari `51-mlops-model-risk-management.md` → model lifecycle, drift detection, champion/challenger, model retirement
39. Pelajari `52-transaction-cost-analysis-execution-quality.md` → TCA metrics, VWAP benchmark, market impact, best execution
40. Pelajari `53-data-governance-lineage.md` → data catalog, lineage, quality SLA, retention policy, stewardship
41. Pelajari `54-trade-surveillance-market-abuse.md` → wash trade, spoofing, front-running detection, compliance log
42. Pelajari `55-capacity-planning-load-stress-testing.md` → capacity limits, load test, stress test, upgrade roadmap
43. Pelajari `56-notification-strategy-alert-fatigue.md` → alert routing, dedup, quiet hours, alert quality metrics
44. Pelajari `57-user-onboarding-journey-design.md` → onboarding flow, risk profile, paper trading gate, progressive disclosure
45. Pelajari `58-feature-store-engineering-pipeline.md` → feature definitions, computation, serving, freshness, reuse
46. Pelajari `59-competitive-analysis-feature-benchmarking.md` → competitor analysis, feature parity, USP, gap analysis
47. Pelajari `60-monetization-business-model.md` → freemium tiers, revenue projections, cost structure, break-even
48. Pelajari `61-accessibility-a11y-trading-app.md` → WCAG 2.1 AA, screen reader, keyboard nav, color-blind charts
49. Pelajari `62-api-versioning-deprecation-policy.md` → URL versioning, backward compat, deprecation timeline, migration
50. Pelajari `63-investasi-syariah-des-screening.md` → DES screening, DSN-MUI, sukuk, Sharia virtual trading, compliance
51. Pelajari `64-fractional-shares-micro-investing.md` → broker pooling, sub-lot accounting, reksadana fractional, reconciliation
52. Pelajari `65-event-driven-event-sourcing.md` → EDA, CQRS, event store, replay, backpressure, multi-exchange normalization
53. Pelajari `66-market-data-distribution.md` → ticker plant, WebSocket, delta encoding, coalescing, tick validation, CDN caching
54. Pelajari `67-llm-agent-layer-self-evolution.md` → 5-agent self-evolution, LLM code generation, TDD cycle, event bus
55. Pelajari `68-sandbox-execution-self-generated-code.md` → process/container isolation, code scanning, mock strategy, security
56. Pelajari `69-knowledge-base-persistent-memory.md` → function registry, lesson store, pattern memory, search & retrieval
57. Pelajari `70-hot-swap-runtime-update.md` → importlib.reload, state preservation, rollback, safety guards
58. Pelajari `71-eval-gated-promotion-ab-testing.md` → 7-layer eval pipeline, A/B testing, statistical significance, falsification
59. Pelajari `72-human-in-the-loop-oversight.md` → approval gate, risk classification, escalation, kill switch, Telegram bot
60. Pelajari `73-self-evolving-ai-roadmap-recommendation.md` → 5-level roadmap, safety boundaries, cost estimation, risk register
61. Pelajari `74-trading-financial-management-capital-operations.md` → kalkulasi modal, buying power, screen→execute, cash flow, PnL engine, trade ledger, reconciliation
62. Pelajari `75-corporate-actions-processing-adjustment.md` → split, dividend, rights issue, price/position/cost basis adjustment, ex-date logic
63. Pelajari `76-idx-trading-rules-market-mechanics.md` → sesi perdagangan, tick size, lot size, ARA/ARB, circuit breaker, margin/short selling
64. Pelajari `77-performance-attribution-benchmark-comparison.md` → Sharpe/Sortino/Calmar, alpha/beta, Brinson attribution, factor attribution
65. Pelajari `78-reporting-export-system.md` → report types, PDF/CSV/Excel export, template engine, scheduled generation, SPT tax report
66. Pelajari `79-education-content-management.md` → learning path, content CMS, glossary, quiz, contextual help
67. Pelajari `80-watchlist-alert-system.md` → multi-watchlist, 15 alert types, notification routing, alert lifecycle
68. Pelajari `81-gamification-engagement-design.md` → XP/level, badge, streak, challenge, leaderboard, anti-overtrading guardrails
69. Pelajari `82-vendor-third-party-integration-management.md` → vendor health, circuit breaker, broker failover, SLA, vendor evaluation
70. Pelajari `83-advisory-system-screening-to-recommendation.md` → screening ke saran lengkap: jenis strategi, jumlah, entry, exit, persentase untung, alasan empiris, eksekusi otomatis
71. Pelajari `84-new-data-arrival-processing-pipeline.md` → pipeline 7 tahap setiap data baru: ingestion → pemeriksaan → testing → screening → penemuan pola → penandaan DB → post-processing
72. Pelajari `85-backtest-to-live-gap-prevention.md` → mengapa backtest menipu, 8 mekanisme anti-gap yang sudah ada, 6 gap yang masih kurang, transition protocol backtest → paper → live
73. Pelajari `86-gigantic-ai-autonomous-trading-system.md` → arsitektur AI otonom: self-awareness, self-reflection, autonomous loop 9-step, runtime code generation, profitability guard 5-layer, path A0→A4

### Untuk Peneliti

1. Dokumen 01-10 berisi referensi ke sumber otoritatif
2. Dokumen 08-09 berisi riset terkini (behavioral finance, ML trading)
3. Dokumen 11 berisi empirical data dari implementasi nyata
4. Dokumen 13-16 berisi praktik, kendala, pelaku, dan strategi profit
5. Dokumen 17 berisi analisis fitur aplikasi retail/pribadi untuk pasar modal
6. Dokumen 18 berisi spesifikasi teknis modul, engine, data, dan checklist implementasi
7. Dokumen 19 berisi flow, logic, testing, aturan aplikasi, KPI, SLA, dan security rules
8. Dokumen 20 berisi analisis mendalam syarat robot/auto trading (12 pilar, arsitektur, checklist, pitfall)
9. Dokumen 21 berisi portfolio optimization (Markowitz, BL, HRP, risk parity, rebalancing)
10. Dokumen 22 berisi data engineering pipeline (ingestion, ETL, storage, quality, Parquet)
11. Dokumen 23 berisi machine learning untuk trading (feature engineering, WFO, HMM, ensemble)
12. Dokumen 24 berisi market microstructure (order book, spread, slippage, IDX specifics)
13. Dokumen 25 berisi pajak & akuntansi trading (PPh final, dividen, SPT, cost basis)
14. Dokumen 26 berisi post-trade processing (settlement, reconciliation, NAV, attribution)
15. Dokumen 27 berisi deployment & DevOps (Docker, CI/CD, monitoring, disaster recovery)
16. Dokumen 28 berisi API design & integration patterns (REST, WebSocket, FIX, event-driven)
17. Dokumen 29 berisi backtesting & strategy validation (walk-forward, Monte Carlo, Deflated Sharpe)
18. Dokumen 30 berisi sentiment analysis & alternative data (NLP Indonesia, foreign flow, Fear & Greed)
19. Dokumen 31 berisi risk management lanjutan (VaR/CVaR, stress test, Kelly, risk parity)
20. Dokumen 32 berisi UI/UX design untuk aplikasi trading (dashboard, visualization, mobile-first)
21. Dokumen 33 berisi cybersecurity trading system (API security, encryption, audit, OWASP)
22. Dokumen 34 berisi performance engineering (DB optimization, caching, async, profiling)
23. Dokumen 35 berisi multi-asset & cross-market analysis (intermarket, lead-lag, spillover)
24. Dokumen 36 berisi gap data, zona waktu & delay (overlap IDX-global, delay per provider, overnight gap)
25. Dokumen 37 berisi bahasa pemrograman & tech stack (Frontend, Middleware, Backend, benchmark, rekomendasi)
26. Dokumen 38 berisi manajemen aplikasi ritel (User, KYC, Konten, Data, Broker, Billing, Compliance, Risk, Ops, Security, Analytics, Backup)
27. Dokumen 39 berisi screening, AI/ML & pattern memory (screener multi-faktor, LSTM, weight dinamis, win-rate historis, feedback loop)
28. Dokumen 40 berisi OMS/EMS architecture (order state machine, event sourcing, smart order routing, kill switch, reconciliation)
29. Dokumen 41 berisi UU PDP compliance untuk fintech (data subject rights, DPO, breach notification, data localization, consent)
30. Dokumen 42 berisi customer support & dispute resolution (ticketing, escalation, SLA, AI chatbot, LAPS-SJK, OJK reporting)
31. Dokumen 43 berisi mobile app architecture (Flutter, offline support, biometric auth, push notification, security mobile)
32. Dokumen 44 berisi social & copy trading (copy engine, creator ranking, risk firewall, leaderboard, OJK compliance, monetization)
33. Dokumen 45 berisi robo-advisor & goal-based investing (goal planning, risk profiling, DCA, round-up, auto-rebalancing, AI advice)
34. Dokumen 46 berisi prediksi, pola & portfolio pipeline (prediction engine fusion, self-correction, pattern journal, portfolio candidate pipeline)
35. Dokumen 47 berisi operational contract & runbook (5W1H+Output, 53 tasks, RACI, runbook, master schedule, failure handling)
36. Dokumen 48 berisi disaster recovery & BCP (RTO/RPO, recovery procedures, backup strategy, DR drill)
37. Dokumen 49 berisi incident management & post-mortem (lifecycle, blameless post-mortem, action items, metrics)
38. Dokumen 50 berisi change & release management (change classification, canary, feature flags, rollback)
39. Dokumen 51 berisi MLOps & model risk (lifecycle, drift detection, champion/challenger, retirement, governance)
40. Dokumen 52 berisi transaction cost analysis (implementation shortfall, VWAP, market impact, best execution)
41. Dokumen 53 berisi data governance & lineage (catalog, lineage, quality SLA, retention, stewardship, PII)
42. Dokumen 54 berisi trade surveillance & market abuse (wash trade, spoofing, front-running, compliance log)
43. Dokumen 55 berisi capacity planning & stress testing (capacity limits, load test, stress test, upgrade roadmap)
44. Dokumen 56 berisi notification strategy & alert fatigue (routing, dedup, quiet hours, quality metrics)
45. Dokumen 57 berisi user onboarding & journey (first-run, risk profile, paper trading gate, progressive disclosure)
46. Dokumen 58 berisi feature store & engineering pipeline (definitions, computation, serving, freshness, reuse)
47. Dokumen 59 berisi competitive analysis & benchmarking (competitor landscape, feature parity, USP, gap analysis)
48. Dokumen 60 berisi monetization & business model (freemium tiers, revenue projections, cost structure, break-even)
49. Dokumen 61 berisi accessibility a11y (WCAG 2.1 AA, screen reader, keyboard nav, color-blind charts)
50. Dokumen 62 berisi API versioning & deprecation (URL versioning, backward compat, deprecation timeline, migration)
51. Dokumen 63 berisi investasi syariah & DES screening (DSN-MUI, sukuk, Sharia virtual trading, compliance OJK)
52. Dokumen 64 berisi fractional shares & micro-investing (broker pooling, sub-lot accounting, reksadana fractional, reconciliation)
53. Dokumen 65 berisi event-driven architecture & event sourcing (CQRS, event store, replay, backpressure, multi-exchange normalization)
54. Dokumen 66 berisi market data distribution (ticker plant, WebSocket, delta encoding, coalescing, tick validation, CDN caching)
55. Dokumen 67 berisi LLM agent layer untuk self-evolution (5-agent architecture, Monitor-Analyzer-Builder-Validator-Integrator, TDD cycle, event bus integration)
56. Dokumen 68 berisi sandbox execution untuk self-generated code (process/container/E2B isolation, resource limits, code scanning, mock strategy, security measures)
57. Dokumen 69 berisi knowledge base persistent memory (function registry, lesson store, pattern memory integration, search & retrieval, reuse tracking)
58. Dokumen 70 berisi hot-swap runtime module update (importlib.reload, state preservation, dependency-aware reload, rollback manager, safety guards)
59. Dokumen 71 berisi eval-gated promotion & A/B testing (7-layer eval pipeline, statistical significance, falsification criteria, champion/challenger pattern)
60. Dokumen 72 berisi human-in-the-loop oversight (approval gate, risk classification, escalation policy, Telegram approval bot, kill switch, audit & compliance)
61. Dokumen 73 berisi self-evolving AI roadmap & rekomendasi (5-level vision L1-L5, current state assessment, roadmap bertahap, safety boundaries, cost estimation, risk register)
62. Dokumen 74 berisi trading financial management & capital operations (kalkulasi modal, buying power, screen→execute pipeline, cash flow manager, capital allocator, PnL engine, trade ledger, NAV, reconciliation, capital efficiency, financial config)
63. Dokumen 75 berisi corporate actions processing & adjustment (split, dividend, rights issue, price/position/cost basis adjustment, ex-date logic, dividend processor, automated pipeline)
64. Dokumen 76 berisi IDX trading rules & market mechanics (sesi perdagangan, fraksi harga, lot size, auto-reject ARA/ARB, circuit breaker IHSG, short selling, margin trading, order validation)
65. Dokumen 77 berisi performance attribution & benchmark comparison (Sharpe/Sortino/Calmar/IR, alpha/beta vs IHSG, Brinson attribution, factor attribution, return decomposition)
66. Dokumen 78 berisi reporting & export system (portfolio summary, monthly/annual statement, tax report SPT, trade log, PDF/CSV/Excel export, Jinja2 template, scheduled generation, OJK/DJP regulatory reporting)
67. Dokumen 79 berisi education & content management (3-level learning path, 15 modul, content CMS, glossary 200+ entries, quiz & assessment, contextual help, tooltip system)
68. Dokumen 80 berisi watchlist & alert system (multi-watchlist, 15 alert types, alert lifecycle, notification routing push/Telegram/email, snooze & recurring, alert history)
69. Dokumen 81 berisi gamification & engagement design (XP & 8-level system, 15 badge, 4 streak types, challenge/quest, leaderboard non-financial, anti-overtrading guardrails, opt-out)
70. Dokumen 82 berisi vendor & third-party integration management (vendor landscape, health check, broker failover, SLA monitoring, per-vendor circuit breaker, fallback strategy, vendor evaluation framework)
71. Dokumen 83 berisi advisory system: screening ke saran eksekusi (data testing, screening, stock personality, strategy classification, position sizing, entry timing, exit rules, expected profit, 6-factor scores, XAI narrative, backtest evidence, VaR, auto-execution dengan condition check, post-execution monitoring)
72. Dokumen 84 berisi new data arrival processing pipeline: 7 tahap setiap data baru masuk (ingestion, pemeriksaan data lengkap 8 quality checks, testing & validasi, screening, penemuan pola, penandaan & labeling ke database, post-processing trigger), daily runner implementation, real-time pipeline roadmap
73. Dokumen 85 berisi backtest-to-live gap prevention: 7 root causes (look-ahead, survivorship, overfitting, unrealistic costs, market impact, regime change, behavioral gap), 8 mekanisme yang sudah ada (next-bar-open, survivorship-free, walk-forward, realistic costs, regime filter, auto-execution, circuit breaker, paper trading), 6 gap yang masih kurang (WFA mandatory, paper-vs-backtest comparison, conservative slippage, faster regime detection, live degradation alert, mandatory paper period), transition protocol 6 step (backtest → WFA → paper 30 hari → live small → scale up → full), stop conditions, continuous validation loop
74. Dokumen 86 berisi gigantic AI autonomous trading system: self-awareness layer (8 state: market/portfolio/performance/model/data/strategy/self/risk), self-reflection (5 pertanyaan: Am I profitable? Am I degrading? Is my model stale? Am I within risk limits? Are my self-improvements working?), autonomous decision loop 9-step (observe → analyze → reflect → decide → validate → execute → monitor → learn → evolve), runtime code generation dengan 7-layer validation + accountability, profitability guarantee 5-layer (strategy validation → pre-execution risk → post-execution monitoring → self-correction → circuit breaker), 7-layer architecture stack (Layer 0 infrastructure → Layer 1 data → Layer 2 AI/ML → Layer 3 analysis → Layer 4 decision → Layer 5 self-awareness → Layer 6 self-evolution), 5 autonomy levels (A0 manual → A4 fully autonomous), path to full autonomy 24 bulan, perbedaan gigantic AI vs AGI (operational self-awareness bukan philosophical consciousness)
75. Dokumen 87 berisi perkembangan regulasi pasar modal 2026: timeline 2026, POJK No. 3/2026 (Perusahaan Efek — PEKU 1/2/3, permodalan minimum), POJK No. 5/2026 (Manajer Investasi — MIKU 1/2, dana kelolaan minimum), OJK 8 rencana aksi reformasi (free float 15%, UBO transparansi, demutualisasi BEI, enforcement, tata kelola emiten), BEI PPK/FCA reformasi (hapus 3 kriteria teknis, auto-reject berjenjang 4 kelompok harga, Non-Cancellation Period), implikasi untuk aplikasi trading, update konfigurasi, testing
76. Dokumen 88 berisi gap analysis teori vs praktek: audit komparatif antara 88 dokumen pustaka (teori) vs trading-system v0.1.11 (kode aktual), 25+ gap teridentifikasi across frontend (1 dari 7 halaman), OMS (belum dibangun), broker integration (mock only), market data real-time (EOD only), infrastructure (no Redis/DR), security (API key only), AI/ML (DSR missing), testing (KPI tidak otomatis), rencana penutupan gap dengan 8 roadmap dan prioritas timeline
77. Dokumen 89 berisi faktor pasar modal analisis implementasi: audit komprehensif 22 faktor yang mempengaruhi pasar modal IDX (fundamental, teknikal, makro, global, sentimen, relasi, regime, corporate actions, mikrostruktur, behavioral, regulasi, geopolitik, seasonal, komoditas spesifik, sector rotation, insider trading, IPO timing, earnings season, commodity supercycle, tax-loss selling, index inclusion, QE/QT, retail participation), 13 faktor tercakup dan terimplementasi, 5 sebagian, 9 belum dibahas, cara menggunakan data per faktor, implementasi di trading-system, gap prioritas (komoditas spesifik IDX sebagai gap paling kritis — 35% market cap tidak tracked), rekomendasi update pustaka
78. Dokumen 90 berisi analisis parquet data awal: struktur direktori `/media/petrick/Parquet/trading_data` (raw 1024 items + archive 6 subdirs), 28 tabel archive/tables siap pakai, 53 raw subdirs data legacy, 77 tabel sqlite_backup (72.1MB) yang jauh lebih lengkap (212K sentiment rows, 50K news, 871K technical indicators, 122K fundamental snapshots, 7,495 shareholders, 1,523 commodity prices), 9 data berharga belum di-migrate (commodity, sentiment history, social media, shareholders, quarterly earnings, valuation, saham snapshot, pattern reliability, news history), masalah schema (kolom Bahasa Indonesia, duplikasi data, stale data, format UUID), 8 schema SQL baru untuk migration, commodity-to-stock mapping (CPO→AALI/LSIP/SIMP, coal→PTBA/ITMG/ADRO, nickel→INCO/ANTM/MDKA), rekomendasi quick wins (migrate commodity + sentiment + shareholders dalam 1-2 minggu)
79. Dokumen 91 berisi komoditas spesifik IDX: dokumen khusus hubungan harga komoditas dan saham emiten di IDX, mengapa komoditas penting (35% market cap IDX commodity-dependent), mapping lengkap 10 komoditas ke emiten (CPO→AALI/LSIP/SIMP/DSNG/ANJT, batubara→ADRO/PTBA/ITMG/HRUM, nikel→INCO/ANTM/MDKA, tembaga→ANTM/MDKA, emas→ANTM/MDKA, timah→TINS, gas→PGAS, oil→MEDC/ENRG/BULL), mekanisme transmisi (harga komoditas → revenue → earnings → saham), time lag 1-5 hari, faktor driver per komoditas (CPO: produksi Indonesia/Malaysia, demand India/China, biodiesel mandate, El Nino; batubara: demand China/India, DMO policy; nikel: EV battery, export ban; tembaga: global GDP, China property; emas: real interest rate, DXY, geopolitik), cara analisis dan scoring, strategi sebagai faktor tambahan/konfirmasi/risk flag/input macro, roadmap implementasi 6-8 hari (migrate data + mapping + score engine + integrate decision), data source yfinance untuk update forward, komoditas-to-stock beta
80. Dokumen 96 berisi AI/ML audit framework: 4 pilar audit komprehensif untuk mengevaluasi apakah model AI/ML memberikan Alpha atau overfitting — Pilar 1 Model Performance Metrics (Sharpe, Sortino, MaxDD, Information Ratio, Win Rate, IC, Brier Score, Precision@K), Pilar 2 Ablation Study (With AI vs Without AI vs Baseline teknikal vs Random, Delta Alpha per komponen, paired t-test, Diebold-Mariano), Pilar 3 Latency & Cost-Benefit (end-to-end latency profiling, break-even AUM, benefit/cost ratio per komponen), Pilar 4 Feature Importance & Drift (PSI, KS test, model decay indicators, regime shift detection), AI Utility Score Card 7 kriteria weighted 0-5, per-komponen verdict matrix, checklist audit taktis 7 step, script `scripts/audit_ai_utility.py`
81. Dokumen 97 berisi strategi alternatif & ekspansi data 2026: analisis 7 area pengembangan untuk mengatasi prediction accuracy 40-43% — Poin 1 pairs trading (statarb cointegration IDX, Sharpe 1.67 LSTM vs 0.69 traditional, pasangan AKRA-BMRI/BTPN-PWON/BDMN-MIKA), Poin 2 volume features (OFI proxy, VWAP, OBV divergence, foreign flow 1.25M rows belum terhubung), Poin 3 policy event scorer (BI rate cut +30 impact, policy_events 179 rows belum di-consume), Poin 4 data satelit proxy gratis (BPS API/BI SEKI/NOAA ONI/World Bank, satellite imagery defer), Poin 5 meta-labeling (Lopez de Prado triple-barrier + CUSUM + purged walk-forward, fix accuracy via secondary ML model), Poin 6 GitHub repos (vectorbt 8.568 stars, mlfinlab, StatArb-Research, regime-switching-portfolio), Poin 7 dynamic GPU/CPU dispatch (select_device per workload type, VRAM check 4GB GTX 1050 Ti), 7 modul baru dibuat (meta_labeling, pairs_trading, volume_features, policy_event_scorer, macro_data_fetcher, sector_rotation, compute/device), 17 sumber riset 2025-2026
82. Dokumen 98 berisi migrasi SQLite → PostgreSQL: schema "Domino Effect" dengan TIMESTAMPTZ, partitioning stock_prices by month, JSONB untuk event metadata, GiST range index untuk market_sessions, view v_domino_timeline (6 event types dalam satu UTC timeline), backfill broker_transactions dari OHLCV volume + broker list, multi-DB support di kode aplikasi (config database_url, db.raw helper, engine auto-select), connection string PostgreSQL 16 localhost:5432
83. Dokumen 99 berisi matriks relevansi data satelit vs pasar modal: 9 sumber data satelit gratis (NASA POWER, Sentinel-2, VIIRS, Sentinel-1 SAR, AIS, Umbra, MODIS, Landsat, Forest Data Partnership), matriks relevansi 16 pasangan data-satelit vs ticker/komoditas, 6 studi pendukung, prioritas implementasi pipeline
84. Dokumen 100 berisi Astronacci time cycle integration: metodologi Astronacci (Astrology + Fibonacci) sebagai indikator "WHEN" — tabel astronacci_cycles (14,073 rows, 1927–2026), 3 elemen astrologi (Moon Phase 4,879 rows, Retrograde 8 planet 1,203 rows, Ingress Sun+8 planet 4,873 rows) + Fibonacci Time Windows (3,118 rows dari IHSG swing points), module src/market/analysis/astronacci.py dengan PyEphem, integrasi ke SignalEnhancer (signal ke-8, weight 6%) dan MarketContext (weight 3%), backfill script scripts/backfill_astronacci.py, 32 tests

---

## Sumber Pengetahuan

### Riset Internet
- OJK, BEI/IDX, SEC, FCA, ESMA — regulator dan bursa
- Investopedia, CFA Institute, IMF — referensi keuangan
- arxiv.org — riset akademik (market microstructure, ML trading)
- Statista, WFE — statistik pasar global

### Pengalaman Nyata
- Proyek `trading-system` v0.1.11 — **implementasi nyata yang pernah dibangun dan dijalankan**
- **Lokasi source code:** `/home/petrick/projects/global`
- 951 tickers aktif (928 equity + 23 non-equity), ~2.9M rows OHLCV, 39 tabel SQLite
- 88 API endpoints (86 REST + 2 WebSocket), 750+ unit tests across 51 test files
- Bug produksi dan solusi yang terdokumentasi
- **Catatan:** Kode dari proyek tersebut dapat diadopsi/dicopy sebagian atau seluruhnya ke aplikasi baru. Lihat `11-knowledge-transfer-aplikasi.md` untuk detail pola, pelajaran, dan modul yang dapat direuse.

### Dokumen Existing
- `docs/KNOWLEDGE_TRANSFER.md` — diadaptasi ke `11-knowledge-transfer-aplikasi.md`
- **Source code proyek:** `/home/petrick/projects/global` — tersedia untuk diadopsi/dicopy

---

## Statistik

- **Total konten:** ~75000+ baris pengetahuan terstruktur
- **Topik mencakup:** 103 area pengetahuan pasar modal (00-README + 01-102)
- **Kode contoh:** Python (pandas, numpy, scikit-learn, FastAPI)
- **Bahasa:** Indonesia (utama) dengan istilah teknis Inggris
- **Update terbaru:** Lifecycle environment real/testing/AI, multi-market & multi-asset trading system, reformasi regulasi 2026 (UU P2SK, POJK 3/5, JATS MME), concurrency patterns, stale data detection, Deflated Sharpe Ratio, gap analysis teori vs praktek, audit faktor pasar modal, analisis parquet data awal, komoditas spesifik IDX, geopolitik & event shock, seasonal & kalender, AI/ML audit framework, strategi alternatif & ekspansi data 2026, sync DB→Parquet, migrasi SQLite→PostgreSQL, matriks relevansi satelit, Astronacci time cycle integration

---

> Dibuat: Agustus 2026 | Repository: `<PROJECT_DIR>/pustaka/` (Linux: `/opt/lampp/htdocs/market/pustaka/`, Windows: `C:\xampp\htdocs\market\pustaka\`)
>
> **Catatan:** Aplikasi `trading-system` v0.1.11 telah pernah diimplementasikan dan dijalankan di `/home/petrick/projects/global`. Kode, arsitektur, dan pelajaran dari proyek tersebut dapat diadopsi atau dicopy ke aplikasi baru. Pustaka ini berfungsi sebagai dokumentasi referensi sekaligus panduan adopsi.
>
> **Konfigurasi AI:** Lihat `../.devin/` untuk rules, skills, dan workflow yang memandu Devin/Cascade saat bekerja pada pustaka ini. Lihat juga memory sistem untuk konteks persisten antar-sesi.
