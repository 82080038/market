# Analisis Parquet: Data Awal Database & Yang Perlu Diperbaiki

> **Dokumen 90** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Tujuan:** Memberitahu pustaka bahwa database awal bisa di-bootstrap dari `/media/petrick/Parquet/trading_data`, dan menganalisis isi parquet tersebut untuk identifikasi data yang perlu diperbaiki, dilengkapi, atau di-migrate.
>
> **Lokasi data:**
> - **Raw:** `/media/petrick/Parquet/trading_data/raw/` — 1024 items (971 ticker files + 53 subdirs)
> - **Archive:** `/media/petrick/Parquet/trading_data/archive/` — 6 subdirs (ohlcv, tables, foreign_flow_idx, broker_flow_idx, instrument_master, trading_suspensions)
>
> **PENTING — Konvensi Penyimpanan Parquet:**
> - Direktori `/media/petrick/Parquet/trading_data/` **sudah dipakai oleh project `global`** (trading-system v0.1.11). Jangan tulis/modifikasi file di sini dari luar project.
> - Untuk membuat file parquet baru di luar project `global`, gunakan direktori terpisah, misalnya: `/media/petrick/Parquet/pustaka_data/` atau `/media/petrick/Parquet/<project_baru>/`.
> - Struktur direktori `/media/petrick/Parquet/` saat ini:
>   ```
>   /media/petrick/Parquet/
>   ├── trading_data/          # ⚠️ DIPAKAI project global (287MB)
>   │   ├── raw/                # Data raw (971 ticker + 53 subdirs)
>   │   └── archive/            # Data archive (6 subdirs, 28 tabel)
>   ├── System Volume Information/  # Windows metadata (partisi NTFS/exFAT)
>   └── .Trash-1000/           # Recycle bin
>   ```
> - **Jika project baru dibuat** dan butuh menyimpan parquet, buat direktori sendiri:
>   ```bash
>   mkdir -p /media/petrick/Parquet/pustaka_data/{raw,archive}
>   ```
> - **Jika ingin membaca data dari project `global`**, path tetap `/media/petrick/Parquet/trading_data/` (read-only).

---

## Daftar Isi

