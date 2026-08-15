"""Tests for autonomous AI layer: agent, sandbox, approval, hot-swap, memory, pipeline."""

from __future__ import annotations

import signal
import tempfile
from pathlib import Path

import pytest

from market.autonomous.agent import (
    ActionStatus,
    ActionType,
    AgentStage,
    SelfEvolutionAgent,
    ValidationResult,
)
from market.autonomous.approval import ApprovalBot, ApprovalStatus
from market.autonomous.hot_swap import HotSwapManager, SwapStatus
from market.autonomous.memory import MemoryType, PersistentMemory
from market.autonomous.pipeline import AutonomousPipeline
from market.autonomous.sandbox import ASTScanner, Sandbox, SandboxConfig

# --- Agent tests ---


def test_agent_start_cycle():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    assert cycle.cycle_id == "cycle_0001"
    assert cycle.current_stage == AgentStage.OBSERVE
    assert len(agent.cycles) == 1


def test_agent_observe():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    obs = agent.observe(
        cycle,
        metrics={"sharpe": 1.5},
        drift_signals={"feature_psi": 0.3},
        model_performance={"sharpe": 0.8},
        errors=["test error"],
    )
    assert obs.metrics["sharpe"] == 1.5
    assert obs.drift_signals["feature_psi"] == 0.3
    assert cycle.current_stage == AgentStage.ANALYZE


def test_agent_analyze_drift():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(
        cycle,
        metrics={"baseline_sharpe": 1.5},
        drift_signals={"feature_psi": 0.35},
    )
    analysis = agent.analyze(cycle)
    assert analysis.drift_detected
    assert len(analysis.weaknesses) > 0
    assert cycle.current_stage == AgentStage.REFLECT


def test_agent_analyze_performance_degraded():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(
        cycle,
        metrics={"baseline_sharpe": 2.0},
        model_performance={"sharpe": 0.5},
    )
    analysis = agent.analyze(cycle)
    assert analysis.performance_degraded
    assert analysis.severity == "high"


def test_agent_analyze_stable():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(
        cycle,
        metrics={"baseline_sharpe": 1.5},
        model_performance={"sharpe": 1.5},
    )
    analysis = agent.analyze(cycle)
    assert not analysis.drift_detected
    assert not analysis.performance_degraded
    assert len(analysis.opportunities) > 0


def test_agent_reflect():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle, drift_signals={"psi": 0.3})
    agent.analyze(cycle)
    reflection = agent.reflect(cycle)
    assert len(reflection.root_causes) > 0
    assert reflection.confidence > 0
    assert cycle.current_stage == AgentStage.DECIDE


def test_agent_decide_retrain():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(
        cycle,
        metrics={"baseline_sharpe": 2.0},
        drift_signals={"psi": 0.3},
        model_performance={"sharpe": 0.5},
    )
    agent.analyze(cycle)
    agent.reflect(cycle)
    decision = agent.decide(cycle)
    assert decision.action_type == ActionType.RETRAIN_MODEL
    assert cycle.current_stage == AgentStage.VALIDATE


def test_agent_decide_no_action():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(
        cycle,
        metrics={"baseline_sharpe": 1.5},
        model_performance={"sharpe": 1.5},
    )
    agent.analyze(cycle)
    agent.reflect(cycle)
    decision = agent.decide(cycle)
    assert decision.action_type == ActionType.NO_ACTION
    assert not decision.requires_human_approval


def test_agent_validate_passed():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle)
    agent.analyze(cycle)
    agent.reflect(cycle)
    agent.decide(cycle)
    result = agent.validate(cycle, ValidationResult(passed=True, tests_run=10, tests_passed=10))
    assert result.passed
    assert cycle.status == ActionStatus.VALIDATED


