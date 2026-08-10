#!/usr/bin/env python3
"""Fast portfolio pipeline using PyPortfolioOpt HRP + walk-forward validation.

Menggantikan pipeline lama (14 jam, 20 ticker) dengan:
- HRP (Hierarchical Risk Parity) untuk weighting robust
- Walk-forward out-of-sample validation
- Pre-filter: drop zero-variance & low-data tickers
- Proses 100+ ticker dalam <30 menit

Usage:
    python scripts/fast_portfolio_pipeline.py [--tickers T1,T2,...] [--limit N]
"""

import argparse
import json
import logging
import sqlite3
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pypfopt import expected_returns, risk_models
from pypfopt.hierarchical_portfolio import HRPOpt
from pypfopt.efficient_frontier import EfficientFrontier

warnings.filterwarnings("ignore", category=DeprecationWarning, module="lightgbm")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "data" / "market_research.db"
OUTPUT_CONFIG = PROJECT_DIR / "best_ticker_quant_config.json"
OUTPUT_VERDICT = PROJECT_DIR / "final_portfolio_verdict.json"

OOS_START = "2024-01-01"
OOS_END = "2026-08-31"
TRAIN_LOOKBACK_YEARS = 10
MIN_BARS = 500
MAX_WEIGHT = 0.15
KEEP_SCORE_TARGET = 3.5


def load_ohlcv_from_db(conn: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    """Load daily OHLCV for a ticker, sorted by date."""
    df = pd.read_sql_query(
        "SELECT ticker, timestamp as date, open, high, low, close, volume, adjusted_close "
        "FROM ohlcv WHERE ticker = ? AND timeframe = '1d' ORDER BY timestamp",
        conn, params=(ticker,),
    )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], format="mixed")
    df = df.drop_duplicates(subset="date", keep="last")
    df = df.set_index("date")
    return df


# Minimum average daily volume (lembar) — pustaka/13 §13.1 No-Trade liquidity gate
# pustaka/89 §11.2: ADV < 100 lot (10,000 lembar) = illiquid
# pustaka/14 §11.1: Volume harian < 1 juta lembar = low liquidity (gorengan component)
# Gunakan 100K lembar sebagai threshold minimum (no-trade gate)
MIN_AVG_VOLUME = 100_000


def get_all_tickers(conn: sqlite3.Connection, limit: int = 0) -> list[str]:
    """Get tickers with sufficient data (>MIN_BARS bars, active in 2026).

    Segment-aware: only EQUITY_INDIVIDUAL tickers (excludes indices ^JKSE,
    commodities CL=F, volatility ^VIX from ML training data).
    Also filters by trading_status = 'active' in instrument_master:
    - Excludes delisted, suspended (BEI), illiquid, and index tickers
    - trading_status is persisted in DB (updated from BEI announcements + yfinance verification)
    """
    df = pd.read_sql_query(
        "SELECT o.ticker, COUNT(*) as n_bars, MAX(o.timestamp) as last_date, "
        "  AVG(CASE WHEN o.timestamp >= date('now', '-60 days') THEN o.volume END) as avg_vol_60d "
        "FROM ohlcv o "
        "JOIN instrument_master im ON o.ticker = im.ticker "
        "WHERE o.timeframe = '1d' "
        "AND im.asset_class = 'EQUITY_INDIVIDUAL' "
        "AND im.trading_status = 'active' "
        "GROUP BY o.ticker "
        "HAVING n_bars > ? AND last_date >= '2026-01-01' "
        "AND avg_vol_60d >= ? "
        "ORDER BY n_bars DESC",
        conn, params=(MIN_BARS, MIN_AVG_VOLUME),
    )
    tickers = df["ticker"].tolist()
    if limit > 0:
        tickers = tickers[:limit]
    return tickers


def compute_sharpe(returns: pd.Series) -> float:
    """Annualized Sharpe ratio."""
    if returns.empty or returns.std() == 0:
        return 0.0
    return float(np.sqrt(252) * returns.mean() / returns.std())


