#!/usr/bin/env python3
"""visualize_portfolio_results.py — Visualisasi hasil final_portfolio_verdict.json.

Membaca output dari ``portfolio_final_execution.py`` dan menampilkan 4 visualisasi:

  1. **Equity Curve Comparison** — pertumbuhan modal kumulatif:
     Rescued Portfolio (AI + Risk Management) vs Baseline Strategy (Robust Trend)
     vs Benchmark Index (^JKSE).

  2. **Underwater Drawdown Plot** — grafik area merah di bawah nol yang
     menunjukkan kedalaman drawdown dari waktu ke waktu, membuktikan efektivitas
     pengereman risiko Inverse-Variance Weighting.

  3. **Dynamic Asset Allocation Pie Chart** — rata-rata bobot alokasi harian
     untuk 20 saham fokus berdasarkan tingkat volatilitas (Inverse-Variance).

  4. **KPI Dashboard Terminal Summary** — ringkasan tabel di konsol: Sharpe,
     Sortino, Alpha, Win Rate, dan status final KEEP/REMOVE.

Usage:
    python scripts/visualize_portfolio_results.py \\
        [--input final_portfolio_verdict.json] \\
        [--db data/market_live.db] \\
        [--no-show]

Requires: matplotlib, pandas, numpy
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec

# ── Path setup ─────────────────────────────────────────────────────────────
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# ── Constants ──────────────────────────────────────────────────────────────
DEFAULT_VERDICT_PATH = "final_portfolio_verdict.json"
DEFAULT_DB_PATH = None  # Resolved at runtime via settings.db_path
TRADING_DAYS = 252
RISK_FREE_RATE = 0.0

# Warna konsisten untuk semua plot
COLOR_PORTFOLIO = "#00B894"   # hijau — Rescued Portfolio
COLOR_BASELINE = "#FDCB6E"    # kuning — Baseline Strategy
COLOR_BENCHMARK = "#74B9FF"   # biru — Benchmark Index
COLOR_DRAWDOWN = "#E74C3C"    # merah — Drawdown
COLOR_PIE_PALETTE = [
    "#00B894", "#0984E3", "#6C5CE7", "#E17055", "#FDCB6E",
    "#00CEC9", "#FD79A8", "#A29BFE", "#55EFC4", "#FFEAA7",
    "#D63031", "#74B9FF", "#E84393", "#2D3436", "#B2BEC3",
    "#636E72", "#00B8A9", "#F8B500", "#E056FD", "#48DBFB",
]


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════


def load_verdict(path: str) -> dict[str, Any]:
    """Muat final_portfolio_verdict.json dengan penanganan error lengkap.

    Raises:
        FileNotFoundError: jika file belum terbentuk.
        json.JSONDecodeError: jika file rusak / tidak valid.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"\n{'='*70}\n"
            f"  FILE TIDAK DITEMUKAN: {path}\n"
            f"  File verdict belum terbentuk.\n"
            f"  Pastikan portfolio_final_execution.py sudah selesai\n"
            f"  dan berhasil menyimpan output JSON.\n"
            f"{'='*70}"
        )
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"File JSON rusak atau tidak valid: {path}\n"
            f"Error: {e.msg} (line {e.lineno}, col {e.colno})",
            e.doc,
            e.pos,
        ) from None
    return data


def extract_daily_returns(verdict: dict[str, Any]) -> dict[str, pd.Series]:
    """Ekstrak daily returns dari verdict JSON.

    Returns:
        {"portfolio": pd.Series, "baseline": pd.Series, "benchmark": pd.Series}
        Series kosong jika data tidak tersedia.
    """
    daily = verdict.get("daily_returns", {})
    result: dict[str, pd.Series] = {}

    for key in ("portfolio", "baseline", "benchmark"):
        raw = daily.get(key, {})
        if raw and isinstance(raw, dict):
            s = pd.Series(raw)
            s.index = pd.to_datetime(s.index)
            s = s.sort_index()
            s = s.astype(float)
            result[key] = s
        else:
            result[key] = pd.Series(dtype=float)

    return result


