# Matriks Relevansi: Data Satelit vs Pasar Modal

> **Dokumen referensi untuk evaluasi data satelit gratis sebagai sumber sinyal pasar modal.**
> Jika korelasi terbukti signifikan, modul satelit akan digeser ke pipeline aplikasi utama.

---

## 1. Sumber Data Satelit Gratis

### 1.1 NASA POWER API (Sudah Diimplementasi)

| Aspek | Detail |
|------|--------|
| **Parameter** | T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN, WS10M, GWETROOT, etc. |
| **Resolusi** | 0.5° (~50km), harian |
| **Biaya** | Gratis, no API key |
| **Akses** | REST API `https://power.larc.nasa.gov/api/temporal/daily/point` |
| **Data tersedia** | 1981 – sekarang, global |
| **Status di pipeline** | ✅ Real data |

### 1.2 Sentinel-2 (ESA Copernicus via Microsoft Planetary Computer)

| Aspek | Detail |
|------|--------|
| **Resolusi** | 10m/pixel (multispectral) |
| **Revisit** | 5 hari (twin satellite S2A + S2B) |
| **Biaya** | Gratis sepenuhnya, **no account needed** via Planetary Computer |
| **Akses** | STAC API `https://planetarycomputer.microsoft.com/api/stac/v1` |
| **Data tersedia** | Juli 2015 – sekarang, global |
| **Parameter** | 13 band multispectral → NDVI, LSWI, NDMI, NBR, NDWI, SAVI |
| **Status di pipeline** | ✅ Diimplementasi (NDVI real) |

### 1.3 VIIRS Nighttime Lights (NASA/NOAA)

| Aspek | Detail |
|------|--------|
| **Resolusi** | 500m, harian / monthly composite |
| **Biaya** | Gratis, perlu NASA Earthdata account |
| **Akses** | NASA Earthdata API, GEE |
| **Data tersedia** | 2012 – sekarang, global |
| **Status di pipeline** | ⚠️ Simulasi (butuh Earthdata auth) |

### 1.4 Sentinel-1 SAR (ESA Copernicus)

| Aspek | Detail |
|------|--------|
| **Resolusi** | 10m, C-band radar |
| **Revisit** | 6 hari |
| **Biaya** | Gratis |
| **Keunggulan** | Penetrasi awan — critical untuk Indonesia |
| **Data tersedia** | 2014 – sekarang, global |
| **Status di pipeline** | ❌ Belum diimplementasi |

### 1.5 AIS Ship Tracking (AISStream.io)

| Aspek | Detail |
|------|--------|
| **Resolusi** | Real-time, per vessel |
| **Biaya** | Gratis (AISStream.io) |
| **Akses** | WebSocket API |
| **Status di pipeline** | ❌ Belum diimplementasi |

### 1.6 Umbra Open Data (SAR 25cm)

| Aspek | Detail |
|------|--------|
| **Resolusi** | 25cm (komersial tertinggi) |
| **Biaya** | Gratis (Creative Commons, no sign-up) |
| **Data tersedia** | 20+ lokasi global, weekly update |
| **Limitasi** | Coverage terbatas (hanya 20+ lokasi fix) |
| **Status di pipeline** | ❌ Belum diimplementasi |

### 1.7 MODIS (NASA Terra/Aqua)

| Aspek | Detail |
|------|--------|
| **Resolusi** | 250m–1km |
| **Revisit** | 1-2 hari |
| **Biaya** | Gratis |
| **Data tersedia** | 2000 – sekarang |
| **Status di pipeline** | ❌ Belum diimplementasi |

### 1.8 Landsat 8/9 (USGS/NASA)

| Aspek | Detail |
|------|--------|
| **Resolusi** | 30m multispectral, 15m panchromatic |
| **Revisit** | 8 hari (L8+L9 combined) |
| **Biaya** | Gratis |
| **Data tersedia** | 1972 – sekarang (archive terpanjang) |
| **Status di pipeline** | ❌ Belum diimplementasi |

### 1.9 Forest Data Partnership (Google Cloud)

