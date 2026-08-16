"""Enhanced Signal Generator (catatan.md TAHAP 5 -- Prompt 5.1).

Wrapper/enhancement layer yang mengintegrasikan output signal generator
existing (``generate_ticker_signals``) dengan:

1. **InstrumentBehaviorProfiler** -- query profile sebelum generate signal.
2. **Trading style suitability** -- filter/score berdasarkan suitability
   intraday/swing/investing dari profile.
3. **Cross-market coefficients** -- apply untuk overnight gap prediction.
4. **Position sizing** -- respect ``optimal_position_size_pct`` dari profile.

Filosofi: tidak memodifikasi ``generate_ticker_signals`` yang sudah berjalan
produksi (prinsip "jangan modifikasi kode yang bekerja"). Sebagai gantinya,
modul ini menyediakan ``EnhancedSignalGenerator`` yang membungkus signal
mentah dan menambahkan metadata + filter berdasarkan profile/cross-market.

Output: ``EnhancedSignal`` dengan field original (direction, position) +
enhancement (profile, suitability, gap_prediction, sizing_reasoning).

Referensi:
- catatan.md L646-L655 (Prompt 5.1)
- pustaka/92-multi-market-multi-asset-trading-system.md §6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from market.advisory.trading_style_advisor import (
    TradingStyleAdvisor,
    UserProfile,
)
from market.analysis.cross_market_coefficients import (
    CrossMarketCoefficientEngine,
)
from market.analysis.instrument_profiler import (
    InstrumentBehaviorProfiler,
    InstrumentProfile,
)
from market.risk.cost_model import TradingCostModel

logger = logging.getLogger(__name__)


@dataclass
class EnhancedSignal:
    """Signal enhanced dengan profile + cross-market context."""

    ticker: str
    direction: int  # +1 BUY, -1 SELL, 0 HOLD (dari signal generator original)
    raw_position: float  # position size fraction dari generator original
    entry_price: float | None = None
    # Profile context
    profile: InstrumentProfile | None = None
    # Suitability scores (1-10) dari profile
    intraday_suitability: float | None = None
    swing_suitability: float | None = None
    investing_suitability: float | None = None
    # Filter decision
    passes_suitability_filter: bool = True
    filter_reason: str = ""
    # Cross-market gap prediction
    overnight_gap_prediction_pct: float = 0.0
    cross_market_sources: list[dict[str, Any]] = field(default_factory=list)
    # Position sizing (respecting optimal_position_size_pct)
    adjusted_position_pct: float | None = None
    sizing_reasoning: str = ""
    # Final confidence (combined signal + profile)
    confidence: float = 0.0
    # Trading style recommendation for this signal
    recommended_style: str = ""  # intraday/swing/investing
    # Cost filter
    cost_filter_passed: bool = True
    cost_filter_reason: str = ""


class EnhancedSignalGenerator:
    """Wrap raw signal generator output with profile + cross-market context.

    Usage:
        gen = EnhancedSignalGenerator()
        signals = gen.enhance_signals({
            "BBCA.JK": {"direction": 1, "raw_position": 0.3, "entry_price": 8500},
            ...
        })
    """

    def __init__(
        self,
        profiler: InstrumentBehaviorProfiler | None = None,
        cross_market: CrossMarketCoefficientEngine | None = None,
        advisor: TradingStyleAdvisor | None = None,
        cost_model: TradingCostModel | None = None,
        min_suitability_score: float = 4.0,
        enable_cost_filter: bool = True,
    ) -> None:
        self.profiler = profiler or InstrumentBehaviorProfiler()
        self.cross_market = cross_market or CrossMarketCoefficientEngine()
        self.advisor = advisor or TradingStyleAdvisor()
        self.cost_model = cost_model or TradingCostModel()
        self.min_suitability_score = min_suitability_score
        self.enable_cost_filter = enable_cost_filter

    def enhance_signal(
        self,
        ticker: str,
        direction: int,
        raw_position: float,
        entry_price: float | None = None,
        target_style: str | None = None,
        user_profile: UserProfile | None = None,
    ) -> EnhancedSignal:
        """Enhance single signal with profile + cross-market context.

        Args:
            ticker: Instrument ticker.
            direction: +1/0/-1 from raw signal generator.
            raw_position: Position size fraction (0-1) from raw generator.
            entry_price: Entry price (optional).
            target_style: If set, check suitability for this style only.
            user_profile: If set, use to determine target_style automatically.
        """
        sig = EnhancedSignal(
            ticker=ticker, direction=direction,
            raw_position=raw_position, entry_price=entry_price,
        )

        # 1. Query profile
        sig.profile = self.profiler.get_profile(ticker)
        if sig.profile is not None:
            sig.intraday_suitability = sig.profile.intraday_suitability
            sig.swing_suitability = sig.profile.swing_suitability
            sig.investing_suitability = sig.profile.investing_suitability

        # 2. Determine target style
        if target_style is None and user_profile is not None:
            try:
                rec = self.advisor.recommend_style(user_profile.user_id)
                target_style = rec.primary_style
            except Exception:
                target_style = "swing"  # default

        # 3. Suitability filter
        sig = self._apply_suitability_filter(sig, target_style)
        if not sig.passes_suitability_filter:
            sig.confidence = 0.0
            return sig

        # 3b. Cost filter — reject if expected move < break-even cost
        if self.enable_cost_filter:
            sig = self._apply_cost_filter(sig)
            if not sig.cost_filter_passed:
                sig.confidence = 0.0
                return sig

        # 4. Cross-market gap prediction
        sig = self._apply_cross_market_prediction(sig)

        # 5. Position sizing (respect optimal_position_size_pct)
        sig = self._apply_position_sizing(sig)

        # 6. Confidence
        sig.confidence = self._compute_confidence(sig, target_style)
        sig.recommended_style = target_style or "swing"
        return sig

    def enhance_signals(
        self,
        raw_signals: dict[str, dict[str, Any]],
        target_style: str | None = None,
        user_id: str | None = None,
    ) -> list[EnhancedSignal]:
        """Enhance multiple signals at once.

        Args:
            raw_signals: {ticker: {"direction": int, "raw_position": float, ...}}
            target_style: Force this style for all. If None, derive from user profile.
            user_id: If target_style is None, load user profile to determine style.
        """
        user_profile = None
        if target_style is None and user_id is not None:
            user_profile = self.advisor.get_profile(user_id)
        out: list[EnhancedSignal] = []
        for ticker, raw in raw_signals.items():
            try:
                sig = self.enhance_signal(
                    ticker=ticker,
                    direction=int(raw.get("direction", 0)),
                    raw_position=float(raw.get("raw_position", 0.0)),
                    entry_price=raw.get("entry_price"),
                    target_style=target_style,
                    user_profile=user_profile,
                )
                out.append(sig)
            except Exception as exc:
                logger.warning("enhance_signal %s failed: %s", ticker, exc)
        return out

    # ── internal helpers ────────────────────────────────────────────────────

    def _apply_cost_filter(self, sig: EnhancedSignal) -> EnhancedSignal:
        """Check if expected price move exceeds round-trip trading cost.

        Uses the instrument's avg_daily_volatility as the expected move
        (1-day ATR proxy). If the expected move is smaller than the
        break-even round-trip cost, the signal is rejected because
        the trade cannot profitably cover its own costs.

        For swing/investing styles, the expected move is multiplied by
        the holding period factor (swing=3x, investing=10x) since longer
        holds capture larger moves.
        """
        if sig.profile is None or sig.profile.avg_daily_volatility is None:
            sig.cost_filter_passed = True
            sig.cost_filter_reason = "no profile -- cost filter skipped"
            return sig
        if sig.direction == 0:
            sig.cost_filter_passed = True
            sig.cost_filter_reason = "HOLD -- no cost"
            return sig
        daily_vol_pct = float(sig.profile.avg_daily_volatility)
        # Holding period factor: swing ~3 days, investing ~10 days, intraday ~1
        # The expected move scales with sqrt(time) but we use linear as
        # a conservative approximation.
        style_factor = {"intraday": 1.0, "swing": 3.0, "investing": 10.0}.get(
            sig.recommended_style or "swing", 3.0,
        )
        expected_move_pct = daily_vol_pct * style_factor
        break_even_pct = self.cost_model.break_even_move_pct()
        if expected_move_pct < break_even_pct:
            sig.cost_filter_passed = False
            sig.cost_filter_reason = (
                f"Expected move {expected_move_pct:.2f}% < break-even cost "
                f"{break_even_pct:.2f}% (round-trip) -- trade tidak profitable"
            )
        else:
            sig.cost_filter_passed = True
            sig.cost_filter_reason = (
                f"Expected move {expected_move_pct:.2f}% >= break-even "
                f"{break_even_pct:.2f}% -- OK"
            )
        return sig

    def _apply_suitability_filter(
        self, sig: EnhancedSignal, target_style: str | None,
    ) -> EnhancedSignal:
        """Check if instrument is suitable for target_style."""
        if sig.profile is None:
            sig.passes_suitability_filter = True
            sig.filter_reason = "no profile -- passthrough"
            return sig
        if target_style is None:
            sig.passes_suitability_filter = True
            sig.filter_reason = "no target style -- passthrough"
            return sig
        score_map = {
            "intraday": sig.intraday_suitability,
            "swing": sig.swing_suitability,
            "investing": sig.investing_suitability,
        }
        score = score_map.get(target_style)
        if score is None:
            sig.passes_suitability_filter = True
            sig.filter_reason = f"no {target_style} suitability score -- passthrough"
            return sig
        if score < self.min_suitability_score:
            sig.passes_suitability_filter = False
            sig.filter_reason = (
                f"{target_style} suitability {score} < minimum {self.min_suitability_score}"
            )
        else:
            sig.passes_suitability_filter = True
            sig.filter_reason = (
                f"{target_style} suitability {score} >= {self.min_suitability_score}"
            )
        return sig

    def _apply_cross_market_prediction(self, sig: EnhancedSignal) -> EnhancedSignal:
        """Apply cross-market coefficients for overnight gap prediction.

        Only meaningful for IDX tickers (target = ^JKSE). For individual stocks,
        we use the stock's beta to IHSG x IHSG's predicted gap from global indices.
        """
        if sig.profile is None or sig.profile.beta_to_ihsg is None:
            return sig
        # Get IHSG predicted gap from global indices
        ihsg_gap_pct = 0.0
        sources: list[dict[str, Any]] = []
        for src in ["^GSPC", "^HSI", "^N225"]:
            try:
                coef = self.cross_market.get_coefficient(src, "^JKSE", lag=1)
                if coef is None or coef.coefficient is None:
                    continue
                # We don't have today's source return here; in production this
                # would be fetched from latest OHLCV. For now, store coefficient
                # as the structural sensitivity.
                sources.append({
                    "source": src,
                    "coefficient": coef.coefficient,
                    "p_value": coef.p_value,
                    "regime": coef.regime,
                })
                # Accumulate structural sensitivity (will be multiplied by actual
                # source return at signal generation time)
                ihsg_gap_pct += abs(coef.coefficient)
            except Exception:
                continue
        # Stock gap = beta x IHSG gap
        beta = sig.profile.beta_to_ihsg
        sig.overnight_gap_prediction_pct = round(beta * ihsg_gap_pct * 100, 4)
        sig.cross_market_sources = sources
        return sig

    def _apply_position_sizing(self, sig: EnhancedSignal) -> EnhancedSignal:
        """Respect optimal_position_size_pct from profile."""
        if sig.profile is None or sig.profile.optimal_position_size_pct is None:
            sig.adjusted_position_pct = sig.raw_position
            sig.sizing_reasoning = "no profile -- using raw position"
            return sig
        optimal = sig.profile.optimal_position_size_pct
        # Cap raw_position at optimal
        if sig.raw_position > optimal:
            sig.adjusted_position_pct = optimal
            sig.sizing_reasoning = (
                f"raw {sig.raw_position:.4f} capped at optimal {optimal:.4f} "
                f"(liquidity constraint from profile)"
            )
        else:
            sig.adjusted_position_pct = sig.raw_position
            sig.sizing_reasoning = (
                f"raw {sig.raw_position:.4f} within optimal {optimal:.4f} -- no cap needed"
            )
        return sig

    @staticmethod
    def _compute_confidence(sig: EnhancedSignal, target_style: str | None) -> float:
        """Combine signal direction strength + profile confidence + suitability."""
        if not sig.passes_suitability_filter:
            return 0.0
        if not sig.cost_filter_passed:
            return 0.0
        score = 5.0
        # Signal direction strength
        score += min(2.0, abs(sig.raw_position) * 4)
        # Profile confidence
        if sig.profile and sig.profile.profile_confidence is not None:
            score += (sig.profile.profile_confidence - 5) * 0.3
        # Suitability for target style
        if target_style and sig.profile:
            suit_map = {
                "intraday": sig.intraday_suitability,
                "swing": sig.swing_suitability,
                "investing": sig.investing_suitability,
            }
            s = suit_map.get(target_style)
            if s is not None:
                score += (s - 5) * 0.3
        # Cross-market corroboration
        if sig.overnight_gap_prediction_pct > 0 and sig.direction > 0:
            score += 0.5  # gap predicts up + BUY signal
        elif sig.overnight_gap_prediction_pct < 0 and sig.direction < 0:
            score += 0.5  # gap predicts down + SELL signal
        return float(max(0.0, min(10.0, round(score, 2))))


__all__ = ["EnhancedSignal", "EnhancedSignalGenerator"]
