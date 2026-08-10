# 100 — Astronacci: Financial Astrology & Time Cycle Integration

> **Integrasi metodologi Astronacci (Astrology + Fibonacci) sebagai indikator "WHEN" — kapan harga berpotensi berbalik arah — ke dalam database, signal enhancer, dan market context aplikasi swing trading.**

---

## 1. Latar Belakang & Metodologi

### 1.1 Apa itu Astronacci?

Astronacci adalah metodologi trading yang menggabungkan **Astrology** (sebagai referensi waktu) dan **Fibonacci** (sebagai validasi struktur harga). Dikembangkan oleh **Gema Goeyardi** / Astronacci International.

**Framework:**
- **Astrology = Time reference (WHEN)** — kapan market berpotensi berbalik arah
- **Fibonacci = Structure validation (WHERE)** — di level harga apa reversal terjadi
- **Price action = Final confirmation** — konfirmasi dari pergerakan harga aktual

### 1.2 Tiga Elemen Astrologi Utama

1. **Moon Phase** — New Moon, First Quarter, Full Moon, Last Quarter
   - Indikator pergeseran psikologi/sensitivitas market
   - Riset Goeyardi (2026): ~78-79% reversal probability saat New Moon dan Full Moon
   - Siklus sinodik: 29.53 hari (New Moon ke New Moon)

2. **Planetary Retrograde** — Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto
   - Momentum trend melambat, false breakout meningkat
   - Market memasuki mode evaluasi, bukan mode ekspansi
   - Mercury Retrograde paling terkenal: ~3-4x per tahun, ~3 minggu per episode

3. **Planetary Ingress** — Planet masuk ke zodiac sign baru
   - Reset karakter market, fase siklus baru
   - Sun ingress (monthly) paling signifikan untuk siklus jangka pendek
   - Jupiter/Saturn ingress untuk siklus tahunan/dekade

### 1.3 Fibonacci Time Windows

Dari swing high/low signifikan, proyeksikan Fibonacci sequence (1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233...) sebagai offset hari ke depan. Titik temu Fibonacci time ratio = potensi reversal zone.

### 1.4 Sumber

- Goeyardi, G. (2021). "Financial analysis method based on astrology, Fibonacci, and Astronacci." *IJEBR* Vol.22 No.2/3.
- astronacci.com/blog/read/astrologi-trading-time-trigger-market-cycle
- financialadviser.ph (March 2026 STA Philippines summit coverage)

---

## 2. Implementasi Database

### 2.1 Tabel `astronacci_cycles`

Lihat DDL: `docs/domino_effect_schema.sql:698-731`, migration: `alembic/versions/0018_add_astronacci_cycles.py`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | BIGSERIAL PK | Auto-increment |
| `cycle_uuid` | UUID | Default `gen_random_uuid()` |
| `cycle_type` | VARCHAR(50) | MOON_PHASE_NEW, MERCURY_RETROGRADE, SUN_INGRESS, FIBONACCI_TIME, dll. |
| `title` | VARCHAR(200) | "New Moon", "Mercury Retrograde", "Sun Ingress → ARIES" |
| `start_at` | TIMESTAMPTZ | Mulai siklus (UTC) |
| `end_at` | TIMESTAMPTZ | Akhir siklus (UTC) |
| `potential_impact` | VARCHAR(20) | CRITICAL, HIGH, MEDIUM, LOW |
| `target_asset_class` | VARCHAR(50) | ALL, EQUITY, COMMODITY, FX |
| `expected_reversal` | VARCHAR(20) | BULLISH_REVERSAL, BEARISH_REVERSAL, VOLATILITY, NEUTRAL |
| `description` | TEXT | Penjelasan siklus |
| `created_at` | TIMESTAMPTZ | Default NOW() |

### 2.2 Integrasi `v_domino_timeline`

Tabel `astronacci_cycles` di-UNION ALL ke view `v_domino_timeline` sebagai `event_type = 'ASTRONACCI_CYCLE'`. Lihat `docs/domino_effect_schema.sql:443-464`.

### 2.3 Backfill Data

Script: `scripts/backfill_astronacci.py`

**Hasil backfill (1927–2026, 98.6 tahun):**

| Cycle Type | Count |
|------------|-------|
| MOON_PHASE_NEW | 1,219 |
| MOON_PHASE_FULL | 1,220 |
| MOON_PHASE_FIRST_QUARTER | 1,220 |
| MOON_PHASE_LAST_QUARTER | 1,220 |
| MERCURY_RETROGRADE | 426 |
| VENUS_RETROGRADE | 170 |
| MARS_RETROGRADE | 101 |
| JUPITER_RETROGRADE | 101 |
| SATURN_RETROGRADE | 104 |
| URANUS_RETROGRADE | 100 |
| NEPTUNE_RETROGRADE | 102 |
| PLUTO_RETROGRADE | 99 |
| SUN_INGRESS | 1,183 |
| MERCURY_INGRESS | 1,429 |
| VENUS_INGRESS | 1,251 |
| MARS_INGRESS | 682 |
| JUPITER_INGRESS | 161 |
| SATURN_INGRESS | 82 |
| URANUS_INGRESS | 39 |
| NEPTUNE_INGRESS | 25 |
| PLUTO_INGRESS | 21 |
| FIBONACCI_TIME | 3,118 |
| **Total** | **14,073** |

---

