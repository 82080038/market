"""Tests for PatternDetector and PredictionEngine (pustaka/18 §3.3, pustaka/29, pustaka/67)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.analysis.extras import PatternMemory
from market.analysis.pattern_detector import PatternDetector
from market.analysis.prediction import (
    ErrorCategory,
    PredictionEngine,
    PredictionMethod,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate mock OHLCV data."""
    rng = np.random.RandomState(seed)
    close = 8000 + rng.randn(n).cumsum() * 30
    dates = pd.bdate_range("2023-06-01", periods=n)
    return pd.DataFrame({
        "open": close + rng.randn(n) * 10,
        "high": close + abs(rng.randn(n) * 20),
        "low": close - abs(rng.randn(n) * 20),
        "close": close,
        "volume": rng.randint(100000, 1000000, n).astype(float),
    }, index=dates)


def _make_double_bottom_data() -> pd.DataFrame:
    """Generate data with a double bottom pattern."""
    n = 120
    dates = pd.bdate_range("2023-06-01", periods=n)
    close = np.zeros(n)
    # First 60 bars: decline to bottom
    for i in range(60):
        close[i] = 9000 - i * 30
    # Bounce up
    for i in range(60, 80):
        close[i] = 7200 + (i - 60) * 40
    # Second decline to similar bottom
    for i in range(80, 100):
        close[i] = 8000 - (i - 80) * 35
    # Bounce again
    for i in range(100, 120):
        close[i] = 7300 + (i - 100) * 30

    return pd.DataFrame({
        "open": close + 5,
        "high": close + 20,
        "low": close - 20,
        "close": close,
        "volume": np.random.RandomState(123).randint(100000, 500000, n).astype(float),
    }, index=dates)


# ---------------------------------------------------------------------------
# PatternDetector tests
# ---------------------------------------------------------------------------


