# Audit Framework AI/ML dalam Sistem Trading Quant

> **Framework komprehensif untuk mengevaluasi apakah model AI/ML memberikan Alpha atau justru overfitting dan membuang biaya komputasi.**

---

## Daftar Isi

1. [Konteks Sistem](#1-konteks-sistem)
2. [Pilar 1: Model Performance Metrics](#2-pilar-1-model-performance-metrics)
3. [Pilar 2: Ablation Study](#3-pilar-2-ablation-study)
4. [Pilar 3: Latency & Cost-Benefit Analysis](#4-pilar-3-latency--cost-benefit-analysis)
5. [Pilar 4: Feature Importance & Drift Audit](#5-pilar-4-feature-importance--drift-audit)
6. [Matriks Evaluasi](#6-matriks-evaluasi)
7. [Checklist Audit Taktis](#7-checklist-audit-taktis)
8. [Referensi](#8-referensi)

---

## 1. Konteks Sistem

### 1.1 Model AI/ML yang Tertanam

Sistem ini memiliki beberapa lapisan AI/ML yang perlu diaudit:

| Lapisan | Model | Lokasi Kode | GPU? | Output |
|---------|-------|-------------|------|--------|
| **MLSignalProvider** | LightGBM (200 trees, 18 features, walk-forward CV) | `src/market/analysis/ml_signal.py` | Tidak | Signal [-1, 1] |
| **MultiFactorModel** | LightGBM 3-class (300 trees, 25+ features, PCA + feature selection) | `src/market/analysis/multi_factor.py` | Tidak | BUY/SELL/HOLD + probabilities |
| **LSTMModel** | PyTorch LSTM (price prediction) | `src/market/mlops/training.py` | Ya (`cuda:1`) | Price forecast |
| **LightGBMEnsemble** | LightGBM ensemble (tabular features) | `src/market/mlops/training.py` | Tidak | Return prediction |
| **SelfEvolutionAgent** | LLM-based 9-stage loop (observe→evolve) | `src/market/autonomous/agent.py` | Tidak (API) | Code/strategy patches |
| **SentimentEngine** | Lexicon-based NLP (EN+ID) | `src/market/analysis/sentiment.py` | Tidak | Sentiment score |
| **PredictionEngine** | Ensemble (MA, momentum, pattern, vol-adjusted) | `src/market/analysis/prediction.py` | Tidak | Price + direction |
| **DecisionEngine** | Weighted factor combination + regime adjustment | `src/market/analysis/decision.py` | Tidak | Recommendation |

### 1.2 Pertanyaan Audit Utama

1. **Apakah AI memberikan Alpha?** — Apakah sinyal AI menghasilkan return di atas benchmark (IHSG) setelah biaya?
2. **Apakah AI overfitting?** — Apakah performa training >> performa out-of-sample?
3. **Apakah AI worth it?** — Apakah peningkatan return > biaya komputasi (GPU, API, waktu)?
4. **Apakah AI masih valid?** — Apakah terjadi model decay / feature drift?

---

## 2. Pilar 1: Model Performance Metrics

### 2.1 Metrik Wajib (Bukan Sekadar Akurasi)

Akurasi klasifikasi (BUY/SELL/HOLD) menyesatkan di trading karena:
- **Class imbalance**: HOLD mendominasi (~60-70% hari)
- **Cost asymmetry**: salah prediksi SELL saat market naik vs salah BUY saat market turun punya cost berbeda
- **Magnitude matters**: prediksi BUY yang benar tapi return 0.1% tidak cukup untuk cover biaya

#### Metrik Portfolio-Level (Wajib)

| Metrik | Formula | Target Minimum | Interpretasi |
|--------|---------|----------------|--------------|
| **Sharpe Ratio** | `(R_p - R_f) / σ_p` | ≥ 1.0 (annualized) | Return per unit risk. <0.5 = tidak worth, >2.0 = curiga overfit |
| **Sortino Ratio** | `(R_p - R_f) / σ_downside` | ≥ 1.5 | Sharpe tapi hanya hitung downside volatility. Lebih realistis untuk trading |
| **Maximum Drawdown** | `min(P_t / max(P_0..t) - 1)` | ≤ -15% | Worst peak-to-trough loss. >-25% = risk management gagal |
| **Information Ratio** | `(R_p - R_b) / TE` | ≥ 0.5 | Alpha per unit tracking error vs benchmark (IHSG) |
| **Calmar Ratio** | `CAGR / |MaxDD|` | ≥ 1.0 | Return vs drawdown risk |
| **Win Rate** | `n_wins / n_trades` | ≥ 45% | Tingkat kemenangan. <40% = model tidak punya edge |
| **Profit Factor** | `Σ(profits) / |Σ(losses)|` | ≥ 1.3 | Total profit vs total loss. <1.0 = rugi pasti |
| **Expectancy** | `(WinRate × AvgWin) - (LossRate × AvgLoss)` | > 0 | Expected return per trade dalam R (risk unit) |

#### Metrik Sinyal-Level (Per Prediksi)

| Metrik | Formula | Target | Interpretasi |
|--------|---------|--------|--------------|
| **Directional Accuracy** | `P(sign(pred) == sign(actual))` | ≥ 52% | Apakah arah prediksi benar? 50% = random |
| **IC (Information Coefficient)** | `Spearman(pred, actual_return)` | ≥ 0.05 | Rank correlation prediksi vs return. <0.02 = noise |
| **Hit Rate per Class** | Per-class accuracy | BUY ≥ 50%, SELL ≥ 50% | Apakah model benar-benar bisa membedakan BUY vs SELL? |
| **Brier Score** | `mean((prob - outcome)^2)` | ≤ 0.22 | Kalibrasi probabilitas. 0.25 = random untuk 4-class |
| **Precision@K** | Top-K prediction accuracy | ≥ 55% | Dari top 10 rekomendasi, berapa yang profit? |

### 2.2 Definisi "Alpha" yang Benar

Alpha = Return strategi - Return benchmark - Biaya trading - Risk-free rate

```
Alpha = (R_strategy - R_benchmark) - (commission + slippage + spread + tax)
```

**Biaya IDX per round-trip:**
- Komisi broker: 0.15% (online discount)
- Spread: 0.05-0.20% (liquid stocks)
- Slippage: 0.05-0.10% (market order)
- PPh final: 0.1% (jual only)
- **Total per round-trip: ~0.35-0.55%**

**Implikasi:** Untuk swing trading dengan hold period 5-10 hari, Alpha harus > 0.5% per trade untuk break even.

---

## 3. Pilar 2: Ablation Study

### 3.1 Metodologi

Ablation study = menghapus komponen AI satu per satu dan mengukur dampaknya pada profitabilitas.

#### Skenario Pengujian

| Skenario | Komponen Aktif | Tujuan |
|----------|----------------|--------|
| **A: Full AI** | MLSignal + MultiFactor + LSTM + Sentiment + DecisionEngine | Baseline sistem lengkap |
| **B: Tanpa LSTM** | MLSignal + MultiFactor + Sentiment + DecisionEngine | Apakah LSTM memberi nilai tambah? |
| **C: Tanpa MultiFactor** | MLSignal + LSTM + Sentiment + DecisionEngine | Apakah MultiFactor (PCA + feature selection) worth it? |
| **D: Tanpa MLSignal** | MultiFactor + LSTM + Sentiment + DecisionEngine | Apakah MLSignal redundant vs MultiFactor? |
| **E: Tanpa Sentiment** | MLSignal + MultiFactor + LSTM + DecisionEngine | Apakah sentiment NLP memberi Alpha? |
| **F: Tanpa AI (Baseline)** | Technical only (RSI, MACD, MA crossover) + fundamental | Apakah AI lebih baik dari aturan dasar? |
| **G: Random Signal** | Random BUY/SELL dengan probabilitas sama | Floor / null hypothesis |

#### Hipotesis Nol (H0)

**H0: AI tidak memberikan Alpha yang signifikan secara statistik dibandingkan baseline teknikal.**

Jika p-value > 0.05 untuk perbandingan A vs F, maka AI tidak terbukti memberikan Alpha.

### 3.2 Logika Deteksi Kontribusi AI

```
Delta_Alpha = Alpha(A: Full AI) - Alpha(F: Baseline Teknikal)

Jika Delta_Alpha > 0.5% per trade AND p-value < 0.05:
    → AI memberikan kontribusi signifikan
    → Lanjutkan penggunaan AI

Jika Delta_Alpha > 0 tapi p-value > 0.05:
    → Peningkatan tidak signifikan secara statistik
    → AI mungkin hanya noise
    → Pertimbangkan simplifikasi model

Jika Delta_Alpha ≤ 0:
    → AI merugikan (overfitting atau noise)
    → Hapus komponen AI yang tidak kontributif
```

### 3.3 Per-Komponen Ablation Delta

Untuk setiap komponen X (LSTM, MultiFactor, MLSignal, Sentiment):

```
Delta_X = Alpha(Full) - Alpha(Tanpa X)

Jika Delta_X ≤ 0: Komponen X merugikan → HAPUS
Jika 0 < Delta_X < cost_X: Komponen X tidak worth biayanya → HAPUS
Jika Delta_X > cost_X: Komponen X memberikan nilai → PERTAHANKAN
```

### 3.4 Implementasi dengan Walk-Forward

Pengujian harus dilakukan dengan **walk-forward backtest** (bukan single train-test split):

1. Bagi data menjadi window berurutan (mis. 252 hari train, 63 hari test)
2. Untuk setiap window:
   - Train semua model pada data train
   - Jalankan backtest pada data test untuk setiap skenario (A-G)
   - Catat return, Sharpe, MaxDD per skenario
3. Agregasi hasil across windows
4. Uji signifikansi statistik (paired t-test atau Diebold-Mariano test)

---

## 4. Pilar 3: Latency & Cost-Benefit Analysis

### 4.1 Latency Audit

Untuk setiap komponen AI, ukur **end-to-end latency** dari sinyal masuk hingga rekomendasi keluar:

| Komponen | Target Latency | Method |
|----------|----------------|--------|
| MLSignal | < 500ms | `time.perf_counter()` around `predict()` |
| MultiFactor | < 2s | Feature pipeline + LightGBM inference |
| LSTM | < 1s (GPU) / < 5s (CPU) | PyTorch inference timing |
| Sentiment | < 200ms | NLP lexicon scoring |
| DecisionEngine | < 100ms | Weighted combination |
| SelfEvolution | N/A (async) | Tidak real-time, jalankan off-hours |
| **Total E2E** | < 5s | Single ticker recommendation |

**Untuk Day Trading (15-min polling):** Total latency < 15 detik (agar masih ada waktu eksekusi).
**Untuk Swing Trading (EOD):** Latency tidak kritis (< 5 menit acceptable).

### 4.2 Cost-Benefit Matrix

| Komponen | Cost/Bulan | Revenue Lift/Bulan | Net Benefit | Verdict |
|----------|------------|-------------------|-------------|---------|
| MLSignal | Rp 0 (CPU) | ? | ? | ? |
| MultiFactor | Rp 0 (CPU) | ? | ? | ? |
| LSTM (GPU) | Listrik ~Rp 150K/bln | ? | ? | ? |
| SelfEvolution (LLM API) | $X API cost | ? | ? | ? |
| Sentiment | Rp 0 (CPU) | ? | ? | ? |

**Formula:**
```
Net Benefit = Revenue Lift - Total Cost
Revenue Lift = (Alpha_AI - Alpha_baseline) × Portfolio Value × Trade Frequency
```

### 4.3 Break-Even Analysis

```
Break-even AUM = Monthly Cost / (Monthly Alpha %)
```

Contoh: Jika LLM API cost $50/bulan dan Alpha dari SelfEvolution = 0.2%/bulan:
```
Break-even = $50 / 0.002 = $25,000
```
Jika portfolio < $25,000, SelfEvolution tidak worth it.

---

## 5. Pilar 4: Feature Importance & Drift Audit

### 5.1 Feature Importance Audit

Untuk setiap model, periksa:

1. **Top features apakah masuk akal?** — Jika feature #1 adalah "volume_ratio_lag_47" yang tidak punya justifikasi teori, curigai overfit
2. **Feature concentration** — Jika 1 feature menyumbang >50% importance, model terlalu bergantung pada 1 sinyal
3. **Feature stability** — Apakah top features konsisten across walk-forward windows? Jika tidak, model menangkap noise
4. **Redundancy** — Apakah ada pasangan feature dengan correlation > 0.9? Hapus salah satu

### 5.2 Feature Drift Detection

**Population Stability Index (PSI):**

```
PSI = Σ (p_current - p_reference) × ln(p_current / p_reference)

PSI < 0.1:  Tidak ada drift (stable)
PSI 0.1-0.25: Drift moderat (monitor)
PSI > 0.25: Drift signifikan (RETRAIN)
```

**Kapan cek drift:**
- Setelah event besar (crash, policy change, geopolitical shock)
- Bulanan untuk model swing trading
- Mingguan untuk model day trading
- Saat validation accuracy turun > 5pp dari baseline

### 5.3 Model Decay Indicators

| Indikator | Threshold | Action |
|-----------|-----------|--------|
| Validation accuracy drop | > 5pp dari baseline | Retrain |
| IC drop | > 30% dari baseline | Retrain |
| Sharpe drop | > 0.3 dari baseline | Pause + investigate |
| Feature drift (PSI) | > 0.25 | Retrain dengan data baru |
| Prediction distribution shift | KS test p < 0.05 | Calibrate atau retrain |
| Win rate drop | > 10pp dari baseline | Pause model |

### 5.4 Market Regime Shift Detection

Model bisa decay bukan karena model buruk, tapi karena **regime pasar berubah**:

| Regime | Karakteristik | Model Performance |
|--------|--------------|-------------------|
| **Trending bull** | SMA50 > SMA200, low vol | Momentum models excel |
| **Trending bear** | SMA50 < SMA200, high vol | Mean reversion models excel |
| **Sideways/range** | Low ADX, low vol | Pattern models excel |
| **Crisis/high vol** | VIX > 30, sharp moves | Most models fail → cash/hedge |

**Audit:** Bandingkan model performance per regime. Jika model hanya unggul di 1 regime, tambahkan regime detection + model switching.

---

## 6. Matriks Evaluasi

### 6.1 AI Utility Score Card

| Kriteria | Bobot | Skor (0-5) | Bobot×Skor |
|----------|-------|-----------|------------|
| Alpha vs benchmark (annualized) | 25% | 0=no alpha, 5=>5% alpha | |
| Sharpe ratio improvement | 20% | 0=<0, 5=>1.0 improvement | |
| Statistical significance (p-value) | 15% | 0=p>0.2, 5=p<0.01 | |
| Cost efficiency (benefit/cost ratio) | 15% | 0=<1x, 5=>10x | |
| Latency acceptable | 10% | 0=>60s, 5=<1s | |
| Model stability (low drift) | 10% | 0=high drift, 5=stable | |
| Feature interpretability | 5% | 0=black box, 5=fully explainable | |
| **Total** | 100% | | **/5.0** |

**Verdict:**
- **≥ 3.5:** AI memberikan nilai signifikan → pertahankan dan optimalkan
- **2.0-3.4:** AI memberikan nilai marginal → optimasi atau simplifikasi
- **< 2.0:** AI tidak memberikan nilai → hapus atau rearchitect

### 6.2 Per-Komponen Verdict Matrix

| Komponen | Alpha Delta | Cost | Statistical Sig. | Verdict |
|----------|-------------|------|-------------------|---------|
| MLSignal | ? | Rp 0 | ? | ? |
| MultiFactor | ? | Rp 0 | ? | ? |
| LSTM | ? | Rp 150K/bln | ? | ? |
| SelfEvolution | ? | $X/bln | ? | ? |
| Sentiment | ? | Rp 0 | ? | ? |

---

## 7. Checklist Audit Taktis

### Pre-Audit (Persiapan)
- [ ] Pastikan `market_paper.db` memiliki OHLCV lengkap (≥ 2 tahun history)
- [ ] Pastikan technical_indicators dan daily_risk_metrics sudah di-backfill
- [ ] Pastikan ML labels (triple-barrier) sudah computed
- [ ] Siapkan benchmark: IHSG (^JKSE) return untuk periode yang sama

### Audit Step 1: Performance Baseline
- [ ] Jalankan backtest skenario F (baseline teknikal) untuk periode walk-forward
- [ ] Jalankan backtest skenario A (full AI) untuk periode yang sama
- [ ] Hitung Sharpe, Sortino, MaxDD, Win Rate, Profit Factor untuk keduanya
- [ ] Hitung Alpha = R_A - R_F - biaya

### Audit Step 2: Ablation Per Komponen
- [ ] Jalankan skenario B-E (hapus 1 komponen pada satu waktu)
- [ ] Hitung Delta_X untuk setiap komponen
- [ ] Uji signifikansi statistik (paired t-test atau Diebold-Mariano)
- [ ] Identifikasi komponen dengan Delta ≤ 0

### Audit Step 3: Latency Profiling
- [ ] Instrument setiap komponen dengan `time.perf_counter()`
- [ ] Jalankan 100x untuk dapat median latency
- [ ] Bandingkan dengan target latency
- [ ] Identifikasi bottleneck

### Audit Step 4: Cost-Benefit
- [ ] Hitung biaya operasional per komponen (listrik GPU, API cost)
- [ ] Hitung revenue lift = Alpha × portfolio value × trade frequency
- [ ] Hitung break-even AUM
- [ ] Buat rekomendasi keep/hapus per komponen

### Audit Step 5: Feature Drift
- [ ] Ambil feature distribution dari training window
- [ ] Ambil feature distribution dari recent window (3 bulan terakhir)
- [ ] Hitung PSI per feature
- [ ] Identifikasi feature dengan PSI > 0.25
- [ ] Jalankan KS test untuk prediction distribution

### Audit Step 6: Regime Analysis
- [ ] Klasifikasikan setiap periode ke regime (bull/bear/sideways/crisis)
- [ ] Bandingkan model performance per regime
- [ ] Identifikasi regime di mana model gagal
- [ ] Evaluasi kebutuhan regime-aware model switching

### Audit Step 7: Final Report
- [ ] Lengkapi AI Utility Score Card
- [ ] Lengkapi Per-Komponen Verdict Matrix
- [ ] Buat rekomendasi: keep, optimize, simplify, atau remove
- [ ] Schedule re-audit (bulanan untuk swing, mingguan untuk day)

---

## 8. Referensi

### Akademik
- López de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley. — Bab 11-13: Backtesting, CV, Feature Importance
- López de Prado, M. (2019). *Trends in Quantitative Finance.* CFA Institute. — Deflated Sharpe Ratio
- Diebold, F.X. & Yilmaz, K. (2012). "Better to Give than to Receive." *International Journal of Forecasting.* — Variance decomposition
- Bailey, D. & López de Prado, M. (2012). "The Sharpe Ratio Efficient Frontier." *Journal of Risk.* — Probabilistic Sharpe Ratio

### Internal
- `pustaka/23-machine-learning-trading.md` — ML untuk trading
- `pustaka/29-backtesting-strategy-validation.md` — Backtest validation
- `pustaka/51-mlops-model-risk-management.md` — Model risk management
- `pustaka/71-eval-gated-promotion-ab-testing.md` — Eval-gated promotion
- `pustaka/85-backtest-to-live-gap-prevention.md` — Backtest to live gap
- `src/market/mlops/drift.py` — DriftDetector implementation
- `src/market/mlops/cross_validation.py` — WalkForwardCV, PurgedKFoldCV
- `src/market/mlops/promotion.py` — EvalGate, ABTestFramework

### Kode
- `scripts/audit_ai_utility.py` — Script audit dasar (Pilar 1-4: performance, ablation, latency, drift)
- `scripts/audit_ai_advanced.py` — Script audit lanjutan (feature remediation, delta alpha, significance tests, automated score card)
- `src/market/backtest/engine.py` — Event-driven backtest engine

---

## 9. Hasil Eksekusi Audit (7 Agustus 2026)

### 9.1 Feature Remediation

3 fitur drifted terdeteksi (PSI > 0.25): `vol_20`, `rsi`, `ma_ratio_50`. Remediasi:
- **8 replaced** dengan alternatif stabil (rsi_rank, vol_pctile, ma_ratio_zscore)
- **1 dropped** (ma_ratio_50 di TIRT.JK — tidak ada alternatif stabil)
- Teknik: regime-aware exponential weighting (half-life 126 hari, recent boost 2.0x)

### 9.2 Delta Alpha

| Component | ΔAlpha | ΔSharpe | Verdict |
|-----------|--------|---------|---------|
| MLSignal | 0.00% | +0.399 | MARGINAL (2.85/5.00) |
| MultiFactor | 0.00% | -2.271 | MARGINAL (2.37/5.00) |

### 9.3 Statistical Significance

| Test | MLSignal | MultiFactor |
|------|----------|-------------|
| Paired t-test | p=0.561 (NOT sig) | p=0.000 (sig, AI LEBIH BURUK) |
| Diebold-Mariano | p=0.001 (sig) | p=0.165 (NOT sig) |
| Bootstrap Reality Check | p=0.492 (NOT sig) | p=0.474 (NOT sig) |

### 9.4 Rekomendasi

1. **MLSignal**: Retrain dengan fitur remediated, kurangi walk-forward step size, tune signal threshold.
2. **MultiFactor**: Retrain dengan fitur remediated + exogenous global features, evaluasi ulang dengan lebih banyak ticker.
3. **Baseline teknikal** (MA crossover + RSI) juga merugi (Sharpe -0.40) — perlu strategi baseline yang lebih baik untuk perbandingan yang adil.

---

## 10. Update Status (10 Agustus 2026) — Post-Normalisasi & Modularisasi

### 10.1 Database Normalization

| Perubahan | Sebelum | Sesudah | Status |
|-----------|---------|---------|--------|
| technical_indicators | EAV (1 row per indicator) | `technical_indicators_wide` (1 row per date+ticker) | 3M+ rows, 0% NULL |
| stock_personality | Single table (profile + prediction) | Split: `stock_personality` (profile) + `stock_prediction` (prediction) | 1,020 rows di stock_prediction |
| FK declarations | Tidak ada | Migration `0012` menambah FK declarations | Applied |

### 10.2 Hyperparameter Anti-Overfit

**MLSignalProvider** (`src/market/analysis/ml_signal.py`):
- `min_data_in_leaf=40` — mencegah leaf dengan terlalu sedikit sample (anti-overfit)
- `reg_alpha=0.1` (L1) — sparse feature selection, mengurangi noise features
- `reg_lambda=1.0` (L2) — weight regularization
- `learning_rate=0.05` — lower LR = slower but more stable convergence
- `subsample=0.8`, `colsample_bytree=0.8` — row & column sampling untuk diversity

**MultiFactorModel** (`src/market/analysis/multi_factor.py`):
- `min_data_in_leaf=50` — lebih konservatif dari MLSignal (25+ features → butuh lebih banyak data per leaf)
- `reg_alpha=0.1`, `reg_lambda=1.0` — same regularization
- `subsample=0.8`, `colsample_bytree=0.8` — same sampling strategy
- `n_estimators=300` (diturunkan dari default ke 200 dengan early stopping 15)

**Parameter lain yang dapat di-tune untuk MARGINAL → KEEP:**
- `signal_threshold` (ReformConfig) — turunkan dari 0.1 ke 0.05 untuk lebih banyak sinyal
- `adapt_kappa` — kappa adaptif per ticker berdasarkan vol regime
- `meta_prob_threshold` — turunkan dari 0.5 ke 0.4 untuk lebih banyak trade pass meta-labeling
- `vol_aggressiveness` — naikkan dari 2.5 ke 3.0 untuk cut posisi volatil lebih cepat
- `horizon` — coba 3 (shorter) vs 5 (current) vs 10 (longer) untuk capture different regimes
- `n_estimators` — 100-200 dengan early stopping lebih agresif (5-10 rounds)

### 10.3 Walk-Forward CV Konsistensi

Sebelumnya `MLSignalProvider` dan `MultiFactorModel` masing-masing mengimplementasikan manual 80/20 split. Sekarang keduanya menggunakan `mlops/cross_validation.walk_forward_splits` untuk konsistensi dan reproducibility.

### 10.4 Stale Data Detection

`src/market/data/refresh_stale.py` — engine deteksi data usang (>24h) dengan auto-refresh:
- Tabel yang dimonitor: `stock_personality`, `stock_prediction`, `technical_indicators_wide`, `fundamental_data`, `recompute_watermark`, `data_watermark`
- Excluded: 139 tickers (suspended/delisting/inactive via `instrument_master`)
- CLI: `python -m market.data.refresh_stale --dry-run`

### 10.5 MLOps Integration

| Komponen | Lokasi | Fungsi |
|----------|--------|--------|
| ModelRegistry | `batch_compute_predictions.py` | Register model per ticker dengan `@experiment` alias |
| DriftDetector | `scripts/weekly_drift_check.py` | PSI-based feature drift, weekly cron (Saturday 04:00 UTC) |
| EvalGate | `fast_portfolio_pipeline.py` | Replaces hardcoded Score >= 3.5 dengan criteria-based evaluation |
| SignalEnhancer | `daily_signal_cron.py` | 5 non-trend signals (volume, policy, sector, pairs, meta-labeling) |

### 10.6 Pipeline Replacement

Pipeline lama 14-jam (`run_production_pipeline.sh`) **dihapus**. Pengganti: `fast_portfolio_pipeline.py` (~4-65 detik). Lihat `MEGAPLAN.md` untuk detail.

---

> Dibuat: 7 Agustus 2026 | Update: 10 Agustus 2026 | Dokumen: `pustaka/96-ai-ml-audit-framework.md` | Cross-ref: `23`, `29`, `51`, `71`, `85`, `97`
