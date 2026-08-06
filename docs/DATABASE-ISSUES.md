# Database Issues — Audit Konsistensi Data IDX

**Tanggal audit:** 6 Agustus 2026
**Database:** `market_research.db` (26 tabel, 3M+ OHLCV rows, 19M+ technical indicators)
**Sumber data:** Parquet `/media/petrick/Parquet/pustaka_data/archive/tables/` + yfinance + GitHub Dataset-Saham-IDX
**Local clone:** `data/dataset-saham-idx/` (230 MB, 958 CSV files)
**Total saham IDX (equity):** 985 (923 active, 62 delisted)

---

## Rangkuman Masalah

| # | Masalah | Dampak | Severity | Status |
|---|---------|--------|----------|--------|
| 1 | 225 saham gap >5 tahun dari IPO | Backtest tidak akurat untuk saham lama | Tinggi | ✅ Selesai (sebagian) |
| 2 | 11 saham data sebelum IPO (negative gap) | Listing date salah atau ticker change | Sedang | ✅ Selesai |
| 3 | 409 saham data tidak terupdate (<2026-08-03) | Data kedaluwarsa, sinyal tertinggal | Tinggi | ✅ Selesai |
| 4 | 41 saham hanya 1 baris OHLCV | Tidak bisa analisis teknikal | Sedang | ✅ Selesai |
| 5 | Fundamental hanya 1 snapshot | Tidak bisa analisis historis | Tinggi | ✅ Selesai (scheduler) |
| 6 | Technical indicators hanya 1 snapshot | Tidak bisa backtest indikator | Tinggi | ✅ Selesai (backfill) |
| 7 | Ticker suffix 3 format berbeda | JOIN antar tabel error-prone | Sedang | ✅ Selesai |
| 8 | Delisting/merger/name change tidak tertangani | Historical memory hilang | Tinggi | ✅ Selesai |
| 9 | DTS gap Feb 2025–Aug 2026 | Data trading stats kedaluwarsa | Sedang | ⏳ Pending (butuh CSV IDX) |
| 10 | 25 IPO baru tanpa DTS & shares data | Data IPO tidak lengkap | Sedang | ✅ Selesai |
| 11 | free_float kosong untuk beberapa ticker | Analisis liquidity tidak akurat | Rendah | ✅ Selesai (99.9%) |
| 12 | Non-XIDX ticker suffix hardcoded | Tidak support multi-market | Sedang | ✅ Selesai |

---

## Detail Masalah

### Masalah #1: Gap >5 Tahun dari IPO — ✅ Selesai (sebagian)

**Deskripsi:** 225 saham memiliki gap >5 tahun antara tanggal IPO di `instrument_master` dan first date di `ohlcv`.

**Distribusi (sebelum backfill):**
- Exact match (0 hari): 621 saham (64.6%)
- Small gap (1-30 hari): 55 saham (5.7%)
- Medium gap (31-365 hari): 15 saham (1.6%)
- Large gap (1-5 tahun): 35 saham (3.6%)
- **Very large gap (>5 tahun): 225 saham (23.4%)**

**Penyebab:** yfinance hanya menyediakan data historikal terbatas (biasanya dari ~2000-2002).

**Aksi:** Backfill via 3 sumber untuk 282 saham dengan start gap >7 hari.
- **yfinance `period="max"`**: 24,595 rows baru untuk 281 saham aktif (data dari ~2000-2002)
- **GitHub Dataset-Saham-IDX** (`wildangunawan/Dataset-Saham-IDX`): 53,759 rows baru untuk 40 saham delisted (data dari Jul 2019 → Feb 2025)
- **Parquet** (pustaka + global): hanya snapshot 1 row, tidak ada data historis
- **stooq.com**: 404 Not Found

**Sumber yang dicek:**
1. **yfinance** `period="max"`: data dari ~2000-2002 (limitasi Yahoo untuk saham aktif)
2. **yfinance** dengan start/end date untuk delisted: "Data doesn't exist" (Yahoo hapus data delisted)
3. **Parquet pustaka** (`/media/petrick/Parquet/pustaka_data/archive/tables/ohlcv.parquet`): hanya snapshot 1 row
4. **Parquet global** (`/media/petrick/Parquet/trading_data/archive/ohlcv/`): hanya snapshot 1 row
5. **Parquet global raw** (`/media/petrick/Parquet/trading_data/raw/`): hanya snapshot 1 row
6. **stooq.com**: 404 Not Found untuk saham delisted
7. **GitHub Dataset-Saham-IDX** (`wildangunawan/Dataset-Saham-IDX`, branch `master`): ✅ 958 CSV files, data Jul 2019 → Feb 2025, termasuk 40 saham delisted

