# Laporan Audit Aplikasi Pasar Modal

> **Update 2026-08-15:** Database utama sekarang PostgreSQL 16 di `localhost:5433/market` (alembic head 0023). File `data/market_research.db` (SQLite) sudah tidak ada. Laporan ini ditulis saat masih SQLite dan dipertahankan untuk konteks historis.

**Tanggal audit:** 5 Agustus 2026 (update pasca-implementasi rekomendasi)
**Repository:** https://github.com/82080038/market.git  
**Path:** `/opt/lampp/htdocs/market`  
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
| Database | ✅ `market_research.db` terisi: 3M+ OHLCV + 1M+ DTS + 178K foreign_flow + 1K fundamental |
| Scheduler | ✅ 6 tasks terdaftar (fetch_eod, fetch_fundamental, quality_check, feature_store, drift_detection, generate_reports) |
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
- ✅ **PyTorch Installation** — `torch 2.5.1+cu121` installed, LSTM training verified on `cuda:1` (GTX 1050 Ti, 4GB VRAM, 16.6 MB used). `get_device()` auto-selects `cuda:1` per project rules. Added `[gpu]` extras to `pyproject.toml`.
- ⏳ **Live Gate** — Setelah paper period memadai, ajukan approval untuk broker real.

---

## Data Quality Cleanup (6 Agustus 2026)

**Audit mendalam `market_paper.db`** menemukan 8 masalah kualitas data. Semua telah diperbaiki dengan script `src/market/data/cleanup_data.py` (idempotent, safe to re-run).

### Hasil Perbaikan

| # | Masalah | Sebelum | Sesudah | Status |
|---|---|---|---|---|
| 1 | Ticker suffix inconsistency | instrument_master & foreign_flow tanpa `.JK` suffix; hanya 976/990 OHLCV match | 990/990 OHLCV ∩ instrument_master match; 970 IM + 961 FF tickers dinormalisasi | ✅ |
| 2 | OHLC anomalies (high<low, high<open/close, low>open/close) | 796 rows anomali | 0 anomali | ✅ |
| 3 | volume=0 tidak di-flag | 523K rows tanpa flag | 232K rows di-flag `data_quality_score=0.3` | ✅ |
| 4 | Timestamp dengan jam (17:00:00) + gap BBCA.JK 24 hari | 7,344 rows dengan time component; BBCA.JK Juli 2026 hanya 7 rows | 0 rows dengan time; BBCA.JK 23 rows; 882 rows backfilled | ✅ |
| 5 | sector_master duplikasi (22 rows, 2 sistem) | 22 rows dengan 3-letter + long-form codes | 11 rows (long-form IDX only) | ✅ |
| 6 | market_calendar hanya 2026 | 365 rows (2026 only) | 9,773 rows (2000-2026), 6,882 trading days | ✅ |
| 7 | fundamental_data nilai 0 (pe/pb/roe/eps/market_cap) | 991 rows dengan pe=0, pb=0, roe=0, eps=0 | 991 rows dengan nilai real (pe=5.54, pb=20403, roe=0.21, eps=1642.97) | ✅ |
| 8 | esg_scores & corporate_governance tidak ada di DB | 0 rows | esg_scores: 164 rows, corporate_governance: 208 rows | ✅ |

### File Baru/Dimodifikasi

- **`src/market/data/cleanup_data.py`** (baru) — Script cleanup komprehensif untuk 8 fix.
- **`src/market/db/models.py`** — Tambah `ESGScore` dan `CorporateGovernance` models.
- **`alembic/versions/0002_add_esg_governance.py`** (baru) — Migration untuk 2 tabel baru.

### Database Status Pasca-Cleanup

| DB | Ukuran | Tabel | Rows | Status |
|---|---|---|---|---|
| `market_research.db` | ~900 MB | 42+ | 3M+ OHLCV, 1M+ DTS, 19M+ TI | ✅ Bersih, lengkap |
| `market_paper.db` | ~840 MB | 23+ | 3M+ OHLCV + 7 tabel lainnya | ✅ Di-seed dari research |
| `market_live.db` | 268 KB | 21 | 1 | Sesuai (Live belum aktif) |

### Backup

- `data/backups/market_paper.db.pre-cleanup-20260806-000825.db` (825 MB)
- `data/backups/market_research.db.pre-seed-20260806-001740.db` (268 KB)

---

## 6. Data Enrichment & Corporate Actions (6 Agustus 2026)

**Audit mendalam corporate events IDX** — delisting, merger, pailit, name change, dan standardisasi ticker suffix.

### Hasil Perbaikan

| # | Masalah | Sebelum | Sesudah | Status |
|---|---|---|---|---|
| 1 | Delisting/merger tidak tertangani | 46 delisted tanpa reason, 0 merger | 62 delisted, 211 risk_reason, 3 merger, 2 corporate_actions | ✅ |
| 2 | Name change tidak tercatat | 0 former_name | 34 tickers dengan former_name | ✅ |
| 3 | Non-XIDX suffix hardcoded | `.JK` hardcoded di 6 file | `ticker_util.py` helper, 6 file updated | ✅ |
| 4 | Screener tidak filter merged | N/A | `excluded_merged` filter + `ScreeningResult` | ✅ |
| 5 | 25 IPO baru tanpa DTS/shares | 0 DTS, 0 shares | 4,928 DTS rows, 25 listed_shares filled | ✅ |
| 6 | free_float kosong | ~15 tickers kosong | 922/923 (99.9%) terisi | ✅ |
| 7 | DTS gap Feb 2025–Aug 2026 | Gap ~18 bulan | 4,928 rows derived untuk IPO; gap utama pending | ⏳ |
| 8 | Migration 0006 | N/A | 6 kolom baru di instrument_master | ✅ |

