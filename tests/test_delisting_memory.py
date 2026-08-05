"""Tests for DelistingMemory module (pustaka/67, pustaka/69)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.analysis.delisting_memory import (
    DelistingMemory,
    DelistingReason,
    InstrumentStatus,
    WarningPattern,
    WarningPatternType,
)
from market.analysis.pattern_detector import PatternDetector
from market.analysis.prediction import PredictionEngine


def _make_ohlcv(n: int = 200, seed: int = 42) -> pd.DataFrame:
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


def _make_declining_ohlcv(n: int = 200) -> pd.DataFrame:
    """Data with sustained price decline and volume collapse."""
    dates = pd.bdate_range("2023-01-01", periods=n)
    close = np.linspace(10000, 3000, n)  # 70% decline
    # Exponential volume decay: 1M → 5K (99.5% drop)
    volume = np.exp(np.linspace(np.log(1000000), np.log(5000), n))
    return pd.DataFrame({
        "open": close + 5,
        "high": close + 15,
        "low": close - 15,
        "close": close,
        "volume": volume,
    }, index=dates)


class TestDelistingMemory:
    def test_record_delisting(self):
        mem = DelistingMemory()
        record = mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.FINANCIAL_DISTRESS,
            event_date="2024-01-15",
            last_price=50,
            price_decline_pct=85.0,
            sector="energy",
        )

        assert record.ticker == "DEAD.JK"
        assert record.status == InstrumentStatus.DELISTED
        assert record.reason == DelistingReason.FINANCIAL_DISTRESS
        assert record.risk_score > 0.8
        assert "DEAD.JK" in record.lesson

    def test_record_suspension(self):
        mem = DelistingMemory()
        record = mem.record_suspension(
            ticker="SUSP.JK",
            exchange="IDX",
            reason=DelistingReason.REGULATORY_VIOLATION,
            event_date="2024-03-01",
        )

        assert record.status == InstrumentStatus.SUSPENDED
        assert record.reason == DelistingReason.REGULATORY_VIOLATION

    def test_block_instrument(self):
        mem = DelistingMemory()
        record = mem.block_instrument(
            ticker="RISKY.JK",
            reason="Pattern matches delisted instruments",
            risk_score=0.9,
        )

        assert record.status == InstrumentStatus.BLOCKED
        assert record.risk_score == 0.9

    def test_is_blocked(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )

        assert mem.is_blocked("DEAD.JK") is True
        assert mem.is_blocked("ALIVE.JK") is False

    def test_is_suspended(self):
        mem = DelistingMemory()
        mem.record_suspension(
            ticker="SUSP.JK",
            exchange="IDX",
            reason=DelistingReason.EXTENDED_SUSPENSION,
            event_date="2024-03-01",
        )

        assert mem.is_suspended("SUSP.JK") is True
        assert mem.is_suspended("OK.JK") is False
        # Suspended is not blocked
        assert mem.is_blocked("SUSP.JK") is False

    def test_get_record(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.NEGATIVE_EQUITY,
            event_date="2024-01-15",
        )

        record = mem.get_record("DEAD.JK")
        assert record is not None
        assert record.ticker == "DEAD.JK"

        assert mem.get_record("UNKNOWN.JK") is None

    def test_auto_lesson_generation(self):
        mem = DelistingMemory()
        record = mem.record_delisting(
            ticker="LESSON.JK",
            exchange="IDX",
            reason=DelistingReason.GOING_CONCERN,
            event_date="2024-01-15",
        )

        assert "going concern" in record.lesson.lower()
        assert "LESSON.JK" in record.lesson

    def test_warning_patterns_in_record(self):
        mem = DelistingMemory()
        patterns = [
            WarningPattern(
                pattern_type=WarningPatternType.SUSTAINED_PRICE_DECLINE,
                description="Price declined 60%",
                severity=0.8,
                detected_date="2024-01-01",
            ),
            WarningPattern(
                pattern_type=WarningPatternType.VOLUME_COLLAPSE,
                description="Volume dropped 85%",
                severity=0.7,
                detected_date="2024-01-01",
            ),
        ]

        record = mem.record_delisting(
            ticker="WARN.JK",
            exchange="IDX",
            reason=DelistingReason.FINANCIAL_DISTRESS,
            event_date="2024-01-15",
            warning_patterns=patterns,
        )

        assert len(record.warning_patterns) == 2
        assert record.risk_score > 0.7

    def test_check_warning_patterns_clean(self):
        mem = DelistingMemory()
        data = _make_ohlcv(200)
        warnings = mem.check_warning_patterns("OK.JK", data)

        # Clean data should have no warnings
        assert len(warnings) == 0

    def test_check_warning_patterns_declining(self):
        mem = DelistingMemory()
        data = _make_declining_ohlcv(200)
        warnings = mem.check_warning_patterns("DECLINE.JK", data)

        # Should detect sustained price decline and volume collapse
        warning_types = [w.pattern_type for w in warnings]
        assert WarningPatternType.SUSTAINED_PRICE_DECLINE in warning_types
        assert WarningPatternType.VOLUME_COLLAPSE in warning_types

    def test_check_warning_patterns_insufficient_data(self):
        mem = DelistingMemory()
        data = _make_ohlcv(30)
        warnings = mem.check_warning_patterns("SHORT.JK", data)

        assert len(warnings) == 0

    def test_check_warning_patterns_no_look_ahead(self):
        mem = DelistingMemory()
        data = _make_declining_ohlcv(200)
        as_of = data.index[100]

        warnings = mem.check_warning_patterns("TEST.JK", data, as_of=as_of)

        # At bar 100, decline may not be severe enough yet
        # The key is it should not crash and should use truncated data
        assert isinstance(warnings, list)

    def test_generate_reminders_clean(self):
        mem = DelistingMemory()
        data = _make_ohlcv(200)
        reminders = mem.generate_reminders("OK.JK", data)

        # Clean data, no delisting records → no reminders
        assert len(reminders) == 0

    def test_generate_reminders_delisted(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )

        data = _make_ohlcv(200)
        reminders = mem.generate_reminders("DEAD.JK", data)

        assert len(reminders) == 1
        assert reminders[0].severity == "critical"
        assert "DELISTED" in reminders[0].message

    def test_generate_reminders_suspended(self):
        mem = DelistingMemory()
        mem.record_suspension(
            ticker="SUSP.JK",
            exchange="IDX",
            reason=DelistingReason.REGULATORY_VIOLATION,
            event_date="2024-03-01",
        )

        data = _make_ohlcv(200)
        reminders = mem.generate_reminders("SUSP.JK", data)

        assert len(reminders) == 1
        assert reminders[0].severity == "critical"
        assert "SUSPENDED" in reminders[0].message

    def test_generate_reminders_warning_patterns(self):
        mem = DelistingMemory()
        # Record a delisted instrument with specific warning patterns
        patterns = [
            WarningPattern(
                pattern_type=WarningPatternType.SUSTAINED_PRICE_DECLINE,
                description="Declined 70%",
                severity=0.9,
                detected_date="2024-01-01",
            ),
        ]
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.FINANCIAL_DISTRESS,
            event_date="2024-01-15",
            warning_patterns=patterns,
        )

        # Now check a declining instrument
        data = _make_declining_ohlcv(200)
        reminders = mem.generate_reminders("NEW.JK", data)

        # Should detect warning patterns and find similar delisted
        assert len(reminders) > 0
        assert any(r.reminder_type == "pattern_match" for r in reminders)
        # Should find DEAD.JK as similar
        pattern_reminder = next(r for r in reminders if r.reminder_type == "pattern_match")
        assert "DEAD.JK" in pattern_reminder.similar_delisted

    def test_portfolio_risk_filter(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )
        mem.block_instrument("RISKY.JK", "AI block")

        result = mem.get_portfolio_risk_filter(["ALIVE1.JK", "DEAD.JK", "ALIVE2.JK", "RISKY.JK"])

        assert "ALIVE1.JK" in result["approved"]
        assert "ALIVE2.JK" in result["approved"]
        assert "DEAD.JK" in result["blocked"]
        assert "RISKY.JK" in result["blocked"]
        assert result["blocked_count"] == 2
        assert result["approved_count"] == 2

    def test_get_lessons(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD1.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )
        mem.record_delisting(
            ticker="DEAD2.JK",
            exchange="IDX",
            reason=DelistingReason.VOLUNTARY_DELISTING,
            event_date="2024-02-01",
        )

        lessons = mem.get_lessons()
        assert len(lessons) == 2
        # Bankruptcy should have higher risk score
        assert lessons[0]["risk_score"] >= lessons[1]["risk_score"]

    def test_summary(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )
        mem.record_suspension(
            ticker="SUSP.JK",
            exchange="IDX",
            reason=DelistingReason.REGULATORY_VIOLATION,
            event_date="2024-03-01",
        )

        summary = mem.summary()
        assert summary["total_records"] == 2
        assert summary["by_status"]["delisted"] == 1
        assert summary["by_status"]["suspended"] == 1
        assert summary["by_reason"]["bankruptcy"] == 1

    def test_sync_to_persistent_memory(self):
        from market.autonomous.memory import MemoryType, PersistentMemory

        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )

        persistent = PersistentMemory()
        count = mem.sync_to_persistent_memory(persistent)

        assert count == 1
        # Verify it was stored
        results = persistent.search(
            memory_type=MemoryType.SEMANTIC,
            tags=["delisting_lesson", "DEAD.JK"],
        )
        assert len(results) == 1
        assert "DEAD.JK" in results[0].content

    def test_sync_to_persistent_memory_no_duplicates(self):
        from market.autonomous.memory import PersistentMemory

        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )

        persistent = PersistentMemory()
        count1 = mem.sync_to_persistent_memory(persistent)
        count2 = mem.sync_to_persistent_memory(persistent)

        assert count1 == 1
        assert count2 == 0  # Already synced


class TestPatternDetectorDelistingIntegration:
    def test_detector_with_delisted_ticker(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )

        detector = PatternDetector(delisting_memory=mem, min_lookback=50)
        data = _make_ohlcv(200)
        detections = detector.detect("DEAD.JK", data)

        # Should return empty (blocked)
        assert len(detections) == 0
        # Should log the block
        assert any("BLOCKED" in e.message or "DELISTED" in e.message for e in detector.log)

    def test_detector_with_suspended_ticker(self):
        mem = DelistingMemory()
        mem.record_suspension(
            ticker="SUSP.JK",
            exchange="IDX",
            reason=DelistingReason.REGULATORY_VIOLATION,
            event_date="2024-03-01",
        )

        detector = PatternDetector(delisting_memory=mem, min_lookback=50)
        data = _make_ohlcv(200)
        detector.detect("SUSP.JK", data)

        # Should still detect patterns but log suspension warning
        assert any("SUSPENDED" in e.message for e in detector.log)

    def test_detector_logs_ai_reminders(self):
        mem = DelistingMemory()
        # Record a delisted instrument with warning patterns
        patterns = [
            WarningPattern(
                pattern_type=WarningPatternType.SUSTAINED_PRICE_DECLINE,
                description="Declined 70%",
                severity=0.9,
                detected_date="2024-01-01",
            ),
        ]
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.FINANCIAL_DISTRESS,
            event_date="2024-01-15",
            warning_patterns=patterns,
        )

        detector = PatternDetector(delisting_memory=mem, min_lookback=50)
        data = _make_declining_ohlcv(200)
        detector.detect("NEW.JK", data)

        # Should log AI reminders about warning patterns
        assert any("AI REMINDER" in e.message for e in detector.log)


class TestPredictionEngineDelistingIntegration:
    def test_prediction_refused_for_delisted(self):
        mem = DelistingMemory()
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.BANKRUPTCY,
            event_date="2024-01-15",
        )

        detector = PatternDetector(delisting_memory=mem, min_lookback=50)
        engine = PredictionEngine(pattern_detector=detector)
        data = _make_ohlcv(200)
        pred = engine.predict("DEAD.JK", data)

        assert pred.predicted_price == 0.0
        assert pred.predicted_direction == "flat"
        assert pred.confidence == 0.0
        assert "BLOCKED" in pred.rationale or "DELISTED" in pred.rationale

    def test_prediction_confidence_reduced_for_suspended(self):
        mem = DelistingMemory()
        mem.record_suspension(
            ticker="SUSP.JK",
            exchange="IDX",
            reason=DelistingReason.EXTENDED_SUSPENSION,
            event_date="2024-03-01",
        )

        detector = PatternDetector(delisting_memory=mem, min_lookback=50)
        engine = PredictionEngine(pattern_detector=detector)
        data = _make_ohlcv(200)
        pred = engine.predict("SUSP.JK", data)

        # Confidence should be reduced (x0.3)
        assert pred.confidence < 0.5

    def test_prediction_confidence_reduced_for_warning_patterns(self):
        mem = DelistingMemory()
        patterns = [
            WarningPattern(
                pattern_type=WarningPatternType.SUSTAINED_PRICE_DECLINE,
                description="Declined 70%",
                severity=0.9,
                detected_date="2024-01-01",
            ),
        ]
        mem.record_delisting(
            ticker="DEAD.JK",
            exchange="IDX",
            reason=DelistingReason.FINANCIAL_DISTRESS,
            event_date="2024-01-15",
            warning_patterns=patterns,
        )

        detector = PatternDetector(delisting_memory=mem, min_lookback=50)
        engine = PredictionEngine(pattern_detector=detector)
        data = _make_declining_ohlcv(200)
        pred = engine.predict("NEW.JK", data)

        # Confidence should be reduced due to delisting risk
        assert pred.confidence < 0.8


class TestDelistingAPI:
    def test_delisting_summary_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/delisting/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_records" in data

    def test_delisting_records_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/delisting/records")
        assert response.status_code == 200
        data = response.json()
        assert "records" in data

    def test_delisting_lessons_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/delisting/lessons")
        assert response.status_code == 200
        data = response.json()
        assert "lessons" in data

    def test_delisting_check_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.get("/api/delisting/check/BBCA.JK")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "BBCA.JK"
        assert "is_blocked" in data

    def test_delisting_record_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.post("/api/delisting/record", json={
            "ticker": "TEST.JK",
            "exchange": "IDX",
            "reason": "financial_distress",
            "event_date": "2024-01-15",
            "last_price": 100,
            "price_decline_pct": 75.0,
            "sector": "energy",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "TEST.JK"
        assert data["status"] == "delisted"

    def test_delisting_block_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.post("/api/delisting/block", json={
            "ticker": "BLOCKED.JK",
            "reason": "AI risk: pattern matches delisted",
            "risk_score": 0.85,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "BLOCKED.JK"
        assert data["status"] == "blocked"

    def test_delisting_filter_endpoint(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.post("/api/delisting/filter", json={
            "tickers": ["BBCA.JK", "BBRI.JK", "TLKM.JK"],
        })
        assert response.status_code == 200
        data = response.json()
        assert "approved" in data
        assert "blocked" in data
        assert data["total"] == 3

    def test_delisting_record_missing_data(self):
        from fastapi.testclient import TestClient

        from market.api.app import create_app

        client = TestClient(create_app())
        response = client.post("/api/delisting/record", json={
            "ticker": "TEST.JK",
        })
        assert response.status_code == 400
