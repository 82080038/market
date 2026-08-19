# 100 — Astronacci: Financial Astrology + Fibonacci Price Confluence

> **Integrasi metodologi Astronacci (Astrology + Fibonacci Price Retracement) sebagai indikator "WHEN + WHERE" — kapan dan di level harga apa reversal berpotensi terjadi — ke dalam database, signal enhancer, dan market context aplikasi swing trading.**

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

### 1.3 Fibonacci Price Retracement

Dari swing high/low signifikan, hitung level retracement harga pada rasio Fibonacci: **23.6%, 38.2%, 50%, 61.8%, 78.6%**. Level 61.8% (golden ratio) adalah level yang paling dimonitor oleh trader institusional (Goldman Sachs, ICT/OTE). Berbeda dengan Fibonacci *time zones* (offset hari), price retracement mengidentifikasi **WHERE** harga berpotensi find support/resistance.

### 1.4 Confluence (Inovasi Utama Astronacci)

Sinyal Astronacci baru **hanya fire** ketika KEDUA kondisi terpenuhi:
1. Event astrologi aktif (dalam time window) → **WHEN**
2. Harga saat ini berada dalam tolerance band (±1.5%) dari level Fibonacci → **WHERE**

Goeyardi (2021): "After obtaining the Astrology factor, it will be checked whether it has been confirmed by Fibonacci."

Tanpa confluence: sinyal astrology-only (lemah, weight ~0.5x)
Dengan confluence: sinyal penuh (WHEN + WHERE aligned, boost 1.5-2x)

### 1.5 Reversal Mapping (Directional)

Moon phases sekarang memiliki directional signal berdasarkan academic evidence:
- **New Moon → BULLISH_REVERSAL** (Yuan et al. 2006: returns ~2x near New Moon)
- **Full Moon → BEARISH_REVERSAL** (Dichev & Janes 2001: lower returns near Full Moon)
- **First/Last Quarter → VOLATILITY** (transitional)

### 1.6 Sumber

- Goeyardi, G. (2021). "Financial analysis method based on astrology, Fibonacci, and Astronacci." *IJEBR* Vol.22 No.2/3.
- Yuan, K., Zheng, L., Zhu, Q. (2006). "Are investors moonstruck?" *J. Empirical Finance* 13(1), 1-23.
- Dichev, I.D., Janes, T.D. (2001). "Lunar cycle effects in stock returns." *Working paper*, Univ. of Michigan.
- Qi, Y., Wang, H., Zhang, B. (2022). "Long Live Hermes! Mercury Retrograde and Equity Prices." *SSRN* 4074620.
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
| `cycle_type` | VARCHAR(50) | MOON_PHASE_NEW, MERCURY_RETROGRADE, SUN_INGRESS, FIBONACCI_PRICE, dll. |
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
| FIBONACCI_PRICE | 5 |
| **Total** | **10,960** |

---

## 3. Implementasi Kode

### 3.1 Module: `src/market/analysis/astronacci.py`

Library: `ephem` (PyEphem) untuk komputasi astronomi.

**Class diagram:**
- `MoonPhaseCalculator` — komputasi 4 fase bulan via `ephem.next_new_moon`, `next_full_moon`, dll.
- `RetrogradeCalculator` — deteksi retrograde dengan scan geocentric ecliptic longitude harian (8 planet)
- `IngressCalculator` — deteksi ingress (Sun + 8 planet) dengan zodiac sign change detection
- `FibonacciPriceRetracementCalculator` — swing high/low detection + Fibonacci price retracement levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) + confluence check
- `AstronacciEngine` — orchestrator semua calculator dengan confluence logic
- `compute_astronacci_signal()` — convenience function untuk SignalEnhancer (menerima `current_price` untuk confluence)

**Signal output (dengan confluence):**
```python
{
    "active_cycles": ["MOON_PHASE_NEW", "FIBONACCI_PRICE"],
    "time_signal": 0.25,      # [-1, 1] directional (boosted by confluence)
    "volatility_signal": 0.45, # [0, 1] expected volatility
    "confidence": 0.72,        # [0, 1] (confluence adds +0.3)
    "cycle_count": 2,
    "confluence": {            # None if no confluence
        "matched": True,
        "ratio": 0.618,
        "fib_price": 8385.70,
        "current_price": 8385.70,
        "distance_pct": 0.0,
        "direction": "BULLISH",
        "swing_high": 9134.70,
        "swing_low": 5342.14,
    }
}
```

**Confluence boost logic:**
- Astrology + Fibonacci aligned: **2x** signal boost
- Astrology + Fibonacci conflicting: Fibonacci overrides direction, **1.3x** boost
- Fibonacci only (no astrology): weak standalone signal (**0.15**)
- 61.8% golden ratio: extra **1.2x** multiplier
- 78.6% OTE deep zone: extra **1.1x** multiplier

### 3.2 SignalEnhancer Integration

`src/market/analysis/signal_enhancer.py` — Astronacci sebagai signal ke-8:

- **Weight:** 0.06 (6% dari total adjustment)
- **Method:** `_compute_astronacci_signal(as_of, df)` — compute active cycles + Fibonacci confluence dalam 3-day forward window
- **Current price:** otomatis diambil dari `df["close"].iloc[-1]` untuk confluence check
- **Signal mapping:** `time_signal` → directional adjustment (boosted 1.5-2x jika confluence), `volatility_signal` → confidence adjustment
- **Confluence confidence:** +0.10 extra confidence adjustment saat confluence terdeteksi
- **Graceful degradation:** jika ephem tidak terinstall atau tidak ada active cycles + no confluence, signal skipped

