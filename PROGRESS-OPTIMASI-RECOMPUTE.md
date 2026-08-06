# Progress: Optimasi Incremental Recompute + ML Pipeline

> **Tanggal:** 7 Agustus 2026
> **Status:** Phase 1 (Vectorize + Watermark) selesai, belum di-test full di Windows karena lambat.
> **Lanjut di:** Linux (`/opt/lampp/htdocs/market/`)

---

## Ringkasan Eksekusi

### Phase 1: Vectorize + Watermark (SELESAI — perlu test di Linux)

#### 1A. Migration 0009 — `recompute_watermark` table
- **File:** `alembic/versions/0009_recompute_watermark.py`
- **Status:** Created + migrated (sudah di-run di Windows)
- **Schema:**
  ```sql
  CREATE TABLE recompute_watermark (
      ticker TEXT PRIMARY KEY,
      table_name TEXT PRIMARY KEY,
      last_processed_date DATE,
      last_ohlcv_date DATE,
      rows_processed INTEGER,
      updated_at DATETIME
  );
  CREATE INDEX ix_recompute_watermark_table ON recompute_watermark(table_name);
  ```

#### 1B. Model `RecomputeWatermark` di `models.py`
- **File:** `src/market/db/models.py` (line ~858)
- **Status:** Added, setelah `SchedulerState`, sebelum `ParquetSyncState`

#### 1C. Bounded Load + Watermark Helpers di `recompute_internal.py`
- **File:** `src/market/data/recompute_internal.py`
- **Functions added:**
  - `_load_ohlcv_df_since(session, ticker, since_date, buffer_days=0)` — load OHLCV hanya dari `since_date - buffer_days` ke latest. Mengurangi data yang dimuat dari ~1000 rows → ~250 rows per ticker.
  - `_get_watermark(session, ticker, table_name)` — baca watermark dari DB
  - `_set_watermark(session, ticker, table_name, last_date, rows)` — upsert watermark
- **Imports added:** `date` dari `datetime`, `RecomputeWatermark` dari `models`

#### 1D. Vectorized `recompute_ml_labels` (MAIN OPTIMIZATION)
- **File:** `src/market/data/recompute_internal.py` (line ~758)
- **Before:** Python loop per tanggal per horizon = ~4M iterations → **56 menit**
- **After:** Numpy vectorized barrier check (loop over 21 offsets, not 1000+ dates) + bulk insert via `executemany` → **14.8 detik** (227x speedup)
- **Key changes:**
  1. `tp_first_hit` / `sl_first_hit` — numpy array, diisi dengan loop over `k in range(1, horizon+1)` (max 21 iterations, bukan 1000+)
  2. `ret` — vectorized: `close[horizon:] / close[:n-horizon] - 1) * 100`
  3. `vol_adj_ret` — vectorized dengan `np.where` + `np.errstate` untuk suppress warning
  4. Bulk insert: batch list of dicts, `session.execute(text(INSERT), batch)` setiap 5000 rows
  5. Per-ticker watermark: cek `_get_watermark()` → bounded load via `_load_ohlcv_df_since()` → delete labels within max_horizon of watermark → recompute only new dates → `_set_watermark()`
  6. **Fallback:** jika watermark belum ada tapi labels sudah ada (first incremental run), cek `MAX(date) FROM ml_labels WHERE ticker = :t` sebagai fallback watermark

#### 1E. Bounded Load + Watermark untuk `fear_greed`
- **File:** `src/market/data/recompute_internal.py` (line ~571)
- Bounded load: `_load_ohlcv_df_since(session, IHSG_TICKER, wm, buffer_days=50)` (MA20 butuh 20 hari)
- Watermark fallback: cek `MAX(tanggal) FROM fear_greed` jika watermark belum ada
- Update watermark di akhir fungsi

#### 1F. Bounded Load + Watermark untuk `market_regimes`
- **File:** `src/market/data/recompute_internal.py` (line ~1015)
- Bounded load: `_load_ohlcv_df_since(session, IHSG_TICKER, wm, buffer_days=250)` (MA200 butuh 200 hari)
- Watermark fallback: cek `MAX(date) FROM market_regimes` jika watermark belum ada
- Update watermark di akhir fungsi

### Test Results (Windows)

#### Test 1: Vectorized ml_labels incremental
- **Hasil:** 14.8 detik, 33,249 rows, 963 watermarks tracked
- **Before:** 9,853,286 rows, max_date=2026-08-05
- **After:** 9,853,232 rows, max_date=2026-08-05
- **Delta:** -54 rows (expected: penghapusan label dalam 21 hari watermark + recompute)
- **Note:** Ada numpy RuntimeWarning (divide by zero) yang sudah di-fix dengan `np.errstate(divide="ignore", invalid="ignore")`
- **Error di test script:** SQL syntax error di query label distribution (LIMIT before GROUP BY) — bukan issue di kode recompute, hanya di test script

#### Test 2: Full run_all_recompute incremental
- **Status:** Dibatalkan user karena Windows terlalu lambat untuk 4 snapshot tables (technical_indicators, scores, relationship_matrix, stock_personality yang masih full recompute)
- **Test script:** `_tmp_test_all_incremental.py` — siap di-run di Linux

---

## Yang Perlu Dilakukan di Linux

### 1. Test Phase 1 end-to-end
```bash
cd /opt/lampp/htdocs/market
python _tmp_test_all_incremental.py
```
Atau test per-fungsi:
```bash
python _tmp_test_vectorized.py
```