def test_agent_validate_failed():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle, drift_signals={"psi": 0.3})
    agent.analyze(cycle)
    agent.reflect(cycle)
    agent.decide(cycle)
    result = agent.validate(
        cycle,
        ValidationResult(passed=False, tests_run=10, tests_passed=5, errors=["test failure"]),
    )
    assert not result.passed
    assert cycle.status == ActionStatus.VALIDATION_FAILED


def test_agent_execute_approved():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle)
    agent.analyze(cycle)
    agent.reflect(cycle)
    agent.decide(cycle)
    agent.validate(cycle)
    status = agent.execute(cycle, human_approved=True)
    assert status == ActionStatus.COMPLETED  # NO_ACTION


def test_agent_execute_rejected():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle, drift_signals={"psi": 0.3})
    agent.analyze(cycle)
    agent.reflect(cycle)
    agent.decide(cycle)
    agent.validate(cycle)
    status = agent.execute(cycle, human_approved=False)
    assert status == ActionStatus.REJECTED


def test_agent_execute_pending():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle, drift_signals={"psi": 0.3})
    agent.analyze(cycle)
    agent.reflect(cycle)
    agent.decide(cycle)
    agent.validate(cycle)
    status = agent.execute(cycle, human_approved=None)
    assert status == ActionStatus.PROPOSED


def test_agent_learn():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle)
    agent.analyze(cycle)
    agent.reflect(cycle)
    agent.decide(cycle)
    agent.validate(cycle)
    agent.execute(cycle, human_approved=True)
    agent.monitor(cycle)
    lessons = agent.learn(cycle, outcome_notes="test")
    assert len(lessons) > 0


def test_agent_evolve():
    agent = SelfEvolutionAgent()
    cycle = agent.start_cycle()
    agent.observe(cycle)
    agent.analyze(cycle)
    agent.reflect(cycle)
    agent.decide(cycle)
    agent.validate(cycle)
    agent.execute(cycle, human_approved=True)
    agent.monitor(cycle)
    agent.learn(cycle)
    policy = agent.evolve(cycle)
    assert "retrain_weight" in policy
    assert cycle.completed_at is not None


def test_agent_run_full_cycle():
    agent = SelfEvolutionAgent()
    cycle = agent.run_full_cycle(
        metrics={"baseline_sharpe": 1.5},
        drift_signals={"psi": 0.3},
        model_performance={"sharpe": 0.5},
        human_approved=True,
    )
    assert cycle.completed_at is not None
    assert cycle.current_stage == AgentStage.OBSERVE  # Ready for next


# --- Sandbox tests ---


def test_ast_scanner_clean_code():
    code = "x = 1 + 2\nprint(x)"
    ast_violations, import_violations = ASTScanner.scan(code)
    assert len(ast_violations) == 0
    assert len(import_violations) == 0


def test_ast_scanner_forbidden_import():
    code = "import os\nos.system('rm -rf /')"
    _ast_violations, import_violations = ASTScanner.scan(
        code, forbidden_imports={"os"},
    )
    assert any("os" in v for v in import_violations)


def test_ast_scanner_exec_call():
    code = "exec('print(1)')"
    ast_violations, _ = ASTScanner.scan(code)
    assert any("exec" in v for v in ast_violations)


def test_ast_scanner_eval_call():
    code = "eval('1+1')"
    ast_violations, _ = ASTScanner.scan(code)
    assert any("eval" in v for v in ast_violations)


def test_sandbox_validate_clean():
    sandbox = Sandbox()
    is_valid, ast_v, imp_v = sandbox.validate("x = 1 + 2")
    assert is_valid
    assert len(ast_v) == 0
    assert len(imp_v) == 0


def test_sandbox_validate_forbidden():
    sandbox = Sandbox()
    is_valid, _ast_v, imp_v = sandbox.validate("import os")
    assert not is_valid
    assert len(imp_v) > 0


def test_sandbox_execute_success():
    sandbox = Sandbox(SandboxConfig(timeout_seconds=2.0))
    result = sandbox.execute("x = 1 + 2\nprint(x)")
    assert result.success
    assert "3" in result.output


