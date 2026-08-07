"""Feature Drift Isolation & Regime-Aware Remediation Pipeline.

Tugas 1 dari Langkah Eksekusi Mandiri (pustaka/96 §5).

Mengapa momentum/volatilitas/volume drift saat regime shift?
------------------------------------------------------------
Fitur berbasis momentum (RSI, MACD, momentum_5/10), volatilitas (ATR%, BB width),
dan volume (vol_ratio, vol_trend) bersifat **regime-dependent**:

1. **RSI/MACD** di pasar trending menghasilkan distribusi nilai yang terpusat
   di ekstrim (>70 atau <30 untuk RSI; histogram besar untuk MACD).
   Saat pasar berubah ke sideways, RSI berfluktuasi di sekitar 40-60 dan
   MACD histogram mengecil → distribusi bergeser drastis → PSI tinggi.

2. **Volatilitas (ATR%, BB width)** naik tajam saat crisis/bear market
   dan turun saat sideways low-vol. Distribusi nilai berubah dari
   right-skewed ke left-skewed → PSI > 0.25.

3. **Volume features** bergantung pada partisipasi pasar. Saat regime
   berubah dari bull (volume tinggi) ke sideways (volume rendah),
   vol_ratio dan vol_trend berubah mean dan variance-nya → drift.

Solusi: **Regime-Aware Exponential Weighting**
----------------------------------------------
Daripada memberi bobot sama ke semua data historis, kita berikan
bobot eksponensial yang lebih tinggi pada data terbaru:

    w(t) = exp(-λ * (T - t))

di mana λ = decay rate, T = tanggal terakhir, t = tanggal observasi.
Ini membuat model ML cepat beradaptasi: data 30 hari lalu dapat
bobot ~exp(-λ*30) yang jauh lebih kecil dari data kemarin.

Pipeline:
  1. Load features dari DB (TechnicalIndicator + computed dari OHLCV)
  2. Hitung PSI per feature (reference window vs current window)
  3. Isolasi fitur dengan PSI > 0.25 (drifted)
  4. Deteksi regime pasar (MarketRegime table atau heuristic)
  5. Apply exponential decay weighting (λ configurable)
  6. Output: weighted feature matrix + drift report

Usage:
    DB_PATH=data/market_research.db python scripts/feature_drift_remediation.py \
        [--tickers BBCA,BBRI,TLKM] [--lambda 0.02] [--ref-end 2025-06-30] \
        [--cur-start 2025-07-01] [--output drift_remediation_report.json]

Cross-ref: pustaka/96 §5 (Feature Drift), pustaka/23 §5 (Regime-Aware ML),
           pustaka/51 §5 (Drift Detection), src/market/mlops/drift.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select, text

from market.db.engine import get_sessionmaker
from market.db.models import OHLCV, TechnicalIndicator, MarketRegime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Konstanta ──────────────────────────────────────────────────────────────

PSI_THRESHOLD = 0.25
PSI_MODERATE = 0.10
DEFAULT_LAMBDA = 0.02  # Decay rate: ~50% weight di ~35 hari (~1.5 bulan)
TRADING_DAYS = 252


# ── Data Structures ────────────────────────────────────────────────────────


@dataclass
class FeatureDriftResult:
    """Hasil audit drift untuk satu fitur."""

    feature: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    status: str  # stable, moderate, drifted
    ref_mean: float
    cur_mean: float
    ref_std: float
    cur_std: float
    regime_ref: str
    regime_cur: str


@dataclass
class RemediationReport:
    """Laporan lengkap remediasi drift."""

    audit_date: str = ""
    tickers_audited: list[str] = field(default_factory=list)
    total_features: int = 0
    drifted_features: list[FeatureDriftResult] = field(default_factory=list)
    moderate_features: list[FeatureDriftResult] = field(default_factory=list)
    stable_features: list[FeatureDriftResult] = field(default_factory=list)
    lambda_decay: float = DEFAULT_LAMBDA
    regime_distribution: dict[str, int] = field(default_factory=dict)
    weighted_feature_summary: dict = field(default_factory=dict)


# ── 1. PSI Computation ────────────────────────────────────────────────────


def population_stability_index(
    reference: np.ndarray,
    current: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Hitung Population Stability Index (PSI).

    PSI < 0.1:  stable (tidak ada drift)
    PSI 0.1-0.25: moderate drift (monitor)
    PSI > 0.25: significant drift (RETRAIN)

    Menggunakan quantile bins dari reference distribution agar
    robust terhadap outlier dan skewness.
    """
    # Gunakan quantile bins dari reference untuk konsistensi
    bins = np.linspace(
        min(reference.min(), current.min()),
        max(reference.max(), current.max()),
        n_bins + 1,
    )

    ref_hist, _ = np.histogram(reference, bins=bins)
    cur_hist, _ = np.histogram(current, bins=bins)

    # Normalisasi ke proporsi dengan smoothing epsilon
    ref_prop = ref_hist / len(reference) + 1e-6
    cur_prop = cur_hist / len(current) + 1e-6

    psi = np.sum((cur_prop - ref_prop) * np.log(cur_prop / ref_prop))
    return float(psi)


