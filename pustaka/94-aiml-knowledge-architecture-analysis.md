# Arsitektur Pengetahuan AI/ML: Analisis Database Pasar Modal

> **Audit data aktual untuk persiapan model AI/ML/Predictive Analytics, structured around 5 pillars.**

---

## 1. Konteks

Dokumen ini mencatat hasil audit database `market_research.db` (~6 GB, 40 tabel) untuk persiapan arsitektur pengetahuan AI/ML. Berbeda dengan dokumen pustaka lain yang berisi teori, dokumen ini berisi **temuan data aktual** dan **tindakan implementasi** yang sudah dilakukan.

Sumber: `pustaka/23-machine-learning-trading.md` (teori ML), `pustaka/84-new-data-arrival-processing-pipeline.md` (pipeline labeling), `pustaka/58-feature-store-engineering-pipeline.md` (feature store).

---

## 2. 5 Pilar Arsitektur Pengetahuan

### Pilar 1: Asset Mapping & Timing Mechanism

**Status data:**
- `market_registry`: 8 bursa terdaftar (XIDX, XNYS, XNAS, XHKG, XTKS, XLON, XEUC, XFRA) dengan timezone dan jam perdagangan.
- `instrument_master`: ~1000+ instrumen, mayoritas equity IDX, ada komoditas (GC=F, CL=F), forex (IDR=X), index (^GSPC, ^HSI, dll).
- `market_calendar`: **HANYA IDX** — bursa global belum memiliki kalender.
- `OHLCV`: 1008 ticker, data harian 1997-07-02 s/d 2026-08-06, ~2.9M rows.

**Gap yang diidentifikasi:**
- Market calendar global (non-IDX) belum tersedia → **PRIORITAS 6**.
- Timezone overlap IDX-global tercermin di `pustaka/36-gap-data-timezone-global-idx.md` tapi belum ada kode yang mengautomasi penyesuaian.

**Tindakan:**
- Script `scripts/generate_global_calendar.py` dibuat untuk generate kalender XNYS, XNAS, XHKG, XTKS, XLON, XEUC (2020-2027).

### Pilar 2: Correlation & Intermarket Analysis

**Status data:**
- `relationship_matrix`: Schema sudah mendukung multi-window (kolom `window`), tapi **hanya window=60** yang dihitung.
- `REFERENCE_ASSETS` di `analysis/relationship.py`: 13 aset referensi (7 index global + 5 macro proxy + IHSG).
- `MacroEconomicEngine` di `analysis/macro.py`: menggunakan US10Y, Gold, Oil, USD/IDR untuk klasifikasi regime.

**Gap yang diidentifikasi:**
- Relationship matrix hanya window=60 → tidak ada multi-window untuk validasi stabilitas korelasi.
- DXY (US Dollar Index) belum di-fetch sebagai macro series.

**Tindakan:**
- `recompute_relationship_matrix` dimodifikasi untuk multi-window: **30/60/90/180/360 hari**.
- DXY ditambahkan ke macro fetch pipeline.

### Pilar 3: Price Driver Indicators

**Status data:**
- `technical_indicators`: ~29M rows, 6 indikator (MACD, ATR, MA, BB, ADX, RSI).
- `fundamental_data`: HANYA **1 snapshot per ticker** (dari `fetch_fundamental.py` yang fetch `yfinance.Ticker.info`). Tidak ada history quarterly.
- `macro_data`: 5 series dari FRED (DGS10, VIXCLS, CPIAUCSL, FEDFUNDS, UNRATE) — **hanya 1 baris per series** (masalah fetch pipeline).
- `foreign_flow` & `broker_flow`: Data aliran dana asing dan broker tersedia.
- `scores`: 6 engine scores (technical, fundamental, macro, global, relationship, sentiment).

