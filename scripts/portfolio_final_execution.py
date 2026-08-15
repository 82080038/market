"""Portfolio Final Execution — Walk-Forward OOS Evaluation & KEEP Verdict.

Skrip orkestrasi trading final yang memuat parameter optimal per ticker hasil
``portfolio_data_remediation.py``, menjalankan simulasi walk-forward out-of-sample
(Jan 2024 – Aug 2026) pada 20 saham fokus, menggabungkan sinyal individual menjadi
portofolio global dengan Inverse-Variance Weighting harian, dan memverifikasi
apakah portofolio multi-ticker menembus target KEEP (Score ≥ 3.5) dengan Alpha
gabungan positif.

Pipeline 4 modul:

  MODULE 1 — Load Ticker-Specific Parameters
      * Baca ``best_ticker_quant_config.json`` (output portfolio_data_remediation).
      * Ekstrak adapt_kappa, baseline_mode, best_params, cluster info per ticker.

  MODULE 2 — Signal Generation + Inverse-Variance Weighting
      * Per ticker: bangun sinyal vol-targeted + meta-labeled regime-invariant.
      * Hitung return strategi per ticker pada periode OOS.
      * Gabungkan via Inverse-Variance Weighting harian (bobot ∝ 1/variance).

  MODULE 3 — Walk-Forward OOS Performance Re-Evaluation
      * Filter periode Jan 2024 – Aug 2026 (out-of-sample blind period).
      * Hitung Sharpe, Sortino, Alpha, Max Drawdown, Win Rate via
        ``audit_ai_utility.compute_performance_metrics``.
      * Bandingkan vs baseline (MA crossover + RSI) per ticker.

  MODULE 4 — Final KEEP Target Verification
      * Score Card via ``audit_ai_advanced.compute_component_score_card``.
      * Cetak laporan komprehensif di konsol.
      * Simpan verdict ke ``final_portfolio_verdict.json``.

Usage:
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market python scripts/portfolio_final_execution.py \
        [--config best_ticker_quant_config.json] \
        [--output final_portfolio_verdict.json] \
        [--oos-start 2024-01-01] [--oos-end 2026-08-31]

Requires: scipy, pandas, numpy, lightgbm
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

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
from alpha_rescue_pipeline import ReformConfig  # noqa: E402
from alpha_hyper_tuner import (  # noqa: E402
    HyperParamSpace,
    generate_robust_trend_baseline,
    compute_adaptive_threshold,
    _build_config_from_params,
    _generate_vol_targeted_with_baseline,
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
from portfolio_data_remediation import (  # noqa: E402
    DEFAULT_FOCUS_TICKERS,
    REGIME_INVARIANT_INDICATORS,
    KEEP_SCORE_TARGET,
    open_db,
    json_safe,
    load_ohlcv_sqlite,
    load_benchmark_sqlite,
    load_technical_features_sqlite,
    build_regime_invariant_features,
    _generate_regime_invariant_meta_signals,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("final_execution")

import warnings  # noqa: E402
warnings.filterwarnings("ignore", category=FutureWarning)


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TickerExecution:
    """Hasil eksekusi final untuk satu ticker pada periode OOS."""
    ticker: str = ""
    sector: str = ""
    cluster_id: int = -1
    cluster_label: str = ""
    adapt_kappa: float = 0.15
    gk_volatility: float = 0.0
    baseline_mode: str = "donchian"
    best_params: dict = field(default_factory=dict)
    # OOS metrics
    oos_sharpe: float = 0.0
    oos_sortino: float = 0.0
    oos_alpha: float = 0.0
    oos_max_drawdown: float = 0.0
    oos_win_rate: float = 0.0
    oos_total_return: float = 0.0
    oos_n_trades: int = 0
    oos_returns: pd.Series | None = None
    # Baseline comparison
    baseline_sharpe: float = 0.0
    baseline_alpha: float = 0.0
    # Portfolio weight
    portfolio_weight: float = 0.0


@dataclass
class FinalVerdictReport:
    """Laporan verdict final portofolio."""
    execution_date: str = ""
    config_path: str = ""
    db_path: str = ""
    oos_start: str = ""
    oos_end: str = ""
    n_tickers: int = 0
    n_tickers_executed: int = 0
    # Portfolio metrics
    portfolio_sharpe: float = 0.0
    portfolio_sortino: float = 0.0
    portfolio_alpha: float = 0.0
    portfolio_max_drawdown: float = 0.0
    portfolio_win_rate: float = 0.0
    portfolio_total_return: float = 0.0
    portfolio_calmar: float = 0.0
    portfolio_information_ratio: float = 0.0
    # Score card
    portfolio_score: float = 0.0
    portfolio_verdict: str = ""
    promoted_to_keep: bool = False
    # Significance
    p_value_paired_ttest: float = 1.0
    p_value_diebold_mariano: float = 1.0
    p_value_whites_rc: float = 1.0
    # Weights
    portfolio_weights: dict = field(default_factory=dict)
    # Per-ticker
    ticker_results: list[dict] = field(default_factory=list)
    # Baseline portfolio (for comparison)
    baseline_portfolio_sharpe: float = 0.0
    baseline_portfolio_alpha: float = 0.0
    baseline_portfolio_max_drawdown: float = 0.0
    # Delta
    delta_sharpe: float = 0.0
    delta_alpha: float = 0.0
    # Daily returns (untuk visualisasi equity curve & drawdown)
    daily_portfolio_returns: dict = field(default_factory=dict)
    daily_baseline_returns: dict = field(default_factory=dict)
    daily_benchmark_returns: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 1 — LOAD TICKER-SPECIFIC PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════


def load_ticker_config(config_path: str) -> dict[str, dict]:
    """Muat konfigurasi parameter optimal per ticker dari best_ticker_quant_config.json.

    Returns:
        {ticker: {sector, cluster_id, cluster_label, adapt_kappa, gk_volatility,
                  baseline_mode, baseline_params, best_params, ...}}
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config tidak ditemukan: {path}. "
            "Jalankan portfolio_data_remediation.py terlebih dahulu."
        )
    with path.open("r") as f:
        data = json.load(f)
    tickers_section = data.get("tickers", data)
    if not tickers_section:
        raise ValueError(f"Tidak ada ticker config di {path}")
    logger.info("Config loaded: %s (%d tickers)", path.name, len(tickers_section))
    return tickers_section