### 3.3 MarketContext Integration

`src/market/analysis/market_context.py` — Astronacci sebagai faktor konteks:

- **Fields:** `astronacci_signal`, `astronacci_volatility`, `astronacci_active_cycles`
- **Weight in composite_signal:** 3% base, 4% untuk Communication Services
- **Method:** `_fetch_astronacci(ctx, as_of, df)` — compute signal + confluence saat `get_context()` dipanggil
- **Current price:** otomatis diambil dari `df["close"].iloc[-1]` untuk confluence check

### 3.4 API Routes

`src/market/api/routes_cosmos.py` — endpoint `/cosmos/astronacci`:
- Menghitung posisi planet, fase bulan, siklus aktif, dan sinyal Astronacci
- Menggunakan harga ^JKSE terbaru dari DB untuk Fibonacci retracement + confluence
- Output: bodies, active_cycles, signal (dengan confluence field)

### 3.5 Scheduler Task

`src/market/scheduler_tasks.py` — task `compute_astronacci_cycles`:
- **Schedule:** weekly (Sabtu 14:00 WIB)
- Compute semua cycles (Moon, Retrograde, Ingress, Fibonacci price retracement) untuk 90 hari ke depan
- Persist ke `astronacci_cycles` table
- Menggunakan harga ^JKSE dari DB untuk Fibonacci retracement levels

### 3.6 Backfill Script

`scripts/backfill_astronacci.py`:
- Auto-detect date range dari `stock_prices` min/max
- Compute semua cycles (Moon, Retrograde, Ingress, Fibonacci)
- Bulk insert via `psycopg2.extras.execute_values`
- Idempotent (TRUNCATE + INSERT)
- Flag `--fibonacci` untuk include Fibonacci retracement dari IHSG swing points
- Flag `--dry-run` untuk preview

---

## 4. Testing

`tests/test_astronacci.py` — 31 tests:

- **TestMoonPhaseCalculator** (7): New Moon, Full Moon, 4 phases, impact/reversal (BULLISH/BEARISH), window duration, empty range, sorted
- **TestRetrogradeCalculator** (4): Mercury retrograde 2025, all 8 planets, window duration, sorted
- **TestIngressCalculator** (4): Sun monthly, Aries ingress, Jupiter rare, sorted
- **TestFibonacciPriceRetracementCalculator** (7): swing points, retracement levels, levels within range, confluence match, confluence no-match, visualization cycles, empty prices
- **TestAstronacciEngine** (4): all cycles, sorted, with Fibonacci price, empty range
- **TestAstronacciSignal** (8): New Moon signal, no cycles, range validation, Mercury retrograde, Fibonacci prices, confluence match, no confluence without price, confidence quality
- **TestHelperFunctions** (3): zodiac sign, ecliptic longitude, longitude range
- **TestAstronacciCycle** (2): to_dict, defaults

---

## 5. Cross-Reference

- Schema DDL: `docs/domino_effect_schema.sql:698-731`
- View integration: `docs/domino_effect_schema.sql:443-464`
- Migration: `alembic/versions/0018_add_astronacci_cycles.py`
- Module: `src/market/analysis/astronacci.py`
- API Routes: `src/market/api/routes_cosmos.py` (endpoint /cosmos/astronacci)
- Scheduler: `src/market/scheduler_tasks.py` (task compute_astronacci_cycles)
- Backfill: `scripts/backfill_astronacci.py`
- Tests: `tests/test_astronacci.py`
- SignalEnhancer: `src/market/analysis/signal_enhancer.py` (signal ke-8)
- MarketContext: `src/market/analysis/market_context.py` (faktor astronacci)
- Integration report: `docs/ASTRONACCI-INTEGRATION-REPORT.md`
- Pendahulu: `pustaka/97-strategi-alternatif-ekspansi-data-2026.md` (7 modul signal enhancer)
- Database: `pustaka/98-migrasi-sqlite-ke-postgresql.md` (v_domino_timeline)

---

## 6. Catatan & Limitasi

1. **Astronacci dengan confluence adalah indikator WHEN + WHERE.** Astrology mengidentifikasi KAPAN, Fibonacci price retracement mengidentifikasi DI MANA. Confluence (keduanya aligned) menghasilkan sinyal high-probability. Tanpa confluence, sinyal astrology-only lebih lemah.
2. **Reversal mapping directional:** Moon phases sekarang memiliki arah (New Moon → BULLISH, Full Moon → BEARISH) berdasarkan academic evidence (Yuan et al. 2006, Dichev & Janes 2001).
3. **Fibonacci price retracement** menggunakan swing high/low terakhir dari ^JKSE (300 bar lookback). Level 61.8% (golden ratio) mendapat extra weight karena paling dimonitor institusional.
4. **Tolerance band ±1.5%** untuk confluence check. Institutional algorithms cluster within ~1% dari exact level.
5. **Komputasi retrograde/ingress** menggunakan scan harian geocentric ecliptic longitude. Presisi ±1 hari.
6. **ephem (PyEphem)** menggunakan model VSOP87/ELP2000 dengan akurasi ~1 arcsecond untuk planet.
7. **Weight rendah (3-6%)** adalah intentional — Astronacci adalah faktor pelengkap, bukan driver utama. Signal enhancer tetap mengandalkan ML, volume, dan event sebagai signal primer. Namun confluence boost (1.5-2x) dapat meningkatkan kontribusi signifikan saat kedua faktor aligned.
8. **Database truncation:** Tabel `astronacci_cycles` di-truncate saat refactor untuk menghapus data Fibonacci time zones yang lama. Data baru menggunakan `FIBONACCI_PRICE` cycle type.
