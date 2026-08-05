# MLOps & Model Risk Management

> **Dokumen 51** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** MLOps lifecycle untuk LSTM dan ML models di sistem trading — model versioning, drift detection, model monitoring, champion/challenger, model retirement, model risk governance.
>
> **Konteks:** Dokumen 23 bahas ML trading. Dokumen 39 bahas AI/ML pattern memory. Dokumen 46 bahas prediksi & pipeline. Tapi belum ada doc yang membahas MLOps: bagaimana model dilifecycle dari development → production → monitoring → retirement. Dokumen ini mengisi gap.

---

## Daftar Isi

1. [MLOps Lifecycle](#1-mlops-lifecycle)
2. [Model Registry & Versioning](#2-model-registry--versioning)
3. [Drift Detection](#3-drift-detection)
4. [Model Monitoring in Production](#4-model-monitoring-in-production)
5. [Champion/Challenger Pattern](#5-championchallenger-pattern)
6. [Model Retirement Policy](#6-model-retirement-policy)
7. [Model Risk Governance](#7-model-risk-governance)
8. [Feature Store Integration](#8-feature-store-integration)

---

## 1. MLOps Lifecycle

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ DEVELOP  │──▶│ VALIDATE │──▶│ DEPLOY   │──▶│ MONITOR  │──▶│ DETECT   │──▶│ RETIRE/  │
│          │   │          │   │          │   │          │   │ DRIFT    │   │ RETRAIN  │
│ Train    │   │ OOS test │   │ Canary   │   │ Metrics  │   │ Data     │   │ Archive  │
│ Experim  │   │ Walk-fwd │   │ Full     │   │ Alerts   │   │ drift    │   │ Old model│
│ Features │   │ Purged   │   │ Feature  │   │ Health   │   │ Concept  │   │ New model│
│          │   │ TSS      │   │ flag     │   │ Score    │   │ drift    │   │ v+1      │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                                      │
                                                                      ▼
                                                              ┌──────────┐
                                                              │ LOOP BACK│
                                                              │ to DEVELOP│
                                                              └──────────┘
```

### 1.1 Fase Detail

| Fase | Tujuan | Output | Tools |
|------|--------|--------|-------|
| **Develop** | Train model dengan latest data + features | `models/lstm/{ticker}_lstm.pt` | PyTorch, GPU cuda:1 |
| **Validate** | OOS test, walk-forward, purged TSS | OOS R², directional accuracy | walk_forward.py |
| **Deploy** | Canary → full rollout | Model in production | Feature flags, model registry |
| **Monitor** | Track prediction quality, drift | Health score per model | Monitoring dashboard |
| **Detect Drift** | Identify data/concept drift | Drift alert | Statistical tests |
| **Retire/Retrain** | Archive old, deploy new | New model version | Model registry update |

---

## 2. Model Registry & Versioning

### 2.1 Model Registry Schema

```sql
CREATE TABLE model_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    model_type TEXT NOT NULL,          -- 'lstm', 'sentiment_nlp', 'regime_hmm'
    version TEXT NOT NULL,             -- semver: '1.0.0', '1.1.0', '2.0.0'
    file_path TEXT NOT NULL,           -- 'models/lstm/BBCA.JK_lstm.pt'
    trained_at TIMESTAMP NOT NULL,
    trained_by TEXT NOT NULL,          -- 'T-025 (weekly retrain)'
    training_data_start DATE NOT NULL,
    training_data_end DATE NOT NULL,
    -- Metrics
    oos_r2 REAL,                       -- out-of-sample R²
    oos_rmse REAL,                     -- out-of-sample RMSE
    directional_accuracy REAL,         -- % correct direction prediction
    oos_sharpe REAL,                   -- Sharpe ratio of strategy using this model
    -- Status
    status TEXT NOT NULL,              -- 'champion', 'challenger', 'archived', 'retired'
    deployed_at TIMESTAMP,
    retired_at TIMESTAMP,
    -- Metadata
    hyperparams_json TEXT,             -- JSON: {batch_size: 64, hidden_dim: 256, ...}
    features_json TEXT,                -- JSON: list of features used
    notes TEXT,
    UNIQUE(ticker, model_type, version)
);
```

### 2.2 Versioning Convention

```
MAJOR.MINOR.PATCH

MAJOR: Breaking change (new architecture, different features)
MINOR: Retrain with new data (same architecture)
PATCH: Hyperparameter tuning (same architecture, same data)
```

Contoh:
- `BBCA.JK_lstm v1.0.0` — initial model
- `BBCA.JK_lstm v1.1.0` — weekly retrain (Sabtu, T-025)
- `BBCA.JK_lstm v1.1.1` — learning rate tuning
- `BBCA.JK_lstm v2.0.0` — new architecture (e.g., added attention layer)

### 2.3 Model File Naming

```
models/lstm/
├── BBCA.JK_lstm_v1.0.0.pt    (archived)
├── BBCA.JK_lstm_v1.1.0.pt    (champion — current production)
├── BBCA.JK_lstm_v1.2.0.pt    (challenger — canary testing)
└── TLKM.JK_lstm_v1.0.0.pt    (champion)
```

---

## 3. Drift Detection

### 3.1 Types of Drift

| Drift Type | Definisi | Detection Method | Impact |
|------------|----------|------------------|--------|
| **Data Drift** | Distribution of input features changes | KS test, PSI (Population Stability Index) | Model trained on old distribution → predictions stale |
| **Concept Drift** | Relationship between features and target changes | Prediction accuracy decline, residual analysis | Model logic no longer valid |
| **Prediction Drift** | Distribution of predictions changes | Monitor prediction distribution over time | Model may be biased toward new data pattern |

### 3.2 Data Drift Detection

```python
# ai_learning/drift_detection.py

import numpy as np
from scipy.stats import ks_2samp

def compute_psi(expected, actual, bins=10):
    """Population Stability Index — PSI < 0.1 stable, 0.1-0.25 concerning, > 0.25 drift."""
    expected_pct = np.histogram(expected, bins=bins)[0] / len(expected)
    actual_pct = np.histogram(actual, bins=bins)[0] / len(actual)
    # Avoid log(0)
    expected_pct = np.clip(expected_pct, 0.001, None)
    actual_pct = np.clip(actual_pct, 0.001, None)
    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return psi

def check_data_drift(ticker, reference_window=60, current_window=5):
    """
    Compare feature distributions: reference (training period) vs current (recent).
    """
    ref_features = load_features(ticker, days_back=reference_window, end_offset=current_window)
    cur_features = load_features(ticker, days_back=current_window)

    drift_report = {}
    for feature_name in ref_features.columns:
        psi = compute_psi(ref_features[feature_name], cur_features[feature_name])
        ks_stat, ks_p = ks_2samp(ref_features[feature_name], cur_features[feature_name])

        drift_report[feature_name] = {
            "psi": psi,
            "ks_statistic": ks_stat,
            "ks_p_value": ks_p,
            "status": "stable" if psi < 0.1 else ("concerning" if psi < 0.25 else "drift")
        }

    return drift_report
```

### 3.3 Concept Drift Detection

```python
def check_concept_drift(ticker, window=20):
    """
    Monitor prediction accuracy over time.
    If accuracy declines consistently → concept drift.
    """
    recent_predictions = load_prediction_log(ticker, days=window)
    evaluated = [p for p in recent_predictions if p.status == "SUCCESS" or p.status == "FAIL"]

    if len(evaluated) < 10:
        return {"status": "insufficient_data"}

    accuracy = sum(1 for p in evaluated if p.status == "SUCCESS") / len(evaluated)

    # Compare with historical baseline
    historical_accuracy = get_historical_accuracy(ticker, days=252)

    decline = historical_accuracy - accuracy

    return {
        "current_accuracy": accuracy,
        "historical_accuracy": historical_accuracy,
        "decline": decline,
        "status": "drift" if decline > 0.10 else ("concerning" if decline > 0.05 else "stable")
    }
```

### 3.4 Drift Alert Thresholds

| Metric | Green | Yellow | Red (Drift) | Action |
|--------|-------|--------|-------------|--------|
| PSI | < 0.10 | 0.10-0.25 | > 0.25 | Retrain model |
| KS p-value | > 0.05 | 0.01-0.05 | < 0.01 | Investigate feature |
| Accuracy decline | < 5% | 5-10% | > 10% | Retrain + feature review |
| Prediction variance | < 2x baseline | 2-3x | > 3x | Investigate model |

### 3.5 Drift Check Schedule

| Check | Frequency | Scope |
|-------|-----------|-------|
| Data drift (PSI) | Daily (post-pipeline) | All tickers, top 20 features |
| Concept drift (accuracy) | Daily (post T-023) | All tickers with ≥ 10 evaluated predictions |
| Prediction drift | Weekly | All tickers, prediction distribution |
| Full drift report | Weekly (Sabtu) | All tickers, all features, comprehensive |

---

## 4. Model Monitoring in Production

### 4.1 Model Health Score

```python
def compute_model_health(ticker):
    """
    Composite health score 0-100 for a model in production.
    """
    scores = {}

    # 1. Prediction accuracy (40%)
    drift = check_concept_drift(ticker)
    scores["accuracy"] = max(0, 100 - (drift.get("decline", 0) * 1000))

    # 2. Data drift (25%)
    data_drift = check_data_drift(ticker)
    avg_psi = np.mean([v["psi"] for v in data_drift.values()])
    scores["data_stability"] = max(0, 100 - (avg_psi * 400))

    # 3. Prediction frequency (15%)
    recent_preds = count_predictions(ticker, days=7)
    scores["coverage"] = min(100, recent_preds / 7 * 100)

    # 4. Latency (10%)
    avg_inference_time = get_avg_inference_time(ticker)
    scores["latency"] = max(0, 100 - (avg_inference_time - 0.5) * 50)  # 0.5s baseline

    # 5. Error rate (10%)
    error_rate = get_error_rate(ticker, days=7)
    scores["reliability"] = max(0, 100 - (error_rate * 100))

    # Weighted composite
    weights = {"accuracy": 0.40, "data_stability": 0.25, "coverage": 0.15,
               "latency": 0.10, "reliability": 0.10}

    health = sum(scores[k] * weights[k] for k in weights)
    return {"health_score": health, "components": scores}
```

### 4.2 Monitoring Dashboard

| Metric | Display | Alert Threshold |
|--------|---------|-----------------|
| Model health score | Gauge 0-100 per ticker | < 60 |
| OOS R² trend | Line chart per ticker | Declining 3 weeks |
| Prediction accuracy | Bar chart per ticker | < 50% |
| Data drift PSI | Heatmap ticker × feature | > 0.25 |
| Inference latency | Line chart | > 2s per ticker |
| Error rate | Line chart | > 5% |

### 4.3 Model Monitoring Schedule

| Task | Frequency | Owner | Alert Channel |
|------|-----------|-------|---------------|
| Health score computation | Daily (post-pipeline) | Monitoring Engine | Telegram if < 60 |
| Drift detection | Daily | Drift Detection module | Audit log + Telegram if Red |
| Performance metrics | Weekly | Walk-Forward (T-027) | Model Registry update |
| Full model audit | Monthly | Manual review | Report generated |

---

## 5. Champion/Challenger Pattern

### 5.1 Konsep

```
┌──────────────────────────────────────────┐
│           PRODUCTION                      │
│                                          │
│  ┌─────────────┐  ┌─────────────┐        │
│  │ CHAMPION    │  │ CHALLENGER  │        │
│  │ v1.1.0      │  │ v1.2.0      │        │
│  │ 90% traffic │  │ 10% traffic │        │
│  │ (835 tickers│  │ (93 tickers)│        │
│  │  random)    │  │  random)    │        │
│  └─────────────┘  └─────────────┘        │
│         │                │               │
│         └────────┬───────┘               │
│                  ▼                       │
│         ┌──────────────┐                 │
│         │ COMPARISON   │                 │
│         │ OOS R², acc, │                 │
│         │ directional  │                 │
│         └──────────────┘                 │
│                  │                       │
│         ┌────────┼────────┐              │
│         ▼        ▼        ▼              │
│      CHALLENGER  CHALLENGER  KEEP        │
│      WINS        LOSES     BOTH          │
│      → Promote   → Archive  → Monitor    │
└──────────────────────────────────────────┘
```

### 5.2 Promotion Criteria

Challenger dipromote ke Champion jika:

| Criteria | Threshold | Wajib? |
|----------|-----------|--------|
| OOS R² | Challenger > Champion by ≥ 0.02 | Ya |
| Directional accuracy | Challenger > Champion by ≥ 3% | Ya |
| No severe drift | Challenger PSI < 0.25 | Ya |
| Latency | Challenger ≤ Champion + 20% | Ya |
| Minimum samples | ≥ 20 predictions per model | Ya |
| Stability | Challenger variance < Champion variance | Nice to have |

### 5.3 Implementation

```python
# ai_learning/champion_challenger.py

class ChampionChallenger:
    def __init__(self, ticker, model_type="lstm"):
        self.ticker = ticker
        self.model_type = model_type

    def get_champion(self):
        """Return current champion model."""
        return model_registry.get_model(
            ticker=self.ticker,
            model_type=self.model_type,
            status="champion"
        )

    def get_challenger(self):
        """Return current challenger model."""
        return model_registry.get_model(
            ticker=self.ticker,
            model_type=self.model_type,
            status="challenger"
        )

    def evaluate_challenger(self):
        """Compare challenger vs champion. Return promotion decision."""
        champion = self.get_champion()
        challenger = self.get_challenger()

        if not challenger:
            return {"decision": "no_challenger"}

        # Get predictions from both models
        champ_preds = get_predictions(champion, min_count=20)
        chall_preds = get_predictions(challenger, min_count=20)

        if len(champ_preds) < 20 or len(chall_preds) < 20:
            return {"decision": "insufficient_data",
                    "champion_count": len(champ_preds),
                    "challenger_count": len(chall_preds)}

        # Compare metrics
        champ_r2 = compute_r2(champ_preds)
        chall_r2 = compute_r2(chall_preds)
        champ_acc = compute_directional_accuracy(champ_preds)
        chall_acc = compute_directional_accuracy(chall_preds)

        # Decision
        promote = (chall_r2 > champ_r2 + 0.02 and
                   chall_acc > champ_acc + 0.03)

        return {
            "decision": "promote" if promote else "keep_champion",
            "champion": {"r2": champ_r2, "accuracy": champ_acc},
            "challenger": {"r2": chall_r2, "accuracy": chall_acc},
            "delta_r2": chall_r2 - champ_r2,
            "delta_accuracy": chall_acc - champ_acc
        }

    def promote_challenger(self):
        """Promote challenger to champion, archive old champion."""
        old_champion = self.get_champion()
        challenger = self.get_challenger()

        model_registry.update_status(old_champion.id, "archived")
        model_registry.update_status(challenger.id, "champion")
        model_registry.update_deployed_at(challenger.id)

        audit_log(f"Model promoted: {self.ticker} {challenger.version} → champion")
```

---

## 6. Model Retirement Policy

### 6.1 Retirement Triggers

| Trigger | Condition | Action |
|---------|-----------|--------|
| **Accuracy decline** | OOS accuracy < 45% for 3 consecutive weeks | Retire + retrain |
| **Severe drift** | PSI > 0.25 for 3 consecutive days | Retire + retrain |
| **Architecture change** | New model architecture (MAJOR version) | Retire old, deploy new |
| **Feature deprecation** | Feature no longer available/computed | Retire + retrain without feature |
| **Age** | Model > 90 days since last retrain | Auto-retrain (T-025) |
| **Manual** | Developer decides model is no longer valid | Retire + document reason |

### 6.2 Retirement Process

```
1. IDENTIFY: Drift detection or manual review flags model
2. NOTIFY: Alert via Telegram + audit_log
3. REPLACEMENT: Train new model (T-025) or promote challenger
4. VALIDATE: New model passes OOS validation (T-027)
5. DEPLOY: New model to production (champion/challenger)
6. ARCHIVE: Old model status → 'archived', file kept for 30 days
7. DELETE: After 30 days, delete .pt file (save storage)
8. DOCUMENT: Record retirement reason in model_registry
```

### 6.3 Model Lifecycle States

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ TRAINING │──▶│ VALIDATING│──▶│ CHALLENGER│──▶│ CHAMPION │──▶│ ARCHIVED │
│          │   │          │   │          │   │          │   │          │
│ In       │   │ OOS test │   │ Canary   │   │ Production│  │ Kept 30d │
│ progress │   │ Walk-fwd │   │ 10%      │   │ 90%      │   │ then     │
│          │   │          │   │          │   │          │   │ deleted  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                     │              │
                                     │ Fail         │ Retire
                                     ▼              ▼
                                ┌──────────┐  ┌──────────┐
                                │ REJECTED │  │ RETIRED  │
                                │ Delete   │  │ Document │
                                └──────────┘  └──────────┘
```

---

## 7. Model Risk Governance

### 7.1 Model Risk Categories

| Risk | Definisi | Mitigation |
|------|----------|------------|
| **Model error** | Model produces wrong predictions | OOS validation, walk-forward, drift detection |
| **Model misuse** | Model used outside its intended scope | Document model purpose, limitations |
| **Model drift** | Model becomes stale over time | Auto-retrain weekly, drift monitoring |
| **Model dependency** | System too dependent on one model | Champion/challenger, fallback to factor-only |
| **Model transparency** | Cannot explain why model predicts X | XAI engine (T-032), SHAP values |

### 7.2 Model Risk Assessment

```markdown
## Model Risk Assessment — [Model Name] v[Version]

### Model Purpose
- **What:** Predict N-day forward return for [ticker]
- **Architecture:** LSTM, 2 layers, hidden_dim=256, lookback=60
- **Features:** 20+ technical indicators, normalized

### Performance Metrics
- OOS R²: [value] (target: > 0)
- Directional accuracy: [value] (target: > 55%)
- OOS Sharpe: [value] (target: > 0.5)

### Limitations
- Trained on [date range] data only
- Does not capture black swan events
- Performance degrades in regime changes
- Requires ≥ 252 days of history

### Risk Mitigations
- Weekly retrain (T-025)
- Drift detection daily
- Champion/challenger pattern
- Fallback to factor-only if model unavailable

### Approval
- Validated by: [walk-forward test results]
- Approved by: [developer name]
- Deploy date: [date]
- Next review: [date + 30 days]
```

### 7.3 Model Inventory Review (Monthly)

| Ticker | Model | Version | Status | Health | Last Retrain | OOS R² | Action |
|--------|-------|---------|--------|--------|--------------|--------|--------|
| BBCA.JK | LSTM | 1.1.0 | Champion | 82 | 2026-08-03 | 0.15 | OK |
| TLKM.JK | LSTM | 1.1.0 | Champion | 45 | 2026-08-03 | -0.02 | Retrain |
| ASII.JK | LSTM | 1.0.0 | Champion | 71 | 2026-07-27 | 0.08 | OK |
| ... | ... | ... | ... | ... | ... | ... | ... |

---

## 8. Feature Store Integration

### 8.1 Feature Definitions

Setiap feature yang digunakan model harus terdefinisi di feature store:

```yaml
feature:
  name: rsi_14
  description: Relative Strength Index 14-period
  computation: |
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
  dtype: float
  range: [0, 100]
  freshness: daily (post T-010)
  used_by: [lstm_v1, factor_screener, pattern_detection]
```

### 8.2 Feature Freshness Monitoring

| Feature | Expected Freshness | Check | Alert if |
|---------|-------------------|-------|----------|
| OHLCV | Daily 16:30 WIB | Latest date in ohlcv | > 1 day stale |
| RSI_14 | Daily 18:00 WIB | Latest date in technical_indicators | > 1 day stale |
| foreign_flow | Daily 17:00 WIB | Latest date in foreign_flow | > 1 day stale |
| macro_data | Weekly (Senin) | Latest date in macro_data | > 8 days stale |

### 8.3 Feature Reuse

| Feature | Used By Models |
|---------|---------------|
| `rsi_14` | LSTM, Factor Screener, Pattern Detection, Decision Engine |
| `macd_histogram` | LSTM, Pattern Detection, Technical Analysis |
| `foreign_net_buy` | Sentiment Engine, Prediction Engine, Decision Engine |
| `var_95` | Risk Engine, Portfolio Engine, Decision Engine |

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **23** (ML Trading) | ML algorithms; this doc covers operational lifecycle |
| **39** (Screening/AI/ML) | Pattern memory; this doc covers model governance |
| **46** (Prediksi/Pola/Portfolio) | Prediction pipeline; this doc covers model monitoring |
| **47** (Operational Contract) | T-020 (LSTM), T-025 (Retrain), T-027 (Walk-Forward) |
| **50** (Change/Release) | Model deployment follows change management |
| **58** (Feature Store) | Dedicated feature store document |

---

## Referensi

1. `src/trading_system/ai_learning/engine.py` — Dynamic weight optimization & model registry
2. `src/trading_system/ai_learning/deep_learning.py` — LSTM training (PyTorch CUDA)
3. `src/trading_system/ai_learning/walk_forward.py` — Walk-forward validation
4. `src/trading_system/ai_learning/model_registry.py` — Model versioning & promotion
5. `pustaka/23-machine-learning-trading.md` — ML pipeline, walk-forward, ensemble
6. `pustaka/39-screening-aiml-pattern-memory.md` — Pattern memory & AI/ML screening
7. `pustaka/58-feature-store-engineering-pipeline.md` — Feature store
8. `pustaka/85-backtest-to-live-gap-prevention.md` — Model degradation & backtest-to-live gap
9. Google MLOps: Continuous training & delivery for ML systems
10. López de Prado, M. (2018) — *Advances in Financial Machine Learning* — Model risk management

---

> **Catatan:** MLOps untuk trading system adalah tentang disiplin: model bukan static artifact, tapi living system yang perlu dimonitor, di-retrain, dan di-retire. "Model yang tidak dimonitor adalah model yang sudah broken — Anda hanya belum tahu." Untuk pembahasan bagaimana model degradation berkontribusi pada gap backtest-to-live dan cara mencegahnya, lihat `85-backtest-to-live-gap-prevention.md`.
