# Incident Management & Post-Incident Review

> **Dokumen 49** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Incident lifecycle, blameless post-mortem, on-call rotation, action item tracking untuk sistem trading.
>
> **Konteks:** Dokumen 47 punya failure handling dan escalation (SEV-0 to SEV-3). Dokumen 48 punya DR/BCP. Tapi belum ada formal incident management process: bagaimana incident dideteksi, di-respons, di-mitigate, di-resolve, lalu di-post-mortem. Dokumen ini mengisi gap.

---

## Daftar Isi

1. [Incident Lifecycle](#1-incident-lifecycle)
2. [Severity Matrix](#2-severity-matrix)
3. [On-Call Rotation](#3-on-call-rotation)
4. [Incident Response Procedure](#4-incident-response-procedure)
5. [Blameless Post-Mortem](#5-blameless-post-mortem)
6. [Action Item Tracking](#6-action-item-tracking)
7. [Incident Metrics](#7-incident-metrics)
8. [Incident Log Template](#8-incident-log-template)

---

## 1. Incident Lifecycle

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ DETECT   │──▶│ RESPOND  │──▶│ MITIGATE │──▶│ RESOLVE  │──▶│ POST-MORTEM│─▶│ IMPROVE  │
│          │   │          │   │          │   │          │   │          │   │          │
│ Alert    │   │ Acknowledge│  │ Stop     │   │ Fix root │   │ Blameless│   │ Action   │
│ Monitor  │   │ Assess    │   │ bleeding │   │ cause    │   │ analysis │   │ items    │
│ User rep │   │ Severity  │   │ Workaround│  │ Verify   │   │ Timeline │   │ deployed │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

### 1.1 Fase Detail

| Fase | Tujuan | SLA | Output |
|------|--------|-----|--------|
| **Detect** | Identifikasi incident | < 5 min (monitoring) atau < 1 jam (user report) | Alert triggered |
| **Respond** | Acknowledge dan assess severity | < 5 min dari alert | Incident log created, severity assigned |
| **Mitigate** | Stop the bleeding, reduce impact | < 30 min untuk SEV-0 | Impact contained, workaround applied |
| **Resolve** | Fix root cause, verify fix | < RTO (see doc 48) | Service restored, verified |
| **Post-Mortem** | Understand what happened | < 48 jam dari resolve | Post-mortem document |
| **Improve** | Prevent recurrence | < 2 minggu dari post-mortem | Action items deployed |

---

## 2. Severity Matrix

| Severity | Definisi | Contoh | Response Time | Escalation |
|----------|----------|--------|---------------|------------|
| **SEV-0** | Sistem tidak bisa dipakai sama sekali. Data loss. | DB corrupt, disk full, semua services down | Immediate (24/7) | Telegram + phone |
| **SEV-1** | Komponen critical degraded. Pipeline tidak jalan. | API down, GPU fail, Yahoo down saat pipeline | < 15 min | Telegram |
| **SEV-2** | Komponen non-critical gagal. Workaround ada. | idx.co.id blocked, Telegram bot down, single engine error | < 4 jam | Audit log |
| **SEV-3** | Minor issue, tidak impact user. | UI glitch, log warning, cosmetic bug | Next session | Audit log only |

### 2.1 Trading-Specific Severity Rules

- **Salah rekomendasi BUY/SELL** karena bug → **SEV-0** (user bisa loss uang)
- **Data OHLCV stale > 1 hari** → **SEV-1** (semua analysis tidak valid)
- **LSTM model corrupt** → **SEV-1** (prediction tidak akurat)
- **Audit log tidak writing** → **SEV-1** (compliance issue)
- **Auto-trade mengirim order salah** → **SEV-0** (financial loss)

---

## 3. On-Call Rotation

### 3.1 Solo Developer On-Call

Untuk solo developer, on-call tidak ada rotasi. Tapi prinsip tetap:

| Aturan | Implementasi |
|--------|--------------|
| **24/7 availability** | Telegram alert diaktifkan, phone notif |
| **Quiet hours** | SEV-3 tidak alert setelah 22:00 WIB |
| **Backup contact** | Jika tidak respon dalam 30 min → email backup |
| **Do Not Disturb override** | SEV-0 dan SEV-1 override DND |

### 3.2 Future: Team On-Call

| Role | Jadwal | Tanggung Jawab |
|------|--------|----------------|
| **Primary on-call** | 1 minggu rotation | Respond to all alerts |
| **Secondary on-call** | 1 minggu rotation | Backup jika primary tidak respon dalam 15 min |
| **Escalation manager** | On-demand | Untuk SEV-0 yang tidak resolve dalam 1 jam |

### 3.3 On-Call Checklist

- [ ] Telegram alert aktif dan tested
- [ ] Laptop dengan akses ke repo + .venv
- [ ] SSH access ke server (if remote)
- [ ] DR plan (doc 48) accessible
- [ ] Incident log template ready
- [ ] Phone charged dan tidak silent

---

## 4. Incident Response Procedure

### 4.1 Step-by-Step

```
STEP 1: DETECT
├── Alert dari monitoring (T-044) → Telegram
├── Alert dari user report → Telegram/email
└── Alert dari failed task → audit_log

STEP 2: RESPOND (< 5 min)
├── Acknowledge alert (Telegram reply "ACK")
├── Create incident log (see §8 template)
├── Assess severity (see §2 matrix)
├── If SEV-0: start timer, notify all stakeholders

STEP 3: MITIGATE (< 30 min untuk SEV-0)
├── Stop the bleeding:
│   ├── Stop affected services
│   ├── Enable fallback (CPU, stale data, etc.)
│   └── Prevent cascading failures
├── Apply workaround if available
└── Update incident log with mitigation status

STEP 4: RESOLVE (< RTO)
├── Identify root cause
├── Apply fix
├── Verify fix (functional test)
├── Restart services
├── Verify all services operational
└── Update incident log: "RESOLVED"

STEP 5: POST-MORTEM (< 48 jam)
├── Schedule post-mortem review
├── Write blameless analysis (see §5)
├── Identify action items
└── Create tickets for action items

STEP 6: IMPROVE (< 2 minggu)
├── Deploy action items
├── Update DR plan if needed
├── Update runbook if needed
├── Update monitoring if needed
└── Close incident log
```

### 4.2 Communication During Incident

| Timing | Channel | Message |
|--------|---------|---------|
| T+0 (detect) | Telegram | "[SEV-X] {component} incident detected. Investigating." |
| T+5 (respond) | Telegram | "[SEV-X] Severity assessed. Mitigation in progress." |
| T+30 (mitigate) | Telegram | "[SEV-X] Mitigation applied: {workaround}. Root cause investigation ongoing." |
| T+resolve | Telegram | "[SEV-X] RESOLVED. Root cause: {cause}. RTO: {time}. Post-mortem scheduled." |
| T+48h | Audit log | Post-mortem document linked |

---

## 5. Blameless Post-Mortem

### 5.1 Prinsip Blameless

- **Tidak mencari siapa yang salah** — mencari **apa** yang salah
- **Setiap orang membuat keputusan terbaik dengan informasi yang ada saat itu**
- **Fokus pada system improvement, bukan individual blame**
- **Semua orang merasa safe untuk share apa yang mereka lakukan**

### 5.2 Post-Mortem Template

```markdown
## Post-Mortem: [Incident Title]

**Date:** [YYYY-MM-DD]
**Severity:** [SEV-X]
**Duration:** [detection to resolution]
**Author:** [name]

### Summary
[1-2 paragraph summary of what happened]

### Timeline (all times WIB)
| Time | Event |
|------|-------|
| 16:30 | Monitoring alert: "DB unresponsive" |
| 16:32 | Acknowledged, severity assessed as SEV-0 |
| 16:35 | Stopped all services |
| 16:40 | Identified: SQLite WAL checkpoint corruption |
| 16:50 | Restored from backup (trading_system_20260804.db) |
| 17:00 | Verified DB integrity, row counts match |
| 17:05 | Restarted API, scheduler |
| 17:10 | Verified all endpoints responding |
| 17:15 | Incident resolved. RTO: 45 min (target: 30 min) |

### Root Cause
[Technical explanation of why the incident occurred]

Example:
SQLite WAL checkpoint failed due to disk I/O contention
during backup process. The backup (T-008) and WAL checkpoint
ran simultaneously, causing WAL file corruption.

### Contributing Factors
- [Factor 1: e.g., backup and checkpoint not coordinated]
- [Factor 2: e.g., no disk I/O monitoring]
- [Factor 3: e.g., WAL checkpoint timeout too aggressive]

### What Worked
- [Monitoring detected within 5 min]
- [Backup was valid and recent]
- [Recovery procedure was clear and executable]

### What Didn't Work
- [RTO exceeded target by 15 min]
- [No disk I/O alerting before contention]
- [Backup and checkpoint not serialized]

### Action Items
| # | Action | Owner | Priority | Due Date | Status |
|---|--------|-------|----------|----------|--------|
| 1 | Serialize backup and WAL checkpoint | [name] | High | [date] | Open |
| 2 | Add disk I/O monitoring | [name] | Medium | [date] | Open |
| 3 | Update DR plan with WAL checkpoint scenario | [name] | Low | [date] | Open |

### Lessons Learned
- [Lesson 1]
- [Lesson 2]

### Appendix
- [Links to logs, alerts, code changes]
```

### 5.3 Post-Mortem Quality Checklist

- [ ] Timeline lengkap dari detection ke resolution
- [ ] Root cause diidentifikasi (bukan hanya symptom)
- [ ] Contributing factors diidentifikasi
- [ ] Action items specific, measurable, ada owner dan due date
- [ ] Tidak ada blame language ("X should have...", "X failed to...")
- [ ] Lessons learned actionable
- [ ] Post-mortem disimpan di repo (version control)

---

## 6. Action Item Tracking

### 6.1 Action Item Lifecycle

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ CREATED  │──▶│ IN PROGRESS│──▶│ DEPLOYED │──▶│ VERIFIED │
│          │   │          │   │          │   │          │
│ Post-mortem│  │ Developer│   │ Merged   │   │ Tested in│
│ output   │   │ working  │   │ deployed │   │ production│
└──────────┘   └──────────┘   └──────────┘   └──────────┘
```

### 6.2 Action Item Priority

| Priority | SLA | Contoh |
|----------|-----|--------|
| **Critical** | < 24 jam | Fix yang mencegah SEV-0 recurrence |
| **High** | < 1 minggu | Fix yang mencegah SEV-1 recurrence |
| **Medium** | < 2 minggu | Improvement yang mengurangi RTO |
| **Low** | < 1 bulan | Documentation update, monitoring improvement |

### 6.3 Action Item Review

- **Weekly review**: semua open action items, check progress
- **Monthly review**: semua action items, close completed ones
- **Quarterly review**: analyze pattern — apakah incident tertentu berulang?

---

## 7. Incident Metrics

### 7.1 Key Metrics

| Metric | Definisi | Target | Formula |
|--------|----------|--------|---------|
| **MTTD** (Mean Time To Detect) | Rata-rata waktu dari failure ke detection | < 5 min | Σ(detection_time - failure_time) / N |
| **MTTA** (Mean Time To Acknowledge) | Rata-rata waktu dari alert ke acknowledge | < 5 min | Σ(ack_time - alert_time) / N |
| **MTTM** (Mean Time To Mitigate) | Rata-rata waktu dari acknowledge ke mitigation | < 30 min | Σ(mitigate_time - ack_time) / N |
| **MTTR** (Mean Time To Resolve) | Rata-rata waktu dari failure ke resolution | < RTO | Σ(resolve_time - failure_time) / N |
| **Incident Rate** | Jumlah incident per bulan | < 5/bulan | count(incidents) per month |
| **SEV-0 Rate** | Jumlah SEV-0 per quarter | 0 | count(SEV-0) per quarter |
| **Post-Mortem Completion** | % incident dengan post-mortem | 100% untuk SEV-0/1 | count(post-mortems) / count(incidents) |
| **Action Item Closure** | % action items closed within SLA | > 90% | count(closed_on_time) / count(total) |

### 7.2 Monthly Incident Report

```markdown
## Incident Report — [Month Year]

**Total incidents:** [N]
**SEV-0:** [N] | **SEV-1:** [N] | **SEV-2:** [N] | **SEV-3:** [N]

### MTTR Trend
| Month | MTTR | Target |
|-------|------|--------|
| [prev] | [min] | [target] |
| [current] | [min] | [target] |

### Top Incidents
1. [Title] — SEV-X — MTTR: [min] — Root cause: [summary]
2. [Title] — SEV-X — MTTR: [min] — Root cause: [summary]

### Recurring Issues
- [Pattern if any]

### Action Items Status
- Total open: [N]
- Closed this month: [N]
- Overdue: [N]
```

---

## 8. Incident Log Template

### 8.1 Incident Log Entry (audit_log)

```json
{
  "incident_id": "INC-2026-08-05-001",
  "severity": "SEV-0",
  "title": "SQLite DB corruption",
  "detected_at": "2026-08-05T16:30:00+07:00",
  "detected_by": "monitoring",
  "acknowledged_at": "2026-08-05T16:32:00+07:00",
  "mitigated_at": "2026-08-05T16:45:00+07:00",
  "resolved_at": "2026-08-05T17:15:00+07:00",
  "affected_components": ["sqlite_db", "api", "scheduler"],
  "root_cause": "WAL checkpoint corruption during backup",
  "rto_actual": "45 min",
  "rto_target": "30 min",
  "rpo_actual": "1 hour",
  "rpo_target": "1 hour",
  "post_mortem": "pustaka/post-mortems/INC-2026-08-05-001.md",
  "action_items": ["AI-001", "AI-002", "AI-003"]
}
```

### 8.2 Incident ID Convention

```
INC-YYYY-MM-DD-NNN

INC = Incident
YYYY-MM-DD = Date detected
NNN = Sequential number per day (001, 002, ...)
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **47** (Operational Contract) | T-044 (monitoring) detects incidents; T-046 (audit log) records |
| **48** (DR/BCP) | DR procedures are executed during incident response |
| **50** (Change/Release) | Post-mortem action items may require code changes |
| **56** (Notification Strategy) | Incident alerts use notification strategy |

---

## Referensi

1. `src/trading_system/monitoring/engine.py` — System health monitor (incident detection)
2. `src/trading_system/utils/notifier.py` — Telegram notification for incident alerts
3. `pustaka/47-operational-contract-runbook.md` — T-044 (monitoring), T-046 (audit log)
4. `pustaka/48-disaster-recovery-business-continuity.md` — DR procedures
5. Google SRE Book — Incident Management & Postmortem chapter
6. NFPA 1600: Standard on Continuity, Emergency, and Crisis Management

---

> **Catatan:** Incident management adalah discipline, bukan ad-hoc. Setiap incident adalah opportunity untuk improve. "Fail forward" — setiap kegagalan membuat sistem lebih robust jika di-post-mortem dengan benar.
