"""ML signal provider using LightGBM with walk-forward CV (pustaka/23, pustaka/51).

Trains a LightGBM model on historical features and provides a prediction
signal (-1.0 to 1.0) for the ensemble prediction engine.

Features used:
- Technical: RSI, MA ratio, momentum, ATR%
- Volume: relative volume
- Price: close, high-low range
- Regime: trend regime label (ADX-based)

Target: Triple-barrier labels (López de Prado Ch. 3):
  - 1 = take-profit hit (upward barrier)
  - 0 = vertical/time barrier (neutral)
  - -1 = stop-loss hit (downward barrier)
  Binary mode: 1 = up barrier hit, 0 = down or vertical barrier

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
        n_estimators: int = 300,
        max_depth: int = 5,
        min_data_in_leaf: int = 60,
        reg_alpha: float = 0.15,
        reg_lambda: float = 2.0,
        learning_rate: float = 0.03,
        subsample: float = 0.7,
        colsample_bytree: float = 0.7,
        early_stopping_rounds: int = 20,
        min_gain_to_split: float = 0.01,
        use_triple_barrier: bool = True,
        tp_barrier: float = 0.015,
        sl_barrier: float = 0.015,
        use_atr_barriers: bool = True,
        atr_multiplier: float = 1.5,
    ) -> None:
        self.horizon = horizon
        self.min_train_samples = min_train_samples
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_data_in_leaf = min_data_in_leaf
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.learning_rate = learning_rate
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.early_stopping_rounds = early_stopping_rounds
        self.min_gain_to_split = min_gain_to_split
        self.use_triple_barrier = use_triple_barrier
        self.tp_barrier = tp_barrier
        self.sl_barrier = sl_barrier
        self.use_atr_barriers = use_atr_barriers
        self.atr_multiplier = atr_multiplier
        self._models: dict[str, object] = {}

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare feature columns from OHLCV data."""
        data = df.copy()
        close = data["close"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)
        volume = data["volume"].astype(float)

        # RSI (14) — remediated: use rsi_rank (rolling percentile) for regime stability
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        data["rsi"] = 100 - (100 / (1 + rs))
        data["rsi_rank"] = data["rsi"].rolling(60, min_periods=20).rank(pct=True)

        # MA ratios — remediated: use ma_ratio_zscore for regime stability
        data["ma_5"] = close.rolling(5).mean()
        data["ma_20"] = close.rolling(20).mean()
        data["ma_ratio"] = data["ma_5"] / data["ma_20"]
        ma_ratio_mean = data["ma_ratio"].rolling(60, min_periods=20).mean()
        ma_ratio_std = data["ma_ratio"].rolling(60, min_periods=20).std()
        data["ma_ratio_zscore"] = (
            (data["ma_ratio"] - ma_ratio_mean) / ma_ratio_std.replace(0, np.nan)
        )

        # Momentum
        data["momentum_5"] = close.pct_change(5) * 100
        data["momentum_10"] = close.pct_change(10) * 100

        # Volatility — remediated: use vol_pctile (rolling percentile) for regime stability
        data["atr_pct"] = (
            (high - low) / close * 100
        ).rolling(14).mean()
        data["vol_pctile"] = data["atr_pct"].rolling(60, min_periods=20).rank(pct=True)

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

        # ADX-based trend regime (pustaka/23 §5)
        # Simple proxy: 20-bar directional movement strength
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        atr_val = (high - low).rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / atr_val.replace(0, np.nan)
        minus_di = 100 * minus_dm.rolling(14).mean() / atr_val.replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(14).mean()
        data["trend_regime"] = (adx > 25).astype(int)  # 1 = trending, 0 = ranging

        # Target: triple-barrier labels (López de Prado)
        if self.use_triple_barrier:
            data["target"] = self._compute_triple_barrier_labels(data)
        else:
            # Fallback: simple binary up/down
            data["forward_return"] = close.shift(-self.horizon) / close - 1
            data["target"] = (data["forward_return"] > 0).astype(int)

        return data

    def _compute_triple_barrier_labels(self, data: pd.DataFrame) -> pd.Series:
        """Compute triple-barrier labels (López de Prado Ch. 3).

        For each bar, simulate forward H bars and check which barrier is hit first:
        - Upper barrier (take-profit): +tp_barrier or ATR * atr_multiplier
        - Lower barrier (stop-loss): -sl_barrier or -ATR * atr_multiplier
        - Vertical barrier (time): H bars elapsed → neutral

        Returns binary target: 1 = upper barrier hit, 0 = lower or vertical.
        """
        close = data["close"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)
        n = len(close)
        labels = pd.Series(0, index=data.index, dtype=int)

        # Compute ATR for dynamic barriers
        if self.use_atr_barriers:
            atr = (high - low).rolling(14).mean()
            tp = atr * self.atr_multiplier
            sl = atr * self.atr_multiplier
        else:
            tp = pd.Series(self.tp_barrier, index=data.index)
            sl = pd.Series(self.sl_barrier, index=data.index)

        for i in range(n - self.horizon):
            entry_price = float(close.iloc[i])
            tp_val = float(tp.iloc[i]) if not np.isnan(tp.iloc[i]) else self.tp_barrier
            sl_val = float(sl.iloc[i]) if not np.isnan(sl.iloc[i]) else self.sl_barrier

            for j in range(1, self.horizon + 1):
                ret = (float(close.iloc[i + j]) - entry_price) / entry_price
                if ret >= tp_val:
                    labels.iloc[i] = 1  # take-profit hit
                    break
                elif ret <= -sl_val:
                    labels.iloc[i] = 0  # stop-loss hit
                    break
            # If neither barrier hit within horizon → vertical barrier → 0 (neutral/down)
            # Labels[i] stays 0 for vertical barrier

        return labels

    def _get_feature_cols(self) -> list[str]:
        return [
            # Remediated features (regime-stable)
            "rsi_rank", "ma_ratio_zscore", "vol_pctile",
            # Original features (kept for signal)
            "rsi", "ma_ratio", "momentum_5", "momentum_10",
            "atr_pct", "vol_ratio", "hl_range_pct",
            "ma_5_slope", "close_to_high", "close_to_low",
            "rsi_change", "vol_trend", "price_accel", "vol_regime",
            # Volume dynamics features
            "vwap_ratio", "vol_roc_10", "obv_slope", "vol_price_trend",
            # Regime feature (P3-2)
            "trend_regime",
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

        # Walk-forward CV: use mlops.cross_validation for consistent splitting
        from market.mlops.cross_validation import walk_forward_splits
        splits = walk_forward_splits(
            n_samples=len(X_train),
            train_size=int(len(X_train) * 0.8),
            test_size=len(X_train) - int(len(X_train) * 0.8),
        )
        if splits:
            split = splits[0]  # First (and only) split: 80/20
            X_tr = X_train[split.train_start:split.train_end]
            y_tr = y_train[split.train_start:split.train_end]
            X_val = X_train[split.test_start:split.test_end]
            y_val = y_train[split.test_start:split.test_end]
        else:
            # Fallback to simple split
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
        )

        model.fit(
            X_tr, y_tr,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
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
