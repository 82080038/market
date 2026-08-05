# Fractional Shares & Micro-Investing untuk Aplikasi Ritel IDX

> **Dokumen 64** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Implementasi fractional shares untuk aplikasi ritel IDX — mekanisme sub-lot accounting, regulatory framework, broker pooling model, corporate action handling, dan reconciliation.
>
> **Konteks:** BBCA Rp 8,000+/lembar = Rp 800,000+/lot. Investor ritel dengan modal kecil tidak bisa beli blue chip. Fractional shares solusi untuk inklusi finansial, tapi IDX belum mendukung secara native — perlu struktur perantara (broker pooling).

---

## Daftar Isi

1. [Problem Statement](#1-problem-statement)
2. [Regulatory Framework di IDX](#2-regulatory-framework-di-idx)
3. [Broker Pooling Model](#3-broker-pooling-model)
4. [Sub-Lot Accounting](#4-sub-lot-accounting)
5. [Corporate Action Handling](#5-corporate-action-handling)
6. [Reconciliation](#6-reconciliation)
7. [Alternatif: Reksadana Fractional](#7-alternatif-reksadana-fractional)
8. [Implementasi](#8-implementasi)
9. [Adopsi dari Codebase Existing](#9-adopsi-dari-codebase-existing)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Problem Statement

### 1.1 Realitas Harga Saham IDX

| Ticker | Harga/Lembar | 1 Lot (100) | Affordability |
|--------|-------------|-------------|---------------|
| BBCA | Rp 8,450 | Rp 845,000 | ❌ Mahal untuk pemula |
| BBRI | Rp 4,200 | Rp 420,000 | ⚠️ Cukup mahal |
| BMRI | Rp 6,100 | Rp 610,000 | ❌ Mahal |
| ASII | Rp 5,800 | Rp 580,000 | ❌ Mahal |
| TLKM | Rp 3,200 | Rp 320,000 | ⚠️ Moderate |
| UNVR | Rp 4,100 | Rp 410,000 | ⚠️ Cukup mahal |
| ICBP | Rp 12,500 | Rp 1,250,000 | ❌ Sangat mahal |
| GOTO | Rp 65 | Rp 6,500 | ✅ Terjangkau |

### 1.2 Dampak

- Investor dengan modal Rp 100K tidak bisa beli BBCA, BBRI, BMRI, ASII
- Investor terpaksa beli saham gorengan (harga murah, tapi risiko tinggi)
- Blue chip = saham yang paling aman untuk pemula, justru paling tidak terjangkau
- Inklusi finansial terhambat: "investasi butuh modal besar"

### 1.3 Solusi: Fractional Shares

User beli **0.1 lot BBCA** (10 lembar) = Rp 84,500. Broker membeli 1 lot penuh, mencatat 10 lembar milik user A, 90 lembar milik broker (pooling).

---

## 2. Regulatory Framework di IDX

### 2.1 Status Saat Ini

| Aspek | Status | Catatan |
|-------|--------|---------|
| **Fractional shares di IDX** | ❌ Tidak didukung | IDX menggunakan lot 100 lembar |
| **KSEI KSEI** | ❌ Tidak support sub-lot | KSEI record per lot penuh |
| **Broker pooling** | ⚠️ Grey area | Tidak dilarang, tapi tidak diatur eksplisit |
| **Reksadana fractional** | ✅ Didukung | Reksadana bisa beli fraksi |
| **Digital fractional** | ⚠️ Belum ada | OJK belum regulate crypto-style fractional |

### 2.2 Tantangan Regulatory

| Tantangan | Dampak | Mitigasi |
|-----------|--------|----------|
| **Street name holding** | Broker hold saham atas nama sendiri untuk pooling | Butuh agreement yang jelas antara broker dan user |
| **Beneficial ownership** | User adalah beneficial owner, broker adalah legal owner | Butuh internal ledger yang auditable |
| **Voting rights** | User fractional berhak vote? | Proxy voting via broker |
| **Dividend distribution** | Dividen harus dibagi proporsional | Broker distribute setelah terima dari KSEI |
| **Insolvency risk** | Jika broker bangkrut, fractional holder unprotected | Reksadana atau SPV structure lebih aman |

### 2.3 Rekomendasi: Hybrid Model

```
┌──────────────────────────────────────────────────────────────┐
│              FRACTIONAL SHARES HYBRID MODEL                  │
│                                                              │
│  Tier 1: Broker Pooling (Saham Blue Chip)                    │
│  ├── Broker beli 1 lot penuh di IDX                          │
│  ├── Internal ledger track fractional ownership              │
│  ├── User beli minimum 1 lembar (Rp 8,450 untuk BBCA)       │
│  └── Broker sebagai street name holder                       │
│                                                              │
│  Tier 2: Reksadana Fractional (All Saham)                    │
│  ├── Partner dengan manajer investasi                        │
│  ├── User beli unit reksadana (fractional by design)         │
│  ├── Minimum Rp 10,000                                       │
│  └── NAV dihitung harian                                     │
│                                                              │
│  Tier 3: Digital Native (Future)                             │
│  ├── Tokenized fractional (blockchain-based)                 │
│  ├── Smart contract untuk distribution                       │
│  └── Menunggu regulasi OJK                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Broker Pooling Model

### 3.1 Arsitektur

```
┌──────────────────────────────────────────────────────────────┐
│                   BROKER POOLING SYSTEM                       │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              ORDER AGGREGATION                        │   │
│  │  User A: BUY 10 BBCA ──┐                             │   │
│  │  User B: BUY 25 BBCA ──┼──→ Aggregate: BUY 100 BBCA │   │
│  │  User C: BUY 50 BBCA ──┘    (1 lot = 100 lembar)     │   │
│  │  Broker Pool: 15 BBCA (remaining)                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              IDX EXECUTION                           │   │
│  │  Broker submit: BUY 1 lot BBCA @ market              │   │
│  │  KSEI record: 100 lembar di account broker           │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              INTERNAL LEDGER                         │   │
│  │  User A: 10 lembar (beneficial owner)                │   │
│  │  User B: 25 lembar (beneficial owner)                │   │
│  │  User C: 50 lembar (beneficial owner)                │   │
│  │  Broker Pool: 15 lembar (house inventory)            │   │
│  │  Total: 100 lembar (match KSEI)                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Implementasi

```python
class FractionalOrderAggregator:
    """Aggregate fractional orders into full lots for IDX execution."""

    LOT_SIZE = 100  # IDX lot size

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.pending_orders: dict[str, list[dict]] = {}  # ticker → [fractional orders]

    def submit_fractional_order(self, user_id: str, ticker: str,
                                 quantity: int, side: str,
                                 price: float) -> dict:
        """Submit fractional order (quantity < 100)."""
        if quantity < 1:
            return {"status": "error", "message": "Minimum 1 lembar"}

        if quantity % 100 == 0:
            # Full lot — execute directly
            return self._execute_full_lot(user_id, ticker, quantity, side, price)

        # Fractional — add to aggregation queue
        order_id = str(uuid.uuid4())
        self.pending_orders.setdefault(ticker, []).append({
            "order_id": order_id,
            "user_id": user_id,
            "ticker": ticker,
            "quantity": quantity,
            "side": side,
            "price": price,
            "timestamp": datetime.now(UTC),
        })

        # Try to aggregate into full lot
        result = self._try_aggregate(ticker, side, price)
        return {
            "status": "queued",
            "order_id": order_id,
            "message": f"Order queued for aggregation. Will execute when full lot reached.",
            "aggregation_result": result,
        }

    def _try_aggregate(self, ticker: str, side: str, price: float) -> dict | None:
        """Try to aggregate pending fractional orders into full lots."""
        orders = self.pending_orders.get(ticker, [])
        same_side = [o for o in orders if o["side"] == side and o["price"] == price]

        total_qty = sum(o["quantity"] for o in same_side)
        full_lots = total_qty // self.LOT_SIZE

        if full_lots > 0:
            # Execute full lots on IDX
            execute_qty = full_lots * self.LOT_SIZE
            remaining_qty = total_qty - execute_qty

            # Select orders to fill (FIFO)
            filled_orders = []
            accumulated = 0
            for order in same_side:
                if accumulated >= execute_qty:
                    break
                fill_qty = min(order["quantity"], execute_qty - accumulated)
                filled_orders.append({**order, "fill_qty": fill_qty})
                accumulated += fill_qty

            # Submit to IDX
            idx_order = self._submit_to_idx(ticker, execute_qty, side, price)

            # Update internal ledger
            for fo in filled_orders:
                self.storage.update_fractional_position(
                    user_id=fo["user_id"],
                    ticker=ticker,
                    quantity=fo["fill_qty"],
                    side=side,
                    idx_order_id=idx_order["order_id"],
                )

            # Remove filled orders from queue
            remaining_orders = [o for o in same_side if o not in filled_orders]
            self.pending_orders[ticker] = remaining_orders

            return {
                "executed_lots": full_lots,
                "executed_qty": execute_qty,
                "filled_orders": len(filled_orders),
                "idx_order_id": idx_order["order_id"],
            }

        return None

    def _execute_full_lot(self, user_id: str, ticker: str, quantity: int,
                           side: str, price: float) -> dict:
        """Execute full lot order directly on IDX."""
        idx_order = self._submit_to_idx(ticker, quantity, side, price)
        self.storage.update_fractional_position(
            user_id=user_id, ticker=ticker,
            quantity=quantity, side=side,
            idx_order_id=idx_order["order_id"],
        )
        return {"status": "executed", "order_id": idx_order["order_id"]}
```

---

## 4. Sub-Lot Accounting

### 4.1 Internal Ledger

```python
class FractionalLedger:
    """Internal ledger for fractional share positions."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def record_position(self, user_id: str, ticker: str, quantity: int,
                         avg_price: float, idx_order_id: str):
        """Record fractional position in internal ledger."""
        self.storage.execute(
            """INSERT INTO fractional_positions
               (user_id, ticker, quantity, avg_price, idx_order_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, ticker)
               DO UPDATE SET quantity = quantity + ?,
                             avg_price = ?,
                             updated_at = ?""",
            (user_id, ticker, quantity, avg_price, idx_order_id,
             datetime.now(UTC), quantity, avg_price, datetime.now(UTC))
        )

    def get_position(self, user_id: str, ticker: str) -> dict:
        """Get user's fractional position for a ticker."""
        row = self.storage.query_one(
            "SELECT * FROM fractional_positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker)
        )
        if not row:
            return {"quantity": 0, "avg_price": 0}
        return dict(row)

    def get_all_positions(self, user_id: str) -> list[dict]:
        """Get all fractional positions for a user."""
        rows = self.storage.query(
            "SELECT * FROM fractional_positions WHERE user_id = ? AND quantity > 0",
            (user_id,)
        )
        return [dict(r) for r in rows]

    def get_pool_position(self, ticker: str) -> dict:
        """Get broker's pool (house) position for a ticker."""
        row = self.storage.query_one(
            """SELECT SUM(quantity) as total_user_qty
               FROM fractional_positions WHERE ticker = ?""",
            (ticker,)
        )
        ksei_qty = self.storage.get_ksei_position(ticker)
        user_qty = row["total_user_qty"] or 0
        pool_qty = ksei_qty - user_qty

        return {
            "ticker": ticker,
            "ksei_total": ksei_qty,
            "user_total": user_qty,
            "pool_quantity": pool_qty,
        }
```

### 4.2 Database Schema

```sql
-- Fractional positions (internal ledger)
CREATE TABLE fractional_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,          -- Can be fractional (e.g., 10.5 lembar)
    avg_price REAL NOT NULL,
    idx_order_id TEXT,               -- Reference to IDX order
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, ticker),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Broker pool positions (house inventory)
CREATE TABLE broker_pool_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    ksei_quantity INTEGER NOT NULL,   -- Actual quantity at KSEI
    user_quantity REAL NOT NULL,      -- Sum of all user fractional positions
    pool_quantity REAL NOT NULL,      -- ksei - user (broker's own inventory)
    last_reconciled DATETIME,
    UNIQUE(ticker)
);

-- Fractional order queue
CREATE TABLE fractional_order_queue (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    status TEXT DEFAULT 'queued',     -- queued, aggregated, executed, cancelled
    idx_order_id TEXT,
    queued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    executed_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 5. Corporate Action Handling

### 5.1 Stock Split

```python
class FractionalCorporateActionHandler:
    """Handle corporate actions for fractional positions."""

    def process_stock_split(self, ticker: str, ratio: float):
        """Process stock split for all fractional holders.
        
        Example: BBCA 1:2 split → 10 lembar → 20 lembar, price halved
        """
        positions = self.storage.get_all_fractional_positions(ticker)
        for pos in positions:
            new_qty = pos["quantity"] * ratio
            new_avg_price = pos["avg_price"] / ratio
            self.storage.update_fractional_position(
                user_id=pos["user_id"],
                ticker=ticker,
                quantity=new_qty,
                avg_price=new_avg_price,
                idx_order_id=pos["idx_order_id"],
            )

        # Update pool position
        pool = self.storage.get_pool_position(ticker)
        self.storage.update_pool_position(
            ticker=ticker,
            ksei_quantity=int(pool["ksei_quantity"] * ratio),
        )
```

### 5.2 Dividend Distribution

```python
    def process_dividend(self, ticker: str, dividend_per_share: float):
        """Distribute dividend to fractional holders proportionally."""
        positions = self.storage.get_all_fractional_positions(ticker)
        for pos in positions:
            dividend_amount = pos["quantity"] * dividend_per_share
            # Credit to user's cash account
            self.storage.credit_cash(
                user_id=pos["user_id"],
                amount=dividend_amount,
                description=f"Dividend {ticker} ({pos['quantity']} lembar @ Rp {dividend_per_share})",
            )
            # Record for tax
            self.storage.record_dividend(
                user_id=pos["user_id"],
                ticker=ticker,
                quantity=pos["quantity"],
                dividend_per_share=dividend_per_share,
                total_dividend=dividend_amount,
                tax_withheld=dividend_amount * 0.10,  # PPh 10%
            )
```

### 5.3 Rights Issue

```python
    def process_rights_issue(self, ticker: str, ratio: float,
                              subscription_price: float):
        """Process rights issue for fractional holders.
        
        Example: 1:5 → setiap 5 lembar berhak beli 1 lembar baru
        """
        positions = self.storage.get_all_fractional_positions(ticker)
        for pos in positions:
            rights = pos["quantity"] / ratio  # e.g., 10 / 5 = 2 rights
            # Notify user of their rights
            self.storage.create_notification(
                user_id=pos["user_id"],
                type="rights_issue",
                title=f"Hak Anam Rights {ticker}",
                body=f"Anda berhak membeli {rights:.2f} lembar {ticker} @ Rp {subscription_price:,.0f}",
                deadline=date.today() + timedelta(days=14),
            )
```

---

## 6. Reconciliation

### 6.1 Daily Reconciliation

```python
class FractionalReconciliation:
    """Reconcile internal ledger vs KSEI position."""

    def reconcile_ticker(self, ticker: str) -> dict:
        """Reconcile fractional positions for a ticker."""
        # Get KSEI position (actual shares at depository)
        ksei_qty = self.storage.get_ksei_position(ticker)

        # Get sum of all user fractional positions
        user_total = self.storage.get_total_user_fractional(ticker)

        # Get pool position
        pool_qty = ksei_qty - user_total

        # Check for discrepancies
        discrepancy = abs(pool_qty) if pool_qty < 0 else 0

        result = {
            "ticker": ticker,
            "ksei_quantity": ksei_qty,
            "user_total": user_total,
            "expected_pool": ksei_qty - user_total,
            "actual_pool": self.storage.get_pool_quantity(ticker),
            "discrepancy": discrepancy,
            "status": "balanced" if discrepancy < 0.01 else "imbalance",
        }

        if discrepancy > 0.01:
            # Alert: internal ledger doesn't match KSEI
            self._alert_reconciliation_failure(result)

        return result

    def reconcile_all(self) -> list[dict]:
        """Reconcile all tickers with fractional positions."""
        tickers = self.storage.get_tickers_with_fractional()
        return [self.reconcile_ticker(t) for t in tickers]
```

---

## 7. Alternatif: Reksadana Fractional

### 7.1 Kenapa Reksadana Lebih Mudah?

| Aspek | Broker Pooling | Reksadana |
|-------|----------------|-----------|
| **Regulatory** | Grey area | ✅ Clear (POJK 19/2015) |
| **Fractional by design** | Perlu internal ledger | ✅ Native (unit reksadana) |
| **Minimum investasi** | Rp 1 lembar | ✅ Rp 10,000 |
| **Corporate action** | Manual handling | ✅ MI handle |
| **Dividend** | Manual distribute | ✅ MI distribute |
| **Custody** | Broker hold | ✅ KSEI/Bank Kustodian |
| **Fee** | Broker fee | Management fee ~1-2%/tahun |

### 7.2 Implementasi Reksadana Integration

```python
class ReksadanaFractionalService:
    """Fractional investing via reksadana."""

    def buy(self, user_id: str, product_code: str, amount: float) -> dict:
        """Buy reksadana with any amount (min Rp 10,000)."""
        if amount < 10_000:
            return {"status": "error", "message": "Minimum Rp 10,000"}

        # Get current NAV
        nav = self.storage.get_reksadana_nav(product_code)
        if not nav:
            return {"status": "error", "message": "NAV not available"}

        # Compute units
        units = amount / nav

        # Submit to MI (Manajer Investasi)
        order = self.mi_api.submit_buy(
            product_code=product_code,
            amount=amount,
            user_id=user_id,
        )

        return {
            "status": "submitted",
            "product_code": product_code,
            "amount": amount,
            "nav": nav,
            "units": units,
            "order_id": order["order_id"],
        }
```

---

## 8. Implementasi

### 8.1 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/fractional/order` | POST | Submit fractional order |
| `/api/fractional/positions` | GET | Get user fractional positions |
| `/api/fractional/positions/{ticker}` | GET | Get specific position |
| `/api/fractional/pool/{ticker}` | GET | Get broker pool position (admin) |
| `/api/fractional/reconcile` | POST | Trigger reconciliation (admin) |
| `/api/fractional/queue` | GET | View aggregation queue (admin) |
| `/api/reksadana/buy` | POST | Buy reksadana (fractional) |
| `/api/reksadana/sell` | POST | Sell reksadana |
| `/api/reksadana/portfolio` | GET | Get reksadana portfolio |
| `/api/reksadana/products` | GET | List available reksadana |

---

## 9. Adopsi dari Codebase Existing

| Module Existing | Modifikasi |
|----------------|-----------|
| `execution/automated.py` | Tambah fractional order aggregation |
| `data/storage.py` | Tambah fractional tables |
| `portfolio/engine.py` | Include fractional positions |
| `corporate/actions.py` | Handle fractional corporate actions |
| `api/app.py` | Tambah fractional endpoints |

**New modules:**
- `fractional/aggregator.py` — Order aggregation
- `fractional/ledger.py` — Sub-lot accounting
- `fractional/reconciliation.py` — Ledger vs KSEI reconciliation
- `fractional/corporate_actions.py` — Corporate action handling
- `fractional/reksadana.py` — Reksadana fractional service

---

## 10. Checklist Implementasi

### Phase 1: Broker Pooling (4-6 minggu)

- [ ] Database schema: fractional_positions, broker_pool, order_queue
- [ ] `FractionalOrderAggregator` (order aggregation)
- [ ] `FractionalLedger` (sub-lot accounting)
- [ ] IDX execution integration (full lot submission)
- [ ] API: fractional order + positions

### Phase 2: Corporate Actions (3-4 minggu)

- [ ] Stock split handler
- [ ] Dividend distribution
- [ ] Rights issue handling
- [ ] Notification for fractional holders

### Phase 3: Reconciliation (2-3 minggu)

- [ ] `FractionalReconciliation` (daily)
- [ ] Discrepancy alerting
- [ ] Reconciliation report
- [ ] Audit trail

### Phase 4: Reksadana Integration (3-4 minggu)

- [ ] MI API integration
- [ ] Reksadana buy/sell
- [ ] NAV tracking
- [ ] Portfolio view (saham + reksadana)

---

## Referensi

### Internal
- `17-aplikasi-retail-pribadi.md` — Fitur aplikasi ritel
- `40-oms-ems-architecture.md` — OMS/EMS architecture
- `45-robo-advisor-goal-based-investing.md` — Robo-advisor (DCA, round-up)
- `04-instrumen-pasar-modal.md` — Instrumen pasar modal (reksadana, sukuk)

### External
- OJK POJK 19/2015 — Reksadana
- Robinhood Fractional Shares — https://robinhood.com/us/en/support/articles/fractional-shares/
- Fidelity Fractional Shares — https://www.fidelity.com/trading/fractional-shares
- IDX Trading Rules — Lot size 100 lembar

---

> **Catatan:** Fractional shares via broker pooling adalah grey area regulatory di IDX. Reksadana fractional adalah alternatif yang lebih aman secara regulatory. Implementasi broker pooling butuh internal ledger yang auditable dan reconciliation harian untuk mencegah discrepancy.
