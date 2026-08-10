# Laporan Validasi Kualitas Data Pasca-Migrasi PostgreSQL

> **Tanggal:** 10 Agustus 2026 20:45 WIB
> **DBA:** Cascade AI (atas instruksi user)
> **Database:** `postgresql://petrick@localhost:5432/market`
> **Status: ✅ AMAN**

---

## 1. Rekonsiliasi Jumlah Data

### Hasil

| Metrik | Nilai | Status |
|--------|-------|--------|
| Parent table `stock_prices` | 3,217,159 rows | ✅ |
| Sum semua partisi | 3,217,159 rows | ✅ Cocok |
| Jumlah partisi | 19 (18 bulanan + 1 default) | ✅ |
| Data di `stock_prices_default` | 2,954,456 rows (pre-2025-07) | ✅ Wajar |
| Data bocor ke default (post-2025-07) | 0 rows | ✅ Aman |

### Catatan
- 18 partisi bulanan dibuat untuk range 2025-07 s/d 2026-12.
- Partisi `stock_prices_default` (458 MB) menampung data historis 1927-12-30 s/d 2025-06-30. Ini wajar karena partisi bulanan baru dibuat mulai Juli 2025. Untuk optimasi, partisi bulanan dapat dibuat retroaktif untuk periode sebelumnya.
- 4 partisi kosong (2026-09 s/d 2026-12) — pre-created untuk data mendatang.

---

## 2. Integritas Zona Waktu

### 5 Baris Tertua

| Ticker | UTC Time | WIB (Asia/Jakarta) | Close |
|--------|----------|---------------------|-------|
| ^GSPC | 1927-12-30 00:00:00 | 1927-12-30 07:20:00 | 17.66 |
| ^GSPC | 1928-01-03 00:00:00 | 1928-01-03 07:20:00 | 17.76 |
| ^GSPC | 1928-01-04 00:00:00 | 1928-01-04 07:20:00 | 17.72 |
| ^GSPC | 1928-01-05 00:00:00 | 1928-01-05 07:20:00 | 17.55 |
| ^GSPC | 1928-01-06 00:00:00 | 1928-01-06 07:20:00 | 17.66 |

### 5 Baris Terbaru

| Ticker | UTC Time | WIB (Asia/Jakarta) | Close |
|--------|----------|---------------------|-------|
| GC=F | 2026-08-07 00:00:00 | 2026-08-07 07:00:00 | 4340.70 |
| HG=F | 2026-08-07 00:00:00 | 2026-08-07 07:00:00 | 6.57 |
| CL=F | 2026-08-07 00:00:00 | 2026-08-07 07:00:00 | 78.18 |
| CPO=F | 2026-08-07 00:00:00 | 2026-08-07 07:00:00 | 1150.00 |
| 000001.SS | 2026-08-07 00:00:00 | 2026-08-07 07:00:00 | 3940.04 |

### Perbandingan dengan SQLite

| Ticker | SQLite timestamp | PostgreSQL UTC | PostgreSQL WIB | Match? |
|--------|-----------------|----------------|----------------|--------|
| BBCA.JK | 2026-08-06 00:00:00 | 2026-08-06 00:00:00 | 2026-08-06 07:00:00 | ✅ |
| ^GSPC | 1927-12-30 00:00:00 | 1927-12-30 00:00:00 | 1927-12-30 07:20:00 | ✅ |

### Catatan
- Offset `+07:20` pada data 1927 adalah **historical LMT** (Local Mean Time) Jakarta sebelum standardisasi ke UTC+7. PostgreSQL secara akurat menangani offset historis ini dari database timezone IANA.
- Untuk data modern (2020+), offset konsisten `+07:00` (WIB).
- Konversi `AT TIME ZONE 'Asia/Jakarta'` menghasilkan tanggal dan jam yang konsisten dengan data asli SQLite (EOD data, timestamp = midnight UTC).

---

## 3. Pengujian View `v_domino_timeline`

### 3a. Fungsi Window `gap_from_previous` (LAG)

| Metrik | Nilai | Status |
|--------|-------|--------|
| Total rows diuji (5 hari) | 6,298 | ✅ |
| Non-NULL gaps | 6,297 | ✅ |
| NULL gaps (baris pertama, expected) | 1 | ✅ |
| Unexpected NULLs | 0 | ✅ |

**Sample output:**
```
utc_timestamp      | event_type  | gap_from_previous | seconds_gap
2025-07-15 07:00   | PRICE_TICK  | NULL              | (first row)
2025-07-15 07:00   | PRICE_TICK  | 00:00:00          | 0
2025-07-16 07:00   | PRICE_TICK  | 24:00:00          | 86400
2025-07-16 15:00   | BROKER_TRADE| 08:00:00          | 28800
```

### 3b. Logika `causal_role`

| Metrik | Nilai | Status |
|--------|-------|--------|
| Total rows diuji | 6,298 | ✅ |
| NULL causal_role | 0 | ✅ |