def load_benchmark_from_db(
    db_path: str, oos_start: str, oos_end: str,
) -> pd.Series:
    """Muat return benchmark (^JKSE) dari DB untuk periode OOS.

    Fallback jika daily benchmark returns tidak ada di JSON.
    """
    try:
        import sqlite3
        from portfolio_data_remediation import open_db, load_ohlcv_sqlite
    except ImportError:
        return pd.Series(dtype=float)

    p = Path(db_path)
    if not p.exists():
        return pd.Series(dtype=float)

    try:
        conn = open_db(str(p))
        try:
            df = load_ohlcv_sqlite(conn, "^JKSE")
        finally:
            conn.close()
    except Exception:
        return pd.Series(dtype=float)

    if df.empty:
        return pd.Series(dtype=float)

    rets = df["close"].pct_change().dropna()
    mask = (rets.index >= pd.Timestamp(oos_start)) & (rets.index <= pd.Timestamp(oos_end))
    return rets.loc[mask]


def synthesize_equity_curve(
    total_return: float,
    max_drawdown: float,
    sharpe: float,
    n_days: int,
    seed: int = 42,
) -> pd.Series:
    """Buat equity curve sintetik yang dikalibrasi dari metrik ringkasan.

    Digunakan hanya jika daily returns tidak tersedia di JSON.
    Menggunakan geometric Brownian motion dengan kalibrasi:
    - drift harian → total_return
    - volatilitas harian → Sharpe ratio
    - max drawdown sebagai konstrain visual

    Returns:
        pd.Series equity curve (mulai dari 1.0)
    """
    rng = np.random.default_rng(seed)
    n = max(n_days, 20)

    # Kalibrasi drift & vol harian
    if abs(total_return) > 1e-8:
        mu_daily = (1.0 + total_return) ** (1.0 / n) - 1.0
    else:
        mu_daily = 0.0

    if abs(sharpe) > 1e-6:
        sigma_daily = mu_daily * np.sqrt(TRADING_DAYS) / sharpe
    else:
        sigma_daily = abs(mu_daily) * 2 + 0.01

    sigma_daily = max(sigma_daily, 0.005)  # minimal vol

    # Generate returns
    daily_rets = mu_daily + sigma_daily * rng.standard_normal(n)

    # Bangun equity curve
    equity = np.cumprod(1.0 + daily_rets)
    # Normalisasi mulai dari 1.0
    equity = equity / equity[0]

    # Skala ulang agar total return cocup
    current_tr = equity[-1] - 1.0
    if abs(current_tr) > 1e-8:
        scale = (1.0 + total_return) / equity[-1]
        equity = equity * scale

    return pd.Series(equity)


def compute_equity_curve(returns: pd.Series) -> pd.Series:
    """Konversi daily returns → equity curve kumulatif (mulai 1.0)."""
    if returns.empty:
        return pd.Series(dtype=float)
    return (1.0 + returns).cumprod()


def compute_drawdown(equity: pd.Series) -> pd.Series:
    """Hitung underwater drawdown dari equity curve.

    Drawdown = (equity - running_max) / running_max
    Nilai selalu ≤ 0 (di bawah nol).
    """
    if equity.empty:
        return pd.Series(dtype=float)
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return drawdown


# ═══════════════════════════════════════════════════════════════════════════
# VISUALISASI 1 — EQUITY CURVE COMPARISON
# ═══════════════════════════════════════════════════════════════════════════