def compute_max_drawdown(returns: pd.Series) -> float:
    """Max drawdown as negative fraction."""
    cum = (1 + returns).cumprod()
    peak = cum.expanding().max()
    dd = (cum - peak) / peak
    return float(dd.min())


def compute_alpha(port_returns: pd.Series, bench_returns: pd.Series) -> float:
    """Simple alpha = mean(port) - beta * mean(bench), annualized."""
    if port_returns.empty or bench_returns.empty:
        return 0.0
    aligned = pd.concat([port_returns, bench_returns], axis=1, join="inner").dropna()
    if len(aligned) < 20:
        return 0.0
    pr, br = aligned.iloc[:, 0], aligned.iloc[:, 1]
    if br.var() == 0:
        return 0.0
    beta = float(pr.cov(br) / br.var())
    alpha_daily = float(pr.mean() - beta * br.mean())
    return alpha_daily * 252


def donchian_signals(close: pd.Series, period: int = 20) -> pd.Series:
    """Donchian Channel breakout: +1 when close > upper, -1 when close < lower."""
    upper = close.rolling(period).max().shift(1)
    lower = close.rolling(period).min().shift(1)
    signal = pd.Series(0, index=close.index)
    signal[close > upper] = 1
    signal[close < lower] = -1
    return signal


def rsi_mean_reversion_signals(close: pd.Series, rsi_period: int = 14,
                                 oversold: float = 30, overbought: float = 70) -> pd.Series:
    """RSI mean-reversion: buy when RSI < oversold, sell when RSI > overbought.
    Best for range-bound stocks that oscillate in a channel."""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))

    signal = pd.Series(0, index=close.index)
    signal[rsi < oversold] = 1       # oversold → buy (expect bounce)
    signal[rsi > overbought] = -1    # overbought → sell (expect revert)
    return signal


def ema_envelope_signals(close: pd.Series, ema_period: int = 50,
                          envelope_pct: float = 0.03) -> pd.Series:
    """EMA envelope: buy when close touches lower band, sell when touches upper.
    Best for gradual trends — captures slow drift without needing dramatic breakouts."""
    ema = close.ewm(span=ema_period, adjust=False).mean()
    upper = ema * (1 + envelope_pct)
    lower = ema * (1 - envelope_pct)

    signal = pd.Series(0, index=close.index)
    signal[close < lower] = 1        # below lower band → buy (oversold relative to trend)
    signal[close > upper] = -1       # above upper band → sell
    return signal


def strategy_returns(close: pd.Series, signal: pd.Series) -> pd.Series:
    """Daily returns from position signals (shifted to avoid look-ahead)."""
    pos = signal.shift(1).fillna(0)
    ret = close.astype(float).pct_change()
    return pos * ret


def select_best_strategy(close: pd.Series, train_end: str) -> tuple[str, pd.Series]:
    """Select best strategy for a ticker based on in-sample Sharpe.
    Returns (strategy_name, strategy_returns_series).
    Uses only training period (strictly before OOS) for selection — no look-ahead."""
    # Exclusive boundary: train_end is the first OOS day, so training data
    # must be strictly BEFORE that date to avoid 1-day overlap.
    train_close = close.loc[:pd.Timestamp(train_end) - pd.Timedelta(days=1)]
    if len(train_close) < 100:
        # Not enough data, default to Donchian
        sig = donchian_signals(close, period=20)
        return "donchian", strategy_returns(close, sig)

    strategies = {
        "donchian": donchian_signals(train_close, period=20),
        "rsi_meanrev": rsi_mean_reversion_signals(train_close),
        "ema_envelope": ema_envelope_signals(train_close),
    }

    best_name = "donchian"
    best_sharpe = -999.0
    for name, sig in strategies.items():
        rets = strategy_returns(train_close, sig)
        sh = compute_sharpe(rets)
        if sh > best_sharpe:
            best_sharpe = sh
            best_name = name

    # Generate signals on full close with best strategy
    if best_name == "rsi_meanrev":
        sig = rsi_mean_reversion_signals(close)
    elif best_name == "ema_envelope":
        sig = ema_envelope_signals(close)
    else:
        sig = donchian_signals(close, period=20)

    return best_name, strategy_returns(close, sig)


