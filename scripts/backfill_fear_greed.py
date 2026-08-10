"""Backfill Fear & Greed Index from CNN API (rate-limited, non-blocking).

Fetches historical Fear & Greed Index data from CNN's public API.
Uses DynamicRateLimiter for adaptive backoff on 429s.

Usage:
    uv run python scripts/backfill_fear_greed.py &
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PG_DSN = "postgresql://petrick:market_dev@localhost:5432/market"

# Fear & Greed API endpoints
# CNN API blocks non-browser requests (418), use alternative.me instead
FNG_URL = "https://api.alternative.me/fng/?limit=0"

# Rate limiter settings (start conservative for CNN)
DEFAULT_INTERVAL = 2.0
MIN_INTERVAL = 0.5
MAX_INTERVAL = 30.0
BACKOFF_FACTOR = 2.0
SPEEDUP_FACTOR = 0.9


class SimpleRateLimiter:
    """Simple adaptive rate limiter for single domain."""

    def __init__(self):
        self._interval = DEFAULT_INTERVAL
        self._last_request = 0.0
        self._errors = 0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_request = time.monotonic()

    def record_success(self):
        self._errors = 0
        self._interval = max(MIN_INTERVAL, self._interval * SPEEDUP_FACTOR)

    def record_error(self):
        self._errors += 1
        self._interval = min(MAX_INTERVAL, self._interval * BACKOFF_FACTOR)
        logger.warning("Rate limiter backoff: interval=%.1fs, errors=%d", self._interval, self._errors)


def fetch_fear_greed_history(limiter: SimpleRateLimiter) -> list[dict] | None:
    """Fetch full Fear & Greed history from CNN API."""
    limiter.wait()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(FNG_URL, headers=headers, timeout=30)
    except requests.RequestException as e:
        limiter.record_error()
        logger.error("F&G request failed: %s", e)
        return None

    if resp.status_code == 429:
        limiter.record_error()
        logger.warning("HTTP 429 — backing off")
        return None
    if resp.status_code >= 400:
        limiter.record_error()
        logger.warning("HTTP %d", resp.status_code)
        return None

    limiter.record_success()
    try:
        data = resp.json()
    except json.JSONDecodeError:
        logger.error("F&G response not valid JSON")
        return None

    # alternative.me format: { "data": [ {"value": "30", "value_classification": "Fear", "timestamp": "1786320000"}, ... ] }
    results = []
    series = data.get("data", [])
    for point in series:
        value_str = point.get("value")
        label = point.get("value_classification")
        ts_str = point.get("timestamp")
        if value_str is not None and ts_str is not None:
            try:
                value = float(value_str)
                dt = datetime.fromtimestamp(int(ts_str), tz=timezone.utc)
                results.append({
                    "date": dt.date(),
                    "value": value,
                    "label": label or _classify_fg(value),
                    "source": "alternative_me",
                })
            except (ValueError, TypeError):
                continue

    return results


def _classify_fg(value: float) -> str:
    """Classify F&G value into rating."""
    if value >= 75:
        return "Extreme Greed"
    elif value >= 55:
        return "Greed"
    elif value >= 45:
        return "Neutral"
    elif value >= 25:
        return "Fear"
    else:
        return "Extreme Fear"


def upsert_fear_greed(pg_conn, records: list[dict]):
    """Upsert fear_greed records into PostgreSQL."""
    cur = pg_conn.cursor()
    for r in records:
        cur.execute("""
            INSERT INTO fear_greed (date, value, label, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (date, source) DO UPDATE SET
                value = EXCLUDED.value,
                label = EXCLUDED.label
        """, (r["date"], r["value"], r["label"], r["source"]))
    pg_conn.commit()
    cur.close()


def main():
    logger.info("Fear & Greed Index Backfill (CNN API)")
    logger.info("=" * 50)

    limiter = SimpleRateLimiter()

    # Fetch historical data
    logger.info("Fetching Fear & Greed history from CNN...")
    records = fetch_fear_greed_history(limiter)

    if not records:
        logger.error("No data fetched from CNN API")
        return

    logger.info("Fetched %d data points", len(records))

    logger.info("  Date range: %s to %s",
                 min(r["date"] for r in records),
                 max(r["date"] for r in records))

    # Insert to PostgreSQL
    pg_conn = psycopg2.connect(PG_DSN)
    pg_conn.autocommit = False

    try:
        upsert_fear_greed(pg_conn, records)
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM fear_greed")
        row = cur.fetchone()
        logger.info("\nPostgreSQL fear_greed: %d rows (%s to %s)", *row)
        cur.execute("SELECT COUNT(*) FROM fear_greed")
        total = cur.fetchone()[0]
        logger.info("  TOTAL: %d rows", total)
        cur.close()
    except Exception as e:
        pg_conn.rollback()
        logger.error("Upsert failed: %s", e)
    finally:
        pg_conn.close()

    logger.info("Fear & Greed backfill complete")


if __name__ == "__main__":
    main()