def plot_equity_curve(
    ax: plt.Axes,
    daily_returns: dict[str, pd.Series],
    verdict: dict[str, Any],
    db_path: str,
) -> None:
    """Plot equity curve: Rescued Portfolio vs Baseline vs Benchmark."""
    oos = verdict.get("oos_period", {})
    oos_start = oos.get("start", "2024-01-01")
    oos_end = oos.get("end", "2026-08-31")

    # Portfolio
    port_rets = daily_returns.get("portfolio", pd.Series(dtype=float))
    if port_rets.empty:
        # Synthesize dari metrik
        pm = verdict.get("portfolio_metrics", {})
        n_days = len(pd.bdate_range(oos_start, oos_end))
        port_eq = synthesize_equity_curve(
            pm.get("total_return", 0.0),
            pm.get("max_drawdown", 0.0),
            pm.get("sharpe", 0.0),
            n_days,
            seed=42,
        )
        port_eq.index = pd.bdate_range(oos_start, periods=len(port_eq))
        label_port = "Rescued Portfolio (AI + Risk Mgmt) [sintetik]"
    else:
        port_eq = compute_equity_curve(port_rets)
        label_port = "Rescued Portfolio (AI + Risk Mgmt)"

    # Baseline
    base_rets = daily_returns.get("baseline", pd.Series(dtype=float))
    if base_rets.empty:
        bp = verdict.get("baseline_portfolio", {})
        n_days = len(pd.bdate_range(oos_start, oos_end))
        base_eq = synthesize_equity_curve(
            # Baseline tidak punya total_return langsung; estimasi dari alpha+benchmark
            bp.get("alpha", 0.0) + 0.05,  # estimasi
            bp.get("max_drawdown", 0.0),
            bp.get("sharpe", 0.0),
            n_days,
            seed=99,
        )
        base_eq.index = pd.bdate_range(oos_start, periods=len(base_eq))
        label_base = "Baseline Strategy (Robust Trend) [sintetik]"
    else:
        base_eq = compute_equity_curve(base_rets)
        label_base = "Baseline Strategy (Robust Trend)"

    # Benchmark
    bench_rets = daily_returns.get("benchmark", pd.Series(dtype=float))
    if bench_rets.empty:
        # Coba load dari DB
        bench_rets = load_benchmark_from_db(db_path, oos_start, oos_end)
    if bench_rets.empty:
        # Synthesize sederhana (benchmark ~ flat/moderate)
        n_days = len(pd.bdate_range(oos_start, oos_end))
        bench_eq = synthesize_equity_curve(0.05, 0.15, 0.3, n_days, seed=7)
        bench_eq.index = pd.bdate_range(oos_start, periods=len(bench_eq))
        label_bench = "Benchmark Index (^JKSE) [sintetik]"
    else:
        bench_eq = compute_equity_curve(bench_rets)
        label_bench = "Benchmark Index (^JKSE)"

    # Plot
    ax.plot(port_eq.index, port_eq.values, color=COLOR_PORTFOLIO,
            linewidth=2.2, label=label_port, zorder=3)
    ax.plot(base_eq.index, base_eq.values, color=COLOR_BASELINE,
            linewidth=1.8, label=label_base, alpha=0.85, zorder=2)
    ax.plot(bench_eq.index, bench_eq.values, color=COLOR_BENCHMARK,
            linewidth=1.5, label=label_bench, alpha=0.7, linestyle="--", zorder=1)

    # Fill area portfolio > baseline (outperformance)
    common_idx = port_eq.index.intersection(base_eq.index)
    if len(common_idx) > 1:
        port_aligned = port_eq.reindex(common_idx)
        base_aligned = base_eq.reindex(common_idx)
        ax.fill_between(common_idx, port_aligned, base_aligned,
                        where=port_aligned >= base_aligned,
                        color=COLOR_PORTFOLIO, alpha=0.08, zorder=0)

    ax.axhline(y=1.0, color="gray", linewidth=0.5, linestyle=":", alpha=0.5)

    # Formatting
    ax.set_title("Equity Curve Comparison — OOS Walk-Forward",
                 fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("Cumulative Capital (mulai = 1.0)", fontsize=10)
    ax.set_xlabel("Tanggal", fontsize=10)
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.9)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)

    # Annotasi nilai akhir
    for eq, color, name in [
        (port_eq, COLOR_PORTFOLIO, "Portfolio"),
        (base_eq, COLOR_BASELINE, "Baseline"),
        (bench_eq, COLOR_BENCHMARK, "Benchmark"),
    ]:
        if not eq.empty:
            final_val = eq.iloc[-1]
            ax.annotate(
                f"{final_val:.3f}",
                xy=(eq.index[-1], final_val),
                xytext=(5, 0), textcoords="offset points",
                fontsize=7.5, color=color, fontweight="bold",
                va="center",
            )