## 3. Implementasi Kode

### 3.1 Module: `src/market/analysis/astronacci.py`

Library: `ephem` (PyEphem) untuk komputasi astronomi.

**Class diagram:**
- `MoonPhaseCalculator` — komputasi 4 fase bulan via `ephem.next_new_moon`, `next_full_moon`, dll.
- `RetrogradeCalculator` — deteksi retrograde dengan scan geocentric ecliptic longitude harian (8 planet)
- `IngressCalculator` — deteksi ingress (Sun + 8 planet) dengan zodiac sign change detection
- `FibonacciTimeCalculator` — swing high/low detection + Fibonacci sequence projection
- `AstronacciEngine` — orchestrator semua calculator
- `compute_astronacci_signal()` — convenience function untuk SignalEnhancer

**Signal output:**
```python
{
    "active_cycles": ["MOON_PHASE_NEW", "MERCURY_RETROGRADE"],
    "time_signal": -0.15,      # [-1, 1] directional
    "volatility_signal": 0.45,  # [0, 1] expected volatility
    "confidence": 0.4,          # [0, 1]
    "cycle_count": 2
}
```

### 3.2 SignalEnhancer Integration

`src/market/analysis/signal_enhancer.py` — Astronacci sebagai signal ke-8:

- **Weight:** 0.06 (6% dari total adjustment)
- **Method:** `_compute_astronacci_signal(as_of)` — compute active cycles dalam 3-day forward window
- **Signal mapping:** `time_signal` → directional adjustment, `volatility_signal` → confidence adjustment
- **Graceful degradation:** jika ephem tidak terinstall atau tidak ada active cycles, signal skipped

### 3.3 MarketContext Integration

`src/market/analysis/market_context.py` — Astronacci sebagai faktor konteks:

- **Fields:** `astronacci_signal`, `astronacci_volatility`, `astronacci_active_cycles`
- **Weight in composite_signal:** 3% base, 4% untuk Communication Services
- **Method:** `_fetch_astronacci(ctx, as_of)` — compute signal saat `get_context()` dipanggil

### 3.4 Backfill Script

`scripts/backfill_astronacci.py`:
- Auto-detect date range dari `stock_prices` min/max
- Compute semua cycles (Moon, Retrograde, Ingress, Fibonacci)
- Bulk insert via `psycopg2.extras.execute_values`
- Idempotent (TRUNCATE + INSERT)
- Flag `--fibonacci` untuk include Fibonacci time windows dari IHSG swing points
- Flag `--dry-run` untuk preview

---

## 4. Testing

`tests/test_astronacci.py` — 32 tests:

- **TestMoonPhaseCalculator** (7): New Moon, Full Moon, 4 phases, impact/reversal, window duration, empty range, sorted
- **TestRetrogradeCalculator** (4): Mercury retrograde 2025, all 8 planets, window duration, sorted
- **TestIngressCalculator** (4): Sun monthly, Aries ingress, Jupiter rare, sorted
- **TestFibonacciTimeCalculator** (4): swing points, windows computed, 24h duration, empty prices
- **TestAstronacciEngine** (4): all cycles, sorted, with Fibonacci, empty range
- **TestAstronacciSignal** (4): New Moon signal, no cycles, range validation, Mercury retrograde
- **TestHelperFunctions** (3): zodiac sign, ecliptic longitude, longitude range
- **TestAstronacciCycle** (2): to_dict, defaults

---

## 5. Cross-Reference

- Schema DDL: `docs/domino_effect_schema.sql:698-731`
- View integration: `docs/domino_effect_schema.sql:443-464`
- Migration: `alembic/versions/0018_add_astronacci_cycles.py`
- Module: `src/market/analysis/astronacci.py`
- Backfill: `scripts/backfill_astronacci.py`
- Tests: `tests/test_astronacci.py`
- SignalEnhancer: `src/market/analysis/signal_enhancer.py` (signal ke-8)
- MarketContext: `src/market/analysis/market_context.py` (faktor astronacci)
- Integration report: `docs/ASTRONACCI-INTEGRATION-REPORT.md`
- Pendahulu: `pustaka/97-strategi-alternatif-ekspansi-data-2026.md` (7 modul signal enhancer)
- Database: `pustaka/98-migrasi-sqlite-ke-postgresql.md` (v_domino_timeline)

---

## 6. Catatan & Limitasi

1. **Astronacci adalah indikator waktu, BUKAN prediksi arah.** Ia mengidentifikasi KAPAN market berpotensi berbalik, bukan KE ARAH MANA. Directional signal hanya kontribusi kecil (weight 3-6%) dalam composite.
2. **Komputasi retrograde/ingress menggunakan scan harian** geocentric ecliptic longitude. Presisi adalah ±1 hari. Untuk presisi lebih tinggi, diperlukan scan per-jam.
3. **Fibonacci time windows** memerlukan price data (IHSG) dan hanya cover 1990–2026 (data IHSG tersedia). Cycle astronomi cover 1927–2026.
4. **ephem (PyEphem)** menggunakan model VSOP87/ELP2000 dengan akurasi ~1 arcsecond untuk planet, lebih dari cukup untuk purpose ini.
5. **Weight rendah (3-6%)** adalah intentional — Astronacci adalah faktor pelengkap, bukan driver utama. Signal enhancer tetap mengandalkan ML, volume, dan event sebagai signal primer.