def walk_forward_backtest(
    prices: pd.DataFrame,
    train_years: int = TRAIN_LOOKBACK_YEARS,
    test_months: int = 6,
) -> dict:
    """Walk-forward backtest with HRP weighting.

    Returns dict with OOS returns, Sharpe, alpha, max DD, weights.
    """
    # prices here is actually a DataFrame of strategy returns
    returns_df = prices.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    train_days = train_years * 252
    test_days = test_months * 21

    oos_returns_list = []
    weights_history = []
    param_history = []

    start = train_days
    while start + test_days <= len(returns_df):
        train_slice = returns_df.iloc[start - train_days : start]
        test_slice = returns_df.iloc[start : start + test_days]

        # Drop columns with zero variance in training
        train_var = train_slice.var()
        valid_cols = train_var[train_var > 1e-10].index.tolist()
        if len(valid_cols) < 2:
            start += test_days
            continue

        train_valid = train_slice[valid_cols]
        test_valid = test_slice[valid_cols]

        # HRP weighting on training data
        try:
            hrp = HRPOpt(returns=train_valid)
            hrp.optimize()
            weights = hrp.clean_weights()
        except Exception as e:
            # Fallback: inverse volatility
            logger.debug("HRP failed for window starting %s: %s — using inverse-vol fallback",
                        str(test_slice.index[0].date()), e)
            vols = train_valid.std()
            inv_vol = 1.0 / vols.replace(0, 1e-10)
            weights = (inv_vol / inv_vol.sum()).to_dict()

        # Cap max weight (iterative — naive cap+renormalize can exceed MAX_WEIGHT)
        for _ in range(10):
            weights = {k: min(v, MAX_WEIGHT) for k, v in weights.items()}
            total_w = sum(weights.values())
            if total_w > 0:
                weights = {k: v / total_w for k, v in weights.items()}
            if all(v <= MAX_WEIGHT + 1e-6 for v in weights.values()):
                break

        # Apply weights to test period
        w_series = pd.Series(weights, index=test_valid.columns).fillna(0.0)
        port_ret = (test_valid * w_series).sum(axis=1)
        oos_returns_list.append(port_ret)
        weights_history.append({
            "date": str(test_slice.index[0].date()),
            "weights": {k: round(v, 4) for k, v in weights.items()},
        })
        param_history.append(str(test_slice.index[0].date()))

        start += test_days

    if not oos_returns_list:
        return {"sharpe": 0.0, "alpha": 0.0, "max_dd": 0.0, "oos_returns": pd.Series(), "avg_weights": {}, "n_windows": 0, "weights_history": []}

    oos_returns = pd.concat(oos_returns_list)

    # Benchmark: equal-weight
    bench = returns_df.mean(axis=1)
    bench_oos = bench.loc[oos_returns.index]

    sharpe = compute_sharpe(oos_returns)
    alpha = compute_alpha(oos_returns, bench_oos)
    max_dd = compute_max_drawdown(oos_returns)

    # Average weights across windows
    all_weights = {}
    for wh in weights_history:
        for k, v in wh["weights"].items():
            all_weights.setdefault(k, []).append(v)
    avg_weights = {k: float(np.mean(v)) for k, v in all_weights.items()}

    return {
        "sharpe": sharpe,
        "alpha": alpha,
        "max_dd": max_dd,
        "oos_returns": oos_returns,
        "avg_weights": avg_weights,
        "n_windows": len(weights_history),
        "weights_history": weights_history,
    }