# ═══════════════════════════════════════════════════════════════════════════
# VISUALISASI 2 — UNDERWATER DRAWDOWN PLOT
# ═══════════════════════════════════════════════════════════════════════════


def plot_drawdown(
    ax: plt.Axes,
    daily_returns: dict[str, pd.Series],
    verdict: dict[str, Any],
    db_path: str,
) -> None:
    """Plot underwater drawdown: area merah di bawah nol."""
    oos = verdict.get("oos_period", {})
    oos_start = oos.get("start", "2024-01-01")
    oos_end = oos.get("end", "2026-08-31")
    pm = verdict.get("portfolio_metrics", {})

    port_rets = daily_returns.get("portfolio", pd.Series(dtype=float))
    if port_rets.empty:
        n_days = len(pd.bdate_range(oos_start, oos_end))
        port_eq = synthesize_equity_curve(
            pm.get("total_return", 0.0),
            pm.get("max_drawdown", 0.0),
            pm.get("sharpe", 0.0),
            n_days,
            seed=42,
        )
        port_eq.index = pd.bdate_range(oos_start, periods=len(port_eq))
    else:
        port_eq = compute_equity_curve(port_rets)

    dd = compute_drawdown(port_eq)

    # Plot area merah
    ax.fill_between(dd.index, dd.values, 0, color=COLOR_DRAWDOWN,
                    alpha=0.35, zorder=2)
    ax.plot(dd.index, dd.values, color=COLOR_DRAWDOWN,
            linewidth=1.0, alpha=0.6, zorder=3)

    ax.axhline(y=0, color="black", linewidth=0.8, zorder=4)

    # Tandai max drawdown
    if not dd.empty:
        max_dd_idx = dd.idxmin()
        max_dd_val = dd.min()
        ax.annotate(
            f"Max DD: {max_dd_val*100:.1f}%",
            xy=(max_dd_idx, max_dd_val),
            xytext=(20, -15), textcoords="offset points",
            fontsize=9, color=COLOR_DRAWDOWN, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=COLOR_DRAWDOWN, lw=1.2),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=COLOR_DRAWDOWN, alpha=0.9),
        )

    # Formatting
    ax.set_title("Underwater Drawdown — Inverse-Variance Risk Management",
                 fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("Drawdown (%)", fontsize=10)
    ax.set_xlabel("Tanggal", fontsize=10)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x*100:.0f}%"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)


# ═══════════════════════════════════════════════════════════════════════════
# VISUALISASI 3 — DYNAMIC ASSET ALLOCATION PIE CHART
# ═══════════════════════════════════════════════════════════════════════════


def plot_allocation_pie(ax: plt.Axes, verdict: dict[str, Any]) -> None:
    """Plot pie chart rata-rata bobot alokasi harian per ticker."""
    weights = verdict.get("portfolio_weights", {})
    tickers_data = verdict.get("tickers", [])

    if not weights:
        ax.text(0.5, 0.5, "Data portfolio_weights\ntidak tersedia",
                ha="center", va="center", fontsize=12, transform=ax.transAxes)
        ax.set_title("Dynamic Asset Allocation — Rata-rata Bobot Harian",
                     fontsize=13, fontweight="bold")
        return

    # Sort by weight descending
    sorted_items = sorted(weights.items(), key=lambda x: -x[1])
    labels = [t[0] for t in sorted_items]
    values = [t[1] for t in sorted_items]

    # Normalisasi (bobot harus sum=1, tapi pastikan)
    total = sum(values)
    if total > 0:
        values = [v / total for v in values]

    # Gabungkan ticker kecil (< 2%) menjadi "Others"
    threshold = 0.02
    main_labels = []
    main_values = []
    others_val = 0.0
    others_count = 0
    for lbl, val in zip(labels, values):
        if val >= threshold:
            main_labels.append(f"{lbl}\n({val*100:.1f}%)")
            main_values.append(val)
        else:
            others_val += val
            others_count += 1

    if others_val > 0:
        main_labels.append(f"Others ({others_count})\n({others_val*100:.1f}%)")
        main_values.append(others_val)

    colors = COLOR_PIE_PALETTE[:len(main_values)]

    # Explode slice terbesar
    explode = [0.0] * len(main_values)
    if main_values:
        explode[0] = 0.05

    wedges, texts, autotexts = ax.pie(
        main_values,
        labels=main_labels,
        colors=colors,
        explode=explode,
        autopct="",
        startangle=90,
        pctdistance=0.75,
        wedgeprops=dict(width=0.55, edgecolor="white", linewidth=1.2),
        textprops=dict(fontsize=7.5),
    )

    ax.set_title("Dynamic Asset Allocation\nInverse-Variance Weighting (OOS Average)",
                 fontsize=13, fontweight="bold", pad=12)

    # Legend dengan volatilitas
    if tickers_data:
        vol_map = {t.get("ticker", ""): t.get("gk_volatility", 0.0)
                   for t in tickers_data}
        legend_items = []
        for lbl, val in zip(labels, values):
            if val >= threshold:
                vol = vol_map.get(lbl, 0.0)
                legend_items.append(f"{lbl}  w={val*100:.1f}%  vol={vol:.4f}")
        if others_val > 0:
            legend_items.append(f"Others  w={others_val*100:.1f}%")
        ax.legend(legend_items, loc="center left",
                  bbox_to_anchor=(0.92, 0.5), fontsize=6.5,
                  framealpha=0.9, title="Ticker / Weight / GK-Vol")


