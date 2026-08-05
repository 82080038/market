"""UU PDP (No. 27/2022) compliance checklist (pustaka/41).

Provides:
- Compliance checklist for Indonesian Personal Data Protection Law
- Data processing activity tracking
- Data subject rights management
- Breach notification workflow
- Data retention policy enforcement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ChecklistStatus(Enum):
    """Status of a compliance checklist item."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    IN_PROGRESS = "in_progress"
    NOT_APPLICABLE = "not_applicable"


class DataSubjectRight(Enum):
    """Rights of data subjects under UU PDP."""

    ACCESS = "access"
    CORRECTION = "correction"
    ERASURE = "erasure"
    PORTABILITY = "portability"
    OBJECTION = "objection"
    RESTRICTION = "restriction"
    WITHDRAW_CONSENT = "withdraw_consent"


@dataclass
class ChecklistItem:
    """A single compliance checklist item."""

    item_id: str
    category: str
    description: str
    status: ChecklistStatus = ChecklistStatus.NOT_APPLICABLE
    evidence: str = ""
    last_checked: str = ""
    notes: str = ""


@dataclass
class DataProcessingActivity:
    """A registered data processing activity."""

    activity_id: str
    purpose: str
    data_types: list[str]
    legal_basis: str
    retention_period_days: int
    third_party_sharing: bool = False
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DataSubjectRequest:
    """A data subject rights request."""

    request_id: str
    right: DataSubjectRight
    subject_id: str
    description: str = ""
    status: str = "pending"  # pending, processing, fulfilled, rejected
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    fulfilled_at: str | None = None
    response_notes: str = ""


@dataclass
class BreachRecord:
    """A data breach record."""

    breach_id: str
    detected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    severity: str = "low"
    description: str = ""
    affected_records: int = 0
    notified: bool = False
    notified_at: str | None = None
    resolution: str = ""


