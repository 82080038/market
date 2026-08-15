"""AI/ML Utility Audit Script — Comprehensive evaluation of AI components.

Implements the 4-pillar audit framework from pustaka/96-ai-ml-audit-framework.md:
  1. Model Performance Metrics (Sharpe, Sortino, MaxDD, IR, Win Rate, IC)
  2. Ablation Study (With AI vs Without AI vs Baseline)
  3. Latency & Cost-Benefit Analysis
  4. Feature Importance & Drift Audit

Usage:
    DATABASE_URL=postgresql://petrick:market_dev@localhost:5433/market python scripts/audit_ai_utility.py [--tickers BBCA,BBRI] [--limit 20]

Output: JSON report + console summary.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from sqlalchemy import select

from market.db.engine import get_sessionmaker
from market.db.models import OHLCV

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

TRADING_DAYS = 252
RISK_FREE_RATE = 0.05 / TRADING_DAYS  # ~5% annual (SBN yield)
IDX_COMMISSION = 0.0015  # 0.15% per side
IDX_SLIPPAGE = 0.0005  # 0.05%
IDX_TAX = 0.001  # 0.1% PPh final (sell only)
ROUND_TRIP_COST = 2 * (IDX_COMMISSION + IDX_SLIPPAGE) + IDX_TAX  # ~0.55%


# ── Data Structures ───────────────────────────────────────────────────────


@dataclass
class PerformanceMetrics:
    """Portfolio-level performance metrics."""

    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    n_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0


@dataclass
class SignalMetrics:
    """Signal-level metrics (per prediction)."""

    directional_accuracy: float = 0.0
    information_coefficient: float = 0.0
    brier_score: float = 0.0
    precision_at_k: float = 0.0
    n_predictions: int = 0


@dataclass
class LatencyProfile:
    """Latency measurement for a component."""

    component: str
    median_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    n_runs: int = 0


@dataclass
class DriftResult:
    """Feature drift detection result."""

    feature: str
    psi: float = 0.0
    ks_statistic: float = 0.0
    ks_pvalue: float = 0.0
    status: str = "stable"  # stable, moderate, drifted


@dataclass
class AuditReport:
    """Full audit report."""

    audit_date: str = ""
    tickers_audited: list[str] = field(default_factory=list)
    performance: dict[str, PerformanceMetrics] = field(default_factory=dict)
    signal_quality: dict[str, SignalMetrics] = field(default_factory=dict)
    ablation: dict[str, dict] = field(default_factory=dict)
    latency: list[LatencyProfile] = field(default_factory=list)
    drift: list[DriftResult] = field(default_factory=list)
    score_card: dict = field(default_factory=dict)
    verdict: str = ""


# ── Pilar 1: Performance Metrics ──────────────────────────────────────────


def compute_performance_metrics(
    returns: pd.Series,
    benchmark: pd.Series | None = None,
    cost_per_trade: float = ROUND_TRIP_COST,
) -> PerformanceMetrics:
    """Compute portfolio-level performance metrics from a return series.

    Args:
        returns: Daily returns of the strategy (after cost).
        benchmark: Daily returns of benchmark (IHSG). Optional.
        cost_per_trade: Round-trip cost per trade (commission + slippage + tax).

    Returns:
        PerformanceMetrics with all fields computed.
    """
    if returns.empty or len(returns) < 10:
        return PerformanceMetrics()

    returns = returns.dropna()
    n_days = len(returns)

    # Total return
    cumulative = (1 + returns).cumprod()
    total_return = float(cumulative.iloc[-1] - 1)

    # Annualized return (CAGR) — guard against negative base
    years = n_days / TRADING_DAYS
    if years > 0 and total_return > -1:
        annualized_return = float((1 + total_return) ** (1 / years) - 1)
    else:
        annualized_return = float(total_return / years) if years > 0 else 0.0

    # Sharpe ratio
    excess = returns - RISK_FREE_RATE
    if excess.std() > 1e-10:
        sharpe = float(np.sqrt(TRADING_DAYS) * excess.mean() / excess.std())
        # Clamp to reasonable range [-10, 10]
        sharpe = max(-10.0, min(10.0, sharpe))
    else:
        sharpe = 0.0

    # Sortino ratio (downside deviation only)
    downside = excess[excess < 0]
    sortino = float(
        np.sqrt(TRADING_DAYS) * excess.mean() / downside.std()
        if len(downside) > 0 and downside.std() > 0 else 0.0
    )

    # Maximum drawdown
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_dd = float(drawdown.min())

    # Calmar ratio
    cagr = annualized_return
    calmar = float(cagr / abs(max_dd) if max_dd < 0 else 0.0)

    # Win rate, profit factor, expectancy
    trades = returns[returns != 0]
    n_trades = len(trades)
    wins = trades[trades > 0]
    losses = trades[trades < 0]
    win_rate = float(len(wins) / n_trades) if n_trades > 0 else 0.0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0
    profit_factor = float(
        wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else 0.0
    )
    loss_rate = 1 - win_rate
    expectancy = float(win_rate * avg_win + loss_rate * avg_loss)

    # Information ratio (vs benchmark)
    ir = 0.0
    alpha = 0.0
    beta = 1.0
    if benchmark is not None:
        bench_aligned = benchmark.reindex(returns.index).dropna()
        ret_aligned = returns.reindex(bench_aligned.index).dropna()
        if len(ret_aligned) > 10 and len(bench_aligned) == len(ret_aligned):
            active_return = ret_aligned - bench_aligned
            tracking_error = active_return.std()
            ir = float(
                np.sqrt(TRADING_DAYS) * active_return.mean() / tracking_error
                if tracking_error > 0 else 0.0
            )
            # Simple regression alpha/beta
            slope, intercept, _, _, _ = stats.linregress(bench_aligned.values, ret_aligned.values)
            beta = float(slope)
            alpha = float(intercept * TRADING_DAYS)  # annualized

    return PerformanceMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_dd,
        calmar_ratio=calmar,
        information_ratio=ir,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        n_trades=n_trades,
        avg_win=avg_win,
        avg_loss=avg_loss,
        alpha=alpha,
        beta=beta,
    )


def compute_signal_metrics(
    predictions: np.ndarray,
    actual_returns: np.ndarray,
    probabilities: np.ndarray | None = None,
    k: int = 10,
) -> SignalMetrics:
    """Compute signal-level metrics.

    Args:
        predictions: Array of predicted signals (-1, 0, 1) or predicted returns.
        actual_returns: Array of actual next-period returns.
        probabilities: Optional array of predicted probabilities (for Brier score).
        k: Top-K for precision@K.

    Returns:
        SignalMetrics.
    """
    n = len(predictions)
    if n < 10:
        return SignalMetrics(n_predictions=n)

    # Directional accuracy
    pred_sign = np.sign(predictions)
    actual_sign = np.sign(actual_returns)
    directional_acc = float(np.mean(pred_sign == actual_sign))

    # Information Coefficient (Spearman rank correlation)
    if np.std(predictions) > 0 and np.std(actual_returns) > 0:
        ic, _ = stats.spearmanr(predictions, actual_returns)
        ic = float(ic) if not np.isnan(ic) else 0.0
    else:
        ic = 0.0

    # Brier score (if probabilities provided)
    brier = 0.0
    if probabilities is not None and len(probabilities) == n:
        # Assuming binary: outcome = 1 if return > 0, else 0
        outcomes = (actual_returns > 0).astype(float)
        brier = float(np.mean((probabilities - outcomes) ** 2))

    # Precision@K: from top-K predictions by absolute signal, how many correct direction?
    abs_pred = np.abs(predictions)
    top_k_idx = np.argsort(abs_pred)[-k:] if n >= k else np.argsort(abs_pred)
    top_k_correct = np.mean(pred_sign[top_k_idx] == actual_sign[top_k_idx])
    precision_at_k = float(top_k_correct)

    return SignalMetrics(
        directional_accuracy=directional_acc,
        information_coefficient=ic,
        brier_score=brier,
        precision_at_k=precision_at_k,
        n_predictions=n,
    )


# ── Pilar 2: Ablation Study ───────────────────────────────────────────────


def simulate_strategy_returns(
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    cost_per_trade: float = ROUND_TRIP_COST,
) -> pd.Series:
    """Simulate daily returns from a signal series.

    Args:
        ohlcv: DataFrame with 'close' column, DatetimeIndex.
        signals: Series of signals (-1, 0, 1) aligned to ohlcv index.
        cost_per_trade: Round-trip cost when signal changes.

    Returns:
        Daily returns series (after cost).
    """
    close = ohlcv["close"].astype(float)
    returns = close.pct_change()

    # Align signals with returns
    signals = signals.reindex(returns.index).fillna(0)

    # Apply cost when signal changes
    signal_change = signals.diff().fillna(0) != 0
    cost = signal_change.astype(float) * cost_per_trade

    strategy_returns = signals.shift(1) * returns - cost
    return strategy_returns.dropna()


def generate_baseline_signals(ohlcv: pd.DataFrame) -> pd.Series:
    """Generate baseline technical signals (no AI).

    Simple MA crossover + RSI:
    - BUY (1) when SMA20 > SMA50 AND RSI < 70
    - SELL (-1) when SMA20 < SMA50 AND RSI > 30
    - HOLD (0) otherwise
    """
    close = ohlcv["close"].astype(float)

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    signal = pd.Series(0, index=ohlcv.index)
    signal[(sma20 > sma50) & (rsi < 70)] = 1
    signal[(sma20 < sma50) & (rsi > 30)] = -1

    return signal


def generate_random_signals(ohlcv: pd.DataFrame, seed: int = 42) -> pd.Series:
    """Generate random signals as null hypothesis baseline."""
    rng = np.random.default_rng(seed)
    n = len(ohlcv)
    raw = rng.random(n)
    signal = pd.Series(np.where(raw > 0.5, 1, np.where(raw > 0.3, -1, 0)), index=ohlcv.index)
    return signal


def ablation_study(
    ohlcv: pd.DataFrame,
    ai_signals: pd.Series | None = None,
    benchmark_returns: pd.Series | None = None,
) -> dict:
    """Run ablation study comparing strategies.

    Scenarios:
        A: Full AI (if ai_signals provided)
        F: Baseline technical (MA crossover + RSI)
        G: Random signal

    Args:
        ohlcv: OHLCV DataFrame.
        ai_signals: Pre-computed AI signals. If None, only baseline + random.
        benchmark_returns: Benchmark (IHSG) returns for Information Ratio.

    Returns:
        Dict with performance metrics per scenario.
    """
    results = {}

    # Scenario F: Baseline technical
    baseline_signals = generate_baseline_signals(ohlcv)
    baseline_returns = simulate_strategy_returns(ohlcv, baseline_signals)
    results["F_baseline"] = compute_performance_metrics(baseline_returns, benchmark_returns)

    # Scenario G: Random
    random_signals = generate_random_signals(ohlcv)
    random_returns = simulate_strategy_returns(ohlcv, random_signals)
    results["G_random"] = compute_performance_metrics(random_returns, benchmark_returns)

    # Scenario A: Full AI (if provided)
    if ai_signals is not None:
        ai_returns = simulate_strategy_returns(ohlcv, ai_signals)
        results["A_full_ai"] = compute_performance_metrics(ai_returns, benchmark_returns)

        # Delta Alpha
        delta_alpha = results["A_full_ai"].alpha - results["F_baseline"].alpha
        results["delta_alpha"] = delta_alpha

        # Statistical significance (paired t-test on daily returns)
        aligned = pd.DataFrame({
            "ai": ai_returns,
            "baseline": baseline_returns,
        }).dropna()

        if len(aligned) > 30:
            t_stat, p_value = stats.ttest_rel(aligned["ai"], aligned["baseline"])
            results["ablation_ttest"] = {
                "t_statistic": float(t_stat),
                "p_value": float(p_value),
                "significant": p_value < 0.05,
            }

    return results


# ── Pilar 3: Latency & Cost-Benefit ───────────────────────────────────────


def profile_latency(func, *args, n_runs: int = 100, component_name: str = "") -> LatencyProfile:
    """Profile latency of a function by running it n_runs times.

    Args:
        func: Callable to profile.
        *args: Arguments to pass to func.
        n_runs: Number of runs.
        component_name: Name for reporting.

    Returns:
        LatencyProfile with median, p95, p99.
    """
    timings = []

    # Warm-up
    try:
        func(*args)
    except Exception:
        pass

    for _ in range(n_runs):
        t0 = time.perf_counter()
        try:
            func(*args)
        except Exception:
            pass
        t1 = time.perf_counter()
        timings.append((t1 - t0) * 1000)  # ms

    timings = np.array(timings)
    return LatencyProfile(
        component=component_name,
        median_ms=float(np.median(timings)),
        p95_ms=float(np.percentile(timings, 95)),
        p99_ms=float(np.percentile(timings, 99)),
        n_runs=n_runs,
    )


def cost_benefit_analysis(
    alpha_lift_pct: float,
    portfolio_value: float,
    trade_frequency_per_month: float,
    monthly_cost: float,
) -> dict:
    """Compute cost-benefit analysis for an AI component.

    Args:
        alpha_lift_pct: Monthly alpha improvement in percentage (e.g., 0.5 = 0.5%).
        portfolio_value: Total portfolio value in IDR.
        trade_frequency_per_month: Number of trades per month.
        monthly_cost: Monthly operational cost in IDR.

    Returns:
        Dict with benefit, cost, net, break-even AUM, and verdict.
    """
    monthly_revenue_lift = alpha_lift_pct / 100 * portfolio_value * trade_frequency_per_month
    net_benefit = monthly_revenue_lift - monthly_cost
    break_even_aum = monthly_cost / (alpha_lift_pct / 100 * trade_frequency_per_month) if alpha_lift_pct > 0 else float("inf")
    benefit_cost_ratio = monthly_revenue_lift / monthly_cost if monthly_cost > 0 else float("inf")

    if net_benefit > 0 and benefit_cost_ratio > 2:
        verdict = "KEEP — significant net benefit"
    elif net_benefit > 0:
        verdict = "MARGINAL — positive but low ratio"
    else:
        verdict = "REMOVE — cost exceeds benefit"

    return {
        "monthly_revenue_lift": monthly_revenue_lift,
        "monthly_cost": monthly_cost,
        "net_benefit": net_benefit,
        "break_even_aum": break_even_aum,
        "benefit_cost_ratio": benefit_cost_ratio,
        "verdict": verdict,
    }


# ── Pilar 4: Feature Drift ────────────────────────────────────────────────


def population_stability_index(
    reference: np.ndarray,
    current: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute Population Stability Index (PSI).

    PSI < 0.1: stable
    PSI 0.1-0.25: moderate drift
    PSI > 0.25: significant drift

    Args:
        reference: Reference distribution (training data).
        current: Current distribution (recent data).
        n_bins: Number of bins for histogram.

    Returns:
        PSI value.
    """
    # Use reference bins for both
    bins = np.linspace(
        min(reference.min(), current.min()),
        max(reference.max(), current.max()),
        n_bins + 1,
    )

    ref_hist, _ = np.histogram(reference, bins=bins)
    cur_hist, _ = np.histogram(current, bins=bins)

    # Normalize to proportions
    ref_prop = ref_hist / len(reference) + 1e-6
    cur_prop = cur_hist / len(current) + 1e-6

    psi = np.sum((cur_prop - ref_prop) * np.log(cur_prop / ref_prop))
    return float(psi)