def build_config_from_ticker_params(
    base_config: ReformConfig,
    ticker_cfg: dict,
) -> ReformConfig:
    """Bangun ReformConfig dengan best_params ticker di-override."""
    best_params = ticker_cfg.get("best_params", {})
    baseline_mode = ticker_cfg.get("baseline_mode", "donchian")
    if best_params:
        return _build_config_from_params(base_config, best_params, baseline_mode)
    return base_config


def build_baseline_candidate(ticker_cfg: dict) -> dict:
    """Ekstrak baseline candidate dict dari ticker config."""
    mode = ticker_cfg.get("baseline_mode", "donchian")
    baseline_params = ticker_cfg.get("baseline_params", {})
    candidate = {"mode": mode}
    candidate.update(baseline_params)
    return candidate


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 2 — SIGNAL GENERATION + INVERSE-VARIANCE WEIGHTING
# ═══════════════════════════════════════════════════════════════════════════


def generate_ticker_signals(
    ohlcv: pd.DataFrame,
    config: ReformConfig,
    baseline_candidate: dict,
    tech_features: pd.DataFrame,
    adapt_kappa: float,
) -> tuple[pd.Series, pd.Series, dict]:
    """Hasilkan sinyal perdagangan final untuk satu ticker.

    Pipeline: vol-targeted baseline → regime-invariant meta-labeling → positions.

    Returns:
        (positions, strategy_returns, diagnostics)
    """
    if ohlcv.empty or len(ohlcv) < config.min_train_samples + 50:
        return (
            pd.Series(0.0, index=ohlcv.index),
            pd.Series(dtype=float),
            {"n_predictions": 0, "accept_rate": 0.0, "brier": 1.0},
        )

    # Vol-targeted positions
    vol_positions, vol_diag = _generate_vol_targeted_with_baseline_ticker(
        ohlcv, config, baseline_candidate,
    )

    # Regime-invariant meta-labeling
    feat_df = build_regime_invariant_features(ohlcv, tech_features)
    rescued, meta_diag = _generate_regime_invariant_meta_signals(
        ohlcv, vol_positions, config, feat_df, adapt_kappa=adapt_kappa,
    )

    # Convert to discrete positions
    positions = convert_signal_to_position(rescued, config.signal_threshold)
    returns = simulate_strategy_returns(ohlcv, positions)

    diag = {
        "n_predictions": meta_diag.get("n_predictions", 0),
        "accept_rate": meta_diag.get("accept_rate", 0.0),
        "brier": meta_diag.get("brier", 1.0),
    }
    return positions, returns, diag


def generate_baseline_ticker_signals(
    ohlcv: pd.DataFrame,
) -> pd.Series:
    """Hasilkan sinyal baseline (MA crossover + RSI) untuk perbandingan."""
    baseline_signals = generate_baseline_signals(ohlcv)
    return simulate_strategy_returns(ohlcv, baseline_signals)


