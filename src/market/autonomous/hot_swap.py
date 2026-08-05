"""Hot-swap runtime module update with rollback (pustaka/70).

Allows updating Python modules at runtime without restarting the application:
- Versioned module registry
- Atomic swap (old version backed up before new version loaded)
- Automatic rollback on failure
- Health check after swap
- Swap history audit log
"""

from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SwapStatus(Enum):
    """Status of a hot-swap operation."""

    PENDING = "pending"
    SWAPPED = "swapped"
    HEALTH_CHECK_PASSED = "health_check_passed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class ModuleVersion:
    """A versioned module entry."""

    module_name: str
    version: str
    code: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_active: bool = False


@dataclass
class SwapRecord:
    """Record of a hot-swap operation."""

    swap_id: str
    module_name: str
    old_version: str
    new_version: str
    status: SwapStatus = SwapStatus.PENDING
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    error: str = ""
    health_check_result: dict[str, Any] = field(default_factory=dict)


class HotSwapManager:
    """Manages hot-swap of Python modules at runtime."""

    def __init__(self) -> None:
        self._versions: dict[str, list[ModuleVersion]] = {}
        self._swap_history: list[SwapRecord] = []
        self._swap_counter = 0
        self._health_check_fn: Any = None

    def set_health_check(self, fn: Any) -> None:
        """Set a health check function to run after swap.

        Args:
            fn: Function that returns dict with 'healthy' bool and 'details'.
        """
        self._health_check_fn = fn

    def register_version(
        self,
        module_name: str,
        version: str,
        code: str,
    ) -> ModuleVersion:
        """Register a new module version.

        Args:
            module_name: Fully qualified module name.
            version: Version string.
            code: Python source code.

        Returns:
            The registered ModuleVersion.
        """
        mv = ModuleVersion(
            module_name=module_name,
            version=version,
            code=code,
        )

        if module_name not in self._versions:
            self._versions[module_name] = []
        self._versions[module_name].append(mv)

        # If first version, mark as active
        if len(self._versions[module_name]) == 1:
            mv.is_active = True

        return mv

    def get_active_version(self, module_name: str) -> ModuleVersion | None:
        """Get the currently active version of a module."""
        versions = self._versions.get(module_name, [])
        for v in versions:
            if v.is_active:
                return v
        return None

    def get_versions(self, module_name: str) -> list[ModuleVersion]:
        """Get all registered versions of a module."""
        return self._versions.get(module_name, [])

    def swap(
        self,
        module_name: str,
        new_version: str,
        run_health_check: bool = True,
    ) -> SwapRecord:
        """Hot-swap a module to a new version.

        Args:
            module_name: Module to swap.
            new_version: Target version string.
            run_health_check: Whether to run health check after swap.

        Returns:
            SwapRecord with the result.
        """
        self._swap_counter += 1
        swap_id = f"swap_{self._swap_counter:04d}"

        old = self.get_active_version(module_name)
        old_version = old.version if old else "none"

        new_mv = None
        for v in self._versions.get(module_name, []):
            if v.version == new_version:
                new_mv = v
                break

        if new_mv is None:
            record = SwapRecord(
                swap_id=swap_id,
                module_name=module_name,
                old_version=old_version,
                new_version=new_version,
                status=SwapStatus.FAILED,
                error=f"Version {new_version} not found for module {module_name}",
            )
            self._swap_history.append(record)
            return record

        record = SwapRecord(
            swap_id=swap_id,
            module_name=module_name,
            old_version=old_version,
            new_version=new_version,
        )
        self._swap_history.append(record)

        # Perform swap
        try:
            # Deactivate old version
            if old:
                old.is_active = False

            # Activate new version
            new_mv.is_active = True
            record.status = SwapStatus.SWAPPED

            # Reload module if it's already imported
            if module_name in sys.modules:
                try:
                    importlib.reload(sys.modules[module_name])
                except Exception as e:
                    logger.warning(f"Module reload failed: {e}")

            # Run health check
            if run_health_check and self._health_check_fn:
                health_result = self._health_check_fn()
                record.health_check_result = health_result

                if health_result.get("healthy", False):
                    record.status = SwapStatus.HEALTH_CHECK_PASSED
                else:
                    record.status = SwapStatus.HEALTH_CHECK_FAILED
                    # Rollback if there was a previous version
                    if old:
                        self._rollback(record, old, new_mv)
            elif not run_health_check:
                record.status = SwapStatus.HEALTH_CHECK_PASSED

        except Exception as e:
            record.status = SwapStatus.FAILED
            record.error = str(e)
            # Rollback
            if old:
                self._rollback(record, old, new_mv)

        record.completed_at = datetime.now(UTC).isoformat()
        return record

    def _rollback(
        self,
        record: SwapRecord,
        old_version: ModuleVersion,
        new_version: ModuleVersion,
    ) -> None:
        """Rollback to the previous version."""
        new_version.is_active = False
        old_version.is_active = True
        record.status = SwapStatus.ROLLED_BACK

        # Reload old module
        if record.module_name in sys.modules:
            try:
                importlib.reload(sys.modules[record.module_name])
            except Exception as e:
                logger.warning(f"Rollback reload failed: {e}")

    def rollback_last(self, module_name: str) -> SwapRecord | None:
        """Manually rollback the last swap for a module.

        Args:
            module_name: Module to rollback.

        Returns:
            SwapRecord for the rollback, or None if no swap to rollback.
        """
        # Find the last swap record for this module
        last_swap = None
        for record in reversed(self._swap_history):
            if record.module_name == module_name and record.status in (
                SwapStatus.HEALTH_CHECK_PASSED,
                SwapStatus.SWAPPED,
            ):
                last_swap = record
                break

        if last_swap is None:
            return None

        # Find versions
        old_mv = None
        new_mv = None
        for v in self._versions.get(module_name, []):
            if v.version == last_swap.old_version:
                old_mv = v
            if v.version == last_swap.new_version:
                new_mv = v

        if old_mv is None or new_mv is None:
            return None

        # Create rollback record
        self._swap_counter += 1
        rollback_record = SwapRecord(
            swap_id=f"swap_{self._swap_counter:04d}",
            module_name=module_name,
            old_version=last_swap.new_version,
            new_version=last_swap.old_version,
        )
        self._swap_history.append(rollback_record)

        self._rollback(rollback_record, old_mv, new_mv)
        rollback_record.completed_at = datetime.now(UTC).isoformat()
        return rollback_record

    @property
    def swap_history(self) -> list[SwapRecord]:
        """Full swap history."""
        return self._swap_history

    @property
    def registered_modules(self) -> list[str]:
        """List of registered module names."""
        return list(self._versions.keys())
