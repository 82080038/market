# Change & Release Management untuk Trading System

> **Dokumen 50** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Strategi deploy yang aman untuk sistem trading — blue-green, canary release, rollback strategy, feature flags, change approval process.
>
> **Konteks:** Dokumen 27 bahas deployment & DevOps secara umum. Tapi sistem trading punya risiko unik: bug di decision engine → salah rekomendasi → user loss uang. Deploy ke sistem trading butuh strategi khusus yang lebih hati-hati dari web app biasa.

---

## Daftar Isi

1. [Kenapa Trading System Butuh Change Management Khusus](#1-kenapa-trading-system-butuh-change-management-khusus)
2. [Change Classification](#2-change-classification)
3. [Release Strategies](#3-release-strategies)
4. [Feature Flags untuk Trading Logic](#4-feature-flags-untuk-trading-logic)
5. [Rollback Strategy per Komponen](#5-rollback-strategy-per-komponen)
6. [Change Approval Process](#6-change-approval-process)
7. [Pre-Deployment Checklist](#7-pre-deployment-checklist)
8. [Post-Deployment Verification](#8-post-deployment-verification)

---

## 1. Kenapa Trading System Butuh Change Management Khusus

### 1.1 Risiko Unik Trading System

| Risiko | Impact | Kenapa Tidak Boleh Terjadi |
|--------|--------|---------------------------|
| **Bug di decision engine** | User dapat rekomendasi salah → loss uang | Financial loss, trust loss |
| **Bug di scoring weights** | Composite score salah → ranking salah | User salah pilih saham |
| **Bug di order execution** | Order salah harga/jumlah | Financial loss, regulatory issue |
| **Bug di data validation** | Data corrupt masuk pipeline → semua analysis salah | Garbage in, garbage out |
| **Bug di risk engine** | Position sizing salah → overexpose | Capital loss, margin call |

### 1.2 Prinsip Change Management untuk Trading

1. **Tidak deploy saat market open** — deploy hanya di maintenance window (01:00-05:00 WIB)
2. **Tidak deploy saat pipeline running** — tunggu T-019 (pipeline) selesai
3. **Selalu test dengan real data** — unit test tidak cukup, perlu integration test dengan DB
4. **Rollback plan wajib** — setiap deploy harus punya rollback < 5 min
5. **Canary untuk trading logic** — release ke subset ticker dulu sebelum full rollout
6. **Feature flag untuk risky changes** — bisa disable tanpa redeploy

---

## 2. Change Classification

| Class | Definisi | Contoh | Approval | Deploy Window |
|-------|----------|--------|----------|---------------|
| **A: Critical Trading Logic** | Perubahan yang memengaruhi rekomendasi/eksekusi | Scoring weights, decision engine, risk engine, order execution | Manual review + test wajib | Maintenance window only |
| **B: Analysis Engine** | Perubahan di engine analisis (tidak langsung ke rekomendasi) | Technical indicator formula, sentiment scoring, pattern detection | Manual review | Maintenance window |
| **C: Data Pipeline** | Perubahan di data fetch/validate/store | New data source, validation rule change, schema migration | Manual review + migration test | Maintenance window |
| **D: Infrastructure** | Perubahan infra tidak impact trading logic | API endpoint baru, logging, monitoring, UI | Auto (CI/CD) | Any time (non-market hours preferred) |
| **E: Cosmetic** | UI, docs, comments | Frontend styling, README update | Auto (CI/CD) | Any time |

---

## 3. Release Strategies

### 3.1 Blue-Green Deployment

```
┌─────────────────┐     ┌─────────────────┐
│  BLUE (current)  │     │  GREEN (new)    │
│  v0.1.11         │     │  v0.1.12        │
│  API:8000        │     │  API:8001       │
│  [serving]       │     │  [testing]      │
└─────────────────┘     └─────────────────┘
         │                       │
         └───────┬───────────────┘
                 ▼
         ┌──────────────┐
         │  Health Check │
         │  (green)      │
         └──────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
  PASS         FAIL        MANUAL
  Switch       Abort       Review
  traffic      rollback    needed
```

**Procedure:**
1. Deploy new version to green environment (port 8001)
2. Run health checks: API, DB, GPU, data
3. Run smoke tests: `/api/recommend/BBCA.JK`, `/api/explain/BBCA.JK`
4. Compare results: green vs blue (scores should be similar unless intentional change)
5. If pass: switch traffic (update nginx/port)
6. If fail: abort, keep blue, investigate green

### 3.2 Canary Release untuk Trading Logic

```
Phase 1: Canary 5% (47 tickers dari 928)
├── Run new logic on 47 random tickers
├── Compare scores with old logic
├── Check: no NaN, no extreme values, no crash
└── If OK → Phase 2

Phase 2: Canary 25% (232 tickers)
├── Run new logic on 232 tickers
├── Compare score distribution with old
├── Check: avg score delta < 10 points
└── If OK → Phase 3

Phase 3: Canary 50% (464 tickers)
├── Run new logic on 464 tickers
├── Full validation
└── If OK → Phase 4

Phase 4: Full rollout (928 tickers)
├── Replace old logic entirely
├── Archive old version (git tag)
└── Monitor for 24h
```

**Implementation:**
```python
# config.py
CANARY_TICKERS = config("CANARY_TICKERS", default=None)  # comma-separated
CANARY_PERCENT = config("CANARY_PERCENT", default=0, cast=float)

# pipeline.py
def run_pipeline(tickers):
    if CANARY_TICKERS:
        canary_set = set(CANARY_TICKERS.split(","))
        for ticker in tickers:
            if ticker in canary_set:
                run_new_logic(ticker)  # v0.1.12
            else:
                run_old_logic(ticker)  # v0.1.11
    elif CANARY_PERCENT > 0:
        canary_count = int(len(tickers) * CANARY_PERCENT)
        canary_set = set(random.sample(tickers, canary_count))
        for ticker in tickers:
            if ticker in canary_set:
                run_new_logic(ticker)
            else:
                run_old_logic(ticker)
    else:
        for ticker in tickers:
            run_new_logic(ticker)  # full rollout
```

### 3.3 Rolling Deployment (untuk non-trading changes)

```
Instance 1: v0.1.11 → v0.1.12 (restart)
Instance 2: v0.1.11 → v0.1.12 (restart)
Instance 3: v0.1.11 → v0.1.12 (restart)
```

Hanya untuk Class D/E changes yang tidak impact trading logic.

---

## 4. Feature Flags untuk Trading Logic

### 4.1 Kenapa Feature Flags

- **Toggle tanpa redeploy** — disable risky feature dalam < 1 detik
- **A/B testing** — bandingkan old vs new scoring logic
- **Gradual rollout** — aktifkan untuk % ticker tertentu
- **Emergency kill switch** — disable auto-trade instantly

### 4.2 Feature Flag Catalog

| Flag | Default | Type | Impact jika OFF |
|------|---------|------|-----------------|
| `auto_trade_enabled` | false | Kill switch | No auto-trading |
| `lstm_prediction_enabled` | true | Kill switch | Skip LSTM, factor-only prediction |
| `pattern_detection_enabled` | true | Kill switch | Skip pattern detection |
| `sentiment_nlp_enabled` | true | Kill switch | Skip IndoBERT, use lexicon |
| `canary_scoring_v2` | false | Canary | Use v1 scoring logic |
| `new_risk_model` | false | Canary | Use old risk model |
| `portfolio_hrp` | true | Toggle | Use Markowitz instead of HRP |
| `regime_detection_enabled` | true | Kill switch | Use default weights |

### 4.3 Implementation

```python
# config.py
auto_trade_enabled = config("auto_trade_enabled", default=False, cast=bool)
lstm_prediction_enabled = config("lstm_prediction_enabled", default=True, cast=bool)
canary_scoring_v2 = config("canary_scoring_v2", default=False, cast=bool)

# usage in pipeline.py
if lstm_prediction_enabled:
    lstm_pred = run_lstm(ticker)
else:
    lstm_pred = None  # factor-only prediction

if canary_scoring_v2:
    composite = new_scoring_v2(scores)
else:
    composite = old_scoring_v1(scores)
```

### 4.4 Feature Flag Lifecycle

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ CREATED  │──▶│ TEST     │──▶│ CANARY   │──▶│ FULL ON  │──▶│ REMOVE   │
│ default= │   │ default= │   │ default= │   │ default= │   │ flag     │
│ OFF      │   │ ON (dev) │   │ OFF (prod│   │ ON (prod)│   │ removed  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

- **CREATED**: Flag ditambah, default OFF
- **TEST**: ON di development, OFF di production
- **CANARY**: ON untuk subset di production
- **FULL ON**: ON untuk semua di production
- **REMOVE**: Setelah stabil, flag dihapus dari code (dead code cleanup)

---

## 5. Rollback Strategy per Komponen

| Komponen | Rollback Method | Time | Data Impact |
|----------|----------------|------|-------------|
| **API** | `git checkout v0.1.11 && restart uvicorn` | < 2 min | None (stateless) |
| **Frontend** | `git checkout v0.1.11 && npm run build` | < 5 min | None (stateless) |
| **Scoring logic** | Set feature flag `canary_scoring_v2=false` | < 1 sec | Scores dari new logic tetap di DB (perlu re-run) |
| **DB schema** | Alembic downgrade | < 5 min | Data dari migration mungkin hilang |
| **LSTM models** | Restore old `.pt` files from git LFS / backup | < 10 min | None (model files) |
| **Config (.env)** | Restore old `.env` from git | < 1 min | None |
| **Data (OHLCV)** | Tidak rollback — data adalah fact | N/A | N/A |

### 5.1 Rollback Decision Tree

```
Bug detected post-deploy?
├── Is it SEV-0 (user financial impact)?
│   ├── YES → Immediate rollback (< 5 min)
│   └── NO → Continue
├── Is it in trading logic?
│   ├── YES → Feature flag OFF (< 1 sec)
│   └── NO → Continue
├── Is it in infrastructure?
│   ├── YES → Git rollback + restart (< 5 min)
│   └── NO → Continue
└── Is it cosmetic?
    ├── YES → Fix in next release
    └── NO → Assess severity, decide
```

---

## 6. Change Approval Process

### 6.1 Solo Developer Approval

Untuk solo developer, "approval" = self-review checklist:

```
CHANGE REQUEST (self-review)
══════════════════════════════
Change Class: [A/B/C/D/E]
Description: [what changes]
Files changed: [list]
Tests passed: [Y/N — which tests]
Rollback plan: [how to undo]
Feature flag needed: [Y/N]
Canary needed: [Y/N]

Self-Review Checklist:
[ ] Code reviewed (diff checked)
[ ] Unit tests pass: .venv/bin/pytest tests/unit/ -x
[ ] Integration test pass: manual test with real data
[ ] No breaking API changes (or versioned)
[ ] DB migration tested (if applicable)
[ ] Rollback plan verified
[ ] Deploy window correct (maintenance window for Class A/B/C)
```

### 6.2 Future: Change Advisory Board (CAB)

| Role | Responsibility |
|------|----------------|
| **Change requester** | Submit change request with description, risk, rollback |
| **Technical reviewer** | Review code, architecture, test coverage |
| **Business approver** | Assess business risk, approve/reject |
| **Release manager** | Schedule deploy, execute, verify |

---

## 7. Pre-Deployment Checklist

### 7.1 Universal Checklist (semua class)

- [ ] Code committed dan pushed ke git
- [ ] Unit tests pass: `.venv/bin/pytest tests/unit/ -x`
- [ ] Lint pass: `.venv/bin/ruff check src/`
- [ ] Type check pass: `.venv/bin/mypy src/`
- [ ] Version bumped di `pyproject.toml` + `__init__.py` + API
- [ ] CHANGELOG.md updated
- [ ] Rollback plan documented
- [ ] Deploy window confirmed (maintenance window untuk Class A/B/C)

### 7.2 Class A/B Additional Checklist (Trading Logic)

- [ ] Manual test: `compute-scores BBCA.JK` — verify scores make sense
- [ ] Manual test: `recommend BBCA.JK` — verify recommendation makes sense
- [ ] Manual test: `explain BBCA.JK` — verify narrative correct
- [ ] Compare scores: new vs old (delta < 10 points unless intentional)
- [ ] Feature flag created (if canary/phased rollout needed)
- [ ] No NaN/Inf in scores
- [ ] No crash on edge cases (IPO, suspension, delisted ticker)

### 7.3 Class C Additional Checklist (Data Pipeline)

- [ ] DB migration tested on copy of production DB
- [ ] `alembic upgrade head` — verify
- [ ] `alembic downgrade -1` — verify rollback
- [ ] Data validation post-migration
- [ ] Backup DB sebelum migration

---

## 8. Post-Deployment Verification

### 8.1 Automated Verification (immediately after deploy)

```bash
#!/bin/bash
# scripts/post_deploy_verify.sh

echo "=== Post-Deploy Verification ==="

# 1. API health
curl -s http://localhost:8000/api/health | jq .status
# Expected: "ok"

# 2. Ticker count
COUNT=$(curl -s http://localhost:8000/api/tickers | jq '.tickers | length')
echo "Ticker count: $COUNT"
# Expected: ~928

# 3. Recommendation smoke test
curl -s http://localhost:8000/api/recommend/BBCA.JK | jq '.action'
# Expected: "BUY" | "HOLD" | "WATCHLIST" | "AVOID"

# 4. XAI smoke test
curl -s http://localhost:8000/api/explain/BBCA.JK | jq '.narrative | length'
# Expected: > 100

# 5. Monitor endpoint
curl -s http://localhost:8000/api/monitor | jq '.health_score'
# Expected: > 70

# 6. DB integrity
sqlite3 data/trading_system.db "PRAGMA integrity_check;"
# Expected: "ok"

echo "=== Verification Complete ==="
```

### 8.2 Manual Verification (within 1 hour post-deploy)

- [ ] Frontend loads correctly (http://localhost:3000)
- [ ] Data inspection dashboard shows data
- [ ] No error in API logs
- [ ] No error in scheduler logs
- [ ] Monitoring health score > 70
- [ ] Telegram alert test (if alerting changed)

### 8.3 24-Hour Monitoring Post-Deploy

- [ ] Next pipeline run (18:00 WIB) completes successfully
- [ ] No SEV-0/SEV-1 incident within 24 hours
- [ ] Scores distribution similar to pre-deploy (unless intentional change)
- [ ] If canary: compare canary vs control group scores

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **27** (Deployment/DevOps) | General deployment strategy; this doc adds trading-specific constraints |
| **47** (Operational Contract) | T-044 (monitoring) used for post-deploy verification |
| **48** (DR/BCP) | Rollback is part of DR; failed deploy may trigger DR |
| **49** (Incident Mgmt) | Failed deploy → incident → post-mortem → change process improvement |
| **51** (MLOps) | Model deployment follows change management process |

---

## Referensi

1. `src/trading_system/api/app.py` — API version endpoint
2. `src/trading_system/__init__.py` — Version string
3. `pyproject.toml` — Project version & tooling config
4. `pustaka/27-deployment-devops-trading.md` — Docker, CI/CD, blue-green deploy
5. `pustaka/47-operational-contract-runbook.md` — T-044 (monitoring) for post-deploy verification
6. `pustaka/51-mlops-model-risk-management.md` — Model deployment follows change management

---

> **Catatan:** Change management untuk trading system adalah tentang disiplin, bukan bureaucracy. Goal: deploy dengan confidence, rollback dengan cepat, tidak surprise user. "Deploy slow, rollback fast."
