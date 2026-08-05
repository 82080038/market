# Prediksi, Pola & Portfolio Pipeline: Dari Data Lampau ke Keputusan Portofolio

> **Dokumen 46** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Arsitektur pipeline prediksi masa depan berdasarkan seluruh data lampau dan memori pola, testing per saham dengan self-correction, penyimpanan dan dokumentasi pola per saham, serta pipeline dari bobot prediksi ke kandidat portofolio.

---

## Daftar Isi

1. [Arsitektur Pipeline](#1-arsitektur-pipeline)
2. [Prediction Engine: Prediksi Masa Depan](#2-prediction-engine-prediksi-masa-depan)
3. [Per-Stock Testing & Pattern Discovery](#3-per-stock-testing--pattern-discovery)
4. [Error Analysis Engine: Self-Correction](#4-error-analysis-engine-self-correction)
5. [Pattern Journal: Penyimpanan & Dokumentasi Pola](#5-pattern-journal-penyimpanan--dokumentasi-pola)
6. [Portfolio Candidate Pipeline](#6-portfolio-candidate-pipeline)
7. [Integrasi dengan Modul Existing](#7-integrasi-dengan-modul-existing)
8. [Database Schema](#8-database-schema)
9. [Implementasi Kode](#9-implementasi-kode)
10. [Checklist Implementasi](#10-checklist-implementasi)
11. [Operasional: Kapan & Bagaimana Pipeline Dijalankan](#11-operasional-kapan--bagaimana-pipeline-dijalankan)

---

## 1. Arsitektur Pipeline

### 1.1 Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│              PREDIKSI → POLA → PORTFOLIO PIPELINE                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STAGE 1: DATA AGGREGATION                                          │
│  OHLCV (2.9M) │ Fundamental │ Macro │ Global │ Sentiment            │
│  Foreign Flow │ Broker Flow │ Pattern History (2,386 rows)          │
│                          │                                          │
│  STAGE 2: PER-STOCK TESTING                                         │
│  For each ticker (928 equities):                                    │
│    → Detect all patterns (chart, candlestick, trend, volume)        │
│    → Run LSTM prediction (GPU cuda:1)                               │
│    → Run factor scoring (6 factors)                                 │
│    → Lookup pattern reliability (win-rate per pola per saham)       │
│    → Combine → PREDICTION + CONFIDENCE                              │
│                          │                                          │
│  STAGE 3: PREDICTION ENGINE (FUSION)                                │
│  Fuse: LSTM + Pattern reliability + Factor scores                   │
│  + Regime context + Foreign flow + Sentiment                        │
│  → Direction (UP/DOWN/FLAT) + Expected return + Confidence          │
│  → Reasoning: top 5 factors yang drive prediksi                     │
│                          │                                          │
│  STAGE 4: EVALUATION & SELF-CORRECTION                              │
│  N days later:                                                       │
│    → CORRECT: reinforce pattern, increase confidence                │
│    → WRONG: Error Analysis Engine → root cause → mark → adjust      │
│    → Document to Pattern Journal                                    │
│                          │                                          │
│  STAGE 5: PORTFOLIO CANDIDATE PIPELINE                              │
│  All stocks with prediction + confidence:                           │
│    → Filter: confidence > 60, direction UP                          │
│    → Risk check: VaR, drawdown, liquidity, correlation              │
│    → Portfolio optimization: HRP / Markowitz / Risk Parity          │
│    → Output: kandidat portofolio dengan bobot per saham             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Prinsip Pipeline

| Prinsip | Deskripsi |
|---------|-----------|
| **Per-stock personalized** | Setiap saham punya pola unik. Tidak generic one-size-fits-all. |
| **Pattern memory is persistent** | Pola yang pernah terjadi disimpan selamanya. Tidak dilupakan. |
| **Self-correcting** | Setiap kesalahan prediksi dianalisis, ditandai, dan dijadikan pelajaran. |
| **Fully documented** | Setiap pola, prediksi, dan koreksi tercatat dengan alasan yang dapat ditelusuri. |
| **Portfolio-driven** | Output akhir bukan hanya "BUY BBCA", tapi alokasi portofolio lengkap. |
| **GPU-accelerated** | LSTM training dan inference menggunakan GPU `cuda:1` (lihat `34-performance-engineering-optimization.md` §13). |

---

## 2. Prediction Engine: Prediksi Masa Depan

### 2.1 Konsep

Prediction Engine adalah **fusion layer** yang menggabungkan semua sumber pengetahuan untuk memprediksi arah dan magnitudo pergerakan harga saham dalam N hari ke depan, berdasarkan **seluruh data lampau** dan **memori pola**.

### 2.2 Input Data

| Sumber Data | Modul | Yang Diberikan |
|-------------|-------|----------------|
| **OHLCV historis** | `data/storage.py` | Harga OHLCV, date range 1997-2026, 2.9M rows |
| **Technical indicators** | `analysis/technical.py` | RSI, MACD, ADX, ATR, Bollinger, OBV, Ichimoku, dll. |
| **Pattern history** | `pattern_analysis` table | 2,386 pola terdeteksi dengan outcome SUCCESS/FAIL |
| **Pattern reliability** | `analysis/pattern_reliability.py` | Win-rate per pola per saham |
| **Fundamental data** | `fundamental_data` table | ROE, P/E, P/B, DER, EPS, EBITDA, dll. |
| **Macro data** | `macro_data` table | BI rate, inflasi, GDP, USD/IDR, dll. |
| **Global market** | `analysis/global_market.py` | S&P 500, NASDAQ, VIX, crude oil, gold |
| **Foreign flow** | `foreign_flow` table | Net buy/sell asing per saham per hari |
| **Broker flow** | `broker_flow` table | Konsentrasi broker per saham |
| **Sentiment** | `sentiment/engine.py` | News sentiment, social media, Fear & Greed |
| **Regime** | `analysis/enhanced_regime.py` | Market regime: easing/tightening/growth/slowdown/risk_off |
| **Stock personality** | `stock_personality` table | Volatility, beta, liquidity, dll. |

### 2.3 Output Prediction

```python
@dataclass
class Prediction:
    ticker: str                    # "BBCA.JK"
    direction: str                 # "UP" | "DOWN" | "FLAT"
    expected_return_pct: float     # +5.2 (artinya +5.2% dalam N hari)
    horizon_days: int              # 20 (prediksi untuk 20 hari ke depan)
    confidence: float              # 0-100
    prediction_date: str           # "2026-08-05"
    target_date: str               # "2026-08-25"
    target_price: float            # 8250
    entry_range: tuple[float, float]  # (7850, 7950)
    stop_loss: float               # 7600
    take_profit: float             # 8500
    reasoning: list[dict]          # Top 5 factors yang drive prediksi
    pattern_detected: list[str]    # ["double_bottom", "bullish_engulfing"]
    pattern_win_rates: dict        # {"double_bottom": 0.72, ...}
    regime: str                    # "growth"
    model_version: str             # "lstm_v2.3.1"
    factors_used: dict             # Breakdown kontribusi setiap faktor
    status: str = "PENDING"        # PENDING / SUCCESS / FAIL / EXPIRED
```

### 2.4 Fusion Formula

```python
def fuse_prediction(lstm_pred, pattern_win_rates, factor_scores,
                    regime, foreign_signal, sentiment_score, weights):
    """
    Fuse all signals into final prediction.
    Weights are regime-specific (from AI Learning Engine).
    """
    # Normalize LSTM: -10%→0, +10%→100
    lstm_score = max(0, min(100, (lstm_pred["expected_return"] + 0.10) * 500))

    # Pattern: average win-rate * 100
    pattern_score = (sum(pattern_win_rates.values()) / max(len(pattern_win_rates), 1)) * 100

    # Factor composite: weighted by regime-specific weights
    factor_composite = sum(
        factor_scores.get(k, 50) * weights.get(k, 1/6)
        for k in ["technical", "fundamental", "macro", "global", "relationship", "sentiment"]
    )

    # Foreign flow & sentiment: -100..+100 → 0..100
    foreign_score = (foreign_signal + 100) / 2
    sentiment_norm = (sentiment_score + 100) / 2

    # Weighted fusion
    final_score = (
        lstm_score * 0.25 +
        pattern_score * 0.20 +
        factor_composite * 0.35 +
        foreign_score * 0.10 +
        sentiment_norm * 0.10
    )

    direction = "UP" if final_score > 60 else "DOWN" if final_score < 40 else "FLAT"
    confidence = min(100, abs(final_score - 50) * 2 + pattern_score * 0.3)

    return {"direction": direction, "confidence": confidence, "final_score": final_score}
```

### 2.5 LSTM Per-Ticker

Setiap saham punya model LSTM yang dipersonalisasi — bukan generic one-size-fits-all.

```python
class PerTickerLSTM:
    """LSTM model personalized per ticker. Stored at models/lstm/{ticker}_lstm.pt"""

    def train(self, ticker: str, ohlcv: pd.DataFrame):
        device = get_device()  # auto-detect cuda:1 (lihat §13.6 performance doc)
        features = engineer_features(ohlcv)  # 20+ technical indicators
        X, y = create_sequences(features, lookback=60, horizon=20)

        model = LSTMModel(input_dim=X.shape[2], hidden_dim=128, num_layers=2)
        model.to(device)
        # Train with batch_size <= 64 (4GB VRAM constraint)
        # ...

    def predict(self, ticker: str, recent_data: pd.DataFrame) -> dict:
        # Load model, inference on GPU
        return {"expected_return": 0.052, "confidence_raw": 0.73, "horizon_days": 20}
```

**Catatan GPU:** Training 928 model LSTM per ticker dijadwalkan di off-hours (20:00 WIB, lihat `36-gap-data-timezone-global-idx.md` §9). GPU `cuda:1` untuk heavy compute. Batch size ≤ 64, hidden dim ≤ 256 (lihat `34-performance-engineering-optimization.md` §13).

---

## 3. Per-Stock Testing & Pattern Discovery

### 3.1 Testing Pipeline Per Saham

```python
def test_single_stock(ticker: str, as_of_date: str = None) -> dict:
    """Comprehensive testing for a single stock."""
    # 1. Load all historical data
    ohlcv = storage.get_ohlcv(ticker, end_date=as_of_date)
    if len(ohlcv) < 252:
        return {"status": "SKIP", "reason": "insufficient_data"}

    # 2. Detect ALL patterns currently forming
    current_patterns = technical.detect_patterns(ohlcv.tail(60))

    # 3. Lookup historical reliability per pattern
    pattern_reliabilities = {}
    for pattern in current_patterns:
        reliability = pattern_reliability.score_pattern(ticker, pattern.name)
        pattern_reliabilities[pattern.name] = reliability

    # 4. Run LSTM prediction (GPU)
    lstm_pred = per_ticker_lstm.predict(ticker, ohlcv.tail(60))

    # 5. Run factor scoring (6 factors)
    factor_scores = factor_engine.compute_all_factors(ticker)

    # 6. Get regime, foreign flow, sentiment
    regime = enhanced_regime.get_current_regime()
    foreign_signal = foreign_flow_analyzer.get_signal(ticker)
    sentiment = sentiment_engine.get_score(ticker)

    # 7. FUSE into final prediction
    prediction = prediction_engine.predict(ticker, horizon_days=20)

    # 8. Store prediction for later evaluation
    store_prediction(ticker, prediction)

    # 9. Store detected patterns to Pattern Journal
    for pattern in current_patterns:
        pattern_journal.record_detection(ticker, pattern, prediction, regime, foreign_signal)

    return {"ticker": ticker, "prediction": prediction,
            "patterns_detected": current_patterns, "pattern_reliabilities": pattern_reliabilities}
```

### 3.2 Batch Testing (All 928 Stocks)

```python
def test_all_stocks(as_of_date: str = None) -> list[dict]:
    """Run testing for all active equity tickers. GPU for LSTM batch."""
    tickers = storage.list_active_equity_tickers()  # 928 tickers
    results = []
    for ticker in tickers:
        result = test_single_stock(ticker, as_of_date)
        results.append(result)
    # Sort by confidence (highest first)
    results.sort(key=lambda r: r.get("prediction", {}).get("confidence", 0), reverse=True)
    return results
```

### 3.3 Pattern Discovery (Menemukan Pola Baru)

Selain mendeteksi pola yang sudah dikenal, aplikasi **mencari pola baru** yang belum teridentifikasi:

```python
def discover_patterns(ticker: str, ohlcv: pd.DataFrame) -> list[dict]:
    """
    Discover new, undocumented patterns via clustering.
    Extract all 20-day windows, cluster similar shapes, check outcome consistency.
    """
    windows = extract_windows(ohlcv, window_size=20)
    normalized = normalize_windows(windows)  # z-score normalization
    clusters = cluster_windows(normalized, method="kmeans", n_clusters=20)

    new_patterns = []
    for cluster_id, members in clusters.items():
        outcomes = [compute_forward_return(ohlcv, m["end_date"], 20) for m in members]
        avg_return = np.mean(outcomes)
        win_rate = np.mean([1 if o > 0 else 0 for o in outcomes])

        if len(members) >= 5 and abs(avg_return) > 0.02:  # significant
            new_patterns.append({
                "ticker": ticker,
                "pattern_name": f"discovered_cluster_{cluster_id}",
                "occurrences": len(members),
                "avg_return": avg_return,
                "win_rate": win_rate,
                "example_dates": [m["end_date"] for m in members[:3]],
                "characteristics": describe_cluster(members),
                "is_new": True,
            })
    return new_patterns
```

---

## 4. Error Analysis Engine: Self-Correction

### 4.1 Konsep

Ketika prediksi **salah**, aplikasi tidak hanya mencatat kegagalan — aplikasi **mencari kenapa salah**, menandai jenis kesalahan, dan **memperbaiki/adjust pola** untuk prediksi masa depan.

### 4.2 Error Analysis Flow

```
PREDICTION MADE (Day 0)
    │
    ▼
WAIT N DAYS (horizon)
    │
    ▼
EVALUATE OUTCOME (Day N)
    │
    ├── CORRECT → reinforce pattern, increase confidence
    │
    └── WRONG → Error Analysis Engine activates
                    │
                    ├── 1. CLASSIFY ERROR TYPE
                    │   → Direction wrong? Magnitude wrong? Timing wrong?
                    │   → Regime change? Black swan? Model limitation?
                    │
                    ├── 2. ROOT CAUSE ANALYSIS
                    │   → Which factor was wrong?
                    │   → Which pattern failed?
                    │   → Was foreign flow signal misleading?
                    │   → Did regime change mid-prediction?
                    │
                    ├── 3. MARK & TAG
                    │   → Tag prediction with error type
                    │   → Tag pattern with failure context
                    │   → Store in Pattern Journal with "LESSON LEARNED"
                    │
                    ├── 4. ADJUST & CORRECT
                    │   → Reduce pattern win-rate weight
                    │   → Adjust LSTM feature importance
                    │   → Adjust factor weight for this ticker
                    │   → Update regime-specific weights
                    │
                    └── 5. DOCUMENT
                        → "Pattern Journal: BBCA double_bottom failed on
                           2026-08-05 because foreign sell despite pattern..."
```

### 4.3 Error Types

| Error Type | Deskripsi | Contoh | Auto-Correction |
|------------|-----------|--------|-----------------|
| **DIRECTION_WRONG** | Prediksi UP, actual DOWN | "Prediksi BBCA UP +5%, actual -3%" | Reduce confidence untuk pola ini di saham ini |
| **MAGNITUDE_WRONG** | Arah benar, besaran jauh | "Prediksi +5%, actual +15%" | Adjust LSTM expected return calibration |
| **TIMING_WRONG** | Arah benar, timing meleset | "Naik tapi setelah 45 hari, bukan 20" | Extend horizon atau add timing feature |
| **REGIME_CHANGE** | Regime berubah mid-prediction | "Growth → slowdown di hari 10" | Add regime stability check |
| **PATTERN_FAILED** | Pola terdeteksi tapi gagal | "Double bottom tapi harga turun lebih dalam" | Reduce win-rate, add context filter |
| **FACTOR_MISLEADING** | Faktor beri sinyal salah | "Fundamental tinggi tapi harga turun (macro event)" | Adjust factor weight untuk regime ini |
| **BLACK_SWAN** | Event tak terduga | "Geopolitical event" | Flag as outlier, exclude dari learning |
| **MODEL_LIMITATION** | Model tidak capture pola | "LSTM tidak prediksi sudden gap down" | Add feature atau model lain |

### 4.4 Root Cause Analysis

```python
def analyze_error(prediction: dict, actual_return: float, actual_direction: str) -> dict:
    """Analyze why a prediction was wrong."""
    error_type = classify_error(prediction, actual_return, actual_direction)

    root_causes = []
    corrections = []

    # 1. Check each factor's contribution
    factors = json.loads(prediction.get("factors_json", "{}"))
    for factor, score in factors.items():
        factor_dir = "UP" if score > 50 else "DOWN"
        if factor_dir != actual_direction:
            root_causes.append({"factor": factor, "predicted": factor_dir, "actual": actual_direction})
            corrections.append({"action": "reduce_weight", "target": factor,
                                "ticker": prediction["ticker"], "amount": 0.05})

    # 2. Check pattern failures
    patterns = json.loads(prediction.get("patterns_detected_json", "[]"))
    for pattern_name in patterns:
        rel = pattern_reliability.score_pattern(prediction["ticker"], pattern_name)
        if rel["win_rate"] < 0.50:
            root_causes.append({"factor": f"pattern:{pattern_name}", "win_rate": rel["win_rate"]})
            corrections.append({"action": "reduce_pattern_confidence",
                                "target": pattern_name, "ticker": prediction["ticker"]})

    # 3. Check regime change
    regime_at_pred = prediction.get("regime")
    regime_at_eval = enhanced_regime.get_current_regime()
    if regime_at_pred != regime_at_eval:
        root_causes.append({"factor": "regime", "at_prediction": regime_at_pred,
                            "at_evaluation": regime_at_eval})
        corrections.append({"action": "add_regime_stability_check", "ticker": prediction["ticker"]})

    # 4. Check foreign flow signal
    foreign_at_pred = prediction.get("foreign_flow_signal")
    if foreign_at_pred == "net_buy" and actual_direction == "DOWN":
        root_causes.append({"factor": "foreign_flow", "signal": "net_buy", "actual": "DOWN"})
        corrections.append({"action": "add_context_filter", "target": "foreign_flow",
                            "ticker": prediction["ticker"]})

    lesson = generate_lesson_text(error_type, root_causes, prediction)

    return {"error_type": error_type, "root_causes": root_causes,
            "corrections": corrections, "lesson": lesson}
```

### 4.5 Correction Actions

| Action | Target | Effect |
|--------|--------|--------|
| **reduce_weight** | Factor (technical/fundamental/macro/...) | Kurangi bobot faktor ini untuk saham ini di regime saat ini |
| **increase_weight** | Factor yang benar | Naikkan bobot faktor yang memberi sinyal benar |
| **reduce_pattern_confidence** | Pattern (misal: double_bottom) | Turunkan confidence untuk pola ini di saham ini |
| **increase_pattern_confidence** | Pattern yang benar | Naikkan confidence untuk pola yang berhasil |
| **add_context_filter** | Pattern + context | Hanya gunakan pola jika konteks tertentu terpenuhi |
| **flag_outlier** | Prediction | Tandai sebagai outlier, exclude dari learning |
| **retrain_lstm** | LSTM model untuk ticker ini | Retrain dengan data terbaru termasuk failure case |
| **adjust_horizon** | Prediction horizon | Ubah horizon prediksi (misal: 20 → 30 hari) |
| **add_feature** | LSTM features | Tambahkan feature baru yang bisa mencegah error serupa |

### 4.6 Self-Correction Loop

```python
def self_correction_loop():
    """
    Scheduled task: evaluate all pending predictions whose horizon has passed.
    Run daily at 16:30 WIB (post-close, see timezone doc §9).
    """
    pending = storage.get_pending_predictions()
    for pred in pending:
        result = error_analysis.evaluate_prediction(pred["id"])
        if result["status"] == "FAIL":
            # Apply corrections automatically
            error_analysis.apply_corrections(result["analysis"])
            # Document to Pattern Journal
            pattern_journal.record_failure(pred, result["analysis"])
        elif result["status"] == "SUCCESS":
            # Reinforce successful patterns
            error_analysis.reinforce_success(pred)
            pattern_journal.record_success(pred, result["actual_return"])
```

---

## 5. Pattern Journal: Penyimpanan & Dokumentasi Pola

### 5.1 Konsep

Setiap pola yang pernah terdeteksi untuk setiap saham harus **tersimpan dan terdokumentasi dengan baik** — tidak hanya win-rate, tapi juga konteks, outcome, dan lesson learned.

### 5.2 Pattern Journal Entry

```python
@dataclass
class PatternJournalEntry:
    id: str
    ticker: str                      # "BBCA.JK"
    pattern_name: str                # "double_bottom"
    pattern_type: str                # "chart" | "candlestick" | "trend" | "volume" | "discovered"
    detected_date: str               # "2026-08-04"
    entry_price: float               # 7850

    # Konteks saat pola terdeteksi
    context: dict
    # {"regime": "growth", "foreign_flow": "net_buy", "volume_ratio": 1.8,
    #  "market_sentiment": 65, "global_market": "SP500 +0.5%", "sector_trend": "banking_up"}

    # Prediksi saat pola terdeteksi
    prediction: dict
    # {"direction": "UP", "expected_return": 0.052, "horizon_days": 20,
    #  "confidence": 72, "target_price": 8250, "stop_loss": 7600}

    # Hasil aktual setelah N hari
    outcome: dict
    # {"actual_return": 0.051, "actual_direction": "UP", "result": "SUCCESS",
    #  "evaluation_date": "2026-08-24", "max_drawdown_during": -0.012}

    # Analisis kesalahan (jika gagal)
    error_analysis: dict | None
    # {"error_type": "MAGNITUDE_WRONG", "root_causes": [...],
    #  "corrections": [...], "lesson": "Pola double bottom di BBCA saat foreign sell..."}

    # Win-rate sebelum dan sesudah update
    reliability_before: float        # 0.72
    reliability_after: float         # 0.714

    tags: list[str]                  # ["growth_regime", "foreign_buy", "high_volume"]
    notes: str                       # Catatan tambahan
```

### 5.3 Storage

| Storage | Konten |
|---------|--------|
| **`pattern_analysis` table** | Detection record (existing, 2,386 rows) |
| **`pattern_reliability` table** | Aggregated win-rate per pola per saham (existing) |
| **`pattern_journal` table** (NEW) | Full journal: context + prediction + outcome + error analysis |
| **`prediction_log` table** (NEW) | Semua prediksi + outcome |
| **`error_analysis` table** (NEW) | Root cause untuk prediksi yang gagal |
| **`pattern_context` table** (NEW) | Konteks saat pola terdeteksi |
| **`discovered_patterns` table** (NEW) | Pola baru yang ditemukan oleh ML |

### 5.4 Query Examples

```python
# "Tampilkan semua pola BBCA yang pernah gagal dan pelajarannya"
journal.get_entries(ticker="BBCA.JK", outcome_result="FAIL", include_error_analysis=True)

# "Pola apa yang paling reliable untuk TLKM saat regime growth?"
journal.get_reliable_patterns(ticker="TLKM.JK", regime="growth", min_win_rate=0.65)

# "Pola apa yang sering gagal untuk ASII?"
journal.get_unreliable_patterns(ticker="ASII.JK", max_win_rate=0.40)

# "Tampilkan semua lesson learned untuk BBCA"
journal.get_lessons(ticker="BBCA.JK")

# "Pola baru yang ditemukan oleh ML untuk UNVR"
journal.get_discovered_patterns(ticker="UNVR.JK")
```

### 5.5 Pattern Profile per Saham

Setiap saham punya **Pattern Profile** — dokumentasi lengkap semua pola yang pernah terdeteksi:

```markdown
# Pattern Profile: BBCA.JK

## Statistik
- Total pola terdeteksi: 47
- Total prediksi: 32
- Win-rate overall: 68%
- Pola paling reliable: double_bottom (72%)
- Pola paling tidak reliable: head_and_shoulders (35%)

## Pola Terdeteksi (Top 10)
| Pola | Occurrences | Win Rate | Avg Return | Last Detected | Tags |
|------|-------------|----------|------------|---------------|------|
| double_bottom | 15 | 72% | +8.5% | 2026-08-04 | growth, foreign_buy |
| bullish_engulfing | 12 | 65% | +4.2% | 2026-07-15 | high_volume |
| golden_cross | 8 | 75% | +12.1% | 2026-06-20 | growth, trending |

## Lessons Learned
1. "Double bottom di BBCA saat foreign sell tidak reliable (win-rate 40%).
   Hanya valid jika foreign net buy."
2. "Bullish engulfing + volume > 2x average = 80% win-rate.
   Tanpa volume = 45%."
3. "Golden cross saat regime tightening = 30% win-rate (false signal)."

## Pola Baru yang Ditemukan
- discovered_cluster_3: 8 occurrences, 75% win-rate, avg +6.2%
  - Karakteristik: volume spike + RSI < 35 + foreign net buy
  - Belum diberi nama, perlu validasi lebih lanjut
```

---

## 6. Portfolio Candidate Pipeline

### 6.1 Konsep

Bobot (confidence + expected return) dari setiap saham yang sudah dianalisa dan diprediksi menjadi **kandidat untuk dimasukkan ke dalam portofolio**. Pipeline ini mengkonversi prediksi individual menjadi alokasi portofolio yang optimal.

### 6.2 Pipeline

```
928 STOCKS → PREDICTION ENGINE → FILTER → RISK CHECK → CORRELATION → OPTIMIZATION → PORTFOLIO
              │                     │           │             │              │            │
              ▼                     ▼           ▼             ▼              ▼            ▼
          928 predictions      ~50 candidates  ~20 pass    ~10 diversified  optimal    Final allocation
          (direction,          (confidence     (VaR, DD,   (low correlation) weights    (BBCA 15%,
           confidence)          > 60, UP)       liquidity)                                TLKM 10%, ...)
```

### 6.3 Stage 1: Filter by Confidence

```python
def filter_candidates(predictions: list[Prediction], min_confidence: float = 60) -> list:
    """Filter stocks with sufficient confidence and expected return."""
    return [
        p for p in predictions
        if p.confidence >= min_confidence
        and p.direction == "UP"
        and p.expected_return_pct > 0.02  # minimum 2% expected return
    ]
```

### 6.4 Stage 2: Risk Check

```python
def risk_check(candidates: list[Prediction]) -> list:
    """Filter stocks that pass risk criteria."""
    passed = []
    for pred in candidates:
        # VaR check: skip if VaR > 8%
        var_95 = risk_engine.compute_var(pred.ticker, confidence=0.95)
        if var_95 > 0.08:
            continue
        # Max drawdown: skip if > 25%
        max_dd = risk_engine.compute_max_drawdown(pred.ticker, lookback=252)
        if max_dd > 0.25:
            continue
        # Liquidity: skip if avg volume < 100K
        avg_volume = storage.get_avg_volume(pred.ticker, days=30)
        if avg_volume < 100000:
            continue
        # Auto-reject check (IDX specific)
        if is_auto_reject(pred.ticker):
            continue
        passed.append(pred)
    return passed
```

### 6.5 Stage 3: Correlation Filter

```python
def correlation_filter(candidates: list[Prediction], max_correlation: float = 0.7) -> list:
    """Remove highly correlated stocks for diversification."""
    tickers = [p.ticker for p in candidates]
    corr_matrix = relationship_engine.get_correlation_matrix(tickers)

    # Greedy: keep highest confidence, remove correlated
    sorted_cands = sorted(candidates, key=lambda p: p.confidence, reverse=True)
    selected = []
    for pred in sorted_cands:
        is_correlated = any(
            abs(corr_matrix.loc[pred.ticker, s.ticker]) > max_correlation
            for s in selected
        )
        if not is_correlated:
            selected.append(pred)
    return selected
```

### 6.6 Stage 4: Portfolio Optimization

```python
def optimize_portfolio(candidates: list[Prediction]) -> dict:
    """
    Optimize portfolio weights using expected returns + risk.
    Methods: HRP (Hierarchical Risk Parity) or Markowitz MPT.
    """
    tickers = [p.ticker for p in candidates]
    expected_returns = np.array([p.expected_return_pct for p in candidates])
    cov_matrix = risk_engine.get_covariance_matrix(tickers)

    # Method 1: HRP (robust, no matrix inversion needed)
    weights_hrp = hrp_optimize(cov_matrix, expected_returns)

    # Method 2: Markowitz (max Sharpe)
    weights_markowitz = markowitz_optimize(expected_returns, cov_matrix)

    # Method 3: Risk parity
    weights_risk_parity = risk_parity_optimize(cov_matrix)

    # Select best based on out-of-sample Sharpe
    best = select_best_method(
        {"hrp": weights_hrp, "markowitz": weights_markowitz, "risk_parity": weights_risk_parity},
        cov_matrix, expected_returns,
    )

    return {
        "method": best,
        "weights": {tickers[i]: round(weights_hrp[i], 4) for i in range(len(tickers))},
        "expected_portfolio_return": float(np.dot(weights_hrp, expected_returns)),
        "expected_portfolio_volatility": float(np.sqrt(weights_hrp @ cov_matrix @ weights_hrp)),
        "candidates": tickers,
    }
```

### 6.7 Portfolio Output

```python
@dataclass
class PortfolioCandidate:
    ticker: str                # "BBCA.JK"
    weight: float              # 0.15 (15% of portfolio)
    prediction: Prediction     # Full prediction object
    expected_return: float     # +5.2%
    expected_risk: float       # 12.3% annualized volatility
    position_size_idr: float   # Rp 15,000,000 (if portfolio = Rp 100M)
    entry_range: tuple         # (7850, 7950)
    stop_loss: float           # 7600
    take_profit: float         # 8500
    reasoning: str             # "BBCA: 15% allocation. Confidence 72. Double bottom (72% win-rate)."

@dataclass
class PortfolioAllocation:
    date: str                  # "2026-08-05"
    total_capital: float       # 100000000
    candidates: list[PortfolioCandidate]
    expected_return: float     # +4.8% (portfolio weighted)
    expected_volatility: float # 11.2%
    expected_sharpe: float     # 0.43
    method: str                # "hrp"
    max_single_weight: float   # 0.20 (no stock > 20%)
    sector_allocation: dict    # {"banking": 0.35, "consumer": 0.25, ...}
```

---

## 7. Integrasi dengan Modul Existing

### 7.1 Modul yang Sudah Ada (Adopsi Langsung)

| Modul | File | Fungsi di Pipeline |
|-------|------|-------------------|
| Pattern Detection | `analysis/technical.py` | Stage 2: Detect patterns |
| Pattern Reliability | `analysis/pattern_reliability.py` | Stage 2: Lookup win-rate |
| AI Learning Engine | `ai_learning/engine.py` | Stage 3: Dynamic weights + feedback |
| Deep Learning (LSTM) | `ai_learning/deep_learning.py` | Stage 2: Price prediction (GPU) |
| Walk-Forward | `ai_learning/walk_forward.py` | Validation |
| Model Registry | `ai_learning/model_registry.py` | Model versioning |
| Decision Engine | `decision/engine.py` | Stage 3: Factor scoring |
| Risk Engine | `risk/engine.py` | Stage 5: VaR, drawdown |
| Relationship Engine | `analysis/relationship.py` | Stage 5: Correlation |
| Portfolio Engine | `portfolio/engine.py` | Stage 5: Optimization |
| XAI Engine | `xai/engine.py` | Narrative untuk setiap prediksi |
| Enhanced Regime | `analysis/enhanced_regime.py` | Stage 3: Regime context |
| Foreign Flow | `sentiment/foreign_flow.py` | Stage 3: Foreign signal |
| Sentiment Engine | `sentiment/engine.py` | Stage 3: Sentiment score |

### 7.2 Modul Baru yang Perlu Dibuat

| Modul | File (proposed) | Fungsi |
|-------|-----------------|--------|
| **Prediction Engine** | `analysis/prediction_engine.py` | Fuse all signals → final prediction |
| **Per-Ticker LSTM** | `ai_learning/per_ticker_lstm.py` | Personalized LSTM per saham |
| **Pattern Discovery** | `analysis/pattern_discovery.py` | Find new patterns via clustering |
| **Error Analysis Engine** | `ai_learning/error_analysis.py` | Root cause analysis untuk wrong predictions |
| **Pattern Journal** | `analysis/pattern_journal.py` | Store & query pattern documentation |
| **Portfolio Candidate Pipeline** | `portfolio/candidate_pipeline.py` | Prediction → filter → risk → optimization |
| **Prediction Evaluator** | `analysis/prediction_evaluator.py` | Auto-evaluate predictions N days later |

---

## 8. Database Schema

### 8.1 Tabel Baru

```sql
-- Prediction log: semua prediksi yang pernah dibuat
CREATE TABLE IF NOT EXISTS prediction_log (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    prediction_date TEXT NOT NULL,
    target_date TEXT NOT NULL,
    direction TEXT,              -- UP / DOWN / FLAT
    expected_return_pct REAL,
    confidence REAL,
    target_price REAL,
    entry_price_low REAL,
    entry_price_high REAL,
    stop_loss REAL,
    take_profit REAL,
    regime TEXT,
    model_version TEXT,
    factors_json TEXT,           -- JSON: factor breakdown
    reasoning_json TEXT,         -- JSON: top 5 reasons
    patterns_detected_json TEXT, -- JSON: list of patterns
    foreign_flow_signal TEXT,
    status TEXT DEFAULT 'PENDING', -- PENDING / SUCCESS / FAIL / EXPIRED
    actual_return_pct REAL,
    actual_direction TEXT,
    evaluation_date TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Error analysis: root cause untuk prediksi yang gagal
CREATE TABLE IF NOT EXISTS error_analysis (
    id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    error_type TEXT,             -- DIRECTION_WRONG / MAGNITUDE_WRONG / etc.
    root_causes_json TEXT,       -- JSON: list of root causes
    corrections_json TEXT,       -- JSON: list of correction actions
    lesson_text TEXT,            -- Human-readable lesson
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (prediction_id) REFERENCES prediction_log(id)
);

-- Pattern journal: dokumentasi lengkap per pola per saham
CREATE TABLE IF NOT EXISTS pattern_journal (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    pattern_type TEXT,           -- chart / candlestick / trend / volume / discovered
    detected_date TEXT NOT NULL,
    entry_price REAL,
    context_json TEXT,           -- JSON: regime, foreign_flow, volume, sentiment
    prediction_json TEXT,        -- JSON: direction, expected_return, confidence
    outcome_json TEXT,           -- JSON: actual_return, result, evaluation_date
    error_analysis_id TEXT,      -- FK to error_analysis if failed
    reliability_before REAL,
    reliability_after REAL,
    tags_json TEXT,              -- JSON: list of tags
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (error_analysis_id) REFERENCES error_analysis(id)
);

-- Pattern context: konteks saat pola terdeteksi
CREATE TABLE IF NOT EXISTS pattern_context (
    id TEXT PRIMARY KEY,
    pattern_journal_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    regime TEXT,
    foreign_flow_signal TEXT,    -- net_buy / net_sell / neutral
    volume_ratio REAL,
    market_sentiment REAL,
    global_market_state TEXT,
    sector_trend TEXT,
    days_to_earnings INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (pattern_journal_id) REFERENCES pattern_journal(id)
);

-- Portfolio candidates: kandidat portofolio dari pipeline
CREATE TABLE IF NOT EXISTS portfolio_candidates (
    id TEXT PRIMARY KEY,
    allocation_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    weight REAL,                 -- 0.15 = 15%
    prediction_id TEXT NOT NULL,
    expected_return REAL,
    expected_risk REAL,
    position_size_idr REAL,
    entry_price_low REAL,
    entry_price_high REAL,
    stop_loss REAL,
    take_profit REAL,
    reasoning TEXT,
    status TEXT DEFAULT 'CANDIDATE', -- CANDIDATE / ENTERED / REJECTED / EXPIRED
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (prediction_id) REFERENCES prediction_log(id)
);

-- Discovered patterns: pola baru yang ditemukan oleh ML
CREATE TABLE IF NOT EXISTS discovered_patterns (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    cluster_id INTEGER,
    pattern_name TEXT,           -- "discovered_cluster_3"
    occurrences INTEGER,
    avg_return REAL,
    win_rate REAL,
    example_dates_json TEXT,     -- JSON: list of example dates
    characteristics_json TEXT,   -- JSON: what defines this pattern
    validated BOOLEAN DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 8.2 Index

```sql
CREATE INDEX IF NOT EXISTS idx_prediction_log_ticker ON prediction_log(ticker);
CREATE INDEX IF NOT EXISTS idx_prediction_log_status ON prediction_log(status);
CREATE INDEX IF NOT EXISTS idx_prediction_log_date ON prediction_log(prediction_date);
CREATE INDEX IF NOT EXISTS idx_error_analysis_ticker ON error_analysis(ticker);
CREATE INDEX IF NOT EXISTS idx_error_analysis_type ON error_analysis(error_type);
CREATE INDEX IF NOT EXISTS idx_pattern_journal_ticker ON pattern_journal(ticker);
CREATE INDEX IF NOT EXISTS idx_pattern_journal_pattern ON pattern_journal(pattern_name);
CREATE INDEX IF NOT EXISTS idx_pattern_journal_date ON pattern_journal(detected_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_candidates_date ON portfolio_candidates(allocation_date);
CREATE INDEX IF NOT EXISTS idx_discovered_patterns_ticker ON discovered_patterns(ticker);
```

---

## 9. Implementasi Kode

### 9.1 Prediction Engine

```python
# analysis/prediction_engine.py

from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid

@dataclass
class Prediction:
    id: str
    ticker: str
    direction: str
    expected_return_pct: float
    horizon_days: int
    confidence: float
    prediction_date: str
    target_date: str
    target_price: float
    entry_range: tuple
    stop_loss: float
    take_profit: float
    reasoning: list
    pattern_detected: list
    pattern_win_rates: dict
    regime: str
    model_version: str
    factors_used: dict
    status: str = "PENDING"

class PredictionEngine:
    """Fuse all signals into final prediction per stock."""

    def __init__(self, storage, pattern_reliability, ai_learning,
                 regime_engine, foreign_flow, sentiment_engine, lstm_engine):
        self.storage = storage
        self.pattern_reliability = pattern_reliability
        self.ai_learning = ai_learning
        self.regime_engine = regime_engine
        self.foreign_flow = foreign_flow
        self.sentiment_engine = sentiment_engine
        self.lstm_engine = lstm_engine

    def predict(self, ticker: str, horizon_days: int = 20) -> Prediction | None:
        """Generate prediction for a single ticker."""
        ohlcv = self.storage.get_ohlcv(ticker)
        if len(ohlcv) < 252:
            return None

        current_price = float(ohlcv["close"].iloc[-1])

        # 1. Detect patterns
        patterns = self._detect_patterns(ohlcv.tail(60))

        # 2. Pattern reliability
        pattern_win_rates = {}
        for p in patterns:
            rel = self.pattern_reliability.score_pattern(ticker, p)
            pattern_win_rates[p] = rel.get("win_rate", 0)

        # 3. LSTM prediction (GPU cuda:1)
        lstm_pred = self.lstm_engine.predict(ticker, ohlcv.tail(60))

        # 4. Factor scores
        factor_scores = self._get_factor_scores(ticker)

        # 5. Regime + foreign flow + sentiment
        regime = self.regime_engine.get_current_regime()
        foreign_signal = self.foreign_flow.get_signal(ticker)
        sentiment = self.sentiment_engine.get_score(ticker)

        # 6. Regime-specific weights
        weights = self.ai_learning.get_regime_weights(regime)

        # 7. Fuse
        final_score = self._fuse(
            lstm_pred, pattern_win_rates, factor_scores,
            regime, foreign_signal, sentiment, weights
        )

        direction = "UP" if final_score > 60 else "DOWN" if final_score < 40 else "FLAT"
        confidence = min(100, abs(final_score - 50) * 2 + sum(pattern_win_rates.values()) / max(len(pattern_win_rates), 1) * 30)

        return Prediction(
            id=str(uuid.uuid4()),
            ticker=ticker,
            direction=direction,
            expected_return_pct=lstm_pred.get("expected_return", 0),
            horizon_days=horizon_days,
            confidence=confidence,
            prediction_date=datetime.now().strftime("%Y-%m-%d"),
            target_date=(datetime.now() + timedelta(days=horizon_days)).strftime("%Y-%m-%d"),
            target_price=current_price * (1 + lstm_pred.get("expected_return", 0)),
            entry_range=(current_price * 0.99, current_price * 1.01),
            stop_loss=current_price * 0.95,
            take_profit=current_price * 1.10,
            reasoning=self._build_reasoning(factor_scores, patterns, pattern_win_rates),
            pattern_detected=patterns,
            pattern_win_rates=pattern_win_rates,
            regime=regime,
            model_version="lstm_v2.3.1",
            factors_used=factor_scores,
        )

    def _fuse(self, lstm_pred, pattern_win_rates, factor_scores,
              regime, foreign_signal, sentiment, weights):
        """Fuse all signals into final score 0-100."""
        lstm_score = max(0, min(100, (lstm_pred.get("expected_return", 0) + 0.10) * 500))
        pattern_score = (sum(pattern_win_rates.values()) / max(len(pattern_win_rates), 1)) * 100
        factor_composite = sum(
            factor_scores.get(k, 50) * weights.get(k, 1/6)
            for k in ["technical", "fundamental", "macro", "global", "relationship", "sentiment"]
        )
        foreign_score = (foreign_signal + 100) / 2
        sentiment_norm = (sentiment + 100) / 2

        return (
            lstm_score * 0.25 +
            pattern_score * 0.20 +
            factor_composite * 0.35 +
            foreign_score * 0.10 +
            sentiment_norm * 0.10
        )
```

### 9.2 Error Analysis Engine

```python
# ai_learning/error_analysis.py

class ErrorAnalysisEngine:
    """Analyze why predictions were wrong and apply corrections."""

    def __init__(self, storage, pattern_reliability, ai_learning, regime_engine):
        self.storage = storage
        self.pattern_reliability = pattern_reliability
        self.ai_learning = ai_learning
        self.regime_engine = regime_engine

    def evaluate_prediction(self, prediction_id: str) -> dict:
        """Evaluate a prediction after horizon days have passed."""
        pred = self.storage.get_prediction(prediction_id)
        if not pred or pred["status"] != "PENDING":
            return None

        target_date = datetime.strptime(pred["target_date"], "%Y-%m-%d")
        if datetime.now() < target_date:
            return {"status": "STILL_PENDING"}

        ohlcv = self.storage.get_ohlcv(pred["ticker"],
                                        start=pred["prediction_date"],
                                        end=pred["target_date"])
        if ohlcv.empty:
            return {"status": "NO_DATA"}

        actual_return = (float(ohlcv["close"].iloc[-1]) - pred["entry_price_low"]) / pred["entry_price_low"]
        actual_direction = "UP" if actual_return > 0.01 else "DOWN" if actual_return < -0.01 else "FLAT"
        result = "SUCCESS" if pred["direction"] == actual_direction else "FAIL"

        self.storage.update_prediction(prediction_id, {
            "status": result,
            "actual_return_pct": actual_return,
            "actual_direction": actual_direction,
            "evaluation_date": datetime.now().strftime("%Y-%m-%d"),
        })

        if result == "FAIL":
            analysis = self.analyze_error(pred, actual_return, actual_direction)
            self.storage.save_error_analysis(analysis)
            self.apply_corrections(analysis)
            return {"status": "FAIL", "analysis": analysis}

        self.reinforce_success(pred)
        return {"status": "SUCCESS", "actual_return": actual_return}

    def analyze_error(self, prediction, actual_return, actual_direction):
        """Root cause analysis for a failed prediction."""
        error_type = self._classify_error(prediction, actual_return, actual_direction)
        root_causes, corrections = [], []

        # Check factors
        factors = json.loads(prediction.get("factors_json", "{}"))
        for factor, score in factors.items():
            factor_dir = "UP" if score > 50 else "DOWN"
            if factor_dir != actual_direction:
                root_causes.append({"factor": factor, "predicted": factor_dir, "actual": actual_direction})
                corrections.append({"action": "reduce_weight", "target": factor,
                                    "ticker": prediction["ticker"], "amount": 0.05})

        # Check patterns
        patterns = json.loads(prediction.get("patterns_detected_json", "[]"))
        for pattern_name in patterns:
            rel = self.pattern_reliability.score_pattern(prediction["ticker"], pattern_name)
            if rel["win_rate"] < 0.50:
                root_causes.append({"factor": f"pattern:{pattern_name}", "win_rate": rel["win_rate"]})
                corrections.append({"action": "reduce_pattern_confidence",
                                    "target": pattern_name, "ticker": prediction["ticker"]})

        # Check regime change
        regime_at_eval = self.regime_engine.get_current_regime()
        if prediction.get("regime") != regime_at_eval:
            root_causes.append({"factor": "regime", "at_prediction": prediction.get("regime"),
                                "at_evaluation": regime_at_eval})
            corrections.append({"action": "add_regime_stability_check", "ticker": prediction["ticker"]})

        lesson = self._generate_lesson(error_type, root_causes, prediction)
        return {"prediction_id": prediction["id"], "ticker": prediction["ticker"],
                "error_type": error_type, "root_causes": root_causes,
                "corrections": corrections, "lesson": lesson}

    def apply_corrections(self, analysis):
        """Apply correction actions from error analysis."""
        for c in analysis["corrections"]:
            if c["action"] == "reduce_weight":
                self.ai_learning.adjust_weight(ticker=c["ticker"], factor=c["target"], delta=-c["amount"])
            elif c["action"] == "reduce_pattern_confidence":
                self.pattern_reliability.reduce_confidence(ticker=c["ticker"], pattern=c["target"])

    def reinforce_success(self, pred):
        """Reinforce patterns that led to a successful prediction."""
        patterns = json.loads(pred.get("patterns_detected_json", "[]"))
        for p in patterns:
            self.pattern_reliability.increase_confidence(ticker=pred["ticker"], pattern=p)

    def _classify_error(self, pred, actual_return, actual_direction):
        if pred["direction"] != actual_direction:
            return "DIRECTION_WRONG"
        elif abs(actual_return - pred["expected_return_pct"]) > 0.05:
            return "MAGNITUDE_WRONG"
        else:
            return "TIMING_WRONG"

    def _generate_lesson(self, error_type, root_causes, pred):
        factors_str = ", ".join([r["factor"] for r in root_causes])
        return (f"Prediksi {pred['ticker']} {pred['direction']} gagal ({error_type}). "
                f"Root cause: {factors_str}. Pola: {pred.get('patterns_detected_json', '[]')}. "
                f"Regime: {pred.get('regime', 'unknown')}.")
```

### 9.3 Portfolio Candidate Pipeline

```python
# portfolio/candidate_pipeline.py

class PortfolioCandidatePipeline:
    """Convert predictions into portfolio allocation."""

    def __init__(self, prediction_engine, risk_engine, relationship_engine, storage):
        self.prediction_engine = prediction_engine
        self.risk_engine = risk_engine
        self.relationship_engine = relationship_engine
        self.storage = storage

    def run(self, min_confidence: float = 60, max_correlation: float = 0.7) -> dict:
        """Run full pipeline: predict all stocks → filter → optimize."""
        # 1. Get all predictions
        tickers = self.storage.list_active_equity_tickers()
        predictions = []
        for ticker in tickers:
            pred = self.prediction_engine.predict(ticker)
            if pred:
                predictions.append(pred)

        # 2. Filter by confidence
        candidates = [p for p in predictions
                      if p.confidence >= min_confidence
                      and p.direction == "UP"
                      and p.expected_return_pct > 0.02]

        # 3. Risk check
        candidates = self._risk_check(candidates)

        # 4. Correlation filter
        candidates = self._correlation_filter(candidates, max_correlation)

        # 5. Optimize
        allocation = self._optimize(candidates)

        # 6. Store candidates
        for cand in allocation["candidates"]:
            self.storage.save_portfolio_candidate(cand)

        return allocation

    def _risk_check(self, candidates):
        passed = []
        for pred in candidates:
            var_95 = self.risk_engine.compute_var(pred.ticker, confidence=0.95)
            if var_95 > 0.08:
                continue
            max_dd = self.risk_engine.compute_max_drawdown(pred.ticker, lookback=252)
            if max_dd > 0.25:
                continue
            avg_volume = self.storage.get_avg_volume(pred.ticker, days=30)
            if avg_volume < 100000:
                continue
            passed.append(pred)
        return passed

    def _correlation_filter(self, candidates, max_correlation):
        tickers = [p.ticker for p in candidates]
        corr = self.relationship_engine.get_correlation_matrix(tickers)
        sorted_cands = sorted(candidates, key=lambda p: p.confidence, reverse=True)
        selected = []
        for pred in sorted_cands:
            if all(abs(corr.loc[pred.ticker, s.ticker]) <= max_correlation for s in selected):
                selected.append(pred)
        return selected

    def _optimize(self, candidates):
        if not candidates:
            return {"method": "none", "weights": {}, "candidates": []}

        tickers = [p.ticker for p in candidates]
        expected_returns = np.array([p.expected_return_pct for p in candidates])
        cov_matrix = self.risk_engine.get_covariance_matrix(tickers)

        # HRP optimization (robust)
        weights = hrp_optimize(cov_matrix, expected_returns)

        # Cap max weight at 20%
        weights = np.minimum(weights, 0.20)
        weights = weights / weights.sum()  # renormalize

        return {
            "method": "hrp",
            "weights": {tickers[i]: round(float(weights[i]), 4) for i in range(len(tickers))},
            "expected_return": float(np.dot(weights, expected_returns)),
            "expected_volatility": float(np.sqrt(weights @ cov_matrix @ weights)),
            "candidates": [
                {"ticker": tickers[i], "weight": float(weights[i]),
                 "prediction_id": candidates[i].id,
                 "expected_return": candidates[i].expected_return_pct,
                 "confidence": candidates[i].confidence,
                 "entry_range": candidates[i].entry_range,
                 "stop_loss": candidates[i].stop_loss,
                 "take_profit": candidates[i].take_profit,
                 "reasoning": candidates[i].reasoning}
                for i in range(len(tickers))
            ],
        }
```

---

## 10. Checklist Implementasi

### Prediction Engine
- [ ] `analysis/prediction_engine.py` — fusion LSTM + pattern + factor + regime + sentiment
- [ ] `ai_learning/per_ticker_lstm.py` — personalized LSTM per saham (GPU cuda:1)
- [ ] `prediction_log` table — store semua prediksi
- [ ] Auto-evaluate predictions setelah horizon tercapai

### Per-Stock Testing
- [ ] `test_single_stock()` function — comprehensive testing per ticker
- [ ] `test_all_stocks()` function — batch testing 928 tickers
- [ ] `analysis/pattern_discovery.py` — clustering untuk pola baru
- [ ] `discovered_patterns` table — store pola yang ditemukan ML
- [ ] GPU batch inference untuk 928 tickers (schedule 20:00 WIB)

### Error Analysis & Self-Correction
- [ ] `ai_learning/error_analysis.py` — root cause analysis
- [ ] 8 error types: DIRECTION_WRONG, MAGNITUDE_WRONG, TIMING_WRONG, REGIME_CHANGE, PATTERN_FAILED, FACTOR_MISLEADING, BLACK_SWAN, MODEL_LIMITATION
- [ ] Auto-correction: reduce_weight, reduce_pattern_confidence, add_context_filter, retrain_lstm
- [ ] `error_analysis` table — store root cause + corrections + lesson
- [ ] Self-correction loop: daily 16:30 WIB, evaluate all pending predictions

### Pattern Journal
- [ ] `analysis/pattern_journal.py` — store & query pattern documentation
- [ ] `pattern_journal` table — full entry: context + prediction + outcome + error
- [ ] `pattern_context` table — konteks saat pola terdeteksi
- [ ] Pattern Profile per saham (auto-generated markdown report)
- [ ] Query API: get_reliable_patterns, get_unreliable_patterns, get_lessons

### Portfolio Candidate Pipeline
- [ ] `portfolio/candidate_pipeline.py` — prediction → filter → risk → optimize
- [ ] Filter: confidence > 60, direction UP, expected return > 2%
- [ ] Risk check: VaR < 8%, max drawdown < 25%, liquidity > 100K volume
- [ ] Correlation filter: max 0.7 correlation between candidates
- [ ] Optimization: HRP / Markowitz / Risk Parity (select best)
- [ ] `portfolio_candidates` table — store kandidat dengan bobot
- [ ] Max single weight: 20% (diversification constraint)

### Integrasi
- [ ] Connect ke existing: pattern_reliability, ai_learning, decision_engine, risk_engine
- [ ] XAI narrative untuk setiap prediksi (Bahasa Indonesia)
- [ ] Schedule: test_all_stocks di 18:00 WIB, self-correction di 16:30 WIB
- [ ] GPU: LSTM training di 20:00 WIB off-hours (cuda:1)

---

## 11. Operasional: Kapan & Bagaimana Pipeline Dijalankan

### 11.1 Konteks Operasional

Pipeline ini tidak berjalan sekali lalu selesai — **berjalan setiap hari** sebagai bagian dari siklus operasional aplikasi. Jadwal mengacu pada waktu WIB (GMT+7, lihat `36-gap-data-timezone-global-idx.md` §9) dan dibagi berdasarkan fase pasar: pre-market, market hours, post-market, dan off-hours.

### 11.2 Jadwal Harian Pipeline (WIB)

```
WIB   00    02    04    06    08    10    12    14    16    18    20    22    24
      │     │     │     │     │     │     │     │     │     │     │     │     │
      ░░░░░░░░░░░░░░░░░░░░░░░ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ░░░░░░░░░░░░░░░░░░░░░░
      │     │     │     │     │     │     │     │     │     │     │     │     │
      │     │     │     │  ⑥  │  ①  │   IDX TRADING    │ ②③ │ ④  │ ⑤  │  ⑦  │
      │     │     │     │ Gap │ Pre │   09:00-15:50    │Self│Test│Port│ LSTM│
      │     │     │     │ Pred│ Mkt │                   │Corr│ All│Cand│Train│
      │     │     │     │ 06  │ Scan│                   │16:30│18  │18:30│ 20  │
      │     │     │     │     │ 08  │                   │    │    │    │     │
      │     │     │  US  │     │     │                   │    │    │    │     │
      │     │     │ Close│     │     │                   │    │    │    │     │
      │     │     │ 05  │     │     │                   │    │    │    │     │
      DB    │     │     │     │     │                   │    │    │    │     │
      Bkp   │     │     │     │     │                   │    │    │    │     │
      01    │     │     │     │     │                   │    │    │    │     │

Legend: ▓ = IDX market hours, ░ = off-hours, ①-⑦ = pipeline stages
```

### 11.3 Detail Setiap Stage per Hari

| # | Stage | Waktu WIB | Fase Pasar | Trigger | Yang Dijalankan | Output |
|---|-------|-----------|------------|---------|-----------------|--------|
| ① | **Pre-Market Scan** | 08:30 | Pre-market | Schedule (cron) | `test_single_stock()` untuk setiap saham di watchlist (bukan semua 928) | Quick prediction untuk watchlist stocks. Update watchlist alerts. |
| ② | **Self-Correction Loop** | 16:30 | Post-close | Schedule (cron) | `error_analysis.evaluate_prediction()` untuk semua prediksi yang horizon-nya sudah tercapai | Update status PENDING → SUCCESS/FAIL. Apply corrections. Update Pattern Journal. |
| ③ | **EOD Data Fetch** | 16:30 | Post-close | Schedule (cron) | Fetch OHLCV EOD untuk semua 928 tickers (Yahoo Finance, 10 min delay sudah selesai) | Data OHLCV terbaru tersimpan di DB. |
| ④ | **Test All Stocks** | 18:00 | Post-close | Schedule (cron), setelah EOD data + foreign flow tersedia | `test_all_stocks()` untuk 928 active equities. Jalankan Prediction Engine untuk setiap ticker. | 928 predictions (direction, confidence, expected return). Store ke `prediction_log`. |
| ⑤ | **Portfolio Candidate Pipeline** | 18:30 | Post-close | Setelah ④ selesai | `candidate_pipeline.run()` — filter, risk check, correlation, optimization | Portfolio allocation dengan bobot per saham. Store ke `portfolio_candidates`. |
| ⑥ | **Gap Prediction** | 06:00 | Pre-market (next day) | Schedule (cron), setelah US close (05:00 WIB) | `overnight_gap_prediction()` — prediksi arah IDX open berdasarkan US/Europe semalam | Gap prediction score. Update pre-market signals. |
| ⑦ | **LSTM Retrain** | 20:00 | Off-hours | Schedule (cron), mingguan (Sabtu malam) | `per_ticker_lstm.train()` untuk tickers yang model-nya perlu update. GPU `cuda:1`. | Updated LSTM models per ticker. Store ke `models/lstm/`. |
| — | **DB Backup** | 01:00 | Midnight | Schedule (cron) | SQLite backup + Parquet archive sync | Backup file. |

### 11.4 Dependency Chain

```
EOD Data Fetch (16:30)
    │
    ├── Self-Correction Loop (16:30, parallel)
    │       │
    │       └── Update Pattern Journal
    │
    ▼
Foreign Flow Scrape (17:00)
    │
    ▼
Score Compute (18:00) ── Test All Stocks (18:00)
    │                       │
    │                       ├── Pattern Detection (per ticker)
    │                       ├── LSTM Prediction (GPU, per ticker)
    │                       ├── Factor Scoring (per ticker)
    │                       └── Fusion → Prediction
    │
    ▼
Portfolio Candidate Pipeline (18:30)
    │
    ├── Filter: confidence > 60
    ├── Risk Check: VaR, drawdown, liquidity
    ├── Correlation Filter: max 0.7
    └── Optimization: HRP / Markowitz
    │
    ▼
Portfolio Allocation Output
    │
    ▼
User Review (next morning, 08:30 pre-market)
    │
    ├── User melihat kandidat portofolio di UI
    ├── User approve/reject kandidat
    └── Approved candidates → execution queue
```

### 11.5 Mode Eksekusi

Pipeline dapat dijalankan dalam 3 mode:

| Mode | Kapan | Scope | GPU? | Durasi Estimasi |
|------|-------|-------|------|-----------------|
| **Full** (daily) | 18:00 WIB post-close | 928 tickers | Ya (LSTM batch inference, `cuda:1`) | ~30-45 menit |
| **Watchlist** (pre-market) | 08:30 WIB | ~20-50 tickers di watchlist | Ya (LSTM inference) | ~3-5 menit |
| **Single** (on-demand) | User request via UI/CLI | 1 ticker | Ya (LSTM inference) | ~5 detik |
| **Retrain** (weekly) | 20:00 WIB Sabtu malam | 928 tickers (LSTM training) | Ya (`cuda:1`, batch ≤64) | ~4-8 jam |

### 11.6 Trigger Mechanism

```python
# scripts/daily_pipeline_runner.py
"""
Daily pipeline runner. Scheduled via cron or systemd timer.
Runs every trading day (skip IDX holidays and weekends).
"""

SCHEDULE = {
    # Pre-market
    "06:00": ["gap_prediction"],           # Overnight gap prediction
    "08:30": ["pre_market_scan"],          # Watchlist quick scan

    # Post-market
    "16:30": ["eod_data_fetch", "self_correction"],  # Parallel
    "17:00": ["foreign_flow_scrape"],
    "18:00": ["test_all_stocks"],          # Full pipeline: 928 tickers
    "18:30": ["portfolio_candidate_pipeline"],  # After test_all_stocks

    # Off-hours
    "20:00": ["lstm_retrain_weekly"],      # Saturday only
    "01:00": ["db_backup"],
}

def run_stage(stage: str):
    """Run a single pipeline stage."""
    if stage == "gap_prediction":
        overnight_gap_prediction()
    elif stage == "pre_market_scan":
        for ticker in get_watchlist_tickers():
            test_single_stock(ticker)
    elif stage == "self_correction":
        error_analysis.evaluate_all_pending()
    elif stage == "test_all_stocks":
        test_all_stocks()  # 928 tickers, GPU cuda:1
    elif stage == "portfolio_candidate_pipeline":
        candidate_pipeline.run()
    elif stage == "lstm_retrain_weekly":
        if is_weekend():  # Only Saturday
            retrain_all_lstm()  # GPU cuda:1, 4-8 hours
```

### 11.7 Integrasi dengan Schedule Existing

Pipeline ini **melengkapi** (bukan menggantikan) jadwal yang sudah ada di `36-gap-data-timezone-global-idx.md` §9.3:

| Operasi Existing (§9.3) | Waktu | Operasi Pipeline 46 | Waktu | Relasi |
|--------------------------|-------|----------------------|-------|--------|
| Fetch OHLCV IDX | 16:30 | EOD Data Fetch (③) | 16:30 | **Sama** — pipeline menggunakan data ini |
| Foreign flow scrape | 17:00 | — | — | Pipeline menunggu data ini selesai sebelum test_all_stocks |
| Compute scores | 18:00 | Test All Stocks (④) | 18:00 | **Sama** — pipeline menggantikan/extend score compute dengan full prediction |
| US market monitor | 22:30 | — | — | Tidak terkait langsung (monitoring only) |
| US close check | 05:00 | Gap Prediction (⑥) | 06:00 | Gap prediction menggunakan US close data |
| DB backup | 01:00 | — | — | Tidak terkait |

### 11.8 Estimasi Resource Usage

| Stage | CPU | GPU | RAM | Disk | Network |
|-------|-----|-----|-----|------|---------|
| Pre-Market Scan (20 tickers) | 20% | 10% (LSTM inference) | 500 MB | — | Yahoo API |
| Self-Correction (100 predictions) | 30% | — | 200 MB | Write to DB | — |
| Test All Stocks (928 tickers) | 60% | 80% (LSTM batch, `cuda:1`) | 2 GB | Write to DB | Yahoo API (if data missing) |
| Portfolio Pipeline (50→10 stocks) | 40% | — | 500 MB | Write to DB | — |
| LSTM Retrain (928 models) | 30% | 95% (`cuda:1`, batch=64) | 3 GB | Write models/ | — |

### 11.9 Failure Handling

| Skenario | Yang Terjadi | Recovery |
|----------|-------------|----------|
| Yahoo API down saat EOD fetch | Data OHLCV tidak tersedia | Retry 3x, fallback ke Google Finance, skip stage ④ jika masih gagal |
| GPU tidak tersedia (CUDA error) | LSTM inference tidak bisa jalan | Fallback ke CPU (slow but works). Log warning. |
| DB lock (SQLite WAL) | Write ke prediction_log gagal | Retry dengan backoff. Jika persist, skip stage. |
| IDX holiday | Tidak ada trading | Skip semua stage kecuali self-correction dan DB backup |
| Aplikasi crash mid-pipeline | Sebagian predictions tersimpan | Resume dari ticker terakhir yang belum diproses (checkpoint) |

### 11.10 User Interaction Flow

```
POST-CLOSE (16:30-18:30 WIB)
    │
    ├── Aplikasi menjalankan pipeline otomatis (background)
    │
    ▼
NEXT MORNING (08:30 WIB, pre-market)
    │
    ├── User buka aplikasi
    ├── UI menampilkan: "Pipeline kemarin selesai. 47 kandidat portofolio ditemukan."
    ├── User review kandidat:
    │   ├── Lihat prediction per saham (direction, confidence, reasoning)
    │   ├── Lihat pattern yang terdeteksi + win-rate
    │   ├── Lihat portfolio allocation suggestion (HRP weights)
    │   ├── Lihat lessons learned dari prediksi yang gagal kemarin
    │   └── Approve/reject kandidat
    │
    ▼
MARKET OPEN (09:00 WIB)
    │
    ├── Approved candidates → entry orders (manual atau auto-trade)
    ├── Set stop-loss, take-profit sesuai prediction
    └── Monitor positions during market hours
    │
    ▼
MARKET CLOSE (15:50 WIB)
    │
    ├── Update position PnL
    └── Tunggu post-close pipeline (16:30)
```

### 11.11 Hari Libur & Weekend

| Hari | Pipeline Activity |
|------|-------------------|
| **Senin-Kamis** | Full pipeline: ①②③④⑤⑥ |
| **Jumat** | Full pipeline (short session, schedule adjust: Sesi 1 09:00-11:30, Sesi 2 14:00-15:50) |
| **Sabtu** | ⑦ LSTM Retrain (20:00 WIB, GPU cuda:1, 4-8 jam). Tidak ada ①-⑥. |
| **Minggu** | Tidak ada pipeline. REST. |
| **IDX Holiday** | Hanya ② Self-Correction (jika ada pending predictions) + DB backup. Skip ①③④⑤⑥. |
| **US Holiday** | ⑥ Gap Prediction skip (US market tutup). Pipeline lain normal. |

### 11.12 CLI Commands (Proposed)

```bash
# Run full pipeline manually
python -m trading_system.cli pipeline --full

# Run single stock prediction
python -m trading_system.cli predict BBCA.JK

# Run watchlist scan
python -m trading_system.cli pipeline --watchlist

# Run self-correction only
python -m trading_system.cli pipeline --self-correct

# Run portfolio candidate pipeline
python -m trading_system.cli pipeline --portfolio

# Run LSTM retrain
python -m trading_system.cli pipeline --retrain --gpu cuda:1

# View pipeline status
python -m trading_system.cli pipeline --status

# View predictions
python -m trading_system.cli predictions --ticker BBCA.JK
python -m trading_system.cli predictions --pending
python -m trading_system.cli predictions --failed --limit 10

# View portfolio candidates
python -m trading_system.cli portfolio-candidates --latest

# View pattern journal
python -m trading_system.cli pattern-journal --ticker BBCA.JK
python -m trading_system.cli pattern-journal --lessons --ticker BBCA.JK
```

---

## Referensi

1. `pustaka/39-screening-aiml-pattern-memory.md` — Pattern memory, AI/ML, feedback loop (existing)
2. `pustaka/23-machine-learning-trading.md` — ML pipeline, walk-forward, ensemble
3. `pustaka/18-modul-engine-data-wajib.md` — Decision & Learning Layer
4. `pustaka/31-risk-management-lanjutan.md` — VaR, position sizing, Kelly
5. `pustaka/34-performance-engineering-optimization.md` §13 — GPU/CUDA acceleration
6. `pustaka/36-gap-data-timezone-global-idx.md` §9 — Schedule WIB, timezone awareness
7. `src/trading_system/ai_learning/deep_learning.py` — LSTM implementation (PyTorch CUDA)
8. `src/trading_system/analysis/pattern_reliability.py` — Pattern win-rate engine
9. `src/trading_system/ai_learning/engine.py` — Dynamic weight optimization
10. `src/trading_system/decision/engine.py` — 6-factor weighted decision
11. `src/trading_system/xai/engine.py` — Explainable AI narrative
12. López de Prado, M. (2018) — *Advances in Financial Machine Learning* — HRP, triple-barrier, purged TSS

---

> **Catatan:** Pipeline ini adalah evolusi dari modul yang sudah production-ready di project `global`. Yang sudah ada: pattern detection, pattern reliability, LSTM, AI learning, decision engine, risk engine, XAI. Yang perlu dibuat: Prediction Engine (fusion), Error Analysis Engine (self-correction), Pattern Journal (documentation), Portfolio Candidate Pipeline (allocation). Setiap saham diperlakukan unik — pola, win-rate, dan koreksi disimpan per saham. Kesalahan prediksi bukan kegagalan, tetapi pelajaran yang membuat sistem lebih cerdas dari waktu ke waktu. Untuk arsitektur lengkap yang menyatukan self-correction + self-awareness + self-evolution menjadi "Gigantic AI", lihat `86-gigantic-ai-autonomous-trading-system.md`.
