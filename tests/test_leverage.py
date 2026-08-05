"""Tests for Leverage Advisor (pustaka/18 §6.1, pustaka/31, pustaka/07)."""

from __future__ import annotations

from market.risk.leverage import (
    LeverageAdvisor,
    LeverageConfig,
    LeverageLevel,
    get_asset_class_leverage_max,
)


def _full_lev_config(**overrides) -> LeverageConfig:
    defaults: dict = {
        "enabled": True,
        "max_leverage": 5.0,
        "confirmed_risk": True,
        "confirmed_margin_call": True,
        "confirmed_liquidation": True,
    }
    defaults.update(overrides)
    return LeverageConfig(**defaults)


# ---------------------------------------------------------------------------
# LeverageConfig tests
# ---------------------------------------------------------------------------


class TestLeverageConfig:
    def test_default_disabled(self):
        config = LeverageConfig()
        assert not config.enabled
        assert not config.is_ready()

    def test_is_ready(self):
        config = _full_lev_config()
        assert config.is_ready()

    def test_not_ready_missing_confirmation(self):
        config = _full_lev_config(confirmed_margin_call=False)
        assert not config.is_ready()

    def test_not_ready_disabled(self):
        config = _full_lev_config(enabled=False)
        assert not config.is_ready()


# ---------------------------------------------------------------------------
# LeverageAdvisor tests
# ---------------------------------------------------------------------------


