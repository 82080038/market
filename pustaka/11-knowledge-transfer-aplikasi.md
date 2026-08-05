# Knowledge Transfer: Pola & Pelajaran untuk Aplikasi Pasar Modal

> **Tujuan:** Dokumen ini mengadaptasi dan mengintegrasikan pola arsitektur, praktik terbaik, pelajaran dari bug, dan keputusan desain dari proyek `trading-system` (v0.1.11) ke dalam knowledge base pasar modal. Ini adalah jembatan antara teori pasar modal dan implementasi aplikasi nyata.
>
> **Sumber:** Proyek `trading-system` — sistem decision support untuk saham IDX/Indonesia, 80+ modul Python, 750+ unit tests, 88 API endpoints (86 REST + 2 WebSocket), SQLite + Parquet archive, 951 tickers aktif (928 equity + 23 non-equity), ~2.9M rows OHLCV.
>
> **Lokasi source code:** `/home/petrick/projects/global` — aplikasi ini telah pernah dibangun dan dijalankan. Kode, arsitektur, modul, dan pelajaran dari proyek tersebut **dapat diadopsi atau dicopy** sebagian maupun seluruhnya ke aplikasi baru. Dokumen ini berfungsi sebagai panduan adopsi: setiap section menandai pola/modul yang siap direuse.
>
> **Pembaruan:** Agustus 2026

---

## Daftar Isi