def classify_drift(psi: float) -> str:
    """Klasifikasi status drift dari nilai PSI."""
    if psi < PSI_MODERATE:
        return "stable"
    elif psi < PSI_THRESHOLD:
        return "moderate"
    else:
        return "drifted"


# ── 2. Feature Extraction dari Database ────────────────────────────────────


def load_technical_indicators(
    session,
    ticker: str,
    timeframe: str = "1d",
) -> pd.DataFrame:
    """Load technical indicators dari DB, pivot ke wide format.

    TechnicalIndicator table menyimpan data dalam format long:
        ticker | date | indicator | value | timeframe | source

    Di-pivot ke wide format:
        date | rsi | macd_hist | atr_pct | ...

    Indikator yang di-load: rsi, macd_hist, atr_pct, bollinger_width,
    volume_ratio, momentum_5, momentum_10, obv, vwap_ratio
    """
    rows = session.execute(
        select(TechnicalIndicator)
        .where(
            TechnicalIndicator.ticker == ticker,
            TechnicalIndicator.timeframe == timeframe,
        )
        .order_by(TechnicalIndicator.date)
    ).scalars().all()

    if not rows:
        return pd.DataFrame()

    records = [
        {
            "date": r.date,
            "indicator": r.indicator,
            "value": float(r.value),
        }
        for r in rows
    ]
    df = pd.DataFrame(records)
    df = df.pivot_table(index="date", columns="indicator", values="value")
    df.index = pd.DatetimeIndex(df.index)
    return df


def compute_features_from_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Hitung fitur endogenous dari OHLCV jika TechnicalIndicator kosong.

    Menggunakan logika yang sama dengan MLSignalProvider._prepare_features
    dan MultiFactorFeaturePipeline.compute_endogenous_features.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    features = pd.DataFrame(index=df.index)

    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    features["rsi"] = (100 - (100 / (1 + rs))).fillna(50.0)

    # MACD histogram normalized
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    features["macd_hist_norm"] = (
        (macd_line - macd_signal) / close.replace(0, np.nan)
    ).fillna(0.0)

    # Momentum
    features["momentum_5"] = (close.pct_change(5) * 100).fillna(0.0)
    features["momentum_10"] = (close.pct_change(10) * 100).fillna(0.0)

    # Volatility
    features["atr_pct"] = (
        ((high - low) / close * 100).rolling(14).mean().fillna(0.0)
    )
    features["hl_range_pct"] = ((high - low) / close * 100).fillna(0.0)

    # Bollinger width
    ma20 = close.rolling(20).mean()
    sd20 = close.rolling(20).std()
    features["bb_width"] = ((2 * sd20) / ma20.replace(0, np.nan)).fillna(0.0)

    # Volume features
    vol_ma = volume.rolling(20).mean().replace(0, np.nan)
    features["vol_ratio"] = (volume / vol_ma).fillna(1.0)
    features["vol_trend"] = (volume.pct_change(5) * 100).fillna(0.0)

    # VWAP ratio
    vol_price = close * volume
    vol_sum = volume.rolling(20, min_periods=1).sum().replace(0, np.nan)
    vp_sum = vol_price.rolling(20, min_periods=1).sum()
    vwap = (vp_sum / vol_sum).fillna(close)
    features["vwap_ratio"] = (close / vwap.replace(0, np.nan)).fillna(1.0)

    # MA ratio
    ma5 = close.rolling(5).mean()
    features["ma_ratio"] = (ma5 / ma20.replace(0, np.nan)).fillna(1.0)

    # Volatility regime (percentile rank)
    features["vol_regime"] = (
        features["atr_pct"].rolling(60).rank(pct=True).fillna(0.5)
    )

    return features


