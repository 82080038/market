# Roadmap & Rekomendasi: Dari Trading System ke Self-Evolving AI

> **Dokumen 73** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Roadmap bertahap untuk mengubah aplikasi trading yang dijelaskan di pustaka menjadi self-evolving AI yang dapat membangun, memperbaiki, dan memperbaharui dirinya sendiri — lengkap dengan timeline, prioritas, safety boundary, dan rekomendasi implementasi.
>
> **Konteks:** Dokumen 67-72 mendefinisikan 6 komponen yang harus ditambahkan: LLM Agent Layer, Sandbox Execution, Knowledge Base, Hot-Swap Mechanism, Eval-Gated Promotion, dan Human-in-the-Loop. Dokumen ini menyatukan semuanya menjadi roadmap yang dapat dieksekusi.

---

## Daftar Isi

1. [Vision: 5 Level Self-Evolution](#1-vision-5-level-self-evolution)
2. [Current State Assessment](#2-current-state-assessment)
3. [Roadmap L1: Self-Updating](#3-roadmap-l1-self-updating)
4. [Roadmap L2: Self-Repairing](#4-roadmap-l2-self-repairing)
5. [Roadmap L3: Self-Extending](#5-roadmap-l3-self-extending)
6. [Roadmap L4: Self-Building](#6-roadmap-l4-self-building)
7. [Safety Boundaries](#7-safety-boundaries)
8. [Rekomendasi Implementasi](#8-rekomendasi-implementasi)
9. [Cost & Resource Estimation](#9-cost--resource-estimation)
10. [Risk Register](#10-risk-register)

---

## 1. Vision: 5 Level Self-Evolution

```
L5: FULLY AUTONOMOUS          ← Sci-fi (? tahun)
     │ Self-evolution tanpa human intervention
     │
L4: SELF-BUILDING             ← Research (12-24 bulan)
     │ Auto-generate strategy, auto-rewrite algorithm
     │
L3: SELF-EXTENDING            ← Advanced (6-12 bulan)
     │ Auto-add data source, auto-create indicator
     │
L2: SELF-REPAIRING            ← Intermediate (3-6 bulan)
     │ Auto-failover, auto-fix adapter, auto-rollback
     │
L1: SELF-UPDATING             ← Foundation (2-3 bulan)
     │ Auto-retrain, auto-adjust weight, auto-promote model
     │
L0: MANUAL                    ← Current state
       Human-driven semua: fetch, compute, deploy
```

### 1.1 Kapabilitas per Level

| Kapabilitas | L0 | L1 | L2 | L3 | L4 | L5 |
|-------------|----|----|----|----|----|----|
| Auto-retrain model | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auto-adjust weights | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auto-promote model | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auto-failover data source | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Auto-fix broken adapter | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Auto-rollback bad state | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Auto-add new data source | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Auto-create new indicator | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Auto-generate new strategy | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Auto-rewrite algorithm | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Human-free evolution | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 2. Current State Assessment

### 2.1 Yang SUDAH Ada (dari pustaka 18, 39, 46, 51)

| Komponen | Status | Dokumen |
|----------|--------|---------|
| AI Learning Engine (weight optimization) | ✅ Ready | 18, 39 |
| Regime-specific weights (5 regimes) | ✅ Ready | 39 |
| Walk-Forward Validator | ✅ Ready | 23, 29 |
| Purged TSS | ✅ Ready | 23 |
| Model Registry (versioned) | ✅ Ready | 51 |
| Deep Learning (LSTM, GPU) | ✅ Ready | 23, 39 |
| Ensemble | ✅ Ready | 23 |
| Monitoring Engine | ✅ Ready | 18 |
| AdaptiveRateLimiter (circuit breaker) | ✅ Ready | 18 |
| Backtest Engine (15 metrics) | ✅ Ready | 29 |
| XAI Engine (narrative) | ✅ Ready | 18 |
| Audit Trail (immutable) | ✅ Ready | 18 |
| Event Bus | ✅ Ready | 18, 65 |
| Self-Correction (Error Analysis) | ✅ Ready | 46 |
| Pattern Memory | ✅ Ready | 39 |

### 2.2 Yang BELUM Ada (dokumen 67-72)

| Komponen | Status | Dokumen |
|----------|--------|---------|
| LLM Agent Layer (5 agents) | ❌ New | 67 |
| Sandbox Execution | ❌ New | 68 |
| Knowledge Base (persistent) | ❌ New | 69 |
| Hot-Swap Mechanism | ❌ New | 70 |
| Eval-Gated Promotion (A/B test) | ❌ New | 71 |
| Human-in-the-Loop (approval gate) | ❌ New | 72 |

### 2.3 Readiness Score

| Level | Komponen Ready | Komponen Needed | Readiness |
|-------|---------------|-----------------|-----------|
| L1 | 8/10 | Scheduled retrain, drift detection | **80%** |
| L2 | 4/10 | Auto-failover, self-healing, auto-rollback | **40%** |
| L3 | 2/10 | LLM agents, sandbox, KB, hot-swap, eval-gate | **20%** |
| L4 | 1/10 | LLM code generation, full pipeline | **10%** |
| L5 | 0/10 | Full autonomy | **0%** |

---

## 3. Roadmap L1: Self-Updating (2-3 Bulan)

### 3.1 Tujuan

Sistem dapat **memperbaharui model dan parameter** secara otomatis tanpa human intervention.

### 3.2 Tasks

| # | Task | Priority | Estimasi | Dependencies |
|---|------|----------|----------|--------------|
| 1 | Scheduled retrain LSTM (weekly cron) | High | 3 hari | Existing LSTM |
| 2 | Drift detection integration (PSI > 0.25 → trigger retrain) | High | 3 hari | Existing monitoring |
| 3 | Auto-promote model dari staging → production | High | 2 hari | Existing model registry |
| 4 | Regime auto-detection (HMM) terintegrasi penuh | Medium | 5 hari | Existing enhanced_regime |
| 5 | Weight auto-adjustment schedule (daily, not just on-demand) | Medium | 2 hari | Existing AI Learning Engine |
| 6 | Telegram notification untuk setiap auto-update | Low | 1 hari | Existing telegram notifier |
| 7 | Post-update monitoring (track performance 7 hari post-update) | Medium | 3 hari | Existing monitoring |

### 3.3 Deliverables

- Cron job: `weekly_retrain.py` — retrain LSTM untuk top 50 tickers
- Cron job: `daily_weight_adjust.py` — run AI Learning Engine untuk adjust weights
- Drift detector: `drift_detector.py` — PSI check untuk feature distribution
- Auto-promote: `auto_promote.py` — promote staging model jika Sharpe > production
- Monitoring: post-update performance tracking di `monitoring/engine.py`

### 3.4 Success Criteria

- [ ] LSTM retrain berjalan otomatis setiap minggu tanpa manual intervention
- [ ] Drift detection trigger retrain ketika PSI > 0.25
- [ ] Model staging → production promotion otomatis jika walk-forward pass
- [ ] Weight adjustment harian berjalan dan tercatat di audit log
- [ ] Telegram notification terkirim untuk setiap update

---

## 4. Roadmap L2: Self-Repairing (3-6 Bulan)

### 4.1 Tujuan

Sistem dapat **mendegradasi dengan graceful** dan **memperbaiki diri** ketika komponen gagal.

### 4.2 Tasks

| # | Task | Priority | Estimasi | Dependencies |
|---|------|----------|----------|--------------|
| 1 | Auto-failover data source (Yahoo → IDX scraper → Parquet cache) | High | 5 hari | Existing circuit breaker |
| 2 | Self-healing schema (auto-detect drift, auto-generate migration) | High | 7 hari | Existing Alembic |
| 3 | Auto-retry dengan strategi berbeda (proxy, parser, period) | Medium | 4 hari | Existing rate limiter |
| 4 | Auto-rollback (snapshot state, restore on error) | High | 5 hari | Dokumen 70 (hot-swap) |
| 5 | Health check post-repair (verify fix worked) | Medium | 3 hari | Existing monitoring |
| 6 | Escalation ke human jika auto-repair gagal (3 attempts) | Medium | 2 hari | Dokumen 72 |
| 7 | Telegram alert untuk setiap auto-repair event | Low | 1 hari | Existing telegram |

### 4.3 Deliverables

- `auto_failover.py` — switch sumber data otomatis
- `self_healing_schema.py` — detect dan migrate schema drift
- `auto_rollback.py` — snapshot + restore mechanism
- `health_checker.py` — post-repair verification
- Integrasi dengan `AdaptiveRateLimiter` dan `MonitoringEngine`

### 4.4 Success Criteria

- [ ] Yahoo Finance down → auto-switch ke IDX scraper → alert Telegram
- [ ] Schema drift terdeteksi → auto-generate Alembic migration → auto-apply
- [ ] Adapter error → auto-retry dengan strategi berbeda → success atau escalate
- [ ] Bad state terdeteksi → auto-rollback ke snapshot → verify → alert
- [ ] 3 consecutive auto-repair failures → escalate ke human

---

## 5. Roadmap L3: Self-Extending (6-12 Bulan)

### 5.1 Tujuan

Sistem dapat **menambah kapabilitas baru** (data source, indicator, screener) secara otomatis.

### 5.2 Tasks

| # | Task | Priority | Estimasi | Dependencies |
|---|------|----------|----------|--------------|
| 1 | Implement LLM Agent Layer (5 agents: Monitor, Analyzer, Builder, Validator, Integrator) | Critical | 15 hari | Dokumen 67 |
| 2 | Implement Sandbox Execution (L1 process + L2 container) | Critical | 10 hari | Dokumen 68 |
| 3 | Implement Knowledge Base (function registry + lesson store) | High | 8 hari | Dokumen 69 |
| 4 | Implement Hot-Swap Mechanism (importlib + rollback) | High | 7 hari | Dokumen 70 |
| 5 | Implement Eval-Gated Promotion (A/B test + falsification) | High | 10 hari | Dokumen 71 |
| 6 | Implement Human-in-the-Loop (approval gate + Telegram) | High | 5 hari | Dokumen 72 |
| 7 | LLM client abstraction (OpenAI/Anthropic/local) | Medium | 3 hari | Dokumen 67 |
| 8 | Orchestrator (koordinasi 5-agent loop) | High | 5 hari | Tasks 1-6 |
| 9 | E2E test: trigger → analyze → build → validate → integrate | High | 5 hari | Tasks 1-8 |
| 10 | Dashboard: self-evolution status, pending approvals, KB stats | Low | 5 hari | Tasks 1-9 |

### 5.3 Deliverables

```
src/trading_system/self_evolution/
├── __init__.py
├── orchestrator.py              # Koordinasi 5-agent loop
├── monitor_agent.py             # Deteksi anomaly
├── analyzer_agent.py            # Root cause analysis via LLM
├── builder_agent.py             # Code generation via LLM
├── validator_agent.py           # 7-layer validation
├── integrator_agent.py          # Hot-swap + KB update
├── llm_client.py                # LLM abstraction
├── prompts/                     # Prompt templates
├── sandbox/                     # Sandbox execution
│   ├── process_sandbox.py
│   ├── container_sandbox.py
│   ├── code_scanner.py
│   └── factory.py
├── knowledge_base/              # Persistent memory
│   ├── store.py
│   ├── search.py
│   ├── bridge.py
│   └── models.py
├── hot_swap/                    # Runtime update
│   ├── reloader.py
│   ├── state_manager.py
│   ├── rollback_manager.py
│   ├── safety_guards.py
│   └── dependency_resolver.py
├── eval_gated/                  # A/B testing
│   ├── ab_test.py
│   ├── bootstrap.py
│   ├── falsification.py
│   ├── pipeline.py
│   └── champion.py
└── human_loop/                  # Human oversight
    ├── approval_gate.py
    ├── risk_classifier.py
    ├── escalation.py
    ├── notifications.py
    ├── kill_switch.py
    ├── telegram_handler.py
    └── audit.py
```

### 5.4 Success Criteria

- [ ] Monitor deteksi anomaly → Analyzer identifikasi cause → Builder generate fix
- [ ] Generated code lulus 7-layer validation (unit, integration, backtest, walk-forward, A/B, falsification, code quality)
- [ ] Validated code di-hot-swap ke production tanpa restart
- [ ] Knowledge base menyimpan dan me-reuse solusi
- [ ] Human approval gate bekerja untuk high-risk changes
- [ ] Kill switch dapat menghentikan self-evolution kapan saja
- [ ] Telegram notification untuk setiap event

---

## 6. Roadmap L4: Self-Building (12-24 Bulan)

### 6.1 Tujuan

Sistem dapat **menulis ulang algoritma** dan **menciptakan strategi baru** secara otomatis.

### 6.2 Tasks

| # | Task | Priority | Estimasi | Dependencies |
|---|------|----------|----------|--------------|
| 1 | Strategy ideation via LLM ( Analyzer propose new strategies) | Critical | 10 hari | L3 complete |
| 2 | Auto-generate strategy code (Builder write full strategy) | Critical | 15 hari | L3 complete |
| 3 | Auto-generate backtest config (Builder write backtest setup) | High | 5 hari | L3 complete |
| 4 | Multi-strategy ensemble auto-creation | Medium | 10 hari | Tasks 1-3 |
| 5 | Auto-rewrite scoring algorithm (Builder rewrite decision engine) | High | 15 hari | L3 complete |
| 6 | Auto-optimize hyperparameter (Builder suggest architecture change) | Medium | 10 hari | L3 complete |
| 7 | Cross-market strategy transfer (learn from IDX → apply to other markets) | Low | 15 hari | Tasks 1-6 |
| 8 | Continuous evolution loop (run 24/7 dengan eval-gated improvement) | High | 7 hari | Tasks 1-7 |

### 6.3 Success Criteria

- [ ] Sistem mengusulkan strategi baru berdasarkan pattern discovery
- [ ] Strategi di-generate, di-test (5 tahun backtest + walk-forward), dan di-promote
- [ ] Sistem dapat rewrite scoring algorithm dan prove improvement via A/B test
- [ ] Evolution loop berjalan 24/7 dengan improvement terukur per cycle
- [ ] Semua perubahan high-risk melalui human approval gate

---

## 7. Safety Boundaries

### 7.1 Yang TIDAK BOLEH di-Modify oleh AI

| Komponen | Alasan | Protection |
|----------|--------|------------|
| **Risk limits** (drawdown, position size, daily loss) | Financial safety | Hardcoded + env vars |
| **Compliance rules** (OJK, BEI, UU PDP) | Regulatory | Human-defined, immutable |
| **Audit trail** | Traceability | Append-only, no AI write |
| **API keys & secrets** | Security | .env, no AI access |
| **Kill switch mechanism** | Safety | AI tidak bisa deactivate |
| **Approval gate logic** | Safety | AI tidak bisa bypass |
| **Database schema (core tables)** | Data integrity | Migration only via human approval |
| **Broker connection** | Financial safety | Tidak di-hot-swap |

### 7.2 Yang BOLEH di-Modify oleh AI

| Komponen | Risk Level | Approval |
|----------|------------|----------|
| Data adapters (fetch, parse) | Low | Auto-promote |
| Indicator calculations | Medium | Notify + auto |
| Screener logic | Low | Auto-promote |
| Pattern detection algorithms | Medium | Notify + auto |
| Sentiment analysis logic | Medium | Notify + auto |
| Strategy implementations | High | Human approval |
| Model architecture (LSTM config) | Medium | Notify + auto |
| Factor weights | High | Human approval |
| Risk calculation formulas | Critical | Human approval + confirm |

### 7.3 Safety Checkpoints

```
Before Build:
    └── Code scanner (AST + regex) — block dangerous patterns

After Build:
    └── Sandbox execution — isolated test

After Validate:
    └── Eval-gated promotion — A/B test + falsification

Before Integrate:
    └── Risk classification — determine approval level

After Integrate:
    └── Health check — verify swap succeeded
    └── Post-promotion monitoring — track for regression

Anytime:
    └── Kill switch — human can stop everything
    └── Escalation — auto-escalate on repeated failures
```

---

## 8. Rekomendasi Implementasi

### 8.1 Urutan Implementasi

```
BULAN 1-2: L1 Self-Updating
    └── Maximum value, minimum risk
    └── Gunakan existing components (AI Learning Engine, Model Registry)
    └── ROI: otomatisasi retrain + weight adjustment

BULAN 3-5: L2 Self-Repairing
    └── Auto-failover + auto-rollback
    └── Build trust in autonomous operation
    └── ROI: reduced downtime, faster recovery

BULAN 6-11: L3 Self-Extending
    └── Build LLM Agent Layer + Sandbox + KB + Hot-Swap + Eval-Gate + HITL
    └── Mulai dengan low-risk changes (adapter fix, new indicator)
    └── ROI: auto-add capabilities, reduce manual coding

BULAN 12-23: L4 Self-Building
    └── Strategy generation + algorithm rewrite
    └── Mulai dengan human approval untuk semua changes
    └── Gradually reduce approval requirements seiring trust builds
    └── ROI: continuous improvement, alpha discovery
```

### 8.2 Rekomendasi Teknis

1. **Mulai dengan LLM murah** — Gunakan local LLM (Ollama, vLLM) atau model murah (GPT-4o-mini) untuk iterasi awal. Upgrade ke model lebih baik (Claude Sonnet, GPT-4o) setelah pipeline stabil.

2. **TDD dari hari pertama** — Setiap generated code wajib punya test. Ini bukan opsional. Tanpa TDD, self-evolution akan menghasilkan bug yang tidak terdeteksi.

3. **Sandbox dulu, production nanti** — Jangan pernah eksekusi generated code di production tanpa sandbox. L1 (process) sandbox cukup untuk awal.

4. **Audit trail immutable** — Setiap self-modification tercatat permanen. Ini bukan opsional. Tanpa audit trail, tidak ada traceability.

5. **Telegram sebagai primary interface** — Human-in-the-loop via Telegram adalah paling praktis untuk single-user app. Approval, rejection, kill switch — semua dari phone.

6. **Cost tracking dari awal** — LLM API calls bisa mahal. Track cost per agent, per trigger, per cycle. Set budget harian/bulanan.

7. **Start small, scale gradually** — Mulai dengan 1 trigger type (misal: source_down). Setelah berhasil, tambah trigger type lain. Jangan aktifkan semua sekaligus.

8. **Human approval untuk semua di awal** — Meskipun risk level low, require approval untuk 100 cycles pertama. Setelah trust terbangun, gradually enable auto-promote untuk low-risk.

### 8.3 Rekomendasi Organisasional

1. **Review self-evolution log mingguan** — Setiap minggu, review apa yang diubah, apa yang berhasil, apa yang gagal.

2. **Post-mortem untuk setiap rollback** — Setiap rollback adalah lesson. Document dan simpan ke knowledge base.

3. **Drill kill switch monthly** — Test kill switch setiap bulan untuk memastikan bekerja.

4. **Budget untuk LLM API** — Sisihkan $50-200/bulan untuk LLM API calls (tergantung intensitas evolution).

5. **Backup sebelum setiap cycle** — Walaupun ada auto-rollback, manual backup database sebelum setiap evolution cycle.

---

## 9. Cost & Resource Estimation

### 9.1 Development Cost

| Level | Waktu | Effort | LLM API Cost (dev) |
|-------|-------|--------|---------------------|
| L1 | 2-3 bulan | 20 hari × 4 jam | $0 (no LLM needed) |
| L2 | 3-6 bulan | 27 hari × 4 jam | $0 (no LLM needed) |
| L3 | 6-12 bulan | 73 hari × 6 jam | $200-500 (LLM testing) |
| L4 | 12-24 bulan | 87 hari × 6 jam | $500-2000 (LLM production) |

### 9.2 Operational Cost (per bulan)

| Komponen | Cost | Catatan |
|----------|------|---------|
| LLM API (GPT-4o) | $50-150 | Tergantung frequency evolution cycle |
| LLM API (Claude Sonnet) | $30-100 | Alternative |
| Local LLM (Ollama) | $0 | GPU 1 untuk inference, no API cost |
| Telegram Bot | $0 | Free |
| Docker (sandbox) | $0 | Local |
| E2B (cloud sandbox) | $10-30 | Optional, untuk L2 isolation |
| **Total** | **$0-200/bulan** | Tergantung pilihan LLM |

### 9.3 GPU Usage

| Task | GPU | VRAM | Duration |
|------|-----|------|----------|
| LSTM retrain (L1) | cuda:1 | ~1.5 GB | 30 menit/ticker |
| Walk-forward (L3) | cuda:1 | ~1.5 GB | 2 jam/run |
| Local LLM inference (L3+) | cuda:1 | ~3 GB | Continuous |
| Sandbox test (L3+) | cuda:1 | ~0.5 GB | Per test run |

> **Catatan:** GTX 1050 Ti punya 4 GB VRAM. Local LLM (7B parameter) butuh ~3 GB. Bisa berjalan tapi terbatas pada model kecil. Untuk model lebih besar, gunakan API.

---

## 10. Risk Register

| Risk | Probability | Impact | Mitigasi |
|------|-------------|--------|----------|
| **LLM hallucination** — generate code yang salah | Tinggi | Tinggi | TDD + sandbox + eval-gated |
| **Overfitting ke historical data** | Sedang | Tinggi | Walk-forward + purged TSS + falsification |
| **Cascading failure** — fix introduce new bug | Sedang | Tinggi | Snapshot + rollback + post-promotion monitoring |
| **LLM API cost overrun** | Sedang | Sedang | Cost tracking + budget limit + local LLM fallback |
| **Security vulnerability** — generated code | Rendah | Critical | Code scanner + sandbox + SAST (bandit) |
| **Regulatory violation** — auto-generated strategy | Rendah | Critical | Human approval untuk strategi + compliance check |
| **Data corruption** — bad migration | Rendah | Tinggi | Auto-rollback + DB backup + snapshot |
| **Loss of trust** — terlalu banyak rollback | Sedang | Sedang | Gradual rollout + start with low-risk changes |
| **Complexity explosion** — sistem terlalu kompleks | Sedang | Sedang | XAI + audit trail + documentation |
| **Kill switch tidak bekerja** | Rendah | Critical | Monthly drill + multiple activation methods |

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| LLM Agent Layer | `67-llm-agent-layer-self-evolution.md` |
| Sandbox execution | `68-sandbox-execution-self-generated-code.md` |
| Knowledge base | `69-knowledge-base-persistent-memory.md` |
| Hot-swap mechanism | `70-hot-swap-runtime-update.md` |
| Eval-gated promotion | `71-eval-gated-promotion-ab-testing.md` |
| Human-in-the-loop | `72-human-in-the-loop-oversight.md` |
| AI Learning Engine | `39-screening-aiml-pattern-memory.md` |
| MLOps & model registry | `51-mlops-model-risk-management.md` |
| Prediksi & self-correction | `46-prediksi-pola-portfolio-pipeline.md` |
| Modular architecture | `18-modul-engine-data-wajib.md` |
| Machine learning trading | `23-machine-learning-trading.md` |
| Backtesting & validation | `29-backtesting-strategy-validation.md` |
| Change & release management | `50-change-release-management-trading.md` |
| Deployment & DevOps | `27-deployment-devops-trading.md` |
| GPU/CUDA | `34-performance-engineering-optimization.md` bagian 13 |
| Capacity planning | `55-capacity-planning-load-stress-testing.md` |
| Gigantic AI architecture | `86-gigantic-ai-autonomous-trading-system.md` |
| Backtest-to-live gap | `85-backtest-to-live-gap-prevention.md` |

---

## Referensi Eksternal

1. **SelfEvolve** — Runtime self-extension, Pass@1: 92.7% (arxiv.org/abs/2604.16314, 2026)
2. **Darwin Gödel Machine** — Self-improving coding agents, SWE-bench: 20% → 50% (arxiv.org/abs/2505.22954, 2025) — "safety precautions: sandboxing, human oversight"
3. **SEMAG** — Self-evolutionary multi-agent, HumanEval: 98.8% (arxiv.org/abs/2603.15707, 2026)
4. **AHE** — Eval-gated evolution, Terminal-Bench: 69.7% → 77.0% in 10 iterations (arxiv.org/abs/2604.25850, 2026) — "evolved components encode general engineering experience"
5. **AutoDev** — Autonomous portfolio agent with eval-gated meta-reviewer (github.com/RitikPatill/autodev, 2026) — "prompts sharpen over time based on observed outputs, and we have measurement to back up self-improvement"
6. **AutoMaintainer** — 5-agent autonomous software team (github.com/purvanshjoshi/AutoMaintainer, 2026)
7. **DevinOS** — Self-improving knowledge engine (github.com/IQLaps/Devin, 2026)

---

> **Catatan Akhir:** Pustaka sudah mendesain 60% fondasi untuk self-updating, 30% untuk self-repairing, dan <10% untuk self-building. Dokumen 67-72 menutup gap tersebut. Roadmap ini bukan rencana "all-or-nothing" — setiap level memberikan value independen. **Mulai dari L1, ukur hasil, lanjut ke L2, ukur lagi, dst.** Self-evolution adalah marathon, bukan sprint. Sistem yang berevolusi terlalu cepat tanpa validasi adalah sistem yang akan hancur. Sistem yang berevolusi bertahap dengan eval-gated promotion adalah sistem yang akan menjadi semakin cerdas seiring waktu — seperti trader manusia yang belajar dari pengalaman, tetapi dengan kecepatan dan ketelitian mesin.
