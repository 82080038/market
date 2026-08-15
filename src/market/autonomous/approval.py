"""Human-in-the-loop approval bot (pustaka/72).

Provides an approval workflow for AI-proposed actions:
- Pending approval queue
- Telegram notification (stub — actual sending requires bot token)
- Approval/rejection interface
- Timeout-based auto-rejection
- Audit log of all approvals/rejections
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class ApprovalStatus(Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


@dataclass
class ApprovalRequest:
    """A request for human approval."""

    request_id: str
    cycle_id: str
    action_type: str
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = field(
        default_factory=lambda: (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
    )
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: str | None = None
    decided_by: str | None = None
    notes: str = ""


@dataclass
class ApprovalLog:
    """Audit log entry for approval actions."""

    request_id: str
    action: str  # created, approved, rejected, expired, withdrawn
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    actor: str = "system"
    notes: str = ""


class ApprovalBot:
    """Human-in-the-loop approval bot.

    In production, this would integrate with Telegram Bot API.
    For now, it provides an in-memory approval queue with
    notification hooks.
    """

    def __init__(
        self,
        auto_expire_hours: int = 24,
        telegram_bot_token: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> None:
        self.auto_expire_hours = auto_expire_hours
        self._telegram_bot_token = telegram_bot_token
        self._telegram_chat_id = telegram_chat_id
        self._queue: dict[str, ApprovalRequest] = {}
        self._log: list[ApprovalLog] = []
        self._counter = 0
        self._notification_hook: Any = None

    def set_notification_hook(self, hook: Any) -> None:
        """Set a custom notification hook (e.g., for testing).

        Args:
            hook: Callable that receives an ApprovalRequest.
        """
        self._notification_hook = hook

    def request_approval(
        self,
        cycle_id: str,
        action_type: str,
        description: str,
        details: dict[str, Any] | None = None,
        expire_hours: int | None = None,
    ) -> ApprovalRequest:
        """Create a new approval request.

        Args:
            cycle_id: Agent cycle ID.
            action_type: Type of action (patch_code, retrain, etc.).
            description: Human-readable description.
            details: Additional details.
            expire_hours: Override expiration time.

        Returns:
            The created ApprovalRequest.
        """
        self._counter += 1
        req_id = f"approval_{self._counter:04d}"
        # Use expire_hours if explicitly provided (including 0), else fall back to default
        if expire_hours is not None:
            hours = expire_hours
        else:
            hours = self.auto_expire_hours

        request = ApprovalRequest(
            request_id=req_id,
            cycle_id=cycle_id,
            action_type=action_type,
            description=description,
            details=details or {},
            expires_at=(datetime.now(UTC) + timedelta(hours=hours)).isoformat(),
        )

        self._queue[req_id] = request
        self._log.append(ApprovalLog(
            request_id=req_id,
            action="created",
            actor="agent",
        ))

        # Send notification
        self._notify(request)
        return request

    def approve(
        self,
        request_id: str,
        decided_by: str = "human",
        notes: str = "",
    ) -> ApprovalRequest | None:
        """Approve a pending request.

        Args:
            request_id: ID of the request to approve.
            decided_by: Who approved it.
            notes: Optional notes.

        Returns:
            Updated ApprovalRequest, or None if not found.
        """
        request = self._queue.get(request_id)
        if request is None or request.status != ApprovalStatus.PENDING:
            return None

        request.status = ApprovalStatus.APPROVED
        request.decided_at = datetime.now(UTC).isoformat()
        request.decided_by = decided_by
        request.notes = notes

        self._log.append(ApprovalLog(
            request_id=request_id,
            action="approved",
            actor=decided_by,
            notes=notes,
        ))
        return request

    def reject(
        self,
        request_id: str,
        decided_by: str = "human",
        notes: str = "",
    ) -> ApprovalRequest | None:
        """Reject a pending request.

        Args:
            request_id: ID of the request to reject.
            decided_by: Who rejected it.
            notes: Optional notes.

        Returns:
            Updated ApprovalRequest, or None if not found.
        """
        request = self._queue.get(request_id)
        if request is None or request.status != ApprovalStatus.PENDING:
            return None

        request.status = ApprovalStatus.REJECTED
        request.decided_at = datetime.now(UTC).isoformat()
        request.decided_by = decided_by
        request.notes = notes

        self._log.append(ApprovalLog(
            request_id=request_id,
            action="rejected",
            actor=decided_by,
            notes=notes,
        ))
        return request

    def withdraw(self, request_id: str) -> ApprovalRequest | None:
        """Withdraw a pending request (by the agent).

        Args:
            request_id: ID of the request to withdraw.

        Returns:
            Updated ApprovalRequest, or None if not found.
        """
        request = self._queue.get(request_id)
        if request is None or request.status != ApprovalStatus.PENDING:
            return None

        request.status = ApprovalStatus.WITHDRAWN
        request.decided_at = datetime.now(UTC).isoformat()

        self._log.append(ApprovalLog(
            request_id=request_id,
            action="withdrawn",
            actor="agent",
        ))
        return request

    def expire_stale(self) -> list[ApprovalRequest]:
        """Expire all stale (past deadline) pending requests.

        Returns:
            List of expired requests.
        """
        now = datetime.now(UTC)
        expired: list[ApprovalRequest] = []

        for request in self._queue.values():
            if request.status != ApprovalStatus.PENDING:
                continue
            expires = datetime.fromisoformat(request.expires_at)
            if now >= expires:
                request.status = ApprovalStatus.EXPIRED
                request.decided_at = now.isoformat()
                self._log.append(ApprovalLog(
                    request_id=request.request_id,
                    action="expired",
                    actor="system",
                ))
                expired.append(request)

        return expired

    def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        return [r for r in self._queue.values() if r.status == ApprovalStatus.PENDING]

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        """Get a specific request by ID."""
        return self._queue.get(request_id)

    @property
    def log(self) -> list[ApprovalLog]:
        """Full audit log."""
        return self._log

    def _notify(self, request: ApprovalRequest) -> None:
        """Send notification about a new approval request.

        In production, this would send a Telegram message.
        For now, it calls the notification hook if set.
        """
        if self._notification_hook:
            self._notification_hook(request)
        else:
            if self._telegram_bot_token and self._telegram_chat_id:
                # In production: send via Telegram Bot API
                pass
