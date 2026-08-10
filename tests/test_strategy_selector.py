"""Tests for StrategySelector — personality-aware strategy assignment."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.analysis.profiling import (
    InstrumentProfile,
    PersonalityLabel,
    VolatilityRegime,
)
from market.analysis.strategy_selector import (
    StrategySelector,
    STRATEGY_CLASSES,
    PERSONALITY_TO_CLASS,
    ALL_STRATEGIES,
)


def _make_close(n: int = 200, trend: float = 0.001, vol: float = 0.02) -> pd.Series:
    """Generate synthetic close price series."""
    rng = np.random.default_rng(42)
    returns = rng.normal(trend, vol, n)
    close = 100 * np.cumprod(1 + returns)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(close, index=dates, name="close")


def _make_profile(labels=None, vol=VolatilityRegime.MEDIUM, beta=1.0) -> InstrumentProfile:
    return InstrumentProfile(
        ticker="TEST.JK",
        volatility_regime=vol,
        trend_bias="sideways",
        beta_vs_ihsg=beta,
        liquidity_score=50.0,
        avg_daily_volume=1e6,
        avg_daily_volatility_pct=2.0,
        personality_labels=labels or [PersonalityLabel.MID_CAP],
        sector="Financials",
        commodity_linkage=None,
    )


def test_strategy_selector_basic():
    selector = StrategySelector()
    close = _make_close()
    result = selector.select("TEST.JK", close)
    assert result.ticker == "TEST.JK"
    assert result.best_strategy in ALL_STRATEGIES
    assert result.strategy_class in STRATEGY_CLASSES
    assert result.in_sample_sharpe is not None


def test_strategy_selector_blue_chip_mean_reversion():
    selector = StrategySelector()
    close = _make_close(trend=0.0, vol=0.005)  # low vol, no trend
    profile = _make_profile(labels=[PersonalityLabel.BLUE_CHIP], vol=VolatilityRegime.LOW)
    result = selector.select("TEST.JK", close, profile)
    assert result.strategy_class == "mean_reversion"


def test_strategy_selector_gorengan_technical_only():
    selector = StrategySelector()
    close = _make_close(trend=0.002, vol=0.05)  # high vol
    profile = _make_profile(labels=[PersonalityLabel.GORENGAN], vol=VolatilityRegime.HIGH)
    result = selector.select("TEST.JK", close, profile)
    assert result.strategy_class == "technical_only"


def test_strategy_selector_extreme_volatility_macro_regime():
    selector = StrategySelector()
    close = _make_close(trend=0.0, vol=0.08)  # extreme vol
    profile = _make_profile(labels=[PersonalityLabel.HIGH_BETA], vol=VolatilityRegime.EXTREME)
    result = selector.select("TEST.JK", close, profile)
    assert result.strategy_class == "macro_regime"


def test_strategy_selector_insufficient_data():
    selector = StrategySelector()
    close = _make_close(n=50)  # too short
    result = selector.select("TEST.JK", close)
    assert result.best_strategy == "donchian"
    assert "Insufficient data" in result.strategy_rationale


def test_strategy_selector_batch():
    selector = StrategySelector()
    instruments = {
        "AAA.JK": _make_close(),
        "BBB.JK": _make_close(trend=0.002),
        "CCC.JK": _make_close(n=50),  # insufficient
    }
    results = selector.select_batch(instruments)
    assert len(results) == 3
    assert results["AAA.JK"].ticker == "AAA.JK"
    assert results["CCC.JK"].best_strategy == "donchian"  # default for insufficient


def test_strategy_selector_rationale_contains_personality():
    selector = StrategySelector()
    close = _make_close()
    profile = _make_profile(labels=[PersonalityLabel.DIVIDEND_STOCK])
    result = selector.select("TEST.JK", close, profile)
    assert "dividend_stock" in result.strategy_rationale.lower()


def test_personality_to_class_mapping_completeness():
    """All personality labels should have a strategy class mapping."""
    for label in PersonalityLabel:
        assert label in PERSONALITY_TO_CLASS, f"Missing mapping for {label}"
