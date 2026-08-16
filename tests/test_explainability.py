"""Tests for model explainability (Gap #38)."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.ensemble import RandomForestRegressor

from market.analysis.explainability import (
    FeatureImportance,
    GlobalExplanation,
    LocalExplanation,
    ModelExplainer,
)


@pytest.fixture
def X_y():
    """Simple regression dataset."""
    rng = np.random.default_rng(42)
    X = rng.standard_normal((100, 5))
    y = 2 * X[:, 0] - 3 * X[:, 1] + 0.5 * X[:, 2] + rng.standard_normal(100) * 0.1
    return X, y


@pytest.fixture
def feature_names():
    return ["rsi", "macd", "volume_ratio", "atr", "bb_width"]


@pytest.fixture
def linear_model(X_y, feature_names):
    X, y = X_y
    model = LinearRegression()
    model.fit(X, y)
    return ModelExplainer(model, feature_names)


@pytest.fixture
def tree_model(X_y, feature_names):
    X, y = X_y
    model = RandomForestRegressor(n_estimators=10, random_state=42)
    model.fit(X, y)
    return ModelExplainer(model, feature_names)


def test_feature_importance_dataclass():
    """FeatureImportance can be constructed."""
    fi = FeatureImportance(feature_name="rsi", importance=0.5, rank=1)
    assert fi.feature_name == "rsi"
    assert fi.importance == 0.5
    assert fi.rank == 1


def test_local_explanation_top_features():
    """LocalExplanation.top_features returns top 5."""
    contributions = [
        FeatureImportance(f"f{i}", float(i), i) for i in range(10)
    ]
    exp = LocalExplanation(
        sample_index=0, base_value=0.0, prediction=1.0,
        feature_contributions=contributions,
    )
    top = exp.top_features
    assert len(top) == 5
    # Should be sorted by absolute importance (descending)
    assert top[0].importance == 9.0


def test_detect_model_type_linear(linear_model):
    """Model type detection works for linear models."""
    assert linear_model.model_type == "linear"


def test_detect_model_type_tree(tree_model):
    """Model type detection works for tree models."""
    assert tree_model.model_type == "tree"


def test_explain_global_builtin_linear(linear_model, X_y):
    """explain_global_builtin works for linear models (coef_)."""
    X, _ = X_y
    result = linear_model.explain_global_builtin(X)
    assert result.method == "builtin"
    assert len(result.feature_importance) == 5
    # Features should be ranked
    assert result.feature_importance[0].rank == 1
    # RSI (feature 0) has coefficient 2.0 — should be high importance
    top = result.feature_importance[0]
    assert top.importance > 0


def test_explain_global_builtin_tree(tree_model, X_y):
    """explain_global_builtin works for tree models (feature_importances_)."""
    X, _ = X_y
    result = tree_model.explain_global_builtin(X)
    assert result.method == "builtin"
    assert len(result.feature_importance) == 5
    assert all(f.importance >= 0 for f in result.feature_importance)


def test_explain_local_builtin(linear_model, X_y):
    """_explain_local_builtin returns explanations for all samples."""
    X, _ = X_y
    explanations = linear_model._explain_local_builtin(X, [0, 1, 2])
    assert len(explanations) == 3
    assert all(e.method == "builtin" for e in explanations)
    assert all(len(e.feature_contributions) == 5 for e in explanations)


def test_explain_local_shap_fallback(linear_model, X_y):
    """explain_local_shap falls back to builtin if SHAP not available."""
    X, _ = X_y
    explanations = linear_model.explain_local_shap(X, [0])
    assert len(explanations) == 1
    # Should work (either SHAP or builtin fallback)
    assert explanations[0].method in ("shap", "builtin")


def test_explain_local_lime_fallback(linear_model, X_y):
    """explain_local_lime falls back to builtin if LIME not available."""
    X, _ = X_y
    explanations = linear_model.explain_local_lime(X, [0])
    assert len(explanations) == 1
    assert explanations[0].method in ("lime", "builtin")


def test_explain_convenience_method(linear_model, X_y):
    """explain() returns both local and global."""
    X, _ = X_y
    result = linear_model.explain(X, method="builtin", sample_indices=[0, 1])
    assert "local" in result
    assert "global" in result
    assert len(result["local"]) == 2
    assert isinstance(result["global"], GlobalExplanation)


def test_explain_local_only(linear_model, X_y):
    """explain() with local=True, global_=False."""
    X, _ = X_y
    result = linear_model.explain(X, method="builtin", local=True, global_=False)
    assert "local" in result
    assert "global" not in result


def test_explain_global_only(linear_model, X_y):
    """explain() with local=False, global_=True."""
    X, _ = X_y
    result = linear_model.explain(X, method="builtin", local=False, global_=True)
    assert "global" in result
    assert "local" not in result


def test_global_explanation_ranks_features(linear_model, X_y):
    """Global explanation assigns ranks correctly."""
    X, _ = X_y
    result = linear_model.explain_global_builtin(X)
    ranks = [f.rank for f in result.feature_importance]
    assert sorted(ranks) == [1, 2, 3, 4, 5]


def test_global_explanation_sorted_by_importance(linear_model, X_y):
    """Features are sorted by absolute importance (descending)."""
    X, _ = X_y
    result = linear_model.explain_global_builtin(X)
    importances = [abs(f.importance) for f in result.feature_importance]
    assert importances == sorted(importances, reverse=True)


def test_feature_names_default():
    """Default feature names are f0, f1, ..."""
    rng = np.random.default_rng(42)
    X = rng.standard_normal((50, 3))
    y = X[:, 0] * 2
    model = LinearRegression().fit(X, y)
    explainer = ModelExplainer(model)  # No feature names
    result = explainer.explain_global_builtin(X)
    names = [f.feature_name for f in result.feature_importance]
    assert "f0" in names or "f1" in names or "f2" in names


def test_model_without_importance_attrs():
    """Model without feature_importances_ or coef_ returns zeros."""
    class DummyModel:
        def predict(self, X):
            return np.zeros(len(X))

    explainer = ModelExplainer(DummyModel(), ["a", "b"])
    X = np.array([[1, 2], [3, 4]])
    result = explainer.explain_global_builtin(X)
    assert all(f.importance == 0 for f in result.feature_importance)
