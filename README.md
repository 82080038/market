# Market — Aplikasi Pasar Modal Single-User

Aplikasi **decision-support** untuk pasar modal Indonesia dan global, dibangun dari nol berdasarkan [pustaka/](pustaka/) (94 dokumen pengetahuan). Mendukung analisis multi-faktor, rekomendasi, backtest, paper trading, dan — setelah melewati promotion gates — eksekusi live terkontrol.

> **⚠️ Perhatian:** Aplikasi ini untuk penggunaan **single-user personal**. Fitur multi-user, KYC, RBAC, dan deployment publik sengaja di luar scope. Eksekusi trading nyata memerlukan persetujuan manual dan mekanisme environment `live` yang terisolasi.

---

## Quick Start

```bash
# 1. Install Python 3.11+ dan uv
uv sync --all-extras

# 2. Copy environment template
cp .env.example .env
# Edit .env sesuai environment (research / paper / live)

# 3. Jalankan migrasi database (research/paper default)
uv run market migrate

# 4. Jalankan server API
uv run market api

# 5. Jalankan scheduler harian
uv run market scheduler
```

## Environment

| Environment | Tujuan | Database | Broker | Auto-trading |
|-------------|--------|----------|--------|--------------|
| `research` | Eksperimen & training model | `market_research.db` | `MockBroker` | Tidak |
| `paper` | Validasi live-market tanpa uang nyata | `market_paper.db` | `PaperBroker` | Paper fills only |
| `live` | Eksekusi nyata | `market_live.db` | Broker adapter real | Butuh approval manual |

Lihat [pustaka/93-lifecycle-environments-real-testing-ai.md](pustaka/93-lifecycle-environments-real-testing-ai.md) untuk promotion gates `Research → Paper → Live`.

## Arsitektur

```
market/
├── src/market/        # Backend Python (FastAPI, engines, OMS, AI/ML)
├── frontend/          # Next.js 14 dashboard
├── tests/             # Pytest + Playwright
├── alembic/           # Database migrations
├── data/              # Local SQLite & cache
├── scripts/           # Automation scripts
└── pustaka/           # Knowledge base (94 Markdown docs)
```

## Megaplan

Rencana implementasi lengkap tersedia di [MEGAPLAN.md](MEGAPLAN.md) dengan 12 fase dan completion markers.

## Konvensi

- UI: Bahasa Indonesia; istilah teknis asli dengan tooltip.
- Data: UTC storage; tampilan WIB (UTC+7).
- GPU: `cuda:1` untuk LSTM, walk-forward, Monte Carlo, NLP/IndoBERT.
- Kode: Python 3.11+, Pydantic v2, SQLAlchemy 2.0, TailwindCSS, TypeScript.

## Dokumentasi

- [pustaka/00-README.md](pustaka/00-README.md) — indeks pustaka lengkap.
- [AGENTS.md](AGENTS.md) — aturan AI global untuk project ini.
- [MEGAPLAN.md](MEGAPLAN.md) — rencana implementasi.
