"""Incident response, disaster recovery, and operations runbooks (pustaka/47-50).

Provides:
- Incident management (create, track, resolve, post-mortem)
- DR runbook definitions and execution tracking
- Change/release management
- Operational runbook templates
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class IncidentSeverity(Enum):
    """Incident severity levels."""

    P0 = "p0"  # Critical — system down
    P1 = "p1"  # High — major functionality broken
    P2 = "p2"  # Medium — partial degradation
    P3 = "p3"  # Low — minor issue


class IncidentStatus(Enum):
    """Incident status."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    POST_MORTEM = "post_mortem"
    CLOSED = "closed"


@dataclass
class Incident:
    """An operational incident."""

    incident_id: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None
    description: str = ""
    root_cause: str = ""
    resolution: str = ""
    timeline: list[dict[str, str]] = field(default_factory=list)
    affected_components: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)


@dataclass
class RunbookStep:
    """A single step in an operational runbook."""

    step_number: int
    action: str
    expected_result: str = ""
    verification: str = ""
    estimated_time_minutes: int = 5


@dataclass
class Runbook:
    """An operational runbook."""

    runbook_id: str
    name: str
    description: str
    trigger: str  # When to execute this runbook
    steps: list[RunbookStep] = field(default_factory=list)
    last_executed: str | None = None
    execution_count: int = 0


@dataclass
class RunbookExecution:
    """Record of a runbook execution."""

    execution_id: str
    runbook_id: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    steps_completed: int = 0
    steps_total: int = 0
    success: bool = False
    notes: str = ""


class IncidentManager:
    """Manages operational incidents."""

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._counter = 0

    def create_incident(
        self,
        title: str,
        severity: IncidentSeverity,
        description: str = "",
        affected_components: list[str] | None = None,
    ) -> Incident:
        """Create a new incident.

        Args:
            title: Incident title.
            severity: Severity level.
            description: Incident description.
            affected_components: List of affected components.

        Returns:
            The created Incident.
        """
        self._counter += 1
        inc_id = f"INC-{self._counter:04d}"
        incident = Incident(
            incident_id=inc_id,
            title=title,
            severity=severity,
            description=description,
            affected_components=affected_components or [],
        )
        incident.timeline.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "Incident created",
            "actor": "system",
        })
        self._incidents[inc_id] = incident
        return incident

    def update_incident(
        self,
        incident_id: str,
        status: IncidentStatus | None = None,
        description: str | None = None,
        root_cause: str | None = None,
        resolution: str | None = None,
        timeline_action: str = "",
    ) -> Incident | None:
        """Update an incident.

        Args:
            incident_id: Incident to update.
            status: New status.
            description: Updated description.
            root_cause: Root cause analysis.
            resolution: Resolution description.
            timeline_action: Action to add to timeline.

        Returns:
            Updated Incident, or None if not found.
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None

        if status:
            incident.status = status
            if status == IncidentStatus.RESOLVED:
                incident.resolved_at = datetime.now(UTC).isoformat()

        if description is not None:
            incident.description = description
        if root_cause is not None:
            incident.root_cause = root_cause
        if resolution is not None:
            incident.resolution = resolution

        incident.updated_at = datetime.now(UTC).isoformat()

        if timeline_action:
            incident.timeline.append({
                "timestamp": datetime.now(UTC).isoformat(),
                "action": timeline_action,
                "actor": "operator",
            })

        return incident

    def add_lesson(self, incident_id: str, lesson: str) -> bool:
        """Add a lesson learned to an incident.

        Args:
            incident_id: Incident ID.
            lesson: Lesson learned.

        Returns:
            True if added, False if incident not found.
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return False
        incident.lessons_learned.append(lesson)
        return True

    def get_incident(self, incident_id: str) -> Incident | None:
        """Get an incident by ID."""
        return self._incidents.get(incident_id)

    def get_open_incidents(self) -> list[Incident]:
        """Get all open incidents."""
        return [
            i for i in self._incidents.values()
            if i.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)
        ]

    def get_by_severity(self, severity: IncidentSeverity) -> list[Incident]:
        """Get incidents by severity."""
        return [i for i in self._incidents.values() if i.severity == severity]

    @property
    def incidents(self) -> list[Incident]:
        """All incidents."""
        return list(self._incidents.values())