def test_sandbox_execute_timeout():
    """Timeout test — SIGALRM-based on Unix, skipped on Windows.

    Windows doesn't support signal.SIGALRM, and thread-based timeout cannot
    interrupt a tight loop (while True: pass) in the same process. The sandbox
    falls back to thread-based timeout on Windows, which works for I/O-bound
    code but not CPU-bound infinite loops. This test is Unix-only.
    """
    import sys

    if not hasattr(signal, "SIGALRM"):
        pytest.skip("signal.SIGALRM not available on Windows — timeout test is Unix-only")

    sandbox = Sandbox(SandboxConfig(timeout_seconds=0.1))
    result = sandbox.execute("while True:\n    pass")
    assert not result.success
    assert result.timed_out


def test_sandbox_execute_forbidden_import():
    sandbox = Sandbox()
    result = sandbox.execute("import os\nos.system('echo hi')")
    assert not result.success
    assert len(result.import_violations) > 0


def test_sandbox_execute_allowed_import():
    config = SandboxConfig(
        allowed_imports={"numpy", "math", "pandas"},
        forbidden_imports=set(),
    )
    sandbox = Sandbox(config)
    code = "import numpy as np\nprint(np.array([1, 2, 3]))"
    result = sandbox.execute(code)
    assert result.success


def test_sandbox_syntax_error():
    sandbox = Sandbox()
    result = sandbox.execute("this is not valid python")
    assert not result.success


# --- Approval bot tests ---


def test_approval_request():
    bot = ApprovalBot()
    req = bot.request_approval("cycle_001", "retrain_model", "Retrain model due to drift")
    assert req.status == ApprovalStatus.PENDING
    assert req.request_id == "approval_0001"


def test_approval_approve():
    bot = ApprovalBot()
    req = bot.request_approval("cycle_001", "patch_code", "Fix bug")
    approved = bot.approve(req.request_id, decided_by="petrick")
    assert approved is not None
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.decided_by == "petrick"


def test_approval_reject():
    bot = ApprovalBot()
    req = bot.request_approval("cycle_001", "patch_code", "Fix bug")
    rejected = bot.reject(req.request_id, decided_by="petrick", notes="Too risky")
    assert rejected is not None
    assert rejected.status == ApprovalStatus.REJECTED


def test_approval_withdraw():
    bot = ApprovalBot()
    req = bot.request_approval("cycle_001", "patch_code", "Fix bug")
    withdrawn = bot.withdraw(req.request_id)
    assert withdrawn is not None
    assert withdrawn.status == ApprovalStatus.WITHDRAWN


def test_approval_expire():
    bot = ApprovalBot(auto_expire_hours=0)
    bot.request_approval("cycle_001", "patch_code", "Fix bug", expire_hours=0)
    expired = bot.expire_stale()
    assert len(expired) == 1
    assert expired[0].status == ApprovalStatus.EXPIRED


def test_approval_get_pending():
    bot = ApprovalBot()
    bot.request_approval("c1", "action1", "desc1")
    bot.request_approval("c2", "action2", "desc2")
    pending = bot.get_pending()
    assert len(pending) == 2


def test_approval_log():
    bot = ApprovalBot()
    req = bot.request_approval("c1", "action1", "desc1")
    bot.approve(req.request_id)
    assert len(bot.log) == 2  # created + approved


def test_approval_notification_hook():
    notifications: list[str] = []
    bot = ApprovalBot()
    bot.set_notification_hook(lambda r: notifications.append(r.request_id))
    bot.request_approval("c1", "action1", "desc1")
    assert len(notifications) == 1


# --- Hot-swap tests ---


def test_hot_swap_register_version():
    mgr = HotSwapManager()
    mv = mgr.register_version("market.test", "1.0.0", "x = 1")
    assert mv.module_name == "market.test"
    assert mv.is_active  # First version is active


