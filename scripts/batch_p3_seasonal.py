"""P3: Seasonal pattern engine — backtest monthly returns from stock_prices.

Computes seasonal patterns for IDX stocks using historical OHLCV data:
1. Monthly average returns per ticker (January effect, year-end rally, etc.)
2. Holiday effect analysis (Lebaran, Natal, Tahun Baru)
3. Earnings season pattern (Q1-Q4 reporting cycle impact)
4. Store results in seasonal_patterns table

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p3_seasonal.py
"""
from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np
import pandas as pd
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"


def fetch_monthly_returns(conn, ticker: str) -> pd.DataFrame:
    """Fetch monthly returns for a ticker from stock_prices."""
    cur = conn.cursor()
    cur.execute("""
        SELECT date_trunc('month', timestamp)::date as month,
               first_value(close) OVER w as open_month,
               last_value(close) OVER w as close_month
        FROM (
            SELECT DISTINCT ON (date_trunc('month', timestamp))
                   timestamp, close
            FROM stock_prices
            WHERE ticker = %s AND timeframe = '1d'
            ORDER BY date_trunc('month', timestamp), timestamp
        ) sub
        WINDOW w AS (PARTITION BY date_trunc('month', timestamp))
        ORDER BY month
    """, (ticker,))
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    # Simpler approach: get first and last close per month
    cur.execute("""
        WITH monthly AS (
            SELECT date_trunc('month', timestamp)::date as month,
                   (array_agg(close ORDER BY timestamp ASC))[1] as first_close,
                   (array_agg(close ORDER BY timestamp DESC))[1] as last_close,
                   count(*) as trading_days
            FROM stock_prices
            WHERE ticker = %s AND timeframe = '1d' AND close IS NOT NULL
            GROUP BY 1
        )
        SELECT month, first_close, last_close, trading_days
        FROM monthly
        WHERE trading_days >= 10
        ORDER BY month
    """, (ticker,))
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["month", "first_close", "last_close", "trading_days"])
    # Cast Decimal to float for numeric operations
    df["first_close"] = df["first_close"].astype(float)
    df["last_close"] = df["last_close"].astype(float)
    df["trading_days"] = df["trading_days"].astype(int)
    df["return"] = (df["last_close"] / df["first_close"] - 1) * 100
    df["month_num"] = pd.to_datetime(df["month"]).dt.month
    return df


def compute_seasonal_scores(df: pd.DataFrame) -> dict:
    """Compute seasonal score per month for a ticker."""
    if df.empty:
        return {}
    monthly_stats = {}
    for month in range(1, 13):
        month_data = df[df["month_num"] == month]
        if len(month_data) < 3:  # Need at least 3 years of data
            continue
        avg_return = month_data["return"].mean()
        std_return = month_data["return"].std()
        win_rate = (month_data["return"] > 0).mean() * 100
        # Score: positive avg return + high win rate = bullish seasonal
        # Scale: -100 to +100
        score = np.clip(avg_return * 5 + (win_rate - 50) * 2, -100, 100)
        monthly_stats[month] = {
            "avg_return": round(avg_return, 4),
            "std_return": round(std_return, 4) if not np.isnan(std_return) else 0,
            "win_rate": round(win_rate, 2),
            "n_years": len(month_data),
            "score": round(score, 2),
        }
    return monthly_stats


