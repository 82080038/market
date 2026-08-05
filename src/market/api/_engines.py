"""Lazy singleton engine instances shared across API routes.

All engines are created once on first access. This replaces the
pattern of instantiating engines inside create_app() closures.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any


class _EngineRegistry:
    """Lazy holder for all engine instances."""

    @cached_property
    def decision_engine(self) -> Any:
        from market.analysis.decision import DecisionEngine
        return DecisionEngine()

    @cached_property
    def advisory_engine(self) -> Any:
        from market.analysis.advisory import AdvisoryEngine
        return AdvisoryEngine(self.decision_engine)

    @cached_property
    def readiness_gate(self) -> Any:
        from market.analysis.profiling import InstrumentReadinessGate
        return InstrumentReadinessGate()

    @cached_property
    def automation_orchestrator(self) -> Any:
        from market.execution.automation import AutomationOrchestrator
        return AutomationOrchestrator()

    @cached_property
    def leverage_advisor(self) -> Any:
        from market.risk.leverage import LeverageAdvisor
        return LeverageAdvisor()

    @cached_property
    def autonomous_backtest_runner(self) -> Any:
        from market.backtest.autonomous import AutonomousBacktestRunner
        return AutonomousBacktestRunner()

    @cached_property
    def pattern_detector(self) -> Any:
        from market.analysis.pattern_detector import PatternDetector
        return PatternDetector()

    @cached_property
    def prediction_engine(self) -> Any:
        from market.analysis.prediction import PredictionEngine
        return PredictionEngine(pattern_detector=self.pattern_detector)

    @cached_property
    def delisting_memory(self) -> Any:
        return self.pattern_detector.delisting_memory


engines = _EngineRegistry()
