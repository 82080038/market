# Faktor yang Mempengaruhi Pasar Modal: Analisis, Data, dan Implementasi

> **Dokumen 89** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Tujuan:** Audit komprehensif seluruh faktor yang mempengaruhi pasar modal Indonesia (IDX), menjawab tiga pertanyaan: (1) Apakah sudah lengkap dibahas di pustaka? (2) Bagaimana cara menggunakan data tersebut? (3) Bagaimana implementasinya di `trading-system` v0.1.11?
>
> **Scope:** Sistem personal untuk pemiliknya sendiri — fokus pada faktor yang relevan untuk decision support EOD, bukan untuk distribusi.

---

## Daftar Isi

1. [Kerangka Faktor Pasar Modal](#1-kerangka-faktor-pasar-modal)
2. [Audit Kelengkapan Pustaka](#2-audit-kelengkapan-pustaka)
3. [Faktor Fundamental](#3-faktor-fundamental)
4. [Faktor Teknikal](#4-faktor-teknikal)
5. [Faktor Makro Ekonomi](#5-faktor-makro-ekonomi)
6. [Faktor Pasar Global](#6-faktor-pasar-global)
7. [Faktor Sentimen & Aliran Dana](#7-faktor-sentimen--aliran-dana)
8. [Faktor Relasi & Korelasi](#8-faktor-relasi--korelasi)
9. [Faktor Regime Pasar](#9-faktor-regime-pasar)
10. [Faktor Corporate Actions](#10-faktor-corporate-actions)
11. [Faktor Mikrostruktur & Likuiditas](#11-faktor-mikrostruktur--likuiditas)
12. [Faktor Behavioral](#12-faktor-behavioral)
13. [Faktor Regulasi & Kebijakan](#13-faktor-regulasi--kebijakan)
14. [Faktor Geopolitik & Event Shock](#14-faktor-geopolitik--event-shock)
15. [Faktor Seasonal & Kalender](#15-faktor-seasonal--kalender)
16. [Faktor Komoditas Spesifik IDX](#16-faktor-komoditas-spesifik-idx)
17. [Faktor Yang Belum Tercakup](#17-faktor-yang-belum-tercakup)
18. [Cara Menggunakan Data Faktor](#18-cara-menggunakan-data-faktor)
19. [Implementasi di Trading-System](#19-implementasi-di-trading-system)
20. [Gap dan Rekomendasi](#20-gap-dan-rekomendasi)

---

## 1. Kerangka Faktor Pasar Modal

### 1.1 Taxonomy Faktor

```
FAKTOR YANG MEMPENGARUHI HARGA SAHAM IDX
│
├── INTERNAL EMITEN
│   ├── Fundamental (financial performance, valuation)
│   ├── Corporate actions (split, dividend, rights issue, buyback)
│   └── Manajemen & governance (insider trading, UBO, GCG)
│
├── PASAR DOMESTIK
│   ├── Teknikal (price action, volume, momentum)
│   ├── Mikrostruktur (likuiditas, spread, order book)
│   ├── Sentimen (news, social media, fear/greed)
│   ├── Aliran dana (foreign flow, broker flow, retail participation)
│   ├── Regime (bull/bear/sideways, volatility regime)
│   └── Seasonal (January effect, earnings season, year-end)
│
├── MAKRO EKONOMI
│   ├── Suku bunga (BI rate, Fed rate)
│   ├── Inflasi (CPI, core inflation)
│   ├── Pertumbuhan (GDP, IP, retail sales)
│   ├── Neraca perdagangan (trade balance, current account)
│   ├── Cadangan devisa & nilai rupiah (USD/IDR)
│   └── Fiskal (deficit, debt-to-GDP, tax policy)
│
├── PASAR GLOBAL
│   ├── Indeks global (Dow, S&P 500, Nikkei, Hang Seng, Shanghai)
│   ├── Komoditas (crude oil, gold, CPO, coal, nickel, copper)
│   ├── Forex (DXY, USD/IDR, EUR/USD)
│   ├── Yield (US 10Y, US 2Y, spread)
│   └── Risk sentiment (VIX, MOVE, crypto sentiment)
│
├── RELASI ANTAR ASET
│   ├── Korelasi saham ↔ indeks global
│   ├── Korelasi saham ↔ komoditas
│   ├── Lead-lag antar saham/sektor
│   ├── Cointegration (long-term equilibrium)
│   └── Spillover/contagion (crisis transmission)
│
├── REGULASI & KEBIJAKAN
│   ├── OJK/BEI rules (auto-reject, circuit breaker, short selling)
│   ├── POJK (permodalan broker, free float, UBO)
│   ├── UU P2SK (demutualisasi, reformasi 2026)
│   └── Kebijakan moneter/fiskal pemerintah
│
├── GEOPOLITIK & EVENT SHOCK
│   ├── Konflik/perang (Rusia-Ukraina, Middle East, trade war)
│   ├── Pemilu (political cycle, policy uncertainty)
│   ├── Pandemi/krisis (COVID, supply chain disruption)
│   └── Bencana alam (tsunami, gempa, el nino/la nina)
│
└── BEHAVIORAL
    ├── FOMO & panic selling
    ├── Disposition effect & anchoring
    ├── Herding & confirmation bias
    └── Overconfidence & loss aversion
```

### 1.2 Pertanyaan Audit

| # | Pertanyaan | Metode |
|---|-----------|--------|
| 1 | Apakah faktor ini dibahas di pustaka? | grep 89 dokumen |
| 2 | Di dokumen mana? | file mapping |
| 3 | Apakah ada data source? | acquisition check |
| 4 | Bagaimana cara pakai datanya? | pipeline check |
| 5 | Apakah diimplementasikan di kode? | source code check |
| 6 | Apakah masuk ke decision engine? | weight check |

---

## 2. Audit Kelengkapan Pustaka

### 2.1 Summary Matrix

| Faktor | Pustaka? | Dokumen | Kode? | Decision Weight | Status |
|--------|----------|---------|-------|-----------------|--------|
| **Fundamental** | ✅ Lengkap | 06, 12, 18 | ✅ `analysis/fundamental.py` | 25% | ✅ Tercapai |
| **Teknikal** | ✅ Lengkap | 05, 12, 18 | ✅ `analysis/technical.py` | 20% | ✅ Tercapai |
| **Makro** | ⚠️ Sebagian | 03, 13, 22, 35 | ✅ `analysis/macro.py` | 15% | ⚠️ Data terbatas |
| **Global market** | ⚠️ Sebagian | 03, 13, 35 | ✅ `analysis/global_market.py` | 15% | ⚠️ Indeks only |
| **Sentimen** | ⚠️ Sebagian | 08, 09, 15, 18 | ✅ `sentiment/engine.py` | 15% | ⚠️ News + flow, social stub |
| **Relasi** | ✅ Lengkap | 07, 08, 21, 35 | ✅ `analysis/relationship.py` | 10% | ✅ Tercapai |
| **Regime** | ✅ Lengkap | 05, 09, 13, 18 | ✅ `analysis/regime.py` + `enhanced_regime.py` | Filter | ✅ Tercapai |
| **Corporate actions** | ✅ Lengkap | 01, 06, 75 | ✅ `corporate/actions.py` | Adjust | ✅ Tercapai |
| **Mikrostruktur** | ✅ Lengkap | 08, 13, 14, 24 | ✅ `analysis/order_book.py` | Screen | ✅ Tercapai |
| **Behavioral** | ✅ Lengkap | 09, 13, 16, 17 | ⚠️ `analysis/red_flags.py` | Warning | ⚠️ Sebagian |
| **Regulasi** | ✅ Lengkap | 10, 14, 76, 87 | ⚠️ Config, tidak ada engine | Guard | ⚠️ Config only |
| **Geopolitik** | ❌ Kurang | 03, 09, 21 (sebaran) | ❌ Tidak ada | — | ❌ Gap |
| **Seasonal** | ❌ Kurang | 09, 39 (mention only) | ❌ Tidak ada | — | ❌ Gap |
| **Komoditas spesifik** | ❌ Kurang | 01-09 (mention), 35 | ⚠️ Macro oil/gold, tidak CPO/coal/nickel | — | ❌ Gap |
| **Sector rotation** | ⚠️ Sebagian | 16, 35, 46 | ❌ Tidak ada | — | ❌ Gap |
| **Insider trading** | ⚠️ Sebagian | 02, 13 | ❌ Tidak ada | — | ❌ Gap |
| **IPO timing** | ❌ Tidak ada | — | ❌ Tidak ada | — | ❌ Gap |
| **Earnings season timing** | ❌ Kurang | 26, 39 (mention) | ❌ Tidak ada | — | ❌ Gap |
| **Commodity supercycle** | ❌ Tidak ada | — | ❌ Tidak ada | — | ❌ Gap |
| **Tax-loss selling** | ⚠️ Sebagian | 09 (mention) | ❌ Tidak ada | — | ❌ Gap |
| **Index inclusion (MSCI/FTSE)** | ⚠️ Sebagian | 03, 13, 14, 15 | ❌ Tidak ada | — | ❌ Gap |
| **QE/QT impact** | ⚠️ Sebagian | 06, 15 | ❌ Tidak ada | — | ❌ Gap |
| **Retail participation (SID)** | ⚠️ Sebagian | 03, 10, 14, 17 | ❌ Tidak ada | — | ❌ Gap |

### 2.2 Verdict

- **13 faktor tercakup dan terimplementasi** ✅
- **5 faktor tercakup tapi implementasi sebagian** ⚠️
- **9 faktor belum/tidak dibahas dan tidak diimplementasi** ❌

---

## 3. Faktor Fundamental

### 3.1 Pustaka
- `06-analisis-fundamental.md` — PER, PBV, ROE, DER, growth, kualitas laporan keuangan
- `12-panduan-membangun-aplikasi-pasar-modal.md` §5 — modul fundamental
- `18-modul-engine-data-wajib.md` — fundamental engine spec

### 3.2 Cara Pakai Data
| Data | Source | Frekuensi | Cara Pakai |
|------|--------|-----------|------------|
| PER (Price/Earnings) | yfinance `trailingPE` | EOD | Lower = cheaper, tapi bisa value trap. Bandingkan dengan sektor dan historis |
| PBV (Price/Book) | yfinance `priceToBook` | EOD | Lower = cheaper. PBV < 1 = trading below book value |
| ROE (Return on Equity) | yfinance `returnOnEquity` | Quarterly | Higher = better profitability. ROE > 15% = good |
| DER (Debt/Equity) | yfinance `debtToEquity` | Quarterly | Lower = safer. DER < 2 = manageable |
| Revenue growth | yfinance `revenueGrowth` | Quarterly | Positive = growing. > 10% = strong growth |
| EPS growth | yfinance `earningsGrowth` | Quarterly | Positive = profitable growth |
| Free cash flow | yfinance `freeCashflow` | Quarterly | Positive = self-funding. FCF yield = FCF/MarketCap |
| Dividend yield | yfinance `dividendYield` | EOD | Income return. > 5% = attractive (tapi cek sustainability) |

### 3.3 Implementasi
- **Kode:** `src/trading_system/analysis/fundamental.py` — 5 komponen: PER, PBV, ROE, DER, growth
- **Scoring:** 0-100, 5 komponen × 25 max = 125, normalized to 100
- **Weight multiplier:** 0.0 (no data), 0.5 (degraded), 1.0 (ok) — auto-redistribute weight jika data missing
- **Decision weight:** 25% (terbesar)
- **DB:** `fundamental_data` table (991 rows)

### 3.4 Gap
- **Earnings season timing** — tidak ada tracking kapan emiten akan rilis laporan keuangan berikutnya
- **Fundamental quality flag** — tidak ada deteksi akuntansi agresif (earnings manipulation)
- **Sector-relative valuation** — tidak ada PER/PBV relative to sector median

---

## 4. Faktor Teknikal

### 4.1 Pustaka
- `05-analisis-teknikal.md` — RSI, MACD, SMA, EMA, Bollinger, stochastic, ADX, OBV
- `12-panduan-membangun-aplikasi-pasar-modal.md` §4 — modul teknikal
- `18-modul-engine-data-wajib.md` — technical engine spec

### 4.2 Cara Pakai Data
| Indicator | Periode | Sinyal | Cara Pakai |
|-----------|---------|--------|------------|
| RSI(14) | Daily | > 70 overbought, < 30 oversold | Sell signal > 70, buy signal < 30 (trend market: adjust) |
| MACD(12,26,9) | Daily | Crossover + histogram | Buy: MACD > signal, Sell: MACD < signal |
| SMA(50,200) | Daily | Golden/death cross | Buy: SMA50 > SMA200, Sell: SMA50 < SMA200 |
| Bollinger(20,2) | Daily | Band touch + squeeze | Buy: price touch lower band, Sell: touch upper |
| ADX(14) | Daily | > 25 = trending | Filter: only trade when ADX > 25 |
| ATR(14) | Daily | Volatility measure | Position sizing: stop = entry - 2×ATR |
| OBV | Daily | Divergence with price | Confirm trend: OBV rising + price rising = healthy |

### 4.3 Implementasi
- **Kode:** `src/trading_system/analysis/technical.py` — RSI, MACD, SMA, EMA, Bollinger, ADX, ATR, OBV
- **Scoring:** 0-100, momentum (RSI+MACD) + trend (SMA+ADX) + volatility (Bollinger+ATR)
- **Decision weight:** 20%
- **DB:** `technical_indicators` table (11,136 rows)

### 4.4 Gap
- **Ichimoku Cloud** — tidak diimplementasi (populer di trader Indonesia)
- **Volume Profile / VWAP** — tidak diimplementasi
- **Multi-timeframe analysis** — hanya daily, tidak ada weekly/monthly confluence

---

## 5. Faktor Makro Ekonomi

### 5.1 Pustaka
- `03-pasar-modal-global.md` — suku bunga, inflasi, GDP
- `13-hal-yang-perlu-diperhatikan.md` — faktor makro yang pengaruhi IDX
- `22-data-engineering-pipeline.md` — macro data pipeline
- `35-multi-asset-cross-market-analysis.md` — cross-asset macro

### 5.2 Cara Pakai Data
| Data | Source | Frekuensi | Cara Pakai |
|------|--------|-----------|------------|
| BI Rate | BI website / yfinance `^IRX` | Monthly | Lower = bullish equities. Rate cut = growth stimulus |
| Inflasi (CPI) | BPS / yfinance | Monthly | High inflation = bearish (margin squeeze, rate hike risk) |
| GDP growth | BPS | Quarterly | > 5% = bullish for IDX. < 3% = bearish |
| Trade balance | BPS / BEI | Monthly | Surplus = bullish (export strong). Deficit = bearish |
| Current account | BI | Quarterly | Deficit = rupiah pressure = foreign outflow risk |
| Cadangan devisa | BI | Monthly | Declining = risk signal. < $100B = crisis zone |
| USD/IDR | yfinance `IDR=X` | EOD | Rupiah weakening = foreign outflow pressure |
| US 10Y yield | yfinance `^TNX` | EOD | Rising = risk-off for emerging markets |
| Crude oil | yfinance `CL=F` | EOD | Oil up = inflation risk but positive for IDX energy stocks |
| Gold | yfinance `GC=F` | EOD | Gold up = risk-off. Safe haven flow |

### 5.3 Implementasi
- **Kode:** `src/trading_system/analysis/macro.py` — classify_regime (growth/slowdown), compute_score
- **Data:** US10Y, GOLD, OIL, USD_IDR dari yfinance
- **Scoring:** 0-100, breakdown per asset (gold, oil, US10Y, USD/IDR)
- **Regime classification:** growth (oil up + USD/IDR down), slowdown (oil down + USD/IDR up)
- **Decision weight:** 15%
- **DB:** `macro_data` table (10,036 rows)

### 5.4 Gap
- **BI Rate data** — tidak ada direct fetch dari BI. Hanya proxy via US10Y
- **Inflasi CPI** — tidak ada data inflasi di pipeline
- **GDP growth** — tidak ada data GDP di pipeline
- **Trade balance / current account** — tidak ada
- **Cadangan devisa** — tidak ada
- **Fiskal (deficit, debt-to-GDP)** — tidak ada
- **QE/QT tracking** — tidak ada

**Root cause:** yfinance tidak menyediakan data makro Indonesia (BI rate, CPI, GDP). Perlu scraping BI/BPS atau API pihak ketiga.

---

## 6. Faktor Pasar Global

### 6.1 Pustaka
- `03-pasar-modal-global.md` — indeks global, komoditas, forex
- `13-hal-yang-perlu-diperhatikan.md` — pengaruh pasar global ke IDX
- `35-multi-asset-cross-market-analysis.md` — cross-market analysis

### 6.2 Cara Pakai Data
| Data | Source | Frekuensi | Cara Pakai |
|------|--------|-----------|------------|
| Dow Jones | yfinance `^DJI` | EOD | US market sentiment. Dow up = risk-on for IDX |
| S&P 500 | yfinance `^GSPC` | EOD | Broad US market. Correlation with IDX ~0.3-0.5 |
| Nasdaq | yfinance `^IXIC` | EOD | Tech sentiment. Nasdaq up = tech stocks bullish |
| Nikkei 225 | yfinance `^N225` | EOD | Japan market. Asian sentiment proxy |
| Hang Seng | yfinance `^HSI` | EOD | HK/China market. China sentiment proxy |
| Shanghai | yfinance `000001.SS` | EOD | China mainland. Commodity demand signal |
| VIX | yfinance `^VIX` | EOD | Fear index. VIX > 30 = panic, risk-off for IDX |
| DXY | yfinance `DX-Y.NYB` | EOD | Dollar index. DXY up = rupiah pressure = bearish IDX |
| Crude oil | yfinance `CL=F` | EOD | Oil up = inflation + energy stocks bullish |
| Gold | yfinance `GC=F` | EOD | Safe haven. Gold up = risk-off |

### 6.3 Implementasi
- **Kode:** `src/trading_system/analysis/global_market.py` — GlobalMarketEngine
- **Data:** Dow, S&P 500, Nasdaq, Nikkei, Hang Seng, Shanghai, VIX, DXY, crude, gold
- **Scoring:** 0-100, based on index performance (1-day, 5-day, 20-day returns)
- **Decision weight:** 15%
- **World monitor:** `analysis/world_monitor.py` — CII score, convergence, velocity spike, silent divergence, sector cascade

### 6.4 Gap
- **Sector-specific global** — tidak ada tracking sektor global (e.g., global bank stocks, global mining stocks)
- **ETF flows** — tidak ada tracking emerging market ETF flows (EEM, EIDO)
- **Asian FX basket** — tidak ada tracking KRW, THB, MYR vs IDR (regional contagion)

---

## 7. Faktor Sentimen & Aliran Dana

### 7.1 Pustaka
- `08-trading-algoritmik.md` — sentimen sebagai input
- `09-behavioral-finance.md` — fear/greed, herding
- `15-pelaku-pasar-modal.md` — foreign flow, broker flow, retail
- `18-modul-engine-data-wajib.md` — sentiment engine spec

### 7.2 Cara Pakai Data
| Data | Source | Frekuensi | Cara Pakai |
|------|--------|-----------|------------|
| Foreign net buy/sell | IDX scraper | Daily | Foreign net buy = bullish signal. Persistent sell = bearish |
| Broker flow | IDX scraper | Daily | Top broker accumulation = smart money. Broker ranking |
| News sentiment | RSS (Kontan, Bisnis, CNBC) | Real-time | Positive news = bullish. Negative = bearish. Lexicon-based NLP |
| Social media | Reddit (PRAW), X (API) | Real-time | Retail sentiment. Hype = FOMO warning |
| Google Trends | pytrends | Weekly | Search interest spike = retail attention. Leading indicator |
| Fear & Greed | CNN-style calculation | Daily | Extreme fear = contrarian buy. Extreme greed = sell |

### 7.3 Implementasi
- **Kode:** `src/trading_system/sentiment/engine.py` — 5 sub-engine:
  - Foreign flow: `sentiment/foreign_flow.py` ✅ fungsional
  - Broker summary: `sentiment/broker_summary.py` ✅ fungsional
  - News NLP: RSS feed + Indonesian lexicon ✅ fungsional
  - Social media: `sentiment/social_media.py` ⚠️ class exists, no API integration
  - Google Trends: `sentiment/google_trends.py` ⚠️ class exists, no API call
- **Scoring:** Weighted composite: foreign_flow 0.30, broker 0.20, news 0.25, social 0.15, trends 0.10
- **Decision weight:** 15%
- **DB:** `foreign_flow` (103,046 rows), `broker_flow` (15,830 rows), `fear_greed` (466 rows), `news` (110 rows)

### 7.4 Gap
- **Fear & Greed index** — ada di DB (466 rows) tapi tidak ada engine yang compute secara real-time
- **Social media API integration** — stub only, tidak ada Reddit/X API call
- **Google Trends API** — stub only, tidak ada pytrends call
- **Insider trading signal** — tidak ada tracking masyarakat direktori/komisaris beli/jual
- **Retail participation (SID growth)** — tidak ada tracking KSEI single investor ID data

---

## 8. Faktor Relasi & Korelasi

### 8.1 Pustaka
- `07-manajemen-risiko.md` — diversifikasi via correlation
- `08-trading-algoritmik.md` — pairs trading, correlation breakdown
- `21-portfolio-optimization-construction.md` — correlation matrix
- `35-multi-asset-cross-market-analysis.md` — Diebold-Yilmaz spillover

### 8.2 Cara Pakai Data
| Data | Source | Frekuensi | Cara Pakai |
|------|--------|-----------|------------|
| Rolling correlation | Computed from OHLCV | Daily | High corr = less diversification. Monitor breakdown |
| Lead-lag | Cross-correlation function | Daily | Stock A leads stock B by N days → predict B from A |
| Cointegration | Engle-Granger / Johansen | Weekly | Long-term equilibrium. Deviation = arbitrage opportunity |
| Spillover | Diebold-Yilmaz variance decomposition | Weekly | How much shock in market A affects market B |
| Influence score | Average absolute correlation | Daily | How much a stock is influenced by global/macro factors |

### 8.3 Implementasi
- **Kode:** `src/trading_system/analysis/relationship.py` — rolling correlation, influence score
- **Lead-lag:** `src/trading_system/analysis/lead_lag.py` — cross-correlation, pair analysis
- **Scoring:** 0-100, based on influence score (how well global/macro explains the stock)
- **Decision weight:** 10%
- **DB:** `relationship_matrix` (12,077 rows)

### 8.4 Gap
- **Diebold-Yilmaz spillover** — dibahas di pustaka tapi tidak diimplementasi
- **Cointegration test** — dibahas tapi tidak diimplementasi
- **Pairs trading signal** — tidak ada pairs trading engine
- **Sector correlation heatmap** — tidak ada visualisasi

---

## 9. Faktor Regime Pasar

### 9.1 Pustaka
- `05-analisis-teknikal.md` — trending vs sideways
- `09-behavioral-finance.md` — bull/bear psychology
- `13-hal-yang-perlu-diperhatikan.md` — regime detection
- `18-modul-engine-data-wajib.md` — regime engine spec

### 9.2 Cara Pakai Data
| Data | Source | Frekuensi | Cara Pakai |
|------|--------|-----------|------------|
| IHSG vs SMA200 | Computed from OHLCV | Daily | Above SMA200 = bull, below = bear |
| VIX level | yfinance `^VIX` | Daily | VIX < 20 = calm, 20-30 = elevated, > 30 = panic |
| Correlation regime | Computed | Weekly | High corr = systemic risk. Low corr = stock-specific |
| Global risk regime | Enhanced regime engine | Daily | risk_on / risk_off / neutral |

### 9.3 Implementasi
- **Kode:** `src/trading_system/analysis/regime.py` — rule-based: trending/neutral/volatile/shock
- **Enhanced:** `src/trading_system/analysis/enhanced_regime.py` — z-score based: risk_on/risk_off/neutral
- **Usage:** Regime multiplier untuk position sizing (trending=1.0, neutral=0.7, volatile=0.5, shock=0.3)
- **Decision engine:** `apply_regime_filter()` — adjust scores berdasarkan regime (tightening/easing)
- **DB:** regime stored in scores breakdown

### 9.4 Gap
- **HMM (Hidden Markov Model)** — dibahas di pustaka tapi tidak diimplementasi (rule-based only)
- **Volatility regime (GARCH)** — tidak ada GARCH model untuk volatility forecasting
- **Sector rotation regime** — tidak ada tracking sektor mana yang outperform/underperform per regime

---

## 10. Faktor Corporate Actions

### 10.1 Pustaka
- `01-fundamental-pasar-modal.md` — split, dividend, rights issue
- `06-analisis-fundamental.md` — impact corporate actions
- `75-corporate-actions-processing-adjustment.md` — processing pipeline

### 10.2 Cara Pakai Data
| Event | Impact | Cara Pakai |
|-------|--------|------------|
| Stock split | Price turun, jumlah saham naik. Netral fundamental | Adjust historical price ÷ ratio. Signal: split = bullish (retail accessible) |
| Dividend | Price turun ex-date sebesar dividend | Capture: beli sebelum cum-date, jual setelah ex-date. Yield = annual div/price |
| Rights issue | Dilution jika tidak subscribe | Negative signal jika discount deep. Positive jika untuk ekspansi |
| Buyback | Supply berkurang, price support | Bullish signal: company thinks stock undervalued |
| Delisting | Likuidasi atau go private | Negative: investor trapped. Exit before delisting |
| Suspension | Trading halt | Risk: tidak bisa exit. Monitor BEI announcement |

### 10.3 Implementasi
- **Kode:** `src/trading_system/corporate/actions.py` — fetch splits/dividends from yfinance, store to DB
- **Price adjustment:** `update_adjusted_close()` — backward adjust pre-split/dividend prices
- **DB:** `corporate_actions` (6,365 rows), `dividends` (5,974 rows)
- **Usage:** Price adjustment untuk backtest accuracy

### 10.4 Gap
- **Rights issue tracking** — tidak ada (yfinance tidak provide)
- **Buyback tracking** — tidak ada (perlu scraping BEI disclosure)
- **Delisting/suspension** — ada di DB schema (migration 0003) tapi tidak ada automated alert
- **Dividend calendar** — tidak ada forward dividend calendar (kapan ex-date berikutnya)

---

## 11. Faktor Mikrostruktur & Likuiditas

### 11.1 Pustaka
- `08-trading-algoritmik.md` — market microstructure
- `13-hal-yang-perlu-diperhatikan.md` — likuiditas
- `14-kendala-pasar-modal.md` — gorengan, illiquid stocks
- `24-market-microstructure-likuiditas.md` — spread, depth, Amihud

### 11.2 Cara Pakai Data
| Data | Source | Frekuensi | Cara Pakai |
|------|--------|-----------|------------|
| Average daily volume | OHLCV | Daily | ADV < 100 lot = illiquid. Risk: slippage, exit difficulty |
| Turnover ratio | OHLCV × close | Daily | Low turnover = illiquid. Filter: exclude bottom 20% |
| Amihud illiquidity | \|return\| / volume | Daily | High Amihud = illiquid. Position size inversely proportional |
| Bid-ask spread | Order book (tidak ada) | Real-time | Wide spread = high cost. > 1% = avoid for short-term |
| Price gap | OHLCV | Daily | Frequent gaps = low liquidity or news-driven |
| Volume anomaly | OHLCV | Daily | Volume spike without news = manipulation signal |

### 11.3 Implementasi
- **Kode:** `src/trading_system/analysis/order_book.py` — price gap detection, volume gap, support/resistance, market efficiency
- **Liquidity:** `src/trading_system/analysis/liquidity_filter.py` — ADV, turnover, Amihud
- **Manipulation:** `src/trading_system/analysis/manipulation.py` — volume anomaly, pump-dump, wash trading, spread anomaly
- **Gorengan:** `src/trading_system/analysis/gorengan_detector.py` — price spike, weak fundamental, low liquidity
- **No-trade:** `src/trading_system/analysis/no_trade.py` — evaluate whether to skip a ticker
- **DB:** `pattern_analysis` (2,386 rows)

### 11.4 Gap
- **Real-time bid-ask spread** — tidak ada (EOD data only)
- **Order book depth** — tidak ada (no real-time data)
- **Slippage estimation** — ada di `risk/costs.py` tapi menggunakan model, bukan actual spread

---

## 12. Faktor Behavioral

### 12.1 Pustaka
- `09-behavioral-finance.md` — FOMO, panic, disposition, anchoring, herding, overconfidence, loss aversion
- `13-hal-yang-perlu-diperhatikan.md` — psikologi investor ritel
- `16-strategi-mencari-keuntungan.md` — strategi berdasarkan profil psikologis
- `17-aplikasi-retail-pribadi.md` — behavioral mitigation di aplikasi

### 12.2 Cara Pakai Data
| Bias | Deteksi | Mitigasi |
|------|---------|----------|
| FOMO | Price spike + volume surge + news hype | Warning: "Harga naik X% dalam Y hari. Pertimbangkan valiasi." |
| Panic selling | Price drop + volume surge + fear index high | Warning: "Pasar panik. Jangan jual di bottom. Cek fundamental." |
| Disposition effect | Sell winner too early, hold loser too long | Track: avg holding period winners vs losers. Alert if asymmetric. |
| Anchoring | User fixated on historical high/low price | Show: current price vs 52-week range + fair value estimate |
| Herding | Following foreign flow / broker flow blindly | Show: "Anda follow foreign net buy. Pastikan ada thesis sendiri." |
| Overconfidence | Frequent trading after wins | Track: trade frequency + recent win rate. Alert if overtrading. |

### 12.3 Implementasi
- **Kode:** `src/trading_system/analysis/red_flags.py` — red flag detection
- **No-trade engine:** `analysis/no_trade.py` — block trading jika kondisi tidak aman
- **Gorengan detector:** `analysis/gorengan_detector.py` — FOMO prevention
- **Circuit breaker:** `risk/circuit_breaker.py` — stop trading jika loss limit tercapai
- **Usage:** Warning flag di screener, pre-trade check

### 12.4 Gap
- **Behavioral tracking** — tidak ada tracking user trading pattern (FOMO, disposition effect)
- **Behavioral warning UI** — tidak ada frontend untuk display warning
- **Trade journal** — tidak ada journal untuk self-reflection

---

## 13. Faktor Regulasi & Kebijakan

### 13.1 Pustaka
- `10-regulasi-pasar-modal.md` — OJK, BEI, KSEI, KPEI, POJK, UU
- `14-kendala-pasar-modal.md` — kendala regulasi + reformasi 2026
- `76-idx-trading-rules-market-mechanics.md` — auto-reject, circuit breaker, short selling
- `87-regulatory-developments-2026.md` — POJK 3/5 2026, reformasi
- `10-regulasi-pasar-modal.md` §8 — UU P2SK, demutualisasi, JATS MME (ditambahkan)

### 13.2 Cara Pakai Data
| Regulasi | Impact | Cara Pakai |
|----------|--------|------------|
| Auto-reject (ARA/ARB) | Price limit ±7% (varies by price group) | Pre-trade: reject order jika price di luar band |
| Circuit breaker IHSG | Halt jika IHSG turun > 5% / 10% / 15% | Monitor: stop trading saat halt. Resume setelah 30 menit |
| Short selling rules | Only for stocks in Daftar Efek Bersyarat | Filter: only allow short for eligible stocks |
| Margin trading | Only for stocks in Daftar Efek Margin | Filter: only allow margin for eligible stocks |
| Free float 15% (2026) | Emiten < 15% free float = risk flag | Screen: flag low free float stocks |
| PEKU kategori (2026) | Broker capability differs by kategori | Config: broker adapter knows kategori → capability |

### 13.3 Implementasi
- **Kode:** Auto-reject dan circuit breaker ada di `execution/automated.py` (configurable)
- **DB:** `policy_events` (179 rows), `external_events` (119 rows)
- **Config:** Fee structure, auto-reject bands, circuit breaker thresholds di config
- **Usage:** Guard di execution path

### 13.4 Gap
- **Regulatory change monitoring** — tidak ada automated alert saat OJK/BEI publish new regulation
- **Compliance engine** — tidak ada engine yang validate compliance secara otomatis
- **Short/margin eligibility list** — tidak ada fetch Daftar Efek Bersyarat/Margin dari BEI

---

## 14. Faktor Geopolitik & Event Shock

### 14.1 Pustaka
- `03-pasar-modal-global.md` — global crisis, contagion
- `09-behavioral-finance.md` — crisis psychology
- `21-portfolio-optimization-construction.md` — political risk
- `23-machine-learning-trading.md` — election cycle

**Verdict: ❌ KURANG** — geopolitik hanya disinggung, tidak ada dokumen khusus yang membahas:
- Cara mendeteksi geopolitical risk event
- Cara mengukur impact ke IDX
- Cara hedge atau adjust portfolio saat geopolitical shock
- Historical analysis: dampak perang, pemilu, pandemi ke IDX

### 14.2 Cara Pakai Data
| Event | Source | Impact | Cara Pakai |
|-------|--------|--------|------------|
| Perang/konflik | News, GDELT | Risk-off, oil up, gold up, EM outflow | Reduce position, increase cash. Monitor VIX > 30 |
| Pemilu | KPU, news | Policy uncertainty. Pre-election: volatile. Post: rally jika market-friendly | Reduce position pre-election. Watch policy direction |
| Pandemi | WHO, news | Economic shutdown, crash, recovery (K-shape) | Circuit breaker. Buy post-crash with staged entry |
| Trade war | News, tariff data | Export impact, supply chain disruption | Monitor affected sectors (export, import-dependent) |
| Bencana alam | BMKG, news | Localized economic disruption. Insurance claims | Monitor affected regions/sectors |

### 14.3 Implementasi
- **Kode:** ❌ Tidak ada geopolitical risk engine
- **DB:** `external_events` (119 rows) — ada table tapi tidak ada engine yang consume
- **Policy events:** `policy_events` (179 rows) — ada table tapi tidak ada engine yang consume

### 14.4 Gap (KRITIS)
- **Geopolitical risk index** — tidak ada
- **Event shock detection** — tidak ada automated detection dari news/events
- **Historical event impact analysis** — tidak ada (e.g., berapa IDX drop saat COVID crash 2020, Russia-Ukraine 2022, trade war 2018)
- **Event-based position adjustment** — tidak ada auto-reduce position saat event shock

---

## 15. Faktor Seasonal & Kalender

### 15.1 Pustaka
- `09-behavioral-finance.md` — January effect, window dressing (mention only)
- `39-screening-aiml-pattern-memory.md` — calendar pattern (mention only)

**Verdict: ❌ KURANG** — seasonal effect hanya disinggung, tidak ada analisis mendalam tentang:
- January effect di IDX (apakah ada? seberapa kuat?)
- Earnings season pattern (Q1/Q2/Q3/Q4 reporting cycle impact)
- Year-end rally / window dressing oleh manajer investasi
- Month-end / quarter-end liquidity effect
- Holiday effect (Lebaran, Natal, Tahun Baru)
- Tax-loss selling di akhir tahun

### 15.2 Cara Pakai Data
| Pola | Periode | Cara Pakai |
|------|---------|------------|
| January effect | Awal tahun | Historically: small caps outperform di January. Check IDX data |
| Earnings season | Q1: Apr-Mei, Q2: Jul-Agu, Q3: Okt-Nov, Q4: Feb-Mar | Pre-earnings: reduce position jika uncertain. Post-earnings: react to surprise |
| Year-end rally | Nov-Des | Window dressing oleh MI. IHSG cenderung naik akhir tahun |
| Lebaran effect | Ramadhan-Lebaran | Consumer stocks bullish sebelum Lebaran. Post-Lebaran: normalisasi |
| Month-end effect | 3 hari terakhir bulan | Rebalancing flow. Volume naik. Liquidity effect |
| Tax-loss selling | Desember | Investor jual rugi untuk tax. Price pressure di stocks yang sudah turun |

### 15.3 Implementasi
- **Kode:** ❌ Tidak ada seasonal analysis engine
- **DB:** `market_calendar` (365 rows) — ada kalender bursa tapi tidak ada seasonal pattern analysis

### 15.4 Gap
- **Seasonal pattern backtest** — tidak ada backtest seasonal strategy
- **Earnings calendar** — tidak ada forward earnings calendar
- **Holiday effect analysis** — tidak ada

---

## 16. Faktor Komoditas Spesifik IDX

### 16.1 Pustaka
- `01-fundamental-pasar-modal.md` — CPO, batubara, nikel (mention)
- `03-pasar-modal-global.md` — komoditas (mention)
- `35-multi-asset-cross-market-analysis.md` — cross-asset (mention)

**Verdict: ❌ KURANG** — IDX adalah exchange yang sangat commodity-dependent (sektor energi & material ~35% market cap), tetapi tidak ada analisis spesifik tentang:
- CPO price → impact ke AALI, LSIP, SIMP, DSNG, ANJT
- Batubara price → impact ke PTBA, ITMG, ADRO, HRUM
- Nikel price → impact ke INCO, ANTM, MDKA
- Tembaga → impact ke ANTM, MDKA
- Emas → impact ke ANTM, MDKA
- Tin (timah) → impact ke TINS

### 16.2 Cara Pakai Data
| Komoditas | Source | Ticker IDX | Cara Pakai |
|-----------|--------|------------|------------|
| CPO (Crude Palm Oil) | Bursa Malaysia / yfinance | AALI, LSIP, SIMP, DSNG, ANJT | CPO up = revenue up for CPO producers. Track CPO futures |
| Batubara (Newcastle) | yfinance / ICE | PTBA, ITMG, ADRO, HRUM, BYAN | Coal up = revenue up. Track Newcastle coal index |
| Nikel (LME) | LME / yfinance | INCO, ANTM, MDKA | Nickel up = revenue up. Track LME nickel 3M |
| Tembaga (LME) | LME / yfinance | ANTM, MDKA | Copper up = revenue up. Track LME copper 3M |
| Emas | yfinance `GC=F` | ANTM, MDKA | Gold up = gold miners bullish |
| Tin (LME) | LME | TINS | Tin up = revenue up |

### 16.3 Implementasi
- **Kode:** `analysis/macro.py` — hanya track crude oil dan gold (global), tidak track CPO/coal/nickel/copper/tin
- **Relationship engine:** `analysis/relationship.py` — compute correlation saham vs global, tapi tidak specifik ke komoditas individual
- **DB:** Tidak ada table untuk komoditas spesifik (CPO, coal, nickel)

### 16.4 Gap (KRITIS untuk IDX)
- **Commodity-specific tracking** — CPO, batubara, nikel, tembaga, timah tidak ada di pipeline
- **Commodity-to-stock mapping** — tidak ada mapping komoditas → emiten yang terpengaruh
- **Commodity cycle analysis** — tidak ada supercycle detection
- **Sector rotation** — tidak ada tracking sektor mana yang outperform saat komoditas X naik/turun

---

## 17. Faktor Yang Belum Tercakup

### 17.1 Ringkasan Gap

| Faktor | Pustaka | Kode | Severity | Catatan |
|--------|---------|------|----------|---------|
| **Geopolitik & event shock** | ❌ Kurang | ❌ Tidak ada | **HIGH** | IDX sangat sensitif ke global event. External_events table ada tapi tidak consumed |
| **Seasonal & kalender** | ❌ Kurang | ❌ Tidak ada | **MEDIUM** | January effect, earnings season, year-end rally, Lebaran effect |
| **Komoditas spesifik IDX** | ❌ Kurang | ❌ Tidak ada | **HIGH** | CPO/coal/nickel/copper = 35% IDX market cap. Tidak ada tracking |
| **Sector rotation** | ⚠️ Sebagian | ❌ Tidak ada | **MEDIUM** | Tidak ada engine yang track sektor mana yang lead/lag |
| **Insider trading signal** | ⚠️ Sebagian | ❌ Tidak ada | **LOW** | Masyarakat direktori beli = bullish signal. Perlu scraping BEI disclosure |
| **IPO timing & performance** | ❌ Tidak ada | ❌ Tidak ada | **LOW** | IPO underpricing, flipping strategy. Tidak prioritas untuk personal use |
| **Earnings season timing** | ❌ Kurang | ❌ Tidak ada | **MEDIUM** | Tidak ada forward earnings calendar. Tidak ada pre/post earnings strategy |
| **Commodity supercycle** | ❌ Tidak ada | ❌ Tidak ada | **LOW** | Long-term commodity cycle. Akademik, tidak actionable untuk EOD |
| **Tax-loss selling** | ⚠️ Sebagian | ❌ Tidak ada | **LOW** | Desember effect. Bisa di-backtest tapi tidak ada engine |
| **Index inclusion (MSCI/FTSE)** | ⚠️ Sebagian | ❌ Tidak ada | **LOW** | Passive flow saat masuk/keluar index. Event-driven, jarang |
| **QE/QT impact** | ⚠️ Sebagian | ❌ Tidak ada | **LOW** | Fed balance sheet → EM flow. Akademik |
| **Retail participation (SID)** | ⚠️ Sebagian | ❌ Tidak ada | **LOW** | KSEI SID data. Tidak ada scraping |

### 17.2 Prioritas untuk Personal Use

| Prioritas | Faktor | Alasan | Estimasi Effort |
|-----------|--------|--------|-----------------|
| **P1** | Komoditas spesifik IDX | 35% market cap tidak tracked. Impact besar ke decision quality | 1-2 minggu (tambah ticker + relationship) |
| **P2** | Geopolitik & event shock | External_events table sudah ada, tinggal consume | 1 minggu |
| **P3** | Seasonal & kalender | Backtest seasonal pattern dari OHLCV existing | 1 minggu |
| **P4** | Sector rotation | Aggregate stock scores by sector → rotation signal | 1-2 minggu |
| **P5** | Earnings season timing | Forward calendar dari BEI disclosure | 1 minggu (scraping) |

---

## 18. Cara Menggunakan Data Faktor

### 18.1 Pipeline Saat Ini

```
DATA ACQUISITION (EOD)
│
├── yfinance → OHLCV (928 tickers, 2.9M rows)
├── yfinance → Fundamental ratios (991 tickers)
├── yfinance → Global indices (Dow, S&P, Nikkei, etc.)
├── yfinance → Macro (US10Y, gold, oil, USD/IDR)
├── IDX scraper → Foreign flow (103K rows)
├── IDX scraper → Broker flow (15.8K rows)
├── RSS feeds → News (110 rows)
└── yfinance → Corporate actions (6.3K + 5.9K rows)
         │
         ▼
ANALYSIS PIPELINE
│
├── Technical (RSI, MACD, SMA, ADX, ATR, OBV) → score 0-100
├── Fundamental (PER, PBV, ROE, DER, growth) → score 0-100
├── Macro (oil, gold, US10Y, USD/IDR) → score 0-100
├── Global (Dow, S&P, Nikkei, Hang Seng, VIX) → score 0-100
├── Relationship (rolling corr, influence) → score 0-100
├── Sentiment (foreign flow, broker, news) → score 0-100
├── Regime (trending/neutral/volatile/shock) → multiplier
└── No-trade / Gorengan / Manipulation → filter
         │
         ▼
DECISION ENGINE
│
├── Weighted composite: Tech 20% + Fund 25% + Macro 15% + Global 15% + Rel 10% + Sent 15%
├── Regime filter: adjust scores based on macro regime
├── Weight multiplier: redistribute if fundamental missing
└── Output: conviction score 0-100, recommendation (WATCHLIST/ACCUMULATE/BUY/HOLD/REDUCE/SELL)
         │
         ▼
RISK ENGINE
│
├── Position sizing (Kelly, fixed fractional)
├── VaR / CVaR
├── Circuit breaker (daily loss limit)
└── Costs (fees, slippage, tax)
         │
         ▼
EXECUTION
│
├── Paper trading (simulator)
├── Real execution (broker adapter — mock only)
└── Telegram notification
```

### 18.2 Cara Pakai untuk Decision Support

**Sebagai investor ritel personal, alur penggunaan:**

1. **Screener** — jalankan screener untuk filter saham yang memenuhi kriteria:
   - Likuiditas: ADV > 100 lot, turnover > threshold
   - Bukan gorengan: gorengan detector = False
   - Fundamental: PER < 20, ROE > 12%, DER < 2
   - Technical: RSI < 70 (tidak overbought), ADX > 20 (trending)

2. **Compute scores** — untuk setiap saham yang lolos screen:
   - `compute-scores BBCA.JK` → 6 faktor scores
   - `recommend BBCA.JK` → conviction + entry/exit levels
   - `explain BBCA.JK` → XAI narrative (kenapa skor ini)

3. **Validasi manual** — cek faktor yang tidak tercakup:
   - Cek berita terbaru (geopolitik, corporate action)
   - Cek kalender (earnings season, holiday)
   - Cek komoditas spesifik (CPO untuk AALI, coal untuk PTBA)
   - Cek foreign flow trend (apakah asing net buy/sell?)

4. **Risk management** — tentukan position size:
   - Kelly fraction atau fixed fractional
   - VaR check (max loss per position)
   - Portfolio correlation check

5. **Eksekusi** — paper trade dulu, lalu manual di broker app:
   - `paper-trade` untuk simulasi
   - Eksekusi manual di BNI SmartPlus / Sinarmas Online
   - Catat di trade journal

6. **Monitoring** — track performance:
   - `monitor` untuk system health
   - Telegram alert untuk price target / stop loss
   - Periodic rebalance via `rebalancer`

### 18.3 Cara Pakai Macro/Global Data

```
# Contoh: Cek regime pasar sebelum decision
python -c "
from trading_system.analysis.enhanced_regime import EnhancedRegimeEngine
engine = EnhancedRegimeEngine()
result = engine.classify_regime()
print(f'Regime: {result[\"regime\"]}, Confidence: {result[\"confidence\"]}')
# risk_on → lebih agresif (higher position size)
# risk_off → lebih defensif (reduce position, increase cash)
# neutral → normal
"
```

### 18.4 Cara Pakai Foreign Flow Data

```
# Foreign flow = leading indicator untuk IDX
# Persistent foreign net sell (> 5 hari) = bearish signal
# Foreign net buy + broker accumulation = bullish confirmation

# Cek via API:
curl -H "X-API-Key: dev-secret-key-2026" \
  http://localhost:8000/api/foreign-flow?ticker=BBCA.JK&days=30
```

---

## 19. Implementasi di Trading-System

### 19.1 Yang Sudah Terimplementasi

| Faktor | Modul | File | Score? | Weight |
|--------|-------|------|--------|--------|
| Technical | analysis | `technical.py` | ✅ 0-100 | 20% |
| Fundamental | analysis | `fundamental.py` | ✅ 0-100 | 25% |
| Macro | analysis | `macro.py` | ✅ 0-100 | 15% |
| Global market | analysis | `global_market.py` | ✅ 0-100 | 15% |
| Relationship | analysis | `relationship.py` + `lead_lag.py` | ✅ 0-100 | 10% |
| Sentiment | sentiment | `engine.py` + 4 sub-engine | ✅ 0-100 | 15% |
| Regime | analysis | `regime.py` + `enhanced_regime.py` | ✅ Multiplier | Filter |
| Corporate actions | corporate | `actions.py` | ✅ Price adjust | — |
| Mikrostruktur | analysis | `order_book.py` + `liquidity_filter.py` | ✅ Screen | Filter |
| Manipulation | analysis | `manipulation.py` | ✅ Flag | Filter |
| Gorengan | analysis | `gorengan_detector.py` | ✅ Flag | Filter |
| No-trade | analysis | `no_trade.py` | ✅ Gate | Filter |
| Red flags | analysis | `red_flags.py` | ✅ Flag | Warning |
| World monitor | analysis | `world_monitor.py` | ✅ CII score | Context |
| Pipeline | analysis | `pipeline.py` | ✅ Orchestrate | — |
| Decision | decision | `engine.py` | ✅ Composite | — |
| Risk | risk | `engine.py` + `circuit_breaker.py` + `costs.py` | ✅ Position | — |
| XAI | xai | `engine.py` + 4 context | ✅ Narrative | — |
| Backtest | backtest | `engine.py` + `metrics.py` | ✅ Validate | — |
| AI Learning | ai_learning | `engine.py` + `deep_learning.py` + 5 more | ✅ Optimize | — |

### 19.2 Yang Belum Terimplementasi (Prioritas Personal)

| Faktor | Estimasi | Cara Implementasi |
|--------|----------|-------------------|
| **Komoditas spesifik** | 1-2 minggu | Tambah ticker CPO/coal/nickel/copper ke acquisition. Tambah commodity-to-stock mapping di relationship engine. Tambah commodity score ke macro engine |
| **Geopolitik event** | 1 minggu | Consume `external_events` table. Tambah event impact score (0-100) berdasarkan event severity. Tambah alert via Telegram |
| **Seasonal pattern** | 1 minggu | Backtest monthly returns per ticker. Compute seasonal score (bulan X cenderung naik/turun). Tambah ke decision sebagai minor factor |
| **Sector rotation** | 1-2 minggu | Aggregate scores by sector (banking, energy, consumer, etc.). Compute sector momentum. Tambah sector rotation signal |
| **Earnings calendar** | 1 minggu | Scrape BEI disclosure untuk earnings calendar. Tambah pre/post earnings warning |

---

## 20. Gap dan Rekomendasi

### 20.1 Kelengkapan Pustaka

**Sudah lengkap (13 faktor):**
Fundamental, Teknikal, Makro (sebagian), Global (sebagian), Sentimen (sebagian), Relasi, Regime, Corporate actions, Mikrostruktur, Behavioral, Regulasi, World monitor, Pipeline.

**Belum lengkap (9 faktor):**
Geopolitik, Seasonal, Komoditas spesifik, Sector rotation, Insider trading, IPO timing, Earnings season timing, Commodity supercycle, Tax-loss selling.

### 20.2 Rekomendasi untuk Personal Use

**Prioritas 1 — Komoditas Spesifik (Paling Penting):**
IDX = commodity-heavy exchange. Tanpa tracking CPO/coal/nickel, 35% market cap tidak properly analyzed. Implementasi paling mudah: tambah yfinance ticker untuk commodity futures, tambah relationship mapping.

**Prioritas 2 — Geopolitik Event:**
`external_events` dan `policy_events` table sudah ada di DB (298 rows total) tapi tidak ada engine yang consume. Buat simple event impact scorer.

**Prioritas 3 — Seasonal Pattern:**
Data OHLCV 29 tahun (1997-2026) sudah ada. Backtest monthly returns per ticker → seasonal score. Tidak perlu data baru.

**Tidak perlu untuk personal use:**
IPO timing, commodity supercycle, QE/QT tracking, MSCI/FTSE inclusion, retail participation (SID) — ini faktor yang lebih relevan untuk institutional atau akademik, bukan untuk personal decision support EOD.

### 20.3 Update Pustaka yang Diperlukan

| Dokumen | Update | Status |
|---------|--------|--------|
| **NEW: 90-komoditas-spesifik-idx.md** | Dokumen khusus CPO/coal/nickel/copper/tin → stock mapping, price tracking, impact analysis | Perlu dibuat |
| **14-kendala-pasar-modal.md** | Tambah §13: Geopolitik & event shock impact ke IDX | Perlu update |
| **13-hal-yang-perlu-diperhatikan.md** | Tambah §seasonal: January effect, earnings season, Lebaran effect, year-end rally | Perlu update |
| **35-multi-asset-cross-market-analysis.md** | Tambah komoditas spesifik (CPO, Newcastle coal, LME nickel/copper) | Perlu update |

---

## Referensi

### Internal (Pustaka)
- `01-fundamental-pasar-modal.md` — Konsep dasar fundamental
- `03-pasar-modal-global.md` — Pasar global & komoditas
- `05-analisis-teknikal.md` — Analisis teknikal lengkap
- `06-analisis-fundamental.md` — Analisis fundamental lengkap
- `08-trading-algoritmik.md` — Algoritma trading & microstructure
- `09-behavioral-finance.md` — Behavioral finance
- `13-hal-yang-perlu-diperhatikan.md` — Faktor yang perlu diperhatikan
- `14-kendala-pasar-modal.md` — Kendala pasar modal Indonesia
- `15-pelaku-pasar-modal.md` — Pelaku pasar & aliran dana
- `18-modul-engine-data-wajib.md` — Engine spec
- `22-data-engineering-pipeline.md` — Data pipeline
- `24-market-microstructure-likuiditas.md` — Microstructure
- `35-multi-asset-cross-market-analysis.md` — Cross-market analysis
- `76-idx-trading-rules-market-mechanics.md` — IDX trading rules
- `87-regulatory-developments-2026.md` — Regulasi 2026

### Internal (Codebase)
- `src/trading_system/analysis/` — 27 modul analysis
- `src/trading_system/sentiment/` — 6 modul sentiment
- `src/trading_system/decision/engine.py` — Decision engine
- `src/trading_system/risk/` — Risk engine
- `src/trading_system/corporate/actions.py` — Corporate actions

---

> **Catatan:** Pustaka sudah cukup lengkap untuk 13 dari 22 faktor utama yang mempengaruhi pasar modal. 9 faktor belum dibahas mendalam, dengan **komoditas spesifik IDX** sebagai gap paling kritis (35% market cap tidak tracked). Untuk personal use EOD, prioritas penutupan gap: (1) komoditas spesifik, (2) geopolitical event, (3) seasonal pattern. Faktor institusional/akademik (IPO timing, QE/QT, MSCI inclusion) tidak perlu untuk personal decision support.
