"""Meta-Labeling module — secondary ML model for bet sizing (pustaka/23, pustaka/96).

Implements Marcos López de Prado's meta-labeling technique from
"Advances in Financial Machine Learning" (Chapter 3). The primary prediction
engine (`prediction.py` `_predict_ensemble`) decides the SIDE of a trade
(buy/sell). This meta-model decides the SIZE (0-1, including 0 = no trade) by
predicting the probability that the primary model's bet will be successful.

Components:
1. Triple-Barrier Labeling — label each prediction outcome based on 3 barriers
   (take-profit, stop-loss, vertical/time). Uses ONLY data after the prediction
   date (no look-ahead).
2. Meta-Labeling Model — a LightGBM binary classifier that predicts
   P(primary prediction correct) from features available at prediction time.
3. Bet Sizing — convert meta-model probability to position size [0, 1].
4. CUSUM Filter — sample only events where price change exceeds a
   volatility-scaled threshold, to avoid labeling every bar.

GPU note (AGENTS.md §4): LightGBM is CPU-only here, so no GPU/CUDA check is
needed. If a GPU-accelerated backend is added later, follow AGENTS.md §2
(`cuda:1` check first).

References:
- López de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley.
  Chapter 3: Meta-Labeling and Triple-Barrier Method.
- pustaka/23-machine-learning-trading.md §7.2 (Triple-Barrier),
  §7.3 (Meta-Labeling), §9 (Purged CV).
- pustaka/96-ai-ml-audit-framework.md §3.4 (Walk-Forward).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from market.compute.device import lgbm_device

if TYPE_CHECKING:
    from lightgbm import LGBMClassifier

_lgbm_dev = lgbm_device()

logger = logging.getLogger(__name__)

# ── Default configuration ──────────────────────────────────────────────────

DEFAULT_UPPER_BARRIER = 0.02  # +2% take-profit (or scaled by ATR)
DEFAULT_LOWER_BARRIER = -0.02  # -2% stop-loss (or scaled by ATR)
DEFAULT_VERTICAL_BARRIER = 5  # 5 trading days horizon
DEFAULT_CUSUM_THRESHOLD = 0.02  # 2% cumulative return threshold
DEFAULT_BET_PROB_THRESHOLD = 0.5  # below this → no trade
DEFAULT_MIN_TRAIN_SAMPLES = 200
DEFAULT_PURGE_GAP = 5  # bars purged around train/test boundary
DEFAULT_EMBARGO = 5  # bars embargoed after test fold


# ── 1. Triple-Barrier Labeling ─────────────────────────────────────────────


@dataclass
class TripleBarrierResult:
    """Outcome of triple-barrier labeling for a single event.

    Attributes:
        index: Event timestamp (entry date).
        side: Primary model side (+1 buy, -1 sell, 0 flat).
        label: Barrier label (+1 upper, -1 lower, 0 vertical/time).
        hit_day: Number of bars after entry until a barrier was hit.
        correct: True if primary side matched the barrier label.
        entry_price: Close price at entry.
        exit_price: Close price at barrier hit (or last bar for vertical).
    """

    index: pd.Timestamp
    side: int
    label: int
    hit_day: int
    correct: bool
    entry_price: float
    exit_price: float


def triple_barrier_labels(
    df: pd.DataFrame,
    events: pd.DataFrame,
    upper_barrier: float = DEFAULT_UPPER_BARRIER,
    lower_barrier: float = DEFAULT_LOWER_BARRIER,
    vertical_barrier: int = DEFAULT_VERTICAL_BARRIER,
    use_atr: bool = False,
    atr_col: str = "atr",
) -> pd.DataFrame:
    """Compute triple-barrier labels for a set of events.

    For each event (row in `events`), the barriers are placed relative to the
    entry close price. The label is determined by which barrier is hit FIRST
    using ONLY bars strictly after the event date (no look-ahead):
    - +1: upper (take-profit) barrier hit
    - -1: lower (stop-loss) barrier hit
    -  0: vertical (time) barrier hit — neither horizontal barrier touched

    Args:
        df: OHLCV DataFrame indexed by date, must contain ``close`` column.
            If ``use_atr`` is True, must also contain ``atr_col``.
        events: DataFrame indexed by event date with at least a ``side`` column
            (+1 buy, -1 sell, 0 flat). Index must be a subset of ``df`` index.
        upper_barrier: Take-profit return threshold (e.g. 0.02 = +2%).
            Ignored when ``use_atr`` is True (then = ``upper_atr_mult * atr``).
        lower_barrier: Stop-loss return threshold (e.g. -0.02 = -2%).
        vertical_barrier: Maximum holding period in bars.
        use_atr: If True, barriers are scaled by ATR at entry:
            upper = upper_barrier * atr, lower = lower_barrier * atr.
        atr_col: Column name for ATR in ``df`` (used when ``use_atr``).

    Returns:
        DataFrame indexed by event date with columns:
        ``side``, ``label``, ``hit_day``, ``correct``, ``entry_price``,
        ``exit_price``.
    """
    close = df["close"].astype(float)
    results: list[TripleBarrierResult] = []

    for event_idx, event_row in events.iterrows():
        side = int(event_row.get("side", 0))
        # Locate the entry position in the price series.
        if event_idx not in close.index:
            continue
        entry_pos = close.index.get_loc(event_idx)
        entry_price = float(close.iloc[entry_pos])

        # Determine barrier levels (absolute price thresholds).
        if use_atr and atr_col in df.columns:
            atr_val = float(df[atr_col].iloc[entry_pos])
            upper_level = entry_price * (1.0 + upper_barrier * atr_val)
            lower_level = entry_price * (1.0 + lower_barrier * atr_val)
        else:
            upper_level = entry_price * (1.0 + upper_barrier)
            lower_level = entry_price * (1.0 + lower_barrier)

        label = 0
        hit_day = vertical_barrier
        exit_price = entry_price

        # Scan forward bars ONLY (strictly after entry → no look-ahead).
        end_pos = min(entry_pos + vertical_barrier + 1, len(close))
        for j in range(entry_pos + 1, end_pos):
            bar_high = float(df["high"].iloc[j]) if "high" in df.columns else float(close.iloc[j])
            bar_low = float(df["low"].iloc[j]) if "low" in df.columns else float(close.iloc[j])
            bar_close = float(close.iloc[j])

            # Upper barrier touched first?
            if bar_high >= upper_level:
                label = 1
                hit_day = j - entry_pos
                exit_price = upper_level
                break
            # Lower barrier touched first?
            if bar_low <= lower_level:
                label = -1
                hit_day = j - entry_pos
                exit_price = lower_level
                break
            # Otherwise continue; on the last bar we hit the vertical barrier.
            if j == end_pos - 1:
                label = 0
                hit_day = j - entry_pos
                exit_price = bar_close

        # A buy (side=+1) is correct if upper barrier hit (label=+1).
        # A sell (side=-1) is correct if lower barrier hit (label=-1).
        # Flat (side=0) is never "correct" for trading purposes.
        if side == 1:
            correct = label == 1
        elif side == -1:
            correct = label == -1
        else:
            correct = False

        results.append(
            TripleBarrierResult(
                index=pd.Timestamp(event_idx),
                side=side,
                label=label,
                hit_day=hit_day,
                correct=correct,
                entry_price=entry_price,
                exit_price=exit_price,
            )
        )

    return pd.DataFrame(
        [
            {
                "side": r.side,
                "label": r.label,
                "hit_day": r.hit_day,
                "correct": r.correct,
                "entry_price": r.entry_price,
                "exit_price": r.exit_price,
            }
            for r in results
        ],
        index=[r.index for r in results],
    )


# ── 2. CUSUM Filter ────────────────────────────────────────────────────────


def cusum_filter(
    close: pd.Series,
    threshold: float = DEFAULT_CUSUM_THRESHOLD,
    vol_window: int = 20,
) -> pd.DatetimeIndex:
    """CUSUM event filter: sample bars where cumulative return exceeds threshold.

    Implements the CUSUM filter from López de Prado (Ch. 2). A running sum of
    returns is tracked; when its absolute value exceeds a (volatility-scaled)
    threshold, the bar is flagged as an event and the cumulative sum is reset.

    This avoids labeling every bar and focuses on bars with meaningful price
    movement, which improves the signal-to-noise ratio for the meta-model.

    Args:
        close: Close price series.
        threshold: Base cumulative-return threshold (e.g. 0.02 = 2%).
        vol_window: Rolling window used to scale the threshold by recent
            volatility. The effective threshold per bar is
            ``threshold * rolling_std(returns)``.

    Returns:
        DatetimeIndex of event timestamps (subset of ``close.index``).
    """
    returns = close.pct_change().fillna(0.0)
    vol = returns.rolling(vol_window).std().fillna(0.0)
    # Avoid zero-volatility bars producing infinite effective thresholds.
    eff_threshold = (threshold * vol).where(vol > 0, threshold)

    pos_cum = 0.0
    neg_cum = 0.0
    events: list[pd.Timestamp] = []

    for i in range(len(returns)):
        r = float(returns.iloc[i])
        thr = float(eff_threshold.iloc[i]) if i < len(eff_threshold) else threshold
        if thr <= 0:
            thr = threshold

        pos_cum = max(0.0, pos_cum + r)
        neg_cum = min(0.0, neg_cum + r)

        if pos_cum > thr or neg_cum < -thr:
            events.append(pd.Timestamp(close.index[i]))
            pos_cum = 0.0
            neg_cum = 0.0

    return pd.DatetimeIndex(events)


# ── 3. Feature Engineering ─────────────────────────────────────────────────

META_FEATURE_COLS: list[str] = [
    "rsi",
    "atr_pct",
    "atr_percentile",
    "volume_zscore",
    "regime_label",
    "momentum",
    "ma_slope",
    "foreign_flow_signal",
    "vix_proxy",
    "prediction_confidence",
]


def compute_meta_features(
    df: pd.DataFrame,
    primary_confidence: pd.Series | None = None,
    foreign_flow: pd.Series | None = None,
    vix_proxy: pd.Series | None = None,
) -> pd.DataFrame:
    """Compute meta-model features from OHLCV + optional exogenous signals.

    All features are strictly non-look-ahead: each value at time T uses only
    data available at or before T (rolling windows, no shift(-k)).

    Features:
    - ``rsi``: 14-period RSI.
    - ``atr_pct``: 14-period ATR as % of close.
    - ``atr_percentile``: rolling 60-bar percentile rank of ``atr_pct``.
    - ``volume_zscore``: 20-bar rolling z-score of volume.
    - ``regime_label``: simple regime label (0=low-vol, 1=high-vol) based on
      ``atr_percentile`` > 0.7.
    - ``momentum``: 10-bar return %.
    - ``ma_slope``: 5-bar pct change of 20-bar MA (%).
    - ``foreign_flow_signal``: optional foreign net-buy signal (default 0).
    - ``vix_proxy``: optional volatility-index proxy (default rolling std).
    - ``prediction_confidence``: primary model confidence (default 0.5).

    Args:
        df: OHLCV DataFrame (open, high, low, close, volume).
        primary_confidence: Series of primary model confidence aligned to df.
        foreign_flow: Series of foreign net-flow signal aligned to df.
        vix_proxy: Series of VIX-proxy values aligned to df.

    Returns:
        DataFrame (same index as df) with all meta-feature columns.
    """
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
    rs = avg_gain / avg_loss.replace(0, np.nan)
    data["rsi"] = (100 - (100 / (1 + rs))).fillna(50.0)

    # ATR (14) as % of close
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    data["atr_pct"] = (atr / close * 100).fillna(0.0)
    data["atr_percentile"] = (
        data["atr_pct"].rolling(60, min_periods=20).rank(pct=True).fillna(0.5)
    )

    # Volume z-score
    vol_mean = volume.rolling(20, min_periods=10).mean()
    vol_std = volume.rolling(20, min_periods=10).std()
    data["volume_zscore"] = (
        (volume - vol_mean) / vol_std.replace(0, np.nan)
    ).fillna(0.0).replace([np.inf, -np.inf], 0.0)

    # Regime label
    data["regime_label"] = (data["atr_percentile"] > 0.7).astype(int)

    # Momentum & MA slope
    data["momentum"] = (close.pct_change(10) * 100).fillna(0.0)
    ma_20 = close.rolling(20).mean()
    data["ma_slope"] = (ma_20.pct_change(5) * 100).fillna(0.0)

    # Exogenous signals (default to neutral when not provided)
    if foreign_flow is not None:
        ff_dedup = foreign_flow[~foreign_flow.index.duplicated(keep="last")]
        data["foreign_flow_signal"] = ff_dedup.reindex(data.index).fillna(0.0)
    else:
        data["foreign_flow_signal"] = 0.0

    if vix_proxy is not None:
        vp_dedup = vix_proxy[~vix_proxy.index.duplicated(keep="last")]
        data["vix_proxy"] = vp_dedup.reindex(data.index).fillna(0.0)
    else:
        # Default proxy: 20-bar rolling std of returns * 100
        data["vix_proxy"] = (close.pct_change().rolling(20).std() * 100).fillna(0.0)

    if primary_confidence is not None:
        pc_dedup = primary_confidence[~primary_confidence.index.duplicated(keep="last")]
        data["prediction_confidence"] = (
            pc_dedup.reindex(data.index).fillna(0.5).clip(0.0, 1.0)
        )
    else:
        data["prediction_confidence"] = 0.5

    return data[META_FEATURE_COLS]


# ── 4. Bet Sizing ──────────────────────────────────────────────────────────


@dataclass
class BetSize:
    """Bet sizing result from meta-model probability.

    Attributes:
        probability: Meta-model P(primary prediction correct) in [0, 1].
        size: Position size in [0, 1]. 0 means no trade.
        trade: Whether to take the trade (size > 0).
    """

    probability: float
    size: float
    trade: bool


def bet_size_from_probability(
    probability: float,
    prob_threshold: float = DEFAULT_BET_PROB_THRESHOLD,
    max_size: float = 1.0,
    method: str = "linear",
) -> BetSize:
    """Convert meta-model probability to a position size.

    - If ``probability < prob_threshold`` → no trade (size = 0).
    - ``linear``: size = (probability - 0.5) * 2, capped at ``max_size``.
    - ``lopes_de_prado``: size = probability (the meta-model probability itself
      is the bet size, per López de Prado's recommendation), capped at
      ``max_size``. Only applied when probability >= prob_threshold.

    Args:
        probability: Meta-model probability in [0, 1].
        prob_threshold: Minimum probability to trade (default 0.5).
        max_size: Maximum position size cap (default 1.0).
        method: ``"linear"`` or ``"lopes_de_prado"``.

    Returns:
        BetSize dataclass.
    """
    prob = float(np.clip(probability, 0.0, 1.0))

    if prob < prob_threshold:
        return BetSize(probability=prob, size=0.0, trade=False)

    size = prob if method == "lopes_de_prado" else (prob - 0.5) * 2.0

    size = float(np.clip(size, 0.0, max_size))
    return BetSize(probability=prob, size=size, trade=size > 0.0)


# ── 5. Purged Walk-Forward Cross-Validation ────────────────────────────────


def purged_walk_forward_splits(
    n: int,
    n_splits: int = 5,
    purge_gap: int = DEFAULT_PURGE_GAP,
    embargo: int = DEFAULT_EMBARGO,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate purged + embargoed walk-forward train/test index splits.

    Walk-forward: each test fold comes AFTER the training fold in time.
    Purged: ``purge_gap`` bars are removed from the end of the training fold
    to avoid label leakage (triple-barrier labels span ``vertical_barrier``
    bars into the future).
    Embargo: ``embargo`` bars after each test fold are excluded from
    subsequent training to prevent leakage from overlapping labels.

    Args:
        n: Total number of samples.
        n_splits: Number of walk-forward folds.
        purge_gap: Bars purged at the train/test boundary.
        embargo: Bars embargoed after each test fold.

    Returns:
        List of (train_indices, test_indices) tuples.
    """
    if n <= 0:
        return []

    splits: list[tuple[np.ndarray, np.ndarray]] = []
    fold_size = max(n // (n_splits + 1), purge_gap + embargo + 1)

    for k in range(n_splits):
        test_start = k * fold_size + fold_size
        test_end = min(test_start + fold_size, n)
        if test_start >= n or test_end <= test_start:
            break

        train_end = test_start - purge_gap
        train_start = 0
        if k > 0:
            # Embargo: skip bars right after the previous test fold.
            prev_test_end = k * fold_size + fold_size  # == test_start
            train_start = prev_test_end  # previous test fold excluded
        # Actually for walk-forward, training grows; embargo applies to the
        # boundary between previous test and current train.
        if k > 0:
            prev_test_end = (k - 1) * fold_size + fold_size + fold_size
            train_start = min(prev_test_end + embargo, train_end)

        if train_start >= train_end:
            continue

        train_idx = np.arange(train_start, train_end)
        test_idx = np.arange(test_start, test_end)
        splits.append((train_idx, test_idx))

    return splits


# ── 6. Meta-Labeling Model ─────────────────────────────────────────────────


@dataclass
class MetaLabelResult:
    """Result of a meta-labeling prediction for a single event.

    Attributes:
        probability: P(primary prediction correct) in [0, 1].
        bet_size: Computed position size in [0, 1].
        trade: Whether to take the trade.
        n_train_samples: Number of training samples used.
        model_available: Whether the meta-model was trained successfully.
        feature_values: Dict of feature name → value used for this prediction.
    """

    probability: float
    bet_size: float
    trade: bool
    n_train_samples: int
    model_available: bool
    feature_values: dict[str, float] = field(default_factory=dict)


class MetaLabeler:
    """Meta-labeling model: predicts whether the primary model's bet succeeds.

    The primary model (e.g. ``PredictionEngine._predict_ensemble``) decides the
    SIDE (buy/sell). This secondary LightGBM classifier predicts the
    probability that the primary side will be correct, and converts that into a
    bet size via :func:`bet_size_from_probability`.

    Training uses purged + embargoed walk-forward CV to avoid look-ahead bias
    and label leakage from triple-barrier labels.
    """

    def __init__(
        self,
        upper_barrier: float = DEFAULT_UPPER_BARRIER,
        lower_barrier: float = DEFAULT_LOWER_BARRIER,
        vertical_barrier: int = DEFAULT_VERTICAL_BARRIER,
        use_atr: bool = False,
        prob_threshold: float = DEFAULT_BET_PROB_THRESHOLD,
        min_train_samples: int = DEFAULT_MIN_TRAIN_SAMPLES,
        n_estimators: int = 300,
        max_depth: int = 5,
        learning_rate: float = 0.03,
        min_data_in_leaf: int = 60,
        reg_alpha: float = 0.15,
        reg_lambda: float = 2.0,
        subsample: float = 0.7,
        colsample_bytree: float = 0.7,
        min_gain_to_split: float = 0.01,
        n_splits: int = 5,
        purge_gap: int = DEFAULT_PURGE_GAP,
        embargo: int = DEFAULT_EMBARGO,
        bet_method: str = "linear",
    ) -> None:
        self.upper_barrier = upper_barrier
        self.lower_barrier = lower_barrier
        self.vertical_barrier = vertical_barrier
        self.use_atr = use_atr
        self.prob_threshold = prob_threshold
        self.min_train_samples = min_train_samples
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.min_data_in_leaf = min_data_in_leaf
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.min_gain_to_split = min_gain_to_split
        self.n_splits = n_splits
        self.purge_gap = purge_gap
        self.embargo = embargo
        self.bet_method = bet_method
        self._model: LGBMClassifier | None = None

    # -- public API --------------------------------------------------------

    def fit(
        self,
        df: pd.DataFrame,
        events: pd.DataFrame,
        primary_confidence: pd.Series | None = None,
        foreign_flow: pd.Series | None = None,
        vix_proxy: pd.Series | None = None,
    ) -> dict[str, float]:
        """Train the meta-labeling model on historical events.

        Args:
            df: OHLCV DataFrame.
            events: DataFrame indexed by event date with a ``side`` column
                (primary model's +1/-1/0 direction).
            primary_confidence: Primary model confidence per date.
            foreign_flow: Optional foreign net-flow signal.
            vix_proxy: Optional VIX-proxy series.

        Returns:
            Dict of validation metrics (mean accuracy, mean AUC across folds).
        """
        try:
            import lightgbm as lgb
        except ImportError:
            logger.warning("LightGBM not available — meta-labeler disabled")
            self._model = None
            return {"mean_accuracy": 0.5, "mean_auc": 0.5}

        # Compute triple-barrier labels (uses only forward data → no look-ahead
        # in the LABEL; features are computed separately at event time).
        labels = triple_barrier_labels(
            df,
            events,
            upper_barrier=self.upper_barrier,
            lower_barrier=self.lower_barrier,
            vertical_barrier=self.vertical_barrier,
            use_atr=self.use_atr,
        )
        if labels.empty:
            logger.debug("Meta-labeler: no valid events to label")
            self._model = None
            return {"mean_accuracy": 0.5, "mean_auc": 0.5}

        # Compute features for ALL bars, then select event rows.
        features_all = compute_meta_features(
            df,
            primary_confidence=primary_confidence,
            foreign_flow=foreign_flow,
            vix_proxy=vix_proxy,
        )

        # Align features to labeled events (features at event time T use
        # only data <= T → no look-ahead).
        feature_rows = features_all.reindex(labels.index)
        target = labels["correct"].astype(int)

        # Drop rows with NaN features.
        valid = feature_rows.dropna()
        target = target.reindex(valid.index)
        feature_rows = valid

        if len(feature_rows) < self.min_train_samples:
            logger.debug(
                "Meta-labeler: insufficient training data (%d < %d)",
                len(feature_rows), self.min_train_samples,
            )
            self._model = None
            return {"mean_accuracy": 0.5, "mean_auc": 0.5}

        X = feature_rows[META_FEATURE_COLS].values
        y = target.values

        # Purged + embargoed walk-forward CV for validation metrics.
        splits = purged_walk_forward_splits(
            len(X),
            n_splits=self.n_splits,
            purge_gap=self.purge_gap,
            embargo=self.embargo,
        )

        accuracies: list[float] = []
        aucs: list[float] = []

        for train_idx, test_idx in splits:
            if len(train_idx) < 10 or len(test_idx) < 2:
                continue
            X_tr, X_te = X[train_idx], X[test_idx]
            y_tr, y_te = y[train_idx], y[test_idx]

            # Skip if a fold has only one class.
            if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
                continue

            fold_model = lgb.LGBMClassifier(
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
                device=_lgbm_dev,
            )
            fold_model.fit(X_tr, y_tr)
            preds = fold_model.predict(X_te)
            proba = fold_model.predict_proba(X_te)[:, 1]
            accuracies.append(float((preds == y_te).mean()))
            # AUC via sklearn if available; else approximate with accuracy.
            try:
                from sklearn.metrics import roc_auc_score

                aucs.append(float(roc_auc_score(y_te, proba)))
            except (ImportError, ValueError):
                aucs.append(accuracies[-1])

        # Train final model on ALL data for production use.
        final_model = lgb.LGBMClassifier(
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
            device=_lgbm_dev,
        )
        final_model.fit(X, y)
        self._model = final_model

        metrics = {
            "mean_accuracy": float(np.mean(accuracies)) if accuracies else 0.5,
            "mean_auc": float(np.mean(aucs)) if aucs else 0.5,
        }
        logger.info(
            "Meta-labeler trained: n=%d, acc=%.3f, auc=%.3f",
            len(X), metrics["mean_accuracy"], metrics["mean_auc"],
        )
        return metrics

    def predict(
        self,
        df: pd.DataFrame,
        as_of: str | pd.Timestamp,
        primary_side: int,
        primary_confidence: float = 0.5,
        foreign_flow: float | None = None,
        vix_proxy: float | None = None,
    ) -> MetaLabelResult:
        """Predict bet size for a single event at ``as_of``.

        Features are computed using ONLY data up to and including ``as_of``
        (no look-ahead). If the model is unavailable or the primary side is
        flat (0), returns a no-trade result.

        Args:
            df: OHLCV DataFrame.
            as_of: Prediction date (cutoff).
            primary_side: Primary model direction (+1 buy, -1 sell, 0 flat).
            primary_confidence: Primary model confidence [0, 1].
            foreign_flow: Optional foreign flow signal value at as_of.
            vix_proxy: Optional VIX-proxy value at as_of.

        Returns:
            MetaLabelResult with probability and bet size.
        """
        # Flat primary → no trade.
        if primary_side == 0:
            return MetaLabelResult(
                probability=0.0, bet_size=0.0, trade=False,
                n_train_samples=0, model_available=self._model is not None,
            )

        if self._model is None:
            return MetaLabelResult(
                probability=0.0, bet_size=0.0, trade=False,
                n_train_samples=0, model_available=False,
            )

        cutoff = pd.Timestamp(as_of)
        data_up_to = df.loc[:cutoff]
        if data_up_to.empty:
            return MetaLabelResult(
                probability=0.0, bet_size=0.0, trade=False,
                n_train_samples=0, model_available=True,
            )

        # Build exogenous signal series for the feature computation.
        pc_series = pd.Series(primary_confidence, index=[cutoff])
        ff_series = (
            pd.Series(foreign_flow, index=[cutoff]) if foreign_flow is not None else None
        )
        vp_series = (
            pd.Series(vix_proxy, index=[cutoff]) if vix_proxy is not None else None
        )

        features_all = compute_meta_features(
            data_up_to,
            primary_confidence=pc_series,
            foreign_flow=ff_series,
            vix_proxy=vp_series,
        )
        latest = features_all.iloc[[-1]][META_FEATURE_COLS]

        if latest.isna().any(axis=1).iloc[0]:
            return MetaLabelResult(
                probability=0.0, bet_size=0.0, trade=False,
                n_train_samples=0, model_available=True,
            )

        proba = self._model.predict_proba(latest.values)[0]
        # P(class=1) = probability primary prediction is correct.
        prob = float(proba[1]) if len(proba) > 1 else 0.5

        bet = bet_size_from_probability(
            prob,
            prob_threshold=self.prob_threshold,
            method=self.bet_method,
        )

        feature_vals = {
            col: float(latest[col].iloc[0]) for col in META_FEATURE_COLS
        }

        return MetaLabelResult(
            probability=prob,
            bet_size=bet.size,
            trade=bet.trade,
            n_train_samples=0,  # set during fit, not available here
            model_available=True,
            feature_values=feature_vals,
        )
