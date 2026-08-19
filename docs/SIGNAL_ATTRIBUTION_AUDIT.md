# Audit Metodologi Pengujian & Signal Attribution Log

> **Hasil audit kritis berdasarkan riset internet profesional (Aug 2026). Mengidentifikasi kesalahan metodologi yang dapat menyebabkan signal_attribution_log menyimpan data salah.**

## 1. Kesalahan Metodologi yang Ditemukan

### 1.1 Look-Ahead Bias (KRITIS)

**Masalah:** Signal dihitung menggunakan close price hari ini, lalu diuji terhadap forward return mulai hari ini. Ini benar **jika** signal dihitung SEBELUM market close. Tapi jika signal menggunakan close price hari ini untuk memprediksi return mulai hari ini, itu adalah look-ahead bias — Anda tidak bisa trade pada close price yang baru tersedia setelah market tutup.

**Solusi:** Signal pada tanggal T menggunakan data sampai T-1 (atau T jika timeframe = EOD dan entry = T+1 open). Forward return dihitung dari T+1 open (atau T close jika signal tersedia sebelum close).

**Status aplikasi:** `compute_engine_signals` menggunakan `df` yang include data sampai `as_of_date` (close price T). Forward return dihitung dari close T ke close T+N. Ini **benar untuk EOD swing trading** — signal dihitung setelah close, entry di next day open. Tapi harus didokumentasikan dengan jelas.

### 1.2 API Call Mismatches (BUG)

**Masalah:** Backfill script memanggil engine dengan signature yang salah:

| Engine | Salah | Benar |
|--------|-------|-------|
| TechnicalAnalysisEngine | `.analyze(df)` | `.analyze(ticker, df)` |
| FundamentalAnalysisEngine | `.analyze(ticker, df)` | `.analyze(ticker)` |
| MacroEconomicEngine | `.analyze(df, ticker=ticker)` | `.analyze()` (no args, reads from DB) |
| SentimentEngine | `.analyze(df, ticker=ticker)` | `.analyze(ticker)` |
| Alpha engines | `.compute(df)` | `.generate_signals(close_series)` → returns Series, not scalar |
| VolumeFeatures | `VolumeFeatureCalculator().compute(df)` | `compute_ofi_proxy(df)`, `compute_vwap(df)` |
| PolicyEventScorer | `.load_events()` | `.load()` |
| SectorRotationEngine | `.compute_signal(df, ticker=ticker)` | `.recommend_sectors(prices=df)` |
| MLSignalProvider | `.compute(df, ticker=ticker)` | `.train_and_predict(ticker, df, as_of)` — **terlalu lambat untuk batch** |

**Dampak:** Engine yang dipanggil salah akan mengembalikan error (silently caught), sehingga signal_attribution_log hanya berisi engine yang kebetulan berhasil (astronacci saja). Ini **corrupt data** — log tidak merepresentasikan semua engine.

### 1.3 Alpha Signal Return Type Mismatch (BUG)

**Masalah:** `MeanReversionEngine.generate_signals()` mengembalikan `SignalResult(signal=pd.Series, confidence=pd.Series, metadata=dict)`. Bukan scalar. Script mencoba `float(result.signal)` yang akan fail atau mengambil nilai pertama dari Series, bukan nilai terakhir (yang relevan untuk tanggal T).

**Solusi:** Ambil `result.signal.iloc[-1]` untuk mendapatkan signal pada tanggal terakhir.

### 1.4 ML Engine Tidak Suitable untuk Batch (DESIGN)

**Masalah:** `MLSignalProvider.train_and_predict()` melatih model LSTM dari scratch untuk setiap ticker di setiap tanggal. Ini membutuhkan waktu menit per call. Untuk 250 hari × 6 ticker = 1500 calls, ini akan memakan waktu berjam-jam.

**Solusi:** Skip ML engine di batch backfill. ML engine harus di-run terpisah dengan model pre-trained, atau di-skip dari signal_attribution_log.

### 1.5 Tidak Ada Point-in-Time Discipline (WARNING)

**Masalah:** Fundamental data (P/E, P/B, ROE) diambil dari `fundamental_data` table yang mungkin berisi data yang sudah di-restated. Macro data (GDP, inflation) mungkin sudah di-revised. Ini adalah look-ahead bias untuk fundamental/macro signals.

