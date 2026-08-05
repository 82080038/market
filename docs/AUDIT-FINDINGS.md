# Laporan Audit Aplikasi Pasar Modal

**Tanggal audit:** 5 Agustus 2026 (update pasca-sync GitHub)  
**Repository:** https://github.com/82080038/market.git  
**Path:** `/home/petrick/projects/market`  
**Python:** 3.12 (via uv venv) — target `>=3.11`  
**Node.js:** v20.x

---

## Ringkasan Eksekutif

| Kategori | Status |
|---|---|
| Git sync | ✅ Fast-forward ke `40678fc` berhasil |
| Ruff lint | ✅ All checks passed |
| Mypy type-check | ✅ No issues in 80 source files |
| Pytest | ✅ 691 passed, coverage 83.36% |
| Frontend build | ✅ `npm run build` sukses, 12 halaman |
| Frontend tsc | ✅ No errors |
| npm audit | ⚠️ 3 high severity (postcss & sharp via next) |
| `.env` | ⚠️ Belum dibuat (hanya `.env.example`) |
| Database | ⚠️ `market_live.db` 21 tabel tapi 0 rows; `market_research.db` kosong; `market_paper.db` belum ada |
| Scheduler | ⚠️ 0 tasks terdaftar (skeleton) |
| Model registry | ⚠️ 0 model terdaftar |
| Total bug ditemukan | 2 minor (frontend deps) |
| Total warning | 3 |
| Total issue kode | 4 |

---

## 1. Bug (Test Failure & Logic Errors)

Pasca-sync, seluruh test backend lulus. Bug yang tercatat di audit sebelumnya sudah diperbaiki:

- ✅ `_f()` dan `_s()` di `src/market/data/migrate_parquet.py` sekarang mengembalikan `default` secara langsung.
- ✅ `pyarrow>=15.0` sudah masuk ke `pyproject.toml` dan terpasang di venv.
- ✅ `GlobalMarketEngine.analyze` sudah menghitung `total_ma50 = len(above_ma50) + len(below_ma50)`.
- ✅ `Position.market_value` sudah tidak lagi dead code (dihapus/tersambung ke perhitungan NAV).
- ✅ `MockBroker` reject logic sudah divalidasi ulang di test suite.

### BUG-A: Frontend npm audit — 3 high severity

**File:** `frontend/package-lock.json`  
**Severity:** High  
**Sumber:** `next@15.5.22` membawa `postcss <=8.5.22` dan `sharp <0.35.0`.

**Impact:** XSS via CSS stringification, arbitrary file read via `sourceMappingURL`, dan libvips CVEs.

**Fix:** Upgrade ke Next.js 16.3.0+ (breaking) atau patch transitive deps. Jalankan `npm audit fix --force` lalu verifikasi `npm run build`.

### BUG-B: `market scheduler list` menunjukkan 0 tasks

**File:** `src/market/scheduler.py`, `src/market/cli/main.py`  
**Severity:** Medium  
**Gejala:** Scheduler skeleton belum didaftarkan task nyata.

**Fix:** Registrasi task di startup: EOD fetch, feature store refresh, drift detection, report generation, model retraining.

---

## 2. Warnings

### WARN-01: SQLite connection lifecycle

**Sumber:** `market.db.engine` menggunakan factory `get_engine()` yang membuat engine baru per pemanggilan.

Dampaknya kecil untuk single-user, tapi bisa menyebabkan multiple WAL files dan connection leak jika engine tidak `dispose()`. Konsistenkan penggunaan engine global atau session dependency.

**Fix:** Gunakan single engine singleton, atau pastikan `engine.dispose()` di cleanup test & CLI.

### WARN-02: Scheduler tasks kosong

**Sumber:** `src/market/scheduler.py`, `src/market/cli/main.py`  
**Pesan:** `Total: 0 tasks`

Tidak ada task EOD fetch, model training, atau drift detection yang didaftarkan. Scheduler siap tapi belum terhubung ke business logic.

**Fix:** Daftarkan minimal 4 task: `fetch_eod`, `run_quality_checks`, `refresh_feature_store`, `generate_reports`.

### WARN-03: Dependency sharp install script pending

**Sumber:** `npm install`  
**Pesan:** `1 package has install scripts not yet covered by allowScripts: sharp@0.34.5`

Native dependency `sharp` belum di-approve sehingga install mungkin tidak optimal di environment pembangunan.

**Fix:** Jalankan `npm approve-scripts sharp@0.34.5` atau pertimbangkan downgrade ke sharp tanpa native script jika tidak perlu image optimization.

---

## 3. Code Quality Issues

### ISSUE-01: Watchlist in-memory store

**File:** `src/market/api/app.py`  

```python
_watchlist: list[dict[str, Any]] = []
```

Watchlist disimpan in-memory, hilang saat restart. Model `Watchlist` ada di `src/market/db/models.py` tapi endpoint belum menggunakannya.

**Rekomendasi:** Migrasi CRUD `/api/watchlist` ke DB-backed dengan `Session` dependency. Ini juga memperbaiki portfolio integration.

### ISSUE-02: API Portfolio masih placeholder

**File:** `src/market/api/app.py:304-312`

Endpoint `/api/portfolio` mengembalikan static dict `{"total_nav": 0.0, ...}` tanpa query ke `PortfolioEngine` / DB.

**Rekomendasi:** Sambungkan ke `PortfolioEngine` + `Order`/`Trade` tables. Tampilkan NAV real, posisi, PnL unrealized/realized.

### ISSUE-03: Coverage rendah di modul tertentu

