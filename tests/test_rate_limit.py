"""Tests for rate limiter."""

from __future__ import annotations

import time

from market.data.rate_limit import RateLimiter


def test_rate_limiter_allows_first_call():
    rl = RateLimiter(max_calls=1, window_seconds=0.5)
    wait = rl.acquire()
    assert wait == 0.0


def test_rate_limiter_blocks_second_call():
    rl = RateLimiter(max_calls=1, window_seconds=0.5)
    rl.acquire()
    start = time.monotonic()
    rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.4


def test_rate_limiter_multiple_calls():
    rl = RateLimiter(max_calls=2, window_seconds=0.5)
    rl.acquire()
    rl.acquire()
    start = time.monotonic()
    rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.4