def compute_daily_inverse_variance_weights(
    returns_dict: dict[str, pd.Series],
    oos_start: pd.Timestamp,
    oos_end: pd.Timestamp,
    max_weight: float = 0.20,
    var_epsilon: float = 1e-6,
    min_accept_rate: float = 0.05,
) -> dict[str, pd.Series]:
    """Hitung bobot Inverse-Variance harian yang beradaptasi setiap hari.

    Bobot alokasi otomatis mengecil pada saham volatil (variance tinggi)
    dan membesar pada saham stabil (variance rendah).

    Safeguards against weighting collapse:
    - Filter ticker dengan accept_rate < min_accept_rate (return konstan nol).
    - Variance floor (epsilon) mencegah 1/0 = infinity.
    - Cap max weight per ticker (default 20%).
    - Fallback equal-weighting jika hanya 0-1 ticker yang lolos filter.

    Returns:
        {ticker: weight_series} — bobot harian yang sum=1 per tanggal.
    """
    if not returns_dict:
        return {}

    # Filter ke periode OOS + filter ticker dengan return konstan (accept_rate ~ 0)
    filtered = {}
    for ticker, rets in returns_dict.items():
        oos_rets = rets.loc[
            (rets.index >= oos_start) & (rets.index <= oos_end)
        ]
        if len(oos_rets) == 0:
            continue
        # Hitung accept rate: proporsi hari dengan return != 0
        accept_rate = float((oos_rets != 0.0).sum()) / len(oos_rets)
        if accept_rate < min_accept_rate:
            logger.warning(
                "  Skipping %s from IV weighting: accept_rate=%.4f < %.4f",
                ticker, accept_rate, min_accept_rate,
            )
            continue
        filtered[ticker] = oos_rets

    # Fallback: jika 0-1 ticker lolos filter, gunakan equal weight dari semua ticker
    if len(filtered) <= 1:
        logger.warning(
            "  Only %d ticker(s) passed accept_rate filter — "
            "falling back to equal-weighting across all tickers.",
            len(filtered),
        )
        all_tickers = list(returns_dict.keys())
        if not all_tickers:
            return {}
        all_dates = sorted(set().union(*(
            r.loc[(r.index >= oos_start) & (r.index <= oos_end)].index
            for r in returns_dict.values()
        )))
        if not all_dates:
            return {}
        eq_weight = 1.0 / len(all_tickers)
        return {
            ticker: pd.Series(eq_weight, index=all_dates)
            for ticker in all_tickers
        }

    # Union semua tanggal
    all_dates = sorted(set().union(*(r.index for r in filtered.values())))
    if not all_dates:
        return {}

    # Rolling 60-day variance untuk adaptive weighting
    lookback = 60
    df = pd.DataFrame(filtered)
    df = df.reindex(all_dates).fillna(0.0)

    rolling_var = df.rolling(lookback, min_periods=20).var()
    # Variance floor: mencegah 1/0 = infinity
    rolling_var = rolling_var.clip(lower=var_epsilon)
    rolling_var = rolling_var.replace(0, np.nan).ffill().fillna(var_epsilon)

    # Inverse variance
    inv_var = 1.0 / rolling_var
    row_sums = inv_var.sum(axis=1).replace(0, 1.0)
    weights_df = inv_var.div(row_sums, axis=0)

    # Cap max weight per ticker — iterative cap+redistribute
    for _ in range(20):
        capped = weights_df.clip(upper=max_weight)
        excess = (weights_df - capped).sum(axis=1)
        if (excess.abs() < 1e-9).all():
            weights_df = capped
            break
        weights_df = capped.copy()
        # Redistribute excess to uncapped tickers
        uncapped_mask = weights_df < max_weight
        uncapped_total = weights_df.where(uncapped_mask, 0).sum(axis=1).replace(0, 1.0)
        for col in weights_df.columns:
            mask = uncapped_mask[col]
            weights_df.loc[mask, col] = weights_df.loc[mask, col] + excess.loc[mask] * (
                weights_df.loc[mask, col] / uncapped_total.loc[mask]
            )
    # Final hard clip + renormalize
    weights_df = weights_df.clip(upper=max_weight)
    row_sums = weights_df.sum(axis=1).replace(0, 1.0)
    weights_df = weights_df.div(row_sums, axis=0)

    return {ticker: weights_df[ticker] for ticker in weights_df.columns}


def compute_weighted_portfolio_returns(
    returns_dict: dict[str, pd.Series],
    weights_dict: dict[str, pd.Series],
) -> pd.Series:
    """Hitung return portofolio harian dengan bobot yang berubah setiap hari.

    Args:
        returns_dict: {ticker: daily_returns}
        weights_dict: {ticker: daily_weights} (sum=1 per tanggal)

    Returns:
        Series return portofolio harian.
    """
    if not returns_dict or not weights_dict:
        return pd.Series(dtype=float)

    tickers = list(returns_dict.keys())
    all_dates = sorted(set().union(*(r.index for r in returns_dict.values())))
    portfolio = pd.Series(0.0, index=all_dates)

    for ticker in tickers:
        rets = returns_dict[ticker].reindex(all_dates).fillna(0.0)
        weights = weights_dict.get(ticker)
        if weights is not None:
            weights = weights.reindex(all_dates).fillna(0.0)
            portfolio += rets * weights

    return portfolio


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 3 — WALK-FORWARD OOS PERFORMANCE RE-EVALUATION
# ═══════════════════════════════════════════════════════════════════════════


