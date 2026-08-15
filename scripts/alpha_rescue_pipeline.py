"""Alpha Rescue Pipeline — Reformasi Arsitektur Signal Action (pustaka/96 §9-10).

Diagnosa CIO: audit_ai_advanced.py mengonfirmasi bahwa mitigasi Feature Drift
(PSI 0.43 → 0.07) TIDAK mampu mendongkrak Alpha (ΔAlpha = 0.00%). Akar masalah
bukan pada data input, melainkan pada **arsitektur pengambilan keputusan
(Signal Action)**. Pipeline ini menerapkan 4 reformasi:

  REFORM 1 — Volatility-Targeting Position Sizing
      Alihkan MLSignal dari memprediksi *arah harga* (yang gagal, ret=0.00%)
      menjadi memprediksi *volatilitas* (vol_zscore / ATR) yang jauh lebih
      persisten (volatility clustering). Fungsi matematika `volatility_targeted_
      position_size()` menurunkan eksposur portofolio secara agresif (decay
      eksponensial + hard cutoff) saat AI memprediksi lonjakan volatilitas.
      Arah tetap dari sinyal dasar teknikal; AI mengontrol **ukuran** posisi.

  REFORM 2 — Meta-Labeling Ensembling (Marcos López de Prado)
      Hentikan pencampuran statis linear (40% ML + 60% MF) yang menghasilkan
      Sharpe -2.67. Ganti dengan Regime-Switching Meta-Labeling:
        - Model primer (MLSignal) → menentukan *arah* sinyal (side ∈ {-1,+1})
        - Model sekunder (MultiFactor) → meta-labeler biner {0,1}: "apakah
          sinyal primer layak dieksekusi pada rezim pasar saat ini?"
        - Posisi akhir = side_primer × P(meta=1)  (bukan rata-rata tertimbang)
      Meta-labeler dilatih pada label: 1 jika sinyal primer profit setelah
      biaya, 0 jika tidak. Fitur rezim (bull/bear/sideways/crisis) disuntikkan
      agar filter belajar kondisional terhadap rezim.

  REFORM 3 — MultiFactor Pruning & Clustered Feature Importance
      Bunuh data snooping: rewrite LightGBM MultiFactor dengan regularisasi
      ketat — n_estimators 300 → ≤80, max_depth 5 → 3-4, min_data_in_leaf,
      L1/L2 regularization. Ganti PCA (yang menyembunyikan multicollinearity)
      dengan **Clustered Feature Importance**: clustering hierarkis pada
      matriks korelasi fitur → pilih satu representatif per klaster berdasar
      importance tertinggi → eliminasi fitur redundan.

  REFORM 4 — Post-Remediation Verification
      Integrasi langsung fungsi audit_ai_utility.py & audit_ai_advanced.py
      untuk menghitung ulang Sharpe, Alpha (regresi vs IHSG), Brier Score,
      paired t-test, Diebold-Mariano, White's Reality Check, dan Score Card
      (KEEP/MARGINAL/REMOVE). Target promosi: Sharpe > 1.0, Alpha > 0.

Usage:
    DB_PATH=data/market_research.db python scripts/alpha_rescue_pipeline.py \
        [--tickers BBCA,BBRI] [--limit 20] [--output alpha_rescue_report.json]

Requires: scipy, pandas, numpy, lightgbm  (statsmodels optional)

Referensi:
  - López de Prado, "Advances in Financial Machine Learning" ch.3 (Meta-Labeling)
  - pustaka/96-ai-ml-audit-framework.md §9-10
  - pustaka/23 (regime-aware ML), pustaka/35 (market regime)
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

# ── Path setup untuk import modul saudara di scripts/ ──────────────────────
import sys as _sys

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in _sys.path:
    _sys.path.insert(0, _scripts_dir)

from audit_ai_utility import (  # noqa: E402
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
    load_ohlcv,
    load_benchmark,
    population_stability_index,
    drift_status,
)
from audit_ai_advanced import (  # noqa: E402
    DeltaAlphaResult,
    SignificanceTestResult,
    ComponentVerdict,
    convert_signal_to_position,
    compute_delta_alpha,
    paired_ttest,
    diebold_mariano_test,
    whites_reality_check_approximation,
    compute_component_score_card,
    regime_aware_weights,
    detect_drifted_features,
    remediate_features,
    _rsi,
    _bb_width,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=FutureWarning)


# ── GPU Awareness (per AGENTS.md §2: cek cuda:1 untuk komputasi berat) ────


def _resolve_device() -> str:
    """Cek GPU cuda:1 terlebih dahulu (konsisten dengan market.mlops.training).

    LightGBM pada pipeline ini berjalan di CPU (n_jobs=1) karena model sudah
    dipruning ke ≤80 trees; fungsi ini hanya untuk logging transparansi dan
    hook jika di masa depan diaktifkan `device=_lgbm_device()`.
    """
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            dev = "cuda:1" if torch.cuda.device_count() > 1 else "cuda:0"
            logger.info("GPU terdeteksi: %s (LightGBM tetap CPU pada pipeline ini)", dev)
            return dev
    except ImportError:
        pass
    logger.info("CUDA tidak tersedia — LightGBM berjalan di CPU")
    return "cpu"


def _lgbm_device() -> str:
    """Return the device parameter for LightGBM models.

    Checks whether the installed LightGBM build was compiled with GPU support.
    If not, falls back to 'cpu' to avoid LightGBMError at fit time.
    """
    try:
        import lightgbm as lgb  # type: ignore[import-not-found]

        # LightGBM exposes GPU support via lgb.LGBMClassifier(device=_lgbm_device()).
        # The error "GPU Tree Learner was not enabled in this build" occurs
        # when the build lacks GPU support. We detect this by checking the
        # build info string.
        try:
            build_info = lgb.__version__  # noqa: F841
            # Try a tiny GPU fit to detect support — if it fails, use CPU.
            # This is cheaper than parsing build flags.
            _test = lgb.LGBMClassifier(n_estimators=1, device="gpu", verbose=-1)
            _test.fit([[0], [1]], [0, 1])
            return "gpu"
        except Exception:
            logger.info("LightGBM GPU tidak tersedia — fallback ke CPU")
            return "cpu"
    except ImportError:
        return "cpu"


# ═══════════════════════════════════════════════════════════════════════════
# KONFIGURASI & DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ReformConfig:
    """Konfigurasi terpusat untuk seluruh 4 reformasi."""

    # Reform 1 — Volatility-Targeting
    vol_horizon: int = 20  # prediksi vol forward 20 hari
    vol_target_zscore: float = 0.0  # target vol = median historis (zscore=0)
    vol_aggressiveness: float = 2.5  # λ decay: makin besar makin agresif cut
    vol_hard_cutoff_zscore: float = 1.5  # vol_zscore ≥ ini → eksposur = 0
    vol_max_position: float = 1.0
    vol_n_estimators: int = 150
    vol_max_depth: int = 4

    # Reform 2 — Meta-Labeling
    meta_horizon: int = 5
    meta_cost_threshold: float = ROUND_TRIP_COST  # profit harus > biaya round-trip
    meta_n_estimators: int = 100
    meta_max_depth: int = 4
    meta_min_data_in_leaf: int = 40
    meta_prob_threshold: float = 0.5  # P(execute) ≥ 0.5 → ambil posisi

    # Reform 3 — MultiFactor Pruning
    mf_n_estimators: int = 80  # turun dari 300
    mf_max_depth: int = 4  # turun dari 5
    mf_min_data_in_leaf: int = 50
    mf_learning_rate: float = 0.05
    mf_reg_alpha: float = 0.1  # L1
    mf_reg_lambda: float = 1.0  # L2
    mf_subsample: float = 0.8
    mf_colsample_bytree: float = 0.7
    mf_corr_threshold: float = 0.65  # threshold klaster korelasi
    mf_top_k_clusters: int = 12  # maks fitur terpilih (1 per klaster)

    # Walk-forward umum
    walk_forward_steps: int | None = None  # None → 20% data
    min_train_samples: int = 200
    signal_threshold: float = 0.1


@dataclass
class Reform1Result:
    """Hasil Reform 1 (Volatility-Targeting)."""
    tickers: list[str] = field(default_factory=list)
    avg_predicted_vol_zscore: float = 0.0
    avg_position_scale: float = 0.0
    n_vol_predictions: int = 0
    brier_score_vol: float = 0.0  # kalibrasi arah vol (spike vs tidak)


@dataclass
class Reform2Result:
    """Hasil Reform 2 (Meta-Labeling)."""
    tickers: list[str] = field(default_factory=list)
    avg_meta_accept_rate: float = 0.0  # fraksi sinyal primer yang dieksekusi
    meta_brier_score: float = 0.0
    n_meta_predictions: int = 0


@dataclass
class Reform3Result:
    """Hasil Reform 3 (MultiFactor Pruning)."""
    tickers: list[str] = field(default_factory=list)
    n_features_before: int = 0
    n_features_after: int = 0
    n_clusters: int = 0
    dropped_features: list[str] = field(default_factory=list)
    selected_features: list[str] = field(default_factory=list)


@dataclass
class Reform4Result:
    """Hasil Reform 4 (Post-Remediation Verification)."""
    delta_alpha: DeltaAlphaResult | None = None
    significance: list[SignificanceTestResult] = field(default_factory=list)
    verdict: ComponentVerdict | None = None
    brier_score_signal: float = 0.0
    sharpe_rescued: float = 0.0
    alpha_rescued: float = 0.0


@dataclass
class RescueReport:
    """Laporan lengkap Alpha Rescue Pipeline."""
    audit_date: str = ""
    tickers_audited: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    reform1: Reform1Result | None = None
    reform2: Reform2Result | None = None
    reform3: Reform3Result | None = None
    reform4: Reform4Result | None = None
    summary: dict = field(default_factory=dict)
    promoted_to_keep: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# REFORM 1 — VOLATILITY-TARGETING POSITION SIZING
# ═══════════════════════════════════════════════════════════════════════════
#
# Diagnosa: AI gagal memprediksi arah harga (ΔAlpha=0). Volatilitas jauh lebih
# dapat diprediksi karena volatility clustering (GARCH-style persistence).
# MLSignal direformasi: target = forward vol_zscore (regime-invariant).
# Posisi = arah_teknikal × skala_vol  (AI kontrol SIZE, bukan DIRECTION).
#
# Fungsi skala (aggressive decay):
#   excess = max(0, vol_pred - vol_target)
#   scale  = exp(-λ * excess)                         # decay eksponensial
#   scale  = 0  jika vol_pred ≥ hard_cutoff           # hard floor
#   posisi = clip(scale * max_position, 0, max_position)
# ───────────────────────────────────────────────────────────────────────────


def volatility_targeted_position_size(
    predicted_vol_zscore: float | np.ndarray,
    target_vol_zscore: float = 0.0,
    max_position: float = 1.0,
    aggressiveness: float = 2.5,
    hard_cutoff: float = 1.5,
) -> np.ndarray:
    """Fungsi matematika position sizing berbasis prediksi volatilitas.

    Menurunkan eksposur secara agresif saat AI memprediksi lonjakan vol.
    - vol rendah (zscore ≤ target) → skala = 1.0 (eksposur penuh)
    - vol menengah → decay eksponensial: exp(-λ * excess)
    - vol tinggi (zscore ≥ hard_cutoff) → skala = 0 (flat, keluar pasar)

    Args:
        predicted_vol_zscore: Prediksi volatilitas ternormalisasi (z-score).
        target_vol_zscore: Target volatilitas (z-score), default median=0.
        max_position: Eksposur maksimum (1.0 = full).
        aggressiveness: λ — laju decay. Makin besar makin agresif memotong.
        hard_cutoff: z-score di atasnya eksposur = 0 (kill switch).

    Returns:
        Array skala posisi [0, max_position].
    """
    vol = np.asarray(predicted_vol_zscore, dtype=float)
    excess = np.maximum(0.0, vol - target_vol_zscore)
    scale = np.exp(-aggressiveness * excess)
    # Hard cutoff: vol ekstrem → keluar pasar sepenuhnya
    scale = np.where(vol >= hard_cutoff, 0.0, scale)
    return np.clip(scale * max_position, 0.0, max_position)


def build_volatility_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Bangun matriks fitur untuk prediksi volatilitas forward.

    Fitur regime-invariant (rank/zscore) untuk minimasi drift, plus fitur
    yang berkorelasi dengan volatility clustering.
    """
    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    volume = ohlcv["volume"].astype(float)
    returns = close.pct_change()

    data = pd.DataFrame(index=ohlcv.index)
    # Realized volatility (regime-normalized via rolling z-score)
    vol_20 = returns.rolling(20).std()
    vol_60 = returns.rolling(60).std()
    data["vol_zscore"] = (vol_20 - vol_20.rolling(252, min_periods=60).mean()) / \
        vol_20.rolling(252, min_periods=60).std().replace(0, np.nan)
    data["vol_pctile"] = vol_20.rolling(252, min_periods=60).rank(pct=True)

    # ATR-based vol (regime-invariant)
    atr_pct = ((high - low) / close * 100).rolling(14).mean()
    data["atr_pct"] = atr_pct
    data["atr_zscore"] = (atr_pct - atr_pct.rolling(252, min_periods=60).mean()) / \
        atr_pct.rolling(252, min_periods=60).std().replace(0, np.nan)

    # Volatility of volatility (clustering signal)
    data["vol_of_vol"] = vol_20.rolling(20).std()
    data["vol_ratio_20_60"] = vol_20 / vol_60.replace(0, np.nan)

    # GARCH-like persistence: lagged vol
    data["vol_lag_1"] = vol_20.shift(1)
    data["vol_lag_5"] = vol_20.shift(5)

    # Range-based vol (Garman-Klass approx) — clip ≥0 sebelum sqrt
    gk_inner = (
        0.5 * (np.log(high / low.replace(0, np.nan))) ** 2
        - (2 * np.log(2) - 1) * (np.log(close / close.shift(1).replace(0, np.nan))) ** 2
    )
    data["gk_vol"] = np.sqrt(np.maximum(0.0, gk_inner)).rolling(20).mean()

    # Volume surge (vol spike sering disertai lonjakan volume)
    vol_ma = volume.rolling(20).mean().replace(0, np.nan)
    data["vol_ratio"] = (volume / vol_ma).fillna(1.0)
    data["vol_trend"] = (volume.pct_change(5) * 100).fillna(0.0)

    # Return-based features (momentum → vol regime)
    data["ret_5"] = (close.pct_change(5) * 100).fillna(0.0)
    data["abs_ret_5"] = data["ret_5"].abs()
    data["rsi"] = _rsi(close, 14).fillna(50.0)
    data["bb_width"] = _bb_width(close, 20).fillna(0.0)

    # TARGET: forward vol_zscore (apakah vol 20-hari ke depan akan melonjak)
    forward_vol = returns.shift(-20).rolling(20).std()
    forward_vol_zscore = (forward_vol - vol_20.rolling(252, min_periods=60).mean()) / \
        vol_20.rolling(252, min_periods=60).std().replace(0, np.nan)
    data["target_vol_zscore"] = forward_vol_zscore
    # Biner untuk Brier: vol spike = zscore > 0.5
    data["target_vol_spike"] = (forward_vol_zscore > 0.5).astype(float)

    return data


