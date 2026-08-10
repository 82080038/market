"""Tests for overnight_strategy_mining — Trade Ideas Mode.

Tests macro regime assessment, Donchian signal generation, parameter optimization,
and config update logic.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Add scripts dir to path
import sys
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from overnight_strategy_mining import (
    assess_macro_regime,
    compute_max_drawdown,
    compute_sharpe,
    generate_donchian_signals,
    insert_overnight_notification,
    optimize_donchian_with_lightgbm,
    simulate_returns,
    update_config,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def sample_ohlcv() -> pd.DataFrame:
    """100 days of mock OHLCV data with trend."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 1000 + np.cumsum(np.random.randn(100) * 5 + 0.5)
    high = close + np.abs(np.random.randn(100) * 3)
    low = close - np.abs(np.random.randn(100) * 3)
    volume = np.random.randint(100000, 500000, 100).astype(float)
    return pd.DataFrame({
        "open": close, "high": high, "low": low, "close": close, "volume": volume,
    }, index=dates)


@pytest.fixture()
def global_data_risk_on() -> dict:
    return {
        "^VIX": {"close": 15.0, "daily_return": -0.03, "date": "2024-01-01"},
        "^GSPC": {"close": 4800, "daily_return": 0.008, "date": "2024-01-01"},
        "CL=F": {"close": 72.0, "daily_return": 0.01, "date": "2024-01-01"},
        "MTF=F": {"close": 3500, "daily_return": 0.005, "date": "2024-01-01"},
    }


@pytest.fixture()
def global_data_risk_off() -> dict:
    return {
        "^VIX": {"close": 28.0, "daily_return": 0.05, "date": "2024-01-01"},
        "^GSPC": {"close": 4700, "daily_return": -0.015, "date": "2024-01-01"},
        "CL=F": {"close": 68.0, "daily_return": -0.03, "date": "2024-01-01"},
        "MTF=F": {"close": 3400, "daily_return": -0.02, "date": "2024-01-01"},
    }


# ── Macro Regime Tests ──────────────────────────────────────────────────────


class TestMacroRegime:
    def test_risk_on(self, global_data_risk_on):
        result = assess_macro_regime(global_data_risk_on)
        assert result["regime"] == "risk_on"
        assert result["vix_level"] == 15.0
        assert result["risk_off_signals"] == 0

    def test_risk_off(self, global_data_risk_off):
        result = assess_macro_regime(global_data_risk_off)
        assert result["regime"] == "risk_off"
        assert result["risk_off_signals"] >= 2

    def test_neutral(self):
        data = {
            "^VIX": {"close": 20.0, "daily_return": 0.0},
            "^GSPC": {"close": 4800, "daily_return": -0.005},
            "CL=F": {"close": 72.0, "daily_return": 0.0},
            "MTF=F": {"close": 3500, "daily_return": 0.0},
        }
        result = assess_macro_regime(data)
        assert result["regime"] == "neutral"

    def test_empty_data(self):
        result = assess_macro_regime({})
        # VIX defaults to 20, no risk-off signals, S&P return 0 → neutral
        assert result["regime"] in ("neutral", "risk_on")


# ── Donchian Signal Tests ───────────────────────────────────────────────────


class TestDonchianSignals:
    def test_signal_values(self, sample_ohlcv):
        """Signals should be in {-1, 0, 1}."""
        signals = generate_donchian_signals(sample_ohlcv, period=20)
        assert set(signals.unique()).issubset({-1, 0, 1})

    def test_signal_length(self, sample_ohlcv):
        """Signal length should match OHLCV length."""
        signals = generate_donchian_signals(sample_ohlcv, period=10)
        assert len(signals) == len(sample_ohlcv)

    def test_breakout_signal(self):
        """When close breaks above upper channel, signal should be 1."""
        dates = pd.date_range("2024-01-01", periods=25, freq="D")
        close = pd.Series([100] * 20 + [100, 101, 102, 103, 110], index=dates)
        high = close + 1
        low = close - 1
        ohlcv = pd.DataFrame({"high": high, "low": low, "close": close})
        signals = generate_donchian_signals(ohlcv, period=10)
        # After breakout, signal should become 1
        assert signals.iloc[-1] == 1

    def test_no_breakout(self):
        """When price stays in range, signal should be 0 or persist."""
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        close = pd.Series([100] * 30, index=dates)
        high = close + 1
        low = close - 1
        ohlcv = pd.DataFrame({"high": high, "low": low, "close": close})
        signals = generate_donchian_signals(ohlcv, period=10)
        # No breakout → all zeros
        assert (signals == 0).all()


# ── Strategy Simulation Tests ───────────────────────────────────────────────


class TestSimulateReturns:
    def test_returns_not_empty(self, sample_ohlcv):
        signals = generate_donchian_signals(sample_ohlcv, period=20)
        returns = simulate_returns(sample_ohlcv, signals)
        assert not returns.empty

    def test_cost_applied(self, sample_ohlcv):
        """Cost should reduce returns when signal changes."""
        signals = generate_donchian_signals(sample_ohlcv, period=20)
        returns_no_cost = simulate_returns(sample_ohlcv, signals, cost_per_trade=0.0)
        returns_with_cost = simulate_returns(sample_ohlcv, signals, cost_per_trade=0.01)
        # With cost, cumulative return should be lower
        assert (1 + returns_with_cost).cumprod().iloc[-1] <= (1 + returns_no_cost).cumprod().iloc[-1]


