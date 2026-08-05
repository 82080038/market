# Deployment, DevOps & Infrastructure Trading System

> **Tujuan:** Dokumen ini adalah referensi definitif untuk deployment, DevOps, dan infrastruktur sistem trading — dari Docker containerization, CI/CD pipeline, monitoring & alerting, blue-green deployment, health checks, hingga disaster recovery — dengan fokus pada aplikasi trading pasar modal Indonesia.

---

## Daftar Isi

1. [Deployment Architecture](#1-deployment-architecture)
2. [Docker Containerization](#2-docker-containerization)
3. [CI/CD Pipeline](#3-cicd-pipeline)
4. [Environment Management](#4-environment-management)
5. [Monitoring & Observability](#5-monitoring--observability)
6. [Health Checks & Alerting](#6-health-checks--alerting)
7. [Deployment Strategies](#7-deployment-strategies)
8. [Database Operations](#8-database-operations)
9. [Disaster Recovery](#9-disaster-recovery)
10. [Security Hardening](#10-security-hardening)
11. [Performance Optimization](#11-performance-optimization)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Deployment Architecture

### 1.1 Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION ENVIRONMENT                    │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ API      │  │ Scheduler│  │ Frontend │  │ Monitor  │   │
│  │ (FastAPI)│  │ (APScheduler│  │ (Next.js)│  │ (Health) │   │
│  │ Port 8000│  │ Background│  │ Port 3000│  │          │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │         │
│       └──────────────┴──────┬───────┴──────────────┘         │
│                              │                               │
│                    ┌─────────▼─────────┐                     │
│                    │   SQLite (WAL)    │                     │
│                    │   data/trading.db │                     │
│                    └─────────┬─────────┘                     │
│                              │                               │
│                    ┌─────────▼─────────┐                     │
│                    │  Parquet Archive  │                     │
│                    │  /media/Parquet/  │                     │
│                    └───────────────────┘                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              EXTERNAL INTEGRATIONS                    │   │
│  │  Yahoo Finance │ IDX.co.id │ RSS │ Telegram │ SMTP  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Component Matrix

| Component | Technology | Port | Scale | State |
|-----------|-----------|------|-------|-------|
| **API Server** | FastAPI + Uvicorn | 8000 | 1-2 instances | Stateless |
| **Frontend** | Next.js | 3000 | 1 instance | Stateless |
| **Scheduler** | APScheduler (background) | - | 1 instance | Stateful (timing) |
| **Database** | SQLite (WAL mode) | - | 1 instance | Stateful |
| **Cold Storage** | Parquet files | - | 1 volume | Stateful |
| **Cache** | Redis (optional) | 6379 | 1 instance | Stateful (ephemeral) |
| **Monitor** | Built-in health check | - | 1 instance | Stateless |

### 1.3 Deployment Environments

| Environment | Purpose | Data | API Key | Auto-Trade |
|-------------|---------|------|---------|------------|
| **Development** | Local development | Test DB | dev-key | false |
| **Staging** | Pre-production testing | Copy of prod | staging-key | false |
| **Production** | Live trading | Real DB | prod-key | configurable |

---

## 2. Docker Containerization

### 2.1 Dockerfile

```dockerfile
# Backend
FROM python:3.12-slim AS backend

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

# Application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY .env.example ./

# Non-root user
RUN useradd -m -s /bin/bash trader
USER trader

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "trading_system.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# Frontend
FROM node:20-slim AS frontend

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci --production

COPY frontend/ ./
RUN npm run build

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

CMD ["npm", "start"]
```

### 2.2 Docker Compose

```yaml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_PATH=/data/trading_system.db
      - API_KEY=${API_KEY:-dev-secret-key-2026}
      - AUTO_TRADE_ENABLED=false
      - TRADING_CAPITAL=100000000
      - RISK_PER_TRADE=0.01
      - DATA_RAW_DIR=/data/parquet/raw
      - DATA_ARCHIVE_DIR=/data/parquet/archive
    volumes:
      - trading-data:/data
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    depends_on:
      - redis

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_BASE=http://api:8000
    restart: unless-stopped
    depends_on:
      - api

  scheduler:
    build:
      context: .
      dockerfile: Dockerfile
    command: ["python", "-m", "trading_system.cli", "schedule"]
    environment:
      - DATABASE_PATH=/data/trading_system.db
      - AUTO_TRADE_ENABLED=false
    volumes:
      - trading-data:/data
    restart: unless-stopped
    depends_on:
      - api

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  trading-data:
  redis-data:
```

### 2.3 Multi-Stage Build (Optimized)

```dockerfile
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

RUN useradd -m trader && chown -R trader:trader /app
USER trader

EXPOSE 8000
CMD ["uvicorn", "trading_system.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 3. CI/CD Pipeline

### 3.1 GitHub Actions

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install mypy
      - run: mypy src/trading_system/

  test:
    runs-on: ubuntu-latest
    needs: [lint, type-check]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ --cov=src/trading_system --cov-fail-under=50 -v
      - run: pytest tests/unit/ -k "not slow" --maxfail=5

  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - working-directory: frontend
        run: |
          npm ci
          npm run lint
          npm run build

  docker-build:
    runs-on: ubuntu-latest
    needs: [test, frontend-build]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          tags: trading-system:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    runs-on: ubuntu-latest
    needs: [docker-build]
    if: github.ref == 'refs/heads/main'
    environment: staging
    steps:
      - name: Deploy to staging
        run: |
          echo "Deploy to staging server"
          # ssh and docker-compose pull + restart
```

### 3.2 Pipeline Stages

```
Push → Lint → Type Check → Unit Test → Frontend Build → Docker Build → Deploy Staging → Manual Approval → Deploy Production
```

### 3.3 Branch Strategy

| Branch | Purpose | Auto-Deploy |
|--------|---------|-------------|
| `main` | Production-ready code | → Staging → Production |
| `develop` | Integration branch | → Staging only |
| `feature/*` | Feature development | No deploy |
| `hotfix/*` | Urgent production fix | → Staging → Production (fast-track) |

---

## 4. Environment Management

### 4.1 Environment Variables

```bash
# .env.example — Template for all environments

# Core
APP_ENV=development          # development, staging, production
APP_VERSION=0.1.11
LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR

# Database
DATABASE_PATH=data/trading_system.db
DATABASE_BACKUP_PATH=data/backups/

# API
API_HOST=0.0.0.0
API_PORT=8000
API_KEY=dev-secret-key-2026
CORS_ORIGINS=http://localhost:3000

# Trading
TRADING_CAPITAL=100000000    # Rp 100M
RISK_PER_TRADE=0.01          # 1%
EXIT_CONVICTION_THRESHOLD=40
DAILY_LOSS_LIMIT=1000000     # Rp 1M
AUTO_TRADE_ENABLED=false     # CRITICAL: false by default
TRADING_MODE=paper           # paper, real

# Data
DATA_RAW_DIR=/media/petrick/Parquet/trading_data/raw
DATA_ARCHIVE_DIR=/media/petrick/Parquet/trading_data/archive

# External APIs
YAHOO_FINANCE_RATE_LIMIT=1.0
IDX_SCRAPER_RATE_LIMIT=3.0
FRED_API_KEY=

# Notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

# Scheduler
SCHEDULE_ENABLED=true
SCHEDULE_TIMEZONE=Asia/Jakarta

# Redis (optional)
REDIS_URL=redis://localhost:6379
```

### 4.2 Secret Management

| Secret Type | Dev | Staging | Production |
|-------------|-----|---------|------------|
| **API Key** | `.env` file | `.env` file (gitignored) | Vault/AWS Secrets Manager |
| **DB Path** | Local path | Docker volume | Encrypted EBS volume |
| **Broker API** | Mock | Mock | Vault + env injection |
| **Telegram Token** | Empty | `.env` file | Vault |

### 4.3 Configuration Hierarchy

```
1. Environment variables (highest priority)
2. .env file
3. config.py defaults (lowest priority)
```

---

## 5. Monitoring & Observability

### 5.1 Three Pillars of Observability

| Pillar | Tool | What | Frequency |
|--------|------|------|-----------|
| **Metrics** | Built-in / Prometheus | CPU, memory, latency, error rate | 10s |
| **Logs** | Python logging / ELK | Application events, errors | Real-time |
| **Traces** | OpenTelemetry (optional) | Request flow across services | Per request |

### 5.2 Key Metrics

```python
SYSTEM_METRICS = {
    # Infrastructure
    "cpu_usage_pct": "CPU utilization percentage",
    "memory_usage_mb": "Memory usage in MB",
    "disk_usage_pct": "Disk usage percentage",
    "db_size_mb": "Database file size in MB",
    
    # API
    "api_requests_per_min": "API request rate",
    "api_avg_response_ms": "Average API response time",
    "api_error_rate_pct": "API error percentage",
    "api_p99_response_ms": "99th percentile response time",
    
    # Trading
    "signals_per_day": "Trading signals generated",
    "orders_per_day": "Orders executed",
    "open_positions": "Current open positions count",
    "daily_pnl": "Daily realized + unrealized PnL",
    "win_rate_pct": "Win rate percentage",
    
    # Data
    "data_freshness_hours": "Hours since last data update",
    "ohlcv_rows": "Total OHLCV rows in database",
    "ingest_rate_rows_per_min": "Data ingestion rate",
    
    # Engines
    "engine_last_run": "Last run timestamp per engine",
    "engine_status": "Engine health status (ok/warning/error)",
    "score_computation_time_ms": "Score computation latency",
}
```

### 5.3 Logging Configuration

```python
import logging
import sys

def setup_logging(env: str = "development", level: str = "INFO"):
    """Configure structured logging."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    if env == "production":
        # JSON structured logging for production
        import json_logging
        json_logging.init_non_web(enable_json=True)
        logging.basicConfig(
            level=getattr(logging, level),
            stream=sys.stdout,
            format=log_format,
        )
    else:
        logging.basicConfig(
            level=getattr(logging, level),
            stream=sys.stderr,
            format=log_format,
        )
    
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
```

### 5.4 Log Levels

| Level | When to Use | Example |
|-------|-------------|---------|
| **DEBUG** | Detailed diagnostic info | `f"Processing ticker: {ticker}, step: {step}"` |
| **INFO** | General application flow | `f"BUY {qty} {ticker} @ Rp {price:,.2f}"` |
| **WARNING** | Something unexpected but not fatal | `"AUTO_TRADE_ENABLED=false. Monitoring only."` |
| **ERROR** | Error that should be investigated | `f"Failed to fetch data for {ticker}: {e}"` |
| **CRITICAL** | System-wide failure | `"Daily loss limit exceeded. Trading HALTED."` |

---

## 6. Health Checks & Alerting

### 6.1 Health Check Endpoint

```python
@app.get("/api/health")
async def health_check():
    """Comprehensive health check."""
    checks = {
        "database": await check_database_health(),
        "data_freshness": await check_data_freshness(),
        "engines": await check_engine_health(),
        "scheduler": await check_scheduler_health(),
        "disk_space": check_disk_space(),
    }
    
    all_healthy = all(c["status"] == "ok" for c in checks.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
    }
```

### 6.2 Alert Configuration

```python
ALERT_RULES = {
    # Critical alerts (immediate notification)
    "daily_loss_limit_exceeded": {
        "condition": "daily_pnl < -DAILY_LOSS_LIMIT",
        "severity": "CRITICAL",
        "notify": ["telegram", "email", "audit_log"],
        "action": "halt_trading",
    },
    "database_error": {
        "condition": "db_connection_failed",
        "severity": "CRITICAL",
        "notify": ["telegram", "email"],
        "action": "restart_service",
    },
    "auto_trade_unexpected": {
        "condition": "AUTO_TRADE_ENABLED == true and not confirmed",
        "severity": "CRITICAL",
        "notify": ["telegram", "email"],
        "action": "disable_auto_trade",
    },
    
    # Warning alerts
    "data_stale": {
        "condition": "data_freshness_hours > 24",
        "severity": "WARNING",
        "notify": ["telegram"],
    },
    "engine_failure": {
        "condition": "engine_status == 'error'",
        "severity": "WARNING",
        "notify": ["telegram", "audit_log"],
    },
    "high_error_rate": {
        "condition": "api_error_rate > 5%",
        "severity": "WARNING",
        "notify": ["telegram"],
    },
    "disk_low": {
        "condition": "disk_usage > 80%",
        "severity": "WARNING",
        "notify": ["telegram"],
    },
    
    # Info alerts
    "trade_executed": {
        "condition": "order_filled",
        "severity": "INFO",
        "notify": ["telegram"],
    },
    "stop_loss_triggered": {
        "condition": "sl_hit",
        "severity": "INFO",
        "notify": ["telegram", "audit_log"],
    },
}
```

### 6.3 Telegram Alerting

```python
class TelegramNotifier:
    """Send alerts via Telegram bot."""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send_alert(self, severity: str, title: str, message: str):
        """Send formatted alert to Telegram."""
        emoji = {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "INFO": "ℹ️",
        }.get(severity, "📌")
        
        text = f"{emoji} *{severity}: {title}*\n\n{message}\n\n_{datetime.now(UTC).isoformat()}_"
        
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
```

---

## 7. Deployment Strategies

### 7.1 Strategy Comparison

| Strategy | Downtime | Risk | Rollback | Complexity | Best For |
|----------|----------|------|----------|------------|----------|
| **Recreate** | Yes | Low | Easy | Low | Dev/staging |
| **Rolling** | Minimal | Medium | Medium | Medium | API servers |
| **Blue-Green** | Zero | Low | Instant | High | Production API |
| **Canary** | Zero | Low | Quick | High | Risky changes |

### 7.2 Blue-Green Deployment

```bash
#!/bin/bash
# Blue-green deployment script

CURRENT=$(docker-compose ps --services --filter "status=running" | grep api | head -1)
if [ "$CURRENT" == "api-blue" ]; then
    NEW="api-green"
    OLD="api-blue"
else
    NEW="api-blue"
    OLD="api-green"
fi

echo "Deploying $NEW..."
docker-compose up -d --no-deps --build $NEW

# Wait for health check
echo "Waiting for $NEW to be healthy..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "$NEW is healthy!"
        break
    fi
    sleep 2
done

# Switch traffic
echo "Switching traffic to $NEW..."
docker-compose stop $OLD

echo "Deployment complete. $OLD stopped."
```

### 7.3 Rolling Update (Docker Swarm)

```bash
docker service update \
    --update-parallelism 1 \
    --update-delay 30s \
    --update-failure-action rollback \
    --image trading-system:latest \
    trading_api
```

---

## 8. Database Operations

### 8.1 Backup Strategy

```bash
#!/bin/bash
# Daily database backup

DB_PATH="/data/trading_system.db"
BACKUP_DIR="/data/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/trading_system_$DATE.db"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# SQLite online backup (safe with WAL mode)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Compress
gzip "$BACKUP_FILE"

# Retention: keep 30 days
find "$BACKUP_DIR" -name "trading_system_*.db.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE.gz"
```

### 8.2 Database Maintenance

```python
def database_maintenance(db_path: str):
    """Run periodic database maintenance."""
    conn = sqlite3.connect(db_path)
    
    # 1. ANALYZE (update statistics)
    conn.execute("ANALYZE")
    
    # 2. Integrity check
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if result[0] != "ok":
        logger.error(f"Database integrity check failed: {result[0]}")
    
    # 3. WAL checkpoint
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    
    # 4. Vacuum (reclaim space, run monthly)
    # conn.execute("VACUUM")  # Requires exclusive lock
    
    conn.close()
    
    # 5. Check database size
    db_size = os.path.getsize(db_path) / (1024 * 1024)
    logger.info(f"Database size: {db_size:.1f} MB")
```

### 8.3 Migration Management

```bash
# Check current migration
alembic current

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Create new migration
alembic revision -m "add_new_table"

# View migration history
alembic history --verbose
```

---

## 9. Disaster Recovery

### 9.1 RTO & RPO

| Metric | Target | Method |
|--------|--------|--------|
| **RTO** (Recovery Time Objective) | < 1 hour | Docker redeploy from image |
| **RPO** (Recovery Point Objective) | < 24 hours | Daily backup |

### 9.2 Recovery Procedure

```bash
#!/bin/bash
# Disaster recovery procedure

# 1. Restore database from backup
LATEST_BACKUP=$(ls -t /backups/trading_system_*.db.gz | head -1)
gunzip -c "$LATEST_BACKUP" > /data/trading_system.db

# 2. Run migrations
alembic upgrade head

# 3. Verify database integrity
sqlite3 /data/trading_system.db "PRAGMA integrity_check;"

# 4. Restore Parquet archive (if needed)
rsync -av /backup/parquet/ /media/Parquet/trading_data/

# 5. Start services
docker-compose up -d

# 6. Verify health
sleep 10
curl http://localhost:8000/api/health

# 7. Verify data freshness
curl http://localhost:8000/api/data-overview
```

### 9.3 Backup Verification

```python
def verify_backup(backup_path: str) -> bool:
    """Verify backup integrity."""
    try:
        conn = sqlite3.connect(backup_path)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        
        if result[0] == "ok":
            # Check critical tables exist and have data
            conn = sqlite3.connect(backup_path)
            for table in ["ohlcv", "instrument_master", "scores", "positions", "orders"]:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count == 0:
                    logger.warning(f"Backup verification: {table} is empty")
            conn.close()
            return True
        return False
    except Exception as e:
        logger.error(f"Backup verification failed: {e}")
        return False
```

---

## 10. Security Hardening

### 10.1 Production Security Checklist

| Area | Measure | Priority |
|------|---------|----------|
| **API Authentication** | API key required on all endpoints | HIGH |
| **API Rate Limiting** | 100 req/min per client | HIGH |
| **CORS** | Restrict to known origins | HIGH |
| **HTTPS** | TLS termination at reverse proxy | HIGH |
| **Database** | File permissions 600 | MEDIUM |
| **Secrets** | No secrets in code/git | HIGH |
| **Docker** | Non-root user | MEDIUM |
| **Dependencies** | Regular security updates | MEDIUM |
| **Firewall** | Only expose 80/443 | HIGH |
| **SSH** | Key-based auth only, no root | HIGH |

### 10.2 Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name trading.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name trading.example.com;
    
    ssl_certificate /etc/ssl/certs/trading.crt;
    ssl_certificate_key /etc/ssl/private/trading.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    # API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Rate limiting
        limit_req zone=api burst=20 nodelay;
    }
    
    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
}
```

---

## 11. Performance Optimization

### 11.1 API Performance

| Optimization | Impact | Effort |
|-------------|--------|--------|
| Connection pooling | -50% DB latency | Low |
| Query optimization (indexes) | -80% query time | Low |
| Response caching (Redis) | -90% repeat queries | Medium |
| Pagination on large responses | -95% payload size | Low |
| Async I/O (FastAPI native) | +10x concurrency | Built-in |
| Gzip compression | -70% bandwidth | Low |

### 11.2 Database Optimization

```python
# SQLite optimization for trading system
PRAGMA journal_mode=WAL;        # Concurrent read/write
PRAGMA synchronous=NORMAL;      # Balance safety/speed
PRAGMA cache_size=-64000;       # 64MB cache
PRAGMA temp_store=MEMORY;       # In-memory temp
PRAGMA mmap_size=268435456;     # 256MB memory-mapped I/O
PRAGMA wal_autocheckpoint=1000; # Auto-checkpoint every 1000 pages
```

### 11.3 Frontend Performance

| Optimization | Impact |
|-------------|--------|
| Next.js SSG/SSR | Faster initial load |
| Image optimization | -60% image size |
| Code splitting | Smaller initial bundle |
| API response caching | Fewer requests |
| WebSocket for real-time | No polling overhead |

---

## 12. Checklist Implementasi

### Docker
- [ ] Dockerfile (multi-stage, non-root user)
- [ ] Docker Compose for full stack
- [ ] Health check in Dockerfile
- [ ] Volume mapping for data persistence
- [ ] Environment variable injection
- [ ] Image tagging (version + latest)

### CI/CD
- [ ] Linting (ruff) in CI
- [ ] Type checking (mypy) in CI
- [ ] Unit tests in CI (pytest, ≥ 50% coverage)
- [ ] Frontend build in CI
- [ ] Docker build in CI
- [ ] Automated deployment to staging
- [ ] Manual approval for production

### Monitoring
- [ ] Health check endpoint (/api/health)
- [ ] System metrics (CPU, memory, disk)
- [ ] Application metrics (requests, errors, latency)
- [ ] Trading metrics (signals, orders, PnL)
- [ ] Data freshness monitoring
- [ ] Engine health monitoring
- [ ] Structured logging
- [ ] Log rotation

### Alerting
- [ ] Telegram bot integration
- [ ] Email notification for critical alerts
- [ ] Alert severity levels (CRITICAL/WARNING/INFO)
- [ ] Alert rules for daily loss limit
- [ ] Alert rules for data staleness
- [ ] Alert rules for engine failures
- [ ] Alert rules for high error rate
- [ ] Audit log for all alerts

### Database
- [ ] Daily backup (automated)
- [ ] Backup verification
- [ ] WAL checkpoint scheduling
- [ ] Integrity check scheduling
- [ ] Migration via Alembic
- [ ] Database size monitoring
- [ ] Retention policy (30 days backup)

### Security
- [ ] API key authentication
- [ ] CORS restriction
- [ ] HTTPS/TLS
- [ ] Non-root Docker user
- [ ] No secrets in code
- [ ] File permissions on database
- [ ] Security headers (Nginx)
- [ ] Rate limiting

### Disaster Recovery
- [ ] RTO < 1 hour
- [ ] RPO < 24 hours
- [ ] Documented recovery procedure
- [ ] Backup restoration tested
- [ ] Parquet archive backup
- [ ] Configuration backup (.env)

### Performance
- [ ] Database indexes on hot paths
- [ ] API pagination
- [ ] Response compression (gzip)
- [ ] Connection pooling
- [ ] Frontend code splitting
- [ ] WebSocket for real-time data

---

## Referensi

1. `Dockerfile` — Backend containerization
2. `docker-compose.yml` — Full stack orchestration
3. `.github/workflows/ci.yml` — CI/CD pipeline
4. `src/trading_system/api/app.py` — API with health check
5. `src/trading_system/monitoring/` — System health monitor
6. `src/trading_system/utils/notifier.py` — Telegram notifier
7. `pustaka/19-flow-logic-testing-kpi.md` — Testing & KPI
8. `pustaka/20-syarat-robot-auto-trading.md` — Auto trading requirements
9. Docker Documentation: https://docs.docker.com
10. GitHub Actions: https://docs.github.com/en/actions
11. FastAPI Deployment: https://fastapi.tiangolo.com/deployment/

---

## 12. Implementasi: Structured Logging Configuration

> **Sumber:** `src/trading_system/utils/logging_config.py` (89 baris)

**What:** Structured logging dengan rotation untuk sistem trading.
**Why:** Sistem trading memerlukan audit trail yang dapat di-trace — setiap keputusan, error, dan warning harus tercatat dengan timestamp dan konteks.
**When:** Dipanggil sekali di startup via `setup_logging()`.
**Where:** Entry point aplikasi (API, CLI, scripts).
**Who:** Semua modul menggunakan logger yang sama.

### 12.1 Konfigurasi

| Komponen | Format | Level | Output |
|----------|--------|-------|--------|
| **Console** | `%(asctime)s [%(levelname)s] %(name)s: %(message)s` | `LOG_LEVEL` (default: INFO) | stdout |
| **File** | `%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d: %(message)s` | DEBUG | `logs/trading_system.log` (rotating, 5MB × 3) |
| **Error file** | Same as file | ERROR+ | `logs/trading_system_error.log` (rotating, 5MB × 3) |

### 12.2 Env Vars

| Env Var | Default | Fungsi |
|---------|---------|--------|
| `LOG_LEVEL` | INFO | Minimum level untuk console output |
| `LOG_DIR` | `logs/` | Directory untuk log files |

### 12.3 5W1H

| Aspect | Detail |
|--------|--------|
| **What** | Structured logging dengan rotation (3 handlers) |
| **Why** | Audit trail untuk trading decisions, debugging, dan compliance |
| **When** | Startup — `setup_logging()` dipanggil sekali |
| **Where** | `utils/logging_config.py`, dipanggil dari API/CLI entry point |
| **Who** | Semua modul via `logging.getLogger(__name__)` |
| **How** | `dictConfig` dengan RotatingFileHandler + StreamHandler |

---

> **Catatan:** Deployment dan DevOps adalah fondasi operasional. Sistem trading yang tidak reliable secara infrastruktur akan kehilangan peluang trading dan kepercayaan investor, terlepas dari seberapa bagus strateginya. Implementasi logging: `src/trading_system/utils/logging_config.py`.
