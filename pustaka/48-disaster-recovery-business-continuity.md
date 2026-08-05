# Disaster Recovery & Business Continuity Plan (DR/BCP)

> **Dokumen 48** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Rencana pemulihan bencana dan kontinuitas bisnis untuk setiap komponen sistem trading — RTO/RPO, failover strategy, recovery procedures, DR drill schedule.
>
> **Konteks:** Dokumen 27 bahas deployment & DevOps. Dokumen 47 punya backup task (T-008) dan escalation. Tapi belum ada comprehensive DR plan yang mendefinisikan: apa yang dilakukan saat DB corrupt, GPU fail, API down, data source down, atau multiple failures bersamaan. Dokumen ini mengisi gap.

---

## Daftar Isi

1. [Konsep DR/BCP](#1-konsep-drbcp)
2. [RTO/RPO per Komponen](#2-rtorpo-per-komponen)
3. [Failure Scenarios & Recovery Procedures](#3-failure-scenarios--recovery-procedures)
4. [Backup Strategy](#4-backup-strategy)
5. [Failover & High Availability](#5-failover--high-availability)
6. [DR Drill Schedule](#6-dr-drill-schedule)
7. [Recovery Checklist](#7-recovery-checklist)
8. [Communication Plan](#8-communication-plan)

---

## 1. Konsep DR/BCP

### 1.1 Definisi

| Istilah | Arti |
|---------|------|
| **RTO** (Recovery Time Objective) | Maksimum waktu yang diizinkan dari failure ke recovery |
| **RPO** (Recovery Point Objective) | Maksimum data loss yang diizinkan (diukur dalam waktu) |
| **DR** (Disaster Recovery) | Proses pemulihan sistem setelah failure/bencana |
| **BCP** (Business Continuity Plan) | Rencana agar bisnis tetap berjalan selama disaster |
| **Failover** | Otomatis beralih ke sistem cadangan saat primary gagal |
| **Hot Standby** | Sistem cadangan yang selalu running, siap takeover segera |
| **Cold Standby** | Sistem cadangan yang tidak running, perlu start manual |
| **DR Drill** | Latihan pemulihan untuk memastikan DR plan bekerja |

### 1.2 Prinsip DR untuk Trading System

1. **Trading system tidak boleh down > 1 hari bursa** — RTO maksimal 4 jam untuk komponen critical
2. **Data loss > 1 hari tidak acceptable** — RPO maksimal 1 jam untuk OHLCV
3. **Backup tanpa drill = ilusi** — DR drill wajib minimal quarterly
4. **Recovery procedure harus executable by anyone** — tidak tergantung 1 orang
5. **Priority: data integrity > availability > performance** — lebih baik down sebentar daripada data corrupt

---

## 2. RTO/RPO per Komponen

| Komponen | RTO | RPO | Priority | Justifikasi |
|----------|-----|-----|----------|-------------|
| **SQLite DB** | 30 menit | 1 jam (backup interval) | SEV-0 | Single source of truth, semua engine bergantung |
| **API Server** | 5 menit | 0 (stateless) | SEV-1 | User interface, restart cepat |
| **Frontend** | 5 menit | 0 (stateless) | SEV-2 | Static, redeploy dari git |
| **GPU (cuda:1)** | 2 jam | N/A | SEV-1 | LSTM inference/retrain, fallback ke CPU |
| **Scheduler (daily_runner)** | 15 menit | 0 (stateless) | SEV-1 | Pipeline orchestration |
| **Parquet Archive** | 4 jam | 24 jam (rsync interval) | SEV-2 | Redundant storage, bukan primary |
| **Telegram Bot** | 15 menit | 0 | SEV-3 | Alerting only, non-critical |
| **Yahoo Finance API** | N/A (external) | N/A | SEV-1 | Tidak bisa di-failover, tunggu recovery |
| **idx.co.id Scraper** | N/A (external) | N/A | SEV-2 | Tidak bisa di-failover, skip hari itu |

---

## 3. Failure Scenarios & Recovery Procedures

### 3.1 Scenario: SQLite DB Corrupt

```
SEVERITY: SEV-0
RTO: 30 menit
PROBABILITY: Low (WAL mode, robust)
```

**Detection:**
- API returns 500 on DB queries
- `sqlite3.OperationalError: database disk image is malformed`
- Monitoring (T-044) alerts: "DB unresponsive"

**Recovery Steps:**
1. Stop semua services (API, scheduler, daily_runner)
   ```bash
   # Kill API server
   pkill -f "uvicorn trading_system"
   # Kill scheduler
   pkill -f "daily_runner"
   ```
2. Assess corruption level:
   ```bash
   .venv/bin/python -c "
   import sqlite3
   conn = sqlite3.connect('data/trading_system.db')
   try:
       conn.execute('SELECT COUNT(*) FROM ohlcv').fetchone()
       print('DB OK')
   except Exception as e:
       print(f'DB CORRUPT: {e}')
   "
   ```
3. If corrupt: restore from latest backup
   ```bash
   # Find latest backup
   ls -la backups/trading_system_*.db | tail -1
   # Restore
   cp data/trading_system.db data/trading_system.db.corrupt.$(date +%Y%m%d)
   cp backups/trading_system_$(date +%Y%m%d).db data/trading_system.db
   ```
4. Verify integrity:
   ```bash
   sqlite3 data/trading_system.db "PRAGMA integrity_check;"
   sqlite3 data/trading_system.db "SELECT COUNT(*) FROM ohlcv;"
   ```
5. Restart services:
   ```bash
   .venv/bin/uvicorn trading_system.api.app:app --port 8000 &
   ```
6. Re-fetch today's data if backup was from yesterday:
   ```bash
   .venv/bin/trading-system fetch --all
   ```
7. Post-recovery: audit_log entry, Telegram alert to user

**Data Loss (RPO):** Maksimal 1 jam (backup runs at 01:00 WIB daily, plus WAL checkpoint)

---

### 3.2 Scenario: GPU Failure (cuda:1)

```
SEVERITY: SEV-1
RTO: 2 jam (fallback ke CPU)
PROBABILITY: Medium (GTX 1050 Ti, aging hardware)
```

**Detection:**
- LSTM inference throws `torch.cuda.CUDAError`
- `nvidia-smi` returns error or no GPU detected
- Monitoring (T-044) alerts: "GPU unavailable"

**Recovery Steps:**
1. Verify GPU status:
   ```bash
   nvidia-smi
   # If GPU 1 not visible, check driver
   dmesg | grep -i nvidia | tail -20
   ```
2. If driver issue:
   ```bash
   sudo modprobe nvidia
   # Or restart driver
   sudo systemctl restart nvidia-driver
   ```
3. If hardware failure: fallback to CPU
   ```bash
   export CUDA_VISIBLE_DEVICES=""  # Force CPU mode
   # Or use GPU 0 (shared with display)
   export CUDA_VISIBLE_DEVICES=0
   ```
4. Update config: set `device='cpu'` or `device='cuda:0'` in deep_learning.py
5. Re-run failed LSTM tasks with reduced batch_size (CPU: batch_size=8)
6. Post-recovery: log, alert user about degraded performance

**Impact:** LSTM inference 5-10x slower on CPU. Daily pipeline SLA increases from 20 min to ~60 min.

---

### 3.3 Scenario: API Server Down

```
SEVERITY: SEV-1
RTO: 5 menit
PROBABILITY: Medium (OOM, unhandled exception)
```

**Detection:**
- Frontend shows "Backend unavailable"
- `curl http://localhost:8000/api/health` returns connection refused
- Monitoring (T-044) alerts: "API unresponsive"

**Recovery Steps:**
1. Check if process alive:
   ```bash
   ps aux | grep uvicorn
   ```
2. If dead: check logs for crash reason
   ```bash
   tail -100 /tmp/uvicorn.log
   ```
3. If OOM: reduce batch sizes, clear caches
   ```bash
   # Clear Python cache
   find . -type d -name __pycache__ -exec rm -rf {} +
   ```
4. Restart:
   ```bash
   .venv/bin/uvicorn trading_system.api.app:app --port 8000 &
   ```
5. Verify: `curl http://localhost:8000/api/health`
6. Post-recovery: audit_log, alert

---

### 3.4 Scenario: Yahoo Finance API Down

```
SEVERITY: SEV-1
RTO: N/A (external, wait for recovery)
PROBABILITY: Medium (rate limit, maintenance)
```

**Detection:**
- T-001 (EOD fetch) fails for all tickers
- `yfinance.download()` returns empty DataFrame
- source_health: yahoo_finance → "error"

**Recovery Steps:**
1. Verify: check Yahoo Finance status
   ```bash
   curl -s "https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK" | head
   ```
2. If API down: skip T-001, alert user
3. Fallback: use cached/stale data (mark as stale in scores)
4. If partial: retry failed tickers every 30 min (max 3 retries)
5. If still down at 18:00 WIB: skip pipeline (T-019), use yesterday's scores
6. Post-recovery (next day): re-fetch missing data, re-run pipeline

**Impact:** No new analysis for 1 day. Scores marked as "stale" in API response.

---

### 3.5 Scenario: idx.co.id Blocked / Cloudflare

```
SEVERITY: SEV-2
RTO: N/A (external)
PROBABILITY: High (anti-scraping measures)
```

**Detection:**
- T-002/T-003 scrape returns 403 or Cloudflare challenge
- foreign_flow/broker_flow row count = 0 for today

**Recovery Steps:**
1. Update cloudscraper library:
   ```bash
   .venv/bin/pip install --upgrade cloudscraper
   ```
2. If still blocked: use alternative data source
   - Manual: user checks idx.co.id manually
   - Alternative: broker API (if available)
3. Skip foreign/broker flow for today, mark sentiment as "partial"
4. Post-recovery: re-scrape when available

---

### 3.6 Scenario: Disk Full

```
SEVERITY: SEV-0
RTO: 30 menit
PROBABILITY: Low (monitoring should catch early)
```

**Detection:**
- DB writes fail: `sqlite3.OperationalError: disk I/O error`
- Monitoring alerts: "Disk usage > 90%"

**Recovery Steps:**
1. Check disk usage:
   ```bash
   df -h
   du -sh data/ backups/ models/ logs/
   ```
2. Clean old backups (> 30 days):
   ```bash
   find backups/ -name "trading_system_*.db" -mtime +30 -delete
   ```
3. Clean old logs:
   ```bash
   find logs/ -name "*.log" -mtime +7 -delete
   ```
4. Vacuum SQLite:
   ```bash
   sqlite3 data/trading_system.db "VACUUM;"
   ```
5. Clean old Parquet temp files:
   ```bash
   find /media/petrick/Parquet/trading_data/raw/ -name "*.tmp" -delete
   ```
6. Post-recovery: set up disk space alert at 80% threshold

---

### 3.7 Scenario: Multiple Failures (Worst Case)

```
SEVERITY: SEV-0
RTO: 4 jam
PROBABILITY: Very Low
```

**Scenario:** Yahoo down + DB corrupt + GPU fail on same day

**Recovery Priority:**
1. **DB first** (30 min) — restore from backup
2. **API second** (5 min) — restart with restored DB
3. **GPU third** (2 jam) — fallback to CPU
4. **Data last** — wait for Yahoo recovery, use stale data

**Communication:**
- Telegram alert: "Multiple failures detected. Recovery in progress. Estimated RTO: 4 hours."
- Update every 30 min with progress

---

## 4. Backup Strategy

### 4.1 Backup Tiers

| Tier | Komponen | Frequency | Retention | Storage | Verification |
|------|----------|-----------|-----------|---------|--------------|
| **T1** | SQLite DB | Daily 01:00 WIB | 30 days | `backups/` local | Auto: open + SELECT COUNT |
| **T2** | Parquet Archive | Daily 01:00 WIB | Indefinite | `/media/petrick/Parquet/` | Auto: file count check |
| **T3** | LSTM Models | Weekly (after retrain) | 4 weeks | `models/lstm/` | Auto: load + inference test |
| **T4** | Config (.env) | On change | Indefinite | Git (encrypted) | Manual: diff |
| **T5** | Code | On commit | Indefinite | Git | Auto: CI/CD |
| **T6** | Audit Log | Monthly export | 1 year | `backups/audit_*.csv` | Auto: row count |

### 4.2 Backup Verification

```python
# scripts/verify_backup.py
import sqlite3
import os
from datetime import datetime, timedelta

def verify_latest_backup():
    today = datetime.now().strftime("%Y%m%d")
    backup_path = f"backups/trading_system_{today}.db"

    if not os.path.exists(backup_path):
        alert(f"Backup missing: {backup_path}")
        return False

    try:
        conn = sqlite3.connect(backup_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for table_name, in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            print(f"  {table_name}: {count} rows")

        # Compare with production
        prod_conn = sqlite3.connect("data/trading_system.db")
        for table_name, in tables:
            prod_count = prod_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            backup_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            if abs(prod_count - backup_count) > 100:
                alert(f"Mismatch {table_name}: prod={prod_count} backup={backup_count}")

        conn.close()
        prod_conn.close()
        return True
    except Exception as e:
        alert(f"Backup corrupt: {e}")
        return False
```

### 4.3 3-2-1 Rule

- **3** copies of data (production + local backup + Parquet archive)
- **2** different media (SSD local + external Parquet drive)
- **1** copy offsite (future: cloud backup to S3/GCS)

---

## 5. Failover & High Availability

### 5.1 Current Architecture (Single Node)

```
┌─────────────────────────────────────┐
│         Single Node (localhost)      │
│  ┌──────┐ ┌──────┐ ┌──────────────┐ │
│  │ API  │ │ Sched│ │  SQLite DB   │ │
│  │:8000 │ │ uler │ │  (WAL mode)  │ │
│  └──────┘ └──────┘ └──────────────┘ │
│  ┌──────────────────┐ ┌───────────┐ │
│  │  GPU (cuda:1)    │ │ Frontend  │ │
│  │  GTX 1050 Ti     │ │ :3000     │ │
│  └──────────────────┘ └───────────┘ │
└─────────────────────────────────────┘
```

### 5.2 Failover Matrix

| Component | Primary | Failover | Auto-Failover? | Recovery Action |
|-----------|---------|----------|----------------|-----------------|
| API | uvicorn :8000 | Restart uvicorn | Yes (systemd) | Auto-restart on crash |
| DB | SQLite local | Backup restore | No (manual) | Restore from backup |
| GPU | cuda:1 | cuda:0 or CPU | No (manual) | Set env var |
| Scheduler | daily_runner | Manual run | No (manual) | Run missed tasks |
| Frontend | next dev :3000 | Restart next | Yes (systemd) | Auto-restart |
| Data source | Yahoo Finance | Stale data | Yes (code) | Use last known |

### 5.3 Future: Hot Standby Architecture

```
┌──────────────┐     ┌──────────────┐
│  Primary Node │     │  Standby Node │
│  (active)     │     │  (hot)        │
│  ┌─────────┐  │     │  ┌─────────┐  │
│  │ API     │  │     │  │ API     │  │
│  │ Scheduler│  │     │  │ (idle)  │  │
│  │ GPU     │  │     │  │ GPU     │  │
│  └─────────┘  │     │  └─────────┘  │
│       │       │     │       │       │
│       └───────┴─────┴───────┘       │
│           SQLite (replicated)        │
│           via Litestream             │
└──────────────────────────────────────┘
```

**Litestream** (future): Real-time SQLite replication to S3, enables sub-second RPO and fast failover.

---

## 6. DR Drill Schedule

### 6.1 Quarterly DR Drill

| Quarter | Scenario | Duration | Participants | Success Criteria |
|---------|----------|----------|--------------|------------------|
| Q1 | DB corrupt → restore | 30 min | Solo dev | DB restored, API up, data verified |
| Q2 | GPU fail → CPU fallback | 2 jam | Solo dev | LSTM runs on CPU, pipeline completes |
| Q3 | API crash → restart | 5 min | Solo dev | API up, all endpoints respond |
| Q4 | Full disaster (multi-fail) | 4 jam | Solo dev | All services recovered in order |

### 6.2 DR Drill Procedure

1. **Announce**: Log drill start in audit_log
2. **Simulate**: Stop service / corrupt test DB
3. **Execute**: Follow recovery procedure from §3
4. **Measure**: Record actual RTO vs target
5. **Verify**: All services functional, data integrity confirmed
6. **Document**: Write drill report (what worked, what didn't)
7. **Improve**: Update DR plan based on findings

### 6.3 DR Drill Report Template

```markdown
## DR Drill Report — [Date]

**Scenario:** [e.g., DB Corrupt]
**Target RTO:** 30 min
**Actual RTO:** [time]
**Target RPO:** 1 hour
**Actual RPO:** [data loss measured]

### What Worked
- [item]

### What Didn't Work
- [item]

### Action Items
- [ ] [action] — Owner: [name] — Due: [date]

### DR Plan Updates
- [change to procedure]
```

---

## 7. Recovery Checklist

### 7.1 Pre-Recovery (Detection & Assessment)

- [ ] Alert received (Telegram / monitoring)
- [ ] Severity assessed (SEV-0/1/2/3)
- [ ] Affected components identified
- [ ] Decision: is this a real disaster or transient error?

### 7.2 Recovery Execution

- [ ] Stop affected services (prevent further damage)
- [ ] Follow recovery procedure for specific scenario
- [ ] Verify data integrity post-recovery
- [ ] Restart services
- [ ] Verify all services functional

### 7.3 Post-Recovery

- [ ] Audit log entry: "Recovery completed: [scenario], RTO=[time]"
- [ ] Telegram alert: "System recovered. [summary]"
- [ ] Re-run missed tasks (if data gap)
- [ ] Schedule post-incident review (see doc 49)
- [ ] Update DR plan if procedure was inadequate

---

## 8. Communication Plan

### 8.1 Internal Communication

| Severity | Channel | Template | Frequency |
|----------|---------|----------|-----------|
| SEV-0 | Telegram | "[SEV-0] {component} down. Recovery started. ETA: {RTO}." | Every 15 min |
| SEV-1 | Telegram | "[SEV-1] {component} degraded. Investigating." | Every 30 min |
| SEV-2 | Telegram | "[SEV-2] {component} issue. Will fix in next session." | Once |
| SEV-3 | Audit log | Logged only, no alert | N/A |

### 8.2 Recovery Communication

```
Template: Recovery Complete
---
[RECOVERED] {component} restored.
RTO: {actual_time} (target: {target_rto})
RPO: {data_loss} (target: {target_rpo})
Root cause: {preliminary}
Post-incident review: scheduled for {date}
---
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **27** (Deployment/DevOps) | DR plan complement deployment strategy |
| **33** (Cybersecurity) | Security incidents may trigger DR |
| **47** (Operational Contract) | T-008 (backup) feeds DR; T-044 (monitoring) detects failures |
| **49** (Incident Mgmt) | DR recovery triggers incident management process |
| **55** (Capacity Planning) | Capacity issues may trigger DR scenarios |

---

## Referensi

1. `src/trading_system/data/storage.py` — Backup & restore utilities
2. `src/trading_system/monitoring/engine.py` — Health monitoring for failure detection
3. `scripts/daily_runner.py` — Scheduled backup trigger
4. `pustaka/27-deployment-devops-trading.md` — Deployment & DevOps
5. `pustaka/47-operational-contract-runbook.md` — T-008 (backup), T-044 (monitoring)
6. NIST SP 800-34: Contingency Planning Guide for Federal Information Systems
7. ISO 22301: Business Continuity Management Systems

---

> **Catatan:** DR plan adalah living document. Update setiap DR drill, setiap insiden, dan setiap perubahan arsitektur. DR plan yang tidak di-drill = ilusi keselamatan.
