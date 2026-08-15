# Project Rules: Pustaka Pasar Modal

## 1. Identitas & Tujuan Proyek

- Ini adalah **pustaka pengetahuan** (knowledge base) untuk pembangunan aplikasi pasar modal Indonesia/global.
- Basis pengetahuan berada di `<PROJECT_DIR>/pustaka/` — 103 dokumen Markdown bernomor `00-README.md` sampai `102-*.md`. Lihat §7 untuk padanan path per-OS.
- Pustaka ini mendukung pengembangan aplikasi **single-user (personal)**; fitur multi-user, KYC, RBAC, deployment publik, dan enterprise security adalah **tidak relevan** kecuali secara eksplisit diminta.
- Sumber implementasi referensi: `trading-system` v0.1.11 (asalnya `/home/petrick/projects/global/`; di Windows backup ada di `E:\trading_data\` — baca saja, jangan tulis/modifikasi).
- Path aplikasi: `<PROJECT_DIR>/` — database utama: PostgreSQL 16 (`postgresql://petrick:market_dev@localhost:5432/market` atau via Unix socket `postgresql+psycopg2:///market?host=/var/run/postgresql`), ~6.6 GB, 83 tables + 5 views (3 compatibility views: `instrument_master`, `market_registry`, `market_calendar`). Alembic head = 0023. Migrasi SQLite → PostgreSQL selesai (lihat `pustaka/98-migrasi-sqlite-ke-postgresql.md`); file `data/market_research.db` sudah tidak ada. Set `DATABASE_URL` di `.env` untuk koneksi PG. SQLite fallback hanya untuk unit test fixture scratch.

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
8. **Tidak boleh menghapus** dokumen bernomor 01-100 tanpa persetujuan eksplisit; rename/drop hanya untuk file bantu (<90).

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
- AI/ML audit framework: `pustaka/96-ai-ml-audit-framework.md`
- Strategi alternatif & ekspansi data: `pustaka/97-strategi-alternatif-ekspansi-data-2026.md`
- Matriks relevansi satelit: `pustaka/99-matriks-relevansi-satelit-pasar-modal.md`
- Astronacci time cycle: `pustaka/100-astronacci-time-cycle-integration.md`
- Global-IDX advanced models: `pustaka/101-global-idx-advanced-models.md` (DCC-GARCH, Diebold-Yilmaz, Foreign Flow, Overnight IDX)
- Sector-global link engine: `pustaka/102-sector-global-link-engine.md` (sektor-specific global driver dengan timezone lag)
- Ticker suffix helper: `src/market/data/ticker_util.py` (`to_yf_ticker`, `from_yf_ticker`, `get_currency`)
- Cross-platform path helper: `src/market/paths.py` (`default_parquet_archive`, `default_external_data`, `default_parquet_seed`, `default_global_trading_data`)
- GPU/CPU device dispatch: `src/market/compute/device.py` (`select_device`, VRAM check, workload-type routing)
- Sync DB → Parquet (hybrid incremental): `src/market/data/sync_to_parquet.py` (`sync_all`, `PARTITIONED_TABLES`, `REFERENCE_TABLES`, `RUNTIME_TABLES`), wrapper `scripts/sync_db_to_parquet.py`, state table `parquet_sync_state` (migration 0008). Lihat `pustaka/95-sync-db-to-parquet.md`.
- Migrasi SQLite → PostgreSQL: `docs/domino_effect_schema.sql` (DDL), `scripts/migrate_sqlite_to_pg.py` (migrasi), `scripts/backfill_broker_transactions.py` (backfill), `src/market/db/raw.py` (multi-DB helper). Lihat `pustaka/98-migrasi-sqlite-ke-postgresql.md`. Set `DATABASE_URL` di `.env` untuk switch backend.
- Modul analisis baru: `src/market/analysis/` — `astronacci.py`, `macro_correlation.py`, `strategy_selector.py`, `pairs_trading.py`, `volume_features.py`, `policy_event_scorer.py`, `sector_rotation.py`, `signal_enhancer.py`, `meta_labeling.py`, `news_sentiment.py`, `cross_market_timezone.py`, `execution_analyzer.py`, `alpha_signals.py` (4 alpha signal engines: mean_reversion, reversal, ewma_momentum, regime_switch)
- Modul data baru: `src/market/data/` — `macro_data_fetcher.py`, `satellite_fetcher.py`, `refresh_stale.py`, `timestamp_validation.py`
- API routes baru: `src/market/api/routes_notifications.py`, `src/market/api/routes_recompute.py`
- Migrations: 0001-0023 (alembic head = 0023). Lihat `alembic/versions/`. Migration 0022: normalisasi database (drop `broker`/`broker_bursa`, merge `market_registry`→`exchanges`, merge `instrument_master`→`instruments`, drop prediction columns dari `stock_personality`, add FK constraints). Lihat `docs/DATABASE_NORMALIZATION_0022.md`. Migration 0023: merge `market_calendar`→`exchange_holidays` (compatibility view dibuat).
- Engine ablation framework: `src/market/ablation/` — `engine_registry.py` (42 engine terdaftar: 28 enabled + 14 disabled; 25 SignalEnhancer + 13 MarketContext + 4 PredictionCore), `isolated_backtest.py` (isolasi per-engine, paired t-test, turnover-proportional cost model), `scorecard.py` (KEEP/MARGINAL/REMOVE verdict, Bonferroni correction, Fisher's method p-value aggregation), `ablation_report.py` (JSON report + DB persistence: `save_to_db()`, `load_latest_verdicts()`, `list_ablation_runs()`), `data_checker.py` (pre-flight data validation, per-engine min_data_days, cross-data duration awareness). Runner: `scripts/engine_ablation/run_ablation.py`. Tests: `tests/ablation/` (93 tests). DB tables: `ablation_runs` + `ablation_scorecards` (migration 0020). Lihat `pustaka/96-ai-ml-audit-framework.md` (Pilar 2), `pustaka/101-global-idx-advanced-models.md`, `pustaka/102-sector-global-link-engine.md`.
- Batch data ingestion scripts (P1–P9, eksekusi 15 Agustus 2026): `scripts/batch_p1_commodity.py` (komoditas: CL=F, CPO=F, GC=F, HG=F, MTF=F, NICK.L, TIN.L → `stock_prices` + `macro_data` + `commodity_to_stock_map`), `scripts/batch_p2_event_cleaning.py` (cleaning `external_events` + verify `PolicyEventScorer`), `scripts/batch_p3_seasonal.py` (seasonal pattern engine → `seasonal_patterns`), `scripts/batch_p4_earnings_calendar.py` (forward earnings calendar → `earnings_calendar`), `scripts/batch_p5_macro_id.py` (World Bank macro ID → `macro_data` + `macroeconomic_indicators`), `scripts/batch_p6_spillover.py` (DCC-GARCH → `dcc_garch_results`; Diebold-Yilmaz spillover → `causal_graphs`), `scripts/batch_p7_sector_cleanup.py` (sector taxonomy normalization di `instrument_master`), `scripts/batch_p8_satellite.py` (NASA POWER weather → `satellite_observations` + `satellite_ticker_locations`), `scripts/batch_p9_causal.py` (Granger causality → `causal_relationships` + `causal_graphs`).
- DB tables baru (via CREATE TABLE IF NOT EXISTS di scripts, bukan Alembic migration): `seasonal_patterns`, `earnings_calendar`, `dcc_garch_results`, `commodity_to_stock_map`. Lihat §6 untuk detail.
- DecisionEngine market driver narrative: `src/market/analysis/decision.py` — `DecisionEngine(db_url=...)` sekarang menghasilkan `market_driver_context: list[str]` di `DecisionResult` yang berisi narrative Bahasa Indonesia dari 5 sumber: causal_relationships, seasonal_patterns, commodity_to_stock_map, dcc_garch_results, satellite_observations. Graceful degradation jika db_url=None.
- MEGAPLAN: `MEGAPLAN.md` — eksekusi multi-fase, gunakan skill `/megaplan-executor`.

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
   Get-Content 'C:\xampp\htdocs\market\.env'   # contoh
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
