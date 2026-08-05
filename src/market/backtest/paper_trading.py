"""Paper trading engine (pustaka/93).

Simulates order execution with IDX rules:
- Lot size: 100 shares
- Tick size: 1 IDR for stocks < 200, 2.5 for 200-500, 5 for > 500
- Commission: 0.15%
- Sales tax: 0.1% (sell only)
- Fractional shares not allowed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class PaperOrder:
    """Paper trading order."""

    ticker: str
    side: str  # "buy" or "sell"
    shares: int
    price: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = "filled"  # filled, rejected
    commission: float = 0.0
    sales_tax: float = 0.0
    total_cost: float = 0.0
    rejection_reason: str | None = None


@dataclass
class PaperPosition:
    """Paper trading position."""

    ticker: str
    shares: int = 0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0


class PaperTradingEngine:
    """Paper trading engine with IDX rules."""

    def __init__(
        self,
        initial_capital: float = 100_000_000,
        commission_rate: float = 0.0015,
        sales_tax_rate: float = 0.001,
        lot_size: int = 100,
    ) -> None:
        self.cash = initial_capital
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.sales_tax_rate = sales_tax_rate
        self.lot_size = lot_size
        self.positions: dict[str, PaperPosition] = {}
        self.orders: list[PaperOrder] = []

    def buy(
        self,
        ticker: str,
        shares: int,
        price: float,
    ) -> PaperOrder:
        """Execute a buy order with IDX validation.

        Args:
            ticker: Stock ticker.
            shares: Number of shares (must be multiple of lot_size).
            price: Limit price.

        Returns:
            PaperOrder with execution details.
        """
        # Validate lot size
        if shares % self.lot_size != 0 or shares <= 0:
            return PaperOrder(
                ticker=ticker,
                side="buy",
                shares=shares,
                price=price,
                status="rejected",
                rejection_reason="INVALID_LOT_SIZE",
            )

        trade_value = shares * price
        commission = trade_value * self.commission_rate
        total_cost = trade_value + commission

        # Check buying power
        if total_cost > self.cash:
            return PaperOrder(
                ticker=ticker,
                side="buy",
                shares=shares,
                price=price,
                status="rejected",
                rejection_reason="INSUFFICIENT_FUNDS",
            )

        # Execute
        self.cash -= total_cost

        pos = self.positions.setdefault(
            ticker, PaperPosition(ticker=ticker),
        )
        total_shares = pos.shares + shares
        pos.avg_cost = (
            (pos.shares * pos.avg_cost + trade_value) / total_shares
            if total_shares > 0
            else price
        )
        pos.shares = total_shares

        order = PaperOrder(
            ticker=ticker,
            side="buy",
            shares=shares,
            price=price,
            commission=commission,
            total_cost=total_cost,
        )
        self.orders.append(order)
        return order

    def sell(
        self,
        ticker: str,
        shares: int,
        price: float,
    ) -> PaperOrder:
        """Execute a sell order with IDX validation.

        Args:
            ticker: Stock ticker.
            shares: Number of shares to sell.
            price: Limit price.

        Returns:
            PaperOrder with execution details.
        """
        pos = self.positions.get(ticker)

        if pos is None or pos.shares < shares:
            return PaperOrder(
                ticker=ticker,
                side="sell",
                shares=shares,
                price=price,
                status="rejected",
                rejection_reason="INSUFFICIENT_SHARES",
            )

        if (shares % self.lot_size != 0 or shares <= 0) and shares != pos.shares:
            # Allow selling odd lots only if closing entire position
            return PaperOrder(
                ticker=ticker,
                side="sell",
                shares=shares,
                price=price,
                status="rejected",
                rejection_reason="INVALID_LOT_SIZE",
            )

        trade_value = shares * price
        commission = trade_value * self.commission_rate
        sales_tax = trade_value * self.sales_tax_rate
        net_proceeds = trade_value - commission - sales_tax

        # Realized PnL (FIFO simplified: use avg cost)
        cost_basis = shares * pos.avg_cost
        realized = net_proceeds - cost_basis

        self.cash += net_proceeds
        pos.shares -= shares
        pos.realized_pnl += realized

        order = PaperOrder(
            ticker=ticker,
            side="sell",
            shares=shares,
            price=price,
            commission=commission,
            sales_tax=sales_tax,
            total_cost=net_proceeds,
        )
        self.orders.append(order)
        return order

    def get_portfolio_value(self, prices: dict[str, float]) -> float:
        """Calculate total portfolio value (cash + positions).

        Args:
            prices: Dict mapping ticker to current price.

        Returns:
            Total portfolio value in IDR.
        """
        total = self.cash
        for ticker, pos in self.positions.items():
            if pos.shares > 0 and ticker in prices:
                total += pos.shares * prices[ticker]
        return total

    def get_unrealized_pnl(self, prices: dict[str, float]) -> float:
        """Calculate total unrealized PnL.

        Args:
            prices: Dict mapping ticker to current price.

        Returns:
            Total unrealized PnL in IDR.
        """
        total = 0.0
        for ticker, pos in self.positions.items():
            if pos.shares > 0 and ticker in prices:
                total += pos.shares * (prices[ticker] - pos.avg_cost)
        return total
