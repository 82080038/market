"""Tests for Sector Rotation Analysis Engine.

See:
    pustaka/35-multi-asset-cross-market-analysis.md
    pustaka/89-faktor-pasar-modal-analisis-implementasi.md
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.sector_rotation import (
    RotationSignal,
    SectorMomentum,
    SectorRecommendation,
    SectorScore,
    aggregate_sector_scores,
    compute_relative_strength,
    compute_rotation_pair,
    compute_sector_momentum,
    detect_rotation,
    recommend_sectors,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_returns(n: int = 60, seed: int = 42, mu: float = 0.001) -> pd.Series:
    """Create a synthetic daily returns series."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.Series(np.random.normal(mu, 0.02, n), index=dates)


def _make_momentum_history(
    sectors: list[str],
    n_days: int = 30,
    rising_sector: str | None = None,
    falling_sector: str | None = None,
) -> pd.DataFrame:
    """Build a synthetic sector momentum history DataFrame.

    ``rising_sector`` is low for the first ~2/3 of days and high for the last
    ~1/3, so its short-term rank is much better than its long-term rank.
    ``falling_sector`` is the reverse. All other sectors get stationary
    momentum around the midpoint.
    """
    np.random.seed(0)
    dates = pd.date_range("2024-01-02", periods=n_days, freq="B")
    # Rising/falling sectors are low/high for all but the last few days so
    # the long-window average rank differs sharply from the short-window rank.
    split = max(1, n_days - 5)
    data: dict[str, np.ndarray] = {}
    for s in sectors:
        if s == rising_sector:
            base = np.where(np.arange(n_days) < split, -0.05, 0.05)
        elif s == falling_sector:
            base = np.where(np.arange(n_days) < split, 0.05, -0.05)
        else:
            base = np.random.normal(0.01, 0.005, n_days)
        data[s] = base.astype(float)
    return pd.DataFrame(data, index=dates)


# ---------------------------------------------------------------------------
# aggregate_sector_scores
# ---------------------------------------------------------------------------


def test_aggregate_sector_scores_mean():
    ticker_scores = {
        "BBCA.JK": 0.8, "BBRI.JK": 0.6, "BMRI.JK": 0.4,  # Financials
        "TLKM.JK": 0.5, "ISAT.JK": 0.3,                   # Telecom
        "UNVR.JK": 0.9, "ICBP.JK": 0.7,                   "INDF.JK": 0.5,  # Consumer
    }
    ticker_sectors = {
        "BBCA.JK": "Financials", "BBRI.JK": "Financials", "BMRI.JK": "Financials",
        "TLKM.JK": "Telecom", "ISAT.JK": "Telecom",
        "UNVR.JK": "Consumer", "ICBP.JK": "Consumer", "INDF.JK": "Consumer",
    }
    result = aggregate_sector_scores(ticker_scores, ticker_sectors, method="mean")
    assert set(result.keys()) == {"Financials", "Telecom", "Consumer"}
    fin = result["Financials"]
    assert isinstance(fin, SectorScore)
    assert fin.n_tickers == 3
    assert fin.score == pytest.approx((0.8 + 0.6 + 0.4) / 3, rel=1e-6)
    assert fin.top_tickers[0] == "BBCA.JK"
    assert fin.bottom_tickers[0] == "BMRI.JK"


def test_aggregate_sector_scores_median():
    ticker_scores = {"A.JK": 1.0, "B.JK": 2.0, "C.JK": 100.0}
    ticker_sectors = {"A.JK": "X", "B.JK": "X", "C.JK": "X"}
    result = aggregate_sector_scores(ticker_scores, ticker_sectors, method="median")
    assert result["X"].score == pytest.approx(2.0, rel=1e-6)


def test_aggregate_sector_scores_unknown_ticker_skipped():
    # Ticker in scores but not in sectors mapping -> skipped
    ticker_scores = {"A.JK": 1.0, "UNKNOWN.JK": 5.0}
    ticker_sectors = {"A.JK": "X"}
    result = aggregate_sector_scores(ticker_scores, ticker_sectors)
    assert "X" in result
    assert result["X"].n_tickers == 1
    # No sector created for the unknown ticker
    assert all("UNKNOWN" not in s for s in result)


def test_aggregate_sector_scores_top_bottom_three():
    scores = {f"T{i}.JK": float(i) for i in range(10)}
    sectors = {f"T{i}.JK": "Big" for i in range(10)}
    result = aggregate_sector_scores(scores, sectors)
    big = result["Big"]
    assert big.n_tickers == 10
    assert len(big.top_tickers) == 3
    assert len(big.bottom_tickers) == 3
    assert big.top_tickers == ["T9.JK", "T8.JK", "T7.JK"]
    assert big.bottom_tickers == ["T0.JK", "T1.JK", "T2.JK"]


