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
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

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


class DecisionEngine:
    """Decision engine combining factor scores into recommendation."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        db_url: str | None = None,
        include_driver_narrative: bool = True,
    ) -> None:
        """Initialize decision engine.

        Args:
            weights: Factor weights dict. Uses DEFAULT_WEIGHTS if None.
            db_url: PostgreSQL connection URL for market driver narrative.
                    If None, narrative features are disabled (graceful degradation).
            include_driver_narrative: Whether to fetch market driver context
                    (causal, seasonal, commodity, DCC-GARCH, satellite) from DB.
        """
        self.weights = weights or DEFAULT_WEIGHTS
        self.db_url = db_url
        self.include_driver_narrative = include_driver_narrative

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
            weights=self.weights,
            factor_scores=factor_scores,
            contribution=contribution,
            explanation=explanation,
            market_driver_context=market_driver_context,
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
