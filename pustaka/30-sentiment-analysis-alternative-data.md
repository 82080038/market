# Sentiment Analysis & Alternative Data

> **Tujuan:** Dokumen ini adalah referensi definitif untuk sentiment analysis dan alternative data dalam sistem trading — dari NLP untuk teks Bahasa Indonesia, social media scraping, foreign flow sebagai sentiment proxy, Google Trends, news classification, hingga integrasi dengan Decision Engine — dengan fokus pada pasar modal Indonesia (IDX).

---

## Daftar Isi

1. [Sentiment Analysis Overview](#1-sentiment-analysis-overview)
2. [NLP untuk Bahasa Indonesia](#2-nlp-untuk-bahasa-indonesia)
3. [News Sentiment](#3-news-sentiment)
4. [Social Media Sentiment](#4-social-media-sentiment)
5. [Foreign Flow sebagai Sentiment](#5-foreign-flow-sebagai-sentiment)
6. [Google Trends](#6-google-trends)
7. [Broker Flow Analysis](#7-broker-flow-analysis)
8. [Fear & Greed Index](#8-fear--greed-index)
9. [Alternative Data Sources](#9-alternative-data-sources)
10. [Integrasi dengan Decision Engine](#10-integrasi-dengan-decision-engine)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Sentiment Analysis Overview

### 1.1 Mengapa Sentiment Penting

Harga saham dipengaruhi oleh dua faktor:
- **Fundamental:** Nilai intrinsik perusahaan (earnings, cash flow, growth)
- **Sentiment:** Persepsi kolektif pasar (fear, greed, narrative)

Sentiment dapat memprediksi pergerakan harga jangka pendek sebelum tercermin di fundamental.

### 1.2 Tipe Sentiment Data

| Tipe | Source | Frequency | Latency | Noise |
|------|--------|-----------|---------|-------|
| **News sentiment** | RSS, media | Real-time | Menit-jam | Medium |
| **Social media** | Reddit, X | Real-time | Detik-menit | Tinggi |
| **Foreign flow** | IDX scraper | Daily EOD | 1 hari | Rendah |
| **Broker flow** | IDX scraper | Daily EOD | 1 hari | Rendah |
| **Search trends** | Google Trends | Weekly | 1 minggu | Tinggi |
| **Fear & Greed** | Composite | Daily | 1 hari | Rendah |
| **Insider trading** | IDX disclosure | Event | 1-3 hari | Rendah |

### 1.3 Sentiment Pipeline

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Collect │──▶│ Preprocess│──▶│  Score   │──▶│ Aggregate│──▶│  Feed to │
│  (RSS,   │   │ (Clean,  │   │ (NLP,    │   │ (Per     │   │  Decision│
│   Social,│   │  Tokenize)│   │  Model)  │   │  Ticker) │   │  Engine  │
│   Flow)  │   │          │   │          │   │          │   │          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

---

## 2. NLP untuk Bahasa Indonesia

### 2.1 Tantangan NLP Bahasa Indonesia

| Tantangan | Deskripsi | Solusi |
|-----------|-----------|--------|
| **Limited models** | Lebih sedikit pre-trained model vs English | IndoBERT, IndoNLU |
| **Slang & code-mixing** | "saham naik banget", "market bullish nih" | Custom normalization |
| **Domain-specific** | Istilah finansial Indonesia | Custom vocabulary |
| **Code-switching** | Mix Indonesia-English: "BBRI bullish hari ini" | Bilingual approach |
| **Sarcasm** | "Wah, sahamnya 'naik' banget" (ironis) | Context analysis |

### 2.2 Pre-trained Models

| Model | Provider | Size | Performance | Use Case |
|-------|----------|------|-------------|----------|
| **IndoBERT** | IndoNLU | 110M params | Good | General NLP tasks |
| **IndoBERTweet** | IndoNLU | 110M | Good for social | Twitter/socmed |
| **mBERT** | Google | 110M | Moderate | Multilingual |
| **XLM-R** | Facebook | 550M | Good | Multilingual |
| **GPT-4/Claude** | API | Large | Excellent | Zero-shot sentiment |

### 2.3 Text Preprocessing

```python
import re
import string

def preprocess_indonesian_text(text: str) -> str:
    """Preprocess Indonesian text for sentiment analysis."""
    # Lowercase
    text = text.lower()
    
    # Remove URLs
    text = re.sub(r'http\S+|www\S+', '', text)
    
    # Remove mentions and hashtags (keep hashtag text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#(\w+)', r'\1', text)
    
    # Remove punctuation (keep ! and ? for sentiment)
    text = text.translate(str.maketrans('', '', string.punctuation.replace('!?', '')))
    
    # Normalize common slang
    slang_map = {
        "naik banget": "sangat naik",
        "turun banget": "sangat turun",
        "bullish banget": "sangat bullish",
        "bearish banget": "sangat bearish",
        "gpp": "tidak apa apa",
        "mantul": "mantap betul",
        "cuantik": "cantik",
        "diskon": "turun",
        "discount": "turun",
    }
    for slang, formal in slang_map.items():
        text = text.replace(slang, formal)
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    return text
```

### 2.4 Sentiment Scoring

```python
class SentimentScorer:
    """Sentiment scoring for Indonesian financial text."""
    
    FINANCIAL_POSITIVE = [
        "naik", "bullish", "untung", "profit", "rugi" "dividen",
        "akumulasi", "beli", "hold", "support", "breakout",
        "rebound", "rally", "gain", "positif", "tumbuh",
        "earnings", "cuan", "mantap", "bagus",
    ]
    
    FINANCIAL_NEGATIVE = [
        "turun", "bearish", "rugi", "loss", "jual", "sell",
        "distribusi", "breakdown", "drop", "fall", "negatif",
        "turun", "merosot", "anjlok", "korban", "bocor",
        "scam", "fraud", "manipulasi", "auto reject",
    ]
    
    def score(self, text: str) -> dict:
        """Score sentiment of text (-1 to +1)."""
        text_lower = text.lower()
        
        pos_count = sum(1 for word in self.FINANCIAL_POSITIVE if word in text_lower)
        neg_count = sum(1 for word in self.FINANCIAL_NEGATIVE if word in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            score = 0.0
        else:
            score = (pos_count - neg_count) / total
        
        return {
            "sentiment_score": score,
            "sentiment_label": "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral",
            "positive_signals": pos_count,
            "negative_signals": neg_count,
            "confidence": min(total / 5, 1.0),  # more keywords = higher confidence
        }
```

### 2.5 Using IndoBERT (Advanced)

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class IndoBERTSentiment:
    """IndoBERT-based sentiment classifier."""
    
    def __init__(self, model_name="indobenchmark/indobert-base-p1"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name, num_labels=3  # positive, neutral, negative
        )
    
    def predict(self, text: str) -> dict:
        """Predict sentiment using IndoBERT."""
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        outputs = self.model(**inputs)
        probs = outputs.logits.softmax(dim=-1)[0]
        
        labels = ["negative", "neutral", "positive"]
        predicted_idx = probs.argmax().item()
        
        return {
            "label": labels[predicted_idx],
            "confidence": float(probs[predicted_idx]),
            "probabilities": {labels[i]: float(probs[i]) for i in range(3)},
        }
```

---

## 3. News Sentiment

### 3.1 RSS Feed Sources (Indonesia)

| Source | URL | Coverage | Quality |
|--------|-----|----------|---------|
| **Bisnis.com** | `https://www.bisnis.com/rss` | Market, finance | High |
| **Kontan** | `https://www.kontan.co.id/rss` | Market, finance | High |
| **CNBC Indonesia** | `https://www.cnbcindonesia.com/rss` | Market, finance | High |
| **Investor Daily** | `https://investor.id/rss` | Market | High |
| **IDX channel** | `https://www.idxchannel.com/rss` | Market | Medium |
| **Tempo Bisnis** | `https://bisnis.tempo.co/rss` | General business | Medium |
| **Detik Finance** | `https://finance.detik.com/rss` | General finance | Medium |

### 3.2 News Pipeline

```python
import feedparser

class NewsCollector:
    """Collect and process news from RSS feeds."""
    
    FEEDS = {
        "bisnis": "https://www.bisnis.com/rss/market",
        "kontan": "https://www.kontan.co.id/rss/market",
        "cnbc": "https://www.cnbcindonesia.com/rss/market",
    }
    
    def collect(self) -> list:
        """Collect latest news from all feeds."""
        all_news = []
        
        for source, url in self.FEEDS.items():
            feed = feedparser.parse(url)
            
            for entry in feed.entries:
                news_item = {
                    "source": source,
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "content": self._extract_content(entry),
                }
                
                # Extract tickers mentioned
                news_item["tickers"] = self._extract_tickers(news_item["title"] + " " + news_item["summary"])
                
                # Score sentiment
                news_item["sentiment"] = self.scorer.score(news_item["title"] + " " + news_item["summary"])
                
                all_news.append(news_item)
        
        return all_news
    
    def _extract_tickers(self, text: str) -> list:
        """Extract ticker symbols mentioned in text."""
        # Common IDX tickers
        import re
        tickers = re.findall(r'\b([A-Z]{4})\b', text)
        return list(set(tickers))
```

### 3.3 News Aggregation per Ticker

```python
def aggregate_news_sentiment(news_items: list, ticker: str, window_days: int = 7) -> dict:
    """Aggregate news sentiment for a specific ticker."""
    from datetime import datetime, timedelta
    
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    
    relevant = [
        n for n in news_items
        if ticker in n.get("tickers", [])
        and datetime.strptime(n["published"][:25], "%a, %d %b %Y %H:%M:%S") > cutoff
    ]
    
    if not relevant:
        return {"sentiment_score": 0, "n_articles": 0, "label": "neutral"}
    
    scores = [n["sentiment"]["sentiment_score"] for n in relevant]
    
    return {
        "sentiment_score": np.mean(scores),
        "sentiment_std": np.std(scores),
        "n_articles": len(relevant),
        "label": "positive" if np.mean(scores) > 0.1 else "negative" if np.mean(scores) < -0.1 else "neutral",
        "latest_headline": relevant[0]["title"],
        "latest_date": relevant[0]["published"],
    }
```

---

## 4. Social Media Sentiment

### 4.1 Reddit (r/Saham)

```python
import praw

class RedditSentiment:
    """Collect sentiment from Reddit r/Saham."""
    
    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self.scorer = SentimentScorer()
    
    def collect(self, subreddit="Saham", limit=100) -> list:
        """Collect posts and comments from subreddit."""
        results = []
        
        subreddit = self.reddit.subreddit(subreddit)
        
        for post in subreddit.hot(limit=limit):
            item = {
                "platform": "reddit",
                "title": post.title,
                "body": post.selftext[:500],
                "score": post.score,
                "upvote_ratio": post.upvote_ratio,
                "created_utc": post.created_utc,
                "tickers": self._extract_tickers(post.title + " " + post.selftext),
                "sentiment": self.scorer.score(post.title + " " + post.selftext[:500]),
            }
            results.append(item)
        
        return results
```

### 4.2 X (Twitter)

```python
# Note: X API requires authentication and has rate limits
# Consider using tweepy or snscrape for historical data

class XSentiment:
    """Collect sentiment from X/Twitter."""
    
    KEYWORDS = [
        "#saham", "#IHSG", "#BursaEfekIndonesia",
        "#trading", "#investasi", "#BBRI", "#BBCA",
    ]
    
    def collect(self, keywords: list = None, limit: int = 100) -> list:
        """Collect tweets matching keywords."""
        # Implementation depends on API access
        # Using tweepy or similar library
        pass
```

### 4.3 Social Media Score Normalization

```python
def normalize_social_sentiment(items: list, ticker: str) -> dict:
    """Normalize social media sentiment to 0-100 score."""
    relevant = [i for i in items if ticker in i.get("tickers", [])]
    
    if not relevant:
        return {"score": 50, "n_mentions": 0, "label": "neutral"}
    
    # Weight by engagement (score/upvotes)
    weighted_scores = []
    for item in relevant:
        weight = np.log1p(item.get("score", 1))  # log scale to reduce outlier impact
        weighted_scores.append(item["sentiment"]["sentiment_score"] * weight)
    
    total_weight = sum(np.log1p(i.get("score", 1)) for i in relevant)
    avg_sentiment = sum(weighted_scores) / total_weight if total_weight > 0 else 0
    
    # Convert to 0-100 scale (0=negative, 50=neutral, 100=positive)
    score = 50 + avg_sentiment * 50
    
    return {
        "score": max(0, min(100, score)),
        "n_mentions": len(relevant),
        "label": "positive" if score > 55 else "negative" if score < 45 else "neutral",
        "avg_engagement": np.mean([i.get("score", 0) for i in relevant]),
    }
```

---

## 5. Foreign Flow sebagai Sentiment

### 5.1 Konsep

Di IDX, foreign flow adalah salah satu sentiment indicator terkuat:
- **Foreign net buy** → bullish sentiment (konvensi pasar Indonesia)
- **Foreign net sell** → bearish sentiment
- **Sustained foreign buying** → akumulasi institusional
- **Sudden foreign outflow** → panic/risk-off

### 5.2 Foreign Flow Scoring

```python
def foreign_flow_sentiment(flow_data: pd.DataFrame, ticker: str, window: int = 20) -> dict:
    """Compute foreign flow sentiment score."""
    ticker_flow = flow_data[flow_data["ticker"] == ticker].tail(window)
    
    if ticker_flow.empty:
        return {"score": 50, "label": "neutral", "n_days": 0}
    
    # Net flow
    net_flow = ticker_flow["foreign_net"].sum()
    avg_daily_net = ticker_flow["foreign_net"].mean()
    
    # Net buy days ratio
    net_buy_days = (ticker_flow["foreign_net"] > 0).sum()
    buy_ratio = net_buy_days / len(ticker_flow)
    
    # Trend (recent vs older)
    recent = ticker_flow["foreign_net"].tail(5).mean()
    older = ticker_flow["foreign_net"].head(5).mean()
    trend = recent - older
    
    # Score: 0-100 (50 = neutral)
    # Buy ratio contributes 60%, trend contributes 40%
    score = 50 + (buy_ratio - 0.5) * 60 + np.sign(trend) * 10
    
    return {
        "score": max(0, min(100, score)),
        "label": "positive" if score > 55 else "negative" if score < 45 else "neutral",
        "total_net_flow": net_flow,
        "avg_daily_net": avg_daily_net,
        "net_buy_days": int(net_buy_days),
        "net_sell_days": int(len(ticker_flow) - net_buy_days),
        "trend": "increasing" if trend > 0 else "decreasing" if trend < 0 else "flat",
        "n_days": len(ticker_flow),
    }
```

### 5.3 Foreign Flow Signal Strength

```python
def foreign_flow_signal_strength(flow_data: pd.DataFrame, ticker: str) -> dict:
    """Assess signal strength of foreign flow."""
    flow = foreign_flow_sentiment(flow_data, ticker)
    
    # Strong signal: consistent + large magnitude
    avg_net = abs(flow["avg_daily_net"])
    consistency = abs(flow["net_buy_days"] - flow["n_days"] / 2) / (flow["n_days"] / 2)
    
    strength = "weak"
    if consistency > 0.7 and avg_net > 1e9:  # > Rp 1B average
        strength = "strong"
    elif consistency > 0.5 and avg_net > 5e8:
        strength = "moderate"
    
    return {
        **flow,
        "signal_strength": strength,
        "consistency": consistency,
    }
```

---

## 6. Google Trends

### 6.1 Konsep

Google Trends menunjukkan minat pencarian untuk keyword tertentu dari waktu ke waktu. Dapat mengindikasikan:
- **Rising interest** → meningkatnya perhatian publik
- **Search spike** → event-driven interest (news, earnings)
- **Sustained high search** → popularitas jangka panjang

### 6.2 Implementation

```python
from pytrends.request import TrendReq

class GoogleTrendsCollector:
    """Collect Google Trends data for trading-related keywords."""
    
    def __init__(self):
        self.pytrends = TrendReq(hl='id-ID', tz=420)  # Indonesia, UTC+7
    
    def get_trends(self, keywords: list, timeframe: str = "today 3-m") -> pd.DataFrame:
        """Get search interest for keywords."""
        self.pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo='ID')
        return self.pytrends.interest_over_time()
    
    def get_ticker_trends(self, ticker_name: str) -> dict:
        """Get search trend for a stock name."""
        df = self.get_trends([ticker_name], timeframe="today 3-m")
        
        if df.empty:
            return {"trend_score": 50, "trend_direction": "flat"}
        
        current = df[ticker_name].iloc[-1]
        avg = df[ticker_name].mean()
        recent_avg = df[ticker_name].tail(4).mean()  # last 4 weeks
        
        direction = "rising" if recent_avg > avg * 1.2 else "falling" if recent_avg < avg * 0.8 else "flat"
        
        return {
            "trend_score": int(current),
            "trend_avg": int(avg),
            "trend_direction": direction,
            "trend_change_pct": (recent_avg / avg - 1) * 100 if avg > 0 else 0,
        }
```

### 6.3 Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Weekly granularity** | Tidak bisa daily | Combine with daily data |
| **Rate limited** | 1 req/sec | Cache results |
| **No absolute volume** | Relative only | Use for direction, not magnitude |
| **Keyword matching** | "BBCA" bisa berarti lain | Use full company name |
| **Geo limitation** | Bisa by country/region | Set geo='ID' |

---

## 7. Broker Flow Analysis

### 7.1 Konsep

Broker flow menunjukkan aktivitas per broker. Konsentrasi broker pada satu saham dapat mengindikasikan:
- **Akumulasi institusional** (1-2 broker dominan beli)
- **Distribusi** (1-2 broker dominan jual)
- **Manipulasi** (broker code sama di buy & sell)

### 7.2 Broker Concentration

```python
def broker_concentration(broker_data: pd.DataFrame, ticker: str, date: str) -> dict:
    """Analyze broker concentration for a ticker on a given date."""
    ticker_data = broker_data[
        (broker_data["ticker"] == ticker) & 
        (broker_data["date"] == date)
    ]
    
    if ticker_data.empty:
        return {"concentration": "unknown", "top_brokers": []}
    
    # Buy side
    buy_brokers = ticker_data[ticker_data["side"] == "buy"].nlargest(5, "volume")
    sell_brokers = ticker_data[ticker_data["side"] == "sell"].nlargest(5, "volume")
    
    total_buy = ticker_data[ticker_data["side"] == "buy"]["volume"].sum()
    total_sell = ticker_data[ticker_data["side"] == "sell"]["volume"].sum()
    
    # Concentration ratio (top 3 / total)
    top3_buy = buy_brokers.head(3)["volume"].sum()
    buy_concentration = top3_buy / total_buy if total_buy > 0 else 0
    
    top3_sell = sell_brokers.head(3)["volume"].sum()
    sell_concentration = top3_sell / total_sell if total_sell > 0 else 0
    
    # Same broker on both sides (potential manipulation)
    buy_codes = set(buy_brokers["broker_code"].head(3))
    sell_codes = set(sell_brokers["broker_code"].head(3))
    overlap = buy_codes & sell_codes
    
    return {
        "buy_concentration_ratio": buy_concentration,
        "sell_concentration_ratio": sell_concentration,
        "top_buy_brokers": buy_brokers.to_dict("records"),
        "top_sell_brokers": sell_brokers.to_dict("records"),
        "concentration_label": "high" if max(buy_concentration, sell_concentration) > 0.5 else "moderate" if max(buy_concentration, sell_concentration) > 0.3 else "low",
        "broker_overlap": list(overlap),
        "overlap_flag": len(overlap) > 0,
    }
```

---

## 8. Fear & Greed Index

### 8.1 Komponen

| Component | Weight | Calculation |
|-----------|--------|-------------|
| **Market momentum** | 25% | IHSG vs 125-day SMA |
| **Market volatility** | 25% | Realized volatility vs historical |
| **Foreign flow** | 20% | Net foreign flow (20-day) |
| **Market breadth** | 15% | Advancing/declining stocks |
| **Put/Call equivalent** | 15% | (Not available in IDX — substitute with volume ratio) |

### 8.2 Implementation

```python
def compute_fear_greed(
    ihsg_data: pd.DataFrame,
    foreign_flow: pd.DataFrame,
    breadth_data: pd.DataFrame,
) -> dict:
    """Compute Fear & Greed index for IDX (0=Extreme Fear, 100=Extreme Greed)."""
    scores = {}
    
    # 1. Market momentum (IHSG vs 125-day SMA)
    current = ihsg_data["close"].iloc[-1]
    sma_125 = ihsg_data["close"].rolling(125).mean().iloc[-1]
    momentum = (current / sma_125 - 1) * 100
    scores["momentum"] = max(0, min(100, 50 + momentum * 5))
    
    # 2. Market volatility
    returns = ihsg_data["close"].pct_change()
    current_vol = returns.tail(20).std() * np.sqrt(252)
    historical_vol = returns.tail(125).std() * np.sqrt(252)
    vol_ratio = current_vol / historical_vol if historical_vol > 0 else 1
    scores["volatility"] = max(0, min(100, 100 - vol_ratio * 50))
    
    # 3. Foreign flow
    recent_flow = foreign_flow.tail(20)["foreign_net"].sum()
    scores["foreign_flow"] = max(0, min(100, 50 + np.sign(recent_flow) * 25))
    
    # 4. Market breadth
    advancing = (breadth_data["change_pct"] > 0).sum()
    declining = (breadth_data["change_pct"] < 0).sum()
    total = advancing + declining
    scores["breadth"] = (advancing / total * 100) if total > 0 else 50
    
    # 5. Volume ratio (substitute for put/call)
    # High volume on down days = fear
    scores["volume"] = 50  # placeholder, needs volume direction analysis
    
    # Weighted average
    weights = {"momentum": 0.25, "volatility": 0.25, "foreign_flow": 0.20, "breadth": 0.15, "volume": 0.15}
    fgi = sum(scores[k] * weights[k] for k in weights)
    
    label = (
        "Extreme Fear" if fgi < 25 else
        "Fear" if fgi < 45 else
        "Neutral" if fgi < 55 else
        "Greed" if fgi < 75 else
        "Extreme Greed"
    )
    
    return {
        "fear_greed_index": int(fgi),
        "label": label,
        "components": scores,
        "timestamp": datetime.now(UTC).isoformat(),
    }
```

---

## 9. Alternative Data Sources

### 9.1 Alternative Data Catalog

| Data | Source | Relevance | Accessibility |
|------|--------|-----------|---------------|
| **Insider trading** | IDX disclosure | High | Free (IDX) |
| **Short interest** | KPEI | Medium | Limited |
| **Options flow** | IDX derivatives | Medium | Limited |
| **Government data** | BPS, BI, Kemenkeu | High | Free |
| **Satellite imagery** | Third-party | Low for IDX | Paid |
| **Credit card data** | Third-party | Low for IDX | Paid |
| **Web scraping** | Various | Medium | Free (effort) |
| **App downloads** | App Store/Play Store | Low | Free |
| **Patent filings** | DJKI | Low | Free |
| **Job postings** | Job sites | Low | Free (effort) |

### 9.2 Macro Data Sentiment

```python
def macro_sentiment_score(macro_data: dict) -> dict:
    """Compute sentiment from macro indicators."""
    scores = {}
    
    # BI Rate (low = positive for stocks)
    bi_rate = macro_data.get("bi_rate", 6.0)
    scores["bi_rate"] = max(0, min(100, 100 - bi_rate * 10))
    
    # Inflation (low = positive)
    inflation = macro_data.get("inflation_yoy", 3.0)
    scores["inflation"] = max(0, min(100, 100 - inflation * 15))
    
    # USD/IDR (stable/declining = positive)
    usd_idr_change = macro_data.get("usd_idr_change_20d", 0)
    scores["fx"] = max(0, min(100, 50 - usd_idr_change * 1000))
    
    # Commodity prices (for commodity-heavy IDX)
    commodity_change = macro_data.get("commodity_index_change_20d", 0)
    scores["commodity"] = max(0, min(100, 50 + commodity_change * 100))
    
    # Aggregate
    overall = np.mean(list(scores.values()))
    
    return {
        "macro_sentiment_score": overall,
        "label": "positive" if overall > 55 else "negative" if overall < 45 else "neutral",
        "components": scores,
    }
```

---

## 10. Integrasi dengan Decision Engine

### 10.1 Sentiment Engine Output

```python
class SentimentEngine:
    """Aggregate all sentiment signals into a single score."""
    
    def analyze(self, ticker: str) -> dict:
        """Compute comprehensive sentiment score for a ticker."""
        components = {}
        
        # 1. News sentiment (weight: 30%)
        news = aggregate_news_sentiment(self.news_items, ticker)
        components["news"] = news["sentiment_score"] * 50 + 50  # convert -1..1 to 0..100
        
        # 2. Social media (weight: 15%)
        social = normalize_social_sentiment(self.social_items, ticker)
        components["social"] = social["score"]
        
        # 3. Foreign flow (weight: 30%)
        flow = foreign_flow_sentiment(self.flow_data, ticker)
        components["foreign_flow"] = flow["score"]
        
        # 4. Broker concentration (weight: 15%)
        broker = broker_concentration(self.broker_data, ticker, self.latest_date)
        components["broker"] = 50  # neutral default, adjust based on concentration
        
        # 5. Google Trends (weight: 10%)
        trends = self._get_trends(ticker)
        components["trends"] = trends["trend_score"]
        
        # Weighted average
        weights = {
            "news": 0.30,
            "social": 0.15,
            "foreign_flow": 0.30,
            "broker": 0.15,
            "trends": 0.10,
        }
        
        total_score = sum(components[k] * weights[k] for k in weights)
        
        return {
            "ticker": ticker,
            "sentiment_score": total_score,  # 0-100
            "sentiment_label": (
                "very_positive" if total_score > 70 else
                "positive" if total_score > 55 else
                "neutral" if total_score > 45 else
                "negative" if total_score > 30 else
                "very_negative"
            ),
            "components": components,
            "weights": weights,
            "confidence": self._compute_confidence(components),
        }
    
    def _compute_confidence(self, components: dict) -> float:
        """Compute confidence based on data availability and agreement."""
        # Agreement: how aligned are the components?
        values = list(components.values())
        if len(values) < 2:
            return 0.3
        agreement = 1 - np.std(values) / 50  # lower std = higher agreement
        return max(0.1, min(1.0, agreement))
```

### 10.2 Decision Engine Integration

```python
# In DecisionEngine, sentiment is one of 6 factors with 15% weight
DECISION_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.25,
    "macro": 0.15,
    "global": 0.15,
    "relationship": 0.10,
    "sentiment": 0.15,  # ← from SentimentEngine
}
```

---

## 11. Implementasi untuk IDX

### 11.1 Pertimbangan Khusus

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **Bahasa Indonesia** | NLP model terbatas | IndoBERT + custom lexicon |
| **Foreign flow dominance** | Sentiment indicator utama | Weight 30% untuk foreign flow |
| **Limited social media** | r/Saham kecil vs WallStreetBets | Lower weight untuk social |
| **IDX scraper dependency** | Data bisa delay | Cache + fallback |
| **Slang finansial** | "cuan", "diskon", "diskon besar" | Custom normalization |
| **News behind paywall** | Beberapa media berbayar | Fokus pada RSS gratis |

### 11.2 Recommended Sentiment Stack

```
Layer 1: Foreign Flow (30%) — paling reliable untuk IDX
Layer 2: News Sentiment (30%) — RSS feeds Indonesia
Layer 3: Broker Concentration (15%) — IDX scraper
Layer 4: Social Media (15%) — Reddit r/Saham
Layer 5: Google Trends (10%) — search interest
```

---

## 12. Checklist Implementasi

### NLP
- [ ] Indonesian text preprocessing pipeline
- [ ] Custom financial lexicon (positive/negative words)
- [ ] Slang normalization
- [ ] Ticker extraction from text
- [ ] IndoBERT or similar model integration (optional)

### News
- [ ] RSS feed collector (Bisnis, Kontan, CNBC, Investor ID)
- [ ] News deduplication
- [ ] Ticker extraction from headlines
- [ ] Sentiment scoring per article
- [ ] Aggregation per ticker (7-day rolling)

### Social Media
- [ ] Reddit r/Saham collector
- [ ] X/Twitter collector (if API access)
- [ ] Engagement weighting
- [ ] Ticker extraction
- [ ] Score normalization (0-100)

### Foreign Flow
- [ ] IDX scraper for foreign flow data
- [ ] 20-day rolling sentiment score
- [ ] Net buy/sell day ratio
- [ ] Trend detection (recent vs older)
- [ ] Signal strength classification

### Broker Flow
- [ ] IDX scraper for broker summary
- [ ] Concentration ratio computation
- [ ] Top broker identification
- [ ] Broker overlap detection (manipulation flag)

### Fear & Greed
- [ ] Market momentum component
- [ ] Volatility component
- [ ] Foreign flow component
- [ ] Market breadth component
- [ ] Composite index (0-100)

### Integration
- [ ] SentimentEngine with weighted aggregation
- [ ] Confidence score computation
- [ ] Integration with Decision Engine (15% weight)
- [ ] Sentiment history storage
- [ ] Sentiment trend tracking

### Data Storage
- [ ] `news` table with sentiment scores
- [ ] `sentiment_scores` table per ticker per day
- [ ] `fear_greed` table (daily)
- [ ] `social_mentions` table
- [ ] Audit trail for sentiment calculations

---

## Referensi

1. `src/trading_system/sentiment/` — Sentiment engine modules
2. `src/trading_system/sentiment/engine.py` — Sentiment engine
3. `src/trading_system/sentiment/foreign_flow.py` — Foreign flow analysis
4. `src/trading_system/sentiment/broker_summary.py` — Broker flow analysis
5. `src/trading_system/sentiment/social_media.py` — Social media collector
6. `src/trading_system/sentiment/google_trends.py` — Google Trends
7. IndoNLU: https://github.com/indobenchmark/indonlu
8. `pustaka/09-behavioral-finance.md` — Behavioral finance
9. `pustaka/18-modul-engine-data-wajib.md` — Module registry
10. `pustaka/02-pasar-modal-indonesia.md` — IDX foreign flow convention

---

> **Catatan:** Sentiment di IDX didominasi oleh foreign flow. Untuk sistem trading Indonesia, foreign flow adalah sentiment indicator paling reliable. News dan social media adalah pelengkap, bukan pengganti.
