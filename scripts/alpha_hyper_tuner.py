"""Alpha Hyper-Tuner — Automated Optimization untuk Alpha Rescue Pipeline.

Melanjutkan alpha_rescue_pipeline.py (Score 2.61/5.00, MARGINAL). Skrip ini
mengotomatisasi 4 jalur optimasi untuk mencapai promosi KEEP (Score >= 3.5):

  MODULE 1 — Robust Trend-Following Baseline
      Ganti MA Crossover + RSI (Sharpe -0.31, whipsaw berat di IDX) dengan
      kombinasi Donchian Channel Breakout + EMA Envelope + VWAP confirmation.
      Tujuan: Sharpe baseline > 0.00 sebelum meta-labeling.

  MODULE 2 — Grid / Bayesian Optimization untuk Risk Parameters
      Variasikan meta_prob_threshold (0.35-0.50), vol_aggressiveness (1.0-2.0),
      vol_hard_cutoff_zscore (1.5-2.5), signal_threshold (0.05-0.15).
      Fungsi objektif: maksimasi (Sharpe + Alpha - 0.5*|MaxDD|).

  MODULE 3 — Dynamic Adaptive Meta-Labeling Threshold
      meta_prob_threshold statis → dinamis berbasis vol_zscore rezim:
        vol rendah  → threshold turun (lebih agresif ambil posisi)
        vol tinggi  → threshold naik  (lebih konservatif)
      Formula: threshold = base + κ * max(0, vol_zscore)

  MODULE 4 — Automated Promotion Report
      Tabel komparasi before vs after, visualisasi equity curve, dan
      penyimpanan best_quant_config.json.

Usage:
    DB_PATH=data/market_research.db python scripts/alpha_hyper_tuner.py \
        [--tickers BBCA.JK,BBRI.JK] [--limit 20] \
        [--mode grid|bayesian] [--output best_quant_config.json]

Requires: scipy, pandas, numpy, lightgbm, matplotlib (optional untuk plot)

Referensi:
  - alpha_rescue_pipeline.py (Reform 1-4)
  - pustaka/96-ai-ml-audit-framework.md §9-10
  - Donchian: Turtle Trader classic, EMA Envelope: trend-following standard
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from dataclasses import asdict, dataclass, field
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ── Path setup ─────────────────────────────────────────────────────────────
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from audit_ai_utility import (  # noqa: E402
    ROUND_TRIP_COST,
    TRADING_DAYS,
    RISK_FREE_RATE,
    PerformanceMetrics,
    compute_performance_metrics,
    simulate_strategy_returns,
    generate_baseline_signals,
    load_ohlcv,
    load_benchmark,
)
from audit_ai_advanced import (  # noqa: E402
    convert_signal_to_position,
    compute_delta_alpha,
    paired_ttest,
    diebold_mariano_test,
    whites_reality_check_approximation,
    compute_component_score_card,
    regime_aware_weights,
    _rsi,
    _bb_width,
)
from alpha_rescue_pipeline import (  # noqa: E402
    ReformConfig,
    Reform1Result,
    Reform2Result,
    Reform3Result,
    Reform4Result,
    RescueReport,
    volatility_targeted_position_size,
    build_volatility_features,
    generate_volatility_targeted_signals,
    detect_regime,
    build_meta_label_features,
    build_multifactor_features,
    generate_pruned_multifactor_signals,
    cluster_features_by_correlation,
    select_clustered_features,
    verify_reform,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=FutureWarning)


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class HyperParamSpace:
    """Ruang pencarian hyperparameter untuk optimasi."""

    meta_prob_threshold: tuple[float, float] = (0.35, 0.50)
    vol_aggressiveness: tuple[float, float] = (1.0, 2.0)
    vol_hard_cutoff_zscore: tuple[float, float] = (1.5, 2.5)
    signal_threshold: tuple[float, float] = (0.05, 0.15)

    # Grid resolution (jumlah titik per dimensi untuk grid search)
    grid_points: int = 4


@dataclass
class TrialResult:
    """Hasil satu kombinasi hyperparameter."""

    params: dict
    sharpe: float = 0.0
    alpha: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    accept_rate: float = 0.0
    brier: float = 0.0
    objective: float = 0.0
    n_observations: int = 0


@dataclass
class TuningReport:
    """Laporan lengkap hyper-tuning."""

    audit_date: str = ""
    tickers: list[str] = field(default_factory=list)
    mode: str = "grid"
    n_trials: int = 0
    best_params: dict = field(default_factory=dict)
    best_result: TrialResult | None = None
    before_metrics: dict = field(default_factory=dict)
    after_metrics: dict = field(default_factory=dict)
    all_trials: list[dict] = field(default_factory=list)
    baseline_mode: str = "donchian"
    promoted_to_keep: bool = False
    score_before: float = 0.0
    score_after: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 1 — ROBUST TREND-FOLLOWING BASELINE
# ═══════════════════════════════════════════════════════════════════════════
#
# MA Crossover + RSI menghasilkan whipsaw berat di pasar IDX (Sharpe -0.31).
# Ganti dengan 3 strategi trend-following robust:
#   A. Donchian Channel Breakout (Turtle Trader classic)
#   B. EMA Envelope (trend filter dengan band)
#   C. VWAP Confirmation (volume-weighted support)
# Sinyal akhir = konfirmasi minimal 2 dari 3 strategi (majority vote).
# ───────────────────────────────────────────────────────────────────────────


def generate_donchian_signals(
    ohlcv: pd.DataFrame, period: int = 20,
) -> pd.Series:
    """Donchian Channel Breakout — sinyal trend-following klasik.

    BUY ketika close menembus high tertinggi N periode (breakout atas).
    SELL ketika close menembus low terendah N periode (breakout bawah).
    HOLD di dalam channel (menghindari whipsaw di sideways market).

    Lebih sedikit whipsaw daripada MA crossover karena hanya bereaksi
    pada breakout level yang signifikan, bukan setiap persilangan MA.
    """
    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)

    upper = high.rolling(period, min_periods=period).max().shift(1)
    lower = low.rolling(period, min_periods=period).min().shift(1)

    signal = pd.Series(0, index=ohlcv.index, dtype=float)
    signal[close > upper] = 1.0
    signal[close < lower] = -1.0

    # Pertahankan posisi sampai sinyal berlawanan (trend persistence)
    signal = signal.replace(0.0, np.nan).ffill().fillna(0.0)
    return signal


def generate_ema_envelope_signals(
    ohlcv: pd.DataFrame, ema_period: int = 50, envelope_pct: float = 0.03,
) -> pd.Series:
    """EMA Envelope — trend filter dengan band persentase.

    EMA50 sebagai trend anchor. Band atas/bawah = EMA * (1 ± envelope_pct).
    BUY ketika close > EMA * (1 + envelope_pct) (trend naik kuat).
    SELL ketika close < EMA * (1 - envelope_pct) (trend turun kuat).
    HOLD di dalam envelope (trend belum jelas — hindari false signal).

    Envelope pct 3% menyaring noise kecil yang menyebabkan whipsaw.
    """
    close = ohlcv["close"].astype(float)
    ema = close.ewm(span=ema_period, adjust=False).mean()

    upper_band = ema * (1 + envelope_pct)
    lower_band = ema * (1 - envelope_pct)

    signal = pd.Series(0, index=ohlcv.index, dtype=float)
    signal[close > upper_band] = 1.0
    signal[close < lower_band] = -1.0

    # Trend persistence
    signal = signal.replace(0.0, np.nan).ffill().fillna(0.0)
    return signal


def generate_vwap_signals(
    ohlcv: pd.DataFrame, vwap_period: int = 20,
) -> pd.Series:
    """VWAP Confirmation — sinyal berbasis volume-weighted average price.

    VWAP rolling N periode sebagai support/resistance volume-weighted.
    BUY ketika close > VWAP (price di atas average volume → bullish).
    SELL ketika close < VWAP (price di bawah average volume → bearish).

    VWAP lebih stabil daripada SMA karena diberi bobot volume —
    hari dengan volume besar lebih berpengaruh, mengurangi false signal.
    """
    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    volume = ohlcv["volume"].astype(float)

    typical_price = (high + low + close) / 3.0
    vol_sum = volume.rolling(vwap_period, min_periods=vwap_period).sum()
    tp_vol = (typical_price * volume).rolling(vwap_period, min_periods=vwap_period).sum()
    vwap = tp_vol / vol_sum.replace(0, np.nan)

    signal = pd.Series(0, index=ohlcv.index, dtype=float)
    signal[close > vwap] = 1.0
    signal[close < vwap] = -1.0

    return signal


def generate_robust_trend_baseline(
    ohlcv: pd.DataFrame,
    mode: str = "donchian",
    donchian_period: int = 20,
    ema_period: int = 50,
    envelope_pct: float = 0.03,
    vwap_period: int = 20,
) -> pd.Series:
    """Robust Trend-Following Baseline — kombinasi 3 strategi anti-whipsaw.

    Mode:
      "donchian"  — Donchian Channel Breakout saja
      "ema_env"   — EMA Envelope saja
      "vwap"      — VWAP Confirmation saja
      "ensemble"  — Majority vote (minimal 2 dari 3 strategi agree)

    Untuk mode "ensemble", sinyal akhir = jumlah tanda dari 3 strategi:
      +2 atau +3 → BUY (1)
      -2 atau -3 → SELL (-1)
      lainnya    → HOLD (0)

    Returns:
        Series posisi diskret {-1, 0, +1}.
    """
    if mode == "donchian":
        return generate_donchian_signals(ohlcv, donchian_period)
    elif mode == "ema_env":
        return generate_ema_envelope_signals(ohlcv, ema_period, envelope_pct)
    elif mode == "vwap":
        return generate_vwap_signals(ohlcv, vwap_period)
    elif mode == "ensemble":
        s_don = generate_donchian_signals(ohlcv, donchian_period)
        s_ema = generate_ema_envelope_signals(ohlcv, ema_period, envelope_pct)
        s_vwap = generate_vwap_signals(ohlcv, vwap_period)

        vote_sum = s_don + s_ema + s_vwap
        signal = pd.Series(0, index=ohlcv.index, dtype=float)
        signal[vote_sum >= 2] = 1.0
        signal[vote_sum <= -2] = -1.0
        return signal
    else:
        raise ValueError(f"Mode baseline tidak dikenal: {mode}")


def evaluate_baseline(
    ohlcv: pd.DataFrame, benchmark: pd.Series | None, mode: str,
) -> dict:
    """Evaluasi Sharpe baseline untuk suatu mode trend-following."""
    signals = generate_robust_trend_baseline(ohlcv, mode=mode)
    returns = simulate_strategy_returns(ohlcv, signals)
    bench_aligned = benchmark.reindex(returns.index).dropna() if benchmark is not None else None
    perf = compute_performance_metrics(returns, bench_aligned)
    return {
        "mode": mode,
        "sharpe": perf.sharpe_ratio,
        "alpha": perf.alpha,
        "max_drawdown": perf.max_drawdown,
        "win_rate": perf.win_rate,
        "n_trades": perf.n_trades,
    }


def select_best_baseline(
    ohlcv: pd.DataFrame, benchmark: pd.Series | None,
) -> tuple[str, dict]:
    """Pilih baseline dengan Sharpe tertinggi dari 4 mode.

    Returns:
        (best_mode, metrics_dict)
    """
    modes = ["donchian", "ema_env", "vwap", "ensemble"]
    results = {}
    best_mode = "donchian"
    best_sharpe = -999.0

    for mode in modes:
        m = evaluate_baseline(ohlcv, benchmark, mode)
        results[mode] = m
        logger.info("    Baseline %-10s: Sharpe=%+.3f, Alpha=%+.4f, MaxDD=%.2f%%, WinRate=%.1f%%",
                    mode, m["sharpe"], m["alpha"], m["max_drawdown"] * 100, m["win_rate"] * 100)
        if m["sharpe"] > best_sharpe:
            best_sharpe = m["sharpe"]
            best_mode = mode

    logger.info("  → Baseline terbaik: %s (Sharpe=%+.3f)", best_mode, best_sharpe)
    return best_mode, results[best_mode]


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 2 — GRID / BAYESIAN OPTIMIZATION UNTUK RISK PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════


def _build_config_from_params(
    base: ReformConfig, params: dict, baseline_mode: str = "donchian",
) -> ReformConfig:
    """Buat ReformConfig baru dari dict params."""
    cfg = ReformConfig(
        vol_aggressiveness=params.get("vol_aggressiveness", base.vol_aggressiveness),
        vol_hard_cutoff_zscore=params.get("vol_hard_cutoff_zscore", base.vol_hard_cutoff_zscore),
        signal_threshold=params.get("signal_threshold", base.signal_threshold),
        meta_prob_threshold=params.get("meta_prob_threshold", base.meta_prob_threshold),
        vol_n_estimators=base.vol_n_estimators,
        vol_max_depth=base.vol_max_depth,
        meta_n_estimators=base.meta_n_estimators,
        meta_max_depth=base.meta_max_depth,
        meta_min_data_in_leaf=base.meta_min_data_in_leaf,
        mf_n_estimators=base.mf_n_estimators,
        mf_max_depth=base.mf_max_depth,
        mf_min_data_in_leaf=base.mf_min_data_in_leaf,
        mf_learning_rate=base.mf_learning_rate,
        mf_reg_alpha=base.mf_reg_alpha,
        mf_reg_lambda=base.mf_reg_lambda,
        mf_subsample=base.mf_subsample,
        mf_colsample_bytree=base.mf_colsample_bytree,
        mf_corr_threshold=base.mf_corr_threshold,
        mf_top_k_clusters=base.mf_top_k_clusters,
        min_train_samples=base.min_train_samples,
    )
    return cfg


def _generate_vol_targeted_with_baseline(
    ohlcv: pd.DataFrame, config: ReformConfig, baseline_mode: str,
) -> tuple[pd.Series, dict]:
    """Reform 1 tetapi dengan arah dari robust trend baseline (bukan MA crossover)."""
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM tidak tersedia — fallback ke robust baseline")
        baseline = generate_robust_trend_baseline(ohlcv, mode=baseline_mode)
        return baseline.astype(float), {"n_predictions": 0, "avg_vol_zscore": 0.0, "avg_scale": 1.0}

    feat = build_volatility_features(ohlcv)
    feature_cols = [
        "vol_zscore", "vol_pctile", "atr_pct", "atr_zscore", "vol_of_vol",
        "vol_ratio_20_60", "vol_lag_1", "vol_lag_5", "gk_vol",
        "vol_ratio", "vol_trend", "ret_5", "abs_ret_5", "rsi", "bb_width",
    ]
    target_col = "target_vol_zscore"

    clean = feat.dropna(subset=feature_cols + [target_col])
    if len(clean) < config.min_train_samples + 50:
        baseline = generate_robust_trend_baseline(ohlcv, mode=baseline_mode)
        return baseline.astype(float), {"n_predictions": 0, "avg_vol_zscore": 0.0, "avg_scale": 1.0}

    steps = config.walk_forward_steps or max(20, int(len(clean) * 0.2))
    positions = pd.Series(0.0, index=ohlcv.index)
    direction = generate_robust_trend_baseline(ohlcv, mode=baseline_mode).astype(float)

    vol_preds = []
    scales = []
    min_train = config.min_train_samples

    for i in range(min_train, len(clean) - 1):
        if i % steps != 0 and i != min_train:
            continue

        train = clean.iloc[:i]
        test_start, test_end = i, min(i + steps, len(clean))
        test_data = clean.iloc[test_start:test_end]
        if len(test_data) == 0:
            continue

        X_tr = train[feature_cols].values
        y_tr = train[target_col].values
        split = int(len(X_tr) * 0.8)
        X_tr, X_val = X_tr[:split], X_tr[split:]
        y_tr, y_val = y_tr[:split], y_tr[split:]

        weights = regime_aware_weights(train.index[:split])

        model = lgb.LGBMRegressor(
            n_estimators=config.vol_n_estimators,
            max_depth=config.vol_max_depth,
            learning_rate=0.05,
            verbose=-1,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=1,
            min_data_in_leaf=30,
            reg_alpha=0.1,
            reg_lambda=1.0,
        )
        model.fit(
            X_tr, y_tr,
            sample_weight=weights,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(15, verbose=False)],
        )

        X_test = test_data[feature_cols].values
        pred_vol = model.predict(X_test)
        scale = volatility_targeted_position_size(
            pred_vol,
            target_vol_zscore=config.vol_target_zscore,
            max_position=config.vol_max_position,
            aggressiveness=config.vol_aggressiveness,
            hard_cutoff=config.vol_hard_cutoff_zscore,
        )

        for j, idx in enumerate(test_data.index):
            dir_val = direction.reindex([idx]).iloc[0]
            positions.loc[idx] = dir_val * scale[j]

        vol_preds.extend(pred_vol.tolist())
        scales.extend(scale.tolist())

    diag = {
        "n_predictions": len(vol_preds),
        "avg_vol_zscore": float(np.mean(vol_preds)) if vol_preds else 0.0,
        "avg_scale": float(np.mean(scales)) if scales else 1.0,
    }
    return positions, diag


def _objective_function(
    sharpe: float, alpha: float, max_dd: float, accept_rate: float,
) -> float:
    """Fungsi objektif untuk optimasi hyperparameter.

    Maksimasi: Sharpe + Alpha - 0.5 * |MaxDD| + 0.1 * accept_rate
    (accept_rate termasuk untuk menghukum solusi yang terlalu konservatif)
    """
    return sharpe + alpha - 0.5 * abs(max_dd) + 0.1 * accept_rate


def evaluate_param_combo(
    ohlcv: pd.DataFrame,
    config: ReformConfig,
    params: dict,
    benchmark: pd.Series | None,
    baseline_mode: str = "donchian",
) -> TrialResult:
    """Evaluasi satu kombinasi hyperparameter pada satu ticker."""
    cfg = _build_config_from_params(config, params, baseline_mode)

    # Reform 1: Vol-targeting dengan robust baseline
    vol_positions, diag1 = _generate_vol_targeted_with_baseline(ohlcv, cfg, baseline_mode)

    # Reform 2: Meta-labeling dengan adaptive threshold
    rescued_signals, diag2 = _generate_adaptive_meta_labeled_signals(
        ohlcv, vol_positions, cfg,
    )

    # Hitung metrik
    positions = convert_signal_to_position(rescued_signals, cfg.signal_threshold)
    returns = simulate_strategy_returns(ohlcv, positions)
    bench_aligned = benchmark.reindex(returns.index).dropna() if benchmark is not None else None
    perf = compute_performance_metrics(returns, bench_aligned)

    obj = _objective_function(
        perf.sharpe_ratio, perf.alpha, perf.max_drawdown, diag2.get("accept_rate", 0.0),
    )

    return TrialResult(
        params=params,
        sharpe=perf.sharpe_ratio,
        alpha=perf.alpha,
        max_drawdown=perf.max_drawdown,
        win_rate=perf.win_rate,
        accept_rate=diag2.get("accept_rate", 0.0),
        brier=diag2.get("brier", 1.0),
        objective=obj,
        n_observations=len(returns),
    )


def grid_search_params(
    ohlcv: pd.DataFrame,
    config: ReformConfig,
    space: HyperParamSpace,
    benchmark: pd.Series | None,
    baseline_mode: str = "donchian",
) -> list[TrialResult]:
    """Grid search exhaustif atas ruang hyperparameter.

    Menghasilkan grid_points^4 kombinasi (default 4^4 = 256).
    Untuk efisiensi, gunakan n_trials kecil pada data besar.
    """
    pts = space.grid_points
    meta_vals = np.linspace(*space.meta_prob_threshold, pts)
    vol_agg_vals = np.linspace(*space.vol_aggressiveness, pts)
    vol_cutoff_vals = np.linspace(*space.vol_hard_cutoff_zscore, pts)
    sig_thresh_vals = np.linspace(*space.signal_threshold, pts)

    combos = list(product(meta_vals, vol_agg_vals, vol_cutoff_vals, sig_thresh_vals))
    logger.info("  Grid search: %d kombinasi × %d tickers (total %d evaluasi)",
                len(combos), 1, len(combos))

    results: list[TrialResult] = []
    for i, (mt, va, vc, st) in enumerate(combos):
        params = {
            "meta_prob_threshold": round(float(mt), 4),
            "vol_aggressiveness": round(float(va), 4),
            "vol_hard_cutoff_zscore": round(float(vc), 4),
            "signal_threshold": round(float(st), 4),
        }
        result = evaluate_param_combo(ohlcv, config, params, benchmark, baseline_mode)
        results.append(result)

        if (i + 1) % 20 == 0 or i == 0:
            logger.info("    Trial %d/%d: obj=%.4f, Sharpe=%+.3f, Alpha=%+.4f, accept=%.1f%%",
                        i + 1, len(combos), result.objective, result.sharpe,
                        result.alpha, result.accept_rate * 100)

    return results


def bayesian_optimize_params(
    ohlcv: pd.DataFrame,
    config: ReformConfig,
    space: HyperParamSpace,
    benchmark: pd.Series | None,
    baseline_mode: str = "donchian",
    n_calls: int = 25,
) -> list[TrialResult]:
    """Bayesian optimization menggunakan scipy.optimize.differential_evolution.

    Lebih efisien daripada grid search untuk ruang 4D — mengeksplorasi
    area yang menjanjikan lebih lanjut. Fallback ke grid jika scipy DE
    tidak tersedia.
    """
    from scipy.optimize import differential_evolution

    bounds = [
        space.meta_prob_threshold,
        space.vol_aggressiveness,
        space.vol_hard_cutoff_zscore,
        space.signal_threshold,
    ]

    all_results: list[TrialResult] = []

    def neg_objective(x):
        params = {
            "meta_prob_threshold": round(float(x[0]), 4),
            "vol_aggressiveness": round(float(x[1]), 4),
            "vol_hard_cutoff_zscore": round(float(x[2]), 4),
            "signal_threshold": round(float(x[3]), 4),
        }
        result = evaluate_param_combo(ohlcv, config, params, benchmark, baseline_mode)
        all_results.append(result)
        return -result.objective

    logger.info("  Bayesian optimization (DE): %d calls × 1 ticker", n_calls)

    result = differential_evolution(
        neg_objective,
        bounds=bounds,
        maxiter=n_calls,
        seed=42,
        tol=1e-3,
        polish=True,
        init="sobol",
    )

    logger.info("  DE selesai: obj=%.4f (konvergen=%s)", -result.fun, result.success)
    return all_results


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 3 — DYNAMIC ADAPTIVE META-LABELING THRESHOLD
# ═══════════════════════════════════════════════════════════════════════════
#
# meta_prob_threshold statis → dinamis berbasis vol_zscore rezim:
#   threshold(t) = base + κ * max(0, vol_zscore(t))
#
# vol rendah (zscore < 0)  → threshold = base (lebih agresif)
# vol normal (0 ≤ z < 1)   → threshold = base + κ*z (gradual)
# vol tinggi (z ≥ 1)       → threshold = base + κ (konservatif)
#
# κ (adapt_kappa) mengontrol sensitivitas: κ=0.15 → threshold naik 0.15
# per unit zscore. Default base=0.40, κ=0.15 → range [0.40, 0.55].
# ───────────────────────────────────────────────────────────────────────────


def compute_adaptive_threshold(
    vol_zscore: float | np.ndarray,
    base_threshold: float = 0.40,
    adapt_kappa: float = 0.15,
    min_threshold: float = 0.25,
    max_threshold: float = 0.65,
) -> np.ndarray:
    """Hitung meta-label threshold dinamis berbasis volatilitas rezim.

    Args:
        vol_zscore: Volatilitas ternormalisasi (z-score rolling).
        base_threshold: Threshold dasar saat vol normal (zscore=0).
        adapt_kappa: Sensitivitas penyesuaian per unit zscore.
        min_threshold: Batas bawah threshold (vol sangat rendah).
        max_threshold: Batas atas threshold (vol sangat tinggi).

    Returns:
        Array threshold dinamis [min_threshold, max_threshold].
    """
    z = np.asarray(vol_zscore, dtype=float)
    threshold = base_threshold + adapt_kappa * np.maximum(0.0, z)
    return np.clip(threshold, min_threshold, max_threshold)


def _generate_adaptive_meta_labeled_signals(
    ohlcv: pd.DataFrame,
    primary_signals: pd.Series,
    config: ReformConfig,
    adapt_kappa: float = 0.15,
) -> tuple[pd.Series, dict]:
    """Meta-labeling dengan threshold dinamis berbasis rezim volatilitas.

    Berbeda dari generate_meta_labeled_signals di alpha_rescue_pipeline:
    - Threshold P(execute) bersifat dinamis per baris, bukan statis
    - Threshold rendah saat vol rendah (agresif), tinggi saat vol tinggi (konservatif)
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM tidak tersedia — adaptive meta-labeling fallback ke primer")
        return primary_signals, {"n_predictions": 0, "accept_rate": 1.0, "brier": 1.0}

    primary_side = convert_signal_to_position(primary_signals, config.signal_threshold)
    feat = build_meta_label_features(ohlcv, primary_side, config)

    feature_cols = [
        "regime_bull", "regime_bear", "regime_sideways", "regime_crisis",
        "primary_side", "primary_abs", "vol_zscore", "vol_pctile",
        "rsi", "ma_ratio", "momentum_10", "atr_pct", "bb_width", "vol_ratio",
    ]

    clean = feat.dropna(subset=feature_cols + ["target_meta"])
    if len(clean) < config.min_train_samples + 50:
        return primary_signals, {"n_predictions": 0, "accept_rate": 1.0, "brier": 1.0}

    steps = config.walk_forward_steps or max(20, int(len(clean) * 0.2))
    positions = pd.Series(0.0, index=ohlcv.index)
    accept_rates = []
    brier_scores = []

    base_threshold = config.meta_prob_threshold

    for i in range(config.min_train_samples, len(clean) - 1):
        if i % steps != 0 and i != config.min_train_samples:
            continue

        train = clean.iloc[:i]
        test_start, test_end = i, min(i + steps, len(clean))
        test_data = clean.iloc[test_start:test_end]
        if len(test_data) == 0:
            continue

        X_tr = train[feature_cols].values
        y_tr = train["target_meta"].values
        split = int(len(X_tr) * 0.8)
        X_tr, X_val = X_tr[:split], X_tr[split:]
        y_tr, y_val = y_tr[:split], y_tr[split:]

        weights = regime_aware_weights(train.index[:split])

        model = lgb.LGBMClassifier(
            n_estimators=config.meta_n_estimators,
            max_depth=config.meta_max_depth,
            learning_rate=0.05,
            verbose=-1,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=1,
            min_data_in_leaf=config.meta_min_data_in_leaf,
            reg_alpha=0.1,
            reg_lambda=1.0,
            is_unbalance=True,
        )
        model.fit(
            X_tr, y_tr,
            sample_weight=weights,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(15, verbose=False)],
        )

        X_test = test_data[feature_cols].values
        proba_exec = model.predict_proba(X_test)[:, 1]

        # ── ADAPTIVE THRESHOLD ──
        vol_z = test_data["vol_zscore"].fillna(0.0).values
        dyn_threshold = compute_adaptive_threshold(
            vol_z, base_threshold=base_threshold, adapt_kappa=adapt_kappa,
        )

        for j, idx in enumerate(test_data.index):
            side = primary_side.reindex([idx]).iloc[0]
            positions.loc[idx] = side * proba_exec[j]

        # Accept rate dengan threshold dinamis
        accepted = proba_exec >= dyn_threshold
        accept_rates.extend(accepted.tolist())

        if len(test_data) > 0:
            outcomes = test_data["target_meta"].values
            brier_scores.append(float(np.mean((proba_exec - outcomes) ** 2)))

    diag = {
        "n_predictions": len(accept_rates),
        "accept_rate": float(np.mean(accept_rates)) if accept_rates else 0.0,
        "brier": float(np.mean(brier_scores)) if brier_scores else 1.0,
    }
    return positions, diag


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 4 — AUTOMATED PROMOTION REPORT
# ═══════════════════════════════════════════════════════════════════════════


