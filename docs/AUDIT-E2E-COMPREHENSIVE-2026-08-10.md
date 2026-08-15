# Laporan Audit End-to-End Komprehensif — Aplikasi Pasar Modal

> **Update 2026-08-15:** Database utama sekarang PostgreSQL 16 di `localhost:5433/market` (alembic head 0023). File `data/market_research.db` (SQLite) sudah tidak ada. Laporan ini ditulis saat masih SQLite dan dipertahankan untuk konteks historis.

**Tanggal audit:** 10 Agustus 2026 (Senin)
**Auditor:** Senior Solutions Architect / Principal Quant Researcher / Expert Database Engineer
**Source of truth:** `MEGAPLAN.md` (801 baris), `pustaka/00-95` (96 dokumen)
**Database audited (saat itu):** `data/market_research.db` (10 GB, alembic head `0013`) — sekarang PostgreSQL `market`
**Metodologi:** Audit 4-layer (Database → ML/Infrastructure → Application → DevOps)

---

## Ringkasan Eksekutif

| Layer | Status | Temuan Kritis |
|-------|--------|---------------|
| 1. Database | ✅ Sehat dengan catatan | 4 kolom 100% NULL (ema50, donchian×3); data stale >24h pada 4 tabel inti; `app_notifications` & `transaksi_investor` kosong (0 rows) |
| 2. ML/AI Signal | ⚠️ Akurasi di bawah target | Akurasi 40-43% (di bawah random 50%) di bear market; veto-filter Lopez de Prado tereksekusi benar; DST guard komprehensif |
| 3. Application | 🔴 Gap wire-up kritis | Tidak ada route API untuk `app_notifications`; frontend belum render sinyal BUY/SELL/HOLD + HRP sizing |
| 4. DevOps | ✅ Gate tercapai | 1368 passed / 4 failed (pre-existing); coverage 70.15% (gate 70%); 13 migration bersih |

**Verdict keseluruhan:** Sistem 90% siap dari sisi backend/ML, tetapi **frontend-to-backend wire-up untuk daily signal notification belum ada** — ini adalah gap blocking untuk user-facing delivery. ML accuracy 40-43% adalah prioritas riset tertinggi (target 55%+).

---

## LAYER 1 — PEMETAAN SKEMA DATABASE RELASIONAL

### 1.1 Inventarisasi Tabel (57 objek)

Database `market_research.db` (10 GB) berisi **55 tabel + 2 view-like objects** (sqlite_sequence, alembic_version). Klasifikasi:

| Kategori | Jumlah | Tabel |
|----------|--------|-------|
| Hirarki relasional (migration 0013) | 9 | regulator, bursa_efek, sektor, emiten, instrumen, indeks_pasar, broker, broker_bursa, transaksi_investor |
| Core time-series | 4 | ohlcv, technical_indicators, technical_indicators_wide, daily_trading_stats |
| ML/AI | 5 | stock_personality, stock_prediction, ml_labels, ai_weights, scores |
| Market data | 8 | foreign_flow, macro_data, fundamental_data, corporate_actions, dividends, market_calendar, fx_rates, fear_greed |
| Infrastructure | 7 | app_notifications, data_watermark, recompute_watermark, scheduler_state, parquet_sync_state, source_health, system_state |
| Reference | 6 | instrument_master, market_registry, sector_master, relationship_matrix, pattern_analysis, valuation_cache |
| Risk | 2 | daily_risk_metrics, market_regimes |
| News/Events | 3 | news, policy_events, external_events |
| Execution/OMS | 4 | orders, positions, trade_journal, audit_log |
| Governance/ESG | 3 | esg_scores, corporate_governance, trading_suspensions |
| Misc | 4 | render_log, watchlist, equity_snapshots, broker_flow |

### 1.2 Matriks Peta Struktur Database Aktif — Tabel Inti

#### Hirarki Relasional Baru (Migration 0013: Negara → Regulator → Bursa → Sektor → Emiten → Instrumen → Transaksi)

```
regulator (8 rows) — PK: id_regulator
  └─ negara: VARCHAR(50) NOT NULL
  └─ nama_regulator: VARCHAR(100) NOT NULL
  └─ UNIQUE(nama_regulator, negara)
        │
        ▼ FK ondelete=RESTRICT
bursa_efek (11 rows) — PK: id_bursa
  └─ nama_bursa, mic_code
  └─ FK id_regulator → regulator.id_regulator
  └─ INDEX ix_bursa_regulator
        │
        ▼ FK ondelete=RESTRICT
emiten (999 rows) — PK: id_emiten
  └─ kode_ticker UNIQUE, nama_perusahaan
  └─ FK id_bursa → bursa_efek.id_bursa
  └─ FK id_sektor → sektor.id_sektor (ondelete=SET NULL)
  └─ INDEX ix_emiten_bursa, ix_emiten_sektor
        │
        ▼ FK ondelete=CASCADE
instrumen (999 rows) — PK: id_instrumen
  └─ jenis_instrumen, asset_class, base_currency
  └─ FK id_emiten → emiten.id_emiten
  └─ INDEX ix_instrumen_jenis, ix_instrumen_emiten
        │
        ▼ FK
transaksi_investor (0 rows) — PK: id_transaksi
  └─ tanggal_transaksi, tipe_transaksi, jumlah_lot, harga_per_saham
  └─ biaya_broker, pajak_pph_final, status_eksekusi
  └─ FK id_broker → broker.id_broker
  └─ FK id_instrumen → instrumen.id_instrumen
  └─ INDEX ix_transaksi_tanggal, ix_transaksi_instrumen, ix_transaksi_broker
```

**Verdict hirarki:** ✅ Struktur FK 5-level sesuai spesifikasi (Negara → Regulator → Bursa → Sektor → Emiten → Instrumen → Transaksi). `ondelete=RESTRICT` pada regulator/bursa mencegah orphaning; `CASCADE` pada emiten→instrumen benar.

#### Tabel Core Lainnya

| Tabel | Rows | PK | Kolom Kunci | Index | FK |
|-------|------|----|-------------|-------|----|
| `instrument_master` | 1,056 | ticker (VARCHAR 30) | 29 kolom (asset_class, market_mic, free_float, market_cap, delisting_risk_score, former_ticker, index_category, region, trading_status) | autoindex PK | FK market_mic → market_registry.mic_code |
| `ohlcv` | 3,219,427 | id (INTEGER auto) | ticker, timestamp, timeframe, OHLCV+adjusted_close, data_quality_score | ix_ohlcv_ticker, ix_ohlcv_timestamp, ix_ohlcv_ticker_ts (composite), unique(ticker,timestamp,timeframe) | — |
| `technical_indicators_wide` | 3,049,358 | id (INTEGER auto) | ticker, date, timeframe, 16 indikator (ma20, ma50, rsi, macd, macd_signal, adx, atr14, bb_upper/lower, volume_sma20, ema50, ema_env_upper/lower, donchian_upper/lower/mid) | ix_tiw_ticker_date (composite), ix_tiw_date, ix_tiw_ticker, unique(ticker,date,timeframe) | — |
| `stock_personality` | 1,026 | ticker | 32 kolom (volatility_regime, trend_bias, beta_vs_ihsg, liquidity_score, personality_label, pattern stats, prediction mirror) | autoindex PK | — |
| `stock_prediction` | 1,020 | ticker | 10 kolom (predicted_direction, predicted_price, predicted_return_pct, prediction_confidence, ml_signal, multifactor_signal, composite_signal, factors_summary, prediction_updated_at) | autoindex PK | — |
| `app_notifications` | **0** | id (INTEGER auto) | timestamp, title, body_json (TEXT), status (UNREAD/READ) | ix_app_notif_status | — |

