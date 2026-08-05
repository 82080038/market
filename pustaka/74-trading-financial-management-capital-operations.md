# Trading Financial Management & Capital Operations

> **Dokumen 74** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Kalkulasi modal untuk transaksi, cek ketersediaan modal (buying power), eksekusi transaksi dari hasil screening/decision, manajemen keuangan trading (cash flow, capital allocation, capital efficiency), dan accounting sistem trading (trade ledger, PnL, NAV, reconciliation).
>
> **Konteks:** Dokumen 07 bahas position sizing (risk perspective). Dokumen 25 bahas pajak & akuntansi (tax perspective). Dokumen 26 bahas post-trade settlement (operations perspective). Dokumen 40 bahas OMS/EMS (architecture perspective). Tapi belum ada doc yang menyatukan semuanya dari **financial management perspective**: bagaimana sistem menghitung modal, mengecek ketersediaan, mengeksekusi, dan mengelola keuangan trading secara holistik.

---

## Daftar Isi

1. [Financial Lifecycle Overview](#1-financial-lifecycle-overview)
2. [Kalkulasi Modal untuk Transaksi](#2-kalkulasi-modal-untuk-transaksi)
3. [Cek Ketersediaan Modal (Buying Power)](#3-cek-ketersediaan-modal-buying-power)
4. [Flow: Screening → Decision → Eksekusi](#4-flow-screening--decision--eksekusi)
5. [Manajemen Keuangan Trading](#5-manajemen-keuangan-trading)
6. [Trading Accounting System](#6-trading-accounting-system)
7. [Konfigurasi & Parameter Management](#7-konfigurasi--parameter-management)
8. [Implementasi Kode](#8-implementasi-kode)
9. [Hubungan dengan Dokumen Lain](#9-hubungan-dengan-dokumen-lain)

---

## 1. Financial Lifecycle Overview

### 1.1 Trading Financial Lifecycle

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ SCREEN   │──▶| DECIDE   │──▶| CALCULATE│──▶| CHECK    │──▶| EXECUTE  │
│          │   |          │   | CAPITAL  │   | AVAILAB. │   |          │
│ Screener │   | Decision │   |          │   |          │   |          │
| filter   │   | Engine   │   | Berapa   │   | Apakah   │   | Buy/Sell │
| 928 → 50 │   | reco +   │   | modal    │   | modal    │   | via      │
| ticker   │   | conviction│   | dibutuh- │   | cukup?   │   | broker   │
|          │   |          │   | kan?     │   |          │   |          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                      │
                                                      ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ RECON    │──▶| ACCOUNT  │──▶| REPORT   │──▶| REBALANCE│
│          │   |          │   |          │   |          │
│ Broker   │   | Trade    │   | PnL      │   | Capital  │
| vs       │   | Ledger   │   | NAV      │   | reallo-  │
| internal │   | PnL      │   | Tax      │   | cation   │
|          │   | Cost     │   | SPT      │   |          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
```

### 1.2 Komponen Financial System

| Komponen | Fungsi | Existing Doc | Gap |
|----------|--------|-------------|-----|
| **Capital Calculator** | Hitung total modal dibutuhkan per transaksi | Doc 07 (risk-based) | Tidak ada cost-inclusive calculator |
| **Buying Power Checker** | Cek apakah modal tersedia cukup | Doc 40 (mentioned) | Tidak ada detail implementasi |
| **Execution from Screening** | Screen → decide → execute pipeline | Doc 20, 39 | Tidak ada unified flow |
| **Cash Flow Manager** | Track cash in/out, fees, dividends | Doc 26 (settlement) | Tidak ada cash management module |
| **Trade Ledger** | Record setiap transaksi (double-entry) | Doc 25 (tax) | Tidak ada internal ledger |
| **PnL Engine** | Realized/unrealized PnL, attribution | Doc 26 (NAV) | Tidak ada PnL attribution |
| **Capital Allocator** | Alokasi modal across positions | Doc 21 (portfolio) | Tidak ada capital allocation rules |
| **Reconciliation** | Broker vs internal sync | Doc 26 | Ada, tapi tidak dari financial perspective |

---

## 2. Kalkulasi Modal untuk Transaksi

### 2.1 Komponen Modal per Transaksi

```
Total Modal Dibutuhkan = (Harga × Jumlah Lot × 100) + Biaya Transaksi

Biaya Transaksi (BUY):
  + Broker fee (0.15% × transaction value)
  + Sales tax (PPh final 0.1% × transaction value)
  + SEBI fee (0.005% × transaction value)
  + KPEI fee (Rp 1,000/order)

Biaya Transaksi (SELL):
  + Broker fee (0.15% × transaction value)
  + Sales tax (PPh final 0.1% × transaction value)
  + SEBI fee (0.005% × transaction value)
  + KPEI fee (Rp 1,000/order)
  + BEI fee (0.004% × transaction value)
```

### 2.2 Capital Calculator

```python
# risk/capital_calculator.py

from dataclasses import dataclass
from trading_system.risk.costs import get_default_cost_model

@dataclass
class CapitalRequirement:
    """Total capital needed for a transaction."""
    ticker: str
    action: str  # BUY or SELL
    shares: int
    price: float
    transaction_value: float
    broker_fee: float
    sales_tax: float
    sebi_fee: float
    kpei_fee: float
    bei_fee: float  # SELL only
    total_fees: float
    total_capital_needed: float  # transaction_value + total_fees (BUY)
                                 # or transaction_value - total_fees (SELL, net proceeds)

def calculate_capital_needed(
    ticker: str,
    action: str,
    shares: int,
    price: float,
) -> CapitalRequirement:
    """Calculate total capital needed for a transaction.

    For BUY: total_capital_needed = transaction_value + all fees
    For SELL: total_capital_needed = transaction_value - all fees (net proceeds)
    """
    cost_model = get_default_cost_model()
    transaction_value = shares * price

    broker_fee = cost_model.broker_fee_buy * transaction_value if action == "BUY" \
        else cost_model.broker_fee_sell * transaction_value
    sales_tax = cost_model.sales_tax * transaction_value  # 0.1% PPh final
    sebi_fee = 0.00005 * transaction_value  # SEBI fee
    kpei_fee = 1000.0  # Fixed per order
    bei_fee = 0.00004 * transaction_value if action == "SELL" else 0.0  # BEI fee SELL only

    total_fees = broker_fee + sales_tax + sebi_fee + kpei_fee + bei_fee

    if action == "BUY":
        total_capital = transaction_value + total_fees
    else:
        total_capital = transaction_value - total_fees  # Net proceeds from sell

    return CapitalRequirement(
        ticker=ticker,
        action=action,
        shares=shares,
        price=price,
        transaction_value=transaction_value,
        broker_fee=broker_fee,
        sales_tax=sales_tax,
        sebi_fee=sebi_fee,
        kpei_fee=kpei_fee,
        bei_fee=bei_fee,
        total_fees=total_fees,
        total_capital_needed=total_capital,
    )
```

### 2.3 Position Sizing → Capital Needed

Position sizing (doc 07) menghitung **berapa shares** berdasarkan risk. Capital calculator menghitung **berapa rupiah** dibutuhkan untuk shares tersebut.

```python
def position_sizing_to_capital(
    capital: float,
    entry: float,
    stop_loss: float,
    risk_pct: float = 0.01,
) -> dict:
    """Convert risk-based position sizing to actual capital needed.

    Step 1: Position sizing (risk-based) → shares
    Step 2: Capital calculator → total rupiah needed
    """
    # Step 1: Risk-based position sizing (from doc 07)
    risk_amount = capital * risk_pct
    risk_per_share = abs(entry - stop_loss)
    shares = int(risk_amount / risk_per_share)

    # Round to IDX lot (100 shares)
    shares = max(100, (shares // 100) * 100)

    # Cap at 10% of capital
    max_shares = int((capital * 0.10) / entry)
    shares = min(shares, (max_shares // 100) * 100)

    # Step 2: Calculate actual capital needed
    req = calculate_capital_needed(ticker="UNKNOWN", action="BUY", shares=shares, price=entry)

    return {
        "shares": shares,
        "lots": shares // 100,
        "transaction_value": req.transaction_value,
        "total_fees": req.total_fees,
        "total_capital_needed": req.total_capital_needed,
        "capital_pct": req.total_capital_needed / capital * 100,
        "risk_amount": risk_amount,
        "risk_per_share": risk_per_share,
    }
```

### 2.4 Contoh Perhitungan

```python
# Contoh: BBCA.JK @ Rp 7,850, stop loss Rp 7,600, capital Rp 100,000,000
result = position_sizing_to_capital(
    capital=100_000_000,
    entry=7850,
    stop_loss=7600,
    risk_pct=0.01,  # 1% risk
)

# Output:
# shares: 400 (4 lot)
# transaction_value: Rp 3,140,000
# broker_fee: Rp 4,710 (0.15%)
# sales_tax: Rp 3,140 (0.1%)
# sebi_fee: Rp 157
# kpei_fee: Rp 1,000
# total_fees: Rp 9,007
# total_capital_needed: Rp 3,149,007
# capital_pct: 3.15% dari modal
```

---

## 3. Cek Ketersediaan Modal (Buying Power)

### 3.1 Buying Power Definition

```
Buying Power = Cash Balance - Reserved Cash

Reserved Cash:
  + Pending buy orders (order_value + estimated fees)
  + Settlement pending (T+2, cash belum debited)
  + Minimum cash buffer (configurable, default Rp 0)

Cash Balance:
  + Cash dari broker (real) atau internal tracking (paper)
  + Dividend received (cash in)
  - Buy executed (cash out)
  - Fees paid (cash out)
  + Sell executed (cash in, net of fees)
  + Deposit (cash in)
  - Withdrawal (cash out)
```

### 3.2 Buying Power Checker

```python
# risk/buying_power.py

from dataclasses import dataclass

@dataclass
class BuyingPowerCheck:
    """Result of buying power check."""
    can_execute: bool
    cash_available: float
    buying_power: float
    capital_needed: float
    reserved_cash: float
    shortfall: float  # 0 if can_execute, else negative
    reason: str

def check_buying_power(
    cash_balance: float,
    capital_needed: float,
    reserved_cash: float = 0.0,
    min_cash_buffer: float = 0.0,
) -> BuyingPowerCheck:
    """Check if sufficient buying power exists for a transaction.

    Args:
        cash_balance: Current cash from broker or internal tracking.
        capital_needed: Total capital needed (from CapitalRequirement).
        reserved_cash: Cash reserved for pending orders + settlement.
        min_cash_buffer: Minimum cash to keep as buffer.

    Returns:
        BuyingPowerCheck with can_execute flag and details.
    """
    buying_power = cash_balance - reserved_cash - min_cash_buffer
    shortfall = buying_power - capital_needed

    if shortfall >= 0:
        return BuyingPowerCheck(
            can_execute=True,
            cash_available=cash_balance,
            buying_power=buying_power,
            capital_needed=capital_needed,
            reserved_cash=reserved_cash,
            shortfall=0.0,
            reason="Sufficient buying power.",
        )
    else:
        return BuyingPowerCheck(
            can_execute=False,
            cash_available=cash_balance,
            buying_power=buying_power,
            capital_needed=capital_needed,
            reserved_cash=reserved_cash,
            shortfall=abs(shortfall),
            reason=f"Insufficient buying power. Need Rp {capital_needed:,.0f}, "
                  f"available Rp {buying_power:,.0f}, shortfall Rp {abs(shortfall):,.0f}.",
        )
```

### 3.3 Integrasi dengan Broker Adapter

```python
# Sistem cek buying power sebelum eksekusi
def pre_trade_capital_check(
    broker_adapter: BrokerAdapter,
    ticker: str,
    action: str,
    shares: int,
    price: float,
) -> dict:
    """Full pre-trade capital check using live broker data.

    Step 1: Get cash balance from broker
    Step 2: Calculate capital needed
    Step 3: Check buying power
    Step 4: Return result
    """
    # Step 1: Get live cash balance
    account = broker_adapter.get_account()
    cash_balance = account.cash_balance
    buying_power_broker = account.buying_power

    # Step 2: Calculate capital needed
    req = calculate_capital_needed(ticker, action, shares, price)

    # Step 3: Check buying power
    check = check_buying_power(
        cash_balance=cash_balance,
        capital_needed=req.total_capital_needed,
    )

    # Step 4: Return comprehensive result
    return {
        "can_execute": check.can_execute,
        "broker_buying_power": buying_power_broker,
        "internal_buying_power": check.buying_power,
        "capital_needed": req.total_capital_needed,
        "cash_balance": cash_balance,
        "shortfall": check.shortfall,
        "reason": check.reason,
        "transaction_breakdown": {
            "transaction_value": req.transaction_value,
            "broker_fee": req.broker_fee,
            "sales_tax": req.sales_tax,
            "total_fees": req.total_fees,
        },
    }
```

### 3.4 Current Codebase Status

| Komponen | Status | File |
|----------|--------|------|
| `BrokerAccount.cash_balance` | ✅ Ada | `execution/broker_adapter.py:83` |
| `BrokerAccount.buying_power` | ✅ Ada | `execution/broker_adapter.py:86` |
| `get_cash_balance()` | ✅ Ada (Mock) | `execution/broker_adapter.py:284` |
| Cash check in paper trading | ✅ Ada | `execution/paper_execution.py:93` |
| Cash check in broker mock | ✅ Ada | `execution/broker_adapter.py:207` |
| `check_buying_power()` | ❌ Tidak ada | Perlu dibuat |
| Dynamic cash tracking | ❌ Tidak ada | `portfolio/engine.py` pakai static `self.cash` |
| Reserved cash tracking | ❌ Tidak ada | Perlu dibuat |

---

## 4. Flow: Screening → Decision → Eksekusi

### 4.1 Complete Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                     SCREENING → EXECUTION PIPELINE                    │
│                                                                      │
│  ┌──────────┐                                                        │
│  | SCREENER |                                                        │
│  | 928 → N  |                                                        │
│  | tickers  |                                                        │
│  └────┬─────┘                                                        │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────┐                                                        │
│  | DECISION |  Untuk setiap ticker yang pass screening:             │
│  | ENGINE   |  - Compute 6-factor score                              │
│  |          |  - Generate recommendation (BUY/SELL/HOLD/AVOID)      │
│  |          |  - Set conviction score (0-100)                        │
│  |          |  - Set entry/SL/TP levels                              │
│  └────┬─────┘                                                        │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────┐                                                        │
│  | RISK     |  Untuk setiap BUY/SELL recommendation:                │
│  | ENGINE   |  - Position sizing (risk-based)                        │
│  |          |  - Pre-trade checklist (liquidity, gorengan, etc.)    │
│  |          |  - VaR check                                           │
│  └────┬─────┘                                                        │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────┐                                                        │
│  | CAPITAL  |  Untuk setiap position yang pass risk check:          │
│  | CALC     |  - Calculate total capital needed (price + fees)      │
│  |          |  - Calculate capital % of portfolio                    │
│  └────┬─────┘                                                        │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────┐                                                        │
│  | BUYING   |  Untuk setiap capital requirement:                    │
│  | POWER    |  - Get cash balance from broker                        │
│  | CHECK    |  - Check if buying power sufficient                    │
│  |          |  - If insufficient: skip or queue                      │
│  └────┬─────┘                                                        │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────┐                                                        │
│  | EXECUTE  |  Untuk setiap trade yang pass buying power:           │
│  |          |  - Generate order (ticker, shares, price, SL, TP)     │
│  |          |  - Send to broker (real) or paper engine               │
│  |          |  - Record in trade ledger                              │
│  |          |  - Update cash balance                                 │
│  |          |  - Update position                                     │
│  |          |  - Log to audit trail                                  │
│  └──────────┘                                                        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Screening → Execution Code Flow

```python
# pipeline/screen_to_execute.py

def screen_to_execute_pipeline(
    capital: float,
    max_positions: int = 10,
    auto_trade: bool = False,
    broker_adapter: BrokerAdapter | None = None,
) -> dict:
    """Complete pipeline from screening to execution.

    Step 1: Screen all tickers → filtered list
    Step 2: Decision engine → recommendations
    Step 3: Risk engine → position sizing
    Step 4: Capital calculator → capital needed
    Step 5: Buying power check → can execute?
    Step 6: Execute (if auto_trade) or log (if monitoring)
    """
    results = {
        "screened": 0,
        "recommended": 0,
        "passed_risk": 0,
        "passed_capital": 0,
        "executed": 0,
        "skipped": [],
        "executions": [],
    }

    # Step 1: Screen
    screened_tickers = screener.screen_all()
    results["screened"] = len(screened_tickers)

    # Step 2: Decision for each screened ticker
    for ticker in screened_tickers:
        rec = decision_engine.recommend(ticker, capital=capital)
        if rec["recommendation"]["action"] not in ("BUY", "SELL"):
            continue
        results["recommended"] += 1

        # Step 3: Risk check
        risk_assessment = risk_engine.assess(ticker, rec)
        if not risk_assessment.can_proceed:
            results["skipped"].append({
                "ticker": ticker, "stage": "risk", "reason": risk_assessment.reason,
            })
            continue
        results["passed_risk"] += 1

        # Step 4: Capital calculation
        shares = risk_assessment.position_size
        price = rec["recommendation"]["entry_price"]
        cap_req = calculate_capital_needed(ticker, "BUY", shares, price)

        # Step 5: Buying power check
        if broker_adapter:
            account = broker_adapter.get_account()
            cash = account.cash_balance
        else:
            cash = capital  # Fallback to config capital

        bp_check = check_buying_power(cash, cap_req.total_capital_needed)
        if not bp_check.can_execute:
            results["skipped"].append({
                "ticker": ticker, "stage": "buying_power",
                "reason": bp_check.reason,
            })
            continue
        results["passed_capital"] += 1

        # Step 6: Execute or log
        order = {
            "ticker": ticker,
            "action": rec["recommendation"]["action"],
            "shares": shares,
            "target_price": price,
            "stop_loss": rec["recommendation"]["stop_loss"],
            "take_profit": rec["recommendation"]["take_profit"],
        }

        if auto_trade and broker_adapter:
            result = broker_adapter.place_order(order)
            results["executions"].append({
                "ticker": ticker, "result": result,
            })
            if result["status"] == "ok":
                results["executed"] += 1
        else:
            results["executions"].append({
                "ticker": ticker, "result": {"status": "monitoring", "order": order},
            })

    return results
```

### 4.3 Current Codebase Flow

| Step | Code Location | Status |
|------|---------------|--------|
| Screen | `analysis/factor_screener.py` | ✅ Implemented |
| Decision | `decision/engine.py` | ✅ Implemented |
| Risk check | `risk/pre_trade_checklist.py` | ✅ Implemented |
| Capital calc | — | ❌ Missing |
| Buying power | `execution/broker_adapter.py:207` (mock only) | ⚠️ Partial |
| Execute | `execution/automated.py` | ✅ Implemented |
| Trade ledger | `data/storage.py` (orders table) | ⚠️ Partial |
| Cash update | `execution/paper_execution.py:99` (paper only) | ⚠️ Partial |

---

## 5. Manajemen Keuangan Trading

### 5.1 Cash Flow Management

```
CASH FLOW TRACKING

Cash In (+):
  ├── Deposit (user top-up)
  ├── Sell proceeds (net of fees)
  ├── Dividend received
  └── Rights issue proceeds (if sold)

Cash Out (-):
  ├── Buy cost (price + fees)
  ├── Broker fee
  ├── Sales tax (PPh 0.1%)
  ├── SEBI fee
  ├── KPEI fee
  ├── BEI fee (sell only)
  └── Withdrawal

Cash Balance = Previous Balance + Cash In - Cash Out
```

### 5.2 Cash Flow Tracker

```python
# portfolio/cash_flow.py

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class CashFlowType(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BUY_COST = "buy_cost"
    SELL_PROCEEDS = "sell_proceeds"
    DIVIDEND = "dividend"
    FEE = "fee"
    TAX = "tax"
    ADJUSTMENT = "adjustment"

@dataclass
class CashFlowEntry:
    """Single cash flow entry (double-entry ledger)."""
    date: datetime
    type: CashFlowType
    direction: str  # "IN" or "OUT"
    amount: float
    ticker: str | None = None
    order_id: str | None = None
    description: str = ""
    balance_after: float = 0.0

class CashFlowManager:
    """Manage trading cash flow."""

    def __init__(self, initial_capital: float):
        self.balance = initial_capital
        self.entries: list[CashFlowEntry] = []
        self.reserved: float = 0.0  # Reserved for pending orders

    def deposit(self, amount: float, description: str = "") -> CashFlowEntry:
        """Add capital to trading account."""
        self.balance += amount
        entry = CashFlowEntry(
            date=datetime.now(),
            type=CashFlowType.DEPOSIT,
            direction="IN",
            amount=amount,
            description=description or "Deposit",
            balance_after=self.balance,
        )
        self.entries.append(entry)
        return entry

    def withdraw(self, amount: float, description: str = "") -> CashFlowEntry | None:
        """Withdraw capital from trading account."""
        if amount > self.balance:
            return None  # Insufficient balance
        self.balance -= amount
        entry = CashFlowEntry(
            date=datetime.now(),
            type=CashFlowType.WITHDRAWAL,
            direction="OUT",
            amount=amount,
            description=description or "Withdrawal",
            balance_after=self.balance,
        )
        self.entries.append(entry)
        return entry

    def record_buy(self, ticker: str, shares: int, price: float,
                   fees: float, tax: float, order_id: str = "") -> CashFlowEntry:
        """Record cash outflow from buy execution."""
        cost = shares * price + fees + tax
        self.balance -= cost
        entry = CashFlowEntry(
            date=datetime.now(),
            type=CashFlowType.BUY_COST,
            direction="OUT",
            amount=cost,
            ticker=ticker,
            order_id=order_id,
            description=f"BUY {shares} {ticker} @ {price} + fees {fees} + tax {tax}",
            balance_after=self.balance,
        )
        self.entries.append(entry)
        return entry

    def record_sell(self, ticker: str, shares: int, price: float,
                    fees: float, tax: float, order_id: str = "") -> CashFlowEntry:
        """Record cash inflow from sell execution."""
        proceeds = shares * price - fees - tax
        self.balance += proceeds
        entry = CashFlowEntry(
            date=datetime.now(),
            type=CashFlowType.SELL_PROCEEDS,
            direction="IN",
            amount=proceeds,
            ticker=ticker,
            order_id=order_id,
            description=f"SELL {shares} {ticker} @ {price} - fees {fees} - tax {tax}",
            balance_after=self.balance,
        )
        self.entries.append(entry)
        return entry

    def record_dividend(self, ticker: str, amount: float, tax: float = 0) -> CashFlowEntry:
        """Record dividend received (net of tax)."""
        net = amount - tax
        self.balance += net
        entry = CashFlowEntry(
            date=datetime.now(),
            type=CashFlowType.DIVIDEND,
            direction="IN",
            amount=net,
            ticker=ticker,
            description=f"Dividend {ticker} (net of tax {tax})",
            balance_after=self.balance,
        )
        self.entries.append(entry)
        return entry

    def get_buying_power(self) -> float:
        """Current buying power = balance - reserved."""
        return self.balance - self.reserved

    def get_cash_flow_summary(self, start_date=None, end_date=None) -> dict:
        """Summary of cash flows in a period."""
        entries = self.entries
        if start_date:
            entries = [e for e in entries if e.date >= start_date]
        if end_date:
            entries = [e for e in entries if e.date <= end_date]

        total_in = sum(e.amount for e in entries if e.direction == "IN")
        total_out = sum(e.amount for e in entries if e.direction == "OUT")

        by_type = {}
        for e in entries:
            key = e.type.value
            if key not in by_type:
                by_type[key] = {"in": 0, "out": 0, "count": 0}
            if e.direction == "IN":
                by_type[key]["in"] += e.amount
            else:
                by_type[key]["out"] += e.amount
            by_type[key]["count"] += 1

        return {
            "current_balance": self.balance,
            "buying_power": self.get_buying_power(),
            "total_cash_in": total_in,
            "total_cash_out": total_out,
            "net_cash_flow": total_in - total_out,
            "by_type": by_type,
            "entry_count": len(entries),
        }
```

### 5.3 Capital Allocation

```python
# portfolio/capital_allocator.py

class CapitalAllocator:
    """Allocate capital across multiple positions."""

    def __init__(self, total_capital: float):
        self.total_capital = total_capital

    def allocate_by_conviction(self, recommendations: list[dict]) -> list[dict]:
        """Allocate capital proportional to conviction score.

        Higher conviction → more capital allocation.
        """
        # Filter only BUY recommendations
        buys = [r for r in recommendations if r["action"] == "BUY"]
        if not buys:
            return []

        # Sort by conviction (highest first)
        buys.sort(key=lambda r: r.get("conviction", 0), reverse=True)

        # Allocate proportional to conviction
        total_conviction = sum(r.get("conviction", 0) for r in buys)
        if total_conviction == 0:
            return []

        # Max 10% per position, min 2% per position
        allocations = []
        for rec in buys:
            conviction = rec.get("conviction", 0)
            weight = conviction / total_conviction
            # Cap at 10% of total capital
            weight = min(weight, 0.10)
            # Floor at 2%
            weight = max(weight, 0.02)

            capital_alloc = self.total_capital * weight
            allocations.append({
                "ticker": rec["ticker"],
                "conviction": conviction,
                "weight": weight,
                "capital_allocated": capital_alloc,
                "recommendation": rec,
            })

        # Normalize weights to sum to max_invest_pct (e.g., 80% of capital)
        max_invest_pct = 0.80  # Keep 20% cash buffer
        total_weight = sum(a["weight"] for a in allocations)
        if total_weight > max_invest_pct:
            scale = max_invest_pct / total_weight
            for a in allocations:
                a["weight"] *= scale
                a["capital_allocated"] = self.total_capital * a["weight"]

        return allocations

    def allocate_equal_weight(self, tickers: list[str], max_pct: float = 0.80) -> list[dict]:
        """Equal-weight allocation across tickers."""
        if not tickers:
            return []
        weight = min(max_pct / len(tickers), 0.10)  # Max 10% per position
        return [
            {
                "ticker": t,
                "weight": weight,
                "capital_allocated": self.total_capital * weight,
            }
            for t in tickers
        ]

    def allocate_hrp(self, covariance: pd.DataFrame, weights: pd.Series) -> list[dict]:
        """HRP-based allocation (see doc 21)."""
        # Implementation in portfolio/engine.py
        pass
```

### 5.4 Capital Efficiency Metrics

| Metric | Formula | Target | Description |
|--------|---------|--------|-------------|
| **Capital Utilization** | Invested / Total Capital | 60-80% | % modal yang terinvestasi |
| **Cash Ratio** | Cash / Total Capital | 20-40% | % modal dalam cash |
| **Return on Capital (ROC)** | Realized PnL / Total Capital | > 15% p.a. | Return atas modal |
| **Return on Invested Capital (ROIC)** | PnL / Invested Capital | > 20% p.a. | Return atas modal terinvestasi |
| **Capital Efficiency** | PnL / (Invested Capital × Time) | — | Return per unit modal per unit waktu |
| **Cash Drag** | (Cash × Risk-free rate) / Total Capital | < 2% | Opportunity cost dari cash idle |
| **Capital Turnover** | Total transaction value / Average capital | — | Berapa kali modal berputar dalam periode |

```python
def compute_capital_efficiency(cash_manager: CashFlowManager,
                                positions: list, current_prices: dict) -> dict:
    """Compute capital efficiency metrics."""
    total_capital = cash_manager.balance + sum(
        p["quantity"] * current_prices.get(p["ticker"], 0) for p in positions
    )
    invested = sum(p["quantity"] * current_prices.get(p["ticker"], 0) for p in positions)
    cash = cash_manager.balance

    return {
        "total_capital": total_capital,
        "invested": invested,
        "cash": cash,
        "capital_utilization_pct": invested / total_capital * 100 if total_capital > 0 else 0,
        "cash_ratio_pct": cash / total_capital * 100 if total_capital > 0 else 0,
        "position_count": len(positions),
    }
```

---

## 6. Trading Accounting System

### 6.1 Trade Ledger (Double-Entry)

Setiap transaksi dicatat dalam trade ledger dengan double-entry principle:

```
BUY Transaction:
  DEBIT:  Position (asset)     Rp 3,140,000  (shares × price)
  DEBIT:  Broker Fee (expense) Rp 4,710
  DEBIT:  Sales Tax (expense)  Rp 3,140
  DEBIT:  SEBI Fee (expense)   Rp 157
  DEBIT:  KPEI Fee (expense)   Rp 1,000
  CREDIT: Cash (asset)         Rp 3,149,007  (total cash out)

SELL Transaction:
  DEBIT:  Cash (asset)         Rp X (net proceeds)
  DEBIT:  Broker Fee (expense) Rp Y
  DEBIT:  Sales Tax (expense)  Rp Z
  CREDIT: Position (asset)     Rp W (cost basis of shares sold)
  CREDIT: Realized PnL (income) Rp P (profit/loss)
```

### 6.2 Trade Ledger Schema

```sql
-- Trade ledger (extends existing orders table)
CREATE TABLE IF NOT EXISTS trade_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT UNIQUE NOT NULL,          -- Unique entry ID
    transaction_id TEXT NOT NULL,           -- Links to order
    date TEXT NOT NULL,                     -- Transaction date
    account TEXT NOT NULL,                  -- "trading", "cash", "fee", "tax"
    debit REAL DEFAULT 0,                   -- Debit amount
    credit REAL DEFAULT 0,                  -- Credit amount
    ticker TEXT,                            -- Related ticker (if any)
    description TEXT,                       -- Entry description
    balance_after REAL,                     -- Account balance after entry
    created_at TEXT DEFAULT (datetime('now'))
);

-- Account balances (running balances)
CREATE TABLE IF NOT EXISTS account_balances (
    account TEXT PRIMARY KEY,               -- "trading", "cash", "fee", "tax"
    balance REAL NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### 6.3 PnL Engine

```python
# portfolio/pnl_engine.py

class PnLEngine:
    """Compute realized and unrealized PnL."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def compute_realized_pnl(self, ticker: str, shares_sold: int,
                              sell_price: float, fees: float) -> dict:
        """Compute realized PnL for a sell transaction.

        Uses FIFO cost basis (see doc 25).
        """
        # Get cost basis from buy lots (FIFO)
        cost_basis = self._get_fifo_cost_basis(ticker, shares_sold)
        proceeds = sell_price * shares_sold - fees
        realized_pnl = proceeds - cost_basis
        return_pct = (realized_pnl / cost_basis) * 100 if cost_basis > 0 else 0

        return {
            "ticker": ticker,
            "shares_sold": shares_sold,
            "sell_price": sell_price,
            "cost_basis": cost_basis,
            "proceeds": proceeds,
            "fees": fees,
            "realized_pnl": realized_pnl,
            "return_pct": return_pct,
            "method": "FIFO",
        }

    def compute_unrealized_pnl(self, positions: list, current_prices: dict) -> dict:
        """Compute unrealized PnL for all open positions."""
        total_unrealized = 0
        details = []

        for pos in positions:
            ticker = pos["ticker"]
            qty = pos["quantity"]
            entry = pos["avg_entry_price"]
            current = current_prices.get(ticker, entry)

            market_value = qty * current
            cost_value = qty * entry
            unrealized = market_value - cost_value
            return_pct = (unrealized / cost_value) * 100 if cost_value > 0 else 0

            total_unrealized += unrealized
            details.append({
                "ticker": ticker,
                "quantity": qty,
                "avg_entry": entry,
                "current_price": current,
                "market_value": market_value,
                "cost_value": cost_value,
                "unrealized_pnl": unrealized,
                "return_pct": return_pct,
            })

        return {
            "total_unrealized_pnl": total_unrealized,
            "positions": details,
        }

    def compute_total_pnl(self, cash_balance: float, initial_capital: float,
                          current_prices: dict) -> dict:
        """Compute total PnL (realized + unrealized)."""
        positions = self.storage.get_all_open_positions()
        unrealized = self.compute_unrealized_pnl(positions, current_prices)

        # Realized PnL = current cash - initial capital + invested cost basis
        invested_cost = sum(p["quantity"] * p["avg_entry_price"] for p in positions)
        realized_pnl = (cash_balance + invested_cost) - initial_capital

        total_pnl = realized_pnl + unrealized["total_unrealized_pnl"]
        total_return_pct = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0

        return {
            "initial_capital": initial_capital,
            "current_cash": cash_balance,
            "invested_cost": invested_cost,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized["total_unrealized_pnl"],
            "total_pnl": total_pnl,
            "total_return_pct": total_return_pct,
            "position_details": unrealized["positions"],
        }

    def _get_fifo_cost_basis(self, ticker: str, shares: int) -> float:
        """Get cost basis using FIFO method."""
        lots = self.storage.get_buy_lots(ticker)  # Ordered by date ASC
        remaining = shares
        cost = 0.0

        for lot in lots:
            if remaining <= 0:
                break
            take = min(remaining, lot["remaining_shares"])
            cost += take * lot["price"]
            remaining -= take

        return cost
```

### 6.4 PnL Attribution

```python
def pnl_attribution(pnl_result: dict, period_days: int = 30) -> dict:
    """Attribute PnL to sources."""
    return {
        "total_pnl": pnl_result["total_pnl"],
        "attribution": {
            "capital_gains": sum(
                p["unrealized_pnl"] + p.get("realized_pnl", 0)
                for p in pnl_result["position_details"]
            ),
            "dividends": 0,  # From cash flow entries
            "fees_cost": 0,  # Negative: total fees paid
            "tax_cost": 0,   # Negative: total tax paid
            "cash_drag": 0,  # Opportunity cost of cash
        },
        "period_days": period_days,
        "pnl_per_day": pnl_result["total_pnl"] / period_days if period_days > 0 else 0,
    }
```

### 6.5 NAV Calculation

```python
def compute_nav(cash_balance: float, positions: list, current_prices: dict) -> dict:
    """Compute Net Asset Value.

    NAV = Cash + Market Value of All Positions
    """
    market_value = sum(
        p["quantity"] * current_prices.get(p["ticker"], p["avg_entry_price"])
        for p in positions
    )
    nav = cash_balance + market_value

    return {
        "nav": nav,
        "cash": cash_balance,
        "market_value": market_value,
        "cash_pct": cash_balance / nav * 100 if nav > 0 else 0,
        "invested_pct": market_value / nav * 100 if nav > 0 else 0,
        "position_count": len(positions),
    }
```

### 6.6 Reconciliation

```python
def reconcile_cash(internal_balance: float, broker_balance: float) -> dict:
    """Reconcile internal cash tracking with broker."""
    diff = internal_balance - broker_balance
    tolerance = 1000.0  # Rp 1,000 tolerance for rounding

    return {
        "internal_balance": internal_balance,
        "broker_balance": broker_balance,
        "difference": diff,
        "within_tolerance": abs(diff) <= tolerance,
        "status": "matched" if abs(diff) <= tolerance else "mismatch",
        "action": "none" if abs(diff) <= tolerance else "investigate",
    }

def reconcile_positions(internal_positions: list, broker_positions: list) -> dict:
    """Reconcile internal position tracking with broker."""
    internal_map = {p["ticker"]: p for p in internal_positions}
    broker_map = {p["ticker"]: p for p in broker_positions}

    mismatches = []
    all_tickers = set(internal_map.keys()) | set(broker_map.keys())

    for ticker in all_tickers:
        internal = internal_map.get(ticker)
        broker = broker_map.get(ticker)

        if internal and not broker:
            mismatches.append({"ticker": ticker, "issue": "internal_only",
                              "internal_qty": internal["quantity"]})
        elif broker and not internal:
            mismatches.append({"ticker": ticker, "issue": "broker_only",
                              "broker_qty": broker["shares"]})
        elif internal and broker:
            qty_diff = internal["quantity"] - broker["shares"]
            if abs(qty_diff) > 0:
                mismatches.append({"ticker": ticker, "issue": "quantity_mismatch",
                                  "internal_qty": internal["quantity"],
                                  "broker_qty": broker["shares"],
                                  "difference": qty_diff})

    return {
        "total_tickers": len(all_tickers),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "matched" if not mismatches else "mismatch",
    }
```

---

## 7. Konfigurasi & Parameter Management

### 7.1 Financial Parameters

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| **Total Capital** | `TRADING_CAPITAL` | 100,000,000 | Total modal awal trading |
| **Risk per Trade** | `RISK_PER_TRADE` | 0.01 (1%) | Maks risk per transaksi |
| **Max Position Size** | `MAX_POSITION_PCT` | 0.10 (10%) | Maks % capital per position |
| **Max Sector Exposure** | `MAX_SECTOR_PCT` | 0.30 (30%) | Maks % per sektor |
| **Min Cash Buffer** | `MIN_CASH_BUFFER` | 0 | Minimum cash buffer |
| **Max Invested Pct** | `MAX_INVESTED_PCT` | 0.80 (80%) | Maks % terinvestasi |
| **Daily Loss Limit** | `DAILY_LOSS_LIMIT` | 1,000,000 | Maks loss harian |
| **Exit Conviction Threshold** | `EXIT_CONVICTION_THRESHOLD` | 40 | Conviction minimum untuk hold |
| **Auto Trade** | `AUTO_TRADE_ENABLED` | false | Enable auto execution |
| **Trading Mode** | `TRADING_MODE` | paper | paper or real |
| **Broker Fee Buy** | `BROKER_FEE_BUY` | 0.0015 | 0.15% |
| **Broker Fee Sell** | `BROKER_FEE_SELL` | 0.0025 | 0.25% |
| **Sales Tax** | `SALES_TAX` | 0.001 | 0.1% PPh final |
| **IDX Lot Size** | `IDX_LOT_SIZE` | 100 | Shares per lot |

### 7.2 Set Everything Flow

```python
# config/financial_config.py

class FinancialConfig:
    """Centralized financial configuration."""

    def __init__(self):
        self.trading_capital = float(os.getenv("TRADING_CAPITAL", "100000000"))
        self.risk_per_trade = float(os.getenv("RISK_PER_TRADE", "0.01"))
        self.max_position_pct = float(os.getenv("MAX_POSITION_PCT", "0.10"))
        self.max_sector_pct = float(os.getenv("MAX_SECTOR_PCT", "0.30"))
        self.min_cash_buffer = float(os.getenv("MIN_CASH_BUFFER", "0"))
        self.max_invested_pct = float(os.getenv("MAX_INVESTED_PCT", "0.80"))
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT", "1000000"))
        self.exit_conviction_threshold = int(os.getenv("EXIT_CONVICTION_THRESHOLD", "40"))
        self.auto_trade_enabled = os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true"
        self.trading_mode = os.getenv("TRADING_MODE", "paper")
        self.idx_lot_size = int(os.getenv("IDX_LOT_SIZE", "100"))

    def validate(self) -> list[str]:
        """Validate configuration values."""
        errors = []
        if self.trading_capital <= 0:
            errors.append("TRADING_CAPITAL must be positive")
        if not 0 < self.risk_per_trade <= 0.05:
            errors.append("RISK_PER_TRADE must be between 0 and 5%")
        if not 0 < self.max_position_pct <= 0.25:
            errors.append("MAX_POSITION_PCT must be between 0 and 25%")
        if not 0 < self.max_invested_pct <= 1.0:
            errors.append("MAX_INVESTED_PCT must be between 0 and 100%")
        if self.daily_loss_limit <= 0:
            errors.append("DAILY_LOSS_LIMIT must be positive")
        return errors

    def to_dict(self) -> dict:
        return {
            "trading_capital": self.trading_capital,
            "risk_per_trade": self.risk_per_trade,
            "max_position_pct": self.max_position_pct,
            "max_sector_pct": self.max_sector_pct,
            "min_cash_buffer": self.min_cash_buffer,
            "max_invested_pct": self.max_invested_pct,
            "daily_loss_limit": self.daily_loss_limit,
            "exit_conviction_threshold": self.exit_conviction_threshold,
            "auto_trade_enabled": self.auto_trade_enabled,
            "trading_mode": self.trading_mode,
            "idx_lot_size": self.idx_lot_size,
        }
```

### 7.3 Runtime Configuration Update

```python
# Sistem harus bisa update config tanpa restart
def update_financial_config(key: str, value: str) -> dict:
    """Update financial config at runtime (no restart needed)."""
    os.environ[key.upper()] = value

    # Re-validate
    config = FinancialConfig()
    errors = config.validate()

    return {
        "updated": key,
        "value": value,
        "valid": len(errors) == 0,
        "errors": errors,
    }
```

---

## 8. Implementasi Kode

### 8.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| **Capital Calculator** | `risk/capital_calculator.py` | ❌ New | Hitung total modal per transaksi |
| **Buying Power Checker** | `risk/buying_power.py` | ❌ New | Cek ketersediaan modal |
| **Cash Flow Manager** | `portfolio/cash_flow.py` | ❌ New | Track cash in/out |
| **Capital Allocator** | `portfolio/capital_allocator.py` | ❌ New | Alokasi modal across positions |
| **PnL Engine** | `portfolio/pnl_engine.py` | ❌ New | Realized/unrealized PnL |
| **Trade Ledger** | `data/storage.py` (extend) | ❌ New | Double-entry ledger |
| **Reconciliation** | `portfolio/reconciliation.py` | ❌ New | Broker vs internal sync |
| **Financial Config** | `config/financial_config.py` | ❌ New | Centralized config |
| **Screen-to-Execute** | `pipeline/screen_to_execute.py` | ❌ New | Unified pipeline |

### 8.2 Existing Code to Leverage

| Existing | File | What to Reuse |
|----------|------|---------------|
| `BrokerAccount` | `execution/broker_adapter.py:80` | `cash_balance`, `buying_power` fields |
| `get_cash_balance()` | `execution/broker_adapter.py:136` | Interface for broker cash query |
| Paper cash tracking | `execution/paper_execution.py:38` | `_paper_cash` pattern |
| Position sizing | `risk/engine.py:55` | Risk-based sizing logic |
| Pre-trade checklist | `risk/pre_trade_checklist.py:134` | `check_position_size()` |
| Portfolio exposure | `portfolio/engine.py:34` | `get_exposure()` with cash/invested |
| Cost model | `risk/costs.py` | Fee calculation |
| NAV calculation | `pustaka/26-post-trade-settlement-rekonsiliasi.md:456` | NAV formula |
| FIFO cost basis | `pustaka/25-pajak-akuntansi-trading.md:349` | Cost basis tracking |

### 8.3 Database Schema Extension

```sql
-- Cash flow entries (new table)
CREATE TABLE IF NOT EXISTS cash_flow_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    type TEXT NOT NULL,           -- deposit, withdrawal, buy_cost, sell_proceeds, dividend, fee, tax
    direction TEXT NOT NULL,      -- IN or OUT
    amount REAL NOT NULL,
    ticker TEXT,
    order_id TEXT,
    description TEXT,
    balance_after REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Account balances (new table)
CREATE TABLE IF NOT EXISTS account_balances (
    account TEXT PRIMARY KEY,     -- trading, cash, fees, tax
    balance REAL NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Trade ledger (new table, double-entry)
CREATE TABLE IF NOT EXISTS trade_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT UNIQUE NOT NULL,
    transaction_id TEXT NOT NULL,
    date TEXT NOT NULL,
    account TEXT NOT NULL,
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0,
    ticker TEXT,
    description TEXT,
    balance_after REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Capital allocation log (new table)
CREATE TABLE IF NOT EXISTS capital_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    method TEXT NOT NULL,         -- conviction, equal_weight, hrp
    weight REAL NOT NULL,
    capital_allocated REAL NOT NULL,
    conviction INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **07** (Manajemen Risiko) | Position sizing → capital calculator extends dengan fees |
| **16** (Strategi Mencari Keuntungan) | Capital allocation by capital size |
| **21** (Portfolio Optimization) | HRP allocation → capital allocator |
| **25** (Pajak & Akuntansi) | Tax accounting → trade ledger extends |
| **26** (Post-Trade Settlement) | Settlement → cash flow manager tracks T+2 |
| **31** (Risk Management Lanjutan) | VaR/CVaR → capital efficiency metrics |
| **39** (Screening AI/ML) | Screener → screen-to-execute pipeline |
| **40** (OMS/EMS) | Buying power check → pre-trade risk |
| **47** (Operational Contract) | T-030 (decision), T-040 (execution) → this doc unifies |
| **52** (TCA) | Transaction cost → capital calculator includes TCA |
| **57** (User Onboarding) | Risk profile → capital allocation config |

---

## 10. Checklist Implementasi

### Capital Calculator
- [ ] `calculate_capital_needed()` function
- [ ] Include all fees (broker, tax, SEBI, KPEI, BEI)
- [ ] `position_sizing_to_capital()` integration
- [ ] Unit tests

### Buying Power Checker
- [ ] `check_buying_power()` function
- [ ] Broker adapter integration (`get_account()`)
- [ ] Reserved cash tracking (pending orders)
- [ ] Paper trading integration
- [ ] Unit tests

### Cash Flow Manager
- [ ] `CashFlowManager` class
- [ ] `record_buy()`, `record_sell()`, `record_dividend()`
- [ ] `deposit()`, `withdraw()`
- [ ] Cash flow summary report
- [ ] Database persistence (`cash_flow_entries` table)
- [ ] Unit tests

### Capital Allocator
- [ ] `allocate_by_conviction()` method
- [ ] `allocate_equal_weight()` method
- [ ] HRP integration
- [ ] Max position / max sector limits
- [ ] Cash buffer enforcement
- [ ] Unit tests

### PnL Engine
- [ ] `compute_realized_pnl()` (FIFO)
- [ ] `compute_unrealized_pnl()`
- [ ] `compute_total_pnl()`
- [ ] PnL attribution
- [ ] NAV calculation
- [ ] Unit tests

### Trade Ledger
- [ ] Double-entry schema
- [ ] `record_transaction()` (auto double-entry)
- [ ] Account balance tracking
- [ ] Reconciliation (broker vs internal)
- [ ] Unit tests

### Screen-to-Execute Pipeline
- [ ] `screen_to_execute_pipeline()` function
- [ ] Integration with screener, decision, risk, capital, buying power, execution
- [ ] Logging at each stage
- [ ] Skip/queue logic for insufficient capital
- [ ] Integration tests

### Configuration
- [ ] `FinancialConfig` class
- [ ] Validation
- [ ] Runtime update (no restart)
- [ ] API endpoint for config update
- [ ] Unit tests

---

## Referensi

1. `src/trading_system/execution/automated.py` — Auto-trade execution & condition check
2. `src/trading_system/risk/costs.py` — CostModel (fees, slippage, tax)
3. `src/trading_system/risk/engine.py` — Risk engine (position sizing, VaR)
4. `src/trading_system/portfolio/engine.py` — Portfolio engine (PnL, NAV)
5. `src/trading_system/config.py` — TRADING_CAPITAL, RISK_PER_TRADE
6. `pustaka/07-manajemen-risiko.md` — Risk management fundamentals
7. `pustaka/25-pajak-akuntansi-trading.md` — PPh final, cost basis, SPT
8. `pustaka/40-oms-ems-architecture.md` — OMS/EMS order lifecycle
9. `pustaka/83-advisory-system-screening-to-recommendation.md` — Advisory pipeline
10. `pustaka/85-backtest-to-live-gap-prevention.md` — Realistic cost modeling

---

## 16. Implementasi: Pre-Trade Checklist

> **Sumber:** `src/trading_system/risk/pre_trade_checklist.py` (396 baris)

Sistem `trading-system` mengimplementasikan 9 automated pre-trade checks sebelum eksekusi order.

| 5W1H | Detail |
|------|--------|
| **What** | Pre-Trade Checklist: 9 gate (fundamental, liquidity, position size, sector, free float, R/R, behavioral, gorengan, regime) |
| **Why** | Trading discipline — otomatisasi checks yang seharusnya dilakukan manual sebelum setiap order |
| **When** | Sebelum setiap order placement (buy signal dari decision engine) |
| **Where** | Risk layer: pre_trade_checklist.py → execution engine gate |
| **Who** | Dipanggil oleh execution engine sebelum order placement |
| **How** | 9 checks berurutan, any FAIL = block order, WARN = tampilkan peringatan |

### 16.1 Checklist Items

| # | Check | Threshold | Status |
|---|-------|-----------|--------|
| 1 | Fundamental score | ≥ 40 | PASS/FAIL/WARN |
| 2 | Liquidity (volume) | ≥ 100K shares/day | PASS/FAIL |
| 3 | Position sizing | Risk ≤ 2% capital | PASS/FAIL |
| 4 | Sector concentration | ≤ 30% per sector | PASS/FAIL/WARN |
| 5 | Free float | ≥ 15% (reformasi 2026) | PASS/FAIL/WARN |
| 6 | Risk/Reward ratio | ≥ 1:2 | PASS/FAIL/WARN |
| 7 | Behavioral risk | Score < 70 | PASS/FAIL/WARN |
| 8 | Gorengan detection | Not gorengan | PASS/FAIL |
| 9 | Market regime | Not crisis/unknown | PASS/FAIL |

### 16.2 Output

```python
@dataclass
class PreTradeReport:
    ticker: str
    checks: list[ChecklistResult]
    can_proceed: bool       # True jika tidak ada FAIL

    @property
    def fail_count(self) -> int
    @property
    def warn_count(self) -> int
    @property
    def pass_count(self) -> int
```

### 16.3 Integrasi

- **Execution gate:** `can_proceed = False` → block order
- **Warning UI:** Tampilkan WARN items sebagai peringatan
- **Audit log:** Simpan hasil checklist untuk setiap order

---

## 17. Implementasi: Profit Tracker & Strategy Selector

> **Sumber:** `src/trading_system/portfolio/profit_tracker.py` (202 baris), `src/trading_system/portfolio/strategy_selector.py` (184 baris)

### 17.1 Profit Tracker

| 5W1H | Detail |
|------|--------|
| **What** | Profit Tracker: breakdown return ke capital gain + dividend income + ROI + yield on cost |
| **Why** | Investor perlu tahu sumber return — apakah dari price appreciation atau dividend |
| **When** | Portfolio review dan reporting |
| **Where** | Portfolio layer: profit_tracker.py → portfolio engine + reporting |
| **Who** | Dipanggil oleh portfolio engine dan API reporting |
| **How** | Compute (current_price - avg_cost) × shares + sum dividends, return breakdown |

Memecah return portofolio berdasarkan sumber:

| Komponen | Formula |
|----------|---------|
| Capital gain | `(current_price - avg_cost) × shares` |
| Dividend income | Sum of dividends received |
| Total return | Capital gain + dividends |
| ROI | `Total return / cost_basis` |
| Yield on cost | `Dividends / cost_basis` |

### 17.2 Strategy Selector

Pemilihan strategi berdasarkan profil investor:

| Modal | Risk Tolerance | Strategi | Expected Return |
|-------|---------------|----------|-----------------|
| < Rp 1jt | Any | DCA Blue Chip | 8-12% p.a. |
| Rp 1-10jt | Low-Moderate | Value + DCA | 10-15% p.a. |
| Rp 10-100jt | Moderate | Multi-strategy | 12-18% p.a. |
| > Rp 100jt | High | Active + SW | 15-25% p.a. |

```python
@dataclass
class InvestorProfile:
    capital: float
    risk_tolerance: str    # low, moderate, high
    hours_per_week: float  # waktu tersedia
    timeframe: str         # short, medium, long
    goal: str              # growth, income, stability
    age: int | None
    has_emergency_fund: bool
    uses_cold_money: bool
```

---

> **Catatan:** "Trading tanpa manajemen keuangan adalah judi." Sistem yang tidak tahu berapa modalnya, tidak tahu apakah modal cukup, dan tidak tahu apakah profit atau loss — bukan sistem trading, melainkan sistem spekulasi. Financial management adalah fondasi yang menentukan apakah sistem survive atau blow up. Implementasi: `src/trading_system/risk/pre_trade_checklist.py`, `src/trading_system/portfolio/profit_tracker.py`, `src/trading_system/portfolio/strategy_selector.py`.