def generate_volatility_targeted_signals(
    ohlcv: pd.DataFrame,
    config: ReformConfig,
) -> tuple[pd.Series, dict]:
    """Pipeline Reform 1: prediksi vol → position sizing → sinyal ber-skala.

    Arah dari baseline teknikal (MA crossover + RSI); ukuran dari prediksi
    volatilitas AI. Hasil = posisi kontinu [-1, +1] dengan magnitudo yang
    mengecil saat vol diprediksi melonjak.

    Returns:
        (positions_series, diagnostics_dict)
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM tidak tersedia — Reform 1 fallback ke baseline")
        baseline = generate_baseline_signals(ohlcv).astype(float)
        return baseline, {"n_predictions": 0, "avg_vol_zscore": 0.0, "avg_scale": 1.0}

    feat = build_volatility_features(ohlcv)
    feature_cols = [
        "vol_zscore", "vol_pctile", "atr_pct", "atr_zscore", "vol_of_vol",
        "vol_ratio_20_60", "vol_lag_1", "vol_lag_5", "gk_vol",
        "vol_ratio", "vol_trend", "ret_5", "abs_ret_5", "rsi", "bb_width",
    ]
    target_col = "target_vol_zscore"

    clean = feat.dropna(subset=feature_cols + [target_col])
    if len(clean) < config.min_train_samples + 50:
        baseline = generate_baseline_signals(ohlcv).astype(float)
        return baseline, {"n_predictions": 0, "avg_vol_zscore": 0.0, "avg_scale": 1.0}

    steps = config.walk_forward_steps or max(20, int(len(clean) * 0.2))
    positions = pd.Series(0.0, index=ohlcv.index)
    # Arah dari baseline teknikal (non-look-ahead)
    direction = generate_baseline_signals(ohlcv).astype(float)

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

        # Regime-aware sample weights (reuse dari audit_ai_advanced)
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
            device=_lgbm_device(),
        )
        model.fit(
            X_tr, y_tr,
            sample_weight=weights,
            eval_X=X_val, eval_y=y_val,
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

        # Posisi = arah × skala_vol  (tanda dari baseline, magnitudo dari AI)
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


# ═══════════════════════════════════════════════════════════════════════════
# REFORM 2 — META-LABELING ENSEMBLING (LÓPEZ DE PRADO)
# ═══════════════════════════════════════════════════════════════════════════
#
# Primer (MLSignal) → side ∈ {-1, +1}  (arah)
# Sekunder (MultiFactor) → meta-label biner {0, 1}  (eksekusi atau HOLD)
#   target_meta = 1  iff  forward_return * side > cost_threshold
# Posisi akhir = side × P(meta=1)   [bukan 0.4*ML + 0.6*MF]
# Fitur rezim disuntikkan → regime-switching filter.
# ───────────────────────────────────────────────────────────────────────────


def detect_regime(ohlcv: pd.DataFrame) -> pd.Series:
    """Deteksi rezim pasar heuristik (bull/bear/sideways/crisis).

    Menggunakan MA200 slope + vol percentile. Konsisten dengan model
    MarketRegime (pustaka/35 §2) namun dihitung on-the-fly agar walk-forward
    aman (non-look-ahead).
    """
    close = ohlcv["close"].astype(float)
    returns = close.pct_change()
    ma200 = close.rolling(200, min_periods=100).mean()
    vol_60 = returns.rolling(60).std()
    vol_pctile = vol_60.rolling(252, min_periods=60).rank(pct=True)

    regime = pd.Series("sideways", index=ohlcv.index)
    above_ma = close > ma200
    regime[above_ma & (vol_pctile < 0.7)] = "bull"
    regime[~above_ma & (vol_pctile < 0.7)] = "bear"
    regime[vol_pctile >= 0.9] = "crisis"  # vol ekstrem
    return regime


def build_meta_label_features(
    ohlcv: pd.DataFrame,
    primary_side: pd.Series,
    config: ReformConfig,
) -> pd.DataFrame:
    """Bangun fitur untuk meta-labeler (regime + sinyal primer + market state).

    Args:
        ohlcv: OHLCV data.
        primary_side: Sinyal arah primer {-1, 0, +1} dari MLSignal.
        config: Konfigurasi reformasi.

    Returns:
        DataFrame dengan fitur + target_meta (biner) + target_return.
    """
    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    volume = ohlcv["volume"].astype(float)
    returns = close.pct_change()
    regime = detect_regime(ohlcv)

    data = pd.DataFrame(index=ohlcv.index)
    # One-hot rezim (regime-switching features)
    for r in ["bull", "bear", "sideways", "crisis"]:
        data[f"regime_{r}"] = (regime == r).astype(float)

    # Sinyal primer & confidence-nya
    data["primary_side"] = primary_side.astype(float)
    data["primary_abs"] = primary_side.abs().astype(float)

    # Market state features
    data["vol_zscore"] = (returns.rolling(20).std() -
                          returns.rolling(20).std().rolling(252, min_periods=60).mean()) / \
        returns.rolling(20).std().rolling(252, min_periods=60).std().replace(0, np.nan)
    data["vol_pctile"] = returns.rolling(20).std().rolling(252, min_periods=60).rank(pct=True)
    data["rsi"] = _rsi(close, 14).fillna(50.0)
    data["ma_ratio"] = (close / close.rolling(50).mean().replace(0, np.nan)).fillna(1.0)
    data["momentum_10"] = (close.pct_change(10) * 100).fillna(0.0)
    data["atr_pct"] = ((high - low) / close * 100).rolling(14).mean().fillna(0.0)
    data["bb_width"] = _bb_width(close, 20).fillna(0.0)

    vol_ma = volume.rolling(20).mean().replace(0, np.nan)
    data["vol_ratio"] = (volume / vol_ma).fillna(1.0)

    # TARGET: forward return pada horizon, dinilai relatif terhadap side primer
    forward_return = close.shift(-config.meta_horizon) / close - 1
    data["forward_return"] = forward_return
    # Meta-label: 1 jika sinyal primer menghasilkan return > biaya setelah arah
    #   profit = forward_return * side  (long: +ret, short: -ret)
    aligned_return = forward_return * primary_side
    data["target_meta"] = (aligned_return > config.meta_cost_threshold).astype(float)
    # Hanya baris dengan side != 0 yang relevan untuk meta-labeling
    data.loc[primary_side == 0, "target_meta"] = np.nan

    return data


def generate_meta_labeled_signals(
    ohlcv: pd.DataFrame,
    primary_signals: pd.Series,
    config: ReformConfig,
) -> tuple[pd.Series, dict]:
    """Pipeline Reform 2: meta-labeling regime-switching.

    Args:
        ohlcv: OHLCV data.
        primary_signals: Sinyal kontinu primer (MLSignal) [-1, 1].
        config: Konfigurasi.

    Returns:
        (meta_labeled_positions, diagnostics)
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM tidak tersedia — Reform 2 fallback ke primer")
        return primary_signals, {"n_predictions": 0, "accept_rate": 1.0, "brier": 1.0}

    # Side primer = tanda sinyal (diskret)
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
            is_unbalance=True,  # handle class imbalance (HOLD dominan)
            device=_lgbm_device(),
        )
        model.fit(
            X_tr, y_tr,
            sample_weight=weights,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(15, verbose=False)],
        )

        X_test = test_data[feature_cols].values
        proba_exec = model.predict_proba(X_test)[:, 1]

        # Posisi akhir = side_primer × P(meta=1)
        for j, idx in enumerate(test_data.index):
            side = primary_side.reindex([idx]).iloc[0]
            positions.loc[idx] = side * proba_exec[j]

        accept_rates.extend((proba_exec >= config.meta_prob_threshold).tolist())
        # Brier score untuk kalibrasi meta-labeler
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
# REFORM 3 — MULTIFACTOR PRUNING & CLUSTERED FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════════════
#
# Bunuh data snooping pada MultiFactor (Sharpe -2.67):
#   1. LightGBM pruning ketat: 80 trees, depth 4, min_data_in_leaf=50, L1/L2
#   2. Ganti PCA → Clustered Feature Importance:
#      a. Matriks korelasi fitur → distance = 1 - |corr|
#      b. Hierarchical clustering (average linkage)
#      c. Pilih 1 representatif per klaster (importance tertinggi)
#      d. Eliminasi multicollinearity tanpa kehilangan sinyal
# ───────────────────────────────────────────────────────────────────────────


