"""Model registry with aliases (pustaka/51 §3).

In-memory model registry supporting:
- Model versioning with semantic versions
- Aliases: @experiment, @candidate, @champion
- Model metadata (metrics, config, training info)
- Promotion workflow (experiment → candidate → champion)
- Rollback capability
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ModelAlias(Enum):
    """Model alias enumeration."""

    EXPERIMENT = "@experiment"
    CANDIDATE = "@candidate"
    CHAMPION = "@champion"


@dataclass
class ModelVersion:
    """A registered model version."""

    model_id: str
    model_type: str
    version: str
    metrics: dict[str, float]
    trained_at: str
    device: str
    n_samples: int
    config: dict[str, Any] = field(default_factory=dict)
    status: str = "registered"  # registered, active, archived
    aliases: list[str] = field(default_factory=list)
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_champion(self) -> bool:
        return ModelAlias.CHAMPION.value in self.aliases

    @property
    def is_candidate(self) -> bool:
        return ModelAlias.CANDIDATE.value in self.aliases

    @property
    def is_experiment(self) -> bool:
        return ModelAlias.EXPERIMENT.value in self.aliases


class ModelRegistry:
    """In-memory model registry with alias management."""

    def __init__(self) -> None:
        self._models: dict[str, ModelVersion] = {}
        self._aliases: dict[str, str] = {}  # alias -> model_id
        self._counter = 0

    def register(
        self,
        model_id: str,
        model_type: str,
        version: str,
        metrics: dict[str, float],
        trained_at: str,
        device: str,
        n_samples: int,
        config: dict[str, Any] | None = None,
        alias: ModelAlias | None = None,
    ) -> ModelVersion:
        """Register a new model version.

        Args:
            model_id: Unique model identifier.
            model_type: Model type (lstm, lightgbm, etc.).
            version: Semantic version string.
            metrics: Training/eval metrics.
            trained_at: ISO timestamp.
            device: Device used for training.
            n_samples: Number of training samples.
            config: Model configuration.
            alias: Optional initial alias.

        Returns:
            The registered ModelVersion.
        """
        mv = ModelVersion(
            model_id=model_id,
            model_type=model_type,
            version=version,
            metrics=metrics,
            trained_at=trained_at,
            device=device,
            n_samples=n_samples,
            config=config or {},
        )

        if alias:
            mv.aliases.append(alias.value)
            self._aliases[alias.value] = model_id

        self._models[model_id] = mv
        self._counter += 1
        return mv

    def get(self, model_id: str) -> ModelVersion | None:
        """Get a model by ID."""
        return self._models.get(model_id)

    def get_by_alias(self, alias: str) -> ModelVersion | None:
        """Get a model by alias (e.g. @champion)."""
        mid = self._aliases.get(alias)
        if mid is None:
            return None
        return self._models.get(mid)

    def list_models(self, model_type: str | None = None) -> list[ModelVersion]:
        """List all registered models, optionally filtered by type."""
        models = list(self._models.values())
        if model_type:
            models = [m for m in models if m.model_type == model_type]
        return models

    def assign_alias(self, model_id: str, alias: ModelAlias) -> bool:
        """Assign an alias to a model. Removes alias from previous holder.

        Args:
            model_id: Model to assign alias to.
            alias: Alias to assign.

        Returns:
            True if successful, False if model not found.
        """
        model = self._models.get(model_id)
        if model is None:
            return False

        # Remove alias from previous holder
        prev_id = self._aliases.get(alias.value)
        if prev_id and prev_id != model_id:
            prev_model = self._models.get(prev_id)
            if prev_model and alias.value in prev_model.aliases:
                prev_model.aliases.remove(alias.value)

        # Assign to new model
        if alias.value not in model.aliases:
            model.aliases.append(alias.value)
        self._aliases[alias.value] = model_id
        return True

    def promote(self, model_id: str) -> bool:
        """Promote a model: experiment → candidate → champion.

        Args:
            model_id: Model to promote.

        Returns:
            True if successful.
        """
        model = self._models.get(model_id)
        if model is None:
            return False

        if model.is_experiment:
            # Remove experiment alias, assign candidate
            if ModelAlias.EXPERIMENT.value in model.aliases:
                model.aliases.remove(ModelAlias.EXPERIMENT.value)
            if ModelAlias.EXPERIMENT.value in self._aliases:
                del self._aliases[ModelAlias.EXPERIMENT.value]
            return self.assign_alias(model_id, ModelAlias.CANDIDATE)
        if model.is_candidate:
            # Remove candidate alias, assign champion
            if ModelAlias.CANDIDATE.value in model.aliases:
                model.aliases.remove(ModelAlias.CANDIDATE.value)
            if ModelAlias.CANDIDATE.value in self._aliases:
                del self._aliases[ModelAlias.CANDIDATE.value]
            return self.assign_alias(model_id, ModelAlias.CHAMPION)
        if not model.aliases:
            return self.assign_alias(model_id, ModelAlias.EXPERIMENT)
        return False

    def rollback(self) -> ModelVersion | None:
        """Rollback champion to the previous champion.

        Returns:
            The new champion ModelVersion, or None if no rollback possible.
        """
        champion = self.get_by_alias(ModelAlias.CHAMPION.value)
        if champion is None:
            return None

        # Find the most recent non-champion model of same type
        candidates = [
            m for m in self.list_models(champion.model_type)
            if m.model_id != champion.model_id and m.status == "registered"
        ]
        if not candidates:
            return None

        # Sort by registered_at descending
        candidates.sort(key=lambda m: m.registered_at, reverse=True)
        new_champion = candidates[0]

        # Archive current champion
        champion.status = "archived"
        champion.aliases.remove(ModelAlias.CHAMPION.value)

        # Promote new champion
        self.assign_alias(new_champion.model_id, ModelAlias.CHAMPION)
        return new_champion

    def archive(self, model_id: str) -> bool:
        """Archive a model.

        Args:
            model_id: Model to archive.

        Returns:
            True if successful.
        """
        model = self._models.get(model_id)
        if model is None:
            return False
        model.status = "archived"
        # Remove all aliases
        for alias in model.aliases:
            if self._aliases.get(alias) == model_id:
                del self._aliases[alias]
        model.aliases.clear()
        return True

    @property
    def champion(self) -> ModelVersion | None:
        """Get current champion model."""
        return self.get_by_alias(ModelAlias.CHAMPION.value)

    @property
    def candidate(self) -> ModelVersion | None:
        """Get current candidate model."""
        return self.get_by_alias(ModelAlias.CANDIDATE.value)

    @property
    def experiment(self) -> ModelVersion | None:
        """Get current experiment model."""
        return self.get_by_alias(ModelAlias.EXPERIMENT.value)

    @property
    def count(self) -> int:
        """Total registered models."""
        return len(self._models)
