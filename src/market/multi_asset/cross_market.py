"""Cross-market relationship engine (pustaka/35, pustaka/92 §4.4).

Extends the existing MarketRelationshipEngine to support:
- Cross-market correlation (IDX vs US, HK, JP, etc.)
- Lead-lag analysis across markets with timezone alignment
- Spillover detection (volatility transmission)
- Heatmap data generation for UI
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class CrossMarketCorrelation:
    """Correlation between two markets."""

    market_a: str
    market_b: str
    correlation: float
    p_value: float
    sample_size: int


@dataclass
class LeadLagResult:
    """Lead-lag analysis result between two markets."""

    leader: str
    follower: str
    optimal_lag: int
    correlation_at_lag: float
    significance: float


@dataclass
class SpilloverResult:
    """Volatility spillover from one market to another."""

    source: str
    target: str
    spillover_pct: float
    direction: str  # "unidirectional" or "bidirectional"


@dataclass
class CrossMarketReport:
    """Full cross-market analysis report."""

    correlations: list[CrossMarketCorrelation] = field(default_factory=list)
    lead_lag: list[LeadLagResult] = field(default_factory=list)
    spillovers: list[SpilloverResult] = field(default_factory=list)
    heatmap_data: dict[str, dict[str, float]] = field(default_factory=dict)


class CrossMarketEngine:
    """Cross-market relationship engine."""

    def __init__(self, min_samples: int = 30) -> None:
        self.min_samples = min_samples

    def compute_correlation(
        self,
        returns_a: pd.Series,
        returns_b: pd.Series,
        market_a: str,
        market_b: str,
    ) -> CrossMarketCorrelation | None:
        """Compute correlation between two market return series.

        Args:
            returns_a: Returns for market A.
            returns_b: Returns for market B.
            market_a: Market A name.
            market_b: Market B name.

        Returns:
            CrossMarketCorrelation or None if insufficient data.
        """
        aligned = pd.concat([returns_a, returns_b], axis=1).dropna()
        if len(aligned) < self.min_samples:
            return None

        corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

        # Simple p-value approximation
        n = len(aligned)
        t_stat = corr * np.sqrt(n - 2) / np.sqrt(1 - corr**2) if abs(corr) < 1 else 0
        p_value = float(2 * (1 - 0.5 * (1 + np.tanh(abs(t_stat) / np.sqrt(2)))))

        return CrossMarketCorrelation(
            market_a=market_a,
            market_b=market_b,
            correlation=round(corr, 4),
            p_value=round(p_value, 4),
            sample_size=n,
        )

    def compute_lead_lag(
        self,
        returns_a: pd.Series,
        returns_b: pd.Series,
        market_a: str,
        market_b: str,
        max_lag: int = 10,
    ) -> LeadLagResult | None:
        """Find optimal lead-lag between two market return series.

        Args:
            returns_a: Returns for potential leader.
            returns_b: Returns for potential follower.
            market_a: Market A name.
            market_b: Market B name.
            max_lag: Maximum lag to test (days).

        Returns:
            LeadLagResult or None if insufficient data.
        """
        aligned = pd.concat([returns_a, returns_b], axis=1).dropna()
        if len(aligned) < self.min_samples + max_lag:
            return None

        best_corr = 0.0
        best_lag = 0

        for lag in range(0, max_lag + 1):
            shifted_a = aligned.iloc[:, 0].shift(lag)
            combined = pd.concat([shifted_a, aligned.iloc[:, 1]], axis=1).dropna()
            if len(combined) < self.min_samples:
                continue
            c = float(combined.iloc[:, 0].corr(combined.iloc[:, 1]))
            if abs(c) > abs(best_corr):
                best_corr = c
                best_lag = lag

        significance = abs(best_corr) * np.sqrt(len(aligned) - 2)

        return LeadLagResult(
            leader=market_a if best_lag > 0 else market_b,
            follower=market_b if best_lag > 0 else market_a,
            optimal_lag=best_lag,
            correlation_at_lag=round(best_corr, 4),
            significance=round(float(significance), 4),
        )

    def compute_spillover(
        self,
        vol_a: pd.Series,
        vol_b: pd.Series,
        market_a: str,
        market_b: str,
    ) -> SpilloverResult | None:
        """Detect volatility spillover between markets.

        Uses Granger-causality-like approach: does lagged volatility
        of A predict current volatility of B?

        Args:
            vol_a: Volatility series for market A.
            vol_b: Volatility series for market B.
            market_a: Source market.
            market_b: Target market.

        Returns:
            SpilloverResult or None if insufficient data.
        """
        aligned = pd.concat([vol_a, vol_b], axis=1).dropna()
        if len(aligned) < self.min_samples + 5:
            return None

        # A→B spillover
        lagged_a = aligned.iloc[:, 0].shift(1)
        combined_ab = pd.concat([lagged_a, aligned.iloc[:, 1]], axis=1).dropna()
        corr_ab = float(combined_ab.iloc[:, 0].corr(combined_ab.iloc[:, 1]))

        # B→A spillover
        lagged_b = aligned.iloc[:, 1].shift(1)
        combined_ba = pd.concat([lagged_b, aligned.iloc[:, 0]], axis=1).dropna()
        corr_ba = float(combined_ba.iloc[:, 0].corr(combined_ba.iloc[:, 1]))

        # Determine direction
        threshold = 0.1
        ab_significant = abs(corr_ab) > threshold
        ba_significant = abs(corr_ba) > threshold

        if ab_significant and ba_significant:
            direction = "bidirectional"
            spillover = (abs(corr_ab) + abs(corr_ba)) / 2 * 100
        elif ab_significant:
            direction = "unidirectional"
            spillover = abs(corr_ab) * 100
        elif ba_significant:
            direction = "unidirectional"
            # Swap source/target
            market_a, market_b = market_b, market_a
            spillover = abs(corr_ba) * 100
        else:
            return None

        return SpilloverResult(
            source=market_a,
            target=market_b,
            spillover_pct=round(spillover, 2),
            direction=direction,
        )

    def generate_heatmap(
        self,
        returns: dict[str, pd.Series],
    ) -> dict[str, dict[str, float]]:
        """Generate correlation heatmap data for all market pairs.

        Args:
            returns: Dict mapping market name to returns series.

        Returns:
            Nested dict: {market_a: {market_b: correlation}}.
        """
        markets = list(returns.keys())
        heatmap: dict[str, dict[str, float]] = {}

        for m_a in markets:
            heatmap[m_a] = {}
            for m_b in markets:
                if m_a == m_b:
                    heatmap[m_a][m_b] = 1.0
                    continue
                result = self.compute_correlation(
                    returns[m_a], returns[m_b], m_a, m_b,
                )
                heatmap[m_a][m_b] = result.correlation if result else 0.0

        return heatmap

    def analyze(
        self,
        returns: dict[str, pd.Series],
        volatilities: dict[str, pd.Series] | None = None,
        max_lag: int = 10,
    ) -> CrossMarketReport:
        """Full cross-market analysis.

        Args:
            returns: Dict mapping market name to returns series.
            volatilities: Optional dict mapping market name to volatility series.
            max_lag: Maximum lag for lead-lag analysis.

        Returns:
            CrossMarketReport with all analyses.
        """
        markets = list(returns.keys())
        correlations: list[CrossMarketCorrelation] = []
        lead_lag: list[LeadLagResult] = []

        for i, m_a in enumerate(markets):
            for m_b in markets[i + 1 :]:
                corr = self.compute_correlation(
                    returns[m_a], returns[m_b], m_a, m_b,
                )
                if corr:
                    correlations.append(corr)

                ll = self.compute_lead_lag(
                    returns[m_a], returns[m_b], m_a, m_b, max_lag,
                )
                if ll:
                    lead_lag.append(ll)

        spillovers: list[SpilloverResult] = []
        if volatilities:
            for i, m_a in enumerate(markets):
                for m_b in markets[i + 1 :]:
                    if m_a in volatilities and m_b in volatilities:
                        sp = self.compute_spillover(
                            volatilities[m_a], volatilities[m_b], m_a, m_b,
                        )
                        if sp:
                            spillovers.append(sp)

        heatmap = self.generate_heatmap(returns)

        return CrossMarketReport(
            correlations=correlations,
            lead_lag=lead_lag,
            spillovers=spillovers,
            heatmap_data=heatmap,
        )
