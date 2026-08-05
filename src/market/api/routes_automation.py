"""Automation & leverage endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from market.api._engines import engines
from market.api._shared import _dataclass_to_dict
from market.execution.automation import (
    AutomationConfig,
    ExecutionMode,
    MarketScope,
    SignalSource,
)
from market.risk.leverage import LeverageConfig, get_asset_class_leverage_max

router = APIRouter(prefix="/api", tags=["automation"])


@router.get("/automation/config")
async def get_automation_config() -> dict[str, Any]:
    """Get current automation config and gate status."""
    config = engines.automation_orchestrator.config
    gate_result = engines.automation_orchestrator.last_gate_result
    return {
        "config": _dataclass_to_dict(config) if config else None,
        "gate_result": _dataclass_to_dict(gate_result) if gate_result else None,
        "last_plan": (
            _dataclass_to_dict(engines.automation_orchestrator.last_plan)
            if engines.automation_orchestrator.last_plan else None
        ),
        "last_execution": (
            _dataclass_to_dict(engines.automation_orchestrator.last_execution)
            if engines.automation_orchestrator.last_execution else None
        ),
        "available_sources": [s.value for s in SignalSource],
        "available_scopes": [s.value for s in MarketScope],
        "available_modes": [m.value for m in ExecutionMode],
    }


@router.post("/automation/config")
async def set_automation_config(body: dict[str, Any]) -> dict[str, Any]:
    """Set automation config and run gate check.

    Request body:
        enabled_sources: list[str] — signal sources to enable
        market_scope: list[str] — market scopes (idx, global, multi_asset)
        execution_mode: str — manual, semi_auto, full_auto
        min_confidence: float — minimum confidence (0-100)
        max_orders_per_session: int
        max_value_per_session: float
        auto_sell: bool
        auto_rebalance: bool
        confirmed_paper_30d: bool
        confirmed_risk_understood: bool
        confirmed_risk_limits: bool
    """
    sources = {SignalSource(s) for s in body.get("enabled_sources", [])}
    scopes = {MarketScope(s) for s in body.get("market_scope", [])}
    mode = ExecutionMode(body.get("execution_mode", "manual"))

    config = AutomationConfig(
        enabled_sources=sources,
        market_scope=scopes,
        execution_mode=mode,
        min_confidence=float(body.get("min_confidence", 65.0)),
        max_orders_per_session=int(body.get("max_orders_per_session", 5)),
        max_value_per_session=float(
            body.get("max_value_per_session", 50_000_000)
        ),
        auto_sell=bool(body.get("auto_sell", False)),
        auto_rebalance=bool(body.get("auto_rebalance", False)),
        confirmed_paper_30d=bool(body.get("confirmed_paper_30d", False)),
        confirmed_risk_understood=bool(body.get("confirmed_risk_understood", False)),
        confirmed_risk_limits=bool(body.get("confirmed_risk_limits", False)),
    )

    gate_result = engines.automation_orchestrator.configure(config)
    return {
        "config": (
            _dataclass_to_dict(engines.automation_orchestrator.config)
            if engines.automation_orchestrator.config else None
        ),
        "gate_result": _dataclass_to_dict(gate_result),
    }


@router.post("/automation/plan")
async def prepare_automation_plan(body: dict[str, Any]) -> dict[str, Any]:
    """Prepare execution plan from signals (no execution).

    Request body:
        signals: list of {ticker, side, source, confidence, price, recommendation}
    """
    signals = body.get("signals", [])
    plan = engines.automation_orchestrator.prepare_plan(signals)
    return dict(_dataclass_to_dict(plan))


@router.post("/automation/execute")
async def execute_automation(body: dict[str, Any]) -> dict[str, Any]:
    """Execute automation plan from signals.

    Runs full pipeline: gate -> plan -> execute.
    Request body:
        signals: list of {ticker, side, source, confidence, price, recommendation}
    """
    signals = body.get("signals", [])
    result = engines.automation_orchestrator.execute(signals)
    return dict(_dataclass_to_dict(result))


@router.post("/leverage/advise")
async def leverage_advise(body: dict[str, Any]) -> dict[str, Any]:
    """Get leverage recommendation with justification.

    Request body:
        ticker: str
        capital: float — modal yang dialokasikan (IDR)
        price: float — harga saat ini
        asset_class: str — equity, etf, bond, commodity, forex, crypto, derivative
        kelly_fraction: float (optional) — 0-1
        win_rate: float (optional) — 0-1
        avg_win: float (optional) — %
        avg_loss: float (optional) — %
        volatility_pct: float (optional) — annualized %
        drawdown_pct: float (optional) — current drawdown %
        confidence: float (optional) — 0-100
        circuit_breaker: bool (optional)
        stop_loss: float (optional)
        leverage_enabled: bool (optional) — user toggle
        max_leverage: float (optional) — user cap
        confirmed_risk: bool (optional)
        confirmed_margin_call: bool (optional)
        confirmed_liquidation: bool (optional)
    """
    ticker = body.get("ticker", "UNKNOWN")
    capital = float(body.get("capital", 10_000_000))
    price = float(body.get("price", 1000))
    asset_class = body.get("asset_class", "equity")
    asset_max = get_asset_class_leverage_max(asset_class)

    lev_config = LeverageConfig(
        enabled=bool(body.get("leverage_enabled", False)),
        max_leverage=float(body.get("max_leverage", 2.0)),
        confirmed_risk=bool(body.get("confirmed_risk", False)),
        confirmed_margin_call=bool(body.get("confirmed_margin_call", False)),
        confirmed_liquidation=bool(body.get("confirmed_liquidation", False)),
    )

    kelly_raw = body.get("kelly_fraction")
    kelly = float(kelly_raw) if kelly_raw is not None else None
    win_raw = body.get("win_rate")
    win_rate = float(win_raw) if win_raw is not None else None
    aw_raw = body.get("avg_win")
    avg_win = float(aw_raw) if aw_raw is not None else None
    al_raw = body.get("avg_loss")
    avg_loss = float(al_raw) if al_raw is not None else None
    vol_raw = body.get("volatility_pct")
    vol = float(vol_raw) if vol_raw is not None else None
    dd_raw = body.get("drawdown_pct")
    dd = float(dd_raw) if dd_raw is not None else 0.0
    conf_raw = body.get("confidence")
    conf = float(conf_raw) if conf_raw is not None else 100.0
    sl_raw = body.get("stop_loss")
    sl = float(sl_raw) if sl_raw is not None else 0.0

    rec = engines.leverage_advisor.advise(
        ticker=ticker,
        capital=capital,
        price=price,
        asset_class_max=asset_max,
        kelly_fraction=kelly,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        volatility_pct=vol,
        drawdown_pct=dd,
        confidence=conf,
        circuit_breaker_triggered=bool(body.get("circuit_breaker", False)),
        leverage_config=lev_config,
        stop_loss=sl,
    )
    return dict(_dataclass_to_dict(rec))
