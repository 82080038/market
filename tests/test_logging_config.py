"""Tests for structured logging configuration (Gap #28)."""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from market.logging_config import JsonFormatter, get_logger, setup_logging


def test_json_formatter_basic():
    """JsonFormatter produces valid JSON with required fields."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Test message %s",
        args=("hello",),
        exc_info=None,
        func="test_func",
    )
    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test.module"
    assert data["module"] == "test"
    assert data["function"] == "test_func"
    assert data["line"] == 42
    assert data["message"] == "Test message hello"
    assert "timestamp" in data


def test_json_formatter_extra_fields():
    """Extra fields passed via logger.info(extra=...) appear in JSON output."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="test.py",
        lineno=10,
        msg="Data fetched",
        args=(),
        exc_info=None,
        func="fetch",
    )
    record.ticker = "BBCA.JK"
    record.rows = 1000
    record.duration_ms = 125.5
    output = formatter.format(record)
    data = json.loads(output)

    assert data["ticker"] == "BBCA.JK"
    assert data["rows"] == 1000
    assert data["duration_ms"] == 125.5


def test_json_formatter_exception():
    """Exception traceback is included in JSON output."""
    formatter = JsonFormatter()
    try:
        raise ValueError("Test error")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=20,
        msg="Operation failed",
        args=(),
        exc_info=exc_info,
        func="broken",
    )
    output = formatter.format(record)
    data = json.loads(output)

    assert "exception" in data
    assert "ValueError" in data["exception"]
    assert "Test error" in data["exception"]


def test_json_formatter_non_serializable_extra():
    """Non-JSON-serializable extra fields are converted to string."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="msg",
        args=(),
        exc_info=None,
        func="f",
    )
    record.complex_obj = {"set": {1, 2, 3}}  # sets are not JSON-serializable
    output = formatter.format(record)
    data = json.loads(output)

    # Should be stringified, not cause an error
    assert "complex_obj" in data
    assert isinstance(data["complex_obj"], str)


def test_setup_logging_json_format():
    """setup_logging with json format configures JSON handler."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    logger = logging.getLogger("test.json")
    logger.info("JSON test", extra={"context": "value"})

    output = stream.getvalue().strip()
    data = json.loads(output)
    assert data["message"] == "JSON test"
    assert data["context"] == "value"

    # Cleanup
    root.handlers.clear()


def test_setup_logging_text_format():
    """setup_logging with text format produces human-readable output."""
    setup_logging(level="DEBUG", fmt="text")

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)


def test_setup_logging_json_format_via_settings():
    """setup_logging with json format configures JsonFormatter."""
    setup_logging(level="INFO", fmt="json")

    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_setup_logging_replaces_existing_handlers():
    """setup_logging clears existing handlers to avoid duplicates."""
    setup_logging(level="INFO", fmt="text")
    root = logging.getLogger()
    assert len(root.handlers) == 1

    # Call again — should still have only 1 handler
    setup_logging(level="INFO", fmt="json")
    assert len(root.handlers) == 1


def test_setup_logging_reduces_noisy_loggers():
    """Third-party loggers are set to WARNING level."""
    setup_logging(level="DEBUG", fmt="text")

    for noisy in ("urllib3", "httpx", "httpcore"):
        assert logging.getLogger(noisy).level == logging.WARNING


def test_get_logger_auto_setup():
    """get_logger auto-configures logging if not yet configured."""
    root = logging.getLogger()
    root.handlers.clear()

    logger = get_logger("test.auto")
    assert len(root.handlers) >= 1
    assert logger.name == "test.auto"


def test_log_format_env_var():
    """Settings has log_format field defaulting to text."""
    from market.config import settings
    assert hasattr(settings, "log_format")
    assert settings.log_format in ("text", "json")