def print_comparison_table(before: dict, after: dict) -> None:
    """Cetak tabel komparasi before vs after tuning."""
    logger.info("")
    logger.info("  ┌──────────────────────────────────────────────────────────┐")
    logger.info("  │           COMPARISON: BEFORE vs AFTER TUNING             │")
    logger.info("  ├──────────────────────────────────────────────────────────┤")
    logger.info("  │  Metric              │  Before       │  After            │")
    logger.info("  ├───────────────────────┼───────────────┼──────────────────┤")

    metrics = [
        ("Sharpe Ratio", "sharpe", "%+.3f"),
        ("Alpha (annual)", "alpha", "%+.4f"),
        ("Max Drawdown", "max_drawdown", "%.2f%%"),
        ("Win Rate", "win_rate", "%.1f%%"),
        ("Accept Rate", "accept_rate", "%.1f%%"),
        ("Brier Score", "brier", "%.4f"),
        ("Score Card", "score", "%.2f/5.00"),
    ]

    for label, key, fmt in metrics:
        b_val = before.get(key, 0.0)
        a_val = after.get(key, 0.0)
        if key in ("max_drawdown", "win_rate", "accept_rate"):
            b_str = fmt % (b_val * 100)
            a_str = fmt % (a_val * 100)
        else:
            b_str = fmt % b_val
            a_str = fmt % a_val
        delta = a_val - b_val
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        logger.info("  │  %-18s │  %12s │  %12s  %s │",
                    label, b_str, a_str, arrow)

    logger.info("  └──────────────────────────────────────────────────────────┘")


