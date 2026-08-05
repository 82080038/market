# Market Data Distribution Architecture untuk Trading System

> **Dokumen 66** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Arsitektur distribusi data pasar dari system ke end user — ticker plant, WebSocket fan-out, delta encoding, coalescing, price tick validation, dan CDN/edge caching untuk historical data.
>
> **Konteks:** Dokumen 22 covers data **ingestion** (dari exchange ke system). Dokumen ini covers data **distribution** (dari system ke end user). Critical untuk real-time price feed yang smooth dan reliable di aplikasi mobile/web.

---

## Daftar Isi

1. [Ticker Plant Architecture](#1-ticker-plant-architecture)
2. [WebSocket vs SSE](#2-websocket-vs-sse)
3. [Connection Pooling & Sharding](#3-connection-pooling--sharding)
4. [Delta Encoding](#4-delta-encoding)
5. [Coalescing & Throttling](#5-coalescing--throttling)
6. [Price Tick Validation](#6-price-tick-validation)
7. [CDN/Edge Caching](#7-cdnedge-caching)
8. [Implementasi](#8-implementasi)
9. [Adopsi dari Codebase Existing](#9-adopsi-dari-codebase-existing)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Ticker Plant Architecture

### 1.1 Konsep

Ticker plant = komponen yang menerima raw market data, memvalidasi, menormalisasi, dan mendistribusikan ke subscribers.

```
┌──────────────────────────────────────────────────────────────┐
│                   TICKER PLANT ARCHITECTURE                   │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ Yahoo    │  │ IDX      │  │ Broker   │                   │
│  │ Finance  │  │ Scraper  │  │ API      │                   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
│       │             │             │                          │
│       ▼             ▼             ▼                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              INGESTION LAYER                         │   │
│  │  ├── Parse & validate                                │   │
│  │  ├── Normalize to standard format                    │   │
│  │  ├── Deduplicate                                     │   │
│  │  └── Sequence number assignment                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              TICKER PLANT CORE                       │   │
│  │  ├── Latest price cache (per ticker)                 │   │
│  │  ├── Tick validation (bad tick, gap detection)       │   │
│  │  ├── Coalescing window (batch updates)               │   │
│  │  └── Distribution fan-out                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                         │                                    │
│          ┌──────────────┼──────────────┐                    │
│          ▼              ▼              ▼                    │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐           │
│  │  WebSocket   │ │  REST    │ │  Event Bus   │           │
│  │  Gateway     │ │  Cache   │ │  (internal)  │           │
│  │  (real-time) │ │  (poll)  │ │              │           │
│  └──────────────┘ └──────────┘ └──────────────┘           │
│         │                                              │
│         ▼                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              CLIENT DEVICES                          │   │
│  │  ├── Mobile app (Flutter)                            │   │
│  │  ├── Web app (Next.js)                               │   │
│  │  └── Desktop (future)                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Implementasi

```python
class TickerPlant:
    """Central ticker plant for market data distribution."""

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.latest_prices: dict[str, dict] = {}  # ticker → latest tick
        self.subscribers: dict[str, set[callable]] = {}  # ticker → callbacks
        self.coalesce_buffer: dict[str, dict] = {}
        self.last_flush = datetime.now(UTC)
        self.coalesce_window_ms = 100  # Batch updates in 100ms windows

    def ingest_tick(self, ticker: str, price: float, volume: int,
                     source: str, bid: float | None = None,
                     ask: float | None = None) -> dict:
        """Ingest a market data tick."""
        # 1. Validate tick
        validation = self._validate_tick(ticker, price, volume)
        if not validation["valid"]:
            return {"status": "rejected", "reason": validation["reason"]}

        # 2. Check if price actually changed
        prev = self.latest_prices.get(ticker)
        if prev and prev["price"] == price and prev["volume"] == volume:
            return {"status": "duplicate", "message": "No change"}

        # 3. Create tick record
        tick = {
            "ticker": ticker,
            "price": price,
            "volume": volume,
            "bid": bid,
            "ask": ask,
            "source": source,
            "change_pct": self._compute_change_pct(ticker, price),
            "timestamp": datetime.now(UTC).isoformat(),
            "sequence": self._next_sequence(ticker),
        }

        # 4. Update latest price cache
        self.latest_prices[ticker] = tick

        # 5. Add to coalesce buffer
        self.coalesce_buffer[ticker] = tick

        # 6. Check if flush needed
        elapsed = (datetime.now(UTC) - self.last_flush).total_seconds() * 1000
        if elapsed >= self.coalesce_window_ms:
            self._flush()

        return {"status": "accepted", "tick": tick}

    def _validate_tick(self, ticker: str, price: float, volume: int) -> dict:
        """Validate tick data."""
        if price <= 0:
            return {"valid": False, "reason": "invalid_price"}
        if price > 100_000_000:  > Rp 100M per share = suspicious
            return {"valid": False, "reason": "price_too_high"}

        # Check against previous price for sudden jump
        prev = self.latest_prices.get(ticker)
        if prev:
            change_pct = abs(price - prev["price"]) / prev["price"]
            if change_pct > 0.25:  # > 25% change in single tick
                return {"valid": False, "reason": f"suspicious_jump: {change_pct:.1%}"}

        return {"valid": True}

    def _flush(self):
        """Flush coalesced ticks to subscribers."""
        if not self.coalesce_buffer:
            return

        ticks = list(self.coalesce_buffer.values())
        self.coalesce_buffer.clear()
        self.last_flush = datetime.now(UTC)

        # Distribute to subscribers
        for tick in ticks:
            ticker = tick["ticker"]
            for callback in self.subscribers.get(ticker, []):
                try:
                    callback(tick)
                except Exception as e:
                    logger.error(f"Subscriber callback error: {e}")

        # Also publish to event bus
        for tick in ticks:
            self._publish_event("marketdata.tick", tick)

    def subscribe(self, ticker: str, callback: callable):
        """Subscribe to tick updates for a ticker."""
        self.subscribers.setdefault(ticker, set()).add(callback)

    def unsubscribe(self, ticker: str, callback: callable):
        """Unsubscribe from tick updates."""
        if ticker in self.subscribers:
            self.subscribers[ticker].discard(callback)
```

---

## 2. WebSocket vs SSE

### 2.1 Comparison

| Aspek | WebSocket | SSE (Server-Sent Events) |
|-------|-----------|-------------------------|
| **Direction** | Bidirectional (full-duplex) | Unidirectional (server→client) |
| **Use case** | Real-time price + order submission | Price feed only (no order submission) |
| **Reconnection** | Manual | Auto (browser built-in) |
| **Protocol** | ws:// / wss:// | HTTP (text/event-stream) |
| **Proxy compatibility** | ⚠️ Some proxies block | ✅ Standard HTTP |
| **Mobile battery** | ⚠️ Keep-alive drains battery | ✅ More efficient |
| **Max connections** | ~6 per domain (HTTP/1.1) | Same, but HTTP/2 solves |
| **Best for** | Trading app (need send orders) | Watchlist price feed |

### 2.2 Rekomendasi

- **Trading app**: WebSocket (butuh kirim order)
- **Watchlist only**: SSE (lebih efficient untuk mobile)
- **Hybrid**: SSE untuk price feed, REST untuk order submission

### 2.3 WebSocket Implementation

```python
class MarketDataWebSocketGateway:
    """WebSocket gateway for real-time market data distribution."""

    def __init__(self, ticker_plant: TickerPlant):
        self.ticker_plant = ticker_plant
        self.connections: dict[str, set[WebSocket]] = {}  # ticker → websockets
        self.user_subscriptions: dict[WebSocket, set[str]] = {}  # ws → tickers

    async def handle_connection(self, ws: WebSocket):
        """Handle WebSocket connection lifecycle."""
        await ws.accept()
        self.user_subscriptions[ws] = set()

        try:
            while True:
                message = await ws.receive_json()
                await self._handle_message(ws, message)
        except WebSocketDisconnect:
            self._cleanup(ws)

    async def _handle_message(self, ws: WebSocket, message: dict):
        """Handle incoming WebSocket message."""
        msg_type = message.get("type")

        if msg_type == "subscribe":
            tickers = message.get("tickers", [])
            for ticker in tickers:
                await self._subscribe(ws, ticker)

        elif msg_type == "unsubscribe":
            tickers = message.get("tickers", [])
            for ticker in tickers:
                await self._unsubscribe(ws, ticker)

        elif msg_type == "ping":
            await ws.send_json({"type": "pong"})

    async def _subscribe(self, ws: WebSocket, ticker: str):
        """Subscribe WebSocket to ticker updates."""
        self.connections.setdefault(ticker, set()).add(ws)
        self.user_subscriptions[ws].add(ticker)

        # Send latest price immediately
        latest = self.ticker_plant.latest_prices.get(ticker)
        if latest:
            await ws.send_json({
                "type": "tick",
                "data": latest,
            })

        # Register callback for future updates
        async def on_tick(tick: dict):
            await self._broadcast_to_ticker(ticker, tick)

        self.ticker_plant.subscribe(ticker, on_tick)

    async def _broadcast_to_ticker(self, ticker: str, tick: dict):
        """Broadcast tick to all subscribers of a ticker."""
        subscribers = self.connections.get(ticker, set())
        dead = []
        for ws in subscribers:
            try:
                await ws.send_json({
                    "type": "tick",
                    "data": tick,
                })
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._cleanup(ws)

    def _cleanup(self, ws: WebSocket):
        """Clean up WebSocket connection."""
        tickers = self.user_subscriptions.pop(ws, set())
        for ticker in tickers:
            if ticker in self.connections:
                self.connections[ticker].discard(ws)
```

---

## 3. Connection Pooling & Sharding

### 3.1 Problem

Single WebSocket server punya limit ~10,000 concurrent connections. Untuk scale ke 100K+ users, butuh sharding.

### 3.2 Sharding Strategy

```python
class WebSocketShardManager:
    """Manage WebSocket connections across multiple shards."""

    def __init__(self, num_shards: int = 8):
        self.num_shards = num_shards
        self.shards: dict[int, set[str]] = {i: set() for i in range(num_shards)}

    def get_shard(self, ticker: str) -> int:
        """Determine which shard handles a ticker."""
        return hash(ticker) % self.num_shards

    def assign_connection(self, user_id: str, tickers: list[str]) -> dict:
        """Assign user connection to appropriate shards."""
        shard_assignments = {}
        for ticker in tickers:
            shard = self.get_shard(ticker)
            shard_assignments.setdefault(shard, []).append(ticker)
            self.shards[shard].add(user_id)

        return {
            "shards": shard_assignments,
            "total_shards": len(shard_assignments),
        }
```

### 3.3 Architecture

```
                    User connects
                         │
                         ▼
              ┌─────────────────────┐
              │  Load Balancer       │
              │  (sticky session)    │
              └──────────┬──────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Shard 0  │  │ Shard 1  │  │ Shard 2  │  ...
    │ BBCA,    │  │ TLKM,    │  │ ASII,    │
    │ BBRI     │  │ UNVR     │  │ BMRI     │
    └──────────┘  └──────────┘  └──────────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
                    Redis Pub/Sub
                    (cross-shard)
```

---

## 4. Delta Encoding

### 4.1 Konsep

Daripada kirim full tick setiap update, kirim hanya **apa yang berubah**:

```json
// Full tick (traditional)
{"ticker": "BBCA.JK", "price": 8450, "volume": 1000, "bid": 8440, "ask": 8460, "change_pct": 1.2}

// Delta encoding (efficient)
{"t": "BBCA.JK", "p": 8450, "v": 1000}  // Only changed fields
```

### 4.2 Implementasi

```python
class DeltaEncoder:
    """Encode market data updates as deltas to reduce bandwidth."""

    FIELD_MAP = {
        "t": "ticker",
        "p": "price",
        "v": "volume",
        "b": "bid",
        "a": "ask",
        "c": "change_pct",
    }

    def __init__(self):
        self.last_sent: dict[str, dict] = {}  # ticker → last full update

    def encode(self, tick: dict) -> dict:
        """Encode tick as delta from last sent."""
        ticker = tick["ticker"]
        last = self.last_sent.get(ticker, {})

        delta = {"t": ticker}
        for short, full in self.FIELD_MAP.items():
            if full == "ticker":
                continue
            current = tick.get(full)
            previous = last.get(full)
            if current != previous and current is not None:
                delta[short] = current

        self.last_sent[ticker] = tick
        return delta

    def decode(self, delta: dict) -> dict:
        """Decode delta back to full tick."""
        ticker = delta.get("t")
        if not ticker:
            return delta

        last = self.last_sent.get(ticker, {})
        full = {"ticker": ticker}

        for short, full_name in self.FIELD_MAP.items():
            if short in delta:
                full[full_name] = delta[short]
            elif full_name in last:
                full[full_name] = last[full_name]

        self.last_sent[ticker] = full
        return full
```

### 4.3 Bandwidth Savings

| Method | Size per tick | Savings |
|--------|--------------|---------|
| Full JSON | ~120 bytes | 0% |
| Delta encoded | ~40 bytes | **67%** |
| Delta + gzip | ~25 bytes | **79%** |
| Protobuf | ~15 bytes | **87%** |

---

## 5. Coalescing & Throttling

### 5.1 Problem

Saat market aktif, tick bisa datang 10-50x per detik per ticker. Kirim semua ke client = battery drain + bandwidth waste.

### 5.2 Coalescing Strategy

```python
class TickCoalescer:
    """Coalesce multiple ticks into periodic updates."""

    def __init__(self, window_ms: int = 100, max_ticks: int = 50):
        self.window_ms = window_ms
        self.max_ticks = max_ticks
        self.buffer: dict[str, dict] = {}  # ticker → latest tick
        self.last_flush = datetime.now(UTC)
        self.flush_callback: callable | None = None

    def submit(self, tick: dict):
        """Submit tick to coalescer."""
        self.buffer[tick["ticker"]] = tick

        # Flush if window elapsed or buffer full
        elapsed = (datetime.now(UTC) - self.last_flush).total_seconds() * 1000
        if elapsed >= self.window_ms or len(self.buffer) >= self.max_ticks:
            self.flush()

    def flush(self):
        """Flush coalesced ticks."""
        if not self.buffer or not self.flush_callback:
            return

        ticks = list(self.buffer.values())
        self.buffer.clear()
        self.last_flush = datetime.now(UTC)
        self.flush_callback(ticks)
```

### 5.3 Throttling per Client

| Client Type | Update Frequency | Strategy |
|-------------|-----------------|----------|
| **Active trader** (app open, viewing chart) | 100ms (10 fps) | Coalesce 100ms |
| **Passive** (app in background) | 5s | Coalesce 5s |
| **Watchlist** (scrolling) | 500ms | Coalesce 500ms |
| **Push notification** | Event-based | Only on alert trigger |

---

## 6. Price Tick Validation

### 6.1 Validation Pipeline

```
Raw tick arrives
    │
    ▼
1. Format validation (price > 0, volume >= 0)
    │
    ▼
2. Plausibility check (price within reasonable range)
    │
    ▼
3. Jump detection (change < 25% from previous)
    │
    ▼
4. Sequence check (sequence number = prev + 1)
    │
    ▼
5. Cross-reference (compare with other sources)
    │
    ▼
6. Auto-reject check (within IDX ±20% range)
    │
    ▼
Accepted → Distribute to subscribers
```

### 6.2 Bad Tick Handling

```python
class TickValidator:
    """Validate market data ticks before distribution."""

    MAX_JUMP_PCT = 0.25  # 25% jump = suspicious
    AUTO_REJECT_PCT = 0.20  # IDX auto-reject ±20%

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.last_ticks: dict[str, dict] = {}

    def validate(self, tick: dict) -> dict:
        """Validate a tick. Returns validation result."""
        ticker = tick["ticker"]
        price = tick["price"]

        # 1. Format validation
        if price <= 0:
            return {"valid": False, "reason": "invalid_price", "action": "drop"}

        # 2. Plausibility
        if price > 100_000_000:
            return {"valid": False, "reason": "price_implausible", "action": "drop"}

        # 3. Jump detection
        prev = self.last_ticks.get(ticker)
        if prev:
            jump = abs(price - prev["price"]) / prev["price"]
            if jump > self.MAX_JUMP_PCT:
                return {
                    "valid": False,
                    "reason": f"suspicious_jump_{jump:.1%}",
                    "action": "quarantine",
                    "previous_price": prev["price"],
                }

        # 4. Auto-reject check
        ref_price = self.storage.get_reference_price(ticker)
        if ref_price:
            upper = ref_price * (1 + self.AUTO_REJECT_PCT)
            lower = ref_price * (1 - self.AUTO_REJECT_PCT)
            if price > upper or price < lower:
                return {
                    "valid": True,
                    "warning": "auto_reject_zone",
                    "action": "flag",
                }

        self.last_ticks[ticker] = tick
        return {"valid": True, "action": "distribute"}
```

---

## 7. CDN/Edge Caching

### 7.1 What to Cache

| Data Type | Cache Strategy | TTL |
|-----------|---------------|-----|
| **Historical chart data** (1yr, 5yr) | CDN edge cache | 1 hour |
| **Stock profile** (name, sector, ISIN) | CDN edge cache | 24 hours |
| **Fundamental data** (PE, ROE, etc.) | CDN edge cache | 1 hour |
| **Latest price** | Redis cache (not CDN) | 1 second |
| **Order book** | Redis only (not cacheable) | N/A |
| **News** | CDN edge cache | 5 minutes |

### 7.2 Implementation

```python
class MarketDataCache:
    """Multi-tier cache for market data distribution."""

    def __init__(self, redis_client, cdn_base_url: str):
        self.redis = redis_client
        self.cdn_base_url = cdn_base_url
        self.local_cache: dict[str, tuple] = {}  # LRU cache
        self.local_cache_max = 1000

    async def get_latest_price(self, ticker: str) -> dict | None:
        """Get latest price from Redis (hot cache)."""
        data = await self.redis.hgetall(f"price:{ticker}")
        if data:
            return {
                "ticker": ticker,
                "price": float(data["price"]),
                "volume": int(data["volume"]),
                "timestamp": data["timestamp"],
            }
        return None

    async def set_latest_price(self, ticker: str, tick: dict):
        """Set latest price in Redis."""
        await self.redis.hset(f"price:{ticker}", mapping={
            "price": tick["price"],
            "volume": tick["volume"],
            "timestamp": tick["timestamp"],
        })
        await self.redis.expire(f"price:{ticker}", 60)  # TTL 60s

    async def get_historical_chart(self, ticker: str,
                                     period: str = "1Y") -> str:
        """Get historical chart data from CDN."""
        url = f"{self.cdn_base_url}/charts/{ticker}_{period}.json"
        # Client fetches from CDN directly (edge cached)
        return url
```

---

## 8. Implementasi

### 8.1 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `GET /api/data/price/{ticker}` | GET | Get latest price (REST, cached) |
| `GET /api/data/ohlcv?ticker=&period=` | GET | Get historical OHLCV |
| `GET /api/data/quote/{ticker}` | GET | Get full quote (bid/ask/volume) |
| `WS /ws/prices` | WS | Subscribe to real-time price updates |
| `WS /ws/quotes` | WS | Subscribe to real-time quote updates |
| `GET /api/data/snapshot` | GET | Get price snapshot for multiple tickers |

### 8.2 WebSocket Message Protocol

```json
// Client → Server: Subscribe
{"type": "subscribe", "tickers": ["BBCA.JK", "TLKM.JK"]}

// Server → Client: Initial snapshot
{"type": "snapshot", "data": {"BBCA.JK": {"p": 8450, "v": 1000}, "TLKM.JK": {"p": 3200, "v": 500}}}

// Server → Client: Delta update
{"type": "delta", "data": {"t": "BBCA.JK", "p": 8460, "v": 1200}}

// Client → Server: Unsubscribe
{"type": "unsubscribe", "tickers": ["TLKM.JK"]}

// Server → Client: Heartbeat
{"type": "heartbeat", "timestamp": "2026-08-05T03:00:00Z"}
```

---

## 9. Adopsi dari Codebase Existing

| Module Existing | Modifikasi |
|----------------|-----------|
| `api/app.py` | Tambah WebSocket endpoints untuk price feed |
| `data/acquisition.py` | Integrate dengan TickerPlant |
| `data/storage.py` | Tambah price cache tables |
| `monitoring/engine.py` | Monitor ticker plant health |

**New modules:**
- `distribution/ticker_plant.py` — Central ticker plant
- `distribution/websocket_gateway.py` — WebSocket gateway
- `distribution/delta_encoder.py` — Delta encoding
- `distribution/coalescer.py` — Tick coalescing
- `distribution/validator.py` — Tick validation
- `distribution/cache.py` — Multi-tier cache

---

## 10. Checklist Implementasi

### Phase 1: Ticker Plant (3-4 minggu)

- [ ] `TickerPlant` class (ingest, validate, cache)
- [ ] `TickValidator` (format, plausibility, jump detection)
- [ ] Integration dengan existing data acquisition
- [ ] Redis cache for latest prices

### Phase 2: WebSocket Gateway (3-4 minggu)

- [ ] `MarketDataWebSocketGateway` (pub/sub)
- [ ] Subscribe/unsubscribe protocol
- [ ] Connection management (cleanup, heartbeat)
- [ ] API: `WS /ws/prices`

### Phase 3: Optimization (2-3 minggu)

- [ ] `DeltaEncoder` (reduce bandwidth 67%)
- [ ] `TickCoalescer` (batch updates, reduce frequency)
- [ ] Client-specific throttling (active vs passive)
- [ ] Gzip compression

### Phase 4: Caching & Scale (2-3 minggu)

- [ ] Multi-tier cache (local → Redis → CDN)
- [ ] CDN setup for historical chart data
- [ ] Connection sharding (for scale)
- [ ] Performance test under load

---

## 11. Stale Data Detection & 7-State Market Data Model

> **Gap teridentifikasi:** Dokumen ini membahas tick validation (§6) dan coalescing (§5) tetapi tidak membahas stale data detection — kondisi di mana feed terlihat connected tetapi data sudah basi. Stale data lebih berbahaya dari disconnected feed karena terlihat normal.

### 11.1 Mengapa Stale Data Berbahaya

```
SCENARIO: Stale Book
  Feed status:    CONNECTED ✓
  Last update:    45 detik lalu
  Market moved:   +2.3% since last tick
  Your stop-loss: Masih di harga lama (sudah breached di market)
  Your limit:      Masih di harga lama (sudah passed di market)
  Hasil:          Order di harga yang sudah tidak relevan
```

Stale data adalah **silent failure** — tidak ada error, tidak ada disconnect, tapi data sudah tidak mencerminkan realitas pasar.

### 11.2 7-State Market Data Model

Setiap quote harus diberi label state yang menentukan behavior aplikasi:

| State | Meaning | App Behavior | Trigger |
|-------|---------|-------------|---------|
| **LIVE** | WebSocket updates fresh (≤3s) | Tampilkan harga normal | Quote age ≤ 3s |
| **DEGRADED** | Update mulai lambat (>3s) | Tampilkan harga, monitor ketat | Quote age 3-10s |
| **STALE** | Data terlalu lama untuk trust | Request fallback snapshot | Quote age > 10s |
| **FALLBACK** | REST snapshot dipakai karena WS stale | Tampilkan label "fallback" | REST snapshot berhasil setelah stale |
| **RECOVERING** | WS resume tapi belum confirmed | Tunggu 3 tick fresh sebelum live | WS updates resume setelah fallback |
| **DEAD** | Tidak ada harga reliable | Block trading, suppress alert | WS stale + REST fallback gagal |
| **MARKET_CLOSED** | Session tutup, tick tidak expected | Tampilkan harga close terakhir | Market status = closed |

### 11.3 Implementasi State Machine

```python
class MarketDataState:
    """7-state market data freshness tracker."""

    THRESHOLDS = {
        "live": 3,        # seconds
        "degraded": 10,   # seconds
        "stale": 30,      # seconds
    }

    def __init__(self):
        self.quotes = {}  # symbol → QuoteState

    def update_quote(self, symbol: str, price: float, source: str = "ws"):
        """Called when new tick arrives."""
        q = self.quotes.setdefault(symbol, QuoteState(symbol))
        q.price = price
        q.source = source
        q.exchange_ts = time.time()
        q.received_ts = time.time()
        if q.state == "FALLBACK" and source == "ws":
            q.recovery_ticks += 1
            if q.recovery_ticks >= 3:
                q.state = "LIVE"
                q.recovery_ticks = 0
        elif source == "ws":
            q.state = "LIVE"

    def check_state(self, symbol: str, market_open: bool) -> str:
        """Determine current state based on age."""
        if not market_open:
            return "MARKET_CLOSED"
        q = self.quotes.get(symbol)
        if not q:
            return "DEAD"
        age = time.time() - q.received_ts
        if age <= self.THRESHOLDS["live"]:
            return "LIVE"
        elif age <= self.THRESHOLDS["degraded"]:
            return "DEGRADED"
        elif age <= self.THRESHOLDS["stale"]:
            return "STALE"
        else:
            return "DEAD"
```

### 11.4 Quote Metadata Schema

Setiap quote yang dikirim ke frontend/decision engine harus membawa metadata:

| Field | Why It Matters |
|-------|---------------|
| `symbol` | Identifikasi instrumen |
| `price` | Nilai harga terbaru |
| `source` | `ws` / `rest_fallback` / `cached` / `prev_close` — mencegah fallback dikira live |
| `exchange_timestamp` | Kapan event terjadi di exchange |
| `received_timestamp` | Kapan aplikasi menerima |
| `age_seconds` | Umur data — mencegah stale dikira fresh |
| `state` | LIVE/DEGRADED/STALE/FALLBACK/RECOVERING/DEAD/MARKET_CLOSED |
| `action` | display / display_with_warning / block_trading / suppress_alert |

### 11.5 Heartbeat Detection per Symbol

```python
class HeartbeatMonitor:
    """Per-symbol freshness monitoring."""

    def __init__(self, expected_interval: dict = None):
        # Default: expect update every 5s during market hours
        self.expected = expected_interval or {"default": 5.0}
        self.last_update = {}  # symbol → timestamp

    def on_tick(self, symbol: str):
        self.last_update[symbol] = time.time()

    def is_stale(self, symbol: str, threshold_multiplier: float = 3.0) -> bool:
        """Stale if no update for N * expected_interval."""
        last = self.last_update.get(symbol)
        if not last:
            return True
        expected = self.expected.get(symbol, self.expected["default"])
        age = time.time() - last
        return age > expected * threshold_multiplier
```

### 11.6 Sequence Number Monitoring

Jika data source menyediakan sequence number (e.g., IDX DataFeed), wajib dimonitor:

```python
def check_sequence(self, symbol: str, seq: int) -> bool:
    """Returns True if sequence is valid (no gap)."""
    expected = self.last_seq.get(symbol, -1) + 1
    if seq < expected:
        return False  # Duplicate or reorder — discard
    if seq > expected:
        self._on_gap_detected(symbol, expected, seq)  # Gap — trigger recovery
        return False
    self.last_seq[symbol] = seq
    return True
```

| Condition | Meaning | Action |
|-----------|---------|--------|
| `seq == expected` | Normal | Apply delta |
| `seq < expected` | Duplicate/reorder | Discard |
| `seq > expected` | Gap (missed messages) | Stop applying, trigger snapshot recovery |

### 11.7 Frontend Behavior per State

| State | UI Display | Trading | Alert |
|-------|-----------|---------|-------|
| LIVE | Harga normal, hijau | Enabled | Normal |
| DEGRADED | Harga normal, kuning "delayed" | Enabled dengan warning | Warning |
| STALE | Harga abu-abu "stale" | Disabled | Warning + auto-request fallback |
| FALLBACK | Harga dengan label "fallback" | Disabled | Info |
| RECOVERING | Harga dengan label "recovering" | Disabled | Info |
| DEAD | "Tidak ada data" | Blocked | Critical |
| MARKET_CLOSED | Harga close + "Pasar Tutup" | Disabled | Normal |

### 11.8 5W1H

| Aspect | Detail |
|--------|--------|
| **What** | 7-state market data freshness model + stale detection + heartbeat monitoring |
| **Why** | Stale data lebih berbahaya dari disconnected — terlihat hidup tapi sudah basi. Stop-loss di harga stale = loss tidak terkendali |
| **When** | Setiap tick yang masuk dan setiap query harga oleh frontend/decision engine |
| **Where** | Ticker plant, WebSocket gateway, frontend price display, pre-trade validation |
| **Who** | Market data engineer + frontend engineer |
| **How** | Age-based state transition + heartbeat per symbol + sequence number gap detection + REST fallback path |

---

## Referensi

### Internal
- `22-data-engineering-pipeline.md` — Data ingestion pipeline
- `28-api-design-integration-patterns.md` — WebSocket, REST patterns
- `34-performance-engineering-optimization.md` — Caching, async I/O
- `36-gap-data-timezone-global-idx.md` — Data delay per provider
- `43-mobile-app-architecture.md` — Mobile app data consumption
- `65-event-driven-event-sourcing.md` — Event-driven architecture

### External
- WebSocket Protocol — https://datatracker.ietf.org/doc/html/rfc6455
- Server-Sent Events — https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- Redis Pub/Sub — https://redis.io/docs/interprocess/pubsub/
- Cloudflare CDN — https://www.cloudflare.com/cdn/
- **EODHD Academy — Real-Time Market Data Reliability: Stale Price Detection, REST Fallback, WebSocket Recovery**
- **NexusFi Academy — Data Quality and Integrity in Futures Trading (stale book, sequence gaps, heartbeat)**
- **NexusFi Academy — Market Data Handling for Automated Trading Systems (staleness detection, tick-size compliance)**

---

> **Catatan:** Untuk single-user system, WebSocket gateway cukup simple (1 connection). Ticker plant dan delta encoding tetap valuable untuk bandwidth optimization. Coalescing critical untuk mobile battery efficiency. Tick validation wajib untuk mencegah bad data mencapai decision engine. **Stale data detection (§11)** adalah pertahanan terakhir — data yang terlihat hidup tapi sudah basi lebih berbahaya dari data yang jelas putus.