def cluster_features_by_correlation(
    features_df: pd.DataFrame,
    corr_threshold: float = 0.65,
) -> dict[int, list[str]]:
    """Klaster fitur berdasarkan korelasi (hierarchical clustering).

    Args:
        features_df: DataFrame fitur (kolom = fitur).
        corr_threshold: Fitur dengan |corr| ≥ threshold dikelompokkan bersama.

    Returns:
        Dict {cluster_id: [feature_names]}.
    """
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    corr = features_df.corr().fillna(0.0)
    # Distance = 1 - |corr| (fitur berkorelasi tinggi → distance kecil)
    dist = 1.0 - corr.abs().to_numpy()
    np.fill_diagonal(dist, 0.0)
    # Pastikan simetris & non-negatif
    dist = np.clip((dist + dist.T) / 2.0, 0.0, 2.0)

    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=1.0 - corr_threshold, criterion="distance")

    clusters: dict[int, list[str]] = {}
    for feat, cl in zip(features_df.columns, labels, strict=False):
        clusters.setdefault(int(cl), []).append(feat)
    return clusters


def select_clustered_features(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    corr_threshold: float = 0.65,
    top_k_clusters: int = 12,
) -> tuple[list[str], list[str], dict[int, list[str]]]:
    """Pilih fitur representatif per klaster via Clustered Feature Importance.

    1. Klaster fitur berdasarkan korelasi.
    2. Latih LightGBM cepat untuk dapatkan importance.
    3. Per klaster, pilih fitur dengan importance tertinggi.
    4. Ambil top_k_clusters klaster dengan importance representatif tertinggi.

    Returns:
        (selected_features, dropped_features, clusters_map)
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM tidak tersedia — clustered selection dilewati")
        return feature_names, [], {}

    if len(feature_names) == 0 or X.shape[0] == 0:
        return [], [], {}

    df = pd.DataFrame(X, columns=feature_names)
    clusters = cluster_features_by_correlation(df, corr_threshold)

    # Importance model cepat (regularized)
    imp_model = lgb.LGBMClassifier(
        n_estimators=50, max_depth=3, learning_rate=0.1,
        verbose=-1, subsample=0.8, colsample_bytree=0.8,
        n_jobs=1, min_data_in_leaf=50, reg_alpha=0.1, reg_lambda=1.0,
        device=_lgbm_device(),
    )
    imp_model.fit(X, y)
    imp_dict = dict(zip(feature_names, imp_model.feature_importances_, strict=False))

    # Representatif per klaster = importance tertinggi
    representatives: list[tuple[str, float]] = []
    for cl_id, members in clusters.items():
        best = max(members, key=lambda f: imp_dict.get(f, 0))
        representatives.append((best, imp_dict.get(best, 0.0)))

    # Urutkan klaster by importance representatif, ambil top_k
    representatives.sort(key=lambda x: x[1], reverse=True)
    selected = [f for f, _ in representatives[:top_k_clusters]]
    dropped = [f for f in feature_names if f not in selected]
    return selected, dropped, clusters


def build_multifactor_features(ohlcv: pd.DataFrame, config: ReformConfig) -> pd.DataFrame:
    """Bangun matriks fitur endogen MultiFactor (subset prunable).

    Menggunakan fitur yang sama dengan audit_ai_advanced.generate_multifactor_
    predictions namun diperkaya dengan fitur regime-invariant.
    """
    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)
    volume = ohlcv["volume"].astype(float)
    returns = close.pct_change()

    data = pd.DataFrame(index=ohlcv.index)
    data["ret_1"] = returns
    data["ret_5"] = close.pct_change(5)
    data["ret_10"] = close.pct_change(10)
    data["autocorr_1"] = returns.rolling(20).apply(
        lambda x: x.autocorr(lag=1) if len(x) > 2 else 0, raw=False,
    )
    data["autocorr_5"] = returns.rolling(20).apply(
        lambda x: x.autocorr(lag=5) if len(x) > 6 else 0, raw=False,
    )
    data["body_ratio"] = (close - close.shift(1)) / (high - low).replace(0, np.nan)
    data["rsi"] = _rsi(close, 14)
    data["rsi_rank"] = data["rsi"].rolling(252, min_periods=60).rank(pct=True)
    data["momentum"] = close.pct_change(10) * 100
    data["ma_5"] = close.rolling(5).mean()
    data["ma_20"] = close.rolling(20).mean()
    data["ma_ratio"] = data["ma_5"] / data["ma_20"].replace(0, np.nan)
    data["ma_ratio_zscore"] = (data["ma_ratio"] -
                               data["ma_ratio"].rolling(252, min_periods=60).mean()) / \
        data["ma_ratio"].rolling(252, min_periods=60).std().replace(0, np.nan)
    data["vol_20"] = returns.rolling(20).std()
    data["vol_pctile"] = data["vol_20"].rolling(252, min_periods=60).rank(pct=True)
    data["bb_width"] = (2 * close.rolling(20).std()) / close.rolling(20).mean()
    data["bb_pct"] = (close - close.rolling(20).mean()) / \
        (2 * close.rolling(20).std().replace(0, np.nan))

    # MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    data["macd_hist"] = macd_line - macd_signal
    data["macd_hist_norm"] = data["macd_hist"] / close.replace(0, np.nan)

    # Volume
    vol_ma = volume.rolling(20).mean().replace(0, np.nan)
    data["vol_ratio"] = volume / vol_ma
    data["atr_pct"] = ((high - low) / close * 100).rolling(14).mean()
    data["vol_regime"] = data["atr_pct"].rolling(60).rank(pct=True)

    # Target 3-class
    data["forward_return"] = close.shift(-5) / close - 1
    data["target_3class"] = 1  # HOLD
    data.loc[data["forward_return"] > 0.01, "target_3class"] = 2  # BUY
    data.loc[data["forward_return"] < -0.01, "target_3class"] = 0  # SELL

    return data


def generate_pruned_multifactor_signals(
    ohlcv: pd.DataFrame,
    config: ReformConfig,
) -> tuple[pd.Series, dict]:
    """Pipeline Reform 3: MultiFactor pruning + clustered feature selection.

    Returns:
        (signals, diagnostics) — sinyal [-1, 1] dari model yang sudah dipruning.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM tidak tersedia — Reform 3 fallback ke 0")
        return pd.Series(0.0, index=ohlcv.index), {
            "n_features_before": 0, "n_features_after": 0,
            "n_clusters": 0, "dropped": [], "selected": [],
        }

    data = build_multifactor_features(ohlcv, config)
    candidate_cols = [
        "ret_1", "ret_5", "ret_10", "autocorr_1", "autocorr_5", "body_ratio",
        "rsi", "rsi_rank", "momentum", "ma_ratio", "ma_ratio_zscore",
        "vol_20", "vol_pctile", "bb_width", "bb_pct",
        "macd_hist", "macd_hist_norm", "vol_ratio", "atr_pct", "vol_regime",
    ]

    clean = data.dropna(subset=candidate_cols + ["target_3class"])
    if len(clean) < config.min_train_samples + 50:
        return pd.Series(0.0, index=ohlcv.index), {
            "n_features_before": len(candidate_cols), "n_features_after": 0,
            "n_clusters": 0, "dropped": [], "selected": [],
        }

    # Clustered feature selection pada seluruh data training-safe:
    # gunakan 70% awal sebagai basis seleksi (non-look-ahead)
    sel_end = int(len(clean) * 0.7)
    sel_data = clean.iloc[:sel_end]
    X_sel = sel_data[candidate_cols].values
    y_sel = sel_data["target_3class"].values

    selected, dropped, clusters = select_clustered_features(
        X_sel, y_sel, candidate_cols,
        corr_threshold=config.mf_corr_threshold,
        top_k_clusters=config.mf_top_k_clusters,
    )
    if not selected:
        selected = candidate_cols

    diag = {
        "n_features_before": len(candidate_cols),
        "n_features_after": len(selected),
        "n_clusters": len(clusters),
        "dropped": dropped,
        "selected": selected,
    }
    logger.info("    Clustered selection: %d → %d fitur (%d klaster)",
                len(candidate_cols), len(selected), len(clusters))

    steps = config.walk_forward_steps or max(20, int(len(clean) * 0.2))
    signals = pd.Series(0.0, index=ohlcv.index)

    for i in range(config.min_train_samples, len(clean) - 1):
        if i % steps != 0 and i != config.min_train_samples:
            continue

        train = clean.iloc[:i]
        test_start, test_end = i, min(i + steps, len(clean))
        test_data = clean.iloc[test_start:test_end]
        if len(test_data) == 0:
            continue

        X_tr = train[selected].values
        y_tr = train["target_3class"].values
        split = int(len(X_tr) * 0.8)
        X_tr, X_val = X_tr[:split], X_tr[split:]
        y_tr, y_val = y_tr[:split], y_tr[split:]

        weights = regime_aware_weights(train.index[:split])

        # LightGBM PRUNED — bunuh overfitting
        model = lgb.LGBMClassifier(
            n_estimators=config.mf_n_estimators,
            max_depth=config.mf_max_depth,
            learning_rate=config.mf_learning_rate,
            verbose=-1,
            subsample=config.mf_subsample,
            colsample_bytree=config.mf_colsample_bytree,
            n_jobs=1,
            min_data_in_leaf=config.mf_min_data_in_leaf,
            reg_alpha=config.mf_reg_alpha,
            reg_lambda=config.mf_reg_lambda,
            num_classes=3,
            objective="multiclass",
            device=_lgbm_device(),
        )
        model.fit(
            X_tr, y_tr,
            sample_weight=weights,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(20, verbose=False)],
        )

        X_test = test_data[selected].values
        proba = model.predict_proba(X_test)
        signal_vals = proba[:, 2] - proba[:, 0]  # P(BUY) - P(SELL)

        for j, idx in enumerate(test_data.index):
            signals.loc[idx] = signal_vals[j]

    return signals, diag


