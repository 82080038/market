# New Data Arrival Processing Pipeline

> **Dokumen 84** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Setiap kali data baru masuk (OHLCV, fundamental, macro, foreign flow, news), aplikasi harus: (1) pemeriksaan data lengkap, (2) testing & validasi, (3) screening, (4) penemuan pola, (5) penandaan/labeling ke database. Dokumen ini menyatukan seluruh chain dari data arrival hingga database tagging berdasarkan praktek nyata di codebase.
>
> **Konteks:** Doc 22 bahas data quality framework. Doc 39 bahas screening & labeling. Doc 46 bahas pattern detection. Doc 53 bahas data governance. Tapi tidak ada dokumen yang menyatukan semuanya menjadi **satu pipeline continuous** yang berjalan setiap kali data baru tiba.

---

## Daftar Isi

1. [Pipeline Overview](#1-pipeline-overview)
2. [Stage 1: Data Arrival & Ingestion](#2-stage-1-data-arrival--ingestion)
3. [Stage 2: Pemeriksaan Data Lengkap](#3-stage-2-pemeriksaan-data-lengkap)
4. [Stage 3: Testing & Validasi](#4-stage-3-testing--validasi)
5. [Stage 4: Screening](#5-stage-4-screening)
6. [Stage 5: Penemuan Pola](#6-stage-5-penemuan-pola)
7. [Stage 6: Penandaan & Labeling ke Database](#7-stage-6-penandaan--labeling-ke-database)
8. [Stage 7: Post-Processing Trigger](#8-stage-7-post-processing-trigger)
9. [Implementasi: Daily Runner](#9-implementasi-daily-runner)
10. [Implementasi: Real-Time Pipeline](#10-implementasi-real-time-pipeline)
11. [Hubungan dengan Dokumen Lain](#11-hubungan-dengan-dokumen-lain)

---

## 1. Pipeline Overview

### 1.1 Complete Chain

```
DATA ARRIVAL
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1: INGESTION                                             │
│  ├─ Fetch dari source (Yahoo Finance / Parquet archive / IDX)  │
│  ├─ Rate limiting & retry                                       │
│  ├─ Raw data disimpan ke Parquet (raw zone)                    │
│  └─ Source health update                                        │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2: PEMERIKSAAN DATA LENGKAP                              │
│  ├─ Completeness check (null/missing)                          │
│  ├─ Plausibility check (OHLC consistency, price > 0)          │
│  ├─ Volume anomaly (spike > 10x median)                       │
│  ├─ Gap detection (missing dates > 5 days)                    │
│  ├─ Cross-source check (adjusted_close vs close ratio)        │
│  ├─ Reconciliation (volume consistency, typical price range)  │
│  ├─ TIP quality checks (duplicates, stale, abnormal returns)  │
│  └─ Data quality score (0-100, tier: gold/silver/bronze/reject)│
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼  (only if quality >= 50, not "pause")
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3: TESTING & VALIDASI                                    │
│  ├─ Schema validation (columns, types)                         │
│  ├─ Normalization (timestamp format, column naming)            │
│  ├─ Corporate action detection (split/dividend from ratio)     │
│  ├─ Adjusted close computation                                │
│  └─ Save to SQLite (clean data) + Parquet archive sync         │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 4: SCREENING                                             │
│  ├─ Technical screener (price > SMA50, RSI, ADX, volume)      │
│  ├─ Momentum screener (price > SMA50&200, MACD+, ADX > 25)   │
│  ├─ Value screener (PER < 15, ROE > 10%, DER < 1)            │
│  ├─ Factor screener (composite rank across all factors)       │
│  ├─ Liquidity filter (ADV, bid-ask spread)                    │
│  └─ Equity-only filter (asset_class = 'equity')               │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 5: PENEMUAN POLA                                         │
│  ├─ Technical indicators (RSI, MACD, MA, ADX, Bollinger, ATR) │
│  ├─ Chart pattern detection (head & shoulders, triangles, etc)│
│  ├─ Candlestick pattern detection (engulfing, doji, hammer)   │
│  ├─ Pattern reliability scoring (historical win-rate)         │
│  ├─ Stock personality classification                          │
│  │   (volatility regime, trend bias, liquidity, best pattern) │
│  └─ Save pattern_analysis to DB                                │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 6: PENANDAAN & LABELING KE DATABASE                      │
│  ├─ 6-factor score labeling (technical, fundamental, macro,   │
│  │   global, relationship, sentiment → scores table)          │
│  ├─ AI labeling (forward_return, triple_barrier labels)       │
│  ├─ Stock personality tagging (personality_label to DB)       │
│  ├─ Pattern tagging (pattern_type, confidence, direction)     │
│  ├─ Data quality tag (data_quality_score per row)            │
│  ├─ Watermark update (last_data_date, row_count)             │
│  └─ Audit trail (every action logged)                         │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 7: POST-PROCESSING TRIGGER                               │
│  ├─ Decision engine: compute conviction → action              │
│  ├─ Recommendation generation (BUY/SELL/HOLD/AVOID)           │
│  ├─ XAI narrative explanation                                 │
│  ├─ Risk metrics update (VaR, drawdown, volatility)          │
│  ├─ Performance snapshot                                      │
│  ├─ Alert check (price/score/conviction alerts)              │
│  └─ Automated execution (if enabled)                          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Praktik Nyata di Codebase

| Stage | File | Fungsi | Status |
|-------|------|--------|--------|
| Ingestion | `data/acquisition.py` | `YahooFinanceAdapter.fetch()` | ✅ Production |
| Ingestion | `data/archive.py` | `ArchiveAdapter.load_ohlcv()` | ✅ Production |
| Pemeriksaan | `data/validation.py` | `DataQualityValidator.validate()` | ✅ Production |
| Testing | `data/acquisition.py` | `normalize_ohlcv()` | ✅ Production |
| Testing | `corporate/actions.py` | `CorporateActionEngine.fetch()` | ✅ Production |
| Storage | `data/storage.py` | `save_ohlcv()`, `save_score()` | ✅ Production |
| Screening | `analysis/screener.py` | `screen_universe()` | ✅ Production |
| Screening | `analysis/factor_screener.py` | `FactorScreenerService.screen()` | ✅ Production |
| Pattern | `analysis/technical.py` | `TechnicalAnalysisEngine.analyze()` | ✅ Production |
| Pattern | `analysis/pattern_reliability.py` | `PatternReliabilityEngine` | ✅ Production |
| Labeling | `ai_learning/labeling.py` | Triple-barrier, forward return | ✅ Production |
| Scoring | `analysis/pipeline.py` | `AnalysisPipeline.compute()` | ✅ Production |
| Personality | `data/storage.py` | `save_stock_personality()` | ✅ Production |
| Pattern tag | `data/storage.py` | `save_pattern_analysis()` | ✅ Production |
| Post-proc | `decision/engine.py` | `DecisionEngine.recommend()` | ✅ Production |
| Post-proc | `xai/engine.py` | `ExplainableAIEngine.explain()` | ✅ Production |
| Orchestrator | `scripts/daily_runner.py` | `daily_job()` | ✅ Production |

---

## 2. Stage 1: Data Arrival & Ingestion

### 2.1 Data Sources

| Source | Data Type | Trigger | Code |
|--------|-----------|---------|------|
| **Yahoo Finance** | OHLCV, splits, dividends | Daily runner / CLI fetch | `YahooFinanceAdapter.fetch()` |
| **Parquet archive** | OHLCV (historical) | Fallback before Yahoo | `ArchiveAdapter.load_ohlcv()` |
| **IDX scraper** | Foreign flow, broker flow | CLI fetch-idx-* | `data/idx_scraper.py` |
| **yfinance info** | Fundamental data | During compute pipeline | `FundamentalAnalysisEngine.fetch()` |

### 2.2 Ingestion Process (Existing Code)

```python
# data/acquisition.py:126-214
class YahooFinanceAdapter:
    def fetch(self, ticker: str, period: str = "2y") -> dict:
        # 1. Rate-limited fetch
        result = self.rate_limiter.execute(ticker, _do_fetch)

        # 2. On error: update source health, audit log
        if result.error:
            self.storage.update_source_health("yahoo_finance", "down", success=False)
            self.storage.audit("data.raw.ohlcv.error", {...})
            return {"status": "error"}

        # 3. Rename columns to standard schema
        df.rename(columns={"Date": "timestamp", "Open": "open", ...})

        # 4. Add metadata columns
        df["ticker"] = ticker
        df["asset_class"] = "equity"
        df["exchange"] = "INDO" if ticker.endswith(".JK") else "GLOBAL"
        df["source"] = "yahoo_finance"
        df["ingested_at"] = datetime.now(UTC).isoformat()

        # 5. Save raw to Parquet (raw zone + archive)
        df.to_parquet(raw_file, index=False)
        df.to_parquet(archive_file, index=False)

        # 6. Auto-fetch corporate actions
        ca_engine.fetch(ticker)
        storage.update_adjusted_close(ticker)

        # 7. Update source health + audit
        self.storage.update_source_health("yahoo_finance", "ok", success=True)
        self.storage.audit("data.raw.ohlcv", {...})

        return {"status": "ok", "records": df}
```

### 2.3 Incremental Fetch

```python
# analysis/pipeline.py:34-103 — ensure_ohlcv()
def ensure_ohlcv(self, ticker: str, period: str = "2y") -> bool:
    df = self.storage.load_ohlcv(ticker)
    if not df.empty:
        last_ts = str(df.index[-1])[:10]
        today = datetime.now().strftime("%Y-%m-%d")
        if last_ts >= today:
            return True  # Already current

        # Try Parquet archive first (faster, no rate limit)
        arch_df = self.archive.load_ohlcv(ticker, start=last_ts)
        if not arch_df.empty:
            # ... validate and save incremental
            return True

        # Fallback: Yahoo Finance incremental
        result = adapter.fetch_incremental(ticker, last_timestamp=last_ts)
        # ... validate and save
        return True

    # SQLite empty — try Parquet archive full load
    # ... then Yahoo Finance full fetch
    return False
```

---

## 3. Stage 2: Pemeriksaan Data Lengkap

### 3.1 Eight Quality Checks (Existing Code: `data/validation.py`)

```python
class DataQualityValidator:
    def validate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, DataQualityReport]:
        # Check 1: COMPLETENESS — null/missing percentage
        missing_pct = df.isna().mean().mean() * 100
        if missing_pct > 0:
            score -= missing_pct * 2
            anomalies.append({"check": "completeness", ...})

        # Check 2: PLAUSIBILITY — OHLC consistency
        # - Price > 0 for all OHLC columns
        # - low <= high
        # - close within [low, high]
        for _, row in df.iterrows():
            if row.get(col) <= 0:
                anomalies.append({"check": "plausibility", "severity": "high"})
            if row.get("low") > row.get("high"):
                anomalies.append({"check": "plausibility", "severity": "high"})
            if row.get("close") < row.get("low") or row.get("close") > row.get("high"):
                anomalies.append({"check": "plausibility", "severity": "high"})

        # Check 3: VOLUME ANOMALY — spike > 10x median
        median_vol = df["volume"].median()
        spikes = df[df["volume"] > 10 * median_vol]
        if not spikes.empty:
            anomalies.append({"check": "plausibility", "severity": "low"})

        # Check 4: GAP DETECTION — missing dates > 5 days
        diffs = df_sorted["timestamp_dt"].diff().dt.days.dropna()
        weekend_gaps = (diffs > 5).sum()
        if weekend_gaps:
            anomalies.append({"check": "completeness", "severity": "low"})

        # Check 5: CROSS-SOURCE — adjusted_close vs close ratio
        ratio = adj / cls
        # Detect unexpected ratio jumps (possible split/dividend or data error)
        ratio_diffs = ratio.diff().abs()
        large_jumps = (ratio_diffs > 0.5).sum()
        # Check ratio outside [0.01, 1.0]

        # Check 6: RECONCILIATION — volume consistency
        negative_vol = (vol < 0).sum()  # High severity
        zero_vol = (vol == 0).sum()     # Low severity if > 10%

        # Check 7: OHLCV INTERNAL — typical price range
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        out_of_range = ((typical_price < df["low"]) | (typical_price > df["high"])).sum()

        # Check 8: TIP QUALITY — duplicates, stale, abnormal returns
        qr = check_quality(df, symbol=str(ticker))
        # - duplicates: duplicate timestamps
        # - stale_data: last bar > 7 days ago
        # - abnormal_returns: > 25% daily move

        # Final score & tier
        score = max(0.0, min(100.0, score))
        if score >= 90: action = "accept"; tier = "gold"
        elif score >= 70: action = "flag"; tier = "silver"
        elif score >= 50: action = "delayed_review"; tier = "bronze"
        else: action = "pause"; tier = "reject"

        df["data_quality_score"] = score  # Tag quality score to each row
        return df, report
```

### 3.2 Quality Tier Actions

| Score | Tier | Action | What Happens |
|-------|------|--------|-------------|
| ≥ 90 | **Gold** | `accept` | Save immediately, use for all analysis |
| 70-89 | **Silver** | `flag` | Save but flag for review, use with caution |
| 50-69 | **Bronze** | `delayed_review` | Queue for manual review, don't use for decisions |
| < 50 | **Reject** | `pause` | Do NOT save, reject data, alert admin |

### 3.3 Anomaly Logging

Setiap anomaly dicatat dan di-audit:

```python
self.storage.audit("data.quality.validation", {
    "record_count": n,
    "data_quality_score": score,
    "anomaly_count": len(anomalies),
    "action": action,
})
```

---

## 4. Stage 3: Testing & Validasi

### 4.1 Normalization (Existing Code: `data/acquisition.py`)

```python
def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names, timestamp format, data types."""
    # Rename Yahoo Finance columns to standard schema
    # Parse timestamps with mixed format support
    # Ensure numeric types for OHLCV columns
    return df
```

### 4.2 Corporate Action Detection

```python
# corporate/actions.py — auto-triggered during fetch
class CorporateActionEngine:
    def fetch(self, ticker: str):
        """Fetch splits & dividends from yfinance, store to DB."""
        # Detect stock splits and dividends
        # Compute backward adjustment factors
        # Store corporate_actions + dividends to DB

    def compute_adjustment_factor(self, ticker: str) -> pd.DataFrame:
        """Compute cumulative backward adjustment factors."""
        # For splits: adj_factor *= 1.0 / split_ratio (pre-ex-date)
        # For dividends: adj_factor *= (close - dividend) / close (pre-ex-date)
```

### 4.3 Storage with Quality Tag

```python
# data/storage.py:493-545 — save_ohlcv()
def save_ohlcv(self, df: pd.DataFrame) -> int:
    """Save OHLCV to SQLite with data_quality_score per row."""
    # INSERT OR REPLACE into ohlcv table
    # Includes data_quality_score column (from Stage 2)

    # Update watermark (last_data_date, first_data_date, row_count)
    self.update_watermark(ticker, ...)

    # Auto-sync to Parquet archive
    self._sync_ohlcv_to_parquet(df)

    return n
```

### 4.4 Data Watermark

Setiap save update watermark untuk tracking:

```python
# Tracks: ticker, last_data_date, first_data_date, row_count, source
# Used by: incremental fetch (know where to resume), freshness check, monitoring
```

---

## 5. Stage 4: Screening

### 5.1 Screening Templates (Existing Code: `analysis/screener.py`)

```python
TEMPLATES = {
    "technical": technical_template,   # Price > SMA50, RSI 30-70, ADX > 20
    "momentum": momentum_template,     # Price > SMA50&200, MACD+, ADX > 25
    "value": value_template,           # PER < 15, ROE > 10%, DER < 1
}

def screen_universe(features_df, template="technical", as_of=None):
    """Run screening template on universe of tickers."""
    result = TEMPLATES[template](features_df)
    result = result.sort_values("score", ascending=False)
    result["rank"] = result.index + 1
    return result
```

### 5.2 Factor Screener (Existing Code: `analysis/factor_screener.py`)

```python
class FactorScreenerService:
    def screen(self, top_n=20, min_composite=0.0, factor_filter=None):
        """Run factor screen and return top-ranked instruments."""
        result = self.engine.compute()
        # Composite rank across all factors
        # Filter by min_composite, min_factor_rank
        # Return top N with factor breakdown + reason codes
```

### 5.3 Equity-Only Filter

```python
# Only process equity stocks (928 active)
tickers = storage.list_active_equity_tickers()
# Filters: is_active = 1 AND asset_class = 'equity'
```

### 5.4 Screening Output

```
Screening Result:
  Universe: 928 equity tickers
  Template: technical
  Pass: 47 tickers
  Top 10:
    1. BBCA.JK  score=85  (RSI=58, ADX=32, above SMA50)
    2. TLKM.JK  score=78  (RSI=52, ADX=28, above SMA50)
    3. ASII.JK  score=75  (RSI=45, ADX=25, above SMA50)
    ...
```

---

## 6. Stage 5: Penemuan Pola

### 6.1 Technical Indicators (Existing Code: `analysis/technical.py`)

```python
class TechnicalAnalysisEngine:
    def analyze(self) -> dict:
        """Compute 30+ technical indicators."""
        # RSI(14), MACD(12,26,9), SMA(20,50,200), EMA(12,26)
        # ADX(14), Bollinger Bands(20,2), ATR(14)
        # Volume profile, OBV, Stochastic
        # Trend classification (uptrend/downtrend/sideways)
        # Pattern detection (chart + candlestick)
        return {
            "score": ...,
            "breakdown": {...},
            "indicators": {...},
            "patterns_detected": [...],
        }
```

### 6.2 Pattern Detection

| Pattern Category | Patterns | Source |
|-----------------|----------|--------|
| **Chart patterns** | Head & shoulders, double top/bottom, triangles, wedges | `analysis/technical.py` |
| **Candlestick patterns** | Engulfing, doji, hammer, shooting star, harami | `analysis/technical.py` |
| **Reliability scoring** | Historical win-rate per pattern per stock | `analysis/pattern_reliability.py` |

### 6.3 Pattern Reliability Engine (Existing Code)

```python
class PatternReliabilityEngine:
    def score_pattern(self, kode: str, pattern_name: str) -> dict:
        """Get reliability score for a specific pattern on a stock."""
        return {
            "found": True,
            "pattern": pattern_name,
            "win_rate": 0.68,
            "total_occurrences": 25,
            "success_count": 17,
            "avg_return_5d": 2.3,
            "avg_return_10d": 4.1,
            "avg_return_20d": 7.8,
            "reliability_rating": "good",
        }

    def enrich_technical_signals(self, ticker, detected_patterns):
        """Enrich detected patterns with historical reliability data."""
        # For each detected pattern, look up historical win-rate
        # Filter: only recommend patterns with win_rate >= 60%
```

### 6.4 Stock Personality Classification

```python
# DB table: stock_personality (944 rows)
# Fields: volatility_regime, trend_bias, trend_strength, beta_vs_ihsg,
#         correlation_ihsg, liquidity_score, personality_label,
#         best_pattern, best_pattern_winrate

def classify_stock_personality(ticker: str, df: pd.DataFrame) -> dict:
    """Classify stock personality from historical data."""
    return {
        "kode": ticker,
        "avg_daily_volatility": ...,
        "volatility_regime": "high_volatility",  # high/medium/low
        "trend_bias": "uptrend",                 # uptrend/downtrend/sideways
        "trend_strength": 0.72,                  # 0-1
        "beta_vs_ihsg": 1.15,
        "correlation_ihsg": 0.68,
        "liquidity_score": 1.0,                  # high/moderate/low
        "personality_label": "momentum_stock",   # classification
        "best_pattern": "bullish_engulfing",
        "best_pattern_winrate": 0.68,
    }
```

---

## 7. Stage 6: Penandaan & Labeling ke Database

### 7.1 Six-Factor Score Labeling

```python
# analysis/pipeline.py:105-165 — compute()
def compute(self, ticker: str, period: str = "2y") -> dict:
    # Run all 6 engines
    tech = self.technical.analyze()        # → score 0-100
    fund = self.fundamental.analyze()      # → score 0-100
    macro = self.macro.analyze(period)     # → score 0-100
    glob = self.global_market.analyze()    # → score 0-100
    rel = self.relationship.compute(ticker) # → score 0-100
    sent = self.sentiment.compute(ticker)  # → score 0-100

    # Save each score to DB with breakdown
    for engine, res in results.items():
        self.storage.save_score(
            ticker, engine, res["score"],
            res.get("breakdown", {}),
            as_of=as_of,
        )
    # → scores table: 6 rows per ticker per compute cycle
```

### 7.2 AI Labeling (Existing Code: `ai_learning/labeling.py`)

```python
# Three labeling methods for ML training:
LABEL_TYPES = {
    "forward_return": "N-day forward return → regression target",
    "triple_barrier": "+1 (TP hit), -1 (SL hit), 0 (timeout) → classification target",
    "alpha_adjusted": "Label disesuaikan regime → risk-aware labeling",
}

# Labels stored for ML training (walk-forward, purged TSS)
```

### 7.3 Pattern Tagging to DB

```python
# data/storage.py:1659-1675 — save_pattern_analysis()
def save_pattern_analysis(self, record: dict):
    """Save detected pattern to pattern_analysis table."""
    # Fields: ticker, date, pattern_type, confidence, direction, details, source
    # Example:
    #   ticker=BBCA.JK, date=2026-08-05, pattern_type=bullish_engulfing,
    #   confidence=0.85, direction=bullish, details={...}, source=technical
```

### 7.4 Stock Personality Tagging

```python
# data/storage.py:2008-2037 — save_stock_personality()
def save_stock_personality(self, record: dict):
    """Save stock personality classification to DB."""
    # Fields: kode, profile_date, avg_daily_volatility, volatility_regime,
    #         trend_bias, trend_strength, beta_vs_ihsg, correlation_ihsg,
    #         avg_volume, liquidity_score, personality_label
```

### 7.5 Data Quality Tagging

```python
# Every row in ohlcv table has data_quality_score column
# Set during validation stage:
df["data_quality_score"] = score  # 0-100

# Allows downstream filtering:
# - Only use gold tier (>= 90) for decision engine
# - Flag silver tier (70-89) for review
# - Exclude bronze/reject from analysis
```

### 7.6 Watermark & Audit Tagging

```python
# Watermark: tracks data freshness per ticker
storage.update_watermark(
    ticker=ticker,
    last_data_date=...,
    first_data_date=...,
    row_count=...,
    source=...,
)

# Audit: every action logged
storage.audit("data.raw.ohlcv", {...})
storage.audit("data.quality.validation", {...})
storage.audit("decision.recommendation.created", {...})
```

### 7.7 Complete Database Tagging Summary

| Tag/Label | DB Table | Column(s) | When |
|-----------|----------|-----------|------|
| **Data quality score** | `ohlcv` | `data_quality_score` | After validation |
| **Quality tier** | audit_log | `action` (accept/flag/pause) | After validation |
| **6-factor scores** | `scores` | `score`, `breakdown` | After pipeline compute |
| **Technical indicators** | `technical_indicators` | 30+ indicator columns | After technical analysis |
| **Pattern detected** | `pattern_analysis` | `pattern_type`, `confidence`, `direction` | After pattern detection |
| **Stock personality** | `stock_personality` | `personality_label`, `volatility_regime`, `trend_bias` | After personality classification |
| **Corporate actions** | `corporate_actions` | `action_type`, `value`, `ex_date` | After corporate action fetch |
| **Dividends** | `dividends` | `amount`, `ex_date`, `record_date` | After dividend fetch |
| **Fundamental data** | `fundamental_data` | `pe_ratio`, `pb_ratio`, `roe`, `der` | After fundamental fetch |
| **AI labels** | (training data) | `forward_return`, `triple_barrier` | During ML training cycle |
| **Watermark** | `data_watermark` | `last_data_date`, `row_count` | After every save |
| **Audit trail** | `audit_log` | `event_type`, `payload` | Every action |

---

## 8. Stage 7: Post-Processing Trigger

### 8.1 Decision Engine (Triggered After Scoring)

```python
# decision/engine.py:143-213 — recommend()
def recommend(self, ticker: str) -> dict:
    # Load latest scores from DB (tagged in Stage 6)
    scores = self.load_latest_scores(ticker)

    # Apply regime filter
    adjusted = self.apply_regime_filter(scores, macro_regime)

    # AI Learning: dynamic weights
    weights = self.ai_learning.get_factor_weights(ticker, macro_regime)

    # Compute conviction
    conviction = self.compute_conviction(adjusted, weights)

    # Risk analysis
    risk = self.risk.analyze(ticker, capital=capital)

    # Decide action
    action = self.decide_action(conviction, risk["risk_flags"], has_position)

    # Build recommendation
    recommendation = {
        "action": action,
        "conviction_score": conviction,
        "position_size": risk["position_size"],
        "entry_price_range": [...],
        "stop_loss": risk["stop_loss"],
        "take_profit": risk["take_profit"],
        "contributing_scores": adjusted,
        ...
    }

    # XAI explanation
    recommendation["explanation"] = self.xai.explain(ticker, recommendation)

    # Audit
    self.storage.audit("decision.recommendation.created", recommendation)

    return recommendation
```

### 8.2 Alert Check

After new data + scoring, check if any alerts should trigger:
- Price alert (price crossed threshold)
- Score alert (score crossed threshold)
- Conviction alert (conviction >= 70 → BUY signal)
- Pattern alert (new pattern detected)
- Quality alert (data quality dropped)

---

## 9. Implementasi: Daily Runner

### 9.1 Full Pipeline (Existing Code: `scripts/daily_runner.py`)

```python
def daily_job():
    """Full daily pipeline: fetch → scores → recommendations → execution → risk → performance."""

    # Step 1: Fetch & Validate OHLCV
    fetch_results = fetch_and_validate(tickers)
    # → For each ticker: fetch → normalize → validate → save

    # Step 2: Compute Analysis Scores
    for ticker in tickers:
        if fetch_results[ticker]["status"] == "ok":
            compute_scores_for_ticker(ticker)
            # → AnalysisPipeline.compute()
            # → Runs all 6 engines, saves scores to DB

    # Step 3: Generate Recommendations
    recommendations = generate_recommendations(rec_tickers)
    # → DecisionEngine.recommend() per ticker

    # Step 4: Automated Execution (trading days only)
    run_automated_execution(tickers)
    # → AutomatedExecutionEngine.run_once()

    # Step 5: Daily Risk Metrics
    save_daily_risk_metrics()
    # → VaR, CVaR, drawdown

    # Step 6: Performance Snapshot
    save_performance_snapshot()
    # → Equity curve, NAV

    # Step 7: Render Supplementary Data
    # → corporate_actions, fundamental, technical_indicators,
    #   macro_data, fear_greed, pattern_analysis, stock_personality,
    #   market_calendar, foreign_flow, broker_flow, news, etc.
```

### 9.2 Per-Ticker Pipeline Detail

```
For each ticker (e.g., BBCA.JK):

1. FETCH
   ├─ Check watermark (last_data_date)
   ├─ If stale: try Parquet archive for incremental
   ├─ Fallback: Yahoo Finance incremental fetch
   └─ If empty: full fetch (Parquet → Yahoo)
        ↓
2. NORMALIZE
   ├─ Rename columns to standard schema
   ├─ Parse timestamps (mixed format)
   ├─ Add metadata (ticker, asset_class, exchange, source, ingested_at)
   └─ Set data_quality_score = None (pre-validation)
        ↓
3. VALIDATE (8 checks)
   ├─ Completeness → plausibility → volume → gaps
   ├─ Cross-source → reconciliation → OHLCV internal → TIP quality
   ├─ Compute quality score (0-100)
   ├─ Assign tier (gold/silver/bronze/reject)
   └─ If pause (< 50): STOP, don't save
        ↓
4. SAVE TO DB
   ├─ INSERT OR REPLACE into ohlcv table
   ├─ Update data_watermark
   ├─ Sync to Parquet archive
   └─ Audit log
        ↓
5. CORPORATE ACTIONS
   ├─ Fetch splits & dividends from yfinance
   ├─ Save to corporate_actions + dividends tables
   ├─ Compute adjustment factors
   └─ Update adjusted_close in ohlcv
        ↓
6. COMPUTE SCORES (6 engines)
   ├─ Technical: 30+ indicators, pattern detection → score
   ├─ Fundamental: PER/PBV/ROE/DER → score
   ├─ Macro: BI rate, inflation, GDP, regime → score
   ├─ Global: S&P500, STI, HSCEI correlation → score
   ├─ Relationship: cross-asset, lead-lag → score
   ├─ Sentiment: 6 sources (foreign/broker/news/social/trends/fear-greed) → score
   └─ Save all 6 scores to scores table with breakdown
        ↓
7. PATTERN DETECTION
   ├─ Detect chart patterns (head&shoulders, triangles, etc.)
   ├─ Detect candlestick patterns (engulfing, doji, hammer, etc.)
   ├─ Score pattern reliability (historical win-rate)
   ├─ Save to pattern_analysis table
   └─ Update stock_personality if needed
        ↓
8. RECOMMENDATION
   ├─ Load latest 6 scores
   ├─ Apply regime filter
   ├─ AI Learning: optimize weights
   ├─ Compute conviction
   ├─ Risk engine: position size, SL, TP, VaR
   ├─ Decide action (BUY/SELL/HOLD/AVOID/WATCHLIST)
   ├─ XAI: generate narrative explanation
   └─ Save recommendation + audit
        ↓
9. ALERTS & EXECUTION
   ├─ Check alerts (price, score, conviction, pattern)
   ├─ If auto_trade_enabled: execute
   └─ Monitor existing positions (SL/TP/trailing)
```

---

## 10. Implementasi: Real-Time Pipeline

### 10.1 Future: Event-Driven Pipeline

```
Market Data Feed (real-time)
    │
    ▼
┌──────────────┐
│  Event Bus   │  (Kafka / Redis Stream)
└──┬───────────┘
   │
   ├─→ Validation Worker (Stage 2-3)
   │     └─ Quality check → save to DB
   │
   ├─→ Screening Worker (Stage 4)
   │     └─ Real-time screen → alert if new ticker passes
   │
   ├─→ Pattern Worker (Stage 5)
   │     └─ Real-time pattern detection → save to DB
   │
   ├─→ Decision Worker (Stage 7)
   │     └─ Real-time recommendation → alert/execute
   │
   └─→ Risk Worker
        └─ Real-time VaR update → alert if threshold breach
```

### 10.2 Current vs Future

| Aspect | Current (Daily) | Future (Real-Time) |
|--------|-----------------|-------------------|
| **Trigger** | Cron (17:00 WIB) | Event-driven (every tick) |
| **Latency** | End-of-day | < 1 second |
| **Pipeline** | Sequential (fetch → compute → rec) | Parallel (event bus) |
| **Screening** | All tickers at once | On new data arrival |
| **Pattern** | Daily batch | Real-time detection |
| **Alerts** | After daily run | Immediate |
| **Execution** | After daily run | Real-time if enabled |

---

## 11. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **22** (Data Engineering) | Data quality framework, ingestion, validation rules |
| **39** (Screening AI/ML) | Screener, labeling engine, pattern memory |
| **46** (Prediksi & Pola) | Pattern detection, portfolio pipeline |
| **47** (Operational Contract) | Daily tasks (T-010 fetch, T-020 watchlist, T-030 decision) |
| **53** (Data Governance) | Data lineage, watermark, audit trail |
| **58** (Feature Store) | Feature computation pipeline |
| **66** (Market Data Distribution) | Real-time data feed architecture |
| **75** (Corporate Actions) | Auto-triggered during ingestion |
| **82** (Vendor Management) | Data source health, fallback |
| **83** (Advisory System) | Post-processing: recommendation from scores |

---

## 12. Checklist Implementasi

### Stage 1: Ingestion
- [x] Yahoo Finance adapter with rate limiting
- [x] Parquet archive fallback
- [x] Incremental fetch (watermark-based)
- [x] Source health tracking
- [x] Audit logging
- [ ] Real-time feed adapter (future)

### Stage 2: Pemeriksaan Data
- [x] Completeness check
- [x] Plausibility check (OHLC consistency)
- [x] Volume anomaly detection
- [x] Gap detection
- [x] Cross-source check (adjusted vs close)
- [x] Reconciliation (volume, typical price)
- [x] TIP quality checks (duplicates, stale, abnormal)
- [x] Quality score (0-100) with tier system
- [ ] Cross-source validation (multiple data providers)

### Stage 3: Testing & Validasi
- [x] Normalization (column names, timestamps)
- [x] Corporate action detection (auto-triggered)
- [x] Adjusted close computation
- [x] Save to SQLite with quality tag
- [x] Watermark update
- [x] Parquet archive sync
- [ ] Schema enforcement (strict type checking)

### Stage 4: Screening
- [x] Technical screener template
- [x] Momentum screener template
- [x] Value screener template
- [x] Factor screener (composite rank)
- [x] Equity-only filter
- [ ] Liquidity filter integration with screener
- [ ] Custom screener (user-defined rules)

### Stage 5: Penemuan Pola
- [x] Technical indicators (30+)
- [x] Chart pattern detection
- [x] Candlestick pattern detection
- [x] Pattern reliability scoring (historical win-rate)
- [x] Stock personality classification
- [ ] Real-time pattern detection
- [ ] Pattern confidence calibration

### Stage 6: Penandaan & Labeling
- [x] 6-factor score labeling → scores table
- [x] Pattern tagging → pattern_analysis table
- [x] Stock personality tagging → stock_personality table
- [x] Data quality tag → ohlcv.data_quality_score
- [x] Watermark → data_watermark table
- [x] Audit trail → audit_log table
- [x] AI labeling (triple_barrier, forward_return)
- [ ] Regime label tagging
- [ ] Anomaly label tagging

### Stage 7: Post-Processing
- [x] Decision engine (conviction → action)
- [x] Recommendation generation
- [x] XAI narrative explanation
- [x] Risk metrics update
- [x] Performance snapshot
- [x] Automated execution (if enabled)
- [ ] Real-time alert check
- [ ] Alert routing (push/Telegram/email)

### Orchestrator
- [x] Daily runner (batch mode)
- [x] Market calendar awareness (trading vs non-trading day)
- [x] Supplementary data rendering
- [ ] Real-time event-driven pipeline
- [ ] Per-data-arrival trigger (not just daily)

---

## Referensi

1. `src/trading_system/data/acquisition.py` — Data ingestion (Yahoo, Parquet, IDX)
2. `src/trading_system/data/validation.py` — 8 quality checks, tier system
3. `src/trading_system/data/storage.py` — SQLite storage & watermark
4. `src/trading_system/analysis/pipeline.py` — 6-factor scoring pipeline
5. `src/trading_system/analysis/pattern_reliability.py` — Pattern detection & reliability
6. `scripts/daily_runner.py` — Daily pipeline orchestrator
7. `pustaka/22-data-engineering-pipeline.md` — Data engineering pipeline
8. `pustaka/53-data-governance-lineage.md` — Data governance & quality
9. `pustaka/86-gigantic-ai-autonomous-trading-system.md` — Autonomous pipeline vision

---

> **Catatan:** Setiap data baru yang masuk bukan sekadar disimpan — data harus melalui 7 tahap: ingestion → pemeriksaan → testing → screening → penemuan pola → penandaan → post-processing. Setiap tahap menambahkan metadata, label, atau tag ke database. Inilah yang membedakan "database yang penuh data" dengan "database yang penuh pengetahuan." Data tanpa pemeriksaan adalah noise. Data tanpa labeling adalah harta karun yang tidak tergali. Data tanpa pattern discovery adalah angka tanpa makna. Untuk visi pipeline ini berjalan sepenuhnya otonom sebagai bagian dari "Gigantic AI", lihat `86-gigantic-ai-autonomous-trading-system.md`.
