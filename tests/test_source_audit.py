"""Unit tests for data source audit module (S1 layer isolation).

Verifies that ``market.data.source_audit``:
1. Correctly classifies tables into Internet / Local Logic / Reference / User Input.
2. Correctly assigns update methods (Delta / Batch / Statis / Event-driven).
3. Produces valid Markdown and JSON output.
4. Is 100% free of S2+ dependencies (no analysis, risk, execution, backtest, autonomous, api imports).
"""

from __future__ import annotations

import ast
import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from market.data.source_audit import (
    AuditReport,
    SourceType,
    TableClassification,
    UpdateMethod,
    _TABLE_REGISTRY,
    _get_orm_table_names,
    classify_table,
    run_audit,
)


# ── 1. Registry completeness ────────────────────────────────────────────


class TestRegistryCompleteness:
    """Verify the static registry covers all ORM tables."""

    def test_registry_has_all_orm_tables(self):
        """Every ORM table should have an entry in _TABLE_REGISTRY."""
        orm_tables = _get_orm_table_names()
        missing = orm_tables - set(_TABLE_REGISTRY.keys())
        assert not missing, f"Tables missing from registry: {missing}"

    def test_registry_entries_have_required_fields(self):
        """Each registry entry must have source_type and update_method."""
        for table_name, info in _TABLE_REGISTRY.items():
            assert "source_type" in info, f"{table_name}: missing source_type"
            assert "update_method" in info, f"{table_name}: missing update_method"
            assert "description" in info, f"{table_name}: missing description"

    def test_source_types_are_valid_enum(self):
        """All source_type values must be SourceType enum members."""
        for table_name, info in _TABLE_REGISTRY.items():
            st = info["source_type"]
            assert isinstance(st, SourceType), f"{table_name}: {st} is not SourceType"

    def test_update_methods_are_valid_enum(self):
        """All update_method values must be UpdateMethod enum members."""
        for table_name, info in _TABLE_REGISTRY.items():
            um = info["update_method"]
            assert isinstance(um, UpdateMethod), f"{table_name}: {um} is not UpdateMethod"


# ── 2. Classification logic ─────────────────────────────────────────────


class TestClassifyTable:
    """Test classify_table function."""

    def test_classify_known_table(self):
        """classify_table should return correct classification for known table."""
        tc = classify_table("ohlcv")
        assert tc.table_name == "ohlcv"
        assert tc.source_type == SourceType.INTERNET
        assert tc.update_method == UpdateMethod.DELTA
        assert tc.connector is not None
        assert "yahoo" in tc.connector.lower()

    def test_classify_local_logic_table(self):
        """technical_indicators should be classified as local_logic / batch."""
        tc = classify_table("technical_indicators")
        assert tc.source_type == SourceType.LOCAL_LOGIC
        assert tc.update_method == UpdateMethod.BATCH
        assert tc.recompute_function is not None

    def test_classify_delta_table(self):
        """ml_labels should be classified as local_logic / delta."""
        tc = classify_table("ml_labels")
        assert tc.source_type == SourceType.LOCAL_LOGIC
        assert tc.update_method == UpdateMethod.DELTA
        assert "incremental" in tc.recompute_function.lower() or "watermark" in tc.recompute_function.lower()

    def test_classify_reference_table(self):
        """market_registry should be classified as reference / statis."""
        tc = classify_table("market_registry")
        assert tc.source_type == SourceType.REFERENCE
        assert tc.update_method == UpdateMethod.STATIS

    def test_classify_user_input_table(self):
        """positions should be classified as user_input / event_driven."""
        tc = classify_table("positions")
        assert tc.source_type == SourceType.USER_INPUT
        assert tc.update_method == UpdateMethod.EVENT_DRIVEN

    def test_classify_unknown_table(self):
        """Unknown table should get default classification."""
        tc = classify_table("nonexistent_table")
        assert tc.table_name == "nonexistent_table"
        assert tc.source_type == SourceType.INTERNET  # default fallback
        assert "Unclassified" in tc.description


# ── 3. Internet vs Local Logic classification ───────────────────────────


