# Session Memory — Pustaka Pasar Modal

## Checkpoint Sesi 2026-08-06 03:17 WIB

- **Alasan:** Selesai analisis 5 proposal dari AI lain, semua ditolak (sudah ada di kodebase). User akan mulai percakapan baru.
- **Topik aktif:** Intraday polling + prediction-vs-actual comparison + review proposal AI lain

### Keputusan Desain
- Metodologi: Quant/Algorithmic Trading. Target: Day Trading (intraday 15-min) + Swing Trading (EOD). Bukan HFT/Scalping.
- 5 proposal AI lain ditolak: (1) Quant module, (2) Global Market State, (3) Parquet+Polars, (4) Streamlit dashboard, (5) XGBoost ML handler — semua sudah ada versi lebih lengkap di kodebase.

### File Dimodifikasi Sesi Ini
- `src/market/scheduler.py` — tambah schedule `every_15min`
- `src/market/scheduler_tasks.py` — tambah `_task_fetch_intraday` + `INTRADAY_TICKERS` + register task
- `src/market/pipelines/data_fetch.py` — tambah `on_intraday_requested` handler
- `src/market/core/wiring.py` — wire `data.fetch.intraday.requested`
- `src/market/data/yahoo_adapter.py` — tambah `interval` parameter di `fetch_ohlcv`
- `src/market/api/routes_prices.py` (BARU) — 3 endpoint: `/api/prices/latest`, `/api/prices/intraday/trigger`, `/api/prices/compare/{ticker}`
- `src/market/api/app.py` — register prices router + update endpoint inventory
- `tests/test_intraday.py` (BARU) — 11 test cases
- `tests/test_cli.py` — update task count 10→11
- `MEGAPLAN.md` — tambah intraday polling + prediction comparison di Next Steps + Out of Scope HFT + Constraints
- `AGENTS.md` — tambah metodologi trading di Keputusan Desain Tetap
- `.devin/SESSION_MEMORY.md` — update status + fitur baru

### Test Status
- `tests/test_intraday.py` — 11 passed (11 detik)
- Full test suite belum selesai di-run (di-cancel user untuk paste chat AI lain)
- Ruff check: clean untuk file baru/modifikasi
- TODO: jalankan full test suite di sesi berikutnya

### Pending
- Jalankan full `pytest tests/` untuk verifikasi semua test pass
- Update `pustaka/` jika ada dokumen yang perlu cross-reference dengan intraday polling

## Ringkasan Proyek

- Pustaka ini adalah knowledge base untuk membangun aplikasi pasar modal (global & Indonesia), terutama decision-support EOD untuk single-user.
- Keputusan desain tetap: UI Bahasa Indonesia + tooltip, timezone WIB display / UTC storage, single-user (no RBAC/JWT), GPU `cuda:1` untuk komputasi berat, `.env` untuk kredensial.
- Implementasi referensi: `trading-system` v0.1.11 di `/home/petrick/projects/global/` (boleh diadopsi/dicopy).

## Hasil Audit Pustaka (2026-08-06)

- **Total dokumen:** 94 file Markdown (`00-README.md` s/d `93-lifecycle-environments-real-testing-ai.md`).
- **Indeks `00-README.md`** sudah mencakup dokumen 87–93.
- **Tidak ada link internal markdown yang rusak**.
- **Cross-check pustaka vs DB:** pustaka `18` & `90` mendokumentasikan `esg_scores` (164) dan `corporate_governance` (208) — sekarang sudah sesuai (tabel dibuat & di-seed).
- **Beberapa angka rows di pustaka `18` kedaluwarsa** (fear_greed 466→1178, technical_indicators 11.136→9.690, stock_personality 944→925) — perlu update dokumen.

## Hasil Cleanup Database (2026-08-06)

### 8 Masalah Kualitas Data — SEMUA DIPERBAIKI

