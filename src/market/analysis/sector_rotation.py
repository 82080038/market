"""Sector Rotation Analysis Engine (pustaka/35-multi-asset-cross-market-analysis.md).

Analyzes sector rotation within the Indonesian stock market (IDX) by combining
sector momentum, rank rotation, and relative strength vs the market benchmark.

The engine is CPU-only (pandas/numpy) and strictly avoids look-ahead bias:
any signal computed at time T uses only data with timestamps <= T.

References:
    pustaka/35-multi-asset-cross-market-analysis.md
    pustaka/89-faktor-pasar-modal-analisis-implementasi.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SectorScore:
    """Aggregate score for a single sector.

    Attributes:
        sector: Sector name (e.g. "Financials", "Energy").
        score: Aggregate score across all tickers in the sector.
        n_tickers: Number of tickers contributing to the score.
        top_tickers: Top 3 tickers by score within the sector.
        bottom_tickers: Bottom 3 tickers by score within the sector.
    """

    sector: str
    score: float
    n_tickers: int
    top_tickers: list[str] = field(default_factory=list)
    bottom_tickers: list[str] = field(default_factory=list)


@dataclass
class SectorMomentum:
    """Momentum snapshot for a single sector.

    Attributes:
        sector: Sector name.
        momentum: Cumulative return over the lookback window.
        rank: Momentum rank (1 = highest momentum, N = lowest).
        return_pct: Cumulative return expressed as a percentage.
    """

    sector: str
    momentum: float
    rank: int
    return_pct: float


@dataclass
class RotationSignal:
    """Rotation signal comparing short-term vs long-term sector rank.

    Attributes:
        sector: Sector name.
        rotation_signal: Value in [-1, +1]; positive = rising, negative = falling.
        rank_change: long_rank - short_rank (positive = improving).
        direction: "rising", "falling", or "stable".
        short_rank: Average rank over the short window.
        long_rank: Average rank over the long window.
    """

    sector: str
    rotation_signal: float
    rank_change: int
    direction: str
    short_rank: int
    long_rank: int


@dataclass
class SectorRecommendation:
    """Composite recommendation for a single sector.

    Attributes:
        sector: Sector name.
        rank: Recommendation rank (1 = best).
        composite_score: Weighted blend of momentum, rotation, and RS.
        direction: Rotation direction ("rising"/"falling"/"stable").
        momentum_score: Normalized momentum contribution.
        rotation_score: Rotation signal contribution.
        rs_score: Normalized relative-strength contribution.
        rationale: Human-readable explanation of the recommendation.
    """

    sector: str
    rank: int
    composite_score: float
    direction: str
    momentum_score: float
    rotation_score: float
    rs_score: float
    rationale: str


def aggregate_sector_scores(
    ticker_scores: dict[str, float],
    ticker_sectors: dict[str, str],
    method: str = "mean",
) -> dict[str, SectorScore]:
    """Aggregate per-ticker scores into per-sector scores.

    Tickers present in ``ticker_scores`` but missing from ``ticker_sectors``
    (or vice versa) are skipped gracefully.

    Args:
        ticker_scores: Mapping of ticker -> score.
        ticker_sectors: Mapping of ticker -> sector name.
        method: Aggregation method: "mean", "median", or "weighted"
            (currently equal weight, same as "mean").

    Returns:
        Dict mapping sector name to SectorScore.
    """
    # Group tickers by sector, only keeping tickers present in both inputs
    sector_tickers: dict[str, list[str]] = {}
    for ticker, _score in ticker_scores.items():
        sector = ticker_sectors.get(ticker)
        if sector is None:
            continue
        sector_tickers.setdefault(sector, []).append(ticker)

    results: dict[str, SectorScore] = {}
    for sector, tickers in sector_tickers.items():
        scores = np.array(
            [ticker_scores[t] for t in tickers], dtype=float,
        )
        if scores.size == 0:
            continue

        if method == "median":
            agg = float(np.median(scores))
        elif method == "weighted":
            # Equal weight for now — identical to mean
            agg = float(np.mean(scores))
        else:  # "mean" (default)
            agg = float(np.mean(scores))

        # Sort tickers by score descending for top, ascending for bottom
        sorted_desc = sorted(tickers, key=lambda t: ticker_scores[t], reverse=True)
        sorted_asc = sorted(tickers, key=lambda t: ticker_scores[t])

        results[sector] = SectorScore(
            sector=sector,
            score=round(agg, 6),
            n_tickers=len(tickers),
            top_tickers=sorted_desc[:3],
            bottom_tickers=sorted_asc[:3],
        )

    return results


def compute_sector_momentum(
    sector_returns: dict[str, pd.Series],
    lookback: int = 20,
) -> dict[str, SectorMomentum]:
    """Compute cumulative momentum for each sector and rank them.

    Momentum is the cumulative return over the last ``lookback`` days.
    Rank 1 = highest momentum, N = lowest. Empty input returns an empty dict.

    Args:
        sector_returns: Mapping of sector -> daily returns series.
        lookback: Number of trailing days for cumulative return.

    Returns:
        Dict mapping sector name to SectorMomentum.
    """
    if not sector_returns:
        return {}

    momentum_values: dict[str, float] = {}
    for sector, returns in sector_returns.items():
        if returns is None or returns.empty:
            continue
        tail = returns.tail(lookback)
        if tail.empty:
            continue
        # Cumulative return = product(1 + r) - 1
        cum = float((1.0 + tail).prod() - 1.0)
        momentum_values[sector] = cum

    if not momentum_values:
        return {}

    # Rank: 1 = highest momentum
    sorted_sectors = sorted(
        momentum_values.items(), key=lambda kv: kv[1], reverse=True,
    )
    results: dict[str, SectorMomentum] = {}
    for rank, (sector, mom) in enumerate(sorted_sectors, start=1):
        results[sector] = SectorMomentum(
            sector=sector,
            momentum=round(mom, 6),
            rank=rank,
            return_pct=round(mom * 100.0, 4),
        )

    return results


def detect_rotation(
    sector_momentum_history: pd.DataFrame,
    short_window: int = 5,
    long_window: int = 20,
) -> dict[str, RotationSignal]:
    """Detect sector rotation by comparing short-term vs long-term ranks.

    For each sector, compute the average rank over the last ``short_window``
    days and the last ``long_window`` days. A sector whose short-term rank is
    better (lower number) than its long-term rank is "rising".

    No look-ahead bias: only the trailing windows ending at the last row are
    used. Callers may apply ``.shift(1)`` to the input frame to align signals
    to the next trading day.

    Args:
        sector_momentum_history: DataFrame (index=dates, columns=sectors,
            values=momentum). Higher momentum = better.
        short_window: Trailing days for short-term rank.
        long_window: Trailing days for long-term rank.

    Returns:
        Dict mapping sector name to RotationSignal.
    """
    if sector_momentum_history is None or sector_momentum_history.empty:
        return {}

    sectors = list(sector_momentum_history.columns)
    n_sectors = len(sectors)
    if n_sectors == 0:
        return {}

    max_rank = n_sectors

    # Rank sectors per row: 1 = highest momentum (rank ascending=False)
    daily_ranks = sector_momentum_history.rank(
        axis=1, method="average", ascending=False,
    )

    # Use only trailing windows (no look-ahead)
    short_ranks = daily_ranks.tail(short_window).mean()
    long_ranks = daily_ranks.tail(long_window).mean()

    results: dict[str, RotationSignal] = {}
    for sector in sectors:
        short_rank = float(short_ranks.get(sector, np.nan))
        long_rank = float(long_ranks.get(sector, np.nan))
        if np.isnan(short_rank) or np.isnan(long_rank):
            continue

        rank_change = round(long_rank - short_rank)
        rotation_signal = (
            (long_rank - short_rank) / max_rank if max_rank > 0 else 0.0
        )
        # Clamp to [-1, 1]
        rotation_signal = float(
            max(-1.0, min(1.0, rotation_signal)),
        )

        if rank_change > 1:
            direction = "rising"
        elif rank_change < -1:
            direction = "falling"
        else:
            direction = "stable"

        results[sector] = RotationSignal(
            sector=sector,
            rotation_signal=round(rotation_signal, 6),
            rank_change=rank_change,
            direction=direction,
            short_rank=round(short_rank),
            long_rank=round(long_rank),
        )

    return results


def compute_relative_strength(
    sector_returns: pd.Series,
    market_returns: pd.Series,
    window: int = 60,
) -> tuple[float, float]:
    """Compute relative strength of a sector vs the market benchmark.

    RS = cumulative sector return - cumulative market return over ``window``.
    RS ratio = sector_return / market_return (guarded against division by zero).

    No look-ahead bias: only the trailing ``window`` days ending at the last
    aligned row are used.

    Args:
        sector_returns: Daily returns series for the sector.
        market_returns: Daily returns series for the market benchmark.
        window: Trailing window in trading days.

    Returns:
        Tuple of (rs, rs_ratio). Positive RS means the sector is
        outperforming the market.
    """
    if sector_returns is None or market_returns is None:
        return 0.0, 0.0
    if sector_returns.empty or market_returns.empty:
        return 0.0, 0.0

    combined = pd.DataFrame(
        {"sector": sector_returns, "market": market_returns},
    ).dropna()
    if combined.empty:
        return 0.0, 0.0

    tail = combined.tail(window)
    if tail.empty:
        return 0.0, 0.0

    sector_cum = float((1.0 + tail["sector"]).prod() - 1.0)
    market_cum = float((1.0 + tail["market"]).prod() - 1.0)

    rs = sector_cum - market_cum
    rs_ratio = 0.0 if abs(market_cum) < 1e-10 else sector_cum / market_cum

    return round(rs, 6), round(rs_ratio, 6)


def compute_rotation_pair(
    risk_on_returns: pd.Series,
    risk_off_returns: pd.Series,
    window: int = 20,
) -> float:
    """Compute a risk-on vs risk-off rotation signal in [-1, 1].

    Signal = (risk_on_cum - risk_off_cum) /
             (abs(risk_on_cum) + abs(risk_off_cum) + 1e-10)

    Positive signal favors risk-on; negative favors risk-off.

    Args:
        risk_on_returns: Daily returns series for the risk-on basket.
        risk_off_returns: Daily returns series for the risk-off basket.
        window: Trailing window in trading days.

    Returns:
        Float in [-1, 1].
    """
    if risk_on_returns is None or risk_off_returns is None:
        return 0.0
    if risk_on_returns.empty or risk_off_returns.empty:
        return 0.0

    combined = pd.DataFrame(
        {"risk_on": risk_on_returns, "risk_off": risk_off_returns},
    ).dropna()
    if combined.empty:
        return 0.0

    tail = combined.tail(window)
    if tail.empty:
        return 0.0

    risk_on_cum = float((1.0 + tail["risk_on"]).prod() - 1.0)
    risk_off_cum = float((1.0 + tail["risk_off"]).prod() - 1.0)

    denom = abs(risk_on_cum) + abs(risk_off_cum) + 1e-10
    signal = (risk_on_cum - risk_off_cum) / denom
    return float(max(-1.0, min(1.0, signal)))


def recommend_sectors(
    sector_momentum_dict: dict[str, SectorMomentum],
    rotation_dict: dict[str, RotationSignal],
    rs_dict: dict[str, float],
    top_n: int = 3,
) -> list[SectorRecommendation]:
    """Combine momentum, rotation, and relative strength into recommendations.

    composite = 0.4 * momentum_normalized + 0.3 * rotation_signal
                + 0.3 * rs_normalized

    Momentum is normalized so rank 1 -> 1.0 and rank N -> 0.0. Relative
    strength is min-max normalized across sectors. The result is sorted by
    composite score descending (best first) and assigned ranks.

    Args:
        sector_momentum_dict: Output of compute_sector_momentum.
        rotation_dict: Output of detect_rotation.
        rs_dict: Mapping of sector -> RS value (from compute_relative_strength).
        top_n: Number of top sectors to return (returns all if fewer exist).

    Returns:
        List of SectorRecommendation sorted by rank (best first).
    """
    if not sector_momentum_dict:
        return []

    sectors = list(sector_momentum_dict.keys())
    n = len(sectors)
    if n == 0:
        return []

    # Normalize momentum: rank 1 -> 1.0, rank N -> 0.0
    momentum_norm: dict[str, float] = {}
    for s in sectors:
        rank = sector_momentum_dict[s].rank
        momentum_norm[s] = (n - rank) / (n - 1) if n > 1 else 1.0

    # Normalize RS via min-max across sectors
    rs_values = np.array(
        [rs_dict.get(s, 0.0) for s in sectors], dtype=float,
    )
    rs_min = float(np.min(rs_values))
    rs_max = float(np.max(rs_values))
    rs_range = rs_max - rs_min
    rs_norm: dict[str, float] = {}
    for s in sectors:
        val = rs_dict.get(s, 0.0)
        if rs_range < 1e-12:
            rs_norm[s] = 0.5
        else:
            rs_norm[s] = (val - rs_min) / rs_range

    composite: dict[str, float] = {}
    for s in sectors:
        rot = rotation_dict.get(s)
        rot_signal = rot.rotation_signal if rot else 0.0
        score = (
            0.4 * momentum_norm[s]
            + 0.3 * rot_signal
            + 0.3 * rs_norm[s]
        )
        composite[s] = float(score)

    sorted_sectors = sorted(sectors, key=lambda s: composite[s], reverse=True)

    recommendations: list[SectorRecommendation] = []
    for rank, sector in enumerate(sorted_sectors, start=1):
        mom = sector_momentum_dict[sector]
        rot = rotation_dict.get(sector)
        direction = rot.direction if rot else "stable"
        rot_score = rot.rotation_signal if rot else 0.0
        rs_val = rs_dict.get(sector, 0.0)

        rationale = (
            f"{sector}: momentum rank {mom.rank} "
            f"({mom.return_pct:+.2f}%), rotation {direction} "
            f"(signal {rot_score:+.3f}), RS vs market {rs_val:+.4f}. "
            f"Composite {composite[sector]:.4f}."
        )

        recommendations.append(
            SectorRecommendation(
                sector=sector,
                rank=rank,
                composite_score=round(composite[sector], 6),
                direction=direction,
                momentum_score=round(momentum_norm[sector], 6),
                rotation_score=round(rot_score, 6),
                rs_score=round(rs_norm[sector], 6),
                rationale=rationale,
            ),
        )

    return recommendations[:top_n] if top_n > 0 else recommendations


class SectorRotationEngine:
    """Engine wrapper for sector rotation analysis.

    Wraps the standalone functions in this module into a class interface
    expected by ``SignalEnhancer``. Provides ``recommend_sectors`` which
    takes prices and tickers, computes momentum/rotation/RS internally,
    and returns ``SectorRecommendation`` objects with a ``rotation_signal``
    attribute for compatibility with ``SignalEnhancer._compute_sector_signal``.
    """

    def __init__(
        self,
        short_window: int = 20,
        long_window: int = 60,
        rotation_window: int = 20,
        rs_window: int = 60,
    ) -> None:
        self.short_window = short_window
        self.long_window = long_window
        self.rotation_window = rotation_window
        self.rs_window = rs_window

    def recommend_sectors(
        self,
        prices: pd.DataFrame | None = None,
        tickers: list[str] | None = None,
        market_prices: pd.Series | None = None,
        top_n: int = 3,
    ) -> list[SectorRecommendation]:
        """Compute sector recommendations from price data.

        Args:
            prices: DataFrame where each column is a sector/asset close price.
            tickers: List of column names to use (defaults to all columns).
            market_prices: Optional market benchmark for RS calculation.
            top_n: Number of top sectors to return.

        Returns:
            List of SectorRecommendation with rotation_signal populated.
        """
        if prices is None or prices.empty:
            return []

        sectors = tickers or list(prices.columns)
        returns = prices.pct_change().dropna()

        market_returns = (
            market_prices.pct_change().dropna()
            if market_prices is not None and not market_prices.empty
            else None
        )

        momentum_dict: dict[str, SectorMomentum] = {}
        rotation_dict: dict[str, RotationSignal] = {}
        rs_dict: dict[str, float] = {}

        for sector in sectors:
            if sector not in returns.columns:
                continue
            sr = returns[sector].dropna()
            if sr.empty:
                continue

            momentum_dict[sector] = compute_sector_momentum(
                sr, short_window=self.short_window, long_window=self.long_window,
            )

            short_ret = sr.tail(self.rotation_window)
            long_ret = sr.tail(self.long_window)
            rotation_dict[sector] = detect_rotation(short_ret, long_ret)

            if market_returns is not None:
                rs_val, _ = compute_relative_strength(
                    sr, market_returns, window=self.rs_window,
                )
                rs_dict[sector] = rs_val
            else:
                rs_dict[sector] = 0.0

        recs = recommend_sectors(momentum_dict, rotation_dict, rs_dict, top_n=top_n)

        # Attach rotation_signal for SignalEnhancer compatibility
        for rec in recs:
            rec.rotation_signal = rec.rotation_score  # type: ignore[attr-defined]

        return recs
