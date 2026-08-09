# Session Memory — Pustaka Pasar Modal

## Checkpoint Sesi 2026-08-09 14:43 WIB — Production Pipeline Result

- **Topik aktif:** Production pipeline real DB selesai, portfolio belum lolos KEEP, rencana lanjutan
- **Pipeline:** `run_production_pipeline.sh` — Step 1 selesai (14 jam, 20 ticker, exit code 1), Step 2-3 abort
- **Hasil:** Score 3.71/5.00, Alpha ≈ 0, Sharpe -10.0, Promoted KEEP = False
- **Root cause:** Inverse-variance weighting collapse ke BVIC.JK (AcceptRate=0%, zero variance)
- **File generated:** `best_ticker_quant_config.json` (26 KB), `portfolio_data_remediation_report.json` (31 KB)
- **File belum ada:** `final_portfolio_verdict.json` (Step 3 tidak jalan)
- **Rencana:** Fix IV weighting → re-run pipeline → daily signal cron → git push
- **File rencana:** `RENCANA-LANJUTAN-PRODUCTION-PIPELINE.md` (baru dibuat)
- **Top 4 ticker Alpha positif:** UNTR.JK (+0.115), SONA.JK (+0.090), APLI.JK (+0.087), BCIC.JK (+0.068)
- **Script production:** `scripts/run_production_pipeline.sh`, `scripts/daily_signal_cron.py`
- **Git:** Commit `f898cf6` (37 file, 19,237 baris) sudah push ke GitHub
- **Wait-shutdown script:** CANCELED (pipeline exit 1, shutdown tidak terjadi)
- **Crontab:** Belum di-install (daily signal cron belum terjadwal otomatis)

### File yang berubah sesi ini:
- `RENCANA-LANJUTAN-PRODUCTION-PIPELINE.md` (BARU) — rencana lengkap fix + re-run
- `MEGAPLAN.md` — tambah section "Production Pipeline — Real DB Execution"
- `.devin/SESSION_MEMORY.md` — update checkpoint (this file)
- `PROGRESS-OPTIMASI-RECOMPUTE.md` — tambah section production pipeline
- `docs/AUDIT-FINDINGS.md` — tambah section production pipeline audit
- `pustaka/00-README.md` — update referensi
- `scripts/daily_signal_cron.py` — Telegram → Direct App Notification (app_notifications table)
- `scripts/run_production_pipeline.sh` — Bash orchestrator (BARU)
- `.gitignore` — exclude DB parts, pipeline output JSON

### Pending:
- Fix inverse-variance weighting di `portfolio_data_remediation.py` dan `portfolio_final_execution.py`
- Re-run pipeline setelah fix
- Install crontab untuk daily signal cron
- Evaluasi model quality (15/20 ticker Sharpe negatif pada real DB)

## Update Rules 2026-08-06 (Sesi Pendek) — PowerShell Quoting

