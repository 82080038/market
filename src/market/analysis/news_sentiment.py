"""Unified News Sentiment Analyzer.

Consolidates 3 duplicate implementations into one module with:
- Keyword-based lexicon (EN+ID) with negation handling
- TF-IDF feature extraction for ML pipeline
- Time-decay weighting (exponential decay by news age)
- IndoBERT/FinBERT transformer model (optional, GPU cuda:1)
- Numerical feature output for AI/ML modeling

Replaces:
- scripts/scrape_rss_news.py::compute_sentiment
- scripts/backfill_data.py::classify_sentiment
- src/market/analysis/sentiment.py::SentimentEngine._analyze_news
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np

logger = logging.getLogger(__name__)

# ── Unified Lexicon (EN+ID) ──────────────────────────────────────────────────
# Merged from all 3 previous implementations + expanded financial terms

POSITIVE_WORDS: frozenset[str] = frozenset({
    # Indonesian
    "naik", "unggul", "untung", "laba", "pertumbuhan", "positif", "optimis",
    "beli", "akumulasi", "kenaikan", "melonjak", "menguat", "surplus",
    "dividen", "ekspansi", "peningkatan", "rekomen", "rekomendasi",
    "overweight", "target", "upgrade", "potensi", "peluang", "mendukung",
    "memperkuat", "memperluas", "meraih", "mencapai", "tembus", "rekor",
    "tinggi", "bangkit", "pulih", "tumbuh", "inovasi", "transformatif",
    "strategis", "investasi", "capex", "naiknya", "meroket", "mencatatkan",
    "meningkat", "mendapat", "membeli", "rebound", "capai", "menarik",
    "solid", "stabil", "premi", "menguatkan", "menguat", "menguatnya",
    "positifnya", "menguntungkan", "lancar", "sukses", "menggeliat",
    "merekam", "membukukan", "mencetak", "melonjak", "membesar",
    "mengembangkan", "mempertebal", "menggenjot", "mengakselerasi",
    # English
    "surge", "soar", "rally", "gain", "profit", "growth", "positive",
    "buy", "accumulate", "outperform", "strong", "beat", "exceed",
    "record", "high", "opportunity", "expansion", "dividend", "buyback",
    "breakthrough", "innovation", "support", "hold", "potential",
    "bullish", "upgrade", "overweight", "outperform", "robust",
})

NEGATIVE_WORDS: frozenset[str] = frozenset({
    # Indonesian
    "turun", "rugi", "kerugian", "negatif", "pesimis", "jual", "distribusi",
    "bearish", "penurunan", "anjlok", "melemah", "defisit", "merosot",
    "gagal", "terhenti", "suspensi", "delisting", "pailit", "default",
    "downgrade", "underperform", "risiko", "ancaman", "tekanan",
    "korupsi", "skandal", "pelanggaran", "sanksi", "denda", "gugatan",
    "pembekuan", "perampasan", "terjun", "jatuh", "krisis",
    "konsolidasi", "pelemahan", "tertekan", "memble", "stagnan",
    "lemah", "terpuruk", "terendah", "pelarian", "anjur", "blokir",
    "suspend", "sita", "investigasi", "pemeriksaan", "tertunda",
    "membatalkan", "merugi", "merosot", "tergelincir", "meleset",
    "menurun", "menurunkan", "memburuk", "terjerat", "terjebak",
    "kehilangan", "mengalami", "penurunan", "pelemahan",
    # English
    "plunge", "crash", "drop", "fall", "loss", "negative", "bearish",
    "sell", "distribution", "downgrade", "underperform", "weak", "miss",
    "suspend", "delist", "bankrupt", "default", "scandal", "fraud",
    "corruption", "penalty", "lawsuit", "risk", "threat", "pressure",
    "crisis", "stagnant", "decline", "slump", "cut", "underweight",
})

NEGATION_WORDS: frozenset[str] = frozenset({
    "tidak", "bukan", "jangan", "tak", "nggak", "belum", "tanpa",
    "no", "not", "never", "without",
})

INTENSIFIER_WORDS: frozenset[str] = frozenset({
    "sangat", "amat", "begitu", "betul-betul", "benar-benar",
    "very", "extremely", "highly", "significantly", "substantially",
})

# Financial context words that boost relevance
FINANCIAL_CONTEXT_WORDS: frozenset[str] = frozenset({
    "saham", "emit", "perusahaan", "laporan", "keuangan", "pendapatan",
    "earnings", "revenue", "ebitda", "npm", "roe", "roa", "der",
    "car", "npl", "bumn", "ihsg", "indeks", "sektor", "valas",
    "suku bunga", "bi rate", "inflasi", "gdp", "ekspor", "impor",
    "dividen", "split", "right issue", "ipo", "buyback",
    "broker", "analis", "rating", "target harga", "rekomendasi",
})


@dataclass
class NewsSentimentResult:
    """Result of analyzing a single news item."""

    score: float  # -1.0 (very negative) to 1.0 (very positive)
    label: str  # "positive", "negative", "neutral"
    confidence: float  # 0.0 to 1.0
    positive_count: int
    negative_count: int
    relevance: float  # 0.0 to 1.0 — how relevant to financial markets
    method: str  # "keyword", "transformer"


@dataclass
class NewsFeatureVector:
    """Numerical feature vector from news data for ML pipeline."""

    sentiment_score: float  # weighted avg sentiment (-1 to 1)
    sentiment_momentum: float  # change in sentiment vs previous period
    news_count: int  # total news articles
    news_volume_zscore: float  # z-score of news volume vs 30-day average
    positive_ratio: float  # fraction of positive news
    negative_ratio: float  # fraction of negative news
    neutral_ratio: float  # fraction of neutral news
    sentiment_volatility: float  # std dev of sentiment scores
    avg_relevance: float  # avg financial relevance
    tfidf_top_features: dict[str, float] = field(default_factory=dict)
    decay_weighted_score: float = 0.0  # time-decay weighted sentiment
    days_since_last_news: int = 0


class NewsSentimentAnalyzer:
    """Unified news sentiment analyzer with multiple backends.

    Backends (in priority order):
    1. Transformer (IndoBERT/FinBERT) — if transformers + torch available
    2. Keyword lexicon (EN+ID) with negation — always available

    Features:
    - Keyword matching with word boundary regex
    - Negation handling (3-word window)
    - Intensifier boosting (1.5x weight)
    - Financial relevance scoring
    - TF-IDF feature extraction
    - Time-decay weighting (exponential, half-life=7 days)
    - Numerical feature vector for ML pipeline
    """

    def __init__(
        self,
        method: str = "auto",  # "auto", "keyword", "transformer"
        model_name: str = "indobenchmark/indobert-base-p1",
        device: str | None = None,
        tfidf_max_features: int = 100,
    ) -> None:
        self._method = method
        self._model_name = model_name
        if device is None:
            from market.compute.device import select_device
            device = select_device("nlp_sentiment", data_size=1000)
        self._device = device
        self._tfidf_max_features = tfidf_max_features

        self._transformer = None
        self._tokenizer = None
        self._tfidf = None
        self._tfidf_fitted = False

        if method in ("auto", "transformer"):
            self._try_load_transformer()

    def _try_load_transformer(self) -> bool:
        """Try to load IndoBERT/FinBERT transformer model.

        Falls back to keyword backend if:
        - transformers/torch not installed
        - model fails to load
        - model is a base language model (not fine-tuned for sentiment)
        """
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self._transformer = AutoModelForSequenceClassification.from_pretrained(
                self._model_name,
            )

            # Detect base language models (not fine-tuned for sentiment).
            # Base models have default id2label like {0: 'LABEL_0', 1: 'LABEL_1'}
            # and random classification heads → meaningless sentiment scores.
            id2label = getattr(self._transformer.config, "id2label", {})
            is_base_model = all(
                str(v).startswith("LABEL_") for v in id2label.values()
            ) if id2label else True

            if is_base_model:
                logger.warning(
                    "NewsSentiment: %s appears to be a base model (not fine-tuned "
                    "for sentiment) — falling back to keyword backend",
                    self._model_name,
                )
                self._transformer = None
                self._tokenizer = None
                return False

            if torch.cuda.is_available() and self._device.startswith("cuda"):
                dev = torch.device(self._device)
                self._transformer = self._transformer.to(dev)
                logger.info("NewsSentiment: transformer loaded on %s", self._device)
            else:
                logger.info("NewsSentiment: transformer loaded on CPU")
            return True
        except ImportError:
            logger.info("NewsSentiment: transformers/torch not installed, using keyword backend")
            return False
        except Exception as e:
            logger.warning("NewsSentiment: failed to load transformer: %s", e)
            return False

    @property
    def active_method(self) -> str:
        """Which backend is actually active."""
        if self._transformer is not None:
            return "transformer"
        return "keyword"

    # ── Single text analysis ──────────────────────────────────────────────

    def analyze_text(self, title: str, body: str | None = None) -> NewsSentimentResult:
        """Analyze a single news text.

        Args:
            title: News headline.
            body: News body text (optional, concatenated with title).

        Returns:
            NewsSentimentResult with score, label, confidence, relevance.
        """
        text = (title or "").lower()
        if body:
            text += " " + body.lower()
        if not text.strip():
            return NewsSentimentResult(
                score=0.0, label="neutral", confidence=0.0,
                positive_count=0, negative_count=0, relevance=0.0,
                method="keyword",
            )

        if self._transformer is not None:
            return self._analyze_transformer(text, title)

        return self._analyze_keyword(text)

    def _analyze_keyword(self, text: str) -> NewsSentimentResult:
        """Keyword-based sentiment with negation + intensifier handling."""
        words = re.findall(r"\b\w+\b", text)
        if not words:
            return NewsSentimentResult(
                score=0.0, label="neutral", confidence=0.0,
                positive_count=0, negative_count=0, relevance=0.0,
                method="keyword",
            )

        positive = 0
        negative = 0
        negation_window = 3  # words after negation are affected

        for i, word in enumerate(words):
            # Check negation within window
            negated = False
            intensifier = False
            for j in range(max(0, i - negation_window), i):
                if words[j] in NEGATION_WORDS:
                    negated = True
                if words[j] in INTENSIFIER_WORDS:
                    intensifier = True

            weight = 1.5 if intensifier else 1.0

            if word in POSITIVE_WORDS:
                if negated:
                    negative += weight
                else:
                    positive += weight
            elif word in NEGATIVE_WORDS:
                if negated:
                    positive += weight
                else:
                    negative += weight

        total = positive + negative
        if total == 0:
            return NewsSentimentResult(
                score=0.0, label="neutral", confidence=0.0,
                positive_count=0, negative_count=0,
                relevance=self._compute_relevance(text),
                method="keyword",
            )

        score = (positive - negative) / total
        confidence = min(1.0, total / 10.0)  # more keywords → higher confidence
        label = self._score_to_label(score)

        return NewsSentimentResult(
            score=round(score, 4),
            label=label,
            confidence=round(confidence, 4),
            positive_count=int(positive),
            negative_count=int(negative),
            relevance=self._compute_relevance(text),
            method="keyword",
        )

    def _analyze_transformer(self, text: str, title: str) -> NewsSentimentResult:
        """Transformer-based sentiment (IndoBERT/FinBERT)."""
        import torch

        # Truncate to model max length
        encoded = self._tokenizer(
            text[:512],
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )

        device = next(self._transformer.parameters()).device
        encoded = {k: v.to(device) for k, v in encoded.items()}

        with torch.no_grad():
            outputs = self._transformer(**encoded)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)

        # Assume 3-class: [negative, neutral, positive]
        if probs.shape[-1] == 3:
            neg_p, neu_p, pos_p = probs[0].cpu().tolist()
            score = pos_p - neg_p  # -1 to 1
            confidence = max(pos_p, neg_p, neu_p)
        elif probs.shape[-1] == 2:
            neg_p, pos_p = probs[0].cpu().tolist()
            score = pos_p - neg_p
            confidence = max(pos_p, neg_p)
        else:
            # Fallback: use argmax
            pred = probs[0].argmax().item()
            score = (pred - 1) / max(1, probs.shape[-1] - 2)
            confidence = probs[0][pred].item()

        return NewsSentimentResult(
            score=round(float(score), 4),
            label=self._score_to_label(score),
            confidence=round(float(confidence), 4),
            positive_count=1 if score > 0.15 else 0,
            negative_count=1 if score < -0.15 else 0,
            relevance=self._compute_relevance(text),
            method="transformer",
        )

    # ── Batch analysis with time-decay ────────────────────────────────────

    def analyze_batch(
        self,
        items: list[dict],
        reference_date: date | None = None,
        half_life_days: float = 7.0,
    ) -> list[NewsSentimentResult]:
        """Analyze a batch of news items.

        Args:
            items: List of dicts with 'title', 'body' (optional), 'date' (optional).
            reference_date: Date for time-decay calculation (default: today).
            half_life_days: Half-life for exponential decay (default: 7 days).

        Returns:
            List of NewsSentimentResult (same order as input).
        """
        results = []
        for item in items:
            title = item.get("title", item.get("headline", ""))
            body = item.get("body", item.get("summary"))
            result = self.analyze_text(title, body)
            results.append(result)
        return results

    def compute_time_decay_weight(
        self,
        news_date: date,
        reference_date: date | None = None,
        half_life_days: float = 7.0,
    ) -> float:
        """Exponential time-decay weight.

        Weight = 0.5 ^ ((ref - news_date) / half_life)

        Recent news gets weight ~1.0, old news decays exponentially.
        """
        ref = reference_date or date.today()
        age_days = max(0, (ref - news_date).days)
        return math.pow(0.5, age_days / half_life_days)

    def weighted_sentiment(
        self,
        items: list[dict],
        reference_date: date | None = None,
        half_life_days: float = 7.0,
    ) -> float:
        """Compute time-decay weighted sentiment score.

        Args:
            items: List of dicts with 'title', 'body', 'date'.
            reference_date: Reference date for decay.
            half_life_days: Half-life for decay.

        Returns:
            Weighted sentiment score (-1.0 to 1.0).
        """
        if not items:
            return 0.0

        ref = reference_date or date.today()
        results = self.analyze_batch(items, ref, half_life_days)

        total_weight = 0.0
        weighted_sum = 0.0

        for item, result in zip(items, results, strict=False):
            news_date = item.get("date")
            if news_date is None:
                weight = 1.0
            else:
                if isinstance(news_date, str):
                    try:
                        news_date = datetime.fromisoformat(news_date).date()
                    except ValueError:
                        news_date = ref
                weight = self.compute_time_decay_weight(news_date, ref, half_life_days)

            # Multiply by confidence for more reliable signals
            w = weight * (0.5 + result.confidence * 0.5)
            total_weight += w
            weighted_sum += result.score * w

        if total_weight == 0:
            return 0.0
        return round(weighted_sum / total_weight, 4)

    # ── TF-IDF feature extraction ─────────────────────────────────────────

    def fit_tfidf(self, texts: list[str]) -> None:
        """Fit TF-IDF vectorizer on corpus of news texts."""
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._tfidf = TfidfVectorizer(
            max_features=self._tfidf_max_features,
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True,
        )
        self._tfidf.fit(texts)
        self._tfidf_fitted = True
        logger.info("NewsSentiment: TF-IDF fitted on %d texts, %d features",
                     len(texts), len(self._tfidf.vocabulary_))

    def extract_tfidf_features(self, text: str) -> dict[str, float]:
        """Extract TF-IDF feature vector for a single text.

        Returns:
            Dict of {term: tfidf_weight} for non-zero features.
        """
        if not self._tfidf_fitted or self._tfidf is None:
            return {}

        vec = self._tfidf.transform([text])
        feature_names = self._tfidf.get_feature_names_out()
        cols = vec.nonzero()[1]
        return {feature_names[c]: float(vec[0, c]) for c in cols}

    # ── Full feature vector for ML pipeline ───────────────────────────────

    def extract_features(
        self,
        items: list[dict],
        previous_items: list[dict] | None = None,
        reference_date: date | None = None,
        half_life_days: float = 7.0,
        volume_lookback_days: int = 30,
    ) -> NewsFeatureVector:
        """Extract full numerical feature vector from news data for ML.

        Args:
            items: Current period news items (list of dicts with title, body, date).
            previous_items: Previous period items for momentum calculation.
            reference_date: Reference date.
            half_life_days: Time-decay half-life.
            volume_lookback_days: Lookback for volume z-score.

        Returns:
            NewsFeatureVector with all numerical features.
        """
        ref = reference_date or date.today()

        if not items:
            return NewsFeatureVector(
                sentiment_score=0.0, sentiment_momentum=0.0,
                news_count=0, news_volume_zscore=0.0,
                positive_ratio=0.0, negative_ratio=0.0, neutral_ratio=1.0,
                sentiment_volatility=0.0, avg_relevance=0.0,
                decay_weighted_score=0.0, days_since_last_news=999,
            )

        results = self.analyze_batch(items, ref, half_life_days)
        scores = [r.score for r in results]
        labels = [r.label for r in results]
        relevances = [r.relevance for r in results]

        # Basic stats
        news_count = len(items)
        positive_ratio = labels.count("positive") / news_count
        negative_ratio = labels.count("negative") / news_count
        neutral_ratio = labels.count("neutral") / news_count
        sentiment_volatility = float(np.std(scores)) if len(scores) > 1 else 0.0
        avg_relevance = sum(relevances) / news_count if relevances else 0.0

        # Time-decay weighted score
        decay_score = self.weighted_sentiment(items, ref, half_life_days)

        # Simple average sentiment
        sentiment_score = sum(scores) / news_count

        # Momentum: current vs previous period
        if previous_items:
            prev_results = self.analyze_batch(previous_items, ref, half_life_days)
            prev_score = sum(r.score for r in prev_results) / len(prev_results) if prev_results else 0.0
            sentiment_momentum = sentiment_score - prev_score
        else:
            sentiment_momentum = 0.0

        # News volume z-score (vs lookback period)
        # If we have enough history, compute z-score; otherwise 0
        # Z-score: (today_count - avg) / std — simplified
        news_volume_zscore = 0.0  # Would need historical daily counts

        # Days since last news
        news_dates = [
            self._parse_date(item.get("date", ""), ref)
            for item in items
        ]
        if news_dates:
            latest = max(news_dates)
            days_since = max(0, (ref - latest).days)
        else:
            days_since = 999

        # TF-IDF top features (if fitted)
        tfidf_features = {}
        if self._tfidf_fitted and self._tfidf is not None:
            all_text = " ".join(
                (item.get("title", "") + " " + item.get("body", "")).lower()
                for item in items
            )
            tfidf_features = self.extract_tfidf_features(all_text)
            # Keep only top 10
            if tfidf_features:
                top = sorted(tfidf_features.items(), key=lambda x: -x[1])[:10]
                tfidf_features = dict(top)

        return NewsFeatureVector(
            sentiment_score=round(sentiment_score, 4),
            sentiment_momentum=round(sentiment_momentum, 4),
            news_count=news_count,
            news_volume_zscore=round(news_volume_zscore, 4),
            positive_ratio=round(positive_ratio, 4),
            negative_ratio=round(negative_ratio, 4),
            neutral_ratio=round(neutral_ratio, 4),
            sentiment_volatility=round(sentiment_volatility, 4),
            avg_relevance=round(avg_relevance, 4),
            tfidf_top_features=tfidf_features,
            decay_weighted_score=decay_score,
            days_since_last_news=days_since,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _score_to_label(score: float) -> str:
        if score > 0.15:
            return "positive"
        elif score < -0.15:
            return "negative"
        return "neutral"

    @staticmethod
    def _compute_relevance(text: str) -> float:
        """Compute financial relevance score (0-1) based on context words."""
        if not text:
            return 0.0
        words = set(re.findall(r"\b\w+\b", text))
        hits = len(words & FINANCIAL_CONTEXT_WORDS)
        # Also check multi-word phrases
        for phrase in FINANCIAL_CONTEXT_WORDS:
            if " " in phrase and phrase in text:
                hits += 1
        # Normalize: 3+ hits → high relevance
        return min(1.0, hits / 5.0)

    @staticmethod
    def _parse_date(date_val: str | date | None, fallback: date) -> date:
        """Parse date from various formats."""
        if date_val is None or date_val == "":
            return fallback
        if isinstance(date_val, date):
            return date_val
        if isinstance(date_val, datetime):
            return date_val.date()
        for fmt in ("%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(date_val, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(date_val).date()
        except (ValueError, TypeError):
            return fallback


# ── Convenience functions (drop-in replacements for old implementations) ─────

_analyzer_instance: NewsSentimentAnalyzer | None = None


def get_analyzer(method: str = "auto") -> NewsSentimentAnalyzer:
    """Get singleton analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = NewsSentimentAnalyzer(method=method)
    return _analyzer_instance


def compute_sentiment(title: str, body: str | None = None) -> tuple[float, str]:
    """Drop-in replacement for scrape_rss_news.py::compute_sentiment.

    Returns:
        Tuple of (sentiment_score, sentiment_label).
    """
    analyzer = get_analyzer()
    result = analyzer.analyze_text(title, body)
    return result.score, result.label


def classify_sentiment(text: str) -> tuple[float, str]:
    """Drop-in replacement for backfill_data.py::classify_sentiment.

    Returns:
        Tuple of (sentiment_score, impact_label).
    """
    analyzer = get_analyzer()
    result = analyzer.analyze_text(text)
    return result.score, result.label


def analyze_news_texts(texts: list[str]) -> float:
    """Drop-in replacement for SentimentEngine._analyze_news.

    Returns:
        Sentiment score 0-100 (50 = neutral).
    """
    if not texts:
        return 50.0
    analyzer = get_analyzer()
    results = [analyzer.analyze_text(t) for t in texts]
    # Convert -1..1 to 0..100 scale (50 = neutral)
    avg = sum(r.score for r in results) / len(results)
    return round(50.0 + avg * 50.0, 2)
