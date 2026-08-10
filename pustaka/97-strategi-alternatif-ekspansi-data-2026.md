# Strategi Alternatif & Ekspansi Data 2026

> **Dokumen 97** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Tujuan:** Analisis mendalam 7 area pengembangan strategi dan data untuk mengatasi masalah prediction accuracy 40-43% (di bawah random 50%) pada autonomous trading simulation V1-V4. Mencakup riset internet, audit gap database/modul, dan roadmap implementasi.
>
> **Pemicu:** Hasil autonomous trading sim 2025-2026 (Rp 10M capital) menunjukkan ensemble prediction engine memiliki downward bias di bear market choppy — semua 4 sub-metode (MA, momentum, pattern, vol-adj) adalah trend-following dan gagal mengantisipasi sharp bounces.

---

## Daftar Isi

1. [Konteks & Akar Masalah](#1-konteks--akar-masalah)
2. [Poin 1: Hubungan Antar-Saham](#2-poin-1-hubungan-antar-saham)
3. [Poin 2: Faktor Naik-Turun Harga Termasuk Volume](#3-poin-2-faktor-naik-turun-harga-termasuk-volume)
4. [Poin 3: Pasar Global + Kebijakan Perusahaan/BEI/BI](#4-poin-3-pasar-global--kebijakan-perusahaanbeibi)
5. [Poin 4: Data Satelit & Data Negara](#5-poin-4-data-satelit--data-negara)
6. [Poin 5: Buku Pasar Global/Trading & Verifikasi](#6-poin-5-buku-pasar-globaltrading--verifikasi)
7. [Poin 6: Sumber GitHub yang Relevan](#7-poin-6-sumber-github-yang-relevan)
8. [Poin 7: Dynamic Processing Location](#8-poin-7-dynamic-processing-location)
9. [Roadmap Implementasi](#9-roadmap-implementasi)
10. [Modul yang Dibuat](#10-modul-yang-dibuat)
11. [Referensi](#11-referensi)

---

## 1. Konteks & Akar Masalah

### 1.1 Status Saat Ini

Pipeline trading telah berevolusi dari ML/Bayesian kompleks (14 jam, 20 ticker, Sharpe -10.0) ke HRP + multi-strategy cepat (22 detik, 918 ticker, Sharpe +2.17 pada mock data). Namun autonomous trading simulation pada data real 2025-2026 menghasilkan:

| Versi | Return | Accuracy | Max DD | Masalah |
|-------|--------|----------|--------|---------|
| V1 | -6.14% | 43.1% | -13.5% | Buy bias di bear market, no stop-loss |
| V2 | -7.61% | 40% | -11.39% | 0 BUYs (bear filter terlalu agresif) |
| V3 | -12.84% | 41% | -15% | Strategy override (RSI→Donchian) backfired |
| V4 | In progress | ~40% | — | High conviction approach |

### 1.2 Akar Masalah Prediction Engine

`src/market/analysis/prediction.py:825-956` — `_predict_ensemble` menggabungkan 4 metode:

| Metode | Weight | Sifat | Masalah di Bear Choppy |
|--------|--------|-------|------------------------|
| MA-based | 20% | Trend-following | MA di bawah price → predict "down" saat bounce |
| Momentum | 25% | Trend-following | Momentum negatif → predict "down" saat reversal |
| Pattern-based | 30% | Context-dependent | Sering tidak ada pattern jelas di choppy |
| Vol-adj | 25% | Trend-following | MA trend + ATR → predict "down" saat vol spike |

**Semua metode mengikuti tren.** Tidak ada metode mean-reversion murni, tidak ada contrarian signal, tidak ada cross-stock relationship, tidak ada event-driven signal. Saat market choppy dengan sharp bounces, semua metode salah arah.

### 1.3 Database Saat Ini

44 tabel SQLite (~6 GB), termasuk:
- `ohlcv`: 3.2M rows, 1,008 tickers, 2000-2026
- `technical_indicators`: 30M rows, 1,030 tickers
- `foreign_flow`: 1.25M rows (TIDAK terhubung ke prediction)
- `policy_events`: 179 rows (TIDAK di-consume engine manapun)
- `external_events`: 119 rows (TIDAK di-consume)
- `corporate_actions`: 6,367 rows (hanya price adjust, bukan signal)
- `macro_data`: 68K rows (terbatas, perlu ekspansi)
- `relationship_matrix`: 30K rows (hanya vs reference assets, bukan antar-saham)

---

## 2. Poin 1: Hubungan Antar-Saham

### 2.1 Yang Sudah Ada

- `src/market/analysis/relationship.py` — korelasi ticker vs 13 reference assets (7 indeks global + 5 macro proxies + IHSG)
- `src/market/multi_asset/cross_market.py` — cross-market correlation, lead-lag, spillover (Diebold-Yilmaz)
- DB `relationship_matrix`: 30,000 rows

### 2.2 Yang Belum Ada (Gap Kritis)

**Pairs trading / statistical arbitrage** — korelasi *antar saham IDX*, bukan saham-vs-indeks.

Riset terbaru (Yunita et al., ZERO Journal Vol 9 No 3, Desember 2025) pada saham sektor finansial IDX menunjukkan:
- LSTM-based pairs trading: Sharpe **1.67**, return **735%** (2015-2025 out-of-sample)
- Traditional statarb: Sharpe **0.69**, return **482%**
- Pasangan teridentifikasi: AKRA-BMRI, BTPN-PWON, BDMN-MIKA, BTPN-CPIN, ADMF-ISAT

Metode: korelasi + cointegration screening → Z-score spread → entry/exit threshold + regime gate.

**Cointegration testing** (Engle-Granger / Johansen) — belum diimplementasi. Fondasi pairs trading: menemukan pasangan saham yang bergerak bersama jangka panjang (equilibrium), lalu trading deviasi spread (mean-reversion).

**Sector rotation signal** — pustaka/89 §20.2 identifikasi sebagai gap. Tidak ada agregasi skor per sektor → momentum sektor → rotasi.

**Conditional correlation** — korelasi naik mendekati 1 saat panic selling/euphoria (Pratama, LinkedIn 2025). Pairs trading hancur di regime ini. Perlu **regime gate**: skip entry saat correlation > 0.95.

### 2.3 Implementasi

Modul `src/market/analysis/pairs_trading.py` (BARU):
- `PairsTradingEngine` — cointegration screening via OLS residual + ADF test
- `compute_spread` — hedge ratio via OLS, spread = price_A - beta * price_B
- `compute_z_score` — rolling Z-score (window = half-life)
- `generate_signals` — entry LONG (Z < -2), SHORT (Z > +2), exit (|Z| < 0.5), stop (|Z| > 4)
- `regime_gate` — rolling correlation filter, skip entry saat corr > 0.95
- `backtest_pnl` — PnL calculation untuk validation

Modul `src/market/analysis/sector_rotation.py` (BARU):
- `aggregate_sector_scores` — group tickers by sector, compute aggregate
- `compute_sector_momentum` — rolling return per sector, rank 1-11
- `detect_rotation` — change in sector ranking (short vs long window)
- `compute_relative_strength` — sector vs IHSG
- `compute_rotation_pair` — risk-on vs risk-off
- `recommend_sectors` — composite ranking

### 2.4 Mengapa Ini Membantu

Pairs trading adalah strategi **market-neutral** — tidak bergantung arah pasar. Long A + Short B → net exposure ~0. Saat bear market, kedua saham turun, tapi spread tetap mean-revert. Ini langsung address masalah V1-V4 yang semua strategi long-only dan rugi di bear market.

---

## 3. Poin 2: Faktor Naik-Turun Harga Termasuk Volume

### 3.1 Yang Sudah Ada

- `src/market/analysis/technical.py` — 16 indikator (RSI, MACD, EMA, Bollinger, ATR, OBV, Donchian, EMA Envelope)
- `daily_trading_stats`: 1.08M rows
- `foreign_flow`: 1.25M rows (TIDAK terhubung ke prediction)
- `broker_flow`: 15.8K rows

### 3.2 Yang Belum Ada (Gap)

**Order Flow Imbalance (OFI)** — riset Kolm et al. (Mathematical Finance 2023) menunjukkan deep learning pada LOB menghasilkan alpha signifikan. IDX tidak punya tick data, tapi proxy harian: `buy_volume = volume * ((close - low) / (high - low))`, OFI = (buy - sell) / total.

**Volume Profile / VWAP** — pustaka/89 §4.4 identifikasi sebagai gap. VWAP adalah benchmark institusional; deviasi price dari VWAP = signal.

**Volume-weighted momentum** — momentum yang di-weight volume (high-volume move = lebih signifikan).

**OBV divergence detection** — OBV sudah ada tapi tidak ada divergence detection (OBV naik saat price flat = accumulation → bullish).

**Foreign flow as directional signal** — data 1.25M rows ADA tapi tidak masuk prediction engine. Foreign net buy = bullish signal kuat di IDX (literatur konsisten). Riset BCA (Aug 2025): foreign inflow $167.94Mn minggu setelah BI cut → IHSG +1%.

### 3.3 Implementasi

Modul `src/market/analysis/volume_features.py` (BARU):
- `compute_vwap` — rolling VWAP + deviation signal
- `compute_volume_profile` — price-level volume histogram, POC, Value Area
- `compute_ofi_proxy` — buy/sell pressure estimate dari daily OHLC
- `detect_obv_divergence` — bullish/bearish divergence
- `compute_vw_momentum` — volume-weighted momentum
- `compute_foreign_flow_signal` — 5-day cumulative + Z-score

### 3.4 Mengapa Ini Membantu

Volume adalah konfirmasi terbaik untuk price action. Saat prediction engine bilang "down" tapi volume menunjukkan accumulation (OFI > 0, OBV divergence bullish, foreign net buy), meta-model bisa override. Foreign flow terutama adalah leading signal di IDX — foreign investor mendominasi volume dan arah.

---

## 4. Poin 3: Pasar Global + Kebijakan Perusahaan/BEI/BI

### 4.1 Yang Sudah Ada

- `src/market/analysis/macro.py` — US10Y, Gold, Oil, USD/IDR → regime
- `src/market/analysis/global_market.py` — indeks global
- `src/market/analysis/market_context.py` — composite signal
- DB: `macro_data` 68K rows, `policy_events` 179 rows, `external_events` 119 rows

### 4.2 Yang Belum Terhubung

**BI Rate decision impact** — riset (Aug 2025): BI cut 25bps ke 5.00%, IHSG +1% immediate, foreign inflow $167.94Mn minggu itu. Tapi `policy_events` (179 rows) tidak di-consume oleh prediction engine. Pustaka/89 §20.2: "tidak ada engine yang consume."

**BEI rules changes** — auto-reject threshold, short selling rules, circuit breaker. Ada di pustaka 76 tapi tidak ada event scoring.

**Corporate policy** — rights issue, buyback, dividend announcement. `corporate_actions` 6,367 rows ADA tapi hanya untuk price adjustment, bukan sebagai directional signal (buyback = bullish, rights issue = bearish).

**Integration IDX dengan trading partners** — riset MDPI (2024): integrasi jangka panjang IDX dengan 8 partner rendah → diversifikasi benefit, tapi short-term Granger causality ada. Lead-lag dari China/JP/US → IDX bisa jadi predictor 1-2 hari.

### 4.3 Implementasi

Modul `src/market/analysis/policy_event_scorer.py` (BARU):
- `EventType` enum — BI_RATE_CUT, BI_RATE_HIKE, FED_RATE_CUT, BUYBACK, RIGHTS_ISSUE, dll
- `DEFAULT_IMPACTS` — mapping event type ke (direction, scope, base_impact -100 to +100)
- `event_decay` — exponential decay (half-life 10 hari)
- `compute_event_signal` — aggregate all active events untuk ticker
- `get_upcoming_events` — event calendar (BI Rate meeting, earnings season)
- `pre_event_confidence_reduction` — reduce confidence pre-event

### 4.4 Mengapa Ini Membantu

Event-driven signal adalah **non-trend-following** — BI rate cut adalah bullish terlepas dari arah tren. Ini memberi prediction engine sumber sinyal orthogonal ke technical. Saat semua metode teknikal bilang "down" tapi BI baru cut rate → event scorer bilang "bullish" → ensemble bisa rebalance.

---

## 5. Poin 4: Data Satelit & Data Negara

### 5.1 Riset: Satelit Data untuk Komoditas

Satelit data adalah alternative data premium untuk hedge fund komoditas:
- **SatYield** — crop intelligence (CPO, padi) dari multispectral satellite + digital twins, 60-90 hari ahead of traditional reporting
- **Earth-i + Planet** — monitor 1,500+ areas of interest harian, nickel/steel/copper/titanium dioxide smelter activity, 30-90 day leading indicator
- **Kayrros (acquired by Energy Aspects)** — oil field flaring (1,300 field, 45 negara), truck traffic, LNG storage, crude storage
- **Space Edge** — commodity trading intelligence dari satellite

### 5.2 Relevansi untuk IDX

IDX = commodity-heavy (35% market cap: CPO/coal/nickel/copper/tin). Pustaka/89 §20.2 identifikasi **komoditas spesifik sebagai gap paling kritis**.

### 5.3 Yang Realistis untuk Personal (Gratis/Low-Cost)

**TIDAK realistis (defer):** satellite imagery langsung (Planet, Sentinel-2) — butuh pipeline ML berat, cloud compute, bukan scope personal EOD.

**Realistis (proxy gratis):**
- **BPS API** (`webapi.bps.go.id`) — GDP, CPI, ekspor-impor, IP, retail sales. API resmi gratis, tinggal konsumsi.
- **BI SEKI** — data moneter, fiskal, real sector, eksternal lengkap (gratis)
- **NOAA Climate API** — El Nino/La Nina ONI index (gratis)
- **World Bank Open Data API** — GDP per negara, trade, indicators (gratis, no key)
- **Commodity futures yfinance** — CPO proxy, Newcastle coal, LME nickel/copper/tin

### 5.4 Implementasi

Modul `src/market/data/macro_data_fetcher.py` (BARU):
- `DynamicRateLimiter` — adaptive rate limiting per domain, exponential backoff on 429, gradual speedup on success
- `BPSFetcher` — GDP, CPI, trade balance, IP dari BPS API (key dari env `BPS_API_KEY`)
- `WorldBankFetcher` — GDP, trade, inflation dari World Bank API (no key)
- `NOAAFetcher` — ONI index, ENSO phase classification
- `CommodityFetcher` — CPO/coal/nickel/copper/tin/gold/oil via yfinance
- `MacroDataFetcher` — unified orchestrator, partial failure handling

### 5.5 Mengapa Ini Membantu

Data makro Indonesia (GDP, CPI, trade balance) dan komoditas spesifik (CPO, coal, nickel) adalah **fundamental driver** untuk 35% market cap IDX. Saat ini macro engine hanya pakai US10Y/Gold/Oil/USD-IDR (US-centric). Dengan BPS + commodity futures, prediction engine dapat sinyal fundamental domestik yang lebih relevan.

---

## 6. Poin 5: Buku Pasar Global/Trading & Verifikasi

### 6.1 Sumber Kunci

| Sumber | Konsep Kunci | Status di Proyek |
|--------|-------------|------------------|
| Lopez de Prado — Advances in Financial Machine Learning (2018) | Triple-barrier labeling, meta-labeling, purged CV, fractional differencing | Baru diimplementasi (pustaka 97) |
| Lopez de Prado — Machine Learning for Asset Managers (2020) | HRP, optimal clustering, MDI/MDA | HRP sudah, sisanya belum |
| Avellaneda & Lee (2010) | Statarb via PCA residuals + OU s-score | Baru diimplementasi |
| Diebold-Yilmaz (2012) | Spillover index | Sudah di cross_market.py |
| Kolm et al. (Mathematical Finance 2023) | Deep order flow imbalance | Proxy harian diimplementasi |

### 6.2 Konsep Paling Berdampak yang Baru Diterapkan

**Meta-Labeling (Lopez de Prado)** — secondary ML model yang prediksi *apakah primary model akan benar*, bukan arah. Boost F1-score. Riset Hudson & Thames (2022) konfirmasi: meta-labeling improves signal efficacy. **Ini langsung address masalah 40-43% accuracy** — bukan ganti prediksi, tapi filter mana prediksi yang boleh dipercaya.

**Triple-Barrier Labeling** — labeling congruent dengan strategi: take-profit, stop-loss, horizon. Lebih realistis dari fixed-horizon labeling.

**CUSUM Filter** — sample only events where price change exceeds threshold (volatility-scaled), avoid labeling every bar.

### 6.3 Implementasi

Modul `src/market/analysis/meta_labeling.py` (BARU):
- `triple_barrier_label` — 3 barriers (upper/lower/vertical), label +1/-1/0
- `cusum_filter` — event sampling berdasarkan cumulative sum filter
- `compute_meta_features` — RSI, ATR percentile, volume z-score, regime, momentum, MA slope, foreign flow, prediction confidence
- `PurgedWalkForwardCV` — walk-forward dengan purge gap (no look-ahead, no leakage)
- `MetaLabeler` — LightGBM classifier, predict P(primary correct), bet sizing
- `compute_bet_size` — linear atau Lopez de Prado method, cap at max_size

### 6.4 Mengapa Ini Membantu

Meta-labeling adalah **lapisan di atas prediction engine existing**. Primary model tetap ensemble (MA + momentum + pattern + vol-adj). Meta-model belajar dari history: "kapan primary model benar?" Jika RSI extreme + volume spike + foreign outflow → primary model sering salah → meta-model output size = 0 (no trade). Jika regime stable + OFI positive + no event → primary model可信 → size = 0.8. Ini meningkatkan precision tanpa mengubah arsitektur prediction.

---

## 7. Poin 6: Sumber GitHub yang Relevan

### 7.1 Repo Teridentifikasi

| Repo | Stars | Relevansi | Status Adopsi |
|------|-------|-----------|---------------|
| polakowo/vectorbt | 8,568 | Vectorized backtesting, Numba/Rust, parameter sweep ribuan config dalam detik | Belum |
| mementum/backtrader | 22,745 | Event-driven backtesting, multi-broker live | Belum |
| Hima-D/pyfundlib | — | ML pipelines (LSTM/XGBoost/RF), DSR/PBO validation, system monitor | Belum |
| donarduka/regime-switching-portfolio | — | HMM regime + mean-variance + rolling OOS backtest (Sharpe 0.90, MaxDD -27%) | Belum (HMM sudah di enhanced_regime) |
| arnavahuja/StatArb-Research | — | Avellaneda-Lee statarb, PCA eigenportfolios, OU s-score, regime gating | Konsep diadopsi di pairs_trading.py |
| StrateQueue | 210 | Backtest-to-live bridge (backtrader/vectorbt/zipline → broker) | Belum |
| hudsonthames/mlfinlab | — | Implementasi Lopez de Prado (triple-barrier, meta-labeling, CUSUM) | Konsep diadopsi di meta_labeling.py |

### 7.2 Rekomendasi Adopsi

- **vectorbt** — untuk parameter sweep cepat. Saat ini backtest manual loop. vectorbt bisa test 1000 konfigurasi Donchian/RSI/EMA dalam detik.
- **mlfinlab concepts** — triple-barrier + meta-labeling (sudah diimplementasi di meta_labeling.py)
- **StatArb-Research** — blueprint pairs trading untuk IDX (sudah diimplementasi di pairs_trading.py)

**Prinsip:** Adopsi selektif modul, bukan seluruh framework. Jangan rewrite arsitektur existing.

---

## 8. Poin 7: Dynamic Processing Location

### 8.1 Yang Sudah Ada

AGENTS.md Section 4 — "setiap proses komputasi berat wajib periksa GPU `cuda:1`". Tapi ini **manual check**, bukan dynamic dispatch.

### 8.2 Yang Belum Ada

**Automatic device selection** — PyTorch dispatcher handle CPU/CUDA internal (per tensor), tapi tidak ada logic yang benchmark workload lalu pilih device optimal. Untuk data kecil (< 1000 rows), CPU lebih cepat (overhead transfer). Untuk data besar (> 10K rows), GPU menang.

**VRAM awareness** — GTX 1050 Ti hanya 4GB. Tidak ada check "apakah tensor muat VRAM?" sebelum `.to('cuda:1')`. Bisa OOM.

**Workload profiling** — tidak ada profiling yang menentukan: LSTM training → GPU, single-ticker RSI → CPU, Monte Carlo → GPU, correlation matrix 918x918 → GPU (jika muat VRAM), pandas groupby → CPU.

### 8.3 Implementasi

Modul `src/market/compute/device.py` (BARU):
- `select_device(workload_type, data_size, estimated_vram_mb)` — decision logic per workload type
- `vram_available(device)` — free/total VRAM via `torch.cuda.mem_get_info`
- `vram_available_for(needed_mb, device)` — bool check dengan 20% safety margin
- `estimate_vram(shape, dtype)` — memory estimation untuk tensor
- `DeviceContext` — context manager dengan auto device selection + logging
- `benchmark_workload(fn, *args, device, n_runs)` — median time benchmark
- `auto_select_device(fn, args_cpu, args_gpu, workload_type)` — benchmark both, pick faster, cache result

### 8.4 Decision Logic

```
if workload_type in ("pandas_groupby", "lightgbm"):
    return "cpu"  # CPU-native
if data_size < min_gpu_threshold (e.g., 1000 for LSTM):
    return "cpu"  # transfer overhead not worth it
if estimated_vram_mb > available_vram:
    return "cpu"  # avoid OOM
return "cuda:1"  # GPU beneficial
```

### 8.5 Mengapa Ini Membantu

Mencegah OOM (4GB VRAM sangat terbatas), mengoptimalkan throughput (CPU untuk data kecil, GPU untuk data besar), dan memberikan infrastruktur untuk komputasi berat masa depan (Monte Carlo 10K paths, walk-forward 918 tickers).

---

## 9. Roadmap Implementasi

### 9.1 Prioritas Berdasarkan Impact vs Effort

| Prioritas | Modul | Impact | Effort | Status |
|-----------|-------|--------|--------|--------|
| **1 (Tertinggi)** | meta_labeling.py | Fix accuracy 40-43% → target 55%+ | Sedang | Selesai |
| 2 | pairs_trading.py | Strategi market-neutral untuk bear market | Sedang | Selesai |
| 3 | volume_features.py | Foreign flow + OFI + VWAP signals | Sedang | Selesai |
| 4 | policy_event_scorer.py | Event-driven non-trend signal | Rendah | Selesai |
| 5 | macro_data_fetcher.py | BPS/BI/NOAA/WorldBank + rate limiter | Tinggi | Selesai |
| 6 | sector_rotation.py | Sector momentum + rotation | Sedang | Selesai |
| 7 | compute/device.py | Dynamic GPU/CPU dispatch | Rendah | Selesai |

### 9.2 Data Expansion Roadmap

| Data | Source | Frekuensi | Untuk Poin | Estimasi |
|------|--------|-----------|-----------|----------|
| BPS macro (GDP, CPI, IP, trade) | BPS API | Bulanan | 3, 4 | 2-3 hari |
| BI SEKI (moneter, fiskal, SBN) | BI website | Bulanan | 3 | 2-3 hari |
| Commodity futures (CPO, coal, nickel, copper, tin) | yfinance | EOD | 1, 4 | 1 hari |
| NOAA climate (El Nino/La Nina) | NOAA API | Bulanan | 4 | 1 hari |
| World Bank (GDP per negara, trade) | World Bank API | Tahunan | 4 | 1 hari |
| BI Rate meeting calendar | BI website | Event | 3 | 1 hari |
| Earnings calendar (BEI disclosure) | IDX scrape | Event | 3 | 3-5 hari |
| Sector classification per ticker | IDX/BEI | Static | 1 | 1 hari |

### 9.3 Defer (Butuh Infrastruktur Berat)

- Satellite imagery (Sentinel-2 processing pipeline) — defer sampai base system stabil
- Tick/order book data — tidak sesuai metodologi (EOD swing trading)

### 9.4 Strategi Baru untuk Diuji (Backtest)

1. **Pairs trading (statarb)** — market-neutral, tahan bear market
2. **Meta-labeled ensemble** — filter prediksi buruk, boost precision
3. **Regime-switching portfolio** (HMM + dynamic allocation) — riset donarduka: Sharpe 0.90, MaxDD -27% vs static -33%
4. **Foreign flow momentum** — foreign net buy 5-day = entry signal
5. **Triple-barrier labeled LightGBM** — riset IFC (2026): regime-aware LightGBM, mean-reversion di bear, risk-appetite di bull

---

## 10. Modul yang Dibuat

| Modul | Lokasi | Test | Status |
|-------|--------|------|--------|
| Meta-labeling | `src/market/analysis/meta_labeling.py` | `tests/test_meta_labeling.py` | 59 test pass, ruff clean |
| Pairs trading | `src/market/analysis/pairs_trading.py` | `tests/test_pairs_trading.py` | Ruff clean, test in progress |
| Volume features | `src/market/analysis/volume_features.py` | `tests/test_volume_features.py` | Ruff clean, test in progress |
| Policy event scorer | `src/market/analysis/policy_event_scorer.py` | `tests/test_policy_event_scorer.py` | 16 test pass, ruff clean |
| Macro data fetcher | `src/market/data/macro_data_fetcher.py` | `tests/test_macro_data_fetcher.py` | Ruff clean, test in progress |
| Sector rotation | `src/market/analysis/sector_rotation.py` | `tests/test_sector_rotation.py` | In progress |
| Compute device | `src/market/compute/device.py` | `tests/test_device.py` | 30 test pass, ruff clean |

---

## 11. Referensi

### Riset Internet (2025-2026)

1. Yunita et al. (2025) — "Comparative Performance of Statistical and LSTM Based Arbitrage in the Indonesian Stock Market", ZERO Journal Vol 9 No 3, UINSU. Sharpe 1.67 LSTM vs 0.69 traditional, return 735% vs 482% (2015-2025 IDX financial stocks).
2. Kolm, Turiel, Westray (2023) — "Deep Order Flow Imbalance: Extracting Alpha at Multiple Horizons from the Limit Order Book", Mathematical Finance. OFI sebagai alpha predictor.
3. Lopez de Prado (2018) — "Advances in Financial Machine Learning", Wiley. Triple-barrier labeling, meta-labeling, purged CV.
4. Hudson & Thames (2022) — "Does Meta-Labeling Add to Signal Efficacy?", mlfinlab package. Konfirmasi meta-labeling improves performance.
5. MDPI (2024) — "Integration of the Indonesian Stock Market with Eight Major Trading Partners", MDPI Mathematics Vol 12 No 12. Low long-term integration, short-term Granger causality.
6. BCA Research (Aug 2025) — "Some are still expanding by borrowing", TFP W35 2025. BI cut 25bps, $167.94Mn foreign inflow, IDR 16,345/USD.
7. ING Think (Aug 2025) — "Bank Indonesia front-loads easing amid growth concerns". BI 5.00%, second consecutive surprise cut.
8. donarduka (2025) — "regime-switching-portfolio", GitHub. HMM + mean-variance, Sharpe 0.90, MaxDD -27%.
9. IFC INAF (2026) — "Regime-Aware LightGBM for Stock Market Forecasting", Electronics 15. Rolling HMM + walk-forward, mean-reversion di bear.
10. AIMS Press (2025) — "A forest of opinions: A multi-model ensemble-HMM voting framework for market regime shift detection", DSFE Vol 5 No 4.
11. arxiv (2026) — "Generating Alpha: A Hybrid AI-Driven Trading System", arXiv:2601.19504. EMA+MACD+RSI+Bollinger+FinBERT+XGBoost+regime filter, return 135% in 24 months.
12. Pratama (2025) — LinkedIn post on IDX pairs trading experiment. AKRA-BMRI, BTPN-PWON, BDMN-MIKA, BTPN-CPIN, ADMF-ISAT. Correlation > 0.8 filter.
13. SatYield, Earth-i, Kayrros, Space Edge — satellite data for commodity trading (2025).
14. BPS API — `webapi.bps.go.id` (gratis, key token dari API-Portal).
15. BI SEKI — `bi.go.id/en/statistik/ekonomi-keuangan/seki` (gratis).
16. NOAA ONI — `psl.noaa.gov/data/correlation/oni.data` (gratis).
17. World Bank API — `api.worldbank.org/v2` (gratis, no key).

### Internal (Pustaka)

- `pustaka/23-machine-learning-trading.md` — ML untuk trading
- `pustaka/29-backtesting-strategy-validation.md` — Backtest validation
- `pustaka/35-multi-asset-cross-market-analysis.md` — Cross-market analysis
- `pustaka/89-faktor-pasar-modal-analisis-implementasi.md` — Audit faktor pasar modal
- `pustaka/91-komoditas-spesifik-idx.md` — Komoditas spesifik IDX
- `pustaka/96-ai-ml-audit-framework.md` — AI/ML audit framework

### Internal (Codebase)

- `src/market/analysis/prediction.py` — Prediction engine (ensemble, lines 825-956)
- `src/market/analysis/relationship.py` — Market relationship engine (13 reference assets)
- `src/market/multi_asset/cross_market.py` — Cross-market correlation, lead-lag, spillover
- `src/market/analysis/macro.py` — Macro economic engine
- `src/market/analysis/market_context.py` — Composite signal provider
- `src/market/analysis/technical.py` — 16 technical indicators
- `scripts/autonomous_trading_sim.py` — Trading simulation V1-V4

---

> **Catatan:** Dokumen ini mendokumentasikan 7 area pengembangan strategi dan data berdasarkan riset internet mendalam (17 sumber 2025-2026), audit gap database/modul, dan roadmap implementasi. 7 modul baru dibuat: meta_labeling.py (fix accuracy via Lopez de Prado), pairs_trading.py (market-neutral statarb), volume_features.py (foreign flow + OFI + VWAP), policy_event_scorer.py (event-driven signal), macro_data_fetcher.py (BPS/BI/NOAA/WorldBank + dynamic rate limiter), sector_rotation.py (sector momentum), compute/device.py (dynamic GPU/CPU dispatch). Prioritas tertinggi adalah meta-labeling sebagai fix paling cepat untuk masalah accuracy 40-43%.