class TestSourceClassification:
    """Verify Internet vs Local Logic split is correct."""

    @pytest.mark.parametrize("table_name", [
        "ohlcv", "stock_prices", "dividends", "corporate_actions",
        "fundamental_data", "macro_data", "macroeconomic_indicators",
        "fx_rates", "foreign_flow", "broker_flow", "daily_trading_stats",
        "fear_greed", "news", "satellite_observations",
        "policy_events", "external_events",
    ])
    def test_internet_tables(self, table_name):
        """These tables MUST be classified as Internet (external API)."""
        tc = classify_table(table_name)
        assert tc.source_type == SourceType.INTERNET, f"{table_name} should be INTERNET"
        assert tc.connector is not None, f"{table_name} must have a connector"

    @pytest.mark.parametrize("table_name", [
        "technical_indicators", "technical_indicators_wide", "scores",
        "relationship_matrix", "stock_personality", "stock_prediction",
        "ml_labels", "market_regimes", "pattern_analysis",
        "valuation_cache", "satellite_correlation_results",
    ])
    def test_local_logic_tables(self, table_name):
        """These tables MUST be classified as Local Logic (recompute)."""
        tc = classify_table(table_name)
        assert tc.source_type == SourceType.LOCAL_LOGIC, f"{table_name} should be LOCAL_LOGIC"
        assert tc.recompute_function is not None, f"{table_name} must have recompute_function"

    @pytest.mark.parametrize("table_name", [
        "market_registry", "exchanges", "instrument_master", "instruments",
        "sector_master", "regulator", "bursa_efek", "sektor",
        "emiten", "instrumen", "indeks_pasar", "broker", "broker_bursa",
    ])
    def test_reference_tables(self, table_name):
        """These tables MUST be classified as Reference (semi-static)."""
        tc = classify_table(table_name)
        assert tc.source_type == SourceType.REFERENCE, f"{table_name} should be REFERENCE"


# ── 4. Update method classification ─────────────────────────────────────


class TestUpdateMethod:
    """Verify Delta vs Batch classification."""

    @pytest.mark.parametrize("table_name", [
        "ml_labels", "market_regimes", "fear_greed",
        "equity_snapshots", "daily_risk_metrics",
    ])
    def test_delta_tables(self, table_name):
        """These tables support incremental (delta) updates."""
        tc = classify_table(table_name)
        assert tc.update_method == UpdateMethod.DELTA, f"{table_name} should be DELTA"

    @pytest.mark.parametrize("table_name", [
        "technical_indicators", "technical_indicators_wide", "scores",
        "relationship_matrix", "stock_personality", "stock_prediction",
        "pattern_analysis", "valuation_cache", "strategy_assignment",
        "ai_weights", "satellite_correlation_results",
    ])
    def test_batch_tables(self, table_name):
        """These tables require full recompute (batch)."""
        tc = classify_table(table_name)
        assert tc.update_method == UpdateMethod.BATCH, f"{table_name} should be BATCH"

    @pytest.mark.parametrize("table_name", [
        "market_registry", "exchanges", "instrument_master",
        "sector_master", "regulator", "bursa_efek", "sektor",
        "emiten", "instrumen", "indeks_pasar", "broker",
    ])
    def test_statis_tables(self, table_name):
        """These tables are semi-static (rarely change)."""
        tc = classify_table(table_name)
        assert tc.update_method == UpdateMethod.STATIS, f"{table_name} should be STATIS"


# ── 5. Report output format ─────────────────────────────────────────────


