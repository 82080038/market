# Screening Saham, AI/ML, dan Pattern Memory

> **Tujuan:** Dokumen ini menganalisis tiga komponen kritis untuk aplikasi ritel pasar modal: (1) screening saham, (2) AI/ML untuk mempelajari pola saham dan faktor yang mempengaruhi, serta (3) sistem "mengingat" pola historis. Setiap komponen dianalisis dari tiga sudut: kebutuhan bisnis untuk investor ritel IDX, implementasi yang sudah ada di codebase `trading-system` v0.1.11, dan gap yang perlu diisi untuk aplikasi ritel production-ready.

---

## Daftar Isi

1. [Screening Saham](#1-screening-saham)
2. [AI/ML untuk Mempelajari Pola Saham](#2-aiml-untuk-mempelajari-pola-saham)
3. [Faktor yang Mempengaruhi Harga Saham](#3-faktor-yang-mempengaruhi-harga-saham)
4. [Pattern Memory — Mengingat Pola Historis](#4-pattern-memory--mengingat-pola-historis)
5. [Integrasi Ketiga Komponen](#5-integrasi-ketiga-komponen)
6. [Implementasi di Codebase Existing](#6-implementasi-di-codebase-existing)
7. [Gap untuk Aplikasi Ritel](#7-gap-untuk-aplikasi-ritel)
8. [Roadmap Implementasi](#8-roadmap-implementasi)
9. [Referensi Silang](#9-referensi-silang)

---

## 1. Screening Saham

### 1.1 Mengapa Screening Wajib

| Masalah Ritel | Solusi Screener |
|---------------|-----------------|
| **928 saham aktif di IDX** — tidak mungkin monitor semua | Filter ke 10-20 saham yang memenuhi kriteria |
| **Bias familiarity** — beli saham yang "dengar namanya" saja | Screener berbasis kriteria objektif, bukan nama |
| **Tidak tahu mulai dari mana** | Preset screener: "Value", "Momentum", "Dividen" |
| **Informasi overload** — terlalu banyak data per saham | Screener merangkum ke satu score/rank |
| **FOMO** — beli saham yang sudah naik tinggi | Screener bisa filter: "naik < 10% dalam 30 hari" |

### 1.2 Tipe Screener

#### Screener Teknikal

Filter berdasarkan indikator teknikal. Cocok untuk swing trader.

| Kriteria | Parameter | Contoh |
|----------|-----------|--------|
| Trend | Price > SMA 50 | Saham dalam uptrend |
| Momentum | RSI 30-70 | Tidak overbought/oversold |
| Trend strength | ADX > 20 | Trend kuat |
| Volume | Volume > 20-day avg | Ada minat institusi |
| Bollinger | Close > BB lower | Tidak breakdown |

**Implementasi:** `src/trading_system/analysis/screener.py` — fungsi `technical_template()`

#### Screener Fundamental

Filter berdasarkan metrik fundamental. Cocok untuk value investor.

| Kriteria | Parameter | Contoh |
|----------|-----------|--------|
| Valuasi | P/E < 15, P/B < 1.5 | Undervalued |
| Profitabilitas | ROE > 15% | Perusahaan efisien |
| Growth | EPS growth > 10% YoY | Tumbuh |
| Debt | DER < 1.0 | Tidak overleveraged |
| Dividen | Dividend yield > 3% | Income stock |

#### Screener Multi-Faktor

Filter berdasarkan composite score dari multiple factors. Ini keunggulan aplikasi ini vs kompetitor.

| Faktor | Weight | Metrik |
|--------|--------|--------|
| Value | 25% | P/E, P/B, EV/EBITDA percentile rank |
| Momentum | 25% | 1M/3M/6M return percentile rank |
| Quality | 25% | ROE, ROA, debt ratio percentile rank |
| Volatility | 25% | 20-day volatility (inverse) percentile rank |

**Implementasi:** `src/trading_system/analysis/factor_screener.py` — `FactorScreenerService.screen()`

#### Screener Sentimen

Filter berdasarkan sentimen pasar. Khusus untuk IDX.

| Kriteria | Parameter | Contoh |
|----------|-----------|--------|
| Foreign flow | Net buy > 3-day avg | Asing akumulasi |
| Broker flow | Top broker buy | Broker besar beli |
| News sentiment | NLP score > 0.5 | Berita positif |
| Social | Reddit/Trending up | Hype positif |
| Fear & Greed | Index < 30 (fear) | Kontrarian buy |

#### Screener Gorengan Detector

Filter khusus untuk menghindari saham gorengan.

| Red Flag | Threshold | Score |
|----------|-----------|-------|
| Price spike tanpa fundamental | +20% in 5 days + P/E > 50 | +30 |
| Volume surge di saham illiquid | Vol > 5x avg + avg vol < 500K | +25 |
| Market cap kecil | < Rp 200M | +20 |
| Free float rendah | < 20% | +15 |
| Tidak ada dividen 3 tahun | - | +10 |
| EPS negatif | - | +15 |
| Broker concentration | 1 broker > 30% | +15 |

> Score >= 60 = HIGH risk (gorengan), 30-59 = MEDIUM, < 30 = LOW

### 1.3 Screener UI untuk Ritel

```
┌─────────────────────────────────────────────────────┐
│  Screener Saham                                      │
│                                                      │
│  Preset: [Value] [Momentum] [Dividen] [Gorengan?]    │
│                                                      │
│  Filter Custom:                                      │
│  P/E max:     [ 15  ]                                │
│  ROE min:     [ 15% ]                                │
│  Volume min:  [ 1M  ]                                │
│  Foreign:     [ Net Buy ▼ ]                          │
│  Sektor:      [ All ▼ ]                              │
│                                                      │
│  [ SCREEN ]                                          │
├─────────────────────────────────────────────────────┤
│  Hasil (23 saham match):                             │
│                                                      │
│  #  Ticker   Score  P/E   ROE   Foreign  Sektor     │
│  1  BBCA.JK  85     12.3  24%   +45M     Bank        │
│  2  TLKM.JK  78     8.5   18%   +12M     Telco       │
│  3  UNVR.JK  75     14.2  22%   +8M      Consumer    │
│  ...                                                 │
│                                                      │
│  [ Save as Preset ]  [ Export CSV ]                  │
└─────────────────────────────────────────────────────┘
```

### 1.4 Status Implementasi

| Komponen | File | Status | Untuk Ritel |
|----------|------|--------|-------------|
| Technical screener | `analysis/screener.py` | ✅ Production | Perlu UI |
| Factor screener | `analysis/factor_screener.py` | ✅ Production | Perlu UI |
| Gorengan detector | `17-aplikasi-retail-pribani.md` (code snippet) | ⚠️ Pseudocode | Perlu implementasi |
| Sentiment screener | Belum ada | ❌ | Perlu buat |
| Screener API | `/api/screen` | ✅ Production | Perlu frontend |
| Factor API | `/api/factors` | ✅ Production | Perlu frontend |
| Save preset | Belum ada | ❌ | Perlu DB table + UI |

---

## 2. AI/ML untuk Mempelajari Pola Saham

### 2.1 Mengapa AI/ML Wajib

| Tanpa AI/ML | Dengan AI/ML |
|-------------|-------------|
| 928 saham, analyst hanya bisa cover 20-30 | Semua 928 saham di-scan otomatis |
| Pattern detection manual (mata + chart) | Otomatis, konsisten, 24/7 |
| Weight faktor statis (tidak adaptif) | Weight dinamis berdasarkan regime |
| Tidak tahu pola mana yang reliable | Win-rate historis per pola per saham |
| Tidak belajar dari kesalahan | Feedback loop: prediksi → evaluasi → adjust |
| Human bias dalam penilaian | Objektif, data-driven |

### 2.2 Arsitektur AI/ML di Codebase

```
┌──────────────────────────────────────────────────────────────┐
│                    AI LEARNING PIPELINE                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. LABELING (labeling.py)                                   │
│     OHLCV → forward_return / triple_barrier labels           │
│     "Apakah saham ini naik 5% dalam 20 hari ke depan?"       │
│                                                              │
│  2. FEATURE ENGINEERING (analysis/*.py)                      │
│     Technical, Fundamental, Macro, Global, Sentiment         │
│     → 50+ features per ticker per hari                       │
│                                                              │
│  3. MODEL TRAINING (deep_learning.py)                        │
│     LSTM (PyTorch CUDA) / MLP (sklearn)                      │
│     Input: 20-day lookback window                            │
│     Output: predicted return / direction                     │
│                                                              │
│  4. WALK-FORWARD VALIDATION (walk_forward.py)                │
│     Rolling window: train 1 year → test 3 months             │
│     Cegah overfitting + data leakage                         │
│                                                              │
│  5. PURGED TSS (purged_tss.py)                               │
│     Purged time-series split — hapus overlap                 │
│     antara train dan test untuk mencegah leakage             │
│                                                              │
│  6. MODEL REGISTRY (model_registry.py)                       │
│     Versioning: experiment → staging → production            │
│     Track metrics per version                                │
│                                                              │
│  7. ENSEMBLE (ensemble.py)                                   │
│     Combine multiple models → robust prediction              │
│                                                              │
│  8. WEIGHT OPTIMIZATION (engine.py)                          │
│     Adjust 6-factor weights berdasarkan:                     │
│     - Market regime (easing/tightening/growth/slowdown)      │
│     - Historical consistency per engine                      │
│     - Data coverage per engine                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Komponen AI/ML yang Sudah Ada

#### AILearningEngine (`ai_learning/engine.py`)

Mengoptimasi factor weights secara dinamis:

```python
# Regime-specific weights
REGIME_WEIGHTS = {
    "easing":     {"technical": 0.15, "fundamental": 0.30, "macro": 0.20, ...},
    "tightening": {"technical": 0.25, "fundamental": 0.15, "macro": 0.25, ...},
    "growth":     {"technical": 0.20, "fundamental": 0.25, "macro": 0.15, ...},
    "slowdown":   {"technical": 0.25, "fundamental": 0.20, "macro": 0.25, ...},
    "risk_off":   {"technical": 0.10, "fundamental": 0.20, "macro": 0.25, ...},
}
```

**Cara kerja:**
1. Cek AI-trained weights dari DB (jika fresh < 7 hari)
2. Jika tidak ada, gunakan regime-based weights
3. Adjust berdasarkan historical consistency (mean score + std dev)
4. Adjust berdasarkan data coverage (fundamental .JK sering limited)
5. Renormalize weights

#### DeepLearningModel (`ai_learning/deep_learning.py`)

LSTM untuk price prediction:

| Aspek | Detail |
|-------|--------|
| **Model** | LSTM (PyTorch) atau MLP (sklearn) |
| **Input** | 20-day lookback, 5 features (OHLCV) |
| **Output** | Predicted return |
| **GPU** | Auto-detect CUDA, prefer `cuda:1` (GPU 1 free) |
| **VRAM** | Max 4GB (GTX 1050 Ti) — batch_size <= 64, hidden <= 256 |
| **Backend priority** | PyTorch > TensorFlow > sklearn |
| **Config** | lookback=20, lstm_units=50, dropout=0.2, epochs=50 |

#### Labeling Engine (`ai_learning/labeling.py`)

| Label Type | Deskripsi | Use Case |
|------------|-----------|----------|
| `forward_return` | N-day forward return | Regresi: prediksi return |
| `triple_barrier` | +1 (profit take), -1 (stop loss), 0 (timeout) | Klasifikasi: arah |
| `alpha_adjusted` | Label disesuaikan regime | Risk-aware labeling |

#### Walk-Forward Validator (`ai_learning/walk_forward.py`)

| Parameter | Default | Tujuan |
|-----------|---------|--------|
| `train_size` | 252 (1 tahun) | Data training |
| `test_size` | 63 (3 bulan) | Data testing |
| `step_size` | 63 (3 bulan) | Overlap antar fold |
| `expanding` | False | Rolling vs expanding window |
| `use_gpu` | False | Parallel fold training (torch only) |

#### Model Registry (`ai_learning/model_registry.py`)

```
model_store/
  ├── lstm_bbca/
  │   ├── v1.0/model.pkl + metadata.json  (experiment)
  │   ├── v1.1/model.pkl + metadata.json  (staging)
  │   └── v2.0/model.pkl + metadata.json  (production)
  ├── lstm_tlkm/
  │   └── ...
  └── ensemble_all/
      └── ...
```

### 2.4 Pola Saham yang Bisa Dipelajari ML

| Tipe Pola | Detection Method | ML Approach |
|-----------|-----------------|-------------|
| **Chart pattern** (double bottom, H&S, triangle) | `analysis/technical.py` | CNN pada price image atau LSTM pada sequence |
| **Candlestick pattern** (doji, hammer, engulfing) | `analysis/technical.py` | Rule-based + ML confirmation |
| **Trend pattern** (higher high, lower low) | Moving average analysis | LSTM sequence classification |
| **Volume pattern** (accumulation, distribution) | Volume analysis | Anomaly detection |
| **Seasonality** (year-end rally, January effect) | Calendar analysis | Time-series decomposition |
| **Lead-lag** (saham A naik → saham B ikut) | `analysis/lead_lag.py` | Granger causality + ML |
| **Sector rotation** (dana pindah sektor) | `analysis/cross_asset.py` | Regime detection + clustering |
| **Foreign flow pattern** | `sentiment/foreign_flow.py` | Pattern matching + prediction |

### 2.5 Status Implementasi AI/ML

| Komponen | File | Status | Baris |
|----------|------|--------|-------|
| Weight optimization | `ai_learning/engine.py` | ✅ Production | 310 |
| Deep learning (LSTM) | `ai_learning/deep_learning.py` | ✅ Working | 318 |
| Labeling | `ai_learning/labeling.py` | ✅ Working | 173 |
| Walk-forward | `ai_learning/walk_forward.py` | ✅ Working | 168 |
| Purged TSS | `ai_learning/purged_tss.py` | ✅ Working | ~80 |
| Model registry | `ai_learning/model_registry.py` | ✅ Working | 188 |
| Ensemble | `ai_learning/ensemble.py` | ✅ Working | ~100 |
| GPU acceleration | PyTorch CUDA (cuda:1) | ✅ Working | - |

---

## 3. Faktor yang Mempengaruhi Harga Saham

### 3.1 Enam Faktor Multi-Faktor Engine

Codebase sudah menggabungkan **6 faktor** dalam Decision Engine (`decision/engine.py`):

```
                    ┌─────────────────┐
                    │  DECISION ENGINE │
                    │  Weighted Score  │
                    └────────┬────────┘
                             │
        ┌────────┬───────────┼───────────┬────────┬────────┐
        │        │           │           │        │        │
   Technical  Fundamental  Macro    Global  Relation  Sentiment
      20%       25%        15%      15%      10%       15%
```

### 3.2 Detail Per Faktor

#### Technical (20%) — `analysis/technical.py`

| Sub-faktor | Indikator | Impact |
|------------|-----------|--------|
| Trend | SMA 20/50/200, MACD | Uptrend/downtrend/sideways |
| Momentum | RSI, Stochastic, Williams %R | Overbought/oversold |
| Volatility | Bollinger Bands, ATR | Risk level |
| Volume | Volume ratio, OBV | Konfirmasi trend |
| Pattern | Double bottom, H&S, triangle | Reversal/continuation signal |

#### Fundamental (25%) — `analysis/fundamental.py`

| Sub-faktor | Metrik | Impact |
|------------|--------|--------|
| Valuasi | P/E, P/B, EV/EBITDA | Undervalued/overvalued |
| Profitabilitas | ROE, ROA, net margin | Efisiensi perusahaan |
| Growth | EPS growth, revenue growth | Pertumbuhan |
| Solvabilitas | DER, current ratio | Risiko keuangan |
| Dividen | Yield, payout ratio | Income vs growth |

#### Macro (15%) — `analysis/macro.py`

| Sub-faktor | Indikator | Impact |
|------------|-----------|--------|
| Interest rate | BI 7-day repo rate | Diskon cash flow |
| Inflation | CPI, core inflation | Purchasing power |
| GDP | GDP growth, quarterly | Economic health |
| Currency | USD/IDR, EUR/IDR | Import/export impact |
| IHSG | Composite index trend | Market direction |

#### Global (15%) — `analysis/global_market.py`

| Sub-faktor | Indikator | Impact |
|------------|-----------|--------|
| US market | S&P 500, NASDAQ, Dow Jones | Sentimen global |
| Volatility | VIX | Risk appetite |
| Commodity | Crude oil, gold, copper | Commodity-linked stocks |
| Regional | Hang Seng, Nikkei, STI | Regional sentiment |
| Forex | DXY (dollar index) | Capital flow direction |

#### Relationship (10%) — `analysis/relationship.py`

| Sub-faktor | Metrik | Impact |
|------------|--------|--------|
| Correlation | Pearson/Spearman antar saham | Diversifikasi |
| Lead-lag | Granger causality | Saham pemimpin vs pengikut |
| Sector beta | Beta vs sektor | Relative strength |
| Spillover | Diebold-Yilmaz variance decomposition | Contagion effect |

#### Sentiment (15%) — `sentiment/`

| Sub-faktor | Sumber | Impact |
|------------|--------|--------|
| Foreign flow | IDX scraper (foreign buy/sell) | Asing akumulasi/distribusi |
| Broker flow | IDX scraper (broker summary) | Broker besar aktif |
| News sentiment | RSS + NLP (IndoBERT) | Berita positif/negatif |
| Social | Reddit, X (Twitter) | Retail sentiment |
| Trends | Google Trends | Search interest |
| Fear & Greed | Composite index | Market emotion |

### 3.3 Dynamic Weight Adjustment

AI Learning Engine menyesuaikan weight berdasarkan:

| Trigger | Adjustment | Contoh |
|---------|-----------|--------|
| **Regime easing** (BI rate turun) | Fundamental ↑, Technical ↓ | "Cari saham value, bukan momentum" |
| **Regime tightening** (BI rate naik) | Macro ↑, Technical ↑ | "Pentingkan macro & technical" |
| **Regime growth** (GDP > 5%) | Fundamental ↑, Sentiment ↑ | "Growth stock, sentiment positif" |
| **Regime slowdown** (GDP < 4%) | Macro ↑, Sentiment ↓ | "Defensive, macro penting" |
| **Engine consistency tinggi** | Weight ↑ | "Technical selalu akurat untuk BBCA" |
| **Engine consistency rendah** | Weight ↓ | "Sentiment tidak konsisten untuk TLKM" |
| **Data coverage < 60%** | Weight ↓ 30% | "Fundamental data .JK terbatas" |
| **Data coverage < 40%** | Weight ↓ 50% | "Hampir tidak ada fundamental data" |
| **Weight multiplier = 0** | Weight = 0 | "Fundamental data unavailable" |

### 3.4 Faktor Khusus IDX

Faktor yang **hanya relevan untuk pasar Indonesia** dan tidak ada di market lain:

| Faktor | Deskripsi | Dampak |
|--------|-----------|--------|
| **Foreign flow** | Dominasi asing (~30% value traded) | Foreign net sell → bearish signal |
| **Auto-reject** | Circuit breaker BEI (±15% daily, ±20% cumulative) | Halt trading, impact psikologis |
| **Gorengan** | Saham dimanipulasi bandar | High risk, harus di-deteksi |
| **Lot size** | 100 lembar per lot | Position sizing berbeda dari US (1 share) |
| **Tick size** | Fraksi harga (Rp 1-500) | Impact biaya transaksi |
| **T+2 settlement** | 2 hari kerja | Cash flow management |
| **Sesi perdagangan** | 2 sesi dengan break (09:00-11:30, 13:30-15:50) | Liquidity gap antar sesi |
| **Jumat pendek** | Sesi 2 lebih singkat | Volume lebih rendah |
| **Koneksi broker** | Broker API terbatas (Sinarmas, BNI) | Eksekusi tergantung broker |
| **IDX data delay** | Yahoo Finance 10 min delay | Tidak real-time untuk free tier |

---

## 4. Pattern Memory — Mengingat Pola Historis

### 4.1 Mengapa "Mengingat" Wajib

| Tanpa Pattern Memory | Dengan Pattern Memory |
|---------------------|----------------------|
| Setiap pola diperlakukan sama | Win-rate per pola per saham |
| Tidak tahu pola reliable atau tidak | "BBCA double bottom: 72% win-rate" |
| Tidak belajar dari kesalahan | "Pola gagal 3x → turunkan confidence" |
| Tidak ada konteks | "Pola saat foreign buy lebih reliable" |
| Manual tracking | Otomatis, tersimpan di DB |

### 4.2 Pattern Reliability Engine

**Implementasi:** `src/trading_system/analysis/pattern_reliability.py`

```python
class PatternReliabilityEngine:
    """Score patterns by historical reliability data."""
    
    def get_reliable_patterns(
        self, kode: str | None = None, 
        min_win_rate: float = 60.0, 
        min_rating: str = "average"
    ) -> pd.DataFrame:
        """Get patterns that meet reliability criteria."""
        
    def score_pattern(self, kode: str, pattern_name: str) -> dict:
        """Get reliability score for a specific pattern on a stock.
        
        Returns: win_rate, total_occurrences, success_count, fail_count,
                 avg_return, reliability_rating
        """
```

### 4.3 Database Storage

| Tabel | Rows | Konten |
|-------|------|--------|
| `pattern_analysis` | 2,386 | Pola terdeteksi per saham per tanggal + hasil |
| `pattern_reliability` | (extended storage) | Win-rate agregat per pola per saham |

### 4.4 Cara Kerja Pattern Memory

```
STEP 1: DETECT
  analysis/technical.py → "BBCA: Double Bottom detected on 2026-08-04"

STEP 2: LOOKUP
  pattern_reliability.py → "BBCA Double Bottom: 
    win_rate: 72%
    total_occurrences: 15
    success_count: 11
    fail_count: 4
    avg_return: +8.5%
    reliability_rating: good"

STEP 3: SCORE
  decision/engine.py → technical score naik karena:
    - Pattern detected: +20 points
    - High win-rate (72%): +15 points
    - Good reliability rating: +5 points

STEP 4: STORE
  pattern_analysis table → insert record:
    ticker: BBCA.JK
    pattern: double_bottom
    detected_date: 2026-08-04
    entry_price: 7850
    status: PENDING

STEP 5: EVALUATE (N days later)
  → Check: did price hit profit target or stop loss?
  → Update pattern_analysis: status = SUCCESS/FAIL
  → Update pattern_reliability: recalculate win_rate

STEP 6: FEEDBACK LOOP
  ai_learning/engine.py → adjust weight:
    "Technical engine konsisten akurat untuk BBCA" → weight ↑
    "Pattern reliability tinggi" → confidence ↑
```

### 4.5 Pattern Memory Hierarchy

| Level | Yang Diingat | Storage |
|-------|-------------|---------|
| **Per saham** | Win-rate double bottom untuk BBCA | `pattern_reliability` |
| **Per sektor** | Win-rate double bottom untuk sektor Bank | Agregat dari per-saham |
| **Per regime** | Win-rate double bottom saat regime easing | `ai_weights` table |
| **Per engine** | Technical engine consistency untuk BBCA | `scores` table history |
| **System-wide** | Faktor mana yang paling predictive saat ini | `ai_weights` table |

### 4.6 Context-Aware Pattern Memory

Pola tidak dievaluasi dalam isolasi — **konteks mempengaruhi reliabilitas**:

| Konteks | Impact pada Pattern | Implementasi |
|---------|---------------------|--------------|
| **Foreign net buy** | Pattern lebih reliable | Cek foreign_flow saat pattern detected |
| **Market regime** | Pattern bull ≠ pattern bear | Tag pattern dengan regime saat detection |
| **Volume** | Pattern + volume tinggi = reliable | Volume ratio saat detection |
| **Sector trend** | Pattern sektornya naik = konfirmasi | Sektor index saat detection |
| **Global market** | Pattern saat US naik vs turun | Global score saat detection |
| **Time of year** | Year-end rally, January effect | Calendar tag |

### 4.7 Status Implementasi Pattern Memory

| Komponen | File | Status | Catatan |
|----------|------|--------|---------|
| Pattern detection | `analysis/technical.py` | ✅ Production | Multiple pattern types |
| Pattern reliability | `analysis/pattern_reliability.py` | ✅ Production | Win-rate per saham per pola |
| Pattern storage | `pattern_analysis` table (2,386 rows) | ✅ Production | Historical record |
| Extended storage | `data/extended_storage.py` | ✅ Production | Pattern reliability data |
| Feedback loop | `ai_learning/engine.py` | ✅ Production | Weight adjustment dari consistency |
| Context tagging | ⚠️ Partial | Perlu extend | Regime + foreign flow tag |
| Evaluation scheduler | ❌ | Perlu buat | Auto-evaluate pattern N days after detection |

---

## 5. Integrasi Ketiga Komponen

### 5.1 Flow Integrasi

```
┌──────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION                           │
│                                                                   │
│  "Screener, cari saham value dengan foreign net buy"             │
│       │                                                           │
│       ▼                                                           │
│  ┌─────────────┐                                                  │
│  │  SCREENER    │  Filter 928 → 23 saham                          │
│  │  (multi-faktor)│                                               │
│  └──────┬──────┘                                                  │
│         │                                                         │
│         ▼  23 saham candidates                                    │
│  ┌─────────────┐                                                  │
│  │  AI/ML       │  Score setiap saham dengan 6 faktor             │
│  │  ENGINE      │  Weight dinamis berdasarkan regime              │
│  │              │  LSTM prediction untuk top candidates           │
│  └──────┬──────┘                                                  │
│         │                                                         │
│         ▼  Top 5 saham dengan score > 60                          │
│  ┌─────────────┐                                                  │
│  │  PATTERN     │  Cek pola chart yang sedang terbentuk           │
│  │  MEMORY      │  Lookup win-rate historis per pola per saham    │
│  │              │  Filter: hanya pola dengan win-rate > 60%       │
│  └──────┬──────┘                                                  │
│         │                                                         │
│         ▼  3 saham dengan pattern reliable                        │
│  ┌─────────────┐                                                  │
│  │  DECISION    │  Combine: screener score + AI score +           │
│  │  ENGINE      │  pattern reliability → final conviction         │
│  └──────┬──────┘                                                  │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐                                                  │
│  │  XAI         │  "BBCA: BUY (conviction 72)                     │
│  │  NARRATIVE   │   - Fundamental: ROE 24%, P/E 12 (undervalued) │
│  │              │   - Foreign: Net buy +Rp 45M (3 hari)          │
│  │              │   - Pattern: Double Bottom (72% win-rate)       │
│  │              │   - AI: LSTM prediksi +5.2% dalam 20 hari       │
│  │              │   - Regime: Growth → fundamental weight tinggi" │
│  └──────┬──────┘                                                  │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐                                                  │
│  │  RISK CHECK  │  Position sizing, stop-loss, diversification    │
│  └──────┬──────┘                                                  │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐                                                  │
│  │  EXECUTION   │  Order ke broker (atau paper trading)           │
│  └──────┬──────┘                                                  │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────┐                                                  │
│  │  STORE &     │  Record: prediction, entry, pattern detected    │
│  │  EVALUATE    │  Evaluate N days later: SUCCESS/FAIL            │
│  │              │  Update pattern_reliability win-rate             │
│  │              │  Feedback to AI Learning Engine                  │
│  └─────────────┘                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Feedback Loop Detail

```
                    ┌──────────────────┐
                    │   PREDICTION      │
                    │   "BBCA: BUY"     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   EXECUTION       │
                    │   Buy 10 lot @7850│
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   MONITORING      │
                    │   Track price,    │
                    │   SL, TP          │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   EVALUATION      │
                    │   20 days later:  │
                    │   Price = 8,250   │
                    │   Result: +5.1%   │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼──────┐ ┌─────▼───────┐
     │ PATTERN       │ │ AI/ML     │ │ DECISION    │
     │ MEMORY        │ │ ENGINE    │ │ ENGINE      │
     │               │ │           │ │             │
     │ Update:       │ │ Update:   │ │ Update:     │
     │ double_bottom │ │ LSTM      │ │ Technical   │
     │ BBCA:         │ │ accuracy  │ │ weight for  │
     │ win_rate 72%  │ │ score     │ │ BBCA ↑      │
     │ → 73% (11→12  │ │ adjusted  │ │             │
     │   success)    │ │           │ │             │
     └───────────────┘ └───────────┘ └─────────────┘
```

---

## 6. Implementasi di Codebase Existing

### 6.1 Yang Sudah Production-Ready

| Modul | File | Baris | Fungsi |
|-------|------|-------|--------|
| **Technical Screener** | `analysis/screener.py` | 161 | 3 template: technical, momentum, value |
| **Factor Screener** | `analysis/factor_screener.py` | 126 | Multi-faktor composite ranking |
| **Factor Engine** | `analysis/factor_engine.py` | - | Value, momentum, quality, volatility |
| **Pattern Detection** | `analysis/technical.py` | - | Chart & candlestick pattern detection |
| **Pattern Reliability** | `analysis/pattern_reliability.py` | 119 | Win-rate per pola per saham |
| **AI Learning Engine** | `ai_learning/engine.py` | 310 | Dynamic weight optimization |
| **Deep Learning** | `ai_learning/deep_learning.py` | 318 | LSTM price prediction (PyTorch CUDA) |
| **Labeling** | `ai_learning/labeling.py` | 173 | Triple-barrier + forward return |
| **Walk-Forward** | `ai_learning/walk_forward.py` | 168 | Rolling/expanding validation |
| **Purged TSS** | `ai_learning/purged_tss.py` | ~80 | Anti-leakage time-series split |
| **Model Registry** | `ai_learning/model_registry.py` | 188 | Versioning: experiment→staging→prod |
| **Ensemble** | `ai_learning/ensemble.py` | ~100 | Combine multiple models |
| **Decision Engine** | `decision/engine.py` | - | 6-factor weighted scoring |
| **XAI Engine** | `xai/engine.py` | - | Narrative explanation |
| **Screener API** | `/api/screen` | - | REST endpoint |
| **Factor API** | `/api/factors` | - | REST endpoint |
| **Pattern DB** | `pattern_analysis` table | 2,386 rows | Historical pattern record |

### 6.2 Yang Perlu Dibuat untuk Aplikasi Ritel

| Komponen | Prioritas | Estimasi Effort |
|----------|-----------|-----------------|
| **Screener UI** (frontend) | Tinggi | 2-3 minggu |
| **Gorengan detector** (production code) | Tinggi | 1 minggu |
| **Sentiment screener** | Sedang | 1-2 minggu |
| **Pattern alert notification** | Tinggi | 1 minggu |
| **Pattern evaluation scheduler** | Tinggi | 1 minggu |
| **Context tagging** (regime + foreign flow) | Sedang | 1-2 minggu |
| **Save screener preset** (DB + UI) | Sedang | 3 hari |
| **AI prediction UI** | Sedang | 1 minggu |
| **Factor influence radar chart** | Rendah | 3 hari |
| **Learning feedback display** | Rendah | 3 hari |

---

## 7. Gap untuk Aplikasi Ritel

### 7.1 User-Facing Features yang Belum Ada

| Fitur | Engine Status | UI Status | Gap |
|-------|--------------|-----------|-----|
| Screener dengan filter visual | ✅ Backend | ❌ | Frontend panel + result table |
| Save screener preset | ❌ | ❌ | DB table `screener_presets` + API + UI |
| Pattern alert (push notification) | ✅ Detection | ❌ | Notification trigger + template |
| AI prediction display | ✅ LSTM | ❌ | Frontend card: "AI prediksi +5% dalam 20 hari" |
| Factor radar chart | ✅ 6 faktor | ❌ | Frontend visualization |
| Pattern reliability display | ✅ Backend | ❌ | Frontend: "Win-rate 72% (15 occurrences)" |
| Learning feedback | ✅ Backend | ❌ | Frontend: "Model belajar: weight naik" |
| Backtest for user | ✅ Backend | ❌ | Frontend: pilih strategi + saham + lihat hasil |
| Gorengan warning | ⚠️ Pseudocode | ❌ | Production code + UI warning |

### 7.2 Engine Enhancements yang Perlu

| Enhancement | Tujuan | Estimasi |
|-------------|--------|----------|
| **Pattern evaluation scheduler** | Auto-evaluate pattern N days after detection | 1 minggu |
| **Context-aware pattern tagging** | Tag pattern dengan regime + foreign flow | 1-2 minggu |
| **Pattern confidence score** | Combine win-rate + context → confidence | 3 hari |
| **Sector pattern reliability** | Win-rate per pola per sektor (bukan per saham) | 3 hari |
| **Real-time pattern detection** | Detect pattern intraday (bukan EOD only) | 2-3 minggu |
| **LSTM per ticker** | Train model per saham (bukan generic) | 1-2 minggu |
| **Ensemble LSTM + factor** | Combine LSTM prediction dengan factor score | 1 minggu |
| **Feature importance display** | Tampilkan faktor mana paling predictive | 3 hari |

---

## 8. Roadmap Implementasi

### Phase 1: Screener MVP (Bulan 1-2)

- [ ] Frontend screener panel (filter + result table)
- [ ] 3 preset: Value, Momentum, Dividen
- [ ] Gorengan detector (production code)
- [ ] Screener API integration
- [ ] Save preset (DB + API)

### Phase 2: Pattern Memory (Bulan 3-4)

- [ ] Pattern alert notification (push + in-app)
- [ ] Pattern reliability display di saham detail
- [ ] Pattern evaluation scheduler (auto-evaluate N days)
- [ ] Context tagging (regime + foreign flow)
- [ ] Pattern confidence score

### Phase 3: AI/ML User-Facing (Bulan 5-6)

- [ ] AI prediction card ("LSTM prediksi +X% dalam 20 hari")
- [ ] Factor radar chart (6 faktor visualization)
- [ ] XAI narrative (Bahasa Indonesia, plain language)
- [ ] Learning feedback display
- [ ] Feature importance display

### Phase 4: Advanced AI (Bulan 7-9)

- [ ] LSTM per ticker (personalized model)
- [ ] Ensemble LSTM + factor score
- [ ] Real-time pattern detection (intraday)
- [ ] Sector pattern reliability
- [ ] Backtest for user (pilih strategi + saham)

### Phase 5: Scale (Bulan 10-12)

- [ ] Sentiment screener (foreign flow + broker + NLP)
- [ ] Multi-model ensemble (LSTM + XGBoost + factor)
- [ ] Auto-retrain scheduler (monthly)
- [ ] Model A/B testing (production vs experiment)
- [ ] GPU scaling (multi-GPU training)

---

## 9. Referensi Silang

| Topik | Dokumen | Bagian |
|-------|---------|--------|
| Fitur aplikasi retail | `17-aplikasi-retail-pribadi.md` | 5 (Analisis), 6 (Screener), 7 (Rekomendasi) |
| Modul & engine wajib | `18-modul-engine-data-wajib.md` | 3 (Analysis), 4 (Intelligence), 9 (Decision) |
| Analisis teknikal | `05-analisis-teknikal.md` | Pattern detection, indikator |
| Analisis fundamental | `06-analisis-fundamental.md` | Metrik valuasi, profitabilitas |
| Trading algoritmik | `08-trading-algoritmik.md` | ML, backtest, walk-forward |
| Behavioral finance | `09-behavioral-finance.md` | Bias retail, nudge |
| Knowledge transfer | `11-knowledge-transfer-aplikasi.md` | AI learning, pattern reliability |
| Sentiment analysis | `30-sentiment-analysis-alternative-data.md` | NLP, foreign flow, Fear & Greed |
| Risk management | `31-risk-management-lanjutan.md` | Position sizing, VaR |
| Multi-asset analysis | `35-multi-asset-cross-market-analysis.md` | Lead-lag, spillover, correlation |
| Bahasa pemrograman | `37-bahasa-pemrograman-tech-stack.md` | Python untuk ML/AI |
| Manajemen aplikasi | `38-manajemen-aplikasi-ritel.md` | Data management, analytics |

### Codebase Referensi

| File | Fungsi |
|------|--------|
| `src/trading_system/analysis/screener.py` | Technical screener (3 template) |
| `src/trading_system/analysis/factor_screener.py` | Multi-factor screener service |
| `src/trading_system/analysis/factor_engine.py` | Factor computation (value, momentum, quality, vol) |
| `src/trading_system/analysis/pattern_reliability.py` | Pattern win-rate engine |
| `src/trading_system/analysis/technical.py` | Pattern detection (chart + candlestick) |
| `src/trading_system/ai_learning/engine.py` | Dynamic weight optimization |
| `src/trading_system/ai_learning/deep_learning.py` | LSTM price prediction (PyTorch CUDA) |
| `src/trading_system/ai_learning/labeling.py` | Triple-barrier + forward return labeling |
| `src/trading_system/ai_learning/walk_forward.py` | Walk-forward validation |
| `src/trading_system/ai_learning/purged_tss.py` | Purged time-series split |
| `src/trading_system/ai_learning/model_registry.py` | Model versioning |
| `src/trading_system/ai_learning/ensemble.py` | Multi-model ensemble |
| `src/trading_system/decision/engine.py` | 6-factor weighted decision |
| `src/trading_system/xai/engine.py` | Explainable AI narrative |

---

## Referensi Eksternal

1. Lopez de Prado, M. (2018) — *Advances in Financial Machine Learning* — Triple-barrier labeling, purged TSS
2. De Prado, M. (2019) — *Trend Following on Momentum* — Walk-forward analysis
3. Kolm & Ritter (2019) — *Modern Neural Networks for Stock Prediction* — LSTM for finance
4. Fischer & Krauss (2018) — *Deep Learning with Long Short-Term Memory Networks for Financial Market Predictions*
5. Takeuchi & Li (2014) — *Applying Deep Learning to Genre Classification of Stock Prices*
6. Gu, Kelly & Xiu (2020) — *Empirical Asset Pricing via Machine Learning* — Factor models + ML
7. Han, He & Wu (2023) — *Chart Pattern Detection with Deep Learning*
8. IDX Regulation — Auto-reject, trading halt, circuit breaker

---

## 15. Implementasi: Factor Engine (Cross-Sectional Ranking)

> **Sumber:** `src/trading_system/analysis/factor_engine.py` (316 baris), `src/trading_system/analysis/factor_screener.py` (126 baris)

Sistem `trading-system` mengimplementasikan 6 faktor dengan cross-sectional percentile ranking, liquidity filter, dan factor versioning.

| 5W1H | Detail |
|------|--------|
| **What** | Factor Engine: 6 faktor (momentum, low vol, quality, beta, size, value) dengan cross-sectional ranking |
| **Why** | Screening berbasis single metric (PE, ROE) tidak cukup — multi-factor ranking memberikan view holistik |
| **When** | Screening harian, compute-scores, dan API `/api/factors` |
| **Where** | Analysis layer: factor_engine.py → factor_screener.py → API + CLI |
| **Who** | Dipanggil oleh factor_screener.py, API endpoint, dan CLI `screen` |
| **How** | Compute raw factor values per ticker → percentile rank (0-1) → composite rank → top N screening |

### 15.1 Faktor

| Faktor | Formula | Min History |
|--------|---------|-------------|
| **Momentum** | Mean(1M, 3M, 6M, 12M returns) | 22 hari |
| **Low volatility** | -std(60-day returns) | 60 hari |
| **Quality** | mean(60d returns) / std(60d returns) | 60 hari |
| **Beta** | cov(r, benchmark) / var(benchmark) | 60 hari |
| **Size** | Market cap (proxy: price × volume) | 20 hari |
| **Value** | PE, PB ratio (dari fundamental_data) | Fundamental |

### 15.2 Pipeline

```
Universe (928 equity tickers)
  → Liquidity filter (volume > 100K, min 60 bars)
  → Compute raw factor values per ticker
  → Cross-sectional percentile rank (0-1)
  → Composite rank (weighted average)
  → Top N screening
```

### 15.3 Factor Versioning

```python
FACTOR_VERSION = "1.0"
MIN_HISTORY_DAYS = 60
LIQUIDITY_MIN_VOLUME = 100_000
```

Setiap perubahan formula → versi naik → backtest ulang dengan versi baru.

### 15.4 FactorScreenerService

```python
class FactorScreenerService:
    def screen(self, top_n=20, min_composite=0.0,
               factor_filter=None, min_factor_rank=0.0) -> dict:
        """Returns: as_of, factor_version, universe_size, results"""

    def explain(self, symbol) -> dict:
        """Returns: composite_rank, factor breakdown with tier (top/above/average/below/bottom quintile)"""
```

---

## 16. Implementasi: Alpha Composer

> **Sumber:** `src/trading_system/analysis/alpha_composer.py` (173 baris)

**What:** Menggabungkan factor scores dengan regime/sector/macro multipliers menjadi composite alpha signal.
**Why:** Factor scores mentah perlu diadjust berdasarkan kondisi pasar — momentum bagus di bull market tapi berbahaya di crisis.
**When:** Setelah factor engine compute, sebelum decision engine.
**Where:** Pipeline: Factor Engine → Alpha Composer → Decision Engine.
**Who:** Dipanggil oleh analysis pipeline, konsumsi oleh decision engine.

### 16.1 Regime Multipliers

| Regime | Multiplier | Arti |
|--------|------------|------|
| bull | 1.0 | Full alpha exposure |
| risk_on | 1.0 | Full alpha exposure |
| neutral | 0.7 | Reduce alpha |
| sideways | 0.5 | Significant reduce |
| bear | 0.2 | Minimal exposure |
| risk_off | 0.2 | Minimal exposure |
| crisis | 0.0 | Zero alpha |
| unknown | 0.0 | Zero alpha (safety) |

### 16.2 Factor Weights (default)

| Faktor | Weight |
|--------|--------|
| Momentum | 25% |
| Low volatility | 20% |
| Quality | 20% |
| Value | 15% |
| Size | 10% |
| Beta | 10% |

### 16.3 Output

Composite alpha per instrument dengan component breakdown dan reason codes. Versioned (`ALPHA_VERSION = "1.0"`).

---

## 17. Implementasi: Alpha Validation Lab

> **Sumber:** `src/trading_system/analysis/alpha_validation.py` (185 baris)

**What:** Workflow validasi alpha factor sebelum production.
**Why:** Factor yang bagus in-sample bisa overfit — perlu OOS test, parameter robustness, dan cost-adjusted returns.
**When:** Sebelum deploy factor baru atau perubahan parameter.
**Where:** Research/testing pipeline, terpisah dari production.
**Who:** Quant developer menjalankan eksperimen validasi.

### 17.1 Validation Criteria

| Kriteria | Threshold | Status |
|----------|-----------|--------|
| OOS Sharpe | ≥ 0.3 | VALID / WATCH / REJECT |
| In-sample Sharpe | ≥ 0.5 | |
| Sortino | ≥ 0.7 | |
| Calmar | ≥ 0.3 | |
| Max drawdown | ≤ 25% | |
| Hit rate | ≥ 45% | |
| Robustness score | ≥ 0.6 | |
| Turnover | ≤ 2.0 (annualized) | |

### 17.2 Validation Flow

```
ExperimentConfig (factor_name, hypothesis, date range)
  → Run backtest with walk-forward
  → Compute in-sample & OOS metrics
  → Parameter robustness test (perturb params ±20%)
  → Regime segmentation (bull/bear/neutral performance)
  → Leakage & survivorship bias check
  → Cost-adjusted returns
  → ValidationResult: VALID / WATCH / REJECT
```

---

## 18. Implementasi: Liquidity Filter

> **Sumber:** `src/trading_system/analysis/liquidity_filter.py` (87 baris)

**What:** Filter saham illiquid berdasarkan average daily volume.
**Why:** Saham illiquid → slippage tinggi, manipulasi mudah, exit sulit. Sistem trading tidak boleh merekomendasikan saham yang tidak bisa dieksekusi.
**When:** Sebelum screening, factor compute, dan backtest.
**Where:** Integrasi dengan `screener.py` dan `factor_screener.py`.
**Who:** Dipanggil otomatis oleh screener dan factor engine.

### 18.1 Parameter

| Parameter | Default | Fungsi |
|-----------|---------|--------|
| `min_volume` | 100,000 shares | Minimum avg daily volume |
| `min_trading_days` | 20 hari | Minimum history untuk filter |

### 18.2 Method

```python
class LiquidityFilter:
    def is_liquid(self, data: pd.DataFrame, window: int = 20) -> bool:
        """True jika avg volume ≥ min_volume dan history ≥ min_trading_days."""

    def filter_liquid(self, tickers_data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Filter dict ticker→DataFrame, keep only liquid stocks."""
```

---

> **Kesimpulan:** Screening saham, AI/ML untuk pola, dan pattern memory adalah **tiga komponen wajib** yang saling terintegrasi. Codebase `trading-system` v0.1.11 sudah punya **fondasi engine-level** yang production-ready untuk ketiganya — screener (2 file), AI/ML (7 file), pattern memory (1 file + DB table 2,386 rows). Yang perlu dilakukan untuk aplikasi ritel adalah **membungkus engine yang sudah ada dengan UI user-friendly** dan menambah beberapa komponen pendukung (gorengan detector production code, pattern evaluation scheduler, context tagging). Estimasi total: 6-9 bulan untuk full implementation, 2-3 bulan untuk MVP. Implementasi Factor Engine: `src/trading_system/analysis/factor_engine.py`, `src/trading_system/analysis/factor_screener.py`. Alpha Composer: `src/trading_system/analysis/alpha_composer.py`. Alpha Validation: `src/trading_system/analysis/alpha_validation.py`. Liquidity Filter: `src/trading_system/analysis/liquidity_filter.py`.