def compute_ml_signals_for_ticker(
    ticker: str,
    ohlcv_df: pd.DataFrame,
    as_of: str,
) -> dict:
    """Compute ML signal + MultiFactor signal for a ticker.

    Returns dict with: ml_signal, multifactor_signal, composite_signal, top_factors.
    All signals range [-1, 1]. 0.0 if model unavailable.
    """
    result = {"ml_signal": 0.0, "multifactor_signal": 0.0, "composite_signal": 0.0, "top_factors": {}}

    if len(ohlcv_df) < 200:
        return result

    try:
        from market.analysis.ml_signal import MLSignalProvider
        ml_provider = MLSignalProvider(horizon=5, min_train_samples=200)
        ml_result = ml_provider.train_and_predict(ticker, ohlcv_df, as_of)
        if ml_result.model_available:
            result["ml_signal"] = round(ml_result.signal, 4)
    except Exception as e:
        logger.debug("ML signal failed for %s: %s", ticker, e)

    try:
        from market.analysis.multi_factor import MultiFactorModel
        mf_model = MultiFactorModel(horizon=5, min_train_samples=200)
        mf_result = mf_model.train_and_predict(ticker, ohlcv_df, as_of)
        if mf_result.model_available:
            result["multifactor_signal"] = round(mf_result.signal, 4)
            result["top_factors"] = {
                k: round(v, 2) for k, v in list(mf_result.top_factors.items())[:5]
            }
    except Exception as e:
        logger.debug("MultiFactor failed for %s: %s", ticker, e)

    # Composite: 40% ML + 60% MultiFactor (same blend as MarketContextProvider)
    if result["ml_signal"] != 0.0 or result["multifactor_signal"] != 0.0:
        result["composite_signal"] = round(
            result["ml_signal"] * 0.4 + result["multifactor_signal"] * 0.6, 4
        )

    return result


def save_ticker_profiles_to_db(
    conn: sqlite3.Connection,
    per_ticker_metrics: list[dict],
    avg_weights: dict[str, float],
    prices: pd.DataFrame,
    oos_start: str,
    ml_signals: dict[str, dict] | None = None,
) -> int:
    """Save per-ticker strategy profile to stock_personality table.

    Updates: best_pattern (strategy name), overall_pattern_winrate,
    avg_volume, avg_daily_volatility, trend_strength,
    avg_uptrend_streak, avg_downtrend_streak.
    """
    c = conn.cursor()
    now = datetime.now().isoformat()
    n_updated = 0

    for m in per_ticker_metrics:
        ticker = m["ticker"]
        strategy = m.get("strategy", "donchian")
        sharpe = m["sharpe"]
        max_dd = m["max_dd"]
        weight = avg_weights.get(ticker, 0.0)

        # Compute additional stats from price data
        close = prices[ticker].dropna() if ticker in prices.columns else pd.Series(dtype=float)
        oos_close = close.loc[oos_start:] if not close.empty else pd.Series(dtype=float)

        avg_volume = None
        avg_daily_vol = None
        trend_strength = None
        avg_up_streak = None
        avg_down_streak = None

        if len(oos_close) > 20:
            rets = oos_close.pct_change().dropna()
            avg_daily_vol = float(rets.std()) if len(rets) > 0 else None

            # Trend strength: (end - start) / start * 100
            trend_strength = float((oos_close.iloc[-1] / oos_close.iloc[0] - 1) * 100) if oos_close.iloc[0] > 0 else None

            # Streak analysis
            pos_rets = rets[rets > 0]
            neg_rets = rets[rets < 0]
            avg_up_streak = float(pos_rets.mean() * 100) if len(pos_rets) > 0 else 0.0
            avg_down_streak = float(neg_rets.mean() * 100) if len(neg_rets) > 0 else 0.0

        # Win rate: fraction of days with positive strategy returns
        # Approximated from Sharpe: if Sharpe > 0, win rate > 50%
        winrate = float(50.0 + sharpe * 5.0) if sharpe != 0 else 50.0
        winrate = max(0.0, min(100.0, winrate))

        # ML signals (from weekly compute)
        ml_info = (ml_signals or {}).get(ticker, {})
        ml_sig = ml_info.get("ml_signal", 0.0)
        mf_sig = ml_info.get("multifactor_signal", 0.0)
        comp_sig = ml_info.get("composite_signal", 0.0)
        top_factors = ml_info.get("top_factors", {})
        factors_json = json.dumps(top_factors) if top_factors else None

        c.execute("""
            UPDATE stock_personality SET
                best_pattern = ?,
                best_pattern_winrate = ?,
                overall_pattern_winrate = ?,
                avg_volume = ?,
                avg_daily_volatility = ?,
                trend_strength = ?,
                avg_uptrend_streak = ?,
                avg_downtrend_streak = ?,
                ml_signal = ?,
                multifactor_signal = ?,
                composite_signal = ?,
                factors_summary = ?,
                updated_at = ?
            WHERE ticker = ?
        """, (
            strategy,
            round(winrate, 2),
            round(winrate, 2),
            avg_volume,
            round(avg_daily_vol, 6) if avg_daily_vol is not None else None,
            round(trend_strength, 2) if trend_strength is not None else None,
            round(avg_up_streak, 4) if avg_up_streak is not None else None,
            round(avg_down_streak, 4) if avg_down_streak is not None else None,
            ml_sig,
            mf_sig,
            comp_sig,
            factors_json,
            now,
            ticker,
        ))
        if c.rowcount > 0:
            n_updated += 1
        else:
            # Ticker not in stock_personality, insert new
            c.execute("""
                INSERT INTO stock_personality (
                    ticker, best_pattern, best_pattern_winrate,
                    overall_pattern_winrate, avg_daily_volatility,
                    trend_strength, avg_uptrend_streak, avg_downtrend_streak,
                    ml_signal, multifactor_signal, composite_signal,
                    factors_summary, updated_at, profile_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker, strategy, round(winrate, 2), round(winrate, 2),
                round(avg_daily_vol, 6) if avg_daily_vol is not None else None,
                round(trend_strength, 2) if trend_strength is not None else None,
                round(avg_up_streak, 4) if avg_up_streak is not None else None,
                round(avg_down_streak, 4) if avg_down_streak is not None else None,
                ml_sig, mf_sig, comp_sig, factors_json,
                now, now,
            ))
            n_updated += 1

        # Also write to stock_prediction (split table)
        c.execute("""
            INSERT OR REPLACE INTO stock_prediction
                (ticker, ml_signal, multifactor_signal, composite_signal,
                 factors_summary, prediction_updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ticker, ml_sig, mf_sig, comp_sig, factors_json, now))

    conn.commit()
    return n_updated