def evaluate_oos_ticker(
    ohlcv: pd.DataFrame,
    benchmark: pd.Series | None,
    config: ReformConfig,
    baseline_candidate: dict,
    tech_features: pd.DataFrame,
    adapt_kappa: float,
    oos_start: pd.Timestamp,
    oos_end: pd.Timestamp,
) -> tuple[TickerExecution, pd.Series, pd.Series]:
    """Evaluasi satu ticker pada periode OOS.

    Returns:
        (TickerExecution, oos_strategy_returns, oos_baseline_returns)
    """
    positions, strategy_returns, diag = generate_ticker_signals(
        ohlcv, config, baseline_candidate, tech_features, adapt_kappa,
    )
    baseline_returns = generate_baseline_ticker_signals(ohlcv)

    # Filter ke OOS period
    oos_mask = (strategy_returns.index >= oos_start) & (strategy_returns.index <= oos_end)
    oos_returns = strategy_returns.loc[oos_mask]
    oos_baseline = baseline_returns.loc[
        (baseline_returns.index >= oos_start) & (baseline_returns.index <= oos_end)
    ]

    # Align benchmark
    bench_oos = None
    if benchmark is not None:
        bench_oos = benchmark.reindex(oos_returns.index).dropna()

    perf = compute_performance_metrics(oos_returns, bench_oos)
    base_perf = compute_performance_metrics(oos_baseline, bench_oos)

    exec_result = TickerExecution(
        oos_sharpe=perf.sharpe_ratio,
        oos_sortino=perf.sortino_ratio,
        oos_alpha=perf.alpha,
        oos_max_drawdown=perf.max_drawdown,
        oos_win_rate=perf.win_rate,
        oos_total_return=perf.total_return,
        oos_n_trades=perf.n_trades,
        oos_returns=oos_returns,
        baseline_sharpe=base_perf.sharpe_ratio,
        baseline_alpha=base_perf.alpha,
    )

    return exec_result, oos_returns, oos_baseline


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 4 — FINAL KEEP TARGET VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════


def compute_final_verdict(
    portfolio_returns: pd.Series,
    baseline_portfolio_returns: pd.Series,
    benchmark: pd.Series | None,
    oos_start: pd.Timestamp,
    oos_end: pd.Timestamp,
) -> tuple[ComponentVerdict, dict, dict]:
    """Hitung Score Card final dan verdict KEEP/MARGINAL/REMOVE.

    Returns:
        (ComponentVerdict, portfolio_metrics_dict, baseline_metrics_dict)
    """
    # Filter benchmark to OOS
    bench_oos = None
    if benchmark is not None:
        bench_oos = benchmark.reindex(portfolio_returns.index).dropna()

    # Portfolio metrics
    perf = compute_performance_metrics(portfolio_returns, bench_oos)
    port_metrics = {
        "sharpe": perf.sharpe_ratio,
        "sortino": perf.sortino_ratio,
        "alpha": perf.alpha,
        "max_drawdown": perf.max_drawdown,
        "win_rate": perf.win_rate,
        "total_return": perf.total_return,
        "calmar": perf.calmar_ratio,
        "information_ratio": perf.information_ratio,
        "n_trades": perf.n_trades,
    }

    # Baseline portfolio metrics
    base_perf = compute_performance_metrics(baseline_portfolio_returns, bench_oos)
    base_metrics = {
        "sharpe": base_perf.sharpe_ratio,
        "sortino": base_perf.sortino_ratio,
        "alpha": base_perf.alpha,
        "max_drawdown": base_perf.max_drawdown,
        "win_rate": base_perf.win_rate,
        "total_return": base_perf.total_return,
    }

    # Delta Alpha (portfolio vs baseline)
    # Build a synthetic ohlcv-like for compute_delta_alpha (uses close for baseline signals)
    # Instead, compute delta directly
    delta_alpha = perf.alpha - base_perf.alpha
    delta_sharpe = perf.sharpe_ratio - base_perf.sharpe_ratio

    delta_result = DeltaAlphaResult(
        component="FinalPortfolio",
        alpha_ai=perf.alpha,
        alpha_baseline=base_perf.alpha,
        delta_alpha=delta_alpha,
        sharpe_ai=perf.sharpe_ratio,
        sharpe_baseline=base_perf.sharpe_ratio,
        delta_sharpe=delta_sharpe,
        win_rate_ai=perf.win_rate,
        win_rate_baseline=base_perf.win_rate,
        max_dd_ai=perf.max_drawdown,
        max_dd_baseline=base_perf.max_drawdown,
        n_observations=len(portfolio_returns),
    )

    # Significance tests
    sig_results: list[SignificanceTestResult] = []
    aligned = pd.DataFrame({
        "ai": portfolio_returns,
        "baseline": baseline_portfolio_returns,
    }).dropna()

    if len(aligned) > 30:
        sig_results.append(paired_ttest(aligned["ai"], aligned["baseline"]))
        if bench_oos is not None:
            bench_re = bench_oos.reindex(aligned.index).fillna(0)
            sig_results.append(diebold_mariano_test(
                aligned["ai"] - bench_re,
                aligned["baseline"] - bench_re,
                horizon=5,
            ))
        sig_results.append(whites_reality_check_approximation(
            aligned["ai"], aligned["baseline"], n_bootstrap=500,
        ))

    verdict = compute_component_score_card(
        component_name="FinalPortfolio",
        delta_alpha_result=delta_result,
        significance_results=sig_results,
        drift_results=None,
        latency_ms=None,
        monthly_cost=0.0,
    )

    return verdict, port_metrics, base_metrics


