"""Tests for Model Registry file persistence (Gap #37)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from market.mlops.registry import ModelAlias, ModelRegistry, ModelVersion


def test_registry_in_memory_default():
    """Registry without persist_path is in-memory only (backward compat)."""
    reg = ModelRegistry()
    reg.register("m1", "lstm", "1.0.0", {"sharpe": 1.5}, "2024-01-01", "cpu", 100)
    assert reg.count == 1

    # save() should raise without persist_path
    with pytest.raises(RuntimeError, match="in-memory only"):
        reg.save()


def test_registry_persist_to_file(tmp_path: Path):
    """Registry with persist_path saves to JSON file."""
    persist = tmp_path / "registry.json"
    reg = ModelRegistry(persist_path=persist)
    reg.register(
        "m1", "lstm", "1.0.0",
        metrics={"sharpe": 1.5, "max_drawdown": -0.1},
        trained_at="2024-01-01T00:00:00Z",
        device="cpu",
        n_samples=1000,
        config={"lr": 0.01},
        alias=ModelAlias.CHAMPION,
    )

    assert persist.exists()
    data = json.loads(persist.read_text())
    assert "models" in data
    assert "m1" in data["models"]
    assert data["models"]["m1"]["model_type"] == "lstm"
    assert data["models"]["m1"]["metrics"]["sharpe"] == 1.5
    assert data["aliases"]["@champion"] == "m1"


def test_registry_load_from_file(tmp_path: Path):
    """Registry auto-loads from persist file on init."""
    persist = tmp_path / "registry.json"

    # First instance: register and auto-save
    reg1 = ModelRegistry(persist_path=persist)
    reg1.register("m1", "lstm", "1.0.0", {"sharpe": 1.2}, "2024-01-01", "cpu", 500)
    reg1.assign_alias("m1", ModelAlias.CHAMPION)
    assert persist.exists()

    # Second instance: should auto-load
    reg2 = ModelRegistry(persist_path=persist)
    assert reg2.count == 1
    assert reg2.champion is not None
    assert reg2.champion.model_id == "m1"
    assert reg2.champion.metrics["sharpe"] == 1.2


def test_registry_persist_promote(tmp_path: Path):
    """Promotion is persisted to file."""
    persist = tmp_path / "registry.json"
    reg = ModelRegistry(persist_path=persist)
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100,
                 alias=ModelAlias.EXPERIMENT)

    # Promote experiment → candidate
    reg.promote("m1")
    assert reg.candidate is not None

    # Reload and verify
    reg2 = ModelRegistry(persist_path=persist)
    assert reg2.candidate is not None
    assert reg2.candidate.model_id == "m1"


def test_registry_persist_rollback(tmp_path: Path):
    """Rollback is persisted to file."""
    persist = tmp_path / "registry.json"
    reg = ModelRegistry(persist_path=persist)
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100)
    reg.register("m2", "lstm", "1.1.0", {}, "2024-01-02", "cpu", 100)
    reg.assign_alias("m2", ModelAlias.CHAMPION)

    reg.rollback()
    assert reg.champion.model_id == "m1"

    reg2 = ModelRegistry(persist_path=persist)
    assert reg2.champion is not None
    assert reg2.champion.model_id == "m1"


def test_registry_persist_archive(tmp_path: Path):
    """Archive is persisted to file."""
    persist = tmp_path / "registry.json"
    reg = ModelRegistry(persist_path=persist)
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100,
                 alias=ModelAlias.EXPERIMENT)
    reg.archive("m1")

    reg2 = ModelRegistry(persist_path=persist)
    model = reg2.get("m1")
    assert model.status == "archived"
    assert len(model.aliases) == 0


def test_registry_persist_config_field(tmp_path: Path):
    """Config dict with nested values is persisted correctly."""
    persist = tmp_path / "registry.json"
    reg = ModelRegistry(persist_path=persist)
    reg.register(
        "m1", "lightgbm", "2.0.0",
        metrics={"accuracy": 0.55},
        trained_at="2024-06-01",
        device="cuda:1",
        n_samples=50000,
        config={
            "max_depth": 5,
            "n_estimators": 300,
            "lr": 0.03,
            "feature_names": ["rsi_rank", "ma_ratio_zscore", "vol_pctile"],
        },
    )

    reg2 = ModelRegistry(persist_path=persist)
    model = reg2.get("m1")
    assert model.config["max_depth"] == 5
    assert model.config["n_estimators"] == 300
    assert model.config["feature_names"] == ["rsi_rank", "ma_ratio_zscore", "vol_pctile"]


def test_registry_load_nonexistent_file(tmp_path: Path):
    """Loading from non-existent file is a no-op (empty registry)."""
    persist = tmp_path / "nonexistent.json"
    reg = ModelRegistry(persist_path=persist)
    assert reg.count == 0
    assert not persist.exists()


def test_registry_atomic_write(tmp_path: Path):
    """Save uses atomic write (temp file + rename) — no corruption on crash."""
    persist = tmp_path / "registry.json"
    reg = ModelRegistry(persist_path=persist)
    reg.register("m1", "lstm", "1.0.0", {}, "2024-01-01", "cpu", 100)

    # No .tmp file should remain after save
    assert not (tmp_path / "registry.tmp").exists()
    assert persist.exists()


def test_model_version_to_dict_from_dict_roundtrip():
    """ModelVersion serialization is a clean roundtrip."""
    mv = ModelVersion(
        model_id="test1",
        model_type="lightgbm",
        version="1.0.0",
        metrics={"sharpe": 1.5},
        trained_at="2024-01-01",
        device="cpu",
        n_samples=1000,
        config={"lr": 0.01},
        aliases=["@champion"],
    )
    d = mv.to_dict()
    mv2 = ModelVersion.from_dict(d)
    assert mv2.model_id == mv.model_id
    assert mv2.model_type == mv.model_type
    assert mv2.metrics == mv.metrics
    assert mv2.config == mv.config
    assert mv2.aliases == mv.aliases
