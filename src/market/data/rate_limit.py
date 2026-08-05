"""Rate limiter for data acquisition (pustaka/18 §2.1).

Sliding window rate limiting with thread safety.
"""

from __future__ import annotations

import threading
import time
from collections import deque


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
