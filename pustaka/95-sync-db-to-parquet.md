# Sync Database ke Parquet (Hybrid Incremental)

> **Desain dan implementasi sinkronisasi incremental dari SQLite database aplikasi ke Parquet archive, menggantikan full-export yang menulis ulang seluruh data setiap kali dijalankan.**

---

## 1. Latar Belakang & Motivasi

### 1.1 Masalah dengan Full Export

Sebelumnya, sinkronisasi DB → Parquet dilakukan dengan dua script full-export:

1. `scripts/export_db_to_parquet.py` — raw dump tanpa kompresi, tanpa drop kolom bookkeeping (`id`, `created_at`, `updated_at`), hardcoded `E:/`.
2. `src/market/data/export_to_parquet.py` — full export dengan snappy compression, drop kolom bookkeeping, rename kolom `pe`→`pe_ratio` dll, OS-aware path via `settings.parquet_archive_path`.

Keduanya menulis ulang **seluruh** data setiap kali dijalankan. Untuk database ~6 GB dengan 5.580.129 baris (41 tabel), ini mahal:

- Tabel besar: `ohlcv` 3.024.934 rows, `foreign_flow` 1.253.802 rows, `daily_trading_stats` 1.082.968 rows.
- **`E:\` adalah flashdisk** (AGENTS.md §7) — write endurance terbatas, menulis 5.5M rows berkali-kali mempercepat keausan.
- Tidak ada cara untuk menjalankan sync lebih sering (mis. setelah fetch harian) tanpa beban I/O besar.

### 1.2 Mengapa Sync Inkremental Tidak Trivial

Parquet adalah format **immutable columnar** — tidak mendukung update in-place. "Upsert" = rewrite file/row-group. Oleh karena itu, sync inkremental yang efisien memerlukan **partisi** sehingga hanya partisi baru yang ditulis ulang.

Kompleksitas tambahan:

- **Deteksi perubahan tidak seragam.** Hanya 6 tabel punya `updated_at` dengan `onupdate=_utcnow` (instrument_master, corporate_actions, source_health, stock_personality, system_state, scheduler_state). Tabel besar time-series (`ohlcv`, `foreign_flow`, `daily_trading_stats`, `macro_data`, `fx_rates`, `fear_greed`) tidak punya `updated_at` — mereka append-only.
- `data_watermark` cuma 152 rows, per `(ticker, table_name)` — belum cover semua tabel, dan tidak ada kolom "last_synced_to_parquet".
- Tabel reference kecil mutable (instrument_master, fundamental_data, esg_scores, dll) — walau kecil, row-nya bisa berubah/hapus. Sync butuh merge logic, dan akhirnya tetap rewrite file.

### 1.3 Solusi: Hybrid Strategy

Bukan "ganti export jadi sync" secara biner, tapi **hybrid** berdasarkan karakteristik tabel:

| Kategori | Strategi | Alasan |
|----------|----------|--------|
| Time-series besar append-only | **Partitioned Parquet by `year`/`month`** + watermark tracking | Hindari rewrite 3M rows; flashdisk awet |
| Reference kecil mutable | **Full rewrite** (snappy) | Simpel, murah (<70k rows total) |
| Runtime kosong | Skip atau full rewrite trivial | 0 rows |

---

## 2. Klasifikasi Tabel

Berdasarkan audit `src/market/db/models.py` (41 user tables + 2 infra):

### 2.1 Partitioned Time-Series (19 tabel)

Tabel append-only dengan kolom date natural. Partisi Hive `year=YYYY/month=MM`.

| Tabel | partition_col | Rename map |
|-------|---------------|------------|
| `ohlcv` | `timestamp` | — |
| `corporate_actions` | `ex_date` | — |
| `dividends` | `ex_date` | — |
| `market_calendar` | `date` | — |
| `fx_rates` | `date` | — |
| `fundamental_data` | `date` | `pe`→`pe_ratio`, `pb`→`pb_ratio`, `der`→`debt_to_equity`, `eps`→`earnings_per_share`, `net_income`→`net_profit` |
| `macro_data` | `date` | — |
| `foreign_flow` | `date` | — |
| `daily_trading_stats` | `date` | — |
| `technical_indicators` | `date` | — |
| `broker_flow` | `date` | — |
| `pattern_analysis` | `date` | — |
| `valuation_cache` | `date` | — |
| `ml_labels` | `date` | — |
| `market_regimes` | `date` | — |
| `policy_events` | `tanggal` | — |
| `external_events` | `tanggal` | — |
| `fear_greed` | `tanggal` | — |
| `audit_log` | `created_at` | — (created_at di-keep sebagai event time, tidak di-drop) |

### 2.2 Reference Full-Rewrite (12 tabel)

Tabel kecil dan/atau mutable. Full rewrite dengan snappy compression setiap run.

`market_registry`, `instrument_master`, `sector_master`, `scores`, `relationship_matrix`, `stock_personality`, `esg_scores`, `corporate_governance`, `source_health`, `news`, `trading_suspensions`, `data_watermark`.

### 2.3 Runtime (10 tabel)

Skip ketika kosong, full rewrite ketika non-empty (tiny).

`positions`, `orders`, `equity_snapshots`, `daily_risk_metrics`, `trade_journal`, `ai_weights`, `render_log`, `watchlist`, `system_state`, `scheduler_state`.

### 2.4 Skip (2 tabel)

`parquet_sync_state` (self-reference), `alembic_version` (infra).

---

## 3. Skema Partisi Parquet

**Hive-style partitioning** dengan `year`/`month`:

```
<parquet_archive>/archive/tables/
├── ohlcv/
│   ├── year=2024/
│   │   ├── month=01/
│   │   │   └── data.parquet
│   │   ├── month=02/
│   │   │   └── data.parquet
│   │   └── ...
│   └── year=2025/
│       └── ...
├── foreign_flow/
│   └── year=YYYY/month=MM/data.parquet
├── instrument_master.parquet          # reference: flat file
├── market_registry.parquet            # reference: flat file
└── ...
```

**Keuntungan Hive partitioning:**

- Kompatibel dengan `pyarrow.dataset` — query filter otomatis push-down per partisi.
- Hanya partisi dalam window sync yang ditulis ulang.
- Migrasi dari flat file lama: jalankan sync pertama dengan `--full-rewrite` flag untuk bootstrap, lalu sync inkremental normal.

---

## 4. Sync State Tracking

Tabel baru `parquet_sync_state` (migration `0008`) melacak state per tabel:

| Kolom | Tipe | Deskripsi |
|-------|------|-----------|
| `table_name` | VARCHAR(50) PK | Nama tabel |
| `sync_mode` | VARCHAR(20) | `partitioned` atau `full_rewrite` |
| `partition_col` | VARCHAR(50) | Kolom date untuk partisi (NULL untuk full_rewrite) |
| `last_synced_date` | DATE | MAX(partition_col) yang sudah disync (NULL untuk full_rewrite) |
| `last_synced_at` | DATETIME | Timestamp run terakhir |
| `last_row_count` | INTEGER | Rows di run terakhir |
| `total_partitions_written` | INTEGER | Akumulasi partisi yang pernah ditulis |
| `updated_at` | DATETIME | Auto-update via `onupdate` |

### 4.1 Algoritma Sync Partitioned

```
1. Baca parquet_sync_state untuk tabel ini.
2. Jika last_synced_date is None (initial sync):
   - Tulis SEMUA partisi yang ada di DB.
