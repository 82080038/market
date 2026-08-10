"""Multi-Factor Quant Feature Engineering Pipeline (pustaka/23, pustaka/51, pustaka/67).

Combines endogenous (price pattern) and exogenous (global market) features
into a unified feature matrix for ML-based trading decisions.

Three feature dimensions:
1. PRICE PATTERN FEATURES (Endogenous):
   - Autocorrelation (lag 1, 5, 10)
   - Momentum: RSI, MACD histogram, ROC
   - Volatility: Bollinger Band width, ATR percentile
   - Candlestick: standardized body/shadow ratios, doji/hammer/marubozu scores

2. GLOBAL MARKET CROSS-CORRELATION (Exogenous):
   - Returns from S&P 500, NASDAQ, FTSE, Nikkei, Hang Seng
   - Commodity returns: Gold (GC=F), Oil (CL=F), Copper (HG=F)
   - Lead-lag shifted returns (previous day close → current day prediction)
   - Rolling correlation with each global index

3. DIMENSIONALITY REDUCTION & FEATURE SELECTION:
   - PCA on exogenous feature block (retain 95% variance)
   - LightGBM feature importance for final feature selection
   - Prevents Curse of Dimensionality / overfitting

All operations strictly non-look-ahead: features at time T use only
data available before or at T. Global market data is shifted to ensure
only closed sessions are used (per Time-Zone Bucket Grid).

References: pustaka/18 §3, pustaka/20, pustaka/23, pustaka/26, pustaka/51.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── 1. PRICE PATTERN FEATURES (Endogenous) ────────────────────────────────


def compute_autocorrelation(
    close: pd.Series, lags: list[int] | None = None,
) -> dict[str, float]:
    """Compute autocorrelation at multiple lags.

    Autocorrelation measures serial dependence of returns. High positive
    autocorrelation at lag 1 suggests momentum; negative suggests mean reversion.

    Args:
        close: Close price series.
        lags: List of lag periods (default: [1, 5, 10]).

    Returns:
        Dict of {acf_lag_N: value} for each lag.
    """
    if lags is None:
        lags = [1, 5, 10]

    returns = close.pct_change().dropna()
    result: dict[str, float] = {}

    for lag in lags:
        if len(returns) <= lag:
            result[f"acf_{lag}"] = 0.0
            continue
        shifted = returns.shift(lag)
        valid = returns.dropna().align(shifted.dropna(), join="inner")[0]
        shifted_valid = returns.dropna().align(shifted.dropna(), join="inner")[1]
        if len(valid) < 2 or valid.std() == 0 or shifted_valid.std() == 0:
            result[f"acf_{lag}"] = 0.0
        else:
            corr = float(valid.corr(shifted_valid))
            result[f"acf_{lag}"] = corr if np.isfinite(corr) else 0.0

    return result


def compute_autocorrelation_series(
    close: pd.Series, lag: int = 1, window: int = 20,
) -> pd.Series:
    """Compute rolling autocorrelation at given lag.

    Args:
        close: Close price series.
        lag: Autocorrelation lag.
        window: Rolling window size.

    Returns:
        pd.Series of rolling autocorrelation values.
    """
    returns = close.pct_change()
    shifted = returns.shift(lag)

    # Rolling correlation
    result = returns.rolling(window).corr(shifted)
    result = result.fillna(0.0).replace([np.inf, -np.inf], 0.0)
    return result


def compute_candlestick_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute standardized candlestick pattern features.

    Features:
    - body_ratio: |close - open| / (high - low) — candle body proportion
    - upper_shadow: (high - max(open, close)) / (high - low)
    - lower_shadow: (min(open, close) - low) / (high - low)
    - doji_score: 1 - body_ratio (high = doji-like)
    - hammer_score: lower_shadow high + small body (bullish reversal)
    - marubozu_score: body_ratio high + small shadows (strong trend)
    - gap_up: (open - prev_close) / prev_close
    - gap_down: (prev_close - open) / prev_close

    Args:
        df: OHLCV DataFrame.

    Returns:
        DataFrame with candlestick feature columns added.
    """
    result = df.copy()
    o = result["open"].astype(float)
    h = result["high"].astype(float)
    lo = result["low"].astype(float)
    c = result["close"].astype(float)

    hl_range = (h - lo).replace(0, np.nan)
    body = (c - o).abs()
    result["body_ratio"] = (body / hl_range).fillna(0.0)
    result["upper_shadow"] = ((h - o.combine(c, max)) / hl_range).fillna(0.0)
    result["lower_shadow"] = ((o.combine(c, min) - lo) / hl_range).fillna(0.0)

    # Pattern scores
    result["doji_score"] = (1.0 - result["body_ratio"]).clip(0, 1)
    result["hammer_score"] = (
        result["lower_shadow"] * (1 - result["body_ratio"])
    ).clip(0, 1)
    result["marubozu_score"] = (
        result["body_ratio"] * (1 - result["upper_shadow"] - result["lower_shadow"]).clip(0, 1)
    ).clip(0, 1)

    # Gaps
    prev_close = c.shift(1)
    result["gap"] = (o - prev_close) / prev_close.replace(0, np.nan)
    result["gap"] = result["gap"].fillna(0.0).replace([np.inf, -np.inf], 0.0)

    return result


