# Project Rules: Pustaka Pasar Modal

## 1. Identitas & Tujuan Proyek

- Ini adalah **pustaka pengetahuan** (knowledge base) untuk pembangunan aplikasi pasar modal Indonesia/global.
- Basis pengetahuan berada di `<PROJECT_DIR>/pustaka/` — 96 dokumen Markdown bernomor `00-README.md` sampai `95-*.md`. Lihat §7 untuk padanan path per-OS.
- Pustaka ini mendukung pengembangan aplikasi **single-user (personal)**; fitur multi-user, KYC, RBAC, deployment publik, dan enterprise security adalah **tidak relevan** kecuali secara eksplisit diminta.
- Sumber implementasi referensi: `trading-system` v0.1.11 (asalnya `/home/petrick/projects/global/`; di Windows backup ada di `E:\trading_data\` — baca saja, jangan tulis/modifikasi).
- Path aplikasi: `<PROJECT_DIR>/` — database utama: `data/market_research.db` (~6 GB, dirakit dari part backup di external drive).

## 2. Keputusan Desain Tetap

- **Metodologi trading:** Algorithmic/Quantitative Trading (Quant). Target simulasi: Day Trading (jika bisa) dan Swing Trading (wajib). Scalping/HFT tidak dirancang — tidak ada data tick-level, tidak ada WebSocket streaming, tidak ada co-located server. Intraday polling 15-menit via yfinance cukup untuk monitoring Day Trading; EOD data + recompute pipeline adalah backbone untuk Swing Trading.
- **Bahasa UI:** Bahasa Indonesia; istilah teknis pasar modal (`ticker`, `OHLCV`, `RSI`, `MACD`, `VaR`, `P/E`, dll.) tetap dalam bahasa asli dengan tooltip Bahasa Indonesia.
- **Zona waktu:** penyimpanan UTC, tampilan WIB (UTC+7), memperhatikan jam perdagangan IDX dan DST pasar global.
- **GPU/CUDA:** setiap proses komputasi berat (LSTM, walk-forward, Monte Carlo, VaR, NLP/IndoBERT, ensemble) wajib memeriksa GPU `cuda:1` terlebih dahulu.
- **Data Parquet existing:** `<PARQUET_BASE>/trading_data/` adalah milik project `global`; baca saja, jangan tulis/modifikasi dari luar project tersebut. Backup tabel pustaka ada di `<PARQUET_BASE>/pustaka_data/archive/tables/`. Lihat §7 untuk path per-OS.

## 3. Aturan Kerja pada Pustaka

1. **Selalu mulai dari `pustaka/00-README.md`** untuk orientasi sebelum mengubah dokumen lain.
2. **Lakukan audit singkat** (read + grep) sebelum membuat/mengubah file; hindari duplikasi topik antar-dokumen.
3. **Update indeks README** setiap kali menambah/menghapus/mengganti nama dokumen.
4. **Gunakan Bahasa Indonesia** untuk narasi; kode dan nama konstanta tetap English.
5. **Sertakan sumber** (OJK, BEI/IDX, SEC, arxiv, yfinance, buku) untuk setiap klaim numerik atau regulasi.
6. **Cross-reference** dengan `pustaka/XX-nama-file.md#section` jika dokumen saling berkaitan.
7. **Jangan hardcode API key** atau kredensial broker; gunakan `.env` dan pastikan `.gitignore` memproteksinya.
8. **Tidak boleh menghapus** dokumen bernomor 01-91 tanpa persetujuan eksplisit; rename/drop hanya untuk file bantu (<90).

## 4. Pengelolaan Context & Memory (Wajib)

- Saat context window mendekati batas (~70% terpakai atau sebelum topik besar berganti), **segera buat checkpoint**:
  - Gunakan skill `/context-checkpoint` untuk menyimpan ringkasan ke `.devin/SESSION_MEMORY.md` dan/atau memory system.
  - Ringkasan harus mencakup: topik aktif, keputusan desain, file yang sudah diubah, tugas yang masih pending, dependensi antar-file.
- Jika melanjutkan sesi baru, **baca dulu `.devin/SESSION_MEMORY.md` dan memory** sebelum bertindak.
- Setiap perubahan aturan (rules), skill, atau workflow Devin/Cascade harus segera direfleksikan di `.devin/` dan di-memory-kan agar tidak hilang saat context reset.
- Hindari mengulang analisis dari awal; gunakan hasil checkpoint dan pustaka sebagai konteks dingin.

## 5. Keamanan & Keselamatan

- Tanyakan persetujuan user sebelum menjalankan perintah yang menghapus data, mengubah skema DB produksi, atau melakukan eksekusi trading nyata.
- Pantau path sensitif: `.env`, kredensial broker, private key, backup DB.
- Patuhi UU PDP (No. 27/2022) untuk data pribadi meskipun single-user.

## 6. Referensi Cepat

- Index & navigasi: `pustaka/00-README.md`
- Gap teori vs kode: `pustaka/88-gap-teori-vs-praktek.md`
- Audit faktor pasar modal: `pustaka/89-faktor-pasar-modal-analisis-implementasi.md`
- Audit data parquet: `pustaka/90-analisis-parquet-data-awal.md`
- Komoditas IDX: `pustaka/91-komoditas-spesifik-idx.md`
- Lifecycle environments: `pustaka/93-lifecycle-environments-real-testing-ai.md`
- Ticker suffix helper: `src/market/data/ticker_util.py` (`to_yf_ticker`, `from_yf_ticker`, `get_currency`)
- Cross-platform path helper: `src/market/paths.py` (`default_parquet_archive`, `default_external_data`, `default_parquet_seed`, `default_global_trading_data`)
- Sync DB → Parquet (hybrid incremental): `src/market/data/sync_to_parquet.py` (`sync_all`, `PARTITIONED_TABLES`, `REFERENCE_TABLES`, `RUNTIME_TABLES`), wrapper `scripts/sync_db_to_parquet.py`, state table `parquet_sync_state` (migration 0008). Lihat `pustaka/95-sync-db-to-parquet.md`.
- Migrasi SQLite → PostgreSQL: `docs/domino_effect_schema.sql` (DDL), `scripts/migrate_sqlite_to_pg.py` (migrasi), `scripts/backfill_broker_transactions.py` (backfill), `src/market/db/raw.py` (multi-DB helper). Lihat `pustaka/98-migrasi-sqlite-ke-postgresql.md`. Set `DATABASE_URL` di `.env` untuk switch backend.

## 7. Cross-Platform OS Awareness (Wajib)

Aplikasi ini dikembangkan di **dua OS developer**:

| OS | Project dir | Parquet base | External backup |
|----|-------------|--------------|-----------------|
| Linux | `/opt/lampp/htdocs/market/` | `/media/petrick/Parquet/` | `/media/petrick/Parquet/projects/market/` |
| Windows | `C:\xampp\htdocs\market\` | `E:\` (flashdisk) | `E:\projects\market\` |

### Aturan path:

1. **JANGAN hardcode path OS-spesifik** di kode Python. Gunakan `src/market/paths.py` yang memilih default berdasarkan `sys.platform`.
2. **Prioritas resolusi path:** env var (`.env`) > OS-aware default (`market.paths`) > CLI flag (`--seed-dir` dll).
3. **Gunakan `pathlib.Path`** untuk semua operasi path — otomatis handle separator (`/` vs `\`).
4. **Path di `.env`** boleh pakai `/` atau `\`; `pathlib` menormalisasi di kedua OS.
5. **Shell script** (`.sh`) tetap Linux-only; jika perlu automation Windows, buat padanan `.ps1` atau `.bat`.
6. **Docstring/komentar** boleh menyebut kedua path (Linux + Windows) untuk klarifikasi.

### File yang sudah OS-aware:

- `src/market/paths.py` — helper pusat (BARU)
- `src/market/config.py` — `parquet_archive_path` pakai `default_parquet_archive()`
- `src/market/data/import_missing_tables.py` — 3 path GLOBAL_* pakai `market.paths`
- `src/market/data/export_to_parquet.py` — baca dari `settings.parquet_archive_path`
- `src/market/data/sync_to_parquet.py` — hybrid incremental sync, output ke `settings.parquet_archive_path` (BARU)
- `scripts/seed_from_parquet.py` — `SEED_DIR` baca env `PARQUET_SEED_PATH` > OS-aware default
- `scripts/sync_db_to_parquet.py` — wrapper untuk `market.data.sync_to_parquet` (BARU)

## 8. Aturan Terminal & Command Output

- **JANGAN gunakan `tail`, `head -n`, `Select-Object -Last N`, atau `| head`** untuk memotong output command di terminal/Cascade.
- Output command harus **langsung terlihat penuh** di terminal agar developer dapat memverifikasi hasil tanpa membuka file tambahan.
- Jika output terlalu panjang dan sistem otomatis truncate, itu diizinkan (sistem menulis ke file overflow). Yang dilarang adalah **proaktif memotong** dengan `tail`/`head`/`-Last`/`-First`.
- Pengecualian: jika command menghasilkan ribuan baris (mis. `git log` panjang, `ls` direktori besar), gunakan filter yang spesifik (`grep`, `where`, `Select-String`) — bukan `tail`/`head` generik.

## 9. Aturan PowerShell Quoting (Wajib di Windows)

Berlaku saat `sys.platform == 'win32'` (machine ini: `C:\xampp\htdocs\market\`). Tujuan: menghindari parsing error saat exec tool melewatkan command ke PowerShell.

1. **Path selalu pakai single quote** — backslash aman di dalam single quote tanpa escaping:
   ```powershell
   python 'C:\xampp\htdocs\market\scripts\foo.py'
   Get-Content 'C:\xampp\htdocs\market\data\market_research.db'   # contoh
   ```
   JANGAN: `python "C:\xampp\htdocs\market\scripts\foo.py"` kecuali benar-benar butuh ekspansi variabel.

2. **Hindari `python -c "..."` dengan string kompleks.** Tulis ke file sementara lalu jalankan:
   ```powershell
   # BURUK: python -c "import json; print(json.dumps({'a': 'b \"x\"'}))"
   # BAIK:
   Set-Content -Path '_tmp_dev.py' -Value "import json; print(json.dumps({'a': 'b \"x\"'}))"
   python _tmp_dev.py
   Remove-Item _tmp_dev.py
   ```
   Konvensi nama file sementara: `_tmp_<tujuan>.py` (mis. `_tmp_check.py`, `_tmp_audit.py`) — sudah konsisten dengan file yang ada di repo.

3. **Multi-command: gunakan `;` (selalu jalan) atau `if ($?) { ... }` untuk conditional.** JANGAN pakai `&&` kecuali yakin PowerShell 7+ aktif:
   ```powershell
   # Aman di semua versi PS:
   python script.py; if ($?) { python next.py }
   # Hanya PS 7+:
   python script.py && python next.py
   ```

4. **Escape double-quote di dalam double-quoted string** pakai backtick `` `" `` ATAU gandakan `""`. JANGAN pakai `\"` (backslash bukan escape char di PowerShell):
   ```powershell
   "hallo `"dunia`""        # benar
   "hallo ""dunia"""        # benar (gandakan)
   "hallo \"dunia\""        # SALAH — string terpotong di \"
   ```

5. **Argumen mentah ke exe** (mengikuti konvensi cmd.exe): pakai token `--%`:
   ```powershell
   git --% config --global user.name "Foo Bar"
   ```

6. **Panggil exe dengan path ber-spasi** pakai call operator `&`:
   ```powershell
   & 'C:\Program Files\Python312\python.exe' script.py
   ```

7. **Line continuation** pakai backtick `` ` ``, bukan backslash:
   ```powershell
   Get-ChildItem `
     -Path 'C:\xampp\htdocs\market' `
     -Filter '*.py'
   ```

8. **Variabel & subexpression**: gunakan `$env:VAR` dan `$(...)` untuk ekspansi di dalam double-quote. Single-quote tidak mengekspansi apa pun.

9. **Verifikasi sebelum commit**: jika ragu apakah command akan parse benar, tulis dulu ke file `.ps1` sementara, jalankan, lalu hapus. Lebih aman daripada menebak nested quote.

### Referensi cepat
- Single quote `'...'` = literal (aman untuk path Windows).
- Double quote `"..."` = ekspansi `$var`, `$(...)`, `` `" `` escape.
- Backslash `\` = karakter biasa, BUKAN escape.
- Backtick `` ` `` = escape char PowerShell.