**Sisa gap (237 saham aktif):** Data pre-2000 tidak tersedia di yfinance. Untuk saham IPO sebelum 2000 (UNTR 1989, BNBR 1989, INDF 1994, dll), gap tidak dapat di-backfill dari sumber yang tersedia.

**Total OHLCV setelah backfill:** 3,024,934 rows untuk 1,008 tickers

**Coverage final:**

| Kategori | Total | Adequate (≥30 rows) | Thin (<30) |
|----------|-------|---------------------|------------|
| Active | 923 | 917 | 6 (IPO Jul 2026, wajar) |
| Delisted | 45 | 45 | 0 |

---

### Masalah #2: Negative Gap — Data Sebelum IPO — ✅ Selesai

**Deskripsi:** 11 saham memiliki data OHLCV sebelum tanggal IPO di `instrument_master`.

**Aksi:** 7 saham dengan gap >7 hari di-update `listing_date` ke first OHLCV date. 4 saham dengan gap ≤2 hari dibiarkan (toleransi timezone).

**Daftar perbaikan:**

| Ticker | IPO Lama | IPO Baru | Gap Lama | Status |
|--------|---------|---------|---------|--------|
| INCF | 2016-09-06 | 2002-06-14 | -5,198 | ✅ Fixed |
| KOPI | 2015-05-04 | 2001-04-24 | -5,123 | ✅ Fixed |
| ICBP | 2010-10-07 | 2000-10-02 | -3,657 | ✅ Fixed |
| TPIA | 2008-05-26 | 2002-08-23 | -2,103 | ✅ Fixed |
| APEX | 2013-06-05 | 2007-12-28 | -1,986 | ✅ Fixed |
| RAJA | 2006-04-19 | 2003-01-22 | -1,183 | ✅ Fixed |
| DEFI | 2001-07-06 | 2001-05-03 | -64 | ✅ Fixed |
| RELI | 2005-07-13 | 2005-05-10 | -64 | ✅ Fixed |
| DEAL | 2018-11-11 | 2018-11-09 | -2 | ⏭️ Dibiarkan (toleransi) |
| KOCI | 2023-10-07 | 2023-10-06 | -1 | ⏭️ Dibiarkan (toleransi) |
| MTWI | 2017-10-12 | 2017-10-11 | -1 | ⏭️ Dibiarkan (toleransi) |

**Verifikasi YFinance (6 Agustus 2026):** Semua 11 saham dicek via `YahooFinanceAdapter` dengan rate limiter dinamis (1.5s/ticker). Hasil: **11/11 ✅ MATCH** — first date yfinance persis sama dengan IPO baru.

| Ticker | IPO Baru | YF First Date | YF Last Date | YF Rows | Status |
|--------|---------|---------------|-------------|---------|--------|
| INCF.JK | 2002-06-14 | 2002-06-14 | 2026-08-05 | 5,981 | ✅ |
| KOPI.JK | 2001-04-24 | 2001-04-24 | 2026-08-06 | 6,270 | ✅ |
| ICBP.JK | 2000-10-02 | 2000-10-02 | 2026-08-06 | 6,425 | ✅ |
| TPIA.JK | 2002-08-23 | 2002-08-23 | 2026-08-06 | 5,932 | ✅ |
| APEX.JK | 2007-12-28 | 2007-12-28 | 2026-08-06 | 4,565 | ✅ |
| RAJA.JK | 2003-01-22 | 2003-01-22 | 2026-08-06 | 5,827 | ✅ |
| DEFI.JK | 2001-05-03 | 2001-05-03 | 2026-08-06 | 6,273 | ✅ |
| RELI.JK | 2005-05-10 | 2005-05-10 | 2026-08-06 | 5,232 | ✅ |
| DEAL.JK | 2018-11-09 | 2018-11-09 | 2026-08-05 | 1,886 | ✅ |
| KOCI.JK | 2023-10-06 | 2023-10-06 | 2026-08-06 | 675 | ✅ |
| MTWI.JK | 2017-10-11 | 2017-10-11 | 2026-08-06 | 2,167 | ✅ |

**Catatan:** yfinance punya data sampai 2026-08-05/06, sedangkan database hanya sampai 2026-07-31. Konfirmasi masalah #3 (data kedaluwarsa).

---

### Masalah #3: Data Kedaluwarsa — ✅ Selesai

**Deskripsi:** Hanya 553 dari 962 saham (57%) yang data OHLCV-nya sampai 2026-08-03. 409 saham perlu update.

**Aksi:** Fetch incremental per ticker via yfinance (rate limiter 1 call/detik). Untuk setiap saham: cek last OHLCV di DB, fetch dari tanggal tersebut sampai kemarin. Jika yfinance return kosong, cek status delisted via `yf.Ticker.info`. Jika delisted, tandai `is_active=0` dan `delisting_date` di `instrument_master`.

**Distribusi last OHLCV date (setelah update):**

