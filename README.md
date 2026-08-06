# Market — Aplikasi Pasar Modal Quant AI

Aplikasi **decision-support** untuk pasar modal Indonesia (IDX) dan global, dibangun berbasis Algorithmic/Quantitative Trading. Menggabungkan analisis multi-faktor, Machine Learning (LightGBM), NLP sentiment, dan manajemen risiko otomatis untuk rekomendasi Swing Trading dan Day Trading monitoring.

> **⚠️ Perhatian:** Aplikasi ini untuk penggunaan **single-user personal**. Fitur multi-user, KYC, RBAC, dan deployment publik sengaja di luar scope. Eksekusi trading nyata memerlukan persetujuan manual dan mekanisme environment `live` yang terisolasi.

---

## Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js 14)                        │
│          Dashboard, Charts, REST API + SWR polling               │
├─────────────────────────────────────────────────────────────────┤
│                      FastAPI Backend                             │
│   REST endpoints, Pydantic v2 validation, async I/O              │
├─────────────────────────────────────────────────────────────────┤
│                    Analysis & AI Layer                           │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌──────────────┐  │
│  │Technical │  │MultiFactor │  │MarketCtx │  │Prediction   │  │
│  │Analysis  │  │Pipeline    │  │Provider  │  │Engine       │  │
│  │Engine    │  │(PCA+LGBM)  │  │(9 signals│  │(Ensemble 5  │  │
│  │(MA,RSI,  │  │(30 endo +  │  │ + global │  │ methods +   │  │
│  │ MACD,BB) │  │ 24 exo)    │  │ sentiment│  │ context adj)│  │
│  └──────────┘  └────────────┘  └──────────┘  └──────────────┘  │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌──────────────┐  │
│  │Pattern   │  │ML Signal   │  │Risk      │  │Robo Advisor │  │
│  │Detector  │  │Provider    │  │Manager   │  │(NLP keyword │  │
│  │(candlest)│  │(LightGBM   │  │(VaR,CVaR │  │ EN+ID lexicon│  │
│  │          │  │ walk-fwd)  │  │ drawdown)│  │)            │  │
│  └──────────┘  └────────────┘  └──────────┘  └──────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    Data Access Layer                             │
│  Yahoo Finance adapter, Parquet storage, SQLAlchemy ORM,         │
│  Corporate Action adjustment, Time-Zone Bucket Grid              │
├─────────────────────────────────────────────────────────────────┤
│              Database (SQLite + Parquet + Alembic)               │
│  42+ tables: OHLCV, Fundamental, Macro, News, Scores, DTS, etc.   │
└─────────────────────────────────────────────────────────────────┘
```

### Komponen Kunci

- **Async Event Broker** (`src/market/core/events.py`): Event-driven architecture untuk decoupled communication antar modul.
- **Multi-Factor ML Pipeline** (`src/market/analysis/multi_factor.py`): 30 endogenous + 24 exogenous features → PCA → LightGBM 3-class (BUY/SELL/HOLD) dengan walk-forward CV.
- **Market Context Provider** (`src/market/analysis/market_context.py`): 9 sinyal gabungan — fundamental, macro, sentiment, foreign flow, cross-market, ML, news, commodity, global sentiment (Time-Zone Bucket Grid).
- **Prediction Engine** (`src/market/analysis/prediction.py`): Ensemble 5 metode (MA, momentum, pattern, vol-adjusted, context-adjusted) dengan error tracking dan risk memory.
- **Risk Manager** (`src/market/analysis/risk.py`): VaR 95/99, CVaR, max drawdown, position sizing berbasis ATR.
- **NLP Sentiment** (`src/market/social/robo_advisor.py`): Keyword-based NLP dengan lexicon EN+ID untuk news sentiment.
- **Ticker Suffix Utility** (`src/market/data/ticker_util.py`): Standardisasi suffix yfinance berdasarkan `market_registry.data_suffix` — menggantikan hardcoded `.JK` di seluruh codebase. Mendukung XIDX, XNYS, XNAS, XFRA, XHKG, XSHG, XTSE, dll.
- **Ticker Screener** (`src/market/data/screener.py`): Filter berlapis untuk eligible tickers — exclude delisted, suspended, merged, blocked, dan low-liquidity.
- **Delisting Memory** (`src/market/analysis/delisting_memory.py`): AI-driven blocking instruments berdasarkan risk score dan status delisting/merger.

---

## Quick Start

### Prasyarat

- **Python 3.11+** dan [uv](https://github.com/astral-sh/uv) package manager
- **Node.js 18+** dan npm (untuk frontend)
- **SQLite** (sudah bundled, tidak perlu instalasi terpisah)
- Opsional: **NVIDIA GPU** dengan CUDA untuk LSTM/Monte Carlo (gunakan `cuda:1`)

### Instalasi

```bash
# 1. Clone repository
git clone https://github.com/petrick/market.git
cd market

# 2. Install Python dependencies
uv sync --all-extras

# 3. Install frontend dependencies
cd frontend && npm install && cd ..

# 4. Copy environment template
cp .env.example .env
# Edit .env sesuai environment (research / paper / live)

# 5. Jalankan migrasi database
uv run market migrate

# 6. ⚠️ RESTORE DATA BESAR DARI EXTERNAL DRIVE (wajib untuk menjalankan aplikasi)
#    Lihat section "Data Eksternal (Wajib)" di bawah.
#    Jika Anda memiliki flashdisk backup:
bash scripts/restore_data_from_external.sh

# 7. Seed database dari Parquet (jika tidak punya backup DB, lihat section Database Seeding)
uv run python scripts/seed_from_parquet.py

# 8. Jalankan server API
uv run market api

# 9. Jalankan frontend (terminal terpisah)
cd frontend && npm run dev

# 10. Jalankan scheduler harian (terminal terpisah)
uv run market scheduler
```

---

## Data Eksternal (Wajib)

Aplikasi ini menggunakan data pasar modal berukuran besar (**~6 GB database + 233 MB CSV dataset**) yang **tidak disimpan di repository Git**. Ada dua cara untuk mendapatkan data:

### Opsi A: Restore dari External Drive (Cepat)

Jika Anda memiliki backup data di external drive:

```bash
# 1. Mount external drive (otomatis di sebagian besar Linux desktop)
#    Default path: /media/petrick/Parquet/projects/market/

# 2. Restore data ke project directory
bash scripts/restore_data_from_external.sh

# 3. Verifikasi
ls -lh data/market_research.db  # ~6 GB
ls data/dataset-saham-idx/       # 1027 CSV files
```

Skrip `restore_data_from_external.sh` akan:
- Mengembalikan `market_research.db` (auto-rejoin chunk jika FAT32)
- Mengembalikan `dataset-saham-idx/` (1027 CSV files)
- Mengembalikan `parquet_seeds/` dan `parquet_export/`

### Opsi B: Seed dari Parquet (Dari Nol)

Jika Anda tidak punya backup DB, bangun dari nol:

```bash
# 1. Siapkan file Parquet di direktori seed
#    Default: /media/petrick/Parquet/pustaka_data/archive/tables/

# 2. Validasi schema
uv run python scripts/seed_from_parquet.py --validate

# 3. Seed database
uv run python scripts/seed_from_parquet.py

# 4. Backfill dari Yahoo Finance (membutuhkan internet)
uv run python scripts/backfill_data.py
```

### Opsi C: Backup Data ke External Drive

Jika Anda sudah punya database dan ingin backup:

```bash
# Copy data ke external drive (tidak hapus source)
bash scripts/sync_data_to_external.sh

# Atau pindahkan (hapus source setelah copy)
bash scripts/sync_data_to_external.sh --move
```

### Daftar Data yang Tidak di-Git

| Path | Ukuran | Deskripsi | Sumber |
|------|--------|-----------|--------|
| `data/market_research.db` | ~6 GB | Database utama (OHLCV, DTS, fundamental, dll) | Seed/backfill |
| `data/market_paper.db` | ~6 GB | Database paper trading | Seed dari research |
| `data/market_live.db` | <1 MB | Database live (kosong, sesuai) | Migrate |
| `data/dataset-saham-idx/` | 233 MB | 1027 CSV files IDX (Jul 2019–Feb 2025) | GitHub clone |
| `data/backups/` | varies | Backup DB sebelum cleanup | Auto-generated |
| `data/parquet_export/` | varies | Export Parquet dari DB | `--export` flag |
| `.venv/` | ~674 MB | Python virtual environment | `uv sync` |
| `frontend/node_modules/` | ~588 MB | Node.js dependencies | `npm install` |
| `models/` | varies | Trained ML models | Training |
| `logs/` | varies | Application logs | Runtime |

> **⚠️ Penting:** Aplikasi akan error jika `data/market_research.db` tidak ada. Pastikan salah satu opsi di atas sudah dijalankan sebelum `uv run market api`.

---

## Database Seeding (Parquet Portable Seeder)

Aplikasi ini menyediakan skrip seeder portable yang memungkinkan contributor untuk mengisi database lokal dari file Parquet eksternal.

### Cara Kerja

1. **Siapkan file Parquet** di direktori seed (default: `/media/petrick/Parquet/pustaka_data/archive/tables/`)
2. **Validasi schema** — skrip akan memeriksa kompatibilitas kolom Parquet vs database
3. **Seed database** — import data dengan INSERT batch (5000 rows/batch)

### Perintah

```bash
# Validasi semua file Parquet (tanpa import)
uv run python scripts/seed_from_parquet.py --validate

# Seed semua tabel dari Parquet
uv run python scripts/seed_from_parquet.py

# Seed tabel spesifik
uv run python scripts/seed_from_parquet.py --table ohlcv

# Export database ke Parquet (untuk berbagi data)
uv run python scripts/seed_from_parquet.py --export

# Export tabel spesifik
uv run python scripts/seed_from_parquet.py --export --table instrument_master

# Gunakan direktori Parquet custom
uv run python scripts/seed_from_parquet.py --seed-dir /path/to/parquet/files
```

### Schema Validation

Skrip seeder melakukan validasi otomatis:
- **Required columns**: kolom wajib per tabel (misal: `ohlcv` butuh `ticker`, `timestamp`, `open`, `high`, `low`, `close`, `volume`)
- **Column mapping**: konversi nama kolom Parquet → DB (misal: `pe_ratio` → `pe`)
- **Extra columns**: kolom Parquet yang tidak ada di DB akan di-skip (warning)

### 28+ Seedable Tables

`ohlcv`, `instrument_master`, `fundamental_data`, `corporate_actions`, `dividends`, `foreign_flow`, `macro_data`, `market_registry`, `market_calendar`, `news`, `scores`, `technical_indicators`, `relationship_matrix`, `fear_greed`, `pattern_analysis`, `stock_personality`, `sector_master`, `watchlist`, `broker_flow`, `fx_rates`, `external_events`, `policy_events`, `esg_scores`, `corporate_governance`, `valuation_cache`, `trading_suspensions`, `daily_trading_stats`, `data_watermark`, `source_health`

---

## Environment

| Environment | Tujuan | Database | Broker | Auto-trading |
|-------------|--------|----------|--------|--------------|
| `research` | Eksperimen & training model | `market_research.db` | `MockBroker` | Tidak |
| `paper` | Validasi live-market tanpa uang nyata | `market_paper.db` | `PaperBroker` | Paper fills only |
| `live` | Eksekusi nyata | `market_live.db` | Broker adapter real | Butuh approval manual |

Lihat [pustaka/93-lifecycle-environments-real-testing-ai.md](pustaka/93-lifecycle-environments-real-testing-ai.md) untuk promotion gates `Research → Paper → Live`.

---

## Struktur Direktori

```
market/
├── src/market/
│   ├── analysis/         # Analysis engines (technical, ML, prediction, multi-factor)
│   ├── api/              # FastAPI routes & schemas
│   ├── autonomous/       # Autonomous pipeline & scheduler
│   ├── backtest/         # Backtest engine & strategies
│   ├── core/             # Event broker, config, exceptions
│   ├── data/             # Data adapters (Yahoo), storage, contracts
│   ├── db/               # SQLAlchemy models, engine, Alembic
│   ├── oms/              # Order Management System
│   ├── risk/             # Risk manager (VaR, position sizing)
│   └── social/           # Robo advisor, NLP sentiment
├── frontend/             # Next.js 14 dashboard (TailwindCSS, TypeScript)
├── tests/                # Pytest unit + integration tests
├── alembic/              # Database migrations
├── data/                 # Local SQLite, Parquet seeds/exports
├── scripts/              # Automation scripts (backfill, seed, simulation)
├── pustaka/              # Knowledge base (94 Markdown docs)
├── docs/                 # ADRs, audit findings, database issues
└── .github/workflows/    # CI (lint + test)
```

---

## Corporate Actions & Delisting Logic

Aplikasi menangani corporate events IDX secara komprehensif sebagai memory untuk ML/AI:

- **Merger**: `instrument_master.underlying_ticker` di-set ke ticker penerus; `corporate_actions` diisi dengan `action_type='merger'`; screener mengecualikan ticker yang sudah merged.
- **Pailit/Bankruptcy**: `instrument_master.delisting_risk_reason` diisi (e.g. "pailit", "voluntary delisting"); `is_active=0` + `delisting_date`.
- **Name Change**: `instrument_master.former_ticker` dan `former_name` diisi untuk kontinuitas historis.
- **Trading Suspension**: Tabel `trading_suspensions` dengan `suspend_date`, `resume_date`, `reason`.
- **DTS (Daily Trading Stats)**: Data bid/offer, frequency, value, listed_shares dari GitHub Dataset-Saham-IDX (Jul 2019–Feb 2025) + derived dari OHLCV untuk IPO baru.

### Database Stats (6 Agustus 2026)

| Tabel | Rows | Tickers | Periode |
|-------|------|---------|--------|
| `instrument_master` | 985 | 923 active, 62 delisted | — |
| `ohlcv` | 3,024,934 | 1,008 | 2000–2026-08-06 |
| `daily_trading_stats` | 1,082,968 | 983 | 2019–2026-08-05 |
| `foreign_flow` | 178,201 | — | 2019–2026-08-03 |
| `fundamental_data` | 1,007 | 1,007 | snapshot |
| `corporate_actions` | 6,367 | — | dividend 5,974, split 391, merger 2 |
| `technical_indicators` | 19M+ | 923 | time series |

### Migration History

| Version | Description |
|---------|-------------|
| 0001 | Initial schema: all Fase 1 tables |
| 0002 | Add esg_scores and corporate_governance tables |
| 0003 | Complete schema: 15 missing tables + 4 column additions |
| 0004 | Add scheduler_state table |
| 0005 | Add suspension_date column to instrument_master |
| 0006 | Add listed_shares, tradeable_shares, delisting_risk_score, delisting_risk_reason, former_ticker, former_name |

---

## Backtest & Simulasi

```bash
# Jalankan backtest simulation (8 tickers, 2-year period)
uv run python scripts/run_backtest_simulation.py

# Backfill data dari Yahoo Finance
uv run python scripts/backfill_data.py
```

### Hasil Simulasi (5-Stage Comparison)

| Stage | Fitur | Accuracy | Correct |
|-------|-------|----------|---------|
| 1 | Technical only | 36.0% | 27/75 |
| 2 | + Market context | 44.0% | 33/75 |
| 3 | + Cross-market + ML | 46.7% | 35/75 |
| 4 | + Commodity + News + Global sentiment | 48.0% | 36/75 |
| 5 | + Multi-Factor Pipeline (PCA + 3-class LGBM) | 49.3% | 37/75 |

---

## Konvensi

- **UI**: Bahasa Indonesia; istilah teknis pasar modal (`ticker`, `OHLCV`, `RSI`, `MACD`, `VaR`) tetap dalam bahasa asli dengan tooltip.
- **Data**: UTC storage; tampilan WIB (UTC+7). Jam perdagangan IDX dan DST pasar global diperhatikan.
- **GPU**: `cuda:1` untuk LSTM, walk-forward, Monte Carlo, NLP/IndoBERT.
- **Kode**: Python 3.11+, Pydantic v2, SQLAlchemy 2.0, TailwindCSS, TypeScript.
- **No look-ahead**: Semua backtest dan feature engineering menggunakan strict cutoff `as_of`.

---

## Testing

```bash
# Run all tests
uv run pytest tests/ -q

# Run specific test modules
uv run pytest tests/test_backtest.py tests/test_multi_factor.py -q

# Lint
uv run ruff check src/ tests/ scripts/
```

---

## Megaplan

Rencana implementasi lengkap tersedia di [MEGAPLAN.md](MEGAPLAN.md) dengan 12 fase dan completion markers.

## Dokumentasi

- [pustaka/00-README.md](pustaka/00-README.md) — indeks pustaka lengkap (94 dokumen).
- [AGENTS.md](AGENTS.md) — aturan AI global untuk project ini.
- [MEGAPLAN.md](MEGAPLAN.md) — rencana implementasi 12 fase.
- [CONTRIBUTING.md](CONTRIBUTING.md) — panduan kontribusi untuk contributor.
- [docs/adr/](docs/adr/) — Architecture Decision Records.
- [docs/DATABASE-ISSUES.md](docs/DATABASE-ISSUES.md) — audit konsistensi data IDX.
- [docs/AUDIT-FINDINGS.md](docs/AUDIT-FINDINGS.md) — laporan audit aplikasi.
- [docs/prompting-ai-ml-analysis.md](docs/prompting-ai-ml-analysis.md) — prompt template untuk analisis AI/ML.
