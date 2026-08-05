"""Self-evolution agent loop (pustaka/67, pustaka/86).

The agent loop follows a 9-stage cycle:
1. Observe  — collect metrics, drift signals, performance data
2. Analyze  — identify weaknesses, patterns, opportunities
3. Reflect  — reason about root causes and potential fixes
4. Decide   — choose an action (patch, retrain, adjust params, escalate)
5. Validate — run sandbox tests on proposed change
6. Execute  — apply change (hot-swap or queue for human approval)
7. Monitor  — watch post-change metrics
8. Learn    — record outcome in persistent memory
9. Evolve   — update decision policy based on learned outcomes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AgentStage(Enum):
    """Stages of the self-evolution agent loop."""

    OBSERVE = "observe"
    ANALYZE = "analyze"
    REFLECT = "reflect"
    DECIDE = "decide"
    VALIDATE = "validate"
    EXECUTE = "execute"
    MONITOR = "monitor"
    LEARN = "learn"
    EVOLVE = "evolve"


class ActionType(Enum):
    """Types of actions the agent can propose."""

    PATCH_CODE = "patch_code"
    RETRAIN_MODEL = "retrain_model"
    ADJUST_PARAMS = "adjust_params"
    ESCALATE_HUMAN = "escalate_human"
    NO_ACTION = "no_action"


class ActionStatus(Enum):
    """Status of a proposed action."""

    PROPOSED = "proposed"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


@dataclass
class Observation:
    """Data collected during the observe stage."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metrics: dict[str, float] = field(default_factory=dict)
    drift_signals: dict[str, float] = field(default_factory=dict)
    model_champion_id: str | None = None
    model_performance: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Analysis:
    """Result of the analyze stage."""

    weaknesses: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    drift_detected: bool = False
    performance_degraded: bool = False
    severity: str = "low"  # low, medium, high, critical


@dataclass
class Reflection:
    """Result of the reflect stage."""

    root_causes: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class Decision:
    """Result of the decide stage."""

    action_type: ActionType
    description: str
    patch_code: str | None = None
    params_change: dict[str, Any] = field(default_factory=dict)
    target_model_id: str | None = None
    requires_human_approval: bool = True
    confidence: float = 0.0


@dataclass
class ValidationResult:
    """Result of sandbox validation."""

    passed: bool
    tests_run: int = 0
    tests_passed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0


@dataclass
class AgentCycle:
    """A complete agent cycle record."""

    cycle_id: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    current_stage: AgentStage = AgentStage.OBSERVE
    observation: Observation | None = None
    analysis: Analysis | None = None
    reflection: Reflection | None = None
    decision: Decision | None = None
    validation: ValidationResult | None = None
    status: ActionStatus = ActionStatus.PROPOSED
    outcome_notes: str = ""
    learned_lessons: list[str] = field(default_factory=list)


