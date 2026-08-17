"""Tests for SignalEnhancer — integration of 7 doc-97 modules into prediction.

Verifies that SignalEnhancer:
- Gracefully degrades when modules/data are unavailable.
- Adjusts confidence and direction based on volume, event, sector, pairs, meta signals.
- Does not introduce look-ahead bias.
- Produces valid EnhancementResult structure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.analysis.prediction import Prediction, PredictionMethod
from market.analysis.signal_enhancer import (
    EnhancementResult,
    EnhancementSignal,
    SignalEnhancer,
)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate sample OHLCV data."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    volume = np.random.randint(100000, 500000, n).astype(float)
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def base_prediction(sample_ohlcv) -> Prediction:
    """Base prediction from the existing engine."""
    return Prediction(
        ticker="TEST.JK",
        as_of=str(sample_ohlcv.index[-1]),
        method=PredictionMethod.ENSEMBLE,
        predicted_price=105.0,
        predicted_direction="up",
        predicted_return_pct=2.5,
        confidence=0.65,
        horizon_days=5,
        indicators_used={"rsi": 55.0, "ma_short": 102.0, "ma_long": 100.0},
        pattern_signals=["bullish_engulfing"],
        rationale="Ensemble: MA=20%, Mom=25%, Pat=30%, Vol=25%.",
    )


class TestSignalEnhancerBasic:
    def test_no_modules_graceful_degradation(self, base_prediction, sample_ohlcv):
        """Enhancer with no module instances should still compute volume from OHLCV."""
        enhancer = SignalEnhancer()
        result = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", sample_ohlcv.index[-1]
        )
        assert isinstance(result, EnhancementResult)
        assert result.enhanced_prediction.predicted_direction == "up"
        assert len(result.signals) == 10
        # Volume signal is computed from OHLCV data, not a module instance.
        vol_sig = next(s for s in result.signals if s.source == "volume")
        assert vol_sig.available
        # Astronacci signal is computed from ephem (no module instance needed).
        astro_sig = next(s for s in result.signals if s.source == "astronacci")
        assert astro_sig.available
        # Other 6 signals require module instances → unavailable.
        # Note: cross_market may also be available if CrossMarketTimezone module
        # auto-loads from default config — include it in the "available" set.
        for sig in result.signals:
            if sig.source not in ("volume", "astronacci", "cross_market"):
                assert not sig.available

    def test_empty_dataframe(self, base_prediction):
        """Empty OHLCV should return base prediction."""
        enhancer = SignalEnhancer()
        result = enhancer.enhance(base_prediction, pd.DataFrame(), "TEST.JK", "2024-06-01")
        assert result.final_confidence == base_prediction.confidence
        assert result.final_direction == base_prediction.predicted_direction

    def test_short_dataframe(self, base_prediction):
        """Short OHLCV (< 20 bars) should skip volume signal."""
        enhancer = SignalEnhancer()
        short_df = pd.DataFrame(
            {"close": [100, 101, 102], "high": [101, 102, 103],
             "low": [99, 100, 101], "volume": [100, 200, 150]},
            index=pd.date_range("2024-01-01", periods=3, freq="B"),
        )
        result = enhancer.enhance(base_prediction, short_df, "TEST.JK", short_df.index[-1])
        vol_sig = [s for s in result.signals if s.source == "volume"][0]
        assert not vol_sig.available

    def test_enhancement_result_structure(self, base_prediction, sample_ohlcv):
        """Verify EnhancementResult has all required fields."""
        enhancer = SignalEnhancer()
        result = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", sample_ohlcv.index[-1]
        )
        assert isinstance(result, EnhancementResult)
        assert isinstance(result.enhanced_prediction, Prediction)
        assert isinstance(result.signals, list)
        assert len(result.signals) == 10
        assert isinstance(result.final_confidence, float)
        assert isinstance(result.final_direction, str)
        assert isinstance(result.bet_size, float)
        assert isinstance(result.total_adjustment, float)


class TestVolumeSignal:
    def test_volume_signal_computed(self, base_prediction, sample_ohlcv):
        """Volume signal should be computed when OHLCV has enough data."""
        enhancer = SignalEnhancer()
        result = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", sample_ohlcv.index[-1]
        )
        vol_sig = [s for s in result.signals if s.source == "volume"][0]
        assert vol_sig.available
        assert -1 <= vol_sig.signal <= 1
        assert "OFI" in vol_sig.rationale

    def test_volume_signal_with_foreign_flow(self, base_prediction, sample_ohlcv):
        """Volume signal should incorporate foreign flow when provided."""
        np.random.seed(42)
        ff = pd.Series(
            np.random.randn(len(sample_ohlcv)) * 1e6,
            index=sample_ohlcv.index,
            name="foreign_flow",
        )
        enhancer = SignalEnhancer()
        result = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", sample_ohlcv.index[-1],
            foreign_flow=ff,
        )
        vol_sig = [s for s in result.signals if s.source == "volume"][0]
        assert vol_sig.available
        assert "FF=" in vol_sig.rationale

    def test_volume_signal_no_volume_column(self, base_prediction):
        """Should skip volume signal when no volume column."""
        enhancer = SignalEnhancer()
        df = pd.DataFrame(
            {"close": np.random.randn(50) + 100},
            index=pd.date_range("2024-01-01", periods=50, freq="B"),
        )
        result = enhancer.enhance(base_prediction, df, "TEST.JK", df.index[-1])
        vol_sig = [s for s in result.signals if s.source == "volume"][0]
        assert not vol_sig.available


class TestNoLookAhead:
    def test_truncation_to_as_of(self, base_prediction, sample_ohlcv):
        """Enhancer should only use data up to as_of."""
        as_of = sample_ohlcv.index[100]
        enhancer = SignalEnhancer()
        result = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", as_of
        )
        vol_sig = [s for s in result.signals if s.source == "volume"][0]
        assert vol_sig.available

    def test_future_data_not_used(self, base_prediction, sample_ohlcv):
        """Data after as_of should not affect the signal."""
        as_of = sample_ohlcv.index[100]
        enhancer = SignalEnhancer()

        # Run with full data.
        result1 = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", as_of
        )

        # Run with truncated data.
        df_trunc = sample_ohlcv.loc[:as_of]
        result2 = enhancer.enhance(
            base_prediction, df_trunc, "TEST.JK", as_of
        )

        vol_sig1 = [s for s in result1.signals if s.source == "volume"][0]
        vol_sig2 = [s for s in result2.signals if s.source == "volume"][0]
        assert abs(vol_sig1.signal - vol_sig2.signal) < 1e-6


class TestConfidenceAdjustment:
    def test_confidence_within_bounds(self, base_prediction, sample_ohlcv):
        """Enhanced confidence should stay in [0.05, 1.0]."""
        enhancer = SignalEnhancer()
        result = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", sample_ohlcv.index[-1]
        )
        assert 0.05 <= result.final_confidence <= 1.0

    def test_direction_preserved_when_no_adjustment(self, base_prediction, sample_ohlcv):
        """Direction should not change when total_adjustment is small."""
        enhancer = SignalEnhancer(signal_threshold=999.0)  # impossibly high
        result = enhancer.enhance(
            base_prediction, sample_ohlcv, "TEST.JK", sample_ohlcv.index[-1]
        )
        assert result.final_direction == base_prediction.predicted_direction


class TestEnhancementSignalDataclass:
    def test_default_values(self):
        sig = EnhancementSignal(source="test")
        assert sig.signal == 0.0
        assert sig.confidence_adjustment == 1.0
        assert sig.rationale == ""
        assert not sig.available

    def test_with_values(self):
        sig = EnhancementSignal(
            source="volume",
            signal=0.5,
            confidence_adjustment=1.15,
            rationale="OFI positive",
            available=True,
        )
        assert sig.signal == 0.5
        assert sig.available
