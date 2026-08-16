"""Notification channels — Telegram, Email, Webhook (Gap #42).

Provides concrete implementations for the AlertChannel enum:
- ``TelegramNotifier``: sends messages via Telegram Bot API (HTTP)
- ``EmailNotifier``: sends emails via SMTP (stdlib smtplib)
- ``WebhookNotifier``: sends JSON POST to a custom URL
- ``NotificationDispatcher``: routes notifications to configured channels

All notifiers are designed for graceful degradation — if credentials are
not configured or the send fails, the error is logged but does NOT raise.
This ensures notification failures never crash the main pipeline.

Configuration via .env:
    TELEGRAM_BOT_TOKEN=123456:ABC-DEF
    TELEGRAM_CHAT_ID=123456789
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=user@gmail.com
    SMTP_PASSWORD=app_password
    SMTP_FROM=user@gmail.com
    SMTP_TO=user@gmail.com
    WEBHOOK_URL=https://example.com/hook
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests

from market.analysis.alerts import AlertChannel

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


@dataclass
class NotificationResult:
    """Result of a notification send attempt."""
    channel: AlertChannel
    success: bool
    error: str | None = None
    response: Any = None


class TelegramNotifier:
    """Send notifications via Telegram Bot API.

    Args:
        bot_token: Telegram bot token from BotFather.
        chat_id: Target chat/channel ID.
    """

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def is_configured(self) -> bool:
        """True if both bot_token and chat_id are set."""
        return bool(self._bot_token and self._chat_id)

    def send(self, message: str, parse_mode: str = "HTML") -> NotificationResult:
        """Send a message via Telegram.

        Args:
            message: Message text (HTML formatting supported).
            parse_mode: Telegram parse mode ("HTML" or "MarkdownV2").

        Returns:
            NotificationResult with success status.
        """
        if not self.is_configured:
            return NotificationResult(
                channel=AlertChannel.TELEGRAM,
                success=False,
                error="Telegram not configured (missing bot_token or chat_id)",
            )

        try:
            url = TELEGRAM_API_BASE.format(token=self._bot_token)
            resp = requests.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return NotificationResult(
                channel=AlertChannel.TELEGRAM,
                success=True,
                response=resp.json(),
            )
        except requests.RequestException as exc:
            logger.error("Telegram send failed: %s", exc)
            return NotificationResult(
                channel=AlertChannel.TELEGRAM,
                success=False,
                error=str(exc),
            )


class EmailNotifier:
    """Send notifications via SMTP.

    Args:
        host: SMTP server hostname.
        port: SMTP server port (587 for TLS, 465 for SSL).
        user: SMTP username.
        password: SMTP password (use app password for Gmail).
        from_addr: Sender email address.
        to_addr: Recipient email address.
        use_ssl: Use SSL directly (port 465) instead of STARTTLS (port 587).
    """

    def __init__(
        self,
        host: str | None = None,
        port: int = 587,
        user: str | None = None,
        password: str | None = None,
        from_addr: str | None = None,
        to_addr: str | None = None,
        use_ssl: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_addr
        self._to = to_addr
        self._use_ssl = use_ssl

    @property
    def is_configured(self) -> bool:
        """True if all required SMTP fields are set."""
        return bool(self._host and self._user and self._password and self._from and self._to)

    def send(
        self,
        subject: str,
        body: str,
        html: bool = False,
    ) -> NotificationResult:
        """Send an email notification.

        Args:
            subject: Email subject line.
            body: Email body (plain text or HTML).
            html: If True, body is HTML.

        Returns:
            NotificationResult with success status.
        """
        if not self.is_configured:
            return NotificationResult(
                channel=AlertChannel.EMAIL,
                success=False,
                error="Email not configured (missing SMTP settings)",
            )

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._from
            msg["To"] = self._to

            if html:
                msg.attach(MIMEText(body, "html", "utf-8"))
            else:
                msg.attach(MIMEText(body, "plain", "utf-8"))

            if self._use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self._host, self._port, context=context, timeout=15) as server:
                    server.login(self._user, self._password)
                    server.sendmail(self._from, [self._to], msg.as_string())
            else:
                with smtplib.SMTP(self._host, self._port, timeout=15) as server:
                    server.ehlo()
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                    server.login(self._user, self._password)
                    server.sendmail(self._from, [self._to], msg.as_string())

            return NotificationResult(
                channel=AlertChannel.EMAIL,
                success=True,
            )
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            return NotificationResult(
                channel=AlertChannel.EMAIL,
                success=False,
                error=str(exc),
            )


class WebhookNotifier:
    """Send notifications via HTTP POST webhook.

    Args:
        url: Webhook endpoint URL.
        headers: Optional extra headers.
    """

    def __init__(
        self,
        url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._url = url
        self._headers = headers or {"Content-Type": "application/json"}

    @property
    def is_configured(self) -> bool:
        """True if URL is set."""
        return bool(self._url)

    def send(self, payload: dict[str, Any]) -> NotificationResult:
        """Send a JSON POST to the webhook URL.

        Args:
            payload: JSON body to send.

        Returns:
            NotificationResult with success status.
        """
        if not self.is_configured:
            return NotificationResult(
                channel=AlertChannel.WEBHOOK,
                success=False,
                error="Webhook not configured (missing URL)",
            )

        try:
            resp = requests.post(
                self._url,
                json=payload,
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
            return NotificationResult(
                channel=AlertChannel.WEBHOOK,
                success=True,
                response=resp.json() if resp.content else None,
            )
        except requests.RequestException as exc:
            logger.error("Webhook send failed: %s", exc)
            return NotificationResult(
                channel=AlertChannel.WEBHOOK,
                success=False,
                error=str(exc),
            )


class NotificationDispatcher:
    """Routes notifications to multiple channels.

    Aggregates Telegram, Email, and Webhook notifiers. Sends to all
    configured channels and collects results.

    Args:
        telegram: Optional TelegramNotifier instance.
        email: Optional EmailNotifier instance.
        webhook: Optional WebhookNotifier instance.
    """

    def __init__(
        self,
        telegram: TelegramNotifier | None = None,
        email: EmailNotifier | None = None,
        webhook: WebhookNotifier | None = None,
    ) -> None:
        self._telegram = telegram
        self._email = email
        self._webhook = webhook

    @classmethod
    def from_env(cls) -> NotificationDispatcher:
        """Create a dispatcher configured from environment variables.

        Reads TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SMTP_*, WEBHOOK_URL
        from the process environment.
        """
        import os

        telegram = TelegramNotifier(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
        )

        smtp_host = os.environ.get("SMTP_HOST")
        email = EmailNotifier(
            host=smtp_host,
            port=int(os.environ.get("SMTP_PORT", "587")),
            user=os.environ.get("SMTP_USER"),
            password=os.environ.get("SMTP_PASSWORD"),
            from_addr=os.environ.get("SMTP_FROM"),
            to_addr=os.environ.get("SMTP_TO"),
            use_ssl=os.environ.get("SMTP_USE_SSL", "").lower() in ("1", "true", "yes"),
        ) if smtp_host else None

        webhook = WebhookNotifier(
            url=os.environ.get("WEBHOOK_URL"),
        )

        return cls(telegram=telegram, email=email, webhook=webhook)

    def dispatch(
        self,
        message: str,
        channels: list[AlertChannel] | None = None,
        subject: str = "Market Notification",
        extra_payload: dict[str, Any] | None = None,
    ) -> list[NotificationResult]:
        """Send a notification to all specified channels.

        Args:
            message: Notification message text.
            channels: List of channels to send to. If None, sends to all
                configured channels.
            subject: Subject line for email.
            extra_payload: Extra data for webhook payload.

        Returns:
            List of NotificationResult, one per channel attempted.
        """
        if channels is None:
            channels = []
            if self._telegram and self._telegram.is_configured:
                channels.append(AlertChannel.TELEGRAM)
            if self._email and self._email.is_configured:
                channels.append(AlertChannel.EMAIL)
            if self._webhook and self._webhook.is_configured:
                channels.append(AlertChannel.WEBHOOK)

        results: list[NotificationResult] = []

        for ch in channels:
            if ch == AlertChannel.TELEGRAM and self._telegram:
                results.append(self._telegram.send(message))
            elif ch == AlertChannel.EMAIL and self._email:
                results.append(self._email.send(subject, message))
            elif ch == AlertChannel.WEBHOOK and self._webhook:
                payload = {"message": message, "subject": subject}
                if extra_payload:
                    payload.update(extra_payload)
                results.append(self._webhook.send(payload))
            else:
                results.append(NotificationResult(
                    channel=ch,
                    success=False,
                    error="Channel not configured",
                ))

        return results

    @property
    def configured_channels(self) -> list[AlertChannel]:
        """List of channels that are configured and ready."""
        channels: list[AlertChannel] = []
        if self._telegram and self._telegram.is_configured:
            channels.append(AlertChannel.TELEGRAM)
        if self._email and self._email.is_configured:
            channels.append(AlertChannel.EMAIL)
        if self._webhook and self._webhook.is_configured:
            channels.append(AlertChannel.WEBHOOK)
        return channels