def load_ohlcv(session, ticker: str, timeframe: str = "1d") -> pd.DataFrame:
    """Load OHLCV dari database."""
    rows = session.execute(
        select(OHLCV)
        .where(OHLCV.ticker == ticker, OHLCV.timeframe == timeframe)
        .order_by(OHLCV.timestamp)
    ).scalars().all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        [
            {
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": int(r.volume) if r.volume else 0,
            }
            for r in rows
        ],
        index=pd.DatetimeIndex([r.timestamp for r in rows]),
    )
    df = df[~df.index.duplicated(keep="last")]
    return df


def load_features(
    session,
    ticker: str,
    timeframe: str = "1d",
) -> pd.DataFrame:
    """Load features: prioritaskan TechnicalIndicator table, fallback ke computed.

    Jika TechnicalIndicator table memiliki data untuk ticker ini,
    gunakan itu. Jika tidak, hitung dari OHLCV.
    """
    ti_df = load_technical_indicators(session, ticker, timeframe)
    if not ti_df.empty and len(ti_df) > 50:
        logger.debug("%s: loaded %d rows from technical_indicators", ticker, len(ti_df))
        return ti_df

    ohlcv = load_ohlcv(session, ticker, timeframe)
    if ohlcv.empty:
        logger.warning("%s: no OHLCV data", ticker)
        return pd.DataFrame()

    features = compute_features_from_ohlcv(ohlcv)
    logger.debug("%s: computed %d features from OHLCV (%d rows)", ticker, features.shape[1], len(features))
    return features


# ── 3. Regime Detection ────────────────────────────────────────────────────


def load_market_regimes(session) -> pd.DataFrame:
    """Load market regime labels dari DB (MarketRegime table).

    Jika table kosong, gunakan heuristic regime detection dari ^JKSE.
    """
    rows = session.execute(
        select(MarketRegime).order_by(MarketRegime.date)
    ).scalars().all()

    if rows:
        df = pd.DataFrame(
            [
                {
                    "date": r.date,
                    "regime": r.regime,
                    "vix_level": r.vix_level,
                    "fear_greed_label": r.fear_greed_label,
                }
                for r in rows
            ]
        )
        df["date"] = pd.DatetimeIndex(df["date"])
        return df.set_index("date")

    # Fallback: heuristic regime detection dari ^JKSE
    logger.info("MarketRegime table kosong — menggunakan heuristic dari ^JKSE")
    ihsg = load_ohlcv(session, "^JKSE")
    if ihsg.empty:
        return pd.DataFrame()

    close = ihsg["close"].astype(float)
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    vol_20 = close.pct_change().rolling(20).std() * np.sqrt(TRADING_DAYS)

    regime = pd.Series("sideways", index=ihsg.index)
    regime[(sma50 > sma200) & (vol_20 < 0.25)] = "bull"
    regime[(sma50 < sma200) & (vol_20 < 0.30)] = "bear"
    regime[vol_20 >= 0.30] = "crisis"

    return pd.DataFrame({"regime": regime}, index=ihsg.index)


