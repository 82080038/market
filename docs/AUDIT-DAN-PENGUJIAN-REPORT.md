# Laporan Audit Database PostgreSQL & Pengujian Modul Prediksi S2

**Tanggal:** 11 Agustus 2026  
**Database:** PostgreSQL `market` (Unix socket, peer auth)  
**Engine:** SQLAlchemy + psycopg2  

---

## TAHAP 1: Audit Kelengkapan Database

### Ringkasan Eksekutif

Audit dijalankan menggunakan `src/market/data/db_completeness_audit.py` yang memeriksa:
- Row count per tabel
- Date range (min/max timestamp)
- Null rate per kolom (>50% ditandai)
- Column diff: ORM vs PostgreSQL actual schema
- Empty tables (0 rows)
- Missing tables (ada di ORM, tidak ada di PG)

### Tabel dengan Data Lengkap (OK)

| Tabel | Rows | Date Range | Status |
|-------|------|------------|--------|
| `stock_prices` | 3,230,675 | 1927-12-31 → 2026-08-11 | OK (partitioned) |
| `stock_prices_default` | 2,962,296 | — | OK (default partition) |
| `foreign_flow` | 1,253,802 | 2019-07-29 → 2026-08-03 | OK |
| `market_sessions` | 8,307 | — | OK |
| `macroeconomic_indicators` | 4,527 | 1947 → 2026-08-10 | OK |
| `broker_transactions` | 345,104 | — | OK |
| `corporate_actions` | 5,974 | — | OK |
| `instruments` | 1,066 | — | OK |
| `fear_greed` | 3,110 | 2018-02-01 → 2026-08-11 | OK |
| `fundamental_data` | 1,107 | 2024-12-31 → 2026-08-10 | Partial (see below) |
| `events` | 298 | — | OK |
| `exchanges` | 18 | — | OK |
| `macro_data` | 139 | 2010-01-01 → 2025-07-16 | Stale (see below) |
| `news_sentiment` | 628 | 2026-07-29 → 2026-08-11 | OK |

### Data Gaps Teridentifikasi

#### Gap 1: `stock_prices` XIDX — 4 hari missing (FIXED)
- **Sebelum:** Latest = 2026-08-07
- **Sesudah:** Latest = 2026-08-10 (Aug 8 = Jumat non-trading/weekend, Aug 10 = Senin)
- **Aksi:** yfinance delta fetch untuk 1032 tickers → 925 rows inserted

#### Gap 2: `macro_data` — stale >1 tahun (PARTIALLY FIXED)
- **Sebelum:** Latest = 2025-07-16
- **Sesudah:** World Bank API fetch → 32 rows baru (GDP growth + forex reserves 2025)
- **Sisa:** Inflation CPI & Real Interest Rate gagal (World Bank API timeout)

#### Gap 3: `technical_indicators` — 0 rows (EMPTY)
- **Penyebab:** Tabel ada di PG tetapi belum pernah diisi dari PostgreSQL backend
- **Dampak:** S2 prediction engine tidak memiliki pre-computed indicators
- **Solusi:** Jalankan `recompute_technical_indicators` dari `market.analysis.recompute`

#### Gap 4: `market_regimes` — 0 rows (EMPTY)
- **Penyebab:** Sama dengan Gap 3 — recompute belum dijalankan di PG
- **Solusi:** Jalankan `recompute_market_regimes`

#### Gap 5: `stock_personality` — 0 rows (EMPTY)
- **Penyebab:** Batch compute predictions belum dijalankan di PG
- **Solusi:** Jalankan `scripts/batch_compute_predictions.py`

#### Gap 6: `satellite_*` tables — 0 rows (EMPTY)
- **Penyebab:** Tidak ada sumber data satelit yang terintegrasi
- **Status:** Tidak dapat diisi tanpa API satelit (NOAA, Sentinel) — low priority

