# Ablation Test Deep Analysis: Best Practices vs Current Implementation

> Hasil riset mendalam tentang ablation study best practices untuk ML/trading systems,
> analisis cara kerja setiap engine, data requirements, dan rekomendasi perbaikan
> framework ablation aplikasi pasar modal.

## 1. Ablation Study Best Practices (Riset Internet)

### 1.1 Definisi & Tujuan

Ablation study dalam ML/quant trading adalah metode evaluasi komponen dengan
**mengisolasi kontribusi setiap engine** terhadap performa keseluruhan sistem.
Berbeda dengan feature importance (yang mengukur kontribusi fitur dalam satu model),
ablation mengukur kontribusi **seluruh pipeline engine** terhadap outcome.

### 1.2 Prinsip Utama (Literatur)

1. **Leave-One-Out (LOO)**: Hapus satu engine, ukur perubahan performa.
   - Baseline = semua engine aktif
   - Ablated = baseline tanpa engine X
   - Delta = performa(ablated) - performa(baseline)
   - Engine yang kontribusinya negatif → kandidat REMOVE

2. **Add-One-In (AOI)**: Tambah satu engine ke baseline kosong.
   - Baseline = tidak ada engine (buy-and-hold atau random)
   - Isolated = hanya engine X
   - Delta = performa(isolated) - performa(baseline)
   - Engine yang tidak memberikan alpha → kandidat REMOVE

3. **Statistical Significance**: Paired t-test pada daily returns, bukan
   hanya perbandingan Sharpe ratio. Minimum 30 observations untuk validitas
   statistik. **Multiple testing correction wajib** saat menguji banyak engine
   (Bonferroni: α/n, atau Benjamini-Hochberg FDR).

4. **Walk-Forward Validation**: Prevent look-ahead bias dengan rolling windows
   dan purge gaps (López de Prado). Setiap fold harus independen.

5. **Deflated Sharpe Ratio (DSR)**: Account for selection bias saat multiple
   strategies diuji. DSR = Sharpe - correction_factor(N_trials, skew, kurtosis).

6. **Transaction Costs**: Wajib include commission, slippage, dan market impact.
   Signal yang profitable gross tapi unprofitable net = tidak ada alpha.

7. **Data Quality First**: Garbage in = garbage out. Pre-flight data validation
   untuk mencegah false "REMOVE" verdict dari data gap, bukan dari engine yang
   buruk.

8. **Signal Diagnostics vs Strategy Outcomes**: Pisahkan metric roles:
   - Signal quality: hit rate, calibration, information coefficient
   - Strategy profitability: Sharpe, alpha, max drawdown
   - Engine bisa punya signal quality tinggi tapi profitability rendah
     (karena costs, timing, atau market regime)

### 1.3 Yang TIDAK Boleh Dilakukan

- **Cherry-picking**: Hanya melaporkan periode di mana engine perform well
- **Look-ahead bias**: Menggunakan data future untuk signal generation
- **Ignoring regime**: Engine bisa perform well di bull market tapi buruk di bear
- **No transaction costs**: Backtest tanpa biaya = ilusi profit
- **No multiple testing correction**: 15 engine × α=0.05 → ~0.75 false positive
  expected secara random

---

## 2. Analisis Setiap Engine: Cara Kerja, Data, Durasi

### 2.1 SignalEnhancer Engines (8)

#### 2.1.1 Volume (VWAP + OFI + OBV + Foreign Flow)

**Cara kerja:**
- VWAP: Rolling volume-weighted average price, window=20 bars
- Deviation: (close - VWAP) / VWAP → positive = price above VWAP (bullish)
- OFI Proxy: Order Flow Imbalance dari buy/sell pressure
- OBV Divergence: Bullish/bearish divergence detection, window=20
- Foreign Flow: Z-score of foreign net buy, window=5
- Aggregate: `clip(OFI + VWAP_dev*5 + OBV + FF, -1, 1)`

**Data yang dibutuhkan:**
- `ohlcv`: open, high, low, close, volume (wajib)
- `foreign_flow`: buy_value, sell_value (opsional, untuk FF signal)

**Durasi minimum:**
- VWAP rolling: 20 trading days (window=20)
- OBV divergence: 20 trading days
- Foreign flow Z-score: 5 trading days + buffer
- **Minimum total: 20 trading days** (current: 20 ✓)
- **Recommended: 60 trading days** (untuk stable OBV divergence + multiple regimes)

**Implementasi ablation saat ini:**
- ❌ Hanya menggunakan VWAP deviation, tidak include OFI, OBV, foreign flow
- ❌ Tidak menggunakan `SignalEnhancer._compute_volume_signal()` yang sebenarnya
- ⚠️ Signal terlalu simplistik vs implementasi production

