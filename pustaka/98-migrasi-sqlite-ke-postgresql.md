# Migrasi SQLite → PostgreSQL (Domino Effect Schema)

> **Dokumen ini mendokumentasikan migrasi database dari SQLite ke PostgreSQL dengan schema "Domino Effect" untuk analisis kausal real-time.**

---

## 1. Latar Belakang

Database SQLite `market_research.db` (~6 GB) telah melayani aplikasi sejak awal pengembangan. Untuk mendukung:

- **Analisis kausal real-time** (event → price reaction timeline)
- **Time-range queries** yang efisien (GiST indexes)
- **Partitioning** untuk data besar (3.2M+ rows OHLCV)
- **JSONB** untuk metadata event yang fleksibel
- **TIMESTAMPTZ** untuk universal UTC timeline ordering

maka dilakukan migrasi ke PostgreSQL 16.

---

## 2. Arsitektur Schema

### 2.1 Tabel Inti

| Tabel | Deskripsi | Key Features |
|-------|-----------|-------------|
| `exchanges` | Bursa (XIDX, XNYS, XNAS, dll) | Multi-timezone, IANA tz |
| `instruments` | Saham/indeks/ETF | FK ke exchanges, JSONB metadata |
| `brokers` | Broker pialang | — |
| `market_sessions` | Sesi perdagangan per bursa | TIMESTAMPTZ, GiST range index |
| `events` | Berita makro, kebijakan | JSONB metadata, impact scoring |
| `corporate_actions` | Dividen, split, rights issue | JSONB details |
| `stock_prices` | OHLCV | Partitioned by month, TIMESTAMPTZ |
| `broker_transactions` | Transaksi per broker per ticker | FK ke brokers + instruments |

### 2.2 View: `v_domino_timeline`

View unified yang menggabungkan semua event types dalam satu garis waktu UTC:

```sql
SELECT utc_timestamp, event_type, category, title, impact_level, impact_direction, source
FROM v_domino_timeline
WHERE utc_timestamp >= '2025-07-01T00:00:00+00:00'
ORDER BY utc_timestamp;
```

Event types: `MARKET_OPEN`, `MARKET_CLOSE`, `EVENT`, `CORPORATE_ACTION`, `PRICE_TICK`, `BROKER_TRADE`.

### 2.3 Function: `create_stock_price_partition(year, month)`

Utility function untuk membuat partisi bulanan `stock_prices_YYYY_MM` secara otomatis.

---

## 3. Data Migrated

| Tabel PostgreSQL | Rows | Sumber SQLite |
|-----------------|------|--------------|
| `stock_prices` | 3,219,474 | `ohlcv` (1927–2026, full history) |
| `market_sessions` | 8,307 | Generated dari `market_registry.trading_hours` |
| `corporate_actions` | 5,974 | `dividends` |
| `instruments` | 1,056 | `instrument_master` |
| `events` | 298 | `policy_events` (179) + `external_events` (119) |
| `brokers` | 20 | `broker` |
| `exchanges` | 12 | `market_registry` (11) + `OFF` catch-all |
| `broker_transactions` | ~400K | Rendered dari OHLCV volume + broker list |

### 3.1 Backfill `broker_transactions`

SQLite `broker_flow` hanya berisi data aggregate `__MARKET__` (per broker per hari, tanpa ticker). Strategi backfill:

1. Ambil top 50 ticker paling aktif per hari (by volume)
2. Distribusi volume ke 5-8 broker (deterministic seeded random)
3. Split BUY/SELL berdasarkan daily price movement (up day → 60-70% buy)
4. Top 5 broker ditandai sebagai foreign (`is_foreign=TRUE`)

Script: `scripts/backfill_broker_transactions.py`

---

## 4. Multi-DB Support di Kode Aplikasi

### 4.1 Config (`src/market/config.py`)

```python
class Settings(BaseSettings):
    db_path: str | None = None          # SQLite path
    database_url: str | None = None     # PostgreSQL URL

    @property
    def db_backend(self) -> str:
        return "postgresql" if self.database_url else "sqlite"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.resolved_db_path}"
```

### 4.2 Engine (`src/market/db/engine.py`)

Auto-select SQLite atau PostgreSQL engine berdasarkan `settings.db_backend`.

### 4.3 Raw Connection (`src/market/db/raw.py`)

```python
from market.db.raw import get_raw_connection, execute_query

# Auto-converts ? → %s for PostgreSQL
rows = execute_query(
    "SELECT * FROM ohlcv WHERE ticker=? AND date>=?",
    (ticker, cutoff_date),
)
```

### 4.4 Cara Switch

Set di `.env`:
```
DATABASE_URL=postgresql://petrick:market_dev@localhost:5432/market
```

Tanpa `DATABASE_URL`, aplikasi otomatis fallback ke SQLite.

---

## 5. File Relevan

- **Schema DDL:** `docs/domino_effect_schema.sql`
- **Migration script:** `scripts/migrate_sqlite_to_pg.py`
- **Backfill script:** `scripts/backfill_broker_transactions.py`
- **Raw DB helper:** `src/market/db/raw.py`
- **Config:** `src/market/config.py` (`database_url`, `db_backend`, `resolved_database_url`)
- **Engine:** `src/market/db/engine.py` (`_make_sqlite_engine`, `_make_postgresql_engine`)
- **Alembic env:** `alembic/env.py`

---

## 6. Connection Details

- **PostgreSQL 16** di localhost:5432
- **User:** `petrick`
- **Database:** `market`
- **Connection string:** `postgresql://petrick:market_dev@localhost:5432/market`

---

## 7. Catatan

- Scripts (`daily_signal_cron.py`, `data_health.py`, dll) masih menggunakan `sqlite3.connect` — refactoring bertahap diperlukan.
- Alembic migrations (0001-0014) ditulis untuk SQLite; perlu di-generate ulang untuk PostgreSQL schema.
- `stock_prices` menggunakan partitioning by month — pastikan partisi dibuat sebelum insert data di luar range existing.
- View `v_domino_timeline` menggabungkan 6 event types dalam satu timeline UTC untuk analisis domino effect.

---

> Dibuat: 10 Agustus 2026 | Sumber: Migrasi real data SQLite 6GB → PostgreSQL 16
