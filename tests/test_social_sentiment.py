"""Tests for social sentiment analysis (Gap #26)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from market.analysis.social_sentiment import (
    AggregatedSentiment,
    SentimentLabel,
    SentimentResult,
    SocialPost,
    SocialSentimentCollector,
    BEARISH_WORDS,
    BULLISH_WORDS,
)


@pytest.fixture
def collector() -> SocialSentimentCollector:
    """Collector with no credentials (graceful degradation)."""
    return SocialSentimentCollector()


def test_sentiment_label_enum():
    """SentimentLabel has expected values."""
    assert SentimentLabel.VERY_BULLISH.value == "very_bullish"
    assert SentimentLabel.BEARISH.value == "bearish"
    assert SentimentLabel.NEUTRAL.value == "neutral"


def test_collector_no_credentials(collector: SocialSentimentCollector):
    """Collector without credentials is not available."""
    assert collector.reddit_available is False
    assert collector.x_available is False


def test_collect_reddit_no_credentials(collector: SocialSentimentCollector):
    """collect_reddit_posts returns empty list without credentials."""
    posts = collector.collect_reddit_posts("BBCA.JK", limit=10)
    assert posts == []


def test_collect_x_no_credentials(collector: SocialSentimentCollector):
    """collect_x_posts returns empty list without credentials."""
    posts = collector.collect_x_posts("BBCA.JK", limit=10)
    assert posts == []


def test_collect_all_no_credentials(collector: SocialSentimentCollector):
    """collect_all returns empty list without credentials."""
    posts = collector.collect_all("BBCA.JK", limit=10)
    assert posts == []


def test_analyze_sentiment_bullish(collector: SocialSentimentCollector):
    """analyze_sentiment detects bullish sentiment."""
    post = SocialPost(
        platform="reddit", post_id="1", ticker="BBCA.JK",
        text="BBCA is going to moon! Buy buy buy! Strong breakout!",
        author="user1", created_at=datetime.now(UTC).isoformat(),
        score=100,
    )
    result = collector.analyze_sentiment(post)
    assert result.sentiment_score > 0
    assert result.label in (SentimentLabel.BULLISH, SentimentLabel.VERY_BULLISH)
    assert len(result.keywords) > 0


def test_analyze_sentiment_bearish(collector: SocialSentimentCollector):
    """analyze_sentiment detects bearish sentiment."""
    post = SocialPost(
        platform="reddit", post_id="2", ticker="BBCA.JK",
        text="Sell BBCA now! Crash coming. Overvalued and weak.",
        author="user2", created_at=datetime.now(UTC).isoformat(),
        score=50,
    )
    result = collector.analyze_sentiment(post)
    assert result.sentiment_score < 0
    assert result.label in (SentimentLabel.BEARISH, SentimentLabel.VERY_BEARISH)


def test_analyze_sentiment_neutral(collector: SocialSentimentCollector):
    """analyze_sentiment returns neutral for no keywords."""
    post = SocialPost(
        platform="x", post_id="3", ticker="BBCA.JK",
        text="Just checking the weather today.",
        author="user3", created_at=datetime.now(UTC).isoformat(),
    )
    result = collector.analyze_sentiment(post)
    assert result.sentiment_score == 0.0
    assert result.label == SentimentLabel.NEUTRAL


def test_analyze_sentiment_indonesian_bullish(collector: SocialSentimentCollector):
    """analyze_sentiment detects Indonesian bullish words."""
    post = SocialPost(
        platform="reddit", post_id="4", ticker="TLKM.JK",
        text="TLKM cuan besar! Beli sekarang, naiknya kenceng!",
        author="user4", created_at=datetime.now(UTC).isoformat(),
    )
    result = collector.analyze_sentiment(post)
    assert result.sentiment_score > 0
    assert result.label in (SentimentLabel.BULLISH, SentimentLabel.VERY_BULLISH)


def test_analyze_sentiment_indonesian_bearish(collector: SocialSentimentCollector):
    """analyze_sentiment detects Indonesian bearish words."""
    post = SocialPost(
        platform="reddit", post_id="5", ticker="TLKM.JK",
        text="TLKM turun, rugi nih. Jual saja, bahaya.",
        author="user5", created_at=datetime.now(UTC).isoformat(),
    )
    result = collector.analyze_sentiment(post)
    assert result.sentiment_score < 0
    assert result.label in (SentimentLabel.BEARISH, SentimentLabel.VERY_BEARISH)


def test_analyze_sentiment_mixed(collector: SocialSentimentCollector):
    """analyze_sentiment handles mixed sentiment."""
    post = SocialPost(
        platform="x", post_id="6", ticker="BBCA.JK",
        text="Buy BBCA but also risk of decline. Bullish but cautious.",
        author="user6", created_at=datetime.now(UTC).isoformat(),
    )
    result = collector.analyze_sentiment(post)
    # Should be between -1 and 1
    assert -1.0 <= result.sentiment_score <= 1.0


def test_analyze_sentiment_confidence(collector: SocialSentimentCollector):
    """Confidence increases with more keywords."""
    few = SocialPost(
        platform="x", post_id="7", ticker="X",
        text="buy", author="u", created_at="",
    )
    many = SocialPost(
        platform="x", post_id="8", ticker="X",
        text="buy bullish moon rocket pump long hold green gain profit breakout",
        author="u", created_at="",
    )
    r_few = collector.analyze_sentiment(few)
    r_many = collector.analyze_sentiment(many)
    assert r_many.confidence > r_few.confidence


def test_bullish_words_not_empty():
    """Bullish lexicon is populated."""
    assert len(BULLISH_WORDS) > 10
    assert "buy" in BULLISH_WORDS
    assert "beli" in BULLISH_WORDS


def test_bearish_words_not_empty():
    """Bearish lexicon is populated."""
    assert len(BEARISH_WORDS) > 10
    assert "sell" in BEARISH_WORDS
    assert "jual" in BEARISH_WORDS


def test_bullish_and_bearish_disjoint():
    """Bullish and bearish words don't overlap."""
    overlap = BULLISH_WORDS & BEARISH_WORDS
    assert len(overlap) == 0


def test_default_subreddits():
    """Default subreddits include relevant ones."""
    assert "wallstreetbets" in SocialSentimentCollector.DEFAULT_SUBREDDITS
    assert "saham" in SocialSentimentCollector.DEFAULT_SUBREDDITS


def test_analyze_ticker_no_credentials(collector: SocialSentimentCollector):
    """analyze_ticker returns empty dict without credentials."""
    result = collector.analyze_ticker("BBCA.JK", limit=10)
    assert result == {}


def test_aggregated_sentiment_dataclass():
    """AggregatedSentiment can be constructed."""
    agg = AggregatedSentiment(
        ticker="X", platform="reddit",
        post_count=10, avg_sentiment=0.5,
        sentiment_label=SentimentLabel.BULLISH,
        bullish_count=6, bearish_count=2, neutral_count=2,
        total_score=500,
    )
    assert agg.ticker == "X"
    assert agg.post_count == 10
    assert agg.sentiment_label == SentimentLabel.BULLISH