**Distribusi causal_role (BBCA.JK, 15-18 Jul 2025):**
- **EFFECT**: PRICE_TICK dengan impact_direction BULLISH/BEARISH
- **REACTOR**: BROKER_TRADE (BUY/SELL)
- **NEUTRAL**: PRICE_TICK dengan impact_direction NEUTRAL
- **CONTEXT**: MARKET_OPEN / MARKET_CLOSE

### 3c. Distribusi Event Types di View

| Event Type | Count |
|------------|-------|
| PRICE_TICK | 3,217,159 |
| BROKER_TRADE | 345,104 |
| MARKET_OPEN | 8,307 |
| MARKET_CLOSE | 8,307 |
| CORPORATE_ACTION | 5,974 |
| EVENT | 298 |

---

## 4. Deteksi Anomali & Cleanup

### 4a. Duplikat (ticker + timestamp)

| Fase | Duplikat Groups | Extra Rows | Status |
|------|----------------|------------|--------|
| Sebelum cleanup | 2,315 | 2,315 | ⚠️ Ditemukan |
| Setelah hapus parquet_archive dupes | 9 | 9 | ⚠️ Sisa |
| Setelah hapus yahoo_finance dupes | 0 | 0 | ✅ Bersih |

**Root cause:** Data komoditas (GC=F, CL=F, CPO=F) dan XCID.JK masuk dari multiple sources (parquet_archive, yfinance, yahoo_finance) dengan nilai OHLCV identik.

**Aksi cleanup:**
- `DELETE FROM stock_prices WHERE source='parquet_archive' AND (duplikat dengan source lain)` → 2,306 rows dihapus
- `DELETE FROM stock_prices WHERE source='yahoo_finance' AND (duplikat dengan 'yfinance')` → 9 rows dihapus
- **Total dihapus: 2,315 rows**

### 4b. Harga NULL

| Kolom | NULL Count | Status |
|-------|-----------|--------|
| open | 0 | ✅ |
| high | 0 | ✅ |
| low | 0 | ✅ |
| close | 0 | ✅ |
| volume | 0 | ✅ |

### 4c. Harga Nol / Negatif

| Anomali | Sebelum Cleanup | Setelah Cleanup | Status |
|---------|----------------|----------------|--------|
| open = 0 | 0 | 0 | ✅ |
| high = 0 | 50,897 | 0 | ✅ Fixed |
| low = 0 | 50,897 | 0 | ✅ Fixed |
| close = 0 | 0 | 0 | ✅ |
| open < 0 | 0 | 0 | ✅ |
| high < 0 | 0 | 0 | ✅ |
| low < 0 | 0 | 0 | ✅ |
| close < 0 | 0 | 0 | ✅ |
| volume < 0 | 0 | 0 | ✅ |

**Root cause high=0 & low=0:** 50,897 rows dari source `github_dataset_saham_idx` berisi close-only data (open=close, high=0, low=0, volume=0) untuk 37 tickers illiquid IDX (KBRI.JK, GOLL.JK, SUGI.JK, dll).

**Aksi cleanup:**
- `UPDATE stock_prices SET high = close, low = close WHERE high = 0 AND low = 0 AND close > 0` → 50,897 rows diperbaiki
- High dan low diset sama dengan close (karena hanya close price yang tersedia dari source ini)

---

## 5. Ringkasan Final

| Aspek Validasi | Status | Detail |
|---------------|--------|--------|
| **1. Rekonsiliasi jumlah** | ✅ AMAN | Parent = sum partisi = 3,217,159 |
| **2. Integritas zona waktu** | ✅ AMAN | UTC → WIB konversi konsisten dengan SQLite |
| **3. View v_domino_timeline** | ✅ AMAN | LAG + causal_role berjalan, 0 NULL tak terduga |
| **4a. Duplikat** | ✅ AMAN | 2,315 duplikat dihapus, 0 tersisa |
| **4b. NULL prices** | ✅ AMAN | 0 NULL di semua kolom OHLCV |
| **4c. Zero/negative prices** | ✅ AMAN | 50,897 high=low=0 diperbaiki, 0 tersisa |

### Data Final Setelah Cleanup

| Metrik | Nilai |
|--------|-------|
| Total `stock_prices` | 3,217,159 rows |
| Total `broker_transactions` | 345,104 rows |
| Total partisi | 19 (18 bulanan + 1 default) |
| Duplikat | 0 |
| NULL prices | 0 |
| Zero/negative prices | 0 |
| Rows dihapus (duplikat) | 2,315 |
| Rows diperbaiki (high/low=0) | 50,897 |

### Rekomendasi

1. **Partisi retroaktif:** Buat partisi bulanan untuk periode pre-2025-07 untuk mengosongkan `stock_prices_default` (opsional, untuk performance).
2. **Unique constraint:** Tambah `UNIQUE(ticker, timestamp, timeframe)` setelah cleanup untuk mencegah duplikat di masa depan.
3. **Source priority rule:** Implementasikan logic di migration script untuk otomatis memilih source prioritas (yfinance > parquet_archive) saat ada konflik.

---

> **Verdict: DATA DALAM KONDISI AMAN** ✅
> Semua 4 aspek validasi lulus. Data duplikat dan cacat telah dibersihkan dan diverifikasi ulang.