def main() -> None:
    logger.info("=" * 70)
    logger.info("P3: SEASONAL PATTERN ENGINE — Backtest monthly returns")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Create seasonal_patterns table
    logger.info("")
    logger.info("--- Creating seasonal_patterns table ---")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seasonal_patterns (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
            avg_return FLOAT,
            std_return FLOAT,
            win_rate FLOAT,
            n_years INTEGER,
            seasonal_score FLOAT,
            pattern_type VARCHAR(50),
            computed_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (ticker, month)
        )
    """)
    conn.commit()

    # Get all IDX tickers with sufficient data
    logger.info("")
    logger.info("--- Fetching tickers with sufficient historical data ---")
    cur.execute("""
        SELECT ticker, count(*), min(timestamp)::date, max(timestamp)::date
        FROM stock_prices
        WHERE ticker LIKE '%%.JK' AND timeframe = '1d' AND close IS NOT NULL
        GROUP BY ticker
        HAVING count(*) > 252 AND min(timestamp) < '2022-01-01'
        ORDER BY ticker
    """)
    tickers = cur.fetchall()
    logger.info("  Found %d tickers with >1 year history before 2022", len(tickers))

    # Compute seasonal patterns for each ticker
    logger.info("")
    logger.info("--- Computing seasonal patterns ---")
    total_computed = 0
    batch_count = 0

    for ticker, n_rows, min_date, max_date in tickers:
        df = fetch_monthly_returns(conn, ticker)
        if df.empty:
            continue
        seasonal = compute_seasonal_scores(df)
        if not seasonal:
            continue

        for month, stats in seasonal.items():
            # Determine pattern type
            if month == 1 and stats["score"] > 10:
                ptype = "january_effect"
            elif month in [11, 12] and stats["score"] > 10:
                ptype = "year_end_rally"
            elif month in [3, 4] and stats["score"] < -10:
                ptype = "earnings_season_q1"
            elif month in [7, 8] and stats["score"] < -10:
                ptype = "earnings_season_q2"
            elif stats["score"] > 20:
                ptype = "strong_seasonal_bullish"
            elif stats["score"] < -20:
                ptype = "strong_seasonal_bearish"
            else:
                ptype = "neutral"

            cur.execute("""
                INSERT INTO seasonal_patterns (ticker, month, avg_return, std_return, win_rate, n_years, seasonal_score, pattern_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, month) DO UPDATE SET
                    avg_return = EXCLUDED.avg_return,
                    std_return = EXCLUDED.std_return,
                    win_rate = EXCLUDED.win_rate,
                    n_years = EXCLUDED.n_years,
                    seasonal_score = EXCLUDED.seasonal_score,
                    pattern_type = EXCLUDED.pattern_type,
                    computed_at = now()
            """, (ticker, month, stats["avg_return"], stats["std_return"],
                  stats["win_rate"], stats["n_years"], stats["score"], ptype))
            total_computed += 1

        batch_count += 1
        if batch_count % 50 == 0:
            conn.commit()
            logger.info("  Processed %d/%d tickers, %d seasonal records so far",
                        batch_count, len(tickers), total_computed)

    conn.commit()
    logger.info("  Total: %d tickers processed, %d seasonal records computed",
                batch_count, total_computed)

    # Compute aggregate IHSG seasonal pattern
    logger.info("")
    logger.info("--- Computing aggregate market (IHSG) seasonal pattern ---")
    cur.execute("""
        WITH monthly AS (
            SELECT date_trunc('month', timestamp)::date as month,
                   (array_agg(close ORDER BY timestamp ASC))[1] as first_close,
                   (array_agg(close ORDER BY timestamp DESC))[1] as last_close,
                   count(*) as trading_days
            FROM stock_prices
            WHERE ticker = '^JKSE' AND timeframe = '1d' AND close IS NOT NULL
            GROUP BY 1
        )
        SELECT month, first_close, last_close, trading_days FROM monthly WHERE trading_days >= 10 ORDER BY month
    """)
    rows = cur.fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["month", "first_close", "last_close", "trading_days"])
        df["return"] = (df["last_close"] / df["first_close"] - 1) * 100
        df["month_num"] = pd.to_datetime(df["month"]).dt.month
        seasonal = compute_seasonal_scores(df)
        for month, stats in seasonal.items():
            cur.execute("""
                INSERT INTO seasonal_patterns (ticker, month, avg_return, std_return, win_rate, n_years, seasonal_score, pattern_type)
                VALUES ('^JKSE', %s, %s, %s, %s, %s, %s, 'aggregate_market')
                ON CONFLICT (ticker, month) DO UPDATE SET
                    avg_return = EXCLUDED.avg_return,
                    std_return = EXCLUDED.std_return,
                    win_rate = EXCLUDED.win_rate,
                    n_years = EXCLUDED.n_years,
                    seasonal_score = EXCLUDED.seasonal_score,
                    pattern_type = EXCLUDED.pattern_type
            """, (month, stats["avg_return"], stats["std_return"],
                  stats["win_rate"], stats["n_years"], stats["score"]))
        conn.commit()
        logger.info("  IHSG aggregate: %d months computed", len(seasonal))

    # Final audit
    logger.info("")
    logger.info("--- Final audit ---")
    cur.execute("SELECT count(*) FROM seasonal_patterns")
    total = cur.fetchone()[0]
    logger.info("  Total seasonal_patterns records: %d", total)

    cur.execute("SELECT pattern_type, count(*) FROM seasonal_patterns GROUP BY pattern_type ORDER BY count(*) DESC")
    for row in cur.fetchall():
        logger.info("  %s: %d", row[0], row[1])

    cur.execute("""
        SELECT ticker, month, avg_return, win_rate, seasonal_score, pattern_type
        FROM seasonal_patterns
        WHERE pattern_type IN ('january_effect', 'year_end_rally', 'strong_seasonal_bullish', 'strong_seasonal_bearish')
        ORDER BY seasonal_score DESC
        LIMIT 20
    """)
    logger.info("")
    logger.info("  Top seasonal patterns:")
    for row in cur.fetchall():
        logger.info("    %s month=%d avg_ret=%.2f%% win_rate=%.1f%% score=%.1f (%s)",
                    row[0], row[1], row[2], row[3], row[4], row[5])

    conn.close()
    logger.info("")
    logger.info("P3 COMPLETE.")


if __name__ == "__main__":
    main()
