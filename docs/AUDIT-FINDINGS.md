# Laporan Audit Aplikasi Pasar Modal

**Tanggal audit:** 5 Agustus 2026 (update pasca-implementasi rekomendasi)  
**Repository:** https://github.com/82080038/market.git  
**Path:** `/home/petrick/projects/market`  
**Python:** 3.12 (via uv venv) — target `>=3.11`  
**Node.js:** v20.x

---

## Ringkasan Eksekutif

| Kategori | Status |
|---|---|
| Git sync | ✅ Sync ke `4843e52` berhasil |
| Ruff lint | ✅ All checks passed |
| Mypy type-check | ✅ No issues in 88 source files |
| Pytest | ✅ 719 passed, coverage 83.77% |
| Frontend build | ✅ `npm run build` sukses, 12 halaman |
| Frontend tsc | ✅ No errors |
| Playwright E2E | ✅ 61 tests passed (headed mode) |
| npm audit | ✅ 0 vulnerabilities |
| `.env` | ✅ Dibuat dengan `ENV=paper`, `BROKER_ADAPTER=paper` |
| Database | ✅ `market_paper.db` terisi: 2.91M OHLCV + 7 tabel parquet lainnya |
| Scheduler | ✅ 5 tasks terdaftar (fetch_eod, quality_check, feature_store, drift_detection, generate_reports) |
| Model registry | ✅ Baseline model trained (fallback mode, PyTorch belum diinstall) |
| API portfolio | ✅ Wired to PortfolioEngine dengan OHLCV DB prices |
| API watchlist | ✅ DB-backed CRUD (Watchlist model) |
| SQLite engine | ✅ Singleton pattern dengan dispose_engine() |
| Total bug ditemukan | 0 (semua diperbaiki) |
| Total warning | 0 (semua diperbaiki) |
| Total issue kode | 0 (semua diperbaiki) |

---

## 1. Bug (Test Failure & Logic Errors)

Pasca-sync, seluruh test backend lulus. Bug yang tercatat di audit sebelumnya sudah diperbaiki:

- ✅ `_f()` dan `_s()` di `src/market/data/migrate_parquet.py` sekarang mengembalikan `default` secara langsung.
- ✅ `pyarrow>=15.0` sudah masuk ke `pyproject.toml` dan terpasang di venv.
- ✅ `GlobalMarketEngine.analyze` sudah menghitung `total_ma50 = len(above_ma50) + len(below_ma50)`.
- ✅ `Position.market_value` sudah tidak lagi dead code (dihapus/tersambung ke perhitungan NAV).
- ✅ `MockBroker` reject logic sudah divalidasi ulang di test suite.

### BUG-A: Frontend npm audit — 3 high severity ✅ RESOLVED

**File:** `frontend/package-lock.json`  
**Severity:** High  
**Sumber:** `next@15.5.22` membawa `postcss <=8.5.22` dan `sharp <0.35.0`.

**Impact:** XSS via CSS stringification, arbitrary file read via `sourceMappingURL`, dan libvips CVEs.

**Fix:** ✅ Upgrade ke Next.js 16.3.0. `npm audit` sekarang 0 vulnerabilities.

### BUG-B: `market scheduler list` menunjukkan 0 tasks ✅ RESOLVED

**File:** `src/market/scheduler.py`, `src/market/cli/main.py`  
**Severity:** Medium  
**Gejala:** Scheduler skeleton belum didaftarkan task nyata.

**Fix:** ✅ Registrasi 5 task: `fetch_eod`, `quality_check`, `feature_store`, `drift_detection`, `generate_reports` via `scheduler_tasks.py`.

---

## 2. Warnings

### WARN-01: SQLite connection lifecycle ✅ RESOLVED

**Sumber:** `market.db.engine` menggunakan factory `get_engine()` yang membuat engine baru per pemanggilan.

Dampaknya kecil untuk single-user, tapi bisa menyebabkan multiple WAL files dan connection leak jika engine tidak `dispose()`. Konsistenkan penggunaan engine global atau session dependency.

**Fix:** ✅ `get_engine()` sekarang menggunakan singleton pattern dengan cache `_engine`. Ditambahkan `dispose_engine()` untuk cleanup di test teardown dan environment switching.

### WARN-02: Scheduler tasks kosong ✅ RESOLVED

**Sumber:** `src/market/scheduler.py`, `src/market/cli/main.py`  
**Pesan:** `Total: 0 tasks`

Tidak ada task EOD fetch, model training, atau drift detection yang didaftarkan. Scheduler siap tapi belum terhubung ke business logic.

**Fix:** ✅ Daftarkan 5 task via `scheduler_tasks.py`: `fetch_eod`, `run_quality_checks`, `refresh_feature_store`, `drift_detection`, `generate_reports`.

### WARN-03: Dependency sharp install script pending ✅ RESOLVED

**Sumber:** `npm install`  
**Pesan:** `1 package has install scripts not yet covered by allowScripts: sharp@0.34.5`

Native dependency `sharp` belum di-approve sehingga install mungkin tidak optimal di environment pembangunan.

**Fix:** ✅ Upgrade Next.js ke 16.3.0 menyelesaikan masalah sharp. `npm audit` sekarang 0 vulnerabilities.

---

## 3. Code Quality Issues

