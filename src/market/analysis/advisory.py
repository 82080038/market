"""Advisory System (pustaka/83).

Screening → Scoring → Recommendation pipeline.
Provides stock screening with preset filters and generates
advisory reports for the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from market.analysis.decision import DecisionEngine, DecisionResult


@dataclass
class ScreenResult:
    """Screening result for a single stock."""

    ticker: str
    passed: bool
    filters: dict[str, bool] = field(default_factory=dict)
    decision: DecisionResult | None = None


@dataclass
class AdvisoryReport:
    """Full advisory report for the user."""

    date: str
    market_regime: str
    screened: int
    passed: int
    results: list[ScreenResult] = field(default_factory=list)
    top_picks: list[DecisionResult] = field(default_factory=list)
    summary: str = ""


class AdvisoryEngine:
    """Advisory engine: screening → scoring → recommendation."""

    def __init__(self, decision_engine: DecisionEngine | None = None) -> None:
        self.decision_engine = decision_engine or DecisionEngine()

    def screen(
        self,
        universe: dict[str, dict[str, float | None]],
        min_technical: float = 0.0,
        min_fundamental: float = 0.0,
        min_sentiment: float = 0.0,
        min_composite: float = 50.0,
    ) -> list[ScreenResult]:
        """Screen stocks through filters and score passing ones.

        Args:
            universe: Dict mapping ticker to factor scores dict.
            min_technical: Minimum technical score to pass.
            min_fundamental: Minimum fundamental score to pass.
            min_sentiment: Minimum sentiment score to pass.
            min_composite: Minimum composite score to be a top pick.

        Returns:
            List of ScreenResult for all screened stocks.
        """
        results: list[ScreenResult] = []

        for ticker, scores in universe.items():
            tech = scores.get("technical")
            fund = scores.get("fundamental")
            sent = scores.get("sentiment")
            macro = scores.get("macro")
            glob = scores.get("global")
            rel = scores.get("relationship")

            filters: dict[str, bool] = {
                "technical": tech is not None and tech >= min_technical,
                "fundamental": fund is not None and fund >= min_fundamental,
                "sentiment": sent is not None and sent >= min_sentiment,
            }

            passed = all(filters.values())

            decision: DecisionResult | None = None
            if passed:
                decision = self.decision_engine.decide(
                    ticker=ticker,
                    technical=tech,
                    fundamental=fund,
                    macro=macro,
                    global_market=glob,
                    relationship=rel,
                    sentiment=sent,
                )
                if decision.composite_score < min_composite:
                    passed = False

            results.append(
                ScreenResult(
                    ticker=ticker,
                    passed=passed,
                    filters=filters,
                    decision=decision,
                ),
            )

        return results

    def generate_report(
        self,
        market_regime: str,
        universe: dict[str, dict[str, float | None]],
        min_technical: float = 0.0,
        min_fundamental: float = 0.0,
        min_sentiment: float = 0.0,
        min_composite: float = 50.0,
        top_n: int = 10,
    ) -> AdvisoryReport:
        """Generate a full advisory report.

        Args:
            market_regime: Current market regime label.
            universe: Dict mapping ticker to factor scores.
            min_*: Screening thresholds.
            top_n: Number of top picks to include.

        Returns:
            AdvisoryReport with screening results and top picks.
        """
        results = self.screen(
            universe,
            min_technical=min_technical,
            min_fundamental=min_fundamental,
            min_sentiment=min_sentiment,
            min_composite=min_composite,
        )

        passed_results = [r for r in results if r.passed and r.decision]
        top_picks = sorted(
            [r.decision for r in passed_results if r.decision],
            key=lambda d: d.composite_score,
            reverse=True,
        )[:top_n]

        from datetime import UTC, datetime

        summary = (
            f"Market regime: {market_regime}. "
            f"Screened {len(results)} stocks, {len(passed_results)} passed. "
            f"Top {len(top_picks)} picks: "
            + ", ".join(
                f"{d.ticker} ({d.recommendation}, {d.composite_score:.1f})"
                for d in top_picks[:5]
            )
        )

        return AdvisoryReport(
            date=datetime.now(UTC).strftime("%Y-%m-%d"),
            market_regime=market_regime,
            screened=len(results),
            passed=len(passed_results),
            results=results,
            top_picks=top_picks,
            summary=summary,
        )