**Gap yang diidentifikasi:**
- Fundamental data tidak ada quarterly history → **PRIORITAS 2**.
- Macro data Indonesia (BI Rate, CPI, GDP) tidak ada → **PRIORITAS 3**.
- yfinance macro series (DXY, GOLD, OIL, US10Y, USD/IDR) hanya 1 baris → **PRIORITAS 4**.

**Tindakan:**
- Script `scripts/backfill_fundamental_quarterly.py` dibuat untuk fetch ~8 quarter history dari `yfinance.Ticker.quarterly_financials/balance_sheet/cashflow`.
- Script `scripts/fetch_macro_all.py` dibuat untuk fetch:
  - Indonesia macro dari FRED CSV (INTDSBIDM193N=BI Rate, IDNCPIALLMINMEI=CPI, NGDPRXDCID=GDP).
  - Global macro dari yfinance full history (^TNX, ^VIX, GC=F, CL=F, IDR=X, DX-Y.NYB).
- Pipeline `data_fetch.py` macro fetch diperbaiki: MACRO_SERIES diganti dengan MACRO_YF_TICKERS mapping yang benar.

### Pilar 4: Anomaly & Systemic Risk Detection

**Status data:**
- `trading_suspensions`: Data suspensi dengan alasan dan tipe.
- `instrument_master`: `delisting_risk_score` dan `delisting_risk_reason` tersedia.
- `external_events`: Kategori geopolitik, perang, bencana alam, pandemi, ESG.
- `policy_events`: Kategori moneter, regulasi OJK/BEI, fiskal, politik.
- `fear_greed`: Indeks ketakutan & keserakahan (dihari dari IHSG momentum/volatility/volume).

**Gap yang diidentifikasi:**
- Tidak ada tabel `market_regimes` untuk regime-aware ML → **PRIORITAS 7**.
- Regime detection HMM belum diimplementasi (teori di `pustaka/23 §5`).

**Tindakan:**
- Tabel `market_regimes` ditambahkan ke `models.py` dengan kolom: date, regime (bull/bear/sideways/crisis), vix_level, fear_greed_label, foreign_flow_trend.
- Fungsi `recompute_market_regimes` diimplementasi dengan heuristic rules (MA50/MA200 crossover + volatility + VIX + Fear&Greed + foreign flow).
- HMM-based detection sebagai roadmap enhancement (butuh `hmmlearn` library).

### Pilar 5: Data Structuring for AI/ML

**Status data:**
- `ai_weights`: Tabel untuk weight optimization results.
- `stock_personality`: Klasifikasi kepribadian saham (active trader, balanced, volatile speculator, dll).
- `pattern_analysis`: Pola yang terdeteksi (volatility, trend, RSI, volume spike, breakout, crossover).
- `ml_signal.py`: LightGBM signal provider dengan walk-forward CV — tapi **tidak ada triple-barrier labels**.

**Gap yang diidentifikasi:**
- Triple-barrier labels (López de Prado) tidak ada di database → **PRIORITAS 1**.
- Feature store belum terstruktur (teori di `pustaka/58` tapi belum ada kode).

**Tindakan:**
- Tabel `ml_labels` ditambahkan ke `models.py` dengan kolom: ticker, date, horizon, direction (up/down/static), barrier_hit, return_pct, vol_adjusted_return.
- Fungsi `recompute_ml_labels` diimplementasi dengan:
  - 4 horizon: 1, 5, 10, 21 hari.
  - ATR14-based barriers: TP = +2×ATR, SL = -2×ATR.
  - First-barrier-hit logic (TP/SL/time).
  - Volatility-adjusted return.

---

## 3. Implementasi yang Telah Dilakukan

### 3.1 Model Database Baru

**File:** `src/market/db/models.py`

- `MLLabel` — triple-barrier labels untuk ML training (pustaka/23 §4, pustaka/84 Stage 6).
- `MarketRegime` — regime harian (bull/bear/sideways/crisis) untuk regime-aware ML (pustaka/23 §5).

