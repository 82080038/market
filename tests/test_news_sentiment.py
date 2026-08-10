"""Tests for unified NewsSentimentAnalyzer and NewsFeatureProvider."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from market.analysis.news_sentiment import (
    FINANCIAL_CONTEXT_WORDS,
    NEGATION_WORDS,
    NEGATIVE_WORDS,
    POSITIVE_WORDS,
    NewsFeatureVector,
    NewsSentimentAnalyzer,
    NewsSentimentResult,
    analyze_news_texts,
    classify_sentiment,
    compute_sentiment,
    get_analyzer,
)


# ── NewsSentimentResult dataclass ──────────────────────────────────────


class TestNewsSentimentResult:
    def test_default_values(self):
        r = NewsSentimentResult(
            score=0.0, label="neutral", confidence=0.0,
            positive_count=0, negative_count=0, relevance=0.0,
            method="keyword",
        )
        assert r.score == 0.0
        assert r.label == "neutral"
        assert r.method == "keyword"

    def test_positive_result(self):
        r = NewsSentimentResult(
            score=0.8, label="positive", confidence=0.9,
            positive_count=5, negative_count=1, relevance=0.6,
            method="keyword",
        )
        assert r.score == 0.8
        assert r.label == "positive"
        assert r.positive_count == 5


# ── Keyword-based analysis ─────────────────────────────────────────────


class TestKeywordAnalysis:
    def test_positive_text(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Saham BBCA naik meroket, profit melonjak")
        assert result.score > 0
        assert result.label == "positive"
        assert result.positive_count >= 2
        assert result.method == "keyword"

    def test_negative_text(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Saham anjlok, rugi besar, bearish")
        assert result.score < 0
        assert result.label == "negative"
        assert result.negative_count >= 2

    def test_neutral_text(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Hari ini cuaca cerah di Jakarta")
        assert result.score == 0.0
        assert result.label == "neutral"
        assert result.positive_count == 0
        assert result.negative_count == 0

    def test_empty_text(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("")
        assert result.score == 0.0
        assert result.label == "neutral"

    def test_none_text(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text(None)
        assert result.score == 0.0

    def test_negation_handling(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        # "tidak naik" should be negative
        result = analyzer.analyze_text("saham tidak naik")
        assert result.negative_count >= 1
        assert result.positive_count == 0

    def test_negation_reverses_negative(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        # "tidak turun" should be positive
        result = analyzer.analyze_text("saham tidak turun")
        assert result.positive_count >= 1
        assert result.negative_count == 0

    def test_intensifier_boost(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        # "sangat naik" should have higher positive weight than "naik"
        result_normal = analyzer.analyze_text("naik")
        result_intensified = analyzer.analyze_text("sangat naik")
        assert result_intensified.positive_count >= result_normal.positive_count

    def test_english_positive(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Stock surge, profit beat expectations")
        assert result.score > 0
        assert result.label == "positive"

    def test_english_negative(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Stock plunge, loss, bankruptcy fears")
        assert result.score < 0
        assert result.label == "negative"

    def test_mixed_language(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Saham rally tapi rugi masih besar")
        # Both positive and negative words present
        assert result.positive_count >= 1
        assert result.negative_count >= 1

    def test_body_concatenated(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Saham", "naik profit bullish")
        assert result.score > 0
        assert result.label == "positive"

    def test_confidence_increases_with_more_keywords(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result1 = analyzer.analyze_text("naik")
        result3 = analyzer.analyze_text("naik profit bullish rally gain")
        assert result3.confidence > result1.confidence


# ── Financial relevance ────────────────────────────────────────────────


class TestRelevance:
    def test_high_relevance(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Saham emit laporan keuangan pendapatan earnings revenue")
        assert result.relevance > 0.5

    def test_low_relevance(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Cuaca hari ini cerah sekali")
        assert result.relevance < 0.2

    def test_no_relevance(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        result = analyzer.analyze_text("Olahraga sepak bola")
        assert result.relevance == 0.0


# ── Time-decay weighting ───────────────────────────────────────────────


class TestTimeDecay:
    def test_decay_weight_recent(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        ref = date(2026, 8, 11)
        news_date = date(2026, 8, 10)  # 1 day old
        weight = analyzer.compute_time_decay_weight(news_date, ref, half_life_days=7.0)
        assert weight > 0.9  # Almost 1.0

    def test_decay_weight_old(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        ref = date(2026, 8, 11)
        news_date = date(2026, 7, 28)  # 14 days old = 2 half-lives
        weight = analyzer.compute_time_decay_weight(news_date, ref, half_life_days=7.0)
        assert abs(weight - 0.25) < 0.01  # 0.5^2 = 0.25

    def test_decay_weight_future(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        ref = date(2026, 8, 11)
        news_date = date(2026, 8, 15)  # Future date
        weight = analyzer.compute_time_decay_weight(news_date, ref, half_life_days=7.0)
        assert weight == 1.0  # Clamped to 1.0

    def test_weighted_sentiment_prefers_recent(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        ref = date(2026, 8, 11)
        items = [
            {"title": "saham naik profit", "date": ref - timedelta(days=1)},  # Recent positive
            {"title": "saham rugi anjlok", "date": ref - timedelta(days=30)},  # Old negative
        ]
        score = analyzer.weighted_sentiment(items, reference_date=ref, half_life_days=7.0)
        # Recent positive should dominate
        assert score > 0

    def test_weighted_sentiment_empty(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        assert analyzer.weighted_sentiment([]) == 0.0

    def test_weighted_sentiment_no_dates(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        items = [{"title": "saham naik", "date": None}]
        score = analyzer.weighted_sentiment(items)
        assert score > 0  # No date → weight = 1.0


# ── Batch analysis ─────────────────────────────────────────────────────


class TestBatchAnalysis:
    def test_batch_multiple(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        items = [
            {"title": "saham naik profit"},
            {"title": "saham anjlok rugi"},
            {"title": "cuaca cerah"},
        ]
        results = analyzer.analyze_batch(items)
        assert len(results) == 3
        assert results[0].score > 0
        assert results[1].score < 0
        assert results[2].score == 0.0

    def test_batch_empty(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        results = analyzer.analyze_batch([])
        assert results == []


# ── Feature vector extraction ──────────────────────────────────────────


class TestFeatureExtraction:
    def test_extract_features_basic(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        ref = date(2026, 8, 11)
        items = [
            {"title": "saham naik profit bullish", "date": ref - timedelta(days=1)},
            {"title": "saham untung dividen", "date": ref - timedelta(days=2)},
            {"title": "saham rugi anjlok", "date": ref - timedelta(days=5)},
        ]
        fv = analyzer.extract_features(items, reference_date=ref)
        assert isinstance(fv, NewsFeatureVector)
        assert fv.news_count == 3
        assert fv.positive_ratio > 0
        assert fv.negative_ratio > 0
        assert fv.neutral_ratio >= 0
        assert fv.sentiment_volatility > 0
        assert fv.days_since_last_news == 1

    def test_extract_features_empty(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        fv = analyzer.extract_features([])
        assert fv.news_count == 0
        assert fv.sentiment_score == 0.0
        assert fv.neutral_ratio == 1.0
        assert fv.days_since_last_news == 999

    def test_extract_features_with_momentum(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        ref = date(2026, 8, 11)
        current = [
            {"title": "saham naik profit", "date": ref - timedelta(days=1)},
        ]
        previous = [
            {"title": "saham rugi anjlok", "date": ref - timedelta(days=35)},
        ]
        fv = analyzer.extract_features(current, previous_items=previous, reference_date=ref)
        # Momentum should be positive (current positive vs previous negative)
        assert fv.sentiment_momentum > 0

    def test_extract_features_decay_weighted(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        ref = date(2026, 8, 11)
        # Use different scores so decay weighting matters
        items = [
            {"title": "saham naik profit", "date": ref - timedelta(days=1)},   # positive, recent
            {"title": "saham rugi anjlok", "date": ref - timedelta(days=14)},  # negative, old
        ]
        fv = analyzer.extract_features(items, reference_date=ref, half_life_days=7.0)
        assert fv.decay_weighted_score > 0  # Recent positive dominates
        # Decay weighted should be more positive than simple avg (recent positive weighted more)
        assert fv.decay_weighted_score > fv.sentiment_score


# ── TF-IDF ─────────────────────────────────────────────────────────────


class TestTFIDF:
    def test_fit_and_extract(self):
        analyzer = NewsSentimentAnalyzer(method="keyword", tfidf_max_features=20)
        corpus = [
            "saham naik profit dividen",
            "saham rugi anjlok bearish",
            "emit laporan keuangan pendapatan",
            "broker rekomendasi beli saham",
        ]
        analyzer.fit_tfidf(corpus)
        features = analyzer.extract_tfidf_features("saham naik profit")
        assert len(features) > 0
        assert all(isinstance(v, float) for v in features.values())

    def test_tfidf_not_fitted(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        features = analyzer.extract_tfidf_features("saham naik")
        assert features == {}


# ── Convenience functions ──────────────────────────────────────────────


class TestConvenienceFunctions:
    def test_compute_sentiment(self):
        score, label = compute_sentiment("saham naik profit")
        assert score > 0
        assert label == "positive"

    def test_classify_sentiment(self):
        score, label = classify_sentiment("saham anjlok rugi")
        assert score < 0
        assert label == "negative"

    def test_analyze_news_texts(self):
        score = analyze_news_texts(["saham naik", "profit bullish"])
        # 0-100 scale, 50 = neutral
        assert score > 50.0

    def test_analyze_news_texts_empty(self):
        assert analyze_news_texts([]) == 50.0

    def test_get_analyzer_singleton(self):
        a1 = get_analyzer()
        a2 = get_analyzer()
        assert a1 is a2


# ── Active method ──────────────────────────────────────────────────────


class TestActiveMethod:
    def test_keyword_method(self):
        analyzer = NewsSentimentAnalyzer(method="keyword")
        assert analyzer.active_method == "keyword"

    def test_auto_falls_back_to_keyword(self):
        # Without transformers installed, auto should fall back
        analyzer = NewsSentimentAnalyzer(method="auto")
        # Either transformer or keyword, depending on environment
        assert analyzer.active_method in ("keyword", "transformer")


# ── Lexicon coverage ───────────────────────────────────────────────────


class TestLexicon:
    def test_positive_words_not_empty(self):
        assert len(POSITIVE_WORDS) > 50

    def test_negative_words_not_empty(self):
        assert len(NEGATIVE_WORDS) > 50

    def test_negation_words_present(self):
        assert "tidak" in NEGATION_WORDS
        assert "bukan" in NEGATION_WORDS
        assert "not" in NEGATION_WORDS

    def test_financial_context_words_present(self):
        assert "saham" in FINANCIAL_CONTEXT_WORDS
        assert "dividen" in FINANCIAL_CONTEXT_WORDS
        assert "earnings" in FINANCIAL_CONTEXT_WORDS

    def test_no_overlap_pos_neg(self):
        overlap = POSITIVE_WORDS & NEGATIVE_WORDS
        assert len(overlap) == 0, f"Overlap: {overlap}"


# ── NewsFeatureProvider ────────────────────────────────────────────────


class TestNewsFeatureProvider:
    def test_empty_features(self):
        from market.analysis.news_features import NewsFeatureProvider
        provider = NewsFeatureProvider()
        features = provider._empty_features()
        assert features["news_sentiment_score"] == 0.0
        assert features["news_count"] == 0.0
        assert features["news_neutral_ratio"] == 1.0
        assert features["news_days_since_last"] == 999.0

    def test_get_features_no_data(self, isolated_db):
        from market.analysis.news_features import NewsFeatureProvider
        provider = NewsFeatureProvider()
        features = provider.get_features("NONEXIST.JK", isolated_db, date(2026, 8, 11))
        assert features["news_count"] == 0.0
        assert features["news_sentiment_score"] == 0.0

    def test_get_features_batch_empty(self, isolated_db):
        from market.analysis.news_features import NewsFeatureProvider
        provider = NewsFeatureProvider()
        df = provider.get_features_batch(["NONEXIST.JK"], isolated_db, date(2026, 8, 11))
        assert len(df) == 1
        assert "news_sentiment_score" in df.columns