### 2. Verifikasi migration sudah applied
```bash
python -m alembic current
# Should show: 0009 (head)
```

### 3. Jika migration belum applied di Linux
```bash
python -m alembic upgrade head
```

### 4. Test kedua run incremental (verifikasi watermark bekerja)
Run kedua kali harus jauh lebih cepat karena watermark sudah ada:
```bash
python _tmp_test_all_incremental.py  # run pertama: seed watermark
python _tmp_test_all_incremental.py  # run kedua: should be near-instant for ml_labels
```

---

## File yang Dimodifikasi

| File | Perubahan |
|------|-----------|
| `alembic/versions/0009_recompute_watermark.py` | NEW — migration untuk watermark table |
| `src/market/db/models.py` | Added `RecomputeWatermark` model |
| `src/market/data/recompute_internal.py` | Added `_load_ohlcv_df_since`, `_get_watermark`, `_set_watermark`; vectorized `recompute_ml_labels`; bounded load + watermark untuk `fear_greed` dan `market_regimes` |

## File Test (sementara, bisa dihapus setelah selesai)

| File | Tujuan |
|------|--------|
| `_tmp_test_vectorized.py` | Test vectorized ml_labels incremental |
| `_tmp_test_all_incremental.py` | Test full run_all_recompute incremental |
| `_tmp_test_incremental.py` | Test lama dari sesi sebelumnya |

---

## TODO Selanjutnya

### Phase 1E: Test vectorized + watermark end-to-end (di Linux)
- Run `_tmp_test_all_incremental.py` di Linux
- Verifikasi: run kedua harus near-instant untuk ml_labels (watermark sudah ada)
- Verifikasi: label distribution masih sama dengan full recompute

### Phase 2: Build Feature Store (SQLite-based)
- `feature_definitions` table: nama, formula, version, dependencies
- `feature_values` table: ticker, date, feature_name, value, version
- Compute features vectorized dari OHLCV
- Enabler untuk LightGBM + backtest (eliminasi training-serving skew)
- Lihat: `pustaka/94-aiml-knowledge-architecture-analysis.md` untuk arsitektur

### Phase 3: HMM Regime (hmmlearn.GaussianHMM rolling)
- Ganti heuristic `recompute_market_regimes` dengan HMM
- Input: IHSG daily returns (~1000 rows, sangat cepat)
- K=3 states (bull/bear/sideways)
- Rolling fit setiap 63 trading days, hanya data [0, t] (no look-ahead)
- Library: `hmmlearn` (`pip install hmmlearn`)
- Tidak bergantung recompute pipeline 986 tickers

### Phase 4: LightGBM Walk-Forward Training (GPU cuda:1)
- Feature matrix: join dari feature store (Phase 2)
- Labels: dari `ml_labels` (triple-barrier, horizon=5 atau 10)
- Walk-forward: expanding window, purged K-fold, embargo 21 hari
- LightGBM config: 800 rounds, lr=0.03, max_depth=6, 31 leaves, early_stopping=50
- GPU: wajib `cuda:1` (5-20x speedup)
- Lihat: `pustaka/23-*.md` untuk teori triple-barrier

### Phase 5: Backtest dengan Triple-Barrier Labels
- Input: ml_labels + feature matrix
- Walk-forward: train on [0,T], test on [T+1, T+H], slide
- Realistic costs: slippage, spread, broker fee, impact cost
- Lihat: `pustaka/88-gap-teori-vs-praktek.md` untuk gap analysis

### Phase 6: Update RINGKASAN-DATA-ML.md
- Update §12 "Incremental Recompute Architecture" dengan detail watermark + vectorized
- Tambah §13 "Feature Store Architecture" (setelah Phase 2)
- Tambah §14 "HMM Regime Detection" (setelah Phase 3)
- Tambah §15 "Walk-Forward Training" (setelah Phase 4)
- Tambah §16 "Backtest Strategy" (setelah Phase 5)

---

## Arsitektur Watermark

```
┌─────────────────────────────────────────────────────────────┐
│                    recompute_watermark                        │
│  ticker  | table_name      | last_processed_date | rows     │
│ ---------+-----------------+---------------------+----------│
│  AAPL    | ml_labels       | 2026-08-05          | 33249    │
│  ^JKSE   | fear_greed      | 2026-08-05          | 365      │
│  ^JKSE   | market_regimes  | 2026-08-05          | 365      │
│  ...     | ...             | ...                 | ...      │
└─────────────────────────────────────────────────────────────┘

Incremental flow per ticker:
1. _get_watermark(ticker, table) → wm
2. _load_ohlcv_df_since(ticker, wm - buffer_days) → bounded OHLCV
3. DELETE rows where date > (wm - max_horizon)  -- only for ml_labels
4. Compute labels/indicators for dates > (wm - max_horizon)
5. Bulk INSERT new rows
6. _set_watermark(ticker, table, last_date, row_count)

Buffer days per table:
  ml_labels:      max_horizon(21) + atr_period(14) + 10 = 45 days
  fear_greed:     50 days (MA20 + safety)
  market_regimes: 250 days (MA200 + safety)
```

## Key Metrics

| Metric | Before (Full) | After (Incremental) | Speedup |
|--------|---------------|---------------------|---------|
| ml_labels recompute | ~56 menit | 14.8 detik | 227x |
| Data loaded per ticker | ~1000 rows | ~250 rows | 4x |
| Python iterations | ~4M (per date) | ~84 (per offset) | 47,619x |
| Insert method | ORM add() | executemany() | ~10x |