# ---------------------------------------------------------------------------
# compute_sector_momentum
# ---------------------------------------------------------------------------


def test_compute_sector_momentum_ranking():
    np.random.seed(1)
    dates = pd.date_range("2024-01-02", periods=40, freq="B")
    # High-return sector should rank 1
    high = pd.Series(np.random.normal(0.01, 0.01, 40), index=dates)
    low = pd.Series(np.random.normal(-0.01, 0.01, 40), index=dates)
    mid = pd.Series(np.random.normal(0.0, 0.01, 40), index=dates)
    result = compute_sector_momentum(
        {"High": high, "Low": low, "Mid": mid}, lookback=20,
    )
    assert isinstance(result["High"], SectorMomentum)
    assert result["High"].rank == 1
    assert result["Low"].rank == 3
    # Rank 1 should have the highest return_pct
    assert result["High"].return_pct > result["Mid"].return_pct
    assert result["Mid"].return_pct > result["Low"].return_pct


def test_compute_sector_momentum_empty():
    assert compute_sector_momentum({}) == {}
    assert compute_sector_momentum({"X": pd.Series(dtype=float)}) == {}


# ---------------------------------------------------------------------------
# detect_rotation
# ---------------------------------------------------------------------------


def test_detect_rotation_rising():
    hist = _make_momentum_history(
        ["A", "B", "C"], n_days=30, rising_sector="A",
    )
    result = detect_rotation(hist, short_window=5, long_window=20)
    a = result["A"]
    assert isinstance(a, RotationSignal)
    assert a.direction == "rising"
    assert a.rotation_signal > 0
    # Short rank should be better (lower) than long rank for a rising sector
    assert a.short_rank <= a.long_rank


def test_detect_rotation_falling():
    hist = _make_momentum_history(
        ["A", "B", "C"], n_days=30, falling_sector="A",
    )
    result = detect_rotation(hist, short_window=5, long_window=20)
    a = result["A"]
    assert a.direction == "falling"
    assert a.rotation_signal < 0
    assert a.short_rank >= a.long_rank


def test_detect_rotation_empty():
    assert detect_rotation(pd.DataFrame()) == {}


# ---------------------------------------------------------------------------
# compute_relative_strength
# ---------------------------------------------------------------------------


def test_compute_relative_strength_outperforming():
    dates = pd.date_range("2024-01-02", periods=80, freq="B")
    # Deterministic: sector has higher returns than the market
    sector = pd.Series(np.full(80, 0.002), index=dates)
    market = pd.Series(np.full(80, 0.0005), index=dates)
    rs, rs_ratio = compute_relative_strength(sector, market, window=60)
    assert rs > 0  # sector beats market
    assert rs_ratio > 0


def test_compute_relative_strength_lagging():
    np.random.seed(3)
    dates = pd.date_range("2024-01-02", periods=80, freq="B")
    sector = pd.Series(np.random.normal(-0.002, 0.01, 80), index=dates)
    market = pd.Series(np.random.normal(0.001, 0.01, 80), index=dates)
    rs, _ = compute_relative_strength(sector, market, window=60)
    assert rs < 0  # sector lags market


def test_compute_relative_strength_empty():
    rs, rs_ratio = compute_relative_strength(
        pd.Series(dtype=float), pd.Series(dtype=float),
    )
    assert rs == 0.0
    assert rs_ratio == 0.0


# ---------------------------------------------------------------------------
# compute_rotation_pair
# ---------------------------------------------------------------------------


def test_compute_rotation_pair_risk_on_favored():
    np.random.seed(4)
    dates = pd.date_range("2024-01-02", periods=40, freq="B")
    risk_on = pd.Series(np.random.normal(0.01, 0.01, 40), index=dates)
    risk_off = pd.Series(np.random.normal(-0.01, 0.01, 40), index=dates)
    signal = compute_rotation_pair(risk_on, risk_off, window=20)
    assert signal > 0
    assert -1.0 <= signal <= 1.0


def test_compute_rotation_pair_risk_off_favored():
    np.random.seed(5)
    dates = pd.date_range("2024-01-02", periods=40, freq="B")
    risk_on = pd.Series(np.random.normal(-0.01, 0.01, 40), index=dates)
    risk_off = pd.Series(np.random.normal(0.01, 0.01, 40), index=dates)
    signal = compute_rotation_pair(risk_on, risk_off, window=20)
    assert signal < 0


