# Bahasa Pemrograman Terbaik untuk Aplikasi Pasar Modal

> **Tujuan:** Dokumen ini adalah hasil riset internet mendalam tentang bahasa pemrograman dan tech stack terbaik untuk membangun aplikasi pasar modal (trading system) — dari Frontend, Middleware, hingga Backend — dengan rekomendasi spesifik untuk konteks IDX/Indonesia dan sistem `trading-system` v0.1.11 yang sudah ada di `/home/petrick/projects/global`.

---

## Daftar Isi

1. [Arsitektur Aplikasi Pasar Modal](#1-arsitektur-aplikasi-pasar-modal)
2. [Frontend: Bahasa & Framework](#2-frontend-bahasa--framework)
3. [Middleware: API Gateway & Message Queue](#3-middleware-api-gateway--message-queue)
4. [Backend: Bahasa & Framework](#4-backend-bahasa--framework)
5. [Database & Storage Layer](#5-database--storage-layer)
6. [Benchmark Performance](#6-benchmark-performance)
7. [Rekomendasi Tech Stack](#7-rekomendasi-tech-stack)
8. [Pertimbangan Khusus IDX](#8-pertimbangan-khusus-idx)
9. [Adopsi dari Proyek Existing](#9-adopsi-dari-proyek-existing)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Arsitektur Aplikasi Pasar Modal

### 1.1 Layer Arsitektur

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND LAYER                           │
│  Web Dashboard │ Mobile App │ Real-Time Charts │ Order UI   │
│  (React/Next.js │ React Native/Flutter │ WebSocket │ D3.js) │
├─────────────────────────────────────────────────────────────┤
│                     MIDDLEWARE LAYER                         │
│  API Gateway │ Auth │ Rate Limiting │ WebSocket Hub          │
│  Message Queue │ Event Bus │ gRPC/REST Translation           │
│  (Go/Nginx │ Redis │ Kafka/RabbitMQ │ gRPC)                 │
├─────────────────────────────────────────────────────────────┤
│                     BACKEND LAYER                            │
│  Decision Engine │ Risk Engine │ Execution Engine            │
│  Backtest Engine │ Sentiment Engine │ ML/AI Engine           │
│  (Python/FastAPI │ Go microservices │ Rust matching engine)  │
├─────────────────────────────────────────────────────────────┤
│                     DATA LAYER                               │
│  PostgreSQL │ Redis │ Time-Series DB │ Parquet Archive       │
│  SQLite (dev) │ S3/MinIO │ InfluxDB/TimescaleDB              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Prinsip Pemilihan Tech Stack

| Prinsip | Penjelasan |
|---------|------------|
| **Performance** | Real-time data, low latency untuk eksekusi |
| **Reliability** | Tidak boleh crash saat market volatile |
| **Scalability** | Bisa handle 900+ tickers, ribuan concurrent users |
| **Developer velocity** | Solo/small team → fast development cycle |
| **Ecosystem** | Library untuk charting, ML, financial computation |
| **Hiring** | Kemudahan mencari developer |
| **Type safety** | Mencegah bug di sistem finansial |
| **Community** | Stack Overflow, dokumentasi, tutorial |

---

## 2. Frontend: Bahasa & Framework

### 2.1 Bahasa: TypeScript (Juara Mutlak)

| Bahasa | Score | Alasan |
|--------|-------|--------|
| **TypeScript** | ★★★★★ | Industry standard untuk web frontend, type safety, ecosystem terbesar |
| JavaScript | ★★★☆☆ | OK tapi tidak ada type safety → berbahaya untuk sistem finansial |
| Dart | ★★★☆☆ | Hanya untuk Flutter, ecosystem terbatas |
| Python (transpile) | ★★☆☆☆ | Tidak practical untuk frontend |

> **Verdict:** **TypeScript** adalah satu-satunya pilihan rasional untuk frontend aplikasi pasar modal. Type safety mencegah bug kritis di UI finansial.

### 2.2 Framework: Next.js vs SvelteKit vs Nuxt vs Vue vs Angular

| Framework | UI Library | Bundle Size (gzipped) | Performance | Ecosystem | Learning Curve | Score |
|-----------|-----------|----------------------|-------------|-----------|----------------|-------|
| **Next.js 16** | React 19 | ~85KB | Excellent | **Largest** | Steep | ★★★★★ |
| **SvelteKit 2** | Svelte 5 | **~15KB** | **Best** | Growing | Gentle | ★★★★☆ |
| **Nuxt 3** | Vue 3 | ~60KB | Good | Large | Moderate | ★★★★☆ |
| **Vue 3 (SPA)** | Vue 3 | ~30KB | Good | Large | Easy | ★★★☆☆ |
| **Angular 17** | Angular | ~120KB | Good | Enterprise | Very Steep | ★★★☆☆ |

### 2.3 Detail Perbandingan

#### Next.js (React) — **REKOMENDASI #1**

**Kelebihan:**
- Ecosystem terbesar: shadcn/ui, Tremor (dashboard), Recharts, Lightweight Charts
- Server Components → zero JS untuk static parts
- React Native untuk mobile app (code sharing)
- ISR (Incremental Static Regeneration) untuk caching
- 45M weekly npm downloads (24x SvelteKit)
- 138K+ GitHub stars
- Hiring pool terbesar

**Kekurangan:**
- Bundle size terbesar (~85KB baseline)
- App Router complexity (caching, server components)
- Vercel-centric (beberapa feature optimal di Vercel)
- Frequent breaking changes antar major version

**Best for:** Aplikasi trading kompleks dengan banyak third-party integrations, dashboard data-heavy, tim yang butuh hiring mudah

#### SvelteKit (Svelte) — **REKOMENDASI #2 (Performance)**

**Kelebihan:**
- **Bundle terkecil** (~15KB) — 5-6x lebih kecil dari Next.js
- **Performance terbaik** — direct DOM manipulation, no virtual DOM
- Lighthouse score 95-100 (vs Next.js 85-95)
- Cold start tercepat (~80ms vs Next.js ~300ms)
- Developer experience terbaik (paling sedikit boilerplate)
- Best untuk real-time data (fine-grained reactivity)

**Kekurangan:**
- Ecosystem 10x lebih kecil dari React
- Sulit hire developer Svelte
- Library charting terbatas (bisa pakai D3.js langsung)
- Tidak ada React Native equivalent untuk mobile

**Best for:** Real-time trading dashboard, performance-critical UI, solo developer yang value DX

#### Nuxt 3 (Vue) — **REKOMENDASI #3**

**Kelebihan:**
- Module system terbaik (200+ modules: auth, image, SEO)
- Auto-imports → less boilerplate
- Nitro server engine → deploy ke platform apapun
- Vue lebih mudah dipelajari dari React
- Hybrid rendering per-route

**Kekurangan:**
- Ecosystem lebih kecil dari React
- Boilerplate SaaS lebih sedikit
- Bundle size menengah (~60KB)

**Best for:** Tim dengan Vue expertise, SEO-heavy applications

### 2.4 Mobile App

| Framework | Bahasa | Performance | Code Sharing | Score |
|-----------|--------|-------------|--------------|-------|
| **React Native** | TypeScript/JS | Native-like | **High** (dengan React web) | ★★★★★ |
| **Flutter** | Dart | **Best** | Medium (UI berbeda) | ★★★★☆ |
| **Kotlin (Native)** | Kotlin | **Best** | None | ★★★☆☆ |
| **Swift (Native)** | Swift | **Best** | None | ★★★☆☆ |

> **Verdict:** **React Native** untuk code sharing dengan web (TypeScript + React). **Flutter** jika performance UI adalah prioritas utama.

### 2.5 Charting & Visualization Library

| Library | Framework | Use Case | License |
|---------|-----------|----------|---------|
| **Lightweight Charts** | Framework-agnostic | Candlestick, OHLCV (TradingView) | Apache 2.0 |
| **Recharts** | React | Line, bar, area charts | MIT |
| **Tremor** | React | Dashboard components | Apache 2.0 |
| **D3.js** | Framework-agnostic | Custom visualization | ISC |
| **AG Grid** | React/Vue/Angular | Data grid (portfolio table) | MIT/Enterprise |
| **TanStack Table** | Framework-agnostic | Headless table | MIT |
| **Nivo** | React | Charts (sunburst, calendar) | MIT |
| **react-window** | React | Virtual scrolling (large lists) | MIT |

---

## 3. Middleware: API Gateway & Message Queue

### 3.1 API Gateway

| Technology | Bahasa | Performance | Use Case | Score |
|-----------|--------|-------------|----------|-------|
| **Go (chi/Gin)** | Go | 105K RPS | High-throughput gateway | ★★★★★ |
| **Rust (Actix)** | Rust | 110K RPS | Ultra-low latency gateway | ★★★★★ |
| **Nginx** | C | 200K+ RPS | Reverse proxy, load balancer | ★★★★★ |
| **Kong** | Lua/OpenResty | 80K RPS | Enterprise API gateway | ★★★★☆ |
| **Node.js (Express)** | TypeScript | 18K RPS | Simple gateway | ★★★☆☆ |
| **Python (FastAPI)** | Python | 8K RPS | Prototyping only | ★★☆☆☆ |

> **Verdict:** **Go** untuk API gateway (best balance performance + simplicity). **Nginx** sebagai reverse proxy di depan.

### 3.2 Service-to-Service Communication

| Protocol | Use Case | Performance | Score |
|----------|----------|-------------|-------|
| **gRPC** | Internal microservices | **Best** (binary, multiplexed) | ★★★★★ |
| **REST/HTTP** | External API, frontend | Good (universal) | ★★★★☆ |
| **WebSocket** | Real-time data push | Good (persistent) | ★★★★★ |
| **GraphQL** | Flexible client queries | Moderate (overhead) | ★★★☆☆ |
| **FIX** | Broker communication | Industry standard | ★★★★☆ |

### 3.3 Message Queue / Event Bus

| Technology | Performance | Use Case | Score |
|-----------|-------------|----------|-------|
| **Apache Kafka** | **Highest throughput** | Event streaming, order events | ★★★★★ |
| **RabbitMQ** | Good | Task queue, RPC | ★★★★☆ |
| **Redis Pub/Sub** | Fast | Simple pub/sub, cache invalidation | ★★★★☆ |
| **NATS** | Very fast | Lightweight messaging | ★★★☆☆ |
| **Amazon SQS** | Managed | Cloud-native queue | ★★★☆☆ |

> **Verdict:** **Kafka** untuk event-driven architecture (order events, trade fills). **Redis** untuk simple pub/sub dan caching. **RabbitMQ** untuk task queue.

### 3.4 Caching

| Technology | Use Case | Latency | Score |
|-----------|----------|---------|-------|
| **Redis** | Session, price cache, hot data | <1ms | ★★★★★ |
| **In-memory (dict)** | Single-process cache | ~0ms | ★★★★☆ |
| **Memcached** | Simple key-value | <1ms | ★★★☆☆ |

---

## 4. Backend: Bahasa & Framework

### 4.1 Perbandingan Bahasa Backend

| Bahasa | Performance | Dev Speed | Ecosystem | Type Safety | Concurrency | Memory | Score |
|--------|-------------|-----------|-----------|-------------|-------------|--------|-------|
| **Python** | Slow (8K RPS) | **Fastest** | **Largest** (ML/data) | Optional | GIL limited | Medium | ★★★★☆ |
| **Go** | **Fast** (48K RPS) | Fast | Growing | Strong | **Goroutines** | **Low** (12MB) | ★★★★★ |
| **Rust** | **Fastest** (110K RPS) | Medium | Growing | **Strongest** | Fearless | **Lowest** | ★★★★☆ |
| **Java** | Good (32K RPS) | Slow | **Largest** | Strong | Virtual threads | High (287MB) | ★★★★☆ |
| **TypeScript/Node** | Medium (18K RPS) | Fast | Large | Optional | Event loop | Medium | ★★★☆☆ |
| **C++** | **Fastest** | Slow | Large | Manual | Manual | Lowest | ★★★☆☆ |

### 4.2 Detail Per Bahasa

#### Python (FastAPI) — **REKOMENDASI untuk Decision/Risk/ML Engine**

**Kelebihan:**
- **Ecosystem ML/Data terbesar**: pandas, numpy, scikit-learn, PyTorch, TensorFlow
- FastAPI: auto docs, Pydantic validation, async support
- Development speed tercepat (847 LOC vs Go 1456 vs Java 2847 untuk API sama)
- Existing codebase `trading-system` v0.1.11 sudah Python
- Library finansial: ta-lib, backtrader, zipline-reloaded, pyfolio
- IndoBERT untuk NLP Bahasa Indonesia
- Yahoo Finance yfinance, PRAW (Reddit), PyTrends

**Kekurangan:**
- **Slowest**: 8K RPS (6x lebih lambat dari Go)
- GIL → tidak ada true parallelism untuk CPU-bound
- Memory tinggi under load (234MB vs Go 47MB)
- Cold start 487ms (vs Go 11ms)
- Tidak suitable untuk HFT atau matching engine

**Best for:** Decision engine, risk engine, ML/AI, backtest, sentiment analysis, data pipeline

#### Go (Gin/Fiber) — **REKOMENDASI untuk API Gateway & Microservices**

**Kelebihan:**
- **Performance terbaik untuk backend umum**: 48K RPS
- Memory terendah: 12MB idle, 47MB under load
- Cold start 11ms (instant)
- Goroutines → concurrency sangat mudah
- Compiled → single binary deployment
- Strong typing, no runtime errors dari type mismatch
- 18MB under 1000 connections (vs Spring Boot 480MB)

**Kekurangan:**
- Ecosystem ML/data sangat terbatas
- Tidak ada library seperti pandas, scikit-learn
- Verbose untuk complex business logic
- GC pauses (12-45μs) — tidak suitable untuk HFT
- Learning curve dari Python ke Go

**Best for:** API gateway, WebSocket hub, order routing, market data service, notification service

#### Rust (Actix/Tokio) — **REKOMENDASI untuk Matching Engine & HFT**

**Kelebihan:**
- **Performance absolut terbaik**: 110K RPS, 12μs execution
- **No GC** → deterministic latency, zero pause time
- Memory safety tanpa garbage collector
- Fearless concurrency (no data races)
- 8M orders/sec (matching engine benchmark)
- 7.4x faster than Go, 10.2x better tail latency
- Zero-cost abstractions

**Kekurangan:**
- **Steepest learning curve** (borrow checker, ownership)
- Development speed paling lambat (14 weeks vs Go 6 weeks untuk MVP)
- Ecosystem finansial terbatas
- Compile time lama
- Sulit hire developer Rust

**Best for:** Matching engine, order book, HFT components, ultra-low latency systems

#### Java (Spring Boot) — **Enterprise Option**

**Kelebihan:**
- Enterprise ecosystem (Spring, Hibernate, Kafka)
- JDBC connection pooling → excellent untuk DB-heavy workloads
- Virtual threads (Java 21) → concurrency improved
- JIT optimization → fast setelah warmup
- Banyak developer Java di Indonesia

**Kekurangan:**
- Memory sangat tinggi: 287MB idle, 512MB under load
- Cold start 4.8 detik (brutal untuk serverless)
- Verbose: 2847 LOC untuk API yang sama
- JVM overhead
- Overkill untuk solo/small team

**Best for:** Enterprise dengan tim besar (>50 engineers), legacy integration, banking-grade systems

#### TypeScript (Node.js) — **Full-Stack Option**

**Kelebihan:**
- Same language dengan frontend → code sharing
- Fast development (4 min setup)
- Large ecosystem (npm)
- Good untuk I/O-bound tasks
- Real-time WebSocket natural

**Kekurangan:**
- Single-threaded → CPU-bound bottleneck
- 18K RPS (2.7x slower than Go)
- Memory 189MB under load
- Type safety optional (bypass dengan `any`)
- Not suitable untuk computation-heavy (ML, backtest)

**Best for:** BFF (Backend for Frontend), WebSocket hub, SSR server, simple API

### 4.3 Framework Backend per Bahasa

| Bahasa | Framework | Performance | DX | Score |
|--------|-----------|-------------|-----|-------|
| **Python** | **FastAPI** | 8K RPS | **Best** (auto docs, Pydantic) | ★★★★★ |
| **Python** | Django | 5K RPS | Good (batteries-included) | ★★★☆☆ |
| **Go** | **Gin** | 48K RPS | Good (minimalist) | ★★★★★ |
| **Go** | Fiber | 50K RPS | Good (Express-like) | ★★★★☆ |
| **Go** | Echo | 45K RPS | Good | ★★★★☆ |
| **Rust** | **Actix-Web** | 110K RPS | Medium (complex) | ★★★★★ |
| **Rust** | Axum | 100K RPS | Good (tokio-based) | ★★★★☆ |
| **Java** | **Spring Boot** | 32K RPS | Good (enterprise) | ★★★★☆ |
| **Java** | Quarkus | 40K RPS | Good (cloud-native) | ★★★☆☆ |
| **TS** | Express | 18K RPS | Good (simple) | ★★★☆☆ |
| **TS** | NestJS | 15K RPS | Good (structured) | ★★★★☆ |

---

## 5. Database & Storage Layer

### 5.1 Database Comparison

| Database | Type | Use Case | Performance | Score |
|----------|------|----------|-------------|-------|
| **PostgreSQL** | Relational | Transactional data, orders, positions | Excellent | ★★★★★ |
| **SQLite** | Relational | Dev/small scale, embedded | Good (WAL mode) | ★★★★☆ |
| **TimescaleDB** | Time-series | OHLCV, tick data (PostgreSQL extension) | **Best** for time-series | ★★★★★ |
| **InfluxDB** | Time-series | Market data, metrics | Very good | ★★★★☆ |
| **Redis** | Key-value | Cache, session, real-time prices | <1ms latency | ★★★★★ |
| **MongoDB** | Document | Read models, flexible schema | Good | ★★★☆☆ |
| **ClickHouse** | Columnar | Analytics, large-scale queries | **Best** for analytics | ★★★★☆ |

### 5.2 Storage Architecture

```
┌──────────────────────────────────────────────────┐
│  HOT DATA (Redis)         │ < 1ms │ Prices, session │
├──────────────────────────────────────────────────┤
│  WARM DATA (PostgreSQL)   │ ~5ms  │ Orders, scores  │
├──────────────────────────────────────────────────┤
│  COLD DATA (Parquet/S3)   │ ~100ms│ Historical OHLCV│
├──────────────────────────────────────────────────┤
│  ARCHIVE (Parquet)        │ ~1s   │ Raw data backup │
└──────────────────────────────────────────────────┘
```

---

## 6. Benchmark Performance

### 6.1 Backend Framework Benchmark (1M Requests)

| Framework | RPS | P50 Latency | P99 Latency | Memory (Idle) | Memory (Load) | Cold Start |
|-----------|-----|-------------|-------------|---------------|---------------|------------|
| **Rust (Actix)** | 110,000 | 2ms | 7ms | 80MB | 250MB | ~5ms |
| **Go (Gin)** | 48,234 | 8ms | 23ms | **12MB** | **47MB** | **11ms** |
| **Java (Spring Boot)** | 31,847 | 12ms | 41ms | 287MB | 512MB | 4,847ms |
| **Node.js (Express)** | 18,456 | 22ms | 89ms | 58MB | 189MB | 312ms |
| **Python (FastAPI)** | 8,923 | 45ms | 156ms | 67MB | 234MB | 487ms |

### 6.2 Matching Engine Benchmark (3M Orders)

| Language | Time | Throughput | vs Rust |
|----------|------|-----------|---------|
| **Rust** | 371ms | **8,078,405 orders/sec** | 1x |
| **Python** | 4.5s | 663,226 orders/sec | 12x slower |
| **Go** | 12.2s | 245,693 orders/sec | 33x slower |
| **TypeScript** | 30.9s | 97,053 orders/sec | 83x slower |

### 6.3 Frontend Bundle Size

| Framework | Hello World | Typical Dashboard | Lighthouse |
|-----------|-------------|-------------------|------------|
| **SvelteKit** | **~15KB** | ~60-100KB | **95-100** |
| **Nuxt 3** | ~60KB | ~180-300KB | 90-95 |
| **Next.js** | ~85KB | ~150-250KB | 85-95 |

### 6.4 Development Speed (Same API)

| Language | Setup Time | Lines of Code | Features/Min |
|----------|-----------|---------------|--------------|
| **Node.js** | 4 min | 1,124 | Fast |
| **Python** | 5 min | **847** | **Fastest** |
| **Go** | 8 min | 1,456 | Medium |
| **Java** | 18 min | 2,847 | Slow |

---

## 7. Rekomendasi Tech Stack

### 7.1 Stack A: "Python-First" (Adopsi dari Existing) — **REKOMENDASI UTAMA**

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND: Next.js 16 + TypeScript + shadcn/ui          │
│  CHARTS:  Lightweight Charts + Recharts + Tremor         │
│  MOBILE:  React Native (opsional)                        │
├─────────────────────────────────────────────────────────┤
│  MIDDLEWARE: Nginx (reverse proxy) + Redis (cache)       │
│  API GATEWAY: FastAPI (existing) atau Go (future)        │
│  WEBSOCKET: FastAPI WebSocket (existing)                 │
│  MESSAGE QUEUE: Redis Pub/Sub (simple) atau Kafka (scale)│
├─────────────────────────────────────────────────────────┤
│  BACKEND: Python + FastAPI (existing trading-system)     │
│  ML/AI: Python + PyTorch + scikit-learn (existing)       │
│  BACKTEST: Python (existing)                             │
│  MATCHING ENGINE: Rust (opsional, jika butuh HFT)        │
├─────────────────────────────────────────────────────────┤
│  DATABASE: SQLite (dev) → PostgreSQL (prod)              │
│  CACHE: Redis                                             │
│  COLD STORAGE: Parquet (existing)                        │
│  TIME-SERIES: TimescaleDB (opsional untuk scale)         │
└─────────────────────────────────────────────────────────┘
```

**Alasan:**
- Codebase `trading-system` v0.1.11 sudah Python + FastAPI + SQLite
- 80+ modul, 750+ tests, 88 API endpoints (86 REST + 2 WebSocket) sudah ada
- Ecosystem ML/data Python tidak tertandingi
- Next.js + TypeScript untuk frontend baru (lebih modern dari existing)
- Adopsi langsung, tidak perlu rewrite

**Trade-off:**
- Performance backend terbatas (8K RPS) — cukup untuk ~100 concurrent users
- Jika butuh scale → tambah Go microservice untuk hot path (order routing)

### 7.2 Stack B: "Polyglot" (Performance + ML) — **REKOMENDASI FUTURE**

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND: Next.js 16 + TypeScript                       │
├─────────────────────────────────────────────────────────┤
│  API GATEWAY: Go (Gin) — 48K RPS, 12MB memory            │
│  WEBSOCKET HUB: Go (gorilla/websocket)                   │
│  MESSAGE QUEUE: Kafka (order events)                     │
├─────────────────────────────────────────────────────────┤
│  DECISION ENGINE: Python + FastAPI (ML, scoring)         │
│  RISK ENGINE: Python (existing)                          │
│  MATCHING ENGINE: Rust (Actix) — 8M orders/sec           │
│  MARKET DATA SERVICE: Go (high throughput)               │
│  SENTIMENT ENGINE: Python (IndoBERT, NLP)                │
├─────────────────────────────────────────────────────────┤
│  DATABASE: PostgreSQL + TimescaleDB                      │
│  CACHE: Redis                                             │
│  COLD STORAGE: Parquet + S3/MinIO                        │
└─────────────────────────────────────────────────────────┘
```

**Alasan:**
- Go untuk hot path (API gateway, WebSocket, market data) → 6x faster
- Python untuk computation (ML, scoring, sentiment) → ecosystem
- Rust untuk matching engine → ultra-low latency
- Best of all worlds

**Trade-off:**
- 3 bahasa → complexity tinggi
- Butuh tim multi-language
- Overkill untuk solo developer

### 7.3 Stack C: "Go-First" (Simpel & Cepat) — **ALTERNATIF**

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND: SvelteKit + TypeScript                        │
├─────────────────────────────────────────────────────────┤
│  MIDDLEWARE: Go (Gin) + Redis + RabbitMQ                 │
├─────────────────────────────────────────────────────────┤
│  BACKEND: Go (Gin/Fiber) untuk semua service             │
│  ML: Python microservice (hanya untuk ML inference)      │
├─────────────────────────────────────────────────────────┤
│  DATABASE: PostgreSQL + Redis                             │
└─────────────────────────────────────────────────────────┘
```

**Alasan:**
- Go single language untuk backend → simpel, fast, low memory
- SvelteKit → bundle terkecil, performance terbaik
- Python hanya untuk ML (separate microservice)

**Trade-off:**
- Harus rewrite semua modul Python ke Go
- Ecosystem ML Go terbatas
- Tidak ada library seperti pandas di Go

---

## 8. Pertimbangan Khusus IDX

### 8.1 Faktor Indonesia

| Faktor | Implikasi Tech Stack |
|--------|---------------------|
| **900+ tickers** | Batch processing, tidak butuh HFT |
| **T+2 settlement** | Tidak real-time critical untuk settlement |
| **10 min Yahoo delay** | Python cukup (tidak butuh sub-second) |
| **IDX scraper** | Python ecosystem (BeautifulSoup, Selenium) |
| **NLP Bahasa Indonesia** | Python (IndoBERT, IndoNLU) — tidak ada di Go/Rust |
| **Solo/small team** | Python = fastest development |
| **Konektivitas broker** | Python library tersedia (Sinarmas, BNI stubs) |
| **Regulasi OJK** | Audit trail → PostgreSQL transactional |

### 8.2 Tidak Butuh HFT

IDX bukan market HFT. Tidak ada sub-microsecond execution requirement. Latency target:
- API response: < 500ms (Python FastAPI cukup)
- Order execution: < 2s (broker API bottleneck, bukan bahasa)
- Data update: < 15 min (Yahoo Finance 10 min delay)
- Score computation: < 5s (batch, tidak real-time)

> **Kesimpulan:** Python FastAPI **cukup** untuk IDX. Tidak perlu Go/Rust kecuali untuk scale-up.

---

## 9. Adopsi dari Proyek Existing

### 9.1 Yang Bisa Diadopsi Langsung

| Komponen | Bahasa | Status | Adopsi |
|----------|--------|--------|--------|
| **Data acquisition** (Yahoo Finance) | Python | Production-ready | ✅ Copy langsung |
| **Storage** (SQLite + Parquet) | Python | Production-ready | ✅ Copy langsung |
| **Decision Engine** | Python | Production-ready | ✅ Copy langsung |
| **Risk Engine** | Python | Production-ready | ✅ Copy langsung |
| **Backtest Engine** | Python | Production-ready | ✅ Copy langsung |
| **Sentiment Engine** | Python | Production-ready | ✅ Copy langsung |
| **AI/ML Engine** | Python | Production-ready | ✅ Copy langsung |
| **CLI** | Python | Production-ready | ✅ Copy langsung |
| **API (FastAPI)** | Python | 88 endpoints | ✅ Copy + extend |
| **Frontend (Next.js)** | TypeScript | Data Inspection only | ⚠️ Perlu rebuild |

### 9.2 Yang Perlu Di-rewrite / Baru

| Komponen | Dari | Ke | Alasan |
|----------|------|-----|--------|
| **Frontend dashboard** | Next.js (minimal) | Next.js + shadcn/ui + Tremor | UI baru lengkap |
| **Mobile app** | None | React Native | Baru |
| **API Gateway** | FastAPI (monolith) | Go gateway (opsional) | Performance |
| **Real-time WebSocket** | FastAPI WS | Go WS hub (opsional) | Concurrent connections |
| **Database** | SQLite | PostgreSQL | Concurrent writes, scale |

### 9.3 Migration Path

```
Phase 1 (MVP): Adopsi langsung
  └─ Python FastAPI + SQLite + Next.js frontend baru

Phase 2 (Scale): Tambah Go middleware
  └─ Go API gateway + Redis cache + PostgreSQL

Phase 3 (Performance): Rust untuk hot path
  └─ Rust matching engine (jika butuh)
```

---

## 10. Checklist Implementasi

### Frontend
- [ ] TypeScript sebagai bahasa utama
- [ ] Next.js 16 sebagai framework (atau SvelteKit jika performance priority)
- [ ] shadcn/ui + Tremor untuk dashboard components
- [ ] Lightweight Charts untuk candlestick/OHLCV
- [ ] TanStack Table untuk portfolio grid
- [ ] WebSocket untuk real-time data
- [ ] SWR/React Query untuk data fetching + caching
- [ ] React Native untuk mobile (opsional, phase 2)

### Middleware
- [ ] Nginx sebagai reverse proxy
- [ ] Redis untuk caching (prices, session, hot data)
- [ ] gRPC untuk service-to-service (jika microservices)
- [ ] WebSocket hub untuk real-time push
- [ ] Kafka/RabbitMQ untuk event-driven (jika scale)
- [ ] JWT + RBAC untuk auth

### Backend
- [ ] Python + FastAPI untuk core engine (adopsi existing)
- [ ] Go untuk API gateway (opsional, phase 2)
- [ ] Rust untuk matching engine (opsional, phase 3)
- [ ] Pydantic untuk request/response validation
- [ ] asyncpg untuk PostgreSQL async access
- [ ] Gunicorn + Uvicorn workers untuk production

### Database
- [ ] SQLite untuk development (existing)
- [ ] PostgreSQL untuk production
- [ ] TimescaleDB untuk time-series (opsional)
- [ ] Redis untuk cache
- [ ] Parquet untuk cold storage (existing)

### Adopsi
- [ ] Copy modul Python dari `/home/petrick/projects/global`
- [ ] Rebuild frontend dengan Next.js + TypeScript
- [ ] Migrate SQLite → PostgreSQL (jika production)
- [ ] Add Redis cache layer
- [ ] Add Nginx reverse proxy
- [ ] Docker containerization

---

## Referensi

1. Trading App Development Guide 2026: https://www.fintegrationfs.com/post/how-to-build-a-trading-application-the-complete-developer-guide-2025
2. Tech Stack for Trading Platforms: https://fintechzoom.com/trading/tech-stack-for-trading-platforms/
3. Top Stock Trading App Frameworks 2026: https://medium.com/@suhani1/stock-trading-app-development-today-frameworks-that-ensure-speed-security-f8164a9686ca
4. Programming Languages for Investment Platforms: https://iemlabs.com/blogs/which-programming-languages-do-investment-platform-developers-prefer/
5. Rust vs Go for HFT: https://dev.to/speed_engineer/building-real-time-trading-systems-why-we-abandoned-go-for-rust-21km
6. Rust vs C++ vs Python vs Go vs TS for HFT: https://www.linkedin.com/pulse/comparing-rust-c-python-java-go-typescriptnodejs-hft-trading-souza-nxlkf
7. Crypto Matching Engine Benchmark: https://github.com/silencebeat/crypto_matching_engine_comparison
8. Python vs Rust for Backtesting: https://www.quantlabsnet.com/post/python-vs-rust-for-quantitative-backtesting-engines-a-deep-dive-into-latency-memory-and-compilat
9. Web Framework Benchmark 100M Requests: https://www.xugj520.cn/en/archives/web-framework-benchmark-100m-requests.html
10. FastAPI vs Gin vs Spring Boot 2026: https://medium.com/@rameshkannanyt0078/fastapi-vs-gin-vs-spring-boot-2026-1m-request-benchmarks-thatll-change-your-stack-choice-d1ceb49ef1ee
11. Next.js vs Nuxt vs SvelteKit 2026: https://trybuildpilot.com/675-nuxt-vs-next-vs-sveltekit-2026
12. Svelte vs React for Fintech: https://trio.dev/svelte-vs-react/
13. Frontend Frameworks for Banks 2026: https://www.sencha.com/blog/front-end-frameworks-for-banks-and-financial-institutions-a-2026-guide/
14. gRPC Stock Trading Platform: https://github.com/Ayush2102/grpc-stock-trading-platform
15. Glyph Trading Platform Architecture: https://github.com/yash-gadgil/glyph/blob/main/docs/architecture.md
16. `pustaka/11-knowledge-transfer-aplikasi.md` — Pola arsitektur dari proyek nyata
17. `pustaka/27-deployment-devops-trading.md` — Deployment & DevOps
18. `pustaka/28-api-design-integration-patterns.md` — API design patterns
19. `pustaka/32-ui-ux-design-trading-app.md` — UI/UX design
20. `pustaka/34-performance-engineering-optimization.md` — Performance optimization

---

> **Kesimpulan:** Untuk aplikasi pasar modal IDX/Indonesia, **Python + FastAPI** untuk backend (adopsi langsung dari existing), **Next.js + TypeScript** untuk frontend (rebuild), **Redis** untuk cache, **PostgreSQL** untuk production database. Tidak perlu Go/Rust kecuali untuk scale-up. Ecosystem ML Python dan library finansial tidak tertandingi oleh bahasa lain. Solo developer atau small team → Python is the pragmatic choice.