def compute_bollinger_features(
    close: pd.Series, period: int = 20, std_mult: float = 2.0,
) -> pd.DataFrame:
    """Compute Bollinger Band features.

    Features:
    - bb_width: (upper - lower) / middle — volatility expansion/contraction
    - bb_pct: close position within bands (0 = at lower, 1 = at upper)
    - bb_squeeze: bb_width below 20th percentile of rolling window

    Args:
        close: Close price series.
        period: Bollinger period.
        std_mult: Standard deviation multiplier.

    Returns:
        DataFrame with bb_width, bb_pct, bb_squeeze columns.
    """
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper = ma + std_mult * sd
    lower = ma - std_mult * sd

    bb_width = ((upper - lower) / ma.replace(0, np.nan)).fillna(0.0)
    bb_pct = ((close - lower) / (upper - lower).replace(0, np.nan)).clip(0, 2).fillna(1.0)
    bb_squeeze = (bb_width < bb_width.rolling(60).quantile(0.2)).astype(float)

    return pd.DataFrame(
        {"bb_width": bb_width, "bb_pct": bb_pct, "bb_squeeze": bb_squeeze},
        index=close.index,
    )


def compute_macd_features(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9,
) -> pd.DataFrame:
    """Compute MACD features.

    Features:
    - macd_line: MACD line (fast EMA - slow EMA)
    - macd_signal: Signal line (EMA of MACD)
    - macd_hist: Histogram (MACD - Signal)
    - macd_hist_norm: Histogram normalized by close price

    Args:
        close: Close price series.

    Returns:
        DataFrame with MACD feature columns.
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    macd_hist_norm = (macd_hist / close.replace(0, np.nan)).fillna(0.0)

    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "macd_hist_norm": macd_hist_norm,
        },
        index=close.index,
    )


def compute_endogenous_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all endogenous (price pattern) features.

    Combines autocorrelation, candlestick, Bollinger, MACD, and
    existing technical features into a single DataFrame.

    Args:
        df: OHLCV DataFrame (with adjusted prices).

    Returns:
        DataFrame with all endogenous feature columns.
    """
    result = df.copy()
    close = result["close"].astype(float)

    # Autocorrelation (rolling)
    result["acf_1"] = compute_autocorrelation_series(close, lag=1, window=20)
    result["acf_5"] = compute_autocorrelation_series(close, lag=5, window=20)
    result["acf_10"] = compute_autocorrelation_series(close, lag=10, window=20)

    # Candlestick
    result = compute_candlestick_features(result)

    # Bollinger
    bb = compute_bollinger_features(close)
    result["bb_width"] = bb["bb_width"]
    result["bb_pct"] = bb["bb_pct"]
    result["bb_squeeze"] = bb["bb_squeeze"]

    # MACD
    macd = compute_macd_features(close)
    result["macd_hist_norm"] = macd["macd_hist_norm"]
    result["macd_line_norm"] = (macd["macd_line"] / close.replace(0, np.nan)).fillna(0.0)

    # RSI (14) — reuse from existing
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result["rsi"] = (100 - (100 / (1 + rs))).fillna(50.0)

    # Momentum
    result["momentum_5"] = (close.pct_change(5) * 100).fillna(0.0)
    result["momentum_10"] = (close.pct_change(10) * 100).fillna(0.0)
    result["roc_20"] = (close.pct_change(20) * 100).fillna(0.0)

    # MA ratios
    result["ma_5"] = close.rolling(5).mean()
    result["ma_20"] = close.rolling(20).mean()
    result["ma_ratio"] = (result["ma_5"] / result["ma_20"].replace(0, np.nan)).fillna(1.0)
    result["ma_5_slope"] = result["ma_5"].pct_change(3).fillna(0.0)

    # Volatility
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    result["atr_pct"] = ((high - low) / close * 100).rolling(14).mean().fillna(0.0)
    result["hl_range_pct"] = ((high - low) / close * 100).fillna(0.0)
    result["vol_regime"] = result["atr_pct"].rolling(60).rank(pct=True).fillna(0.5)

    # Close relative to range
    result["close_to_high"] = (close / high.rolling(20).max().replace(0, np.nan)).fillna(1.0)
    result["close_to_low"] = (close / low.rolling(20).min().replace(0, np.nan)).fillna(1.0)

    # Volume features
    volume = result["volume"].astype(float)
    vol_ma = volume.rolling(20).mean().replace(0, np.nan)
    result["vol_ratio"] = (volume / vol_ma).fillna(1.0)
    result["vol_trend"] = (volume.pct_change(5) * 100).fillna(0.0)

    # VWAP
    vol_price = close * volume
    vol_sum = volume.rolling(20, min_periods=1).sum().replace(0, np.nan)
    vp_sum = vol_price.rolling(20, min_periods=1).sum()
    result["vwap_20"] = (vp_sum / vol_sum).fillna(close)
    result["vwap_ratio"] = (close / result["vwap_20"].replace(0, np.nan)).fillna(1.0)

    # Price acceleration
    result["price_accel"] = (result["momentum_5"] - result["momentum_5"].shift(5)).fillna(0.0)

    return result