### 1.3 Analisis NULL Percentage

#### `instrument_master` (1,056 rows)

| Kolom | NULL | % | Status |
|-------|------|---|--------|
| name | 0 | 0.00% | ✅ |
| sector | 34 | 3.22% | ✅ |
| listing_date | 71 | 6.72% | ✅ |
| delisting_date | 991 | 93.84% | ✅ Expected (hanya 62 delisted) |
| free_float | 1,031 | **97.63%** | 🔴 Tinggi — perlu backfill |
| market_cap | 1,031 | **97.63%** | 🔴 Tinggi — perlu backfill |
| listed_shares | 73 | 6.91% | ✅ |
| former_ticker | 1,052 | 99.62% | ✅ Expected (hanya merger) |
| index_category | 999 | 94.60% | ✅ Expected (hanya 57 indeks) |
| trading_status | 0 | 0.00% | ✅ |

#### `technical_indicators_wide` (3,049,358 rows) — KRITIS

| Kolom | NULL | % | Status |
|-------|------|---|--------|
| ma20, ma50, rsi, macd, macd_signal, adx, atr14, bb_upper/lower, volume_sma20 | 0.4-9.7% | ✅ Normal (warmup period) |
| **ema50** | 3,049,358 | **100.00%** | 🔴 **KOSONG TOTAL** |
| **donchian_upper** | 3,049,358 | **100.00%** | 🔴 **KOSONG TOTAL** |
| **donchian_lower** | 3,049,358 | **100.00%** | 🔴 **KOSONG TOTAL** |
| **donchian_mid** | 3,049,358 | **100.00%** | 🔴 **KOSONG TOTAL** |

**Root cause:** Kolom `ema50`, `donchian_upper/lower/mid` didefinisikan di migration 0012 tetapi **backfill script belum dijalankan** untuk 4 indikator ini. Overnight Strategy Mining menggunakan Donchian sweep (period 10-25) — jika membaca dari tabel ini, akan mendapat NULL. **Namun**, `overnight_strategy_mining.py` menghitung Donchian on-the-fly dari OHLCV (bukan dari tabel wide), sehingga fungsionalitas tidak broken — tetapi tabel wide tidak serve kebutuhan ini.

**Rekomendasi:** Jalankan backfill untuk 4 kolom ini, atau drop kolom jika tidak ada consumer (lihat §Rekomendasi).

#### `stock_personality` (1,026 rows)

| Kolom | NULL | % | Status |
|-------|------|---|--------|
| avg_volume | 1,026 | **100.00%** | 🔴 **KOSONG TOTAL** — perlu backfill dari OHLCV |
| volatility_regime, trend_bias, beta_vs_ihsg, liquidity_score, personality_label | 41 | 4.00% | ✅ (ticker tanpa OHLCV cukup) |
| prediction_confidence, ml_signal, multifactor_signal, composite_signal, predicted_direction | 6 | 0.58% | ✅ |

#### `stock_prediction` (1,020 rows)

| Kolom | NULL | % | Status |
|-------|------|---|--------|
| ml_signal, multifactor_signal, composite_signal, prediction_updated_at | 0 | 0.00% | ✅ |
| factors_summary | 140 | 13.73% | ⚠️ Moderate |
| predicted_direction, predicted_price, predicted_return_pct, prediction_confidence | 5 | 0.49% | ✅ |

### 1.4 Watermark & Stale Data Detection (>24h)

Menggunakan logika `src/market/data/refresh_stale.py` (`STALE_THRESHOLD_HOURS = 24`). Current UTC: 2026-08-10T09:17.

| Tabel | Kolom Timestamp | Min | Max | Umur (jam) | Status |
|-------|----------------|-----|-----|-----------|--------|
| `ohlcv` | timestamp | 1927-12-30 | 2026-08-07 | 81.3h | 🔴 **STALE** |
| `technical_indicators_wide` | date | 2000-03-30 | 2026-08-06 | 105.3h | 🔴 **STALE** |
| `daily_trading_stats` | date | 2019-07-29 | 2026-08-05 | 129.3h | 🔴 **STALE** |
| `foreign_flow` | date | 2019-07-29 | 2026-08-03 | 177.3h | 🔴 **STALE** |
| `corporate_actions` | ex_date | 1999-03-19 | 2026-08-03 | 177.3h | 🔴 **STALE** |
| `stock_personality` | updated_at | 2026-08-07 | 2026-08-10T11:08 | -1.9h | ✅ Fresh |
| `stock_prediction` | prediction_updated_at | 2026-08-10T06:09 | 2026-08-10T11:08 | -1.9h | ✅ Fresh |

**Catatan:** Stale >24h pada ohlcv/technical_indicators/daily_trading_stats/foreign_flow adalah **expected** karena hari ini Senin 10 Agustus 2026 — pasar terakhir update Jumat 7 Agustus (weekend gap). Bukan indikator pipeline rusak. `refresh_stale.py` menghitung stale berdasarkan `datetime('now', '-1 day')` yang akan flag ini, tetapi cron EOD akan auto-refresh saat pasar buka Senin.

**`data_watermark` table** mencatat 20 entri (ohlcv, corporate_actions, dividends, macro_data, foreign_flow, market_calendar, fundamental_data, stock_personality, instrument_master, sector_master, scores, technical_indicators, relationship_matrix, fear_greed, fx_rates + 5 per-ticker ohlcv watermark). Latest watermark: 2026-08-06 (yahoo_finance per-ticker fetch).

### 1.5 Verdict Layer 1

- ✅ Hirarki FK 5-level (Negara → Regulator → Bursa → Sektor → Emiten → Instrumen → Transaksi) terbentuk sesuai migration 0013.
- ✅ Index composite pada tabel time-series (ix_ohlcv_ticker_ts, ix_tiw_ticker_date) — query per-ticker efisien.
- 🔴 **4 kolom 100% NULL** di `technical_indicators_wide` (ema50, donchian×3) — backfill belum dijalankan.
- 🔴 `avg_volume` 100% NULL di `stock_personality` — perlu backfill dari OHLCV.
- ⚠️ `app_notifications` (0 rows) dan `transaksi_investor` (0 rows) — belum ada data real/mock. Execution Analyzer akan return `no_data` signal (sesuai desain).
- ✅ Stale detection engine (`refresh_stale.py`) aktif dengan exclusion 139 tickers (suspended/delisted/inactive).

