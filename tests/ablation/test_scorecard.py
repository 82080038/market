"""Tests for scorecard verdict logic."""

from __future__ import annotations

import pytest

from market.ablation.isolated_backtest import IsolationResult
from market.ablation.scorecard import ScoreCard, Verdict, score_engine


def _make_result(
    engine_name: str = "test",
    delta_sharpe: float = 0.2,
    delta_alpha: float = 0.01,
    delta_win_rate: float = 5.0,
    p_value: float = 0.01,
    is_significant: bool = True,
    n_observations: int = 500,
    isolated_sharpe: float = 1.5,
    baseline_sharpe: float = 1.3,
    error: str | None = None,
) -> IsolationResult:
    return IsolationResult(
        engine_name=engine_name,
        baseline_metrics={"sharpe_ratio": baseline_sharpe, "alpha": 0.0, "win_rate_pct": 50.0},
        isolated_metrics={"sharpe_ratio": isolated_sharpe, "alpha": delta_alpha, "win_rate_pct": 50.0 + delta_win_rate},
        delta_metrics={"sharpe_ratio": delta_sharpe, "alpha": delta_alpha, "win_rate_pct": delta_win_rate},
        p_value=p_value,
        t_statistic=2.5,
        is_significant=is_significant,
        n_observations=n_observations,
        error=error,
    )


class TestScoreEngine:
    def test_keep_verdict(self):
        """KEEP when p < 0.05 and delta_sharpe > 0.1."""
        result = _make_result(delta_sharpe=0.2, p_value=0.01, is_significant=True)
        sc = score_engine(result)
        assert sc.verdict == Verdict.KEEP
        assert sc.composite_score > 0
        assert len(sc.reasons) > 0

    def test_marginal_verdict_low_pvalue_small_sharpe(self):
        """MARGINAL when p < 0.05 but delta_sharpe <= 0.1."""
        result = _make_result(delta_sharpe=0.05, p_value=0.02, is_significant=True)
        sc = score_engine(result)
        assert sc.verdict == Verdict.MARGINAL

    def test_marginal_verdict_medium_pvalue(self):
        """MARGINAL when 0.05 <= p < 0.10."""
        result = _make_result(delta_sharpe=0.2, p_value=0.07, is_significant=False)
        sc = score_engine(result)
        assert sc.verdict == Verdict.MARGINAL

    def test_remove_verdict_high_pvalue(self):
        """REMOVE when p >= 0.10."""
        result = _make_result(delta_sharpe=0.2, p_value=0.15, is_significant=False)
        sc = score_engine(result)
        assert sc.verdict == Verdict.REMOVE
        assert any("Not significant" in r for r in sc.reasons)

    def test_remove_verdict_negative_sharpe(self):
        """REMOVE when delta_sharpe <= 0."""
        result = _make_result(delta_sharpe=-0.1, p_value=0.01, is_significant=True)
        sc = score_engine(result)
        assert sc.verdict == Verdict.REMOVE
        assert any("negative" in r.lower() for r in sc.reasons)

    def test_error_result(self):
        """Error results get REMOVE verdict."""
        result = _make_result(error="Connection failed")
        sc = score_engine(result)
        assert sc.verdict == Verdict.REMOVE
        assert sc.composite_score == 0.0
        assert any("Error" in r for r in sc.reasons)

    def test_composite_score_range(self):
        """Composite score should be in [0, 100]."""
        result = _make_result(delta_sharpe=0.5, delta_alpha=0.05, delta_win_rate=10, p_value=0.001)
        sc = score_engine(result)
        assert 0 <= sc.composite_score <= 100

    def test_to_dict(self):
        result = _make_result()
        sc = score_engine(result)
        d = sc.to_dict()
        assert d["engine_name"] == "test"
        assert d["verdict"] == "KEEP"
        assert "composite_score" in d
        assert "reasons" in d
        assert isinstance(d["reasons"], list)

    def test_keep_scores_higher_than_remove(self):
        keep_result = _make_result(delta_sharpe=0.3, p_value=0.001)
        remove_result = _make_result(delta_sharpe=-0.1, p_value=0.5, is_significant=False)
        keep_sc = score_engine(keep_result)
        remove_sc = score_engine(remove_result)
        assert keep_sc.composite_score > remove_sc.composite_score

    def test_positive_alpha_adds_reason(self):
        result = _make_result(delta_alpha=0.05)
        sc = score_engine(result)
        assert any("Positive alpha" in r for r in sc.reasons)

    def test_negative_alpha_adds_reason(self):
        result = _make_result(delta_alpha=-0.03, delta_sharpe=0.2, p_value=0.01)
        sc = score_engine(result)
        assert any("Negative alpha" in r for r in sc.reasons)