| # | Masalah | Sebelum | Sesudah |
|---|---|---|---|
| 1 | Ticker suffix inconsistency | 976/990 match | 990/990 match |
| 2 | OHLC anomalies | 796 rows | 0 rows |
| 3 | volume=0 tidak di-flag | 523K unflagged | 232K flagged dqs=0.3 |
| 4 | Timestamp jam + gap | 7,344 bad ts, gap 24 hari | 0 bad ts, gap terisi (882 backfill) |
| 5 | sector_master duplikasi | 22 rows (2 sistem) | 11 rows (1 sistem) |
| 6 | market_calendar hanya 2026 | 365 rows | 9,773 rows (2000-2026) |
| 7 | fundamental_data nilai 0 | pe/pb/roe/eps = 0 | Nilai real (pe=5.54, pb=20403, roe=0.21) |
| 8 | ESG & CG tidak ada | 0 rows | esg: 164, cg: 208 |

### File Baru/Dimodifikasi

- `src/market/data/cleanup_data.py` (baru) — Script cleanup 8 fix, idempotent.
- `src/market/db/models.py` — Tambah `ESGScore` & `CorporateGovernance` models.
- `alembic/versions/0002_add_esg_governance.py` (baru) — Migration 2 tabel baru.
- `docs/AUDIT-FINDINGS.md` — Tambah section "Data Quality Cleanup".

### Database Status Pasca-Cleanup

| DB | Ukuran | Tabel | Rows | Status |
|---|---|---|---|---|
| `market_paper.db` | 839 MB | 23 | 3,070,605 | ✅ Bersih, lengkap |
| `market_research.db` | 839 MB | 23 | 3,070,605 | ✅ Di-seed dari paper |
| `market_live.db` | 268 KB | 21 | 1 | Sesuai (Live belum aktif) |

### Backup

- `data/backups/market_paper.db.pre-cleanup-20260806-000825.db` (825 MB)
- `data/backups/market_research.db.pre-seed-20260806-001740.db` (268 KB)

## Status Implementasi Terkini

- **Sync GitHub:** ✅ Commit `4843e52` (per audit 2026-08-05).
- **Backend Quality:** ✅ 760+ tests pass, coverage 76%+, `ruff check .` clean.
- **Frontend Build:** ✅ `npm run build` sukses (Next.js 15.5.22, 12 halaman).
- **Database:** ✅ Semua 3 DB siap. Paper & Research ter-seed penuh, Live kosong (sesuai).
- **Scheduler:** ✅ 11 tasks terdaftar (fetch_intraday, fetch_eod, fetch_global, fetch_macro, health_check, quality_check, recompute, feature_store, drift_detection, generate_reports, export_parquet).
- **Model registry:** ✅ Baseline model trained (fallback mode, PyTorch belum diinstall).
- **Environment File:** ✅ `.env` dibuat dengan `ENV=paper`, `BROKER_ADAPTER=paper`.

## Fitur Baru (Sesi 2026-08-06)

### TickerScreener — Screening sebelum fetch
- File: `src/market/data/screener.py`
- Filter 5 lapis: active status, delisting_date, trading suspension, AI block (DelistingMemory), liquidity score
- Terintegrasi di `DataFetchPipeline.on_fetch_requested` — hanya fetch ticker yang lolos screening
- Test: `tests/test_screener.py` (9 test cases)

### Intraday Polling — 15-menit via yfinance
- File: `src/market/pipelines/data_fetch.py::on_intraday_requested`
- Scheduler task `fetch_intraday` dengan schedule `every_15min`
- Polling ~13 ticker penting (IDX + global indices + commodities)
- Store ke OHLCV dengan `timeframe='15m'`
- Event: `data.fetch.intraday.requested` → `data.fetch.intraday.completed`
- Wiring: `src/market/core/wiring.py` sudah subscribe handler

### Endpoint API Baru
- `GET /api/prices/latest` — snapshot harga intraday terbaru dari DB
- `POST /api/prices/intraday/trigger` — trigger manual intraday fetch
- `GET /api/prices/compare/{ticker}` — bandingkan prediksi vs harga aktual
- File: `src/market/api/routes_prices.py`
- Test: `tests/test_intraday.py` (11 test cases)

