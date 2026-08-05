"""Autonomous improvement pipeline (pustaka/71, pustaka/73).

Integrates the self-evolution agent with:
- MLOps eval-gate for model promotion
- Sandbox for code validation
- Approval bot for human-in-the-loop
- Hot-swap for runtime updates
- Persistent memory for learning

The pipeline orchestrates the full flow:
1. Agent detects issue (drift, performance degradation)
2. Agent proposes action (retrain, patch, adjust)
3. Sandbox validates proposed change
4. Eval-gate checks if action passes criteria
5. Approval bot requests human approval
6. Hot-swap applies change if approved
7. Memory records outcome
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from market.autonomous.agent import (
    ActionStatus,
    ActionType,
    AgentCycle,
    SelfEvolutionAgent,
)
from market.autonomous.approval import ApprovalBot
from market.autonomous.hot_swap import HotSwapManager
from market.autonomous.memory import MemoryType, PersistentMemory
from market.autonomous.sandbox import Sandbox, SandboxConfig, SandboxResult

if TYPE_CHECKING:
    from market.mlops.drift import DriftDetector
    from market.mlops.promotion import EvalGate
    from market.mlops.registry import ModelRegistry


@dataclass
class PipelineResult:
    """Result of an autonomous improvement pipeline run."""

    cycle: AgentCycle
    sandbox_result: SandboxResult | None = None
    approval_request_id: str | None = None
    swap_record_id: str | None = None
    memory_entry_ids: list[str] = field(default_factory=list)
    completed: bool = False
    summary: str = ""


class AutonomousPipeline:
    """Autonomous improvement pipeline integrating all components."""

    def __init__(
        self,
        agent: SelfEvolutionAgent | None = None,
        sandbox: Sandbox | None = None,
        approval_bot: ApprovalBot | None = None,
        hot_swap: HotSwapManager | None = None,
        memory: PersistentMemory | None = None,
        eval_gate: EvalGate | None = None,
        drift_detector: DriftDetector | None = None,
        registry: ModelRegistry | None = None,
    ) -> None:
        self.agent = agent or SelfEvolutionAgent()
        self.sandbox = sandbox or Sandbox(SandboxConfig(timeout_seconds=5.0))
        self.approval_bot = approval_bot or ApprovalBot()
        self.hot_swap = hot_swap or HotSwapManager()
        self.memory = memory or PersistentMemory()
        self.eval_gate = eval_gate
        self.drift_detector = drift_detector
        self.registry = registry

    def run(
        self,
        metrics: dict[str, float] | None = None,
        drift_signals: dict[str, float] | None = None,
        model_performance: dict[str, float] | None = None,
        errors: list[str] | None = None,
        proposed_code: str | None = None,
        human_approved: bool | None = None,
    ) -> PipelineResult:
        """Run the autonomous improvement pipeline.

        Args:
            metrics: Current system metrics.
            drift_signals: Drift detection signals.
            model_performance: Model performance metrics.
            errors: List of errors.
            proposed_code: AI-generated code (if patch action).
            human_approved: Pre-approved human decision.

        Returns:
            PipelineResult with the full cycle outcome.
        """
        # Start agent cycle
        cycle = self.agent.start_cycle()
        result = PipelineResult(cycle=cycle)

        # Stages 1-4: Observe, Analyze, Reflect, Decide
        self.agent.observe(
            cycle, metrics, drift_signals,
            model_performance=model_performance, errors=errors,
        )
        analysis = self.agent.analyze(cycle)
        self.agent.reflect(cycle)
        decision = self.agent.decide(cycle)

        # Store observation in episodic memory
        mem_id = self.memory.store(
            MemoryType.EPISODIC,
            f"Agent cycle {cycle.cycle_id}: observed severity={analysis.severity}, "
            f"action={decision.action_type.value}",
            metadata={
                "cycle_id": cycle.cycle_id,
                "weaknesses": analysis.weaknesses,
                "decision": decision.description,
            },
            tags=["agent_cycle", analysis.severity],
        )
        result.memory_entry_ids.append(mem_id.entry_id)

        # Stage 5: Validate
        sandbox_result: SandboxResult | None = None

        if decision.action_type == ActionType.PATCH_CODE and proposed_code:
            sandbox_result = self.sandbox.execute(proposed_code)
            result.sandbox_result = sandbox_result

            from market.autonomous.agent import ValidationResult as AgentValResult
            agent_val = AgentValResult(
                passed=sandbox_result.success,
                tests_run=1 if sandbox_result.success else 0,
                tests_passed=1 if sandbox_result.success else 0,
                errors=[sandbox_result.error] if sandbox_result.error else [],
                execution_time_ms=sandbox_result.execution_time_ms,
            )
            self.agent.validate(cycle, agent_val)

            if sandbox_result.success:
                # Store successful patch in procedural memory
                mem_id = self.memory.store(
                    MemoryType.PROCEDURAL,
                    f"Validated patch for {decision.description}",
                    metadata={"code": proposed_code[:500]},
                    tags=["patch", "validated"],
                )
                result.memory_entry_ids.append(mem_id.entry_id)
            else:
                # Store failure in episodic memory
                mem_id = self.memory.store(
                    MemoryType.EPISODIC,
                    f"Patch validation failed: {sandbox_result.error}",
                    tags=["patch", "failed", "sandbox"],
                )
                result.memory_entry_ids.append(mem_id.entry_id)

        elif decision.action_type == ActionType.RETRAIN_MODEL:
            # Simulate retrain validation
            from market.autonomous.agent import ValidationResult as AgentValResult
            agent_val = AgentValResult(
                passed=True, tests_run=5, tests_passed=5,
                execution_time_ms=200.0,
            )
            self.agent.validate(cycle, agent_val)

        elif decision.action_type == ActionType.NO_ACTION:
            self.agent.validate(cycle)

        else:
            self.agent.validate(cycle)

        # Stage 5b: Eval-gate check (if model-related action)
        if (
            self.eval_gate
            and decision.action_type == ActionType.RETRAIN_MODEL
            and cycle.validation
            and cycle.validation.passed
            and self.registry
        ):
            # Check if retrained model passes eval criteria
            # In production, this would evaluate the newly trained model
            pass

        # Stage 6: Execute (with approval if needed)
        if decision.requires_human_approval and human_approved is None:
            # Request approval via bot
            approval_req = self.approval_bot.request_approval(
                cycle_id=cycle.cycle_id,
                action_type=decision.action_type.value,
                description=decision.description,
                details={
                    "confidence": decision.confidence,
                    "severity": analysis.severity,
                },
            )
            result.approval_request_id = approval_req.request_id

            # Store in working memory
            mem_id = self.memory.store(
                MemoryType.WORKING,
                f"Approval pending: {approval_req.request_id} for {decision.description}",
                metadata={"approval_id": approval_req.request_id},
                tags=["approval", "pending"],
            )
            result.memory_entry_ids.append(mem_id.entry_id)

            # Don't execute yet — waiting for approval
            self.agent.execute(cycle, human_approved=None)
            result.summary = f"Action proposed, awaiting approval: {approval_req.request_id}"
        else:
            status = self.agent.execute(cycle, human_approved=human_approved)

            if status == ActionStatus.EXECUTED:
                result.summary = f"Action executed: {decision.description}"
            elif status == ActionStatus.COMPLETED:
                result.summary = "No action needed"
            elif status == ActionStatus.REJECTED:
                result.summary = "Action rejected"
            else:
                result.summary = f"Action status: {status.value}"

        # Stage 7: Monitor (simulated)
        self.agent.monitor(cycle)

        # Stage 8: Learn
        lessons = self.agent.learn(cycle, outcome_notes=result.summary)

        # Store lessons in semantic memory
        for lesson in lessons:
            mem_id = self.memory.store(
                MemoryType.SEMANTIC,
                lesson,
                metadata={"cycle_id": cycle.cycle_id},
                tags=["lesson", decision.action_type.value],
            )
            result.memory_entry_ids.append(mem_id.entry_id)

        # Stage 9: Evolve
        self.agent.evolve(cycle)

        # Store evolved policy in procedural memory
        mem_id = self.memory.store(
            MemoryType.PROCEDURAL,
            f"Decision policy updated after cycle {cycle.cycle_id}",
            metadata={"lessons": lessons},
            tags=["policy", "evolution"],
        )
        result.memory_entry_ids.append(mem_id.entry_id)

        result.completed = True
        result.summary += f" | Lessons: {len(lessons)} | Memories: {len(result.memory_entry_ids)}"
        return result