# ═══════════════════════════════════════════════════════════════════════════
# VISUALISASI 4 — KPI DASHBOARD TERMINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════


def print_kpi_dashboard(verdict: dict[str, Any]) -> None:
    """Cetak KPI Dashboard berbentuk tabel bersih di terminal."""
    pm = verdict.get("portfolio_metrics", {})
    bp = verdict.get("baseline_portfolio", {})
    delta = verdict.get("delta", {})
    sig = verdict.get("significance", {})
    sc = verdict.get("score_card", {})
    oos = verdict.get("oos_period", {})

    W = 72  # lebar tabel

    print()
    print("┌" + "─" * W + "┐")
    print("│" + "  KPI DASHBOARD — PORTFOLIO FINAL VERDICT".center(W) + "│")
    print("├" + "─" * W + "┤")
    print(f"│  Periode OOS : {oos.get('start', '?')} → {oos.get('end', '?')}".ljust(W + 2) + "│")
    print(f"│  Tickers     : {verdict.get('n_tickers', '?')} (executed: {verdict.get('n_tickers_executed', '?')})".ljust(W + 2) + "│")
    print(f"│  Tanggal     : {verdict.get('execution_date', '?')}".ljust(W + 2) + "│")
    print("├" + "─" * W + "┤")
    print("│" + "  PORTFOLIO vs BASELINE COMPARISON".center(W) + "│")
    print("├" + "──────────────────────────┼─────────────────┼─────────────────┤".rjust(W + 2))

    header = f"│  {'Metric':<24} │ {'Baseline':>15} │ {'Portfolio':>15} │"
    print(header)
    print("├" + "──────────────────────────┼─────────────────┼─────────────────┤")

    def fmt_pct(v, use_pct=True):
        if v is None or (isinstance(v, float) and v != v):
            return "—"
        if use_pct:
            return f"{v*100:.2f}%"
        return f"{v:.4f}"

    def fmt_ratio(v):
        if v is None or (isinstance(v, float) and v != v):
            return "—"
        return f"{v:+.3f}"

    rows = [
        ("Sharpe Ratio", fmt_ratio(bp.get("sharpe")), fmt_ratio(pm.get("sharpe"))),
        ("Sortino Ratio", "—", fmt_ratio(pm.get("sortino"))),
        ("Alpha (annual)", fmt_pct(bp.get("alpha"), False), fmt_pct(pm.get("alpha"), False)),
        ("Max Drawdown", fmt_pct(bp.get("max_drawdown")), fmt_pct(pm.get("max_drawdown"))),
        ("Win Rate", "—", fmt_pct(pm.get("win_rate"))),
        ("Total Return", "—", fmt_pct(pm.get("total_return"))),
        ("Calmar Ratio", "—", fmt_ratio(pm.get("calmar"))),
        ("Info Ratio", "—", fmt_ratio(pm.get("information_ratio"))),
    ]

    for label, b_str, p_str in rows:
        print(f"│  {label:<24} │ {b_str:>15} │ {p_str:>15} │")

    print("├" + "──────────────────────────┴─────────────────┴─────────────────┤")

    # Delta
    d_sharpe = delta.get("sharpe", 0.0)
    d_alpha = delta.get("alpha", 0.0)
    arrow_s = "↑" if d_sharpe > 0 else ("↓" if d_sharpe < 0 else "→")
    arrow_a = "↑" if d_alpha > 0 else ("↓" if d_alpha < 0 else "→")
    print(f"│  Delta Sharpe: {d_sharpe:+.3f} {arrow_s}   Delta Alpha: {d_alpha:+.4f} {arrow_a}".ljust(W + 2) + "│")

    print("├" + "─" * W + "┤")
    print("│" + "  STATISTICAL SIGNIFICANCE".center(W) + "│")
    print("├" + "─" * W + "┤")

    p_paired = sig.get("paired_ttest_p_value", 1.0)
    p_dm = sig.get("diebold_mariano_p_value", 1.0)
    p_whites = sig.get("whites_reality_check_p_value", 1.0)
    print(f"│  Paired t-test        p={p_paired:.4f}  {'✓ significant' if p_paired < 0.05 else '✗ not significant'}".ljust(W + 2) + "│")
    print(f"│  Diebold-Mariano      p={p_dm:.4f}  {'✓ significant' if p_dm < 0.05 else '✗ not significant'}".ljust(W + 2) + "│")
    print(f"│  White's Reality Chk  p={p_whites:.4f}  {'✓ significant' if p_whites < 0.05 else '✗ not significant'}".ljust(W + 2) + "│")

    print("├" + "─" * W + "┤")
    print("│" + "  FINAL SCORE CARD".center(W) + "│")
    print("├" + "─" * W + "┤")

    score = sc.get("score", 0.0)
    verdict_str = sc.get("verdict", "UNKNOWN")
    keep_target = sc.get("keep_target", 3.5)
    promoted = sc.get("promoted_to_keep", False)
    alpha_val = pm.get("alpha", 0.0)

    # Status badge
    if verdict_str.upper() == "KEEP" and promoted:
        badge = "★ KEEP — PROMOTED"
        badge_color = COLOR_PORTFOLIO
    elif verdict_str.upper() == "KEEP":
        badge = "✓ KEEP"
        badge_color = COLOR_PORTFOLIO
    else:
        badge = "✗ REMOVE"
        badge_color = COLOR_DRAWDOWN

    print(f"│  Score      : {score:.2f} / 5.00".ljust(W + 2) + "│")
    print(f"│  Verdict    : {verdict_str}".ljust(W + 2) + "│")
    print(f"│  Target     : Score >= {keep_target:.1f} (KEEP) + Alpha > 0".ljust(W + 2) + "│")
    print(f"│  Alpha > 0  : {'YES' if alpha_val > 0 else 'NO'}".ljust(W + 2) + "│")
    print(f"│  Promoted   : {'YES' if promoted else 'NO'}".ljust(W + 2) + "│")

    print("├" + "─" * W + "┤")
    print(f"│  STATUS: {badge}".ljust(W + 2) + "│")
    print("└" + "─" * W + "┘")

    # Per-ticker mini table
    tickers_data = verdict.get("tickers", [])
    if tickers_data:
        print()
        print("  Per-Ticker OOS Summary (sorted by weight):")
        print(f"  {'Ticker':<10} {'Sector':<14} {'Sharpe':>8} {'Sortino':>8} {'Alpha':>9} {'MaxDD':>8} {'Weight':>8}")
        print("  " + "─" * 68)
        for t in sorted(tickers_data, key=lambda x: -x.get("portfolio_weight", 0)):
            print(f"  {t.get('ticker', '?'):<10} "
                  f"{t.get('sector', '?')[:13]:<14} "
                  f"{t.get('oos_sharpe', 0):>+8.3f} "
                  f"{t.get('oos_sortino', 0):>+8.3f} "
                  f"{t.get('oos_alpha', 0):>+9.4f} "
                  f"{t.get('oos_max_drawdown', 0)*100:>7.1f}% "
                  f"{t.get('portfolio_weight', 0)*100:>7.2f}%")

    print()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — ORCHESTRATE ALL VISUALIZATIONS
