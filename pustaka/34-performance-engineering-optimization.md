# Performance Engineering & Optimization

> **Tujuan:** Dokumen ini adalah referensi definitif untuk performance engineering sistem trading — dari database optimization, caching strategies, async I/O, query tuning, memory management, hingga frontend performance — dengan implementasi kode untuk sistem trading Indonesia (IDX) dengan ~3M rows OHLCV dan 900+ tickers.

---

## Daftar Isi

1. [Performance Baseline](#1-performance-baseline)
2. [Database Optimization](#2-database-optimization)
3. [Query Tuning](#3-query-tuning)
4. [Caching Strategies](#4-caching-strategies)
5. [Async I/O](#5-async-io)
6. [Memory Management](#6-memory-management)
7. [Batch Processing](#7-batch-processing)
8. [Frontend Performance](#8-frontend-performance)
9. [Profiling & Benchmarking](#9-profiling--benchmarking)
10. [Scalability Planning](#10-scalability-planning)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Performance Baseline

### 1.1 Current System Scale

| Metric | Value | Growth Rate |
|--------|-------|-------------|
| **OHLCV rows** | ~3,000,000 | ~250K/year |
| **Tickers** | ~951 | ~20/year |
| **Database size** | ~460 MB | ~40 MB/year |
| **API endpoints** | 88 | Stable |
| **Unit tests** | 750+ | Growing |
| **Parquet files** | ~1,222 | ~100/year |

### 1.2 Performance Targets

| Operation | Target Latency | Current | Priority |
|-----------|---------------|---------|----------|
| **API: Get OHLCV (single ticker)** | < 100ms | ~200ms | HIGH |
| **API: Get recommendation** | < 500ms | ~1s | HIGH |
| **API: Compute scores** | < 2s | ~5s | MEDIUM |
| **API: List tickers** | < 50ms | ~100ms | MEDIUM |
| **API: Backtest (1 year)** | < 5s | ~15s | MEDIUM |
| **Data: Fetch ticker (Yahoo)** | < 3s | ~2s | OK |
| **Data: Ingest batch (100 tickers)** | < 60s | ~90s | LOW |
| **Frontend: Initial page load** | < 2s | ~3s | MEDIUM |
| **Frontend: Chart render** | < 500ms | ~800ms | LOW |

### 1.3 Performance Measurement Framework

```python
import time
from functools import wraps
from contextlib import contextmanager

@contextmanager
def measure_time(label: str):
    """Context manager to measure execution time."""
    start = time.perf_counter()
    yield
    elapsed = (time.perf_counter() - start) * 1000
    if elapsed > 100:
        print(f"⏱ {label}: {elapsed:.1f}ms")
    else:
        print(f"  {label}: {elapsed:.1f}ms")

def timed(func):
    """Decorator to time function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        if elapsed > 100:
            import logging
            logging.getLogger(__name__).warning(
                f"SLOW: {func.__name__} took {elapsed:.1f}ms"
            )
        return result
    return wrapper
```

---

## 2. Database Optimization

### 2.1 SQLite Configuration

```python
# Optimal SQLite configuration for trading system
SQLITE_PRAGMAS = {
    "journal_mode": "WAL",           # Concurrent read/write
    "synchronous": "NORMAL",         # Balance safety/speed
    "cache_size": -64000,            # 64MB cache (negative = KB)
    "temp_store": "MEMORY",          # In-memory temp tables
    "mmap_size": 268435456,          # 256MB memory-mapped I/O
    "wal_autocheckpoint": 1000,      # Auto-checkpoint every 1000 pages
    "busy_timeout": 5000,            # 5s timeout for locked DB
    "foreign_keys": "ON",            # Enforce FK constraints
}

def configure_sqlite(conn):
    """Apply optimal SQLite pragmas."""
    for pragma, value in SQLITE_PRAGMAS.items():
        conn.execute(f"PRAGMA {pragma} = {value}")
```

### 2.2 Index Strategy

```sql
-- Critical indexes for OHLCV (largest table)
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_date 
    ON ohlcv(ticker, date DESC);          -- Most common query pattern

CREATE INDEX IF NOT EXISTS idx_ohlcv_date 
    ON ohlcv(date DESC);                  -- Date range scans

CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker 
    ON ohlcv(ticker);                     -- Ticker-only lookups

-- Scores table
CREATE INDEX IF NOT EXISTS idx_scores_ticker_date
    ON scores(ticker, date DESC);

-- Technical indicators
CREATE INDEX IF NOT EXISTS idx_ti_ticker_date
    ON technical_indicators(ticker, date DESC);

-- Foreign flow
CREATE INDEX IF NOT EXISTS idx_ff_ticker_date
    ON foreign_flow(ticker, date DESC);

-- Audit log
CREATE INDEX IF NOT EXISTS idx_audit_timestamp
    ON audit_log(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_event
    ON audit_log(event_type, timestamp DESC);

-- Orders
CREATE INDEX IF NOT EXISTS idx_orders_ticker_date
    ON orders(ticker, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status, created_at DESC);

-- Positions
CREATE INDEX IF NOT EXISTS idx_positions_status
    ON positions(status, ticker);
```

### 2.3 Index Maintenance

```python
def maintain_indexes(conn):
    """Periodic index maintenance."""
    # 1. Check index usage
    unused = conn.execute("""
        SELECT name, tbl_name 
        FROM sqlite_master 
        WHERE type = 'index' AND sql IS NOT NULL
    """).fetchall()
    
    # 2. ANALYZE (update query planner statistics)
    conn.execute("ANALYZE")
    
    # 3. Check for fragmentation
    fragmented = conn.execute("""
        SELECT name, tbl_name 
        FROM sqlite_master 
        WHERE type = 'index' 
        AND name NOT LIKE 'sqlite_%'
        AND name NOT LIKE 'idx_%'
    """).fetchall()
    
    # 4. Rebuild fragmented indexes
    for idx_name, tbl_name in fragmented:
        conn.execute(f"REINDEX {idx_name}")
```

### 2.4 WAL Management

```python
def manage_wal(db_path: str):
    """Manage WAL file size."""
    conn = sqlite3.connect(db_path)
    
    # Check WAL size
    wal_path = db_path + "-wal"
    wal_size = os.path.getsize(wal_path) / (1024 * 1024) if os.path.exists(wal_path) else 0
    
    if wal_size > 100:  # > 100MB
        # Force checkpoint
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        logger.info(f"WAL checkpointed: {wal_size:.1f}MB → 0")
    
    conn.close()
```

---

## 3. Query Tuning

### 3.1 Common Query Patterns

```python
# Pattern 1: Get latest OHLCV for ticker (most common)
# SLOW: full table scan
# SELECT * FROM ohlcv WHERE ticker = 'BBCA.JK' ORDER BY date DESC LIMIT 1

# FAST: uses idx_ohlcv_ticker_date
def get_latest_ohlcv(storage, ticker: str):
    return storage.execute_query(
        "SELECT * FROM ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        (ticker,)
    )

# Pattern 2: Date range query
def get_ohlcv_range(storage, ticker: str, start: str, end: str):
    return storage.execute_query(
        """SELECT * FROM ohlcv 
           WHERE ticker = ? AND date BETWEEN ? AND ?
           ORDER BY date""",
        (ticker, start, end)
    )

# Pattern 3: Batch ticker data (avoid N+1 queries)
def get_batch_latest_prices(storage, tickers: list):
    placeholders = ','.join('?' * len(tickers))
    return storage.execute_query(
        f"""SELECT ticker, close, date FROM ohlcv 
            WHERE ticker IN ({placeholders})
            AND date = (SELECT MAX(date) FROM ohlcv WHERE ticker = ohlcv.ticker)""",
        tickers
    )
```

### 3.2 Query Optimization Patterns

```python
# ANTI-PATTERN: N+1 queries
# SLOW: 991 queries
for ticker in tickers:
    price = get_latest_price(ticker)  # 1 query each

# FAST: 1 query
def get_all_latest_prices(storage):
    """Get latest price for all tickers in one query."""
    return storage.execute_query("""
        SELECT o.ticker, o.close, o.date
        FROM ohlcv o
        INNER JOIN (
            SELECT ticker, MAX(date) as max_date
            FROM ohlcv
            GROUP BY ticker
        ) latest ON o.ticker = latest.ticker AND o.date = latest.max_date
    """)

# ANTI-PATTERN: Loading entire DataFrame
# SLOW: loads all 3M rows
df = storage.load_ohlcv("BBCA.JK")  # all history
latest = df.iloc[-1]

# FAST: query only what you need
def get_latest_price(storage, ticker: str) -> float:
    result = storage.execute_query(
        "SELECT close FROM ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        (ticker,)
    )
    return result[0]["close"] if result else None
```

### 3.3 EXPLAIN QUERY PLAN

```python
def explain_query(conn, query: str, params: tuple = ()):
    """Analyze query execution plan."""
    plan = conn.execute(f"EXPLAIN QUERY PLAN {query}", params).fetchall()
    
    for row in plan:
        print(f"  {'  ' * row[0]}{row[3]}")
    
    # Check for TABLE SCAN (bad)
    has_scan = any("SCAN" in row[3] for row in plan)
    if has_scan:
        logger.warning(f"Query has TABLE SCAN: {query[:100]}")
    
    return plan
```

---

## 4. Caching Strategies

### 4.1 Cache Layers

```
┌──────────────────────────────────────────────────────┐
│              CACHE HIERARCHY                          │
├──────────────────────────────────────────────────────┤
│  L1: In-memory (Python dict)     │ TTL: 60s          │
│  → Hot data: latest prices, market status            │
├──────────────────────────────────────────────────────┤
│  L2: Redis (optional)            │ TTL: 5min         │
│  → Warm data: scores, indicators, recommendations    │
├──────────────────────────────────────────────────────┤
│  L3: SQLite database             │ Persistent        │
│  → Cold data: historical OHLCV, audit logs           │
├──────────────────────────────────────────────────────┤
│  L4: Parquet archive             │ Cold storage      │
│  → Archive data: raw files, historical snapshots     │
└──────────────────────────────────────────────────────┘
```

### 4.2 In-Memory Cache

```python
import time
from collections import OrderedDict

class LRUCache:
    """Thread-safe LRU cache with TTL."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 60):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
    
    def get(self, key: str):
        with self._lock:
            if key not in self.cache:
                return None
            
            value, timestamp = self.cache[key]
            if time.time() - timestamp > self.ttl:
                del self.cache[key]
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return value
    
    def set(self, key: str, value):
        with self._lock:
            self.cache[key] = (value, time.time())
            self.cache.move_to_end(key)
            
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)  # remove oldest
    
    def clear(self):
        with self._lock:
            self.cache.clear()

# Global cache instances
price_cache = LRUCache(max_size=1000, ttl_seconds=30)       # 30s for prices
score_cache = LRUCache(max_size=500, ttl_seconds=300)       # 5min for scores
recommendation_cache = LRUCache(max_size=500, ttl_seconds=300)
market_status_cache = LRUCache(max_size=10, ttl_seconds=60) # 1min for market status
```

### 4.3 Redis Cache (Optional)

```python
import redis.asyncio as redis

class RedisCache:
    """Redis-based cache for distributed deployments."""
    
    def __init__(self, url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(url)
    
    async def get(self, key: str):
        value = await self.redis.get(key)
        return json.loads(value) if value else None
    
    async def set(self, key: str, value, ttl: int = 300):
        await self.redis.setex(key, ttl, json.dumps(value, default=str))
    
    async def delete(self, key: str):
        await self.redis.delete(key)
    
    async def get_many(self, keys: list):
        values = await self.redis.mget(keys)
        return [json.loads(v) if v else None for v in values]
```

### 4.4 Cache-Aside Pattern

```python
async def get_recommendation(ticker: str, storage, decision_engine):
    """Cache-aside pattern for recommendations."""
    cache_key = f"recommendation:{ticker}"
    
    # 1. Try cache
    cached = recommendation_cache.get(cache_key)
    if cached:
        return cached
    
    # 2. Cache miss: compute
    result = decision_engine.recommend(ticker)
    
    # 3. Store in cache
    recommendation_cache.set(cache_key, result)
    
    return result
```

### 4.5 Cache Invalidation

```python
def invalidate_ticker_cache(ticker: str):
    """Invalidate all cache entries for a ticker."""
    price_cache.set(f"price:{ticker}", None)  # will be recomputed
    score_cache.set(f"scores:{ticker}", None)
    recommendation_cache.set(f"recommendation:{ticker}", None)
```

---

## 5. Async I/O

### 5.1 FastAPI Async Patterns

```python
# WRONG: blocking call in async endpoint
@app.get("/api/data/ohlcv")
async def get_ohlcv(ticker: str):
    df = storage.load_ohlcv(ticker)  # BLOCKING! This is sync
    return df.to_dict("records")

# CORRECT: run blocking I/O in thread pool
@app.get("/api/data/ohlcv")
async def get_ohlcv(ticker: str):
    df = await run_in_threadpool(storage.load_ohlcv, ticker)
    return df.to_dict("records")

# CORRECT: use async storage
@app.get("/api/recommend/{ticker}")
async def get_recommendation(ticker: str):
    # Parallel data fetching
    ohlcv_task = asyncio.create_task(run_in_threadpool(storage.load_ohlcv, ticker))
    scores_task = asyncio.create_task(run_in_threadpool(storage.get_scores, ticker))
    
    ohlcv = await ohlcv_task
    scores = await scores_task
    
    return process_recommendation(ohlcv, scores)
```

### 5.2 Parallel Data Fetching

```python
async def fetch_all_data(ticker: str, storage):
    """Fetch all data for a ticker in parallel."""
    tasks = {
        "ohlcv": asyncio.create_task(run_in_threadpool(storage.load_ohlcv, ticker)),
        "scores": asyncio.create_task(run_in_threadpool(storage.get_scores, ticker)),
        "indicators": asyncio.create_task(run_in_threadpool(storage.get_indicators, ticker)),
        "fundamental": asyncio.create_task(run_in_threadpool(storage.get_fundamental, ticker)),
        "foreign_flow": asyncio.create_task(run_in_threadpool(storage.get_foreign_flow, ticker)),
    }
    
    results = {}
    for key, task in tasks.items():
        try:
            results[key] = await task
        except Exception as e:
            logger.error(f"Failed to fetch {key} for {ticker}: {e}")
            results[key] = None
    
    return results
```

### 5.3 Batch Yahoo Finance Fetching

```python
async def fetch_batch_tickers(tickers: list, max_concurrent: int = 10):
    """Fetch multiple tickers concurrently with rate limiting."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_one(ticker: str):
        async with semaphore:
            return await run_in_threadpool(yf.download, ticker, period="1y")
    
    tasks = [fetch_one(t) for t in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return dict(zip(tickers, results))
```

---

## 6. Memory Management

### 6.1 DataFrame Memory Optimization

```python
def optimize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce DataFrame memory usage."""
    original_mem = df.memory_usage(deep=True).sum() / 1024**2
    
    for col in df.columns:
        col_type = df[col].dtype
        
        if col_type == 'object':
            # Convert to category if low cardinality
            if df[col].nunique() / len(df) < 0.5:
                df[col] = df[col].astype('category')
        
        elif col_type == 'float64':
            # Downcast to float32 if precision allows
            df[col] = pd.to_numeric(df[col], downcast='float')
        
        elif col_type == 'int64':
            # Downcast to smallest int type
            df[col] = pd.to_numeric(df[col], downcast='integer')
    
    optimized_mem = df.memory_usage(deep=True).sum() / 1024**2
    reduction = (1 - optimized_mem / original_mem) * 100
    
    logger.info(f"DataFrame memory: {original_mem:.1f}MB → {optimized_mem:.1f}MB ({reduction:.0f}% reduction)")
    
    return df
```

### 6.2 Lazy Loading

```python
class LazyOHLCV:
    """Lazy-loading OHLCV data — only load when accessed."""
    
    def __init__(self, storage, ticker: str):
        self.storage = storage
        self.ticker = ticker
        self._df = None
    
    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            self._df = self.storage.load_ohlcv(self.ticker)
        return self._df
    
    def latest_price(self) -> float:
        """Get latest price without loading full DataFrame."""
        if self._df is not None:
            return float(self._df["close"].iloc[-1])
        # Direct DB query
        result = self.storage.execute_query(
            "SELECT close FROM ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (self.ticker,)
        )
        return result[0]["close"] if result else None
```

### 6.3 Memory Monitoring

```python
import psutil
import resource

def memory_usage() -> dict:
    """Get current memory usage."""
    process = psutil.Process()
    mem_info = process.memory_info()
    
    return {
        "rss_mb": mem_info.rss / 1024**2,       # Resident Set Size
        "vms_mb": mem_info.vms / 1024**2,       # Virtual Memory Size
        "percent": process.memory_percent(),
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }
```

---

## 7. Batch Processing

### 7.1 Score Computation Batch

```python
def compute_scores_batch(tickers: list, storage, batch_size: int = 50):
    """Compute scores for multiple tickers in batches."""
    results = {}
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        
        for ticker in batch:
            try:
                scores = compute_scores(ticker, storage)
                results[ticker] = scores
            except Exception as e:
                logger.error(f"Score computation failed for {ticker}: {e}")
                results[ticker] = None
        
        # Checkpoint: save batch results
        save_scores_batch(results, storage)
        
        # Memory cleanup
        gc.collect()
        
        logger.info(f"Computed scores: {i + len(batch)}/{len(tickers)}")
    
    return results
```

### 7.2 Data Ingestion Pipeline

```python
async def ingest_ticker_batch(tickers: list, storage, max_concurrent: int = 5):
    """Ingest data for multiple tickers with controlled concurrency."""
    semaphore = asyncio.Semaphore(max_concurrent)
    rate_limiter = RateLimiter(rate=1.0)  # 1 request/sec
    
    async def ingest_one(ticker: str):
        async with semaphore:
            await rate_limiter.acquire()
            try:
                df = await run_in_threadpool(yf.download, ticker, period="2y")
                if not df.empty:
                    storage.save_ohlcv(ticker, df)
                    return {"ticker": ticker, "status": "ok", "rows": len(df)}
            except Exception as e:
                return {"ticker": ticker, "status": "error", "error": str(e)}
    
    tasks = [ingest_one(t) for t in tickers]
    results = await asyncio.gather(*tasks)
    
    success = sum(1 for r in results if r["status"] == "ok")
    logger.info(f"Ingestion complete: {success}/{len(tickers)} successful")
    
    return results
```

---

## 8. Frontend Performance

### 8.1 Next.js Optimization

| Technique | Impact | Implementation |
|-----------|--------|----------------|
| **SSG/SSR** | Faster initial load | `getStaticProps` / `getServerSideProps` |
| **Code splitting** | Smaller bundles | Dynamic imports |
| **Image optimization** | -60% image size | `next/image` |
| **API response caching** | Fewer requests | `revalidate` in ISR |
| **Lazy loading** | Faster initial render | `next/dynamic` |
| **Prefetching** | Instant navigation | `<Link prefetch>` |

### 8.2 API Response Optimization

```python
# Pagination for large responses
@app.get("/api/data/ohlcv")
async def get_ohlcv(
    ticker: str,
    page: int = 1,
    page_size: int = 500,
):
    """Paginated OHLCV response."""
    offset = (page - 1) * page_size
    df = storage.load_ohlcv(ticker)
    total = len(df)
    
    paginated = df.iloc[offset:offset + page_size]
    
    return {
        "status": "ok",
        "data": paginated.to_dict("records"),
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }

# Response compression
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # compress > 1KB
```

### 8.3 Frontend Caching

```typescript
// SWR for data fetching with cache
import useSWR from 'swr';

function useTickerData(ticker: string) {
  const { data, error } = useSWR(
    `/api/data/ohlcv?ticker=${ticker}`,
    fetcher,
    {
      revalidateOnFocus: false,
      revalidateIfStale: false,
      refreshInterval: 60000, // refresh every 60s
      dedupingInterval: 30000, // dedupe within 30s
    }
  );
  return { data, error };
}

// React Query for more control
import { useQuery } from '@tanstack/react-query';

function useRecommendation(ticker: string) {
  return useQuery({
    queryKey: ['recommendation', ticker],
    queryFn: () => api.getRecommendation(ticker),
    staleTime: 5 * 60 * 1000,  // 5 minutes
    cacheTime: 30 * 60 * 1000, // 30 minutes
  });
}
```

---

## 9. Profiling & Benchmarking

### 9.1 Python Profiling

```python
import cProfile
import pstats

def profile_function(func, *args, **kwargs):
    """Profile a function and print stats."""
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = func(*args, **kwargs)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # top 20 by cumulative time
    
    return result

# Usage
profile_function(compute_scores, "BBCA.JK", storage)
```

### 9.2 Database Benchmarking

```python
def benchmark_queries(storage, n_runs: int = 100):
    """Benchmark critical database queries."""
    benchmarks = {
        "latest_price": lambda: storage.execute_query(
            "SELECT close FROM ohlcv WHERE ticker = 'BBCA.JK' ORDER BY date DESC LIMIT 1"
        ),
        "ticker_history_1y": lambda: storage.execute_query(
            "SELECT * FROM ohlcv WHERE ticker = 'BBCA.JK' AND date >= '2025-01-01' ORDER BY date"
        ),
        "all_latest_prices": lambda: storage.execute_query("""
            SELECT o.ticker, o.close FROM ohlcv o
            INNER JOIN (SELECT ticker, MAX(date) as max_date FROM ohlcv GROUP BY ticker) l
            ON o.ticker = l.ticker AND o.date = l.max_date
        """),
        "scores_lookup": lambda: storage.execute_query(
            "SELECT * FROM scores WHERE ticker = 'BBCA.JK' ORDER BY date DESC LIMIT 1"
        ),
    }
    
    results = {}
    for name, query_fn in benchmarks.items():
        times = []
        for _ in range(n_runs):
            start = time.perf_counter()
            query_fn()
            times.append((time.perf_counter() - start) * 1000)
        
        results[name] = {
            "mean_ms": np.mean(times),
            "p50_ms": np.percentile(times, 50),
            "p95_ms": np.percentile(times, 95),
            "p99_ms": np.percentile(times, 99),
            "max_ms": np.max(times),
        }
    
    return results
```

### 9.3 Benchmark Script

```bash
# Run benchmarks
.venv/bin/python scripts/bench/speedtest_idx.py

# Expected output:
# Query: latest_price          mean: 0.5ms  p99: 2.1ms
# Query: ticker_history_1y     mean: 15ms   p99: 25ms
# Query: all_latest_prices     mean: 50ms   p99: 80ms
# Query: scores_lookup         mean: 0.3ms  p99: 1.5ms
```

---

## 10. Scalability Planning

### 10.1 Growth Projections

| Year | OHLCV Rows | DB Size | Tickers | API RPS |
|------|-----------|---------|---------|---------|
| **2026** | 3M | 460 MB | 991 | 10 |
| **2027** | 3.25M | 500 MB | 1,011 | 50 |
| **2028** | 3.5M | 540 MB | 1,031 | 100 |
| **2030** | 4M | 620 MB | 1,071 | 500 |

### 10.2 Scaling Strategy

| Component | Current | When to Scale | How |
|-----------|---------|--------------|-----|
| **SQLite** | Single file | > 1GB or high write contention | PostgreSQL migration |
| **API** | Single process | > 100 RPS | Uvicorn workers + Nginx |
| **Cache** | In-memory dict | Multi-instance | Redis |
| **Frontend** | Single Next.js | High traffic | CDN + edge caching |
| **Data fetch** | Sequential | > 1,000 tickers | Parallel + queue |

### 10.3 SQLite → PostgreSQL Migration Path

```python
# When SQLite hits limits, migrate to PostgreSQL
# Key differences:
MIGRATION_NOTES = {
    "connection": "sqlite3.connect() → psycopg2.connect()",
    "pragma": "SQLite PRAGMAs → PostgreSQL config (shared_buffers, work_mem)",
    "wal": "SQLite WAL → PostgreSQL WAL (built-in)",
    "concurrent_writes": "SQLite limited → PostgreSQL full concurrent",
    "partitioning": "Not in SQLite → PostgreSQL table partitioning by date",
    "full_text_search": "LIKE → PostgreSQL tsvector/GIN",
}
```

---

## 11. Implementasi untuk IDX

### 11.1 IDX-Specific Performance

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **900+ tickers** | Batch processing needed | Parallel fetch with rate limiting |
| **Thin liquidity stocks** | Many zeros in volume | Sparse data optimization |
| **Yahoo Finance rate limit** | 1 req/sec max | Rate limiter + caching |
| **IDX scraper** | 0.3s/request | Cache + batch |
| **Market hours only** | Idle off-hours | Schedule heavy tasks off-hours |
| **WIB timezone** | Data alignment | Consistent timezone handling |

### 11.2 Optimal Schedule

```python
OPTIMAL_SCHEDULE = {
    # Off-market hours (16:15 - 08:59 WIB)
    "data_fetch": "17:00 WIB",       # After market close
    "score_compute": "18:00 WIB",    # After data update
    "backtest_run": "20:00 WIB",     # Off-peak
    "db_maintenance": "23:00 WIB",   # Late night
    "backup": "01:00 WIB",           # Early morning
    "index_rebuild": "02:00 WIB",    # Lowest activity
    
    # Market hours (09:00 - 15:50 WIB)
    "price_update": "every 30s",     # During market
    "position_monitor": "every 60s", # During market
    "signal_check": "every 5min",    # During market
}
```

---

## 12. Checklist Implementasi

### Database
- [ ] SQLite PRAGMAs configured (WAL, cache, mmap)
- [ ] Indexes on all hot query paths
- [ ] ANALYZE run periodically
- [ ] WAL checkpoint scheduled
- [ ] Database size monitored
- [ ] No TABLE SCAN in critical queries

### Query
- [ ] EXPLAIN QUERY PLAN for all critical queries
- [ ] No N+1 query patterns
- [ ] Batch queries for multiple tickers
- [ ] Pagination on large result sets
- [ ] Parameterized queries (no f-string SQL)

### Caching
- [ ] LRU cache for hot data (prices, market status)
- [ ] Cache for scores and recommendations (5min TTL)
- [ ] Cache invalidation on data update
- [ ] Redis for multi-instance (if needed)
- [ ] Cache hit rate monitoring

### Async
- [ ] No blocking I/O in async endpoints
- [ ] Parallel data fetching where possible
- [ ] Semaphore for rate-limited external APIs
- [ ] Thread pool for CPU-bound work

### Memory
- [ ] DataFrame downcasting (float64→float32, int64→int32)
- [ ] Category dtype for low-cardinality columns
- [ ] Lazy loading for large datasets
- [ ] gc.collect() after batch processing
- [ ] Memory usage monitoring

### Frontend
- [ ] Gzip compression enabled
- [ ] API response pagination
- [ ] SWR/React Query for client caching
- [ ] Code splitting (dynamic imports)
- [ ] Image optimization (next/image)
- [ ] Virtual scrolling for large lists

### Profiling
- [ ] cProfile for score computation
- [ ] Database query benchmarks
- [ ] API endpoint latency monitoring
- [ ] Memory usage tracking
- [ ] Slow query detection (> 100ms)

### Scalability
- [ ] Growth projections documented
- [ ] SQLite → PostgreSQL migration plan
- [ ] Horizontal scaling plan (Uvicorn workers)
- [ ] Redis migration plan for cache
- [ ] CDN plan for frontend

---

## 13. GPU/CUDA Acceleration

### 13.1 Aturan Wajib: Selalu Periksa Kemungkinan GPU

**Setiap proses development, testing, dan production** harus selalu memeriksa apakah GPU CUDA dapat membantu mempercepat operasi. GPU sudah tersedia di project `global` dan terbukti berfungsi.

### 13.2 Hardware yang Tersedia

| GPU | Model | VRAM | Compute Capability | Status | Penggunaan |
|-----|-------|------|--------------------|---------|------------|
| **GPU 0** | NVIDIA GeForce GTX 1050 Ti (Pascal GP107) | 4 GB | 6.1 | Digunakan Xorg/GNOME display | **Hindari** untuk compute (display overhead) |
| **GPU 1** | NVIDIA GeForce GTX 1050 Ti (Pascal GP107) | 4 GB | 6.1 | Bebas untuk ML compute | **Prefer** `cuda:1` untuk semua workload |
| **Driver** | NVIDIA 580.173.02 | — | — | — | — |
| **CUDA Runtime** | 13.0 | — | — | — | — |
| **Toolkit** | nvcc 12.0.140 | — | — | — | — |
| **cuDNN** | 8.x (system), 9.1 (torch wheel) | — | — | — | — |

### 13.3 Batasan Hardware (Pascal GP107)

| Batasan | Implikasi | Mitigasi |
|---------|-----------|----------|
| **4 GB VRAM per GPU** | Batch size dan model size terbatas | `batch_size <= 64`, `hidden_dim <= 256` |
| **No Tensor Cores** (Pascal) | FP16 acceleration terbatas | FP32 adalah primary path. FP16 mixed precision limited benefit. |
| **Compute capability 6.1** | Tidak support fitur arsitektur baru (Ampere/Hopper) | Gunakan fitur CUDA yang compatible dengan cc 6.1 |
| **2 GPU identik** | Bisa parallel training 2 model sekaligus | GPU 0 untuk display + light task, GPU 1 untuk heavy compute |

### 13.4 Software Stack

| Komponen | Versi | Status |
|----------|-------|--------|
| **PyTorch** | 2.5.1+cu121 | Terinstall di `.venv`, auto-detect CUDA |
| **Install command** | `pip install -e ".[gpu]" --index-url https://download.pytorch.org/whl/cu121` | — |
| **Backend priority** | PyTorch > TensorFlow > sklearn | Auto-fallback jika CUDA tidak tersedia |
| **CUDA device preference** | `cuda:1` (GPU 1, bebas dari display) | Auto-detect di `deep_learning.py` |

### 13.5 Operasi yang Wajib Diperiksa untuk GPU Acceleration

Setiap modul yang melakukan komputasi berikut **wajib** memeriksa apakah GPU dapat membantu:

| Operasi | Modul/Sumber | GPU Benefit | Implementasi |
|---------|-------------|-------------|--------------|
| **LSTM training & inference** | `ai_learning/deep_learning.py` | **Tinggi** — 5-20x faster untuk 900+ tickers | PyTorch LSTM dengan `device=cuda:1` |
| **Walk-forward parallel folds** | `ai_learning/walk_forward.py` | **Tinggi** — parallel fold training | PyTorch dengan `use_gpu=True` |
| **Ensemble model training** | `ai_learning/ensemble.py` | **Sedang** — multiple models parallel | Train di GPU 0 dan GPU 1 sekaligus |
| **Backtesting (Monte Carlo)** | `backtest/metrics.py` | **Sedang-Tinggi** — 10K simulations | Tensor operations di GPU |
| **Feature engineering (bulk)** | `analysis/pipeline.py` | **Sedang** — 900+ tickers × 20+ indicators | Pandas/numpy GPU (cuDF jika available) |
| **Correlation matrix computation** | `analysis/relationship.py` | **Rendah-Sedang** — 900×900 matrix | numpy cukup, GPU opsional untuk 900+ |
| **Regime detection (HMM)** | `analysis/enhanced_regime.py` | **Sedang** — HMM fitting | `hmmlearn` tidak native GPU, tapi pre-processing bisa |
| **Factor screening (900+ tickers)** | `analysis/factor_screener.py` | **Rendah-Sedang** — bulk computation | numpy vectorization cukup, GPU opsional |
| **Vectorized backtest** | `backtest/engine.py` | **Sedang** — large portfolio simulation | Tensor operations di GPU untuk portfolio level |
| **Risk simulation (VaR Monte Carlo)** | `risk/engine.py` | **Sedang-Tinggi** — 10K+ scenarios | GPU untuk Monte Carlo simulation |
| **Data normalization (bulk)** | `data/acquisition.py` | **Rendah** — I/O bound, bukan compute | GPU tidak membantu untuk I/O |
| **NLP/Sentiment (IndoBERT)** | `sentiment/engine.py` | **Tinggi** — transformer inference | HuggingFace `transformers` dengan GPU |

### 13.6 Aturan Pemeriksaan GPU (Wajib di Setiap Modul)

```python
import torch

def get_device() -> torch.device:
    """
    Auto-detect best available device.
    Priority: cuda:1 (GPU 1, free) > cuda:0 (GPU 0, display) > cpu
    """
    if not torch.cuda.is_available():
        return torch.device("cpu")
    
    n_gpus = torch.cuda.device_count()
    if n_gpus >= 2:
        # Prefer GPU 1 (free from display overhead)
        return torch.device("cuda:1")
    elif n_gpus == 1:
        # Only GPU 0 available (shared with display)
        return torch.device("cuda:0")
    return torch.device("cpu")

def check_gpu_memory(device: torch.device) -> dict:
    """Check available VRAM before allocating model."""
    if device.type == "cpu":
        return {"available": None, "total": None, "used": None}
    
    torch.cuda.empty_cache()
    total = torch.cuda.get_device_properties(device).total_memory
    allocated = torch.cuda.memory_allocated(device)
    available = total - allocated
    return {
        "available_mb": available / 1024**2,
        "total_mb": total / 1024**2,
        "used_mb": allocated / 1024**2,
    }

def safe_batch_size(device: torch.device, sample_size_mb: float) -> int:
    """Calculate safe batch size based on available VRAM."""
    if device.type == "cpu":
        return 32  # CPU fallback
    
    mem = check_gpu_memory(device)
    available_mb = mem["available_mb"]
    # Reserve 20% for overhead
    usable_mb = available_mb * 0.8
    batch_size = int(usable_mb / sample_size_mb)
    # Cap at 64 for GTX 1050 Ti (4GB VRAM)
    return min(batch_size, 64)
```

### 13.7 Checklist GPU untuk Setiap Modul Baru

Setiap modul baru yang melakukan komputasi intensif **wajib** memenuhi checklist berikut:

- [ ] **Pemeriksaan awal:** Apakah operasi ini compute-bound? Jika ya, periksa GPU.
- [ ] **Auto-detect device:** Gunakan `get_device()` — jangan hardcode `cuda:0` atau `cuda:1`.
- [ ] **VRAM check:** Cek `check_gpu_memory()` sebelum alokasi model. Jangan melebihi 4 GB.
- [ ] **Batch size adaptif:** Gunakan `safe_batch_size()` — maksimal 64 untuk GTX 1050 Ti.
- [ ] **Hidden dim limit:** Maksimal 256 untuk LSTM/Transformer di 4 GB VRAM.
- [ ] **FP32 primary:** Pascal tidak punya Tensor Cores. FP32 adalah path utama. FP16 mixed precision hanya marginal benefit.
- [ ] **CPU fallback:** Jika CUDA tidak tersedia, fallback ke CPU otomatis. Tidak crash.
- [ ] **GPU 1 preference:** Jika 2 GPU tersedia, prefer `cuda:1` (bebas dari display overhead).
- [ ] **Memory cleanup:** `torch.cuda.empty_cache()` setelah training/inference selesai.
- [ ] **Monitoring:** Log GPU utilization (`nvidia-smi`) sebelum dan sesudah operasi berat.
- [ ] **Benchmark:** Bandingkan wall-time GPU vs CPU untuk operasi yang sama. Jika GPU tidak lebih cepat, gunakan CPU.
- [ ] **Graceful degradation:** Jika VRAM tidak cukup, auto-reduce batch size atau fallback ke CPU.

### 13.8 Operasi yang TIDAK Perlu GPU

| Operasi | Alasan |
|---------|--------|
| **Data fetching (Yahoo, IDX scraper)** | I/O bound, bukan compute |
| **Database read/write (SQLite)** | I/O bound |
| **API request handling (FastAPI)** | Network bound |
| **Single ticker score computation** | Data terlalu kecil untuk GPU overhead |
| **Technical indicators (RSI, MACD)** | pandas vectorization sudah cepat |
| **Frontend rendering** | Browser/Next.js, bukan Python |
| **Logging & audit trail** | I/O bound |
| **Rate limiting** | Logic bound, bukan compute |

### 13.9 Monitoring GPU

```bash
# Real-time monitoring (run di terminal terpisah)
nvidia-smi -l 1

# One-shot check
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv

# Output example:
# index, name, memory.total [MiB], memory.used [MiB], memory.free [MiB], utilization.gpu [%], temperature.gpu [C]
# 0, NVIDIA GeForce GTX 1050 Ti, 4096 MiB, 520 MiB, 3576 MiB, 3 %, 42
# 1, NVIDIA GeForce GTX 1050 Ti, 4096 MiB, 0 MiB, 4096 MiB, 0 %, 39
```

### 13.10 Adopsi dari Project `global`

Implementasi GPU sudah berfungsi di project `global`:

| File | Fungsi GPU | Status |
|------|-----------|--------|
| `src/trading_system/ai_learning/deep_learning.py` | LSTM training dengan PyTorch CUDA, auto-detect `cuda:1` | Production |
| `src/trading_system/ai_learning/walk_forward.py` | Parallel fold training dengan `use_gpu=True` | Working |
| `src/trading_system/ai_learning/ensemble.py` | Multi-model training | Working |
| `pyproject.toml` | `[gpu]` extra: `torch>=2.5.1+cu121` | Configured |
| `.venv/` | PyTorch 2.5.1+cu121 terinstall | Active |

**Cara adopsi:** Copy `deep_learning.py` dengan `get_device()` pattern, atau adaptasi pattern auto-detect ke modul baru yang membutuhkan GPU.

---

## Referensi

1. `src/trading_system/data/storage.py` — Data storage with SQLite
2. `src/trading_system/data/rate_limiter.py` — Rate limiting
3. `src/trading_system/api/app.py` — FastAPI application
4. `scripts/bench/` — Benchmark scripts
5. `frontend/app/lib/api.ts` — Frontend API layer
6. `pustaka/22-data-engineering-pipeline.md` — Data pipeline
7. `pustaka/27-deployment-devops-trading.md` — Deployment
8. `pustaka/28-api-design-integration-patterns.md` — API design
9. SQLite Optimization: https://www.sqlite.org/optimizer.html
10. FastAPI Performance: https://fastapi.tiangolo.com/deployment/
11. `src/trading_system/ai_learning/deep_learning.py` — GPU/CUDA implementation (PyTorch, cuda:1)
12. `pustaka/23-machine-learning-trading.md` — ML pipeline, walk-forward, ensemble
13. PyTorch CUDA: https://pytorch.org/docs/stable/cuda.html
14. NVIDIA GTX 1050 Ti specs: https://www.nvidia.com/en-us/geforce/graphics-cards/gtx-1050-ti/

---

> **Catatan:** Performance bukan tentang premature optimization, tetapi tentang mengetahui bottleneck dan mengatasinya secara sistematis. Ukur dulu, optimasi kemudian. "Premature optimization is the root of all evil" — Donald Knuth.
