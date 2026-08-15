"""Customer support and dispute resolution workflow (pustaka/42).

Provides:
- Support ticket management
- Dispute resolution workflow
- SLA tracking for support responses
- Escalation rules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum


class TicketStatus(Enum):
    """Support ticket status."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_RESPONSE = "waiting_response"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class TicketPriority(Enum):
    """Support ticket priority."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class DisputeStatus(Enum):
    """Dispute resolution status."""

    FILED = "filed"
    UNDER_REVIEW = "under_review"
    INVESTIGATING = "investigating"
    PROPOSED_RESOLUTION = "proposed_resolution"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


@dataclass
class SupportTicket:
    """A customer support ticket."""

    ticket_id: str
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.NORMAL
    status: TicketStatus = TicketStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None
    category: str = "general"
    messages: list[dict[str, str]] = field(default_factory=list)
    assigned_to: str | None = None
    sla_deadline: str = ""


@dataclass
class Dispute:
    """A customer dispute."""

    dispute_id: str
    ticket_id: str
    subject: str
    description: str
    status: DisputeStatus = DisputeStatus.FILED
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolution_proposed: str = ""
    resolution_accepted: bool = False
    investigation_notes: list[str] = field(default_factory=list)


class SupportManager:
    """Customer support and dispute resolution manager."""

    def __init__(
        self,
        sla_hours_urgent: int = 2,
        sla_hours_high: int = 8,
        sla_hours_normal: int = 24,
        sla_hours_low: int = 72,
    ) -> None:
        self.sla_hours = {
            TicketPriority.URGENT: sla_hours_urgent,
            TicketPriority.HIGH: sla_hours_high,
            TicketPriority.NORMAL: sla_hours_normal,
            TicketPriority.LOW: sla_hours_low,
        }
        self._tickets: dict[str, SupportTicket] = {}
        self._disputes: dict[str, Dispute] = {}
        self._ticket_counter = 0
        self._dispute_counter = 0

    def create_ticket(
        self,
        subject: str,
        description: str,
        priority: TicketPriority = TicketPriority.NORMAL,
        category: str = "general",
    ) -> SupportTicket:
        """Create a new support ticket.

        Args:
            subject: Ticket subject.
            description: Issue description.
            priority: Priority level.
            category: Ticket category.

        Returns:
            The created SupportTicket.
        """
        self._ticket_counter += 1
        ticket_id = f"TKT-{self._ticket_counter:05d}"
        sla_hours = self.sla_hours[priority]
        deadline = datetime.now(UTC) + timedelta(hours=sla_hours)

        ticket = SupportTicket(
            ticket_id=ticket_id,
            subject=subject,
            description=description,
            priority=priority,
            category=category,
            sla_deadline=deadline.isoformat(),
        )
        ticket.messages.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "from": "user",
            "message": description,
        })
        self._tickets[ticket_id] = ticket
        return ticket

    def add_message(self, ticket_id: str, message: str, from_user: str = "support") -> bool:
        """Add a message to a ticket.

        Args:
            ticket_id: Ticket to add message to.
            message: Message content.
            from_user: Who sent the message.

        Returns:
            True if added, False if ticket not found.
        """
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return False

        ticket.messages.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "from": from_user,
            "message": message,
        })
        ticket.updated_at = datetime.now(UTC).isoformat()
        return True

    def resolve_ticket(self, ticket_id: str, resolution: str = "") -> SupportTicket | None:
        """Resolve a support ticket.

        Args:
            ticket_id: Ticket to resolve.
            resolution: Resolution message.

        Returns:
            Updated SupportTicket, or None if not found.
        """
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return None

        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = datetime.now(UTC).isoformat()
        ticket.updated_at = ticket.resolved_at
        if resolution:
            ticket.messages.append({
                "timestamp": datetime.now(UTC).isoformat(),
                "from": "support",
                "message": resolution,
            })
        return ticket

    def escalate_ticket(self, ticket_id: str) -> SupportTicket | None:
        """Escalate a support ticket.

        Args:
            ticket_id: Ticket to escalate.

        Returns:
            Updated SupportTicket, or None if not found.
        """
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return None
        ticket.status = TicketStatus.ESCALATED
        ticket.updated_at = datetime.now(UTC).isoformat()
        return ticket

    def file_dispute(
        self,
        ticket_id: str,
        subject: str,
        description: str,
    ) -> Dispute | None:
        """File a dispute from a support ticket.

        Args:
            ticket_id: Related ticket ID.
            subject: Dispute subject.
            description: Dispute description.

        Returns:
            The created Dispute, or None if ticket not found.
        """
        if ticket_id not in self._tickets:
            return None

        self._dispute_counter += 1
        dispute_id = f"DSP-{self._dispute_counter:05d}"
        dispute = Dispute(
            dispute_id=dispute_id,
            ticket_id=ticket_id,
            subject=subject,
            description=description,
        )
        self._disputes[dispute_id] = dispute
        return dispute

    def update_dispute(
        self,
        dispute_id: str,
        status: DisputeStatus,
        notes: str = "",
        resolution: str = "",
    ) -> Dispute | None:
        """Update a dispute.

        Args:
            dispute_id: Dispute to update.
            status: New status.
            notes: Investigation notes.
            resolution: Proposed resolution.

        Returns:
            Updated Dispute, or None if not found.
        """
        dispute = self._disputes.get(dispute_id)
        if dispute is None:
            return None

        dispute.status = status
        dispute.updated_at = datetime.now(UTC).isoformat()
        if notes:
            dispute.investigation_notes.append(notes)
        if resolution:
            dispute.resolution_proposed = resolution
        return dispute

    def check_sla_breach(self) -> list[SupportTicket]:
        """Check for tickets that have breached SLA.

        Returns:
            List of tickets with breached SLA.
        """
        now = datetime.now(UTC)
        breached: list[SupportTicket] = []

        for ticket in self._tickets.values():
            if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
                continue
            if ticket.sla_deadline:
                deadline = datetime.fromisoformat(ticket.sla_deadline)
                if now >= deadline:
                    breached.append(ticket)

        return breached

    def get_ticket(self, ticket_id: str) -> SupportTicket | None:
        """Get a ticket by ID."""
        return self._tickets.get(ticket_id)

    def get_dispute(self, dispute_id: str) -> Dispute | None:
        """Get a dispute by ID."""
        return self._disputes.get(dispute_id)

    @property
    def tickets(self) -> list[SupportTicket]:
        """All tickets."""
        return list(self._tickets.values())

    @property
    def disputes(self) -> list[Dispute]:
        """All disputes."""
        return list(self._disputes.values())

    @property
    def open_tickets(self) -> list[SupportTicket]:
        """All open tickets."""
        return [
            t for t in self._tickets.values()
            if t.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)
        ]
