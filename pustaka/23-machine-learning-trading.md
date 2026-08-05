# Machine Learning untuk Trading

> **Tujuan:** Dokumen ini adalah referensi definitif untuk penerapan machine learning dalam sistem trading — dari feature engineering, model selection, training/validation, walk-forward optimization, regime detection, hingga deployment dan monitoring model di produksi.

---

## Daftar Isi

1. [ML Pipeline untuk Trading](#1-ml-pipeline-untuk-trading)
2. [Feature Engineering](#2-feature-engineering)
3. [Model Selection](#3-model-selection)
4. [Training & Validation](#4-training--validation)
5. [Walk-Forward Optimization](#5-walk-forward-optimization)
6. [Regime Detection](#6-regime-detection)
7. [Labeling Strategies](#7-labeling-strategies)
8. [Model Registry & Versioning](#8-model-registry--versioning)
9. [Purged Cross-Validation](#9-purged-cross-validation)
10. [Ensemble Methods](#10-ensemble-methods)
11. [Anti-Overfitting Checklist](#11-anti-overfitting-checklist)
12. [Implementasi untuk IDX](#12-implementasi-untuk-idx)

---

## 1. ML Pipeline untuk Trading

### 1.1 Alur End-to-End

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Data    │──▶│ Feature  │──▶│  Label   │──▶│  Train   │──▶│ Validate │
│  Loading │   │ Engineering│  │ Generation│  │  Model   │   │ (WFO)    │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └────┬─────┘
                                                                  │
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│ Monitor  │◀──│ Deploy   │◀──│ Ensemble │◀──│ Backtest │◀───────┘
│ Drift    │   │ Registry │   │ Selection│   │ Results  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
```

### 1.2 Prinsip ML Trading

| Prinsip | Deskripsi | Dampak jika Dilanggar |
|---------|-----------|----------------------|
| **No look-ahead bias** | Feature hanya menggunakan data yang available saat prediksi | Backtest menipu, live gagal |
| **Purged CV** | Cross-validation dengan gap untuk autocorrelation | Overfitting, inflated metrics |
| **Walk-forward** | Train pada periode A, test pada B > A | Realistic performance estimate |
| **Feature stability** | Feature distribution stabil over time | Model degradation |
| **Ensemble > single** | Kombinasi model lebih robust | Single point of failure |
| **Position sizing from ML** | Probabilitas → position size, bukan binary signal | Over/under-sizing |

---

## 2. Feature Engineering

### 2.1 Kategori Feature

| Kategori | Contoh | Window | Stationarity |
|----------|--------|--------|--------------|
| **Price-based** | Returns, log returns, momentum | 1-250 days | Relatively stable |
| **Technical indicators** | RSI, MACD, ATR, Bollinger | 14-200 days | Bounded (0-100) |
| **Volume-based** | OBV, volume ratio, money flow | 10-100 days | Non-stationary |
| **Fundamental** | P/E, ROE, debt ratio, earnings growth | Quarterly | Slow-moving |
| **Macro** | BI rate, inflation, USD/IDR, commodity | Monthly | Non-stationary |
| **Sentiment** | Foreign flow, broker flow, news score | Daily | Bounded |
| **Cross-sectional** | Sector momentum, relative strength | Daily | Ranked |
| **Alternative** | Google Trends, social media | Weekly | Noisy |

### 2.2 Feature Construction

```python
import numpy as np
import pandas as pd

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute comprehensive feature set from OHLCV."""
    f = pd.DataFrame(index=df.index)
    
    # Returns
    f["return_1d"] = df["close"].pct_change(1)
    f["return_5d"] = df["close"].pct_change(5)
    f["return_20d"] = df["close"].pct_change(20)
    f["log_return_1d"] = np.log(df["close"] / df["close"].shift(1))
    
    # Volatility
    f["volatility_20d"] = f["return_1d"].rolling(20).std()
    f["volatility_60d"] = f["return_1d"].rolling(60).std()
    f["vol_ratio"] = f["volatility_20d"] / f["volatility_60d"]
    
    # Momentum
    f["rsi_14"] = compute_rsi(df["close"], 14)
    f["macd"], f["macd_signal"] = compute_macd(df["close"])
    f["macd_hist"] = f["macd"] - f["macd_signal"]
    
    # Volume
    f["volume_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
    f["obv"] = (np.sign(f["return_1d"]) * df["volume"]).cumsum()
    
    # Price patterns
    f["high_low_range"] = (df["high"] - df["low"]) / df["close"]
    f["close_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"])
    
    # Moving averages
    for window in [10, 20, 50, 200]:
        sma = df["close"].rolling(window).mean()
        f[f"sma_{window}_ratio"] = df["close"] / sma
    
    # ATR
    f["atr_14"] = compute_atr(df, 14)
    f["atr_pct"] = f["atr_14"] / df["close"]
    
    return f
```

### 2.3 Feature Selection

```python
from sklearn.feature_selection import SelectKBest, f_regression, mutual_info_regression

def select_features(X, y, method="mutual_info", k=20):
    """Select top-k features."""
    if method == "mutual_info":
        selector = SelectKBest(mutual_info_regression, k=k)
    elif method == "f_regression":
        selector = SelectKBest(f_regression, k=k)
    
    selector.fit(X, y)
    selected = X.columns[selector.get_support()]
    return list(selected)
```

### 2.4 Feature Importance

```python
from sklearn.ensemble import RandomForestRegressor

def feature_importance(X, y):
    """Compute feature importance via Random Forest."""
    rf = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
    rf.fit(X, y)
    
    importance = pd.Series(rf.feature_importances_, index=X.columns)
    return importance.sort_values(ascending=False)
```

### 2.5 Stationarity Check

```python
from statsmodels.tsa.stattools import adfuller

def check_stationarity(series, significance=0.05):
    """Augmented Dickey-Fuller test for stationarity."""
    result = adfuller(series.dropna())
    return {
        "adf_statistic": result[0],
        "p_value": result[1],
        "is_station": result[1] < significance,
    }
```

---

## 3. Model Selection

### 3.1 Model Comparison

| Model | Type | Strengths | Weaknesses | Best For |
|-------|------|-----------|------------|----------|
| **Linear Regression** | Linear | Interpretable, fast | Underfits complex patterns | Factor weight optimization |
| **Ridge/Lasso** | Linear regularized | Feature selection, robust | Still linear | Many features, multicollinearity |
| **Random Forest** | Tree ensemble | Non-linear, robust | Can overfit | Feature importance, classification |
| **Gradient Boosting** | Tree ensemble | High performance | Sensitive to hyperparams | Return prediction, classification |
| **LSTM/GRU** | Deep learning | Sequential patterns | Slow, overfits, black-box | Time series with long dependencies |
| **Transformer** | Deep learning | Attention mechanism | Very complex, data-hungry | Large datasets, multi-asset |
| **HMM** | Probabilistic | Regime detection | Assumes Markov property | Market regime identification |

### 3.2 Model untuk Sistem Trading IDX

```python
# 1. Factor Weight Optimization (Linear Regression)
from sklearn.linear_regression import LinearRegression

model_lr = LinearRegression()
model_lr.fit(X_train, y_train)
# Weights = coefficients → use for Decision Engine scoring

# 2. Return Prediction (Gradient Boosting)
from sklearn.ensemble import GradientBoostingRegressor

model_gbr = GradientBoostingRegressor(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    random_state=42,
)
model_gbr.fit(X_train, y_train)

# 3. Direction Prediction (Random Forest Classifier)
from sklearn.ensemble import RandomForestClassifier

model_rfc = RandomForestClassifier(
    n_estimators=100,
    max_depth=5,
    class_weight="balanced",
    random_state=42,
)
model_rfc.fit(X_train, y_direction_train)

# 4. Regime Detection (HMM)
from hmmlearn.hmm import GaussianHMM

model_hmm = GaussianHMM(n_components=3, covariance_type="full", n_iter=100)
model_hmm.fit(returns_scaled)
regimes = model_hmm.predict(returns_scaled)
```

---

## 4. Training & Validation

### 4.1 Train/Test Split untuk Time Series

```python
def time_series_split(df, train_ratio=0.7, val_ratio=0.15):
    """Chronological split — NO random shuffle."""
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))
    
    train = df.iloc[:train_end]
    val = df.iloc[train_end:val_end]
    test = df.iloc[val_end:]
    
    return train, val, test
```

> **KRITIS:** Jangan pernah gunakan `train_test_split(shuffle=True)` untuk time series. Ini menyebabkan look-ahead bias.

### 4.2 Metrics

```python
def evaluate_model(y_true, y_pred, y_direction_true=None, y_direction_pred=None):
    """Comprehensive model evaluation."""
    from sklearn.metrics import (
        mean_squared_error, mean_absolute_error,
        accuracy_score, precision_score, recall_score, f1_score,
    )
    
    metrics = {
        "mse": mean_squared_error(y_true, y_pred),
        "rmse": np.sqrt(mean_squared_error(y_true, y_pred)),
        "mae": mean_absolute_error(y_true, y_pred),
        "r2": 1 - mean_squared_error(y_true, y_pred) / y_true.var(),
    }
    
    if y_direction_true is not None:
        metrics.update({
            "accuracy": accuracy_score(y_direction_true, y_direction_pred),
            "precision": precision_score(y_direction_true, y_direction_pred, average="weighted"),
            "recall": recall_score(y_direction_true, y_direction_pred, average="weighted"),
            "f1": f1_score(y_direction_true, y_direction_pred, average="weighted"),
        })
    
    # Trading-specific metrics
    hit_rate = np.mean(np.sign(y_pred) == np.sign(y_true))
    metrics["hit_rate"] = hit_rate
    
    # Profit factor (if we trade based on predictions)
    returns = y_true * np.sign(y_pred)
    metrics["profit_factor"] = returns[returns > 0].sum() / abs(returns[returns < 0].sum())
    
    return metrics
```

### 4.3 Hyperparameter Tuning

```python
from sklearn.model_selection import TimeSeriesSplit
from sklearn.model_selection import GridSearchCV

def tune_hyperparameters(X, y, model, param_grid):
    """Time-series-aware hyperparameter tuning."""
    tscv = TimeSeriesSplit(n_splits=5)
    grid = GridSearchCV(model, param_grid, cv=tscv, scoring="neg_mean_squared_error")
    grid.fit(X, y)
    return grid.best_params_, grid.best_score_
```

---

## 5. Walk-Forward Optimization

### 5.1 Konsep

Walk-forward optimization (WFO) mensimulasikan trading realistis:
1. Train model pada window [t-k, t]
2. Predict pada [t, t+h]
3. Slide window forward, retrain
4. Aggregate out-of-sample predictions

```
Time →
Train: [======]          [======]          [======]
Test:          [==]              [==]              [==]
               ↑                 ↑                 ↑
               Prediksi 1        Prediksi 2        Prediksi 3
```

### 5.2 Implementasi

```python
def walk_forward_optimize(X, y, model_factory, train_window=252, test_window=21):
    """Walk-forward optimization for time series.
    
    Args:
        X: Feature DataFrame
        y: Target Series
        model_factory: callable that returns a fresh model
        train_window: training window size (e.g., 252 = 1 year)
        test_window: test window size (e.g., 21 = 1 month)
    
    Returns:
        DataFrame with predictions and actuals
    """
    results = []
    n = len(X)
    
    for start in range(train_window, n, test_window):
        end = min(start + test_window, n)
        
        # Train on [start-train_window, start)
        X_train = X.iloc[start - train_window:start]
        y_train = y.iloc[start - train_window:start]
        
        # Predict on [start, end)
        X_test = X.iloc[start:end]
        y_test = y.iloc[start:end]
        
        # Fresh model
        model = model_factory()
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        for i, (pred, actual) in enumerate(zip(y_pred, y_test)):
            results.append({
                "date": X_test.index[i],
                "predicted": pred,
                "actual": actual,
            })
    
    return pd.DataFrame(results).set_index("date")
```

### 5.3 Purged Walk-Forward

```python
def purged_walk_forward(X, y, model_factory, train_window=252, test_window=21, purge_window=5):
    """Walk-forward with purge gap to reduce autocorrelation bias."""
    results = []
    n = len(X)
    
    for start in range(train_window + purge_window, n, test_window):
        end = min(start + test_window, n)
        
        # Train on [start-train_window-purge_window, start-purge_window)
        train_start = start - train_window - purge_window
        train_end = start - purge_window
        
        X_train = X.iloc[train_start:train_end]
        y_train = y.iloc[train_start:train_end]
        
        X_test = X.iloc[start:end]
        y_test = y.iloc[start:end]
        
        model = model_factory()
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        for i, (pred, actual) in enumerate(zip(y_pred, y_test)):
            results.append({
                "date": X_test.index[i],
                "predicted": pred,
                "actual": actual,
            })
    
    return pd.DataFrame(results).set_index("date")
```

---

## 6. Regime Detection

### 6.1 Mengapa Regime Detection Penting

Market regime menentukan strategi yang efektif:
- **Bull regime:** Momentum, trend-following works
- **Bear regime:** Mean reversion, defensive
- **Sideways:** Range trading, low conviction
- **Crisis:** Cash, hedging

### 6.2 Hidden Markov Model (HMM)

```python
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

def detect_regimes(returns: pd.Series, n_regimes: int = 3):
    """Detect market regimes using HMM.
    
    Returns:
        Series of regime labels (0, 1, 2, ...)
    """
    # Scale returns
    scaler = StandardScaler()
    returns_scaled = scaler.fit_transform(returns.values.reshape(-1, 1))
    
    # Fit HMM
    model = GaussianHMM(
        n_components=n_regimes,
        covariance_type="full",
        n_iter=100,
        random_state=42,
    )
    model.fit(returns_scaled)
    
    # Predict regimes
    regimes = model.predict(returns_scaled)
    
    # Label regimes by mean return
    regime_means = []
    for i in range(n_regimes):
        mean_ret = returns[regimes == i].mean()
        regime_means.append((i, mean_ret))
    
    # Sort: 0=bear, 1=sideways, 2=bull
    regime_means.sort(key=lambda x: x[1])
    label_map = {old: new for new, (old, _) in enumerate(regime_means)}
    
    return pd.Series(
        [label_map[r] for r in regimes],
        index=returns.index,
        name="regime",
    )
```

### 6.3 Regime-Aware Strategy

```python
class RegimeAwareStrategy:
    """Adjust strategy based on detected regime."""
    
    REGIME_WEIGHTS = {
        "bull": {
            "technical": 0.30, "fundamental": 0.20, "macro": 0.10,
            "global": 0.10, "relationship": 0.10, "sentiment": 0.20,
        },
        "bear": {
            "technical": 0.15, "fundamental": 0.35, "macro": 0.20,
            "global": 0.15, "relationship": 0.05, "sentiment": 0.10,
        },
        "sideways": {
            "technical": 0.25, "fundamental": 0.25, "macro": 0.15,
            "global": 0.10, "relationship": 0.15, "sentiment": 0.10,
        },
    }
    
    def get_weights(self, regime: str) -> dict:
        return self.REGIME_WEIGHTS.get(regime, self.REGIME_WEIGHTS["sideways"])
```

---

## 7. Labeling Strategies

### 7.1 Fixed-Horizon Labeling

```python
def fixed_horizon_labels(returns: pd.Series, horizon: int = 5, threshold: float = 0.0):
    """Label: 1 if forward return > threshold, -1 if < -threshold, 0 otherwise."""
    forward = returns.shift(-horizon)
    labels = pd.Series(0, index=returns.index)
    labels[forward > threshold] = 1
    labels[forward < -threshold] = -1
    return labels
```

### 7.2 Triple-Barrier Method (López de Prado)

```python
def triple_barrier_labels(
    df: pd.DataFrame,
    upper_barrier: float = 0.02,    # take profit
    lower_barrier: float = -0.02,   # stop loss
    vertical_barrier: int = 10,     # max holding period
):
    """Triple-barrier labeling method.
    
    Returns: 1 (hit upper), -1 (hit lower), 0 (hit vertical/time)
    """
    labels = pd.Series(0, index=df.index)
    
    for i in range(len(df) - vertical_barrier):
        entry_price = df["close"].iloc[i]
        
        for j in range(1, vertical_barrier + 1):
            if i + j >= len(df):
                break
            
            ret = (df["close"].iloc[i + j] / entry_price) - 1
            
            if ret >= upper_barrier:
                labels.iloc[i] = 1
                break
            elif ret <= lower_barrier:
                labels.iloc[i] = -1
                break
            # else: continue to next day (vertical barrier)
    
    return labels
```

### 7.3 Meta-Labeling

```python
def meta_labeling(primary_signals: pd.Series, side: pd.Series):
    """Meta-labeling: predict whether primary signal will be correct.
    
    primary_signals: 1 (up), -1 (down), 0 (no signal)
    side: actual outcome (1 if correct, 0 if wrong)
    
    Use secondary model to filter primary signals.
    """
    # Train model to predict probability of primary signal being correct
    # Only trade when secondary model says probability > 0.5
    return side  # binary: 1 (trade), 0 (skip)
```

---

## 8. Model Registry & Versioning

### 8.1 Model Registry Schema

```python
class ModelRegistry:
    """Track model versions, performance, and deployment status."""
    
    def register_model(self, name, version, model, metrics, features, training_data):
        """Register a new model version."""
        entry = {
            "name": name,
            "version": version,
            "created_at": datetime.now(UTC).isoformat(),
            "metrics": metrics,
            "features": features,
            "training_data_range": training_data,
            "status": "staging",  # staging → production → archived
        }
        self.storage.save_model_registry(entry)
    
    def get_production_model(self, name: str):
        """Get current production model."""
        return self.storage.get_model(name, status="production")
    
    def promote_to_production(self, name: str, version: str):
        """Promote model version to production."""
        # Archive current production
        current = self.get_production_model(name)
        if current:
            self.storage.update_model_status(
                name, current["version"], "archived"
            )
        # Promote new
        self.storage.update_model_status(name, version, "production")
```

### 8.2 Model Lifecycle

```
Training → Staging → Validation → Production → Monitor → Retire
                         ↑                          │
                         └──── Retrain (drift) ──────┘
```

---

## 9. Purged Cross-Validation

### 9.1 Masalah Standard K-Fold untuk Time Series

Standard K-fold cross-validation:
- Shuffles data → look-ahead bias
- Train/test overlap → inflated metrics
- Autocorrelation → information leakage

### 9.2 Purged K-Fold

```python
class PurgedKFold:
    """K-fold with purge gap for time series."""
    
    def __init__(self, n_splits=5, purge_gap=5):
        self.n_splits = n_splits
        self.purge_gap = purge_gap
    
    def split(self, X):
        n = len(X)
        indices = np.arange(n)
        fold_size = n // (self.n_splits + 1)
        
        for i in range(self.n_splits):
            test_start = (i + 1) * fold_size
            test_end = min(test_start + fold_size, n)
            
            # Purge: remove gap around test set
            purge_start = max(0, test_start - self.purge_gap)
            purge_end = min(n, test_end + self.purge_gap)
            
            train = np.concatenate([
                indices[:purge_start],
                indices[purge_end:],
            ])
            test = indices[test_start:test_end]
            
            yield train, test
```

---

## 10. Ensemble Methods

### 10.1 Voting Ensemble

```python
from sklearn.ensemble import VotingClassifier, VotingRegressor

def create_ensemble(models: list, voting="soft"):
    """Create voting ensemble from multiple models."""
    ensemble = VotingRegressor(
        estimators=[(f"model_{i}", m) for i, m in enumerate(models)],
    )
    return ensemble
```

### 10.2 Stacking

```python
from sklearn.ensemble import StackingRegressor

def create_stacking(base_models, meta_model):
    """Stacking ensemble with meta-learner."""
    stacked = StackingRegressor(
        estimators=[(f"base_{i}", m) for i, m in enumerate(base_models)],
        final_estimator=meta_model,
        cv=TimeSeriesSplit(n_splits=5),
    )
    return stacked
```

### 10.3 Weighted Ensemble

```python
def weighted_ensemble(predictions: dict, weights: dict):
    """Weighted average of multiple model predictions."""
    result = np.zeros(len(list(predictions.values())[0]))
    for name, preds in predictions.items():
        result += weights[name] * preds
    return result
```

---

## 11. Anti-Overfitting Checklist

### 11.1 Common Pitfalls

| Pitfall | Deskripsi | Solusi |
|---------|-----------|--------|
| **Look-ahead bias** | Menggunakan data future di feature | Hanya gunakan data ≤ prediction date |
| **Survivorship bias** | Hanya saham yang masih listed | Include delisted stocks |
| **Overfitting** | Model terlalu kompleks | Regularization, simpler model |
| **Data snooping** | Test banyak hypothesis pada same data | Multiple testing correction |
| **Leakage in CV** | Train/test overlap | Purged K-fold |
| **Hyperparameter overfit** | Tuning pada test set | Nested CV |

### 11.2 Checklist

- [ ] **No look-ahead:** Semua feature hanya menggunakan data yang available at prediction time
- [ ] **Chronological split:** Train sebelum test, no shuffle
- [ ] **Purged CV:** Gap antara train dan test folds
- [ ] **Walk-forward:** Out-of-sample validation dengan rolling window
- [ ] **Multiple metrics:** Tidak hanya optimize satu metric
- [ ] **Feature stability:** Feature distribution tidak drift signifikan
- [ ] **Model simplicity:** Prefer simpler model jika performansi mirip
- [ ] **Out-of-sample test:** Data yang belum pernah dilihat model
- [ ] **Monte Carlo:** Test robustness dengan random perturbation
- [ ] **Paper trading:** Forward test sebelum live

---

## 12. Implementasi untuk IDX

### 12.1 Pertimbangan Khusus

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **Data terbatas** | ~2,906,406 rows OHLCV, 951 tickers aktif | Transfer learning, simpler models |
| **Fundamental sulit** | Data .JK terbatas di Yahoo | Skip fundamental, fokus teknikal |
| **Korelasi tinggi** | Sahham IDX bergerak bersama | Cross-sectional features, HRP |
| **Regime jelas** | Bull/bear cycles IDX kuat | HMM regime detection wajib |
| **Suspend/delisting** | Saham hilang | Filter is_active, survivorship handling |
| **Thin volume** | Banyak saham illiquid | Volume filter, liquidity features |

### 12.2 Recommended Model Stack

```
Layer 1: Regime Detection (HMM)
    ↓ regime label
Layer 2: Factor Weight Optimization (Ridge Regression)
    ↓ optimized weights per regime
Layer 3: Return Prediction (Gradient Boosting)
    ↓ expected return per ticker
Layer 4: Direction Classification (Random Forest)
    ↓ buy/sell/hold signal
Layer 5: Meta-Labeling (Logistic Regression)
    ↓ confidence filter
Layer 6: Ensemble (Weighted average)
    ↓ final signal + confidence
```

### 12.3 Integration dengan Decision Engine

```python
class AILearningEngine:
    """AI Learning integration with Decision Engine."""
    
    def optimize_weights(self, ticker: str, regime: str) -> dict:
        """Return optimized factor weights for current regime."""
        # Load regime-specific model
        model = self.registry.get_production_model(f"weight_opt_{regime}")
        
        # Get latest features
        features = self._compute_features(ticker)
        
        # Predict optimal weights
        weights = model.predict(features.reshape(1, -1))
        
        return {
            "technical": weights[0],
            "fundamental": weights[1],
            "macro": weights[2],
            "global": weights[3],
            "relationship": weights[4],
            "sentiment": weights[5],
        }
```

---

## Referensi

1. López de Prado, M. (2018). "Advances in Financial Machine Learning"
2. De Prado, M. (2019). "Trend Following on the Shoulders of Giants"
3. `src/trading_system/ai_learning/` — AI Learning modules
4. `src/trading_system/ai_learning/weight_optimizer.py` — LR weight optimization
5. `src/trading_system/ai_learning/deep_learning.py` — Deep learning models
6. `src/trading_system/ai_learning/ensemble.py` — Ensemble methods
7. `src/trading_system/ai_learning/labeling.py` — Labeling strategies
8. `src/trading_system/ai_learning/model_registry.py` — Model registry
9. `src/trading_system/ai_learning/purged_tss.py` — Purged time series split
10. `src/trading_system/ai_learning/walk_forward.py` — Walk-forward optimization
11. `pustaka/08-trading-algoritmik.md` — Trading algoritmik
12. scikit-learn: https://scikit-learn.org
13. hmmlearn: https://hmmlearn.readthedocs.io

---

> **Catatan:** ML untuk trading adalah seni dan sains. Model terbaik bukan yang paling kompleks, tetapi yang paling robust out-of-sample. Selalu gunakan walk-forward validation dan paper trading sebelum live.
