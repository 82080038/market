"""Backfill historical news (2024-2026) from Google News RSS + Indonesian RSS feeds.

Uses dynamic rate limiting and multiple sources:
1. Google News RSS with date-range queries (saham, IHSG, ticker-specific)
2. CNBC Indonesia RSS (market, news, investment)
3. Tempo Bisnis RSS
4. Detik Finance RSS

Stores into both `news` and `news_sentiment` PostgreSQL tables.

Usage:
    python scripts/backfill_historical_news.py [--months-back 30]
"""
from __future__ import annotations

import argparse
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import psycopg2
import requests

from market.analysis.news_sentiment import NewsSentimentAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_analyzer = NewsSentimentAnalyzer()

PG_DSN = "postgresql://petrick:market_dev@localhost:5432/market"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Ticker keywords for extraction
TICKER_KEYWORDS = {
    "BBCA.JK": ["BCA", "BBCA"],
    "BBRI.JK": ["BRI", "BBRI"],
    "UNVR.JK": ["Unilever", "UNVR"],
    "ANTM.JK": ["Antam", "ANTM"],
    "TLKM.JK": ["Telkom", "TLKM"],
    "MDKA.JK": ["Merdeka", "MDKA"],
    "UNTR.JK": ["United Tractors", "UNTR"],
    "ASII.JK": ["Astra", "ASII"],
    "BMRI.JK": ["Mandiri", "BMRI"],
    "BBNI.JK": ["BNI", "BBNI"],
    "GOTO.JK": ["GoTo", "GOTO"],
    "ICBP.JK": ["Indofood", "ICBP"],
    "INDF.JK": ["Indofood", "INDF"],
    "KLBF.JK": ["Kalbe", "KLBF"],
    "ASRI.JK": ["Alam Sutera", "ASRI"],
    "CPIN.JK": ["Charoen", "CPIN"],
    "EXCL.JK": ["XL Axiata", "EXCL"],
    "ISAT.JK": ["Indosat", "ISAT"],
    "PGAS.JK": ["PGN", "PGAS"],
    "SMGR.JK": ["Semen Indonesia", "SMGR"],
    # Global tickers/indices that affect IDX via correlation
    "^GSPC": ["S&P 500", "SPX", "S&P500"],
    "^HSI": ["Hang Seng", "HSI"],
    "^N225": ["Nikkei", "N225"],
    "^VIX": ["VIX", "fear index"],
    "CL=F": ["crude oil", "WTI", "oil price", "Brent"],
    "GC=F": ["gold price", "gold futures", "XAU"],
    "CPO=F": ["palm oil", "CPO price", "crude palm oil"],
    "HG=F": ["copper price", "copper futures"],
    "DX-Y.NYB": ["dollar index", "DXY", "USD index"],
    "IDR=X": ["rupiah", "USD IDR", "IDR USD"],
}


class DynamicRateLimiter:
    """Adaptive rate limiter: increases delay on errors, decreases on success."""

    def __init__(self, base_delay: float = 3.0, max_delay: float = 30.0, min_delay: float = 1.0):
        self.delay = base_delay
        self.max_delay = max_delay
        self.min_delay = min_delay
        self.consecutive_errors = 0
        self.consecutive_success = 0

    def wait(self):
        time.sleep(self.delay)

    def on_success(self):
        self.consecutive_errors = 0
        self.consecutive_success += 1
        if self.consecutive_success >= 3 and self.delay > self.min_delay:
            self.delay = max(self.min_delay, self.delay * 0.8)
            self.consecutive_success = 0
            logger.debug("Rate limiter: decreased to %.1fs", self.delay)

    def on_error(self, status_code: int | None = None):
        self.consecutive_success = 0
        self.consecutive_errors += 1
        multiplier = 1.5 if status_code and status_code == 429 else 2.0
        self.delay = min(self.max_delay, self.delay * multiplier)
        logger.warning("Rate limiter: increased to %.1fs (errors=%d)", self.delay, self.consecutive_errors)


def extract_ticker(text: str) -> str | None:
    """Extract first matching ticker from text."""
    text_upper = text.upper()
    for ticker, keywords in TICKER_KEYWORDS.items():
        for kw in keywords:
            if kw.upper() in text_upper:
                return ticker
    return None


def parse_date(date_str: str) -> str:
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_google_news_rss(query: str, when: str, rate_limiter: DynamicRateLimiter) -> list[dict]:
    """Fetch Google News RSS with query and date range."""
    url = f"https://news.google.com/rss/search?q={query}+when:{when}&hl=id&gl=ID&ceid=ID:id"
    articles = []
    try:
        rate_limiter.wait()
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            rate_limiter.on_success()
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "") or ""
                pub_date = item.findtext("pubDate", "") or ""
                source = item.findtext("source", "") or ""
                link = item.findtext("link", "") or ""
                # Clean title (remove " - Source" suffix)
                title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()
                articles.append({
                    "headline": title[:500],
                    "date": parse_date(pub_date),
                    "source": source or "google_news",
                    "url": link,
                })
        else:
            rate_limiter.on_error(resp.status_code)
            logger.warning("Google News RSS %s: HTTP %d", query, resp.status_code)
    except Exception as e:
        rate_limiter.on_error()
        logger.error("Google News RSS %s: %s", query, e)
    return articles


