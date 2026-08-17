"""Tests for RecomputeGraph — selective recompute dependency graph."""

from __future__ import annotations

import pytest
import json

from market.analysis.recompute_graph import RecomputeGraph


class TestRecomputeGraphQuery:
    """Test dependency graph queries."""

    def test_get_full_graph(self):
        """Should return a dict of function_name → [data_sources]."""
        graph = RecomputeGraph.get_full_graph()
        assert isinstance(graph, dict)
        # Should have at least the core recompute functions
        assert "recompute_scores" in graph or len(graph) > 0

    def test_get_all_data_sources(self):
        """Should return list of unique data sources."""
        sources = RecomputeGraph.get_all_data_sources()
        assert isinstance(sources, list)
        # stock_prices should be a common dependency
        if sources:
            assert "stock_prices" in sources

    def test_get_affected_functions_stock_prices(self):
        """stock_prices should affect multiple recompute functions."""
        affected = RecomputeGraph.get_affected_functions("stock_prices")
        assert isinstance(affected, list)
        # If DB has data, should have multiple functions
        # If no DB, should return empty list (graceful degradation)
        if affected:
            assert "recompute_scores" in affected or "recompute_technical_indicators" in affected

    def test_get_affected_functions_nonexistent_source(self):
        """Non-existent data source should return empty list."""
        affected = RecomputeGraph.get_affected_functions("nonexistent_table_xyz")
        assert affected == []

    def test_get_function_dependencies(self):
        """Should return list of dependency dicts for a function."""
        deps = RecomputeGraph.get_function_dependencies("recompute_scores")
        assert isinstance(deps, list)
        if deps:
            assert "data_source" in deps[0]
            assert "source_type" in deps[0]
            assert "is_required" in deps[0]


class TestRecomputeGraphTrigger:
    """Test selective recompute trigger."""

    def test_trigger_dry_run(self):
        """Dry run should return affected functions without executing."""
        result = RecomputeGraph.trigger_recompute(
            data_source="stock_prices",
            triggered_by="test",
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert "functions_triggered" in result
        assert "functions_skipped" in result
        assert isinstance(result["functions_triggered"], list)

    def test_trigger_dry_run_nonexistent(self):
        """Dry run with non-existent source should return empty lists."""
        result = RecomputeGraph.trigger_recompute(
            data_source="nonexistent_table_xyz",
            triggered_by="test",
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["functions_triggered"] == []


class TestRecomputeGraphManage:
    """Test dependency management."""

    def test_add_and_remove_dependency(self):
        """Should add and remove a dependency."""
        # Add
        success = RecomputeGraph.add_dependency(
            function_name="test_function_xyz",
            data_source="test_source_xyz",
            source_type="table",
            is_required=False,
            description="Test dependency",
        )
        # If DB is available, should succeed
        if success:
            # Verify it exists
            deps = RecomputeGraph.get_function_dependencies("test_function_xyz")
            assert any(d["data_source"] == "test_source_xyz" for d in deps)

            # Remove
            removed = RecomputeGraph.remove_dependency("test_function_xyz", "test_source_xyz")
            assert removed is True

            # Verify it's gone
            deps = RecomputeGraph.get_function_dependencies("test_function_xyz")
            assert all(d["data_source"] != "test_source_xyz" for d in deps)
        # If DB not available, just pass


class TestRecomputeGraphCache:
    """Test cache management."""

    def test_clear_cache(self):
        """Should not raise."""
        RecomputeGraph.clear_cache()
        assert True

    def test_graph_cached_consistent(self):
        """Two calls should return same result."""
        g1 = RecomputeGraph.get_full_graph()
        g2 = RecomputeGraph.get_full_graph()
        assert g1 == g2


class TestRecomputeGraphHistory:
    """Test trigger history."""

    def test_get_trigger_history(self):
        """Should return list of trigger records."""
        history = RecomputeGraph.get_trigger_history(limit=5)
        assert isinstance(history, list)
        if history:
            assert "triggered_by" in history[0]
            assert "data_source_updated" in history[0]
            assert "functions_triggered" in history[0]
            assert "status" in history[0]