class PDPCompliance:
    """UU PDP compliance management.

    Implements compliance checklist based on UU No. 27/2022
    (Indonesian Personal Data Protection Law).
    """

    def __init__(self) -> None:
        self._checklist: dict[str, ChecklistItem] = {}
        self._activities: dict[str, DataProcessingActivity] = {}
        self._requests: dict[str, DataSubjectRequest] = {}
        self._breaches: dict[str, BreachRecord] = {}
        self._request_counter = 0
        self._breach_counter = 0
        self._init_default_checklist()

    def _init_default_checklist(self) -> None:
        """Initialize default UU PDP compliance checklist."""
        items = [
            ("PDP-001", "Consent", "Obtain explicit consent for data processing"),
            ("PDP-002", "Consent", "Provide mechanism to withdraw consent"),
            ("PDP-003", "Transparency", "Maintain data processing activity register"),
            ("PDP-004", "Transparency", "Privacy policy published and accessible"),
            ("PDP-005", "Data Minimization", "Only collect necessary data"),
            ("PDP-006", "Data Quality", "Ensure data accuracy and completeness"),
            ("PDP-007", "Retention", "Define and enforce data retention periods"),
            ("PDP-008", "Security", "Implement technical/organizational measures"),
            ("PDP-009", "Security", "Encrypt personal data at rest and in transit"),
            ("PDP-010", "Rights", "Process data subject access requests in 3 days"),
            ("PDP-011", "Rights", "Process data subject correction requests"),
            ("PDP-012", "Rights", "Process data subject erasure requests"),
            ("PDP-013", "Rights", "Support data portability"),
            ("PDP-014", "Breach", "Notify OJK within 3 days of breach discovery"),
            ("PDP-015", "Breach", "Notify affected data subjects of breach"),
            ("PDP-016", "Breach", "Maintain breach register"),
            ("PDP-017", "DPO", "Appoint Data Protection Officer (if required)"),
            ("PDP-018", "Transfer", "Ensure safeguards for cross-border transfer"),
        ]

        for item_id, category, desc in items:
            self._checklist[item_id] = ChecklistItem(
                item_id=item_id,
                category=category,
                description=desc,
                status=ChecklistStatus.NOT_APPLICABLE,
            )

    def update_checklist_item(
        self,
        item_id: str,
        status: ChecklistStatus,
        evidence: str = "",
        notes: str = "",
    ) -> ChecklistItem | None:
        """Update a checklist item.

        Args:
            item_id: Item to update.
            status: New status.
            evidence: Evidence of compliance.
            notes: Additional notes.

        Returns:
            Updated ChecklistItem, or None if not found.
        """
        item = self._checklist.get(item_id)
        if item is None:
            return None

        item.status = status
        item.evidence = evidence
        item.notes = notes
        item.last_checked = datetime.now(UTC).isoformat()
        return item

    def register_processing_activity(
        self,
        activity_id: str,
        purpose: str,
        data_types: list[str],
        legal_basis: str,
        retention_period_days: int,
        third_party_sharing: bool = False,
    ) -> DataProcessingActivity:
        """Register a data processing activity.

        Args:
            activity_id: Unique activity ID.
            purpose: Purpose of processing.
            data_types: Types of personal data processed.
            legal_basis: Legal basis for processing.
            retention_period_days: Data retention period.
            third_party_sharing: Whether data is shared with third parties.

        Returns:
            The registered DataProcessingActivity.
        """
        activity = DataProcessingActivity(
            activity_id=activity_id,
            purpose=purpose,
            data_types=data_types,
            legal_basis=legal_basis,
            retention_period_days=retention_period_days,
            third_party_sharing=third_party_sharing,
        )
        self._activities[activity_id] = activity
        return activity

    def create_subject_request(
        self,
        right: DataSubjectRight,
        subject_id: str,
        description: str = "",
    ) -> DataSubjectRequest:
        """Create a data subject rights request.

        Args:
            right: Type of right being exercised.
            subject_id: Data subject identifier.
            description: Request details.

        Returns:
            The created DataSubjectRequest.
        """
        self._request_counter += 1
        req_id = f"DSR-{self._request_counter:04d}"
        request = DataSubjectRequest(
            request_id=req_id,
            right=right,
            subject_id=subject_id,
            description=description,
        )
        self._requests[req_id] = request
        return request

    def fulfill_request(
        self,
        request_id: str,
        response_notes: str = "",
    ) -> DataSubjectRequest | None:
        """Mark a data subject request as fulfilled.

        Args:
            request_id: Request to fulfill.
            response_notes: Notes about the fulfillment.

        Returns:
            Updated DataSubjectRequest, or None if not found.
        """
        request = self._requests.get(request_id)
        if request is None:
            return None

        request.status = "fulfilled"
        request.fulfilled_at = datetime.now(UTC).isoformat()
        request.response_notes = response_notes
        return request

    def record_breach(
        self,
        severity: str = "low",
        description: str = "",
        affected_records: int = 0,
    ) -> BreachRecord:
        """Record a data breach.

        Args:
            severity: Breach severity.
            description: Breach description.
            affected_records: Number of affected records.

        Returns:
            The created BreachRecord.
        """
        self._breach_counter += 1
        breach_id = f"BR-{self._breach_counter:04d}"
        breach = BreachRecord(
            breach_id=breach_id,
            severity=severity,
            description=description,
            affected_records=affected_records,
        )
        self._breaches[breach_id] = breach
        return breach

    def notify_breach(self, breach_id: str) -> BreachRecord | None:
        """Mark a breach as notified to authorities.

        Args:
            breach_id: Breach to mark as notified.

        Returns:
            Updated BreachRecord, or None if not found.
        """
        breach = self._breaches.get(breach_id)
        if breach is None:
            return None
        breach.notified = True
        breach.notified_at = datetime.now(UTC).isoformat()
        return breach

    def compliance_summary(self) -> dict[str, Any]:
        """Get compliance summary.

        Returns:
            Dict with compliance statistics.
        """
        total = len(self._checklist)
        vals = list(self._checklist.values())
        compliant = sum(1 for i in vals if i.status == ChecklistStatus.COMPLIANT)
        non_compliant = sum(1 for i in vals if i.status == ChecklistStatus.NON_COMPLIANT)
        in_progress = sum(1 for i in vals if i.status == ChecklistStatus.IN_PROGRESS)
        not_applicable = sum(1 for i in vals if i.status == ChecklistStatus.NOT_APPLICABLE)

        return {
            "total_items": total,
            "compliant": compliant,
            "non_compliant": non_compliant,
            "in_progress": in_progress,
            "not_applicable": not_applicable,
            "compliance_rate": round(compliant / total * 100, 2) if total > 0 else 0.0,
            "pending_requests": sum(1 for r in self._requests.values() if r.status == "pending"),
            "unnotified_breaches": sum(1 for b in self._breaches.values() if not b.notified),
            "registered_activities": len(self._activities),
        }

    @property
    def checklist(self) -> list[ChecklistItem]:
        """All checklist items."""
        return list(self._checklist.values())

    @property
    def activities(self) -> list[DataProcessingActivity]:
        """All processing activities."""
        return list(self._activities.values())

    @property
    def requests(self) -> list[DataSubjectRequest]:
        """All data subject requests."""
        return list(self._requests.values())

    @property
    def breaches(self) -> list[BreachRecord]:
        """All breach records."""
        return list(self._breaches.values())