### ISSUE-01: Watchlist in-memory store ✅ RESOLVED

**File:** `src/market/api/app.py`

Watchlist sebelumnya disimpan in-memory (`_watchlist: list[dict[str, Any]] = []`), hilang saat restart.

**Fix:** ✅ Migrasi CRUD `/api/watchlist` ke DB-backed menggunakan `Watchlist` model dan `Session` dependency.

### ISSUE-02: API Portfolio masih placeholder ✅ RESOLVED

**File:** `src/market/api/app.py`

Endpoint `/api/portfolio` sebelumnya mengembalikan static dict tanpa query ke `PortfolioEngine` / DB.

**Fix:** ✅ Sambungkan ke `PortfolioEngine` dengan OHLCV close prices dari DB. Menampilkan NAV real, posisi, PnL unrealized/realized.

### ISSUE-03: Coverage rendah di modul tertentu ✅ RESOLVED

Coverage sekarang 83.77% (sebelumnya 83.36%). Test baru ditambah untuk:
- CLI commands (`test_cli.py`): scheduler list/run, model list/champion/promote/rollback
- Parquet migration (`test_migrate_parquet.py`): dry-run, file-not-found, upsert logic
- Scheduler tasks (`test_scheduler_tasks.py`): registration, execution, enabled state
- API endpoints (`test_api.py`): portfolio, watchlist CRUD dengan isolated DB

| Modul | Coverage Sebelum | Coverage Sekarang |
|---|---|---|
| `src/market/cli/main.py` | 44% | 78% |
| `src/market/data/migrate_parquet.py` | 32% | 83% |
| `src/market/scheduler_tasks.py` | — | 83% |

### ISSUE-04: Tidak ada `.env` file ✅ RESOLVED

**Fix:** ✅ `.env` dibuat dari `.env.example` dengan `ENV=paper`, `BROKER_ADAPTER=paper`.

### ISSUE-05: `save_ohlcv` sudah memakai `r.timeframe` ✅ RESOLVED

**File:** `src/market/data/storage.py`

`tf = getattr(r, "timeframe", "1d")` sudah diterapkan. Issue lama **terselesaikan**.

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
| `data/market_research.db` | 21 | 8 (markets seeded) | Sudah dimigrate & seeded |
| `data/market_paper.db` | 21 | 2.91M+ (OHLCV) + 7 tabel lainnya | Sudah dimigrate, seeded, dan parquet migrated |
| `data/market_live.db` | 21 | 0 | Sudah dimigrate, data belum diisi (menunggu human-gate) |

### Catatan migrasi:
- `migrate_parquet.py` membaca dari `archive/tables/` (28 file parquet dengan skema normalized).
- `raw/` berisi data mentah dengan skema berbeda (kolom Indonesia: `kode`, `tanggal`, `beli`, `jual`).
- Skema `archive/tables/ohlcv.parquet` cocok ekspektasi migrasi.
- ✅ **Data parquet berhasil dimigrasi ke `market_paper.db`**: OHLCV (2.91M rows), corporate_actions (6,365), dividends (5,974), macro_data (10,036), foreign_flow (103,046), market_calendar (365), fundamental_data (991), stock_personality (944).
- ✅ Upsert logic untuk `stock_personality` dan duplicate skip untuk `ohlcv` mencegah UNIQUE constraint errors.

---

## 5. Rekomendasi Prioritas Perbaikan — Status

### Prioritas Tinggi ✅ SEMUA SELESAI:
1. ✅ **Buat `.env` dari `.env.example`** — `ENV=paper`, `BROKER_ADAPTER=paper`.
2. ✅ **Migrate & seed `market_research.db` dan `market_paper.db`** — 8 markets seeded.
3. ✅ **Migrasi data parquet ke SQLite** — 2.91M OHLCV + 7 tabel lainnya.
4. ✅ **Perbaiki 3 high severity frontend vulnerabilities** — Next.js 16.3.0, 0 vulnerabilities.

### Prioritas Sedang ✅ SEMUA SELESAI:
5. ✅ **Register scheduler tasks** — 5 tasks terdaftar.
6. ✅ **Wire-up `/api/portfolio` dan `/api/watchlist` ke database** — DB-backed.
7. ✅ **Naikkan test coverage** — 719 tests, 83.77% coverage.
8. ✅ **Paper trading siap** — PortfolioEngine dengan initial cash 100M IDR, OHLCV prices dari DB.

### Prioritas Rendah ✅ SELESAI / IN PROGRESS:
9. ✅ **Model champion pertama** — Baseline LSTM trained (fallback mode), registered & promoted to champion.
10. ⏳ **Robo-advisor integration** — Module tersedia, belum terhubung ke portfolio & watchlist.
11. ⏳ **Social/copy trading (paper-only)** — Stubs tersedia, leaderboard paper-only.
12. ⏳ **Documentation polish** — AUDIT-FINDINGS.md updated, user manual belum dibuat.

### Remaining (Human-Gate Required):
- ⏳ **Paper Trading 30 Hari** — Jalankan minimal 30 hari simulasi sebelum human-gate broker real.
- ⏳ **PyTorch Installation** — Install `torch` untuk GPU-accelerated LSTM training (saat ini fallback mode).
- ⏳ **Live Gate** — Setelah paper period memadai, ajukan approval untuk broker real.
