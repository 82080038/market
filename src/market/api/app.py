"""FastAPI application for Market (pustaka/18 §8).

Thin factory: creates a FastAPI app and includes all route modules.
Each route module is an APIRouter with its own prefix and tags.

Endpoint inventory:
    GET  /api/health              — health check
    GET  /api/env                 — environment config
    GET  /api/markets             — market registry list
    GET  /api/scores/{ticker}     — 6 factor scores for a ticker
    GET  /api/recommend/{ticker}  — composite recommendation with XAI
    GET  /api/advisory            — advisory report (screening → top picks)
    GET  /api/readiness/{ticker}  — instrument readiness assessment
    GET  /api/portfolio           — portfolio summary (NAV, positions, exposure)
    GET  /api/watchlist           — watchlist list
    POST /api/watchlist           — add to watchlist
    DELETE /api/watchlist/{ticker} — remove from watchlist
    GET  /api/backtest/run        — run backtest (query params)
    GET  /api/autonomous-backtest/status   — autonomous backtest runner status
    GET  /api/autonomous-backtest/runs     — list of past autonomous backtest runs
    GET  /api/autonomous-backtest/latest   — latest autonomous backtest run details
    POST /api/autonomous-backtest/trigger  — force trigger autonomous backtest (admin)
    GET  /api/automation/config   — get automation config & gate status
    POST /api/automation/config   — set automation config
    POST /api/automation/plan     — prepare execution plan from signals
    POST /api/automation/execute  — execute plan via broker
    POST /api/leverage/advise     — leverage recommendation with justification
    POST /api/pattern/detect      — detect patterns (no look-ahead, as_of date)
    POST /api/prediction/predict  — predict next-period price (no look-ahead)
    POST /api/prediction/verify   — verify past prediction, track error + root cause
    GET  /api/prediction/errors   — prediction error summary with lessons
    GET  /api/prediction/risk/{ticker} — risk adjustment from prediction errors
    GET  /api/delisting/summary   — delisting memory summary
    GET  /api/delisting/records   — list all delisting records
    GET  /api/delisting/lessons   — AI lessons from delisting events
    GET  /api/delisting/check/{ticker} — check ticker for delisting/suspension/warnings
    POST /api/delisting/record    — record a delisting or suspension event
    POST /api/delisting/block     — block an instrument from portfolio
    POST /api/delisting/filter    — filter tickers for portfolio inclusion
    GET  /api/instruments         — list instruments (filter by market/asset class)
    GET  /api/fx-risk             — FX risk assessment for multi-currency positions
    GET  /api/data/sources        — data source health listing
    GET  /api/data/watermarks     — table watermarks (staleness tracking)
    GET  /api/data/audit          — audit log (paginated)
    POST /api/data/fetch          — trigger manual data fetch
    GET  /api/data/quality/{ticker} — data quality score per ticker
    GET  /api/prices/latest         — latest intraday price snapshot
    POST /api/prices/intraday/trigger — manually trigger intraday fetch
    GET  /api/prices/compare/{ticker} — prediction vs actual price comparison
"""

from __future__ import annotations

from fastapi import FastAPI

from market.api.routes_analysis import router as analysis_router
from market.api.routes_automation import router as automation_router
from market.api.routes_backtest import autonomous_router as autonomous_backtest_router
from market.api.routes_backtest import router as backtest_router
from market.api.routes_data import router as data_router
from market.api.routes_delisting import router as delisting_router
from market.api.routes_instruments import router as instruments_router
from market.api.routes_portfolio import router as portfolio_router
from market.api.routes_prediction import router as prediction_router
from market.api.routes_prices import router as prices_router
from market.api.routes_recompute import router as recompute_router
from market.api.routes_system import router as system_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Market API",
        description="Single-user capital market decision-support API.",
        version="0.1.0",
    )

    app.include_router(system_router)
    app.include_router(analysis_router)
    app.include_router(portfolio_router)
    app.include_router(backtest_router)
    app.include_router(autonomous_backtest_router)
    app.include_router(automation_router)
    app.include_router(prediction_router)
    app.include_router(delisting_router)
    app.include_router(instruments_router)
    app.include_router(data_router)
    app.include_router(prices_router)
    app.include_router(recompute_router)

    return app


# Module-level app instance
app = create_app()