def get_regime_at(regimes: pd.DataFrame, target_date: pd.Timestamp) -> str:
    """Ambil regime pada tanggal terdekat <= target_date."""
    if regimes.empty:
        return "unknown"
    mask = regimes.index <= target_date
    if not mask.any():
        return "unknown"
    return str(regimes.loc[mask].iloc[-1].get("regime", "unknown"))


# ── 4. Drift Audit per Feature ─────────────────────────────────────────────


def audit_feature_drift(
    features: pd.DataFrame,
    ref_end_date: str,
    cur_start_date: str,
    regimes: pd.DataFrame | None = None,
) -> list[FeatureDriftResult]:
    """Audit drift untuk semua kolom fitur.

    Membagi data menjadi:
    - Reference window: dari awal hingga ref_end_date
    - Current window: dari cur_start_date hingga akhir

    Untuk setiap fitur, hitung PSI dan KS test.
    Bandingkan statistik deskriptif dan regime antara window.
    """
    ref_end = pd.Timestamp(ref_end_date)
    cur_start = pd.Timestamp(cur_start_date)

    reference = features.loc[:ref_end]
    current = features.loc[cur_start:]

    if reference.empty or current.empty:
        logger.warning(
            "Empty window: ref=%d rows, cur=%d rows",
            len(reference), len(current),
        )
        return []

    # Regime pada masing-masing window
    regime_ref = "unknown"
    regime_cur = "unknown"
    if regimes is not None and not regimes.empty:
        regime_ref = get_regime_at(regimes, ref_end)
        regime_cur = get_regime_at(regimes, features.index[-1])

    results = []
    for col in features.columns:
        ref_data = reference[col].dropna().values
        cur_data = current[col].dropna().values

        if len(ref_data) < 20 or len(cur_data) < 20:
            continue

        psi = population_stability_index(ref_data, cur_data)
        ks_stat, ks_p = stats.ks_2samp(ref_data, cur_data)

        results.append(FeatureDriftResult(
            feature=col,
            psi=psi,
            ks_statistic=float(ks_stat),
            ks_pvalue=float(ks_p),
            status=classify_drift(psi),
            ref_mean=float(np.mean(ref_data)),
            cur_mean=float(np.mean(cur_data)),
            ref_std=float(np.std(ref_data)),
            cur_std=float(np.std(cur_data)),
            regime_ref=regime_ref,
            regime_cur=regime_cur,
        ))

    return results


# ── 5. Regime-Aware Exponential Weighting ──────────────────────────────────


def compute_exponential_weights(
    dates: pd.DatetimeIndex,
    lambda_decay: float = DEFAULT_LAMBDA,
) -> np.ndarray:
    """Hitung bobot eksponensial decay untuk setiap tanggal.

    w(t) = exp(-λ * (T - t))

    di mana:
    - λ (lambda_decay): decay rate per hari
    - T: tanggal terbaru dalam data
    - t: tanggal observasi

    Interpretasi λ:
    - λ=0.01: half-life ~69 hari (~3.5 bulan) — adaptasi lambat
    - λ=0.02: half-life ~35 hari (~1.5 bulan) — adaptasi sedang (DEFAULT)
    - λ=0.05: half-life ~14 hari (~3 minggu) — adaptasi cepat
    - λ=0.10: half-life ~7 hari (~1.5 minggu) — sangat agresif

    Bobot dinormalisasi sehingga sum = 1 untuk digunakan sebagai
    sample weights di LightGBM.
    """
    if len(dates) == 0:
        return np.array([])

    # T = tanggal terbaru
    T = dates.max()

    # Hitung selisih hari (T - t) untuk setiap observasi
    # Konversi ke numpy array agar operasi np.exp dan .sum() konsisten
    days_diff = np.array((T - dates).days, dtype=float)

    # Bobot eksponensial: w(t) = exp(-λ * Δt)
    weights = np.exp(-lambda_decay * days_diff)

    # Normalisasi: sum(weights) = 1
    weights = weights / weights.sum()

    return weights


