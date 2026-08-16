"""Reports API routes (Gap #25).

Exposes trade log, dividend history, and tax report endpoints:

    GET /api/reports/trade-log        — trade history (from orders table)
    GET /api/reports/dividends        — dividend history
    GET /api/reports/tax/{year}       — annual tax summary (PPh final 0.1%)
    GET /api/reports/statement        — monthly portfolio statement
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from market.db.engine import get_session
from market.db.models import CorporateAction

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/trade-log")
async def trade_log(
    session: Annotated[Session, Depends(get_session)],
    ticker: str | None = Query(None),
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """Get trade log from orders table."""
    # Use raw SQL with CAST because positions/orders tables have text columns
    # that don't match ORM Numeric types (pre-existing schema issue)
    sql = """
        SELECT id, ticker, order_type, order_style,
               CAST(quantity AS FLOAT) as quantity,
               CAST(price AS FLOAT) as price,
               CAST(total_value AS FLOAT) as total_value,
               CAST(fee AS FLOAT) as fee,
               status, created_at
        FROM orders
    """
    params: dict[str, Any] = {"limit": limit}
    if ticker:
        sql += " WHERE ticker = :ticker"
        params["ticker"] = ticker
    sql += " ORDER BY created_at DESC LIMIT :limit"

    rows = session.execute(text(sql), params).all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "order_type": r.order_type,
            "order_style": r.order_style,
            "quantity": r.quantity or 0.0,
            "price": r.price or 0.0,
            "total_value": r.total_value or 0.0,
            "fee": r.fee or 0.0,
            "status": r.status,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/dividends")
async def dividends(
    session: Annotated[Session, Depends(get_session)],
    ticker: str | None = Query(None),
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """Get dividend history."""
    stmt = (
        select(CorporateAction)
        .where(CorporateAction.action_type == "dividend")
        .order_by(CorporateAction.ex_date.desc())
        .limit(limit)
    )
    if ticker:
        stmt = stmt.where(CorporateAction.ticker == ticker)

    rows = session.execute(stmt).scalars().all()
    return [
        {
            "ticker": r.ticker,
            "action_type": r.action_type,
            "ex_date": r.ex_date.isoformat() if r.ex_date else None,
            "record_date": r.record_date.isoformat() if r.record_date else None,
            "payment_date": r.payment_date.isoformat() if r.payment_date else None,
            "value": float(r.value) if r.value else 0.0,
            "currency": r.currency,
        }
        for r in rows
    ]


@router.get("/tax/{year}")
async def tax_report(
    year: int,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Annual tax summary for a given year.

    Indonesian stock trading tax:
    - PPh final 0.1% on sell value (IDX stocks)
    """
    from datetime import date

    start = date(year, 1, 1)
    end = date(year, 12, 31)

    sql = """
        SELECT ticker, order_type, order_style,
               CAST(quantity AS FLOAT) as quantity,
               CAST(price AS FLOAT) as price,
               CAST(total_value AS FLOAT) as total_value,
               CAST(fee AS FLOAT) as fee,
               created_at
        FROM orders
        WHERE created_at IS NOT NULL
        ORDER BY created_at
    """
    rows = session.execute(text(sql)).all()

    sells: list[dict[str, Any]] = []
    total_sell_value = 0.0
    total_fee = 0.0

    for o in rows:
        if not o.created_at:
            continue
        # created_at is text in DB; parse to date for comparison
        ca = str(o.created_at)
        try:
            order_date_str = ca[:10]  # YYYY-MM-DD
            order_date = date.fromisoformat(order_date_str)
        except (ValueError, TypeError):
            continue
        if order_date < start or order_date > end:
            continue

        # Treat SELL orders as taxable
        ot = (o.order_type or "").upper()
        os_ = (o.order_style or "").upper()
        if ot == "SELL" or os_ == "SELL":
            sell_value = float(o.total_value or (o.quantity or 0) * (o.price or 0))
            fee = float(o.fee or 0)
            total_sell_value += sell_value
            total_fee += fee
            sells.append({
                "ticker": o.ticker,
                "quantity": float(o.quantity or 0),
                "price": float(o.price or 0),
                "sell_value": round(sell_value, 2),
                "fee": round(fee, 2),
                "date": ca,
            })

    # Expected PPh final = 0.1% of sell value
    expected_tax = total_sell_value * 0.001

    return {
        "year": year,
        "total_sell_value": round(total_sell_value, 2),
        "total_tax_paid": 0.0,  # Tax is deducted by broker, not tracked separately
        "expected_pph_final_0_1_pct": round(expected_tax, 2),
        "total_commission": round(total_fee, 2),
        "net_proceeds": round(total_sell_value - total_fee, 2),
        "sell_count": len(sells),
        "sells": sells,
    }


@router.get("/statement")
async def statement(
    session: Annotated[Session, Depends(get_session)],
    month: str = Query(..., description="YYYY-MM"),
) -> dict[str, Any]:
    """Monthly portfolio statement."""
    sql = """
        SELECT ticker,
               CAST(quantity AS FLOAT) as quantity,
               CAST(avg_entry_price AS FLOAT) as avg_entry_price,
               CAST(current_price AS FLOAT) as current_price,
               CAST(unrealized_pnl AS FLOAT) as unrealized_pnl
        FROM positions
        WHERE status = 'OPEN'
    """
    rows = session.execute(text(sql)).all()

    return {
        "month": month,
        "positions": [
            {
                "ticker": r.ticker,
                "quantity": r.quantity or 0.0,
                "avg_entry_price": r.avg_entry_price or 0.0,
                "current_price": r.current_price,
                "market_value": (
                    r.quantity * r.current_price
                    if r.current_price and r.quantity else None
                ),
                "unrealized_pnl": r.unrealized_pnl,
            }
            for r in rows
        ],
        "position_count": len(rows),
    }
