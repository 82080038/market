# Modul, Engine, dan Data yang Harus Ada

> **Tujuan:** Dokumen ini adalah referensi definitif untuk semua modul, engine, dan data yang **wajib ada** dalam sistem aplikasi pasar modal — mulai dari data layer, analysis layer, decision layer, risk layer, hingga infrastructure. Setiap modul mencakup: tujuan, input, output, fungsi utama, dependensi, dan file implementasi.

---

## Daftar Isi

1. [Arsitektur Layered](#1-arsitektur-layered)
2. [Data Layer](#2-data-layer)
3. [Analysis Layer](#3-analysis-layer)
4. [Intelligence Layer](#4-intelligence-layer)
5. [Sentiment Layer](#5-sentiment-layer)
6. [Risk Layer](#6-risk-layer)
7. [Portfolio Layer](#7-portfolio-layer)
8. [Execution Layer](#8-execution-layer)
9. [Decision & Learning Layer](#9-decision--learning-layer)
10. [Infrastructure Layer](#10-infrastructure-layer)
11. [API Layer](#11-api-layer)
12. [Frontend Layer](#12-frontend-layer)
13. [Database Schema](#13-database-schema)
14. [Data Sources](#14-data-sources)
15. [Engine Registry](#15-engine-registry)
16. [Event Bus](#16-event-bus)
17. [Data Contracts](#17-data-contracts)
18. [Checklist Implementasi](#18-checklist-implementasi)

---

## 1. Arsitektur Layered

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION & COMMAND LAYER                          │
│  Dashboard (Next.js)  │  Engine Monitor (WebSocket)  │  CLI  │  API          │
├──────────────────────────────────────────────────────────────────────────────┤
│                         DECISION & LEARNING LAYER                             │
│  Decision Engine  →  AI Learning Engine  →  Explainable AI Engine              │
├──────────────────────────────────────────────────────────────────────────────┤
│                         RISK & PORTFOLIO LAYER                                │
│  Risk Engine  +  Portfolio Engine  +  Execution Engine                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                         ANALYSIS LAYER                                        │
│  Fundamental │ Technical │ Macro │ Global │ Sentiment │ Corporate Action     │
├──────────────────────────────────────────────────────────────────────────────┤
│                         RELATIONSHIP & INTELLIGENCE LAYER                     │
│  Market Relationship Engine  +  Cross-Asset Correlation Engine                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                         DATA LAYER                                            │
│  Acquisition → Validation → Storage → Catalog → API / Event Bus                │
├──────────────────────────────────────────────────────────────────────────────┤
│                         INFRASTRUCTURE LAYER                                  │
│  Scheduler, Monitoring 24/7, Logging, Backtesting, Paper Trading, Deployment    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Prinsip Inti

1. **Data First** — Setiap data wajib melalui validasi sebelum digunakan
2. **Backtestable First** — Setiap strategi wajib dapat diuji secara historis
3. **Modular & Decoupled** — Setiap engine dapat dikembangkan dan diganti secara independen
4. **Explainable** — Setiap rekomendasi wajib dapat dijelaskan
5. **Risk-Aware** — Risk Engine wajib berjalan sebelum Decision Engine
6. **Continuous Learning** — AI membantu menemukan pola, bukan mengambil alih keputusan

---

## 2. Data Layer

### 2.1 Data Acquisition Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/data/acquisition.py` |
| **Tujuan** | Mengumpulkan data dari berbagai sumber secara otomatis, terjadwal, dan terverifikasi |
| **Input** | Konfigurasi sumber data, jadwal dari Scheduler |
| **Output** | Event `data.raw.*`, raw data di staging area |

#### Komponen Teknis

| Komponen | Fungsi |
|----------|--------|
| **RateLimiter** | Sliding window rate limiting dengan `threading.Lock` (default: 1 call/1 detik) |
| **YahooFinanceAdapter** | Fetch OHLCV dari Yahoo Finance via `yfinance` |
| **IDXScraper** | Scraping idx.co.id untuk foreign flow & broker summary (via `cloudscraper`) |
| **normalize_ohlcv** | Normalisasi DataFrame ke skema standar |

#### Data yang Diambil

| Kategori | Data | Sumber |
|----------|------|--------|
| Saham Indonesia | OHLCV harian | Yahoo Finance (`*.JK`) |
| Saham Global | OHLCV harian | Yahoo Finance (`^GSPC`, `^IXIC`, dll.) |
| Indeks | IHSG, S&P 500, Nasdaq, dll. | Yahoo Finance |
| Forex & Valas | USD/IDR, DXY | Yahoo Finance |
| Komoditas | Oil, Gold, Coal | Yahoo Finance |
| Macro | BI Rate, inflasi, GDP | BPS, BI, FRED |
| Laporan Keuangan | Neraca, laba rugi | Yahoo Finance, BEI |
| Foreign Flow | Net buy/sell asing | idx.co.id scraper |
| Broker Summary | Aktivitas broker | idx.co.id scraper |

#### Fungsi Utama

| Fungsi | Input | Output |
|--------|-------|--------|
| `fetch(source, ticker, range)` | source id, ticker, rentang tanggal | payload mentah + status |
| `normalize(payload, schema)` | payload mentah, skema target | record ternormalisasi |
| `publish(record)` | record ternormalisasi | event ke Event Bus + tulis ke raw_zone |
| `track_metadata(source, status)` | source id, hasil fetch | update tabel `source_health` |

### 2.2 Data Quality Validation Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/data/validation.py` |
| **Tujuan** | Menjamin data yang masuk bersih, konsisten, dan dapat dipercaya |
| **Input** | Event `data.raw.*` dari Acquisition Engine |
| **Output** | `data_quality_score` (0-100), daftar anomali, event `data.clean.*` |

#### Jenis Validasi

| Jenis | Check | Severity |
|------|-------|----------|
| **Completeness** | Missing values, gap harian | Medium |
| **Plausibility** | Harga ≤ 0, low > high, close di luar range | High |
| **Volume Spike** | Volume > 10x median | Low |
| **Gap Detection** | Gap > 5 hari | Low |

#### Skor Kualitas

| Skor | Tindakan | Arti |
|------|----------|------|
| ≥ 90 | `accept` | Data diterima sepenuhnya |
| 70-89 | `flag` | Diterima dengan flag untuk review |
| < 70 | `pause` | Data ditolak, tidak disimpan |

### 2.3 Data Storage

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/data/storage.py` |
| **Tujuan** | Repository utama dengan SQLite (WAL mode) |
| **Engine** | SQLite dengan `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL` |

#### Operasi Utama

| Method | Fungsi |
|--------|--------|
| `save_ohlcv(df)` | Simpan OHLCV dengan INSERT OR REPLACE |
| `load_ohlcv(ticker, start, end, timeframe)` | Muat OHLCV sebagai DataFrame |
| `list_tickers()` | Daftar ticker unik |
| `save_score(ticker, engine, score, breakdown)` | Simpan skor engine |
| `load_scores(ticker, engine)` | Muat skor, diurutkan `as_of` desc |
| `save_relationship(a, b, window, corr, lag)` | Simpan matriks relationship |
| `save_corporate_action(record)` | Simpan aksi korporasi |
| `update_source_health(source, status)` | Upsert status sumber data |
| `audit(event_type, payload, actor)` | Tulis audit log (append-only) |

### 2.4 Modul Data Pendukung

| Modul | File | Fungsi |
|-------|------|--------|
| **Contracts** | `data/contracts.py` | Pydantic v2 data contracts untuk validasi skema |
| **Quality Utils** | `data/quality.py` | Helper perhitungan skor kualitas, deteksi anomali |
| **Seeder** | `data/seeder.py` | Isi database dengan data dummy untuk testing |
| **Archive** | `data/archive.py` | Parquet archive adapter (cold storage) |
| **Rate Limit** | `data/rate_limit.py` | YFinance rate limiter + circuit breaker |
| **IDX Scraper** | `data/idx_scraper.py` | Scraper idx.co.id (cloudscraper bypass) |
| **Import Legacy** | `data/import_legacy.py` | Import data legacy MySQL |
| **Extended Storage** | `data/extended_storage.py` | Akses 14 tabel import MySQL |

---

## 3. Analysis Layer

### 3.1 Technical Analysis Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/analysis/technical.py` |
| **Class** | `TechnicalAnalysisEngine` |
| **Tujuan** | Menganalisis perilaku harga dan volume secara kuantitatif |
| **Input** | OHLCV harian dari Data Storage |
| **Output** | `technical_score` (0-100) + breakdown per komponen |

#### Indikator yang Dihitung

| Indikator | Periode | Fungsi |
|-----------|---------|--------|
| Moving Average | 20, 50 hari | Identifikasi tren |
| ADX | 14 hari | Kekuatan tren |
| RSI | 14 hari | Momentum overbought/oversold |
| MACD | 12, 26, 9 | Konfirmasi tren dan sinyal |
| ATR | 14 hari | Volatilitas |
| Bollinger Bands | 20 hari, 2 std | Range normal harga |
| Volume SMA | 20 hari | Baseline volume |
| Volume Ratio | — | Volume relatif terhadap rata-rata |
| Volatility (annualized) | 20 hari | Rezim volatilitas |

#### Klasifikasi Tren

| Kondisi | Label |
|---------|-------|
| MA20 > MA50 dan close > MA20 | Uptrend |
| MA20 < MA50 dan close < MA20 | Downtrend |
| Kondisi lainnya | Sideways |

#### Volume Profile

| Komponen | Deskripsi |
|----------|-----------|
| **POC (Point of Control)** | Harga dengan volume tertinggi |
| **VAH (Value Area High)** | Batas atas 70% volume |
| **VAL (Value Area Low)** | Batas bawah 30% volume |

#### Perhitungan Skor (0-100)

| Komponen | Logika | Range |
|----------|--------|-------|
| Trend | Uptrend=25, Sideways=12, Downtrend=0 | 0-25 |
| RSI | (RSI - 30) * (25/40), clamped | 0-25 |
| MACD | MACD > Signal = 25, else 0 | 0-25 |
| Volatility | max(0, 25 - vol*100) | 0-25 |
| Volume | min(25, vol_ratio * 12.5) | 0-25 |

### 3.2 Fundamental Analysis Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/analysis/fundamental.py` |
| **Class** | `FundamentalAnalysisEngine` |
| **Tujuan** | Menilai kesehatan dan valuasi perusahaan berdasarkan laporan keuangan |
| **Input** | Laporan keuangan dari Yahoo Finance / fallback ke `saham_snapshot` / `idx_financial_statements` |
| **Output** | `fundamental_score` (0-100) + breakdown rasio |

#### Rasio yang Dihitung

| Kategori | Rasio |
|----------|-------|
| **Valuasi** | PER, PBV, PS, Dividend Yield |
| **Profitabilitas** | ROE, ROA, Gross/Operating/Net Margin |
| **Leverage** | DER, Debt-to-Asset |
| **Growth** | Revenue Growth, EPS Growth |

#### Fallback Chain

1. Yahoo Finance (`t.info`) — sumber utama
2. `saham_snapshot` table — data import MySQL (PER/PBV/ROE/DER/market_cap)
3. `idx_financial_statements` table — laporan keuangan tahunan/kuartalan
4. Jika semua tidak tersedia → nilai netral 12.5, status `"warning"`

#### Perhitungan Skor (0-100)

| Komponen | Logika | Range |
|----------|--------|-------|
| PER | min(25, max(0, 25 - PER/5)) | 0-25 |
| PBV | min(25, max(0, 25 - PBV/0.4)) | 0-25 |
| ROE | min(25, ROE) | 0-25 |
| DER | max(0, 25 - DER*25) | 0-25 |
| Growth | min(25, max(0, 12.5 + avg(eps_g, rev_g))) | 0-25 |

### 3.3 Macro Economic Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/analysis/macro.py` |
| **Class** | `MacroEconomicEngine` |
| **Tujuan** | Memantau dan mengukur dampak kondisi makroekonomi |
| **Input** | Data makro dari Yahoo Finance (US10Y, Gold, Oil, USD/IDR, DXY) |
| **Output** | `macro_score` (0-100) + regime klasifikasi |

#### Klasifikasi Rezim

| Rezim | Kondisi | Dampak |
|-------|---------|--------|
| Tightening | US10Y naik | Tekanan valuasi |
| Easing | US10Y turun | Dukungan valuasi |
| Growth | Oil naik, USD/IDR turun | Pertumbuhan ekonomi |
| Slowdown | Oil turun, USD/IDR naik | Perlambatan ekonomi |
| Neutral | Kondisi lainnya | Tidak ada sinyal kuat |

#### Perhitungan Skor (0-100)

| Komponen | Logika | Range |
|----------|--------|-------|
| US10Y | max(0, 25 - yield * 2.5) | 0-25 |
| Gold | 25 jika chg < 5%, 12.5 if < 10%, 0 if ≥ 10% | 0-25 |
| Oil | 25 jika 60-90, else 15 | 0-25 |
| USD/IDR | 25 jika chg < 0, else 12.5 | 0-25 |

### 3.4 Global Market Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/analysis/global_market.py` |
| **Class** | `GlobalMarketEngine` |
| **Tujuan** | Memantau bursa utama dunia dan mengukur dampaknya ke Indonesia |
| **Input** | OHLCV 7 indeks global dari Yahoo Finance |
| **Output** | `global_score` (0-100) |

#### Indeks yang Dipantau

| Wilayah | Indeks | Ticker |
|---------|--------|--------|
| Amerika | S&P 500 | `^GSPC` |
| Amerika | Nasdaq | `^IXIC` |
| Amerika | Dow Jones | `^DJI` |
| Tiongkok | Hang Seng | `^HSI` |
| Asia | Nikkei 225 | `^N225` |
| Eropa | FTSE 100 | `^FTSE` |
| Eropa | DAX 40 | `^GDAXI` |

#### Perhitungan Skor (0-100)

| Komponen | Logika | Range |
|----------|--------|-------|
| Above MA50 | (jumlah di atas MA50 / total) * 50 | 0-50 |
| Above MA200 | (jumlah di atas MA200 / total) * 50 | 0-50 |

### 3.5 Advanced Technical Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/analysis/advanced_technical.py` |
| **Tujuan** | Indikator teknikal lanjutan (Ichimoku, Stochastic, Williams %R) |

### 3.6 Analysis Pipeline (Orkestrator)

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/analysis/pipeline.py` |
| **Class** | `AnalysisPipeline` |
| **Tujuan** | Orkestrasi eksekusi semua engine analisis secara berurutan |

#### Alur `compute(ticker, period)`

1. **Ensure OHLCV** — Pastikan data tersedia (fetch jika belum)
2. **Technical** — Load OHLCV, panggil `analyze()`
3. **Fundamental** — Fetch data fundamental, panggil `analyze()`
4. **Macro** — Panggil `analyze(period)`
5. **Global** — Panggil `analyze(period)`
6. **Relationship** — Panggil `compute(ticker)`
7. **Corporate** — Panggil `fetch(ticker)`
8. **Sentiment** — Panggil `compute(ticker)`
9. **Save Scores** — Simpan semua skor ke database
10. **Return** — Dictionary dengan semua skor dan detail

### 3.7 Modul Analysis Tambahan

| Modul | File | Fungsi |
|-------|------|--------|
| **Regime Detection** | `analysis/regime.py` | Deteksi rezim pasar (uptrend/downtrend/sideways) |
| **Enhanced Regime** | `analysis/enhanced_regime.py` | HMM-based regime detection |
| **Cross-Asset** | `analysis/cross_asset.py` | Analisis cross-asset |
| **Lead-Lag** | `analysis/lead_lag.py` | Analisis lead-lag antar aset |
| **Factor Engine** | `analysis/factor_engine.py` | Factor-based analysis |
| **Factor Screener** | `analysis/factor_screener.py` | Screener berbasis faktor |
| **Screener** | `analysis/screener.py` | Stock screener dengan preset filter |
| **Manipulation** | `analysis/manipulation.py` | Deteksi manipulasi pasar |
| **No-Trade Zone** | `analysis/no_trade.py` | Deteksi zona no-trade |
| **Red Flags** | `analysis/red_flags.py` | Deteksi red flag saham |
| **Order Book** | `analysis/order_book.py` | Analisis order book |
| **Attribution** | `analysis/attribution.py` | Performance attribution |
| **Alpha Composer** | `analysis/alpha_composer.py` | Alpha composition |
| **Alpha Validation** | `analysis/alpha_validation.py` | Alpha validation |
| **World Monitor** | `analysis/world_monitor.py` | Global market monitor |
| **Liquidity Filter** | `analysis/liquidity_filter.py` | Filter likuiditas |
| **Pattern Reliability** | `analysis/pattern_reliability.py` | Skor reliabilitas pola chart |

---

## 4. Intelligence Layer

### 4.1 Market Relationship Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/analysis/relationship.py` |
| **Class** | `MarketRelationshipEngine` |
| **Tujuan** | Menghitung pengaruh antarpasar secara kuantitatif |
| **Input** | OHLCV saham lokal + 13 aset pembanding (7 indeks global + 5 proxy makro + 1 IHSG) |
| **Output** | `relationship_score` (0-100) + relationship matrix |

#### Metode

| Metode | Deskripsi |
|--------|-----------|
| **Rolling Correlation** | Korelasi Pearson return harian, window 60 hari |
| **Lag Analysis** | Uji lag -5 hingga +5 hari untuk korelasi tertinggi |

#### Aset Pembanding (13 total)

| Kategori | Aset | Ticker |
|----------|------|--------|
| Indeks Global | S&P 500 | `^GSPC` |
| Indeks Global | Nasdaq | `^IXIC` |
| Indeks Global | Dow Jones | `^DJI` |
| Indeks Global | Hang Seng | `^HSI` |
| Indeks Global | Nikkei 225 | `^N225` |
| Indeks Global | FTSE 100 | `^FTSE` |
| Indeks Global | DAX 40 | `^GDAXI` |
| Proxy Makro | US 10Y Yield | `^TNX` |
| Proxy Makro | Gold | `GC=F` |
| Proxy Makro | Crude Oil | `CL=F` |
| Proxy Makro | USD/IDR | `IDR=X` |
| Proxy Makro | DXY | `DX-Y.NYB` |
| Benchmark | IHSG | `^JKSE` |

#### Output

```json
{
  "score": 45.67,
  "window": 60,
  "relationships": [
    {"asset": "SP500", "ticker": "^GSPC", "correlation": 0.32, "lag": 0},
    {"asset": "GOLD", "ticker": "GC=F", "correlation": -0.15, "lag": 2}
  ]
}
```

**Influence Score** = rata-rata |correlation| * 100. Skor tinggi = sangat dipengaruhi pasar global.

### 4.2 Corporate Action Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/corporate/actions.py` |
| **Class** | `CorporateActionEngine` |
| **Tujuan** | Memantau aksi korporasi yang memengaruhi valuasi, harga, dan posisi |

#### Aksi Korporasi yang Dilacak

| Jenis | Sumber | Unit |
|-------|--------|------|
| Stock Split | `t.splits` | Rasio (mis. 2:1 = 2.0) |
| Dividend | `t.dividends` | IDR per share |
| Rights Issue | Pengumuman BEI | — |
| Share Buyback | Pengumuman BEI | — |
| Akuisisi/Merger | Pengumuman BEI | — |
| Delisting/IPO | BEI | — |

#### Adjustment Factor

- **Split:** Harga sebelum ex-date dikalikan rasio split
- **Dividend:** `price / (price - dividend)`

---

## 5. Sentiment Layer

### 5.1 Sentiment Engine (NLP — Indonesian News)

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/sentiment/engine.py` |
| **Class** | `SentimentEngine` |
| **Tujuan** | Analisis berita keuangan Indonesia menggunakan NLP lexicon-based |
| **Input** | RSS feed Bisnis.com, Kontan, CNBC Indonesia |
| **Output** | `sentiment_score` (0-100) |

#### Indonesian Sentiment Lexicon

| Kategori | Kata Contoh | Jumlah |
|----------|-------------|--------|
| **Positive** | naik, untung, bullish, beli, tumbuh, optimis, rally, profit, dividen | 40+ |
| **Negative** | turun, rugi, bearish, jual, lemah, jatuh, anjlok, crash, fraud | 40+ |
| **Ambiguous** | rugi, cut loss, koreksi, adjustment | 4 (konteks-dependent) |

#### Negation Detection

Deteksi kata "tidak", "bukan", "jangan" sebelum kata sentiment untuk membalikkan polaritas.

### 5.2 Foreign Flow Sentiment

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/sentiment/foreign_flow.py` |
| **Tujuan** | Analisis pola aliran modal asing (proxy dari OHLCV) |
| **Output** | Score 0-100, label: `accumulation` / `distribution` |

### 5.3 Broker Summary Sentiment

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/sentiment/broker_summary.py` |
| **Tujuan** | Track smart money dari IDX broker summary harian |

#### Klasifikasi Broker

| Tipe | Broker Contoh |
|------|---------------|
| **Smart Money (foreign)** | CLSA, CS, JPM, UBS, MS, GS, DB, CITI, BNP, BARCAP, MACQ, NOMURA |
| **Retail Brokers** | POIN, IPOT, STOCK, MINNA, MULIA, PHILLIP |

### 5.4 Social Media Sentiment

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/sentiment/social_media.py` |
| **Tujuan** | Deteksi sentiment real-time dari social media |
| **Sumber** | Reddit (r/IndonesiaInvesting, r/saham), X/Twitter |

### 5.5 Google Trends Sentiment

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/sentiment/google_trends.py` |
| **Tujuan** | Search interest sebagai leading indicator |
| **API** | `pytrends` (gratis) |

### 5.6 Integrasi Pipeline Sentiment

`SentimentEngine.compute(ticker)` menggabungkan **6 sumber** dengan bobot:

| Sumber | Bobot | Tipe |
|--------|-------|------|
| Foreign Flow | 0.25 | Real-time proxy dari OHLCV |
| Broker Summary (Smart Money) | 0.20 | IDX broker summary |
| IDX Historical Sentiment | 0.20 | Pre-computed dari `idx_sentiment_data` |
| Social Media (Reddit + X) | 0.15 | Real-time NLP |
| Google Trends | 0.10 | Leading indicator |
| News NLP (Indonesian RSS) | 0.10 | Confirmation signal |

Bobot dinormalisasi berdasarkan sumber yang aktif.

---

## 6. Risk Layer

### 6.1 Risk Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/risk/engine.py` |
| **Class** | `RiskEngine` |
| **Tujuan** | Melindungi modal sebelum sistem memberikan sinyal |
| **Input** | Kandidat sinyal, posisi portofolio, data volatilitas |
| **Output** | `position_size`, `stop_loss`, `take_profit`, `risk_flags` |

#### Komponen Risk

| Komponen | Deskripsi |
|----------|-----------|
| **Position Sizing** | Fixed fractional, risk 1% modal per trade |
| **Stop Loss** | ATR-based: `stop = price - 1.5 * ATR` |
| **Take Profit** | Risk-reward 1:2: `tp = price + 2 * stop_distance` |
| **Likuiditas** | Cek `target_value > adv_value * 1%` → flag `LIQUIDITY_LOW` |
| **Volatilitas** | Vol annualized > 50% → flag `HIGH_VOLATILITY` |

#### Output

```json
{
  "ticker": "BBCA.JK",
  "last_price": 8750.00,
  "atr": 125.50,
  "position_size": 0.085,
  "stop_loss": 8561.75,
  "take_profit": 9126.50,
  "slippage": 0.0005,
  "risk_flags": [],
  "avg_daily_volume": 12500000
}
```

### 6.2 Modul Risk Tambahan

| Modul | File | Fungsi |
|-------|------|--------|
| **Enhanced Risk** | `risk/enhanced_risk.py` | Enhanced risk metrics |
| **Circuit Breaker** | `risk/circuit_breaker.py` | Circuit breaker otomatis saat drawdown melewati threshold |
| **Slippage Model** | `risk/slippage.py` | Slippage dinamis berdasarkan order size, ADV, time of day |
| **Correlation Sizing** | `risk/corr_sizing.py` | Position sizing berbasis korelasi |
| **Cost Model** | `risk/costs.py` | Model biaya transaksi IDX |
| **Kelly Criterion** | `risk/kelly.py` | Kelly fraction (conservative) |
| **Expectancy** | `risk/expectancy.py` | Expected value per trade |

---

## 7. Portfolio Layer

### 7.1 Portfolio Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/portfolio/engine.py` |
| **Tujuan** | Mengelola alokasi modal berdasarkan rekomendasi |
| **Input** | Rekomendasi dari Decision Engine |
| **Output** | Order list untuk eksekusi |

### 7.2 Performance Analytics

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/portfolio/performance.py` |
| **Class** | `PerformanceAnalytics` |
| **Tujuan** | Menghitung metrik kinerja portofolio |

#### Metrik yang Dihitung

| Metrik | Rumus |
|--------|-------|
| Total Return | `equity[-1] / equity[0] - 1` |
| Sharpe Ratio | `excess.mean() / returns.std() * sqrt(252)` |
| Max Drawdown | `min((equity - cummax) / cummax)` |
| Win Rate | `wins / total_trades` |
| Profit Factor | `wins.sum() / |losses.sum()|` |
| Average Win | `wins.mean()` |
| Average Loss | `losses.mean()` |
| Equity Curve | Time series nilai equity |

### 7.3 Portfolio Rebalancer

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/portfolio/rebalancer.py` |
| **Class** | `PortfolioRebalancer` |
| **Tujuan** | Menyeimbangkan portofolio ke bobot target |

#### Konfigurasi

```bash
REBALANCE_ENABLED=true
REBALANCE_FREQUENCY=monthly
REBALANCE_TARGET_WEIGHTS={"BBCA.JK": 0.4, "TLKM.JK": 0.3, "ASII.JK": 0.3}
```

#### Method

| Method | Fungsi |
|--------|--------|
| `compute_drift()` | Hitung selisih bobot aktual vs target |
| `rebalance()` | Eksekusi order untuk menyeimbangkan (threshold default 5%) |
| Runtime toggle | `POST /api/rebalance/toggle` tanpa restart |

---

## 8. Execution Layer

### 8.1 Execution Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/execution/engine.py` |
| **Class** | `ExecutionEngine` |
| **Tujuan** | Menghitung biaya transaksi realistis dan memeriksa kelayakan order |

#### Komponen Biaya IDX

| Komponen | Beli | Jual |
|----------|------|------|
| Broker fee | 0.15% | 0.15% |
| Levy bursa | 0.00043% | 0.00043% |
| PPh final | — | 0.1% |

#### Slippage Dinamis

| Rasio order/ADV | Slippage |
|-----------------|----------|
| < 0.1% | 0.05% (default) |
| 0.1%-1% | 0.10% (2x default) |
| > 1% | 0.20% (4x default) |

### 8.2 Automated Execution Engine (Robot Trader)

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/execution/automated.py` |
| **Class** | `AutomatedExecutionEngine` |
| **Tujuan** | Robot trader: baca sinyal, hitung sizing, eksekusi otomatis, monitor SL/TP |

#### Mode Operasi

| Mode | Env Var | Perilaku |
|------|---------|----------|
| **Monitoring** | `AUTO_TRADE_ENABLED=false` (default) | Log sinyal, tidak eksekusi |
| **Eksekusi** | `AUTO_TRADE_ENABLED=true` | Eksekusi BUY/SELL otomatis |

#### Method

| Method | Fungsi |
|--------|--------|
| `process_signal(ticker)` | Eksekusi satu ticker: decision → risk → order |
| `monitor_positions()` | Cek SL/TP/Trailing untuk semua posisi terbuka |
| `run_once(tickers)` | Satu siklus lengkap untuk list ticker |
| `run_loop(tickers, interval)` | Loop berkelanjutan |

### 8.3 Modul Execution Tambahan

| Modul | File | Fungsi |
|-------|------|--------|
| **Interface** | `execution/interface.py` | Abstract base class `TradingInterface` |
| **Paper Execution** | `execution/paper_execution.py` | Simulasi eksekusi untuk paper trading |
| **Real Execution** | `execution/real_execution.py` | Eksekusi real via broker API |
| **Broker Adapter** | `execution/broker_adapter.py` | Adapter untuk broker (Mock + Sinarmas/BNI) |
| **Tax** | `execution/tax.py` | PPh final 0.1% untuk sell |
| **Factory** | `execution/__init__.py` | `get_execution_engine()` → paper or real |

---

## 9. Decision & Learning Layer

### 9.1 Decision Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/decision/engine.py` |
| **Class** | `DecisionEngine` |
| **Tujuan** | Menggabungkan skor dari semua engine menjadi rekomendasi yang dapat dieksekusi |
| **Input** | Skor dari 6 engine: technical, fundamental, macro, global, relationship, sentiment |
| **Output** | `action` (BUY/HOLD/WATCHLIST/AVOID), `conviction_score` (0-100), `position_size`, `entry/sl/tp` |

#### Bobot Default

```python
DEFAULT_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.25,
    "macro": 0.15,
    "global": 0.15,
    "relationship": 0.10,
    "sentiment": 0.15,
}
```

#### Regime Filter

| Rezim | Penyesuaian |
|-------|-------------|
| Tightening | macro * 0.8, technical * 0.9 |
| Easing | macro * 1.1 (max 100), fundamental * 1.05 (max 100) |
| Lainnya | Tidak ada penyesuaian |

#### Logika Keputusan

```
Jika HIGH_VOLATILITY atau LIQUIDITY_LOW dalam risk_flags:
    Jika conviction < 60: AVOID
Jika conviction >= 70: BUY
Jika conviction >= 55: WATCHLIST
Jika conviction >= 40: HOLD
Jika conviction < 40: AVOID
```

#### Conviction Score

```
conviction = sum(score[k] * weight[k]) / sum(weight[k])
```

Weighted average, hanya menggunakan bobot untuk engine yang memiliki skor (weight redistribution).

### 9.2 AI Learning Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/ai_learning/engine.py` |
| **Class** | `AILearningEngine` |
| **Tujuan** | Optimasi factor weights secara dinamis berdasarkan regime, konsistensi, dan data coverage |

#### Regime-Specific Weights

```python
REGIME_WEIGHTS = {
    "easing": {"technical": 0.15, "fundamental": 0.30, "macro": 0.20, ...},
    "tightening": {"technical": 0.25, "fundamental": 0.15, "macro": 0.25, ...},
    "risk_off": {"technical": 0.10, "fundamental": 0.20, "macro": 0.25, ...},
    "neutral": None,  # Uses DEFAULT_WEIGHTS
}
```

#### Consistency Adjustment

| Kondisi | Adjustment |
|---------|------------|
| Mean ≥ 60 + std < 15 | weight × 1.15 (reliable) |
| Mean ≥ 50 + std < 20 | weight × 1.05 |
| Mean < 40 atau std > 25 | weight × 0.80 (unreliable) |
| No data | weight × 0.85 |

#### Linear Regression Training

1. Ambil historical scores dan OHLCV
2. Compute forward return: `next_close / close - 1`
3. Pivot scores: satu row per date, kolom = engine scores
4. Standardize features dengan `StandardScaler`
5. Train `LinearRegression`: X = scores, y = forward return
6. Normalize coefficients: `np.maximum(coef, 0)` (clip negative, bukan `np.abs`)
7. Simpan ke database

### 9.3 Modul AI Learning Tambahan

| Modul | File | Fungsi |
|-------|------|--------|
| **Deep Learning** | `ai_learning/deep_learning.py` | LSTM, Transformer models |
| **Ensemble** | `ai_learning/ensemble.py` | Ensemble model |
| **Labeling** | `ai_learning/labeling.py` | Labeling engine untuk supervised learning |
| **Model Registry** | `ai_learning/model_registry.py` | Registry model terlatih |
| **Purged TSS** | `ai_learning/purged_tss.py` | Purged TimeSeriesSplit (anti look-ahead) |
| **Walk-Forward** | `ai_learning/walk_forward.py` | Walk-forward optimization |

### 9.4 Explainable AI Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/xai/engine.py` |
| **Class** | `ExplainableAIEngine` |
| **Tujuan** | Memberikan alasan yang jelas untuk setiap rekomendasi |

#### Output

| Komponen | Deskripsi |
|----------|-----------|
| **Narrative** | Teks penjelasan natural language |
| **Top Factors** | 3 faktor dengan skor tertinggi |
| **Confidence Interval** | `[conviction - 10, conviction + 10]` |
| **Risk Summary** | Daftar risk flags |
| **Counter Scenarios** | 2 skenario alternatif yang dapat mengubah rekomendasi |

---

## 10. Infrastructure Layer

### 10.1 Backtesting Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/backtest/engine.py` |
| **Class** | `BacktestEngine` |
| **Tujuan** | Menguji strategi trading secara historis dengan biaya realistis |

#### Cost Model

```python
buy_cost_pct = buy_fee + levy + slippage    # 0.20043%
sell_cost_pct = sell_fee + levy + slippage  # 0.30043%
```

#### Strategi

| Strategi | File | Deskripsi |
|----------|------|-----------|
| **BuyAndHold** | `backtest/strategies.py` | Beli di awal, jual di akhir |
| **MovingAverageCrossover** | `backtest/strategies.py` | Fast MA > Slow MA → BUY |
| **ConvictionStrategy** | `backtest/strategies.py` | Replay skor historis, logika Decision Engine |

#### Metrik (15 total)

| Metrik | Rumus |
|--------|-------|
| Total Return | `equity[-1] / equity[0] - 1` |
| CAGR | `(equity[-1] / equity[0])^(1/years) - 1` |
| Max Drawdown | `min((equity - cummax) / cummax)` |
| Sharpe Ratio | `excess.mean() / returns.std() * sqrt(252)` |
| Sortino Ratio | `excess.mean() / downside.std() * sqrt(252)` |
| Calmar Ratio | `CAGR / |max_drawdown|` |
| Win Rate | `wins / total_trades` |
| Profit Factor | `wins.sum() / |losses.sum()|` |
| Average Win | `wins.mean()` |
| Average Loss | `losses.mean()` |
| Expectancy | `trades.pnl.mean()` |
| Volatility | `returns.std() * sqrt(252)` |
| Beta | `cov(returns, benchmark) / var(benchmark)` |
| Alpha | `returns.mean() - rf - beta * (benchmark.mean() - rf)` |
| Exposure Time | `n_days / 252` |

#### Modul Backtest Tambahan

| Modul | File | Fungsi |
|-------|------|--------|
| **Metrics** | `backtest/metrics.py` | Monte Carlo, Walk-Forward |

### 10.2 Paper Trading Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/paper_trading/engine.py` |
| **Class** | `PaperTradingEngine` |
| **Tujuan** | Simulasi order dari rekomendasi dengan harga pasar tanpa uang sungguhan |

#### Alur `simulate(ticker)`

1. Decision Engine → rekomendasi
2. Portfolio Engine → order
3. Execution Engine → feasibility check
4. Execution Engine → simulate fill (slippage, fees, net value)
5. Return hasil lengkap

### 10.3 Monitoring Engine

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/monitoring/engine.py` |
| **Class** | `MonitoringEngine` |
| **Tujuan** | Health check sederhana seluruh engine dan sumber data |

#### Output `health()`

| Komponen | Isi |
|----------|-----|
| Source Health | Status semua sumber data |
| Tickers in DB | Daftar ticker tersimpan |
| Score Count | Jumlah skor yang telah dihitung |
| Alerts | Daftar sumber dengan status bukan "ok" |

---

## 11. API Layer

### 11.1 FastAPI Application

| Aspek | Detail |
|-------|--------|
| **File** | `src/trading_system/api/app.py` |
| **Framework** | FastAPI + Uvicorn ASGI |
| **Port** | 8000 |
| **Total Endpoints** | 88 (86 REST + 2 WebSocket) |

#### Middleware

| Middleware | Fungsi |
|------------|--------|
| **Correlation ID** | `X-Correlation-ID` header untuk observability |
| **API Key Auth** | `X-API-Key` header, `secrets.compare_digest` |
| **Rate Limiting** | 60 req/min per IP, cleanup otomatis |
| **SanitizedJSONResponse** | NaN/Inf → `null` (RFC 7159 compliance) |

#### Endpoint Kategori

| Kategori | Jumlah | Contoh Endpoint |
|----------|--------|-----------------|
| **System & Data** | 6 | `GET /api/health`, `GET /api/tickers`, `POST /api/fetch` |
| **Analysis & Decision** | 7 | `GET /api/scores/{ticker}`, `GET /api/recommend/{ticker}` |
| **Execution & Orders** | 8 | `GET /api/positions`, `POST /api/execution/run` |
| **Portfolio & Rebalance** | 4 | `POST /api/rebalance`, `GET /api/rebalance/status` |
| **Performance** | 3 | `GET /api/performance`, `POST /api/performance/snapshot` |
| **Watchlist** | 4 | `GET /api/watchlist`, `POST /api/watchlist/{ticker}` |
| **AI Learning** | 4 | `GET /api/factor-weights/{ticker}`, `POST /api/ai/train` |
| **Risk** | 4 | `GET /api/risk/{ticker}`, `GET /api/risk/daily` |
| **Audit & System State** | 4 | `GET /api/audit`, `PUT /api/system-state/{key}` |
| **CRUD Delete** | 8 | `DELETE /api/data/{ticker}`, `DELETE /api/scores/{ticker}` |
| **Backtest** | 3 | `POST /api/backtest`, `POST /api/backtest/monte-carlo` |
| **Simulation & Monitor** | 3 | `POST /api/paper-trade`, `GET /api/monitor` |
| **Extended Data** | 14 | `GET /api/extended/snapshot/{ticker}`, dll. |
| **Replay** | 2 | `GET /api/replay/list`, `GET /api/replay/{ticker}` |
| **WebSocket** | 1 | `ws://host:8000/ws/live` |

---

## 12. Frontend Layer

### 12.1 Teknologi

| Komponen | Teknologi |
|----------|-----------|
| Framework | Next.js 16 (App Router), React 19, TypeScript |
| Styling | TailwindCSS v4 |
| Chart Finansial | TradingView Lightweight Charts, Recharts |
| Real-time | WebSocket |
| Data Fetching | TanStack Query (React Query) |

### 12.2 Halaman

| Halaman | Path | Fungsi |
|---------|------|--------|
| Home | `/` | Redirect ke dashboard |
| Dashboard | `/` | Analisis saham lengkap |
| Engine Monitor | `/engines` | Monitor status engine real-time (WebSocket) |
| Backtest | `/backtest` | Backtest + Monte Carlo + Walk-Forward |
| Portfolio | `/portfolio` | Alokasi portofolio, posisi, exposure |
| Audit | `/audit` | Audit log untuk traceability |
| Replay | `/replay` | Replay simulation hasil backtest |

---

## 13. Database Schema

### 13.1 Tabel Inti (SQLite WAL mode)

| # | Tabel | Primary Key | Ditulis oleh | Dibaca oleh |
|---|-------|-------------|--------------|-------------|
| 1 | `ohlcv` | ticker, timestamp, timeframe | Acquisition/Validation | Technical, Fundamental, Backtest |
| 2 | `source_health` | source | Acquisition | Monitoring |
| 3 | `audit_log` | event_id (auto) | Semua engine | XAI, Compliance |
| 4 | `scores` | ticker, engine, as_of | Semua Analysis Engine | Decision, XAI |
| 5 | `relationship_matrix` | asset_a, asset_b, window | Relationship Engine | Decision, XAI |
| 6 | `corporate_actions` | ticker, action_type, ex_date | Corporate Action Engine | Fundamental, Technical, Portfolio |
| 7 | `news` | news_id | Acquisition | Sentiment Engine |
| 8 | `positions` | id (auto) | Execution Engine | Portfolio, Risk |
| 9 | `orders` | id (auto) | Execution Engine | Performance, AI Learning |
| 10 | `system_state` | key | API | API, Frontend |
| 11 | `equity_snapshots` | id (auto) | Performance Analytics | AI Learning, Frontend |
| 12 | `watchlist` | id (auto) | API | Frontend |
| 13 | `ai_weights` | id (auto) | AI Learning Engine | Decision Engine |
| 14 | `daily_risk_metrics` | date | Risk Engine | API, Frontend |
| 15 | `render_log` | ticker, table_name | Archive | Monitoring |
| 16 | `data_watermark` | ticker, table_name | Acquisition | Monitoring, Scheduler |

### 13.2 Tabel Extended (D1-D31, Import MySQL)

| # | Tabel | Primary Key | Data |
|---|-------|-------------|------|
| 17 | `instrument_master` | ticker | 992 tickers (951 aktif: 928 equity + 23 non-equity) |
| 18 | `fundamental_data` | ticker, date, source | 991 rows |
| 19 | `macro_data` | series_name, date, source | 10,036 rows |
| 20 | `foreign_flow` | ticker, date, source | 103,046 rows |
| 21 | `broker_flow` | ticker, date, broker, source | 15,830 rows |
| 22 | `policy_events` | id (auto) | 179 rows |
| 23 | `dividends` | ticker, ex_date, source | 5,974 rows |
| 24 | `sector_master` | id (auto) | Master sektor |
| 25 | `market_calendar` | date | 365 rows |
| 26 | `fear_greed` | id (auto) | 466 rows |
| 27 | `external_events` | id (auto) | 119 rows |
| 28 | `esg_scores` | id (auto) | 164 rows |
| 29 | `corporate_governance` | id (auto) | GCG scores |
| 30 | `stock_personality` | id (auto) | 944 rows |
| 31 | `trade_journal` | id (auto) | Trade log |
| 32 | `pattern_analysis` | id (auto) | 2,386 rows |
| 33 | `valuation_cache` | ticker, date, method, source | DCF/relative |
| 34 | `technical_indicators` | ticker, date, indicator, timeframe, source | 11,136 rows |
| 35 | `trading_suspensions` | id (auto) | Suspend/delisting |

### 13.3 Tabel Extended Storage (14 tabel import MySQL)

| Tabel | Fungsi |
|-------|--------|
| `saham_snapshot` | Snapshot harga + PER/PBV/ROE/DER |
| `shareholders` | Data pemegang saham |
| `company_directors` | Data direksi & komisaris |
| `broker_summary` | Ringkasan aktivitas broker |
| `pattern_reliability` | Win rate historis pola chart |
| `pattern_candidates` | Kandidat pola terdeteksi |
| `advanced_features` | Order flow, volume profile, anomali |
| `ai_scores_history` | Historis skor AI dengan breakdown |
| `idx_sentiment_data` | Sentimen historis IDX (212K rows) |
| `idx_market_indices` | Data indeks pasar (JCI, sektoral) |
| `idx_financial_statements` | Laporan keuangan tahunan/kuartalan |
| `idx_social_media_sentiment` | Post media sosial + sentimen |
| `idx_stock_splits` | Riwayat stock split |
| `idx_quarterly_earnings` | Data laba kuartalan |

### 13.4 Parquet Storage (Cold Archive)

| Direktori | Env Var | Default | Isi |
|-----------|---------|---------|-----|
| **Raw** | `DATA_RAW_DIR` | `/media/petrick/Parquet/trading_data/raw` | ~1222 file Parquet mentah |
| **Archive** | `DATA_ARCHIVE_DIR` | `/media/petrick/Parquet/trading_data/archive` | ~1027 file Parquet archive |

---

## 14. Data Sources

### 14.1 Sumber Data Utama

| Sumber | Data | Akses | Rate Limit |
|--------|------|-------|------------|
| **Yahoo Finance** | OHLCV saham, indeks, forex, komoditas | `yfinance` (gratis) | 1 call/detik |
| **IDX.co.id** | Foreign flow, broker summary | `cloudscraper` (gratis) | — |
| **RSS Feeds** | Berita keuangan Indonesia | `feedparser` (gratis) | — |
| **Reddit** | Social media sentiment | `praw` (gratis) | API limit |
| **X/Twitter** | Social media sentiment | `tweepy` (API key) | API limit |
| **Google Trends** | Search interest | `pytrends` (gratis) | — |
| **BPS/BI/FRED** | Macro data | API/website | — |

### 14.2 Ticker Konfigurasi

| Kategori | Ticker | Jumlah |
|----------|--------|--------|
| **Saham IDX** | `*.JK` | 928 active equity + 40 delisted |
| **Indeks Global** | `^GSPC`, `^IXIC`, `^DJI`, `^HSI`, `^N225`, `^FTSE`, `^GDAXI` | 7 |
| **Proxy Makro** | `^TNX`, `GC=F`, `CL=F`, `IDR=X`, `DX-Y.NYB` | 5 |
| **Benchmark** | `^JKSE` | 1 |
| **Forex** | `EURIDR=X`, `JPYIDR=X` | 2 (skip jika quality=0) |
| **Total** | | 992 (951 aktif: 928 equity + 23 non-equity) |

### 14.3 Default Tickers

```python
DEFAULT_TICKERS = ["BBCA.JK", "TLKM.JK", "ASII.JK", "UNVR.JK", "BMRI.JK"]
```

### 14.4 IDX Conventions

| Konvensi | Nilai |
|----------|-------|
| **Lot size** | 100 lembar |
| **Ticker suffix** | `.JK` |
| **Broker fee (buy)** | 0.15% |
| **Broker fee (sell)** | 0.25% (0.15% + 0.1% PPh) |
| **Levy** | 0.00043% |
| **Settlement** | T+2 |
| **Auto reject** | ±15% dari reference price |

#### Tick Size IDX

```python
def idx_tick_size(price: float) -> float:
    if price < 200:    return 1.0
    elif price < 500:  return 2.0
    elif price < 2000: return 5.0
    elif price < 5000: return 10.0
    else:              return 25.0
```

---

## 15. Engine Registry

Daftar lengkap semua engine terdaftar di `ENGINE_REGISTRY`:

| # | Name | Module | Class |
|---|------|--------|-------|
| 1 | `technical` | `trading_system.analysis.technical` | `TechnicalAnalysisEngine` |
| 2 | `fundamental` | `trading_system.analysis.fundamental` | `FundamentalAnalysisEngine` |
| 3 | `macro` | `trading_system.analysis.macro` | `MacroEconomicEngine` |
| 4 | `global_market` | `trading_system.analysis.global_market` | `GlobalMarketEngine` |
| 5 | `relationship` | `trading_system.analysis.relationship` | `MarketRelationshipEngine` |
| 6 | `sentiment` | `trading_system.sentiment.engine` | `SentimentEngine` |
| 7 | `corporate` | `trading_system.corporate.actions` | `CorporateActionEngine` |
| 8 | `decision` | `trading_system.decision.engine` | `DecisionEngine` |
| 9 | `xai` | `trading_system.xai.engine` | `ExplainableAIEngine` |
| 10 | `backtest` | `trading_system.backtest.engine` | `BacktestEngine` |
| 11 | `paper_trading` | `trading_system.paper_trading.engine` | `PaperTradingEngine` |
| 12 | `monitoring` | `trading_system.monitoring.engine` | `MonitoringEngine` |
| 13 | `ai_learning` | `trading_system.ai_learning.engine` | `AILearningEngine` |
| 14 | `risk` | `trading_system.risk.engine` | `RiskEngine` |
| 15 | `execution` | `trading_system.execution.engine` | `ExecutionEngine` |
| 16 | `automated_execution` | `trading_system.execution.automated` | `AutomatedExecutionEngine` |
| 17 | `rebalancer` | `trading_system.portfolio.rebalancer` | `PortfolioRebalancer` |
| 18 | `performance_analytics` | `trading_system.portfolio.performance` | `PerformanceAnalytics` |

### Status Engine

| Status | Arti |
|--------|------|
| `healthy` | Engine berjalan, ada skor terbaru |
| `idle` | Engine belum pernah dijalankan |
| `warning` | Monitoring tidak ok |
| `error` | Exception saat inisialisasi |

---

## 16. Event Bus

### Daftar Topic Event Bus

| Topic | Publisher | Subscriber |
|-------|-----------|------------|
| `data.raw.ohlcv` | Acquisition Engine | Validation Engine |
| `data.raw.fundamental` | Acquisition Engine | Validation Engine |
| `data.raw.news` | Acquisition Engine | Validation Engine |
| `data.raw.corporate_action` | Acquisition Engine | Validation Engine |
| `data.clean.ohlcv` | Validation Engine | Semua Analysis Engine |
| `data.clean.fundamental` | Validation Engine | Fundamental Engine |
| `data.clean.macro` | Validation Engine | Macro Engine |
| `data.clean.calendar` | Validation Engine | Macro Engine |
| `data.quality.alert` | Validation Engine | Monitoring Engine |
| `analysis.fundamental.score` | Fundamental Engine | Decision, XAI |
| `analysis.technical.score` | Technical Engine | Decision, XAI |
| `analysis.macro.regime` | Macro Engine | Decision, Relationship, Risk |
| `analysis.global.score` | Global Engine | Decision, Relationship |
| `analysis.sentiment.score` | Sentiment Engine | Decision, XAI |
| `analysis.corporate_action.updated` | Corporate Engine | Fundamental, Technical, Portfolio |
| `analysis.relationship.updated` | Relationship Engine | Decision, XAI |
| `risk.assessment.completed` | Risk Engine | Decision, Portfolio |
| `decision.recommendation.created` | Decision Engine | Portfolio, XAI, Presentation, Paper Trading |
| `portfolio.rebalance.generated` | Portfolio Engine | Execution Engine |
| `execution.order.filled` | Execution Engine | Backtest, Paper Trading, Audit |
| `execution.order.rejected` | Execution Engine | Audit |
| `xai.explanation.generated` | XAI Engine | Presentation Layer |

---

## 17. Data Contracts

### 17.1 `ohlcv_record`

```json
{
  "ticker": "BBCA.JK",
  "asset_class": "equity",
  "exchange": "IDX",
  "timestamp": "2026-07-29T00:00:00+07:00",
  "timeframe": "1d",
  "open": 9500, "high": 9575, "low": 9475, "close": 9550,
  "volume": 12500000,
  "adjusted_close": 9550,
  "source": "IDX",
  "ingested_at": "2026-07-29T20:05:00+07:00"
}
```

### 17.2 `fundamental_record`

```json
{
  "ticker": "BBCA.JK",
  "period": "2026-Q2",
  "period_type": "quarterly",
  "statement": {
    "revenue": 0, "net_income": 0, "total_equity": 0, "total_debt": 0,
    "operating_cash_flow": 0, "eps": 0
  },
  "restated": false,
  "source": "BEI"
}
```

### 17.3 `macro_record`

```json
{
  "indicator": "BI_RATE",
  "country": "ID",
  "period": "2026-07",
  "actual": 5.75,
  "consensus": 5.75,
  "previous": 5.75,
  "unit": "percent",
  "source": "BI"
}
```

### 17.4 `score_record`

```json
{
  "ticker": "BBCA.JK",
  "engine": "fundamental",
  "score": 78.5,
  "breakdown": {"PER": 0.7, "ROE": 0.9, "DER": 0.6},
  "as_of": "2026-07-29T20:10:00+07:00"
}
```

### 17.5 `recommendation_record`

```json
{
  "recommendation_id": "BBCA.JK_2026-07-30T11:23:45Z",
  "ticker": "BBCA.JK",
  "action": "BUY",
  "conviction_score": 82,
  "position_size": 0.05,
  "entry_price_range": [9500, 9600],
  "stop_loss": 9200,
  "take_profit": 10200,
  "expected_hold_period": "3-6 months",
  "risk_flags": [],
  "contributing_scores": {
    "fundamental": 78.5, "technical": 65, "macro": 70, "sentiment": 55
  },
  "created_at": "2026-07-30T11:23:45Z"
}
```

---

## 18. Checklist Implementasi

### Phase 1: Fondasi Data & Backtest

- [ ] Data Acquisition Engine (Yahoo Finance adapter + rate limiter)
- [ ] Data Quality Validation Engine (completeness, plausibility, gap)
- [ ] Data Storage (SQLite WAL, 16 tabel inti)
- [ ] Backtesting Engine (event-driven, cost model IDX)
- [ ] 2-3 strategi benchmark (BuyAndHold, MA Crossover)
- [ ] Metrik kinerja lengkap (15 metrik)

### Phase 2: Analysis Layer

- [ ] Technical Analysis Engine (MA, RSI, MACD, ATR, BB, Volume Profile)
- [ ] Fundamental Analysis Engine (PER, PBV, ROE, DER, Growth + fallback)
- [ ] Macro Economic Engine (US10Y, Gold, Oil, USD/IDR + regime)
- [ ] Global Market Engine (7 indeks global, MA50/MA200)
- [ ] Analysis Pipeline (orkestrasi semua engine)

### Phase 3: Intelligence & Sentiment

- [ ] Market Relationship Engine (rolling correlation, lag analysis, 13 aset)
- [ ] Corporate Action Engine (split, dividend, adjustment factor)
- [ ] Sentiment Engine (6 sumber: NLP, foreign flow, broker, social, trends, historical)
- [ ] IDX Scraper (foreign flow, broker summary)

### Phase 4: Decision, Risk, Portfolio & Execution

- [ ] Risk Engine (ATR, position sizing, SL/TP, liquidity, volatility flags)
- [ ] Portfolio Engine (alokasi modal, order generation)
- [ ] Execution Engine (biaya IDX, slippage dinamis, feasibility)
- [ ] Decision Engine (multi-factor weighted scoring, regime filter, conviction)
- [ ] Automated Execution (robot trader, SL/TP monitoring, trailing stop)

### Phase 5: AI, Explainability & Continuous Improvement

- [ ] AI Learning Engine (regime weights, consistency adjustment, LR training)
- [ ] Explainable AI Engine (narrative, top factors, counter scenarios)
- [ ] Monitoring Engine (health check, alerts)
- [ ] Paper Trading Engine (simulasi, slippage validation)
- [ ] Performance Analytics (Sharpe, drawdown, win rate, equity curve)
- [ ] Portfolio Rebalancer (drift, threshold, calendar-based)

### Phase 6: Extended Data & Advanced Features

- [ ] Import 14 tabel MySQL (saham_snapshot, idx_financial_statements, dll.)
- [ ] Circuit Breaker (drawdown limit, auto-halt)
- [ ] Slippage Model (dinamis berdasarkan order size, ADV, time of day)
- [ ] Liquidity Filter (avg volume check sebelum entry)
- [ ] Pattern Reliability Engine (win rate historis pola chart)
- [ ] Advanced Technical (Ichimoku, Stochastic, Williams %R)
- [ ] Enhanced Regime (HMM-based)
- [ ] Cross-Asset Analysis
- [ ] Lead-Lag Analysis
- [ ] Factor Engine & Factor Screener
- [ ] Manipulation Detection
- [ ] No-Trade Zone Detection
- [ ] Red Flag Detection
- [ ] Order Book Analysis
- [ ] Performance Attribution
- [ ] Alpha Composer & Validation

### Phase 7: API & Frontend

- [ ] FastAPI (88 endpoint: 86 REST + 2 WebSocket)
- [ ] API Key Auth (`secrets.compare_digest`)
- [ ] SanitizedJSONResponse (NaN/Inf → null)
- [ ] Rate Limiting (60 req/min)
- [ ] Next.js Frontend (dashboard, engine monitor, backtest, portfolio, audit)
- [ ] WebSocket real-time engine status
- [ ] TradingView Lightweight Charts integration

### Phase 8: Production & Compliance

- [ ] Audit log (append-only, semua event tercatat)
- [ ] Telegram notifier
- [ ] CLI (17+ subcommands)
- [ ] Docker containerization
- [ ] CI/CD (GitHub Actions)
- [ ] Unit tests (750+ tests, coverage ≥ 50%)
- [ ] E2E tests (Playwright)
- [ ] Alembic schema migrations
- [ ] Parquet cold archive (raw + archive dirs)

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| Arsitektur lengkap | `docs/arsitektur-sistem-trading.md` |
| Buku panduan teknis | `docs/buku-sistem-trading.md` |
| Knowledge transfer | `pustaka/11-knowledge-transfer-aplikasi.md` |
| Panduan membangun aplikasi | `pustaka/12-panduan-membangun-aplikasi-pasar-modal.md` |
| Aplikasi retail | `pustaka/17-aplikasi-retail-pribadi.md` |
| API reference | `docs/API_REFERENCE.md` |
| Developer guide | `docs/DEVELOPER_GUIDE.md` |
| Test plan | `docs/TEST_PLAN.md` |
| Status | `docs/STATUS.md` |

---

## Referensi

1. `docs/arsitektur-sistem-trading.md` — Arsitektur sistem trading profesional (kerangka dasar)
2. `docs/buku-sistem-trading.md` — Buku panduan teknis lengkap (3092 baris)
3. `src/trading_system/` — Source code implementasi
4. `src/trading_system/api/app.py` — ENGINE_REGISTRY dan API endpoints
5. `src/trading_system/data/storage.py` — Database schema (SCHEMA constant)
6. `src/trading_system/config.py` — Konfigurasi global
7. `pyproject.toml` — Dependencies dan tooling
8. `alembic/versions/` — Schema migrations (0001-0003)

---

> **Catatan:** Dokumen ini adalah referensi definitif untuk modul, engine, dan data yang harus ada dalam sistem. Untuk implementasi teknis detail, lihat `docs/buku-sistem-trading.md` dan source code di `src/trading_system/`. Untuk pola arsitektur dan lessons learned, lihat `pustaka/11-knowledge-transfer-aplikasi.md`.
