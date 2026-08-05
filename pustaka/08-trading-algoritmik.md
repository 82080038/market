# Trading Algoritmik & Kuantitatif

> **Tujuan:** Dokumen ini adalah referensi komprehensif tentang trading algoritmik dan kuantitatif — strategi, market microstructure, order book, execution, backtesting, dan machine learning — sebagai basis untuk modul trading algoritmik dalam aplikasi pasar modal.

---

## Daftar Isi

1. [Konsep Dasar Trading Algoritmik](#1-konsep-dasar-trading-algoritmik)
2. [Market Microstructure](#2-market-microstructure)
3. [Limit Order Book (LOB)](#3-limit-order-book-lob)
4. [Strategi Trading Algoritmik](#4-strategi-trading-algoritmik)
5. [Execution Algorithms](#5-execution-algorithms)
6. [Backtesting](#6-backtesting)
7. [Walk-Forward Analysis](#7-walk-forward-analysis)
8. [Machine Learning untuk Trading](#8-machine-learning-untuk-trading)
9. [High-Frequency Trading (HFT)](#9-high-frequency-trading-hft)
10. [Sentiment Analysis & Alternative Data](#10-sentiment-analysis--alternative-data)
11. [Implementasi Kode](#11-implementasi-kode)
12. [Pitfalls dan Anti-Patterns](#12-pitfalls-dan-anti-patterns)

---

## 1. Konsep Dasar Trading Algoritmik

### 1.1 Definisi

Trading algoritmik adalah eksekusi order otomatis menggunakan program komputer berdasarkan aturan pre-defined. Sistem kuantitatif menggunakan model matematis dan statistik untuk mengidentifikasi dan mengeksekusi peluang trading.

### 1.2 Tipe Peserta Algoritmik

| Tipe | Deskripsi | Frekuensi | Hold Period |
|------|-----------|-----------|-------------|
| **Market Maker** | Provide liquidity, earn spread | Ultra-high | Detik-menit |
| **Statistical Arbitrage** | Exploit price dislocations | High | Menit-hari |
| **Momentum/Trend Following** | Follow trends | Low-medium | Hari-minggu |
| **Mean Reversion** | Fade extremes | Medium | Jam-hari |
| **Event-Driven** | React to news/events | Variable | Jam-hari |
| **Execution Algorithm** | Minimize market impact | Variable | Intraday |

### 1.3 Komponen Sistem Trading Algoritmik

```
Data Acquisition → Signal Generation → Risk Check → Execution → Monitoring
     ↓                  ↓                  ↓            ↓           ↓
  Market Data       Strategy Logic      Position     Broker      P&L
  Alternative       Indicators          Sizing       API         Drawdown
  News/Fundamental  ML Models           Limits       Smart Order  Risk
```

---

## 2. Market Microstructure

### 2.1 Konsep Dasar

Market microstructure adalah studi tentang bagaimana order diproses, bagaimana harga terbentuk, dan bagaimana likuiditas disediakan dalam pasar finansial.

### 2.2 Tipe Order

| Order | Deskripsi | Eksekusi |
|-------|-----------|----------|
| **Market Order (MO)** | Beli/jual segera pada harga terbaik | Immediate, price not guaranteed |
| **Limit Order (LO)** | Beli/jual pada harga tertentu atau lebih baik | Queued in order book |
| **Cancel Order (CO)** | Batalkan pending limit order | Immediate removal |
| **Stop Order** | Trigger market order saat harga mencapai level | Conditional |
| **Iceberg** | Large order dengan tampilan parsial | Hidden quantity |

### 2.3 Price-Time Priority

Sebagian besar bursa menggunakan **price-time priority**:

1. **Price priority:** Order dengan harga terbaik dieksekusi lebih dulu
   - Buy: highest bid first
   - Sell: lowest ask first
2. **Time priority:** Pada harga yang sama, order yang masuk lebih dulu dieksekusi lebih dulu (FIFO)

### 2.4 Bid-Ask Spread

$$Spread = Ask - Bid$$

| Spread | Likuiditas |
|--------|-----------|
| 1 tick | Sangat likuid (blue chip) |
| 2-5 ticks | Likuid |
| > 5 ticks | Illiquid |

### 2.5 Market Impact

$$Impact = f(Order\ Size, ADV, Volatility)$$

- Order besar relatif terhadap Average Daily Volume (ADV) → higher impact
- Volatilitas tinggi → higher impact
- Market impact = slippage antara expected price dan actual fill price

---

## 3. Limit Order Book (LOB)

### 3.1 Struktur LOB

```
         ASK (Sell Orders)
         ─────────────────
Price    101.00  |  100 shares  ← Best Ask
         100.75  |  200 shares
         100.50  |  150 shares
         ─────────────────
         100.25  |  300 shares  ← Best Bid
         100.00  |  500 shares
          99.75  |  100 shares
         ─────────────────
         BID (Buy Orders)
```

### 3.2 Komponen LOB

| Komponen | Deskripsi |
|----------|-----------|
| **Best Bid** | Highest price buyer willing to pay |
| **Best Ask** | Lowest price seller willing to accept |
| **Mid Price** | (Best Bid + Best Ask) / 2 |
| **Spread** | Best Ask - Best Bid |
| **Depth** | Volume available at each price level |
| **Imbalance** | (Bid Volume - Ask Volume) / (Bid Volume + Ask Volume) |

### 3.3 Order Flow Dynamics

```
Market Buy  → Matches against Ask side → Price moves up
Market Sell → Matches against Bid side → Price moves down
Limit Buy   → Added to Bid side → May increase depth
Limit Sell  → Added to Ask side → May increase depth
Cancel Buy  → Removed from Bid side → May reduce depth
Cancel Sell → Removed from Ask side → May reduce depth
```

### 3.4 Volume Imbalance Signal

```python
def order_imbalance(bid_volume, ask_volume):
    """
    Calculate order book imbalance.
    Positive = more buy pressure, Negative = more sell pressure.
    """
    total = bid_volume + ask_volume
    if total == 0:
        return 0
    return (bid_volume - ask_volume) / total
```

### 3.5 Queue Position

Untuk limit orders, posisi dalam queue menentukan probabilitas eksekusi:

- Posisi 1 di best bid → high fill probability
- Posisi 100 di best bid → low fill probability
- Queue position = function of time, price level, and order size

---

## 4. Strategi Trading Algoritmik

### 4.1 Trend Following

```python
def trend_following_strategy(df, fast=20, slow=50):
    """
    Moving average crossover strategy.
    Buy when fast MA crosses above slow MA.
    Sell when fast MA crosses below slow MA.
    """
    df['ma_fast'] = df['close'].rolling(fast).mean()
    df['ma_slow'] = df['close'].rolling(slow).mean()
    
    df['signal'] = 0
    df.loc[df['ma_fast'] > df['ma_slow'], 'signal'] = 1  # long
    df.loc[df['ma_fast'] < df['ma_slow'], 'signal'] = -1  # short
    
    # Generate trade signals on crossover
    df['position'] = df['signal'].shift(1).fillna(0)
    df['returns'] = df['close'].pct_change()
    df['strategy_returns'] = df['position'] * df['returns']
    
    return df
```

### 4.2 Mean Reversion

```python
def mean_reversion_strategy(df, lookback=20, z_threshold=2.0):
    """
    Bollinger Band mean reversion.
    Buy when price touches lower band.
    Sell when price touches upper band.
    """
    df['sma'] = df['close'].rolling(lookback).mean()
    df['std'] = df['close'].rolling(lookback).std()
    df['upper'] = df['sma'] + z_threshold * df['std']
    df['lower'] = df['sma'] - z_threshold * df['std']
    df['z_score'] = (df['close'] - df['sma']) / df['std']
    
    df['signal'] = 0
    df.loc[df['z_score'] < -z_threshold, 'signal'] = 1   # buy oversold
    df.loc[df['z_score'] > z_threshold, 'signal'] = -1   # sell overbought
    
    df['position'] = df['signal'].shift(1).fillna(0)
    df['strategy_returns'] = df['position'] * df['close'].pct_change()
    
    return df
```

### 4.3 Statistical Arbitrage (Pairs Trading)

```python
def pairs_trading_strategy(df_a, df_b, lookback=60, z_threshold=2.0):
    """
    Pairs trading: long/short two cointegrated stocks.
    """
    import numpy as np
    
    # Calculate spread
    spread = df_a['close'] - df_b['close']
    
    # Rolling z-score of spread
    spread_mean = spread.rolling(lookback).mean()
    spread_std = spread.rolling(lookback).std()
    z_score = (spread - spread_mean) / spread_std
    
    # Signals
    signals = np.where(z_score > z_threshold, -1,   # short A, long B
              np.where(z_score < -z_threshold, 1,    # long A, short B
                       0))                            # neutral
    
    return signals, z_score
```

### 4.4 Momentum Strategy

```python
def momentum_strategy(df, lookback=252, holding=21):
    """
    Cross-sectional momentum: buy winners, sell losers.
    """
    df['momentum'] = df['close'].pct_change(lookback)
    df['rank'] = df['momentum'].rank(pct=True)
    
    df['signal'] = 0
    df.loc[df['rank'] > 0.8, 'signal'] = 1   # top 20% momentum
    df.loc[df['rank'] < 0.2, 'signal'] = -1  # bottom 20%
    
    return df
```

### 4.5 Breakout Strategy

```python
def breakout_strategy(df, lookback=20):
    """
    Donchian channel breakout.
    Buy when price breaks above N-day high.
    Sell when price breaks below N-day low.
    """
    df['upper'] = df['high'].rolling(lookback).max().shift(1)
    df['lower'] = df['low'].rolling(lookback).min().shift(1)
    
    df['signal'] = 0
    df.loc[df['close'] > df['upper'], 'signal'] = 1
    df.loc[df['close'] < df['lower'], 'signal'] = -1
    
    df['position'] = df['signal'].shift(1).fillna(0)
    df['strategy_returns'] = df['position'] * df['close'].pct_change()
    
    return df
```

---

## 5. Execution Algorithms

### 5.1 VWAP (Volume-Weighted Average Price)

```python
def vwap_execution(total_shares, historical_volume_profile, trading_days=1):
    """
    Split order according to historical volume pattern.
    Goal: execute at or better than VWAP.
    """
    # Normalize volume profile to percentages
    volume_pct = historical_volume_profile / historical_volume_profile.sum()
    
    # Allocate shares per time bucket
    schedule = total_shares * volume_pct
    
    return schedule
```

### 5.2 TWAP (Time-Weighted Average Price)

```python
def twap_execution(total_shares, n_buckets):
    """
    Split order evenly across time.
    Simple but doesn't account for volume patterns.
    """
    shares_per_bucket = total_shares / n_buckets
    return [shares_per_bucket] * n_buckets
```

### 5.3 Implementation Shortfall

```python
def implementation_shortfall(arrival_price, fill_prices, fill_quantities, 
                              total_quantity):
    """
    Measure total cost of execution vs arrival price.
    """
    total_cost = sum(q * (p - arrival_price) for p, q in zip(fill_prices, fill_quantities))
    return total_cost / total_quantity
```

### 5.4 Smart Order Routing

```python
class SmartOrderRouter:
    """Route orders to best available venue."""
    
    def __init__(self, venues):
        self.venues = venues  # list of venue objects with quote data
    
    def route_order(self, side, quantity):
        """Find best execution venue."""
        if side == 'buy':
            # Sort by ask price ascending
            sorted_venues = sorted(self.venues, key=lambda v: v.best_ask)
            best_venue = sorted_venues[0]
            return {'venue': best_venue.name, 'price': best_venue.best_ask, 
                    'quantity': min(quantity, best_venue.ask_size)}
        else:
            sorted_venues = sorted(self.venues, key=lambda v: -v.best_bid)
            best_venue = sorted_venues[0]
            return {'venue': best_venue.name, 'price': best_venue.best_bid,
                    'quantity': min(quantity, best_venue.bid_size)}
```

---

## 6. Backtesting

### 6.1 Prinsip Dasar

> **Backtesting adalah simulasi strategi pada data historis untuk evaluasi.** Kualitas backtesting menentukan apakah strategi akan bekerja di live trading.

### 6.2 Next-Bar-Open Execution (No Look-Ahead Bias)

```python
# WRONG (look-ahead bias):
signal = df["close"] > df["close"].rolling(20).mean()
df["position"] = signal.astype(int)  # uses bar-N data for entry at bar-N

# CORRECT (next-bar-open):
signal = df["close"] > df["close"].rolling(20).mean()
df["entry_price"] = df["open"].shift(-1)  # entry at next bar open
df["position"] = signal.shift(1).fillna(0).astype(int)  # signal bar-N, execute bar-N+1
```

### 6.3 Transaction Costs

```python
def apply_transaction_costs(returns, position_changes, 
                            commission_bps=5, slippage_bps=2):
    """
    Apply realistic transaction costs to strategy returns.
    """
    total_costs_bps = commission_bps + slippage_bps
    cost_per_trade = total_costs_bps / 10000
    costs = position_changes.abs() * cost_per_trade
    net_returns = returns - costs
    return net_returns
```

### 6.4 IDX-Specific Rounding

```python
def idx_round_shares(target_shares, lot_size=100):
    """Round to IDX lot size (100 shares)."""
    return round(target_shares / lot_size) * lot_size

def idx_round_price(price):
    """Round to IDX tick size."""
    if price < 200:    tick = 1.0
    elif price < 500:  tick = 2.0
    elif price < 2000: tick = 5.0
    elif price < 5000: tick = 10.0
    else:              tick = 25.0
    return round(price / tick) * tick
```

### 6.5 Backtest Engine

```python
class BacktestEngine:
    """Simple backtesting engine."""
    
    def __init__(self, initial_capital=100_000_000, commission=0.0015):
        self.initial_capital = initial_capital
        self.commission = commission
        self.reset()
    
    def reset(self):
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []
    
    def run(self, df, signals):
        """Run backtest on signals."""
        for i, row in df.iterrows():
            # Execute signals
            for ticker, signal in signals.get(i, {}).items():
                if signal == 'BUY' and ticker not in self.positions:
                    shares = self.capital * 0.1 / row['close']  # 10% allocation
                    cost = shares * row['close'] * (1 + self.commission)
                    self.capital -= cost
                    self.positions[ticker] = {'shares': shares, 'cost': cost}
                    self.trades.append({'date': i, 'ticker': ticker, 
                                       'action': 'BUY', 'shares': shares, 
                                       'price': row['close']})
                
                elif signal == 'SELL' and ticker in self.positions:
                    pos = self.positions[ticker]
                    proceeds = pos['shares'] * row['close'] * (1 - self.commission)
                    self.capital += proceeds
                    self.trades.append({'date': i, 'ticker': ticker,
                                       'action': 'SELL', 'shares': pos['shares'],
                                       'price': row['close']})
                    del self.positions[ticker]
            
            # Track equity
            position_value = sum(
                p['shares'] * row['close'] for p in self.positions.values()
            )
            total_equity = self.capital + position_value
            self.equity_curve.append({'date': i, 'equity': total_equity})
        
        return self.equity_curve
```

---

## 7. Walk-Forward Analysis

### 7.1 Konsep

Walk-forward analysis mensimulasikan bagaimana strategi beradaptasi seiring waktu:

```
Train 1 | Test 1
        Train 2 | Test 2
                Train 3 | Test 3
```

### 7.2 Purged Time Series Split

```python
class PurgedTSS:
    """Time Series Split with purge gap to prevent label leakage."""
    
    def __init__(self, n_splits=5, purge_days=5):
        self.n_splits = n_splits
        self.purge_days = purge_days
    
    def split(self, X):
        n = len(X)
        test_size = n // (self.n_splits + 1)
        
        for i in range(self.n_splits):
            train_end = (i + 1) * test_size
            test_start = train_end + self.purge_days  # purge gap
            test_end = test_start + test_size
            
            if test_end > n:
                break
            
            train_idx = list(range(0, train_end))
            test_idx = list(range(test_start, test_end))
            
            yield train_idx, test_idx
```

### 7.3 Monte Carlo with Block Bootstrap

```python
def block_bootstrap(returns, n_samples=10000, block_size=20):
    """
    Block bootstrap preserving autocorrelation.
    IID resampling destroys temporal structure.
    """
    import numpy as np
    n = len(returns)
    samples = []
    
    for _ in range(n_samples):
        blocks = []
        remaining = n
        while remaining > 0:
            start = np.random.randint(0, n - block_size)
            block = returns[start:start + min(block_size, remaining)]
            blocks.append(block)
            remaining -= len(block)
        sample = np.concatenate(blocks)
        samples.append(sample)
    
    return np.array(samples)
```

---

## 8. Machine Learning untuk Trading

### 8.1 Tipe ML untuk Trading

| Tipe | Algoritma | Aplikasi |
|------|-----------|----------|
| **Supervised** | Linear Regression, Random Forest, XGBoost | Return prediction, classification |
| **Unsupervised** | K-Means, PCA | Regime detection, clustering |
| **Reinforcement** | Q-Learning, PPO | Execution optimization, portfolio management |
| **Deep Learning** | LSTM, Transformer | Time series prediction, NLP sentiment |

### 8.2 Feature Engineering

```python
def create_ml_features(df):
    """Create features for ML model from OHLCV data."""
    # Price-based features
    df['return_1d'] = df['close'].pct_change(1)
    df['return_5d'] = df['close'].pct_change(5)
    df['return_20d'] = df['close'].pct_change(20)
    
    # Technical indicators as features
    df['rsi'] = compute_rsi(df['close'])
    df['macd'], df['macd_signal'], _ = compute_macd(df['close'])
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    
    # Volume features
    df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    
    # Volatility features
    df['volatility_20d'] = df['return_1d'].rolling(20).std()
    
    # Lag features
    for lag in [1, 2, 3, 5]:
        df[f'return_lag_{lag}'] = df['return_1d'].shift(lag)
    
    return df
```

### 8.3 Weight Optimization via Linear Regression

```python
def optimize_weights_lr(features, target):
    """
    Optimize factor weights using Linear Regression.
    Clip negative coefficients to 0 (not abs!).
    """
    from sklearn.linear_model import LinearRegression
    import numpy as np
    
    model = LinearRegression()
    model.fit(features, target)
    
    # WRONG: coef = np.abs(model.coef_)  # changes meaning
    # CORRECT:
    coef = np.maximum(model.coef_, 0)  # negative = not predictive, ignore
    
    # Normalize to sum to 1
    if coef.sum() > 0:
        coef = coef / coef.sum()
    
    return coef
```

### 8.4 Model Registry

```python
class ModelRegistry:
    """Versioned model storage with metadata."""
    
    def __init__(self, storage_dir='models/'):
        self.storage_dir = storage_dir
    
    def save_model(self, model, version, metrics, features, train_range):
        """Save model with full metadata."""
        import json, pickle
        from pathlib import Path
        
        model_dir = Path(self.storage_dir) / version
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model
        with open(model_dir / 'model.pkl', 'wb') as f:
            pickle.dump(model, f)
        
        # Save metadata
        metadata = {
            'version': version,
            'metrics': metrics,
            'features': features,
            'train_range': train_range,
            'created_at': datetime.now().isoformat(),
        }
        with open(model_dir / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def load_model(self, version):
        """Load model by version."""
        import pickle
        from pathlib import Path
        
        model_path = Path(self.storage_dir) / version / 'model.pkl'
        with open(model_path, 'rb') as f:
            return pickle.load(f)
```

---

## 9. High-Frequency Trading (HFT)

### 9.1 Karakteristik

- **Speed:** Microsecond latency
- **Frequency:** Ribuan order per detik
- **Hold time:** Detik sampai menit
- **Profit per trade:** Sangat kecil (cents per share)
- **Volume:** 30-50% dari total volume di developed markets
- **Infrastructure:** Co-location, direct market access, FPGA

### 9.2 Strategi HFT

| Strategi | Deskripsi |
|----------|-----------|
| **Market Making** | Provide liquidity, earn spread + rebates |
| **Statistical Arbitrage** | Exploit micro-price dislocations |
| **Latency Arbitrage** | Exploit speed advantage between venues |
| **Event Arbitrage** | React to news faster than others |
| **Order Book Imbalance** | Predict short-term price direction from LOB |

### 9.3 Market Making

```python
class SimpleMarketMaker:
    """Simplified market making strategy."""
    
    def __init__(self, spread_capture=0.02, inventory_limit=100):
        self.spread_capture = spread_capture
        self.inventory_limit = inventory_limit
        self.inventory = 0
    
    def quote(self, mid_price):
        """Generate bid and ask quotes."""
        # Widen quotes when inventory is high
        inventory_skew = (self.inventory / self.inventory_limit) * self.spread_capture
        
        bid = mid_price - self.spread_capture + inventory_skew
        ask = mid_price + self.spread_capture + inventory_skew
        
        # Reduce size when near inventory limit
        remaining_capacity = self.inventory_limit - abs(self.inventory)
        size = max(1, remaining_capacity // 10)
        
        return {'bid': bid, 'ask': ask, 'size': size}
```

---

## 10. Sentiment Analysis & Alternative Data

### 10.1 Sumber Data Sentimen

| Sumber | Data | Aplikasi |
|--------|------|----------|
| **News** | Berita finansial, press release | Event detection, sentiment |
| **Social Media** | Twitter/X, Reddit, StockTwits | Retail sentiment |
| **Google Trends** | Search volume | Interest indicator |
| **Analyst Reports** | Rating changes, price targets | Institutional sentiment |
| **Insider Trading** | Form 4 filings | Insider confidence |
| **Options Flow** | Put/call ratio, unusual activity | Smart money positioning |
| **Foreign Flow** | Net buy/sell by foreign investors | (Indonesia-specific) |
| **Broker Flow** | Broker concentration | Accumulation/distribution |

### 10.2 NLP untuk Sentimen

```python
def sentiment_analysis(text, lexicon_positive, lexicon_negative):
    """
    Simple lexicon-based sentiment analysis.
    For Indonesian text, need domain-specific lexicon.
    """
    words = text.lower().split()
    pos_count = sum(1 for w in words if w in lexicon_positive)
    neg_count = sum(1 for w in words if w in lexicon_negative)
    
    total = pos_count + neg_count
    if total == 0:
        return 0  # neutral
    return (pos_count - neg_count) / total  # -1 to +1
```

### 10.3 Indonesian NLP Considerations

- Kata ambigu: "rugi" bisa positif (akuntansi) atau negatif (berita saham)
- Negation detection: "tidak untung" = negatif, "untung" = positif
- Domain-specific lexicon perlu review oleh native speaker
- Slang dan abbreviations pasar saham Indonesia

---

## 11. Implementasi Kode

### 11.1 Strategy Framework

```python
class TradingStrategy:
    """Base class for trading strategies."""
    
    VERSION = "1.0"
    
    def __init__(self, name, params=None):
        self.name = name
        self.params = params or {}
        self.positions = {}
    
    def generate_signals(self, df):
        """Override in subclass. Return DataFrame with 'signal' column."""
        raise NotImplementedError
    
    def get_version(self):
        return self.VERSION
    
    def get_params(self):
        return self.params
```

### 11.2 Multi-Factor Decision Engine

```python
class DecisionEngine:
    """Multi-factor weighted scoring decision engine."""
    
    DEFAULT_WEIGHTS = {
        "technical": 0.20,
        "fundamental": 0.25,
        "macro": 0.15,
        "global": 0.15,
        "relationship": 0.10,
        "sentiment": 0.15,
    }
    
    VERSION = "2.0"
    
    def __init__(self, weights=None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
    
    def compute_conviction(self, scores):
        """Compute weighted conviction score 0-100."""
        available = {f: s for f, s in scores.items() if f in self.weights and s is not None}
        
        if not available:
            return 0
        
        # Redistribute weights for missing factors
        weights = self.weights.copy()
        for factor in list(weights):
            if factor not in available:
                w = weights.pop(factor)
                total = sum(weights.values())
                for f in weights:
                    weights[f] += w * (weights[f] / total)
        
        conviction = sum(available[f] * weights[f] for f in available)
        return min(100, max(0, conviction))
    
    def decide(self, scores, has_position=False, conviction_threshold=50):
        """Make trading decision."""
        conviction = self.compute_conviction(scores)
        
        if not has_position and conviction >= conviction_threshold:
            return {"action": "BUY", "conviction": conviction, 
                   "reasons": self._get_reasons(scores, "BUY")}
        elif has_position and conviction < 40:
            return {"action": "SELL", "conviction": conviction,
                   "reasons": ["LOW_CONVICTION_EXIT"]}
        else:
            return {"action": "HOLD", "conviction": conviction,
                   "reasons": self._get_reasons(scores, "HOLD")}
    
    def _get_reasons(self, scores, action):
        """Generate reason codes for audit trail."""
        reasons = []
        for factor, score in scores.items():
            if score is None:
                reasons.append(f"{factor.upper()}_UNAVAILABLE")
            elif score < 30:
                reasons.append(f"{factor.upper()}_WEAK")
            elif score > 70:
                reasons.append(f"{factor.upper()}_STRONG")
        return reasons
```

---

## 12. Pitfalls dan Anti-Patterns

### 12.1 Look-Ahead Bias

| Pitfall | Fix |
|---------|-----|
| Using close price for same-bar entry | Use next-bar open |
| Using future data for normalization | Use rolling/expanding only |
| Fitting on full dataset then testing | Use walk-forward / TimeSeriesSplit |

### 12.2 Overfitting

| Pitfall | Fix |
|---------|-----|
| Too many parameters | Minimize free parameters |
| Optimizing on in-sample only | Out-of-sample testing |
| Ignoring transaction costs | Include realistic costs |
| Too good to be true results | Walk-forward + Monte Carlo |

### 12.3 Survivorship Bias

| Pitfall | Fix |
|---------|-----|
| Only testing current index members | Include delisted companies |
| Ignoring delisted stocks | Use point-in-time constituent lists |

### 12.4 Data Snooping

| Pitfall | Fix |
|---------|-----|
| Testing many strategies on same data | Bonferroni correction |
| Selecting best from many backtests | Pre-register hypothesis |
| Cherry-picking parameters | Deflated Sharpe Ratio |

---

## Referensi

1. arxiv.org — Instantaneous Order Impact and High-Frequency Strategy Optimization in Limit Order Books
2. arxiv.org — Algorithmic trading in a microstructural limit order book model
3. arxiv.org — Reinforcement Learning for Trade Execution with Market and Limit Orders
4. Larry Harris — Trading and Exchanges: Market Microstructure for Practitioners
5. Marcos López de Prado — Advances in Financial Machine Learning
6. Ernie Chan — Algorithmic Trading: Winning Strategies and Their Rationale
7. Robert Carver — Systematic Trading

---

> **Catatan:** Untuk implementasi produksi dalam aplikasi, lihat `11-knowledge-transfer-aplikasi.md` dan `12-panduan-membangun-aplikasi-pasar-modal.md`.
