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

# Module-level cache for global asset data (loaded once per process)
_global_data_cache: dict[str, pd.DataFrame] | None = None
_cpi_series_cache: pd.Series | None = None


def _load_global_data_cache() -> dict[str, pd.DataFrame]:
    """Load all global asset OHLCV data once and cache for the process lifetime."""
    global _global_data_cache
    if _global_data_cache is not None:
        return _global_data_cache

    from market.db.raw import get_raw_connection, _PgConnWrapper

    def _raw_conn(c):
        return c._conn if isinstance(c, _PgConnWrapper) else c

    from market.analysis.multi_factor import GLOBAL_ASSETS

    cache: dict[str, pd.DataFrame] = {}
    try:
        with get_raw_connection() as conn:
            rc = _raw_conn(conn)
            for gticker in GLOBAL_ASSETS:
                try:
                    gdf = pd.read_sql(
                        f"SELECT timestamp as date, close FROM ohlcv WHERE ticker='{gticker}' ORDER BY timestamp",
                        rc,
                    )
                    if not gdf.empty:
                        gdf["date"] = pd.to_datetime(gdf["date"])
                        gdf = gdf.set_index("date").sort_index()
                        if not gdf.index.is_unique:
                            gdf = gdf[~gdf.index.duplicated(keep="last")]
                        cache[gticker] = gdf
                except Exception:
                    pass
    except Exception as e:
        logger.debug("global data cache load failed: %s", e)

    _global_data_cache = cache
    logger.info("Global data cache loaded: %d/%d assets", len(cache), len(GLOBAL_ASSETS))
    return cache


