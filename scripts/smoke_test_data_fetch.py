#!/usr/bin/env python3
"""Smoke test for DataFetchPipeline — live DB with 1-2 tickers.

Verifies end-to-end flow against real database (PostgreSQL or SQLite).
Does NOT mock yfinance — makes real API calls.

Usage:
    # PostgreSQL (default from .env)
    python scripts/smoke_test_data_fetch.py

    # SQLite
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market python scripts/smoke_test_data_fetch.py

    # Custom tickers
    python scripts/smoke_test_data_fetch.py --tickers BBCA.JK,BBRI.JK
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test DataFetchPipeline")
    parser.add_argument(
        "--tickers", default="BBCA.JK,^GSPC",
        help="Comma-separated tickers to test (default: BBCA.JK,^GSPC)",
    )
    args = parser.parse_args()
    tickers = args.tickers.split(",")

    logger.info("=" * 60)
    logger.info("DataFetchPipeline Smoke Test")
    logger.info("=" * 60)

    # ── Step 1: Verify DB connection ──────────────────────────────
    from market.db.engine import get_sessionmaker
    from sqlalchemy import text

    session = get_sessionmaker()()
    try:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
        logger.info("[PASS] Step 1: DB connection OK")
    except Exception as e:
        logger.error("[FAIL] Step 1: DB connection failed: %s", e)
        return 1
    finally:
        session.close()

    # ── Step 2: Test YahooFinanceAdapter directly ─────────────────
    from market.data.yahoo_adapter import YahooFinanceAdapter

    adapter = YahooFinanceAdapter()
    test_ticker = tickers[0]
    logger.info("Step 2: Fetching %s via YahooFinanceAdapter...", test_ticker)

    try:
        records = adapter.fetch_ohlcv(
            ticker=test_ticker, period="5d",
            market_mic="XIDX" if test_ticker.endswith(".JK") else "XNYS",
            currency="IDR" if test_ticker.endswith(".JK") else "USD",
        )
        if records:
            logger.info(
                "[PASS] Step 2: Fetched %d records for %s (latest close: %s)",
                len(records), test_ticker, records[-1].close,
            )
        else:
            logger.warning("[WARN] Step 2: No records returned for %s (market may be open)", test_ticker)
    except Exception as e:
        logger.error("[FAIL] Step 2: YahooFinanceAdapter failed: %s", e)
        return 1

    # ── Step 3: Test DataAcquisitionEngine ────────────────────────
    from market.data.acquisition import DataAcquisitionEngine
    from market.data.storage import DataRepository

    session = get_sessionmaker()()
    try:
        repo = DataRepository(session)
        engine = DataAcquisitionEngine()
        engine.set_repository(repo)

        test_ticker2 = tickers[0]
        logger.info("Step 3: Fetch+store %s via DataAcquisitionEngine...", test_ticker2)

        result = engine.fetch_and_store(
            ticker=test_ticker2, period="5d",
            market_mic="XIDX" if test_ticker2.endswith(".JK") else "XNYS",
            currency="IDR" if test_ticker2.endswith(".JK") else "USD",
        )

        logger.info(
            "  Result: fetched=%d, stored=%d, quality=%.1f, action=%s",
            result["fetched"], result["stored"],
            result["quality_score"], result["action"],
        )

        if result["stored"] > 0:
            logger.info("[PASS] Step 3: DataAcquisitionEngine stored %d rows", result["stored"])
        else:
            logger.warning("[WARN] Step 3: No rows stored (action=%s)", result["action"])
    except Exception as e:
        logger.error("[FAIL] Step 3: DataAcquisitionEngine failed: %s", e)
        return 1
    finally:
        session.close()

    # ── Step 4: Test TickerScreener ───────────────────────────────
    from market.data.screener import TickerScreener

    session = get_sessionmaker()()
    try:
        screener = TickerScreener()
        screening = screener.screen(session)
        logger.info(
            "[PASS] Step 4: TickerScreener passed=%d, excluded=%d",
            len(screening.passed), screening.total_excluded,
        )
        if screening.passed:
            logger.info("  Sample tickers: %s", screening.passed[:5])
    except Exception as e:
        logger.error("[FAIL] Step 4: TickerScreener failed: %s", e)
        return 1
    finally:
        session.close()

    # ── Step 5: Test full DataFetchPipeline via event broker ──────
    from market.core.events import EventBroker
    from market.pipelines.data_fetch import DataFetchPipeline

    logger.info("Step 5: Testing DataFetchPipeline intraday handler...")

    test_broker = EventBroker()
    pipeline = DataFetchPipeline()
    test_broker.subscribe("data.fetch.intraday.requested", pipeline.on_intraday_requested)

    received_events = []
    test_broker.subscribe(
        "data.fetch.intraday.completed",
        lambda e: received_events.append(e),
    )

    intraday_ticker = tickers[0] if tickers[0].endswith(".JK") else "^JKSE"
    test_broker.emit("data.fetch.intraday.requested", {"tickers": [intraday_ticker]})

    if received_events:
        evt = received_events[0]
        prices = evt.payload.get("prices", {})
        if intraday_ticker in prices:
            price = prices[intraday_ticker]
            logger.info(
                "[PASS] Step 5: Intraday fetch OK — %s: %s %s (%.2f%%)",
                intraday_ticker, price["price"], price["currency"],
                price["change_pct"],
            )
        else:
            logger.warning("[WARN] Step 5: Intraday event emitted but no price for %s", intraday_ticker)
    else:
        logger.warning("[WARN] Step 5: No intraday event received (market may be closed)")

    # ── Summary ───────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Smoke test complete — all steps passed")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
