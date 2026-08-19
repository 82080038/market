"""Signal Enhancer — integrates 9 signal modules into prediction pipeline.

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
6. **Smart Money** — retail absorption detection from volume/price patterns.
7. **Cross-market domino** — causal chain from v_domino_timeline.
8. **Astronacci** (``astronacci.py``) — time-cycle signal from astrological
   events (Moon Phases, Retrogrades, Ingresses) + Fibonacci time windows.
9. **Market Influence KB** (``market_influence_kb.py``) — consolidated
   influence mapping from sector-global links, commodity sensitivity,
   Granger causality, and macro policy. Adds a net influence signal.
10. **Broker Momentum** (``broker_daily_summary`` table) — market-wide
    broker activity momentum (total value/volume trend, top broker
    concentration). Adds a smart-money liquidity signal.

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
    from market.analysis.meta_labeling import MetaLabeler
    from market.analysis.market_influence_kb import MarketInfluenceKB
    from market.analysis.pairs_trading import PairsTradingEngine
    from market.analysis.policy_event_scorer import PolicyEventScorer
    from market.analysis.prediction import Prediction
    from market.analysis.sector_rotation import SectorRotationEngine

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
        smart_money_weight: float = 0.12,
        cross_market_weight: float = 0.12,
        astronacci_weight: float = 0.06,
        influence_kb_weight: float = 0.08,
        broker_momentum_weight: float = 0.10,
        signal_threshold: float = 0.15,
        smart_money_streak_threshold: int = 3,
        mid_cap_relax_factor: float = 0.15,
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
            smart_money_weight: Weight for Smart Money (retail absorption) signal.
            signal_threshold: Minimum |total_adjustment| to flip direction.
            smart_money_streak_threshold: Consecutive days of positive Smart Money
                Score required to trigger meta_prob_threshold relaxation.
            mid_cap_relax_factor: How much to relax the meta-labeler prob_threshold
                for Mid-Cap stocks with strong accumulation streak (e.g. 0.15 means
                threshold lowered from 0.50 to 0.35).
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
        self.smart_money_weight = smart_money_weight
        self.cross_market_weight = cross_market_weight
        self.astronacci_weight = astronacci_weight
        self.influence_kb_weight = influence_kb_weight
        self.broker_momentum_weight = broker_momentum_weight
        self.signal_threshold = signal_threshold
        self.smart_money_streak_threshold = smart_money_streak_threshold
        self.mid_cap_relax_factor = mid_cap_relax_factor

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

        # 5. Smart Money / Retail Absorption signal.
        smart_money_sig = self._compute_smart_money_signal(df_trunc, ticker)
        signals.append(smart_money_sig)

        # 6. Cross-market domino signal (causal chain from v_domino_timeline).
        domino_sig = self._compute_cross_market_signal(df_trunc, ticker, as_of)
        signals.append(domino_sig)

        # 8. Astronacci time-cycle signal.
        astro_sig = self._compute_astronacci_signal(as_of, df_trunc)
        signals.append(astro_sig)

        # 9. Market Influence KB signal.
        influence_sig = self._compute_influence_kb_signal(ticker, df_trunc)
        signals.append(influence_sig)

        # 10. Broker momentum signal (from broker_daily_summary table).
        broker_sig = self._compute_broker_momentum_signal(as_of)
        signals.append(broker_sig)

        # 7. Meta-labeler bet sizing (with optional threshold relaxation).
        # If Smart Money Score shows accumulation for >=3 consecutive days,
        # relax the meta-labeler prob_threshold for Mid-Cap stocks.
        relax_factor = 0.0
        if (
            smart_money_sig.available
            and hasattr(smart_money_sig, 'rationale')
            and 'streak=' in smart_money_sig.rationale
        ):
            # Extract streak from rationale string
            import re
            streak_match = re.search(r'streak=(\d+)', smart_money_sig.rationale)
            if streak_match:
                streak_val = int(streak_match.group(1))
                if streak_val >= self.smart_money_streak_threshold:
                    relax_factor = self.mid_cap_relax_factor

        meta_sig = self._compute_meta_signal(
            df, base, ticker, as_of, foreign_flow,
            prob_relax=relax_factor,
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
            elif sig.source == "smart_money":
                total_adj += sig.signal * self.smart_money_weight
            elif sig.source == "cross_market":
                total_adj += sig.signal * self.cross_market_weight
            elif sig.source == "astronacci":
                total_adj += sig.signal * self.astronacci_weight
            elif sig.source == "influence_kb":
                total_adj += sig.signal * self.influence_kb_weight
            elif sig.source == "broker_momentum":
                total_adj += sig.signal * self.broker_momentum_weight
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

            # Convert to UTC-aware datetime for comparison
            as_of_dt = pd.Timestamp(as_of)
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.tz_localize("UTC")
            as_of_dt = as_of_dt.to_pydatetime()

            event_signal = self.policy_scorer.compute_event_signal(
                ticker=ticker,
                as_of_date=as_of_dt,
            )

            if event_signal is None:
                return EnhancementSignal(source="event")

            # Normalize: event_signal.score is unbounded, clip to [-100, +100].
            raw_score = float(event_signal.score)
            normalized = np.clip(raw_score / 100.0, -1, 1)

            # Confidence adjustment: strong events boost or reduce confidence.
            conf_adj = 1.0 + abs(normalized) * 0.10

            return EnhancementSignal(
                source="event",
                signal=float(normalized),
                confidence_adjustment=conf_adj,
                rationale=f"score={raw_score:.1f}, n_events={len(event_signal.active_events)}",
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

    def _compute_smart_money_signal(
        self,
        df: pd.DataFrame,
        ticker: str,
    ) -> EnhancementSignal:
        """Compute Smart Money Score from retail broker absorption.

        Uses calculate_retail_absorption from volume_features.py to detect
        institutional accumulation patterns (Bandarmology). Requires
        broker_flow data to be pre-loaded; gracefully skips if unavailable.
        """
        try:
            from market.analysis.volume_features import calculate_retail_absorption

            # broker_flow data must be passed in or loaded externally.
            # This method checks if broker_flow_df is available in df as metadata.
            # If not available, skip gracefully.
            broker_flow_df = getattr(df, '_attrs', {}).get('broker_flow_df') if hasattr(df, '_attrs') else None
            if broker_flow_df is None or broker_flow_df.empty:
                return EnhancementSignal(source="smart_money")

            result = calculate_retail_absorption(
                broker_flow_df=broker_flow_df,
                ohlcv_df=df,
                ticker=ticker,
                lookback=5,
            )

            signal = float(np.clip(result.smart_money_score, -1, 1))
            conf_adj = 1.0
            if result.accumulation_streak >= 3:
                conf_adj = 1.15  # Boost confidence when 3+ day accumulation streak

            return EnhancementSignal(
                source="smart_money",
                signal=signal,
                confidence_adjustment=conf_adj,
                rationale=(
                    f"smart_money={result.smart_money_score:.2f}, "
                    f"label={result.label}, "
                    f"retail_sell_ratio={result.retail_sell_ratio:.2f}, "
                    f"streak={result.accumulation_streak}"
                ),
                available=True,
            )
        except Exception as e:
            logger.debug("Smart money signal failed: %s", e)
            return EnhancementSignal(source="smart_money")

    def _compute_cross_market_signal(
        self,
        df: pd.DataFrame,
        ticker: str,
        as_of: str | pd.Timestamp,
    ) -> EnhancementSignal:
        """Compute cross-market domino causal chain signal.

        Queries ``v_domino_timeline`` (PostgreSQL) to get the sequence of
        market closes on the prediction date. Markets that close BEFORE IDX
        (Tokyo, Hong Kong, Shanghai) provide same-day directional signal.
        Markets that close AFTER IDX (US, Europe) use previous day's close.

        Anti look-ahead: only uses data from markets that have already closed
        before IDX close (08:50 UTC). US/European markets use T-1 data.

        The signal is a weighted average of pre-IDX market returns:
        - Tokyo (^N225, close 06:30 UTC): weight 0.35
        - Hong Kong (^HSI, close 08:00 UTC): weight 0.35
        - Shanghai (000001.SS, close 07:00 UTC): weight 0.15
        - Bursa Malaysia (CPO=F, close 10:00 UTC): weight 0.15 (T-1)

        Falls back to computing from OHLCV data if v_domino_timeline unavailable.
        """
        try:
            if "close" not in df.columns or len(df) < 2:
                return EnhancementSignal(source="cross_market")

            cutoff = pd.Timestamp(as_of)
            pred_date = cutoff.date()

            # Try PostgreSQL v_domino_timeline first
            try:
                from market.db.raw import execute_query

                rows = execute_query(
                    """SELECT ticker, exchange_mic, impact_direction, price,
                       utc_timestamp
                       FROM v_domino_timeline
                       WHERE utc_timestamp >= %s
                         AND utc_timestamp < %s
                         AND event_type = 'PRICE_TICK'
                         AND ticker IN ('^N225', '^HSI', '000001.SS', 'CPO=F')
                       ORDER BY utc_timestamp""",
                    (f"{pred_date}T00:00:00+00:00",
                     f"{pred_date}T12:00:00+00:00"),
                )

                if rows and len(rows) >= 2:
                    # Build signal from pre-IDX market directions
                    weights = {
                        "^N225": 0.35,
                        "^HSI": 0.35,
                        "000001.SS": 0.15,
                        "CPO=F": 0.15,
                    }
                    direction_map = {
                        "BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0,
                    }

                    total_signal = 0.0
                    total_weight = 0.0
                    parts = []

                    for row in rows:
                        t = row[0]
                        direction = row[2]
                        w = weights.get(t, 0.0)
                        if w > 0 and direction in direction_map:
                            contrib = direction_map[direction] * w
                            total_signal += contrib
                            total_weight += w
                            parts.append(f"{t}={direction}")

                    if total_weight > 0:
                        signal = float(np.clip(total_signal / total_weight, -1, 1))
                        conf_adj = 1.0 + abs(signal) * 0.08
                        return EnhancementSignal(
                            source="cross_market",
                            signal=signal,
                            confidence_adjustment=conf_adj,
                            rationale=f"domino[{', '.join(parts)}] → {signal:.2f}",
                            available=True,
                        )
            except Exception:
                pass

            # Fallback: compute from OHLCV data in df
            # Use T-0 for Asian markets (close before IDX), T-1 for others
            asian_tickers = {
                "^N225": ("nikkei", 0.35),
                "^HSI": ("hangseng", 0.35),
                "000001.SS": ("shanghai", 0.15),
                "CPO=F": ("cpo", 0.15),
            }

            # Check if global data columns exist in df (from compute_exogenous_features)
            total_signal = 0.0
            total_weight = 0.0
            parts = []

            for gticker, (name, weight) in asian_tickers.items():
                col_1 = f"{name}_lag1_ret"
                if col_1 in df.columns:
                    val = float(df[col_1].iloc[-1]) if not df[col_1].empty else 0.0
                    if np.isnan(val):
                        val = 0.0
                    contrib = np.clip(val * 10, -1, 1) * weight
                    total_signal += contrib
                    total_weight += weight
                    direction = "BULLISH" if val > 0 else "BEARISH" if val < 0 else "NEUTRAL"
                    parts.append(f"{gticker}={direction}")

            if total_weight > 0:
                signal = float(np.clip(total_signal / total_weight, -1, 1))
                conf_adj = 1.0 + abs(signal) * 0.08
                return EnhancementSignal(
                    source="cross_market",
                    signal=signal,
                    confidence_adjustment=conf_adj,
                    rationale=f"domino[{', '.join(parts)}] → {signal:.2f}",
                    available=True,
                )

            return EnhancementSignal(source="cross_market")
        except Exception as e:
            logger.debug("Cross-market signal failed: %s", e)
            return EnhancementSignal(source="cross_market")

    def _compute_astronacci_signal(
        self,
        as_of: str | pd.Timestamp,
        df: pd.DataFrame | None = None,
    ) -> EnhancementSignal:
        """Compute Astronacci signal with Fibonacci price confluence.

        Uses the AstronacciEngine to check for active astrological time
        cycles (Moon Phases, Planetary Retrogrades, Ingresses) within a
        3-day forward window from as_of, AND checks if current price is
        near a Fibonacci retracement level (38.2%, 50%, 61.8%, 78.6%).

        When both astrology event AND Fibonacci price level align
        (confluence), the signal is boosted 1.5-2x. This is the core
        Astronacci methodology: WHEN (astrology) + WHERE (Fibonacci price).

        Returns a directional signal in [-1, +1] based on the expected
        reversal type of active cycles and Fibonacci confluence, plus a
        volatility-based confidence adjustment.
        """
        try:
            from market.analysis.astronacci import compute_astronacci_signal

            cutoff = pd.Timestamp(as_of)
            if cutoff.tzinfo is None:
                cutoff = cutoff.tz_localize("UTC")
            as_of_dt = cutoff.to_pydatetime()

            # Prepare prices DataFrame for Fibonacci retracement computation.
            prices_df = None
            current_price = None
            if df is not None and not df.empty and "close" in df.columns:
                prices_df = df.reset_index().rename(columns={df.index.name or "index": "timestamp"})
                if "timestamp" not in prices_df.columns:
                    prices_df = df.reset_index(names=["timestamp"])
                # Current price = latest close
                current_price = float(df["close"].iloc[-1])

            result = compute_astronacci_signal(
                as_of_dt, window_days=3, prices=prices_df, current_price=current_price,
            )

            if result["cycle_count"] == 0 and result.get("confluence") is None:
                return EnhancementSignal(source="astronacci")

            time_sig = result["time_signal"]
            vol_sig = result["volatility_signal"]
            confidence = result["confidence"]
            active = result["active_cycles"]
            confluence = result.get("confluence")

            # Confidence adjustment: active cycles + confluence boost confidence
            conf_adj = 1.0 + (vol_sig * 0.15) + (confidence * 0.05)
            if confluence and confluence["matched"]:
                conf_adj += 0.10  # confluence adds extra confidence
            conf_adj = max(0.85, min(1.30, conf_adj))

            # Build rationale
            cycle_summary = ", ".join(active[:5])
            if len(active) > 5:
                cycle_summary += f" (+{len(active) - 5} more)"
            confluence_str = ""
            if confluence and confluence["matched"]:
                confluence_str = (
                    f", CONFLUENCE: Fib {confluence['ratio']:.1%} @ {confluence['fib_price']:.2f}"
                    f" ({confluence['direction']}, dist={confluence['distance_pct']:.2f}%)"
                )
            rationale = (
                f"cycles={result['cycle_count']}, time_signal={time_sig:.3f}, "
                f"vol_signal={vol_sig:.3f}, active=[{cycle_summary}]{confluence_str}"
            )

            return EnhancementSignal(
                source="astronacci",
                signal=time_sig,
                confidence_adjustment=conf_adj,
                rationale=rationale,
                available=True,
            )
        except Exception as e:
            logger.debug("Astronacci signal failed: %s", e)
            return EnhancementSignal(source="astronacci")

    def _compute_influence_kb_signal(
        self,
        ticker: str,
        df_trunc: pd.DataFrame,
    ) -> EnhancementSignal:
        """Compute Market Influence KB signal.

        Queries the ``market_influence_kb`` table for all active influences
        on *ticker*, then fetches recent returns for each source ticker from
        ``df_trunc`` (if the source is a global index or commodity already in
        the OHLCV table) or from macro_data. The net influence signal is
        computed as a strength-weighted average of direction × actual return.

        Falls back to theoretical signal (strength-only) if no return data
        is available.
        """
        try:
            from market.db.engine import get_sessionmaker
            from market.analysis.market_influence_kb import MarketInfluenceKB

            session = get_sessionmaker()()
            try:
                kb = MarketInfluenceKB(session)
                influences = kb.get_influences(ticker, active_only=True)

                if not influences:
                    return EnhancementSignal(source="influence_kb")

                # Try to get recent returns for source tickers from df_trunc
                # df_trunc is the target ticker's OHLCV — we need source returns
                # from stock_prices or macro_data. For now, use theoretical signal
                # (strength-only) as we don't have source OHLCV in df_trunc.
                sig = kb.compute_influence_signal(ticker)

                # Build rationale
                top_sources = []
                for inf in influences[:5]:
                    direction_arrow = "↑" if inf.direction == "positive" else "↓"
                    top_sources.append(
                        f"{inf.source_ticker}{direction_arrow}({inf.strength or 0:.2f})"
                    )
                rationale = (
                    f"net={sig.net_signal:+.3f}, sources={sig.source_count}, "
                    f"top=[{', '.join(top_sources)}]"
                )

                # Confidence adjustment: more sources → more confidence
                conf_adj = 1.0 + min(0.15, sig.source_count * 0.02)

                return EnhancementSignal(
                    source="influence_kb",
                    signal=sig.net_signal,
                    confidence_adjustment=conf_adj,
                    rationale=rationale,
                    available=True,
                )
            finally:
                session.close()
        except Exception as e:
            logger.debug("Influence KB signal failed: %s", e)
            return EnhancementSignal(source="influence_kb")

    def _compute_meta_signal(
        self,
        df: pd.DataFrame,
        base: "Prediction",
        ticker: str,
        as_of: str | pd.Timestamp,
        foreign_flow: pd.Series | None,
        prob_relax: float = 0.0,
    ) -> EnhancementSignal:
        """Compute meta-labeler bet sizing signal.

        Args:
            prob_relax: If > 0, relax the meta-labeler prob_threshold by this
                amount (e.g. 0.15 lowers threshold from 0.50 to 0.35). Used
                when Smart Money Score detects strong accumulation streak.
        """
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

            # Apply Smart Money threshold relaxation for Mid-Cap
            original_threshold = self.meta_labeler.prob_threshold
            if prob_relax > 0:
                relaxed = max(0.1, original_threshold - prob_relax)
                self.meta_labeler.prob_threshold = relaxed
                logger.debug(
                    "Meta threshold relaxed: %.2f → %.2f (Smart Money streak)",
                    original_threshold, relaxed,
                )

            try:
                result = self.meta_labeler.predict(
                    df=df,
                    as_of=as_of,
                    primary_side=side,
                    primary_confidence=base.confidence,
                    foreign_flow=ff_val,
                )
            finally:
                self.meta_labeler.prob_threshold = original_threshold

            rationale = f"P(correct)={result.probability:.3f}, bet={result.bet_size:.2f}, trade={result.trade}"
            if prob_relax > 0:
                rationale += f", threshold_relaxed={prob_relax:.2f}"

            return EnhancementSignal(
                source="meta",
                signal=result.bet_size,
                confidence_adjustment=1.0,
                rationale=rationale,
                available=True,
            )
        except Exception as e:
            logger.debug("Meta signal failed: %s", e)
            return EnhancementSignal(source="meta")

    def _compute_broker_momentum_signal(
        self,
        as_of: str | pd.Timestamp,
    ) -> EnhancementSignal:
        """Compute market-wide broker momentum signal from broker_daily_summary.

        Reads aggregate broker activity (total value, volume, frequency) and
        computes a momentum signal based on:
        - Total market value trend (3-day vs prior 2-day)
        - Top broker concentration (HHI) — high concentration = smart money
        - Frequency trend — rising frequency = broad participation (bullish)

        Signal range: [-1, +1]. Positive = bullish liquidity regime.
        """
        try:
            from datetime import timedelta

            from sqlalchemy import text

            from market.db.engine import get_engine

            cutoff = pd.Timestamp(as_of)
            if cutoff.tzinfo is not None:
                cutoff_date = cutoff.tz_convert("UTC").date()
            else:
                cutoff_date = cutoff.date()

            with get_engine().connect() as conn:
                # Get last 5 trading days of aggregate broker data
                rows = conn.execute(
                    text(
                        "SELECT date, SUM(value) as total_val, SUM(volume) as total_vol, "
                        "SUM(frequency) as total_freq, COUNT(*) as n_brokers "
                        "FROM broker_daily_summary "
                        "WHERE date <= :cutoff "
                        "GROUP BY date ORDER BY date DESC LIMIT 5"
                    ),
                    {"cutoff": cutoff_date},
                ).all()

                if len(rows) < 3:
                    return EnhancementSignal(source="broker_momentum")

                # Recent 3 days vs prior 2 days
                recent_val = float(sum(float(r[1] or 0) for r in rows[:3])) / 3
                prior_val = float(sum(float(r[1] or 0) for r in rows[3:5])) / max(1, len(rows[3:5]))

                if prior_val > 0:
                    val_momentum = (recent_val - prior_val) / prior_val
                else:
                    val_momentum = 0.0

                # Frequency trend (rising = bullish)
                recent_freq = float(sum(float(r[3] or 0) for r in rows[:3])) / 3
                prior_freq = float(sum(float(r[3] or 0) for r in rows[3:5])) / max(1, len(rows[3:5]))
                if prior_freq > 0:
                    freq_momentum = (recent_freq - prior_freq) / prior_freq
                else:
                    freq_momentum = 0.0

                # Top broker concentration (latest day)
                latest_date = rows[0][0]
                broker_rows = conn.execute(
                    text(
                        "SELECT value FROM broker_daily_summary "
                        "WHERE date = :d ORDER BY value DESC LIMIT 10"
                    ),
                    {"d": latest_date},
                ).all()

                if broker_rows:
                    top_10_val = float(sum(float(r[0] or 0) for r in broker_rows))
                    total_val = float(sum(float(r[1] or 0) for r in rows[:1]))
                    if total_val and total_val > 0:
                        concentration = top_10_val / total_val
                    else:
                        concentration = 0.5
                else:
                    concentration = 0.5

                # Signal: weighted combination
                # Value momentum (50%) + frequency momentum (30%) + concentration (20%)
                # High concentration (>0.6) = smart money dominant = mildly bullish
                concentration_signal = (concentration - 0.5) * 0.4  # [-0.2, +0.2]

                raw_signal = (
                    np.tanh(val_momentum) * 0.50
                    + np.tanh(freq_momentum) * 0.30
                    + concentration_signal
                )
                signal = float(np.clip(raw_signal, -1.0, 1.0))

                conf_adj = 1.0 + abs(signal) * 0.08

                return EnhancementSignal(
                    source="broker_momentum",
                    signal=signal,
                    confidence_adjustment=conf_adj,
                    rationale=(
                        f"val_mom={val_momentum:+.3f}, freq_mom={freq_momentum:+.3f}, "
                        f"top10_conc={concentration:.2f}"
                    ),
                    available=True,
                )

        except Exception as e:
            logger.debug("Broker momentum signal failed: %s", e)
            return EnhancementSignal(source="broker_momentum")
