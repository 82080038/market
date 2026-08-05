# Lifecycle Environment: Real Trading, Testing, AI/ML & Data Development

> **Dokumen 93** | Pustaka Pengetahuan Pasar Modal Indonesia/Global
>
> **Tujuan:** Menganalisis konsep "3 versi aplikasi" (real trading, testing, pengembangan data/AI/ML/engine) dan menerjemahkannya menjadi arsitektur lingkungan (environments) serta **promotion gates** yang aman untuk sistem trading single-user. Dokumen ini memadukan best practice industri algoritmic trading, model risk management, dan champion-challenger deployment.
>
> **Cross-reference:** Lihat `92-multi-market-multi-asset-trading-system.md` untuk modul multi-pasar; `85-backtest-to-live-gap-prevention.md` untuk mitigasi backtest-to-live gap; `51-mlops-model-risk-management.md` untuk model registry; `47-operational-contract-runbook.md` untuk operasional harian; `41-uu-pdp-compliance-fintech.md` untuk kepatuhan data.

---

## Daftar Isi

1. [Kesimpulan Eksekutif](#1-kesimpulan-eksekutif)
2. [Analisis Konsep 3 Versi](#2-analisis-konsep-3-versi)
3. [Rekomendasi Arsitektur Environment](#3-rekomendasi-arsitektur-environment)
4. [Promotion Gates Antar-Environment](#4-promotion-gates-antar-environment)
5. [Isolasi Data, Kode, Model, dan Konfigurasi](#5-isolasi-data-kode-model-dan-konfigurasi)
6. [CI/CD & Model Registry](#6-cicd--model-registry)
7. [Monitoring, Circuit Breaker, dan Rollback](#7-monitoring-circuit-breaker-dan-rollback)
8. [Governance & Approval Workflow](#8-governance--approval-workflow)
9. [Penerapan pada Project Ini](#9-penerapan-pada-project-ini)
10. [Referensi](#10-referensi)

---

## 1. Kesimpulan Eksekutif

Konsep 3 versi yang Anda usulkan sangat benar dan sesuai dengan standar industri algoritmic trading. Namun, istilah "versi" bisa membingungkan karena ketiganya bukan "varian produk" melainkan **lingkungan (environments) yang berbeda dalam satu lifecycle**:

| Nama Konseptual Anda | Nama Industri yang Tepat | Fungsi |
|----------------------|--------------------------|--------|
| **Versi Trading Real** | **Production / Live** | Eksekusi dengan uang nyata, supervised oleh risk controls dan kill switch. |
| **Versi Testing Aplikasi** | **Staging / Paper Trading** | Semua sinyal live, semua fill simulasi; validasi operasional tanpa risiko finansial. |
| **Versi Pengembangan Data, AI/ML, Model, Engine** | **Research / Development / Sandbox** | Eksperimen, backtest, training model, feature engineering, sandbox kode yang dihasilkan AI. |

**Rekomendasi utama:**

1. Pisahkan ketiganya secara tegas pada **database, konfigurasi, model registry, dan broker adapter**.
2. Gunakan **promotion gates** yang jelas dan terukur; jangan "copy-paste" manual antar-environment.
3. Semua strategi/model **wajib** melewati: backtest rigor → paper trading → live dengan skala kecil.
4. Manusia tetap menyetujui perpindahan ke Production/Live; AI boleh mengusulkan dan menyiapkan artefak, tetapi **tidak boleh mengaktifkan eksekusi uang nyata tanpa approval**.

---

## 2. Analisis Konsep 3 Versi

### 2.1 Apa yang Benar dari Konsep Anda

Best practice industri menegaskan bahwa strategi algoritmik harus melalui serangkaian validasi sebelum uang nyata dipertaruhkan. AI Fin Hub menyebutnya sebagai **three-stage deployment pipeline: backtest → paper → live** dengan *explicit promotion gates* antara setiap tahap. Masing-masing menjawab pertanyaan berbeda:

- **Backtest / Research:** "Apakah strategi ini bisa bekerja secara historis?"
- **Paper / Staging:** "Apakah sinyal bertahan ketika bertemu microstructure pasar saat ini?"
- **Live / Production:** "Apakah eksekusi, latency, dan slippage masih menyisakan edge?"

Menyatukan ketiga tahap ini dalam satu kode tanpa gate adalah sumber utama kegagalan retail: *"Most retail strategies skip straight from a backtest into real money, and the live P&L curve answers whatever question the backtest ignored."* — AI Fin Hub.

Algorithm Development Lifecycle (ADL) dari CryptoMantiq merumuskan lima fase berurutan: **Design → Code → Backtest → Paper Trade → Live Deploy**, dengan aturan *"no phase can be bypassed"*. Setiap fase memiliki pass/fail gate, dan kegagalan pada satu fase mengharuskan kembali ke fase yang menyebabkan kegagalan, bukan melanjutkan ke tahap berikutnya.

### 2.2 Di Mana Konsep Perlu Diperjelas

| Potensi Ambigu | Klarifikasi |
|----------------|-------------|
| "Versi" bisa diartikan aplikasi terpisah | Sebaiknya gunakan istilah **environment** dalam satu aplikasi yang sama, dipilih lewat konfigurasi. |
| "Testing" hanya UI/functional test saja | Testing environment untuk trading harus mencakup **paper trading live-market**, bukan hanya unit test. |
| "Pengembangan AI/ML" dianggap sekadar training | Harus mencakup **sandbox, reproducible backtest, model registry, champion/challenger**, dan rollback. |
| Promosi antar-environment tidak diatur | Perlu **gate criteria** numerik dan approval workflow. |

---

## 3. Rekomendasi Arsitektur Environment

### 3.1 Tiga Environment dalam Satu Codebase

Gunakan **satu source code**, tiga runtime profile. Manfaatnya: tidak ada *drift* kode antar-environment, semua fitur tersedia di semua environment, dan perbedaan hanya pada data, konfigurasi, dan broker adapter.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          SINGLE CODEBASE                                │
│  src/market/                                                            │
│    ├── data/                                                            │
│    ├── analysis/                                                        │
│    ├── ai_learning/                                                     │
│    ├── decision/                                                        │
│    ├── advisory/                                                        │
│    ├── risk/                                                            │
│    ├── portfolio/                                                       │
│    ├── execution/                                                       │
│    ├── api/                                                             │
│    └── frontend/                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│  ENVIRONMENT PROFILE (dipilih via env var / CLI flag)                     │
│  RESEARCH   →  PAPER    →  LIVE                                          │
│     ↓              ↓          ↓                                         │
│  sandbox_db     paper_db   live_db                                        │
│  mock_broker    paper_bkr  real_bkr                                      │
│  candidate tag  challenger tag  champion tag                            │
│  full logging   full logging   minimal operational logging                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Per-Environment Characteristics

#### A. Research / Development / Sandbox (`ENV=research`)

| Aspek | Konfigurasi |
|-------|-------------|
| **Database** | `market_research.db` atau disposable SQLite in-memory |
| **Broker adapter** | Mock / simulated only |
| **Data** | Historical + sample live untuk replay; boleh as-is untuk eksperimen |
| **Model registry** | Experiments, tidak masuk production registry |
| **AI-generated code** | Dijalankan di sandbox terisolasi, wajib AST scan & test sebelum dipromosikan |
| **Tujuan** | Eksperimen fitur, feature engineering, training model, backtest hipotesis |
| **Durasi** | Iteratif tanpa batas; hasil yang lulus gate dipromosikan ke Paper |

#### B. Staging / Paper Trading (`ENV=paper`)

| Aspek | Konfigurasi |
|-------|-------------|
| **Database** | `market_paper.db` |
| **Broker adapter** | Paper/simulated broker atau broker-provided paper account |
| **Data** | Live market data real-time/EOD, sama seperti Live |
| **Model registry** | `@candidate` atau `@challenger` |
| **AI-generated code** | Boleh dipromosikan jika lulus eval-gate; tetap dinyalakan via feature flag |
| **Tujuan** | Validasi sinyal, fills, slippage, OMS, risk controls, dan operasional 24/7 tanpa uang nyata |
| **Durasi minimum** | **30 hari kalender** per strategi/model (CryptoMantiq ADL; AI Fin Hub) |

#### C. Production / Live Trading (`ENV=live`)

| Aspek | Konfigurasi |
|-------|-------------|
| **Database** | `market_live.db` |
| **Broker adapter** | Real broker API (Sinarmas/BNI/Interactive Brokers/Alpaca, dll.) |
| **Data** | Live market data |
| **Model registry** | `@champion` |
| **AI-generated code** | Hanya model/strategi yang sudah lulus Paper ≥30 hari dan di-approve manual |
| **Tujuan** | Eksekusi uang nyata dengan risk controls keras |
| **Skala awal** | Mulai dari **25% position size untuk 30 trade pertama**, baru naik setelah performa cocok dengan Paper |

---

## 4. Promotion Gates Antar-Environment

### 4.1 Research → Paper (Backtest Quality Gate)

Sebelum model/strategi dari Research dipromosikan ke Paper, wajib memenuhi:

| Gate | Threshold | Sumber |
|------|-----------|--------|
| **Future-peek audit** | Semua fitur t-1, tidak ada data masa depan | Best practice internal (`85-backtest-to-live-gap-prevention.md`) |
| **Probability of Backtest Overfitting (PBO)** | < 0.5 | Bailey & López de Prado (2014), AI Fin Hub |
| **Walk-forward OOS Sharpe** | ≥ 0.8 × in-sample Sharpe | AI Fin Hub |
| **Deflated Sharpe Ratio (DSR)** | > 0.5 | Bailey & López de Prado (2014), AI Fin Hub |
| **Minimum trades** | ≥ 100 | CryptoMantiq ADL |
| **Max drawdown** | < 25% | RustyBT Production Deployment |
| **Profit factor** | ≥ 1.2 | CryptoMantiq ADL |
| **Win rate** | ≥ 40% | CryptoMantiq ADL |
| **Reproducibility** | Backtest rerun menghasilkan equity curve identik | Lycore Strategy Guide |
| **Code review & AST scan** | Lulus `ruff`, `mypy`, unit test ≥70%, sandbox test | Project rules |
| **Model card** | Dokumen input, asumsi, limitasi, test result | MRM Principles (SME Finance Forum) |

### 4.2 Paper → Live (Operational Readiness Gate)

| Gate | Threshold | Sumber |
|------|-----------|--------|
| **Minimum paper period** | 30 hari kalender | AI Fin Hub, CryptoMantiq ADL |
| **Live-vs-paper fill divergence** | Mean < 10 bps | AI Fin Hub |
| **Signal alignment live vs paper** | ≥ 95% | RustyBT Shadow Trading |
| **Execution quality** | Fill rate ≥ 90% | RustyBT Shadow Trading |
| **Broker rate-limit headroom** | < 50% usage at peak; 2× headroom | AI Fin Hub |
| **Heartbeat, watchdog, circuit breaker** | Green 100% selama paper | AI Fin Hub, RustyBT |
| **Daily review checklist** | Selesai 14 hari berturut-turut tanpa error material | RustyBT |
| **Human approval** | Approval eksplisit via UI/Telegram | Project safety rules |
| **Risk limits configured** | Daily loss limit, max drawdown, position size, correlation cap | FMSB SoGP |
| **Incident & rollback runbook** | Tersedia dan diuji | MRM Principles |

### 4.3 Live Scale-Up Gate

| Gate | Threshold |
|------|-----------|
| **Trade count** | ≥ 30 trade live pertama |
| **Live Sharpe 20-day rolling** | ≥ 50% paper Sharpe |
| **Drawdown** | ≤ 2 × 95th-percentile backtest drawdown |
| **Slippage 50-order rolling** | ≤ 1.5 × paper slippage |
| **Broker error rate 1h** | ≤ 2% |
| **Position correlation** | ≤ planned max |
| **Scale step** | 25% → 50% → 75% → 100% (masing-masing setelah 30 trade stabil) |

---

## 5. Isolasi Data, Kode, Model, dan Konfigurasi

### 5.1 Database Isolation

Setiap environment punya database terpisah untuk mencegah data test merembes ke live.

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    env: str = "research"  # research | paper | live
    db_path: str | None = None

    @property
    def resolved_db_path(self) -> str:
        if self.db_path:
            return self.db_path
        return f"data/market_{self.env}.db"
```

| Environment | File DB | Catatan |
|-------------|---------|---------|
| Research | `data/market_research.db` | Boleh dihapus/direbuild setiap eksperimen. |
| Paper | `data/market_paper.db` | Persistent; digunakan untuk audit 30 hari. |
| Live | `data/market_live.db` | Hanya data real; backup otomatis harian. |

### 5.2 Broker Adapter Isolation

```python
class BrokerAdapter(ABC):
    env: str

    async def submit_order(self, order: Order) -> Fill:
        if self.env == "research":
            return self._mock_fill(order)
        if self.env == "paper":
            return self._paper_fill(order)
        if self.env == "live":
            return await self._real_fill(order)
```

Penting: `env=live` **tidak boleh** bisa diaktifkan hanya dengan mengubah env var. Butuh file approval token yang di-generate setelah human sign-off.

### 5.3 Model Registry & Feature Store Isolation

Gunakan alias tagging seperti champion-challenger pattern (StackSimplify):

| Alias | Environment | Arti |
|-------|-------------|------|
| `@experiment` | Research | Model sedang dikembangkan. |
| `@candidate` | Paper | Model siap diuji live-market. |
| `@champion` | Live | Model yang sedang berjalan di production. |
| `@retired` | - | Model yang sudah tidak digunakan, disimpan untuk audit. |

Inference service selalu memuat model berdasarkan alias, bukan versi spesifik. Saat promote, cukup pindahkan alias; tidak perlu redeploy kode.

### 5.4 Configuration Isolation

Gunakan file `.env` terpisah atau prefix:

```bash
# .env.research
ENV=research
DB_PATH=data/market_research.db
BROKER_ADAPTER=MockBroker
AUTO_TRADE_ENABLED=false

# .env.paper
ENV=paper
DB_PATH=data/market_paper.db
BROKER_ADAPTER=PaperBroker
AUTO_TRADE_ENABLED=true   # hanya paper fills

# .env.live
ENV=live
DB_PATH=data/market_live.db
BROKER_ADAPTER=SinarmasBroker  # contoh broker IDX
AUTO_TRADE_ENABLED=false       # manual start setelah approval
LIVE_APPROVAL_TOKEN=/secure/live_approval.token
```

---

## 6. CI/CD & Model Registry

### 6.1 Promotion Pipeline

```
Research branch (ai/<experiment-name>)
    │
    ├── Unit tests, lint, type check
    ├── Backtest quality gate (PBO, DSR, WFA)
    └── Model card generated
    ↓
Merge to `paper` branch
    │
    ├── Deploy to Paper environment
    ├── Run 30-day paper trading
    └── Operational readiness gate
    ↓
Human approval + live approval token
    ↓
Merge to `main` / `live` branch
    │
    ├── Deploy to Live environment
    ├── Start with 25% position size
    └── Scale up gate
```

### 6.2 Reproducibility & Audit Trail

- Setiap backtest harus **reproducible**: seed, data snapshot, parameter, dan versi kode tercatat.
- Setiap promosi model harus menyertakan: model card, test results, approver identity, rollback path.
- Semua perubahan skema DB production wajib melalui Alembic dengan `downgrade` yang diuji.

Sesuai MRM Principles (SME Finance Forum): *"Implementation is the process of deploying a model into production, where design and testing meet real-world application... A clear and structured implementation plan is essential... risk assessment, change management, parallel testing, output verification, control integration, governance and handover."*

---

## 7. Monitoring, Circuit Breaker, dan Rollback

### 7.1 Auto-Pause Metrics di Live

Setiap hari trading, hitung 7 metrik berikut. Jika salah satu melampaui threshold, sistem **auto-pause** entri baru (AI Fin Hub):

1. **Daily P&L** di bawah persentil ke-2 distribusi backtest.
2. **Rolling 5-day P&L** di bawah persentil ke-5.
3. **Live Sharpe 20-hari** < 50% paper Sharpe.
4. **Drawdown** > 2 × 95th-percentile backtest drawdown.
5. **Fill slippage 50-order** > 1.5 × paper slippage.
6. **Broker error rate 1 jam** > 2%.
7. **Position correlation** > maksimum yang direncanakan.

### 7.2 Rollback Rule

Jika **rolling 20-hari live Sharpe < 50% paper Sharpe** atau **drawdown > 2 × 95th-percentile backtest drawdown**, strategi **demoted** kembali ke Paper. Demotion adalah *information-preserving pause*: strategi tetap berjalan di Paper terhadap data live sehingga dapat diamati apakah regresi berlanjut atau berbalik.

### 7.3 Kill Switch

- File-based kill switch: jika file `.KILL_SWITCH` ada, semua order baru ditolak.
- Daily loss limit: jika kerugian harian melebihi threshold, trading dihentikan.
- Manual kill: tersedia di UI dan Telegram.

---

## 8. Governance & Approval Workflow

### 8.1 Three Lines of Defence (Sederhana untuk Single-User)

Meskipun single-user, tetap perlu pemisahan peran dalam logika sistem:

| Peran | Fungsi |
|-------|--------|
| **Developer/Researcher (AI/User)** | Membuat strategi/model, menjalankan backtest, mempersiapkan model card. |
| **Validator (AI sub-agent / user)** | Independen meninjau code, hasil backtest, dan kepatuhan. Tidak boleh sama dengan developer. |
| **Approver (User)** | Manusia yang menyetujui promosi Paper→Live dan pengaktifan live trading. |

### 8.2 Approval Checklist Paper → Live

- [ ] Backtest + paper report disetujui.
- [ ] Risk limits, circuit breakers, dan kill switch dikonfigurasi.
- [ ] Live broker credentials tersedia di `.env` (tidak di-commit).
- [ ] Approval token / signature tercatat di audit log.
- [ ] Rollback dan incident runbook tersedia.
- [ ] Posisi awal: 25% size, 30 trade pertama.

### 8.3 Model Risk Tiering

Sesuai FMSB SoGP dan Databricks MRM guidance, model dapat dikelompokkan ke dalam tier:

| Tier | Kriteria | Approval |
|------|----------|----------|
| **Tier-1** | Model yang langsung menghasilkan order live, material | User + validator sign-off |
| **Tier-2** | Model rekomendasi/skor yang tidak eksekusi otomatis | User sign-off |
| **Tier-3** | Model eksplorasi/analitis | Owner sign-off |

---

## 9. Penerapan pada Project Ini

### 9.1 Yang Sudah Tersedia

Pustaka sudah memiliki fondasi yang kuat:

- `85-backtest-to-live-gap-prevention.md` → mitigasi look-ahead, survivorship, overfitting, realistic cost.
- `51-mlops-model-risk-management.md` → model registry, drift detection, champion/challenger.
- `71-eval-gated-promotion-ab-testing.md` → eval-gated promotion.
- `72-human-in-the-loop-oversight.md` → approval gate, kill switch, Telegram bot.
- `47-operational-contract-runbook.md` → 5W1H operasional harian.
- `41-uu-pdp-compliance-fintech.md` → kepatuhan data.

### 9.2 Yang Perlu Dibangun

1. **Environment selector** di CLI dan API (`--env research|paper|live`).
2. **Database isolation** via `market_{env}.db`.
3. **Broker adapter mode** research/mock, paper, live.
4. **Backtest quality gate runner** otomatis (PBO, DSR, WFA, future-peek audit).
5. **Paper trading orchestrator** dengan 30-day clock dan divergence tracker.
6. **Model registry alias** (`@experiment`, `@candidate`, `@champion`).
7. **Live approval token & audit log**.
8. **Auto-pause & rollback module** untuk 7 metric live.
9. **CI/CD promotion pipeline** research → paper → live.

### 9.3 Rekomendasi Roadmap Tambahan

Setelah MVP IDX stabil, alokasikan **4-6 minggu khusus** untuk membangun environment lifecycle dan governance ini sebelum menyentuh uang nyata. Ini lebih penting daripada menambah fitur analisis karena mengurangi risiko finansial yang fatal.

---

## 10. Referensi

1. **AI Fin Hub — Backtest to Paper to Live: Deployment Playbook** (2026). https://aifinhub.io/articles/backtest-to-paper-to-live-playbook/ — promotion gates: PBO, DSR, WFA, 30-day paper, 10 bps divergence, 7 live auto-pause metrics, rollback rule.
2. **CryptoMantiq — Algorithm Development Lifecycle (ADL) Explained** (2026). https://www.cryptomantiq.com/glossary/algorithm-development-lifecycle — 5-phase quality gate: Design, Code, Backtest, Paper Trade, Live Deploy; minimum thresholds (win rate ≥40%, profit factor ≥1.2, max DD <25%, Sharpe ≥0.5, ≥100 trades).
3. **RustyBT — Production Deployment Documentation** (2026). https://jerryinyang.github.io/rustybt/api/live-trading/production-deployment/ — 4-6 weeks deployment timeline: backtest validation, 2-week paper trading, shadow trading, production deployment.
4. **Lycore — Algorithmic Trading Platform Development: Strategy Guide** (2026). https://www.lycore.com/blog/algorithmic-trading-platforms-how-to-enable-strategy-backtesting-live-execution/ — 3-layer architecture, honest backtesting, reproducibility guarantee, event-driven execution.
5. **FMSB — Model Risk: Electronic Trading Algorithms** (2024). https://fmsb.com/wp-content/uploads/2025/04/Model-Risk-Electronic-Trading-Algorithm_FINAL-05.04.pdf — model tiering, input/output controls, pre-defined limits, manual supervision, testing requirements.
6. **SME Finance Forum — Principles for Model Risk Management** (2025). https://www.smefinanceforum.org/sites/default/files/2025-09/2025-08-01%20MRM%20Principles%20v1.0.pdf — independent challenge, accountability, benchmarks, implementation & handover, parallel testing, audit trail.
7. **StackSimplify — ML Governance: The Champion-Challenger Pattern** (2026). https://stacksimplify.com/blog/ml-governance-model-registry/ — model registry aliases (`@champion`, `@candidate`), quality gate, blue-green deployment, rollback.
8. **Burning Cost — Champion/Challenger Testing** (2026). https://burning-cost.github.io/2026/03/17/champion-model-unchallenged/ — shadow mode sebagai default, deterministic routing, power analysis, audit log granularity.
9. **Databricks — Model Risk Management in 2026** (2026). https://www.databricks.com/blog/model-risk-management-2026-bankers-guide-revised-interagency-guidance — risk-based tiering, lifecycle thinking, effective challenge, controlled promotion, rollback.

---

> **Catatan praktis:** Jangan anggap environment lifecycle sebagai "fitur tambahan". Ini adalah **infrastruktur keselamatan** yang memisahkan eksperimen dari uang nyata. Bangun sebelum eksekusi live pertama.
