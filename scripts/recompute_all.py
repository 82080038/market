"""Recompute stale analysis tables from freshly-backfilled stock_prices.

Steps:
  1. Recompute daily_trading_stats from stock_prices (previous_close, change, value)
  2. Recompute daily_risk_metrics (VaR-95/99, CVaR, max_drawdown, annualized_volatility)
  3. Run existing run_all_recompute (incremental) for 7 internal tables

Usage:
    python scripts/recompute_all.py [--full]
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

# Ensure project root on sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from market.config import settings
from market.db.engine import get_sessionmaker
from market.analysis.recompute import run_all_recompute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── Step 1: daily_trading_stats ─────────────────────────────────────────────

DTS_UPSERT_SQL = """
INSERT INTO daily_trading_stats
    (ticker, date, previous_close, change, value, source, created_at)
VALUES
    (:ticker, :date, :prev_close, :change, :value, 'computed_from_ohlcv', :now)
ON CONFLICT (ticker, date, source) DO UPDATE SET
    previous_close = EXCLUDED.previous_close,
    change = EXCLUDED.change,
    value = EXCLUDED.value,
    created_at = EXCLUDED.created_at
"""


def recompute_daily_trading_stats(session) -> int:
    """Compute previous_close, change, and value (close*volume) from stock_prices.

    Only computes for dates not already present (incremental).
    Fields like frequency, offer/bid, listed_shares are NOT available from yfinance
    and will remain NULL — those require the GitHub Dataset-Saham-IDX source.
    """
    logger.info("Recomputing daily_trading_stats from stock_prices...")

    # Find the max date already in daily_trading_stats
    last_date = session.execute(
        text("SELECT MAX(date) FROM daily_trading_stats WHERE source = 'computed_from_ohlcv'")
    ).scalar()
    if last_date is None:
        last_date = session.execute(
            text("SELECT MAX(date) FROM daily_trading_stats")
        ).scalar()

    if last_date is not None:
        if isinstance(last_date, str):
            from datetime import date as _date
            last_date = _date.fromisoformat(last_date)
        start_date = last_date + timedelta(days=1)
        logger.info("  Incremental from %s", start_date)
    else:
        start_date = datetime(2025, 1, 1).date()
        logger.info("  Full recompute from %s", start_date)

    # Load OHLCV data for the date range
    rows = session.execute(text("""
        SELECT ticker, timestamp::date as date, open, high, low, close, volume
        FROM stock_prices
        WHERE timeframe = '1d'
          AND timestamp::date >= :start
          AND volume IS NOT NULL
          AND close IS NOT NULL
        ORDER BY ticker, timestamp
    """), {"start": start_date}).fetchall()

    if not rows:
        logger.info("  No new rows to compute")
        return 0

    df = pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)

    # Group by ticker and compute previous_close and change
    grouped = df.groupby("ticker", sort=False)
    batch = []
    count = 0
    now = datetime.now(UTC)

    for ticker, group in grouped:
        group = group.sort_values("date")
        prev_close = group["close"].shift(1)
        change = group["close"] - prev_close
        value = group["close"] * group["volume"]

        for idx, row in group.iterrows():
            pc = prev_close.loc[idx]
            ch = change.loc[idx]
            if pd.notna(pc) and pd.notna(ch):
                batch.append({
                    "ticker": ticker,
                    "date": row["date"],
                    "prev_close": round(float(pc), 4),
                    "change": round(float(ch), 4),
                    "value": round(float(value.loc[idx]), 2),
                    "now": now,
                })
                count += 1

            if len(batch) >= 5000:
                session.execute(text(DTS_UPSERT_SQL), batch)
                session.commit()
                logger.info("  daily_trading_stats: %d rows", count)
                batch.clear()

    if batch:
        session.execute(text(DTS_UPSERT_SQL), batch)
        session.commit()

    logger.info("  daily_trading_stats: DONE, %d rows", count)
    return count


# ── Step 2: daily_risk_metrics ──────────────────────────────────────────────

DRM_DELETE_SQL = "DELETE FROM daily_risk_metrics WHERE ticker = :ticker AND date = :date"
DRM_INSERT_SQL = """
INSERT INTO daily_risk_metrics
    (ticker, date, var_95, var_99, cvar_95, cvar_99, max_drawdown, annualized_volatility, created_at)
VALUES
    (:ticker, :date, :var95, :var99, :cvar95, :cvar99, :max_dd, :ann_vol, :now)