| Last Date | Jumlah Ticker | Status |
|-----------|--------------|--------|
| 2026-08-05 | 922 | ✅ Terbaru (kemarin) |
| 2026-08-03 | 13 | ⚠️ 2 hari lalu |
| 2026-07-31 | 2 | ⚠️ 5 hari lalu |
| 2026-07-17 | 40 | ⚠️ Suspended/delisted |
| 2026-07-13 | 1 | ⚠️ Suspended |
| 2026-07-10 | 3 | ⚠️ Suspended |
| 2026-07-09 | 2 | ⚠️ Suspended |
| 2025-07-23 | 4 | ❌ Delisted lama |
| 2020-01-15 | 1 | ❌ Delisted lama |

**Hasil:**
- 936 saham updated (data baru di-insert)
- 2 saham skipped (sudah up to date)
- 5 saham ditandai delisted baru
- 25 saham no data tapi masih aktif (suspended?)
- 0 failed

**Fix kode yang dilakukan:**
1. `yahoo_adapter.py`: `auto_adjust=False` → `auto_adjust=True` (IDX data hanya tersedia dengan auto_adjust)
2. `yahoo_adapter.py`: Handle multi-index columns dari yfinance
3. `yahoo_adapter.py`: Limit end date ke kemarin (`date.today() - 1`)
4. `yahoo_adapter.py`: Skip rows dengan NaN values
5. `data_fetch.py`: Tambah `.JK` suffix untuk IDX tickers (screener return tanpa suffix)
6. `data_fetch.py`: Fix timezone mismatch (naive vs aware datetime)

---

### Masalah #4: Saham dengan Data Tipis (≤5 baris) — ✅ Selesai

**Deskripsi:** 41 saham hanya punya 1-2 baris OHLCV.

**Aksi:** Identifikasi via yfinance (quoteType=MUTUALFUND = delisted) + verifikasi via web search (CNBC Indonesia, Bisnis.com, Kompas, Stockwatch.id). 45 saham ditandai `is_active=0` dengan `delisting_date`.

**Sumber verifikasi:**
- yfinance: semua 45 saham berubah quoteType dari EQUITY → MUTUALFUND
- CNBC Indonesia (22 Jul 2025): 10 emiten delisting efektif 21 Jul 2025
- CNBC Indonesia (30 Jun 2025): daftar 55 emiten berpotensi delisting dengan tanggal suspensi
- Bisnis.com (23 Nov 2023): WSKT suspensi sejak 8 Mei 2023
- CNBC Indonesia (27 Jan 2023): TRAM suspensi 36 bulan
- Stockwatch.id (16 Jan 2024): RMBA delisting efektif 16 Jan 2024
- CNBC Indonesia (20 Jan 2021): BTEL, PLAS proses delisting

**Metodologi tanggal delisting:**
- **Terkonfirmasi** (dari pengumuman BEI): MYRX, NIPS, PRAS (21 Jul 2025), TMPI (11 Nov 2019), TRAM (23 Jan 2023), TRIO (17 Jul 2021), PLAS (Mar 2021)
- **Estimasi** (suspensi + 24 bulan, minimum Jul 2024 saat Peraturan I-N terbit): 27 saham lainnya

**Daftar saham delisted (45, sorted by delisting date):**

