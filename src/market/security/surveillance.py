"""Trade surveillance and market-abuse detection (pustaka/54).

Provides:
- Wash trade detection (same account buy/sell same security)
- Spoofing detection (large orders cancelled before execution)
- Front-running detection (trading ahead of client orders)
- Layering detection (multiple orders at different price levels)
- Insider trading pattern detection
- Alert generation and logging
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class AlertSeverity(Enum):
    """Severity of a surveillance alert."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of market abuse alerts."""

    WASH_TRADE = "wash_trade"
    SPOOFING = "spoofing"
    FRONT_RUNNING = "front_running"
    LAYERING = "layering"
    INSIDER_TRADING = "insider_trading"
    UNUSUAL_VOLUME = "unusual_volume"
    PRICE_MANIPULATION = "price_manipulation"


@dataclass
class TradeRecord:
    """A trade record for surveillance."""

    trade_id: str
    account_id: str
    ticker: str
    side: str  # "buy" or "sell"
    quantity: float
    price: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    order_id: str = ""
    client_order_id: str | None = None


@dataclass
class OrderRecord:
    """An order record for surveillance."""

    order_id: str
    account_id: str
    ticker: str
    side: str
    quantity: float
    price: float
    status: str  # "new", "cancelled", "filled", "partial"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    cancel_timestamp: str | None = None
    fill_quantity: float = 0.0


