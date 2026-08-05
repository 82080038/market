# Hot-Swap Mechanism: Runtime Module Update Tanpa Restart

> **Dokumen 70** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Mekanisme hot-swap untuk mengganti modul Python saat runtime tanpa restart sistem — sehingga Integrator Agent dapat mengintegrasikan kode baru yang di-generate oleh Builder secara langsung ke production.
>
> **Konteks:** Dokumen 67 mendefinisikan Integrator Agent yang bertugas mengintegrasikan validated code. Dokumen 68 mendefinisikan sandbox untuk testing. Dokumen ini mendefinisikan bagaimana kode yang sudah divalidasi di-swap ke production tanpa menghentikan sistem trading.

---

## Daftar Isi

1. [Konsep Hot-Swap](#1-konsep-hot-swap)
2. [Python `importlib` Mechanism](#2-python-importlib-mechanism)
3. [Module Swap Strategy](#3-module-swap-strategy)
4. [State Preservation](#4-state-preservation)
5. [Rollback Mechanism](#5-rollback-mechanism)
6. [Safety Guards](#6-safety-guards)
7. [Database Schema](#7-database-schema)
8. [Implementasi Kode](#8-implementasi-kode)
9. [Checklist Implementasi](#9-checklist-implementasi)

---

## 1. Konsep Hot-Swap

### 1.1 Mengapa Hot-Swap

| Tanpa Hot-Swap | Dengan Hot-Swap |
|----------------|-----------------|
| Restart sistem untuk setiap update | Update tanpa downtime |
| Trading terhenti selama update | Trading berlanjut tanpa pause |
| Manual deploy: stop → replace → start | Otomatis: swap → verify → keep/rollback |
| Tidak feasible untuk self-evolving system | Self-evolution berjalan saat sistem aktif |

### 1.2 Prinsip

| Prinsip | Deskripsi |
|---------|-----------|
| **Atomic swap** | Module lama diganti baru dalam satu operasi, tidak ada state intermediate |
| **State preservation** | State yang aman (DB connections, cache) dipertahankan, state yang berbahaya di-reset |
| **Instant rollback** | Jika swap gagal, kembalikan ke module lama dalam < 1 detik |
| **Thread-safe** | Swap aman bahkan saat thread lain sedang menggunakan module |
| **Versioned** | Setiap swap tercatat dengan versi lama dan baru |
| **Health check post-swap** | Verifikasi module baru berfungsi sebelum commit |

### 1.3 Yang BISA dan TIDAK BISA di-Hot-Swap

| Bisa Hot-Swap | Tidak Bisa Hot-Swap |
|---------------|---------------------|
| Analysis engines (technical, fundamental, macro) | Database schema (butuh migration) |
| Data adapters (fetch, parse, validate) | Database connection (butuh reconnect) |
| Strategy implementations | API endpoints (butuh FastAPI reload) |
| Indicator calculations | Configuration (butuh restart untuk env vars) |
| Sentiment analysis logic | Broker connection (butuh reconnect) |
| Pattern detection algorithms | Auth middleware (security risk) |
| Risk calculation formulas | Event bus topology (butuh restart) |

---

## 2. Python `importlib` Mechanism

### 2.1 Basic Reload

```python
import importlib
import sys

# Reload module yang sudah di-import
import trading_system.analysis.technical
importlib.reload(trading_system.analysis.technical)

# Sekarang semua import baru akan dapat versi baru
# Tapi reference lama masih pegang versi lama
```

### 2.2 Limitasi `importlib.reload()`

| Limitasi | Dampak | Solusi |
|----------|--------|--------|
| **Reference lama tidak update** | `from module import func` masih pegang func lama | Gunakan `import module` bukan `from module import` |
| **Class instances lama** | Object yang sudah dibuat masih class lama | Re-instantiate objects setelah reload |
| **Circular imports** | Bisa cause infinite loop | Topological sort sebelum reload |
| **C extensions** | `.so`/`.pyd` tidak bisa reload | Hanya pure Python yang bisa hot-swap |
| **sys.modules cache** | Module di-cache, perlu invalidate | Hapus dari sys.modules sebelum reload |

### 2.3 Safe Reload Pattern

```python
# self_evolution/hot_swap/reloader.py
import importlib
import sys
import inspect
from typing import Any

class SafeReloader:
    """Safe module reload dengan state preservation dan rollback."""

    def __init__(self):
        self._swap_history: list[dict] = []
        self._locked_modules: set[str] = set()

    def reload_module(self, module_path: str, new_code: str | None = None) -> dict:
        """
        Reload module dengan aman.
        
        Args:
            module_path: e.g. "trading_system.analysis.technical"
            new_code: Optional — jika ada, write ke file dulu sebelum reload
        
        Returns:
            {success, old_version, new_version, error}
        """
        if module_path in self._locked_modules:
            return {"success": False, "error": "Module is locked"}

        # 1. Backup module lama
        old_module = sys.modules.get(module_path)
        old_code = ""
        if old_module:
            filepath = inspect.getfile(old_module)
            with open(filepath, "r") as f:
                old_code = f.read()

        # 2. Write new code jika ada
        if new_code and old_module:
            filepath = inspect.getfile(old_module)
            with open(filepath, "w") as f:
                f.write(new_code)

        # 3. Invalidate cache
        self._invalidate_cache(module_path)

        # 4. Reload
        try:
            if old_module:
                new_module = importlib.reload(old_module)
            else:
                new_module = importlib.import_module(module_path)

            # 5. Health check
            if not self._health_check(new_module):
                # Rollback
                self._rollback(module_path, old_code)
                return {"success": False, "error": "Health check failed"}

            # 6. Record swap
            swap_record = {
                "module_path": module_path,
                "old_version": old_code[:100],  # First 100 chars for logging
                "new_version": new_code[:100] if new_code else "reload only",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
            }
            self._swap_history.append(swap_record)

            return {"success": True, "old_version": old_code, "new_version": new_code}

        except Exception as e:
            # Rollback on error
            if old_module:
                self._rollback(module_path, old_code)
            return {"success": False, "error": str(e)}

    def _invalidate_cache(self, module_path: str):
        """Invalidate sys.modules cache untuk module dan submodules."""
        # Hapus module dan semua submodules
        to_remove = [
            key for key in sys.modules
            if key == module_path or key.startswith(module_path + ".")
        ]
        for key in to_remove:
            mod = sys.modules.pop(key, None)
            # Jangan hapus jika sedang digunakan oleh thread lain

    def _health_check(self, module: Any) -> bool:
        """Quick health check setelah reload."""
        try:
            # Cek apakah module punya atribut dasar
            if not hasattr(module, "__name__"):
                return False
            # Cek apakah tidak ada import error
            if hasattr(module, "__spec__") and module.__spec__ is None:
                return False
            return True
        except Exception:
            return False

    def _rollback(self, module_path: str, old_code: str):
        """Rollback ke kode lama."""
        module = sys.modules.get(module_path)
        if module:
            filepath = inspect.getfile(module)
            with open(filepath, "w") as f:
                f.write(old_code)
            self._invalidate_cache(module_path)
            importlib.import_module(module_path)
```

---

## 3. Module Swap Strategy

### 3.1 Swap Pipeline

```
INTEGRATOR AGENT
    │
    ├── 1. IDENTIFY target module
    │   └── "trading_system.analysis.technical"
    │
    ├── 2. SNAPSHOT current state
    │   ├── Save old code
    │   ├── Save old module object
    │   └── Save dependent references
    │
    ├── 3. WRITE new code to file
    │   └── Overwrite .py file dengan new content
    │
    ├── 4. INVALIDATE cache
    │   ├── Remove from sys.modules
    │   └── Remove submodules
    │
    ├── 5. RELOAD module
    │   └── importlib.reload() atau importlib.import_module()
    │
    ├── 6. HEALTH CHECK
    │   ├── Module importable?
    │   ├── Key functions callable?
    │   ├── No import errors?
    │   └── Quick smoke test
    │
    ├── 7a. PASS → COMMIT
    │   ├── Update references
    │   ├── Re-instantiate objects
    │   ├── Audit log
    │   └── Telegram notification
    │
    └── 7b. FAIL → ROLLBACK
        ├── Restore old code
        ├── Re-import old module
        ├── Alert: "Hot-swap failed, rolled back"
        └── Audit log
```

### 3.2 Dependency-Aware Swap

```python
# self_evolution/hot_swap/dependency_resolver.py
import importlib
import sys
from typing import Any

class DependencyResolver:
    """Resolve urutan reload berdasarkan dependency graph."""

    def get_reload_order(self, module_path: str) -> list[str]:
        """Topological sort: dependents dulu, baru module utama."""
        # 1. Cari semua module yang import module_path
        dependents = self._find_dependents(module_path)

        # 2. Topological sort
        order = []
        visited = set()

        def visit(mod):
            if mod in visited:
                return
            visited.add(mod)
            for dep in self._find_dependents(mod):
                visit(dep)
            order.append(mod)

        visit(module_path)
        return order

    def _find_dependents(self, module_path: str) -> list[str]:
        """Cari semua module yang import module_path."""
        dependents = []
        for name, module in sys.modules.items():
            if module is None:
                continue
            # Cek apakah module ini import module_path
            if hasattr(module, "__dict__"):
                for attr_name, attr_value in module.__dict__.items():
                    if attr_value is not None and hasattr(attr_value, "__module__"):
                        if attr_value.__module__ == module_path:
                            dependents.append(name)
                            break
        return dependents
```

---

## 4. State Preservation

### 4.1 State Classification

| State Type | Preservation Strategy | Contoh |
|------------|----------------------|--------|
| **Database connections** | Preserve (reconnect jika perlu) | `DataStorage._conn` |
| **Cache** | Preserve (LRU, dict) | `TechnicalAnalysisEngine._indicator_cache` |
| **Configuration** | Preserve (read dari env/config) | `config.TRADING_CAPITAL` |
| **Model weights** | Preserve (di model_store/) | LSTM weights |
| **Engine instances** | Re-instantiate dengan new code | `TechnicalAnalysisEngine()` |
| **Thread state** | Tidak bisa preserve — wait for idle | Background threads |
| **File handles** | Close dan reopen | Log files |

### 4.2 State Manager

```python
# self_evolution/hot_swap/state_manager.py
import pickle
import copy
from typing import Any

class StateManager:
    """Preserve dan restore state across hot-swap."""

    def snapshot_state(self, module_path: str) -> dict[str, Any]:
        """Snapshot state dari module sebelum swap."""
        module = sys.modules.get(module_path)
        if not module:
            return {}

        state = {}
        # Copy attributes yang aman untuk preserve
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name, None)
            # Hanya preserve non-callable, non-class attributes
            if not callable(attr) and not inspect.isclass(attr):
                try:
                    state[attr_name] = copy.deepcopy(attr)
                except (TypeError, pickle.PicklingError):
                    pass  # Skip non-serializable

        return state

    def restore_state(self, module_path: str, state: dict[str, Any]):
        """Restore state ke module setelah swap."""
        module = sys.modules.get(module_path)
        if not module:
            return

        for attr_name, value in state.items():
            try:
                setattr(module, attr_name, value)
            except (AttributeError, TypeError):
                pass  # Skip jika tidak bisa set
```

---

## 5. Rollback Mechanism

### 5.1 Rollback Levels

| Level | Trigger | Method | Speed |
|-------|---------|--------|-------|
| **L1: Code rollback** | Health check fail | Restore old .py file + re-import | < 1 detik |
| **L2: Module rollback** | Runtime error post-swap | Restore old module object | < 1 detik |
| **L3: Process rollback** | Cascading failure | Restart process dengan old code | 5-10 detik |
| **L4: Snapshot rollback** | Data corruption | Restore DB snapshot | 30-60 detik |

### 5.2 Rollback Manager

```python
# self_evolution/hot_swap/rollback_manager.py
import os
import shutil
from datetime import datetime, timezone
from dataclasses import dataclass, field

@dataclass
class SwapSnapshot:
    snapshot_id: str
    module_path: str
    old_code: str
    old_file_path: str
    old_module_state: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    restored: bool = False
    restored_at: str | None = None

class RollbackManager:
    """Manage snapshots dan rollback untuk hot-swap."""

    def __init__(self, snapshot_dir: str = ".snapshots"):
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)
        self._snapshots: dict[str, SwapSnapshot] = {}

    def create_snapshot(self, module_path: str, old_code: str,
                        old_file_path: str, old_state: dict) -> str:
        """Create snapshot sebelum hot-swap."""
        import uuid
        snapshot_id = str(uuid.uuid4())
        snapshot = SwapSnapshot(
            snapshot_id=snapshot_id,
            module_path=module_path,
            old_code=old_code,
            old_file_path=old_file_path,
            old_module_state=old_state,
        )
        self._snapshots[snapshot_id] = snapshot

        # Persist ke file
        snapshot_file = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
        import json
        with open(snapshot_file, "w") as f:
            json.dump({
                "snapshot_id": snapshot_id,
                "module_path": module_path,
                "old_file_path": old_file_path,
                "old_code": old_code,
                "created_at": snapshot.created_at,
            }, f)

        return snapshot_id

    def rollback(self, snapshot_id: str) -> bool:
        """Rollback ke snapshot."""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot or snapshot.restored:
            return False

        try:
            # 1. Restore old code
            with open(snapshot.old_file_path, "w") as f:
                f.write(snapshot.old_code)

            # 2. Invalidate cache
            self._invalidate_cache(snapshot.module_path)

            # 3. Re-import
            import importlib
            importlib.import_module(snapshot.module_path)

            # 4. Restore state
            # (state restoration handled by StateManager)

            snapshot.restored = True
            snapshot.restored_at = datetime.now(timezone.utc).isoformat()
            return True

        except Exception:
            return False

    def _invalidate_cache(self, module_path: str):
        """Invalidate sys.modules cache."""
        import sys
        to_remove = [
            key for key in sys.modules
            if key == module_path or key.startswith(module_path + ".")
        ]
        for key in to_remove:
            sys.modules.pop(key, None)
```

---

## 6. Safety Guards

### 6.1 Pre-Swap Checks

```python
# self_evolution/hot_swap/safety_guards.py

class SafetyGuards:
    """Safety checks sebelum dan setelah hot-swap."""

    # Modules yang TIDAK BOLEH di-hot-swap
    LOCKED_MODULES = {
        "trading_system.api.app",           # API endpoints — butuh FastAPI reload
        "trading_system.config",            # Config — butuh restart
        "trading_system.data.storage",      # DB layer — butuh migration
        "trading_system.execution.automated", # Auto-trading — terlalu risky
    }

    # Modules yang boleh di-hot-swap dengan extra caution
    HIGH_RISK_MODULES = {
        "trading_system.decision.engine",
        "trading_system.risk.engine",
        "trading_system.ai_learning.engine",
    }

    def can_swap(self, module_path: str) -> tuple[bool, str]:
        """Cek apakah module boleh di-hot-swap."""
        if module_path in self.LOCKED_MODULES:
            return False, f"Module {module_path} is locked — requires restart"

        if module_path in self.HIGH_RISK_MODULES:
            return True, "HIGH_RISK — requires human approval"

        return True, "OK"

    def pre_swap_checks(self, module_path: str) -> dict:
        """Checks sebelum swap."""
        checks = {
            "module_exists": module_path in sys.modules,
            "not_locked": module_path not in self.LOCKED_MODULES,
            "no_active_trades": self._check_no_active_trades(),
            "market_closed": self._check_market_closed(),
            "no_background_tasks": self._check_no_background_tasks(),
        }
        checks["all_passed"] = all(checks.values())
        return checks

    def post_swap_checks(self, module_path: str) -> dict:
        """Checks setelah swap."""
        checks = {
            "module_importable": module_path in sys.modules,
            "key_functions_callable": self._check_key_functions(module_path),
            "no_import_errors": self._check_no_import_errors(module_path),
            "smoke_test_pass": self._run_smoke_test(module_path),
        }
        checks["all_passed"] = all(checks.values())
        return checks

    def _check_no_active_trades(self) -> bool:
        """Cek apakah tidak ada posisi terbuka."""
        # Query positions table
        return True  # Simplified

    def _check_market_closed(self) -> bool:
        """Cek apakah pasar sedang tutup (lebih aman untuk swap)."""
        from datetime import datetime, timezone, timedelta
        wib = timezone(timedelta(hours=7))
        now = datetime.now(wib)
        # IDX jam: 09:00-15:50 WIB, Jumat 09:00-11:30 & 14:00-15:50
        if now.weekday() >= 5:  # Sabtu/Minggu
            return True
        hour = now.hour
        if hour < 9 or hour >= 16:
            return True
        if now.weekday() == 4 and (hour >= 12 and hour < 14):
            return True
        return False

    def _check_no_background_tasks(self) -> bool:
        """Cek apakah tidak ada background task yang sedang jalan."""
        # Cek thread pool, celery tasks, dll
        return True  # Simplified

    def _check_key_functions(self, module_path: str) -> bool:
        """Cek apakah key functions di module baru bisa dipanggil."""
        module = sys.modules.get(module_path)
        if not module:
            return False
        # Cek apakah module punya expected functions
        # (definisi expected functions per module)
        return True

    def _run_smoke_test(self, module_path: str) -> bool:
        """Run quick smoke test setelah swap."""
        try:
            module = sys.modules.get(module_path)
            if not module:
                return False
            # Call a simple function jika ada
            # Atau just verify import succeeded
            return True
        except Exception:
            return False
```

### 6.2 Timing Constraints

| Condition | Swap Allowed? | Reason |
|-----------|---------------|--------|
| Market open (09:00-15:50 WIB) | ❌ No | Trading aktif, risk of disruption |
| Market closed (after 15:50) | ✅ Yes | Aman, tidak ada trading |
| Weekend (Sabtu/Minggu) | ✅ Yes | Market tutup |
| Active positions exist | ❌ No | Risk of inconsistent state |
| Background task running | ❌ No | Risk of race condition |
| During backtest | ⚠️ Caution | Bisa interfere dengan results |

---

## 7. Database Schema

```sql
-- Hot-swap log
CREATE TABLE IF NOT EXISTS hot_swap_log (
    swap_id TEXT PRIMARY KEY,
    module_path TEXT NOT NULL,
    trigger_id TEXT,
    old_version_hash TEXT,       -- SHA256 of old code
    new_version_hash TEXT,       -- SHA256 of new code
    status TEXT NOT NULL,         -- pending, success, failed, rolled_back
    pre_swap_checks TEXT,         -- JSON
    post_swap_checks TEXT,        -- JSON
    snapshot_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (trigger_id) REFERENCES evolution_triggers(trigger_id)
);
```

---

## 8. Implementasi Kode

### 8.1 Module Structure

```
src/trading_system/self_evolution/hot_swap/
├── __init__.py
├── reloader.py            # SafeReloader
├── state_manager.py       # StateManager
├── rollback_manager.py    # RollbackManager
├── safety_guards.py       # SafetyGuards
└── dependency_resolver.py # DependencyResolver
```

### 8.2 HotSwapManager (Unified)

```python
# self_evolution/hot_swap/__init__.py
from dataclasses import dataclass
from typing import Any

@dataclass
class SwapResult:
    swap_id: str
    module_path: str
    success: bool
    snapshot_id: str | None
    error: str | None
    pre_checks: dict[str, Any]
    post_checks: dict[str, Any]

class HotSwapManager:
    """Unified hot-swap manager: guards → snapshot → swap → verify → commit/rollback."""

    def __init__(self, db_path: str, snapshot_dir: str = ".snapshots"):
        self.reloader = SafeReloader()
        self.state_mgr = StateManager()
        self.rollback_mgr = RollbackManager(snapshot_dir)
        self.guards = SafetyGuards()
        self.db_path = db_path

    def swap(self, module_path: str, new_code: str,
             trigger_id: str | None = None,
             force: bool = False) -> SwapResult:
        """
        Hot-swap module dengan new code.
        
        Args:
            module_path: Python module path (e.g. "trading_system.analysis.technical")
            new_code: New Python source code
            trigger_id: Optional trigger ID untuk audit
            force: Skip safety guards (DANGEROUS — only for testing)
        
        Returns:
            SwapResult dengan success/failure details
        """
        import uuid
        swap_id = str(uuid.uuid4())

        # 1. Safety checks
        if not force:
            can_swap, reason = self.guards.can_swap(module_path)
            if not can_swap:
                return SwapResult(
                    swap_id=swap_id, module_path=module_path,
                    success=False, snapshot_id=None,
                    error=reason, pre_checks={}, post_checks={},
                )

            pre_checks = self.guards.pre_swap_checks(module_path)
            if not pre_checks["all_passed"]:
                return SwapResult(
                    swap_id=swap_id, module_path=module_path,
                    success=False, snapshot_id=None,
                    error=f"Pre-swap checks failed: {pre_checks}",
                    pre_checks=pre_checks, post_checks={},
                )
        else:
            pre_checks = {"forced": True}

        # 2. Snapshot
        old_state = self.state_mgr.snapshot_state(module_path)
        old_module = sys.modules.get(module_path)
        old_code = ""
        old_file_path = ""
        if old_module:
            import inspect
            old_file_path = inspect.getfile(old_module)
            with open(old_file_path, "r") as f:
                old_code = f.read()

        snapshot_id = self.rollback_mgr.create_snapshot(
            module_path, old_code, old_file_path, old_state
        )

        # 3. Swap
        swap_result = self.reloader.reload_module(module_path, new_code)

        if not swap_result["success"]:
            # Auto-rollback
            self.rollback_mgr.rollback(snapshot_id)
            return SwapResult(
                swap_id=swap_id, module_path=module_path,
                success=False, snapshot_id=snapshot_id,
                error=swap_result.get("error", "Unknown error"),
                pre_checks=pre_checks, post_checks={},
            )

        # 4. Post-swap checks
        post_checks = self.guards.post_swap_checks(module_path)
        if not post_checks["all_passed"]:
            # Auto-rollback
            self.rollback_mgr.rollback(snapshot_id)
            return SwapResult(
                swap_id=swap_id, module_path=module_path,
                success=False, snapshot_id=snapshot_id,
                error=f"Post-swap checks failed: {post_checks}",
                pre_checks=pre_checks, post_checks=post_checks,
            )

        # 5. Restore state
        self.state_mgr.restore_state(module_path, old_state)

        # 6. Audit log
        self._log_swap(swap_id, module_path, trigger_id,
                        old_code, new_code, "success", snapshot_id,
                        pre_checks, post_checks)

        # 7. Telegram notification
        self._notify_swap(module_path, True)

        return SwapResult(
            swap_id=swap_id, module_path=module_path,
            success=True, snapshot_id=snapshot_id,
            error=None, pre_checks=pre_checks, post_checks=post_checks,
        )

    def rollback(self, snapshot_id: str) -> bool:
        """Manual rollback ke snapshot tertentu."""
        success = self.rollback_mgr.rollback(snapshot_id)
        if success:
            self._log_rollback(snapshot_id)
        return success
```

---

## 9. Checklist Implementasi

### Phase 1: Core Reload

- [ ] Implementasi `SafeReloader` dengan `importlib.reload()`
- [ ] Implementasi `StateManager` untuk state preservation
- [ ] Implementasi `RollbackManager` dengan snapshot/restore
- [ ] Test: reload module sederhana, verify state preserved
- [ ] Test: reload dengan bug, verify auto-rollback

### Phase 2: Safety

- [ ] Implementasi `SafetyGuards` dengan pre/post checks
- [ ] Definisikan `LOCKED_MODULES` dan `HIGH_RISK_MODULES`
- [ ] Implementasi market hours check (WIB timezone)
- [ ] Implementasi active trades check
- [ ] Test: swap saat market open → blocked
- [ ] Test: swap saat market closed → allowed

### Phase 3: Integration

- [ ] Integrasikan dengan Integrator Agent (dokumen 67)
- [ ] Tambah `hot_swap_log` table ke database
- [ ] Tambah Telegram notification untuk setiap swap
- [ ] Implementasi `DependencyResolver` untuk reload order
- [ ] E2E test: trigger → build → validate → swap → verify → rollback

### Phase 4: Hardening

- [ ] Tambah concurrent swap protection (mutex per module)
- [ ] Tambah swap rate limiting (max 1 swap per module per 5 menit)
- [ ] Tambah swap cooldown setelah rollback (10 menit)
- [ ] Tambah dashboard: swap history, success rate, active snapshots
- [ ] Tambah alert: "3 consecutive swap failures → disable self-evolution"

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| LLM Agent Layer | `67-llm-agent-layer-self-evolution.md` |
| Sandbox execution | `68-sandbox-execution-self-generated-code.md` |
| Knowledge base | `69-knowledge-base-persistent-memory.md` |
| Change & release management | `50-change-release-management-trading.md` |
| Deployment & DevOps | `27-deployment-devops-trading.md` |
| Event-driven architecture | `65-event-driven-event-sourcing.md` |
| Timezone & market hours | `36-gap-data-timezone-global-idx.md` |

---

## Referensi Eksternal

1. **SelfEvolve** — `importlib.reload()` untuk runtime self-extension (arxiv.org/abs/2604.16314, 2026) — "newly generated functions can be promoted from sandbox to permanent system integration: added to the knowledge base and immediately accessible without restart (through the importlib.reload() Python feature)"
2. **Python docs** — `importlib.reload()` — https://docs.python.org/3/library/importlib.html
3. **Blue-green deployment** — Analog untuk process-level swap (martinfowler.com)
4. **Canary release** — Analog untuk gradual rollout (dokumen 50)

---

> **Catatan:** Hot-swap adalah **jembatan** antara sandbox dan production. Tanpa hot-swap, setiap self-evolution cycle membutuhkan restart sistem — yang tidak feasible untuk trading system yang harus berjalan terus-menerus. Dengan hot-swap, sistem dapat berevolusi saat berjalan, seperti organisme hidup yang beregenerasi.
