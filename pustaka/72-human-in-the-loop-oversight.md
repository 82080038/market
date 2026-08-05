# Human-in-the-Loop: Oversight untuk Self-Evolving AI

> **Dokumen 72** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Sistem human-in-the-loop yang memastikan manusia tetap memiliki kontrol atas self-evolving AI — approval gates, escalation policies, notification strategy, dan kill switch — sehingga self-evolution berjalan aman dan terkendali.
>
> **Konteks:** Dokumen 67-71 mendefinisikan arsitektur self-evolving AI yang otonom. Tapi otonomi penuh berisiko terlalu tinggi untuk sistem trading yang menangani uang nyata. Dokumen ini mendefinisikan boundary antara otonomi AI dan kontrol manusia, terinspirasi dari praktik safety pada Darwin Gödel Machine ("safety precautions: sandboxing, human oversight") dan AHE ("human oversight").

---

## Daftar Isi

1. [Mengapa Human-in-the-Loop Wajib](#1-mengapa-human-in-the-loop-wajib)
2. [Approval Gate Architecture](#2-approval-gate-architecture)
3. [Risk Classification](#3-risk-classification)
4. [Escalation Policy](#4-escalation-policy)
5. [Notification Strategy](#5-notification-strategy)
6. [Kill Switch](#6-kill-switch)
7. [Audit & Compliance](#7-audit--compliance)
8. [Database Schema](#8-database-schema)
9. [Implementasi Kode](#9-implementasi-kode)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Mengapa Human-in-the-Loop Wajib

### 1.1 Risiko Otonomi Penuh

| Risiko | Contoh | Dampak |
|--------|--------|--------|
| **Financial loss** | AI generate strategi yang overfit → live trading loss | Loss uang nyata |
| **Regulatory violation** | AI generate strategi yang melanggar OJK rules | Sanksi, denda |
| **Data corruption** | AI generate adapter yang corrupt database | Data hilang, tidak konsisten |
| **Security vulnerability** | AI generate code dengan backdoor/injection | Data leakage, hack |
| **Cascading failure** | AI fix satu bug tapi introduce bug lain | Sistem rusak berantai |
| **Unintended behavior** | AI optimasi metric yang salah | "Gaming the metric" |
| **Hallucination** | AI generate code yang terlihat benar tapi subtle bug | Silent error |

### 1.2 Prinsip

| Prinsip | Deskripsi |
|---------|-----------|
| **Otonomi bertingkat** | AI otonom untuk low-risk, human approval untuk high-risk |
| **Default deny** | Jika tidak yakin risk level, anggap high-risk → require approval |
| **Transparent** | Setiap approval request punya context lengkap (what, why, metrics) |
| **Reversible** | Setiap approved change punya rollback path |
| **Time-boxed** | Approval request expire setelah N jam → auto-reject |
| **Auditable** | Setiap approval/rejection tercatat dengan reason |
| **Kill switch always** | Human dapat stop self-evolution kapan saja |

### 1.3 Inspirasi dari Riset

| Sumber | Insight |
|--------|---------|
| **Darwin Gödel Machine (2025)** | "All experiments were done with safety precautions (e.g., sandboxing, human oversight)" |
| **AHE (2026)** | Human oversight sebagai komponen eksplisit dalam evolution loop |
| **AutoDev (2026)** | "Only `agents/*.py` prompt strings are editable; structural files are off-limits to keep self-modification bounded" |
| **SelfEvolve (2026)** | Process isolation sebagai safety layer, bukan human approval |

---

## 2. Approval Gate Architecture

### 2.1 Overview

```
SELF-EVOLUTION CYCLE
    │
    ├── Monitor → Analyze → Build → Validate
    │
    ▼
EVAL-GATED PROMOTION (dokumen 71)
    │
    ├── Recommendation: "promote"
    │
    ▼
RISK CLASSIFICATION
    │
    ├── LOW RISK ──▶ AUTO-PROMOTE (no human needed)
    │                   │
    │                   └── Audit log + Telegram notification
    │
    ├── MEDIUM RISK ──▶ NOTIFICATION + 30min AUTO-PROMOTE
    │                   │
    │                   ├── Human dapat reject dalam 30 menit
    │                   └── Jika tidak reject → auto-promote
    │
    ├── HIGH RISK ──▶ HUMAN APPROVAL REQUIRED
    │                   │
    │                   ├── Telegram: approval request dengan details
    │                   ├── Human approve → promote
    │                   ├── Human reject → discard
    │                   └── Timeout 24 jam → auto-reject
    │
    └── CRITICAL ──▶ HUMAN APPROVAL + CONFIRMATION
                        │
                        ├── Telegram: approval request
                        ├── Human approve (1st) → confirmation request
                        ├── Human confirm (2nd) → promote
                        ├── Human reject → discard
                        └── Timeout 48 jam → auto-reject
```

### 2.2 Approval Gate dalam Orchestrator

```python
# self_evolution/orchestrator.py (extension dari dokumen 67)

class ApprovalGate:
    """Gate yang menentukan apakah perubahan perlu human approval."""

    def __init__(self, telegram_notifier, db_path: str):
        self.telegram = telegram_notifier
        self.db_path = db_path
        self.timeout_low = 0          # No timeout — auto
        self.timeout_medium = 30 * 60  # 30 menit
        self.timeout_high = 24 * 3600  # 24 jam
        self.timeout_critical = 48 * 3600  # 48 jam

    def gate(self, analysis, validation, eval_result) -> dict:
        """
        Determine if change needs human approval.
        
        Returns: {action: "auto_promote"|"notify"|"require_approval"|"require_confirmation",
                  risk_level, timeout_seconds}
        """
        risk = self._classify_risk(analysis, validation, eval_result)

        if risk == "low":
            return {"action": "auto_promote", "risk_level": risk, "timeout": 0}

        elif risk == "medium":
            return {"action": "notify", "risk_level": risk,
                    "timeout": self.timeout_medium}

        elif risk == "high":
            return {"action": "require_approval", "risk_level": risk,
                    "timeout": self.timeout_high}

        elif risk == "critical":
            return {"action": "require_confirmation", "risk_level": risk,
                    "timeout": self.timeout_critical}

        # Default: treat as high risk
        return {"action": "require_approval", "risk_level": "high",
                "timeout": self.timeout_high}
```

---

## 3. Risk Classification

### 3.1 Risk Matrix

| Solution Type | Impact Area | Risk Level | Approval |
|---------------|-------------|------------|----------|
| **fix_bug** (adapter) | Data fetching | Low | Auto-promote |
| **fix_bug** (scraper) | Data scraping | Low | Auto-promote |
| **fix_bug** (indicator) | Analysis | Medium | Notify + auto |
| **fix_bug** (decision engine) | Trading decisions | High | Approval required |
| **fix_bug** (risk engine) | Risk management | Critical | Approval + confirm |
| **fix_bug** (execution) | Order execution | Critical | Approval + confirm |
| **add_adapter** (new data source) | Data acquisition | Low | Auto-promote |
| **add_feature** (new indicator) | Analysis | Medium | Notify + auto |
| **add_feature** (new screener) | Screening | Low | Auto-promote |
| **new_strategy** | Trading decisions | High | Approval required |
| **optimize_model** (LSTM) | Prediction | Medium | Notify + auto |
| **optimize_model** (weight) | Decision scoring | High | Approval required |
| **optimize_model** (risk params) | Risk management | Critical | Approval + confirm |

### 3.2 Risk Scoring

```python
# self_evolution/human_loop/risk_classifier.py
from dataclasses import dataclass
from typing import Any

@dataclass
class RiskAssessment:
    risk_level: str  # low, medium, high, critical
    score: int       # 0-100
    factors: dict[str, Any]
    reasoning: str

class RiskClassifier:
    """Classify risk level untuk self-evolution changes."""

    # Impact weights
    IMPACT_WEIGHTS = {
        "data_fetching": 10,
        "data_scraping": 15,
        "analysis": 30,
        "screening": 20,
        "prediction": 35,
        "decision_scoring": 60,
        "trading_decisions": 70,
        "risk_management": 85,
        "order_execution": 95,
        "portfolio_management": 75,
        "compliance": 90,
    }

    # Solution type multipliers
    TYPE_MULTIPLIERS = {
        "fix_bug": 0.8,       # Fixing existing — less risky
        "add_adapter": 0.5,   # Adding data source — low risk
        "add_feature": 0.7,   # Adding capability — moderate
        "new_strategy": 1.0,  # New strategy — full risk
        "optimize_model": 0.9, # Optimization — high risk
    }

    def classify(self, analysis, validation, eval_result) -> RiskAssessment:
        """Classify risk untuk proposed change."""
        # 1. Base score dari impact area
        impact_area = analysis.code_spec.get("impact_area", "analysis")
        base_score = self.IMPACT_WEIGHTS.get(impact_area, 30)

        # 2. Multiply by solution type
        type_mult = self.TYPE_MULTIPLIERS.get(analysis.solution_type, 1.0)
        score = int(base_score * type_mult)

        # 3. Adjust berdasarkan validation metrics
        if validation.metrics.get("sharpe", 0) > 2.0:
            score += 10  # Very high Sharpe → suspicious, might be overfit
        if validation.metrics.get("max_drawdown", 0) < -0.3:
            score += 15  # High drawdown → risky
        if eval_result.recommendation == "inconclusive":
            score += 20  # Inconclusive → more risk

        # 4. Adjust berdasarkan falsification
        falsif = eval_result.layer_results.get("falsification", {})
        if not falsif.get("passed", True):
            score += 30  # Falsification failed → very risky

        # 5. Clamp
        score = max(0, min(100, score))

        # 6. Determine risk level
        if score < 25:
            level = "low"
        elif score < 50:
            level = "medium"
        elif score < 75:
            level = "high"
        else:
            level = "critical"

        return RiskAssessment(
            risk_level=level,
            score=score,
            factors={
                "impact_area": impact_area,
                "solution_type": analysis.solution_type,
                "base_score": base_score,
                "type_multiplier": type_mult,
                "sharpe": validation.metrics.get("sharpe", 0),
                "max_drawdown": validation.metrics.get("max_drawdown", 0),
                "falsification_passed": falsif.get("passed", True),
            },
            reasoning=f"Impact: {impact_area} ({base_score}), Type: {analysis.solution_type} (×{type_mult}), Adjusted: {score} → {level}",
        )
```

---

## 4. Escalation Policy

### 4.1 Escalation Triggers

| Trigger | Action | Notify |
|---------|--------|--------|
| **3 consecutive build failures** | Pause self-evolution, human review | Telegram: "Builder stuck" |
| **5 consecutive validation failures** | Pause, review LLM prompt quality | Telegram: "Validator stuck" |
| **2 consecutive rollback after promote** | Disable auto-promote, require all approvals | Telegram: "Unstable changes" |
| **Critical risk change detected** | Require double confirmation | Telegram: "Critical change pending" |
| **Kill switch activated** | Stop all self-evolution immediately | Telegram: "KILL SWITCH ACTIVATED" |
| **LLM API cost > budget** | Pause, wait for budget reset | Telegram: "Budget exceeded" |
| **Sandbox security breach** | Stop all, human investigation | Telegram: "SECURITY ALERT" |

### 4.2 Escalation Levels

```
Level 0: Normal operation
    └── AI otonom untuk low-risk changes

Level 1: Caution (3 failures)
    └── All changes require notification (no auto-promote)

Level 2: Warning (5 failures or 2 rollbacks)
    └── All changes require explicit human approval

Level 3: Critical (security breach or kill switch)
    └── Self-evolution completely stopped
    └── Human investigation required
    └── Manual restart needed
```

### 4.3 Implementation

```python
# self_evolution/human_loop/escalation.py
from dataclasses import dataclass
from enum import IntEnum

class EscalationLevel(IntEnum):
    NORMAL = 0
    CAUTION = 1
    WARNING = 2
    CRITICAL = 3

@dataclass
class EscalationState:
    level: EscalationLevel
    consecutive_failures: int = 0
    consecutive_rollbacks: int = 0
    last_escalation: str = ""
    kill_switch_active: bool = False

class EscalationManager:
    """Manage escalation levels untuk self-evolution."""

    def __init__(self, telegram_notifier, db_path: str):
        self.telegram = telegram_notifier
        self.db_path = db_path
        self.state = EscalationState(level=EscalationLevel.NORMAL)

    def record_failure(self, stage: str, reason: str):
        """Record failure dan update escalation level."""
        self.state.consecutive_failures += 1

        if self.state.consecutive_failures >= 5:
            self._escalate(EscalationLevel.WARNING,
                           f"5 consecutive failures at {stage}")
        elif self.state.consecutive_failures >= 3:
            self._escalate(EscalationLevel.CAUTION,
                           f"3 consecutive failures at {stage}")

    def record_success(self):
        """Record success, reset failure counter."""
        self.state.consecutive_failures = 0
        if self.state.level == EscalationLevel.CAUTION:
            self._de_escalate()

    def record_rollback(self, reason: str):
        """Record rollback after promotion."""
        self.state.consecutive_rollbacks += 1

        if self.state.consecutive_rollbacks >= 2:
            self._escalate(EscalationLevel.WARNING,
                           "2 consecutive rollbacks — unstable changes")

    def activate_kill_switch(self, reason: str):
        """Activate kill switch — stop all self-evolution."""
        self.state.kill_switch_active = True
        self.state.level = EscalationLevel.CRITICAL
        self._notify(f"🚨 KILL SWITCH ACTIVATED: {reason}")
        self._log_escalation("kill_switch", reason)

    def deactivate_kill_switch(self):
        """Deactivate kill switch — manual reset."""
        self.state.kill_switch_active = False
        self.state.level = EscalationLevel.NORMAL
        self.state.consecutive_failures = 0
        self.state.consecutive_rollbacks = 0
        self._notify("✅ Kill switch deactivated — self-evolution resumed")
        self._log_escalation("kill_switch_reset", "Manual reset")

    def can_auto_promote(self) -> bool:
        """Cek apakah auto-promote diizinkan."""
        if self.state.kill_switch_active:
            return False
        if self.state.level >= EscalationLevel.WARNING:
            return False
        return True

    def _escalate(self, level: EscalationLevel, reason: str):
        """Escalate ke level yang lebih tinggi."""
        if level > self.state.level:
            self.state.level = level
            self.state.last_escalation = reason
            level_name = level.name
            self._notify(f"⚠️ Escalation to {level_name}: {reason}")
            self._log_escalation(level_name.lower(), reason)

    def _de_escalate(self):
        """De-escalate ke level yang lebih rendah."""
        if self.state.level > EscalationLevel.NORMAL:
            self.state.level = EscalationLevel(self.state.level - 1)
            self._notify(f"↓ De-escalated to {self.state.level.name}")

    def _notify(self, message: str):
        """Send Telegram notification."""
        # self.telegram.send(message)
        pass

    def _log_escalation(self, level: str, reason: str):
        """Log escalation ke database."""
        pass
```

---

## 5. Notification Strategy

### 5.1 Notification Types

| Type | Channel | Priority | Content |
|------|---------|----------|---------|
| **Auto-promote** | Telegram | Low | "✅ Auto-promoted: {module} (risk: low)" |
| **Pending approval** | Telegram | High | "🔔 Approval needed: {description} (risk: {level})" |
| **Critical pending** | Telegram + Sound | Critical | "🚨 CRITICAL: {description} — double confirmation required" |
| **Promoted** | Telegram | Medium | "✅ Promoted: {module} — Sharpe: {before} → {after}" |
| **Rejected** | Telegram | Low | "❌ Rejected: {reason}" |
| **Rolled back** | Telegram | High | "⚠️ Rolled back: {module} — reason: {reason}" |
| **Escalation** | Telegram | High | "⚠️ Escalation: {level} — {reason}" |
| **Kill switch** | Telegram + Sound | Critical | "🚨 KILL SWITCH: {reason}" |

### 5.2 Telegram Message Format

```
🔔 APPROVAL REQUIRED — Self-Evolution

📊 Change: Optimize LSTM model for BBCA.JK
🎯 Type: optimize_model
⚠️ Risk: HIGH (score: 65/100)
📈 Metrics:
   Sharpe: 1.2 → 1.8 (+50%)
   Max DD: -15% → -12% (+20%)
   Win Rate: 52% → 58% (+6%)
🔍 Validation: 7/7 layers passed
🧪 Falsification: All passed
⏰ Expires: 24 jam dari sekarang

Reply:
  /approve {trigger_id} — Approve
  /reject {trigger_id} — Reject
  /details {trigger_id} — Full details
```

### 5.3 Implementation

```python
# self_evolution/human_loop/notifications.py
from dataclasses import dataclass
from typing import Any

@dataclass
class ApprovalRequest:
    trigger_id: str
    description: str
    risk_level: str
    risk_score: int
    metrics_before: dict[str, float]
    metrics_after: dict[str, float]
    validation_summary: dict[str, Any]
    timeout_seconds: int
    created_at: str
    status: str = "pending"  # pending, approved, rejected, expired

class NotificationManager:
    """Manage notifications ke human via Telegram."""

    def __init__(self, telegram_token: str, chat_id: str):
        self.token = telegram_token
        self.chat_id = chat_id

    def send_approval_request(self, request: ApprovalRequest):
        """Send approval request via Telegram."""
        message = self._format_approval_message(request)
        self._send_telegram(message)

    def send_auto_promote_notification(self, trigger_id: str, module: str,
                                        risk: str, metrics: dict):
        """Send notification untuk auto-promote."""
        message = (
            f"✅ Auto-promoted: {module}\n"
            f"   Risk: {risk}\n"
            f"   Sharpe: {metrics.get('sharpe', 'N/A')}\n"
            f"   Trigger: {trigger_id}"
        )
        self._send_telegram(message)

    def send_rollback_notification(self, module: str, reason: str):
        """Send notification untuk rollback."""
        message = f"⚠️ Rolled back: {module}\n   Reason: {reason}"
        self._send_telegram(message)

    def send_kill_switch(self, reason: str):
        """Send kill switch alert."""
        message = f"🚨 KILL SWITCH ACTIVATED\n   Reason: {reason}\n"
        message += "   Self-evolution STOPPED. Manual reset required."
        self._send_telegram(message)

    def _format_approval_message(self, request: ApprovalRequest) -> str:
        """Format approval request message."""
        metrics_lines = []
        for key in ["sharpe", "max_drawdown", "win_rate", "profit_factor"]:
            before = request.metrics_before.get(key, "N/A")
            after = request.metrics_after.get(key, "N/A")
            if isinstance(before, float) and isinstance(after, float):
                change = ((after - before) / abs(before) * 100) if before != 0 else 0
                metrics_lines.append(f"   {key}: {before:.2f} → {after:.2f} ({change:+.0f}%)")
            else:
                metrics_lines.append(f"   {key}: {before} → {after}")

        hours = request.timeout_seconds // 3600
        return (
            f"🔔 APPROVAL REQUIRED — Self-Evolution\n\n"
            f"📊 Change: {request.description}\n"
            f"⚠️ Risk: {request.risk_level.upper()} (score: {request.risk_score}/100)\n"
            f"📈 Metrics:\n" + "\n".join(metrics_lines) + "\n"
            f"🔍 Validation: {request.validation_summary.get('layers_passed', '?')}/"
            f"{request.validation_summary.get('layers_total', '?')} layers passed\n"
            f"⏰ Expires: {hours} jam dari sekarang\n\n"
            f"Reply:\n"
            f"  /approve {request.trigger_id}\n"
            f"  /reject {request.trigger_id}\n"
            f"  /details {request.trigger_id}"
        )

    def _send_telegram(self, message: str):
        """Send message via Telegram Bot API."""
        import requests
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        requests.post(url, json={
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        })
```

---

## 6. Kill Switch

### 6.1 Konsep

Kill switch adalah **emergency stop** yang dapat diaktifkan manusia kapan saja untuk menghentikan seluruh self-evolution activity.

### 6.2 Activation Methods

| Method | Speed | Use Case |
|--------|-------|----------|
| **Telegram command** | < 5 detik | `/kill` dari phone |
| **CLI command** | < 2 detik | `self-evolve --kill` dari terminal |
| **API endpoint** | < 1 detik | `POST /api/self-evolution/kill` |
| **File flag** | < 1 detik | `touch .kill_switch` |
| **Env var** | restart | `SELF_EVOLUTION_ENABLED=false` |

### 6.3 Implementation

```python
# self_evolution/human_loop/kill_switch.py
import os
from pathlib import Path

class KillSwitch:
    """Kill switch untuk emergency stop self-evolution."""

    KILL_FILE = ".kill_switch"

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._state = False

    def is_active(self) -> bool:
        """Cek apakah kill switch aktif."""
        # Check file flag
        if Path(self.KILL_FILE).exists():
            return True
        # Check env var
        if os.environ.get("SELF_EVOLUTION_ENABLED", "true").lower() == "false":
            return True
        # Check DB state
        return self._check_db_state()

    def activate(self, reason: str = "Manual activation"):
        """Activate kill switch."""
        Path(self.KILL_FILE).touch()
        self._save_db_state(True, reason)
        # Also stop auto-trading untuk safety
        os.environ["AUTO_TRADE_ENABLED"] = "false"

    def deactivate(self, reason: str = "Manual reset"):
        """Deactivate kill switch."""
        if Path(self.KILL_FILE).exists():
            Path(self.KILL_FILE).unlink()
        self._save_db_state(False, reason)

    def _check_db_state(self) -> bool:
        """Check kill switch state dari database."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT value FROM system_state WHERE key = 'self_evolution_kill_switch'"
        )
        row = cursor.fetchone()
        conn.close()
        return row is not None and row[0] == "true"

    def _save_db_state(self, active: bool, reason: str):
        """Save kill switch state ke database."""
        import sqlite3
        from datetime import datetime, timezone
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO system_state (key, value, updated_at, updated_by)
               VALUES ('self_evolution_kill_switch', ?, ?, ?)""",
            ("true" if active else "false",
             datetime.now(timezone.utc).isoformat(),
             f"kill_switch: {reason}")
        )
        conn.commit()
        conn.close()
```

---

## 7. Audit & Compliance

### 7.1 Audit Trail untuk Self-Evolution

Setiap self-evolution event wajib tercatat di `audit_log` (table existing) dengan:

| Field | Value |
|-------|-------|
| `event_type` | `self_evolution.*` (e.g. `self_evolution.promote`, `self_evolution.rollback`) |
| `payload` | JSON: trigger_id, module, risk_level, metrics, approval |
| `actor` | `builder_agent`, `integrator_agent`, `human:<name>` |
| `timestamp` | UTC ISO format |

### 7.2 Compliance Checklist

- [ ] Setiap self-modification tercatat di audit_log (immutable)
- [ ] Setiap approval/rejection tercatat dengan reason
- [ ] Setiap rollback tercatat dengan cause
- [ ] Kill switch activation tercatat
- [ ] Escalation events tercatat
- [ ] LLM API calls tercatat (cost tracking)
- [ ] Human dapat export audit log untuk review
- [ ] Audit log tidak bisa di-modify oleh AI (append-only)

---

## 8. Database Schema

```sql
-- Approval requests
CREATE TABLE IF NOT EXISTS evolution_approvals (
    approval_id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    description TEXT NOT NULL,
    metrics_before TEXT,              -- JSON
    metrics_after TEXT,               -- JSON
    validation_summary TEXT,          -- JSON
    status TEXT DEFAULT 'pending',    -- pending, approved, rejected, expired, auto_promoted
    timeout_seconds INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,                  -- human:<name>, auto:low_risk, auto:timeout
    decision_reason TEXT,
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);

-- Escalation log
CREATE TABLE IF NOT EXISTS escalation_log (
    escalation_id TEXT PRIMARY KEY,
    level TEXT NOT NULL,              -- caution, warning, critical
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT
);

-- Kill switch state (juga di system_state table existing)
-- system_state key: 'self_evolution_kill_switch', value: 'true'/'false'

-- LLM API cost tracking
CREATE TABLE IF NOT EXISTS llm_api_costs (
    cost_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,         -- analyzer, builder
    llm_model TEXT NOT NULL,          -- gpt-4o, claude-sonnet, dll
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    trigger_id TEXT,
    created_at TEXT NOT NULL
);
```

---

## 9. Implementasi Kode

### 9.1 Module Structure

```
src/trading_system/self_evolution/human_loop/
├── __init__.py
├── approval_gate.py       # ApprovalGate
├── risk_classifier.py     # RiskClassifier
├── escalation.py          # EscalationManager
├── notifications.py       # NotificationManager
├── kill_switch.py         # KillSwitch
└── audit.py               # SelfEvolutionAudit
```

### 9.2 Telegram Bot Handler

```python
# self_evolution/human_loop/telegram_handler.py
import json
import sqlite3
from datetime import datetime, timezone

class TelegramApprovalHandler:
    """Handle approval responses dari Telegram."""

    def __init__(self, db_path: str, telegram_token: str):
        self.db_path = db_path
        self.token = telegram_token

    def handle_command(self, command: str, trigger_id: str,
                       user_id: str, username: str) -> str:
        """Handle /approve, /reject, /details commands."""
        if command == "approve":
            return self._handle_approve(trigger_id, user_id, username)
        elif command == "reject":
            return self._handle_reject(trigger_id, user_id, username)
        elif command == "details":
            return self._handle_details(trigger_id)
        elif command == "kill":
            return self._handle_kill(user_id, username)
        elif command == "resume":
            return self._handle_resume(user_id, username)
        else:
            return f"Unknown command: {command}"

    def _handle_approve(self, trigger_id: str, user_id: str, username: str) -> str:
        """Approve pending change."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """SELECT approval_id, risk_level, status FROM evolution_approvals
               WHERE trigger_id = ? AND status = 'pending'""",
            (trigger_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return f"❌ No pending approval for trigger {trigger_id}"

        approval_id, risk_level, _ = row
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """UPDATE evolution_approvals
               SET status = 'approved', decided_at = ?, decided_by = ?,
                   decision_reason = 'Approved via Telegram'
               WHERE approval_id = ?""",
            (now, f"human:{username}", approval_id)
        )
        conn.commit()
        conn.close()

        return f"✅ Approved: {trigger_id} (risk: {risk_level})"

    def _handle_reject(self, trigger_id: str, user_id: str, username: str) -> str:
        """Reject pending change."""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE evolution_approvals
               SET status = 'rejected', decided_at = ?, decided_by = ?,
                   decision_reason = 'Rejected via Telegram'
               WHERE trigger_id = ? AND status = 'pending'""",
            (now, f"human:{username}", trigger_id)
        )
        conn.commit()
        conn.close()

        return f"❌ Rejected: {trigger_id}"

    def _handle_kill(self, user_id: str, username: str) -> str:
        """Activate kill switch."""
        # Implementasi kill switch activation
        return "🚨 Kill switch activated. Self-evolution stopped."

    def _handle_resume(self, user_id: str, username: str) -> str:
        """Deactivate kill switch."""
        return "✅ Self-evolution resumed."
```

---

## 10. Checklist Implementasi

### Phase 1: Core Approval System

- [ ] Implementasi `RiskClassifier` dengan impact weights dan type multipliers
- [ ] Implementasi `ApprovalGate` dengan 4 risk levels
- [ ] Buat database tables: `evolution_approvals`, `escalation_log`, `llm_api_costs`
- [ ] Implementasi `NotificationManager` dengan Telegram integration
- [ ] Test: low-risk change → auto-promote (no notification needed)

### Phase 2: Escalation & Kill Switch

- [ ] Implementasi `EscalationManager` dengan 4 levels
- [ ] Implementasi `KillSwitch` dengan file flag + DB state + env var
- [ ] Integrasikan escalation dengan Orchestrator (dokumen 67)
- [ ] Test: 3 consecutive failures → escalate to CAUTION
- [ ] Test: kill switch → all self-evolution stops

### Phase 3: Telegram Integration

- [ ] Setup Telegram bot untuk approval commands
- [ ] Implementasi `TelegramApprovalHandler` untuk /approve, /reject, /details, /kill
- [ ] Test: send approval request → receive /approve → verify approved
- [ ] Test: timeout → auto-reject
- [ ] Test: critical risk → double confirmation

### Phase 4: Audit & Compliance

- [ ] Implementasi audit logging untuk setiap self-evolution event
- [ ] Tambah LLM API cost tracking
- [ ] Buat dashboard: pending approvals, escalation level, kill switch status
- [ ] Tambah API endpoints: `GET /api/self-evolution/approvals`,
  `POST /api/self-evolution/kill`, `POST /api/self-evolution/resume`
- [ ] E2E test: trigger → build → validate → approval → promote → audit

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| LLM Agent Layer | `67-llm-agent-layer-self-evolution.md` |
| Sandbox execution | `68-sandbox-execution-self-generated-code.md` |
| Knowledge base | `69-knowledge-base-persistent-memory.md` |
| Hot-swap mechanism | `70-hot-swap-runtime-update.md` |
| Eval-gated promotion | `71-eval-gated-promotion-ab-testing.md` |
| Notification strategy | `56-notification-strategy-alert-fatigue.md` |
| Change & release management | `50-change-release-management-trading.md` |
| Incident management | `49-incident-management-post-mortem.md` |
| Cybersecurity | `33-cybersecurity-trading-system.md` |
| Audit trail | `18-modul-engine-data-wajib.md` bagian 13.1 |
| Telegram notifier | `utils/telegram_notifier.py` (existing) |

---

## Referensi Eksternal

1. **Darwin Gödel Machine** — "All experiments were done with safety precautions (e.g., sandboxing, human oversight)" (arxiv.org/abs/2505.22954, 2025)
2. **AHE** — Human oversight sebagai komponen eksplisit (arxiv.org/abs/2604.25850, 2026)
3. **AutoDev** — Bounded self-modification: "structural files are off-limits" (github.com/RitikPatill/autodev, 2026)
4. **AutoMaintainer** — Self-correcting dengan human review gate (github.com/purvanshjoshi/AutoMaintainer, 2026)
5. **AI safety research** — "Human-in-the-loop AI systems" — Stanford HAI, DeepMind safety team

---

> **Catatan:** Human-in-the-loop bukan pembatas self-evolution, melainkan **safety harness** yang memungkinkan self-evolution berjalan dengan percaya diri. Tanpa human oversight, self-evolution terlalu berisiko untuk sistem trading. Dengan human oversight, AI dapat berevolusi dengan aman — manusia setuju, AI mengeksekusi.