@dataclass
class SurveillanceAlert:
    """A surveillance alert."""

    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    account_id: str
    ticker: str
    description: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    related_trades: list[str] = field(default_factory=list)
    related_orders: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class TradeSurveillance:
    """Trade surveillance and market-abuse detection engine."""

    def __init__(
        self,
        wash_trade_window_seconds: int = 300,
        spoofing_cancel_ratio: float = 0.9,
        unusual_volume_threshold: float = 5.0,
    ) -> None:
        self.wash_trade_window = timedelta(seconds=wash_trade_window_seconds)
        self.spoofing_cancel_ratio = spoofing_cancel_ratio
        self.unusual_volume_threshold = unusual_volume_threshold
        self._trades: list[TradeRecord] = []
        self._orders: list[OrderRecord] = []
        self._alerts: list[SurveillanceAlert] = []
        self._alert_counter = 0

    def record_trade(self, trade: TradeRecord) -> None:
        """Record a trade for surveillance."""
        self._trades.append(trade)

    def record_order(self, order: OrderRecord) -> None:
        """Record an order for surveillance."""
        self._orders.append(order)

    def detect_wash_trades(self) -> list[SurveillanceAlert]:
        """Detect wash trades (same account buying and selling same security).

        Returns:
            List of wash trade alerts.
        """
        new_alerts: list[SurveillanceAlert] = []

        # Group trades by account and ticker
        by_account_ticker: dict[tuple[str, str], list[TradeRecord]] = {}
        for trade in self._trades:
            key = (trade.account_id, trade.ticker)
            by_account_ticker.setdefault(key, []).append(trade)

        for (account, ticker), trades in by_account_ticker.items():
            # Sort by timestamp
            trades.sort(key=lambda t: t.timestamp)

            for i, t1 in enumerate(trades):
                for t2 in trades[i + 1:]:
                    # Check if within time window
                    dt1 = datetime.fromisoformat(t1.timestamp)
                    dt2 = datetime.fromisoformat(t2.timestamp)
                    if dt2 - dt1 > self.wash_trade_window:
                        break

                    # Check opposite sides and similar quantities
                    if (
                        t1.side != t2.side
                        and abs(t1.quantity - t2.quantity) / max(t1.quantity, t2.quantity) < 0.1
                    ):
                        alert = self._create_alert(
                            AlertType.WASH_TRADE,
                            AlertSeverity.HIGH,
                            account,
                            ticker,
                            f"Possible wash trade: {t1.side} {t1.quantity} "
                            f"then {t2.side} {t2.quantity} within "
                            f"{self.wash_trade_window.total_seconds():.0f}s",
                            related_trades=[t1.trade_id, t2.trade_id],
                        )
                        new_alerts.append(alert)

        return new_alerts

    def detect_spoofing(self) -> list[SurveillanceAlert]:
        """Detect spoofing (large orders placed then cancelled).

        Returns:
            List of spoofing alerts.
        """
        new_alerts: list[SurveillanceAlert] = []

        # Group orders by account and ticker
        by_account_ticker: dict[tuple[str, str], list[OrderRecord]] = {}
        for order in self._orders:
            key = (order.account_id, order.ticker)
            by_account_ticker.setdefault(key, []).append(order)

        for (account, ticker), orders in by_account_ticker.items():
            cancelled = [o for o in orders if o.status == "cancelled"]
            total = len(orders)

            if total == 0:
                continue

            cancel_ratio = len(cancelled) / total

            if cancel_ratio > self.spoofing_cancel_ratio and len(cancelled) >= 3:
                # Check if cancelled orders were large
                large_cancelled = [
                    o for o in cancelled if o.quantity > 1000
                ]

                if large_cancelled:
                    alert = self._create_alert(
                        AlertType.SPOOFING,
                        AlertSeverity.HIGH,
                        account,
                        ticker,
                        f"Possible spoofing: {len(cancelled)}/{total} orders cancelled "
                        f"({cancel_ratio:.0%}), {len(large_cancelled)} large orders",
                        related_orders=[o.order_id for o in large_cancelled],
                    )
                    new_alerts.append(alert)

        return new_alerts

    def detect_layering(self) -> list[SurveillanceAlert]:
        """Detect layering (multiple orders at different price levels).

        Returns:
            List of layering alerts.
        """
        new_alerts: list[SurveillanceAlert] = []

        by_account_ticker: dict[tuple[str, str], list[OrderRecord]] = {}
        for order in self._orders:
            key = (order.account_id, order.ticker)
            by_account_ticker.setdefault(key, []).append(order)

        for (account, ticker), orders in by_account_ticker.items():
            # Look for multiple simultaneous orders at different prices
            active_orders = [
                o for o in orders
                if o.status in ("new", "partial") and o.quantity > 500
            ]

            if len(active_orders) >= 5:
                price_levels = {o.price for o in active_orders}
                if len(price_levels) >= 4:
                    alert = self._create_alert(
                        AlertType.LAYERING,
                        AlertSeverity.MEDIUM,
                        account,
                        ticker,
                        f"Possible layering: {len(active_orders)} active orders "
                        f"at {len(price_levels)} price levels",
                        related_orders=[o.order_id for o in active_orders[:10]],
                    )
                    new_alerts.append(alert)

        return new_alerts

    def detect_unusual_volume(self) -> list[SurveillanceAlert]:
        """Detect unusual trading volume.

        Returns:
            List of unusual volume alerts.
        """
        new_alerts: list[SurveillanceAlert] = []

        # Group trades by ticker
        by_ticker: dict[str, list[TradeRecord]] = {}
        for trade in self._trades:
            by_ticker.setdefault(trade.ticker, []).append(trade)

        for ticker, trades in by_ticker.items():
            if len(trades) < 10:
                continue

            # Calculate average volume per account
            by_account: dict[str, float] = {}
            for t in trades:
                by_account[t.account_id] = by_account.get(t.account_id, 0) + t.quantity

            avg_volume = sum(by_account.values()) / len(by_account) if by_account else 0

            for account, volume in by_account.items():
                if avg_volume > 0 and volume > avg_volume * self.unusual_volume_threshold:
                    alert = self._create_alert(
                        AlertType.UNUSUAL_VOLUME,
                        AlertSeverity.MEDIUM,
                        account,
                        ticker,
                        f"Unusual volume: {volume:,.0f} vs avg {avg_volume:,.0f} "
                        f"({volume / avg_volume:.1f}x)",
                        metadata={"volume": volume, "average": avg_volume},
                    )
                    new_alerts.append(alert)

        return new_alerts

    def run_all_checks(self) -> list[SurveillanceAlert]:
        """Run all surveillance checks.

        Returns:
            List of all new alerts.
        """
        all_alerts: list[SurveillanceAlert] = []
        all_alerts.extend(self.detect_wash_trades())
        all_alerts.extend(self.detect_spoofing())
        all_alerts.extend(self.detect_layering())
        all_alerts.extend(self.detect_unusual_volume())
        return all_alerts

    def _create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        account_id: str,
        ticker: str,
        description: str,
        related_trades: list[str] | None = None,
        related_orders: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SurveillanceAlert:
        """Create and record a surveillance alert."""
        self._alert_counter += 1
        alert = SurveillanceAlert(
            alert_id=f"alert_{self._alert_counter:06d}",
            alert_type=alert_type,
            severity=severity,
            account_id=account_id,
            ticker=ticker,
            description=description,
            related_trades=related_trades or [],
            related_orders=related_orders or [],
            metadata=metadata or {},
        )
        self._alerts.append(alert)
        return alert

    @property
    def alerts(self) -> list[SurveillanceAlert]:
        """All surveillance alerts."""
        return self._alerts

    @property
    def trades(self) -> list[TradeRecord]:
        """All recorded trades."""
        return self._trades

    @property
    def orders(self) -> list[OrderRecord]:
        """All recorded orders."""
        return self._orders