class TestMaxDrawdown:
    def test_positive_returns(self):
        """All positive returns → no drawdown."""
        returns = pd.Series([0.01, 0.02, 0.01, 0.03])
        dd = compute_max_drawdown(returns)
        assert dd == 0.0

    def test_with_drawdown(self):
        """Drawdown after a peak."""
        returns = pd.Series([0.05, -0.10, -0.05, 0.02])
        dd = compute_max_drawdown(returns)
        assert dd < 0.0

    def test_empty(self):
        assert compute_max_drawdown(pd.Series([])) == 0.0


class TestSharpe:
    def test_positive_sharpe(self):
        returns = pd.Series([0.01] * 100 + [0.0] * 50)
        sharpe = compute_sharpe(returns)
        assert sharpe > 0.0

    def test_zero_volatility(self):
        returns = pd.Series([0.0] * 100)
        sharpe = compute_sharpe(returns)
        assert sharpe == 0.0


# ── Optimization Tests ──────────────────────────────────────────────────────


class TestOptimizeDonchian:
    def test_returns_best_period(self, sample_ohlcv):
        """Optimization should return a best_period in the tested range."""
        result = optimize_donchian_with_lightgbm(sample_ohlcv, "neutral")
        assert result["best_period"] in range(10, 26)
        assert "all_results" in result
        assert len(result["all_results"]) > 0

    def test_all_results_have_metrics(self, sample_ohlcv):
        """Each result should have period, max_drawdown, sharpe."""
        result = optimize_donchian_with_lightgbm(sample_ohlcv, "risk_on")
        for r in result["all_results"]:
            assert "period" in r
            assert "max_drawdown" in r
            assert "sharpe" in r

    def test_insufficient_data(self):
        """Too few rows → default period 20."""
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        ohlcv = pd.DataFrame({
            "high": [100] * 30, "low": [99] * 30,
            "close": [100] * 30, "volume": [1000.0] * 30,
        }, index=dates)
        result = optimize_donchian_with_lightgbm(ohlcv, "neutral")
        assert result["best_period"] == 20

    def test_regime_affects_selection(self, sample_ohlcv):
        """Different regimes may select different best periods."""
        result_risk_on = optimize_donchian_with_lightgbm(sample_ohlcv, "risk_on")
        result_risk_off = optimize_donchian_with_lightgbm(sample_ohlcv, "risk_off")
        # Both should return valid results
        assert result_risk_on["best_period"] in range(10, 26)
        assert result_risk_off["best_period"] in range(10, 26)


# ── Config Update Tests ─────────────────────────────────────────────────────


class TestUpdateConfig:
    def test_creates_new_config(self, tmp_path):
        """Should create config file if it doesn't exist."""
        config_path = str(tmp_path / "test_config.json")
        macro = {"regime": "risk_on", "vix_level": 15.0}
        opt = {"best_period": 15, "best_max_dd": -0.05, "best_sharpe": 1.2,
               "best_win_rate": 0.55, "best_lgb_score": 0.3, "all_results": []}
        update_config(config_path, 15, macro, opt)
        with open(config_path) as f:
            config = json.load(f)
        assert "overnight_strategy" in config
        assert config["overnight_strategy"]["best_donchian_period"] == 15
        assert "^JKSE" in config["tickers"]

    def test_updates_existing_config(self, tmp_path):
        """Should update existing config without losing data."""
        config_path = str(tmp_path / "test_config.json")
        # Write initial config
        with open(config_path, "w") as f:
            json.dump({"tickers": {"BBCA.JK": {"strategy": "donchian"}}, "pipeline": "v1"}, f)
        macro = {"regime": "risk_off", "vix_level": 28.0}
        opt = {"best_period": 20, "best_max_dd": -0.08, "best_sharpe": 0.5,
               "best_win_rate": 0.48, "best_lgb_score": 0.1, "all_results": []}
        update_config(config_path, 20, macro, opt)
        with open(config_path) as f:
            config = json.load(f)
        assert config["pipeline"] == "v1"  # preserved
        assert "BBCA.JK" in config["tickers"]  # preserved
        assert config["overnight_strategy"]["best_donchian_period"] == 20
        assert config["tickers"]["^JKSE"]["donchian_period"] == 20


# ── Notification Tests ──────────────────────────────────────────────────────


class TestNotification:
    def test_insert_notification(self, tmp_path):
        """Should insert notification into app_notifications table."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE app_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                title TEXT NOT NULL,
                body_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'UNREAD'
            )
        """)
        conn.commit()

        macro = {"regime": "risk_on", "vix_level": 15.0}
        opt = {"best_period": 15, "best_max_dd": -0.05, "best_sharpe": 1.2,
               "best_win_rate": 0.55, "best_lgb_score": 0.3, "all_results": []}
        notif_id = insert_overnight_notification(conn, macro, opt)
        assert notif_id > 0

        # Verify
        row = conn.execute("SELECT title, status FROM app_notifications WHERE id = ?", (notif_id,)).fetchone()
        assert row is not None
        assert "Overnight Strategy Mining" in row[0]
        assert row[1] == "UNREAD"
        conn.close()