def print_final_report(
    report: FinalVerdictReport,
    ticker_executions: list[TickerExecution],
) -> None:
    """Cetak laporan komprehensif di konsol."""
    logger.info("")
    logger.info("=" * 76)
    logger.info("  PORTFOLIO FINAL EXECUTION — WALK-FORWARD OOS VERDICT")
    logger.info("=" * 76)
    logger.info("  Periode OOS : %s → %s", report.oos_start, report.oos_end)
    logger.info("  Tickers     : %d (executed: %d)", report.n_tickers, report.n_tickers_executed)
    logger.info("  DB          : %s", report.db_path)
    logger.info("  Config      : %s", report.config_path)
    logger.info("")

    # Portfolio vs Baseline comparison
    logger.info("  ┌──────────────────────────────────────────────────────────────────────┐")
    logger.info("  │  PORTFOLIO vs BASELINE (OOS: Jan 2024 – Aug 2026)                   │")
    logger.info("  ├──────────────────────────┼──────────────────┼──────────────────┤")
    logger.info("  │  Metric                  │  Baseline (MA+RSI)│  Final Portfolio │")
    logger.info("  ├──────────────────────────┼──────────────────┼──────────────────┤")

    metrics = [
        ("Sharpe Ratio", report.baseline_portfolio_sharpe, report.portfolio_sharpe, "%+.3f"),
        ("Sortino Ratio", 0.0, report.portfolio_sortino, "%+.3f"),
        ("Alpha (annual)", report.baseline_portfolio_alpha, report.portfolio_alpha, "%+.4f"),
        ("Max Drawdown", report.baseline_portfolio_max_drawdown, report.portfolio_max_drawdown, "%.2f%%"),
        ("Win Rate", 0.0, report.portfolio_win_rate, "%.1f%%"),
        ("Total Return", 0.0, report.portfolio_total_return, "%.2f%%"),
        ("Calmar Ratio", 0.0, report.portfolio_calmar, "%.3f"),
        ("Info Ratio", 0.0, report.portfolio_information_ratio, "%.3f"),
    ]

    for label, b_val, a_val, fmt in metrics:
        if "%" in fmt and "Drawdown" in label or "Win Rate" in label or "Total" in label:
            b_str = fmt % (b_val * 100) if b_val != 0.0 else "—"
            a_str = fmt % (a_val * 100)
        else:
            b_str = fmt % b_val if b_val != 0.0 else "—"
            a_str = fmt % a_val
        delta = a_val - b_val
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        logger.info("  │  %-22s │  %16s │  %16s  %s │", label, b_str, a_str, arrow)

    logger.info("  └──────────────────────────┴──────────────────┴──────────────────┘")
    logger.info("")

    # Delta metrics
    logger.info("  Delta Sharpe : %+.3f", report.delta_sharpe)
    logger.info("  Delta Alpha  : %+.4f", report.delta_alpha)
    logger.info("")

    # Significance tests
    logger.info("  Statistical Significance:")
    logger.info("    Paired t-test       p-value: %.4f %s",
                report.p_value_paired_ttest,
                "✓" if report.p_value_paired_ttest < 0.05 else "✗")
    logger.info("    Diebold-Mariano     p-value: %.4f %s",
                report.p_value_diebold_mariano,
                "✓" if report.p_value_diebold_mariano < 0.05 else "✗")
    logger.info("    White's Reality Chk p-value: %.4f %s",
                report.p_value_whites_rc,
                "✓" if report.p_value_whites_rc < 0.05 else "✗")
    logger.info("")

    # Per-ticker summary
    logger.info("  Per-Ticker OOS Summary:")
    logger.info("  %-10s %-12s κ=%.4s  %-8s %-8s %-8s %-8s %-6s",
                "Ticker", "Cluster", "κ", "Sharpe", "Sortino", "Alpha", "MaxDD", "Weight")
    logger.info("  " + "-" * 72)
    for te in sorted(ticker_executions, key=lambda x: -x.portfolio_weight):
        logger.info("  %-10s %-12s %.4f  %+.3f   %+.3f   %+.4f  %.1f%%   %.4f",
                    te.ticker, te.cluster_label, te.adapt_kappa,
                    te.oos_sharpe, te.oos_sortino, te.oos_alpha,
                    te.oos_max_drawdown * 100, te.portfolio_weight)

    logger.info("")
    logger.info("  Inverse-Variance Weights (OOS average):")
    for te in sorted(ticker_executions, key=lambda x: -x.portfolio_weight):
        bar_len = int(te.portfolio_weight * 50)
        logger.info("    %-10s %6.2f%% %s",
                    te.ticker, te.portfolio_weight * 100, "█" * bar_len)

    # Final verdict
    logger.info("")
    logger.info("  ┌──────────────────────────────────────────────────────────────────────┐")
    logger.info("  │  FINAL SCORE CARD                                                   │")
    logger.info("  │  Score: %.2f / 5.00   |  Verdict: %-10s                       │",
                report.portfolio_score, report.portfolio_verdict)
    logger.info("  │  Target: Score ≥ %.1f (KEEP)  |  Alpha > 0: %s                  │",
                KEEP_SCORE_TARGET, "YES" if report.portfolio_alpha > 0 else "NO")
    logger.info("  └──────────────────────────────────────────────────────────────────────┘")

    if report.promoted_to_keep:
        logger.info("")
        logger.info("  ★★★ PORTFOLIO PROMOTED: KEEP (Score=%.2f, Alpha=%+.4f) ★★★",
                    report.portfolio_score, report.portfolio_alpha)
        logger.info("  Portofolio multi-ticker LOLUS verifikasi final dengan:")
        logger.info("    - Sharpe ratio portofolio gabungan: %+.3f", report.portfolio_sharpe)
        logger.info("    - Alpha portofolio gabungan       : %+.4f", report.portfolio_alpha)
        logger.info("    - Max Drawdown                    : %.2f%%", report.portfolio_max_drawdown * 100)
        logger.info("    - Sortino ratio                   : %+.3f", report.portfolio_sortino)
        logger.info("    - Inverse-Variance weighting aktif: bobot adaptif harian")
    else:
        logger.info("")
        logger.info("  ✗ Belum terpromosi (Score=%.2f, target=%.1f). Rekomendasi:",
                    report.portfolio_score, KEEP_SCORE_TARGET)
        if report.portfolio_alpha <= 0:
            logger.info("    - Alpha portofolio ≤ 0 — perlu tuning ulang atau tambah ticker")
        if report.portfolio_sharpe < 1.0:
            logger.info("    - Sharpe < 1.0 — evaluasi baseline candidates tambahan")
        if report.p_value_paired_ttest >= 0.05:
            logger.info("    - Outperformance tidak signifikan (p=%.4f) — perluas OOS period",
                        report.p_value_paired_ttest)
        logger.info("    - Verifikasi kelengkapan technical_indicators per ticker")

    logger.info("")
    logger.info("=" * 76)


# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════


def run_final_execution(
    tickers: list[str],
    db_path: str,
    config_path: str = "best_ticker_quant_config.json",
    output_path: str = "final_portfolio_verdict.json",
    oos_start: str = "2024-01-01",
    oos_end: str = "2026-08-31",
) -> FinalVerdictReport:
    """Jalankan pipeline final execution end-to-end.

    Alur:
      1. Load ticker-specific config dari best_ticker_quant_config.json.
      2. Per ticker: generate signals → OOS returns.
      3. Inverse-Variance daily weighting → portfolio returns.
      4. Score Card → KEEP verdict → save JSON.
    """
    oos_start_ts = pd.Timestamp(oos_start)
    oos_end_ts = pd.Timestamp(oos_end)

    report = FinalVerdictReport(
        execution_date=pd.Timestamp.now().isoformat(),
        config_path=config_path,
        db_path=db_path,
        oos_start=oos_start,
        oos_end=oos_end,
        n_tickers=len(tickers),
    )

    logger.info("=" * 76)
    logger.info("PORTFOLIO FINAL EXECUTION — WALK-FORWARD OOS EVALUATION")
    logger.info("=" * 76)
    logger.info("DB: %s", db_path)
    logger.info("Config: %s", config_path)
    logger.info("OOS Period: %s → %s", oos_start, oos_end)
    logger.info("Tickers: %d (%s)", len(tickers), tickers)
    logger.info("Target: Score >= %.1f (KEEP) + Alpha > 0", KEEP_SCORE_TARGET)
    logger.info("")

    # ── MODULE 1: Load Config ──
    logger.info("MODULE 1 — Load Ticker-Specific Parameters")
    logger.info("-" * 76)
    ticker_configs = load_ticker_config(config_path)

    base_config = ReformConfig()

    # ── MODULE 2: Signal Generation ──
    logger.info("")
    logger.info("MODULE 2 — Signal Generation + Inverse-Variance Weighting")
    logger.info("-" * 76)

    conn = open_db(db_path)
    try:
        benchmark = load_benchmark_sqlite(conn)

        ticker_executions: list[TickerExecution] = []
        strategy_returns_dict: dict[str, pd.Series] = {}
        baseline_returns_dict: dict[str, pd.Series] = {}

        for i, ticker in enumerate(tickers):
            t0 = time.time()
            tcfg = ticker_configs.get(ticker, {})

            ohlcv = load_ohlcv_sqlite(conn, ticker)
            tech = load_technical_features_sqlite(conn, ticker)

            if ohlcv.empty or len(ohlcv) < base_config.min_train_samples + 50:
                logger.info("  [%2d/%d] %s — SKIP (data < %d rows)",
                            i + 1, len(tickers), ticker,
                            base_config.min_train_samples + 50)
                continue

            ticker_config = build_config_from_ticker_params(base_config, tcfg)
            baseline_candidate = build_baseline_candidate(tcfg)
            adapt_kappa = tcfg.get("adapt_kappa", 0.15)

            exec_result, oos_rets, oos_base = evaluate_oos_ticker(
                ohlcv, benchmark, ticker_config, baseline_candidate, tech,
                adapt_kappa, oos_start_ts, oos_end_ts,
            )

            # Fill metadata
            exec_result.ticker = ticker
            exec_result.sector = tcfg.get("sector", "Unknown")
            exec_result.cluster_id = tcfg.get("cluster_id", -1)
            exec_result.cluster_label = tcfg.get("cluster_label", "outlier")
            exec_result.adapt_kappa = adapt_kappa
            exec_result.gk_volatility = tcfg.get("gk_volatility", 0.0)
            exec_result.baseline_mode = tcfg.get("baseline_mode", "donchian")
            exec_result.best_params = tcfg.get("best_params", {})

            ticker_executions.append(exec_result)
            strategy_returns_dict[ticker] = oos_rets
            baseline_returns_dict[ticker] = oos_base

            logger.info("  [%2d/%d] %s | κ=%.4f | Sharpe=%+.3f | Sortino=%+.3f | "
                        "Alpha=%+.4f | MaxDD=%.1f%% | %s",
                        i + 1, len(tickers), ticker, adapt_kappa,
                        exec_result.oos_sharpe, exec_result.oos_sortino,
                        exec_result.oos_alpha, exec_result.oos_max_drawdown * 100,
                        f"{time.time()-t0:.1f}s")

            # Free memory
            del ohlcv, tech

        report.n_tickers_executed = len(ticker_executions)
        logger.info("")
        logger.info("  Tickers executed: %d/%d", len(ticker_executions), len(tickers))

        if not strategy_returns_dict:
            logger.warning("Tidak ada ticker dengan data cukup — pipeline berhenti")
            return report

        # ── Inverse-Variance Daily Weighting ──
        logger.info("")
        logger.info("  Computing daily Inverse-Variance weights (lookback=60 days)...")
        daily_weights = compute_daily_inverse_variance_weights(
            strategy_returns_dict, oos_start_ts, oos_end_ts,
        )

        # Average weight per ticker (for reporting)
        for te in ticker_executions:
            w_series = daily_weights.get(te.ticker)
            if w_series is not None and len(w_series) > 0:
                te.portfolio_weight = float(w_series.mean())

        # Portfolio returns
        portfolio_returns = compute_weighted_portfolio_returns(
            strategy_returns_dict, daily_weights,
        )

        # Baseline portfolio (equal-weight)
        baseline_portfolio = ensemble_portfolio_returns(
            baseline_returns_dict,
            compute_inverse_variance_weights(baseline_returns_dict),
        )

        logger.info("  Portfolio OOS returns: %d days", len(portfolio_returns))
        logger.info("")

        # ── MODULE 3: OOS Performance ──
        logger.info("MODULE 3 — Walk-Forward OOS Performance Re-Evaluation")
        logger.info("-" * 76)

        # ── MODULE 4: Final KEEP Verdict ──
        logger.info("")
        logger.info("MODULE 4 — Final KEEP Target Verification")
        logger.info("-" * 76)

        verdict, port_metrics, base_metrics = compute_final_verdict(
            portfolio_returns, baseline_portfolio, benchmark,
            oos_start_ts, oos_end_ts,
        )

        score = verdict.score_card["weighted_total"]
        promoted = (
            verdict.verdict == "KEEP"
            and port_metrics["alpha"] > 0
            and score >= KEEP_SCORE_TARGET
        )

        # Extract significance p-values
        p_paired = 1.0
        p_dm = 1.0
        p_whites = 1.0
        for sig in verdict.__dict__.get("significance_results", []):
            pass  # ComponentVerdict doesn't store sig_results directly

        # Re-extract from aligned comparison
        aligned = pd.DataFrame({
            "ai": portfolio_returns, "baseline": baseline_portfolio,
        }).dropna()
        if len(aligned) > 30:
            sig_paired = paired_ttest(aligned["ai"], aligned["baseline"])
            p_paired = sig_paired.p_value
            bench_oos = benchmark.reindex(aligned.index).fillna(0) if benchmark is not None else None
            if bench_oos is not None:
                sig_dm = diebold_mariano_test(
                    aligned["ai"] - bench_oos, aligned["baseline"] - bench_oos, horizon=5,
                )
                p_dm = sig_dm.p_value
            sig_whites = whites_reality_check_approximation(
                aligned["ai"], aligned["baseline"], n_bootstrap=500,
            )
            p_whites = sig_whites.p_value

        # Fill report
        report.portfolio_sharpe = port_metrics["sharpe"]
        report.portfolio_sortino = port_metrics["sortino"]
        report.portfolio_alpha = port_metrics["alpha"]
        report.portfolio_max_drawdown = port_metrics["max_drawdown"]
        report.portfolio_win_rate = port_metrics["win_rate"]
        report.portfolio_total_return = port_metrics["total_return"]
        report.portfolio_calmar = port_metrics["calmar"]
        report.portfolio_information_ratio = port_metrics["information_ratio"]
        report.portfolio_score = score
        report.portfolio_verdict = verdict.verdict
        report.promoted_to_keep = promoted
        report.p_value_paired_ttest = p_paired
        report.p_value_diebold_mariano = p_dm
        report.p_value_whites_rc = p_whites
        report.portfolio_weights = {
            te.ticker: round(te.portfolio_weight, 4) for te in ticker_executions
        }
        report.baseline_portfolio_sharpe = base_metrics["sharpe"]
        report.baseline_portfolio_alpha = base_metrics["alpha"]
        report.baseline_portfolio_max_drawdown = base_metrics["max_drawdown"]
        report.delta_sharpe = port_metrics["sharpe"] - base_metrics["sharpe"]
        report.delta_alpha = port_metrics["alpha"] - base_metrics["alpha"]
        report.ticker_results = [json_safe(asdict(te)) for te in ticker_executions]

        # Simpan daily returns untuk visualisasi (equity curve & drawdown)
        report.daily_portfolio_returns = {
            d.isoformat(): float(r) for d, r in portfolio_returns.items()
        }
        report.daily_baseline_returns = {
            d.isoformat(): float(r) for d, r in baseline_portfolio.items()
        }
        if benchmark is not None:
            bench_oos = benchmark.reindex(portfolio_returns.index).fillna(0.0)
            report.daily_benchmark_returns = {
                d.isoformat(): float(r) for d, r in bench_oos.items()
            }

        # Print comprehensive report
        print_final_report(report, ticker_executions)

        # Save JSON
        save_verdict_json(report, output_path)
        logger.info("  Verdict disimpan: %s", output_path)

    finally:
        conn.close()

    return report


