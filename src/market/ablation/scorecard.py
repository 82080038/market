"""Scorecard — verdict per engine: KEEP, MARGINAL, or REMOVE.

Decision logic based on:
1. Statistical significance (p-value from paired t-test)
2. Delta Sharpe (improvement over baseline)
3. Delta Alpha (excess return vs benchmark)
4. Win rate improvement

Verdict thresholds:
    KEEP:     p < 0.05 AND delta_sharpe > 0.1
    MARGINAL: p < 0.10 OR (p < 0.05 AND delta_sharpe > 0 but <= 0.1)
    REMOVE:   p >= 0.10 OR delta_sharpe <= 0

The scorecard also computes a composite score (0-100) for ranking engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from market.ablation.isolated_backtest import IsolationResult


class Verdict(str, Enum):
    KEEP = "KEEP"
    MARGINAL = "MARGINAL"
    REMOVE = "REMOVE"


@dataclass
class ScoreCard:
    """Scorecard for a single engine."""

    engine_name: str
    verdict: Verdict
    composite_score: float  # 0-100, higher is better
    delta_sharpe: float
    delta_alpha: float
    delta_win_rate: float
    p_value: float
    is_significant: bool
    n_observations: int
    isolated_sharpe: float
    baseline_sharpe: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "engine_name": self.engine_name,
            "verdict": self.verdict.value,
            "composite_score": round(self.composite_score, 2),
            "delta_sharpe": round(self.delta_sharpe, 4),
            "delta_alpha": round(self.delta_alpha, 4),
            "delta_win_rate": round(self.delta_win_rate, 2),
            "p_value": round(self.p_value, 6),
            "is_significant": self.is_significant,
            "n_observations": self.n_observations,
            "isolated_sharpe": round(self.isolated_sharpe, 4),
            "baseline_sharpe": round(self.baseline_sharpe, 4),
            "reasons": self.reasons,
        }


def score_engine(result: IsolationResult, n_engines_tested: int = 1) -> ScoreCard:
    """Compute scorecard for a single engine from its isolation result.

    Args:
        result: IsolationResult from IsolatedBacktester.run().
        n_engines_tested: Number of engines being tested in this ablation run.
            Used for Bonferroni correction: adjusted_alpha = 0.05 / n_engines_tested.
            This prevents false positives when testing many engines simultaneously.

    Returns:
        ScoreCard with verdict and composite score.
    """
    # Bonferroni correction for multiple testing
    # When testing N engines, the probability of at least one false positive
    # at α=0.05 is 1-(1-0.05)^N. For N=15, this is ~0.54.
    # Bonferroni: α_adjusted = α / N
    n = max(n_engines_tested, 1)
    alpha_05 = 0.05 / n
    alpha_10 = 0.10 / n
    if result.error:
        return ScoreCard(
            engine_name=result.engine_name,
            verdict=Verdict.REMOVE,
            composite_score=0.0,
            delta_sharpe=0.0,
            delta_alpha=0.0,
            delta_win_rate=0.0,
            p_value=1.0,
            is_significant=False,
            n_observations=0,
            isolated_sharpe=0.0,
            baseline_sharpe=0.0,
            reasons=[f"Error: {result.error}"],
        )

    delta_sharpe = result.delta_sharpe
    delta_alpha = result.delta_alpha
    delta_win_rate = result.delta_win_rate
    p_value = result.p_value
    significant = p_value < alpha_05

    isolated_sharpe = result.isolated_metrics.get("sharpe_ratio", 0.0)
    baseline_sharpe = result.baseline_metrics.get("sharpe_ratio", 0.0)

    reasons: list[str] = []

    # Determine verdict — check delta_sharpe first so harmful engines
    # are always REMOVE even if statistically significant.
    if delta_sharpe <= 0:
        verdict = Verdict.REMOVE
        if p_value < alpha_05:
            reasons.append(
                f"Significant (p={p_value:.4f}, Bonferroni α={alpha_05:.4f}) but negative Sharpe delta "
                f"({delta_sharpe:.3f}) — engine is harmful"
            )
        else:
            reasons.append(f"Negative or zero Sharpe delta ({delta_sharpe:.3f})")
    elif p_value < alpha_05 and delta_sharpe > 0.1:
        verdict = Verdict.KEEP
        reasons.append(f"Significant (p={p_value:.4f}, Bonferroni α={alpha_05:.4f}) with meaningful Sharpe improvement (+{delta_sharpe:.3f})")
    elif p_value < alpha_10:
        verdict = Verdict.MARGINAL
        reasons.append(f"Marginally significant (p={p_value:.4f}, Bonferroni α={alpha_10:.4f})")
        reasons.append(f"Small positive Sharpe delta (+{delta_sharpe:.3f})")
    elif p_value < alpha_05 and delta_sharpe > 0:
        verdict = Verdict.MARGINAL
        reasons.append(f"Significant but small Sharpe improvement (+{delta_sharpe:.3f} <= 0.1)")
    else:
        verdict = Verdict.REMOVE
        reasons.append(f"Not significant (p={p_value:.4f} >= Bonferroni α={alpha_10:.4f})")

    # Composite score (0-100)
    # Components:
    #   - Significance score: (1 - p_value) * 30  [max 30]
    #   - Sharpe improvement: min(max(delta_sharpe * 10, 0), 25)  [max 25]
    #   - Alpha contribution: min(max(delta_alpha * 20, 0), 20)  [max 20]
    #   - Win rate improvement: min(max(delta_win_rate * 2, 0), 15)  [max 15]
    #   - Isolated Sharpe absolute: min(max(isolated_sharpe * 10, 0), 10)  [max 10]

    sig_score = (1 - p_value) * 30
    sharpe_score = min(max(delta_sharpe * 10, 0), 25)
    alpha_score = min(max(delta_alpha * 20, 0), 20)
    winrate_score = min(max(delta_win_rate * 2, 0), 15)
    abs_sharpe_score = min(max(isolated_sharpe * 10, 0), 10)

    composite = sig_score + sharpe_score + alpha_score + winrate_score + abs_sharpe_score

    if delta_alpha > 0:
        reasons.append(f"Positive alpha contribution (+{delta_alpha:.4f})")
    elif delta_alpha < 0:
        reasons.append(f"Negative alpha contribution ({delta_alpha:.4f})")

    if delta_win_rate > 0:
        reasons.append(f"Win rate improved by +{delta_win_rate:.1f}%")
    elif delta_win_rate < 0:
        reasons.append(f"Win rate decreased by {delta_win_rate:.1f}%")

    return ScoreCard(
        engine_name=result.engine_name,
        verdict=verdict,
        composite_score=composite,
        delta_sharpe=delta_sharpe,
        delta_alpha=delta_alpha,
        delta_win_rate=delta_win_rate,
        p_value=p_value,
        is_significant=significant,
        n_observations=result.n_observations,
        isolated_sharpe=isolated_sharpe,
        baseline_sharpe=baseline_sharpe,
        reasons=reasons,
    )