"""


def recompute_daily_risk_metrics(session) -> int:
    """Compute VaR, CVaR, max_drawdown, annualized_volatility from stock_prices.

    Uses 252-day rolling window for VaR/CVaR, 252-day for annualized volatility,
    and 252-day max drawdown. Per-ticker, incremental (only new dates).
    """
    logger.info("Recomputing daily_risk_metrics from stock_prices...")

    # Find max date already in daily_risk_metrics
    last_date = session.execute(
        text("SELECT MAX(date) FROM daily_risk_metrics")
    ).scalar()
    if last_date is not None:
        if isinstance(last_date, str):
            from datetime import date as _date
            last_date = _date.fromisoformat(last_date)
        # Need 252 trading days of history for lookback
        lookback_start = last_date - timedelta(days=400)
        start_date = last_date + timedelta(days=1)
        logger.info("  Incremental from %s (lookback from %s)", start_date, lookback_start)
    else:
        lookback_start = datetime(2024, 1, 1).date()
        start_date = datetime(2025, 1, 1).date()
        logger.info("  Full recompute from %s (lookback from %s)", start_date, lookback_start)

    # Load tickers that have data after start_date
    tickers = session.execute(text("""
        SELECT DISTINCT ticker FROM stock_prices
        WHERE timeframe = '1d' AND timestamp::date >= :start
        ORDER BY ticker
    """), {"start": start_date}).fetchall()

    if not tickers:
        logger.info("  No new tickers to compute")
        return 0

    ticker_list = [t[0] for t in tickers]
    logger.info("  %d tickers to process", len(ticker_list))

    count = 0
    now = datetime.now(UTC)
    window = 252
    batch = []

    for ticker in ticker_list:
        rows = session.execute(text("""
            SELECT timestamp::date as date, close
            FROM stock_prices
            WHERE ticker = :ticker AND timeframe = '1d'
              AND timestamp::date >= :lookback
            ORDER BY timestamp
        """), {"ticker": ticker, "lookback": lookback_start}).fetchall()

        if len(rows) < window:
            continue

        df = pd.DataFrame(rows, columns=["date", "close"])
        df["close"] = df["close"].astype(float)
        df["returns"] = df["close"].pct_change(fill_method=None)

        for i in range(window, len(df)):
            date_val = df["date"].iloc[i]
            if date_val < start_date:
                continue

            ret_window = df["returns"].iloc[i - window + 1: i + 1].dropna()
            if len(ret_window) < 50:
                continue

            ret_pct = ret_window * 100

            var_95 = float(np.percentile(ret_pct, 5))
            var_99 = float(np.percentile(ret_pct, 1))
            cvar_95 = float(ret_pct[ret_pct <= var_95].mean()) if (ret_pct <= var_95).any() else var_95
            cvar_99 = float(ret_pct[ret_pct <= var_99].mean()) if (ret_pct <= var_99).any() else var_99

            close_window = df["close"].iloc[i - window + 1: i + 1]
            running_max = close_window.cummax()
            drawdown = (close_window / running_max - 1) * 100
            max_dd = float(drawdown.min())

            ann_vol = float(ret_pct.std() * np.sqrt(252))

            batch.append({
                "ticker": ticker,
                "date": date_val,
                "var95": round(var_95, 4),
                "var99": round(var_99, 4),
                "cvar95": round(cvar_95, 4),
                "cvar99": round(cvar_99, 4),
                "max_dd": round(max_dd, 4),
                "ann_vol": round(ann_vol, 4),
                "now": now,
            })
            count += 1

            if len(batch) >= 5000:
                for r in batch:
                    session.execute(text(DRM_DELETE_SQL), {"ticker": r["ticker"], "date": r["date"]})
                session.execute(text(DRM_INSERT_SQL), batch)
                session.commit()
                logger.info("  daily_risk_metrics: %d rows (last: %s)", count, ticker)
                batch.clear()

    if batch:
        for r in batch:
            session.execute(text(DRM_DELETE_SQL), {"ticker": r["ticker"], "date": r["date"]})
        session.execute(text(DRM_INSERT_SQL), batch)
        session.commit()

    logger.info("  daily_risk_metrics: DONE, %d rows", count)
    return count


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    full_mode = "--full" in sys.argv

    logger.info("=== Recompute All Pipeline (mode=%s) ===", "full" if full_mode else "incremental")
    logger.info("Database: %s", settings.resolved_database_url)
    t0 = time.time()

    session = get_sessionmaker()()
    try:
        # Step 1: daily_trading_stats
        t1 = time.time()
        dts_count = recompute_daily_trading_stats(session)
        logger.info("Step 1 (daily_trading_stats): %d rows in %.1fs", dts_count, time.time() - t1)

        # Step 2: daily_risk_metrics
        t2 = time.time()
        drm_count = recompute_daily_risk_metrics(session)
        logger.info("Step 2 (daily_risk_metrics): %d rows in %.1fs", drm_count, time.time() - t2)

        # Step 3: run_all_recompute (7 internal tables)
        t3 = time.time()
        logger.info("Step 3: Running run_all_recompute (incremental=%s)...", not full_mode)
        results = run_all_recompute(session, dry_run=False, incremental=not full_mode)
        for name, cnt in results.items():
            status = f"{cnt} rows" if cnt >= 0 else "FAILED"
            logger.info("  %s: %s", name, status)
        logger.info("Step 3 done in %.1fs", time.time() - t3)

        # Summary
        elapsed = time.time() - t0
        logger.info("=" * 60)
        logger.info("RECOMPUTE COMPLETE in %.1fs (%.1f min)", elapsed, elapsed / 60)
        logger.info("  daily_trading_stats: %d rows", dts_count)
        logger.info("  daily_risk_metrics:  %d rows", drm_count)
        for name, cnt in results.items():
            status = f"{cnt} rows" if cnt >= 0 else "FAILED"
            logger.info("  %s: %s", name, status)
        logger.info("=" * 60)

    finally:
        session.close()


if __name__ == "__main__":
    main()
