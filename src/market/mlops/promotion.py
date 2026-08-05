"""Champion/challenger promotion workflow + A/B testing + eval-gated promotion.

Implements:
- Champion/challenger evaluation and promotion
- A/B testing framework for strategy comparison
- Eval-gated promotion: model must pass eval criteria before promotion
- Statistical significance testing
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from market.mlops.registry import ModelAlias, ModelRegistry


@dataclass
class EvalCriteria:
    """Criteria for eval-gated promotion."""

    min_sharpe: float = 0.5
    max_drawdown: float = -0.20
    min_win_rate: float = 0.45
    min_samples: int = 100
    max_drift_psi: float = 0.25


@dataclass
class EvalResult:
    """Result of model evaluation."""

    model_id: str
    passed: bool
    metrics: dict[str, float]
    criteria: EvalCriteria
    failures: list[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ABTestResult:
    """Result of an A/B test between two strategies."""

    name: str
    strategy_a: str
    strategy_b: str
    metric_a: float
    metric_b: float
    winner: str
    confidence: float
    n_samples: int
    is_significant: bool
    p_value: float


class EvalGate:
    """Eval-gated promotion pipeline."""

    def __init__(
        self,
        registry: ModelRegistry,
        criteria: EvalCriteria | None = None,
    ) -> None:
        self.registry = registry
        self.criteria = criteria or EvalCriteria()

    def evaluate(
        self,
        model_id: str,
        metrics: dict[str, float],
        drift_psi: float = 0.0,
    ) -> EvalResult:
        """Evaluate a model against promotion criteria.

        Args:
            model_id: Model to evaluate.
            metrics: Evaluation metrics dict.
            drift_psi: Drift PSI score.

        Returns:
            EvalResult with pass/fail and specific failures.
        """
        failures: list[str] = []

        sharpe = metrics.get("sharpe", 0.0)
        if sharpe < self.criteria.min_sharpe:
            failures.append(
                f"sharpe {sharpe:.3f} < min {self.criteria.min_sharpe}",
            )

        drawdown = metrics.get("max_drawdown", 0.0)
        if drawdown < self.criteria.max_drawdown:
            failures.append(
                f"drawdown {drawdown:.3f} < max {self.criteria.max_drawdown}",
            )

        win_rate = metrics.get("win_rate", 0.0)
        if win_rate < self.criteria.min_win_rate:
            failures.append(
                f"win_rate {win_rate:.3f} < min {self.criteria.min_win_rate}",
            )

        n_samples = int(metrics.get("n_samples", 0))
        if n_samples < self.criteria.min_samples:
            failures.append(
                f"samples {n_samples} < min {self.criteria.min_samples}",
            )

        if drift_psi > self.criteria.max_drift_psi:
            failures.append(
                f"drift PSI {drift_psi:.3f} > max {self.criteria.max_drift_psi}",
            )

        passed = len(failures) == 0
        return EvalResult(
            model_id=model_id,
            passed=passed,
            metrics=metrics,
            criteria=self.criteria,
            failures=failures,
        )

    def promote_if_passed(
        self,
        model_id: str,
        metrics: dict[str, float],
        drift_psi: float = 0.0,
    ) -> EvalResult:
        """Evaluate and promote if criteria are met.

        Args:
            model_id: Model to evaluate.
            metrics: Evaluation metrics.
            drift_psi: Drift PSI score.

        Returns:
            EvalResult. If passed, model is promoted.
        """
        result = self.evaluate(model_id, metrics, drift_psi)

        if result.passed:
            model = self.registry.get(model_id)
            if model:
                if model.is_experiment or not model.aliases:
                    self.registry.promote(model_id)
                elif model.is_candidate:
                    self.registry.promote(model_id)

        return result


class ABTestFramework:
    """A/B testing framework for strategy comparison."""

    def __init__(self, significance_level: float = 0.05) -> None:
        self.significance_level = significance_level
        self._tests: list[ABTestResult] = []

    def run_test(
        self,
        name: str,
        strategy_a: str,
        strategy_b: str,
        returns_a: np.ndarray[Any, np.dtype[Any]],
        returns_b: np.ndarray[Any, np.dtype[Any]],
        metric_fn: Callable[..., Any] | None = None,
    ) -> ABTestResult:
        """Run an A/B test between two strategies.

        Args:
            name: Test name.
            strategy_a: Name of strategy A.
            strategy_b: Name of strategy B.
            returns_a: Returns array for strategy A.
            returns_b: Returns array for strategy B.
            metric_fn: Function to compute metric from returns. Defaults to mean.

        Returns:
            ABTestResult with winner and significance.
        """
        if metric_fn is None:
            metric_fn = np.mean

        metric_a = float(metric_fn(returns_a))
        metric_b = float(metric_fn(returns_b))

        # Paired t-test approximation
        min_len = min(len(returns_a), len(returns_b))
        if min_len < 2:
            p_value = 1.0
            confidence = 0.0
        else:
            diff = returns_a[:min_len] - returns_b[:min_len]
            mean_diff = np.mean(diff)
            std_diff = np.std(diff, ddof=1)
            t_stat = 0.0 if std_diff == 0 else mean_diff / (std_diff / np.sqrt(min_len))

            # Two-tailed p-value approximation
            from scipy import stats as sp_stats  # type: ignore[import-untyped]

            p_value = float(2 * (1 - sp_stats.t.cdf(abs(t_stat), df=min_len - 1)))
            confidence = float(1 - p_value)

        is_significant = p_value < self.significance_level
        winner = strategy_a if metric_a > metric_b else strategy_b

        result = ABTestResult(
            name=name,
            strategy_a=strategy_a,
            strategy_b=strategy_b,
            metric_a=round(metric_a, 6),
            metric_b=round(metric_b, 6),
            winner=winner,
            confidence=round(confidence, 4),
            n_samples=min_len,
            is_significant=is_significant,
            p_value=round(p_value, 6),
        )

        self._tests.append(result)
        return result

    @property
    def results(self) -> list[ABTestResult]:
        """All test results."""
        return self._tests

    def get_significant_results(self) -> list[ABTestResult]:
        """Get only statistically significant results."""
        return [t for t in self._tests if t.is_significant]
