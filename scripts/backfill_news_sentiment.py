"""Backfill news sentiment from SQLite news table → PostgreSQL news_sentiment.

Reads news articles from SQLite (110 rows) and computes keyword-based
sentiment (EN+ID lexicon). Stores into PostgreSQL news_sentiment table.

Usage:
    uv run python scripts/backfill_news_sentiment.py
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime

import psycopg2

from market.analysis.news_sentiment import NewsSentimentAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_analyzer = NewsSentimentAnalyzer()

SQLITE_PATH = "/home/petrick/projects/market/data/market_research.db"
PG_DSN = "postgresql://petrick:market_dev@localhost:5432/market"


def compute_sentiment(title: str, body: str | None = None) -> tuple[float, str]:
    """Compute sentiment using unified NewsSentimentAnalyzer."""
    result = _analyzer.analyze_text(title, body)
    return result.score, result.label


def parse_date(date_str: str) -> str:
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(date_str).strftime("%Y-%m-%d")
    except ValueError:
        pass
    return datetime.now().strftime("%Y-%m-%d")


def extract_first_ticker(entities: str) -> str | None:
    if not entities:
        return None
    tickers = [t.strip() for t in entities.split(",") if t.strip()]
    return tickers[0] if tickers else None


def main():
    logger.info("News Sentiment Backfill (SQLite → PostgreSQL)")
    logger.info("=" * 50)

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute("""
        SELECT id, headline, body, published_at, source, entities, sentiment, impact
        FROM news ORDER BY published_at DESC
    """).fetchall()
    logger.info("SQLite news: %d articles", len(rows))

    if not rows:
        logger.info("No news to process — exiting")
        sqlite_conn.close()
        return

    pg_conn = psycopg2.connect(PG_DSN)
    pg_conn.autocommit = False
    cur = pg_conn.cursor()

    cur.execute("SELECT COUNT(*) FROM news_sentiment")
    existing = cur.fetchone()[0]
    logger.info("PostgreSQL news_sentiment: %d existing rows", existing)

    inserted = 0
    errors = 0

    for row in rows:
        try:
            score, label = compute_sentiment(row["headline"], row["body"])
            ticker = extract_first_ticker(row["entities"])
            pub_date = parse_date(row["published_at"])

            cur.execute("""
                INSERT INTO news_sentiment (
                    ticker, date, headline, sentiment_score,
                    sentiment_label, relevance_score, source
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT DO NOTHING
            """, (
                ticker,
                pub_date,
                row["headline"][:500] if row["headline"] else None,
                score,
                label,
                abs(score),
                row["source"] or "sqlite_news",
            ))
            inserted += 1
        except Exception as e:
            errors += 1
            logger.debug("Skip news id=%s: %s", row["id"], e)

    pg_conn.commit()

    logger.info("\n" + "=" * 50)
    logger.info("NEWS SENTIMENT BACKFILL COMPLETE")
    logger.info("  Inserted: %d, Errors: %d", inserted, errors)

    cur.execute("""
        SELECT sentiment_label, COUNT(*), AVG(sentiment_score)
        FROM news_sentiment GROUP BY sentiment_label ORDER BY sentiment_label
    """)
    logger.info("  Sentiment distribution:")
    for r in cur.fetchall():
        logger.info("    %s: %d articles (avg score: %.3f)", r[0], r[1], r[2] or 0)
    cur.execute("SELECT COUNT(*) FROM news_sentiment")
    total = cur.fetchone()[0]
    logger.info("  TOTAL: %d rows", total)

    cur.close()
    pg_conn.close()
    sqlite_conn.close()


if __name__ == "__main__":
    main()
