"""Security modules API routes (Gap #24).

Integrates Sharia screening, trade surveillance, and fractional shares
into the API:

    GET  /api/security/sharia/screen/{ticker}    — screen single stock
    POST /api/security/sharia/screen-batch       — screen multiple stocks
    GET  /api/security/sharia/compliant          — list compliant stocks
    POST /api/security/surveillance/trade        — record a trade
    POST /api/security/surveillance/order        — record an order
    GET  /api/security/surveillance/alerts       — get surveillance alerts
    POST /api/security/fractional/buy            — buy fractional shares
    GET  /api/security/fractional/position/{ticker} — get fractional position
    POST /api/security/fractional/plan           — create micro-investment plan
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter
from pydantic import BaseModel

from market.security.fractional import FractionalSharesManager
from market.security.sharia import ShariaScreener, ScreeningCriteria
from market.security.surveillance import TradeSurveillance

router = APIRouter(prefix="/api/security", tags=["security"])

# Module-level singletons (single-user app)
_sharia_screener = ShariaScreener()
_surveillance = TradeSurveillance()
_fractional_mgr = FractionalSharesManager()


# ── Sharia Screening ──────────────────────────────────────────────────────

class ShariaScreenRequest(BaseModel):
    ticker: str
    tags: list[str] = []
    debt_to_assets: float = 0.0
    interest_income_to_revenue: float = 0.0
    haram_income_to_revenue: float = 0.0
    non_compliant_investment_pct: float = 0.0


class ShariaBatchRequest(BaseModel):
    stocks: list[ShariaScreenRequest]


@router.post("/sharia/screen")
async def screen_sharia(req: ShariaScreenRequest) -> dict[str, Any]:
    """Screen a single stock for Sharia compliance."""
    if req.tags:
        _sharia_screener.register_business_tags(req.ticker, set(req.tags))
    result = _sharia_screener.screen(
        ticker=req.ticker,
        debt_to_assets=req.debt_to_assets,
        interest_income_to_revenue=req.interest_income_to_revenue,
        haram_income_to_revenue=req.haram_income_to_revenue,
        non_compliant_investment_pct=req.non_compliant_investment_pct,
    )
    return {
        "ticker": result.ticker,
        "is_compliant": result.is_compliant,
        "stage": result.stage.value,
        "business_activity_pass": result.business_activity_pass,
        "financial_ratio_pass": result.financial_ratio_pass,
        "failures": result.failures,
        "ratios": result.ratios,
        "screened_at": result.screened_at,
    }


@router.post("/sharia/screen-batch")
async def screen_sharia_batch(req: ShariaBatchRequest) -> list[dict[str, Any]]:
    """Screen multiple stocks for Sharia compliance."""
    stocks_data = [
        {
            "ticker": s.ticker,
            "tags": s.tags,
            "debt_to_assets": s.debt_to_assets,
            "interest_income_to_revenue": s.interest_income_to_revenue,
            "haram_income_to_revenue": s.haram_income_to_revenue,
            "non_compliant_investment_pct": s.non_compliant_investment_pct,
        }
        for s in req.stocks
    ]
    results = _sharia_screener.screen_batch(stocks_data)
    return [
        {
            "ticker": r.ticker,
            "is_compliant": r.is_compliant,
            "stage": r.stage.value,
            "failures": r.failures,
            "ratios": r.ratios,
        }
        for r in results
    ]


@router.get("/sharia/compliant")
async def list_compliant() -> dict[str, Any]:
    """List Sharia-compliant criteria and haram activities."""
    return {
        "criteria": {
            "max_debt_to_assets": _sharia_screener.criteria.max_debt_to_assets,
            "max_interest_income_to_revenue": _sharia_screener.criteria.max_interest_income_to_revenue,
            "max_haram_income_to_revenue": _sharia_screener.criteria.max_haram_income_to_revenue,
            "max_non_compliant_investment_to_total": _sharia_screener.criteria.max_non_compliant_investment_to_total,
        },
        "haram_activities": sorted(
            _sharia_screener._business_tags.get("__haram__", set())
        ) if False else [
            "alcohol", "pork", "gambling", "conventional_banking",
            "conventional_insurance", "tobacco", "weapons",
            "adult_entertainment", "music_production", "hotels_resorts", "cinema",
        ],
    }


# ── Trade Surveillance ────────────────────────────────────────────────────

class TradeRecordRequest(BaseModel):
    trade_id: str
    account_id: str = "default"
    ticker: str
    side: str
    quantity: float
    price: float
    order_id: str = ""
    client_order_id: str | None = None


class OrderRecordRequest(BaseModel):
    order_id: str
    account_id: str = "default"
    ticker: str
    side: str
    quantity: float
    price: float
    status: str = "new"
    fill_quantity: float = 0.0
    cancel_timestamp: str | None = None


@router.post("/surveillance/trade")
async def record_trade(req: TradeRecordRequest) -> dict[str, Any]:
    """Record a trade for surveillance analysis."""
    from market.security.surveillance import TradeRecord
    trade = TradeRecord(
        trade_id=req.trade_id,
        account_id=req.account_id,
        ticker=req.ticker,
        side=req.side,
        quantity=req.quantity,
        price=req.price,
        order_id=req.order_id,
        client_order_id=req.client_order_id,
    )
    _surveillance.record_trade(trade)
    return {"status": "ok", "trade_id": req.trade_id}


@router.post("/surveillance/order")
async def record_order(req: OrderRecordRequest) -> dict[str, Any]:
    """Record an order for surveillance analysis."""
    from market.security.surveillance import OrderRecord
    order = OrderRecord(
        order_id=req.order_id,
        account_id=req.account_id,
        ticker=req.ticker,
        side=req.side,
        quantity=req.quantity,
        price=req.price,
        status=req.status,
        fill_quantity=req.fill_quantity,
        cancel_timestamp=req.cancel_timestamp,
    )
    _surveillance.record_order(order)
    return {"status": "ok", "order_id": req.order_id}


@router.get("/surveillance/alerts")
async def get_alerts() -> dict[str, Any]:
    """Get surveillance alerts."""
    alerts = _surveillance.run_all_checks()
    return {
        "alert_count": len(alerts),
        "alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type.value,
                "severity": a.severity.value,
                "account_id": a.account_id,
                "ticker": a.ticker,
                "description": a.description,
                "timestamp": a.timestamp,
                "related_trades": a.related_trades,
                "related_orders": a.related_orders,
            }
            for a in alerts
        ],
    }


# ── Fractional Shares ─────────────────────────────────────────────────────

class FractionalBuyRequest(BaseModel):
    ticker: str
    amount: float
    price: float


class MicroPlanRequest(BaseModel):
    ticker: str
    amount_per_period: float
    frequency: str = "monthly"


@router.post("/fractional/buy")
async def buy_fractional(req: FractionalBuyRequest) -> dict[str, Any]:
    """Buy fractional shares."""
    is_valid, msg = _fractional_mgr.validate_investment(req.amount)
    if not is_valid:
        return {"status": "error", "message": msg}

    position = _fractional_mgr.buy_fractional(req.ticker, req.amount, req.price)
    if position is None:
        return {"status": "error", "message": "Buy failed"}

    return {
        "status": "ok",
        "ticker": position.ticker,
        "quantity": position.quantity,
        "average_price": position.average_price,
        "total_cost": position.total_cost,
    }


@router.get("/fractional/position/{ticker}")
async def get_fractional_position(ticker: str) -> dict[str, Any]:
    """Get fractional position for a ticker."""
    position = _fractional_mgr.get_position(ticker)
    if position is None:
        return {"status": "not_found", "ticker": ticker}

    return {
        "status": "ok",
        "ticker": position.ticker,
        "quantity": position.quantity,
        "average_price": position.average_price,
        "total_cost": position.total_cost,
    }


@router.post("/fractional/plan")
async def create_micro_plan(req: MicroPlanRequest) -> dict[str, Any]:
    """Create a micro-investment plan."""
    plan = _fractional_mgr.create_plan(
        ticker=req.ticker,
        amount_per_period=req.amount_per_period,
        frequency=req.frequency,
    )
    return {
        "status": "ok",
        "plan_id": plan.plan_id,
        "ticker": plan.ticker,
        "amount_per_period": plan.amount_per_period,
        "frequency": plan.frequency,
        "active": plan.active,
    }
