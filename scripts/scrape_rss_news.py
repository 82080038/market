"""RSS news scraper → PostgreSQL news_sentiment (non-blocking, rate-limited).

Scrapes multiple Indonesian financial RSS feeds, computes keyword-based
sentiment (EN+ID lexicon), and stores into PostgreSQL news_sentiment table.

Uses DynamicRateLimiter for adaptive backoff per domain.
Designed to run as a periodic background task (daily cron).

Usage:
    uv run python scripts/scrape_rss_news.py
    uv run python scripts/scrape_rss_news.py --days 7
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime, timezone

import psycopg2
import requests

# Use unified NewsSentimentAnalyzer
from market.analysis.news_sentiment import NewsSentimentAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_analyzer = NewsSentimentAnalyzer()

PG_DSN = "postgresql://petrick:market_dev@localhost:5432/market"

# Indonesian financial RSS feeds (from pustaka/30-sentiment-analysis-alternative-data.md)
RSS_FEEDS = [
    ("CNBC Market", "https://www.cnbcindonesia.com/market/rss"),
    ("CNBC News", "https://www.cnbcindonesia.com/news/rss"),
    ("CNBC Investment", "https://www.cnbcindonesia.com/investment/rss"),
    ("Tempo Bisnis", "https://rss.tempo.co/bisnis"),
    ("Kontan Market", "https://www.kontan.co.id/rss/market"),
    ("Kontan Finance", "https://www.kontan.co.id/rss/finance"),
    ("Bisnis.com Market", "https://www.bisnis.com/rss?category=market"),
    ("Detik Finance", "https://finance.detik.com/rss"),
]

# Rate limiter settings
DEFAULT_INTERVAL = 3.0
MIN_INTERVAL = 1.0
MAX_INTERVAL = 60.0
BACKOFF_FACTOR = 2.0
SPEEDUP_FACTOR = 0.85
REQUEST_TIMEOUT = 20


class AdaptiveRateLimiter:
    """Per-domain adaptive rate limiter."""

    def __init__(self):
        self._intervals: dict[str, float] = {}
        self._last_request: dict[str, float] = {}
        self._errors: dict[str, int] = {}

    def wait(self, domain: str):
        interval = self._intervals.get(domain, DEFAULT_INTERVAL)
        last = self._last_request.get(domain)
        now = time.monotonic()
        if last is not None:
            elapsed = now - last
            if elapsed < interval:
                time.sleep(interval - elapsed)
        self._last_request[domain] = time.monotonic()

    def record_success(self, domain: str):
        self._errors[domain] = 0
        current = self._intervals.get(domain, DEFAULT_INTERVAL)
        self._intervals[domain] = max(MIN_INTERVAL, current * SPEEDUP_FACTOR)

    def record_error(self, domain: str):
        errors = self._errors.get(domain, 0) + 1
        self._errors[domain] = errors
        current = self._intervals.get(domain, DEFAULT_INTERVAL)
        self._intervals[domain] = min(MAX_INTERVAL, current * BACKOFF_FACTOR)
        logger.warning("Backoff %s: interval=%.1fs, errors=%d", domain, self._intervals[domain], errors)


def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse
    try:
        host = urlparse(url).hostname or "unknown"
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return "unknown"


# Sentiment lexicon (EN+ID)
POSITIVE_WORDS = {
    "naik", "unggul", "untung", "laba", "pertumbuhan", "positif", "optimis",
    "beli", "akumulasi", "rally", "bullish", "kenaikan", "melonjak", "menguat",
    "surplus", "dividen", "buyback", "ekspansi", "peningkatan", "rekomen",
    "rekomendasi", "overweight", "target", "upgrade", "potensi", "peluang",
    "mendukung", "memperkuat", "memperluas", "meraih", "mencapai",
    "tembus", "rekor", "tinggi", "bangkit", "pulih", "tumbuh",
    "inovasi", "transformatif", "strategis", "investasi", "capex",
    "surge", "soar", "rally", "gain", "profit", "growth", "positive",
    "buy", "accumulate", "upgrade", "outperform", "strong",
    "beat", "exceed", "record", "high", "opportunity", "expansion",
    "dividend", "buyback", "breakthrough", "innovation",
}

NEGATIVE_WORDS = {
    "turun", "rugi", "kerugian", "negatif", "pesimis", "jual", "distribusi",
    "bearish", "penurunan", "anjlok", "melemah", "defisit", "merosot",
    "gagal", "terhenti", "suspensi", "delisting", "pailit", "default",
    "downgrade", "underperform", "risiko", "ancaman", "tekanan",
    "korupsi", "skandal", "pelanggaran", "sanksi", "denda", "gugatan",
    "pembekuan", "perampasan", "terjun", "jatuh", "krisis",
    "konsolidasi", "pelemahan", "tertekan", "memble", "stagnan",
    "plunge", "crash", "drop", "fall", "loss", "negative", "bearish",
    "sell", "distribution", "downgrade", "underperform", "weak", "miss",
    "suspend", "delist", "bankrupt", "default", "scandal", "fraud",
    "corruption", "penalty", "lawsuit", "risk", "threat", "pressure",
    "crisis", "stagnant", "decline", "slump",
}


def compute_sentiment(title: str, body: str | None = None) -> tuple[float, str]:
    """Compute sentiment using unified NewsSentimentAnalyzer."""
    result = _analyzer.analyze_text(title, body)
    return result.score, result.label


def extract_tickers(text: str) -> list[str]:
    """Extract IDX ticker mentions from text."""
    tickers = re.findall(r"\b([A-Z]{3,5})\.JK\b", text)
    if not tickers:
        # Match 4-letter all-caps words (common IDX pattern)
        tickers = re.findall(r"\b([A-Z]{4})\b", text)
    return list(set(tickers))


def parse_rss_date(date_str: str) -> str:
    """Parse RSS date format to YYYY-MM-DD."""
    if not date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(date_str).strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.sub(r"<[^>]+>", "", text or "")
    clean = re.sub(r"&[a-z]+;", " ", clean)
    return clean.strip()


def fetch_rss_feed(url: str, feed_name: str, limiter: AdaptiveRateLimiter) -> list[dict]:
    """Fetch and parse an RSS feed. Returns list of article dicts."""
    domain = _domain_from_url(url)
    limiter.wait(domain)

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        limiter.record_error(domain)
        logger.warning("[%s] Request failed: %s", feed_name, e)
        return []

    if resp.status_code == 429:
        limiter.record_error(domain)
        logger.warning("[%s] HTTP 429 — backing off", feed_name)
        return []
    if resp.status_code >= 400:
        limiter.record_error(domain)
        logger.warning("[%s] HTTP %d", feed_name, resp.status_code)
        return []

    limiter.record_success(domain)

    # Parse XML
    try:
        from xml.etree import ElementTree as ET
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning("[%s] XML parse error: %s", feed_name, e)
        return []

    articles = []

    # RSS 2.0 format: channel/item
    items = root.findall(".//item")
    for item in items:
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        pub_date = item.findtext("pubDate", default="")
        description = item.findtext("description", default="")

        # Clean HTML from description
        body = strip_html(description)

        # Try to get content:encoded (some feeds)
        content = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", default="")
        if content:
            body = strip_html(content)

        if not title:
            continue

        articles.append({
            "headline": title.strip(),
            "body": body[:2000] if body else None,
            "url": link.strip(),
            "published_at": pub_date.strip(),
            "source": url,
        })

    return articles


def main():
    parser = argparse.ArgumentParser(description="Scrape RSS news → news_sentiment")
    parser.add_argument("--days", type=int, default=30, help="Only keep articles from last N days")
    args = parser.parse_args()

    logger.info("RSS News Scraper → news_sentiment")
    logger.info("  Feeds: %d", len(RSS_FEEDS))
    logger.info("  Days filter: %d", args.days)
    logger.info("=" * 60)

    limiter = AdaptiveRateLimiter()
    all_articles = []

    for feed_name, url in RSS_FEEDS:
        logger.info("[%s] Fetching %s", feed_name, url)
        articles = fetch_rss_feed(url, feed_name, limiter)
        logger.info("[%s] Got %d articles", feed_name, len(articles))
        all_articles.extend(articles)

    logger.info("\nTotal articles fetched: %d", len(all_articles))

    if not all_articles:
        logger.error("No articles fetched — exiting")
        return

    # Filter by date
    cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from datetime import timedelta
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=args.days)

    filtered = []
    for a in all_articles:
        pub_date = parse_rss_date(a["published_at"])
        try:
            dt = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dt >= cutoff_dt:
                a["parsed_date"] = pub_date
                filtered.append(a)
        except ValueError:
            a["parsed_date"] = pub_date
            filtered.append(a)

    logger.info("After date filter (last %d days): %d articles", args.days, len(filtered))

    # Insert to PostgreSQL
    pg_conn = psycopg2.connect(PG_DSN)
    pg_conn.autocommit = False
    cur = pg_conn.cursor()

    # Check existing headlines+dates to avoid duplicates
    existing_keys = set()
    cur.execute("SELECT headline, date FROM news_sentiment")
    for row in cur.fetchall():
        existing_keys.add((row[0], str(row[1])))

    inserted = 0
    skipped = 0
    errors = 0

    for a in filtered:
        headline = a["headline"][:500]
        pub_date = a["parsed_date"]
        dedup_key = (headline, pub_date)

        if dedup_key in existing_keys:
            skipped += 1
            continue

        try:
            result = _analyzer.analyze_text(a["headline"], a["body"])
            tickers = extract_tickers(a["headline"] + " " + (a["body"] or ""))
            ticker = tickers[0] if tickers else None

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
                headline,
                result.score,
                result.label,
                result.relevance,
                a["source"],
            ))
            inserted += 1
            existing_keys.add(dedup_key)
        except Exception as e:
            errors += 1
            logger.debug("Skip article: %s", e)

    pg_conn.commit()

    logger.info("\n" + "=" * 60)
    logger.info("RSS SCRAPE COMPLETE")
    logger.info("  Fetched: %d, Filtered: %d, Inserted: %d, Skipped (dup): %d, Errors: %d",
                len(all_articles), len(filtered), inserted, skipped, errors)

    # Verify
    cur.execute("""
        SELECT sentiment_label, COUNT(*), AVG(sentiment_score)
        FROM news_sentiment GROUP BY sentiment_label ORDER BY sentiment_label
    """)
    logger.info("  Sentiment distribution:")
    for r in cur.fetchall():
        logger.info("    %s: %d articles (avg: %.3f)", r[0], r[1], r[2] or 0)
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM news_sentiment")
    total = cur.fetchone()
    logger.info("  TOTAL: %d rows, %d tickers", total[0], total[1])

    cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