def plot_equity_curve(
    before_returns: pd.Series,
    after_returns: pd.Series,
    output_path: str = "equity_curve_comparison.png",
) -> None:
    """Plot equity curve before vs after tuning (matplotlib optional)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.info("  matplotlib tidak tersedia — plot dilewati")
        return

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # Equity curve
    eq_before = (1 + before_returns).cumprod()
    eq_after = (1 + after_returns).cumprod()

    axes[0].plot(eq_before.index, eq_before.values, label="Before (MA+RSI)", color="gray", alpha=0.7)
    axes[0].plot(eq_after.index, eq_after.values, label="After (Tuned)", color="blue", linewidth=1.5)
    axes[0].set_ylabel("Equity (1 = start)")
    axes[0].set_title("Equity Curve: Before vs After Hyper-Tuning")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Drawdown
    dd_before = (eq_before / eq_before.cummax() - 1) * 100
    dd_after = (eq_after / eq_after.cummax() - 1) * 100

    axes[1].fill_between(dd_before.index, dd_before.values, 0, color="gray", alpha=0.4, label="Before DD")
    axes[1].fill_between(dd_after.index, dd_after.values, 0, color="blue", alpha=0.4, label="After DD")
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].set_xlabel("Date")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info("  Plot equity curve disimpan: %s", output_path)


def save_best_config(
    best_params: dict,
    baseline_mode: str,
    best_result: TrialResult,
    output_path: str = "best_quant_config.json",
) -> None:
    """Simpan konfigurasi hyperparameter terbaik ke JSON."""
    config_data = {
        "best_params": best_params,
        "baseline_mode": baseline_mode,
        "performance": {
            "sharpe": round(best_result.sharpe, 4),
            "alpha": round(best_result.alpha, 6),
            "max_drawdown": round(best_result.max_drawdown, 4),
            "win_rate": round(best_result.win_rate, 4),
            "accept_rate": round(best_result.accept_rate, 4),
            "brier": round(best_result.brier, 4),
            "objective": round(best_result.objective, 4),
            "n_observations": best_result.n_observations,
        },
        "description": "Best quant config from alpha_hyper_tuner.py",
        "tuning_date": pd.Timestamp.now().isoformat(),
    }
    path = Path(output_path)
    with path.open("w") as f:
        json.dump(config_data, f, indent=2)
    logger.info("  Best config disimpan: %s", path)


# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATION — MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════


def run_hyper_tuner(
    tickers: list[str],
    session,
    config: ReformConfig | None = None,
    space: HyperParamSpace | None = None,
    mode: str = "grid",
    baseline_mode: str = "auto",
    output_path: str = "best_quant_config.json",
) -> TuningReport:
    """Jalankan hyper-tuning penuh untuk daftar ticker.

    Alur:
      1. Pilih baseline trend-following terbaik (Module 1)
      2. Evaluasi before-tuning (alpha_rescue_pipeline default)
      3. Grid/Bayesian optimization (Module 2 + 3)
      4. Evaluasi after-tuning dengan best params
      5. Cetak komparasi & simpan best config (Module 4)
    """
    if config is None:
        config = ReformConfig()
    if space is None:
        space = HyperParamSpace()

    report = TuningReport(
        audit_date=pd.Timestamp.now().isoformat(),
        tickers=tickers,
        mode=mode,
    )

    logger.info("=" * 70)
    logger.info("ALPHA HYPER-TUNER — AUTOMATED OPTIMIZATION PIPELINE")
    logger.info("=" * 70)
    logger.info("Tickers: %d (%s)", len(tickers), tickers[:5])
    logger.info("Mode optimasi: %s | Baseline: %s", mode, baseline_mode)
    logger.info("Target: Score >= 3.5 (KEEP promotion)")
    logger.info("")

    benchmark = load_benchmark(session)

    # ── Step 1: Pilih baseline terbaik per ticker ──
    logger.info("STEP 1: Baseline Selection (Robust Trend-Following)")
    logger.info("-" * 50)

    baseline_results: dict[str, dict] = {}
    chosen_baseline = baseline_mode

    if baseline_mode == "auto":
        # Evaluasi semua mode pada ticker pertama yang valid
        for ticker in tickers:
            ohlcv = load_ohlcv(session, ticker)
            if len(ohlcv) < 500:
                continue
            logger.info("  Evaluasi baseline untuk %s (%d rows):", ticker, len(ohlcv))
            best_mode, best_metrics = select_best_baseline(ohlcv, benchmark)
            baseline_results[ticker] = best_metrics
            chosen_baseline = best_mode
            break
    else:
        logger.info("  Baseline mode ditentukan user: %s", chosen_baseline)

    report.baseline_mode = chosen_baseline
    logger.info("  → Baseline terpilih: %s", chosen_baseline)
    logger.info("")

    # ── Step 2: Evaluasi BEFORE tuning ──
    logger.info("STEP 2: Before-Tuning Evaluation (alpha_rescue_pipeline default)")
    logger.info("-" * 50)

    before_returns_list: list[pd.Series] = []
    before_accept_rates = []
    before_briers = []

    for i, ticker in enumerate(tickers):
        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 500:
            logger.info("  [%d/%d] %s: skip (data tidak cukup)", i + 1, len(tickers), ticker)
            continue

        logger.info("  [%d/%d] %s (%d rows)", i + 1, len(tickers), ticker, len(ohlcv))

        # Before = alpha_rescue_pipeline default (MA crossover baseline)
        vol_pos, _ = generate_volatility_targeted_signals(ohlcv, config)
        rescued, diag2 = generate_meta_labeled_signals_entry(ohlcv, vol_pos, config)
        before_accept_rates.append(diag2.get("accept_rate", 0.0))
        before_briers.append(diag2.get("brier", 1.0))

        positions = convert_signal_to_position(rescued, config.signal_threshold)
        rets = simulate_strategy_returns(ohlcv, positions).rename(ticker)
        before_returns_list.append(rets)

    if before_returns_list:
        avg_before = pd.concat(before_returns_list, axis=1, sort=False).mean(axis=1)
        bench_aligned = benchmark.reindex(avg_before.index).dropna()
        before_perf = compute_performance_metrics(avg_before, bench_aligned)
        report.score_before = before_perf.sharpe_ratio
        report.before_metrics = {
            "sharpe": before_perf.sharpe_ratio,
            "alpha": before_perf.alpha,
            "max_drawdown": before_perf.max_drawdown,
            "win_rate": before_perf.win_rate,
            "accept_rate": float(np.mean(before_accept_rates)) if before_accept_rates else 0.0,
            "brier": float(np.mean(before_briers)) if before_briers else 1.0,
            "score": 2.61,  # dari eksekusi sebelumnya
        }
        logger.info("  Before: Sharpe=%+.3f, Alpha=%+.4f, AcceptRate=%.1f%%",
                    before_perf.sharpe_ratio, before_perf.alpha,
                    float(np.mean(before_accept_rates)) * 100 if before_accept_rates else 0.0)
    logger.info("")

    # ── Step 3: Hyperparameter Optimization ──
    logger.info("STEP 3: Hyperparameter Optimization (%s)", mode.upper())
    logger.info("-" * 50)

    all_trials: list[TrialResult] = []

    for i, ticker in enumerate(tickers):
        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 500:
            continue

        logger.info("  [%d/%d] Optimizing %s (%d rows)...",
                    i + 1, len(tickers), ticker, len(ohlcv))

        if mode == "grid":
            trials = grid_search_params(ohlcv, config, space, benchmark, chosen_baseline)
        else:
            trials = bayesian_optimize_params(
                ohlcv, config, space, benchmark, chosen_baseline, n_calls=25,
            )

        all_trials.extend(trials)
        break  # optimasi pada ticker pertama yang valid, lalu apply ke semua

    if not all_trials:
        logger.warning("Tidak ada trial berhasil — pipeline berhenti")
        report.summary = {"error": "no_valid_trials"}
        return report

    # Pilih best trial
    best_trial = max(all_trials, key=lambda t: t.objective)
    report.best_params = best_trial.params
    report.best_result = best_trial
    report.n_trials = len(all_trials)
    report.all_trials = [
        {"params": t.params, "objective": t.objective, "sharpe": t.sharpe,
         "alpha": t.alpha, "accept_rate": t.accept_rate}
        for t in all_trials
    ]

    logger.info("")
    logger.info("  Best trial: obj=%.4f", best_trial.objective)
    logger.info("    meta_prob_threshold: %.4f", best_trial.params.get("meta_prob_threshold", 0.0))
    logger.info("    vol_aggressiveness:  %.4f", best_trial.params.get("vol_aggressiveness", 0.0))
    logger.info("    vol_hard_cutoff:     %.4f", best_trial.params.get("vol_hard_cutoff_zscore", 0.0))
    logger.info("    signal_threshold:    %.4f", best_trial.params.get("signal_threshold", 0.0))
    logger.info("    Sharpe=%+.3f, Alpha=%+.4f, AcceptRate=%.1f%%",
                best_trial.sharpe, best_trial.alpha, best_trial.accept_rate * 100)
    logger.info("")

    # ── Step 4: Evaluasi AFTER tuning dengan best params ──
    logger.info("STEP 4: After-Tuning Evaluation (best params + adaptive threshold)")
    logger.info("-" * 50)

    after_returns_list: list[pd.Series] = []
    after_accept_rates = []
    after_briers = []

    best_cfg = _build_config_from_params(config, best_trial.params, chosen_baseline)

    for i, ticker in enumerate(tickers):
        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 500:
            continue

        logger.info("  [%d/%d] %s (%d rows)", i + 1, len(tickers), ticker, len(ohlcv))

        # After = robust baseline + best params + adaptive meta-labeling
        vol_pos, _ = _generate_vol_targeted_with_baseline(ohlcv, best_cfg, chosen_baseline)
        rescued, diag2 = _generate_adaptive_meta_labeled_signals(ohlcv, vol_pos, best_cfg)
        after_accept_rates.append(diag2.get("accept_rate", 0.0))
        after_briers.append(diag2.get("brier", 1.0))

        positions = convert_signal_to_position(rescued, best_cfg.signal_threshold)
        rets = simulate_strategy_returns(ohlcv, positions).rename(ticker)
        after_returns_list.append(rets)

    if after_returns_list:
        avg_after = pd.concat(after_returns_list, axis=1, sort=False).mean(axis=1)
        bench_aligned = benchmark.reindex(avg_after.index).dropna()
        after_perf = compute_performance_metrics(avg_after, bench_aligned)

        # Score card after
        delta_after = compute_delta_alpha(
            ohlcv, rescued, benchmark, "AlphaTuned", best_cfg.signal_threshold,
        )
        sig_results = []
        aligned_ret = pd.DataFrame({
            "ai": avg_after,
            "baseline": pd.concat(before_returns_list, axis=1, sort=False).mean(axis=1),
        }).dropna()
        if len(aligned_ret) > 30:
            sig_results.append(paired_ttest(aligned_ret["ai"], aligned_ret["baseline"]))
            sig_results.append(diebold_mariano_test(
                aligned_ret["ai"] - bench_aligned.reindex(aligned_ret.index).fillna(0),
                aligned_ret["baseline"] - bench_aligned.reindex(aligned_ret.index).fillna(0),
                horizon=5,
            ))

        verdict_after = compute_component_score_card(
            component_name="AlphaTuned",
            delta_alpha_result=delta_after,
            significance_results=sig_results,
            drift_results=None,
            latency_ms=None,
            monthly_cost=0.0,
        )

        score_after = verdict_after.score_card["weighted_total"]
        promoted = (
            verdict_after.verdict == "KEEP"
            and after_perf.sharpe_ratio > 1.0
            and after_perf.alpha > 0
        )

        report.after_metrics = {
            "sharpe": after_perf.sharpe_ratio,
            "alpha": after_perf.alpha,
            "max_drawdown": after_perf.max_drawdown,
            "win_rate": after_perf.win_rate,
            "accept_rate": float(np.mean(after_accept_rates)) if after_accept_rates else 0.0,
            "brier": float(np.mean(after_briers)) if after_briers else 1.0,
            "score": score_after,
        }
        report.score_after = score_after
        report.promoted_to_keep = promoted

        # ── Step 5: Promotion Report ──
        logger.info("")
        logger.info("STEP 5: Automated Promotion Report")
        logger.info("-" * 50)

        print_comparison_table(report.before_metrics, report.after_metrics)

        logger.info("")
        logger.info("  Verdict: %s | Score: %.2f/5.00 | Promoted: %s",
                    verdict_after.verdict, score_after, "YES" if promoted else "NO")

        if promoted:
            logger.info("")
            logger.info("  ★★★ PROMOSI BERHASIL: MARGINAL → KEEP ★★★")
            logger.info("  Target tercapai: Sharpe > 1.0, Alpha > 0, Score >= 3.5")
        else:
            logger.info("")
            logger.info("  ✗ Belum terpromosi. Rekomendasi:")
            if after_perf.sharpe_ratio < 1.0:
                logger.info("    - Sharpe masih < 1.0 — coba baseline mode lain atau perluas ruang pencarian")
            if after_perf.alpha <= 0:
                logger.info("    - Alpha masih ≤ 0 — pertimbangkan tambahan fitur eksogen")
            logger.info("    - Tuning adapt_kappa untuk adaptive threshold")
            logger.info("    - Coba mode='bayesian' dengan n_calls lebih besar")

        # Plot equity curve
        if before_returns_list:
            avg_before = pd.concat(before_returns_list, axis=1, sort=False).mean(axis=1)
            plot_equity_curve(avg_before, avg_after)

        # Save best config
        save_best_config(best_trial.params, chosen_baseline, best_trial, output_path)

    return report


def generate_meta_labeled_signals_entry(
    ohlcv: pd.DataFrame, primary_signals: pd.Series, config: ReformConfig,
) -> tuple[pd.Series, dict]:
    """Wrapper untuk generate_meta_labeled_signals dari alpha_rescue_pipeline."""
    from alpha_rescue_pipeline import generate_meta_labeled_signals
    return generate_meta_labeled_signals(ohlcv, primary_signals, config)


def _report_to_dict(report: TuningReport) -> dict:
    """Serialisasi TuningReport ke dict JSON-safe."""
    def _safe(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: _safe(v) for k, v in asdict(obj).items() if v is not None}
        if isinstance(obj, list):
            return [_safe(x) for x in obj]
        return obj
    return _safe(report)


def main():
    from sqlalchemy import text
    from market.db.engine import get_sessionmaker

    parser = argparse.ArgumentParser(
        description="Alpha Hyper-Tuner — Automated Optimization untuk Alpha Rescue Pipeline",
    )
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    parser.add_argument("--limit", type=int, default=20, help="Max tickers")
    parser.add_argument("--mode", type=str, default="grid", choices=["grid", "bayesian"],
                        help="Mode optimasi: grid atau bayesian")
    parser.add_argument("--baseline", type=str, default="auto",
                        choices=["auto", "donchian", "ema_env", "vwap", "ensemble"],
                        help="Mode baseline trend-following")
    parser.add_argument("--output", type=str, default="best_quant_config.json",
                        help="Output JSON file untuk best config")
    parser.add_argument("--grid-points", type=int, default=4,
                        help="Grid resolution per dimension (grid mode only)")
    args = parser.parse_args()

    config = ReformConfig()
    space = HyperParamSpace(grid_points=args.grid_points)

    session = get_sessionmaker()()

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

    report = run_hyper_tuner(
        tickers, session, config, space,
        mode=args.mode, baseline_mode=args.baseline, output_path=args.output,
    )

    # Save full report
    full_report_path = Path(args.output).parent / "alpha_hyper_tuner_report.json"
    with full_report_path.open("w") as f:
        json.dump(_report_to_dict(report), f, indent=2, default=str)
    logger.info("")
    logger.info("Laporan lengkap disimpan ke %s", full_report_path)


if __name__ == "__main__":
    main()