def save_verdict_json(report: FinalVerdictReport, output_path: str) -> None:
    """Simpan final_portfolio_verdict.json."""
    output = {
        "execution_date": report.execution_date,
        "config_path": report.config_path,
        "db_path": report.db_path,
        "oos_period": {
            "start": report.oos_start,
            "end": report.oos_end,
        },
        "n_tickers": report.n_tickers,
        "n_tickers_executed": report.n_tickers_executed,
        "portfolio_metrics": {
            "sharpe": round(report.portfolio_sharpe, 4),
            "sortino": round(report.portfolio_sortino, 4),
            "alpha": round(report.portfolio_alpha, 6),
            "max_drawdown": round(report.portfolio_max_drawdown, 4),
            "win_rate": round(report.portfolio_win_rate, 4),
            "total_return": round(report.portfolio_total_return, 4),
            "calmar": round(report.portfolio_calmar, 4),
            "information_ratio": round(report.portfolio_information_ratio, 4),
        },
        "baseline_portfolio": {
            "sharpe": round(report.baseline_portfolio_sharpe, 4),
            "alpha": round(report.baseline_portfolio_alpha, 6),
            "max_drawdown": round(report.baseline_portfolio_max_drawdown, 4),
        },
        "delta": {
            "sharpe": round(report.delta_sharpe, 4),
            "alpha": round(report.delta_alpha, 6),
        },
        "significance": {
            "paired_ttest_p_value": round(report.p_value_paired_ttest, 4),
            "diebold_mariano_p_value": round(report.p_value_diebold_mariano, 4),
            "whites_reality_check_p_value": round(report.p_value_whites_rc, 4),
        },
        "score_card": {
            "score": round(report.portfolio_score, 2),
            "verdict": report.portfolio_verdict,
            "keep_target": KEEP_SCORE_TARGET,
            "promoted_to_keep": report.promoted_to_keep,
        },
        "portfolio_weights": report.portfolio_weights,
        "daily_returns": {
            "portfolio": report.daily_portfolio_returns,
            "baseline": report.daily_baseline_returns,
            "benchmark": report.daily_benchmark_returns,
        },
        # Strip oos_returns (pd.Series) dari ticker results agar JSON-safe
        "tickers": [
            {k: v for k, v in t.items() if k != "oos_returns"}
            for t in report.ticker_results
        ],
    }

    path = Path(output_path)
    with path.open("w") as f:
        json.dump(json_safe(output), f, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Portfolio Final Execution — Walk-Forward OOS & KEEP Verdict",
    )
    parser.add_argument("--tickers", type=str, default=None,
                        help="Comma-separated tickers (default: 20 focus ticker)")
    parser.add_argument("--config", type=str,
                        default="best_ticker_quant_config.json",
                        help="Path ke best_ticker_quant_config.json")
    parser.add_argument("--output", type=str,
                        default="final_portfolio_verdict.json",
                        help="Output JSON verdict file")
    parser.add_argument("--db", type=str, default=None,
                        help="Path DB (default: env DB_PATH atau settings.db_path dari .env)")
    parser.add_argument("--oos-start", type=str, default="2024-01-01",
                        help="OOS period start date (default: 2024-01-01)")
    parser.add_argument("--oos-end", type=str, default="2026-08-31",
                        help="OOS period end date (default: 2026-08-31)")
    args = parser.parse_args()

    from market.config import settings as _settings
    db_path = args.db or os.environ.get("DB_PATH") or _settings.db_path

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = DEFAULT_FOCUS_TICKERS

    report = run_final_execution(
        tickers, db_path,
        config_path=args.config,
        output_path=args.output,
        oos_start=args.oos_start,
        oos_end=args.oos_end,
    )

    if not report.promoted_to_keep:
        logger.info("")
        logger.info("Exit code 1: portofolio belum mencapai target KEEP.")
        sys.exit(1)


if __name__ == "__main__":
    main()