# ── 2. GLOBAL MARKET CROSS-CORRELATION (Exogenous) ────────────────────────


# Global indices and commodities
GLOBAL_ASSETS: dict[str, str] = {
    "^GSPC": "sp500",
    "^IXIC": "nasdaq",
    "^FTSE": "ftse",
    "^N225": "nikkei",
    "^HSI": "hangseng",
    "GC=F": "gold",
    "CL=F": "oil",
    "HG=F": "copper",
    "MTF=F": "coal",
    "CPO=F": "cpo",
    "NI=F": "nickel",
}


def compute_exogenous_features(
    df: pd.DataFrame,
    global_data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    lookback: int = 5,
    corr_window: int = 60,
) -> pd.DataFrame:
    """Compute exogenous (global market) features aligned to ticker data.

    For each global asset, computes:
    - lag_1_return: Previous day's return (with timezone-aware alignment)
    - lag_5_return: 5-day momentum
    - rolling_corr: 60-day rolling correlation with ticker returns

    Asymmetric lag (anti look-ahead bias per Time-Zone Bucket Grid):
    - Asian markets (^N225, ^HSI): T-0 (close before IDX → same-day data valid)
    - US markets (^GSPC, ^VIX, ^TNX): T-1 (close after IDX → previous day only)
    - Commodities (GC=F, CL=F, HG=F, MTF=F, CPO=F): T-1 (US-centric settle)

    At 16:15 WIB (09:15 UTC) prediction time:
    - Tokyo (^N225) closed at 06:30 UTC → same-day close available
    - Hong Kong (^HSI) closed at 08:00 UTC → same-day close available
    - US (^GSPC) opens at 13:30/14:30 UTC → must use previous day close

    Args:
        df: Ticker OHLCV DataFrame (aligned index).
        global_data: Dict of {ticker: DataFrame} for global assets.
        as_of: Cutoff date (if None, use all data).
        lookback: Momentum lookback period.
        corr_window: Rolling correlation window.

    Returns:
        DataFrame with exogenous feature columns.
    """
    from market.analysis.cross_market_timezone import get_ticker_lag

    ticker_returns = df["close"].astype(float).pct_change()
    result = pd.DataFrame(index=df.index)

    for gticker, gname in GLOBAL_ASSETS.items():
        if gticker not in global_data:
            continue

        gdf = global_data[gticker]
        if gdf.empty:
            continue

        gclose = gdf["close"].astype(float)

        # Align to ticker index via reindex (forward-fill for non-overlapping days)
        gclose_aligned = gclose.reindex(df.index, method="ffill")

        # Asymmetric lag: T-0 for Asian, T-1 for US/commodities
        lag = get_ticker_lag(gticker)
        g_returns = gclose_aligned.pct_change().shift(lag)

        # Lag returns (previous session close → today's prediction)
        result[f"{gname}_lag1_ret"] = g_returns.fillna(0.0)
        result[f"{gname}_lag5_ret"] = (
            (gclose_aligned / gclose_aligned.shift(lookback) - 1).shift(lag).fillna(0.0)
        )

        # Rolling correlation (ticker vs global, 60-day window)
        rolling_corr = ticker_returns.rolling(corr_window).corr(g_returns)
        result[f"{gname}_corr"] = rolling_corr.fillna(0.0).replace(
            [np.inf, -np.inf], 0.0
        )

    return result