**Migration:** `alembic/versions/0007_add_ml_labels_market_regimes.py`

### 3.2 Recompute Pipeline

**File:** `src/market/data/recompute_internal.py`

- `recompute_ml_labels(session)` — compute triple-barrier labels untuk semua IDX tickers × 4 horizons.
- `recompute_market_regimes(session)` — compute regime harian dari IHSG + VIX + Fear&Greed + foreign flow.
- `recompute_relationship_matrix(session)` — **dimodifikasi** dari single-window (60) ke multi-window (30/60/90/180/360).
- `run_all_recompute` — ditambah ml_labels dan market_regimes.

**File:** `src/market/pipelines/recompute.py`
- Pipeline recompute sekarang menjalankan 7 fungsi (sebelumnya 5).

### 3.3 Data Fetch Pipeline

**File:** `src/market/pipelines/data_fetch.py`

- `MACRO_SERIES` (FRED names) diganti dengan `MACRO_YF_TICKERS` mapping ke yfinance ticker yang benar.
- `on_fetch_macro_requested` di-rewrite untuk fetch US10Y (^TNX), VIX (^VIX), GOLD (GC=F), CRUDE_OIL (CL=F), USD_IDR (IDR=X), DXY (DX-Y.NYB).

### 3.4 Script Baru

| Script | Fungsi |
|--------|--------|
| `scripts/backfill_fundamental_quarterly.py` | Fetch ~8 quarter fundamental history dari yfinance untuk semua IDX tickers |
| `scripts/fetch_macro_all.py` | Fetch Indonesia macro (FRED) + global macro full history (yfinance) |
| `scripts/generate_global_calendar.py` | Generate market calendar untuk 6 bursa global (2020-2027) |

---

## 4. Cara Menjalankan

```bash
# 1. Run migration untuk create new tables
ENV=research alembic upgrade head

# 2. Backfill fundamental quarterly history
ENV=research uv run python scripts/backfill_fundamental_quarterly.py

# 3. Fetch macro data (Indonesia + global)
ENV=research uv run python scripts/fetch_macro_all.py

# 4. Generate global market calendar
ENV=research uv run python scripts/generate_global_calendar.py --all-years

# 5. Recompute all internal tables (including new ml_labels & market_regimes)
ENV=research uv run python -m market.data.recompute_internal
```

---

## 5. Roadmap Selanjutnya

1. **HMM-based regime detection** — ganti heuristic rules dengan `hmmlearn` untuk 3-4 state HMM pada IHSG returns.
2. **Feature store** — implementasi centralized feature definitions sesuai `pustaka/58`.
3. **Purged k-fold CV** — implementasi López de Prado's purged cross-validation untuk ML training.
4. **Meta-labeling** — secondary model yang memprediksi precision dari primary model (pustaka/23 §4.3).
5. **Commodity-to-stock mapping** — integrasi `pustaka/91` ke relationship matrix (CPO→AALI, coal→PTBA, dll).
6. **Sentiment history backfill** — migrate sentiment data dari parquet backup (`pustaka/90`).

---

## 6. Cross-Reference

- Teori ML labeling: `pustaka/23-machine-learning-trading.md#4-labeling`
- Teori regime detection: `pustaka/23-machine-learning-trading.md#5-regime-detection`
- Pipeline data arrival: `pustaka/84-new-data-arrival-processing-pipeline.md#stage-6`
- Feature store: `pustaka/58-feature-store-engineering-pipeline.md`
- Intermarket analysis: `pustaka/35-multi-asset-cross-market-analysis.md`
- Gap data & timezone: `pustaka/36-gap-data-timezone-global-idx.md`
- Faktor pasar modal: `pustaka/89-faktor-pasar-modal-analisis-implementasi.md`
- Komoditas IDX: `pustaka/91-komoditas-spesifik-idx.md`
- Multi-market system: `pustaka/92-multi-market-multi-asset-trading-system.md`
