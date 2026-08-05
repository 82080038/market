# Event-Driven Architecture & Event Sourcing untuk Trading System

> **Dokumen 65** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Implementasi event-driven architecture (EDA) dan event sourcing untuk trading system — Kafka/Pulsar topic design, CQRS pattern, event store, replay capability, backpressure handling, dan multi-exchange normalization via event streaming.
>
> **Konteks:** EDA adalah standard backbone untuk modern trading platform. Event sourcing memungkinkan complete audit trail, replay untuk backtest, dan fault isolation. Dokumen 28 membahas event-driven secara umum, dokumen ini fokus pada trading-specific patterns.

---

## Daftar Isi

1. [Konsep Event-Driven Architecture](#1-konsep-event-driven-architecture)
2. [Event Sourcing Pattern](#2-event-sourcing-pattern)
3. [CQRS: Command Query Responsibility Segregation](#3-cqrs-command-query-responsibility-segregation)
4. [Kafka Topic Design](#4-kafka-topic-design)
5. [Event Schema & Versioning](#5-event-schema--versioning)
6. [Replay Capability](#6-replay-capability)
7. [Backpressure Handling](#7-backpressure-handling)
8. [Multi-Exchange Normalization](#8-multi-exchange-normalization)
9. [Implementasi](#9-implementasi)
10. [Adopsi dari Codebase Existing](#10-adopsi-dari-codebase-existing)
11. [Checklist Implementasi](#11-checklist-implementasi)

---

## 1. Konsep Event-Driven Architecture

### 1.1 Mengapa EDA untuk Trading?

| Masalah Traditional (Request-Response) | Solusi EDA |
|---------------------------------------|------------|
| Tight coupling antar module | Loose coupling via events |
| Sinkron blocking calls | Async event processing |
| Sulit replay state | Event store = natural audit trail |
| Single point of failure | Fault isolation per consumer |
| Sulit scale individual components | Scale consumers independently |
| Race condition pada shared state | Single-writer per event stream |

### 1.2 Arsitektur

```
┌──────────────────────────────────────────────────────────────┐
│                EVENT-DRIVEN TRADING SYSTEM                    │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Market   │  │ Order    │  │ Risk     │  │ Portfolio│    │
│  │ Data     │  │ Manager  │  │ Engine   │  │ Manager  │    │
│  │ Source   │  │ (OMS)    │  │          │  │          │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │           │
│       ▼             ▼             ▼             ▼           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              EVENT BUS (Kafka / Pulsar)              │   │
│  │                                                      │   │
│  │  Topics:                                             │   │
│  │  ├── marketdata.ticks                                │   │
│  │  ├── marketdata.ohlcv                                │   │
│  │  ├── orders.lifecycle                                │   │
│  │  ├── orders.fills                                    │   │
│  │  ├── risk.alerts                                     │   │
│  │  ├── portfolio.updates                               │   │
│  │  ├── position.changes                                │   │
│  │  ├── sentiment.news                                  │   │
│  │  ├── system.health                                   │   │
│  │  └── audit.events                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│       │             │             │             │           │
│       ▼             ▼             ▼             ▼           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Decision │  │ XAI      │  │ Monitor  │  │ Audit    │    │
│  │ Engine   │  │ Engine   │  │ Service  │  │ Logger   │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1.3 Event Flow Example

```
Market data tick arrives
    │
    ▼
Producer: marketdata.ticks ← {ticker: "BBCA.JK", price: 8450, volume: 1000}
    │
    ├──→ Consumer: Decision Engine (process tick, generate signal)
    ├──→ Consumer: Risk Engine (check position exposure)
    ├──→ Consumer: Portfolio Manager (update portfolio value)
    ├──→ Consumer: XAI Engine (update narrative)
    └──→ Consumer: WebSocket Gateway (push to frontend)
```

---

## 2. Event Sourcing Pattern

### 2.1 Konsep

Daripada menyimpan **current state** saja, simpan **setiap event** yang mengubah state. State saat ini = result dari replay semua events.

### 2.2 Event Store vs State Store

| Aspek | State Store (Traditional) | Event Store (Event Sourcing) |
|-------|--------------------------|------------------------------|
| **What stored** | Current state only | All events that led to state |
| **Audit trail** | Limited (last update only) | Complete (every change) |
| **Replay** | ❌ Not possible | ✅ Replay from any point |
| **Debugging** | Hard (what happened?) | Easy (replay events) |
| **Storage** | Small | Large (grows with events) |
| **Query speed** | Fast (direct read) | Slower (replay or projection) |
| **Regulatory** | Partial | Complete audit trail |

### 2.3 Implementasi Event Store

```python
class EventStore:
    """Append-only event store for trading system."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def append(self, stream_id: str, event_type: str,
               data: dict, metadata: dict | None = None) -> str:
        """Append event to stream. Returns event_id."""
        event_id = str(uuid.uuid4())
        sequence = self._get_next_sequence(stream_id)

        self.storage.execute(
            """INSERT INTO event_store
               (event_id, stream_id, event_type, sequence_num,
                data, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, stream_id, event_type, sequence,
             json.dumps(data), json.dumps(metadata or {}),
             datetime.now(UTC))
        )
        return event_id

    def get_events(self, stream_id: str,
                    from_sequence: int = 0,
                    to_sequence: int | None = None) -> list[dict]:
        """Get events for a stream, optionally range."""
        query = """SELECT * FROM event_store
                   WHERE stream_id = ? AND sequence_num >= ?
                   ORDER BY sequence_num"""
        params = [stream_id, from_sequence]
        if to_sequence:
            query += " AND sequence_num <= ?"
            params.append(to_sequence)

        rows = self.storage.query(query, params)
        return [self._deserialize(r) for r in rows]

    def get_events_by_type(self, event_type: str,
                            since: datetime | None = None) -> list[dict]:
        """Get all events of a specific type."""
        query = "SELECT * FROM event_store WHERE event_type = ?"
        params = [event_type]
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        query += " ORDER BY timestamp"

        rows = self.storage.query(query, params)
        return [self._deserialize(r) for r in rows]

    def replay_stream(self, stream_id: str,
                       as_of: datetime | None = None) -> dict:
        """Replay all events to reconstruct state."""
        events = self.get_events(stream_id)
        if as_of:
            events = [e for e in events
                      if datetime.fromisoformat(e["timestamp"]) <= as_of]

        state = {}
        for event in events:
            state = self._apply_event(state, event)
        return state

    def _apply_event(self, state: dict, event: dict) -> dict:
        """Apply event to state (fold function)."""
        etype = event["event_type"]
        data = event["data"]

        if etype == "position_opened":
            state["positions"] = state.get("positions", {})
            state["positions"][data["ticker"]] = {
                "quantity": data["quantity"],
                "avg_price": data["price"],
            }
        elif etype == "position_closed":
            state["positions"] = state.get("positions", {})
            state["positions"].pop(data["ticker"], None)
        elif etype == "order_created":
            state["orders"] = state.get("orders", [])
            state["orders"].append(data)
        elif etype == "score_computed":
            state["scores"] = state.get("scores", {})
            state["scores"][data["ticker"]] = data

        return state

    def _get_next_sequence(self, stream_id: str) -> int:
        result = self.storage.query_one(
            "SELECT MAX(sequence_num) as max_seq FROM event_store WHERE stream_id = ?",
            (stream_id,)
        )
        return (result["max_seq"] or 0) + 1

    def _deserialize(self, row: dict) -> dict:
        return {
            **row,
            "data": json.loads(row["data"]) if row["data"] else {},
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
        }
```

### 2.4 Database Schema

```sql
CREATE TABLE event_store (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    stream_id TEXT NOT NULL,           -- e.g., "order:123", "portfolio:user1", "ticker:BBCA.JK"
    event_type TEXT NOT NULL,          -- e.g., "order_created", "fill_received", "score_computed"
    sequence_num INTEGER NOT NULL,     -- Per-stream sequence
    data TEXT NOT NULL,                -- JSON event payload
    metadata TEXT,                     -- JSON: correlation_id, causation_id, user_id, etc.
    timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_event_stream ON event_store(stream_id, sequence_num);
CREATE INDEX idx_event_type ON event_store(event_type);
CREATE INDEX idx_event_timestamp ON event_store(timestamp);
```

---

## 3. CQRS: Command Query Responsibility Segregation

### 3.1 Konsep

Pisahkan **write model** (commands yang modify state) dari **read model** (queries yang read state).

```
┌──────────────────────────────────────────────────────────────┐
│                        CQRS PATTERN                           │
│                                                              │
│  COMMAND SIDE (Write)          QUERY SIDE (Read)             │
│  ┌──────────────┐              ┌──────────────┐             │
│  │ SubmitOrder  │              │ GetPortfolio │             │
│  │ CancelOrder  │              │ GetOrders    │             │
│  │ UpdateRisk   │              │ GetPositions │             │
│  │ ComputeScore │              │ GetScores    │             │
│  └──────┬───────┘              └──────┬───────┘             │
│         │                             │                      │
│         ▼                             ▼                      │
│  ┌──────────────┐              ┌──────────────┐             │
│  │  Event Store │─── events ──→│  Read Model  │             │
│  │  (append     │              │  (Projection)│             │
│  │   only)      │              │  (Optimized  │             │
│  │              │              │   for reads) │             │
│  └──────────────┘              └──────────────┘             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Implementasi

```python
class CommandBus:
    """Command bus for write operations."""

    def __init__(self, event_store: EventStore, handlers: dict):
        self.event_store = event_store
        self.handlers = handlers

    def send(self, command: dict) -> dict:
        """Send command to appropriate handler."""
        cmd_type = command["type"]
        handler = self.handlers.get(cmd_type)
        if not handler:
            return {"status": "error", "message": f"No handler for {cmd_type}"}

        # Execute command → produce events
        events = handler.handle(command)

        # Append events to store
        for event in events:
            self.event_store.append(
                stream_id=event["stream_id"],
                event_type=event["type"],
                data=event["data"],
                metadata={"command_id": command.get("command_id")},
            )

        return {"status": "ok", "events": len(events)}


class QueryBus:
    """Query bus for read operations (from projections)."""

    def __init__(self, projections: dict):
        self.projections = projections

    def query(self, query_type: str, params: dict) -> dict:
        """Query read model projection."""
        projection = self.projections.get(query_type)
        if not projection:
            return {"status": "error", "message": f"No projection for {query_type}"}
        return projection.query(params)


class PortfolioProjection:
    """Read model projection for portfolio queries."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def on_event(self, event: dict):
        """Update projection when new event arrives."""
        if event["event_type"] == "position_opened":
            self.storage.upsert_portfolio_view(
                user_id=event["data"]["user_id"],
                ticker=event["data"]["ticker"],
                quantity=event["data"]["quantity"],
                avg_price=event["data"]["price"],
            )
        elif event["event_type"] == "position_closed":
            self.storage.delete_portfolio_view(
                user_id=event["data"]["user_id"],
                ticker=event["data"]["ticker"],
            )

    def query(self, params: dict) -> dict:
        """Query portfolio from read-optimized view."""
        user_id = params["user_id"]
        positions = self.storage.get_portfolio_view(user_id)
        return {"positions": positions}
```

---

## 4. Kafka Topic Design

### 4.1 Topic Structure

| Topic | Partitions | Key | Producers | Consumers |
|-------|-----------|-----|-----------|-----------|
| `marketdata.ticks` | 50 | ticker | MarketDataAdapter | Decision, Risk, Portfolio, WS |
| `marketdata.ohlcv` | 10 | ticker | MarketDataAdapter | Analysis, Backtest, Storage |
| `orders.lifecycle` | 20 | order_id | OMS | Risk, Audit, WS, Monitor |
| `orders.fills` | 20 | order_id | EMS, Broker | OMS, Portfolio, Audit |
| `risk.alerts` | 5 | alert_id | RiskEngine | Monitor, Notification, WS |
| `portfolio.updates` | 20 | user_id | PortfolioManager | WS, XAI, Notification |
| `position.changes` | 20 | user_id | OMS, EMS | Portfolio, Risk, Audit |
| `sentiment.news` | 5 | ticker | SentimentEngine | Decision, XAI |
| `scores.computed` | 10 | ticker | DecisionEngine | Portfolio, XAI, Storage |
| `system.health` | 3 | component | Monitor | AlertManager, Dashboard |
| `audit.events` | 10 | entity_id | All | AuditLogger, Compliance |

### 4.2 Event Examples

```json
// marketdata.ticks
{
  "event_id": "uuid",
  "event_type": "tick",
  "stream_id": "ticker:BBCA.JK",
  "timestamp": "2026-08-05T03:00:00Z",
  "data": {
    "ticker": "BBCA.JK",
    "price": 8450,
    "volume": 1000,
    "bid": 8440,
    "ask": 8460,
    "change_pct": 1.2
  }
}

// orders.lifecycle
{
  "event_id": "uuid",
  "event_type": "order_created",
  "stream_id": "order:12345",
  "timestamp": "2026-08-05T03:01:00Z",
  "data": {
    "order_id": "12345",
    "user_id": "user1",
    "ticker": "BBCA.JK",
    "side": "BUY",
    "quantity": 100,
    "price": 8450,
    "order_type": "limit"
  },
  "metadata": {
    "correlation_id": "uuid",
    "command_id": "uuid"
  }
}

// scores.computed
{
  "event_id": "uuid",
  "event_type": "score_computed",
  "stream_id": "ticker:BBCA.JK",
  "timestamp": "2026-08-05T03:02:00Z",
  "data": {
    "ticker": "BBCA.JK",
    "technical": 56,
    "fundamental": 80,
    "macro": 76,
    "global_market": 50,
    "relationship": 16,
    "sentiment": 45,
    "composite": 55.11
  }
}
```

---

## 5. Event Schema & Versioning

### 5.1 Schema Registry

```python
class EventSchemaRegistry:
    """Manage event schema versions for backward compatibility."""

    SCHEMAS = {
        "tick": {
            "1.0": {"ticker": str, "price": float, "volume": int},
            "1.1": {"ticker": str, "price": float, "volume": int, "bid": float, "ask": float},
            "2.0": {"ticker": str, "price": float, "volume": int, "bid": float, "ask": float,
                     "change_pct": float, "source": str},
        },
        "order_created": {
            "1.0": {"order_id": str, "user_id": str, "ticker": str, "side": str,
                    "quantity": int, "price": float},
            "1.1": {"order_id": str, "user_id": str, "ticker": str, "side": str,
                    "quantity": int, "price": float, "order_type": str},
        },
    }

    def validate(self, event_type: str, version: str, data: dict) -> bool:
        """Validate event data against schema."""
        schema = self.SCHEMAS.get(event_type, {}).get(version)
        if not schema:
            return False
        return all(field in data for field in schema)
```

### 5.2 Versioning Rules

| Change Type | Version Bump | Compatibility |
|-------------|-------------|---------------|
| **Add field** | Minor (1.0 → 1.1) | Backward compatible |
| **Remove field** | Major (1.x → 2.0) | Breaking change |
| **Change field type** | Major (1.x → 2.0) | Breaking change |
| **Rename field** | Major (1.x → 2.0) | Breaking change |

---

## 6. Replay Capability

### 6.1 Use Cases

| Use Case | Benefit |
|----------|---------|
| **Backtest** | Replay historical market events through strategy |
| **Audit** | Reconstruct state at any point in time |
| **Debug** | Replay events that caused a bug |
| **Disaster recovery** | Rebuild state from event log |
| **New projection** | Build new read model from historical events |
| **Compliance** | Regulator can audit complete event history |

### 6.2 Replay Implementation

```python
class EventReplayService:
    """Replay events for backtest, audit, or recovery."""

    def __init__(self, event_store: EventStore):
        self.event_store = event_store

    def replay_for_backtest(self, start: datetime, end: datetime,
                              strategy: callable) -> dict:
        """Replay market events through a strategy for backtesting."""
        events = self.event_store.get_events_by_type("tick", since=start)
        events = [e for e in events
                  if datetime.fromisoformat(e["timestamp"]) <= end]

        results = {"trades": [], "portfolio_value": 0}
        portfolio = {}

        for event in events:
            tick = event["data"]
            signal = strategy(tick, portfolio)
            if signal:
                results["trades"].append(signal)
                self._apply_trade(portfolio, signal)

        results["portfolio"] = portfolio
        results["final_value"] = sum(
            p["quantity"] * p["avg_price"] for p in portfolio.values()
        )
        return results

    def replay_for_audit(self, stream_id: str,
                          as_of: datetime) -> dict:
        """Reconstruct state at a specific point in time."""
        return self.event_store.replay_stream(stream_id, as_of=as_of)

    def replay_for_recovery(self, stream_id: str) -> dict:
        """Rebuild state from event log (disaster recovery)."""
        return self.event_store.replay_stream(stream_id)
```

---

## 7. Backpressure Handling

### 7.1 Problem

Saat market volatility spike, event volume bisa 10-100x normal. Consumers tidak bisa keep up → lag → stale data.

### 7.2 Strategies

| Strategy | Implementasi | Trade-off |
|----------|-------------|-----------|
| **Buffer queue** | Consumer buffer events, process async | Memory usage |
| **Drop low-priority** | Drop sentiment/news events, keep market data | Loss of data |
| **Batch processing** | Process events in batches (100-1000) | Latency |
| **Scale consumers** | Auto-scale consumer instances | Cost |
| **Rate limit producer** | Throttle producer during spike | Data delay |
| **Coalesce** | Merge multiple ticks into 1 (keep latest) | Data loss (intermediate) |

### 7.3 Implementasi

```python
class BackpressureHandler:
    """Handle backpressure during market volatility spikes."""

    def __init__(self, max_queue_size: int = 10_000,
                 coalesce_window_ms: int = 100):
        self.max_queue_size = max_queue_size
        self.coalesce_window_ms = coalesce_window_ms
        self.queue: dict[str, dict] = {}  # ticker → latest event
        self.last_flush = datetime.now(UTC)

    def submit(self, event: dict) -> str:
        """Submit event with backpressure handling."""
        ticker = event["data"].get("ticker")
        if not ticker:
            return "processed"

        # Coalesce: keep only latest event per ticker within window
        self.queue[ticker] = event

        # Check if flush needed
        elapsed = (datetime.now(UTC) - self.last_flush).total_seconds() * 1000
        if elapsed >= self.coalesce_window_ms or len(self.queue) >= self.max_queue_size:
            self._flush()
            return "flushed"

        return "coalesced"

    def _flush(self):
        """Flush coalesced events to consumer."""
        events = list(self.queue.values())
        self.queue.clear()
        self.last_flush = datetime.now(UTC)

        for event in events:
            self._process(event)

    def _process(self, event: dict):
        """Process single event."""
        # Actual processing logic
        pass
```

---

## 8. Multi-Exchange Normalization

### 8.1 Problem

Setiap exchange punya format data berbeda:
- IDX: ticker "BBCA.JK", price in IDR, lot 100
- US: ticker "AAPL", price in USD, lot 1
- HK: ticker "0700.HK", price in HKD, lot 500

### 8.2 Normalization via Event Streaming

```python
class MultiExchangeNormalizer:
    """Normalize market data from multiple exchanges via events."""

    EXCHANGE_CONFIG = {
        "IDX": {"currency": "IDR", "lot_size": 100, "tz": "Asia/Jakarta"},
        "US": {"currency": "USD", "lot_size": 1, "tz": "America/New_York"},
        "HK": {"currency": "HKD", "lot_size": 500, "tz": "Asia/Hong_Kong"},
    }

    def normalize(self, raw_event: dict, exchange: str) -> dict:
        """Normalize raw market data event to standard format."""
        config = self.EXCHANGE_CONFIG.get(exchange, {})

        return {
            "event_id": str(uuid.uuid4()),
            "event_type": "tick_normalized",
            "stream_id": f"ticker:{raw_event['ticker']}",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "ticker": raw_event["ticker"],
                "exchange": exchange,
                "price": float(raw_event["price"]),
                "currency": config.get("currency", "Unknown"),
                "volume": int(raw_event.get("volume", 0)),
                "lot_size": config.get("lot_size", 1),
                "local_time": self._convert_tz(raw_event.get("timestamp"), config.get("tz")),
                "utc_time": datetime.now(UTC).isoformat(),
            },
            "metadata": {
                "source_exchange": exchange,
                "raw_event_id": raw_event.get("event_id"),
            },
        }
```

---

## 9. Implementasi

### 9.1 Technology Choice

| Component | Recommendation | Alternative |
|-----------|---------------|-------------|
| **Event bus** | Redis Streams (simple, low latency) | Apache Kafka (scalable), Pulsar (multi-tenant) |
| **Event store** | SQLite (single-user) | PostgreSQL (multi-user), EventStoreDB |
| **Schema registry** | Custom (Python dict) | Confluent Schema Registry |
| **Consumer framework** | Python asyncio | Celery, Faust |

### 9.2 For Single-User System (Current)

Kafka mungkin overkill untuk single-user system. Redis Streams atau bahkan SQLite-based event store cukup:

```python
# Simple SQLite-based event bus for single-user
class SQLiteEventBus:
    """Lightweight event bus using SQLite (no Kafka needed)."""

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.handlers: dict[str, list[callable]] = {}

    def subscribe(self, event_type: str, handler: callable):
        """Subscribe to event type."""
        self.handlers.setdefault(event_type, []).append(handler)

    def publish(self, event_type: str, data: dict, stream_id: str = ""):
        """Publish event to bus."""
        # 1. Persist to event store
        self.storage.execute(
            """INSERT INTO event_store (event_id, stream_id, event_type,
               sequence_num, data, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), stream_id, event_type,
             self._next_seq(stream_id), json.dumps(data),
             datetime.now(UTC))
        )

        # 2. Notify handlers (async)
        for handler in self.handlers.get(event_type, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
```

---

## 10. Adopsi dari Codebase Existing

| Module Existing | Modifikasi untuk EDA |
|----------------|---------------------|
| `analysis/pipeline.py` | Publish `score_computed` event |
| `execution/automated.py` | Publish `order_created`, `order_filled` events |
| `sentiment/engine.py` | Publish `sentiment_computed` event |
| `monitoring/engine.py` | Subscribe to `system.health` events |
| `xai/engine.py` | Subscribe to `score_computed`, `portfolio.updates` |
| `data/storage.py` | Tambah `event_store` table |
| `api/app.py` | WebSocket gateway subscribe to events |

**New modules:**
- `events/event_store.py` — Event store implementation
- `events/event_bus.py` — Event bus (SQLite or Redis)
- `events/projections.py` — Read model projections
- `events/replay.py` — Replay service
- `events/normalizer.py` — Multi-exchange normalization

---

## 11. Checklist Implementasi

### Phase 1: Event Store (2-3 minggu)

- [ ] Database schema: `event_store` table
- [ ] `EventStore` class (append, get, replay)
- [ ] Unit tests: append, replay, reconstruct state

### Phase 2: Event Bus (2-3 minggu)

- [ ] `SQLiteEventBus` or Redis Streams integration
- [ ] Pub/sub mechanism
- [ ] Error handling for failed handlers
- [ ] Integration with existing modules (publish events)

### Phase 3: CQRS Projections (3-4 minggu)

- [ ] Portfolio projection (read-optimized)
- [ ] Order history projection
- [ ] Score history projection
- [ ] Projection update on event

### Phase 4: Replay & Backpressure (2-3 minggu)

- [ ] Replay service (backtest, audit, recovery)
- [ ] Backpressure handler (coalesce, batch)
- [ ] Multi-exchange normalizer
- [ ] Performance test under load

---

## Referensi

### Internal
- `28-api-design-integration-patterns.md` — Event-driven architecture (general)
- `40-oms-ems-architecture.md` — OMS event sourcing for orders
- `22-data-engineering-pipeline.md` — Data pipeline architecture
- `34-performance-engineering-optimization.md` — Performance optimization

### External
- Apache Kafka — https://kafka.apache.org
- Redis Streams — https://redis.io/docs/data-types/streams/
- Martin Fowler — CQRS pattern: https://martinfowler.com/bliki/CQRS.html
- Greg Young — Event Sourcing: https://martinfowler.com/eaaDev/EventSourcing.html

---

> **Catatan:** Untuk single-user system, SQLite-based event store cukup (tidak perlu Kafka). Event sourcing paling valuable untuk audit trail dan replay capability. CQRS projections optional untuk single-user, tapi valuable untuk query performance.
