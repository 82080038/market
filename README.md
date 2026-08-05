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
│  39 tables: OHLCV, Fundamental, Macro, News, Scores, etc.        │
└─────────────────────────────────────────────────────────────────┘
```

### Komponen Kunci

- **Async Event Broker** (`src/market/core/events.py`): Event-driven architecture untuk decoupled communication antar modul.
- **Multi-Factor ML Pipeline** (`src/market/analysis/multi_factor.py`): 30 endogenous + 24 exogenous features → PCA → LightGBM 3-class (BUY/SELL/HOLD) dengan walk-forward CV.
- **Market Context Provider** (`src/market/analysis/market_context.py`): 9 sinyal gabungan — fundamental, macro, sentiment, foreign flow, cross-market, ML, news, commodity, global sentiment (Time-Zone Bucket Grid).
- **Prediction Engine** (`src/market/analysis/prediction.py`): Ensemble 5 metode (MA, momentum, pattern, vol-adjusted, context-adjusted) dengan error tracking dan risk memory.
- **Risk Manager** (`src/market/analysis/risk.py`): VaR 95/99, CVaR, max drawdown, position sizing berbasis ATR.
- **NLP Sentiment** (`src/market/social/robo_advisor.py`): Keyword-based NLP dengan lexicon EN+ID untuk news sentiment.

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

# 6. Seed database dari Parquet (lihat section Database Seeding di bawah)
uv run python scripts/seed_from_parquet.py

# 7. Jalankan server API
uv run market api

# 8. Jalankan frontend (terminal terpisah)
cd frontend && npm run dev

# 9. Jalankan scheduler harian (terminal terpisah)
uv run market scheduler
```

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

### 27 Seedable Tables

`ohlcv`, `instrument_master`, `fundamental_data`, `corporate_actions`, `dividends`, `foreign_flow`, `macro_data`, `market_registry`, `market_calendar`, `news`, `scores`, `technical_indicators`, `relationship_matrix`, `fear_greed`, `pattern_analysis`, `stock_personality`, `sector_master`, `watchlist`, `broker_flow`, `fx_rates`, `external_events`, `policy_events`, `esg_scores`, `corporate_governance`, `valuation_cache`, `trading_suspensions`, `data_watermark`, `source_health`

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
├── docs/                 # ADRs & audit findings
└── .github/workflows/    # CI (lint + test)
```

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
