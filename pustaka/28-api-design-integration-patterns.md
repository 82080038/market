# API Design & Integration Patterns untuk Trading System

> **Tujuan:** Dokumen ini adalah referensi definitif untuk desain API dan pola integrasi sistem trading — REST API design, WebSocket real-time, FIX protocol, broker API integration, event-driven architecture, dan pola komunikasi antar service — dengan fokus pada aplikasi trading pasar modal Indonesia.

---

## Daftar Isi

1. [API Architecture Overview](#1-api-architecture-overview)
2. [REST API Design](#2-rest-api-design)
3. [WebSocket Real-Time](#3-websocket-real-time)
4. [FIX Protocol](#4-fix-protocol)
5. [Broker API Integration](#5-broker-api-integration)
6. [Event-Driven Architecture](#6-event-driven-architecture)
7. [Authentication & Authorization](#7-authentication--authorization)
8. [Error Handling & Status Codes](#8-error-handling--status-codes)
9. [API Versioning & Documentation](#9-api-versioning--documentation)
10. [Integration Patterns](#10-integration-patterns)
11. [Rate Limiting & Throttling](#11-rate-limiting--throttling)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. API Architecture Overview

### 1.1 Layered API Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    CLIENT LAYER                           │
│  Web (Next.js) │ Mobile │ CLI │ Third-party integrations │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                 GATEWAY LAYER                             │
│  Nginx (TLS, Rate Limit, CORS, Security Headers)         │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                  API LAYER (FastAPI)                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│  │  Auth   │ │  REST   │ │WebSocket│ │Middleware│        │
│  │Middleware│ │Endpoints│ │ Events  │ │  (CORS) │        │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘        │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│               SERVICE LAYER                               │
│  DecisionEngine │ RiskEngine │ ExecutionEngine │ ...     │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│               DATA LAYER                                  │
│  SQLite (WAL) │ Parquet │ Redis Cache                    │
└──────────────────────────────────────────────────────────┘
```

### 1.2 API Categories

| Category | Prefix | Purpose | Auth |
|----------|--------|---------|------|
| **Public** | `/api/` | Market data, health, tickers | API Key |
| **Trading** | `/api/trade/` | Order placement, positions | API Key + confirmation |
| **Analysis** | `/api/scores/` | Compute scores, recommendations | API Key |
| **Admin** | `/api/admin/` | System config, engine control | Admin Key |
| **WebSocket** | `/ws` | Real-time updates | Token |

---

## 2. REST API Design

### 2.1 Design Principles

| Principle | Description | Example |
|-----------|-------------|---------|
| **Resource-oriented** | URL = noun, HTTP method = verb | `GET /api/data/ohlcv?ticker=BBCA.JK` |
| **Stateless** | No server-side session | Each request carries auth |
| **Cacheable** | ETag/Cache-Control headers | `Cache-Control: max-age=300` |
| **Layered** | Client doesn't know about backend layers | Transparent proxy support |
| **Uniform interface** | Consistent response format | `{status, data, error}` |

### 2.2 Endpoint Design

```python
# RESTful resource naming
GET    /api/tickers                    # List all tickers
GET    /api/tickers/{ticker}           # Get specific ticker info
GET    /api/data/{category}            # Get data (ohlcv, macro, etc.)
GET    /api/data/ohlcv?ticker={ticker} # Get OHLCV for ticker
GET    /api/indicators/{ticker}        # Get technical indicators
GET    /api/scores/{ticker}            # Get latest scores
POST   /api/scores/compute             # Compute scores
GET    /api/recommend/{ticker}         # Get recommendation
GET    /api/explain/{ticker}           # Get XAI explanation
GET    /api/positions                  # List open positions
POST   /api/trade/order                # Place order
DELETE /api/trade/order/{order_id}     # Cancel order
GET    /api/portfolio                  # Get portfolio summary
POST   /api/backtest                   # Run backtest
GET    /api/health                     # Health check
GET    /api/monitor                    # System monitoring
WS     /ws                             # WebSocket connection
```

### 2.3 Response Format

```python
# Standard success response
{
    "status": "ok",
    "data": { ... },
    "meta": {
        "count": 100,
        "page": 1,
        "page_size": 50,
        "total_pages": 2,
    },
    "timestamp": "2026-08-04T10:30:00+07:00",
}

# Standard error response
{
    "status": "error",
    "error": {
        "code": "NOT_FOUND",
        "message": "Ticker not found: INVALID.JK",
        "details": { ... },
    },
    "timestamp": "2026-08-04T10:30:00+07:00",
}
```

### 2.4 Pagination

```python
@app.get("/api/data/ohlcv")
async def get_ohlcv(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 1000,
    api_key: str = Depends(get_api_key),
):
    """Get OHLCV data with pagination."""
    offset = (page - 1) * page_size
    
    df = storage.load_ohlcv(ticker, start_date, end_date)
    total = len(df)
    
    paginated = df.iloc[offset:offset + page_size]
    
    return {
        "status": "ok",
        "data": paginated.to_dict("records"),
        "meta": {
            "count": len(paginated),
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
```

### 2.5 Filtering & Sorting

```python
@app.get("/api/tickers")
async def list_tickers(
    sector: str | None = None,
    is_active: bool = True,
    asset_class: str = "equity",
    sort_by: str = "ticker",
    sort_order: str = "asc",
    api_key: str = Depends(get_api_key),
):
    """List tickers with filtering and sorting."""
    query = "SELECT * FROM instrument_master WHERE 1=1"
    params = []
    
    if sector:
        query += " AND sector = ?"
        params.append(sector)
    if is_active is not None:
        query += " AND is_active = ?"
        params.append(1 if is_active else 0)
    if asset_class:
        query += " AND asset_class = ?"
        params.append(asset_class)
    
    sort_column = sort_by if sort_by in ["ticker", "sector", "market_cap"] else "ticker"
    sort_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
    query += f" ORDER BY {sort_column} {sort_dir}"
    
    results = storage.execute_query(query, params)
    return {"status": "ok", "data": results, "meta": {"count": len(results)}}
```

---

## 3. WebSocket Real-Time

### 3.1 WebSocket Architecture

```python
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {
            "prices": [],
            "signals": [],
            "portfolio": [],
            "alerts": [],
        }
    
    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel in self.active_connections:
            self.active_connections[channel].append(websocket)
    
    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            self.active_connections[channel].remove(websocket)
    
    async def broadcast(self, channel: str, message: dict):
        for connection in self.active_connections.get(channel, []):
            await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
```

### 3.2 WebSocket Channels

| Channel | Data | Frequency | Client |
|---------|------|-----------|--------|
| `prices` | Real-time price updates | On change | Dashboard |
| `signals` | Trading signals | On signal | Trading UI |
| `portfolio` | Position updates | On trade | Portfolio UI |
| `alerts` | System alerts | On alert | Notification panel |
| `scores` | Score updates | On compute | Analysis UI |

### 3.3 Message Format

```json
{
    "channel": "signals",
    "type": "trading_signal",
    "data": {
        "ticker": "BBCA.JK",
        "action": "BUY",
        "conviction": 72.5,
        "entry_range": [8425, 8475],
        "stop_loss": 8200,
        "take_profit": 8800,
        "scores": {
            "technical": 65,
            "fundamental": 80,
            "macro": 70,
            "global": 55,
            "relationship": 40,
            "sentiment": 60
        }
    },
    "timestamp": "2026-08-04T10:30:00+07:00"
}
```

### 3.4 Heartbeat

```python
import asyncio

async def heartbeat(websocket: WebSocket, interval: int = 30):
    """Send periodic heartbeat to keep connection alive."""
    while True:
        await asyncio.sleep(interval)
        try:
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()})
        except Exception:
            break
```

---

## 4. FIX Protocol

### 4.1 Overview

FIX (Financial Information eXchange) adalah standard messaging protocol untuk electronic trading.

| FIX Version | Use Case | IDX Relevance |
|-------------|----------|---------------|
| **FIX 4.2** | Order management | Most common |
| **FIX 4.4** | Extended order types | Richer functionality |
| **FIX 5.0** | Session + application split | Modern |
| **FIX 5.0 SP2** | Latest standard | Future |

### 4.2 Key FIX Messages

| MsgType | Message | Direction |
|---------|---------|-----------|
| **D** | New Order Single | Client → Broker |
| **8** | Execution Report | Broker → Client |
| **F** | Order Cancel Request | Client → Broker |
| **9** | Order Cancel Reject | Broker → Client |
| **G** | Order Cancel/Replace | Client → Broker |
| **0** | Heartbeat | Both |
| **1** | Test Request | Both |
| **A** | Logon | Both |
| **5** | Logout | Both |

### 4.3 FIX Message Structure

```
8=FIX.4.4|9=120|35=D|49=TRADER|56=BROKER|
11=ORDER001|21=1|55=BBCA.JK|54=1|38=1000|
40=2|44=8000|59=0|47=A|60=20260804-10:30:00|
10=123|
```

| Tag | Field | Value |
|-----|-------|-------|
| 8 | BeginString | FIX.4.4 |
| 9 | BodyLength | 120 |
| 35 | MsgType | D (New Order) |
| 49 | SenderCompID | TRADER |
| 56 | TargetCompID | BROKER |
| 11 | ClOrdID | ORDER001 |
| 55 | Symbol | BBCA.JK |
| 54 | Side | 1 (Buy) |
| 38 | OrderQty | 1000 |
| 40 | OrdType | 2 (Limit) |
| 44 | Price | 8000 |
| 59 | TimeInForce | 0 (Day) |
| 60 | TransactTime | 20260804-10:30:00 |
| 10 | CheckSum | 123 |

### 4.4 FIX for IDX (Future)

```python
class FIXAdapter:
    """FIX protocol adapter for IDX broker integration."""
    
    def create_new_order(self, ticker: str, side: str, qty: int, 
                         price: float, order_type: str = "LIMIT"):
        """Create FIX New Order Single message."""
        message = {
            "MsgType": "D",
            "SenderCompID": self.sender_id,
            "TargetCompID": self.broker_id,
            "ClOrdID": self._gen_order_id(),
            "Symbol": ticker,
            "Side": "1" if side == "BUY" else "2",
            "OrderQty": str(qty),
            "OrdType": "2" if order_type == "LIMIT" else "1",
            "Price": str(price) if order_type == "LIMIT" else None,
            "TimeInForce": "0",  # Day order
            "TransactTime": datetime.now(UTC).strftime("%Y%m%d-%H:%M:%S"),
        }
        return self._serialize(message)
```

> **Catatan:** FIX protocol saat ini belum umum untuk retail broker di Indonesia. Sebagian besar broker menggunakan REST API atau proprietary WebSocket. FIX lebih relevan untuk institusional.

---

## 5. Broker API Integration

### 5.1 Broker Adapter Pattern

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class BrokerOrder:
    ticker: str
    side: str          # BUY or SELL
    quantity: int
    price: float
    order_type: str    # MARKET, LIMIT
    time_in_force: str = "DAY"

@dataclass
class BrokerOrderResult:
    order_id: str
    status: str        # FILLED, PARTIAL, REJECTED, PENDING
    filled_qty: int
    filled_price: float
    fee: float
    timestamp: str

class BrokerAdapter(ABC):
    """Abstract base class for broker API integration."""
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with broker API."""
        pass
    
    @abstractmethod
    async def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        """Place an order with the broker."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> BrokerOrderResult:
        """Get order status."""
        pass
    
    @abstractmethod
    async def get_positions(self) -> list:
        """Get current positions from broker."""
        pass
    
    @abstractmethod
    async def get_account(self) -> dict:
        """Get account balance and info."""
        pass
```

### 5.2 Indonesian Broker Integrations

| Broker | API Type | Status | Notes |
|--------|----------|--------|-------|
| **Sinarmas** | REST API | Stub | In development |
| **BNI Sekuritas** | REST API | Stub | In development |
| **Mandiri Sekuritas** | REST API | Planned | |
| **BRI Danareksa** | REST API | Planned | |
| **Stockbit** | REST API | Planned | Retail-focused |
| **Mirae Asset** | REST API | Planned | |
| **Mock** | In-memory | ✅ Active | For testing |

### 5.3 Mock Broker Adapter

```python
class MockBrokerAdapter(BrokerAdapter):
    """Mock broker for testing and development."""
    
    def __init__(self):
        self.orders = {}
        self.positions = {}
        self.cash = 100_000_000  # Rp 100M
        self.order_counter = 0
    
    async def authenticate(self) -> bool:
        return True
    
    async def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        self.order_counter += 1
        order_id = f"MOCK-{self.order_counter:06d}"
        
        # Simulate fill
        result = BrokerOrderResult(
            order_id=order_id,
            status="FILLED",
            filled_qty=order.quantity,
            filled_price=order.price,
            fee=order.quantity * order.price * 0.0025,
            timestamp=datetime.now(UTC).isoformat(),
        )
        
        self.orders[order_id] = result
        
        # Update positions
        if order.side == "BUY":
            self.cash -= order.quantity * order.price + result.fee
            if order.ticker in self.positions:
                pos = self.positions[order.ticker]
                total_qty = pos["quantity"] + order.quantity
                pos["avg_price"] = (
                    (pos["quantity"] * pos["avg_price"] + order.quantity * order.price) 
                    / total_qty
                )
                pos["quantity"] = total_qty
            else:
                self.positions[order.ticker] = {
                    "quantity": order.quantity,
                    "avg_price": order.price,
                }
        else:  # SELL
            self.cash += order.quantity * order.price - result.fee
            if order.ticker in self.positions:
                self.positions[order.ticker]["quantity"] -= order.quantity
        
        return result
```

### 5.4 Real Broker Adapter (Sinarmas Example)

```python
class SinarmasBrokerAdapter(BrokerAdapter):
    """Sinarmas Sekuritas broker API adapter."""
    
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.token = None
    
    async def authenticate(self) -> bool:
        """Authenticate and get session token."""
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{self.base_url}/auth/login",
                json={"api_key": self.api_key, "api_secret": self.api_secret},
            )
            if response.status == 200:
                data = await response.json()
                self.token = data.get("token")
                return True
            return False
    
    async def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        """Place order via broker API."""
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "symbol": order.ticker,
            "side": order.side,
            "quantity": order.quantity,
            "price": order.price,
            "order_type": order.order_type,
        }
        
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{self.base_url}/orders",
                json=payload,
                headers=headers,
            )
            data = await response.json()
            return BrokerOrderResult(
                order_id=data["order_id"],
                status=data["status"],
                filled_qty=data.get("filled_qty", 0),
                filled_price=data.get("filled_price", 0),
                fee=data.get("fee", 0),
                timestamp=data.get("timestamp"),
            )
```

---

## 6. Event-Driven Architecture

### 6.1 Event Bus Topics

```python
EVENT_TOPICS = {
    # Data events
    "data.raw.ohlcv": "Raw OHLCV data ingested",
    "data.raw.macro": "Raw macro data ingested",
    "data.raw.news": "Raw news ingested",
    "data.clean.ohlcv": "Validated OHLCV data",
    "data.quality.score": "Data quality score computed",
    
    # Analysis events
    "analysis.technical.score": "Technical analysis score computed",
    "analysis.fundamental.score": "Fundamental analysis score computed",
    "analysis.macro.score": "Macro analysis score computed",
    "analysis.sentiment.score": "Sentiment analysis score computed",
    "analysis.relationship.score": "Relationship analysis score computed",
    
    # Decision events
    "decision.recommendation.created": "New recommendation generated",
    "decision.signal.generated": "Trading signal generated",
    
    # Execution events
    "execution.order.created": "Order created",
    "execution.order.filled": "Order filled",
    "execution.order.cancelled": "Order cancelled",
    "execution.position.opened": "Position opened",
    "execution.position.closed": "Position closed",
    "execution.stop_loss.triggered": "Stop loss triggered",
    "execution.take_profit.triggered": "Take profit triggered",
    "execution.trailing_stop.triggered": "Trailing stop triggered",
    "execution.halt.activated": "Trading halt activated",
    
    # Risk events
    "risk.limit.exceeded": "Risk limit exceeded",
    "risk.daily_loss.limit": "Daily loss limit reached",
    
    # System events
    "system.health.degraded": "System health degraded",
    "system.engine.error": "Engine error",
    "system.data.stale": "Data staleness detected",
}
```

### 6.2 Event Structure

```python
@dataclass
class Event:
    topic: str
    payload: dict
    timestamp: str
    source: str
    version: str = "1.0"
    
    def to_dict(self):
        return {
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "source": self.source,
            "version": self.version,
        }

# Example event
event = Event(
    topic="decision.recommendation.created",
    payload={
        "ticker": "BBCA.JK",
        "action": "BUY",
        "conviction": 72.5,
        "scores": {"technical": 65, "fundamental": 80, ...},
    },
    timestamp="2026-08-04T10:30:00+07:00",
    source="decision_engine",
)
```

### 6.3 Pub/Sub Pattern

```python
class EventBus:
    """Simple in-process event bus."""
    
    def __init__(self):
        self.subscribers: dict[str, list[Callable]] = {}
    
    def subscribe(self, topic: str, handler: Callable):
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(handler)
    
    async def publish(self, event: Event):
        handlers = self.subscribers.get(event.topic, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event.topic}: {e}")

# Usage
event_bus = EventBus()

# Subscribe
event_bus.subscribe("decision.recommendation.created", on_recommendation)
event_bus.subscribe("execution.order.filled", on_order_filled)

# Publish
await event_bus.publish(event)
```

### 6.4 External Message Queue (Future)

| Technology | Use Case | Complexity |
|------------|----------|------------|
| **Redis Pub/Sub** | Simple pub/sub | Low |
| **RabbitMQ** | Reliable message queue | Medium |
| **Apache Kafka** | High-throughput streaming | High |
| **Celery + Redis** | Task queue + result backend | Medium |

---

## 7. Authentication & Authorization

### 7.1 API Key Authentication

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def get_api_key(api_key: str = Security(api_key_header)):
    """Validate API key."""
    expected_key = os.getenv("API_KEY", "dev-secret-key-2026")
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key

# Apply to all endpoints
@app.get("/api/data/ohlcv", dependencies=[Depends(get_api_key)])
async def get_ohlcv(ticker: str):
    ...
```

### 7.2 JWT Authentication (Future)

```python
from datetime import datetime, timedelta
import jwt

def create_jwt_token(user_id: str, secret: str, expires_hours: int = 24) -> str:
    """Create JWT token."""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=expires_hours),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def verify_jwt_token(token: str, secret: str) -> dict:
    """Verify JWT token."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### 7.3 Role-Based Access Control

| Role | Permissions |
|------|------------|
| **Viewer** | Read market data, scores, recommendations |
| **Trader** | Viewer + place orders, manage positions |
| **Admin** | Trader + system config, engine control, user management |

---

## 8. Error Handling & Status Codes

### 8.1 HTTP Status Codes

| Code | Meaning | When to Use |
|------|---------|-------------|
| **200** | OK | Successful GET, POST |
| **201** | Created | Resource created |
| **204** | No Content | Successful DELETE |
| **400** | Bad Request | Invalid input, validation error |
| **401** | Unauthorized | Missing/invalid API key |
| **403** | Forbidden | Insufficient permissions |
| **404** | Not Found | Resource doesn't exist |
| **409** | Conflict | Duplicate resource |
| **422** | Unprocessable Entity | Validation error (FastAPI default) |
| **429** | Too Many Requests | Rate limit exceeded |
| **500** | Internal Server Error | Server-side error |
| **503** | Service Unavailable | System overloaded/maintenance |

### 8.2 Error Response Format

```python
class APIError(Exception):
    """Custom API error."""
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

@app.exception_handler(APIError)
async def api_error_handler(request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

# Usage
raise APIError(
    code="TICKER_NOT_FOUND",
    message=f"Ticker not found: {ticker}",
    status_code=404,
)
```

### 8.3 Error Codes

```python
ERROR_CODES = {
    # Data errors
    "TICKER_NOT_FOUND": "Ticker does not exist in database",
    "DATA_NOT_AVAILABLE": "No data available for the requested range",
    "DATA_QUALITY_LOW": "Data quality score below threshold",
    
    # Trading errors
    "INSUFFICIENT_CAPITAL": "Not enough capital for this order",
    "POSITION_NOT_FOUND": "No open position for this ticker",
    "ORDER_ALREADY_EXISTS": "Duplicate order",
    "MARKET_CLOSED": "Market is currently closed",
    "AUTO_TRADE_DISABLED": "Auto trading is not enabled",
    "DAILY_LOSS_LIMIT_REACHED": "Daily loss limit has been reached, trading halted",
    
    # Validation errors
    "INVALID_TICKER": "Ticker format is invalid",
    "INVALID_QUANTITY": "Quantity must be positive and in multiples of 100",
    "INVALID_PRICE": "Price must be positive",
    
    # System errors
    "ENGINE_ERROR": "Analysis engine encountered an error",
    "DATABASE_ERROR": "Database operation failed",
    "EXTERNAL_API_ERROR": "External API call failed",
}
```

---

## 9. API Versioning & Documentation

### 9.1 Versioning Strategy

```python
# URL-based versioning (recommended for simplicity)
@app.get("/api/v1/data/ohlcv")
async def get_ohlcv_v1(ticker: str):
    ...

@app.get("/api/v2/data/ohlcv")
async def get_ohlcv_v2(ticker: str, include_adjusted: bool = True):
    ...
```

### 9.2 OpenAPI/Swagger

```python
from fastapi import FastAPI

app = FastAPI(
    title="Trading System API",
    description="API for Indonesian stock market trading system",
    version="0.1.11",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Tag grouping
@app.get("/api/data/ohlcv", tags=["Data"])
async def get_ohlcv(ticker: str):
    """Get OHLCV data for a specific ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., BBCA.JK)
    
    Returns:
        OHLCV data with optional pagination
    """
    ...
```

### 9.3 API Documentation Best Practices

| Practice | Description |
|----------|-------------|
| **Descriptive summaries** | Each endpoint has a clear summary |
| **Parameter descriptions** | All parameters documented |
| **Response examples** | Example responses for success and error |
| **Error codes** | All possible error codes listed |
| **Authentication** | How to authenticate clearly explained |
| **Rate limits** | Document rate limits |
| **Changelog** | Version history with breaking changes |

---

## 10. Integration Patterns

### 10.1 Pattern Catalog

| Pattern | Use Case | Implementation |
|---------|----------|----------------|
| **Adapter** | Broker API integration | `BrokerAdapter` ABC |
| **Factory** | Execution engine selection | `get_execution_engine()` |
| **Observer/Pub-Sub** | Event-driven updates | `EventBus` |
| **Repository** | Data access abstraction | `DataStorage` |
| **Strategy** | Multiple scoring strategies | Engine registry |
| **Facade** | Simplified API for complex subsystem | `DecisionEngine.recommend()` |
| **Circuit Breaker** | External API failure protection | Rate limiter + health check |
| **Retry** | Transient failure handling | Exponential backoff |

### 10.2 Circuit Breaker Pattern

```python
class CircuitBreaker:
    """Circuit breaker for external API calls."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self.failure_count = 0
            self.state = "CLOSED"
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
            
            raise
```

### 10.3 Retry with Exponential Backoff

```python
async def retry_with_backoff(func, max_retries=3, base_delay=1, max_delay=60):
    """Retry async function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {e}")
            await asyncio.sleep(delay)
```

---

## 11. Rate Limiting & Throttling

### 11.1 API Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/data/ohlcv")
@limiter.limit("100/minute")
async def get_ohlcv(request: Request, ticker: str):
    ...
```

### 11.2 Rate Limit Tiers

| Tier | Limit | Scope | Use Case |
|------|-------|-------|----------|
| **Public** | 10 req/min | IP | Unauthenticated |
| **Authenticated** | 100 req/min | API Key | Normal usage |
| **Premium** | 1000 req/min | API Key | Heavy usage |
| **Internal** | No limit | localhost | Service-to-service |

### 11.3 Rate Limit Response

```python
# HTTP 429 response
{
    "status": "error",
    "error": {
        "code": "RATE_LIMIT_EXCEEDED",
        "message": "Rate limit exceeded: 100 requests per minute",
        "details": {
            "limit": 100,
            "window": "60s",
            "retry_after": 30,
        }
    }
}
```

### 11.4 Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1691542200
```

---

## 12. Checklist Implementasi

### REST API
- [ ] Resource-oriented URL design
- [ ] Standard response format (status, data, meta, error)
- [ ] Pagination on list endpoints
- [ ] Filtering and sorting support
- [ ] Proper HTTP status codes
- [ ] Input validation (Pydantic models)
- [ ] Error handling with custom error codes
- [ ] API key authentication
- [ ] CORS configuration
- [ ] Gzip compression

### WebSocket
- [ ] Channel-based subscription
- [ ] Connection manager (connect/disconnect/broadcast)
- [ ] Heartbeat mechanism
- [ ] Reconnection logic (client-side)
- [ ] Message format (JSON with channel, type, data, timestamp)
- [ ] Authentication for WebSocket connections

### Broker Integration
- [ ] BrokerAdapter abstract base class
- [ ] MockBrokerAdapter for testing
- [ ] Real broker adapter (at least one)
- [ ] Order placement (BUY/SELL)
- [ ] Order cancellation
- [ ] Order status query
- [ ] Position query
- [ ] Account/balance query
- [ ] Error handling for broker API failures
- [ ] Circuit breaker for broker API

### Event-Driven
- [ ] Event bus (in-process pub/sub)
- [ ] Event topics defined for all key events
- [ ] Event structure (topic, payload, timestamp, source)
- [ ] Audit trail for all events
- [ ] Event consumers for key topics

### Security
- [ ] API key authentication on all endpoints
- [ ] Rate limiting (per API key)
- [ ] CORS restricted to known origins
- [ ] HTTPS/TLS in production
- [ ] No secrets in code or git
- [ ] Input sanitization
- [ ] SQL injection prevention (parameterized queries)

### Documentation
- [ ] OpenAPI/Swagger auto-generated
- [ ] Endpoint descriptions and examples
- [ ] Error code documentation
- [ ] Authentication guide
- [ ] Rate limit documentation
- [ ] WebSocket protocol documentation
- [ ] API changelog

### Integration Patterns
- [ ] Adapter pattern (broker, data sources)
- [ ] Factory pattern (execution engine)
- [ ] Circuit breaker (external APIs)
- [ ] Retry with exponential backoff
- [ ] Repository pattern (data access)
- [ ] Observer/Pub-Sub (event bus)

---

## Referensi

1. `src/trading_system/api/app.py` — FastAPI application with 88 endpoints (86 REST + 2 WebSocket)
2. `src/trading_system/execution/broker_adapter.py` — Broker adapter ABC
3. `src/trading_system/execution/interface.py` — TradingInterface ABC
4. `src/trading_system/execution/__init__.py` — Factory pattern
5. `src/trading_system/data/rate_limiter.py` — Rate limiting
6. `pustaka/18-modul-engine-data-wajib.md` — Module registry
7. `pustaka/19-flow-logic-testing-kpi.md` — API rules & security
8. `pustaka/20-syarat-robot-auto-trading.md` — Broker integration requirements
9. FastAPI Documentation: https://fastapi.tiangolo.com
10. FIX Protocol: https://www.fixtrading.org
11. REST API Design: https://restfulapi.net
12. `docs/API_REFERENCE.md` — API reference

---

> **Catatan:** API adalah wajah sistem. Desain API yang baik membuat integrasi mudah, debugging cepat, dan scaling teratur. Investasi waktu di API design selalu dibayar kembali.