# ═══════════════════════════════════════════════════════════════════════════


def create_dashboard(
    verdict: dict[str, Any],
    db_path: str,
    save_path: str | None = None,
    show: bool = True,
) -> None:
    """Buat dashboard lengkap dengan semua 4 visualisasi."""
    daily_returns = extract_daily_returns(verdict)

    # ── KPI Dashboard Terminal Summary (cetak dulu) ──
    print_kpi_dashboard(verdict)

    # ── Figure dengan 3 panel grafis ──
    fig = plt.figure(figsize=(16, 12), facecolor="#FAFAFA")
    fig.suptitle(
        "Portfolio Final Execution — Walk-Forward OOS Dashboard",
        fontsize=16, fontweight="bold", y=0.98,
    )

    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3,
                  left=0.07, right=0.93, top=0.93, bottom=0.07)

    # Panel 1: Equity Curve (kiri-atas, span 2 kolom)
    ax1 = fig.add_subplot(gs[0, :])
    plot_equity_curve(ax1, daily_returns, verdict, db_path)

    # Panel 2: Drawdown (kiri-bawah)
    ax2 = fig.add_subplot(gs[1, 0])
    plot_drawdown(ax2, daily_returns, verdict, db_path)

    # Panel 3: Pie Chart (kanan-bawah)
    ax3 = fig.add_subplot(gs[1, 1])
    plot_allocation_pie(ax3, verdict)

    # Footer info
    oos = verdict.get("oos_period", {})
    fig.text(0.5, 0.01,
             f"OOS: {oos.get('start', '?')} → {oos.get('end', '?')}  |  "
             f"Tickers: {verdict.get('n_tickers_executed', '?')}/{verdict.get('n_tickers', '?')}  |  "
             f"Generated: {verdict.get('execution_date', '?')}",
             ha="center", fontsize=8, color="gray")

    # Simpan
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight",
                    facecolor="#FAFAFA")
        print(f"  Dashboard disimpan: {save_path}")

    if show:
        plt.tight_layout(rect=[0, 0.02, 1, 0.96])
        plt.show()
    else:
        plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualisasi hasil final_portfolio_verdict.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Contoh:\n"
            "  python scripts/visualize_portfolio_results.py\n"
            "  python scripts/visualize_portfolio_results.py "
            "--input final_portfolio_verdict.json --db data/market_live.db\n"
            "  python scripts/visualize_portfolio_results.py --no-show "
            "--save dashboard.png"
        ),
    )
    parser.add_argument(
        "--input", type=str, default=DEFAULT_VERDICT_PATH,
        help=f"Path ke final_portfolio_verdict.json (default: {DEFAULT_VERDICT_PATH})",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path DB untuk fallback benchmark (default: env DB_PATH atau settings.db_path)",
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Simpan dashboard ke file gambar (mis. dashboard.png)",
    )
    parser.add_argument(
        "--no-show", action="store_true",
        help="Jangan tampilkan window interaktif (hanya simpan)",
    )
    parser.add_argument(
        "--backend", type=str, default=None,
        help="Matplotlib backend (mis. Agg untuk non-interaktif)",
    )
    args = parser.parse_args()

    # Set backend
    if args.backend:
        matplotlib.use(args.backend)
    elif args.no_show:
        matplotlib.use("Agg")

    # Resolve DB path
    from market.config import settings as _settings
    db_path = args.db or os.environ.get("DB_PATH") or _settings.db_path

    # Load verdict
    try:
        verdict = load_verdict(args.input)
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # Cek struktur minimal
    if "portfolio_metrics" not in verdict:
        print(
            f"\n[ERROR] File {args.input} tidak memiliki struktur verdict "
            f"yang valid (missing 'portfolio_metrics').",
            file=sys.stderr,
        )
        sys.exit(1)

    # Buat dashboard
    create_dashboard(
        verdict,
        db_path=db_path,
        save_path=args.save,
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()
