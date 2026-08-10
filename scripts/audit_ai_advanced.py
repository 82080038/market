"""Advanced AI/ML Audit — Feature Remediation, Delta Alpha, Statistical Significance, Score Card.

Extends audit_ai_utility.py with:
  1. Feature Remediation Pipeline (drift detection → regime-aware reweighting → replacement)
  2. Delta Alpha Execution (MLSignal & MultiFactor vs Baseline)
  3. Statistical Significance Test (Diebold-Mariano + Paired t-test)
  4. Automated AI Utility Score Card (KEEP / MARGINAL / REMOVE verdict per component)

Usage:
    DB_PATH=data/market_research.db python scripts/audit_ai_advanced.py [--tickers BBCA,BBRI] [--limit 20]

Requires: scipy, statsmodels, pandas, numpy, lightgbm
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

try:
    from statsmodels.stats.diagnostic import acorr_ljungbox
    from statsmodels.stats.stattools import jarque_bera
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

import sys as _sys
from pathlib import Path as _Path

# Add scripts directory to path for importing audit_ai_utility
_scripts_dir = str(_Path(__file__).resolve().parent)
if _scripts_dir not in _sys.path:
    _sys.path.insert(0, _scripts_dir)

from audit_ai_utility import (
    ROUND_TRIP_COST,
    TRADING_DAYS,
    RISK_FREE_RATE,
    PerformanceMetrics,
    SignalMetrics,
    DriftResult,
    compute_performance_metrics,
    compute_signal_metrics,
    simulate_strategy_returns,
    generate_baseline_signals,
    generate_random_signals,
    load_ohlcv,
    load_benchmark,
    population_stability_index,
    ks_test_drift,
    drift_status,
    profile_latency,
    cost_benefit_analysis,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=FutureWarning)


# ── Data Structures ───────────────────────────────────────────────────────


@dataclass
class FeatureRemediationResult:
    """Result of feature remediation for a single feature."""
    feature: str
    psi_before: float
    psi_after: float
    action: str  # "reweighted", "replaced", "kept", "dropped"
    replacement: str | None = None
    regime_weights_applied: bool = False
    notes: str = ""


@dataclass
class DeltaAlphaResult:
    """Delta Alpha comparison between AI and baseline."""
    component: str
    alpha_ai: float
    alpha_baseline: float
    delta_alpha: float
    sharpe_ai: float
    sharpe_baseline: float
    delta_sharpe: float
    win_rate_ai: float
    win_rate_baseline: float
    max_dd_ai: float
    max_dd_baseline: float
    n_observations: int


@dataclass
class SignificanceTestResult:
    """Statistical significance test result."""
    test_name: str
    statistic: float
    p_value: float
    significant: bool  # p < 0.05
    effect_size: float  # Cohen's d or equivalent
    interpretation: str


@dataclass
class ComponentVerdict:
    """Final verdict for a single AI component."""
    component: str
    score_card: dict
    delta_alpha: float
    delta_sharpe: float
    p_value: float
    significant: bool
    verdict: str  # KEEP, MARGINAL, REMOVE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AdvancedAuditReport:
    """Full advanced audit report."""
    audit_date: str = ""
    tickers_audited: list[str] = field(default_factory=list)
    remediation: list[FeatureRemediationResult] = field(default_factory=list)
    delta_alpha: list[DeltaAlphaResult] = field(default_factory=list)
    significance: list[SignificanceTestResult] = field(default_factory=list)
    verdicts: list[ComponentVerdict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ── Pilar 1: Feature Remediation Pipeline ─────────────────────────────────


def detect_drifted_features(
    features_df: pd.DataFrame,
    reference_end_date: str,
    current_start_date: str,
    psi_threshold: float = 0.25,
) -> list[tuple[str, float]]:
    """Detect features with PSI above threshold.

    Args:
        features_df: DataFrame with features and DatetimeIndex.
        reference_end_date: End date for reference window.
        current_start_date: Start date for current window.
        psi_threshold: PSI value above which feature is considered drifted.

    Returns:
        List of (feature_name, psi_value) tuples for drifted features.
    """
    reference = features_df.loc[:reference_end_date]
    current = features_df.loc[current_start_date:]

    drifted = []
    for col in features_df.columns:
        ref_data = reference[col].dropna().values
        cur_data = current[col].dropna().values

        if len(ref_data) < 20 or len(cur_data) < 20:
            continue

        psi = population_stability_index(ref_data, cur_data)
        if psi > psi_threshold:
            drifted.append((col, psi))

    return drifted


def regime_aware_weights(
    index: pd.DatetimeIndex,
    decay_half_life: int = 126,  # ~6 months
    recent_boost: float = 2.0,
) -> np.ndarray:
    """Compute regime-aware sample weights for training.

    Gives exponentially decaying weights with half-life, plus a boost factor
    for the most recent regime. This ensures the model prioritizes recent
    market behavior while still learning from historical patterns.

    Args:
        index: DatetimeIndex of the training data.
        decay_half_life: Half-life in days for exponential decay.
        recent_boost: Multiplier for the most recent `decay_half_life` period.

    Returns:
        Array of sample weights, same length as index.
    """
    n = len(index)
    if n == 0:
        return np.array([])

    # Exponential time decay: more recent = higher weight
    days_from_end = np.arange(n, 0, -1)
    decay_weights = np.exp(-np.log(2) * days_from_end / decay_half_life)

    # Regime boost: extra weight for last `decay_half_life` days
    recent_mask = days_from_end <= decay_half_life
    regime_weights = np.where(recent_mask, recent_boost, 1.0)

    # Combined weights, normalized
    weights = decay_weights * regime_weights
    weights = weights / weights.sum() * n  # normalize to sum=n

    return weights


def compute_stable_alternative_features(ohlcv: pd.DataFrame) -> dict[str, pd.Series]:
    """Compute stable alternative features that are less prone to drift.

    These features use rank-based or normalized formulations that are
    more robust to regime shifts than raw values.

    Args:
        ohlcv: OHLCV DataFrame.

    Returns:
        Dict mapping feature name to Series.
    """
    close = ohlcv["close"].astype(float)
    returns = close.pct_change()

    alternatives = {}

    # 1. Rank-based RSI (0-1 scale, regime-invariant)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    alternatives["rsi_rank"] = rsi.rolling(252, min_periods=60).rank(pct=True)

    # 2. Volatility percentile (regime-normalized)
    vol_20 = returns.rolling(20).std()
    alternatives["vol_pctile"] = vol_20.rolling(252, min_periods=60).rank(pct=True)

    # 3. MA ratio z-score (normalized against rolling distribution)
    ma_20 = close.rolling(20).mean()
    ma_50 = close.rolling(50).mean()
    ma_ratio = ma_20 / ma_50
    ma_ratio_mean = ma_ratio.rolling(252, min_periods=60).mean()
    ma_ratio_std = ma_ratio.rolling(252, min_periods=60).std()
    alternatives["ma_ratio_zscore"] = (ma_ratio - ma_ratio_mean) / ma_ratio_std.replace(0, np.nan)

    # 4. Return z-score (normalized momentum)
    ret_5 = close.pct_change(5)
    ret_mean = ret_5.rolling(252, min_periods=60).mean()
    ret_std = ret_5.rolling(252, min_periods=60).std()
    alternatives["ret_5_zscore"] = (ret_5 - ret_mean) / ret_std.replace(0, np.nan)

    # 5. Drawdown-based feature (regime-invariant)
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    alternatives["drawdown"] = drawdown

    # 6. Volume z-score (normalized)
    volume = ohlcv["volume"].astype(float)
    vol_mean = volume.rolling(20).mean()
    vol_std = volume.rolling(20).std()
    alternatives["vol_zscore"] = (volume - vol_mean) / vol_std.replace(0, np.nan)

    return alternatives


def remediate_features(
    features_df: pd.DataFrame,
    ohlcv: pd.DataFrame,
    reference_end_date: str,
    current_start_date: str,
    psi_threshold: float = 0.25,
) -> tuple[pd.DataFrame, list[FeatureRemediationResult]]:
    """Full feature remediation pipeline.

    Steps:
    1. Detect drifted features (PSI > threshold)
    2. For each drifted feature:
       a. Try regime-aware reweighting (compute PSI after reweighting)
       b. If still drifted, replace with stable alternative
       c. If no alternative available, drop the feature
    3. Return remediated DataFrame + list of actions taken

    Args:
        features_df: Original feature DataFrame.
        ohlcv: OHLCV data for computing alternatives.
        reference_end_date: End of reference window.
        current_start_date: Start of current window.
        psi_threshold: PSI threshold for drift.

    Returns:
        (remediated_df, list of remediation results)
    """
    remediated = features_df.copy()
    results = []

    # Detect drifted features
    drifted = detect_drifted_features(
        features_df, reference_end_date, current_start_date, psi_threshold,
    )

    if not drifted:
        logger.info("  No drifted features detected (PSI < %.2f)", psi_threshold)
        return remediated, results

    logger.info("  Drifted features (%d): %s", len(drifted), [f[0] for f in drifted])

    # Compute stable alternatives
    alternatives = compute_stable_alternative_features(ohlcv)

    # Mapping from drifted feature to stable alternative
    replacement_map = {
        "rsi": "rsi_rank",
        "vol_20": "vol_pctile",
        "ma_ratio_20": "ma_ratio_zscore",
        "ma_ratio_50": "ma_ratio_zscore",
        "ret_1": "ret_5_zscore",
        "bb_width": "vol_pctile",
    }

    for feature_name, psi_before in drifted:
        result = FeatureRemediationResult(
            feature=feature_name,
            psi_before=psi_before,
            psi_after=psi_before,  # will update
            action="kept",
        )

        # Step 1: Try regime-aware reweighting
        # Apply weights to reference distribution and re-check PSI
        ref_data = features_df.loc[:reference_end_date, feature_name].dropna()
        cur_data = features_df.loc[current_start_date:, feature_name].dropna()

        if len(ref_data) > 20 and len(cur_data) > 20:
            weights = regime_aware_weights(ref_data.index)
            # Weighted resampling: oversample high-weight periods
            n_resample = min(len(ref_data), 5000)
            weighted_indices = np.random.choice(
                ref_data.index,
                size=n_resample,
                replace=True,
                p=weights / weights.sum(),
            )
            reweighted_ref = ref_data.loc[weighted_indices].values

            psi_after_reweight = population_stability_index(reweighted_ref, cur_data.values)

            if psi_after_reweight < psi_threshold:
                result.psi_after = psi_after_reweight
                result.action = "reweighted"
                result.regime_weights_applied = True
                result.notes = f"PSI reduced {psi_before:.3f} → {psi_after_reweight:.3f} via regime-aware weighting"
                results.append(result)
                continue

        # Step 2: Try replacement with stable alternative
        alt_name = replacement_map.get(feature_name)
        if alt_name and alt_name in alternatives:
            alt_series = alternatives[alt_name]
            alt_ref = alt_series.loc[:reference_end_date].dropna().values
            alt_cur = alt_series.loc[current_start_date:].dropna().values

            if len(alt_ref) > 20 and len(alt_cur) > 20:
                alt_psi = population_stability_index(alt_ref, alt_cur)

                if alt_psi < psi_threshold:
                    # Replace the feature
                    remediated[feature_name] = alt_series
                    result.psi_after = alt_psi
                    result.action = "replaced"
                    result.replacement = alt_name
                    result.notes = f"Replaced with {alt_name} (PSI {psi_before:.3f} → {alt_psi:.3f})"
                    results.append(result)
                    continue

        # Step 3: Drop the feature if nothing worked
        remediated = remediated.drop(columns=[feature_name])
        result.action = "dropped"
        result.notes = f"Feature dropped (PSI {psi_before:.3f}, no stable alternative found)"
        results.append(result)

    return remediated, results


# ── Pilar 2: Delta Alpha Execution ────────────────────────────────────────


def generate_mlsignal_predictions(
    ohlcv: pd.DataFrame,
    walk_forward_steps: int | None = None,
) -> pd.Series:
    """Generate MLSignal predictions using walk-forward backtest.

    Trains LightGBM on expanding window, predicts at each step.
    Uses the same feature set as MLSignalProvider.

    Args:
        ohlcv: OHLCV DataFrame.
        walk_forward_steps: Number of prediction steps. If None, predict on last 20% of data.

    Returns:
        Series of signals (-1 to 1) aligned to ohlcv index.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM not available — MLSignal predictions are zero")
        return pd.Series(0.0, index=ohlcv.index)

    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    volume = ohlcv["volume"].astype(float)

    # Build features (same as MLSignalProvider._prepare_features)
    data = ohlcv.copy()
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    data["rsi"] = 100 - (100 / (1 + rs))
    data["ma_5"] = close.rolling(5).mean()
    data["ma_20"] = close.rolling(20).mean()
    data["ma_ratio"] = data["ma_5"] / data["ma_20"]
    data["momentum_5"] = close.pct_change(5) * 100
    data["momentum_10"] = close.pct_change(10) * 100
    data["atr_pct"] = ((high - low) / close * 100).rolling(14).mean()
    data["vol_ma"] = volume.rolling(20).mean()
    data["vol_ratio"] = volume / data["vol_ma"]
    data["hl_range_pct"] = (high - low) / close * 100
    data["ma_5_slope"] = data["ma_5"].pct_change(3) * 100
    data["close_to_high"] = close / high.rolling(20).max()
    data["close_to_low"] = close / low.rolling(20).min()
    data["rsi_change"] = data["rsi"].diff(3)
    data["vol_trend"] = volume.pct_change(5) * 100
    data["price_accel"] = data["momentum_5"] - data["momentum_5"].shift(5)
    data["vol_regime"] = data["atr_pct"].rolling(60).rank(pct=True)

    vol_price = close * volume
    vol_sum = volume.rolling(20, min_periods=1).sum()
    vp_sum = vol_price.rolling(20, min_periods=1).sum()
    data["vwap_20"] = vp_sum / vol_sum.replace(0, np.nan)
    data["vwap_ratio"] = close / data["vwap_20"].replace(0, np.nan)
    data["vol_roc_10"] = (volume - volume.shift(10)) / volume.shift(10).replace(0, np.nan) * 100
    obv_direction = np.sign(close.diff())
    data["obv"] = (obv_direction * volume).cumsum()
    data["obv_slope"] = data["obv"].diff(5)
    price_change = close.pct_change()
    vol_norm = volume / volume.rolling(20).mean().replace(0, np.nan)
    data["vol_price_trend"] = (price_change * vol_norm).rolling(10).mean()

    # Target: forward 5-day return > 0
    data["forward_return"] = close.shift(-5) / close - 1
    data["target"] = (data["forward_return"] > 0).astype(int)

    feature_cols = [
        "rsi", "ma_ratio", "momentum_5", "momentum_10",
        "atr_pct", "vol_ratio", "hl_range_pct",
        "ma_5_slope", "close_to_high", "close_to_low",
        "rsi_change", "vol_trend", "price_accel", "vol_regime",
        "vwap_ratio", "vol_roc_10", "obv_slope", "vol_price_trend",
    ]

    # Walk-forward backtest
    clean = data.dropna(subset=feature_cols + ["target"])
    if len(clean) < 300:
        return pd.Series(0.0, index=ohlcv.index)

    if walk_forward_steps is None:
        walk_forward_steps = max(50, int(len(clean) * 0.2))

    signals = pd.Series(0.0, index=ohlcv.index)

    min_train = 200
    for i in range(min_train, len(clean) - 1):
        if i % walk_forward_steps != 0 and i != min_train:
            continue

        train = clean.iloc[:i]
        test_start = i
        test_end = min(i + walk_forward_steps, len(clean))

        X_train = train[feature_cols].values
        y_train = train["target"].values

        # Walk-forward: 80/20 split within training
        split = int(len(X_train) * 0.8)
        X_tr, X_val = X_train[:split], X_train[split:]
        y_tr, y_val = y_train[:split], y_train[split:]

        model = lgb.LGBMClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            verbose=-1, subsample=0.8, colsample_bytree=0.8,
        )
        model.fit(
            X_tr, y_tr,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(10, verbose=False)],
        )

        # Predict for test window
        test_data = clean.iloc[test_start:test_end]
        if len(test_data) == 0:
            continue
        X_test = test_data[feature_cols].values
        proba = model.predict_proba(X_test)
        signal_vals = 2 * proba[:, 1] - 1  # P(up) → [-1, 1]

        for j, idx in enumerate(test_data.index):
            signals.loc[idx] = signal_vals[j]

    return signals