# ── 3. DIMENSIONALITY REDUCTION & FEATURE SELECTION ───────────────────────


@dataclass
class FeatureSelectionResult:
    """Result of feature selection process."""

    selected_features: list[str]
    dropped_features: list[str]
    importances: dict[str, float]
    pca_components: int | None = None
    pca_explained_variance: float | None = None


def select_features_by_importance(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    top_k: int = 20,
    importance_threshold: float = 0.0,
) -> FeatureSelectionResult:
    """Select top features using LightGBM feature importance.

    Trains a fast LightGBM model and uses split importance to rank features.
    Selects top_k features or those above importance_threshold.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target vector.
        feature_names: Names of features.
        top_k: Maximum number of features to select.
        importance_threshold: Minimum importance to retain.

    Returns:
        FeatureSelectionResult with selected/dropped features.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM not available — skipping feature selection")
        return FeatureSelectionResult(
            selected_features=feature_names,
            dropped_features=[],
            importances={},
        )

    model = lgb.LGBMClassifier(
        n_estimators=50,
        max_depth=4,
        learning_rate=0.1,
        verbose=-1,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=1,
    )

    model.fit(X, y)
    importances = model.feature_importances_

    # Create importance dict
    imp_dict = dict(zip(feature_names, importances, strict=False))
    sorted_features = sorted(imp_dict.items(), key=lambda x: x[1], reverse=True)

    # Select top_k above threshold
    selected = [
        f for f, imp in sorted_features[:top_k]
        if imp >= importance_threshold
    ]
    dropped = [f for f in feature_names if f not in selected]

    return FeatureSelectionResult(
        selected_features=selected,
        dropped_features=dropped,
        importances=imp_dict,
    )


def apply_pca_to_block(
    X_block: np.ndarray,
    n_components: int | None = None,
    variance_threshold: float = 0.95,
) -> tuple[np.ndarray, int, float]:
    """Apply PCA to a block of features (e.g., exogenous features).

    Reduces dimensionality while retaining variance_threshold of variance.

    Args:
        X_block: Feature block matrix (n_samples, n_block_features).
        n_components: Fixed number of components (if None, auto-select).
        variance_threshold: Minimum cumulative variance to retain.

    Returns:
        Tuple of (transformed_matrix, n_components_used, explained_variance).
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    if X_block.shape[1] <= 2:
        return X_block, X_block.shape[1], 1.0

    # Standardize before PCA
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_block)

    if n_components is None:
        # Start with all components, then select
        pca_full = PCA()
        pca_full.fit(X_scaled)
        cumvar = np.cumsum(pca_full.explained_variance_ratio_)
        n_components = int(np.searchsorted(cumvar, variance_threshold) + 1)
        n_components = max(1, min(n_components, X_block.shape[1]))

    pca = PCA(n_components=n_components)
    X_transformed = pca.fit_transform(X_scaled)

    explained = float(
        np.sum(pca.explained_variance_ratio_[:n_components])
    )

    return X_transformed, n_components, explained


# ── 4. UNIFIED FEATURE MATRIX BUILDER ─────────────────────────────────────


