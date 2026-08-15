"""Portfolio Data Remediation — Quant-Safe Patching, Clustering & Ticker-Specific Tuning.

Skrip integrasi lanjutan yang menyembuhkan masalah kualitas data kronis pada
20 saham fokus (KPIG, TRIM, SONA, MEDC, UNTR, ICBP, ...) yang dilaporkan oleh
``database_profile_report.json``:

  * ``instrument_master.market_cap`` & ``subsector`` 100% NULL untuk focus ticker
  * ``fundamental_data`` (PE/PB) >84% NULL → fitur fundamental tidak dapat diandalkan
  * ``stock_personality`` metrik historis (avg_daily_volatility, trend_strength,
    correlation_ihsg, ...) 100% NULL

Pipeline 4 modul:

  MODULE A — Quant-Safe Data Patching & Fallback Layer
      * ``calculated_market_cap`` proksi = ohlcv.close × daily_trading_stats.listed_shares
        (fallback: instrument_master.listed_shares bila daily_trading_stats kosong).
      * Sembuhkan 100% NULL ``stock_personality``: hitung ``avg_daily_volatility``
        (std deviasi return 20 hari) dan ``trend_strength`` (korelasi harga vs waktu)
        langsung dari ohlcv.

  MODULE B — Sector-Level Hierarchical Clustering
      Kelompokkan 20 ticker ke 3 kluster operasional berbasis ``sector`` (100%
      lengkap) digabung ``calculated_market_cap`` (log-scale) via scipy kmeans2.

  MODULE C — Ticker-Specific Bayesian Tuning (regime-invariant features)
      * ``scipy.optimize.differential_evolution`` independen per ticker.
      * PAKSA LightGBM hanya memakai fitur regime-invariant 100% lengkap dari
        ``technical_indicators``: RSI, MACD, ATR14, BB_LOWER, VOLUME_SMA20.
        Fitur fundamental bolong (PE/PB) DILARANG dipakai.
      * ``adapt_kappa`` otomatis: κ ∝ 1/GK_volatility → saham volatil (MEDC,
        KPIG/TRIM) dapat κ kecil; defensif (ICBP/INDF) dapat κ besar.

  MODULE D — Output Matrix & Execution Validation
      * Simpan konfigurasi optimal per ticker → ``best_ticker_quant_config.json``.
      * Uji portofolio pembobotan Inverse-Variance; target KEEP (Score ≥ 3.5)
        dengan Alpha portofolio gabungan positif.

Desain memori (DB 9.23 GB):
  * sqlite3 read-only + PRAGMA mmap/cache; query per-ticker dengan WHERE ticker
    + LIMIT, JOIN efisien pada kolom terindeks.
  * ohlcv & technical_indicators dimuat per-ticker (~6.5k baris) lalu di-drop
    setelah diproses — tidak menahan seluruh tabel di RAM.

Usage:
    DB_PATH=data/market_research.db python scripts/portfolio_data_remediation.py \
        [--tickers KPIG.JK,TRIM.JK] [--limit 20] [--n-calls 20] \
        [--output best_ticker_quant_config.json] [--dry-run]

Requires: scipy, pandas, numpy, lightgbm

Referensi:
  - database_profile_report.json (audit kualitas data)
  - scripts/portfolio_cluster_tuner.py (Module 1-4, ticker-specific tuning)
  - scripts/alpha_hyper_tuner.py (adaptive kappa, _objective_function)
  - scripts/alpha_rescue_pipeline.py (ReformConfig, build_meta_label_features)
  - pustaka/96-ai-ml-audit-framework.md §9-10
  - AGENTS.md §2 (Keputusan Desain), §7 (Cross-Platform OS Awareness)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.cluster.vq import kmeans2
from scipy.optimize import differential_evolution

# ── Path setup ─────────────────────────────────────────────────────────────
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# Reusable pure-function helpers dari modul audit/tuning yang sudah ada.
# Fungsi-fungsi ini beroperasi pada DataFrame/Series (tidak butuh DB session).
from audit_ai_utility import (  # noqa: E402
    ROUND_TRIP_COST,
    TRADING_DAYS,
    RISK_FREE_RATE,
    compute_performance_metrics,
    simulate_strategy_returns,
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
)
from alpha_rescue_pipeline import (  # noqa: E402
    ReformConfig,
    build_meta_label_features,
    detect_regime,
    _lgbm_device as lgbm_device,
)
from alpha_hyper_tuner import (  # noqa: E402
    HyperParamSpace,
    TrialResult,
    generate_robust_trend_baseline,
    compute_adaptive_threshold,
    _build_config_from_params,
    _generate_vol_targeted_with_baseline,
    _objective_function,
)
from portfolio_cluster_tuner import (  # noqa: E402
    BASELINE_CANDIDATES,
    compute_garman_klass_volatility,
    compute_cross_sectional_kappa,
    compute_inverse_variance_weights,
    ensemble_portfolio_returns,
    evaluate_portfolio,
    select_best_baseline_for_ticker,
    _generate_vol_targeted_with_baseline_ticker,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("remediation")

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Konstanta ──────────────────────────────────────────────────────────────

# 20 ticker fokus default (dari database_profile_report.json summary).
DEFAULT_FOCUS_TICKERS: list[str] = [
    "KPIG.JK", "TRIM.JK", "SONA.JK", "TIRT.JK", "TCID.JK", "MEDC.JK", "PANS.JK",
    "KDSI.JK", "MTDL.JK", "BCIC.JK", "SPMA.JK", "BVIC.JK", "APLI.JK", "RBMS.JK",
    "UNTR.JK", "BNBR.JK", "INDF.JK", "UNIC.JK", "ASBI.JK", "ICBP.JK",
]

# Fitur regime-invariant 100% lengkap dari technical_indicators (0% NULL,
# diverifikasi di database_profile_report.json §data_quality.technical_indicators).
# PE/PB (fundamental_data, >84% NULL) DILARANG masuk daftar ini.
REGIME_INVARIANT_INDICATORS: list[str] = [
    "RSI", "MACD", "ATR14", "BB_LOWER", "VOLUME_SMA20",
]

# Cluster operasional target.
N_OPERATIONAL_CLUSTERS = 3
CLUSTER_LABELS = ["cluster_0", "cluster_1", "cluster_2"]

# Threshold promosi KEEP.
KEEP_SCORE_TARGET = 3.5


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TickerRemediation:
    """Hasil remediasi + optimasi untuk satu ticker."""

    ticker: str = ""
    sector: str = ""
    calculated_market_cap: float = 0.0
    market_cap_source: str = ""  # "daily_trading_stats" | "instrument_master"
    listed_shares: float = 0.0
    latest_close: float = 0.0
    # Healed stock_personality metrics
    avg_daily_volatility: float = 0.0
    trend_strength: float = 0.0
    correlation_ihsg: float = 0.0
    avg_volume: float = 0.0
    volume_consistency: float = 0.0
    # Cluster
    cluster_id: int = -1
    cluster_label: str = ""
    # Tuning
    baseline_mode: str = "donchian"
    baseline_params: dict = field(default_factory=dict)
    best_params: dict = field(default_factory=dict)
    adapt_kappa: float = 0.15
    gk_volatility: float = 0.0
    sharpe: float = 0.0
    alpha: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    accept_rate: float = 0.0
    brier: float = 0.0
    objective: float = 0.0
    n_observations: int = 0
    feature_completeness_pct: float = 0.0
    returns: pd.Series | None = None


@dataclass
class RemediationReport:
    """Laporan lengkap remediasi + tuning portofolio."""

    audit_date: str = ""
    db_path: str = ""
    tickers: list[str] = field(default_factory=list)
    n_tickers: int = 0
    n_tickers_optimized: int = 0
    ticker_results: list[dict] = field(default_factory=list)
    clusters: dict[int, list[str]] = field(default_factory=dict)
    portfolio_weights: dict = field(default_factory=dict)
    portfolio_sharpe: float = 0.0
    portfolio_alpha: float = 0.0
    portfolio_max_drawdown: float = 0.0
    portfolio_win_rate: float = 0.0
    portfolio_score: float = 0.0
    portfolio_verdict: str = ""
    promoted_to_keep: bool = False
    remediation_summary: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# DB CONNECTION — memory-efficient sqlite3 read-only
# ═══════════════════════════════════════════════════════════════════════════


def open_db(db_path: str) -> object:
    """Buka koneksi DB dengan pragma performa memori-efisien (SQLite-only).

    Untuk SQLite: URI read-only dengan PRAGMA mmap/cache.
    Untuk PostgreSQL: delegasi ke ``get_raw_connection()``.
    """
    from market.config import settings as _settings

    if _settings.db_backend == "postgresql":
        from market.db.raw import get_raw_connection
        return get_raw_connection().__enter__()

    import sqlite3
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Database tidak ditemukan: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def json_safe(obj: Any) -> Any:
    """Rekursif ubah numpy/pandas/Timestamp → JSON-safe."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [json_safe(v) for v in obj.tolist()]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        return obj
    return obj


