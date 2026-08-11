"""Rate limiter for data acquisition (pustaka/18 §2.1).

Provides two rate limiters:
  - ``RateLimiter``: sliding window rate limiting with thread safety (static).
  - ``DynamicRateLimiter``: adaptive rate limiter with exponential backoff
    on HTTP 429 / errors. Dynamically adjusts delay based on server response
    to avoid IP bans (anti HTTP 429 IP ban).

The ``DynamicRateLimiter`` is the recommended limiter for third-party API
calls (yfinance, FRED, NASA POWER, Sentinel-2) because it reacts to server
feedback instead of using a fixed rate.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Raised when the circuit breaker trips after too many consecutive errors.

    This distinguishes recoverable API errors (429, 500) from unrecoverable
    network-level failures (DNS resolution, connection refused) that won't
    resolve with retries.
    """


class RateLimiter:
    """Sliding window rate limiter.

    Args:
        max_calls: Maximum calls allowed in the window.
        window_seconds: Size of the sliding window in seconds.
    """

    def __init__(self, max_calls: float = 1.0, window_seconds: float = 1.0) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a call slot is available. Returns wait time in seconds."""
        with self._lock:
            now = time.monotonic()
            while self._timestamps and self._timestamps[0] <= now - self._window:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max_calls:
                wait = self._window - (now - self._timestamps[0])
                if wait > 0:
                    time.sleep(wait)
                now = time.monotonic()
                while self._timestamps and self._timestamps[0] <= now - self._window:
                    self._timestamps.popleft()

            self._timestamps.append(now)
            return 0.0


class DynamicRateLimiter:
    """Adaptive rate limiter for third-party API calls (anti HTTP 429 IP ban).

    Dynamically adjusts delay between requests based on:
    - Success/failure ratio
    - Response time
    - HTTP 429 (Too Many Requests) responses

    Starts with a base delay, increases on errors (exponential backoff),
    decreases on sustained success. This prevents IP bans from yfinance,
    FRED, NASA POWER, and other free APIs.

    Args:
        initial_delay: Starting delay between requests (seconds).
        min_delay: Floor delay — never go below this.
        max_delay: Ceiling delay — never exceed this (avoids infinite stalls).
        backoff_factor: Multiplier applied on error (1.5 = 50% increase).
        recovery_factor: Multiplier applied after sustained success (0.9 = 10% decrease).
        success_streak_threshold: Consecutive successes before reducing delay.
    """

    def __init__(
        self,
        initial_delay: float = 0.5,
        min_delay: float = 0.1,
        max_delay: float = 30.0,
        backoff_factor: float = 1.5,
        recovery_factor: float = 0.9,
        success_streak_threshold: int = 5,
    ) -> None:
        self.delay = initial_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self._success_streak_threshold = success_streak_threshold
        self._consecutive_success = 0
        self._consecutive_errors = 0
        self._total_requests = 0
        self._total_errors = 0
        self._lock = threading.Lock()
        self._circuit_tripped = False
        self._circuit_threshold = 10  # Trip after 10 consecutive errors

    def wait(self) -> None:
        """Sleep for the current delay period.

        Raises:
            CircuitBreakerError: If the circuit breaker has tripped.
        """
        if self._circuit_tripped:
            raise CircuitBreakerError(
                f"Circuit breaker tripped — {self._consecutive_errors} "
                f"consecutive errors. Call reset_circuit() to retry."
            )
        if self.delay > 0:
            time.sleep(self.delay)

    def acquire(self) -> float:
        """Compatibility alias for ``wait()`` — returns 0.0 (sliding-window API)."""
        self.wait()
        return 0.0

    def on_success(self, response_time: float | None = None) -> None:
        """Record a successful API call. Gradually reduce delay."""
        with self._lock:
            self._consecutive_success += 1
            self._consecutive_errors = 0
            self._total_requests += 1
            # After N consecutive successes, reduce delay
            if self._consecutive_success >= self._success_streak_threshold:
                self.delay = max(self.min_delay, self.delay * self.recovery_factor)
                self._consecutive_success = 0

    def on_error(self, status_code: int | None = None) -> None:
        """Record a failed API call. Increase delay (exponential backoff).

        HTTP 429 (Too Many Requests) triggers aggressive backoff
        (backoff_factor squared) to avoid IP bans.

        After ``circuit_threshold`` consecutive errors, the circuit breaker
        trips — subsequent calls to ``wait()`` will raise ``CircuitBreakerError``.
        """
        with self._lock:
            self._consecutive_errors += 1
            self._consecutive_success = 0
            self._total_requests += 1
            self._total_errors += 1
            # 429 = Too Many Requests → aggressive backoff
            if status_code == 429:
                self.delay = min(
                    self.max_delay, self.delay * (self.backoff_factor ** 2))
            else:
                self.delay = min(self.max_delay, self.delay * self.backoff_factor)
            if self._consecutive_errors >= self._circuit_threshold:
                self._circuit_tripped = True
                logger.error(
                    "Circuit breaker tripped after %d consecutive errors",
                    self._consecutive_errors,
                )
            logger.warning(
                "DynamicRateLimiter: delay increased to %.1fs "
                "(status=%s, consecutive errors: %d)",
                self.delay, status_code, self._consecutive_errors,
            )

    def reset_circuit(self) -> None:
        """Reset the circuit breaker after a network recovery."""
        with self._lock:
            self._circuit_tripped = False
            self._consecutive_errors = 0
            self.delay = max(self.min_delay, self.delay * 0.3)  # Aggressive recovery
            logger.info("Circuit breaker reset — delay reduced to %.1fs", self.delay)

    @property
    def circuit_tripped(self) -> bool:
        return self._circuit_tripped

    @property
    def stats(self) -> dict:
        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": self._total_errors / max(1, self._total_requests),
            "current_delay": self.delay,
            "circuit_tripped": self._circuit_tripped,
        }


def retry_with_backoff(
    func,
    max_retries: int = 3,
    rate_limiter: DynamicRateLimiter | RateLimiter | None = None,
):
    """Execute a function with retry and exponential backoff.

    Args:
        func: Callable that returns the result, or raises an exception.
            If it raises ``requests.exceptions.HTTPError``, the response
            status code is extracted for the rate limiter.
        max_retries: Maximum number of retry attempts.
        rate_limiter: Optional rate limiter for adaptive delays.

    Returns:
        The result of func, or None if all retries fail.
    """
    import requests

    for attempt in range(max_retries + 1):
        if rate_limiter is not None:
            if isinstance(rate_limiter, DynamicRateLimiter):
                rate_limiter.wait()
            else:
                rate_limiter.acquire()
        try:
            result = func()
            if isinstance(rate_limiter, DynamicRateLimiter):
                rate_limiter.on_success()
            return result
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if isinstance(rate_limiter, DynamicRateLimiter):
                rate_limiter.on_error(status)
            if attempt < max_retries:
                extra = rate_limiter.delay if isinstance(
                    rate_limiter, DynamicRateLimiter) else 1.0
                wait_time = (2 ** attempt) + extra
                logger.warning(
                    "HTTP %s on attempt %d/%d, retrying in %.1fs",
                    status, attempt + 1, max_retries, wait_time)
                time.sleep(wait_time)
            else:
                raise
        except Exception as exc:
            if isinstance(rate_limiter, DynamicRateLimiter):
                rate_limiter.on_error(None)
            if attempt < max_retries:
                extra = rate_limiter.delay if isinstance(
                    rate_limiter, DynamicRateLimiter) else 1.0
                wait_time = (2 ** attempt) + extra
                logger.warning(
                    "Error on attempt %d/%d: %s, retrying in %.1fs",
                    attempt + 1, max_retries, exc, wait_time)
                time.sleep(wait_time)
            else:
                raise
    return None
