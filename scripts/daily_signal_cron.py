"""Daily Signal Cron — Sinyal Trading EOD Harian + Direct App Notification.

Skrip produksi harian yang membaca parameter model optimal dari
``best_ticker_quant_config.json`` (Single Source of Truth), menarik data
End-of-Day terbaru dari database asli, menjalankan generate_ticker_signals()
untuk 20 saham fokus, dan menyuntikkan keputusan trading hari ini
(BUY/SELL/HOLD + position sizing) langsung ke tabel ``app_notifications``
di database aplikasi — tanpa pihak ketiga (Telegram/dll).

Dirancang untuk dijalankan via cron job setiap hari bursa pukul 16:15 WIB
(09:15 UTC) setelah bursa IDX tutup perdagangan harian.

Pipeline 4 modul:

  MODULE 1 — Production Config Loader (Single Source of Truth)
      * Baca ``best_ticker_quant_config.json`` untuk best_params, baseline_mode,
        adapt_kappa per ticker.
      * Baca ``final_portfolio_verdict.json`` untuk portfolio_weights sebagai
        filter sekunder (responsivitas risiko adapt_kappa per ticker).
      * Verifikasi gate KEEP (Score >= 3.5 + Alpha > 0).

  MODULE 2 — Latest EOD Data Ingestion
      * Query tanggal bursa terakhir dari tabel ohlcv (time-bias safe:
        menggunakan max(timestamp) dari DB, bukan jam sistem).
      * Load OHLCV + technical_indicators untuk lookback window (default 300
        hari bursa) per ticker — cukup untuk training context signal generation.

  MODULE 3 — Live Signal Processing
      * Jalankan generate_ticker_signals() per ticker menggunakan parameter
        optimal dari config.
      * Ekstrak posisi hari terakhir → BUY (+1) / SELL (-1) / HOLD (0).
      * Hitung bobot Inverse-Variance 60 hari terakhir untuk position sizing.
      * Position sizing: unit = (PORTFOLIO_CAPITAL x portfolio_weight x
        |signal|) / latest_close, dibulatkan ke lot 100 saham IDX.

  MODULE 4 — Direct App Notification Injection
      * Buat tabel ``app_notifications`` jika belum ada (CREATE TABLE IF NOT
        EXISTS) dengan kolom: id, timestamp, title, body_json, status.
      * Insert payload JSON lengkap (sinyal + position sizing untuk 20 saham)
        agar backend aplikasi langsung membacanya sebagai notifikasi internal.
      * Tidak menggunakan Telegram atau pihak ketiga — murni DB injection.

Usage:
    # Jalankan manual (dry-run, tanpa insert DB):
    DB_PATH=data/market_research.db python scripts/daily_signal_cron.py --dry-run

    # Jalankan dengan notifikasi DB:
    DB_PATH=data/market_research.db python scripts/daily_signal_cron.py

    # Override config & modal:
    DB_PATH=data/market_research.db \\
    PORTFOLIO_CAPITAL=100000000 \\
    python scripts/daily_signal_cron.py \\
        --config best_ticker_quant_config.json \\
        --verdict final_portfolio_verdict.json

Crontab (crontab -e):
    # Jalankan setiap hari Senin-Jumat pukul 16:15 WIB (09:15 UTC)
    # IDX close 16:00 WIB, beri 15 menit untuk EOD data settlement
    15 9 * * 1-5 DB_PATH=/home/petrick/projects/market/data/market_research.db \\
        PORTFOLIO_CAPITAL=100000000 \\
        /home/petrick/projects/market/.venv/bin/python3 \\
        /home/petrick/projects/market/scripts/daily_signal_cron.py \\
        >> /home/petrick/projects/market/logs/daily_signal.log 2>&1

Requires: pandas, numpy, lightgbm
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Path setup (konsisten dengan portfolio_final_execution.py) ──────────────
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from alpha_rescue_pipeline import ReformConfig  # noqa: E402
from portfolio_data_remediation import (  # noqa: E402
    DEFAULT_FOCUS_TICKERS,
    KEEP_SCORE_TARGET,
    open_db,
)
from portfolio_final_execution import (  # noqa: E402
    build_baseline_candidate,
    build_config_from_ticker_params,
    generate_ticker_signals,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("daily_signal")

import warnings  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)


# ═══════════════════════════════════════════════════════════════════════════
# KONSTANTA
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_LOOKBACK_DAYS = 300


def load_ticker_strategies_from_db(
    conn: sqlite3.Connection,
    limit: int = 0,
) -> dict[str, str]:
    """Load best strategy per ticker from stock_personality table.

    Returns:
        {ticker: strategy_name} for all tickers with best_pattern filled.
        Strategy: 'donchian', 'rsi_meanrev', or 'ema_envelope'.
    """
    sql = (
        "SELECT ticker, best_pattern FROM stock_personality "
        "WHERE best_pattern IS NOT NULL ORDER BY ticker"
    )
    if limit > 0:
        sql += f" LIMIT {limit}"
    rows = conn.execute(sql).fetchall()
    return {r[0]: r[1] for r in rows}


def load_tickers_from_db(
    conn: sqlite3.Connection,
    limit: int = 0,
) -> list[str]:
    """Load ticker list from stock_personality (best_pattern IS NOT NULL).

    Falls back to DEFAULT_FOCUS_TICKERS if table empty.
    """
    sql = (
        "SELECT ticker FROM stock_personality "
        "WHERE best_pattern IS NOT NULL ORDER BY ticker"
    )
    if limit > 0:
        sql += f" LIMIT {limit}"
    rows = conn.execute(sql).fetchall()
    tickers = [r[0] for r in rows]
    if not tickers:
        logger.warning(
            "  stock_personality kosong — fallback ke DEFAULT_FOCUS_TICKERS (%d)",
            len(DEFAULT_FOCUS_TICKERS),
        )
        return DEFAULT_FOCUS_TICKERS
    return tickers


DEFAULT_PORTFOLIO_CAPITAL = 100_000_000  # 100 juta IDR

# WIB = UTC+7, jam tutup bursa IDX = 16:00 WIB = 09:00 UTC
IDX_CLOSE_WIB = "16:00"

# Inverse-Variance lookback untuk position sizing harian
IV_LOOKBACK_DAYS = 60


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TickerSignal:
    """Hasil sinyal trading harian untuk satu ticker."""
    ticker: str = ""
    signal_date: str = ""  # YYYY-MM-DD (tanggal bursa terakhir dari DB)
    signal: int = 0  # +1=BUY, -1=SELL, 0=HOLD
    signal_label: str = "HOLD"
    close_price: float = 0.0
    portfolio_weight: float = 0.0
    vol_60d: float = 0.0  # volatilitas 60 hari (annualized)
    adapt_kappa: float = 0.0
    baseline_mode: str = ""
    position_value_idr: float = 0.0  # nilai posisi dalam IDR
    unit_size: int = 0  # jumlah saham (lot 100 untuk IDX)
    unit_lots: int = 0  # jumlah lot (1 lot = 100 saham)
    n_train_rows: int = 0
    error: str = ""


@dataclass
class DailySignalReport:
    """Laporan sinyal harian untuk seluruh portofolio."""
    signal_date: str = ""
    execution_timestamp: str = ""
    verdict_path: str = ""
    db_path: str = ""
    portfolio_capital: float = 0.0
    keep_score: float = 0.0
    keep_verdict: str = ""
    promoted_to_keep: bool = False
    n_tickers: int = 0
    n_buy: int = 0
    n_sell: int = 0
    n_hold: int = 0
    n_errors: int = 0
    signals: list[TickerSignal] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 1 — PRODUCTION CONFIG LOADER
# ═══════════════════════════════════════════════════════════════════════════


def load_verdict_config(verdict_path: str) -> dict[str, Any]:
    """Muat final_portfolio_verdict.json dan validasi gate KEEP.

    Returns:
        Dict dengan keys:
          - score_card: {score, verdict, promoted_to_keep}
          - portfolio_weights: {ticker: weight}
          - tickers: list[dict] per-ticker results
          - portfolio_metrics: {sharpe, alpha, ...}
    """
    path = Path(verdict_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Verdict file tidak ditemukan: {path}. "
            "Jalankan portfolio_final_execution.py terlebih dahulu."
        )
    with path.open("r") as f:
        data = json.load(f)

    score_card = data.get("score_card", {})
    score = score_card.get("score", 0.0)
    verdict = score_card.get("verdict", "UNKNOWN")
    promoted = score_card.get("promoted_to_keep", False)

    logger.info("Verdict loaded: %s", path.name)
    logger.info("  Score: %.2f | Verdict: %s | KEEP: %s",
                score, verdict, promoted)

    if not promoted:
        logger.warning(
            "  ⚠ Portofolio belum lolos gate KEEP (Score >= %.1f + Alpha > 0). "
            "Sinyal tetap dihasilkan untuk monitoring, "
            "tapi eksekusi trading tidak disarankan.", KEEP_SCORE_TARGET,
        )

    return dict(data)


def extract_ticker_params(
    verdict_data: dict[str, Any],
    fallback_config_path: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Ekstrak parameter per-ticker dari verdict JSON.

    Verdict JSON berisi ``tickers`` list dengan field: ticker, adapt_kappa,
    baseline_mode, best_params, portfolio_weight, gk_volatility, dll.

    Jika best_params kosong di verdict (ticker di-skip saat eksekusi),
    fallback ke best_ticker_quant_config.json.

    Returns:
        {ticker: {adapt_kappa, baseline_mode, best_params, baseline_params,
                  portfolio_weight, gk_volatility, sector}}
    """
    # Build lookup dari verdict tickers list
    verdict_tickers: dict[str, dict[str, Any]] = {}
    for t in verdict_data.get("tickers", []):
        ticker = t.get("ticker", "")
        if ticker:
            verdict_tickers[ticker] = t

    # Portfolio weights dari top-level
    portfolio_weights = verdict_data.get("portfolio_weights", {})

    # Fallback config (best_ticker_quant_config.json)
    fallback_tickers: dict[str, dict[str, Any]] = {}
    if fallback_config_path:
        fb_path = Path(fallback_config_path)
        if fb_path.exists():
            with fb_path.open("r") as f:
                fb_data = json.load(f)
            fallback_tickers = fb_data.get("tickers", {})
            logger.info("  Fallback config loaded: %s (%d tickers)",
                        fb_path.name, len(fallback_tickers))

    result: dict[str, dict[str, Any]] = {}
    for ticker, vt in verdict_tickers.items():
        best_params = vt.get("best_params", {})
        baseline_params = {}

        # Fallback jika best_params kosong di verdict
        if not best_params and ticker in fallback_tickers:
            fb = fallback_tickers[ticker]
            best_params = fb.get("best_params", {})
            baseline_params = fb.get("baseline_params", {})
            adapt_kappa = fb.get("adapt_kappa", vt.get("adapt_kappa", 0.15))
            baseline_mode = fb.get("baseline_mode", vt.get("baseline_mode", "donchian"))
            gk_vol = fb.get("gk_volatility", vt.get("gk_volatility", 0.0))
            sector = fb.get("sector", vt.get("sector", "Unknown"))
        else:
            baseline_params = vt.get("baseline_params", {})
            adapt_kappa = vt.get("adapt_kappa", 0.15)
            baseline_mode = vt.get("baseline_mode", "donchian")
            gk_vol = vt.get("gk_volatility", 0.0)
            sector = vt.get("sector", "Unknown")

        result[ticker] = {
            "adapt_kappa": adapt_kappa,
            "baseline_mode": baseline_mode,
            "best_params": best_params,
            "baseline_params": baseline_params,
            "portfolio_weight": portfolio_weights.get(ticker, 0.0),
            "gk_volatility": gk_vol,
            "sector": sector,
        }

    # Tambah ticker dari fallback yang tidak ada di verdict
    for ticker, fb in fallback_tickers.items():
        if ticker not in result:
            result[ticker] = {
                "adapt_kappa": fb.get("adapt_kappa", 0.15),
                "baseline_mode": fb.get("baseline_mode", "donchian"),
                "best_params": fb.get("best_params", {}),
                "baseline_params": fb.get("baseline_params", {}),
                "portfolio_weight": portfolio_weights.get(ticker, 0.0),
                "gk_volatility": fb.get("gk_volatility", 0.0),
                "sector": fb.get("sector", "Unknown"),
            }

    return result


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 2 — LATEST EOD DATA INGESTION
# ═══════════════════════════════════════════════════════════════════════════


