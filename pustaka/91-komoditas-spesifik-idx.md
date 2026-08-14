# Komoditas Spesifik IDX: Dari Harga Komoditas ke Keputusan Saham

> **Dokumen 91** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Tujuan:** Dokumen khusus yang membahas hubungan antara harga komoditas dan saham emiten di Bursa Efek Indonesia (IDX). IDX adalah exchange yang sangat commodity-dependent — sektor energi & material mencakup ~35% market cap. Dokumen ini mengisi gap terbesar dari dokumen 89 (faktor pasar modal) dan memberikan roadmap implementasi menggunakan data komoditas yang sudah ada di parquet (`raw/commodity/`).
>
> **Konteks:** Data komoditas 1,523 rows (2018-2026) sudah tersedia di `/media/petrick/Parquet/trading_data/raw/commodity/` dengan 10 jenis komoditas: CPO, batubara, nikel, tembaga, emas, perak, timah, aluminium, gas, crude oil. Lihat `90-analisis-parquet-data-awal.md` untuk detail.

---

## Daftar Isi

1. [Mengapa Komoditas Penting untuk IDX](#1-mengapa-komoditas-penting-untuk-idx)
2. [Mapping Komoditas ke Emiten IDX](#2-mapping-komoditas-ke-emiten-idx)
3. [CPO (Crude Palm Oil)](#3-cpo-crude-palm-oil)
4. [Batubara (Coal)](#4-batubara-coal)
5. [Nikel](#5-nikel)
6. [Tembaga (Copper)](#6-tembaga-copper)
7. [Emas (Gold)](#7-emas-gold)
8. [Komoditas Lain](#8-komoditas-lain)
9. [Cara Menggunakan Data Komoditas](#9-cara-menggunakan-data-komoditas)
10. [Implementasi di Trading-System](#10-implementasi-di-trading-system)
11. [Data Source dan Update](#11-data-source-dan-update)

---

## 1. Mengapa Komoditas Penting untuk IDX

### 1.1 Struktur IDX

IDX unik dibandingkan bursa regional (SGX, SET, KLSE) karena **sangat commodity-dependent**:

| Sektor | Bobot IHSG | Komoditas Driver | Emiten Kunci |
|--------|-----------|------------------|--------------|
| Energi | ~18% | Batubara, crude oil | ADRO, PTBA, ITMG, MEDC |
| Material | ~12% | CPO, nikel, tembaga, emas | AALI, INCO, ANTM, MDKA |
| Konsumer Primer | ~8% | CPO (sawit), kelapa sawit | LSIP, SIMP, DSNG |
| Keuangan | ~25% | (tidak langsung — bank lending ke commodity) | BBCA, BBRI, BMRI |
| Lainnya | ~37% | — | — |

**Total sektor yang langsung dipengaruhi komoditas: ~35-40% market cap IDX**

### 1.2 Mekanisme Transmisi

```
HARGA KOMODITAS NAIK
│
├── Revenue emiten produsen naik (price × volume)
│   └── Laba bersih naik → EPS naik → harga saham naik
│
├── Margin mungkin berubah (cost structure matters)
│   ├── Cost naik < revenue naik → margin expand → bullish
│   └── Cost naik > revenue naik → margin compress → bearish
│
├── Valuation re-rating (PER naik karena earnings growth)
│
└── Sentimen investor asing (commodity funds flow)

HARGA KOMODITAS TURUN
│
├── Revenue emiten produsen turun
│   └── Laba turun → EPS turun → harga saham turun
│
├── Emiten konsumer/pengguna komoditas: cost turun → margin naik
│   └── Contoh: harga CPO turun → produsen makanan (INDF, ICBP) margin naik
│
└── Risk-off untuk commodity-heavy portfolio
```

### 1.3 Time Lag

| Komoditas | Lag ke Saham | Catatan |
|-----------|-------------|---------|
| CPO | 1-3 hari | CPO futures di Bursa Malaysia, saham sawit reaksi cepat |
| Batubara | 1-5 hari | Newcastle index weekly, saham coal reaksi dalam seminggu |
| Nikel | 1-3 hari | LME nickel 3M daily, INCO/ANTM reaksi cepat |
| Tembaga | 1-3 hari | LME copper 3M daily |
| Emas | 0-2 hari | Gold futures real-time, ANTM gold division reaksi cepat |
| Crude oil | 1-3 hari | WTI/Brent daily, MEDC/ENRG reaksi |

---

## 2. Mapping Komoditas ke Emiten IDX

### 2.1 Tabel Lengkap

| Komoditas | Ticker yfinance | Emiten Produsen (beneficiary harga naik) | Emiten Konsumer (beneficiary harga turun) |
|-----------|----------------|------------------------------------------|------------------------------------------|
| **CPO** | `FCPO=F` (Bursa Malaysia) | AALI.JK, LSIP.JK, SIMP.JK, DSNG.JK, ANJT.JK, SGRO.JK, SSMS.JK, BWPT.JK | INDF.JK, ICBP.JK, MYOR.JK, ULTR.JK |
| **Batubara** | `NEWC=F` (ICE Newcastle) | PTBA.JK, ITMG.JK, ADRO.JK, HRUM.JK, BYAN.JK, INDY.JK, BSSR.JK, SMMT.JK, ZBRA.JK | — (tidak ada konsumer besar) |
| **Nikel** | LME (tidak ada yfinance) | INCO.JK, ANTM.JK, MDKA.JK | — |
| **Tembaga** | `HG=F` (COMEX) | ANTM.JK, MDKA.JK | — |
| **Emas** | `GC=F` (COMEX) | ANTM.JK, MDKA.JK | — |
| **Perak** | `SI=F` (COMEX) | ANTM.JK | — |
| **Timah** | LME (tidak ada yfinance) | TINS.JK | — |
| **Aluminium** | `ALI=F` (LME) | INAL.JK (jika listed) | — |
| **Gas Alam** | `NG=F` (Henry Hub) | PGAS.JK | — |
| **Crude Oil** | `CL=F` (WTI) / `BZ=F` (Brent) | MEDC.JK, ENRG.JK, BULL.JK, AKRA.JK (trading) | — |

### 2.2 Sensitivitas

Tidak semua emiten produsen punya sensitivitas yang sama terhadap harga komoditas. Faktor yang menentukan:

| Faktor | Tinggi Sensitivitas | Rendah Sensitivitas |
|--------|--------------------|--------------------|
| **Revenue share** | > 80% dari komoditas tersebut | < 30% (diversified) |
| **Cost structure** | Cost relatif fixed (operating leverage tinggi) | Cost variabel (margin stabil) |
| **Production volume** | Volume stabil → price-driven | Volume berubah → price + volume |
| **Hedging** | Tidak hedge → full exposure | Hedge → exposure tertutup |
| **Vertical integration** | Pure upstream → full exposure | Integrated (upstream + downstream) → partial |

**Contoh:**
- **AALI** — 95% revenue dari CPO → **sangat sensitif** ke harga CPO
- **ANTM** — diversified (emas, nikel, tembaga, batubara) → **moderat**, tergantung komoditas dominan
- **MDKA** — nikel + stainless steel → **moderat**, tergantung product mix

---

## 3. CPO (Crude Palm Oil)

### 3.1 Overview

CPO adalah komoditas terpenting untuk IDX setelah batubara. Indonesia adalah **produsen CPO terbesar dunia** (~60% global supply). Emiten sawit di IDX berkapitalisasi besar dan likuid.

### 3.2 Emiten CPO

| Ticker | Nama | Market Cap | ADV | Revenue Share CPO | Sensitivitas |
|--------|------|-----------|-----|-------------------|--------------|
| AALI.JK | Astra Agro Lestari | Besar | Likuid | ~95% | **Sangat Tinggi** |
| LSIP.JK | London Sumatra | Besar | Likuid | ~90% | **Sangat Tinggi** |
| SIMP.JK | Salim Ivomas | Sedang | Sedang | ~85% | **Tinggi** |
| DSNG.JK | Dharma Satya Nusantara | Sedang | Sedang | ~80% | **Tinggi** |
| ANJT.JK | Austindo Nusantara Jaya | Sedang | Sedang | ~75% | **Tinggi** |
| SGRO.JK | Sampoerna Agro | Sedang | Sedang | ~85% | **Tinggi** |
| SSMS.JK | Sawit Sumbermas Sarana | Kecil | Rendah | ~90% | **Tinggi** |
| BWPT.JK | Eagle High Plantations | Kecil | Rendah | ~85% | **Tinggi** |

### 3.3 Cara Analisis

```
1. Track harga CPO (Bursa Malaysia FCPO, atau data parquet existing)
2. Hitung perubahan CPO 1-bulan, 3-bulan, 6-bulan
3. Estimasi impact ke revenue emiten:
   Revenue change ≈ ΔCPO × production volume × 1 (assuming volume stable)
4. Estimasi impact ke earnings:
   Earnings change ≈ Revenue change × (1 - cost ratio)
   Cost ratio CPO ~60-70% (land, labor, fertilizer, transport)
5. Bandingkan dengan konsensus/ekspektasi pasar
6. Sinyal:
   - CPO naik > 10% dalam 1 bulan → bullish untuk AALI, LSIP, SIMP
   - CPO turun > 10% dalam 1 bulan → bearish untuk produsen, bullish untuk INDF/ICBP
```

### 3.4 Faktor yang Menggerakkan Harga CPO

| Faktor | Arah | Catatan |
|--------|------|---------|
| Produksi Indonesia | Naik → CPO turun | Musim panen (Aug-Nov) → supply naik |
| Produksi Malaysia | Naik → CPO turun | Data MPOB monthly |
| Demand India/China | Naik → CPO naik | Import data monthly |
| Biodiesel mandate | Naik → CPO naik | Indonesia B40 program |
| El Nino / La Nina | El Nino → CPO naik (drought reduces yield) | 6-12 month lag |
| EU deforestation regulation | Tighten → CPO turun (demand pressure) | EUDR 2025 |
| Crude oil price | Naik → CPO naik (biodiesel economics) | Correlation ~0.3-0.5 |

---

## 4. Batubara (Coal)

### 4.1 Overview

Indonesia adalah **eksportir batubara terbesar dunia** (~35% global seaborne trade). Emiten batubara di IDX berkapitalisasi besar dan dividenden tinggi.

### 4.2 Emiten Batubara

| Ticker | Nama | Market Cap | ADV | Revenue Share Coal | Sensitivitas |
|--------|------|-----------|-----|-------------------|--------------|
| ADRO.JK | Adaro Energy | Besar | Likuid | ~90% | **Sangat Tinggi** |
| PTBA.JK | Bukit Asam | Besar | Likuid | ~95% | **Sangat Tinggi** |
| ITMG.JK | Indo Tambangraya | Besar | Likuid | ~95% | **Sangat Tinggi** |
| HRUM.JK | Harum Energy | Sedang | Sedang | ~90% | **Tinggi** |
| BYAN.JK | Bayan Resources | Sedang | Rendah | ~95% | **Tinggi** |
| INDY.JK | Indika Energy | Sedang | Sedang | ~70% | **Tinggi** |
| BSSR.JK | Bara Senayang | Kecil | Rendah | ~95% | **Tinggi** |
| SMMT.JK | Samindo Resources | Kecil | Rendah | ~90% | **Tinggi** |
| ZBRA.JK | Zebra Nusantara | Kecil | Rendah | ~80% | **Tinggi** |

### 4.3 Cara Analisis

```
1. Track harga batubara (Newcastle index, atau data parquet existing)
2. Hitung perubahan harga 1-bulan, 3-bulan
3. Estimasi impact ke revenue:
   Revenue change ≈ ΔCoal price × export volume × 1
4. Estimasi impact ke earnings:
   Earnings change ≈ Revenue change × (1 - cost ratio)
   Cost ratio batubara ~50-65% (mining, transport, royalty)
5. Sinyal:
   - Coal naik > 15% dalam 1 bulan → bullish untuk ADRO, PTBA, ITMG
   - Coal turun > 15% → bearish, tapi cek dividend yield (sering tetap bayar dividen)
```

### 4.4 Faktor yang Menggerakkan Harga Batubara

| Faktor | Arah | Catatan |
|--------|------|---------|
| Demand China | Naik → coal naik | China import ~50% seaborne |
| Demand India | Naik → coal naik | India import growing |
| China energy policy | Shift ke renewable → coal turun | Long-term trend |
| Winter demand | Naik → coal naik | Nov-Feb (Northern hemisphere) |
| Indonesia DMO policy | Tighten → export turun → coal naik | Domestic Market Obligation 25% |
| Crude oil / gas price | Naik → coal naik (substitution) | Correlation ~0.4 |
| ESG pressure | Tighten → coal turun (long-term) | Coal divestment trend |

---

## 5. Nikel

### 5.1 Overview

Indonesia adalah **produsen nikel terbesar dunia** (~50% global supply). Nikel critical untuk baterai EV — demand growth tinggi.

### 5.2 Emiten Nikel

| Ticker | Nama | Market Cap | ADV | Revenue Share Nickel | Sensitivitas |
|--------|------|-----------|-----|---------------------|--------------|
| INCO.JK | Vale Indonesia | Besar | Likuid | ~90% | **Sangat Tinggi** |
| ANTM.JK | Aneka Tambang | Sedang | Likuid | ~30% (juga emas, tembaga) | **Moderat** |
| MDKA.JK | Merdeka Copper | Sedang | Likuid | ~40% (joli nikel + stainless) | **Moderat** |

### 5.3 Faktor yang Menggerakkan Harga Nikel

| Faktor | Arah | Catatan |
|--------|------|---------|
| EV battery demand | Naik → nickel naik | Long-term structural growth |
| Indonesia export policy | Ban → nickel naik | Indonesia pernah ban export nickel ore 2014-2017, 2020-sekarang |
| Stainless steel demand | Naik → nickel naik | ~70% nickel demand dari stainless |
| LME inventory | Naik → nickel turun | Supply glut signal |
| China property | Naik → nickel naik (stainless demand) | Property sector correlation |

---

## 6. Tembaga (Copper)

### 6.1 Overview

Tembaga adalah "Doctor Copper" — indikator kesehatan ekonomi global. Demand dari konstruksi, elektronik, dan EV.

### 6.2 Emiten Tembaga

| Ticker | Nama | Revenue Share Copper | Sensitivitas |
|--------|------|---------------------|--------------|
| ANTM.JK | Aneka Tambang | ~15% | Rendah (diversified) |
| MDKA.JK | Merdeka Copper | ~30% | Moderat |

### 6.3 Faktor Driver

| Faktor | Arah | Catatan |
|--------|------|---------|
| Global GDP growth | Naik → copper naik | "Doctor Copper" |
| China property | Naik → copper naik | China ~50% global copper demand |
| EV transition | Naik → copper naik | EV butuh 4x copper vs ICE |
| Supply disruption | Strike, mine closure → copper naik | Chile, Peru supply risk |

---

## 7. Emas (Gold)

### 7.1 Overview

Emas adalah safe haven asset. Harga emas naik saat ketidakpastian tinggi (geopolitik, inflasi, resesi).

### 7.2 Emiten Emas

| Ticker | Nama | Revenue Share Gold | Sensitivitas |
|--------|------|-------------------|--------------|
| ANTM.JK | Aneka Tambang | ~25% (gold division) | Moderat |
| MDKA.JK | Merdeka Copper | ~10% | Rendah |

### 7.3 Faktor Driver

| Faktor | Arah | Catatan |
|--------|------|---------|
| Real interest rate | Naik → gold turun | Opportunity cost of holding gold |
| USD strength (DXY) | Naik → gold turun | Gold priced in USD |
| Geopolitical risk | Naik → gold naik | Safe haven demand |
| Inflation | Naik → gold naik | Hedge against inflation |
| Central bank buying | Naik → gold naik | China, Russia, India CB gold buying |

---

## 8. Komoditas Lain

### 8.1 Timah (Tin)

| Emiten | Ticker | Revenue Share | Catatan |
|--------|--------|--------------|---------|
| PT Timah | TINS.JK | ~95% | Indonesia adalah produsen timah terbesar #2 dunia |

**Driver:** Demand elektronik (solder), solder wave technology, Indonesia export policy.

### 8.2 Gas Alam

| Emiten | Ticker | Revenue Share | Catatan |
|--------|--------|--------------|---------|
| Perusahaan Gas Negara | PGAS.JK | ~80% | Gas distribution, bukan production |

**Driver:** Indonesia domestic gas policy, LNG global price, infrastructure investment.

### 8.3 Crude Oil

| Emiten | Ticker | Revenue Share | Catatan |
|--------|--------|--------------|---------|
| Medco Energi | MEDC.JK | ~85% | E&P company |
| Energi Mega Persada | ENRG.JK | ~80% | E&P company |
| Bull Energy | BULL.JK | ~70% | Oil & gas trading |

**Driver:** OPEC+ policy, global demand, Indonesia lifting volume.

---

## 9. Cara Menggunakan Data Komoditas

### 9.1 Sebagai Faktor Tambahan di Decision Engine

```
COMMODITY SCORE (0-100)
│
├── Untuk emiten produsen komoditas:
│   ├── Cek harga komoditas terkait (1-bulan change, 3-bulan change)
│   ├── Jika harga naik > 10% → score boost (+10-20)
│   ├── Jika harga turun > 10% → score penalty (-10-20)
│   └── Jika harga stabil → netral (50)
│
├── Untuk emiten konsumer komoditas:
│   ├── Cek harga komoditas input (e.g., CPO untuk INDF)
│   ├── Jika harga turun → score boost (margin expand)
│   └── Jika harga naik → score penalty (margin compress)
│
└── Composite: weighted average berdasarkan revenue share komoditas
```

### 9.2 Sebagai Sinyal Konfirmasi

Komoditas tidak harus menjadi faktor utama, tapi sebagai **konfirmasi**:

1. **Technical bullish + CPO naik** → konfirmasi bullish untuk AALI → lebih yakin
2. **Technical bullish + CPO turun** → divergensi → hati-hati, mungkin false signal
3. **Fundamental undervalued + coal naik** → catalyst untuk re-rating
4. **Foreign net buy + nickel naik** → smart money confirm commodity thesis

### 9.3 Sebagai Risk Flag

1. **Concentration risk** — jika portfolio terlalu banyak emiten komoditas yang sama (e.g., 5 saham batubara) → tidak diversifikasi
2. **Commodity crash** — jika multiple komoditas turun simultan → risk-off untuk seluruh commodity sector
3. **Correlation breakdown** — saat komoditas dan saham disconnect → bisa jadi early warning

### 9.4 Sebagai Input untuk Macro Engine

Harga komoditas juga mempengaruhi makro ekonomi Indonesia:

| Komoditas | Makro Impact |
|-----------|-------------|
| Batubara naik | Trade balance surplus → rupiah menguat → bullish IDX |
| CPO naik | Trade balance surplus → rupiah menguat → bullish IDX |
| Crude oil naik | Impor BBM naik → trade balance tertekan → inflasi naik → bearish |
| Emas naik | Risk-off global → foreign outflow dari EM → bearish IDX |

---

## 10. Implementasi di Trading-System

### 10.1 Data yang Sudah Ada

Data komoditas 1,523 rows sudah ada di `/media/petrick/Parquet/trading_data/raw/commodity/`:
- Kolom: `periode`, `nama`, `satuan`, `harga`, `perubahan`
- Komoditas: CPO, batubara, nikel, tembaga, emas, perak, timah, aluminium, gas, crude oil
- Date range: 2018-2026

### 10.2 Yang Perlu Dilakukan

**Step 1: Migrate data ke DB (1-2 hari)**

```sql
CREATE TABLE IF NOT EXISTS commodity_prices (
    date TEXT NOT NULL,
    commodity_name TEXT NOT NULL,
    unit TEXT,
    price REAL,
    change_pct REAL,
    source TEXT DEFAULT 'legacy_parquet',
    PRIMARY KEY (date, commodity_name)
);
```

Rename kolom: `periode` → `date`, `nama` → `commodity_name`, `satuan` → `unit`, `harga` → `price`, `perubahan` → `change_pct`.

**Step 2: Commodity-to-stock mapping (1 hari)**

```python
COMMODITY_STOCK_MAP = {
    "CPO": {
        "producers": ["AALI.JK", "LSIP.JK", "SIMP.JK", "DSNG.JK", "ANJT.JK", "SGRO.JK", "SSMS.JK", "BWPT.JK"],
        "consumers": ["INDF.JK", "ICBP.JK", "MYOR.JK", "ULTR.JK"],
    },
    "Batubara": {
        "producers": ["ADRO.JK", "PTBA.JK", "ITMG.JK", "HRUM.JK", "BYAN.JK", "INDY.JK", "BSSR.JK", "SMMT.JK", "ZBRA.JK"],
        "consumers": [],
    },
    "Nikel": {
        "producers": ["INCO.JK", "ANTM.JK", "MDKA.JK"],
        "consumers": [],
    },
    "Tembaga": {
        "producers": ["ANTM.JK", "MDKA.JK"],
        "consumers": [],
    },
    "Emas": {
        "producers": ["ANTM.JK", "MDKA.JK"],
        "consumers": [],
    },
    "Timah": {
        "producers": ["TINS.JK"],
        "consumers": [],
    },
    "Gas": {
        "producers": ["PGAS.JK"],
        "consumers": [],
    },
    "Crude Oil": {
        "producers": ["MEDC.JK", "ENRG.JK", "BULL.JK"],
        "consumers": [],
    },
}
```

**Step 3: Commodity score engine (2-3 hari)**

```python
class CommodityScoreEngine:
    """Compute commodity-based score for each ticker."""
    
    def compute_score(self, ticker: str) -> tuple[float, dict]:
        """Returns (score 0-100, breakdown)."""
        # 1. Find which commodities affect this ticker
        # 2. Get latest price change (1-month, 3-month)
        # 3. Score: price up → boost for producers, penalty for consumers
        # 4. Weight by revenue share (if available)
        # 5. Return composite score
```

**Step 4: Integrate ke decision engine (1 hari)**

Tambah commodity score sebagai faktor ke-7 di decision engine:
- Weight: 5-10% (sebagai faktor tambahan, bukan pengganti 6 faktor existing)
- Atau: sebagai adjustment multiplier pada fundamental score (commodity price → earnings forecast → fundamental)

### 10.3 Estimasi Total

| Komponen | Estimasi |
|----------|----------|
| Migrate commodity data | 1-2 hari |
| Commodity-to-stock mapping | 1 hari |
| Commodity score engine | 2-3 hari |
| Integrate ke decision engine | 1 hari |
| Testing | 1 hari |
| **Total** | **6-8 hari** |

---

## 11. Data Source dan Update

### 11.1 Data Source

| Komoditas | Source | Frekuensi | Format | Access |
|-----------|--------|-----------|--------|--------|
| CPO | Bursa Malaysia (FCPO) | Daily | Futures price | yfinance `FCPO=F` |
| Batubara | ICE Newcastle (NEWC) | Weekly | Index price | yfinance (jika available) atau manual |
| Nikel | LME Nickel 3M | Daily | Spot price | yfinance (tidak ada) — perlu scraping atau API |
| Tembaga | COMEX (HG=F) | Daily | Futures price | yfinance `HG=F` |
| Emas | COMEX (GC=F) | Daily | Futures price | yfinance `GC=F` |
| Perak | COMEX (SI=F) | Daily | Futures price | yfinance `SI=F` |
| Timah | LME Tin 3M | Daily | Spot price | yfinance (tidak ada) — perlu scraping |
| Crude Oil | WTI (CL=F) / Brent (BZ=F) | Daily | Futures price | yfinance `CL=F`, `BZ=F` |
| Gas | Henry Hub (NG=F) | Daily | Futures price | yfinance `NG=F` |

### 11.2 Update Strategy

```
DAILY (EOD):
├── Fetch yfinance: GC=F, SI=F, HG=F, CL=F, BZ=F, NG=F, FCPO=F
├── Store ke commodity_prices table
└── Compute commodity score untuk affected tickers

WEEKLY:
├── Cek Newcastle coal index (manual atau API)
├── Cek LME nickel/tin (manual atau API)
└── Update commodity_prices untuk yang tidak ada daily feed

MONTHLY:
├── Review commodity-to-stock mapping (emiten baru, delisting)
├── Backtest commodity score accuracy
└── Adjust weights jika perlu
```

### 11.3 Data Parquet Existing

Data parquet `raw/commodity/` sudah punya 1,523 rows (2018-2026) untuk 10 komoditas. Ini cukup untuk:
- Backtest commodity score strategy
- Correlation analysis komoditas vs saham
- Regime detection berdasarkan commodity cycle

**Gap yang perlu di-backfill:**
- Beberapa bulan missing (cek konsistensi date range per komoditas)
- Data 2026 mungkin belum lengkap (last entry Jul 2026)

---

## Referensi

### Internal (Pustaka)
- `01-fundamental-pasar-modal.md` — Konsep dasar komoditas
- `03-pasar-modal-global.md` — Pasar global & komoditas
- `06-analisis-fundamental.md` — Analisis fundamental emiten komoditas
- `13-hal-yang-perlu-diperhatikan.md` — Faktor yang perlu diperhatikan (termasuk komoditas)
- `35-multi-asset-cross-market-analysis.md` — Cross-market analysis
- `89-faktor-pasar-modal-analisis-implementasi.md` — Audit faktor (komoditas sebagai gap kritis)
- `90-analisis-parquet-data-awal.md` — Analisis parquet (commodity data di raw/)

### External
- Bursa Malaysia — FCPO futures
- ICE — Newcastle coal index
- LME — Nickel, copper, tin 3M prices
- yfinance — Gold, silver, crude oil, gas futures

### Internal (Codebase)
- `src/market/analysis/cross_market_timezone.py` — DST-aware Wall Street close detection + `verify_dst_cutoff()` + `get_aligned_global_features()` (T-0 Asian, T-1 US/commodities) + `GLOBAL_TICKER_LAGS` + `MARKET_TIMEZONES`
- `src/market/analysis/multi_factor.py` — `GLOBAL_ASSETS` dict dengan 11 aset (5 indeks + 6 komoditas: GC=F, CL=F, HG=F, MTF=F, CPO=F, NI=F), asymmetric lag returns via `get_ticker_lag()` sebagai exogenous features
- `src/market/analysis/market_context.py` — `_fetch_commodity_signal()` sector-specific: Energy→CL=F+MTF=F, Basic Materials→GC=F+HG=F+NI=F, Consumer Defensive→CPO=F
- `src/market/data/macro_data_fetcher.py` — `CommodityFetcher` dengan `COMMODITY_TICKERS` (CPO proxy, CPO=F, FCPO=F, coal MTF=F, nickel, copper, tin, gold, oil)
- `scripts/backfill_commodity_futures.py` — Backfill 7 commodity futures dari yfinance (CL=F, GC=F, HG=F, MTF=F, CPO=F, FCPO=F, NI=F)
- `scripts/daily_signal_cron.py` — DST cutoff check sebelum signal computation + app_notifications INSERT (status=UNREAD)

---

> **Update 10 Agustus 2026:** Commodity futures data sudah di-backfill ke `ohlcv` table (CL=F: 2,179 rows, GC=F: 2,179, HG=F: 905, MTF=F: 750, CPO=F: 1,408). NI=F (nickel) tidak tersedia di yfinance (404). FCPO=F (alt ticker Bursa Malaysia) ditambahkan ke backfill script sebagai fallback. T-1 returns dari 5 komoditas (oil, gold, copper, coal, CPO) sudah masuk sebagai exogenous features di `MultiFactorFeaturePipeline` via `compute_exogenous_features()` dengan **asymmetric lag** (T-0 untuk ^N225/^HSI, T-1 untuk US/commodities) menggunakan `get_ticker_lag()`. Sector-specific commodity momentum signals sudah aktif di `MarketContextProvider._fetch_commodity_signal()`. DST-aware cutoff (`verify_dst_cutoff()`) memastikan global data di-lock hanya setelah Wall Street fully close (03:00 WIB summer / 04:00 WIB winter). `get_aligned_global_features()` menyupply global features siap pakai untuk MultiFactorModel/MLSignalProvider di 16:15 WIB.

---

> **Update 15 Agustus 2026 (P1 — Batch Commodity Ingestion):** Data komoditas real telah di-fetch dan disimpan ke PostgreSQL `market`:
> - `stock_prices`: CL=F (2,946 rows, 2020-01-02→2026-08-13), CPO=F (2,570), GC=F (2,946), HG=F (2,573), MTF=F (2,860, stale hingga 2025-12-27 — Yahoo tidak update).
> - **NICK.L** (WisdomTree Nickel Etc, LSE): 1,670 rows, 2020-01-02→2026-08-12 — proxy untuk LME Nickel karena NI=F tidak tersedia di yfinance (404).
> - **TIN.L** (WisdomTree Tin ETC, LSE): 1,386 rows, 2021-02-16→2026-08-13 — proxy untuk LME Tin karena TIN=F tidak tersedia di yfinance (404).
> - `macro_data` series baru: NICKEL (1,670 rows), TIN (1,386 rows), NEWCASTLE_COAL (1,745), CPO (1,663), COPPER (1,863).
> - `commodity_to_stock_map` (tabel baru): 28 mappings komoditas→saham IDX dengan sensitivity score (CPO→AALI 0.85, NICKEL→INCO 0.95, COAL→ADRO 0.80, dll).
> - Granger causality (P9): NICK.L→INCO.JK p=0.0000 (sangat signifikan, lag=1), NICK.L→ANTM.JK p=0.0032, NICK.L→TINS.JK p=0.0086.
> - Script: `scripts/batch_p1_commodity.py` + `scripts/batch_p9_causal.py`.
> - **Gap:** MTF=F (coal) stale hingga 2025-12-27 — perlu alternative source (ICE API atau manual input).
