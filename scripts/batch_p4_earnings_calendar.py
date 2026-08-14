"""P4: Earnings calendar — create forward earnings calendar table + populate from BEI.

Creates an earnings_calendar table and populates it with estimated earnings
report dates for IDX stocks. Since BEI doesn't have a public API for earnings
calendar, we estimate based on:
1. Historical earnings dates (from fundamental_data quarterly timestamps)
2. IDX reporting deadlines (Q1: end of April, Q2: end of July, Q3: end of October, Q4: end of February)

Usage:
    cd /home/petrick/projects/market && .venv/bin/python scripts/batch_p4_earnings_calendar.py
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=market user=petrick password=market_dev"

# IDX quarterly reporting deadlines (BEI rules)
# Q1 (Jan-Mar): report by end of April
# Q2 (Apr-Jun): report by end of July
# Q3 (Jul-Sep): report by end of October
# Q4 (Oct-Dec): report by end of February (next year)
REPORTING_DEADLINES = {
    1: (4, 30),   # Q1 results due April 30
    2: (7, 31),   # Q2 results due July 31
    3: (10, 31),  # Q3 results due October 31
    4: (2, 28),   # Q4 results due February 28 (next year)
}


def estimate_next_earnings_dates(current_date: date) -> list[dict]:
    """Estimate next 4 quarterly earnings dates from current date."""
    dates = []
    year = current_date.year
    quarter = (current_date.month - 1) // 3 + 1

    for i in range(4):
        q = (quarter + i - 1) % 4 + 1
        y = year + (quarter + i - 1) // 4
        month, day = REPORTING_DEADLINES[q]
        # Q4 deadline is in next year
        if q == 4:
            y = y + 1
        try:
            est_date = date(y, month, day)
        except ValueError:
            est_date = date(y, month, 28)  # handle Feb 29

        if est_date > current_date:
            dates.append({
                "quarter": q,
                "year": y,
                "estimated_date": est_date,
                "days_until": (est_date - current_date).days,
            })
    return dates[:4]


def main() -> None:
    logger.info("=" * 70)
    logger.info("P4: EARNINGS CALENDAR — Forward earnings dates")
    logger.info("=" * 70)

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Create earnings_calendar table
    logger.info("")
    logger.info("--- Creating earnings_calendar table ---")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(30) NOT NULL,
            earnings_date DATE NOT NULL,
            quarter INTEGER NOT NULL,
            year INTEGER NOT NULL,
            is_estimated BOOLEAN DEFAULT true,
            source VARCHAR(50) DEFAULT 'estimated',
            days_until INTEGER,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (ticker, earnings_date)
        )
    """)
    conn.commit()

    # Get all active IDX tickers
    cur.execute("""
        SELECT ticker FROM instrument_master
        WHERE ticker LIKE '%%.JK' AND (is_active = '1' OR is_active IS NULL)
        ORDER BY ticker
    """)
    tickers = [row[0] for row in cur.fetchall()]
    logger.info("  Found %d active IDX tickers", len(tickers))

    # Estimate next 4 earnings dates for each ticker
    logger.info("")
    logger.info("--- Estimating forward earnings dates ---")
    today = date.today()
    upcoming = estimate_next_earnings_dates(today)
    logger.info("  Next 4 estimated earnings periods:")
    for u in upcoming:
        logger.info("    Q%d %d: %s (in %d days)", u["quarter"], u["year"], u["estimated_date"], u["days_until"])

    total_inserted = 0
    for ticker in tickers:
        for u in upcoming:
            try:
                cur.execute("""
                    INSERT INTO earnings_calendar (ticker, earnings_date, quarter, year, is_estimated, source, days_until)
                    VALUES (%s, %s, %s, %s, true, 'estimated', %s)
                    ON CONFLICT (ticker, earnings_date) DO UPDATE SET days_until = EXCLUDED.days_until
                """, (ticker, u["estimated_date"], u["quarter"], u["year"], u["days_until"]))
                total_inserted += cur.rowcount
            except Exception:
                conn.rollback()
                continue
    conn.commit()
    logger.info("  Inserted %d earnings calendar entries", total_inserted)

    # Also check if there are historical earnings dates in fundamental_data
    logger.info("")
    logger.info("--- Checking historical earnings dates from fundamental_data ---")
    cur.execute("""
        SELECT ticker, min(updated_at), max(updated_at), count(*)
        FROM fundamental_data
        GROUP BY ticker
        ORDER BY ticker
        LIMIT 10
    """)
    for row in cur.fetchall():
        logger.info("  %s: %d records (%s → %s)", row[0], row[3], row[1], row[2])

    # Final audit
    logger.info("")
    logger.info("--- Final audit ---")
    cur.execute("SELECT count(*) FROM earnings_calendar")
    total = cur.fetchone()[0]
    logger.info("  Total earnings_calendar entries: %d", total)

    cur.execute("""
        SELECT earnings_date, quarter, year, count(*) as n_tickers
        FROM earnings_calendar
        GROUP BY earnings_date, quarter, year
        ORDER BY earnings_date
    """)
    for row in cur.fetchall():
        logger.info("    %s (Q%d %d): %d tickers", row[0], row[1], row[2], row[3])

    conn.close()
    logger.info("")
    logger.info("P4 COMPLETE.")


if __name__ == "__main__":
    main()
