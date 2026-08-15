# Database Normalization — Migration 0022 + 0023

**Tanggal:** 2026-08-15
**Migration IDs:** 0022 (P0-P2), 0023 (P3)
**Alembic Head:** 0023 (sebelumnya 0021)

## Ringkasan

Normalisasi database PostgreSQL untuk menghilangkan duplikasi tabel, merge overlapping schema, dan menambah referential integrity. Perubahan ini bersifat **breaking change** — semua kode yang mereferensikan tabel lama harus diupdate.

## Perubahan Detail

### 1. Tabel Dihapus

| Tabel | Alasan | Pengganti |
|-------|--------|-----------|
| `broker` | Duplikat `brokers` (20 rows sama, `brokers` punya UUID + FK) | `brokers` |
| `broker_bursa` | Junction table untuk `broker` yang sudah dihapus | `brokers.exchange_mic` (langsung di tabel brokers) |

### 2. Tabel Di-merge

| Tabel Lama | Di-merge Ke | Mekanisme |
|------------|-------------|-----------|
| `market_registry` | `exchanges` | Data dimigrasi, tabel di-drop, **compatibility view** dibuat |
| `instrument_master` | `instruments` | Data dimigrasi, tabel di-drop, **compatibility view** dibuat |

**Compatibility views** (`market_registry`, `instrument_master`) tetap tersedia di PostgreSQL untuk backward compatibility dengan kode lama yang menggunakan raw SQL. View ini memetakan kolom lama ke kolom baru.

### 3. Kolom Dihapus dari `stock_personality`

Kolom prediksi yang sudah ada di `stock_prediction` dihapus dari `stock_personality` untuk mengurangi write amplification:

- `ml_signal`, `multifactor_signal`, `composite_signal`
- `factors_summary`
- `predicted_direction`, `predicted_price`, `predicted_return_pct`
- `prediction_confidence`, `prediction_updated_at`

**Gunakan `stock_prediction` untuk semua data prediksi.**

### 4. Kolom Baru di `exchanges` (dari `market_registry`)

- `trading_hours`, `supports_dst`, `settlement_cycle`
- `tick_size_rule`, `data_suffix`, `trading_status`, `updated_at`

### 5. Kolom Baru di `instruments` (dari `instrument_master`)

- `reporting_currency`, `lot_size`, `tick_size`, `subsector`
- `underlying_ticker`, `suspension_date`, `delisting_date`, `board`
- `free_float`, `market_cap`, `listed_shares`, `tradeable_shares`
- `delisting_risk_score`, `delisting_risk_reason`
- `former_ticker`, `former_name`, `index_category`, `region`, `updated_at`

### 6. Foreign Key Constraints Baru

FK `NOT VALID` ditambahkan dari 17 tabel ke `instruments(ticker)`:

- `foreign_flow`, `fundamental_data`, `technical_indicators`, `technical_indicators_wide`
- `daily_trading_stats`, `daily_risk_metrics`, `scores`, `dividends`
- `corporate_governance`, `esg_scores`, `news_sentiment`, `pattern_analysis`
- `trading_suspensions`, `valuation_cache`, `broker_flow`, `watchlist`, `stock_prediction`

**Catatan:** `stock_prices` tidak mendapat FK karena merupakan partitioned table (PostgreSQL tidak support NOT VALID FK pada partitioned table).

FK menggunakan `NOT VALID` artinya existing data tidak divalidasi, hanya insert/update baru yang akan di-check.

### 7. Unique Constraint Baru

- `news_sentiment`: `UNIQUE (ticker, date, headline)`

**Deferred** (karena keterbatasan disk space):
- `daily_trading_stats`: `UNIQUE (ticker, date)` — 1M+ rows, butuh index build space
- `daily_risk_metrics`: `UNIQUE (ticker, date)` — 8.9M rows, butuh index build space

## Perubahan Kode Python

### File yang Diupdate

| File | Perubahan |
|------|-----------|
| `src/market/db/models.py` | `MarketRegistry` dihapus, `InstrumentMaster` → view alias, `Exchange` + `Instrument` ditambah kolom merge, `Broker`/`BrokerBursa` dihapus, `Broker` baru untuk `brokers` table, `StockPersonality` prediction columns dihapus, `TransaksiInvestor` FK → `brokers.id` |
| `src/market/data/seed.py` | `MarketRegistry` → `Exchange`, tambah `name` field ke `DEFAULT_MARKETS` |
| `src/market/data/ticker_util.py` | `MarketRegistry` → `Exchange` |
| `src/market/api/routes_cosmos.py` | `MarketRegistry` → `Exchange` |
| `tests/test_db.py` | `MarketRegistry` → `Exchange`, `InstrumentMaster` → `Instrument` |
| `tests/test_engine.py` | `MarketRegistry` → `Exchange` |
| `tests/test_seed.py` | `MarketRegistry` → `Exchange` |

### Migration Guide untuk Developer

1. **Pull latest code:** `git pull origin main`
2. **Run migration:** `alembic upgrade head`
3. **Update imports:** Ganti `from market.db.models import MarketRegistry` → `from market.db.models import Exchange`
4. **Update query code:** `session.query(MarketRegistry)` → `session.query(Exchange)`
5. **Raw SQL:** Query ke `market_registry` dan `instrument_master` tetap work via compatibility view, tapi disarankan migrate ke `exchanges`/`instruments`
6. **Prediction columns:** Akses via `stock_prediction` table, bukan `stock_personality`

## Yang Tidak Berubah

- `ohlcv` — sudah berupa VIEW sebelumnya (membaca dari `stock_prices`), tidak diubah
- `events`, `external_events`, `policy_events` — schema berbeda, tidak di-merge
- `news` vs `news_sentiment` — schema berbeda, tidak di-merge

## Migration 0023: Merge market_calendar → exchange_holidays (P3)

**Status:** Completed (2026-08-15, setelah disk space tersedia)

- `market_calendar` (27,305 rows, 7 exchanges) di-merge ke `exchange_holidays` (4,609 → 7,451 rows)
- Holiday names dari `market_calendar` (Bahasa Indonesia) menggantikan "Market Holiday" generic via ON CONFLICT UPDATE
- `market_calendar` table di-drop, compatibility view dibuat (hanya menampilkan holidays)
- ORM `MarketCalendar` diupdate menjadi view alias
- `migrate_parquet.py` diupdate untuk insert ke `exchange_holidays` via raw SQL

## Rollback

```bash
# Rollback ke pre-0023 (restore market_calendar table)
alembic downgrade 0022

# Rollback ke pre-0022 (restore semua tabel lama)
alembic downgrade 0021
```

Rollback 0023 akan:
- Recreate `market_calendar` table
- Migrate holidays dari `exchange_holidays` kembali ke `market_calendar`

Rollback 0022 akan:
- Recreate `broker`, `broker_bursa`, `market_registry`, `instrument_master` tables
- Restore prediction columns di `stock_personality`
- Drop FK dan unique constraints
- Drop kolom merge dari `exchanges` dan `instruments`
