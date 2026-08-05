"""Vendor health check and SLA monitoring (pustaka/82).

Provides:
- Vendor/service registry
- Health check polling
- SLA tracking (uptime, response time, error rate)
- Alerting on SLA breach
- Vendor status dashboard data
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class VendorStatus(Enum):
    """Status of a vendor service."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class SLAConfig:
    """SLA configuration for a vendor."""

    target_uptime_pct: float = 99.9
    max_response_time_ms: float = 1000.0
    max_error_rate_pct: float = 1.0
    check_interval_seconds: int = 60


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    vendor_id: str
    status: VendorStatus
    response_time_ms: float = 0.0
    status_code: int = 200
    error_message: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class VendorRecord:
    """A registered vendor/service."""

    vendor_id: str
    name: str
    endpoint: str
    sla_config: SLAConfig = field(default_factory=SLAConfig)
    status: VendorStatus = VendorStatus.UNKNOWN
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    health_history: list[HealthCheckResult] = field(default_factory=list)
    uptime_seconds: float = 0.0
    total_seconds: float = 0.0
    avg_response_time_ms: float = 0.0
    error_count: int = 0
    total_checks: int = 0


class VendorHealthMonitor:
    """Monitors vendor health and SLA compliance."""

    def __init__(self) -> None:
        self._vendors: dict[str, VendorRecord] = {}

    def register_vendor(
        self,
        vendor_id: str,
        name: str,
        endpoint: str,
        sla_config: SLAConfig | None = None,
    ) -> VendorRecord:
        """Register a new vendor for monitoring.

        Args:
            vendor_id: Unique vendor identifier.
            name: Human-readable name.
            endpoint: Health check endpoint URL.
            sla_config: SLA configuration.

        Returns:
            The registered VendorRecord.
        """
        vendor = VendorRecord(
            vendor_id=vendor_id,
            name=name,
            endpoint=endpoint,
            sla_config=sla_config or SLAConfig(),
        )
        self._vendors[vendor_id] = vendor
        return vendor

    def record_health_check(
        self,
        vendor_id: str,
        status: VendorStatus,
        response_time_ms: float = 0.0,
        status_code: int = 200,
        error_message: str = "",
    ) -> HealthCheckResult | None:
        """Record a health check result.

        Args:
            vendor_id: Vendor to record for.
            status: Health status.
            response_time_ms: Response time.
            status_code: HTTP status code.
            error_message: Error message if any.

        Returns:
            HealthCheckResult, or None if vendor not found.
        """
        vendor = self._vendors.get(vendor_id)
        if vendor is None:
            return None

        result = HealthCheckResult(
            vendor_id=vendor_id,
            status=status,
            response_time_ms=response_time_ms,
            status_code=status_code,
            error_message=error_message,
        )

        vendor.health_history.append(result)
        vendor.status = status
        vendor.total_checks += 1

        # Update metrics
        if status == VendorStatus.HEALTHY:
            vendor.uptime_seconds += vendor.sla_config.check_interval_seconds
        vendor.total_seconds += vendor.sla_config.check_interval_seconds

        # Update average response time (rolling)
        n = len(vendor.health_history)
        vendor.avg_response_time_ms = (
            (vendor.avg_response_time_ms * (n - 1) + response_time_ms) / n
        )

        if status != VendorStatus.HEALTHY:
            vendor.error_count += 1

        return result

    def check_sla_compliance(self, vendor_id: str) -> dict[str, Any]:
        """Check if a vendor is meeting SLA.

        Args:
            vendor_id: Vendor to check.

        Returns:
            Dict with SLA compliance details.
        """
        vendor = self._vendors.get(vendor_id)
        if vendor is None:
            return {"vendor_id": vendor_id, "found": False}

        uptime_pct = (
            (vendor.uptime_seconds / vendor.total_seconds * 100)
            if vendor.total_seconds > 0 else 0.0
        )
        error_rate_pct = (
            (vendor.error_count / vendor.total_checks * 100)
            if vendor.total_checks > 0 else 0.0
        )

        sla = vendor.sla_config
        violations: list[str] = []

        if uptime_pct < sla.target_uptime_pct:
            violations.append(
                f"Uptime {uptime_pct:.2f}% < target {sla.target_uptime_pct}%",
            )

        if vendor.avg_response_time_ms > sla.max_response_time_ms:
            violations.append(
                f"Avg response {vendor.avg_response_time_ms:.0f}ms "
                f"> max {sla.max_response_time_ms}ms",
            )

        if error_rate_pct > sla.max_error_rate_pct:
            violations.append(
                f"Error rate {error_rate_pct:.2f}% > max {sla.max_error_rate_pct}%",
            )

        return {
            "vendor_id": vendor_id,
            "found": True,
            "name": vendor.name,
            "status": vendor.status.value,
            "uptime_pct": round(uptime_pct, 4),
            "avg_response_time_ms": round(vendor.avg_response_time_ms, 2),
            "error_rate_pct": round(error_rate_pct, 4),
            "total_checks": vendor.total_checks,
            "sla_violations": violations,
            "sla_compliant": len(violations) == 0,
        }

    def get_vendor(self, vendor_id: str) -> VendorRecord | None:
        """Get a vendor record."""
        return self._vendors.get(vendor_id)

    def get_all_vendors(self) -> list[VendorRecord]:
        """Get all registered vendors."""
        return list(self._vendors.values())

    def get_healthy_vendors(self) -> list[VendorRecord]:
        """Get all healthy vendors."""
        return [v for v in self._vendors.values() if v.status == VendorStatus.HEALTHY]

    def get_degraded_vendors(self) -> list[VendorRecord]:
        """Get all degraded vendors."""
        return [v for v in self._vendors.values() if v.status == VendorStatus.DEGRADED]

    def get_down_vendors(self) -> list[VendorRecord]:
        """Get all down vendors."""
        return [v for v in self._vendors.values() if v.status == VendorStatus.DOWN]

    def dashboard(self) -> list[dict[str, Any]]:
        """Get dashboard summary for all vendors.

        Returns:
            List of vendor summary dicts.
        """
        return [
            self.check_sla_compliance(v.vendor_id)
            for v in self._vendors.values()
        ]
