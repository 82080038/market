# Post-Trade, Settlement & Rekonsiliasi

> **Tujuan:** Dokumen ini adalah referensi definitif untuk post-trade processing — trade capture, clearing & settlement, reconciliation, corporate action processing, NAV calculation, dan performance attribution — dengan fokus pada pasar modal Indonesia (IDX).

---

## Daftar Isi

1. [Trade Lifecycle](#1-trade-lifecycle)
2. [Trade Capture & Enrichment](#2-trade-capture--enrichment)
3. [Clearing & Settlement (IDX)](#3-clearing--settlement-idx)
4. [Reconciliation](#4-reconciliation)
5. [Corporate Action Processing](#5-corporate-action-processing)
6. [NAV Calculation](#6-nav-calculation)
7. [Performance Attribution](#7-performance-attribution)
8. [Position Management](#8-position-management)
9. [Implementasi Sistem](#9-implementasi-sistem)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Trade Lifecycle

### 1.1 Tahapan Trade Lifecycle

```
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ Pre-Trade│──▶│ Execution│──▶│  Trade   │──▶│ Clearing │──▶│Settlement│
│ Decision │   │ (OMS/EMS)│   │ Capture  │   │ (KPEI)   │   │ (KSEI)   │
└─────────┘   └─────────┘   └────┬────┘   └────┬────┘   └────┬────┘
                                  │              │              │
                                  ▼              ▼              ▼
                            ┌─────────┐   ┌─────────┐   ┌─────────┐
                            │Enrichment│  │ Netting  │  │ Custody  │
                            │& Validate│  │& Margin  │  │& Book    │
                            └─────────┘   └─────────┘   └─────────┘
                                                                │
                                                                ▼
                                                          ┌─────────┐
                                                          │ Post-   │
                                                          │ Settlement│
                                                          │ (Recon, │
                                                          │ NAV, Attr)│
                                                          └─────────┘
```

### 1.2 IDX Trade Lifecycle

| Stage | IDX Entity | Timeline | Description |
|-------|-----------|----------|-------------|
| **Order submission** | Broker → JATS | Real-time | Order routed to exchange |
| **Matching** | BEI (JATS-NextG) | Real-time | Price-time priority matching |
| **Trade confirmation** | Broker → Investor | T+0 | Trade confirmation sent |
| **Clearing** | KPEI | T+0 to T+1 | Netting, margin calculation |
| **Settlement** | KSEI | T+2 | Securities + cash settlement |
| **Reconciliation** | Broker/Custodian | T+2+ | Position reconciliation |
| **Reporting** | Broker → Investor | T+5 | Trade report + bukti potong |

---

## 2. Trade Capture & Enrichment

### 2.1 Trade Capture

```python
class TradeCapture:
    """Capture and enrich trade execution data."""
    
    def capture_trade(self, execution: dict) -> dict:
        """Capture a trade execution with full enrichment."""
        trade = {
            # Core fields
            "trade_id": execution["order_id"],
            "ticker": execution["ticker"],
            "side": execution["order_type"],  # BUY or SELL
            "quantity": execution["quantity"],
            "price": execution["price"],
            "value": execution["quantity"] * execution["price"],
            
            # Timestamps
            "execution_time": execution["created_at"],
            "settlement_date": self._compute_settlement_date(execution["created_at"]),
            
            # Costs
            "broker_fee": execution.get("fee", 0),
            "levy": execution["value"] * 0.00004,
            "pph_final": execution["value"] * 0.001 if execution["order_type"] == "SELL" else 0,
            "total_cost": 0,  # computed below
            
            # PnL (for sells)
            "realized_pnl": execution.get("realized_pnl", 0),
            "cost_basis": 0,  # computed from FIFO/avg
            
            # Metadata
            "trigger": execution.get("trigger", "SIGNAL"),
            "strategy": execution.get("strategy", "default"),
            "broker": execution.get("broker", "default"),
        }
        
        trade["total_cost"] = trade["broker_fee"] + trade["levy"] + trade["pph_final"]
        
        return trade
    
    def _compute_settlement_date(self, trade_date: str, days: int = 2) -> str:
        """Compute T+2 settlement date (skipping weekends/holidays)."""
        from datetime import datetime, timedelta
        
        dt = datetime.fromisoformat(trade_date)
        settlement = dt
        
        added = 0
        while added < days:
            settlement += timedelta(days=1)
            if settlement.weekday() < 5 and not self._is_holiday(settlement):
                added += 1
        
        return settlement.isoformat()
    
    def _is_holiday(self, dt) -> bool:
        """Check if date is a market holiday."""
        # Query market_calendar table
        return False  # placeholder
```

### 2.2 Trade Enrichment

| Field | Source | Purpose |
|-------|--------|---------|
| `settlement_date` | Computed (T+2) | Cash flow planning |
| `cost_basis` | FIFO/avg from buy lots | Realized PnL |
| `realized_pnl` | Sell proceeds - cost basis | Tax & performance |
| `sector` | Instrument master | Attribution |
| `market_cap_tier` | Instrument master | Liquidity classification |
| `fx_rate` | BI rate (if foreign) | Currency normalization |

---

## 3. Clearing & Settlement (IDX)

### 3.1 KPEI (Kliring Penjaminan Efek Indonesia)

| Function | Description |
|----------|-------------|
| **Netting** | Net buy/sell obligations per broker per security |
| **Margin** | Initial margin + variation margin calculation |
| **Guarantee** | KPEI becomes counterparty (novation) |
| **Default management** | Handle broker default |

### 3.2 KSEI (Kustodian Sentral Efek Indonesia)

| Function | Description |
|----------|-------------|
| **Book entry** | Electronic record of securities ownership |
| **Settlement** | Transfer of securities on settlement date |
| **Custody** | Safekeeping of securities |
| **Corporate actions** | Process dividends, splits, rights |

### 3.3 Settlement Timeline (T+2)

```
T+0 (Trade Date):
  - Order matched on JATS
  - Trade confirmation sent to investor
  - KPEI begins clearing

T+1:
  - KPEI completes netting
  - Margin calculations finalized
  - Trade affirmation by counterparties

T+2 (Settlement Date):
  - KSEI transfers securities (book entry)
  - Cash transferred via RDN
  - Trade is legally settled
  - Positions updated in KSEI system
```

### 3.4 Settlement Status

```python
SETTLEMENT_STATUS = {
    "PENDING": "Trade captured, awaiting settlement",
    "AFFIRMED": "Counterparties confirmed trade terms",
    "SETTLED": "Securities and cash transferred",
    "FAILED": "Settlement failed (insufficient funds/shares)",
    "CANCELLED": "Trade cancelled before settlement",
}

def check_settlement_status(order_id: str, storage) -> str:
    """Check settlement status of an order."""
    order = storage.get_order(order_id)
    if not order:
        return "NOT_FOUND"
    
    trade_date = datetime.fromisoformat(order["created_at"])
    settlement_date = compute_settlement_date(order["created_at"])
    now = datetime.now(UTC)
    
    if now < trade_date:
        return "PENDING"
    elif now < settlement_date:
        return "AFFIRMED"
    elif now >= settlement_date:
        return "SETTLED"
```

---

## 4. Reconciliation

### 4.1 Tipe Reconciliation

| Type | Compare | Frequency | Purpose |
|------|---------|-----------|---------|
| **Position recon** | Internal positions vs KSEI/broker | Daily | Detect position breaks |
| **Cash recon** | Internal cash vs RDN | Daily | Detect cash breaks |
| **Trade recon** | Internal trades vs broker statement | Daily | Detect trade breaks |
| **NAV recon** | Internal NAV vs custodian | Daily | Verify valuation |

### 4.2 Position Reconciliation

```python
def reconcile_positions(
    internal_positions: list,
    broker_positions: list,
) -> dict:
    """Reconcile internal positions with broker positions."""
    internal_map = {p["ticker"]: p["quantity"] for p in internal_positions}
    broker_map = {p["ticker"]: p["quantity"] for p in broker_positions}
    
    all_tickers = set(internal_map.keys()) | set(broker_map.keys())
    
    matches = []
    breaks = []
    
    for ticker in all_tickers:
        internal_qty = internal_map.get(ticker, 0)
        broker_qty = broker_map.get(ticker, 0)
        diff = internal_qty - broker_qty
        
        if diff == 0:
            matches.append({"ticker": ticker, "quantity": internal_qty})
        else:
            breaks.append({
                "ticker": ticker,
                "internal_quantity": internal_qty,
                "broker_quantity": broker_qty,
                "difference": diff,
                "severity": "HIGH" if abs(diff) > 100 else "LOW",
            })
    
    return {
        "total_tickers": len(all_tickers),
        "matched": len(matches),
        "breaks": len(breaks),
        "break_details": breaks,
        "status": "BALANCED" if len(breaks) == 0 else "IMBALANCED",
    }
```

### 4.3 Cash Reconciliation

```python
def reconcile_cash(internal_cash: float, broker_cash: float, tolerance: float = 1000) -> dict:
    """Reconcile internal cash with broker/RDN cash."""
    diff = internal_cash - broker_cash
    
    return {
        "internal_cash": internal_cash,
        "broker_cash": broker_cash,
        "difference": diff,
        "within_tolerance": abs(diff) <= tolerance,
        "status": "BALANCED" if abs(diff) <= tolerance else "IMBALANCED",
    }
```

### 4.4 Break Resolution

```python
class BreakResolver:
    """Resolve reconciliation breaks."""
    
    def resolve_break(self, break_entry: dict) -> dict:
        """Attempt to resolve a reconciliation break."""
        ticker = break_entry["ticker"]
        diff = break_entry["difference"]
        
        # Common causes:
        # 1. Trade not yet settled
        # 2. Corporate action not processed
        # 3. Manual adjustment not recorded
        # 4. System error
        
        resolution = {
            "ticker": ticker,
            "difference": diff,
            "investigation": [],
            "resolution": None,
        }
        
        # Check unsettled trades
        unsettled = self._check_unsettled_trades(ticker)
        if unsettled:
            resolution["investigation"].append(f"Found {len(unsettled)} unsettled trades")
            if sum(t["quantity"] for t in unsettled) == diff:
                resolution["resolution"] = "EXPLAINED_BY_UNSETTLED_TRADES"
        
        # Check recent corporate actions
        recent_ca = self._check_recent_corporate_actions(ticker)
        if recent_ca:
            resolution["investigation"].append(f"Found {len(recent_ca)} recent corporate actions")
        
        # Check manual adjustments
        manual_adj = self._check_manual_adjustments(ticker)
        if manual_adj:
            resolution["investigation"].append(f"Found {len(manual_adj)} manual adjustments")
        
        if not resolution["resolution"]:
            resolution["resolution"] = "UNRESOLVED - requires manual investigation"
        
        return resolution
```

---

## 5. Corporate Action Processing

### 5.1 Tipe Corporate Actions

| CA Type | Impact on Position | Impact on Price | Action Required |
|---------|-------------------|-----------------|-----------------|
| **Stock split** | Quantity ↑, price ↓ | Adjust historical | Update position & cost basis |
| **Reverse split** | Quantity ↓, price ↑ | Adjust historical | Update position & cost basis |
| **Dividend (cash)** | No change | Price drops ~dividend | Record income |
| **Dividend (stock)** | Quantity ↑ | Price ↓ | Update position |
| **Rights issue** | Option to buy more | Price adjustment | Track rights |
| **Bonus issue** | Quantity ↑ | Price ↓ | Update position |
| **Merger/Acquisition** | Ticker change | Varies | Convert positions |
| **Delisting** | Position frozen | N/A | Mark as illiquid |
| **Suspension** | No trade | N/A | Flag as suspended |
| **Name change** | Ticker change | None | Update ticker mapping |

### 5.2 CA Processing Pipeline

```python
class CorporateActionProcessor:
    """Process corporate actions and update positions."""
    
    def process_ca(self, ca: dict) -> dict:
        """Process a single corporate action."""
        ca_type = ca["action_type"]
        
        if ca_type == "STOCK_SPLIT":
            return self._process_split(ca)
        elif ca_type == "CASH_DIVIDEND":
            return self._process_dividend(ca)
        elif ca_type == "STOCK_DIVIDEND":
            return self._process_stock_dividend(ca)
        elif ca_type == "BONUS_SHARES":
            return self._process_bonus(ca)
        elif ca_type == "RIGHTS_ISSUE":
            return self._process_rights(ca)
        elif ca_type == "MERGER":
            return self._process_merger(ca)
        elif ca_type == "DELISTING":
            return self._process_delisting(ca)
        else:
            return {"status": "unknown_ca_type", "ca_type": ca_type}
    
    def _process_split(self, ca: dict) -> dict:
        """Process stock split."""
        ticker = ca["ticker"]
        ratio = ca["ratio"]  # e.g., 2 means 1:2 (each share becomes 2)
        ex_date = ca["ex_date"]
        
        # Update all open positions
        positions = self.storage.get_open_position(ticker)
        if positions:
            old_qty = positions["quantity"]
            new_qty = old_qty * ratio
            new_entry = positions["avg_entry_price"] / ratio
            
            self.storage.update_position(
                positions["id"],
                quantity=new_qty,
                avg_entry_price=new_entry,
            )
        
        # Adjust historical OHLCV
        self._adjust_ohlcv_for_split(ticker, ratio, ex_date)
        
        # Audit
        self.storage.audit("corporate_action.split", {
            "ticker": ticker,
            "ratio": ratio,
            "ex_date": ex_date,
            "old_quantity": old_qty,
            "new_quantity": new_qty,
        })
        
        return {"status": "processed", "action": "split", "ticker": ticker}
    
    def _process_dividend(self, ca: dict) -> dict:
        """Process cash dividend."""
        ticker = ca["ticker"]
        amount_per_share = ca["amount_per_share"]
        ex_date = ca["ex_date"]
        
        positions = self.storage.get_open_position(ticker)
        if positions:
            total_dividend = positions["quantity"] * amount_per_share
            pph = total_dividend * 0.10  # PPh final 10%
            net = total_dividend - pph
            
            # Record dividend
            self.storage.save_dividend({
                "ticker": ticker,
                "ex_date": ex_date,
                "amount_per_share": amount_per_share,
                "total_shares": positions["quantity"],
                "gross_dividend": total_dividend,
                "pph_final": pph,
                "net_dividend": net,
            })
        
        return {"status": "processed", "action": "dividend", "ticker": ticker}
```

### 5.3 OHLCV Adjustment

```python
def adjust_ohlcv_for_split(df: pd.DataFrame, ratio: float, ex_date: str) -> pd.DataFrame:
    """Adjust OHLCV data for stock split."""
    df = df.copy()
    mask = df["date"] < ex_date
    
    df.loc[mask, ["open", "high", "low", "close"]] /= ratio
    df.loc[mask, "volume"] *= ratio
    
    return df
```

---

## 6. NAV Calculation

### 6.1 Formula

```
NAV = Cash + Σ(Position Quantity × Current Price) - Liabilities
```

### 6.2 Implementation

```python
def calculate_nav(storage, current_prices: dict) -> dict:
    """Calculate Net Asset Value."""
    # Cash balance
    cash = storage.get_cash_balance()
    
    # Positions
    positions = storage.get_all_open_positions()
    
    # Market value
    market_value = 0
    total_cost = 0
    position_details = []
    
    for pos in positions:
        ticker = pos["ticker"]
        qty = pos["quantity"]
        entry = pos["avg_entry_price"]
        current = current_prices.get(ticker, entry)
        
        pos_value = qty * current
        pos_cost = qty * entry
        unrealized = pos_value - pos_cost
        
        market_value += pos_value
        total_cost += pos_cost
        
        position_details.append({
            "ticker": ticker,
            "quantity": qty,
            "avg_entry": entry,
            "current_price": current,
            "market_value": pos_value,
            "cost_basis": pos_cost,
            "unrealized_pnl": unrealized,
            "return_pct": (unrealized / pos_cost) * 100 if pos_cost > 0 else 0,
        })
    
    nav = cash + market_value
    
    return {
        "nav": nav,
        "cash": cash,
        "market_value": market_value,
        "total_cost": total_cost,
        "total_unrealized_pnl": market_value - total_cost,
        "total_return_pct": ((market_value - total_cost) / total_cost) * 100 if total_cost > 0 else 0,
        "positions": position_details,
        "timestamp": datetime.now(UTC).isoformat(),
    }
```

### 6.3 Daily NAV Series

```python
def compute_daily_nav_series(storage, start_date: str, end_date: str) -> pd.DataFrame:
    """Compute daily NAV series for performance analysis."""
    nav_records = []
    
    # Get all trades in range
    orders = storage.get_orders(limit=100000)
    
    # Get all positions
    positions = storage.get_all_open_positions()
    
    # For each trading day, compute NAV
    trading_days = get_trading_days(start_date, end_date)
    
    for day in trading_days:
        # Get closing prices for this day
        prices = get_closing_prices(trading_days=[day])
        
        # Compute NAV
        nav = calculate_nav(storage, prices)
        
        nav_records.append({
            "date": day,
            "nav": nav["nav"],
            "cash": nav["cash"],
            "market_value": nav["market_value"],
            "unrealized_pnl": nav["total_unrealized_pnl"],
        })
    
    return pd.DataFrame(nav_records).set_index("date")
```

---

## 7. Performance Attribution

### 7.1 Attribution Dimensions

| Dimension | Question | Method |
|-----------|----------|--------|
| **Asset allocation** | How much return from sector/asset choice? | Brinson model |
| **Stock selection** | How much return from picking right stocks? | Brinson model |
| **Timing** | How much return from market timing? | Regression |
| **Factor exposure** | Which factors drove returns? | Factor regression |
| **Cost impact** | How much did costs erode returns? | Cost analysis |

### 7.2 Brinson Attribution

```python
def brinson_attribution(
    portfolio_weights: dict,
    benchmark_weights: dict,
    portfolio_returns: dict,
    benchmark_returns: dict,
) -> dict:
    """Brinson-Fachler performance attribution.
    
    Decomposes active return into:
    - Allocation effect (weighting decisions)
    - Selection effect (stock picking)
    - Interaction effect
    """
    sectors = set(portfolio_weights.keys()) | set(benchmark_weights.keys())
    
    allocation_effect = 0
    selection_effect = 0
    interaction_effect = 0
    
    for sector in sectors:
        wp = portfolio_weights.get(sector, 0)
        wb = benchmark_weights.get(sector, 0)
        rp = portfolio_returns.get(sector, 0)
        rb = benchmark_returns.get(sector, 0)
        
        # Allocation: (wp - wb) * rb
        alloc = (wp - wb) * rb
        allocation_effect += alloc
        
        # Selection: wb * (rp - rb)
        select = wb * (rp - rb)
        selection_effect += select
        
        # Interaction: (wp - wb) * (rp - rb)
        interact = (wp - wb) * (rp - rb)
        interaction_effect += interact
    
    total_active_return = allocation_effect + selection_effect + interaction_effect
    
    return {
        "allocation_effect": allocation_effect,
        "selection_effect": selection_effect,
        "interaction_effect": interaction_effect,
        "total_active_return": total_active_return,
    }
```

### 7.3 Factor Attribution

```python
def factor_attribution(returns: pd.Series, factors: pd.DataFrame) -> dict:
    """Attribute returns to risk factors using regression."""
    from sklearn.linear_model import LinearRegression
    
    model = LinearRegression()
    model.fit(factors, returns)
    
    contributions = {}
    for i, factor in enumerate(factors.columns):
        contributions[factor] = model.coef_[i] * factors[factor].mean()
    
    return {
        "alpha": model.intercept_,
        "factor_contributions": contributions,
        "r_squared": model.score(factors, returns),
    }
```

### 7.4 Cost Impact Analysis

```python
def cost_impact_analysis(orders: list, initial_capital: float) -> dict:
    """Analyze impact of transaction costs on returns."""
    total_fees = sum(o.get("fee", 0) for o in orders)
    total_pph = sum(o.get("pph", 0) for o in orders if o["order_type"] == "SELL")
    total_slippage = sum(o.get("slippage_cost", 0) for o in orders)
    
    total_costs = total_fees + total_pph + total_slippage
    cost_pct = total_costs / initial_capital * 100
    
    return {
        "total_fees": total_fees,
        "total_pph": total_pph,
        "total_slippage": total_slippage,
        "total_costs": total_costs,
        "cost_pct_of_capital": cost_pct,
        "trades_count": len(orders),
        "avg_cost_per_trade": total_costs / len(orders) if orders else 0,
    }
```

---

## 8. Position Management

### 8.1 Position State Machine

```
                    ┌──────────┐
                    │   NONE   │ (no position)
                    └────┬─────┘
                         │ BUY
                         ▼
                    ┌──────────┐
        ┌───────────│   OPEN   │───────────┐
        │           └────┬─────┘           │
        │ SELL (partial) │ SELL (full)     │
        │                ▼                 │
        │           ┌──────────┐           │
        └──────────▶│  CLOSED  │           │
                    └──────────┘           │
                                           │
    Partial sell: OPEN (reduced qty)      │
    Full sell: CLOSED                      │
```

### 8.2 Position Update Logic

```python
def update_position_on_fill(
    storage, order: dict, existing_position: dict | None
) -> dict:
    """Update position after order fill."""
    if order["order_type"] == "BUY":
        if existing_position:
            # Add to existing position
            old_qty = existing_position["quantity"]
            old_entry = existing_position["avg_entry_price"]
            new_qty = order["quantity"]
            new_price = order["price"]
            
            total_qty = old_qty + new_qty
            avg_entry = (old_qty * old_entry + new_qty * new_price) / total_qty
            
            storage.update_position(
                existing_position["id"],
                quantity=total_qty,
                avg_entry_price=avg_entry,
            )
            return {"status": "position_increased", "quantity": total_qty}
        else:
            # New position
            position_id = storage.save_position(
                ticker=order["ticker"],
                quantity=order["quantity"],
                avg_entry_price=order["price"],
                stop_loss=order.get("stop_loss"),
                take_profit=order.get("take_profit"),
            )
            return {"status": "position_opened", "position_id": position_id}
    
    elif order["order_type"] == "SELL":
        if existing_position:
            remaining = existing_position["quantity"] - order["quantity"]
            realized_pnl = (order["price"] - existing_position["avg_entry_price"]) * order["quantity"]
            
            if remaining <= 0:
                storage.update_position(
                    existing_position["id"],
                    status="CLOSED",
                    quantity=0,
                    realized_pnl=realized_pnl,
                )
                return {"status": "position_closed", "realized_pnl": realized_pnl}
            else:
                storage.update_position(
                    existing_position["id"],
                    quantity=remaining,
                    realized_pnl=realized_pnl,
                )
                return {"status": "position_reduced", "remaining": remaining, "realized_pnl": realized_pnl}
```

---

## 9. Implementasi Sistem

### 9.1 Post-Trade Engine

```python
class PostTradeEngine:
    """Post-trade processing engine."""
    
    def __init__(self, storage):
        self.storage = storage
        self.ca_processor = CorporateActionProcessor(storage)
        self.recon = ReconciliationEngine(storage)
    
    def daily_post_trade_process(self):
        """Run daily post-trade processing."""
        results = {}
        
        # 1. Trade capture & enrichment
        results["trade_capture"] = self._capture_today_trades()
        
        # 2. Settlement check
        results["settlement"] = self._check_settlements()
        
        # 3. Corporate action processing
        results["corporate_actions"] = self._process_today_cas()
        
        # 4. Position reconciliation
        results["reconciliation"] = self._run_reconciliation()
        
        # 5. NAV calculation
        results["nav"] = self._calculate_end_of_day_nav()
        
        # 6. Performance attribution
        results["attribution"] = self._run_attribution()
        
        # 7. Audit
        self.storage.audit("post_trade.daily", results)
        
        return results
```

### 9.2 Database Schema

```sql
-- Trade capture table (enriched orders)
CREATE TABLE IF NOT EXISTS trade_captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    value REAL NOT NULL,
    execution_time TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    broker_fee REAL DEFAULT 0,
    levy REAL DEFAULT 0,
    pph_final REAL DEFAULT 0,
    total_cost REAL DEFAULT 0,
    realized_pnl REAL DEFAULT 0,
    cost_basis REAL DEFAULT 0,
    settlement_status TEXT DEFAULT 'PENDING',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Reconciliation breaks
CREATE TABLE IF NOT EXISTS recon_breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ticker TEXT,
    break_type TEXT NOT NULL,  -- 'position', 'cash', 'trade'
    internal_value REAL,
    external_value REAL,
    difference REAL,
    severity TEXT,
    status TEXT DEFAULT 'OPEN',  -- OPEN, INVESTIGATING, RESOLVED
    resolution TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- NAV history
CREATE TABLE IF NOT EXISTS nav_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    nav REAL NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    total_cost REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    realized_pnl_today REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Corporate action log
CREATE TABLE IF NOT EXISTS ca_processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ca_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action_type TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    positions_updated INTEGER,
    ohlcv_adjusted INTEGER,
    status TEXT NOT NULL,
    details TEXT,  -- JSON
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## 10. Checklist Implementasi

### Trade Capture
- [ ] Trade capture with enrichment (settlement date, costs, PnL)
- [ ] Settlement date computation (T+2, skipping holidays)
- [ ] Settlement status tracking
- [ ] Trade audit trail

### Clearing & Settlement
- [ ] Settlement status tracking (PENDING → AFFIRMED → SETTLED)
- [ ] Holiday calendar integration
- [ ] Failed settlement handling
- [ ] Cash flow projection (T+2)

### Reconciliation
- [ ] Position reconciliation (internal vs broker)
- [ ] Cash reconciliation (internal vs RDN)
- [ ] Trade reconciliation (internal vs broker statement)
- [ ] Break detection and logging
- [ ] Break resolution workflow
- [ ] Daily recon scheduler

### Corporate Actions
- [ ] Stock split processing (position + OHLCV adjustment)
- [ ] Cash dividend processing (income + PPh)
- [ ] Stock dividend / bonus shares
- [ ] Rights issue tracking
- [ ] Merger/acquisition (ticker conversion)
- [ ] Delisting/suspension (position flagging)
- [ ] CA audit trail

### NAV
- [ ] Daily NAV calculation
- [ ] NAV history series
- [ ] Cash + market value computation
- [ ] Unrealized PnL tracking
- [ ] NAV per unit (for fund structures)

### Attribution
- [ ] Brinson attribution (allocation vs selection)
- [ ] Factor attribution (regression-based)
- [ ] Cost impact analysis
- [ ] Benchmark comparison (IHSG)
- [ ] Monthly/quarterly attribution report

### Position Management
- [ ] Position state machine (NONE → OPEN → CLOSED)
- [ ] Average entry price (weighted)
- [ ] Partial sell support
- [ ] Stop-loss / take-profit tracking
- [ ] Trailing stop update
- [ ] Highest price since entry tracking

### Database
- [ ] `trade_captures` table
- [ ] `recon_breaks` table
- [ ] `nav_history` table
- [ ] `ca_processing_log` table
- [ ] Proper indexes
- [ ] Audit trail integration

---

## Referensi

1. KPEI — Kliring Penjaminan Efek Indonesia
2. KSEI — Kustodian Sentral Efek Indonesia
3. BEI — Peraturan I-B (Perdagangan Efek)
4. `src/trading_system/data/storage.py` — Position & order management
5. `src/trading_system/corporate/` — Corporate action processing
6. `src/trading_system/portfolio/` — Portfolio engine & performance
7. `src/trading_system/execution/automated.py` — Automated execution
8. `pustaka/18-modul-engine-data-wajib.md` — Module registry
9. `pustaka/19-flow-logic-testing-kpi.md` — Data flow & business logic
10. `pustaka/25-pajak-akuntansi-trading.md` — Tax & accounting

---

> **Catatan:** Post-trade processing adalah "back office" yang sering diabaikan tetapi kritis untuk akurasi PnL, kepatuhan pajak, dan kepercayaan investor. Reconciliation harian adalah discipline yang tidak boleh dilewati.