def test_hot_swap_register_multiple():
    mgr = HotSwapManager()
    mgr.register_version("market.test", "1.0.0", "x = 1")
    mgr.register_version("market.test", "1.1.0", "x = 2")
    versions = mgr.get_versions("market.test")
    assert len(versions) == 2
    assert versions[0].is_active
    assert not versions[1].is_active


def test_hot_swap_swap():
    mgr = HotSwapManager()
    mgr.register_version("market.test", "1.0.0", "x = 1")
    mgr.register_version("market.test", "1.1.0", "x = 2")
    record = mgr.swap("market.test", "1.1.0", run_health_check=False)
    assert record.status == SwapStatus.HEALTH_CHECK_PASSED
    active = mgr.get_active_version("market.test")
    assert active.version == "1.1.0"


def test_hot_swap_health_check_fail_rollback():
    mgr = HotSwapManager()
    mgr.register_version("market.test", "1.0.0", "x = 1")
    mgr.register_version("market.test", "1.1.0", "x = 2")
    mgr.set_health_check(lambda: {"healthy": False, "details": "test failed"})
    record = mgr.swap("market.test", "1.1.0", run_health_check=True)
    assert record.status == SwapStatus.ROLLED_BACK
    active = mgr.get_active_version("market.test")
    assert active.version == "1.0.0"


def test_hot_swap_health_check_pass():
    mgr = HotSwapManager()
    mgr.register_version("market.test", "1.0.0", "x = 1")
    mgr.register_version("market.test", "1.1.0", "x = 2")
    mgr.set_health_check(lambda: {"healthy": True, "details": "all good"})
    record = mgr.swap("market.test", "1.1.0", run_health_check=True)
    assert record.status == SwapStatus.HEALTH_CHECK_PASSED


def test_hot_swap_version_not_found():
    mgr = HotSwapManager()
    mgr.register_version("market.test", "1.0.0", "x = 1")
    record = mgr.swap("market.test", "9.9.9")
    assert record.status == SwapStatus.FAILED


def test_hot_swap_rollback_last():
    mgr = HotSwapManager()
    mgr.register_version("market.test", "1.0.0", "x = 1")
    mgr.register_version("market.test", "1.1.0", "x = 2")
    mgr.swap("market.test", "1.1.0", run_health_check=False)
    assert mgr.get_active_version("market.test").version == "1.1.0"
    rollback = mgr.rollback_last("market.test")
    assert rollback is not None
    assert mgr.get_active_version("market.test").version == "1.0.0"


def test_hot_swap_history():
    mgr = HotSwapManager()
    mgr.register_version("market.test", "1.0.0", "x = 1")
    mgr.register_version("market.test", "1.1.0", "x = 2")
    mgr.swap("market.test", "1.1.0", run_health_check=False)
    assert len(mgr.swap_history) == 1


# --- Memory tests ---


def test_memory_store_retrieve():
    mem = PersistentMemory()
    entry = mem.store(MemoryType.EPISODIC, "Test memory content")
    retrieved = mem.retrieve(entry.entry_id)
    assert retrieved is not None
    assert retrieved.content == "Test memory content"
    assert retrieved.access_count == 1


def test_memory_search_by_type():
    mem = PersistentMemory()
    mem.store(MemoryType.EPISODIC, "Episode 1")
    mem.store(MemoryType.SEMANTIC, "Fact 1")
    mem.store(MemoryType.EPISODIC, "Episode 2")
    episodic = mem.search(memory_type=MemoryType.EPISODIC)
    assert len(episodic) == 2


def test_memory_search_by_tag():
    mem = PersistentMemory()
    mem.store(MemoryType.EPISODIC, "Content 1", tags=["drift", "model"])
    mem.store(MemoryType.EPISODIC, "Content 2", tags=["patch"])
    mem.store(MemoryType.EPISODIC, "Content 3", tags=["drift"])
    results = mem.search(tags=["drift"])
    assert len(results) == 2


