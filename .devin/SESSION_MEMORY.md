# Session Memory — Pustaka Pasar Modal

## Checkpoint Terbaru

- **Waktu:** 2026-08-06 00:20 WIB (sesi cleanup data quality).
- **Alasan:** Audit pustaka + database menemukan 8 masalah kualitas data; semua diperbaiki batch.
- **Perubahan signifikan:** `market_paper.db` & `market_research.db` sekarang bersih dan lengkap (3,070,605 rows, 23 tabel).

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
- **Backend Quality:** ✅ 719 tests pass, coverage 83.77%, `ruff check .` clean, `mypy` clean.
- **Frontend Build:** ✅ `npm run build` sukses (Next.js 15.5.22, 12 halaman).
- **Database:** ✅ Semua 3 DB siap. Paper & Research ter-seed penuh, Live kosong (sesuai).
- **Scheduler:** ✅ 5 tasks terdaftar (fetch_eod, quality_check, feature_store, drift_detection, generate_reports).
- **Model registry:** ✅ Baseline model trained (fallback mode, PyTorch belum diinstall).
- **Environment File:** ✅ `.env` dibuat dengan `ENV=paper`, `BROKER_ADAPTER=paper`.

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
