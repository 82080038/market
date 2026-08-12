"""CausalStock-style Lag-Dependent Causal Discovery Engine.

Inspired by CausalStock (Liu et al., 2024 — "Deep End-to-end Causal Discovery
for News-driven Stock Movement Prediction"), this module implements a
practical version of lag-dependent causal discovery between stock tickers.

CausalStock uses:
1. Variational inference with Gumbel-softmax for causal graph estimation
2. Lag-dependent temporal causal discovery (TCD)
3. Functional Causal Model (FCM) for prediction

This implementation uses **Granger causality** as a practical substitute for
variational inference — it tests whether past values of ticker J improve
prediction of ticker I, which is a well-established causal discovery method
for time series. The result is a directed causal graph (asymmetric, unlike
correlation).

Key differences from correlation:
- **Correlation** (symmetric): A and B move together
- **Granger causality** (asymmetric): A's past values help predict B's future,
  but not necessarily vice versa

Output:
- Causal strength matrix (directed, lag-dependent)
- Signal: if ticker is causally influenced by market leaders, use that as signal

References:
    - CausalStock: arxiv.org/abs/2411.06391
    - Granger, C.W.J. (1969). "Investigating Causal Relations by Econometric Models"
    - pustaka/96-ai-ml-audit-framework.md (Pilar 2)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class CausalLink:
    """A directed causal link from source to target."""

    source: str
    target: str
    lag: int
    f_statistic: float
    p_value: float
    strength: float  # Normalized [0, 1]


@dataclass
class CausalGraph:
    """Directed causal graph between tickers."""

    links: list[CausalLink] = field(default_factory=list)
    matrix: pd.DataFrame | None = None

    def get_influencers(self, ticker: str, top_n: int = 5) -> list[CausalLink]:
        """Get top causal influencers for a ticker."""
        incoming = [l for l in self.links if l.target == ticker]
        incoming.sort(key=lambda l: l.strength, reverse=True)
        return incoming[:top_n]

    def get_influencees(self, ticker: str, top_n: int = 5) -> list[CausalLink]:
        """Get tickers that this ticker causally influences."""
        outgoing = [l for l in self.links if l.source == ticker]
        outgoing.sort(key=lambda l: l.strength, reverse=True)
        return outgoing[:top_n]


def granger_causality(
    source: pd.Series,
    target: pd.Series,
    max_lag: int = 3,
) -> tuple[float, float, int]:
    """Compute Granger causality from source to target.

    Tests whether past values of source improve prediction of target
    beyond what target's own past provides.

    Args:
        source: Time series of the potential cause.
        target: Time series of the potential effect.
        max_lag: Maximum lag to test.

    Returns:
        Tuple of (F-statistic, p-value, best_lag).
    """
    df = pd.DataFrame({"source": source, "target": target}).dropna()
    if len(df) < max_lag + 20:
        return 0.0, 1.0, 0

    target_clean = df["target"].values
    source_clean = df["source"].values

    best_f = 0.0
    best_p = 1.0
    best_lag = 0

    for lag in range(1, max_lag + 1):
        if len(target_clean) <= lag + 10:
            continue

        y = target_clean[lag:]
        X_restricted = np.column_stack(
            [target_clean[lag - k:-k] for k in range(1, lag + 1)]
        )
        X_unrestricted = np.column_stack([
            target_clean[lag - k:-k] for k in range(1, lag + 1)
        ] + [
            source_clean[lag - k:-k] for k in range(1, lag + 1)
        ])

        X_restricted = np.column_stack([np.ones(len(y)), X_restricted])
        X_unrestricted = np.column_stack([np.ones(len(y)), X_unrestricted])

        try:
            beta_r = np.linalg.lstsq(X_restricted, y, rcond=None)[0]
            resid_r = y - X_restricted @ beta_r
            ssr_r = np.sum(resid_r ** 2)

            beta_u = np.linalg.lstsq(X_unrestricted, y, rcond=None)[0]
            resid_u = y - X_unrestricted @ beta_u
            ssr_u = np.sum(resid_u ** 2)

            n = len(y)
            p_restricted = X_restricted.shape[1]
            p_unrestricted = X_unrestricted.shape[1]
            df_num = p_unrestricted - p_restricted
            df_den = n - p_unrestricted

            if df_den <= 0 or ssr_u <= 0:
                continue

            f_stat = ((ssr_r - ssr_u) / df_num) / (ssr_u / df_den)
            p_value = 1.0 - stats.f.cdf(f_stat, df_num, df_den)

            if f_stat > best_f:
                best_f = f_stat
                best_p = p_value
                best_lag = lag
        except Exception:
            continue

    return best_f, best_p, best_lag


def build_causal_graph(
    returns_df: pd.DataFrame,
    max_lag: int = 3,
    significance: float = 0.05,
    min_f_stat: float = 2.0,
) -> CausalGraph:
    """Build a directed causal graph from returns DataFrame.

    Args:
        returns_df: DataFrame where each column is a ticker's returns.
        max_lag: Maximum lag for Granger causality test.
        significance: P-value threshold for significance.
        min_f_stat: Minimum F-statistic for a link to be included.

    Returns:
        CausalGraph with directed links and strength matrix.
    """
    tickers = list(returns_df.columns)
    links: list[CausalLink] = []
    strength_matrix = pd.DataFrame(0.0, index=tickers, columns=tickers)

    for i, target in enumerate(tickers):
        for j, source in enumerate(tickers):
            if i == j:
                continue

            target_series = returns_df[target].dropna()
            source_series = returns_df[source].dropna()

            common = target_series.index.intersection(source_series.index)
            if len(common) < max_lag + 20:
                continue

            f_stat, p_val, best_lag = granger_causality(
                source_series.loc[common],
                target_series.loc[common],
                max_lag=max_lag,
            )

            if p_val < significance and f_stat > min_f_stat:
                strength = float(1.0 / (1.0 + np.exp(-f_stat / 5.0)))
                links.append(CausalLink(
                    source=source,
                    target=target,
                    lag=best_lag,
                    f_statistic=f_stat,
                    p_value=p_val,
                    strength=strength,
                ))
                strength_matrix.loc[source, target] = strength

    return CausalGraph(links=links, matrix=strength_matrix)


class CausalDiscoveryEngine:
    """Lag-dependent causal discovery engine for stock movement prediction.

    Discovers directed causal relationships between tickers using Granger
    causality, then generates trading signals based on the causal graph.

    Signal logic:
    - If market leaders (high causal strength sources) are bullish -> target bullish
    - If market leaders are bearish -> target bearish
    - Causal strength weights the signal confidence

    Usage:
        engine = CausalDiscoveryEngine()
        graph = engine.discover(returns_df)
        signal = engine.generate_signal(ticker, graph, returns_df)
    """

    def __init__(
        self,
        max_lag: int = 3,
        significance: float = 0.05,
        retest_interval: int = 60,
        min_data_days: int = 120,
    ) -> None:
        self.max_lag = max_lag
        self.significance = significance
        self.retest_interval = retest_interval
        self.min_data_days = min_data_days

    def discover(self, returns_df: pd.DataFrame) -> CausalGraph:
        """Build causal graph from returns data."""
        return build_causal_graph(
            returns_df,
            max_lag=self.max_lag,
            significance=self.significance,
        )

    def generate_signal(
        self,
        ticker: str,
        graph: CausalGraph,
        returns_df: pd.DataFrame,
        lookback: int = 5,
    ) -> int:
        """Generate trading signal for a ticker based on causal influencers.

        Args:
            ticker: Target ticker.
            graph: Causal graph from discover().
            returns_df: Returns DataFrame.
            lookback: Days to look back for influencer momentum.

        Returns:
            Signal: -1, 0, or +1.
        """
        influencers = graph.get_influencers(ticker, top_n=5)
        if not influencers:
            return 0

        weighted_signal = 0.0
        total_weight = 0.0

        for link in influencers:
            if link.source not in returns_df.columns:
                continue

            source_returns = returns_df[link.source].dropna()
            if len(source_returns) < lookback:
                continue

            recent_return = float(source_returns.tail(lookback).sum())
            weighted_signal += recent_return * link.strength
            total_weight += link.strength

        if total_weight == 0:
            return 0

        consensus = weighted_signal / total_weight

        if consensus > 0.01:
            return 1
        elif consensus < -0.01:
            return -1
        return 0

    def generate_signal_series(
        self,
        ticker: str,
        all_returns: pd.DataFrame,
        window: int = 120,
    ) -> pd.Series:
        """Generate signal series for backtesting (walk-forward, no look-ahead).

        Args:
            ticker: Target ticker.
            all_returns: DataFrame with all tickers' returns.
            window: Rolling window for causal graph re-estimation.

        Returns:
            Series of signals {-1, 0, +1}.
        """
        signals = pd.Series(0, index=all_returns.index)

        if len(all_returns) < self.min_data_days:
            return signals

        graph: CausalGraph | None = None
        last_retest = 0

        for i in range(self.min_data_days, len(all_returns)):
            if graph is None or (i - last_retest) >= self.retest_interval:
                train_data = all_returns.iloc[max(0, i - window):i]
                if len(train_data) >= 60:
                    graph = self.discover(train_data)
                    last_retest = i

            if graph is None:
                continue

            current_data = all_returns.iloc[:i + 1]
            sig = self.generate_signal(ticker, graph, current_data)
            signals.iloc[i] = sig

        return signals