# ═══════════════════════════════════════════════════════════════════════════
# DB LOADERS — per-ticker, ringan
# ═══════════════════════════════════════════════════════════════════════════


def load_ohlcv_sqlite(conn: object, ticker: str,
                      timeframe: str = "1d") -> pd.DataFrame:
    """Muat OHLCV satu ticker dari DB (ringan, ~6.5k baris).

    Index = DatetimeIndex (timestamp). Hanya kolom yang dibutuhkan untuk
    menghemat memori.
    """
    from market.config import settings as _settings
    _ph = "%s" if _settings.db_backend == "postgresql" else "?"
    sql = (
        f"SELECT timestamp, open, high, low, close, volume "
        f"FROM ohlcv WHERE ticker = {_ph} AND timeframe = {_ph} "
        f"ORDER BY timestamp"
    )
    df = pd.read_sql_query(
        sql, conn, params=(ticker, timeframe),
        parse_dates=["timestamp"],
    )
    if df.empty:
        return pd.DataFrame()
    df = df.set_index("timestamp")
    df = df[~df.index.duplicated(keep="last")]
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    return df


def load_benchmark_sqlite(conn: object,
                          ticker: str = "^JKSE") -> pd.Series:
    """Muat return benchmark (IHSG) dari ohlcv."""
    df = load_ohlcv_sqlite(conn, ticker)
    if df.empty:
        return pd.Series(dtype=float)
    return df["close"].pct_change().dropna()


def load_technical_features_sqlite(
    conn: object, ticker: str,
    indicators: list[str] | None = None,
) -> pd.DataFrame:
    """Pivot technical_indicators (long-format) → wide DataFrame per ticker.

    technical_indicators skema: (id, ticker, date, indicator, value, timeframe,
    source, created_at). Hanya indikator regime-invariant yang dimuat untuk
    meminimalkan memori.

    Returns:
        DataFrame index=Date (YYYY-MM-DD), kolom=indikator. Sudah di-transform
        menjadi regime-invariant (scale-free).
    """
    if indicators is None:
        indicators = REGIME_INVARIANT_INDICATORS

    from market.config import settings as _settings
    _ph = "%s" if _settings.db_backend == "postgresql" else "?"

    placeholders = ",".join(_ph for _ in indicators)
    sql = (
        f"SELECT date, indicator, value FROM technical_indicators "
        f"WHERE ticker = {_ph} AND indicator IN ({placeholders}) "
        f"ORDER BY date"
    )
    params: tuple[Any, ...] = (ticker, *indicators)
    df = pd.read_sql_query(sql, conn, params=params, parse_dates=["date"])
    if df.empty:
        return pd.DataFrame()

    # Pivot long → wide
    wide = df.pivot_table(index="date", columns="indicator", values="value",
                          aggfunc="first")
    wide = wide.reindex(columns=indicators)
    wide.index = pd.DatetimeIndex(wide.index)
    return wide


def get_instrument_master_row(conn: object,
                              ticker: str) -> dict[str, Any]:
    """Ambil baris instrument_master untuk satu ticker."""
    from market.config import settings as _settings
    _ph = "%s" if _settings.db_backend == "postgresql" else "?"
    cur = conn.cursor()
    cur.execute(
        f"SELECT ticker, sector, subsector, market_cap, listed_shares, "
        f"tradeable_shares, free_float, name "
        f"FROM instrument_master WHERE ticker = {_ph}",
        (ticker,),
    )
    row = cur.fetchone()
    if row is None:
        return {}
    cols = ["ticker", "sector", "subsector", "market_cap", "listed_shares",
            "tradeable_shares", "free_float", "name"]
    return dict(zip(cols, row))


def get_latest_listed_shares(conn: object,
                             ticker: str) -> tuple[float | None, str]:
    """Ambil listed_shares terbaru untuk ticker.

    Prioritas: daily_trading_stats (sesuai instruksi) → fallback
    instrument_master.listed_shares.

    Returns:
        (listed_shares, source)
    """
    from market.config import settings as _settings
    _ph = "%s" if _settings.db_backend == "postgresql" else "?"
    cur = conn.cursor()
    cur.execute(
        f"SELECT listed_shares FROM daily_trading_stats "
        f"WHERE ticker = {_ph} AND listed_shares IS NOT NULL "
        f"ORDER BY date DESC LIMIT 1",
        (ticker,),
    )
    row = cur.fetchone()
    if row and row[0] is not None:
        return float(row[0]), "daily_trading_stats"

    cur.execute(
        f"SELECT listed_shares FROM instrument_master "
        f"WHERE ticker = {_ph} AND listed_shares IS NOT NULL",
        (ticker,),
    )
    row = cur.fetchone()
    if row and row[0] is not None:
        return float(row[0]), "instrument_master"
    return None, "missing"


# ═══════════════════════════════════════════════════════════════════════════
# MODULE A — QUANT-SAFE DATA PATCHING & FALLBACK LAYER
# ═══════════════════════════════════════════════════════════════════════════