| Aspek | Detail |
|------|--------|
| **Resolusi** | 1-degree tiles, pantropical |
| **Biaya** | Gratis (CC-BY 4.0, requester-pays egress) |
| **Komoditas** | coffee, cocoa, palm, rubber |
| **Status di pipeline** | ❌ Belum diimplementasi |

---

## 2. Matriks Relevansi: Data Satelit vs Pasar Modal

| Data Satelit | Komoditas/Sektor | Ticker/Instrumen | Frekuensi | Lead Time | Status |
|-------------|-----------------|-----------------|-----------|-----------|--------|
| **Sentinel-2 NDVI** | CPO/Sawit | AALI.JK, LSIP.JK, SIMP.JK | 5 hari | 1-3 bulan | ✅ |
| **Sentinel-2 NDVI** | Corn (US) | ZC=F, ADM, BG | 5 hari | 1-3 bulan | ✅ |
| **Sentinel-2 NDVI** | Soybean (US) | ZS=F, BG | 5 hari | 1-3 bulan | ✅ |
| **Sentinel-2 NDVI** | Soybean (Brazil) | SOYB, Bovespa agri | 5 hari | 1-3 bulan | ✅ |
| **Sentinel-2 NDVI** | Wheat (US/Kansas) | ZW=F | 5 hari | 1-3 bulan | ✅ |
| **Sentinel-2 NDVI** | Cotton (US/Texas) | CT=F | 5 hari | 1-3 bulan | ✅ |
| **Sentinel-1 SAR** | Pelabuhan/Shipping | SMDR.JK, INPP.JK | 6 hari | 1-2 minggu | ❌ |
| **Sentinel-1 SAR** | Oil storage | CL=F, XLE ETF | 6 hari | 1-2 minggu | ❌ |
| **VIIRS Nightlight** | Aktivitas ekonomi | ^JKSE, IDX sektoral | harian | 1-3 bulan | ⚠️ |
| **VIIRS Nightlight** | Pelabuhan | SMDR.JK, INPP.JK | harian | 1-3 bulan | ⚠️ |
| **AIS ship tracking** | Trade flow | Shipping ETFs, BUMI.JK | real-time | 1-5 hari | ❌ |
| **NASA POWER** | Cuaca perkebunan | AALI.JK, LSIP.JK | harian | 2-8 minggu | ✅ |
| **NASA POWER** | Cuaca corn/soy | ZC=F, ZS=F | harian | 2-8 minggu | ✅ |
| **MODIS NDVI** | Macro crop trend | Commodity ETFs | 1-2 hari | 3-6 bulan | ❌ |
| **Landsat** | Long-term vegetasi | Climate/agri ETFs | 8 hari | 6-12 bulan | ❌ |
| **Umbra SAR** | Oil tank, port | CL=F, DAC, STNG | weekly | 1-2 minggu | ❌ |

---

## 3. Studi Pendukung

### 3.1 Container Port Satellite → Stock Returns (Nature, 2023)
- **Metode:** U-Net segmentation Sentinel-2 untuk 48 container ports → container area
- **Hasil:** Prediksi return saham di 27 dari 33 negara (2019-2021)
- **Return:** Annualized 16.38%, Sharpe 1.19
- **Sumber:** *Eye in outer space: satellite imageries of container ports can predict world stock returns* — Humanities and Social Sciences Communications, Nature

### 3.2 Nowcasting Global Trade from Space (IMF, 2025)
- **Metode:** AIS vessel movements + IMF PortWatch
- **Hasil:** Monthly nowcast global maritime trade (80% merchandise trade by volume)
- **Sumber:** IMF Working Paper WP/25/126

### 3.3 Watching Trade from Space (arxiv, 2025)
- **Metode:** SAR (Sentinel-1) + NTL (VIIRS) + XGBoost → port-level trade
- **Hasil:** Strong out-of-sample accuracy untuk US ports, validated on Russia post-sanctions
- **Sumber:** arxiv:2604.15444

### 3.4 Sentinel-2 NDVI → Grain Futures (ESA EO4Society, 2023)
- **Metode:** NDVI Sentinel-2 vs USDA Crop Production Report
- **Hasil:** Positive returns untuk Corn; Wheat mixed (information asymmetry dengan speculator institusional)
- **Sumber:** ESA EO4Society, Dresden 2023

