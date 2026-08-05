# Laporan Audit Aplikasi Pasar Modal

**Tanggal audit:** 5 Agustus 2026  
**Repository:** https://github.com/82080038/market.git  
**Path:** `/opt/lampp/htdocs/market`  
**Python:** 3.14.4 (venv) — target `>=3.11`  
**Node.js:** v20.20.2  

---

## Ringkasan Eksekutif

| Kategori | Status |
|---|---|
| Ruff lint | ✅ All checks passed |
| Mypy type-check | ✅ No issues in 80 source files |
| Pytest | ❌ 1 failed, 457 passed (coverage 82.68%) |
| Frontend tsc | ✅ No errors |
| npm audit | ❌ 2 vulnerabilities (1 high, 1 critical) |
| Total bug ditemukan | 7 |
| Total warning | 5 |
| Total issue kode | 6 |

---

## 1. Bug (Test Failure & Logic Errors)

### BUG-01: Test `test_run_all_migrations_missing_files` gagal

**File:** `tests/test_migrate.py:35-43`  
**Severity:** High  
**Gejala:** `AssertionError: ohlcv should be 0, got -1`  

**Root cause:** Test mengasumsikan file parquet tidak ada di path konfigurasi, tapi `settings.parquet_archive_path` menunjuk ke `/media/petrick/Parquet/trading_data/` yang berisi data nyata (2.9M baris di `archive/tables/ohlcv.parquet`). Fungsi `migrate_ohlcv` menemukan file, mencoba insert 2.9M baris ke in-memory SQLite, dan gagal (return -1).

**Fix:** Test harus mock `settings.parquet_archive_path` ke path sementara yang kosong, atau menggunakan `monkeypatch`.

### BUG-02: `_f()` return `None` ketika `default=0.0`

**File:** `src/market/data/migrate_parquet.py:49-52`  
**Severity:** Medium  

```python
def _f(row: pd.Series, key: str, default: float = 0.0) -> float | None:
    v = row.get(key)
    return float(v) if pd.notna(v) else default if default else None
```

`default if default else None` — ketika `default=0.0` (falsy), return `None` bukan `0.0`. Ini menyebabkan field numerik yang missing menjadi `NULL` di DB padahal seharusnya `0.0`.

**Fix:** `return float(v) if pd.notna(v) else default`

### BUG-03: `_s()` return `None` ketika `default=""`

**File:** `src/market/data/migrate_parquet.py:55-58`  
**Severity:** Medium  

```python
def _s(row: pd.Series, key: str, default: str = "") -> str | None:
    v = row.get(key)
    return str(v) if pd.notna(v) else default if default else None
```

Sama dengan BUG-02: `default=""` (falsy) mengembalikan `None` bukan `""`.

**Fix:** `return str(v) if pd.notna(v) else default`

### BUG-04: `Position.market_value` selalu return 0.0

**File:** `src/market/execution/portfolio.py:22-24`  
**Severity:** Low  

```python
@property
def market_value(self) -> float:
    return self.shares * self.current_price if hasattr(self, "current_price") else 0.0
```

`current_price` tidak pernah diset sebagai atribut dataclass. Property ini selalu return `0.0`. Dead code — `get_nav()` dan `get_summary()` tidak menggunakan property ini (mereka terima `prices` dict sebagai parameter).

**Fix:** Hapus property atau ubah untuk menerima price parameter.

### BUG-05: `pyarrow` tidak ada di dependencies

**File:** `pyproject.toml`  
**Severity:** High  

`pyarrow` dibutuhkan untuk `pd.read_parquet()` di `migrate_parquet.py` dan analisis data, tapi tidak listed di `[project.dependencies]`. Install manual diperlukan: `uv add pyarrow`.

**Fix:** Tambahkan `"pyarrow>=15.0"` ke dependencies.

### BUG-06: MockBroker reject market order dengan price=None tapi shares>0

**File:** `src/market/execution/brokers.py:58-60`  
**Severity:** Low  

```python
def submit(self, order: Order) -> BrokerFill | None:
    if order.price is None and order.shares > 0:
        return None  # Market orders need a reference price
```

Logika: jika `price is None` DAN `shares > 0`, reject. Tapi jika `shares <= 0` dan `price is None`, lanjut ke `fill_price = order.price or 0.0` = `0.0`. Ini mengembalikan fill dengan price 0 untuk order tidak valid.

**Fix:** Validasi `order.price is None or order.price <= 0` di awal.

### BUG-07: Frontend Next.js 14.2.5 — critical security vulnerabilities

**File:** `frontend/package.json`  
**Severity:** Critical  

`next@14.2.5` memiliki multiple CVEs: DoS, SSRF, cache poisoning, middleware bypass, unbounded Server Action payload. `postcss` juga vulnerable (XSS, path traversal).

**Fix:** Upgrade `next` ke `>=14.2.35` atau terbaru. Run `npm audit fix --force`.

---

## 2. Warnings

### WARN-01: ResourceWarning — unclosed SQLite connections

**Sumber:** Multiple tests (test_migrate, test_db, test_storage, dll.)  
**Jumlah:** ~10+ instances  

SQLite connections tidak ditutup dengan benar setelah test. Menyebabkan resource leak.

**Fix:** Pastikan `engine.dispose()` dipanggil di test teardown. Gunakan fixture `yield engine` + cleanup.

### WARN-02: StarletteDeprecationWarning — httpx dengan TestClient

**Sumber:** `fastapi/testclient.py`  
**Pesan:** `Using httpx with starlette.testclient is deprecated; install httpx2 instead.`

**Fix:** Update ke versi FastAPI/Starlette terbaru atau install `httpx2`.

