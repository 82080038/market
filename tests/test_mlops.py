"""Tests for MLOps: training, registry, feature store, CV, drift, promotion."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market.mlops.cross_validation import (
    PurgedKFoldCV,
    WalkForwardCV,
    aggregate_cv_results,
    purged_kfold_splits,
    walk_forward_splits,
)
from market.mlops.drift import (
    DriftDetector,
    DriftReport,
    population_stability_index,
)
from market.mlops.feature_store import FeatureDefinition, FeatureStore
from market.mlops.promotion import (
    ABTestFramework,
    EvalCriteria,
    EvalGate,
)
from market.mlops.registry import ModelAlias, ModelRegistry
from market.mlops.training import (
    LSTMModel,
    TrainingConfig,
    TrainingPipeline,
    get_device,
)

# --- Training tests ---


def test_get_device():
    device = get_device()
    assert device in ("cpu", "cuda:0", "cuda:1")


def test_training_config_defaults():
    config = TrainingConfig()
    assert config.model_type == "lstm"
    assert config.sequence_length == 20
    assert config.epochs == 50


def test_lstm_prepare_sequences():
    config = TrainingConfig(sequence_length=10)
    model = LSTMModel(config)
    data = pd.DataFrame({
        "close": np.random.RandomState(42).normal(100, 5, 50),
        "volume": np.full(50, 1_000_000.0),
        "rsi": np.random.RandomState(42).normal(50, 10, 50),
        "forward_return_5d": np.random.RandomState(42).normal(0, 0.02, 50),
    })
    X, y = model.prepare_sequences(data, ["close", "volume", "rsi"], "forward_return_5d")
    assert X.shape == (40, 10, 3)
    assert y.shape == (40,)


def test_training_pipeline_lightgbm():
    config = TrainingConfig(model_type="lightgbm", epochs=10)
    pipeline = TrainingPipeline(config)
    data = pd.DataFrame({
        "close": np.random.RandomState(42).normal(100, 5, 100),
        "volume": np.full(100, 1_000_000.0),
        "rsi": np.random.RandomState(42).normal(50, 10, 100),
    })
    result = pipeline.train(data, model_id="test_lgbm")
    assert result.model_id == "test_lgbm"
    assert result.model_type == "lightgbm"
    assert "rmse" in result.metrics or "fallback" in result.metrics


def test_training_pipeline_lstm():
    config = TrainingConfig(model_type="lstm", epochs=5, patience=3)
    pipeline = TrainingPipeline(config)
    data = pd.DataFrame({
        "close": np.random.RandomState(42).normal(100, 5, 60),
        "volume": np.full(60, 1_000_000.0),
        "rsi": np.random.RandomState(42).normal(50, 10, 60),
    })
    result = pipeline.train(data, model_id="test_lstm")
    assert result.model_id == "test_lstm"
    assert result.model_type == "lstm"
    assert "final_loss" in result.metrics


def test_training_pipeline_invalid_type():
    config = TrainingConfig(model_type="invalid")
    pipeline = TrainingPipeline(config)
    data = pd.DataFrame({"close": [1, 2, 3]})
    with pytest.raises(ValueError, match="Unknown model type"):
        pipeline.train(data)


# --- Model registry tests ---


def test_registry_register():
    reg = ModelRegistry()
    mv = reg.register(
        model_id="m1",
        model_type="lstm",
        version="1.0.0",
        metrics={"sharpe": 1.2},
        trained_at="2024-01-01T00:00:00Z",
        device="cpu",
        n_samples=1000,
    )
    assert mv.model_id == "m1"
    assert reg.count == 1


def test_registry_assign_alias():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100)
    reg.register("m2", "lstm", "1.1.0", {}, "2024-01-02", "cpu", 100)

    reg.assign_alias("m1", ModelAlias.CHAMPION)
    assert reg.champion is not None
    assert reg.champion.model_id == "m1"

    # Reassign to m2
    reg.assign_alias("m2", ModelAlias.CHAMPION)
    assert reg.champion.model_id == "m2"
    assert not reg.get("m1").is_champion


def test_registry_promote():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100, alias=ModelAlias.EXPERIMENT)

    # experiment → candidate
    assert reg.promote("m1")
    assert reg.candidate is not None
    assert reg.candidate.model_id == "m1"

    # candidate → champion
    assert reg.promote("m1")
    assert reg.champion is not None
    assert reg.champion.model_id == "m1"


def test_registry_rollback():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100)
    reg.register("m2", "lstm", "1.1.0", {}, "2024-01-02", "cpu", 100)
    reg.assign_alias("m2", ModelAlias.CHAMPION)

    new_champion = reg.rollback()
    assert new_champion is not None
    assert new_champion.model_id == "m1"


def test_registry_archive():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100, alias=ModelAlias.EXPERIMENT)
    assert reg.archive("m1")
    assert reg.get("m1").status == "archived"
    assert len(reg.get("m1").aliases) == 0


def test_registry_list_by_type():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100)
    reg.register("m2", "lightgbm", "1.0.0", {}, "2024-01-01", "cpu", 100)
    lstm_models = reg.list_models("lstm")
    assert len(lstm_models) == 1


# --- Feature store tests ---


def test_feature_store_register_defaults():
    store = FeatureStore()
    store.register_default_features()
    features = store.registered_features
    assert "rsi_14@1.0.0" in features
    assert "sma_20@1.0.0" in features
    assert "atr_14@1.0.0" in features


def test_feature_store_compute():
    store = FeatureStore()
    store.register_default_features()
    rng = np.random.RandomState(42)
    data = pd.DataFrame({
        "open": rng.normal(100, 5, 100),
        "high": rng.normal(105, 5, 100),
        "low": rng.normal(95, 5, 100),
        "close": rng.normal(100, 5, 100),
        "volume": rng.uniform(500_000, 2_000_000, 100),
    })
    feature_set = store.compute(data, ["rsi_14", "sma_20"])
    assert "rsi_14" in feature_set.features.columns
    assert "sma_20" in feature_set.features.columns
    assert feature_set.n_rows == 100


def test_feature_store_cache():
    store = FeatureStore()
    store.register_default_features()
    data = pd.DataFrame({
        "close": np.random.RandomState(42).normal(100, 5, 50),
        "high": np.random.RandomState(42).normal(105, 5, 50),
        "low": np.random.RandomState(42).normal(95, 5, 50),
        "volume": np.full(50, 1_000_000.0),
    })
    fs = store.compute(data, ["rsi_14"])
    store.cache(fs, "test_cache")
    cached = store.get_cached("test_cache")
    assert cached is not None
    assert cached.n_rows == 50


def test_feature_store_custom_feature():
    store = FeatureStore()
    store.register(FeatureDefinition(
        name="custom_returns",
        description="Daily returns",
        version="1.0.0",
        compute_fn=lambda df: df["close"].pct_change(),
        dependencies=["close"],
    ))
    data = pd.DataFrame({"close": np.random.RandomState(42).normal(100, 5, 50)})
    fs = store.compute(data, ["custom_returns"])
    assert "custom_returns" in fs.features.columns


# --- Cross-validation tests ---


def test_walk_forward_splits():
    splits = walk_forward_splits(500, train_size=200, test_size=50)
    assert len(splits) > 0
    assert splits[0].train_start == 0
    assert splits[0].train_end == 200
    assert splits[0].test_start == 200
    assert splits[0].test_end == 250


def test_walk_forward_splits_step():
    splits = walk_forward_splits(500, train_size=200, test_size=50, step_size=25)
    assert len(splits) > 3
    assert splits[1].train_start == 25


def test_purged_kfold_splits():
    splits = purged_kfold_splits(500, n_folds=5, purge_pct=0.05)
    assert len(splits) > 0
    for split in splits:
        # Train and test must not overlap (purge gap ensures separation)
        overlap = min(split.train_end, split.test_end) - max(split.train_start, split.test_start)
        assert overlap <= 0  # No overlap between train and test


def test_walk_forward_cv_run():
    cv = WalkForwardCV(train_size=80, test_size=20)
    data = pd.DataFrame({
        "f1": np.random.RandomState(42).normal(0, 1, 200),
        "f2": np.random.RandomState(43).normal(0, 1, 200),
        "target": np.random.RandomState(44).normal(0, 0.1, 200),
    })

    def train_fn(X, y):
        return np.mean(y)

    def eval_fn(model, X, y):
        preds = np.full(len(y), model)
        rmse = float(np.sqrt(np.mean((preds - y) ** 2)))
        return {"rmse": rmse}

    results = cv.run(data, ["f1", "f2"], "target", train_fn, eval_fn)
    assert len(results) > 0
    assert all("rmse" in r.metrics for r in results)


def test_purged_kfold_cv_run():
    cv = PurgedKFoldCV(n_folds=5, purge_pct=0.05)
    data = pd.DataFrame({
        "f1": np.random.RandomState(42).normal(0, 1, 200),
        "target": np.random.RandomState(44).normal(0, 0.1, 200),
    })

    def train_fn(X, y):
        return np.mean(y)

    def eval_fn(model, X, y):
        return {"mae": float(np.mean(np.abs(np.full(len(y), model) - y)))}

    results = cv.run(data, ["f1"], "target", train_fn, eval_fn)
    assert len(results) > 0


def test_aggregate_cv_results():
    from market.mlops.cross_validation import CVResult

    results = [
        CVResult(fold=0, train_size=100, test_size=20, metrics={"rmse": 0.1}),
        CVResult(fold=1, train_size=100, test_size=20, metrics={"rmse": 0.2}),
    ]
    agg = aggregate_cv_results(results)
    assert "rmse_mean" in agg
    assert "rmse_std" in agg
    assert abs(agg["rmse_mean"] - 0.15) < 0.01


# --- Drift detection tests ---


def test_psi_no_drift():
    rng = np.random.RandomState(42)
    baseline = rng.normal(0, 1, 1000)
    current = rng.normal(0, 1, 1000)
    psi = population_stability_index(baseline, current)
    assert psi < 0.1  # No significant drift


def test_psi_with_drift():
    rng = np.random.RandomState(42)
    baseline = rng.normal(0, 1, 1000)
    current = rng.normal(2, 1, 1000)  # Shifted mean
    psi = population_stability_index(baseline, current)
    assert psi > 0.25  # Significant drift


def test_drift_detector_metric_drift():
    detector = DriftDetector(metric_threshold=0.1)
    detector.set_baseline_metrics({"sharpe": 1.5, "rmse": 0.05})
    results = detector.check_metric_drift({"sharpe": 1.0, "rmse": 0.05})
    sharpe_result = next(r for r in results if r.metric_name == "sharpe")
    assert sharpe_result.is_drifted  # 33% drop > 10% threshold
    rmse_result = next(r for r in results if r.metric_name == "rmse")
    assert not rmse_result.is_drifted


def test_drift_detector_prediction_drift():
    detector = DriftDetector(psi_threshold=0.25)
    rng = np.random.RandomState(42)
    detector.set_baseline_predictions(rng.normal(0, 1, 500))
    current = rng.normal(3, 1, 500)  # Drifted
    result = detector.check_prediction_drift(current)
    assert result.is_drifted


def test_drift_detector_feature_drift():
    detector = DriftDetector()
    rng = np.random.RandomState(42)
    baseline = pd.DataFrame({"f1": rng.normal(0, 1, 500), "f2": rng.normal(5, 2, 500)})
    detector.set_baseline_features(baseline)
    current = pd.DataFrame({"f1": rng.normal(5, 1, 500), "f2": rng.normal(5, 2, 500)})
    psi_scores = detector.check_feature_drift(current)
    assert "f1" in psi_scores
    assert psi_scores["f1"] > 0.25
    assert psi_scores["f2"] < 0.25


def test_drift_detector_assess():
    detector = DriftDetector()
    detector.set_baseline_metrics({"sharpe": 1.5})
    rng = np.random.RandomState(42)
    detector.set_baseline_predictions(rng.normal(0, 1, 500))
    report = detector.assess(
        current_metrics={"sharpe": 0.5},
        current_predictions=rng.normal(3, 1, 500),
    )
    assert isinstance(report, DriftReport)
    assert report.is_drifted


# --- Promotion tests ---


def test_eval_gate_pass():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100, alias=ModelAlias.EXPERIMENT)
    gate = EvalGate(
        reg, EvalCriteria(min_sharpe=0.5, max_drawdown=-0.3, min_win_rate=0.4, min_samples=50),
    )
    result = gate.promote_if_passed("m1", {
        "sharpe": 1.0, "max_drawdown": -0.1, "win_rate": 0.55, "n_samples": 100,
    })
    assert result.passed
    assert reg.candidate is not None
    assert reg.candidate.model_id == "m1"


def test_eval_gate_fail():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100, alias=ModelAlias.EXPERIMENT)
    gate = EvalGate(reg, EvalCriteria(min_sharpe=1.0))
    result = gate.promote_if_passed("m1", {"sharpe": 0.3, "n_samples": 100})
    assert not result.passed
    assert len(result.failures) > 0


def test_eval_gate_promote_to_champion():
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100, alias=ModelAlias.CANDIDATE)
    gate = EvalGate(
        reg, EvalCriteria(min_sharpe=0.5, max_drawdown=-0.5, min_win_rate=0.3, min_samples=50),
    )
    result = gate.promote_if_passed("m1", {
        "sharpe": 1.0, "max_drawdown": -0.1, "win_rate": 0.55, "n_samples": 100,
    })
    assert result.passed
    assert reg.champion is not None
    assert reg.champion.model_id == "m1"


def test_ab_test_framework():
    framework = ABTestFramework()
    rng = np.random.RandomState(42)
    returns_a = rng.normal(0.001, 0.02, 200)
    returns_b = rng.normal(0.002, 0.02, 200)
    result = framework.run_test("test1", "strategy_a", "strategy_b", returns_a, returns_b)
    assert result.name == "test1"
    assert result.winner in ("strategy_a", "strategy_b")
    assert 0 <= result.p_value <= 1


def test_ab_test_significant():
    framework = ABTestFramework()
    rng = np.random.RandomState(42)
    returns_a = rng.normal(0.001, 0.01, 500)
    returns_b = rng.normal(0.005, 0.01, 500)  # Clearly better
    result = framework.run_test("test2", "a", "b", returns_a, returns_b)
    assert result.winner == "b"
    assert result.is_significant


def test_ab_test_get_significant():
    framework = ABTestFramework()
    rng = np.random.RandomState(42)
    # Non-significant
    framework.run_test("ns", "a", "b", rng.normal(0, 0.01, 100), rng.normal(0, 0.01, 100))
    # Significant
    framework.run_test("sig", "a", "b", rng.normal(0, 0.01, 500), rng.normal(0.01, 0.01, 500))
    sig_results = framework.get_significant_results()
    assert len(sig_results) >= 1