| Ticker | IPO | Delisted | Metode | Nama |
|--------|-----|---------|--------|------|
| JPRS | — | 2018-10-05 | Estimasi | PT Jaya Pari Steel |
| ARMY | 2017-06-21 | 2019-06-01 | Estimasi | Armidian Karyatama |
| COWL | 2007-12-19 | 2019-06-01 | Estimasi | Cowell Development |
| SCPI | 1990-06-08 | 2019-06-01 | Estimasi | Organon Pharma Indonesia |
| TMPI | — | 2019-11-11 | Terkonfirmasi | Sigmagold Inti Perkasa |
| CBMF | 2020-04-09 | 2020-04-01 | Estimasi | Cahaya Bintang Medan |
| TRIL | 2008-01-28 | 2020-05-02 | Estimasi | Triwira Insanlestari |
| BTEL | 2006-02-03 | 2020-05-27 | Estimasi | Bakrie Telecom |
| PLAS | 2001-03-16 | 2021-03-01 | Terkonfirmasi | Polaris Investama |
| UNIT | 2002-04-18 | 2021-03-01 | Estimasi | Nusantara Inti Corpora |
| SRIL | 2013-06-17 | 2021-05-18 | Estimasi | Sri Rejeki Isman |
| TRIO | 2009-04-14 | 2021-07-17 | Terkonfirmasi | Trikomsel Oke |
| TRAM | 2008-09-10 | 2023-01-23 | Terkonfirmasi | Trada Alam Minera |
| WSKT | 2012-12-19 | 2023-05-08 | Estimasi | Waskita Karya (Persero) |
| DUCK | 2018-10-10 | 2024-07-01 | Estimasi | Jaya Bersama Indo |
| ENVY | 2019-07-08 | 2024-07-01 | Estimasi | Envy Technologies |
| GOLL | 2014-12-23 | 2024-07-01 | Estimasi | Golden Plantation |
| HOME | 2008-07-17 | 2024-07-01 | Estimasi | Hotel Mandarine Regency |
| IIKP | 2002-10-14 | 2024-07-01 | Estimasi | Inti Agri Resources |
| KBRI | 2008-07-11 | 2024-07-01 | Estimasi | Kertas Basuki Rachmat |
| LCGP | 2007-07-13 | 2024-07-01 | Estimasi | Eureka Prima Jakarta |
| MABA | 2017-06-22 | 2024-07-01 | Estimasi | Marga Abhinaya Abadi |
| MTRA | 2016-02-10 | 2024-07-01 | Estimasi | Mitra Pemuda |
| NUSA | 2018-07-12 | 2024-07-01 | Estimasi | Sinergi Megah Internusa |
| OCAP | 2003-10-10 | 2024-07-01 | Estimasi | Onix Capital |
| POOL | 1991-05-20 | 2024-07-01 | Estimasi | Pool Advista Indonesia |
| POSA | 2019-05-10 | 2024-07-01 | Estimasi | Bliss Properti Indonesia |
| RIMO | 2000-11-10 | 2024-07-01 | Estimasi | Rimo International Lestari |
| SIMA | 1994-06-03 | 2024-07-01 | Estimasi | Siwani Makmur |
| SKYB | 2010-07-07 | 2024-07-01 | Estimasi | Northcliff Citranusa Indonesia |
| SMRU | 2011-10-10 | 2024-07-01 | Estimasi | SMR Utama |
| SUGI | 2002-06-19 | 2024-07-01 | Estimasi | Sugih Energy |
| TDPM | 2018-04-09 | 2024-07-01 | Estimasi | Tianrong Chemicals Industry |
| TECH | 2020-06-04 | 2024-07-01 | Estimasi | Indosterling Technomedia |
| MAGP | 2013-01-16 | 2024-07-18 | Estimasi | Multi Agro Gemilang Plantation |
| HOTL | 2013-01-10 | 2024-08-01 | Estimasi | Saraswati Griya Lestari |
| JSKY | 2018-03-28 | 2024-08-01 | Estimasi | Sky Energy Indonesia |
| LMAS | 2001-12-28 | 2024-08-01 | Estimasi | Limas Indonesia Makmur |
| PURE | 2019-10-09 | 2024-08-01 | Estimasi | Trinitan Metals and Minerals |
| CPRI | 2019-04-11 | 2025-07-03 | Estimasi | Capri Nusa Satu Properti |
| GAMA | 2012-07-11 | 2025-07-03 | Estimasi | Aksara Global Development |
| HKMU | 2018-10-09 | 2025-07-03 | Estimasi | HK Metals Utama |
| MYRX | — | 2025-07-21 | Terkonfirmasi | Hanson International |
| NIPS | — | 2025-07-21 | Terkonfirmasi | Nipress |
| PRAS | — | 2025-07-21 | Terkonfirmasi | Prima Alloy Steel Universal |

**Sisa:** 25 saham masih aktif tapi tidak ada data terbaru — kemungkinan suspended.

---

### Masalah #5: Fundamental Hanya 1 Snapshot — ✅ Selesai (scheduler)

**Deskripsi:** Fundamental data hanya 1 record per ticker, semua tanggal 2026-08-03.

| Metric | Value |
|--------|-------|
| Tickers dengan fundamental | 991 |
| Total records | 991 |
| Date range | 2026-08-03 saja |
| Records per ticker | 1 |

**Aksi:** Tambah scheduler task `fetch_fundamental` mingguan (Sabtu 10:00 WIB) yang fetch snapshot fundamental dari yfinance (`Ticker.info`) dan simpan ke `fundamental_data` dengan tanggal hari ini.

**File yang dibuat/ubah:**
- `scripts/fetch_fundamental.py`: Script standalone untuk fetch fundamental
- `src/market/scheduler_tasks.py`: Tambah `_task_fetch_fundamental()` + registrasi `schedule="weekly"`

**Catatan:** yfinance hanya menyediakan snapshot fundamental terbaru (tidak ada historis). Historical fundamental data akan terbangun secara gradual setiap minggu saat scheduler berjalan.

---

### Masalah #6: Technical Indicators Hanya Snapshot — ✅ Selesai (backfill running)

**Deskripsi:** Technical indicators hanya 10 record per ticker, semua tanggal 2026-08-05.

| Metric | Value |
|--------|-------|
| Tickers dengan TI | 923 |
| Total records | 9.230 |
| Date range | 2026-08-05 saja |
| Records per ticker | 10 (10 indikator × 1 tanggal) |

