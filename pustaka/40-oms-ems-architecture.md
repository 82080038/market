# OMS/EMS Architecture: Order Management & Execution Management System

> **Dokumen 40** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Design pattern Order Management System (OMS) dan Execution Management System (EMS) untuk aplikasi ritel IDX — order state machine, event sourcing, smart order routing, partial fill handling, idempotency, kill switch, dan reconciliation.
>
> **Konteks:** OMS adalah "jantung" platform trading. Setiap order dari user hingga settlement melewati OMS. Tanpa OMS yang robust, order bisa hilang, duplicate, atau inconsistent — yang berarti kerugian finansial dan masalah regulatori.

---

## Daftar Isi

1. [Konsep Dasar OMS vs EMS](#1-konsep-dasar-oms-vs-ems)
2. [Order State Machine](#2-order-state-machine)
3. [Event Sourcing Pattern](#3-event-sourcing-pattern)
4. [Smart Order Routing (SOR)](#4-smart-order-routing-sor)
5. [Partial Fill Handling](#5-partial-fill-handling)
6. [Order Idempotency](#6-order-idempotency)
7. [Kill Switch & Emergency Controls](#7-kill-switch--emergency-controls)
8. [Reconciliation](#8-reconciliation)
9. [IDX-Specific Considerations](#9-idx-specific-considerations)
10. [Implementasi](#10-implementasi)
11. [Adopsi dari Codebase Existing](#11-adopsi-dari-codebase-existing)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Konsep Dasar OMS vs EMS

### 1.1 Definisi

| Komponen | Fungsi | Analogi |
|----------|--------|---------|
| **OMS** (Order Management System) | Track lifecycle order dari user hingga fill/cancel. Maintains order state, audit trail, position | "Sistem administrasi" — tahu status setiap order |
| **EMS** (Execution Management System) | Route order ke venue/broker, manage execution logic (TWAP, VWAP, limit chase), handle partial fills | "Eksekutor" — yang benar-benar kirim order ke bursa |
| **Risk Engine** | Pre-trade check: buying power, position limit, market hours, fat-finger detection | "Satpam" — cek sebelum order masuk |

### 1.2 Arsitektur

```
┌──────────────────────────────────────────────────────────────┐
│                      USER (Mobile/Web)                        │
│                         │                                     │
│                    REST API                                   │
│                         ▼                                     │
├──────────────────────────────────────────────────────────────┤
│                     API GATEWAY                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐      │
│  │  Auth &      │  │  Rate       │  │  Request        │      │
│  │  Session     │  │  Limiter    │  │  Validator      │      │
│  └─────────────┘  └─────────────┘  └─────────────────┘      │
│                         │                                     │
│                         ▼                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    OMS CORE                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │    │
│  │  │  Order    │  │  State   │  │  Event Store     │  │    │
│  │  │  Factory  │  │  Machine │  │  (Audit Trail)   │  │    │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │    │
│  │  │  Position │  │  Order   │  │  Idempotency     │  │    │
│  │  │  Manager  │  │  Book    │  │  Token Cache     │  │    │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                     │
│              ┌──────────┴──────────┐                         │
│              ▼                     ▼                         │
│  ┌───────────────┐      ┌────────────────┐                  │
│  │  RISK ENGINE  │      │  EMS CORE      │                  │
│  │  (Pre-trade)  │      │  (Execution)   │                  │
│  │  - Buying power│     │  - Smart Route │                  │
│  │  - Position limit│   │  - Partial Fill│                  │
│  │  - Market hours │    │  - Cancel/Mod  │                  │
│  │  - Fat-finger   │    │  - TWAP/VWAP   │                  │
│  └───────────────┘      └────────────────┘                  │
│                              │                               │
│                              ▼                               │
│                    ┌─────────────────┐                       │
│                    │  BROKER API     │                       │
│                    │  (FIX/REST)     │                       │
│                    └─────────────────┘                       │
│                              │                               │
│                              ▼                               │
│                    ┌─────────────────┐                       │
│                    │  IDX EXCHANGE   │                       │
│                    └─────────────────┘                       │
└──────────────────────────────────────────────────────────────┘
```

### 1.3 Write Path (Order Submission)

```
User submit order
    │
    ▼
API Gateway (auth, rate limit)
    │
    ▼
OMS: Create order (status=NEW)
    │
    ▼
Risk Engine: Pre-trade check
    │
    ├─ FAIL → OMS: status=REJECTED, notify user
    │
    ▼ PASS
OMS: status=PENDING_RISK → ROUTED
    │
    ▼
EMS: Route to broker
    │
    ▼
Broker: Acknowledge
    │
    ▼
OMS: status=ACKNOWLEDGED
    │
    ▼
Broker: Fill (partial/full)
    │
    ▼
OMS: status=PARTIALLY_FILLED / FILLED
    │
    ▼
Position Manager: Update position
    │
    ▼
Event Store: Record all events
```

### 1.4 Read Path (Order Status Query)

```
User query order status
    │
    ▼
API Gateway
    │
    ▼
OMS: Read from Order Book (current state)
    │
    ▼
Return: status, fills, position, PnL
```

---

## 2. Order State Machine

### 2.1 State Diagram

```
                         ┌──────────┐
                         │   NEW    │
                         └────┬─────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
                    ▼         ▼         ▼
              ┌─────────┐ ┌────────┐ ┌──────────┐
              │ PENDING │ │REJECTED│ │ CANCELLED│
              │ _RISK   │ │        │ │          │
              └────┬────┘ └────────┘ └──────────┘
                   │         ▲
                   ▼         │
              ┌─────────┐   │ Risk check fail
              │ ROUTED  │───┘
              └────┬────┘
                   │
                   ▼
              ┌───────────┐
              │ACKNOWLEDGED│
              └────┬──────┘
                   │
          ┌────────┼────────┐
          │        │        │
          ▼        ▼        ▼
    ┌──────────┐ ┌────────┐ ┌──────────┐
    │ PARTIAL  │ │ FILLED │ │ CANCELLED│
    │ _FILLED  │ │        │ │          │
    └────┬─────┘ └────────┘ └──────────┘
         │
         ├─ more fills ──→ PARTIALLY_FILLED
         │
         ├─ complete ────→ FILLED
         │
         └─ user cancel──→ CANCELLED
```

### 2.2 Valid State Transitions

| From | To | Trigger |
|------|-----|---------|
| NEW | PENDING_RISK | Order accepted by OMS |
| NEW | CANCELLED | User cancel before risk check |
| PENDING_RISK | ROUTED | Risk check passed |
| PENDING_RISK | REJECTED | Risk check failed |
| ROUTED | ACKNOWLEDGED | Broker acknowledges order |
| ROUTED | CANCELLED | Timeout / user cancel |
| ACKNOWLEDGED | PARTIALLY_FILLED | Partial fill received |
| ACKNOWLEDGED | FILLED | Full fill received |
| ACKNOWLEDGED | CANCELLED | User cancel (if allowed) |
| PARTIALLY_FILLED | PARTIALLY_FILLED | More partial fills |
| PARTIALLY_FILLED | FILLED | Remaining quantity filled |
| PARTIALLY_FILLED | CANCELLED | Cancel remaining quantity |

**Invalid transitions** (must be rejected with alert):
- FILLED → anything (terminal state)
- CANCELLED → anything (terminal state)
- REJECTED → anything (terminal state)
- ACKNOWLEDGED → NEW (cannot go back)

### 2.3 Implementasi State Machine

```python
from enum import Enum
from transitions import Machine


class OrderState(Enum):
    NEW = "new"
    PENDING_RISK = "pending_risk"
    ROUTED = "routed"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Order:
    """Order entity with state machine."""

    states = [s.value for s in OrderState]

    transitions = [
        # trigger,             source,              dest,               conditions
        ("submit_to_risk",     "new",               "pending_risk"),
        ("cancel_pre_risk",    "new",               "cancelled"),
        ("risk_pass",          "pending_risk",      "routed"),
        ("risk_fail",          "pending_risk",      "rejected"),
        ("broker_ack",         "routed",            "acknowledged"),
        ("cancel_timeout",     "routed",            "cancelled"),
        ("partial_fill",       "acknowledged",      "partially_filled"),
        ("full_fill",          "acknowledged",      "filled"),
        ("cancel_post_ack",    "acknowledged",      "cancelled"),
        ("more_partial",       "partially_filled",  "partially_filled"),
        ("complete_fill",      "partially_filled",  "filled"),
        ("cancel_remaining",   "partially_filled",  "cancelled"),
    ]

    TERMINAL_STATES = {"filled", "cancelled", "rejected"}

    def __init__(self, order_id: str, user_id: str, ticker: str,
                 side: str, quantity: int, price: float, order_type: str):
        self.order_id = order_id
        self.user_id = user_id
        self.ticker = ticker
        self.side = side  # BUY / SELL
        self.quantity = quantity
        self.remaining_quantity = quantity
        self.price = price
        self.order_type = order_type  # market / limit / stop
        self.fills: list[dict] = []
        self.events: list[dict] = []

        self.machine = Machine(
            model=self,
            states=Order.states,
            transitions=Order.transitions,
            initial="new",
        )

    def apply_fill(self, fill_qty: int, fill_price: float, fill_id: str):
        """Apply a fill to the order."""
        if self.state in self.TERMINAL_STATES:
            raise ValueError(f"Cannot fill order in terminal state: {self.state}")

        self.fills.append({
            "fill_id": fill_id,
            "quantity": fill_qty,
            "price": fill_price,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        self.remaining_quantity -= fill_qty

        if self.remaining_quantity <= 0:
            if self.state == "acknowledged":
                self.full_fill()
            elif self.state == "partially_filled":
                self.complete_fill()
        else:
            if self.state == "acknowledged":
                self.partial_fill()
            elif self.state == "partially_filled":
                self.more_partial()

    def record_event(self, event_type: str, data: dict):
        """Record state change event for audit trail."""
        self.events.append({
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "from_state": self.state,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        })
```

---

## 3. Event Sourcing Pattern

### 3.1 Konsep

Daripada menyimpan hanya **current state** order, simpan **setiap event** yang mengubah state. Keuntungan:

- **Complete audit trail** — setiap perubahan tercatat dengan timestamp
- **Replay capability** — bisa reconstruct state pada waktu tertentu
- **Debugging** — telusuri persis apa yang terjadi saat error
- **Regulatory compliance** — regulator bisa audit setiap step

### 3.2 Event Store Schema

```sql
CREATE TABLE order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,         -- UUID
    order_id TEXT NOT NULL,                -- FK ke orders
    event_type TEXT NOT NULL,              -- created, risk_passed, routed, acked, filled, cancelled, etc.
    sequence_num INTEGER NOT NULL,         -- Urutan event per order
    from_state TEXT,
    to_state TEXT,
    timestamp DATETIME NOT NULL,
    actor TEXT NOT NULL,                   -- user_id, system, broker
    metadata TEXT,                         -- JSON: fill_qty, fill_price, reject_reason, etc.
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE INDEX idx_order_events_order ON order_events(order_id);
CREATE INDEX idx_order_events_type ON order_events(event_type);
CREATE INDEX idx_order_events_timestamp ON order_events(timestamp);
```

### 3.3 Implementasi Event Store

```python
class OrderEventStore:
    """Append-only event store for order lifecycle."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def append(self, order_id: str, event_type: str,
               from_state: str, to_state: str,
               actor: str, metadata: dict | None = None) -> str:
        """Append event to store. Returns event_id."""
        event_id = str(uuid.uuid4())
        seq = self._get_next_sequence(order_id)

        self.storage.execute(
            """INSERT INTO order_events
               (event_id, order_id, event_type, sequence_num,
                from_state, to_state, timestamp, actor, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, order_id, event_type, seq,
             from_state, to_state, datetime.now(UTC), actor,
             json.dumps(metadata or {}))
        )
        return event_id

    def get_events(self, order_id: str) -> list[dict]:
        """Get all events for an order, ordered by sequence."""
        rows = self.storage.query(
            """SELECT * FROM order_events
               WHERE order_id = ? ORDER BY sequence_num""",
            (order_id,)
        )
        return [dict(r) for r in rows]

    def reconstruct_state(self, order_id: str, as_of: datetime | None = None) -> dict:
        """Reconstruct order state from events (optionally as of a point in time)."""
        events = self.get_events(order_id)
        if as_of:
            events = [e for e in events
                      if datetime.fromisoformat(e["timestamp"]) <= as_of]

        if not events:
            return {"state": "unknown", "events": []}

        last_event = events[-1]
        return {
            "order_id": order_id,
            "state": last_event["to_state"],
            "events": events,
            "event_count": len(events),
        }

    def _get_next_sequence(self, order_id: str) -> int:
        """Get next sequence number for an order."""
        result = self.storage.query_one(
            "SELECT MAX(sequence_num) as max_seq FROM order_events WHERE order_id = ?",
            (order_id,)
        )
        return (result["max_seq"] or 0) + 1
```

### 3.4 Event Types

| Event Type | Trigger | Metadata |
|------------|---------|----------|
| `order_created` | User submit order | `{side, ticker, qty, price, order_type}` |
| `risk_check_started` | OMS forward to risk | `{risk_checks: [...]}` |
| `risk_check_passed` | All risk checks pass | `{checks_passed: [...], latency_ms}` |
| `risk_check_failed` | Any risk check fail | `{failed_check, reason, threshold, actual}` |
| `order_routed` | EMS route to broker | `{broker, venue, routing_decision}` |
| `order_acknowledged` | Broker confirms receipt | `{broker_order_id, timestamp}` |
| `partial_fill` | Partial fill received | `{fill_id, fill_qty, fill_price, remaining}` |
| `full_fill` | Complete fill | `{fill_id, fill_qty, fill_price, total_fills}` |
| `order_cancelled` | Cancel request | `{reason, actor, remaining_qty}` |
| `order_rejected` | Broker reject | `{reject_reason, reject_code}` |
| `order_expired` | TTL expired | `{ttl_seconds, reason}` |
| `cancel_replaced` | Modify order | `{old_qty, new_qty, new_price}` |

---

## 4. Smart Order Routing (SOR)

### 4.1 Konteks IDX

IDX adalah **single venue** (tidak seperti US yang punya multiple exchanges). Namun, ada **multiple broker** yang bisa dipilih. SOR untuk IDX berarti:

| Decision | Faktor |
|----------|--------|
| Pilih broker | Latency, fee, reliability, broker-specific limits |
| Pilih order type | Market vs limit vs stop, tergantung likuiditas |
| Split order | Large order → split untuk reduce market impact |
| Timing | Eksekusi segera vs wait for better price |

### 4.2 Implementasi SOR

```python
class SmartOrderRouter:
    """Smart order routing untuk IDX (multi-broker)."""

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.brokers = self._load_brokers()

    def route(self, order: Order) -> dict:
        """Determine best routing for an order."""
        routing = {
            "order_id": order.order_id,
            "broker": None,
            "strategy": None,
            "split": None,
            "timing": "immediate",
        }

        # 1. Check if order needs splitting (large order)
        avg_volume = self.storage.get_avg_volume(order.ticker, days=20)
        order_value = order.quantity * order.price

        if avg_volume > 0 and order_value > avg_volume * 0.10:
            # Order > 10% of 20-day average volume → split
            routing["strategy"] = "split"
            routing["split"] = self._compute_split_schedule(
                order.quantity, avg_volume, order.side
            )
        else:
            routing["strategy"] = "direct"

        # 2. Select broker
        routing["broker"] = self._select_broker(order)

        # 3. Timing decision
        if order.order_type == "limit":
            routing["timing"] = "immediate"  # Limit order: place immediately
        elif order.order_type == "market":
            # Check market conditions
            spread = self.storage.get_bid_ask_spread(order.ticker)
            if spread and spread > 0.02:  # Spread > 2%
                routing["timing"] = "wait_narrow"  # Wait for spread to narrow
            else:
                routing["timing"] = "immediate"

        return routing

    def _select_broker(self, order: Order) -> str:
        """Select best broker for order."""
        scored = []
        for broker_id, broker in self.brokers.items():
            score = 0.0
            # Latency score (lower = better)
            score += (1.0 - broker["avg_latency_ms"] / 1000) * 30
            # Fee score (lower = better)
            score += (1.0 - broker["fee_bps"] / 50) * 25
            # Reliability score
            score += broker["success_rate"] * 25
            # Capacity score
            if broker["remaining_capacity"] > order.quantity:
                score += 20
            scored.append((broker_id, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0] if scored else None

    def _compute_split_schedule(self, total_qty: int, avg_volume: float,
                                 side: str) -> list[dict]:
        """Compute TWAP-style split schedule."""
        max_per_slice = int(avg_volume * 0.05)  # Max 5% of avg volume per slice
        slices = []
        remaining = total_qty
        slice_num = 0

        while remaining > 0:
            qty = min(max_per_slice, remaining)
            slices.append({
                "slice": slice_num,
                "quantity": qty,
                "delay_seconds": slice_num * 300,  # 5 min between slices
            })
            remaining -= qty
            slice_num += 1

        return slices
```

---

## 5. Partial Fill Handling

### 5.1 Scenario

User order BUY 1000 BBCA @ 8,400. Likuiditas terbatas:
- Fill 1: 300 @ 8,400
- Fill 2: 500 @ 8,410
- Fill 3: 200 @ 8,405

### 5.2 Implementasi

```python
class FillProcessor:
    """Process incoming fills from broker."""

    def __init__(self, storage: DataStorage, event_store: OrderEventStore):
        self.storage = storage
        self.event_store = event_store

    def process_fill(self, order_id: str, fill_data: dict) -> dict:
        """Process a fill from broker."""
        order = self.storage.get_order(order_id)
        if not order:
            return {"status": "error", "message": "Order not found"}

        if order["status"] in ("filled", "cancelled", "rejected"):
            return {"status": "error", "message": f"Order already {order['status']}"}

        fill_id = fill_data["fill_id"]
        fill_qty = fill_data["quantity"]
        fill_price = fill_data["price"]

        # Check for duplicate fill (idempotency)
        if self.storage.fill_exists(fill_id):
            return {"status": "duplicate", "message": "Fill already processed"}

        # Save fill record
        self.storage.save_fill(
            fill_id=fill_id,
            order_id=order_id,
            quantity=fill_qty,
            price=fill_price,
            timestamp=datetime.now(UTC),
        )

        # Update order
        order_obj = self._reconstruct_order(order)
        order_obj.apply_fill(fill_qty, fill_price, fill_id)

        # Record event
        self.event_store.append(
            order_id=order_id,
            event_type="partial_fill" if order_obj.remaining_quantity > 0 else "full_fill",
            from_state=order["status"],
            to_state=order_obj.state,
            actor="broker",
            metadata={
                "fill_id": fill_id,
                "fill_qty": fill_qty,
                "fill_price": fill_price,
                "remaining": order_obj.remaining_quantity,
            },
        )

        # Update position
        self._update_position(order, fill_qty, fill_price)

        # Update order in DB
        self.storage.update_order_status(
            order_id, order_obj.state,
            filled_quantity=order_obj.quantity - order_obj.remaining_quantity,
            avg_fill_price=self._compute_avg_fill_price(order_obj.fills),
        )

        # Notify user via WebSocket
        self._notify_user(order["user_id"], {
            "type": "fill",
            "order_id": order_id,
            "fill_qty": fill_qty,
            "fill_price": fill_price,
            "remaining": order_obj.remaining_quantity,
            "order_status": order_obj.state,
        })

        return {
            "status": "ok",
            "order_status": order_obj.state,
            "filled_qty": fill_qty,
            "remaining": order_obj.remaining_quantity,
        }

    def _compute_avg_fill_price(self, fills: list[dict]) -> float:
        """Compute volume-weighted average fill price."""
        total_value = sum(f["quantity"] * f["price"] for f in fills)
        total_qty = sum(f["quantity"] for f in fills)
        return total_value / total_qty if total_qty > 0 else 0
```

---

## 6. Order Idempotency

### 6.1 Problem

User submit order → network timeout → user retry → **TWO orders created**. Ini adalah bug paling berbahaya di trading system.

### 6.2 Solution: Idempotency Token

```python
class OrderFactory:
    """Create orders with idempotency guarantee."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def create_order(
        self,
        user_id: str,
        ticker: str,
        side: str,
        quantity: int,
        price: float,
        order_type: str,
        idempotency_key: str,  # Client-generated UUID
    ) -> dict:
        """Create order with idempotency. Same key = same order."""

        # Check if order with this idempotency key already exists
        existing = self.storage.get_order_by_idempotency_key(user_id, idempotency_key)
        if existing:
            return {
                "status": "duplicate",
                "order_id": existing["id"],
                "message": "Order already created with this idempotency key",
                "order": existing,
            }

        # Create new order
        order_id = str(uuid.uuid4())
        self.storage.create_order(
            order_id=order_id,
            user_id=user_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            idempotency_key=idempotency_key,
            status="new",
        )

        return {
            "status": "created",
            "order_id": order_id,
        }
```

### 6.3 Client-Side Implementation

```typescript
// Frontend: generate idempotency key per order attempt
async function submitOrder(order: OrderParams): Promise<OrderResult> {
  const idempotencyKey = crypto.randomUUID();  // Generate once

  try {
    const response = await fetch('/api/orders', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(order),
    });
    return await response.json();
  } catch (error) {
    // On timeout/error, RETRY with SAME idempotency key
    // Server will return the original order, not create a duplicate
    const retry = await fetch('/api/orders', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Idempotency-Key': idempotencyKey,  // SAME KEY
      },
      body: JSON.stringify(order),
    });
    return await retry.json();
  }
}
```

---

## 7. Kill Switch & Emergency Controls

### 7.1 Kill Switch Hierarchy

| Level | Trigger | Action | Scope |
|-------|---------|--------|-------|
| **User Kill Switch** | User manual | Cancel all open orders for this user | Per user |
| **Risk Kill Switch** | Daily loss limit exceeded | Halt new orders, notify user | Per user |
| **System Kill Switch** | System malfunction | Halt all trading, cancel all orders | System-wide |
| **Market Kill Switch** | IDX trading halt / auto-reject | Halt all IDX orders | Market-wide |
| **Compliance Kill Switch** | Regulatory alert | Freeze account, pending review | Per user |

### 7.2 Implementasi

```python
class KillSwitchManager:
    """Manage emergency stop mechanisms."""

    def __init__(self, storage: DataStorage, event_store: OrderEventStore):
        self.storage = storage
        self.event_store = event_store

    def user_kill_switch(self, user_id: str) -> dict:
        """User-initiated: cancel all open orders."""
        open_orders = self.storage.get_open_orders(user_id)
        cancelled = 0

        for order in open_orders:
            if order["status"] in ("new", "pending_risk", "routed",
                                    "acknowledged", "partially_filled"):
                self._cancel_order(order["id"], reason="user_kill_switch")
                cancelled += 1

        self.storage.set_state(f"kill_switch_{user_id}", datetime.now(UTC).isoformat())
        return {"status": "activated", "orders_cancelled": cancelled}

    def system_kill_switch(self, reason: str) -> dict:
        """System-wide: halt all trading."""
        # 1. Set global halt flag
        self.storage.set_state("system_halt", "true")
        self.storage.set_state("system_halt_reason", reason)
        self.storage.set_state("system_halt_timestamp", datetime.now(UTC).isoformat())

        # 2. Cancel all open orders system-wide
        all_open = self.storage.get_all_open_orders()
        cancelled = 0
        for order in all_open:
            self._cancel_order(order["id"], reason=f"system_kill_switch: {reason}")
            cancelled += 1

        # 3. Notify all connected users via WebSocket
        self._broadcast_halt_notification(reason)

        # 4. Alert operations team
        self._alert_ops_team(reason, cancelled)

        return {
            "status": "activated",
            "reason": reason,
            "orders_cancelled": cancelled,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def check_market_halt(self) -> bool:
        """Check if IDX market is halted (auto-reject, trading halt)."""
        market_status = self.storage.get_market_status()
        if market_status in ("halted", "auto_reject", "pre_open", "post_close"):
            return True
        return False

    def _cancel_order(self, order_id: str, reason: str):
        """Cancel a single order."""
        order = self.storage.get_order(order_id)
        if not order:
            return

        old_status = order["status"]
        self.storage.update_order_status(order_id, "cancelled")

        self.event_store.append(
            order_id=order_id,
            event_type="order_cancelled",
            from_state=old_status,
            to_state="cancelled",
            actor="system",
            metadata={"reason": reason},
        )
```

---

## 8. Reconciliation

### 8.1 Reconciliation Process

```
┌────────────────────────────────────────────────────────────┐
│                    RECONCILIATION CYCLE                      │
│                                                            │
│  1. Fetch broker statement (end of day)                    │
│     ↓                                                      │
│  2. Compare: OMS orders vs broker statement                │
│     ↓                                                      │
│  3. Identify discrepancies:                                │
│     a. Order in OMS but not in broker → ghost order        │
│     b. Order in broker but not in OMS → orphan order       │
│     c. Fill qty/price mismatch → fill discrepancy          │
│     d. Status mismatch → status discrepancy                │
│     ↓                                                      │
│  4. Auto-resolve minor discrepancies (rounding < Rp 10)    │
│     ↓                                                      │
│  5. Escalate major discrepancies to ops team               │
│     ↓                                                      │
│  6. Record reconciliation result + audit trail             │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 8.2 Implementasi

```python
class ReconciliationEngine:
    """Reconcile OMS state vs broker statement."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def reconcile_daily(self, date: str) -> dict:
        """Run daily reconciliation for all orders."""
        # Get all orders for the date
        oms_orders = self.storage.get_orders_by_date(date)
        broker_orders = self._fetch_broker_statement(date)

        discrepancies = []

        for oms_order in oms_orders:
            broker_order = self._find_broker_match(broker_orders, oms_order)

            if not broker_order:
                discrepancies.append({
                    "type": "ghost_order",
                    "order_id": oms_order["id"],
                    "severity": "high",
                    "detail": "Order exists in OMS but not in broker statement",
                })
                continue

            # Check fill quantity
            oms_filled = oms_order.get("filled_quantity", 0)
            broker_filled = broker_order.get("filled_quantity", 0)
            if oms_filled != broker_filled:
                discrepancies.append({
                    "type": "fill_qty_mismatch",
                    "order_id": oms_order["id"],
                    "severity": "high",
                    "oms_qty": oms_filled,
                    "broker_qty": broker_filled,
                })

            # Check fill price (tolerance Rp 1)
            oms_price = oms_order.get("avg_fill_price", 0)
            broker_price = broker_order.get("avg_fill_price", 0)
            if abs(oms_price - broker_price) > 1:
                discrepancies.append({
                    "type": "fill_price_mismatch",
                    "order_id": oms_order["id"],
                    "severity": "medium",
                    "oms_price": oms_price,
                    "broker_price": broker_price,
                })

            # Check status
            if oms_order["status"] != broker_order["status"]:
                discrepancies.append({
                    "type": "status_mismatch",
                    "order_id": oms_order["id"],
                    "severity": "medium",
                    "oms_status": oms_order["status"],
                    "broker_status": broker_order["status"],
                })

        # Check for orphan orders (in broker but not in OMS)
        oms_ids = {o["id"] for o in oms_orders}
        for broker_order in broker_orders:
            if broker_order["client_order_id"] not in oms_ids:
                discrepancies.append({
                    "type": "orphan_order",
                    "order_id": broker_order["client_order_id"],
                    "severity": "high",
                    "detail": "Order exists in broker but not in OMS",
                })

        result = {
            "date": date,
            "oms_order_count": len(oms_orders),
            "broker_order_count": len(broker_orders),
            "discrepancy_count": len(discrepancies),
            "discrepancies": discrepancies,
            "reconciled_at": datetime.now(UTC).isoformat(),
        }

        self.storage.save_reconciliation_result(result)
        return result
```

---

## 9. IDX-Specific Considerations

### 9.1 IDX Trading Rules

| Rule | Dampak ke OMS |
|------|--------------|
| **Auto-reject** (price move >20% from reference) | OMS harus check auto-reject status sebelum route |
| **Trading halt** | OMS harus detect halt dan queue orders |
| **Tick size** (fraksi harga) | OMS harus round price ke tick size yang valid |
| **Lot size** (100 shares) | OMS harus validate quantity dalam kelipatan 100 |
| **Short selling** | Tidak allowed untuk ritel → OMS block SELL jika no position |
| **T+2 settlement** | OMS harus track settlement date |
| **Trading hours** (09:00-15:30 WIB) | OMS check market hours sebelum accept order |
| **Pre-opening** (08:45-09:00) | OMS support pre-open order type |

### 9.2 IDX Fraksi Harga (Tick Size)

```python
def round_to_tick(price: float) -> float:
    """Round price to IDX tick size (fraksi harga)."""
    if price < 200:
        tick = 1        # Rp 1
    elif price < 500:
        tick = 2        # Rp 2
    elif price < 2000:
        tick = 5        # Rp 5
    elif price < 5000:
        tick = 10       # Rp 10
    else:
        tick = 25       # Rp 25
    return round(price / tick) * tick
```

### 9.3 Auto-Reject Monitoring

```python
class AutoRejectMonitor:
    """Monitor IDX auto-reject status."""

    def check_before_route(self, ticker: str, order: Order) -> dict:
        """Check if order would hit auto-reject."""
        ref_price = self.storage.get_reference_price(ticker)
        upper_limit = ref_price * 1.20  # +20%
        lower_limit = ref_price * 0.80  # -20%

        if order.side == "BUY" and order.price > upper_limit:
            return {
                "can_route": False,
                "reason": "auto_reject_upper",
                "message": f"Price {order.price} exceeds auto-reject upper limit {upper_limit}",
            }

        if order.side == "SELL" and order.price < lower_limit:
            return {
                "can_route": False,
                "reason": "auto_reject_lower",
                "message": f"Price {order.price} below auto-reject lower limit {lower_limit}",
            }

        return {"can_route": True}
```

---

## 10. Implementasi

### 10.1 Database Schema

```sql
-- Orders table
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,                  -- BUY / SELL
    quantity INTEGER NOT NULL,
    filled_quantity INTEGER DEFAULT 0,
    remaining_quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    avg_fill_price REAL DEFAULT 0,
    order_type TEXT NOT NULL,            -- market / limit / stop
    status TEXT NOT NULL DEFAULT 'new',
    idempotency_key TEXT UNIQUE,         -- Prevent duplicate orders
    broker_id TEXT,
    broker_order_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    parent_order_id TEXT,                -- For split orders
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Fills table
CREATE TABLE fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    fill_id TEXT UNIQUE NOT NULL,        -- Broker fill ID (idempotency)
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    fee REAL DEFAULT 0,
    timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

-- Order events (event sourcing)
CREATE TABLE order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    order_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    from_state TEXT,
    to_state TEXT,
    timestamp DATETIME NOT NULL,
    actor TEXT NOT NULL,
    metadata TEXT,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

-- Reconciliation results
CREATE TABLE reconciliation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    oms_order_count INTEGER,
    broker_order_count INTEGER,
    discrepancy_count INTEGER,
    discrepancies TEXT,                 -- JSON
    reconciled_at DATETIME,
    UNIQUE(date)
);
```

### 10.2 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/orders` | POST | Create new order (with idempotency key) |
| `/api/orders` | GET | List user orders (with filters) |
| `/api/orders/{id}` | GET | Get order detail + event history |
| `/api/orders/{id}/cancel` | POST | Cancel order |
| `/api/orders/{id}/modify` | POST | Modify order (cancel-replace) |
| `/api/orders/{id}/fills` | GET | Get fills for order |
| `/api/orders/kill-switch` | POST | User kill switch (cancel all) |
| `/api/orders/batch` | POST | Batch order submission |
| `/api/orders/reconcile` | POST | Trigger reconciliation (admin) |
| `/api/orders/positions` | GET | Get user positions |
| `WS /ws/orders` | WS | Real-time order updates |

---

## 11. Adopsi dari Codebase Existing

### 11.1 Module yang Sudah Ada

| Module | Fungsi | Yang Perlu Ditambah |
|--------|--------|-------------------|
| `execution/automated.py` | Auto trading engine | OMS state machine, event sourcing |
| `execution/interface.py` | Execution interface | EMS routing logic, SOR |
| `execution/broker_adapter.py` | Broker adapter | FIX protocol, partial fill handling |
| `data/storage.py` | Data storage | Order/fill/event tables, idempotency |
| `risk/engine.py` | Risk engine | Pre-trade risk checks untuk OMS |

### 11.2 Modifikasi yang Diperlukan

1. **`execution/automated.py`** — Tambah `OrderStateMachine` class
2. **`data/storage.py`** — Tambah `save_order`, `save_fill`, `get_order_by_idempotency_key`
3. **`execution/interface.py`** — Tambah `SmartOrderRouter`, `FillProcessor`
4. **New: `execution/oms.py`** — OMS core: order factory, order book, event store
5. **New: `execution/ems.py`** — EMS core: routing, execution algorithms
6. **New: `execution/reconciliation.py`** — Reconciliation engine
7. **New: `execution/kill_switch.py`** — Kill switch manager

---

## 12. Checklist Implementasi

### Phase 1: Core OMS (3-4 minggu)

- [ ] Database schema: `orders`, `fills`, `order_events` tables
- [ ] `Order` class dengan state machine
- [ ] `OrderEventStore` (append-only event log)
- [ ] `OrderFactory` dengan idempotency key
- [ ] API: `POST /api/orders`, `GET /api/orders/{id}`
- [ ] Unit tests: state transitions, idempotency

### Phase 2: EMS & Routing (3-4 minggu)

- [ ] `SmartOrderRouter` untuk multi-broker
- [ ] `FillProcessor` untuk partial fills
- [ ] Broker adapter enhancement (partial fill support)
- [ ] API: `POST /api/orders/{id}/cancel`, `/modify`
- [ ] WebSocket: real-time order updates

### Phase 3: Risk & Controls (2-3 minggu)

- [ ] Pre-trade risk checks (buying power, position limit, market hours)
- [ ] `KillSwitchManager` (user, system, market levels)
- [ ] Auto-reject monitoring
- [ ] Tick size validation
- [ ] Lot size validation

### Phase 4: Reconciliation (2-3 minggu)

- [ ] `ReconciliationEngine` (daily reconciliation)
- [ ] Discrepancy detection & escalation
- [ ] Reconciliation report
- [ ] API: `POST /api/orders/reconcile`

### Phase 5: Polish (2 minggu)

- [ ] Integration tests (end-to-end order flow)
- [ ] Performance tests (order throughput)
- [ ] Audit trail verification
- [ ] Documentation

---

## Referensi

### Internal
- `20-syarat-robot-auto-trading.md` — 12 pilar syarat robot trading
- `28-api-design-integration-patterns.md` — REST, WebSocket, FIX protocol
- `26-post-trade-settlement-rekonsiliasi.md` — Post-trade & settlement
- `24-market-microstructure-likuiditas.md` — Market microstructure IDX

### External
- HLD Handbook — Brokerage Platform Design (Robinhood/E*TRADE/IB)
- Algovantis — End-to-End Algorithmic Trading System Design
- Gegobyteapps — Trading System Architecture Guide 2026
- FCA — Multi-firm review of algorithmic trading controls (RTS 6)
- FIX Protocol Ltd — FIX 4.4 specification

---

## 13. Concurrency & Race Condition Patterns

> **Gap teridentifikasi:** Dokumen ini membahas idempotency (§6) tetapi tidak membahas race condition pada balance reservation, concurrency control untuk concurrent order submission, saga pattern untuk distributed order processing, dan materialized view pattern untuk position serving. Bagian ini mengisi gap tersebut.

### 13.1 TOCTOU Race Condition pada Balance Check

**Problem (Time-Of-Check-Time-Of-Use):**

```
User balance: Rp100.000.000

Request A (BUY 50jt): read balance=100jt → check 100jt >= 50jt ✓ → write balance=50jt
Request B (BUY 50jt): read balance=100jt → check 100jt >= 50jt ✓ → write balance=50jt
                                                                    ↓
                                              Hasil: balance=50jt (harusnya 0jt)
                                              Kedua order lolos, user overdraw
```

**Solution: Conditional UPDATE (atomic check-and-decrement):**

```python
class BalanceReservation:
    """Atomic balance reservation using conditional UPDATE."""

    def reserve_balance(self, user_id: str, amount: float) -> dict:
        """Reserve balance atomically. Fails if insufficient."""
        result = self.storage.execute(
            """
            UPDATE user_balance
            SET available = available - :amount,
                reserved = reserved + :amount
            WHERE user_id = :user_id
              AND available >= :amount
            """,
            {"user_id": user_id, "amount": amount},
        )
        if result.rowcount == 0:
            return {"status": "rejected", "reason": "INSUFFICIENT_BALANCE"}
        return {"status": "reserved", "amount": amount}
```

**Tiga pattern atomicity (urutan robustness):**

| Pattern | Cara Kerja | Kapan Pakai |
|---------|-----------|-------------|
| **Conditional UPDATE** | `UPDATE ... WHERE balance >= amount` dalam satu statement | Simple check-and-decrement |
| **SELECT FOR UPDATE** | Transaction + row lock: `SELECT ... FOR UPDATE` → check → update | Multi-step validation dalam transaction |
| **Optimistic concurrency** | Version column: `UPDATE ... WHERE version = :expected` | High contention, read-heavy |

### 13.2 Saga Pattern untuk Distributed Order Processing

**Problem:** Order processing melibatkan multiple steps (reserve balance → submit to broker → process fills → settle). Jika step N gagal, steps 1..N-1 harus di-rollback.

**Solution: Orchestrator-Based Saga dengan Compensation:**

```python
class OrderSaga:
    """Saga orchestrator untuk order processing dengan compensation."""

    STEPS = [
        ("reserve_funds", "release_funds"),
        ("submit_order", "cancel_order"),
        ("process_fills", "reverse_fills"),
        ("settle", "reverse_settlement"),
    ]

    async def execute(self, order: Order) -> dict:
        completed = []
        for step_name, compensation_name in self.STEPS:
            try:
                # Persist state BEFORE executing (crash recovery)
                await self._save_saga_state(order.id, step_name, "in_progress")
                await getattr(self, f"_{step_name}")(order)
                completed.append((step_name, compensation_name))
                await self._save_saga_state(order.id, step_name, "done")
            except Exception as e:
                # Run compensations in reverse for completed steps
                for done_step, comp_name in reversed(completed):
                    await getattr(self, f"_{comp_name}")(order)
                return {"status": "failed", "failed_at": step_name, "error": str(e)}
        return {"status": "settled"}
```

| Step | Forward | Compensation |
|------|---------|-------------|
| 1. reserve_funds | `balance.hold(amount)` | `balance.release(amount)` |
| 2. submit_order | `broker.submit(order)` | `broker.cancel(order_id)` |
| 3. process_fills | Debit/credit per fill | Mirror credit/debit |
| 4. settle | Record settlement + release excess | Mark settlement reversed |

**Crash recovery:** State `in_progress` di DB → `recoverInFlight()` pada boot menyelesaikan atau meng-compensate.

### 13.3 Materialized View Pattern untuk Position Serving

**Problem:** Position P&L dihitung dari event stream (fills). User query position setiap detik → tidak boleh hit event store setiap kali.

**Solution:** Pre-compute position di queryable store, update via event subscription:

```python
class PositionService:
    """Serve positions from materialized view, not from event stream."""

    def __init__(self):
        self.event_store = OrderEventStore()
        self.position_cache = {}  # In production: Redis/DynamoDB

    def on_fill(self, fill_event: dict):
        """Update materialized view on fill event (idempotent)."""
        key = (fill_event["user_id"], fill_event["ticker"])
        if self._is_processed(fill_event["fill_id"]):
            return  # Idempotent: skip duplicate
        pos = self.position_cache.setdefault(key, {"qty": 0, "avg_price": 0, "pnl": 0})
        # Atomic update
        new_qty = pos["qty"] + fill_event["quantity"]
        pos["avg_price"] = (
            (pos["avg_price"] * pos["qty"] + fill_event["price"] * fill_event["quantity"])
            / new_qty if new_qty != 0 else 0
        )
        pos["qty"] = new_qty
        self._mark_processed(fill_event["fill_id"])

    def get_position(self, user_id: str, ticker: str) -> dict:
        """User queries pre-computed position, not event stream."""
        return self.position_cache.get((user_id, ticker), {"qty": 0, "avg_price": 0, "pnl": 0})
```

### 13.4 Claim-Before-Dispatch Pattern untuk Workers

**Problem:** Multiple workers dapat mengambil order yang sama dari queue secara bersamaan.

**Solution:** Atomic claim sebelum eksekusi:

```python
class OrderWorker:
    """Claim order atomically before processing."""

    def claim_next_order(self) -> Optional[Order]:
        """Atomically transition order from pending to processing."""
        result = self.storage.execute(
            """
            UPDATE orders
            SET status = 'processing', claimed_at = :now
            WHERE id = (
                SELECT id FROM orders
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
            )
            RETURNING *
            """,
            {"now": datetime.utcnow()},
        )
        return Order(**result.fetchone()) if result.rowcount > 0 else None
```

**Untuk PostgreSQL:** Gunakan `FOR UPDATE SKIP LOCKED` untuk concurrent claim:
```sql
SELECT * FROM orders WHERE status = 'pending'
ORDER BY created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1
```

### 13.5 Concurrency Matrix untuk Trading System

| Domain | Parallelism | Serialization Key | Protection |
|--------|------------|-------------------|------------|
| Order placement | Per-user/symbol/side | `user_id:symbol:side` | Idempotency key + balance lock |
| Order dispatch | Per-order | `order_id` | Claim-before-dispatch |
| Fill processing | Per-fill | `fill_id` | Idempotency (fill_exists check) |
| Position update | Per-user/symbol | `user_id:symbol` | Atomic increment |
| Balance update | Per-user | `user_id` | Conditional UPDATE |
| Strategy execution | Per-strategy/symbol | `strategy_id:symbol` | Execution lock |
| Reconciliation | Per-batch | `batch_id` | Bounded worker pool |

### 13.6 5W1H

| Aspect | Detail |
|--------|--------|
| **What** | Concurrency patterns: TOCTOU prevention, saga, materialized view, claim-before-dispatch |
| **Why** | Race condition di money path = kerugian finansial langsung. Dua order concurrent dapat overdraw balance. Lost fill dapat corrupt position |
| **When** | Saat sistem mendukung concurrent order submission, multiple workers, atau async broker callback |
| **Where** | OMS core, balance management, position service, fill processor, worker pool |
| **Who** | Backend engineer yang implementasi OMS/EMS |
| **How** | Conditional UPDATE untuk atomicity, saga untuk multi-step, materialized view untuk read path, claim untuk worker dispatch |

---

## Referensi

### Internal
- `20-syarat-robot-auto-trading.md` — 12 pilar syarat robot trading
- `28-api-design-integration-patterns.md` — REST, WebSocket, FIX protocol
- `26-post-trade-settlement-rekonsiliasi.md` — Post-trade & settlement
- `24-market-microstructure-likuiditas.md` — Market microstructure IDX

### External
- HLD Handbook — Brokerage Platform Design (Robinhood/E*TRADE/IB)
- Algovantis — End-to-End Algorithmic Trading System Design
- Gegobyteapps — Trading System Architecture Guide 2026
- FCA — Multi-firm review of algorithmic trading controls (RTS 6)
- FIX Protocol Ltd — FIX 4.4 specification
- **DashDevs — Real-Time Trading Platform Development (concurrency, idempotency, backpressure)**
- **Manuel Fedele — High-Throughput Trading Platform Architecture on AWS (materialized view, saga)**
- **QuantDinger — Concurrency Model for Trading Backend (serialization matrix)**

---

> **Catatan:** OMS adalah komponen paling critical di platform trading. Bug di OMS = kerugian finansial langsung. Investasi waktu di testing (unit, integration, stress) adalah wajib, bukan opsional. **Concurrency patterns (§13)** adalah pertahanan terhadap race condition yang paling sulit dideteksi — bug hanya muncul saat dua request tiba dalam window milidetik yang sama.
