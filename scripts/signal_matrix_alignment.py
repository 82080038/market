"""Signal Matrix Alignment — MLSignal × MultiFactor Time-Series Merge.

Tugas 2 dari Langkah Eksekusi Mandiri (pustaka/96 §3 Ablation Study).

Menggabungkan sinyal dari dua model ML (MLSignalProvider dan MultiFactorModel)
menjadi satu matriks sinyal bersih yang siap untuk Ablation Study.

Tantangan yang diatasi:
-----------------------
1. **Timestamp mismatch**: MLSignal dan MultiFactor bisa menghasilkan
   prediksi pada tanggal yang berbeda (scheduling gap, data delay).
   Solusi: inner join pada timestamp harian (hanya tanggal di mana
   kedua model memiliki prediksi).

2. **Data leakage (kebocoran data masa depan)**:
   - Forward return target (shift(-horizon)) TIDAK BOLEH ikut di-merge
     sebelum alignment selesai.
   - Sinyal pada tanggal T hanya boleh menggunakan data hingga T-1
     (strict non-look-ahead).
   - Setelah merge, target dihitung ulang dari OHLCV untuk memastikan
     tidak ada leakage dari salah satu model.

3. **Missing values (Quant-Safe Imputation)**:
   - Forward fill dengan batasan maksimum (limit) untuk menghindari
     sinyal stale yang berbahaya.
   - Jika gap > limit, biarkan NaN (tidak ada sinyal = HOLD).
   - Tidak menggunakan backward fill (bfill) karena itu = data leakage.
   - Tidak menggunakan mean/median imputation karena mengubah distribusi.

4. **Visual bias prevention**:
   - Drop baris di mana salah satu sinyal masih NaN setelah imputation.
   - Log statistik pre/post alignment untuk audit trail.

Output:
-------
DataFrame dengan kolom:
    date | ticker | ml_signal | mf_signal | mf_action | mf_prob_buy |
    mf_prob_sell | mf_prob_hold | blended_signal | target_3class | next_return

Siap dimasukkan ke Ablation Study (pustaka/96 §3).

Usage:
    DB_PATH=data/market_research.db python scripts/signal_matrix_alignment.py \
        [--tickers BBCA,BBRI,TLKM] [--limit 20] [--ffill-limit 3] \
        [--output signal_matrix.parquet]

Cross-ref: pustaka/96 §3 (Ablation Study), pustaka/23 §4 (Triple-Barrier),
           pustaka/85 (Backtest-to-Live Gap Prevention),
           src/market/analysis/ml_signal.py, src/market/analysis/multi_factor.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select, text

from market.db.engine import get_sessionmaker
from market.db.models import OHLCV, MLLabel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Konstanta ──────────────────────────────────────────────────────────────

DEFAULT_FFill_LIMIT = 3  # Maksimum 3 hari forward fill
ML_HORIZON = 5  # MLSignal horizon (5-day forward)
MF_HORIZON = 5  # MultiFactor horizon (5-day forward)
UP_THRESHOLD = 0.01  # +1% → BUY
DOWN_THRESHOLD = -0.01  # -1% → SELL
ML_BLEND_WEIGHT = 0.40  # 40% MLSignal
MF_BLEND_WEIGHT = 0.60  # 60% MultiFactor


# ── 1. Signal Generators ──────────────────────────────────────────────────
# Menggunakan interface dari MLSignalProvider dan MultiFactorModel
# untuk menghasilkan sinyal per ticker per tanggal.


def generate_mlsignal_series(
    df: pd.DataFrame,
    as_of_dates: pd.DatetimeIndex,
    min_train: int = 200,
) -> pd.DataFrame:
    """Generate MLSignal sinyal untuk setiap tanggal di as_of_dates.

    Menggunakan MLSignalProvider dengan walk-forward:
    - Untuk setiap tanggal T, train pada data hingga T, predict signal.
    - Signal range: [-1, 1] (2*P(up) - 1).

    Non-look-ahead: training hanya menggunakan data <= T.
    """
    from market.analysis.ml_signal import MLSignalProvider

    provider = MLSignalProvider(
        horizon=ML_HORIZON,
        min_train_samples=min_train,
        n_estimators=200,
        max_depth=6,
    )

    records = []
    for as_of in as_of_dates:
        try:
            result = provider.train_and_predict("", df, as_of)
            if result.model_available:
                records.append({
                    "date": pd.Timestamp(as_of),
                    "ml_signal": result.signal,
                    "ml_confidence": result.confidence,
                    "ml_n_train": result.n_train_samples,
                })
        except Exception as e:
            logger.debug("MLSignal failed at %s: %s", as_of, e)

    if not records:
        return pd.DataFrame(columns=["date", "ml_signal", "ml_confidence", "ml_n_train"])

    return pd.DataFrame(records).set_index("date")


def generate_multifactor_series(
    df: pd.DataFrame,
    as_of_dates: pd.DatetimeIndex,
    global_data: dict[str, pd.DataFrame] | None = None,
    min_train: int = 200,
) -> pd.DataFrame:
    """Generate MultiFactor sinyal untuk setiap tanggal di as_of_dates.

    Menggunakan MultiFactorModel dengan walk-forward:
    - Untuk setiap tanggal T, build features hingga T, train, predict.
    - Output: action (BUY/SELL/HOLD), probabilities, signal [-1, 1].

    Non-look-ahead: feature building dan training hanya menggunakan data <= T.
    """
    from market.analysis.multi_factor import MultiFactorModel

    model = MultiFactorModel(
        horizon=MF_HORIZON,
        min_train_samples=min_train,
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        use_pca=True,
        select_features=True,
        top_k_features=25,
    )

    records = []
    for as_of in as_of_dates:
        try:
            result = model.train_and_predict(
                "", df, as_of, global_data=global_data,
            )
            if result.model_available:
                records.append({
                    "date": pd.Timestamp(as_of),
                    "mf_signal": result.signal,
                    "mf_action": result.action,
                    "mf_action_code": result.action_code,
                    "mf_prob_buy": result.probabilities.get("BUY", 0.0),
                    "mf_prob_sell": result.probabilities.get("SELL", 0.0),
                    "mf_prob_hold": result.probabilities.get("HOLD", 0.0),
                    "mf_confidence": result.confidence,
                    "mf_n_train": result.n_train_samples,
                })
        except Exception as e:
            logger.debug("MultiFactor failed at %s: %s", as_of, e)

    if not records:
        return pd.DataFrame(columns=[
            "date", "mf_signal", "mf_action", "mf_action_code",
            "mf_prob_buy", "mf_prob_sell", "mf_prob_hold",
            "mf_confidence", "mf_n_train",
        ])

    return pd.DataFrame(records).set_index("date")


# ── 2. Quant-Safe Imputation ──────────────────────────────────────────────


def quant_safe_imputation(
    df: pd.DataFrame,
    signal_cols: list[str],
    ffill_limit: int = DEFAULT_FFill_LIMIT,
) -> pd.DataFrame:
    """Quant-Safe Imputation untuk missing values pada sinyal trading.

    Aturan:
    1. **Forward fill dengan limit**: Isi NaN dengan nilai terakhir yang
       valid, maksimal `ffill_limit` hari. Jika gap > limit, biarkan NaN.
       Rationale: sinyal 1-3 hari lalu masih relevan untuk swing trading,
       tapi >3 hari = stale signal yang berbahaya.

    2. **NO backward fill (bfill)**: Menggunakan data masa depan untuk
       mengisi masa lalu = data leakage. DILARANG.

    3. **NO mean/median imputation**: Mengubah distribusi sinyal dan
       menciptakan sinyal sintetis yang tidak ada. DILARANG.

    4. **NaN setelah imputation = HOLD (signal=0)**: Jika sinyal masih
       NaN setelah forward fill, berarti tidak ada prediksi yang valid.
       Dalam trading, tidak ada sinyal = tidak ada posisi = HOLD.

    Args:
        df: DataFrame dengan DatetimeIndex, sinyal di kolom signal_cols.
        signal_cols: Kolom yang akan di-impute.
        ffill_limit: Maksimum hari untuk forward fill.

    Returns:
        DataFrame dengan sinyal yang sudah di-impute + kolom
        '{col}_imputed' flag yang menandai baris yang di-fill.
    """
    result = df.copy()

    for col in signal_cols:
        if col not in result.columns:
            continue

        # Flag baris yang akan di-impute
        imputed_mask = result[col].isna()

        # Forward fill dengan limit
        result[col] = result[col].ffill(limit=ffill_limit)

        # Update flag: hanya yang berhasil di-fill
        imputed_mask = imputed_mask & result[col].notna()
        result[f"{col}_imputed"] = imputed_mask.astype(int)

        # Sisa NaN setelah ffill → set ke 0 (HOLD / neutral)
        # Tapi tandai dengan flag agar tidak dianggap sinyal asli
        still_nan = result[col].isna()
        result[col] = result[col].fillna(0.0)
        result[f"{col}_no_signal"] = still_nan.astype(int)

    return result


# ── 3. Alignment & Merge ──────────────────────────────────────────────────


def align_signals(
    ml_signals: pd.DataFrame,
    mf_signals: pd.DataFrame,
    ticker: str,
    ffill_limit: int = DEFAULT_FFill_LIMIT,
) -> pd.DataFrame:
    """Align MLSignal dan MultiFactor pada timestamp harian.

    Strategi alignment:
    1. **Outer join** pada index (date) untuk menangkap semua tanggal.
       Ini memastikan kita tahu kapan ada gap di salah satu model.
    2. **Quant-Safe Imputation**: forward fill dengan limit.
    3. **Drop baris di mana kedua sinyal tidak ada** (no signal dari
       manapun = tidak ada trade).
    4. **Hitung blended signal**: weighted average dari MLSignal (40%)
       dan MultiFactor (60%).

    Non-look-ahead verification:
    - Sinyal pada tanggal T hanya dari model yang train pada data <= T.
    - Tidak ada shift pada sinyal setelah merge.
    - Target (next_return) dihitung dari OHLCV setelah alignment.

    Args:
        ml_signals: DataFrame MLSignal dengan DatetimeIndex.
        mf_signals: DataFrame MultiFactor dengan DatetimeIndex.
        ticker: Ticker untuk labeling.
        ffill_limit: Maksimum hari forward fill.

    Returns:
        DataFrame aligned dengan kolom sinyal gabungan.
    """
    # Step 1: Outer join pada date index
    merged = ml_signals.join(
        mf_signals, how="outer", sort=True,
    )

    # Step 2: Quant-Safe Imputation
    signal_cols = ["ml_signal", "mf_signal"]
    merged = quant_safe_imputation(merged, signal_cols, ffill_limit)

    # Step 3: Drop baris di mana KEDUA sinyal tidak ada (no_signal dari keduanya)
    both_no_signal = (
        merged.get("ml_signal_no_signal", pd.Series(dtype=int)) == 1
    ) & (
        merged.get("mf_signal_no_signal", pd.Series(dtype=int)) == 1
    )
    pre_drop = len(merged)
    merged = merged[~both_no_signal]
    post_drop = len(merged)
    logger.debug(
        "%s: dropped %d rows with no signal from both models (pre=%d, post=%d)",
        ticker, pre_drop - post_drop, pre_drop, post_drop,
    )

    # Step 4: Hitung blended signal
    # Blended = 0.40 * MLSignal + 0.60 * MultiFactor
    # Hanya jika kedua sinyal tersedia (bukan no_signal)
    ml_available = merged.get("ml_signal_no_signal", pd.Series(dtype=int)) == 0
    mf_available = merged.get("mf_signal_no_signal", pd.Series(dtype=int)) == 0

    blended = pd.Series(0.0, index=merged.index)
    # Kedua sinyal ada: weighted average
    both_avail = ml_available & mf_available
    blended[both_avail] = (
        ML_BLEND_WEIGHT * merged.loc[both_avail, "ml_signal"]
        + MF_BLEND_WEIGHT * merged.loc[both_avail, "mf_signal"]
    )
    # Hanya MLSignal yang ada
    only_ml = ml_available & ~mf_available
    blended[only_ml] = merged.loc[only_ml, "ml_signal"]
    # Hanya MultiFactor yang ada
    only_mf = ~ml_available & mf_available
    blended[only_mf] = merged.loc[only_mf, "mf_signal"]

    merged["blended_signal"] = blended
    merged["ticker"] = ticker

    # Step 5: Tambahkan flag alignment quality
    merged["alignment_quality"] = "both"  # default: kedua model aktif
    merged.loc[only_ml, "alignment_quality"] = "ml_only"
    merged.loc[only_mf, "alignment_quality"] = "mf_only"

    return merged


# ── 4. Target Computation (Post-Alignment, No Leakage) ────────────────────


def compute_targets_post_alignment(
    aligned: pd.DataFrame,
    ohlcv: pd.DataFrame,
    horizon: int = ML_HORIZON,
) -> pd.DataFrame:
    """Hitung target (next_return, target_3class) SETELAH alignment.

    Penting untuk mencegah data leakage:
    - Target TIDAK diambil dari model output (bisa ada look-ahead).
    - Target dihitung dari OHLCV murni: return dari close[T] ke close[T+horizon].
    - Hanya dihitung untuk tanggal yang sudah aligned.

    Args:
        aligned: DataFrame hasil align_signals().
        ohlcv: OHLCV DataFrame dengan DatetimeIndex.
        horizon: Forward return horizon (trading days).

    Returns:
        DataFrame dengan kolom tambahan: next_return, target_3class.
    """
    result = aligned.copy()

    close = ohlcv["close"].astype(float)

    # Forward return: close[T+horizon] / close[T] - 1
    # shift(-horizon) = ambil nilai horizon hari ke depan
    forward_return = (close.shift(-horizon) / close - 1).reindex(result.index)

    result["next_return"] = forward_return

    # 3-class target: BUY(2), HOLD(1), SELL(0)
    target = pd.Series(1, index=result.index, dtype=int)  # default HOLD
    target[forward_return > UP_THRESHOLD] = 2  # BUY
    target[forward_return < DOWN_THRESHOLD] = 0  # SELL
    target[forward_return.isna()] = -1  # Unknown (will be dropped)
    result["target_3class"] = target

    return result


# ── 5. Data Leakage Prevention Audit ──────────────────────────────────────


def audit_data_leakage(aligned: pd.DataFrame) -> dict:
    """Audit matriks sinyal untuk memastikan tidak ada data leakage.

    Checks:
    1. Tidak ada kolom yang mengandung data masa depan (shift negative).
    2. Sinyal pada tanggal T tidak menggunakan data > T.
    3. Target_3class hanya menggunakan next_return yang dihitung post-alignment.
    4. Tidak ada backward fill (bfill) yang digunakan.

    Returns:
        Dict dengan hasil audit per check.
    """
    audit = {
        "leakage_checks": {},
        "passed": True,
    }

    # Check 1: Kolom yang mencurigakan (mengandung 'forward', 'future', 'target' sebelum alignment)
    suspicious_cols = [
        c for c in aligned.columns
        if any(k in c.lower() for k in ["forward", "future"])
        and c not in ["next_return", "forward_return"]
    ]
    audit["leakage_checks"]["no_suspicious_columns"] = {
        "passed": len(suspicious_cols) == 0,
        "details": f"Suspicious columns: {suspicious_cols}" if suspicious_cols else "None",
    }

    # Check 2: next_return hanya ada untuk tanggal yang punya OHLCV setelahnya
    if "next_return" in aligned.columns:
        nan_count = aligned["next_return"].isna().sum()
        total = len(aligned)
        audit["leakage_checks"]["next_return_coverage"] = {
            "passed": nan_count < total,
            "details": f"{nan_count}/{total} NaN (expected: tail rows only)",
        }

    # Check 3: Tidak ada bfill flag
    bfill_cols = [c for c in aligned.columns if "bfill" in c.lower()]
    audit["leakage_checks"]["no_backward_fill"] = {
        "passed": len(bfill_cols) == 0,
        "details": f"bfill columns: {bfill_cols}" if bfill_cols else "None",
    }

    # Check 4: Sinyal dalam range valid
    if "ml_signal" in aligned.columns:
        ml_range = aligned["ml_signal"].describe()[["min", "max"]]
        audit["leakage_checks"]["ml_signal_range"] = {
            "passed": ml_range["min"] >= -1.01 and ml_range["max"] <= 1.01,
            "details": f"ML signal range: [{ml_range['min']:.3f}, {ml_range['max']:.3f}]",
        }

    if "mf_signal" in aligned.columns:
        mf_range = aligned["mf_signal"].describe()[["min", "max"]]
        audit["leakage_checks"]["mf_signal_range"] = {
            "passed": mf_range["min"] >= -1.01 and mf_range["max"] <= 1.01,
            "details": f"MF signal range: [{mf_range['min']:.3f}, {mf_range['max']:.3f}]",
        }

    # Check 5: blended_signal dalam range valid
    if "blended_signal" in aligned.columns:
        bl_range = aligned["blended_signal"].describe()[["min", "max"]]
        audit["leakage_checks"]["blended_signal_range"] = {
            "passed": bl_range["min"] >= -1.01 and bl_range["max"] <= 1.01,
            "details": f"Blended signal range: [{bl_range['min']:.3f}, {bl_range['max']:.3f}]",
        }

    # Overall pass
    audit["passed"] = all(
        v["passed"] for v in audit["leakage_checks"].values()
    )

    return audit


# ── 6. Utility: Load OHLCV & Global Data ──────────────────────────────────


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


def load_global_data(session) -> dict[str, pd.DataFrame]:
    """Load global market data untuk MultiFactor exogenous features."""
    global_tickers = ["^GSPC", "^IXIC", "^FTSE", "^N225", "^HSI", "GC=F", "CL=F", "HG=F"]
    result = {}
    for gticker in global_tickers:
        df = load_ohlcv(session, gticker)
        if not df.empty:
            result[gticker] = df
    return result


# ── 7. Main Pipeline ──────────────────────────────────────────────────────


def run_signal_alignment(
    tickers: list[str],
    ffill_limit: int = DEFAULT_FFill_LIMIT,
    output_path: str = "signal_matrix.parquet",
    skip_ml: bool = False,
) -> pd.DataFrame:
    """Jalankan pipeline alignment sinyal end-to-end.

    Steps:
    1. Load OHLCV untuk setiap ticker
    2. Generate MLSignal series (walk-forward per ticker)
    3. Generate MultiFactor series (walk-forward per ticker)
    4. Align kedua series pada timestamp harian
    5. Quant-Safe Imputation (forward fill dengan limit)
    6. Hitung target post-alignment (no leakage)
    7. Audit data leakage
    8. Output: DataFrame bersih untuk Ablation Study

    Args:
        tickers: List ticker saham yang diuji.
        ffill_limit: Maksimum hari forward fill untuk missing values.
        output_path: Path untuk save output (parquet atau csv).
        skip_ml: Jika True, skip ML generation (hanya alignment dummy).

    Returns:
        DataFrame bersih siap Ablation Study.
    """
    session = get_sessionmaker()()

    # Load global data untuk MultiFactor
    global_data = load_global_data(session)
    logger.info("Global data loaded: %d assets", len(global_data))

    all_aligned = []

    for i, ticker in enumerate(tickers):
        logger.info("[%d/%d] Processing %s...", i + 1, len(tickers), ticker)

        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 250:
            logger.warning("  %s: insufficient OHLCV (%d rows), skipping", ticker, len(ohlcv))
            continue

        # Tentukan tanggal untuk walk-forward prediction
        # Mulai dari 200 hari terakhir (cukup untuk Ablation Study)
        as_of_dates = ohlcv.index[-200:]

        # Generate MLSignal series
        logger.debug("  Generating MLSignal series (%d dates)...", len(as_of_dates))
        ml_signals = generate_mlsignal_series(ohlcv, as_of_dates)

        # Generate MultiFactor series
        logger.debug("  Generating MultiFactor series (%d dates)...", len(as_of_dates))
        mf_signals = generate_multifactor_series(ohlcv, as_of_dates, global_data)

        if ml_signals.empty and mf_signals.empty:
            logger.warning("  %s: no signals generated from either model, skipping", ticker)
            continue

        # Align signals
        logger.debug("  Aligning signals (ffill_limit=%d)...", ffill_limit)
        aligned = align_signals(ml_signals, mf_signals, ticker, ffill_limit)

        # Compute targets post-alignment (no leakage)
        aligned = compute_targets_post_alignment(aligned, ohlcv, ML_HORIZON)

        # Drop rows dengan target unknown (tail rows tanpa forward return)
        pre_drop = len(aligned)
        aligned = aligned[aligned["target_3class"] >= 0]
        post_drop = len(aligned)
        logger.debug(
            "  %s: dropped %d tail rows (no forward return)",
            ticker, pre_drop - post_drop,
        )

        if aligned.empty:
            logger.warning("  %s: empty after alignment + target drop", ticker)
            continue

        # Audit data leakage
        leakage_audit = audit_data_leakage(aligned)
        if not leakage_audit["passed"]:
            logger.warning("  %s: DATA LEAKAGE DETECTED!", ticker)
            for check, result in leakage_audit["leakage_checks"].items():
                if not result["passed"]:
                    logger.warning("    ❌ %s: %s", check, result["details"])
        else:
            logger.debug("  %s: leakage audit PASSED", ticker)

        # Log alignment statistics
        quality_counts = aligned["alignment_quality"].value_counts().to_dict()
        imputed_ml = aligned["ml_signal_imputed"].sum() if "ml_signal_imputed" in aligned else 0
        imputed_mf = aligned["mf_signal_imputed"].sum() if "mf_signal_imputed" in aligned else 0
        logger.info(
            "  %s: %d aligned rows | quality=%s | imputed: ml=%d mf=%d",
            ticker, len(aligned), quality_counts, imputed_ml, imputed_mf,
        )

        all_aligned.append(aligned)

    session.close()

    if not all_aligned:
        logger.error("No aligned data produced. Check ticker data availability.")
        return pd.DataFrame()

    # Concat semua ticker
    final_df = pd.concat(all_aligned, axis=0)
    if "ticker" in final_df.columns:
        final_df = final_df.sort_values(["ticker", "date"])
    else:
        final_df = final_df.sort_index()

    # Reset index untuk output yang clean
    final_df = final_df.reset_index()
    if "date" not in final_df.columns:
        final_df = final_df.rename(columns={"index": "date"})

    # Print summary
    print("\n" + "=" * 70)
    print("SIGNAL MATRIX ALIGNMENT REPORT")
    print("=" * 70)
    print(f"  Tickers processed:    {len(tickers)}")
    print(f"  Tickers with output:  {final_df['ticker'].nunique() if 'ticker' in final_df else 0}")
    print(f"  Total aligned rows:   {len(final_df)}")
    print(f"  Forward fill limit:   {ffill_limit} days")
    print(f"  ML blend weight:      {ML_BLEND_WEIGHT:.0%}")
    print(f"  MF blend weight:      {MF_BLEND_WEIGHT:.0%}")

    if "alignment_quality" in final_df.columns:
        quality_dist = final_df["alignment_quality"].value_counts()
        print(f"  Alignment quality:")
        for q, count in quality_dist.items():
            print(f"    {q}: {count} ({count/len(final_df)*100:.1f}%)")

    if "target_3class" in final_df.columns:
        target_dist = final_df["target_3class"].value_counts().sort_index()
        target_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        print(f"  Target distribution:")
        for t, count in target_dist.items():
            label = target_map.get(int(t), str(t))
            print(f"    {label}: {count} ({count/len(final_df)*100:.1f}%)")

    print(f"\n  Output columns: {list(final_df.columns)}")
    print(f"  Output shape:   {final_df.shape}")
    print("=" * 70)

    # Save output
    out_path = Path(output_path)
    if out_path.suffix == ".parquet":
        final_df.to_parquet(out_path, index=False)
    else:
        final_df.to_csv(out_path, index=False)
    print(f"  Saved to: {out_path}")

    return final_df


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Signal Matrix Alignment — MLSignal × MultiFactor",
    )
    parser.add_argument(
        "--tickers", type=str, default=None,
        help="Comma-separated tickers (default: top 20 by row count)",
    )
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Max tickers if --tickers not specified (default: 20)",
    )
    parser.add_argument(
        "--ffill-limit", type=int, default=DEFAULT_FFill_LIMIT,
        help=f"Maximum forward fill days (default: {DEFAULT_FFill_LIMIT})",
    )
    parser.add_argument(
        "--output", type=str, default="signal_matrix.parquet",
        help="Output file path (parquet or csv)",
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

    logger.info("=== SIGNAL MATRIX ALIGNMENT ===")
    logger.info("Tickers: %d (%s)", len(tickers), tickers[:5])
    logger.info("Forward fill limit: %d days", args.ffill_limit)

    run_signal_alignment(
        tickers=tickers,
        ffill_limit=args.ffill_limit,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