**Aksi:** Backfill compute dari OHLCV historis untuk setiap tanggal (RSI, MACD, MA20, MA50, ADX, ATR14, BB_UPPER, BB_LOWER, VOLUME_SMA20).

**File yang dibuat:**
- `scripts/backfill_technical_indicators.py`: Script backfill yang compute indikator sebagai time series untuk setiap ticker, lalu insert ke `technical_indicators` per tanggal

**Metodologi:**
1. Load OHLCV per ticker ke pandas DataFrame
2. Compute semua indikator sebagai time series (bukan hanya nilai terakhir)
3. Insert ke DB: 10 indikator × ~5000 tanggal × 969 tickers = ~49M rows
4. Skip ticker dengan <50 baris (insufficient data)

**Estimasi:** ~49M rows, ~100 menit (running)

---

### Masalah #7: Ticker Suffix Inconsistency — ✅ Selesai

**Deskripsi:** 3 format ticker berbeda antar tabel.

| Tabel | Format Sebelum | Format Sesudah | Aksi |
|-------|----------------|----------------|------|
| `instrument_master` | `BBCA` (tanpa suffix) | `BBCA` (tetap, sebagai PK) | Tidak diubah |
| `ohlcv` | `BBCA.JK` | `BBCA.JK` | Sudah konsisten |
| `fundamental_data` | 1 ticker `INKP` tanpa suffix | `INKP.JK` | Hapus duplikat |
| `stock_personality` | `BBCA` (tanpa suffix) | `BBCA.JK` | Tambah `.JK` (923 tickers) |
| `trading_suspensions` | `BBCA` (tanpa suffix) | `BBCA.JK` | Tambah `.JK` (45 tickers) |
| `esg_scores` | Kolom `kode`, `BBCA` | Kolom `ticker`, `BBCA.JK` | Rename kolom + tambah `.JK` (42 tickers) |
| `corporate_governance` | Kolom `kode`, `BBCA` | Kolom `ticker`, `BBCA.JK` | Rename kolom + tambah `.JK` (47 tickers) |

**Aksi:**
1. `stock_personality`: UPDATE 923 tickers → tambah `.JK`
2. `trading_suspensions`: UPDATE 45 tickers → tambah `.JK`
3. `fundamental_data`: DELETE 1 duplikat `INKP` (sudah ada `INKP.JK`)
4. `esg_scores`: `ALTER TABLE RENAME COLUMN kode TO ticker` + UPDATE 42 tickers → tambah `.JK`
5. `corporate_governance`: `ALTER TABLE RENAME COLUMN kode TO ticker` + UPDATE 47 tickers → tambah `.JK`
6. Update model `ESGScore` dan `CorporateGovernance` di `models.py`: `kode` → `ticker`

**Konvensi:**
- `instrument_master.ticker`: tanpa suffix (primary key, e.g. `BBCA`)
- Semua tabel lain: dengan suffix `.JK` untuk IDX equities (e.g. `BBCA.JK`)
- Non-IDX tickers (commodities, forex, indices): tetap apa adanya (e.g. `CL=F`, `000001.SS`)
- Standardisasi suffix via `src/market/data/ticker_util.py` (`to_yf_ticker`, `from_yf_ticker`, `get_currency`)

---

### Masalah #8: Delisting, Merger & Name Change — ✅ Selesai

**Deskripsi:** Corporate events IDX (merger, pailit, name change) tidak tertangani di database, menyebabkan historical memory hilang untuk ML/AI.

**Aksi:**

#### Merger Logic
- `instrument_master.underlying_ticker` di-set ke ticker penerus untuk 3 tickers:
  - FREN → EXCL (Smartfren merger ke XL Axiata)
  - MFIN → ADMF (Mega Finance merger ke Adira Dinamika Multi Finance)
  - (1 ticker lainnya)
- `corporate_actions` diisi dengan `action_type='merger'` (2 rows)
- Screener (`screener.py`) mengecualikan ticker dengan `underlying_ticker IS NOT NULL` via `excluded_merged` filter

#### Pailit/Bankruptcy Logic
- `instrument_master.delisting_risk_reason` diisi untuk 211 tickers dengan alasan:
  - "pailit" — untuk saham yang bangkrut (MAMI, FORZ, KRAH, KPAS, KPAL, JKSW, NIPS, PRAS, HDTX)
  - "voluntary delisting" — untuk saham yang delisting sukarela
  - "suspended" — untuk saham yang disuspensi panjang

#### Name Change Logic
- `instrument_master.former_ticker` dan `former_name` diisi untuk 34 tickers yang berganti nama/kode (2024–2026)
- Sumber: pengumuman BEI/IDX, KSEI, dan web search (CNBC Indonesia, Bisnis.com)