| Modul | Coverage |
|---|---|
| `src/market/cli/main.py` | 44% |
| `src/market/data/migrate_parquet.py` | 32% |
| `src/market/data/yahoo_adapter.py` | 20% |
| `src/market/mlops/training.py` | 56% |
| `src/market/social/reporting.py` | 68% |
| `src/market/social/robo_advisor.py` | 75% |
| `src/market/multi_asset/cross_market.py` | 67% |
| `src/market/multi_asset/validation.py` | 72% |

**Rekomendasi:**
- CLI: tambah integration test untuk `market migrate`, `market scheduler run`, `market model promote`.
- `migrate_parquet` / `yahoo_adapter`: test dengan fixture parquet kecil & mock yfinance.
- `training.py`: mock torch/LightGBM untuk testing pipeline tanpa GPU.
- `reporting.py`: test export CSV/Excel/PDF.

### ISSUE-04: Tidak ada `.env` file

Hanya `.env.example` yang ada. Aplikasi berjalan default `research`, broker mock, GPU `cuda:1`.

**Rekomendasi:** Copy `.env.example` ke `.env`, set `ENV=paper`, dan pastikan path parquet & device sesuai mesin.

### ISSUE-05: `save_ohlcv` sudah memakai `r.timeframe`

**File:** `src/market/data/storage.py`

`tf = getattr(r, "timeframe", "1d")` sudah diterapkan. Issue lama **terselesaikan**, tetapi perlu test untuk timeframe non-`1d`.

---

## 4. Data Parquet — Struktur

### Lokasi: `/media/petrick/Parquet/trading_data/` (read-only, milik project global)

| Path | Jumlah | Skema |
|---|---|---|
| `raw/*.parquet` | 971 file ticker | timestamp, open, high, low, close, adjusted_close, volume, dividends, splits, ticker, asset_class, exchange, timeframe, source, ingested_at |
| `raw/ohlcv/` | 27 file (2000-2026) | kode, tanggal, open, high, low, close, adj_close, volume, created_at, updated_at |
| `raw/fundamental/` | 1 file (836 rows) | id, kode, periode, revenue, net_profit, total_equity, eps, book_value_per_share, npm, revenue_growth, profit_growth, created_at |
| `raw/foreign_flow/` | 1 file (464 rows) | id, tanggal, beli, jual, net, created_at |
| `raw/macro/` | 1 file (379 rows) | id, periode, suku_bunga, inflasi, gdp_growth, kurs_usd, created_at |
| `raw/stock_personality/` | 1 file (11 rows) | id, kode, profile_date, avg_daily_volatility, ... |
| `archive/tables/` | 28 file parquet | Berbagai skema termasuk ohlcv (2.9M rows), instrument_master, corporate_actions, dividends, macro_data, dll. |
| `raw/` subfolders lain | 50+ folder | ai_alerts, ai_auto_trade, ai_correlation, ai_portfolio, ai_scores, backtest_result, blind_forecast, broker_flow, chart_patterns, commodity, corporate_action, corporate_governance, data_fetch_log, di_ohlcv_daily, esg_scores, event_external, fear_greed_index, global, ihsg, indikator_teknikal, kebijakan_regulasi, ml_config, mm_exchange, mm_instrument, mm_issuer, mm_listing, mm_security, multi_asset, notifications, pattern_analysis, portfolio, price_alerts, saham, saham_historical, sektor, sentiment, sqlite_backup, sqlite_global_market_data, sqlite_instruments, sqlite_macro_data, sqlite_ohlcv, stock_ipo, strategy_config, technical, trade_journal, trader_saldo, training_log, transaksi |

### Status Database Lokal

| Database | Tabel | Rows | Catatan |
|---|---|---|---|
| `data/market_research.db` | — | — | Belum dimigrate |
| `data/market_paper.db` | — | — | Belum dibuat |
| `data/market_live.db` | 21 tabel | 0 | Sudah dimigrate, data belum diisi |

### Catatan migrasi:
- `migrate_parquet.py` membaca dari `archive/tables/` (28 file parquet dengan skema normalized).
- `raw/` berisi data mentah dengan skema berbeda (kolom Indonesia: `kode`, `tanggal`, `beli`, `jual`).
- Skema `archive/tables/ohlcv.parquet` cocok ekspektasi migrasi.
- **Belum ada data yang tersedia di SQLite lokal** — aplikasi saat ini berjalan dengan mock/synthetic data di banyak endpoint.

---

## 5. Rekomendasi Prioritas Perbaikan

### Prioritas Tinggi (segera):
1. **Buat `.env` dari `.env.example`** — set `ENV=paper` untuk memulai paper trading.
2. **Migrate & seed `market_research.db` dan `market_paper.db`** — jalankan `market migrate` untuk kedua environment.
3. **Migrasi data parquet ke SQLite** — jalankan `market data migrate-parquet` (atau script setara) dari `archive/tables/`.
4. **Perbaiki 3 high severity frontend vulnerabilities** — upgrade Next.js / patch `postcss` dan `sharp`.

### Prioritas Sedang:
5. **Register scheduler tasks** — EOD fetch, quality check, feature store refresh, drift detection, report generation.
6. **Wire-up `/api/portfolio` dan `/api/watchlist` ke database** — ganti placeholder & in-memory store.
7. **Naikkan test coverage modul low-coverage** — CLI commands, parquet migration, yahoo adapter, training pipeline.
8. **Implementasikan paper trading 30 hari** — seed portfolio cash, jalankan sinyal harian, catat PnL & trade ledger.

### Prioritas Rendah:
9. **Model champion pertama** — latih baseline LSTM/LightGBM di Paper setelah data cukup, daftarkan ke model registry.
10. **Robo-advisor integration** — hubungkan goal-based recommendations ke portfolio & watchlist.
11. **Social/copy trading (paper-only)** — pastikan leaderboard hanya untuk paper, tidak untuk live.
12. **Documentation polish** — user manual, runbooks, dan changelog.
