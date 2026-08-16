"""Structured logging configuration (Gap #28).

Provides JSON-formatted structured logging for production observability:
- ``JsonFormatter``: emits each log record as a single-line JSON object
- ``setup_logging()``: configures root logger based on ``settings.log_format``
- Context fields: timestamp, level, module, function, line, message, plus
  any ``extra`` fields passed by the caller

JSON format is ideal for log aggregation (ELK, Loki, Datadog).
Text format (default) is human-readable for local development.

Usage:
    from market.logging_config import setup_logging
    setup_logging()  # call once at app startup

    import logging
    logger = logging.getLogger(__name__)
    logger.info("Data fetched", extra={"ticker": "BBCA.JK", "rows": 1000})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from market.config import settings


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Each record includes:
    - timestamp: ISO 8601 UTC
    - level: log level name
    - logger: logger name
    - module: module name
    - function: function name
    - line: line number
    - message: log message
    - Any extra fields passed via ``logger.info(..., extra={...})``
    - exception: traceback if an exception was logged
    """

    # Standard LogRecord attributes that should not be treated as "extra"
    _STANDARD_KEYS = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        """Format a LogRecord as JSON."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in self._STANDARD_KEYS and not key.startswith("_"):
                log_entry[key] = self._safe_json(value)

        # Add exception info if present
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str, ensure_ascii=False)

    @staticmethod
    def _safe_json(value: Any) -> Any:
        """Make a value JSON-safe."""
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return str(value)


def setup_logging(
    level: str | None = None,
    fmt: str | None = None,
) -> None:
    """Configure the root logger with structured or text formatting.

    Args:
        level: Override log level (defaults to ``settings.log_level``).
        fmt: Override format — "json" or "text" (defaults to ``settings.log_format``).
    """
    log_level = level or settings.log_level
    log_format = fmt or settings.log_format

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)

    if log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        # Human-readable text format for local development
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    root.addHandler(handler)

    # Reduce noise from third-party libraries
    for noisy in ("urllib3", "httpx", "httpcore", "asyncio", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger. Convenience function that ensures logging is configured.

    Args:
        name: Logger name (defaults to caller's module name).

    Returns:
        Configured logger instance.
    """
    if not logging.getLogger().handlers:
        setup_logging()
    return logging.getLogger(name)