1. [Pola Arsitektur](#1-pola-arsitektur)
2. [Database & Storage](#2-database--storage)
3. [Decision Engine Pattern](#3-decision-engine-pattern)
4. [Keamanan](#4-keamanan)
5. [Data Quality & Rate Limiting](#5-data-quality--rate-limiting)
6. [Backtesting Anti-Bias](#6-backtesting-anti-bias)
7. [AI/ML Engineering](#7-aiml-engineering)
8. [API Design](#8-api-design)
9. [Konfigurasi & Environment](#9-konfigurasi--environment)
10. [Testing](#10-testing)
11. [Repository Hygiene](#11-repository-hygiene)
12. [Pelajaran dari Bug Produksi](#12-pelajaran-dari-bug-produksi)
13. [IDX-Specific Conventions](#13-idx-specific-conventions)
14. [Anti-Pattern yang Dihindari](#14-anti-pattern-yang-dihindari)
15. [Quick Reference](#15-quick-reference)

---

## 1. Pola Arsitektur

### 1.1 Modular Monolith (bukan Microservice)

Untuk solo developer atau tim kecil (<5 orang), **modular monolith** lebih efektif dari microservice. Setiap modul adalah package Python terpisah dengan boundary jelas, tapi berbagi process space dan database tunggal.

```
src/trading_system/
  data/           # Acquisition, storage, validation
  analysis/       # 24 engine analisis (technical, fundamental, macro, ...)
  sentiment/      # 6 sumber sentimen
  decision/       # Multi-factor weighted scoring
  risk/           # 8 engine risk management
  execution/      # Broker adapter, paper/real execution
  backtest/       # Engine + strategies + metrics
  ai_learning/    # LR, DL, ensemble, walk-forward
  xai/            # Explainable AI narrative
  api/            # FastAPI (88 endpoints)
  cli.py          # 17 subcommands
  config.py       # Single source of truth
```

**Mengapa monolith:** Tidak ada network overhead, shared type safety, debug mudah, deploy sederhana (1 process). Boundary modul dijaga via `__init__.py` exports dan convention (modul hanya import dari `data/`, `config`, atau sesama sub-domain).

**Kapan pindah ke microservice:** Hanya jika tim >10 orang ATAU ada need untuk scale komponen berbeda secara independen (mis. scraping scale terpisah dari API).

### 1.2 Single Source of Truth untuk Config

Semua konstanta penting (modal trading, threshold, rate limit) didefinisikan **sekali** di `config.py` dan dibaca oleh semua engine. Tidak ada hard-code angka di modul lain.

```python
# config.py — satu sumber kebenaran
TRADING_CAPITAL = _safe_float("TRADING_CAPITAL", "100000000")
EXIT_CONVICTION_THRESHOLD = _safe_float("EXIT_CONVICTION_THRESHOLD", "40")

# risk/engine.py, decision/engine.py, execution/automated.py — semua baca dari config
from trading_system.config import TRADING_CAPITAL
```

**Pelajaran:** Sebelum refactor, ada 3 angka modal berbeda di 3 engine → bug ketidakcocokan. Satukan ke satu sumber, hilangkan seluruh kelas bug.

### 1.3 Versioned Outputs

Setiap engine menyertakan `version` string di outputnya. Memudahkan audit dan reproducibility — tahu versi algoritma mana yang menghasilkan skor tertentu.

```python
class FactorEngine:
    VERSION = "1.0"
    def compute(self, ...):
        return {"score": ..., "version": self.VERSION, "reasons": [...]}
```

### 1.4 Reason Codes untuk Audit

Setiap keputusan (BUY/HOLD/SELL, NO_TRADE, REJECT) disertai list reason codes. Bukan hanya "HOLD", tapi `HOLD` dengan `["LOW_CONFIDENCE", "STALE_DATA", "REGIME_GATE"]`.

```python
{"action": "HOLD", "conviction": 35, "reasons": ["LOW_CONFIDENCE", "REGIME_GATE"]}
```

Memungkinkan: (1) XAI narrative generation, (2) audit trail, (3) debugging "mengapa sistem tidak beli saham X?".

---

## 2. Database & Storage

### 2.1 SQLite WAL Mode untuk Analytics Workload

SQLite dengan **WAL (Write-Ahead Logging)** mode cocok untuk analytics workload hingga ~3M rows per tabel, concurrent read + single writer.

```python
conn = sqlite3.connect(str(db_path))
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")  # balance safety vs speed
conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
```

**Kapan pindah dari SQLite:** Jika ada >1 concurrent writer ATAU tabel >50M rows dengan query kompleks. Sebelum itu, SQLite + indeks yang tepat lebih dari cukup dan menghilangkan seluruh kompleksitas DBA.

### 2.2 Parquet Archive untuk Data Raw Permanen

Pattern **two-tier storage**: SQLite untuk query/hot path, Parquet untuk raw archive (cold storage, immutable, columnar).

```
data/
  trading_system.db          # SQLite (hot, queryable)
  archive/                   # Parquet (cold, immutable)
    ohlcv/
      BBCA.JK/2024.parquet
      BBCA.JK/2025.parquet
```

**Mengapa Parquet untuk archive:** (1) Columnar = kompresi efisien untuk time-series, (2) Schema evolution friendly, (3) Portable (bisa dibaca pandas/duckdb/polars), (4) Tidak butuh server, (5) Immutable = audit-friendly.

### 2.3 Schema Migrations via Alembic

Jangan pernah modify schema via `ALTER TABLE` ad-hoc di kode. Gunakan migration tool (Alembic) dengan versioned files:

```
alembic/versions/
  0001_initial.py
  0002_d1_d31_tables.py
  0003_ipo_suspension_delisting.py
```

Setiap migration: (1) `upgrade()` dan `downgrade()`, (2) idempotent, (3) tested.

**Bug yang ditemukan:** Alembic migration 0003 menggunakan `conn.execute("PRAGMA ...")` yang gagal dengan SQLAlchemy 2.0 — perlu dibungkus dengan `sqlalchemy.text()`.

### 2.4 SQL Injection Protection untuk Dynamic Identifiers

SQLite/PostgreSQL tidak bisa parameterize **identifiers** (column/table names) — hanya values. Untuk dynamic column names, gunakan **allowlist**:

```python
_POSITION_COLUMNS = {"ticker", "shares", "avg_cost", "unrealized_pnl", ...}

def update_position(self, ticker: str, **kwargs):
    for col in kwargs:
        if col not in _POSITION_COLUMNS:
            raise ValueError(f"Unknown column: {col}")
    sets = ", ".join(f"{c} = ?" for c in kwargs)  # safe: allowlist-validated
    vals = list(kwargs.values()) + [ticker]
    conn.execute(f"UPDATE positions SET {sets} WHERE ticker = ?", vals)
```

---

## 3. Decision Engine Pattern

### 3.1 Multi-Factor Weighted Scoring

Pattern untuk menggabungkan sinyal dari multiple engine menjadi satu skor 0-100:

```python
DEFAULT_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.25,
    "macro": 0.15,
    "global": 0.15,
    "relationship": 0.10,
    "sentiment": 0.15,
}  # total = 1.0

conviction = sum(scores[f] * weights[f] for f in scores)  # 0-100
```

**Kunci:** (1) Bobot bisa dioptimasi via AI Learning, (2) Bobot bisa di-override per-request via API, (3) Jika satu faktor unavailable, **redistribute** bobotnya proporsional ke faktor lain (jangan pakai skor netral 50).

### 3.2 Weight Redistribution saat Faktor Unavailable

```python
def _redistribute_weights(self, weights, ticker):
    wm = self._check_fundamental_weight_multiplier(ticker)  # 0.0, 0.5, or 1.0
    if wm == 0.0 and weights["fundamental"] > 0:
        # Pindahkan bobot fundamental ke faktor lain proporsional
        fund_w = weights.pop("fundamental")
        total = sum(weights.values())
        for f in weights:
            weights[f] += fund_w * (weights[f] / total)
```

**Mengapa penting:** Untuk saham .JK, data fundamental yfinance sering kosong. Pakai skor netral 50 akan menarik conviction ke tengah secara artifisial. Redistribute lebih jujur — "saya tidak tahu fundamental, andalkan faktor lain".

### 3.3 Regime-Aware Score Adjustment

Sesuaikan skor berdasarkan market regime (tightening/easing/neutral):

```python
if macro_regime == "tightening":
    adjusted["macro"] *= 0.8
    adjusted["technical"] *= 0.9
elif macro_regime == "easing":
    adjusted["macro"] = min(100, adjusted["macro"] * 1.1)
```

### 3.4 Conviction-Based Exit Signal

Tidak hanya entry (BUY), tapi juga exit (SELL) berbasis conviction:

```python
if conviction < EXIT_CONVICTION_THRESHOLD and has_position:
    action = "SELL"
    reasons.append("LOW_CONVICTION_EXIT")
```

---

## 4. Keamanan

### 4.1 API Key dengan `secrets.compare_digest` (Anti Timing Attack)

```python
import secrets

def verify_api_key(provided: str, expected: str) -> bool:
    if not expected:
        return False  # fail-closed jika key belum dikonfigurasi
    return secrets.compare_digest(provided, expected)
```

**Jangan pakai `==`** — vulnerable ke timing attack.

### 4.2 Path Traversal Protection

```python
import re
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

def safe_path(base: Path, name: str) -> Path | None:
    if not SAFE_NAME.match(name):
        return None
    resolved = (base / name).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return None
    return resolved
```

**Pelajaran:** Ticker seperti `a/../../etc/passwd` bisa escape directory.

### 4.3 Fail-Fast di Production

```python
if os.getenv("ENV") == "production" and not os.getenv("API_KEY"):
    raise RuntimeError("API_KEY wajib di-set di production")
```

### 4.4 WebSocket Auth via Query Param

WebSocket tidak bisa set custom header dari browser. Gunakan query param:

```
ws://localhost:8000/ws/live?token=YOUR_API_KEY
```

---

## 5. Data Quality & Rate Limiting

### 5.1 Adaptive Rate Limiter dengan Circuit Breaker

3-state circuit breaker untuk external API calls:

```
CLOSED → (error rate > threshold) → OPEN
OPEN → (timeout elapsed) → HALF_OPEN
HALF_OPEN → (success) → CLOSED
HALF_OPEN → (failure) → OPEN
```

### 5.2 Kalibrasi Rate Limit via Stress Test

Jangan menebak rate limit. **Test empiris**:

```python
# scripts/bench/ratelimit_stress.py
# Test: 30 requests ke Yahoo Finance dengan delay 0.0s → 100% success
# Keputusan: 0.3s delay (safety margin) untuk batch 989 ticker
```

### 5.3 Data Freshness Check

Sebelum pakai data, cek umur. Re-fetch jika basi:

```python
def ensure_data(self, ticker, max_age_days=1):
    last = self.storage.get_last_date(ticker)
    if last and (datetime.now() - last).days > max_age_days:
        self.fetch(ticker)
```

### 5.4 Mixed Datetime Format Handling

**Bug yang ditemukan:** `ingested_at` memiliki mixed datetime formats (ISO8601 dengan timezone + space-separated tanpa timezone). Solusi:

```python
pd.to_datetime(df['ingested_at'], format="mixed", utc=True)
```

---

## 6. Backtesting Anti-Bias

### 6.1 Next-Bar-Open Execution (No Look-Ahead Bias)

```python
# WRONG (look-ahead bias):
signal = df["close"] > df["close"].rolling(20).mean()
df["position"] = signal.astype(int)

# CORRECT (next-bar-open):
signal = df["close"] > df["close"].rolling(20).mean()
df["entry_price"] = df["open"].shift(-1)
df["position"] = signal.shift(1).fillna(0).astype(int)
```

### 6.2 Block Bootstrap Monte Carlo

Untuk preserve autokorelasi & volatility clustering:

```python
def block_bootstrap(returns, n_samples, block_size=20):
    n = len(returns)
    samples = []
    for _ in range(n_samples):
        blocks = [returns[i:i+block_size] for i in random.sample(range(n-block_size), n//block_size)]
        samples.append(np.concatenate(blocks))
    return samples
```

IID resampling menghancurkan struktur temporal — block bootstrap menjaganya.

### 6.3 IDX-Specific Rounding

```python
shares = round(target_shares / IDX_LOT_SIZE) * IDX_LOT_SIZE  # 100 lembar/lot
fill_price = round_to_tick(price)  # tick: Rp1/2/5/10/25 berdasarkan harga
```

---

## 7. AI/ML Engineering

### 7.1 Clip Negative Coefficients (bukan `np.abs`)

```python
# WRONG: coef = np.abs(model.coef_)  # mengubah arti
# CORRECT:
coef = np.maximum(model.coef_, 0)  # faktor negatif = tidak prediktif, ignore
```

### 7.2 TimeSeriesSplit (bukan KFold) untuk Time-Series Data

```python
from sklearn.model_selection import TimeSeriesSplit
tscv = TimeSeriesSplit(n_splits=5)
```

### 7.3 Purged Time Series Split

Tambahkan **gap/purge** antara train dan test untuk menghindari label leakage:

```python
class PurgedTSS:
    def split(self, X, purge_days=5):
        for train_end, test_start in self._get_splits(X):
            train = X[:train_end - purge_days]
            test = X[test_start:]
            yield train, test
```

### 7.4 Model Registry (Versioned Storage)

Setiap model disimpan dengan metadata: version, metrics, training data range, feature list. Bisa rollback ke versi sebelumnya.

### 7.5 Minimum Sample Threshold

```python
if len(X) < 60:
    return {"status": "insufficient_data", "n_samples": len(X)}
```

---

## 8. API Design

### 8.1 SanitizedJSONResponse untuk NaN/Inf

`float('nan')` dan `float('inf')` menghasilkan JSON invalid. Custom JSONResponse:

```python
class SanitizedJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        def sanitize(obj):
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(v) for v in obj]
            return obj
        return json.dumps(sanitize(content), ensure_ascii=False).encode("utf-8")
```

### 8.2 Pagination Validation

```python
def _clamp_pagination(page, limit, max_limit=1000):
    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), max_limit))
    return page, limit
```

### 8.3 Empty Body Acceptance untuk POST

```python
@app.post("/api/rebalance")
async def rebalance(payload: dict = Body(default_factory=dict)):
    pass
```

### 8.4 Sensitive Path Matching

Match dengan parameterized path prefix, bukan prefix match sederhana:

```python
_SENSITIVE_PATHS = {"/api/execution/toggle", "/api/rebalance/toggle"}

def is_sensitive(path: str) -> bool:
    parts = path.strip("/").split("/")
    normalized = "/".join(p if not is_param_value(p) else "{param}" for p in parts)
    return normalized in _SENSITIVE_PATHS
```

---

## 9. Konfigurasi & Environment

### 9.1 Safe Env Var Parsing

```python
def _safe_float(env_key: str, default: str) -> float:
    raw = os.getenv(env_key, default)
    if raw is None or raw.strip() == "":
        raw = default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)
```

### 9.2 Simple .env Parser (tanpa python-dotenv)

```python
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip().strip("\"'")
            if _key and _key not in os.environ:
                os.environ[_key] = _val
```

**Kunci:** `if _key not in os.environ` — env var yang sudah set (mis. via Docker) tidak di-override.

### 9.3 `.env.example` sebagai Dokumentasi

```env
# YFINANCE_RATE_LIMIT_WINDOW — delay antar request ke Yahoo Finance (detik)
# Calibrated via scripts/bench/ratelimit_stress.py (Aug 2026).
# Stress test: 100% success at 0.0s delay for 30 requests.
# 0.3s chosen with safety margin for 989-ticker batches.
YFINANCE_RATE_LIMIT_WINDOW=0.3
```

---

## 10. Testing

### 10.1 Fixture Autouse untuk Test Determinism

```python
@pytest.fixture(autouse=True)
def reset_api_key(monkeypatch):
    monkeypatch.setattr("trading_system.utils.notifier._API_KEY", "")
```

**Tanpa ini:** 11 test gagal di satu machine (karena `.env` set API_KEY) tapi pass di CI.

### 10.2 Coverage Threshold Realistis

`fail_under = 50` — bukan 90%. Coverage 50% yang stabil lebih baik dari target 90% yang mendorong test trivial.

### 10.3 Test Plan Dokumentasi

Dokumentasikan test plan terpisah — bukan hanya "run pytest". Struktur: apa yang di-test per modul, scenario coverage, known limitations.

---

## 11. Repository Hygiene

### 11.1 `.gitignore` Komprehensif

```gitignore
*.deb
*.rpm
*.exe
reports/
scripts/missing_*.txt
__pycache__/
*.py[cod]
*.egg-info/
```

### 11.2 Jangan Commit File Tidak Relevan

Installer `Devin-linux-x64-3.4.27.deb` (5.2MB) ter-commit tidak sengaja — membesarkan repo untuk semua clone selamanya.

### 11.3 Hapus Folder Yatim

Jika modul dipindahkan, **hapus folder lama sepenuhnya** — termasuk `__pycache__`.

### 11.4 Path References Konsisten

Saat memindahkan file, update **semua** referensi path di code, comment, dan docs.

---

## 12. Pelajaran dari Bug Produksi

### 12.1 Lexicon Sentimen: Kata Ambigu

Kata `"rugi"` awalnya ada di `POSITIVE_WORDS` (karena "rugi" = laba dalam konteks akuntansi tertentu). Padahal di berita saham, "rugi" hampir selalu negatif.

**Pelajaran:** Untuk NLP domain-specific, review lexicon manual dengan native speaker. Kata ambigu/context-dependent harus dihapus atau ditangani via negasi detection.

### 12.2 Tiebreaker yang Selalu True

```python
# BUG: oil_now > 0 selalu True (harga minyak selalu positif)
if oil_now > 0:
    return "growth"  # selalu return growth, never "slowdown"

# FIX: bandingkan dengan periode sebelumnya
if oil_now > oil_prev:
    return "growth"
```

### 12.3 Broker Summary `% Out` Always 0

```python
# BUG: cek index label "%" (always False, kolomnya "% Out")
if "%" in row:
    pct = row["%"]

# FIX: cek column name yang sebenarnya
if "% Out" in row.index:
    pct = row["% Out"]
```

**Pelajaran:** `in` operator pada pandas Series mengecek values, bukan index/columns.

### 12.4 Division by Zero di Position Sizing

```python
# BUG: last_price <= 0 → stop_distance = 0 → division by zero
# FIX: guard eksplisit
if stop_distance <= 0 or last_price <= 0:
    return {"error": "invalid_stop_distance", ...}
```

### 12.5 Inf di Backtest Metrics

```python
# BUG: equity_curve.iloc[0] == 0 → total_return = inf
# FIX: guard + replace
if equity_curve.iloc[0] == 0:
    total_return = float("nan")
```

### 12.6 Indonesian Column Names in Parquet

**Bug:** `policy_events` parquet memiliki Indonesian column names (tanggal, kategori, judul, etc.) — perlu column mapping ke English schema names.

**Pelajaran:** Data dari sumber eksternal bisa memiliki schema yang tidak terduga. Selalu lakukan column mapping dan validasi schema saat ingest.

### 12.7 SQLAlchemy 2.0 Breaking Change

**Bug:** `conn.execute("PRAGMA ...")` gagal dengan SQLAlchemy 2.0 — perlu dibungkus dengan `sqlalchemy.text()`.

**Pelajaran:** Upgrade dependency major version dapat break existing code. Test semua migration setelah upgrade.

---

## 13. IDX-Specific Conventions

Untuk developer yang membangun aplikasi untuk Bursa Efek Indonesia:

### 13.1 Lot Size

1 lot = 100 lembar saham. Semua order harus kelipatan 100:

```python
IDX_LOT_SIZE = 100
shares = round(target_shares / IDX_LOT_SIZE) * IDX_LOT_SIZE
```

### 13.2 Tick Size Berdasarkan Fraksi Harga

```python
def idx_tick_size(price: float) -> float:
    if price < 200:    return 1.0
    elif price < 500:  return 2.0
    elif price < 2000: return 5.0
    elif price < 5000: return 10.0
    else:              return 25.0
```

### 13.3 Broker Fee & Tax

```python
DEFAULT_BROKER_FEE_BUY = 0.0015   # 0.15%
DEFAULT_BROKER_FEE_SELL = 0.0025  # 0.25% (termasuk PPh 0.1%)
DEFAULT_LEVY = 0.0000043          # 0.00043%
```

### 13.4 Circuit Breaker IDX

- **Auto Reject:** Harga turun >15% dari reference → trading halt
- **Auto Suspension:** Harga naik >15% dari reference
- **Market-wide halt:** IHSG turun >5% → semua trading halt 30 menit
- **IHSG turun >10%:** Trading halt 30 menit
- **IHSG turun >15%:** Suspend sampai penutupan

### 13.5 Yahoo Finance Ticker Format

Saham IDX: `BBCA.JK`, `TLKM.JK` (suffix `.JK`). Index: `^JKSE` (IHSG).

### 13.6 IDX.co.id Scraper (Real Data)

Endpoint gratis untuk foreign flow & broker summary:
- `idx.co.id/primary/TradingSummary/getStockSummary` — foreign flow per saham
- `idx.co.id/primary/TradingSummary/getBrokerSummary` — broker summary per hari

Data tersedia sejak Jan 2020. Rate limit 0.3s/request aman.

### 13.7 Instrument Classification

```python
# Equity stocks (saham) — untuk trading signals
asset_class = 'equity' AND is_active = 1

# Non-equity reference — untuk macro/global, NOT for trading signals
# forex, index, commodity, ETF
```

**Pelajaran:** Downstream engines harus filter `is_active = 1 AND asset_class = 'equity'` untuk memproses hanya listed saham.

---

## 14. Anti-Pattern yang Dihindari

### 14.1 Hard-Code Konfigurasi di Multiple Places

```python
# BAD: modal di-hard-code di 3 file berbeda
# GOOD: satu sumber di config.py
from trading_system.config import TRADING_CAPITAL
```

### 14.2 `np.abs` untuk Koefisien Negatif

```python
# BAD: mengubah arti (negatif jadi positif)
coef = np.abs(model.coef_)
# GOOD: clip ke 0
coef = np.maximum(model.coef_, 0)
```

### 14.3 IID Resampling untuk Time-Series

```python
# BAD: menghancurkan struktur temporal
# GOOD: block bootstrap preserve autocorrelation
```

### 14.4 `==` untuk String Comparison yang Security-Sensitive

```python
# BAD: timing attack vulnerable
# GOOD: secrets.compare_digest
```

### 14.5 KFold untuk Time-Series Data

```python
# BAD: future data leak ke training set
# GOOD: TimeSeriesSplit atau PurgedTSS
```

### 14.6 Assume Input Selalu Valid

```python
# BAD: crash pada data corrupt
# GOOD: guard + explicit error return
if entry <= stop:
    return {"error": "invalid_stop", "message": "entry must be > stop"}
```

---

## 15. Quick Reference

### Stack yang Terbukti Berhasil

| Komponen | Pilihan | Alternatif |
|----------|---------|------------|
| Bahasa | Python 3.11+ | — |
| DB | SQLite (WAL mode) | PostgreSQL jika >1 writer |
| Archive | Parquet | — |
| Web framework | FastAPI | Flask |
| Frontend | Next.js + TypeScript | — |
| Linter | ruff (line-length 120) | — |
| Type checker | mypy | — |
| Test | pytest + coverage ≥50% | — |
| Migration | Alembic | — |
| HTTP client | httpx | requests |
| Data | pandas + numpy | polars |
| ML | scikit-learn | tensorflow |
| Package manager | uv | pip |

### Prinsip Desain Inti

1. **Single source of truth** — konfigurasi, tidak duplikasi
2. **Fail-fast** — crash di startup > jalan tanpa keamanan
3. **PIT-safe** — semua komputasi hanya pakai data sampai `as_of`
4. **Versioned outputs** — setiap engine sertakan version string
5. **Reason codes** — setiap keputusan disertai alasan untuk audit
6. **Guard everything** — jangan assume input valid, terutama di financial code
7. **Modular monolith** — boundary jelas tanpa network overhead
8. **Two-tier storage** — SQLite hot + Parquet cold
9. **Empirical calibration** — test rate limit, jangan menebak
10. **Test determinism** — autouse fixture reset state, tidak terpengaruh `.env`

### Data Snapshot (Aug 2026)

| Metrik | Nilai |
|--------|-------|
| Total tickers | 951 aktif (928 equity + 23 non-equity) |
| OHLCV rows | 2,906,406 |
| Date range | 1997-07-02 to 2026-08-04 |
| Total rows all tables | ~3,100,000 |
| Total tables | 39 |
| API endpoints | 88 (86 REST + 2 WebSocket) |
| Unit test files | 51 |
| Unit tests | 752 |

---

## Referensi

1. Dokumen asli: `docs/KNOWLEDGE_TRANSFER.md` (922 lines)
2. Proyek `trading-system` v0.1.11
3. `docs/DEVELOPER_GUIDE.md`
4. `docs/API_REFERENCE.md`
5. `CHANGELOG.md`

---

> **Catatan:** Dokumen ini adalah adaptasi dari `docs/KNOWLEDGE_TRANSFER.md` yang diintegrasikan ke dalam knowledge base pasar modal di `pustaka/`. Untuk panduan membangun aplikasi lengkap, lihat `12-panduan-membangun-aplikasi-pasar-modal.md`.
