# Flow, Logic, Testing, Aturan Aplikasi, dan KPI

> **Tujuan:** Dokumen ini adalah referensi definitif untuk semua flow sistem, business logic, strategi testing, aturan aplikasi, dan Key Performance Indicators (KPI) yang wajib ada dalam sistem aplikasi pasar modal. Mencakup: data flow end-to-end, decision logic, state machine, validation rules, test strategy, CI/CD pipeline, dan metrik kinerja sistem.

---

## Daftar Isi

1. [Data Flow End-to-End](#1-data-flow-end-to-end)
2. [Process Flow per Engine](#2-process-flow-per-engine)
3. [Business Logic](#3-business-logic)
4. [State Machine](#4-state-machine)
5. [Aturan Aplikasi](#5-aturan-aplikasi)
6. [Validation Rules](#6-validation-rules)
7. [Testing Strategy](#7-testing-strategy)
8. [Test Plan Lengkap](#8-test-plan-lengkap)
9. [CI/CD Pipeline](#9-cicd-pipeline)
10. [KPI Sistem](#10-kpi-sistem)
11. [KPI Engine](#11-kpi-engine)
12. [KPI Bisnis](#12-kpi-bisnis)
13. [SLA dan Threshold](#13-sla-dan-threshold)
14. [Monitoring & Alerting](#14-monitoring--alerting)
15. [Error Handling & Recovery](#15-error-handling--recovery)
16. [Security Rules](#16-security-rules)
17. [Configuration Management](#17-configuration-management)
18. [Checklist QA](#18-checklist-qa)

---

## 1. Data Flow End-to-End

### 1.1 Alur Keputusan Lengkap (11 Tahap)

```
[1] Scheduler memicu Data Acquisition Engine
        │
        ▼
[2] Data Acquisition Engine → fetch & normalize → publish event data.raw.*
        │
        ▼
[3] Data Quality Validation Engine → validasi, cross-check, reconcile
        │  (gagal validasi → flag anomali → Monitoring Engine → alert)
        ▼
[4] Data Storage (clean_zone) → publish event data.clean.*
        │
        ├──────────────► Fundamental Analysis Engine ─┐
        ├──────────────► Technical Analysis Engine ───┤
        ├──────────────► Macro Economic Engine ────────┤
        ├──────────────► Global Market Engine ─────────┼──► analysis.*.score
        ├──────────────► News & Sentiment Engine ───────┤
        ├──────────────► Corporate Action Engine ───────┘
        │
        ▼
[5] Market Relationship Engine (mengonsumsi data.clean.* + analysis.macro.regime)
        │  → analysis.relationship.updated
        ▼
[6] Decision Engine
        │  - collect_scores() dari semua event analysis.*.score
        │  - apply_regime_filter()
        │  - kirim kandidat ke Risk Engine
        ▼
[7] Risk Engine → risk.assessment.completed (position size, SL/TP, risk flags)
        │
        ▼
[8] Decision Engine → apply_risk_filter() → decision.recommendation.created
        │
        ├──► Explainable AI Engine → xai.explanation.generated
        ├──► Portfolio Engine → portfolio.rebalance.generated
        └──► Presentation Layer (Dashboard, Alerts)
        ▼
[9] Execution Engine → execution.order.filled / rejected
        │
        ▼
[10] Backtesting Engine (offline) / Paper Trading Module (live)
        │  → trade_history, equity_curve
        ▼
[11] AI Learning Engine → retrain factor_weights & regime_model
        │
        └──► kembali memengaruhi Decision Engine (langkah 6) pada siklus berikutnya
```

### 1.2 Alur Data Harian (Daily Runner)

```
06:00 WIB  ── Scheduler trigger ──
                │
                ▼
06:05       Fetch OHLCV (Yahoo Finance, ~951 tickers aktif)
                │  Rate limit: 1 call/detik
                │  Retry: 3x dengan exponential backoff
                ▼
06:30       Validate (completeness, plausibility, gap)
                │  Skor < 70 → reject, alert
                ▼
06:35       Save to SQLite (INSERT OR REPLACE)
                │
                ▼
06:40       Fetch IDX foreign flow & broker summary (idx.co.id)
                │  Rate limit: 0.3s/req
                ▼
07:00       Compute scores (Analysis Pipeline)
                │  Technical → Fundamental → Macro → Global → Relationship → Sentiment
                ▼
07:15       Save scores to database
                │
                ▼
17:00       Decision Engine → generate recommendations
                │  Risk Engine → position sizing, SL/TP
                │  XAI Engine → narrative explanation
                ▼
17:05       Paper Trading simulation (if enabled)
                │
                ▼
17:10       Telegram notification (if configured)
                │
                ▼
17:15       Save equity snapshot
                │
                ▼
DONE        Audit log: semua event tercatat
```

### 1.3 Alur Eksekusi Otomatis (Robot Trader)

```
Trigger: run_loop(tickers, interval=15s)
        │
        ▼
┌─── process_signal(ticker) ───────────────────────────┐
│                                                       │
│  1. DecisionEngine.recommend(ticker)                  │
│        │                                              │
│        ├─ action == BUY dan tidak ada posisi?          │
│        │   └─ RiskEngine.analyze(ticker)               │
│        │      └─ Hitung shares, entry, SL, TP          │
│        │         └─ ExecutionEngine.simulate_fill()    │
│        │            └─ Save order + position           │
│        │               └─ Telegram notification       │
│        │                                              │
│        ├─ action == SELL/AVOID dan ada posisi?         │
│        │   └─ ExecutionEngine.simulate_fill(SELL)      │
│        │      └─ Close position, realize PnL           │
│        │         └─ Telegram notification             │
│        │                                              │
│        └─ action == HOLD/WATCHLIST?                    │
│            └─ Log only, no execution                   │
│                                                       │
│  2. monitor_positions()                               │
│        ├─ price <= stop_loss? → SELL (stop-loss hit)   │
│        ├─ price >= take_profit? → SELL (take-profit)   │
│        ├─ price > highest_since_entry?                 │
│        │   └─ Update trailing stop                     │
│        └─ daily_loss > DAILY_LOSS_LIMIT?                │
│            └─ Halt trading, persist halt state          │
│                                                       │
└───────────────────────────────────────────────────────┘
        │
        ▼
    sleep(interval) → loop
```

### 1.4 Alur Backtest

```
Input: ticker, strategy, start_date, end_date, initial_capital
        │
        ▼
[1] Load OHLCV dari storage (date range)
        │
        ▼
[2] strategy.generate_signals(df) → DataFrame dengan kolom 'signal'
        │  signal: 1=BUY, -1=SELL, 0=HOLD
        ▼
[3] Iterasi setiap baris (event-driven):
        │
        ├─ Hitung equity = capital + position * price
        │
        ├─ Sinyal BUY dan tidak ada posisi:
        │   ├─ Entry price = open bar berikutnya (anti look-ahead)
        │   ├─ Slippage: fill_price = open * (1 + slippage)
        │   ├─ Shares = (capital * 0.99) // fill_price
        │   ├─ Round ke IDX lot size (100)
        │   ├─ Round fill_price ke tick size IDX
        │   ├─ Deduct fees (broker + levy)
        │   └─ Catat trade ke audit log
        │
        ├─ Sinyal SELL dan ada posisi:
        │   ├─ Exit price = open bar berikutnya
        │   ├─ Slippage: fill_price = open * (1 - slippage)
        │   ├─ Round ke tick size IDX
        │   ├─ Deduct fees (broker + levy + PPh 0.1%)
        │   ├─ Hitung realized PnL
        │   └─ Catat trade ke audit log
        │
        └─ Catat equity point ke equity_curve
        │
        ▼
[4] Force close posisi yang masih terbuka di akhir periode
        │
        ▼
[5] Hitung benchmark equity curve (IHSG buy & hold)
        │
        ▼
[6] compute_metrics(trade_history, equity_curve, benchmark)
        │  → 15 metrik (Total Return, CAGR, Sharpe, Sortino, Calmar,
        │    Max DD, Win Rate, Profit Factor, Avg Win/Loss,
        │    Expectancy, Volatility, Beta, Alpha, Exposure Time)
        ▼
Output: backtest_report + trade_history + equity_curve
```

---

## 2. Process Flow per Engine

### 2.1 Technical Analysis Engine Flow

```
Input: OHLCV DataFrame
        │
        ▼
[1] Compute indicators
        ├─ MA20, MA50 (trend)
        ├─ ADX14 (trend strength)
        ├─ RSI14 (momentum)
        ├─ MACD(12,26,9) (trend confirmation)
        ├─ ATR14 (volatility)
        ├─ Bollinger Bands(20, 2σ) (range)
        ├─ Volume SMA20 (baseline)
        └─ Volatility annualized (20-day)
        │
        ▼
[2] Classify trend regime
        ├─ MA20 > MA50 dan close > MA20 → Uptrend
        ├─ MA20 < MA50 dan close < MA20 → Downtrend
        └─ Else → Sideways
        │
        ▼
[3] Volume Profile
        ├─ Histogram 10 bin by close price
        ├─ POC = price with max volume
        ├─ VAH = upper 70% boundary
        └─ VAL = lower 30% boundary
        │
        ▼
[4] Score computation (0-100)
        ├─ Trend: 25/12/0
        ├─ RSI: (RSI - 30) * (25/40), clamped 0-25
        ├─ MACD: 25 if MACD > Signal, else 0
        ├─ Volatility: max(0, 25 - vol*100)
        └─ Volume: min(25, vol_ratio * 12.5)
        │
        ▼
Output: {score, breakdown, regime, indicators, volume_profile}
```

### 2.2 Decision Engine Flow

```
Input: ticker
        │
        ▼
[1] collect_scores(ticker)
        │  Query scores table untuk 6 engine:
        │  technical, fundamental, macro, global, relationship, sentiment
        │
        ▼
[2] Get factor weights
        │  Priority:
        │  1. AI-trained weights (if fresh <7 days)
        │  2. Regime-specific + consistency-adjusted
        │  3. DEFAULT_WEIGHTS
        │
        ▼
[3] apply_regime_filter(scores, macro_regime)
        ├─ Tightening: macro * 0.8, technical * 0.9
        ├─ Easing: macro * 1.1 (max 100), fundamental * 1.05 (max 100)
        └─ Other: no adjustment
        │
        ▼
[4] compute_conviction(filtered_scores, weights)
        │  conviction = sum(score[k] * weight[k]) / sum(weight[k])
        │  (weight redistribution untuk engine yang tidak punya skor)
        │
        ▼
[5] RiskEngine.analyze(ticker)
        │  → position_size, stop_loss, take_profit, risk_flags
        │
        ▼
[6] decide_action(conviction, risk_flags)
        ├─ HIGH_VOLATILITY or LIQUIDITY_LOW in risk_flags?
        │   └─ conviction < 60 → AVOID
        ├─ conviction >= 70 → BUY
        ├─ conviction >= 55 → WATCHLIST
        ├─ conviction >= 40 → HOLD
        ├─ conviction < EXIT_CONVICTION_THRESHOLD (40) → AVOID
        │   └─ If position exists → SELL
        │
        ▼
[7] Build recommendation object
        │  {action, conviction, position_size, entry_range, SL, TP,
        │   hold_period, risk_flags, contributing_scores}
        │
        ▼
[8] Audit log: decision.recommendation.created
        │
        ▼
Output: recommendation dict
```

### 2.3 Sentiment Engine Flow (6 Sources)

```
Input: ticker
        │
        ▼
┌─── Source 1: Foreign Flow ──────────────────────┐
│  Proxy dari OHLCV:                              │
│  - Large volume + price up = accumulation       │
│  - Large volume + price down = distribution     │
│  Score: 0-100, label: accumulation/distribution │
│  Weight: 0.25                                   │
└─────────────────────────────────────────────────┘
┌─── Source 2: Broker Summary ────────────────────┐
│  IDX broker summary harian:                     │
│  - Smart money net buy = bullish                │
│  - Smart money net sell = bearish               │
│  - Retail buy + smart sell = contrarian bearish │
│  Weight: 0.20                                   │
└─────────────────────────────────────────────────┘
┌─── Source 3: IDX Historical ────────────────────┐
│  Pre-computed dari idx_sentiment_data:           │
│  - sentiment_score (-1..1) → skala 0-100        │
│  Weight: 0.20                                   │
└─────────────────────────────────────────────────┘
┌─── Source 4: Social Media ──────────────────────┐
│  Reddit (r/IndonesiaInvesting, r/saham):        │
│  X/Twitter (ticker hashtag search):             │
│  - Tokenisasi + Indonesian lexicon              │
│  - Emoji detection                              │
│  - Volume spike = increasing attention          │
│  Weight: 0.15                                   │
└─────────────────────────────────────────────────┘
┌─── Source 5: Google Trends ─────────────────────┐
│  Search interest via pytrends:                  │
│  - Rising = bullish (momentum)                  │
│  - Falling = bearish (waning interest)          │
│  - Volume > 2x average = viral attention        │
│  Weight: 0.10                                   │
└─────────────────────────────────────────────────┘
┌─── Source 6: News NLP ──────────────────────────┐
│  RSS feeds (Bisnis.com, Kontan, CNBC ID):       │
│  - Fetch + filter by ticker keyword             │
│  - Tokenisasi headline + body                   │
│  - Sentiment: (pos - neg) / total               │
│  - Negation detection ("tidak untung")          │
│  - Fallback: price & volume proxy               │
│  Weight: 0.10                                   │
└─────────────────────────────────────────────────┘
        │
        ▼
Aggregate: weighted average (normalize if sources missing)
        │
        ▼
Save sub-source scores to database
        │
        ▼
Output: {score: 0-100, label, breakdown per source}
```

---

## 3. Business Logic

### 3.1 Scoring Logic

Setiap engine menghasilkan skor 0-100 dengan bobot berbeda:

| Engine | Bobot Default | Logika Skor | Fallback |
|--------|---------------|-------------|----------|
| **Technical** | 20% | Trend (25) + RSI (25) + MACD (25) + Vol (25) + Volume (25) | Tidak ada |
| **Fundamental** | 25% | PER (25) + PBV (25) + ROE (25) + DER (25) + Growth (25) | saham_snapshot → idx_financial_statements → netral 12.5 |
| **Macro** | 15% | US10Y (25) + Gold (25) + Oil (25) + USD/IDR (25) | Tidak ada |
| **Global** | 15% | Above MA50 (50) + Above MA200 (50) | Tidak ada |
| **Relationship** | 10% | Avg \|correlation\| * 100 | Tidak ada |
| **Sentiment** | 15% | Weighted 6 sources | Price & volume proxy |

### 3.2 Weight Redistribution

Ketika engine tidak memiliki skor (data tidak tersedia), bobotnya didistribusikan ke engine lain:

```python
conviction = sum(score[k] * weight[k] for k in weights if k in scores) / sum(weight[k])
```

Hanya bobot untuk engine yang **memiliki** skor yang dihitung. Ini mencegah penaltian tidak adil ketika data fundamental tidak tersedia untuk saham .JK.

### 3.3 Regime-Aware Adjustment

| Regime | Engine yang Disesuaikan | Adjustment |
|--------|------------------------|------------|
| **Tightening** | macro, technical | macro × 0.8, technical × 0.9 |
| **Easing** | macro, fundamental | macro × 1.1 (max 100), fundamental × 1.05 (max 100) |
| **Growth** | — | Tidak ada |
| **Slowdown** | — | Tidak ada |
| **Neutral** | — | Tidak ada (DEFAULT_WEIGHTS) |

### 3.4 AI Learning Logic

#### Consistency Adjustment

| Kondisi | Adjustment | Alasan |
|---------|------------|--------|
| Mean ≥ 60 + std < 15 | weight × 1.15 | Engine reliable, skor konsisten |
| Mean ≥ 50 + std < 20 | weight × 1.05 | Engine cukup reliable |
| Mean < 40 atau std > 25 | weight × 0.80 | Engine unreliable, skor volatile |
| No data | weight × 0.85 | Engine tidak punya histori |

#### Data Coverage Adjustment (Fundamental)

| Coverage | Adjustment | Alasan |
|----------|------------|--------|
| < 0.4 | weight × 0.5 | Data sangat terbatas |
| < 0.6 | weight × 0.7 | Data terbatas |
| == 0 | weight = 0 | Data tidak tersedia sama sekali |

#### Linear Regression Training

```python
# 1. Ambil historical scores dan OHLCV
# 2. Compute forward return: next_close / close - 1
# 3. Pivot scores: satu row per date, kolom = engine scores
# 4. Standardize features dengan StandardScaler
# 5. Train LinearRegression: X = scores, y = forward return
# 6. Clip negative coefficients: np.maximum(coef, 0)
#    (faktor negatif = tidak prediktif, bukan anti-prediktif)
# 7. Normalize weights: total = 1.0
# 8. Simpan ke database
```

### 3.5 Risk Logic

#### Position Sizing

```python
stop_distance = 1.5 * ATR
stop_loss = last_price - stop_distance
take_profit = last_price + 2 * stop_distance    # R:R = 1:2

risk_amount = capital * 0.01                     # 1% risk per trade
position_value = risk_amount / (stop_distance / last_price)
position_size = min(position_value / capital, 0.10)  # Max 10% modal
```

#### Risk Flags

| Flag | Kondisi | Dampak |
|------|---------|--------|
| `LIQUIDITY_LOW` | target_value > adv_value * 1% | Slippage 5bps → 20bps |
| `HIGH_VOLATILITY` | Vol annualized > 50% | conviction < 60 → AVOID |

#### Circuit Breaker

| Trigger | Tindakan |
|---------|----------|
| Daily loss > `DAILY_LOSS_LIMIT` | Halt trading, persist halt state |
| Portfolio drawdown > threshold | Stop new entries |
| Auto-reject IDX ±15% | Pause trading untuk ticker |

### 3.6 Execution Logic

#### Cost Model IDX

```
Buy:
  total_cost = order_value * (1 + broker_fee + levy + slippage)
  broker_fee = 0.15%
  levy = 0.00043%
  slippage = 0.05% (dinamis, lihat §2.1 di file 18)

Sell:
  total_cost = order_value * (broker_fee + levy + PPh + slippage)
  broker_fee = 0.15%
  levy = 0.00043%
  PPh = 0.1% (final tax)
  slippage = 0.05% (dinamis)
```

#### Slippage Dinamis

| Rasio order/ADV | Slippage | Logic |
|-----------------|----------|-------|
| < 0.1% | 0.05% | Default, order kecil |
| 0.1%-1% | 0.10% | 2x default, order sedang |
| > 1% | 0.20% | 4x default, order besar |

---

## 4. State Machine

### 4.1 State Machine Rekomendasi

```
                    ┌──────────┐
                    │  AVOID   │◄──────── conviction < 40
                    └──────────┘           atau risk flag + conviction < 60
                         │
                         │ conviction naik ≥ 40
                         ▼
                    ┌──────────┐
                    │   HOLD   │◄──────── 40 ≤ conviction < 55
                    └──────────┘
                         │
                         │ conviction naik ≥ 55
                         ▼
                    ┌──────────┐
                    │WATCHLIST │◄──────── 55 ≤ conviction < 70
                    └──────────┘
                         │
                         │ conviction naik ≥ 70
                         ▼
                    ┌──────────┐
                    │   BUY    │──────── conviction turun < 70
                    └──────────┘         │
                         │               │
                         │ conviction    │ conviction turun < 40
                         │ turun < 55    ▼
                         │          ┌──────────┐
                         │          │   SELL   │ (jika ada posisi)
                         │          └──────────┘
                         ▼
                    ┌──────────┐
                    │   HOLD   │
                    └──────────┘
```

### 4.2 State Machine Posisi

```
┌─────────┐     BUY order      ┌─────────┐     SL/TP hit     ┌─────────┐
│  EMPTY  │──────────────────►│  OPEN   │──────────────────►│ CLOSED  │
│         │                   │         │                   │         │
└─────────┘                   └─────────┘                   └─────────┘
                                  │  ▲                          │
                                  │  │ Trailing stop update     │
                                  │  │                          │
                                  │  └──────────────────┐      │
                                  │                     │      │
                                  │ SELL signal         │      │
                                  ▼                     │      │
                              ┌─────────┐               │      │
                              │ CLOSING │───────────────┘      │
                              └─────────┘                      │
                                                               │
                                                               ▼
                                                          Realized PnL
                                                          recorded in
                                                          orders table
```

### 4.3 State Machine Auto-Trade

```
                    ┌──────────────┐
                    │  MONITORING  │ (AUTO_TRADE_ENABLED=false)
                    │  (log only)  │
                    └──────────────┘
                          │  toggle ON
                          ▼
                    ┌──────────────┐
                    │   TRADING    │ (AUTO_TRADE_ENABLED=true)
                    │  (execute)   │
                    └──────────────┘
                          │  daily_loss > LIMIT
                          ▼
                    ┌──────────────┐
                    │   HALTED     │ (circuit breaker)
                    │  (no trade)  │
                    └──────────────┘
                          │  manual reset
                          ▼
                    ┌──────────────┐
                    │   TRADING    │
                    └──────────────┘
```

### 4.4 State Machine Data Quality

```
┌───────────┐  score ≥ 90   ┌──────────┐
│  RAW DATA │──────────────►│ ACCEPTED │ ──► Save to clean_zone
│           │               └──────────┘
│           │  score 70-89  ┌──────────┐
│           │──────────────►│  FLAGGED │ ──► Save + flag for review
│           │               └──────────┘
│           │  score < 70   ┌──────────┐
│           │──────────────►│ REJECTED │ ──► Alert, do NOT save
└───────────┘               └──────────┘
```

---

## 5. Aturan Aplikasi

### 5.1 Prinsip Utama

| # | Prinsip | Implementasi |
|---|---------|--------------|
| 1 | **Data First** | Setiap data wajib melalui validation sebelum digunakan |
| 2 | **Backtestable First** | Setiap strategi wajib dapat diuji secara historis |
| 3 | **Modular & Decoupled** | Setiap engine dapat dikembangkan dan diganti secara independen |
| 4 | **Explainable** | Setiap rekomendasi wajib dapat dijelaskan (XAI) |
| 5 | **Risk-Aware** | Risk Engine wajib berjalan sebelum Decision Engine |
| 6 | **Continuous Learning** | AI membantu menemukan pola, bukan mengambil alih keputusan |
| 7 | **Audit Trail** | Semua keputusan tercatat dalam audit log (append-only) |
| 8 | **Safe by Default** | Auto-trade default OFF, paper mode default |
| 9 | **Single Source of Truth** | Konfigurasi terpusat di `config.py`, tidak hardcoded |
| 10 | **Fail-Fast** | Error tidak ditelan, exception di-raise |

### 5.2 Aturan Data

| # | Aturan | Konsekuensi Pelanggaran |
|---|--------|------------------------|
| D1 | Data wajib melalui validation sebelum storage | Data corrupt masuk sistem |
| D2 | Skor kualitas < 70 → data ditolak | Sinyal dari data buruk |
| D3 | Gap > 5 hari → flag anomali | Backtest tidak akurat |
| D4 | Harga ≤ 0 atau low > high → reject | Skor engine tidak valid |
| D5 | Volume > 10x median → flag | False signal |
| D6 | Data macro/global basi (>1 hari bursa) → re-fetch | Skor tidak relevan |
| D7 | Raw data disimpan di Parquet (staging) | Tidak ada audit trail |
| D8 | Clean data di SQLite (WAL mode) | Tidak ada ACID guarantee |
| D9 | Audit log bersifat append-only | Tidak ada traceability |
| D10 | Data watermark per ticker per tabel | Tidak tahu data sampai kapan |

### 5.3 Aturan Trading

| # | Aturan | Implementasi |
|---|--------|--------------|
| T1 | Risk per trade maksimal 1% modal | `RISK_PER_TRADE = 0.01` |
| T2 | Position size maksimal 10% modal per saham | `min(position_value / capital, 0.10)` |
| T3 | Stop-loss wajib untuk setiap posisi BUY | `stop_loss = entry - 1.5 * ATR` |
| T4 | Risk-reward ratio minimum 1:2 | `take_profit = entry + 2 * stop_distance` |
| T5 | Exit jika conviction < 40 dan ada posisi | `EXIT_CONVICTION_THRESHOLD = 40` |
| T6 | Daily loss limit → halt trading | `DAILY_LOSS_LIMIT` env var |
| T7 | Auto-trade default OFF | `AUTO_TRADE_ENABLED = false` |
| T8 | Paper mode default | `TRADING_MODE = "paper"` |
| T9 | Shares dibulatkan ke lot IDX (100) | `IDX_LOT_SIZE = 100` |
| T10 | Harga dibulatkan ke tick size IDX | `round_to_tick(price)` |
| T11 | PPh final 0.1% hanya untuk sell | `DEFAULT_BROKER_FEE_SELL = 0.0025` |
| T12 | Settlement T+2 untuk saham IDX | Konvensi BEI |

### 5.4 Aturan AI/ML

| # | Aturan | Alasan |
|---|--------|--------|
| A1 | Koefisien negatif di-clip ke 0, bukan `np.abs` | Faktor negatif = tidak prediktif, bukan anti-prediktif |
| A2 | Minimal 60 sampel untuk training LR | Rule of thumb: 10 sampel per fitur (6 fitur) |
| A3 | TimeSeriesSplit (purged) untuk cross-validation | Mencegah look-ahead bias |
| A4 | Walk-forward optimization untuk validasi | Simulasi kondisi real-time |
| A5 | AI memberi bobot, bukan otoritas final | Keputusan tetap dapat diaudit |
| A6 | Simpan riwayat performa AI vs default (A/B) | Validasi AI tidak degradasi |
| A7 | Regime-aware weights | Bobot berbeda per kondisi pasar |
| A8 | Consistency adjustment berdasarkan histori | Engine unreliable → bobot turun |
| A9 | Data coverage adjustment untuk fundamental | Data .JK terbatas → bobot turun |
| A10 | Model registry dengan versioning | Reproducibility |

### 5.5 Aturan API

| # | Aturan | Implementasi |
|---|--------|--------------|
| P1 | API key via `X-API-Key` header | `secrets.compare_digest` (anti timing-attack) |
| P2 | API key wajib non-kosong di production | `ENV=production` → fail-fast |
| P3 | Rate limit 60 req/min per IP | In-memory, cleanup otomatis 60s |
| P4 | NaN/Inf → `null` di JSON response | `SanitizedJSONResponse` |
| P5 | Endpoint sensitif wajib API key | `/api/execution/toggle`, `/api/rebalance/toggle` |
| P6 | WebSocket auth via `?token=` query param | `/ws/live?token=<api_key>` |
| P7 | Correlation ID untuk setiap request | `X-Correlation-ID` header |
| P8 | Empty body diterima untuk POST tertentu | `Body(default_factory=dict)` |
| P9 | Pagination validation (max 1000 per page) | Cegah DoS |
| P10 | CORS terbatas ke `localhost:3000` | `CORS_ORIGINS` env var |

### 5.6 Aturan Backtest

| # | Aturan | Alasan |
|---|--------|--------|
| B1 | Eksekusi di open bar berikutnya (`shift(-1)`) | Anti look-ahead bias |
| B2 | Shares dibulatkan ke lot IDX (100) | Konsisten dengan live trading |
| B3 | Fill price dibulatkan ke tick size IDX | Konsisten dengan aturan BEI |
| B4 | Biaya transaksi realistis (fee + levy + PPh + slippage) | Profit tidak inflated |
| B5 | Point-in-time safety (`merge_asof direction="backward"`) | Hanya gunakan skor yang tersedia |
| B6 | Sertakan saham delisted | Anti survivorship bias |
| B7 | Walk-forward + out-of-sample testing | Anti overfitting |
| B8 | Monte Carlo dengan block bootstrap | Preserve autokorelasi |
| B9 | Benchmark vs IHSG buy & hold | Baseline pembanding |
| B10 | Risk-free rate 5% (asumsi SBN) | Sharpe/Alpha realistis |

---

## 6. Validation Rules

### 6.1 Data Validation

| Rule | Field | Kondisi | Severity | Action |
|------|-------|---------|----------|--------|
| V1 | open, high, low, close | ≤ 0 | High | Reject, skor -2.0 |
| V2 | low vs high | low > high | High | Reject, skor -2.0 |
| V3 | close vs [low, high] | close < low atau close > high | High | Reject, skor -2.0 |
| V4 | volume | > 10x median | Low | Flag, skor -1.0 |
| V5 | timestamp | Gap > 5 hari | Low | Flag, skor -0.5 |
| V6 | NaN per kolom | missing_pct > 0 | Medium | Skor -missing_pct * 2 |
| V7 | adjusted_close | = close (sementara) | — | Diisi validator |
| V8 | ingested_at | Mixed datetime format | — | `format="mixed", utc=True` |

### 6.2 Input Validation API

| Rule | Endpoint | Validasi |
|------|----------|---------|
| IV1 | `GET /api/data/{category}` | category ∈ {ohlcv, fundamental, macro, news} |
| IV2 | `GET /api/data/ohlcv` | ticker wajib, start/end optional, max 5000 rows |
| IV3 | `POST /api/backtest` | ticker wajib, strategy ∈ {buy_hold, ma_crossover, conviction} |
| IV4 | `POST /api/scores/compute` | ticker wajib, period optional (default 2y) |
| IV5 | `POST /api/fetch` | ticker wajib, period ∈ {1mo, 3mo, 6mo, 1y, 2y, 5y, max} |
| IV6 | `GET /api/audit` | pagination max 1000, filter by event_type/actor |
| IV7 | `DELETE /api/*` | before_date format ISO8601 |
| IV8 | `POST /api/ai/train` | ticker wajib, min_samples default 60 |

### 6.3 Business Validation

| Rule | Kondisi | Error |
|------|---------|-------|
| BV1 | Position size > 10% modal | `ValueError: position_size exceeds max` |
| BV2 | Order value > available cash | `feasible = False` |
| BV3 | Shares tidak bulat per lot 100 | `round(shares / 100) * 100` |
| BV4 | Fill price tidak di tick size | `round_to_tick(price)` |
| BV5 | Ticker tidak berakhiran `.JK` untuk equity | Filter `asset_class = 'equity'` |
| BV6 | Unknown column in update_position | `ValueError: Unknown column` |
| BV7 | Unsafe path (directory traversal) | `safe_path()` returns None |
| BV8 | API key kosong di production | Fail-fast, return 500 |

---

## 7. Testing Strategy

### 7.1 Pyramid Testing

```
                    ┌───────────┐
                    │    E2E    │  Playwright (browser automation)
                    │  ~5 tests │  Dashboard, chart, API integration
                   ┌┴───────────┴┐
                   │ Integration │  API endpoint tests, cross-module
                   │  ~50 tests  │  Pipeline, storage+engine
                  ┌┴─────────────┴┐
                  │     Unit      │  750+ tests across 51 files
                  │  ~750 tests   │  Every engine, every function
                 ─┴───────────────┴─
                  │  Property     │  Hypothesis (invariants)
                  │  ~10 tests    │  Equity ≥ 0, win rate ∈ [0,1]
                 ─┴───────────────┴─
```

### 7.2 Test Categories

| Kategori | Jumlah | Fokus | Framework |
|----------|--------|-------|-----------|
| **Core Engine** | ~200 | Technical, Fundamental, Macro, Global, Sentiment, Decision, Risk, XAI, AI Learning, Backtest, Paper Trading, Monitoring | pytest |
| **Execution** | ~80 | Execution Engine, Interface, Automated, Broker Adapter | pytest |
| **Data Layer** | ~60 | Storage CRUD, Validation, Data Source, Archive, Import Legacy | pytest |
| **API & CLI** | ~100 | 88 endpoints, CRUD, 17 CLI subcommands | pytest |
| **TIP Components** | ~155 | 6 layers (Data Quality, Advanced Technical, Alpha, Risk, AI, Validation) | pytest |
| **Property-Based** | ~10 | Invariants: equity ≥ 0, PnL consistent, win rate ∈ [0,1] | Hypothesis |
| **E2E** | ~5 | Dashboard load, ticker switch, chart render, comprehensive | Playwright |
| **P2 Fix** | ~20 | Adjusted close, data source adapter, WAL+Alembic, WebSocket | pytest |

### 7.3 Test Discipline

| # | Aturan | Alasan |
|---|--------|--------|
| TD1 | Design/update tests **before** major implementation | Test-driven development |
| TD2 | **Never** delete or weaken tests without explicit direction | Regresi tersembunyi |
| TD3 | Coverage minimum 50% | `fail_under = 50` di `pyproject.toml` |
| TD4 | Fixture `autouse` untuk reset state | Isolasi test |
| TD5 | Realistic data fixtures (bukan dummy minimal) | Cakupan edge case |
| TD6 | Test plan terdokumentasi (`docs/TEST_PLAN.md`) | Onboarding tester |
| TD7 | Property-based test untuk invariants matematis | Hypothesis menemukan edge case |
| TD8 | 0 warnings policy | `pytest -W error` |
| TD9 | Test CLI subcommands via `capsys` | Mencegah dead code |
| TD10 | E2E wajib backend + frontend running | Integrasi nyata |

### 7.4 Test Environment

```python
# conftest.py — shared fixtures
@pytest.fixture(autouse=True)
def reset_api_key(monkeypatch):
    """Reset API key untuk deterministic testing."""
    monkeypatch.setattr("trading_system.utils.notifier._API_KEY", "")

@pytest.fixture
def storage(tmp_path):
    """Temporary SQLite database untuk setiap test."""
    return DataStorage(db_path=tmp_path / "test.db")

@pytest.fixture
def sample_ohlcv():
    """Realistic OHLCV data untuk testing."""
    return pd.DataFrame({
        "ticker": ["BBCA.JK"] * 100,
        "timestamp": pd.date_range("2026-01-01", periods=100, freq="D"),
        "open": np.random.uniform(8000, 9000, 100),
        "high": np.random.uniform(8500, 9500, 100),
        "low": np.random.uniform(7500, 8500, 100),
        "close": np.random.uniform(8000, 9000, 100),
        "volume": np.random.randint(1000000, 50000000, 100),
        ...
    })
```

---

## 8. Test Plan Lengkap

### 8.1 Core Engine Tests

| Engine | Test File | Test Cases | Fokus |
|--------|-----------|-----------|-------|
| Technical | `test_technical.py` | RSI, MACD, MA, ADX, BB, volume profile, trend classification | Skor 0-100, regime |
| Fundamental | `test_fundamental.py` | yfinance fetch, fallback chain, scoring | PER/PBV/ROE/DER/Growth |
| Sentiment | `test_sentiment.py` | NLP lexicon, negation, 6-source weighting, IDX historical | Indonesian text |
| Decision | `test_decision.py` | Weighted scoring, regime filter, BUY/HOLD/WATCHLIST/AVOID | Conviction threshold |
| Risk | `test_risk.py` | VaR, CVaR, position sizing, SL/TP, risk flags | ATR-based |
| Cost Model | `test_costs.py` | Broker fees, levy, PPh, slippage, feasibility | IDX conventions |
| Portfolio | `test_portfolio.py` | Equity, cash tracking, position management | Order generation |
| Rebalancer | `test_rebalancer.py` | Target weights, drift, rebalance, toggle | Runtime toggle |
| Performance | `test_performance_watchlist.py` | Sharpe, drawdown, win rate, equity curve, watchlist CRUD | Metrics |
| XAI | `test_xai.py` | Narrative, top factors, confidence interval, counter scenarios | Explanation |
| AI Learning | `test_ai_learning.py` | LR optimization, coefficient clipping, OOS, regime weights | np.maximum vs np.abs |
| Backtest | `test_backtest.py` | BuyAndHold, MA Crossover, Conviction, warmup, point-in-time | Anti look-ahead |
| Corporate | `test_corporate.py` | Splits, dividends, fetch & store | Adjustment factor |
| Monitoring | `test_monitoring.py` | Health check, source status | Alert detection |
| Paper Trading | `test_paper_trading.py` | State persistence, P&L tracking | Simulasi |

### 8.2 TIP Component Tests (Layer 1-6)

| Layer | Test File | Komponen | Test Cases |
|-------|-----------|----------|-----------|
| **L1** | `test_layer1_tip.py` | Data Quality Engine, Rate Limiter | Empty df, duplicates, zero/negative prices, high<low, missing bars, stale data, circuit breaker |
| **L2** | `test_layer2_tip.py` | Advanced Technical, Enhanced Regime, Factor Engine | Ichimoku, Williams %R, OBV, Stoch RSI, HMM, momentum/quality/beta/size/value |
| **L3** | `test_layer3_tip.py` | Alpha Composer, No-Trade Engine | Regime/sector multiplier, min score gate, 9 no-trade gates |
| **L4** | `test_layer4_tip.py` | Enhanced Risk, Alpha Validation | Vol-targeting, sector cap, drawdown/beta guard, VALID/WATCH/REJECT |
| **L5** | `test_layer5_tip.py` | Labeling, Deep Learning, Ensemble, Model Registry | Forward return, triple barrier, LSTM, voting/stacking, version |
| **L6** | `test_layer6_tip.py` | Purged TSS, Walk-Forward, Expectancy, Attribution, Corr Sizing, Cross-Asset, Lead-Lag, Manipulation, Factor Screener | Purging, embargo, OOS metrics, Kelly, factor/sector attribution |

### 8.3 Property-Based Tests

| Invariant | Framework | Test |
|-----------|-----------|------|
| Equity never negative | Hypothesis | `equity >= 0` for all timesteps |
| PnL consistent with trades | Hypothesis | `sum(realized_pnl) == final_equity - initial + fees` |
| Trade count ≥ 0 | Hypothesis | `len(trades) >= 0` |
| Win rate ∈ [0, 1] | Hypothesis | `0 <= win_rate <= 1` |
| Scores ∈ [0, 100] | Hypothesis | `0 <= score <= 100` for all engines |

### 8.4 E2E Tests (Playwright)

| File | Test Cases | Prasyarat |
|------|-----------|-----------|
| `test_dashboard.py` | Dashboard load, ticker switch, chart render, API integration | Backend + Frontend running |
| `comprehensive_test.py` | Full E2E: backtest, Monte Carlo, walk-forward, execution, risk | Backend + Frontend running |
| `capture_console_errors.py` | Console error capture during interaction | Backend + Frontend running |
| `record_demo.py` | Demo recording: dashboard, analyze, ticker switch | Backend + Frontend running |
| `run_all.py` | Simulation suite runner | Backend + Frontend running |

### 8.5 Running Tests

```bash
# All unit tests
.venv/bin/python -m pytest tests/unit/ -v

# With coverage
.venv/bin/python -m pytest tests/unit/ --cov=trading_system --cov-report=term-missing

# Specific layer
.venv/bin/python -m pytest tests/unit/test_layer1_tip.py -v

# Property-based
.venv/bin/python -m pytest tests/unit/test_property_based.py -v

# E2E (requires backend + frontend running)
.venv/bin/python -m pytest tests/e2e/test_dashboard.py -v

# Comprehensive E2E
.venv/bin/python tests/e2e/comprehensive_test.py

# With pattern
.venv/bin/python -m pytest tests/unit/ -k "test_delete" -v

# With warnings as errors
.venv/bin/python -m pytest tests/unit/ -W error
```

---

## 9. CI/CD Pipeline

### 9.1 GitHub Actions (`.github/workflows/ci.yml`)

```
Push to main
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step 1: Lint (ruff)                        │
│  ruff check src/trading_system/ tests/unit/ │
│  Rules: E, F, W, I, UP, B, SIM              │
│  Line length: 120                            │
│  Target: py311                               │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step 2: Type Check (mypy)                  │
│  mypy src/trading_system/                    │
│  python_version = "3.11"                     │
│  Non-blocking (warning only)                 │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step 3: Unit Tests (pytest)                │
│  pytest tests/unit/ --cov=trading_system    │
│  Coverage gate: 50% minimum                  │
│  750+ tests, 0 warnings                      │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step 4: Frontend Lint (ESLint)             │
│  cd frontend && npm run lint                 │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step 5: Frontend Build (Next.js)           │
│  cd frontend && npm run build                │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step 6: Docker Build                        │
│  docker build -t trading-system .            │
└─────────────────────────────────────────────┘
    │
    ▼
  All green → deploy ready
```

### 9.2 Git Workflow

```bash
# Branch naming
git checkout -b feat/<feature-name>     # new feature
git checkout -b fix/<bug-name>          # bug fix
git checkout -b docs/<doc-name>         # documentation
git checkout -b refactor/<refactor>     # refactoring
git checkout -b test/<test-name>        # testing
git checkout -b chore/<chore>           # maintenance

# Commit message format
type: short description

# Types: feat, fix, docs, refactor, test, chore, ci
# Example: feat: add Kelly Criterion position sizing
```

### 9.3 Code Quality Tools

| Tool | Konfigurasi | Fungsi |
|------|-------------|--------|
| **ruff** | `pyproject.toml` (line=120, py311, E/F/W/I/UP/B/SIM) | Linter + formatter |
| **mypy** | `pyproject.toml` (py311, non-blocking) | Type checking |
| **pytest** | `pyproject.toml` (fail_under=50) | Testing + coverage |
| **ESLint** | `frontend/eslint.config.mjs` | Frontend linting |
| **Playwright** | `tests/e2e/` | E2E browser testing |

---

## 10. KPI Sistem

### 10.1 KPI Infrastruktur

| KPI | Target | Saat Ini | Metrik |
|-----|--------|----------|--------|
| **Total tickers** | ≥ 900 | 951 (928 equity + 23 non-equity) | `SELECT COUNT(*) FROM instrument_master WHERE is_active=1` |
| **Total OHLCV rows** | ≥ 2M | 2,906,406 | `SELECT COUNT(*) FROM ohlcv` |
| **Total tabel** | ≥ 35 | 39 | Schema count |
| **API endpoints** | ≥ 80 | 88 (86 REST + 2 WS) | Route count |
| **Unit tests** | ≥ 500 | 752 | `pytest --collect-only` |
| **Test coverage** | ≥ 50% | ≥ 50% | `pytest --cov` |
| **Test warnings** | 0 | 0 | `pytest -W error` |
| **DB size** | < 500 MB | ~460 MB | File size |
| **Parquet files (raw)** | ≥ 900 | ~1222 | File count |
| **Parquet files (archive)** | ≥ 800 | ~1027 | File count |

### 10.2 KPI Performa Sistem

| KPI | Target | Measurement |
|-----|--------|-------------|
| **API response time (p50)** | < 100ms | Endpoint latency |
| **API response time (p95)** | < 500ms | Endpoint latency |
| **Score computation time** | < 5s per ticker | `compute-scores` CLI |
| **Backtest time** | < 30s for 2y data | `POST /api/backtest` |
| **Fetch time (1 ticker, 2y)** | < 10s | `fetch` CLI |
| **Database query (OHLCV, 1 ticker)** | < 50ms | `load_ohlcv()` |
| **Engine status check** | < 2s | `GET /api/engines` |
| **Frontend load time** | < 3s | Playwright E2E |

### 10.3 KPI Data Quality

| KPI | Target | Measurement |
|-----|--------|-------------|
| **Data completeness** | ≥ 95% | `(1 - missing_pct) * 100` |
| **Data quality score avg** | ≥ 85 | `AVG(data_quality_score)` |
| **Source uptime** | ≥ 99% | `source_health` status |
| **Data freshness** | ≤ 1 day | `data_watermark.last_data_date` |
| **Gap detection rate** | < 5% of tickers | Gap > 5 hari count |
| **Anomaly rate** | < 2% of records | Plausibility check failures |

---

## 11. KPI Engine

### 11.1 KPI per Analysis Engine

| Engine | KPI | Target | Measurement |
|--------|-----|--------|-------------|
| **Technical** | Score distribution | Mean 40-60, std < 25 | `AVG(score), STDDEV(score)` |
| **Fundamental** | Data coverage | ≥ 60% of tickers | Coverage ratio |
| **Macro** | Regime accuracy | Manual validation | Regime vs actual market |
| **Global** | Score vs IHSG correlation | Positive | Score vs IHSG return |
| **Relationship** | Avg influence score | 20-60 | `AVG(|correlation|) * 100` |
| **Sentiment** | Source availability | ≥ 4 of 6 sources active | Active source count |

### 11.2 KPI Decision Engine

| KPI | Target | Measurement |
|-----|--------|-------------|
| **BUY accuracy** | ≥ 60% profitable | Forward return after BUY signal |
| **AVOID accuracy** | ≥ 60% negative return | Forward return after AVOID signal |
| **Conviction calibration** | High conviction → high hit rate | Bin analysis |
| **Signal frequency** | 5-20% of tickers get BUY | `COUNT(BUY) / COUNT(*)` |
| **Regime filter effectiveness** | Filter reduces false signals | Compare filtered vs unfiltered |

### 11.3 KPI Risk Engine

| KPI | Target | Measurement |
|-----|--------|-------------|
| **Max drawdown** | < 15% | `min((equity - cummax) / cummax)` |
| **VaR accuracy** | Actual losses < VaR 95% | Backtesting VaR |
| **Position sizing accuracy** | Risk per trade ≤ 1% | Actual loss vs risk_amount |
| **SL/TP effectiveness** | SL hit < 40%, TP hit > 30% | Trade outcome ratio |
| **Circuit breaker trigger** | Rare (< 5x/year) | Halt count |

### 11.4 KPI Execution

| KPI | Target | Measurement |
|-----|--------|-------------|
| **Slippage accuracy** | Estimated vs actual < 2x | Paper vs live slippage |
| **Fee calculation accuracy** | 100% match with broker | Broker statement vs system |
| **Order fill rate** | ≥ 95% | `filled / total_orders` |
| **Execution latency** | < 1s (paper) | Order to fill time |

### 11.5 KPI AI Learning

| KPI | Target | Measurement |
|-----|--------|-------------|
| **R² out-of-sample** | > 0 | `TimeSeriesSplit` R² |
| **AI vs default weights** | AI ≥ default return | A/B comparison |
| **Training samples** | ≥ 60 per ticker | `n_samples` in training |
| **Model freshness** | < 7 days | `ai_weights.created_at` |
| **Coefficient stability** | Low variance across retraining | Coefficient delta |

---

## 12. KPI Bisnis

### 12.1 KPI Portofolio

| KPI | Target | Formula |
|-----|--------|---------|
| **Total Return** | > IHSG return | `equity[-1] / equity[0] - 1` |
| **CAGR** | > 10%/year | `(equity[-1] / equity[0])^(1/years) - 1` |
| **Sharpe Ratio** | > 1.0 | `excess.mean() / returns.std() * sqrt(252)` |
| **Sortino Ratio** | > 1.5 | `excess.mean() / downside.std() * sqrt(252)` |
| **Calmar Ratio** | > 1.0 | `CAGR / |max_drawdown|` |
| **Max Drawdown** | < -15% | `min((equity - cummax) / cummax)` |
| **Win Rate** | > 50% | `wins / total_trades` |
| **Profit Factor** | > 1.5 | `wins.sum() / |losses.sum()|` |
| **Expectancy** | > 0 | `trades.pnl.mean()` |
| **Beta vs IHSG** | 0.7-1.3 | `cov(returns, bench) / var(bench)` |
| **Alpha** | > 0 | `returns.mean() - rf - beta * (bench.mean() - rf)` |

### 12.2 KPI User Experience

| KPI | Target | Measurement |
|-----|--------|-------------|
| **Dashboard load time** | < 3s | Playwright |
| **Chart render time** | < 1s | Playwright |
| **Ticker switch time** | < 2s | Playwright |
| **API availability** | ≥ 99.5% | Uptime monitoring |
| **Error rate** | < 1% | `error_count / total_requests` |
| **WebSocket connection** | Stable | Connection duration |

### 12.3 KPI Compliance

| KPI | Target | Measurement |
|-----|--------|-------------|
| **Audit log completeness** | 100% of decisions | `audit_log` entries vs `recommendations` |
| **Audit log retention** | ≥ 1 year | Oldest entry date |
| **API key enforcement** | 100% in production | Sensitive endpoint check |
| **Data privacy** | No PII in logs | Log scan |
| **Regulatory compliance** | OJK/BEI rules | Manual audit |

---

## 13. SLA dan Threshold

### 13.1 SLA Operasional

| Komponen | SLA | Alert Threshold | Action |
|----------|-----|-----------------|--------|
| **API server** | 99.5% uptime | Down > 5 min | Restart, Telegram alert |
| **Data fetch** | Daily by 07:00 WIB | Delay > 30 min | Retry, alert |
| **Score computation** | Daily by 08:00 WIB | Delay > 1 hour | Retry, alert |
| **Database** | 99.9% available | Lock > 10s | WAL checkpoint, restart |
| **Frontend** | 99% available | Down > 10 min | Restart, alert |
| **WebSocket** | Stable connection | Disconnect > 5x/min | Reconnect logic |

### 13.2 Threshold Alerting

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| **Data quality score** | < 85 | < 70 | Flag → Reject |
| **Source health** | Last error > 1 hour | Status = "down" | Switch source, alert |
| **Drawdown** | > 10% | > 15% | Reduce position, alert |
| **Daily loss** | > 50% of limit | > 100% of limit | Halt trading |
| **API latency p95** | > 500ms | > 2000ms | Investigate, scale |
| **Error rate** | > 0.5% | > 2% | Investigate, rollback |
| **Test coverage** | < 55% | < 50% | Add tests |
| **DB size** | > 450 MB | > 500 MB | Archive old data |

### 13.3 Threshold Engine

| Engine | Warning | Critical | Action |
|--------|---------|----------|--------|
| **Technical score** | < 30 | < 20 | AVOID signal |
| **Fundamental data coverage** | < 0.6 | < 0.4 | Weight reduction |
| **Sentiment source availability** | < 4 sources | < 3 sources | Fallback to proxy |
| **Relationship correlation** | > 0.8 | > 0.9 | Diversification warning |
| **Volatility annualized** | > 40% | > 50% | HIGH_VOLATILITY flag |
| **Liquidity (order/ADV)** | > 0.5% | > 1% | LIQUIDITY_LOW flag |

---

## 14. Monitoring & Alerting

### 14.1 Monitoring Engine

| Komponen | Yang Dipantau | Frekuensi |
|----------|---------------|-----------|
| **Source Health** | Status semua sumber data | Setiap fetch |
| **Engine Status** | 18 engine di registry | On-demand (`GET /api/engines`) |
| **Data Freshness** | `data_watermark.last_data_date` | Harian |
| **Score Count** | Total skor di database | Harian |
| **Alert Queue** | Sumber dengan status ≠ "ok" | Real-time |
| **WebSocket** | Engine status live | Real-time (`/ws/live`) |

### 14.2 Alert Channels

| Channel | Trigger | Konfigurasi |
|---------|---------|-------------|
| **Telegram** | Order execution, SL/TP hit, daily loss limit | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| **Dashboard** | Engine status, data quality alert | Frontend `/engines` page |
| **Audit Log** | Semua event (append-only) | `audit_log` table |
| **API Response** | Error di endpoint | HTTP status code + error message |

### 14.3 Alert Priority

| Priority | Trigger | Response Time |
|----------|---------|---------------|
| **P0 — Critical** | API down, data corrupt, halt trading | < 5 menit |
| **P1 — High** | Source down, quality < 70, drawdown > 15% | < 30 menit |
| **P2 — Medium** | Quality < 85, latency > 500ms, coverage < 60% | < 2 jam |
| **P3 — Low** | Source lag, test coverage < 55% | < 1 hari |

---

## 15. Error Handling & Recovery

### 15.1 Error Handling Pattern

```python
# Pattern: fail-fast dengan audit log
try:
    result = engine.compute(ticker)
    if result["status"] != "ok":
        storage.audit("engine.warning", {"ticker": ticker, "status": result["status"]})
    return result
except Exception as e:
    storage.audit("engine.error", {"ticker": ticker, "error": str(e)})
    raise  # fail-fast, do not swallow
```

### 15.2 Recovery Strategy

| Skenario | Recovery | Implementasi |
|----------|----------|--------------|
| **Yahoo Finance down** | Retry 3x + exponential backoff | `RateLimiter` dengan circuit breaker |
| **IDX scraper blocked** | Switch to proxy OHLCV | `foreign_flow.py` fallback |
| **Database locked** | WAL mode + busy_timeout 5000ms | `PRAGMA busy_timeout = 5000` |
| **API key missing (production)** | Fail-fast, return 500 | `ENV=production` check |
| **Data gap detected** | Flag, continue with available data | Validation engine |
| **Score computation fails** | Log error, skip engine, continue | Pipeline pattern |
| **Order execution fails** | Log, close position manually | `execution.order.rejected` |
| **Daily loss limit hit** | Halt trading, persist state | `system_state` table |
| **WebSocket disconnect** | Auto-reconnect | Frontend logic |
| **Frontend build fails** | Block CI/CD | GitHub Actions |

### 15.3 Circuit Breaker Pattern

```python
# Rate limiter dengan circuit breaker
class RateLimiter:
    # States: CLOSED (normal) → OPEN (tripped) → HALF_OPEN (testing)

    def acquire(self):
        if self._circuit_open:
            raise RateLimitError("Circuit breaker open")
        # ... sliding window check ...
        if self._consecutive_failures >= 5:
            self._circuit_open = True
            # Auto-reset after cooldown (30s)
```

---

## 16. Security Rules

### 16.1 Authentication & Authorization

| # | Rule | Implementasi |
|---|------|--------------|
| S1 | API key via `X-API-Key` header | `secrets.compare_digest` (anti timing-attack) |
| S2 | API key wajib non-kosong di production | `ENV=production` → fail-fast |
| S3 | WebSocket auth via `?token=` query param | `/ws/live?token=<api_key>` |
| S4 | Sensitive endpoints always require API key | `/api/execution/toggle`, `/api/rebalance/toggle` |
| S5 | GET endpoints (read-only) exempt from API key | Health, tickers, data |
| S6 | Rate limiting per IP (60 req/min) | In-memory, cleanup 60s |

### 16.2 Data Security

| # | Rule | Implementasi |
|---|------|--------------|
| D1 | SQL injection prevention | Parameterized queries (`?` placeholder) |
| D2 | Column allowlist for dynamic UPDATE | `_POSITION_COLUMNS` set validation |
| D3 | Path traversal prevention | `safe_path()` dengan regex + resolve check |
| D4 | No PII in logs | Audit log hanya mencatat event_type + payload bisnis |
| D5 | No API key in response | Key hanya digunakan untuk comparison |
| D6 | CORS restricted | `CORS_ORIGINS` env var (default localhost:3000) |

### 16.3 Infrastructure Security

| # | Rule | Implementasi |
|---|------|--------------|
| I1 | Docker container non-root | Dockerfile `USER` directive |
| I2 | Environment variables for secrets | `.env` file, tidak hardcoded |
| I3 | API key rotation supported | Env var update + restart |
| I4 | Audit log append-only | `INSERT` only, no UPDATE/DELETE |
| I5 | Database backup | Parquet archive + SQLite backup |

---

## 17. Configuration Management

### 17.1 Single Source of Truth

Semua konfigurasi terpusat di `src/trading_system/config.py`:

```python
# Environment loading
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        # Parse key=value, skip comments, strip quotes
        ...

# Safe float helper
def _safe_float(env_key: str, default: str) -> float:
    raw = os.getenv(env_key, default)
    if raw is None or raw.strip() == "":
        raw = default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)
```

### 17.2 Configuration Categories

| Kategori | Parameter | Default | Override |
|----------|-----------|---------|----------|
| **Path** | `DB_PATH` | `data/trading_system.db` | — |
| **Path** | `DATA_RAW_DIR` | `data/raw/` | Env var |
| **Path** | `DATA_ARCHIVE_DIR` | `data/archive/` | Env var |
| **Trading** | `TRADING_CAPITAL` | 100,000,000 | Env var |
| **Trading** | `RISK_PER_TRADE` | 0.01 | Env var |
| **Trading** | `EXIT_CONVICTION_THRESHOLD` | 40 | Env var |
| **Trading** | `TRADING_MODE` | "paper" | Env var |
| **Trading** | `AUTO_TRADE_ENABLED` | false | Env var |
| **Trading** | `DAILY_LOSS_LIMIT` | 1,000,000 | Env var |
| **IDX** | `IDX_LOT_SIZE` | 100 | — |
| **IDX** | `DEFAULT_BROKER_FEE_BUY` | 0.0015 | — |
| **IDX** | `DEFAULT_BROKER_FEE_SELL` | 0.0025 | — |
| **IDX** | `DEFAULT_LEVY` | 0.0000043 | — |
| **IDX** | `DEFAULT_SLIPPAGE` | 0.0005 | — |
| **IDX** | `DEFAULT_BENCHMARK` | "^JKSE" | — |
| **API** | `API_KEY` | — | Env var |
| **API** | `CORS_ORIGINS` | localhost:3000 | Env var |
| **API** | `RATE_LIMIT_MAX` | 60 | Env var |
| **API** | `ENV` | development | Env var |
| **Rebalance** | `REBALANCE_ENABLED` | false | Env var |
| **Rebalance** | `REBALANCE_FREQUENCY` | monthly | Env var |
| **Rebalance** | `REBALANCE_TARGET_WEIGHTS` | JSON | Env var |
| **Notification** | `TELEGRAM_BOT_TOKEN` | — | Env var |
| **Notification** | `TELEGRAM_CHAT_ID` | — | Env var |
| **Sentiment** | `REDDIT_CLIENT_ID` | — | Env var |
| **Sentiment** | `TWITTER_BEARER_TOKEN` | — | Env var |
| **Rate Limit** | `YFINANCE_RATE_LIMIT_CALLS` | 1 | — |
| **Rate Limit** | `YFINANCE_RATE_LIMIT_WINDOW` | 1.0 | — |

### 17.3 Runtime Toggle

| Toggle | Endpoint | Effect |
|--------|----------|--------|
| **Auto-trade** | `POST /api/execution/toggle` | Enable/disable auto execution |
| **Rebalance** | `POST /api/rebalance/toggle` | Enable/disable rebalancing |

Kedua toggle mengupdate `os.environ` dan instance engine **tanpa restart server**.

---

## 18. Checklist QA

### 18.1 Pre-Release Checklist

- [ ] **Unit tests:** 750+ tests passing, 0 warnings
- [ ] **Coverage:** ≥ 50%
- [ ] **Lint:** `ruff check` clean
- [ ] **Type check:** `mypy` (non-blocking, no new errors)
- [ ] **Frontend lint:** `npm run lint` clean
- [ ] **Frontend build:** `npm run build` success
- [ ] **Docker build:** Image builds successfully
- [ ] **E2E tests:** Playwright passing
- [ ] **API key:** Set in production (`ENV=production`)
- [ ] **Auto-trade:** OFF by default (`AUTO_TRADE_ENABLED=false`)
- [ ] **Trading mode:** Paper by default (`TRADING_MODE=paper`)
- [ ] **Audit log:** All decisions logged
- [ ] **Database:** Migrations applied (`alembic upgrade head`)
- [ ] **Data:** Fresh data fetched (watermark < 1 day)
- [ ] **Documentation:** STATUS.md, CHANGELOG.md updated

### 18.2 Production Deployment Checklist

- [ ] `.env` configured with all required variables
- [ ] `ENV=production` set
- [ ] `API_KEY` set to strong random value
- [ ] `CORS_ORIGINS` restricted to production domain
- [ ] `AUTO_TRADE_ENABLED=false` (default, enable manually if ready)
- [ ] `TRADING_MODE=paper` (switch to `real` only when ready)
- [ ] `DAILY_LOSS_LIMIT` set appropriately
- [ ] `REBALANCE_ENABLED=false` (enable if needed)
- [ ] `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` configured
- [ ] Database backup taken
- [ ] Parquet archive synced
- [ ] Docker containers running
- [ ] Health check: `GET /api/health` returns ok
- [ ] Engine status: `GET /api/engines` all healthy
- [ ] Monitor: `GET /api/monitor` no alerts
- [ ] Frontend accessible
- [ ] WebSocket connection stable

### 18.3 Post-Release Monitoring

- [ ] **First 15 min:** Watch API logs for errors
- [ ] **First 1 hour:** Monitor engine status via `/api/engines`
- [ ] **First 1 day:** Check data freshness, score computation, audit log
- [ ] **First 1 week:** Review KPI dashboard, portfolio performance
- [ ] **Weekly:** Review test coverage, lint results, error rate
- [ ] **Monthly:** Review KPI targets, SLA compliance, alert history
- [ ] **Quarterly:** Full audit: security, compliance, performance, accuracy

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| Arsitektur lengkap | `docs/arsitektur-sistem-trading.md` |
| Buku panduan teknis | `docs/buku-sistem-trading.md` |
| Developer guide | `docs/DEVELOPER_GUIDE.md` |
| Test plan | `docs/TEST_PLAN.md` |
| Status implementasi | `docs/STATUS.md` |
| Saran pengembangan | `docs/SARAN_PENGEMBANGAN.md` |
| API reference | `docs/API_REFERENCE.md` |
| Modul & engine | `pustaka/18-modul-engine-data-wajib.md` |
| Knowledge transfer | `pustaka/11-knowledge-transfer-aplikasi.md` |
| Panduan membangun | `pustaka/12-panduan-membangun-aplikasi-pasar-modal.md` |
| Aplikasi retail | `pustaka/17-aplikasi-retail-pribadi.md` |

---

## Referensi

1. `docs/arsitektur-sistem-trading.md` — Arsitektur, alur data, event bus, data contracts
2. `docs/buku-sistem-trading.md` — Buku panduan teknis (3092 baris)
3. `docs/TEST_PLAN.md` — Test plan lengkap (750+ tests)
4. `docs/DEVELOPER_GUIDE.md` — Developer guide (997 baris)
5. `docs/STATUS.md` — Status implementasi dan perbaikan
6. `docs/SARAN_PENGEMBANGAN.md` — Saran pengembangan (1233 baris)
7. `src/trading_system/config.py` — Konfigurasi global
8. `src/trading_system/api/app.py` — API endpoints dan middleware
9. `src/trading_system/data/storage.py` — Database schema
10. `src/trading_system/decision/engine.py` — Decision logic
11. `src/trading_system/risk/engine.py` — Risk logic
12. `src/trading_system/backtest/engine.py` — Backtest logic
13. `src/trading_system/ai_learning/engine.py` — AI learning logic
14. `pyproject.toml` — Tooling config (ruff, mypy, pytest)
15. `.github/workflows/ci.yml` — CI/CD pipeline

---

## 16. Implementasi: No-Trade Engine dalam Flow Pipeline

> **Sumber:** `src/trading_system/analysis/no_trade.py` (259 baris)

No-Trade Engine berada **sebelum** Decision Engine dalam pipeline — sebagai gate yang menentukan apakah suatu saham layak diproses lebih lanjut.

| 5W1H | Detail |
|------|--------|
| **What** | No-Trade Engine flow: 7 gate berurutan sebelum decision engine |
| **Why** | Mencegah decision engine memproses saham yang tidak layak — hemat compute dan mencegah false signal |
| **When** | Setiap compute-scores run, sebelum decision engine |
| **Where** | Pipeline: analysis → no_trade.py → decision engine (gate sebelum conviction scoring) |
| **Who** | Dipanggil oleh pipeline.py, output dikonsumsi decision engine dan monitoring |
| **How** | 7 gate check: data quality, confidence, liquidity, event risk, model agreement, regime, IPO lockup |

### 16.1 Posisi dalam Flow

```
Data Acquisition → Validation → Technical/Fundamental/Macro/Global/Sentiment
  → No-Trade Engine (7 gates)
    → if NO_TRADE: skip, log reason
    → if PROCEED: continue to Decision Engine
      → Decision Engine (conviction scoring)
        → Risk Engine (position sizing, SL/TP)
          → Pre-Trade Checklist (9 checks)
            → Execution or Skip
```

### 16.2 Gate Flow Detail

| Gate | Input | Output |
|------|-------|--------|
| Data quality | `last_bar_date` vs today | PASS if < 7 days stale |
| Confidence | `composite_alpha` | PASS if ≥ 0.3 |
| Liquidity | `avg_volume_20d` | PASS if ≥ 100K |
| Event risk | `corporate_actions` within 5 days | PASS if no event |
| Model agreement | `model_agreement_ratio` | PASS if ≥ 0.6 |
| Regime | `macro_regime` | PASS if not crisis/unknown |
| IPO lockup | `listing_date`, `bars_since_listing` | PASS if ≥ 20 bars |

### 16.3 KPI: NO_TRADE Rate

| Metric | Target | Action if Off |
|--------|--------|---------------|
| NO_TRADE rate | 30-60% | < 30%: gates too loose; > 60%: gates too strict |
| Top reason | Track distribution | If "data quality" dominates → fix data pipeline |
| False positive rate | < 10% | Monitor via manual review |

---

> **Catatan:** Dokumen ini adalah referensi definitif untuk flow, logic, testing, aturan aplikasi, dan KPI. Untuk detail implementasi teknis, lihat source code di `src/trading_system/` dan dokumentasi di `docs/`. Untuk daftar modul dan engine, lihat `pustaka/18-modul-engine-data-wajib.md`. Untuk strategi mencegah gap antara hasil testing dan trading nyata, lihat `85-backtest-to-live-gap-prevention.md`. Implementasi No-Trade Engine: `src/trading_system/analysis/no_trade.py`.
