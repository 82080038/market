# Advisory System: Screening ke Saran Eksekusi

> **Dokumen 83** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Bagaimana aplikasi — atas hasil screening, pemeriksaan, dan testing data — sanggup memberikan saran lengkap kepada user: jenis pasar/strategi saham apa, berapa jumlahnya, kapan masuk, kapan keluar, persentase untung, dan alasan empiris. Serta kemampuan eksekusi otomatis setelah semua tahapan perhitungan selesai dan keputusan profit telah dipastikan.
>
> **Konteks:** Doc 19 bahas decision engine flow. Doc 74 bahas screening→execution pipeline (financial perspective). Doc 39 bahas screening AI/ML. Doc 16 bahas strategi trading. Tapi tidak ada dokumen yang menyatukan semuanya dari perspektif **advisory system**: bagaimana aplikasi bertindak sebagai advisor trading yang memberikan saran konkret dengan alasan empiris, dan sanggup mengeksekusi otomatis.

---

## Daftar Isi

1. [Advisory System Overview](#1-advisory-system-overview)
2. [Screening: Apa yang Diperiksa](#2-screening-apa-yang-diperiksa)
3. [Saran Jenis Pasar & Strategi](#3-saran-jenis-pasar--strategi)
4. [Saran Jumlah (Position Sizing)](#4-saran-jumlah-position-sizing)
5. [Saran Kapan Masuk (Entry)](#5-saran-kapan-masuk-entry)
6. [Saran Kapan Keluar (Exit)](#6-saran-kapan-keluar-exit)
7. [Saran Persentase Untung](#7-saran-persentase-untung)
8. [Alasan Empiris & Nyata](#8-alasan-empiris--nyata)
9. [Eksekusi Otomatis](#9-eksekusi-otomatis)
10. [Implementasi Kode](#10-implementasi-kode)
11. [Hubungan dengan Dokumen Lain](#11-hubungan-dengan-dokumen-lain)

---

## 1. Advisory System Overview

### 1.1 Kapabilitas Aplikasi

Aplikasi sanggup memberikan saran trading yang lengkap dan berbasis data:

| Saran | Kapabilitas | Sumber Data |
|-------|-------------|-------------|
| **Jenis pasar/strategi** | Swing, position, dividend, momentum, value | Stock personality + market regime |
| **Saham apa yang dibeli** | Ticker spesifik dari 928 equity | Screener + factor screener |
| **Berapa jumlahnya** | Position size dalam lot & rupiah | Risk engine + capital calculator |
| **Kapan masuk** | Entry price range | Last price ± 1% + technical confirmation |
| **Kapan keluar** | Stop loss, take profit, trailing, conviction exit | Risk engine (ATR-based) |
| **Persentase untung** | Expected return % dari TP vs entry | Risk/reward ratio |
| **Berapa lama tahan** | Expected hold period | Strategy type + conviction |
| **Alasan empiris** | 6-factor scores, backtest, VaR, regime | Decision engine + XAI |
| **Eksekusi otomatis** | Auto-execute jika semua check pass | Automated execution engine |

### 1.2 Advisory Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ADVISORY PIPELINE                                 │
│                                                                      │
│  [1] DATA TESTING & VALIDATION                                       │
│      ├─ OHLCV quality check (completeness, outliers, gaps)          │
│      ├─ Data freshness check (last update, stale detection)         │
│      ├─ Stock personality classification                             │
│      └─ Market regime detection (macro/global)                      │
│           ↓                                                          │
│  [2] SCREENING                                                       │
│      ├─ Technical screener (928 → N tickers)                        │
│      ├─ Factor screener (composite rank, factor breakdown)          │
│      ├─ Liquidity filter (ADV, bid-ask spread)                      │
│      └─ Equity-only filter (asset_class = 'equity')                 │
│           ↓                                                          │
│  [3] DECISION ENGINE (per ticker yang pass screening)               │
│      ├─ Compute 6-factor score (technical, fundamental, macro,      │
│      │   global, relationship, sentiment)                           │
│      ├─ Apply regime filter (adjust scores by macro regime)         │
│      ├─ AI Learning: dynamic weight optimization                    │
│      ├─ Compute conviction (weighted average)                       │
│      ├─ Risk engine: position size, SL, TP, VaR, volatility        │
│      ├─ Decide action: BUY / WATCHLIST / HOLD / AVOID / SELL       │
│      └─ Build recommendation object                                  │
│           ↓                                                          │
│  [4] XAI EXPLANATION (alasan empiris)                                │
│      ├─ Narrative explanation (Indonesian)                          │
│      ├─ Top contributing factors                                     │
│      ├─ Confidence interval                                          │
│      └─ Counter-scenario analysis                                    │
│           ↓                                                          │
│  [5] STRATEGY CLASSIFICATION                                         │
│      ├─ Stock personality → strategy type                            │
│      ├─ Market regime → approach (aggressive/defensive)             │
│      ├─ Conviction → conviction tier                                 │
│      └─ Risk flags → guardrails                                      │
│           ↓                                                          │
│  [6] ADVISORY OUTPUT (saran lengkap ke user)                         │
│      ├─ "Beli BBCA.JK, strategi swing trading"                      │
│      ├─ "Jumlah: 40 lot (4,000 lembar), Rp 32,800,000"             │
│      ├─ "Entry: Rp 8,100 – Rp 8,260"                                │
│      ├─ "Stop loss: Rp 7,850 (exit jika turun ke sini)"             │
│      ├─ "Take profit: Rp 8,800 (target untung +7.3%)"              │
│      ├─ "Tahan: 1-3 bulan"                                          │
│      ├─ "Alasan: Technical 72, Fundamental 85, Macro 78, ..."      │
│      └─ "Risiko: VaR 1-day 95% = Rp 1,200,000"                     │
│           ↓                                                          │
│  [7] EKSEKUSI (manual atau otomatis)                                 │
│      ├─ Manual: user konfirmasi → eksekusi                          │
│      └─ Auto: AUTO_TRADE_ENABLED=true → eksekusi langsung           │
│           ↓                                                          │
│  [8] POST-EXECUTION MONITORING                                       │
│      ├─ SL/TP monitoring (real-time price check)                    │
│      ├─ Trailing stop (ATR-based)                                   │
│      ├─ Conviction-based exit (SELL if conviction < 40)             │
│      └─ Profit/loss tracking                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Screening: Apa yang Diperiksa

### 2.1 Data Testing & Validation

Sebelum screening, setiap ticker melalui pemeriksaan data:

```python
def validate_ticker_data(ticker: str, storage: DataStorage) -> dict:
    """Validate data quality before screening."""
    df = storage.load_ohlcv(ticker)

    checks = {
        "has_data": not df.empty,
        "min_history_days": len(df) >= 252,  # Min 1 year
        "last_update_fresh": _check_freshness(df),
        "no_significant_gaps": _check_gaps(df),
        "price_positive": (df["close"] > 0).all() if not df.empty else False,
        "volume_not_zero": (df["volume"] > 0).any() if not df.empty else False,
    }

    all_pass = all(checks.values())
    return {"ticker": ticker, "valid": all_pass, "checks": checks}
```

### 2.2 Screening Templates

Aplikasi punya 3 template screening (existing code: `analysis/screener.py`):

| Template | Kriteria | Cocok untuk |
|----------|---------|-------------|
| **Technical** | Price > SMA50, RSI 30-70, ADX > 20, Volume > avg | Trend following |
| **Momentum** | Price > SMA50 & SMA200, RSI 50-75, ADX > 25, MACD+ | Momentum trading |
| **Value** | PER < 15, ROE > 10%, DER < 1.0 | Value investing |

### 2.3 Factor Screener

Aplikasi juga punya factor-based screening (existing code: `analysis/factor_screener.py`):

```python
# FactorScreenerService.screen()
# Compute composite rank across all factors
# Filter by min_composite, min_factor_rank
# Return top N with factor breakdown
```

### 2.4 Equity-Only Filter

```python
# Only equity stocks (asset_class = 'equity', is_active = 1)
# Excludes forex, index, commodity, ETF
# 928 active equity tickers
tickers = storage.list_active_equity_tickers()
```

### 2.5 Stock Personality Classification

Database punya tabel `stock_personality` (944 rows) yang mengklasifikasikan setiap saham:

| Field | Description | Example |
|-------|-------------|---------|
| `volatility_regime` | High/medium/low volatility | "high_volatility" |
| `trend_bias` | Uptrend/downtrend/sideways | "uptrend" |
| `trend_strength` | 0-1 scale | 0.72 |
| `liquidity_score` | High/moderate/low | 1.0 (high) |
| `personality_label` | Classification | "momentum_stock" |
| `best_pattern` | Most reliable pattern | "bullish_engulfing" |
| `best_pattern_winrate` | Win rate of best pattern | 0.68 |

---

## 3. Saran Jenis Pasar & Strategi

### 3.1 Strategy Classification Engine

Aplikasi memetakan stock personality + market regime ke strategi:

```python
def classify_strategy(
    personality: dict,
    regime: str,
    conviction: float,
    user_risk_profile: dict,
) -> dict:
    """Classify the recommended trading strategy for a ticker."""

    # Step 1: Base strategy from stock personality
    vol = personality.get("volatility_regime", "medium")
    trend = personality.get("trend_bias", "sideways")
    liquidity = personality.get("liquidity_score", 0.5)

    if vol == "high_volatility" and trend == "uptrend":
        base_strategy = "momentum"
    elif vol == "low_volatility" and liquidity >= 0.8:
        base_strategy = "swing_trading"
    elif trend == "uptrend" and personality.get("trend_strength", 0) > 0.7:
        base_strategy = "position_trading"
    elif liquidity >= 0.8 and vol == "low_volatility":
        base_strategy = "dividend_investing"
    else:
        base_strategy = "swing_trading"  # Default

    # Step 2: Adjust by market regime
    if regime == "tightening":
        # Defensive: reduce aggressive strategies
        if base_strategy == "momentum":
            base_strategy = "swing_trading"
    elif regime == "easing":
        # Aggressive: can use momentum
        if base_strategy == "dividend_investing":
            base_strategy = "position_trading"

    # Step 3: Adjust by conviction
    if conviction >= 80:
        conviction_tier = "high_conviction"
        hold_period = "1-3 months"
    elif conviction >= 70:
        conviction_tier = "moderate_conviction"
        hold_period = "2-4 weeks"
    elif conviction >= 55:
        conviction_tier = "watchlist"
        hold_period = "monitor"
    else:
        conviction_tier = "low_conviction"
        hold_period = "avoid"

    # Step 4: Adjust by user risk profile
    risk_tolerance = user_risk_profile.get("risk_tolerance", "moderate")
    if risk_tolerance == "conservative" and base_strategy == "momentum":
        base_strategy = "swing_trading"
    elif risk_tolerance == "aggressive" and base_strategy == "dividend_investing":
        base_strategy = "position_trading"

    return {
        "strategy": base_strategy,
        "conviction_tier": conviction_tier,
        "expected_hold_period": hold_period,
        "regime_adjusted": regime != "neutral",
        "risk_profile_adjusted": risk_tolerance != "moderate",
        "rationale": _build_strategy_rationale(
            personality, regime, conviction, base_strategy
        ),
    }
```

### 3.2 Strategy Output Examples

```
Ticker: BBCA.JK
Personality: low_volatility, uptrend, high_liquidity
Regime: easing
Conviction: 82

→ Strategy: position_trading
→ Conviction tier: high_conviction
→ Hold period: 1-3 months
→ Rationale: "BBCA memiliki volatilitas rendah dengan tren naik kuat.
   Likuiditas tinggi memungkinkan entry/exit mudah. Regime easing
   mendukung saham perbankan. Conviction 82 menunjukkan sinyal kuat
   dari 6 faktor analisis."
```

```
Ticker: TLKM.JK
Personality: low_volatility, sideways, high_liquidity
Regime: neutral
Conviction: 68

→ Strategy: dividend_investing
→ Conviction tier: watchlist
→ Hold period: monitor
→ Rationale: "TLKM sideways dengan volatilitas rendah — cocok untuk
   strategi dividend. Likuiditas tinggi. Tunggu conviction > 70
   untuk BUY signal."
```

### 3.3 Strategy Types & Characteristics

| Strategy | Typical Hold | Target Return | Risk Level | Best For |
|----------|-------------|---------------|------------|----------|
| **Swing Trading** | 2-14 days | 5-15% per trade | Medium | Volatile, trending stocks |
| **Position Trading** | 1-6 months | 20-50% per trade | Medium | Strong trend, high conviction |
| **Momentum** | 1-4 weeks | 10-30% per trade | High | High volatility + uptrend |
| **Value Investing** | 6-24 months | 15-25% p.a. | Low | Undervalued, strong fundamental |
| **Dividend Investing** | 12+ months | 7-12% + dividend | Low | High liquidity, stable |

---

## 4. Saran Jumlah (Position Sizing)

### 4.1 Risk-Based Position Sizing (Existing Code)

```python
# risk/engine.py:43-58
# Position sizing: target risk 1% of capital, stop = 1.5 ATR

risk_amount = capital * risk_per_trade  # e.g., Rp 100jt × 1% = Rp 1jt
stop_distance = 1.5 * atr               # e.g., 1.5 × Rp 200 = Rp 300
position_value = risk_amount / (stop_distance / last_price)
position_size = min(position_value / capital, 0.1)  # max 10% of capital

# Example:
# Capital: Rp 100,000,000
# Risk per trade: 1% = Rp 1,000,000
# BBCA last price: Rp 8,200
# ATR(14): Rp 200
# Stop distance: 1.5 × 200 = Rp 300
# Position value: 1,000,000 / (300/8200) = Rp 27,333,333
# Position size: min(27.3M/100M, 10%) = 10% = Rp 10,000,000
# Shares: 10,000,000 / 8,200 = 1,219 → round to 1,200 (12 lot)
# Actual capital needed: 1,200 × 8,200 = Rp 9,840,000 + fees
```

### 4.2 Capital Calculation (Including Fees)

```python
def calculate_total_capital_needed(
    shares: int,
    price: float,
    cost_model: CostModel,
) -> dict:
    """Calculate total capital needed including all fees."""
    gross_value = shares * price
    broker_fee = cost_model.broker_fee(gross_value)
    sebi_fee = cost_model.sebi_fee(gross_value)
    kpei_fee = cost_model.kpei_fee(gross_value)
    bei_fee = cost_model.bei_fee(gross_value)
    pph = gross_value * 0.001  # PPh final 0.1%

    total_fees = broker_fee + sebi_fee + kpei_fee + bei_fee + pph
    total_capital = gross_value + total_fees

    return {
        "shares": shares,
        "price": price,
        "gross_value": gross_value,
        "fees_breakdown": {
            "broker": broker_fee,
            "sebi": sebi_fee,
            "kpei": kpei_fee,
            "bei": bei_fee,
            "pph_final": pph,
        },
        "total_fees": total_fees,
        "total_capital_needed": total_capital,
        "fee_percentage": (total_fees / gross_value) * 100,
    }
```

### 4.3 Output ke User

```
SARAN JUMLAH:
  Modal: Rp 100,000,000
  Risk per trade: 1% = Rp 1,000,000
  Position size: 10% = Rp 10,000,000
  Shares: 1,200 (12 lot)
  Harga: Rp 8,200
  Gross value: Rp 9,840,000
  Fees: Rp 39,360 (0.4%)
  Total capital needed: Rp 9,879,360
  Sisa buying power: Rp 90,120,640
```

---

## 5. Saran Kapan Masuk (Entry)

### 5.1 Entry Price Range (Existing Code)

```python
# decision/engine.py:187
entry_price_range = [round(last_price * 0.99, 2), round(last_price * 1.01, 2)]
# e.g., last_price = 8200 → entry range = [8118, 8282]
```

### 5.2 Entry Timing Logic

```python
def determine_entry_timing(
    last_price: float,
    technical_indicators: dict,
    strategy: str,
) -> dict:
    """Determine optimal entry timing."""
    rsi = technical_indicators.get("rsi_14", 50)
    sma_20 = technical_indicators.get("sma_20", last_price)
    sma_50 = technical_indicators.get("sma_50", last_price)
    macd_hist = technical_indicators.get("macd_hist", 0)
    bb_position = technical_indicators.get("bb_position", 0.5)

    entry_signals = []
    confidence = 0

    # Signal 1: Pullback to support
    if strategy == "swing_trading" and last_price <= sma_20 * 1.02:
        entry_signals.append("Pullback ke SMA20 — entry dekat support")
        confidence += 30

    # Signal 2: RSI not overbought
    if rsi < 65:
        entry_signals.append(f"RSI {rsi:.0f} — belum overbought")
        confidence += 20

    # Signal 3: MACD positive
    if macd_hist > 0:
        entry_signals.append("MACD histogram positif — momentum bullish")
        confidence += 25

    # Signal 4: Above SMA50 (trend intact)
    if last_price > sma_50:
        entry_signals.append("Harga di atas SMA50 — tren naik intakt")
        confidence += 25

    return {
        "entry_price_range": [round(last_price * 0.99, 2), round(last_price * 1.01, 2)],
        "entry_signals": entry_signals,
        "entry_confidence": min(confidence, 100),
        "recommended_entry": "limit" if confidence < 80 else "market",
        "rationale": "; ".join(entry_signals),
    }
```

### 5.3 Output ke User

```
SARAN ENTRY:
  Entry price range: Rp 8,118 – Rp 8,282
  Sinyal entry:
    ✓ Pullback ke SMA20 — entry dekat support
    ✓ RSI 58 — belum overbought
    ✓ MACD histogram positif — momentum bullish
    ✓ Harga di atas SMA50 — tren naik intakt
  Entry confidence: 100%
  Recommended order type: market (sinyal kuat)
```

---

## 6. Saran Kapan Keluar (Exit)

### 6.1 Exit Rules (Multi-Layer)

| Exit Type | Trigger | Source |
|-----------|---------|--------|
| **Stop Loss** | Price ≤ SL (entry - 1.5 × ATR) | Risk engine |
| **Take Profit** | Price ≥ TP (entry + 2 × stop_distance) | Risk engine |
| **Trailing Stop** | SL naik mengikuti harga (ATR-based) | Automated execution |
| **Conviction Exit** | Conviction < 40 (deteriorating) | Decision engine |
| **Time Stop** | No progress after N days | Strategy-dependent |
| **Fundamental Exit** | Fundamental deteriorates | Fundamental engine |

### 6.2 Stop Loss & Take Profit (Existing Code)

```python
# risk/engine.py:46-53
if atr > 0:
    stop_distance = 1.5 * atr          # 1.5x ATR
else:
    stop_distance = last_price * 0.05   # Fallback: 5% of price

stop_loss = last_price - stop_distance
take_profit = last_price + 2 * stop_distance  # R:R = 1:2

# Example:
# BBCA: last_price = 8,200, ATR = 200
# stop_distance = 1.5 × 200 = 300
# stop_loss = 8,200 - 300 = 7,900
# take_profit = 8,200 + 600 = 8,800
```

### 6.3 Trailing Stop

```python
def compute_trailing_stop(
    current_price: float,
    highest_since_entry: float,
    atr: float,
    multiplier: float = 2.0,
) -> float:
    """ATR-based trailing stop."""
    trailing = highest_since_entry - multiplier * atr
    return max(trailing, current_price * 0.95)  # Never below 5% from current
```

### 6.4 Conviction-Based Exit

```python
# decision/engine.py:130-131
if has_position and conviction < EXIT_CONVICTION_THRESHOLD:  # < 40
    return "SELL"  # Exit because conviction deteriorated
```

### 6.5 Output ke User

```
SARAN EXIT:
  Stop loss: Rp 7,900 (exit jika harga turun ke sini)
    → Loss if hit: Rp 300/lembar × 1,200 = Rp 360,000 (-3.7%)
  Take profit: Rp 8,800 (exit jika harga naik ke sini)
    → Profit if hit: Rp 600/lembar × 1,200 = Rp 720,000 (+7.3%)
  Trailing stop: Aktif setelah +3% gain (2x ATR dari highest)
  Conviction exit: SELL jika conviction turun < 40
  Risk/Reward: 1:2 (risk Rp 360K untuk profit Rp 720K)
```

---

## 7. Saran Persentase Untung

### 7.1 Expected Profit Calculation

```python
def compute_expected_profit(
    entry_price: float,
    take_profit: float,
    stop_loss: float,
    shares: int,
    total_fees: float,
    win_probability: float = 0.6,  # Estimated from backtest
) -> dict:
    """Compute expected profit with probability weighting."""
    gross_profit = (take_profit - entry_price) * shares
    gross_loss = (entry_price - stop_loss) * shares
    net_profit = gross_profit - total_fees  # Fees on sell side too
    net_loss = gross_loss + total_fees

    expected_value = (win_probability * net_profit) - ((1 - win_probability) * net_loss)

    profit_pct = ((take_profit - entry_price) / entry_price) * 100
    loss_pct = ((entry_price - stop_loss) / entry_price) * 100

    return {
        "entry_price": entry_price,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "shares": shares,
        "gross_profit_if_tp": gross_profit,
        "gross_loss_if_sl": gross_loss,
        "net_profit_if_tp": net_profit,
        "net_loss_if_sl": net_loss,
        "profit_percentage": round(profit_pct, 2),
        "loss_percentage": round(loss_pct, 2),
        "risk_reward_ratio": round(gross_profit / gross_loss, 2),
        "win_probability": win_probability,
        "expected_value": expected_value,
        "expected_value_pct": round((expected_value / (entry_price * shares)) * 100, 2),
    }
```

### 7.2 Output ke User

```
SARAN PERSENTASE UNTUNG:
  Entry: Rp 8,200
  Take profit: Rp 8,800
  Stop loss: Rp 7,900

  Jika TP hit:
    Profit kotor: Rp 720,000
    Fees jual: ~Rp 39,360
    Profit bersih: Rp 680,640
    Persentase: +7.3%

  Jika SL hit:
    Loss kotor: Rp 360,000
    Fees jual: ~Rp 39,360
    Loss bersih: Rp 399,360
    Persentase: -3.7%

  Risk/Reward: 1:2
  Win probability (dari backtest): 60%
  Expected value: +Rp 243,384 (+2.5% per trade)
  Expected value positif → trade ini menguntungkan dalam jangka panjang
```

---

## 8. Alasan Empiris & Nyata

### 8.1 6-Factor Score Breakdown

Setiap rekomendasi disertai skor dari 6 faktor analisis:

```python
# Existing: decision/engine.py:192
"contributing_scores": adjusted,
# e.g., {"technical": 72, "fundamental": 85, "macro": 78,
#         "global": 65, "relationship": 60, "sentiment": 70}
```

| Faktor | Bobot | Data Source | Empirical Basis |
|--------|-------|-------------|-----------------|
| **Technical** | 20% | OHLCV, indicators | RSI, MACD, MA, ADX, Bollinger — 30+ indicators |
| **Fundamental** | 25% | yfinance, IDX | PER, PBV, ROE, DER, growth — 5+ ratios |
| **Macro** | 15% | Macro data | BI rate, inflation, GDP, regime |
| **Global** | 15% | Global indices | S&P 500, STI, HSCEI — correlation |
| **Relationship** | 10% | Relationship matrix | Cross-asset, lead-lag, sector |
| **Sentiment** | 15% | 6 sources | Foreign flow, broker, news, social, trends, fear/greed |

### 8.2 XAI Narrative (Existing Code)

```python
# decision/engine.py:206-207
explanation = self.xai.explain(ticker, recommendation)
recommendation["explanation"] = explanation
```

XAI engine menghasilkan:
- **Narrative explanation** dalam Bahasa Indonesia
- **Top contributing factors** (faktor apa yang paling mendukung/menentang)
- **Confidence interval** (seberapa yakin sistem)
- **Counter-scenario** (kondisi apa yang bisa membatalkan rekomendasi)

### 8.3 Backtest Evidence

```python
def get_backtest_evidence(ticker: str, strategy: str) -> dict:
    """Provide backtest evidence for recommendation."""
    backtest_result = run_backtest(
        ticker=ticker,
        strategy="conviction",  # Replay historical scores
        period="2y",
    )

    return {
        "historical_hit_rate": backtest_result["win_rate"],
        "historical_sharpe": backtest_result["sharpe"],
        "historical_max_drawdown": backtest_result["max_drawdown"],
        "historical_avg_return_per_trade": backtest_result["avg_return"],
        "total_trades": backtest_result["total_trades"],
        "profitable_trades": backtest_result["winning_trades"],
        "evidence_period": f"{backtest_result['start_date']} to {backtest_result['end_date']}",
    }
```

### 8.4 Risk Metrics (Empirical)

```python
# From risk engine (existing):
"var_95_1d": var_95,           # Value at Risk 95% confidence, 1-day
"var_99_1d": var_99,           # VaR 99%
"historical_var_95_1d": hist_var_95,  # Empirical VaR (no distribution assumption)
"cvar_95_1d": cvar_95,         # Conditional VaR (expected loss beyond VaR)
"max_drawdown": max_drawdown,  # Historical worst drawdown
"annualized_volatility": volatility,  # Annualized volatility
```

### 8.5 Complete Advisory Output with Evidence

```json
{
  "recommendation_id": "BBCA.JK_2026-08-05T...",
  "ticker": "BBCA.JK",
  "action": "BUY",
  "conviction_score": 82.15,
  "strategy": "position_trading",
  "expected_hold_period": "1-3 months",

  "saran_jumlah": {
    "shares": 1200,
    "lots": 12,
    "price": 8200,
    "gross_value": 9840000,
    "total_fees": 39360,
    "total_capital_needed": 9879360,
    "position_pct_of_capital": "9.9%"
  },

  "saran_entry": {
    "entry_price_range": [8118, 8282],
    "entry_signals": [
      "Pullback ke SMA20 — entry dekat support",
      "RSI 58 — belum overbought",
      "MACD histogram positif — momentum bullish",
      "Harga di atas SMA50 — tren naik intakt"
    ],
    "entry_confidence": 100,
    "recommended_order_type": "market"
  },

  "saran_exit": {
    "stop_loss": 7900,
    "take_profit": 8800,
    "trailing_stop": "Aktif setelah +3% gain",
    "conviction_exit": "SELL jika conviction < 40",
    "risk_reward_ratio": "1:2"
  },

  "saran_persentase_untung": {
    "profit_if_tp": 720000,
    "profit_pct": 7.3,
    "loss_if_sl": 360000,
    "loss_pct": 3.7,
    "win_probability": 0.60,
    "expected_value": 243384,
    "expected_value_pct": 2.5
  },

  "alasan_empiris": {
    "contributing_scores": {
      "technical": 72,
      "fundamental": 85,
      "macro": 78,
      "global": 65,
      "relationship": 60,
      "sentiment": 70
    },
    "weights_used": {
      "technical": 0.20,
      "fundamental": 0.25,
      "macro": 0.15,
      "global": 0.15,
      "relationship": 0.10,
      "sentiment": 0.15
    },
    "regime": "easing",
    "risk_metrics": {
      "var_95_1d": 240000,
      "var_99_1d": 340000,
      "max_drawdown": -0.18,
      "annualized_volatility": 0.22
    },
    "backtest_evidence": {
      "historical_hit_rate": 0.62,
      "historical_sharpe": 1.45,
      "total_trades": 47,
      "evidence_period": "2024-08-01 to 2026-08-01"
    },
    "xai_narrative": "BBCA.JK mendapat conviction 82.15 dari kombinasi 6 faktor. Faktor fundamental (85) menjadi kontributor terbesar dengan PER 12.5, ROE 18%, DER 0.8. Technical (72) menunjukkan tren naik dengan RSI 58 (belum overbought). Macro regime easing mendukung sektor perbankan. Sentiment (70) didukung foreign net buy. Risk: VaR 1-day 95% = Rp 240,000. Counter-scenario: jika BI rate naik tak terduga, conviction bisa turun ke 60-an."
  }
}
```

---

## 9. Eksekusi Otomatis

### 9.1 Auto-Execution Conditions

Aplikasi sanggup mengeksekusi otomatis setelah semua tahapan selesai:

```python
def check_auto_execution_conditions(
    recommendation: dict,
    capital_check: dict,
    market_status: dict,
    config: dict,
) -> dict:
    """Check all conditions before auto-executing."""
    conditions = {
        "auto_trade_enabled": config.get("AUTO_TRADE_ENABLED", False),
        "action_is_buy": recommendation["action"] == "BUY",
        "conviction_sufficient": recommendation["conviction_score"] >= 70,
        "buying_power_sufficient": capital_check["can_execute"],
        "market_open": market_status["is_open"],
        "no_critical_risk_flags": "HIGH_VOLATILITY" not in recommendation.get("risk_flags", [])
                                  and "LIQUIDITY_LOW" not in recommendation.get("risk_flags", []),
        "daily_loss_limit_not_exceeded": not _daily_loss_exceeded(config),
        "max_positions_not_exceeded": not _max_positions_exceeded(config),
    }

    all_pass = all(conditions.values())
    return {
        "can_auto_execute": all_pass,
        "conditions": conditions,
        "failed_conditions": [k for k, v in conditions.items() if not v],
    }
```

### 9.2 Auto-Execution Flow

```python
def auto_execute_recommendation(recommendation: dict, broker: BrokerAdapter) -> dict:
    """Auto-execute a recommendation if all conditions pass."""
    # Step 1: Check all conditions
    conditions = check_auto_execution_conditions(...)
    if not conditions["can_auto_execute"]:
        return {
            "status": "skipped",
            "reason": "Conditions not met",
            "failed": conditions["failed_conditions"],
        }

    # Step 2: Generate order
    order = {
        "ticker": recommendation["ticker"],
        "action": "BUY",
        "shares": recommendation["position_size_shares"],
        "price": recommendation["entry_price_range"][1],  # Upper bound for market buy
        "stop_loss": recommendation["stop_loss"],
        "take_profit": recommendation["take_profit"],
        "order_type": "limit",
        "time_in_force": "DAY",
    }

    # Step 3: Execute
    result = broker.place_order(order)

    # Step 4: Log
    storage.audit("execution.auto.order_placed", {
        "order": order,
        "result": result,
        "recommendation_id": recommendation["recommendation_id"],
    })

    # Step 5: Set up monitoring (SL/TP)
    monitor.register_stop_loss(order["ticker"], order["stop_loss"])
    monitor.register_take_profit(order["ticker"], order["take_profit"])
    monitor.register_trailing_stop(order["ticker"], atr)

    return {"status": "executed", "order": order, "result": result}
```

### 9.3 Post-Execution Monitoring

```
After execution:
  ├─ Real-time price monitoring (every 1 min during market hours)
  ├─ Stop loss check: if price ≤ SL → SELL
  ├─ Take profit check: if price ≥ TP → SELL
  ├─ Trailing stop: update SL as price rises
  ├─ Conviction check: if conviction < 40 → SELL
  ├─ Daily PnL tracking
  └─ Audit trail: every action logged
```

---

## 10. Implementasi Kode

### 10.1 Current Codebase Status

| Komponen | File | Status | Description |
|----------|------|--------|-------------|
| Screener | `analysis/screener.py` | ✅ | 3 templates (technical, momentum, value) |
| Factor Screener | `analysis/factor_screener.py` | ✅ | Composite rank + factor breakdown |
| Decision Engine | `decision/engine.py` | ✅ | 6-factor scoring, conviction, action |
| Risk Engine | `risk/engine.py` | ✅ | Position sizing, SL/TP, VaR, volatility |
| XAI Engine | `xai/engine.py` | ✅ | Narrative explanation, top factors |
| Stock Personality | DB `stock_personality` | ✅ | 944 rows classified |
| Automated Execution | `execution/automated.py` | ✅ | Auto-trade with circuit breaker |
| Advisory Pipeline | — | ❌ New | Unified advisory output |
| Strategy Classifier | — | ❌ New | Personality → strategy mapping |
| Entry Timing | — | ❌ New | Technical signal-based entry |
| Expected Profit Calc | — | ❌ New | Probability-weighted expected value |
| Backtest Evidence | `backtest/engine.py` | ✅ | Conviction strategy replay |

### 10.2 Advisory API Endpoint

```python
@app.get("/api/advisory/{ticker}")
async def get_advisory(ticker: str, capital: float = TRADING_CAPITAL):
    """Complete advisory output for a ticker."""
    # Step 1: Validate data
    data_check = validate_ticker_data(ticker, storage)

    # Step 2: Get recommendation
    decision = DecisionEngine(storage)
    rec = decision.recommend(ticker, capital=capital)

    # Step 3: Classify strategy
    personality = storage.load_stock_personality(ticker)
    strategy = classify_strategy(personality, rec["regime"], rec["conviction"])

    # Step 4: Entry timing
    indicators = storage.get_latest_indicators(ticker)
    entry_timing = determine_entry_timing(rec["last_price"], indicators, strategy["strategy"])

    # Step 5: Expected profit
    expected = compute_expected_profit(
        rec["entry_price_range"][0], rec["take_profit"],
        rec["stop_loss"], rec["position_size_shares"],
        rec["total_fees"]
    )

    # Step 6: Backtest evidence
    backtest = get_backtest_evidence(ticker, strategy["strategy"])

    return {
        "ticker": ticker,
        "data_valid": data_check["valid"],
        "recommendation": rec,
        "strategy": strategy,
        "entry_timing": entry_timing,
        "expected_profit": expected,
        "backtest_evidence": backtest,
        "xai_explanation": rec.get("explanation"),
    }
```

---

## 11. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **08** (Trading Algoritmik) | Decision engine pattern, multi-factor scoring |
| **11** (Knowledge Transfer) | Decision engine pattern dari proyek existing |
| **16** (Strategi Mencari Keuntungan) | Strategi trading (swing, position, dividend) |
| **18** (Modul Engine) | Decision engine, risk engine, XAI engine modul |
| **19** (Flow Logic) | Decision flow, conviction, action state machine, rules T1-T8 |
| **39** (Screening AI/ML) | Screener, factor screener, pattern memory |
| **45** (Robo-Advisor) | Goal-based investing, risk profile |
| **46** (Prediksi & Portfolio Pipeline) | Portfolio candidate pipeline |
| **57** (User Onboarding) | Risk profile assessment |
| **74** (Financial Management) | Capital calculation, buying power, screen→execute |
| **77** (Performance Attribution) | Backtest evidence, benchmark comparison |

---

## 12. Checklist Implementasi

### Data Testing
- [ ] `validate_ticker_data()` — quality, freshness, gaps
- [ ] Stock personality loading
- [ ] Market regime detection
- [ ] Unit tests

### Screening
- [ ] Technical screener (✅ existing)
- [ ] Momentum screener (✅ existing)
- [ ] Value screener (✅ existing)
- [ ] Factor screener (✅ existing)
- [ ] Equity-only filter (✅ existing)
- [ ] Unit tests

### Strategy Classification
- [ ] `classify_strategy()` — personality → strategy
- [ ] Regime adjustment
- [ ] Conviction tier
- [ ] User risk profile adjustment
- [ ] Strategy rationale generator
- [ ] Unit tests

### Entry Timing
- [ ] `determine_entry_timing()` — technical signals
- [ ] Entry confidence scoring
- [ ] Order type recommendation
- [ ] Unit tests

### Expected Profit
- [ ] `compute_expected_profit()` — probability-weighted
- [ ] Fee-adjusted profit/loss
- [ ] Risk/reward ratio
- [ ] Win probability from backtest
- [ ] Unit tests

### Advisory API
- [ ] `/api/advisory/{ticker}` — complete advisory output
- [ ] `/api/advisory/screen` — screen all + advisory for top N
- [ ] JSON response with all sections
- [ ] Integration tests

### Auto-Execution
- [ ] Condition checker (✅ existing in automated.py)
- [ ] Order generation
- [ ] Post-execution monitoring (SL/TP/trailing)
- [ ] Audit trail
- [ ] Unit tests

### XAI Integration
- [ ] Narrative explanation (✅ existing)
- [ ] Top contributing factors (✅ existing)
- [ ] Counter-scenario analysis
- [ ] Confidence interval
- [ ] Unit tests

---

## Referensi

1. `src/trading_system/decision/engine.py` — 6-factor weighted decision engine
2. `src/trading_system/risk/engine.py` — Position sizing, VaR, risk metrics
3. `src/trading_system/xai/engine.py` — XAI narrative generation
4. `src/trading_system/execution/automated.py` — Auto-execution with condition check
5. `src/trading_system/api/app.py` — `/api/recommend/{ticker}`, `/api/explain/{ticker}`
6. `pustaka/39-screening-aiml-pattern-memory.md` — Screening & AI/ML
7. `pustaka/74-trading-financial-management-capital-operations.md` — Capital & position sizing
8. `pustaka/85-backtest-to-live-gap-prevention.md` — Backtest-to-live gap prevention
9. `pustaka/86-gigantic-ai-autonomous-trading-system.md` — Autonomous AI architecture

---

> **Catatan:** Aplikasi ini tidak sekadar menampilkan data — aplikasi ini **memberikan saran** yang konkret, lengkap, dan berbasis data empiris. Setiap saran (apa, berapa, kapan masuk, kapan keluar, berapa untung) disertai alasan yang dapat ditelusuri: skor 6 faktor, backtest historis, risk metrics, dan narrative XAI. Jika user mengaktifkan auto-trade, aplikasi sanggup mengeksekusi otomatis setelah semua tahapan perhitungan selesai dan semua kondisi terpenuhi. Inilah perbedaan antara "aplikasi menampilkan chart" dan "aplikasi yang menjadi trading advisor." Untuk memastikan saran yang menguntungkan di backtest juga menguntungkan di live trading, lihat `85-backtest-to-live-gap-prevention.md`. Untuk arsitektur AI otonom yang menjalankan advisory ini secara mandiri, lihat `86-gigantic-ai-autonomous-trading-system.md`.