### WARN-03: Alembic DeprecationWarning — missing path_separator

**Sumber:** `alembic/config.py:604`  
**Pesan:** `No path_separator found in configuration; falling back to legacy splitting.`

**Fix:** Tambahkan `path_separator = os` ke `alembic.ini` di section `[alembic]`.

### WARN-04: recharts 2.x deprecated

**File:** `frontend/package.json`  
**Pesan:** `1.x and 2.x branches are no longer active. Bump to Recharts v3.`

**Fix:** Upgrade `recharts` ke v3.

### WARN-05: Python 3.14 di venv, target >=3.11

**Catatan:** `pyproject.toml` specifies `>=3.11`, venv menggunakan Python 3.14.4. Tidak ada error, tapi beberapa library mungkin belum fully compatible dengan 3.14. Test coverage menunjukkan `src/market/config.py` hanya 44% — field validator dan properties tidak teruji.

---

## 3. Code Quality Issues

### ISSUE-01: Watchlist in-memory store

**File:** `src/market/api/app.py:30`  

```python
_watchlist: list[dict[str, Any]] = []
```

Watchlist disimpan in-memory, hilang saat restart. Model `Watchlist` ada di DB (`src/market/db/models.py`) tapi tidak digunakan.

**Rekomendasi:** Migrasi ke DB-backed watchlist menggunakan model yang sudah ada.

### ISSUE-02: Engine instances tidak digunakan

**File:** `src/market/api/app.py:25-31`  

```python
TechnicalAnalysisEngine()
FundamentalAnalysisEngine()
MacroEconomicEngine()
GlobalMarketEngine()
MarketRelationshipEngine()
SentimentEngine()
```

Engine instances dibuat tapi tidak disimpan ke variabel. Hanya `decision_engine` dan `advisory_engine` yang digunakan. Lainnya dibuang (garbage collected).

**Fix:** Simpan ke variabel atau hapus jika tidak digunakan.

### ISSUE-03: Coverage rendah di modul tertentu

| Modul | Coverage |
|---|---|
| `src/market/config.py` | 44% |
| `src/market/data/rate_limit.py` | 43% |
| `src/market/db/__init__.py` | 20% |
| `src/market/multi_asset/__init__.py` | 56% |
| `src/market/security/fractional.py` | 64% |

**Rekomendasi:** Tambah test untuk config field validator, rate limiter edge cases, dan DB init.

### ISSUE-04: Tidak ada `.env` file

Hanya `.env.example` yang ada. Aplikasi jalan dengan default `research` mode, tapi `parquet_archive_path` default menunjuk ke `/media/petrick/Parquet/trading_data/` yang hardcode di `Settings`.

**Rekomendasi:** Copy `.env.example` ke `.env` dan sesuaikan nilai.

### ISSUE-05: `GlobalMarketEngine.analyze` — total count includes empty DataFrames

**File:** `src/market/analysis/global_market.py:94-96`  

```python
total = len(data)
ma50_score = (len(above_ma50) / total) * 50 if total > 0 else 0
```

`total` menghitung semua entries termasuk yang empty/skip. Jika 3 dari 7 index kosong, score hanya 4/7 * 50 = 28.5 max, bukan 50.

**Fix:** `total = len(above_ma50) + len(below_ma50)` untuk MA50, dan sama untuk MA200.

### ISSUE-06: Hardcoded `timeframe="1d"` di `save_ohlcv`

**File:** `src/market/data/storage.py:55`  

```python
OHLCV.timeframe == "1d",
```

`save_ohlcv` selalu menggunakan `"1d"` untuk query dan insert, mengabaikan `timeframe` dari `NormalizedOHLCV`. Data intraday tidak akan tersimpan dengan benar.

**Fix:** Gunakan `r.timeframe` atau field dari record.

---

## 4. Data Parquet — Struktur

### Lokasi: `/media/petrick/Parquet/trading_data/`

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

### Catatan migrasi:
- `migrate_parquet.py` membaca dari `archive/tables/` (28 file parquet dengan skema yang sudah normalized)
- `raw/` berisi data mentah dengan skema berbeda (Indonesian column names: `kode`, `tanggal`, `beli`, `jual`)
- Skema `archive/tables/ohlcv.parquet` cocok dengan ekspektasi migrasi (ticker, timestamp, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
- Skema `raw/ohlcv/` menggunakan `kode` (tanpa `.JK`) dan `tanggal` — perlu transformasi jika ingin dimigrasi

---

## 5. Rekomendasi Prioritas Perbaikan

### Prioritas Tinggi (segera):
1. **BUG-07:** Upgrade Next.js untuk security
2. **BUG-05:** Tambah `pyarrow` ke dependencies
3. **BUG-02 & BUG-03:** Fix `_f()` dan `_s()` default value logic
4. **BUG-01:** Fix test migrasi dengan mocking

### Prioritas Sedang:
5. **WARN-03:** Tambah `path_separator = os` ke alembic.ini
6. **ISSUE-05:** Fix GlobalMarketEngine total count
7. **ISSUE-06:** Fix hardcoded timeframe di save_ohlcv
8. **ISSUE-01:** Migrasi watchlist ke DB
9. **ISSUE-02:** Hapus engine instances yang tidak digunakan

### Prioritas Rendah:
10. **BUG-04:** Hapus atau perbaiki `Position.market_value`
11. **BUG-06:** Validasi MockBroker untuk order tidak valid
12. **WARN-01:** Fix resource warnings di tests
13. **WARN-04:** Upgrade recharts ke v3
14. **ISSUE-03:** Tambah test coverage untuk modul low-coverage