def _load_cpi_series_cache() -> pd.Series | None:
    """Load Indonesia CPI series once and cache for the process lifetime."""
    global _cpi_series_cache
    if _cpi_series_cache is not None:
        return _cpi_series_cache

    from market.db.raw import get_raw_connection, _PgConnWrapper

    def _raw_conn(c):
        return c._conn if isinstance(c, _PgConnWrapper) else c

    try:
        with get_raw_connection() as conn:
            rc = _raw_conn(conn)
            cpi_df = pd.read_sql(
                "SELECT date, value FROM macro_data WHERE series_name='ID_CPI' ORDER BY date",
                rc,
            )
            if not cpi_df.empty:
                cpi_df["date"] = pd.to_datetime(cpi_df["date"])
                cpi_df = cpi_df.set_index("date").sort_index()
                _cpi_series_cache = cpi_df["value"]
    except Exception:
        pass

    return _cpi_series_cache


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

    P6: Ticker-specific profiles — each ticker has different optimal horizon,
    model complexity, and feature subsets based on its volatility/autocorrelation pattern.
    """

    # P6: Ticker-specific profiles based on pattern analysis
    # Key insight: each ticker has different autocorrelation, trend, and direction bias
    TICKER_PROFILES = {
        # Downtrend banking — down predictions more accurate, use shorter horizon
        "BBCA.JK": {"horizon": 5, "max_depth": 4, "min_data_in_leaf": 80, "n_estimators": 200},
        "BBRI.JK": {"horizon": 5, "max_depth": 4, "min_data_in_leaf": 80, "n_estimators": 200},
        # Balanced — keep defaults
        "UNVR.JK": {"horizon": 7, "max_depth": 5, "min_data_in_leaf": 60, "n_estimators": 300},
        # Uptrend momentum — up predictions strong, use longer horizon
        "ANTM.JK": {"horizon": 7, "max_depth": 5, "min_data_in_leaf": 60, "n_estimators": 300},
        # High vol, up-biased — need more regularization
        "MDKA.JK": {"horizon": 5, "max_depth": 3, "min_data_in_leaf": 100, "n_estimators": 200},
        # Mean-reverting — shorter horizon captures reversal better
        "UNTR.JK": {"horizon": 3, "max_depth": 4, "min_data_in_leaf": 80, "n_estimators": 200},
        # Mean-revert + strong downtrend — shorter horizon
        "APLI.JK": {"horizon": 3, "max_depth": 4, "min_data_in_leaf": 80, "n_estimators": 200},
        # Strong mean-revert — very short horizon
        "BCIC.JK": {"horizon": 3, "max_depth": 3, "min_data_in_leaf": 100, "n_estimators": 200},
        # Moderate vol, balanced
        "INCO.JK": {"horizon": 5, "max_depth": 5, "min_data_in_leaf": 60, "n_estimators": 300},
        # High vol, strong uptrend, balanced
        "KRAS.JK": {"horizon": 7, "max_depth": 5, "min_data_in_leaf": 60, "n_estimators": 300},
    }

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
        use_precomputed_labels: bool = False,
        db_path: str | None = None,
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
        self.use_precomputed_labels = use_precomputed_labels
        self._db_path = db_path
        self.use_regime_conditional = False  # P4-1: disabled — reduces training samples too much
        self._models: dict[str, object] = {}
        self._regime_models: dict[str, dict[int, object]] = {}  # ticker → {regime_label: model}

    def _prepare_features(self, df: pd.DataFrame, ticker: str | None = None) -> pd.DataFrame:
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

        # P4-2: Feature interactions — cross-features for non-linear patterns
        data["rsi_x_vol"] = data["rsi"] * data["vol_ratio"]
        data["momentum_x_regime"] = data["momentum_5"] * data["trend_regime"]
        data["ma_ratio_x_vol_pctile"] = data["ma_ratio"] * data["vol_pctile"]
        data["rsi_rank_x_regime"] = data["rsi_rank"] * data["trend_regime"]

        # P7: Exogenous ecosystem features
        # Load from DB: USD/IDR FX, Shanghai Composite, Indonesia CPI, corporate actions
        data = self._add_exogenous_features(data, ticker=ticker)

        # Target: triple-barrier labels (López de Prado)
        if self.use_precomputed_labels and ticker is not None:
            data["target"] = self._load_precomputed_labels(data, ticker)
        elif self.use_triple_barrier:
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

        P4-4: ATR multiplier adapts to ticker's volatility percentile —
        high-volatility tickers get wider barriers (2.0x), low-vol get tighter (1.0x).

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
            # P4-4: Adaptive multiplier based on ATR percentile
            atr_pctile = atr.rolling(120, min_periods=60).rank(pct=True)
            # Low vol (pctile < 0.3) → 1.0x, Mid → 1.5x, High vol (pctile > 0.7) → 2.0x
            adaptive_mult = atr_pctile.map(
                lambda p: 1.0 if p < 0.3 else (2.0 if p > 0.7 else 1.5)
            ).fillna(1.5)
            tp = atr * adaptive_mult
            sl = atr * adaptive_mult
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

    def _load_precomputed_labels(self, data: pd.DataFrame, ticker: str) -> pd.Series:
        """Load pre-computed triple-barrier labels from ml_labels table.

        Maps direction to binary target:
          'up' → 1 (take-profit hit)
          'down'/'static' → 0 (stop-loss or time expired)

        Falls back to on-the-fly computation if DB unavailable or no data.
        """
        from market.db.raw import execute_query

        try:
            rows = execute_query(
                "SELECT date, direction FROM ml_labels WHERE ticker=? AND horizon=? ORDER BY date",
                (ticker, self.horizon),
            )

            if not rows:
                logger.debug(
                    "ml_labels: no precomputed labels for %s h=%d, falling back",
                    ticker, self.horizon,
                )
                return self._compute_triple_barrier_labels(data)

            label_map = {d: 1 if direction == "up" else 0 for d, direction in rows}
            labels = pd.Series(0, index=data.index, dtype=int)
            for ts in data.index:
                date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
                if date_str in label_map:
                    labels[ts] = label_map[date_str]

            logger.debug(
                "ml_labels: loaded %d labels for %s h=%d (%d up, %d down/static)",
                len(rows), ticker, self.horizon,
                sum(1 for _, d in rows if d == "up"),
                sum(1 for _, d in rows if d != "up"),
            )
            return labels
        except Exception as e:
            logger.debug("ml_labels load failed for %s: %s, falling back", ticker, e)
            return self._compute_triple_barrier_labels(data)

    def _add_exogenous_features(self, data: pd.DataFrame, ticker: str | None = None) -> pd.DataFrame:
        """P7: Add exogenous ecosystem features from DB with timezone-aware lag.

        Uses ``compute_exogenous_features()`` from ``multi_factor.py`` which
        applies asymmetric T-0/T-1 lag per ticker to prevent look-ahead bias:
        - Asian markets (^N225, ^HSI): T-0 (close before IDX → same-day valid)
        - US markets (^GSPC, ^VIX, ^TNX): T-1 (close after IDX → prev day only)
        - Commodities (GC=F, CL=F, HG=F, CPO=F): T-1 (US-centric settle)

        Also loads:
        - Indonesia CPI (inflation, monthly → forward-filled)
        - Corporate action event flags (dividend/split within ±5 days)
        """
        # ── Global market features (cached at module level) ────────────
        try:
            from market.analysis.multi_factor import compute_exogenous_features

            global_data = _load_global_data_cache()
            if global_data:
                exog_df = compute_exogenous_features(
                    data, global_data, as_of=None, lookback=5, corr_window=60,
                )
                for col in exog_df.columns:
                    data[col] = exog_df[col].fillna(0.0)
        except Exception as e:
            logger.debug("compute_exogenous_features failed: %s", e)

        # ── CPI (cached at module level) ────────────────────────────────
        try:
            cpi_series_raw = _load_cpi_series_cache()
            if cpi_series_raw is not None and not cpi_series_raw.empty:
                cpi_series = cpi_series_raw.reindex(data.index, method="ffill")
                cpi_change = cpi_series.pct_change(60)
                data["id_inflation_3m"] = cpi_change.values
            else:
                data["id_inflation_3m"] = 0.0
        except Exception:
            data["id_inflation_3m"] = 0.0

        # ── Corporate action event flags (per-ticker, not cached) ────────
        if ticker:
            from market.db.raw import get_raw_connection, _PgConnWrapper

            def _raw_conn(c):
                return c._conn if isinstance(c, _PgConnWrapper) else c

            try:
                with get_raw_connection() as conn:
                    rc = _raw_conn(conn)
                    try:
                        ca_df = pd.read_sql(
                            f"SELECT ex_date, action_type FROM corporate_actions WHERE ticker='{ticker}' AND ex_date IS NOT NULL",
                            rc,
                        )
                        if not ca_df.empty:
                            ca_df["ex_date"] = pd.to_datetime(ca_df["ex_date"])
                            event_dates = ca_df["ex_date"].values
                            data["has_corp_action"] = 0
                            for ed in event_dates:
                                mask = (data.index >= ed - pd.Timedelta(days=5)) & (data.index <= ed + pd.Timedelta(days=5))
                                data.loc[mask, "has_corp_action"] = 1
                        else:
                            data["has_corp_action"] = 0
                    except Exception:
                        data["has_corp_action"] = 0

                    try:
                        div_df = pd.read_sql(
                            f"SELECT ex_date FROM dividends WHERE ticker='{ticker}' AND ex_date IS NOT NULL",
                            rc,
                        )
                        if not div_df.empty:
                            div_df["ex_date"] = pd.to_datetime(div_df["ex_date"])
                            data["has_dividend"] = 0
                            for ed in div_df["ex_date"].values:
                                mask = (data.index >= ed - pd.Timedelta(days=5)) & (data.index <= ed + pd.Timedelta(days=5))
                                data.loc[mask, "has_dividend"] = 1
                        else:
                            data["has_dividend"] = 0
                    except Exception:
                        data["has_dividend"] = 0
            except Exception:
                data["has_corp_action"] = 0
                data["has_dividend"] = 0
        else:
            data["has_corp_action"] = 0
            data["has_dividend"] = 0

        # Fill NaN for all exogenous features
        exog_cols = [
            "id_inflation_3m", "has_corp_action", "has_dividend",
        ]
        for col in exog_cols:
            if col not in data.columns:
                data[col] = 0.0
            else:
                data[col] = data[col].fillna(0.0)

        return data

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
            # Feature interactions (P4-2)
            "rsi_x_vol", "momentum_x_regime", "ma_ratio_x_vol_pctile",
            "rsi_rank_x_regime",
            # P7: Exogenous ecosystem features (timezone-aware T-0/T-1 lag)
            "sp500_lag1_ret", "sp500_lag5_ret", "sp500_corr",
            "nasdaq_lag1_ret", "nasdaq_lag5_ret", "nasdaq_corr",
            "ftse_lag1_ret", "ftse_lag5_ret", "ftse_corr",
            "nikkei_lag1_ret", "nikkei_lag5_ret", "nikkei_corr",
            "hangseng_lag1_ret", "hangseng_lag5_ret", "hangseng_corr",
            "gold_lag1_ret", "gold_lag5_ret", "gold_corr",
            "oil_wti_lag1_ret", "oil_wti_lag5_ret", "oil_wti_corr",
            "copper_lag1_ret", "copper_lag5_ret", "copper_corr",
            "cpo_lag1_ret", "cpo_lag5_ret", "cpo_corr",
            "id_inflation_3m",
            "has_corp_action", "has_dividend",
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
        
        # P6: Apply ticker-specific profile
        profile = self.TICKER_PROFILES.get(ticker, {})
        effective_horizon = profile.get("horizon", self.horizon)
        effective_max_depth = profile.get("max_depth", self.max_depth)
        effective_min_leaf = profile.get("min_data_in_leaf", self.min_data_in_leaf)
        effective_n_estimators = profile.get("n_estimators", self.n_estimators)
        
        # Temporarily override horizon for feature preparation
        original_horizon = self.horizon
        if effective_horizon != self.horizon:
            self.horizon = effective_horizon
        
        data = self._prepare_features(df, ticker=ticker)
        self.horizon = original_horizon  # restore
        
        feature_cols = self._get_feature_cols()
        # Only keep features that exist in the prepared data (some global assets may be missing)
        feature_cols = [c for c in feature_cols if c in data.columns]

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

        # P4-1: Regime-conditional models — train separate models per regime
        current_regime = int(train_data["trend_regime"].iloc[-1]) if "trend_regime" in train_data.columns else 0

        if self.use_regime_conditional and "trend_regime" in train_data.columns:
            # Train regime-specific models
            regime_models = {}
            val_accuracies = []
            for regime_label in [0, 1]:
                regime_data = train_data[train_data["trend_regime"] == regime_label]
                if len(regime_data) < 50:
                    continue

                X_reg = regime_data[feature_cols].values
                y_reg = regime_data["target"].values

                # Walk-forward split within regime data
                split_idx_r = int(len(X_reg) * 0.8)
                X_tr_r, X_val_r = X_reg[:split_idx_r], X_reg[split_idx_r:]
                y_tr_r, y_val_r = y_reg[:split_idx_r], y_reg[split_idx_r:]

                if len(X_tr_r) < 30 or len(X_val_r) < 10:
                    continue

                model_r = lgb.LGBMClassifier(
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
                model_r.fit(
                    X_tr_r, y_tr_r,
                    eval_X=X_val_r, eval_y=y_val_r,
                    callbacks=[lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
                )
                regime_models[regime_label] = model_r
                val_preds_r = model_r.predict(X_val_r)
                val_acc_r = float((val_preds_r == y_val_r).mean()) if len(y_val_r) > 0 else 0.5
                val_accuracies.append(val_acc_r)

            self._regime_models[ticker] = regime_models

            # Predict with the model matching current regime
            latest = data.loc[:cutoff].iloc[-1:]
            if latest.empty or latest[feature_cols].isna().any(axis=1).iloc[0]:
                return MLSignal(
                    signal=0.0, confidence=0.0,
                    n_train_samples=len(train_data),
                    model_available=True,
                )

            X_pred = latest[feature_cols].values
            if current_regime in regime_models:
                proba = regime_models[current_regime].predict_proba(X_pred)[0]
            elif regime_models:
                # Fallback to any available regime model
                proba = list(regime_models.values())[0].predict_proba(X_pred)[0]
            else:
                return MLSignal(
                    signal=0.0, confidence=0.0,
                    n_train_samples=len(train_data),
                    model_available=True,
                )

            signal = float(2 * proba[1] - 1)
            val_acc = sum(val_accuracies) / len(val_accuracies) if val_accuracies else 0.5

            logger.debug(
                "ML signal for %s: signal=%.3f, val_acc=%.3f, n_train=%d, regime=%d",
                ticker, signal, val_acc, len(train_data), current_regime,
            )

            return MLSignal(
                signal=signal,
                confidence=val_acc,
                n_train_samples=len(train_data),
                model_available=True,
            )

        # Fallback: single model (non-regime-conditional)
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

        # P4-5: Exponential sample weighting — recent samples get more weight
        # Decay factor: 0.995 → half-life ~138 bars (~7 months daily)
        n_tr = len(X_tr)
        sample_weights = np.power(0.995, np.arange(n_tr - 1, -1, -1))
        sample_weights = sample_weights / sample_weights.mean()  # normalize to mean=1

        model = lgb.LGBMClassifier(
            n_estimators=effective_n_estimators,
            max_depth=effective_max_depth,
            learning_rate=self.learning_rate,
            min_data_in_leaf=effective_min_leaf,
            reg_alpha=self.reg_alpha,
            reg_lambda=self.reg_lambda,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            min_gain_to_split=self.min_gain_to_split,
            verbose=-1,
        )

        model.fit(
            X_tr, y_tr,
            sample_weight=sample_weights,
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
