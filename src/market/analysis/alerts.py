"""Watchlist alerts and notification routing (pustaka/18 §13, pustaka/33).

Provides:
- Alert rule definition (price, volume, indicator, news)
- Alert evaluation and triggering
- Notification routing (Telegram, email, in-app)
- 15 alert types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AlertCondition(Enum):
    """Alert trigger conditions (15 types)."""

    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CHANGE_PCT = "price_change_pct"
    VOLUME_SPIKE = "volume_spike"
    VOLUME_AVERAGE = "volume_average"
    RSI_OVERBOUGHT = "rsi_overbought"
    RSI_OVERSOLD = "rsi_oversold"
    MACD_CROSS = "macd_cross"
    MA_CROSS = "ma_cross"
    BOLLINGER_BREAK = "bollinger_break"
    NEWS_TRIGGER = "news_trigger"
    DIVIDEND_EX = "dividend_ex"
    CORPORATE_ACTION = "corporate_action"
    DRAWDOWN_LIMIT = "drawdown_limit"
    STOP_LOSS = "stop_loss"


class AlertChannel(Enum):
    """Alert notification channels."""

    TELEGRAM = "telegram"
    EMAIL = "email"
    IN_APP = "in_app"
    WEBHOOK = "webhook"


class AlertStatus(Enum):
    """Alert status."""

    ACTIVE = "active"
    TRIGGERED = "triggered"
    EXPIRED = "expired"
    DISABLED = "disabled"


@dataclass
class AlertRule:
    """A watchlist alert rule."""

    alert_id: str
    ticker: str
    condition: AlertCondition
    threshold: float = 0.0
    channels: list[AlertChannel] = field(default_factory=lambda: [AlertChannel.IN_APP])
    message: str = ""
    status: AlertStatus = AlertStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    triggered_at: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertNotification:
    """A triggered alert notification."""

    notification_id: str
    alert_id: str
    ticker: str
    condition: AlertCondition
    message: str
    channels: list[AlertChannel]
    sent_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    delivered: bool = False


class AlertManager:
    """Manages watchlist alerts and notifications.

    Supports 15 alert types with multi-channel routing.
    """

    def __init__(self) -> None:
        self._alerts: dict[str, AlertRule] = {}
        self._notifications: list[AlertNotification] = []
        self._alert_counter = 0
        self._notif_counter = 0

    def create_alert(
        self,
        ticker: str,
        condition: AlertCondition,
        threshold: float = 0.0,
        channels: list[AlertChannel] | None = None,
        message: str = "",
        expires_at: str | None = None,
    ) -> AlertRule:
        """Create a new alert rule.

        Args:
            ticker: Ticker to monitor.
            condition: Alert condition type.
            threshold: Trigger threshold value.
            channels: Notification channels.
            message: Custom alert message.
            expires_at: Optional expiry timestamp.

        Returns:
            The created AlertRule.
        """
        self._alert_counter += 1
        alert_id = f"ALR-{self._alert_counter:05d}"
        alert = AlertRule(
            alert_id=alert_id,
            ticker=ticker,
            condition=condition,
            threshold=threshold,
            channels=channels or [AlertChannel.IN_APP],
            message=message or f"{condition.value} for {ticker}",
            expires_at=expires_at,
        )
        self._alerts[alert_id] = alert
        return alert

    def evaluate(
        self,
        ticker: str,
        current_data: dict[str, float],
    ) -> list[AlertNotification]:
        """Evaluate alerts for a ticker against current data.

        Args:
            ticker: Ticker to evaluate.
            current_data: Dict with current price, volume, RSI, etc.

        Returns:
            List of triggered AlertNotifications.
        """
        notifications: list[AlertNotification] = []
        now = datetime.now(UTC).isoformat()

        for alert in self._alerts.values():
            if alert.ticker != ticker or alert.status != AlertStatus.ACTIVE:
                continue

            if alert.expires_at and alert.expires_at < now:
                alert.status = AlertStatus.EXPIRED
                continue

            triggered = self._check_condition(alert, current_data)
            if triggered:
                notif = self._trigger(alert, current_data)
                notifications.append(notif)

        return notifications

    def _check_condition(
        self,
        alert: AlertRule,
        data: dict[str, float],
    ) -> bool:
        """Check if alert condition is met.

        Args:
            alert: Alert rule to check.
            data: Current market data.

        Returns:
            True if condition is triggered.
        """
        c = alert.condition
        t = alert.threshold

        if c == AlertCondition.PRICE_ABOVE:
            return data.get("price", 0) > t
        elif c == AlertCondition.PRICE_BELOW:
            return data.get("price", 0) < t
        elif c == AlertCondition.PRICE_CHANGE_PCT:
            return abs(data.get("change_pct", 0)) >= t
        elif c == AlertCondition.VOLUME_SPIKE:
            avg_vol = data.get("avg_volume", 1)
            return data.get("volume", 0) > avg_vol * t
        elif c == AlertCondition.VOLUME_AVERAGE:
            return data.get("volume", 0) >= t
        elif c == AlertCondition.RSI_OVERBOUGHT:
            return data.get("rsi", 0) > t
        elif c == AlertCondition.RSI_OVERSOLD:
            return data.get("rsi", 100) < t
        elif c == AlertCondition.MACD_CROSS:
            return bool(data.get("macd_cross", False))
        elif c == AlertCondition.MA_CROSS:
            return bool(data.get("ma_cross", False))
        elif c == AlertCondition.BOLLINGER_BREAK:
            return bool(data.get("bollinger_break", False))
        elif c == AlertCondition.NEWS_TRIGGER:
            return data.get("news_sentiment", 0) > t
        elif c == AlertCondition.DIVIDEND_EX:
            return bool(data.get("dividend_ex", False))
        elif c == AlertCondition.CORPORATE_ACTION:
            return bool(data.get("corporate_action", False))
        elif c == AlertCondition.DRAWDOWN_LIMIT:
            return data.get("drawdown_pct", 0) >= t
        elif c == AlertCondition.STOP_LOSS:
            return data.get("price", 0) <= t
        return False

    def _trigger(
        self,
        alert: AlertRule,
        data: dict[str, float],
    ) -> AlertNotification:
        """Trigger an alert and create notification.

        Args:
            alert: Alert to trigger.
            data: Current market data.

        Returns:
            AlertNotification.
        """
        self._notif_counter += 1
        notif_id = f"NTF-{self._notif_counter:06d}"

        msg = alert.message or f"{alert.condition.value} for {alert.ticker}"
        price = data.get("price", 0.0)
        full_msg = f"{msg} (price: {price})"

        notif = AlertNotification(
            notification_id=notif_id,
            alert_id=alert.alert_id,
            ticker=alert.ticker,
            condition=alert.condition,
            message=full_msg,
            channels=alert.channels,
        )
        self._notifications.append(notif)

        alert.status = AlertStatus.TRIGGERED
        alert.triggered_at = datetime.now(UTC).isoformat()

        return notif

    def disable_alert(self, alert_id: str) -> bool:
        """Disable an alert.

        Args:
            alert_id: Alert to disable.

        Returns:
            True if disabled, False if not found.
        """
        alert = self._alerts.get(alert_id)
        if alert is None:
            return False
        alert.status = AlertStatus.DISABLED
        return True

    def enable_alert(self, alert_id: str) -> bool:
        """Re-enable a disabled alert.

        Args:
            alert_id: Alert to enable.

        Returns:
            True if enabled, False if not found.
        """
        alert = self._alerts.get(alert_id)
        if alert is None:
            return False
        alert.status = AlertStatus.ACTIVE
        return True

    def get_alerts(self, ticker: str | None = None) -> list[AlertRule]:
        """Get alerts, optionally filtered by ticker."""
        if ticker:
            return [a for a in self._alerts.values() if a.ticker == ticker]
        return list(self._alerts.values())

    def get_alert(self, alert_id: str) -> AlertRule | None:
        """Get an alert by ID."""
        return self._alerts.get(alert_id)

    @property
    def notifications(self) -> list[AlertNotification]:
        """All notifications."""
        return list(self._notifications)

    @property
    def active_alerts(self) -> list[AlertRule]:
        """All active alerts."""
        return [a for a in self._alerts.values() if a.status == AlertStatus.ACTIVE]
