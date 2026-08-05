"""Fractional shares and micro-investing support (pustaka/64).

Provides:
- Fractional share quantity management
- Micro-investing order splitting
- Minimum investment amount validation
- Fractional position tracking
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FractionalPosition:
    """A fractional share position."""

    ticker: str
    quantity: float
    average_price: float
    total_cost: float

    @property
    def market_value(self) -> float:
        """Current market value (requires current_price to be set)."""
        return self.quantity * self.average_price


@dataclass
class MicroInvestmentPlan:
    """A recurring micro-investment plan."""

    plan_id: str
    ticker: str
    amount_per_period: float
    frequency: str = "monthly"  # daily, weekly, monthly
    next_execution: str = ""
    active: bool = True
    total_invested: float = 0.0
    total_shares: float = 0.0
    executions: int = 0


class FractionalSharesManager:
    """Manages fractional share operations.

    Supports micro-investing with small dollar amounts
    by allowing fractional share quantities.
    """

    def __init__(
        self,
        min_investment: float = 10_000.0,  # IDR 10,000 minimum
        max_decimal_places: int = 6,
    ) -> None:
        self.min_investment = min_investment
        self.max_decimal_places = max_decimal_places
        self._positions: dict[str, FractionalPosition] = {}
        self._plans: dict[str, MicroInvestmentPlan] = {}
        self._plan_counter = 0

    def calculate_shares(self, amount: float, price: float) -> float:
        """Calculate fractional shares for a given investment amount.

        Args:
            amount: Investment amount in currency.
            price: Current share price.

        Returns:
            Fractional share quantity.
        """
        if price <= 0:
            return 0.0
        shares = amount / price
        return round(shares, self.max_decimal_places)

    def validate_investment(self, amount: float) -> tuple[bool, str]:
        """Validate if investment amount meets minimum.

        Args:
            amount: Investment amount.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if amount <= 0:
            return False, "Investment amount must be positive"
        if amount < self.min_investment:
            return False, f"Minimum investment is {self.min_investment:,.0f}"
        return True, ""

    def buy_fractional(
        self,
        ticker: str,
        amount: float,
        price: float,
    ) -> FractionalPosition | None:
        """Buy fractional shares.

        Args:
            ticker: Stock ticker.
            amount: Investment amount.
            price: Current share price.

        Returns:
            Updated FractionalPosition, or None if invalid.
        """
        is_valid, _error = self.validate_investment(amount)
        if not is_valid:
            return None

        shares = self.calculate_shares(amount, price)
        if shares <= 0:
            return None

        if ticker in self._positions:
            pos = self._positions[ticker]
            new_quantity = pos.quantity + shares
            new_cost = pos.total_cost + amount
            new_avg = new_cost / new_quantity
            pos.quantity = round(new_quantity, self.max_decimal_places)
            pos.average_price = round(new_avg, 6)
            pos.total_cost = new_cost
        else:
            self._positions[ticker] = FractionalPosition(
                ticker=ticker,
                quantity=shares,
                average_price=price,
                total_cost=amount,
            )

        return self._positions[ticker]

    def sell_fractional(
        self,
        ticker: str,
        shares: float,
        price: float,
    ) -> float | None:
        """Sell fractional shares.

        Args:
            ticker: Stock ticker.
            shares: Number of shares to sell (can be fractional).
            price: Current share price.

        Returns:
            Proceeds from sale, or None if insufficient shares.
        """
        pos = self._positions.get(ticker)
        if pos is None or pos.quantity < shares:
            return None

        proceeds = shares * price
        pos.quantity = round(pos.quantity - shares, self.max_decimal_places)
        pos.total_cost = pos.quantity * pos.average_price

        if pos.quantity <= 0:
            del self._positions[ticker]

        return proceeds

    def create_plan(
        self,
        ticker: str,
        amount_per_period: float,
        frequency: str = "monthly",
    ) -> MicroInvestmentPlan | None:
        """Create a recurring micro-investment plan.

        Args:
            ticker: Stock ticker.
            amount_per_period: Amount to invest each period.
            frequency: "daily", "weekly", or "monthly".

        Returns:
            Created MicroInvestmentPlan, or None if invalid.
        """
        is_valid, _ = self.validate_investment(amount_per_period)
        if not is_valid:
            return None

        self._plan_counter += 1
        plan_id = f"plan_{self._plan_counter:04d}"
        plan = MicroInvestmentPlan(
            plan_id=plan_id,
            ticker=ticker,
            amount_per_period=amount_per_period,
            frequency=frequency,
        )
        self._plans[plan_id] = plan
        return plan

    def execute_plan(self, plan_id: str, current_price: float) -> FractionalPosition | None:
        """Execute a micro-investment plan.

        Args:
            plan_id: Plan ID to execute.
            current_price: Current share price.

        Returns:
            Updated position, or None if plan not found/inactive.
        """
        plan = self._plans.get(plan_id)
        if plan is None or not plan.active:
            return None

        pos = self.buy_fractional(plan.ticker, plan.amount_per_period, current_price)
        if pos:
            plan.total_invested += plan.amount_per_period
            plan.total_shares = pos.quantity
            plan.executions += 1

        return pos

    def get_position(self, ticker: str) -> FractionalPosition | None:
        """Get fractional position for a ticker."""
        return self._positions.get(ticker)

    def get_plan(self, plan_id: str) -> MicroInvestmentPlan | None:
        """Get a micro-investment plan."""
        return self._plans.get(plan_id)

    @property
    def positions(self) -> list[FractionalPosition]:
        """All fractional positions."""
        return list(self._positions.values())

    @property
    def plans(self) -> list[MicroInvestmentPlan]:
        """All micro-investment plans."""
        return list(self._plans.values())