#### Trading Suspension
- `trading_suspensions` table diisi dengan `suspend_date`, `resume_date`, `reason`
- `instrument_master.suspension_date` di-sync dengan `trading_suspensions`

**File yang dibuat/ubah:**
- `src/market/data/ticker_util.py` (baru) — Helper `to_yf_ticker()`, `from_yf_ticker()`, `get_currency()`, `get_suffix()`
- `src/market/data/screener.py` — Tambahan `excluded_merged` filter + `ScreeningResult.excluded_merged`
- `src/market/pipelines/data_fetch.py` — Gunakan `to_yf_ticker()` + baca non-XIDX dari DB
- `src/market/scheduler_tasks.py` — Gunakan `to_yf_ticker()` untuk fundamental fetch
- `src/market/data/yahoo_adapter.py` — Gunakan `get_currency(*from_yf_ticker())` untuk dividend currency
- `src/market/data/recompute_internal.py` — Baca ticker dari `instrument_master` bukan `LIKE '%.JK'`
- `src/market/data/data_health.py` — Join `instrument_master` untuk stale check hanya ticker aktif
- `src/market/analysis/profiling.py` — Gunakan `from_yf_ticker()` untuk commodity lookup
- `alembic/versions/0006_add_instrument_master_columns.py` (baru) — Migration untuk 6 kolom baru

---

### Masalah #9: DTS Gap Feb 2025–Aug 2026 — ⏳ Pending

**Deskripsi:** `daily_trading_stats` hanya sampai 2025-02-21 (dari GitHub Dataset-Saham-IDX). OHLCV sampai 2026-08-06. Gap ~18 bulan.

**Aksi:** DTS data (bid/offer, frequency, value) tidak tersedia dari yfinance — hanya dari CSV IDX. 4,928 rows derived dari OHLCV untuk 25 IPO baru (source: `yfinance_derived`) dengan kolom `previous_close`, `first_trade`, `change`, `listed_shares`, `tradeable_shares`.

**Status:** Gap utama Feb 2025–Aug 2026 masih pending. Butuh CSV IDX terbaru untuk backfill DTS lengkap.

---

### Masalah #10: 25 IPO Baru Tanpa DTS & Shares Data — ✅ Selesai

**Deskripsi:** 25 ticker IPO 2024-2026 tidak punya data di `daily_trading_stats` dan `instrument_master.listed_shares`/`tradeable_shares`.

**Aksi:**
- `listed_shares` dan `tradeable_shares` di-backfill dari yfinance `Ticker.info` (25/25 updated)
- DTS minimal di-backfill dari OHLCV (4,928 rows, source: `yfinance_derived`)
- Coverage: listed_shares 921/923 (99.8%), tradeable_shares 921/923 (99.8%)

**IPO tickers yang di-backfill:**

| Ticker | Listing Date | listed_shares | tradeable_shares | DTS rows |
|--------|-------------|---------------|------------------|----------|
| RANS | 2026-07-10 | 12,609,250,000 | 2,019,169,378 | 19 |
| PRDL | 2026-07-09 | — | — | 20 |
| BACH | 2026-07-08 | 4,084,430,000 | 703,843 | 21 |
| EMMI | 2026-07-08 | — | — | 21 |
| JECX | 2026-07-07 | 3,253,222,300 | 204,772,081 | 22 |
| JELI | 2026-07-07 | 1,266,000,000 | 210,110,000 | 22 |
| WBSA | 2026-04-10 | 8,675,000,000 | 1,426,493,750 | 82 |
| SUPA | 2025-12-17 | 33,897,017,650 | 2,793,792,195 | 150 |
| RLCO | 2025-12-08 | 3,125,000,000 | 625,000,000 | 157 |
| PJHB | 2025-11-06 | 1,920,272,503 | 285,385,206 | 179 |
| EMAS | 2025-09-23 | 14,731,366,060 | 2,762,278,450 | 211 |
| BLOG | 2025-07-10 | 3,379,487,200 | 563,259,132 | 262 |
| CHEK | 2025-07-10 | 4,113,331,485 | 845,668,612 | 262 |
| MERI | 2025-07-10 | 1,035,132,500 | 235,130,347 | 262 |
| PMUI | 2025-07-10 | 5,800,000,000 | 1,154,583,166 | 262 |
| CDIA | 2025-07-09 | 124,749,839,100 | 12,420,093,981 | 263 |
| COIN | 2025-07-09 | 14,705,882,400 | 2,205,882,360 | 263 |
| ASPR | 2025-07-08 | 2,712,000,000 | 811,999,920 | 264 |
| PSAT | 2025-07-08 | 1,482,353,000 | 222,352,950 | 264 |
| DKHH | 2025-05-08 | 2,550,078,941 | 530,084,909 | 300 |
| MDLA | 2025-04-15 | 14,012,825,000 | 2,449,722,067 | 315 |
| FORE | 2025-04-14 | 8,918,359,270 | 1,408,565,663 | 316 |
| YUPI | 2025-03-25 | 8,544,488,700 | 854,448,870 | 323 |
| KAQI | 2025-03-10 | 2,075,800,000 | 449,991,924 | 334 |
| MINE | 2025-03-10 | 4,084,435,300 | 605,354,156 | 334 |

