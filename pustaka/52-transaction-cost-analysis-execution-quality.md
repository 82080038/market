# Transaction Cost Analysis (TCA) & Execution Quality

> **Dokumen 52** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Mengukur kualitas eksekusi order — implementation shortfall, VWAP/TWAP benchmark, market impact modeling, slippage analysis per ticker per order size.
>
> **Konteks:** Dokumen 29 bahas backtesting dengan slippage assumption. Dokumen 40 bahas OMS/EMS architecture. Tapi belum ada doc yang membahas TCA: bagaimana mengukur apakah eksekusi order optimal, berapa slippage real, dan apakah broker memberikan best execution.

---

## Daftar Isi

1. [Kenapa TCA Penting](#1-kenapa-tca-penting)
2. [TCA Metrics](#2-tca-metrics)
3. [Benchmark Comparison](#3-benchmark-comparison)
4. [Market Impact Model](#4-market-impact-model)
5. [Slippage Analysis](#5-slippage-analysis)
6. [Best Execution Policy](#6-best-execution-policy)
7. [TCA Report Template](#7-tca-report-template)
8. [Implementation](#8-implementation)

---

## 1. Kenapa TCA Penting

### 1.1 Problem Statement

| Tanpa TCA | Dengan TCA |
|-----------|------------|
| User tidak tahu apakah order di-fill dengan harga optimal | User tahu slippage per order |
| Slippage diasumsikan fixed (0.1%) di backtest | Slippage real diukur per ticker per size |
| Tidak ada feedback ke decision engine | Slippage data → adjust entry/exit di recommendation |
| Tidak ada evaluasi broker quality | Broker comparison: mana yang lebih baik fill |
| Backtest tidak realistik | Backtest menggunakan TCA-adjusted returns |

### 1.2 TCA untuk IDX

IDX punya karakteristik unik yang memengaruhi TCA:
- **Auto-reject**: price move > 20% → trading halted → slippage extreme
- **Lot size**: 100 shares per lot → rounding impact untuk small capital
- **Tick size**: Rp 5 untuk harga < Rp 200, Rp 25 untuk harga > Rp 200
- **2 sesi**: Sesi 1 (09:00-11:30), Sesi 2 (14:00-15:50) → liquidity berbeda
- **Broker fee**: 0.15% + levy 0.025% + BEI fee

---

## 2. TCA Metrics

### 2.1 Core Metrics

| Metric | Definisi | Formula | Ideal |
|--------|----------|---------|-------|
| **Implementation Shortfall (IS)** | Selisih return teoritis vs return actual | IS = (decision_price - execution_price) / decision_price | < 0.5% |
| **Slippage** | Selisih harga order vs harga fill | slippage = (fill_price - order_price) / order_price | < 0.1% |
| **VWAP Slippage** | Selisih fill vs VWAP hari itu | vwap_slip = (fill_price - vwap) / vwap | < 0.2% |
| **Arrival Price Slippage** | Selisih fill vs harga saat order dibuat | arrival_slip = (fill_price - arrival_price) / arrival_price | < 0.15% |
| **Market Impact** | Harga movement akibat order kita | impact = (post_order_price - pre_order_price) / pre_order_price | < 0.05% |
| **Timing Cost** | Cost dari delay decision ke execution | timing = (execution_price - decision_price) / decision_price | < 0.3% |
| **Total Cost** | Semua cost: slippage + fee + impact | total = slippage + fee + impact | < 0.5% |

### 2.2 IDX-Specific Costs

```python
# execution/tca.py

def compute_total_cost(order):
    """
    Compute total execution cost untuk IDX order.
    """
    fill_price = order.fill_price
    decision_price = order.decision_price  # price saat recommendation dibuat
    arrival_price = order.arrival_price    # price saat order submitted
    vwap = get_vwap(order.ticker, order.date)

    # Slippage components
    slippage = (fill_price - arrival_price) / arrival_price
    vwap_slippage = (fill_price - vwap) / vwap
    timing_cost = (arrival_price - decision_price) / decision_price

    # Fees (IDX)
    broker_fee = 0.0015  # 0.15%
    levy_fee = 0.00025   # 0.025%
    bei_fee = 0.0001     # 0.01% (approximate)

    total_fees = broker_fee + levy_fee + bei_fee

    # Market impact (if order > 5% of daily volume)
    daily_volume = get_daily_volume(order.ticker, order.date)
    order_value = fill_price * order.shares
    volume_participation = order_value / (daily_volume * fill_price)

    if volume_participation > 0.05:
        market_impact = 0.001 * (volume_participation / 0.05)  # linear model
    else:
        market_impact = 0.0

    # Implementation shortfall
    is_pct = (decision_price - fill_price) / decision_price + total_fees

    return {
        "slippage_pct": slippage,
        "vwap_slippage_pct": vwap_slippage,
        "timing_cost_pct": timing_cost,
        "fees_pct": total_fees,
        "market_impact_pct": market_impact,
        "implementation_shortfall_pct": is_pct,
        "total_cost_pct": abs(slippage) + total_fees + market_impact,
        "volume_participation_pct": volume_participation,
        "fill_price": fill_price,
        "vwap": vwap,
        "arrival_price": arrival_price,
        "decision_price": decision_price
    }
```

---

## 3. Benchmark Comparison

### 3.1 Benchmark Types

| Benchmark | Kapan Dipakai | Kelebihan | Kekurangan |
|-----------|---------------|-----------|------------|
| **VWAP** | Intraday execution | Standard industri, fair | Tidak relevan untuk 1 trade |
| **TWAP** | Intraday, simple | Simple computation | Tidak capture volume pattern |
| **Arrival Price** | Best for measuring alpha | Mengukur total cost dari decision | Sensitive to timing |
| **Previous Close** | Daily execution | Simple, unambiguous | Tidak capture intraday |
| **Open Price** | Open auction | Relevant untuk market open | Tidak relevan untuk intraday |

### 3.2 VWAP Computation

```python
def compute_vwap(ticker, date, session=None):
    """
    Volume-Weighted Average Price untuk IDX.
    session: '1' (09:00-11:30), '2' (14:00-15:50), None (full day)
    """
    intraday = get_intraday_data(ticker, date)  # 1-min bars

    if session == "1":
        intraday = intraday[intraday.time.between("09:00", "11:30")]
    elif session == "2":
        intraday = intraday[intraday.time.between("14:00", "15:50")]

    vwap = (intraday.close * intraday.volume).sum() / intraday.volume.sum()
    return vwap
```

### 3.3 Benchmark Report

```
Order: BUY BBCA.JK 1000 shares @ 7850
Date: 2026-08-05

Benchmark Comparison:
┌─────────────────┬──────────┬───────────┬────────────┐
│ Benchmark       │ Price    │ Slippage  │ Status     │
├─────────────────┼──────────┼───────────┼────────────┤
│ Decision Price  │ 7820     │ +0.38%    │ Within IS  │
│ Arrival Price   │ 7845     │ +0.06%    │ Good       │
│ VWAP (full day) │ 7855     │ -0.06%    │ Good       │
│ TWAP (full day) │ 7858     │ -0.10%    │ Good       │
│ Previous Close  │ 7800     │ +0.64%    │ Acceptable │
│ Open Price      │ 7830     │ +0.26%    │ Good       │
└─────────────────┴──────────┴───────────┴────────────┘

Verdict: Execution quality GOOD. Fill below VWAP (positive alpha).
```

---

## 4. Market Impact Model

### 4.1 Square Root Model (Almgren-Chriss simplified)

```python
def estimate_market_impact(order_value, daily_volume, avg_daily_volatility):
    """
    Square root market impact model.
    Common for equity markets, adapted for IDX.

    impact = k * sigma * sqrt(eta)
    where:
      k = impact coefficient (~0.1 for IDX)
      sigma = daily volatility
      eta = order_value / daily_volume (participation rate)
    """
    k = 0.1  # IDX impact coefficient (calibrate with historical data)
    sigma = avg_daily_volatility  # e.g., 0.02 (2% daily)
    eta = order_value / (daily_volume * get_close_price(ticker))

    impact = k * sigma * np.sqrt(eta)
    return impact
```

### 4.2 Impact per Order Size (IDX)

| Order Size (% daily vol) | Est. Market Impact | Action |
|--------------------------|-------------------|--------|
| < 1% | < 0.02% | Safe, no impact |
| 1-5% | 0.02-0.05% | Minimal impact |
| 5-10% | 0.05-0.10% | Noticeable, consider splitting |
| 10-20% | 0.10-0.20% | Significant, split order |
| > 20% | > 0.20% | High impact, use TWAP/VWAP algo |

### 4.3 Liquidity Categories per Ticker

| Category | Avg Daily Volume | Max Order Size (no impact) | Example Tickers |
|----------|-----------------|---------------------------|-----------------|
| **Highly Liquid** | > Rp 100B | Rp 5B (5%) | BBCA.JK, BBRI.JK, TLKM.JK |
| **Liquid** | Rp 10B-100B | Rp 1B (5%) | ASII.JK, UNVR.JK, BMRI.JK |
| **Moderate** | Rp 1B-10B | Rp 100M (5%) | Most mid-cap |
| **Illiquid** | < Rp 1B | Rp 10M (5%) | Small-cap, infrequent trading |

---

## 5. Slippage Analysis

### 5.1 Slippage per Ticker

```python
def analyze_slippage_by_ticker(start_date, end_date):
    """
    Aggregate slippage statistics per ticker.
    """
    orders = get_orders(start_date, end_date)

    report = {}
    for ticker in orders.ticker.unique():
        ticker_orders = orders[orders.ticker == ticker]

        report[ticker] = {
            "order_count": len(ticker_orders),
            "avg_slippage_pct": ticker_orders.slippage.mean(),
            "median_slippage_pct": ticker_orders.slippage.median(),
            "p95_slippage_pct": ticker_orders.slippage.quantile(0.95),
            "avg_vwap_slippage": ticker_orders.vwap_slippage.mean(),
            "avg_total_cost": ticker_orders.total_cost.mean(),
            "worst_fill": ticker_orders.slippage.max(),
            "best_fill": ticker_orders.slippage.min(),
        }

    return report
```

### 5.2 Slippage Heatmap

| Ticker | Avg Slippage | P95 Slippage | VWAP Slip | Total Cost | Rating |
|--------|-------------|-------------|-----------|------------|--------|
| BBCA.JK | 0.05% | 0.12% | -0.03% | 0.23% | Excellent |
| TLKM.JK | 0.08% | 0.18% | 0.02% | 0.26% | Good |
| ASII.JK | 0.15% | 0.35% | 0.08% | 0.33% | Fair |
| UNVR.JK | 0.06% | 0.14% | -0.01% | 0.24% | Excellent |
| BMRI.JK | 0.10% | 0.22% | 0.04% | 0.28% | Good |

### 5.3 Slippage → Decision Engine Feedback

```python
def adjust_recommendation_for_tca(ticker, recommendation):
    """
    Adjust entry/exit levels berdasarkan historical TCA.
    """
    tca_stats = get_tca_stats(ticker, days=90)

    if tca_stats["avg_total_cost"] > 0.005:  # > 0.5%
        # Widen entry range to account for slippage
        recommendation.entry_low *= (1 - tca_stats["avg_slippage_pct"])
        recommendation.entry_high *= (1 + tca_stats["avg_slippage_pct"])

        # Tighten take-profit to account for exit slippage
        recommendation.take_profit *= (1 - tca_stats["avg_slippage_pct"])

    return recommendation
```

---

## 6. Best Execution Policy

### 6.1 Best Execution Obligation

> "Setiap order harus di-eksekusi dengan harga terbaik yang tersedia di market saat itu."

### 6.2 Best Execution Factors

| Factor | How to Measure | Weight |
|--------|---------------|--------|
| **Price** | Slippage vs arrival price | 40% |
| **Speed** | Time from order to fill | 20% |
| **Likelihood of execution** | Fill rate | 20% |
| **Settlement** | T+2 vs T+1 | 10% |
| **Fees** | Total fee % | 10% |

### 6.3 Best Execution Score

```python
def compute_best_execution_score(order):
    """
    Score 0-100, higher = better execution.
    """
    # Price score (40%): slippage < 0.1% = 100, > 0.5% = 0
    price_score = max(0, 100 - (abs(order.slippage_pct) * 1000)) * 0.40

    # Speed score (20%): < 5s = 100, > 60s = 0
    fill_time = (order.fill_time - order.submit_time).total_seconds()
    speed_score = max(0, 100 - (fill_time - 5) * 2) * 0.20

    # Execution likelihood (20%): filled = 100, partial = 50, rejected = 0
    if order.status == "FILLED":
        exec_score = 100 * 0.20
    elif order.status == "PARTIAL":
        exec_score = 50 * 0.20
    else:
        exec_score = 0

    # Settlement (10%): T+2 standard for IDX
    settlement_score = 100 * 0.10  # T+2 is standard

    # Fees (10%): 0.15% = 100, 0.30% = 0
    fee_score = max(0, 100 - (order.fees_pct - 0.0015) * 1000) * 0.10

    return price_score + speed_score + exec_score + settlement_score + fee_score
```

---

## 7. TCA Report Template

### 7.1 Daily TCA Report

```markdown
## TCA Daily Report — [Date]

### Summary
- Total orders: [N]
- Total value: Rp [X]
- Avg slippage: [X]%
- Avg total cost: [X]%
- Best execution score: [X]/100

### Orders Detail
| Ticker | Side | Shares | Fill | Arrival | VWAP | Slip | VWAP Slip | Cost | Score |
|--------|------|--------|------|---------|------|------|-----------|------|-------|
| BBCA.JK | BUY | 1000 | 7850 | 7845 | 7855 | 0.06% | -0.06% | 0.23% | 87 |
| TLKM.JK | SELL | 500 | 3500 | 3505 | 3498 | -0.14% | 0.06% | 0.19% | 91 |

### Flags
- [ ] Any order with slippage > 0.5%
- [ ] Any order with total cost > 0.8%
- [ ] Any order with best execution score < 60
- [ ] Any rejected/partial fill

### Action Items
- [ ] Investigate high slippage orders
- [ ] Adjust entry/exit for tickers with consistent high slippage
```

### 7.2 Monthly TCA Summary

```markdown
## TCA Monthly Summary — [Month]

### Aggregate Stats
| Metric | This Month | Last Month | Trend |
|--------|-----------|------------|-------|
| Avg slippage | 0.08% | 0.10% | ↓ improving |
| Avg VWAP slip | 0.02% | 0.03% | ↓ improving |
| Avg total cost | 0.25% | 0.28% | ↓ improving |
| Best exec score | 85 | 82 | ↑ improving |

### Per-Ticker Analysis
[Slippage heatmap table]

### Per-Broker Analysis (if multiple brokers)
| Broker | Orders | Avg Slippage | Avg Cost | Score |
|--------|--------|-------------|----------|-------|
| Sinarmas | 45 | 0.07% | 0.24% | 87 |
| BNI | 12 | 0.12% | 0.29% | 79 |

### Recommendations
- [ ] Consider switching broker for high-slippage tickers
- [ ] Split large orders for illiquid tickers
- [ ] Use limit orders instead of market orders for wide-spread tickers
```

---

## 8. Implementation

### 8.1 TCA Table Schema

```sql
CREATE TABLE tca_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,               -- 'BUY' or 'SELL'
    shares INTEGER NOT NULL,
    decision_price REAL,              -- price saat recommendation dibuat
    arrival_price REAL,               -- price saat order submitted
    fill_price REAL NOT NULL,
    fill_time TIMESTAMP NOT NULL,
    submit_time TIMESTAMP NOT NULL,
    vwap REAL,                        -- VWAP for that day
    slippage_pct REAL,
    vwap_slippage_pct REAL,
    timing_cost_pct REAL,
    fees_pct REAL,
    market_impact_pct REAL,
    implementation_shortfall_pct REAL,
    total_cost_pct REAL,
    best_execution_score REAL,
    volume_participation_pct REAL,
    broker TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 8.2 Integration dengan Existing System

| Integration Point | How |
|-------------------|-----|
| **T-030 (Decision Engine)** | `decision_price` = price saat recommendation dibuat |
| **T-041 (Auto Trade)** | `arrival_price` = price saat order submitted |
| **T-042 (Position Monitor)** | Fill data dari broker → TCA computation |
| **Backtest Engine** | Use historical TCA stats untuk realistic slippage |
| **XAI (T-032)** | Include TCA cost in narrative: "Est. total cost: 0.25%" |

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **29** (Backtesting) | TCA data → realistic backtest slippage |
| **40** (OMS/EMS) | OMS records order data untuk TCA |
| **47** (Operational Contract) | T-041 (Auto Trade) feeds TCA |
| **07** (Risk Management) | TCA cost → risk-adjusted returns |

---

## Referensi

1. `src/trading_system/risk/costs.py` — CostModel (broker fees, slippage, tax)
2. `src/trading_system/execution/engine.py` — ExecutionEngine (slippage estimation, fill simulation)
3. `src/trading_system/backtest/engine.py` — BacktestEngine (realistic cost integration)
4. `pustaka/24-market-microstructure-likuiditas.md` — Order book, spread, slippage modeling
5. `pustaka/29-backtesting-strategy-validation.md` — Transaction cost modeling in backtests
6. `pustaka/40-oms-ems-architecture.md` — OMS/EMS order data feeds TCA
7. Kissell, R. (2013) — *The Science of Algorithmic Trading and Portfolio Management* — Implementation shortfall
8. Almgren & Chriss (2000) — Optimal execution of portfolio transactions

---

## 10. Implementasi: CostModel Singleton

> **Sumber:** `src/trading_system/risk/costs.py` (202 baris)

Sistem `trading-system` mengimplementasikan single source of truth untuk ATR, broker fee, levy, dan slippage.

| 5W1H | Detail |
|------|--------|
| **What** | CostModel singleton: buy/sell fee, levy, slippage, ATR — satu instance untuk semua modul |
| **Why** | Tanpa singleton, tarif bisa inconsistent antar modul — backtest pakai fee berbeda dari execution = gap backtest-to-live |
| **When** | Setiap order calculation, backtest, dan risk assessment |
| **Where** | Risk layer: costs.py → execution engine, backtest engine, risk engine, enhanced risk |
| **Who** | Dipanggil oleh semua modul yang butuh fee/slippage/ATR |
| **How** | Singleton pattern via `get_default_cost_model()`, adaptive slippage 3-tier berdasarkan order size vs ADV |

### 10.1 CostModel Class

```python
class CostModel:
    buy_fee: float = 0.0015       # 0.15% beli
    sell_fee: float = 0.0025      # 0.15% broker + 0.1% PPh
    levy: float = 0.0000043       # 0.00043% levy bursa
    slippage: float = 0.0005      # 0.05% slippage default

    def buy_cost_pct(self) -> float:   # Total: fee + levy + slippage
    def sell_cost_pct(self) -> float:  # Total: fee + levy + slippage

    def compute_fees(self, order_value, action) -> dict:
        """Returns: brokerage, levy, tax, total"""

    def estimate_slippage(self, order_value, avg_daily_value) -> float:
        """3-tier: <0.1% ADV = base, <1% = 2x, >1% = 4x"""

    def simulate_fill(self, action, shares, last_price, avg_daily_value) -> dict:
        """Returns: fill_price, gross_value, fees, net_value, slippage_pct"""

    def check_feasibility(self, shares, price, cash, avg_daily_value) -> dict:
        """Returns: feasible, required_cash, available_cash, slippage_pct"""
```

### 10.2 Adaptive Slippage (3-Tier)

| Order Size vs ADV | Slippage Multiplier | Rationale |
|--------------------|---------------------|-----------|
| < 0.1% ADV | 1x (0.05%) | Negligible market impact |
| 0.1% - 1% ADV | 2x (0.10%) | Moderate impact |
| > 1% ADV | 4x (0.20%) | Significant impact, warn user |

### 10.3 ATR Consolidation

`compute_atr()` dan `get_latest_atr()` dipindahkan ke `costs.py` sebagai single source — digunakan oleh risk engine, execution engine, backtest engine, dan enhanced risk.

### 10.4 Singleton Pattern

```python
_default_cost_model = CostModel()

def get_default_cost_model() -> CostModel:
    return _default_cost_model
```

Semua modul menggunakan instance yang sama → perubahan tarif hanya di satu tempat.

---

> **Catatan:** TCA bukan luxury — adalah necessity untuk trading real. "Profit yang tidak diukur adalah profit yang tidak ada." Setiap basis point slippage yang dihemat = profit yang di-amankan. Implementasi: `src/trading_system/risk/costs.py`.
