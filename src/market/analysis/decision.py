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

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.14,
    "fundamental": 0.16,
    "macro": 0.08,
    "global": 0.08,
    "relationship": 0.06,
    "sentiment": 0.16,
    "holiday": 0.06,
    "prediction": 0.10,
    "alpha": 0.06,
    "policy_event": 0.04,
    "sector_rotation": 0.03,
    "seasonal": 0.02,
    "earnings": 0.01,
}

RECOMMENDATION_THRESHOLDS: dict[str, tuple[float, float]] = {
    "strong_buy": (80.0, 100.0),
    "buy": (65.0, 80.0),
    "hold": (45.0, 65.0),
    "reduce": (30.0, 45.0),
    "sell": (0.0, 30.0),
}

# Bahasa Indonesia labels for months
MONTH_NAMES_ID = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}

# Pattern type labels in Bahasa Indonesia
PATTERN_LABELS_ID = {
    "january_effect": "January Effect",
    "year_end_rally": "Year-End Rally",
    "strong_seasonal_bullish": "Seasonal Bullish Kuat",
    "strong_seasonal_bearish": "Seasonal Bearish Kuat",
    "earnings_season_q1": "Earnings Season Q1",
    "earnings_season_q2": "Earnings Season Q2",
    "aggregate_market": "Pola Market Aggregate",
    "neutral": "Netral",
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
    # Market driver context (causal, seasonal, commodity, DCC-GARCH, satellite)
    market_driver_context: list[str] = field(default_factory=list)
    # Current market regime (from market_regimes table, pustaka/23 §5)
    regime: str = ""


class DecisionEngine:
    """Decision engine combining factor scores into recommendation."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        db_url: str | None = None,
        include_driver_narrative: bool = True,
        use_db_weights: bool = True,
        use_regime_adjustment: bool = True,
    ) -> None:
        """Initialize decision engine.

        Args:
            weights: Factor weights dict. If None and use_db_weights=True,
                loads from signal_weights table via WeightRegistry.
            db_url: PostgreSQL connection URL for market driver narrative
                    and regime lookup. If None, both are disabled (graceful
                    degradation).
            include_driver_narrative: Whether to fetch market driver context
                    (causal, seasonal, commodity, DCC-GARCH, satellite) from DB.
            use_db_weights: Whether to load weights from DB (signal_weights table).
            use_regime_adjustment: Whether to adjust factor weights based on
                    current market regime from market_regimes table. Falls back
                    to SIDEWAYS if table is empty or db_url is None.

        Raises:
            WeightRegistryError: If use_db_weights=True and DB weights are unavailable.
        """
        if weights is not None:
            self.weights = weights
        elif use_db_weights:
            from market.analysis.weight_registry import WeightRegistry
            self.weights = WeightRegistry.get_weights("decision_engine")
        else:
            raise ValueError(
                "DecisionEngine requires either explicit weights or use_db_weights=True. "
                "No hardcoded fallback weights are available."
            )
        self.db_url = db_url
        self.include_driver_narrative = include_driver_narrative
        self.use_regime_adjustment = use_regime_adjustment

    def decide(
        self,
        ticker: str,
        technical: float | None = None,
        fundamental: float | None = None,
        macro: float | None = None,
        global_market: float | None = None,
        relationship: float | None = None,
        sentiment: float | None = None,
        holiday: float | None = None,
        prediction: float | None = None,
        alpha: float | None = None,
        policy_event: float | None = None,
        sector_rotation: float | None = None,
        seasonal: float | None = None,
        earnings: float | None = None,
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
            holiday: Holiday effect score (0-100).
            prediction: PredictionEngine output score (0-100).
                Derived from predicted direction + confidence + return%.
            alpha: Alpha signals composite score (0-100).
            policy_event: Policy/external event score (0-100).
            sector_rotation: Sector rotation momentum score (0-100).
            seasonal: Seasonal pattern score (0-100).
            earnings: Earnings calendar impact score (0-100).

        Returns:
            DecisionResult with composite score, recommendation,
            contribution breakdown, explanation, and market driver context.
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
        if holiday is not None:
            factor_scores["holiday"] = holiday
        if prediction is not None:
            factor_scores["prediction"] = prediction
        if alpha is not None:
            factor_scores["alpha"] = alpha
        if policy_event is not None:
            factor_scores["policy_event"] = policy_event
        if sector_rotation is not None:
            factor_scores["sector_rotation"] = sector_rotation
        if seasonal is not None:
            factor_scores["seasonal"] = seasonal
        if earnings is not None:
            factor_scores["earnings"] = earnings

        if not factor_scores:
            return DecisionResult(
                ticker=ticker,
                composite_score=0.0,
                recommendation="no_data",
                weights=self.weights,
                factor_scores={},
                contribution={},
                explanation=["No factor scores available."],
                regime="",
            )

        # Regime-aware weight adjustment (pustaka/23 §5)
        # Reads latest regime from market_regimes table; falls back to
        # sideways if table is empty or db_url is None.
        regime = ""
        effective_weights = self.weights
        if self.use_regime_adjustment:
            try:
                regime = self._get_current_regime()
                effective_weights = self._adjust_weights_for_regime(self.weights, regime)
            except Exception as e:
                logger.debug("Regime adjustment skipped: %s", e)
                regime = "sideways"
                effective_weights = self.weights

        # Renormalize weights for available factors
        total_weight = sum(
            effective_weights.get(f, 0) for f in factor_scores
        )
        if total_weight == 0:
            total_weight = 1.0

        composite = 0.0
        contribution: dict[str, float] = {}
        for factor, score in factor_scores.items():
            w = effective_weights.get(factor, 0) / total_weight
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

        # Add regime context to explanation
        if self.use_regime_adjustment and regime and regime != "sideways":
            explanation.append(
                f"Market regime: {regime.upper()} — weights adjusted accordingly.",
            )

        # Generate market driver context (causal, seasonal, commodity, etc.)
        market_driver_context: list[str] = []
        if self.include_driver_narrative and self.db_url:
            try:
                market_driver_context = self.generate_market_driver_narrative(ticker)
            except Exception as e:
                logger.warning("Market driver narrative failed for %s: %s", ticker, e)

        return DecisionResult(
            ticker=ticker,
            composite_score=round(composite, 2),
            recommendation=recommendation,
            weights=effective_weights,
            factor_scores=factor_scores,
            contribution=contribution,
            explanation=explanation,
            market_driver_context=market_driver_context,
            regime=regime,
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

    # ------------------------------------------------------------------
    # Market Driver Narrative — contextual explanation from DB
    # ------------------------------------------------------------------

    def _get_db_connection(self):
        """Get PostgreSQL connection (lazy import to avoid hard dependency)."""
        import psycopg2
        if not self.db_url:
            raise RuntimeError("db_url not configured")
        # Parse URL: postgresql://user:pass@host:port/dbname
        # or use as-is for psycopg2
        conn = psycopg2.connect(self.db_url)
        return conn

    # ------------------------------------------------------------------
    # Regime-aware weight adjustment (pustaka/23 §5, pustaka/35 §2)
    # ------------------------------------------------------------------

    _REGIME_STRING_MAP = {
        "bull": "bull",
        "bear": "bear",
        "sideways": "sideways",
        "crisis": "crisis",
        "recovery": "recovery",
    }

    def _get_current_regime(self) -> str:
        """Get current market regime from market_regimes table.

        Reads the latest regime label from the ``market_regimes`` table
        (populated by ``recompute_market_regimes``). Falls back to
        ``"sideways"`` if the table is empty, stale (>7 days), or db_url
        is not configured.

        Returns:
            Regime string: 'bull', 'bear', 'sideways', 'crisis', or 'recovery'.
        """
        if not self.db_url:
            return "sideways"

        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT regime, date FROM market_regimes
                ORDER BY date DESC LIMIT 1
            """)
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row and row[0]:
                regime_str = str(row[0]).lower().strip()
                # Validate against known regimes
                if regime_str in self._REGIME_STRING_MAP:
                    # Check freshness — skip if older than 7 days
                    if row[1] is not None:
                        from datetime import date as _date, timedelta as _td
                        regime_date = row[1]
                        if isinstance(regime_date, str):
                            regime_date = _date.fromisoformat(regime_date)
                        if isinstance(regime_date, _date):
                            if (_date.today() - regime_date) > _td(days=7):
                                logger.warning(
                                    "market_regimes table stale (latest=%s), "
                                    "using sideways fallback", regime_date,
                                )
                                return "sideways"
                    return self._REGIME_STRING_MAP[regime_str]
        except Exception as e:
            logger.debug("Regime lookup failed: %s", e)

        return "sideways"

    def _adjust_weights_for_regime(
        self, base_weights: dict[str, float], regime: str,
    ) -> dict[str, float]:
        """Adjust factor weights based on market regime.

        Uses ``RegimeWeightAdjuster`` from ``attribution.py`` to blend
        base weights with regime-specific weights. Factors not covered
        by regime weights retain their base weight.

        Args:
            base_weights: Original factor weights.
            regime: Regime string ('bull', 'bear', 'sideways', 'crisis', 'recovery').

        Returns:
            Adjusted and normalized weights dict.
        """
        from market.analysis.attribution import MarketRegime, RegimeWeightAdjuster

        regime_enum = {
            "bull": MarketRegime.BULL,
            "bear": MarketRegime.BEAR,
            "sideways": MarketRegime.SIDEWAYS,
            "crisis": MarketRegime.CRISIS,
            "recovery": MarketRegime.RECOVERY,
        }.get(regime, MarketRegime.SIDEWAYS)

        adjuster = RegimeWeightAdjuster()
        return adjuster.adjust_weights(base_weights, regime_enum)

    def generate_market_driver_narrative(self, ticker: str) -> list[str]:
        """Generate market driver context narrative for a ticker.

        Reads from database tables:
        - causal_relationships: Granger causality from global drivers
        - seasonal_patterns: Monthly seasonal score and patterns
        - commodity_to_stock_map: Commodity sensitivity mapping
        - dcc_garch_results: DCC-GARCH correlation with global indices
        - satellite_observations: Weather/NDVI context for commodity stocks

        Args:
            ticker: Stock ticker (e.g. 'INCO.JK').

        Returns:
            List of narrative strings in Bahasa Indonesia.
        """
        narratives: list[str] = []

        try:
            conn = self._get_db_connection()
        except Exception as e:
            logger.debug("DB connection failed for narrative: %s", e)
            return narratives

        try:
            narratives.extend(self._narrative_causal(conn, ticker))
            narratives.extend(self._narrative_seasonal(conn, ticker))
            narratives.extend(self._narrative_commodity(conn, ticker))
            narratives.extend(self._narrative_dcc_garch(conn, ticker))
            narratives.extend(self._narrative_satellite(conn, ticker))
            narratives.extend(self._narrative_holiday(conn))
        finally:
            conn.close()

        return narratives

    def _narrative_causal(self, conn, ticker: str) -> list[str]:
        """Narrative dari Granger causality — global drivers yang mempengaruhi ticker."""
        cur = conn.cursor()
        cur.execute("""
            SELECT cause_ticker, p_value, lag_days
            FROM causal_relationships
            WHERE effect_ticker = %s AND p_value < 0.05
            ORDER BY p_value ASC
            LIMIT 5
        """, (ticker,))
        rows = cur.fetchall()
        if not rows:
            return []

        narratives: list[str] = []
        narratives.append(
            f"📊 Causal Discovery — {len(rows)} global driver signifikan "
            f"Granger-cause {ticker}:"
        )
        for cause, p_val, lag in rows:
            strength = "sangat signifikan" if p_val < 0.01 else "signifikan"
            narratives.append(
                f"  • {cause} → {ticker}: p={p_val:.4f} ({strength}), "
                f"lag={lag} hari"
            )
        return narratives

    def _narrative_seasonal(self, conn, ticker: str) -> list[str]:
        """Narrative dari seasonal pattern — bulan terbaik/terburuk untuk ticker."""
        cur = conn.cursor()
        cur.execute("""
            SELECT month, avg_return, win_rate, seasonal_score, pattern_type, n_years
            FROM seasonal_patterns
            WHERE ticker = %s
            ORDER BY seasonal_score DESC
            LIMIT 3
        """, (ticker,))
        top = cur.fetchall()

        cur.execute("""
            SELECT month, avg_return, win_rate, seasonal_score, pattern_type, n_years
            FROM seasonal_patterns
            WHERE ticker = %s
            ORDER BY seasonal_score ASC
            LIMIT 2
        """, (ticker,))
        bottom = cur.fetchall()

        if not top:
            return []

        narratives: list[str] = []
        narratives.append(
            f"📅 Seasonal Pattern — berdasarkan {top[0][5]} tahun historis:"
        )
        for month, avg_ret, win_rate, score, ptype, n_years in top:
            month_name = MONTH_NAMES_ID.get(month, str(month))
            pattern_label = PATTERN_LABELS_ID.get(ptype, ptype)
            narratives.append(
                f"  • {month_name}: avg_return={avg_ret:+.2f}%, "
                f"win_rate={win_rate:.0f}%, score={score:.1f} ({pattern_label})"
            )
        if bottom:
            for month, avg_ret, win_rate, score, ptype, n_years in bottom:
                month_name = MONTH_NAMES_ID.get(month, str(month))
                if score < -10:
                    narratives.append(
                        f"  • {month_name}: avg_return={avg_ret:+.2f}% "
                        f"(seasonal bearish, score={score:.1f})"
                    )
        return narratives

    def _narrative_commodity(self, conn, ticker: str) -> list[str]:
        """Narrative dari commodity_to_stock_map — komoditas yang sensitif untuk ticker."""
        cur = conn.cursor()
        cur.execute("""
            SELECT commodity_series, sensitivity
            FROM commodity_to_stock_map
            WHERE ticker = %s
            ORDER BY sensitivity DESC
        """, (ticker,))
        rows = cur.fetchall()
        if not rows:
            return []

        narratives: list[str] = []
        narratives.append(
            f"🛢️ Komoditas Sensitivity — {len(rows)} komoditas mempengaruhi {ticker}:"
        )
        for commodity, sensitivity in rows:
            level = "tinggi" if sensitivity >= 0.75 else "sedang" if sensitivity >= 0.5 else "rendah"
            narratives.append(
                f"  • {commodity}: sensitivity={sensitivity:.2f} ({level})"
            )

        # Also fetch latest commodity price
        for commodity, _ in rows[:2]:
            cur.execute("""
                SELECT date, value FROM macro_data
                WHERE series_name = %s
                ORDER BY date DESC LIMIT 1
            """, (commodity,))
            price_row = cur.fetchone()
            if price_row:
                narratives.append(
                    f"  • {commodity} harga terakhir: {price_row[1]:.2f} "
                    f"({price_row[0]})"
                )
        return narratives

    def _narrative_dcc_garch(self, conn, ticker: str) -> list[str]:
        """Narrative dari DCC-GARCH — korelasi dinamis dengan global indices."""
        cur = conn.cursor()
        cur.execute("""
            SELECT pair, latest_corr, avg_corr, n_obs
            FROM dcc_garch_results
            WHERE pair LIKE %s
            ORDER BY ABS(latest_corr) DESC
            LIMIT 5
        """, (f"{ticker}_%",))
        rows = cur.fetchall()
        if not rows:
            return []

        narratives: list[str] = []
        narratives.append(
            f"🔗 DCC-GARCH — korelasi dinamis dengan global drivers:"
        )
        for pair, latest, avg, n_obs in rows:
            partner = pair.replace(f"{ticker}_", "", 1)
            direction = "positif" if latest >= 0 else "negatif"
            strength = "kuat" if abs(latest) >= 0.5 else "sedang" if abs(latest) >= 0.3 else "lemah"
            narratives.append(
                f"  • {partner}: korelasi {direction} {strength} "
                f"(latest={latest:+.3f}, avg={avg:+.3f}, n={n_obs})"
            )
        return narratives

    def _narrative_satellite(self, conn, ticker: str) -> list[str]:
        """Narrative dari satellite_observations — cuaca/NDVI untuk commodity stocks."""
        cur = conn.cursor()
        # Get locations for this ticker
        cur.execute("""
            SELECT location_name, sector
            FROM satellite_ticker_locations
            WHERE ticker = %s
        """, (ticker,))
        locations = cur.fetchall()
        if not locations:
            return []

        narratives: list[str] = []
        narratives.append(
            f"🛰️ Satelit & Cuaca — {len(locations)} lokasi pemantauan:"
        )
        for loc_name, sector in locations[:3]:
            # Get latest weather data for this location
            cur.execute("""
                SELECT metric, value, date
                FROM satellite_observations
                WHERE location_name = %s AND source = 'nasa_power'
                ORDER BY date DESC LIMIT 4
            """, (loc_name,))
            weather = cur.fetchall()
            if weather:
                weather_str = ", ".join(
                    f"{m}={v:.1f}" for m, v, _ in weather
                )
                narratives.append(
                    f"  • {loc_name} ({sector}): {weather_str}"
                )
        return narratives

    def _narrative_holiday(self, conn) -> list[str]:
        """Narrative dari holiday effect — pre/post holiday returns untuk IDX."""
        cur = conn.cursor()
        today = date.today()

        # Cek apakah hari ini atau besok adalah holiday IDX
        cur.execute("""
            SELECT holiday_date, holiday_name
            FROM exchange_holidays
            WHERE mic_code = 'XIDX'
              AND holiday_date BETWEEN %s AND %s
            ORDER BY holiday_date
        """, (today, today + timedelta(days=7)))
        upcoming = cur.fetchall()
        if not upcoming:
            return []

        narratives: list[str] = []
        narratives.append("📅 Holiday Effect — upcoming IDX holidays:")

        for h_date, h_name in upcoming[:3]:
            days_until = (h_date - today).days
            # Get pre/post holiday expected returns from analysis
            cur.execute("""
                SELECT pre_holiday_avg_return, post_holiday_avg_return,
                       pre_holiday_win_rate, post_holiday_win_rate,
                       is_significant, n_occurrences
                FROM holiday_effects
                WHERE mic_code = 'XIDX' AND holiday_name = %s
            """, (h_name,))
            row = cur.fetchone()
            if row:
                pre_ret, post_ret, pre_wr, post_wr, is_sig, n = row
                sig_label = "★ significant" if is_sig else ""
                if days_until == 0:
                    narratives.append(
                        f"  • {h_name} (HARI INI): "
                        f"post-historical avg={post_ret:+.2f}% "
                        f"(win rate {post_wr:.0f}%, n={n}) {sig_label}"
                    )
                elif days_until == 1:
                    narratives.append(
                        f"  • {h_name} (BESOK): "
                        f"pre-historical avg={pre_ret:+.2f}% "
                        f"(win rate {pre_wr:.0f}%, n={n}) {sig_label}"
                    )
                else:
                    narratives.append(
                        f"  • {h_name} ({days_until}h lagi): "
                        f"pre={pre_ret:+.2f}% post={post_ret:+.2f}% "
                        f"(n={n}) {sig_label}"
                    )
            else:
                if days_until == 0:
                    narratives.append(f"  • {h_name} (HARI INI)")
                elif days_until == 1:
                    narratives.append(f"  • {h_name} (BESOK)")
                else:
                    narratives.append(f"  • {h_name} ({days_until}h lagi)")

        # Cek spillover: apakah ada bursa global libur hari ini?
        cur.execute("""
            SELECT eh.mic_code, eh.holiday_name,
                   hs.idx_next_day_avg_return, hs.idx_next_day_win_rate,
                   hs.is_significant, hs.n_occurrences
            FROM exchange_holidays eh
            LEFT JOIN holiday_spillover hs
              ON hs.source_mic = eh.mic_code AND hs.source_holiday_name = eh.holiday_name
            WHERE eh.holiday_date = %s
              AND eh.mic_code != 'XIDX'
        """, (today,))
        spillovers = cur.fetchall()
        if spillovers:
            narratives.append("🌍 Spillover global → IDX (hari ini):")
            for mic, hname, idx_ret, idx_wr, is_sig, n in spillovers:
                if idx_ret is not None:
                    sig_label = "★ significant" if is_sig else ""
                    narratives.append(
                        f"  • {mic} {hname}: IDX expected {idx_ret:+.2f}% "
                        f"(win rate {idx_wr:.0f}%, n={n}) {sig_label}"
                    )

        return narratives

    def compute_holiday_score(self, ticker: str) -> float | None:
        """Compute holiday effect score (0-100) for a ticker.

        Uses holiday_effects + holiday_spillover tables to derive a score.
        Only applicable to IDX tickers (.JK).

        Score logic:
        - Base 50 (neutral)
        + pre_holiday_expected_return * 10 (if pre-holiday)
        + post_holiday_expected_return * 10 (if post-holiday)
        + spillover_expected_return * 10 (if global holiday today)
        - Clamped to [0, 100]

        Returns None if no holiday data available or not IDX ticker.
        """
        if not ticker.endswith(".JK"):
            return None

        try:
            from market.analysis.holiday_effect import HolidayEffectAnalyzer

            analyzer = HolidayEffectAnalyzer()
            features = analyzer.get_holiday_features("XIDX", date.today())
            spillover = analyzer.get_spillover_features(date.today())

            score = 50.0  # neutral base

            if features["is_pre_holiday"] and features["pre_holiday_expected_return"]:
                score += features["pre_holiday_expected_return"] * 10
            if features["is_post_holiday"] and features["post_holiday_expected_return"]:
                score += features["post_holiday_expected_return"] * 10
            if spillover.get("spillover_active_count", 0) > 0:
                score += spillover["spillover_total_expected_return"] * 10

            # If no holiday nearby at all, return None (no signal)
            if (not features["is_pre_holiday"]
                    and not features["is_post_holiday"]
                    and not features["is_holiday_today"]
                    and spillover.get("spillover_active_count", 0) == 0):
                return None

            return max(0.0, min(100.0, score))
        except Exception as e:
            logger.debug("Holiday score computation failed for %s: %s", ticker, e)
            return None

    @staticmethod
    def prediction_score_from_prediction(pred: object) -> float | None:
        """Convert PredictionEngine output to a 0-100 score for DecisionEngine.

        Args:
            pred: Prediction dataclass with predicted_direction, confidence,
                predicted_return_pct fields.

        Returns:
            Score 0-100, or None if prediction is not actionable.
        """
        try:
            direction = getattr(pred, "predicted_direction", "flat")
            confidence = getattr(pred, "confidence", 0.0)
            return_pct = getattr(pred, "predicted_return_pct", 0.0)

            if direction == "flat" or confidence < 0.1:
                return 50.0  # neutral

            # Base 50 + direction * confidence * return magnitude
            dir_val = 1.0 if direction == "up" else -1.0 if direction == "down" else 0.0
            score = 50.0 + dir_val * confidence * min(abs(return_pct), 10.0) * 5.0
            return max(0.0, min(100.0, score))
        except Exception:
            return None

    def compute_alpha_score(self, ticker: str) -> float | None:
        """Compute alpha signals score (0-100) from 4 alpha engines.

        Requires OHLCV data — delegates to MarketContextProvider if available.
        Returns None if no data available.
        """
        try:
            from sqlalchemy import text as sa_text

            conn = self._get_db_connection()
            cur = conn.cursor()
            # Check if we have recent OHLCV data for this ticker
            cur.execute("""
                SELECT close, high, low, volume, open, timestamp
                FROM stock_prices
                WHERE ticker = %s AND timeframe = '1d'
                ORDER BY timestamp DESC LIMIT 100
            """, (ticker,))
            rows = cur.fetchall()
            conn.close()

            if len(rows) < 50:
                return None

            import pandas as pd
            rows.reverse()
            df = pd.DataFrame(
                [(r[5], r[4], r[1], r[2], r[0], r[3]) for r in rows],
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df = df.set_index("timestamp")

            from market.analysis.alpha_signals import (
                EWMAMomentumEngine,
                MeanReversionEngine,
                RegimeSwitchEngine,
                ShortTermReversalEngine,
            )

            close = df["close"]

            signals = []
            for Engine in [MeanReversionEngine, ShortTermReversalEngine, EWMAMomentumEngine, RegimeSwitchEngine]:
                result = Engine().generate_signals(close)
                if len(result.signal):
                    signals.append(float(result.signal.iloc[-1]))

            if not signals:
                return None

            avg = sum(signals) / len(signals)
            # Convert [-1, 1] → [0, 100]
            return max(0.0, min(100.0, 50.0 + avg * 50.0))
        except Exception as e:
            logger.debug("Alpha score computation failed for %s: %s", ticker, e)
            return None

    def compute_policy_event_score(self, ticker: str) -> float | None:
        """Compute policy event score (0-100) from policy_events + external_events."""
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            today = date.today()

            cur.execute("""
                SELECT direction, impact_score
                FROM policy_events
                WHERE event_date >= %s
                ORDER BY event_date DESC LIMIT 20
            """, (today - timedelta(days=30),))
            policy_rows = cur.fetchall()

            cur.execute("""
                SELECT dampak_market
                FROM external_events
                WHERE tanggal >= %s
                ORDER BY tanggal DESC LIMIT 20
            """, (today - timedelta(days=30),))
            ext_rows = cur.fetchall()
            conn.close()

            total = len(policy_rows) + len(ext_rows)
            if total == 0:
                return None

            signal = 0.0
            for row in policy_rows:
                direction = float(row[0]) if row[0] else 0.0
                signal += direction
            for row in ext_rows:
                dampak = row[0] if row[0] else "Sedang"
                signal += {"Tinggi": 0.5, "Sedang": 0.0, "Rendah": -0.3}.get(dampak, 0.0)

            avg_signal = signal / max(total, 1)
            return max(0.0, min(100.0, 50.0 + avg_signal * 50.0))
        except Exception as e:
            logger.debug("Policy event score computation failed for %s: %s", ticker, e)
            return None

    def compute_seasonal_score(self, ticker: str) -> float | None:
        """Compute seasonal pattern score (0-100) from seasonal_patterns table."""
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            month = date.today().month

            cur.execute("""
                SELECT seasonal_score, pattern_type
                FROM seasonal_patterns
                WHERE ticker = %s AND month = %s
                ORDER BY seasonal_score DESC LIMIT 1
            """, (ticker, month))
            row = cur.fetchone()
            conn.close()

            if row and row[0] is not None:
                # seasonal_score is -1.0 to 1.0 → convert to 0-100
                return max(0.0, min(100.0, 50.0 + float(row[0]) * 50.0))
            return None
        except Exception as e:
            logger.debug("Seasonal score computation failed for %s: %s", ticker, e)
            return None

    def compute_earnings_score(self, ticker: str) -> float | None:
        """Compute earnings calendar impact score (0-100)."""
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            today = date.today()

            cur.execute("""
                SELECT earnings_date
                FROM earnings_calendar
                WHERE ticker = %s AND earnings_date >= %s
                ORDER BY earnings_date LIMIT 1
            """, (ticker, today))
            row = cur.fetchone()
            conn.close()

            if not row:
                return None

            report_date = row[0]
            days_to = (report_date - today).days if report_date else 999

            if days_to <= 0:
                # Post-earnings drift
                return 50.0
            elif days_to <= 5:
                # Pre-earnings uncertainty → slight bearish
                return 42.0  # below neutral
            elif days_to <= 30:
                return 48.0  # mild uncertainty
            return None
        except Exception as e:
            logger.debug("Earnings score computation failed for %s: %s", ticker, e)
            return None

    def fetch_scores_from_db(self, ticker: str) -> dict[str, float]:
        """Auto-fetch all available factor scores from DB for a ticker.

        Returns dict with any available scores: technical, fundamental, macro,
        global, relationship, sentiment, holiday, alpha, policy_event,
        seasonal, earnings.
        """
        scores: dict[str, float] = {}

        try:
            conn = self._get_db_connection()
            cur = conn.cursor()

            # 6 standard scores from scores table
            cur.execute("""
                SELECT engine, score
                FROM scores
                WHERE ticker = %s
                ORDER BY as_of DESC LIMIT 6
            """, (ticker,))
            for engine, score in cur.fetchall():
                if score is not None:
                    if engine == "global_market":
                        engine = "global"
                    scores[engine] = float(score)

            conn.close()
        except Exception as e:
            logger.debug("Score fetch failed for %s: %s", ticker, e)

        # Holiday score
        holiday = self.compute_holiday_score(ticker)
        if holiday is not None:
            scores["holiday"] = holiday

        # Alpha score
        alpha = self.compute_alpha_score(ticker)
        if alpha is not None:
            scores["alpha"] = alpha

        # Policy event score
        policy = self.compute_policy_event_score(ticker)
        if policy is not None:
            scores["policy_event"] = policy

        # Seasonal score
        seasonal = self.compute_seasonal_score(ticker)
        if seasonal is not None:
            scores["seasonal"] = seasonal

        # Earnings score
        earnings = self.compute_earnings_score(ticker)
        if earnings is not None:
            scores["earnings"] = earnings

        return scores

    def decide_with_db(self, ticker: str, prediction: object | None = None) -> DecisionResult:
        """Full auto-decision: fetch all scores from DB + prediction → decide.

        This is the bridge method that connects PredictionEngine output
        to DecisionEngine without manual parameter passing.

        Args:
            ticker: Stock ticker (e.g. 'BBCA.JK').
            prediction: Optional Prediction dataclass from PredictionEngine.

        Returns:
            DecisionResult with all available factor scores.
        """
        scores = self.fetch_scores_from_db(ticker)

        # Add prediction score if provided
        if prediction is not None:
            pred_score = self.prediction_score_from_prediction(prediction)
            if pred_score is not None:
                scores["prediction"] = pred_score

        return self.decide(ticker=ticker, **scores)