### File Baru/Dimodifikasi

- **`src/market/data/ticker_util.py`** (baru) — Helper standardisasi suffix yfinance.
- **`src/market/data/screener.py`** — Tambahan `excluded_merged` filter.
- **`src/market/pipelines/data_fetch.py`** — Gunakan `to_yf_ticker()`, baca non-XIDX dari DB.
- **`src/market/scheduler_tasks.py`** — Gunakan `to_yf_ticker()` untuk fundamental fetch.
- **`src/market/data/yahoo_adapter.py`** — Gunakan `get_currency(*from_yf_ticker())`.
- **`src/market/data/recompute_internal.py`** — Baca ticker dari `instrument_master`.
- **`src/market/data/data_health.py`** — Join `instrument_master` untuk stale check.
- **`src/market/analysis/profiling.py`** — Gunakan `from_yf_ticker()`.
- **`alembic/versions/0006_add_instrument_master_columns.py`** (baru) — Migration 6 kolom.

### Database Stats Final (6 Agustus 2026)

| Tabel | Rows | Tickers | Periode |
|-------|------|---------|--------|
| `instrument_master` | 985 | 923 active, 62 delisted | — |
| `ohlcv` | 3,024,934 | 1,008 | 2000–2026-08-06 |
| `daily_trading_stats` | 1,082,968 | 983 | 2019–2026-08-05 |
| `foreign_flow` | 178,201 | — | 2019–2026-08-03 |
| `fundamental_data` | 1,007 | 1,007 | snapshot |
| `corporate_actions` | 6,367 | — | dividend 5,974, split 391, merger 2 |
| `technical_indicators` | 19M+ | 923 | time series |
| `trading_suspensions` | 45+ | 45 | — |
| `esg_scores` | 164 | 42 | — |
| `corporate_governance` | 208 | 47 | — |

### Migration History

| Version | Description |
|---------|-------------|
| 0001 | Initial schema |
| 0002 | Add esg_scores and corporate_governance |
| 0003 | Complete schema: 15 missing tables + 4 column additions |
| 0004 | Add scheduler_state |
| 0005 | Add suspension_date to instrument_master |
| 0006 | Add listed_shares, tradeable_shares, delisting_risk_score, delisting_risk_reason, former_ticker, former_name |

---

## 7. Production Pipeline Audit (8-9 Agustus 2026)

### Eksekusi Pipeline

Pipeline `run_production_pipeline.sh` dijalankan pada real DB (9.23 GB) dengan 20 ticker fokus IDX.

**Durasi:** ~14 jam | **CPU:** 99% sustained | **RAM:** 2.9% | **OOM:** tidak ada

### Hasil

| Metrik | Mock DB | Real DB | Target |
|--------|---------|---------|--------|
| Score | 4.19/5.00 | 3.71/5.00 | ≥ 3.5 ✓ |
| Alpha | +0.0021 | ~0.0 | > 0 ✗ |
| Sharpe | +0.85 | -10.0 | > 0 ✗ |
| Max DD | -3.98% | ~0.0% | > -10% ✓ |
| Promoted KEEP | True | False | True ✗ |

### Root Cause: Inverse-Variance Weighting Collapse

BVIC.JK (AcceptRate=0%, zero variance) mendapat 100% bobot portfolio. Semua ticker lain weight=0.0. Akibat: portfolio Sharpe=-10.0, Alpha≈0.

**Fix yang diperlukan:**
1. Filter ticker dengan AcceptRate < 5% dari IV pool
2. Floor variance dengan epsilon (smoothing)
3. Cap max weight per ticker (mis. 20%)
4. Fallback equal-weight untuk ticker dengan Alpha > 0

### Per-Ticker Performance (Real DB)

**Alpha positif (4 ticker):**
- UNTR.JK: Sharpe=+0.263, Alpha=+0.115, Accept=70.9%
- SONA.JK: Sharpe=+0.188, Alpha=+0.090, Accept=12.2%
- BCIC.JK: Sharpe=+0.093, Alpha=+0.068, Accept=52.8%
- APLI.JK: Sharpe=+0.075, Alpha=+0.087, Accept=40.4%

**Alpha negatif (8 ticker):** ICBP, MEDC, INDF, RBMS, KPIG, ASBI, BNBR, TIRT (lengkap di `RENCANA-LANJUTAN-PRODUCTION-PIPELINE.md`)

### File Generated

- `best_ticker_quant_config.json` (26 KB) — config 20 ticker dengan best_params
- `portfolio_data_remediation_report.json` (31 KB) — full report
- `final_portfolio_verdict.json` — **belum ada** (Step 3 abort karena exit code 1)

### Rekomendasi

1. **Immediate:** Fix IV weighting, re-run pipeline
2. **Short-term:** Jalankan Step 3 manual untuk OOS evaluation
3. **Long-term:** Evaluasi model quality — 15/20 ticker Sharpe negatif pada real DB
4. **Crontab:** Install daily signal cron (16:15 WIB / 09:15 UTC, Senin-Jumat)