@dataclass
class FeatureMatrix:
    """Unified feature matrix for multi-factor ML model."""

    endogenous: pd.DataFrame
    exogenous: pd.DataFrame
    combined: pd.DataFrame
    feature_names: list[str]
    endogenous_names: list[str]
    exogenous_names: list[str]
    selection_result: FeatureSelectionResult | None = None
    pca_result: tuple[int, float] | None = None


class MultiFactorFeaturePipeline:
    """Builds unified feature matrix from endogenous + exogenous factors.

    Pipeline steps:
    1. Compute endogenous features (price patterns, technical indicators)
    2. Compute exogenous features (global market returns, correlations)
    3. Apply PCA to exogenous block (dimensionality reduction)
    4. Combine into unified matrix
    5. Optionally select top features via LightGBM importance

    All operations are strictly non-look-ahead.
    """

    def __init__(
        self,
        horizon: int = 5,
        use_pca: bool = True,
        pca_variance: float = 0.95,
        top_k_features: int = 25,
    ) -> None:
        self.horizon = horizon
        self.use_pca = use_pca
        self.pca_variance = pca_variance
        self.top_k_features = top_k_features

    def build(
        self,
        df: pd.DataFrame,
        global_data: dict[str, pd.DataFrame] | None = None,
        as_of: pd.Timestamp | None = None,
        select_features: bool = False,
    ) -> FeatureMatrix:
        """Build unified feature matrix.

        Args:
            df: Ticker OHLCV DataFrame (adjusted prices).
            global_data: Dict of global asset DataFrames.
            as_of: Cutoff date for non-look-ahead.
            select_features: If True, run feature selection.

        Returns:
            FeatureMatrix with all components.
        """
        if as_of is not None:
            df = df.loc[:as_of].copy()

        # Step 1: Endogenous features
        endo = compute_endogenous_features(df)

        # Step 2: Exogenous features
        if global_data:
            exo = compute_exogenous_features(df, global_data, as_of)
        else:
            exo = pd.DataFrame(index=df.index)

        # Step 3: Define feature column names
        endo_names = [
            "acf_1", "acf_5", "acf_10",
            "body_ratio", "upper_shadow", "lower_shadow",
            "doji_score", "hammer_score", "marubozu_score", "gap",
            "bb_width", "bb_pct", "bb_squeeze",
            "macd_hist_norm", "macd_line_norm",
            "rsi", "momentum_5", "momentum_10", "roc_20",
            "ma_ratio", "ma_5_slope",
            "atr_pct", "hl_range_pct", "vol_regime",
            "close_to_high", "close_to_low",
            "vol_ratio", "vol_trend",
            "vwap_ratio", "price_accel",
        ]
        # Filter to columns that exist
        endo_names = [c for c in endo_names if c in endo.columns]

        exo_names = [c for c in exo.columns if c not in ["close"]]

        # Step 4: Add target (forward return)
        close = df["close"].astype(float)
        endo["forward_return"] = close.shift(-self.horizon) / close - 1
        endo["target_3class"] = self._make_3class_target(endo["forward_return"])

        # Step 5: Combine
        combined = endo.copy()
        for col in exo_names:
            combined[col] = exo[col]

        all_features = endo_names + exo_names

        # Step 6: Optional PCA on exogenous block
        pca_result = None
        if self.use_pca and len(exo_names) > 2:
            exo_data = exo[exo_names].fillna(0.0).values
            if len(exo_data) > 10:
                X_pca, n_comp, explained = apply_pca_to_block(
                    exo_data, variance_threshold=self.pca_variance,
                )
                pca_result = (n_comp, explained)
                # Replace exogenous columns with PCA components
                for i in range(n_comp):
                    combined[f"pca_exo_{i}"] = X_pca[:, i]
                # Remove original exogenous names, add PCA names
                all_features = endo_names + [
                    f"pca_exo_{i}" for i in range(n_comp)
                ]

        # Step 7: Optional feature selection
        selection_result = None
        if select_features and len(all_features) > self.top_k_features:
            # Prepare data for selection
            train_data = combined[[*all_features, "target_3class"]].dropna()
            if len(train_data) > 50:
                X_sel = train_data[all_features].values
                y_sel = train_data["target_3class"].values
                selection_result = select_features_by_importance(
                    X_sel, y_sel, all_features,
                    top_k=self.top_k_features,
                )
                all_features = selection_result.selected_features

        return FeatureMatrix(
            endogenous=endo,
            exogenous=exo,
            combined=combined,
            feature_names=all_features,
            endogenous_names=endo_names,
            exogenous_names=exo_names,
            selection_result=selection_result,
            pca_result=pca_result,
        )

    @staticmethod
    def _make_3class_target(
        forward_return: pd.Series,
        up_threshold: float = 0.01,
        down_threshold: float = -0.01,
    ) -> pd.Series:
        """Convert forward returns to 3-class target: BUY(2), HOLD(1), SELL(0).

        Args:
            forward_return: Forward return series.
            up_threshold: Return above this → BUY.
            down_threshold: Return below this → SELL.

        Returns:
            Integer series with 0 (SELL), 1 (HOLD), 2 (BUY).
        """
        result = pd.Series(1, index=forward_return.index, dtype=int)
        result[forward_return > up_threshold] = 2  # BUY
        result[forward_return < down_threshold] = 0  # SELL
        result[forward_return.isna()] = -1  # Unknown (will be dropped)
        return result