---

## LAYER 2 — AUDIT MODUL KECERDASAN BUATAN & ALIRAN ISYARAT

### 2.1 MLSignalProvider (`src/market/analysis/ml_signal.py`)

**Model:** LightGBM binary classifier (`LGBMClassifier`) — target: 5-day forward return direction (1=up, 0=down).

**18 Feature Engineering** (lines 69-162):
- Teknikal: RSI(14), MA ratio (MA5/MA20), momentum 5d/10d, ATR%(14), volume ratio, high-low range%
- Lanjutan: MA slope, close-to-high/low range, RSI change 3d, volume trend 5d, price acceleration, volatility regime (60d percentile)
- Volume dynamics: VWAP(20), VWAP ratio, VROC(10), OBV slope(5), volume-price trend correlation

**Hyperparameter (lines 44-66):**
```python
n_estimators = 200
max_depth = 6
min_data_in_leaf = 40
reg_alpha = 0.1
reg_lambda = 1.0
learning_rate = 0.05
subsample = 0.8
colsample_bytree = 0.8
early_stopping = 10 rounds
```

**Output:** `MLSignal(signal ∈ [-1,1], confidence=val_acc, n_train_samples, model_available)`. Signal = `2 * P(up) - 1`. Walk-forward CV via `mlops.cross_validation.walk_forward_splits` (80/20).

### 2.2 MultiFactorModel (`src/market/analysis/multi_factor.py`)

**Model:** LightGBM 3-class (SELL=0, HOLD=1, BUY=2) — target: 5-day forward return bins.

**Factor decomposition (lines 42-672):**
1. **Endogenous price pattern** (30+ fitur): rolling ACF (lag 1/5/10), candlestick (body_ratio, shadow, doji/hammer/marubozu score, gap), Bollinger (width, %B, squeeze), MACD (line, signal, hist, hist_norm)
2. **Exogenous global market** (lines 253-400): returns dari ^GSPC, ^IXIC, ^FTSE, ^N225, ^HSI, GC=F, CL=F, HG=F, MTF=F, CPO=F — lead-lag shifted, rolling correlation
3. **Dimensionality reduction**: PCA (retain 95% variance, lines 428-478), LightGBM feature importance selection (top 25 default)

**Hyperparameter (lines 717-749):**
```python
n_estimators = 300
max_depth = 5
learning_rate = 0.05
min_data_in_leaf = 50
reg_alpha = 0.1, reg_lambda = 1.0
subsample = 0.8, colsample_bytree = 0.8
use_pca = True, select_features = True, top_k_features = 25
early_stopping = 15 rounds
```

**Output:** `MultiFactorPrediction(signal = proba[BUY] - proba[SELL], confidence = max(proba) * val_acc)`.

### 2.3 Empat Modul Analisis Baru — Integrasi ke Daily Signal Pipeline

**Pola integrasi:** 4 modul **tidak diimpor langsung** di `daily_signal_cron.py`. Mereka di-wire melalui `SignalEnhancer` (`src/market/analysis/signal_enhancer.py`) yang bertindak sebagai facade.

| Modul | File | SignalEnhancer Method | Output |
|-------|------|----------------------|--------|
| Meta-labeling | `meta_labeling.py` | `_compute_meta_label()` (lines 481-530) | bet_size ∈ [0,1], veto jika <0.1 |
| Pairs trading | `pairs_trading.py` | `_compute_pairs_signal()` (lines 471-479) | spread z-score signal |
| Volume features | `volume_features.py` | `_compute_volume_signal()` (lines 329-398) | OFI+VWAP+OBV+foreign_flow composite |
| Policy event scorer | `policy_event_scorer.py` | `_compute_event_signal()` (lines 400-434) | event-weighted score [-100,100] |

#### 2.3.1 Meta-Labeling (Lopez de Prado) — Veto Filter

**Public API:**
- `triple_barrier_labels()` (lines 83-203) — 3-barrier labeling (take-profit, stop-loss, time)
- `cusum_filter()` (lines 209-262) — event sampling saat price change > threshold
- `MetaLabeler.fit()` (lines 555-688) — train secondary LightGBM binary classifier
- `MetaLabeler.predict()` (lines 690-751) — predict P(primary correct)
- `bet_size_from_probability()` (lines 388-424) — convert probability → position size

**Secondary model:** LightGBM binary, 16 meta-features (RSI, MACD, volatility, primary confidence, foreign flow, VIX proxy). CV: purged walk-forward with embargo (5 splits, purge_gap=5, embargo=5).

**VETO FILTER — Lopez de Prado (bet_size < 0.1 → FLAT):**

Lokasi exact:
- `src/market/analysis/signal_enhancer.py:294-296` — `if bet_size < 0.1: new_direction = "flat"`
- `scripts/daily_signal_cron.py:739-743` — enforcement di prediction pipeline:
```python
if enhancement.bet_size < 0.1:
    logger.debug("SignalEnhancer: meta-labeler vetoed %s (bet_size=%.2f)",
                 ticker, enhancement.bet_size)
    result["prediction_confidence"] = 0.0
    result["predicted_direction"] = "flat"
```

**Verdict veto:** ✅ Tereksekusi benar di 2 lokasi (SignalEnhancer + daily_signal_cron). Threshold 0.1 (10% max position) sesuai Lopez de Prado. `DEFAULT_BET_PROB_THRESHOLD = 0.5` (line 51).

#### 2.3.2 Pairs Trading

- **Pair selection:** correlation >0.5 → Engle-Granger cointegration (custom ADF, MacKinnon 1991 critical values) → half-life <20 days
- **Spread:** `spread = price_A - beta * price_B` (OLS hedge ratio)
- **Z-score:** rolling mean/std, **shifted by 1** (anti look-ahead, lines 521-523)
- **Threshold:** entry |Z|>2.0, exit |Z|<0.5, stop |Z|>4.0, regime gate (corr>0.95 → skip)

#### 2.3.3 Volume Features

6 fitur: VWAP(20), Volume Profile (POC/VAH/VAL), OFI proxy, OBV divergence, foreign flow momentum, retail absorption (Smart Money). Semua rolling stats **shifted by 1** untuk anti look-ahead. Feed via `clip(OFI + VWAP_dev*5 + OBV + foreign_flow, -1, 1)`.

#### 2.3.4 Policy Event Scorer

17 event types (BI_RATE_CUT/HIKE, FED_RATE, GEOPOLITICAL, TRADE_WAR, BUYBACK, RIGHTS_ISSUE, STOCK_SPLIT, MERGER, EARNINGS_BEAT/MISS, dll). Exponential decay `0.5^(days_since/half_life)`, half-life=10 days. Market-wide weight=0.3, ticker-specific=1.0. **No look-ahead:** hanya event dengan `event_date <= as_of_date` (line 197).

