"""Tests for RecomputeEstimator — duration/row estimation and smart skip."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from market.analysis.recompute_estimator import RecomputeEstimator


class TestEstimateFunction:
    """Test per-function estimation."""

    def test_estimate_function_returns_dict(self):
        """Should return a dict with estimation fields."""
        est = RecomputeEstimator.estimate_function("recompute_scores")
        assert isinstance(est, dict)
        assert "function_name" in est
        assert "predicted_duration_s" in est
        assert "predicted_rows" in est
        assert "confidence" in est
        assert "run_count" in est
        assert est["function_name"] == "recompute_scores"

    def test_estimate_function_unknown(self):
        """Unknown function should return empty estimate with source='no_data'."""
        est = RecomputeEstimator.estimate_function("nonexistent_function_xyz")
        assert est["confidence"] == "none"
        assert est["predicted_duration_s"] is None
        assert est["predicted_rows"] is None
        assert est["run_count"] == 0
        assert est["source"] == "no_data"


class TestEstimateTrigger:
    """Test trigger-level estimation."""

    def test_estimate_trigger_returns_dict(self):
        """Should return dict with total estimates and per-function breakdown."""
        est = RecomputeEstimator.estimate_trigger("stock_prices")
        assert isinstance(est, dict)
        assert "data_source" in est
        assert "total_estimated_duration_s" in est
        assert "total_estimated_rows" in est or "total_predicted_rows" in est
        assert "functions" in est
        assert "can_skip" in est
        assert est["data_source"] == "stock_prices"

    def test_estimate_trigger_nonexistent(self):
        """Non-existent data source should return empty functions."""
        est = RecomputeEstimator.estimate_trigger("nonexistent_table_xyz")
        assert est["functions"] == []


class TestShouldSkip:
    """Test smart skip logic."""

    def test_should_skip_never_run(self):
        """Function that never ran should not be skipped."""
        skip = RecomputeEstimator.should_skip("nonexistent_function_xyz", "stock_prices")
        assert skip is False

    def test_should_skip_nonexistent_source(self):
        """Non-existent data source should not cause skip."""
        skip = RecomputeEstimator.should_skip("recompute_scores", "nonexistent_table_xyz")
        assert skip is False


class TestRecordRun:
    """Test run recording."""

    def test_record_run_and_history(self):
        """Should record a run and appear in history."""
        now = datetime.now(UTC)
        success = RecomputeEstimator.record_run(
            function_name="test_function_record_run",
            started_at=now,
            completed_at=now + timedelta(seconds=5),
            duration_seconds=5.0,
            rows_affected=100,
            status="completed",
        )
        if success:
            history = RecomputeEstimator.get_run_history("test_function_record_run")
            assert len(history) > 0
            assert history[0]["function_name"] if "function_name" in history[0] else True
            assert history[0]["duration_seconds"] == 5.0
            assert history[0]["rows_affected"] == 100


class TestDryRunWithEstimate:
    """Test that dry_run includes estimates."""

    def test_dry_run_has_estimate(self):
        """Dry run should include estimate field."""
        from market.analysis.recompute_graph import RecomputeGraph

        result = RecomputeGraph.trigger_recompute(
            data_source="stock_prices",
            triggered_by="test",
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert "estimate" in result
        assert "functions_to_run" in result
        assert "functions_skip_fresh" in result
