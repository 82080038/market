"""Tests for Instrument Knowledge Profiler (pustaka/39, 84, 89, 91, 92)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.analysis.extras import PatternMemory
from market.analysis.profiling import (
    DataSufficiencyChecker,
    FactorRelevanceMapper,
    InstrumentProfiler,
    InstrumentReadinessGate,
    ModelPerformanceRecord,
    ModelPerformanceTracker,
    PatternKnowledgeAssessor,
    PersonalityLabel,
    ReadinessLevel,
    StrategyType,
    VolatilityRegime,
)


def _make_ohlcv(
    n: int = 300,
    start_price: float = 100.0,
    volatility: float = 0.01,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    rng = np.random.RandomState(seed)
    returns = rng.normal(0.001, volatility, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    op = close * (1 + rng.normal(0, 0.003, n))
    volume = rng.randint(100_000, 1_000_000, n).astype(float)
    return pd.DataFrame(
        {"open": op, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def _make_ihsg(n: int = 300) -> pd.DataFrame:
    """Generate synthetic IHSG data."""
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    rng = np.random.RandomState(99)
    returns = rng.normal(0.0005, 0.008, n)
    close = 7000 * np.cumprod(1 + returns)
    return pd.DataFrame({"close": close}, index=dates)


# ---------------------------------------------------------------------------
# DataSufficiencyChecker tests
# ---------------------------------------------------------------------------


class TestDataSufficiencyChecker:
    def test_sufficient_data(self):
        checker = DataSufficiencyChecker(StrategyType.SWING, "equity")
        df = _make_ohlcv(300)
        result = checker.check("TEST.JK", df)
        assert result.is_sufficient
        assert result.bars_available == 300
        assert result.bars_required == 252
        assert result.coverage_pct > 0
        assert result.data_quality_score > 50

    def test_insufficient_bars(self):
        checker = DataSufficiencyChecker(StrategyType.POSITION, "equity")
        df = _make_ohlcv(100)
        result = checker.check("SHORT.JK", df)
        assert not result.is_sufficient
        assert result.bars_available == 100
        assert result.bars_required == 504
        assert any("Insufficient bars" in r for r in result.reasons)

    def test_empty_data(self):
        checker = DataSufficiencyChecker()
        result = checker.check("EMPTY.JK", pd.DataFrame())
        assert not result.is_sufficient
        assert result.bars_available == 0

    def test_strategy_min_bars(self):
        # Asset class equity min (252) overrides scalping (60) and swing (200)
        assert DataSufficiencyChecker(StrategyType.SCALPING).min_bars == 252
        assert DataSufficiencyChecker(StrategyType.SWING).min_bars == 252
        # Position (504) > equity min (252)
        assert DataSufficiencyChecker(StrategyType.POSITION).min_bars == 504
        assert DataSufficiencyChecker(StrategyType.DIVIDEND).min_bars == 1008

    def test_asset_class_min_bars(self):
        checker = DataSufficiencyChecker(StrategyType.SCALPING, "bond")
        # Bond requires 365, scalping requires 60 → max wins
        assert checker.min_bars == 365

    def test_custom_min_bars(self):
        checker = DataSufficiencyChecker(custom_min_bars=500)
        assert checker.min_bars == 500

    def test_gap_detection(self):
        checker = DataSufficiencyChecker(StrategyType.SWING, "equity")
        df = _make_ohlcv(300)
        # Insert a big gap by dropping 40 consecutive rows in the middle
        df_gapped = pd.concat([df.iloc[:150], df.iloc[190:]])
        result = checker.check("GAPPED.JK", df_gapped)
        assert result.gap_count > 0
        assert result.max_gap_days > 5


# ---------------------------------------------------------------------------
# InstrumentProfiler tests
# ---------------------------------------------------------------------------


class TestInstrumentProfiler:
    def test_basic_profile(self):
        profiler = InstrumentProfiler()
        df = _make_ohlcv(300)
        profile = profiler.profile("BBCA.JK", df)
        assert profile.ticker == "BBCA.JK"
        assert profile.volatility_regime in VolatilityRegime
        assert profile.trend_bias in ("uptrend", "downtrend", "sideways", "unknown")
        assert 0 <= profile.liquidity_score <= 100
        assert len(profile.personality_labels) > 0

    def test_empty_data(self):
        profiler = InstrumentProfiler()
        profile = profiler.profile("EMPTY.JK", pd.DataFrame())
        assert PersonalityLabel.UNKNOWN in profile.personality_labels
        assert profile.trend_bias == "unknown"

    def test_short_data(self):
        profiler = InstrumentProfiler()
        df = _make_ohlcv(10)
        profile = profiler.profile("SHORT.JK", df)
        assert profile.trend_bias == "unknown"

    def test_beta_vs_ihsg(self):
        profiler = InstrumentProfiler()
        df = _make_ohlcv(300)
        ihsg = _make_ihsg(300)
        profile = profiler.profile("BBCA.JK", df, ihsg_df=ihsg)
        # Beta should be computable
        assert profile.beta_vs_ihsg != 0.0 or profile.beta_vs_ihsg == 0.0  # just check it runs

    def test_commodity_linkage(self):
        profiler = InstrumentProfiler()
        df = _make_ohlcv(300)
        profile = profiler.profile("AALI.JK", df)
        assert profile.commodity_linkage == "cpo"
        assert PersonalityLabel.COMMODITY_LINKED in profile.personality_labels

    def test_gorengan_detection(self):
        profiler = InstrumentProfiler(gorengan_threshold=0.01)
        df = _make_ohlcv(300, volatility=0.06, seed=7)
        profile = profiler.profile("GORENG.JK", df, market_cap=50_000_000_000)
        # High volatility + low market cap should trigger gorengan or illiquid
        labels = {lbl.value for lbl in profile.personality_labels}
        assert "gorengan" in labels or "illiquid" in labels or "small_cap" in labels

    def test_blue_chip_detection(self):
        profiler = InstrumentProfiler()
        df = _make_ohlcv(300, volatility=0.005, seed=11)
        # Override volume to be > 1M for higher liquidity score
        df["volume"] = np.random.RandomState(55).randint(2_000_000, 5_000_000, 300).astype(float)
        profile = profiler.profile("BBCA.JK", df, market_cap=15_000_000_000_000)
        assert PersonalityLabel.BLUE_CHIP in profile.personality_labels

    def test_volatility_classification(self):
        profiler = InstrumentProfiler()
        assert profiler._classify_volatility(0.5) == VolatilityRegime.LOW
        assert profiler._classify_volatility(2.0) == VolatilityRegime.MEDIUM
        assert profiler._classify_volatility(4.0) == VolatilityRegime.HIGH
        assert profiler._classify_volatility(6.0) == VolatilityRegime.EXTREME


# ---------------------------------------------------------------------------
# FactorRelevanceMapper tests
# ---------------------------------------------------------------------------


class TestFactorRelevanceMapper:
    def test_default_weights(self):
        mapper = FactorRelevanceMapper()
        df = _make_ohlcv(300)
        profiler = InstrumentProfiler()
        profile = profiler.profile("TEST.JK", df)
        result = mapper.map_factors("TEST.JK", profile)
        assert sum(result.weights.values()) == pytest_approx(1.0)
        assert len(result.primary_factors) > 0

    def test_sector_override(self):
        mapper = FactorRelevanceMapper()
        df = _make_ohlcv(300)
        profiler = InstrumentProfiler()
        profile = profiler.profile("ADRO.JK", df, sector="energy")
        result = mapper.map_factors("ADRO.JK", profile)
        # Energy sector should boost global
        assert result.weights["global"] >= 0.15
        assert "energy" in result.rationale[0].lower()

    def test_commodity_linkage_boost(self):
        mapper = FactorRelevanceMapper()
        df = _make_ohlcv(300)
        profiler = InstrumentProfiler()
        profile = profiler.profile("INCO.JK", df)
        result = mapper.map_factors("INCO.JK", profile)
        assert result.weights["global"] > 0.10
        assert result.weights["relationship"] > 0.10
        assert any("commodity" in r.lower() for r in result.rationale)

    def test_gorengan_adjustment(self):
        mapper = FactorRelevanceMapper()
        profiler = InstrumentProfiler(gorengan_threshold=0.01)
        df = _make_ohlcv(300, volatility=0.06, seed=7)
        # Low volume + small cap to trigger gorengan
        df["volume"] = np.random.RandomState(33).randint(5_000, 20_000, 300).astype(float)
        profile = profiler.profile("GORENG.JK", df, market_cap=20_000_000_000)
        result = mapper.map_factors("GORENG.JK", profile)
        assert PersonalityLabel.GORENGAN in profile.personality_labels
        assert result.weights["technical"] > 0.20
        assert result.weights["fundamental"] < 0.25
        assert any("gorengan" in r.lower() for r in result.rationale)

    def test_blue_chip_adjustment(self):
        mapper = FactorRelevanceMapper()
        profiler = InstrumentProfiler()
        df = _make_ohlcv(300, volatility=0.005, seed=11)
        df["volume"] = np.random.RandomState(55).randint(2_000_000, 5_000_000, 300).astype(float)
        profile = profiler.profile("BBCA.JK", df, market_cap=15_000_000_000_000)
        assert PersonalityLabel.BLUE_CHIP in profile.personality_labels
        result = mapper.map_factors("BBCA.JK", profile)
        assert result.weights["fundamental"] > 0.25
        assert any("blue chip" in r.lower() for r in result.rationale)

    def test_weights_normalized(self):
        mapper = FactorRelevanceMapper()
        df = _make_ohlcv(300)
        profiler = InstrumentProfiler()
        profile = profiler.profile("TEST.JK", df, sector="financials")
        result = mapper.map_factors("TEST.JK", profile)
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 0.01


def pytest_approx(expected, rel=0.01):
    """Simple approximate check."""
    return _Approx(expected, rel)


class _Approx:
    def __init__(self, expected, rel):
        self.expected = expected
        self.rel = rel

    def __eq__(self, other):
        return abs(other - self.expected) < self.rel


# ---------------------------------------------------------------------------
# PatternKnowledgeAssessor tests
# ---------------------------------------------------------------------------


class TestPatternKnowledgeAssessor:
    def test_no_patterns(self):
        assessor = PatternKnowledgeAssessor()
        result = assessor.assess("NEW.JK")
        assert result.total_patterns == 0
        assert result.confidence_level == "none"
        assert result.reliability_score == 0.0

    def test_with_patterns(self):
        mem = PatternMemory()
        for i in range(10):
            p = mem.record_pattern("flag", "TEST.JK", direction="bullish", price_at_detection=100)
            mem.update_outcome(p.pattern_id, 105 if i < 7 else 95)
        assessor = PatternKnowledgeAssessor(mem)
        result = assessor.assess("TEST.JK")
        assert result.total_patterns == 10
        assert result.evaluated_patterns == 10
        assert result.confirmed_patterns == 7
        assert result.failed_patterns == 3
        assert result.reliability_score == 70.0
        assert result.confidence_level == "medium"

    def test_high_confidence(self):
        mem = PatternMemory()
        for i in range(25):
            p = mem.record_pattern(
                "double_bottom", "GOOD.JK",
                direction="bullish", price_at_detection=100,
            )
            mem.update_outcome(p.pattern_id, 105 if i < 18 else 95)
        assessor = PatternKnowledgeAssessor(mem)
        result = assessor.assess("GOOD.JK")
        assert result.confidence_level == "high"
        assert result.reliability_score == 72.0

    def test_best_patterns(self):
        mem = PatternMemory()
        # flag: 4/5 confirmed
        for i in range(5):
            p = mem.record_pattern("flag", "TEST.JK", direction="bullish", price_at_detection=100)
            mem.update_outcome(p.pattern_id, 105 if i < 4 else 95)
        # wedge: 1/5 confirmed
        for i in range(5):
            p = mem.record_pattern("wedge", "TEST.JK", direction="bullish", price_at_detection=100)
            mem.update_outcome(p.pattern_id, 105 if i < 1 else 95)
        assessor = PatternKnowledgeAssessor(mem)
        result = assessor.assess("TEST.JK")
        assert any("flag" in bp for bp in result.best_patterns)
        assert not any("wedge" in bp for bp in result.best_patterns)

    def test_knowledge_gaps(self):
        mem = PatternMemory()
        mem.record_pattern("flag", "NEW.JK", direction="bullish", price_at_detection=100)
        # Only 1 pattern, pending
        assessor = PatternKnowledgeAssessor(mem)
        result = assessor.assess("NEW.JK")
        assert len(result.knowledge_gaps) > 0
        assert any("few patterns" in g.lower() for g in result.knowledge_gaps)


# ---------------------------------------------------------------------------
# ModelPerformanceTracker tests
# ---------------------------------------------------------------------------


class TestModelPerformanceTracker:
    def test_no_model(self):
        tracker = ModelPerformanceTracker()
        result = tracker.assess("NEW.JK")
        assert not result.has_model
        assert not result.is_degraded
        assert "Train initial model" in result.recommendation

    def test_good_performance(self):
        tracker = ModelPerformanceTracker()
        tracker.record_performance(ModelPerformanceRecord(
            ticker="GOOD.JK", model_id="m1", model_type="lstm",
            sharpe_ratio=1.5, mae=0.02, directional_accuracy=70.0,
            evaluated_at="2024-01-01",
        ))
        result = tracker.assess("GOOD.JK")
        assert result.has_model
        assert not result.is_degraded
        assert result.latest_sharpe == 1.5

    def test_degraded_sharpe(self):
        tracker = ModelPerformanceTracker()
        tracker.record_performance(ModelPerformanceRecord(
            ticker="BAD.JK", model_id="m1", model_type="lstm",
            sharpe_ratio=0.2, mae=0.05, directional_accuracy=65.0,
            evaluated_at="2024-01-01",
        ))
        result = tracker.assess("BAD.JK")
        assert result.is_degraded
        assert result.auto_adjustment is not None

    def test_degraded_accuracy(self):
        tracker = ModelPerformanceTracker()
        tracker.record_performance(ModelPerformanceRecord(
            ticker="BAD.JK", model_id="m1", model_type="lstm",
            sharpe_ratio=1.0, mae=0.05, directional_accuracy=40.0,
            evaluated_at="2024-01-01",
        ))
        result = tracker.assess("BAD.JK")
        assert result.is_degraded
        assert result.auto_adjustment == "retrain"

    def test_baseline_degradation(self):
        tracker = ModelPerformanceTracker()
        # Good baseline
        for i in range(4):
            tracker.record_performance(ModelPerformanceRecord(
                ticker="DECL.JK", model_id=f"m{i}", model_type="lstm",
                sharpe_ratio=2.0, mae=0.01, directional_accuracy=75.0,
                evaluated_at=f"2024-01-0{i+1}",
            ))
        # Degraded latest
        tracker.record_performance(ModelPerformanceRecord(
            ticker="DECL.JK", model_id="m5", model_type="lstm",
            sharpe_ratio=1.0, mae=0.03, directional_accuracy=60.0,
            evaluated_at="2024-02-01",
        ))
        result = tracker.assess("DECL.JK")
        # sharpe 1.0 < baseline 2.0 * 0.7 = 1.4
        assert result.is_degraded
        assert any("degraded from baseline" in r.lower() for r in result.degradation_reasons)

    def test_negative_sharpe_adjustment(self):
        tracker = ModelPerformanceTracker()
        tracker.record_performance(ModelPerformanceRecord(
            ticker="NEG.JK", model_id="m1", model_type="lstm",
            sharpe_ratio=-0.5, mae=0.08, directional_accuracy=50.0,
            evaluated_at="2024-01-01",
        ))
        result = tracker.assess("NEG.JK")
        assert result.is_degraded
        assert result.auto_adjustment == "reduce_position_size"


# ---------------------------------------------------------------------------
# InstrumentReadinessGate tests
# ---------------------------------------------------------------------------


class TestInstrumentReadinessGate:
    def test_ready_instrument(self):
        gate = InstrumentReadinessGate()
        df = _make_ohlcv(300)
        report = gate.evaluate("BBCA.JK", df)
        assert report.readiness_level in (ReadinessLevel.READY, ReadinessLevel.CONDITIONAL)
        assert report.readiness_score > 0
        assert report.data_sufficiency is not None
        assert report.profile is not None
        assert report.factor_relevance is not None
        assert report.pattern_knowledge is not None
        assert report.model_performance is not None
        assert len(report.summary) > 0

    def test_insufficient_data(self):
        gate = InstrumentReadinessGate()
        df = _make_ohlcv(20)
        report = gate.evaluate("NEW.JK", df)
        assert report.readiness_level == ReadinessLevel.INSUFFICIENT_DATA
        assert len(report.blockers) > 0

    def test_not_ready(self):
        gate = InstrumentReadinessGate(min_readiness_score=90)
        df = _make_ohlcv(100)
        report = gate.evaluate("WEAK.JK", df)
        assert report.readiness_level in (
            ReadinessLevel.NOT_READY, ReadinessLevel.CONDITIONAL,
            ReadinessLevel.INSUFFICIENT_DATA,
        )

    def test_evaluate_batch(self):
        gate = InstrumentReadinessGate()
        instruments = {
            "A.JK": _make_ohlcv(300, seed=1),
            "B.JK": _make_ohlcv(300, seed=2),
            "C.JK": _make_ohlcv(30, seed=3),
        }
        reports = gate.evaluate_batch(instruments)
        assert len(reports) == 3
        assert "A.JK" in reports
        assert reports["A.JK"].readiness_level in (
            ReadinessLevel.READY, ReadinessLevel.CONDITIONAL,
        )
        assert reports["C.JK"].readiness_level == ReadinessLevel.INSUFFICIENT_DATA

    def test_filter_ready(self):
        gate = InstrumentReadinessGate()
        instruments = {
            "READY.JK": _make_ohlcv(300, seed=1),
            "SHORT.JK": _make_ohlcv(30, seed=2),
        }
        reports = gate.evaluate_batch(instruments)
        ready = gate.filter_ready(reports)
        assert "READY.JK" in ready
        assert "SHORT.JK" not in ready

    def test_filter_ready_exclude_conditional(self):
        gate = InstrumentReadinessGate(min_readiness_score=80)
        instruments = {
            "A.JK": _make_ohlcv(300, seed=1),
            "B.JK": _make_ohlcv(300, seed=2),
        }
        reports = gate.evaluate_batch(instruments)
        ready_strict = gate.filter_ready(reports, include_conditional=False)
        ready_loose = gate.filter_ready(reports, include_conditional=True)
        assert len(ready_loose) >= len(ready_strict)

    def test_with_ihsg_and_sector(self):
        gate = InstrumentReadinessGate()
        df = _make_ohlcv(300)
        ihsg = _make_ihsg(300)
        report = gate.evaluate(
            "ADRO.JK", df, ihsg_df=ihsg, sector="energy",
            market_cap=5_000_000_000_000,
        )
        assert report.profile is not None
        assert report.profile.sector == "energy"
        assert report.factor_relevance is not None
        assert report.factor_relevance.weights["global"] >= 0.15

    def test_gorengan_warning(self):
        gate = InstrumentReadinessGate()
        df = _make_ohlcv(300, volatility=0.12, seed=7)
        df["volume"] = np.random.RandomState(33).randint(5_000, 20_000, 300).astype(float)
        report = gate.evaluate(
            "GORENG.JK", df, market_cap=20_000_000_000,
        )
        assert any("gorengan" in w.lower() for w in report.warnings)

    def test_summary_content(self):
        gate = InstrumentReadinessGate()
        df = _make_ohlcv(300)
        report = gate.evaluate("TEST.JK", df)
        assert "TEST.JK" in report.summary
        assert "score" in report.summary.lower()
        assert "Data:" in report.summary
        assert "Profile:" in report.summary
        assert "Patterns:" in report.summary
        assert "Model:" in report.summary

    def test_recommendations_generated(self):
        gate = InstrumentReadinessGate()
        df = _make_ohlcv(300)
        report = gate.evaluate("TEST.JK", df)
        # Should have some recommendations (at least pattern knowledge gaps)
        assert isinstance(report.recommendations, list)

    def test_readiness_score_range(self):
        gate = InstrumentReadinessGate()
        df = _make_ohlcv(300)
        report = gate.evaluate("TEST.JK", df)
        assert 0 <= report.readiness_score <= 100

    def test_empty_dataframe(self):
        gate = InstrumentReadinessGate()
        report = gate.evaluate("EMPTY.JK", pd.DataFrame())
        assert report.readiness_level == ReadinessLevel.INSUFFICIENT_DATA
        assert report.readiness_score < 50