#### 2.1.2 Event (Policy Event Scorer)

**Cara kerja:**
- Load `policy_events` + `external_events` dari DB
- Map kategori Indonesia → EventType (BI_RATE_CUT, FED_RATE_HIKE, dll)
- Exponential decay: half-life=10 days
- Market-wide events: weight=0.3 per ticker
- Ticker-specific events: weight=1.0
- Composite score [-100, +100] → normalized [-1, +1]

**Data yang dibutuhkan:**
- `policy_events`: tanggal, kategori, judul, instansi, dampak
- `external_events`: tanggal, kategori, judul, lokasi, dampak_market

**Durasi minimum:**
- Decay half-life=10 days → event masih relevan sampai ~30 days (3 half-lives)
- Untuk multiple event types: butuh 90+ days
- **Minimum: 30 trading days** (current: 30 ✓ untuk basic)
- **Recommended: 180 trading days** (untuk capture multiple BI rate decisions,
  geopolitical events, earnings cycles)

**Implementasi ablation saat ini:**
- ❌ Tidak menggunakan `PolicyEventScorer.load()` dari DB
- ❌ Signal generation manual, tidak menggunakan `compute_event_signal()`
- ⚠️ Tidak memetakan kategori Indonesia → EventType

#### 2.1.3 Meta (Meta-Labeling)

**Cara kerja:**
- Triple barrier method: profit target, stop loss, vertical barrier (holding period)
- Primary model → directional prediction
- Secondary model (LightGBM) → predict P(primary correct)
- Output: bet size [0,1] + trade/no-trade decision
- Features: ATR ratio, volatility, RSI, etc.

**Data yang dibutuhkan:**
- `ohlcv` untuk label generation (triple barrier)
- Trained LightGBM model

**Durasi minimum:**
- López de Prado: minimum 500-1000 labeled events for training
- With walk-forward CV: need 1000+ days
- **Minimum: 500 trading days** (current: 50 ❌ WAY TOO LOW)
- **Status: SKIP** (butuh trained model, tidak bisa test tanpa training)

#### 2.1.4 Smart Money (Retail Absorption / Bandarmology)

**Cara kerja:**
- Retail brokers (YP, CC, XL, PD) net selling >60% volume
- Price holds at/above VWAP → institutions absorbing supply
- Score [-1, +1], lookback=5 days
- Accumulation streak counter

**Data yang dibutuhkan:**
- `broker_flow`: ticker, date, broker, buy_volume, sell_volume, net_volume
- `ohlcv`: high, low, close, volume

**Durasi minimum:**
- Lookback=5 days + buffer
- **Minimum: 20 trading days** (current: 20 ✓)
- **Issue: broker_flow hanya ticker '__MARKET__', tidak per-ticker** → SKIP

#### 2.1.5 Cross-Market (Domino Effect)

**Cara kerja:**
- Pre-IDX market returns: ^N225 (weight 0.35), ^HSI (0.35), 000001.SS (0.15), CPO=F (0.15)
- Anti-lookahead: hanya pakai market yang sudah close sebelum IDX
- Signal: weighted sum of pre-market returns

**Data yang dibutuhkan:**
- `ohlcv` untuk global tickers: ^N225, ^HSI, 000001.SS, CPO=F

**Durasi minimum:**
- Spillover analysis: VAR models, 60-252 day windows
- Diebold-Yilmaz spillover index: 200-day rolling window
- **Minimum: 60 trading days** (current: 20 ❌ TOO LOW)
- **Recommended: 252 trading days** (untuk stable spillover estimates)

#### 2.1.6 Sector Rotation

**Cara kerja:**
- `compute_sector_momentum()`: cumulative return over lookback=20 days
- `detect_rotation()`: short_window=5 vs long_window=20 rank comparison
- `compute_relative_strength()`: sector vs market, window=60
- Composite: 0.4*momentum + 0.3*rotation + 0.3*RS

**Data yang dibutuhkan:**
- `ohlcv` untuk sector constituents
- `sector_master`: kode, nama (sector mapping)
- Market benchmark (IHSG) untuk RS

**Durasi minimum:**
- Momentum lookback: 20 days
- Rotation: short=5, long=20 days → butuh 20+ days history
- RS window: 60 days
- **Minimum: 60 trading days** (current: 60 ✓)
- **Recommended: 252 trading days** (untuk full RS normalization)

