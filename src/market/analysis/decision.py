"""Decision Engine (pustaka/18 §3.6, pustaka/83).

Combines all factor scores into a final recommendation with
explainable AI (XAI) breakdown.

Default weights:
    technical:     20%
    fundamental:   25%
    macro:         10%
    global:        10%
    relationship:  10%
    sentiment:     25%
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.20,
    "fundamental": 0.25,
    "macro": 0.10,
    "global": 0.10,
    "relationship": 0.10,
    "sentiment": 0.25,
}

RECOMMENDATION_THRESHOLDS: dict[str, tuple[float, float]] = {
    "strong_buy": (80.0, 100.0),
    "buy": (65.0, 80.0),
    "hold": (45.0, 65.0),
    "reduce": (30.0, 45.0),
    "sell": (0.0, 30.0),
}


@dataclass
class DecisionResult:
    """Decision engine result with XAI breakdown."""

    ticker: str
    composite_score: float
    recommendation: str
    weights: dict[str, float] = field(default_factory=dict)
    factor_scores: dict[str, float] = field(default_factory=dict)
    contribution: dict[str, float] = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)


class DecisionEngine:
    """Decision engine combining factor scores into recommendation."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or DEFAULT_WEIGHTS

    def decide(
        self,
        ticker: str,
        technical: float | None = None,
        fundamental: float | None = None,
        macro: float | None = None,
        global_market: float | None = None,
        relationship: float | None = None,
        sentiment: float | None = None,
    ) -> DecisionResult:
        """Combine factor scores into a composite recommendation.

        Missing factors are excluded and weights renormalized.

        Args:
            ticker: Stock ticker.
            technical: Technical analysis score (0-100).
            fundamental: Fundamental analysis score (0-100).
            macro: Macro economic score (0-100).
            global_market: Global market score (0-100).
            relationship: Relationship score (0-100).
            sentiment: Sentiment score (0-100).

        Returns:
            DecisionResult with composite score, recommendation,
            contribution breakdown, and explanation.
        """
        factor_scores: dict[str, float] = {}
        if technical is not None:
            factor_scores["technical"] = technical
        if fundamental is not None:
            factor_scores["fundamental"] = fundamental
        if macro is not None:
            factor_scores["macro"] = macro
        if global_market is not None:
            factor_scores["global"] = global_market
        if relationship is not None:
            factor_scores["relationship"] = relationship
        if sentiment is not None:
            factor_scores["sentiment"] = sentiment

        if not factor_scores:
            return DecisionResult(
                ticker=ticker,
                composite_score=0.0,
                recommendation="no_data",
                weights=self.weights,
                factor_scores={},
                contribution={},
                explanation=["No factor scores available."],
            )

        # Renormalize weights for available factors
        total_weight = sum(
            self.weights.get(f, 0) for f in factor_scores
        )
        if total_weight == 0:
            total_weight = 1.0

        composite = 0.0
        contribution: dict[str, float] = {}
        for factor, score in factor_scores.items():
            w = self.weights.get(factor, 0) / total_weight
            contrib = score * w
            composite += contrib
            contribution[factor] = round(contrib, 2)

        composite = min(100.0, max(0.0, composite))

        # Determine recommendation
        recommendation = "hold"
        for label, (low, high) in RECOMMENDATION_THRESHOLDS.items():
            if low <= composite < high:
                recommendation = label
                break

        # Generate explanation
        explanation = self._generate_explanation(
            factor_scores, contribution, composite, recommendation,
        )

        return DecisionResult(
            ticker=ticker,
            composite_score=round(composite, 2),
            recommendation=recommendation,
            weights=self.weights,
            factor_scores=factor_scores,
            contribution=contribution,
            explanation=explanation,
        )

    def _generate_explanation(
        self,
        factor_scores: dict[str, float],
        contribution: dict[str, float],
        composite: float,
        recommendation: str,
    ) -> list[str]:
        """Generate human-readable explanation for the decision."""
        explanations: list[str] = []

        # Sort factors by contribution
        sorted_factors = sorted(
            contribution.items(), key=lambda x: x[1], reverse=True,
        )

        explanations.append(
            f"Composite score: {composite:.1f}/100 → {recommendation.upper()}",
        )

        for factor, contrib in sorted_factors[:3]:
            score = factor_scores[factor]
            if score >= 70:
                qual = "strong"
            elif score >= 50:
                qual = "moderate"
            else:
                qual = "weak"
            explanations.append(
                f"{factor}: {score:.1f} ({qual}) → +{contrib:.1f} to composite",
            )

        # Flag weakest factor
        if sorted_factors:
            weakest = sorted_factors[-1]
            if weakest[1] < 5.0:
                explanations.append(
                    f"Warning: {weakest[0]} is the weakest factor "
                    f"({factor_scores[weakest[0]]:.1f}).",
                )

        return explanations