def apply_regime_aware_weighting(
    features: pd.DataFrame,
    lambda_decay: float = DEFAULT_LAMBDA,
    regimes: pd.DataFrame | None = None,
    regime_boost: float = 1.5,
) -> pd.DataFrame:
    """Apply Regime-Aware Exponential Weighting ke feature matrix.

    Menggabungkan dua sumber bobot:
    1. **Exponential decay**: bobot lebih besar untuk data terbaru
    2. **Regime boost**: bobot tambahan untuk data dengan regime
       yang sama dengan regime terkini

    Formula gabungan:
        w_final(t) = w_exp(t) * (regime_boost if regime(t) == regime(T) else 1.0)

    Ini memastikan model:
    - Cepat beradaptasi dengan kondisi terbaru (exponential decay)
    - Lebih memperhatikan data dari regime yang sama dengan saat ini
      (regime boost)

    Args:
        features: DataFrame fitur dengan DatetimeIndex.
        lambda_decay: Decay rate λ untuk exponential weighting.
        regimes: DataFrame regime dari load_market_regimes().
        regime_boost: Multiplier untuk data dengan regime yang sama.

    Returns:
        DataFrame dengan kolom tambahan 'sample_weight' yang berisi
        bobot ternormalisasi untuk setiap baris.
    """
    result = features.copy()

    # Step 1: Exponential decay weights
    weights = compute_exponential_weights(result.index, lambda_decay)

    # Step 2: Regime boost (jika data regime tersedia)
    if regimes is not None and not regimes.empty:
        current_regime = get_regime_at(regimes, result.index[-1])

        # Align regime ke feature index
        regime_aligned = regimes.reindex(result.index, method="ffill")
        regime_series = regime_aligned["regime"].fillna("unknown")

        # Boost: kalikan bobot dengan regime_boost jika regime sama
        boost_mask = (regime_series == current_regime).values
        weights = weights * np.where(boost_mask, regime_boost, 1.0)

        logger.info(
            "Regime-aware weighting: current_regime=%s, boosted=%d/%d rows",
            current_regime, boost_mask.sum(), len(boost_mask),
        )

    # Normalisasi ulang setelah regime boost
    weights = weights / weights.sum()

    result["sample_weight"] = weights
    return result


def get_remediation_actions(
    drift_results: list[FeatureDriftResult],
) -> dict[str, list[str]]:
    """Generate rekomendasi perbaikan per fitur berdasarkan status drift.

    Untuk fitur drifted (PSI > 0.25):
    - Tandai untuk retraining dengan exponential weighting
    - Pertimbangkan transformasi (rank, quantile, winsorize)
    - Atau ganti dengan fitur alternatif yang lebih stabil

    Untuk fitur moderate (0.1 < PSI < 0.25):
    - Monitor, siapkan contingency retrain
    """
    actions = {
        "retrain_with_weights": [],
        "monitor": [],
        "consider_transform": [],
        "consider_replacement": [],
    }

    for r in drift_results:
        if r.status == "drifted":
            actions["retrain_with_weights"].append(r.feature)

            # Fitur momentum yang drifted → pertimbangkan rank transform
            if any(k in r.feature for k in ["rsi", "macd", "momentum", "roc"]):
                actions["consider_transform"].append(
                    f"{r.feature} → rank_transform (momentum drift saat regime shift)"
                )

            # Fitur volatilitas yang drifted → pertimbangkan percentile transform
            elif any(k in r.feature for k in ["atr", "bb_width", "hl_range", "vol_regime"]):
                actions["consider_transform"].append(
                    f"{r.feature} → percentile_rank (vol regime shift)"
                )

            # Fitur volume yang drifted → pertimbangkan log transform
            elif any(k in r.feature for k in ["vol_ratio", "vol_trend", "vwap"]):
                actions["consider_transform"].append(
                    f"{r.feature} → log_transform (volume regime shift)"
                )

        elif r.status == "moderate":
            actions["monitor"].append(r.feature)

    return actions


