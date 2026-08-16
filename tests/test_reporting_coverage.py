"""Comprehensive tests for social/reporting.py — PDF, performance_report, generate dispatch, edge cases."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from market.social.reporting import (
    ReportConfig,
    ReportFormat,
    ReportResult,
    ReportType,
    ReportingEngine,
)


# ── PDF generation tests ──────────────────────────────────────────────────


class TestPDFGeneration:
    """Test generate_pdf and generate with PDF format."""

    def test_pdf_with_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [
                {"ticker": "BBCA", "shares": 100, "value": 750000},
                {"ticker": "TLKM", "shares": 200, "value": 640000},
            ]
            result = engine.generate_pdf(data, "Test PDF Report", filename="test_report")
            assert result.format == ReportFormat.PDF
            assert result.rows == 2
            assert result.file_path is not None
            assert result.file_path.endswith(".pdf")
            assert result.content is not None
            assert len(result.content) > 0

    def test_pdf_with_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [{"col1": "a", "col2": "b"}]
            result = engine.generate_pdf(data, "Summary Test", summary="This is a summary")
            assert result.format == ReportFormat.PDF
            assert result.rows == 1
            assert result.content is not None

    def test_pdf_no_filename(self):
        engine = ReportingEngine()
        data = [{"x": 1}]
        result = engine.generate_pdf(data, "No File PDF")
        assert result.format == ReportFormat.PDF
        assert result.file_path is None
        assert result.content is not None

    def test_pdf_empty_data(self):
        engine = ReportingEngine()
        result = engine.generate_pdf([], "Empty PDF")
        assert result.format == ReportFormat.PDF
        assert result.error == "No data to export"
        assert result.rows == 0

    def test_generate_with_pdf_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [{"a": 1, "b": 2}]
            config = ReportConfig(
                report_type=ReportType.CUSTOM,
                title="Custom PDF",
                format=ReportFormat.PDF,
            )
            result = engine.generate(data, config, filename="custom_pdf")
            assert result.format == ReportFormat.PDF
            assert result.rows == 1


# ── Performance report tests ──────────────────────────────────────────────


class TestPerformanceReport:
    """Test performance_report method."""

    def test_performance_report_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [
                {"date": "2026-01-01", "return_pct": 1.5, "sharpe": 0.8},
                {"date": "2026-01-02", "return_pct": -0.3, "sharpe": 0.7},
            ]
            result = engine.performance_report(data, format=ReportFormat.CSV)
            assert result.format == ReportFormat.CSV
            assert result.rows == 2
            assert result.file_path is not None
            assert "performance" in result.file_path

    def test_performance_report_excel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [{"date": "2026-01-01", "return_pct": 1.5}]
            result = engine.performance_report(data, format=ReportFormat.EXCEL)
            assert result.rows == 1

    def test_performance_report_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [{"date": "2026-01-01", "return_pct": 1.5}]
            result = engine.performance_report(data, format=ReportFormat.PDF)
            assert result.format == ReportFormat.PDF
            assert result.rows == 1

    def test_performance_report_json(self):
        engine = ReportingEngine()
        data = [{"date": "2026-01-01", "return_pct": 1.5}]
        result = engine.performance_report(data, format=ReportFormat.JSON)
        assert result.report_type == ReportType.PERFORMANCE
        assert result.format == ReportFormat.JSON
        assert result.rows == 1
        assert result.content is not None
        parsed = json.loads(result.content)
        assert len(parsed) == 1

    def test_performance_report_empty(self):
        engine = ReportingEngine()
        result = engine.performance_report([], format=ReportFormat.CSV)
        assert result.error == "No data to export"
        assert result.rows == 0


# ── Generate dispatch tests ───────────────────────────────────────────────


class TestGenerateDispatch:
    """Test generate() method dispatching to correct format."""

    def test_generate_csv_with_config_title(self):
        engine = ReportingEngine()
        data = [{"a": 1}]
        config = ReportConfig(
            report_type=ReportType.TRADE_HISTORY,
            title="",  # Empty title → should use report_type fallback
            format=ReportFormat.CSV,
        )
        result = engine.generate(data, config)
        assert result.title == "Trade History"  # report_type.value.replace("_", " ").title()

    def test_generate_excel_with_config_title(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [{"a": 1, "b": 2}]
            config = ReportConfig(
                report_type=ReportType.RISK_ANALYSIS,
                title="Custom Risk Title",
                format=ReportFormat.EXCEL,
            )
            result = engine.generate(data, config, filename="risk_report")
            assert result.title == "Custom Risk Title"
            assert result.format == ReportFormat.EXCEL
            assert result.rows == 1

    def test_generate_json_with_config_title(self):
        engine = ReportingEngine()
        data = [{"a": 1}]
        config = ReportConfig(
            report_type=ReportType.TAX_SUMMARY,
            format=ReportFormat.JSON,
        )
        result = engine.generate(data, config)
        assert result.title == "Tax Summary"
        assert result.format == ReportFormat.JSON
        assert result.content is not None

    def test_generate_json_empty_data(self):
        engine = ReportingEngine()
        config = ReportConfig(
            report_type=ReportType.CUSTOM,
            format=ReportFormat.JSON,
        )
        result = engine.generate([], config)
        assert result.rows == 0
        assert result.content is not None
        parsed = json.loads(result.content)
        assert parsed == []


# ── Portfolio summary report with different formats ──────────────────────


class TestPortfolioSummaryFormats:
    """Test portfolio_summary_report with all formats."""

    def test_portfolio_summary_excel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            holdings = [{"ticker": "BBCA", "shares": 100, "value": 750000}]
            result = engine.portfolio_summary_report(holdings, format=ReportFormat.EXCEL)
            assert result.format == ReportFormat.EXCEL
            assert result.rows == 1

    def test_portfolio_summary_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            holdings = [{"ticker": "BBCA", "shares": 100, "value": 750000}]
            result = engine.portfolio_summary_report(holdings, format=ReportFormat.PDF)
            assert result.format == ReportFormat.PDF
            assert result.rows == 1

    def test_portfolio_summary_json(self):
        engine = ReportingEngine()
        holdings = [{"ticker": "BBCA", "shares": 100, "value": 750000}]
        result = engine.portfolio_summary_report(holdings, format=ReportFormat.JSON)
        assert result.report_type == ReportType.PORTFOLIO_SUMMARY
        assert result.format == ReportFormat.JSON
        assert result.rows == 1


# ── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and fallback behavior."""

    def test_csv_with_filename_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [{"a": 1, "b": "hello"}]
            result = engine.generate_csv(data, "Test", filename="output")
            assert result.file_path is not None
            assert Path(result.file_path).exists()
            content = Path(result.file_path).read_bytes()
            assert b"a,b" in content

    def test_excel_with_filename_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ReportingEngine(output_dir=tmpdir)
            data = [{"a": 1, "b": "hello"}]
            result = engine.generate_excel(data, "Test", filename="output")
            assert result.file_path is not None
            assert Path(result.file_path).exists()

    def test_excel_empty_data(self):
        engine = ReportingEngine()
        result = engine.generate_excel([], "Empty Excel")
        assert result.format == ReportFormat.EXCEL
        assert result.error == "No data to export"

    def test_csv_no_filename_no_file(self):
        engine = ReportingEngine()
        data = [{"a": 1}]
        result = engine.generate_csv(data, "No File CSV")
        assert result.file_path is None
        assert result.content is not None

    def test_report_counter_increments(self):
        engine = ReportingEngine()
        data = [{"a": 1}]
        r1 = engine.generate_csv(data, "R1")
        r2 = engine.generate_csv(data, "R2")
        r3 = engine.generate_csv(data, "R3")
        assert r1.report_id != r2.report_id
        assert r2.report_id != r3.report_id
        assert r3.report_id > r1.report_id

    def test_report_result_defaults(self):
        result = ReportResult(
            report_id="RPT-001",
            report_type=ReportType.CUSTOM,
            format=ReportFormat.CSV,
            title="Test",
        )
        assert result.file_path is None
        assert result.content is None
        assert result.rows == 0
        assert result.error == ""
        assert result.generated_at != ""

    def test_report_config_defaults(self):
        config = ReportConfig(report_type=ReportType.PERFORMANCE)
        assert config.title == ""
        assert config.format == ReportFormat.CSV
        assert config.include_charts is True
        assert config.include_summary is True
        assert config.date_from == ""
        assert config.date_to == ""
        assert config.metadata == {}

    def test_default_output_dir(self):
        engine = ReportingEngine()
        assert str(engine._output_dir) == "/tmp/market_reports"