**Solusi ideal:** Gunakan point-in-time database (menyimpan data sebagai yang dirilis pada tanggal T, bukan revised version). Untuk aplikasi personal, ini bisa di-mitigate dengan mencatat `as_of_date` dan hanya menggunakan data yang tersedia sebelum tanggal tersebut.

### 1.6 Directional Accuracy Tanpa IC (METHODOLOGY GAP)

**Masalah:** Backtest Astronacci sebelumnya hanya mengukur directional accuracy (UP/DOWN benar/salah). Ini tidak cukup. Riset profesional (AlphaEval 2025, crucible v0.3.1, MikaMirAI) menunjukkan bahwa:

- **Information Coefficient (IC)** = Spearman rank correlation antara signal dan forward return. IC > 0.03 sudah signifikan. IC > 0.15 suspicious (leakage).
- **Directional accuracy** 50% = random, 52-55% = signifikan, >58% = suspicious.
- **Rank IC** lebih robust dari directional accuracy karena tidak sensitif terhadap magnitude.

**Solusi:** signal_attribution_log harus menyimpan IC (Spearman correlation) selain directional accuracy.

### 1.7 Tidak Ada Multiple Comparison Correction (METHODOLOGY GAP)

**Masalah:** Kita menguji 14+ engine secara bersamaan. Semakin banyak engine diuji, semakin besar peluang salah satu terlihat bagus secara kebetulan. Harvey, Liu, dan Zhu (2016) menemukan bahwa dengan 316+ factor yang diuji, t-statistic threshold harus 3.0 (bukan 2.0).

**Solusi:** Terapkan Bonferroni correction: jika menguji N engine, significance threshold = 0.05/N. Atau gunakan Deflated Sharpe Ratio (Bailey & López de Prado 2014).

## 2. Modul yang Seharusnya Ada (Berdasarkan Riset)

Berdasarkan riset FactSet, Bloomberg MAC3, MeridianAlgo, dan ml4trading.io, modul profesional yang **belum ada** di aplikasi:

### 2.1 Yang SUDAH ada (32 engines)
- Technical, Fundamental, Macro, Sentiment, Relationship, Global
- Alpha (mean reversion, reversal, EWMA momentum, regime switch)
- Astronacci (astrology + Fibonacci confluence)
- Volume features, Policy event, Sector rotation, Pairs trading
- Meta labeling, News sentiment, Holiday effect, Market influence KB
- ML (LSTM), Walk-forward optimizer, DCC-GARCH
- Risk (Monte Carlo VaR, Capital-aware position sizer)
- Causal discovery, Cross-market coefficients, Instrument profiler

### 2.2 Yang BELUM ada (gap berdasarkan riset profesional)

| Modul | Deskripsi | Prioritas | Sumber |
|-------|-----------|-----------|--------|
| **Fama-French Factor Model** | 3-factor/5-factor model: market, size, value, profitability, investment | TINGGI | Fama & French (1992, 2015); toraniko; OpenFactor |
| **Brinson Attribution** | Decompose return: berapa dari asset allocation vs stock selection | TINGGI | Brinson et al. (1986); QuanterLab |
| **Order Flow Imbalance (OFI)** | VPIN, Kyle's lambda, depth metrics dari tick data | SEDANG | ml4trading.io; Kyle (1985) — *butuh tick data, tidak ada* |
| **Volatility Regime Detector** | GARCH/HMM untuk detect regime shift (volatility clustering) | SEDANG | MeridianAlgo; sudah ada DCC-GARCH tapi belum HMM regime |
| **Execution Algorithms** | VWAP, TWAP, POV, Implementation Shortfall | RENDAH | MeridianAlgo — *butuh order-level data, tidak ada* |
| **Black-Litterman** | Portfolio optimization dengan views | RENDAH | MeridianAlgo — *portfolio optimization, bukan signal* |
| **CPPI / Portfolio Insurance** | Drawdown protection | RENDAH | MeridianAlgo — *risk management, bukan signal* |

### 2.3 Yang Ada Tapi Perlu Diperbaiki

