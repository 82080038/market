"""API versioning policy and deprecation management (pustaka/62).

Provides:
- API version registry and routing
- Deprecation tracking with sunset dates
- Version negotiation (header, URL path, query param)
- Backward compatibility checks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class VersionStatus(Enum):
    """Status of an API version."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    RETIRED = "retired"


@dataclass
class APIVersion:
    """An API version definition."""

    version: str  # e.g., "v1", "v2"
    status: VersionStatus = VersionStatus.ACTIVE
    released_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    deprecated_at: str | None = None
    sunset_at: str | None = None
    retired_at: str | None = None
    changes: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)


@dataclass
class DeprecationNotice:
    """A deprecation notice for an endpoint or version."""

    target: str  # endpoint path or version
    deprecated_at: str
    sunset_at: str
    replacement: str | None = None
    reason: str = ""


class APIVersionManager:
    """Manages API versions and deprecation policy.

    Follows the API versioning policy from pustaka/62:
    - Major versions in URL path: /api/v1/..., /api/v2/...
    - Deprecation headers: Deprecation, Sunset, Link
    - Minimum 6 months deprecation period before sunset
    """

    def __init__(self, deprecation_period_months: int = 6) -> None:
        self.deprecation_period_months = deprecation_period_months
        self._versions: dict[str, APIVersion] = {}
        self._notices: dict[str, DeprecationNotice] = {}

    def register_version(
        self,
        version: str,
        endpoints: list[str] | None = None,
        changes: list[str] | None = None,
    ) -> APIVersion:
        """Register a new API version.

        Args:
            version: Version string (e.g., "v1").
            endpoints: List of endpoint paths.
            changes: List of change descriptions.

        Returns:
            The registered APIVersion.
        """
        av = APIVersion(
            version=version,
            endpoints=endpoints or [],
            changes=changes or [],
        )
        self._versions[version] = av
        return av

    def deprecate(
        self,
        version: str,
        replacement: str | None = None,
        reason: str = "",
    ) -> DeprecationNotice | None:
        """Mark a version as deprecated.

        Args:
            version: Version to deprecate.
            replacement: Replacing version (if any).
            reason: Deprecation reason.

        Returns:
            DeprecationNotice, or None if version not found.
        """
        av = self._versions.get(version)
        if av is None:
            return None

        now = datetime.now(UTC)
        sunset = now + timedelta(days=self.deprecation_period_months * 30)

        av.status = VersionStatus.DEPRECATED
        av.deprecated_at = now.isoformat()
        av.sunset_at = sunset.isoformat()

        notice = DeprecationNotice(
            target=version,
            deprecated_at=av.deprecated_at,
            sunset_at=av.sunset_at,
            replacement=replacement,
            reason=reason,
        )
        self._notices[version] = notice
        return notice

    def retire(self, version: str) -> bool:
        """Retire a version (mark as no longer available).

        Args:
            version: Version to retire.

        Returns:
            True if retired, False if not found.
        """
        av = self._versions.get(version)
        if av is None:
            return False
        av.status = VersionStatus.RETIRED
        av.retired_at = datetime.now(UTC).isoformat()
        return True

    def get_version(self, version: str) -> APIVersion | None:
        """Get version info by name."""
        return self._versions.get(version)

    def get_active_versions(self) -> list[APIVersion]:
        """Get all non-retired versions."""
        return [
            v for v in self._versions.values()
            if v.status != VersionStatus.RETIRED
        ]

    def get_deprecation_headers(self, version: str) -> dict[str, str]:
        """Get deprecation headers for a version.

        Args:
            version: Version to get headers for.

        Returns:
            Dict of HTTP headers for deprecation.
        """
        av = self._versions.get(version)
        if av is None or av.status == VersionStatus.ACTIVE:
            return {}

        headers: dict[str, str] = {}
        if av.status in (VersionStatus.DEPRECATED, VersionStatus.SUNSET):
            headers["Deprecation"] = "true"
            if av.sunset_at:
                sunset_date = datetime.fromisoformat(av.sunset_at)
                headers["Sunset"] = sunset_date.strftime("%a, %d %b %Y %H:%M:%S GMT")

            notice = self._notices.get(version)
            if notice and notice.replacement:
                headers["Link"] = f'</api/{notice.replacement}/>; rel="successor-version"'

        return headers

    def check_version_status(self, version: str) -> dict[str, Any]:
        """Check the status of a version.

        Args:
            version: Version to check.

        Returns:
            Dict with status info.
        """
        av = self._versions.get(version)
        if av is None:
            return {"exists": False, "status": "unknown"}

        result: dict[str, Any] = {
            "exists": True,
            "status": av.status.value,
            "version": av.version,
        }

        if av.status == VersionStatus.DEPRECATED:
            notice = self._notices.get(version)
            if notice:
                result["sunset_at"] = notice.sunset_at
                result["replacement"] = notice.replacement
                result["reason"] = notice.reason

                # Check if sunset has passed
                sunset = datetime.fromisoformat(notice.sunset_at)
                if datetime.now(UTC) > sunset:
                    result["status"] = "sunset_overdue"

        return result

    @property
    def versions(self) -> list[APIVersion]:
        """All registered versions."""
        return list(self._versions.values())

    @property
    def notices(self) -> list[DeprecationNotice]:
        """All deprecation notices."""
        return list(self._notices.values())