class TestLeverageAdvisor:
    def test_disabled_returns_no_leverage(self):
        advisor = LeverageAdvisor()
        config = LeverageConfig(enabled=False)
        rec = advisor.advise(
            ticker="BBCA.JK",
            capital=10_000_000,
            price=8500,
            asset_class_max=1.0,
            leverage_config=config,
        )
        assert rec.recommended_leverage == 1.0
        assert rec.level == LeverageLevel.NONE
        assert not rec.can_apply
        assert rec.rejection_reason == "LEVERAGE_DISABLED"

    def test_circuit_breaker_returns_no_leverage(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config()
        rec = advisor.advise(
            ticker="BBCA.JK",
            capital=10_000_000,
            price=8500,
            asset_class_max=10.0,
            circuit_breaker_triggered=True,
            leverage_config=config,
        )
        assert rec.recommended_leverage == 1.0
        assert not rec.can_apply
        assert rec.rejection_reason == "CIRCUIT_BREAKER"

    def test_asset_class_no_leverage(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config()
        rec = advisor.advise(
            ticker="BBCA.JK",
            capital=10_000_000,
            price=8500,
            asset_class_max=1.0,
            leverage_config=config,
        )
        assert rec.recommended_leverage == 1.0
        assert not rec.can_apply
        assert rec.rejection_reason == "ASSET_NO_LEVERAGE"

    def test_missing_confirmation(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(confirmed_risk=False)
        rec = advisor.advise(
            ticker="BBCA.JK",
            capital=10_000_000,
            price=8500,
            asset_class_max=10.0,
            leverage_config=config,
        )
        assert rec.recommended_leverage == 1.0
        assert not rec.can_apply
        assert rec.rejection_reason == "CONFIRMATION_INCOMPLETE"

    def test_kelly_based_leverage(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=10.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.25,
            leverage_config=config,
        )
        # theoretical = 1/(1-0.25) = 1.333
        assert rec.recommended_leverage > 1.0
        assert rec.can_apply
        assert rec.theoretical_kelly_leverage > 1.0

    def test_win_rate_based_leverage(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=10.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            win_rate=0.65,
            avg_win=3.0,
            avg_loss=1.5,
            leverage_config=config,
        )
        assert rec.recommended_leverage > 1.0
        assert rec.can_apply

    def test_volatility_haircut(self):
        advisor = LeverageAdvisor(target_vol_pct=20.0)
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.4,
            volatility_pct=40.0,
            leverage_config=config,
        )
        # Vol 40% > target 20% → haircut 0.5
        vol_haircut = [h for h in rec.haircuts if h.name == "volatility"]
        assert len(vol_haircut) == 1
        assert vol_haircut[0].factor == 0.5
        assert rec.recommended_leverage < rec.theoretical_kelly_leverage

    def test_high_volatility_warning(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="BTC-USD",
            capital=10_000_000,
            price=50000,
            asset_class_max=5.0,
            kelly_fraction=0.3,
            volatility_pct=60.0,
            leverage_config=config,
        )
        assert any("sangat tinggi" in w for w in rec.warnings)

    def test_drawdown_haircut(self):
        advisor = LeverageAdvisor(max_drawdown_pct=10.0)
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.4,
            drawdown_pct=5.0,
            leverage_config=config,
        )
        dd_haircut = [h for h in rec.haircuts if h.name == "drawdown"]
        assert len(dd_haircut) == 1
        assert dd_haircut[0].factor == 0.5

    def test_drawdown_near_threshold_warning(self):
        advisor = LeverageAdvisor(max_drawdown_pct=10.0)
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.4,
            drawdown_pct=8.0,
            leverage_config=config,
        )
        assert any("mendekati threshold" in w for w in rec.warnings)

    def test_confidence_haircut(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.4,
            confidence=60.0,
            leverage_config=config,
        )
        conf_haircut = [h for h in rec.haircuts if h.name == "confidence"]
        assert len(conf_haircut) == 1
        assert conf_haircut[0].factor == 0.6

    def test_low_confidence_warning(self):
        advisor = LeverageAdvisor(min_confidence=70.0)
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.4,
            confidence=50.0,
            leverage_config=config,
        )
        assert any("di bawah minimum" in w for w in rec.warnings)

    def test_cap_at_asset_max(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=100.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=10.0,
            kelly_fraction=0.8,
            leverage_config=config,
        )
        assert rec.recommended_leverage <= 10.0

    def test_cap_at_user_max(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=2.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.8,
            leverage_config=config,
        )
        assert rec.recommended_leverage <= 2.0

    def test_leverage_floor_1(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.0,
            drawdown_pct=9.0,
            confidence=30.0,
            volatility_pct=80.0,
            leverage_config=config,
        )
        assert rec.recommended_leverage >= 1.0

    def test_margin_and_liquidation(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=10.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.5,
            leverage_config=config,
        )
        # theoretical = 1/(1-0.5) = 2.0
        assert rec.recommended_leverage > 1.0
        assert rec.leveraged_position_value > rec.effective_capital
        assert rec.liquidation_price > 0
        assert rec.liquidation_price < 1.08
        assert rec.max_loss_at_leverage > 0

    def test_max_loss_with_stop_loss(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=5.0)
        rec = advisor.advise(
            ticker="BBCA.JK",
            capital=10_000_000,
            price=8500,
            asset_class_max=10.0,
            kelly_fraction=0.3,
            stop_loss=8000,
            leverage_config=config,
        )
        assert rec.max_loss_at_leverage > 0
        # Max loss should be less than leveraged position value
        assert rec.max_loss_at_leverage < rec.leveraged_position_value

    def test_rationale_populated(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=10.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.3,
            volatility_pct=25.0,
            drawdown_pct=3.0,
            confidence=80.0,
            leverage_config=config,
        )
        assert "Kelly" in rec.rationale
        assert "haircut" in rec.rationale.lower()
        assert "Cap" in rec.rationale

    def test_conditions_populated(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=5.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.3,
            stop_loss=1.05,
            leverage_config=config,
        )
        assert len(rec.conditions) >= 2
        assert any("Stop loss" in c for c in rec.conditions)
        assert any("Liquidation" in c for c in rec.conditions)

    def test_high_leverage_monitor_condition(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=50.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            kelly_fraction=0.8,
            leverage_config=config,
        )
        if rec.recommended_leverage > 2.0:
            assert any("Monitor" in c for c in rec.conditions)

    def test_no_kelly_no_win_rate_defaults_to_1x(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=10.0)
        rec = advisor.advise(
            ticker="EURUSD",
            capital=10_000_000,
            price=1.08,
            asset_class_max=50.0,
            leverage_config=config,
        )
        # Without kelly or win_rate, theoretical = 1.0
        assert rec.theoretical_kelly_leverage == 1.0
        # After haircuts, still >= 1.0
        assert rec.recommended_leverage >= 1.0

    def test_level_classification(self):
        advisor = LeverageAdvisor()
        config = _full_lev_config(max_leverage=50.0)

        # Conservative: 1-2x
        rec = advisor.advise(
            ticker="EURUSD", capital=10_000_000, price=1.08,
            asset_class_max=50.0, kelly_fraction=0.2,
            leverage_config=config,
        )
        assert rec.level in (LeverageLevel.CONSERVATIVE, LeverageLevel.NONE)

        # Aggressive: 5-10x
        rec2 = advisor.advise(
            ticker="EURUSD", capital=10_000_000, price=1.08,
            asset_class_max=50.0, kelly_fraction=0.5,
            leverage_config=_full_lev_config(max_leverage=50.0),
        )
        assert rec2.recommended_leverage <= 50.0


