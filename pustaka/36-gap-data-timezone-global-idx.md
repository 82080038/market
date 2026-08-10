# Gap Data, Zona Waktu & Delay: Market Global vs Indonesia

> **Tujuan:** Dokumen ini adalah referensi definitif untuk memahami gap data, perbedaan zona waktu, delay data feed, dan overlap perdagangan antara pasar modal Indonesia (IDX) dengan bursa global — implikasi untuk sistem trading, data engineering, dan risk management.

---

## Daftar Isi

1. [Zona Waktu Bursa Global](#1-zona-waktu-bursa-global)
2. [Jam Perdagangan IDX](#2-jam-perdagangan-idx)
3. [Overlap IDX dengan Bursa Global](#3-overlap-idx-dengan-bursa-global)
4. [Delay Data per Provider](#4-delay-data-per-provider)
5. [Overnight Gap Risk](#5-overnight-gap-risk)
6. [Dampak ke Sistem Trading](#6-dampak-ke-sistem-trading)
7. [Strategi Mitigasi Gap](#7-strategi-mitigasi-gap)
8. [Implementasi untuk IDX](#8-implementasi-untuk-idx)
9. [Checklist Implementasi](#9-checklist-implementasi)

---

## 1. Zona Waktu Bursa Global

### 1.1 Tabel Lengkap Bursa Utama

| Bursa | Kode | Zona Waktu | UTC Trading Hours | DST | Overlap IDX |
|-------|------|-----------|-------------------|-----|-------------|
| **IDX (Jakarta)** | IDX | UTC+7 | 02:00 - 08:50 | None | - |
| **Tokyo (TSE)** | TSE | UTC+9 | 00:00 - 06:30 | None | Partial |
| **Shanghai (SSE)** | SSE | UTC+8 | 01:30 - 07:00 | None | Moderate |
| **Shenzhen (SZSE)** | SZSE | UTC+8 | 01:30 - 07:00 | None | Moderate |
| **Hong Kong (HKEX)** | HKEX | UTC+8 | 01:30 - 08:00 | None | **Strong** |
| **Singapore (SGX)** | SGX | UTC+8 | 01:00 - 09:00 | None | **Strong** |
| **Seoul (KRX)** | KRX | UTC+9 | 00:00 - 06:00 | None | Partial |
| **Taiwan (TWSE)** | TWSE | UTC+8 | 01:00 - 05:30 | None | Moderate |
| **Mumbai (BSE)** | BSE | UTC+5:30 | 03:45 - 10:00 | None | Moderate |
| **Thailand (SET)** | SET | UTC+7 | 02:30 - 09:30 | None | **Strong** (same TZ) |
| **London (LSE)** | LSE | UTC+0/+1 | 08:00 - 16:30 | Mar-Oct | **None** |
| **Frankfurt (FWB)** | FWB | UTC+1/+2 | 08:00 - 16:30 | Mar-Oct | **None** |
| **Euronext Paris** | EPA | UTC+1/+2 | 08:00 - 16:30 | Mar-Oct | **None** |
| **SIX Swiss** | SIX | UTC+1/+2 | 08:00 - 16:20 | Mar-Oct | **None** |
| **NYSE** | NYSE | UTC-5/-4 | 14:30 - 21:00 | Mar-Nov | **None** |
| **NASDAQ** | NASDAQ | UTC-5/-4 | 14:30 - 21:00 | Mar-Nov | **None** |
| **Toronto (TSX)** | TSX | UTC-5/-4 | 14:30 - 21:00 | Mar-Nov | **None** |
| **Brazil (B3)** | B3 | UTC-3 | 13:00 - 21:00 | Oct-Feb | **None** |
| **ASX (Sydney)** | ASX | UTC+10/+11 | 23:00 - 05:00(+1) | Oct-Apr | **None** |
| **NZX (Wellington)** | NZX | UTC+12/+13 | 21:00 - 04:00(+1) | Sep-Apr | **None** |

### 1.2 Visual Timeline (UTC)

```
UTC:  00    02    04    06    08    10    12    14    16    18    20    22    24
      │     │     │     │     │     │     │     │     │     │     │     │     │
TSE   ▓▓▓▓▓▓▓▓▓░░░▓▓▓▓▓▓▓▓▓                                     (lunch break)
KRX   ▓▓▓▓▓▓▓▓▓░░░▓▓▓▓▓▓▓
SSE   ░░▓▓▓▓▓▓░░░░░░░▓▓▓▓▓
HKEX  ░░▓▓▓▓▓▓▓░░░▓▓▓▓▓▓▓▓
SGX   ░▓▓▓▓▓▓▓▓▓░░░▓▓▓▓▓▓▓▓▓▓
IDX   ░░▓▓▓▓▓▓▓▓░░░▓▓▓▓▓▓▓▓░
SET   ░░░▓▓▓▓▓▓▓░░░▓▓▓▓▓▓▓▓▓
BSE   ░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
LSE                             ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
FWB                             ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
NYSE                                              ▓▓▓▓▓▓▓▓▓▓▓▓▓
NASDAQ                                            ▓▓▓▓▓▓▓▓▓▓▓▓▓

Legend: ▓ = trading session, ░ = pre/post, gap = closed
```

### 1.3 Key Observation

**IDX tutup sebelum Eropa dan AS buka.** Ini berarti:
- Event Eropa/AS baru tercermin di IDX pada **hari berikutnya**
- IDX memiliki **overnight exposure** terhadap global macro
- Foreign flow di IDX dipengaruhi oleh sentiment semalam dari US market

---

## 2. Jam Perdagangan IDX

### 2.1 Detail Sesi Perdagangan

| Sesi | Senin-Kamis (WIB) | Jumat (WIB) | UTC |
|------|-------------------|-------------|-----|
| **Pre-Opening (Input)** | 08:45 - 08:57 | 08:45 - 08:57 | 01:45 - 01:57 |
| **Non-Cancellation (No Withdraw)** | 08:56 - 08:57 | 08:56 - 08:57 | 01:56 - 01:57 |
| **Non-Cancellation (No Amend)** | 08:56 - 08:59 | 08:56 - 08:59 | 01:56 - 01:59 |
| **Pre-Opening (Matching)** | 08:58 - 08:59 | 08:58 - 08:59 | 01:58 - 01:59 |
| **Sesi 1** | 09:00 - 12:00 | 09:00 - 11:30 | 02:00 - 05:00 |
| **Break** | 12:00 - 13:30 | 11:30 - 14:00 | 05:00 - 06:30 |
| **Sesi 2** | 13:30 - 15:50 | 14:00 - 15:50 | 06:30 - 08:50 |
| **Pre-Closing (Input)** | 15:50 - 15:59 | 15:50 - 15:59 | 08:50 - 08:59 |
| **Random Closing** | 15:58 - 15:59 | 15:58 - 15:59 | 08:58 - 08:59 |
| **Pre-Closing (Matching)** | 16:00 - 16:01 | 16:00 - 16:01 | 09:00 - 09:01 |
| **Post-Closing** | 16:02 - 16:15 | 16:02 - 16:15 | 09:02 - 09:15 |

### 2.2 Catatan

- **Jumat:** Sesi 1 lebih pendek (09:00 - 11:30), break lebih panjang, Sesi 2 mulai 14:00
- **WIB = UTC+7** sepanjang tahun (tidak ada DST)
- **JATS time:** Waktu resmi BEI, mengacu pada server JATS
- **Auto-reject:** ±15% dari harga referensi (daily price limit)
- **Negotiated Market:** 09:00 - 16:30 WIB (lebih panjang dari regular market)

---

## 3. Overlap IDX dengan Bursa Global

### 3.1 Matriks Overlap

| Bursa | Overlap dengan IDX | Durasi | Kualitas |
|-------|--------------------|--------|----------|
| **Tokyo (TSE)** | Sesi 1 IDX ↔ Sesi 2 TSE | ~3 jam | Moderate |
| **Shanghai (SSE)** | Sesi 1 IDX ↔ Sesi 1 SSE | ~3 jam | Moderate |
| **Hong Kong (HKEX)** | Sesi 1 & 2 IDX ↔ Sesi 1 & 2 HKEX | ~6.5 jam | **Strong** |
| **Singapore (SGX)** | Full IDX ↔ Full SGX | ~6.5 jam | **Strong** |
| **Thailand (SET)** | Full IDX ↔ Full SET (same TZ) | ~7 jam | **Strong** |
| **Mumbai (BSE)** | Sesi 2 IDX ↔ Sesi 1 BSE | ~2.5 jam | Moderate |
| **London (LSE)** | **No overlap** | 0 | None |
| **New York (NYSE)** | **No overlap** | 0 | None |

### 3.2 Dampak Overlap ke Trading

| Overlap Level | Dampak |
|---------------|--------|
| **Strong (HK, SG, TH)** | Korelasi intraday tinggi, foreign flow regional |
| **Moderate (JP, CN, IN)** | Sentiment Asia, commodity linkage |
| **None (UK, US, EU)** | Overnight gap risk, event-driven gap |

---

## 4. Delay Data per Provider

### 4.1 IDX Data Delay

| Provider | Delay IDX | Format | Akses | Biaya |
|----------|-----------|--------|-------|-------|
| **Yahoo Finance** | **10 menit** | OHLCV, REST | Public, free | Gratis |
| **Google Finance** | **10 menit** | Price only | Public, free | Gratis |
| **ICE Data Services** | **Real-time** | L1/L2, streaming | API (licensed) | Berbayar |
| **Invezgo API** | **~5 detik** | REST + WebSocket | API | Berbayar |
| **RapidAPI IDX** | **Real-time** (no cache) | REST | API | Freemium |
| **iTick API** | **<50ms** (WebSocket) | REST + WS | API | Freemium |
| **Broker lokal** (BCA, BNI, Sinarmas) | **Real-time** | Proprietary | Broker API | Per broker |
| **IDX scraper** (EOD) | **1-2 jam** setelah close | CSV/HTML | Web scraping | Gratis |

### 4.2 Global Data Delay (Yahoo Finance)

| Market | Suffix | Delay | Provider |
|--------|--------|-------|----------|
| **US (NYSE/NASDAQ)** | (none) | **Real-time** | ICE Data Services |
| **US Indices** (^GSPC, ^IXIC) | ^ | Real-time | |
| **Indonesia (IDX)** | .JK | **10 menit** | ICE Data Services |
| **UK (LSE)** | .L | 15 menit | ICE Data Services |
| **Germany** | .DE | 15 menit | ICE Data Services |
| **France** | .PA | 15 menit | ICE Data Services |
| **Japan (TSE)** | .T | Real-time | |
| **Hong Kong** | .HK | 15 menit | |
| **Australia** | .AX | 20 menit | |
| **India (BSE)** | .BO | 15 menit | |

### 4.3 Yahoo Finance IDX Issue (2025-2026)

Sejak ~September 2025, Yahoo Finance mengalami masalah update data IDX:
- Data hari baru kadang baru muncul setelah market close (bukan real-time)
- Bukan masalah di sisi client/API, tapi di sisi Yahoo
- **Workaround:** Gunakan Google Finance untuk real-time price, atau broker API untuk eksekusi

### 4.4 BEI Data Distribution Enhancement (2025)

BEI menyempurnakan format distribusi data sejak 25 Agustus 2025:
- 8 file data tambahan kini tersedia di **akhir Sesi 1** (sebelumnya hanya EOD)
- Mencakup: summary aktivitas transaksi, data indeks, rekapitulasi per tipe investor
- Dampak: peningkatan 88% nilai transaksi Sesi 1, 65% Sesi 2
- Investor aktif harian naik 28% (195K → 250K)

---

## 5. Overnight Gap Risk

### 5.1 Gap Timeline

```
WIB timeline (Senin-Kamis):

15:50 ─── IDX CLOSE ─────────────────────────────────────────── 09:00 ─── IDX OPEN
     │                                                         │
     │  16:00 WIB: LSE opens                                   │
     │  17:30 WIB: Frankfurt closes                            │
     │  22:30 WIB: NYSE opens                                  │
     │  23:00 WIB: NASDAQ trading                              │
     │  05:00 WIB: NYSE closes                                 │
     │  06:30 WIB: Tokyo opens                                 │
     │                                                         │
     │ ← ─ ─ ─ ─ OVERNIGHT GAP (~17 hours) ─ ─ ─ ─ ─ ─ ─ ─ → │
```

### 5.2 Gap Duration Table

| Skenario | Gap Duration | Event Risk |
|----------|-------------|------------|
| **IDX close → US open** | ~6.5 jam | FOMC, US earnings, economic data |
| **IDX close → Europe open** | ~10 menit | Minimal (hampir bersamaan) |
| **US close → IDX open** | ~11.5 jam | Semua overnight US event |
| **Jumat close → Senin open** | ~63 jam | Weekend accumulation |
| **Holiday gap** | Variable | Multi-day accumulation |

### 5.3 Historical Gap Examples (IDX)

| Event | Tanggal | Gap IDX | Penyebab |
|-------|---------|---------|----------|
| **FOMC rate hike** | Jun 2022 | -2.1% opening | Fed +75bps overnight |
| **SVB collapse** | Mar 2023 | -1.8% opening | US banking crisis |
| **COVID-19** | Mar 2020 | -3.5% opening | Global pandemic fear |
| **Fed pivot** | Nov 2023 | +1.5% opening | Fed dovish signal |
| **China stimulus** | Sep 2024 | +1.2% opening | China policy support |

---

## 6. Dampak ke Sistem Trading

### 6.1 Data Latency Impact per Use Case

| Use Case | Max Tolerable Delay | Recommended Source |
|----------|--------------------|--------------------|
| **Eksekusi order live** | < 1 detik | Broker API (real-time) |
| **Stop-loss / take-profit check** | < 5 detik | Broker API |
| **Position monitoring** | < 15 menit | Yahoo Finance (10 min) |
| **Signal generation** | < 15 menit | Yahoo Finance (10 min) |
| **Prediksi IDX opening** | EOD (T-1) | Yahoo Finance global (US close) |
| **Backtest** | T+1 (EOD) | Historical database |
| **Foreign flow analysis** | 1-2 jam post-close | IDX scraper |
| **Cross-market correlation** | 15 menit | Yahoo Finance global |
| **Score computation** | EOD | Database (batch) |

### 6.2 Timezone Handling dalam Code

```python
from datetime import datetime, timezone, timedelta

# IDX timezone
WIB = timezone(timedelta(hours=7))

# Market hours check
def is_idx_open(now: datetime = None) -> bool:
    """Check if IDX is currently open."""
    now = now or datetime.now(WIB)
    now_wib = now.astimezone(WIB)
    
    # Weekend check
    if now_wib.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    
    hour_min = now_wib.hour * 100 + now_wib.minute
    
    # Monday-Thursday
    if now_wib.weekday() < 4:
        return (900 <= hour_min <= 1200) or (1330 <= hour_min <= 1550)
    # Friday
    else:
        return (900 <= hour_min <= 1130) or (1400 <= hour_min <= 1550)

# Global market status
GLOBAL_MARKETS = {
    "US": {"tz": "America/New_York", "open": "09:30", "close": "16:00"},
    "London": {"tz": "Europe/London", "open": "08:00", "close": "16:30"},
    "Tokyo": {"tz": "Asia/Tokyo", "open": "09:00", "close": "15:00"},
    "HongKong": {"tz": "Asia/Hong_Kong", "open": "09:30", "close": "16:00"},
    "Singapore": {"tz": "Asia/Singapore", "open": "09:00", "close": "17:00"},
}
```

### 6.3 Data Timestamp Alignment

```python
def align_global_to_idx(global_data: pd.DataFrame, idx_data: pd.DataFrame) -> dict:
    """Align global market data to IDX trading dates."""
    # Global markets may have different trading days (holidays)
    # Align by date, forward-fill missing global data
    
    idx_dates = set(idx_data.index.date)
    global_dates = set(global_data.index.date)
    
    # Dates only in IDX (no global data — e.g., IDX-specific holiday)
    idx_only = idx_dates - global_dates
    
    # Dates only in global (no IDX — e.g., US holiday while IDX open)
    global_only = global_dates - idx_dates
    
    # Common trading days
    common = idx_dates & global_dates
    
    return {
        "common_days": len(common),
        "idx_only_days": len(idx_only),
        "global_only_days": len(global_only),
        "alignment_pct": len(common) / len(idx_dates) * 100 if idx_dates else 0,
    }
```

---

## 7. Strategi Mitigasi Gap

### 7.1 Overnight Risk Management

| Strategi | Implementasi | Trade-off |
|----------|-------------|-----------|
| **Reduce position before close** | Close 50% position jika overnight risk tinggi | Miss upside gap |
| **Hedge dengan global futures** | Short US futures saat IDX tutup | Cost, complexity |
| **Pre-market global monitoring** | Monitor US/Europe semalam sebelum IDX open | Effort, automation |
| **Gap prediction model** | Score overnight global → predict IDX opening | Model risk |
| **Wider stop-loss** | Set SL wider untuk accommodate gap | Larger risk per trade |
| **No overnight position** | Day trading only | Miss multi-day trends |

### 7.2 Gap Prediction Score

```python
def overnight_gap_prediction(global_data: dict) -> dict:
    """Predict IDX opening direction from overnight global markets."""
    # US market (closes ~05:00 WIB, 5 hours before IDX open)
    sp500_change = global_data.get("sp500_change", 0)
    nasdaq_change = global_data.get("nasdaq_change", 0)
    vix_change = global_data.get("vix_change", 0)
    us_10y_change = global_data.get("us_10y_change", 0)
    dxy_change = global_data.get("dxy_change", 0)
    
    # Weighted score
    score = (
        sp500_change * 0.30 +
        nasdaq_change * 0.20 +
        vix_change * -0.20 +
        us_10y_change * -0.15 +
        dxy_change * -0.15
    ) * 20  # scale to -100..+100
    
    return {
        "predicted_gap": "up" if score > 5 else "down" if score < -5 else "flat",
        "signal_strength": abs(score),
        "score": score,
        "components": {
            "sp500": sp500_change,
            "nasdaq": nasdaq_change,
            "vix": vix_change,
            "us_10y": us_10y_change,
            "dxy": dxy_change,
        },
        "confidence": min(abs(score) / 50, 1.0),
    }
```

### 7.3 Data Source Fallback Chain

```python
DATA_FALLBACK = {
    "idx_realtime": [
        "broker_api",        # Best: real-time, < 1s
        "invezgo_api",       # Good: ~5s delay
        "rapidapi_idx",      # Good: real-time, rate limited
        "yahoo_finance",     # Fallback: 10 min delay
        "google_finance",    # Last resort: 10 min delay
    ],
    "idx_eod": [
        "database",          # Best: local, instant
        "yahoo_finance",     # Fallback: 10 min delay
        "idx_scraper",       # Fallback: 1-2h post-close
    ],
    "global_realtime": [
        "yahoo_finance",     # US: real-time, EU: 15 min
        "google_finance",    # Fallback
    ],
}
```

---

## 8. Implementasi untuk IDX

### 8.1 Pertimbangan Khusus

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **No overlap with US/EU** | Overnight gap risk | Gap prediction + risk management |
| **10 min Yahoo delay** | Tidak untuk eksekusi | Broker API untuk eksekusi, Yahoo untuk monitoring |
| **Yahoo IDX issue (2025+)** | Data bisa delay > 10 min | Fallback ke Google Finance atau broker API |
| **WIB = UTC+7** | Alignment dengan global | Consistent timezone handling di semua code |
| **Jumat short session** | Break lebih panjang | Adjust schedule untuk Jumat |
| **IDX holiday vs global** | Tanggal trading berbeda | Calendar alignment, forward-fill global data |
| **BEI data enhancement** | Data Sesi 1 kini available | Manfaatkan untuk intraday analysis |

### 8.2 Optimal Data Schedule

```python
DATA_SCHEDULE = {
    # Pre-market (06:00-08:59 WIB)
    "global_check": "06:00 WIB",       # Check overnight US/Europe
    "gap_prediction": "08:00 WIB",     # Compute overnight gap score
    "pre_market_scan": "08:30 WIB",    # Scan watchlist signals
    
    # Market hours (09:00-15:50 WIB)
    "price_update": "every 30s",       # During market (Yahoo or broker API)
    "position_monitor": "every 60s",   # Check SL/TP
    "signal_check": "every 5min",      # Decision engine run
    
    # Post-market (16:00-23:59 WIB)
    "eod_data_fetch": "16:30 WIB",     # Fetch EOD data
    "foreign_flow_scrape": "17:00 WIB", # IDX scraper
    "score_compute": "18:00 WIB",      # Batch score computation
    "us_market_monitor": "22:30 WIB",  # Monitor US open
    
    # Overnight (00:00-06:00 WIB)
    "us_close_check": "05:00 WIB",     # US market close
    "backup": "01:00 WIB",             # Database backup
}
```

---

## 9. Checklist Implementasi

### Timezone
- [ ] Consistent WIB (UTC+7) untuk semua IDX data
- [ ] UTC untuk storage dan cross-market comparison
- [ ] DST handling untuk US/Europe markets
- [ ] Market calendar (IDX holidays + global holidays)
- [ ] `is_idx_open()` function untuk schedule

### Data Delay
- [ ] Yahoo Finance: 10 min delay IDX (monitoring only)
- [ ] Broker API: real-time untuk eksekusi
- [ ] Fallback chain: broker → API → Yahoo → Google
- [ ] Yahoo IDX issue awareness (post-2025)
- [ ] BEI Sesi 1 data utilization

### Gap Risk
- [ ] Overnight gap prediction model
- [ ] Pre-market global monitoring
- [ ] Position reduction untuk high overnight risk
- [ ] Wider stop-loss untuk gap-prone stocks
- [ ] Weekend gap awareness

### Cross-Market Alignment
- [ ] Date alignment IDX ↔ global
- [ ] Forward-fill missing global data
- [ ] Holiday calendar sync
- [ ] Lead-lag analysis (US → IDX next day)
- [ ] Asia regional correlation (HK, SG, TH)

### Schedule
- [ ] Pre-market global check (06:00 WIB)
- [ ] Gap prediction (08:00 WIB)
- [ ] Post-market EOD fetch (16:30 WIB)
- [ ] Foreign flow scrape (17:00 WIB)
- [ ] US market monitoring (22:30 WIB)

---

## 9. GMT+7 Local Timezone Awareness

### 9.1 Konteks Aplikasi

Aplikasi ini dijalankan di komputer yang berada di wilayah **GMT+7 (WIB / Indonesia Barat)**. Semua operasi terjadwal harus memperhitungkan perbedaan waktu antara bursa global dan waktu lokal aplikasi.

### 9.2 Aturan Timezone

| Layer | Timezone | Alasan |
|-------|----------|--------|
| **Database storage** | UTC | Konsistensi cross-market, tidak terpengaruh DST |
| **Internal processing** | UTC | Mencegah bug offset saat join data global + IDX |
| **Display ke user** | WIB (UTC+7) | User berada di GMT+7 |
| **Schedule operasi** | WIB (UTC+7) | Intuitive untuk user, align dengan jam IDX |
| **Logging** | UTC + WIB | Dual format untuk debugging: `2026-08-05T03:00:00Z (10:00 WIB)` |

### 9.3 Operasi Terjadwal yang Wajib Memperhitungkan Timezone

Berikut semua operasi aplikasi yang sensitif terhadap waktu dan zona waktu:

| Operasi | Waktu Optimal (WIB) | Pertimbangan Timezone |
|---------|---------------------|----------------------|
| **Fetch OHLCV IDX** | 16:30 (post-close) | IDX tutup 15:50 WIB. Yahoo delay 10 menit. Fetch setelah 16:15 untuk data lengkap. |
| **Fetch OHLCV global** | 06:00 (pre-market IDX) | US tutup 05:00 WIB. EU tutup 00:30 WIB. Asia buka 08:00 WIB. Fetch sebelum IDX open. |
| **Foreign flow scrape** | 17:00 (post-close) | IDX scraper update setelah close. |
| **Broker flow scrape** | 17:30 (post-close) | Broker summary update setelah close + settlement. |
| **Compute scores** | 18:00 (post-close) | Setelah semua data tersedia. Batch processing. |
| **Backtesting** | 19:00-23:00 (off-hours) | CPU-intensive, tidak mengganggu market operations. |
| **PnL testing** | 19:00-23:00 (off-hours) | Same. |
| **Risk management assessment** | 08:00 (pre-market) + 16:00 (post-close) | Pre-market: check overnight gap risk. Post-close: update VaR, drawdown. |
| **Portfolio rebalancing** | 16:30 (post-close) | Setelah EOD data tersedia. |
| **AI/ML auto-adjust** | 20:00 (off-hours) | Retrain LSTM, optimasi weight, walk-forward. CPU/GPU intensive. |
| **Strategy testing** | 21:00 (off-hours) | Walk-forward, Monte Carlo. CPU-intensive. |
| **US market monitoring** | 22:30 (US open) | NYSE buka 21:30 WIB (Mar-Nov, DST) atau 22:30 WIB (Nov-Mar, non-DST). |
| **US market close check** | 05:00 WIB (US close) | NYSE tutup 05:00 WIB (DST) atau 06:00 WIB (non-DST). |
| **Overnight gap prediction** | 06:00 (pre-market) | Setelah US close, sebelum IDX open. |
| **Database backup** | 01:00 (midnight) | Off-peak, tidak mengganggu operasi. |
| **Parquet archive** | 23:00 (off-hours) | Cold storage sync. |

### 9.4 DST (Daylight Saving Time) Handling

US dan Europe mengubah offset UTC 2x per tahun. Aplikasi **wajib** menangani ini:

| Periode | US (NYSE/NASDAQ) | Europe (LSE/FWB) | Implikasi WIB |
|---------|-------------------|-------------------|---------------|
| **Mar - Nov (US DST)** | UTC-4 | UTC+1 (Mar-Oct) | US open: 21:30 WIB, US close: 03:00 WIB |
| **Nov - Mar (US non-DST)** | UTC-5 | UTC+0 (Oct-Mar) | US open: 22:30 WIB, US close: 04:00 WIB |
| **Transition days** | Offset berubah | Offset berubah | Schedule US monitoring harus dinamis |

> **Implementasi production:** Modul `src/market/analysis/cross_market_timezone.py` menggunakan `zoneinfo` (Python 3.9+) untuk deteksi DST yang akurat (mengikuti aturan IANA tzdata — second Sunday of March 02:00 → first Sunday of November 02:00). Fungsi `verify_dst_cutoff()` dipanggil di `daily_signal_cron.py` sebelum signal computation untuk memastikan Wall Street sudah fully closed sebelum global index data (^GSPC, ^VIX, GC=F, CL=F) di-lock untuk LightGBM features.
>
> **Anti look-ahead bias dengan asymmetric lag:** `get_aligned_global_features()` dan `compute_exogenous_features()` menerapkan lag berbeda per ticker: T-0 untuk Asian markets (^N225, ^HSI — close sebelum IDX), T-1 untuk US markets (^GSPC, ^VIX, ^TNX) dan commodities (GC=F, CL=F, HG=F, MTF=F, CPO=F). Konfigurasi lag via `GLOBAL_TICKER_LAGS` dict dan `MARKET_TIMEZONES` metadata.

```python
from market.analysis.cross_market_timezone import (
    verify_dst_cutoff, get_us_close_wib, get_aligned_global_features, get_ticker_lag,
)

# Check apakah Wall Street sudah close (DST-aware)
result = verify_dst_cutoff()
if result.us_market_closed:
    print(f"Wall Street CLOSED ({result.dst_label}) — global data safe")
    print(f"US close: {get_us_close_wib()}")  # "03:00 WIB" (summer) or "04:00 WIB" (winter)
else:
    print(f"Wall Street still OPEN — wait {result.wait_seconds}s")

# Get aligned features at 16:15 WIB
features = get_aligned_global_features(as_of_wib=prediction_time, global_data=data)
# Asian tickers (T-0): nikkei_lag1_ret, hsi_lag1_ret — same-day close
# US tickers (T-1): sp500_lag1_ret, vix_lag1_ret — previous-day close
# Commodities (T-1): gold_lag1_ret, oil_lag1_ret — previous-day settle
```

### 9.5 Konversi Waktu untuk Display

```python
def utc_to_wib(utc_dt: datetime) -> datetime:
    """Convert UTC datetime to WIB (UTC+7) for display."""
    return utc_dt.astimezone(WIB)

def wib_to_utc(wib_dt: datetime) -> datetime:
    """Convert WIB datetime to UTC for storage."""
    return wib_dt.astimezone(timezone.utc)

def format_dual_time(utc_dt: datetime) -> str:
    """Format with both UTC and WIB for logging."""
    wib = utc_dt.astimezone(WIB)
    return f"{utc_dt.isoformat()} ({wib.strftime('%H:%M WIB')})"
```

### 9.6 Schedule Matrix (WIB)

```
WIB:  00    02    04    06    08    10    12    14    16    18    20    22    24
      │     │     │     │     │     │     │     │     │     │     │     │     │
      ░░░░░░░░░░░░░░░░░░░░░░░ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ░░░░░░░░░░░░░░░░░░░░░░
      │     │     │     │     │     │     │     │     │     │     │     │     │
      DB    │     │  Gap  Pre-  │   IDX TRADING    │ Post │ AI/  │ US   │
      Bkp   │     │  Pred  Mkt  │   09:00-15:50    │ Mkt  │ ML   │ Mon  │
            │     │  06:00 Scan │                   │ Fetch│ Adj  │ 22:30│
            │     │             │                   │ 16:30│20:00│      │
            │     │  US Close   │                   │ Score│     │      │
            │     │  05:00      │                   │ 18:00│     │      │

Legend: ▓ = IDX market hours, ░ = off-hours, operations scheduled in gaps
```

### 9.7 Checklist Timezone untuk Aplikasi

- [ ] Semua timestamp di database disimpan dalam UTC
- [ ] Semua display ke user dikonversi ke WIB (UTC+7)
- [ ] Schedule operasi menggunakan WIB sebagai acuan
- [ ] DST handling untuk US market (Mar-Nov offset berubah)
- [ ] DST handling untuk Europe market (Mar-Oct offset berubah)
- [ ] `is_idx_open()` function mengacu pada WIB
- [ ] `is_us_open()` function mengacu pada WIB dengan DST adjustment
- [ ] Logging menggunakan dual format (UTC + WIB)
- [ ] Backtest menggunakan UTC internally, display hasil dalam WIB
- [ ] PnL calculation menggunakan tanggal IDX (WIB), bukan tanggal US
- [ ] Risk assessment pre-market mengacu pada WIB (08:00)
- [ ] Portfolio rebalancing post-close mengacu pada WIB (16:30)
- [ ] AI/ML retraining schedule mengacu pada WIB off-hours (20:00)
- [ ] Database backup schedule mengacu pada WIB midnight (01:00)

---

## Referensi

1. `pustaka/02-pasar-modal-indonesia.md` — IDX trading hours & conventions
2. `pustaka/03-pasar-modal-global.md` — Global market structure
3. `pustaka/22-data-engineering-pipeline.md` — Data pipeline & latency
4. `pustaka/35-multi-asset-cross-market-analysis.md` — Cross-market analysis
5. Yahoo Finance data delays: https://help.yahoo.com/kb/SLN2310.html
6. BEI trading hours: https://bcasekuritas.co.id/en/help/faq/exchange-trading-hours
7. Global market overlap: https://markethours.io/market-overlap
8. Global exchange times: https://blog.itick.net/en/stock-api/global-exchange-times
9. BEI data enhancement: https://www.tempo.co/info-tempo/format-distribusi-data-bei-disempurnakan-transaksi-melejit-2106374
10. `src/trading_system/data/acquisition.py` — Yahoo Finance data fetching
11. `src/trading_system/data/rate_limiter.py` — Rate limiting untuk data fetch

---

> **Catatan:** Aplikasi dijalankan di GMT+7 (WIB). IDX beroperasi di UTC+7 tanpa DST, tutup sebelum Eropa dan AS buka. Semua operasi terjadwal (fetch, backtest, PnL, risk, portfolio, AI/ML, strategy testing) harus mengacu pada waktu WIB lokal dengan memperhitungkan DST untuk US/Europe. Storage UTC, display WIB.