def fetch_rss_feed(url: str, source_name: str, rate_limiter: DynamicRateLimiter) -> list[dict]:
    """Fetch a standard RSS feed."""
    articles = []
    try:
        rate_limiter.wait()
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            rate_limiter.on_success()
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "") or ""
                pub_date = item.findtext("pubDate", "") or ""
                link = item.findtext("link", "") or ""
                articles.append({
                    "headline": title[:500],
                    "date": parse_date(pub_date),
                    "source": source_name,
                    "url": link,
                })
        else:
            rate_limiter.on_error(resp.status_code)
            logger.warning("RSS %s: HTTP %d", source_name, resp.status_code)
    except Exception as e:
        rate_limiter.on_error()
        logger.error("RSS %s: %s", source_name, e)
    return articles


def compute_sentiment(headline: str) -> tuple[float, str, float]:
    """Compute sentiment score, label, relevance."""
    result = _analyzer.analyze_text(headline)
    return result.score, result.label, result.relevance


def insert_articles(pg_conn, articles: list[dict]) -> tuple[int, int]:
    """Insert articles into news + news_sentiment, skip duplicates."""
    cur = pg_conn.cursor()

    # Load existing headlines for dedup
    cur.execute("SELECT headline FROM news")
    existing_news = {row[0] for row in cur.fetchall()}
    cur.execute("SELECT headline FROM news_sentiment")
    existing_ns = {row[0] for row in cur.fetchall()}

    # Get max IDs
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM news")
    news_id = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM news_sentiment")
    ns_id = cur.fetchone()[0]

    news_inserted = 0
    ns_inserted = 0

    for a in articles:
        headline = a["headline"]
        if not headline or headline in existing_news:
            continue

        ticker = extract_ticker(headline)
        score, label, relevance = compute_sentiment(headline)

        # Insert into news
        news_id += 1
        try:
            cur.execute("""
                INSERT INTO news (id, news_id, headline, body, published_at, source, entities, topic, sentiment, impact)
                VALUES (%s, %s, %s, NULL, %s, %s, %s, '', %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                news_id,
                a["url"] or f"google_news/{hash(headline)}",
                headline,
                a["date"],
                a["source"],
                ticker,
                "1" if score > 0.3 else "-1" if score < -0.3 else "0",
                "high" if relevance > 0.7 else "medium" if relevance > 0.3 else "low",
            ))
            if cur.rowcount > 0:
                news_inserted += 1
                existing_news.add(headline)
        except Exception:
            pass

        # Insert into news_sentiment
        if headline not in existing_ns:
            ns_id += 1
            try:
                cur.execute("""
                    INSERT INTO news_sentiment (id, ticker, date, headline, sentiment_score, sentiment_label, relevance_score, source, url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    ns_id,
                    ticker,
                    a["date"],
                    headline,
                    score,
                    label,
                    relevance,
                    a["source"],
                    a.get("url"),
                ))
                if cur.rowcount > 0:
                    ns_inserted += 1
                    existing_ns.add(headline)
            except Exception:
                pass

    pg_conn.commit()
    cur.close()
    return news_inserted, ns_inserted


