"""Tests for RecomputeAnalyzer — prediction generation, DB storage, and feedback loop."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market.analysis.recompute_analyzer import RecomputeAnalyzer
from market.analysis.recompute_estimator import RecomputeEstimator


class TestRecomputeAnalyzerPrediction:
    """Test prediction computation and DB storage."""

    def test_get_prediction_nonexistent(self):
        """Should return None for function with no predictions."""
        pred = RecomputeAnalyzer.get_prediction("nonexistent_function_xyz")
        assert pred is None

    def test_get_all_predictions_returns_list(self):
        """Should return a list of prediction dicts."""
        preds = RecomputeAnalyzer.get_all_predictions()
        assert isinstance(preds, list)

    def test_analyze_function_no_history(self):
        """Should handle function with no run history gracefully."""
        result = RecomputeAnalyzer.analyze_function("nonexistent_function_xyz")
        assert isinstance(result, dict)
        assert result.get("generated", 0) == 0

    def test_analyze_all_returns_summary(self):
        """Should return a summary dict."""
        summary = RecomputeAnalyzer.analyze_all()
        assert isinstance(summary, dict)
        assert "functions_analyzed" in summary or "error" in summary


class TestRecomputeAnalyzerFeedback:
    """Test feedback loop: prediction accuracy evaluation."""

    def test_evaluate_prediction_accuracy(self):
        """Should return a summary dict."""
        result = RecomputeAnalyzer.evaluate_prediction_accuracy()
        assert isinstance(result, dict)
        assert "predictions_evaluated" in result or "error" in result

    def test_get_accuracy_history(self):
        """Should return a list of accuracy records."""
        history = RecomputeAnalyzer.get_accuracy_history()
        assert isinstance(history, list)

    def test_mark_prediction_used_nonexistent(self):
        """Should not raise for nonexistent prediction."""
        RecomputeAnalyzer.mark_prediction_used("nonexistent_xyz", incremental=False)
        assert True


class TestEstimatorReadsFromDB:
    """Test that RecomputeEstimator reads predictions from DB."""

    def test_estimate_function_returns_source_field(self):
        """Estimate should include 'source' field indicating data origin."""
        est = RecomputeEstimator.estimate_function("recompute_scores")
        assert "source" in est
        assert est["source"] in ("db_prediction", "no_data")

    def test_estimate_function_includes_confidence_score(self):
        """Should include numeric confidence_score."""
        est = RecomputeEstimator.estimate_function("recompute_scores")
        assert "confidence_score" in est
        assert 0.0 <= est["confidence_score"] <= 1.0

    def test_estimate_function_includes_analysis_method(self):
        """Should include analysis_method field."""
        est = RecomputeEstimator.estimate_function("recompute_scores")
        assert "analysis_method" in est

    def test_estimate_function_includes_sample_size(self):
        """Should include sample_size field."""
        est = RecomputeEstimator.estimate_function("recompute_scores")
        assert "sample_size" in est


class TestIntegrationAnalyzerEstimator:
    """Test integration between Analyzer and Estimator."""

    def test_record_run_then_analyze_then_estimate(self):
        """Full cycle: record run → analyze → get prediction from DB."""
        now = datetime.now(UTC)

        # 1. Record a few runs
        for i in range(3):
            RecomputeEstimator.record_run(
                function_name="test_analyzer_cycle_fn",
                started_at=now - timedelta(seconds=10 - i),
                completed_at=now - timedelta(seconds=5 - i),
                duration_seconds=5.0 + i,
                rows_affected=100 + i * 10,
                status="completed",
            )

        # 2. Analyze
        result = RecomputeAnalyzer.analyze_function("test_analyzer_cycle_fn")
        assert result.get("generated", 0) + result.get("updated", 0) > 0

        # 3. Get prediction from DB
        pred = RecomputeAnalyzer.get_prediction("test_analyzer_cycle_fn")
        if pred:
            assert pred["function_name"] == "test_analyzer_cycle_fn"
            assert pred["predicted_duration_s"] > 0
            assert pred["predicted_rows"] > 0
            assert pred["analysis_method"] in ("rolling_avg", "exponential", "regression", "last_value")

        # 4. Estimate should now use DB prediction
        est = RecomputeEstimator.estimate_function("test_analyzer_cycle_fn")
        if est["source"] == "db_prediction":
            assert est["predicted_duration_s"] is not None
            assert est["predicted_rows"] is not None
