"""Comprehensive tests for scheduler_tasks.py — event emitters & DB-heavy tasks.

Tests cover:
- Simple event emitter tasks (health_check, fetch_eod, fetch_global, etc.)
- _task_fetch_intraday with market open/closed mocking
- _task_feature_store with DB mocking
- _task_drift_detection with DB mocking
- _task_generate_reports with DB mocking
- _task_startup_catchup with DB mocking
- Subprocess-based tasks (weekly_hrp, weekly_drift, backup, track_kpi, scrape_news, etc.)
- _task_macro_correlation_analysis with DB mocking
- _task_compute_astronacci_cycles with DB mocking
- _task_fetch_fundamental with yfinance mocking
- _task_strategy_assignment with DB mocking
- register_default_tasks schedule correctness
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from market.core.events import broker
from market.scheduler import DailyScheduler
from market.scheduler_tasks import (
    INTRADAY_TICKER_MIC,
    _task_backup_postgresql,
    _task_compute_astronacci_cycles,
    _task_drift_detection,
    _task_export_parquet,
    _task_feature_store,
    _task_fetch_eod,
    _task_fetch_fundamental,
    _task_fetch_global,
    _task_fetch_intraday,
    _task_fetch_macro,
    _task_fetch_macro_fred,
    _task_fetch_macroeconomic_indicators,
    _task_fetch_fundamental_quarterly,
    _task_fetch_satellite,
    _task_generate_reports,
    _task_generate_signals,
    _task_health_check,
    _task_macro_correlation_analysis,
    _task_quality_check,
    _task_recompute,
    _task_scrape_news,
    _task_startup_catchup,
    _task_strategy_assignment,
    _task_track_kpi,
    _task_weekly_drift_check,
    _task_weekly_hrp_recompute,
    register_default_tasks,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _capture_event(event_name: str) -> list:
    """Subscribe to event_name and capture emitted events."""
    captured = []
    handler = lambda e: captured.append(e)
    broker.subscribe(event_name, handler)
    return captured


def _make_mock_session():
    """Create a mock SQLAlchemy session."""
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    session.execute.return_value.fetchone.return_value = None
    session.execute.return_value.scalar.return_value = None
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.connection.return_value = MagicMock()
    return session


# ── Simple event emitter tasks ────────────────────────────────────────────


class TestEventEmitterTasks:
    """Test that simple tasks emit the correct events."""

    def test_health_check_emits(self):
        captured = _capture_event("health.check.requested")
        _task_health_check()
        assert len(captured) == 1
        assert captured[0].name == "health.check.requested"

    def test_fetch_eod_emits(self):
        captured = _capture_event("data.fetch.requested")
        _task_fetch_eod()
        assert len(captured) >= 1
        assert captured[-1].payload.get("source") == "eod"

    def test_fetch_global_emits(self):
        captured = _capture_event("data.fetch_global.requested")
        _task_fetch_global()
        assert len(captured) >= 1
        assert captured[-1].payload.get("source") == "global"

    def test_fetch_macro_emits(self):
        captured = _capture_event("data.fetch_macro.requested")
        _task_fetch_macro()
        assert len(captured) >= 1
        assert captured[-1].payload.get("source") == "macro"

    def test_quality_check_emits(self):
        captured = _capture_event("health.check.requested")
        _task_quality_check()
        assert len(captured) >= 1
        assert captured[-1].payload.get("source") == "quality_check"

    def test_recompute_emits(self):
        captured = _capture_event("data.recompute.requested")
        _task_recompute()
        assert len(captured) >= 1
        assert captured[-1].payload.get("incremental") is True

    def test_generate_signals_emits(self):
        captured = _capture_event("signal.generate.requested")
        _task_generate_signals()
        assert len(captured) >= 1
        assert captured[-1].payload.get("dry_run") is False

    def test_export_parquet_emits(self):
        captured = _capture_event("data.export.requested")
        _task_export_parquet()
        assert len(captured) >= 1


# ── Intraday fetch task ───────────────────────────────────────────────────


class TestFetchIntraday:
    """Test _task_fetch_intraday with market open/closed scenarios."""

    def test_all_markets_closed_skips(self):
        with patch("market.data.timestamp_validation.is_market_open", return_value=False):
            captured = _capture_event("data.fetch.intraday.requested")
            _task_fetch_intraday()
            assert len(captured) == 0

    def test_some_markets_open_emits(self):
        def mock_open(mic):
            return mic in ("XIDX", "XNYS")

        with patch("market.data.timestamp_validation.is_market_open", side_effect=mock_open):
            captured = _capture_event("data.fetch.intraday.requested")
            _task_fetch_intraday()
            assert len(captured) >= 1
            tickers = captured[-1].payload.get("tickers", [])
            assert "^JKSE" in tickers
            assert "^GSPC" in tickers

    def test_intraday_ticker_mic_dict_not_empty(self):
        assert len(INTRADAY_TICKER_MIC) >= 10
        assert "^JKSE" in INTRADAY_TICKER_MIC
        assert INTRADAY_TICKER_MIC["^JKSE"] == "XIDX"


# ── Feature store task ────────────────────────────────────────────────────


class TestFeatureStore:
    """Test _task_feature_store with mocked DB."""

    def test_no_tickers_found(self):
        mock_session = _make_mock_session()
        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            _task_feature_store()
            mock_session.close.assert_called_once()

    def test_with_tickers_but_insufficient_data(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.fetchall.return_value = [("BBCA.JK",)]
        import pandas as pd
        mock_session.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=[("BBCA.JK",)])),
        ]
        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("pandas.read_sql", return_value=pd.DataFrame()):
                _task_feature_store()
                mock_session.close.assert_called_once()


# ── Drift detection task ──────────────────────────────────────────────────


class TestDriftDetection:
    """Test _task_drift_detection with mocked DB."""

    def test_insufficient_recent_predictions(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.fetchall.return_value = []  # 0 rows

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            _task_drift_detection()
            mock_session.close.assert_called_once()

    def test_with_enough_data_no_drift(self):
        mock_session = _make_mock_session()
        recent_rows = [("BBCA.JK", 0.5, 0.8, "up", datetime.now(UTC))] * 25
        baseline_rows = [("BBCA.JK", 0.3, 0.7, "up", datetime.now(UTC) - timedelta(days=60))] * 25

        # Need to handle two queries: recent and baseline
        results = [MagicMock(fetchall=MagicMock(return_value=recent_rows)),
                    MagicMock(fetchall=MagicMock(return_value=baseline_rows))]
        mock_session.execute.side_effect = results

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            _task_drift_detection()
            mock_session.close.assert_called()


# ── Generate reports task ─────────────────────────────────────────────────


class TestGenerateReports:
    """Test _task_generate_reports with mocked DB."""

    def test_no_scores_found(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.fetchall.return_value = []

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            _task_generate_reports()
            mock_session.close.assert_called_once()

    def test_with_scores_and_report(self):
        mock_session = _make_mock_session()
        scores = [("BBCA.JK", "technical", 75.0, "{}", datetime.now(UTC))]
        mock_session.execute.return_value.fetchall.return_value = scores
        mock_session.execute.return_value.fetchone.return_value = (50.0,)

        mock_report = MagicMock()
        mock_report.summary = "Test report"
        mock_report.date = "2026-08-17"
        mock_report.market_regime = "Neutral"
        mock_report.screened = 1
        mock_report.passed = 1
        mock_report.top_picks = []

        mock_engine = MagicMock()
        mock_engine.generate_report.return_value = mock_report

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.analysis.advisory.AdvisoryEngine", return_value=mock_engine):
                _task_generate_reports()
                mock_session.close.assert_called()


# ── Startup catchup task ──────────────────────────────────────────────────


class TestStartupCatchup:
    """Test _task_startup_catchup with mocked DB."""

    def test_no_ohlcv_data_triggers_fetch(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.scalar.return_value = None

        fetch_captured = _capture_event("data.fetch.requested")
        recompute_captured = _capture_event("data.recompute.requested")
        export_captured = _capture_event("data.export.requested")

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.config.settings") as mock_settings:
                mock_settings.db_backend = "postgresql"
                _task_startup_catchup()
                mock_session.close.assert_called_once()

        assert len(fetch_captured) >= 1
        assert len(recompute_captured) >= 1
        assert len(export_captured) >= 1

    def test_fresh_data_no_action(self):
        mock_session = _make_mock_session()
        recent_time = datetime.now(UTC) - timedelta(hours=2)
        mock_session.execute.return_value.scalar.return_value = recent_time

        fetch_captured = _capture_event("data.fetch.requested")

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.config.settings") as mock_settings:
                mock_settings.db_backend = "postgresql"
                _task_startup_catchup()
                mock_session.close.assert_called_once()

        # Should NOT emit fetch events when data is fresh
        new_events = [e for e in fetch_captured if e.payload.get("source") == "startup_catchup"]
        assert len(new_events) == 0

    def test_stale_data_triggers_chain(self):
        mock_session = _make_mock_session()
        stale_time = datetime.now(UTC) - timedelta(hours=48)
        mock_session.execute.return_value.scalar.return_value = stale_time

        fetch_captured = _capture_event("data.fetch.requested")

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.config.settings") as mock_settings:
                mock_settings.db_backend = "postgresql"
                _task_startup_catchup()
                mock_session.close.assert_called_once()

        startup_events = [e for e in fetch_captured if e.payload.get("source") == "startup_catchup"]
        assert len(startup_events) >= 1


# ── Subprocess-based tasks ────────────────────────────────────────────────


class TestSubprocessTasks:
    """Test subprocess-based tasks with mocked subprocess.run."""

    def test_weekly_hrp_script_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            _task_weekly_hrp_recompute()  # Should log warning and return

    def test_weekly_hrp_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                _task_weekly_hrp_recompute()

    def test_weekly_hrp_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                _task_weekly_hrp_recompute()

    def test_weekly_drift_check_script_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            _task_weekly_drift_check()

    def test_weekly_drift_check_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                _task_weekly_drift_check()

    def test_weekly_drift_check_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                _task_weekly_drift_check()

    def test_backup_postgresql_script_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            _task_backup_postgresql()

    def test_backup_postgresql_not_pg_url(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch.dict("os.environ", {"DATABASE_URL": "sqlite:///test.db"}):
                _task_backup_postgresql()

    def test_backup_postgresql_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "backup done"
        mock_result.stderr = ""

        with patch("pathlib.Path.exists", return_value=True):
            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost/db"}):
                with patch("subprocess.run", return_value=mock_result):
                    _task_backup_postgresql()

    def test_backup_postgresql_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "backup failed"

        with patch("pathlib.Path.exists", return_value=True):
            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost/db"}):
                with patch("subprocess.run", return_value=mock_result):
                    _task_backup_postgresql()

    def test_backup_postgresql_timeout(self):
        import subprocess as sp

        with patch("pathlib.Path.exists", return_value=True):
            with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost/db"}):
                with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="backup", timeout=1800)):
                    _task_backup_postgresql()

    def test_track_kpi_script_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            _task_track_kpi()

    def test_track_kpi_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "kpi done"
        mock_result.stderr = ""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                _task_track_kpi()

    def test_track_kpi_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "kpi error"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                _task_track_kpi()

    def test_track_kpi_timeout(self):
        import subprocess as sp

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="track_kpi", timeout=600)):
                _task_track_kpi()

    def test_scrape_news_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            _task_scrape_news()

    def test_scrape_news_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            _task_scrape_news()

    def test_scrape_news_timeout(self):
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="scrape", timeout=300)):
            _task_scrape_news()

    def test_fetch_fundamental_quarterly_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done\nline2\nline3"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_fundamental_quarterly()

    def test_fetch_fundamental_quarterly_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_fundamental_quarterly()

    def test_fetch_fundamental_quarterly_timeout(self):
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="fq", timeout=3600)):
            _task_fetch_fundamental_quarterly()

    def test_fetch_macro_fred_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_macro_fred()

    def test_fetch_macro_fred_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_macro_fred()

    def test_fetch_macro_fred_timeout(self):
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="fred", timeout=600)):
            _task_fetch_macro_fred()

    def test_fetch_macroeconomic_indicators_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_macroeconomic_indicators()

    def test_fetch_macroeconomic_indicators_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_macroeconomic_indicators()

    def test_fetch_macroeconomic_indicators_timeout(self):
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="mei", timeout=600)):
            _task_fetch_macroeconomic_indicators()

    def test_fetch_satellite_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_satellite()

    def test_fetch_satellite_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            _task_fetch_satellite()

    def test_fetch_satellite_timeout(self):
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="sat", timeout=1800)):
            _task_fetch_satellite()


# ── Macro correlation analysis ────────────────────────────────────────────


class TestMacroCorrelation:
    """Test _task_macro_correlation_analysis with mocked DB."""

    def test_no_tickers_fallback(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.fetchall.return_value = []
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.analysis.macro_correlation.full_analysis", side_effect=Exception("no data")):
                _task_macro_correlation_analysis()
                mock_session.close.assert_called_once()

    def test_with_tickers_and_results(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.scalars.return_value.all.return_value = ["BBCA.JK"]

        mock_report = {
            "event_study": {"n_events": 3, "mean_forward_return_pct": 1.5},
            "granger_causality": {"is_significant": True, "p_value": 0.04},
        }

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.analysis.macro_correlation.full_analysis", return_value=mock_report):
                _task_macro_correlation_analysis()
                mock_session.close.assert_called_once()


# ── Astronacci cycles ─────────────────────────────────────────────────────


class TestAstronacciCycles:
    """Test _task_compute_astronacci_cycles with mocked engine and DB."""

    def test_computation_failure_returns_early(self):
        with patch("market.analysis.astronacci.AstronacciEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.compute_cycles.side_effect = Exception("ephem error")
            mock_engine_cls.return_value = mock_engine

            _task_compute_astronacci_cycles()

    def test_successful_computation(self):
        mock_cycle = MagicMock()
        mock_cycle.cycle_type = "MOON_PHASE"
        mock_cycle.title = "Full Moon"
        mock_cycle.start_at = datetime.now(UTC)
        mock_cycle.end_at = datetime.now(UTC) + timedelta(days=3)
        mock_cycle.potential_impact = "MEDIUM"
        mock_cycle.target_asset_class = "ALL"
        mock_cycle.expected_reversal = "NEUTRAL"
        mock_cycle.description = "Full moon cycle"

        with patch("market.analysis.astronacci.AstronacciEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.compute_cycles.return_value = [mock_cycle]
            mock_engine_cls.return_value = mock_engine

            mock_session = _make_mock_session()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = 1
            mock_session.execute.return_value = mock_result

            with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
                _task_compute_astronacci_cycles()
                mock_session.commit.assert_called_once()
                mock_session.close.assert_called_once()

    def test_persistence_failure(self):
        mock_cycle = MagicMock()
        mock_cycle.cycle_type = "RETROGRADE"
        mock_cycle.title = "Mercury Retrograde"
        mock_cycle.start_at = datetime.now(UTC)
        mock_cycle.end_at = datetime.now(UTC) + timedelta(days=20)
        mock_cycle.potential_impact = "HIGH"
        mock_cycle.target_asset_class = "ALL"
        mock_cycle.expected_reversal = "BEARISH"
        mock_cycle.description = "Mercury retrograde"

        with patch("market.analysis.astronacci.AstronacciEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.compute_cycles.return_value = [mock_cycle]
            mock_engine_cls.return_value = mock_engine

            mock_session = _make_mock_session()
            mock_session.execute.side_effect = Exception("DB error")

            with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
                _task_compute_astronacci_cycles()
                mock_session.rollback.assert_called_once()
                mock_session.close.assert_called_once()


# ── Fetch fundamental ─────────────────────────────────────────────────────


class TestFetchFundamental:
    """Test _task_fetch_fundamental with mocked yfinance and DB."""

    def test_no_tickers(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.fetchall.return_value = []

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.data.ticker_util.to_yf_ticker", return_value="BBCA.JK"):
                _task_fetch_fundamental()
                mock_session.close.assert_called_once()

    def test_with_tickers_and_info(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.fetchall.return_value = [("BBCA.JK",)]
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        mock_yf_ticker = MagicMock()
        mock_yf_ticker.info = {
            "trailingPE": 15.5,
            "priceToBook": 2.1,
            "returnOnEquity": 0.18,
            "marketCap": 1000000000000,
        }

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            with patch("market.data.ticker_util.to_yf_ticker", return_value="BBCA.JK"):
                with patch("yfinance.Ticker", return_value=mock_yf_ticker):
                    _task_fetch_fundamental()
                    mock_session.close.assert_called_once()


# ── Strategy assignment ───────────────────────────────────────────────────


class TestStrategyAssignment:
    """Test _task_strategy_assignment with mocked DB."""

    def test_no_tickers(self):
        mock_session = _make_mock_session()
        mock_session.execute.return_value.fetchall.return_value = []

        with patch("market.db.engine.get_sessionmaker", return_value=lambda: mock_session):
            _task_strategy_assignment()
            mock_session.close.assert_called_once()


# ── Register default tasks ────────────────────────────────────────────────


class TestRegisterDefaultTasksExtended:
    """Extended tests for register_default_tasks beyond existing tests."""

    def test_all_tasks_have_unique_ids(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        ids = [t.task_id for t in sched.tasks]
        assert len(ids) == len(set(ids))

    def test_all_tasks_have_non_empty_names(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        for t in sched.tasks:
            assert t.name, f"Task {t.task_id} has empty name"

    def test_all_tasks_have_valid_time_format(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        for t in sched.tasks:
            parts = t.time_of_day.split(":")
            assert len(parts) == 2, f"Task {t.task_id} has invalid time: {t.time_of_day}"
            hour, minute = int(parts[0]), int(parts[1])
            assert 0 <= hour <= 23
            assert 0 <= minute <= 59

    def test_all_tasks_have_callable_func(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        for t in sched.tasks:
            assert callable(t.func), f"Task {t.task_id} func is not callable"

    def test_schedule_types_valid(self):
        valid_schedules = {"daily", "weekly", "monthly", "hourly", "EOD", "every_15min"}
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        for t in sched.tasks:
            assert t.schedule in valid_schedules, f"Task {t.task_id} has unknown schedule: {t.schedule}"

    def test_get_task_returns_registered(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        task = sched.get_task("fetch_eod")
        assert task is not None
        assert task.task_id == "fetch_eod"

    def test_unregister_task(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        assert sched.unregister_task("fetch_eod") is True
        assert sched.get_task("fetch_eod") is None
        assert sched.unregister_task("nonexistent") is False

    def test_enable_disable_task(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        assert sched.disable_task("fetch_eod") is True
        assert not sched.get_task("fetch_eod").enabled
        assert sched.enable_task("fetch_eod") is True
        assert sched.get_task("fetch_eod").enabled
        assert sched.disable_task("nonexistent") is False
        assert sched.enable_task("nonexistent") is False

    def test_run_nonexistent_task_returns_none(self):
        sched = DailyScheduler(persist=False)
        assert sched.run_task("nonexistent") is None

    def test_executions_property(self):
        sched = DailyScheduler(persist=False)
        register_default_tasks(sched)
        sched.run_task("health_check")
        assert len(sched.executions) == 1
        assert sched.executions[0].task_id == "health_check"
