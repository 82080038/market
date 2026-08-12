"""Tests for denoised news encoder."""

from __future__ import annotations

import pandas as pd
import pytest

from market.analysis.denoised_news import (
    DenoisedNewsEncoder,
    NewsScore,
    _keyword_impact,
    _keyword_sentiment,
    _ticker_relevance,
)


class TestKeywordSentiment:
    def test_positive(self):
        assert _keyword_sentiment("BBCA untung besar dividen") > 0

    def test_negative(self):
        assert _keyword_sentiment("suspensi perdagangan rugi besar") < 0

    def test_neutral(self):
        assert _keyword_sentiment("rapat umum pemegang saham") == 0.0

    def test_rate_hike_negative(self):
        assert _keyword_sentiment("BI naikkan suku bunga 25 bps") < 0

    def test_rate_cut_positive(self):
        assert _keyword_sentiment("Fed penurunan suku bunga 50 bps") > 0


class TestKeywordImpact:
    def test_high_impact(self):
        assert _keyword_impact("BI rate dividen buyback akuisisi") == 100.0

    def test_medium_impact(self):
        assert _keyword_impact("BI rate dividen") == 75.0

    def test_low_impact(self):
        assert _keyword_impact("BI rate") == 50.0

    def test_no_impact(self):
        assert _keyword_impact("cuaca hari ini cerah") == 0.0


class TestTickerRelevance:
    def test_direct_ticker(self):
        assert _ticker_relevance("BBCA naik", "BBCA.JK") == 1.0

    def test_company_name(self):
        assert _ticker_relevance("Bank Central Asia untung", "BBCA.JK") == 0.9

    def test_no_relevance(self):
        assert _ticker_relevance("cuaca cerah", "BBCA.JK") == 0.0


class TestDenoisedNewsEncoder:
    def test_score_news(self):
        encoder = DenoisedNewsEncoder()
        score = encoder.score_news("BBCA untung besar dividen", "BBCA.JK")
        assert isinstance(score, NewsScore)
        assert score.sentiment > 0
        assert score.impact > 0
        assert score.relevance > 0
        assert score.denoised_score > 0

    def test_score_irrelevant_news(self):
        encoder = DenoisedNewsEncoder()
        score = encoder.score_news("cuaca cerah hari ini", "BBCA.JK")
        assert score.relevance == 0.0
        assert score.denoised_score == 0.0

    def test_aggregate_signal(self):
        encoder = DenoisedNewsEncoder()
        news_df = pd.DataFrame({
            "judul": ["BBCA dividen besar", "BBCA untung", "cuaca cerah"],
            "tanggal": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        })
        signal = encoder.aggregate_signal(news_df, "BBCA.JK", lookback_days=5)
        assert -1.0 <= signal <= 1.0
        assert signal > 0  # Positive news

    def test_aggregate_signal_empty(self):
        encoder = DenoisedNewsEncoder()
        signal = encoder.aggregate_signal(pd.DataFrame(), "BBCA.JK")
        assert signal == 0.0

    def test_generate_signal_series(self):
        encoder = DenoisedNewsEncoder()
        news_df = pd.DataFrame({
            "judul": ["BBCA dividen besar", "BBCA rugi besar"],
            "tanggal": pd.to_datetime(["2024-01-01", "2024-06-01"]),
        })
        dates = pd.date_range("2024-01-01", "2024-12-31", freq="B")
        signals = encoder.generate_signal_series(news_df, "BBCA.JK", dates, lookback_days=5)
        assert len(signals) == len(dates)
        assert signals.isin([-1, 0, 1]).all()

    def test_llm_fallback(self):
        encoder = DenoisedNewsEncoder(use_llm=True, llm_model="test")
        # Should fall back to rule-based
        assert encoder.use_llm is False