#### Gap 7: `stock_prices.vwap` — 100% NULL
- **Penyebab:** yfinance tidak menyediakan VWAP untuk daily bars
- **Dampak:** Market factors module menggunakan VWAP ratio sebagai feature
- **Solusi:** Hitung VWAP dari OHLCV: `VWAP = sum(close * volume) / sum(volume)` per hari

#### Gap 8: `fundamental_data` — 61.79% NULL `dividend_yield`
- **Penyebab:** Banyak emiten tidak membagikan dividen
- **Status:** Wajar — tidak semua emiten IDX membayar dividen

#### Gap 9: `fundamental_data` — 4 kolom ORM missing di PG
- **Kolom:** `car`, `loan_to_deposit`, `nim`, `npl_ratio`
- **Penyebab:** Kolom bank-specific belum di-add di PG schema
- **Solusi:** `ALTER TABLE fundamental_data ADD COLUMN ...`

### Tabel yang Tidak Ada di PG (MISSING dari audit)

Tabel berikut ada di ORM models tetapi tidak ditemukan di PG:

| Tabel | Penyebab | Prioritas |
|-------|----------|-----------|
| `ohlcv` | Diganti dengan `stock_prices` (partitioned) | N/A — sudah ada |
| `instrument_master` | Diganti dengan `instruments` | N/A — sudah ada |
| `sector_master` | Diganti dengan `sektor` (dropped) | Low |
| `market_registry` | Diganti dengan `exchanges` | N/A |
| `ml_labels` | 9.85M rows di SQLite, belum migrated | Medium |
| `scores` | Diganti dengan `stock_personality`? | Low |
| `news` | Diganti dengan `news_sentiment` | N/A |
| `relationship_matrix` | Belum migrated | Medium |
| `valuation_cache` | Belum migrated | Low |
| `policy_events` | Belum migrated | Medium |
| `external_events` | Belum migrated | Medium |
| `trading_suspensions` | Belum migrated | Low |
| `astronacci_cycles` | Belum migrated | Low |

---

## TAHAP 2: Pengujian Modul Prediksi S2

### Setup

- **Script:** `scripts/test_prediction_validation.py`
- **Engine:** `PredictionEngine` (ensemble: MA + momentum + pattern + vol-adjusted + market context)
- **Data source:** PostgreSQL `stock_prices` (real data, bukan mock)
- **Tickers tested:** 10 focus tickers (BBCA, BBRI, UNVR, ANTM, MDKA, UNTR, APLI, BCIC, INCO, KRAS)
- **Tests per ticker:** 8 tests × 10 tickers = **80 total tests**

### Test Results: 80/80 PASS

| Test | Deskripsi | Hasil |
|------|-----------|-------|
| `basic_prediction` | Engine menghasilkan prediksi valid (price > 0) | 10/10 PASS |
| `no_data_leakage` | Truncation di as_of = manual truncation (no look-ahead) | 10/10 PASS |
| `nan_handling` | Engine tidak crash pada NaN di close/high | 10/10 PASS |
| `division_by_zero` | Engine tidak crash pada price = 0.0 | 10/10 PASS (after fix) |
| `insufficient_data` | Engine return flat/0.0 untuk <35 bars | 10/10 PASS |
| `consistency` | Same input → same output (deterministic) | 10/10 PASS |
| `temporal_consistency` | Prediction T-30 ≠ T-0 (different data windows) | 10/10 PASS |
| `market_context` | MarketContextProvider terintegrasi dengan PG | 10/10 PASS |

### Bug Ditemukan & Diperbaiki

**Bug:** `ZeroDivisionError` di `PredictionEngine._predict_ensemble`  
**Root cause:** Tidak ada guard untuk `current_price = 0.0` sebelum perhitungan `ret_pct = (predicted_price - price) / price * 100`  
**Fix:** Added zero/negative price guard di `src/market/analysis/prediction.py:254-270` — return safe fallback Prediction (flat, 0.0 confidence)  
**File:** `@/home/petrick/projects/market/src/market/analysis/prediction.py:254-270`

### Data Leakage Assessment