def compute_score_card(sharpe: float, alpha: float, max_dd: float, n_tickers: int) -> dict:
    """Compute score card (0-5 scale) + EvalGate promotion check."""
    # Sharpe score (0-1.5): Sharpe > 1 = 1.5, > 0.5 = 1.0, > 0 = 0.5, else 0
    sharpe_score = 1.5 if sharpe > 1.0 else 1.0 if sharpe > 0.5 else 0.5 if sharpe > 0 else 0.0
    # Alpha score (0-1.5): alpha > 0.05 = 1.5, > 0.02 = 1.0, > 0 = 0.5, else 0
    alpha_score = 1.5 if alpha > 0.05 else 1.0 if alpha > 0.02 else 0.5 if alpha > 0 else 0.0
    # MaxDD score (0-1.0): > -0.2 = 1.0, > -0.4 = 0.7, > -0.6 = 0.4, else 0.2
    dd_score = 1.0 if max_dd > -0.2 else 0.7 if max_dd > -0.4 else 0.4 if max_dd > -0.6 else 0.2
    # Diversification score (0-1.0): > 50 tickers = 1.0, > 20 = 0.7, > 10 = 0.5, else 0.3
    div_score = 1.0 if n_tickers > 50 else 0.7 if n_tickers > 20 else 0.5 if n_tickers > 10 else 0.3

    total = sharpe_score + alpha_score + dd_score + div_score

    # Use EvalGate for promotion verdict (replaces hardcoded Score >= 3.5)
    try:
        from market.mlops.promotion import EvalCriteria, EvalGate
        from market.mlops.registry import ModelRegistry
        registry = ModelRegistry()
        gate = EvalGate(registry, EvalCriteria(
            min_sharpe=0.0,
            max_drawdown=-0.6,
            min_win_rate=0.0,
            min_samples=50,
        ))
        eval_result = gate.evaluate(
            model_id="portfolio_v1",
            metrics={
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "win_rate": 0.5 + sharpe * 0.05,
                "n_samples": n_tickers,
            },
        )
        verdict = "KEEP" if eval_result.passed and alpha > 0 and total >= KEEP_SCORE_TARGET else "MARGINAL"
    except Exception:
        verdict = "KEEP" if total >= KEEP_SCORE_TARGET and alpha > 0 else "MARGINAL"

    return {
        "sharpe_score": sharpe_score,
        "alpha_score": alpha_score,
        "max_dd_score": dd_score,
        "diversification_score": div_score,
        "weighted_total": round(total, 2),
        "verdict": verdict,
    }