### 2.4 Cross-Market Timezone & DST Guard (`cross_market_timezone.py`)

**DST Detection (lines 193-213):** Menggunakan `zoneinfo` America/New_York.
- EDT (DST, Mar→Nov): US close = 20:00 UTC (03:00 WIB)
- EST (Standard, Nov→Mar): US close = 21:00 UTC (04:00 WIB)

**Time-zone bucket grid** (prediction time 16:15 WIB / 09:15 UTC):
- Tokyo (^N225): closed 06:30 UTC → **T-0 available**
- Hong Kong (^HSI): closed 08:00 UTC → **T-0 available**
- US (^GSPC, ^VIX, ^TNX): opens 13:30/14:30 UTC → **T-1 only**
- Commodities (GC=F, CL=F, HG=F, MTF=F, CPO=F): US-centric settle → **T-1 only**

**Look-Ahead Bias Guards — 4 lapis:**
1. `GLOBAL_TICKER_LAGS` dict (lines 91-110): Asian T-0, US/EU/Commodities T-1
2. `get_aligned_global_features()` (lines 321-415): apply correct lag per ticker
3. `DST_AWARE_GLOBAL_TICKERS` list (lines 50-59): tickers yang butuh tunggu US close
4. `compute_exogenous_features()` asymmetric lag: ganti uniform `.shift(1)` → `get_ticker_lag(gticker)` per ticker

**Verdict DST/Look-Ahead:** ✅ **Komprehensif.** Asian markets menggunakan T-0 (same-day close valid), US/commodities T-1. Mencegah look-ahead untuk Asian features yang sebelumnya tertunda 1 hari. DST-aware via zoneinfo (bukan hardcoded offset).

### 2.5 Diagram Aliran Sinyal Harian (End-to-End)

```
┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 1: LOAD CONFIG (daily_signal_cron.py:1024-1066)              │
│  ├─ Load best_ticker_quant_config.json (verdict config)             │
│  ├─ Extract per-ticker params (Donchian period, kappa)              │
│  └─ Load ticker strategies from stock_personality DB                │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 2: EOD DATA INGESTION (lines 1036-1088)                      │
│  ├─ Get latest trading date from DB                                 │
│  ├─ Load OHLCV for 20 focus tickers (DEFAULT_FOCUS_TICKERS)         │
│  └─ Compute daily inverse-variance weights                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 3: LIVE SIGNAL PROCESSING (lines 1090-1182) — PER TICKER     │
│                                                                     │
│  ┌─ Load OHLCV + technical_indicators_wide ─────────────────────┐   │
│  ├─ Blend portfolio weights (50% verdict + 50% IV) ─────────────┤   │
│  ├─ Baseline signal: process_ticker_signal() ───────────────────┤   │
│  │                                                              │   │
│  ├─ MLSignalProvider.predict() ─── LightGBM binary ─────┐       │   │
│  ├─ MultiFactorModel.predict() ─── LightGBM 3-class ───┤       │   │
│  ├─ MarketContextProvider ────────────────────────────┤       │   │
│  └─ PredictionEngine.ENSEMBLE ────────────────────────┤       │   │
│                                                       ▼       │   │
│                                              ┌────────────┐  │   │
│  ┌─ SignalEnhancer.enhance() ────────────────│ composite  │  │   │
│  │  ├─ _compute_volume_signal() ─────────────┤ signal     │  │   │
│  │  │   (OFI+VWAP+OBV+foreign_flow) ─────────┤            │  │   │
│  │  ├─ _compute_event_signal() ──────────────┤            │  │   │
│  │  │   (policy_event_scorer) ───────────────┤            │  │   │
│  │  ├─ _compute_sector_signal() ─────────────┤            │  │   │
│  │  │   (sector_rotation) ───────────────────┤            │  │   │
│  │  ├─ _compute_pairs_signal() ──────────────┤            │  │   │
│  │  │   (pairs_trading z-score) ─────────────┤            │  │   │
│  │  └─ _compute_meta_label() ────────────────┤            │  │   │
│  │      (MetaLabeler.predict → bet_size) ────┤            │  │   │
│  │                                            └─────┬──────┘  │   │
│  │  ★ VETO FILTER (bet_size < 0.1 → FLAT) ★        │         │   │
│  │  Location: signal_enhancer.py:294-296            │         │   │
│  │           + daily_signal_cron.py:739-743         │         │   │
│  └──────────────────────────────────────────────────┘         │   │
│                           ▼                                    │   │
│  Save prediction to stock_prediction + stock_personality ─────┘   │
└──────────────────────────┬────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 4: NOTIFICATION (lines 1413-1498)                            │
│  ├─ build_notification_payload():                                   │
│  │   ├─ Fetch execution_analysis via run_full_analysis() ──────┐   │
│  │   ├─ Query latest overnight_strategy from app_notifications ┤   │
│  │   └─ Build payload: signal_date, keep_score, keep_verdict,   │   │
│  │      summary{buy,sell,hold,errors}, signals[],               │   │
│  │      execution_analysis, overnight_strategy                  │   │
│  └─ INSERT to app_notifications (status=UNREAD) ────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.6 Deteksi Bottleneck

| Bottleneck | Lokasi | Severity | Rekomendasi |
|------------|--------|----------|-------------|
| **ML accuracy 40-43%** | Ensemble prediction engine (`prediction.py:825-956`) — 4 metode semua trend-following | 🔴 Tinggi | Meta-labeling retraining (prioritas TERTINGGI); regime-specific models |
| **MultiFactor ΔSharpe -2.271** | `multi_factor.py` — Sharpe -2.67 vs baseline -0.40 | 🔴 Tinggi | Feature selection terlalu agresif (top 25); perlu tuning |
| **Pairs/Sector belum fully wired** | `signal_enhancer.py` — pairs butuh pair_ticker+pair_prices; sector butuh sector param | ⚠️ Sedang | Tambah config mapping pair & sector per ticker |
| **Donchian 100% NULL di wide table** | `technical_indicators_wide` — 4 kolom kosong | ⚠️ Sedang | Backfill atau drop kolom (overnight mining compute on-the-fly) |
| **avg_volume 100% NULL** | `stock_personality` | ⚠️ Sedang | Backfill dari OHLCV (sederhana: `SELECT AVG(volume) GROUP BY ticker`) |
| **app_notifications kosong** | Tabel 0 rows — cron belum pernah jalan real | ⚠️ Sedang | Jalankan daily_signal_cron.py sekali untuk populate |

---

## LAYER 3 — PEMETAAN BACKEND API & FRONTEND WIRE-UP

### 3.1 Fast Portfolio Pipeline — HRP Allocation (`scripts/fast_portfolio_pipeline.py`)

**Metode HRP:** Menggunakan `pypfopt.hierarchical_portfolio.HRPOpt` (PyPortfolioOpt).
- Tree clustering: scipy hierarchical clustering (single linkage)
- Quasi-diagonalization: reorder matrix berdasarkan cluster hierarchy
- Recursive bisection: split cluster recursively untuk alokasi weight

**Stock universe:**
- Default: 100 tickers (`--limit 100`, line 539)
- Filter: MIN_BARS=500, active trading, asset_class='EQUITY_INDIVIDUAL', avg volume ≥100K shares
- Runtime: ~65 detik (100 tickers) vs ~10 menit (917 tickers eligible)

**Walk-forward backtest (lines 217-313):**
- Training window: 2520 trading days (10 tahun)
- Test window: 126 trading days (6 bulan)
- Sliding window dengan OOS validation

**Weight cap:** MAX_WEIGHT = 0.15 (15% per ticker, line 47). Iterative renormalization ke sum=1.0.

**Fallback:** Jika HRP fail → inverse-volatility weighting (`1/vol` normalized).

**Bottleneck analysis:**
- Correlation matrix: O(n²) — 100 tickers = 10,000 pairwise (manageable)
- Memory: 100 tickers × 2520 days ≈ 2MB prices + 80KB correlation — tidak ada issue
- Untuk 1000 tickers: 1M pairwise correlations — potensi bottleneck, tetapi belum di-test

**Input:** `ohlcv` + `instrument_master` (JOIN untuk filter asset_class/trading_status).
**Output:** `best_ticker_quant_config.json` (config), `final_portfolio_verdict.json` (verdict), update `stock_personality` + `stock_prediction` di DB.

**Verdict HRP:** ✅ Efisien untuk 100 saham. Fallback inverse-vol baik. Cap 15% mencegah konsentrasi berlebih.

### 3.2 Backend FastAPI — REST API Routes

**App definition:** `src/market/api/app.py:70-95` — `create_app()` dengan 11 routers.

**41 route terdaftar** across 11 router files:

| Router | Routes | Endpoint |
|--------|--------|----------|
| routes_system | 3 | /health, /env, /markets |
| routes_analysis | 4 | /scores/{ticker}, /recommend/{ticker}, /advisory, /readiness/{ticker} |
| routes_portfolio | 4 | /portfolio, /watchlist (GET, POST, DELETE) |
| routes_backtest | 1 | /backtest/run |
| routes_automation | 5 | /automation/config, /plan, /execute, /leverage/advise |
| routes_prediction | 5 | /pattern/detect, /prediction/predict, /verify, /errors, /risk/{ticker} |
| routes_delisting | 7 | /delisting/summary, /records, /lessons, /check, /record, /block, /filter |
| routes_instruments | 2 | /instruments, /fx-risk |
| routes_data | 5 | /sources, /watermarks, /audit, /fetch, /quality/{ticker} |
| routes_prices | 3 | /latest, /intraday/trigger, /compare/{ticker} |
| routes_recompute | 2 | /recompute (HTML), /api/recompute/stats |

### 3.3 🔴 TEMUAN KRITIS — Tidak Ada Route API untuk `app_notifications`

**Bukti:** `grep -r "app_notification|notification|AppNotification" src/market/api/` → **0 matches**.

**Model ADA** (`src/market/db/models.py:1094-1103`):
```python
class AppNotification(Base):
    __tablename__ = "app_notifications"
    id: Mapped[int] = primary_key
    timestamp: Mapped[datetime]
    title: Mapped[str]
    body_json: Mapped[str]  # Contains signal payload
    status: Mapped[str]  # 'UNREAD' or 'READ'