### 3.5 QuantAg — Satellite Crop Yield Signal Engine
- **Metode:** Sentinel-2 NDVI/LSWI via Microsoft Planetary Computer → ML trading signals
- **Komoditas:** Corn, Soy, Wheat, Cotton (US, Brazil, Russia, China)
- **Sumber:** github.com/rmkenv/quantag

### 3.6 SatLens — Open Source Satellite Economic Monitor
- **Metode:** Sentinel-2 ship detection + VIIRS nightlight + AIS → economic activity
- **Sumber:** github.com/satlens/satlens

---

## 4. Prioritas Implementasi Pipeline

| Prioritas | Sumber | Use Case | Effort | Status |
|-----------|--------|----------|--------|--------|
| **1** | Sentinel-2 via Planetary Computer | NDVI real untuk CPO, Corn, Soy, Wheat, Cotton | Medium | ✅ Produksi |
| **2** | NASA POWER (existing) | Cuaca perkebunan, semua kasus | Rendah | ✅ Produksi |
| **3** | VIIRS Nightlight via NASA Earthdata | Aktivitas ekonomi/pelabuhan | Medium | ❌ Dihapus |
| **4** | Sentinel-1 SAR via Copernicus | Vessel detection, oil storage | Tinggi | ❌ |
| **5** | AIS via AISStream.io | Ship tracking real-time | Rendah | ❌ |
| **6** | Umbra Open Data | SAR 25cm oil tank | Rendah | ❌ |

---

## 5. Arsitektur Produksi (Terintegrasi)

### 5.1 Modul Aplikasi

| Komponen | Path | Fungsi |
|----------|------|--------|
| `src/market/data/satellite_fetcher.py` | Modul utama | Fetcher global: NASA POWER + Sentinel-2 NDVI |
| `scripts/fetch_satellite_data.py` | CLI wrapper | `--ticker`, `--sector`, `--lat/--lon`, `--seed`, `--from-watchlist` |
| `scripts/satellite_stock_correlation.py` | Riset pipeline | Korelasi & Granger causality analysis |
| `src/market/db/models.py` | ORM | `SatelliteObservation`, `SatelliteCorrelationResult`, `SatelliteTickerLocation` |
| `alembic/versions/0016_add_satellite_tables.py` | Migrasi | Skema PostgreSQL/SQLite untuk satelit |
| `alembic/versions/0017_add_satellite_ticker_locations.py` | Migrasi | Tabel mapping ticker→lokasi |
| `docs/domino_effect_schema.sql` | DDL PostgreSQL | DDL untuk 3 tabel satelit |

### 5.2 Resolusi Lokasi (Global)

Pipeline satelit mendukung **lokasi apa pun di Bumi**. Resolusi lokasi:

1. **`satellite_ticker_locations` table** — mapping eksplisit per-ticker (prioritas tertinggi)
2. **`SECTOR_FALLBACK_LOCATIONS`** — fallback berbasis sektor (global coverage)
3. **Skip** — jika tidak ada mapping

Sektor fallback yang tersedia (cakupan global — semua benua):

