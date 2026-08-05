"""Broker adapters (pustaka/40, pustaka/76).

Implements:
- MockBroker: instant fill at requested price (for testing).
- PaperBroker: simulated fill with slippage and IDX costs.
- RealBroker: stub for live broker integration (Sinarmas/BNI).

All brokers implement the BrokerAdapter interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from market.execution.oms import Order, OrderSide


@dataclass
class BrokerFill:
    """Broker fill result."""

    shares: int
    price: float
    commission: float
    sales_tax: float


class BrokerAdapter(Protocol):
    """Broker adapter interface."""

    def submit(self, order: Order) -> BrokerFill | None:
        """Submit an order to the broker.

        Args:
            order: Order to submit.

        Returns:
            BrokerFill if filled, None if rejected/pending.
        """
        ...

    def cancel(self, order_id: str) -> bool:
        """Cancel an order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            True if cancelled successfully.
        """
        ...


class MockBroker:
    """Mock broker — instant fill at requested price, no costs."""

    def submit(self, order: Order) -> BrokerFill | None:
        if order.price is None and order.shares > 0:
            return None  # Market orders need a reference price

        fill_price = order.price or 0.0
        return BrokerFill(
            shares=order.shares,
            price=fill_price,
            commission=0.0,
            sales_tax=0.0,
        )

    def cancel(self, order_id: str) -> bool:
        return True


class PaperBroker:
    """Paper broker — simulated fill with slippage and IDX costs."""

    def __init__(
        self,
        commission_rate: float = 0.0015,
        sales_tax_rate: float = 0.001,
        slippage_rate: float = 0.0005,
    ) -> None:
        self.commission_rate = commission_rate
        self.sales_tax_rate = sales_tax_rate
        self.slippage_rate = slippage_rate

    def submit(self, order: Order) -> BrokerFill | None:
        if order.price is None or order.price <= 0:
            return None

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = order.price * (1 + self.slippage_rate)
        else:
            fill_price = order.price * (1 - self.slippage_rate)

        trade_value = order.shares * fill_price
        commission = trade_value * self.commission_rate
        sales_tax = (
            trade_value * self.sales_tax_rate
            if order.side == OrderSide.SELL
            else 0.0
        )

        return BrokerFill(
            shares=order.shares,
            price=round(fill_price, 4),
            commission=round(commission, 2),
            sales_tax=round(sales_tax, 2),
        )

    def cancel(self, order_id: str) -> bool:
        return True


class RealBroker:
    """Real broker stub — placeholder for live integration.

    This should be replaced with actual broker API calls
    (Sinarmas, BNI, etc.) when going live.
    """

    def __init__(self, broker_name: str = "sinarmas") -> None:
        self.broker_name = broker_name
        self._connected = False

    def connect(self, api_key: str, api_secret: str) -> bool:
        """Connect to broker API.

        Args:
            api_key: API key from broker.
            api_secret: API secret from broker.

        Returns:
            True if connected successfully.
        """
        # Stub: always returns False (not implemented)
        self._connected = False
        return False

    def submit(self, order: Order) -> BrokerFill | None:
        if not self._connected:
            return None
        # Real implementation would submit to broker API
        return None

    def cancel(self, order_id: str) -> bool:
        if not self._connected:
            return False
        return False
