# Feature Store & Feature Engineering Pipeline

> **Dokumen 58** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Centralized feature definitions, feature computation pipeline, feature serving (online vs offline), feature freshness monitoring, feature reuse across models.
>
> **Konteks:** Dokumen 23 bahas ML trading. Dokumen 51 bahas MLOps. Tapi belum ada doc tentang feature store: bagaimana features didefinisikan, dihitung, diserved ke model, dan dimonitor untuk freshness.

---

## Daftar Isi

1. [Kenapa Feature Store](#1-kenapa-feature-store)
2. [Feature Catalog](#2-feature-catalog)
3. [Feature Computation Pipeline](#3-feature-computation-pipeline)
4. [Feature Serving](#4-feature-serving)
5. [Feature Freshness Monitoring](#5-feature-freshness-monitoring)
6. [Feature Versioning](#6-feature-versioning)
7. [Feature Reuse Matrix](#7-feature-reuse-matrix)

---

## 1. Kenapa Feature Store

### 1.1 Problem tanpa Feature Store

| Tanpa Feature Store | Dengan Feature Store |
|---------------------|----------------------|
| RSI_14 dihitung di 3 tempat berbeda dengan kode berbeda | RSI_14 didefinisikan sekali, digunakan di mana-mana |
| Feature definition tidak terdokumentasi | Setiap feature punya definisi, range, dtype |
| Tidak tahu feature stale atau fresh | Freshness monitoring per feature |
| Training/serving skew: feature di training berbeda dari serving | Same computation for training dan serving |
| Feature baru sulit di-reuse | Catalog: cari feature, gunakan langsung |

### 1.2 Feature Store Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FEATURE STORE                          │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ DEFINITIONS │  │ COMPUTATION │  │  REGISTRY   │       │
│  │ (YAML)      │  │ (Python)    │  │  (SQLite)   │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│         │                │                │               │
│         └────────┬───────┴────────────────┘               │
│                  ▼                                        │
│         ┌──────────────┐                                  │
│         │ FEATURE TABLE│                                  │
│         │ (SQLite)     │                                  │
│         │ ticker       │                                  │
│         │ date         │                                  │
│         │ feature_name │                                  │
│         │ feature_value│                                  │
│         │ computed_at  │                                  │
│         └──────────────┘                                  │
│                  │                                        │
│         ┌────────┼────────┐                               │
│         ▼        ▼        ▼                               │
│    OFFLINE    ONLINE   FRESHNESS                          │
│    (training) (serving) MONITOR                           │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Feature Catalog

### 2.1 Feature Definition Format

```yaml
# feature_store/definitions/technical.yaml

feature:
  name: rsi_14
  category: technical
  description: "Relative Strength Index 14-period"
  computation: |
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
  dtype: float
  range: [0, 100]
  neutral: 50
  lookback: 14
  frequency: daily
  freshness_sla: 1 hour (post T-010)
  used_by:
    - lstm_v1 (input feature)
    - factor_screener (technical factor)
    - pattern_detection (pattern input)
    - decision_engine (technical sub-score)
  version: "1.0.0"
  dependencies:
    - ohlcv.close
```

### 2.2 Complete Feature Catalog

| Feature | Category | Description | Range | Used By |
|---------|----------|-------------|-------|---------|
| `rsi_14` | technical | RSI 14-period | 0-100 | LSTM, Screener, Pattern, Decision |
| `macd_line` | technical | MACD line (12,26,9) | unbounded | LSTM, Pattern, Decision |
| `macd_histogram` | technical | MACD histogram | unbounded | LSTM, Pattern |
| `bb_position` | technical | Bollinger Band position | 0-1 | LSTM, Screener |
| `atr_14` | technical | ATR 14-period | > 0 | LSTM, Risk (SL/TP) |
| `sma_20` | technical | Simple Moving Average 20 | > 0 | Pattern, Screener |
| `sma_50` | technical | Simple Moving Average 50 | > 0 | Pattern, Screener |
| `sma_200` | technical | Simple Moving Average 200 | > 0 | Pattern, Regime |
| `volume_ratio` | technical | Volume / Avg Volume 20 | 0-10 | LSTM, Pattern |
| `stoch_k` | technical | Stochastic %K | 0-100 | LSTM, Screener |
| `stoch_d` | technical | Stochastic %D | 0-100 | LSTM, Screener |
| `adx_14` | technical | ADX 14-period | 0-100 | LSTM, Regime |
| `obv` | technical | On-Balance Volume | cumulative | Pattern |
| `cci_20` | technical | Commodity Channel Index | unbounded | LSTM |
| `willr_14` | technical | Williams %R | -100-0 | LSTM |
| `foreign_net_buy` | flow | Foreign net buy (Rp) | unbounded | Sentiment, Prediction |
| `foreign_net_buy_ratio` | flow | Foreign net buy / volume | -1 to 1 | Sentiment, Decision |
| `broker_net_buy` | flow | Broker net buy (Rp) | unbounded | Sentiment |
| `fear_greed_index` | sentiment | Fear & Greed Index | 0-100 | Sentiment, Decision |
| `news_sentiment_score` | sentiment | NLP sentiment (-1 to 1) | -1 to 1 | Sentiment, Prediction |
| `social_sentiment` | sentiment | Reddit/X sentiment | -1 to 1 | Sentiment |
| `bi_rate` | macro | BI 7-day reverse repo rate | 0-20 | Macro, Regime |
| `inflation_yoy` | macro | CPI inflation YoY | -5 to 30 | Macro, Regime |
| `usd_idr` | macro | USD/IDR exchange rate | > 0 | Macro, Global |
| `vix` | global | VIX index | 0-100 | Global, Regime |
| `snp500_return_1d` | global | S&P500 1-day return | -10 to 10 | Global |
| `oil_return_1d` | global | Crude oil 1-day return | -10 to 10 | Global |
| `gold_return_1d` | global | Gold 1-day return | -10 to 10 | Global |
| `roe` | fundamental | Return on Equity | -100 to 100 | Fundamental, Screener |
| `pe_ratio` | fundamental | Price-to-Earnings ratio | -100 to 500 | Fundamental, Screener |
| `pb_ratio` | fundamental | Price-to-Book ratio | -10 to 50 | Fundamental, Screener |
| `der` | fundamental | Debt-to-Equity ratio | 0-20 | Fundamental, Screener |
| `revenue_growth_yoy` | fundamental | Revenue growth YoY | -100 to 500 | Fundamental |
| `correlation_bbc` | relationship | Correlation with BBCA.JK | -1 to 1 | Portfolio, Risk |
| `beta_market` | relationship | Beta vs IHSG | -3 to 5 | Risk, Portfolio |
| `prediction_direction` | ai | LSTM prediction direction | UP/DOWN | Decision, XAI |
| `prediction_confidence` | ai | LSTM confidence | 0-100 | Decision, XAI |
| `pattern_detected` | pattern | Detected pattern name | string | Prediction, XAI |
| `pattern_win_rate` | pattern | Pattern historical win rate | 0-100 | Prediction, Decision |
| `regime_label` | regime | HMM regime label | string | Decision, Weights |
| `var_95` | risk | Value at Risk 95% | > 0 | Risk, Portfolio |
| `max_drawdown_252` | risk | Max drawdown 252-day | < 0 | Risk |

---

## 3. Feature Computation Pipeline

### 3.1 Computation Order

```
T-001 (OHLCV) ──▶ T-010 (Technical) ──▶ technical_features
                        │
T-002 (Foreign) ──▶ foreign_features
T-003 (Broker)  ──▶ broker_features
T-005 (Macro)   ──▶ macro_features
T-006 (Global)  ──▶ global_features
                        │
                        ▼
              ┌─────────────────┐
              │ FEATURE TABLE   │
              │ (all features)  │
              └─────────────────┘
                        │
              ┌────────┼────────┐
              ▼        ▼        ▼
          T-015     T-020     T-030
         (Sentiment) (LSTM)  (Decision)
```

### 3.2 Feature Computation Code

```python
# feature_store/compute.py

class FeatureStore:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)

    def compute_and_store(self, ticker, date, feature_name, value):
        """Compute and store a feature value."""
        self.conn.execute("""
            INSERT OR REPLACE INTO feature_store
            (ticker, date, feature_name, feature_value, computed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (ticker, date, feature_name, value, datetime.now()))
        self.conn.commit()

    def get_features(self, ticker, date, feature_names=None):
        """Retrieve features for a ticker on a date."""
        if feature_names:
            placeholders = ",".join("?" * len(feature_names))
            rows = self.conn.execute(f"""
                SELECT feature_name, feature_value
                FROM feature_store
                WHERE ticker = ? AND date = ? AND feature_name IN ({placeholders})
            """, (ticker, date, *feature_names)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT feature_name, feature_value
                FROM feature_store
                WHERE ticker = ? AND date = ?
            """, (ticker, date)).fetchall()

        return {name: value for name, value in rows}

    def get_feature_history(self, ticker, feature_name, days=252):
        """Retrieve feature history for training."""
        rows = self.conn.execute("""
            SELECT date, feature_value
            FROM feature_store
            WHERE ticker = ? AND feature_name = ?
            ORDER BY date DESC LIMIT ?
        """, (ticker, feature_name, days)).fetchall()
        return pd.DataFrame(rows, columns=["date", "value"])
```

---

## 4. Feature Serving

### 4.1 Online vs Offline Serving

| Mode | Use Case | Latency Target | Source |
|------|----------|---------------|--------|
| **Online** | Real-time prediction, API request | < 100ms | In-memory cache |
| **Offline** | Training, backtest, batch | < 1s per ticker | SQLite query |
| **Streaming** | (future) Real-time feature update | < 1s | Event-driven |

### 4.2 Online Serving (Cache)

```python
class OnlineFeatureCache:
    """In-memory cache for fast feature serving."""

    def __init__(self, ttl_seconds=3600):
        self.cache = {}  # (ticker, feature_name) -> (value, timestamp)
        self.ttl = ttl_seconds

    def get(self, ticker, feature_name):
        key = (ticker, feature_name)
        if key in self.cache:
            value, ts = self.cache[key]
            if (datetime.now() - ts).seconds < self.ttl:
                return value
        # Cache miss → query DB
        value = feature_store.get_features(ticker, today, [feature_name])
        if value:
            self.cache[key] = (value[feature_name], datetime.now())
            return value[feature_name]
        return None

    def invalidate(self, ticker=None, feature_name=None):
        """Invalidate cache entries."""
        if ticker and feature_name:
            self.cache.pop((ticker, feature_name), None)
        elif ticker:
            self.cache = {k: v for k, v in self.cache.items() if k[0] != ticker}
        else:
            self.cache.clear()
```

---

## 5. Feature Freshness Monitoring

### 5.1 Freshness Check

```python
def check_feature_freshness():
    """Check all features for freshness."""
    feature_defs = load_feature_definitions()
    issues = []

    for feature in feature_defs:
        latest = get_latest_feature_date(feature.name)
        if latest is None:
            issues.append({"feature": feature.name, "status": "missing",
                          "message": "No data in feature store"})
        elif (datetime.now().date() - latest).days > feature.stale_days:
            issues.append({"feature": feature.name, "status": "stale",
                          "latest_date": latest,
                          "stale_days": (datetime.now().date() - latest).days,
                          "threshold": feature.stale_days})

    return issues
```

### 5.2 Freshness SLA

| Feature Category | Freshness SLA | Stale Threshold | Alert |
|-----------------|---------------|-----------------|-------|
| Technical | Daily 18:00 WIB | > 1 day | SEV-2 |
| Flow (foreign/broker) | Daily 17:00 WIB | > 1 day | SEV-2 |
| Macro | Weekly (Senin) | > 8 days | SEV-2 |
| Global | Daily 16:30 WIB | > 1 day | SEV-2 |
| Fundamental | Quarterly | > 100 days | SEV-3 |
| Sentiment | Daily 18:00 WIB | > 1 day | SEV-2 |
| AI/Prediction | Daily 18:30 WIB | > 1 day | SEV-1 |
| Risk | Daily 18:30 WIB | > 1 day | SEV-2 |

---

## 6. Feature Versioning

### 6.1 Version Convention

```
MAJOR.MINOR.PATCH

MAJOR: Breaking change (different computation formula)
MINOR: New parameter (e.g., RSI 14 → RSI 21 as new feature)
PATCH: Bug fix in computation (same formula, fixed code)
```

### 6.2 Backward Compatibility

- Old feature version tetap tersedia di feature store selama 30 hari setelah new version
- Model yang menggunakan old version tetap berfungsi
- Setelah 30 hari: migrate model to new version, deprecate old

---

## 7. Feature Reuse Matrix

| Feature | LSTM | Factor Screener | Pattern Detect | Sentiment | Decision | Risk | Portfolio | XAI |
|---------|------|----------------|----------------|-----------|----------|------|-----------|-----|
| `rsi_14` | ✅ | ✅ | ✅ | — | ✅ | — | — | ✅ |
| `macd_histogram` | ✅ | — | ✅ | — | ✅ | — | — | ✅ |
| `bb_position` | ✅ | ✅ | — | — | — | — | — | — |
| `atr_14` | ✅ | — | — | — | — | ✅ | — | ✅ |
| `volume_ratio` | ✅ | ✅ | ✅ | — | — | — | — | — |
| `foreign_net_buy` | — | — | — | ✅ | ✅ | — | — | ✅ |
| `fear_greed_index` | — | — | — | ✅ | ✅ | — | — | ✅ |
| `bi_rate` | — | — | — | — | ✅ | — | — | ✅ |
| `vix` | — | — | — | — | ✅ | — | — | ✅ |
| `roe` | — | ✅ | — | — | ✅ | — | — | ✅ |
| `pe_ratio` | — | ✅ | — | — | ✅ | — | — | ✅ |
| `beta_market` | — | — | — | — | — | ✅ | ✅ | — |
| `var_95` | — | — | — | — | — | ✅ | ✅ | ✅ |
| `prediction_direction` | — | — | — | — | ✅ | — | ✅ | ✅ |
| `pattern_win_rate` | — | — | — | — | ✅ | — | — | ✅ |
| `regime_label` | — | — | — | — | ✅ | — | — | ✅ |

**Total unique features:** 42
**Max reuse:** `rsi_14` (8 consumers), `foreign_net_buy` (4 consumers)

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **23** (ML Trading) | ML models consume features from feature store |
| **51** (MLOps) | Feature store is part of MLOps lifecycle |
| **47** (Operational Contract) | T-010 (technical) computes features |
| **22** (Data Engineering) | Pipeline feeds feature store |
| **53** (Data Governance) | Feature store is governed data asset |

---

## Referensi

1. `src/trading_system/analysis/pipeline.py` — Feature computation pipeline
2. `src/trading_system/analysis/technical.py` — Technical indicator features
3. `src/trading_system/analysis/fundamental.py` — Fundamental features
4. `src/trading_system/ai_learning/engine.py` — Feature consumption for ML
5. `pustaka/22-data-engineering-pipeline.md` — Data pipeline feeds feature store
6. `pustaka/23-machine-learning-trading.md` — ML feature engineering
7. `pustaka/51-mlops-model-risk-management.md` — Feature store in MLOps lifecycle
8. Feast: Open-source feature store (feast.dev)
9. Tecton: Feature Store for Machine Learning

---

> **Catatan:** Feature store adalah single source of truth untuk features. "Compute once, use everywhere." Training/serving skew adalah silent killer — feature store mencegahnya dengan unified definition dan computation.