# ---------------------------------------------------------------------------
# get_asset_class_leverage_max tests
# ---------------------------------------------------------------------------


class TestGetAssetClassLeverageMax:
    def test_equity(self):
        assert get_asset_class_leverage_max("equity") == 1.0

    def test_etf(self):
        assert get_asset_class_leverage_max("etf") == 1.0

    def test_bond(self):
        assert get_asset_class_leverage_max("bond") == 1.0

    def test_commodity(self):
        assert get_asset_class_leverage_max("commodity") == 10.0

    def test_forex(self):
        assert get_asset_class_leverage_max("forex") == 50.0

    def test_crypto(self):
        assert get_asset_class_leverage_max("crypto") == 5.0

    def test_derivative(self):
        assert get_asset_class_leverage_max("derivative") == 20.0

    def test_invalid(self):
        assert get_asset_class_leverage_max("invalid") == 1.0


# ---------------------------------------------------------------------------
# Integration with AutomationGate R11
# ---------------------------------------------------------------------------


class TestAutomationGateLeverage:
    def test_leverage_disabled_passes(self):
        from market.execution.automation import AutomationConfig, AutomationGate, ExecutionMode

        gate = AutomationGate(env="paper")
        config = AutomationConfig(
            execution_mode=ExecutionMode.MANUAL,
        )
        result = gate.check_config(config)
        r11 = [r for r in result.rules if r.rule_id == "R11_LEVERAGE"]
        assert len(r11) == 1
        assert r11[0].status.value == "pass"

    def test_leverage_enabled_no_confirmation_fails(self):
        from market.execution.automation import AutomationConfig, AutomationGate, ExecutionMode

        gate = AutomationGate(env="paper")
        config = AutomationConfig(
            execution_mode=ExecutionMode.SEMI_AUTO,
            enabled_sources={
                __import__(
                    "market.execution.automation", fromlist=["SignalSource"]
                ).SignalSource.SCREENING_AI
            },
            confirmed_paper_30d=True,
            confirmed_risk_understood=True,
            confirmed_risk_limits=True,
            leverage_config=_full_lev_config(confirmed_risk=False),
        )
        result = gate.check_config(config)
        r11 = [r for r in result.rules if r.rule_id == "R11_LEVERAGE"]
        assert r11[0].status.value == "fail"

    def test_leverage_enabled_with_confirmations_passes(self):
        from market.execution.automation import AutomationConfig, AutomationGate, ExecutionMode

        gate = AutomationGate(env="paper")
        config = AutomationConfig(
            execution_mode=ExecutionMode.SEMI_AUTO,
            enabled_sources={
                __import__(
                    "market.execution.automation", fromlist=["SignalSource"]
                ).SignalSource.SCREENING_AI
            },
            confirmed_paper_30d=True,
            confirmed_risk_understood=True,
            confirmed_risk_limits=True,
            leverage_config=_full_lev_config(),
        )
        result = gate.check_config(config)
        r11 = [r for r in result.rules if r.rule_id == "R11_LEVERAGE"]
        assert r11[0].status.value == "pass"

    def test_leverage_high_max_warning(self):
        from market.execution.automation import AutomationConfig, AutomationGate, ExecutionMode

        gate = AutomationGate(env="paper")
        config = AutomationConfig(
            execution_mode=ExecutionMode.SEMI_AUTO,
            enabled_sources={
                __import__(
                    "market.execution.automation", fromlist=["SignalSource"]
                ).SignalSource.SCREENING_AI
            },
            confirmed_paper_30d=True,
            confirmed_risk_understood=True,
            confirmed_risk_limits=True,
            leverage_config=_full_lev_config(max_leverage=15.0),
        )
        result = gate.check_config(config)
        r11 = [r for r in result.rules if r.rule_id == "R11_LEVERAGE"]
        assert r11[0].status.value == "warning"
