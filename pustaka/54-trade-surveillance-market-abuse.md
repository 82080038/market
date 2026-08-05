# Trade Surveillance & Market Abuse Detection

> **Dokumen 54** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Deteksi pola trading mencurigakan, compliance log untuk OJK, best execution obligation tracking.
>
> **Konteks:** Dokumen 33 bahas cybersecurity. Dokumen 41 bahas UU PDP. Tapi belum ada doc tentang trade surveillance: deteksi wash trade, spoofing, layering, front-running — bahkan untuk single-user system, accidental patterns bisa terlihat seperti market abuse.

---

## Daftar Isi

1. [Kenapa Trade Surveillance untuk Single-User](#1-kenapa-trade-surveillance-untuk-single-user)
2. [Market Abuse Patterns](#2-market-abuse-patterns)
3. [Detection Rules](#3-detection-rules)
4. [Surveillance Dashboard](#4-surveillance-dashboard)
5. [Compliance Log untuk OJK](#5-compliance-log-untuk-ojk)
6. [Alert & Investigation](#6-alert--investigation)

---

## 1. Kenapa Trade Surveillance untuk Single-User

### 1.1 Risiko tanpa Surveillance

| Risiko | Impact |
|--------|--------|
| **Accidental wash trade** | Buy dan sell ticker yang sama di hari yang sama → terlihat manipulasi |
| **Pattern mirip spoofing** | Order besar lalu cancel → terlihat manipulasi market |
| **Tidak ada audit trail** | Jika OJK audit, tidak bisa pembuktian |
| **Tidak ada best execution proof** | Tidak bisa tunjukkan bahwa order di-fill dengan harga wajar |

### 1.2 Prinsip

1. **Self-surveillance** — sistem monitor diri sendiri, bukan external regulator
2. **Log everything** — setiap order, cancel, modify tercatat
3. **Alert on suspicious** — jika pattern terlihat abusive, alert user
4. **Compliance ready** — jika OJK audit, data siap

---

## 2. Market Abuse Patterns

### 2.1 Patterns untuk Deteksi

| Pattern | Definisi | Deteksi | Severity |
|---------|----------|---------|----------|
| **Wash Trade** | Buy dan sell ticker sama dalam waktu singkat | Same ticker, opposite side, < 1 hour | High |
| **Spoofing** | Order besar lalu cancel sebelum fill | Order > 5x normal size, cancelled < 30s | High |
| **Layering** | Multiple order di harga berbeda lalu cancel | > 5 orders same ticker, cancelled in batch | High |
| **Front-running** | Order sebelum recommendation published | Order time < recommendation time | Medium |
| **Marking the close** | Order besar di menit terakhir sesi | Order > 3x normal, last 5 min of session | Medium |
| **Excessive trading** | > 20 orders per ticker per day | Count orders per ticker per day | Low |
| **Circular trading** | Buy A → sell A → buy A pattern | Detect round-trip pattern | Medium |

### 2.2 False Positive Awareness

- **Wash trade**: bisa terjadi jika user change mind (buy lalu sell karena salah klik)
- **Spoofing**: bisa terjadi jika order terlalu besar lalu user cancel karena sadar salah
- **Front-running**: bisa terjadi jika user manual order sebelum sistem publish recommendation
- **Marking the close**: bisa terjadi jika user baru sempat trade di akhir sesi

---

## 3. Detection Rules

```python
# surveillance/detector.py

def detect_wash_trade(orders, ticker, date):
    """Deteksi buy dan sell ticker sama dalam 1 jam."""
    ticker_orders = orders[(orders.ticker == ticker) & (orders.date == date)]
    ticker_orders = ticker_orders.sort_values('fill_time')

    for i in range(len(ticker_orders) - 1):
        for j in range(i + 1, len(ticker_orders)):
            if ticker_orders.iloc[i].side != ticker_orders.iloc[j].side:
                time_diff = (ticker_orders.iloc[j].fill_time -
                             ticker_orders.iloc[i].fill_time).total_seconds()
                if time_diff < 3600:  # < 1 hour
                    return {
                        "pattern": "wash_trade",
                        "severity": "high",
                        "order_1": ticker_orders.iloc[i].id,
                        "order_2": ticker_orders.iloc[j].id,
                        "time_diff_seconds": time_diff,
                        "note": "Buy dan sell ticker sama dalam < 1 jam"
                    }
    return None

def detect_spoofing(orders, ticker, date):
    """Deteksi order besar yang di-cancel."""
    cancelled = orders[(orders.ticker == ticker) & (orders.date == date) &
                       (orders.status == 'CANCELLED')]
    filled = orders[(orders.ticker == ticker) & (orders.date == date) &
                    (orders.status == 'FILLED')]

    if len(filled) == 0:
        avg_size = 0
    else:
        avg_size = filled.shares.mean()

    for _, order in cancelled.iterrows():
        if avg_size > 0 and order.shares > avg_size * 5:
            cancel_time = (order.cancel_time - order.submit_time).total_seconds()
            if cancel_time < 30:
                return {
                    "pattern": "spoofing",
                    "severity": "high",
                    "order_id": order.id,
                    "order_size": order.shares,
                    "avg_size": avg_size,
                    "cancel_seconds": cancel_time,
                    "note": "Order besar di-cancel < 30 detik"
                }
    return None

def detect_front_running(orders, recommendations, ticker, date):
    """Deteksi order sebelum recommendation published."""
    ticker_orders = orders[(orders.ticker == ticker) & (orders.date == date)]
    ticker_recs = recommendations[(recommendations.ticker == ticker) &
                                   (recommendations.date == date)]

    for _, order in ticker_orders.iterrows():
        for _, rec in ticker_recs.iterrows():
            if order.submit_time < rec.published_at:
                time_diff = (rec.published_at - order.submit_time).total_seconds()
                if time_diff < 300:  # < 5 min before recommendation
                    return {
                        "pattern": "front_running",
                        "severity": "medium",
                        "order_id": order.id,
                        "order_time": order.submit_time,
                        "rec_time": rec.published_at,
                        "time_diff_seconds": time_diff,
                        "note": "Order dibuat sebelum recommendation dipublish"
                    }
    return None

def detect_marking_the_close(orders, ticker, date):
    """Deteksi order besar di 5 menit terakhir sesi."""
    ticker_orders = orders[(orders.ticker == ticker) & (orders.date == date)]

    for _, order in ticker_orders.iterrows():
        fill_time = order.fill_time
        # Sesi 1 close: 11:30, Sesi 2 close: 15:50
        if fill_time.hour == 11 and fill_time.minute >= 25:
            session_end = "11:30"
        elif fill_time.hour == 15 and fill_time.minute >= 45:
            session_end = "15:50"
        else:
            continue

        avg_size = ticker_orders.shares.mean()
        if order.shares > avg_size * 3:
            return {
                "pattern": "marking_the_close",
                "severity": "medium",
                "order_id": order.id,
                "order_size": order.shares,
                "avg_size": avg_size,
                "session_end": session_end,
                "note": f"Order besar di 5 menit terakhir sesi (close {session_end})"
            }
    return None

def detect_excessive_trading(orders, ticker, date):
    """Deteksi > 20 orders per ticker per day."""
    count = len(orders[(orders.ticker == ticker) & (orders.date == date)])
    if count > 20:
        return {
            "pattern": "excessive_trading",
            "severity": "low",
            "order_count": count,
            "note": f"{count} orders untuk {ticker} dalam 1 hari"
        }
    return None
```

---

## 4. Surveillance Dashboard

### 4.1 Daily Surveillance Summary

```
Trade Surveillance Report — 2026-08-05
═══════════════════════════════════════

Total orders: 12
Total tickers traded: 5

Pattern Detection:
┌────────────────────┬────────┬──────────┬─────────────────────┐
│ Pattern            │ Count  │ Severity │ Action              │
├────────────────────┼────────┼──────────┼─────────────────────┤
│ Wash Trade         │ 0      │ —        │ Clear               │
│ Spoofing           │ 0      │ —        │ Clear               │
│ Front-running      │ 1      │ Medium   │ Review (see note)   │
│ Marking the close  │ 0      │ —        │ Clear               │
│ Excessive trading  │ 0      │ —        │ Clear               │
└────────────────────┴────────┴──────────┴─────────────────────┘

Alerts:
- [MEDIUM] Front-running detected: BBCA.JK order at 18:22,
  recommendation published at 18:25. Time diff: 3 min.
  Note: User may have manually ordered based on pre-published signal.

Best Execution:
- All 12 orders filled within SLA
- Avg slippage: 0.08%
- Best execution score: 87/100

Compliance Status: ✅ No high-severity alerts
```

---

## 5. Compliance Log untuk OJK

### 5.1 Log Schema

```sql
CREATE TABLE surveillance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_date DATE NOT NULL,
    pattern_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    ticker TEXT,
    order_ids_json TEXT,           -- JSON array of related order IDs
    details_json TEXT,             -- JSON with detection details
    investigated BOOLEAN DEFAULT FALSE,
    investigation_notes TEXT,
    false_positive BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 OJK Audit Package

Jika OJK audit, siapkan:

1. **Order history** — semua orders dalam periode audit
2. **Surveillance log** — semua pattern detected dan investigation
3. **Best execution proof** — TCA report per order
4. **Audit trail** — audit_log entries untuk periode audit
5. **Decision trail** — recommendation history (kenapa order dibuat)

---

## 6. Alert & Investigation

### 6.1 Alert Routing

| Severity | Channel | Action |
|----------|---------|--------|
| High | Telegram + audit_log | Immediate review, halt auto-trade if pattern continues |
| Medium | Audit log + daily report | Review within 24 hours |
| Low | Daily report only | Monitor trend |

### 6.2 Investigation Process

1. **Alert received** — surveillance detects pattern
2. **Review orders** — check if pattern is intentional or accidental
3. **Classify** — false positive (accidental) or true positive (intentional)
4. **Document** — investigation notes in surveillance_log
5. **Action** — if true positive, adjust trading rules to prevent recurrence

---

## 7. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **33** (Cybersecurity) | Security logs complement surveillance logs |
| **41** (UU PDP) | Compliance framework |
| **47** (Operational Contract) | T-041 (Auto Trade), T-046 (Audit Log) |
| **52** (TCA) | Best execution proof feeds surveillance |

---

## Referensi

1. `src/trading_system/execution/automated.py` — Auto-trade execution (audit trail)
2. `src/trading_system/data/storage.py` — audit_log table
3. `pustaka/33-cybersecurity-trading-system.md` — Security audit trail
4. `pustaka/40-oms-ems-architecture.md` — OMS order audit
5. `pustaka/52-transaction-cost-analysis-execution-quality.md` — Best execution proof
6. OJK Regulation No. 17/POJK.03/2014 — Internal Audit
7. IOSCO Principles for Market Integrity

---

## 8. Implementasi: Manipulation Detection Engine

> **Sumber:** `src/trading_system/analysis/manipulation.py` (179 baris)

Sistem `trading-system` mengimplementasikan deteksi 6 pattern manipulasi pasar langsung dari data OHLCV.

| 5W1H | Detail |
|------|--------|
| **What** | Manipulation Detection Engine: 6 pattern (volume anomaly, P-V divergence, marking close, pump & dump, wash trading, spread anomaly) |
| **Why** | IDX punya riwayat manipulasi (gorengan, wash trading) — sistem trading harus deteksi dan hindari saham yang dimanipulasi |
| **When** | Pre-trade checklist, surveillance monitoring, dan screening |
| **Where** | Analysis layer: manipulation.py → pre-trade checklist + XAI + surveillance |
| **Who** | Dipanggil oleh pre_trade_checklist.py dan score_context.py (XAI) |
| **How** | Pattern matching pada OHLCV: volume > 5x median, price-volume divergence > 30%, marking close, pump & dump sequence |

### 8.1 Pattern Detection

| Pattern | Deteksi | Threshold |
|---------|---------|-----------|
| **Volume anomaly** | Volume spike vs median 20 hari | > 5x median |
| **Price-volume divergence** | Harga naik tapi volume turun (atau sebaliknya) | Divergence > 30% |
| **Marking the close** | Price spike di menit-menit akhir sesi | Return 15:30-15:50 > 2x daily return |
| **Pump & dump** | Sharp rise + volume spike + sharp decline | Rise > 20% lalu drop > 15% |
| **Wash trading** | High volume tapi price change kecil | Volume > 3x median, price change < 1% |
| **Spread anomaly** | High-low range spike | Range > 3x rata-rata |

### 8.2 Output

```python
@dataclass
class ManipulationFlag:
    check: str          # Nama pattern
    date: str           # Tanggal deteksi
    severity: str       # low, medium, high
    detail: str         # Deskripsi

@dataclass
class ManipulationReport:
    symbol: str
    flags: list[ManipulationFlag]
    risk_score: float   # 0-100

    @property
    def has_danger(self) -> bool:
        return any(f.severity == "high" for f in self.flags)
```

### 8.3 Integrasi

- **Pre-trade checklist:** Block order jika `has_danger = True`
- **Surveillance dashboard:** Tampilkan manipulation flags untuk monitoring
- **Compliance log:** Simpan ke audit_log untuk laporan OJK
- **Alert system:** Notifikasi jika risk_score > 70

---

> **Catatan:** Trade surveillance bukan paranoia — adalah profesionalisme. "Audit diri sendiri sebelum diaudit orang lain." Setiap pattern mencurigakan yang terdeteksi adalah opportunity untuk improve trading discipline. Implementasi: `src/trading_system/analysis/manipulation.py`.