### YahooFinanceAdapter — interval parameter
- `src/market/data/yahoo_adapter.py::fetch_ohlcv` sekarang menerima `interval` parameter (default "1d", support "15m", "5m")

## Keputusan Desain: Metodologi Trading

- **Algorithmic/Quantitative Trading (Quant)** — bukan HFT, bukan Scalping
- Target simulasi: **Day Trading** (jika bisa, dengan intraday 15-min polling) dan **Swing Trading** (wajib, dengan EOD data + recompute pipeline)
- Scalping/HFT tidak dirancang: tidak ada data tick-level, tidak ada WebSocket streaming, tidak ada co-located server
- Frontend cukup REST + SWR polling, tidak perlu real-time tick chart
- Prediction engine (ensemble: MA, momentum, pattern, vol-adjusted) cocok untuk Swing Trading horizon (1-5 hari)

## Human-Gate Checklist (MEGAPLAN §6.4)

- [x] Migrasi `market_live.db` — 21 tabel berhasil di-migrate.
- [x] Install dependency sistem — openpyxl, reportlab, pyarrow sudah terpasang.
- [x] Security config — single-user local, `.env` + `.gitignore` sudah ada.
- [x] Seed `market_paper.db` — ✅ 3,070,605 rows dari parquet_archive.
- [x] **Cleanup kualitas data `market_paper.db`** — ✅ 8 masalah diperbaiki (2026-08-06).
- [x] **Seed `market_research.db`** — ✅ Mirror dari paper (2026-08-06).
- [x] **Tambah tabel `esg_scores` & `corporate_governance`** — ✅ Migration 0002 + import parquet.
- [ ] **Update pustaka `18` & `90`** — angka rows kedaluwarsa (fear_greed, technical_indicators, stock_personality).
- [ ] **Broker real activation** — form disiapkan di FE settings, perlu approval token.
- [ ] **Deploy ke cloud/VPS** — local-only untuk sekarang.
- [ ] **Model champion di Live** — CLI `market model promote/rollback` siap, perlu eval-gate pass.

## Tugas / Next Steps yang Masih Terbuka

### Segera (prioritas tinggi)
1. **Update pustaka `18-modul-engine-data-wajib.md`** — koreksi angka rows kedaluwarsa (fear_greed 466→1178, technical_indicators 11.136→9.690, stock_personality 944→925). Tambahkan dokumentasi untuk `esg_scores` & `corporate_governance` yang sekarang sudah ada di DB.
2. **Recompute technical_indicators & scores** — sedang berjalan via `recompute_internal.py` dengan data bersih.
3. **Upgrade frontend dependencies** jika ada vulnerability baru.

### Sedang (setelah data bersih)
4. **Register scheduler tasks** — ✅ sudah 5 tasks. Pastikan task cleanup_data terjadwal.
5. **Jalankan paper trading 30 hari** minimum sebelum live gate.
6. **Latih dan daftarkan model champion** pertama di Paper environment (PyTorch install needed).

### Panjang
7. **Broker real activation** setelah paper trading memadai.
8. **Deploy ke cloud/VPS** setelah dinyatakan layak live.

## Referensi Kunci

- `pustaka/00-README.md` — indeks dan keputusan desain.
- `pustaka/18-modul-engine-data-wajib.md` — daftar modul, engine, data wajib (perlu update angka).
- `pustaka/88-gap-teori-vs-praktek.md` — audit gap teori vs praktek.
- `pustaka/89-faktor-pasar-modal-analisis-implementasi.md` — audit faktor pasar modal.
- `pustaka/90-analisis-parquet-data-awal.md` — audit data parquet awal (perlu update angka).
- `pustaka/91-komoditas-spesifik-idx.md` — komoditas IDX.
- `pustaka/92-multi-market-multi-asset-trading-system.md` — multi-market & multi-asset blueprint.
- `pustaka/93-lifecycle-environments-real-testing-ai.md` — lifecycle environment & promotion gates.
- `docs/AUDIT-FINDINGS.md` — laporan audit aplikasi + data quality cleanup.
- `src/market/data/cleanup_data.py` — script cleanup 8 fix (idempotent).