**Implementasi ablation saat ini:**
- ⚠️ Menggunakan static momentum + RS, tidak menggunakan rotation detection
- ⚠️ Signal konstan (tidak time-varying) → tidak ada trading dynamics

#### 2.1.7 Pairs Trading (Statistical Arbitrage)

**Cara kerja:**
- Engle-Granger cointegration: OLS residuals + custom ADF test
- p-value < 0.05 → cointegrated
- Z-score: rolling window=20, look-ahead safe (shift by 1)
- Entry: |Z| > 2.0, Exit: |Z| < 0.5, Stop: |Z| > 4.0
- Regime gate: rolling corr > 0.95 → skip new entries
- Half-life filter: 5-60 trading days

**Data yang dibutuhkan:**
- `ohlcv` untuk 2+ cointegrated tickers
- Known IDX pairs: AKRA-BMRI, BTPN-PWON, BDMN-MIKA, BTPN-CPIN, ADMF-ISAT

**Durasi minimum:**
- Cointegration testing: 252+ days (1 year) minimum
- Z-score rolling: 20 days
- Regime filter: 20 days rolling correlation
- **Minimum: 252 trading days** (current: 60 ❌ WAY TOO LOW)
- **Recommended: 504 trading days** (2 years for stable cointegration)

**Implementasi ablation saat ini:**
- ⚠️ Menggunakan `PairsTradingEngine.compute_spread()` + `compute_zscore()` ✓
- ❌ Tidak melakukan cointegration test sebelum compute spread
- ❌ Tidak menggunakan `generate_signals()` dengan position state machine
- ❌ Tidak menggunakan regime gate

#### 2.1.8 Astronacci (Time Cycle)

**Cara kerja:**
- Moon phases, planetary retrogrades, ingresses, Fibonacci time windows
- Produces time_signal [-1, +1] and volatility_signal
- TIMING indicator — WHEN, not WHAT direction

**Data yang dibutuhkan:**
- Astronomical calculations (no DB data needed)

**Durasi minimum:**
- **Minimum: 1 day** (current: 1 ✓)
- **Note**: Should be evaluated on timing accuracy, not P&L alone

### 2.2 MarketContext Engines (7)

#### 2.2.1 Fundamental

**Cara kerja:**
- PE ratio: low = undervalued (bullish)
- ROE: high = quality (bullish)
- DER: low = safe (bullish)
- Dividend yield: high = income (bullish)
- Composite fundamental score

**Data yang dibutuhkan:**
- `fundamental_data`: pe, roe, der, dividend_yield, date, ticker
- `instrument_master`: untuk sector/industry context

**Durasi minimum:**
- Fundamental data is quarterly/annual → need time-series, not snapshot
- **Minimum: 365 calendar days** (current: 90 ❌ TOO LOW untuk quarterly data)
- **Recommended: 1095 calendar days** (3 years for fundamental trend)
- **Current issue: fundamental_data is snapshot, not time-series** → WARN

#### 2.2.2 Macro

**Cara kerja:**
- `macro_data`: BI rate, CPI, GDP
- BI rate change: cut → bullish, hike → bearish
- Correlation between macro indicators and stock returns

**Data yang dibutuhkan:**
- `macro_data`: series_name, value, date
- `ohlcv` for stock returns

**Durasi minimum:**
- Macro indicators are monthly/quarterly
- Need 90+ days for meaningful correlation
- **Minimum: 90 trading days** (current: 30 ❌ TOO LOW)
- **Recommended: 252 trading days** (1 year for full macro cycle)

#### 2.2.3 ML (LightGBM)

**Cara kerja:**
- Trained LightGBM with technical + fundamental features
- Predicts next-day direction probability [0, 1]
- Requires trained model

**Data yang dibutuhkan:**
- `ohlcv`, `technical_indicators`
- Trained LightGBM model

**Durasi minimum:**
- Train/test split with walk-forward: 500+ days
- **Minimum: 500 trading days** (current: 200 ❌ TOO LOW)
- **Status: SKIP** (butuh trained model)

#### 2.2.4 News Sentiment

**Cara kerja:**
- `NewsSentimentAnalyzer`: keyword lexicon or IndoBERT
- Time-decay weighting (half-life=7 days)
- Score [-1, +1] from headline analysis
- Daily aggregation aligned to trading days

**Data yang dibutuhkan:**
- `news`: published_at (RFC822), headline, source

**Durasi minimum:**
- Need 30+ days for meaningful sentiment patterns
- Need 100+ news items for statistical significance
- **Minimum: 30 trading days** (current: 7 ❌ TOO LOW)
- **Recommended: 90 trading days** (for diverse news patterns)

#### 2.2.5 Commodity

