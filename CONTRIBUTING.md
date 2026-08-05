# Panduan Kontribusi — Market Quant AI

Terima kasih telah berkontribusi pada proyek Market Quant AI. Dokumen ini menjelaskan cara setup, konvensi kode, dan workflow untuk contributor.

---

## 1. Fork & Setup

```bash
# 1. Fork repository di GitHub
# 2. Clone fork Anda
git clone https://github.com/<username>/market.git
cd market

# 3. Tambahkan upstream remote
git remote add upstream https://github.com/petrick/market.git

# 4. Install dependencies
uv sync --all-extras
cd frontend && npm install && cd ..

# 5. Copy environment template
cp .env.example .env
# Edit .env — set MARKET_ENV=research untuk development

# 6. Jalankan migrasi database
uv run market migrate
```

---

## 2. Database Seeding dari Parquet

Setelah fork, Anda perlu mengisi database lokal dengan data. Cara tercepat adalah menggunakan Parquet seeder.

### Opsi A: Seed dari file Parquet eksternal

```bash
# 1. Salin file Parquet ke direktori seed (atau gunakan path custom)
#    Default: /media/petrick/Parquet/pustaka_data/archive/tables/
#    Atau:   --seed-dir /path/to/your/parquet/files

# 2. Validasi schema sebelum import
uv run python scripts/seed_from_parquet.py --validate

# 3. Seed database
uv run python scripts/seed_from_parquet.py

# 4. Verifikasi data
uv run python -c "
from market.db.engine import get_sessionmaker
from sqlalchemy import text
s = get_sessionmaker()()
for t in ['ohlcv', 'instrument_master', 'fundamental_data']:
    count = s.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
    print(f'{t}: {count} rows')
s.close()
"
```

### Opsi B: Backfill dari Yahoo Finance

```bash
# Backfill semua data dari Yahoo Finance (membutuhkan koneksi internet)
uv run python scripts/backfill_data.py
```

### Opsi C: Export DB eksisting ke Parquet

Jika Anda sudah punya database dan ingin berbagi data:

```bash
uv run python scripts/seed_from_parquet.py --export
# File Parquet akan tersimpan di data/parquet_export/
```

---

## 3. Konvensi Kode

### Python

- **Python 3.11+**, gunakan `from __future__ import annotations`
- **Linter**: `uv run ruff check src/ tests/ scripts/`
- **Formatter**: `uv run ruff format src/ tests/ scripts/`
- **Type hints**: wajib pada semua function signatures
- **Docstrings**: wajib pada public functions dan classes (triple-quote, Bahasa Indonesia narasi + English untuk kode)

### Struktur Modul

```
src/market/
├── analysis/    # Engine analisis (technical, ML, prediction)
├── api/         # FastAPI routes & Pydantic schemas
├── autonomous/  # Pipeline & scheduler
├── backtest/    # Backtest engine & strategies
├── core/        # Event broker, config, exceptions
├── data/        # Data adapters, storage, contracts
├── db/          # SQLAlchemy models, engine
├── oms/         # Order Management System
├── risk/        # Risk manager
└── social/      # Robo advisor, NLP
```

### Frontend

- **Next.js 14** App Router, TypeScript strict mode
- **TailwindCSS** untuk styling
- **SWR** untuk data fetching (REST polling, bukan WebSocket)
- **Bahasa Indonesia** untuk UI text; istilah teknis (`ticker`, `OHLCV`, `RSI`) tetap English

### Database

- **SQLAlchemy 2.0** ORM, semua model di `src/market/db/models.py`
- **Alembic** untuk migrasi: `uv run alembic revision --autogenerate -m "description"`
- **SQLite** untuk semua environment (research/paper/live)
- **Parquet** untuk data portability dan seeder

---

## 4. Workflow Git

### Branch

```bash
# Buat branch feature dari main
git checkout main
git pull upstream main
git checkout -b feature/nama-fitur

# Commit dengan pesan deskriptif
git add .
git commit -m "feat: tambahkan VWAP feature ke ML pipeline"

# Push ke fork Anda
git push origin feature/nama-fitur

# Buat Pull Request di GitHub ke upstream/main
```

### Commit Convention

- `feat:` fitur baru
- `fix:` bug fix
- `docs:` dokumentasi
- `refactor:` refactor tanpa perubahan perilaku
- `test:` tambah/ubah test
- `chore:` maintenance, dependency update

### Sebelum Pull Request

```bash
# 1. Pastikan lint pass
uv run ruff check src/ tests/ scripts/

# 2. Pastikan tests pass
uv run pytest tests/ -q

# 3. Jalankan simulasi untuk verifikasi tidak ada regression
uv run python scripts/run_backtest_simulation.py
```

---

## 5. Aturan Penting

1. **No look-ahead bias**: Semua feature engineering dan backtest harus menggunakan strict cutoff `as_of`. Data di masa depan tidak boleh digunakan untuk prediksi di masa lalu.

2. **Adjusted prices**: Gunakan `adjusted_close` (bukan `close` mentah) untuk semua perhitungan historis. Lihat `src/market/analysis/market_factors.py:ensure_adjusted()`.

3. **UTC storage**: Semua timestamp disimpan dalam UTC. Tampilan WIB (UTC+7) hanya di frontend.

4. **GPU**: Setiap proses komputasi berat (LSTM, Monte Carlo, NLP) wajib memeriksa `cuda:1` terlebih dahulu.

5. **Pustaka pengetahuan**: Sebelum menambah/mengubah dokumen di `pustaka/`, baca `pustaka/00-README.md` untuk orientasi. Update indeks README setiap kali menambah/menghapus dokumen.

6. **Tidak hardcode API key**: Gunakan `.env` untuk kredensial. Pastikan `.gitignore` memproteksi file sensitif.

7. **Single-user**: Jangan tambahkan fitur multi-user, RBAC, atau KYC. Aplikasi ini untuk penggunaan personal.

---

## 6. Testing

```bash
# Run semua tests
uv run pytest tests/ -q

# Run dengan coverage
uv run pytest tests/ --cov=src/market --cov-report=term-missing

# Run test spesifik
uv run pytest tests/test_multi_factor.py -v
uv run pytest tests/test_backtest.py -v
uv run pytest tests/test_market_factors.py -v
```

### Test Modules

| File | Deskripsi |
|------|-----------|
| `test_backtest.py` | Backtest engine & strategies |
| `test_multi_factor.py` | Multi-factor feature pipeline & ML model |
| `test_market_factors.py` | Price adjustment, volume dynamics, time-zone grid |
| `test_api.py` | API endpoint tests |
| `test_advisory.py` | Robo advisor & NLP tests |
| `test_acquisition.py` | Data acquisition & Yahoo adapter tests |

---

## 7. Troubleshooting

### Database locked

```bash
# Hapus WAL/SHM files
rm data/*.db-wal data/*.db-shm
# Restart aplikasi
```

### LightGBM not available

```bash
uv add lightgbm
```

### GPU not detected

```bash
# Verifikasi CUDA
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

### Parquet seed validation fails

```bash
# Cek schema Parquet
uv run python -c "
import pyarrow.parquet as pq
schema = pq.read_schema('path/to/file.parquet')
print(schema)
"
```

---

## 8. Resource

- [pustaka/00-README.md](pustaka/00-README.md) — 94 dokumen pengetahuan pasar modal
- [MEGAPLAN.md](MEGAPLAN.md) — rencana implementasi 12 fase
- [AGENTS.md](AGENTS.md) — aturan AI global
- [docs/adr/](docs/adr/) — Architecture Decision Records
