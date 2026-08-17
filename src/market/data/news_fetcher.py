"""News sentiment fetcher — RSS feeds from Indonesian financial portals.

Fetches news from 10+ Indonesian financial RSS feeds, extracts stock tickers,
runs sentiment analysis (lexicon-based + optional IndoBERT), and stores to
news_sentiment table.

RSS Sources:
    - CNBC Indonesia, Kontan, Bisnis Indonesia, Detik Finance, Kompas Money,
      Tempo Bisnis, Liputan6 Bisnis, Okezone Finance, Sindonews Ekonomi,
      Republika Ekonomi

Usage:
    from market.data.news_fetcher import NewsFetcher
    fetcher = NewsFetcher()
    count = fetcher.fetch_and_store()
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from market.db.engine import get_sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Indonesian financial RSS feeds
RSS_FEEDS: list[dict[str, str]] = [
    {"name": "CNBC Indonesia", "url": "https://www.cnbcindonesia.com/market/rss"},
    {"name": "CNBC Investment", "url": "https://www.cnbcindonesia.com/investment/rss"},
    {"name": "Kontan Investasi", "url": "https://www.kontan.co.id/rss/investasi"},
    {"name": "Kontan Market", "url": "https://www.kontan.co.id/rss/market"},
    {"name": "Bisnis Finansial", "url": "https://finansial.bisnis.com/rss"},
    {"name": "Detik Finance", "url": "https://finance.detik.com/rss"},
    {"name": "Kompas Money", "url": "https://money.kompas.com/rss"},
    {"name": "Tempo Bisnis", "url": "https://bisnis.tempo.co/rss"},
    {"name": "Liputan6 Bisnis", "url": "https://www.liputan6.com/bisnis/rss"},
    {"name": "Okezone Economy", "url": "https://economy.okezone.com/rss"},
]

# Indonesian financial sentiment lexicon (simplified)
POSITIVE_WORDS = {
    "naik", "untung", "profit", "rugi turun", "beli", "akumulasi", "bullish",
    "positif", "tumbuh", "melonjak", "menguat", "meroket", "rekor", "dividen",
    "surplus", "gain", "rally", "optimis", "mendapatkan", "labu bersih",
    "laba bersih", "laba", "kenaikan", "peningkatan", "capai", "tembus",
    "beli besar", "akumulasi besar", "overweight", "upgrade", "breakout",
}
NEGATIVE_WORDS = {
    "turun", "rugi", "loss", "jual", "distribusi", "bearish", "negatif",
    "anjlok", "melemah", "terjun", "jatuh", "koreksi", "penurunan", "turun",
    "ditarik", "sell", "underweight", "downgrade", "breakdown", "tekanan",
    "pelarian", "panic", "krisis", "gagal", "bangkrut", "delisting",
    "suspensi", "rugi bersih", "defisit", "tertekan", "melemah",
}

# Regex for IDX ticker extraction (4-letter codes)
TICKER_PATTERN = re.compile(r"\b([A-Z]{4})\b")


class NewsFetcher:
    """Fetch news from RSS feeds, extract tickers, score sentiment, store to DB."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._owns_session = session is None
        self._feedparser = None
        self._transformer = None

    def _get_session(self) -> Session:
        if self._session is None:
            self._session = get_sessionmaker()()
            self._owns_session = True
        return self._session

    def _close_session(self) -> None:
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    def _init_feedparser(self):
        if self._feedparser is None:
            try:
                import feedparser
                self._feedparser = feedparser
            except ImportError:
                logger.error("feedparser not installed. Run: uv pip install feedparser")
                raise

    def _score_sentiment_lexicon(self, text: str) -> tuple[float, str]:
        """Score sentiment using Indonesian financial lexicon.

        Returns (score, label) where score is -1.0 to 1.0 and label is
        'positive', 'negative', or 'neutral'.
        """
        text_lower = text.lower()
        pos_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)
        neg_count = sum(1 for w in NEGATIVE_WORDS if w in text_lower)

        total = pos_count + neg_count
        if total == 0:
            return 0.0, "neutral"

        score = (pos_count - neg_count) / total
        if score > 0.1:
            return score, "positive"
        elif score < -0.1:
            return score, "negative"
        return score, "neutral"

    def _extract_tickers(self, text: str, valid_tickers: set[str] | None = None) -> list[str]:
        """Extract IDX ticker codes (4-letter uppercase) from text.

        Args:
            text: Text to search.
            valid_tickers: Set of valid tickers (with .JK suffix). If provided,
                only return tickers in this set.
        """
        tickers = set()
        for match in TICKER_PATTERN.finditer(text):
            code = match.group(1)
            # Filter common false positives
            if code not in {"THIS", "THAT", "WITH", "FROM", "HAVE", "BEEN", "WERE",
                           "WILL", "THEY", "THEM", "SOME", "SUCH", "EACH", "BOTH",
                           "INFO", "DATA", "NEWS", "MARK", "JAKA", "BANK", "INDO"}:
                ticker = f"{code}.JK"
                if valid_tickers is None or ticker in valid_tickers:
                    tickers.add(ticker)
        return list(tickers)

    def fetch_and_store(self, hours_back: int = 24) -> dict[str, int]:
        """Fetch news from RSS feeds and store to news_sentiment table.

        Args:
            hours_back: Only process news within this many hours (default 24).

        Returns:
            Dict with keys: feeds_checked, articles_fetched, articles_stored,
            tickers_extracted, errors.
        """
        self._init_feedparser()
        session = self._get_session()
        feedparser = self._feedparser

        # Load valid tickers from instruments table for FK validation
        valid_tickers = set()
        try:
            rows = session.execute(text("SELECT ticker FROM instruments")).all()
            valid_tickers = {r[0] for r in rows}
            logger.info("Loaded %d valid tickers from instruments", len(valid_tickers))
        except Exception as e:
            logger.warning("Could not load valid tickers: %s", e)

        cutoff = datetime.now(UTC) - timedelta(hours=hours_back)

        feeds_checked = 0
        articles_fetched = 0
        articles_stored = 0
        tickers_extracted = 0
        errors = 0

        for feed_info in RSS_FEEDS:
            feeds_checked += 1
            try:
                feed = feedparser.parse(feed_info["url"])
                if not feed.entries:
                    logger.debug("No entries from %s", feed_info["name"])
                    continue

                for entry in feed.entries:
                    title = entry.get("title", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    published_str = entry.get("published", entry.get("updated", ""))
                    link = entry.get("link", "")

                    # Parse published date
                    try:
                        if hasattr(entry, "published_parsed"):
                            pub_date = datetime(*entry.published_parsed[:6], tzinfo=UTC)
                        elif hasattr(entry, "updated_parsed"):
                            pub_date = datetime(*entry.updated_parsed[:6], tzinfo=UTC)
                        else:
                            pub_date = datetime.now(UTC)
                    except Exception:
                        pub_date = datetime.now(UTC)

                    if pub_date < cutoff:
                        continue

                    articles_fetched += 1

                    # Extract tickers from title + summary
                    combined_text = f"{title} {summary}"
                    tickers = self._extract_tickers(combined_text, valid_tickers)

                    # Score sentiment
                    score, label = self._score_sentiment_lexicon(combined_text)

                    # Skip if no valid tickers found (FK constraint)
                    if not tickers:
                        continue

                    for ticker in tickers:
                        try:
                            session.execute(
                                text("""
                                    INSERT INTO news_sentiment
                                        (ticker, date, headline, sentiment_score,
                                         sentiment_label, source, url, created_at)
                                    VALUES
                                        (:ticker, :date, :headline, :score,
                                         :label, :source, :url, :now)
                                    ON CONFLICT (ticker, date, headline) DO NOTHING
                                """),
                                {
                                    "ticker": ticker,
                                    "date": pub_date.date(),
                                    "headline": title[:500],
                                    "score": score,
                                    "label": label,
                                    "source": feed_info["name"],
                                    "url": link[:1000],
                                    "now": datetime.now(UTC),
                                },
                            )
                            articles_stored += 1
                            tickers_extracted += 1
                        except Exception as e:
                            logger.debug("Failed to store news for %s: %s", ticker, e)
                            errors += 1

                session.commit()
                logger.info("News from %s: %d articles, %d stored",
                           feed_info["name"], len(feed.entries), articles_stored)

            except Exception as e:
                logger.error("Failed to fetch RSS from %s: %s", feed_info["name"], e)
                session.rollback()
                errors += 1

        self._close_session()

        logger.info(
            "News fetch complete: %d feeds, %d articles, %d stored, %d tickers, %d errors",
            feeds_checked, articles_fetched, articles_stored, tickers_extracted, errors,
        )

        return {
            "feeds_checked": feeds_checked,
            "articles_fetched": articles_fetched,
            "articles_stored": articles_stored,
            "tickers_extracted": tickers_extracted,
            "errors": errors,
        }
