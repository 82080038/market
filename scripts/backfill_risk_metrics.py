"""Backfill daily_risk_metrics with per-ticker VaR, CVaR, max drawdown, volatility.

Computes risk metrics from OHLCV daily returns using a 252-day rolling window.
Uses historical simulation method for VaR/CVaR.

Usage:
    DB_PATH=data/market_research.db python scripts/backfill_risk_metrics.py [--tickers AAA,BBB] [--batch-size 200]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from market.db.engine import get_sessionmaker
from market.db.models import DailyRiskMetric, OHLCV

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

ROLLING_WINDOW = 252  # 1 year of trading days
TRADING_DAYS = 252


def load_ohlcv_df(session, ticker: str) -> pd.DataFrame:
    rows = session.execute(
        select(OHLCV.close, OHLCV.timestamp)
        .where(OHLCV.ticker == ticker, OHLCV.timeframe == "1d")
        .order_by(OHLCV.timestamp)
    ).all()
    if not rows:
        return pd.DataFrame()
    data = [{"close": float(r[0])} for r in rows]
    idx = pd.DatetimeIndex([r[1] for r in rows])
    return pd.DataFrame(data, index=idx)


def compute_risk_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling VaR, CVaR, max drawdown, annualized volatility.

    Returns DataFrame indexed by date with columns:
        var_95, var_99, cvar_95, cvar_99, max_drawdown, annualized_volatility
    """
    # Deduplicate index (some tickers have duplicate dates)
    df = df[~df.index.duplicated(keep="last")]

    close = df["close"].astype(float)
    returns = close.pct_change().dropna()

    if len(returns) < 20:
        return pd.DataFrame()

    result = pd.DataFrame(index=df.index)

    # Rolling VaR (historical simulation)
    rolling_var_95 = returns.rolling(ROLLING_WINDOW, min_periods=60).quantile(0.05)
    rolling_var_99 = returns.rolling(ROLLING_WINDOW, min_periods=60).quantile(0.01)

    result["var_95"] = rolling_var_95
    result["var_99"] = rolling_var_99

    # Rolling CVaR (expected shortfall = mean of returns below VaR)
    def _cvar(window, percentile):
        if len(window) < 60:
            return np.nan
        var = np.quantile(window, percentile)
        tail = window[window <= var]
        return tail.mean() if len(tail) > 0 else np.nan

    result["cvar_95"] = returns.rolling(ROLLING_WINDOW, min_periods=60).apply(
        lambda w: _cvar(w, 0.05), raw=True
    )
    result["cvar_99"] = returns.rolling(ROLLING_WINDOW, min_periods=60).apply(
        lambda w: _cvar(w, 0.01), raw=True
    )

    # Rolling max drawdown (252-day window)
    def _max_dd(window_prices):
        if len(window_prices) < 60:
            return np.nan
        cummax = np.maximum.accumulate(window_prices)
        drawdown = (window_prices - cummax) / cummax
        return drawdown.min()

    result["max_drawdown"] = close.rolling(ROLLING_WINDOW, min_periods=60).apply(
        _max_dd, raw=True
    )

    # Rolling annualized volatility (252-day window, min 60)
    rolling_vol = returns.rolling(ROLLING_WINDOW, min_periods=60).std() * np.sqrt(TRADING_DAYS)
    result["annualized_volatility"] = rolling_vol

    # Drop rows where all metrics are NaN
    result = result.dropna(how="all")
    return result


