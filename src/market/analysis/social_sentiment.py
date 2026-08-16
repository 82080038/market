"""Social sentiment analysis from Reddit and X/Twitter (Gap #26).

Collects social media posts mentioning stock tickers and computes
sentiment scores using text analysis. Integrates with SentimentEngine.

Data sources:
- Reddit (via praw): r/wallstreetbets, r/stocks, r/investing, r/saham
- X/Twitter (via tweepy): Search for $TICKER mentions

Graceful degradation:
- If praw/tweepy not installed, returns empty results with warning.
- If API credentials missing, returns empty results with warning.
- Never crashes the application due to social sentiment failure.

Note: This is NOT social/copy trading. This is sentiment data collection
for analysis purposes only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SentimentLabel(str, Enum):
    """Sentiment classification labels."""

    VERY_BEARISH = "very_bearish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    VERY_BULLISH = "very_bullish"


@dataclass
class SocialPost:
    """A social media post mentioning a ticker."""

    platform: str  # "reddit" or "x"
    post_id: str
    ticker: str
    text: str
    author: str
    created_at: str
    score: int = 0  # Upvotes/likes
    comments: int = 0
    url: str = ""
    subreddit: str = ""  # Reddit only


@dataclass
class SentimentResult:
    """Sentiment analysis result for a single post."""

    post: SocialPost
    sentiment_score: float  # -1.0 to 1.0
    label: SentimentLabel
    confidence: float  # 0.0 to 1.0
    keywords: list[str] = field(default_factory=list)


@dataclass
class AggregatedSentiment:
    """Aggregated sentiment for a ticker."""

    ticker: str
    platform: str
    post_count: int
    avg_sentiment: float  # -1.0 to 1.0
    sentiment_label: SentimentLabel
    bullish_count: int
    bearish_count: int
    neutral_count: int
    total_score: int  # Sum of upvotes/likes
    top_keywords: list[str] = field(default_factory=list)
    assessed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── Sentiment lexicon (simplified, Indonesian + English) ──────────────────

BULLISH_WORDS = {
    # English
    "buy", "bullish", "moon", "rocket", "pump", "long", "hold", "diamond",
    "hands", "tendies", "green", "gain", "profit", "breakout", "support",
    "undervalued", "accumulate", "strong", "upgrade", "beat", "surge",
    "rally", "boom", "growth", "outperform", "overweight",
    # Indonesian
    "beli", "naik", "untung", "cuan", "laba", "rangking", "kenceng",
    "bagus", "mantap", "oke", " lancar", "positif", "naiknya",
}

BEARISH_WORDS = {
    # English
    "sell", "bearish", "dump", "short", "put", "crash", "bubble",
    "overvalued", "decline", "loss", "red", "fall", "drop", "weak",
    "downgrade", "miss", "plunge", "bear", "correction", "risk",
    "sell-off", "capitulation", "bankruptcy", "fraud",
    # Indonesian
    "jual", "turun", "rugi", "merugi", "jatuh", "lemah", "buruk",
    "negatif", "anjlok", "kerugian", "gagal", "bahaya", "anjlok",
}


class SocialSentimentCollector:
    """Collects social media posts and computes sentiment (Gap #26).

    Supports Reddit (via praw) and X/Twitter (via tweepy).
    Gracefully degrades if libraries or credentials are missing.
    """

    # Default subreddits to monitor
    DEFAULT_SUBREDDITS = [
        "wallstreetbets", "stocks", "investing", "saham",
        "IndonesianStocks", "stockmarket",
    ]

    def __init__(
        self,
        reddit_client_id: str | None = None,
        reddit_client_secret: str | None = None,
        reddit_user_agent: str = "market-app/1.0",
        x_bearer_token: str | None = None,
        subreddits: list[str] | None = None,
    ) -> None:
        self.reddit_client_id = reddit_client_id
        self.reddit_client_secret = reddit_client_secret
        self.reddit_user_agent = reddit_user_agent
        self.x_bearer_token = x_bearer_token
        self.subreddits = subreddits or self.DEFAULT_SUBREDDITS

        self._reddit = None
        self._x_client = None
        self._init_reddit()
        self._init_x()

    def _init_reddit(self) -> None:
        """Initialize Reddit client (praw)."""
        if not self.reddit_client_id or not self.reddit_client_secret:
            logger.info("Reddit credentials not configured — Reddit sentiment disabled.")
            return
        try:
            import praw  # type: ignore[import-untyped]
            self._reddit = praw.Reddit(
                client_id=self.reddit_client_id,
                client_secret=self.reddit_client_secret,
                user_agent=self.reddit_user_agent,
            )
            logger.info("Reddit client initialized.")
        except ImportError:
            logger.warning("praw not installed — Reddit sentiment disabled.")
        except Exception as exc:
            logger.warning("Failed to initialize Reddit client: %s", exc)

    def _init_x(self) -> None:
        """Initialize X/Twitter client (tweepy)."""
        if not self.x_bearer_token:
            logger.info("X/Twitter bearer token not configured — X sentiment disabled.")
            return
        try:
            import tweepy  # type: ignore[import-untyped]
            self._x_client = tweepy.Client(bearer_token=self.x_bearer_token)
            logger.info("X/Twitter client initialized.")
        except ImportError:
            logger.warning("tweepy not installed — X sentiment disabled.")
        except Exception as exc:
            logger.warning("Failed to initialize X client: %s", exc)

    @property
    def reddit_available(self) -> bool:
        return self._reddit is not None

    @property
    def x_available(self) -> bool:
        return self._x_client is not None

    def collect_reddit_posts(
        self,
        ticker: str,
        limit: int = 100,
        time_filter: str = "week",
    ) -> list[SocialPost]:
        """Collect Reddit posts mentioning a ticker.

        Args:
            ticker: Stock ticker (e.g. "BBCA.JK").
            limit: Maximum posts to collect.
            time_filter: "day", "week", "month", "year", "all".

        Returns:
            List of SocialPost objects.
        """
        if not self.reddit_available:
            logger.debug("Reddit not available — returning empty list.")
            return []

        posts: list[SocialPost] = []
        search_query = f'"{ticker}" OR "${ticker}"'

        try:
            for subreddit_name in self.subreddits:
                if len(posts) >= limit:
                    break
                try:
                    subreddit = self._reddit.subreddit(subreddit_name)
                    submissions = subreddit.search(
                        search_query, limit=limit // len(self.subreddits) + 1,
                        time_filter=time_filter,
                    )
                    for submission in submissions:
                        if len(posts) >= limit:
                            break
                        posts.append(SocialPost(
                            platform="reddit",
                            post_id=submission.id,
                            ticker=ticker,
                            text=submission.title + " " + (submission.selftext or ""),
                            author=str(submission.author) if submission.author else "unknown",
                            created_at=datetime.fromtimestamp(
                                submission.created_utc, tz=UTC,
                            ).isoformat(),
                            score=submission.score,
                            comments=submission.num_comments,
                            url=submission.url,
                            subreddit=subreddit_name,
                        ))
                except Exception as exc:
                    logger.debug("Error searching r/%s: %s", subreddit_name, exc)
        except Exception as exc:
            logger.warning("Reddit collection failed: %s", exc)

        return posts

    def collect_x_posts(
        self,
        ticker: str,
        limit: int = 100,
        max_results: int = 100,
    ) -> list[SocialPost]:
        """Collect X/Twitter posts mentioning a ticker.

        Args:
            ticker: Stock ticker.
            limit: Maximum posts to collect.

        Returns:
            List of SocialPost objects.
        """
        if not self.x_available:
            logger.debug("X/Twitter not available — returning empty list.")
            return []

        posts: list[SocialPost] = []
        query = f"${ticker} lang:en OR lang:id -is:retweet"

        try:
            response = self._x_client.search_recent_tweets(
                query=query,
                max_results=min(max_results, limit),
                tweet_fields=["created_at", "public_metrics", "author_id"],
            )
            if response.data:
                for tweet in response.data:
                    metrics = tweet.public_metrics or {}
                    posts.append(SocialPost(
                        platform="x",
                        post_id=tweet.id,
                        ticker=ticker,
                        text=tweet.text,
                        author=str(tweet.author_id),
                        created_at=tweet.created_at.isoformat() if tweet.created_at else "",
                        score=metrics.get("like_count", 0),
                        comments=metrics.get("reply_count", 0),
                    ))
        except Exception as exc:
            logger.warning("X/Twitter collection failed: %s", exc)

        return posts

    def collect_all(
        self,
        ticker: str,
        limit: int = 100,
    ) -> list[SocialPost]:
        """Collect posts from all available platforms.

        Args:
            ticker: Stock ticker.
            limit: Max posts per platform.

        Returns:
            Combined list of SocialPost from all platforms.
        """
        posts: list[SocialPost] = []
        posts.extend(self.collect_reddit_posts(ticker, limit))
        posts.extend(self.collect_x_posts(ticker, limit))
        return posts

    @staticmethod
    def analyze_sentiment(post: SocialPost) -> SentimentResult:
        """Analyze sentiment of a single post using lexicon-based approach.

        Args:
            post: Social media post.

        Returns:
            SentimentResult with score, label, and confidence.
        """
        text_lower = post.text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        bullish_hits = words & BULLISH_WORDS
        bearish_hits = words & BEARISH_WORDS

        bullish_count = len(bullish_hits)
        bearish_count = len(bearish_hits)
        total = bullish_count + bearish_count

        if total == 0:
            score = 0.0
            label = SentimentLabel.NEUTRAL
            confidence = 0.5
        else:
            score = (bullish_count - bearish_count) / total
            confidence = min(1.0, total / 10.0)  # More keywords = higher confidence

            if score > 0.5:
                label = SentimentLabel.VERY_BULLISH
            elif score > 0.1:
                label = SentimentLabel.BULLISH
            elif score < -0.5:
                label = SentimentLabel.VERY_BEARISH
            elif score < -0.1:
                label = SentimentLabel.BEARISH
            else:
                label = SentimentLabel.NEUTRAL

        keywords = list(bullish_hits | bearish_hits)

        return SentimentResult(
            post=post,
            sentiment_score=round(score, 4),
            label=label,
            confidence=round(confidence, 4),
            keywords=keywords,
        )

    def analyze_ticker(
        self,
        ticker: str,
        limit: int = 100,
    ) -> dict[str, AggregatedSentiment]:
        """Collect and analyze sentiment for a ticker across all platforms.

        Args:
            ticker: Stock ticker.
            limit: Max posts per platform.

        Returns:
            Dict mapping platform name to AggregatedSentiment.
        """
        posts = self.collect_all(ticker, limit)
        results = [self.analyze_sentiment(p) for p in posts]

        # Group by platform
        by_platform: dict[str, list[SentimentResult]] = {}
        for r in results:
            by_platform.setdefault(r.post.platform, []).append(r)

        aggregated: dict[str, AggregatedSentiment] = {}
        for platform, platform_results in by_platform.items():
            scores = [r.sentiment_score for r in platform_results]
            avg_score = sum(scores) / len(scores) if scores else 0.0

            bullish = sum(1 for r in platform_results if r.sentiment_score > 0.1)
            bearish = sum(1 for r in platform_results if r.sentiment_score < -0.1)
            neutral = len(platform_results) - bullish - bearish

            # Aggregate keywords
            keyword_counts: dict[str, int] = {}
            for r in platform_results:
                for kw in r.keywords:
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
            top_keywords = sorted(keyword_counts, key=lambda k: -keyword_counts[k])[:10]

            # Determine label
            if avg_score > 0.5:
                label = SentimentLabel.VERY_BULLISH
            elif avg_score > 0.1:
                label = SentimentLabel.BULLISH
            elif avg_score < -0.5:
                label = SentimentLabel.VERY_BEARISH
            elif avg_score < -0.1:
                label = SentimentLabel.BEARISH
            else:
                label = SentimentLabel.NEUTRAL

            total_score = sum(r.post.score for r in platform_results)

            aggregated[platform] = AggregatedSentiment(
                ticker=ticker,
                platform=platform,
                post_count=len(platform_results),
                avg_sentiment=round(avg_score, 4),
                sentiment_label=label,
                bullish_count=bullish,
                bearish_count=bearish,
                neutral_count=neutral,
                total_score=total_score,
                top_keywords=top_keywords,
            )

        return aggregated