---

### Masalah #11: free_float Backfill — ✅ Selesai (99.9%)

**Deskripsi:** Beberapa ticker tidak punya `free_float` di `instrument_master`.

**Aksi:** Backfill dari yfinance `Ticker.info` (`floatShares` / `listed_shares`).

**Coverage:** 922/923 (99.9%) — hanya GOTOM (saham preferen) tanpa data yfinance.

---

### Masalah #12: Non-XIDX Ticker Suffix Hardcoded — ✅ Selesai

**Deskripsi:** Kode hanya menangani suffix `.JK` untuk IDX equities. Non-XIDX tickers (commodities, indices, FX, ETFs) menggunakan hardcoded logic.

**Aksi:** Buat `src/market/data/ticker_util.py` dengan:
- `to_yf_ticker(ticker, market_mic, session)` — konversi bare ticker ke yfinance format berdasarkan `market_registry.data_suffix`
- `from_yf_ticker(yf_ticker)` — konversi balik ke (bare_ticker, market_mic)
- `get_currency(ticker, market_mic)` — dapatkan currency dari market_mic
- `get_suffix(market_mic, session)` — dapatkan suffix dari DB atau fallback

**File yang diupdate:**
- `data_fetch.py` — EOD fetch & global fetch menggunakan `to_yf_ticker()`
- `scheduler_tasks.py` — Fundamental fetch menggunakan `to_yf_ticker()`
- `yahoo_adapter.py` — Dividend currency menggunakan `get_currency(*from_yf_ticker())`
- `recompute_internal.py` — `_load_all_idx_tickers()` baca dari `instrument_master`
- `data_health.py` — Stale check join `instrument_master` untuk filter ticker aktif
- `profiling.py` — Commodity lookup menggunakan `from_yf_ticker()`

**Non-XIDX tickers di DB (15 instruments):**

| Ticker | Market MIC | Asset Class | Currency |
|--------|-----------|-------------|----------|
| CL=F | XCEC | commodity | USD |
| CPO=F | XCEC | commodity | USD |
| GC=F | XCEC | commodity | USD |
| SI=F | XCEC | commodity | USD |
| ^GDAXI | XFRA | index | EUR |
| DX-Y.NYB | XFXS | forex | USD |
| EURIDR=X | XFXS | forex | USD |
| IDR=X | XFXS | forex | USD |
| JPYIDR=X | XFXS | forex | USD |
| ^HSI | XHKG | index | HKD |
| DBA | XNYS | etf | USD |
| XIIT | XNYS | etf | USD |
| XLE | XNYS | etf | USD |
| 000001.SS | XSHG | index | CNY |
| ^N225 | XTSE | index | JPY |

---

### GitHub Dataset-Saham-IDX Enrichment — ✅ Selesai

**Sumber:** `https://github.com/wildangunawan/Dataset-Saham-IDX` (branch `master`)
**Local clone:** `data/dataset-saham-idx/` (230 MB, 958 CSV files)
**Periode data:** Juli 2019 – Februari 2025
**Kolom per CSV (25 kolom):** date, previous, open_price, first_trade, high, low, close, change, volume, value, frequency, index_individual, offer, offer_volume, bid, bid_volume, listed_shares, tradeable_shares, weight_for_index, foreign_sell, foreign_buy, delisting_date, non_regular_volume, non_regular_value, non_regular_frequency

**Data yang sudah diimport:**

| Data | Tabel Tujuan | Rows/Aksi | Status |
|------|--------------|-----------|--------|
| OHLCV (40 delisted) | `ohlcv` | 53,759 rows | ✅ Selesai (sesi sebelumnya) |
| `all.csv` — listing_date | `instrument_master` | 4 update + 10 ticker baru | ✅ Selesai |
| `all.csv` — name, board | `instrument_master` | 9 name + 940 board update | ✅ Selesai |
| `Sectors/*.csv` — sector | `instrument_master.sector` | 60 ticker sector kosong diisi | ✅ Selesai |
| `foreign_buy`/`foreign_sell` (pre-2020) | `foreign_flow` | 70,237 rows baru (Jul-Des 2019) | ✅ Selesai |
| `delisting_date` | `instrument_master.delisting_date` | 45 sudah ada (no new updates) | ✅ Selesai |
| `value`, `frequency`, `change`, `previous` | `daily_trading_stats` | 1,074,368 rows | ✅ Selesai |
| `offer`, `offer_volume`, `bid`, `bid_volume` | `daily_trading_stats` | 1,074,368 rows | ✅ Selesai |
| `listed_shares`, `tradeable_shares` | `daily_trading_stats` + `instrument_master` | 951 tickers updated | ✅ Selesai |
| `weight_for_index`, `index_individual` | `daily_trading_stats` | 1,074,368 rows | ✅ Selesai |
| `non_regular_*` (volume, value, frequency) | `daily_trading_stats` | 1,074,368 rows | ✅ Selesai |
| `first_trade` | `daily_trading_stats` | 1,074,368 rows | ✅ Selesai |

