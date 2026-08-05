# Market Microstructure & Likuiditas

> **Tujuan:** Dokumen ini adalah referensi definitif untuk market microstructure — order book dynamics, bid-ask spread, price discovery, slippage modeling, dan likuiditas analysis — dengan fokus pada pasar modal Indonesia (IDX).

---

## Daftar Isi

1. [Konsep Market Microstructure](#1-konsep-market-microstructure)
2. [Order Book (Limit Order Book)](#2-order-book-limit-order-book)
3. [Bid-Ask Spread](#3-bid-ask-spread)
4. [Price Discovery](#4-price-discovery)
5. [Slippage Modeling](#5-slippage-modeling)
6. [Likuiditas Analysis](#6-likuiditas-analysis)
7. [Market Impact](#7-market-impact)
8. [IDX Microstructure Specifics](#8-idx-microstructure-specifics)
9. [Implementasi untuk Trading System](#9-implementasi-untuk-trading-system)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Konsep Market Microstructure

### 1.1 Definisi

Market microstructure adalah studi tentang proses dan mekanisme yang menentukan harga aset dalam pasar perdagangan. Fokus pada:

- **Bagaimana order diterima, diproses, dan di-match**
- **Bagaimana informasi terdifusi ke harga**
- **Bagaimana likuiditas mempengaruhi biaya transaksi**
- **Bagaimana struktur bursa mempengaruhi perilaku pasar**

### 1.2 Komponen Utama

```
┌─────────────────────────────────────────────────────────┐
│                  MARKET MICROSTRUCTURE                   │
├──────────────┬──────────────┬──────────────────────────┤
│  Order Flow  │  Order Book  │   Price Discovery        │
│  - Buy/Sell  │  - Bids      │   - Spread               │
│  - Size      │  - Asks      │   - Depth                │
│  - Type      │  - Volume    │   - Resiliency           │
│              │  - Priority  │   - Information          │
├──────────────┼──────────────┼──────────────────────────┤
│  Likuiditas  │  Market Impact│  Transaction Costs      │
│  - Tightness │  - Price move│   - Commission           │
│  - Depth     │  - Slippage  │   - Spread cost          │
│  - Resiliency│  - Permanent │   - Slippage             │
│              │  - Temporary │   - Opportunity cost     │
└──────────────┴──────────────┴──────────────────────────┘
```

### 1.3 Jenis Pasar

| Tipe | Deskripsi | Contoh | IDX Status |
|------|-----------|--------|------------|
| **Order-Driven** | Order matched by computer | BEI (JATS-NextG) | ✅ Primary |
| **Quote-Driven** | Market maker provides quotes | Nasdaq | ❌ |
| **Hybrid** | Order + market maker | NYSE | ❌ |
| **Dark Pool** | Anonymous, no public order book | ITG/Posit | ❌ |

---

## 2. Order Book (Limit Order Book)

### 2.1 Struktur Order Book

```
┌─────────────────────────────────────────┐
│           ORDER BOOK (BBCA.JK)          │
├──────────────┬──────────┬───────────────┤
│    BIDS      │  PRICE   │     ASKS      │
│  (Buy Orders)│          │  (Sell Orders)│
├──────────────┼──────────┼───────────────┤
│              │  8,050   │    200        │
│         500  │  8,025   │    150        │
│       1,000  │  8,000   │    100  ← Best Ask
│       2,000  │  7,975   │              │  ← Best Bid
│       1,500  │  7,950   │              │
│         800  │  7,925   │              │
├──────────────┼──────────┼───────────────┤
│  Total: 5,800│  Spread  │  Total: 450   │
│              │  = 25    │               │
└──────────────┴──────────┴───────────────┘
```

### 2.2 Order Priority

| Priority | Deskripsi | IDX Implementation |
|----------|-----------|-------------------|
| **Price** | Better price first | Best bid/ask matched first |
| **Time** | Same price → FIFO | Earlier order matched first |
| **Pro-Rata** | Same price → proportional | Not used in IDX |

### 2.3 Order Book Reconstruction

```python
class OrderBook:
    """Simplified order book representation."""
    
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.bids = []  # [(price, volume), ...] descending
        self.asks = []  # [(price, volume), ...] ascending
    
    def update(self, side: str, price: float, volume: int):
        """Update order book with new/modified order."""
        book = self.bids if side == "buy" else self.asks
        
        if volume == 0:
            # Remove order
            book = [(p, v) for p, v in book if p != price]
        else:
            # Add or update
            book = [(p, v) for p, v in book if p != price]
            book.append((price, volume))
        
        # Sort
        if side == "buy":
            self.bids = sorted(book, key=lambda x: -x[0])
        else:
            self.asks = sorted(book, key=lambda x: x[0])
    
    @property
    def best_bid(self):
        return self.bids[0] if self.bids else (0, 0)
    
    @property
    def best_ask(self):
        return self.asks[0] if self.asks else (float('inf'), 0)
    
    @property
    def spread(self):
        return self.best_ask[0] - self.best_bid[0]
    
    @property
    def mid_price(self):
        return (self.best_bid[0] + self.best_ask[0]) / 2
    
    def depth(self, levels=5):
        """Get top N levels."""
        return {
            "bids": self.bids[:levels],
            "asks": self.asks[:levels],
        }
```

### 2.4 Order Book Imbalance

```python
def order_book_imbalance(bids: list, asks: list, levels: int = 5) -> float:
    """Compute order book imbalance (-1 to +1).
    
    +1 = all bids (strong buy pressure)
    -1 = all asks (strong sell pressure)
    """
    bid_volume = sum(v for _, v in bids[:levels])
    ask_volume = sum(v for _, v in asks[:levels])
    total = bid_volume + ask_volume
    
    if total == 0:
        return 0.0
    
    return (bid_volume - ask_volume) / total
```

---

## 3. Bid-Ask Spread

### 3.1 Komponen Spread

| Komponen | Deskripsi | Faktor |
|----------|-----------|--------|
| **Order processing cost** | Biaya bursa + kliring + KSEI | Fixed per trade |
| **Inventory cost** | Risk borne by market maker | Volatility, holding period |
| **Adverse selection** | Information asymmetry | News, informed traders |

### 3.2 Spread Measurement

```python
def compute_spread_metrics(df: pd.DataFrame) -> dict:
    """Compute spread metrics from OHLCV data.
    
    Note: Without Level 2 data, we estimate spread from high-low.
    """
    # Corwin-Schultz spread estimator
    high_low = np.log(df["high"] / df["low"])
    
    # Daily spread estimate
    cs_spread = 2 * (np.exp(-np.sqrt(2) * np.sqrt(np.log(high_low.rolling(2).sum() / np.log(high_low.rolling(2).apply(lambda x: x[0]**2 + x[1]**2))))) - 1)
    
    # Roll's spread estimator (from serial covariance of returns)
    returns = df["close"].pct_change()
    roll_spread = 2 * np.sqrt(-returns.rolling(20).cov(returns.shift(1)).clip(upper=0))
    
    return {
        "corwin_schultz_spread": float(cs_spread.mean()),
        "roll_spread": float(roll_spread.mean()),
        "avg_high_low_range": float((df["high"] - df["low"]).mean() / df["close"].mean()),
    }
```

### 3.3 Spread untuk IDX

| Saham | Typical Spread | Likuiditas | Notes |
|-------|---------------|------------|-------|
| BBCA.JK | 5-25 pts | Sangat likuid | Blue chip |
| TLKM.JK | 5-20 pts | Likuid | Blue chip |
| UNVR.JK | 10-50 pts | Likuid | Blue chip |
| Mid-cap | 10-100 pts | Sedang | Spread lebar |
| Small-cap | 50-500 pts | Illiquid | Spread sangat lebar |
| Gorengan | 100-1000+ pts | Sangat illiquid | Extreme spread |

---

## 4. Price Discovery

### 4.1 Konsep

Price discovery adalah proses dimana pasar menentukan harga equilibrium melalui interaksi buy dan sell orders.

### 4.2 Faktor yang Mempengaruhi

| Faktor | Deskripsi | Measurement |
|--------|-----------|-------------|
| **Order flow** | Buy vs sell pressure | Order imbalance |
| **Information** | News, announcements | Event study |
| **Liquidity** | Depth, resiliency | Volume, spread |
| **Volatility** | Price uncertainty | ATR, realized vol |
| **Market structure** | Trading rules, mechanisms | Auto-reject, circuit breaker |

### 4.3 Price Efficiency

```python
def price_efficiency(df: pd.DataFrame) -> dict:
    """Measure price efficiency metrics."""
    returns = df["close"].pct_change().dropna()
    
    # Variance ratio (Lo-MacKinlay)
    # VR(q) = Var(q-period return) / (q * Var(1-period return))
    # VR = 1 → random walk (efficient)
    # VR > 1 → momentum
    # VR < 1 → mean reversion
    
    var_1 = returns.var()
    results = {}
    
    for q in [5, 10, 20]:
        var_q = returns.rolling(q).sum().var()
        vr = var_q / (q * var_1) if var_1 > 0 else 0
        results[f"variance_ratio_{q}"] = vr
    
    # Autocorrelation
    results["autocorr_1"] = returns.autocorr(lag=1)
    results["autocorr_5"] = returns.autocorr(lag=5)
    
    return results
```

---

## 5. Slippage Modeling

### 5.1 Definisi

Slippage = selisih antara harga ekspektasi dan harga eksekusi aktual.

```
Slippage = Execution Price - Expected Price
Expected Price = Mid price (or VWAP or arrival price)
```

### 5.2 Tipe Slippage

| Tipe | Penyebab | Magnitude |
|------|----------|-----------|
| **Market slippage** | Market order melawan order book | Spread + depth |
| **Impact slippage** | Order besar menggerakkan harga | Proportional to sqrt(order size) |
| **Timing slippage** | Delay antara signal dan execution | Volatility × time |
| **Latency slippage** | Network/processing delay | Microseconds (HFT) |

### 5.3 Slippage Model

```python
def estimate_slippage(
    order_size: int,
    avg_daily_volume: int,
    spread_bps: float,
    volatility: float,
    participation_rate: float = 0.01,
) -> dict:
    """Estimate slippage for a given order.
    
    Uses square-root impact model:
    Impact = σ × sqrt(order_size / ADV) × coefficient
    """
    # Market impact (square-root model)
    impact_coeff = 0.142  # empirical coefficient (Almgren et al.)
    volume_ratio = order_size / avg_daily_volume
    permanent_impact = impact_coeff * volatility * np.sqrt(volume_ratio)
    
    # Temporary impact (spread + market impact)
    temporary_impact = spread_bps / 10000 + 0.5 * permanent_impact
    
    # Total slippage
    total_slippage = permanent_impact + temporary_impact
    
    return {
        "permanent_impact_bps": permanent_impact * 10000,
        "temporary_impact_bps": temporary_impact * 10000,
        "total_slippage_bps": total_slippage * 10000,
        "volume_ratio": volume_ratio,
        "participation_rate": participation_rate,
    }
```

### 5.4 IDX Slippage Estimation

```python
def idx_slippage_model(
    ticker: str,
    order_value_idr: float,
    avg_daily_value_idr: float,
    spread_pct: float = 0.001,  # 0.1% default
    volatility: float = 0.02,   # 2% daily vol
) -> float:
    """IDX-specific slippage model.
    
    IDX characteristics:
    - Wider spreads than developed markets
    - Lower liquidity for most stocks
    - Auto-reject limits price movement
    - Lot-based trading (100 shares)
    """
    # Participation rate
    participation = order_value_idr / avg_daily_value_idr
    
    # Square-root impact (higher coefficient for IDX)
    impact_coeff = 0.25  # higher than developed markets
    impact = impact_coeff * volatility * np.sqrt(participation)
    
    # Spread cost
    spread_cost = spread_pct / 2  # half spread
    
    # Total slippage
    total = impact + spread_cost
    
    # Cap at auto-reject limit (15-20%)
    total = min(total, 0.15)
    
    return total
```

### 5.5 Execution Cost Model

```python
class ExecutionCostModel:
    """Total execution cost model for IDX."""
    
    def __init__(self):
        self.buy_fee = 0.0015       # 0.15% broker commission
        self.sell_fee = 0.0025      # 0.25% broker commission
        self.levy = 0.00004         # BEI levy
        self.pph = 0.001            # 0.1% PPh final (sell only)
    
    def total_buy_cost(self, value: float) -> dict:
        fee = value * (self.buy_fee + self.levy)
        return {"fee": fee, "fee_pct": (self.buy_fee + self.levy) * 100}
    
    def total_sell_cost(self, value: float) -> dict:
        fee = value * (self.sell_fee + self.levy + self.pph)
        return {"fee": fee, "fee_pct": (self.sell_fee + self.levy + self.pph) * 100}
    
    def round_trip_cost(self, value: float) -> dict:
        buy = self.total_buy_cost(value)
        sell = self.total_sell_cost(value)
        slippage = value * 0.002  # estimated 0.2% slippage
        total = buy["fee"] + sell["fee"] + slippage
        return {
            "buy_fee": buy["fee"],
            "sell_fee": sell["fee"],
            "slippage": slippage,
            "total_cost": total,
            "total_pct": total / value * 100,
        }
```

---

## 6. Likuiditas Analysis

### 6.1 Dimensi Likuiditas

| Dimensi | Deskripsi | Measurement | Target |
|---------|-----------|-------------|--------|
| **Tightness** | Spread sempit | Bid-ask spread | < 0.2% |
| **Depth** | Volume di order book | Volume at best bid/ask | > 10 lots |
| **Resiliency** | Pulih setelah trade besar | Time to refill spread | < 1 minute |
| **Immediacy** | Speed of execution | Time to fill market order | < 1 second |
| **Breadth** | Width of order book | Volume across price levels | Deep book |

### 6.2 Likuiditas Metrics

```python
def liquidity_metrics(df: pd.DataFrame, ticker: str) -> dict:
    """Compute liquidity metrics from OHLCV data."""
    avg_volume = df["volume"].rolling(20).mean().iloc[-1]
    avg_value = (df["close"] * df["volume"]).rolling(20).mean().iloc[-1]
    
    # Amihud illiquidity ratio
    returns = df["close"].pct_change()
    dollar_volume = df["close"] * df["volume"]
    amihud = (returns.abs() / dollar_volume).rolling(20).mean().iloc[-1]
    
    # Turnover ratio
    shares_outstanding = get_shares_outstanding(ticker)
    turnover = avg_volume / shares_outstanding if shares_outstanding > 0 else 0
    
    # Zero return days (illiquidity proxy)
    zero_days = (returns == 0).rolling(20).sum().iloc[-1]
    
    # High-low range (volatility proxy)
    hl_range = ((df["high"] - df["low"]) / df["close"]).rolling(20).mean().iloc[-1]
    
    return {
        "avg_daily_volume": int(avg_volume),
        "avg_daily_value_idr": float(avg_value),
        "amihud_illiquidity": float(amihud * 1e10),  # scaled
        "turnover_ratio": float(turnover),
        "zero_return_days_20d": int(zero_days),
        "avg_hl_range_pct": float(hl_range * 100),
        "liquidity_score": _compute_liquidity_score(avg_volume, amihud, zero_days),
    }

def _compute_liquidity_score(volume, amihud, zero_days):
    """Score 0-100, higher = more liquid."""
    score = 50  # baseline
    if volume > 1_000_000: score += 20
    elif volume > 100_000: score += 10
    elif volume < 10_000: score -= 20
    
    if amihud < 0.01: score += 15
    elif amihud > 0.1: score -= 15
    
    if zero_days < 2: score += 15
    elif zero_days > 10: score -= 15
    
    return max(0, min(100, score))
```

### 6.3 Likuiditas Classification untuk IDX

| Tier | Avg Daily Volume | Avg Daily Value | Spread | Examples |
|------|-----------------|-----------------|--------|----------|
| **Tier 1 (Very Liquid)** | > 5M shares | > Rp 50B | < 0.1% | BBCA, BBRI, TLKM, ASII |
| **Tier 2 (Liquid)** | 1-5M shares | Rp 10-50B | 0.1-0.3% | UNVR, BMRI, GOTO, ICBP |
| **Tier 3 (Moderate)** | 100K-1M shares | Rp 1-10B | 0.3-1% | Mid-cap stocks |
| **Tier 4 (Illiquid)** | < 100K shares | < Rp 1B | > 1% | Small-cap stocks |
| **Tier 5 (Very Illiquid)** | < 10K shares | < Rp 100M | > 5% | Micro-cap, gorengan |

---

## 7. Market Impact

### 7.1 Square-Root Model

```
Impact = σ × η × √(Q/V)
```

Dimana:
- `σ` = volatility
- `η` = impact coefficient (~0.1-0.3)
- `Q` = order size
- `V` = average daily volume

### 7.2 Almgren-Chriss Model

```python
def almgren_chriss_impact(
    order_size: float,
    adv: float,
    volatility: float,
    eta: float = 0.142,
    beta: float = 0.6,
):
    """Almgren-Chriss market impact model."""
    # Permanent impact
    permanent = eta * volatility * (order_size / adv) ** beta
    
    # Temporary impact (depends on execution speed)
    # For immediate execution:
    temporary = eta * volatility * np.sqrt(order_size / adv)
    
    return {
        "permanent_impact": permanent,
        "temporary_impact": temporary,
        "total_impact": permanent + temporary,
    }
```

### 7.3 Participation Rate Constraint

```python
def max_order_size(adv: float, max_participation: float = 0.05) -> float:
    """Maximum order size as % of average daily volume."""
    return adv * max_participation

# Rule of thumb: never trade more than 5% of daily volume
# For IDX: even more conservative (2-3%) due to lower liquidity
```

---

## 8. IDX Microstructure Specifics

### 8.1 Trading Mechanism

| Feature | IDX Rule | Impact |
|---------|----------|--------|
| **Order-driven** | JATS-NextG matching engine | No market maker |
| **Lot size** | 100 shares | Minimum trade unit |
| **Tick size** | Dynamic (price-based) | Discrete pricing |
| **Auto-reject** | ±15% (regular), ±20% (IPO) | Price limit |
| **Circuit breaker** | IHSG -5% → 30 min halt | Market-wide halt |
| **Short selling** | Regulated, limited stocks | Only specific stocks |
| **Settlement** | T+2 | KSEI settlement |
| **Trading hours** | 09:00-15:50 WIB | No pre/post market |

### 8.2 IDX Tick Size Schedule

| Price Range | Tick Size |
|-------------|----------|
| < Rp 200 | Rp 1 |
| Rp 200 - 500 | Rp 2 |
| Rp 500 - 2,000 | Rp 5 |
| Rp 2,000 - 5,000 | Rp 10 |
| > Rp 5,000 | Rp 25 |

```python
def idx_tick_size(price: float) -> float:
    """Get IDX tick size for a given price."""
    if price < 200:
        return 1
    elif price < 500:
        return 2
    elif price < 2000:
        return 5
    elif price < 5000:
        return 10
    else:
        return 25

def round_to_tick(price: float, tick: float = None) -> float:
    """Round price to nearest tick."""
    if tick is None:
        tick = idx_tick_size(price)
    return round(price / tick) * tick
```

### 8.3 Auto-Reject Mechanism

```python
def compute_auto_reject_range(ref_price: float, limit: float = 0.15):
    """Compute IDX auto-reject price range."""
    lower = ref_price * (1 - limit)
    upper = ref_price * (1 + limit)
    
    # Round to tick
    lower = round_to_tick(lower)
    upper = round_to_tick(upper)
    
    return {"lower": lower, "upper": upper, "ref_price": ref_price}
```

### 8.4 IDX-Specific Risk Flags

```python
def idx_risk_flags(ticker: str, df: pd.DataFrame) -> list:
    """IDX-specific microstructure risk flags."""
    flags = []
    
    # Low liquidity
    avg_vol = df["volume"].rolling(20).mean().iloc[-1]
    if avg_vol < 100_000:
        flags.append("LOW_LIQUIDITY")
    
    # Wide spread (estimated from high-low)
    hl_pct = ((df["high"] - df["low"]) / df["close"]).rolling(20).mean().iloc[-1]
    if hl_pct > 0.03:  # > 3% daily range
        flags.append("WIDE_SPREAD")
    
    # Zero volume days
    zero_days = (df["volume"] == 0).rolling(20).sum().iloc[-1]
    if zero_days > 3:
        flags.append("FREQUENT_NO_TRADE")
    
    # Auto-reject hit
    daily_return = df["close"].pct_change()
    reject_days = (daily_return.abs() > 0.14).rolling(20).sum().iloc[-1]
    if reject_days > 2:
        flags.append("FREQUENT_AUTO_REJECT")
    
    return flags
```

---

## 9. Implementasi untuk Trading System

### 9.1 Slippage-Aware Position Sizing

```python
def slippage_aware_position_size(
    capital: float,
    risk_per_trade: float,
    price: float,
    adv: float,
    volatility: float,
    max_participation: float = 0.03,
) -> int:
    """Position size considering slippage and liquidity constraints."""
    # Risk-based size
    risk_amount = capital * risk_per_trade
    stop_distance = 1.5 * volatility * price  # ATR-based
    risk_based_qty = risk_amount / stop_distance
    
    # Liquidity-based cap
    max_qty = adv * max_participation
    
    # Capital-based cap (10% of capital)
    capital_cap = (capital * 0.10) / price
    
    # Take minimum
    qty = min(risk_based_qty, max_qty, capital_cap)
    
    # Round to IDX lot
    qty = max(100, int(qty // 100) * 100)
    
    return qty
```

### 9.2 Execution Algorithm Selection

```python
def select_execution_algorithm(
    order_size: int,
    adv: int,
    urgency: str = "normal",
) -> str:
    """Select execution algorithm based on order characteristics."""
    participation = order_size / adv
    
    if participation < 0.01:
        return "market_order"  # Small order, execute immediately
    elif participation < 0.05:
        return "twap"  # Medium order, time-weighted
    elif participation < 0.10:
        return "vwap"  # Large order, volume-weighted
    else:
        return "implementation_shortfall"  # Very large, minimize total cost
```

### 9.3 TWAP/VWAP Execution (Simplified)

```python
def twap_schedule(total_qty: int, duration_minutes: int, slices: int = 10):
    """Time-Weighted Average Price execution schedule."""
    qty_per_slice = total_qty // slices
    interval = duration_minutes // slices
    
    schedule = []
    for i in range(slices):
        schedule.append({
            "slice": i + 1,
            "quantity": qty_per_slice,
            "time_offset_min": i * interval,
        })
    
    # Remainder
    remainder = total_qty - qty_per_slice * slices
    if remainder > 0:
        schedule[-1]["quantity"] += remainder
    
    return schedule

def vwap_schedule(total_qty: int, volume_profile: list):
    """Volume-Weighted Average Price execution schedule."""
    total_profile = sum(volume_profile)
    
    schedule = []
    for i, vol in enumerate(volume_profile):
        qty = int(total_qty * vol / total_profile)
        qty = max(100, qty // 100 * 100)  # round to lot
        schedule.append({
            "slice": i + 1,
            "quantity": qty,
            "volume_weight": vol / total_profile,
        })
    
    return schedule
```

---

## 10. Checklist Implementasi

### Order Book
- [ ] Order book data structure (bids/asks sorted)
- [ ] Order book imbalance computation
- [ ] Depth analysis (top 5 levels)
- [ ] Spread monitoring (real-time)

### Slippage
- [ ] Square-root impact model
- [ ] IDX-specific slippage calibration
- [ ] Slippage-aware position sizing
- [ ] Execution cost model (fees + spread + impact)

### Likuiditas
- [ ] Liquidity metrics (Amihud, turnover, zero days)
- [ ] Liquidity classification (Tier 1-5)
- [ ] Liquidity filter for tradeable universe
- [ ] Liquidity risk flags

### IDX Specifics
- [ ] Tick size rounding
- [ ] Auto-reject range computation
- [ ] Lot size (100 shares) rounding
- [ ] Market hours check (09:00-15:50 WIB)
- [ ] Circuit breaker detection (IHSG -5%)

### Execution
- [ ] Execution algorithm selection (market/TWAP/VWAP)
- [ ] Participation rate limit (≤ 3% ADV)
- [ ] Execution schedule generation
- [ ] Post-trade slippage analysis

### Integration
- [ ] Slippage in backtesting engine
- [ ] Liquidity filter in stock screener
- [ ] Risk flags in Decision Engine
- [ ] Execution cost in portfolio rebalancing

---

## Referensi

1. O'Hara, M. (1995). "Market Microstructure Theory"
2. Almgren, R. & Chriss, N. (2000). "Optimal Execution of Portfolio Transactions"
3. Corwin, D. & Schultz, P. (2012). "A Simple Way to Estimate Bid-Ask Spreads from Daily High and Low Prices"
4. Roll, R. (1984). "A Simple Implicit Measure of the Effective Bid-Ask Spread"
5. Amihud, Y. (2002). "Illiquidity and Stock Returns"
6. BEI — Peraturan I-B (Perdagangan Efek)
7. `src/trading_system/execution/costs.py` — Cost model
8. `src/trading_system/risk/engine.py` — Risk engine (liquidity check)
9. `src/trading_system/analysis/advanced_technical.py` — Advanced technical analysis
10. `pustaka/08-trading-algoritmik.md` — Trading algoritmik

---

## 12. Implementasi: Order Book Analyzer

> **Sumber:** `src/trading_system/analysis/order_book.py` (381 baris)

Sistem `trading-system` mengimplementasikan analisis gap dan support/resistance dari data OHLCV — pure pandas/numpy, tanpa dependency eksternal.

| 5W1H | Detail |
|------|--------|
| **What** | Order Book Analyzer: price gap, volume gap, S/R detection, gap fill prediction |
| **Why** | Gap dan S/R levels adalah microstructure signal penting untuk entry/exit timing di IDX |
| **When** | Pre-trade analysis, backtest, dan screening |
| **Where** | Analysis layer, dapat dipanggil oleh screener dan XAI |
| **Who** | Dipanggil oleh screener.py dan advanced_context.py (XAI) |
| **How** | Detect gaps > 2% antar candle, volume change > 50%, S/R tested ≥ 3x dengan 1% tolerance |

### 12.1 Fitur

| Fitur | Deskripsi | Parameter |
|-------|-----------|-----------|
| **Price gap detection** | Deteksi gap antar candle > threshold | `gap_threshold = 0.02` (2%) |
| **Volume gap detection** | Deteksi perubahan volume > threshold | `volume_threshold = 0.5` (50%) |
| **Support/Resistance** | Level yang diuji ≥ 3x dengan toleransi 1% | `test_count ≥ 3`, `tolerance = 1%` |
| **Gap strength scoring** | Ukur kekuatan gap berdasarkan rasio | `gap_ratio` |
| **Gap fill prediction** | Prediksi gap fill menuju equilibrium | Berdasarkan historical fill rate |

### 12.2 Output

```python
class OrderBookAnalyzer:
    def detect_price_gaps(self, data: pd.DataFrame) -> list[dict]:
        """Returns list of gaps with direction (UP/DOWN) and strength."""

    def detect_volume_gaps(self, data: pd.DataFrame) -> list[dict]:
        """Returns list of volume anomalies (INCREASE/DECREASE)."""

    def identify_support_resistance(self, data: pd.DataFrame) -> list[dict]:
        """Returns S/R levels with test count and strength."""
```

### 12.3 Use Case

- **Pre-trade:** Cek apakah harga dekat support/resistance kuat
- **Risk management:** Gap risk → adjust stop loss placement
- **Pattern discovery:** Gap fill prediction sebagai trading signal
- **Liquidity analysis:** Volume gap → deteksi perubahan minat investor

---

> **Catatan:** Microstructure understanding adalah competitive advantage. Trader yang memahami likuiditas, spread, dan impact akan menghindari biaya tersembunyi yang menggerus return. Implementasi: `src/trading_system/analysis/order_book.py`.
