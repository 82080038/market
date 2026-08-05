# Capacity Planning & Load/Stress Testing

> **Dokumen 55** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Kapan scale dari 928 ke 2000+ tickers, kapan butuh GPU upgrade, load test pipeline, stress test multi-failure scenario.
>
> **Konteks:** Dokumen 34 bahas performance engineering. Dokumen 27 bahas deployment. Tapi belum ada doc tentang capacity planning: berapa maksimum ticker sebelum pipeline OOM? Kapan VRAM tidak cukup? Apa yang terjadi jika semua data source down bersamaan?

---

## Daftar Isi

1. [Current Capacity Baseline](#1-current-capacity-baseline)
2. [Capacity Limits per Komponen](#2-capacity-limits-per-komponen)
3. [Scale-Up Triggers](#3-scale-up-triggers)
4. [Load Testing](#4-load-testing)
5. [Stress Testing](#5-stress-testing)
6. [Capacity Forecast](#6-capacity-forecast)
7. [Upgrade Roadmap](#7-upgrade-roadmap)

---

## 1. Current Capacity Baseline

### 1.1 Current System Specs

| Komponen | Spec | Utilization (928 tickers) | Headroom |
|----------|------|--------------------------|----------|
| **CPU** | (varies) | ~60% during pipeline | 40% |
| **RAM** | (varies) | ~4GB during pipeline | (varies) |
| **GPU 0** | GTX 1050 Ti 4GB | Used by Xorg | N/A |
| **GPU 1** | GTX 1050 Ti 4GB | ~70% during LSTM batch (64) | 30% |
| **Disk** | SQLite ~460MB + Parquet ~50GB | < 50% disk | 50%+ |
| **Network** | 100 Mbps | ~5 Mbps during fetch | 95% |

### 1.2 Pipeline Timing (928 tickers)

| Task | Time | Bottleneck | Scale Limit |
|------|------|------------|-------------|
| T-001 EOD Fetch | ~60s | Network (yfinance rate limit) | ~2000 tickers (120s) |
| T-002 Foreign Flow | ~10 min | Network (idx.co.id rate 0.3s) | ~2000 tickers (20 min) |
| T-010 Technical | ~2 min | CPU (pandas vectorization) | ~2000 tickers (4 min) |
| T-014 Relationship | ~5 min | CPU (928×928 matrix) | ~2000 tickers (20 min — O(n²)) |
| T-015 Sentiment | ~5 min | GPU (IndoBERT) + I/O | ~2000 tickers (10 min) |
| T-019 Full Pipeline | ~5 min | CPU (orchestration) | ~2000 tickers (10 min) |
| T-020 LSTM Inference | ~20 min | GPU (batch 64, cuda:1) | ~2000 tickers (40 min) |
| T-025 LSTM Retrain | ~4-8 jam | GPU (928 models) | ~2000 tickers (8-16 jam) |
| **Total Daily** | **~45 min** | — | **~90 min at 2000** |

---

## 2. Capacity Limits per Komponen

### 2.1 GPU VRAM (4GB GTX 1050 Ti)

| Batch Size | Hidden Dim | VRAM Used | Status |
|------------|------------|-----------|--------|
| 32 | 128 | ~1.5 GB | Safe |
| 64 | 256 | ~2.8 GB | Safe (current) |
| 128 | 256 | ~4.2 GB | **OOM** |
| 64 | 512 | ~5.1 GB | **OOM** |

**Limit:** batch_size ≤ 64, hidden_dim ≤ 256 untuk 4GB VRAM.

### 2.2 CPU — Relationship Matrix (O(n²))

| Tickers | Matrix Size | Memory | Compute Time |
|---------|-------------|--------|--------------|
| 928 | 928×928 = 861K pairs | ~200 MB | ~5 min |
| 2000 | 2000×2000 = 4M pairs | ~800 MB | ~20 min |
| 5000 | 5000×5000 = 25M pairs | ~5 GB | ~2 jam |

**Limit:** ~3000 tickers sebelum relationship matrix menjadi bottleneck.

### 2.3 SQLite

| Metric | Current | Limit | Action Needed |
|--------|---------|-------|---------------|
| DB size | ~460 MB | ~10 GB practical | None (plenty of room) |
| ohlcv rows | 2.9M | ~50M before query slowdown | None |
| Concurrent reads | 1 (single user) | WAL supports concurrent read | None |
| Write throughput | ~1000 rows/s | ~5000 rows/s | None |

**Limit:** SQLite cukup hingga ~5000 tickers atau ~50M ohlcv rows.

### 2.4 Network

| Task | Bandwidth | Limit |
|------|-----------|-------|
| yfinance fetch | ~5 Mbps | yfinance rate limit (1 req/s) |
| idx.co.id scrape | ~2 Mbps | idx.co.id rate limit (0.3 req/s) |
| API response | ~10 Mbps | localhost, no limit |

**Limit:** yfinance rate limit (1 req/s) → 928 tickers = ~15 min. 2000 tickers = ~33 min.

---

## 3. Scale-Up Triggers

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Pipeline time > 90 min | 2 consecutive days | Optimize or scale |
| GPU VRAM > 90% | During LSTM batch | Reduce batch_size or upgrade GPU |
| DB size > 5 GB | Monthly check | Archive old data |
| Disk usage > 80% | Monitoring alert | Clean old backups |
| Relationship matrix > 20 min | Per run | Sample subset or use GPU |
| LSTM retrain > 12 jam | Weekly | Upgrade GPU or parallelize |
| API response > 2s | P95 latency | Add caching or scale API |

---

## 4. Load Testing

### 4.1 Load Test Scenarios

| Scenario | What We Test | Method | Pass Criteria |
|----------|-------------|--------|---------------|
| **Full pipeline 928** | Normal load | `daily_runner.py` | Complete < 60 min |
| **Full pipeline 2000** | Future load | Simulate 2000 tickers (duplicate) | Complete < 120 min |
| **API burst 100 req/s** | API capacity | `locust` or `ab` | P95 < 500ms |
| **LSTM batch max** | GPU capacity | batch_size=64, 928 tickers | No OOM |
| **DB write burst** | DB capacity | 10K INSERT/s | No error |

### 4.2 Load Test Script

```python
# tests/load/test_pipeline_capacity.py

import time
import pytest

@pytest.mark.slow
def test_full_pipeline_928_tickers():
    """Load test: full pipeline untuk 928 tickers."""
    tickers = get_all_active_equity_tickers()
    assert len(tickers) == 928

    start = time.time()
    pipeline.run_full_pipeline(tickers)
    elapsed = time.time() - start

    assert elapsed < 3600  # < 60 min
    # Verify all scores computed
    scores = get_today_scores()
    assert len(scores) >= 900  # > 97% coverage

@pytest.mark.slow
def test_api_burst():
    """Load test: 100 concurrent API requests."""
    import concurrent.futures
    import requests

    def make_request():
        return requests.get(
            "http://localhost:8000/api/recommend/BBCA.JK",
            headers={"X-API-Key": "test"}
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(make_request) for _ in range(100)]
        results = [f.result() for f in futures]

    success = sum(1 for r in results if r.status_code == 200)
    assert success >= 95  # > 95% success rate
```

---

## 5. Stress Testing

### 5.1 Stress Test Scenarios

| Scenario | Simulasi | Expected Behavior | Pass Criteria |
|----------|----------|-------------------|---------------|
| **Yahoo + IDX down** | Block both APIs | Skip fetch, use stale data, alert | No crash, graceful degradation |
| **GPU failure during LSTM** | Kill CUDA context | Fallback to CPU, continue | Pipeline completes (slower) |
| **DB corrupt during pipeline** | Corrupt WAL file | Detect, stop, alert | No data loss beyond RPO |
| **Disk full during pipeline** | Fill disk to 99% | Detect, clean, alert | No partial writes |
| **OOM during relationship matrix** | Reduce available RAM | Catch OOM, reduce matrix size | Partial results saved |
| **Network outage mid-fetch** | Disconnect network | Retry, then skip, alert | Partial data saved |

### 5.2 Stress Test: Multi-Failure

```python
# tests/stress/test_multi_failure.py

@pytest.mark.stress
def test_yahoo_and_gpu_fail_simultaneously():
    """
    Worst case: Yahoo Finance down + GPU fail on same day.
    Expected: Pipeline runs with CPU + stale data, alert sent.
    """
    # Mock Yahoo Finance failure
    mock_yfinance_down()

    # Mock GPU failure
    mock_cuda_unavailable()

    # Run pipeline
    results = pipeline.run_full_pipeline(get_all_tickers())

    # Verify graceful degradation
    assert results.status == "degraded"
    assert results.using_stale_data == True
    assert results.using_cpu_fallback == True
    assert results.alert_sent == True
    assert results.scores_computed > 0  # Still produced some scores
```

---

## 6. Capacity Forecast

### 6.1 Growth Projections

| Metric | Current (2026) | 1 Year (2027) | 2 Year (2028) | Limit |
|--------|---------------|---------------|---------------|-------|
| Active tickers | 928 | 928 (IDX stable) | ~1000 (IPO) | ~3000 (CPU limit) |
| OHLCV rows/year | ~230K | ~230K | ~250K | ~50M (SQLite) |
| DB size | 460 MB | ~600 MB | ~750 MB | ~10 GB |
| Parquet archive | 50 GB | ~70 GB | ~90 GB | Disk dependent |
| LSTM models | 928 files | 928 files | ~1000 files | Disk dependent |
| Pipeline time | 45 min | 45 min | ~50 min | < 90 min target |

### 6.2 When to Upgrade

| Component | Trigger | Timeline | Estimated Cost |
|-----------|---------|----------|----------------|
| **GPU** | LSTM retrain > 12 jam OR VRAM OOM | 1-2 years | Rp 5-15M (RTX 3060/4060) |
| **CPU** | Pipeline > 90 min | 2-3 years | Rp 3-10M |
| **RAM** | OOM during relationship matrix | 1-2 years | Rp 1-3M (32GB) |
| **Disk** | Disk > 80% | 1-2 years | Rp 1-2M (1TB SSD) |
| **SQLite → PostgreSQL** | > 3000 tickers OR concurrent users | 3+ years | Migration effort |

---

## 7. Upgrade Roadmap

### 7.1 Phase 1: GPU Upgrade (Priority: High)

```
Current: 2x GTX 1050 Ti (4GB each, Pascal, no Tensor Cores)
Target:  1x RTX 4060 (8GB VRAM, Ada Lovelace, Tensor Cores)

Benefits:
- 2x VRAM (8GB vs 4GB) → batch_size 128, hidden_dim 512
- Tensor Cores → FP16 acceleration for LSTM
- 3-5x faster LSTM training/inference
- Single GPU simplifies code (no cuda:0/cuda:1 split)

Impact:
- LSTM retrain: 4-8 jam → 1-2 jam
- LSTM inference: 20 min → 5-10 min
- Can handle 2000+ tickers comfortably
```

### 7.2 Phase 2: RAM Upgrade (Priority: Medium)

```
Current: (varies, assume 16GB)
Target:  32GB or 64GB

Benefits:
- Relationship matrix 2000×2000 without OOM
- Larger pandas DataFrames in memory
- More room for caching

Impact:
- Relationship analysis: 20 min → 10 min (more memory for vectorization)
```

### 7.3 Phase 3: SQLite → PostgreSQL (Priority: Low, 3+ years)

```
Trigger: > 3000 tickers OR > 5 concurrent users

Benefits:
- Concurrent writes (SQLite: single writer)
- Better query optimization
- Built-in replication
- Larger dataset handling

Migration:
- Alembic migration to PostgreSQL schema
- Data migration script (SQLite → PostgreSQL)
- Update all DB connection strings
- Test all queries (some SQLite-specific syntax may need adjustment)
```

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **27** (Deployment/DevOps) | Infrastructure deployment |
| **34** (Performance Engineering) | Optimization techniques complement capacity planning |
| **47** (Operational Contract) | SLA per task feeds capacity analysis |
| **48** (DR/BCP) | Stress test scenarios overlap with DR scenarios |

---

## Referensi

1. `src/trading_system/ai_learning/deep_learning.py` — GPU/CUDA usage (PyTorch, cuda:1)
2. `src/trading_system/data/storage.py` — SQLite database size monitoring
3. `src/trading_system/analysis/relationship.py` — O(n²) relationship matrix
4. `pustaka/27-deployment-devops-trading.md` — Infrastructure deployment
5. `pustaka/34-performance-engineering-optimization.md` — Performance optimization
6. `pustaka/47-operational-contract-runbook.md` — SLA per task
7. `pustaka/48-disaster-recovery-business-continuity.md` — Stress test scenarios

---

> **Catatan:** Capacity planning adalah tentang antisipasi, bukan reaksi. "Plan for 2x, build for 3x, worry at 4x." Sistem trading yang lambat = opportunity lost — setiap menit pipeline lebih lama adalah menit di mana decisions tidak up-to-date.