| Engine | Masalah | Fix |
|--------|---------|-----|
| Alpha engines | Return Series, bukan scalar | Ambil `.iloc[-1]` |
| Volume features | Wrong function names | `compute_ofi_proxy`, `compute_vwap` |
| PolicyEventScorer | `.load_events()` tidak ada | `.load()` |
| SectorRotation | Wrong API | `.recommend_sectors()` |
| ML | Terlalu lambat untuk batch | Skip di batch, run terpisah |
| Relationship | Butuh reference_returns dict | Skip di batch mode |
| Global | Butuh multi-asset data dict | Skip di batch mode |

## 3. Metodologi Pengujian yang Benar

Berdasarkan crucible v0.3.1, oos-lab, AlphaEval, dan walk-forward validation papers:

### 3.1 Untuk Setiap Engine, Ukur:

1. **Directional Accuracy** — % prediksi arah benar (UP/DOWN). Threshold: >55% signifikan, >58% suspicious.
2. **Information Coefficient (IC)** — Spearman rank correlation signal vs forward return. Threshold: >0.03 signifikan, >0.15 suspicious.
3. **IC Stability** — Std dev of daily IC. IC yang stabil (>0.03 dengan low variance) lebih reliable dari IC tinggi tapi volatile.
4. **Forward Return Spread** — Mean forward return saat signal bullish vs bearish. Selisih harus > 0 dan statistically significant (t-test).
5. **Sharpe Ratio (signal-weighted)** — Annualized Sharpe dari strategy yang weight berdasarkan signal.
6. **Deflated Sharpe** — Sharpe setelah dikoreksi untuk multiple testing (jumlah engine yang diuji).

### 3.2 Validasi:

1. **Walk-forward** — Bagi data menjadi rolling windows. Train di window 1, test di window 2, advance.
2. **Out-of-sample** — Jangan optimize parameter pada periode yang sama dengan evaluasi.
3. **Point-in-time** — Hanya gunakan data yang tersedia pada tanggal T.
4. **Transaction costs** — Model spread, commission, slippage. Untuk IDX: ~0.15% round trip (komisi 0.1% + spread 0.05%).

### 3.3 Keputusan Engine:

| Kriteria | Keputusan |
|----------|-----------|
| IC > 0.03, DirAcc > 53%, stable | **KEEP** — engine berkontribusi signal |
| IC ~ 0, DirAcc ~ 50% | **DROP** — engine tidak lebih baik dari random |
| IC < 0, DirAcc < 50% | **FIX** — engine mungkin salah arah (inverted signal) |
| IC > 0.15, DirAcc > 60% | **AUDIT** — suspicious, kemungkinan leakage |
| Engine gagal compute | **FIX API** — perbaiki pemanggilan |

## 4. Implementasi

### 4.1 Perbaikan signal_attribution_log

Tabel ditambah kolom IC:
- `ic_5d` — Spearman rank correlation signal vs fwd_return_5d (diisi saat batch analysis)
- Tidak perlu per-row, di-compute aggregate per engine

### 4.2 Pipeline yang Benar

```
Step 1: Untuk setiap (ticker, date), compute signal dari semua engine dengan API yang BENAR
Step 2: Simpan signal ke signal_attribution_log
Step 3: Setelah semua signal terisi, compute forward returns (1d, 3d, 5d, 10d)
Step 4: Compute directional accuracy per engine
Step 5: Compute IC (Spearman) per engine
Step 6: Apply multiple comparison correction (Bonferroni)
Step 7: Buat keputusan: keep/fix/drop per engine
```

## 5. Referensi

- Harvey, Liu, Zhu (2016) — "...and the Cross-Section of Expected Returns" — t-stat ≥ 3.0 untuk factor baru
- McLean & Pontiff (2016) — returns decline ~58% post-publication
- Bailey & López de Prado (2014) — Deflated Sharpe Ratio
- AlphaEval (2025) — 5-dimension evaluation: predictive power, stability, robustness, logic, diversity
- crucible v0.3.1 — edge validation: bootstrap CI, permutation p-value, walk-forward
- oos-lab — PBO/CSCV, Harvey-Liu haircut, PSR
- ml4trading.io — point-in-time discipline, IC, leakage detection
- MikaMirAI — Rank IC 0.05-0.15 = good, DirAcc >58% = suspicious