**Cara kerja:**
- Correlation between commodity prices (CPO, gold, coal, nickel) and IDX stocks
- Positive commodity move → bullish for producers, bearish for consumers
- Uses OHLCV for commodity tickers

**Data yang dibutuhkan:**
- `ohlcv` for commodity tickers: CPO=F, GC=F, ^BRENT, COAL

**Durasi minimum:**
- Correlation analysis: 60-252 days rolling
- CPO-ASEAN equity studies use 5-15 years of daily data
- **Minimum: 60 trading days** (current: 20 ❌ TOO LOW)
- **Recommended: 252 trading days** (for stable correlation estimates)

#### 2.2.6 Global Sentiment (VIX + Fear & Greed)

**Cara kerja:**
- VIX: rolling 20-day MA ratio → elevated VIX = risk-off
- Fear & Greed: 0-100 scale, 7 indicators (CNN version)
  - Market momentum: S&P 500 vs 125-day average
  - VIX component: 50-day SMA
  - Contrarian: extreme fear = buy, extreme greed = sell

**Data yang dibutuhkan:**
- `ohlcv` for ^VIX
- `fear_greed`: tanggal, nilai, label

**Durasi minimum:**
- VIX 20-day MA: 20 days
- Fear & Greed momentum: 125-day SMA
- **Minimum: 125 trading days** (current: 20 ❌ WAY TOO LOW)
- **Recommended: 252 trading days** (for full F&G calculation)

#### 2.2.7 Governance (ESG + Corporate Governance)

**Cara kerja:**
- ESG scores: annual frequency, 0-100 scale
- Corporate governance: board structure, GCG score
- High ESG → lower long-term risk
- Low ESG → higher risk premium
- Slow-moving signal (quarterly/annual changes)

**Data yang dibutuhkan:**
- `esg_scores`: score, year, ticker, rating_agency
- `corporate_governance`: gcg_score, board_commissioners, year, ticker

**Durasi minimum:**
- ESG is annual → need 2+ years for trend analysis
- MSCI study: ESG financial effects unfold over multiyear periods
- Governance = short-term event risk; E/S = long-term erosion risk
- **Minimum: 730 calendar days (2 years)** (current: 365 ❌ TOO LOW)
- **Recommended: 1095 calendar days (3 years)** (for ESG trend)
- **Note**: ESG is NOT a source of "free alpha" — it's a risk management tool

---

## 3. Perbandingan: Current vs Research-Based min_data_days

| Engine | Current | Research | Gap | Status |
|--------|---------|----------|-----|--------|
| volume | 20 | 20 | 0 | ✓ OK |
| event | 30 | 90 | +60 | ⚠️ Update |
| meta | 50 | 500 | +450 | ❌ Major fix |
| smart_money | 20 | 20 | 0 | ✓ OK (but SKIP: no per-ticker data) |
| cross_market | 20 | 60 | +40 | ⚠️ Update |
| sector | 60 | 60 | 0 | ✓ OK |
| pairs | 60 | 252 | +192 | ❌ Major fix |
| astronacci | 1 | 1 | 0 | ✓ OK |
| fundamental | 90 | 365 | +275 | ❌ Major fix |
| macro | 30 | 90 | +60 | ⚠️ Update |
| ml | 200 | 500 | +300 | ❌ Major fix (but SKIP anyway) |
| news | 7 | 30 | +23 | ⚠️ Update |
| commodity | 20 | 60 | +40 | ⚠️ Update |
| global_sentiment | 20 | 125 | +105 | ❌ Major fix |
| governance | 365 | 730 | +365 | ❌ Major fix |

---

## 4. Rekomendasi Perbaikan

### 4.1 Update ENGINE_MIN_DAYS (Priority: HIGH)

Update nilai minimum berdasarkan riset:

```python
ENGINE_MIN_DAYS = {
    "volume": 20,           # VWAP 20-day window (OK)
    "event": 90,            # 3x half-life decay, multiple event types
    "meta": 500,            # Lopez de Prado: 500+ labeled events
    "smart_money": 20,      # 5-day lookback + buffer (OK)
    "cross_market": 60,     # Spillover analysis stability
    "sector": 60,           # RS 60-day window (OK)
    "pairs": 252,           # 1 year minimum for cointegration
    "astronacci": 1,        # Astronomical calc (OK)
    "fundamental": 365,     # Annual/quarterly fundamental data
    "macro": 90,            # Macro correlation stability
    "ml": 500,              # Walk-forward train/test split
    "news": 30,             # Meaningful sentiment patterns
    "commodity": 60,        # Stable correlation estimates
    "global_sentiment": 125, # F&G 125-day SMA component
    "governance": 730,      # 2 years for ESG trend
}
```

