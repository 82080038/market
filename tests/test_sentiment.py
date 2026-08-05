"""Tests for Sentiment Engine."""

from __future__ import annotations

from market.analysis.sentiment import SentimentEngine


def test_sentiment_all_sources():
    engine = SentimentEngine()
    result = engine.analyze(
        "BBCA.JK",
        foreign_flow_score=70.0,
        broker_summary_score=65.0,
        historical_score=60.0,
        social_media_score=55.0,
        google_trends_score=50.0,
        news_texts=["BBCA profit naik", "dividen dibagikan"],
    )
    assert 0 <= result.score <= 100
    assert result.label in ("positive", "neutral", "negative")
    assert len(result.sources) == 6
    assert "news_nlp" in result.sources


def test_sentent_partial_sources():
    engine = SentimentEngine()
    result = engine.analyze(
        "PARTIAL.JK",
        foreign_flow_score=80.0,
        news_texts=["rugi besar", "anjlok"],
    )
    assert 0 <= result.score <= 100
    assert len(result.sources) == 2


def test_sentiment_no_sources():
    engine = SentimentEngine()
    result = engine.analyze("NODATA.JK")
    assert result.score == 50.0
    assert result.label == "neutral"


def test_sentiment_news_positive():
    engine = SentimentEngine()
    result = engine.analyze(
        "POS.JK", news_texts=["BBCA profit naik", "dividen dibagarkan", "bullish"],
    )
    assert result.sources["news_nlp"] > 50.0


def test_sentiment_news_negative():
    engine = SentimentEngine()
    result = engine.analyze(
        "NEG.JK", news_texts=["rugi besar", "anjlok", "bearish"],
    )
    assert result.sources["news_nlp"] < 50.0


def test_sentiment_news_negation():
    engine = SentimentEngine()
    result = engine.analyze(
        "NEG.JK", news_texts=["tidak naik", "bukan untung"],
    )
    # Negated positive words should be negative
    assert result.sources["news_nlp"] < 50.0


def test_sentiment_news_neutral():
    engine = SentimentEngine()
    result = engine.analyze("NEU.JK", news_texts=["rapat direksi", "pengumuman"])
    assert result.sources["news_nlp"] == 50.0


def test_sentiment_positive_label():
    engine = SentimentEngine()
    result = engine.analyze(
        "STRONG.JK",
        foreign_flow_score=90.0,
        broker_summary_score=85.0,
        historical_score=80.0,
        social_media_score=75.0,
        google_trends_score=70.0,
        news_texts=["profit naik", "bullish", "rally"],
    )
    assert result.label == "positive"
    assert result.score >= 70.0


def test_sentiment_negative_label():
    engine = SentimentEngine()
    result = engine.analyze(
        "WEAK.JK",
        foreign_flow_score=10.0,
        broker_summary_score=15.0,
        historical_score=20.0,
        news_texts=["rugi", "anjlok", "bearish"],
    )
    assert result.label == "negative"
    assert result.score < 40.0


def test_sentiment_empty_news():
    engine = SentimentEngine()
    result = engine.analyze("EMPTY.JK", news_texts=[])
    assert result.sources["news_nlp"] == 50.0