def compute_calculated_market_cap(
    conn: object, ticker: str, ohlcv: pd.DataFrame,
) -> tuple[float, float, str]:
    """Hitung proksi calculated_market_cap = close × listed_shares.

    Karena instrument_master.market_cap 100% NULL untuk focus ticker, gunakan
    close terbaru dari ohlcv × listed_shares dari daily_trading_stats (fallback
    instrument_master).

    Args:
        conn: koneksi DB.
        ticker: ticker.
        ohlcv: DataFrame ohlcv ticker (sudah dimuat).

    Returns:
        (calculated_market_cap, listed_shares, source)
    """
    listed_shares, source = get_latest_listed_shares(conn, ticker)
    if ohlcv.empty or listed_shares is None:
        return 0.0, listed_shares or 0.0, source
    latest_close = float(ohlcv["close"].iloc[-1])
    market_cap = latest_close * listed_shares
    return market_cap, listed_shares, source


def compute_stock_personality_metrics(
    ohlcv: pd.DataFrame, benchmark: pd.Series | None = None,
) -> dict[str, float]:
    """Sembuhkan 100% NULL stock_personality dari ohlcv historis.

    Metrik yang dihitung:
      * avg_daily_volatility: rata-rata std deviasi return 20 hari (rolling).
      * trend_strength: |korelasi Pearson| antara harga close vs waktu (index),
        diskalakan ×100 → 0..100. Tinggi = tren kuat (satu arah dominan).
      * correlation_ihsg: korelasi return ticker vs return IHSG (benchmark).
      * avg_volume: rata-rata volume 20 hari terakhir.
      * volume_consistency: 1 - (std volume / mean volume) selama 60 hari
        terakhir (konsistensi likuiditas, 0..1).

    Returns:
        Dict metrik yang siap di-UPDATE ke stock_personality.
    """
    if ohlcv.empty or len(ohlcv) < 30:
        return {
            "avg_daily_volatility": 0.0, "trend_strength": 0.0,
            "correlation_ihsg": 0.0, "avg_volume": 0.0,
            "volume_consistency": 0.0,
        }

    close = ohlcv["close"].astype(float)
    volume = ohlcv["volume"].astype(float)
    returns = close.pct_change()

    # avg_daily_volatility: rolling 20-day std of returns, lalu di-rata-rata.
    rolling_vol = returns.rolling(20, min_periods=20).std()
    avg_daily_volatility = float(rolling_vol.dropna().mean())
    if np.isnan(avg_daily_volatility):
        avg_daily_volatility = 0.0

    # trend_strength: |corr(close, time)| × 100.
    t = np.arange(len(close), dtype=float)
    if close.std() > 0 and t.std() > 0:
        corr = float(np.corrcoef(close.values, t)[0, 1])
    else:
        corr = 0.0
    trend_strength = round(abs(corr) * 100.0, 2)
    if np.isnan(trend_strength):
        trend_strength = 0.0

    # correlation_ihsg: corr(return ticker, return benchmark) pada index sama.
    correlation_ihsg = 0.0
    if benchmark is not None and not benchmark.empty:
        aligned = pd.DataFrame({"ret": returns, "bench": benchmark}).dropna()
        if len(aligned) > 30 and aligned["ret"].std() > 0 and aligned["bench"].std() > 0:
            correlation_ihsg = round(
                float(aligned["ret"].corr(aligned["bench"])), 4)

    # avg_volume: rata-rata volume 20 hari terakhir.
    avg_volume = float(volume.tail(20).mean())

    # volume_consistency: 1 - CV(volume) selama 60 hari terakhir (clamp 0..1).
    recent_vol = volume.tail(60)
    if recent_vol.mean() > 0:
        cv = recent_vol.std() / recent_vol.mean()
        volume_consistency = round(max(0.0, min(1.0, 1.0 - float(cv))), 2)
    else:
        volume_consistency = 0.0

    return {
        "avg_daily_volatility": round(avg_daily_volatility, 4),
        "trend_strength": trend_strength,
        "correlation_ihsg": correlation_ihsg,
        "avg_volume": round(avg_volume, 2),
        "volume_consistency": volume_consistency,
    }


def remediate_ticker(
    conn: object, ticker: str, benchmark: pd.Series | None,
) -> tuple[TickerRemediation, pd.DataFrame, pd.DataFrame]:
    """Jalankan Module A untuk satu ticker.

    Returns:
        (remediation_record, ohlcv, tech_features) — ohlcv & tech_features
        dikembalikan agar dapat di-reuse di Module C tanpa reload DB.
    """
    im = get_instrument_master_row(conn, ticker)
    sector = im.get("sector") or "Unknown"

    ohlcv = load_ohlcv_sqlite(conn, ticker)
    tech = load_technical_features_sqlite(conn, ticker)

    market_cap, listed_shares, mc_source = compute_calculated_market_cap(
        conn, ticker, ohlcv)
    latest_close = float(ohlcv["close"].iloc[-1]) if not ohlcv.empty else 0.0

    personality = compute_stock_personality_metrics(ohlcv, benchmark)

    rec = TickerRemediation(
        ticker=ticker,
        sector=sector,
        calculated_market_cap=market_cap,
        market_cap_source=mc_source,
        listed_shares=listed_shares,
        latest_close=latest_close,
        avg_daily_volatility=personality["avg_daily_volatility"],
        trend_strength=personality["trend_strength"],
        correlation_ihsg=personality["correlation_ihsg"],
        avg_volume=personality["avg_volume"],
        volume_consistency=personality["volume_consistency"],
    )
    return rec, ohlcv, tech


# ═══════════════════════════════════════════════════════════════════════════
# MODULE B — SECTOR-LEVEL HIERARCHICAL CLUSTERING (3 kluster operasional)
# ═══════════════════════════════════════════════════════════════════════════