class RunbookManager:
    """Manages operational runbooks."""

    def __init__(self) -> None:
        self._runbooks: dict[str, Runbook] = {}
        self._executions: list[RunbookExecution] = []
        self._execution_counter = 0
        self._register_default_runbooks()

    def _register_default_runbooks(self) -> None:
        """Register default DR and operational runbooks."""
        # Database failure runbook
        self.register_runbook(
            runbook_id="RB-DB-001",
            name="Database Connection Failure",
            description="Steps to recover from database connection loss",
            trigger="Database connection error or timeout",
            steps=[
                RunbookStep(
                    1, "Check database process status",
                    "Process running", "ps aux | grep postgres", 2,
                ),
                RunbookStep(
                    2, "Check network connectivity",
                    "Can reach database port", "telnet db_host 5432", 2,
                ),
                RunbookStep(
                    3, "Restart database if needed",
                    "Database starts successfully",
                    "systemctl restart postgresql", 5,
                ),
                RunbookStep(
                    4, "Verify application connectivity",
                    "App can connect", "curl /api/v1/health", 2,
                ),
                RunbookStep(
                    5, "Check for data corruption",
                    "No corruption detected", "pg_check", 10,
                ),
            ],
        )

        # Market data feed failure
        self.register_runbook(
            runbook_id="RB-MD-001",
            name="Market Data Feed Failure",
            description="Steps to recover from market data feed interruption",
            trigger="Market data feed stale or disconnected",
            steps=[
                RunbookStep(
                    1, "Check feed provider status",
                    "Provider operational", "Check vendor dashboard", 2,
                ),
                RunbookStep(
                    2, "Reconnect data feed",
                    "Feed connected", "Restart feed adapter", 5,
                ),
                RunbookStep(
                    3, "Verify data freshness",
                    "Data timestamp < 60s",
                    "Check latest bar timestamp", 2,
                ),
                RunbookStep(
                    4, "Backfill missing data",
                    "No gaps in data", "Run backfill job", 15,
                ),
            ],
        )

        # Model drift response
        self.register_runbook(
            runbook_id="RB-ML-001",
            name="Model Drift Response",
            description="Steps to respond to model drift detection",
            trigger="Drift PSI > 0.25",
            steps=[
                RunbookStep(
                    1, "Assess drift severity",
                    "Severity classified", "Review drift report", 5,
                ),
                RunbookStep(
                    2, "Check feature distributions",
                    "Root cause identified",
                    "Compare feature stats", 10,
                ),
                RunbookStep(
                    3, "Trigger model retrain",
                    "Retrain started", "Run training pipeline", 30,
                ),
                RunbookStep(
                    4, "Validate retrained model",
                    "Model passes eval-gate",
                    "Run eval-gate checks", 15,
                ),
                RunbookStep(
                    5, "Promote if passed",
                    "New model is champion",
                    "Run promotion workflow", 5,
                ),
            ],
        )

    def register_runbook(
        self,
        runbook_id: str,
        name: str,
        description: str,
        trigger: str,
        steps: list[RunbookStep] | None = None,
    ) -> Runbook:
        """Register a new runbook.

        Args:
            runbook_id: Unique runbook ID.
            name: Human-readable name.
            description: Description.
            trigger: When to execute.
            steps: List of steps.

        Returns:
            The registered Runbook.
        """
        runbook = Runbook(
            runbook_id=runbook_id,
            name=name,
            description=description,
            trigger=trigger,
            steps=steps or [],
        )
        self._runbooks[runbook_id] = runbook
        return runbook

    def execute_runbook(
        self,
        runbook_id: str,
        notes: str = "",
    ) -> RunbookExecution | None:
        """Record a runbook execution.

        Args:
            runbook_id: Runbook to execute.
            notes: Execution notes.

        Returns:
            RunbookExecution record, or None if runbook not found.
        """
        runbook = self._runbooks.get(runbook_id)
        if runbook is None:
            return None

        self._execution_counter += 1
        execution = RunbookExecution(
            execution_id=f"EXEC-{self._execution_counter:04d}",
            runbook_id=runbook_id,
            steps_total=len(runbook.steps),
            steps_completed=len(runbook.steps),
            success=True,
            notes=notes,
            completed_at=datetime.now(UTC).isoformat(),
        )
        self._executions.append(execution)

        runbook.last_executed = datetime.now(UTC).isoformat()
        runbook.execution_count += 1

        return execution

    def get_runbook(self, runbook_id: str) -> Runbook | None:
        """Get a runbook by ID."""
        return self._runbooks.get(runbook_id)

    @property
    def runbooks(self) -> list[Runbook]:
        """All registered runbooks."""
        return list(self._runbooks.values())

    @property
    def executions(self) -> list[RunbookExecution]:
        """All execution records."""
        return self._executions