1. [Struktur Direktori Parquet](#1-struktur-direktori-parquet)
2. [Archive/Tables: 28 Tabel Siap Pakai](#2-archivetables-28-tabel-siap-pakai)
3. [Raw Subdirs: 53 Direktori Data Legacy](#3-raw-subdirs-53-direktori-data-legacy)
4. [Sqlite_Backup: 77 Tabel Backup Database Lama](#4-sqlite_backup-77-tabel-backup-database-lama)
5. [Data Berharga yang Belum Di-migrate](#5-data-berharga-yang-belum-di-migrate)
6. [Masalah dan Yang Perlu Diperbaiki](#6-masalah-dan-yang-perlu-diperbaiki)
7. [Rekomendasi](#7-rekomendasi)

---

## 1. Struktur Direktori Parquet

```
/media/petrick/Parquet/trading_data/
│
├── raw/                          # 1024 items
│   ├── *.JK_*.parquet            # 971 ticker OHLCV files (naming: TICKER_1d_TIMESTAMP atau TICKER_TIMESTAMP)
│   ├── *.X parquet               # 3 forex files (EURIDR, IDR, JPYIDR — quality=0.0, skipped)
│   ├── ohlcv/                    # 27 files, 23.1MB — OHLCV per tahun (2000-2026)
│   ├── saham_historical/         # 27 files, 0.6MB — historical snapshot per tahun
│   ├── chart_patterns/           # 27 files, 0.4MB — pattern detection per tahun
│   ├── multi_asset/              # 43 files, 0.3MB — multi-asset price history
│   ├── di_ohlcv_daily/           # 3 files, 0.8MB — daily OHLCV dengan UUID instrument_id
│   ├── sqlite_backup/            # 77 files, 72.1MB — BACKUP DATABASE LAMA (TERLENGKAP)
│   ├── commodity/                # 1 file — KOMODITAS (CPO, batubara, nikel, tembaga, dll)
│   ├── stock_ipo/                # 1 file — IPO data (348 entries)
│   ├── macro/                    # 1 file — makro Indonesia (BI rate, inflasi, GDP, kurs)
│   ├── global/                   # 1 file — indeks global snapshot
│   ├── ihsg/                     # 1 file — IHSG history
│   ├── sentiment/                # 1 file — news sentiment (921 entries)
│   ├── event_eksternal/          # 1 file — geopolitical events (119 entries)
│   ├── kebijakan_regulasi/       # 1 file — policy events (179 entries)
│   ├── corporate_governance/     # 1 file — GCG data (208 entries)
│   ├── esg_scores/               # 1 file — ESG scores (164 entries)
│   ├── stock_personality/        # 1 file — personality (11 entries)
│   ├── saham/                    # 1 file — saham snapshot (359 entries, dengan PER/PBV/ROE/DER)
│   ├── sektor/                   # 1 file — sektor master (11 entries)
│   ├── mm_*/                     # 6 dirs — master data (exchange, instrument, issuer, listing, security)
│   ├── sqlite_*/                 # 4 dirs — sqlite export (global_market, instruments, macro, ohlcv)
│   └── [30+ dirs lainnya]        # ai_*, backtest, blind_forecast, dll
│
└── archive/                      # 6 subdirs
    ├── ohlcv/                    # 993 files — OHLCV per ticker (latest snapshot)
    ├── tables/                   # 28 files — tabel siap pakai untuk bootstrap
    ├── foreign_flow_idx/         # 2 files — IDX foreign flow scrape
    ├── broker_flow_idx/          # 2 files — IDX broker flow scrape
    ├── instrument_master/        # 1 file — instrument master (latest)
    └── trading_suspensions/      # 1 file — trading suspensions
```

---

## 2. Archive/Tables: 28 Tabel Siap Pakai

Tabel-tabel ini sudah di-migrate ke SQLite via `scripts/bootstrap_from_parquet.py`.

| File | Rows | Size | Kolom Utama | Status |
|------|------|------|-------------|--------|
| `ohlcv.parquet` | 2,913,473 | 41.7MB | ticker, timestamp, OHLCV, adjusted_close, data_quality_score | ✅ Sudah di DB |
| `foreign_flow.parquet` | 103,046 | 3.3MB | ticker, date, foreign_buy/sell/net, domestic_buy/sell/net | ✅ Sudah di DB |
| `broker_flow.parquet` | 15,830 | 0.3MB | ticker, date, broker, buy/sell volume/value, net | ✅ Sudah di DB |
| `macro_data.parquet` | 10,036 | 0.1MB | series_name, date, value, unit, source, frequency | ✅ Sudah di DB |
| `scores.parquet` | 9,830 | 0.2MB | ticker, engine, score, breakdown, as_of | ✅ Sudah di DB |
| `technical_indicators.parquet` | 11,136 | 0.1MB | ticker, date, indicator, value, timeframe, source | ✅ Sudah di DB |
| `relationship_matrix.parquet` | 12,077 | 0.2MB | asset_a, asset_b, window, correlation, lag | ✅ Sudah di DB |
| `corporate_actions.parquet` | 6,365 | 0.1MB | ticker, action_type, announce/ex/record/payment_date, value | ✅ Sudah di DB |
| `dividends.parquet` | 5,974 | 0.1MB | ticker, ex/record/payment_date, amount, currency, frequency | ✅ Sudah di DB |
| `instrument_master.parquet` | 992 | 0.1MB | ticker, name, sector, subsector, exchange, listing/delisting_date, is_active, asset_class | ✅ Sudah di DB |
| `fundamental_data.parquet` | 991 | 0.1MB | ticker, date, PE, PB, ROE, DER, dividend_yield, EPS, revenue, total_assets | ✅ Sudah di DB |
| `stock_personality.parquet` | 944 | 0.1MB | kode, volatility_regime, trend_bias, beta_vs_ihsg, liquidity_score, personality_label | ✅ Sudah di DB |
| `fear_greed.parquet` | 466 | 0.0MB | tanggal, nilai, label | ✅ Sudah di DB |
| `market_calendar.parquet` | 365 | 0.0MB | date, exchange, is_trading_day, holiday_name, half_day | ✅ Sudah di DB |
| `watchlist.parquet` | 359 | 0.0MB | ticker, is_favorite, notes | ✅ Sudah di DB |
| `esg_scores.parquet` | 164 | 0.0MB | kode, year, rating_agency, rating, score | ✅ Sudah di DB |
| `policy_events.parquet` | 179 | 0.0MB | tanggal, kategori, judul, instansi, dampak, sektor | ✅ Sudah di DB |
| `external_events.parquet` | 119 | 0.0MB | tanggal, kategori, judul, lokasi, dampak_market, sektor | ✅ Sudah di DB |
| `news.parquet` | 110 | 0.0MB | headline, body, published_at, source, entities, sentiment, impact | ✅ Sudah di DB |
| `sector_master.parquet` | 22 | 0.0MB | kode, nama, deskripsi | ✅ Sudah di DB |
| `pattern_analysis.parquet` | 2,386 | 0.1MB | ticker, date, pattern_type, confidence, direction | ✅ Sudah di DB |
| `corporate_governance.parquet` | 208 | 0.0MB | kode, year, board_commissioners, GCG_score, ACGS_score | ✅ Sudah di DB |
| `audit_log.parquet` | 3,125 | — | (audit entries) | ✅ Sudah di DB |
| `render_log.parquet` | 22 | — | ticker, table_name, last_rendered, status | ✅ Sudah di DB |
| `source_health.parquet` | 2 | — | source, last_success, last_error, status | ✅ Sudah di DB |
| `ai_scores_historical.parquet` | — | — | (AI scores history) | ✅ Sudah di DB |
| `alerts_historical.parquet` | — | — | (alerts history) | ✅ Sudah di DB |
| `backtest_results.parquet` | — | — | (backtest results) | ✅ Sudah di DB |

---

## 3. Raw Subdirs: 53 Direktori Data Legacy

Direktori di `raw/` yang **TIDAK** ada di `archive/tables` — berisi data dari database lama yang belum tentu di-migrate.

### 3.1 Data Berharga yang Belum Di-migrate

| Direktori | Rows | Kolom | Deskripsi | Ada di DB? |
|-----------|------|-------|-----------|------------|
| **`commodity/`** | 1,523 | periode, nama, satuan, harga, perubahan | **KOMODITAS IDX** (CPO, batubara, nikel, tembaga, emas, perak, timah, aluminium, gas, crude oil) — date range 2018-2026 | ❌ TIDAK ADA |
| **`stock_ipo/`** | 348 | kode, ipo_date, ipo_price, shares_offered, underwriter | **IPO data** — 348 IPO entries dengan tanggal dan harga | ❌ TIDAK ADA |
| **`macro/`** | 379 | periode, suku_bunga, inflasi, gdp_growth, kurs_usd | **Makro Indonesia** — BI rate, inflasi, GDP, kurs USD/IDR (2024-2025) | ⚠️ Sebagian (macro_data ada tapi format berbeda) |
| **`global/`** | 1,760 | tanggal, nama, negara, nilai, perubahan | **Indeks global snapshot** — Dow, S&P, Nasdaq, Nikkei, Hang Seng, dll | ⚠️ Sebagian (global_market engine pakai yfinance langsung) |
| **`ihsg/`** | 465 | tanggal, harga, perubahan, volume | **IHSG history** — 465 entries (Jun 2025 - Jul 2025) | ⚠️ Sebagian (IHSG ada di OHLCV sebagai ^JKSE) |
| **`sentiment/`** | 921 | tanggal, judul, sentimen, sumber, kode | **News sentiment** — 921 entries dengan label positif/negatif/netral | ⚠️ Sebagian (news table ada, 110 rows — ini 8x lebih banyak) |
| **`event_eksternal/`** | 119 | tanggal, kategori, judul, lokasi, dampak_market, sektor | **Geopolitical events** — konflik, pandemi, trade war | ✅ Sudah di DB (external_events) |
| **`kebijakan_regulasi/`** | 179 | tanggal, kategori, judul, instansi, dampak, sektor | **Policy events** — BI rate, OJK, BEI regulations | ✅ Sudah di DB (policy_events) |
| **`corporate_governance/`** | 208 | kode, year, board_commissioners, GCG_score, ACGS_score | **Corporate governance** — GCG/ACGS scores | ✅ Sudah di DB |
| **`esg_scores/`** | 164 | kode, year, rating_agency, rating, score | **ESG scores** | ✅ Sudah di DB |
| **`saham/`** | 359 | kode, nama, sektor, harga, PER, PBV, ROE, DER, market_cap, ipo_date | **Saham snapshot** — 359 entries dengan fundamental ratios | ⚠️ Sebagian (fundamental_data ada, tapi ini snapshot dengan lebih banyak field) |
| **`sektor/`** | 11 | kode, nama, deskripsi | **Sektor master** — 11 sektor IDX | ⚠️ Sebagian (sector_master ada, 22 rows) |
| **`multi_asset/`** | 16,560 | kode, nama, jenis, harga, change_pct, tanggal | **Multi-asset history** — indeks, komoditas, forex (1984-2026) | ❌ TIDAK ADA |
| **`chart_patterns/`** | ~700 | tanggal, kode, pattern, pattern_type, confidence | **Chart patterns** — 27 files per tahun (2000-2026) | ❌ TIDAK ADA (pattern_analysis ada tapi 2,386 rows, ini lebih banyak) |
| **`di_ohlcv_daily/`** | 10,862 | ohlcv_id, instrument_id, trade_date, OHLCV | **Daily OHLCV dengan UUID** — 3 files (2024, 2025, 2026) | ❌ TIDAK ADA (format berbeda, pakai UUID) |
| **`sqlite_global_market_data/`** | 15,046 | date, ticker, OHLCV, data_source | **Global market OHLCV** — ^GSPC, ^DJI, ^IXIC, dll | ❌ TIDAK ADA (global_market engine pakai yfinance langsung) |
| **`sqlite_macro_data/`** | 8,776 | date, series_id, value, region, category, data_source | **Macro data FRED** — FEDFUNDS, CPI, GDP, dll | ⚠️ Sebagian (macro_data ada 10,036 rows, tapi ini 8,776 rows dengan format berbeda) |
| **`sqlite_ohlcv/`** | 23,851 | date, ticker, OHLCV | **OHLCV legacy** — 23,851 rows | ❌ TIDAK ADA (sudah superseded oleh archive/tables/ohlcv) |

### 3.2 Data Master (mm_*)

| Direktori | Rows | Kolom | Deskripsi | Ada di DB? |
|-----------|------|-------|-----------|------------|
| `mm_exchange/` | 13 | exchange_id, name, mic_code, country, timezone, currency | Master exchange (IDX, NYSE, Nasdaq, dll) | ❌ TIDAK ADA |
| `mm_instrument/` | 107 | instrument_id, security_id, asset_class, instrument_type, currency, status | Master instrument (UUID-based) | ❌ TIDAK ADA |
| `mm_issuer/` | 57 | issuer_id, legal_name, short_name, country, sector_code, industry_code | Master issuer (BCA, BRI, Mandiri, dll) | ❌ TIDAK ADA |
| `mm_listing/` | 47 | listing_id, instrument_id, exchange_id, ticker, isin, currency, listing_date | Master listing (EIDO, AAXJ, VWO, dll) | ❌ TIDAK ADA |
| `mm_security/` | 87 | security_id, issuer_id, security_type, currency, par_value, status | Master security | ❌ TIDAK ADA |

### 3.3 Data Aplikasi Lama (tidak relevan untuk decision support)

| Direktori | Rows | Deskripsi | Relevan? |
|-----------|------|-----------|----------|
| `ai_alerts/` | 188 | AI alert history | ⚠️ Opsional |
| `ai_auto_trade/` | — | AI auto trade log | ⚠️ Opsional |
| `ai_correlation/` | — | AI correlation analysis | ⚠️ Opsional |
| `ai_portfolio/` | — | AI portfolio recommendations | ⚠️ Opsional |
| `ai_scores/` | — | AI scores | ⚠️ Opsional |
| `backtest_result/` | — | Backtest results | ⚠️ Opsional |
| `blind_forecast/` | — | Blind forecast predictions | ⚠️ Opsional |
| `data_fetch_log/` | — | Data fetch log | ❌ Tidak |
| `ml_config/` | 7 | ML config key-value | ❌ Tidak |
| `notifications/` | 29 | Notification history | ❌ Tidak |
| `portfolio/` | 5 | Portfolio positions (legacy) | ❌ Tidak |
| `price_alerts/` | 4 | Price alert config | ❌ Tidak |
| `strategy_config/` | 4 | Strategy config | ❌ Tidak |
| `trade_journal/` | 4 | Trade journal (legacy) | ❌ Tidak |
| `trader_saldo/` | 6 | Trader saldo (legacy) | ❌ Tidak |
| `training_log/` | 4 | ML training log | ❌ Tidak |
| `transaksi/` | 5 | Transaksi (legacy) | ❌ Tidak |

---

## 4. Sqlite_Backup: 77 Tabel Backup Database Lama

**Ini adalah harta karun data.** Direktori `raw/sqlite_backup/` (72.1MB) berisi backup tabel-tabel dari database lama yang **jauh lebih lengkap** dari yang ada di `archive/tables/`.

### 4.1 Tabel yang JAUH Lebih Lengkap di Sqlite_Backup

| Tabel | Archive/Tables | Sqlite_Backup | Selisih | Catatan |
|-------|---------------|---------------|---------|---------|
| **news** | 110 rows | **50,921 rows** | **462x lebih banyak** | Archive hanya snapshot terbaru, backup punya history lengkap |
| **technical_indicators** | 11,136 rows | **871,324 rows** | **78x lebih banyak** | Archive hanya latest, backup punya history per ticker per date |
| **pattern_analysis** | 2,386 rows | **50,053 rows** | **21x lebih banyak** | Archive hanya latest, backup punya history |
| **stock_ipo** | 348 rows (raw/) | **1,392 rows** | **4x lebih banyak** | Backup punya IPO data lebih lengkap |
| **stock_personality** | 944 rows | **802 rows** | 0.85x | Format berbeda (backup lebih detail: personality_type, volatility_profile) |
| **relationship_matrix** | 12,077 rows | **65 rows** | 0.005x | Archive lebih lengkap |
| **scores** | 9,830 rows | **8,696 rows** | 0.88x | Hampir sama |
| **ohlcv** | 2,913,473 rows | **2,038,595 rows** | 0.70x | Archive lebih lengkap (sudah di-update) |

### 4.2 Tabel HANYA di Sqlite_Backup (Tidak Ada di Archive/Tables)

| Tabel | Rows | Kolom | Deskripsi | Relevan? |
|-------|------|-------|-----------|----------|
| **`idx_sentiment_data`** | **212,003** | symbol, date, sentiment_score, sentiment_label, news_count, social_media_sentiment, analyst_sentiment | **Sentiment per ticker per hari** — 212K rows! | ✅ **SANGAT RELEVAN** |
| **`idx_social_media_sentiment`** | 2,350 | symbol, platform, post_id, content, author, author_followers, posted_at | **Social media sentiment** — Reddit/X posts | ✅ **SANGAT RELEVAN** |
| **`idx_quarterly_earnings`** | 20 | symbol, quarter_date, earnings, revenue, earnings_estimate, revenue_estimate, earnings_surprise | **Quarterly earnings** — dengan estimate & surprise | ✅ **RELEVAN** (earnings season) |
| **`idx_stock_splits`** | 378 | symbol, date, ratio | **Stock splits** — 378 entries | ✅ **RELEVAN** (corporate actions) |
| **`idx_broker_summary`** | — | — | Broker summary | ✅ RELEVAN |
| **`idx_foreign_flow_summary`** | — | — | Foreign flow summary | ✅ RELEVAN |
| **`shareholders`** | **7,495** | kode, nama, jumlah_saham, persentase, tipe | **Pemegang saham** — 7,495 entries | ✅ **RELEVAN** (insider tracking) |
| **`valuation_cache`** | 1,226 | ticker, date, method, intrinsic_value, market_price, upside_pct, assumptions | **Valuation** — DCF, DDM, dll | ✅ **RELEVAN** |
| **`saham_snapshot`** | **122,026** | kode, tanggal, harga, perubahan, volume, PER, PBV | **Saham snapshot history** — 122K rows! | ✅ **RELEVAN** (historical valuation) |
| **`saham_historical`** | 66,360 | kode, tanggal, harga_close/open/high/low, volume | **Saham historical** — 66K rows | ⚠️ Sebagian (sudah di OHLCV) |
| **`legacy_global_market_data`** | 45,138 | date, ticker, OHLCV | **Global market OHLCV** — 45K rows | ✅ **RELEVAN** |
| **`legacy_macro_data`** | 26,328 | date, series_id, value, region, category, data_source | **Macro data FRED** — 26K rows | ✅ **RELEVAN** |
| **`legacy_ohlcv`** | 71,553 | date, ticker, OHLCV | **Legacy OHLCV** — 71K rows | ⚠️ Sebagian (sudah di OHLCV) |
| **`legacy_instruments`** | 63 | ticker, name, instrument_type, exchange, sector, industry, currency, board | **Legacy instruments** — 63 tickers | ⚠️ Sebagian (instrument_master lebih lengkap) |
| **`pattern_candidates`** | 208 | kode, pattern, pattern_type, detected_at, detected_date, current_price | **Pattern candidates** | ⚠️ Opsional |
| **`pattern_reliability`** | 421 | kode, pattern, pattern_type, total_occurrences, success_count, fail_count, win_rate | **Pattern reliability stats** | ✅ **RELEVAN** |
| **`ihsg_data`** | 1,860 | tanggal, harga, perubahan, volume | **IHSG history** — 1,860 rows | ⚠️ Sebagian (ada di OHLCV ^JKSE) |
| **`system_state`** | 199 | key, value, updated_at | System state key-value | ❌ Tidak |
| **`orders`** | 6 | ticker, order_type, quantity, price | Orders (legacy) | ❌ Tidak |
| **`positions`** | 14 | ticker, quantity, avg_entry_price, current_price, stop_loss, take_profit | Positions (legacy) | ❌ Tidak |
| **`ml_training_log`** | 16 | mode, stocks, lookback, forecast_horizon, status | ML training log | ❌ Tidak |
| **`trade_journal_imported`** | 16 | trader_id, kode, jenis, tanggal, harga, jumlah, alasan | Trade journal imported | ❌ Tidak |

---

## 5. Data Berharga yang Belum Di-migrate

### 5.1 Prioritas Tinggi (Langsung Meningkatkan Decision Quality)

| Data | Lokasi | Rows | Kenapa Penting | Cara Migrate |
|------|--------|------|----------------|--------------|
| **Commodity (CPO, coal, nickel, copper, tin, gold, silver, aluminium, gas, oil)** | `raw/commodity/` | 1,523 | **Gap paling kritis** dari dokumen 89 — 35% IDX market cap tidak tracked. Data sudah ada! | Tambah tabel `commodity_prices` di DB, import parquet, tambah commodity-to-stock mapping di relationship engine |
| **Sentiment per ticker per hari** | `raw/sqlite_backup/idx_sentiment_data.parquet` | 212,003 | Sentiment engine saat ini hanya 110 news rows. Ini 212K rows dengan sentiment_score per ticker per hari | Migrate ke tabel `sentiment_history` di DB, atau enrich `news` table |
| **Social media sentiment** | `raw/sqlite_backup/idx_social_media_sentiment.parquet` | 2,350 | Social media engine saat ini = stub. Ini punya 2,350 posts dengan content + author | Migrate ke tabel `social_media_sentiment` di DB |
| **Shareholders (pemegang saham)** | `raw/sqlite_backup/shareholders.parquet` | 7,495 | Insider trading tracking — gap dari dokumen 89. 7,495 entries dengan jumlah_saham, persentase, tipe | Migrate ke tabel `shareholders` di DB |
| **Quarterly earnings** | `raw/sqlite_backup/idx_quarterly_earnings.parquet` | 20 | Earnings season timing — gap dari dokumen 89. Hanya 20 rows tapi format bagus (earnings, revenue, estimate, surprise) | Migrate ke tabel `quarterly_earnings` di DB |
| **Stock splits** | `raw/sqlite_backup/idx_stock_splits.parquet` | 378 | Corporate actions — 378 split entries (lebih lengkap dari corporate_actions 6,365 yang campur) | Enrich `corporate_actions` table |
| **Saham snapshot history** | `raw/sqlite_backup/saham_snapshot.parquet` | 122,026 | Historical PER/PBV/ROE/DER per saham per hari — 122K rows! Fundamental engine saat ini hanya snapshot | Migrate ke tabel `fundamental_history` atau enrich `fundamental_data` |
| **Valuation cache** | `raw/sqlite_backup/valuation_cache.parquet` | 1,226 | DCF/DDM valuation per ticker — intrinsic_value, market_price, upside_pct | Migrate ke tabel `valuation_cache` di DB |
| **Pattern reliability stats** | `raw/sqlite_backup/pattern_reliability.parquet` | 421 | Win rate per pattern per ticker — berguna untuk strategy validation | Migrate ke tabel `pattern_reliability` di DB |

### 5.2 Prioritas Sedang (Enrich Data Existing)

| Data | Lokasi | Rows | Kenapa Penting | Cara Migrate |
|------|--------|------|----------------|--------------|
| **News history lengkap** | `raw/sqlite_backup/news.parquet` | 50,921 | News table saat ini hanya 110 rows. Backup punya 50,921 — 462x lebih banyak | Enrich `news` table di DB |
| **Technical indicators history** | `raw/sqlite_backup/technical_indicators.parquet` | 871,324 | Technical_indicators saat ini 11,136 rows. Backup punya 871K — 78x lebih banyak | Enrich `technical_indicators` table |
| **Pattern analysis history** | `raw/sqlite_backup/pattern_analysis.parquet` | 50,053 | Pattern_analysis saat ini 2,386 rows. Backup punya 50K — 21x lebih banyak | Enrich `pattern_analysis` table |
| **IPO data lengkap** | `raw/sqlite_backup/stock_ipo.parquet` | 1,392 | IPO data di raw/ hanya 348. Backup punya 1,392 — 4x lebih banyak | Migrate ke tabel `ipo_data` di DB |
| **Legacy macro data (FRED)** | `raw/sqlite_backup/legacy_macro_data.parquet` | 26,328 | Macro_data saat ini 10,036 rows. Backup punya 26K — 2.6x lebih banyak (FEDFUNDS, CPI, GDP, dll) | Enrich `macro_data` table |
| **Legacy global market data** | `raw/sqlite_backup/legacy_global_market_data.parquet` | 45,138 | Global market OHLCV — 45K rows (^GSPC, ^DJI, ^IXIC, dll) | Enrich atau tambah tabel `global_market_ohlcv` |
| **Multi-asset history** | `raw/multi_asset/` | 16,560 | Multi-asset price history (indeks, komoditas, forex) 1984-2026 | Migrate ke tabel `multi_asset_history` di DB |

### 5.3 Prioritas Rendah (Nice to Have)

| Data | Lokasi | Rows | Catatan |
|------|--------|------|---------|
| Master data (mm_*) | `raw/mm_*/` | 47-107 | UUID-based, tidak kompatibel dengan schema existing |
| Saham historical | `raw/sqlite_backup/saham_historical.parquet` | 66,360 | Sudah di OHLCV (format berbeda) |
| Legacy OHLCV | `raw/sqlite_backup/legacy_ohlcv.parquet` | 71,553 | Sudah superseded |
| Chart patterns per tahun | `raw/chart_patterns/` | ~700 | Format berbeda dari pattern_analysis |

---

## 6. Masalah dan Yang Perlu Diperbaiki

### 6.1 Masalah Schema — Kolom Bahasa Indonesia

Beberapa parquet di `raw/` menggunakan kolom Bahasa Indonesia yang tidak kompatibel dengan schema DB (English):

| File | Kolom ID | Kolom EN (di DB) | Status |
|------|----------|-------------------|--------|
| `raw/event_eksternal/` | tanggal, kategori, judul, lokasi, dampak_market, sektor | date, category, title, location, market_impact, sector | ✅ Sudah ada mapping di `bootstrap_from_parquet.py` |
| `raw/kebijakan_regulasi/` | tanggal, kategori, judul, instansi, dampak, sektor | date, category, title, agency, impact, sector | ✅ Sudah ada mapping |
| `raw/commodity/` | periode, nama, satuan, harga, perubahan | date, commodity_name, unit, price, change_pct | ❌ Belum ada mapping |
| `raw/macro/` | periode, suku_bunga, inflasi, gdp_growth, kurs_usd | date, bi_rate, inflation, gdp_growth, usd_idr | ❌ Belum ada mapping |
| `raw/global/` | tanggal, nama, negara, nilai, perubahan | date, index_name, country, value, change_pct | ❌ Belum ada mapping |
| `raw/ihsg/` | tanggal, harga, perubahan, volume | date, price, change, volume | ❌ Belum ada mapping |
| `raw/sentiment/` | tanggal, judul, sentimen, sumber, kode | date, headline, sentiment, source, ticker | ❌ Beluk ada mapping |
| `raw/saham/` | kode, nama, sektor, harga, perubahan, per, pbv, roe, der | ticker, name, sector, price, change, pe_ratio, pb_ratio, roe, debt_to_equity | ❌ Belum ada mapping |

### 6.2 Masalah Duplikasi Data

| Data | Lokasi 1 | Lokasi 2 | Lokasi 3 | Masalah |
|------|----------|----------|----------|---------|
| OHLCV | `archive/tables/ohlcv.parquet` (2.9M) | `raw/ohlcv/` (27 files, 23.1MB) | `raw/sqlite_backup/ohlcv.parquet` (2M) | 3 copy, archive/tables adalah yang paling updated |
| Macro | `archive/tables/macro_data.parquet` (10K) | `raw/macro/` (379) | `raw/sqlite_backup/legacy_macro_data.parquet` (26K) | 3 copy dengan format berbeda |
| Global market | (yfinance langsung) | `raw/global/` (1,760) | `raw/sqlite_backup/legacy_global_market_data.parquet` (45K) | Tidak ada di archive/tables |
| News | `archive/tables/news.parquet` (110) | `raw/sentiment/` (921) | `raw/sqlite_backup/news.parquet` (50,921) | 3 copy, sqlite_backup paling lengkap |
| IPO | `raw/stock_ipo/` (348) | — | `raw/sqlite_backup/stock_ipo.parquet` (1,392) | 2 copy, sqlite_backup paling lengkap |

### 6.3 Masalah Data Stale

| Data | Last Update | Masalah |
|------|-------------|---------|
| `raw/macro/` | Des 2025 | Hanya sampai Des 2025, tidak ada 2026 |
| `raw/global/` | Jul 2025 | Snapshot saja, tidak ada history |
| `raw/ihsg/` | Jul 2025 | Hanya Jun-Jul 2025 |
| `raw/sentiment/` | Jul 2025 | Hanya sampai Jul 2025 |
| `raw/commodity/` | Jul 2026 | Paling updated, tapi ada gap (missing months) |
| `raw/saham/` | Jul 2026 | Snapshot, bukan time series |

### 6.4 Masalah Format

| Masalah | Lokasi | Detail |
|---------|--------|--------|
| **UUID-based instrument_id** | `raw/di_ohlcv_daily/`, `raw/mm_*/` | Tidak kompatibel dengan schema DB yang pakai ticker string |
| **Ticker tanpa .JK suffix** | `raw/saham/`, `raw/stock_ipo/`, `raw/sqlite_backup/shareholders.parquet` | DB pakai format `BBCA.JK`, parquet pakai `BBCA` |
| **Date format mixed** | `raw/` various | Ada yang `2025-07-11` (string), ada yang datetime, ada yang `20250711` |
| **Kolom `id` auto-increment** | `raw/saham/`, `raw/sentiment/`, dll | Tidak relevan untuk migrate (DB punya auto-increment sendiri) |

### 6.5 Yang Perlu Diperbaiki di Parquet Existing

| File | Masalah | Perbaikan |
|------|---------|-----------|
| `raw/commodity/commodity.parquet` | Kolom Bahasa Indonesia (periode, nama, satuan, harga, perubahan) | Rename ke English: date, commodity_name, unit, price, change_pct |
| `raw/commodity/commodity.parquet` | Ticker tidak ada .JK suffix di mapping komoditas → saham | Tambah kolom `affected_tickers` (e.g., CPO → AALI.JK, LSIP.JK, SIMP.JK) |
| `raw/commodity/commodity.parquet` | Gap data: beberapa bulan missing (e.g., Mar 2024, Jun 2024, Sep 2024) | Backfill dari yfinance atau sumber lain |
| `raw/macro/macro.parquet` | Hanya 379 rows (2024-2025), tidak ada 2026 | Fetch BI rate, inflasi, GDP terbaru dari BPS/BI |
| `raw/macro/macro.parquet` | Kolom Bahasa Indonesia | Rename ke English: date, bi_rate, inflation, gdp_growth, usd_idr |
| `raw/sqlite_backup/idx_sentiment_data.parquet` | 212K rows tapi tidak di-migrate | Migrate ke DB — tabel `sentiment_history` |
| `raw/sqlite_backup/news.parquet` | 50,921 rows tapi hanya 110 di DB | Migrate ke DB — enrich `news` table |
| `raw/sqlite_backup/technical_indicators.parquet` | 871K rows tapi hanya 11,136 di DB | Migrate ke DB — enrich `technical_indicators` table |
| `raw/sqlite_backup/shareholders.parquet` | 7,495 rows, ticker tanpa .JK | Migrate ke DB — tambah .JK suffix, tabel `shareholders` |
| `raw/sqlite_backup/saham_snapshot.parquet` | 122K rows dengan PER/PBV/ROE/DER history | Migrate ke DB — tabel `fundamental_history` |
| `raw/sqlite_backup/valuation_cache.parquet` | 1,226 rows DCF/DDM valuation | Migrate ke DB — tabel `valuation_cache` |
| `raw/sqlite_backup/idx_social_media_sentiment.parquet` | 2,350 rows social media posts | Migrate ke DB — tabel `social_media_sentiment` |

---

## 7. Rekomendasi

### 7.1 Quick Wins (1-2 minggu, high impact)

| Aksi | Estimasi | Impact |
|------|----------|--------|
| **Migrate commodity data** | 2 hari | Tutup gap terbesar dari dokumen 89 (komoditas spesifik IDX). Data sudah ada, tinggal rename kolom + import |
| **Migrate sentiment history (212K rows)** | 3 hari | Sentiment engine saat ini hanya 110 news. 212K rows akan membuat sentiment scoring jauh lebih akurat |
| **Migrate shareholders (7,495 rows)** | 1 hari | Insider trading tracking — gap dari dokumen 89 |
| **Migrate quarterly earnings (20 rows)** | 1 hari | Earnings season timing — gap dari dokumen 89 |
| **Migrate valuation cache (1,226 rows)** | 1 hari | DCF/DDM valuation per ticker |

### 7.2 Medium Term (1-3 bulan)

| Aksi | Estimasi | Impact |
|------|----------|--------|
| **Migrate news history (50,921 rows)** | 1 minggu | 462x lebih banyak news data untuk sentiment engine |
| **Migrate technical indicators history (871K rows)** | 1 minggu | 78x lebih banyak technical history untuk backtest |
| **Migrate saham snapshot (122K rows)** | 1 minggu | Historical fundamental ratios (PER/PBV/ROE/DER per hari) |
| **Migrate pattern reliability (421 rows)** | 2 hari | Win rate per pattern per ticker untuk strategy validation |
| **Migrate legacy macro data (26K rows)** | 1 minggu | 2.6x lebih banyak macro data (FRED: FEDFUNDS, CPI, GDP) |
| **Migrate legacy global market (45K rows)** | 1 minggu | Global market OHLCV history |

### 7.3 Yang Tidak Perlu Di-migrate

| Data | Alasan |
|------|--------|
| `raw/sqlite_backup/legacy_ohlcv.parquet` (71K) | Sudah superseded oleh archive/tables/ohlcv (2.9M rows) |
| `raw/sqlite_backup/legacy_instruments.parquet` (63) | instrument_master (992 rows) lebih lengkap |
| `raw/mm_*/` (UUID-based) | Tidak kompatibel dengan schema DB |
| `raw/sqlite_backup/orders.parquet` (6) | Legacy orders, tidak relevan |
| `raw/sqlite_backup/positions.parquet` (14) | Legacy positions, tidak relevan |
| `raw/sqlite_backup/system_state.parquet` (199) | System state key-value, tidak relevan |
| `raw/sqlite_backup/ml_training_log.parquet` (16) | ML training log, tidak relevan |
| `raw/ai_*/`, `raw/notifications/`, `raw/portfolio/`, `raw/price_alerts/`, `raw/strategy_config/`, `raw/trade_journal/`, `raw/trader_saldo/`, `raw/transaksi/` | Data aplikasi lama, tidak relevan untuk decision support |

### 7.4 Schema Baru yang Diperlukan

```sql
-- Commodity prices (prioritas 1)
CREATE TABLE IF NOT EXISTS commodity_prices (
    date TEXT NOT NULL,
    commodity_name TEXT NOT NULL,
    unit TEXT,
    price REAL,
    change_pct REAL,
    source TEXT DEFAULT 'legacy_parquet',
    PRIMARY KEY (date, commodity_name)
);

-- Sentiment history (prioritas 1)
CREATE TABLE IF NOT EXISTS sentiment_history (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    sentiment_score REAL,
    sentiment_label TEXT,
    news_count INTEGER,
    social_media_sentiment REAL,
    analyst_sentiment REAL,
    source TEXT DEFAULT 'legacy_parquet',
    PRIMARY KEY (ticker, date)
);

-- Shareholders (prioritas 1)
CREATE TABLE IF NOT EXISTS shareholders (
    ticker TEXT NOT NULL,
    holder_name TEXT NOT NULL,
    shares BIGINT,
    percentage REAL,
    holder_type TEXT,
    updated_at TEXT,
    PRIMARY KEY (ticker, holder_name)
);

-- Quarterly earnings (prioritas 1)
CREATE TABLE IF NOT EXISTS quarterly_earnings (
    ticker TEXT NOT NULL,
    quarter_date TEXT NOT NULL,
    earnings REAL,
    revenue REAL,
    earnings_estimate REAL,
    revenue_estimate REAL,
    earnings_surprise REAL,
    PRIMARY KEY (ticker, quarter_date)
);

-- Valuation cache (prioritas 1)
CREATE TABLE IF NOT EXISTS valuation_cache (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    method TEXT,
    intrinsic_value REAL,
    market_price REAL,
    upside_pct REAL,
    assumptions TEXT,
    source TEXT,
    PRIMARY KEY (ticker, date, method)
);

-- Social media sentiment (prioritas 2)
CREATE TABLE IF NOT EXISTS social_media_sentiment (
    ticker TEXT,
    platform TEXT,
    post_id TEXT,
    content TEXT,
    author TEXT,
    author_followers INTEGER,
    posted_at TEXT,
    sentiment_score REAL,
    PRIMARY KEY (post_id)
);

-- Fundamental history (prioritas 2)
CREATE TABLE IF NOT EXISTS fundamental_history (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    pe_ratio REAL,
    pb_ratio REAL,
    roe REAL,
    debt_to_equity REAL,
    market_cap REAL,
    source TEXT DEFAULT 'saham_snapshot',
    PRIMARY KEY (ticker, date)
);

-- Pattern reliability (prioritas 2)
CREATE TABLE IF NOT EXISTS pattern_reliability (
    ticker TEXT NOT NULL,
    pattern TEXT NOT NULL,
    pattern_type TEXT,
    total_occurrences INTEGER,
    success_count INTEGER,
    fail_count INTEGER,
    win_rate REAL,
    PRIMARY KEY (ticker, pattern)
);
```

### 7.5 Commodity-to-Stock Mapping

Data komoditas di `raw/commodity/` punya jenis: CPO, batubara, nikel, tembaga, emas, perak, timah, aluminium, gas, crude oil. Mapping ke emiten IDX:

| Komoditas | Emiten IDX |
|-----------|------------|
| CPO | AALI.JK, LSIP.JK, SIMP.JK, DSNG.JK, ANJT.JK, SGRO.JK, SSMS.JK |
| Batubara | PTBA.JK, ITMG.JK, ADRO.JK, HRUM.JK, BYAN.JK, INDY.JK, BSSR.JK |
| Nikel | INCO.JK, ANTM.JK, MDKA.JK |
| Tembaga | ANTM.JK, MDKA.JK |
| Emas | ANTM.JK, MDKA.JK |
| Timah | TINS.JK |
| Aluminium | INAL.JK (jika listed) |
| Gas | PGAS.JK |
| Crude Oil | MEDC.JK, ENRG.JK, BULL.JK |

---

## Referensi

### Internal (Pustaka)
- `88-gap-teori-vs-praktek.md` — Gap analysis teori vs praktek
- `89-faktor-pasar-modal-analisis-implementasi.md` — Audit faktor pasar modal (komoditas spesifik sebagai gap paling kritis)

### Internal (Codebase)
- `scripts/bootstrap_from_parquet.py` — Script bootstrap dari parquet ke SQLite
- `src/trading_system/data/storage.py` — DataStorage class, schema definition
- `alembic/versions/` — Database migrations

### Data Location
- Raw: `/media/petrick/Parquet/trading_data/raw/` (dipakai project global — read-only dari luar)
- Archive: `/media/petrick/Parquet/trading_data/archive/` (dipakai project global — read-only dari luar)
- Sqlite backup: `/media/petrick/Parquet/trading_data/raw/sqlite_backup/` (72.1MB, 77 files)
- **Parquet baru (di luar project global):** `/media/petrick/Parquet/pustaka_data/` (atau nama project baru)

### Konvensi Penyimpanan Parquet

| Path | Pemilik | Akses | Catatan |
|------|--------|-------|--------|
| `/media/petrick/Parquet/trading_data/` | Project `global` (trading-system) | Read-only dari luar | 287MB, sudah dipakai untuk bootstrap DB |
| `/media/petrick/Parquet/pustaka_data/` | Pustaka / project baru | Read-write | Buat direktori ini untuk parquet baru |
| `/media/petrick/Parquet/<nama_lain>/` | Project lain | Read-write | Satu direktori per project |

**Aturan:**
1. Satu project = satu direktori parquet di bawah `/media/petrick/Parquet/`
2. Jangan menulis ke direktori project lain (hanya baca jika perlu)
3. Struktur internal: `raw/` untuk data mentah, `archive/` untuk data terstruktur
4. Format file: `{nama_tabel}_{YYYYMMDD}_{HHMMSS}.parquet` atau `{ticker}_{timeframe}_{timestamp}.parquet`

---

> **Catatan:** Parquet di `/media/petrick/Parquet/trading_data` adalah sumber data awal untuk bootstrap database. `archive/tables/` (28 tabel) sudah di-migrate ke SQLite. Namun `raw/sqlite_backup/` (77 tabel, 72.1MB) berisi data **jauh lebih lengkap** yang belum di-migrate — termasuk 212K sentiment rows, 50K news, 871K technical indicators, 122K fundamental snapshots, 7,495 shareholders, dan 1,523 commodity prices. Data komoditas adalah penemuan paling penting: **gap terbesar dari dokumen 89 (komoditas spesifik IDX) ternyata sudah punya datanya** — tinggal di-migrate dan di-mapping ke emiten. **Konvensi penyimpanan:** `/media/petrick/Parquet/trading_data/` dipakai project `global` — untuk parquet baru di luar project, gunakan direktori terpisah seperti `/media/petrick/Parquet/pustaka_data/`.
