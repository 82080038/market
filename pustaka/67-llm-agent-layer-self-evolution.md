# LLM Agent Layer untuk Self-Evolving Trading AI

> **Dokumen 67** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Arsitektur multi-agent LLM yang berfungsi sebagai lapisan self-evolution di atas sistem trading existing — Monitor, Analyzer, Builder, Validator, Integrator — untuk mencapai kapabilitas self-building, self-repairing, dan self-updating.
>
> **Konteks:** Dokumen 23 bahas ML untuk trading. Dokumen 39 bahas AI/ML pattern memory. Dokumen 46 bahas prediksi & self-correction. Dokumen 51 bahas MLOps & model risk. Tapi belum ada doc yang membahas arsitektur LLM agent layer yang dapat menulis, memodifikasi, dan mengintegrasikan kode baru secara otomatis. Dokumen ini mengisi gap tersebut, berdasarkan riset terbaru: SelfEvolve (2026), Darwin Gödel Machine (2025), SEMAG (2026), AHE (2026).

---

## Daftar Isi

1. [Arsitektur 5-Agent](#1-arsitektur-5-agent)
2. [Monitor Agent](#2-monitor-agent)
3. [Analyzer Agent](#3-analyzer-agent)
4. [Builder Agent](#4-builder-agent)
5. [Validator Agent](#5-validator-agent)
6. [Integrator Agent](#6-integrator-agent)
7. [Event Bus Integration](#7-event-bus-integration)
8. [Database Schema](#8-database-schema)
9. [Implementasi Kode](#9-implementasi-kode)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Arsitektur 5-Agent

### 1.1 Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SELF-EVOLVING TRADING AI                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  MONITOR     │───▶│  ANALYZER    │───▶│  BUILDER     │          │
│  │  Agent       │    │  Agent       │    │  Agent       │          │
│  │              │    │              │    │              │          │
│  │ - Performance│    │ - Root cause │    │ - Generate   │          │
│  │ - Drift      │    │ - Gap        │    │   code       │          │
│  │ - New source │    │   analysis   │    │ - Write test │          │
│  │ - Broken     │    │ - Strategy   │    │ - TDD cycle  │          │
│  │   adapter    │    │   ideas      │    │              │          │
│  └──────────────┘    └──────────────┘    └──────┬───────┘          │
│                                                 │                   │
│                    ┌──────────────┐    ┌────────▼───────┐          │
│                    │  VALIDATOR   │◀───│  INTEGRATOR   │          │
│                    │  Agent       │    │  Agent        │          │
│                    │              │    │               │          │
│                    │ - Backtest   │    │ - Hot-swap    │          │
│                    │ - Walk-fwd   │    │ - Knowledge   │          │
│                    │ - Unit test  │    │   base update │          │
│                    │ - Edge case  │    │ - Registry    │          │
│                    └──────┬───────┘    └───────────────┘          │
│                           │                                         │
│                    ┌──────▼───────┐                                 │
│                    │  PROMOTER    │                                 │
│                    │  (Automated) │                                 │
│                    │              │                                 │
│                    │ - If pass:   │                                 │
│                    │   promote    │                                 │
│                    │ - If fail:   │                                 │
│                    │   rollback   │                                 │
│                    └──────────────┘                                 │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  EXISTING TRADING SYSTEM (dari pustaka 18)                          │
│  Data → Analysis → Decision → Risk → Execution → Portfolio          │
│  AI Learning Engine → Model Registry → Walk-Forward                 │
│  Monitoring → Audit Trail → XAI                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Prinsip Desain

| Prinsip | Deskripsi | Dampak jika Dilanggar |
|---------|-----------|----------------------|
| **Separation of concerns** | Setiap agent punya satu peran, tidak overlap | Sirkular dependensi, deadlock |
| **Bounded modification** | AI hanya boleh modify komponen yang diizinkan | Sistem rusak tak terkendali |
| **TDD mandatory** | Setiap generated code wajib punya test sebelum integrate | Bug production, loss finansial |
| **Sandbox isolation** | Generated code dieksekusi di isolated environment | Security breach, data corruption |
| **Human-in-the-loop** | High-risk changes wajib approval manusia | Unintended trading behavior |
| **Audit trail immutable** | Setiap self-modification tercatat permanen | Tidak ada traceability |
| **Rollback always available** | Setiap change punya snapshot untuk rollback | Irreversible damage |

### 1.3 Alur End-to-End

```
TRIGGER (Monitor deteksi anomaly)
    │
    ▼
ANALYZE (Analyzer identifikasi root cause + propose solution)
    │
    ▼
BUILD (Builder generate code via LLM + TDD)
    │
    ▼
VALIDATE (Validator: backtest + walk-forward + unit test + edge case)
    │
    ├── PASS ──▶ INTEGRATE (hot-swap + knowledge base update + registry)
    │                   │
    │                   ▼
    │              PROMOTE (production deploy + audit log)
    │
    └── FAIL ──▶ FEEDBACK (kirim ke Analyzer untuk iterasi)
                     │
                     ▼
                RETRY (max 3 iterasi, lalu human escalation)
```

---

## 2. Monitor Agent

### 2.1 Fungsi

Deteksi anomaly, performance degradation, dan opportunity yang membutuhkan self-evolution.

### 2.2 Sumber Sinyal

| Sumber | Trigger | Contoh |
|--------|---------|--------|
| **Performance metrics** | Sharpe ratio drop > 20% | "LSTM BBCA Sharpe turun dari 1.8 ke 1.1" |
| **Data drift** | PSI > 0.25 | "Distribusi volume TLKM shift signifikan" |
| **Concept drift** | Model accuracy drop > 15% | "Technical score tidak lagi berkorelasi dengan return" |
| **Source health** | Circuit breaker open > 5 menit | "IDX scraper return 403 selama 30 menit" |
| **New data source** | API endpoint baru terdeteksi | "Bursa Malaysia buka API publik" |
| **Error rate** | Exception rate > threshold | "10% fetch gagal dalam 1 jam" |
| **Backtest regression** | New strategy < baseline | "Strategi baru Sharpe 0.8 vs baseline 1.5" |
| **Market regime change** | HMM regime transition | "Regime berubah dari growth ke slowdown" |
| **User feedback** | Manual flag dari user | "User report rekomendasi tidak masuk akal" |

### 2.3 Implementasi

```python
# self_evolution/monitor_agent.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import json
import time

class TriggerType(Enum):
    PERFORMANCE_DROP = "performance_drop"
    DATA_DRIFT = "data_drift"
    CONCEPT_DRIFT = "concept_drift"
    SOURCE_DOWN = "source_down"
    NEW_DATA_SOURCE = "new_data_source"
    ERROR_RATE = "error_rate"
    BACKTEST_REGRESSION = "backtest_regression"
    REGIME_CHANGE = "regime_change"
    USER_FEEDBACK = "user_feedback"

@dataclass
class EvolutionTrigger:
    trigger_id: str
    trigger_type: TriggerType
    severity: str  # critical, high, medium, low
    description: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    source_component: str = ""

    def __post_init__(self):
        if not self.timestamp:
            from datetime import datetime, timezone
            self.timestamp = datetime.now(timezone.utc).isoformat()

class MonitorAgent:
    """Deteksi anomaly dan opportunity untuk self-evolution."""

    def __init__(self, db_path: str, config: dict | None = None):
        self.db_path = db_path
        self.config = config or {}
        self.thresholds = {
            "sharpe_drop_pct": 0.20,
            "psi_drift": 0.25,
            "accuracy_drop_pct": 0.15,
            "circuit_breaker_minutes": 5,
            "error_rate_pct": 10.0,
        }

    def check_performance(self, ticker: str, window_days: int = 30) -> list[EvolutionTrigger]:
        """Cek apakah model performance drop untuk ticker tertentu."""
        triggers = []
        # Bandingkan Sharpe ratio window terakhir vs baseline
        # Jika drop > threshold, buat trigger
        return triggers

    def check_data_drift(self, ticker: str) -> list[EvolutionTrigger]:
        """Cek PSI (Population Stability Index) untuk feature distribution."""
        triggers = []
        # Hitung PSI untuk volume, return, volatility
        # Jika PSI > 0.25, flag drift
        return triggers

    def check_source_health(self) -> list[EvolutionTrigger]:
        """Cek status semua sumber data dari source_health table."""
        triggers = []
        # Query source_health untuk status != "ok"
        # Jika circuit breaker open > 5 menit, trigger
        return triggers

    def check_error_rate(self, window_minutes: int = 60) -> list[EvolutionTrigger]:
        """Cek error rate dari audit_log."""
        triggers = []
        # Query audit_log untuk error count dalam window
        # Jika error rate > threshold, trigger
        return triggers

    def scan_all(self) -> list[EvolutionTrigger]:
        """Jalankan semua check dan kumpulkan triggers."""
        all_triggers = []
        all_triggers.extend(self.check_source_health())
        all_triggers.extend(self.check_error_rate())
        # Untuk setiap ticker aktif:
        #   all_triggers.extend(self.check_performance(ticker))
        #   all_triggers.extend(self.check_data_drift(ticker))
        return all_triggers

    def publish_triggers(self, triggers: list[EvolutionTrigger]) -> None:
        """Publish triggers ke event bus untuk Analyzer Agent."""
        for trigger in triggers:
            # Event bus: self_evolution.trigger.created
            event = {
                "event_type": "self_evolution.trigger.created",
                "trigger_id": trigger.trigger_id,
                "trigger_type": trigger.trigger_type.value,
                "severity": trigger.severity,
                "description": trigger.description,
                "context": trigger.context,
                "timestamp": trigger.timestamp,
            }
            # Simpan ke database
            self._save_trigger(trigger)
            # Publish ke event bus (lihat dokumen 65 event-driven)
```

### 2.4 Database Table

```sql
CREATE TABLE IF NOT EXISTS evolution_triggers (
    trigger_id TEXT PRIMARY KEY,
    trigger_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    context TEXT,  -- JSON
    source_component TEXT,
    status TEXT DEFAULT 'open',  -- open, analyzing, building, validating, resolved, rejected
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS evolution_actions (
    action_id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,  -- monitor, analyzer, builder, validator, integrator
    action_type TEXT NOT NULL,
    payload TEXT,  -- JSON
    result TEXT,   -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);
```

---

## 3. Analyzer Agent

### 3.1 Fungsi

Menerima trigger dari Monitor, melakukan root cause analysis, dan mengusulkan solusi.

### 3.2 Kapabilitas

| Analisis | Input | Output |
|----------|-------|--------|
| **Root cause** | Trigger + log + metrics | Penyebab utama + evidence |
| **Gap analysis** | Trigger + existing modules | Modul/fitur yang kurang |
| **Strategy ideation** | Market data + pattern history | Usulan strategi baru |
| **Fix proposal** | Bug report + codebase context | Patch code + test plan |
| **Adapter proposal** | New data source spec | Adapter design + interface |

### 3.3 Implementasi

```python
# self_evolution/analyzer_agent.py
from dataclasses import dataclass
from typing import Any

@dataclass
class AnalysisResult:
    trigger_id: str
    root_cause: str
    evidence: list[str]
    proposed_solution: str
    solution_type: str  # fix_bug, add_adapter, new_strategy, optimize_model, add_feature
    estimated_risk: str  # low, medium, high, critical
    code_spec: dict[str, Any]  # spesifikasi untuk Builder
    test_plan: list[str]  # test cases yang harus dijalankan Validator

class AnalyzerAgent:
    """Root cause analysis dan solution proposal via LLM."""

    def __init__(self, llm_client, db_path: str):
        self.llm = llm_client  # OpenAI/Anthropic/local LLM client
        self.db_path = db_path

    def analyze(self, trigger) -> AnalysisResult:
        """Analisis trigger dan usulkan solusi."""
        # 1. Kumpulkan context: log, metrics, codebase, audit trail
        context = self._gather_context(trigger)

        # 2. Kirim ke LLM dengan structured prompt
        prompt = self._build_analysis_prompt(trigger, context)
        response = self.llm.complete(prompt)

        # 3. Parse response menjadi AnalysisResult
        result = self._parse_analysis(response, trigger.trigger_id)

        # 4. Simpan ke evolution_actions
        self._save_analysis(result)

        return result

    def _gather_context(self, trigger) -> dict:
        """Kumpulkan context relevan dari database dan codebase."""
        return {
            "trigger": trigger.__dict__,
            "recent_errors": self._query_recent_errors(trigger.source_component),
            "performance_history": self._query_performance_history(trigger),
            "relevant_code": self._find_relevant_code(trigger),
            "similar_past_triggers": self._query_similar_triggers(trigger),
        }

    def _build_analysis_prompt(self, trigger, context) -> str:
        """Bangun prompt untuk LLM dengan context lengkap."""
        return f"""You are analyzing a trading system anomaly. Provide root cause analysis and solution.

TRIGGER:
- Type: {trigger.trigger_type.value}
- Severity: {trigger.severity}
- Description: {trigger.description}

CONTEXT:
- Recent errors: {context['recent_errors'][:5]}
- Performance history: {context['performance_history']}
- Relevant code files: {context['relevant_code'][:3]}
- Similar past incidents: {context['similar_past_triggers'][:3]}

Respond in JSON format:
{{
    "root_cause": "...",
    "evidence": ["...", "..."],
    "proposed_solution": "...",
    "solution_type": "fix_bug|add_adapter|new_strategy|optimize_model|add_feature",
    "estimated_risk": "low|medium|high|critical",
    "code_spec": {{
        "module": "...",
        "function": "...",
        "inputs": [...],
        "outputs": [...],
        "logic": "..."
    }},
    "test_plan": ["test case 1", "test case 2", ...]
}}
"""
```

---

## 4. Builder Agent

### 4.1 Fungsi

Menerima AnalysisResult dari Analyzer, generate kode via LLM dengan TDD approach.

### 4.2 TDD Cycle

```
AnalysisResult
    │
    ▼
GENERATE TEST (LLM write test cases berdasarkan test_plan)
    │
    ▼
GENERATE CODE (LLM write implementation berdasarkan code_spec)
    │
    ▼
RUN TEST (eksekusi di sandbox)
    │
    ├── PASS ──▶ kirim ke Validator
    │
    └── FAIL ──▶ FEEDBACK (kirim error ke LLM untuk fix)
                     │
                     ▼
                REGENERATE (max 3 iterasi)
```

### 4.3 Implementasi

```python
# self_evolution/builder_agent.py
from dataclasses import dataclass
from typing import Any

@dataclass
class BuildResult:
    trigger_id: str
    code_files: dict[str, str]  # filepath -> content
    test_files: dict[str, str]  # filepath -> content
    test_results: dict[str, Any]  # test name -> pass/fail
    iterations: int
    status: str  # success, failed, max_iterations_reached

class BuilderAgent:
    """Generate code via LLM dengan TDD approach."""

    def __init__(self, llm_client, sandbox_executor, db_path: str):
        self.llm = llm_client
        self.sandbox = sandbox_executor  # lihat dokumen 68
        self.db_path = db_path
        self.max_iterations = 3

    def build(self, analysis: AnalysisResult) -> BuildResult:
        """Generate code dengan TDD cycle."""
        # 1. Generate test cases
        test_code = self._generate_tests(analysis)

        # 2. Generate implementation
        impl_code = self._generate_implementation(analysis, test_code)

        # 3. TDD iteration loop
        for iteration in range(self.max_iterations):
            results = self.sandbox.run_tests(impl_code, test_code)

            if results["all_passed"]:
                return BuildResult(
                    trigger_id=analysis.trigger_id,
                    code_files=impl_code,
                    test_files=test_code,
                    test_results=results,
                    iterations=iteration + 1,
                    status="success",
                )

            # Feedback loop: kirim error ke LLM untuk fix
            impl_code = self._regenerate_with_feedback(
                analysis, impl_code, test_code, results["failures"]
            )

        return BuildResult(
            trigger_id=analysis.trigger_id,
            code_files=impl_code,
            test_files=test_code,
            test_results=results,
            iterations=self.max_iterations,
            status="max_iterations_reached",
        )

    def _generate_tests(self, analysis) -> dict[str, str]:
        """Generate test cases berdasarkan analysis.test_plan."""
        prompt = f"""Generate pytest test cases for the following specification:

SOLUTION TYPE: {analysis.solution_type}
CODE SPEC: {json.dumps(analysis.code_spec, indent=2)}
TEST PLAN: {json.dumps(analysis.test_plan, indent=2)}

Requirements:
- Use pytest framework
- Include edge cases (empty input, None, extreme values)
- Include integration test if applicable
- Mock external API calls
- Test data quality validation
"""
        response = self.llm.complete(prompt)
        return self._parse_code_response(response)

    def _generate_implementation(self, analysis, test_code) -> dict[str, str]:
        """Generate implementation berdasarkan spec dan test."""
        prompt = f"""Generate Python implementation that passes the following tests:

CODE SPEC: {json.dumps(analysis.code_spec, indent=2)}
TEST CODE: {test_code}

Requirements:
- Follow existing codebase patterns (type hints, docstrings)
- Use Pydantic v2 for data contracts
- Handle errors gracefully (no bare except)
- Add logging for debugging
- Line length max 120 chars (ruff)
"""
        response = self.llm.complete(prompt)
        return self._parse_code_response(response)
```

---

## 5. Validator Agent

### 5.1 Fungsi

Validasi kode yang dihasilkan Builder melalui multiple validation layers.

### 5.2 Validation Layers

| Layer | Metode | Gate |
|-------|--------|------|
| **Unit test** | pytest di sandbox | 100% pass required |
| **Integration test** | pytest dengan test DB | 100% pass required |
| **Backtest** | BacktestEngine 5 tahun | Sharpe > 0.5 (strategi baru) |
| **Walk-forward** | WalkForward 3 folds | OOS performance > 70% in-sample |
| **Edge case** | Extreme values, empty data | No crash, graceful handling |
| **Code quality** | ruff + mypy | 0 errors, 0 warnings |
| **Security scan** | SAST (bandit) | No high/critical vulnerabilities |
| **PIT-safe check** | Point-in-time audit | No look-ahead bias |

### 5.3 Implementasi

```python
# self_evolution/validator_agent.py
from dataclasses import dataclass
from typing import Any

@dataclass
class ValidationResult:
    trigger_id: str
    layer_results: dict[str, dict[str, Any]]  # layer -> {passed, details}
    overall_passed: bool
    failure_reasons: list[str]
    metrics: dict[str, float]  # sharpe, max_drawdown, win_rate, dll.

class ValidatorAgent:
    """Multi-layer validation untuk self-generated code."""

    def __init__(self, db_path: str, backtest_engine, walk_forward):
        self.db_path = db_path
        self.backtest = backtest_engine
        self.walk_forward = walk_forward

    def validate(self, build_result: BuildResult, analysis: AnalysisResult) -> ValidationResult:
        """Jalankan semua validation layers."""
        results = {}

        # Layer 1: Unit test
        results["unit_test"] = self._run_unit_tests(build_result)

        # Layer 2: Integration test
        results["integration_test"] = self._run_integration_tests(build_result)

        # Layer 3: Code quality (ruff + mypy)
        results["code_quality"] = self._check_code_quality(build_result)

        # Layer 4: Security scan
        results["security"] = self._security_scan(build_result)

        # Layer 5: Backtest (untuk strategi/indicator baru)
        if analysis.solution_type in ("new_strategy", "optimize_model", "add_feature"):
            results["backtest"] = self._run_backtest(build_result, analysis)

        # Layer 6: Walk-forward (untuk strategi/model)
        if analysis.solution_type in ("new_strategy", "optimize_model"):
            results["walk_forward"] = self._run_walk_forward(build_result, analysis)

        # Layer 7: PIT-safe check
        results["pit_safe"] = self._check_pit_safe(build_result)

        # Determine overall pass/fail
        required_layers = ["unit_test", "integration_test", "code_quality", "security", "pit_safe"]
        if analysis.solution_type in ("new_strategy", "optimize_model", "add_feature"):
            required_layers.extend(["backtest", "walk_forward"])

        overall_passed = all(
            results.get(layer, {}).get("passed", False)
            for layer in required_layers
        )

        failure_reasons = [
            f"{layer}: {results[layer].get('details', 'unknown')}"
            for layer in required_layers
            if not results.get(layer, {}).get("passed", False)
        ]

        return ValidationResult(
            trigger_id=build_result.trigger_id,
            layer_results=results,
            overall_passed=overall_passed,
            failure_reasons=failure_reasons,
            metrics=results.get("backtest", {}).get("metrics", {}),
        )

    def _run_unit_tests(self, build_result) -> dict:
        """Run pytest di sandbox."""
        # lihat dokumen 68 untuk sandbox execution
        pass

    def _run_backtest(self, build_result, analysis) -> dict:
        """Run backtest dengan 5 tahun data IDX."""
        pass

    def _run_walk_forward(self, build_result, analysis) -> dict:
        """Run walk-forward dengan 3 folds, purged TSS."""
        pass

    def _check_pit_safe(self, build_result) -> dict:
        """Audit bahwa tidak ada look-ahead bias di generated code."""
        # Cek: tidak ada akses ke data future
        # Cek: tidak ada .shift(-n) tanpa guard
        # Cek: tidak ada akses ke kolom yang belum ada di timestamp prediksi
        pass
```

---

## 6. Integrator Agent

### 6.1 Fungsi

Integrasi kode yang sudah divalidasi ke sistem production — hot-swap modul, update knowledge base, promote model di registry.

### 6.2 Implementasi

```python
# self_evolution/integrator_agent.py
from dataclasses import dataclass

@dataclass
class IntegrationResult:
    trigger_id: str
    integrated_modules: list[str]
    knowledge_base_updates: list[str]
    model_registry_version: str | None
    audit_log_id: str
    rollback_snapshot_id: str
    status: str  # integrated, failed, rolled_back

class IntegratorAgent:
    """Integrasi validated code ke production via hot-swap."""

    def __init__(self, db_path: str, model_registry, knowledge_base):
        self.db_path = db_path
        self.model_registry = model_registry
        self.knowledge_base = knowledge_base  # lihat dokumen 69

    def integrate(self, build_result: BuildResult, validation: ValidationResult) -> IntegrationResult:
        """Integrasi validated code ke production."""
        # 1. Snapshot state saat ini untuk rollback
        snapshot_id = self._create_snapshot()

        # 2. Hot-swap modul (lihat dokumen 70)
        integrated = []
        for filepath, content in build_result.code_files.items():
            self._hot_swap_module(filepath, content)
            integrated.append(filepath)

        # 3. Update knowledge base
        kb_updates = self._update_knowledge_base(build_result, validation)

        # 4. Promote model di registry jika applicable
        model_version = None
        if build_result.code_files:
            # Cek apakah ada model file
            model_version = self._promote_model_if_applicable(build_result)

        # 5. Audit log
        audit_id = self._write_audit_log(
            trigger_id=build_result.trigger_id,
            action="self_evolution.integrate",
            modules=integrated,
            snapshot_id=snapshot_id,
        )

        # 6. Telegram notification
        self._notify_integration(build_result, validation)

        return IntegrationResult(
            trigger_id=build_result.trigger_id,
            integrated_modules=integrated,
            knowledge_base_updates=kb_updates,
            model_registry_version=model_version,
            audit_log_id=audit_id,
            rollback_snapshot_id=snapshot_id,
            status="integrated",
        )

    def rollback(self, snapshot_id: str) -> bool:
        """Rollback ke state sebelum integration."""
        # Restore dari snapshot
        pass
```

---

## 7. Event Bus Integration

### 7.1 New Event Bus Topics

| Topic | Publisher | Subscriber |
|-------|-----------|------------|
| `self_evolution.trigger.created` | Monitor Agent | Analyzer Agent |
| `self_evolution.analysis.completed` | Analyzer Agent | Builder Agent |
| `self_evolution.build.completed` | Builder Agent | Validator Agent |
| `self_evolution.validation.passed` | Validator Agent | Integrator Agent |
| `self_evolution.validation.failed` | Validator Agent | Analyzer Agent (feedback) |
| `self_evolution.integration.completed` | Integrator Agent | Monitor Agent, Audit |
| `self_evolution.rollback.executed` | Integrator Agent | Monitor, Audit, Telegram |

### 7.2 Event Flow

```
Monitor ──(trigger.created)──▶ Analyzer
Analyzer ──(analysis.completed)──▶ Builder
Builder  ──(build.completed)──▶ Validator
Validator ──(validation.passed)──▶ Integrator
Validator ──(validation.failed)──▶ Analyzer [feedback loop]
Integrator ──(integration.completed)──▶ Monitor [confirm resolved]
Integrator ──(rollback.executed)──▶ Monitor, Telegram [alert]
```

---

## 8. Database Schema

### 8.1 Tabel Tambahan

```sql
-- Evolution triggers (dari Monitor)
CREATE TABLE IF NOT EXISTS evolution_triggers (
    trigger_id TEXT PRIMARY KEY,
    trigger_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    context TEXT,
    source_component TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

-- Evolution actions (log setiap agent action)
CREATE TABLE IF NOT EXISTS evolution_actions (
    action_id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    action_type TEXT NOT NULL,
    payload TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);

-- Rollback snapshots
CREATE TABLE IF NOT EXISTS evolution_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    component TEXT NOT NULL,
    snapshot_data TEXT,  -- JSON: file contents, model weights, config
    created_at TEXT NOT NULL,
    restored_at TEXT,
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);
```

---

## 9. Implementasi Kode

### 9.1 Module Structure

```
src/trading_system/self_evolution/
├── __init__.py
├── monitor_agent.py       # Monitor Agent
├── analyzer_agent.py      # Analyzer Agent
├── builder_agent.py       # Builder Agent
├── validator_agent.py     # Validator Agent
├── integrator_agent.py    # Integrator Agent
├── orchestrator.py        # Orchestrator: koordinasi 5 agent
├── llm_client.py          # LLM client abstraction (OpenAI/Anthropic/local)
└── prompts/               # Prompt templates per agent
    ├── analysis_prompt.txt
    ├── builder_test_prompt.txt
    ├── builder_impl_prompt.txt
    └── fix_feedback_prompt.txt
```

### 9.2 Orchestrator

```python
# self_evolution/orchestrator.py

class SelfEvolutionOrchestrator:
    """Koordinasi 5-agent self-evolution loop."""

    def __init__(self, db_path: str, llm_client, sandbox, backtest_engine, walk_forward):
        self.monitor = MonitorAgent(db_path)
        self.analyzer = AnalyzerAgent(llm_client, db_path)
        self.builder = BuilderAgent(llm_client, sandbox, db_path)
        self.validator = ValidatorAgent(db_path, backtest_engine, walk_forward)
        self.integrator = IntegratorAgent(db_path, None, None)

    def run_cycle(self) -> list[dict]:
        """Jalankan satu cycle: scan → analyze → build → validate → integrate."""
        results = []

        # 1. Monitor: scan untuk triggers
        triggers = self.monitor.scan_all()

        for trigger in triggers:
            if trigger.severity == "critical":
                # Critical: langsung human escalation
                self._escalate_to_human(trigger)
                continue

            # 2. Analyze
            analysis = self.analyzer.analyze(trigger)

            # 3. Build
            build = self.builder.build(analysis)

            if build.status != "success":
                self._escalate_to_human(trigger, reason="Builder failed")
                continue

            # 4. Validate
            validation = self.validator.validate(build, analysis)

            if not validation.overall_passed:
                # Feedback ke analyzer untuk iterasi
                self._send_feedback(trigger, validation)
                continue

            # 5. Integrate (dengan human approval jika high-risk)
            if analysis.estimated_risk in ("high", "critical"):
                approval = self._request_human_approval(trigger, analysis, validation)
                if not approval:
                    continue

            integration = self.integrator.integrate(build, validation)
            results.append({
                "trigger_id": trigger.trigger_id,
                "status": "integrated",
                "modules": integration.integrated_modules,
            })

        return results

    def run_loop(self, interval_minutes: int = 30):
        """Run self-evolution loop secara berkala."""
        import time
        while True:
            self.run_cycle()
            time.sleep(interval_minutes * 60)
```

### 9.3 LLM Client Abstraction

```python
# self_evolution/llm_client.py
from abc import ABC, abstractmethod

class LLMClient(ABC):
    """Abstraction untuk LLM provider — swap tanpa code change."""

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        """Sync completion."""
        pass

    @abstractmethod
    async def complete_async(self, prompt: str, max_tokens: int = 4096) -> str:
        """Async completion."""
        pass

class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.2,  # low temperature untuk code generation
        )
        return response.choices[0].message.content

class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

class LocalLLMClient(LLMClient):
    """Untuk LLM lokal (Ollama, vLLM, dll.) — gratis, private."""
    def __init__(self, endpoint: str = "http://localhost:11434"):
        self.endpoint = endpoint

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        import requests
        response = requests.post(
            f"{self.endpoint}/api/generate",
            json={"prompt": prompt, "max_tokens": max_tokens, "temperature": 0.2},
        )
        return response.json()["response"]
```

---

## 10. Checklist Implementasi

### Phase 1: Foundation

- [ ] Buat module `self_evolution/` dengan 5 agent + orchestrator
- [ ] Implementasi LLM client abstraction (OpenAI/Anthropic/local)
- [ ] Buat database tables: `evolution_triggers`, ` evolution_actions`, `evolution_snapshots`
- [ ] Implementasi Monitor Agent dengan 5 check methods
- [ ] Buat prompt templates untuk setiap agent

### Phase 2: Core Loop

- [ ] Implementasi Analyzer Agent dengan LLM integration
- [ ] Implementasi Builder Agent dengan TDD cycle
- [ ] Implementasi Validator Agent dengan 7 validation layers
- [ ] Implementasi Integrator Agent dengan hot-swap + rollback
- [ ] Implementasi Orchestrator dengan feedback loop

### Phase 3: Integration

- [ ] Tambah event bus topics untuk self_evolution.*
- [ ] Integrasikan dengan existing MonitoringEngine
- [ ] Tambah CLI subcommand: `self-evolve --scan`, `self-evolve --run`
- [ ] Tambah API endpoint: `GET /api/self-evolution/status`, `POST /api/self-evolution/trigger`
- [ ] Tambah Telegram notification untuk setiap integration

### Phase 4: Safety & Governance

- [ ] Implementasi human approval gate untuk high-risk changes
- [ ] Tambah rate limiting untuk LLM API calls
- [ ] Tambah cost tracking untuk LLM usage
- [ ] Buat dashboard untuk monitor self-evolution activity
- [ ] E2E test: trigger → analyze → build → validate → integrate → rollback

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| Event bus & EDA | `65-event-driven-event-sourcing.md` |
| MLOps & model registry | `51-mlops-model-risk-management.md` |
| Monitoring engine | `18-modul-engine-data-wajib.md` bagian 10.3 |
| Backtest engine | `29-backtesting-strategy-validation.md` |
| Walk-forward & purged TSS | `23-machine-learning-trading.md` bagian 5, 9 |
| AI Learning Engine | `39-screening-aiml-pattern-memory.md` bagian 2 |
| Prediksi & self-correction | `46-prediksi-pola-portfolio-pipeline.md` bagian 4 |
| Change & release management | `50-change-release-management-trading.md` |
| Cybersecurity | `33-cybersecurity-trading-system.md` |
| Audit trail | `18-modul-engine-data-wajib.md` bagian 13.1 |

---

## Referensi Eksternal

1. **SelfEvolve** — Runtime self-extension via LLM code generation (arxiv.org/abs/2604.16314, 2026) — Pass@1: 92.7%
2. **Darwin Gödel Machine** — Self-improving coding agents (arxiv.org/abs/2505.22954, 2025) — SWE-bench: 20% → 50%
3. **SEMAG** — Self-evolutionary multi-agent code generation (arxiv.org/abs/2603.15707, 2026) — HumanEval: 98.8%
4. **AHE** — Agentic Harness Engineering (arxiv.org/abs/2604.25850, 2026) — Terminal-Bench: 69.7% → 77.0%
5. **AutoMaintainer** — Autonomous AI software team (github.com/purvanshjoshi/AutoMaintainer, 2026)

---

> **Catatan:** LLM Agent Layer ini berfungsi sebagai **lapisan di atas** sistem trading existing. Tidak menggantikan engine yang sudah ada, tetapi menambahkan kapabilitas self-build, self-repair, dan self-update. Setiap self-modification wajib melalui validasi 7-layer dan human approval untuk high-risk changes. Untuk arsitektur lengkap yang menyatukan 5-agent layer + self-awareness + profitability guard menjadi "Gigantic AI", lihat `86-gigantic-ai-autonomous-trading-system.md`.