def test_memory_search_by_query():
    mem = PersistentMemory()
    mem.store(MemoryType.SEMANTIC, "Model drift detected in production")
    mem.store(MemoryType.SEMANTIC, "System stable")
    results = mem.search(query="drift")
    assert len(results) == 1
    assert "drift" in results[0].content


def test_memory_update():
    mem = PersistentMemory()
    entry = mem.store(MemoryType.WORKING, "Initial content")
    updated = mem.update(entry.entry_id, content="Updated content", relevance_score=0.5)
    assert updated is not None
    assert updated.content == "Updated content"
    assert updated.relevance_score == 0.5


def test_memory_forget():
    mem = PersistentMemory()
    entry = mem.store(MemoryType.EPISODIC, "To be forgotten")
    result = mem.forget(entry.entry_id)
    assert result
    assert mem.retrieve(entry.entry_id) is None
    assert mem.count == 0


def test_memory_consolidate():
    mem = PersistentMemory()
    mem.store(MemoryType.EPISODIC, "Important", relevance_score=0.9)
    mem.store(MemoryType.EPISODIC, "Trivial", relevance_score=0.05)
    removed = mem.consolidate(threshold=0.1)
    assert removed == 1
    assert mem.count == 1


def test_memory_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "memory.json"
        mem1 = PersistentMemory(storage_path=path)
        mem1.store(MemoryType.EPISODIC, "Persistent content", tags=["test"])

        mem2 = PersistentMemory(storage_path=path)
        assert mem2.count == 1
        results = mem2.search(tags=["test"])
        assert len(results) == 1
        assert results[0].content == "Persistent content"


def test_memory_stats():
    mem = PersistentMemory()
    mem.store(MemoryType.EPISODIC, "E1")
    mem.store(MemoryType.SEMANTIC, "S1")
    mem.store(MemoryType.PROCEDURAL, "P1")
    stats = mem.stats()
    assert stats["episodic"] == 1
    assert stats["semantic"] == 1
    assert stats["procedural"] == 1


# --- Pipeline tests ---


def test_pipeline_no_action():
    pipeline = AutonomousPipeline()
    result = pipeline.run(
        metrics={"baseline_sharpe": 1.5},
        model_performance={"sharpe": 1.5},
    )
    assert result.completed
    assert result.cycle.decision is not None
    assert result.cycle.decision.action_type == ActionType.NO_ACTION


def test_pipeline_with_drift():
    pipeline = AutonomousPipeline()
    result = pipeline.run(
        metrics={"baseline_sharpe": 1.5},
        drift_signals={"feature_psi": 0.35},
        model_performance={"sharpe": 0.5},
        human_approved=True,
    )
    assert result.completed
    assert result.cycle.decision is not None
    assert result.cycle.decision.action_type == ActionType.RETRAIN_MODEL


def test_pipeline_awaiting_approval():
    pipeline = AutonomousPipeline()
    result = pipeline.run(
        metrics={"baseline_sharpe": 1.5},
        drift_signals={"feature_psi": 0.35},
        model_performance={"sharpe": 0.5},
        human_approved=None,
    )
    assert result.approval_request_id is not None
    assert "awaiting approval" in result.summary


def test_pipeline_patch_code():
    pipeline = AutonomousPipeline()
    code = "import numpy as np\nx = np.array([1, 2, 3])\nprint(x)"
    result = pipeline.run(
        metrics={"baseline_sharpe": 1.5},
        model_performance={"sharpe": 1.5},
        errors=["test error"],
        proposed_code=code,
        human_approved=True,
    )
    assert result.completed
    assert result.sandbox_result is not None
    assert result.sandbox_result.success


def test_pipeline_creates_memories():
    pipeline = AutonomousPipeline()
    result = pipeline.run(
        metrics={"baseline_sharpe": 1.5},
        model_performance={"sharpe": 1.5},
    )
    assert len(result.memory_entry_ids) > 0
    assert pipeline.memory.count > 0
