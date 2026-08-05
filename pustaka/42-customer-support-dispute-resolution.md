# Customer Support & Dispute Resolution untuk Aplikasi Trading

> **Dokumen 42** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Sistem customer support, ticketing, escalation workflow, AI chatbot dengan guardrails, dispute resolution, dan integrasi dengan LAPS-SJK (Lembaga Alternatif Penyelesaian Sengketa Sektor Jasa Keuangan).
>
> **Konteks:** OJK POJK 22/2023 mewajibkan mekanisme pengaduan konsumen. Trading app menangani tiket high-stakes: trade dispute, KYC stuck, withdrawal gagal — setiap tiket punya implikasi regulatori. Support bukan generic CX, melainkan regulated financial service.

---

## Daftar Isi

1. [Regulatory Framework](#1-regulatory-framework)
2. [Ticketing System Architecture](#2-ticketing-system-architecture)
3. [Ticket Classification](#3-ticket-classification)
4. [Escalation Workflow](#4-escalation-workflow)
5. [SLA Management](#5-sla-management)
6. [AI Chatbot dengan Guardrails](#6-ai-chatbot-dengan-guardrails)
7. [Dispute Resolution & LAPS-SJK](#7-dispute-resolution--laps-sjk)
8. [Knowledge Base & FAQ](#8-knowledge-base--faq)
9. [Audit Trail & Compliance](#9-audit-trail--compliance)
10. [Implementasi](#10-implementasi)
11. [Adopsi dari Codebase Existing](#11-adopsi-dari-codebase-existing)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Regulatory Framework

### 1.1 Regulasi yang Berlaku

| Regulasi | Ruang Lingkup | Dampak ke Support |
|----------|--------------|-------------------|
| **POJK 22/2023** | Perlindungan konsumen jasa keuangan | Wajib punya mekanisme pengaduan |
| **SEOJK 23/2023** | Penyelesaian pengaduan konsumen | Prosedur & SLA pengaduan |
| **UU PDP 27/2022** | Personal data protection | Audit trail support interaction |
| **POJK 11/2022** | IT risk management | Incident reporting ke OJK |
| **UU 8/1999** | Perlindungan konsumen | Hak konsumen: informasi, didengar, kompensasi |
| **POJK 1/2023** | Akses konsumen di sektor jasa keuangan | Mekanisme akses & pengaduan |

### 1.2 Kewajiban Penyedia Layanan

| Kewajiban | Implementasi |
|-----------|-------------|
| **Penyediaan kanal pengaduan** | Minimal: email, telepon, aplikasi |
| **Respon pengaduan** | Maksimal 5 hari kerja (SEOJK 23/2023) |
| **Penyelesaian pengaduan** | Maksimal 20 hari kerja |
| **Notifikasi hasil** | Beritahu konsumen hasil investigasi |
| **Eskalasi ke LAPS-SJK** | Jika tidak terselesaikan dalam 20 hari |
| **Reporting ke OJK** | Laporan pengaduan periodik |
| **Audit trail** | Setiap interaksi tercatat |

---

## 2. Ticketing System Architecture

### 2.1 Arsitektur

```
┌──────────────────────────────────────────────────────────────┐
│                   CUSTOMER SUPPORT SYSTEM                     │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  In-App  │  │  Email   │  │  Phone   │  │  Social  │    │
│  │  Chat    │  │  Ticket  │  │  Call    │  │  Media   │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │           │
│       └─────────────┴─────────────┴─────────────┘           │
│                         │                                    │
│                         ▼                                    │
│              ┌─────────────────────┐                        │
│              │   Ticket Router     │                        │
│              │   (Classification)  │                        │
│              └──────────┬──────────┘                        │
│                         │                                    │
│              ┌──────────┴──────────┐                        │
│              ▼                     ▼                        │
│    ┌───────────────┐    ┌──────────────────┐               │
│    │  AI Chatbot   │    │  Human Agent     │               │
│    │  (Tier 1)     │    │  (Tier 2/3)      │               │
│    └───────┬───────┘    └────────┬─────────┘               │
│            │                     │                          │
│            ▼                     ▼                          │
│    ┌───────────────┐    ┌──────────────────┐               │
│    │  Auto-resolve │    │  Escalation      │               │
│    │  (FAQ, basic) │    │  Workflow        │               │
│    └───────────────┘    └────────┬─────────┘               │
│                                 │                           │
│                                 ▼                           │
│                       ┌──────────────────┐                 │
│                       │  Compliance &    │                 │
│                       │  LAPS-SJK        │                 │
│                       └──────────────────┘                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Database Schema

```sql
-- Support tickets
CREATE TABLE support_tickets (
    id TEXT PRIMARY KEY,
    ticket_number TEXT UNIQUE NOT NULL,      -- Human-readable: TKT-2026-000123
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,                   -- in_app, email, phone, social
    category TEXT NOT NULL,                  -- kyc, trade_dispute, payment, technical, complaint
    subcategory TEXT,
    priority TEXT NOT NULL DEFAULT 'normal', -- low, normal, high, urgent, critical
    status TEXT NOT NULL DEFAULT 'open',     -- open, in_progress, escalated, resolved, closed
    subject TEXT NOT NULL,
    description TEXT,
    assigned_agent TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    first_response_at DATETIME,
    resolved_at DATETIME,
    closed_at DATETIME,
    sla_deadline DATETIME,
    escalation_level INTEGER DEFAULT 0,
    laps_sjk_ref TEXT,                       -- Reference jika eskalasi ke LAPS-SJK
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Ticket messages (conversation thread)
CREATE TABLE ticket_messages (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    sender_type TEXT NOT NULL,               -- user, agent, bot, system
    sender_id TEXT,
    message TEXT NOT NULL,
    attachments TEXT,                        -- JSON array of file paths
    is_internal_note BOOLEAN DEFAULT FALSE,  -- Internal note (not visible to user)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(id)
);

-- Ticket audit trail
CREATE TABLE ticket_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    action TEXT NOT NULL,                    -- created, assigned, escalated, resolved, etc.
    actor TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(id)
);

-- Knowledge base articles
CREATE TABLE kb_articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,                               -- JSON array
    views INTEGER DEFAULT 0,
    helpful_votes INTEGER DEFAULT 0,
    unhelpful_votes INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    published BOOLEAN DEFAULT FALSE
);
```

---

## 3. Ticket Classification

### 3.1 Kategori Tiket

| Kategori | Subkategori | Priority Default | SLA Response | Contoh |
|----------|-------------|-----------------|--------------|--------|
| **Trade Dispute** | Order tidak terkirim | Urgent | 1 jam | "Order BUY BBCA saya tidak execute" |
| **Trade Dispute** | Fill price salah | Urgent | 1 jam | "Harga fill berbeda dari yang saya lihat" |
| **Trade Dispute** | Position tidak muncul | High | 2 jam | "Portfolio saya tidak show posisi" |
| **KYC** | Verifikasi tertunda | High | 4 jam | "KYC saya sudah 3 hari belum approve" |
| **KYC** | Dokumen ditolak | Normal | 8 jam | "Foto KTP saya ditolak, kenapa?" |
| **Payment** | Withdrawal gagal | Urgent | 1 jam | "Tarik dana Rp 5M gagal" |
| **Payment** | Deposit tidak masuk | Urgent | 1 jam | "Transfer 2 jam lalu, belum masuk" |
| **Payment** | RDN tidak ter-link | High | 4 jam | "Tidak bisa link rekening BCA" |
| **Technical** | App crash | High | 2 jam | "App crash saat buka chart" |
| **Technical** | Data tidak update | Normal | 8 jam | "Chart BBCA tidak update" |
| **Technical** | Login gagal | High | 2 jam | "Tidak bisa login" |
| **Complaint** | Layanan buruk | Normal | 8 jam | "CS lambat respon" |
| **Complaint** | Fee tidak transparan | Normal | 8 jam | "Tidak tahu kenapa kena fee" |
| **Complaint** | Eksekusi lambat | High | 4 jam | "Order 5 menit baru execute" |
| **Regulatory** | Pelanggaran OJK | Critical | 30 menit | "Saya mau report pelanggaran" |
| **Security** | Akun dibajak | Critical | 30 menit | "Ada yang login dari device tidak dikenal" |
| **Security** | Suspicious activity | Critical | 30 menit | "Transaksi yang tidak saya lakukan" |

### 3.2 Auto-Classification

```python
class TicketClassifier:
    """Auto-classify incoming tickets based on content."""

    KEYWORDS = {
        "trade_dispute": {
            "order_tidak_terkirim": ["order tidak", "tidak execute", "order gagal", "pending order"],
            "fill_price_salah": ["harga salah", "fill aneh", "slippage", "harga beda"],
            "position_hilang": ["posisi hilang", "portfolio kosong", "tidak muncul"],
        },
        "kyc": {
            "verifikasi_tertunda": ["kyc belum", "verifikasi lama", "approve lama", "pending kyc"],
            "dokumen_ditolak": ["ktp ditolak", "dokumen reject", "verifikasi gagal"],
        },
        "payment": {
            "withdrawal_gagal": ["tarik dana gagal", "withdraw gagal", "penarikan gagal"],
            "deposit_tidak_masuk": ["deposit belum", "transfer belum masuk", "top up gagal"],
            "rdn_tidak_terlink": ["rdn tidak", "rekening tidak link", "bank tidak connect"],
        },
        "security": {
            "akun_dibajak": ["dibajak", "hack", "tidak dikenal", "device asing"],
            "suspicious": ["tidak saya lakukan", "transaksi aneh", "aktivitas mencurigakan"],
        },
    }

    def classify(self, subject: str, description: str) -> dict:
        """Classify ticket based on subject and description."""
        text = f"{subject} {description}".lower()

        for category, subcategories in self.KEYWORDS.items():
            for subcategory, keywords in subcategories.items():
                if any(kw in text for kw in keywords):
                    priority = self._get_default_priority(category)
                    return {
                        "category": category,
                        "subcategory": subcategory,
                        "priority": priority,
                        "confidence": "high",
                    }

        # Fallback: check for regulatory/complaint keywords
        if any(kw in text for kw in ["lapor", "pelanggaran", "report", "komplain"]):
            return {"category": "complaint", "subcategory": None, "priority": "normal", "confidence": "medium"}

        return {"category": "general", "subcategory": None, "priority": "normal", "confidence": "low"}

    def _get_default_priority(self, category: str) -> str:
        priorities = {
            "trade_dispute": "urgent",
            "kyc": "high",
            "payment": "urgent",
            "technical": "high",
            "security": "critical",
            "complaint": "normal",
        }
        return priorities.get(category, "normal")
```

---

## 4. Escalation Workflow

### 4.1 Tier Structure

```
┌─────────────────────────────────────────────────────────────┐
│                    ESCALATION TIERS                          │
│                                                             │
│  Tier 1: AI Chatbot                                         │
│  ├── Auto-resolve: FAQ, basic questions                     │
│  ├── Collect info: screenshots, error messages              │
│  ├── Escalate to Tier 2 if: complex, emotional, regulatory  │
│  └── ~60% of tickets auto-resolved                          │
│                                                             │
│  Tier 2: Support Agent (L1)                                 │
│  ├── Handle: most user issues                               │
│  ├── Tools: user account, order history, KYC status         │
│  ├── Escalate to Tier 3 if: trade dispute, regulatory,      │
│  │   security, or needs supervisor approval                 │
│  └── ~30% of tickets resolved at this tier                  │
│                                                             │
│  Tier 3: Senior Agent / Supervisor (L2)                     │
│  ├── Handle: complex disputes, compensation, regulatory     │
│  ├── Tools: partial refund, fee reversal, account freeze    │
│  ├── Escalate to Compliance if: regulatory violation,       │
│  │   large compensation, legal threat                       │
│  └── ~8% of tickets resolved at this tier                   │
│                                                             │
│  Tier 4: Compliance / Legal                                 │
│  ├── Handle: regulatory complaints, LAPS-SJK cases          │
│  ├── Tools: full investigation, OJK reporting               │
│  ├── Escalate to LAPS-SJK if: unresolved within 20 days     │
│  └── ~2% of tickets reach this tier                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Escalation Triggers

| Trigger | From | To | Condition |
|---------|------|-----|-----------|
| **Complexity** | Tier 1 | Tier 2 | Bot cannot resolve after 3 interactions |
| **Emotional** | Tier 1 | Tier 2 | Detect frustration/anger in language |
| **Regulatory** | Any | Tier 4 | Mention "OJK", "lapor", "pelanggaran", "pengaduan" |
| **Security** | Any | Tier 4 | Account takeover, suspicious activity |
| **SLA breach** | Tier 2 | Tier 3 | No response within SLA deadline |
| **Compensation** | Tier 2 | Tier 3 | Refund/credit > Rp 500,000 |
| **Unresolved** | Tier 3 | Tier 4 | No resolution after 2 business days |
| **LAPS-SJK** | Tier 4 | External | Unresolved after 20 business days |

### 4.3 Implementasi

```python
class EscalationManager:
    """Manage ticket escalation workflow."""

    ESCALATION_THRESHOLDS = {
        "bot_to_agent": 3,        # Max bot interactions before escalate
        "agent_to_supervisor": 4, # Hours without response
        "supervisor_to_compliance": 48,  # Hours unresolved
        "compliance_to_laps": 20,  # Business days unresolved
    }

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def check_escalation(self, ticket_id: str) -> dict | None:
        """Check if ticket needs escalation based on triggers."""
        ticket = self.storage.get_ticket(ticket_id)
        if not ticket or ticket["status"] in ("resolved", "closed"):
            return None

        current_level = ticket["escalation_level"]
        created = datetime.fromisoformat(ticket["created_at"])
        elapsed = datetime.now(UTC) - created

        # Check SLA breach
        if ticket["sla_deadline"] and datetime.now(UTC) > datetime.fromisoformat(ticket["sla_deadline"]):
            return self._escalate(ticket, reason="sla_breach")

        # Auto-escalate based on category + time
        if current_level == 0 and elapsed.total_seconds() > 3600:  # 1 hour
            if ticket["priority"] in ("urgent", "critical"):
                return self._escalate(ticket, reason="priority_timeout")

        if current_level == 1 and elapsed.total_seconds() > 14400:  # 4 hours
            return self._escalate(ticket, reason="agent_timeout")

        if current_level == 2 and elapsed.total_seconds() > 172800:  # 48 hours
            return self._escalate(ticket, reason="supervisor_timeout")

        # Check for regulatory keywords in latest message
        latest_msg = self.storage.get_latest_ticket_message(ticket_id)
        if latest_msg:
            if self._contains_regulatory_keywords(latest_msg["message"]):
                return self._escalate(ticket, reason="regulatory_keyword",
                                      target_level=3)

        return None

    def _escalate(self, ticket: dict, reason: str, target_level: int | None = None) -> dict:
        """Escalate ticket to next level."""
        current = ticket["escalation_level"]
        new_level = target_level if target_level is not None else current + 1

        self.storage.update_ticket(ticket["id"], {
            "escalation_level": new_level,
            "status": "escalated",
        })

        self.storage.add_ticket_audit(ticket["id"], {
            "action": "escalated",
            "actor": "system",
            "old_value": str(current),
            "new_value": str(new_level),
            "reason": reason,
        })

        # Notify appropriate team
        self._notify_escalation_team(ticket, new_level, reason)

        return {"ticket_id": ticket["id"], "new_level": new_level, "reason": reason}

    def _contains_regulatory_keywords(self, text: str) -> bool:
        keywords = ["ojk", "lapor", "pelanggaran", "pengaduan", "laps-sjk",
                     "dewan komisioner", "inspeksi", "audit ojk"]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)
```

---

## 5. SLA Management

### 5.1 SLA Matrix

| Priority | First Response | Resolution | Escalation |
|----------|---------------|------------|------------|
| **Critical** | 30 menit | 4 jam | Auto-escalate after 1 jam |
| **Urgent** | 1 jam | 8 jam | Auto-escalate after 2 jam |
| **High** | 2 jam | 24 jam | Auto-escalate after 4 jam |
| **Normal** | 8 jam | 3 hari | Auto-escalate after 1 hari |
| **Low** | 24 jam | 7 hari | No auto-escalation |

### 5.2 SLA Tracking

```python
class SLAManager:
    """Track and enforce SLA for support tickets."""

    SLA_CONFIG = {
        "critical": {"first_response_minutes": 30, "resolution_hours": 4},
        "urgent": {"first_response_minutes": 60, "resolution_hours": 8},
        "high": {"first_response_minutes": 120, "resolution_hours": 24},
        "normal": {"first_response_minutes": 480, "resolution_hours": 72},
        "low": {"first_response_minutes": 1440, "resolution_hours": 168},
    }

    def compute_sla_deadline(self, priority: str, created_at: datetime) -> datetime:
        """Compute SLA deadline for a ticket."""
        config = self.SLA_CONFIG.get(priority, self.SLA_CONFIG["normal"])
        return created_at + timedelta(hours=config["resolution_hours"])

    def check_sla_status(self, ticket: dict) -> dict:
        """Check if ticket is within SLA."""
        if ticket["status"] in ("resolved", "closed"):
            return {"status": "met", "breached": False}

        deadline = datetime.fromisoformat(ticket["sla_deadline"])
        now = datetime.now(UTC)
        remaining = deadline - now

        if remaining.total_seconds() < 0:
            return {
                "status": "breached",
                "breached": True,
                "overdue_by_minutes": abs(remaining.total_seconds()) / 60,
            }

        return {
            "status": "at_risk" if remaining.total_seconds() < 3600 else "on_track",
            "breached": False,
            "remaining_minutes": remaining.total_seconds() / 60,
        }
```

---

## 6. AI Chatbot dengan Guardrails

### 6.1 Guardrail Principles

| Principle | Implementasi |
|-----------|-------------|
| **Scripted disclosures** | Jawaban regulatory wajib pakai template, tidak boleh di-improvise |
| **Threshold blocks** | Bot tidak bisa authorize refund/credit > Rp 500K |
| **Escalation triggers** | Bot wajib escalate jika detect: marah, regulatory, security |
| **No financial advice** | Bot tidak boleh beri rekomendasi beli/jual saham |
| **PII protection** | Bot tidak display full NIK, nomor rekening, dll |
| **Audit trail** | Setiap bot interaction tercatat dengan reasoning |

### 6.2 Implementasi

```python
class SupportChatbot:
    """AI chatbot for Tier 1 support with guardrails."""

    # Guardrails
    MAX_AUTO_REFUND = 500_000  # Rp 500K
    ESCALATION_KEYWORDS = [
        "marah", "kecewa", "lapor", "ojk", "pengaduan", "pengacara",
        "tuntutan", "ganti rugi besar", "penipuan", "fraud",
    ]
    FORBIDDEN_ADVICE = [
        "beli", "jual", "rekomendasi saham", "investasi di",
        "hold", "cut loss", "average down",
    ]
    PII_PATTERNS = [
        r"\b\d{16}\b",  # NIK
        r"\b\d{10,16}\b",  # Account numbers
    ]

    def __init__(self, storage: DataStorage, llm_client):
        self.storage = storage
        self.llm = llm_client

    def respond(self, user_id: str, ticket_id: str, message: str) -> dict:
        """Generate response with guardrail checks."""
        # 1. Check for escalation triggers
        if self._needs_escalation(message):
            return self._escalate_to_agent(ticket_id, reason="escalation_keyword")

        # 2. Check for forbidden financial advice
        if self._is_financial_advice_request(message):
            return {
                "response": "Saya tidak dapat memberikan rekomendasi investasi. "
                           "Untuk analisis saham, silakan gunakan fitur Screener "
                           "atau Decision Engine di aplikasi.",
                "action": "blocked_advice",
            }

        # 3. Mask PII in message
        masked_message = self._mask_pii(message)

        # 4. Generate response via LLM
        context = self._build_context(user_id, ticket_id)
        response = self.llm.generate(masked_message, context)

        # 5. Check response for compliance
        if self._response_has_issues(response):
            return self._escalate_to_agent(ticket_id, reason="response_compliance_check")

        # 6. Check if auto-resolve is possible
        if self._can_auto_resolve(message, response):
            return {
                "response": response,
                "action": "auto_resolve",
                "resolved": True,
            }

        return {"response": response, "action": "continue"}

    def _needs_escalation(self, message: str) -> bool:
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in self.ESCALATION_KEYWORDS)

    def _is_financial_advice_request(self, message: str) -> bool:
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in self.FORBIDDEN_ADVICE)

    def _mask_pii(self, message: str) -> str:
        import re
        for pattern in self.PII_PATTERNS:
            message = re.sub(pattern, "[REDACTED]", message)
        return message

    def _can_auto_resolve(self, message: str, response: str) -> bool:
        """Determine if ticket can be auto-resolved."""
        # Auto-resolve only for FAQ-type questions
        auto_resolve_keywords = ["terima kasih", "sudah jelas", "paham", "ok", "baik"]
        return any(kw in message.lower() for kw in auto_resolve_keywords)
```

---

## 7. Dispute Resolution & LAPS-SJK

### 7.1 Alur Penyelesaian Sengketa

```
┌──────────────────────────────────────────────────────────────┐
│              DISPUTE RESOLUTION FLOW                         │
│                                                              │
│  1. Konsumen ajukan pengaduan                                │
│     ↓                                                        │
│  2. Penyedia layanan respon (maks 5 hari kerja)              │
│     ↓                                                        │
│  3. Investigasi & penyelesaian (maks 20 hari kerja)          │
│     ├─ Terselesaikan → Notifikasi hasil → Close ticket       │
│     │                                                        │
│     └─ Tidak terselesaikan → Eskalasi ke LAPS-SJK           │
│         ↓                                                    │
│  4. LAPS-SJK mediasi                                         │
│     ├─ Mediasi berhasil → Eksekusi kesepakatan               │
│     │                                                        │
│     └─ Mediasi gagal → Konsumen dapat ke pengadilan         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 7.2 LAPS-SJK Integration

```python
class LAPSSJKIntegration:
    """Integration with LAPS-SJK for dispute escalation."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def escalate_to_laps(self, ticket_id: str) -> dict:
        """Escalate unresolved ticket to LAPS-SJK."""
        ticket = self.storage.get_ticket(ticket_id)
        if not ticket:
            return {"status": "error", "message": "Ticket not found"}

        # Check if ticket has been open for 20 business days
        created = datetime.fromisoformat(ticket["created_at"])
        business_days = self._count_business_days(created, datetime.now(UTC))

        if business_days < 20:
            return {
                "status": "error",
                "message": f"Ticket must be open for 20 business days before LAPS-SJK escalation. Current: {business_days} days."
            }

        # Prepare LAPS-SJK submission
        submission = {
            "ticket_number": ticket["ticket_number"],
            "user_id": ticket["user_id"],
            "user_name": self.storage.get_user_name(ticket["user_id"]),
            "complaint_summary": ticket["subject"],
            "complaint_detail": ticket["description"],
            "attempted_resolution": self._get_resolution_history(ticket_id),
            "compensation_requested": self._get_compensation_requested(ticket_id),
            "submission_date": datetime.now(UTC).isoformat(),
        }

        # Submit to LAPS-SJK (API or manual)
        laps_ref = self._submit_to_laps(submission)

        self.storage.update_ticket(ticket_id, {
            "laps_sjk_ref": laps_ref,
            "status": "laps_sjk_escalated",
        })

        return {"status": "escalated", "laps_sjk_ref": laps_ref}

    def _count_business_days(self, start: datetime, end: datetime) -> int:
        """Count business days between two dates (excluding weekends & holidays)."""
        days = 0
        current = start.date()
        holidays = self.storage.get_market_holidays()
        while current < end.date():
            if current.weekday() < 5 and current not in holidays:
                days += 1
            current += timedelta(days=1)
        return days
```

---

## 8. Knowledge Base & FAQ

### 8.1 Knowledge Base Structure

| Kategori | Artikel | Contoh |
|----------|---------|--------|
| **Getting Started** | 10-15 | Cara buka akun, verifikasi KYC, link RDN |
| **Trading** | 15-20 | Cara beli saham, order type, auto-reject, tick size |
| **Portfolio** | 10-15 | Cara lihat PnL, dividend, corporate action |
| **Payment** | 10-15 | Cara deposit, withdrawal, biaya transaksi |
| **Security** | 5-10 | Cara aktifkan 2FA, secure akun, phishing awareness |
| **Syariah** | 10-15 | Cara aktifkan Sharia Mode, DES, zakat |
| **Tax** | 5-10 | PPh final 0.1%, pajak dividen, SPT |
| **Technical** | 10-15 | Troubleshooting app, update, device compatibility |

### 8.2 FAQ Auto-Suggest

```python
class FAQAutoSuggest:
    """Auto-suggest FAQ articles based on user message."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def suggest(self, message: str, limit: int = 3) -> list[dict]:
        """Suggest relevant FAQ articles based on message content."""
        articles = self.storage.get_published_articles()
        scored = []

        for article in articles:
            score = self._compute_relevance(message, article)
            if score > 0.3:
                scored.append((article, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [{"id": a["id"], "title": a["title"], "score": s}
                for a, s in scored[:limit]]

    def _compute_relevance(self, message: str, article: dict) -> float:
        """Compute relevance score between message and article."""
        msg_words = set(message.lower().split())
        title_words = set(article["title"].lower().split())
        tag_words = set(t.lower() for t in article.get("tags", []))

        title_overlap = len(msg_words & title_words) / max(len(title_words), 1)
        tag_overlap = len(msg_words & tag_words) / max(len(tag_words), 1)

        return (title_overlap * 0.6) + (tag_overlap * 0.4)
```

---

## 9. Audit Trail & Compliance

### 9.1 What to Log

| Event | Data yang Dicatat |
|-------|-------------------|
| Ticket created | Timestamp, user, channel, category, priority |
| Ticket assigned | Agent ID, timestamp |
| Message sent | Sender, content (hashed for PII), timestamp |
| Status changed | Old status, new status, actor, timestamp |
| Escalation | From level, to level, reason, timestamp |
| Resolution | Resolution type, compensation, agent, timestamp |
| LAPS-SJK escalation | Reference number, submission date |
| User satisfaction | CSAT score, feedback, timestamp |

### 9.2 Reporting ke OJK

```python
class OJKReportingService:
    """Generate periodic reports for OJK compliance."""

    def generate_monthly_report(self, month: str) -> dict:
        """Generate monthly consumer complaint report for OJK."""
        tickets = self.storage.get_tickets_by_month(month)

        report = {
            "reporting_period": month,
            "total_complaints": len(tickets),
            "by_category": {},
            "by_priority": {},
            "resolution_stats": {
                "resolved_within_sla": 0,
                "resolved_outside_sla": 0,
                "escalated_to_laps": 0,
                "unresolved": 0,
            },
            "average_resolution_time_hours": 0,
            "compensation_paid": 0,
            "recurring_issues": [],
        }

        for ticket in tickets:
            cat = ticket["category"]
            report["by_category"][cat] = report["by_category"].get(cat, 0) + 1
            pri = ticket["priority"]
            report["by_priority"][pri] = report["by_priority"].get(pri, 0) + 1

            if ticket["status"] == "resolved":
                if ticket["resolved_at"] and ticket["sla_deadline"]:
                    if datetime.fromisoformat(ticket["resolved_at"]) <= datetime.fromisoformat(ticket["sla_deadline"]):
                        report["resolution_stats"]["resolved_within_sla"] += 1
                    else:
                        report["resolution_stats"]["resolved_outside_sla"] += 1
            elif ticket.get("laps_sjk_ref"):
                report["resolution_stats"]["escalated_to_laps"] += 1
            else:
                report["resolution_stats"]["unresolved"] += 1

        return report
```

---

## 10. Implementasi

### 10.1 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/support/tickets` | POST | Create ticket |
| `/api/support/tickets` | GET | List user tickets |
| `/api/support/tickets/{id}` | GET | Get ticket detail |
| `/api/support/tickets/{id}/messages` | GET | Get conversation |
| `/api/support/tickets/{id}/messages` | POST | Reply to ticket |
| `/api/support/tickets/{id}/escalate` | POST | Escalate ticket |
| `/api/support/tickets/{id}/resolve` | POST | Resolve ticket (agent) |
| `/api/support/tickets/{id}/close` | POST | Close ticket (user/agent) |
| `/api/support/tickets/{id}/satisfaction` | POST | Submit CSAT |
| `/api/support/chatbot` | POST | Chatbot interaction |
| `/api/support/kb` | GET | Search knowledge base |
| `/api/support/kb/{id}` | GET | Get article |
| `/api/support/kb/{id}/vote` | POST | Vote helpful/unhelpful |
| `/api/support/faq/suggest` | GET | Auto-suggest FAQ |
| `WS /ws/support` | WS | Real-time chat |

---

## 11. Adopsi dari Codebase Existing

| Module Existing | Modifikasi |
|----------------|-----------|
| `api/app.py` | Tambah support endpoints |
| `data/storage.py` | Tambah ticket tables |
| `monitoring/engine.py` | Tambah SLA monitoring alert |
| `utils/telegram.py` | Tambah alert untuk critical tickets |

**New modules:**
- `support/ticketing.py` — Ticket management
- `support/classifier.py` — Auto-classification
- `support/escalation.py` — Escalation workflow
- `support/chatbot.py` — AI chatbot dengan guardrails
- `support/sla.py` — SLA management
- `support/laps_sjk.py` — LAPS-SJK integration
- `support/kb.py` — Knowledge base
- `support/ojk_report.py` — OJK reporting

---

## 12. Checklist Implementasi

### Phase 1: Core Ticketing (3-4 minggu)

- [ ] Database schema: tickets, messages, audit
- [ ] `TicketManager` class (CRUD)
- [ ] `TicketClassifier` (auto-classification)
- [ ] API: ticket CRUD + messages
- [ ] In-app chat UI

### Phase 2: Escalation & SLA (2-3 minggu)

- [ ] `EscalationManager` (tier-based)
- [ ] `SLAManager` (tracking + alerts)
- [ ] Auto-escalation rules
- [ ] Agent dashboard

### Phase 3: AI Chatbot (3-4 minggu)

- [ ] `SupportChatbot` dengan guardrails
- [ ] FAQ auto-suggest
- [ ] Knowledge base CRUD
- [ ] Bot-to-agent handoff

### Phase 4: Compliance (2-3 minggu)

- [ ] LAPS-SJK integration
- [ ] OJK monthly reporting
- [ ] Audit trail verification
- [ ] CSAT collection

---

## Referensi

### Internal
- `38-manajemen-aplikasi-ritel.md` — Manajemen aplikasi ritel (admin module)
- `33-cybersecurity-trading-system.md` — Cybersecurity
- `41-uu-pdp-compliance-fintech.md` — UU PDP compliance
- `10-regulasi-pasar-modal.md` — Regulasi pasar modal

### External
- POJK 22/2023 — Perlindungan konsumen jasa keuangan
- SEOJK 23/2023 — Penyelesaian pengaduan konsumen
- LAPS-SJK — Lembaga Alternatif Penyelesaian Sengketa Sektor Jasa Keuangan
- Lorikeet AI — AI support for fintech (guardrails, audit trail)

---

> **Catatan:** Customer support di trading app bukan generic CX. Setiap tiket adalah regulated interaction yang butuh audit trail. AI chatbot wajib punya guardrails: tidak boleh beri financial advice, tidak boleh authorize refund besar, dan wajib escalate untuk keyword regulatory.
