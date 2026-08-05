# Panduan Membangun Aplikasi Pasar Modal

> **Tujuan:** Dokumen ini adalah sintesis dari seluruh knowledge base di `pustaka/` — merujuk ke setiap dokumen dan mengoutline bagaimana pengetahuan tersebut dapat digunakan untuk membangun aplikasi pasar modal yang lengkap, profesional, dan production-ready.

---

## Daftar Isi

1. [Visi Aplikasi](#1-visi-aplikasi)
2. [Arsitektur Sistem](#2-arsitektur-sistem)
3. [Modul Data Acquisition](#3-modul-data-acquisition)
4. [Modul Analisis Teknikal](#4-modul-analisis-teknikal)
5. [Modul Analisis Fundamental](#5-modul-analisis-fundamental)
6. [Modul Sentimen & Behavioral](#6-modul-sentimen--behavioral)
7. [Modul Decision Engine](#7-modul-decision-engine)
8. [Modul Risk Management](#8-modul-risk-management)
9. [Modul Backtesting](#9-modul-backtesting)
10. [Modul Execution](#10-modul-execution)
11. [Modul Portfolio Management](#11-modul-portfolio-management)
12. [Modul AI/ML](#12-modul-aiml)
13. [Modul XAI (Explainable AI)](#13-modul-xai-explainable-ai)
14. [API Design](#14-api-design)
15. [Frontend](#15-frontend)
16. [Compliance & Regulasi](#16-compliance--regulasi)
17. [Testing & Deployment](#17-testing--deployment)
18. [Roadmap Pengembangan](#18-roadmap-pengembangan)
19. [Referensi Silang](#19-referensi-silang)

---

## 1. Visi Aplikasi

### 1.1 Deskripsi

Aplikasi pasar modal adalah sistem **decision support** yang membantu investor membuat keputusan investasi yang terinformasi dengan menggabungkan:

- **Analisis teknikal** (indikator harga/volume)
- **Analisis fundamental** (laporan keuangan, valuasi)
- **Analisis makro** (suku bunga, inflasi, ekonomi)
- **Analisis global** (pasar dunia, komoditas, forex)
- **Analisis sentimen** (berita, social media, foreign flow)
- **Manajemen risiko** (position sizing, VaR, drawdown control)
- **AI/ML** (optimasi bobot, prediksi, walk-forward)

### 1.2 Prinsip Desain

Mengadopsi dari `11-knowledge-transfer-aplikasi.md`:

1. **Single source of truth** — konfigurasi terpusat
2. **Modular monolith** — boundary jelas, tanpa network overhead
3. **Versioned outputs** — setiap engine sertakan version
4. **Reason codes** — setiap keputusan disertai alasan
5. **Guard everything** — validasi semua input
6. **PIT-safe** — point-in-time accuracy untuk backtesting
7. **Fail-fast** — crash di startup > jalan tanpa keamanan
8. **Two-tier storage** — SQLite hot + Parquet cold
9. **Empirical calibration** — test, jangan menebak
10. **Test determinism** — fixture autouse, tidak terpengaruh env

### 1.3 Keputusan Desain Tetap

Berikut keputusan desain yang berlaku untuk seluruh modul aplikasi (lihat `00-README.md` bagian "Keputusan Desain Aplikasi" untuk detail lengkap):

| Keputusan | Ringkasan | Dokumen Referensi |
|-----------|-----------|-------------------|
| **Frontend Bahasa Indonesia** | Semua UI dalam Bahasa Indonesia. Istilah/singkatan pasar modal yang tidak dapat diterjemahkan wajib memiliki tooltip penjelasan. | `32-ui-ux-design-trading-app.md` §13 |
| **Timezone GMT+7 (WIB)** | Aplikasi dijalankan di GMT+7. Storage UTC, display WIB. Semua operasi terjadwal (render, backtest, PnL, risk, portfolio, AI/ML, strategy testing) memperhitungkan jam IDX, overlap bursa global, overnight gap, dan DST. | `36-gap-data-timezone-global-idx.md` §9 |
| **Single-User Application** | Hanya satu user. Tidak perlu multi-user auth, RBAC, JWT, OAuth, KYC, atau rate limiting per-user. Security minimal: `.env` untuk config, broker API key tetap aman, audit trail untuk debugging. | `33-cybersecurity-trading-system.md` §13 |
| **GPU/CUDA Wajib Diperiksa** | Setiap modul compute-bound wajib periksa GPU. 2x GTX 1050 Ti (4GB VRAM), prefer `cuda:1`. PyTorch 2.5.1+cu121. Batasan: batch ≤64, hidden ≤256, FP32 primary. | `34-performance-engineering-optimization.md` §13 |

---

## 2. Arsitektur Sistem

### 2.1 Modular Monolith

```
src/market_app/
  data/               # Acquisition, storage, validation
    acquisition.py    # Yahoo Finance, idx.co.id scraper
    storage.py        # SQLite CRUD
    validation.py     # Data quality checks
    seeder.py         # Instrument master seeder
    archive.py        # Parquet archival
    rate_limiter.py   # Adaptive rate limiter
  
  analysis/           # Analysis engines
    technical.py      # RSI, MACD, Bollinger, ATR, Ichimoku
    fundamental.py    # P/E, ROE, ROIC, DCF
    macro.py          # BI rate, inflation, GDP
    global_market.py  # S&P 500, oil, gold, USD/IDR
    relationship.py   # Correlation, lead-lag
    regime.py         # Market regime detection
    screener.py       # Stock screener
  
  sentiment/          # Sentiment engines
    engine.py         # Indonesian NLP sentiment
    foreign_flow.py   # Foreign net buy/sell
    broker_summary.py # Broker concentration
    social_media.py   # Reddit, X
    google_trends.py  # Search interest
  
  decision/           # Multi-factor decision
    engine.py         # Weighted scoring, conviction
  
  risk/               # Risk management
    var.py            # VaR, CVaR
    position_sizing.py # Kelly, ATR-based
    drawdown.py       # Drawdown monitoring
    kelly.py          # Kelly criterion
  
  execution/          # Order execution
    broker_adapter.py # Mock + real broker
    paper_trading.py  # Paper trading simulator
  
  backtest/           # Backtesting
    engine.py         # Backtest engine
    strategies.py     # Strategy library
    metrics.py        # Performance metrics
  
  ai_learning/        # AI/ML
    weight_optimizer.py # LR weight optimization
    deep_learning.py  # LSTM, Transformer
    walk_forward.py   # Walk-forward analysis
    model_registry.py # Versioned model storage
  
  xai/                # Explainable AI
    engine.py         # Narrative generation
  
  api/                # REST API
    app.py            # FastAPI application
  
  cli.py              # CLI entry point
  config.py           # Single source of truth
```

### 2.2 Technology Stack

Lihat `11-knowledge-transfer-aplikasi.md` bagian [15. Quick Reference](#15-quick-reference).

| Komponen | Pilihan |
|----------|---------|
| Backend | Python 3.11+, FastAPI |
| Database | SQLite (WAL mode) |
| Archive | Parquet |
| Frontend | Next.js + TypeScript + TailwindCSS |
| Linter | ruff |
| Type checker | mypy |
| Test | pytest (coverage ≥50%) |
| Migration | Alembic |
| Data | pandas + numpy |
| ML | scikit-learn |
| Package manager | uv |

---

## 3. Modul Data Acquisition

### 3.1 Sumber Data

| Data | Sumber | Frekuensi | Format |
|------|--------|-----------|--------|
| OHLCV harian | Yahoo Finance (`TICKER.JK`) | Harian | JSON |
| Foreign flow | idx.co.id scraper | Harian | JSON |
| Broker flow | idx.co.id scraper | Harian | JSON |
| Fundamental | Yahoo Finance / idx.co.id | Q-Tahunan | JSON/PDF |
| Macro | Bank Indonesia, BPS | Bulanan | JSON |
| Global market | Yahoo Finance (`^GSPC`, `CL=F`, `GC=F`) | Harian | JSON |
| Kalender ekonomi | Investing.com / TradingEconomics | Harian | JSON |
| Berita | RSS, scraping | Real-time | Text |

### 3.2 Implementasi

**Referensi:** `01-fundamental-pasar-modal.md` (bagian 5), `02-pasar-modal-indonesia.md` (bagian 12), `11-knowledge-transfer-aplikasi.md` (bagian 5)

```python
# data/acquisition.py
import yfinance as yf

def fetch_ohlcv(ticker: str, period: str = "max") -> pd.DataFrame:
    """Fetch OHLCV from Yahoo Finance."""
    data = yf.download(ticker, period=period, progress=False)
    # Normalize columns, validate, store
    return data

# data/rate_limiter.py
class AdaptiveRateLimiter:
    """3-state circuit breaker for API calls."""
    # Lihat 11-knowledge-transfer-aplikasi.md bagian 5.1
```

### 3.3 Data Quality

- **Freshness check:** Re-fetch jika data >1 hari (lihat `11-knowledge-transfer.md` bagian 5.3)
- **Validation:** Cek OHLC consistency (high ≥ low, volume ≥ 0)
- **Missing data handling:** Skip tickers dengan quality score 0
- **Schema validation:** Column mapping untuk data dari sumber berbeda

### 3.4 Storage Schema

```sql
-- Core tables
CREATE TABLE instrument_master (
    ticker TEXT PRIMARY KEY,
    name TEXT, sector TEXT, asset_class TEXT,
    is_active INTEGER, listing_date DATE, delisting_date DATE
);

CREATE TABLE ohlcv (
    ticker TEXT, date DATE, open REAL, high REAL,
    low REAL, close REAL, volume INTEGER, adjusted_close REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE foreign_flow (
    ticker TEXT, date DATE,
    foreign_buy REAL, foreign_sell REAL, foreign_net REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE fundamental_data (
    ticker TEXT, date DATE,
    revenue REAL, net_income REAL, total_assets REAL,
    total_equity REAL, total_debt REAL, eps REAL, pe_ratio REAL,
    pb_ratio REAL, roe REAL, roa REAL, div_yield REAL,
    PRIMARY KEY (ticker, date)
);
```

---

## 4. Modul Analisis Teknikal

### 4.1 Indikator yang Diimplementasikan

**Referensi:** `05-analisis-teknikal.md` (komprehensif)

| Kategori | Indikator |
|----------|-----------|
| **Trend** | SMA, EMA, WMA, MACD, ADX, Ichimoku, Parabolic SAR |
| **Momentum** | RSI, Stochastic, ROC, CCI, Williams %R |
| **Volatility** | Bollinger Bands, ATR, Keltner Channels |
| **Volume** | OBV, VWAP, MFI, Accumulation/Distribution |

### 4.2 Implementasi

```python
# analysis/technical.py
class TechnicalEngine:
    VERSION = "1.0"
    
    def compute_all(self, df: pd.DataFrame) -> dict:
        """Compute all technical indicators."""
        # Lihat 05-analisis-teknikal.md bagian 12 untuk kode lengkap
        indicators = {}
        indicators.update(self._trend_indicators(df))
        indicators.update(self._momentum_indicators(df))
        indicators.update(self._volatility_indicators(df))
        indicators.update(self._volume_indicators(df))
        indicators['version'] = self.VERSION
        return indicators
    
    def score(self, indicators: dict) -> float:
        """Convert indicators to 0-100 score."""
        # Scoring logic: trend alignment, momentum, volatility position
        pass
```

### 4.3 Pattern Detection

Implementasi candlestick dan chart pattern detection — lihat `05-analisis-teknikal.md` bagian 7-8.

---

## 5. Modul Analisis Fundamental

### 5.1 Rasio yang Dihitung

**Referensi:** `06-analisis-fundamental.md` (komprehensif)

| Kategori | Rasio |
|----------|-------|
| **Profitabilitas** | Gross Margin, Operating Margin, Net Margin, ROE, ROA, ROIC |
| **Leverage** | D/E, Interest Coverage, Net Debt/EBITDA |
| **Likuiditas** | Current Ratio, Quick Ratio, Cash Ratio |
| **Valuasi** | P/E, PEG, P/B, EV/EBITDA, P/S, Dividend Yield |
| **Efisiensi** | Asset Turnover, Inventory Turnover, DSO |

### 5.2 Valuasi

Implementasi DCF, relative valuation, DDM — lihat `06-analisis-fundamental.md` bagian 8 dan 12.

### 5.3 Kualitas Earnings

```python
# analysis/fundamental.py
class FundamentalEngine:
    VERSION = "1.0"
    
    def earnings_quality(self, net_income, cfo, total_assets):
        """Assess earnings quality."""
        accrual_ratio = (net_income - cfo) / total_assets
        cash_coverage = cfo / net_income if net_income > 0 else 0
        return {
            'accrual_ratio': accrual_ratio,
            'cash_coverage': cash_coverage,
            'quality_score': self._quality_score(accrual_ratio, cash_coverage),
        }
```

### 5.4 Weight Multiplier untuk Saham Tanpa Data Fundamental

```python
def fundamental_weight_multiplier(self, ticker):
    """Return 0.0, 0.5, or 1.0 based on data availability."""
    # Lihat 11-knowledge-transfer-aplikasi.md bagian 3.2
    if not self._has_fundamental_data(ticker):
        return 0.0  # redistribute weight to other factors
    elif self._has_partial_data(ticker):
        return 0.5
    else:
        return 1.0
```

---

## 6. Modul Sentimen & Behavioral

### 6.1 Sentiment Engine

**Referensi:** `09-behavioral-finance.md` (bagian 6, 8), `02-pasar-modal-indonesia.md` (bagian 10)

```python
# sentiment/engine.py
class SentimentEngine:
    """Indonesian NLP sentiment analysis."""
    # Lihat 09-behavioral-finance.md bagian 8.2 untuk implementasi
```

### 6.2 Foreign Flow sebagai Indikator

- **Foreign net buy** = sinyal positif (konvensi Indonesia)
- **Foreign net sell** = sinyal negatif
- Data dari `idx.co.id` scraper

### 6.3 Broker Flow Analysis

- **Broker concentration** = potensi akumulasi/distribusi institusional
- **% Out** = persentase volume broker terhadap total

### 6.4 Behavioral Risk Score

Implementasi `behavioral_risk_score()` — lihat `09-behavioral-finance.md` bagian 8.3.

---

## 7. Modul Decision Engine

### 7.1 Multi-Factor Weighted Scoring

**Referensi:** `11-knowledge-transfer-aplikasi.md` bagian 3, `08-trading-algoritmik.md` bagian 11.2

```python
# decision/engine.py
class DecisionEngine:
    VERSION = "2.0"
    
    DEFAULT_WEIGHTS = {
        "technical": 0.20,
        "fundamental": 0.25,
        "macro": 0.15,
        "global": 0.15,
        "relationship": 0.10,
        "sentiment": 0.15,
    }
    
    def compute_conviction(self, scores):
        """Compute weighted conviction 0-100."""
        # Lihat 08-trading-algoritmik.md bagian 11.2
        # Termasuk weight redistribution untuk faktor unavailable
        pass
    
    def decide(self, scores, has_position=False):
        """Make BUY/HOLD/SELL decision with reason codes."""
        # Lihat 11-knowledge-transfer-aplikasi.md bagian 3.4
        pass
```

### 7.2 Regime-Aware Adjustment

Sesuaikan skor berdasarkan market regime — lihat `11-knowledge-transfer-aplikasi.md` bagian 3.3.

### 7.3 Conviction-Based Exit

Exit bukan hanya dari stop-loss, tapi juga dari conviction drop — lihat `11-knowledge-transfer-aplikasi.md` bagian 3.4.

---

## 8. Modul Risk Management

### 8.1 Position Sizing

**Referensi:** `07-manajemen-risiko.md` (komprehensif)

| Metode | Implementasi |
|--------|-------------|
| Fixed Fractional | Risk 1-2% per trade |
| Volatility-Adjusted (ATR) | Stop = N × ATR |
| Kelly Criterion | Quarter Kelly recommended |
| Equal Risk Contribution | Inverse-volatility weighting |

### 8.2 VaR/CVaR

```python
# risk/var.py
class RiskEngine:
    def var(self, returns, confidence=0.95):
        """Historical VaR."""
        # Lihat 07-manajemen-risiko.md bagian 6
        pass
    
    def cvar(self, returns, confidence=0.95):
        """Conditional VaR (Expected Shortfall)."""
        # Lihat 07-manajemen-risiko.md bagian 7
        pass
```

### 8.3 Drawdown Control

```python
# risk/drawdown.py
class DrawdownController:
    """Automated drawdown monitoring and trading halt."""
    # Lihat 07-manajemen-risiko.md bagian 8.4
    # Halt trading at 20% drawdown
    # Warning at 15% drawdown
    # Resume at 5% drawdown recovery
```

### 8.4 Complete Risk Manager

Lihat `07-manajemen-risiko.md` bagian 12.1 untuk `RiskManager` class lengkap.

---

## 9. Modul Backtesting

### 9.1 Anti-Bias Principles

**Referensi:** `11-knowledge-transfer-aplikasi.md` bagian 6, `08-trading-algoritmik.md` bagian 6-7

1. **Next-bar-open execution** — no look-ahead bias
2. **Block bootstrap** — preserve autocorrelation
3. **IDX rounding** — lot size (100) dan tick size
4. **Transaction costs** — broker fee + PPh + levy
5. **Purged TimeSeriesSplit** — prevent label leakage

### 9.2 Walk-Forward Analysis

```python
# backtest/walk_forward.py
class WalkForward:
    """Walk-forward optimization with purge gap."""
    # Lihat 08-trading-algoritmik.md bagian 7
```

### 9.3 Monte Carlo

```python
# backtest/metrics.py
def monte_carlo_backtest(returns, n_simulations=10000):
    """Block bootstrap Monte Carlo."""
    # Lihat 08-trading-algoritmik.md bagian 7.3
```

---

## 10. Modul Execution

### 10.1 Broker Adapter Pattern

```python
# execution/broker_adapter.py
class BrokerAdapter:
    """Abstract broker adapter."""
    
    def place_order(self, ticker, side, quantity, order_type, price=None):
        """Place order via broker API."""
        pass

class MockBroker(BrokerAdapter):
    """Mock broker for paper trading."""
    pass

class SinarmasBroker(BrokerAdapter):
    """Sinarmas broker adapter (stub)."""
    pass
```

### 10.2 Paper Trading

Simulator yang menjalankan strategi tanpa real money — penting untuk validasi sebelum live trading.

### 10.3 Execution Algorithms

Implementasi VWAP, TWAP, implementation shortfall — lihat `08-trading-algoritmik.md` bagian 5.

---

## 11. Modul Portfolio Management

### 11.1 Portfolio Engine

```python
# portfolio/engine.py
class PortfolioEngine:
    def rebalance(self, target_weights, current_weights):
        """Generate rebalancing orders."""
        pass
    
    def performance(self, start_date, end_date):
        """Compute portfolio performance metrics."""
        # Sharpe, Sortino, Calmar, Max Drawdown
        pass
```

### 11.2 Rebalancing Strategies

| Strategi | Deskripsi |
|----------|-----------|
| **Calendar rebalancing** | Rebalance setiap N bulan |
| **Threshold rebalancing** | Rebalance saat drift > X% |
| **Risk parity** | Equal risk contribution |
| **Factor tilting** | Tilt ke faktor dengan skor tinggi |

---

## 12. Modul AI/ML

### 12.1 Weight Optimization

**Referensi:** `11-knowledge-transfer-aplikasi.md` bagian 7, `08-trading-algoritmik.md` bagian 8

```python
# ai_learning/weight_optimizer.py
def optimize_weights_lr(features, target):
    """Optimize factor weights via Linear Regression."""
    # Lihat 08-trading-algoritmik.md bagian 8.3
    # Clip negative coefficients to 0 (NOT np.abs!)
```

### 12.2 Deep Learning

```python
# ai_learning/deep_learning.py
def lstm_predict(sequences, target_horizon=5):
    """LSTM for return prediction."""
    # Requires tensorflow
    # Minimum 60 samples
    pass
```

### 12.3 Walk-Forward with Purged TSS

Lihat `08-trading-algoritmik.md` bagian 7.1-7.2.

### 12.4 Model Registry

Versioned model storage dengan metadata — lihat `08-trading-algoritmik.md` bagian 8.4.

---

## 13. Modul XAI (Explainable AI)

### 13.1 Narrative Generation

```python
# xai/engine.py
class XAIEngine:
    def generate_narrative(self, decision, scores, reasons):
        """Generate human-readable narrative for decision."""
        # Lihat 09-behavioral-finance.md bagian 9.3
        pass
    
    def top_factors(self, scores, weights):
        """Identify top contributing factors."""
        contributions = {f: scores[f] * weights[f] for f in scores}
        return sorted(contributions.items(), key=lambda x: -x[1])[:3]
```

### 13.2 Tujuan XAI

- **Transparansi:** Investor tahu mengapa sistem merekomendasikan X
- **Audit trail:** Regulator dapat memverifikasi keputusan
- **Trust:** User lebih percaya sistem yang dapat menjelaskan
- **Debugging:** Developer dapat trace mengapa sistem tidak beli saham X

---

## 14. API Design

### 14.1 Endpoint Structure

**Referensi:** `11-knowledge-transfer-aplikasi.md` bagian 8

```
GET  /api/health              — Health check
GET  /api/tickers             — List all tickers
GET  /api/data/ohlcv          — OHLCV data
GET  /api/indicators/{ticker} — Technical indicators
GET  /api/fundamental/{ticker} — Fundamental data
GET  /api/recommend/{ticker}  — Recommendation
GET  /api/explain/{ticker}    — XAI narrative
POST /api/scores/compute      — Compute scores
POST /api/backtest            — Run backtest
GET  /api/monitor             — System health
WS   /ws/live                 — Real-time updates
```

### 14.2 Security

- API key via `X-API-Key` header
- `secrets.compare_digest` (anti timing attack)
- Path traversal protection
- Fail-fast di production
- WebSocket auth via query param

Lihat `11-knowledge-transfer-aplikasi.md` bagian 4.

### 14.3 Best Practices

- `SanitizedJSONResponse` untuk NaN/Inf
- Pagination validation
- Empty body acceptance untuk POST
- Sensitive path matching

---

## 15. Frontend

### 15.1 Technology

- **Framework:** Next.js + TypeScript
- **Styling:** TailwindCSS
- **Components:** shadcn/ui
- **Icons:** Lucide
- **Charts:** Recharts atau TradingView lightweight charts

### 15.2 Halaman Utama

| Halaman | Fungsi |
|---------|--------|
| **Dashboard** | Overview portfolio, market summary |
| **Data Inspection** | Browse OHLCV, indicators, fundamentals |
| **Recommendation** | List rekomendasi dengan conviction |
| **Backtest** | Run dan visualize backtest |
| **Portfolio** | Portfolio management dan rebalancing |
| **Settings** | Konfigurasi weights, risk params |

### 15.3 API Integration

```typescript
// frontend/app/lib/api.ts
async function safeApiFetch(endpoint: string, options?: RequestInit) {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const base = process.env.NEXT_PUBLIC_API_BASE;
  
  const res = await fetch(`${base}${endpoint}`, {
    ...options,
    headers: {
      'X-API-Key': apiKey,
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
```

---

## 16. Compliance & Regulasi

### 16.1 Lisensi yang Diperlukan

**Referensi:** `10-regulasi-pasar-modal.md` bagian 7.1

| Aktivitas Aplikasi | Lisensi (Indonesia) |
|--------------------|---------------------|
| Menampilkan data pasar | Tidak perlu |
| Rekomendasi saham | Penasihat Investasi |
| Trading otomatis | Perusahaan Efek |
| Mengelola dana | Manajer Investasi |
| Robo-advisor | PI + MI |

### 16.2 Disclosure

1. Risk disclosure di setiap rekomendasi
2. Conflict of interest disclosure
3. Methodology disclosure (XAI)
4. Performance disclaimer
5. "Bukan ajakan untuk membeli/menjual"

### 16.3 Data Privacy

- UU PDP (Indonesia Personal Data Protection)
- GDPR (jika user EU)
- Consent management
- Data minimization
- Security measures

### 16.4 Audit Trail

Setiap keputusan sistem harus tercatat dengan:
- Timestamp
- Ticker
- Action (BUY/HOLD/SELL)
- Conviction score
- Engine version
- Factor scores
- Reason codes
- Data as-of date

---

## 17. Testing & Deployment

### 17.1 Testing Strategy

**Referensi:** `11-knowledge-transfer-aplikasi.md` bagian 10

| Tipe | Tools | Coverage |
|------|-------|----------|
| **Unit tests** | pytest | ≥50% |
| **Integration tests** | pytest + test DB | Critical paths |
| **E2E tests** | Playwright | User flows |
| **API tests** | httpx + pytest | All endpoints |
| **Backtest validation** | Walk-forward | Strategy robustness |

### 17.2 Test Determinism

```python
# conftest.py
@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Reset env vars for deterministic tests."""
    monkeypatch.setattr("market_app.config._API_KEY", "")
```

### 17.3 CI/CD

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install uv && uv sync
      - run: ruff check src/
      - run: mypy src/
      - run: pytest --cov=src --cov-fail-under=50
```

### 17.4 Deployment

| Environment | Setup |
|-------------|-------|
| **Development** | Local SQLite, `.env` file |
| **Staging** | Docker, test database |
| **Production** | Docker, production DB, API_KEY required |

---

## 18. Roadmap Pengembangan

### Phase 1: Foundation (MVP)

- [ ] Data acquisition (Yahoo Finance OHLCV)
- [ ] SQLite storage dengan Alembic migration
- [ ] Technical indicators (SMA, EMA, RSI, MACD, Bollinger)
- [ ] Basic API (FastAPI)
- [ ] CLI entry point
- [ ] Basic frontend (data inspection)

### Phase 2: Analysis

- [ ] Fundamental analysis (rasio, DCF)
- [ ] Macro analysis (BI rate, inflation)
- [ ] Global market analysis
- [ ] Sentiment engine (Indonesian NLP)
- [ ] Foreign flow & broker flow (idx.co.id scraper)
- [ ] Decision engine (multi-factor weighted scoring)

### Phase 3: Risk & Backtest

- [ ] Position sizing (fixed fractional, ATR-based)
- [ ] VaR/CVaR computation
- [ ] Drawdown monitoring
- [ ] Backtest engine (anti-bias)
- [ ] Walk-forward analysis
- [ ] Monte Carlo simulation

### Phase 4: AI & Advanced

- [ ] Weight optimization (LR)
- [ ] Deep learning (LSTM)
- [ ] Model registry
- [ ] XAI narrative generation
- [ ] Portfolio optimization (efficient frontier)
- [ ] Rebalancing strategies

### Phase 5: Execution & Live

- [ ] Paper trading simulator
- [ ] Broker adapter (real broker API)
- [ ] Automated execution dengan risk controls
- [ ] Real-time monitoring
- [ ] Alert system (Telegram/email)
- [ ] Production deployment

### Phase 6: Enhancement

- [ ] ESG scoring
- [ ] Syariah screening
- [ ] Options/derivatives support
- [ ] Multi-market support (regional)
- [ ] Mobile app
- [ ] Social/copy trading features

---

## 19. Referensi Silang

Setiap modul dalam panduan ini merujuk ke dokumen knowledge base spesifik:

| Modul Aplikasi | Dokumen Referensi | Bagian |
|----------------|-------------------|--------|
| Data Acquisition | `01-fundamental-pasar-modal.md` | 5, 10 |
| Data Acquisition | `02-pasar-modal-indonesia.md` | 12 |
| Data Acquisition | `11-knowledge-transfer-aplikasi.md` | 5 |
| Technical Analysis | `05-analisis-teknikal.md` | Seluruh |
| Fundamental Analysis | `06-analisis-fundamental.md` | Seluruh |
| Sentiment | `09-behavioral-finance.md` | 6, 8 |
| Sentiment | `02-pasar-modal-indonesia.md` | 10 |
| Decision Engine | `11-knowledge-transfer-aplikasi.md` | 3 |
| Decision Engine | `08-trading-algoritmik.md` | 11 |
| Risk Management | `07-manajemen-risiko.md` | Seluruh |
| Backtesting | `11-knowledge-transfer-aplikasi.md` | 6 |
| Backtesting | `08-trading-algoritmik.md` | 6, 7 |
| AI/ML | `08-trading-algoritmik.md` | 8 |
| AI/ML | `11-knowledge-transfer-aplikasi.md` | 7 |
| XAI | `09-behavioral-finance.md` | 9 |
| API Design | `11-knowledge-transfer-aplikasi.md` | 8 |
| Compliance | `10-regulasi-pasar-modal.md` | Seluruh |
| IDX Conventions | `02-pasar-modal-indonesia.md` | 8 |
| IDX Conventions | `11-knowledge-transfer-aplikasi.md` | 13 |
| Global Context | `03-pasar-modal-global.md` | Seluruh |
| Instruments | `04-instrumen-pasar-modal.md` | Seluruh |

---

## Kesimpulan

Knowledge base di `pustaka/` menyediakan fondasi lengkap untuk membangun aplikasi pasar modal:

1. **Pengetahuan domain** (dokumen 01-10) — pasar modal, instrumen, analisis, risiko, behavioral, regulasi
2. **Pengetahuan implementasi** (dokumen 11) — pola arsitektur, best practices, bug lessons dari proyek nyata
3. **Panduan sintesis** (dokumen 12 — dokumen ini) — blueprint modul dan roadmap

Dengan mengikuti pola yang terbukti dari proyek `trading-system` dan pengetahuan pasar modal yang komprehensif, developer dapat membangun aplikasi yang:

- **Robust** — guard everything, fail-fast, test determinism
- **Scalable** — modular monolith yang dapat evolve ke microservice
- **Compliant** — mengikuti regulasi OJK dan global
- **Transparent** — XAI, reason codes, audit trail
- **Data-driven** — multi-factor scoring, backtested, walk-forward validated
- **Risk-aware** — position sizing, VaR, drawdown control

---

## Referensi

1. `src/trading_system/` — Complete trading system source code
2. `pustaka/18-modul-engine-data-wajib.md` — Module & engine specification
3. `pustaka/19-flow-logic-testing-kpi.md` — Flow, logic, testing, KPI
4. `pustaka/20-syarat-robot-auto-trading.md` — 12 pilar robot trading
5. `pustaka/11-knowledge-transfer-aplikasi.md` — Knowledge transfer dari proyek nyata
6. `pustaka/17-aplikasi-retail-pribadi.md` — Retail app features
7. FastAPI: https://fastapi.tiangolo.com/
8. Next.js: https://nextjs.org/
9. SQLite: https://www.sqlite.org/

---

> **Mulai dari:** `01-fundamental-pasar-modal.md` untuk pemula, atau `11-knowledge-transfer-aplikasi.md` untuk developer yang sudah familiar dengan pasar modal.