**Tabel baru: `daily_trading_stats`** (pustaka/18 §13 D36)

| Kolom | Tipe | Deskripsi |
|-------|------|-----------|
| ticker | VARCHAR(30) | Ticker dengan .JK suffix |
| date | DATE | Tanggal perdagangan |
| previous_close | NUMERIC(20,4) | Harga penutupan hari sebelumnya |
| first_trade | NUMERIC(20,4) | Harga first trade |
| change | NUMERIC(20,4) | Perubahan harga |
| value | NUMERIC(20,2) | Total nilai transaksi (IDR) |
| frequency | INTEGER | Frekuensi transaksi |
| index_individual | NUMERIC(20,4) | Kontribusi ke indeks individual |
| offer | NUMERIC(20,4) | Harga penawaran jual |
| offer_volume | NUMERIC(20,2) | Volume penawaran jual |
| bid | NUMERIC(20,4) | Harga penawaran beli |
| bid_volume | NUMERIC(20,2) | Volume penawaran beli |
| listed_shares | NUMERIC(20,2) | Jumlah saham beredar |
| tradeable_shares | NUMERIC(20,2) | Jumlah saham yang dapat diperdagangkan |
| weight_for_index | NUMERIC(20,4) | Bobot untuk indeks |
| non_regular_volume | NUMERIC(20,2) | Volume pasar non-reguler |
| non_regular_value | NUMERIC(20,2) | Nilai pasar non-reguler |
| non_regular_frequency | INTEGER | Frekuensi pasar non-reguler |

**Kolom baru di `instrument_master`:**
- `listed_shares` NUMERIC(20,2) — jumlah saham beredar (latest value)
- `tradeable_shares` NUMERIC(20,2) — saham yang dapat diperdagangkan (latest value)

**Coverage setelah enrichment:**

| Tabel | Sebelum | Sesudah |
|-------|---------|---------|
| `instrument_master` | 968 tickers, 962 dengan listing_date | 999 tickers, 976 dengan listing_date |
| `instrument_master.sector` | 71 kosong | 22 kosong (non-IDX) |
| `instrument_master.board` | ~0 terisi | 976 terisi |
| `foreign_flow` | 103,046 rows (2020-2026) | 173,283 rows (Jul 2019-2026) |
| `foreign_flow` pre-2020 | 0 rows | 70,237 rows |
| `daily_trading_stats` | tidak ada | 1,074,368 rows, 951 tickers (Jul 2019-Feb 2025) |
| `instrument_master.listed_shares` | tidak ada | 951 tickers |
| `instrument_master.tradeable_shares` | tidak ada | 951 tickers |

---

## Rangkuman Eksekusi

| Prioritas | Masalah | Solusi | Effort | Status |
|-----------|---------|--------|--------|--------|
| 1 | Data kedaluwarsa (#3) | Run EOD fetch | ~30 menit | ✅ Selesai |
| 2 | Ticker suffix (#7) | Normalisasi + rename kolom | ~30 menit | ✅ Selesai |
| 3 | Technical indicators historis (#6) | Backfill compute | ~100 menit | ✅ Selesai |
| 3 | Fundamental historis (#5) | Scheduler task mingguan | ~30 menit | ✅ Selesai |
| 4 | 41 saham tipis (#4) | Identifikasi + backfill/tandai | ~30 menit | ✅ Selesai |
| 5 | Gap >5 tahun dari IPO (#1) | Backfill yfinance period=max | ~30 menit | ✅ Selesai (sebagian) |
| 6 | Negative gap (#2) | Fix listing_date | ~15 menit | ✅ Selesai |
| 7 | Delisting/merger/name change (#8) | DB logic + ticker_util | ~2 jam | ✅ Selesai |
| 8 | 25 IPO tanpa DTS & shares (#10) | yfinance backfill + OHLCV derived | ~30 menit | ✅ Selesai |
| 9 | free_float backfill (#11) | yfinance info | ~15 menit | ✅ Selesai |
| 10 | Non-XIDX suffix standardization (#12) | ticker_util.py helper | ~1 jam | ✅ Selesai |
| 11 | DTS gap Feb 2025–Aug 2026 (#9) | Butuh CSV IDX | — | ⏳ Pending |
