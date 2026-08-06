# Ringkasan Pengetahuan: Data & ML Pipeline

> **Oret-oret catatan pengetahuan tentang arsitektur data & feature
> untuk pipeline ML pada aplikasi pasar modal.** Bukan backlog
> pekerjaan — hanya rangkuman apa yang ada, apa yang masih terbatas,
> dan bagaimana seluruh komponen menyatu menjadi feature matrix.
>
> **Sumber utama:**
> - `pustaka/94-aiml-knowledge-architecture-analysis.md` — audit 5 pilar arsitektur pengetahuan AI/ML
> - `pustaka/23-machine-learning-trading.md` — teori ML trading (labeling, walk-forward, regime, ensemble)
> - `pustaka/58-feature-store-engineering-pipeline.md` — feature store & feature engineering pipeline
> - `pustaka/84-new-data-arrival-processing-pipeline.md` — pipeline data arrival & labeling

---

## Daftar Isi

**Bagian 1: Arsitektur Data & Feature**
1. [5 Pilar Arsitektur Pengetahuan AI/ML](#5-pilar-arsitektur-pengetahuan-aiml)
2. [ML Feature Matrix (Target)](#ml-feature-matrix-target)
3. [Macro Indonesia Series Target](#macro-indonesia-series-target-macro_data)
4. [Status Kesiapan Komponen Data](#status-kesiapan-komponen-data)
5. [Audit Detail per Tabel](#audit-detail-per-tabel)
6. [Gap Pengetahuan Data](#gap-pengetahuan-data)

**Bagian 2: Teori ML & Pipeline**
7. [Triple-Barrier Labeling](#triple-barrier-labeling)
8. [Walk-Forward Optimization & Purged CV](#walk-forward-optimization--purged-cv)
9. [Regime Detection](#regime-detection)
10. [Recommended Model Stack (6-Layer)](#recommended-model-stack-6-layer)
11. [Feature Store Architecture](#feature-store-architecture)
12. [Incremental Recompute Architecture](#incremental-recompute-architecture)
13. [Anti-Overfitting Checklist](#anti-overfitting-checklist)

**Bagian 3: Quant Trading IDX**
14. [Pertimbangan Khusus IDX](#pertimbangan-khusus-idx)
15. [Backtesting Framework](#backtesting-framework)
16. [Backtest-to-Live Gap Prevention](#backtest-to-live-gap-prevention)
17. [Portfolio Construction & Position Sizing](#portfolio-construction--position-sizing)
18. [Risk Management Lanjutan](#risk-management-lanjutan)
19. [Market Microstructure IDX](#market-microstructure-idx)
20. [Execution & Slippage Modeling (TCA)](#execution--slippage-modeling-tca)
21. [Corporate Actions & Price Adjustment](#corporate-actions--price-adjustment)
22. [Tax & P&L Tracking](#tax--pl-tracking)
23. [Data Quality Framework](#data-quality-framework)
24. [Commodity-Linked Stocks IDX](#commodity-linked-stocks-idx)

**Bagian 4: Konteks Pasar Modal**
25. [Multi-Asset Cross-Market Analysis](#multi-asset-cross-market-analysis)
26. [Behavioral Finance & Bias](#behavioral-finance--bias)
27. [Regulatory IDX 2026](#regulatory-idx-2026)
28. [Performance Attribution & Benchmark](#performance-attribution--benchmark)
29. [LLM Agent Layer & Self-Evolving AI](#llm-agent-layer--self-evolving-ai)

**Bagian 5: Penutup**
30. [Deteksi Risiko Delisting (Secondary Label Source)](#deteksi-risiko-delisting-secondary-label-source)
31. [Roadmap Pengetahuan](#roadmap-pengetahuan)

---

## 5 Pilar Arsitektur Pengetahuan AI/ML

> Kerangka konseptual dari `pustaka/94` untuk menyusun pengetahuan
> data AI/ML. Setiap pilar = satu kelompok data + fungsi analitik
> yang harus tersedia sebelum model ML dapat ditraining dengan layak.

| Pilar | Fokus | Tabel Inti | Status |
|-------|-------|------------|--------|
| **1. Asset Mapping & Timing** | Bursa, instrumen, kalender, timezone | `market_registry`, `instrument_master`, `market_calendar`, `ohlcv` | ✅ IDX, ⚠️ global calendar |
| **2. Correlation & Intermarket** | Korelasi cross-asset multi-window | `relationship_matrix` | ✅ Multi-window (30/60/90/180/360) |
| **3. Price Driver Indicators** | Teknikal, fundamental, macro, flow | `technical_indicators`, `fundamental_data`, `macro_data`, `foreign_flow`, `scores` | 🟧 teknikal ✅, fundamental & macro terbatas |
| **4. Anomaly & Systemic Risk** | Suspensi, delisting, event, regime | `trading_suspensions`, `instrument_master`, `external_events`, `policy_events`, `fear_greed`, `market_regimes` | ✅ data ada, ⚠️ HMM belum |
| **5. Data Structuring for AI/ML** | Label, personality, pattern, feature store | `ml_labels`, `stock_personality`, `pattern_analysis`, `ai_weights` | ✅ label 9.85M rows, 🟧 feature store belum |

> **Inti:** Pilar 1–4 = data sources, Pilar 5 = struktur agar data
> siap ditraining. Tanpa Pilar 5 (label + feature store), data
> hanya bisa dipakai untuk analisis deskriptif, bukan prediktif.

---

## ML Feature Matrix (Target)

> Arsitektur target feature matrix yang menjadi acuan pengetahuan
> data ML. Setiap kelompok feature di bawah berasal dari satu atau
> lebih tabel sumber di database `market_research.db`.

**Time-aligned features per `(ticker, date)`:**

| Kelompok | Feature | Sumber / Tabel | Keterangan |
|----------|---------|----------------|------------|
| **Price** | OHLCV returns (1d, 5d, 21d), ATR, volatility regime | `ohlcv`, `technical_indicators` | Lengkap |
| **Technical** | RSI, MACD, ADX, BB position, MA cross signals | `technical_indicators` | Lengkap |
| **Flow** | Foreign net buy/sell (1d, 5d, 21d), broker concentration, volume anomaly | `foreign_flow`, `broker_flow` | `broker_flow` terbatas (1 ticker, 20 broker) |
| **Macro** | US10Y (DGS10), VIX, DXY, credit spread, BI Rate, ID CPI | `macro_data` | US lengkap, Indonesia belum |
| **Cross** | Corr to `^GSPC`/`^TNX`/`DXY`/`CL=F`/`GC=F` (multi-window) | `relationship_matrix` | Hanya window=60 |
| **Fund** | PE, PB, ROE, DER, earnings trend, balance sheet | `fundamental_data` | Snapshot only (1 baris/ticker) |
| **Sentiment** | Fear&Greed, news sentiment, policy event flag | `fear_greed`, `news_*`, `external_events`, `policy_events` | News sangat sedikit (~110) |
| **Pattern** | Trend label, volatility regime, pattern detected | `pattern_analysis` | 2.366 baris |
| **Personality** | Volatility regime, beta_vs_ihsg, liquidity_score (encoded) | `stock_personality` | 923 tickers, 22 fitur |
| **Risk** | Delisting risk score, board risk, volume_zero_streak | `instrument_master`, `trading_suspensions` | Risk score 0–95 + reason |
| **Regime** | Market regime (bull/bear/sideways/crisis) | `market_regimes` | Heuristic only (MA50/MA200 + vol) |

**Labels (target):**

- **Primary label:** Triple-barrier direction (`up`/`down`/`static`) @ horizon → tabel `ml_labels`.
- **Secondary label:** Delisting risk probability (0–1).

---

## Macro Indonesia Series Target (`macro_data`)

> Daftar series Indonesia yang menjadi target pengetahuan macro
> domestik (Pilar 3 dokumen 94). Berbeda dengan series US yang
> sudah terisi, series Indonesia sebagian besar masih perlu
> fetcher atau verifikasi kontinuitas.

| Series ID | Nama | Sumber | Keterangan |
|-----------|------|--------|------------|
| `BI_RATE` | Bank Indonesia 7-day reverse repo rate | FRED `INTDSBIDM193N` | Sudah di-fetch `scripts/fetch_macro_all.py`, perlu verifikasi kontinuitas |
| `ID_CPI` | Inflasi Indonesia YoY | FRED `IDNCPIALLMINMEI` | Sudah di-fetch, perlu verifikasi kontinuitas |
| `ID_GDP` | PDB Indonesia | FRED `NGDPRXDCID` | Sudah di-fetch, perlu verifikasi kontinuitas |
| `ID_TRADE_BALANCE` | Neraca perdagangan | BPS / FRED | Belum ada fetcher |
| `ID_CURRENT_ACCOUNT` | Neraca jasa berjalan | BPS / FRED | Belum ada fetcher |
| `ID_10Y_BOND` | Yield obligasi pemerintah Indonesia 10 tahun | Bloomberg / investing.com / BI API | Belum ada fetcher |

---

## Status Kesiapan Komponen Data

> Audit kesiapan tiap komponen sumber feature untuk `ml_feature_matrix`.
> Lihat juga `pustaka/94-aiml-knowledge-architecture-analysis.md`
> untuk detail baris & coverage.

| Komponen | Tabel | Kesiapan | Catatan |
|----------|-------|----------|---------|
| Price history (OHLCV) | `ohlcv` | ✅ Siap | 3M baris, 1.008 tickers, 1997–2026 |
| Technical features | `technical_indicators` | ✅ Siap | 29.5M baris, 10 indikator |
| Cross-asset correlation | `relationship_matrix` | ✅ Siap | Multi-window (30/60/90/180/360), 63.072 baris |
| Foreign flow signal | `foreign_flow` | ✅ Siap | 178K baris, 983 tickers |
| Pattern labels | `pattern_analysis` | ⚠️ Terbatas | 2.366 baris, perlu lebih banyak pola |
| Stock personality | `stock_personality` | ✅ Siap | 985 tickers dengan 22 fitur |
| Multi-factor scores | `scores` | ✅ Siap | 6 engine × 980 tickers = 5.880 baris |
| ML labels (triple-barrier) | `ml_labels` | ✅ Siap | 9.853.286 baris, 4 horizon (1/5/10/21), 986 tickers |
| Suspension history | `trading_suspensions` | ✅ Siap | 64 records dengan reason |
| Macro signals (US) | `macro_data` | ⚠️ Terbatas | Hanya US, beberapa series hampir kosong |
| FX rates | `fx_rates` | ⚠️ Terbatas | Hanya 3 pair, EUR/JPY hanya 518 baris |
| Fear & Greed | `fear_greed` | ✅ Siap | 1.178 baris daily (2021–2026) |
| External/Policy events | `external_events`, `policy_events` | ⚠️ Terbatas | 119+179 baris, perlu lebih banyak |

> **Komponen ⚠️ Terbatas** = area yang perlu diperluas sebelum
> feature matrix dianggap viable untuk training ML.

---

## Audit Detail per Tabel

> Breakdown baris & distribusi per tabel sumber feature.
> Dipakai untuk verifikasi coverage data.

### `trading_suspensions` (64 baris)

| Klasifikasi Reason | Jumlah | Contoh Ticker |
|--------------------|--------|---------------|
| Suspensi > 6 bulan | 28 | SUGI, GOLL, KBRI, TRIL, HOME, OCAP, MABA, NIPS, SIMA, SKYB, dll |
| Kelangsungan usaha | 12 | PLAS, BTEL, SCPI, ARMY, COWL, SRIL, WSKT |
| Pailit / PKPU | 10 | MAMI, FORZ, MYRX, KRAH, KPAS, KPAL, NIPS, JKSW |
| Suspensi 24 bulan | 5 | TRIO, CPRI, GAMA, HKMU |
| Kasus Jiwasraya | 5 | MYRX, TRAM, RIMO, PRAS |
| Voluntary delisting (go private) | 4 | TURI, RMBA, MASA, CNTB/CNTX |
| Merger | 4 | JPRS, FREN, MFIN |

### `stock_personality` (985 tickers)

| Label | Jumlah |
|-------|--------|
| Active Trader | ~390 |
| Balanced Stock | ~355 |
| Volatile Speculator | ~145 |
| Illiquid Stock | ~20 |
| Momentum Stock | ~10 |
| Declining Stock | ~8 |
| Defensive / Balanced | ~5 |

### `pattern_analysis` (2.366 baris)

| Pattern | Jumlah |
|---------|--------|
| Volatility: moderate/high/low | 923 |
| Trend: Sideways/Uptrend/Downtrend | 923 |
| Bollinger Breakout | 98 |
| RSI Overbought/Oversold | 156 |
| Volume Spike | 94 |
| Resistance Breakout / Support Breakdown | 85 |
| MACD Crossover (Bull/Bear) | 57 |
| Golden Cross / Death Cross | 25 |
| GAP_PATTERN | 5 |

### `technical_indicators` (9.783 baris — latest snapshot)

> **Catatan:** Setelah recompute Aug 2026, `technical_indicators`
> hanya menyimpan snapshot terbaru per ticker (bukan historical
> 29.5M rows seperti migrasi awal). 10 indikator × ~978 tickers.

| Indicator | Baris | Tickers |
|-----------|-------|---------|
| MA20 | ~978 | 978 |
| MA50 | ~978 | 978 |
| RSI | ~978 | 978 |
| MACD | ~978 | 978 |
| MACD_SIGNAL | ~978 | 978 |
| ADX | ~978 | 978 |
| ATR14 | ~978 | 978 |
| BB_UPPER / BB_LOWER | ~978 | 978 |
| VOLUME_SMA20 | ~978 | 978 |

### `ml_labels` (9.853.286 baris — triple-barrier, recomputed Aug 2026)

| Direction | Jumlah | Persentase |
|-----------|--------|------------|
| static (time_expired) | 5.975.893 | 60.6% |
| up (take_profit) | 2.025.892 | 20.6% |
| down (stop_loss) | 1.851.501 | 18.8% |

| Horizon | Jumlah |
|----------|--------|
| h=1 | 2.470.241 |
| h=5 | 2.466.907 |
| h=10 | 2.462.736 |
| h=21 | 2.453.402 |

> **Catatan:** Distribusi seimbang antar horizon. Dominasi `static`
> (60.6%) wajar karena barrier ±2×ATR cukup lebar untuk saham
> less volatile. 0 NULL values pada `return_pct` dan `direction`.
> Dedup index OHLCV diterapkan sebelum labeling untuk mencegah
> `UNIQUE constraint` violation.

### Sentimen & Alternative Data

| Tabel | Baris | Keterangan |
|-------|-------|------------|
| `news` | 110 | Headline, body, sentiment score, impact — sangat sedikit |
| `fear_greed` | 1.178 | Daily Fear & Greed index (2021–2026) |
| `foreign_flow` | 178.201 | Foreign buy/sell/net per ticker per hari |
| `broker_flow` | 15.830 | Hanya 1 ticker, 20 broker — terbatas |
| `scores` | 5.880 | 6 engine × 980 tickers (technical, sentiment, relationship, macro, global, fundamental) |

### `fundamental_data` (1.007 baris)

| Field | Ketersediaan | Catatan |
|-------|--------------|---------|
| `pe`, `pb`, `roe`, `der`, `eps` | ✓ | Rasio valuasi standar |
| `revenue`, `net_income`, `total_assets` | ✓ | Data laporan keuangan |
| `market_cap`, `book_value_per_share` | ✓ | Market data |
| `total_liabilities`, `cash_flow` | ✓ | Balance sheet items |
| `fiscal_year`, `quarter` | ✓ | Period identification |
| `dividend_yield` | ✓ | Yield data |

> **Catatan:** Semua field tersedia, tapi hanya 1 baris per ticker
> (snapshot) — tren finansial per quarter tidak tertangkap.

### `external_events` (119 baris) & `policy_events` (179 baris)

| Kategori External | Jumlah | Rentang |
|-------------------|--------|---------|
| Konflik Geopolitik | 62 | 2005–2026 |
| Perang | 18 | 2007–2025 |
| Bencana Alam | 16 | 2005–2025 |
| Pandemi | 12 | 2009–2025 |
| Perubahan Iklim | 6 | 2024–2025 |
| ESG | 5 | 2024–2025 |

| Kategori Policy | Jumlah | Rentang |
|-----------------|--------|---------|
| Moneter | 110 | 2005–2025 |
| Regulasi OJK | 23 | 2006–2025 |
| Regulasi BEI | 21 | 2006–2025 |
| Fiskal | 16 | 2005–2025 |
| Politik | 9 | 2007–2025 |

### `macro_data` (10.036 baris, 14 series)

| Series | Sumber | Baris | Rentang | Kategori |
|--------|--------|-------|---------|----------|
| DGS10 | FRED | 2.498 | 2016–2026 | Yield 10Y US |
| T10Y2Y | FRED | 2.499 | 2016–2026 | Yield spread 10Y-2Y |
| VIXCLS | FRED | 2.544 | 2016–2026 | Volatility |
| BAMLH0A0HYM2 | FRED | 787 | 2023–2026 | Credit spread (high yield) |
| `fed_funds_rate` | yfinance | 1.255 | 2021–2026 | Interest rate (daily) |
| FEDFUNDS | FRED | 120 | 2016–2026 | Interest rate (monthly) |
| CPIAUCSL | FRED | 118 | 2016–2026 | Inflation (CPI) |
| UNRATE | FRED | 119 | 2016–2026 | Unemployment |
| USALOLITONOSTSAM | FRED | 91 | 2016–2024 | Leading index |
| DXY, GOLD, OIL, US10Y, USD_IDR | yfinance | 1 each | 2026 saja | **Hampir kosong** |

> **Catatan:** 5 series yfinance (DXY, GOLD, OIL, US10Y, USD_IDR)
> hanya 1 baris (2026 saja) — series praktis kosong, perlu
> re-fetch full history.

---

## Gap Pengetahuan Data

> Daftar gap data yang teridentifikasi dari audit di atas.
> Dirangkum untuk konteks pengetahuan, bukan tracking pekerjaan.

| # | Gap | Dampak |
|---|-----|--------|
| G1 | `broker_flow` hanya 1 ticker dengan 20 broker (15.830 baris) — sangat terbatas | Tidak dapat menganalisis broker concentration secara luas |
| G2 | Tidak ada tabel `portfolio_flow` (mutual fund / reksa dana flow data) | Institutional flow dari manajer investasi tidak tertangkap — blind spot aliran dana domestik |
| G3 | Tidak ada data bond yield Indonesia (`INDOGB` / `ID_10Y_BOND`) — hanya US yields di `macro_data` | Yield curve domestik tidak tertangkap → credit cycle Indonesia blind |
| G4 | ✅ TERATASI: `relationship_matrix` sekarang multi-window (30/60/90/180/360), 63.072 baris | Korelasi stabil vs transient dapat dibedakan |
| G5 | `fundamental_data` hanya 1 baris per ticker (snapshot) | Tren kerusakan finansial per quarter tidak dapat dilihat |
| G6 | `news` hanya 110 baris | Sentiment model tidak viable dengan 110 sample |
| G7 | Tidak ada tabel `financial_report_submission` | Keterlambatan laporan keuangan tidak dapat di-track terstruktur |
| G8 | 5 series yfinance macro (DXY, GOLD, OIL, US10Y, USD_IDR) hanya 1 baris | Series praktis kosong, tidak dapat dipakai untuk feature macro |
| G9 | `market_regimes` hanya heuristic (MA50/MA200 + vol) — HMM belum diimplementasi | Regime-aware prediction terbatas pada rule-based |
| G10 | `market_calendar` hanya IDX — bursa global belum punya kalender | Trading day awareness untuk AI global terbatas |

---

## Deteksi Risiko Delisting (Secondary Label Source)

> Rincian feature & sumber data untuk menghitung **delisting risk
> probability (0–1)** — secondary label pada `ml_feature_matrix`.
> Dikelompokkan per kategori risiko sesuai audit database.

### A. Risiko Finansial (Ekuitas Negatif, Gagal Bayar)

| Feature / Signal | Sumber | Catatan |
|------------------|--------|---------|
| `der > 3` (Debt-to-Equity Ratio tinggi) | `fundamental_data.der` | Threshold konservatif IDX |
| `total_liabilities > total_assets` (ekuitas negatif) | `fundamental_data` | Sinyal insolvensi |
| `net_income < 0` sustained (rugi berkelanjutan) | `fundamental_data.net_income` | Perlu multi-quarter |
| `cash_flow < 0` (arus kas negatif) | `fundamental_data.cash_flow` | Burn rate tinggi |

> **Gap:** Data fundamental hanya 1 baris per saham — tidak dapat
> melihat tren kerusakan finansial (lihat G5 di atas).

### B. Risiko Legal/Kepatuhan (Terlambat Laporan Keuangan)

| Feature / Signal | Sumber | Catatan |
|------------------|--------|---------|
| Suspensi > 6 bulan (tidak lapor keuangan) | `trading_suspensions.reason LIKE '%Suspensi >6 bulan%'` | Indikasi kuat non-compliance |
| Kasus Jiwasraya / kasus legal | `trading_suspensions.reason LIKE '%Kasus Jiwasraya%'` | Kasus legal/kepatuhan serius |

> **Gap:** Tidak ada tabel `financial_report_submission` untuk track
> keterlambatan laporan keuangan secara terstruktur (lihat G7).

### C. Risiko Likuiditas & Manipulasi Pasar

| Feature / Signal | Sumber | Catatan |
|------------------|--------|---------|
| Board = 'Pemantauan Khusus' | `instrument_master.board` | Sinyal kuat risiko |
| `value = 0` sustained (tidak diperdagangkan) | `daily_trading_stats.value` | Likuiditas nol |
| `volume = 0` sustained > 6 bulan | `ohlcv.volume` | **Early warning paling kuat** — 30 saham dengan skor 95 |
| `personality_label = 'Illiquid Stock'` | `stock_personality` | 19 saham |
| `personality_label = 'Declining Stock'` | `stock_personality` | 8 saham |

> **Catatan:** Kategori C sudah punya data siap (`instrument_master`,
> `daily_trading_stats`, `ohlcv`, `stock_personality` — semua ✅ Siap
> di tabel Status Kesiapan). Hanya perlu script agregasi untuk
> hitung sustained-zero window & gabung ke delisting risk score.

---

## Triple-Barrier Labeling

> Metode labeling utama untuk ML training (López de Prado, *Advances
> in Financial Machine Learning*). Berbeda dari fixed-horizon
> labeling yang hanya melihat return di hari ke-N, triple-barrier
> mensimulasikan posisi trading nyata dengan TP/SL/timeout.

### Konsep

Tiga barrier yang membungkus pergerakan harga sejak entry:

```
                    ┌─ Upper barrier (Take Profit)  → label = +1
                    │
   Entry price ────┤
                    │
                    └─ Lower barrier (Stop Loss)    → label = -1

   Vertical barrier (max holding period) → label =  0 (timeout)
```

- **Upper barrier (TP):** harga naik ≥ threshold → label `+1` (up)
- **Lower barrier (SL):** harga turun ≤ threshold → label `-1` (down)
- **Vertical barrier:** tidak kena TP/SL dalam horizon → label `0` (static)

### Implementasi aktual (`recompute_ml_labels`)

Sumber: `pustaka/94 §3.2`, `src/market/data/recompute_internal.py`

| Parameter | Nilai | Catatan |
|-----------|-------|---------|
| Horizon | 1, 5, 10, 21 hari | 4 horizon paralel — day trading sampai monthly |
| Upper barrier (TP) | +2 × ATR14 | Volatility-adjusted, bukan fixed % |
| Lower barrier (SL) | -2 × ATR14 | Simetris dengan TP |
| Vertical barrier | horizon hari | Timeout = max holding period |
| Logic | First-barrier-hit | Barrier pertama yang tersentuh menentukan label |
| Output | `vol_adjusted_return` | Return dinormalisasi ATR untuk cross-ticker comparability |

**Tabel target:** `ml_labels` — kolom `(ticker, date, horizon, direction, barrier_hit, return_pct, vol_adjusted_return)`.

### Mengapa ATR-based, bukan fixed %

| Pendekatan | Kelemahan | Keunggulan ATR-based |
|------------|----------|----------------------|
| Fixed % (mis. ±2%) | Saham volatile jarang kena TP/SL; saham illiquid over-trigger | Barrier menyesuaikan volatilitas tiap ticker |
| | Tidak akomodasi regime (bull/bear vol berbeda) | Bull market → ATR besar → barrier lebar → label `0` lebih jarang |
| | Cross-ticker comparability rendah | `vol_adjusted_return` memungkinkan model belajar cross-ticker |

### Meta-Labeling (Roadmap)

Secondary model yang memprediksi **precision** primary model — bukan
arah. Output: `1` (trade) atau `0` (skip). Tujuan: filter sinyal
low-confidence dari primary model.

```
Primary model  → direction (up/down/static)
                     ↓
Meta-labeler   → confidence (0–1)
                     ↓
Final signal   → trade only if confidence > threshold
```

> Sumber: `pustaka/23 §7.3`. Belum diimplementasi — roadmap
> pengetahuan, lihat section [Roadmap Pengetahuan](#roadmap-pengetahuan).

---

## Walk-Forward Optimization & Purged CV

> Metode validasi untuk time-series ML. Standard K-fold CV tidak
> valid untuk data finansial karena: (1) shuffle → look-ahead bias,
> (2) train/test overlap → inflated metrics, (3) autocorrelation →
> information leakage.

### Walk-Forward Optimization (WFO)

Simulasi trading realistis dengan rolling window:

```
Time →
Train: [======]          [======]          [======]
Test:          [==]              [==]              [==]
               ↑                 ↑                 ↑
               Prediksi 1        Prediksi 2        Prediksi 3
```

| Parameter | Nilai tipikal | Catatan |
|-----------|---------------|---------|
| `train_window` | 252 hari (1 tahun) | Cukup untuk menangkap 1 cycle |
| `test_window` | 21 hari (1 bulan) | Out-of-sample per bulan |
| Model | Fresh setiap window | Tidak carry-over state |

### Purged Walk-Forward

Variasi WFO dengan **purge gap** antara train dan test untuk
mengurangi autocorrelation bias:

```
Train: [======]
                    ← purge gap (5 hari) →
                                          Test: [==]
```

- Train berakhir `purge_window` hari sebelum test dimulai
- Tujuan: label horizon N hari masih "bocor" ke test set jika
  tidak ada gap (label di hari t menggunakan return t+1..t+N)

### Purged K-Fold (López de Prado)

Generalisasi purge untuk K-fold cross-validation:

| Masalah Standard K-Fold | Solusi Purged K-Fold |
|--------------------------|----------------------|
| Shuffle → look-ahead | Chronological split, no shuffle |
| Train/test overlap | Purge gap di kedua sisi test fold |
| Autocorrelation leakage | Purge window ≥ max horizon label |

> Sumber: `pustaka/23 §5` (WFO) & §9 (Purged K-Fold).
> Implementasi referensi: `src/trading_system/ai_learning/walk_forward.py`,
> `src/trading_system/ai_learning/purged_tss.py`.

---

## Regime Detection

> Market regime menentukan strategi efektif. Model ML yang
> regime-aware dapat menggunakan weight berbeda per regime —
> meningkatkan robustness signifikan vs model single-regime.

### 4 Regime Utama

| Regime | Karakteristik | Strategi Efektif |
|--------|---------------|------------------|
| **Bull** | Trend naik, vol rendah, momentum kuat | Trend-following, momentum |
| **Bear** | Trend turun, vol tinggi, drawdown | Mean reversion, defensive, cash |
| **Sideways** | Range-bound, vol sedang | Range trading, low conviction |
| **Crisis** | Sell-off tajam, vol ekstrem | Cash, hedging, risk-off |

### Implementasi aktual (heuristic)

Sumber: `pustaka/94 §3.2`, `recompute_market_regimes`

Regime harian dihitung dari kombinasi:

| Signal | Sumber | Kontribusi |
|--------|--------|------------|
| MA50/MA200 crossover | `ohlcv` IHSG | Bull (MA50 > MA200) / Bear (MA50 < MA200) |
| Volatilitas | `technical_indicators.ATR14` | Crisis jika vol ekstrem |
| VIX | `macro_data.VIXCLS` | Risk-off jika VIX > threshold |
| Fear & Greed | `fear_greed` | Sentimen pasar |
| Foreign flow trend | `foreign_flow` | Akumulasi/distribusi asing |

**Tabel target:** `market_regimes` — kolom `(date, regime, vix_level, fear_greed_label, foreign_flow_trend)`.

### HMM-based Detection (Teori → Roadmap)

Hidden Markov Model dengan `n_components=3-4` pada IHSG returns:

| Komponen | Output |
|----------|--------|
| State 0 | Bear (mean return negatif) |
| State 1 | Sideways (mean return ~0) |
| State 2 | Bull (mean return positif) |
| State 3 (opsional) | Crisis (mean return sangat negatif, vol ekstrem) |

Library: `hmmlearn.GaussianHMM` dengan `covariance_type="full"`,
`n_iter=100`. Scaling: `StandardScaler` sebelum fit.

> **GPU note:** HMM fitting berbasis EM iteratif — untuk dataset
> IDX (~2.9M baris OHLCV) tidak butuh GPU, CPU cukup. GPU `cuda:1`
> baru relevan jika pakai neural HMM (PyTorch) atau dataset multi-
# juta baris per ticker.
> Sumber: `pustaka/23 §6`. Implementasi referensi:
> `src/trading_system/analysis/enhanced_regime.py`.

### Regime-Aware Weight Adjustment

Setiap regime punya bobot feature berbeda — model regime-aware
mengoptimalkan weight per regime:

| Regime | Technical | Fundamental | Macro | Global | Relationship | Sentiment |
|--------|-----------|-------------|-------|--------|--------------|-----------|
| Bull | 0.35 | 0.20 | 0.15 | 0.15 | 0.10 | 0.05 |
| Bear | 0.20 | 0.25 | 0.25 | 0.15 | 0.10 | 0.05 |
| Sideways | 0.25 | 0.25 | 0.15 | 0.10 | 0.15 | 0.10 |
| Crisis | 0.15 | 0.20 | 0.30 | 0.20 | 0.05 | 0.10 |

> Sumber: `pustaka/23 §6.3` (RegimeAwareStrategy).

---

## Recommended Model Stack (6-Layer)

> Arsitektur ML berlapis untuk IDX, dari `pustaka/23 §12.2`.
> Setiap layer menerima output layer sebelumnya — bukan model
# tunggal monolitik.

```
Layer 1: Regime Detection (HMM)
    ↓ regime label (bull/bear/sideways/crisis)
Layer 2: Factor Weight Optimization (Ridge Regression)
    ↓ optimized weights per regime
Layer 3: Return Prediction (Gradient Boosting — LightGBM)
    ↓ expected return per ticker
Layer 4: Direction Classification (Random Forest)
    ↓ buy/sell/hold signal
Layer 5: Meta-Labeling (Logistic Regression)
    ↓ confidence filter (trade/skip)
Layer 6: Ensemble (Weighted average)
    ↓ final signal + confidence
```

| Layer | Model | Input | Output | Status Implementasi |
|-------|-------|-------|--------|---------------------|
| 1 | HMM (`hmmlearn`) | IHSG returns | regime label | 🟧 heuristic only, HMM TODO |
| 2 | Ridge Regression | regime + features | weight per factor | ✅ `ai_learning/weight_optimizer.py` |
| 3 | LightGBM | feature matrix | expected return | ✅ `ml_signal.py` (walk-forward CV) |
| 4 | Random Forest | feature matrix | direction (1/-1/0) | ✅ `ai_learning/` |
| 5 | Logistic Regression | primary signal + features | confidence (0–1) | ⬜ TODO (meta-labeling) |
| 6 | Weighted Ensemble | all model outputs | final signal | ✅ `ai_learning/ensemble.py` |

| **Catatan:** Layer 3 (`ml_signal.py`) sudah ada dengan walk-forward
> CV, dan **triple-barrier labels sudah di-populate** (9.853.286
> rows di `ml_labels`, recomputed Aug 2026). Label siap untuk
> training model ML.

---

## Feature Store Architecture

> Centralized feature definitions, computation, dan serving.
> Tanpa feature store, feature dihitung di banyak tempat dengan
> kode berbeda → training/serving skew, sulit di-reuse, sulit
> di-version. Sumber: `pustaka/58`.

### Problem vs Solution

| Tanpa Feature Store | Dengan Feature Store |
|---------------------|----------------------|
| RSI_14 dihitung di 3 tempat berbeda dengan kode berbeda | RSI_14 didefinisikan sekali, digunakan di mana-mana |
| Feature definition tidak terdokumentasi | Setiap feature punya definisi, range, dtype |
| Tidak tahu feature stale atau fresh | Freshness monitoring per feature |
| Training/serving skew | Same computation for training dan serving |
| Feature baru sulit di-reuse | Catalog: cari feature, gunakan langsung |

### Arsitektur

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

### Feature Definition Format (YAML)

```yaml
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

### Computation Order (Pipeline Stages)

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

### Feature Catalog (Excerpt)

| Feature | Category | Range | Used By |
|---------|----------|-------|---------|
| `rsi_14` | technical | 0–100 | LSTM, Screener, Pattern, Decision |
| `macd_histogram` | technical | unbounded | LSTM, Pattern |
| `bb_position` | technical | 0–1 | LSTM, Screener |
| `atr_14` | technical | > 0 | LSTM, Risk (SL/TP) |
| `foreign_net_buy` | flow | unbounded | Sentiment, Prediction |
| `fear_greed_index` | sentiment | 0–100 | Sentiment, Decision |
| `bi_rate` | macro | 0–20 | Macro, Regime |
| `vix` | global | 0–100 | Global, Regime |
| `roe` | fundamental | -100 to 100 | Fundamental, Screener |
| `beta_market` | relationship | -3 to 5 | Risk, Portfolio |
| `regime_label` | regime | string | Decision, Weights |
| `var_95` | risk | > 0 | Risk, Portfolio |

> **Status:** Teori lengkap di `pustaka/58`, tapi **belum ada
> implementasi kode** — feature masih tersebar di `technical_indicators`,
> `scores`, `relationship_matrix`, `macro_data` tanpa versioning
> terpusat. Lihat [Roadmap Pengetahuan](#roadmap-pengetahuan).

---

## Incremental Recompute Architecture

> Sistem recompute pipeline mendukung dua mode: **full** (DELETE + recompute
> all) dan **incremental** (append hanya tanggal baru). Implementasi di
> `src/market/data/recompute_internal.py`, `src/market/pipelines/recompute.py`,
> `src/market/scheduler_tasks.py`, dan `src/market/api/routes_recompute.py`.
>
> **Sumber:** `pustaka/84-new-data-arrival-processing-pipeline.md`

### Motivasi

Sebelum incremental, setiap recompute harian (18:00 WIB) melakukan
`DELETE FROM <table>` + insert ulang seluruh data. Untuk `ml_labels`
(9.85M rows), ini butuh **~56 menit**. Padahal data baru per hari hanya
~986 tickers × 4 horizon = ~3.944 rows baru. Full recompute sangat
tidak efisien untuk daily pipeline.

### Strategi per Tabel

| Tabel | Tipe | Strategi | Waktu Full | Waktu Incremental |
|-------|------|----------|-----------|-------------------|
| `technical_indicators` | Snapshot | Full (latest only, ~9K rows) | ~10s | ~10s (sama) |
| `scores` | Snapshot | Full (latest only, ~6K rows) | ~15s | ~15s (sama) |
| `relationship_matrix` | Snapshot | Full (latest corr, ~63K rows) | ~3min | ~3min (sama) |
| `fear_greed` | Time-series | **Append new dates** | ~5s | <1s |
| `stock_personality` | Snapshot | Full (latest profile, ~985 rows) | ~5s | ~5s (sama) |
| `ml_labels` | Time-series | **Append + recompute last 21d** | ~56min | **<2min** |
| `market_regimes` | Time-series | **Append new dates** | ~5s | <1s |

> **Snapshot tables** selalu full recompute karena hanya menyimpan nilai
> terbaru per ticker. Tidak ada konsep "tanggal baru" — setiap recompute
> mengganti snapshot lama dengan yang baru. Waktu eksekusi sudah cepat.

### Incremental ml_labels — Algoritma

`ml_labels` adalah tabel terberat (9.85M rows). Algoritma incremental:

1. Cari `MAX(date)` di `ml_labels` → `last_date`
2. Hitung `cutoff = last_date - 21 hari` (max horizon)
3. `DELETE FROM ml_labels WHERE date > cutoff` — hapus label 21 hari
   terakhir karena barrier (TP/SL) bisa berubah dengan data baru
4. Untuk setiap ticker, cari first index di OHLCV dimana
   `date > cutoff` → `start_i`
5. Generate label dari `start_i` sampai akhir data

> **Kenapa hapus 21 hari terakhir?** Label untuk date D butuh data
> sampai D + horizon (max 21). Jika data baru masuk, label untuk
> tanggal dalam 21 hari terakhir bisa berubah (barrier baru terhitung).
> Jadi harus dihapus dan dihitung ulang.

### Event Flow

```
Scheduler (18:00 WIB)
  ↓
_task_recompute()
  ↓ emit "data.recompute.requested" {incremental: True}
  ↓
RecomputePipeline.on_recompute_requested()
  ↓ run_all_recompute(session, incremental=True)
  ↓
  ├─ technical_indicators  → full recompute (snapshot)
  ├─ scores                → full recompute (snapshot)
  ├─ relationship_matrix   → full recompute (snapshot)
  ├─ fear_greed            → append new dates only
  ├─ stock_personality     → full recompute (snapshot)
  ├─ ml_labels             → delete last 21d + append
  └─ market_regimes        → append new dates only
  ↓
emit "data.recompute.completed" {incremental: True}
```

### Mode Selection

| Trigger | Mode | Alasan |
|---------|------|--------|
| Scheduler harian (18:00 WIB) | `incremental` | Data baru hanya 1 hari |
| Startup catch-up | `incremental` | Backfill data terlewat |
| Dashboard manual (default) | `incremental` | Aman untuk daily use |
| Dashboard manual (pilih Full) | `full` | Setelah schema change / data cleanup |

### Dashboard UI

Dashboard recompute (`/recompute`) memiliki toggle button:
- **Incremental** (default, hijau) — hanya append tanggal baru
- **Full** (merah) — DELETE all + recompute, ~56 menit

Warning message context-aware:
- Full mode: peringatan hapus semua data, estimasi 56 menit
- Incremental mode: info append only, estimasi < 2 menit

### Idempotency

- **Full:** `DELETE FROM <table>` + INSERT ulang. Idempotent.
- **Incremental:** `DELETE WHERE date > cutoff` + INSERT. Idempotent
  karena label untuk date yang sama akan dihapus dulu sebelum di-insert
  ulang. Jalankan 2x → hasil sama.
- **Startup catch-up:** Fetch skip ticker yang data-nya masih fresh
  (< 26 jam). Recompute incremental hanya append yang baru. Export
  incremental hybrid (hanya partition yang berubah).

### File yang Dimodifikasi

- `src/market/data/recompute_internal.py` — parameter `incremental` di
  semua 7 fungsi + `run_all_recompute`
- `src/market/pipelines/recompute.py` — baca `incremental` dari event
  payload, pass ke `run_all_recompute`
- `src/market/scheduler_tasks.py` — `_task_recompute` dan
  `_task_startup_catchup` emit `incremental: True`
- `src/market/api/routes_recompute.py` — WebSocket accept `?mode=`
  query param, dashboard UI mode selector

---

## Anti-Overfitting Checklist

> Pitfall umum ML untuk trading & solusinya. Sumber: `pustaka/23 §11`.

### Common Pitfalls

| Pitfall | Deskripsi | Solusi |
|---------|-----------|--------|
| **Look-ahead bias** | Menggunakan data future di feature | Hanya gunakan data ≤ prediction date |
| **Survivorship bias** | Hanya saham yang masih listed | Include delisted stocks |
| **Overfitting** | Model terlalu kompleks | Regularization, simpler model |
| **Data snooping** | Test banyak hypothesis pada same data | Multiple testing correction |
| **Leakage in CV** | Train/test overlap | Purged K-fold |
| **Hyperparameter overfit** | Tuning pada test set | Nested CV |

### Checklist Verifikasi

- [ ] **No look-ahead:** Semua feature hanya menggunakan data yang available at prediction time
- [ ] **Chronological split:** Train sebelum test, no shuffle
- [ ] **Purged CV:** Gap antara train dan test folds
- [ ] **Walk-forward:** Out-of-sample validation dengan rolling window
- [ ] **Multiple metrics:** Tidak hanya optimize satu metric
- [ ] **Feature stability:** Feature distribution tidak drift signifikan
- [ ] **Model simplicity:** Prefer simpler model jika performansi mirip
- [ ] **Out-of-sample test:** Data yang belum pernah dilihat model
- [ ] **Monte Carlo:** Test robustness dengan random perturbation
- [ ] **Paper trading:** Forward test sebelum live

---

## Pertimbangan Khusus IDX

> Faktor-faktor spesifik pasar Indonesia yang mempengaruhi desain
> ML pipeline. Sumber: `pustaka/23 §12.1`.

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **Data terbatas** | ~3M rows OHLCV, 1.008 tickers, 986 aktif untuk labeling | Transfer learning, simpler models |
| **Fundamental sulit** | Data `.JK` terbatas di Yahoo Finance | Skip fundamental jika perlu, fokus teknikal |
| **Korelasi tinggi** | Saham IDX bergerak bersama (IHSG-driven) | Cross-sectional features, HRP |
| **Regime jelas** | Bull/bear cycles IDX kuat | HMM regime detection wajib |
| **Suspend/delisting** | Saham hilang tiba-tiba | Filter `is_active`, survivorship handling |
| **Thin volume** | Banyak saham illiquid (19 saham "Illiquid Stock") | Volume filter, liquidity features |

### IDX-Specific Feature Notes

- **Commodity-to-stock mapping** — integrasi `pustaka/91` ke
  relationship matrix: CPO → AALI/LSNG, coal → PTBA/ITMG, tin → TINS,
  nickel → INCO/ANTM. Saat ini belum terintegrasi di `relationship_matrix`.
- **Auto-reject & tick size** — fitur IDX-specific yang tidak ada
  di pasar global. Lihat section [Market Microstructure IDX](#market-microstructure-idx).
- **Foreign flow dominance** — foreign flow adalah sentiment
  indicator terkuat di IDX (konvensi: net buy = bullish). Lihat
  `pustaka/30-sentiment-analysis-alternative-data.md §5`.

---

## Backtesting Framework

> Prinsip & parameter backtesting untuk validasi strategi quant.
> Sumber: `pustaka/29-backtesting-strategy-validation.md`,
> `pustaka/85-backtest-to-live-gap-prevention.md`.

### Prinsip Backtesting

| Prinsip | Deskripsi |
|---------|-----------|
| **No look-ahead** | Hanya gunakan info available saat keputusan dibuat |
| **Realistic costs** | Broker fee, spread, slippage, PPh — bukan zero-cost |
| **Survivorship inclusion** | Include delisted/suspended stocks, bukan hanya yang masih listed |
| **Out-of-sample test** | Data yang belum pernah dilihat model |
| **Multiple regimes** | Test across bull/bear/sideways/crisis |
| **Statistical rigor** | Sharpe, Sortino, win rate, profit factor, statistical tests |

### Vectorized vs Event-Driven

| Mode | Kecepatan | Akurasi | Use Case |
|------|-----------|---------|----------|
| **Vectorized** | Cepat | Rendah (no partial fills) | Signal research, parameter sweep |
| **Event-Driven** | Lambat | Tinggi (partial fills, latency) | Production simulation, final validation |

### Parameter Backtest IDX

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| Position size per trade | 10% | Default vectorized backtest |
| Broker fee | 0.15–0.25% | Fee broker IDX |
| Levy + BEI fee | ~0.035% | Levy 0.025% + BEI 0.01% |
| PPh final | 0.1% | Pajak penjualan saham (dari bruto) |
| Slippage (realistis) | 0.15–0.50% | Bukan 0.05% — sesuai realitas IDX |
| Slippage (blue chip) | 0.05–0.15% | BBCA, TLKM, BBRI |
| Slippage (small-cap) | 0.30–0.50% | Likuiditas rendah |
| Minimum lot | 100 shares | Lot size IDX |
| Out-of-sample ratio | 20–30% | Portion data untuk testing |
| Walk-forward window | 2–3 thn in-sample, 6–12 bln out-of-sample | Rolling window |
| Monte Carlo iterations | 1000+ | Jumlah simulasi minimum |
| Sharpe ratio threshold | > 1.0 (good), > 1.5 (live minimum) | Dianggap viable |
| Maximum drawdown | 20–30% (toleransi), < 20% (live minimum) | Batas toleransi |
| Minimum trades | 30–50 | Untuk statistical significance |

### Regime IDX untuk Backtest

| Periode | Regime | Event |
|---------|--------|-------|
| 2016–2018 | Bull | Jokowi pro-growth, commodity recovery |
| 2018–2019 | Bear | Trade war US-China, rupiah weakening |
| Mar 2020 | Crisis | COVID crash (-37% IHSG) |
| 2020–2022 | Bull | Recovery, commodity supercycle |
| 2023–2024 | Sideways | Rate hike cycle, election uncertainty |
| 2025–2026 | Bull? | Reformasi PPK, free float 15% |

> **Catatan:** Backtest wajib test across multiple regime — strategi
> yang hanya bagus di bull market akan gagal di bear/crisis.

---

## Backtest-to-Live Gap Prevention

> Backtest selalu overestimate live performance — gap ini wajib
> dipahami & dimitigasi. Sumber: `pustaka/85`.

### Degradasi Tipikal Backtest → Live

| Metric | Backtest | Live (typical) | Degradasi |
|--------|----------|----------------|-----------|
| Win rate | 65–80% | 40–55% | -20 to -30% |
| Sharpe ratio | 1.5–3.0 | 0.3–1.0 | -50 to -70% |
| Max drawdown | -5% to -15% | -15% to -35% | 2–3× worse |
| Return p.a. | +30–50% | -10% to +15% | -60 to -130% |
| Slippage | 0.05% | 0.15–0.50% | 3–10× worse |

### 7 Root Causes

| # | Root Cause | Impact | Mitigasi |
|---|------------|--------|----------|
| 1 | Look-ahead bias | Overstated return 5–15% | Next-bar-open execution |
| 2 | Survivorship bias | Overstated return 10–30% | Include delisted stocks |
| 3 | Unrealistic costs | Overstated return 5–20% | Total cost ~0.354% + slippage 0.15–0.50% |
| 4 | Overfitting | Backtest bagus, live gagal | Walk-forward + purged CV |
| 5 | Market impact | Slippage real > model | Liquidity-aware slippage model |
| 6 | Regime change | Parameter tidak generalisasi | Regime-aware testing |
| 7 | Behavioral gap | Hesitation, override signal | Automated execution |

### Next-Bar-Open Execution

```
Sinyal di bar t  →  eksekusi di open bar t+1

❌ Salah: sinyal di bar t, eksekusi di close bar t (look-ahead)
✅ Benar:  sinyal di bar t, eksekusi di open bar t+1 (realistis)
```

> **Catatan:** Gap 1 bar ini menghilangkan look-ahead bias tapi
> menambah slippage (open price bisa gap dari close). Trade-off
> ini wajib — realistis > optimistis.

---

## Portfolio Construction & Position Sizing

> Output ML → portfolio. Teori portfolio optimization & implementasi
> untuk IDX. Sumber: `pustaka/21-portfolio-optimization-construction.md`.

### Metode Optimization

| Metode | Keunggulan | Kelemahan | Cocok untuk |
|--------|------------|-----------|-------------|
| **Mean-Variance (MVO)** | Klasik, optimal risk-return | Sensitif terhadap estimasi return | Bull market, estimasi return reliable |
| **Min Variance** | Tidak perlu estimasi return | Bisa underperform di bull | Defensive, bear market |
| **Max Sharpe** | Optimal risk-adjusted return | Sensitif terhadap Rf & return | Balanced market |
| **Black-Litterman** | Gabung market equilibrium + views | Butuh views yang baik | Active manager dengan views |
| **HRP** | Robust, clustering-based | Tidak optimal secara klasik | N > T, korelasi tidak stabil |
| **Risk Parity** | Equal risk contribution | Bisa over-weight volatile assets | Long-term, diversified |

### Parameter Portfolio IDX

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| Risk-free rate (Rf) | 5–7% | SBN 10-year Indonesia (default Sharpe) |
| Risk aversion (λ) | 2–4 | Quadratic utility |
| Max single position | 10–20% | Batas koncentrasi |
| Max sector exposure | 30–40% | Batas eksposur sektor |
| Min position size | 0.5–1% | Terlalu kecil = tidak impact |
| Max concurrent positions | 15–20 | Manajemen capacity |
| Min assets | 10–15 | Diversifikasi minimum |
| Max assets | 30–50 | Manajemen capacity |
| Target volatility | 15–20% annualized | Swing trading portfolio |
| Rebalancing | Monthly/Quarterly | Swing trading frequency |
| Shrinkage intensity | 0.1–0.5 | Ledoit-Wolf covariance |
| Correlation threshold | > 0.7 | Clustering HRP |
| Liquidity filter | ADV > Rp 1–5 miliar | Minimum tradable |

### Constraint IDX

- **Long-only** — IDX tidak mengizinkan short selling bebas. MVO
  wajib constraint `w_i ≥ 0`.
- **Sektor koncentrasi** — IDX didominasi Finance (~25%), Consumer,
  Infrastructure. Sector caps wajib.
- **Likuiditas** — hanya saham dengan ADV > Rp 1–5 miliar yang layak
  untuk quant portfolio (top 20–30 saham = >60% volume IDX).

### Position Sizing Methods

| Metode | Formula | Use Case |
|--------|---------|----------|
| **Fixed fractional** | Risk 1–2% capital per trade | Simple, default |
| **Volatility-adjusted (ATR)** | Position = (Risk% × Capital) / (ATR × multiplier) | IDX — vol tinggi |
| **Equal risk contribution** | Position ∝ 1/volatility | Risk parity |
| **Kelly Criterion** | f* = (bp - q) / b | Optimal jika win rate known |
| **Fractional Kelly** | 0.25–0.50 × f* | Konservatif, mengurangi drawdown |

> **Kelly formula:** `f* = (b×p - q) / b`, di mana `b` = win/loss
> ratio, `p` = win rate, `q` = loss rate. Full Kelly terlalu
> agresif → gunakan fractional Kelly 25–50%.

---

## Risk Management Lanjutan

> Layered risk management untuk quant trading. Sumber:
> `pustaka/07-manajemen-risiko.md`, `pustaka/31-risk-management-lanjutan.md`.

### 4 Layer Risk Management

| Layer | Scope | Tools |
|-------|-------|-------|
| **Position** | Per trade | Stop-loss, take-profit, time stop |
| **Portfolio** | Per portfolio | VaR, CVaR, max drawdown, correlation |
| **System** | Per day/session | Daily loss limit, circuit breaker |
| **External** | Market level | Regime detection, macro risk, stress test |

### Stop Loss Strategies

| Strategi | Parameter | Keunggulan | Kelemahan |
|----------|-----------|------------|-----------|
| Fixed percentage | 5–10% | Simple | Tidak akomodasi vol |
| ATR-based | 2–3× ATR14 | Volatility-adjusted | Bisa lebar di volatile market |
| Support-based | Di bawah support | Technical | Subjective |
| Moving average | Di bawah MA20/MA50 | Trend-following | Lag |
| Trailing stop | 2–3× ATR from high | Lock profit | Bisa whipsaw |
| Time stop | 20–30 bars | Exit jika stagnan | Bisa exit sebelum breakout |

### VaR & CVaR

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| VaR confidence | 95–99% | Standar industri |
| VaR holding period | 1–10 hari | Swing: 5–10 hari |
| CVaR multiplier | 1.5–2.0× VaR | Tail risk buffer |
| VaR warning | 80% utilization | Reduce position |
| VaR breach | 100% utilization | Action required |
| Daily loss limit | 3–5% portfolio | Circuit breaker |
| Stress test scenarios | 5–10 | Crisis simulation |

### Stress Test Scenarios IDX

| Scenario | Trigger | Impact IHSG |
|----------|---------|-------------|
| COVID crash | Pandemi | -37% (Mar 2020) |
| 2015 crash | Rupiah crisis | -12% (Aug 2015) |
| 2008 GFC | Global financial crisis | -47% (Oct 2007–Oct 2008) |
| Rate hike | BI rate +200bps | -5 to -10% |
| Commodity crash | Coal/CPO -30% | -10 to -15% (energy heavy) |
| Foreign exodus | Foreign sell Rp 5T+ | -5 to -8% |

### Drawdown Management

| Trigger | Action |
|---------|--------|
| Drawdown > 10% | Reduce position size 50% |
| Drawdown > 20% | Halt new entry, exit weak positions |
| Drawdown > 30% | Full stop, review strategy |
| Recovery > 6 bulan | Strategy retirement candidate |

> **Catatan IDX:** Saham IDX highly correlated ke IHSG →
> correlation-based sizing wajib. Jika korelasi > 0.7 antar posisi,
> reduce aggregate size.

---

## Market Microstructure IDX

> Aturan mekanisme perdagangan IDX yang impact execution & signal.
> Sumber: `pustaka/24-market-microstructure-likuiditas.md`,
> `pustaka/76-idx-trading-rules-market-mechanics.md`.

### Sesi Perdagangan IDX (WIB)

| Sesi | Waktu | Aktivitas |
|------|-------|-----------|
| Pre-opening | 08:45–08:59 | Order collection |
| Sesi 1 | 09:00–11:30 | Regular trading |
| Lunch break | 11:30–13:30 | Pause (Jumat: 11:30–13:00) |
| Sesi 2 | 13:30–14:49 | Regular trading (Jumat: 14:00–14:49) |
| Pre-closing | 14:50–15:00 | Closing collection |
| Closing | 15:00 | Matching closing |
| Post-trade | 15:00–16:00 | Post-trade processing |

> **Catatan Jumat:** Sesi 1 09:00–11:30, break 11:30–13:30, Sesi 2
> 14:00–14:49 (lebih pendek karena Jumat prayer time).

### Fraksi Harga (Tick Size)

| Range Harga (Rp) | Tick Size (Rp) |
|-------------------|-----------------|
| < 200 | 1 |
| 200 – 500 | 2 |
| 500 – 2.000 | 5 |
| 2.000 – 5.000 | 10 |
| 5.000 – 10.000 | 25 |
| > 10.000 | 50 |

> **Impact:** Order harus dibulatkan ke tick size. Slippage minimum
> = 1 tick. Untuk saham < Rp 200, 1 tick = Rp 1 = bisa 0.5%+ slippage.

### Auto-Reject (ARA/ARB)

| Range Harga (Rp) | ARA (lower) | ARB (upper) | Range |
|-------------------|-------------|-------------|-------|
| < 200 | -25% | +25% | ±25% |
| 200 – 5.000 | -20% | +20% | ±20% |
| > 5.000 | -15% | +15% | ±15% |

> **Impact:** Tidak bisa place order di luar batas ARA/ARB.
> Stop-loss yang terlalu jauh bisa tidak tereksekusi jika harga
> gap langsung ke auto-reject. **Reformasi 2026:** usulan auto-reject
> berjenjang (35%/25%/20% per range) — lihat section
> [Regulatory IDX 2026](#regulatory-idx-2026).

### Circuit Breaker

| Trigger | Action |
|---------|--------|
| IHSG turun > 10% dalam 1 sesi | Halt trading 30 menit |
| IHSG turun > 15% | Halt trading 1 jam |
| IHSG turun > 20% | Halt trading sampai akhir hari |

### Bid-Ask Spread per Tier

| Tier | Spread (pts) | Contoh | Slippage Estimasi |
|------|--------------|--------|-------------------|
| Blue chip | 5–25 | BBCA, TLKM, BBRI | 0.05–0.15% |
| Mid-cap | 10–100 | ANTM, INCO, MEDC | 0.10–0.25% |
| Small-cap | 50–500 | Banyak saham IDX | 0.20–0.40% |
| Gorengan | 100–1000+ | Saham illiquid | 0.30–0.50%+ |

> **Catatan:** Data Level 2 (order book) IDX tidak publik. Estimasi
> spread dari OHLCV menggunakan Corwin-Schultz atau Roll estimator.

### Liquidity Filter untuk Quant

| Kategori | Daily Value | Max Order | Max % ADV |
|----------|-------------|-----------|-----------|
| Highly Liquid | > Rp 100B | Rp 5B | 5% |
| Liquid | Rp 50–100B | Rp 2.5B | 5% |
| Moderately Liquid | Rp 10–50B | Rp 500M | 5% |
| Illiquid | < Rp 10B | Rp 100M | 1% |

> **Quant universe IDX:** fokus top 20–30 saham (highly liquid +
> liquid) yang menyumbang >60% volume IDX. Illiquid stocks =
> slippage tinggi, market impact signifikan.

---

## Execution & Slippage Modeling (TCA)

> Transaction Cost Analysis untuk evaluasi kualitas eksekusi.
> Sumber: `pustaka/52-transaction-cost-analysis-execution-quality.md`.

### Komponen Biaya Transaksi

| Komponen | Nilai | Keterangan |
|----------|-------|------------|
| Broker fee | 0.15–0.25% | Variabel per broker |
| Levy IDX | 0.025% | Levy bursa |
| BEI fee | ~0.01% | Fee BEI |
| PPh final | 0.1% | Pajak penjualan (dari bruto) |
| **Total fee (sell)** | **~0.354%** | Broker + levy + BEI + PPh |
| Slippage | 0.15–0.50% | Tergantung likuiditas |
| **Total cost (sell)** | **~0.5–0.85%** | Fee + slippage |
| **Round-trip cost** | **~0.7–1.2%** | Buy + sell (fee + slippage) |

> **Threshold profitabilitas:** strategi harus menghasilkan return
> > 0.7% per round-trip untuk cover biaya transaksi saja.

### Market Impact Model

```
Market Impact = k × √(Order Size / Daily Volume)

k = 0.1 (koefisien IDX)
```

| Order Size vs Daily Vol | Impact | Kategori |
|-------------------------|--------|----------|
| < 1% | < 0.02% | Safe |
| 1–5% | 0.02–0.05% | Minimal |
| 5–10% | 0.05–0.10% | Noticeable |
| 10–20% | 0.10–0.20% | Significant |
| > 20% | > 0.20% | High — avoid |

### Benchmark Eksekusi

| Benchmark | Formula | Use Case |
|-----------|---------|----------|
| **VWAP** | Volume-weighted avg price hari itu | Intraday execution quality |
| **TWAP** | Time-weighted avg price | Simple benchmark |
| **Arrival Price** | Harga saat order dibuat | Total cost decision → execution |
| **Previous Close** | Close hari sebelumnya | Next-day execution |
| **Open Price** | Open hari eksekusi | Next-bar-open execution |

### Implementation Shortfall

```
IS = (Return teoritis) - (Return actual)
   = Slippage + Fee + Market Impact + Timing Cost
```

| Komponen | Target | Alert |
|----------|--------|-------|
| Implementation Shortfall | < 0.5% | > 1.0% |
| VWAP Slippage | < 0.2% | > 0.5% |
| Arrival Price Slippage | < 0.15% | > 0.4% |
| Market Impact | < 0.05% | > 0.2% |
| Timing Cost | < 0.3% | > 0.7% |

---

## Corporate Actions & Price Adjustment

> Corporate actions mempengaruhi harga, jumlah lembar, cost basis.
> Wajib untuk OHLCV adjustment & backtest. Sumber:
> `pustaka/75-corporate-actions-processing-adjustment.md`.

### Impact per Corporate Action

| Corporate Action | Harga | Jumlah Lembar | Cost Basis | Pajak |
|------------------|-------|---------------|------------|-------|
| Stock Split | ÷ ratio | × ratio | ÷ ratio | Tidak kena |
| Reverse Split | × ratio | ÷ ratio | × ratio | Tidak kena |
| Stock Dividend | ÷ (1+ratio) | × (1+ratio) | ÷ (1+ratio) | Tidak kena |
| Cash Dividend | Turun ~dividend | Tidak berubah | Berkurang dividend | PPh 10% |
| Bonus Share | ÷ (1+ratio) | × (1+ratio) | ÷ (1+ratio) | Tidak kena |
| Rights Issue | Disesuaikan ke TERP | Tidak berubah* | Tidak berubah* | Tidak kena |

*Jika tidak exercise rights. Jika exercise, jumlah & cost basis berubah.

### Timeline IDX

| Event | Timing | Keterangan |
|-------|--------|------------|
| BEI announcement | Min 10 hari bursa sebelum ex-date | Pengumuman corporate action |
| Cum date | Ex-date - 1 trading day | Hari terakhir dengan hak |
| Ex-date | Record date - 2 trading days | Hari pertama tanpa hak (T+2 settlement) |
| Record date | Ex-date + 2 trading days | Penentuan pemegang hak |
| Payment date | Bervariasi (1–4 minggu) | Pembayaran dividend |

### TERP (Theoretical Ex-Rights Price)

```
TERP = (existing_shares × market_price + new_shares × rights_price) / total_shares
```

### Relevansi untuk Backtest

- **Adjusted price wajib** — technical indicator (MA, RSI, MACD)
  harus dihitung dari adjusted close, bukan raw close. Saham yang
  sering split/dividen (BBCA, TLKM, UNVR) akan distorsi indikator
  jika tidak di-adjust.
- **Ex-date awareness** — hindari entry tepat sebelum ex-date
  dividend (harga turun ~dividend). Atau gunakan sebagai strategi
  dividend capture dengan perhitungan PPh 10%.
- **Cost basis tracking** — penting untuk perhitungan PPh final
  0.1% dan pelaporan SPT.

---

## Tax & P&L Tracking

> Pajak & akuntansi trading saham untuk single-user. Sumber:
> `pustaka/25-pajak-akuntansi-trading.md`.

### Pajak Trading Saham IDX

| Jenis Pajak | Tarif | Basis | Pemungut | Sifat |
|-------------|-------|-------|----------|-------|
| PPh Penjualan Saham | 0.1% | Nilai jual bruto | Broker | Final |
| PPh Dividen | 10% | Nilai dividen | Emiten | Final |
| Dividen Bebas Pajak | 0% | Jika diinvestasikan kembali | — | PP 9/2021 |
| PPh Saham Pendiri (IPO) | 0.5% | Nilai pasar saat IPO | Penjamin emisi | Pilihan |

### Syarat Dividen Bebas Pajak (PP 9/2021)

- Penerima: Wajib Pajak orang pribadi
- Investasi kembali: di Indonesia
- Jangka waktu: minimal **2 tahun** (saham), 1 tahun (obligasi)
- Instrumen: saham, obligasi, reksa dana, UMKM

### Cost Basis Tracking

| Metode | Deskripsi | Use Case |
|--------|-----------|----------|
| **FIFO** | First-in, first-out | Default, sesuai praktik umum |
| **Average** | Weighted average cost | Sederhana, cocok untuk single-user |
| **Specific ID** | Pilih lot spesifik | Tax optimization |

### Pelaporan SPT

| SPT | Deadline | Penghasilan |
|-----|----------|-------------|
| SPT OP (1770/1770-S) | 31 Maret tahun berikutnya | Dividen + capital gain saham |
| SPT Badan (1771) | 30 April tahun berikutnya | (Tidak relevan untuk personal) |

> **Catatan:** Dividen dan capital gain saham bursa dilaporkan di
> **Daftar Penghasilan Final** — bukan penghasilan biasa.

### Total Biaya Transaksi (Cost Model)

```
Buy:  Broker fee 0.15–0.25% + Levy 0.025% + BEI 0.01% = ~0.19–0.29%
Sell: Broker fee 0.15–0.25% + Levy 0.025% + BEI 0.01% + PPh 0.1% = ~0.29–0.39%
Round-trip: ~0.48–0.68% (fee saja, belum termasuk slippage)
```

> **Threshold profitabilitas:** strategi swing harus menghasilkan
> return > 0.7% per round-trip untuk cover fee + slippage.

---

## Data Quality Framework

> Framework kualitas data untuk pipeline integrity. Sumber:
> `pustaka/22-data-engineering-pipeline.md`, `pustaka/53-data-governance-lineage.md`.

### Data Quality Dimensions

| Dimension | Threshold | Check |
|-----------|-----------|-------|
| **Completeness** | > 95% | Missing data < 5% |
| **Freshness** | < 24 jam (EOD) | Last update timestamp |
| **Accuracy** | Range check | OHLCV: high ≥ open/close ≥ low, volume ≥ 0 |
| **Consistency** | Cross-table | Ticker di OHLCV harus ada di instrument_master |
| **Timeliness** | SLA per source | yfinance EOD: < 24 jam, FRED: < 7 hari |
| **Uniqueness** | No duplicate | (ticker, date) unique di OHLCV |

### Sumber Data & Rate Limit

| Sumber | Rate Limit | Frekuensi | Delay | Kualitas |
|--------|------------|-----------|-------|----------|
| Yahoo Finance | 1 req/sec | Daily (EOD) | 10 menit untuk IDX | Medium |
| IDX.co.id | 0.3 req/sec | Daily | Real-time | High |
| FRED | 120 req/min | Daily | — | High |
| BPS | — | Monthly/Quarterly | — | High |
| Bank Indonesia | — | Daily/Monthly | — | High |
| RSS Feeds | — | Real-time | — | Medium |

### Ingestion Pattern

| Parameter | Nilai |
|-----------|-------|
| Max retries | 3 |
| Retry delay | 5 sec (exponential backoff) |
| Idempotent | Ya (re-run tidak duplikasi) |
| Fail-fast | Error di ingest → stop |

### Storage Strategy

| Tier | Storage | Retensi | Use Case |
|------|---------|---------|----------|
| Hot | SQLite | 30 hari terakhir | Real-time query, dashboard |
| Warm | Parquet | 1 tahun terakhir | Backtesting, analysis |
| Cold | Parquet compressed | > 1 tahun | Archive, audit |

### Outlier Detection

| Metode | Threshold | Use Case |
|--------|-----------|----------|
| Z-score | > 3σ dari mean | Return ekstrem |
| IQR | > 1.5×IQR dari Q1/Q3 | Volume anomaly |
| Range check | high < low → error | Data error |
| Gap check | |open - prev_close| > 20% | Suspicious gap |

---

## Commodity-Linked Stocks IDX

> ~35–40% market cap IDX dipengaruhi langsung oleh harga komoditas.
> Sumber: `pustaka/91-komoditas-spesifik-idx.md`.

### Mapping Komoditas → Emiten

| Komoditas | Ticker Yfinance | Emiten Produsen | Emiten Konsumer |
|-----------|-----------------|-----------------|-----------------|
| CPO | `FCPO=F` | AALI, LSIP, SIMP, DSNG | INDF, ICBP, MYOR |
| Batubara | `NEWC=F` | PTBA, ITMG, ADRO, HRUM, BYAN | — |
| Nikel | LME | INCO, ANTM, MDKA | — |
| Tembaga | `HG=F` | ANTM, MDKA | — |
| Emas | `GC=F` | ANTM, MDKA | — |
| Crude Oil | `CL=F` / `BZ=F` | MEDC, ENRG, BULL, AKRA | — |

### Time Lag Komoditas → Saham

| Komoditas | Lag | Keterangan |
|-----------|-----|------------|
| CPO | 1–3 hari | Transmission cepat untuk AALI/LSIP |
| Batubara | 1–5 hari | Lag lebih panjang, tergantung contract |
| Nikel | 1–3 hari | LME price → emiten |
| Tembaga | 1–3 hari | LME price → emiten |
| Emas | 0–2 hari | Transmission cepat |
| Crude Oil | 1–3 hari | Brent/WTI → energy stocks |

### Signal Threshold

| Signal | Threshold | Impact |
|--------|-----------|--------|
| CPO naik > 10% / bulan | Bullish | Produsen sawit (AALI, LSIP) |
| CPO turun > 10% / bulan | Bearish produsen, bullish konsumer | INDF, ICBP |
| Batubara naik > 15% / bulan | Bullish | PTBA, ITMG, ADRO |
| Crude oil naik > 20% / bulan | Bullish | MEDC, ENRG |

### Sektor Weight IHSG

| Sektor | Bobot IHSG | Komoditas Driver | Emiten Kunci |
|--------|-----------|------------------|--------------|
| Energi | ~18% | Batubara, crude oil | ADRO, PTBA, ITMG, MEDC |
| Material | ~12% | CPO, nikel, tembaga, emas | AALI, INCO, ANTM, MDKA |
| Konsumer Primer | ~8% | CPO (sawit) | LSIP, SIMP, DSNG |
| Keuangan | ~25% | (tidak langsung) | BBCA, BBRI, BMRI |

> **Feature untuk ML:** tambahkan perubahan harga komoditas
> (1–5 hari lag) sebagai feature di swing trading model untuk
> saham komoditas. Saat ini belum terintegrasi di `relationship_matrix`.

---

## Multi-Asset Cross-Market Analysis

> Intermarket relationships & spillover effects. Sumber:
> `pustaka/35-multi-asset-cross-market-analysis.md`.

### Intermarket Chain (IDX)

```
US Bonds ↑ → US Dollar ↑ → EM Currencies ↓ (IDR) → IDX ↓
Commodity ↑ → Commodity Exporters ↑ → IDX (Energy) ↑
S&P 500 ↑ → Risk-on → Foreign inflow IDX → IDX ↑
VIX ↑ → Risk-off → Foreign outflow IDX → IDX ↓
```

### Correlation Classification

| Korelasi | Range | Interpretasi |
|----------|-------|--------------|
| Tinggi | > 0.7 | Bergerak bersama |
| Sedang | 0.3 – 0.7 | Berkorelasi moderat |
| Rendah | -0.3 – 0.3 | Tidak berkorelasi |
| Negatif | ≤ -0.3 | Bergerak berlawanan |

### Lead-Lag Relationships

| Leading Asset | Lagging Asset | Lag (hari) | Konfidensi |
|---------------|---------------|------------|------------|
| S&P 500 | IHSG | 1–2 | Tinggi |
| US 10Y yield | IDR/USD | 0–1 | Sedang |
| DXY | IDR/USD | 0–1 | Tinggi |
| Crude oil | Energy stocks IDX | 1–3 | Sedang |
| China SHCOMP | IDX commodity stocks | 1–2 | Sedang |

### Parameter Cross-Market

| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| Rolling correlation window | 60 hari | Default (perlu multi-window) |
| Cross-correlation max lag | 20 hari | Lead-lag detection |
| Granger causality p-value | < 0.05 | Threshold signifikansi |
| Clustering threshold | 0.6 | Hierarchical clustering |
| DCC-GARCH span | 60 | Exponentially weighted |

> **Relevansi ML:** S&P 500 leads IDX 1–2 hari → feature lagged
> S&P 500 return untuk prediksi IHSG. Saat korelasi IDX-global naik,
> diversifikasi kurang efektif → reduce position size.

---

## Behavioral Finance & Bias

> Bias kognitif & emosional yang mempengaruhi trading decision.
> Relevan untuk single-user quant — mitigasi bias dengan automation.
> Sumber: `pustaka/09-behavioral-finance.md`.

### Cognitive Biases

| Bias | Deskripsi | Mitigasi |
|------|-----------|----------|
| **Conservatism** | Lambat update belief | Data-driven signal, retrain berkala |
| **Confirmation** | Cari info yang mendukung | Pre-defined exit rules |
| **Anchoring** | Tergantung info pertama | Dynamic price target |
| **Availability** | Overweight info recent | Walk-forward, long-term backtest |

### Emotional Biases

| Bias | Parameter | Mitigasi |
|------|-----------|----------|
| **Loss aversion** | Loss terasa 2–2.5× lebih sakit | Pre-defined stop-loss otomatis |
| **Overconfidence** | Turnover > 200% = overtrading | Max trades per hari/week |
| **Disposition effect** | Sell winners too early, hold losers | Automated exit rules |
| **Herding** | Ikut market sentiment extreme | Contrarian signal dari Fear&Greed |

### Prospect Theory

```
Value(x) = x^α            if x ≥ 0  (gain)
         = -λ × (-x)^β    if x < 0  (loss)

λ (loss aversion) = 2.0–2.5
α, β (diminishing sensitivity) = 0.88
γ (probability weighting) = 0.65
```

> **Relevansi quant:** Implementasi pre-defined exit rules (stop-loss,
> take-profit) otomatis untuk mengatasi disposition effect. Batasi
> frekuensi trading untuk mitigasi overconfidence. Gunakan Fear&Greed
> extreme sebagai contrarian signal.

---

## Regulatory IDX 2026

> Perkembangan regulasi pasar modal 2026 yang impact trading rules.
> Sumber: `pustaka/87-regulatory-developments-2026.md`.

### Reformasi Utama

| Reformasi | Detail | Impact Quant |
|-----------|--------|--------------|
| **Free float 15%** | Naik dari 7.5% → 15% (IPO baru) | Liquidity filter update |
| **PEKU klasifikasi** | 3 tier broker (PEKU 1/2/3) | Verifikasi broker capability |
| **MIKU klasifikasi** | 2 tier manajer investasi | — |
| **Auto-reject berjenjang** | Usulan 35%/25%/20% per range | Stop-loss adjustment |
| **Non-Cancellation Period** | Pre-opening & pre-closing | Anti-manipulasi order |
| **PPK reformasi** | Hapus 3 dari 11 kriteria | Saham keluar PPK |

### Auto-Reject Berjenjang (Usulan 2026)

| Range Harga (Rp) | ARB/ARA Lama | ARB/ARA Usulan | Perubahan |
|-------------------|--------------|----------------|-----------|
| 10–200 | ±25% | ±35% | Lebar (+10%) |
| 200–5.000 | ±20% | ±25% | Lebar (+5%) |
| > 5.000 | ±15% | ±20% | Lebar (+5%) |

> **Impact:** Stop-loss & position sizing harus menyesuaikan jika
> usulan ini diterapkan. Range auto-reject lebih lebar = lebih
> banyak ruang pergerakan = stop-loss bisa lebih jauh.

### PEKU (Perusahaan Efek Klasifikasi Utama)

| Tier | Modal Disetor | MKBD | Aktivitas |
|------|---------------|------|-----------|
| PEKU 1 | Rp 1 miliar | Rp 500 juta | Pemasaran efek terbatas |
| PEKU 2 | Rp 55 miliar | Rp 50 miliar | PEE/PPE terbatas |
| PEKU 3 | Rp 110 miliar | Rp 100 miliar | Full: margin, structured, foreign |

> **Impact:** Hanya PEKU 3 yang bisa support margin trading —
> penting untuk leverage strategy. Verifikasi klasifikasi broker.

---

## Performance Attribution & Benchmark

> Metrik evaluasi strategi & benchmark comparison. Sumber:
> `pustaka/77-performance-attribution-benchmark-comparison.md`.

### Risk-Adjusted Metrics

| Metric | Formula | Interpretasi |
|--------|---------|--------------|
| **Sharpe ratio** | (Return - Rf) / σ | > 1.0 good, > 1.5 live minimum, > 3 suspicious |
| **Sortino ratio** | (Return - Rf) / σ_downside | Lebih baik dari Sharpe (hanya downside vol) |
| **Calmar ratio** | Return / Max Drawdown | Return per unit drawdown |
| **Information Ratio** | Alpha / Tracking Error | Excess return per unit tracking error |

### Alpha-Beta Analysis

| Parameter | Threshold | Interpretasi |
|-----------|-----------|--------------|
| Alpha > 0 | Positive | Outperform benchmark (skill) |
| Alpha < 0 | Negative | Underperform |
| Beta > 1 | Aggressive | Lebih volatile dari market |
| Beta = 1 | Market | Mengikuti market |
| Beta < 1 | Defensive | Kurang volatile |
| R² > 0.7 | High | Return well-explained by market |
| R² < 0.3 | Low | Return idiosyncratic |

### Benchmark IDX

| Benchmark | Use Case |
|-----------|----------|
| IHSG (Composite) | Benchmark utama semua saham |
| LQ45 | Large cap liquid |
| IDX30 | Top 30 liquid |
| Sectoral indices | Sector rotation strategy |
| SBN 10-year | Risk-free rate proxy (5–7%) |

### Brinson Attribution

| Effect | Formula | Interpretasi |
|--------|---------|--------------|
| **Allocation Effect** | Σ (w_p - w_b) × (r_b - r_market) | Kontribusi alokasi sektor |
| **Selection Effect** | Σ w_b × (r_p - r_b) | Kontribusi pemilihan saham |
| **Interaction Effect** | Σ (w_p - w_b) × (r_p - r_b) | Gabungan alokasi + selection |

### Drift Detection

| Metric | Threshold | Action |
|--------|-----------|--------|
| PSI (Population Stability Index) | > 0.25 | Retrain model |
| Concept drift | Accuracy drop > 15% | Retrain |
| Sharpe drop | > 20% from baseline | Review strategy |
| Beta shift | > 0.3 from baseline | Regime change suspected |

> **Relevansi quant:** Gunakan Sharpe > 1.5 dan max drawdown < 20%
> sebagai minimum threshold untuk live trading swing strategy di IDX.
> Selalu bandingkan vs IHSG — alpha > 0 menandakan edge, bukan beta.

---

## LLM Agent Layer & Self-Evolving AI

> Arsitektur AI agent untuk self-evolving trading system. Sumber:
> `pustaka/67-llm-agent-layer-self-evolution.md` sampai
> `pustaka/73-self-evolving-ai-roadmap-recommendation.md`.

### 5-Agent Architecture

```
Monitor → Analyzer → Builder → Validator → Integrator
  ↓          ↓          ↓          ↓           ↓
Deteksi   Root cause  Generate   Backtest   Hot-swap +
anomaly   analysis    code       + test     registry
```

| Agent | Fungsi | Trigger |
|-------|--------|---------|
| **Monitor** | Deteksi anomaly, drift, broken adapter | Performance drop > 20%, PSI > 0.25 |
| **Analyzer** | Root cause analysis | Monitor trigger |
| **Builder** | Generate code perbaikan/strategi baru | Analyzer output |
| **Validator** | Backtest + unit test | Builder output |
| **Integrator** | Hot-swap + registry update | Validator pass |

### Self-Evolution Capabilities

| Capability | Deskripsi |
|------------|-----------|
| Self-building | Generate new components dari spec |
| Self-repairing | Fix broken adapters otomatis |
| Self-updating | Adapt to new data sources |
| Self-optimizing | Retrain model saat drift detected |

### Safety Guardrails

| Guardrail | Nilai | Keterangan |
|-----------|-------|------------|
| Performance drop trigger | > 20% Sharpe | Trigger Monitor Agent |
| PSI drift threshold | > 0.25 | Population Stability Index |
| Concept drift threshold | > 15% accuracy drop | Model retrain |
| Error rate threshold | 10% dalam 1 jam | Circuit breaker |
| Max retry iterations | 3 | Sebelum human escalation |
| Backtest regression | New < baseline | Reject strategy |
| Human-in-the-Loop | High-risk changes | Wajib approval |

### TDD Mandatory

```
Builder generates code → Validator runs tests → Pass? → Integrator
                                            → Fail? → back to Builder
```

> Setiap generated code wajib punya unit test sebelum integrasi.
> Sandbox isolation untuk eksekusi generated code.

### Relevansi untuk Quant IDX

- **Adaptive model maintenance** — Monitor Agent deteksi drift di
  IDX data (volume pattern shift, foreign flow anomaly) → trigger
  automatic retraining.
- **Broken adapter recovery** — auto-repair untuk IDX data source
  yang sering berubah (BEI website structure, API endpoint changes).
- **Strategy evolution** — Analyzer + Builder usulkan strategy baru
  berdasarkan pattern terdeteksi (mis. new sector rotation post-PPK
  reformasi).

---

## Roadmap Pengetahuan

> Item pengetahuan yang sudah teridentifikasi tapi belum
> terimplementasi penuh. Bukan backlog pekerjaan — hanya
> peta pengetahuan untuk konteks.

| # | Item | Status | Sumber Teori |
|---|------|--------|--------------|
| R1 | HMM-based regime detection | Heuristic only, HMM TODO | `pustaka/23 §6` |
| R2 | Feature store centralized | Belum ada kode | `pustaka/58` |
| R3 | Purged k-fold CV | Ada di `trading-system`, belum di `market` | `pustaka/23 §9` |
| R4 | Meta-labeling (secondary model) | Belum diimplementasi | `pustaka/23 §7.3` |
| R5 | Commodity-to-stock mapping | Belum terintegrasi di relationship matrix | `pustaka/91` |
| R6 | Sentiment history backfill | Belum migrate dari parquet backup | `pustaka/90` |
| R7 | Triple-barrier labels populate | Schema ada, data belum di-compute | `pustaka/23 §7.2`, `pustaka/84 Stage 6` |
| R8 | Fundamental quarterly history | Snapshot only, quarterly TODO | `pustaka/94 §3.4` |
| R9 | Indonesia macro series | 3 series fetched, 3 belum ada fetcher | `pustaka/94 §3.4` |
| R10 | Multi-window relationship matrix | Schema siap, hanya window=60 populated | `pustaka/94 §3.2` |

### Cross-Reference Pustaka

| Topik | Dokumen |
|-------|---------|
| Teori ML labeling | `pustaka/23-machine-learning-trading.md#4-labeling` |
| Teori regime detection | `pustaka/23-machine-learning-trading.md#5-regime-detection` |
| Pipeline data arrival | `pustaka/84-new-data-arrival-processing-pipeline.md#stage-6` |
| Feature store | `pustaka/58-feature-store-engineering-pipeline.md` |
| Intermarket analysis | `pustaka/35-multi-asset-cross-market-analysis.md` |
| Gap data & timezone | `pustaka/36-gap-data-timezone-global-idx.md` |
| Faktor pasar modal | `pustaka/89-faktor-pasar-modal-analisis-implementasi.md` |
| Komoditas IDX | `pustaka/91-komoditas-spesifik-idx.md` |
| Multi-market system | `pustaka/92-multi-market-multi-asset-trading-system.md` |
| Sentiment & alternative data | `pustaka/30-sentiment-analysis-alternative-data.md` |
| Market microstructure | `pustaka/24-market-microstructure-likuiditas.md` |
| Audit 5 pilar AI/ML | `pustaka/94-aiml-knowledge-architecture-analysis.md` |
| Backtesting & validation | `pustaka/29-backtesting-strategy-validation.md` |
| Backtest-to-live gap | `pustaka/85-backtest-to-live-gap-prevention.md` |
| Portfolio optimization | `pustaka/21-portfolio-optimization-construction.md` |
| Manajemen risiko | `pustaka/07-manajemen-risiko.md` |
| Risk management lanjutan | `pustaka/31-risk-management-lanjutan.md` |
| IDX trading rules | `pustaka/76-idx-trading-rules-market-mechanics.md` |
| TCA & execution quality | `pustaka/52-transaction-cost-analysis-execution-quality.md` |
| Corporate actions | `pustaka/75-corporate-actions-processing-adjustment.md` |
| Pajak & akuntansi | `pustaka/25-pajak-akuntansi-trading.md` |
| Data engineering pipeline | `pustaka/22-data-engineering-pipeline.md` |
| Behavioral finance | `pustaka/09-behavioral-finance.md` |
| Regulatory 2026 | `pustaka/87-regulatory-developments-2026.md` |
| Performance attribution | `pustaka/77-performance-attribution-benchmark-comparison.md` |
| LLM agent layer | `pustaka/67-llm-agent-layer-self-evolution.md` |