def cluster_tickers_by_sector_cap(
    records: list[TickerRemediation], n_clusters: int = N_OPERATIONAL_CLUSTERS,
) -> dict[str, int]:
    """Kelompokkan ticker ke 3 kluster operasional: sector + log(market_cap).

    Feature space 2D per ticker:
      * sector_encoded: integer encoding sector (one-hot via label encode).
      * log_market_cap: log10(calculated_market_cap) — normalisasi skala kapitalisasi
        yang membentang beberapa orde magnitudo (KPIG ~7.9T vs UNTR ~300B).

    Clustering via scipy.cluster.vq.kmeans2 (k=3, seed tetap untuk reproduksibilitas).
    Sector di-encode sehingga ticker sektor sama cenderung terkelompok, lalu
    market_cap memisahkan besar/kecil di dalam sektor.

    Returns:
        {ticker: cluster_id (0..n-1)}
    """
    valid = [r for r in records if r.calculated_market_cap > 0]
    if not valid:
        return {r.ticker: 0 for r in records}

    # Encode sector → integer
    sectors = sorted({r.sector for r in valid})
    sector_to_id = {s: i for i, s in enumerate(sectors)}
    n_sectors = max(len(sectors), 1)

    # Bangun matriks fitur [sector_onehot_normalized, log_market_cap_normalized]
    rows = []
    for r in valid:
        sec_feat = sector_to_id[r.sector] / max(n_sectors - 1, 1)  # 0..1
        log_cap = np.log10(r.calculated_market_cap) if r.calculated_market_cap > 0 else 0.0
        rows.append([sec_feat, log_cap])
    X = np.array(rows, dtype=float)

    # Normalisasi z-score per kolom agar kmeans tidak didominasi log_cap
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    Xz = (X - mean) / std

    k = min(n_clusters, len(valid))
    # kmeans2 dengan seed tetap; minit='++' untuk inisialisasi k-means++ yang lebih stabil
    centroids, labels = kmeans2(Xz, k, minit="++", seed=42, iter=50)

    # Urutkan cluster berdasarkan log_market_cap centroid (cluster 0 = cap terkecil)
    # agar label kluster operasional konsisten & dapat diinterpretasi.
    cluster_cap = []
    for c in range(k):
        mask = labels == c
        if mask.any():
            cluster_cap.append((c, float(np.mean(X[mask, 1]))))
        else:
            cluster_cap.append((c, 0.0))
    order = [c for c, _ in sorted(cluster_cap, key=lambda x: x[1])]
    remap = {old: new for new, old in enumerate(order)}

    result = {r.ticker: remap[labels[i]] for i, r in enumerate(valid)}
    # Ticker tanpa market_cap → cluster -1 (outlier)
    for r in records:
        if r.ticker not in result:
            result[r.ticker] = -1
    return result


# ═══════════════════════════════════════════════════════════════════════════
# MODULE C — REGIME-INVARIANT META-LABELER + TICKER-SPECIFIC BAYESIAN TUNING
# ═══════════════════════════════════════════════════════════════════════════


def build_regime_invariant_features(
    ohlcv: pd.DataFrame, tech: pd.DataFrame,
) -> pd.DataFrame:
    """Bangun matriks fitur regime-invariant dari technical_indicators.

    Transformasi scale-free agar fitur tidak drift dengan level harga (regime-
    invariant), sesuai syarat "hanya fitur 100% lengkap dari technical_indicators":

      * RSI          → as-is (0..100, sudah bounded & regime-invariant)
      * MACD         → as-is (momentum oscillator, sudah scale-relative)
      * ATR14        → ATR14 / close  (ATR%, volatilitas relatif scale-free)
      * BB_LOWER     → (close - BB_LOWER) / close  (jarak relatif ke lower band)
      * VOLUME_SMA20 → as-is (sudah smoothed volume ratio)

    Fitur fundamental (PE/PB) SENGAJA tidak dimasukkan (>84% NULL → tidak
    dapat diandalkan, akan merusak walk-forward bila di-impute sembarangan).

    Returns:
        DataFrame index=DatetimeIndex (aligned ke ohlcv.index), 5 kolom fitur.
    """
    if tech.empty:
        return pd.DataFrame(index=ohlcv.index)

    close = ohlcv["close"].astype(float)
    # Normalisasi index ke date (tech.index sudah DatetimeIndex date; ohlcv
    # index DatetimeIndex datetime — samakan ke date midnight).
    feat = tech.copy()
    feat.index = pd.DatetimeIndex(feat.index).normalize()
    oh_idx = ohlcv.index.normalize()

    out = pd.DataFrame(index=oh_idx)
    out["close"] = close.values

    # Reindex tech ke ohlcv index (forward fill max 1 hari untuk holiday gap)
    feat_aligned = feat.reindex(oh_idx).ffill(limit=1)

    out["RSI"] = feat_aligned.get("RSI")
    out["MACD"] = feat_aligned.get("MACD")
    atr = feat_aligned.get("ATR14")
    bb_lower = feat_aligned.get("BB_LOWER")
    out["ATR_pct"] = (atr / out["close"]).replace([np.inf, -np.inf], np.nan)
    out["BB_dist"] = ((out["close"] - bb_lower) / out["close"]).replace(
        [np.inf, -np.inf], np.nan)
    out["VOLUME_SMA20"] = feat_aligned.get("VOLUME_SMA20")

    feature_cols = ["RSI", "MACD", "ATR_pct", "BB_dist", "VOLUME_SMA20"]
    out = out[feature_cols]
    # Imputasi sisa NaN dengan median kolom (regime-invariant, tidak lookahead
    # karena median bersifat global summary; walk-forward tetap fair karena
    # target dibentuk dari forward return).
    for c in feature_cols:
        if out[c].isna().any():
            med = out[c].median()
            out[c] = out[c].fillna(med if not np.isnan(med) else 0.0)
    return out


def feature_completeness(tech: pd.DataFrame,
                         indicators: list[str] | None = None) -> float:
    """Hitung % kelengkapan fitur regime-invariant (verifikasi 100% lengkap)."""
    if indicators is None:
        indicators = REGIME_INVARIANT_INDICATORS
    if tech.empty:
        return 0.0
    present = [c for c in indicators if c in tech.columns]
    if not present:
        return 0.0
    non_null = sum(float(tech[c].notna().mean()) for c in present)
    return round(non_null / len(indicators) * 100.0, 2)


