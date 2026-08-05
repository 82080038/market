# Multi-Market & Multi-Asset Trading System

> **Dokumen 92** | Pustaka Pengetahuan Pasar Modal Indonesia/Global
>
> **Tujuan:** Merancang ekstensi aplikasi single-user dari trading saham Indonesia (IDX) ke **multi-pasar** dan **multi-aset**. Dokumen ini memetakan modul, engine, AI/ML, pengambil keputusan, pemberi rekomendasi, OMS, risk, portofolio, dan roadmap implementasi untuk aset lintas bursa dan lintas instrumen.
>
> **Scope:** Personal decision-support dengan jalur menuju paper trading dan live trading terkontrol. Single-user, bukan platform publik. Fitur multi-user, KYC, RBAC, dan enterprise security tetap **tidak relevan**.
>
> **Cross-reference:** Lihat `91-komoditas-spesifik-idx.md` untuk fondasi komoditas → saham IDX; `35-multi-asset-cross-market-analysis.md` untuk analisis korelasi lintas pasar; `04-instrumen-pasar-modal.md` untuk jenis instrumen; `40-oms-ems-architecture.md` untuk fondasi OMS; `18-modul-engine-data-wajib.md` untuk fondasi modul saham Indonesia.

---

## Daftar Isi

1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif)
2. [Keputusan Desain & Batasan](#2-keputusan-desain--batasan)
3. [Market & Asset Class Registry](#3-market--asset-class-registry)
4. [Spesifikasi Modul/Engine (5W1H)](#4-spesifikasi-modulengine-5w1h)
5. [Arsitektur AI/ML](#5-arsitektur-aiml)
6. [Alur Decision & Recommendation](#6-alur-decision--recommendation)
7. [Ekstensi Skema Database](#7-ekstensi-skema-database)
8. [Desain API](#8-desain-api)
9. [Risk & Compliance per Yurisdiksi](#9-risk--compliance-per-yurisdiksi)
10. [Roadmap Implementasi](#10-roadmap-implementasi)
11. [Referensi & Cross-Reference](#11-referensi--cross-reference)

---

## 1. Ringkasan Eksekutif

Aplikasi yang sudah dirancang di `18-modul-engine-data-wajib.md` dan `83-advisory-system-screening-to-recommendation.md` berorientasi pada **saham Indonesia (IDX)**. Dokumen ini menambahkan layer abstraksi **market** dan **asset_class** sehingga satu sistem yang sama dapat:

- Menganalisis saham di **IDX, US (NYSE/Nasdaq), HKEX, SGX, TSE**, dan bursa lain yang didukung Yahoo Finance.
- Memantau instrumen **ETF, obligasi/reksa dana, komoditas, forex, kripto, serta derivatif (opsi/futures)** sebagai aset referensi atau tradeable.
- Menghitung skor multi-faktor, VaR, dan rekomendasi untuk setiap pasar dengan aturan bursa, biaya, pajak, dan timezone yang berbeda.
- Menjalankan **paper trading** lintas pasar dan — setelah validasi — eksekusi live melalui broker adapter yang tepat.

Fondasi tetap: single-user, UTC storage, display WIB, GPU `cuda:1`, `.env` untuk kredensial, audit trail.

---

## 2. Keputusan Desain & Batasan

| Keputusan | Nilai | Alasan |
|-----------|-------|--------|
| **Aset utama fase awal** | Saham global + ETF | Data publik melalui Yahoo Finance, likuiditas tinggi, regulasi paling sederhana. |
| **Aset sekunder** | Obligasi, komoditas, forex, kripto, derivatif | Digunakan sebagai **input faktor** dulu; trading langsung pada fase lanjut. |
| **Sumber data primer** | Yahoo Finance + broker adapter | Gratis/berbayar fleksibel; suffix ticker menentukan market (`.JK`, `.L`, `.T`, `.HK`, dll.) — `03-pasar-modal-global.md` §2. |
| **Timezone** | UTC internal; WIB display default; market local time untuk schedule per bursa. | Menghindari bug saat overlap dan DST — `36-gap-data-timezone-global-idx.md` §1. |
| **Mata uang dasar** | IDR untuk reporting; mata uang asli instrumen disimpan untuk audit. | Pengguna di Indonesia; cross-currency PnL harus dikonversi harian. |
| **Eksekusi real** | Human-gate wajib; paper trading wajib 30 hari per market/strategi baru. | Mengurangi risk live trading lintas pasar — `85-backtest-to-live-gap-prevention.md`. |
| **Instrumen tidak didukung di fase awal** | Short-selling, margin, leverage >1× untuk market baru | Kompleksitas regulasi & risk; ditambahkan setelah MVP stabil. |

---

## 3. Market & Asset Class Registry

### 3.1 Model Data

```python
from enum import StrEnum
from pydantic import BaseModel
from decimal import Decimal
from datetime import time

class AssetClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    BOND = "bond"
    MUTUAL_FUND = "mutual_fund"
    COMMODITY = "commodity"
    FOREX = "forex"
    CRYPTO = "crypto"
    DERIVATIVE_FUTURES = "derivative_futures"
    DERIVATIVE_OPTIONS = "derivative_options"
    WARRANT = "warrant"
    SUKUK = "sukuk"

class MarketStatus(StrEnum):
    ACTIVE = "active"
    HALTED = "halted"
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"

class MarketRegistry(BaseModel):
    mic_code: str               # ISO 10383, e.g. XIDX, XNYS, XNAS, XHKG
    country_code: str           # ISO 3166-1 alpha-3, e.g. IDN, USA, HKG
    timezone: str               # IANA, e.g. Asia/Jakarta, America/New_York
    trading_hours: list[tuple[time, time]]
    supports_dst: bool
    settlement_cycle: int       # T+1, T+2, T+3
    tick_size_rule: str         # reference to rule file
    lot_size: int | None        # None for fractional markets
    currency: str               # ISO 4217, e.g. IDR, USD, HKD
    data_suffix: str | None     # e.g. .JK, .L, .T, .HK
    trading_status: MarketStatus
```

### 3.2 Asset Class Configuration

```python
ASSET_CLASS_CONFIG = {
    AssetClass.EQUITY: {
        "tradeable": True,
        "needs_fundamental": True,
        "default_data_source": "yahoo_finance",
        "risk_profile": "equity_single_stock",
    },
    AssetClass.ETF: {
        "tradeable": True,
        "needs_fundamental": False,
        "default_data_source": "yahoo_finance",
        "risk_profile": "equity_etf",
    },
    AssetClass.BOND: {
        "tradeable": True,
        "needs_fundamental": True,
        "default_data_source": "yahoo_finance",
        "risk_profile": "fixed_income",
    },
    AssetClass.COMMODITY: {
        "tradeable": False,   # Fase awal: faktor saja
        "needs_fundamental": False,
        "default_data_source": "yahoo_finance",
        "risk_profile": "commodity",
    },
    AssetClass.FOREX: {
        "tradeable": False,   # Fase awal: faktor saja
        "needs_fundamental": False,
        "default_data_source": "yahoo_finance",
        "risk_profile": "fx",
    },
    AssetClass.CRYPTO: {
        "tradeable": False,   # Fase awal: faktor/screening saja
        "needs_fundamental": False,
        "default_data_source": "yahoo_finance",
        "risk_profile": "crypto",
    },
    AssetClass.DERIVATIVE_OPTIONS: {
        "tradeable": False,
        "needs_fundamental": False,
        "default_data_source": "broker",
        "risk_profile": "derivative",
    },
}
```

### 3.3 Instrument Master Schema

Tabel `instrument_master` perlu di-extend dari `18-modul-engine-data-wajib.md` §13:

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `ticker` | TEXT | Ticker unik sistem, e.g. `AAPL`, `AAPL.US`, `BBCA.JK` |
| `market_mic` | TEXT | Referensi ke `market_registry.mic_code` |
| `asset_class` | TEXT | `AssetClass` |
| `base_currency` | TEXT | Mata uang asli instrumen |
| `reporting_currency` | TEXT | IDR default |
| `lot_size` | INTEGER | Nullable untuk fractional |
| `tick_size` | REAL | Minimal perubahan harga |
| `is_active` | BOOLEAN | Listing/delisting |
| `sector` | TEXT | Sektor global/IDX |
| `underlying_ticker` | TEXT | Untuk ETF/derivatif/warrant |

---

## 4. Spesifikasi Modul/Engine (5W1H)

### 4.1 Multi-Market Data Acquisition Engine

- **What:** Mengambil OHLCV, fundamental, macro, dan corporate actions dari berbagai bursa dan kelas aset.
- **Why:** Tanpa data ternormalisasi lintas pasar, korelasi dan rekomendasi multi-aset tidak valid.
- **When:** Dijalankan harian setelah close setiap market, plus on-demand.
- **Where:** `src/market/data/acquisition/multi_market.py`.
- **Who:** Scheduler atau user via CLI/API.
- **How:** Adapter pattern per sumber (`YahooFinanceAdapter`, `BrokerAdapter`, `ManualCSVAdapter`). Setiap adapter mengembalikan `NormalizedOHLCV` dengan kolom standar.
- **Output:** Event `data.raw.multi_market.<mic>.<ticker>`, raw Parquet di `/media/petrick/Parquet/market_data/raw/`, metadata source health.

```python
class NormalizedOHLCV(BaseModel):
    ticker: str
    market_mic: str
    asset_class: AssetClass
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted_close: Decimal
    currency: str
    source: str
    data_quality_score: float
```

### 4.2 Market Calendar & Timezone Engine

- **What:** Mengetahui hari kerja, jam perdagangan, libur bursa, DST, dan overlap antar pasar.
- **Why:** Scheduler, risk checks, dan UI harus tahu kapan market buka/tutup — `36-gap-data-timezone-global-idx.md` §1.
- **When:** Dipanggil sebelum setiap fetch, backtest, dan eksekusi.
- **Where:** `src/market/data/calendar/market_calendar.py`.
- **Who:** Scheduler, OMS, UI.
- **How:** Gunakan `exchange_calendars` library + custom override untuk IDX/libur Indonesia. Simpan ke tabel `market_calendar`.
- **Output:** `MarketSession` object: status, next open/close, overlap flags.

```python
class MarketSession(BaseModel):
    mic_code: str
    local_date: date
    is_trading_day: bool
    pre_market: tuple[datetime, datetime] | None
    regular_session: tuple[datetime, datetime] | None
    post_market: tuple[datetime, datetime] | None
    has_dst_transition: bool
```

### 4.3 FX & Currency Risk Engine

- **What:** Mengelola konversi mata uang dan risiko FX untuk PnL/reporting.
- **Why:** Portfolio multi-pasar memiliki exposure mata uang (USD, HKD, JPY, dll.) terhadap IDR.
- **When:** Setiap perhitungan PnL, risk, dan rekomendasi.
- **Where:** `src/market/risk/fx_engine.py`.
- **Who:** Risk engine, portfolio engine, reporting.
- **How:** Fetch `USDIDR=X`, `HKDIDR=X`, dll. dari Yahoo; gunakan spot harian. Simpan `fx_rates` table. Jika data tidak tersedia, gunakan fallback IDR terakhir dengan flag.
- **Output:** `FXRate` + `FXExposure` per portfolio.

### 4.4 Multi-Asset Technical Analysis Engine

- **What:** Menghitung indikator teknikal untuk semua kelas aset yang memiliki OHLCV.
- **Why:** Price action dan volatilitas dapat dibandingkan lintas pasar.
- **When:** Setelah data harian masuk.
- **Where:** `src/market/analysis/technical.py` (extend existing).
- **Who:** Analysis pipeline.
- **How:** Gunakan fungsi vectorized yang sama seperti saham IDX; berikan weight berbeda untuk aset dengan volatilitas tinggi (crypto, commodity).
- **Output:** `technical_score` 0-100 + breakdown per instrumen.

### 4.5 Fundamental Analysis Engine (per Asset Class)

- **What:** Menghitung metrik valuasi sesuai kelas aset.
- **Why:** PER/PBV tidak relevan untuk obligasi, ETF, atau komoditas — `04-instrumen-pasar-modal.md` §2.
- **When:** Periodik: saham (quarterly), obligasi (monthly), ETF (daily NAV).
- **Where:** `src/market/analysis/fundamental.py`.
- **Who:** Analysis pipeline.
- **How:** Strategy pattern:
  - `EquityFundamentalScorer`: PER, PBV, ROE, DER, EPS growth.
  - `BondFundamentalScorer`: YTM, duration, credit rating, spread.
  - `ETFFundamentalScorer`: expense ratio, tracking error, AUM.
  - `CryptoFundamentalScorer`: on-chain metrics (opsional fase lanjut).
- **Output:** `fundamental_score` + breakdown + `missing_fields` flag.

### 4.6 Macro & Global Market Engine

- **What:** Mengumpulkan indeks global, suku bunga, inflasi, dan komoditas sebagai faktor makro.
- **Why:** Pasar global mempengaruhi IDX dan aset lain — `35-multi-asset-cross-market-analysis.md` §1.
- **When:** Harian.
- **Where:** `src/market/analysis/macro_global.py`.
- **Who:** Decision engine, XAI.
- **How:** Fetch `^GSPC`, `^IXIC`, `^N225`, `^HSI`, `^TNX`, `GC=F`, `CL=F`, `DX-Y.NYB`, `USDIDR=X`.
- **Output:** `macro_score` dan `global_market_score` per market.

### 4.7 Cross-Market Relationship Engine

- **What:** Menghitung korelasi, lead-lag, spillover, dan cointegrasi antar aset/pasar.
- **Why:** Identifikasi diversifikasi nyata vs false diversification.
- **When:** Mingguan (rolling window 60 hari) atau setelah event besar.
- **Where:** `src/market/analysis/relationship.py` (extend existing).
- **Who:** Portfolio optimizer, risk engine.
- **How:** Rolling correlation, Granger causality, transfer entropy, DCC-GARCH approximation — `35-multi-asset-cross-market-analysis.md` §2-4.
- **Output:** `relationship_matrix` table + cluster groups + lead-lag signals.

### 4.8 Multi-Asset Sentiment Engine

- **What:** Menggabungkan sentimen dari news, social media, foreign flow, dan broker flow untuk multi-pasar.
- **Why:** Sentimen pasar asing (US, China) berdampak ke IDX.
- **When:** Harian.
- **Where:** `src/market/sentiment/engine.py`.
- **Who:** Decision engine, XAI.
- **How:** NLP Bahasa Indonesia untuk IDX; NLP English untuk US/global; agregasi per market.
- **Output:** `sentiment_score` per ticker + market-level fear/greed proxy.

### 4.9 AI/ML Pattern & Regime Engine

- **What:** Deteksi pola, regime pasar, dan bobot faktor optimal lintas pasar.
- **Why:** Pola di IDX tidak selalu sama dengan US atau crypto.
- **When:** Setiap periode backtest/retrain; gunakan walk-forward untuk menghindari overfit — `23-machine-learning-trading.md`.
- **Where:** `src/market/ai_learning/multi_asset.py`.
- **Who:** Decision engine.
- **How:**
  - Regime detection: HMM atau rolling volatility per market.
  - Transfer learning: train di US, fine-tune di IDX (atau sebaliknya) untuk aset yang memiliki korelasi tinggi.
  - Feature store: 42+ fitur per ticker per pasar — `58-feature-store-engineering-pipeline.md`.
- **Output:** `regime_label`, `optimal_weights` per market/regime, `pattern_reliability`.

### 4.10 Multi-Asset Decision Engine

- **What:** Menghasilkan skor keputusan 0-100 per instrumen berdasarkan bobot faktor yang dapat bervariasi per `asset_class` dan `market_mic`.
- **Why:** Saham, obligasi, ETF, dan crypto memiliki driver yang berbeda.
- **When:** Setelah semua analysis engine selesai.
- **Where:** `src/market/decision/engine.py`.
- **Who:** Recommendation engine, UI.
- **How:**
  - Default weights per `AssetClass`.
  - Regime-based weight adjustment (misal: risk-off → fundamental & bond weight naik, crypto weight turun).
  - Missing data handling: auto-redistribute weight.
- **Output:** `composite_score`, `confidence`, `regime_adjusted_weights`.

```python
DEFAULT_WEIGHTS = {
    AssetClass.EQUITY:    {"technical": 0.20, "fundamental": 0.25, "macro": 0.15, "global": 0.15, "sentiment": 0.15, "relationship": 0.10},
    AssetClass.ETF:       {"technical": 0.25, "fundamental": 0.10, "macro": 0.20, "global": 0.20, "sentiment": 0.15, "relationship": 0.10},
    AssetClass.BOND:      {"technical": 0.10, "fundamental": 0.35, "macro": 0.30, "global": 0.10, "sentiment": 0.10, "relationship": 0.05},
    AssetClass.COMMODITY: {"technical": 0.25, "fundamental": 0.05, "macro": 0.30, "global": 0.20, "sentiment": 0.15, "relationship": 0.05},
}
```

### 4.11 Advisory / Recommendation Engine

- **What:** Mengubah skor, risk metrics, dan backtest evidence menjadi saran `BUY/HOLD/SELL` dengan alasan empiris.
- **Why:** Pengguna butuh rekomendasi yang dapat dijelaskan, bukan hanya angka — `83-advisory-system-screening-to-recommendation.md`.
- **When:** On-demand via API atau saat daily run.
- **Where:** `src/market/advisory/engine.py`.
- **Who:** User via UI/API.
- **How:**
  - Threshold per `AssetClass` (contoh: BUY jika score ≥75 untuk equity, ≥65 untuk ETF).
  - Position sizing: risk per trade × conviction × ATR/volatility per market.
  - Entry/exit: technical levels + market session rules.
  - XAI narrative: top 3 contributors, regime context, warning flags.
- **Output:** `Recommendation` object.

```python
class Recommendation(BaseModel):
    recommendation_id: str
    ticker: str
    market_mic: str
    asset_class: AssetClass
    action: str               # BUY / HOLD / SELL / WATCH
    conviction_score: float
    position_size_pct: float
    entry_price_range: list[Decimal]
    stop_loss: Decimal | None
    take_profit: Decimal | None
    expected_hold_period: str
    risk_flags: list[str]
    xai_narrative_id: str
    created_at: datetime
```

### 4.12 Multi-Asset Risk Engine

- **What:** Menghitung VaR, CVaR, exposure, correlation, drawdown, dan currency risk untuk portfolio lintas pasar.
- **Why:** Diversifikasi lintas pasar mengurangkan risk hanya jika korelasi rendah; risk engine harus memantau perubahan korelasi.
- **When:** Harian dan sebelum setiap rekomendasi/order.
- **Where:** `src/market/risk/engine.py`.
- **Who:** Decision engine, portfolio engine, OMS.
- **How:**
  - Historical simulation VaR per currency bucket.
  - Stress test: US crash, China slowdown, IDR shock, commodity spike.
  - FX risk overlay: jika exposure USD > threshold, beri warning.
- **Output:** `risk_report`, `max_drawdown`, `var_95`, `currency_exposure`.

### 4.13 Multi-Asset Portfolio Optimization & Attribution

- **What:** Alokasi modal lintas pasar dan kelas aset yang mengoptimalkan risk-adjusted return.
- **Why:** Personal investor memiliki modal terbatas; alokasi efisien penting — `21-portfolio-optimization-construction.md`.
- **When:** Mingguan/bulanan atau saat drift > threshold.
- **Where:** `src/market/portfolio/optimizer.py`.
- **Who:** Rebalancer, UI.
- **How:**
  - Hierarchical Risk Parity (HRP) untuk clustering korelasi antar pasar.
  - Black-Litterman untuk blending market-implied returns dengan view AI.
  - Constraint: minimal trade size, lot size, broker fee, tax.
- **Output:** `target_allocation`, `rebalance_orders`, `attribution_report`.

### 4.14 Multi-Market Execution / OMS Engine

- **What:** Order Management System yang memahami aturan setiap bursa.
- **Why:** Order yang valid di IDX bisa tidak valid di NYSE atau HKEX — `40-oms-ems-architecture.md`.
- **When:** Saat user atau automated system mengirim order.
- **Where:** `src/market/execution/oms.py`.
- **Who:** Execution engine, paper trading, live broker adapters.
- **How:**
  - Validasi order: lot size, tick size, market session, price limits, buying power.
  - Routing ke `BrokerAdapter` yang tepat per `market_mic`.
  - State machine: `new → pending → partial → filled / cancelled / rejected`.
  - Idempotency & fill processor.
- **Output:** `Order`, `Fill`, `OrderStatus`.

```python
class Order(BaseModel):
    order_id: str
    ticker: str
    market_mic: str
    side: str               # BUY / SELL
    quantity: int
    order_type: str         # MARKET / LIMIT / STOP
    limit_price: Decimal | None
    currency: str
    broker: str
    paper: bool             # True = simulation
```

### 4.15 Multi-Market UI & Presentation Engine

- **What:** Dashboard yang menampilkan watchlist, portfolio, rekomendasi, dan chart untuk multi-pasar.
- **Why:** Pengguna butuh satu tampilan untuk semua aset dengan informasi timezone & mata uang.
- **When:** On-demand; real-time (EOD) updates.
- **Where:** `frontend/app/` (Next.js).
- **Who:** End user.
- **How:**
  - Market selector di header.
  - Tooltip Bahasa Indonesia untuk istilah teknis.
  - Tampilkan waktu lokal bursa, status market (open/closed), dan converted PnL ke IDR.
  - Chart multi-axis: overlay IHSG vs S&P 500 vs HSI.
- **Output:** Halaman dashboard, stock detail, portfolio, backtest, analysis, settings.

---

## 5. Arsitektur AI/ML

### 5.1 Layer AI/ML Multi-Pasar

```
Data Layer (OHLCV + Fundamental + Macro + Sentiment)
        ↓
Feature Store (asset_class + market_mic tagged)
        ↓
Regime Detection (HMM / rolling vol per market)
        ↓
Pattern Memory (win rate per pattern per market)
        ↓
Model Ensemble:
  - LightGBM / XGBoost untuk scoring
  - LSTM untuk time-series forecasting (GPU cuda:1)
  - Transfer learning dari market besar ke market kecil
        ↓
Eval-Gated Promotion (champion/challenger per market)
        ↓
Decision Engine → Advisory Engine
```

### 5.2 Transfer Learning & Cold Start

- Market dengan data history panjang (US, JP) digunakan sebagai **source model**.
- Market dengan data pendek (IDX untuk aset tertentu) di-**fine-tune** dengan freeze layer tertentu.
- Crypto: gunakan model khusus karena volatilitas dan regime yang berbeda.

### 5.3 Feature Store Multi-Pasar

Setiap fitur di-tagged dengan `market_mic` dan `asset_class` — `58-feature-store-engineering-pipeline.md`. Contoh fitur:

| Fitur | Keterangan | Tag |
|-------|------------|-----|
| `rsi_14` | RSI 14 hari | all |
| `per_ttm` | Price/Earnings trailing 12m | equity, etf |
| `ytm` | Yield to Maturity | bond |
| `crypto_mvrv` | MVRV ratio | crypto (opsional) |
| `fx_usdidr_change_5d` | Perubahan USD/IDR 5 hari | all |

---

## 6. Alur Decision & Recommendation

```
1. Scheduler trigger per market (after close)
2. Fetch & validate data
3. Run analysis engines per asset_class
4. Run cross-market relationship engine
5. Run regime detection
6. Adjust factor weights per regime
7. Compute composite score
8. Risk engine: VaR, FX exposure, correlation stress
9. Advisory engine: generate BUY/HOLD/SELL + position size + entry/exit
10. XAI narrative: explain top factors
11. Store recommendation + audit log
12. UI presents recommendation; paper/live execution gated
```

---

## 7. Ekstensi Skema Database

Tabel baru atau kolom tambahan pada skema yang sudah ada di `18-modul-engine-data-wajib.md` §13:

```sql
-- Market registry
CREATE TABLE market_registry (
    mic_code TEXT PRIMARY KEY,
    country_code TEXT NOT NULL,
    timezone TEXT NOT NULL,
    trading_hours TEXT NOT NULL,          -- JSON array of [start, end]
    supports_dst BOOLEAN NOT NULL,
    settlement_cycle INTEGER NOT NULL,
    tick_size_rule TEXT,
    lot_size INTEGER,
    currency TEXT NOT NULL,
    data_suffix TEXT,
    trading_status TEXT NOT NULL
);

-- FX rates
CREATE TABLE fx_rates (
    pair TEXT NOT NULL,
    date TEXT NOT NULL,
    rate REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (pair, date)
);

-- Extend instrument_master
ALTER TABLE instrument_master ADD COLUMN market_mic TEXT REFERENCES market_registry(mic_code);
ALTER TABLE instrument_master ADD COLUMN asset_class TEXT NOT NULL DEFAULT 'equity';
ALTER TABLE instrument_master ADD COLUMN base_currency TEXT NOT NULL DEFAULT 'IDR';
ALTER TABLE instrument_master ADD COLUMN lot_size INTEGER;
ALTER TABLE instrument_master ADD COLUMN tick_size REAL;
ALTER TABLE instrument_master ADD COLUMN underlying_ticker TEXT;

-- Orders multi-market
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    market_mic TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    order_type TEXT NOT NULL,
    limit_price REAL,
    currency TEXT NOT NULL,
    broker TEXT NOT NULL,
    paper BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## 8. Desain API

Endpoint baru (extend dari `28-api-design-integration-patterns.md`):

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/api/markets` | Daftar market yang aktif + status sesi |
| GET | `/api/markets/{mic}/calendar` | Kalender bursa |
| GET | `/api/fx/rates` | Daftar kurs FX terbaru |
| GET | `/api/instruments?market_mic=&asset_class=` | Daftar instrumen dengan filter |
| GET | `/api/instruments/{ticker}` | Detail instrumen + market info |
| GET | `/api/scores/{ticker}` | Skor multi-faktor per instrumen |
| GET | `/api/recommend/{ticker}` | Rekomendasi + XAI narrative |
| GET | `/api/relationships?market_a=&market_b=` | Korelasi antar market |
| POST | `/api/backtest/multi-market` | Backtest portfolio lintas pasar |
| POST | `/api/paper-trade` | Simulasi order lintas pasar |
| POST | `/api/orders` | Kirim order (paper/live) |
| GET | `/api/portfolio/multi-market` | Portfolio PnL multi-currency |
| GET | `/api/risk/multi-market` | VaR & FX exposure |

---

## 9. Risk & Compliance per Yurisdiksi

| Yurisdiksi | Aspek Kunci | Implikasi Sistem |
|------------|-------------|------------------|
| **Indonesia (IDX)** | PPh final 0.1%, dividen 10%, lot 100, ARA/ARB 15-25% | Implementasi penuh — `25-pajak-akuntansi-trading.md`, `76-idx-trading-rules-market-mechanics.md` |
| **US (NYSE/Nasdaq)** | T+1 settlement, fractional shares, SEC rule (pattern day trader $25k), wash sale | Validasi order; tax report placeholder; tidak disarankan day trading kecil — `03-pasar-modal-global.md` §3.2 |
| **Hong Kong/Singapore** | Lot size bervariasi, T+2, stamp duty | Parameter per market di `market_registry` |
| **Crypto** | Tidak ada settlement T+n, 24/7, high volatilitas | Risk engine khusus; human-gate wajib |
| **Derivatif** | Margin, expiry, Greeks | Fase lanjut; wajib risk warning eksplisit |
| **UU PDP Indonesia** | Data pribadi user wajib dilindungi | `.env` untuk kredensial, tidak menyimpan PII di log — `41-uu-pdp-compliance-fintech.md` |

---

## 10. Roadmap Implementasi

Roadmap ini merupakan **ekstensi** dari roadmap 24 minggu di `92-multi-market-multi-asset-trading-system.md` §10, dengan asumsi MVP saham Indonesia sudah stabil.

| Fase | Durasi | Fokus | Deliverables |
|------|--------|-------|--------------|
| **M-1** | 2-3 minggu | Market Registry & Multi-asset Instrument Master | Tabel `market_registry`, `instrument_master` extended, `asset_class` config |
| **M-2** | 2-3 minggu | Multi-market Data Acquisition + FX Engine | Adapter Yahoo multi-suffix, `fx_rates`, calendar engine, quality validation |
| **M-3** | 3 minggu | Cross-Market Analysis & Relationship Engine | Correlation matrix, lead-lag, spillover, heatmap UI |
| **M-4** | 3 minggu | Multi-Asset Decision & Advisory Engine | Per-asset weights, thresholds, XAI narrative, `/api/recommend/{ticker}` multi-market |
| **M-5** | 2 minggu | Multi-Asset Risk & Portfolio Optimization | HRP, FX exposure, stress test, rebalancing |
| **M-6** | 3 minggu | Multi-Market OMS & Paper Trading | Order validation per market, paper broker, state machine |
| **M-7** | 2 minggu | AI/ML Multi-Asset & Transfer Learning | Regime detection, transfer learning, eval-gated promotion per market |
| **M-8** | 2 minggu | UI Multi-Market, Reporting, Compliance Polish | Market selector, multi-currency PnL, tax/audit report per yurisdiksi |

**Total estimasi:** 17-20 minggu tambahan setelah MVP IDX stabil.

---

## 11. Referensi & Cross-Reference

- Fondasi instrumen: `04-instrumen-pasar-modal.md`
- Pasar global & bursa: `03-pasar-modal-global.md`
- Analisis multi-aset & cross-market: `35-multi-asset-cross-market-analysis.md`
- Zona waktu & gap data global: `36-gap-data-timezone-global-idx.md`
- Komoditas → saham IDX: `91-komoditas-spesifik-idx.md`
- OMS/EMS: `40-oms-ems-architecture.md`
- Modul/engine wajib (IDX): `18-modul-engine-data-wajib.md`
- Advisory & rekomendasi: `83-advisory-system-screening-to-recommendation.md`
- AI/ML trading: `23-machine-learning-trading.md`
- Risk management: `07-manajemen-risiko.md`, `31-risk-management-lanjutan.md`
- Portfolio optimization: `21-portfolio-optimization-construction.md`
- Feature store: `58-feature-store-engineering-pipeline.md`
- Pajak & akuntansi Indonesia: `25-pajak-akuntansi-trading.md`
- Backtest-to-live gap prevention: `85-backtest-to-live-gap-prevention.md`
- Gigantic AI self-evolution: `86-gigantic-ai-autonomous-trading-system.md`

---

> **Catatan:** Dokumen ini adalah blueprint. Prioritas implementasi dapat disesuaikan dengan akses data, biaya broker, dan kebutuhan pengguna. Disarankan memulai dari **saham global (US, HK) dan ETF** karena data publik tersedia dan likuiditas tinggi, baru kemudian mengembangkan obligasi, komoditas, forex, dan derivatif.
