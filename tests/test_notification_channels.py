"""Tests for notification channels (Gap #42)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from market.analysis.alerts import AlertChannel, AlertCondition, AlertManager
from market.notifications.channels import (
    EmailNotifier,
    NotificationDispatcher,
    NotificationResult,
    TelegramNotifier,
    WebhookNotifier,
)


# --- TelegramNotifier tests ---


def test_telegram_not_configured():
    """TelegramNotifier without credentials returns failure."""
    notifier = TelegramNotifier()
    assert not notifier.is_configured
    result = notifier.send("test message")
    assert not result.success
    assert "not configured" in result.error.lower()
    assert result.channel == AlertChannel.TELEGRAM


def test_telegram_configured():
    """TelegramNotifier with credentials is marked as configured."""
    notifier = TelegramNotifier(bot_token="123:ABC", chat_id="456")
    assert notifier.is_configured


@patch("market.notifications.channels.requests.post")
def test_telegram_send_success(mock_post):
    """Telegram send succeeds with valid API response."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}
    mock_post.return_value = mock_resp

    notifier = TelegramNotifier(bot_token="123:ABC", chat_id="456")
    result = notifier.send("Hello <b>world</b>")

    assert result.success
    assert result.response["ok"] is True
    mock_post.assert_called_once()


@patch("market.notifications.channels.requests.post")
def test_telegram_send_failure(mock_post):
    """Telegram send handles API errors gracefully."""
    import requests
    mock_post.side_effect = requests.RequestException("Network error")

    notifier = TelegramNotifier(bot_token="123:ABC", chat_id="456")
    result = notifier.send("test")

    assert not result.success
    assert "Network error" in result.error


# --- EmailNotifier tests ---


def test_email_not_configured():
    """EmailNotifier without SMTP settings returns failure."""
    notifier = EmailNotifier()
    assert not notifier.is_configured
    result = notifier.send("Subject", "Body")
    assert not result.success
    assert "not configured" in result.error.lower()


def test_email_configured():
    """EmailNotifier with all settings is marked as configured."""
    notifier = EmailNotifier(
        host="smtp.gmail.com", user="u", password="p",
        from_addr="a@b.com", to_addr="c@d.com",
    )
    assert notifier.is_configured


@patch("market.notifications.channels.smtplib.SMTP")
def test_email_send_success(mock_smtp):
    """Email send succeeds with mocked SMTP server."""
    server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = server

    notifier = EmailNotifier(
        host="smtp.gmail.com", port=587, user="u", password="p",
        from_addr="a@b.com", to_addr="c@d.com",
    )
    result = notifier.send("Test Subject", "Test Body")

    assert result.success
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("u", "p")
    server.sendmail.assert_called_once()


@patch("market.notifications.channels.smtplib.SMTP")
def test_email_send_html(mock_smtp):
    """Email send with html=True attaches HTML part."""
    server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = server

    notifier = EmailNotifier(
        host="smtp.gmail.com", port=587, user="u", password="p",
        from_addr="a@b.com", to_addr="c@d.com",
    )
    result = notifier.send("Subject", "<h1>HTML</h1>", html=True)

    assert result.success


def test_email_send_failure():
    """Email send handles SMTP errors gracefully."""
    notifier = EmailNotifier(
        host="bad.host", port=999, user="u", password="p",
        from_addr="a@b.com", to_addr="c@d.com",
    )
    result = notifier.send("Subject", "Body")
    # Will fail because bad.host doesn't resolve — but should not raise
    assert not result.success
    assert result.error is not None


# --- WebhookNotifier tests ---


def test_webhook_not_configured():
    """WebhookNotifier without URL returns failure."""
    notifier = WebhookNotifier()
    assert not notifier.is_configured
    result = notifier.send({"key": "value"})
    assert not result.success


@patch("market.notifications.channels.requests.post")
def test_webhook_send_success(mock_post):
    """Webhook send succeeds with valid response."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.content = b'{"status":"ok"}'
    mock_resp.json.return_value = {"status": "ok"}
    mock_post.return_value = mock_resp

    notifier = WebhookNotifier(url="https://example.com/hook")
    result = notifier.send({"alert": "test"})

    assert result.success
    assert result.response == {"status": "ok"}


# --- NotificationDispatcher tests ---


def test_dispatcher_no_channels():
    """Dispatcher with no notifiers returns empty result."""
    dispatcher = NotificationDispatcher()
    results = dispatcher.dispatch("test message")
    assert results == []
    assert dispatcher.configured_channels == []


def test_dispatcher_with_mocked_telegram():
    """Dispatcher routes to Telegram when configured."""
    telegram = TelegramNotifier(bot_token="123:ABC", chat_id="456")
    dispatcher = NotificationDispatcher(telegram=telegram)

    with patch("market.notifications.channels.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        results = dispatcher.dispatch("test")

    assert len(results) == 1
    assert results[0].channel == AlertChannel.TELEGRAM
    assert results[0].success


def test_dispatcher_multiple_channels():
    """Dispatcher sends to multiple configured channels."""
    telegram = TelegramNotifier(bot_token="123:ABC", chat_id="456")
    webhook = WebhookNotifier(url="https://example.com/hook")
    dispatcher = NotificationDispatcher(telegram=telegram, webhook=webhook)

    assert len(dispatcher.configured_channels) == 2

    with patch("market.notifications.channels.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.content = b'{"ok":true}'
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        results = dispatcher.dispatch("multi-channel test")

    assert len(results) == 2
    channels = {r.channel for r in results}
    assert AlertChannel.TELEGRAM in channels
    assert AlertChannel.WEBHOOK in channels


def test_dispatcher_from_env(monkeypatch):
    """Dispatcher.from_env reads configuration from environment."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    monkeypatch.setenv("WEBHOOK_URL", "https://example.com/hook")

    dispatcher = NotificationDispatcher.from_env()
    assert AlertChannel.TELEGRAM in dispatcher.configured_channels
    assert AlertChannel.WEBHOOK in dispatcher.configured_channels


def test_dispatcher_from_env_empty(monkeypatch):
    """Dispatcher.from_env with no env vars has no configured channels."""
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "WEBHOOK_URL"):
        monkeypatch.delenv(key, raising=False)

    dispatcher = NotificationDispatcher.from_env()
    assert dispatcher.configured_channels == []


# --- AlertManager integration test ---


def test_alert_manager_with_dispatcher():
    """AlertManager dispatches to external channels when triggered."""
    telegram = TelegramNotifier(bot_token="123:ABC", chat_id="456")
    dispatcher = NotificationDispatcher(telegram=telegram)
    manager = AlertManager(dispatcher=dispatcher)

    manager.create_alert(
        ticker="BBCA.JK",
        condition=AlertCondition.PRICE_ABOVE,
        threshold=9000,
        channels=[AlertChannel.IN_APP, AlertChannel.TELEGRAM],
    )

    with patch("market.notifications.channels.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        notifications = manager.evaluate("BBCA.JK", {"price": 9100})

    assert len(notifications) == 1
    assert notifications[0].delivered is False
    # Telegram API was called
    mock_post.assert_called_once()


def test_alert_manager_without_dispatcher():
    """AlertManager without dispatcher only creates in-app notifications."""
    manager = AlertManager()
    manager.create_alert(
        ticker="BBCA.JK",
        condition=AlertCondition.PRICE_ABOVE,
        threshold=9000,
        channels=[AlertChannel.IN_APP, AlertChannel.TELEGRAM],
    )

    notifications = manager.evaluate("BBCA.JK", {"price": 9100})
    assert len(notifications) == 1
    # No exception — just no external dispatch