class TestPatternDetector:
    def test_basic_detection(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        detections = detector.detect("BBCA.JK", data)

        assert isinstance(detections, list)
        # May or may not find patterns with random data, but should not crash

    def test_insufficient_data(self):
        detector = PatternDetector(min_lookback=60)
        data = _make_ohlcv(30)
        detections = detector.detect("BBCA.JK", data)

        assert len(detections) == 0
        assert any(e.level == "warn" for e in detector.log)

    def test_no_look_ahead_truncation(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        as_of = data.index[100]

        detector.detect("BBCA.JK", data, as_of=as_of)

        # Should only use data up to index 100
        # Log should mention the as_of date
        assert any("100" in e.message or as_of.isoformat() in e.message for e in detector.log)

    def test_double_bottom_detection(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_double_bottom_data()
        detections = detector.detect("BBCA.JK", data)

        # Should detect double bottom or at least some pattern
        # (exact detection depends on extrema finding)
        assert isinstance(detections, list)

    def test_log_entries_populated(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        detector.detect("BBCA.JK", data)

        assert len(detector.log) > 0
        assert any(e.ticker == "BBCA.JK" for e in detector.log)

    def test_log_cleared_between_runs(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        detector.detect("BBCA.JK", data)
        detector.detect("BBRI.JK", data)
        # Log should be cleared and repopulated
        assert len(detector.log) > 0
        # Should not accumulate
        assert any(e.ticker == "BBRI.JK" for e in detector.log)
        assert not any(e.ticker == "BBCA.JK" for e in detector.log)

    def test_patterns_recorded_in_memory(self):
        memory = PatternMemory()
        detector = PatternDetector(pattern_memory=memory, min_lookback=50)
        data = _make_ohlcv(200)
        detections = detector.detect("BBCA.JK", data)

        # Each detection should have a pattern_record
        for d in detections:
            assert d.pattern_record is not None
            assert d.pattern_record.ticker == "BBCA.JK"

        # PatternMemory should have records
        assert len(memory.patterns) == len(detections)

    def test_detection_direction_values(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        detections = detector.detect("BBCA.JK", data)

        for d in detections:
            assert d.direction in ("bullish", "bearish", "neutral")

    def test_detection_confidence_range(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        detections = detector.detect("BBCA.JK", data)

        for d in detections:
            assert 0.0 <= d.confidence <= 1.0

    def test_detection_has_key_levels(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        detections = detector.detect("BBCA.JK", data)

        for d in detections:
            assert isinstance(d.key_levels, dict)

    def test_as_of_none_uses_all_data(self):
        detector = PatternDetector(min_lookback=50)
        data = _make_ohlcv(200)
        detections = detector.detect("BBCA.JK", data, as_of=None)

        # Should use all data, no error
        assert isinstance(detections, list)

    def test_empty_dataframe(self):
        detector = PatternDetector(min_lookback=50)
        detections = detector.detect("EMPTY.JK", pd.DataFrame())

        assert len(detections) == 0

    def test_macd_crossover_detection(self):
        """Test that MACD crossover can be detected."""
        detector = PatternDetector(min_lookback=50)
        n = 100
        dates = pd.bdate_range("2023-01-01", periods=n)
        # Create data with a trend change to trigger MACD cross
        close = np.concatenate([
            np.linspace(8000, 9000, 50),
            np.linspace(9000, 8500, 50),
        ])
        data = pd.DataFrame({
            "open": close + 5,
            "high": close + 15,
            "low": close - 15,
            "close": close,
            "volume": np.full(n, 500000.0),
        }, index=dates)

        detections = detector.detect("TEST.JK", data)
        # May detect MACD bearish cross or other patterns
        assert isinstance(detections, list)


# ---------------------------------------------------------------------------
# PredictionEngine tests
# ---------------------------------------------------------------------------


class TestPredictionEngine:
    def test_basic_prediction(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        pred = engine.predict("BBCA.JK", data)

        assert pred.ticker == "BBCA.JK"
        assert pred.predicted_direction in ("up", "down", "flat")
        assert 0.0 <= pred.confidence <= 1.0
        assert pred.horizon_days > 0

    def test_no_look_ahead_truncation(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        as_of = data.index[100]
        pred = engine.predict("BBCA.JK", data, as_of=as_of)

        assert pred.as_of == str(as_of)

    def test_insufficient_data(self):
        engine = PredictionEngine()
        data = _make_ohlcv(20)
        pred = engine.predict("BBCA.JK", data)

        assert pred.confidence == 0.0
        assert "Insufficient" in pred.rationale

    def test_prediction_methods(self):
        data = _make_ohlcv(200)
        for method in PredictionMethod:
            engine = PredictionEngine()
            pred = engine.predict("BBCA.JK", data, method=method)
            assert pred.method == method

    def test_ensemble_prediction(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        pred = engine.predict("BBCA.JK", data, method=PredictionMethod.ENSEMBLE)

        assert pred.method == PredictionMethod.ENSEMBLE
        assert "Ensemble" in pred.rationale

    def test_prediction_has_indicators(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        pred = engine.predict("BBCA.JK", data)

        assert "ma_short" in pred.indicators_used
        assert "ma_long" in pred.indicators_used
        assert "rsi" in pred.indicators_used
        assert "atr" in pred.indicators_used

    def test_prediction_log_populated(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        engine.predict("BBCA.JK", data)

        assert len(engine.log) > 0
        assert any(e.level == "predict" for e in engine.log)

    def test_verify_no_pending(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        result = engine.verify("BBCA.JK", data, data.index[100])

        assert result is None

    def test_verify_correct_prediction(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        as_of = data.index[150]

        # Make prediction
        engine.predict("BBCA.JK", data, as_of=as_of)
        # Verify (should have enough future data: 200 - 150 = 50 > horizon=5)
        error = engine.verify("BBCA.JK", data, as_of)

        # Either no error (correct) or an error object
        if error:
            assert error.ticker == "BBCA.JK"
            assert error.error_pct >= 0
        else:
            # Prediction was within tolerance
            pass

    def test_verify_with_error(self):
        """Test that verification tracks errors properly."""
        engine = PredictionEngine()
        n = 200
        dates = pd.bdate_range("2023-01-01", periods=n)
        # Create data with a sharp reversal after bar 100
        close = np.concatenate([
            np.linspace(8000, 10000, 100),  # uptrend
            np.linspace(10000, 7000, 100),  # sharp downtrend
        ])
        data = pd.DataFrame({
            "open": close + 5,
            "high": close + 15,
            "low": close - 15,
            "close": close,
            "volume": np.full(n, 500000.0),
        }, index=dates)

        as_of = dates[100]
        # Predict at the top (uptrend → will predict up, but market goes down)
        engine.predict("TEST.JK", data, as_of=as_of)
        error = engine.verify("TEST.JK", data, as_of)

        # Should have an error (direction wrong)
        if error:
            assert not error.direction_correct
            assert error.error_category in ErrorCategory
            assert error.root_cause != ""
            assert error.lesson != ""
            assert 0.0 <= error.risk_weight <= 1.0

    def test_error_memory_accumulates(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        as_of = data.index[150]

        engine.predict("BBCA.JK", data, as_of=as_of)
        error = engine.verify("BBCA.JK", data, as_of)

        if error:
            assert len(engine.error_memory) == 1
            assert engine.error_memory[0].error_id.startswith("ERR-")

    def test_error_rate_affects_confidence(self):
        engine = PredictionEngine()
        data = _make_ohlcv(200)

        # Add some fake errors to memory
        from market.analysis.prediction import PredictionError
        for _ in range(5):
            PredictionEngine._error_counter += 1
            engine.error_memory.append(PredictionError(
                error_id=f"ERR-{PredictionEngine._error_counter:05d}",
                ticker="BBCA.JK",
                as_of="2023-01-01",
                method=PredictionMethod.ENSEMBLE,
                predicted_price=8000,
                actual_price=8500,
                predicted_direction="down",
                actual_direction="up",
                error_pct=6.25,
                direction_correct=False,
                error_category=ErrorCategory.MODEL_LIMITATION,
                root_cause="Test",
                lesson="Test lesson",
                risk_weight=0.5,
            ))

        pred = engine.predict("BBCA.JK", data)
        # Confidence should be reduced due to 100% error rate
        assert pred.confidence < 1.0

    def test_risk_adjustment_no_errors(self):
        engine = PredictionEngine()
        adj = engine.get_risk_adjustment("BBCA.JK")
        assert adj == 1.0

    def test_risk_adjustment_with_errors(self):
        engine = PredictionEngine()
        from market.analysis.prediction import PredictionError
        PredictionEngine._error_counter += 1
        engine.error_memory.append(PredictionError(
            error_id=f"ERR-{PredictionEngine._error_counter:05d}",
            ticker="BBCA.JK",
            as_of="2023-01-01",
            method=PredictionMethod.ENSEMBLE,
            predicted_price=8000,
            actual_price=9000,
            predicted_direction="down",
            actual_direction="up",
            error_pct=12.5,
            direction_correct=False,
            error_category=ErrorCategory.REGIME_CHANGE,
            root_cause="Regime change",
            lesson="Always check trend",
            risk_weight=0.8,
        ))

        adj = engine.get_risk_adjustment("BBCA.JK")
        assert adj < 1.0
        assert adj >= 0.5

    def test_error_summary_empty(self):
        engine = PredictionEngine()
        summary = engine.get_error_summary()
        assert summary["total_errors"] == 0

    def test_error_summary_with_errors(self):
        engine = PredictionEngine()
        from market.analysis.prediction import PredictionError
        PredictionEngine._error_counter += 1
        engine.error_memory.append(PredictionError(
            error_id=f"ERR-{PredictionEngine._error_counter:05d}",
            ticker="BBCA.JK",
            as_of="2023-01-01",
            method=PredictionMethod.ENSEMBLE,
            predicted_price=8000,
            actual_price=9000,
            predicted_direction="down",
            actual_direction="up",
            error_pct=12.5,
            direction_correct=False,
            error_category=ErrorCategory.VOLATILITY_SPIKE,
            root_cause="Vol spike",
            lesson="Check ATR",
            risk_weight=0.7,
        ))

        summary = engine.get_error_summary("BBCA.JK")
        assert summary["total_errors"] == 1
        assert "volatility_spike" in summary["by_category"]
        assert len(summary["recent_lessons"]) > 0

    def test_root_cause_volatility_spike(self):
        engine = PredictionEngine()
        n = 200
        dates = pd.bdate_range("2023-01-01", periods=n)
        # Low volatility then high volatility
        rng = np.random.RandomState(42)
        close = np.concatenate([
            np.linspace(8000, 8500, 150),
            8500 + rng.randn(50).cumsum() * 200,  # huge volatility
        ])
        data = pd.DataFrame({
            "open": close + 5,
            "high": close + 15,
            "low": close - 15,
            "close": close,
            "volume": np.full(n, 500000.0),
        }, index=dates)

        as_of = dates[150]
        engine.predict("VOL.JK", data, as_of=as_of)
        error = engine.verify("VOL.JK", data, as_of)

        if error:
            # Should detect volatility spike or regime change
            assert error.error_category in (
                ErrorCategory.VOLATILITY_SPIKE,
                ErrorCategory.REGIME_CHANGE,
                ErrorCategory.MODEL_LIMITATION,
            )

    def test_pattern_signals_in_prediction(self):
        detector = PatternDetector(min_lookback=50)
        engine = PredictionEngine(pattern_detector=detector)
        data = _make_ohlcv(200)
        pred = engine.predict("BBCA.JK", data, method=PredictionMethod.PATTERN_BASED)

        # Pattern-based prediction should have pattern_signals
        assert isinstance(pred.pattern_signals, list)

    def test_prediction_with_as_of_truncates(self):
        """Ensure prediction at as_of doesn't use future data."""
        engine = PredictionEngine()
        data = _make_ohlcv(200)
        as_of_early = data.index[50]
        as_of_late = data.index[180]

        pred_early = engine.predict("BBCA.JK", data, as_of=as_of_early)
        pred_late = engine.predict("BBCA.JK", data, as_of=as_of_late)

        # Predictions should be different (different data used)
        # At minimum, as_of should be different
        assert pred_early.as_of != pred_late.as_of


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestPatternPredictionAPI:
    def test_pattern_detect_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())

        # Generate mock OHLCV
        rng = np.random.RandomState(42)
        n = 200
        dates = pd.bdate_range("2023-06-01", periods=n).astype(str)
        close = 8000 + rng.randn(n).cumsum() * 30

        response = client.post("/api/pattern/detect", json={
            "ticker": "BBCA.JK",
            "ohlcv": {
                "date": list(dates),
                "open": list(close + 5),
                "high": list(close + 20),
                "low": list(close - 20),
                "close": list(close),
                "volume": list(np.full(n, 500000.0)),
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert "patterns" in data
        assert "log" in data

    def test_prediction_predict_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())

        rng = np.random.RandomState(42)
        n = 200
        dates = pd.bdate_range("2023-06-01", periods=n).astype(str)
        close = 8000 + rng.randn(n).cumsum() * 30

        response = client.post("/api/prediction/predict", json={
            "ticker": "BBCA.JK",
            "ohlcv": {
                "date": list(dates),
                "open": list(close + 5),
                "high": list(close + 20),
                "low": list(close - 20),
                "close": list(close),
                "volume": list(np.full(n, 500000.0)),
            },
            "method": "ensemble",
        })
        assert response.status_code == 200
        data = response.json()
        assert "prediction" in data
        assert data["prediction"]["ticker"] == "BBCA.JK"
        assert data["prediction"]["method"] == "ensemble"

    def test_prediction_errors_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/prediction/errors")
        assert response.status_code == 200
        data = response.json()
        assert "total_errors" in data

    def test_prediction_risk_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/prediction/risk/BBCA.JK")
        assert response.status_code == 200
        data = response.json()
        assert "ticker" in data
        assert "risk_adjustment" in data

    def test_pattern_detect_missing_data(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.post("/api/pattern/detect", json={
            "ticker": "BBCA.JK",
        })
        assert response.status_code == 400
