# Backtest-to-Live Gap: Mencegah Keuntungan Ilusi Menjadi Kerugian Nyata

> **Dokumen 85** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Mengatasi fenomena "saat testing di aplikasi semuanya benar, berhasil, dan menguntungkan — tapi saat trading nyata, terjadi kebalikannya." Dokumen ini menjawab: apakah aplikasi sudah mengatasi agar di trading nyata tetap menguntungkan? Dan apa yang masih perlu diperbaiki.
>
> **Konteks:** Doc 29 bahas backtest bias (survivorship, look-ahead, overfitting) secara teoritis. Doc 09 bahas behavioral finance. Doc 51 bahas MLOps model risk. Tapi tidak ada dokumen yang menyatukan semuanya dari perspektif **backtest-to-live gap prevention** — mengapa backtest menipu, apa yang aplikasi lakukan untuk mencegah, dan apa yang masih kurang.

---

## Daftar Isi

1. [The Problem: Backtest Untung, Live Rugi](#1-the-problem-backtest-untung-live-rugi)
2. [Root Causes: Mengapa Backtest Menipu](#2-root-causes-mengapa-backtest-menipu)
3. [Apa yang Aplikasi Sudah Lakukan](#3-apa-yang-aplikasi-sudah-lakukan)
4. [Apa yang Masih Kurang](#4-apa-yang-masih-kurang)
5. [Backtest-to-Live Transition Protocol](#5-backtest-to-live-transition-protocol)
6. [Live Performance Monitoring](#6-live-performance-monitoring)
7. [Continuous Validation Framework](#7-continuous-validation-framework)
8. [Hubungan dengan Dokumen Lain](#8-hubungan-dengan-dokumen-lain)

---

## 1. The Problem: Backtest Untung, Live Rugi

### 1.1 Fenomena Umum

```
BACKTEST (historical):
  Equity curve: ↗↗↗↗↗  (selalu naik)
  Win rate: 75%
  Sharpe: 2.1
  Max drawdown: -8%
  Return: +45% p.a.
  → "Sistem ini menguntungkan!"

LIVE TRADING (real):
  Equity curve: ↗↘↘↗↘↘↘  (turun)
  Win rate: 42%
  Sharpe: 0.3
  Max drawdown: -22%
  Return: -15%
  → "Kok bisa beda jauh?"
```

### 1.2 Statistik Industri

| Metric | Backtest | Live (typical) | Degradation |
|--------|----------|----------------|-------------|
| Win rate | 65-80% | 40-55% | -20 to -30% |
| Sharpe ratio | 1.5-3.0 | 0.3-1.0 | -50 to -70% |
| Max drawdown | -5% to -15% | -15% to -35% | 2-3x worse |
| Return p.a. | +30-50% | -10% to +15% | -60 to -130% |
| Slippage | 0.05% | 0.15-0.50% | 3-10x worse |

### 1.3 Pertanyaan User

> "Pada saat testing di aplikasi, biasanya semuanya benar dan berhasil serta menguntungkan, pada saat trading nyata, terjadi kebalikannya; apakah aplikasi sudah mengatasi agar tidak terjadi hal tersebut?"

**Jawaban singkat:** Aplikasi sudah memiliki **8 mekanisme** untuk mengatasi gap ini (lihat §3), tapi masih ada **6 area** yang perlu diperbaiki (lihat §4). Backtest-to-live gap **tidak bisa dihilangkan 100%**, tapi bisa **diminimalkan** dengan disiplin proses.

---

## 2. Root Causes: Mengapa Backtest Menipu

### 2.1 Tujuh Penyebab Utama

| # | Cause | Backtest Assumption | Reality | Impact |
|---|-------|---------------------|---------|--------|
| 1 | **Look-ahead bias** | Sinyal di bar t, eksekusi di bar t | Sinyal di bar t, eksekusi di bar t+1 | Overstated return 5-15% |
| 2 | **Survivorship bias** | Hanya saham yang masih listed | Termasuk yang delisted/suspended | Overstated return 10-30% |
| 3 | **Overfitting** | Parameter di-tune pada data yang sama | Parameter tidak generalizable | Backtest bagus, live gagal |
| 4 | **Unrealistic costs** | Slippage 0.05%, fee minimal | Slippage 0.15-0.50%, fee penuh | Overstated return 5-20% |
| 5 | **Market impact** | Order tidak menggerakkan harga | Order besar menggerakkan harga | Fill price lebih buruk |
| 6 | **Regime change** | Backtest pada 1 regime (bull) | Live di regime berbeda (bear/sideways) | Strategi tidak adaptif |
| 7 | **Behavioral gap** | Backtest tidak ada emosi | Live: fear, greed, panic, hesitation | Eksekusi tidak disiplin |

### 2.2 Detail Setiap Cause

#### Cause 1: Look-Ahead Bias

```
BACKTEST (wrong):
  Bar t: close = 8,200 → signal = BUY
  Bar t: execute at 8,200  ← MENGGUNAKAN INFO YANG BELUM ADA

REALITY:
  Bar t: close = 8,200 → signal = BUY (generated after market close)
  Bar t+1: execute at open = 8,350  ← HARGA SUDAH BERUBAH
```

**Aplikasi sudah atasi:** Next-bar-open execution (§3.1)

#### Cause 2: Survivorship Bias

```
BACKTEST (wrong):
  Universe: BBCA, TLKM, ASII, UNVR, BMRI (semua masih listed di 2026)
  → Semua naik dari 2020-2026 → return tinggi

REALITY:
  Universe 2020: juga ada saham yang delisted (e.g., PTBA suspend, saham gorengan)
  → Jika termasuk yang delisted, return lebih rendah
```

**Aplikasi sudah atasi:** Survivorship-free backtest dengan listing/delisting date filter (§3.2)

#### Cause 3: Overfitting

```
BACKTEST (wrong):
  Strategy: RSI(14) < 32.5 AND ADX > 22.3 AND volume > 1.8x avg
  → Tuned on 2020-2024 data → return 45%
  → Test on same data → return 45% (of course!)

REALITY:
  Same strategy on 2025-2026 → return -5%
  → Parameter tidak generalizable
```

**Aplikasi sudah atasi:** Walk-forward validation, purged TSS (§3.3) — tapi **belum mandatory**

#### Cause 4: Unrealistic Costs

```
BACKTEST (wrong):
  Buy 1,000 shares @ 8,200 = Rp 8,200,000
  Fee: 0.15% = Rp 12,300
  Slippage: 0.05% = Rp 4,100
  Total cost: Rp 16,400

REALITY:
  Buy 1,000 shares @ 8,200
  Fee: 0.15% + levy 0.004% = Rp 12,663
  Slippage: 0.25% (thin liquidity) = Rp 20,500
  Spread cost: 0.10% = Rp 8,200
  Total cost: Rp 41,363 (2.5x backtest assumption)
```

**Aplikasi sudah atasi:** Realistic cost model dengan square-root slippage (§3.4) — tapi **slippage real bisa lebih tinggi**

#### Cause 5: Market Impact

```
BACKTEST:
  Order 10,000 shares → fill at 8,200 (no impact)

REALITY (small-cap, thin liquidity):
  Order 10,000 shares → market impact:
  - Buy 2,000 @ 8,200
  - Buy 2,000 @ 8,250 (price moved up)
  - Buy 2,000 @ 8,300
  - Buy 2,000 @ 8,380
  - Buy 2,000 @ 8,450
  Average fill: 8,316 (1.4% worse than backtest)
```

**Aplikasi sudah atasi:** Liquidity-aware slippage model (§3.4) — tapi **model adalah estimasi, bukan realitas**

#### Cause 6: Regime Change

```
BACKTEST (2020-2024: bull market + easing):
  Strategy momentum → return 45%
  → "Strategi ini menguntungkan!"

REALITY (2025: tightening + bear market):
  Same strategy momentum → return -20%
  → Regime berubah, strategi tidak adaptif
```

**Aplikasi sudah atasi:** Regime filter di decision engine (§3.5) — tapi **regime detection bisa terlambat**

#### Cause 7: Behavioral Gap

```
BACKTEST:
  Signal: BUY → execute immediately → hold until SL/TP
  No emotion, no hesitation, no second-guessing

REALITY:
  Signal: BUY → "Hmm, apa yakin?" → wait 2 days → buy at higher price
  Price drops → panic → sell before SL → realize loss
  Price rises → greedy → don't sell at TP → price reverses → sell at loss
```

**Aplikasi sudah atasi:** Automated execution (§3.6) — tapi **hanya jika auto_trade_enabled = true**

---

## 3. Apa yang Aplikasi Sudah Lakukan

### 3.1 Next-Bar-Open Execution (Anti Look-Ahead)

```python
# backtest/engine.py:129-167
class BacktestEngine:
    def _run_core(self, df, strategy, ...):
        """Core backtest loop — next-bar-open execution.

        Signal generated at bar t is executed at the **open** of bar t+1
        to eliminate look-ahead bias.
        """
        df["next_open"] = df["open"].shift(-1)
        # Signal at bar t → execute at next_open (bar t+1)
```

**Status:** ✅ Implemented. Sinyal di bar t dieksekusi di open bar t+1.

### 3.2 Survivorship-Free Backtest

```python
# backtest/engine.py:40-78
def run(self, ticker, strategy, ..., survivorship_free=True):
    """Survivorship bias prevention: clip to listing/delisting dates."""
    if survivorship_free:
        info = self.storage.get_instrument_status(ticker)
        listing = info.get("listing_date") or info.get("ipo_date")
        delisting = info.get("delisting_date")
        if listing:
            df = df[df.index >= pd.Timestamp(listing)]
        if delisting:
            df = df[df.index < pd.Timestamp(delisting)]
        # Also mask out suspension periods
        suspensions = self.storage.load_suspensions(ticker)
        for s in suspensions:
            # Remove suspended periods from backtest
```

**Status:** ✅ Implemented. Backtest hanya menggunakan data dalam periode listing aktif.

### 3.3 Walk-Forward Validation

```python
# backtest/metrics.py:320-398
def walk_forward_analysis(df, strategy_factory, n_splits=5, ...):
    """Run walk-forward (in-sample/out-of-sample) analysis.

    Splits data into n_splits segments, each with train_size training
    and test_size out-of-sample test period.
    """
    # Train on [t-k, t], test on [t, t+h]
    # Slide window, re-optimize, re-test
    # Report OOS performance consistency

# ai_learning/walk_forward.py
class WalkForwardValidator:
    """Walk-forward validation for time-series models.

    Supports rolling and expanding window modes.
    """
    # Config: train_size=252 (1y), test_size=63 (3m), step_size=63

# ai_learning/purged_tss.py
class PurgedTimeSeriesSplit:
    """Purged time-series split — anti-leakage.

    Removes observations near the train/test boundary to prevent
    information leakage from labels that span the boundary.
    """
```

**Status:** ✅ Implemented. Tapi **belum mandatory** — user bisa skip walk-forward dan langsung backtest.

### 3.4 Realistic Cost Model

```python
# risk/costs.py:60-195
class CostModel:
    """Consolidated transaction cost model for IDX.

    Single source of truth for broker fees, levy, tax, and slippage.
    """
    buy_fee: float = 0.0015      # 0.15%
    sell_fee: float = 0.0025     # 0.25% (includes PPh)
    levy: float = 0.000043       # 0.0043%
    slippage: float = 0.0005     # 0.05% base

    def estimate_slippage(self, order_value, avg_daily_value):
        """Slippage based on order size vs daily volume."""
        ratio = order_value / avg_daily_value
        if ratio < 0.001: return self.slippage        # 0.05%
        if ratio < 0.01:  return self.slippage * 2    # 0.10%
        return self.slippage * 4                       # 0.20%

    def simulate_fill(self, action, shares, last_price, avg_daily_value):
        """Simulate order fill with slippage and fees."""
        slip = self.estimate_slippage(order_value, avg_daily_value)
        fill_price = last_price * (1 + slip) if buy else last_price * (1 - slip)
```

**Status:** ✅ Implemented. Slippage adaptif berdasarkan likuiditas. Tapi **real slippage bisa lebih tinggi** dari estimasi.

### 3.5 Regime Filter

```python
# decision/engine.py:45-54
def apply_regime_filter(self, scores, macro_regime):
    """Adjust scores based on macro regime."""
    if macro_regime == "tightening":
        adjusted["macro"] *= 0.8
        adjusted["technical"] *= 0.9
    elif macro_regime == "easing":
        adjusted["macro"] *= 1.1
        adjusted["fundamental"] *= 1.05

# AI Learning: dynamic weight optimization
weights = self.ai_learning.get_factor_weights(ticker, macro_regime)
```

**Status:** ✅ Implemented. Skor disesuaikan berdasarkan regime. Tapi **regime detection bisa terlambat** 1-2 bulan.

### 3.6 Automated Execution (Anti Behavioral Gap)

```python
# execution/automated.py
class AutomatedExecutionEngine:
    """Automated execution — removes human emotion from trading.

    - Signal → execute immediately (no hesitation)
    - SL/TP → auto-sell (no panic/greed)
    - Daily loss limit → auto-halt (no revenge trading)
    - Circuit breaker → auto-halt on market crash
    """
    # 1. Check SL/TP for existing positions
    # 2. Get recommendation from Decision Engine
    # 3. Execute BUY/SELL automatically
    # 4. No human intervention (if auto_trade_enabled)
```

**Status:** ✅ Implemented. Tapi **default = false** (AUTO_TRADE_ENABLED = false). User harus explicitly enable.

### 3.7 Circuit Breaker & Daily Loss Limit

```python
# risk/circuit_breaker.py
class CircuitBreaker:
    """Halts trading when extreme market events occur.
    - IHSG drop > 3%: caution mode
    - IHSG drop > 5%: trading halt
    - Individual stock drop > 20%: auto-rejection
    """

# execution/automated.py:284-330
def _check_daily_loss_limit(self):
    """Check if daily loss exceeds limit. Returns True if trading should STOP.

    Persisted in system_state so stays in effect across process restarts.
    """
    if total_pnl_today < -self.daily_loss_limit:
        self.storage.set_state("execution_halted_date", today)
        return True  # STOP trading
```

**Status:** ✅ Implemented. Trading berhenti otomatis jika loss harian melewati batas.

### 3.8 Paper Trading (Pre-Live Validation)

```python
# paper_trading/engine.py
class PaperTradingEngine:
    """Simulates orders from recommendations with current market prices.

    - Uses real-time prices (not historical)
    - Computes realistic fill price, fees, PnL
    - No real money at risk
    - Validates that backtest performance translates to live conditions
    """
    def simulate(self, ticker):
        decision = DecisionEngine(self.storage).recommend(ticker)
        orders = self.portfolio.generate_orders(rec)
        fill = self.execution.simulate_fill(order, last_price, avg_daily_value)
        # → Compare paper PnL vs backtest expectation
```

**Status:** ✅ Implemented. Paper trading menggunakan harga real-time untuk validasi.

### 3.9 Summary: 8 Mekanisme yang Sudah Ada

| # | Mekanisme | File | Status | Gap |
|---|-----------|------|--------|-----|
| 1 | Next-bar-open execution | `backtest/engine.py` | ✅ | — |
| 2 | Survivorship-free backtest | `backtest/engine.py` | ✅ | — |
| 3 | Walk-forward validation | `backtest/metrics.py`, `ai_learning/walk_forward.py` | ✅ | Belum mandatory |
| 4 | Realistic cost model | `risk/costs.py` | ✅ | Real slippage bisa lebih tinggi |
| 5 | Regime filter | `decision/engine.py` | ✅ | Detection delay 1-2 bulan |
| 6 | Automated execution | `execution/automated.py` | ✅ | Default off |
| 7 | Circuit breaker + daily loss limit | `risk/circuit_breaker.py` | ✅ | — |
| 8 | Paper trading | `paper_trading/engine.py` | ✅ | Belum ada comparison vs backtest |

---

## 4. Apa yang Masih Kurang

### 4.1 Six Gaps yang Perlu Diatasi

| # | Gap | Dampak | Solusi yang Diperlukan |
|---|-----|--------|----------------------|
| 1 | **Walk-forward belum mandatory** | User bisa skip → overfitting tidak terdeteksi | Gate: backtest tanpa WFA → warning |
| 2 | **Paper trading belum compare dengan backtest** | Tidak tahu seberapa besar gap | Paper-vs-backtest comparison report |
| 3 | **Slippage model undersized** | Real slippage 2-5x estimasi | Conservative slippage multiplier |
| 4 | **Regime detection delay** | Sinyal based on stale regime | Faster regime detection (weekly) |
| 5 | **No live performance degradation alert** | Tidak tahu saat strategi berhenti working | Live-vs-backtest Sharpe comparison |
| 6 | **No mandatory paper period before live** | Langsung live tanpa paper validation | Minimum 30 hari paper before live |

### 4.2 Gap 1: Walk-Forward Belum Mandatory

```python
# CURRENT: user can skip walk-forward
result = backtest.run(ticker, strategy)  # No WFA check

# PROPOSED: gate backtest with WFA
def run_validated_backtest(ticker, strategy):
    """Run backtest with mandatory walk-forward validation."""
    wfa = walk_forward_analysis(df, strategy_factory, n_splits=5)

    if wfa["oos_consistency"] < 0.5:
        return {
            "status": "warning",
            "message": "Walk-forward OOS consistency < 50%. Strategy likely overfit.",
            "wfa_results": wfa,
            "recommendation": "Do NOT use this strategy for live trading.",
        }

    if wfa["oos_mean_return"] < 0:
        return {
            "status": "warning",
            "message": "Walk-forward OOS mean return is negative. Strategy not profitable out-of-sample.",
            "wfa_results": wfa,
        }

    # Only proceed with full backtest if WFA passes
    return backtest.run(ticker, strategy)
```

### 4.3 Gap 2: Paper-vs-Backtest Comparison

```python
def compare_paper_vs_backtest(ticker: str, strategy: str, paper_days: int = 30) -> dict:
    """Compare paper trading results with backtest expectations.

    This is the CRITICAL bridge between backtest and live.
    If paper performance is significantly worse than backtest,
    the strategy is NOT ready for live trading.
    """
    # Get backtest expectation
    backtest_result = backtest.run(ticker, strategy, period="2y")
    backtest_sharpe = backtest_result["metrics"]["sharpe_ratio"]
    backtest_win_rate = backtest_result["metrics"]["win_rate"]

    # Get paper trading results (last N days)
    paper_trades = storage.get_paper_trades(ticker, days=paper_days)
    paper_sharpe = compute_sharpe(paper_trades)
    paper_win_rate = compute_win_rate(paper_trades)

    # Compute degradation
    sharpe_degradation = (backtest_sharpe - paper_sharpe) / backtest_sharpe
    winrate_degradation = (backtest_win_rate - paper_win_rate) / backtest_win_rate

    # Assess
    if sharpe_degradation > 0.5:
        verdict = "REJECT — Sharpe degradation > 50%. Strategy not ready for live."
    elif sharpe_degradation > 0.3:
        verdict = "CAUTION — Sharpe degradation 30-50%. Investigate before live."
    else:
        verdict = "PASS — Paper performance within acceptable range of backtest."

    return {
        "backtest": {"sharpe": backtest_sharpe, "win_rate": backtest_win_rate},
        "paper": {"sharpe": paper_sharpe, "win_rate": paper_win_rate},
        "degradation": {
            "sharpe_pct": round(sharpe_degradation * 100, 1),
            "winrate_pct": round(winrate_degradation * 100, 1),
        },
        "verdict": verdict,
        "paper_days": paper_days,
    }
```

### 4.4 Gap 3: Conservative Slippage Multiplier

```python
# CURRENT: slippage 0.05% base, max 0.20%
# REALITY: IDX small-cap slippage can be 0.30-0.50%

# PROPOSED: add conservative multiplier
class CostModel:
    def __init__(self, ..., slippage_multiplier: float = 1.0):
        self.slippage_multiplier = slippage_multiplier

    def estimate_slippage(self, order_value, avg_daily_value):
        base = super().estimate_slippage(order_value, avg_daily_value)
        return base * self.slippage_multiplier

# For backtest: use slippage_multiplier = 2.0 (conservative)
# For paper: use slippage_multiplier = 1.5 (moderate)
# For live: use slippage_multiplier = 1.0 (actual)
```

### 4.5 Gap 4: Faster Regime Detection

```python
# CURRENT: regime detected from macro engine (monthly data)
# PROBLEM: regime change in week 1, detected in week 4-6

# PROPOSED: weekly regime check using daily proxy
def detect_regime_fast(ticker: str) -> str:
    """Fast regime detection using daily market data."""
    ihsg = storage.load_ohlcv("^JKSE")  # IHSG daily
    recent_20d = ihsg["close"].tail(20)
    recent_50d = ihsg["close"].tail(50)

    # Simple proxy: 20d vs 50d moving average
    if recent_20d.mean() > recent_50d.mean() * 1.02:
        return "bullish"
    elif recent_20d.mean() < recent_50d.mean() * 0.98:
        return "bearish"
    else:
        return "neutral"
```

### 4.6 Gap 5: Live Performance Degradation Alert

```python
def check_live_degradation(ticker: str, strategy: str) -> dict:
    """Monitor if live performance is degrading vs backtest expectation.

    Should run weekly during live trading.
    """
    # Get live trading results (last 30 days)
    live_trades = storage.get_live_trades(ticker, days=30)
    if len(live_trades) < 5:
        return {"status": "insufficient_data"}

    live_sharpe = compute_sharpe(live_trades)
    live_win_rate = compute_win_rate(live_trades)

    # Get backtest benchmark
    backtest_result = backtest.run(ticker, strategy, period="2y")
    bt_sharpe = backtest_result["metrics"]["sharpe_ratio"]

    # Degradation check
    degradation = (bt_sharpe - live_sharpe) / bt_sharpe if bt_sharpe > 0 else 1.0

    if degradation > 0.6:
        return {
            "status": "critical",
            "message": f"Live Sharpe degraded {degradation:.0%} vs backtest. "
                       f"Consider stopping live trading for {ticker}.",
            "action": "STOP",
            "live_sharpe": live_sharpe,
            "backtest_sharpe": bt_sharpe,
        }
    elif degradation > 0.4:
        return {
            "status": "warning",
            "message": f"Live Sharpe degraded {degradation:.0%}. Monitor closely.",
            "action": "MONITOR",
        }
    return {"status": "ok", "degradation_pct": round(degradation * 100, 1)}
```

### 4.7 Gap 6: Mandatory Paper Period

```python
# PROPOSED: enforce minimum paper trading period before live
def check_paper_requirement(ticker: str) -> dict:
    """Check if ticker has sufficient paper trading history before going live."""
    paper_trades = storage.get_paper_trades(ticker, days=30)
    min_paper_days = 30
    min_paper_trades = 5

    days_traded = count_distinct_days(paper_trades)
    total_trades = len(paper_trades)

    if days_traded < min_paper_days:
        return {
            "ready_for_live": False,
            "reason": f"Only {days_traded} paper trading days. Need {min_paper_days}.",
        }
    if total_trades < min_paper_trades:
        return {
            "ready_for_live": False,
            "reason": f"Only {total_trades} paper trades. Need {min_paper_trades}.",
        }

    # Check paper profitability
    paper_pnl = sum(t["pnl"] for t in paper_trades)
    if paper_pnl < 0:
        return {
            "ready_for_live": False,
            "reason": f"Paper trading is losing money (PnL: {paper_pnl}). "
                       "Do NOT go live with a losing strategy.",
        }

    return {"ready_for_live": True, "paper_pnl": paper_pnl}
```

---

## 5. Backtest-to-Live Transition Protocol

### 5.1 Mandatory Steps Before Going Live

```
┌─────────────────────────────────────────────────────────────────┐
│  BACKTEST-TO-LIVE TRANSITION PROTOCOL                            │
│                                                                  │
│  Step 1: BACKTEST WITH BIAS PREVENTION                           │
│  ├─ Next-bar-open execution (anti look-ahead)                   │
│  ├─ Survivorship-free (include delisted)                        │
│  ├─ Realistic costs (fee + levy + PPh + slippage)              │
│  └─ Conservative slippage multiplier (2x base)                 │
│       │                                                          │
│       ▼  PASS if Sharpe > 1.0 and max DD < 20%                  │
│                                                                  │
│  Step 2: WALK-FORWARD VALIDATION                                 │
│  ├─ 5 splits minimum                                            │
│  ├─ OOS consistency > 50%                                       │
│  ├─ OOS mean return > 0                                         │
│  └─ Walk-Forward Efficiency > 50%                               │
│       │                                                          │
│       ▼  PASS if OOS consistency > 50%                          │
│                                                                  │
│  Step 3: PAPER TRADING (minimum 30 days)                         │
│  ├─ Use real-time prices                                        │
│  ├─ Execute all signals (no cherry-picking)                     │
│  ├─ Track PnL, win rate, Sharpe                                │
│  └─ Compare with backtest expectation                           │
│       │                                                          │
│       ▼  PASS if degradation < 30%                              │
│                                                                  │
│  Step 4: LIVE TRADING (small size first)                         │
│  ├─ Start with 10% of intended capital                          │
│  ├─ Auto-trade enabled (remove emotion)                         │
│  ├─ Daily loss limit active                                     │
│  ├─ Circuit breaker active                                      │
│  └─ SL/TP auto-monitoring                                       │
│       │                                                          │
│       ▼  PASS if live Sharpe > 50% of backtest after 30 days    │
│                                                                  │
│  Step 5: SCALE UP                                                │
│  ├─ Increase to 50% of intended capital                         │
│  ├─ Continue monitoring degradation                             │
│  └─ If degradation > 50%: STOP, return to Step 2               │
│       │                                                          │
│       ▼  PASS if stable after 60 days                            │
│                                                                  │
│  Step 6: FULL SIZE                                               │
│  ├─ 100% of intended capital                                    │
│  ├─ Continuous monitoring                                       │
│  └─ Weekly degradation check                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Stop Conditions

| Condition | Action | Rationale |
|-----------|--------|-----------|
| Live Sharpe < 50% of backtest | **STOP** | Strategy not working in live |
| Live max drawdown > 2x backtest | **STOP** | Risk higher than expected |
| Live win rate < 60% of backtest | **CAUTION** | Signal quality degrading |
| Daily loss limit hit | **HALT** | Prevent catastrophic loss |
| Regime change detected | **REVIEW** | Strategy may not adapt |
| 3 consecutive losing trades | **REVIEW** | Check if strategy still valid |

---

## 6. Live Performance Monitoring

### 6.1 Daily Check

```python
def daily_live_check() -> dict:
    """Daily check during live trading."""
    checks = {
        "daily_pnl": compute_daily_pnl(),
        "open_positions": get_open_positions(),
        "sl_tp_breached": check_sl_tp(),
        "circuit_breaker_status": circuit_breaker.status(),
        "daily_loss_limit": _check_daily_loss_limit(),
    }

    # Alert if any critical
    if checks["daily_loss_limit"]:
        send_alert("DAILY LOSS LIMIT HIT — trading halted")
    if checks["sl_tp_breached"]:
        send_alert(f"SL/TP breached for {checks['sl_tp_breached']}")

    return checks
```

### 6.2 Weekly Degradation Report

```python
def weekly_degradation_report() -> dict:
    """Weekly report comparing live vs backtest performance."""
    report = {}
    for ticker in get_live_tickers():
        degradation = check_live_degradation(ticker, strategy)
        report[ticker] = degradation

        if degradation["status"] == "critical":
            send_alert(f"CRITICAL: {ticker} live performance degraded. Consider stopping.")

    return report
```

### 6.3 Monthly Review

```python
def monthly_review() -> dict:
    """Monthly review of all live strategies."""
    return {
        "strategies_live": count_live_strategies(),
        "strategies_profitable": count_profitable(),
        "strategies_degraded": count_degraded(),
        "strategies_stopped": count_stopped(),
        "total_live_pnl": compute_total_pnl(),
        "avg_degradation_pct": compute_avg_degradation(),
        "recommendation": _monthly_recommendation(),
    }
```

---

## 7. Continuous Validation Framework

### 7.1 The Validation Loop

```
┌──────────────────────────────────────────────────────┐
│              CONTINUOUS VALIDATION LOOP               │
│                                                      │
│  ┌──────────┐                                        │
│  │ BACKTEST │ ← Historical data                      │
│  └────┬─────┘                                        │
│       │                                              │
│       ▼                                              │
│  ┌──────────┐                                        │
│  │   WFA    │ ← Out-of-sample test                   │
│  └────┬─────┘                                        │
│       │                                              │
│       ▼                                              │
│  ┌──────────┐                                        │
│  │  PAPER   │ ← Real-time, no money                  │
│  └────┬─────┘                                        │
│       │                                              │
│       ▼                                              │
│  ┌──────────┐     ┌──────────┐                       │
│  │  LIVE    │────→│ MONITOR  │ ← Degradation check   │
│  │ (small)  │     └────┬─────┘                       │
│  └──────────┘          │                             │
│                        │                             │
│              ┌─────────┴─────────┐                   │
│              │                   │                   │
│              ▼                   ▼                   │
│         ┌────────┐         ┌─────────┐               │
│         │ SCALE  │         │  STOP   │               │
│         │  UP    │         │ & REVIEW│               │
│         └────────┘         └─────────┘               │
│              │                   │                   │
│              │                   └───→ Back to WFA   │
│              ▼                                       │
│         ┌────────┐                                   │
│         │ FULL   │                                   │
│         │ SIZE   │                                   │
│         └────┬───┘                                   │
│              │                                       │
│              ▼                                       │
│         ┌──────────┐                                 │
│         │ CONTINUE │ ← Weekly degradation check      │
│         │ MONITOR  │   Monthly review                 │
│         └──────────┘   Quarterly re-validation       │
└──────────────────────────────────────────────────────┘
```

### 7.2 Re-Validation Triggers

| Trigger | Action | Rationale |
|---------|--------|-----------|
| Regime change detected | Re-run WFA | Strategy may not work in new regime |
| Live degradation > 40% | Stop + re-validate | Strategy losing effectiveness |
| 3 months live | Quarterly review | Regular check |
| New data available | Re-train AI weights | Weights may need update |
| Market crash (>10% IHSG) | Halt + review | Extreme event, strategy may fail |

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **09** (Behavioral Finance) | Emotional biases yang menyebabkan behavioral gap |
| **19** (Flow Logic) | Testing rules, backtest rules (T1-T8), paper trading |
| **20** (Syarat Robot Auto Trading) | Automated execution requirements |
| **29** (Backtesting) | Backtest bias theory: survivorship, look-ahead, overfitting, WFA, Monte Carlo |
| **39** (Screening AI/ML) | ML model validation, purged TSS |
| **51** (MLOps Model Risk) | Model registry, regime change, model limitations |
| **71** (Eval & A/B Testing) | Strategy evaluation, gated promotion |
| **77** (Performance Attribution) | Live performance vs benchmark |
| **83** (Advisory System) | Recommendation pipeline yang menghasilkan sinyal |
| **84** (Data Pipeline) | Data quality yang mempengaruhi backtest accuracy |

---

## 9. Checklist: Apakah Aplikasi Siap untuk Live Trading?

### Backtest Quality
- [x] Next-bar-open execution (anti look-ahead)
- [x] Survivorship-free (include delisted/suspended)
- [x] Realistic cost model (fee + levy + PPh + slippage)
- [x] Lot size 100, tick size IDX
- [x] Warmup period skip (anti look-ahead for indicators)
- [ ] Conservative slippage multiplier (2x for backtest)
- [ ] Monte Carlo simulation mandatory

### Validation
- [x] Walk-forward analysis available
- [x] Purged time-series split available
- [ ] Walk-forward **mandatory** before live
- [ ] OOS consistency threshold enforced (> 50%)
- [ ] Paper-vs-backtest comparison report

### Paper Trading
- [x] Paper trading engine available
- [x] Uses real-time prices
- [x] Simulates realistic fill + fees
- [ ] Minimum 30 days paper before live
- [ ] Paper profitability check before live

### Live Trading
- [x] Automated execution (removes emotion)
- [x] Circuit breaker (IHSG crash halt)
- [x] Daily loss limit (auto-halt)
- [x] SL/TP auto-monitoring
- [x] Trailing stop
- [x] Conviction-based exit
- [ ] Start with 10% capital (gradual scale-up)
- [ ] Live degradation monitoring (weekly)
- [ ] Stop condition if degradation > 50%

### Continuous
- [x] AI Learning: dynamic weight re-optimization
- [x] Regime filter in decision engine
- [ ] Faster regime detection (weekly vs monthly)
- [ ] Quarterly re-validation
- [ ] Monthly performance review

---

## 10. Kesimpulan

### Apakah Aplikasi Sudah Mengatasi Backtest-to-Live Gap?

**Ya, sebagian besar.** Aplikasi memiliki 8 mekanisme anti-gap:

1. ✅ Next-bar-open execution (anti look-ahead)
2. ✅ Survivorship-free backtest (anti survivorship bias)
3. ✅ Walk-forward validation (anti overfitting)
4. ✅ Realistic cost model (anti unrealistic costs)
5. ✅ Regime filter (anti regime change)
6. ✅ Automated execution (anti behavioral gap)
7. ✅ Circuit breaker + daily loss limit (anti catastrophic loss)
8. ✅ Paper trading (pre-live validation)

**Tapi masih ada 6 gap yang perlu ditutup:**

1. ❌ Walk-forward belum mandatory
2. ❌ Paper-vs-backtest comparison belum ada
3. ❌ Slippage model terlalu optimis
4. ❌ Regime detection terlambat
5. ❌ Live degradation alert belum ada
6. ❌ Mandatory paper period belum enforced
7. ❌ **Deflated Sharpe Ratio belum dihitung** — tanpa DSR, walk-forward tidak cukup karena tidak mengontrol jumlah trial. Lihat `29-backtesting-strategy-validation.md` §16 untuk implementasi DSR.

### Pesan untuk User

> Backtest yang selalu untung adalah **red flag**, bukan green light. Aplikasi sudah punya mekanisme untuk mencegah backtest menipu (next-bar execution, survivorship-free, walk-forward, realistic costs, circuit breaker). Tapi **backtest-to-live gap tidak bisa dihilangkan 100%** — hanya bisa diminimalkan. Solusinya adalah **disiplin proses**: backtest → walk-forward → paper trading (30 hari) → live (small size) → scale up. Jika paper trading rugi, **JANGAN lanjut ke live**. Jika live performance degrad > 50% vs backtest, **STOP dan re-validate**.

## Referensi

1. `src/trading_system/backtest/engine.py` — Next-bar-open execution, survivorship-free backtest
2. `src/trading_system/backtest/metrics.py` — Walk-forward analysis, Monte Carlo
3. `src/trading_system/risk/costs.py` — Realistic cost model (fees, slippage, tax)
4. `src/trading_system/risk/circuit_breaker.py` — Circuit breaker & daily loss limit
5. `src/trading_system/paper_trading/engine.py` — Paper trading simulator
6. `src/trading_system/execution/automated.py` — Automated execution with risk checks
7. `src/trading_system/ai_learning/walk_forward.py` — Walk-forward validation
8. `pustaka/29-backtesting-strategy-validation.md` — Backtesting & validation
9. `pustaka/51-mlops-model-risk-management.md` — Model degradation & drift detection
10. Bailey & López de Prado (2014) — "The Deflated Sharpe Ratio"
11. Pardo, R. (2008) — *The Evaluation and Optimization of Trading Strategies*

---

> **Ingat:** "Jika backtest terlalu bagus untuk jadi kenyataan, kemungkinan besar memang begitu." (Doc 29, §Catatan)