# ── 6. Main Pipeline ───────────────────────────────────────────────────────


def run_drift_remediation(
    tickers: list[str],
    ref_end_date: str,
    cur_start_date: str,
    lambda_decay: float = DEFAULT_LAMBDA,
    output_path: str = "drift_remediation_report.json",
) -> RemediationReport:
    """Jalankan pipeline drift remediasi end-to-end.

    Steps:
    1. Load features untuk setiap ticker
    2. Audit drift (PSI + KS test)
    3. Isolasi fitur drifted
    4. Apply regime-aware exponential weighting
    5. Generate rekomendasi perbaikan
    6. Save report
    """
    session = get_sessionmaker()()
    report = RemediationReport(
        audit_date=pd.Timestamp.now().isoformat(),
        tickers_audited=tickers,
        lambda_decay=lambda_decay,
    )

    # Load market regimes
    regimes = load_market_regimes(session)
    if not regimes.empty:
        regime_dist = regimes["regime"].value_counts().to_dict()
        report.regime_distribution = {str(k): int(v) for k, v in regime_dist.items()}
        logger.info("Market regimes loaded: %s", regime_dist)

    all_drifted: list[FeatureDriftResult] = []
    all_moderate: list[FeatureDriftResult] = []
    all_stable: list[FeatureDriftResult] = []
    weighted_summaries: dict = {}

    for i, ticker in enumerate(tickers):
        logger.info("[%d/%d] Processing %s...", i + 1, len(tickers), ticker)

        features = load_features(session, ticker)
        if features.empty or len(features) < 100:
            logger.warning("  %s: insufficient data (%d rows), skipping", ticker, len(features))
            continue

        # Audit drift
        drift_results = audit_feature_drift(
            features, ref_end_date, cur_start_date, regimes,
        )

        drifted = [r for r in drift_results if r.status == "drifted"]
        moderate = [r for r in drift_results if r.status == "moderate"]
        stable = [r for r in drift_results if r.status == "stable"]

        all_drifted.extend(drifted)
        all_moderate.extend(moderate)
        all_stable.extend(stable)

        logger.info("  Drift: %d drifted, %d moderate, %d stable (total %d)",
                     len(drifted), len(moderate), len(stable), len(drift_results))

        for d in drifted:
            logger.warning("    🔴 %s: PSI=%.4f, ref_mean=%.3f → cur_mean=%.3f (%s → %s)",
                           d.feature, d.psi, d.ref_mean, d.cur_mean,
                           d.regime_ref, d.regime_cur)

        # Apply regime-aware weighting
        weighted = apply_regime_aware_weighting(
            features, lambda_decay, regimes,
        )

        # Ringkasan bobot
        weights = weighted["sample_weight"]
        weighted_summaries[ticker] = {
            "n_samples": len(weights),
            "weight_mean": float(weights.mean()),
            "weight_max": float(weights.max()),
            "weight_min": float(weights.min()),
            "weight_sum": float(weights.sum()),
            "effective_sample_size": float(1.0 / np.sum(weights ** 2)),
        }

    # Aggregate
    report.total_features = len(all_drifted) + len(all_moderate) + len(all_stable)
    report.drifted_features = all_drifted
    report.moderate_features = all_moderate
    report.stable_features = all_stable
    report.weighted_feature_summary = weighted_summaries

    # Generate remediation actions
    actions = get_remediation_actions(all_drifted + all_moderate)

    # Print summary
    print("\n" + "=" * 70)
    print("FEATURE DRIFT REMEDIATION REPORT")
    print("=" * 70)
    print(f"  Tickers audited:     {len(tickers)}")
    print(f"  Total features:      {report.total_features}")
    print(f"  Drifted (PSI>0.25):  {len(all_drifted)}")
    print(f"  Moderate (PSI>0.10): {len(all_moderate)}")
    print(f"  Stable (PSI<0.10):   {len(all_stable)}")
    print(f"  Lambda (decay):      {lambda_decay}")
    print(f"  Regime distribution: {report.regime_distribution}")
    print()

    if all_drifted:
        print("  🔴 DRIFTED FEATURES (require retrain):")
        # Group by feature name across tickers
        feature_counts: dict[str, int] = {}
        for d in all_drifted:
            feature_counts[d.feature] = feature_counts.get(d.feature, 0) + 1
        for feat, count in sorted(feature_counts.items(), key=lambda x: -x[1]):
            print(f"    {feat}: drifted in {count} ticker(s)")
        print()

    if actions["consider_transform"]:
        print("  📋 RECOMMENDED TRANSFORMATIONS:")
        for t in actions["consider_transform"]:
            print(f"    → {t}")
        print()

    print("  📊 WEIGHTED FEATURE SUMMARY:")
    for ticker, summary in weighted_summaries.items():
        ess = summary["effective_sample_size"]
        print(f"    {ticker}: ESS={ess:.1f} (from {summary['n_samples']} samples)")
    print()

    # Save report
    report_dict = {
        "audit_date": report.audit_date,
        "tickers_audited": report.tickers_audited,
        "total_features": report.total_features,
        "lambda_decay": report.lambda_decay,
        "regime_distribution": report.regime_distribution,
        "drifted_features": [asdict(r) for r in all_drifted],
        "moderate_features": [asdict(r) for r in all_moderate],
        "stable_features": [asdict(r) for r in all_stable],
        "remediation_actions": actions,
        "weighted_feature_summary": weighted_summaries,
    }

    out_path = Path(output_path)
    out_path.write_text(json.dumps(report_dict, indent=2, default=str))
    print(f"  Report saved to: {out_path}")
    print("=" * 70)

    session.close()
    return report


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Feature Drift Isolation & Regime-Aware Remediation",
    )
    parser.add_argument(
        "--tickers", type=str, default=None,
        help="Comma-separated tickers (default: top 20 by row count)",
    )
    parser.add_argument(
        "--ref-end", type=str, default="2025-06-30",
        help="End date for reference window (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--cur-start", type=str, default="2025-07-01",
        help="Start date for current window (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--lambda", dest="lambda_decay", type=float, default=DEFAULT_LAMBDA,
        help=f"Exponential decay rate λ (default: {DEFAULT_LAMBDA})",
    )
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Max tickers if --tickers not specified",
    )
    parser.add_argument(
        "--output", type=str, default="drift_remediation_report.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()

    # Resolve tickers
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        session = get_sessionmaker()()
        rows = session.execute(
            text(
                "SELECT ticker, COUNT(*) as cnt FROM ohlcv "
                "WHERE ticker LIKE '%.JK' AND timeframe='1d' "
                "GROUP BY ticker ORDER BY cnt DESC LIMIT :limit"
            ),
            {"limit": args.limit},
        ).fetchall()
        session.close()
        tickers = [r[0] for r in rows]

    logger.info("=== FEATURE DRIFT REMEDIATION ===")
    logger.info("Tickers: %d (%s)", len(tickers), tickers[:5])
    logger.info("Reference window: until %s", args.ref_end)
    logger.info("Current window: from %s", args.cur_start)
    logger.info("Lambda decay: %s", args.lambda_decay)

    run_drift_remediation(
        tickers=tickers,
        ref_end_date=args.ref_end,
        cur_start_date=args.cur_start,
        lambda_decay=args.lambda_decay,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