def generate_multifactor_predictions(
    ohlcv: pd.DataFrame,
    walk_forward_steps: int | None = None,
) -> pd.Series:
    """Generate MultiFactor predictions using walk-forward backtest.

    Uses endogenous features only (no exogenous/PCA for simplicity in audit mode).
    3-class: BUY (up >1%), SELL (down <-1%), HOLD (otherwise).

    Args:
        ohlcv: OHLCV DataFrame.
        walk_forward_steps: Prediction window size.

    Returns:
        Series of signals (-1 to 1) aligned to ohlcv index.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM not available — MultiFactor predictions are zero")
        return pd.Series(0.0, index=ohlcv.index)

    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    volume = ohlcv["volume"].astype(float)
    returns = close.pct_change()

    # Build endogenous features (subset of MultiFactorFeaturePipeline)
    data = ohlcv.copy()
    data["ret_1"] = returns
    data["ret_5"] = close.pct_change(5)
    data["autocorr_1"] = returns.rolling(20).apply(
        lambda x: x.autocorr(lag=1) if len(x) > 2 else 0, raw=False
    )
    data["autocorr_5"] = returns.rolling(20).apply(
        lambda x: x.autocorr(lag=5) if len(x) > 6 else 0, raw=False
    )
    data["body_ratio"] = (close - close.shift(1)) / (high - low).replace(0, np.nan)
    data["rsi"] = _rsi(close, 14)
    data["momentum"] = close.pct_change(10) * 100
    data["ma_5"] = close.rolling(5).mean()
    data["ma_20"] = close.rolling(20).mean()
    data["ma_ratio"] = data["ma_5"] / data["ma_20"]
    data["vol_20"] = returns.rolling(20).std()
    data["bb_width"] = (2 * close.rolling(20).std()) / close.rolling(20).mean()
    data["bb_pct"] = (close - close.rolling(20).mean()) / (2 * close.rolling(20).std().replace(0, np.nan))

    # MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    data["macd_hist"] = macd_line - macd_signal
    data["macd_hist_norm"] = data["macd_hist"] / close

    # Volume features
    data["vol_ratio"] = volume / volume.rolling(20).mean().replace(0, np.nan)

    # Target: 3-class (up >1% = BUY=2, down <-1% = SELL=0, else HOLD=1)
    data["forward_return"] = close.shift(-5) / close - 1
    data["target_3class"] = 1  # HOLD default
    data.loc[data["forward_return"] > 0.01, "target_3class"] = 2  # BUY
    data.loc[data["forward_return"] < -0.01, "target_3class"] = 0  # SELL

    feature_cols = [
        "ret_1", "ret_5", "autocorr_1", "autocorr_5", "body_ratio",
        "rsi", "momentum", "ma_ratio", "vol_20", "bb_width", "bb_pct",
        "macd_hist_norm", "vol_ratio",
    ]

    clean = data.dropna(subset=feature_cols + ["target_3class"])
    if len(clean) < 300:
        return pd.Series(0.0, index=ohlcv.index)

    if walk_forward_steps is None:
        walk_forward_steps = max(50, int(len(clean) * 0.2))

    signals = pd.Series(0.0, index=ohlcv.index)
    min_train = 200

    for i in range(min_train, len(clean) - 1):
        if i % walk_forward_steps != 0 and i != min_train:
            continue

        train = clean.iloc[:i]
        test_start = i
        test_end = min(i + walk_forward_steps, len(clean))

        X_train = train[feature_cols].values
        y_train = train["target_3class"].values

        split = int(len(X_train) * 0.8)
        X_tr, X_val = X_train[:split], X_train[split:]
        y_tr, y_val = y_train[:split], y_train[split:]

        model = lgb.LGBMClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            verbose=-1, subsample=0.8, colsample_bytree=0.8,
            n_jobs=1, objective="multiclass", num_classes=3,
        )
        model.fit(
            X_tr, y_tr,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(15, verbose=False)],
        )

        test_data = clean.iloc[test_start:test_end]
        if len(test_data) == 0:
            continue
        X_test = test_data[feature_cols].values
        proba = model.predict_proba(X_test)
        # Signal: P(BUY) - P(SELL) → [-1, 1]
        signal_vals = proba[:, 2] - proba[:, 0]

        for j, idx in enumerate(test_data.index):
            signals.loc[idx] = signal_vals[j]

    return signals


def convert_signal_to_position(signal: pd.Series, threshold: float = 0.0) -> pd.Series:
    """Convert continuous signal [-1, 1] to discrete position (-1, 0, 1).

    Args:
        signal: Continuous signal series.
        threshold: Threshold above which to take position.

    Returns:
        Position series.
    """
    position = pd.Series(0, index=signal.index)
    position[signal > threshold] = 1
    position[signal < -threshold] = -1
    return position


def compute_delta_alpha(
    ohlcv: pd.DataFrame,
    ai_signals: pd.Series,
    benchmark: pd.Series | None = None,
    component_name: str = "AI",
    signal_threshold: float = 0.0,
) -> DeltaAlphaResult:
    """Compute Delta Alpha between AI strategy and baseline.

    Args:
        ohlcv: OHLCV DataFrame.
        ai_signals: Continuous AI signals [-1, 1].
        benchmark: Benchmark returns.
        component_name: Name of AI component.
        signal_threshold: Threshold for converting signal to position.

    Returns:
        DeltaAlphaResult with explicit ΔAlpha.
    """
    # Convert AI signal to positions
    ai_positions = convert_signal_to_position(ai_signals, signal_threshold)

    # Baseline signals
    baseline_signals = generate_baseline_signals(ohlcv)

    # Simulate returns
    ai_returns = simulate_strategy_returns(ohlcv, ai_positions)
    baseline_returns = simulate_strategy_returns(ohlcv, baseline_signals)

    # Align
    aligned = pd.DataFrame({
        "ai": ai_returns,
        "baseline": baseline_returns,
    }).dropna()

    if len(aligned) < 30:
        return DeltaAlphaResult(
            component=component_name,
            alpha_ai=0.0, alpha_baseline=0.0, delta_alpha=0.0,
            sharpe_ai=0.0, sharpe_baseline=0.0, delta_sharpe=0.0,
            win_rate_ai=0.0, win_rate_baseline=0.0,
            max_dd_ai=0.0, max_dd_baseline=0.0,
            n_observations=len(aligned),
        )

    bench_aligned = benchmark.reindex(aligned.index).dropna() if benchmark is not None else None

    # Performance metrics
    ai_perf = compute_performance_metrics(aligned["ai"], bench_aligned)
    base_perf = compute_performance_metrics(aligned["baseline"], bench_aligned)

    delta_alpha = ai_perf.alpha - base_perf.alpha
    delta_sharpe = ai_perf.sharpe_ratio - base_perf.sharpe_ratio

    return DeltaAlphaResult(
        component=component_name,
        alpha_ai=ai_perf.alpha,
        alpha_baseline=base_perf.alpha,
        delta_alpha=delta_alpha,
        sharpe_ai=ai_perf.sharpe_ratio,
        sharpe_baseline=base_perf.sharpe_ratio,
        delta_sharpe=delta_sharpe,
        win_rate_ai=ai_perf.win_rate,
        win_rate_baseline=base_perf.win_rate,
        max_dd_ai=ai_perf.max_drawdown,
        max_dd_baseline=base_perf.max_drawdown,
        n_observations=len(aligned),
    )


# ── Pilar 3: Statistical Significance ─────────────────────────────────────


def diebold_mariano_test(
    forecast_errors_ai: pd.Series,
    forecast_errors_baseline: pd.Series,
    horizon: int = 1,
) -> SignificanceTestResult:
    """Diebold-Mariano test for comparing forecast accuracy.

    Tests whether the difference in forecast errors between two models
    is statistically significant, accounting for autocorrelation.

    H0: E[d_t] = 0 (no difference in forecast accuracy)
    H1: E[d_t] ≠ 0 (one model is significantly better)

    Args:
        forecast_errors_ai: Forecast errors from AI model (pred - actual).
        forecast_errors_baseline: Forecast errors from baseline.
        horizon: Forecast horizon (for HAC variance estimation).

    Returns:
        SignificanceTestResult.
    """
    # Loss differential: squared errors
    loss_ai = forecast_errors_ai ** 2
    loss_baseline = forecast_errors_baseline ** 2
    d = loss_baseline - loss_ai  # positive = AI is better

    d_mean = d.mean()
    d_var = d.var()

    # HAC variance estimation (Newey-West with h lags)
    h = horizon - 1
    n = len(d)

    if n < 10 or d_var == 0:
        return SignificanceTestResult(
            test_name="Diebold-Mariano",
            statistic=0.0, p_value=1.0, significant=False,
            effect_size=0.0,
            interpretation="Insufficient data or zero variance",
        )

    # Newey-West HAC variance
    gamma_0 = d_var
    gammas = []
    for k in range(1, h + 1):
        gamma_k = d.iloc[k:].cov(d.iloc[:-k])
        gammas.append(gamma_k)

    hac_var = (gamma_0 + 2 * sum(gammas)) / n
    if hac_var <= 0:
        hac_var = gamma_0 / n

    dm_stat = d_mean / np.sqrt(hac_var)
    p_value = 2 * (1 - stats.norm.cdf(abs(dm_stat)))

    # Effect size (Cohen's d equivalent)
    pooled_std = np.sqrt((loss_ai.var() + loss_baseline.var()) / 2)
    effect_size = float(d_mean / pooled_std) if pooled_std > 0 else 0.0

    if p_value < 0.01:
        interpretation = f"AI significantly better (p={p_value:.4f}, DM={dm_stat:.3f})"
    elif p_value < 0.05:
        interpretation = f"AI marginally better (p={p_value:.4f}, DM={dm_stat:.3f})"
    else:
        interpretation = f"No significant difference (p={p_value:.4f}, DM={dm_stat:.3f})"

    return SignificanceTestResult(
        test_name="Diebold-Mariano",
        statistic=float(dm_stat),
        p_value=float(p_value),
        significant=p_value < 0.05,
        effect_size=effect_size,
        interpretation=interpretation,
    )


def paired_ttest(
    returns_ai: pd.Series,
    returns_baseline: pd.Series,
) -> SignificanceTestResult:
    """Paired t-test comparing daily returns of AI vs baseline.

    H0: mean(AI_returns - baseline_returns) = 0
    H1: mean(AI_returns - baseline_returns) ≠ 0

    Args:
        returns_ai: Daily returns from AI strategy.
        returns_baseline: Daily returns from baseline strategy.

    Returns:
        SignificanceTestResult.
    """
    aligned = pd.DataFrame({
        "ai": returns_ai,
        "baseline": returns_baseline,
    }).dropna()

    if len(aligned) < 30:
        return SignificanceTestResult(
            test_name="Paired t-test",
            statistic=0.0, p_value=1.0, significant=False,
            effect_size=0.0,
            interpretation="Insufficient data",
        )

    diff = aligned["ai"] - aligned["baseline"]
    t_stat, p_value = stats.ttest_rel(aligned["ai"], aligned["baseline"])

    # Effect size: Cohen's d for paired samples
    diff_std = diff.std()
    effect_size = float(diff.mean() / diff_std) if diff_std > 0 else 0.0

    if p_value < 0.01:
        interpretation = f"AI significantly outperforms baseline (p={p_value:.4f}, t={t_stat:.3f})"
    elif p_value < 0.05:
        interpretation = f"AI marginally outperforms baseline (p={p_value:.4f}, t={t_stat:.3f})"
    else:
        interpretation = f"No significant outperformance (p={p_value:.4f}, t={t_stat:.3f})"

    return SignificanceTestResult(
        test_name="Paired t-test",
        statistic=float(t_stat),
        p_value=float(p_value),
        significant=p_value < 0.05,
        effect_size=effect_size,
        interpretation=interpretation,
    )


def whites_reality_check_approximation(
    returns_ai: pd.Series,
    returns_baseline: pd.Series,
    n_bootstrap: int = 1000,
) -> SignificanceTestResult:
    """Bootstrap approximation of White's Reality Check.

    Tests whether the AI model's outperformance is genuine or could have
    arisen from data snooping. Uses bootstrap resampling of the return
    differential to build a null distribution.

    Args:
        returns_ai: Daily returns from AI strategy.
        returns_baseline: Daily returns from baseline strategy.
        n_bootstrap: Number of bootstrap iterations.

    Returns:
        SignificanceTestResult.
    """
    aligned = pd.DataFrame({
        "ai": returns_ai,
        "baseline": returns_baseline,
    }).dropna()

    if len(aligned) < 30:
        return SignificanceTestResult(
            test_name="Bootstrap Reality Check",
            statistic=0.0, p_value=1.0, significant=False,
            effect_size=0.0,
            interpretation="Insufficient data",
        )

    diff = (aligned["ai"] - aligned["baseline"]).values
    observed_mean = diff.mean()

    # Bootstrap: resample with replacement, compute mean each time
    rng = np.random.default_rng(42)
    bootstrap_means = np.zeros(n_bootstrap)
    n = len(diff)

    for i in range(n_bootstrap):
        sample = rng.choice(diff, size=n, replace=True)
        bootstrap_means[i] = sample.mean()

    # P-value: fraction of bootstrap means >= observed (one-sided)
    p_value = float(np.mean(bootstrap_means >= observed_mean))

    # Statistic: observed mean / std of bootstrap means
    bs_std = bootstrap_means.std()
    statistic = float(observed_mean / bs_std) if bs_std > 0 else 0.0

    effect_size = float(observed_mean / diff.std()) if diff.std() > 0 else 0.0

    if p_value < 0.05:
        interpretation = f"Outperformance is genuine (bootstrap p={p_value:.4f})"
    else:
        interpretation = f"Outperformance may be noise (bootstrap p={p_value:.4f})"

    return SignificanceTestResult(
        test_name="Bootstrap Reality Check",
        statistic=statistic,
        p_value=p_value,
        significant=p_value < 0.05,
        effect_size=effect_size,
        interpretation=interpretation,
    )


# ── Pilar 4: Automated AI Utility Score Card ──────────────────────────────


def compute_component_score_card(
    component_name: str,
    delta_alpha_result: DeltaAlphaResult,
    significance_results: list[SignificanceTestResult],
    drift_results: list[DriftResult] | None = None,
    latency_ms: float | None = None,
    monthly_cost: float = 0.0,
    portfolio_value: float = 100_000_000,
    trade_freq: float = 4,
) -> ComponentVerdict:
    """Compute final score card and verdict for an AI component.

    Weights (total = 100%):
    - Delta Alpha: 25%
    - Delta Sharpe: 20%
    - Statistical significance: 15%
    - Cost efficiency: 15%
    - Latency: 10%
    - Model stability (drift): 10%
    - Interpretability: 5%

    Args:
        component_name: Name of the component.
        delta_alpha_result: Delta Alpha computation result.
        significance_results: List of significance test results.
        drift_results: Feature drift results for this component.
        latency_ms: Median latency in milliseconds.
        monthly_cost: Monthly operational cost in IDR.
        portfolio_value: Portfolio value for cost-benefit.
        trade_freq: Trades per month.

    Returns:
        ComponentVerdict with KEEP/MARGINAL/REMOVE.
    """
    scores = {}

    # 1. Delta Alpha (25%) — annualized alpha improvement
    da = delta_alpha_result.delta_alpha * 100  # in %
    scores["delta_alpha"] = min(5, max(0, da / 2))  # 5 = >10% alpha improvement

    # 2. Delta Sharpe (20%)
    ds = delta_alpha_result.delta_sharpe
    # Clamp to [-2, +3] range before scoring: -2→0, +3→5
    ds_clamped = max(-2.0, min(3.0, ds))
    scores["delta_sharpe"] = (ds_clamped + 2) / 5 * 5  # -2→0, +3→5

    # 3. Statistical significance (15%) — use best p-value across tests
    min_p = min((r.p_value for r in significance_results), default=1.0)
    if min_p < 0.01:
        scores["significance"] = 5
    elif min_p < 0.05:
        scores["significance"] = 3
    elif min_p < 0.10:
        scores["significance"] = 1
    else:
        scores["significance"] = 0

    # 4. Cost efficiency (15%)
    if monthly_cost > 0:
        alpha_monthly = max(0, da / 100 / 12)
        revenue_lift = alpha_monthly * portfolio_value * trade_freq
        bc_ratio = revenue_lift / monthly_cost
        scores["cost_efficiency"] = min(5, max(0, bc_ratio / 2))
    else:
        scores["cost_efficiency"] = 5  # free = max score

    # 5. Latency (10%)
    if latency_ms is not None:
        if latency_ms < 500:
            scores["latency"] = 5
        elif latency_ms < 2000:
            scores["latency"] = 4
        elif latency_ms < 5000:
            scores["latency"] = 3
        elif latency_ms < 30000:
            scores["latency"] = 1
        else:
            scores["latency"] = 0
    else:
        scores["latency"] = 3

    # 6. Model stability / drift (10%)
    if drift_results:
        drifted_count = sum(1 for d in drift_results if d.status == "drifted")
        total = len(drift_results)
        stability = 1 - (drifted_count / total) if total > 0 else 1
        scores["stability"] = stability * 5
    else:
        scores["stability"] = 3

    # 7. Interpretability (5%) — LightGBM = partially explainable
    scores["interpretability"] = 3

    # Weighted total
    weights = {
        "delta_alpha": 0.25,
        "delta_sharpe": 0.20,
        "significance": 0.15,
        "cost_efficiency": 0.15,
        "latency": 0.10,
        "stability": 0.10,
        "interpretability": 0.05,
    }
    total = sum(scores[k] * weights[k] for k in weights)

    # Verdict
    if total >= 3.5:
        verdict = "KEEP"
    elif total >= 2.0:
        verdict = "MARGINAL"
    else:
        verdict = "REMOVE"

    # Recommendations
    recommendations = []
    if scores["delta_alpha"] < 2:
        recommendations.append("Delta Alpha rendah — pertimbangkan retraining atau tuning hyperparameter")
    if scores["significance"] < 3:
        recommendations.append("Signifikansi statistik lemah — hasil mungkin noise, perlu lebih banyak data")
    if scores["stability"] < 3:
        recommendations.append("Feature drift terdeteksi — jalankan feature remediation pipeline")
    if scores["cost_efficiency"] < 2 and monthly_cost > 0:
        recommendations.append(f"Biaya Rp {monthly_cost:,.0f}/bln tidak tertutup revenue lift — pertimbangkan downgrade")
    if scores["latency"] < 3:
        recommendations.append("Latency tinggi — optimasi inference atau gunakan GPU")

    return ComponentVerdict(
        component=component_name,
        score_card={
            "scores": {k: round(v, 2) for k, v in scores.items()},
            "weighted_total": round(total, 2),
            "weights": weights,
        },
        delta_alpha=delta_alpha_result.delta_alpha,
        delta_sharpe=delta_alpha_result.delta_sharpe,
        p_value=min_p,
        significant=min_p < 0.05,
        verdict=verdict,
        recommendations=recommendations,
    )


# ── Utility ───────────────────────────────────────────────────────────────


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _bb_width(close: pd.Series, period: int = 20) -> pd.Series:
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return (2 * sd) / ma


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    from sqlalchemy import text
    from market.db.engine import get_sessionmaker

    parser = argparse.ArgumentParser(description="Advanced AI/ML Audit")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    parser.add_argument("--limit", type=int, default=10, help="Max tickers to audit")
    parser.add_argument("--output", type=str, default="audit_advanced_report.json", help="Output JSON file")
    parser.add_argument("--signal-threshold", type=float, default=0.1, help="Signal threshold for position")
    args = parser.parse_args()

    session = get_sessionmaker()()

    # Select tickers (top by OHLCV count for sufficient history)
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        rows = session.execute(
            text(
                "SELECT ticker, COUNT(*) as cnt FROM ohlcv "
                "WHERE ticker LIKE '%.JK' AND timeframe='1d' "
                "GROUP BY ticker ORDER BY cnt DESC LIMIT :limit"
            ),
            {"limit": args.limit},
        ).fetchall()
        tickers = [r[0] for r in rows]

    logger.info("=== ADVANCED AI/ML AUDIT ===")
    logger.info("Tickers: %d (%s)", len(tickers), tickers[:5])

    benchmark = load_benchmark(session)
    logger.info("Benchmark (^JKSE): %d daily returns", len(benchmark))

    report = AdvancedAuditReport(
        audit_date=pd.Timestamp.now().isoformat(),
        tickers_audited=tickers,
    )

    # ── Step 1: Feature Remediation ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 1: FEATURE REMEDIATION PIPELINE")
    logger.info("=" * 60)

    all_remediation = []
    for ticker in tickers[:5]:  # remediation on top 5 for speed
        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 500:
            continue

        logger.info("")
        logger.info("  [%s] Building features...", ticker)
        close = ohlcv["close"].astype(float)
        returns = close.pct_change()

        features = pd.DataFrame(index=ohlcv.index)
        features["ret_1"] = returns
        features["vol_20"] = returns.rolling(20).std()
        features["rsi"] = _rsi(close, 14)
        features["ma_ratio_20"] = close / close.rolling(20).mean()
        features["ma_ratio_50"] = close / close.rolling(50).mean()
        features["bb_width"] = _bb_width(close, 20)

        split_idx = int(len(features) * 0.7)
        ref_end = str(features.index[split_idx].date())
        cur_start = str(features.index[split_idx + 1].date())

        remediated, results = remediate_features(
            features, ohlcv, ref_end, cur_start, psi_threshold=0.25,
        )

        for r in results:
            all_remediation.append(r)
            icon = {"reweighted": "🔄", "replaced": "🔁", "dropped": "❌", "kept": "✅"}[r.action]
            logger.info("  %s %-20s PSI: %.3f → %.3f (%s)",
                        icon, r.feature, r.psi_before, r.psi_after, r.action)
            if r.notes:
                logger.info("      └─ %s", r.notes)

    report.remediation = all_remediation

    # Summary
    actions = {}
    for r in all_remediation:
        actions[r.action] = actions.get(r.action, 0) + 1
    logger.info("")
    logger.info("  Remediation summary: %s", actions)

    # ── Step 2: Delta Alpha Execution ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 2: DELTA ALPHA EXECUTION (MLSignal & MultiFactor vs Baseline)")
    logger.info("=" * 60)

    all_delta_alpha = []
    all_significance = []
    component_returns: dict[str, dict[str, pd.Series]] = {}  # {component: {ticker: returns}}

    for ticker in tickers:
        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 500:
            continue

        logger.info("")
        logger.info("  [%s] Generating predictions...", ticker)

        # MLSignal
        ml_signals = generate_mlsignal_predictions(ohlcv)
        ml_positions = convert_signal_to_position(ml_signals, args.signal_threshold)
        ml_returns = simulate_strategy_returns(ohlcv, ml_positions)

        # MultiFactor
        mf_signals = generate_multifactor_predictions(ohlcv)
        mf_positions = convert_signal_to_position(mf_signals, args.signal_threshold)
        mf_returns = simulate_strategy_returns(ohlcv, mf_positions)

        # Baseline
        baseline_signals = generate_baseline_signals(ohlcv)
        baseline_returns = simulate_strategy_returns(ohlcv, baseline_signals)

        # Store for aggregation
        component_returns.setdefault("MLSignal", {})[ticker] = ml_returns
        component_returns.setdefault("MultiFactor", {})[ticker] = mf_returns
        component_returns.setdefault("baseline", {})[ticker] = baseline_returns

    # Aggregate across tickers
    if component_returns:
        for component in ["MLSignal", "MultiFactor"]:
            comp_returns_list = list(component_returns[component].values())
            base_returns_list = list(component_returns["baseline"].values())

            if not comp_returns_list:
                continue

            avg_comp = pd.concat(comp_returns_list, axis=1).mean(axis=1)
            avg_base = pd.concat(base_returns_list, axis=1).mean(axis=1)

            bench_aligned = benchmark.reindex(avg_comp.index).dropna()

            comp_perf = compute_performance_metrics(avg_comp, bench_aligned)
            base_perf = compute_performance_metrics(avg_base, bench_aligned)

            delta = DeltaAlphaResult(
                component=component,
                alpha_ai=comp_perf.alpha,
                alpha_baseline=base_perf.alpha,
                delta_alpha=comp_perf.alpha - base_perf.alpha,
                sharpe_ai=comp_perf.sharpe_ratio,
                sharpe_baseline=base_perf.sharpe_ratio,
                delta_sharpe=comp_perf.sharpe_ratio - base_perf.sharpe_ratio,
                win_rate_ai=comp_perf.win_rate,
                win_rate_baseline=base_perf.win_rate,
                max_dd_ai=comp_perf.max_drawdown,
                max_dd_baseline=base_perf.max_drawdown,
                n_observations=len(avg_comp),
            )
            all_delta_alpha.append(delta)

            logger.info("")
            logger.info("  %s:", component)
            logger.info("    Alpha (AI):      %.4f (%.2f%%)", delta.alpha_ai, delta.alpha_ai * 100)
            logger.info("    Alpha (Base):    %.4f (%.2f%%)", delta.alpha_baseline, delta.alpha_baseline * 100)
            logger.info("    ΔAlpha:          %.4f (%.2f%%)", delta.delta_alpha, delta.delta_alpha * 100)
            logger.info("    Sharpe (AI):     %.3f", delta.sharpe_ai)
            logger.info("    Sharpe (Base):   %.3f", delta.sharpe_baseline)
            logger.info("    ΔSharpe:         %.3f", delta.delta_sharpe)
            logger.info("    Win Rate (AI):   %.1f%%", delta.win_rate_ai * 100)
            logger.info("    Max DD (AI):     %.2f%%", delta.max_dd_ai * 100)
            logger.info("    N observations:  %d", delta.n_observations)

            # ── Step 3: Statistical Significance ──
            aligned = pd.DataFrame({
                "ai": avg_comp,
                "baseline": avg_base,
            }).dropna()

            if len(aligned) > 30:
                # Paired t-test
                ttest_result = paired_ttest(aligned["ai"], aligned["baseline"])
                all_significance.append(ttest_result)
                logger.info("")
                logger.info("    Statistical Tests:")
                logger.info("      %s: t=%.3f, p=%.4f, significant=%s, effect=%.3f",
                            ttest_result.test_name, ttest_result.statistic,
                            ttest_result.p_value, ttest_result.significant,
                            ttest_result.effect_size)
                logger.info("        → %s", ttest_result.interpretation)

                # Diebold-Mariano (using return prediction errors)
                # Error = predicted return - actual return
                # For strategy returns, "prediction" = the signal-based return
                # "actual" = benchmark return (what you'd get without any signal)
                forecast_err_ai = aligned["ai"] - benchmark.reindex(aligned.index).fillna(0)
                forecast_err_base = aligned["baseline"] - benchmark.reindex(aligned.index).fillna(0)
                dm_result = diebold_mariano_test(forecast_err_ai, forecast_err_base, horizon=5)
                all_significance.append(dm_result)
                logger.info("      %s: DM=%.3f, p=%.4f, significant=%s, effect=%.3f",
                            dm_result.test_name, dm_result.statistic,
                            dm_result.p_value, dm_result.significant,
                            dm_result.effect_size)
                logger.info("        → %s", dm_result.interpretation)

                # Bootstrap Reality Check
                brc_result = whites_reality_check_approximation(
                    aligned["ai"], aligned["baseline"], n_bootstrap=500,
                )
                all_significance.append(brc_result)
                logger.info("      %s: stat=%.3f, p=%.4f, significant=%s, effect=%.3f",
                            brc_result.test_name, brc_result.statistic,
                            brc_result.p_value, brc_result.significant,
                            brc_result.effect_size)
                logger.info("        → %s", brc_result.interpretation)

    report.delta_alpha = all_delta_alpha
    report.significance = all_significance

    # ── Step 3b: Post-Trade Execution Analyzer (Ablation Feedback Loop) ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 3b: POST-TRADE EXECUTION ANALYZER (Slippage & Net Alpha)")
    logger.info("=" * 60)

    execution_analysis: dict = {}
    try:
        from market.analysis.execution_analyzer import run_full_analysis

        execution_analysis = run_full_analysis(session)
        decay_signal = execution_analysis.get("model_decay_signal", "no_data")
        n_tx = execution_analysis.get("transactions_count", 0)

        logger.info("  Transactions analyzed: %d", n_tx)
        logger.info("  Model decay signal: %s", decay_signal)

        if decay_signal == "high_slippage_decay":
            logger.warning("  ⚠ HIGH SLIPPAGE DETECTED — model predictions may be stale")
            logger.warning("    Consider retraining or adjusting signal thresholds")
        elif decay_signal == "moderate_slippage":
            logger.info("  Moderate slippage — monitor for degradation")

        eff = execution_analysis.get("execution_efficiency")
        if eff:
            logger.info("  Avg slippage: %.2f BPS (buy=%.2f, sell=%.2f)",
                        eff["avg_slippage_bps"], eff["avg_slippage_buy_bps"],
                        eff["avg_slippage_sell_bps"])
            logger.info("  Fill rate: %.1f%%, Cost ratio: %.3f%%",
                        eff["fill_rate"] * 100, eff["cost_ratio_pct"])

        na = execution_analysis.get("net_alpha")
        if na:
            logger.info("  Net Alpha: gross=%.0f, fees=%.0f, tax=%.0f, net=%.0f",
                        na["gross_pnl"], na["broker_fees_total"],
                        na["pph_final_total"], na["net_pnl"])
            logger.info("  Net Alpha BPS: %.2f", na["net_alpha_bps"])
    except Exception as e:
        logger.warning("  Execution analyzer skipped: %s", e)
        execution_analysis = {"error": str(e), "model_decay_signal": "skipped"}

    # ── Step 4: Automated Score Card ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 4: AUTOMATED AI UTILITY SCORE CARD")
    logger.info("=" * 60)

    # Get drift results for score card
    drift_for_card = []
    if all_remediation:
        for r in all_remediation:
            drift_for_card.append(DriftResult(
                feature=r.feature,
                psi=r.psi_after if r.action != "kept" else r.psi_before,
                ks_statistic=0.0, ks_pvalue=0.0,
                status=drift_status(r.psi_after if r.action != "kept" else r.psi_before),
            ))

    for delta_result in all_delta_alpha:
        component = delta_result.component
        comp_significance = [s for s in all_significance if component in s.interpretation or True]  # all tests apply

        # Filter significance results for this component (they all use the same tests)
        # In a multi-component scenario, we'd filter; here we use all
        comp_drift = drift_for_card[:6] if drift_for_card else None

        verdict = compute_component_score_card(
            component_name=component,
            delta_alpha_result=delta_result,
            significance_results=comp_significance,
            drift_results=comp_drift,
            latency_ms=None,  # will be profiled separately
            monthly_cost=0 if component == "MLSignal" else 0,  # both CPU-based
        )
        report.verdicts.append(verdict)

        logger.info("")
        logger.info("  ┌─────────────────────────────────────────────┐")
        logger.info("  │  COMPONENT: %-32s│", component)
        logger.info("  ├─────────────────────────────────────────────┤")
        logger.info("  │  ΔAlpha:     %8.4f (%+.2f%%)         │",
                    verdict.delta_alpha, verdict.delta_alpha * 100)
        logger.info("  │  ΔSharpe:    %8.3f                      │", verdict.delta_sharpe)
        logger.info("  │  p-value:    %8.4f                      │", verdict.p_value)
        logger.info("  │  Significant: %-5s                       │",
                    str(verdict.significant))
        logger.info("  │  Score:      %8.2f / 5.00               │",
                    verdict.score_card["weighted_total"])
        logger.info("  │  ┌──────────────────────────────────────┐  │")
        for k, v in verdict.score_card["scores"].items():
            logger.info("  │  │ %-20s %5.2f                 │  │", k, v)
        logger.info("  │  └──────────────────────────────────────┘  │")
        logger.info("  │                                             │")
        logger.info("  │  ★ VERDICT: %-31s│", f"【{verdict.verdict}】")
        logger.info("  └─────────────────────────────────────────────┘")

        if verdict.recommendations:
            logger.info("  Recommendations:")
            for rec in verdict.recommendations:
                logger.info("    • %s", rec)

    # ── Summary ──
    report.summary = {
        "tickers_audited": len(tickers),
        "components_evaluated": len(report.verdicts),
        "verdicts": {v.component: v.verdict for v in report.verdicts},
        "best_delta_alpha": max((v.delta_alpha for v in report.verdicts), default=0.0),
        "any_significant": any(v.significant for v in report.verdicts),
        "features_remediated": len(all_remediation),
        "remediation_actions": actions,
        "execution_decay_signal": execution_analysis.get("model_decay_signal", "skipped"),
        "execution_transactions": execution_analysis.get("transactions_count", 0),
    }

    logger.info("")
    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 60)
    logger.info("  Tickers audited:       %d", len(tickers))
    logger.info("  Components evaluated:   %d", len(report.verdicts))
    logger.info("  Features remediated:    %d", len(all_remediation))
    for v in report.verdicts:
        logger.info("  %s: ΔAlpha=%+.4f, p=%.4f → %s",
                    v.component, v.delta_alpha, v.p_value, v.verdict)

    # ── Save report ──
    report_dict = {
        "audit_date": report.audit_date,
        "tickers_audited": report.tickers_audited,
        "remediation": [asdict(r) for r in report.remediation],
        "delta_alpha": [asdict(r) for r in report.delta_alpha],
        "significance": [asdict(r) for r in report.significance],
        "verdicts": [
            {
                "component": v.component,
                "score_card": v.score_card,
                "delta_alpha": v.delta_alpha,
                "delta_sharpe": v.delta_sharpe,
                "p_value": v.p_value,
                "significant": v.significant,
                "verdict": v.verdict,
                "recommendations": v.recommendations,
            }
            for v in report.verdicts
        ],
        "summary": report.summary,
        "execution_analysis": execution_analysis,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report_dict, indent=2, default=str))
    logger.info("")
    logger.info("Full report saved to: %s", output_path)

    session.close()


if __name__ == "__main__":
    main()
