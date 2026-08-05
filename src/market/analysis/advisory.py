"""Advisory System (pustaka/83).

Readiness Gate → Screening → Scoring → Recommendation pipeline.
Provides stock screening with preset filters and generates
advisory reports for the user.

Before screening, the InstrumentReadinessGate evaluates whether the
application has sufficient knowledge about each instrument (data
duration, pattern history, model performance, factor relevance).
Only instruments that pass the readiness gate proceed to screening.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from market.analysis.decision import DecisionEngine, DecisionResult
from market.analysis.profiling import (
    InstrumentReadinessGate,
    InstrumentReadinessReport,
    ReadinessLevel,
)


@dataclass
class ScreenResult:
    """Screening result for a single stock."""

    ticker: str
    passed: bool
    filters: dict[str, bool] = field(default_factory=dict)
    decision: DecisionResult | None = None
    readiness: InstrumentReadinessReport | None = None


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
    readiness_reports: dict[str, InstrumentReadinessReport] = field(default_factory=dict)
    skipped_not_ready: list[str] = field(default_factory=list)


class AdvisoryEngine:
    """Advisory engine: readiness gate → screening → scoring → recommendation."""

    def __init__(
        self,
        decision_engine: DecisionEngine | None = None,
        readiness_gate: InstrumentReadinessGate | None = None,
    ) -> None:
        self.decision_engine = decision_engine or DecisionEngine()
        self.readiness_gate = readiness_gate or InstrumentReadinessGate()

    def screen(
        self,
        universe: dict[str, dict[str, float | None]],
        min_technical: float = 0.0,
        min_fundamental: float = 0.0,
        min_sentiment: float = 0.0,
        min_composite: float = 50.0,
        readiness_reports: dict[str, InstrumentReadinessReport] | None = None,
    ) -> list[ScreenResult]:
        """Screen stocks through filters and score passing ones.

        If readiness_reports are provided, instruments that are NOT_READY
        or INSUFFICIENT_DATA are automatically filtered out before
        applying technical/fundamental/sentiment filters.

        Args:
            universe: Dict mapping ticker to factor scores dict.
            min_technical: Minimum technical score to pass.
            min_fundamental: Minimum fundamental score to pass.
            min_sentiment: Minimum sentiment score to pass.
            min_composite: Minimum composite score to be a top pick.
            readiness_reports: Optional readiness gate reports per ticker.
                If provided, only READY and CONDITIONAL instruments proceed.

        Returns:
            List of ScreenResult for all screened stocks.
        """
        results: list[ScreenResult] = []
        ready_levels = {ReadinessLevel.READY, ReadinessLevel.CONDITIONAL}

        for ticker, scores in universe.items():
            readiness = readiness_reports.get(ticker) if readiness_reports else None

            # Pre-screening readiness gate
            if readiness is not None and readiness.readiness_level not in ready_levels:
                results.append(
                    ScreenResult(
                        ticker=ticker,
                        passed=False,
                        filters={"readiness": False},
                        decision=None,
                        readiness=readiness,
                    ),
                )
                continue

            tech = scores.get("technical")
            fund = scores.get("fundamental")
            sent = scores.get("sentiment")
            macro = scores.get("macro")
            glob = scores.get("global")
            rel = scores.get("relationship")

            # If readiness report has factor relevance weights, use them
            if readiness and readiness.factor_relevance:
                self.decision_engine.weights = readiness.factor_relevance.weights

            filters: dict[str, bool] = {
                "readiness": True,
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
                    readiness=readiness,
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
        ohlcv_data: dict[str, pd.DataFrame] | None = None,
        ihsg_df: pd.DataFrame | None = None,
        sectors: dict[str, str] | None = None,
        market_caps: dict[str, float] | None = None,
        asset_classes: dict[str, str] | None = None,
    ) -> AdvisoryReport:
        """Generate a full advisory report.

        If ohlcv_data is provided, the readiness gate is run before screening.
        Instruments that fail the readiness gate are skipped and listed in
        skipped_not_ready.

        Args:
            market_regime: Current market regime label.
            universe: Dict mapping ticker to factor scores.
            min_*: Screening thresholds.
            top_n: Number of top picks to include.
            ohlcv_data: Optional dict of ticker → OHLCV DataFrame for readiness gate.
            ihsg_df: IHSG index DataFrame for beta calculation.
            sectors: Dict of ticker → sector.
            market_caps: Dict of ticker → market cap.
            asset_classes: Dict of ticker → asset class.

        Returns:
            AdvisoryReport with screening results and top picks.
        """
        readiness_reports: dict[str, InstrumentReadinessReport] = {}
        skipped: list[str] = []

        if ohlcv_data:
            readiness_reports = self.readiness_gate.evaluate_batch(
                ohlcv_data,
                ihsg_df=ihsg_df,
                sectors=sectors,
                market_caps=market_caps,
                asset_classes=asset_classes,
            )
            skipped = [
                ticker for ticker, report in readiness_reports.items()
                if report.readiness_level not in {
                    ReadinessLevel.READY, ReadinessLevel.CONDITIONAL,
                }
            ]

        results = self.screen(
            universe,
            min_technical=min_technical,
            min_fundamental=min_fundamental,
            min_sentiment=min_sentiment,
            min_composite=min_composite,
            readiness_reports=readiness_reports if readiness_reports else None,
        )

        passed_results = [r for r in results if r.passed and r.decision]
        top_picks = sorted(
            [r.decision for r in passed_results if r.decision],
            key=lambda d: d.composite_score,
            reverse=True,
        )[:top_n]

        from datetime import UTC, datetime

        skipped_msg = f" {len(skipped)} skipped (not ready)." if skipped else ""
        summary = (
            f"Market regime: {market_regime}. "
            f"Screened {len(results)} stocks, {len(passed_results)} passed.{skipped_msg} "
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
            readiness_reports=readiness_reports,
            skipped_not_ready=skipped,
        )