### 4.2 Tambah `data_duration_notes` ke EngineEntry (Priority: HIGH)

Field baru untuk mendokumentasikan ALASAN min_data_days:

```python
@dataclass
class EngineEntry:
    # ... existing fields ...
    min_data_days: int = 30
    data_duration_notes: str = ""  # Research-based justification
```

### 4.3 Tambah Multiple Testing Correction ke Scorecard (Priority: HIGH)

Saat testing 15 engine dengan α=0.05, expected false positive = 0.75.
Wajib apply Bonferroni correction: α_adjusted = 0.05 / n_engines.

```python
def score_engine(result, n_engines_tested=1, alpha=0.05):
    # Bonferroni correction
    adjusted_alpha = alpha / max(n_engines_tested, 1)
    significant = result.p_value < adjusted_alpha
    # ... use adjusted_alpha for verdict ...
```

### 4.4 Improve Signal Generation Fidelity (Priority: MEDIUM)

Engine yang signal generation-nya paling berbeda dari production:

1. **volume**: Gunakan `SignalEnhancer._compute_volume_signal()` yang sebenarnya
   (OFI + VWAP + OBV + foreign flow), bukan hanya VWAP deviation

2. **event**: Gunakan `PolicyEventScorer.load()` + `compute_event_signal()`
   untuk proper event scoring dengan decay

3. **pairs**: Tambahkan cointegration test sebelum compute spread.
   Skip pair jika tidak cointegrated. Gunakan `generate_signals()` dengan
   position state machine + regime gate.

4. **sector**: Gunakan `SectorRotationEngine.recommend_sectors()` dengan
   proper rotation detection (short vs long rank), bukan static momentum

5. **fundamental**: Gunakan composite PE + ROE + DER + dividend yield,
   bukan hanya PE median comparison

6. **global_sentiment**: Include Fear & Greed index dari DB, bukan hanya VIX

### 4.5 Tambah Data Quality Checks (Priority: MEDIUM)

Pre-flight check saat ini hanya memeriksa:
- Table exists ✓
- Row count > 0 ✓
- Date range overlap ✓
- Column names match ✓

Perlu tambah:
- **Non-zero values**: Column tidak all-null atau all-zero
- **Data frequency**: OHLCV harus daily, macro harus monthly/quarterly
- **Ticker coverage**: Proportion of test tickers with data
- **Minimum non-null ratio**: >80% non-null untuk required columns

### 4.6 Tambah Walk-Forward Support (Priority: LOW)

Current: single period test (start to end).
Recommended: rolling windows dengan purge gap.

```python
def run_walk_forward_ablation(
    tickers, engines, start, end,
    train_window=252, test_window=63, purge_gap=5,
):
    # Split [start, end] into overlapping windows
    # For each window: train on train_window, test on test_window
    # Purge gap between train and test to prevent leakage
    # Aggregate results across all windows
```

### 4.7 Tambah Deflated Sharpe Ratio (Priority: LOW)

López de Prado's DSR untuk account selection bias:

```python
def deflated_sharpe_ratio(sharpe, n_trials, n_obs, skew, kurtosis):
    # DSR = Prob(SR > SR_observed | n_trials, n_obs, skew, kurt)
    # Account for multiple testing in strategy selection
```

---

## 5. Summary

### Yang SUDAH BAIK:
- Pre-flight data checker dengan table/column/date validation
- Isolation guarantee (read-only, no DB writes)
- Paired t-test untuk statistical significance
- Transaction cost modeling (0.3% round-trip)
- No-look-ahead bias dalam engine implementations
- Engine registry dengan metadata lengkap

### Yang PERLU DIPERBAIKI:
1. **ENGINE_MIN_DAYS**: 9 dari 15 engine punya nilai terlalu rendah
2. **Multiple testing correction**: Tidak ada Bonferroni/FDR correction
3. **Signal generation fidelity**: 6 engine punya simplifikasi berlebihan
4. **Data quality checks**: Hanya cek existence, tidak cek quality
5. **Walk-forward validation**: Tidak ada rolling window support
6. **Deflated Sharpe Ratio**: Tidak ada selection bias correction

### Prioritas Implementasi:
1. Update `ENGINE_MIN_DAYS` + `data_duration_notes` (HIGH, immediate)
2. Bonferroni correction di scorecard (HIGH, immediate)
3. Improve signal generation untuk top 4 engine (MEDIUM, next)
4. Data quality checks (MEDIUM, next)
5. Walk-forward + DSR (LOW, future)
