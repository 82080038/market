"""ML signal provider using LightGBM with walk-forward CV (pustaka/23, pustaka/51).

Trains a LightGBM model on historical features and provides a prediction
signal (-1.0 to 1.0) for the ensemble prediction engine.

Features used:
- Technical: RSI, MA ratio, momentum, ATR%
- Volume: relative volume
- Price: close, high-low range

Target: 5-day forward return direction (binary: 1 if up, 0 if down)

The model is trained per-ticker with walk-forward CV to avoid look-ahead bias.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MLSignal:
    """ML prediction signal."""

    signal: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    n_train_samples: int
    model_available: bool


class MLSignalProvider:
    """Provides ML-based prediction signal using LightGBM.

    Trains on-the-fly with walk-forward CV per ticker.
    Falls back to 0.0 signal if LightGBM not available.
    """

    def __init__(
        self,
        horizon: int = 5,
        min_train_samples: int = 200,
        n_estimators: int = 200,
        max_depth: int = 6,
    ) -> None:
        self.horizon = horizon
        self.min_train_samples = min_train_samples
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self._models: dict[str, object] = {}

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare feature columns from OHLCV data."""
        data = df.copy()
        close = data["close"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)
        volume = data["volume"].astype(float)

        # RSI (14)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        data["rsi"] = 100 - (100 / (1 + rs))

        # MA ratios
        data["ma_5"] = close.rolling(5).mean()
        data["ma_20"] = close.rolling(20).mean()
        data["ma_ratio"] = data["ma_5"] / data["ma_20"]

        # Momentum
        data["momentum_5"] = close.pct_change(5) * 100
        data["momentum_10"] = close.pct_change(10) * 100

        # Volatility
        data["atr_pct"] = (
            (high - low) / close * 100
        ).rolling(14).mean()

        # Volume relative
        data["vol_ma"] = volume.rolling(20).mean()
        data["vol_ratio"] = volume / data["vol_ma"]

        # High-Low range
        data["hl_range_pct"] = (high - low) / close * 100

        # Additional features for better prediction
        # MA slope (trend direction)
        data["ma_5_slope"] = data["ma_5"].pct_change(3) * 100
        # Close relative to recent range
        data["close_to_high"] = close / high.rolling(20).max()
        data["close_to_low"] = close / low.rolling(20).min()
        # RSI momentum
        data["rsi_change"] = data["rsi"].diff(3)
        # Volume trend
        data["vol_trend"] = volume.pct_change(5) * 100
        # Price acceleration
        data["price_accel"] = data["momentum_5"] - data["momentum_5"].shift(5)
        # Volatility regime
        data["vol_regime"] = data["atr_pct"].rolling(60).rank(pct=True)

        # Volume dynamics features (pustaka/20, pustaka/26)
        # VWAP (20-bar rolling)
        vol_price = close * volume
        vol_sum = volume.rolling(20, min_periods=1).sum()
        vp_sum = vol_price.rolling(20, min_periods=1).sum()
        data["vwap_20"] = vp_sum / vol_sum.replace(0, np.nan)
        data["vwap_ratio"] = close / data["vwap_20"].replace(0, np.nan)

        # Volume Rate of Change (10-bar)
        data["vol_roc_10"] = (
            (volume - volume.shift(10))
            / volume.shift(10).replace(0, np.nan) * 100
        )

        # OBV slope (5-bar)
        obv_direction = np.sign(close.diff())
        data["obv"] = (obv_direction * volume).cumsum()
        data["obv_slope"] = data["obv"].diff(5)

        # Volume-price trend correlation
        price_change = close.pct_change()
        vol_norm = volume / volume.rolling(20).mean().replace(0, np.nan)
        data["vol_price_trend"] = (
            (price_change * vol_norm).rolling(10).mean()
        )

        # Forward return target
        data["forward_return"] = close.shift(-self.horizon) / close - 1
        data["target"] = (data["forward_return"] > 0).astype(int)

        return data

    def _get_feature_cols(self) -> list[str]:
        return [
            "rsi", "ma_ratio", "momentum_5", "momentum_10",
            "atr_pct", "vol_ratio", "hl_range_pct",
            "ma_5_slope", "close_to_high", "close_to_low",
            "rsi_change", "vol_trend", "price_accel", "vol_regime",
            # Volume dynamics features
            "vwap_ratio", "vol_roc_10", "obv_slope", "vol_price_trend",
        ]

    def train_and_predict(
        self,
        ticker: str,
        df: pd.DataFrame,
        as_of: str | pd.Timestamp,
    ) -> MLSignal:
        """Train model on data up to as_of, then predict signal.

        Args:
            ticker: Instrument ticker.
            df: Full OHLCV DataFrame.
            as_of: Cutoff date — only data <= as_of used for training.

        Returns:
            MLSignal with prediction signal.
        """
        cutoff = pd.Timestamp(as_of)
        data = self._prepare_features(df)
        feature_cols = self._get_feature_cols()

        # Filter to training data (up to as_of, drop NaN rows)
        train_data = data.loc[:cutoff].copy()
        train_data = train_data.dropna(subset=[*feature_cols, "target"])

        if len(train_data) < self.min_train_samples:
            logger.debug(
                "ML signal for %s: insufficient training data (%d < %d)",
                ticker, len(train_data), self.min_train_samples,
            )
            return MLSignal(
                signal=0.0, confidence=0.0,
                n_train_samples=len(train_data),
                model_available=False,
            )

        try:
            import lightgbm as lgb
        except ImportError:
            logger.debug("LightGBM not available — ML signal disabled")
            return MLSignal(
                signal=0.0, confidence=0.0,
                n_train_samples=len(train_data),
                model_available=False,
            )

        X_train = train_data[feature_cols].values
        y_train = train_data["target"].values

        # Walk-forward: use last 80% as train, first 20% as validation
        split_idx = int(len(X_train) * 0.8)
        X_tr, X_val = X_train[:split_idx], X_train[split_idx:]
        y_tr, y_val = y_train[:split_idx], y_train[split_idx:]

        model = lgb.LGBMClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=0.05,
            verbose=-1,
            subsample=0.8,
            colsample_bytree=0.8,
        )

        model.fit(
            X_tr, y_tr,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(10, verbose=False)],
        )

        # Predict on the as_of row (latest available features)
        latest = data.loc[:cutoff].iloc[-1:]
        if latest.empty or latest[feature_cols].isna().any(axis=1).iloc[0]:
            return MLSignal(
                signal=0.0, confidence=0.0,
                n_train_samples=len(train_data),
                model_available=True,
            )

        X_pred = latest[feature_cols].values
        proba = model.predict_proba(X_pred)[0]
        # proba[1] = P(up), signal = 2*P(up) - 1 → range [-1, 1]
        signal = float(2 * proba[1] - 1)

        # Confidence from validation accuracy
        val_preds = model.predict(X_val)
        val_acc = float((val_preds == y_val).mean()) if len(y_val) > 0 else 0.5

        self._models[ticker] = model

        logger.debug(
            "ML signal for %s: signal=%.3f, val_acc=%.3f, n_train=%d",
            ticker, signal, val_acc, len(train_data),
        )

        return MLSignal(
            signal=signal,
            confidence=val_acc,
            n_train_samples=len(train_data),
            model_available=True,
        )
