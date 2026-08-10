"""Signal Enhancer — integrates 7 doc-97 modules into prediction pipeline.

Wraps the existing ``PredictionEngine._predict_ensemble`` output and enhances
it with non-trend-following signals from:

1. **Volume features** (``volume_features.py``) — OFI, VWAP deviation, OBV
   divergence, foreign flow momentum. Adds a volume confirmation signal.
2. **Policy event scorer** (``policy_event_scorer.py``) — BI/Fed rate,
   buyback, rights issue, earnings. Adds an event-driven directional bias.
3. **Meta-labeling** (``meta_labeling.py``) — LightGBM secondary model that
   predicts P(primary prediction correct). Adjusts confidence/bet size.
4. **Sector rotation** (``sector_rotation.py``) — sector momentum and rank
   rotation. Adds a sector-level directional bias.
5. **Pairs trading** (``pairs_trading.py``) — cointegration spread Z-score.
   Adds a mean-reversion signal orthogonal to trend.

The enhancer is **additive and optional**: if any module's input data is
unavailable, it silently skips that signal (graceful degradation). The
existing prediction engine output is never degraded — only enhanced.

Design principles:
- NO LOOK-AHEAD: all signals use only data <= as_of.
- CPU-ONLY: no GPU needed for these computations.
- GRACEFUL: missing data → skip, don't crash.
- COMPOSABLE: each signal source independently adjusts the base prediction.

Integration point: called after ``PredictionEngine.predict()`` returns a
``Prediction`` object. The enhancer modifies confidence, direction, and
rationale in-place (returns a new ``Prediction`` copy).

References:
- pustaka/97-strategi-alternatif-ekspansi-data-2026.md (7 modul)
- pustaka/23-machine-learning-trading.md §7 (meta-labeling)
- pustaka/89-faktor-pasar-modal-analisis-implementasi.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from market.analysis.meta_labeling import MetaLabeler, MetaLabelResult
    from market.analysis.pairs_trading import PairsTradingEngine
    from market.analysis.policy_event_scorer import PolicyEventScorer
    from market.analysis.prediction import Prediction
    from market.analysis.sector_rotation import SectorRotationEngine
    from market.analysis.volume_features import (
        compute_foreign_flow_signal,
        compute_ofi_proxy,
        compute_vwap,
        detect_obv_divergence,
    )

logger = logging.getLogger(__name__)


@dataclass
class EnhancementSignal:
    """A single enhancement signal from one of the 7 modules.

    Attributes:
        source: Module name (e.g. "volume", "event", "meta", "sector", "pairs").
        signal: Directional signal in [-1, +1]. Positive = bullish, negative = bearish.
        confidence_adjustment: Multiplicative confidence adjustment (e.g. 1.15 = boost 15%).
        rationale: Human-readable explanation.
        available: Whether the signal was successfully computed.
    """

    source: str
    signal: float = 0.0
    confidence_adjustment: float = 1.0
    rationale: str = ""
    available: bool = False


@dataclass
class EnhancementResult:
    """Result of enhancing a base prediction with 7 signal sources.

    Attributes:
        enhanced_prediction: The modified Prediction (new object).
        signals: List of EnhancementSignal from each source.
        final_confidence: Confidence after all adjustments.
        final_direction: Direction after all adjustments.
        bet_size: Meta-labeler bet size [0, 1] (1.0 if no meta-labeler).
        total_adjustment: Net directional adjustment from all signals.
    """

    enhanced_prediction: "Prediction"
    signals: list[EnhancementSignal] = field(default_factory=list)
    final_confidence: float = 0.0
    final_direction: str = "flat"
    bet_size: float = 1.0
    total_adjustment: float = 0.0


class SignalEnhancer:
    """Enhances base prediction with 7 non-trend signal sources.

    Usage::

        enhancer = SignalEnhancer(
            meta_labeler=meta_labeler,
            policy_scorer=policy_scorer,
            pairs_engine=pairs_engine,
            sector_engine=sector_engine,
        )
        result = enhancer.enhance(base_prediction, ohlcv_df, ticker, as_of)
        if result.bet_size < 0.1:
            # Meta-labeler says: don't trade this prediction
            ...
    """

    def __init__(
        self,
        meta_labeler: "MetaLabeler | None" = None,
        policy_scorer: "PolicyEventScorer | None" = None,
        pairs_engine: "PairsTradingEngine | None" = None,
        sector_engine: "SectorRotationEngine | None" = None,
        volume_weight: float = 0.15,
        event_weight: float = 0.15,
        sector_weight: float = 0.10,
        pairs_weight: float = 0.10,
        meta_weight: float = 0.20,
        signal_threshold: float = 0.15,
    ) -> None:
        """Initialize the signal enhancer.

        Args:
            meta_labeler: Trained MetaLabeler instance (or None to skip).
            policy_scorer: PolicyEventScorer instance (or None to skip).
            pairs_engine: PairsTradingEngine instance (or None to skip).
            sector_engine: SectorRotationEngine instance (or None to skip).
            volume_weight: Weight for volume signal adjustment.
            event_weight: Weight for event signal adjustment.
            sector_weight: Weight for sector signal adjustment.
            pairs_weight: Weight for pairs signal adjustment.
            meta_weight: Weight for meta-labeler bet size adjustment.
            signal_threshold: Minimum |total_adjustment| to flip direction.
        """
        self.meta_labeler = meta_labeler
        self.policy_scorer = policy_scorer
        self.pairs_engine = pairs_engine
        self.sector_engine = sector_engine
        self.volume_weight = volume_weight
        self.event_weight = event_weight
        self.sector_weight = sector_weight
        self.pairs_weight = pairs_weight
        self.meta_weight = meta_weight
        self.signal_threshold = signal_threshold

    def enhance(
        self,
        base: "Prediction",
        df: pd.DataFrame,
        ticker: str,
        as_of: str | pd.Timestamp,
        foreign_flow: pd.Series | None = None,
        sector: str | None = None,
        pair_ticker: str | None = None,
        pair_prices: pd.Series | None = None,
    ) -> EnhancementResult:
        """Enhance a base prediction with all available signal sources.

        Args:
            base: Base prediction from PredictionEngine.predict().
            df: OHLCV DataFrame (full, will be truncated to as_of).
            ticker: Ticker being predicted.
            as_of: Prediction cutoff date.
            foreign_flow: Optional foreign net-flow series for volume signal.
            sector: Optional sector name for sector rotation signal.
            pair_ticker: Optional cointegrated pair ticker for pairs signal.
            pair_prices: Optional close prices for the pair leg.

        Returns:
            EnhancementResult with enhanced prediction and signal details.
        """
        signals: list[EnhancementSignal] = []

        # Truncate data to as_of (no look-ahead).
        cutoff = pd.Timestamp(as_of)
        df_trunc = df.loc[:cutoff].copy()
        if df_trunc.empty:
            return EnhancementResult(
                enhanced_prediction=base,
                signals=signals,
                final_confidence=base.confidence,
                final_direction=base.predicted_direction,
            )

        # 1. Volume features signal.
        vol_sig = self._compute_volume_signal(df_trunc, foreign_flow)
        signals.append(vol_sig)

        # 2. Policy event signal.
        event_sig = self._compute_event_signal(ticker, as_of)
        signals.append(event_sig)

        # 3. Sector rotation signal.
        sector_sig = self._compute_sector_signal(df_trunc, sector)
        signals.append(sector_sig)

        # 4. Pairs trading signal.
        pairs_sig = self._compute_pairs_signal(df_trunc, ticker, pair_ticker, pair_prices)
        signals.append(pairs_sig)

        # 5. Meta-labeler bet sizing.
        meta_sig = self._compute_meta_signal(
            df, base, ticker, as_of, foreign_flow
        )
        signals.append(meta_sig)

        # Aggregate directional adjustments.
        total_adj = 0.0
        conf_mult = 1.0
        bet_size = 1.0

        for sig in signals:
            if not sig.available:
                continue
            if sig.source == "volume":
                total_adj += sig.signal * self.volume_weight
            elif sig.source == "event":
                total_adj += sig.signal * self.event_weight
            elif sig.source == "sector":
                total_adj += sig.signal * self.sector_weight
            elif sig.source == "pairs":
                total_adj += sig.signal * self.pairs_weight
            elif sig.source == "meta":
                bet_size = sig.signal  # meta-labeler returns bet size directly
            conf_mult *= sig.confidence_adjustment

        # Apply adjustments to base prediction.
        from market.analysis.prediction import Prediction

        new_confidence = max(0.05, min(1.0, base.confidence * conf_mult))
        new_direction = base.predicted_direction
        new_ret_pct = base.predicted_return_pct

        # Direction flip if total adjustment is strong enough.
        if abs(total_adj) > self.signal_threshold:
            if total_adj > 0 and base.predicted_direction != "up":
                new_direction = "up"
                new_ret_pct = abs(base.predicted_return_pct) * 0.5 + total_adj * 2
            elif total_adj < 0 and base.predicted_direction != "down":
                new_direction = "down"
                new_ret_pct = -(abs(base.predicted_return_pct) * 0.5 + abs(total_adj) * 2)

        # Apply meta-labeler bet size to confidence.
        if bet_size < 1.0:
            new_confidence *= bet_size
            if bet_size < 0.1:
                new_direction = "flat"
                new_ret_pct = 0.0

        # Build enhanced prediction.
        rationale_parts = [base.rationale]
        for sig in signals:
            if sig.available and sig.rationale:
                rationale_parts.append(f"[{sig.source}] {sig.rationale}")

        enhanced = Prediction(
            ticker=base.ticker,
            as_of=base.as_of,
            method=base.method,
            predicted_price=base.predicted_price,
            predicted_direction=new_direction,
            predicted_return_pct=round(new_ret_pct, 2),
            confidence=round(new_confidence, 3),
            horizon_days=base.horizon_days,
            indicators_used=base.indicators_used,
            pattern_signals=base.pattern_signals,
            rationale=" ".join(rationale_parts),
        )

        return EnhancementResult(
            enhanced_prediction=enhanced,
            signals=signals,
            final_confidence=new_confidence,
            final_direction=new_direction,
            bet_size=bet_size,
            total_adjustment=total_adj,
        )

    # ── Individual signal computations ──────────────────────────────────

    def _compute_volume_signal(
        self,
        df: pd.DataFrame,
        foreign_flow: pd.Series | None,
    ) -> EnhancementSignal:
        """Compute volume-based signal: OFI + VWAP deviation + OBV + foreign flow."""
        try:
            from market.analysis.volume_features import (
                compute_foreign_flow_signal,
                compute_ofi_proxy,
                compute_vwap,
                detect_obv_divergence,
            )

            if len(df) < 20 or "close" not in df.columns:
                return EnhancementSignal(source="volume")

            close = df["close"].astype(float)
            high = df["high"].astype(float) if "high" in df.columns else close
            low = df["low"].astype(float) if "low" in df.columns else close
            if "volume" not in df.columns:
                return EnhancementSignal(source="volume")
            volume = df["volume"].astype(float)
            if volume.sum() == 0:
                return EnhancementSignal(source="volume")

            # OFI proxy: buy/sell pressure. Note: args are (close, volume, high, low).
            ofi_result = compute_ofi_proxy(close, volume, high, low)
            ofi_latest = float(ofi_result.ofi_5.iloc[-1]) if not ofi_result.ofi_5.empty else 0.0

            # VWAP deviation.
            vwap_result = compute_vwap(high, low, close, volume, window=20)
            vwap_dev = float(vwap_result.deviation.iloc[-1]) if not vwap_result.deviation.empty else 0.0

            # OBV divergence — need OBV series, compute simple OBV from close+volume.
            obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
            obv_div = detect_obv_divergence(close, obv, window=20)
            obv_signal = 0.0
            if obv_div.divergence_type == "bullish":
                obv_signal = 0.5 * obv_div.strength
            elif obv_div.divergence_type == "bearish":
                obv_signal = -0.5 * obv_div.strength

            # Foreign flow momentum.
            ff_signal = 0.0
            ff_label = "none"
            if foreign_flow is not None and not foreign_flow.empty:
                ff_result = compute_foreign_flow_signal(foreign_flow, window=5)
                ff_signal = float(ff_result.z_score) / 3.0  # normalize Z to ~[-1, 1]
                ff_signal = np.clip(ff_signal, -1, 1)
                ff_label = ff_result.signal

            # Aggregate volume signal.
            vol_signal = np.clip(ofi_latest + vwap_dev * 5 + obv_signal + ff_signal, -1, 1)

            # Confidence adjustment: volume confirmation.
            tech_direction = 1.0 if close.iloc[-1] > close.iloc[-5] else -1.0
            vol_direction = 1.0 if vol_signal > 0 else -1.0
            conf_adj = 1.10 if tech_direction == vol_direction else 0.90

            return EnhancementSignal(
                source="volume",
                signal=float(vol_signal),
                confidence_adjustment=conf_adj,
                rationale=f"OFI5={ofi_latest:.2f}, VWAP_dev={vwap_dev:.3f}, OBV={obv_div.divergence_type}({obv_div.strength:.2f}), FF={ff_label}",
                available=True,
            )
        except Exception as e:
            logger.debug("Volume signal failed: %s", e)
            return EnhancementSignal(source="volume")

    def _compute_event_signal(
        self,
        ticker: str,
        as_of: str | pd.Timestamp,
    ) -> EnhancementSignal:
        """Compute policy event signal from PolicyEventScorer."""
        try:
            if self.policy_scorer is None:
                return EnhancementSignal(source="event")

            event_signal = self.policy_scorer.compute_event_signal(
                ticker=ticker,
                as_of_date=pd.Timestamp(as_of),
            )

            if event_signal is None:
                return EnhancementSignal(source="event")

            # Normalize: event_signal.composite_score is [-100, +100].
            normalized = float(event_signal.composite_score) / 100.0
            normalized = np.clip(normalized, -1, 1)

            # Confidence adjustment: strong events boost or reduce confidence.
            conf_adj = 1.0 + abs(normalized) * 0.10

            return EnhancementSignal(
                source="event",
                signal=normalized,
                confidence_adjustment=conf_adj,
                rationale=f"score={event_signal.composite_score:.1f}, n_events={event_signal.n_events}",
                available=True,
            )
        except Exception as e:
            logger.debug("Event signal failed: %s", e)
            return EnhancementSignal(source="event")

    def _compute_sector_signal(
        self,
        df: pd.DataFrame,
        sector: str | None,
    ) -> EnhancementSignal:
        """Compute sector rotation signal."""
        try:
            if self.sector_engine is None or sector is None:
                return EnhancementSignal(source="sector")

            # Get sector recommendation.
            recommendation = self.sector_engine.recommend_sectors(
                prices=pd.DataFrame({sector: df["close"]}),
                tickers=[sector],
            )

            if not recommendation:
                return EnhancementSignal(source="sector")

            rec = recommendation[0]
            # Use rotation_signal as directional bias.
            sig = float(rec.rotation_signal) if hasattr(rec, "rotation_signal") else 0.0
            sig = np.clip(sig, -1, 1)

            return EnhancementSignal(
                source="sector",
                signal=sig,
                confidence_adjustment=1.0,
                rationale=f"sector={sector}, rotation={sig:.2f}",
                available=True,
            )
        except Exception as e:
            logger.debug("Sector signal failed: %s", e)
            return EnhancementSignal(source="sector")

    def _compute_pairs_signal(
        self,
        df: pd.DataFrame,
        ticker: str,
        pair_ticker: str | None,
        pair_prices: pd.Series | None,
    ) -> EnhancementSignal:
        """Compute pairs trading Z-score signal (mean-reversion)."""
        try:
            if self.pairs_engine is None or pair_ticker is None or pair_prices is None:
                return EnhancementSignal(source="pairs")

            if "close" not in df.columns or len(df) < 60:
                return EnhancementSignal(source="pairs")

            price_a = df["close"].astype(float)
            price_b = pair_prices.astype(float).reindex(price_a.index).dropna()
            price_a = price_a.reindex(price_b.index)

            if len(price_a) < 60:
                return EnhancementSignal(source="pairs")

            # Compute spread and Z-score.
            spread = self.pairs_engine.compute_spread(price_a, price_b)
            z = self.pairs_engine.compute_zscore(spread, look_ahead_safe=True)
            z_latest = float(z.iloc[-1]) if not z.empty else 0.0

            if np.isnan(z_latest):
                return EnhancementSignal(source="pairs")

            # Pairs signal is mean-reverting: high Z → short spread → bearish for A.
            # Z > 2 → spread too wide → expect reversion → A will fall relative to B.
            # Z < -2 → spread too narrow → expect reversion → A will rise relative to B.
            pairs_signal = np.clip(-z_latest / 4.0, -1, 1)

            return EnhancementSignal(
                source="pairs",
                signal=float(pairs_signal),
                confidence_adjustment=1.05 if abs(z_latest) > 2.0 else 1.0,
                rationale=f"pair={pair_ticker}, Z={z_latest:.2f}",
                available=True,
            )
        except Exception as e:
            logger.debug("Pairs signal failed: %s", e)
            return EnhancementSignal(source="pairs")

    def _compute_meta_signal(
        self,
        df: pd.DataFrame,
        base: "Prediction",
        ticker: str,
        as_of: str | pd.Timestamp,
        foreign_flow: pd.Series | None,
    ) -> EnhancementSignal:
        """Compute meta-labeler bet sizing signal."""
        try:
            if self.meta_labeler is None or self.meta_labeler._model is None:
                return EnhancementSignal(source="meta")

            # Convert direction to side.
            side = 1 if base.predicted_direction == "up" else -1 if base.predicted_direction == "down" else 0

            if side == 0:
                return EnhancementSignal(
                    source="meta",
                    signal=0.0,
                    confidence_adjustment=1.0,
                    rationale="flat primary → no trade",
                    available=True,
                )

            # Get foreign flow value at as_of.
            ff_val = None
            if foreign_flow is not None and not foreign_flow.empty:
                cutoff = pd.Timestamp(as_of)
                ff_before = foreign_flow.loc[:cutoff]
                if not ff_before.empty:
                    ff_val = float(ff_before.iloc[-1])

            result = self.meta_labeler.predict(
                df=df,
                as_of=as_of,
                primary_side=side,
                primary_confidence=base.confidence,
                foreign_flow=ff_val,
            )

            return EnhancementSignal(
                source="meta",
                signal=result.bet_size,
                confidence_adjustment=1.0,
                rationale=f"P(correct)={result.probability:.3f}, bet={result.bet_size:.2f}, trade={result.trade}",
                available=True,
            )
        except Exception as e:
            logger.debug("Meta signal failed: %s", e)
            return EnhancementSignal(source="meta")