def backfill_ticker(session, ticker: str, batch_size: int = 200) -> tuple[int, int]:
    df = load_ohlcv_df(session, ticker)
    if df.empty or len(df) < 60:
        return 0, 0

    # Deduplicate index (some tickers have duplicate dates)
    df = df[~df.index.duplicated(keep="last")]

    risk_df = compute_risk_metrics(df)
    if risk_df.empty:
        return 0, 0

    # Get existing dates
    existing = session.execute(
        text("SELECT DISTINCT date FROM daily_risk_metrics WHERE ticker = :t"),
        {"t": ticker},
    ).fetchall()
    existing_dates = {r[0] for r in existing}

    inserted = 0
    skipped = 0
    batch = []

    for ts, row in risk_df.iterrows():
        d = ts.date() if hasattr(ts, "date") else ts

        if d in existing_dates:
            skipped += 1
            continue

        batch.append({
            "ticker": ticker,
            "date": str(d),
            "var_95": float(row["var_95"]) if not np.isnan(row.get("var_95", np.nan)) else None,
            "var_99": float(row["var_99"]) if not np.isnan(row.get("var_99", np.nan)) else None,
            "cvar_95": float(row["cvar_95"]) if not np.isnan(row.get("cvar_95", np.nan)) else None,
            "cvar_99": float(row["cvar_99"]) if not np.isnan(row.get("cvar_99", np.nan)) else None,
            "max_drawdown": float(row["max_drawdown"]) if not np.isnan(row.get("max_drawdown", np.nan)) else None,
            "annualized_volatility": float(row["annualized_volatility"]) if not np.isnan(row.get("annualized_volatility", np.nan)) else None,
            "portfolio_value": float(df.loc[ts, "close"]),
        })

        if len(batch) >= batch_size:
            session.execute(
                text("""INSERT OR IGNORE INTO daily_risk_metrics
                    (ticker, date, var_95, var_99, cvar_95, cvar_99,
                     max_drawdown, annualized_volatility, portfolio_value, created_at)
                    VALUES (:ticker, :date, :var_95, :var_99, :cvar_95, :cvar_99,
                     :max_drawdown, :annualized_volatility, :portfolio_value, datetime('now'))"""),
                batch,
            )
            session.commit()
            inserted += len(batch)
            batch = []

    if batch:
        session.execute(
            text("""INSERT OR IGNORE INTO daily_risk_metrics
                (ticker, date, var_95, var_99, cvar_95, cvar_99,
                 max_drawdown, annualized_volatility, portfolio_value, created_at)
                VALUES (:ticker, :date, :var_95, :var_99, :cvar_95, :cvar_99,
                 :max_drawdown, :annualized_volatility, :portfolio_value, datetime('now'))"""),
            batch,
        )
        session.commit()
        inserted += len(batch)

    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Backfill daily risk metrics")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--tickers", type=str, default=None)
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    session = get_sessionmaker()()

    if args.clear:
        logger.info("Clearing daily_risk_metrics table...")
        session.execute(text("DELETE FROM daily_risk_metrics"))
        session.commit()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        rows = session.execute(
            text(
                "SELECT DISTINCT ticker FROM ohlcv "
                "WHERE ticker LIKE '%.JK' AND timeframe='1d' "
                "ORDER BY ticker"
            )
        ).fetchall()
        tickers = [r[0] for r in rows]

    total = len(tickers)
    logger.info("Backfilling risk metrics for %d tickers", total)

    total_inserted = 0
    total_skipped = 0
    total_empty = 0

    for i, ticker in enumerate(tickers):
        inserted, skipped = backfill_ticker(session, ticker, args.batch_size)
        total_inserted += inserted
        total_skipped += skipped

        if inserted == 0 and skipped == 0:
            total_empty += 1

        if (i + 1) % 10 == 0 or (i + 1) == total:
            logger.info(
                "[%d/%d] %s: +%d ins, %d skip | Running: ins=%d skip=%d empty=%d",
                i + 1, total, ticker, inserted, skipped,
                total_inserted, total_skipped, total_empty,
            )

    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("  Total tickers: %d", total)
    logger.info("  Total inserted: %d", total_inserted)
    logger.info("  Total skipped: %d", total_skipped)
    logger.info("  Empty/insufficient: %d", total_empty)

    count = session.execute(text("SELECT COUNT(*) FROM daily_risk_metrics")).scalar()
    dates = session.execute(text("SELECT COUNT(DISTINCT date) FROM daily_risk_metrics")).scalar()
    tkrs = session.execute(text("SELECT COUNT(DISTINCT ticker) FROM daily_risk_metrics")).scalar()
    logger.info("  daily_risk_metrics: %d rows, %d dates, %d tickers", count, dates, tkrs)

    session.close()


if __name__ == "__main__":
    main()
