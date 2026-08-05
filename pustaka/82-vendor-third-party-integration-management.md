# Vendor & Third-Party Integration Management

> **Dokumen 82** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Manajemen vendor pihak ketiga — data vendor (Yahoo Finance, IDX scraper, Bloomberg), broker API (Sinarmas, BNI Sekuritas), infrastructure vendor (database, cloud, CDN), vendor SLA, fallback strategy, vendor evaluation, dan contract management.
>
> **Konteks:** Vendor disebut 5x di docs 38, 41. Sistem trading dependen pada banyak vendor eksternal. Tidak ada dokumen yang bahas manajemen vendor secara komprehensif.

---

## Daftar Isi

1. [Vendor Landscape](#1-vendor-landscape)
2. [Data Vendor Management](#2-data-vendor-management)
3. [Broker API Management](#3-broker-api-management)
4. [Infrastructure Vendor Management](#4-infrastructure-vendor-management)
5. [SLA & Monitoring](#5-sla--monitoring)
6. [Fallback & Resilience](#6-fallback--resilience)
7. [Vendor Evaluation](#7-vendor-evaluation)
8. [Implementasi Kode](#8-implementasi-kode)
9. [Hubungan dengan Dokumen Lain](#9-hubungan-dengan-dokumen-lain)

---

## 1. Vendor Landscape

### 1.1 Vendor Categories

| Category | Vendor | Role | Criticality |
|----------|--------|------|-------------|
| **Market Data** | Yahoo Finance | OHLCV, splits, dividends | High |
| **Market Data** | IDX scraper | Foreign flow, broker flow | High |
| **Market Data** | Bloomberg/Refinitiv | Real-time feed (future) | Medium |
| **Broker API** | Sinarmas Sekuritas | Order execution | Critical |
| **Broker API** | BNI Sekuritas | Order execution | Critical |
| **Broker API** | Mock broker | Paper trading | Low |
| **News Data** | RSS/News API | News sentiment | Medium |
| **Social Data** | Reddit API | Social sentiment | Low |
| **Social Data** | Google Trends | Trend data | Low |
| **Infrastructure** | SQLite/PostgreSQL | Database | Critical |
| **Infrastructure** | Cloud provider | Hosting (future) | High |
| **Infrastructure** | CDN | Static assets | Medium |
| **Notification** | Telegram Bot API | Alert delivery | Medium |
| **Notification** | Email service | Report delivery | Medium |
| **Notification** | Push service (FCM) | Mobile push | Medium |

### 1.2 Current Codebase Vendors

| Vendor | File | Status | Fallback |
|--------|------|--------|----------|
| Yahoo Finance | `data/acquisition.py` | ✅ Active | Parquet archive |
| IDX scraper | `data/idx_scraper.py` | ✅ Active | None |
| Mock broker | `execution/broker_adapter.py` | ✅ Active | N/A (paper) |
| Sinarmas | `execution/broker_adapter.py:288` | ❌ Stub | Mock broker |
| BNI Sekuritas | `execution/broker_adapter.py:340` | ❌ Stub | Mock broker |
| Telegram | `utils/telegram_notifier.py` | ✅ Active | None |

---

## 2. Data Vendor Management

### 2.1 Yahoo Finance

```python
# Current: data/acquisition.py
class YahooFinanceAdapter:
    """Yahoo Finance data adapter."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance"

    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter

    def fetch_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Fetch OHLCV data."""
        self.rate_limiter.wait()  # Rate limiting
        # ... fetch logic
```

### 2.2 Vendor Configuration

```python
VENDOR_CONFIG = {
    "yahoo_finance": {
        "name": "Yahoo Finance",
        "type": "market_data",
        "base_url": "https://query1.finance.yahoo.com",
        "rate_limit": "2000/hour",
        "api_key_required": False,
        "data_types": ["ohlcv", "splits", "dividends", "info"],
        "reliability": 0.95,  # Historical uptime
        "fallback": "parquet_archive",
        "cost": "free",
        "sla": "best_effort",
    },
    "idx_scraper": {
        "name": "IDX Web Scraper",
        "type": "market_data",
        "base_url": "https://www.idx.co.id",
        "rate_limit": "60/hour",
        "api_key_required": False,
        "data_types": ["foreign_flow", "broker_flow", "ipo", "delisting"],
        "reliability": 0.90,
        "fallback": "parquet_archive",
        "cost": "free",
        "sla": "best_effort",
    },
    "sinarmas_broker": {
        "name": "Sinarmas Sekuritas",
        "type": "broker_api",
        "base_url": "https://api.sinarmassekuritas.co.id",
        "rate_limit": "100/minute",
        "api_key_required": True,
        "data_types": ["order", "position", "cash_balance", "account"],
        "reliability": 0.99,
        "fallback": "mock_broker",
        "cost": "per_transaction",
        "sla": "99.5% uptime",
    },
    "telegram": {
        "name": "Telegram Bot API",
        "type": "notification",
        "base_url": "https://api.telegram.org",
        "rate_limit": "30/second",
        "api_key_required": True,
        "data_types": ["message"],
        "reliability": 0.995,
        "fallback": "email",
        "cost": "free",
        "sla": "best_effort",
    },
}
```

### 2.3 Vendor Health Check

```python
class VendorHealthChecker:
    """Monitor vendor API health."""

    def __init__(self, config: dict):
        self.config = config
        self.health_status = {}

    async def check_vendor(self, vendor_id: str) -> dict:
        """Check if vendor API is reachable and responsive."""
        vendor = self.config[vendor_id]
        start = time.time()

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(vendor["base_url"])
                latency = (time.time() - start) * 1000

                healthy = response.status_code < 500
                self.health_status[vendor_id] = {
                    "healthy": healthy,
                    "status_code": response.status_code,
                    "latency_ms": latency,
                    "checked_at": datetime.now(),
                }

                return self.health_status[vendor_id]

        except Exception as e:
            self.health_status[vendor_id] = {
                "healthy": False,
                "error": str(e),
                "checked_at": datetime.now(),
            }
            return self.health_status[vendor_id]

    async def check_all_vendors(self) -> dict:
        """Check all configured vendors."""
        results = {}
        for vendor_id in self.config:
            results[vendor_id] = await self.check_vendor(vendor_id)
        return results
```

---

## 3. Broker API Management

### 3.1 Broker Adapter Architecture

```python
# Current: execution/broker_adapter.py
class BrokerAdapter(ABC):
    """Abstract broker adapter."""

    @abstractmethod
    def authenticate(self) -> bool: ...

    @abstractmethod
    def get_account(self) -> BrokerAccount: ...

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult: ...

    @abstractmethod
    def get_position(self, ticker: str) -> BrokerPosition: ...

    @abstractmethod
    def get_cash_balance(self) -> float: ...

# Implementations:
# - MockBrokerAdapter (✅ active, paper trading)
# - SinarmasBrokerAdapter (❌ stub)
# - BNISekuritasBrokerAdapter (❌ stub)
```

### 3.2 Broker Selection & Failover

```python
class BrokerManager:
    """Manage multiple broker adapters with failover."""

    def __init__(self, adapters: dict[str, BrokerAdapter]):
        self.adapters = adapters
        self.primary = None
        self.fallback = None

    def set_primary(self, broker_id: str):
        """Set primary broker."""
        self.primary = self.adapters[broker_id]

    def set_fallback(self, broker_id: str):
        """Set fallback broker."""
        self.fallback = self.adapters[broker_id]

    def execute_order(self, order: dict) -> dict:
        """Execute order with failover."""
        try:
            result = self.primary.place_order(order)
            if result["status"] == "ok":
                return {"broker": "primary", "result": result}
        except Exception as e:
            logger.error(f"Primary broker failed: {e}")

        if self.fallback:
            try:
                result = self.fallback.place_order(order)
                return {"broker": "fallback", "result": result}
            except Exception as e:
                logger.error(f"Fallback broker failed: {e}")

        return {"broker": "none", "result": {"status": "error", "message": "All brokers failed"}}
```

---

## 4. Infrastructure Vendor Management

### 4.1 Infrastructure Dependencies

| Component | Current | Future | SLA |
|-----------|---------|--------|-----|
| **Database** | SQLite (local) | PostgreSQL (cloud) | 99.9% |
| **Object storage** | Local filesystem | S3-compatible | 99.99% |
| **Compute** | Local server | Cloud VM | 99.5% |
| **CDN** | None | Cloudflare | 99.99% |
| **DNS** | Local | Cloud DNS | 99.99% |
| **Monitoring** | Local scripts | Cloud monitoring | 99.9% |

### 4.2 Data Storage Vendor Strategy

```python
class StorageManager:
    """Manage data storage with vendor abstraction."""

    def __init__(self, primary: DataStorage, archive: DataStorage | None = None):
        self.primary = primary
        self.archive = archive

    def save_ohlcv(self, data: pd.DataFrame, ticker: str):
        """Save to primary, backup to archive."""
        self.primary.save_ohlcv(data, ticker)
        if self.archive:
            self.archive.save_ohlcv(data, ticker)

    def load_ohlcv(self, ticker: str) -> pd.DataFrame:
        """Load from primary, fallback to archive."""
        data = self.primary.load_ohlcv(ticker)
        if data.empty and self.archive:
            data = self.archive.load_ohlcv(ticker)
        return data
```

---

## 5. SLA & Monitoring

### 5.1 SLA Definitions

| Vendor | Metric | Target | Alert Threshold |
|--------|--------|--------|-----------------|
| Yahoo Finance | Uptime | 95% | < 90% → switch to archive |
| Yahoo Finance | Latency | < 2 sec | > 5 sec → throttle |
| IDX scraper | Uptime | 90% | < 80% → alert |
| Broker API | Uptime | 99.5% | < 99% → critical alert |
| Broker API | Order latency | < 500 ms | > 2 sec → alert |
| Telegram | Delivery rate | 99% | < 95% → fallback email |
| Database | Query latency | < 100 ms | > 500 ms → investigate |

### 5.2 Vendor Metrics Dashboard

```python
@app.get("/api/vendor/status")
async def get_vendor_status():
    """Get status of all vendors."""
    checker = VendorHealthChecker(VENDOR_CONFIG)
    status = await checker.check_all_vendors()

    return {
        "vendors": status,
        "summary": {
            "total": len(status),
            "healthy": sum(1 for s in status.values() if s.get("healthy")),
            "unhealthy": sum(1 for s in status.values() if not s.get("healthy")),
        },
    }
```

---

## 6. Fallback & Resilience

### 6.1 Fallback Strategy per Vendor

| Vendor | Primary Fallback | Secondary Fallback |
|--------|-----------------|-------------------|
| Yahoo Finance | Parquet archive | Manual data entry |
| IDX scraper | Parquet archive | Skip (stale data OK) |
| Broker API | Mock broker (paper) | Queue order for retry |
| Telegram | Email notification | In-app notification |
| Database | Read-only mode | Maintenance page |

### 6.2 Circuit Breaker per Vendor

```python
class VendorCircuitBreaker:
    """Circuit breaker for vendor API calls."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = {}
        self.last_failure_time = {}
        self.state = {}  # "closed", "open", "half_open"

    def can_call(self, vendor_id: str) -> bool:
        """Check if we can call this vendor."""
        state = self.state.get(vendor_id, "closed")

        if state == "closed":
            return True
        elif state == "open":
            # Check if recovery timeout has passed
            last_failure = self.last_failure_time.get(vendor_id)
            if last_failure and (datetime.now() - last_failure).seconds > self.recovery_timeout:
                self.state[vendor_id] = "half_open"
                return True
            return False
        elif state == "half_open":
            return True

    def record_success(self, vendor_id: str):
        """Record successful call."""
        self.failure_count[vendor_id] = 0
        self.state[vendor_id] = "closed"

    def record_failure(self, vendor_id: str):
        """Record failed call."""
        self.failure_count[vendor_id] = self.failure_count.get(vendor_id, 0) + 1
        self.last_failure_time[vendor_id] = datetime.now()

        if self.failure_count[vendor_id] >= self.failure_threshold:
            self.state[vendor_id] = "open"
            logger.warning(f"Vendor {vendor_id} circuit breaker OPEN")
```

---

## 7. Vendor Evaluation

### 7.1 Evaluation Criteria

| Criteria | Weight | Score (1-5) |
|----------|--------|-------------|
| **Reliability** | 30% | Uptime history, error rate |
| **Data quality** | 25% | Accuracy, completeness, timeliness |
| **Cost** | 15% | Per-call cost, monthly fee |
| **Support** | 10% | Response time, documentation |
| **API quality** | 10% | RESTful, versioning, rate limits |
| **Compliance** | 10% | OJK compliance, data privacy |

### 7.2 Evaluation Process

```python
class VendorEvaluator:
    """Evaluate and compare vendors."""

    CRITERIA = {
        "reliability": 0.30,
        "data_quality": 0.25,
        "cost": 0.15,
        "support": 0.10,
        "api_quality": 0.10,
        "compliance": 0.10,
    }

    def evaluate(self, vendor_id: str, scores: dict[str, int]) -> dict:
        """Evaluate a vendor based on criteria scores (1-5)."""
        total = sum(scores.get(c, 3) * w for c, w in self.CRITERIA.items())
        max_score = 5.0

        return {
            "vendor_id": vendor_id,
            "scores": scores,
            "weighted_score": total,
            "normalized_score": (total / max_score) * 100,
            "recommendation": self._get_recommendation(total),
        }

    def _get_recommendation(self, score: float) -> str:
        if score >= 4.0:
            return "Recommended"
        elif score >= 3.0:
            return "Acceptable with monitoring"
        elif score >= 2.0:
            return "Use only if no alternative"
        else:
            return "Not recommended"
```

---

## 8. Implementasi Kode

### 8.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| `VendorHealthChecker` | `integration/health.py` | ❌ New | Vendor health monitoring |
| `VendorCircuitBreaker` | `integration/circuit_breaker.py` | ❌ New | Per-vendor circuit breaker |
| `BrokerManager` | `execution/broker_manager.py` | ❌ New | Multi-broker with failover |
| `VendorEvaluator` | `integration/evaluator.py` | ❌ New | Vendor evaluation framework |
| `VendorConfig` | `integration/config.py` | ❌ New | Centralized vendor config |
| API endpoint | `api/app.py` | ❌ New | `/api/vendor/status` |

### 8.2 Database Schema

```sql
CREATE TABLE IF NOT EXISTS vendor_config (
    vendor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    base_url TEXT,
    api_key_env TEXT,           -- Env var name for API key
    rate_limit TEXT,
    reliability REAL DEFAULT 0.95,
    fallback_vendor TEXT,
    sla TEXT,
    cost TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vendor_health_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id TEXT NOT NULL,
    healthy INTEGER NOT NULL,
    latency_ms REAL,
    status_code INTEGER,
    error TEXT,
    checked_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vendor_evaluation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id TEXT NOT NULL,
    evaluated_at TEXT DEFAULT (datetime('now')),
    scores TEXT,                -- JSON
    weighted_score REAL,
    recommendation TEXT,
    notes TEXT
);
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **22** (Data Engineering) | Data vendor pipeline |
| **27** (Deployment DevOps) | Infrastructure vendor |
| **28** (API Design) | Vendor API integration patterns |
| **33** (Cybersecurity) | Vendor security, API key management |
| **38** (Manajemen Aplikasi Ritel) | Vendor management module |
| **41** (UU PDP) | Vendor data sharing compliance |
| **47** (Operational Contract) | Vendor health check task |
| **48** (Disaster Recovery) | Vendor failover in DR plan |
| **49** (Incident Management) | Vendor outage incident |
| **53** (Data Governance) | Vendor data lineage |
| **55** (Capacity Planning) | Vendor rate limit capacity |

---

## 10. Checklist Implementasi

### Vendor Config
- [ ] Centralized vendor config (DB table)
- [ ] API key management (env vars, never hardcoded)
- [ ] Vendor activation/deactivation
- [ ] Unit tests

### Health Monitoring
- [ ] `VendorHealthChecker` class
- [ ] Periodic health check (every 5 min)
- [ ] Health log table
- [ ] `/api/vendor/status` endpoint
- [ ] Alert on vendor down
- [ ] Unit tests

### Circuit Breaker
- [ ] Per-vendor circuit breaker
- [ ] Failure threshold (5 failures → open)
- [ ] Recovery timeout (5 min → half-open)
- [ ] Auto-reset on success
- [ ] Unit tests

### Broker Failover
- [ ] `BrokerManager` with primary/fallback
- [ ] Automatic failover on primary failure
- [ ] Order queue for retry
- [ ] Paper trading as ultimate fallback
- [ ] Unit tests

### Vendor Evaluation
- [ ] Evaluation criteria (6 criteria)
- [ ] Scoring framework
- [ ] Evaluation log
- [ ] Periodic re-evaluation (quarterly)
- [ ] Unit tests

### API
- [ ] `/api/vendor/status` — health status
- [ ] `/api/vendor/config` — vendor config
- [ ] `/api/vendor/evaluation` — evaluation results
- [ ] Integration tests

---

## Referensi

1. `src/trading_system/data/acquisition.py` — Yahoo Finance data source
2. `src/trading_system/execution/broker_adapter.py` — Broker API adapter (Mock + Sinarmas/BNI)
3. `src/trading_system/utils/notifier.py` — Telegram notification
4. `src/trading_system/data/rate_limiter.py` — Rate limiting for API vendors
5. `pustaka/27-deployment-devops-trading.md` — Infrastructure vendor management
6. `pustaka/33-cybersecurity-trading-system.md` — API key management
7. `pustaka/56-notification-strategy-alert-fatigue.md` — Vendor health alerts
8. `pustaka/48-disaster-recovery-business-continuity.md` — Vendor failover

---

> **Catatan:** Sistem trading adalah sistem yang dependen pada banyak vendor eksternal. Yahoo Finance bisa down, broker API bisa maintenance, IDX website bisa berubah struktur. Tanpa vendor management yang baik (health check, circuit breaker, fallback), satu vendor yang down bisa menghentikan seluruh sistem. Vendor management bukan opsional — adalah insurance policy.
