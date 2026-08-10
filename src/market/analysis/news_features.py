"""News Feature Provider for ML pipeline.

Extracts numerical features from news_sentiment data for use in
LightGBM and other ML models. Provides features as a pandas DataFrame
ready to merge with OHLCV-based features.

Features produced:
- news_sentiment_score: time-decay weighted sentiment (-1 to 1)
- news_sentiment_momentum: change vs previous period
- news_count: number of articles in lookback
- news_positive_ratio: fraction positive
- news_negative_ratio: fraction negative
- news_neutral_ratio: fraction neutral
- news_sentiment_volatility: std dev of scores
- news_avg_relevance: avg financial relevance
- news_days_since_last: days since last article
- news_tfidf_*: top TF-IDF features (if fitted)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from market.analysis.news_sentiment import NewsSentimentAnalyzer

logger = logging.getLogger(__name__)


class NewsFeatureProvider:
    """Extract numerical news features for ML pipeline.

    Usage:
        provider = NewsFeatureProvider()
        features = provider.get_features(ticker, session, as_of=date)
        # Returns dict of feature_name → float
    """

    def __init__(
        self,
        lookback_days: int = 30,
        half_life_days: float = 7.0,
        tfidf_max_features: int = 50,
    ) -> None:
        self.lookback_days = lookback_days
        self.half_life_days = half_life_days
        self._analyzer = NewsSentimentAnalyzer(tfidf_max_features=tfidf_max_features)
        self._tfidf_fitted = False

    def get_features(
        self,
        ticker: str,
        session,
        as_of: date,
        previous_period_days: int = 30,
    ) -> dict[str, float]:
        """Extract news features for a ticker as of a given date.

        Args:
            ticker: Stock ticker (e.g. "BBCA.JK").
            session: SQLAlchemy session.
            as_of: Cutoff date (no look-ahead).
            previous_period_days: Days for previous period (momentum calculation).

        Returns:
            Dict of feature_name → float, ready for ML pipeline.
        """
        from sqlalchemy import select

        lookback = as_of - timedelta(days=self.lookback_days)
        prev_start = as_of - timedelta(days=self.lookback_days + previous_period_days)

        # Fetch current period news
        current_items = self._fetch_news(session, ticker, lookback, as_of)
        previous_items = self._fetch_news(session, ticker, prev_start, lookback)

        if not current_items:
            return self._empty_features()

        # Extract full feature vector
        fv = self._analyzer.extract_features(
            current_items,
            previous_items=previous_items,
            reference_date=as_of,
            half_life_days=self.half_life_days,
        )

        features = {
            "news_sentiment_score": fv.sentiment_score,
            "news_sentiment_momentum": fv.sentiment_momentum,
            "news_count": float(fv.news_count),
            "news_positive_ratio": fv.positive_ratio,
            "news_negative_ratio": fv.negative_ratio,
            "news_neutral_ratio": fv.neutral_ratio,
            "news_sentiment_volatility": fv.sentiment_volatility,
            "news_avg_relevance": fv.avg_relevance,
            "news_days_since_last": float(fv.days_since_last_news),
            "news_decay_weighted_score": fv.decay_weighted_score,
        }

        # Add TF-IDF features (if fitted)
        for term, weight in fv.tfidf_top_features.items():
            safe_name = f"news_tfidf_{term.replace(' ', '_')}"
            features[safe_name] = weight

        return features

    def get_features_batch(
        self,
        tickers: list[str],
        session,
        as_of: date,
    ) -> pd.DataFrame:
        """Extract news features for multiple tickers.

        Args:
            tickers: List of ticker symbols.
            session: SQLAlchemy session.
            as_of: Cutoff date.

        Returns:
            DataFrame with ticker as index, features as columns.
        """
        rows = []
        for ticker in tickers:
            try:
                feats = self.get_features(ticker, session, as_of)
                feats["ticker"] = ticker
                rows.append(feats)
            except Exception as e:
                logger.debug("News features failed for %s: %s", ticker, e)
                feats = self._empty_features()
                feats["ticker"] = ticker
                rows.append(feats)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index("ticker")
        return df

    def fit_tfidf_on_corpus(self, session, limit: int = 5000) -> None:
        """Fit TF-IDF on existing news corpus for feature extraction.

        Call this once before using TF-IDF features.
        """
        from sqlalchemy import select

        try:
            from market.db.models import NewsSentiment

            rows = session.execute(
                select(NewsSentiment.headline)
                .where(NewsSentiment.headline.isnot(None))
                .limit(limit)
            ).scalars().all()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            # Fallback to legacy news table
            from market.db.models import News

            rows = session.execute(
                select(News.headline)
                .where(News.headline.isnot(None))
                .limit(limit)
            ).scalars().all()

        if rows:
            self._analyzer.fit_tfidf(list(rows))
            self._tfidf_fitted = True
            logger.info("NewsFeatureProvider: TF-IDF fitted on %d headlines", len(rows))

    @staticmethod
    def _fetch_news(session, ticker: str, start: date, end: date) -> list[dict]:
        """Fetch news items from DB within date range."""
        from sqlalchemy import select

        # Try PostgreSQL news_sentiment table first
        try:
            from market.db.models import NewsSentiment

            rows = session.execute(
                select(
                    NewsSentiment.headline,
                    NewsSentiment.sentiment_score,
                    NewsSentiment.date,
                )
                .where(NewsSentiment.ticker == ticker)
                .where(NewsSentiment.date >= start)
                .where(NewsSentiment.date <= end)
                .where(NewsSentiment.sentiment_score.isnot(None))
                .order_by(NewsSentiment.date.desc())
            ).all()

            if rows:
                return [
                    {
                        "title": r[0] or "",
                        "date": r[2] if isinstance(r[2], date) else date.today(),
                        "score": float(r[1]),
                    }
                    for r in rows
                ]
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass

        # Fallback: legacy news table
        try:
            from market.db.models import News

            rows = session.execute(
                select(News.headline, News.sentiment, News.published_at)
                .where(News.entities.ilike(f"%{ticker}%"))
                .where(News.sentiment.isnot(None))
                .order_by(News.published_at.desc())
                .limit(100)
            ).all()

            items = []
            for r in rows:
                pub = r[2]
                if isinstance(pub, str):
                    try:
                        pub = date.fromisoformat(pub[:10])
                    except ValueError:
                        pub = date.today()
                elif isinstance(pub, type(None)):
                    pub = date.today()

                if start <= pub <= end:
                    items.append({
                        "title": r[0] or "",
                        "date": pub,
                        "score": float(r[1]) if r[1] is not None else 0.0,
                    })
            return items
        except Exception:
            return []

    @staticmethod
    def _empty_features() -> dict[str, float]:
        """Return empty feature dict when no news data available."""
        return {
            "news_sentiment_score": 0.0,
            "news_sentiment_momentum": 0.0,
            "news_count": 0.0,
            "news_positive_ratio": 0.0,
            "news_negative_ratio": 0.0,
            "news_neutral_ratio": 1.0,
            "news_sentiment_volatility": 0.0,
            "news_avg_relevance": 0.0,
            "news_days_since_last": 999.0,
            "news_decay_weighted_score": 0.0,
        }