def main():
    parser = argparse.ArgumentParser(description="Backfill historical news 2024-2026")
    parser.add_argument("--months-back", type=int, default=30, help="How many months back to fetch")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("HISTORICAL NEWS BACKFILL")
    logger.info("  Months back: %d", args.months_back)
    logger.info("=" * 60)

    rate_limiter = DynamicRateLimiter(base_delay=3.0, max_delay=30.0, min_delay=1.0)

    all_articles: list[dict] = []
    seen_headlines: set[str] = set()

    # ── Source 1: Google News RSS — Indonesian market news ──
    google_queries_id = [
        "saham+IHSG+bursa+efek+indonesia",
        "BBCA+BCA+saham+saham",
        "BBRI+BRI+saham+bank",
        "TLKM+Telkom+saham",
        "ANTM+Antam+emas+saham",
        "Astra+ASII+saham+indonesia",
        "saham+indonesia+corporate+action",
        "IHSG+indeks+pasar+modal",
        "saham+blue+chip+indonesia",
        "bursa+efek+indonesia+IPO",
    ]

    # ── Source 1b: Google News RSS — Global market news (affects IDX via correlation) ──
    google_queries_global = [
        "Fed+rate+decision+market+impact",
        "US+inflation+CPI+stock+market",
        "China+economy+stock+market+asia",
        "oil+price+crude+OPEC+market",
        "gold+price+commodity+market",
        "geopolitics+war+stock+market",
        "global+market+selloff+risk+off",
        "emerging+market+asia+stocks+flow",
        "US+China+trade+war+tariff",
        "recession+2025+2026+global+economy",
        "Bank+Indonesia+rate+bi+rate",
        "rupiah+USD+IDR+currency",
        "palm+oil+CPO+price+indonesia",
        "coal+price+indonesia+mining",
        "nickel+price+indonesia+mining",
        "Asian+stocks+market+nikkei+hang+seng",
        "foreign+investor+indonesia+stock+flow",
        "MSCI+emerging+market+rebalance",
        "US+treasury+yield+bond+market",
        "dollar+index+DXY+emerging+market",
    ]

    # Google News supports: 1d, 7d, 1m, 3m, 6m, 1y, 2y, 3y
    when_ranges = ["3m", "6m", "1y", "2y"]

    for when in when_ranges:
        for q in google_queries_id + google_queries_global:
            articles = fetch_google_news_rss(q, when, rate_limiter)
            new_count = 0
            for a in articles:
                if a["headline"] not in seen_headlines:
                    seen_headlines.add(a["headline"])
                    all_articles.append(a)
                    new_count += 1
            if new_count > 0:
                logger.info("  Google News [%s, %s]: %d new articles", q[:40], when, new_count)

    logger.info("Google News total: %d unique articles", len(all_articles))

    # ── Source 2: Indonesian RSS feeds (current snapshots) ──
    rss_feeds_id = [
        ("https://www.cnbcindonesia.com/market/rss", "CNBC Indonesia Market"),
        ("https://www.cnbcindonesia.com/news/rss", "CNBC Indonesia News"),
        ("https://rss.tempo.co/bisnis", "Tempo Bisnis"),
        ("https://finance.detik.com/rss", "Detik Finance"),
    ]

    # ── Source 2b: Global financial RSS feeds ──
    rss_feeds_global = [
        ("https://feeds.content.dowjones.io/public/rss/SB10001424053111904210904581603062331608980", "WSJ Markets"),
        ("https://feeds.content.dowjones.io/public/rss/mw_topstories", "MarketWatch"),
        ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC US Markets"),
        ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC Economy"),
        ("https://www.cnbc.com/id/100727362/device/rss/rss.html", "CNBC Asia Markets"),
        ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "NYT Business"),
        ("https://feeds.bbci.co.uk/news/business/rss.xml", "BBC Business"),
        ("https://www.investing.com/rss/news_1.rss", "Investing.com Market News"),
        ("https://www.investing.com/rss/news_25.rss", "Investing.com Economy"),
        ("https://www.investing.com/rss/news_95.rss", "Investing.com Commodities"),
    ]

    rss_feeds = rss_feeds_id + rss_feeds_global

    for url, name in rss_feeds:
        articles = fetch_rss_feed(url, name, rate_limiter)
        new_count = 0
        for a in articles:
            if a["headline"] not in seen_headlines:
                seen_headlines.add(a["headline"])
                all_articles.append(a)
                new_count += 1
        if new_count > 0:
            logger.info("  RSS [%s]: %d new articles", name, new_count)

    logger.info("Total unique articles: %d", len(all_articles))

    # ── Filter by date range ──
    cutoff_start = (datetime.now(timezone.utc) - timedelta(days=args.months_back * 30)).date()
    filtered = [a for a in all_articles if a["date"] >= cutoff_start.isoformat()]
    logger.info("After date filter (>= %s): %d articles", cutoff_start, len(filtered))

    # ── Insert into PostgreSQL ──
    if not filtered:
        logger.info("No articles to insert — exiting")
        return

    pg_conn = psycopg2.connect(PG_DSN)
    pg_conn.autocommit = False
    news_inserted, ns_inserted = insert_articles(pg_conn, filtered)
    pg_conn.close()

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("  Total fetched: %d", len(all_articles))
    logger.info("  Date-filtered: %d", len(filtered))
    logger.info("  news table: +%d rows", news_inserted)
    logger.info("  news_sentiment table: +%d rows", ns_inserted)

    # Verify
    pg_conn = psycopg2.connect(PG_DSN)
    cur = pg_conn.cursor()
    cur.execute("SELECT MIN(published_at), MAX(published_at), COUNT(*) FROM news")
    row = cur.fetchone()
    logger.info("  news table now: %s to %s, %d rows", row[0], row[1], row[2])
    cur.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM news_sentiment")
    row = cur.fetchone()
    logger.info("  news_sentiment now: %s to %s, %d rows", row[0], row[1], row[2])
    cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