| Sektor | Jumlah Lokasi | Cakupan Benua | Contoh Lokasi |
|--------|--------------|---------------|---------------|
| `agriculture` | 34 | Asia, Amerika, Eropa, Afrika, Oseania | Indonesia (CPO Kalimantan/Sumatera, Rice Java), Malaysia (CPO Sabah/Sarawak), US (Corn Iowa, Soybean Illinois, Wheat Kansas, Cotton Texas, Central Valley), Brazil (Soybean, Sugar, Coffee), Argentina (Soybean), India (Wheat, Rice, Cotton), Australia (Wheat, Cotton), Thailand (Rice, Sugar), Vietnam (Rice, Coffee), Côte d'Ivoire & Ghana (Cocoa), China (Soybean, Corn, Cotton), France & Germany (Wheat), Ukraine (Corn, Wheat), Russia (Wheat Krasnodar, Rostov) |
| `energy` | 20 | Asia, Amerika, Eropa, Afrika, Oseania | Indonesia (Coal Kalimantan, Sumatera), US (Shale Texas, Bakken, Gas), Saudi/Iraq/UAE/Kuwait/Iran (Oil), North Sea (Norway, UK), Russia (Oil Siberia, Gas Yamal), Australia (Coal Queensland/NSW, LNG), Nigeria, Angola, Brazil (Pre-Salt), Venezuela, Canada (Oil Sands), Qatar (LNG) |
| `mining` | 19 | Asia, Amerika, Eropa, Afrika, Oseania | Indonesia (Nickel, Copper Papua, Gold Sumbawa, Tin Bangka, Bauxite), Chile (Copper Atacama, Escondida), Peru (Copper, Zinc), Australia (Iron Ore, Gold, Lithium), China (Rare Earth, Tungsten), South Africa (Platinum, Gold, Manganese), DRC (Cobalt), Mongolia (Copper, Coal), Brazil (Iron Ore Carajas), Mexico (Silver), Guinea (Bauxite) |
| `shipping` | 18 | Asia, Amerika, Eropa, Afrika | Indonesia (Tanjung Priok, Tanjung Perak, Bitung), Strait of Malacca, Suez Canal, Panama Canal, Strait of Hormuz, Bab el-Mandeb, Bosphorus, Singapore, Rotterdam, Shanghai, Shenzhen, Busan, Los Angeles, Hamburg, Mumbai, Dubai |
| `textiles` | 7 | Asia, Amerika, Oseania, Eropa | US (Cotton Texas), India (Cotton Gujarat), China (Cotton Xinjiang), Pakistan (Cotton Sindh), Brazil (Cotton), Australia (Cotton Queensland), Turkey (Cotton Aegean) |
| `forestry` | 8 | Asia, Amerika, Eropa, Oseania | Indonesia (Pulp Riau, Kalimantan), Brazil (Eucalyptus), Canada (Timber BC), Russia (Timber Siberia), Sweden, Finland, Chile |
| `aquaculture` | 8 | Asia, Amerika, Eropa | Indonesia (Aquaculture Sulawesi, Fishing Malaka), Norway (Salmon), Chile (Salmon Patagonia), China (Aquaculture Shandong), Vietnam (Mekong Delta), Peru (Anchovy), Japan (Tohoku) |
| **Total** | **114** | **6 benua** | |

### 5.3 Database Tables

| Tabel | Fungsi | Unique Key |
|-------|--------|------------|
| `satellite_observations` | Raw data harian/sparse per lokasi | (location_name, date, metric, source) |
| `satellite_correlation_results` | Hasil analisis korelasi | (location_name, satellite_metric, stock_ticker, frequency, rolling_window) |
| `satellite_ticker_locations` | Mapping ticker→lokasi geografis | (ticker, location_name) |

### 5.4 Metrik Signifikan (Terbukti p < 0.05)

| Metrik | Sumber | Kasus Signifikan |
|--------|--------|------------------|
| NDVI | Sentinel-2 (Planetary Computer) | CPO, Corn |
| T2M | NASA POWER | CPO, Corn |
| PRECTOTCORR | NASA POWER | CPO, Corn |
| RH2M | NASA POWER | CPO |
| ALLSKY_SFC_SW_DWN | NASA POWER | Corn |

**Dihapus (tidak signifikan):** NIGHTLIGHT (simulasi), Kasus B Port/Shipping.

---

## 6. Catatan

- Data satelit adalah **alternative data** — bukan sinyal trading standalone, tapi pelengkap sinyal kuantitatif lainnya.
- Lead time 1-3 bulan untuk NDVI → saham berarti cocok untuk **Swing Trading**, bukan Day Trading.
- Korelasi harian cenderung lemah (r < 0.16) karena noise pasar; resampling ke weekly/monthly meningkatkan |r| hingga 3-5× (lihat hasil pipeline `scripts/satellite_stock_correlation.py`).
- NDVI dari Sentinel-2 adalah data real (via Microsoft Planetary Computer, gratis tanpa API key).
- Pipeline produksi mendukung **lokasi global apa pun** — tidak terbatas ke kasus riset awal.
- Cross-reference: `pustaka/30-sentiment-analysis-alternative-data.md`, `pustaka/97-strategi-alternatif-ekspansi-data-2026.md`
