"""Tests for execution_analyzer — Post-Trade Execution Analyzer.

Tests slippage calculation, net alpha attribution, and execution efficiency
metrics using mock transaction data.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from market.analysis.execution_analyzer import (
    ExecutionEfficiencyResult,
    NetAlphaResult,
    SlippageResult,
    compute_execution_efficiency,
    compute_net_alpha,
    compute_slippage,
    load_target_prices,
    load_transactions,
    run_full_analysis,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def sample_transactions() -> pd.DataFrame:
    """Mock transaction data with BUY and SELL trades."""
    return pd.DataFrame({
        "id_transaksi": [1, 2, 3, 4],
        "tanggal": pd.to_datetime(["2024-01-15", "2024-01-16", "2024-01-20", "2024-01-21"]),
        "ticker": ["BBCA.JK", "BBCA.JK", "BBRI.JK", "BBRI.JK"],
        "tipe": ["BUY", "SELL", "BUY", "SELL"],
        "jumlah_lot": [100, 100, 200, 200],
        "harga_per_saham": [8000.0, 8100.0, 4500.0, 4450.0],
        "biaya_broker": [1200.0, 1215.0, 1350.0, 1335.0],
        "pajak_pph_final": [0.0, 81.0, 0.0, 89.0],
        "status_eksekusi": ["FILLED", "FILLED", "FILLED", "FILLED"],
    })


@pytest.fixture()
def target_prices() -> dict[str, dict[str, float]]:
    """Mock target prices for slippage calculation."""
    return {
        "BBCA.JK": {"2024-01-15": 7980.0, "2024-01-16": 8120.0},
        "BBRI.JK": {"2024-01-20": 4510.0, "2024-01-21": 4460.0},
    }


# ── Slippage Tests ──────────────────────────────────────────────────────────


class TestComputeSlippage:
    def test_basic_slippage(self, sample_transactions, target_prices):
        """Slippage should be computed correctly for each transaction."""
        results = compute_slippage(sample_transactions, target_prices)
        assert len(results) == 4
        assert all(isinstance(r, SlippageResult) for r in results)

    def test_buy_slippage_positive(self, sample_transactions, target_prices):
        """BUY at higher price than target → positive slippage (unfavorable)."""
        results = compute_slippage(sample_transactions, target_prices)
        # BBCA.JK BUY: fill=8000, target=7980 → slippage=+20 IDR → +25 BPS
        bbca_buy = results[0]
        assert bbca_buy.ticker == "BBCA.JK"
        assert bbca_buy.tipe == "BUY"
        assert bbca_buy.slippage_idr > 0  # paid more than target
        assert bbca_buy.slippage_bps > 0

    def test_sell_slippage_positive(self, sample_transactions, target_prices):
        """SELL at lower price than target → positive slippage (unfavorable)."""
        results = compute_slippage(sample_transactions, target_prices)
        # BBCA.JK SELL: fill=8100, target=8120 → slippage=+20 (target - fill)
        bbca_sell = results[1]
        assert bbca_sell.tipe == "SELL"
        assert bbca_sell.slippage_bps > 0  # received less than target

    def test_slippage_total_idr(self, sample_transactions, target_prices):
        """slippage_total_idr = slippage_idr * shares (lot * 100)."""
        results = compute_slippage(sample_transactions, target_prices)
        r = results[0]
        expected = r.slippage_idr * r.jumlah_lot * 100
        assert abs(r.slippage_total_idr - expected) < 0.01

    def test_empty_transactions(self):
        """Empty DataFrame → empty results."""
        results = compute_slippage(pd.DataFrame())
        assert results == []

    def test_no_target_prices_uses_fallback(self, sample_transactions):
        """Without target prices, should use previous transaction price as fallback."""
        results = compute_slippage(sample_transactions, target_prices=None)
        assert len(results) == 4
        # First trade has no previous → slippage = 0
        assert results[0].slippage_bps == 0.0


# ── Net Alpha Tests ─────────────────────────────────────────────────────────


class TestComputeNetAlpha:
    def test_basic_net_alpha(self, sample_transactions):
        """Net alpha should compute gross, fees, tax, and net PnL."""
        result = compute_net_alpha(sample_transactions)
        assert isinstance(result, NetAlphaResult)
        assert result.n_trades == 4
        assert result.n_buy == 2
        assert result.n_sell == 2

    def test_gross_pnl(self, sample_transactions):
        """Gross PnL = SELL value - BUY value."""
        result = compute_net_alpha(sample_transactions)
        # BBCA: sell=8100*100*100, buy=8000*100*100
        # BBRI: sell=4450*200*100, buy=4500*200*100
        sell_value = 8100 * 10000 + 4450 * 20000
        buy_value = 8000 * 10000 + 4500 * 20000
        expected_gross = sell_value - buy_value
        assert abs(result.gross_pnl - expected_gross) < 1.0

    def test_broker_fees_total(self, sample_transactions):
        """Broker fees should sum all biaya_broker."""
        result = compute_net_alpha(sample_transactions)
        expected = 1200 + 1215 + 1350 + 1335
        assert abs(result.broker_fees_total - expected) < 0.01

    def test_pph_final_total(self, sample_transactions):
        """PPh Final should sum all pajak_pph_final (only on SELL)."""
        result = compute_net_alpha(sample_transactions)
        expected = 0 + 81 + 0 + 89
        assert abs(result.pph_final_total - expected) < 0.01

    def test_net_pnl(self, sample_transactions):
        """Net PnL = gross - fees - tax."""
        result = compute_net_alpha(sample_transactions)
        expected = result.gross_pnl - result.broker_fees_total - result.pph_final_total
        assert abs(result.net_pnl - expected) < 1.0

    def test_per_ticker_breakdown(self, sample_transactions):
        """Per-ticker breakdown should have entries for each ticker."""
        result = compute_net_alpha(sample_transactions)
        assert "BBCA.JK" in result.per_ticker
        assert "BBRI.JK" in result.per_ticker
        assert result.per_ticker["BBCA.JK"]["n_trades"] == 2

    def test_empty_transactions(self):
        """Empty DataFrame → zero result."""
        result = compute_net_alpha(pd.DataFrame())
        assert result.gross_pnl == 0.0
        assert result.n_trades == 0


# ── Execution Efficiency Tests ──────────────────────────────────────────────


class TestExecutionEfficiency:
    def test_basic_efficiency(self, sample_transactions, target_prices):
        """Execution efficiency should compute aggregate metrics."""
        slip = compute_slippage(sample_transactions, target_prices)
        eff = compute_execution_efficiency(slip, sample_transactions)
        assert isinstance(eff, ExecutionEfficiencyResult)
        assert eff.n_trades == 4
        assert eff.fill_rate == 1.0  # all FILLED

    def test_avg_slippage(self, sample_transactions, target_prices):
        """Average slippage should be mean of all BPS values."""
        slip = compute_slippage(sample_transactions, target_prices)
        eff = compute_execution_efficiency(slip, sample_transactions)
        expected = np.mean([r.slippage_bps for r in slip])
        assert abs(eff.avg_slippage_bps - expected) < 0.01

    def test_worst_and_best_slippage(self, sample_transactions, target_prices):
        """Worst = max BPS, Best = min BPS."""
        slip = compute_slippage(sample_transactions, target_prices)
        eff = compute_execution_efficiency(slip, sample_transactions)
        bps_values = [r.slippage_bps for r in slip]
        assert eff.worst_slippage_bps == max(bps_values)
        assert eff.best_slippage_bps == min(bps_values)

    def test_empty_results(self):
        """Empty slippage → zero efficiency."""
        eff = compute_execution_efficiency([], pd.DataFrame())
        assert eff.n_trades == 0
        assert eff.avg_slippage_bps == 0.0


# ── Integration Tests ───────────────────────────────────────────────────────


class TestRunFullAnalysis:
    def test_empty_db(self):
        """No transactions → no_data signal."""
        mock_session = MagicMock()
        # Mock load_transactions to return empty
        with patch("market.analysis.execution_analyzer.load_transactions") as mock_load:
            mock_load.return_value = pd.DataFrame()
            result = run_full_analysis(mock_session)
            assert result["transactions_count"] == 0
            assert result["model_decay_signal"] == "no_data"

    def test_with_transactions(self, sample_transactions, target_prices):
        """Full analysis with mock transactions."""
        mock_session = MagicMock()
        with patch("market.analysis.execution_analyzer.load_transactions") as mock_load, \
             patch("market.analysis.execution_analyzer.load_target_prices") as mock_targets:
            mock_load.return_value = sample_transactions
            mock_targets.return_value = target_prices
            result = run_full_analysis(mock_session)
            assert result["transactions_count"] == 4
            assert "net_alpha" in result
            assert "execution_efficiency" in result
            assert "slippage" in result
            assert result["model_decay_signal"] in ("healthy", "moderate_slippage", "high_slippage_decay")
