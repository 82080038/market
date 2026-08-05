"""PnL Engine — realized/unrealized PnL with FIFO cost basis.

Tracks individual lots (buy parcels) and matches sells against
oldest lots first (FIFO). Computes realized and unrealized PnL
per ticker and at portfolio level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Lot:
    """A single buy lot (parcel of shares)."""

    ticker: str
    shares: int
    price: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    remaining: int = 0  # Shares not yet sold

    def __post_init__(self) -> None:
        if self.remaining == 0:
            self.remaining = self.shares


@dataclass
class RealizedTrade:
    """A realized PnL event from selling a lot."""

    ticker: str
    shares: int
    buy_price: float
    sell_price: float
    realized_pnl: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PositionPnL:
    """PnL summary for a single ticker position."""

    ticker: str
    total_shares: int
    avg_cost: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float


@dataclass
class PortfolioPnL:
    """Portfolio-level PnL summary."""

    positions: dict[str, PositionPnL] = field(default_factory=dict)
    total_realized: float = 0.0
    total_unrealized: float = 0.0
    total_pnl: float = 0.0


class PnLEngine:
    """PnL engine with FIFO cost basis tracking."""

    def __init__(self) -> None:
        self._lots: dict[str, list[Lot]] = {}
        self._realized_trades: list[RealizedTrade] = []
        self._realized_by_ticker: dict[str, float] = {}

    def buy(
        self,
        ticker: str,
        shares: int,
        price: float,
        timestamp: datetime | None = None,
    ) -> Lot:
        """Record a buy, creating a new lot.

        Args:
            ticker: Stock ticker.
            shares: Number of shares bought.
            price: Buy price per share.
            timestamp: Trade timestamp.

        Returns:
            The created Lot.
        """
        ts = timestamp or datetime.now(UTC)
        lot = Lot(ticker=ticker, shares=shares, price=price, timestamp=ts)
        self._lots.setdefault(ticker, []).append(lot)
        return lot

    def sell(
        self,
        ticker: str,
        shares: int,
        price: float,
        timestamp: datetime | None = None,
    ) -> list[RealizedTrade]:
        """Record a sell, matching against oldest lots (FIFO).

        Args:
            ticker: Stock ticker.
            shares: Number of shares sold.
            price: Sell price per share.
            timestamp: Trade timestamp.

        Returns:
            List of RealizedTrade events (one per matched lot).
        """
        ts = timestamp or datetime.now(UTC)
        lots = self._lots.get(ticker, [])
        trades: list[RealizedTrade] = []
        remaining_to_sell = shares

        for lot in lots:
            if remaining_to_sell <= 0:
                break
            if lot.remaining <= 0:
                continue

            matched = min(lot.remaining, remaining_to_sell)
            pnl = matched * (price - lot.price)
            lot.remaining -= matched
            remaining_to_sell -= matched

            trade = RealizedTrade(
                ticker=ticker,
                shares=matched,
                buy_price=lot.price,
                sell_price=price,
                realized_pnl=pnl,
                timestamp=ts,
            )
            trades.append(trade)
            self._realized_trades.append(trade)
            self._realized_by_ticker[ticker] = (
                self._realized_by_ticker.get(ticker, 0.0) + pnl
            )

        return trades

    def get_position_pnl(
        self,
        ticker: str,
        current_price: float,
    ) -> PositionPnL:
        """Get PnL summary for a single ticker.

        Args:
            ticker: Stock ticker.
            current_price: Current market price.

        Returns:
            PositionPnL with realized, unrealized, and total PnL.
        """
        lots = self._lots.get(ticker, [])
        total_shares = sum(lot.remaining for lot in lots)
        total_cost = sum(lot.remaining * lot.price for lot in lots)
        avg_cost = total_cost / total_shares if total_shares > 0 else 0.0
        unrealized = total_shares * (current_price - avg_cost) if total_shares > 0 else 0.0
        realized = self._realized_by_ticker.get(ticker, 0.0)

        return PositionPnL(
            ticker=ticker,
            total_shares=total_shares,
            avg_cost=round(avg_cost, 4),
            unrealized_pnl=round(unrealized, 2),
            realized_pnl=round(realized, 2),
            total_pnl=round(unrealized + realized, 2),
        )

    def get_portfolio_pnl(
        self,
        prices: dict[str, float],
    ) -> PortfolioPnL:
        """Get portfolio-level PnL summary.

        Args:
            prices: Dict mapping ticker to current price.

        Returns:
            PortfolioPnL with all positions and totals.
        """
        positions: dict[str, PositionPnL] = {}
        tickers = set(self._lots.keys()) | set(self._realized_by_ticker.keys())

        total_realized = 0.0
        total_unrealized = 0.0

        for ticker in tickers:
            price = prices.get(ticker, 0.0)
            pos = self.get_position_pnl(ticker, price)
            positions[ticker] = pos
            total_realized += pos.realized_pnl
            total_unrealized += pos.unrealized_pnl

        return PortfolioPnL(
            positions=positions,
            total_realized=round(total_realized, 2),
            total_unrealized=round(total_unrealized, 2),
            total_pnl=round(total_realized + total_unrealized, 2),
        )

    def get_realized_trades(self, ticker: str | None = None) -> list[RealizedTrade]:
        """Get realized trade history, optionally filtered by ticker.

        Args:
            ticker: Optional ticker filter.

        Returns:
            List of RealizedTrade events.
        """
        if ticker is None:
            return list(self._realized_trades)
        return [t for t in self._realized_trades if t.ticker == ticker]