3. Jika last_synced_date ada:
   - Hitung cutoff = last_synced_date - safety_days (default 7).
   - Tulis partisi dengan date >= cutoff (catch late corrections).
   - Tulis juga partisi DB yang belum ada di disk (catch-up).
4. Update parquet_sync_state dengan MAX(partition_col) yang dilihat.
```

**Safety window** (default 7 hari) menangani koreksi/insert terlambat — baris dengan date dalam 7 hari terakhir selalu ditulis ulang untuk memastikan konsistensi.

### 4.2 Algoritma Sync Full-Rewrite

```
1. SELECT COUNT(*) FROM tabel.
2. Jika 0: skip, update state.
3. Jika > 0: SELECT *, drop bookkeeping cols, rename, write to <tabel>.parquet.
4. Update parquet_sync_state.
```

---

## 5. Implementasi

### 5.1 File yang Dibuat/Dimodifikasi

| File | Aksi | Deskripsi |
|------|------|-----------|
| `src/market/db/models.py` | Modified | Tambah class `ParquetSyncState` |
| `alembic/versions/0008_parquet_sync_state.py` | Created | Migration tabel `parquet_sync_state` |
| `alembic/env.py` | Modified | Tambah `connect_args={"timeout": 30}` untuk handle DB lock |
| `src/market/data/sync_to_parquet.py` | Created | Modul sync hybrid (529 lines) |
| `scripts/sync_db_to_parquet.py` | Created | Wrapper script untuk CLI |
| `pustaka/95-sync-db-to-parquet.md` | Created | Dokumen ini |
| `pustaka/00-README.md` | Modified | Tambah entry 95 |
| `AGENTS.md` | Modified | Update §1 (jumlah dokumen) & §7 (file OS-aware) |

### 5.2 Penggunaan CLI

```powershell
# Sync inkremental normal (default)
python scripts/sync_db_to_parquet.py

# Dry run (lihat apa yang akan disync tanpa menulis)
python scripts/sync_db_to_parquet.py --dry-run

# Sync hanya satu tabel
python scripts/sync_db_to_parquet.py --table ohlcv

# Force full-rewrite untuk semua tabel (bootstrap dari flat file lama)
python scripts/sync_db_to_parquet.py --full-rewrite

# Custom safety window
python scripts/sync_db_to_parquet.py --safety-days 14
```

### 5.3 Sebagai Python Module

```python
from market.data.sync_to_parquet import sync_all, print_summary

