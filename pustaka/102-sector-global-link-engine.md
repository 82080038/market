# Sector-Global Link Engine: Pola Sektor IDX ↔ Pasar Global dengan Timezone Awareness

> **Tujuan:** Dokumen ini mendefinisikan engine yang memetakan setiap sektor IDX ke global market driver yang relevan, dengan timezone-aware lag (T-0 untuk Asian markets, T-1 untuk US/Europe). Engine ini menjawab pertanyaan: "Bagaimana karakteristik unik tiap sektor IDX berhubungan dengan pasar global yang relevan, dan jam buka/tutup bursa mana yang paling mempengaruhi?"

---

## Daftar Isi

1. [Konsep dan Motivasi](#1-konsep-dan-motivasi)
2. [Sektor → Global Driver Mapping](#2-sektor--global-driver-mapping)
3. [Timezone-Aware Signal Alignment](#3-timezone-aware-signal-alignment)
4. [Implementasi Engine](#4-implementasi-engine)
5. [Ekspektasi dan Limitasi](#5-ekspektasi-dan-limitasi)

---

## 1. Konsep dan Motivasi

### 1.1 Masalah

Engine ablation existing memperlakukan semua ticker IDX sama — tidak ada diferensiasi sektor. Padahal:

- **ADRO (Energy)** paling dipengaruhi oleh harga batubara dan crude oil (NYMEX, close 21:00 UTC)
- **BBCA (Financial Services)** paling dipengaruhi oleh US 10Y yield dan S&P 500 (NYSE, close 21:00 UTC)
- **AALI (Consumer Defensive/Plantation)** paling dipengaruhi oleh CPO futures (Bursa Malaysia, close 10:00 UTC)
- **TLKM (Communication Services)** paling dipengaruhi oleh Nasdaq (NASDAQ, close 21:00 UTC)
- **ANTM (Basic Materials)** paling dipengaruhi oleh gold dan copper prices (COMEX, close 21:00 UTC)

### 1.2 Solusi

Engine `sector_global_link` menggabungkan 3 dimensi:

1. **Sektor mapping** — tiap ticker dipetakan ke sektor via `instrument_master.sector`
2. **Global driver** — tiap sektor dipetakan ke 1-2 global market tickers yang paling relevan
3. **Timezone lag** — sinyal global di-shift sesuai jam tutup bursa (T-0 Asian, T-1 US/Europe)

### 1.3 Mengapa Ini Berbeda dari Engine Existing

| Engine | Pendekatan | Kelemahan |
|--------|-----------|-----------|
| `cross_market` | Sinyal global yang sama untuk semua ticker | Tidak diferensiasi sektor |
| `commodity` | Sinyal komoditas untuk semua ticker | Tidak semua sektor dipengaruhi komoditas |
| `overnight_idx` | Aggregate global → IHSG | Tidak per-ticker, tidak per-sektor |
| `sector_global_link` | **Sektor-specific global driver dengan timezone lag** | Baru |

---

## 2. Sektor → Global Driver Mapping

### 2.1 Mapping Table

| IDX Sector | Global Driver 1 | Global Driver 2 | Lag | Mechanism |
|------------|----------------|----------------|-----|-----------|
| **Energy** | `CL=F` (Crude Oil) | `^GSPC` (S&P 500) | T-1 | Revenue driver + sentiment |
| **Basic Materials** | `GC=F` (Gold) | `000001.SS` (Shanghai) | T-1 / T-0 | Commodity price + China demand |
| **Financial Services** | `^TNX` (US 10Y) | `^GSPC` (S&P 500) | T-1 | Rate sensitivity + sentiment |
| **Consumer Defensive** | `IDR=X` (USD/IDR) | `^GSPC` (S&P 500) | T-1 | Import cost + risk appetite |
| **Consumer Cyclical** | `^IXIC` (Nasdaq) | `^GSPC` (S&P 500) | T-1 | Risk appetite + discretionary |
| **Communication Services** | `^IXIC` (Nasdaq) | — | T-1 | Global tech sentiment |
| **Industrials** | `000001.SS` (Shanghai) | `^GSPC` (S&P 500) | T-0 / T-1 | China demand + industrial cycle |
| **Real Estate** | `^TNX` (US 10Y) | — | T-1 | Rate sensitivity |
| **Technology** | `^IXIC` (Nasdaq) | — | T-1 | Global tech benchmark |
| **Healthcare** | `^GSPC` (S&P 500) | — | T-1 | Defensive global sentiment |
| **Utilities** | `^TNX` (US 10Y) | — | T-1 | Rate sensitivity (bond proxy) |

### 2.2 Subsector Override

Untuk subsektor tertentu, override global driver:

| Subsector | Override Driver | Alasan |
|-----------|----------------|--------|
| Gold (ANTM, MDKA) | `GC=F` | Direct gold price exposure |
| Coal (ADRO, PTBA, ITMG) | `CL=F` | Energy commodity proxy (no coal futures in yfinance) |
| Banks (BBCA, BBRI, BMRI) | `^TNX` primary | Rate sensitivity dominant |
| Telecom (TLKM, ISAT) | `^IXIC` | Global tech/telecom benchmark |
| Plantation (AALI, LSIP) | `CPO=F` if available, else `IDR=X` | CPO price direct revenue |

### 2.3 Signal Direction

| Global Driver | Direction vs IDX Sector | Logic |
|---------------|------------------------|-------|
| `CL=F` (Oil up) | Energy ↑ (+1) | Revenue increase |
| `GC=F` (Gold up) | Basic Materials (Gold) ↑ (+1) | Revenue increase |
| `^TNX` (Yield up) | Financials ↓ (-1) | Margin pressure, Real Estate ↓ (-1) |
| `^TNX` (Yield up) | Utilities ↓ (-1) | Bond proxy outflow |
| `^GSPC` (S&P up) | All sectors ↑ (+1) | Sentiment |
| `^IXIC` (Nasdaq up) | Tech/Telecom ↑ (+1) | Risk appetite |
| `IDR=X` (USD/IDR up) | Consumer Defensive ↓ (-1) | Import cost increase |
| `IDR=X` (USD/IDR up) | Basic Materials ↑ (+1) | Export revenue (USD revenue) |
| `000001.SS` (Shanghai up) | Industrials/Basic Mat ↑ (+1) | China demand |
| `^VIX` (VIX up) | All sectors ↓ (-1) | Risk-off |

---

## 3. Timezone-Aware Signal Alignment

### 3.1 Bursa Trading Hours (UTC)

```
B0: 00:00-02:00 → Tokyo open (overnight Asia)
B1: 02:00-06:30 → Tokyo trading → close 06:30 UTC
B2: 06:30-08:00 → Hong Kong trading → close 08:00 UTC
B3: 08:00-08:50 → Shanghai close 07:00 UTC, IDX open 02:00 UTC (09:00 WIB)
B4: 08:50-14:30 → IDX trading (09:00-15:50 WIB), Europe transition
B5: 14:30-21:00 → NYSE/NASDAQ session
B6: 21:00-24:00 → US close, post-Wall Street
```

### 3.2 Lag Assignment per Global Ticker

| Ticker | Exchange | Close UTC | Lag | Reason |
|--------|----------|-----------|-----|--------|
| `^N225` | TSE | 06:30 | T-0 | Closes before IDX |
| `^HSI` | HKEX | 08:00 | T-0 | Closes before IDX |
| `000001.SS` | SSE | 07:00 | T-0 | Closes before IDX |
| `CPO=F` | Bursa Malaysia | 10:00 | T-1 | Closes after IDX open |
| `^GSPC` | NYSE | 21:00 | T-1 | Closes after IDX |
| `^IXIC` | NASDAQ | 21:00 | T-1 | Closes after IDX |
| `^VIX` | CBOE | 21:00 | T-1 | Closes after IDX |
| `^TNX` | CBOE | 21:00 | T-1 | Closes after IDX |
| `CL=F` | NYMEX | 21:00 | T-1 | Settles after IDX |
| `GC=F` | COMEX | 21:00 | T-1 | Settles after IDX |
| `IDR=X` | FX | 24h | T-1 | Use previous day close |
| `DX-Y.NYB` | ICE | 21:00 | T-1 | Settles after IDX |

### 3.3 Anti Look-Ahead Compliance

- Semua global returns di-shift(1) minimum untuk mencegah look-ahead
- Untuk T-0 tickers (Asian), shift(1) tetap dilakukan karena signal digunakan untuk prediksi T+1
- Untuk T-1 tickers (US/Europe), shift(1) = gunakan close T-1 untuk prediksi T

---

## 4. Implementasi Engine

### 4.1 Signal Generation Logic

```python
# Pseudocode
for each ticker:
    sector = lookup_sector(ticker)  # from instrument_master
    subsector = lookup_subsector(ticker)
    
    # Determine global drivers
    drivers = SECTOR_GLOBAL_MAP.get(sector, [])
    if subsector in SUBSECTOR_OVERRIDE:
        drivers = SUBSECTOR_OVERRIDE[subsector]
    
    for driver_ticker, direction in drivers:
        lag = GLOBAL_TICKER_LAGS[driver_ticker]
        driver_returns = load_ohlcv(driver_ticker).pct_change().shift(lag)
        
        # Generate signal
        if driver_returns > threshold:
            signal = +1 * direction
        elif driver_returns < -threshold:
            signal = -1 * direction
```

### 4.2 Threshold

- Threshold = 0.5% (0.005) — hanya gerakan signifikan yang di-convert ke signal
- Jika |return| < threshold → signal = 0 (neutral)
- Multi-driver: jika 2 drivers disagree → signal = 0 (conflict)
- Multi-driver: jika 2 drivers agree → signal = consensus direction

### 4.3 Engine Registration

| Field | Value |
|-------|-------|
| Name | `sector_global_link` |
| Category | SIGNAL_ENHANCER |
| Signal Type | DIRECTIONAL |
| Default Weight | 0.12 |
| Data Tables | ohlcv, instrument_master |
| Min Data Days | 60 |

---

## 5. Ekspektasi dan Limitasi

### 5.1 Ekspektasi

- **Energy** dan **Basic Materials** sektor paling promising karena direct commodity linkage
- **Financial Services** juga promising karena rate sensitivity well-documented
- **Consumer Defensive** mungkin lebih rendah karena FX effect slower-moving
- Expected ΔSharpe: -0.1 to +0.3 — sektor-specific mapping seharusnya lebih baik dari generic global signal

### 5.2 Limitasi

1. **Subsector mapping tidak lengkap** — `instrument_master.subsector` tidak selalu match dengan komoditas spesifik
2. **Coal futures tidak tersedia** di yfinance — `CL=F` (crude oil) sebagai proxy untuk energy/coal sector kurang ideal
3. **CPO=F data terbatas** — hanya dari Aug 2024, sehingga plantation sector mungkin tidak dapat signal
4. **Threshold static** — 0.5% mungkin tidak optimal untuk semua sektor (volatilitas berbeda)
5. **Tidak ada dynamic weight** — driver 1 dan driver 2 dapat sama-sama weighted, padahal salah satu mungkin lebih dominan

### 5.3 Cross-Reference

- `pustaka/35-multi-asset-cross-market-analysis.md` — teori intermarket analysis
- `pustaka/36-gap-data-timezone-global-idx.md` — timezone alignment & DST
- `pustaka/91-komoditas-spesifik-idx.md` — komoditas spesifik IDX
- `pustaka/101-global-idx-advanced-models.md` — 4 model advanced global-IDX
- `src/market/analysis/cross_market_timezone.py` — timezone lag helper
- `src/market/analysis/sector_rotation.py` — sector rotation engine (IDX internal)
- `src/market/analysis/market_context.py:797` — commodity ticker by sector

---

## Referensi

1. Baur, D.G. & McDermott, T.K. (2010). "Is Gold a Safe Haven?" JBF, 34(8), 1886-1898.
2. Baur, D.G. & Lucey, B.M. (2010). "Is Gold a Hedge or a Safe Haven? An Analysis of Stocks, Bonds and Gold." Financial Review, 45(2), 217-229.
3. Kilian, L. & Park, C. (2009). "The Impact of Oil Price Shocks on the U.S. Stock Market." International Economic Review, 50(4), 1267-1287.
4. Bjørnland, H.C. & Leitemo, K. (2009). "Identifying the Interdependence Between US Monetary Policy and the Stock Market." Journal of Monetary Economics, 56(2), 275-282.
5. Driesprong, G., Jacobsen, B., & Maat, B. (2008). "Striking Oil: Another Puzzle?" Journal of Financial Economics, 89(2), 307-327.
6. Chen, N.F., Roll, R., & Ross, S.A. (1986). "Economic Forces and the Stock Market." Journal of Business, 59(3), 383-403.
7. pustaka/91-komoditas-spesifik-idx.md — komoditas spesifik untuk IDX