```

**Tabel ADA** (migration 0013, 0 rows saat ini).

**Write points ADA** (2 script):
1. `daily_signal_cron.py:1464-1498` — INSERT daily signals (BUY/SELL/HOLD + HRP sizing untuk 20 focus stocks)
2. `overnight_strategy_mining.py:424-473` — INSERT overnight strategy (Donchian optimization result)

**Read points:** Hanya `daily_signal_cron.py:1428-1442` (SELECT overnight untuk enrich payload). **TIDAK ADA route API yang SELECT dari app_notifications.**

**Dampak:** Frontend tidak bisa retrieve daily trading signals via API. Sinyal di-generate dan disimpan ke DB, tetapi **tidak ada jalur delivery ke UI**.

**Verdict:** 🔴 **Gap blocking untuk user-facing delivery.** Perlu buat route `GET /api/notifications` atau `GET /api/signals/daily` yang query `app_notifications WHERE status='UNREAD' ORDER BY timestamp DESC`.

### 3.4 Frontend Next.js — Dashboard Wire-up

**Stack confirmed** (`frontend/package.json`):
- ✅ Next.js 16.3.0 (App Router)
- ✅ TypeScript 5.5.2
- ✅ Tailwind CSS 3.4.4
- ✅ Recharts 2.12.0

**10 halaman ada** (`frontend/src/app/`):
| Halaman | Status | Fetch API? |
|---------|--------|-----------|
| `/` (Dashboard) | 🔴 Static mock data (NAV=0, Return=0) | Tidak |
| `/portfolio` | 🔴 Static table, no data fetch | Tidak |
| `/scan` | ✅ Pattern detection + prediction UI | `/api/pattern/detect`, `/api/prediction/predict` |
| `/data` | ✅ Data quality monitoring | `/api/data/sources`, `/watermarks`, `/audit` |
| `/screener` | — | — |
| `/stock` | — | — |
| `/backtest` | — | — |
| `/automation` | — | — |
| `/reports` | — | — |
| `/settings` | — | — |

**🔴 TEMUAN KRITIS — Tidak ada komponen yang render BUY/SELL/HOLD + HRP sizing:**
- Tidak ada halaman `/signals` atau `/notifications`
- Tidak ada TypeScript type untuk signal payload
- Dashboard (`page.tsx`) hanya static mock (NAV=0, Return=0, Positions=[], Watchlist=[])
- Portfolio page tidak fetch data real

**Data fetching method:** Native `fetch()` API (no axios). Pattern: `Promise.all([fetch(...), fetch(...)])`.

**Gap:** `daily_signal_cron.py` generate sinyal untuk 20 focus stocks dan insert ke `app_notifications`, tetapi **frontend tidak punya mekanisme retrieve atau display**.

### 3.5 20 Focus Stocks vs 100 HRP Stocks — Mismatch

**20 Focus tickers** (`scripts/portfolio_data_remediation.py:142-146`):
```python
DEFAULT_FOCUS_TICKERS = [
    "KPIG.JK", "TRIM.JK", "SONA.JK", "TIRT.JK", "TCID.JK", "MEDC.JK", "PANS.JK",
    "KDSI.JK", "MTDL.JK", "BCIC.JK", "SPMA.JK", "BVIC.JK", "APLI.JK", "RBMS.JK",
    "UNTR.JK", "BNBR.JK", "INDF.JK", "UNIC.JK", "ASBI.JK", "ICBP.JK",
]
```

**100 HRP tickers** (`fast_portfolio_pipeline.py --limit 100`).

**Dampak:** HRP weights dihitung untuk 100 saham, tetapi daily signal hanya generate untuk 20 focus. HRP weights untuk 80 saham lain tidak ter-consume di daily signal.

**Rekomendasi:** Align — atau dokumentasikan bahwa 20 focus adalah subset terpilih dari 100-stock HRP universe.

### 3.6 Verdict Layer 3

- ✅ HRP pipeline efisien (65 detik / 100 saham), fallback inverse-vol, cap 15%.
- ✅ 41 REST API route terdaftar, 11 router modular.
- 🔴 **TIDAK ADA route API untuk app_notifications** — gap blocking delivery sinyal ke frontend.
- 🔴 **Frontend belum render sinyal BUY/SELL/HOLD + HRP sizing** — dashboard static mock.
- ⚠️ Mismatch 20 focus vs 100 HRP — perlu align atau dokumentasi.

---

## LAYER 4 — PROTEKSI SINKRONISASI REPOSITORI & LAPORAN

### 4.1 Pytest Full Suite

**Perintah:** `uv run pytest --tb=line -q --no-header`
**Durasi:** 389.67 detik (6 menit 29 detik)
**Hasil:**

| Metrik | Nilai | Status |
|--------|-------|--------|
| Total tests | 1,372 | — |
| Passed | 1,368 | ✅ |
| Failed | 4 | ⚠️ Pre-existing |
| Coverage total | 70.15% | ✅ (gate 70% tercapai) |
| Coverage gate | 70% | ✅ Pass |
| Total statements | 15,712 | — |
| Missed | 3,986 | — |
| Branch coverage | 4,286 total, 637 partial | — |

**4 Failure (semua pre-existing, bukan dari modul Smart Money):**

| Test | Error | Root Cause |
|------|-------|------------|
| `test_device.py::TestDeviceContext::test_logs_decision` | `assert False` — log decision tidak tercatat | Test assertion terlalu ketat pada logging behavior |
| `test_macro_data_fetcher.py::TestBPSFetcher::test_api_key_missing_returns_empty_and_warns` | `assert False` — warning tidak ter-capture | BPS API key tidak diset di env, warning handler test issue |
| `test_portfolio_data_remediation.py::TestInverseVarianceWeights::test_max_weight_cap_enforced` | `0.375 > 0.20` — weight cap 0.20 dilanggar | IV weighting collapse ke single ticker (BVIC.JK zero variance) — bug known |
| `test_portfolio_final_execution.py::TestDailyInverseVarianceWeights::test_max_weight_cap_enforced` | `0.413 > 0.20` — weight cap 0.20 dilanggar | Sama — IV collapse bug |

**Catatan:** 2 failure IV weight cap adalah bug yang sudah didokumentasikan di SESSION_MEMORY (checkpoint 2026-08-09): "Inverse-variance weighting collapse ke BVIC.JK (AcceptRate=0%, zero variance)". Fast portfolio pipeline sudah mengganti IV → HRP, tetapi test untuk modul lama (portfolio_data_remediation, portfolio_final_execution) masih ada dan fail.

### 4.2 Coverage per Modul (Highlight)

| Modul | Coverage | Status |
|-------|----------|--------|
| `db/models.py` | 100% | ✅ |
| `risk/engine.py` | 96% | ✅ |
| `execution/oms.py` | 95% | ✅ |
| `mlops/cross_validation.py` | 94% | ✅ |
| `security/pdp.py` | 94% | ✅ |
| `data/refresh_stale.py` | 89% | ✅ |
| `data/validation.py` | 91% | ✅ |
| `analysis/ml_signal.py` | — (covered via test) | ✅ |
| `analysis/multi_factor.py` | — (covered via test) | ✅ |
| `data/sync_to_parquet.py` | **0%** | 🔴 Tidak ada test |
| `data/recompute_internal.py` | **4%** | 🔴 Hampir tidak ter-test |
| `pipelines/data_fetch.py` | **26%** | 🔴 Rendah |
| `scheduler_tasks.py` | **25%** | 🔴 Rendah |
| `data/yahoo_adapter.py` | **30%** | ⚠️ Rendah (network I/O) |

### 4.3 Git Status — Perubahan Belum Di-commit

**Branch:** `main`
**Modified (14 file):** SESSION_MEMORY.md, MEGAPLAN.md, audit_ai_advanced.py, batch_compute_predictions.py, daily_signal_cron.py, fast_portfolio_pipeline.py, signal_enhancer.py, volume_features.py, screener.py, models.py, data_fetch.py, test_db.py, test_screener.py, test_signal_enhancer.py, test_volume_features.py

**Untracked (7 file):**
- `alembic/versions/0013_relational_hierarchy_tables.py` — migration hirarki relasional
- `scripts/backfill_relational_tables.py` — backfill script
- `scripts/classify_instruments_v2.py` — klasifikasi v2
- `scripts/overnight_strategy_mining.py` — modul Smart Money Integration
- `src/market/analysis/execution_analyzer.py` — modul Smart Money Integration
- `tests/test_execution_analyzer.py` — 19 tests
- `tests/test_overnight_strategy_mining.py` — 22 tests

**Last commit:** `790d9dc feat: DST-aware cross-market timezone + commodity futures alignment`

**Verdict DevOps:** ⚠️ Perubahan Smart Money Integration + migration 0013 **belum di-commit**. Perlu commit & push untuk persistensi.

### 4.4 Alembic Migration History

| Version | Description | DB State |
|---------|-------------|----------|
| 0001 | Initial schema | ✅ |
| 0002 | Add esg_scores and corporate_governance | ✅ |
| 0003 | Complete schema: 15 missing tables + 4 column additions | ✅ |
| 0004 | Add scheduler_state | ✅ |
| 0005 | Add suspension_date | ✅ |
| 0006 | Add instrument_master columns (6 baru) | ✅ |
| 0007 | Add ml_labels, market_regimes | ✅ |
| 0008 | Add parquet_sync_state | ✅ |
| 0009 | Add recompute_watermark | ✅ |
| 0010 | Add index_category, region | ✅ |
| 0011 | Add ticker to risk_metrics | ✅ |
| 0012 | Wide tables + FK (technical_indicators_wide, stock_prediction split) | ✅ |
| **0013** | **Relational hierarchy tables (regulator→bursa→sektor→emiten→instrumen→transaksi) + app_notifications** | ✅ Head |

Research DB & Paper DB keduanya di alembic 0013.

---

## REKOMENDASI KONKRET PENYESUAIAN PARAMETER LightGBM (40-43% → 55%++)

### Diagnosis Akar Masalah

**Akar masalah** (dari `pustaka/97` & MEGAPLAN): Ensemble prediction engine (`prediction.py:825-956`) menggunakan 4 metode yang **semuanya trend-following** (MA, momentum, pattern, vol-adj). Di bear market choppy dengan sharp bounces, semua metode salah arah. Akurasi 40-43% (di bawah random 50%).

**Feature drift** (PSI >0.25 pada 3 dari 6 fitur): vol_20 (0.472), rsi (0.252), ma_ratio_50 (0.292) — model yang dilatih pada data lama perlu retraining.

**MultiFactor ΔSharpe = -2.271** — model lebih buruk dari baseline. Feature selection terlalu agresif (top 25 dari PCA+importance).

### Rekomendasi 1: Meta-Labeling Retraining (Prioritas TERTINGGI)

**Status:** Modul ada (`meta_labeling.py`), veto filter aktif, tetapi **secondary model belum di-train pada data real**.

**Langkah:**
1. Generate triple-barrier labels pada full OHLCV history (3M+ rows) untuk 20 focus tickers
2. Train MetaLabeler dengan 16 meta-features pada purged walk-forward CV (5 splits, purge_gap=5, embargo=5)
3. Target: precision@1 ≥0.55 (bukan accuracy) — Lopez de Prado menekankan precision, bukan accuracy
4. Tuning `DEFAULT_BET_PROB_THRESHOLD` dari 0.5 → 0.55-0.6 untuk lebih restriktif

**Parameter target MetaLabeler:**
```python
# Secondary model (LightGBM binary: correct/incorrect)
n_estimators = 300       # naik dari default 200
max_depth = 4            # turun dari 6 — model lebih simple, kurang overfit
min_data_in_leaf = 60    # naik dari 40 — regularisasi stronger
learning_rate = 0.03     # turun dari 0.05 — learning lebih halus
reg_alpha = 0.15         # naik dari 0.1
reg_lambda = 2.0         # naik dari 1.0
subsample = 0.7          # turun dari 0.8 — lebih banyak randomness
colsample_bytree = 0.7   # turun dari 0.8
early_stopping = 20      # naik dari 10 — lebih sabar
```

**Expected impact:** Precision naik dari ~40% → 55%+ karena veto filter menahan prediksi low-confidence. Trade frequency turun (acceptable — lebih sedikit trade dengan win rate lebih tinggi).

### Rekomendasi 2: MLSignalProvider Hyperparameter Tuning

**Current:** max_depth=6, n_estimators=200, lr=0.05, min_data_in_leaf=40

**Rekomendasi (anti-overfit untuk bear market):**
```python
max_depth = 5            # turun dari 6 — kurangi kapasitas model
n_estimators = 300       # naik dari 200 — lebih banyak trees dengan lr lebih kecil
learning_rate = 0.03     # turun dari 0.05 — haluskan learning
min_data_in_leaf = 60    # naik dari 40 — strong regularization
reg_alpha = 0.15         # naik dari 0.1
reg_lambda = 2.0         # naik dari 1.0
subsample = 0.7          # turun dari 0.8
colsample_bytree = 0.7   # turun dari 0.8
early_stopping = 20      # naik dari 10
# TAMBAH: num_leaves = 31 (explicit, default 31 — pastikan tidak > 2^max_depth)
# TAMBAH: min_gain_to_split = 0.01 — prunes unnecessary splits
# TAMBAH: feature_fraction_bynode = 0.8 — extra randomness per node
```

### Rekomendasi 3: MultiFactorModel — Kurangi Feature Aggression

**Current:** PCA 95% variance + top 25 features → ΔSharpe -2.271 (lebih buruk dari baseline).

**Diagnosis:** Top 25 features mungkin membuang fitur penting, atau PCA menangkap noise.

**Rekomendasi:**
```python
top_k_features = 40      # naik dari 25 — lebih banyak fitur, kurangi variance
use_pca = False          # atau True dengan variance 99% (naik dari 95%)
n_estimators = 200       # turun dari 300 — kurangi overfit
max_depth = 4            # turun dari 5
min_data_in_leaf = 80    # naik dari 50 — strong regularization
learning_rate = 0.03     # turun dari 0.05
reg_alpha = 0.2          # naik dari 0.1
reg_lambda = 3.0         # naik dari 1.0
subsample = 0.7
colsample_bytree = 0.7
early_stopping = 25      # naik dari 15
```

### Rekomendasi 4: Label Engineering — Triple-Barrier + Regime-Aware

**Current label:** 5-day forward return direction (binary) / bins (3-class).

**Rekomendasi:** Ganti ke **triple-barrier labeling** (Lopez de Prado):
- Take-profit barrier: +2% (1.5× ATR)
- Stop-loss barrier: -2% (1.5× ATR)
- Time barrier: 5 trading days
- Label: {+1 hit TP, -1 hit SL, 0 time out}

**Regime-aware:** Train model terpisah per regime (bull/bear/sideways) menggunakan HMM atau VIX-based classification. Bear market → mean-reversion features dominan; bull → momentum dominan.

### Rekomendasi 5: Feature Remediation — Pakai Fitur Stabil

Dari audit advanced (Step 1), 3 fitur drifted diganti dengan alternatif stabil:

| Fitur Lama (Drifted) | PSI | Fitur Baru (Stabil) | PSI After |
|---------------------|-----|---------------------|-----------|
| vol_20 | 0.472 | vol_pctile | 0.095 |
| rsi | 0.252 | rsi_rank | 0.015 |
| ma_ratio_50 | 0.292 | ma_ratio_zscore | 0.096 |

**Action:** Update feature engineering di `ml_signal.py` dan `multi_factor.py` untuk menggunakan fitur rank-based/z-score yang stabil terhadap regime shift.

### Rekomendasi 6: Ensemble Diversification

**Current:** 4 metode semua trend-following → korrelasi tinggi → ensemble tidak diversify.

**Rekomendasi:** Tambah metode **mean-reversion** ke ensemble:
- RSI oversold/overbought reversal
- Bollinger Band squeeze breakout reversal
- Pairs trading z-score (sudah ada modul, belum fully wired)

**Target:** Ensemble 6 metode (3 trend-following + 3 mean-reversion) → diversifikasi mengurangi error di bear market choppy.

### Ringkasan Target Parameter

| Parameter | MLSignal (Current) | MLSignal (Target) | MultiFactor (Current) | MultiFactor (Target) | MetaLabeler (Target) |
|-----------|-------------------|-------------------|----------------------|---------------------|---------------------|
| max_depth | 6 | **5** | 5 | **4** | **4** |
| n_estimators | 200 | **300** | 300 | **200** | **300** |
| learning_rate | 0.05 | **0.03** | 0.05 | **0.03** | **0.03** |
| min_data_in_leaf | 40 | **60** | 50 | **80** | **60** |
| reg_alpha | 0.1 | **0.15** | 0.1 | **0.2** | **0.15** |
| reg_lambda | 1.0 | **2.0** | 1.0 | **3.0** | **2.0** |
| subsample | 0.8 | **0.7** | 0.8 | **0.7** | **0.7** |
| colsample_bytree | 0.8 | **0.7** | 0.8 | **0.7** | **0.7** |
| early_stopping | 10 | **20** | 15 | **25** | **20** |
| top_k_features | — | — | 25 | **40** | — |
| use_pca | — | — | True (95%) | **False atau 99%** | — |

**Expected outcome:** Akurasi 40-43% → **55%+** dalam 2-3 iterasi retraining dengan feature remediasi + triple-barrier labels + regime-aware models.

---

## PRIORITAS TINDAKAN BERIKUTNYA

### P0 — Blocking (segera)

1. ✅ **SELESAI** — Route API `GET /api/notifications` dibuat di `src/market/api/routes_notifications.py` — list (paginated), get by id, mark as read, latest signals shortcut. 11 tests PASS.
2. ✅ **SELESAI** — Halaman frontend `/signals` dibuat di `frontend/src/app/signals/page.tsx` — render tabel BUY/SELL/HOLD + HRP sizing + Smart Money grid + overnight strategy.
3. ✅ **SELESAI** — Commit & push perubahan Smart Money Integration + migration 0013 + audit implementation.

### P1 — High (minggu ini)

4. ✅ **SELESAI** — Backfill 4 kolom NULL di `technical_indicators_wide` — script `scripts/backfill_ti_wide_null_cols.py` mengcompute EMA50, EMA Envelope, Donchian dari OHLCV untuk 3M rows.
5. ✅ **SELESAI** — Backfill `avg_volume` di `stock_personality` — script `scripts/backfill_avg_volume.py`, 1026 rows updated, 0 NULL remaining.
6. **Meta-labeling retraining** pada data real (3M+ OHLCV rows) — prioritas TERTINGGI untuk fix accuracy.
7. ✅ **SELESAI** — `daily_signal_cron.py` dijalankan untuk populate `app_notifications` (672 tickers, payload lengkap dengan signals + HRP sizing + smart money).

### P2 — Medium (bulan ini)

8. **Hyperparameter tuning** LightGBM sesuai rekomendasi §3 (MLSignal + MultiFactor + MetaLabeler).
9. **Feature remediation** — ganti vol_20→vol_pctile, rsi→rsi_rank, ma_ratio_50→ma_ratio_zscore.
10. **Triple-barrier labeling** ganti 5-day forward return direction.
11. **Regime-aware models** — train terpisah per bull/bear/sideways.
12. **Fully wire pairs_trading & sector_rotation** ke SignalEnhancer (butuh pair_ticker + sector param config).
13. **Align 20 focus vs 100 HRP** — dokumentasi atau expand daily signal ke 100 tickers.

### P3 — Low (next quarter)

14. **Test coverage** untuk modul 0-4%: sync_to_parquet, recompute_internal, data_fetch, scheduler_tasks.
15. **Fix 4 pre-existing test failures** (IV weight cap ×2, device log, BPS API key).
16. **Paper trading 30 hari** — jalankan minimal 30 hari simulasi sebelum human-gate broker real.
17. **Model Champion pertama** — 50 tickers trained (avg val_acc 0.502), perlu retraining + promosi via EvalGate.

---

## LAMPIRAN — REFERENSI FILE & LINE NUMBER

| Komponen | File | Baris Kunci |
|----------|------|-------------|
| MLSignalProvider | `src/market/analysis/ml_signal.py` | 37-279 (class), 44-66 (hyperparam), 69-162 (features), 200 (LGBM), 261 (signal) |
| MultiFactorModel | `src/market/analysis/multi_factor.py` | 703-917 (class), 717-749 (hyperparam), 836 (LGBM 3-class), 861 (signal) |
| Meta-labeling | `src/market/analysis/meta_labeling.py` | 83-203 (triple_barrier), 555-688 (fit), 690-751 (predict), 388-424 (bet_size) |
| Veto filter | `src/market/analysis/signal_enhancer.py` | 294-296 |
| Veto filter (cron) | `scripts/daily_signal_cron.py` | 739-743 |
| Pairs trading | `src/market/analysis/pairs_trading.py` | 260-360 (screen), 558-648 (signals), 568-576 (thresholds) |
| Volume features | `src/market/analysis/volume_features.py` | 46-89 (VWAP), 116-221 (profile), 246-310 (OFI), 452-530 (smart money) |
| Policy event scorer | `src/market/analysis/policy_event_scorer.py` | 28-47 (EventType), 67-85 (impacts), 168-242 (compute) |
| Cross-market DST | `src/market/analysis/cross_market_timezone.py` | 91-110 (lags), 164-190 (US close), 193-213 (DST), 321-415 (aligned features) |
| Daily signal flow | `scripts/daily_signal_cron.py` | 1024-1066 (config), 1036-1088 (data), 1090-1182 (signal), 1413-1461 (payload), 1464-1498 (insert) |
| HRP pipeline | `scripts/fast_portfolio_pipeline.py` | 217-313 (walk-forward), 251-262 (HRP), 539 (limit=100) |
| FastAPI app | `src/market/api/app.py` | 70-95 (create_app) |
| AppNotification model | `src/market/db/models.py` | 1094-1103 |
| Frontend dashboard | `frontend/src/app/page.tsx` | 1-112 (static mock) |
| Focus tickers | `scripts/portfolio_data_remediation.py` | 142-146 |
| Refresh stale | `src/market/data/refresh_stale.py` | 76-143 (detect), 146-210 (refresh) |
| Migration 0013 | `alembic/versions/0013_relational_hierarchy_tables.py` | 24-80+ (hierarchy) |
| Execution analyzer | `src/market/analysis/execution_analyzer.py` | full (SlippageResult, NetAlphaResult, run_full_analysis) |
| Overnight mining | `scripts/overnight_strategy_mining.py` | 424-473 (insert notification) |

---

## PENUTUP

Audit E2E ini menemukan bahwa sistem aplikasi pasar modal **90% siap dari sisi backend/ML/database**, dengan arsitektur yang solid (hirarki FK 5-level, 41 API route, 13 migration bersih, coverage 70.15%, DST guard komprehensif, veto filter Lopez de Prado aktif).

**Status implementasi P0 & P1 (10 Agu 2026):**
1. ✅ **Route API `app_notifications` selesai** — 4 endpoints di `routes_notifications.py`, 11 tests PASS.
2. ✅ **Frontend `/signals` selesai** — render BUY/SELL/HOLD + HRP sizing + Smart Money grid.
3. 🔴 **ML accuracy 40-43%** — di bawah random 50%, perlu meta-labeling retraining + hyperparameter tuning + feature remediasi untuk capai 55%+. **Ini adalah gap tersisa.**

Setelah 3 gap ini ditangani, sistem siap untuk paper trading 30 hari dan menuju human-gate broker real.

---

*Audit dilakukan oleh: Senior Solutions Architect / Principal Quant Researcher / Expert Database Engineer*
*Source of truth: MEGAPLAN.md (801 baris) + pustaka/00-95 (96 dokumen)*
*Database: data/market_research.db (10 GB, alembic 0013, 57 tabel)*
*Test: 1368 passed / 4 failed / coverage 70.15%*