**Status: AMAN (no data leakage)**

Bukti:
1. `_truncate()` method memfilter data `<= as_of` sebelum semua perhitungan
2. Test `no_data_leakage` memverifikasi: prediction dengan truncation = prediction dengan manual truncation (price_diff < 0.50)
3. `MarketContextProvider.get_context()` menggunakan `cutoff = pd.Timestamp(as_of).date()` untuk semua query
4. Exogenous features (USD/IDR, Shanghai) menggunakan `timestamp <= as_of` filter
5. ML signal menggunakan walk-forward CV (train pada data lama, predict pada data baru)

### Sample Predictions (as of 2026-08-10)

| Ticker | Direction | Price | Confidence | Context Confidence |
|--------|-----------|-------|------------|-------------------|
| BBCA.JK | up | 6427.15 | 0.517 | 0.440 |
| BBRI.JK | down | 3105.52 | 0.552 | 0.635 |
| UNVR.JK | up | 1829.85 | 0.575 | 0.489 |
| ANTM.JK | up | 3210.04 | 0.437 | 0.372 |
| MDKA.JK | up | 2974.52 | 0.415 | 0.353 |

---

## TAHAP 3: Data Ingestion Execution

### Rencana & Eksekusi

| Tabel | Gap | Method | Rows Filled | Status |
|-------|-----|--------|-------------|--------|
| `stock_prices` | 4 hari (Aug 8-11) | yfinance delta | 925 | DONE |
| `macro_data` | Stale >1 tahun | World Bank API | 32 | PARTIAL |
| `macroeconomic_indicators` | Up to date | yfinance | 0 | OK |
| `fear_greed` | Up to date | alternative.me | 0 | OK |

### Scripts Created

1. **`scripts/test_prediction_validation.py`** — Skrip uji prediksi S2 (8 tests × N tickers)
2. **`scripts/fill_data_gaps.py`** — Skrip data ingestion (stock_prices, macro, fear_greed)

### Files Modified

1. **`src/market/analysis/prediction.py`** — Fix ZeroDivisionError (zero-price guard)
2. **`src/market/data/db_completeness_audit.py`** — Fix conn.rollback() + None formatting (previous session)
3. **`.env`** — Switch to PostgreSQL (previous session)
4. **`docs/DB-COMPLETENESS-AUDIT.md`** — Full audit report (auto-generated)
5. **`docs/PREDICTION-VALIDATION-REPORT.json`** — Test results JSON (auto-generated)
6. **`docs/DATA-INGESTION-REPORT.json`** — Ingestion report JSON

---

## Rekomendasi Tindak Lanjut

### Prioritas Tinggi
1. **Jalankan recompute pipeline** di PG: `recompute_technical_indicators`, `recompute_market_regimes`, `recompute_scores` — ini akan mengisi `technical_indicators` (0 rows), `market_regimes` (0 rows), `stock_personality` (0 rows)
2. **Migrate `ml_labels`** (9.85M rows) dari SQLite ke PG — diperlukan untuk ML signal precomputed labels
3. **Migrate `relationship_matrix`** dari SQLite ke PG — diperlukan untuk cross-market analysis

### Prioritas Sedang
4. **Add bank-specific columns** di PG: `ALTER TABLE fundamental_data ADD COLUMN npl_ratio NUMERIC(10,4), ADD COLUMN car NUMERIC(10,4), ADD COLUMN nim NUMERIC(10,4), ADD COLUMN loan_to_deposit NUMERIC(10,4)`
5. **Migrate `policy_events` + `external_events`** dari SQLite ke PG — diperlukan untuk PolicyEventScorer
6. **Compute VWAP** dari OHLCV untuk fill 100% NULL vwap column

### Prioritas Rendah
7. **Migrate `astronacci_cycles`** (14K rows) dari SQLite ke PG
8. **Migrate `trading_suspensions`** dari SQLite ke PG
9. **World Bank API retry** untuk inflation CPI & real interest rate (timeout issue)