class TestReportOutput:
    """Test Markdown and JSON output generation."""

    def _make_mock_report(self) -> AuditReport:
        """Create a minimal mock report for testing output formats."""
        classifications = [
            TableClassification(
                table_name="ohlcv",
                source_type=SourceType.INTERNET,
                update_method=UpdateMethod.DELTA,
                connector="yfinance",
                description="OHLCV data",
                columns=["ticker", "timestamp", "open", "high", "low", "close", "volume"],
                row_count=3_200_000,
            ),
            TableClassification(
                table_name="technical_indicators",
                source_type=SourceType.LOCAL_LOGIC,
                update_method=UpdateMethod.BATCH,
                recompute_function="S2: recompute_technical_indicators",
                description="Technical indicators",
                columns=["ticker", "date", "indicator", "value"],
                row_count=9000,
            ),
        ]
        return AuditReport(
            generated_at="2026-08-11T18:00:00+00:00",
            database_url="postgresql://user:***@localhost/market",
            total_tables=2,
            classifications=classifications,
            summary={"internet": 1, "local_logic": 1},
        )

    def test_markdown_output_has_headers(self):
        """Markdown output should contain required headers."""
        report = self._make_mock_report()
        md = report.to_markdown()
        assert "# Data Source Audit Report" in md
        assert "## Summary" in md
        assert "## Table Classifications" in md
        assert "## Column Details" in md

    def test_markdown_output_has_table_rows(self):
        """Markdown output should contain table entries."""
        report = self._make_mock_report()
        md = report.to_markdown()
        assert "`ohlcv`" in md
        assert "`technical_indicators`" in md
        assert "internet" in md
        assert "local_logic" in md

    def test_json_output_is_valid_json(self):
        """JSON output should be valid parseable JSON."""
        report = self._make_mock_report()
        j = report.to_json()
        data = json.loads(j)
        assert "generated_at" in data
        assert "total_tables" in data
        assert "classifications" in data
        assert data["total_tables"] == 2
        assert len(data["classifications"]) == 2

    def test_json_output_has_correct_enum_values(self):
        """JSON output should serialize enums as strings."""
        report = self._make_mock_report()
        j = report.to_json()
        data = json.loads(j)
        assert data["classifications"][0]["source_type"] == "internet"
        assert data["classifications"][0]["update_method"] == "delta"
        assert data["classifications"][1]["source_type"] == "local_logic"
        assert data["classifications"][1]["update_method"] == "batch"

    def test_database_url_password_masked(self):
        """Database URL in report should have password masked."""
        report = self._make_mock_report()
        assert "***" in report.database_url
        assert "password" not in report.database_url.lower()


# ── 6. S1 layer isolation (no S2+ imports) ──────────────────────────────


class TestLayerIsolation:
    """Verify source_audit.py has zero imports from S2 or higher layers."""

    FILE_PATH = pathlib.Path(__file__).resolve().parent.parent / "src" / "market" / "data" / "source_audit.py"

    FORBIDDEN_PREFIXES = [
        "market.analysis",
        "market.mlops",
        "market.risk",
        "market.execution",
        "market.multi_asset",
        "market.backtest",
        "market.autonomous",
        "market.social",
        "market.pipelines",
        "market.scheduler",
        "market.core",
        "market.api",
        "market.cli",
        "market.security",
    ]

    def test_no_s2_plus_imports(self):
        """source_audit.py must not import from any S2+ package."""
        source = self.FILE_PATH.read_text()
        tree = ast.parse(source)

        violations: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for prefix in self.FORBIDDEN_PREFIXES:
                    if module.startswith(prefix):
                        violations.append(f"line {node.lineno}: from {module} import ...")

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    for prefix in self.FORBIDDEN_PREFIXES:
                        if mod.startswith(prefix):
                            violations.append(f"line {node.lineno}: import {mod}")

        assert not violations, (
            f"S2+ import violations found in source_audit.py:\n"
            + "\n".join(violations)
        )

    def test_only_s0_s1_imports(self):
        """source_audit.py should only import from S0 (config/paths/compute) and S1 (db/data)."""
        source = self.FILE_PATH.read_text()
        tree = ast.parse(source)

        allowed_prefixes = [
            "market.config",
            "market.paths",
            "market.compute",
            "market.db",
            "market.data",
        ]

        market_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("market."):
                    market_imports.append(module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("market."):
                        market_imports.append(alias.name)

        for imp in market_imports:
            is_allowed = any(imp.startswith(p) for p in allowed_prefixes)
            assert is_allowed, f"Non-S0/S1 import: {imp}"

    def test_no_string_based_s2_imports(self):
        """Check that no dynamic imports (importlib) reference S2+ modules."""
        source = self.FILE_PATH.read_text()
        for prefix in self.FORBIDDEN_PREFIXES:
            short = prefix.split(".")[-1]
            # Check for string literals containing the package name in import context
            if f'"{prefix}' in source or f"'{prefix}" in source:
                pytest.fail(f"Found dynamic import reference to {prefix} in source")
