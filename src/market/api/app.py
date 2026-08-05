"""FastAPI application for Market (pustaka/18 §8).

Endpoints:
    GET  /api/health              — health check
    GET  /api/env                 — environment config
    GET  /api/scores/{ticker}     — 6 factor scores for a ticker
    GET  /api/recommend/{ticker}  — composite recommendation with XAI
    GET  /api/advisory            — advisory report (screening → top picks)
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

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from market.analysis.advisory import AdvisoryEngine
from market.analysis.decision import DecisionEngine
from market.analysis.fundamental import FundamentalAnalysisEngine
from market.analysis.global_market import GlobalMarketEngine
from market.analysis.macro import MacroEconomicEngine
from market.analysis.relationship import MarketRelationshipEngine
from market.analysis.sentiment import SentimentEngine
from market.analysis.technical import TechnicalAnalysisEngine
from market.config import settings
from market.data.seed import DEFAULT_MARKETS


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
    TechnicalAnalysisEngine()
    FundamentalAnalysisEngine()
    MacroEconomicEngine()
    GlobalMarketEngine()
    MarketRelationshipEngine()
    SentimentEngine()
    decision_engine = DecisionEngine()
    advisory_engine = AdvisoryEngine(decision_engine)

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

    return app


# Module-level app instance
app = create_app()
