"""Portfolio & watchlist endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.api._shared import WatchlistItem, _dataclass_to_dict, to_jakarta
from market.db.engine import get_session
from market.db.models import OHLCV, StockPrice, Watchlist
from market.execution.portfolio import PortfolioEngine

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
async def portfolio(session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get portfolio summary with real positions from DB.

    Loads latest close prices for position valuation.
    Returns PortfolioEngine summary or empty state if no positions.
    """
    engine = PortfolioEngine()

    prices: dict[str, float] = {}

    # Try PG stock_prices first, fallback to SQLite ohlcv
    try:
        tickers = session.execute(
            select(StockPrice.ticker).distinct()
        ).scalars().all()

        for ticker in tickers[:50]:
            latest = session.execute(
                select(StockPrice).where(StockPrice.ticker == ticker)
                .order_by(StockPrice.timestamp.desc()).limit(1)
            ).scalar_one_or_none()
            if latest:
                prices[ticker] = float(latest.close)
        if not prices:
            raise Exception("No PG stock_prices data")
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        tickers = session.execute(
            select(OHLCV.ticker).distinct()
        ).scalars().all()

        for ticker in tickers[:50]:
            latest = session.execute(
                select(OHLCV).where(OHLCV.ticker == ticker)
                .order_by(OHLCV.timestamp.desc()).limit(1)
            ).scalar_one_or_none()
            if latest:
                prices[ticker] = float(latest.close)

    summary = engine.get_summary(prices)
    return dict(_dataclass_to_dict(summary))


@router.get("/watchlist")
async def get_watchlist(
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(Watchlist).order_by(Watchlist.created_at.desc())
        ).scalars().all()
    )
    return [
        {
            "ticker": r.ticker,
            "is_favorite": r.is_favorite,
            "notes": r.notes,
            "added_at": to_jakarta(r.created_at),
        }
        for r in rows
    ]


@router.post("/watchlist")
async def add_watchlist(
    item: WatchlistItem,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    existing = session.execute(
        select(Watchlist).where(Watchlist.ticker == item.ticker)
    ).scalar_one_or_none()
    if existing:
        existing.is_favorite = item.is_favorite
        existing.notes = item.notes
        session.commit()
        return {
            "status": "updated",
            "ticker": item.ticker,
            "is_favorite": item.is_favorite,
            "notes": item.notes,
        }
    entry = Watchlist(
        ticker=item.ticker,
        is_favorite=item.is_favorite,
        notes=item.notes,
    )
    session.add(entry)
    session.commit()
    return {
        "status": "added",
        "ticker": item.ticker,
        "is_favorite": item.is_favorite,
        "notes": item.notes,
    }


@router.delete("/watchlist/{ticker}")
async def remove_watchlist(
    ticker: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    row = session.execute(
        select(Watchlist).where(Watchlist.ticker == ticker)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Ticker not in watchlist")
    session.delete(row)
    session.commit()
    return {"status": "removed", "ticker": ticker}
