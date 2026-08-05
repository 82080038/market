"""FastAPI application for Market (pustaka/18 §8).

Endpoints:
    GET  /api/health              — health check
    GET  /api/env                 — environment config
    GET  /api/scores/{ticker}     — 6 factor scores for a ticker
    GET  /api/recommend/{ticker}  — composite recommendation with XAI
    GET  /api/advisory            — advisory report (screening → top picks)
    GET  /api/readiness/{ticker}  — instrument readiness assessment
    GET  /api/automation/config   — get automation config & gate status
    POST /api/automation/config   — set automation config (centang pilihan)
    POST /api/automation/plan     — prepare execution plan from signals
    POST /api/automation/execute  — execute plan via broker
    POST /api/leverage/advise     — leverage recommendation with justification
    GET  /api/autonomous-backtest/status  — autonomous backtest runner status
    GET  /api/autonomous-backtest/runs    — list of past autonomous backtest runs
    GET  /api/autonomous-backtest/latest  — latest autonomous backtest run details
    POST /api/autonomous-backtest/trigger — force trigger autonomous backtest (admin)
    POST /api/pattern/detect          — detect patterns (no look-ahead, as_of date)
    POST /api/prediction/predict      — predict next-period price (no look-ahead)
    POST /api/prediction/verify       — verify past prediction, track error + root cause
    GET  /api/prediction/errors       — prediction error summary with lessons
    GET  /api/prediction/risk/{ticker} — risk adjustment from prediction errors
    GET  /api/delisting/summary       — delisting memory summary
    GET  /api/delisting/records       — list all delisting records
    GET  /api/delisting/lessons       — AI lessons from delisting events
    GET  /api/delisting/check/{ticker} — check ticker for delisting/suspension/warnings
    POST /api/delisting/record        — record a delisting or suspension event
    POST /api/delisting/block         — block an instrument from portfolio
    POST /api/delisting/filter        — filter tickers for portfolio inclusion
    GET  /api/portfolio           — portfolio summary (NAV, positions, exposure)
    GET  /api/watchlist           — watchlist list
    POST /api/watchlist           — add to watchlist
    GET  /api/backtest/run        — run backtest (query params)
    GET  /api/markets             — market registry list
"""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from market.analysis.advisory import AdvisoryEngine
from market.analysis.decision import DecisionEngine
from market.analysis.delisting_memory import (
    DelistingReason,
    WarningPattern,
    WarningPatternType,
)
from market.analysis.pattern_detector import PatternDetector
from market.analysis.prediction import (
    PredictionEngine,
    PredictionMethod,
)
from market.analysis.profiling import InstrumentReadinessGate
from market.backtest.autonomous import (
    AutonomousBacktestRunner,
    BacktestTrigger,
)
from market.config import settings
from market.data.seed import DEFAULT_MARKETS
from market.execution.automation import (
    AutomationConfig,
    AutomationOrchestrator,
    ExecutionMode,
    MarketScope,
    SignalSource,
)
from market.risk.leverage import LeverageAdvisor, LeverageConfig, get_asset_class_leverage_max


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclass to dict for JSON serialization."""
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in obj.__dataclass_fields__:
            val = getattr(obj, f)
            result[f] = _dataclass_to_dict(val)
        return result
    if isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# --- Request/Response models ---


class WatchlistItem(BaseModel):
    ticker: str
    is_favorite: bool = False
    notes: str | None = None


class ScoreInput(BaseModel):
    technical: float | None = None
    fundamental: float | None = None
    macro: float | None = None
    global_market: float | None = None
    relationship: float | None = None
    sentiment: float | None = None


# --- Mock data helper ---

def _generate_mock_instruments() -> dict[str, Any]:
    """Generate mock OHLCV data for testing autonomous backtest."""
    import pandas as pd

    np_rng = np.random.RandomState(42)
    dates = pd.bdate_range("2023-01-01", periods=300)
    instruments: dict[str, pd.DataFrame] = {}

    for ticker in ["BBCA.JK", "BBRI.JK", "TLKM.JK"]:
        close = 8000 + np_rng.randn(300).cumsum() * 50
        instruments[ticker] = pd.DataFrame({
            "open": close + np_rng.randn(300) * 10,
            "high": close + abs(np_rng.randn(300) * 20),
            "low": close - abs(np_rng.randn(300) * 20),
            "close": close,
            "volume": np_rng.randint(100000, 1000000, 300).astype(float),
        }, index=dates)

    return instruments


# --- App factory ---


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Market API",
        description="Single-user capital market decision-support API.",
        version="0.1.0",
    )

    # In-memory stores (will be replaced by DB-backed in production)
    _watchlist: list[dict[str, Any]] = []

    # Engine instances
    decision_engine = DecisionEngine()
    advisory_engine = AdvisoryEngine(decision_engine)
    readiness_gate = InstrumentReadinessGate()
    automation_orchestrator = AutomationOrchestrator()
    leverage_advisor = LeverageAdvisor()
    autonomous_backtest_runner = AutonomousBacktestRunner()
    pattern_detector = PatternDetector()
    prediction_engine = PredictionEngine(pattern_detector=pattern_detector)
    delisting_memory = pattern_detector.delisting_memory

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.env}

    @app.get("/api/env")
    async def env() -> dict[str, Any]:
        return {
            "env": settings.env,
            "db_path": str(settings.resolved_db_path),
            "reporting_currency": settings.reporting_currency,
            "device": settings.device,
            "broker_adapter": settings.broker_adapter,
            "live_approved": settings.live_approved,
        }

    @app.get("/api/markets")
    async def markets() -> list[dict[str, Any]]:
        return list(DEFAULT_MARKETS)

    @app.get("/api/scores/{ticker}")
    async def get_scores(
        ticker: str,
        technical: float | None = Query(None),
        fundamental: float | None = Query(None),
        macro: float | None = Query(None),
        global_market: float | None = Query(None),
        relationship: float | None = Query(None),
        sentiment: float | None = Query(None),
    ) -> dict[str, Any]:
        """Get 6 factor scores for a ticker.

        If query params are provided, use them directly.
        Otherwise returns a placeholder structure.
        """
        if all(
            v is None
            for v in [technical, fundamental, macro, global_market, relationship, sentiment]
        ):
            return {
                "ticker": ticker,
                "message": "Provide factor scores as query params.",
                "factors": [
                    "technical", "fundamental", "macro",
                    "global", "relationship", "sentiment",
                ],
            }

        result = decision_engine.decide(
            ticker=ticker,
            technical=technical,
            fundamental=fundamental,
            macro=macro,
            global_market=global_market,
            relationship=relationship,
            sentiment=sentiment,
        )
        return dict(_dataclass_to_dict(result))

    @app.get("/api/recommend/{ticker}")
    async def recommend(
        ticker: str,
        technical: float | None = Query(None),
        fundamental: float | None = Query(None),
        macro: float | None = Query(None),
        global_market: float | None = Query(None),
        relationship: float | None = Query(None),
        sentiment: float | None = Query(None),
    ) -> dict[str, Any]:
        """Get composite recommendation with XAI breakdown."""
        result = decision_engine.decide(
            ticker=ticker,
            technical=technical,
            fundamental=fundamental,
            macro=macro,
            global_market=global_market,
            relationship=relationship,
            sentiment=sentiment,
        )
        return dict(_dataclass_to_dict(result))

    @app.get("/api/advisory")
    async def advisory(
        market_regime: str = Query("neutral"),
        min_composite: float = Query(50.0),
    ) -> dict[str, Any]:
        """Get advisory report with top picks.

        Pass universe as query param ticker=score pairs.
        Example: ?ticker=BBCA&tech=75&fund=80&sent=70&ticker=TLKM&tech=50&fund=60&sent=50
        """
        # Placeholder: empty universe returns empty report
        report = advisory_engine.generate_report(
            market_regime=market_regime,
            universe={},
            min_composite=min_composite,
        )
        return dict(_dataclass_to_dict(report))

    @app.get("/api/readiness/{ticker}")
    async def readiness(
        ticker: str,
        sector: str | None = Query(None),
        market_cap: float | None = Query(None),
        asset_class: str = Query("equity"),
        bars: int = Query(0, ge=0, le=10000),
    ) -> dict[str, Any]:
        """Get instrument readiness assessment.

        Evaluates whether the application has sufficient knowledge about
        an instrument before making screening/selection decisions.

        Query params:
            sector: Sector classification (e.g., 'energy', 'financials').
            market_cap: Market capitalization in IDR.
            asset_class: Asset class string (equity, etf, bond, etc.).
            bars: Number of OHLCV bars available (if no real data loaded).
        """
        import numpy as np
        import pandas as pd

        if bars > 0:
            dates = pd.date_range("2024-01-02", periods=bars, freq="B")
            rng = np.random.RandomState(42)
            returns = rng.normal(0.001, 0.01, bars)
            close = 100.0 * np.cumprod(1 + returns)
            high = close * (1 + np.abs(rng.normal(0, 0.005, bars)))
            low = close * (1 - np.abs(rng.normal(0, 0.005, bars)))
            op = close * (1 + rng.normal(0, 0.003, bars))
            volume = rng.randint(100_000, 1_000_000, bars).astype(float)
            df = pd.DataFrame(
                {"open": op, "high": high, "low": low, "close": close, "volume": volume},
                index=dates,
            )
        else:
            df = pd.DataFrame()

        report = readiness_gate.evaluate(
            ticker, df, sector=sector, market_cap=market_cap, asset_class=asset_class,
        )
        return dict(_dataclass_to_dict(report))

    @app.get("/api/portfolio")
    async def portfolio() -> dict[str, Any]:
        """Get portfolio summary placeholder."""
        return {
            "total_nav": 0.0,
            "cash": 0.0,
            "positions": {},
            "message": "Portfolio endpoint — connect to PortfolioEngine in production.",
        }

    @app.get("/api/watchlist")
    async def get_watchlist() -> list[dict[str, Any]]:
        return _watchlist

    @app.post("/api/watchlist")
    async def add_watchlist(item: WatchlistItem) -> dict[str, Any]:
        entry = {
            "ticker": item.ticker,
            "is_favorite": item.is_favorite,
            "notes": item.notes,
            "added_at": datetime.now(UTC).isoformat(),
        }
        _watchlist.append(entry)
        return {"status": "added", **entry}

    @app.delete("/api/watchlist/{ticker}")
    async def remove_watchlist(ticker: str) -> dict[str, str]:
        nonlocal _watchlist
        before = len(_watchlist)
        _watchlist = [w for w in _watchlist if w["ticker"] != ticker]
        if len(_watchlist) == before:
            raise HTTPException(status_code=404, detail="Ticker not in watchlist")
        return {"status": "removed", "ticker": ticker}

    @app.get("/api/backtest/run")
    async def run_backtest(
        ticker: str = Query(...),
        strategy: str = Query("buy_hold", pattern="^(buy_hold|ma_crossover|conviction)$"),
        n_days: int = Query(100, ge=30, le=1000),
    ) -> dict[str, Any]:
        """Run a simple backtest with synthetic data.

        In production, this would load real OHLCV from the database.
        """
        import numpy as np
        import pandas as pd

        from market.backtest.engine import BacktestEngine
        from market.backtest.strategies import (
            BuyHoldStrategy,
            ConvictionStrategy,
            MACrossoverStrategy,
        )

        # Generate synthetic data
        np.random.seed(42)
        dates = pd.date_range("2024-01-02", periods=n_days, freq="B")
        close = 100.0 * np.cumprod(1 + np.random.normal(0.001, 0.015, n_days))
        data = pd.DataFrame(
            {
                "open": close * 1.001,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.full(n_days, 1_000_000.0),
            },
            index=dates,
        )

        strategies = {
            "buy_hold": BuyHoldStrategy(),
            "ma_crossover": MACrossoverStrategy(fast=20, slow=50),
            "conviction": ConvictionStrategy(),
        }
        strat = strategies[strategy]
        engine = BacktestEngine(initial_capital=100_000_000)
        result = engine.run(strat, data, ticker)

        return {
            "ticker": ticker,
            "strategy": strategy,
            "n_days": n_days,
            "metrics": result.metrics,
            "n_trades": len(result.trades),
            "equity_curve_sample": [
                {"date": str(d), "equity": round(v, 2)}
                for d, v in result.equity_curve.iloc[::max(1, n_days // 20)].items()
            ],
        }

    @app.get("/api/instruments")
    async def instruments(
        market_mic: str | None = Query(None),
        asset_class: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List instruments, optionally filtered by market and asset class."""
        from market.multi_asset import AssetClass, Instrument, InstrumentRegistry

        registry = InstrumentRegistry()
        # Seed with some default instruments
        defaults = [
            Instrument(
                "BBCA.JK", "Bank Central Asia",
                AssetClass.EQUITY, "XIDX", "IDR", sector="finance",
            ),
            Instrument(
                "TLKM.JK", "Telkom Indonesia",
                AssetClass.EQUITY, "XIDX", "IDR", sector="telecom",
            ),
            Instrument("AAPL", "Apple Inc", AssetClass.EQUITY, "XNAS", "USD", sector="tech"),
            Instrument("SPY", "S&P 500 ETF", AssetClass.ETF, "XNYS", "USD"),
            Instrument("GLD", "Gold ETF", AssetClass.COMMODITY, "XNYS", "USD"),
            Instrument("USDIDR=X", "USD/IDR", AssetClass.FOREX, "XIDX", "IDR"),
            Instrument("BTC-USD", "Bitcoin", AssetClass.CRYPTO, "XNAS", "USD"),
        ]
        for inst in defaults:
            registry.add(inst)

        ac: AssetClass | None = None
        if asset_class:
            try:
                ac = AssetClass(asset_class)
            except ValueError:
                return []

        results = registry.search(market_mic=market_mic, asset_class=ac)
        return [
            {
                "ticker": inst.ticker,
                "name": inst.name,
                "asset_class": inst.asset_class.value,
                "market_mic": inst.market_mic,
                "currency": inst.currency,
                "sector": inst.sector,
            }
            for inst in results
        ]

    @app.get("/api/fx-risk")
    async def fx_risk(
        positions: str = Query(..., description="Comma-separated currency:amount pairs"),
        base_currency: str = Query("IDR"),
    ) -> dict[str, Any]:
        """Assess FX risk for multi-currency positions."""
        from market.multi_asset.fx_risk import FXRiskEngine

        engine = FXRiskEngine(base_currency=base_currency)
        # Set some default rates
        engine.set_rate("USD", "IDR", 15800)
        engine.set_rate("SGD", "IDR", 11700)
        engine.set_rate("HKD", "IDR", 2020)
        engine.set_rate("JPY", "IDR", 105)

        pos: dict[str, float] = {}
        for pair in positions.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2:
                pos[parts[0].strip()] = float(parts[1])

        report = engine.assess(pos)
        return {
            "base_currency": report.base_currency,
            "total_exposure": report.total_exposure,
            "fx_var_95": report.fx_var_95,
            "fx_volatility_pct": report.fx_volatility_pct,
            "unhedged_pct": report.unhedged_pct,
            "exposures": [
                {
                    "currency": e.currency,
                    "exposure_value": e.exposure_value,
                    "exposure_in_base": e.exposure_in_base,
                    "weight_pct": e.weight_pct,
                }
                for e in report.exposures
            ],
        }

    # --- Automation endpoints ---

    @app.get("/api/automation/config")
    async def get_automation_config() -> dict[str, Any]:
        """Get current automation config and gate status."""
        config = automation_orchestrator.config
        gate_result = automation_orchestrator.last_gate_result
        return {
            "config": _dataclass_to_dict(config) if config else None,
            "gate_result": _dataclass_to_dict(gate_result) if gate_result else None,
            "last_plan": (
                _dataclass_to_dict(automation_orchestrator.last_plan)
                if automation_orchestrator.last_plan else None
            ),
            "last_execution": (
                _dataclass_to_dict(automation_orchestrator.last_execution)
                if automation_orchestrator.last_execution else None
            ),
            "available_sources": [s.value for s in SignalSource],
            "available_scopes": [s.value for s in MarketScope],
            "available_modes": [m.value for m in ExecutionMode],
        }

    @app.post("/api/automation/config")
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

        gate_result = automation_orchestrator.configure(config)
        return {
            "config": (
                _dataclass_to_dict(automation_orchestrator.config)
                if automation_orchestrator.config else None
            ),
            "gate_result": _dataclass_to_dict(gate_result),
        }

    @app.post("/api/automation/plan")
    async def prepare_automation_plan(body: dict[str, Any]) -> dict[str, Any]:
        """Prepare execution plan from signals (no execution).

        Request body:
            signals: list of {ticker, side, source, confidence, price, recommendation}
        """
        signals = body.get("signals", [])
        plan = automation_orchestrator.prepare_plan(signals)
        return dict(_dataclass_to_dict(plan))

    @app.post("/api/automation/execute")
    async def execute_automation(body: dict[str, Any]) -> dict[str, Any]:
        """Execute automation plan from signals.

        Runs full pipeline: gate → plan → execute.
        Request body:
            signals: list of {ticker, side, source, confidence, price, recommendation}
        """
        signals = body.get("signals", [])
        result = automation_orchestrator.execute(signals)
        return dict(_dataclass_to_dict(result))

    @app.post("/api/leverage/advise")
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

        rec = leverage_advisor.advise(
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

    @app.get("/api/autonomous-backtest/status")
    async def autonomous_backtest_status() -> dict[str, Any]:
        """Get autonomous backtest runner status."""
        return autonomous_backtest_runner.status_summary()

    @app.get("/api/autonomous-backtest/runs")
    async def autonomous_backtest_runs() -> dict[str, Any]:
        """List all autonomous backtest runs."""
        runs = autonomous_backtest_runner.runs
        return {
            "total": len(runs),
            "runs": [
                {
                    "run_id": r.run_id,
                    "trigger": r.trigger.value,
                    "status": r.status.value,
                    "triggered_at": r.triggered_at,
                    "completed_at": r.completed_at,
                    "total_instruments": r.total_instruments,
                    "successful": r.successful,
                    "failed": r.failed,
                    "skipped": r.skipped,
                    "avg_sharpe": r.avg_sharpe,
                    "best_sharpe": r.best_sharpe,
                    "best_strategy": r.best_strategy,
                    "worst_strategy": r.worst_strategy,
                    "instruments_tested": r.instruments_tested,
                    "agent_actions": r.agent_actions_proposed,
                    "summary": r.summary,
                    "duration_seconds": r.duration_seconds,
                }
                for r in runs
            ],
        }

    @app.get("/api/autonomous-backtest/latest")
    async def autonomous_backtest_latest() -> dict[str, Any]:
        """Get latest autonomous backtest run with full details."""
        latest = autonomous_backtest_runner.latest
        if latest is None:
            return {"status": "idle", "message": "No autonomous backtest runs yet."}

        instrument_results = []
        for r in latest.instrument_results:
            ir: dict[str, Any] = {
                "ticker": r.ticker,
                "strategy": r.strategy.value,
                "status": r.status.value,
                "metrics": r.metrics,
                "trade_count": r.trade_count,
                "error": r.error,
            }
            if r.walk_forward:
                ir["walk_forward"] = {
                    "oos_sharpe": r.walk_forward.oos_sharpe,
                    "oos_return_pct": r.walk_forward.oos_return_pct,
                    "consistency_pct": r.walk_forward.consistency_pct,
                }
            if r.monte_carlo:
                ir["monte_carlo"] = {
                    "percentiles": r.monte_carlo.percentiles,
                    "prob_loss_pct": r.monte_carlo.prob_loss_pct,
                    "max_drawdown_pct": r.monte_carlo.max_drawdown_pct,
                }
            instrument_results.append(ir)

        return {
            "run_id": latest.run_id,
            "trigger": latest.trigger.value,
            "status": latest.status.value,
            "triggered_at": latest.triggered_at,
            "completed_at": latest.completed_at,
            "total_instruments": latest.total_instruments,
            "total_strategies": latest.total_strategies,
            "successful": latest.successful,
            "failed": latest.failed,
            "skipped": latest.skipped,
            "best_sharpe": latest.best_sharpe,
            "worst_sharpe": latest.worst_sharpe,
            "avg_sharpe": latest.avg_sharpe,
            "best_strategy": latest.best_strategy,
            "worst_strategy": latest.worst_strategy,
            "instruments_tested": latest.instruments_tested,
            "agent_actions_proposed": latest.agent_actions_proposed,
            "summary": latest.summary,
            "duration_seconds": latest.duration_seconds,
            "instrument_results": instrument_results,
        }

    @app.post("/api/autonomous-backtest/trigger")
    async def autonomous_backtest_trigger(body: dict[str, Any]) -> dict[str, Any]:
        """Force trigger an autonomous backtest run (admin only).

        Request body (all optional):
            trigger: str — trigger type (default: manual_force)
            instruments: dict[ticker, {open, high, low, close, volume, ...}] —
                if not provided, uses mock data
        """
        import pandas as pd

        trigger_str = body.get("trigger", "manual_force")
        try:
            trigger = BacktestTrigger(trigger_str)
        except ValueError:
            trigger = BacktestTrigger.MANUAL_FORCE

        instruments_raw = body.get("instruments")
        if instruments_raw and isinstance(instruments_raw, dict):
            instruments = {}
            for ticker, ohlcv in instruments_raw.items():
                if isinstance(ohlcv, dict):
                    instruments[ticker] = pd.DataFrame(ohlcv)
                    if "date" in instruments[ticker].columns:
                        instruments[ticker] = instruments[ticker].set_index("date")
                else:
                    instruments[ticker] = ohlcv
        else:
            instruments = _generate_mock_instruments()

        run = autonomous_backtest_runner.run(instruments, trigger=trigger)
        return dict(_dataclass_to_dict(run))

    # ------------------------------------------------------------------
    # Pattern Detection & Prediction (no look-ahead bias)
    # ------------------------------------------------------------------

    @app.post("/api/pattern/detect")
    async def pattern_detect(body: dict[str, Any]) -> dict[str, Any]:
        """Detect chart patterns with no look-ahead bias.

        Request body:
            ticker: str — instrument ticker
            ohlcv: dict with keys open, high, low, close, volume (lists)
            as_of: str (optional) — detection date cutoff (ISO format)
        """
        import pandas as pd

        ticker = body.get("ticker", "UNKNOWN")
        ohlcv_raw = body.get("ohlcv", {})
        as_of = body.get("as_of")

        if not ohlcv_raw:
            raise HTTPException(400, "Missing ohlcv data")

        df = pd.DataFrame(ohlcv_raw)
        if "date" in df.columns:
            df = df.set_index("date")
        elif "index" in df.columns:
            df = df.set_index("index")

        detections = pattern_detector.detect(ticker, df, as_of)

        return {
            "ticker": ticker,
            "as_of": as_of or str(df.index[-1]),
            "patterns": [
                {
                    "pattern_type": d.pattern_type,
                    "direction": d.direction,
                    "confidence": d.confidence,
                    "price_at_detection": d.price_at_detection,
                    "key_levels": d.key_levels,
                    "description": d.description,
                    "indicators_snapshot": d.indicators_snapshot,
                }
                for d in detections
            ],
            "log": [
                {
                    "timestamp": e.timestamp,
                    "level": e.level,
                    "ticker": e.ticker,
                    "message": e.message,
                    "data": e.data,
                }
                for e in pattern_detector.log
            ],
        }

    @app.post("/api/prediction/predict")
    async def prediction_predict(body: dict[str, Any]) -> dict[str, Any]:
        """Predict next-period price with no look-ahead bias.

        Request body:
            ticker: str
            ohlcv: dict with keys open, high, low, close, volume (lists)
            as_of: str (optional) — prediction date cutoff
            method: str (optional) — ma_based, momentum, pattern_based,
                    volatility_adjusted, ensemble (default)
        """
        import pandas as pd

        ticker = body.get("ticker", "UNKNOWN")
        ohlcv_raw = body.get("ohlcv", {})
        as_of = body.get("as_of")
        method_str = body.get("method", "ensemble")

        if not ohlcv_raw:
            raise HTTPException(400, "Missing ohlcv data")

        try:
            method = PredictionMethod(method_str)
        except ValueError:
            method = PredictionMethod.ENSEMBLE

        df = pd.DataFrame(ohlcv_raw)
        if "date" in df.columns:
            df = df.set_index("date")
        elif "index" in df.columns:
            df = df.set_index("index")

        pred = prediction_engine.predict(ticker, df, as_of, method)

        return {
            "prediction": {
                "ticker": pred.ticker,
                "as_of": pred.as_of,
                "method": pred.method.value,
                "predicted_price": pred.predicted_price,
                "predicted_direction": pred.predicted_direction,
                "predicted_return_pct": pred.predicted_return_pct,
                "confidence": pred.confidence,
                "horizon_days": pred.horizon_days,
                "indicators_used": pred.indicators_used,
                "pattern_signals": pred.pattern_signals,
                "rationale": pred.rationale,
            },
            "log": [
                {
                    "timestamp": e.timestamp,
                    "level": e.level,
                    "ticker": e.ticker,
                    "message": e.message,
                    "data": e.data,
                }
                for e in prediction_engine.log
            ],
        }

    @app.post("/api/prediction/verify")
    async def prediction_verify(body: dict[str, Any]) -> dict[str, Any]:
        """Verify a past prediction against actual outcome.

        Request body:
            ticker: str
            ohlcv: dict with full OHLCV data (including future data)
            as_of: str — the date the prediction was made
        """
        import pandas as pd

        ticker = body.get("ticker", "UNKNOWN")
        ohlcv_raw = body.get("ohlcv", {})
        as_of = body.get("as_of")

        if not ohlcv_raw:
            raise HTTPException(400, "Missing ohlcv data")
        if not as_of:
            raise HTTPException(400, "Missing as_of date")

        df = pd.DataFrame(ohlcv_raw)
        if "date" in df.columns:
            df = df.set_index("date")
        elif "index" in df.columns:
            df = df.set_index("index")

        error = prediction_engine.verify(ticker, df, as_of)

        return {
            "ticker": ticker,
            "as_of": as_of,
            "error": dict(_dataclass_to_dict(error)) if error else None,
            "log": [
                {
                    "timestamp": e.timestamp,
                    "level": e.level,
                    "ticker": e.ticker,
                    "message": e.message,
                    "data": e.data,
                }
                for e in prediction_engine.log
            ],
        }

    @app.get("/api/prediction/errors")
    async def prediction_errors(ticker: str | None = None) -> dict[str, Any]:
        """Get prediction error summary with lessons and risk factors."""
        return prediction_engine.get_error_summary(ticker)

    @app.get("/api/prediction/risk/{ticker}")
    async def prediction_risk(ticker: str) -> dict[str, Any]:
        """Get risk adjustment factor from prediction errors for a ticker."""
        adjustment = prediction_engine.get_risk_adjustment(ticker)
        summary = prediction_engine.get_error_summary(ticker)
        return {
            "ticker": ticker,
            "risk_adjustment": adjustment,
            "error_summary": summary,
        }

    # ------------------------------------------------------------------
    # Delisting Memory & AI Reminders
    # ------------------------------------------------------------------

    @app.get("/api/delisting/summary")
    async def delisting_summary() -> dict[str, Any]:
        """Get delisting memory summary."""
        return delisting_memory.summary()

    @app.get("/api/delisting/records")
    async def delisting_records() -> dict[str, Any]:
        """List all delisting records."""
        return {
            "records": [
                {
                    "record_id": r.record_id,
                    "ticker": r.ticker,
                    "exchange": r.exchange,
                    "status": r.status.value,
                    "reason": r.reason.value,
                    "event_date": r.event_date,
                    "last_price": r.last_price,
                    "price_decline_pct": r.price_decline_pct,
                    "lesson": r.lesson,
                    "risk_score": r.risk_score,
                    "sector": r.sector,
                    "warning_patterns": [
                        {"type": w.pattern_type.value, "description": w.description,
                     "severity": w.severity}
                        for w in r.warning_patterns
                    ],
                }
                for r in delisting_memory.records
            ]
        }

    @app.get("/api/delisting/lessons")
    async def delisting_lessons(limit: int = 20) -> dict[str, Any]:
        """Get AI lessons from delisting events."""
        return {"lessons": delisting_memory.get_lessons(limit=limit)}

    @app.get("/api/delisting/check/{ticker}")
    async def delisting_check(ticker: str) -> dict[str, Any]:
        """Check a ticker for delisting/suspension/warning patterns."""
        record = delisting_memory.get_record(ticker)
        is_blocked = delisting_memory.is_blocked(ticker)
        is_suspended = delisting_memory.is_suspended(ticker)

        return {
            "ticker": ticker,
            "is_blocked": is_blocked,
            "is_suspended": is_suspended,
            "record": dict(_dataclass_to_dict(record)) if record else None,
        }

    @app.post("/api/delisting/record")
    async def delisting_record(body: dict[str, Any]) -> dict[str, Any]:
        """Record a delisting or suspension event.

        Request body:
            ticker: str
            exchange: str
            reason: str (delisting reason enum value)
            event_date: str
            last_price: float (optional)
            price_decline_pct: float (optional)
            sector: str (optional)
            status: str — "delisted" or "suspended" (default: delisted)
            warning_patterns: list of {pattern_type, description, severity} (optional)
        """
        ticker = body.get("ticker", "")
        exchange = body.get("exchange", "IDX")
        reason_str = body.get("reason", "unknown")
        event_date = body.get("event_date", "")
        status_str = body.get("status", "delisted")

        if not ticker or not event_date:
            raise HTTPException(400, "Missing ticker or event_date")

        try:
            reason = DelistingReason(reason_str)
        except ValueError:
            reason = DelistingReason.UNKNOWN

        # Parse warning patterns
        raw_patterns = body.get("warning_patterns", [])
        warning_patterns: list[WarningPattern] = []
        for wp in raw_patterns:
            try:
                ptype = WarningPatternType(wp.get("pattern_type", ""))
            except ValueError:
                continue
            warning_patterns.append(WarningPattern(
                pattern_type=ptype,
                description=wp.get("description", ""),
                severity=float(wp.get("severity", 0.5)),
                detected_date=event_date,
            ))

        if status_str == "suspended":
            record = delisting_memory.record_suspension(
                ticker=ticker,
                exchange=exchange,
                reason=reason,
                event_date=event_date,
                warning_patterns=warning_patterns,
                sector=body.get("sector", ""),
            )
        else:
            record = delisting_memory.record_delisting(
                ticker=ticker,
                exchange=exchange,
                reason=reason,
                event_date=event_date,
                last_price=float(body.get("last_price", 0)),
                price_decline_pct=float(body.get("price_decline_pct", 0)),
                warning_patterns=warning_patterns,
                sector=body.get("sector", ""),
                market_cap_at_delisting=float(body.get("market_cap_at_delisting", 0)),
                days_suspended_before_delisting=int(body.get("days_suspended_before_delisting", 0)),
            )

        return dict(_dataclass_to_dict(record))

    @app.post("/api/delisting/block")
    async def delisting_block(body: dict[str, Any]) -> dict[str, Any]:
        """Block an instrument from portfolio inclusion.

        Request body:
            ticker: str
            reason: str
            risk_score: float (optional, default 0.8)
            similar_delisted: list[str] (optional)
        """
        ticker = body.get("ticker", "")
        reason = body.get("reason", "AI risk block")
        risk_score = float(body.get("risk_score", 0.8))
        similar = body.get("similar_delisted", [])

        if not ticker:
            raise HTTPException(400, "Missing ticker")

        record = delisting_memory.block_instrument(
            ticker=ticker,
            reason=reason,
            risk_score=risk_score,
            similar_delisted=similar,
        )
        return dict(_dataclass_to_dict(record))

    @app.post("/api/delisting/filter")
    async def delisting_filter(body: dict[str, Any]) -> dict[str, Any]:
        """Filter tickers for portfolio inclusion.

        Request body:
            tickers: list[str] — candidate tickers
        """
        tickers = body.get("tickers", [])
        if not tickers:
            raise HTTPException(400, "Missing tickers list")

        return delisting_memory.get_portfolio_risk_filter(tickers)

    return app


# Module-level app instance
app = create_app()
