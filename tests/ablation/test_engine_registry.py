"""Tests for engine registry."""

from __future__ import annotations

import pytest

from market.ablation.engine_registry import (
    EngineCategory,
    EngineEntry,
    EngineRegistry,
    SignalType,
    create_default_registry,
)


class TestEngineRegistry:
    def test_create_default_registry(self):
        registry = create_default_registry()
        assert len(registry) == 29
        assert "astronacci" in registry
        assert "volume" in registry
        assert "meta" in registry
        assert "fundamental" in registry

    def test_categories(self):
        registry = create_default_registry()
        se_engines = registry.by_category(EngineCategory.SIGNAL_ENHANCER)
        mc_engines = registry.by_category(EngineCategory.MARKET_CONTEXT)
        assert len(se_engines) == 22  # 8 original + 4 alpha + 5 v2 + 4 advanced global-IDX + 1 sector-global-link
        assert len(mc_engines) == 7

    def test_default_weights(self):
        registry = create_default_registry()
        assert registry.get("meta").default_weight == 0.20
        assert registry.get("astronacci").default_weight == 0.06
        assert registry.get("volume").default_weight == 0.15
        assert registry.get("fundamental").default_weight == 0.14

    def test_all_enabled(self):
        registry = create_default_registry()
        enabled = registry.enabled_entries()
        assert len(enabled) == 29
        assert all(e.enabled for e in enabled)

    def test_duplicate_registration_raises(self):
        registry = EngineRegistry()
        entry = EngineEntry(
            name="test",
            category=EngineCategory.SIGNAL_ENHANCER,
            signal_type=SignalType.DIRECTIONAL,
            default_weight=0.1,
            purpose="test",
            description="test",
            module="test",
            data_tables=[],
            factory=lambda: None,
        )
        registry.register(entry)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(entry)

    def test_get_unknown_returns_none(self):
        registry = EngineRegistry()
        assert registry.get("nonexistent") is None

    def test_names(self):
        registry = create_default_registry()
        names = registry.names()
        assert "astronacci" in names
        assert len(names) == 29

    def test_by_category_filters_disabled(self):
        registry = EngineRegistry()
        registry.register(EngineEntry(
            name="active",
            category=EngineCategory.SIGNAL_ENHANCER,
            signal_type=SignalType.DIRECTIONAL,
            default_weight=0.1,
            purpose="active",
            description="active",
            module="test",
            data_tables=[],
            factory=lambda: None,
            enabled=True,
        ))
        registry.register(EngineEntry(
            name="inactive",
            category=EngineCategory.SIGNAL_ENHANCER,
            signal_type=SignalType.DIRECTIONAL,
            default_weight=0.1,
            purpose="inactive",
            description="inactive",
            module="test",
            data_tables=[],
            factory=lambda: None,
            enabled=False,
        ))
        result = registry.by_category(EngineCategory.SIGNAL_ENHANCER)
        assert len(result) == 1
        assert result[0].name == "active"