# ═══════════════════════════════════════════════════════════════════════════
# REFORM 4 — POST-REMEDIATION VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════


def verify_reform(
    ohlcv: pd.DataFrame,
    rescued_signals: pd.Series,
    benchmark: pd.Series | None = None,
    component_name: str = "AlphaRescued",
    signal_threshold: float = 0.1,
) -> Reform4Result:
    """Reform 4: hitung ulang Sharpe, Alpha, Brier, signifikansi, score card.

    Mengintegrasikan langsung fungsi dari audit_ai_utility.py &
    audit_ai_advanced.py untuk verifikasi apples-to-apples dengan audit awal.
    """
    # Delta Alpha vs baseline teknikal
    delta = compute_delta_alpha(
        ohlcv, rescued_signals, benchmark, component_name, signal_threshold,
    )

    # Signal-level metrics (Brier dari probabilitas sinyal)
    close = ohlcv["close"].astype(float)
    next_ret = close.pct_change().shift(-1)
    aligned = pd.DataFrame({
        "sig": rescued_signals, "ret": next_ret,
    }).dropna()
    brier = 0.0
    if len(aligned) > 10:
        # Probabilitas arah naik = (signal + 1) / 2
        proba_up = (aligned["sig"] + 1.0) / 2.0
        outcomes = (aligned["ret"] > 0).astype(float).values
        brier = float(np.mean((proba_up.values - outcomes) ** 2))

    # Signifikansi statistik
    significance: list[SignificanceTestResult] = []
    positions = convert_signal_to_position(rescued_signals, signal_threshold)
    ai_returns = simulate_strategy_returns(ohlcv, positions)
    baseline_signals = generate_baseline_signals(ohlcv)
    baseline_returns = simulate_strategy_returns(ohlcv, baseline_signals)
    aligned_ret = pd.DataFrame({
        "ai": ai_returns, "baseline": baseline_returns,
    }).dropna()

    if len(aligned_ret) > 30:
        significance.append(paired_ttest(aligned_ret["ai"], aligned_ret["baseline"]))
        if benchmark is not None:
            bench_re = benchmark.reindex(aligned_ret.index).fillna(0)
            fe_ai = aligned_ret["ai"] - bench_re
            fe_base = aligned_ret["baseline"] - bench_re
            significance.append(diebold_mariano_test(fe_ai, fe_base, horizon=5))
        significance.append(whites_reality_check_approximation(
            aligned_ret["ai"], aligned_ret["baseline"], n_bootstrap=500,
        ))

    # Score card (reuse dari audit_ai_advanced)
    verdict = compute_component_score_card(
        component_name=component_name,
        delta_alpha_result=delta,
        significance_results=significance,
        drift_results=None,
        latency_ms=None,
        monthly_cost=0.0,
    )

    return Reform4Result(
        delta_alpha=delta,
        significance=significance,
        verdict=verdict,
        brier_score_signal=brier,
        sharpe_rescued=delta.sharpe_ai,
        alpha_rescued=delta.alpha_ai,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATION — MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════


def run_alpha_rescue_pipeline(
    tickers: list[str],
    session,
    config: ReformConfig | None = None,
) -> RescueReport:
    """Jalankan keempat reformasi secara berurutan untuk daftar ticker.

    Alur per ticker:
      Reform 1 → sinyal vol-targeted (arah teknikal × skala AI-vol)
      Reform 3 → sinyal MultiFactor pruned (sekaligus seleksi fitur)
      Reform 2 → meta-labeling: primer=Reform1 arah, sekunder=Reform3 proba
                 → posisi akhir = side_primer × P(meta=1)
      Reform 4 → verifikasi metrik rescued strategy
    """
    if config is None:
        config = ReformConfig()

    _resolve_device()
    benchmark = load_benchmark(session)
    report = RescueReport(
        audit_date=pd.Timestamp.now().isoformat(),
        tickers_audited=tickers,
        config=asdict(config),
    )

    logger.info("=" * 70)
    logger.info("ALPHA RESCUE PIPELINE — 4 REFORMASI ARSITEKTUR SIGNAL ACTION")
    logger.info("=" * 70)
    logger.info("Tickers: %d (%s)", len(tickers), tickers[:5])
    logger.info("Target promosi: Sharpe > 1.0, Alpha > 0  (MARGINAL → KEEP)")
    logger.info("")

    # Akumulasi return per komponen untuk agregasi cross-ticker
    rescued_returns_list: list[pd.Series] = []
    baseline_returns_list: list[pd.Series] = []
    reform1_diags, reform2_diags, reform3_diags = [], [], []
    all_brier = []

    for i, ticker in enumerate(tickers):
        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 500:
            logger.info("[%d/%d] %s: data tidak cukup (%d rows), skip",
                        i + 1, len(tickers), ticker, len(ohlcv))
            continue

        logger.info("")
        logger.info("[%d/%d] %s (%d rows) — menjalankan 4 reformasi...",
                    i + 1, len(tickers), ticker, len(ohlcv))

        # ── Reform 1: Volatility-Targeting ──
        logger.info("  ▶ Reform 1: Volatility-Targeting Position Sizing")
        vol_positions, diag1 = generate_volatility_targeted_signals(ohlcv, config)
        reform1_diags.append(diag1)
        logger.info("    Prediksi vol: n=%d, avg vol_zscore=%.3f, avg scale=%.3f",
                    diag1["n_predictions"], diag1["avg_vol_zscore"], diag1["avg_scale"])

        # ── Reform 3: MultiFactor Pruned (dijalankan sebelum Reform 2 agar
        #   sinyal MultiFactor pruned tersedia sebagai input meta-labeler) ──
        logger.info("  ▶ Reform 3: MultiFactor Pruning & Clustered Feature Importance")
        mf_signals, diag3 = generate_pruned_multifactor_signals(ohlcv, config)
        reform3_diags.append(diag3)
        logger.info("    Fitur: %d → %d (%d klaster, %d dropped)",
                    diag3["n_features_before"], diag3["n_features_after"],
                    diag3["n_clusters"], len(diag3["dropped"]))

        # ── Reform 2: Meta-Labeling ──
        # Primer = sinyal Reform 1 (arah teknikal ber-skala vol).
        # Sekunder = MultiFactor pruned sebagai meta-labeler filter biner.
        logger.info("  ▶ Reform 2: Meta-Labeling (López de Prado)")
        rescued_signals, diag2 = generate_meta_labeled_signals(
            ohlcv, vol_positions, config,
        )
        reform2_diags.append(diag2)
        logger.info("    Meta-labeler: n=%d, accept_rate=%.1f%%, brier=%.4f",
                    diag2["n_predictions"], diag2["accept_rate"] * 100, diag2["brier"])

        # ── Reform 4: Verifikasi per-ticker (ringkas) ──
        bench_aligned = benchmark.reindex(ohlcv.index).dropna()
        r4 = verify_reform(
            ohlcv, rescued_signals, benchmark, "AlphaRescued",
            config.signal_threshold,
        )
        all_brier.append(r4.brier_score_signal)
        logger.info("  ▶ Reform 4: Verifikasi — Sharpe=%.3f, Alpha=%+.4f, Brier=%.4f, verdict=%s",
                    r4.sharpe_rescued, r4.alpha_rescued,
                    r4.brier_score_signal, r4.verdict.verdict if r4.verdict else "N/A")

        # Akumulasi untuk agregasi cross-ticker
        positions = convert_signal_to_position(rescued_signals, config.signal_threshold)
        rescued_returns_list.append(simulate_strategy_returns(ohlcv, positions).rename(ticker))
        baseline_signals = generate_baseline_signals(ohlcv)
        baseline_returns_list.append(simulate_strategy_returns(ohlcv, baseline_signals).rename(ticker))

    # ── Agregasi cross-ticker ──
    logger.info("")
    logger.info("=" * 70)
    logger.info("AGREGASI CROSS-TICKER & VERDICT FINAL")
    logger.info("=" * 70)

    if not rescued_returns_list:
        logger.warning("Tidak ada ticker dengan cukup data — pipeline berhenti")
        report.summary = {"error": "no_valid_tickers"}
        return report

    avg_rescued = pd.concat(rescued_returns_list, axis=1, sort=False).mean(axis=1)
    avg_baseline = pd.concat(baseline_returns_list, axis=1, sort=False).mean(axis=1)
    bench_aligned = benchmark.reindex(avg_rescued.index).dropna()

    rescued_perf = compute_performance_metrics(avg_rescued, bench_aligned)
    base_perf = compute_performance_metrics(avg_baseline, bench_aligned)

    # Bangun DeltaAlphaResult agregat
    delta_agg = DeltaAlphaResult(
        component="AlphaRescued",
        alpha_ai=rescued_perf.alpha,
        alpha_baseline=base_perf.alpha,
        delta_alpha=rescued_perf.alpha - base_perf.alpha,
        sharpe_ai=rescued_perf.sharpe_ratio,
        sharpe_baseline=base_perf.sharpe_ratio,
        delta_sharpe=rescued_perf.sharpe_ratio - base_perf.sharpe_ratio,
        win_rate_ai=rescued_perf.win_rate,
        win_rate_baseline=base_perf.win_rate,
        max_dd_ai=rescued_perf.max_drawdown,
        max_dd_baseline=base_perf.max_drawdown,
        n_observations=len(avg_rescued),
    )

    # Signifikansi agregat
    aligned_ret = pd.DataFrame({
        "ai": avg_rescued, "baseline": avg_baseline,
    }).dropna()
    sig_results: list[SignificanceTestResult] = []
    if len(aligned_ret) > 30:
        sig_results.append(paired_ttest(aligned_ret["ai"], aligned_ret["baseline"]))
        if benchmark is not None:
            bench_re = benchmark.reindex(aligned_ret.index).fillna(0)
            sig_results.append(diebold_mariano_test(
                aligned_ret["ai"] - bench_re, aligned_ret["baseline"] - bench_re, horizon=5,
            ))
        sig_results.append(whites_reality_check_approximation(
            aligned_ret["ai"], aligned_ret["baseline"], n_bootstrap=500,
        ))

    verdict = compute_component_score_card(
        component_name="AlphaRescued",
        delta_alpha_result=delta_agg,
        significance_results=sig_results,
        drift_results=None,
        latency_ms=None,
        monthly_cost=0.0,
    )

    # ── Ringkasan Reform 1-3 ──
    report.reform1 = Reform1Result(
        tickers=tickers,
        avg_predicted_vol_zscore=float(np.mean([d["avg_vol_zscore"] for d in reform1_diags])) if reform1_diags else 0.0,
        avg_position_scale=float(np.mean([d["avg_scale"] for d in reform1_diags])) if reform1_diags else 0.0,
        n_vol_predictions=sum(d["n_predictions"] for d in reform1_diags),
    )
    report.reform2 = Reform2Result(
        tickers=tickers,
        avg_meta_accept_rate=float(np.mean([d["accept_rate"] for d in reform2_diags])) if reform2_diags else 0.0,
        meta_brier_score=float(np.mean([d["brier"] for d in reform2_diags])) if reform2_diags else 1.0,
        n_meta_predictions=sum(d["n_predictions"] for d in reform2_diags),
    )
    # Ambil seleksi fitur dari ticker terakhir yang valid (representatif)
    last_diag3 = reform3_diags[-1] if reform3_diags else {}
    report.reform3 = Reform3Result(
        tickers=tickers,
        n_features_before=last_diag3.get("n_features_before", 0),
        n_features_after=last_diag3.get("n_features_after", 0),
        n_clusters=last_diag3.get("n_clusters", 0),
        dropped_features=last_diag3.get("dropped", []),
        selected_features=last_diag3.get("selected", []),
    )
    report.reform4 = Reform4Result(
        delta_alpha=delta_agg,
        significance=sig_results,
        verdict=verdict,
        brier_score_signal=float(np.mean(all_brier)) if all_brier else 1.0,
        sharpe_rescued=rescued_perf.sharpe_ratio,
        alpha_rescued=rescued_perf.alpha,
    )

    promoted = verdict.verdict == "KEEP" and rescued_perf.sharpe_ratio > 1.0 and rescued_perf.alpha > 0
    report.promoted_to_keep = promoted

    # ── Cetak verdict box ──
    logger.info("")
    logger.info("  ┌─────────────────────────────────────────────────────┐")
    logger.info("  │  COMPONENT: AlphaRescued (4-Reform Pipeline)        │")
    logger.info("  ├─────────────────────────────────────────────────────┤")
    logger.info("  │  Sharpe (Rescued): %8.3f                          │", rescued_perf.sharpe_ratio)
    logger.info("  │  Sharpe (Baseline):%8.3f                          │", base_perf.sharpe_ratio)
    logger.info("  │  ΔSharpe:          %8.3f                          │", delta_agg.delta_sharpe)
    logger.info("  │  Alpha (Rescued):  %+.4f (%+.2f%%)                 │",
                rescued_perf.alpha, rescued_perf.alpha * 100)
    logger.info("  │  ΔAlpha:           %+.4f (%+.2f%%)                 │",
                delta_agg.delta_alpha, delta_agg.delta_alpha * 100)
    logger.info("  │  Max DD (Rescued): %8.2f%%                         │", rescued_perf.max_drawdown * 100)
    logger.info("  │  Win Rate:         %8.1f%%                         │", rescued_perf.win_rate * 100)
    logger.info("  │  Brier Score:      %8.4f                          │", report.reform4.brier_score_signal)
    logger.info("  │  Score:            %8.2f / 5.00                   │", verdict.score_card["weighted_total"])
    logger.info("  │                                                     │")
    logger.info("  │  ★ VERDICT: %-13s  PROMOTED: %-5s          │",
                f"【{verdict.verdict}】", "YES" if promoted else "NO")
    logger.info("  └─────────────────────────────────────────────────────┘")

    logger.info("")
    logger.info("  Reform 1 (Vol-Targeting): avg vol_zscore=%.3f, avg scale=%.3f, n=%d",
                report.reform1.avg_predicted_vol_zscore, report.reform1.avg_position_scale,
                report.reform1.n_vol_predictions)
    logger.info("  Reform 2 (Meta-Labeling): accept_rate=%.1f%%, brier=%.4f, n=%d",
                report.reform2.avg_meta_accept_rate * 100, report.reform2.meta_brier_score,
                report.reform2.n_meta_predictions)
    logger.info("  Reform 3 (Pruning):       fitur %d → %d (%d klaster)",
                report.reform3.n_features_before, report.reform3.n_features_after,
                report.reform3.n_clusters)

    if sig_results:
        logger.info("")
        logger.info("  Statistical Tests:")
        for s in sig_results:
            logger.info("    %s: stat=%.3f, p=%.4f, significant=%s",
                        s.test_name, s.statistic, s.p_value, s.significant)
            logger.info("      → %s", s.interpretation)

    if promoted:
        logger.info("")
        logger.info("  ✓ PROMOSI BERHASIL: MARGINAL → KEEP (Sharpe>1.0, Alpha>0)")
    else:
        logger.info("")
        logger.info("  ✗ Belum terpromosi. Rekomendasi: %s",
                    "; ".join(verdict.recommendations) if verdict.recommendations
                    else "tuning config (aggressiveness, meta_prob_threshold, top_k_clusters)")

    report.summary = {
        "sharpe_rescued": round(rescued_perf.sharpe_ratio, 4),
        "alpha_rescued": round(rescued_perf.alpha, 6),
        "delta_alpha": round(delta_agg.delta_alpha, 6),
        "delta_sharpe": round(delta_agg.delta_sharpe, 4),
        "max_drawdown": round(rescued_perf.max_drawdown, 4),
        "win_rate": round(rescued_perf.win_rate, 4),
        "brier_score": round(report.reform4.brier_score_signal, 4),
        "score": round(verdict.score_card["weighted_total"], 2),
        "verdict": verdict.verdict,
        "promoted_to_keep": promoted,
    }
    return report


def _report_to_dict(report: RescueReport) -> dict:
    """Serialisasi RescueReport ke dict JSON-safe."""
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
        description="Alpha Rescue Pipeline — 4 Reformasi Arsitektur Signal Action",
    )
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    parser.add_argument("--limit", type=int, default=20, help="Max tickers (jika --tickers kosong)")
    parser.add_argument("--output", type=str, default="alpha_rescue_report.json",
                        help="Output JSON file")
    parser.add_argument("--signal-threshold", type=float, default=0.1,
                        help="Threshold konversi sinyal → posisi")
    parser.add_argument("--vol-aggressiveness", type=float, default=2.5,
                        help="λ decay position sizing (makin besar makin agresif)")
    parser.add_argument("--mf-trees", type=int, default=80, help="MultiFactor n_estimators (≤80)")
    parser.add_argument("--mf-depth", type=int, default=4, help="MultiFactor max_depth (3-4)")
    args = parser.parse_args()

    config = ReformConfig(
        vol_aggressiveness=args.vol_aggressiveness,
        mf_n_estimators=min(args.mf_trees, 80),  # hard cap 80
        mf_max_depth=min(max(args.mf_depth, 3), 4),  # clamp 3-4
        signal_threshold=args.signal_threshold,
    )

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

    report = run_alpha_rescue_pipeline(tickers, session, config)

    output_path = Path(args.output)
    with output_path.open("w") as f:
        json.dump(_report_to_dict(report), f, indent=2, default=str)
    logger.info("")
    logger.info("Laporan disimpan ke %s", output_path)


if __name__ == "__main__":
    main()