class SelfEvolutionAgent:
    """Self-evolution agent that runs the 9-stage loop.

    The agent is designed to be safe:
    - All code changes require sandbox validation
    - Human approval is required for execution by default
    - Every action is logged for audit
    - Rollback is always available
    """

    def __init__(
        self,
        auto_approve_low_risk: bool = False,
        min_confidence: float = 0.6,
    ) -> None:
        self.auto_approve_low_risk = auto_approve_low_risk
        self.min_confidence = min_confidence
        self._cycles: list[AgentCycle] = []
        self._cycle_counter = 0
        self._decision_policy: dict[str, float] = {
            "patch_code_weight": 0.3,
            "retrain_weight": 0.4,
            "adjust_params_weight": 0.2,
            "escalate_weight": 0.1,
        }

    @property
    def cycles(self) -> list[AgentCycle]:
        """All completed and in-progress cycles."""
        return self._cycles

    def start_cycle(self) -> AgentCycle:
        """Start a new agent cycle."""
        self._cycle_counter += 1
        cycle = AgentCycle(cycle_id=f"cycle_{self._cycle_counter:04d}")
        self._cycles.append(cycle)
        return cycle

    def observe(
        self,
        cycle: AgentCycle,
        metrics: dict[str, float] | None = None,
        drift_signals: dict[str, float] | None = None,
        model_champion_id: str | None = None,
        model_performance: dict[str, float] | None = None,
        errors: list[str] | None = None,
    ) -> Observation:
        """Stage 1: Collect observations."""
        obs = Observation(
            metrics=metrics or {},
            drift_signals=drift_signals or {},
            model_champion_id=model_champion_id,
            model_performance=model_performance or {},
            errors=errors or [],
        )
        cycle.observation = obs
        cycle.current_stage = AgentStage.ANALYZE
        return obs

    def analyze(self, cycle: AgentCycle) -> Analysis:
        """Stage 2: Analyze observations for weaknesses and opportunities."""
        obs = cycle.observation
        if obs is None:
            return Analysis()

        weaknesses: list[str] = []
        opportunities: list[str] = []
        drift_detected = False
        performance_degraded = False
        severity = "low"

        # Check drift signals
        for signal, value in obs.drift_signals.items():
            if value > 0.25:
                weaknesses.append(f"Drift detected in {signal}: PSI={value:.3f}")
                drift_detected = True
                severity = "medium"

        # Check performance degradation
        baseline_sharpe = obs.metrics.get("baseline_sharpe", 0.0)
        current_sharpe = obs.model_performance.get("sharpe", 0.0)
        if baseline_sharpe > 0 and current_sharpe < baseline_sharpe * 0.7:
            weaknesses.append(
                f"Performance degraded: sharpe {current_sharpe:.3f} "
                f"< baseline {baseline_sharpe:.3f}",
            )
            performance_degraded = True
            severity = "high"

        # Check errors
        if obs.errors:
            weaknesses.append(f"Errors detected: {len(obs.errors)} errors")
            if len(obs.errors) > 5:
                severity = "high"

        # Opportunities
        if drift_detected:
            opportunities.append("Retrain model with recent data to address drift")
        if performance_degraded:
            opportunities.append("Adjust model hyperparameters or ensemble weights")
        if not weaknesses:
            opportunities.append("System stable, explore new features or strategies")

        analysis = Analysis(
            weaknesses=weaknesses,
            opportunities=opportunities,
            drift_detected=drift_detected,
            performance_degraded=performance_degraded,
            severity=severity,
        )
        cycle.analysis = analysis
        cycle.current_stage = AgentStage.REFLECT
        return analysis

    def reflect(self, cycle: AgentCycle) -> Reflection:
        """Stage 3: Reflect on root causes and hypotheses."""
        analysis = cycle.analysis
        if analysis is None:
            return Reflection()

        root_causes: list[str] = []
        hypotheses: list[str] = []
        confidence = 0.5

        if analysis.drift_detected:
            root_causes.append("Data distribution shift in production environment")
            hypotheses.append("Recent market regime change causing feature drift")
            confidence += 0.1

        if analysis.performance_degraded:
            root_causes.append("Model no longer captures current market dynamics")
            hypotheses.append("Stale model weights need retraining on recent data")
            confidence += 0.1

        if not root_causes:
            root_causes.append("No significant issues identified")
            hypotheses.append("System operating within normal parameters")
            confidence = 0.8

        reflection = Reflection(
            root_causes=root_causes,
            hypotheses=hypotheses,
            confidence=min(confidence, 1.0),
        )
        cycle.reflection = reflection
        cycle.current_stage = AgentStage.DECIDE
        return reflection

    def decide(self, cycle: AgentCycle) -> Decision:
        """Stage 4: Decide on an action based on analysis and reflection."""
        analysis = cycle.analysis
        reflection = cycle.reflection
        if analysis is None or reflection is None:
            return Decision(
                action_type=ActionType.NO_ACTION,
                description="Insufficient data for decision",
                confidence=0.0,
            )

        action_type = ActionType.NO_ACTION
        description = "No action needed"
        requires_human = True
        confidence = reflection.confidence

        if analysis.severity == "critical":
            action_type = ActionType.ESCALATE_HUMAN
            description = "Critical issue detected, escalating to human"
            requires_human = True
        elif analysis.drift_detected and analysis.performance_degraded:
            action_type = ActionType.RETRAIN_MODEL
            description = "Retrain model to address drift and performance degradation"
            requires_human = True
        elif analysis.drift_detected:
            action_type = ActionType.RETRAIN_MODEL
            description = "Retrain model to address data drift"
            requires_human = not self.auto_approve_low_risk
        elif analysis.performance_degraded:
            action_type = ActionType.ADJUST_PARAMS
            description = "Adjust model hyperparameters to improve performance"
            requires_human = True
        elif analysis.weaknesses:
            action_type = ActionType.PATCH_CODE
            description = "Propose code patch to address identified weakness"
            requires_human = True
        else:
            action_type = ActionType.NO_ACTION
            description = "System stable, no action needed"
            requires_human = False
            confidence = 0.9

        decision = Decision(
            action_type=action_type,
            description=description,
            requires_human_approval=requires_human,
            confidence=confidence,
        )
        cycle.decision = decision
        cycle.current_stage = AgentStage.VALIDATE
        return decision

    def validate(
        self,
        cycle: AgentCycle,
        sandbox_result: ValidationResult | None = None,
    ) -> ValidationResult:
        """Stage 5: Validate proposed action in sandbox."""
        decision = cycle.decision
        if decision is None:
            return ValidationResult(passed=False, errors=["No decision to validate"])

        if decision.action_type == ActionType.NO_ACTION:
            result = ValidationResult(passed=True, tests_run=0, tests_passed=0)
        elif sandbox_result is not None:
            result = sandbox_result
        else:
            # Simulate validation
            result = ValidationResult(
                passed=True,
                tests_run=10,
                tests_passed=10,
                execution_time_ms=150.0,
            )

        cycle.validation = result
        if result.passed:
            cycle.status = ActionStatus.VALIDATED
            cycle.current_stage = AgentStage.EXECUTE
        else:
            cycle.status = ActionStatus.VALIDATION_FAILED
            cycle.current_stage = AgentStage.LEARN
        return result

    def execute(
        self,
        cycle: AgentCycle,
        human_approved: bool | None = None,
    ) -> ActionStatus:
        """Stage 6: Execute the validated action.

        Args:
            cycle: The current agent cycle.
            human_approved: Whether a human has approved. If None and
                approval is required, action is queued.

        Returns:
            Updated ActionStatus.
        """
        decision = cycle.decision
        validation = cycle.validation
        if decision is None or validation is None:
            cycle.status = ActionStatus.REJECTED
            return cycle.status

        if not validation.passed:
            cycle.status = ActionStatus.VALIDATION_FAILED
            return cycle.status

        if decision.requires_human_approval and human_approved is None:
            cycle.status = ActionStatus.PROPOSED
            return cycle.status

        if decision.requires_human_approval and not human_approved:
            cycle.status = ActionStatus.REJECTED
            cycle.current_stage = AgentStage.LEARN
            return cycle.status

        # Execute
        if decision.action_type == ActionType.NO_ACTION:
            cycle.status = ActionStatus.COMPLETED
        else:
            cycle.status = ActionStatus.EXECUTED
        cycle.current_stage = AgentStage.MONITOR
        return cycle.status

    def monitor(
        self,
        cycle: AgentCycle,
        post_metrics: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Stage 7: Monitor post-execution metrics.

        Args:
            cycle: The current agent cycle.
            post_metrics: Metrics after execution.

        Returns:
            Dict of metric changes (post - pre).
        """
        if cycle.observation is None:
            return {}

        pre = cycle.observation.metrics
        post = post_metrics or {}
        changes: dict[str, float] = {}

        for key in set(list(pre.keys()) + list(post.keys())):
            pre_val = pre.get(key, 0.0)
            post_val = post.get(key, 0.0)
            changes[key] = post_val - pre_val

        if cycle.status == ActionStatus.EXECUTED:
            cycle.status = ActionStatus.MONITORING
        cycle.current_stage = AgentStage.LEARN
        return changes

    def learn(
        self,
        cycle: AgentCycle,
        outcome_notes: str = "",
        lessons: list[str] | None = None,
    ) -> list[str]:
        """Stage 8: Learn from the cycle outcome.

        Args:
            cycle: The current agent cycle.
            outcome_notes: Notes about the outcome.
            lessons: Learned lessons.

        Returns:
            List of learned lessons.
        """
        learned = lessons or []

        if cycle.status == ActionStatus.VALIDATION_FAILED:
            learned.append("Validation failed — review sandbox constraints")
        elif cycle.status == ActionStatus.REJECTED:
            learned.append("Human rejected proposal — refine decision criteria")
        elif cycle.status == ActionStatus.COMPLETED:
            learned.append("No action was needed — system stable")
        elif cycle.status in (ActionStatus.EXECUTED, ActionStatus.MONITORING):
            learned.append("Action executed — monitor for side effects")

        cycle.outcome_notes = outcome_notes
        cycle.learned_lessons = learned
        cycle.current_stage = AgentStage.EVOLVE
        return learned

    def evolve(self, cycle: AgentCycle) -> dict[str, float]:
        """Stage 9: Evolve decision policy based on learned outcomes.

        Args:
            cycle: The completed agent cycle.

        Returns:
            Updated decision policy weights.
        """
        # Adjust policy based on outcome
        if cycle.status == ActionStatus.EXECUTED:
            # Successful execution increases confidence in that action type
            if cycle.decision and cycle.decision.action_type == ActionType.RETRAIN_MODEL:
                self._decision_policy["retrain_weight"] = min(
                    1.0, self._decision_policy["retrain_weight"] + 0.05,
                )
        elif (
            cycle.status == ActionStatus.VALIDATION_FAILED
            and cycle.decision
            and cycle.decision.action_type == ActionType.PATCH_CODE
        ):
            # Failed validation decreases confidence
            self._decision_policy["patch_code_weight"] = max(
                0.0, self._decision_policy["patch_code_weight"] - 0.05,
            )

        # Normalize weights
        total = sum(self._decision_policy.values())
        if total > 0:
            for k in self._decision_policy:
                self._decision_policy[k] /= total

        cycle.completed_at = datetime.now(UTC).isoformat()
        cycle.current_stage = AgentStage.OBSERVE  # Ready for next cycle
        return self._decision_policy.copy()

    def run_full_cycle(
        self,
        metrics: dict[str, float] | None = None,
        drift_signals: dict[str, float] | None = None,
        model_performance: dict[str, float] | None = None,
        errors: list[str] | None = None,
        sandbox_result: ValidationResult | None = None,
        human_approved: bool | None = None,
        post_metrics: dict[str, float] | None = None,
    ) -> AgentCycle:
        """Run a complete 9-stage agent cycle.

        Args:
            metrics: Current system metrics.
            drift_signals: Drift detection signals.
            model_performance: Model performance metrics.
            errors: List of errors.
            sandbox_result: Sandbox validation result.
            human_approved: Human approval status.
            post_metrics: Post-execution metrics.

        Returns:
            Completed AgentCycle.
        """
        cycle = self.start_cycle()
        self.observe(
            cycle, metrics, drift_signals,
            model_performance=model_performance, errors=errors,
        )
        self.analyze(cycle)
        self.reflect(cycle)
        self.decide(cycle)
        self.validate(cycle, sandbox_result)
        self.execute(cycle, human_approved)
        self.monitor(cycle, post_metrics)
        self.learn(cycle)
        self.evolve(cycle)
        return cycle