results = sync_all(safety_days=7, only_table="ohlcv")
print_summary(results)
```

---

## 6. Kompatibilitas dengan migrate_parquet.py

`src/market/data/migrate_parquet.py` adalah inverse: baca Parquet → insert ke SQLite. Saat ini `migrate_parquet.py` membaca **flat files** (`ohlcv.parquet`, dll).

**Perubahan format partitioned akan break `migrate_parquet.py`** karena:

- `migrate_ohlcv()` membaca `ARCHIVE_TABLES / "ohlcv.parquet"` (flat).
- Setelah sync partitioned, file flat diganti dengan direktori `ohlcv/year=YYYY/month=MM/data.parquet`.

**Strategi migrasi konsumen:**

1. **Pendekatan bertahap (rekomendasi):** Jalankan sync pertama dengan `--full-rewrite` untuk menghasilkan flat files yang kompatibel dengan `migrate_parquet.py` existing. Setelah semua konsumen di-update, jalankan sync partitioned normal.
2. **Update `migrate_parquet.py`:** Ganti `pd.read_parquet(path)` dengan `pyarrow.dataset.dataset(partition_root, partitioning="hive").to_table().to_pandas()` untuk membaca partisi Hive.

**Catatan pre-existing mismatch:** `migrate_parquet.py` membaca `PE`/`PB` (uppercase, skema global) sementara `export_to_parquet.py` menulis `pe_ratio` (rename). Ini adalah bug pre-existing, bukan diperkenalkan oleh sync ini. Sync partitioned mengikuti konvensi `export_to_parquet.py` (rename `pe`→`pe_ratio`).

---

## 7. Cross-Platform Path Awareness

Mengikuti AGENTS.md §7:

- Output path: `settings.parquet_archive_path` → `default_parquet_archive()` dari `src/market/paths.py`.
- Linux: `/media/petrick/Parquet/pustaka_data/archive/tables/`
- Windows: `E:/pustaka_data/archive/tables/`
- Tidak ada path OS-spesifik yang di-hardcode di `sync_to_parquet.py`.

---

## 8. Testing & Verifikasi

### 8.1 Syntax & Import Check

```powershell
python -m py_compile src/market/data/sync_to_parquet.py
python -m py_compile scripts/sync_db_to_parquet.py
python -m py_compile alembic/versions/0008_parquet_sync_state.py
```

Semua OK.

### 8.2 Dry Run Test

```powershell
python scripts/sync_db_to_parquet.py --dry-run --table instrument_master
```

### 8.3 Full Sync Test

```powershell
# Bootstrap (flat files, kompatibel dengan migrate_parquet.py)
python scripts/sync_db_to_parquet.py --full-rewrite

# Sync inkremental normal
python scripts/sync_db_to_parquet.py
```

### 8.4 Verifikasi Output

```powershell
# Cek struktur direktori partitioned
Get-ChildItem 'E:\pustaka_data\archive\tables\ohlcv' -Recurse -Filter data.parquet

# Cek sync state di DB
python -c "import sqlite3; c=sqlite3.connect('data/market_research.db'); print(c.execute('SELECT * FROM parquet_sync_state').fetchall())"
```

---

## 9. Relasi dengan Dokumen Lain

- `pustaka/18-modul-engine-data-wajib.md` §13 — skema database asli, termasuk `data_watermark`.
- `pustaka/22-data-engineering-pipeline.md` — pipeline data engineering, Parquet storage architecture.
- `pustaka/90-analisis-parquet-data-awal.md` — analisis awal struktur Parquet archive.
- `pustaka/93-lifecycle-environments-real-testing-ai.md` — environment isolation (sync berjalan di research env).
- `AGENTS.md` §7 — cross-platform path awareness.
- `src/market/data/export_to_parquet.py` — predecessor full-export (masih ada, untuk fallback).
- `src/market/data/migrate_parquet.py` — inverse (Parquet → DB), perlu update untuk baca partitioned.

---

## 10. Roadmap Lanjutan

1. **Update `migrate_parquet.py`** untuk baca Hive partitioned dataset (pyarrow.dataset).
2. **Integrasi ke scheduler** — jalankan sync otomatis setelah fetch harian (lihat `pustaka/84-new-data-arrival-processing-pipeline.md`).
3. **API endpoint** `/sync/parquet` di `routes_data.py` untuk trigger sync via UI.
4. **Verifikasi integritas** — bandingkan row count DB vs Parquet per partisi sebagai smoke test.
5. **Compaction** — merge partisi lama ke file yang lebih besar (mis. yearly) untuk reduce file count.

---

## 11. Sumber

- Apache Parquet documentation — partitioned datasets.
- pyarrow.dataset API — Hive partitioning support.
- AGENTS.md §7 — cross-platform path conventions.
- López de Prado, "Advances in Financial Machine Learning" — labeling & data pipeline best practices.
- Internal audit: `src/market/db/models.py` (41 user tables), `src/market/data/export_to_parquet.py` (predecessor), `src/market/data/migrate_parquet.py` (inverse consumer).