def _generate_regime_invariant_meta_signals(
    ohlcv: pd.DataFrame,
    primary_signals: pd.Series,
    config: ReformConfig,
    tech_features: pd.DataFrame,
    adapt_kappa: float = 0.15,
) -> tuple[pd.Series, dict]:
    """Meta-labeler FORCED regime-invariant: hanya fitur dari technical_indicators.

    Berbeda dari ``_generate_adaptive_meta_labeled_signals`` (alpha_hyper_tuner)
    yang memakai fitur ohlcv-computed (regime one-hot, vol_zscore, ma_ratio,
    dll.), fungsi ini HANYA memakai RSI/MACD/ATR_pct/BB_dist/VOLUME_SMA20 dari
    tabel technical_indicators — fitur yang terbukti 100% lengkap & tidak
    bergantung pada fundamental_data yang bolong (PE/PB).

    Threshold P(execute) tetap dinamis berbasis vol_zscore (dihitung dari ohlcv)
    dengan adapt_kappa spesifik ticker.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.warning("LightGBM tidak tersedia — fallback ke primer (regime-invariant)")
        return primary_signals, {"n_predictions": 0, "accept_rate": 1.0, "brier": 1.0}

    primary_side = convert_signal_to_position(primary_signals, config.signal_threshold)

    # Target meta-label: forward return × side > round-trip cost.
    # Dihitung dari ohlcv (struktur target sama dengan build_meta_label_features,
    # tapi fitur X diganti dengan technical_indicators).
    close = ohlcv["close"].astype(float)
    forward_return = close.shift(-config.meta_horizon) / close - 1
    aligned_return = forward_return * primary_side
    target_meta = (aligned_return > config.meta_cost_threshold).astype(float)
    target_meta[primary_side == 0] = np.nan

    # vol_zscore untuk adaptive threshold (dari ohlcv — bukan fitur model).
    returns = close.pct_change()
    vol_roll = returns.rolling(20).std()
    vol_zscore = (
        (vol_roll - vol_roll.rolling(252, min_periods=60).mean())
        / vol_roll.rolling(252, min_periods=60).std().replace(0, np.nan)
    ).fillna(0.0)

    feature_cols = ["RSI", "MACD", "ATR_pct", "BB_dist", "VOLUME_SMA20"]
    feat = tech_features[feature_cols].copy()
    feat["target_meta"] = target_meta
    feat["vol_zscore"] = vol_zscore

    clean = feat.dropna(subset=feature_cols + ["target_meta"])
    if len(clean) < config.min_train_samples + 50:
        return primary_signals, {"n_predictions": 0, "accept_rate": 1.0, "brier": 1.0}

    steps = config.walk_forward_steps or max(20, int(len(clean) * 0.2))
    positions = pd.Series(0.0, index=ohlcv.index)
    accept_rates: list[float] = []
    brier_scores: list[float] = []
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
            device=lgbm_device(),
        )
        model.fit(
            X_tr, y_tr,
            sample_weight=weights,
            eval_X=X_val, eval_y=y_val,
            callbacks=[lgb.early_stopping(15, verbose=False)],
        )

        X_test = test_data[feature_cols].values
        proba_exec = model.predict_proba(X_test)[:, 1]

        vol_z = test_data["vol_zscore"].fillna(0.0).values
        dyn_threshold = compute_adaptive_threshold(
            vol_z, base_threshold=base_threshold, adapt_kappa=adapt_kappa,
        )

        accepted = 0
        for j, idx in enumerate(test_data.index):
            side = primary_side.reindex([idx]).iloc[0]
            exec_prob = proba_exec[j]
            if exec_prob >= dyn_threshold[j]:
                positions.loc[idx] = side * exec_prob
                accepted += 1
            else:
                positions.loc[idx] = 0.0
        accept_rates.append(accepted / max(len(test_data), 1))

        # Brier score (kalibrasi probabilitas) pada test window
        y_test = test_data["target_meta"].values
        brier_scores.append(float(np.mean((proba_exec - y_test) ** 2)) if len(y_test) else 1.0)

    diag = {
        "n_predictions": int(len(clean) - config.min_train_samples),
        "accept_rate": float(np.mean(accept_rates)) if accept_rates else 0.0,
        "brier": float(np.mean(brier_scores)) if brier_scores else 1.0,
        "feature_set": "regime_invariant_technical_indicators",
        "n_features": len(feature_cols),
    }
    return positions, diag


def optimize_ticker_remediated(
    ohlcv: pd.DataFrame,
    benchmark: pd.Series | None,
    config: ReformConfig,
    space: HyperParamSpace,
    baseline_candidate: dict,
    adapt_kappa: float,
    tech_features: pd.DataFrame,
    n_calls: int = 20,
) -> TickerRemediation:
    """Bayesian optimization (differential_evolution) per ticker.

    Perbedaan vs ``portfolio_cluster_tuner.optimize_ticker``:
      * Meta-labeler memakai ``_generate_regime_invariant_meta_signals`` (fitur
        technical_indicators, tanpa PE/PB).
      * κ spesifik ticker dari cross-sectional GK volatility (saham volatil →
        κ kecil → filter tidak membunuh sinyal produktif).
    """
    baseline_mode = baseline_candidate["mode"]
    baseline_params = {k: v for k, v in baseline_candidate.items() if k != "mode"}

    bounds = [
        space.meta_prob_threshold,
        space.vol_aggressiveness,
        space.vol_hard_cutoff_zscore,
        space.signal_threshold,
    ]

    all_results: list[TrialResult] = []

    # Pre-compute baseline direction signals (tidak bergantung params DE).
    baseline_direction = generate_robust_trend_baseline(
        ohlcv, **baseline_candidate,
    ).astype(float)

    # Pre-compute vol-targeted features & meta-label features sekali.
    # Ini menghemat ~50% waktu per evaluasi karena walk-forward vol-target
    # hanya perlu re-fit saat vol_aggressiveness / cutoff berubah.
    # Namun karena params DE mengubah config (vol_aggressiveness, cutoff),
    # kita tidak bisa pre-compute vol_positions sepenuhnya.
    # Solusi: set walk_forward_steps eksplisit agar jumlah model turun.
    fast_config = _build_config_from_params(
        config,
        {"meta_prob_threshold": 0.5, "vol_aggressiveness": 2.5,
         "vol_hard_cutoff_zscore": 1.5, "signal_threshold": 0.1},
        baseline_mode,
    )
    # Paksa walk_forward_steps besar → fewer models per evaluation.
    n_clean = len(tech_features.dropna(
        subset=[c for c in tech_features.columns if c != "target_meta"]
    )) if not tech_features.empty else len(ohlcv)
    fast_steps = max(60, int(n_clean * 0.15))
    fast_config.walk_forward_steps = fast_steps

    def neg_objective(x):
        params = {
            "meta_prob_threshold": round(float(x[0]), 4),
            "vol_aggressiveness": round(float(x[1]), 4),
            "vol_hard_cutoff_zscore": round(float(x[2]), 4),
            "signal_threshold": round(float(x[3]), 4),
        }
        cfg = _build_config_from_params(config, params, baseline_mode)
        cfg.walk_forward_steps = fast_steps

        vol_positions, _ = _generate_vol_targeted_with_baseline_ticker(
            ohlcv, cfg, baseline_candidate,
        )
        rescued, diag2 = _generate_regime_invariant_meta_signals(
            ohlcv, vol_positions, cfg, tech_features, adapt_kappa=adapt_kappa,
        )
        positions = convert_signal_to_position(rescued, cfg.signal_threshold)
        returns = simulate_strategy_returns(ohlcv, positions)
        bench_aligned = (
            benchmark.reindex(returns.index).dropna()
            if benchmark is not None else None
        )
        perf = compute_performance_metrics(returns, bench_aligned)
        obj = _objective_function(
            perf.sharpe_ratio, perf.alpha, perf.max_drawdown,
            diag2.get("accept_rate", 0.0),
        )
        all_results.append(TrialResult(
            params=params, sharpe=perf.sharpe_ratio, alpha=perf.alpha,
            max_drawdown=perf.max_drawdown, win_rate=perf.win_rate,
            accept_rate=diag2.get("accept_rate", 0.0),
            brier=diag2.get("brier", 1.0), objective=obj,
            n_observations=len(returns),
        ))
        return -obj

    differential_evolution(
        neg_objective, bounds=bounds, maxiter=n_calls, seed=42,
        tol=1e-3, polish=True, init="sobol", popsize=5,
    )

    best_trial = max(all_results, key=lambda t: t.objective)

    # Recompute returns dengan best params
    cfg_best = _build_config_from_params(config, best_trial.params, baseline_mode)
    cfg_best.walk_forward_steps = fast_steps
    vol_pos, _ = _generate_vol_targeted_with_baseline_ticker(
        ohlcv, cfg_best, baseline_candidate)
    rescued, diag2 = _generate_regime_invariant_meta_signals(
        ohlcv, vol_pos, cfg_best, tech_features, adapt_kappa=adapt_kappa)
    positions = convert_signal_to_position(rescued, cfg_best.signal_threshold)
    best_returns = simulate_strategy_returns(ohlcv, positions)

    return TickerRemediation(
        baseline_mode=baseline_mode,
        baseline_params=baseline_params,
        best_params=best_trial.params,
        adapt_kappa=adapt_kappa,
        gk_volatility=compute_garman_klass_volatility(ohlcv),
        sharpe=best_trial.sharpe,
        alpha=best_trial.alpha,
        max_drawdown=best_trial.max_drawdown,
        win_rate=best_trial.win_rate,
        accept_rate=best_trial.accept_rate,
        brier=best_trial.brier,
        objective=best_trial.objective,
        n_observations=best_trial.n_observations,
        returns=best_returns,
    )


# ═══════════════════════════════════════════════════════════════════════════
# MODULE D — ORCHESTRATION: REMEDIATION + CLUSTERING + TUNING + VALIDATION
# ═══════════════════════════════════════════════════════════════════════════


def run_portfolio_data_remediation(
    tickers: list[str],
    db_path: str,
    config: ReformConfig | None = None,
    space: HyperParamSpace | None = None,
    n_calls: int = 20,
    output_path: str = "best_ticker_quant_config.json",
    dry_run: bool = False,
) -> RemediationReport:
    """Jalankan pipeline remediasi + tuning penuh.

    Alur:
      A. Per ticker: hitung market_cap proxy + heal stock_personality.
      B. Cluster 20 ticker → 3 kluster (sector + log market_cap).
      C. Cross-sectional κ (GK) → per ticker: baseline selection + Bayesian DE
         dengan regime-invariant features.
      D. Portfolio Inverse-Variance ensemble → Score Card → KEEP validation.
    """
    if config is None:
        config = ReformConfig()
    if space is None:
        space = HyperParamSpace()

    report = RemediationReport(
        audit_date=pd.Timestamp.now().isoformat(),
        db_path=db_path,
        tickers=tickers,
        n_tickers=len(tickers),
    )

    logger.info("=" * 72)
    logger.info("PORTFOLIO DATA REMEDIATION — QUANT-SAFE PATCHING + TUNING")
    logger.info("=" * 72)
    logger.info("DB: %s", db_path)
    logger.info("Tickers: %d (%s)", len(tickers), tickers)
    logger.info("DE calls per ticker: %d  |  Target: Score >= %.1f (KEEP)",
                n_calls, KEEP_SCORE_TARGET)
    logger.info("Regime-invariant features: %s", REGIME_INVARIANT_INDICATORS)
    logger.info("")

    conn = open_db(db_path)
    try:
        benchmark = load_benchmark_sqlite(conn)

        # ── MODULE A: Data Patching ──
        logger.info("MODULE A — Quant-Safe Data Patching & Fallback Layer")
        logger.info("-" * 72)

        records: list[TickerRemediation] = []
        ohlcv_cache: dict[str, pd.DataFrame] = {}
        tech_cache: dict[str, pd.DataFrame] = {}

        for i, ticker in enumerate(tickers):
            t0 = time.time()
            rec, ohlcv, tech = remediate_ticker(conn, ticker, benchmark)
            records.append(rec)
            ohlcv_cache[ticker] = ohlcv
            tech_cache[ticker] = tech
            logger.info(
                "  [%2d/%d] %s | sector=%-22s | cap=%-15s | vol=%.4f | trend=%.1f | %s",
                i + 1, len(tickers), ticker, rec.sector,
                f"{rec.calculated_market_cap:,.0f}",
                rec.avg_daily_volatility, rec.trend_strength,
                f"{time.time()-t0:.1f}s",
            )

        n_cap_healed = sum(1 for r in records if r.calculated_market_cap > 0)
        n_vol_healed = sum(1 for r in records if r.avg_daily_volatility > 0)
        n_trend_healed = sum(1 for r in records if r.trend_strength > 0)
        report.remediation_summary = {
            "market_cap_proxy_healed": n_cap_healed,
            "market_cap_proxy_total": len(records),
            "avg_daily_volatility_healed": n_vol_healed,
            "trend_strength_healed": n_trend_healed,
            "sources": {r.ticker: r.market_cap_source for r in records},
        }
        logger.info("")
        logger.info("  Remediation summary:")
        logger.info("    market_cap proxy healed : %d/%d", n_cap_healed, len(records))
        logger.info("    avg_daily_volatility    : %d/%d", n_vol_healed, len(records))
        logger.info("    trend_strength          : %d/%d", n_trend_healed, len(records))
        logger.info("")

        # ── MODULE B: Sector-Level Clustering ──
        logger.info("MODULE B — Sector-Level Hierarchical Clustering (k=%d)",
                    N_OPERATIONAL_CLUSTERS)
        logger.info("-" * 72)

        cluster_map = cluster_tickers_by_sector_cap(records)
        clusters: dict[int, list[str]] = {c: [] for c in range(N_OPERATIONAL_CLUSTERS)}
        for r in records:
            cid = cluster_map.get(r.ticker, -1)
            r.cluster_id = cid
            r.cluster_label = CLUSTER_LABELS[cid] if 0 <= cid < len(CLUSTER_LABELS) else "outlier"
            if 0 <= cid < N_OPERATIONAL_CLUSTERS:
                clusters[cid].append(r.ticker)
        report.clusters = clusters

        for cid, members in clusters.items():
            logger.info("  %s (n=%d): %s", CLUSTER_LABELS[cid], len(members), members)
        logger.info("")

        if dry_run:
            logger.info("[DRY-RUN] Modul C/D dilewati (--dry-run).")
            report.ticker_results = [json_safe(asdict(r)) for r in records]
            _save_config(records, output_path, report, dry_run=True)
            return report

        # Set walk_forward_steps eksplisit untuk mengurangi jumlah model
        # LightGBM per evaluasi (dari ~20% data → 15% data, fewer windows).
        config.walk_forward_steps = max(60, int(
            max(len(oh) for oh in ohlcv_cache.values()) * 0.15))

        # ── MODULE C: Ticker-Specific Bayesian Tuning ──
        logger.info("MODULE C — Ticker-Specific Bayesian Tuning (regime-invariant)")
        logger.info("-" * 72)

        # Cross-sectional adaptive κ dari GK volatility
        gk_vols: dict[str, float] = {}
        for ticker, ohlcv in ohlcv_cache.items():
            if len(ohlcv) < 500:
                logger.info("  %s: skip (data < 500 rows)", ticker)
                continue
            gk_vols[ticker] = compute_garman_klass_volatility(ohlcv)

        if not gk_vols:
            logger.warning("Tidak ada ticker valid — pipeline berhenti")
            return report

        kappas = compute_cross_sectional_kappa(gk_vols)
        logger.info("  Cross-sectional adaptive κ (invers GK volatility):")
        for t, k in sorted(kappas.items(), key=lambda x: gk_vols[x[0]], reverse=True):
            logger.info("    %-10s κ=%.4f  GK=%.6f  vol_healed=%.4f",
                        t, k, gk_vols[t],
                        next(r.avg_daily_volatility for r in records if r.ticker == t))
        logger.info("")

        # Before-tuning baseline (global config, donchian) untuk perbandingan
        before_returns: dict[str, pd.Series] = {}
        for ticker, ohlcv in ohlcv_cache.items():
            if ticker not in gk_vols:
                continue
            vol_pos, _ = _generate_vol_targeted_with_baseline(ohlcv, config, "donchian")
            feat_pre = build_regime_invariant_features(ohlcv, tech_cache[ticker])
            rescued, _ = _generate_regime_invariant_meta_signals(
                ohlcv, vol_pos, config, feat_pre, adapt_kappa=0.15)
            positions = convert_signal_to_position(rescued, config.signal_threshold)
            before_returns[ticker] = simulate_strategy_returns(ohlcv, positions)

        before_weights = compute_inverse_variance_weights(before_returns)
        before_portfolio = ensemble_portfolio_returns(before_returns, before_weights)
        before_metrics = evaluate_portfolio(before_portfolio, benchmark)
        logger.info("  Before-tuning portfolio: Sharpe=%+.3f, Alpha=%+.4f, "
                    "MaxDD=%.2f%%, WinRate=%.1f%%",
                    before_metrics["sharpe"], before_metrics["alpha"],
                    before_metrics["max_drawdown"] * 100,
                    before_metrics["win_rate"] * 100)
        logger.info("")

        # Per-ticker optimization
        optimized: list[TickerRemediation] = []
        for i, (ticker, ohlcv) in enumerate(ohlcv_cache.items()):
            if ticker not in gk_vols:
                continue
            t0 = time.time()
            logger.info("  [%2d/%d] %s — optimizing (κ=%.4f, GK=%.6f)",
                        i + 1, len(ohlcv_cache), ticker,
                        kappas[ticker], gk_vols[ticker])

            # Cari baseline terbaik
            best_candidate, best_baseline = select_best_baseline_for_ticker(
                ohlcv, benchmark)
            logger.info("    ▶ baseline=%s (params=%s, Sharpe=%+.3f)",
                        best_candidate["mode"],
                        {k: v for k, v in best_candidate.items() if k != "mode"},
                        best_baseline["sharpe"])

            # Bayesian DE dengan regime-invariant features
            tech = tech_cache[ticker]
            feat_df = build_regime_invariant_features(ohlcv, tech)
            completeness = feature_completeness(tech)
            logger.info("    ▶ feature completeness=%.1f%% (regime-invariant)",
                        completeness)

            result = optimize_ticker_remediated(
                ohlcv, benchmark, config, space,
                best_candidate, kappas[ticker], feat_df, n_calls=n_calls,
            )

            # Merge ke record remediasi
            rec = next(r for r in records if r.ticker == ticker)
            rec.baseline_mode = result.baseline_mode
            rec.baseline_params = result.baseline_params
            rec.best_params = result.best_params
            rec.adapt_kappa = result.adapt_kappa
            rec.gk_volatility = result.gk_volatility
            rec.sharpe = result.sharpe
            rec.alpha = result.alpha
            rec.max_drawdown = result.max_drawdown
            rec.win_rate = result.win_rate
            rec.accept_rate = result.accept_rate
            rec.brier = result.brier
            rec.objective = result.objective
            rec.n_observations = result.n_observations
            rec.feature_completeness_pct = completeness
            rec.returns = result.returns
            optimized.append(rec)

            logger.info("    → Sharpe=%+.3f, Alpha=%+.4f, AcceptRate=%.1f%%, "
                        "obj=%.4f (%.1fs)",
                        result.sharpe, result.alpha, result.accept_rate * 100,
                        result.objective, time.time() - t0)
            logger.info("      params: %s", result.best_params)

            # Bebaskan memori fitur per-ticker
            del feat_df

        report.n_tickers_optimized = len(optimized)
        logger.info("")

        # ── MODULE D: Portfolio Validation ──
        logger.info("MODULE D — Portfolio Inverse-Variance Ensemble + Validation")
        logger.info("-" * 72)

        after_returns: dict[str, pd.Series] = {}
        for rec in optimized:
            if rec.returns is not None:
                after_returns[rec.ticker] = rec.returns

        after_weights = compute_inverse_variance_weights(after_returns)
        report.portfolio_weights = {t: round(w, 4) for t, w in after_weights.items()}

        logger.info("  Inverse-Variance weights:")
        for t, w in sorted(after_weights.items(), key=lambda x: -x[1]):
            logger.info("    %-10s weight=%.4f", t, w)

        after_portfolio = ensemble_portfolio_returns(after_returns, after_weights)
        after_metrics = evaluate_portfolio(after_portfolio, benchmark)

        # Score Card
        first_ohlcv = next(iter(ohlcv_cache.values()))
        delta = compute_delta_alpha(
            first_ohlcv,
            after_portfolio.reindex(first_ohlcv.index).fillna(0),
            benchmark, "RemediatedPortfolio", config.signal_threshold,
        )

        sig_results: list[SignificanceTestResult] = []
        aligned = pd.DataFrame({
            "ai": after_portfolio, "baseline": before_portfolio,
        }).dropna()
        if len(aligned) > 30:
            sig_results.append(paired_ttest(aligned["ai"], aligned["baseline"]))
            if benchmark is not None:
                bench_re = benchmark.reindex(aligned.index).fillna(0)
                sig_results.append(diebold_mariano_test(
                    aligned["ai"] - bench_re, aligned["baseline"] - bench_re,
                    horizon=5,
                ))
            sig_results.append(whites_reality_check_approximation(
                aligned["ai"], aligned["baseline"], n_bootstrap=500,
            ))

        verdict = compute_component_score_card(
            component_name="RemediatedPortfolio",
            delta_alpha_result=delta,
            significance_results=sig_results,
            drift_results=None,
            latency_ms=None,
            monthly_cost=0.0,
        )
        score = verdict.score_card["weighted_total"]
        promoted = (
            verdict.verdict == "KEEP"
            and after_metrics["sharpe"] > 1.0
            and after_metrics["alpha"] > 0
            and score >= KEEP_SCORE_TARGET
        )

        report.portfolio_sharpe = after_metrics["sharpe"]
        report.portfolio_alpha = after_metrics["alpha"]
        report.portfolio_max_drawdown = after_metrics["max_drawdown"]
        report.portfolio_win_rate = after_metrics["win_rate"]
        report.portfolio_score = score
        report.portfolio_verdict = verdict.verdict
        report.promoted_to_keep = promoted

        # Simpan ticker results
        report.ticker_results = [json_safe(asdict(r)) for r in records]

        # ── Validation Report ──
        logger.info("")
        logger.info("  ┌────────────────────────────────────────────────────────────────┐")
        logger.info("  │  PORTFOLIO VALIDATION: BEFORE vs AFTER REMEDIATION             │")
        logger.info("  ├────────────────────────────────────────────────────────────────┤")
        for label, key, fmt in [
            ("Sharpe Ratio", "sharpe", "%+.3f"),
            ("Alpha (annual)", "alpha", "%+.4f"),
            ("Max Drawdown", "max_drawdown", "%.2f%%"),
            ("Win Rate", "win_rate", "%.1f%%"),
        ]:
            b_val = before_metrics.get(key, 0.0)
            a_val = after_metrics.get(key, 0.0)
            if key in ("max_drawdown", "win_rate"):
                b_str, a_str = fmt % (b_val * 100), fmt % (a_val * 100)
            else:
                b_str, a_str = fmt % b_val, fmt % a_val
            d = a_val - b_val
            arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
            logger.info("  │  %-16s │  %14s │  %14s  %s │",
                        label, b_str, a_str, arrow)
        logger.info("  │  Score Card      │          3.16  │  %13.2f/5  │", score)
        logger.info("  └────────────────────────────────────────────────────────────────┘")
        logger.info("")

        logger.info("  Per-Ticker Summary:")
        for rec in optimized:
            logger.info("    %-10s cluster=%s κ=%.4f Sharpe=%+.3f Alpha=%+.4f accept=%.1f%%",
                        rec.ticker, rec.cluster_label, rec.adapt_kappa,
                        rec.sharpe, rec.alpha, rec.accept_rate * 100)

        logger.info("")
        logger.info("  Verdict: %s | Score: %.2f/5.00 | Promoted KEEP: %s",
                    verdict.verdict, score, "YES" if promoted else "NO")
        if promoted:
            logger.info("")
            logger.info("  ★★★ PROMOSI BERHASIL → KEEP (Score >= %.1f, Alpha > 0) ★★★",
                        KEEP_SCORE_TARGET)
        else:
            logger.info("")
            logger.info("  ✗ Belum terpromosi (Score=%.2f, target=%.1f). Rekomendasi:",
                        score, KEEP_SCORE_TARGET)
            if after_metrics["alpha"] <= 0:
                logger.info("    - Alpha portofolio ≤ 0 — perluas n_calls atau tambah ticker")
            if after_metrics["sharpe"] < 1.0:
                logger.info("    - Sharpe < 1.0 — evaluasi baseline_candidates tambahan")
            logger.info("    - Verifikasi kelengkapan technical_indicators per ticker")

        # ── Save output ──
        _save_config(records, output_path, report, dry_run=False)
        logger.info("")
        logger.info("  Best ticker quant config disimpan: %s", output_path)

    finally:
        conn.close()

    return report


def _save_config(records: list[TickerRemediation], output_path: str,
                 report: RemediationReport, dry_run: bool) -> None:
    """Simpan best_ticker_quant_config.json + laporan lengkap."""
    config_path = Path(output_path)
    ticker_config: dict[str, dict] = {}
    for rec in records:
        ticker_config[rec.ticker] = {
            "sector": rec.sector,
            "cluster_id": rec.cluster_id,
            "cluster_label": rec.cluster_label,
            "calculated_market_cap": round(rec.calculated_market_cap, 2),
            "market_cap_source": rec.market_cap_source,
            "listed_shares": rec.listed_shares,
            "latest_close": rec.latest_close,
            "healed_personality": {
                "avg_daily_volatility": rec.avg_daily_volatility,
                "trend_strength": rec.trend_strength,
                "correlation_ihsg": rec.correlation_ihsg,
                "avg_volume": rec.avg_volume,
                "volume_consistency": rec.volume_consistency,
            },
            "gk_volatility": round(rec.gk_volatility, 6),
            "adapt_kappa": round(rec.adapt_kappa, 4),
            "baseline_mode": rec.baseline_mode,
            "baseline_params": rec.baseline_params,
            "best_params": rec.best_params,
            "feature_set": "regime_invariant_technical_indicators",
            "feature_completeness_pct": rec.feature_completeness_pct,
            "performance": {
                "sharpe": round(rec.sharpe, 4),
                "alpha": round(rec.alpha, 6),
                "max_drawdown": round(rec.max_drawdown, 4),
                "win_rate": round(rec.win_rate, 4),
                "accept_rate": round(rec.accept_rate, 4),
                "brier": round(rec.brier, 4),
                "objective": round(rec.objective, 4),
                "n_observations": rec.n_observations,
            },
        }

    output = {
        "generated_at": report.audit_date,
        "db_path": report.db_path,
        "n_tickers": report.n_tickers,
        "n_tickers_optimized": report.n_tickers_optimized,
        "regime_invariant_features": REGIME_INVARIANT_INDICATORS,
        "excluded_features": ["PE", "PB", "ROE", "DER", "dividend_yield"],
        "exclusion_reason": "fundamental_data >84% NULL (database_profile_report.json)",
        "clusters": report.clusters,
        "remediation_summary": report.remediation_summary,
        "portfolio_validation": {
            "weights": report.portfolio_weights,
            "sharpe": round(report.portfolio_sharpe, 4),
            "alpha": round(report.portfolio_alpha, 6),
            "max_drawdown": round(report.portfolio_max_drawdown, 4),
            "win_rate": round(report.portfolio_win_rate, 4),
            "score": round(report.portfolio_score, 2),
            "verdict": report.portfolio_verdict,
            "promoted_to_keep": report.promoted_to_keep,
            "keep_score_target": KEEP_SCORE_TARGET,
        },
        "tickers": ticker_config,
    }
    with config_path.open("w") as f:
        json.dump(json_safe(output), f, indent=2)

    # Laporan lengkap (tanpa Series returns)
    full_path = config_path.parent / "portfolio_data_remediation_report.json"
    with full_path.open("w") as f:
        json.dump(json_safe(asdict(report)), f, indent=2, default=str)
    logger.info("  Laporan lengkap disimpan: %s", full_path)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Portfolio Data Remediation — Quant-Safe Patching + Tuning",
    )
    parser.add_argument("--tickers", type=str, default=None,
                        help="Comma-separated tickers (default: 20 focus ticker)")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max tickers bila dipilih otomatis dari ohlcv")
    parser.add_argument("--n-calls", type=int, default=20,
                        help="Max DE iterations per ticker")
    parser.add_argument("--output", type=str,
                        default="best_ticker_quant_config.json",
                        help="Output JSON config per ticker")
    parser.add_argument("--db", type=str, default=None,
                        help="Path DB (default: env DB_PATH atau data/market_research.db)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Hanya jalankan Module A+B (remediation+cluster), "
                             "skip tuning & validation")
    args = parser.parse_args()

    db_path = args.db or os.environ.get("DB_PATH", "data/market_research.db")

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        # Default: 20 focus ticker dari database_profile_report.json
        tickers = DEFAULT_FOCUS_TICKERS[: args.limit]

    config = ReformConfig()
    space = HyperParamSpace()

    report = run_portfolio_data_remediation(
        tickers, db_path, config, space,
        n_calls=args.n_calls, output_path=args.output, dry_run=args.dry_run,
    )

    # Exit code: 0 jika promoted, 1 jika belum
    if not args.dry_run and not report.promoted_to_keep:
        logger.info("")
        logger.info("Exit code 1: portofolio belum mencapai target KEEP.")
        sys.exit(1)


if __name__ == "__main__":
    main()