- **Pemicu:** User minta "Solusi praktis PowerShell quoting" diaktifkan untuk Devin di komputer Windows ini.
- **Aksi:** Tambah **AGENTS.md §9 "Aturan PowerShell Quoting (Wajib di Windows)"** — 9 sub-aturan + referensi cepat.
- **Kunci aturan:**
  1. Path Windows selalu single-quote (`'C:\...'`).
  2. Hindari `python -c "..."` kompleks — tulis ke `_tmp_<tujuan>.py`.
  3. Multi-command: `;` atau `if ($?) { }`, bukan `&&` (kecuali PS7+).
  4. Escape `"` dalam `"..."` pakai backtick `` `" `` atau gandakan `""` — JANGAN `\"`.
  5. Argumen mentah ke exe: `--%`.
  6. Exe ber-spasi: `& 'path.exe'`.
  7. Line continuation: backtick, bukan `\`.
  8. `$env:VAR`, `$(...)` untuk ekspansi di double-quote.
  9. Ragu → tulis `.ps1` sementara, jalankan, hapus.
- **File berubah:** `AGENTS.md` (tambah §9, 69 baris baru setelah §8).
- **Tidak ada perubahan kode Python.** Hanya rules behavior Devin.

## Checkpoint Sesi 2026-08-06 19:30 WIB (Windows Port)

- **Alasan:** Porting aplikasi dari Linux ke Windows selesai + cross-platform OS awareness.
- **Topik aktif:** Cross-platform path handling, Windows environment setup, AGENTS.md §7-8.

### Yang selesai di sesi Windows ini:
- DB `market_research.db` dirakit dari 3 part flashdisk (6083.81 MB) → `data/`.
- `uv` 0.12.2 terinstall, `uv sync --all-extras --dev` sukses (torch 2.13.0, pytest, ruff).
- `npm install` + `npm run build` sukses (frontend 12 halaman).
- `.env` dibuat dengan path Windows (`E:/pustaka_data`, `E:/projects/market`).
- Dataset-Saham-IDX disalin ke `data/dataset-saham-idx/`.
- Alembic verified: `0006 (head)`. Test screener: 9/9 pass.
- **Cross-platform path helper BARU:** `src/market/paths.py` — OS-aware defaults via `sys.platform`.
- **5 file diupdate untuk OS-aware:** `config.py`, `import_missing_tables.py`, `export_to_parquet.py`, `seed_from_parquet.py`, `.env.example`.
- **AGENTS.md §7 (Cross-Platform) + §8 (Aturan Terminal) BARU.**

### Aturan baru (AGENTS.md §7-8):
- §7: Jangan hardcode path OS-spesifik; gunakan `market.paths`; prioritas env > OS-default > CLI.
- §8: Jangan gunakan `tail`/`head`/`Select-Object -Last` di terminal; output harus langsung terlihat penuh.

## Checkpoint Sesi 2026-08-06 17:55 WIB

- **Alasan:** Selesai update seluruh file MD + `.devin` untuk portabilitas ke komputer lain.
- **Topik aktif:** Delisting/merger/name change logic, ticker_util standardization, data enrichment, MD docs update

### Keputusan Desain
- Metodologi: Quant/Algorithmic Trading. Target: Day Trading (intraday 15-min) + Swing Trading (EOD). Bukan HFT/Scalping.
- `ticker_util.py` menggantikan hardcoded `.JK` di seluruh codebase — standardisasi via `market_registry.data_suffix`.
- Screener mengecualikan tickers yang delisted, suspended, merged, blocked, dan low-liquidity.
- Corporate events (merger, pailit, name change) dicatat di `instrument_master` sebagai memory untuk ML/AI.

### File Dimodifikasi Sesi Ini (Checkpoint 22+)
- `src/market/data/ticker_util.py` (BARU) — Helper `to_yf_ticker`, `from_yf_ticker`, `get_currency`, `get_suffix`
- `src/market/data/screener.py` — Tambahan `excluded_merged` filter + `ScreeningResult.excluded_merged`
- `src/market/pipelines/data_fetch.py` — Gunakan `to_yf_ticker()`, baca non-XIDX dari DB
- `src/market/scheduler_tasks.py` — Gunakan `to_yf_ticker()` untuk fundamental fetch
- `src/market/data/yahoo_adapter.py` — Gunakan `get_currency(*from_yf_ticker())` untuk dividend currency
- `src/market/data/recompute_internal.py` — Baca ticker dari `instrument_master` bukan `LIKE '%.JK'`
- `src/market/data/data_health.py` — Join `instrument_master` untuk stale check
- `src/market/analysis/profiling.py` — Gunakan `from_yf_ticker()` untuk commodity lookup
- `alembic/versions/0006_add_instrument_master_columns.py` (BARU) — Migration 6 kolom baru
- `AGENTS.md` — Fix path, update pustaka count 94, tambah ref ticker_util & pustaka/93
- `README.md` — Tambah section Corporate Actions & Delisting Logic, Database Stats, Migration History
- `MEGAPLAN.md` — Fix path, tambah Data Enrichment Completed section
- `CONTRIBUTING.md` — Tambah konvensi ticker_util & screener, test_screener.py
- `docs/DATABASE-ISSUES.md` — Tambah masalah #8-#12, update stats, update summary table
- `docs/AUDIT-FINDINGS.md` — Fix path, tambah section 6 Data Enrichment, update stats
- `.devin/SESSION_MEMORY.md` — Update lengkap (this file)
- `.devin/skills/megaplan-executor/SKILL.md` — Fix path ke `C:\xampp\htdocs\market\`
- `.devin/skills/context-checkpoint/SKILL.md` — Update referensi 00-91 → 00-93
- `.devin/skills/knowledge-base-curator/SKILL.md` — Update referensi 00-91 → 00-93

### Test Status
- `tests/test_screener.py` — 9/9 passed
- All module imports OK (ticker_util, data_fetch, screener, yahoo_adapter, recompute_internal, data_health)
- Migration 0006 stamped pada production DB
- Ruff check: clean

### Pending
- DTS gap Feb 2025–Aug 2026 (butuh CSV IDX — tidak tersedia dari yfinance)
- Fundamental time-series (scheduler weekly aktif, data historis terbangun gradual)
- Update pustaka `18` & `90` — angka rows kedaluwarsa

## Ringkasan Proyek

- Pustaka ini adalah knowledge base untuk membangun aplikasi pasar modal (global & Indonesia), terutama decision-support EOD untuk single-user.
- Path aplikasi: `C:\xampp\htdocs\market\` — database utama: `data/market_research.db` (~6 GB, dirakit dari part backup di flashdisk `E:\projects\market\database\`).
- Keputusan desain tetap: UI Bahasa Indonesia + tooltip, timezone WIB display / UTC storage, single-user (no RBAC/JWT), GPU `cuda:1` untuk komputasi berat, `.env` untuk kredensial.
- Implementasi referensi: `trading-system` v0.1.11 (Linux: `/home/petrick/projects/global/`; Windows: `E:\trading_data\` — baca saja, jangan tulis/modifikasi). Lihat AGENTS.md §7 untuk path OS-aware.

## Database Stats Final (6 Agustus 2026)

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
| 0001 | Initial schema |
| 0002 | Add esg_scores and corporate_governance |
| 0003 | Complete schema: 15 missing tables + 4 column additions |
| 0004 | Add scheduler_state |
| 0005 | Add suspension_date to instrument_master |
| 0006 | Add listed_shares, tradeable_shares, delisting_risk_score, delisting_risk_reason, former_ticker, former_name |

## Data Enrichment Completed (6 Agustus 2026)

- ✅ **Delisting logic**: 62 tickers `is_active=0` + `delisting_date`; 211 tickers `delisting_risk_reason`
- ✅ **Merger logic**: 3 tickers `underlying_ticker` (FREN→EXCL, MFIN→ADMF); 2 `corporate_actions` merger rows
- ✅ **Name changes**: 34 tickers `former_name` (2024–2026 IDX name changes)
- ✅ **Ticker suffix standardization**: `ticker_util.py` menggantikan hardcoded `.JK` di 6 file
- ✅ **Screener enhancement**: `excluded_merged` filter
- ✅ **DTS backfill**: 4,928 rows untuk 25 IPO baru (source: `yfinance_derived`)
- ✅ **free_float backfill**: 922/923 (99.9%) — hanya GOTOM tanpa data
- ✅ **listed_shares/tradeable_shares**: 25 IPO baru di-backfill dari yfinance info
- ✅ **Migration 0006**: 6 kolom baru di `instrument_master`
- ⏳ **DTS gap Feb 2025–Aug 2026**: Butuh CSV IDX
- ⏳ **Fundamental time-series**: Scheduler weekly aktif, gradual

## Fitur Sebelumnya (Sesi 2026-08-06 pagi)

### TickerScreener — Screening sebelum fetch
- File: `src/market/data/screener.py`
- Filter 6 lapis: active status, delisting_date, merged (underlying_ticker), trading suspension, AI block (DelistingMemory), liquidity score
- Test: `tests/test_screener.py` (9 test cases)

### Intraday Polling — 15-menit via yfinance
- Scheduler task `fetch_intraday` dengan schedule `every_15min`
- Polling ~13 ticker penting (IDX + global indices + commodities)
- Store ke OHLCV dengan `timeframe='15m'`

### Endpoint API Baru
- `GET /api/prices/latest` — snapshot harga intraday terbaru dari DB
- `POST /api/prices/intraday/trigger` — trigger manual intraday fetch
- `GET /api/prices/compare/{ticker}` — bandingkan prediksi vs harga aktual

## Status Implementasi Terkini

- **Sync GitHub:** ✅ Commit `4843e52` (per audit 2026-08-05).
- **Backend Quality:** ✅ 760+ tests pass, coverage 76%+, `ruff check .` clean.
- **Frontend Build:** ✅ `npm run build` sukses (Next.js 16.3.0, 12 halaman, 0 vulnerabilities).
- **Database:** ✅ Semua 3 DB siap. Research & Paper ter-seed penuh, Live kosong (sesuai).
- **Scheduler:** ✅ 11+ tasks terdaftar (fetch_intraday, fetch_eod, fetch_global, fetch_macro, fetch_fundamental, health_check, quality_check, recompute, feature_store, drift_detection, generate_reports, export_parquet).
- **Model registry:** ✅ Baseline model trained (PyTorch cu121 installed, LSTM verified on cuda:1).
- **Environment File:** ✅ `.env` dibuat dengan `ENV=paper`, `BROKER_ADAPTER=paper`.
- **Alembic:** ✅ Migration sampai 0006.

## Human-Gate Checklist (MEGAPLAN §6.4)

- [x] Migrasi `market_live.db` — 21 tabel berhasil di-migrate.
- [x] Install dependency sistem — openpyxl, reportlab, pyarrow, torch cu121 terpasang.
- [x] Security config — single-user local, `.env` + `.gitignore` sudah ada.
- [x] Seed `market_paper.db` — 3,070,605 rows dari parquet_archive.
- [x] Cleanup kualitas data `market_paper.db` — 8 masalah diperbaiki.
- [x] Seed `market_research.db` — Mirror dari paper.
- [x] Tambah tabel `esg_scores` & `corporate_governance` — Migration 0002.
- [x] Migration 0006 — 6 kolom baru di instrument_master.
- [x] Data enrichment: delisting, merger, name change, ticker_util, DTS, free_float.
- [ ] Update pustaka `18` & `90` — angka rows kedaluwarsa.
- [ ] Broker real activation — perlu approval token.
- [ ] Deploy ke cloud/VPS — local-only.
- [ ] Model champion di Live — perlu eval-gate pass.

## Referensi Kunci

- `pustaka/00-README.md` — indeks dan keputusan desain (94 dokumen).
- `pustaka/18-modul-engine-data-wajib.md` — daftar modul, engine, data wajib (perlu update angka).
- `pustaka/88-gap-teori-vs-praktek.md` — audit gap teori vs praktek.
- `pustaka/89-faktor-pasar-modal-analisis-implementasi.md` — audit faktor pasar modal.
- `pustaka/90-analisis-parquet-data-awal.md` — audit data parquet awal (perlu update angka).
- `pustaka/91-komoditas-spesifik-idx.md` — komoditas IDX.
- `pustaka/92-multi-market-multi-asset-trading-system.md` — multi-market & multi-asset blueprint.
- `pustaka/93-lifecycle-environments-real-testing-ai.md` — lifecycle environment & promotion gates.
- `docs/AUDIT-FINDINGS.md` — laporan audit aplikasi + data enrichment.
- `docs/DATABASE-ISSUES.md` — audit konsistensi data IDX (12 masalah).
- `src/market/data/ticker_util.py` — helper standardisasi ticker suffix.
- `src/market/data/screener.py` — ticker screener 6-lapis filter.
- `src/market/data/cleanup_data.py` — script cleanup 8 fix (idempotent).