# ── 5. MULTI-FACTOR ML MODEL (LightGBM 3-class) ──────────────────────────


@dataclass
class MultiFactorPrediction:
    """Prediction from multi-factor model."""

    action: str  # "BUY", "SELL", "HOLD"
    action_code: int  # 2=BUY, 0=SELL, 1=HOLD
    probabilities: dict[str, float]  # {BUY: p, HOLD: p, SELL: p}
    signal: float  # -1.0 (sell) to 1.0 (buy)
    confidence: float  # 0.0 to 1.0
    n_train_samples: int
    model_available: bool
    top_features: dict[str, float] = field(default_factory=dict)


class MultiFactorModel:
    """Multi-factor ML model using LightGBM for BUY/SELL/HOLD decisions.

    Uses the MultiFactorFeaturePipeline to build features, then trains
    a 3-class LightGBM classifier with walk-forward CV.

    The model combines:
    - Endogenous price pattern features (30+ features)
    - Exogenous global market features (reduced via PCA)
    - Feature selection via LightGBM importance

    Training is strictly non-look-ahead: only data up to as_of is used.
    """

    def __init__(
        self,
        horizon: int = 5,
        min_train_samples: int = 200,
        n_estimators: int = 200,
        max_depth: int = 4,
        learning_rate: float = 0.03,
        min_data_in_leaf: int = 80,
        reg_alpha: float = 0.2,
        reg_lambda: float = 3.0,
        subsample: float = 0.7,
        colsample_bytree: float = 0.7,
        use_pca: bool = False,
        select_features: bool = True,
        top_k_features: int = 40,
        early_stopping_rounds: int = 25,
        min_gain_to_split: float = 0.01,
    ) -> None:
        self.horizon = horizon
        self.min_train_samples = min_train_samples
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.min_data_in_leaf = min_data_in_leaf
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.early_stopping_rounds = early_stopping_rounds
        self.min_gain_to_split = min_gain_to_split
        self.pipeline = MultiFactorFeaturePipeline(
            horizon=horizon,
            use_pca=use_pca,
            top_k_features=top_k_features,
        )
        self.select_features = select_features
        self._models: dict[str, object] = {}
        self._feature_names: dict[str, list[str]] = {}

    def train_and_predict(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str | pd.Timestamp,
        global_data: dict[str, pd.DataFrame] | None = None,
    ) -> MultiFactorPrediction:
        """Train model on data up to as_of, then predict action.

        Args:
            ticker: Instrument ticker.
            df: Full OHLCV DataFrame (adjusted prices).
            as_of: Cutoff date — only data <= as_of used for training.
            global_data: Dict of global asset DataFrames.

        Returns:
            MultiFactorPrediction with BUY/SELL/HOLD and probabilities.
        """
        cutoff = pd.Timestamp(as_of)

        # Build feature matrix
        fmatrix = self.pipeline.build(
            df, global_data=global_data, as_of=cutoff,
            select_features=self.select_features,
        )

        feature_cols = fmatrix.feature_names
        if not feature_cols:
            return self._fallback_prediction(0, False)

        # Get training data (up to cutoff, drop NaN targets)
        train_data = fmatrix.combined.loc[:cutoff].copy()
        train_data = train_data[
            train_data["target_3class"] >= 0
        ].dropna(subset=feature_cols)

        if len(train_data) < self.min_train_samples:
            logger.debug(
                "MultiFactor for %s: insufficient data (%d < %d)",
                ticker, len(train_data), self.min_train_samples,
            )
            return self._fallback_prediction(
                len(train_data), False,
            )

        try:
            import lightgbm as lgb
        except ImportError:
            logger.warning("LightGBM not available — MultiFactor disabled")
            return self._fallback_prediction(len(train_data), False)

        X_train = train_data[feature_cols].values
        y_train = train_data["target_3class"].values

        # Walk-forward CV: use mlops.cross_validation for consistent splitting
        from market.mlops.cross_validation import walk_forward_splits
        splits = walk_forward_splits(
            n_samples=len(X_train),
            train_size=int(len(X_train) * 0.8),
            test_size=len(X_train) - int(len(X_train) * 0.8),
        )
        if splits:
            split = splits[0]
            X_tr = X_train[split.train_start:split.train_end]
            y_tr = y_train[split.train_start:split.train_end]
            X_val = X_train[split.test_start:split.test_end]
            y_val = y_train[split.test_start:split.test_end]
        else:
            split_idx = int(len(X_train) * 0.8)
            X_tr, X_val = X_train[:split_idx], X_train[split_idx:]
            y_tr, y_val = y_train[:split_idx], y_train[split_idx:]

        model = lgb.LGBMClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            min_data_in_leaf=self.min_data_in_leaf,
            reg_alpha=self.reg_alpha,
            reg_lambda=self.reg_lambda,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            min_gain_to_split=self.min_gain_to_split,
            verbose=-1,
            n_jobs=1,
            num_classes=3,
            objective="multiclass",
        )

        model.fit(
            X_tr, y_tr,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
        )

        # Predict on latest available row
        latest = fmatrix.combined.loc[:cutoff].iloc[-1:]
        if latest.empty:
            return self._fallback_prediction(len(train_data), True)

        X_pred = latest[feature_cols].values
        if np.any(np.isnan(X_pred)):
            return self._fallback_prediction(len(train_data), True)

        proba = model.predict_proba(X_pred)[0]
        # Classes: 0=SELL, 1=HOLD, 2=BUY
        action_code = int(np.argmax(proba))
        action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        action = action_map[action_code]

        # Signal: -1 (sell) to +1 (buy)
        signal = float(proba[2] - proba[0])

        # Confidence: max probability
        confidence = float(max(proba))

        # Validation accuracy
        val_preds = model.predict(X_val)
        val_acc = float(
            (val_preds == y_val).mean()
        ) if len(y_val) > 0 else 0.5

        # Top features
        importances = model.feature_importances_
        imp_dict = dict(zip(feature_cols, importances, strict=False))
        top_features = dict(
            sorted(imp_dict.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        self._models[ticker] = model
        self._feature_names[ticker] = feature_cols

        logger.debug(
            "MultiFactor %s: action=%s, signal=%.3f, conf=%.3f, val_acc=%.3f, "
            "n_train=%d, n_features=%d",
            ticker, action, signal, confidence, val_acc,
            len(train_data), len(feature_cols),
        )

        return MultiFactorPrediction(
            action=action,
            action_code=action_code,
            probabilities={
                "SELL": float(proba[0]),
                "HOLD": float(proba[1]),
                "BUY": float(proba[2]),
            },
            signal=signal,
            confidence=confidence * val_acc,  # Combined confidence
            n_train_samples=len(train_data),
            model_available=True,
            top_features=top_features,
        )

    @staticmethod
    def _fallback_prediction(
        n_samples: int, model_available: bool,
    ) -> MultiFactorPrediction:
        """Return neutral HOLD prediction when model unavailable."""
        return MultiFactorPrediction(
            action="HOLD",
            action_code=1,
            probabilities={"SELL": 0.33, "HOLD": 0.34, "BUY": 0.33},
            signal=0.0,
            confidence=0.0,
            n_train_samples=n_samples,
            model_available=model_available,
        )