def get_latest_trading_date(
    conn: sqlite3.Connection, ticker: str | None = None,
) -> pd.Timestamp | None:
    """Ambil tanggal bursa terakhir dari DB (time-bias safe).

    Menggunakan MAX(timestamp) dari tabel ohlcv, BUKAN jam sistem.
    Jika ticker diberikan, ambil max date untuk ticker tersebut.
    Jika tidak, ambil max date global (untuk menentukan hari bursa terakhir).

    Returns:
        Timestamp tanggal terakhir, atau None jika DB kosong.
    """
    if ticker:
        sql = (
            "SELECT MAX(timestamp) FROM ohlcv "
            "WHERE ticker = ? AND timeframe = '1d'"
        )
        row = conn.execute(sql, (ticker,)).fetchone()
    else:
        sql = "SELECT MAX(timestamp) FROM ohlcv WHERE timeframe = '1d'"
        row = conn.execute(sql).fetchone()

    if not row or not row[0]:
        return None
    return pd.Timestamp(row[0])


def load_recent_ohlcv(
    conn: sqlite3.Connection,
    ticker: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """Muat OHLCV untuk lookback_days hari bursa terakhir per ticker.

    Lebih efisien daripada load_ohlcv_sqlite (load full history) untuk
    cron harian — hanya ambil N baris terakhir.

    Returns:
        DataFrame index=DatetimeIndex, kolom=open/high/low/close/volume.
    """
    sql = (
        "SELECT timestamp, open, high, low, close, volume "
        "FROM ohlcv WHERE ticker = ? AND timeframe = '1d' "
        "ORDER BY timestamp DESC LIMIT ?"
    )
    df = pd.read_sql_query(
        sql, conn, params=(ticker, lookback_days),
        parse_dates=["timestamp"],
    )
    if df.empty:
        return pd.DataFrame()
    df = df.sort_values("timestamp").set_index("timestamp")
    df = df[~df.index.duplicated(keep="last")]
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    return df


def load_recent_tech(
    conn: sqlite3.Connection,
    ticker: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    indicators: list[str] | None = None,
) -> pd.DataFrame:
    """Muat technical_indicators untuk lookback_days hari bursa terakhir.

    Pivot long-format → wide DataFrame, konsisten dengan
    load_technical_features_sqlite tapi dengan LIMIT untuk efisiensi cron.
    """
    from portfolio_data_remediation import REGIME_INVARIANT_INDICATORS
    if indicators is None:
        indicators = REGIME_INVARIANT_INDICATORS

    # Ambil max date untuk ticker ini, lalu hitung cutoff date di Python
    # (SQLite tidak mendukung syntax "? days")
    row = conn.execute(
        "SELECT MAX(date) FROM technical_indicators WHERE ticker = ?",
        (ticker,),
    ).fetchone()
    if not row or not row[0]:
        return pd.DataFrame()
    max_date = pd.Timestamp(row[0])
    cutoff_date = (max_date - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    placeholders = ",".join("?" for _ in indicators)
    sql = (
        f"SELECT date, indicator, value FROM technical_indicators "
        f"WHERE ticker = ? AND indicator IN ({placeholders}) "
        f"AND date >= ? "
        f"ORDER BY date"
    )
    params: tuple[Any, ...] = (ticker, *indicators, cutoff_date)
    df = pd.read_sql_query(sql, conn, params=params, parse_dates=["date"])
    if df.empty:
        return pd.DataFrame()

    wide = df.pivot_table(
        index="date", columns="indicator", values="value", aggfunc="first",
    )
    wide = wide.reindex(columns=indicators)
    wide.index = pd.DatetimeIndex(wide.index)
    return wide


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 3 — LIVE SIGNAL PROCESSING
# ═══════════════════════════════════════════════════════════════════════════


def compute_vol_60d(ohlcv: pd.DataFrame) -> float:
    """Hitung volatilitas 60 hari (annualized) dari return harian.

    Returns:
        Volatilitas annualized (stdev * sqrt(252)), atau 0.0 jika data kurang.
    """
    if len(ohlcv) < 20:
        return 0.0
    returns = ohlcv["close"].pct_change().dropna()
    if len(returns) < 20:
        return 0.0
    vol_daily = returns.tail(60).std()
    return float(vol_daily * np.sqrt(252))


def compute_daily_inverse_variance_weights(
    ohlcv_dict: dict[str, pd.DataFrame],
    lookback: int = IV_LOOKBACK_DAYS,
    max_weight: float = 0.20,
    var_epsilon: float = 1e-6,
) -> dict[str, float]:
    """Hitung bobot Inverse-Variance harian berbasis return 60 hari terakhir.

    w_i = (1/σ²_i) / Σ(1/σ²_j)

    Saham dengan variansi return rendah (stabil) mendapat bobot lebih besar.
    Saham dengan variansi tinggi (volatil) mendapat bobot lebih kecil.
    Ini adalah recomputasi harian dari bobot portofolio, tidak bergantung
    pada portfolio_weights statis dari verdict JSON.

    Safeguards:
    - Variance floor (epsilon) mencegah 1/0 = infinity.
    - Cap max weight per ticker (default 20%).
    - Fallback equal-weighting jika tidak ada ticker valid.

    Returns:
        {ticker: weight} — bobot normalisasi (sum=1.0)
    """
    variances: dict[str, float] = {}
    for ticker, ohlcv in ohlcv_dict.items():
        if ohlcv.empty or len(ohlcv) < 20:
            continue
        log_rets = np.log(ohlcv["close"].astype(float)).diff().dropna()
        if len(log_rets) < 20:
            continue
        recent_rets = log_rets.tail(lookback)
        var = max(float(np.var(recent_rets)), var_epsilon)
        variances[ticker] = var

    if not variances:
        n = len(ohlcv_dict)
        return {t: 1.0 / n for t in ohlcv_dict} if n > 0 else {}

    inv_var = {t: 1.0 / v for t, v in variances.items()}
    total = sum(inv_var.values())
    weights = {t: w / total for t, w in inv_var.items()}

    # Cap max weight per ticker
    weights = {t: min(w, max_weight) for t, w in weights.items()}
    # Renormalize
    total_w = sum(weights.values())
    if total_w > 0:
        weights = {t: w / total_w for t, w in weights.items()}

    # Pastikan ticker tanpa data tetap ada dengan weight=0
    for ticker in ohlcv_dict:
        if ticker not in weights:
            weights[ticker] = 0.0

    return weights


def signal_to_label(signal: float) -> tuple[int, str]:
    """Konversi nilai posisi ke label BUY/SELL/HOLD.

    Args:
        signal: nilai posisi (-1.0, 0.0, +1.0, atau fractional)

    Returns:
        (int_signal, label) — int_signal = +1/-1/0, label = "BUY"/"SELL"/"HOLD"
    """
    if signal > 0:
        return 1, "BUY"
    elif signal < 0:
        return -1, "SELL"
    return 0, "HOLD"


def compute_position_sizing(
    signal: int,
    portfolio_weight: float,
    close_price: float,
    capital: float,
) -> tuple[float, int, int]:
    """Hitung position sizing: nilai IDR, unit saham, dan lot.

    Formula (Weight x Capital / Price):
        position_value = capital x portfolio_weight x |signal|
        unit_size = floor(position_value / close_price)
        unit_lots = floor(unit_size / 100)  # IDX: 1 lot = 100 saham

    Returns:
        (position_value_idr, unit_size, unit_lots)
    """
    if signal == 0 or close_price <= 0 or portfolio_weight <= 0:
        return 0.0, 0, 0
    position_value = capital * portfolio_weight * abs(signal)
    unit_size = int(position_value / close_price)
    unit_lots = unit_size // 100  # IDX board lot = 100 shares
    return position_value, unit_size, unit_lots


def process_ticker_signal(
    ticker: str,
    ticker_params: dict[str, Any],
    ohlcv: pd.DataFrame,
    tech: pd.DataFrame,
    capital: float,
    signal_date: str,
) -> TickerSignal:
    """Jalankan generate_ticker_signals untuk satu ticker dan ekstrak sinyal hari terakhir.

    Returns:
        TickerSignal dengan keputusan trading final hari ini.
    """
    result = TickerSignal(
        ticker=ticker,
        signal_date=signal_date,
        adapt_kappa=ticker_params.get("adapt_kappa", 0.15),
        baseline_mode=ticker_params.get("baseline_mode", "donchian"),
        portfolio_weight=ticker_params.get("portfolio_weight", 0.0),
    )

    base_config = ReformConfig()
    best_params = ticker_params.get("best_params", {})

    # Build config dengan best_params ticker
    if best_params:
        config = build_config_from_ticker_params(base_config, ticker_params)
    else:
        config = base_config
        logger.warning("  %s — best_params kosong, menggunakan default config", ticker)

    baseline_candidate = build_baseline_candidate(ticker_params)
    adapt_kappa = ticker_params.get("adapt_kappa", 0.15)

    # Cek data minimum
    min_rows = config.min_train_samples + 50
    if ohlcv.empty or len(ohlcv) < min_rows:
        result.error = f"data tidak cukup ({len(ohlcv) if not ohlcv.empty else 0} < {min_rows})"
        return result

    result.n_train_rows = len(ohlcv)

    try:
        positions, _returns, _diag = generate_ticker_signals(
            ohlcv, config, baseline_candidate, tech, adapt_kappa,
        )
    except Exception as e:
        result.error = f"signal generation error: {e}"
        return result

    if positions.empty:
        result.error = "positions series kosong"
        return result

    # Ekstrak sinyal hari terakhir
    last_position = float(positions.iloc[-1])
    signal_int, label = signal_to_label(last_position)
    result.signal = signal_int
    result.signal_label = label

    # Close price hari terakhir
    result.close_price = float(ohlcv["close"].iloc[-1])

    # Volatilitas 60 hari
    result.vol_60d = compute_vol_60d(ohlcv)

    # Position sizing
    pos_val, units, lots = compute_position_sizing(
        signal_int, result.portfolio_weight, result.close_price, capital,
    )
    result.position_value_idr = pos_val
    result.unit_size = units
    result.unit_lots = lots

    return result


def run_daily_signal(
    tickers: list[str],
    db_path: str,
    verdict_path: str,
    fallback_config_path: str | None,
    capital: float,
    lookback_days: int,
) -> DailySignalReport:
    """Jalankan pipeline daily signal end-to-end.

    Alur:
      1. Load verdict config + extract per-ticker params.
      2. Tentukan tanggal bursa terakhir dari DB.
      3. Per ticker: load recent EOD → generate signals → extract today's signal.
      4. Aggregate ke DailySignalReport.
    """
    report = DailySignalReport(
        execution_timestamp=pd.Timestamp.now().isoformat(),
        verdict_path=verdict_path,
        db_path=db_path,
        portfolio_capital=capital,
    )

    logger.info("=" * 76)
    logger.info("DAILY SIGNAL CRON — EOD TRADING SIGNALS")
    logger.info("=" * 76)
    logger.info("DB: %s", db_path)
    logger.info("Verdict: %s", verdict_path)
    logger.info("Capital: Rp %s", f"{capital:,.0f}")
    logger.info("Lookback: %d hari bursa", lookback_days)
    logger.info("Tickers: %d", len(tickers))
    logger.info("")

    # ── MODULE 1: Load Config ──
    logger.info("MODULE 1 — Production Config Loader")
    logger.info("-" * 76)
    verdict_data = load_verdict_config(verdict_path)
    report.keep_score = verdict_data.get("score_card", {}).get("score", 0.0)
    report.keep_verdict = verdict_data.get("score_card", {}).get("verdict", "UNKNOWN")
    report.promoted_to_keep = verdict_data.get("score_card", {}).get("promoted_to_keep", False)

    ticker_params = extract_ticker_params(verdict_data, fallback_config_path)
    logger.info("  Ticker params extracted: %d", len(ticker_params))
    logger.info("")

    # ── MODULE 2: Latest EOD Data Ingestion ──
    logger.info("MODULE 2 — Latest EOD Data Ingestion")
    logger.info("-" * 76)

    conn = open_db(db_path)
    try:
        # Load per-ticker strategy from stock_personality (updated by weekly HRP cron)
        db_strategies = load_ticker_strategies_from_db(conn)
        logger.info("  Loaded %d ticker strategies from stock_personality", len(db_strategies))

        # Override baseline_mode with DB strategy if available
        # Map new HRP strategy names to old alpha_rescue_pipeline names
        STRATEGY_MAP = {
            "donchian": "donchian",
            "ema_envelope": "ema_env",
            "rsi_meanrev": "donchian",  # fallback — old pipeline has no RSI mean-reversion
        }
        for ticker, params in ticker_params.items():
            db_strat = db_strategies.get(ticker)
            if db_strat:
                params["baseline_mode"] = STRATEGY_MAP.get(db_strat, "donchian")
        strategy_counts = {}
        for p in ticker_params.values():
            s = p.get("baseline_mode", "donchian")
            strategy_counts[s] = strategy_counts.get(s, 0) + 1
        logger.info("  Strategy distribution: %s", strategy_counts)
        logger.info("")

        latest_date = get_latest_trading_date(conn)
        if latest_date is None:
            logger.error("  DB kosong — tidak ada data ohlcv.")
            return report

        report.signal_date = latest_date.strftime("%Y-%m-%d")
        logger.info("  Tanggal bursa terakhir: %s", report.signal_date)
        logger.info("")

        # ── Pre-pass: Load all OHLCV + compute daily IV weights ──
        logger.info("  Pre-pass: Loading OHLCV for IV weight computation...")
        ohlcv_cache: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            ohlcv_cache[ticker] = load_recent_ohlcv(conn, ticker, lookback_days)

        daily_iv_weights = compute_daily_inverse_variance_weights(ohlcv_cache)
        logger.info("  Daily IV weights computed (%d tickers, lookback=%d days)",
                    len(daily_iv_weights), IV_LOOKBACK_DAYS)
        for t, w in sorted(daily_iv_weights.items(), key=lambda x: -x[1])[:5]:
            logger.info("    %s: %.2f%%", t, w * 100)
        logger.info("")

        # ── MODULE 3: Live Signal Processing ──
        logger.info("MODULE 3 — Live Signal Processing")
        logger.info("-" * 76)

        for i, ticker in enumerate(tickers):
            t0 = time.time()
            params = ticker_params.get(ticker)

            if params is None:
                # Ticker tidak ada di verdict — gunakan default
                logger.warning("  [%2d/%d] %s — SKIP (tidak ada di verdict config)",
                               i + 1, len(tickers), ticker)
                report.signals.append(TickerSignal(
                    ticker=ticker, signal_date=report.signal_date,
                    error="tidak ada di verdict config",
                ))
                report.n_errors += 1
                continue

            ohlcv = ohlcv_cache.get(ticker)
            if ohlcv is None or ohlcv.empty:
                ohlcv = load_recent_ohlcv(conn, ticker, lookback_days)
            tech = load_recent_tech(conn, ticker, lookback_days)

            if ohlcv.empty:
                logger.warning("  [%2d/%d] %s — SKIP (ohlcv kosong)",
                               i + 1, len(tickers), ticker)
                report.signals.append(TickerSignal(
                    ticker=ticker, signal_date=report.signal_date,
                    error="ohlcv kosong",
                ))
                report.n_errors += 1
                continue

            # Override portfolio_weight dengan daily IV weight
            # Blend: 50% verdict weight (OOS-optimized) + 50% daily IV (fresh)
            verdict_w = params.get("portfolio_weight", 0.0)
            daily_w = daily_iv_weights.get(ticker, 0.0)
            blended_w = 0.5 * verdict_w + 0.5 * daily_w if verdict_w > 0 else daily_w
            params["portfolio_weight"] = blended_w

            sig = process_ticker_signal(
                ticker, params, ohlcv, tech, capital, report.signal_date,
            )
            report.signals.append(sig)

            # Count signals
            if sig.signal > 0:
                report.n_buy += 1
            elif sig.signal < 0:
                report.n_sell += 1
            else:
                report.n_hold += 1

            if sig.error:
                report.n_errors += 1
                logger.info("  [%2d/%d] %s — ERROR: %s (%.1fs)",
                            i + 1, len(tickers), ticker, sig.error,
                            time.time() - t0)
            else:
                logger.info(
                    "  [%2d/%d] %s | %-4s | Close=%-10.2f | W=%-5.2f%% | "
                    "Vol60=%-5.1f%% | Unit=%-6d (%d lot) | κ=%.3f | %s | %.1fs",
                    i + 1, len(tickers), ticker, sig.signal_label,
                    sig.close_price, sig.portfolio_weight * 100,
                    sig.vol_60d * 100, sig.unit_size, sig.unit_lots,
                    sig.adapt_kappa, sig.baseline_mode, time.time() - t0,
                )

            del tech

        report.n_tickers = len(report.signals)
        logger.info("")
        logger.info("  Summary: BUY=%d | SELL=%d | HOLD=%d | Errors=%d",
                    report.n_buy, report.n_sell, report.n_hold, report.n_errors)

    finally:
        conn.close()

    return report


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 4 — DIRECT APP NOTIFICATION INJECTION
# ═══════════════════════════════════════════════════════════════════════════


def ensure_app_notifications_table(conn: sqlite3.Connection) -> None:
    """Buat tabel app_notifications jika belum ada (CREATE TABLE IF NOT EXISTS).

    Schema:
        id          — Auto increment PK
        timestamp   — Waktu notifikasi dibuat (UTC ISO format)
        title       — Judul singkat notifikasi
        body_json   — Payload detail sinyal berformat JSON (BUY/SELL/HOLD + sizing)
        status      — Status baca: 'UNREAD' (default), 'READ'
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT NOT NULL,
            body_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'UNREAD'
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_app_notif_status
        ON app_notifications(status, timestamp DESC)
    """)
    conn.commit()


def build_notification_payload(report: DailySignalReport) -> dict:
    """Bangun payload JSON lengkap untuk notifikasi aplikasi.

    Struktur payload:
        {
          "signal_date": "2026-08-08",
          "generated_at": "2026-08-08T09:15:00Z",
          "keep_score": 4.19,
          "keep_verdict": "KEEP",
          "portfolio_capital": 100000000,
          "summary": {"buy": N, "sell": N, "hold": N, "errors": N},
          "signals": [
            {
              "ticker": "KPIG.JK",
              "action": "BUY",
              "signal": 1,
              "close_price": 2872.20,
              "portfolio_weight": 0.0232,
              "position_sizing": {
                "shares": 806,
                "lots": 8,
                "allocation_idr": 2314333.2
              },
              "vol_60d": 0.289,
              "adapt_kappa": 0.1516,
              "baseline_mode": "donchian",
              "error": null
            },
            ...
          ]
        }

    Returns:
        Dict siap di-serialisasi ke JSON dan di-insert ke app_notifications.
    """
    from datetime import datetime, timezone

    signals_payload = []
    for sig in report.signals:
        signals_payload.append({
            "ticker": sig.ticker,
            "action": sig.signal_label if not sig.error else "ERROR",
            "signal": sig.signal,
            "close_price": round(sig.close_price, 4) if sig.close_price else 0.0,
            "portfolio_weight": round(sig.portfolio_weight, 6),
            "position_sizing": {
                "shares": sig.unit_size,
                "lots": sig.unit_lots,
                "allocation_idr": round(sig.position_value_idr, 2),
            },
            "vol_60d": round(sig.vol_60d, 6),
            "adapt_kappa": round(sig.adapt_kappa, 4),
            "baseline_mode": sig.baseline_mode,
            "error": sig.error if sig.error else None,
        })

    return {
        "signal_date": report.signal_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keep_score": report.keep_score,
        "keep_verdict": report.keep_verdict,
        "promoted_to_keep": report.promoted_to_keep,
        "portfolio_capital": report.portfolio_capital,
        "summary": {
            "buy": report.n_buy,
            "sell": report.n_sell,
            "hold": report.n_hold,
            "errors": report.n_errors,
            "total_tickers": report.n_tickers,
        },
        "signals": signals_payload,
    }


def insert_app_notification(
    conn: sqlite3.Connection,
    report: DailySignalReport,
) -> int:
    """Insert notifikasi sinyal harian ke tabel app_notifications.

    Membuat tabel jika belum ada, lalu insert payload JSON lengkap.
    Backend aplikasi dapat membaca baris dengan status='UNREAD' dan
    menampilkannya sebagai notifikasi internal.

    Returns:
        id row yang baru di-insert, atau -1 jika gagal.
    """
    ensure_app_notifications_table(conn)

    payload = build_notification_payload(report)
    body_json = json.dumps(payload, indent=2, ensure_ascii=False, default=str)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    title = (
        f"Sinyal Harian {report.signal_date}: "
        f"{report.n_buy} BUY, {report.n_sell} SELL, {report.n_hold} HOLD"
    )

    cursor = conn.execute(
        "INSERT INTO app_notifications (timestamp, title, body_json, status) "
        "VALUES (?, ?, ?, 'UNREAD')",
        (now, title, body_json),
    )
    conn.commit()
    notif_id = cursor.lastrowid
    logger.info("  App notification inserted: id=%d, title='%s'", notif_id, title)
    return notif_id


def format_signal_table(report: DailySignalReport) -> str:
    """Format laporan sinyal harian sebagai tabel ringkas untuk konsol/log.

    Format tabel dengan: Ticker, Signal, Close, Weight, Unit, Lot, κ, Mode.
    Digunakan untuk output ke terminal dan file log (bukan Telegram).
    """
    lines: list[str] = []
    lines.append(f"Daily Signal — {report.signal_date}")
    lines.append("")
    lines.append(f"Capital: Rp {report.portfolio_capital:,.0f}")
    lines.append(
        f"KEEP Score: {report.keep_score:.2f} | Verdict: {report.keep_verdict}"
    )
    if not report.promoted_to_keep:
        lines.append("  [!] Belum lolos gate KEEP — monitoring only")
    lines.append("")
    lines.append(
        f"Summary: BUY={report.n_buy} | SELL={report.n_sell} | HOLD={report.n_hold}"
    )
    lines.append("")
    header = (
        f"{'Ticker':<10} {'Sig':<5} {'Close':>10} {'W%':>6} "
        f"{'Unit':>7} {'Lot':>5} {'k':>6} {'Mode':<10}"
    )
    lines.append(header)
    lines.append(
        f"{'-'*10} {'-'*5} {'-'*10} {'-'*6} "
        f"{'-'*7} {'-'*5} {'-'*6} {'-'*10}"
    )

    for sig in report.signals:
        if sig.error:
            lines.append(
                f"{sig.ticker:<10} {'ERR':<5} {'-':>10} {'-':>6} "
                f"{'-':>7} {'-':>5} {'-':>6} {sig.error[:10]}"
            )
            continue
        lines.append(
            f"{sig.ticker:<10} {sig.signal_label:<5} {sig.close_price:>10.2f} "
            f"{sig.portfolio_weight*100:>6.2f} {sig.unit_size:>7d} "
            f"{sig.unit_lots:>5d} {sig.adapt_kappa:>6.3f} "
            f"{sig.baseline_mode:<10}"
        )
    lines.append("")
    lines.append(f"{report.execution_timestamp}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# ENV LOADER
# ═══════════════════════════════════════════════════════════════════════════


def load_env(dotenv_path: str = ".env") -> None:
    """Muat .env file jika python-dotenv tersedia."""
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path)
    except ImportError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Daily Signal Cron — EOD Trading Signals + Direct App Notification",
    )
    parser.add_argument("--tickers", type=str, default=None,
                        help="Comma-separated tickers (default: 20 focus ticker)")
    parser.add_argument("--config", type=str,
                        default="best_ticker_quant_config.json",
                        help="Path ke best_ticker_quant_config.json (Single Source of Truth)")
    parser.add_argument("--verdict", type=str,
                        default="final_portfolio_verdict.json",
                        help="Path ke final_portfolio_verdict.json (filter sekunder)")
    parser.add_argument("--db", type=str, default=None,
                        help="Path DB (default: env DB_PATH atau data/market_research.db)")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help=f"Lookback hari bursa (default: {DEFAULT_LOOKBACK_DAYS})")
    parser.add_argument("--capital", type=float, default=None,
                        help="Modal portofolio IDR (default: env PORTFOLIO_CAPITAL)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Jangan insert ke app_notifications, hanya cetak ke konsol")
    parser.add_argument("--no-fallback", action="store_true",
                        help="Jangan baca best_ticker_quant_config.json fallback")
    args = parser.parse_args()

    # Load .env
    project_root = Path(__file__).resolve().parent.parent
    load_env(str(project_root / ".env"))

    # Resolve paths
    db_path = args.db or os.environ.get("DB_PATH", "data/market_research.db")
    capital = args.capital or float(
        os.environ.get("PORTFOLIO_CAPITAL", DEFAULT_PORTFOLIO_CAPITAL)
    )

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        # Load tickers from stock_personality (DB-driven, updated by weekly HRP cron)
        conn = sqlite3.connect(db_path)
        try:
            tickers = load_tickers_from_db(conn)
        finally:
            conn.close()
        logger.info("Loaded %d tickers from stock_personality (DB-driven)", len(tickers))

    fallback_config = None if args.no_fallback else args.config

    # Run pipeline (Modules 1-3)
    report = run_daily_signal(
        tickers, db_path, args.verdict, fallback_config, capital, args.lookback,
    )

    # Print table to console
    logger.info("")
    logger.info("FINAL SIGNAL TABLE")
    logger.info("=" * 76)
    print(format_signal_table(report))

    # Module 4: Direct App Notification (DB injection)
    if args.dry_run:
        logger.info("")
        logger.info("DRY RUN — App notification insertion dilewati.")
    else:
        conn = sqlite3.connect(db_path)
        try:
            notif_id = insert_app_notification(conn, report)
            if notif_id > 0:
                logger.info("  App notification inserted to app_notifications (id=%d)", notif_id)
            else:
                logger.warning("  App notification insertion gagal.")
        finally:
            conn.close()

    # Exit code
    if report.n_errors > 0:
        logger.warning("Selesai dengan %d error(s).", report.n_errors)
        sys.exit(1)


if __name__ == "__main__":
    main()
