"""Model explainability using SHAP and LIME (Gap #38).

Provides model-agnostic interpretability for ML model predictions:
- SHAP (SHapley Additive exPlanations): global and local feature importance
- LIME (Local Interpretable Model-agnostic Explanations): local explanations

Graceful degradation:
- If shap/lime not installed, falls back to built-in feature importance
  (e.g. coef_ for linear models, feature_importances_ for tree models).
- Never crashes due to missing optional dependencies.

Use cases:
- Explain why a model predicted buy/sell for a particular stock
- Identify which features are most important globally
- Debug model behavior and detect data leakage
- Build trust in model predictions for trading decisions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FeatureImportance:
    """Feature importance score."""

    feature_name: str
    importance: float
    rank: int = 0


@dataclass
class LocalExplanation:
    """Local explanation for a single prediction."""

    sample_index: int
    base_value: float  # Expected model output
    prediction: float  # Actual model output
    feature_contributions: list[FeatureImportance] = field(default_factory=list)
    method: str = "shap"  # "shap", "lime", "builtin"

    @property
    def top_features(self) -> list[FeatureImportance]:
        """Top 5 features by absolute contribution."""
        sorted_feats = sorted(
            self.feature_contributions,
            key=lambda f: abs(f.importance),
            reverse=True,
        )
        return sorted_feats[:5]


@dataclass
class GlobalExplanation:
    """Global feature importance across all samples."""

    feature_importance: list[FeatureImportance]
    method: str
    n_samples: int
    model_type: str = "unknown"


class ModelExplainer:
    """Model explainability using SHAP/LIME (Gap #38).

    Provides both local (per-prediction) and global (model-wide)
    feature importance explanations.

    Gracefully degrades to built-in feature importance if SHAP/LIME
    are not installed.
    """

    def __init__(self, model: Any, feature_names: list[str] | None = None) -> None:
        self.model = model
        self.feature_names = feature_names or []
        self._shap_explainer = None
        self._lime_explainer = None
        self._model_type = self._detect_model_type()

    def _detect_model_type(self) -> str:
        """Detect the type of ML model."""
        model_class = self.model.__class__.__name__.lower()

        if any(x in model_class for x in ["xgb", "lightgbm", "catboost", "gradient"]):
            return "tree"
        elif any(x in model_class for x in ["randomforest", "extratrees", "decisiontree"]):
            return "tree"
        elif any(x in model_class for x in ["logistic", "linear", "ridge", "lasso", "svm"]):
            return "linear"
        elif any(x in model_class for x in ["mlp", "neural", "keras", "torch"]):
            return "neural"
        else:
            return "unknown"

    @property
    def model_type(self) -> str:
        return self._model_type

    def _init_shap(self, X: np.ndarray) -> bool:
        """Initialize SHAP explainer."""
        if self._shap_explainer is not None:
            return True
        try:
            import shap  # type: ignore[import-untyped]

            if self._model_type == "tree":
                self._shap_explainer = shap.TreeExplainer(self.model)
            else:
                self._shap_explainer = shap.Explainer(self.model, X)
            logger.info("SHAP explainer initialized (%s).", self._model_type)
            return True
        except ImportError:
            logger.warning("shap not installed — using fallback.")
            return False
        except Exception as exc:
            logger.warning("Failed to initialize SHAP: %s", exc)
            return False

    def explain_local_shap(
        self, X: np.ndarray, sample_indices: list[int] | None = None,
    ) -> list[LocalExplanation]:
        """Explain predictions using SHAP.

        Args:
            X: Feature matrix (n_samples, n_features).
            sample_indices: Specific samples to explain. All if None.

        Returns:
            List of LocalExplanation for each sample.
        """
        if not self._init_shap(X):
            return self._explain_local_builtin(X, sample_indices, method="builtin")

        try:
            shap_values = self._shap_explainer.shap_values(X)

            # Handle different SHAP value formats
            if isinstance(shap_values, list):
                # Multi-class: take positive class (index 1)
                shap_values = shap_values[-1] if len(shap_values) > 1 else shap_values[0]
            if shap_values.ndim == 3:
                shap_values = shap_values[:, :, -1]  # Last class for classification

            base_value = float(np.mean(self.model.predict(X))) if hasattr(self.model, "predict") else 0.0
            predictions = self.model.predict(X) if hasattr(self.model, "predict") else np.zeros(len(X))

            if sample_indices is None:
                sample_indices = list(range(len(X)))

            explanations: list[LocalExplanation] = []
            for idx in sample_indices:
                contributions = []
                for feat_idx, feat_name in enumerate(self.feature_names or [f"f{i}" for i in range(X.shape[1])]):
                    contributions.append(FeatureImportance(
                        feature_name=feat_name,
                        importance=float(shap_values[idx, feat_idx]),
                    ))
                explanations.append(LocalExplanation(
                    sample_index=idx,
                    base_value=base_value,
                    prediction=float(predictions[idx]) if hasattr(predictions, "__getitem__") else 0.0,
                    feature_contributions=contributions,
                    method="shap",
                ))
            return explanations

        except Exception as exc:
            logger.warning("SHAP explanation failed: %s — using fallback.", exc)
            return self._explain_local_builtin(X, sample_indices, method="builtin")

    def explain_local_lime(
        self, X: np.ndarray, sample_indices: list[int] | None = None,
    ) -> list[LocalExplanation]:
        """Explain predictions using LIME.

        Args:
            X: Feature matrix.
            sample_indices: Specific samples to explain.

        Returns:
            List of LocalExplanation.
        """
        try:
            from lime.lime_tabular import LimeTabularExplainer  # type: ignore[import-untyped]

            lime_explainer = LimeTabularExplainer(
                X,
                feature_names=self.feature_names or [f"f{i}" for i in range(X.shape[1])],
                mode="regression" if self._model_type != "linear" or not hasattr(self.model, "predict_proba") else "classification",
            )

            if sample_indices is None:
                sample_indices = list(range(min(5, len(X))))

            explanations: list[LocalExplanation] = []
            for idx in sample_indices:
                if hasattr(self.model, "predict_proba"):
                    exp = lime_explainer.explain_instance(
                        X[idx], self.model.predict_proba, num_features=len(self.feature_names),
                    )
                else:
                    exp = lime_explainer.explain_instance(
                        X[idx], self.model.predict, num_features=len(self.feature_names),
                    )

                contributions = []
                for feat_name, weight in exp.as_list():
                    # Parse feature name (LIME adds conditions like "feature > 0.5")
                    clean_name = feat_name.split()[0] if " " in feat_name else feat_name
                    contributions.append(FeatureImportance(
                        feature_name=clean_name,
                        importance=float(weight),
                    ))

                pred = self.model.predict(X[idx:idx+1])[0] if hasattr(self.model, "predict") else 0.0
                explanations.append(LocalExplanation(
                    sample_index=idx,
                    base_value=0.0,
                    prediction=float(pred),
                    feature_contributions=contributions,
                    method="lime",
                ))
            return explanations

        except ImportError:
            logger.warning("lime not installed — using fallback.")
            return self._explain_local_builtin(X, sample_indices, method="builtin")
        except Exception as exc:
            logger.warning("LIME explanation failed: %s — using fallback.", exc)
            return self._explain_local_builtin(X, sample_indices, method="builtin")

    def _explain_local_builtin(
        self,
        X: np.ndarray,
        sample_indices: list[int] | None,
        method: str = "builtin",
    ) -> list[LocalExplanation]:
        """Fallback: explain using built-in feature importance."""
        global_imp = self.explain_global_builtin(X)

        if sample_indices is None:
            sample_indices = list(range(len(X)))

        predictions = self.model.predict(X) if hasattr(self.model, "predict") else np.zeros(len(X))

        explanations: list[LocalExplanation] = []
        for idx in sample_indices:
            # Use global importance as proxy for local contribution
            contributions = []
            for feat in global_imp.feature_importance:
                contributions.append(FeatureImportance(
                    feature_name=feat.feature_name,
                    importance=feat.importance * float(X[idx, 0]),  # Rough proxy
                ))
            explanations.append(LocalExplanation(
                sample_index=idx,
                base_value=float(np.mean(predictions)),
                prediction=float(predictions[idx]) if hasattr(predictions, "__getitem__") else 0.0,
                feature_contributions=contributions,
                method=method,
            ))
        return explanations

    def explain_global_builtin(self, X: np.ndarray | None = None) -> GlobalExplanation:
        """Get global feature importance from model builtins."""
        n_features = len(self.feature_names) or (X.shape[1] if X is not None else 0)
        importances = np.zeros(n_features)

        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
        elif hasattr(self.model, "coef_"):
            coef = self.model.coef_
            if coef.ndim > 1:
                importances = np.mean(np.abs(coef), axis=0)
            else:
                importances = np.abs(coef)
        else:
            # No built-in importance available
            logger.warning("Model has no feature_importances_ or coef_ — returning zeros.")

        feature_imp = []
        for i, name in enumerate(self.feature_names or [f"f{i}" for i in range(len(importances))]):
            feature_imp.append(FeatureImportance(
                feature_name=name,
                importance=float(importances[i]) if i < len(importances) else 0.0,
            ))

        # Sort by absolute importance and assign ranks
        feature_imp.sort(key=lambda f: abs(f.importance), reverse=True)
        for rank, feat in enumerate(feature_imp):
            feat.rank = rank + 1

        return GlobalExplanation(
            feature_importance=feature_imp,
            method="builtin",
            n_samples=X.shape[0] if X is not None else 0,
            model_type=self._model_type,
        )

    def explain_global_shap(self, X: np.ndarray) -> GlobalExplanation:
        """Get global feature importance using SHAP.

        Args:
            X: Feature matrix.

        Returns:
            GlobalExplanation with mean absolute SHAP values.
        """
        if not self._init_shap(X):
            return self.explain_global_builtin(X)

        try:
            shap_values = self._shap_explainer.shap_values(X)
            if isinstance(shap_values, list):
                shap_values = shap_values[-1] if len(shap_values) > 1 else shap_values[0]
            if shap_values.ndim == 3:
                shap_values = shap_values[:, :, -1]

            mean_abs = np.mean(np.abs(shap_values), axis=0)

            feature_imp = []
            for i, name in enumerate(self.feature_names or [f"f{i}" for i in range(len(mean_abs))]):
                feature_imp.append(FeatureImportance(
                    feature_name=name,
                    importance=float(mean_abs[i]),
                ))

            feature_imp.sort(key=lambda f: abs(f.importance), reverse=True)
            for rank, feat in enumerate(feature_imp):
                feat.rank = rank + 1

            return GlobalExplanation(
                feature_importance=feature_imp,
                method="shap",
                n_samples=X.shape[0],
                model_type=self._model_type,
            )
        except Exception as exc:
            logger.warning("SHAP global explanation failed: %s — using fallback.", exc)
            return self.explain_global_builtin(X)

    def explain(
        self,
        X: np.ndarray,
        method: str = "shap",
        local: bool = True,
        global_: bool = True,
        sample_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        """Explain model predictions (convenience method).

        Args:
            X: Feature matrix.
            method: "shap", "lime", or "builtin".
            local: Whether to compute local explanations.
            global_: Whether to compute global explanation.
            sample_indices: Samples for local explanation.

        Returns:
            Dict with "local" and "global" keys.
        """
        result: dict[str, Any] = {}

        if local:
            if method == "shap":
                result["local"] = self.explain_local_shap(X, sample_indices)
            elif method == "lime":
                result["local"] = self.explain_local_lime(X, sample_indices)
            else:
                result["local"] = self._explain_local_builtin(X, sample_indices)

        if global_:
            if method == "shap":
                result["global"] = self.explain_global_shap(X)
            else:
                result["global"] = self.explain_global_builtin(X)

        return result
