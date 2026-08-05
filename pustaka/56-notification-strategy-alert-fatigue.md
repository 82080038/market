# Notification Strategy & Alert Fatigue Prevention

> **Dokumen 56** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Severity-based routing, alert deduplication, quiet hours, alert aggregation, escalation policy, alert quality metrics.
>
> **Konteks:** Dokumen 47 punya Telegram notification (T-045) dan escalation (SEV-0 to SEV-3). Tapi belum ada strategi: bagaimana mencegah alert fatigue, kapan quiet hours, bagaimana deduplicate alert, bagaimana measure alert quality.

---

## Daftar Isi

1. [Alert Fatigue Problem](#1-alert-fatigue-problem)
2. [Alert Severity & Routing](#2-alert-severity--routing)
3. [Alert Deduplication](#3-alert-deduplication)
4. [Quiet Hours & Suppression](#4-quiet-hours--suppression)
5. [Alert Aggregation](#5-alert-aggregation)
6. [Escalation Policy](#6-escalation-policy)
7. [Alert Quality Metrics](#7-alert-quality-metrics)

---

## 1. Alert Fatigue Problem

### 1.1 Kenapa Alert Fatigue Berbahaya

| Tanpa Strategy | Dengan Strategy |
|---------------|-----------------|
| 100 alert/hari → user ignore semua | 5 alert/hari → user perhatikan setiap alert |
| SEV-3 alert tenggelam di tengah SEV-0 | SEV-0 langsung distinct, SEV-3 di daily report |
| Alert berulang untuk issue yang sama | Dedup: 1 alert per issue, bukan 100 |
| Alert tengah malam untuk non-critical | Quiet hours: SEV-3 tidak alert setelah 22:00 |
| Tidak tahu alert akurat atau tidak | Alert precision/recall diukur |

### 1.2 Target Metrics

| Metric | Target |
|--------|--------|
| Alert per hari | < 10 (excluding daily report) |
| SEV-0/SEV-1 per bulan | < 5 |
| Alert precision (true positive rate) | > 80% |
| Alert response time (SEV-0) | < 5 min |
| Alert fatigue index | < 0.2 (low fatigue) |

---

## 2. Alert Severity & Routing

### 2.1 Routing Matrix

| Severity | Channel | Sound | Quiet Hours Override | Frequency |
|----------|---------|-------|---------------------|-----------|
| **SEV-0** | Telegram + phone push | Loud | Yes (always alert) | Immediate + every 15 min until ACK |
| **SEV-1** | Telegram | Normal | Yes (alert if > 22:00) | Immediate + every 30 min until ACK |
| **SEV-2** | Telegram | Silent | No (suppress 22:00-07:00) | Once + daily summary |
| **SEV-3** | Audit log only | None | N/A | Daily summary only |

### 2.2 Alert Message Format

```
SEV-0 (Critical):
🚨 [SEV-0] {component} DOWN
Component: {name}
Error: {error_message}
Time: {timestamp} WIB
Action needed: {immediate_action}
RTO target: {rto}

SEV-1 (High):
⚠️ [SEV-1] {component} DEGRADED
Component: {name}
Error: {error_message}
Time: {timestamp} WIB
Impact: {impact_description}
Workaround: {workaround if any}

SEV-2 (Medium):
📋 [SEV-2] {component} ISSUE
{description}
Will fix in next session.

SEV-3 (Low):
(Daily summary only, no real-time alert)
```

---

## 3. Alert Deduplication

### 3.1 Dedup Rules

```python
# utils/alert_dedup.py

from collections import defaultdict
from datetime import datetime, timedelta

class AlertDeduplicator:
    def __init__(self, dedup_window_minutes=30):
        self.dedup_window = timedelta(minutes=dedup_window_minutes)
        self.recent_alerts = defaultdict(list)  # key -> [timestamps]

    def should_send(self, alert_key, severity):
        """
        Determine if alert should be sent or deduplicated.

        alert_key: unique identifier for the alert type
                   e.g., "yahoo_api_down", "gpu_oom", "db_slow"
        severity: SEV-0, SEV-1, SEV-2, SEV-3
        """
        now = datetime.now()

        # SEV-0 always send (no dedup)
        if severity == "SEV-0":
            return True

        # Check recent alerts for this key
        recent = self.recent_alerts[alert_key]
        # Clean old entries
        recent = [t for t in recent if now - t < self.dedup_window]
        self.recent_alerts[alert_key] = recent

        if len(recent) > 0:
            # Already alerted recently, dedup
            return False

        # New alert
        recent.append(now)
        return True
```

### 3.2 Dedup Keys

| Alert Key | Dedup Window | Rationale |
|-----------|-------------|-----------|
| `yahoo_api_down` | 30 min | Yahoo may recover quickly |
| `idx_scrape_blocked` | 2 hours | idx.co.id blocks are long |
| `gpu_oom` | 60 min | Will retry with smaller batch |
| `db_slow` | 15 min | May be transient |
| `pipeline_timeout` | 60 min | One alert per pipeline run |
| `stale_data` | 60 min | One alert per stale period |
| `high_slippage` | 24 hours | One alert per ticker per day |
| `model_drift` | 24 hours | One alert per ticker per day |

---

## 4. Quiet Hours & Suppression

### 4.1 Quiet Hours Schedule

| Time Window | SEV-0 | SEV-1 | SEV-2 | SEV-3 |
|-------------|-------|-------|-------|-------|
| 07:00-22:00 (active) | ✅ Alert | ✅ Alert | ✅ Alert | Daily summary |
| 22:00-07:00 (quiet) | ✅ Alert | ✅ Alert (if not ACK'd) | ❌ Suppress | ❌ Suppress |
| Weekend (Sabtu-Minggu) | ✅ Alert | ✅ Alert | ❌ Suppress | ❌ Suppress |
| IDX Holiday | ✅ Alert | ✅ Alert | ❌ Suppress | ❌ Suppress |

### 4.2 Suppression Logic

```python
def should_suppress(severity, current_time=None):
    """Determine if alert should be suppressed during quiet hours."""
    if current_time is None:
        current_time = datetime.now()

    # SEV-0 and SEV-1 never suppressed
    if severity in ("SEV-0", "SEV-1"):
        return False

    # Check if weekend
    if current_time.weekday() >= 5:  # Saturday=5, Sunday=6
        return True

    # Check if IDX holiday
    if is_idx_holiday(current_time.date()):
        return True

    # Check quiet hours (22:00-07:00)
    hour = current_time.hour
    if hour >= 22 or hour < 7:
        return True

    return False
```

---

## 5. Alert Aggregation

### 5.1 Daily Summary Alert

```
📊 Daily Summary — 2026-08-05

Pipeline: ✅ Complete (45 min, 928 tickers)
Scores: ✅ 928/928 computed
Predictions: ✅ 928 generated
Health: ✅ Score 92/100

Issues (SEV-2/3):
- idx.co.id scrape: 3 retries needed (SEV-2)
- TLKM.JK LSTM: OOS R² declined to -0.01 (SEV-3)
- Broker flow: 0 rows for 2 tickers (SEV-3)

Alerts sent today: 2 (1 SEV-1, 1 SEV-2)
Alerts suppressed (quiet hours): 0
Alerts deduplicated: 5

No action needed for SEV-3 items.
```

### 5.2 Weekly Summary

```
📊 Weekly Summary — Week of 2026-08-03

Pipeline runs: 5/5 successful
LSTM retrain: ✅ 928 models, avg OOS R² = 0.12
Weight optimization: ✅ Completed

Incidents: 1 SEV-1 (Yahoo API down, 45 min)
Alerts sent: 8 total (1 SEV-1, 7 SEV-2/3)
Alert precision: 87% (1 false positive)

Action items:
- [ ] Investigate TLKM.JK model degradation
- [ ] Update idx.co.id scraper (3 retries this week)
```

---

## 6. Escalation Policy

### 6.1 Escalation Flow

```
Alert triggered
      │
      ▼
┌──────────────┐
│ DEDUP CHECK  │──▶ Duplicate? ──▶ Suppress
└──────────────┘
      │ (not duplicate)
      ▼
┌──────────────┐
│ QUIET HOURS  │──▶ Suppress (SEV-2/3 only)
└──────────────┘
      │ (not suppressed)
      ▼
┌──────────────┐
│ SEND ALERT   │──▶ Telegram
└──────────────┘
      │
      ▼
┌──────────────┐
│ WAIT FOR ACK │──▶ 5 min (SEV-0) / 15 min (SEV-1)
└──────────────┘
      │ (no ACK)
      ▼
┌──────────────┐
│ ESCALATE     │──▶ Repeat alert + escalate channel
└──────────────┘
      │
      ▼
┌──────────────┐
│ WAIT FOR ACK │──▶ 15 min (SEV-0) / 30 min (SEV-1)
└──────────────┘
      │ (no ACK)
      ▼
┌──────────────┐
│ FINAL ESCALATE│──▶ Email + phone push
└──────────────┘
```

---

## 7. Alert Quality Metrics

### 7.1 Metrics Definitions

| Metric | Definisi | Formula | Target |
|--------|----------|---------|--------|
| **Alert Precision** | % alert yang true positive | true_positives / total_alerts | > 80% |
| **Alert Recall** | % real issues yang terdeteksi | detected_issues / total_issues | > 90% |
| **MTTA** (Mean Time To Acknowledge) | Rata-rata waktu ke acknowledge | Σ(ack_time - alert_time) / N | < 5 min SEV-0 |
| **Alert Volume** | Jumlah alert per hari | count(alerts) per day | < 10 |
| **Alert Fatigue Index** | Ratio suppressed/dedup to total | (suppressed + deduped) / total_triggered | > 0.5 (good dedup) |
| **False Positive Rate** | % alert yang false alarm | false_positives / total_alerts | < 20% |

### 7.2 Monthly Alert Quality Report

```markdown
## Alert Quality Report — [Month]

### Volume
- Total alerts triggered: [N]
- Alerts sent: [N] (after dedup/suppression)
- Alerts suppressed (quiet hours): [N]
- Alerts deduplicated: [N]
- Dedup rate: [X]% (target: > 50%)

### Precision
- True positives: [N]
- False positives: [N]
- Precision: [X]% (target: > 80%)

### Response
- Avg MTTA (SEV-0): [X] min (target: < 5 min)
- Avg MTTA (SEV-1): [X] min (target: < 15 min)
- Unacknowledged alerts: [N]

### Top Alert Sources
1. [source]: [N] alerts
2. [source]: [N] alerts

### Action Items
- [ ] Tune alert threshold for [source] (too many false positives)
- [ ] Adjust dedup window for [alert_key]
```

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **47** (Operational Contract) | T-045 (Telegram) implements this strategy |
| **49** (Incident Mgmt) | Alert triggers incident response |
| **44** (Social/Copy Trading) | Alert sharing for copy trading |

---

## Referensi

1. `src/trading_system/utils/notifier.py` — Telegram & email notification
2. `src/trading_system/monitoring/engine.py` — Alert generation
3. `src/trading_system/api/app.py` — WebSocket alert endpoints
4. `pustaka/47-operational-contract-runbook.md` — T-045 (Telegram notification)
5. `pustaka/49-incident-management-post-mortem.md` — Alert triggers incident response
6. `pustaka/80-watchlist-alert-system.md` — Alert system implementation
7. PagerDuty: Alerting best practices for reducing alert fatigue

---

> **Catatan:** Alert yang baik adalah alert yang ditindak. "Setiap alert yang di-ignore adalah noise yang mengurangi efektivitas alert yang penting." Quality over quantity — lebih baik 5 alert yang semua ditindak daripada 100 alert yang di-ignore.
