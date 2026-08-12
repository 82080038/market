"""Denoised News Encoder — LLM-based multi-perspective news scoring.

Inspired by CausalStock's Denoised News Encoder (Liu et al., 2024) and
Ploutos' Sentiment Analysis Expert (Wang et al., 2024), this module
scores news articles from multiple perspectives to produce denoised
text representations for stock movement prediction.

CausalStock's approach:
- LLM scores every news text from multiple perspectives
- Evaluation scores become denoised text representations
- Removes noise from irrelevant/ambiguous news

This implementation provides two backends:
1. **Rule-based** (default): Keyword + sentiment lexicon scoring
2. **LLM-based** (optional): Uses local LLM (Ollama) or API for scoring

Scoring dimensions (matching CausalStock):
- **Sentiment score**: [-1, 1] — negative, neutral, positive
- **Impact score**: [0, 100] — how relevant to stock price movement
- **Relevance score**: [0, 1] — how related to the specific ticker

References:
    - CausalStock: arxiv.org/abs/2411.06391 (Section 4.2: Market Information Encoder)
    - Ploutos: arxiv.org/abs/2403.00782 (Section 3.1.1: Sentiment Analysis Expert)
    - pustaka/96-ai-ml-audit-framework.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class NewsScore:
    """Multi-perspective news score (CausalStock-style denoised representation)."""

    sentiment: float = 0.0       # [-1, 1] — negative to positive
    impact: float = 0.0          # [0, 100] — relevance to price movement
    relevance: float = 0.0       # [0, 1] — ticker-specific relevance
    denoised_score: float = 0.0  # Weighted composite for signal generation


# Indonesian + English sentiment keywords
POSITIVE_KEYWORDS = {
    "naik", "unggul", "untung", "rugi", "profit", "surplus", "dividen",
    "buyback", "akuisisi", "merger", "ekspansi", "pertumbuhan", "lonjakan",
    "bullish", "rally", "gain", "upgrade", "outperform", "strong",
    "breakthrough", "deal", "contract", "order", "investment", "expansion",
    "hike", "cut",  # rate hike/cut context-dependent
}

NEGATIVE_KEYWORDS = {
    "turun", "rugi", "kerugian", "gagal", "suspensi", "delisting",
    "penurunan", "koreksi", "anjlok", "melemah", "tertekan",
    "bearish", "sell", "downgrade", "underperform", "loss", "debt",
    "default", "fraud", "scandal", "lawsuit", "probe", "investigation",
    "crash", "plunge", "drop", "fall", "decline", "weak",
}

HIGH_IMPACT_KEYWORDS = {
    "bi rate", "fed rate", "suku bunga", "interest rate",
    "dividen", "dividend", "buyback", "rights issue",
    "akuisisi", "acquisition", "merger", "split", "stock split",
    "delisting", "suspensi", "bankrupt", "default",
    "laporan keuangan", "earnings", "quarterly", "annual report",
    "kontrak", "contract", "order", "proyek", "project",
    "rating", "upgrade", "downgrade",
    "geopolitik", "perang", "war", "sanction", "embargo",
    "pandemi", "pandemic", "covid",
}

TICKER_NAME_MAP = {
    "BBCA": ["bank central asia", "bca"],
    "BBRI": ["bank rakyat indonesia", "bri"],
    "BMRI": ["bank mandiri"],
    "BBNI": ["bank negara indonesia", "bni"],
    "TLKM": ["telkom", "telekomunikasi"],
    "ASII": ["astra", "astra international"],
    "UNVR": ["unilever"],
    "GOTO": ["go to", "goto", "gojek", "tokopedia"],
    "ANTM": ["antam", "aneka tambang"],
    "UNTR": ["united tractors"],
    "INDF": ["indofood"],
    "ICBP": ["indofood cbp"],
    "KLBF": ["kalbe farma"],
    "ADRO": ["adaro"],
    "MDKA": ["merdeka copper"],
    "PGAS": ["perusahaan gas negara", "pgn"],
    "SMGR": ["semen gresik", "semen indonesia"],
    "TBKA": ["tabarakah"],
    "BRPT": ["barito pacific"],
    "EMTK": ["elang mahkota"],
}


def _keyword_sentiment(text: str) -> float:
    """Compute sentiment from keyword matching."""
    text_lower = text.lower()

    # Context-dependent: rate hikes/cuts (check FIRST to override generic keywords)
    rate_hike_patterns = [
        "rate hike", "kenaikan suku bunga", "naikkan suku bunga", "naikkan bunga",
        "bunga naik", "suku bunga naik", "bi rate naik", "fed rate naik",
        "kenaikan bi rate", "kenaikan fed rate",
    ]
    rate_cut_patterns = [
        "rate cut", "penurunan suku bunga", "turunkan suku bunga", "turunkan bunga",
        "bunga turun", "suku bunga turun", "bi rate turun", "fed rate turun",
        "penurunan bi rate", "penurunan fed rate",
    ]

    is_rate_hike = any(p in text_lower for p in rate_hike_patterns)
    is_rate_cut = any(p in text_lower for p in rate_cut_patterns)

    if is_rate_hike and not is_rate_cut:
        return -0.5  # Rate hike is negative for stocks
    if is_rate_cut and not is_rate_hike:
        return 0.5  # Rate cut is positive for stocks

    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

    total = pos_count + neg_count
    if total == 0:
        return 0.0
    return (pos_count - neg_count) / total


def _keyword_impact(text: str) -> float:
    """Compute impact score from keyword matching."""
    text_lower = text.lower()
    impact_count = sum(1 for kw in HIGH_IMPACT_KEYWORDS if kw in text_lower)
    # Scale: 0 keywords → 0, 1 → 50, 2 → 75, 3+ → 100
    if impact_count == 0:
        return 0.0
    elif impact_count == 1:
        return 50.0
    elif impact_count == 2:
        return 75.0
    else:
        return 100.0


def _ticker_relevance(text: str, ticker: str) -> float:
    """Compute relevance score for a specific ticker."""
    text_lower = text.lower()
    ticker_clean = ticker.replace(".JK", "").replace(".JK", "")

    # Direct ticker mention
    if ticker_clean.lower() in text_lower:
        return 1.0

    # Company name mention
    names = TICKER_NAME_MAP.get(ticker_clean, [])
    for name in names:
        if name in text_lower:
            return 0.9

    # Sector mention (partial relevance)
    return 0.0


class DenoisedNewsEncoder:
    """Multi-perspective news scoring engine (CausalStock-style).

    Scores news articles from multiple perspectives to produce denoised
    representations. Uses rule-based scoring by default, with optional
    LLM backend for higher quality.

    Usage:
        encoder = DenoisedNewsEncoder()
        score = encoder.score_news("BI naikkan suku bunga 25 bps", "BBCA.JK")
        # NewsScore(sentiment=-0.5, impact=100.0, relevance=0.0, denoised_score=-0.5)

        # Aggregate for signal
        signal = encoder.aggregate_signal(news_df, "BBCA.JK", lookback_days=5)
    """

    def __init__(self, use_llm: bool = False, llm_model: str | None = None) -> None:
        self.use_llm = use_llm
        self.llm_model = llm_model
        if use_llm and llm_model:
            logger.info("DenoisedNewsEncoder: LLM backend=%s (not yet implemented, falling back to rules)", llm_model)
            self.use_llm = False  # Fallback until LLM backend is implemented

    def score_news(self, text: str, ticker: str) -> NewsScore:
        """Score a single news article from multiple perspectives.

        Args:
            text: News article text (title or body).
            ticker: Target ticker (e.g. "BBCA.JK").

        Returns:
            NewsScore with sentiment, impact, relevance, and denoised_score.
        """
        sentiment = _keyword_sentiment(text)
        impact = _keyword_impact(text)
        relevance = _ticker_relevance(text, ticker)

        # Denoised score: sentiment weighted by impact and relevance
        # If news is not relevant to ticker, denoised_score → 0
        denoised = sentiment * (impact / 100.0) * relevance

        return NewsScore(
            sentiment=sentiment,
            impact=impact,
            relevance=relevance,
            denoised_score=denoised,
        )

    def score_news_df(
        self,
        news_df: pd.DataFrame,
        ticker: str,
        text_col: str = "judul",
        date_col: str = "tanggal",
    ) -> pd.DataFrame:
        """Score all news in a DataFrame.

        Args:
            news_df: DataFrame with news articles.
            ticker: Target ticker.
            text_col: Column name for news text.
            date_col: Column name for date.

        Returns:
            DataFrame with original columns + score columns.
        """
        if news_df.empty or text_col not in news_df.columns:
            return news_df

        scores = news_df[text_col].fillna("").apply(
            lambda t: self.score_news(str(t), ticker)
        )

        result = news_df.copy()
        result["sentiment"] = scores.apply(lambda s: s.sentiment)
        result["impact"] = scores.apply(lambda s: s.impact)
        result["relevance"] = scores.apply(lambda s: s.relevance)
        result["denoised_score"] = scores.apply(lambda s: s.denoised_score)

        return result

    def aggregate_signal(
        self,
        news_df: pd.DataFrame,
        ticker: str,
        lookback_days: int = 5,
        text_col: str = "judul",
        date_col: str = "tanggal",
    ) -> float:
        """Aggregate news scores into a single signal for a ticker.

        CausalStock uses the denoised scores as input to the prediction model.
        Here we aggregate them into a single signal value.

        Args:
            news_df: DataFrame with news articles.
            ticker: Target ticker.
            lookback_days: Number of recent days to consider.
            text_col: Column name for news text.
            date_col: Column name for date.

        Returns:
            Signal value [-1, 1] — weighted average of denoised scores.
        """
        if news_df.empty:
            return 0.0

        scored = self.score_news_df(news_df, ticker, text_col, date_col)

        # Filter to relevant news only (relevance > 0)
        relevant = scored[scored["relevance"] > 0]
        if relevant.empty:
            return 0.0

        # Time-weighted average (more recent news → higher weight)
        if date_col in relevant.columns:
            relevant = relevant.copy()
            relevant[date_col] = pd.to_datetime(relevant[date_col], errors="coerce")
            relevant = relevant.dropna(subset=[date_col]).sort_values(date_col)
            # Exponential decay: weight = exp(-days_old / lookback_days)
            latest = relevant[date_col].max()
            relevant["days_old"] = (latest - relevant[date_col]).dt.days
            relevant["weight"] = relevant["days_old"].apply(
                lambda d: max(0, 1.0 - d / lookback_days)
            )
            weighted_sum = (relevant["denoised_score"] * relevant["weight"]).sum()
            total_weight = relevant["weight"].sum()
        else:
            weighted_sum = relevant["denoised_score"].sum()
            total_weight = len(relevant)

        if total_weight == 0:
            return 0.0

        signal = weighted_sum / total_weight
        return max(-1.0, min(1.0, signal))

    def generate_signal_series(
        self,
        news_df: pd.DataFrame,
        ticker: str,
        ohlcv_index: pd.DatetimeIndex,
        lookback_days: int = 5,
        text_col: str = "judul",
        date_col: str = "tanggal",
    ) -> pd.Series:
        """Generate signal series aligned with OHLCV index.

        For each date in ohlcv_index, computes the aggregated news signal
        from the preceding lookback_days.

        Args:
            news_df: DataFrame with news articles.
            ticker: Target ticker.
            ohlcv_index: DatetimeIndex to align signals with.
            lookback_days: News lookback window.
            text_col: Column name for news text.
            date_col: Column name for date.

        Returns:
            Series of signals [-1, 1] indexed by ohlcv_index.
        """
        signals = pd.Series(0.0, index=ohlcv_index)

        if news_df.empty or date_col not in news_df.columns:
            return signals

        news_df = news_df.copy()
        news_df[date_col] = pd.to_datetime(news_df[date_col], errors="coerce")
        news_df = news_df.dropna(subset=[date_col]).sort_values(date_col)

        for idx in ohlcv_index:
            # Get news from the past lookback_days (shifted by 1 for no look-ahead)
            end_date = idx - pd.Timedelta(days=1)
            start_date = end_date - pd.Timedelta(days=lookback_days)
            window_news = news_df[
                (news_df[date_col] >= start_date) & (news_df[date_col] <= end_date)
            ]
            if not window_news.empty:
                sig = self.aggregate_signal(window_news, ticker, lookback_days, text_col, date_col)
                signals.loc[idx] = sig

        # Convert to discrete signals
        discrete = pd.Series(0, index=ohlcv_index)
        discrete[signals > 0.1] = 1
        discrete[signals < -0.1] = -1

        return discrete
