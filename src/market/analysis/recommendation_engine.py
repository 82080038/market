"""Recommendation Engine & Output (catatan.md TAHAP 7 -- Prompt 7.1).

Generate final recommendation yang menggabungkan semua tahap sebelumnya:

1. **Ticker, direction, entry/exit prices** -- dari signal generator + profile.
2. **Position size dalam rupiah dan lot** -- dari CapitalAwarePositionSizer.
3. **Trading style** (intraday/swing/investing) -- dari TradingStyleAdvisor.
4. **Reasoning dalam Bahasa Indonesia** -- human-readable explanation.
5. **Confidence score dan supporting data** -- combined from all sources.

Output: ``RecommendationReport`` berisi list ``Recommendation`` per ticker +
portfolio-level summary. Bisa di-render ke text/JSON untuk notifikasi
(``app_notifications``) atau API response.

Integrasi:
- ``EnhancedSignalGenerator`` → enhanced signals
- ``CapitalAwarePositionSizer`` → position sizing
- ``InstrumentBehaviorProfiler`` → profile + exit prices (ATR-based)
- ``TradingStyleAdvisor`` → style recommendation
- ``CrossMarketCoefficientEngine`` → overnight gap context

Referensi:
- catatan.md L672-L682 (Prompt 7.1)
- pustaka/92-multi-market-multi-asset-trading-system.md §8 (Output Layer)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from market.advisory.trading_style_advisor import TradingStyleAdvisor
from market.analysis.cross_market_coefficients import CrossMarketCoefficientEngine
from market.analysis.enhanced_signal_generator import (
    EnhancedSignal,
    EnhancedSignalGenerator,
)
from market.analysis.instrument_profiler import (
    InstrumentBehaviorProfiler,
)
from market.risk.capital_aware_sizer import (
    CapitalAwarePositionSizer,
    PositionSizingResult,
)
from market.risk.cost_model import TradingCostModel

logger = logging.getLogger(__name__)


@dataclass
class Recommendation:
    """Final recommendation for one instrument."""

    ticker: str
    direction: str  # BUY / SELL / HOLD
    entry_price: float | None
    target_price: float | None  # take-profit
    stop_loss_price: float | None
    # Position sizing
    shares: int
    lots: int
    value_idr: float
    position_pct_of_portfolio: float
    # Style
    trading_style: str  # intraday/swing/investing
    # Confidence & reasoning
    confidence: float  # 0-10
    reasoning: str
    supporting_data: dict[str, Any] = field(default_factory=dict)
    # Risk
    risk_per_trade_idr: float = 0.0
    potential_profit_idr: float = 0.0
    potential_loss_idr: float = 0.0
    reward_risk_ratio: float = 0.0
    # Trading costs
    estimated_cost_idr: float = 0.0
    net_potential_profit_idr: float = 0.0
    net_potential_loss_idr: float = 0.0
    net_reward_risk_ratio: float = 0.0
    # Profile context
    volatility_regime: str | None = None
    liquidity_score: float | None = None
    overnight_gap_prediction_pct: float = 0.0
    # Metadata
    approved: bool = True
    rejection_reason: str = ""
    generated_at: str = ""


@dataclass
class RecommendationReport:
    """Portfolio-level recommendation report."""

    user_id: str
    generated_at: str
    recommendations: list[Recommendation] = field(default_factory=list)
    portfolio_summary: dict[str, Any] = field(default_factory=dict)
    total_allocated_idr: float = 0.0
    total_risk_idr: float = 0.0
    total_potential_profit_idr: float = 0.0
    total_potential_loss_idr: float = 0.0
    average_confidence: float = 0.0
    # Style breakdown
    style_breakdown: dict[str, int] = field(default_factory=dict)  # {style: count}

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "generated_at": self.generated_at,
            "portfolio_summary": self.portfolio_summary,
            "total_allocated_idr": self.total_allocated_idr,
            "total_risk_idr": self.total_risk_idr,
            "total_potential_profit_idr": self.total_potential_profit_idr,
            "total_potential_loss_idr": self.total_potential_loss_idr,
            "average_confidence": self.average_confidence,
            "style_breakdown": self.style_breakdown,
            "recommendations": [asdict(r) for r in self.recommendations],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_text_summary(self) -> str:
        """Render human-readable Bahasa Indonesia summary."""
        lines: list[str] = []
        lines.append("=== LAPORAN REKOMENDASI TRADING ===")
        lines.append(f"User: {self.user_id}")
        lines.append(f"Waktu: {self.generated_at}")
        lines.append(f"Total alokasi: Rp {self.total_allocated_idr:,.0f}")
        lines.append(f"Total risiko: Rp {self.total_risk_idr:,.0f}")
        lines.append(f"Potensi profit (gross): Rp {self.total_potential_profit_idr:,.0f}")
        lines.append(f"Potensi loss (gross): Rp {self.total_potential_loss_idr:,.0f}")
        lines.append(f"Confidence rata-rata: {self.average_confidence:.2f}/10")
        lines.append(f"Distribusi gaya: {self.style_breakdown}")
        lines.append("")
        lines.append("--- REKOMENDASI PER TIKER ---")
        for r in self.recommendations:
            lines.append("")
            lines.append(f"[{r.direction}] {r.ticker} ({r.trading_style.upper()})")
            lines.append(f"  Entry: Rp {r.entry_price:,.0f}" if r.entry_price else "  Entry: -")
            lines.append(f"  Target: Rp {r.target_price:,.0f}" if r.target_price else "  Target: -")
            lines.append(
                f"  Stop Loss: Rp {r.stop_loss_price:,.0f}"
                if r.stop_loss_price else "  Stop Loss: -"
            )
            lines.append(f"  Position: {r.shares} saham ({r.lots} lot) = Rp {r.value_idr:,.0f}")
            lines.append(f"  % Portfolio: {r.position_pct_of_portfolio:.2f}%")
            lines.append(
                f"  Risk: Rp {r.risk_per_trade_idr:,.0f} | "
                f"Reward/Risk: {r.reward_risk_ratio:.2f} (gross)"
            )
            if r.estimated_cost_idr > 0:
                lines.append(
                    f"  Biaya round-trip: Rp {r.estimated_cost_idr:,.0f} | "
                    f"Net R/R: {r.net_reward_risk_ratio:.2f}"
                )
                lines.append(
                    f"  Net profit: Rp {r.net_potential_profit_idr:,.0f} | "
                    f"Net loss: Rp {r.net_potential_loss_idr:,.0f}"
                )
            lines.append(f"  Confidence: {r.confidence:.2f}/10")
            lines.append(f"  Vol regime: {r.volatility_regime} | Liquidity: {r.liquidity_score}/10")
            if r.overnight_gap_prediction_pct:
                lines.append(f"  Overnight gap prediksi: {r.overnight_gap_prediction_pct:+.2f}%")
            if not r.approved:
                lines.append(f"  ⚠ DITOLAK: {r.rejection_reason}")
            lines.append(f"  Reasoning: {r.reasoning}")
        return "\n".join(lines)


class RecommendationEngine:
    """Generate final recommendations combining all engines.

    Usage:
        engine = RecommendationEngine()
        report = engine.generate_report(
            raw_signals={
                "BBCA.JK": {"direction": 1, "raw_position": 0.05, "entry_price": 8500,
                            "win_rate": 0.55, "win_loss_ratio": 1.5},
                ...
            },
            user_id="default",
        )
        print(report.to_text_summary())
    """

    def __init__(
        self,
        signal_generator: EnhancedSignalGenerator | None = None,
        sizer: CapitalAwarePositionSizer | None = None,
        profiler: InstrumentBehaviorProfiler | None = None,
        advisor: TradingStyleAdvisor | None = None,
        cross_market: CrossMarketCoefficientEngine | None = None,
        cost_model: TradingCostModel | None = None,
    ) -> None:
        self.signal_generator = signal_generator or EnhancedSignalGenerator()
        self.sizer = sizer or CapitalAwarePositionSizer()
        self.profiler = profiler or InstrumentBehaviorProfiler()
        self.advisor = advisor or TradingStyleAdvisor()
        self.cross_market = cross_market or CrossMarketCoefficientEngine()
        self.cost_model = cost_model or TradingCostModel()

    def generate_report(
        self,
        raw_signals: dict[str, dict[str, Any]],
        user_id: str = "default",
        target_style: str | None = None,
    ) -> RecommendationReport:
        """Generate full recommendation report.

        Args:
            raw_signals: {ticker: {direction, raw_position, entry_price, win_rate, win_loss_ratio}}
            user_id: User profile ID.
            target_style: Force style for all. If None, derive from user profile.
        """
        # 1. Enhance signals with profile + cross-market
        enhanced = self.signal_generator.enhance_signals(
            raw_signals, target_style=target_style, user_id=user_id,
        )

        # 2. Size positions
        sizing_inputs: list[dict[str, Any]] = []
        style_map: dict[str, str] = {}
        for sig in enhanced:
            style = sig.recommended_style or target_style or "swing"
            style_map[sig.ticker] = style
            raw = raw_signals.get(sig.ticker, {})
            sizing_inputs.append({
                "ticker": sig.ticker,
                "direction": sig.direction,
                "entry_price": raw.get("entry_price") or sig.entry_price or 0.0,
                "win_rate": raw.get("win_rate", 0.55),
                "win_loss_ratio": raw.get("win_loss_ratio", 1.5),
                "target_style": style,
                "raw_position": sig.raw_position,
            })
        sizing_results = self.sizer.size_multiple(sizing_inputs, user_id=user_id)
        sizing_by_ticker = {r.ticker: r for r in sizing_results}

        # 3. Build recommendations
        recs: list[Recommendation] = []
        for sig in enhanced:
            sizing = sizing_by_ticker.get(sig.ticker)
            rec = self._build_recommendation(sig, sizing, style_map.get(sig.ticker, "swing"))
            recs.append(rec)

        # 4. Build report
        report = RecommendationReport(
            user_id=user_id,
            generated_at=datetime.now(UTC).isoformat(),
            recommendations=recs,
        )
        self._finalize_report(report)
        return report

    # ── internal ────────────────────────────────────────────────────────────

    def _build_recommendation(
        self,
        sig: EnhancedSignal,
        sizing: PositionSizingResult | None,
        style: str,
    ) -> Recommendation:
        direction_str = {1: "BUY", -1: "SELL", 0: "HOLD"}.get(sig.direction, "HOLD")
        entry = sig.entry_price or (sizing.entry_price if sizing else None)
        # Exit prices from profile volatility (ATR-like)
        target_price, stop_loss = self._compute_exit_prices(sig, entry)
        # Gross risk/reward
        risk_per_trade = sizing.risk_per_trade_idr if sizing else 0.0
        potential_profit = 0.0
        potential_loss = 0.0
        rr_ratio = 0.0
        # Net (after cost) risk/reward
        estimated_cost = 0.0
        net_profit = 0.0
        net_loss = 0.0
        net_rr = 0.0
        if entry and target_price and stop_loss and sizing and sizing.shares > 0:
            potential_profit = abs(target_price - entry) * sizing.shares
            potential_loss = abs(entry - stop_loss) * sizing.shares
            if potential_loss > 0:
                rr_ratio = round(potential_profit / potential_loss, 2)
            # Net after trading costs
            direction = sig.direction
            net_profit = self.cost_model.net_profit(
                sizing.shares, entry, target_price, direction,
            )
            net_loss = self.cost_model.net_loss(
                sizing.shares, entry, stop_loss, direction,
            )
            rt = self.cost_model.round_trip_cost(
                sizing.shares, entry, target_price,
            )
            estimated_cost = rt.total
            if net_loss > 0:
                net_rr = round(net_profit / net_loss, 2)
        # Reasoning
        reasoning = self._build_reasoning(sig, sizing, style, direction_str)
        # Supporting data
        supporting: dict[str, Any] = {
            "profile_confidence": sig.profile.profile_confidence if sig.profile else None,
            "cross_market_sources": sig.cross_market_sources,
            "sizing_reasoning": sizing.reasoning if sizing else "",
            "filter_reason": sig.filter_reason,
            "cost_filter_passed": sig.cost_filter_passed,
            "cost_filter_reason": sig.cost_filter_reason,
        }
        return Recommendation(
            ticker=sig.ticker,
            direction=direction_str,
            entry_price=entry,
            target_price=target_price,
            stop_loss_price=stop_loss,
            shares=sizing.shares if sizing else 0,
            lots=sizing.lots if sizing else 0,
            value_idr=sizing.value_idr if sizing else 0.0,
            position_pct_of_portfolio=sizing.position_pct_of_portfolio if sizing else 0.0,
            trading_style=style,
            confidence=sig.confidence,
            reasoning=reasoning,
            supporting_data=supporting,
            risk_per_trade_idr=risk_per_trade,
            potential_profit_idr=round(potential_profit, 2),
            potential_loss_idr=round(potential_loss, 2),
            reward_risk_ratio=rr_ratio,
            estimated_cost_idr=round(estimated_cost, 2),
            net_potential_profit_idr=round(net_profit, 2),
            net_potential_loss_idr=round(net_loss, 2),
            net_reward_risk_ratio=net_rr,
            volatility_regime=sig.profile.volatility_regime if sig.profile else None,
            liquidity_score=sig.profile.liquidity_score if sig.profile else None,
            overnight_gap_prediction_pct=sig.overnight_gap_prediction_pct,
            approved=(sizing.approved if sizing else False) and sig.passes_suitability_filter and sig.cost_filter_passed,
            rejection_reason=(
                sizing.rejection_reason if sizing and not sizing.approved
                else (sig.filter_reason if not sig.passes_suitability_filter
                      else (sig.cost_filter_reason if not sig.cost_filter_passed else ""))
            ),
            generated_at=datetime.now(UTC).isoformat(),
        )

    def _compute_exit_prices(
        self, sig: EnhancedSignal, entry: float | None,
    ) -> tuple[float | None, float | None]:
        """Compute target & stop-loss based on profile volatility (ATR-like).

        Target = entry ± 2x daily volatility (reward)
        Stop = entry ∓ 1x daily volatility (risk)
        """
        if entry is None or entry <= 0:
            return (None, None)
        vol_pct = (
            float(sig.profile.avg_daily_volatility) / 100.0
            if sig.profile and sig.profile.avg_daily_volatility
            else 0.02
        )
        direction = sig.direction
        if direction == 0:
            return (None, None)
        # BUY: target above, stop below. SELL: opposite.
        target = entry * (1 + 2 * vol_pct * direction)
        stop = entry * (1 - 1 * vol_pct * direction)
        return (round(target, 2), round(stop, 2))

    def _build_reasoning(
        self,
        sig: EnhancedSignal,
        sizing: PositionSizingResult | None,
        style: str,
        direction_str: str,
    ) -> str:
        parts: list[str] = []
        parts.append(f"{direction_str} {sig.ticker} untuk gaya {style}.")
        if sig.profile:
            parts.append(
                f"Volatility regime: {sig.profile.volatility_regime}, "
                f"liquidity score: {sig.profile.liquidity_score}/10, "
                f"beta IHSG: {sig.profile.beta_to_ihsg}."
            )
            suit = {
                "intraday": sig.intraday_suitability,
                "swing": sig.swing_suitability,
                "investing": sig.investing_suitability,
            }.get(style)
            if suit is not None:
                parts.append(f"Suitability {style}: {suit}/10.")
        if sig.cross_market_sources:
            srcs = ", ".join(
                f"{s['source']} (coef={s['coefficient']:.3f}, p={s['p_value']:.3f})"
                for s in sig.cross_market_sources[:3]
            )
            parts.append(f"Cross-market: {srcs}.")
        if sig.overnight_gap_prediction_pct:
            parts.append(
                f"Prediksi overnight gap: {sig.overnight_gap_prediction_pct:+.2f}%."
            )
        if sizing and sizing.approved:
            parts.append(
                f"Position: {sizing.shares} saham ({sizing.lots} lot) = "
                f"Rp {sizing.value_idr:,.0f} ({sizing.position_pct_of_portfolio:.2f}% portofolio)."
            )
            parts.append(
                f"Kelly: raw={sizing.kelly_fraction_raw}, "
                f"capped={sizing.kelly_fraction_capped}."
            )
            if sizing.estimated_round_trip_cost_idr > 0:
                parts.append(
                    f"Biaya round-trip: Rp {sizing.estimated_round_trip_cost_idr:,.0f} "
                    f"(rate {sizing.round_trip_cost_rate*100:.2f}%)."
                )
        elif sizing:
            parts.append(f"DITOLAK: {sizing.rejection_reason}")
        if not sig.passes_suitability_filter:
            parts.append(f"Filter suitability: {sig.filter_reason}")
        parts.append(f"Confidence: {sig.confidence:.2f}/10.")
        return " ".join(parts)

    def _finalize_report(self, report: RecommendationReport) -> None:
        """Compute portfolio-level aggregates."""
        approved = [r for r in report.recommendations if r.approved]
        report.total_allocated_idr = round(sum(r.value_idr for r in approved), 2)
        report.total_risk_idr = round(sum(r.risk_per_trade_idr for r in approved), 2)
        report.total_potential_profit_idr = round(sum(r.potential_profit_idr for r in approved), 2)
        report.total_potential_loss_idr = round(sum(r.potential_loss_idr for r in approved), 2)
        if approved:
            report.average_confidence = round(
                sum(r.confidence for r in approved) / len(approved), 2
            )
        # Style breakdown
        breakdown: dict[str, int] = {}
        for r in report.recommendations:
            breakdown[r.trading_style] = breakdown.get(r.trading_style, 0) + 1
        report.style_breakdown = breakdown
        # Portfolio summary
        report.portfolio_summary = {
            "total_recommendations": len(report.recommendations),
            "approved": len(approved),
            "rejected": len(report.recommendations) - len(approved),
            "buy_signals": sum(1 for r in report.recommendations if r.direction == "BUY"),
            "sell_signals": sum(1 for r in report.recommendations if r.direction == "SELL"),
            "hold_signals": sum(1 for r in report.recommendations if r.direction == "HOLD"),
            "total_estimated_cost_idr": round(sum(r.estimated_cost_idr for r in approved), 2),
            "total_net_profit_idr": round(sum(r.net_potential_profit_idr for r in approved), 2),
            "total_net_loss_idr": round(sum(r.net_potential_loss_idr for r in approved), 2),
        }


__all__ = [
    "Recommendation",
    "RecommendationEngine",
    "RecommendationReport",
]
