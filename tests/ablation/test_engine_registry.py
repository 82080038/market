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
        assert len(registry) == 42
        assert "astronacci" in registry
        assert "volume" in registry
        assert "meta" in registry
        assert "fundamental" in registry
        assert "mc_sentiment" in registry
        assert "mc_flow" in registry
        assert "mc_cross_market" in registry
        assert "mc_astronacci" in registry
        assert "multi_factor" in registry
        assert "pred_ma" in registry
        assert "pred_momentum" in registry
        assert "pred_pattern" in registry
        assert "pred_vol_adj" in registry
        assert "vta_reasoning" in registry
        assert "causal_discovery" in registry
        assert "denoised_news" in registry
        assert "spillover_lab" in registry

    def test_categories(self):
        registry = create_default_registry()
        se_engines = registry.by_category(EngineCategory.SIGNAL_ENHANCER)
        mc_engines = registry.by_category(EngineCategory.MARKET_CONTEXT)
        assert len(se_engines) == 11  # 8 enabled + 3 new (vta, causal, denoised)
        assert len(mc_engines) == 13  # 7 original + 4 mc_* + 1 multi_factor + 1 spillover_lab
        pc_engines = registry.by_category(EngineCategory.PREDICTION_CORE)
        assert len(pc_engines) == 4  # pred_ma, pred_momentum, pred_pattern, pred_vol_adj

    def test_default_weights(self):
        registry = create_default_registry()
        assert registry.get("meta").default_weight == 0.20
        assert registry.get("astronacci").default_weight == 0.06
        assert registry.get("volume").default_weight == 0.15
        assert registry.get("fundamental").default_weight == 0.14
        assert registry.get("mc_sentiment").default_weight == 0.07
        assert registry.get("mc_flow").default_weight == 0.09
        assert registry.get("mc_cross_market").default_weight == 0.06
        assert registry.get("mc_astronacci").default_weight == 0.03
        assert registry.get("multi_factor").default_weight == 0.14
        assert registry.get("pred_ma").default_weight == 0.25
        assert registry.get("pred_momentum").default_weight == 0.25
        assert registry.get("pred_pattern").default_weight == 0.30
        assert registry.get("pred_vol_adj").default_weight == 0.25
        assert registry.get("vta_reasoning").default_weight == 0.10
        assert registry.get("causal_discovery").default_weight == 0.08
        assert registry.get("denoised_news").default_weight == 0.10
        assert registry.get("spillover_lab").default_weight == 0.06

    def test_all_enabled(self):
        registry = create_default_registry()
        enabled = registry.enabled_entries()
        assert len(enabled) == 28  # 42 total - 14 disabled (9 BUANG + 5 PERTIMBANGKAN)
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
        assert len(names) == 42

    def test_disabled_engines(self):
        """Verify that 14 non-production engines are disabled."""
        registry = create_default_registry()
        disabled = [e for e in registry._entries.values() if not e.enabled]
        assert len(disabled) == 14
        disabled_names = {e.name for e in disabled}
        # 9 BUANG (redundant/overlap)
        assert "mean_reversion" in disabled_names
        assert "reversal" in disabled_names
        assert "ewma_momentum" in disabled_names
        assert "commodity_v2" in disabled_names
        assert "sector_v2" in disabled_names
        assert "volume_v2" in disabled_names
        assert "event_v2" in disabled_names
        assert "ml_v2" in disabled_names
        assert "foreign_flow" in disabled_names
        # 5 PERTIMBANGKAN (unique but not wired, pending ablation test)
        assert "regime_switch" in disabled_names
        assert "dcc_garch" in disabled_names
        assert "spillover_dy" in disabled_names
        assert "overnight_idx" in disabled_names
        assert "sector_global_link" in disabled_names

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
