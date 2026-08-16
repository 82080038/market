"""Performance regression tests (Gap #11).

Uses pytest-benchmark to track performance of critical code paths:
- Technical indicator computation
- Strategy signal generation
- Cross-market correlation
- Data quality monitoring
- Notification dispatch
- Model registry operations

Run with: pytest tests/test_performance.py --benchmark-only
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.technical import TechnicalAnalysisEngine
from market.data.dq_monitor import DataQualityMonitor
from market.mlops.registry import ModelRegistry
from market.multi_asset.cross_market import CrossMarketEngine


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate 500 days of synthetic OHLCV data."""
    np.random.seed(42)
    n = 500
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = 100 + np.random.randn(n).cumsum() * 0.5
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 0.5,
        "high": close + np.random.rand(n) * 0.5,
        "low": close - np.random.rand(n) * 0.5,
        "close": close,
        "volume": np.random.randint(100000, 1000000, n).astype(float),
    }, index=dates)


@pytest.fixture
def sample_returns() -> dict[str, pd.Series]:
    """Generate returns for 5 markets."""
    np.random.seed(42)
    n = 200
    return {
        f"Market{i}": pd.Series(np.random.randn(n) * 0.01) for i in range(5)
    }


# ── Technical Analysis ────────────────────────────────────────────────────

def test_benchmark_technical_analysis(sample_ohlcv, benchmark):
    """Benchmark full technical analysis on 500 bars."""
    ta = TechnicalAnalysisEngine()
    benchmark(ta.analyze, "TEST.JK", sample_ohlcv)


def test_benchmark_rsi(sample_ohlcv, benchmark):
    """Benchmark RSI computation on 500 bars."""
    ta = TechnicalAnalysisEngine()
    benchmark(ta._compute_rsi, sample_ohlcv["close"], 14)


def test_benchmark_macd(sample_ohlcv, benchmark):
    """Benchmark MACD computation on 500 bars."""
    ta = TechnicalAnalysisEngine()
    benchmark(ta._compute_macd, sample_ohlcv["close"])


def test_benchmark_bollinger(sample_ohlcv, benchmark):
    """Benchmark Bollinger Bands computation on 500 bars."""
    ta = TechnicalAnalysisEngine()
    benchmark(ta._compute_bollinger, sample_ohlcv["close"], 20)


def test_benchmark_atr(sample_ohlcv, benchmark):
    """Benchmark ATR computation on 500 bars."""
    ta = TechnicalAnalysisEngine()
    benchmark(ta._compute_atr, sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"], 14)


# ── Cross-Market ──────────────────────────────────────────────────────────

def test_benchmark_correlation(sample_returns, benchmark):
    """Benchmark pairwise correlation computation."""
    engine = CrossMarketEngine(min_samples=30)
    keys = list(sample_returns.keys())

    def compute_all():
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                engine.compute_correlation(sample_returns[a], sample_returns[b], a, b)

    benchmark(compute_all)


def test_benchmark_heatmap(sample_returns, benchmark):
    """Benchmark heatmap generation for 5 markets."""
    engine = CrossMarketEngine(min_samples=30)
    benchmark(engine.generate_heatmap, sample_returns)


def test_benchmark_full_analyze(sample_returns, benchmark):
    """Benchmark full cross-market analysis."""
    engine = CrossMarketEngine(min_samples=30)
    benchmark(engine.analyze, sample_returns, None, 5)


# ── Data Quality ──────────────────────────────────────────────────────────

def test_benchmark_dq_single(sample_ohlcv, benchmark):
    """Benchmark DQ assessment for a single ticker."""
    monitor = DataQualityMonitor()
    benchmark(monitor.assess_ticker, "TEST.JK", sample_ohlcv)


def test_benchmark_dq_batch(benchmark):
    """Benchmark DQ batch assessment for 20 tickers."""
    np.random.seed(42)
    data = {}
    for i in range(20):
        n = 60
        dates = pd.bdate_range("2024-01-01", periods=n)
        data[f"TICK{i}.JK"] = pd.DataFrame({
            "close": 100 + np.random.randn(n).cumsum() * 0.5,
            "volume": np.random.randint(100000, 1000000, n).astype(float),
        }, index=dates)

    monitor = DataQualityMonitor()
    benchmark(monitor.assess_batch, data)


# ── Model Registry ────────────────────────────────────────────────────────

def test_benchmark_registry_register(benchmark):
    """Benchmark model registration."""
    registry = ModelRegistry()

    def register_models():
        for i in range(50):
            registry.register(
                model_id=f"model_{i}",
                model_type="test",
                version=f"1.0.{i}",
                metrics={"accuracy": 0.85 + i * 0.001},
                trained_at="2026-01-01",
                device="cpu",
                n_samples=1000,
            )

    benchmark(register_models)


def test_benchmark_registry_lookup(benchmark):
    """Benchmark model lookup by alias."""
    from market.mlops.registry import ModelAlias

    registry = ModelRegistry()
    for i in range(100):
        registry.register(
            model_id=f"model_{i}",
            model_type="test",
            version=f"1.0.{i}",
            metrics={"accuracy": 0.85},
            trained_at="2026-01-01",
            device="cpu",
            n_samples=1000,
        )
    # Assign champion alias to last model
    registry.assign_alias("model_99", ModelAlias.CHAMPION)

    benchmark(registry.get_by_alias, ModelAlias.CHAMPION.value)


# ── Notification Dispatch ─────────────────────────────────────────────────

def test_benchmark_notification_dispatch(benchmark):
    """Benchmark notification dispatch with no channels (in-app only)."""
    from market.notifications.channels import NotificationDispatcher

    dispatcher = NotificationDispatcher()

    def dispatch_batch():
        for i in range(100):
            dispatcher.dispatch(
                message=f"Test alert body {i}",
                subject=f"Alert {i}",
            )

    benchmark(dispatch_batch)