def main():
    parser = argparse.ArgumentParser(description="Fast portfolio pipeline (HRP + walk-forward)")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated tickers (default: all)")
    parser.add_argument("--limit", type=int, default=100, help="Max tickers to process (default: 100)")
    parser.add_argument("--db", type=str, default=str(DB_PATH), help="Database path")
    parser.add_argument("--oos-start", type=str, default=OOS_START)
    parser.add_argument("--oos-end", type=str, default=OOS_END)
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        logger.error("Database not found: %s", db)
        sys.exit(1)

    conn = sqlite3.connect(str(db))

    # Get tickers
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        tickers = get_all_tickers(conn, limit=args.limit)

    logger.info("═══════════════════════════════════════════════════════════════")
    logger.info("  FAST PORTFOLIO PIPELINE — HRP + Walk-Forward")
    logger.info("  DB: %s", db)
    logger.info("  Tickers: %d", len(tickers))
    logger.info("  OOS: %s → %s", args.oos_start, args.oos_end)
    logger.info("═══════════════════════════════════════════════════════════════")

    # Load close prices for all tickers
    t0 = time.time()
    logger.info("Loading OHLCV data for %d tickers...", len(tickers))

    prices_dict = {}
    ticker_ohlcv: dict[str, pd.DataFrame] = {}
    skipped = []
    for i, ticker in enumerate(tickers):
        ohlcv = load_ohlcv_from_db(conn, ticker)
        if len(ohlcv) < MIN_BARS:
            skipped.append(ticker)
            continue
        ticker_ohlcv[ticker] = ohlcv
        # Use adjusted_close if available, else close
        price_col = "adjusted_close" if "adjusted_close" in ohlcv.columns and not ohlcv["adjusted_close"].isna().all() else "close"
        prices_dict[ticker] = ohlcv[price_col].rename(ticker)
        if (i + 1) % 50 == 0:
            logger.info("  Loaded %d/%d tickers (%.1fs)", i + 1, len(tickers), time.time() - t0)

    if skipped:
        logger.info("  Skipped %d tickers (insufficient data)", len(skipped))

    if len(prices_dict) < 5:
        logger.error("Not enough tickers with sufficient data (%d). Need at least 5.", len(prices_dict))
        sys.exit(1)

    # Build price matrix (aligned dates)
    prices = pd.DataFrame(prices_dict)
    prices = prices.dropna(how="all")
    # Forward fill small gaps
    prices = prices.ffill().dropna(how="all")

    # Filter to OOS period + training lookback
    train_start = (pd.Timestamp(args.oos_start) - pd.DateOffset(years=TRAIN_LOOKBACK_YEARS)).strftime("%Y-%m-%d")
    prices = prices.loc[train_start:args.oos_end]

    logger.info("Price matrix: %d days × %d tickers (%.1fs)", len(prices), prices.shape[1], time.time() - t0)

    # Per-ticker strategy returns (auto-select best strategy)
    logger.info("Computing per-ticker strategy returns (multi-strategy selection)...")
    strategy_returns_dict = {}
    per_ticker_metrics = []
    strategy_usage = {"donchian": 0, "rsi_meanrev": 0, "ema_envelope": 0}

    for ticker in prices.columns:
        close = prices[ticker].dropna()
        if len(close) < MIN_BARS:
            continue

        strat_name, rets = select_best_strategy(close, args.oos_start)
        strategy_usage[strat_name] += 1
        strategy_returns_dict[ticker] = rets

        # OOS metrics
        oos_rets = rets.loc[args.oos_start:args.oos_end]
        if len(oos_rets) > 0:
            sh = compute_sharpe(oos_rets)
            dd = compute_max_drawdown(oos_rets)
            per_ticker_metrics.append({
                "ticker": ticker,
                "strategy": strat_name,
                "sharpe": round(sh, 4),
                "max_dd": round(dd, 4),
                "n_bars": len(oos_rets),
            })

    logger.info("  %d tickers with strategy returns", len(strategy_returns_dict))
    logger.info("  Strategy selection: donchian=%d, rsi_meanrev=%d, ema_envelope=%d",
                strategy_usage["donchian"], strategy_usage["rsi_meanrev"], strategy_usage["ema_envelope"])

    # Compute ML signals (MLSignalProvider + MultiFactorModel) for each ticker
    logger.info("")
    logger.info("Computing ML signals (LightGBM MLSignal + MultiFactor)...")
    t_ml = time.time()
    ml_signals: dict[str, dict] = {}
    n_ml_ok = 0
    for i, ticker in enumerate(prices.columns):
        ohlcv_df = ticker_ohlcv.get(ticker)
        if ohlcv_df is None or len(ohlcv_df) < 200:
            continue
        ml_sig = compute_ml_signals_for_ticker(ticker, ohlcv_df, args.oos_start)
        ml_signals[ticker] = ml_sig
        if ml_sig["composite_signal"] != 0.0:
            n_ml_ok += 1
        if (i + 1) % 100 == 0:
            logger.info("  ML signals: %d/%d tickers (%.1fs)", i + 1, len(prices.columns), time.time() - t_ml)
    logger.info("  ML signals complete: %d/%d tickers with non-zero composite (%.1fs)",
                n_ml_ok, len(ml_signals), time.time() - t_ml)

    # Walk-forward portfolio backtest with HRP
    logger.info("")
    logger.info("Running walk-forward HRP portfolio optimization...")
    t1 = time.time()

    # Use strategy returns for portfolio (not raw returns)
    strat_df = pd.DataFrame(strategy_returns_dict)
    strat_df = strat_df.dropna(how="all").fillna(0.0)
    strat_df = strat_df.loc[train_start:args.oos_end]

    result = walk_forward_backtest(strat_df)

    logger.info("  Walk-forward complete: %d windows (%.1fs)", result["n_windows"], time.time() - t1)
    logger.info("  OOS Sharpe:  %+.4f", result["sharpe"])
    logger.info("  OOS Alpha:   %+.4f", result["alpha"])
    logger.info("  OOS MaxDD:   %.2f%%", result["max_dd"] * 100)

    # Score card
    n_valid = len(strategy_returns_dict)
    score_card = compute_score_card(result["sharpe"], result["alpha"], result["max_dd"], n_valid)

    logger.info("")
    logger.info("  Score Card:")
    logger.info("    Sharpe:          %.1f / 1.5", score_card["sharpe_score"])
    logger.info("    Alpha:           %.1f / 1.5", score_card["alpha_score"])
    logger.info("    MaxDD:           %.1f / 1.0", score_card["max_dd_score"])
    logger.info("    Diversification: %.1f / 1.0", score_card["diversification_score"])
    logger.info("    Total:           %.2f / 5.0", score_card["weighted_total"])
    logger.info("    Verdict:         %s", score_card["verdict"])

    # Top weights
    avg_w = result["avg_weights"]
    top_weights = sorted(avg_w.items(), key=lambda x: -x[1])[:10]
    logger.info("")
    logger.info("  Top 10 HRP weights (OOS average):")
    for ticker, w in top_weights:
        logger.info("    %-12s %6.2f%%", ticker, w * 100)

    # Per-ticker summary (top/bottom 5 by Sharpe)
    per_ticker_sorted = sorted(per_ticker_metrics, key=lambda x: -x["sharpe"])
    logger.info("")
    logger.info("  Top 5 tickers by OOS Sharpe:")
    for t in per_ticker_sorted[:5]:
        logger.info("    %-12s Sharpe=%+.3f  MaxDD=%.1f%%", t["ticker"], t["sharpe"], t["max_dd"] * 100)
    logger.info("  Bottom 5 tickers by OOS Sharpe:")
    for t in per_ticker_sorted[-5:]:
        logger.info("    %-12s Sharpe=%+.3f  MaxDD=%.1f%%", t["ticker"], t["sharpe"], t["max_dd"] * 100)

    # Save config JSON
    config = {
        "pipeline": "fast_hrp_walkforward",
        "generated_at": datetime.now().isoformat(),
        "n_tickers": n_valid,
        "n_tickers_total_db": len(tickers),
        "n_tickers_skipped": len(skipped),
        "oos_start": args.oos_start,
        "oos_end": args.oos_end,
        "train_lookback_years": TRAIN_LOOKBACK_YEARS,
        "max_weight": MAX_WEIGHT,
        "portfolio_validation": {
            "sharpe": round(result["sharpe"], 4),
            "alpha": round(result["alpha"], 6),
            "max_drawdown": round(result["max_dd"], 4),
            "n_windows": result["n_windows"],
            "weights": {k: round(v, 4) for k, v in avg_w.items()},
            "score": score_card["weighted_total"],
            "verdict": score_card["verdict"],
        },
        "score_card": score_card,
        "tickers": {
            t["ticker"]: {
                "oos_sharpe": t["sharpe"],
                "oos_max_dd": t["max_dd"],
                "strategy": t.get("strategy", "donchian"),
                "avg_weight": round(avg_w.get(t["ticker"], 0.0), 4),
                "ml_signal": ml_signals.get(t["ticker"], {}).get("ml_signal", 0.0),
                "multifactor_signal": ml_signals.get(t["ticker"], {}).get("multifactor_signal", 0.0),
                "composite_signal": ml_signals.get(t["ticker"], {}).get("composite_signal", 0.0),
                "top_factors": ml_signals.get(t["ticker"], {}).get("top_factors", {}),
            }
            for t in per_ticker_metrics
        },
        "weights_history": result["weights_history"],
    }

    with open(OUTPUT_CONFIG, "w") as f:
        json.dump(config, f, indent=2)
    logger.info("")
    logger.info("  Config saved: %s (%d bytes)", OUTPUT_CONFIG, OUTPUT_CONFIG.stat().st_size)

    # Save verdict JSON
    verdict = {
        "generated_at": datetime.now().isoformat(),
        "pipeline": "fast_hrp_walkforward",
        "score_card": score_card,
        "promoted_to_keep": score_card["verdict"] == "KEEP",
        "portfolio_metrics": {
            "sharpe": round(result["sharpe"], 4),
            "alpha": round(result["alpha"], 6),
            "max_drawdown": round(result["max_dd"], 4),
        },
        "portfolio_weights": {k: round(v, 4) for k, v in avg_w.items()},
        "n_tickers": n_valid,
        "n_windows": result["n_windows"],
        "per_ticker": per_ticker_sorted,
    }

    with open(OUTPUT_VERDICT, "w") as f:
        json.dump(verdict, f, indent=2)
    logger.info("  Verdict saved: %s (%d bytes)", OUTPUT_VERDICT, OUTPUT_VERDICT.stat().st_size)

    # Save per-ticker profiles to database
    logger.info("")
    logger.info("Saving ticker profiles to database (stock_personality)...")
    n_saved = save_ticker_profiles_to_db(conn, per_ticker_metrics, avg_w, prices, args.oos_start, ml_signals=ml_signals)
    logger.info("  Updated %d ticker profiles in stock_personality table", n_saved)

    logger.info("")
    logger.info("═══════════════════════════════════════════════════════════════")
    logger.info("  PIPELINE COMPLETE — %.1fs total", time.time() - t0)
    logger.info("  Score: %.2f/5.0 — Verdict: %s", score_card["weighted_total"], score_card["verdict"])
    logger.info("═══════════════════════════════════════════════════════════════")

    conn.close()
    sys.exit(0 if score_card["verdict"] == "KEEP" else 1)


if __name__ == "__main__":
    main()