def ks_test_drift(reference: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    """Kolmogorov-Smirnov test for distribution shift.

    Returns:
        (ks_statistic, p_value)
    """
    ks_stat, p_val = stats.ks_2samp(reference, current)
    return float(ks_stat), float(p_val)


def drift_status(psi: float) -> str:
    """Classify drift status from PSI value."""
    if psi < 0.1:
        return "stable"
    elif psi < 0.25:
        return "moderate"
    else:
        return "drifted"


def audit_feature_drift(
    features_df: pd.DataFrame,
    reference_end_date: str,
    current_start_date: str,
) -> list[DriftResult]:
    """Audit feature drift for all columns in a feature DataFrame.

    Args:
        features_df: DataFrame with features and DatetimeIndex.
        reference_end_date: End date for reference window.
        current_start_date: Start date for current window.

    Returns:
        List of DriftResult per feature.
    """
    reference = features_df.loc[:reference_end_date]
    current = features_df.loc[current_start_date:]

    if reference.empty or current.empty:
        logger.warning("Empty reference or current window for drift audit")
        return []

    results = []
    for col in features_df.columns:
        ref_data = reference[col].dropna().values
        cur_data = current[col].dropna().values

        if len(ref_data) < 20 or len(cur_data) < 20:
            continue

        psi = population_stability_index(ref_data, cur_data)
        ks_stat, ks_p = ks_test_drift(ref_data, cur_data)

        results.append(DriftResult(
            feature=col,
            psi=psi,
            ks_statistic=ks_stat,
            ks_pvalue=ks_p,
            status=drift_status(psi),
        ))

    return results


# ── Utility: Load OHLCV ───────────────────────────────────────────────────


def load_ohlcv(session, ticker: str, timeframe: str = "1d") -> pd.DataFrame:
    """Load OHLCV from database into a DataFrame."""
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


def load_benchmark(session, ticker: str = "^JKSE") -> pd.Series:
    """Load benchmark returns."""
    df = load_ohlcv(session, ticker)
    if df.empty:
        return pd.Series(dtype=float)
    return df["close"].pct_change().dropna()


# ── Score Card ────────────────────────────────────────────────────────────


def compute_score_card(
    perf: PerformanceMetrics,
    ablation_result: dict,
    latency: LatencyProfile | None = None,
    drift_results: list[DriftResult] | None = None,
    cost_benefit: dict | None = None,
) -> dict:
    """Compute AI Utility Score Card (0-5 scale).

    Returns dict with per-criterion scores and total.
    """
    scores = {}

    # Alpha vs benchmark (25%)
    alpha_annual = perf.alpha * 100  # in %
    scores["alpha"] = min(5, max(0, alpha_annual / 1.0))  # 5 = >5% alpha

    # Sharpe improvement (20%)
    scores["sharpe"] = min(5, max(0, perf.sharpe_ratio / 1.0))  # 5 = Sharpe > 1

    # Statistical significance (15%)
    ttest = ablation_result.get("ablation_ttest", {})
    p_val = ttest.get("p_value", 1.0)
    scores["significance"] = 5 if p_val < 0.01 else (3 if p_val < 0.05 else (1 if p_val < 0.2 else 0))

    # Cost efficiency (15%)
    if cost_benefit:
        ratio = cost_benefit.get("benefit_cost_ratio", 0)
        scores["cost_efficiency"] = min(5, max(0, ratio / 2))
    else:
        scores["cost_efficiency"] = 3  # neutral if no cost data

    # Latency (10%)
    if latency:
        if latency.median_ms < 1000:
            scores["latency"] = 5
        elif latency.median_ms < 5000:
            scores["latency"] = 3
        elif latency.median_ms < 60000:
            scores["latency"] = 1
        else:
            scores["latency"] = 0
    else:
        scores["latency"] = 3

    # Model stability (10%)
    if drift_results:
        drifted = sum(1 for d in drift_results if d.status == "drifted")
        total = len(drift_results)
        stability = 1 - (drifted / total) if total > 0 else 1
        scores["stability"] = stability * 5
    else:
        scores["stability"] = 3

    # Feature interpretability (5%) — heuristic
    scores["interpretability"] = 3  # LightGBM = partially explainable

    # Weighted total
    weights = {
        "alpha": 0.25,
        "sharpe": 0.20,
        "significance": 0.15,
        "cost_efficiency": 0.15,
        "latency": 0.10,
        "stability": 0.10,
        "interpretability": 0.05,
    }
    total = sum(scores[k] * weights[k] for k in weights)

    if total >= 3.5:
        verdict = "KEEP — AI memberikan nilai signifikan"
    elif total >= 2.0:
        verdict = "MARGINAL — AI memberikan nilai marginal, optimasi diperlukan"
    else:
        verdict = "REMOVE — AI tidak memberikan nilai"

    return {
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "weighted_total": round(total, 2),
        "verdict": verdict,
    }


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    from sqlalchemy import select as sa_select
    from sqlalchemy import text

    parser = argparse.ArgumentParser(description="AI/ML Utility Audit")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    parser.add_argument("--limit", type=int, default=20, help="Max tickers to audit")
    parser.add_argument("--output", type=str, default="audit_report.json", help="Output JSON file")
    args = parser.parse_args()

    session = get_sessionmaker()()

    # Select tickers
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

    logger.info("=== AI/ML UTILITY AUDIT ===")
    logger.info("Tickers to audit: %d (%s)", len(tickers), tickers[:5])

    # Load benchmark
    benchmark = load_benchmark(session)
    logger.info("Benchmark (^JKSE): %d daily returns", len(benchmark))

    report = AuditReport(
        audit_date=pd.Timestamp.now().isoformat(),
        tickers_audited=tickers,
    )

    # ── Pilar 1+2: Performance + Ablation per ticker ──
    all_baseline_returns = []
    all_random_returns = []

    for i, ticker in enumerate(tickers):
        ohlcv = load_ohlcv(session, ticker)
        if len(ohlcv) < 200:
            logger.debug("[%d/%d] %s: insufficient data (%d rows), skipping", i + 1, len(tickers), ticker, len(ohlcv))
            continue

        logger.info("[%d/%d] Auditing %s (%d rows)...", i + 1, len(tickers), ticker, len(ohlcv))

        # Baseline technical signals
        baseline_signals = generate_baseline_signals(ohlcv)
        baseline_returns = simulate_strategy_returns(ohlcv, baseline_signals)

        # Random signals
        random_signals = generate_random_signals(ohlcv)
        random_returns = simulate_strategy_returns(ohlcv, random_signals)

        # Performance metrics
        bench_aligned = benchmark.reindex(baseline_returns.index).dropna()
        baseline_perf = compute_performance_metrics(baseline_returns, bench_aligned)
        random_perf = compute_performance_metrics(random_returns, bench_aligned)

        report.performance[f"{ticker}_baseline"] = baseline_perf
        report.performance[f"{ticker}_random"] = random_perf

        all_baseline_returns.append(baseline_returns.rename(ticker))
        all_random_returns.append(random_returns.rename(ticker))

        # Signal quality for baseline
        next_returns = ohlcv["close"].pct_change().shift(-1)
        aligned = pd.DataFrame({"signal": baseline_signals, "next_ret": next_returns}).dropna()
        if len(aligned) > 50:
            sig_metrics = compute_signal_metrics(
                aligned["signal"].values,
                aligned["next_ret"].values,
            )
            report.signal_quality[f"{ticker}_baseline"] = sig_metrics

    # Aggregate across tickers
    if all_baseline_returns:
        avg_baseline = pd.concat(all_baseline_returns, axis=1).mean(axis=1)
        avg_random = pd.concat(all_random_returns, axis=1).mean(axis=1)
        bench_aligned = benchmark.reindex(avg_baseline.index).dropna()

        agg_baseline = compute_performance_metrics(avg_baseline, bench_aligned)
        agg_random = compute_performance_metrics(avg_random, bench_aligned)

        report.performance["AGGREGATE_baseline"] = agg_baseline
        report.performance["AGGREGATE_random"] = agg_random

        logger.info("")
        logger.info("=" * 60)
        logger.info("AGGREGATE PERFORMANCE (avg across %d tickers)", len(all_baseline_returns))
        logger.info("=" * 60)
        logger.info("  Baseline (Technical):")
        logger.info("    Sharpe:      %.3f", agg_baseline.sharpe_ratio)
        logger.info("    Sortino:     %.3f", agg_baseline.sortino_ratio)
        logger.info("    Max DD:      %.2f%%", agg_baseline.max_drawdown * 100)
        logger.info("    Win Rate:    %.1f%%", agg_baseline.win_rate * 100)
        logger.info("    Profit Factor: %.3f", agg_baseline.profit_factor)
        logger.info("    Alpha (ann): %.2f%%", agg_baseline.alpha * 100)
        logger.info("    Info Ratio:  %.3f", agg_baseline.information_ratio)
        logger.info("    N trades:    %d", agg_baseline.n_trades)
        logger.info("")
        logger.info("  Random (Null Hypothesis):")
        logger.info("    Sharpe:      %.3f", agg_random.sharpe_ratio)
        logger.info("    Max DD:      %.2f%%", agg_random.max_drawdown * 100)
        logger.info("    Win Rate:    %.1f%%", agg_random.win_rate * 100)
        logger.info("    Alpha (ann): %.2f%%", agg_random.alpha * 100)

        # Score card
        report.score_card = compute_score_card(agg_baseline, {})
        logger.info("")
        logger.info("  Score Card: %s", json.dumps(report.score_card, indent=2))

    # ── Pilar 3: Latency profiling (example with baseline signal generation) ──
    if tickers:
        sample_ohlcv = load_ohlcv(session, tickers[0])
        if not sample_ohlcv.empty:
            latency = profile_latency(
                generate_baseline_signals, sample_ohlcv,
                n_runs=50, component_name="baseline_signal_generation",
            )
            report.latency.append(latency)
            logger.info("")
            logger.info("LATENCY PROFILE:")
            logger.info("  %s: median=%.1fms, p95=%.1fms, p99=%.1fms",
                        latency.component, latency.median_ms, latency.p95_ms, latency.p99_ms)

    # ── Pilar 4: Feature drift (using OHLCV-derived features) ──
    if tickers:
        sample_ohlcv = load_ohlcv(session, tickers[0])
        if len(sample_ohlcv) > 500:
            close = sample_ohlcv["close"].astype(float)
            returns = close.pct_change()

            features = pd.DataFrame(index=sample_ohlcv.index)
            features["ret_1"] = returns
            features["vol_20"] = returns.rolling(20).std()
            features["rsi"] = _rsi(close, 14)
            features["ma_ratio_20"] = close / close.rolling(20).mean()
            features["ma_ratio_50"] = close / close.rolling(50).mean()
            features["bb_width"] = _bb_width(close, 20)

            # Split: first 70% as reference, last 30% as current
            split_idx = int(len(features) * 0.7)
            ref_end = features.index[split_idx]
            cur_start = features.index[split_idx + 1]

            drift_results = audit_feature_drift(features, str(ref_end.date()), str(cur_start.date()))
            report.drift = drift_results

            logger.info("")
            logger.info("FEATURE DRIFT AUDIT (%s):", tickers[0])
            for d in drift_results:
                status_icon = "✅" if d.status == "stable" else ("⚠️" if d.status == "moderate" else "🔴")
                logger.info("  %s %-20s PSI=%.4f  KS=%.4f  p=%.4f",
                            status_icon, d.feature, d.psi, d.ks_statistic, d.ks_pvalue)

    # ── Cost-benefit example ──
    if all_baseline_returns:
        alpha_lift = agg_baseline.alpha * 100 / 12  # monthly %
        cb = cost_benefit_analysis(
            alpha_lift_pct=max(0, alpha_lift),
            portfolio_value=100_000_000,  # Rp 100M
            trade_frequency_per_month=4,
            monthly_cost=150_000,  # Rp 150K (GPU electricity)
        )
        logger.info("")
        logger.info("COST-BENEFIT ANALYSIS (Rp 100M portfolio, 4 trades/month):")
        logger.info("  Monthly Revenue Lift: Rp %s", f"{cb['monthly_revenue_lift']:,.0f}")
        logger.info("  Monthly Cost:         Rp %s", f"{cb['monthly_cost']:,.0f}")
        logger.info("  Net Benefit:          Rp %s", f"{cb['net_benefit']:,.0f}")
        logger.info("  Break-even AUM:       Rp %s", f"{cb['break_even_aum']:,.0f}")
        logger.info("  B/C Ratio:            %.2fx", cb["benefit_cost_ratio"])
        logger.info("  Verdict:              %s", cb["verdict"])
        report.ablation["cost_benefit"] = cb

    # ── Save report ──
    report_dict = {
        "audit_date": report.audit_date,
        "tickers_audited": report.tickers_audited,
        "performance": {k: asdict(v) for k, v in report.performance.items()},
        "signal_quality": {k: asdict(v) for k, v in report.signal_quality.items()},
        "ablation": report.ablation,
        "latency": [asdict(v) for v in report.latency],
        "drift": [asdict(v) for v in report.drift],
        "score_card": report.score_card,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report_dict, indent=2, default=str))
    logger.info("")
    logger.info("Full report saved to: %s", output_path)

    session.close()


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


if __name__ == "__main__":
    main()