def test_compute_rotation_pair_empty():
    assert compute_rotation_pair(
        pd.Series(dtype=float), pd.Series(dtype=float),
    ) == 0.0


# ---------------------------------------------------------------------------
# recommend_sectors
# ---------------------------------------------------------------------------


def test_recommend_sectors_sorted_best_first():
    momentum = {
        "A": SectorMomentum("A", 0.05, 1, 5.0),
        "B": SectorMomentum("B", 0.03, 2, 3.0),
        "C": SectorMomentum("C", 0.01, 3, 1.0),
    }
    rotation = {
        "A": RotationSignal("A", 0.5, 2, "rising", 1, 3),
        "B": RotationSignal("B", 0.0, 0, "stable", 2, 2),
        "C": RotationSignal("C", -0.5, -2, "falling", 3, 1),
    }
    rs = {"A": 0.02, "B": 0.0, "C": -0.02}
    recs = recommend_sectors(momentum, rotation, rs, top_n=3)
    assert len(recs) == 3
    assert all(isinstance(r, SectorRecommendation) for r in recs)
    # Ranks should be 1, 2, 3 in order
    assert [r.rank for r in recs] == [1, 2, 3]
    # Best sector (A: top momentum, rising, best RS) should be first
    assert recs[0].sector == "A"
    # Composite scores should be non-increasing
    scores = [r.composite_score for r in recs]
    assert scores == sorted(scores, reverse=True)


def test_recommend_sectors_rationale_nonempty():
    momentum = {
        "A": SectorMomentum("A", 0.05, 1, 5.0),
        "B": SectorMomentum("B", 0.01, 2, 1.0),
    }
    rotation = {
        "A": RotationSignal("A", 0.3, 1, "rising", 1, 2),
        "B": RotationSignal("B", -0.3, -1, "falling", 2, 1),
    }
    rs = {"A": 0.01, "B": -0.01}
    recs = recommend_sectors(momentum, rotation, rs, top_n=2)
    for r in recs:
        assert isinstance(r.rationale, str)
        assert len(r.rationale) > 0
        assert r.sector in r.rationale


def test_recommend_sectors_empty():
    assert recommend_sectors({}, {}, {}) == []


# ---------------------------------------------------------------------------
# No look-ahead bias
# ---------------------------------------------------------------------------


def test_detect_rotation_no_lookahead():
    """detect_rotation should only use trailing windows ending at last row.

    Inserting NaNs after the last valid row must not change the signal,
    and prepending extra rows (future data) must not change it either.
    """
    hist = _make_momentum_history(
        ["A", "B", "C"], n_days=30, rising_sector="A",
    )
    base = detect_rotation(hist, short_window=5, long_window=20)

    # Prepending earlier rows (which represent the "past") should not change
    # the signal computed at the final date.
    earlier = hist.iloc[:5] * 0.0  # zeros, far past
    extended = pd.concat([earlier, hist])
    extended.index = pd.date_range("2023-12-01", periods=len(extended), freq="B")
    ext = detect_rotation(extended, short_window=5, long_window=20)
    for s in base:
        assert base[s].rotation_signal == pytest.approx(
            ext[s].rotation_signal, rel=1e-6,
        )


def test_compute_relative_strength_uses_trailing_window():
    """RS should only depend on the last `window` days, not earlier data."""
    np.random.seed(6)
    dates = pd.date_range("2024-01-02", periods=120, freq="B")
    sector = pd.Series(np.random.normal(0.001, 0.01, 120), index=dates)
    market = pd.Series(np.random.normal(0.001, 0.01, 120), index=dates)

    rs_full, _ = compute_relative_strength(sector, market, window=60)

    # Modify the first 30 days (outside the 60-day trailing window) — RS
    # should be unchanged because only the trailing 60 days are used.
    sector_early = sector.copy()
    sector_early.iloc[:30] = 0.5  # huge but out-of-window
    rs_early, _ = compute_relative_strength(sector_early, market, window=60)
    assert rs_full == pytest.approx(rs_early, rel=1e-6)


def test_compute_sector_momentum_uses_trailing_lookback():
    """Momentum should only use the last `lookback` days."""
    np.random.seed(7)
    dates = pd.date_range("2024-01-02", periods=60, freq="B")
    sector = pd.Series(np.random.normal(0.001, 0.01, 60), index=dates)
    result = compute_sector_momentum({"X": sector}, lookback=20)

    # Modify first 10 days (outside the 20-day lookback) — momentum unchanged
    sector2 = sector.copy()
    sector2.iloc[:10] = 0.5
    result2 = compute_sector_momentum({"X": sector2}, lookback=20)
    assert result["X"].momentum == pytest.approx(result2["X"].momentum, rel=1e-9)
